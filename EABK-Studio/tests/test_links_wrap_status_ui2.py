"""Integration tests (part 2) for FR-1031 / FR-1032 / FR-1033: inline links, SVG labels, empty state, command box, keyboard cards."""
import socket
import subprocess
import sys
import time

import pytest

from test_links_wrap_status_ui import ROOT, studio, _open, _impl, make_zoom, sync_api  # noqa: F401


# FR-1032 AC-191: with decision and run data all four chip kinds are shown.
def test_history_has_all_four_chip_kinds(studio):
    page = _open(studio, "dashboard")
    page.wait_for_selector('[data-testid="history-chip"]')
    kinds = {c.get_attribute("data-kind") for c in page.locator('[data-testid="history-chip"]').all()}
    assert {"decision", "run", "requirement", "impl"} <= kinds
    page.context.close()


# FR-1032 AC-191: with no records the box shows ordinary empty text, not a placeholder chip.
def test_empty_history_box_shows_empty_text_not_chip(tmp_path, studio):
    repo = make_zoom(tmp_path / "e")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2)
    try:
        page = studio[0].new_page()
        page.goto(f"http://127.0.0.1:{port}/#/dashboard")
        page.wait_for_selector('[data-testid="history-box"]')
        box = '[data-testid="history-box"][data-kind="decision"]'
        assert page.locator(f'{box} [data-testid="history-chip"]').count() == 0
        assert page.locator(f'{box} [data-testid="history-empty"]').count() == 1
        page.close()
    finally:
        proc.terminate()


# FR-1031 AC-188 AC-189: IDs and terms inside running text and inside SVG labels become links; unknown IDs do not.
def test_inline_ids_terms_and_svg_labels_are_linked(studio):
    page = _open(studio, "dashboard")
    page.evaluate("""() => {
      const v = document.getElementById('view');
      const p = document.createElement('p'); p.id = 'probe'; p.textContent = 'see FR-001 and 注文 but not FR-9999';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.id = 'probe-svg';
      const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text'); tx.textContent = 'FR-001'; svg.append(tx);
      v.append(p, svg);
    }""")
    page.wait_for_selector("#probe a.xref")
    assert page.locator("#probe a.xref").all_inner_texts() == ["FR-001", "注文"]
    page.wait_for_selector("#probe-svg a.xref")
    assert page.locator("#probe-svg a.xref").first.get_attribute("aria-label").endswith("FR-001")
    page.context.close()


# FR-1033 AC-197: the command box ("> ...") selects and clears a segment; kanban cards work by keyboard.
def test_command_box_selects_and_clears_segment(studio):
    page = _impl(studio)
    page.locator("#q").fill("> ")
    items = page.locator('[data-testid="command-item"]')
    assert items.count() >= 2
    items.first.click()
    page.wait_for_function("() => document.querySelector('[data-testid=impl-filter-status]').dataset.active === 'true'")
    page.locator("#q").fill(">解除")
    page.locator("#q").press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=impl-filter-status]').dataset.active === 'false'")
    page.context.close()


# FR-1033 AC-197: kanban cards are keyboard operable.
def test_kanban_card_opens_detail_with_enter(studio):
    page = _impl(studio)
    page.locator('[data-testid="impl-kanban-card"]').first.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#drawer:not([hidden])")
    page.context.close()
