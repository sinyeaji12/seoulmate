"""한국관광공사 국문 관광정보(KorService2) 어댑터. 개발계정은 호출 한도가 작아 짧게 캐싱한다."""
import time

import httpx

BASE = "https://apis.data.go.kr/B551011/KorService2"
SEOUL_AREA = "1"
# 서울 25개 구 sigunguCode (areaCode=1)
DISTRICTS = {"강남구": 1, "강동구": 2, "강북구": 3, "강서구": 4, "관악구": 5, "광진구": 6, "구로구": 7,
             "금천구": 8, "노원구": 9, "도봉구": 10, "동대문구": 11, "동작구": 12, "마포구": 13,
             "서대문구": 14, "서초구": 15, "성동구": 16, "성북구": 17, "송파구": 18, "양천구": 19,
             "영등포구": 20, "용산구": 21, "은평구": 22, "종로구": 23, "중구": 24, "중랑구": 25}
TTL_SECONDS = 600
_cache: dict[tuple, tuple[float, list[dict]]] = {}


def _coord(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_places(api_key: str, content_type_id: str, keyword: str = "", rows: int = 15,
                 district: str = "", client: httpx.Client | None = None) -> list[dict]:
    if not api_key:
        raise ValueError("TOUR_API_KEY is not set")
    key = (content_type_id, keyword, rows, district)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        return hit[1]
    params = {"serviceKey": api_key, "MobileOS": "ETC", "MobileApp": "seoulmate", "_type": "json",
              "areaCode": SEOUL_AREA, "contentTypeId": content_type_id, "numOfRows": rows, "pageNo": 1}
    if district:
        if district not in DISTRICTS:
            raise ValueError(f"unknown district: {district}")
        params["sigunguCode"] = DISTRICTS[district]
    endpoint = "areaBasedList2"
    if keyword:
        endpoint, params["keyword"] = "searchKeyword2", keyword
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(f"{BASE}/{endpoint}", params=params)
        resp.raise_for_status()
        body = resp.json()["response"]
    finally:
        if owns:
            client.close()
    if body["header"]["resultCode"] != "0000":
        raise LookupError(f"tourapi error: {body['header']['resultMsg']}")
    items = (body["body"].get("items") or {}).get("item", [])
    places = [{"name": i["title"], "address": i["addr1"], "content_type_id": i["contenttypeid"],
               "image": i.get("firstimage", ""),
               "lat": _coord(i.get("mapy")), "lng": _coord(i.get("mapx"))}
              for i in items]
    _cache[key] = (time.monotonic(), places)
    return places


def fetch_festivals(api_key: str, today: str, client: httpx.Client | None = None) -> list[dict]:
    """eventStartDate 이후에 끝나는 행사까지 내려오므로 기간 필터는 호출 측에서 한다."""
    if not api_key:
        raise ValueError("TOUR_API_KEY is not set")
    key = ("festival", today)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        return hit[1]
    params = {"serviceKey": api_key, "MobileOS": "ETC", "MobileApp": "seoulmate", "_type": "json",
              "areaCode": SEOUL_AREA, "eventStartDate": today, "numOfRows": 100, "pageNo": 1}
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(f"{BASE}/searchFestival2", params=params)
        resp.raise_for_status()
        body = resp.json()["response"]
    finally:
        if owns:
            client.close()
    if body["header"]["resultCode"] != "0000":
        raise LookupError(f"tourapi error: {body['header']['resultMsg']}")
    items = (body["body"].get("items") or {}).get("item", [])
    events = [{"name": i["title"], "address": i["addr1"], "image": i.get("firstimage", ""),
               "start": i["eventstartdate"], "end": i["eventenddate"]} for i in items]
    _cache[key] = (time.monotonic(), events)
    return events
