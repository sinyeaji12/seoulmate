"""서울 실시간 도시데이터(citydata) 어댑터. 날씨·혼잡도가 같은 엔드포인트에서 나온다."""
import json
from pathlib import Path

import httpx

BASE = "http://openapi.seoul.go.kr:8088"
# citydata가 실제로 응답하는 지역명(호출로 검증). TourAPI 장소명과 다를 수 있다.
SUPPORTED_AREAS: list[str] = json.loads(
    (Path(__file__).parent.parent / "data" / "realtime_areas.json").read_text("utf-8")
)


def fetch_citydata(area: str, api_key: str, client: httpx.Client | None = None) -> dict:
    if not api_key:
        raise ValueError("SEOUL_API_KEY is not set")
    if area not in SUPPORTED_AREAS:
        raise LookupError(
            f"'{area}'은(는) 실시간 데이터 미지원 장소. 가까운 지원 장소명을 쓰거나 확인 불가로 안내: "
            + ", ".join(SUPPORTED_AREAS)
        )
    url = f"{BASE}/{api_key}/json/citydata/1/5/{area}"
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        body = resp.json()
    finally:
        if owns:
            client.close()
    if "CITYDATA" not in body:
        msg = body.get("RESULT", {}).get("RESULT.MESSAGE", "unexpected response")
        raise LookupError(f"citydata unavailable for '{area}': {msg}")
    return body["CITYDATA"]
