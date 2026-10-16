def test_list_places_filters(registry):
    out = registry.call("list_places", {"category": "indoor"})
    assert out["ok"] and all(p["category"] == "indoor" for p in out["data"])


def test_crowd_mock(registry):
    assert registry.call("get_crowd", {"place": "경복궁"})["data"]["level"] == "붐빔"


def test_real_crowd_parses_citydata(monkeypatch):
    from seoulmate.tools import crowd

    fake = {"LIVE_PPLTN_STTS": [{"AREA_CONGEST_LVL": "보통", "AREA_CONGEST_MSG": "m",
            "PPLTN_TIME": "t", "FCST_PPLTN": [{"FCST_TIME": "15:00", "FCST_CONGEST_LVL": "약간 붐빔"}]}]}
    monkeypatch.setattr(crowd, "fetch_citydata", lambda area, key: fake)
    out = crowd.get_crowd("경복궁", mock=False, api_key="k")
    assert out["level"] == "보통" and out["next_hour"]["level"] == "약간 붐빔"


def test_real_weather_parses_citydata(monkeypatch):
    from seoulmate.tools import weather

    fake = {"WEATHER_STTS": [{"TEMP": "23.4", "PRECPT_TYPE": "없음", "PM10_INDEX": "좋음"}]}
    monkeypatch.setattr(weather, "fetch_citydata", lambda area, key: fake)
    out = weather.get_weather("경복궁", mock=False, api_key="k")
    assert out["temp_c"] == 23.4 and out["pm10_grade"] == "좋음"


def test_real_places_use_tourapi(monkeypatch):
    from seoulmate.tools import places

    monkeypatch.setattr(places, "fetch_places",
                        lambda key, t, kw, rows, district="": [{"name": f"p{t}", "address": "서울", "content_type_id": t}])
    out = places.list_places("all", mock=False, api_key="k")
    assert {p["category"] for p in out} == {"indoor", "outdoor"}


def test_places_rejects_bad_category(registry):
    assert registry.call("list_places", {"category": "moon"})["ok"] is False


def test_unsupported_area_rejected_without_api_call(monkeypatch):
    import pytest

    from seoulmate.clients import seoul

    with pytest.raises(LookupError, match="미지원"):
        seoul.fetch_citydata("덕수궁", "k")
    assert "광화문·덕수궁" in seoul.SUPPORTED_AREAS


def test_food_category_with_district(registry):
    out = registry.call("list_places", {"category": "food", "district": "종로구"})
    assert out["ok"] and out["data"] and all(p["category"] == "food" for p in out["data"])
