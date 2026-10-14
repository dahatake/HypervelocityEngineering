"""Integration tests for FR-1031 / FR-1032 / FR-1033 (EABK Studio UI). Run: python -m pytest EABK-Studio/tests -q"""
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "tests" / "system"))
from entity_repo import make_zoom, DOC  # noqa: E402

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    repo = make_zoom(tmp_path_factory.mktemp("ui") / "r")
    doc = repo / DOC
    long_id = "Y" * 120
    doc.write_text(doc.read_text(encoding="utf-8") + "".join(
        f"\n#### FR-{900 + i} {long_id}{i} " + "とても長い題名" * 10 + "\n- 決定状態: 承認済み\n" for i in range(20))
        + "\n| 日付 | 対象ID | 決定 | 根拠 | run |\n|---|---|---|---|---|\n| 2026-10-15 | FR-001 | " + "長い決定" * 20 + " | 依頼 | " + "R" * 100 + " |\n",
        encoding="utf-8")
    (repo / "docs" / "run-history.md").write_text(
        "| run-id | 開始 | 終了 | HEAD | 結果 | 実装した要求 ID |\n|---|---|---|---|---|---|\n| " + "r" * 100
        + " | 2026-10-15T01:00 | 2026-10-15T02:00 | abc | 実装完了 | FR-001 |\n", encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser, f"http://127.0.0.1:{port}"
        browser.close()
    proc.terminate()


def _open(studio, route, width=1280, lang=None):
    browser, url = studio
    page = browser.new_context(viewport={"width": width, "height": 800}).new_page()
    page.goto(f"{url}/#/{route}")
    page.wait_for_load_state("networkidle")
    if lang == "en":
        page.evaluate("() => localStorage.setItem('eabk.lang','en')")
        page.reload()
        page.wait_for_load_state("networkidle")
    return page


# FR-1031 AC-189 AC-190: existing IDs are links with an accessible kind + ID name and an underline; unknown IDs are not links.
def test_ids_are_underlined_labelled_links_and_unknown_ids_are_not(studio):
    page = _open(studio, "tables?tab=reqs")
    link = page.locator("#view a.xref", has_text=re.compile(r"^FR-001$")).first
    assert link.count() == 1
    assert link.get_attribute("aria-label").endswith("FR-001")
    assert "underline" in link.evaluate("e => getComputedStyle(e).textDecorationLine")
    page.goto(page.url.split("#")[0] + "#/tables?tab=reqs&q=FR-9999")
    page.wait_for_load_state("networkidle")
    assert page.locator("#view a.xref", has_text="FR-9999").count() == 0
    page.context.close()


# FR-1031 AC-188 AC-189: file paths / names in managed data link too (catalog table name inside the drawer).
def test_drawer_ids_are_links(studio):
    page = _open(studio, "map2d?select=FR-001")
    page.wait_for_selector("#drawer:not([hidden])")
    assert page.locator("#drawer a.xref").count() >= 1
    page.context.close()


# FR-1032 AC-191 AC-192 AC-193: chips wrap within boxes at 320px and in EN too.
@pytest.mark.parametrize("width,lang", [(1280, None), (320, None), (320, "en")])
def test_history_chips_wrap_inside_boxes(studio, width, lang):
    page = _open(studio, "dashboard", width, lang)
    page.wait_for_selector('[data-testid="history-chip"]')
    bad = page.evaluate("""() => [...document.querySelectorAll('[data-testid="history-chip"]')].filter(c => {
        const b = c.closest('[data-testid="history-box"]'); if (!b) return true;
        const r = c.getBoundingClientRect(), o = b.getBoundingClientRect();
        return r.left < o.left - 0.5 || r.right > o.right + 0.5 || c.scrollWidth > c.clientWidth + 1;
    }).length""")
    assert bad == 0
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    page.context.close()


def _impl(studio):
    page = _open(studio, "implstatus")
    page.wait_for_selector('[data-testid="impl-bar-segment"]')
    return page


# FR-1033 AC-195 AC-196 AC-197 AC-204: a goal segment applies the (goal, state) pair, shows it in words, works by keyboard, never navigates.
def test_goal_segment_applies_pair_by_keyboard_without_navigation_and_clears(studio):
    page = _impl(studio)
    route = page.url
    seg = page.locator('[data-testid="impl-bar-segment"][data-scope="goal"]').first
    n, state, group = int(seg.get_attribute("data-count")), seg.get_attribute("data-state"), seg.get_attribute("data-group")
    seg.focus()
    page.keyboard.press("Enter")
    status = page.locator('[data-testid="impl-filter-status"]')
    assert state in status.inner_text() and group in status.inner_text()
    assert seg.get_attribute("aria-pressed") == "true"
    assert page.locator('[data-testid="impl-kanban-card"][data-match="true"]').count() == n
    assert page.url == route and page.locator("#drawer[hidden]").count() == 1
    page.keyboard.press("Enter")
    assert page.locator("[data-match]").count() == 0
    page.context.close()


# FR-1033 AC-198: a zero-count state (legend) shows "該当なし" and can be cleared without breaking the screen.
def test_zero_match_state_is_announced_and_clearable(studio):
    page = _impl(studio)
    legends = page.locator('[data-testid="impl-legend-state"]')
    zero = None
    for i in range(legends.count()):
        st = legends.nth(i).get_attribute("data-state")
        if int(page.locator(f'[data-testid="impl-kanban-column"][data-state="{st}"]').get_attribute("data-count")) == 0:
            zero = legends.nth(i)
            break
    assert zero is not None
    zero.click()
    assert "該当なし" in page.locator('[data-testid="impl-filter-status"]').inner_text()
    page.locator('[data-testid="impl-filter-clear"]').click()
    assert page.locator("[data-match]").count() == 0
    page.context.close()


# FR-1033 AC-196: filter mode hides non-matching cards; the layout (kanban columns) stays.
def test_filter_mode_hides_non_matching_cards(studio):
    page = _impl(studio)
    seg = page.locator('[data-testid="impl-bar-segment"][data-scope="all"]').first
    n = int(seg.get_attribute("data-count"))
    seg.click()
    page.locator('[data-testid="impl-filter-mode"]').click()
    assert page.locator('[data-testid="impl-kanban-card"]:visible').count() == n
    assert page.locator('[data-testid="impl-kanban-column"]').count() == 5
    page.context.close()


# FR-1031 AC-204: clicking a segment does not change the selection / open detail.
def test_segment_click_does_not_open_detail(studio):
    page = _impl(studio)
    page.locator('[data-testid="impl-bar-segment"][data-scope="all"]').first.click()
    assert page.locator("#drawer[hidden]").count() == 1
    page.context.close()

