"""System tests for FR-1072 AC-391/AC-392 and NFR-UX-016 AC-395 (run 202610192312).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The implementation is NOT
the oracle.  Widths are PARAM-048 = 1280 / 1024 / 800 / 600 / 320 CSS px (320 = PARAM-034; the header band may scroll horizontally).  AC-393/394/396 are integration level
(EABK-Studio/tests/test_header_row_ui.py).

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - ヘッダー帯: <header class="top">。要素: ナビ #nav a（8）、表示モード切替 [data-testid="header-dim-toggle"] button、
    検索 #q、リポジトリ名 #repoBtn、日時 #modelTime、ロール #personaBar button（3）、言語 #lang、
    テーマ [data-testid="theme-toggle"] button。
  - 地図の表示面: #view canvas。説明パネル（上位層・ロールの説明）: [data-testid="map-tiers"]（<details>、開閉は summary）。
  - 画面: #/map2d。
"""
import pytest

from entity_repo import make_zoom
from test_semantic_zoom_system import _serve
from test_studio_system import studio_url  # noqa: F401  (fixture: 実リポジトリ)

WIDTHS = [1280, 1024, 800, 600, 320]  # PARAM-048
TOL = 2  # PARAM-050: 縦位置の中心の許容差 (CSS px)

ITEMS = {
    "nav": "header.top #nav a",
    "dim": '[data-testid="header-dim-toggle"] button',
    "search": "header.top #q",
    "repo": "header.top #repoBtn",
    "time": "header.top #modelTime",
    "persona": "header.top #personaBar button",
    "lang": "header.top #lang button",
    "theme": 'header.top [data-testid="theme-toggle"] button',
}
MAP_SURFACE = '#view canvas, [data-testid="sz-viewport"]'  # make_zoom のデータでは #/map2d が意味ズーム表示（canvas なし）


def _fr1041_nav_count():
    """FR-1041 AC-225 の「①〜N」から、ナビ全項目の数を要求定義書から求める（数を直書きしない）。"""
    import re
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[3] / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    sec = doc.split("#### FR-1041", 1)[1].split("\n#### ", 1)[0]
    m = re.search(r"①〜[①-⑳](?:、[①-⑳])*", sec)  # 例「①〜⑦、⑨」→ 最大 ⑨
    assert m, "FR-1041 のナビ項目範囲（①〜N）が読めない"
    return max(ord(c) for c in m.group(0) if "①" <= c <= "⑳") - ord("①") + 1


NAV_COUNT = _fr1041_nav_count()
EXPECT_COUNT = {"nav": NAV_COUNT, "dim": 4, "persona": 3}

JS_RECTS = """(sel) => [...document.querySelectorAll(sel)].map((e) => {
  const r = e.getBoundingClientRect();
  return {x: r.left, y: r.top, w: r.width, h: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2,
          text: (e.innerText || e.value || '').trim().slice(0, 30)};
})"""


@pytest.fixture()
def zurl(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "hdrrow"))
    yield url
    proc.terminate()


def _open(browser, url, width, route="map2d", height=800):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    p = ctx.new_page()
    p.goto(url.split("#")[0] + "#/" + route)
    p.wait_for_load_state("networkidle")
    p.wait_for_selector("header.top")
    p.wait_for_selector("header.top #nav a")
    return ctx, p


def _all(page):
    out = {}
    for k, sel in ITEMS.items():
        out[k] = page.evaluate(JS_RECTS, sel)
    return out


def _inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w > 0 and h > 0 and w * h > 0.5  # 外接矩形の交差面積 0（0.5px² は丸め誤差）


# FR-1072 AC-391: every header element sits on one horizontal row at each PARAM-048 width; nav items are not stacked.
@pytest.mark.parametrize("width", WIDTHS)
def test_ac391_all_header_elements_are_on_one_row(browser, zurl, width):
    ctx, page = _open(browser, zurl, width)
    items = _all(page)
    for k, n in EXPECT_COUNT.items():
        assert len(items[k]) == n, f"{k}: {len(items[k])} != {n}"
    assert len(items["lang"]) == 2, "lang"  # FR-011 AC-430: JA/EN の 2 button
    for k in ("search", "repo", "time"):
        assert len(items[k]) == 1, k
    assert len(items["theme"]) >= 1
    flat = [r for v in items.values() for r in v]
    band = page.evaluate("() => { const r = document.querySelector('header.top').getBoundingClientRect(); return {y: r.top, h: r.height}; }")
    tallest = max(r["h"] for r in flat)
    # 各要素の縦位置の中心が、帯の中心から PARAM-050 (2px) 以内（帯の中心は内側高さ clientHeight で測り、スクロールバー分を除く）
    bcy = page.evaluate("() => { const h = document.querySelector('header.top'); return h.getBoundingClientRect().top + h.clientHeight / 2; }")
    for r in flat:
        assert abs(r["cy"] - bcy) <= TOL, f"{r['text']!r} center off by {abs(r['cy'] - bcy):.1f}px at {width}px"
    # ナビ項目は縦に積まれない
    navs = items["nav"]
    assert max(r["y"] for r in navs) - min(r["y"] for r in navs) <= 2
    xs = [r["x"] for r in navs]
    assert xs == sorted(xs) and len(set(xs)) == len(navs) == NAV_COUNT  # FR-1041 のナビ全項目
    # 帯そのものが 1 行分の高さ（折り返して高さが増えない）
    assert band["h"] <= tallest * 2.5
    # ヘッダー帯の外（ページ本体）には横スクロールが出ない
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    ctx.close()


# FR-1072 AC-391 (anomaly): the one-row layout also holds in English (longer labels) and on a screen other than the map.
@pytest.mark.parametrize("width", [800, 600, 320])
def test_ac391_one_row_holds_in_english_on_other_screen(browser, zurl, width):
    ctx = browser.new_context(viewport={"width": width, "height": 800})
    page = ctx.new_page()
    page.goto(zurl.split("#")[0] + "#/dashboard")
    page.evaluate("() => localStorage.setItem('eabk-studio.lang','en')")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("header.top")
    # リロード直後はナビ描画が遅れるため、ナビ項目が出揃うまで待つ
    page.wait_for_function(
        "n => document.querySelectorAll('header.top #nav a').length >= n", arg=NAV_COUNT)
    items = _all(page)
    flat = [r for v in items.values() for r in v]
    assert len(items["nav"]) == NAV_COUNT
    bcy = page.evaluate("() => { const h = document.querySelector('header.top'); return h.getBoundingClientRect().top + h.clientHeight / 2; }")
    assert all(abs(r["cy"] - bcy) <= TOL for r in flat), "elements are not on one row (center off > PARAM-050)"
    assert max(r["y"] for r in items["nav"]) - min(r["y"] for r in items["nav"]) <= 2
    ctx.close()


# FR-1072 AC-392: header element rectangles do not intersect; the page body has no horizontal scroll.
@pytest.mark.parametrize("width", WIDTHS)
def test_ac392_header_elements_do_not_overlap_and_page_has_no_horizontal_scroll(browser, zurl, width):
    ctx, page = _open(browser, zurl, width)
    flat = [r for v in _all(page).values() for r in v]
    for i, a in enumerate(flat):
        for b in flat[i + 1:]:
            assert not _inter(a, b), f"overlap: {a['text']!r} x {b['text']!r}"
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert page.evaluate("() => document.body.scrollWidth <= document.documentElement.clientWidth + 1")
    ctx.close()


# FR-1072 AC-392: when the band overflows it scrolls inside; every element can be reached and receives the click point / keyboard focus.
@pytest.mark.parametrize("width", WIDTHS)
def test_ac392_every_header_element_is_reachable_by_pointer_and_keyboard(browser, zurl, width):
    ctx, page = _open(browser, zurl, width)
    hdr = page.evaluate("""() => { const h = document.querySelector('header.top');
      const all = [...h.querySelectorAll('*')];
      const sc = [h, ...all].find((e) => e.scrollWidth > e.clientWidth + 1 && /(auto|scroll)/.test(getComputedStyle(e).overflowX));
      return {overflow: [h, ...all].some((e) => e.scrollWidth > e.clientWidth + 1), scrollable: !!sc}; }""")
    if hdr["overflow"]:
        assert hdr["scrollable"], "band overflows but is not horizontally scrollable"
        moved = page.evaluate("""() => { const h = document.querySelector('header.top');
          const s = [h, ...h.querySelectorAll('*')].find((e) => e.scrollWidth > e.clientWidth + 1 && /(auto|scroll)/.test(getComputedStyle(e).overflowX));
          s.scrollLeft = s.scrollWidth; return s.scrollLeft > 0; }""")
        assert moved
    for k, sel in ITEMS.items():
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            el.scroll_into_view_if_needed()
            hit = el.evaluate("""(e) => { const r = e.getBoundingClientRect();
              const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
              return !!t && (t === e || e.contains(t) || t.contains(e)); }""")
            assert hit, f"{k}[{i}] is covered / outside the viewport at {width}px"
            el.focus()
            assert el.evaluate("(e) => document.activeElement === e || e.contains(document.activeElement)"), f"{k}[{i}] cannot take focus"
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    ctx.close()


# FR-1072 AC-392 (anomaly): Tab from the first header element walks through all of them without leaving the header early.
@pytest.mark.parametrize("width", [800, 600, 320])
def test_ac392_tab_walks_all_header_controls(browser, zurl, width):
    ctx, page = _open(browser, zurl, width)
    page.locator("header.top #nav a").first.focus()
    seen = set()
    for _ in range(40):
        ident = page.evaluate("() => { const a = document.activeElement; return a && a.closest('header.top') ? (a.closest('#lang') ? 'lang' : a.id || a.getAttribute('href') || a.dataset.dim || a.textContent.trim()) : null; }")
        if ident is None:
            break
        seen.add(ident)
        page.keyboard.press("Tab")
    must = {"q", "repoBtn", "lang"}
    assert must <= seen, f"not reached by Tab: {must - seen}"
    assert len([s for s in seen if s and s.startswith("#/")]) == NAV_COUNT
    ctx.close()


# NFR-UX-016 AC-395: opening the explanation panel on the map never covers the map surface; its content is not lost.
@pytest.mark.parametrize("width", WIDTHS)
def test_ac395_explanation_panel_does_not_cover_the_map(browser, zurl, width):
    ctx, page = _open(browser, zurl, width, "map2d")
    page.wait_for_selector(MAP_SURFACE)
    panel = page.locator('[data-testid="map-tiers"]')
    panel.wait_for()
    if panel.get_attribute("open") is None:
        panel.locator("summary").click()
    assert panel.evaluate("(e) => e.open")
    r = page.evaluate("""(sel) => { const q = (s) => { const e = document.querySelector(s); const b = e.getBoundingClientRect();
        return {x: b.left, y: b.top, w: b.width, h: b.height}; };
      return {panel: q('[data-testid="map-tiers"]'), map: q(sel)}; }""", MAP_SURFACE)
    assert r["map"]["w"] > 100 and r["map"]["h"] > 100, "map surface is hidden or collapsed"
    assert not _inter(r["panel"], r["map"]), f"panel covers map: {r}"
    if width <= 800:  # 狭い幅: 説明パネルは地図の下、または折りたたみ（地図の下端以下に位置）
        assert r["panel"]["y"] >= r["map"]["y"] + r["map"]["h"] - 1 or r["panel"]["x"] >= r["map"]["x"] + r["map"]["w"] - 1
    # 内容が欠けない: パネル内の項目が切れず、地図の操作 (ツールバーの先頭ボタン) が隠れない
    assert panel.evaluate("(e) => e.scrollWidth <= e.clientWidth + 1")
    hit = page.evaluate("""() => { const b = document.querySelector('#view .toolbar button, #view .toolbar'); if (!b) return true;
      const r = b.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!t && (t === b || b.contains(t) || t.contains(b)); }""")
    assert hit, "map toolbar is covered"
    # 測定: パネル内の各項目の外接矩形が親(パネル)の表示領域内にある（横に切れない）
    inside = panel.evaluate("""(p) => [...p.querySelectorAll('[data-testid="tier-group"]')].map((g) => { const a = g.getBoundingClientRect(), b = p.getBoundingClientRect();
      return a.left >= b.left - 1 && a.right <= b.right + 1; })""")
    assert inside and all(inside), "panel items are clipped horizontally"
    assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    ctx.close()


# NFR-UX-016 AC-395 (anomaly): the panel's items are the same at every width (nothing dropped when narrow).
def test_ac395_panel_content_is_not_dropped_when_narrow(browser, zurl):
    counts = {}
    for width in (1280, 600, 320):
        ctx, page = _open(browser, zurl, width, "map2d")
        panel = page.locator('[data-testid="map-tiers"]')
        panel.wait_for()
        if panel.get_attribute("open") is None:
            panel.locator("summary").click()  # 折りたたみ時は開く操作で全内容に到達できる
        counts[width] = panel.locator('[data-testid="tier-group"]').count()
        ctx.close()
    assert counts[1280] > 0
    assert counts[600] == counts[1280] and counts[320] == counts[1280]
