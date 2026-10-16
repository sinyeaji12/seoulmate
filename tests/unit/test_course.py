import json

from seoulmate.agent.loop import run_agent
from seoulmate.agent.schemas import build_course
from tests.conftest import FakeLLM, final, tool_use

CALLS = [
    {"name": "list_places", "input": {}, "result": {"ok": True, "data": [
        {"name": "서울숲", "image": "http://img/1.jpg"}, {"name": "DDP", "image": ""}]}},
    {"name": "get_crowd", "input": {"place": "서울숲"},
     "result": {"ok": True, "data": {"place": "서울숲", "level": "여유"}}},
]


def _answer(*places):
    return "```json\n" + json.dumps({"summary": "s", "stops": [
        {"time": "10:00", "place": p, "reason": "r"} for p in places]}, ensure_ascii=False) + "\n```"


def test_enriches_image_and_crowd_from_tool_results():
    c = build_course(_answer("서울숲", "DDP"), CALLS)
    assert (c.stops[0].image, c.stops[0].crowd) == ("http://img/1.jpg", "여유")
    assert (c.stops[1].image, c.stops[1].crowd) == ("", "")  # 사진·혼잡도 없으면 빈 값


def test_model_cannot_inject_image_url():
    ans = json.dumps({"summary": "s", "stops": [
        {"time": "1", "place": "서울숲", "reason": "r", "image": "http://evil/x.png"}]})
    assert build_course(ans, CALLS).stops[0].image == "http://img/1.jpg"


def test_invalid_json_returns_none():
    assert build_course("그냥 텍스트", CALLS) is None
    assert build_course('{"summary": "s"}', CALLS) is None


def test_run_agent_attaches_course(registry):
    llm = FakeLLM([tool_use("get_crowd", {"place": "서울숲"}), final(_answer("서울숲"))])
    r = run_agent("x", llm, registry)
    assert r.course and r.course.stops[0].crowd == "여유"


def test_festival_filters_by_today(registry):
    out = registry.call("list_festivals", {})
    assert out["ok"] and isinstance(out["data"], list)


def test_festival_period_filter():
    from seoulmate.tools.festivals import list_festivals

    assert list_festivals(mock=True, today="20261015")[0]["name"] == "서울 가을 야시장"
    assert list_festivals(mock=True, today="20261201") == []


def test_course_carries_category_weather_and_forecast():
    calls = CALLS + [
        {"name": "get_weather", "input": {"area": "서울숲"},
         "result": {"ok": True, "data": {"area": "서울숲", "temp_c": 21.0, "precip": "없음", "pm10_grade": "좋음"}}},
        {"name": "get_crowd", "input": {"place": "DDP"},
         "result": {"ok": True, "data": {"place": "DDP", "level": "보통", "next_hour": {"level": "붐빔"}}}},
    ]
    calls[0]["result"]["data"][0]["category"] = "outdoor"
    c = build_course(_answer("서울숲", "DDP"), calls)
    assert c.weather["temp_c"] == 21.0
    assert c.stops[0].category == "outdoor"
    assert c.stops[1].crowd_next == "붐빔"
