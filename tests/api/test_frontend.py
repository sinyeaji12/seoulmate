"""정적 프론트엔드(index.html)의 약속을 지키는지 확인한다: 가챠는 작은 카드 + 팝업, 금지 문구 없음, 클래스 이름 충돌 방지."""
import re
from pathlib import Path

HTML = (Path(__file__).parents[2] / "src" / "seoulmate" / "web" / "static" / "index.html").read_text("utf-8")


def test_gacha_is_small_card_message_plus_popup_not_big_section():
    assert 'class="gacha"' not in HTML and "<section" not in HTML  # 큰 가챠 섹션 없음
    assert 'id="overlay"' in HTML and 'role="dialog"' in HTML and 'aria-modal="true"' in HTML
    assert "gachaCard()" in HTML and "'🎰 서울 가챠'" in HTML and "'뽑기'" in HTML


def test_gacha_copy_and_buttons():
    for text in ("오늘의 서울, 운명에 맡겨 볼래?", "뽑는 중…", "한 번 더 🔄", "이걸로 코스 짜줘", "닫기",
                 "서울 하늘 보는 중… ☁️", "사람 얼마나 있는지 보는 중… 👥", "두구두구… 🥁",
                 "지금이 딱이야 🧡", "가볼 만해 👍", "무난해 🙂", "사진: 한국관광공사"):
        assert text in HTML, text


def test_banned_wording_and_design_leftovers_absent():
    assert "카톡" not in HTML
    assert "Pretendard" not in HTML and "FE9C00" not in HTML.upper()  # 처음 디자인 규칙(라임 키치)
    assert "Black Han Sans" in HTML and "Gowun Dodum" in HTML
    assert "C6FF00" not in HTML.upper() and "B9D65A" in HTML.upper()


def test_popup_state_classes_do_not_collide():
    """팝업 열림(on)과 캡슐 뚜껑(lid)은 서로 다른 클래스여야 한다. 같은 이름이면 흔드는 동안 뚜껑이 열려 보인다."""
    assert ".overlay.on" in HTML and ".lid .top" in HTML
    assert not re.search(r"\.open\s+\.top", HTML)  # 뚜껑 규칙이 .open 후손 선택자가 아니어야 한다
    assert "$('overlay').classList.add('on')" in HTML and "cls('lid')" in HTML
    assert "mbtn cta" not in HTML and ".mbtn.cta" in HTML  # 기존 button.primary 스타일과 겹치지 않게


def test_reduced_motion_and_mobile_bottom_sheet_rules_exist():
    assert "prefers-reduced-motion" in HTML and "matchMedia('(prefers-reduced-motion: reduce)')" in HTML
    assert re.search(r"@media \(max-width:560px\)\s*\{[^}]*\.overlay\s*\{[^}]*align-items:flex-end", HTML)
    assert "height:100%" in HTML.split("@keyframes sheet")[0].split(".dialog {")[-1]


def test_frontend_never_requests_external_images_directly():
    assert "/place-image?name=" in HTML and "visitkorea" not in HTML
