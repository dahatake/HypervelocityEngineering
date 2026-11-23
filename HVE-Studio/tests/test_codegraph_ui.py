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
    page.add_init_script(f"localStorage.setItem('hve-studio.lang','{lang}')")
    page.goto(f"{url}/#/codegraph{query}")
    page.wait_for_selector(CANVAS, timeout=60000)
    page.wait_for_function("() => window.hveView?.getState().nodes > 0", timeout=60000)
    return page


def _settled(page):
    page.wait_for_function("() => document.querySelector('[data-testid=cg-canvas]')?.dataset.settled === 'true'", timeout=30000)


# FR-1091 AC-502: the screen opens on the repository's own functions and the API answers read-only JSON with stats.
def test_ac502_api_and_screen_show_the_repository_graph(studio):
    page = _open(studio)
    _settled(page)
    state = page.evaluate("() => window.hveView.getState()")
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
    base = page.evaluate("() => window.hveView.getState()")
    page.locator('[data-testid="cg-guess"]').check()
    page.wait_for_function("(n) => window.hveView.getState().links > n", arg=base["links"])
    page.locator('[data-testid="cg-guess"]').uncheck()
    page.wait_for_function("(n) => window.hveView.getState().links === n", arg=base["links"])
    page.locator('[data-testid="cg-limit"]').evaluate("e => { e.value = '0'; e.dispatchEvent(new Event('input', { bubbles: true })); }")
    page.wait_for_function("() => window.hveView.getState().nodes <= 100")
    page.locator('[data-testid="cg-limit"]').evaluate("e => { e.value = '3'; e.dispatchEvent(new Event('input', { bubbles: true })); }")
    page.wait_for_function("() => window.hveView.getState().nodes > 150")
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
    z0 = page.evaluate("() => window.hveView.getState().zoom")
    box = page.locator(CANVAS).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, -600)
    page.wait_for_function("(z) => window.hveView.getState().zoom > z", arg=z0)
    page.locator('[data-testid="cg-fit"]').click()
    page.context.close()


# FR-1091 AC-504: with reduced motion the layout is solved at once (settled, still) and the pause control stays usable.
def test_ac504_reduced_motion_is_settled_at_once(studio):
    page = _open(studio, reduced=True)
    assert page.evaluate("() => window.hveView.getState().settled") is True
    page.locator('[data-testid="cg-pause"]').click()
    page.context.close()


# FR-1091 AC-504: the screen is reachable from the Source screen and from the command box, in both languages.
def test_ac504_entry_points_and_english(studio):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('hve-studio.lang','en')")
    page.goto(f"{url}/#/source")
    page.wait_for_selector('[data-testid="src-tab-map"][aria-selected="true"]', timeout=60000)
    page.locator('[data-testid="src-tab-functions"]').click()
    page.wait_for_selector(FP_CARD, timeout=60000)
    assert page.locator('[data-testid="src-tab-functions"]').get_attribute("aria-selected") == "true" and page.locator('[role="tablist"] [role="tab"]').count() == 3  # FR-1100 added "Between repositories"
    page.locator('[data-testid="open-network"]').click()
    page.wait_for_selector(CANVAS, timeout=60000)
    assert page.locator('[data-testid="src-tab-functions"]').get_attribute("aria-selected") == "true"      # the network view stays on the same tab
    assert "Code relations" in page.locator("#view h1").first.inner_text()
    page.locator('[data-testid="src-tab-map"]').click()
    page.wait_for_selector('[data-testid="src-tab-map"][aria-selected="true"]')
    page.locator('[data-testid="src-tab-functions"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(FP_CARD)
    page.locator('[data-testid="command-search"]').fill("> code")
    assert page.locator('[data-testid="command-item"]').count() >= 1
    ctx.close()
