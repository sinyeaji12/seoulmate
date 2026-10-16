"""서울 가챠: 후보 중 랜덤으로 뽑되, 날씨·혼잡도 도구로 확인된 장소만 결과로 낸다.

LLM 없이 결정적으로 동작하지만 에이전트와 같은 원칙을 지킨다 — 도구로 확인하지 않은 장소는
절대 추천하지 않는다(랜덤도 예외 없음). 모든 조회는 ToolRegistry를 거치고, 확인 기록(checked)을 함께 돌려준다.
"""
import random
from dataclasses import dataclass, field

from seoulmate.tools.registry import ToolRegistry

MAX_ATTEMPTS = 8  # 후보 확인에 쓸 최대 시도 수(외부 API 호출 상한)
DRY = {"", "none", "없음", "-"}
BAD_DUST = {"나쁨", "매우나쁨", "매우 나쁨"}
SKIP_CROWD = {"붐빔"}  # '매우 붐비는' 곳은 제외 (약간 붐빔은 R 등급으로 허용)
CROWD_WORDS = {"여유": "사람도 여유로워요", "보통": "사람은 적당해요", "약간 붐빔": "조금 붐비지만 괜찮아요"}


@dataclass
class GachaResult:
    ok: bool
    message: str = ""
    pick: dict | None = None
    checked: list[dict] = field(default_factory=list)  # 도구 호출 기록(이름·입력·성공 여부)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "pick": self.pick, "checked": self.checked}


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


def spin(registry: ToolRegistry, rng: random.Random | None = None,
         exclude: list[str] | None = None) -> GachaResult:
    rng = rng or random.Random()
    checked: list[dict] = []

    def call(name: str, args: dict) -> dict:
        out = registry.call(name, args)
        checked.append({"name": name, "input": args, "ok": out["ok"]})
        return out

    listing = call("list_places", {"category": "all"})
    if not listing["ok"]:
        return GachaResult(False, "후보 장소를 불러오지 못했어요. 잠시 후 다시 돌려줘!", checked=checked)
    pool = [p for p in listing["data"] if p.get("name") not in (exclude or []) and p.get("category") != "food"]
    rng.shuffle(pool)

    for cand in pool[:MAX_ATTEMPTS]:
        name = cand["name"]
        w = call("get_weather", {"area": name})
        if not w["ok"]:
            continue  # 날씨를 확인하지 못한 곳은 추천하지 않는다
        if is_raining(w["data"].get("precip")) and cand.get("category") != "indoor":
            continue  # 비 오면 실내 위주
        c = call("get_crowd", {"place": name})
        if not c["ok"] or c["data"].get("level") in SKIP_CROWD or not c["data"].get("level"):
            continue  # 혼잡도 미확인·매우 붐빔 제외
        level = c["data"]["level"]
        weather = {k: w["data"].get(k) for k in ("temp_c", "precip", "pm10_grade")}
        nxt = (c["data"].get("next_hour") or {}).get("level") or ""
        return GachaResult(True, pick={
            "place": name, "category": cand.get("category", ""), "image": cand.get("image", ""),
            "grade": grade_of(weather, level), "reason": reason_of(weather, level, cand.get("category", "")),
            "crowd": level, "crowd_next": nxt, "weather": weather,
        }, checked=checked)
    return GachaResult(False, "지금 확인된 조건에 맞는 곳이 없어요. 조금 있다가 다시 돌려줘!", checked=checked)
