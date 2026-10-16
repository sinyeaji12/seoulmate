from datetime import datetime, timedelta, timezone

from seoulmate.clients.tour import fetch_festivals

KST = timezone(timedelta(hours=9))
_MOCK = [{"name": "서울 가을 야시장", "address": "서울 중구", "image": "",
          "start": "20261010", "end": "20261031"}]


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def list_festivals(*, mock: bool = True, api_key: str = "", today: str = "") -> list[dict]:
    """오늘 진행 중인 서울 행사. 기간(start<=오늘<=end)으로 걸러서 돌려준다."""
    today = today or today_kst()
    if mock:
        return [f for f in _MOCK if f["start"] <= today <= f["end"]]
    return [f for f in fetch_festivals(api_key, today) if f["start"] <= today <= f["end"]]
