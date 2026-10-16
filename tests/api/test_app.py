import json

import httpx
import pytest
from fastapi.testclient import TestClient

from seoulmate.clients.placeimg import PlaceImages
from seoulmate.config import Settings
from seoulmate.web import app as webapp
from tests.conftest import FakeLLM, final, tool_use

COURSE = json.dumps({"summary": "s", "stops": [{"time": "10:00", "place": "서울숲", "reason": "r"}]},
                    ensure_ascii=False)


@pytest.fixture(autouse=True)
def _fresh_limiter():
    webapp.limiter._hits.clear()


def make_client(llm):
    return TestClient(webapp.create_app(Settings(seoulmate_mock_tools=True), llm_factory=lambda s: llm))


def image_client(*, search_status=200, found=True):
    seen: list[str] = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path.endswith("searchKeyword2"):
            if search_status != 200:
                return httpx.Response(search_status)
            items = [{"title": "북촌한옥마을", "contenttypeid": "12", "addr1": "서울특별시 종로구",
                      "firstimage": "http://tong.visitkorea.or.kr/a.jpg"}] if found else ""
            return httpx.Response(200, json={"response": {"header": {"resultCode": "0000"},
                                                          "body": {"items": {"item": items} if items else ""}}})
        return httpx.Response(200, content=b"IMG", headers={"content-type": "image/jpeg"})

    return TestClient(webapp.create_app(
        Settings(seoulmate_mock_tools=False, tour_api_key="k"), llm_factory=lambda s: None,
        images=PlaceImages("k", client=httpx.Client(transport=httpx.MockTransport(handler))))), seen


def events(text):
    out = []
    for chunk in text.strip().split("\n\n"):
        name, data = chunk.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_health():
    r = make_client(FakeLLM([])).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_index_served():
    assert "서울 메이트" in make_client(FakeLLM([])).get("/").text


def test_chat_streams_tool_then_result():
    c = make_client(FakeLLM([tool_use("get_crowd", {"place": "서울숲"}), final(COURSE)]))
    ev = events(c.post("/chat", json={"message": "오늘 어디 갈까?"}).text)
    assert [e[0] for e in ev] == ["tool", "result"]
    assert ev[1][1]["course"]["stops"][0]["crowd"] == "여유"


def test_gacha_endpoint_uses_tools_and_skips_crowded():
    c = make_client(FakeLLM([]))
    for _ in range(8):
        d = c.post("/gacha", json={}).json()
        assert d["ok"] and d["pick"]["place"] != "경복궁"  # mock: 경복궁은 '붐빔'
        assert d["pick"]["grade"] in ("SSR", "SR", "R")
        assert {x["name"] for x in d["checked"]} >= {"get_weather", "get_crowd"}
        webapp.limiter._hits.clear()


def test_gacha_stream_sends_tool_progress_then_verified_result():
    c = make_client(FakeLLM([]))
    ev = events(c.post("/gacha/stream", json={}).text)
    names = [e[0] for e in ev]
    assert names[-1] == "result" and names.count("tool") >= 2
    assert [e[1]["name"] for e in ev if e[0] == "tool"][:2] == ["get_weather", "get_crowd"]  # 확인이 먼저
    assert ev[-1][1]["ok"] and ev[-1][1]["pick"]["place"]


def test_gacha_rejects_too_many_excludes():
    assert make_client(FakeLLM([])).post("/gacha", json={"exclude": ["a"] * 11}).status_code == 422


def test_rejects_empty_and_too_long():
    c = make_client(FakeLLM([]))
    assert c.post("/chat", json={"message": ""}).status_code == 422
    assert c.post("/chat", json={"message": "가" * 501}).status_code == 422


def test_llm_error_is_generic():
    def boom(s):
        raise RuntimeError("sk-ant-secret")

    c = TestClient(webapp.create_app(Settings(seoulmate_mock_tools=True), llm_factory=boom))
    text = c.post("/chat", json={"message": "x"}).text
    assert "sk-ant" not in text and "event: error" in text


def test_rate_limit():
    c = make_client(FakeLLM([final("{}") for _ in range(12)]))
    codes = [c.post("/chat", json={"message": "x"}).status_code for _ in range(11)]
    assert codes[-1] == 429


def test_place_image_served_through_backend_with_cache_headers():
    c, _ = image_client()
    r = c.get("/place-image", params={"name": "북촌한옥마을"})
    assert r.status_code == 200 and r.content == b"IMG" and r.headers["content-type"] == "image/jpeg"
    assert "max-age=86400" in r.headers["cache-control"]


def test_place_image_404_when_no_photo():
    c, _ = image_client(found=False)
    r = c.get("/place-image", params={"name": "경복궁"})
    assert r.status_code == 404 and r.content == b""


def test_place_image_502_when_tourapi_fails_without_leaking():
    c, _ = image_client(search_status=500)
    r = c.get("/place-image", params={"name": "북촌한옥마을"})
    assert r.status_code == 502 and "k" not in r.text and r.headers["cache-control"] == "no-store"


def test_place_image_is_cached_per_place():
    c, seen = image_client()
    for _ in range(3):
        c.get("/place-image", params={"name": "북촌한옥마을"})
    assert sum(p.endswith("searchKeyword2") for p in seen) == 1


def test_place_image_mock_mode_makes_no_external_call():
    r = make_client(FakeLLM([])).get("/place-image", params={"name": "북촌한옥마을"})
    assert r.status_code == 404


def test_place_image_validates_name():
    c = make_client(FakeLLM([]))
    assert c.get("/place-image").status_code == 422
    assert c.get("/place-image", params={"name": "가" * 61}).status_code == 422
