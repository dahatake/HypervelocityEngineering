"""FR-1091: the code relations screen (#/codegraph) in a real browser, served on this repository's own source."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sync_api = pytest.importorskip("playwright.sync_api")

CANVAS = '[data-testid="cg-canvas"]'
FP_CARD = '[data-testid="fp-card"]'
UI_EL = "HVE-Studio/web/js/ui.js::el"


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


def _open(studio, query="", reduced=False, lang="ja"):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    page.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    page.goto(f"{url}/#/codegraph{query}")
    page.wait_for_selector(CANVAS, timeout=60000)
    page.wait_for_function("() => window.eabkView?.getState().nodes > 0", timeout=60000)
    return page


def _settled(page):
    page.wait_for_function("() => document.querySelector('[data-testid=cg-canvas]')?.dataset.settled === 'true'", timeout=30000)


# FR-1091 AC-502: the screen opens on the repository's own functions and the API answers read-only JSON with stats.
def test_ac502_api_and_screen_show_the_repository_graph(studio):
    page = _open(studio)
    _settled(page)
    state = page.evaluate("() => window.eabkView.getState()")
    assert state["nodes"] > 100 and state["links"] > 100 and state["shown"] == state["nodes"]
    data = page.evaluate("async () => (await fetch('/api/codegraph')).json()")
    assert data["stats"]["nodes"] > 1000 and {"nodes", "edges", "files", "stats"} <= set(data)
    assert page.locator('[data-testid="cg-stats"]').inner_text().strip()
    assert page.locator(CANVAS).evaluate("c => c.width > 0 && c.height > 0 && c.getAttribute('role') === 'img' && c.tabIndex === 0")
    page.context.close()


# FR-1091 AC-503: choosing a symbol (list, keyboard) shows its callers and callees, and a deep link (?sym=) opens it selected.
def test_ac503_select_shows_callers_callees_and_deep_link(studio):
    page = _open(studio, "?sym=" + UI_EL)
    _settled(page)
    assert page.locator('[data-testid="cg-name"]').first.inner_text() == "el"
    assert page.locator(CANVAS).get_attribute("data-selected") == UI_EL
    assert "(0)" not in page.locator(".cg-rel h3").first.inner_text()       # el has callers
    first = page.locator('.cg-rel [data-testid="cg-item"]').first
    target = first.get_attribute("data-id")
    first.focus()
    page.keyboard.press("Enter")                                           # the list is usable without a pointer
    page.wait_for_function("(id) => document.querySelector('[data-testid=cg-canvas]').dataset.selected === id", arg=target)
    page.keyboard.press("Escape")
    page.context.close()


# FR-1091 AC-502: filters rebuild the map: guesses add links only, a smaller limit shows fewer nodes, a kind can be switched off.
def test_ac502_filters_change_what_is_drawn(studio):
    page = _open(studio)
    _settled(page)
    base = page.evaluate("() => window.eabkView.getState()")
    page.locator('[data-testid="cg-guess"]').check()
    page.wait_for_function("(n) => window.eabkView.getState().links > n", arg=base["links"])
    page.locator('[data-testid="cg-guess"]').uncheck()
    page.wait_for_function("(n) => window.eabkView.getState().links === n", arg=base["links"])
    page.locator('[data-testid="cg-limit"]').evaluate("e => { e.value = '0'; e.dispatchEvent(new Event('input', { bubbles: true })); }")
    page.wait_for_function("() => window.eabkView.getState().nodes <= 100")
    page.locator('[data-testid="cg-limit"]').evaluate("e => { e.value = '3'; e.dispatchEvent(new Event('input', { bubbles: true })); }")
    page.wait_for_function("() => window.eabkView.getState().nodes > 150")
    page.locator('[data-testid="cg-kind-method"]').uncheck()
    page.wait_for_function("() => document.querySelector('[data-testid=cg-list]').textContent.length > 0")
    assert not page.locator('.cg-list .dot').evaluate_all("els => els.length === 0")
    page.context.close()


# FR-1091 AC-503: search narrows the list and Enter selects the first match; zoom and pan change the camera.
def test_ac503_search_wheel_zoom_and_fit(studio):
    page = _open(studio)
    _settled(page)
    page.locator('[data-testid="cg-search"]').fill("codegraph_bytes")
    page.wait_for_function("() => document.querySelector('[data-testid=cg-list]').textContent.includes('codegraph_bytes')")
    page.locator('[data-testid="cg-search"]').press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=cg-canvas]').dataset.selected.includes('codegraph_bytes')")
    z0 = page.evaluate("() => window.eabkView.getState().zoom")
    box = page.locator(CANVAS).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, -600)
    page.wait_for_function("(z) => window.eabkView.getState().zoom > z", arg=z0)
    page.locator('[data-testid="cg-fit"]').click()
    page.context.close()


# FR-1091 AC-504: with reduced motion the layout is solved at once (settled, still) and the pause control stays usable.
def test_ac504_reduced_motion_is_settled_at_once(studio):
    page = _open(studio, reduced=True)
    assert page.evaluate("() => window.eabkView.getState().settled") is True
    page.locator('[data-testid="cg-pause"]').click()
    page.context.close()


# FR-1091 AC-504: the screen is reachable from the Source screen and from the command box, in both languages.
def test_ac504_entry_points_and_english(studio):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('eabk-studio.lang','en')")
    page.goto(f"{url}/#/source")
    page.wait_for_selector('[data-testid="open-codegraph"]', timeout=60000)
    page.locator('[data-testid="open-codegraph"]').click()
    page.wait_for_selector(FP_CARD, timeout=60000)
    assert "Code floorplan" in page.locator("#view h1").first.inner_text()
    page.locator('[data-testid="open-network"]').click()
    page.wait_for_selector(CANVAS, timeout=60000)
    assert "Code relations" in page.locator("#view h1").first.inner_text()
    page.locator('[data-testid="open-floorplan"]').click()
    page.wait_for_selector(FP_CARD)
    page.locator('[data-testid="command-search"]').fill("> code")
    assert page.locator('[data-testid="command-item"]').count() >= 1
    ctx.close()


def _fp(studio, query="", lang="en"):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    page.goto(f"{url}/#/floorplan{query}")
    page.wait_for_selector(FP_CARD, timeout=60000)
    return page


# FR-1091 AC-505: parts -> files -> functions as cards and arrows; opening a card goes one level down, the breadcrumb and Esc go back.
def test_ac505_floorplan_levels_cards_and_arrows(studio):
    page = _fp(studio)
    top = page.evaluate("() => window.eabkView.getState()")
    assert top["level"] == 0 and top["cards"] >= 5 and top["arrows"] >= 1
    assert page.locator(".fp-lane-head").count() >= 2
    page.locator(f'{FP_CARD}[data-key="HVE-Studio/web/js"]').click()
    page.locator('[data-testid="fp-open"]').click()
    page.wait_for_function("() => window.eabkView.getState().level === 1")
    files = page.evaluate("() => window.eabkView.getState()")
    assert files["cards"] >= 10 and files["arrows"] >= 10
    assert page.locator(f'{FP_CARD}[data-key="HVE-Studio/web/js/ui.js"] .fp-desc').inner_text().strip()   # plain-language line from the source
    page.locator(f'{FP_CARD}[data-key="HVE-Studio/web/js/ui.js"]').dblclick()
    page.wait_for_function("() => window.eabkView.getState().level === 2")
    assert page.locator(f'{FP_CARD}[data-type="sym"]').count() >= 5
    page.locator('[data-testid="fp-stage"]').focus()
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.eabkView.getState().level === 1")
    page.locator('[data-testid="fp-crumb"]').first.click()
    page.wait_for_function("() => window.eabkView.getState().level === 0")
    page.context.close()


# FR-1091 AC-506: selecting dims the rest and lights the arrows of that card; details list the neighbours; dev names, search, deep link, keyboard.
def test_ac506_floorplan_selection_search_dev_names_and_deep_link(studio):
    page = _fp(studio, "?g=HVE-Studio/web/js")
    page.locator(f'{FP_CARD}[data-key="HVE-Studio/web/js/dashboard.js"]').click()
    assert page.locator(".fp-edge.hot").count() >= 1 and page.locator(".fp-card.dim").count() >= 1
    assert page.locator('[data-testid="fp-name"]').inner_text() == "Dashboard"
    assert page.locator("#view .cg-rel .cg-sym").count() >= 1
    page.locator('[data-testid="fp-dev"]').check()
    assert page.locator('[data-testid="fp-name"]').inner_text() == "dashboard.js"
    page.locator('[data-testid="fp-dev"]').uncheck()
    page.locator('[data-testid="fp-search"]').fill("codegraph_bytes")
    page.locator('[data-testid="fp-hit"]').first.wait_for()
    page.locator('[data-testid="fp-search"]').press("Enter")
    page.wait_for_function("() => window.eabkView.getState().level === 2 && window.eabkView.getState().selected.includes('codegraph_bytes')")
    page.locator(f'{FP_CARD}.sel').focus()
    page.keyboard.press("Escape")
    deep = _fp(studio, "?g=HVE-Studio/web/js&f=HVE-Studio/web/js/ui.js")
    assert deep.evaluate("() => window.eabkView.getState().level") == 2
    deep.context.close()
    page.context.close()
