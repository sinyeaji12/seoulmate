"""기상청 단기예보 어댑터(공공데이터포털 VilageFcstInfoService_2.0). 예보는 오늘부터 며칠 뒤까지만 있다."""
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = timezone(timedelta(hours=9))
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)  # 발표 시각. 자료는 발표 약 10분 뒤부터 조회된다

# 서울 25개 구의 기상청 예보 격자(nx, ny). 구 이름이 아니면 격자를 짐작하지 않고 오류로 돌려보낸다.
GRIDS: dict[str, tuple[int, int]] = {
    "종로구": (60, 127), "중구": (60, 127), "용산구": (60, 126), "성동구": (61, 127), "광진구": (62, 126),
    "동대문구": (61, 127), "중랑구": (62, 128), "성북구": (61, 127), "강북구": (61, 128), "도봉구": (61, 129),
    "노원구": (61, 129), "은평구": (59, 127), "서대문구": (59, 127), "마포구": (59, 127), "양천구": (58, 126),
    "강서구": (58, 126), "구로구": (58, 125), "금천구": (59, 124), "영등포구": (58, 126), "동작구": (59, 125),
    "관악구": (59, 125), "서초구": (61, 125), "강남구": (61, 126), "송파구": (62, 126), "강동구": (62, 126),
}


def latest_base(now: datetime) -> tuple[str, str]:
    """지금 조회할 수 있는 가장 최근 발표의 (base_date, base_time). 발표 15분 뒤부터 쓴다."""
    t = now.astimezone(KST) - timedelta(minutes=15)
    hours = [h for h in BASE_HOURS if h <= t.hour]
    if not hours:  # 새벽 02:15 이전에는 어제 23시 발표
        t, hour = t - timedelta(days=1), BASE_HOURS[-1]
    else:
        hour = hours[-1]
    return t.strftime("%Y%m%d"), f"{hour:02d}00"


def fetch_forecast(district: str, api_key: str, now: datetime | None = None,
                   client: httpx.Client | None = None) -> list[dict]:
    if not api_key:
        raise ValueError("공공데이터포털 API 키가 설정되지 않았어요")
    if district not in GRIDS:
        raise LookupError(f"'{district}'은(는) 예보 격자를 모르는 지역. 서울 구 이름으로 다시: " + ", ".join(GRIDS))
    nx, ny = GRIDS[district]
    base_date, base_time = latest_base(now or datetime.now(KST))
    params = {"serviceKey": api_key, "pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
              "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny}
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(BASE, params=params)
        resp.raise_for_status()
        body = resp.json()
    finally:
        if owns:
            client.close()
    header = body.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        raise LookupError(f"기상청 예보를 받지 못했어요: {header.get('resultMsg', 'unexpected response')}")
    items = body["response"]["body"].get("items", {}).get("item", [])
    if not items:
        raise LookupError("기상청 예보 값이 비어 있어요")
    return items
