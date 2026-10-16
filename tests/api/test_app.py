import json

import pytest
from fastapi.testclient import TestClient

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
