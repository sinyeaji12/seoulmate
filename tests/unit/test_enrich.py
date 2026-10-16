from seoulmate.agent.enrich import enrich_course, find_match, make_enricher
from seoulmate.agent.schemas import Course, Stop
from seoulmate.config import Settings

CAT = [
    {"name": "덕수궁 대한문", "content_type_id": "12", "image": "http://img/daehan.jpg"},
    {"name": "북촌한옥마을", "content_type_id": "12", "image": "http://img/bukchon.jpg"},
    {"name": "아키비스트 서촌", "content_type_id": "39", "image": "http://img/cafe.jpg"},
    {"name": "남산골공원", "content_type_id": "12", "image": ""},
    {"name": "인사동찻집", "content_type_id": "39", "image": "http://img/tea.jpg"},
]


def stop(place, category="", image=""):
    return Stop(time="10:00", place=place, reason="r", category=category, image=image)


def test_exact_and_split_name_match():
    assert find_match("북촌한옥마을", "", CAT)["image"] == "http://img/bukchon.jpg"
    assert find_match("광화문·덕수궁", "", CAT)["image"] == "http://img/daehan.jpg"


def test_neighborhood_does_not_borrow_a_cafe_photo():
    assert find_match("서촌", "", CAT) is None  # 음식점은 장소 후보에서 제외


def test_food_matches_only_restaurants():
    assert find_match("인사동찻집", "food", CAT)["image"] == "http://img/tea.jpg"
    assert find_match("북촌한옥마을", "food", CAT) is None


def test_candidate_without_photo_is_ignored():
    assert find_match("남산골공원", "", CAT) is None


def test_enrich_fills_image_and_category_but_keeps_existing():
    c = Course(summary="s", stops=[stop("북촌한옥마을"), stop("덕수궁 대한문", image="http://keep/x.jpg")])
    enrich_course(c, CAT)
    assert (c.stops[0].image, c.stops[0].category) == ("http://img/bukchon.jpg", "outdoor")
    assert c.stops[1].image == "http://keep/x.jpg"


def test_enricher_off_in_mock_mode():
    assert make_enricher(Settings(seoulmate_mock_tools=True, tour_api_key="k")) is None
    assert make_enricher(Settings(seoulmate_mock_tools=False, tour_api_key="")) is None


def test_enricher_failure_does_not_break_course(monkeypatch):
    from seoulmate.agent import enrich as mod

    monkeypatch.setattr(mod, "fetch_catalog", lambda key: (_ for _ in ()).throw(RuntimeError("quota")))
    c = Course(summary="s", stops=[stop("북촌한옥마을")])
    out = make_enricher(Settings(seoulmate_mock_tools=False, tour_api_key="k"))(c)
    assert out.stops[0].image == ""
