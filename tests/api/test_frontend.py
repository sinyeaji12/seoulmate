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


def test_map_and_schedule_are_linked_only_for_places_with_coordinates():
    assert "function select(i, opt = {})" in HTML
    assert "if (pos) {" in HTML and "li.classList.add('has-pos')" in HTML  # 좌표가 있는 장소만 선택 가능
    assert "row('위치', '정보 없음')" in HTML  # 좌표가 없으면 지어내지 않고 표시
    assert "m.on('click', () => select(p.n - 1, { scroll: true }))" in HTML  # 핀 → 일정으로 스크롤
    assert "map.setView([curStops[i].lat, curStops[i].lng]" in HTML  # 일정 → 지도 이동
    for state in (".step.sel .stop-btn", ".step.sel .rail::after", ".step.sel figure.ph", ".pin.on"):
        assert state in HTML, state
    assert re.search(r"\.pin\.on \{[^}]*var\(--olive\)", HTML)  # 선택은 올리브 + 굵은 링


def test_map_link_is_keyboard_and_reduced_motion_friendly():
    assert "button', 'stop-btn'" in HTML.replace('"', "'") or "el('button', 'stop-btn'" in HTML
    assert "aria-pressed" in HTML and "setAttribute('aria-label', `${p.n}번 ${p.s.place}`)" in HTML
    assert "e.key === 'Enter' || e.key === ' '" in HTML  # 핀에서 Enter·Space
    assert "e.key === 'Escape'" in HTML  # Esc로 선택 해제
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in HTML and "animate: !reduced()" in HTML
    assert "behavior = reduced() ? 'auto' : 'smooth'" in HTML
    assert re.search(r"@media \(prefers-reduced-motion:reduce\) \{[^}]*\.pin", HTML)


def test_mobile_can_hop_between_schedule_and_map_and_attribution_stays():
    assert re.search(r"\.m-only \{ display:none; \}\s*@media \(max-width:900px\) \{ \.m-only \{ display:inline-block; \} \}", HTML)
    assert "지도에서 보기" in HTML and 'id="to-list"' in HTML and "일정으로 돌아가기" in HTML
    assert "OpenStreetMap" in HTML and 'class="mapcap"' in HTML  # 기존 지도 출처 표기 유지


def test_today_in_seoul_is_hidden_until_real_data_arrives_and_is_a_magazine_toc():
    assert re.search(r'<section class="today" id="today"[^>]*\bhidden>', HTML)  # 기본은 숨김
    for text in ("Today in Seoul", "오늘의 서울", "지금 한산한 곳", "지금 붐비는 곳", "서울시 실시간 도시데이터"):
        assert text in HTML, text
    assert "fetch('/seoul-now')" in HTML and "if (d && d.ok) renderToday(d)" in HTML  # 실패·샘플 모드면 아무것도 보이지 않는다
    assert "if (!a && !b) return;" in HTML and "box.hidden = items.length === 0" in HTML  # 빈 쪽·빈 지면은 숨김
    assert "pad2(i + 1)" in HTML and "' 기준'" in HTML  # 번호 + 기준 시각
    rule = re.search(r"\.toc li \{([^}]*)\}", HTML).group(1)
    assert "border-bottom:1px solid var(--line)" in rule and "box-shadow" not in rule  # 얇은 구분선, 카드 아님


def test_today_places_are_appended_to_the_question_never_overwrite_it():
    assert "근처로 코스 짜기" in HTML and "function addToQuestion(name, row)" in HTML
    assert "q.value = next;" in HTML and r"`${cur}\n${line}`" in HTML  # 기존 내용 뒤에 줄을 이어 붙인다
    assert "if (!cur.includes(line))" in HTML  # 같은 문장은 중복해서 넣지 않는다
    assert "next.length > 480" in HTML  # 500자 제한을 넘지 않게
    assert re.search(r"\.toc-row\.added \.nm \{[^}]*var\(--olive\)", HTML)  # 담은 곳은 올리브


def test_today_lives_with_the_cover_and_hides_with_it_in_the_result_view():
    assert '<div id="front">' in HTML and "$('front').hidden = true" in HTML and "$('front').hidden = false" in HTML


def test_with_when_time_are_single_choice_rows_sent_with_the_question():
    for label in ("WITH", "WHEN", "TIME"):
        assert f'id="pk-{label.lower()}">{label}</span>' in HTML, label
    for opt in ("혼자", "친구와", "연인과", "가족과", "오늘", "내일", "주말", "오전", "오후", "저녁"):
        assert f'class="opt" aria-pressed="false">{opt}</button>' in HTML, opt
    assert HTML.count('class="opt"') == 10 and 'role="group" aria-labelledby="pk-' in HTML
    assert "const PICK_LABEL = { with: '함께', when: '언제', time: '시간대' }" in HTML
    assert "o.setAttribute('aria-pressed', 'false')" in HTML  # 한 줄에 하나만, 다시 누르면 해제
    rule = re.search(r"\.opt \{([^}]*)\}", HTML).group(1)
    assert "border:1px solid var(--line-strong)" in rule and "box-shadow" not in rule  # 얇은 선


def test_future_dates_never_pretend_to_have_a_forecast():
    assert "미래 날씨는 아직 확인할 수 없어요" in HTML and re.search(r'id="pick-note"[^>]*\bhidden>', HTML)
    assert "['내일', '주말'].includes(picked('when'))" in HTML
    assert "내일·주말 날씨는 단정하지 말고 지금 기준임을 밝혀 주세요" in HTML  # 모델에게도 알린다
    assert "slice(0, 500 - t.length)" in HTML  # 선택 문장이 500자 제한에 잘려 나가지 않는다


def test_vibe_keywords_come_only_from_evidence_in_the_response():
    assert re.search(r'<section class="vibe" id="vibe"[^>]*\bhidden>', HTML) and "오늘의 분위기" in HTML
    assert "$('vibe').hidden = vibe.length === 0" in HTML  # 근거가 없으면 영역째 숨김
    for kw in ("걷기 좋음", "한적함", "붐빔 주의", "실내 위주"):
        assert f"out.push('{kw}')" in HTML, kw
    assert "return out.slice(0, 3)" in HTML
    for invented in ("사진 많", "감성", "힙", "데이트"):  # 데이터가 없는 분위기는 만들지 않는다
        assert invented not in HTML.split("function vibeKeywords")[1].split("function showResult")[0], invented
    assert HTML.index('id="vibe"') < HTML.index('id="mates-note"')  # MATE'S NOTE 위
