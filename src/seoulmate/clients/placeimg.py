"""장소 대표 이미지 조회: 한국관광공사 TourAPI(searchKeyword2)의 firstimage를 이름으로 찾아 백엔드가 대신 내려준다.

프론트가 외부 이미지를 직접 요청하지 않게 하는 이유: (1) TourAPI 이미지는 http 주소라 https 사이트에서 막힐 수 있고,
(2) 나중에 이미지 저장(canvas) 기능에서 CORS 오염이 생기지 않게 같은 출처로 내려주기 위해서다.
같은 장소는 이름별로 캐시해 다시 조회하지 않는다. 이름이 비슷할 뿐 다른 장소의 사진을 붙이는 것보다 사진 없음이 낫다.
"""
import re
import time

import httpx

from seoulmate.clients.tour import BASE

IMAGE_HOST = "visitkorea.or.kr"  # 이 도메인(과 하위 도메인)의 https 이미지만 내려준다(SSRF 방지)
ALLOWED_TYPES = {"12", "14"}  # 관광지·문화시설은 시작/포함 일치도 허용
EXACT_ONLY_TYPES = {"39", "38", "32", "28", "15"}  # 음식점·쇼핑·숙박·레포츠·행사는 이름이 정확히 같을 때만(식당 이름 장소용)
MAX_BYTES = 5_000_000
HIT_TTL, MISS_TTL, FAIL_TTL = 86400.0, 3600.0, 60.0


class ImageLookupError(Exception):
    """TourAPI/이미지 서버 조회 실패. 메시지에 URL·키를 담지 않는다."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def queries_for(name: str) -> list[str]:
    """'광화문·덕수궁' → ['광화문·덕수궁', '광화문', '덕수궁'], 괄호 설명은 뺀다."""
    base = re.sub(r"\([^)]*\)", "", name).strip()
    parts = [p.strip() for p in re.split(r"[·/]", base)]
    return [q for q in dict.fromkeys([base, *parts]) if len(q) >= 2]


def _in_seoul(item: dict) -> bool:
    """TourAPI는 경복궁·청계천처럼 areacode가 빈 항목이 많아 지역 필터로는 걸러진다 → 주소로 서울을 확인한다."""
    title = item.get("title", "")
    return "서울" in item.get("addr1", "") or item.get("areacode") == "1" or title.startswith("서울")


def _pick(items: list[dict], query: str) -> str | None:
    """사진이 있는 서울의 관광지·문화시설 중 제목이 검색어와 같거나 검색어로 시작하는 것을 채택(정확한 순).
    검색어가 4자 이상이면 제목에 포함된 것도 받는다(예: '롯데월드몰' → '롯데월드타워&롯데월드몰'). 그보다 짧은 이름은
    엉뚱한 상점('홍대' → '○○폰케이스 홍대점')이 걸리지 않게 시작 일치만 허용한다."""
    q = _norm(query)
    best: tuple[int, str] | None = None
    for i in items:
        t = _norm(i.get("title", ""))
        img = i.get("firstimage", "")
        ctype = i.get("contenttypeid")
        if not img or not _in_seoul(i) or ctype not in ALLOWED_TYPES | EXACT_ONLY_TYPES:
            continue
        if ctype in EXACT_ONLY_TYPES:
            if t != q:  # '서촌' → '서촌돌솥' 같은 이웃 가게 사진을 장소 사진으로 쓰지 않는다
                continue
            score = 50
        elif t.startswith(q):
            score = len(t) - len(q)  # 0이면 정확히 일치
        elif len(q) >= 4 and q in t:
            score = 100 + len(t) - len(q)
        else:
            continue
        if best is None or score < best[0]:
            best = (score, img)
    return best[1] if best else None


class PlaceImages:
    def __init__(self, api_key: str, *, client: httpx.Client | None = None, now=time.monotonic):
        self.api_key = api_key
        self._client = client
        self._now = now
        self._cache: dict[str, tuple[float, str | None, bool]] = {}  # 이름 → (만료, 이미지 URL, 실패 여부)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=10.0)
        return self._client

    def _search(self, keyword: str) -> list[dict]:
        params = {"serviceKey": self.api_key, "MobileOS": "ETC", "MobileApp": "seoulmate", "_type": "json",
                  "keyword": keyword, "numOfRows": 50, "pageNo": 1}  # areaCode 필터는 쓰지 않는다(_in_seoul 참고)
        try:
            resp = self._http().get(f"{BASE}/searchKeyword2", params=params)
            resp.raise_for_status()
            body = resp.json()["response"]
            if body["header"]["resultCode"] != "0000":
                raise ImageLookupError("tourapi error")
            return (body["body"].get("items") or {}).get("item", [])
        except ImageLookupError:
            raise
        except Exception as e:  # noqa: BLE001 - 원문에 요청 URL(키)이 섞일 수 있어 종류만 남긴다
            raise ImageLookupError(f"tourapi request failed: {type(e).__name__}") from None

    def find_url(self, name: str, queries: list[str] | None = None) -> str | None:
        """이름으로 대표 이미지 URL을 찾는다. 없으면 None, API 실패면 ImageLookupError. 결과는 캐시한다."""
        hit = self._cache.get(name)
        if hit and self._now() < hit[0]:
            if hit[2]:
                raise ImageLookupError("recent failure")
            return hit[1]
        try:
            url = None
            for q in queries or queries_for(name):
                url = _pick(self._search(q), q)
                if url:
                    break
        except ImageLookupError:
            self._cache[name] = (self._now() + FAIL_TTL, None, True)
            raise
        self._cache[name] = (self._now() + (HIT_TTL if url else MISS_TTL), url, False)
        return url

    def fetch(self, name: str, queries: list[str] | None = None) -> tuple[bytes, str] | None:
        """(이미지 바이트, content-type) 또는 None(사진 없음/키 없음). API 실패는 ImageLookupError."""
        if not self.api_key:
            return None
        url = self.find_url(name, queries)
        if not url:
            return None
        url = re.sub(r"^http://", "https://", url)
        host = httpx.URL(url).host
        if not (host == IMAGE_HOST or host.endswith("." + IMAGE_HOST)):
            return None
        try:
            resp = self._http().get(url)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise ImageLookupError(f"image request failed: {type(e).__name__}") from None
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if not ctype.startswith("image/") or len(resp.content) > MAX_BYTES:
            return None
        return resp.content, "image/jpeg" if ctype == "image/jpg" else ctype
