"""FR-1092: the floorplan viewer in a real browser, served on this repository's own source and its floorplan/architecture.json."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sync_api = pytest.importorskip("playwright.sync_api")

CARD = '[data-testid="fp-card"]'


@pytest.fixture(scope="module")
def studio(request):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(REPO), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 20
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield request.getfixturevalue("shared_browser"), f"http://127.0.0.1:{port}"
    proc.terminate()


def _open(studio, query="", lang="en", reduced=False):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1500, "height": 900}, reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    page.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    page.goto(f"{url}/#/floorplan?tour=0{query}")
    page.wait_for_selector(CARD, timeout=90000)
    return page


def _state(page):
    return page.evaluate("() => window.eabkView.getState()")


def _card(page, key):
    return page.locator(f'{CARD}[data-id="{key}"]')


# FR-1092 AC-510: the overview shows parts and outside services; double-click goes inside, where three columns and pills appear; back, breadcrumb, URL and history follow.
def test_ac510_overview_inside_brackets_and_history(studio):
    page = _open(studio)
    top = _state(page)
    assert top["view"] == "" and top["cards"] >= 8 and page.locator(".fp-line").count() >= 3
    assert page.locator(f'{CARD}[data-type="node"]').count() >= 8
    _card(page, "n:server").dblclick()
    page.wait_for_function("() => window.eabkView.getState().view === 'n:server'")
    labels = page.locator(".fp-bracket").all_inner_texts()
    assert any("Used by" in x for x in labels) and any("Inside Studio server" in x for x in labels) and any("Uses" in x for x in labels)
    assert page.locator(f"{CARD}.pill").count() >= 1 and "v=n%3Aserver" in page.url
    page.go_back()
    page.wait_for_function("() => window.eabkView.getState().view === ''")
    page.go_forward()
    page.wait_for_function("() => window.eabkView.getState().view === 'n:server'")
    page.locator('[data-testid="fp-back"]').click()
    page.wait_for_function("() => window.eabkView.getState().view === ''")
    page.context.close()


# FR-1092 AC-510: the path at the top says where you are (codebase › part › … › folder › file › selected item), each step goes back, the last one is the current place.
def test_ac510_path_shows_the_position_in_the_structure(studio):
    page = _open(studio, "&v=f%3AHVE-Studio%2Fstudio.py")
    page.wait_for_function("() => window.eabkView.getState().view === 'f:HVE-Studio/studio.py'")
    crumbs = page.locator('[data-testid="fp-crumbs"] [data-testid="fp-crumb"]')
    texts = crumbs.all_inner_texts()
    assert texts[0].startswith("Codebase") and texts[1].startswith("Part") and texts[-1].startswith("File") and len(texts) >= 3
    assert crumbs.last.get_attribute("aria-current") == "location" and crumbs.first.get_attribute("aria-current") is None
    page.locator(f'{CARD}[data-type="route"]').first.click()
    assert page.locator('[data-testid="fp-crumbs"] [aria-current="location"]').inner_text().startswith("Endpoint")
    crumbs.nth(1).click()
    page.wait_for_function("() => window.eabkView.getState().view.startsWith('n:')")
    assert page.locator('[data-testid="fp-crumbs"] [aria-current="location"]').inner_text().split("\n")[0] in ("Part", "Folder")
    page.locator('[data-testid="fp-crumbs"] [data-testid="fp-crumb"]').first.click()
    page.wait_for_function("() => window.eabkView.getState().view === ''")
    page.wait_for_function("() => document.querySelectorAll('[data-testid=fp-crumbs] [data-testid=fp-crumb]').length === 1")
    page.context.close()


# FR-1092 AC-510: files hold endpoints and functions; a shared link opens the place; Backspace, F, / and Esc work; the right-click menu and semantic zoom.
def test_ac510_file_view_keyboard_menu_and_semantic_zoom(studio):
    page = _open(studio, "&v=f%3AHVE-Studio%2Fstudio.py")
    page.wait_for_function("() => window.eabkView.getState().view === 'f:HVE-Studio/studio.py'")
    assert page.locator(f'{CARD}[data-type="route"]').count() >= 5 and page.locator(f'{CARD}[data-type="symbol"]').count() >= 3
    route = page.locator(f'{CARD}[data-type="route"]').first
    assert route.locator(".fp-route").inner_text().startswith(("GET", "POST"))
    route.click(button="right")
    assert page.locator('[data-testid="fp-menu"] button').count() >= 3
    page.keyboard.press("Escape")
    page.locator('[data-testid="fp-stage"]').focus()
    page.keyboard.press("Backspace")
    page.wait_for_function("() => window.eabkView.getState().view === 'n:server'")
    page.keyboard.press("f")
    page.keyboard.press("/")
    assert page.evaluate("() => document.activeElement?.dataset.testid") == "fp-search"
    page.keyboard.press("Escape")
    page.locator('[data-testid="fp-stage"]').focus()
    for _ in range(14):
        page.keyboard.press("-")
    assert page.locator(".fp-world").get_attribute("data-zoom") == "far"
    assert not page.locator(f"{CARD} .fp-desc").first.is_visible()
    page.context.close()


# FR-1092 AC-511: details panel, filters and technical names; Health shows what was checked and keeps "Not a problem" after a reload; Recent work and Screens open answer boards.
def test_ac511_panel_health_recent_screens_and_filters(studio):
    page = _open(studio)
    _card(page, "n:server").click()
    assert page.locator('[data-testid="fp-name"]').inner_text() == "Studio server" and page.locator(".fp-line.hot").count() >= 1 and page.locator(f"{CARD}.dim").count() >= 1
    assert page.locator('[data-testid="fp-link"]').count() >= 2
    page.locator('[data-testid="fp-filters"]').click()
    page.locator('[data-testid="fp-technical"]').check()
    page.wait_for_function("() => document.querySelector('[data-testid=fp-name]').textContent === 'server'")
    page.locator('[data-testid="fp-technical"]').uncheck()
    page.locator('[data-testid="fp-health"]').click()
    assert page.locator('[data-testid="fp-h-checked"]').inner_text().strip() and page.locator('[data-testid="fp-issue"]').count() >= 1
    page.locator('[data-testid="fp-h-not"]').first.click()
    n_done = page.locator(".fp-issue.done").count()
    assert n_done >= 1
    page.reload()
    page.wait_for_selector(CARD)
    page.locator('[data-testid="fp-health"]').click()
    assert page.locator(".fp-issue.done").count() >= n_done                  # kept across reloads
    page.locator('[data-testid="fp-h-again"]').first.click()
    page.locator('[data-testid="fp-h-show"]').first.click()
    page.wait_for_function("() => window.eabkView.getState().cards > 0")
    page.locator('[data-testid="fp-recent"]').click()
    assert page.locator('[data-testid="fp-recent-modal"]').is_visible()
    page.locator('[data-testid="fp-recent-modal"] [data-testid="fp-show-recent"]').first.click()
    page.wait_for_function("() => window.eabkView.getState().answer === true")
    page.locator('[data-testid="fp-back-map"]').click()
    page.locator('[data-testid="fp-screens"]').click()
    assert page.locator('[data-testid="fp-screen"]').count() >= 5
    page.locator('[data-testid="fp-screen"]', has_text="Floorplan").first.click()
    page.wait_for_function("() => window.eabkView.getState().answer === true && window.eabkView.getState().cards >= 3")
    page.context.close()


# FR-1092 AC-511: Flows and Start here step through the map with a narration; the written flow comes from architecture.json.
def test_ac511_flows_and_tour(studio):
    page = _open(studio)
    page.locator('[data-testid="fp-flows"]').click()
    page.locator('[data-testid="fp-flow"]', has_text="Opening the code floorplan").click()
    page.wait_for_selector('[data-testid="fp-flowbar"]')
    assert "1 / 4" in page.locator('[data-testid="fp-flowbar"]').inner_text()
    page.locator('[data-testid="fp-flow-next"]').click()
    page.wait_for_function("() => window.eabkView.getState().flow === 1")
    page.keyboard.press("ArrowRight")
    page.wait_for_function("() => window.eabkView.getState().flow === 2")
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.eabkView.getState().flow === null")
    page.locator('[data-testid="fp-tour"]').click()
    assert "1 / 5" in page.locator('[data-testid="fp-flowbar"]').inner_text()
    page.context.close()


# FR-1092 AC-512: the question box follows the lines of the map between two things, in order, and says so when there is no path or no match; Japanese works.
def test_ac512_ask_the_map_and_japanese(studio):
    page = _open(studio)
    page.locator('[data-testid="fp-ask"]').fill("Studio server to Git history")
    page.locator('[data-testid="fp-ask"]').press("Enter")
    page.wait_for_function("() => window.eabkView.getState().answer === true")
    assert page.locator(".fp-steps li").count() >= 2 and page.locator(".fp-step").count() >= 2
    page.locator('[data-testid="fp-back-map"]').click()
    page.locator('[data-testid="fp-ask"]').fill("zzzqqq nothing")
    page.locator('[data-testid="fp-ask"]').press("Enter")
    page.wait_for_function("() => window.eabkView.getState().answer === true")
    page.locator('[data-testid="fp-side"]', has_text="Nothing matched").wait_for()
    page.context.close()
    ja = _open(studio, lang="ja")
    assert "健康診断" in ja.locator('[data-testid="fp-health"]').inner_text() and "フロー" in ja.locator('[data-testid="fp-flows"]').inner_text()
    ja.context.close()


# FR-1092 AC-512: with reduced motion nothing flows along the selected lines.
def test_ac512_reduced_motion_has_no_flow_animation(studio):
    page = _open(studio, reduced=True)
    _card(page, "n:server").click()
    page.wait_for_timeout(400)
    assert page.locator(".fp-line.hot").count() >= 1
    assert page.locator(".fp-line.hot .fp-edge").first.get_attribute("stroke-dashoffset") is None
    page.context.close()
