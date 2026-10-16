from seoulmate.clients.seoul import fetch_citydata

_MOCK = {"경복궁": "붐빔", "북촌한옥마을": "약간 붐빔", "서울숲": "여유", "DDP": "보통"}


def get_crowd(place: str, *, mock: bool = True, api_key: str = "") -> dict:
    """장소 혼잡도(여유/보통/약간 붐빔/붐빔)."""
    if mock:
        return {"place": place, "level": _MOCK.get(place, "보통"), "source": "mock"}
    p = fetch_citydata(place, api_key)["LIVE_PPLTN_STTS"][0]
    nxt = (p.get("FCST_PPLTN") or [{}])[0]
    return {
        "place": place,
        "level": p["AREA_CONGEST_LVL"],
        "message": p.get("AREA_CONGEST_MSG", ""),
        "observed_at": p.get("PPLTN_TIME", ""),
        "next_hour": {"time": nxt.get("FCST_TIME"), "level": nxt.get("FCST_CONGEST_LVL")},
        "source": "seoul-citydata",
    }
