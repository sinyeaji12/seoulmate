"""코스 완성 후 사진·장소 유형을 TourAPI 카탈로그에서 이름으로 채운다.

혼잡도(citydata) 이름과 TourAPI 이름이 달라 도구 결과만으로는 사진이 비는 장소가 많다.
카탈로그는 서울 전체를 한 번 받아 캐싱하므로 장소마다 API를 호출하지 않는다.
"""
import re
from collections.abc import Callable

from seoulmate.agent.schemas import Course
from seoulmate.clients.tour import fetch_places
from seoulmate.config import Settings

_CATEGORY = {"12": "outdoor", "14": "indoor", "39": "food"}
_SPACE_TYPES = {"12", "14"}  # 음식점이 아닌 장소는 관광지·문화시설에서만 찾는다


def fetch_catalog(api_key: str) -> list[dict]:
    out: list[dict] = []
    for t in ("12", "14", "39"):
        out += fetch_places(api_key, t, rows=1000)
    return out


def _keys(place: str) -> list[str]:
    base = re.sub(r"\([^)]*\)", "", place).strip()
    parts = [p.strip() for p in re.split(r"[·/]", base)]
    return [k for k in dict.fromkeys([base, *parts]) if len(k) >= 2]


def find_match(place: str, category: str, catalog: list[dict]) -> dict | None:
    want_food = category == "food"
    pool = [p for p in catalog if (p["content_type_id"] == "39") == want_food
            and (want_food or p["content_type_id"] in _SPACE_TYPES)]
    best: tuple[int, dict] | None = None
    for key in _keys(place):
        for p in pool:
            name = p["name"]
            if key not in name and name not in key:
                continue
            score = (0 if name == key else 1 if name.startswith(key) else 2 + abs(len(name) - len(key))) \
                + (0 if p.get("image") else 100)
            if best is None or score < best[0]:
                best = (score, p)
    return best[1] if best and best[0] < 100 else None  # 사진 있는 후보만 채택


def enrich_course(course: Course, catalog: list[dict]) -> Course:
    for s in course.stops:
        if s.image:
            continue
        m = find_match(s.place, s.category, catalog)
        if m:
            s.image = m["image"]
            s.category = s.category or _CATEGORY.get(m["content_type_id"], "")
    return course


def make_enricher(s: Settings) -> Callable[[Course], Course] | None:
    """실데이터 모드에서만 동작. 실패해도 코스 응답은 막지 않는다."""
    if s.seoulmate_mock_tools or not s.tour_api_key:
        return None

    def enrich(course: Course) -> Course:
        try:
            return enrich_course(course, fetch_catalog(s.tour_api_key))
        except Exception:  # noqa: BLE001 - 사진은 부가 정보
            return course

    return enrich
