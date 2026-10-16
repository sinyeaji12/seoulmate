import json
from pathlib import Path

from seoulmate.clients.tour import fetch_places

_STATIC = json.loads((Path(__file__).parent.parent / "data" / "places.json").read_text("utf-8"))
# TourAPI 콘텐츠 타입: 12 관광지(야외 위주), 14 문화시설(실내 위주), 39 음식점
_TYPES = {"outdoor": ["12"], "indoor": ["14"], "food": ["39"], "all": ["12", "14"]}
_CATEGORY = {"12": "outdoor", "14": "indoor", "39": "food"}


def list_places(category: str = "all", keyword: str = "", district: str = "", *, mock: bool = True,
                api_key: str = "") -> list[dict]:
    if category not in _TYPES:
        raise ValueError("category must be indoor, outdoor, food or all")
    if mock:
        return [p for p in _STATIC if category == "all" and p["category"] != "food"
                or p["category"] == category and (not district or p.get("district", district) == district)]
    out: list[dict] = []
    for t in _TYPES[category]:
        for p in fetch_places(api_key, t, keyword, rows=10, district=district):
            out.append({**p, "category": _CATEGORY[t]})
    return out
