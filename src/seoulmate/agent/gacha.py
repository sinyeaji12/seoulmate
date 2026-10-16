"""서울 가챠: 후보 중 랜덤으로 뽑되, 날씨·혼잡도 도구로 확인된 장소만 결과로 낸다.

LLM 없이 결정적으로 동작하지만 에이전트와 같은 원칙을 지킨다 — 도구로 확인하지 않은 장소는
절대 추천하지 않는다(랜덤·차선책도 예외 없음). 모든 조회는 ToolRegistry를 거치고, 확인 기록(checked)을 함께 돌려준다.

후보는 서울시 실시간 데이터가 실제로 응답하는 지역명(`area`)으로만 구성한다. 관광공사 목록의 임의 장소는
이름이 지원 지역과 달라 날씨·혼잡도를 확인할 수 없으므로 후보로 쓰지 않는다.
"""
import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from seoulmate.tools.registry import ToolRegistry

SPOTS: list[dict] = json.loads((Path(__file__).parent.parent / "data" / "gacha_spots.json").read_text("utf-8"))
MAX_ATTEMPTS = 10  # 후보 확인에 쓸 최대 시도 수(외부 API 호출 상한)
MAX_WEATHER_FAILS = 3  # 날씨 조회가 연달아 이만큼 실패하면 API 문제로 보고 중단
DRY = {"", "none", "없음", "-"}
BAD_DUST = {"나쁨", "매우나쁨", "매우 나쁨"}
SKIP_CROWD = {"붐빔"}  # '매우 붐비는' 곳은 제외 (약간 붐빔은 R 등급으로 허용)
RANK = {"여유": 0, "보통": 1, "약간 붐빔": 2, "붐빔": 3}
CROWD_WORDS = {"여유": "사람도 여유로워요", "보통": "사람은 적당해요", "약간 붐빔": "조금 붐비지만 괜찮아요"}


@dataclass
class GachaResult:
    ok: bool
    message: str = ""
    pick: dict | None = None
    checked: list[dict] = field(default_factory=list)  # 도구 호출 기록(이름·입력·성공 여부)
    rejected: list[dict] = field(default_factory=list)  # 탈락 후보와 이유 코드(원문 오류는 담지 않는다)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "pick": self.pick,
                "checked": self.checked, "rejected": self.rejected}


def is_raining(precip: str | None) -> bool:
    return str(precip or "").strip().lower() not in DRY


def weather_is_good(w: dict) -> bool:
    temp = w.get("temp_c")
    comfy = temp is None or 5 <= float(temp) <= 29
    return not is_raining(w.get("precip")) and w.get("pm10_grade") not in BAD_DUST and comfy


def grade_of(weather: dict, crowd: str) -> str:
    """SSR: 날씨 좋음+한산 / SR: 보통(여유·보통 혼잡) / R: 무난."""
    if weather_is_good(weather) and crowd == "여유":
        return "SSR"
    return "SR" if crowd in ("여유", "보통") else "R"


def reason_of(weather: dict, crowd: str, category: str) -> str:
    temp = weather.get("temp_c")
    rain = is_raining(weather.get("precip"))
    t = f"{round(float(temp))}도 " if temp is not None else ""
    sky = f"{t}{weather.get('precip')}" if rain else f"{t}맑음"
    head = f"비가 와서 실내로 골랐어요. 지금 {sky}" if rain and category == "indoor" else f"지금 {sky}"
    return f"{head}, {CROWD_WORDS.get(crowd, '혼잡도도 확인했어요')}"


def _pick(spot: dict, weather: dict, crowd: str, nxt: str, *, fallback: bool = False) -> dict:
    cat = spot.get("category", "")
    base = {"place": spot["name"], "category": cat, "image": spot.get("image", ""),
            "crowd": crowd, "crowd_next": nxt, "weather": weather, "fallback": fallback}
    if fallback:
        return {**base, "grade": "R", "reason": f"지금 {_sky(weather)}. 다 붐비지만 그나마 여기가 제일 여유로워요"}
    return {**base, "grade": grade_of(weather, crowd), "reason": reason_of(weather, crowd, cat)}


def _sky(weather: dict) -> str:
    t = f"{round(float(weather['temp_c']))}도 " if weather.get("temp_c") is not None else ""
    return t + (str(weather.get("precip")) if is_raining(weather.get("precip")) else "맑음")


def spin(registry: ToolRegistry, rng: random.Random | None = None, exclude: list[str] | None = None,
         spots: list[dict] | None = None, on_call: Callable[[dict], None] | None = None) -> GachaResult:
    rng = rng or random.Random()
    checked: list[dict] = []
    rejected: list[dict] = []

    def call(name: str, args: dict) -> dict:
        out = registry.call(name, args)
        checked.append({"name": name, "input": args, "ok": out["ok"]})
        if on_call:  # 화면이 실제 도구 호출 진행(날씨 → 혼잡도)에 맞춰 문구를 바꿀 수 있게
            on_call(checked[-1])
        return out

    def reject(spot: dict, why: str) -> None:
        rejected.append({"place": spot["name"], "reason": why})

    pool = [s for s in (SPOTS if spots is None else spots) if s["name"] not in (exclude or [])]
    rng.shuffle(pool)
    rainy = False
    weather_ok = crowd_calls = crowd_ok = weather_fails = 0
    verified: list[tuple[dict, dict, str, str]] = []  # (spot, weather, crowd, next) — 날씨·혼잡도 둘 다 확인된 후보
    attempts = 0

    while pool and attempts < MAX_ATTEMPTS:
        spot = pool.pop(0)
        attempts += 1
        w = call("get_weather", {"area": spot["area"]})
        if not w["ok"]:
            reject(spot, "weather_failed")
            weather_fails += 1
            if weather_ok == 0 and weather_fails >= MAX_WEATHER_FAILS:
                break  # 날씨를 한 번도 못 불러왔다 → API 연결 문제
            continue
        weather_ok += 1
        weather = {k: w["data"].get(k) for k in ("temp_c", "precip", "pm10_grade")}
        if is_raining(weather["precip"]):
            if not rainy:  # 비는 도시 전체 조건 → 남은 후보를 실내로 좁힌다
                rainy = True
                pool = [s for s in pool if s.get("category") == "indoor"]
            if spot.get("category") != "indoor":
                reject(spot, "rain_outdoor")
                continue
        crowd_calls += 1
        c = call("get_crowd", {"place": spot["area"]})
        level = (c["data"].get("level") if c["ok"] else "") or ""
        if not c["ok"] or level not in RANK:
            reject(spot, "crowd_failed")
            continue
        crowd_ok += 1
        nxt = (c["data"].get("next_hour") or {}).get("level") or ""
        if level in SKIP_CROWD:
            reject(spot, "too_crowded")
            verified.append((spot, weather, level, nxt))
            continue
        return GachaResult(True, pick=_pick(spot, weather, level, nxt), checked=checked, rejected=rejected)

    if verified:  # 조건에 맞는 곳이 없으면 확인된 곳 중 가장 덜 붐비는 곳을 차선책으로
        spot, weather, level, nxt = min(verified, key=lambda v: (RANK[v[2]], RANK.get(v[3], 3)))
        return GachaResult(True, pick=_pick(spot, weather, level, nxt, fallback=True),
                           checked=checked, rejected=rejected)
    if weather_ok == 0:
        msg = "날씨 정보를 못 불러왔어요 (API 연결 확인 필요)" if checked else "뽑을 후보가 없어요. 이미 다 뽑았나 봐!"
    elif crowd_calls and crowd_ok == 0:  # 혼잡도를 실제로 조회했는데 전부 실패한 경우만
        msg = "혼잡도 정보를 못 불러왔어요 (API 연결 확인 필요)"
    elif rainy:
        msg = "비가 오는데 확인된 실내 장소가 없어요. 조금 있다가 다시 돌려줘!"
    else:
        msg = "지금은 확인된 장소가 없어요. 조금 있다가 다시 돌려줘!"
    return GachaResult(False, msg, checked=checked, rejected=rejected)
