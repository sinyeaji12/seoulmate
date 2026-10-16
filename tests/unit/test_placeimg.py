import httpx
import pytest

from seoulmate.clients.placeimg import ImageLookupError, PlaceImages, queries_for

IMG_URL = "http://tong.visitkorea.or.kr/cms/resource/04/a.jpg"
BYTES = b"\xff\xd8\xffJPEGDATA"


def item(title, ctype="12", image=IMG_URL, addr="서울특별시 종로구", areacode=""):
    return {"title": title, "contenttypeid": ctype, "firstimage": image, "addr1": addr, "areacode": areacode}


def make(items_by_query, *, search_status=200, image_status=200, ctype="image/jpg", image_url_host=None):
    """TourAPI 검색과 이미지 서버를 흉내 낸다. calls에 요청 URL을 쌓는다."""
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path.endswith("searchKeyword2"):
            if search_status != 200:
                return httpx.Response(search_status, text="err")
            items = items_by_query.get(req.url.params["keyword"], [])
            body = {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                 "body": {"items": {"item": items} if items else ""}}}
            return httpx.Response(200, json=body)
        return httpx.Response(image_status, content=BYTES, headers={"content-type": ctype})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PlaceImages("SECRETKEY123", client=client), calls


# ---- 이미지 있을 때 ----
def test_found_returns_image_bytes_over_https():
    pi, calls = make({"북촌한옥마을": [item("북촌한옥마을")]})
    data, ctype = pi.fetch("북촌한옥마을")
    assert data == BYTES and ctype == "image/jpeg"
    assert calls[-1].startswith("https://tong.visitkorea.or.kr/")  # http 주소도 https로 올려 요청


def test_prefers_exact_title_and_accepts_sub_area():
    items = [item("서울숲 곤충식물원", image="http://tong.visitkorea.or.kr/b.jpg"),
             item("서울숲", image="http://tong.visitkorea.or.kr/a.jpg")]
    pi, _ = make({"서울숲": items})
    assert pi.find_url("서울숲").endswith("a.jpg")
    pi2, _ = make({"서울숲": items[:1]})
    assert pi2.find_url("서울숲").endswith("b.jpg")


def test_uses_alias_queries_and_split_names():
    assert queries_for("광화문·덕수궁") == ["광화문·덕수궁", "광화문", "덕수궁"]
    pi, _ = make({"동대문디자인플라자": [item("동대문디자인플라자(DDP)")]})
    assert pi.find_url("DDP", ["동대문디자인플라자", "DDP"])


# ---- 이미지 없을 때 ----
def test_not_found_returns_none():
    pi, _ = make({})
    assert pi.fetch("경복궁") is None


def test_unrelated_or_non_attraction_results_are_rejected():
    items = [item("내맘대로폰케이스 홍대점"), item("홍대 맛집", ctype="39"), item("홍대 호텔", ctype="32"),
             item("홍대공원", image="")]
    pi, _ = make({"홍대": items})
    assert pi.fetch("홍대") is None


def test_non_image_response_is_none():
    pi, _ = make({"a장소": [item("a장소")]}, ctype="text/html")
    assert pi.fetch("a장소") is None


def test_image_from_untrusted_host_is_never_fetched():
    pi, calls = make({"악성": [item("악성", image="http://evil.example.com/x.jpg")]})
    assert pi.fetch("악성") is None
    assert not any("evil.example.com" in c for c in calls)


def test_empty_api_key_means_no_image_and_no_network():
    pi = PlaceImages("")
    assert pi.fetch("북촌한옥마을") is None


# ---- API 실패할 때 ----
def test_api_failure_raises_without_leaking_key():
    pi, _ = make({}, search_status=500)
    with pytest.raises(ImageLookupError) as e:
        pi.fetch("북촌한옥마을")
    assert "SECRETKEY123" not in str(e.value)


def test_image_server_failure_raises():
    pi, _ = make({"북촌한옥마을": [item("북촌한옥마을")]}, image_status=503)
    with pytest.raises(ImageLookupError):
        pi.fetch("북촌한옥마을")


# ---- 캐시 ----
def test_same_place_is_not_searched_again():
    pi, calls = make({"북촌한옥마을": [item("북촌한옥마을")]})
    pi.find_url("북촌한옥마을"); pi.find_url("북촌한옥마을")
    assert sum("searchKeyword2" in c for c in calls) == 1


def test_misses_are_cached_too_and_expire():
    t = [0.0]
    client_calls: list[str] = []

    def handler(req):
        client_calls.append(1)
        return httpx.Response(200, json={"response": {"header": {"resultCode": "0000"}, "body": {"items": ""}}})

    pi = PlaceImages("k", client=httpx.Client(transport=httpx.MockTransport(handler)), now=lambda: t[0])
    pi.find_url("경복궁"); pi.find_url("경복궁")
    assert len(client_calls) == 1  # 없는 장소도 다시 묻지 않는다
    t[0] += 3601
    pi.find_url("경복궁")
    assert len(client_calls) == 2


def test_failure_is_cached_briefly_to_avoid_hammering():
    t = [0.0]
    pi, calls = make({}, search_status=500)
    pi._now = lambda: t[0]
    for _ in range(3):
        with pytest.raises(ImageLookupError):
            pi.find_url("x장소")
    assert len(calls) == 1
    t[0] += 61
    with pytest.raises(ImageLookupError):
        pi.find_url("x장소")
    assert len(calls) == 2


# ---- 서울 판별 / 포함 일치 (사진이 안 나오던 원인: areaCode 필터가 areacode 빈 항목을 걸러냄) ----
def test_blank_areacode_but_seoul_address_is_accepted():
    pi, calls = make({"경복궁": [item("경복궁", areacode="", addr="서울특별시 종로구 사직로 161")]})
    assert pi.fetch("경복궁") is not None
    assert not any("areaCode" in c for c in calls)  # 지역 필터를 걸지 않는다


def test_same_title_in_another_city_is_rejected():
    pi, _ = make({"남산공원": [item("남산공원", addr="대구광역시 중구")]})
    assert pi.fetch("남산공원") is None


def test_seoul_named_place_outside_seoul_address_is_accepted():
    pi, _ = make({"서울대공원": [item("서울대공원", addr="경기도 과천시 대공원광장로 102")]})
    assert pi.fetch("서울대공원") is not None


def test_long_query_matches_inside_title_but_short_query_does_not():
    pi, _ = make({"롯데월드몰": [item("롯데월드타워&롯데월드몰")], "홍대": [item("내맘대로폰케이스 홍대점")]})
    assert pi.find_url("잠실 롯데월드몰", ["롯데월드몰"])
    assert pi.find_url("홍대 골목", ["홍대"]) is None


def test_restaurant_photo_only_for_exact_name():
    shop = [item("토속촌 삼계탕", ctype="39"), item("서촌돌솥", ctype="39")]
    pi, _ = make({"토속촌 삼계탕": shop, "서촌": shop})
    assert pi.find_url("토속촌 삼계탕")            # 식당 이름이 같으면 그 식당 사진
    assert pi.find_url("서촌") is None             # 동네 이름으로 이웃 식당 사진을 빌리지 않는다
