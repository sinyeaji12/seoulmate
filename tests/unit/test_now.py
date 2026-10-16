"""'오늘의 서울' 지면: 기존 get_crowd 결과를 한산한 곳 / 붐비는 곳으로 나누는 규칙과 캐싱."""
from fastapi.testclient import TestClient

from seoulmate.agent.now import SeoulNow, snapshot
from seoulmate.config import Settings
from seoulmate.tools.registry import Tool, ToolRegistry
from seoulmate.web import app as webapp


def spots(*names):
    return [{"name": n, "area": f"{n}-area"} for n in names]


def registry(levels: dict, observed="2026-10-16 18:50", fail=()):
    """get_crowd만 가진 가짜 레지스트리. levels: area -> 단계"""
    calls = []

    def get_crowd(place):
        calls.append(place)
        if place in fail:
            raise RuntimeError("boom")
        return {"place": place, "level": levels[place], "observed_at": observed}

    reg = ToolRegistry([Tool("get_crowd", "", {"type": "object"}, get_crowd)])
    reg.calls = calls
    return reg


def test_splits_calm_and_busy_and_keeps_only_three_each():
    names = [f"c{i}" for i in range(5)] + [f"b{i}" for i in range(5)] + ["mid"]
    lv = {f"c{i}-area": "여유" for i in range(5)} | {f"b{i}-area": "붐빔" for i in range(5)} | {"mid-area": "보통"}
    out = snapshot(registry(lv), spots(*names))
    assert [x["name"] for x in out["calm"]] == ["c0", "c1", "c2"]
    assert [x["name"] for x in out["busy"]] == ["b0", "b1", "b2"]
    assert all(x["level"] == "여유" for x in out["calm"])  # '보통'은 한산한 곳에 넣지 않는다
    assert out["ok"] and out["checked"] == 11 and out["total"] == 11


def test_busier_level_comes_first_and_ties_keep_list_order():
    lv = {"a-area": "약간 붐빔", "b-area": "붐빔", "c-area": "약간 붐빔", "d-area": "붐빔"}
    out = snapshot(registry(lv), spots("a", "b", "c", "d"))
    assert [(x["name"], x["level"]) for x in out["busy"]] == [("b", "붐빔"), ("d", "붐빔"), ("a", "약간 붐빔")]


def test_fewer_than_three_shows_only_what_exists_and_empty_side_is_empty():
    out = snapshot(registry({"a-area": "여유", "b-area": "보통"}), spots("a", "b"))
    assert [x["name"] for x in out["calm"]] == ["a"] and out["busy"] == []


def test_failed_lookups_are_dropped_not_guessed():
    out = snapshot(registry({"a-area": "여유", "b-area": "여유"}, fail={"a-area"}), spots("a", "b"))
    assert [x["name"] for x in out["calm"]] == ["b"] and out["checked"] == 1 and out["total"] == 2


def test_all_failed_is_not_ok():
    out = snapshot(registry({"a-area": "여유"}, fail={"a-area"}), spots("a"))
    assert out["ok"] is False and out["calm"] == [] and out["busy"] == [] and out["observed_at"] == ""


def test_reference_time_is_the_oldest_shown_observation():
    reg = ToolRegistry([Tool("get_crowd", "", {"type": "object"}, lambda place: {
        "level": "여유", "observed_at": {"a-area": "2026-10-16 18:55", "b-area": "2026-10-16 18:45"}[place]})])
    out = snapshot(reg, spots("a", "b"))
    assert (out["observed_date"], out["observed_at"]) == ("2026-10-16", "18:45")


def test_each_area_is_called_once_in_parallel_without_reordering():
    reg = registry({f"p{i}-area": "여유" for i in range(8)})
    out = snapshot(reg, spots(*[f"p{i}" for i in range(8)]), workers=4)
    assert sorted(reg.calls) == sorted(f"p{i}-area" for i in range(8))
    assert [x["name"] for x in out["calm"]] == ["p0", "p1", "p2"]


def test_cache_reuses_result_until_ttl_and_never_caches_failures():
    t = [0.0]
    made = []

    def factory():
        made.append(1)
        return registry({"a-area": "여유"})

    svc = SeoulNow(factory, ttl=300, spots=spots("a"), clock=lambda: t[0])
    assert svc.get()["ok"] and svc.get()["ok"] and len(made) == 1
    t[0] = 299
    svc.get(); assert len(made) == 1
    t[0] = 301
    svc.get(); assert len(made) == 2  # 만료 후 다시 조회

    bad = SeoulNow(lambda: registry({"a-area": "여유"}, fail={"a-area"}), spots=spots("a"))
    assert bad.get()["ok"] is False and bad.get()["ok"] is False  # 실패는 캐싱하지 않는다(매번 다시 시도)


def test_sample_mode_never_calls_tools_and_unexpected_errors_are_contained():
    def never():
        raise AssertionError("샘플 모드에서는 도구를 부르면 안 된다")

    assert SeoulNow(never, enabled=False).get() == {"ok": False, "reason": "sample_mode"}

    def broken():
        raise RuntimeError("registry down")

    assert SeoulNow(broken, spots=spots("a")).get() == {"ok": False, "reason": "unavailable"}


# ---------- HTTP ----------
class FakeNow:
    def __init__(self, data):
        self.data, self.calls = data, 0

    def get(self):
        self.calls += 1
        return self.data


def client(data):
    return TestClient(webapp.create_app(Settings(seoulmate_mock_tools=False), now=FakeNow(data)))


def test_endpoint_returns_snapshot_with_shared_cache_headers():
    webapp.now_limiter._hits.clear()
    data = {"ok": True, "observed_at": "18:45", "observed_date": "2026-10-16", "calm": [{"name": "서촌", "level": "여유"}], "busy": [], "checked": 5, "total": 23}
    r = client(data).get("/seoul-now")
    assert r.status_code == 200 and r.json() == data
    assert "s-maxage=300" in r.headers["cache-control"]


def test_endpoint_does_not_cache_unavailable_or_sample_responses():
    webapp.now_limiter._hits.clear()
    r = client({"ok": False, "reason": "unavailable"}).get("/seoul-now")
    assert r.json()["ok"] is False and r.headers["cache-control"] == "no-store"


def test_endpoint_in_sample_mode_makes_no_external_call():
    webapp.now_limiter._hits.clear()
    r = TestClient(webapp.create_app(Settings(seoulmate_mock_tools=True))).get("/seoul-now")
    assert r.json() == {"ok": False, "reason": "sample_mode"}


def test_endpoint_is_rate_limited():
    webapp.now_limiter._hits.clear()
    c = client({"ok": False, "reason": "unavailable"})
    codes = [c.get("/seoul-now").status_code for _ in range(31)]
    assert codes[-1] == 429
    webapp.now_limiter._hits.clear()
