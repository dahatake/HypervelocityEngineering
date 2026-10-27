"""Integration-level tests (draft) for FR-1072 AC-393 and NFR-UX-016 AC-394 / AC-396 (run 202610192312).

置き場の注記: test-designer は tests/system/ 以外を変更できない（hook G-5）ため、EABK-Studio/tests/test_*_ui.py の流儀
（test_links_wrap_status_ui.py の studio fixture / _open）をそのまま使う形でここに置く。実装者が
EABK-Studio/tests/test_header_row_ui.py へ移してよい（移すときは sys.path の 3 行と import を元の流儀に戻す）。
期待値は要求定義書の受入基準だけから決める。幅は PARAM-048 = 1280 / 1024 / 800 / 600 / 320 CSS px（320 = PARAM-034。ヘッダー帯の横スクロール可）。
Run: python -m pytest tests/system/e2e/test_studio_header_row_integration.py -q
"""
import sys
from pathlib import Path

import pytest

from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: E402,F401

WIDTHS = [1280, 1024, 800, 600, 320]  # PARAM-048

CTRL = {
    "nav": "header.top #nav a",
    "dim": '[data-testid="header-dim-toggle"] button',
    "persona": "header.top #personaBar button",
    "lang": "header.top #lang button",
    "theme": 'header.top [data-testid="theme-toggle"] button',
}

JS_NAMES = """(sel) => [...document.querySelectorAll(sel)].map((e) => {
  const cs = getComputedStyle(e);
  const r = e.getBoundingClientRect();
  return {text: (e.textContent || '').trim(), aria: e.getAttribute('aria-label') || '', title: e.getAttribute('title') || '',
          labelledby: e.getAttribute('aria-labelledby') || '', shown: cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0,
          href: e.getAttribute('href') || '', dim: e.dataset.dim || ''};
})"""

# 常設の要素。一時的な表示（#results・#drawer・#toast・ダイアログ・ツールチップ）は対象外。
# 地図の表示面: 古典のグラフは canvas、エンティティのある管理データ（make_zoom）の意味ズームは sz-viewport
SURFACE = '#view canvas, [data-testid="sz-viewport"]'
PERMANENT = ["header.top", "#navDesc", "#view", '[data-testid="map-tiers"]', SURFACE]
NESTED = {("#view", '[data-testid="map-tiers"]'), ("#view", SURFACE)}  # 親子は交差してよい


def _rects(page, sels):
    return page.evaluate("""(sels) => Object.fromEntries(sels.map((s) => { const e = document.querySelector(s);
      if (!e) return [s, null]; const cs = getComputedStyle(e); const b = e.getBoundingClientRect();
      return [s, cs.display === 'none' ? null : {x: b.left, y: b.top, w: b.width, h: b.height}]; }))""", sels)


def _inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w > 0 and h > 0 and w * h > 0.5  # 外接矩形の交差面積 0（0.5px² は丸め誤差）


def _assert_no_overlap(page, sels=PERMANENT):
    r = _rects(page, sels)
    live = [s for s in sels if r[s]]
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if (a, b) in NESTED or (b, a) in NESTED:
                continue
            assert not _inter(r[a], r[b]), f"{a} overlaps {b}: {r[a]} / {r[b]}"


# FR-1072 AC-393: elements whose label is shortened keep the full text as accessible name and tooltip; nothing is dropped.
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac393_shortened_labels_keep_full_name_and_no_function_is_dropped(studio, lang):
    wide = _open(studio, "map2d", width=1280, lang=lang)
    ref = {k: wide.evaluate(JS_NAMES, sel) for k, sel in CTRL.items()}
    wide.context.close()
    assert len(ref["nav"]) == 9 and len(ref["persona"]) == 3 and len(ref["dim"]) == 4 and len(ref["lang"]) == 2 and ref["theme"]
    for width in (1024, 800, 600, 320):
        page = _open(studio, "map2d", width=width, lang=lang)
        for k, sel in CTRL.items():
            cur = page.evaluate(JS_NAMES, sel)
            assert len(cur) == len(ref[k]), f"{k} lost an element at {width}px"
            for c, r in zip(cur, ref[k]):
                assert c["shown"], f"{k} {r['text']!r} hidden at {width}px"
                full = r["text"]
                if c["text"] != full:  # ラベルを省略・短縮した → 全文を accessible name とツールチップに保つ
                    assert full in c["aria"] or c["labelledby"], f"{k}: full text {full!r} missing from accessible name"
                    assert full in c["title"] or full in c["aria"], f"{k}: full text {full!r} missing from tooltip"
                assert c["aria"] or c["title"] or c["text"] or c["labelledby"], f"{k} has no accessible name"
                assert c["href"] == r["href"] and c["dim"] == r["dim"]
        page.context.close()


# FR-1072 AC-393 (anomaly): a visibly truncated (ellipsis) control must expose its whole text to assistive tech.
@pytest.mark.parametrize("width", [800, 600, 320])
def test_ac393_truncated_controls_expose_full_text(studio, width):
    page = _open(studio, "map2d", width=width)
    bad = page.evaluate("""() => [...document.querySelectorAll('header.top button, header.top a, header.top #modelTime')]
      .filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== 'visible')
      .filter((e) => { const t = (e.textContent || '').trim(); const n = (e.getAttribute('aria-label') || '') + '|' + (e.getAttribute('title') || '');
                       return t && !n.includes(t); }).map((e) => e.textContent.trim())""")
    assert bad == []
    page.context.close()


# NFR-UX-016 AC-394: permanent elements' rectangles do not intersect at each width, on several screens.
@pytest.mark.parametrize("route", ["map2d", "dashboard", "tables", "entities"])
@pytest.mark.parametrize("width", WIDTHS)
def test_ac394_permanent_elements_do_not_intersect(studio, route, width):
    page = _open(studio, route, width=width)
    _assert_no_overlap(page)
    page.context.close()


# NFR-UX-016 AC-394: with the explanation panel opened the rectangles still do not intersect.
@pytest.mark.parametrize("width", WIDTHS)
def test_ac394_opened_explanation_panel_does_not_intersect_the_map(studio, width):
    page = _open(studio, "map2d", width=width)
    panel = page.locator('[data-testid="map-tiers"]')
    panel.wait_for()
    if panel.get_attribute("open") is None:
        panel.locator("summary").click()
    _assert_no_overlap(page)
    r = _rects(page, ['[data-testid="map-tiers"]', SURFACE])
    assert r[SURFACE] and not _inter(r['[data-testid="map-tiers"]'], r[SURFACE])
    page.context.close()


# NFR-UX-016 AC-396: changing the width keeps the typed search text, the route, and the panel state.
def test_ac396_state_survives_width_changes(studio):
    page = _open(studio, "map2d", width=1280)
    panel = page.locator('[data-testid="map-tiers"]')
    panel.wait_for()
    if panel.get_attribute("open") is None:
        panel.locator("summary").click()
    page.locator("#q").fill("FR-00")
    hash_before = page.evaluate("() => location.hash")
    for width in (1024, 800, 600, 320, 1280, 320):
        page.set_viewport_size({"width": width, "height": 800})
        page.wait_for_timeout(150)
        assert page.locator("#q").input_value() == "FR-00", f"search text lost at {width}px"
        assert page.evaluate("() => location.hash") == hash_before
        assert panel.evaluate("(e) => e.open"), f"panel state lost at {width}px"
        _assert_no_overlap(page)
    page.context.close()


# NFR-UX-016 AC-396 (zoom factor): 200% zoom is equivalent to 640 CSS px; typed text and layout hold.
def test_ac396_state_survives_zoom_factor(studio):
    page = _open(studio, "tables", width=1280)
    page.locator("#q").fill("FR-001")
    for w in (640, 320):  # 拡大率 200% 相当 (640) と PARAM-034 相当 (320)
        page.set_viewport_size({"width": w, "height": 400})
        page.wait_for_timeout(150)
        assert page.locator("#q").input_value() == "FR-001", f"typed text lost at {w}px"
        assert "tables" in page.evaluate("() => location.hash")
        _assert_no_overlap(page, ["header.top", "#navDesc", "#view"])
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(150)
    assert page.locator("#q").input_value() == "FR-001"
    _assert_no_overlap(page, ["header.top", "#navDesc", "#view"])
    page.context.close()
