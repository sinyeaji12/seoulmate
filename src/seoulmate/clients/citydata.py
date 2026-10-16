"""서울 실시간 도시데이터 API 어댑터. 날씨·혼잡도가 같은 응답에 들어 있다."""
import httpx

BASE = "http://openapi.seoul.go.kr:8088"


def fetch_citydata(area: str, api_key: str, *, client: httpx.Client | None = None) -> dict:
    if not api_key:
        raise RuntimeError("SEOUL_API_KEY is not set")
    url = f"{BASE}/{api_key}/json/citydata/1/5/{area}"
    c = client or httpx.Client(timeout=15.0)
    resp = c.get(url)
    resp.raise_for_status()
    body = resp.json()
    city = body.get("CITYDATA")
    if not city:
        msg = body.get("RESULT", {}).get("RESULT.MESSAGE", "no data")
        raise LookupError(f"citydata unavailable for '{area}': {msg}")
    return city
