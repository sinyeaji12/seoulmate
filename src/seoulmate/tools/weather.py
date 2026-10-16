from seoulmate.clients.seoul import fetch_citydata

_MOCK = {"temp_c": 18, "precip": "none", "pm10_grade": "보통", "source": "mock"}


def get_weather(area: str, *, mock: bool = True, api_key: str = "") -> dict:
    """현재 날씨. mock 모드는 키 없이 고정 응답(테스트·평가 재현성)."""
    if mock:
        return {"area": area, **_MOCK}
    w = fetch_citydata(area, api_key)["WEATHER_STTS"][0]
    return {
        "area": area,
        "temp_c": float(w["TEMP"]),
        "precip": w.get("PRECPT_TYPE", ""),  # 없음/비/눈 등
        "precip_mm": w.get("PRECIPITATION", "-"),
        "pm10_grade": w.get("PM10_INDEX", ""),
        "observed_at": w.get("WEATHER_TIME", ""),
        "source": "seoul-citydata",
    }
