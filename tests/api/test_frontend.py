"""정적 프론트엔드(index.html)가 매거진 디자인의 약속을 지키는지 확인한다."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from seoulmate.config import Settings
from seoulmate.web import app as webapp

STATIC = Path(__file__).parents[2] / "src" / "seoulmate" / "web" / "static"
HTML = (STATIC / "index.html").read_text("utf-8")


def test_palette_and_fonts():
    for token in ("#F5F3EE", "#242620", "#737B52"):
        assert token in HTML.upper(), token
    assert "Pretendard" in HTML and "Cormorant Garamond" in HTML  # 한글 고딕 + 얇은 세리프


def test_kitsch_style_fully_removed():
    for leftover in ("Black Han Sans", "Gowun Dodum", "B9D65A", "FF5FA2", "C6FF00", "capsule", "overlay", "gcard"):
        assert leftover.lower() not in HTML.lower(), leftover
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", HTML)  # 이모지 없음
    assert "카톡" not in HTML


def test_cover_path_is_managed_in_one_place_and_file_exists():
    assert HTML.count("cover.jpg") == 1 and "const COVER = {" in HTML
    assert (STATIC / "images" / "cover.jpg").is_file()
    assert "src: '/static/images/cover.jpg'" in HTML


def test_cover_copy_and_masthead_are_real_html_text():
    for text in ("오늘은,", "어떤 서울을 걸을까요?", "날씨와 붐빔을 살펴, 지금 당신에게 어울리는 코스를 찾아요.",
                 "어디서 출발하고, 어떤 시간을 보내고 싶나요?", "조용한 오후", "비 오는 날", "전시와 커피",
                 "아직 모르겠다면, 오늘의 산책지를 골라드릴까요?"):
        assert text in HTML, text
    assert '<small>SEOUL MATE</small><div class="big">SEOUL</div>' in HTML  # 사진 위 글자는 이미지가 아니라 텍스트
    assert "[COVER.place, COVER.season, COVER.credit].join(' · ')" in HTML  # "북촌 · 가을 · 사진 출처"


def test_top_menu_is_logo_plus_single_link():
    nav = re.search(r"<nav>(.*?)</nav>", HTML, re.S).group(1)
    assert nav.count("<a ") == 1 and "서비스 소개" in nav and 'href="#about"' in nav
    assert 'id="about"' in HTML


def test_selected_mood_is_olive_and_white_bold_16px():
    rule = re.search(r'\.mood\[aria-pressed="true"\]\s*\{([^}]*)\}', HTML).group(1)
    assert "var(--olive)" in rule and "#fff" in rule and "font-weight:700" in rule and "font-size:16px" in rule
    assert re.search(r"\.btn \{[^}]*background:var\(--olive\)[^}]*color:#fff[^}]*font-size:16px[^}]*font-weight:700", HTML)


def test_mood_choices_are_sent_with_the_question():
    assert "원하는 분위기:" in HTML and "stream('/chat', { message }" in HTML


def test_corners_are_small_and_buttons_are_not_pills():
    assert "--r:4px" in HTML
    assert not re.search(r"border-radius:\s*(9{2,}px|999|50px|100px)", HTML)


def test_motion_is_only_a_soft_fade():
    assert re.findall(r"@keyframes (\w+)", HTML) == ["fade"]
    assert "prefers-reduced-motion" in HTML and "setInterval" not in HTML  # 가짜 진행 표시 없음


def test_progress_is_two_gentle_sentences_not_a_list_of_tool_calls():
    for text in ("오늘의 서울을 천천히 살펴보고 있어요", "당신에게 맞는 골목을 찾고 있어요", "걷기 좋은 곳을 고르고 있어요"):
        assert text in HTML, text
    # 도구 호출을 하나하나 말하던 문장은 더 이상 없다
    for noisy in ("의 날씨를 확인했어요", "의 혼잡도를 살펴봤어요", "걸을 만한 곳을 찾아봤어요", "오늘 열리는 행사를 살펴봤어요",
                  "function stepText", "case 'get_weather'", "case 'get_crowd'"):
        assert noisy not in HTML, noisy
    assert "function makeProgress(list, [first, second])" in HTML
    assert "if (ev === 'tool') chatProgress.step(data)" in HTML  # 둘째 문장은 실제 첫 조회 결과 도착에 맞춰 나온다
    assert "if (advanced) return" in HTML and "i-check" in HTML  # 한 번만 넘어가고, 끝난 문장 앞에 얇은 체크


def test_result_note_sections_and_honest_placeholders():
    for text in ("Walking Note", "정보 없음", "다음 시간", "확인`", "운영시간", "다음 장소", "직선거리 기준", "한국관광공사"):
        assert text in HTML, text
    assert "나만의 서울 산책 노트" in HTML  # title 필드가 아직 없어 고정 제목


def test_never_requests_external_images_directly_and_never_uses_innerhtml():
    assert "/place-image?name=" in HTML and "visitkorea" not in HTML
    assert "innerHTML" not in HTML  # 서버 값은 textContent로만 넣는다


def test_map_uses_leaflet_with_sri_gray_tiles_and_attribution():
    assert HTML.count('integrity="sha512-') == 2  # CSS + JS 모두 무결성 검증
    assert "tile.openstreetmap.org" in HTML and "OpenStreetMap" in HTML and "contributors" in HTML
    assert re.search(r"\.leaflet-tile-pane\s*\{[^}]*grayscale", HTML)
    assert "#737B52" in HTML  # 경로·핀은 올리브
    assert "cartocdn" not in HTML  # CARTO는 API 키가 필요해 쓰지 않는다


def test_photos_get_one_shared_tone_filter():
    assert re.search(r"figure\.ph img \{[^}]*filter:saturate\([^)]*\) sepia\(", HTML)


def test_gacha_is_only_a_small_text_link_with_inline_result():
    assert 'id="gacha-link"' in HTML and "/gacha/stream" in HTML
    assert 'role="dialog"' not in HTML and 'aria-modal' not in HTML


def test_static_files_and_index_are_served():
    c = TestClient(webapp.create_app(Settings(seoulmate_mock_tools=True)))
    cover = c.get("/static/images/cover.jpg")
    assert cover.status_code == 200 and cover.headers["content-type"] == "image/jpeg"
    assert c.get("/static/images/missing.jpg").status_code == 404
    assert "서울 메이트" in c.get("/").text


def test_missing_photo_is_a_low_band_and_network_errors_are_korean():
    assert "figure.ph.empty" in HTML and "fig.classList.add('empty')" in HTML
    assert "서버에 연결하지 못했어요" in HTML  # 브라우저의 'Failed to fetch'를 그대로 보이지 않는다


def test_about_has_two_calm_items_and_sources_live_in_footer_and_map_caption():
    about = re.search(r'<section class="about".*?</section>', HTML, re.S).group(0)
    assert about.count("<li>") == 2 and "출처" not in about  # 소개는 서비스 이야기만
    footer = re.search(r"<footer.*?</footer>", HTML, re.S).group(0)
    assert "서울시 실시간 도시데이터" in footer and "한국관광공사" in footer and "정보 없음" in footer
    assert "OpenStreetMap" in HTML and "<p class=\"mapcap\">지도 ©" in HTML  # 지도 출처 표기는 지도 곁에 유지


def test_mates_note_shows_only_when_the_response_has_an_explanation():
    assert "Mate's Note" in HTML and 'id="mates-note"' in HTML and 'aria-label="이 코스를 고른 이유"' in HTML
    assert re.search(r'<section class="mates-note" id="mates-note"[^>]*\bhidden>', HTML)  # 기본은 숨김
    assert "$('mates-note').hidden = !why" in HTML and "(course.summary || '').trim()" in HTML
    # 장식 요소 없음: 따옴표 문자·카드 그림자·배경 박스를 쓰지 않는다
    rule = re.search(r"\.mates-note \{([^}]*)\}", HTML).group(1)
    assert "box-shadow" not in rule and "background" not in rule and "border-top:1px solid" in rule
    assert "“" not in HTML.split('id="mates-note"')[1].split("</section>")[0]
    assert 'class="lede"' not in HTML  # 예전 평범한 문단은 MATE'S NOTE로 대체됐다
