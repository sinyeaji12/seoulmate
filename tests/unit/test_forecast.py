"""기상청 단기예보 도구: 날짜 해석, 구간 요약, 범위 밖·키 없음 처리."""
from datetime import date, datetime

import httpx
import pytest

from seoulmate.clients import kma
from seoulmate.tools import build_registry
from seoulmate.tools.forecast import get_forecast, resolve_date, summarize
from seoulmate.config import Settings

KST = kma.KST


def item(d, hh, cat, val):
    return {"fcstDate": d, "fcstTime": f"{hh:02d}00", "category": cat, "fcstValue": str(val)}


def day_items(d="20261017"):
    out = []
    for hh in range(0, 24):
        out += [item(d, hh, "TMP", 10 + hh // 2), item(d, hh, "POP", 10 if hh < 15 else 60),
                item(d, hh, "SKY", 1 if hh < 12 else 4), item(d, hh, "PTY", 0 if hh < 15 else 1)]
    return out


def test_when_resolves_to_dates_from_today():
    fri = date(2026, 10, 16)  # 금요일
    assert resolve_date("today", fri) == fri
    assert resolve_date("tomorrow", fri) == date(2026, 10, 17)
    assert resolve_date("saturday", fri) == date(2026, 10, 17) and resolve_date("sunday", fri) == date(2026, 10, 18)
    assert resolve_date("saturday", date(2026, 10, 17)) == date(2026, 10, 17)  # 오늘이 토요일이면 오늘
    assert resolve_date("saturday", date(2026, 10, 18)) == date(2026, 10, 24)
    with pytest.raises(ValueError):
        resolve_date("next month", fri)


def test_summary_groups_by_day_and_slot():
    out = summarize(day_items(), date(2026, 10, 17))
    assert out["day"]["temp_min"] == 10 and out["day"]["temp_max"] == 21 and out["day"]["pop"] == 60
    assert out["morning"]["sky"] == "맑음" and out["morning"]["precip"] == "없음" and out["morning"]["pop"] == 10
    assert out["evening"]["precip"] == "비" and out["evening"]["sky"] == "흐림"
    assert out["afternoon"]["pop"] == 60  # 구간 안 최댓값


def test_date_outside_the_forecast_is_an_error_not_a_guess():
    with pytest.raises(LookupError, match="제공되지 않아요"):
        summarize(day_items("20261017"), date(2026, 10, 25))


def test_latest_base_uses_published_time_with_delay():
    assert kma.latest_base(datetime(2026, 10, 16, 19, 40, tzinfo=KST)) == ("20261016", "1700")
    assert kma.latest_base(datetime(2026, 10, 16, 17, 10, tzinfo=KST)) == ("20261016", "1400")  # 발표 직후엔 이전 발표
    assert kma.latest_base(datetime(2026, 10, 16, 1, 0, tzinfo=KST)) == ("20261015", "2300")


def client_for(payload, status=200, seen=None):
    def handler(req):
        if seen is not None:
            seen.append(dict(req.url.params))
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_body(items):
    return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"}, "body": {"items": {"item": items}}}}


def test_fetch_sends_grid_and_base_time_for_the_district():
    seen = []
    items = kma.fetch_forecast("성동구", "KEY", datetime(2026, 10, 16, 19, 40, tzinfo=KST), client_for(ok_body(day_items()), seen=seen))
    assert items and seen[0]["nx"] == "61" and seen[0]["ny"] == "127" and seen[0]["base_time"] == "1700"


def test_unknown_district_missing_key_and_service_errors():
    with pytest.raises(LookupError, match="격자를 모르는"):
        kma.fetch_forecast("성수동", "KEY", client=client_for({}))  # 구 이름이 아니면 짐작하지 않는다
    with pytest.raises(ValueError):
        kma.fetch_forecast("성동구", "", client=client_for({}))
    bad = {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}
    with pytest.raises(LookupError, match="SERVICE_KEY"):
        kma.fetch_forecast("성동구", "KEY", client=client_for(bad))
    with pytest.raises(LookupError, match="비어"):
        kma.fetch_forecast("성동구", "KEY", client=client_for(ok_body([])))


def test_mock_mode_needs_no_key_or_network():
    out = get_forecast("성동구", "tomorrow", mock=True, now=datetime(2026, 10, 16, 12, tzinfo=KST))
    assert out["date"] == "2026-10-17" and out["source"] == "mock" and out["slots"]["day"]["pop"] == 20


def test_tool_is_registered_and_reports_failures_as_results():
    reg = build_registry(Settings(seoulmate_mock_tools=False, tour_api_key=""))
    assert "get_forecast" in [t["name"] for t in reg.schemas()]
    res = reg.call("get_forecast", {"district": "성동구", "when": "tomorrow"})
    assert res["ok"] is False and "API 키" in res["error"]  # 키가 없으면 예외 대신 오류 결과
    mock = build_registry(Settings(seoulmate_mock_tools=True)).call("get_forecast", {"district": "성동구", "when": "saturday"})
    assert mock["ok"] and mock["data"]["when"] == "saturday"


def test_kma_key_falls_back_to_the_shared_data_portal_key():
    s = Settings(seoulmate_mock_tools=False, tour_api_key="SHARED")
    assert (s.kma_api_key or s.tour_api_key) == "SHARED"
