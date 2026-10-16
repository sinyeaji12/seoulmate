import random

from seoulmate.agent.gacha import grade_of, spin
from seoulmate.tools.registry import Tool, ToolRegistry

PLACES = [
    {"name": "서울숲", "category": "outdoor"},
    {"name": "경복궁", "category": "outdoor"},
    {"name": "DDP", "category": "indoor"},
    {"name": "국립중앙박물관", "category": "indoor"},
]
OBJ = {"type": "object"}


def make_registry(*, precip="none", crowds=None, temp=18, fail=(), places=PLACES):
    """호출 기록을 남기는 가짜 도구 세트. fail에 든 도구 이름은 항상 실패한다."""
    crowds = crowds or {}
    log: list[tuple[str, str]] = []

    def guard(name):
        if name in fail:
            raise RuntimeError("boom")

    def list_places(**kw):
        log.append(("list_places", ""))
        guard("list_places")
        return places

    def get_weather(area):
        log.append(("get_weather", area))
        guard("get_weather")
        return {"area": area, "temp_c": temp, "precip": precip, "pm10_grade": "좋음"}

    def get_crowd(place):
        log.append(("get_crowd", place))
        guard("get_crowd")
        return {"place": place, "level": crowds.get(place, "보통")}

    reg = ToolRegistry([Tool("list_places", "", OBJ, list_places), Tool("get_weather", "", OBJ, get_weather),
                        Tool("get_crowd", "", OBJ, get_crowd)])
    return reg, log


def seeds(n=40):
    return [random.Random(i) for i in range(n)]


def test_rain_never_picks_outdoor():
    reg, _ = make_registry(precip="비")
    for rng in seeds():
        r = spin(reg, rng)
        assert r.ok and r.pick["category"] == "indoor"
        assert "실내" in r.pick["reason"]


def test_very_crowded_place_is_excluded():
    reg, _ = make_registry(crowds={"경복궁": "붐빔"})
    picked = {spin(reg, rng).pick["place"] for rng in seeds(60)}
    assert "경복궁" not in picked and picked  # 다른 곳은 뽑힌다


def test_all_crowded_means_no_pick():
    reg, _ = make_registry(crowds={p["name"]: "붐빔" for p in PLACES})
    r = spin(reg, random.Random(1))
    assert not r.ok and r.pick is None


def test_pick_is_always_verified_by_weather_and_crowd_tools():
    reg, log = make_registry()
    for rng in seeds():
        del log[:]
        r = spin(reg, rng)
        assert ("get_weather", r.pick["place"]) in log and ("get_crowd", r.pick["place"]) in log
        assert log[0][0] == "list_places"
        assert {c["name"] for c in r.checked} >= {"get_weather", "get_crowd"}


def test_no_recommendation_when_weather_tool_fails():
    reg, log = make_registry(fail=("get_weather",))
    r = spin(reg, random.Random(0))
    assert not r.ok and r.pick is None
    assert all(name != "get_crowd" for name, _ in log)  # 날씨 미확인이면 혼잡도도 보지 않고 추천 안 함


def test_no_recommendation_when_crowd_tool_fails():
    reg, _ = make_registry(fail=("get_crowd",))
    r = spin(reg, random.Random(0))
    assert not r.ok and r.pick is None


def test_no_recommendation_when_list_fails():
    reg, log = make_registry(fail=("list_places",))
    r = spin(reg, random.Random(0))
    assert not r.ok and r.pick is None and log == [("list_places", "")]


def test_exclude_skips_already_drawn():
    reg, _ = make_registry()
    drawn = ["서울숲", "경복궁", "DDP"]
    assert all(spin(reg, rng, exclude=drawn).pick["place"] == "국립중앙박물관" for rng in seeds(10))


def test_food_is_never_drawn():
    places = PLACES + [{"name": "토속촌", "category": "food"}]
    reg, _ = make_registry(places=places)
    assert all(spin(reg, rng).pick["place"] != "토속촌" for rng in seeds())


def test_grades():
    good = {"temp_c": 18, "precip": "none", "pm10_grade": "좋음"}
    assert grade_of(good, "여유") == "SSR"
    assert grade_of(good, "보통") == "SR"
    assert grade_of(good, "약간 붐빔") == "R"
    assert grade_of({**good, "precip": "비"}, "여유") == "SR"  # 비 오면 SSR 불가
    assert grade_of({**good, "pm10_grade": "나쁨"}, "여유") == "SR"


def test_reason_mentions_weather_and_crowd():
    reg, _ = make_registry(crowds={"서울숲": "여유"}, places=[PLACES[0]])
    assert spin(reg, random.Random(0)).pick["reason"] == "지금 18도 맑음, 사람도 여유로워요"
