import random

from seoulmate.agent.gacha import SPOTS, grade_of, spin
from seoulmate.clients.seoul import SUPPORTED_AREAS
from seoulmate.tools.registry import Tool, ToolRegistry

OBJ = {"type": "object"}


def spot(name, category):
    return {"name": name, "area": name + "지역", "category": category}


PLACES = [spot("서울숲", "outdoor"), spot("경복궁", "outdoor"), spot("DDP", "indoor"), spot("박물관", "indoor")]


def make_registry(*, precip="none", crowds=None, temp=18, fail=(), crowd_next=""):
    """호출 기록을 남기는 가짜 도구 세트. 날씨·혼잡도는 area(= 이름+'지역')로 조회된다. fail은 항상 실패할 도구."""
    crowds = crowds or {}
    log: list[tuple[str, str]] = []

    def guard(name):
        if name in fail:
            raise RuntimeError("boom http://x/SECRETKEY/json")

    def get_weather(area):
        log.append(("get_weather", area))
        guard("get_weather")
        return {"area": area, "temp_c": temp, "precip": precip, "pm10_grade": "좋음"}

    def get_crowd(place):
        log.append(("get_crowd", place))
        guard("get_crowd")
        return {"place": place, "level": crowds.get(place.removesuffix("지역"), "보통"),
                "next_hour": {"level": crowd_next}}

    reg = ToolRegistry([Tool("get_weather", "", OBJ, get_weather), Tool("get_crowd", "", OBJ, get_crowd)])
    return reg, log


def seeds(n=40):
    return [random.Random(i) for i in range(n)]


def run(reg, rng, **kw):
    kw.setdefault("spots", PLACES)
    return spin(reg, rng, **kw)


# ---- 후보 목록(근본 원인 회귀 방지) ----
def test_curated_spots_are_all_realtime_supported_and_mixed():
    assert len(SPOTS) >= 15
    assert {s["category"] for s in SPOTS} == {"indoor", "outdoor"}
    assert [s["area"] for s in SPOTS if s["area"] not in SUPPORTED_AREAS] == []
    assert len({s["name"] for s in SPOTS}) == len(SPOTS)


# ---- 비 / 붐빔 / 도구 확인 규칙 ----
def test_rain_never_picks_outdoor():
    reg, _ = make_registry(precip="비")
    for rng in seeds():
        r = run(reg, rng)
        assert r.ok and r.pick["category"] == "indoor"
        assert "실내" in r.pick["reason"]


def test_rain_finds_indoor_even_when_most_candidates_are_outdoor():
    spots = [spot(f"야외{i}", "outdoor") for i in range(12)] + [spot("실내", "indoor")]
    reg, _ = make_registry(precip="비")
    for rng in seeds():
        assert run(reg, rng, spots=spots).pick["place"] == "실내"


def test_very_crowded_place_is_excluded_when_alternatives_exist():
    reg, _ = make_registry(crowds={"경복궁": "붐빔"})
    picked = {run(reg, rng).pick["place"] for rng in seeds(60)}
    assert "경복궁" not in picked and picked


def test_pick_is_always_verified_by_weather_and_crowd_tools():
    reg, log = make_registry()
    for rng in seeds():
        del log[:]
        r = run(reg, rng)
        area = r.pick["place"] + "지역"
        assert ("get_weather", area) in log and ("get_crowd", area) in log


def test_fallback_pick_is_also_tool_verified():
    reg, log = make_registry(crowds={p["name"]: "붐빔" for p in PLACES})
    r = run(reg, random.Random(0))
    area = r.pick["place"] + "지역"
    assert ("get_weather", area) in log and ("get_crowd", area) in log


# ---- 도구 실패는 진짜 이유로 ----
def test_weather_failure_reports_real_reason_and_recommends_nothing():
    reg, log = make_registry(fail=("get_weather",))
    r = run(reg, random.Random(0))
    assert not r.ok and r.pick is None
    assert "날씨 정보를 못 불러왔어요" in r.message and "API 연결 확인 필요" in r.message
    assert all(name != "get_crowd" for name, _ in log)
    assert len([n for n, _ in log if n == "get_weather"]) == 3  # 3번 연속 실패하면 중단(호출 낭비 방지)


def test_crowd_failure_reports_real_reason_and_recommends_nothing():
    reg, _ = make_registry(fail=("get_crowd",))
    r = run(reg, random.Random(0))
    assert not r.ok and r.pick is None and "혼잡도 정보를 못 불러왔어요" in r.message


def test_error_details_never_leak_to_client():
    reg, _ = make_registry(fail=("get_weather",))
    blob = str(run(reg, random.Random(0)).to_dict())
    assert "SECRETKEY" not in blob and "boom" not in blob


# ---- 차선책 ----
def test_all_crowded_falls_back_to_least_crowded_instead_of_empty():
    reg, _ = make_registry(crowds={p["name"]: "붐빔" for p in PLACES})
    r = run(reg, random.Random(1))
    assert r.ok and r.pick["fallback"] is True and r.pick["grade"] == "R"
    assert "제일 여유" in r.pick["reason"]


def test_fallback_prefers_better_next_hour_forecast():
    # 전부 붐빔이면 다음 시간 예보가 더 나은 곳이 아니라, 최소한 확인된 곳 중에서만 고른다
    reg, _ = make_registry(crowds={p["name"]: "붐빔" for p in PLACES}, crowd_next="보통")
    assert run(reg, random.Random(2)).pick["place"] in {p["name"] for p in PLACES}


def test_fallback_respects_rain_indoor_only():
    reg, _ = make_registry(precip="비", crowds={p["name"]: "붐빔" for p in PLACES})
    for rng in seeds(10):
        r = run(reg, rng)
        assert r.ok and r.pick["category"] == "indoor"


def test_rain_with_no_indoor_spot_gives_honest_message():
    reg, _ = make_registry(precip="비")
    r = run(reg, random.Random(0), spots=[spot("야외", "outdoor")])
    assert not r.ok and "실내" in r.message


def test_normal_pick_is_not_marked_fallback():
    reg, _ = make_registry()
    assert run(reg, random.Random(0)).pick["fallback"] is False


# ---- 기타 ----
def test_exclude_skips_already_drawn():
    reg, _ = make_registry()
    drawn = ["서울숲", "경복궁", "DDP"]
    assert all(run(reg, rng, exclude=drawn).pick["place"] == "박물관" for rng in seeds(10))


def test_everything_drawn_gives_message_not_crash():
    reg, _ = make_registry()
    r = run(reg, random.Random(0), exclude=[p["name"] for p in PLACES])
    assert not r.ok and r.message


def test_rejected_list_has_reason_codes():
    reg, _ = make_registry(crowds={"경복궁": "붐빔"})
    for rng in seeds(30):
        r = run(reg, rng)
        assert all(x["reason"] in {"too_crowded", "weather_failed", "crowd_failed", "rain_outdoor"} for x in r.rejected)


def test_grades():
    good = {"temp_c": 18, "precip": "none", "pm10_grade": "좋음"}
    assert grade_of(good, "여유") == "SSR"
    assert grade_of(good, "보통") == "SR"
    assert grade_of(good, "약간 붐빔") == "R"
    assert grade_of({**good, "precip": "비"}, "여유") == "SR"
    assert grade_of({**good, "pm10_grade": "나쁨"}, "여유") == "SR"


def test_reason_mentions_weather_and_crowd():
    reg, _ = make_registry(crowds={"서울숲": "여유"})
    r = run(reg, random.Random(0), spots=[PLACES[0]])
    assert r.pick["reason"] == "지금 18도 맑음, 사람도 여유로워요"
