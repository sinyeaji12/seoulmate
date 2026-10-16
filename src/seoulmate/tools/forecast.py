from datetime import date, datetime, timedelta

from seoulmate.clients.kma import KST, fetch_forecast

SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
SLOTS = {"morning": range(6, 12), "afternoon": range(12, 18), "evening": range(18, 24)}
WHEN = ("today", "tomorrow", "saturday", "sunday")
_MOCK_SLOT = {"temp_min": 14, "temp_max": 21, "pop": 20, "sky": "맑음", "precip": "없음"}


def resolve_date(when: str, today: date) -> date:
    """today/tomorrow/saturday/sunday → 날짜. 요일은 오늘 포함 가장 가까운 앞날."""
    if when == "today":
        return today
    if when == "tomorrow":
        return today + timedelta(days=1)
    if when in ("saturday", "sunday"):
        target = 5 if when == "saturday" else 6
        return today + timedelta(days=(target - today.weekday()) % 7)
    raise ValueError(f"when은 {', '.join(WHEN)} 중 하나여야 해요")


def _mode(values: list[str], names: dict[str, str]) -> str:
    seen = [names[v] for v in values if v in names]
    return max(set(seen), key=seen.count) if seen else ""


def summarize(items: list[dict], day: date) -> dict:
    """해당 날짜의 시간별 예보를 하루·오전·오후·저녁으로 묶는다. 값이 없는 구간은 빠진다."""
    ymd = day.strftime("%Y%m%d")
    by_hour: dict[int, dict[str, str]] = {}
    for it in items:
        if it["fcstDate"] == ymd:
            by_hour.setdefault(int(it["fcstTime"][:2]), {})[it["category"]] = it["fcstValue"]
    if not by_hour:
        raise LookupError(f"{day.isoformat()} 예보는 아직 제공되지 않아요(단기예보는 며칠 앞까지만 있어요)")

    def pack(hours: list[dict]) -> dict | None:
        temps = [float(h["TMP"]) for h in hours if "TMP" in h]
        if not temps:
            return None
        pops = [float(h["POP"]) for h in hours if "POP" in h]
        out = {"temp_min": round(min(temps)), "temp_max": round(max(temps)),
               "sky": _mode([h.get("SKY", "") for h in hours], SKY),
               "precip": _mode([h.get("PTY", "") for h in hours], PTY) or ""}
        if pops:
            out["pop"] = round(max(pops))
        return out

    result = {"day": pack(list(by_hour.values()))}
    for name, rng in SLOTS.items():
        result[name] = pack([v for h, v in by_hour.items() if h in rng])
    return {k: v for k, v in result.items() if v}


def get_forecast(district: str, when: str = "tomorrow", *, mock: bool = True, api_key: str = "",
                 now: datetime | None = None) -> dict:
    """기상청 단기예보. district=서울 구 이름, when=today|tomorrow|saturday|sunday."""
    now = now or datetime.now(KST)
    day = resolve_date(when, now.astimezone(KST).date())
    if mock:
        return {"district": district, "date": day.isoformat(), "when": when,
                "slots": {"day": _MOCK_SLOT, "afternoon": _MOCK_SLOT}, "source": "mock"}
    items = fetch_forecast(district, api_key, now)
    return {"district": district, "date": day.isoformat(), "when": when, "slots": summarize(items, day),
            "source": "kma-vilage-fcst"}
