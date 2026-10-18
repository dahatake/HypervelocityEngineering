"""Integration tests for FR-1063 AC-355 (320px 幅・高い拡大率での上位層の表示), AC-352 (a11y の自動検査) と hier.js の層 id。
Run: python -m pytest EABK-Studio/tests/test_tier_reflow_a11y_ui.py -q"""
import json

import pytest

from test_links_wrap_status_ui import ROOT, studio, sync_api  # noqa: F401
from test_map_tiers_ui import graph_studio  # noqa: F401

GROUP = '[data-testid="tier-group"]'
# PARAM-034 の 320px 幅。200〜400% 拡大は CSS px で 640x400 → 320x200 相当の viewport になる。
VIEWPORTS = [(320, 800), (320, 256), (320, 200)]
LIST_ROUTES = ["tables?tab=reqs", "implstatus", "dashboard", "entities", "integrations", "source"]


def _page(studio, route, w, h, lang=None):
    browser, url = studio
    page = browser.new_context(viewport={"width": w, "height": h}).new_page()
    page.goto(f"{url}/#/{route}")
    page.wait_for_load_state("networkidle")
    if lang == "en":
        page.evaluate("() => localStorage.setItem('eabk-studio.lang','en')")
        page.reload()
        page.wait_for_load_state("networkidle")
    return page


def _no_hscroll(page):
    return page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")


def _clipped(page, root_sel):
    """root 内の層の見出し（名称・件数）の文字が、見える領域から欠けていないか。欠けた層の一覧を返す。"""
    return page.evaluate("""(sel) => {
        const bad = [];
        const root = document.querySelector(sel);
        for (const t of root.querySelectorAll('.tier-toggle')) {
            if (t.closest('.tier-body[hidden]')) continue;
            const r = t.getBoundingClientRect();
            for (const c of t.querySelectorAll('.tier-name,.tier-count')) {
                const cr = c.getBoundingClientRect();
                if (!cr.width) { bad.push('empty:' + t.textContent); continue; }
                if (cr.right > r.right + 1 || cr.left < r.left - 1) bad.push('overflow:' + t.textContent);
                if (cr.right > window.innerWidth + 1) bad.push('offscreen:' + t.textContent);
            }
            if (t.scrollWidth > t.clientWidth + 1) bad.push('scroll:' + t.textContent);
        }
        return bad;
    }""", root_sel)


# FR-1063 AC-355: 一覧系の画面は 320px 幅・高い拡大率でも上位層の名称・件数・開閉が欠けず、横スクロールが出ない
@pytest.mark.parametrize("w,h", VIEWPORTS)
@pytest.mark.parametrize("route", LIST_ROUTES)
def test_ac355_list_screens_keep_tier_headings_at_320px(studio, route, w, h):
    page = _page(studio, route, w, h)
    page.wait_for_selector(GROUP)
    assert _no_hscroll(page)
    assert _clipped(page, "#view") == []
    toggle = page.locator(f'{GROUP} [data-testid="tier-toggle"]').first
    before = toggle.get_attribute("aria-expanded")
    toggle.focus()
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") != before
    assert _no_hscroll(page)
    page.context.close()


# FR-1063 AC-355: 英語表示（名称が長くなる）でも同じ
@pytest.mark.parametrize("route", ["tables?tab=files", "implstatus"])
def test_ac355_english_names_do_not_break_layout_at_320px(studio, route):
    page = _page(studio, route, 320, 256, lang="en")
    page.wait_for_selector(GROUP)
    assert _no_hscroll(page) and _clipped(page, "#view") == []
    page.context.close()


# FR-1063 AC-355: マップの隅のパネルが 320px 幅でも名称・件数・開閉が欠けず、ページが横にあふれない
@pytest.mark.parametrize("route", ["map2d", "map3d"])
@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_ac355_map_corner_panel_fits_at_320px(studio, route, w, h):
    page = _page(studio, route, w, h)
    page.wait_for_selector(GROUP)
    assert _no_hscroll(page)
    assert _clipped(page, '[data-testid="map-tiers"]') == []
    box = page.locator('[data-testid="map-tiers"]').bounding_box()
    assert box["x"] >= -1 and box["x"] + box["width"] <= w + 1
    page.context.close()


# FR-1063 AC-355: RPG 風の会話ウィンドウの上位層が 320px 幅でも欠けず、画面内に収まる
@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_ac355_rpg_dialog_tiers_fit_at_320px(studio, w, h):
    page = _page(studio, "maprpg", w, h)
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    page.keyboard.press("Space")
    page.get_by_text("項目の上位層").first.click()
    dlg = page.locator('[data-testid="rpg-dialog"]')
    dlg.wait_for()
    assert _no_hscroll(page)
    assert _clipped(page, '[data-testid="rpg-tiers"]') == []
    box = dlg.bounding_box()
    assert box["x"] >= -1 and box["x"] + box["width"] <= w + 1
    page.context.close()


# FR-1063 AC-355: マップキャンバス上の上位層の見出しは、狭い幅で文字が小さくなって読めないとき、同じ名称・件数を隅のパネルの木（文字）で読める（代替表示）
@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_ac355_canvas_tier_headings_have_text_alternative_at_320px(graph_studio, w, h):
    browser, url, _n = graph_studio
    page = browser.new_context(viewport={"width": w, "height": h}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector("canvas.fill")
    page.wait_for_function("() => document.querySelector('canvas.fill').dataset.tiers && document.querySelector('canvas.fill').dataset.headingsAlt")
    tiers = json.loads(page.eval_on_selector("canvas.fill", "c => c.dataset.tiers"))
    assert tiers
    assert _no_hscroll(page)
    panel = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('[data-testid="map-tiers"] [data-testid="tier-group"]')]
        .map(g => [g.dataset.tierPath, parseInt(g.dataset.count, 10)]))""")
    assert page.locator('[data-testid="map-tiers"]').is_visible()
    for t in tiers:                        # 帯の見出しの (名称, 件数) が、パネルの木にも同じ件数である
        assert panel.get(json.dumps(t["path"], ensure_ascii=False, separators=(",", ":")), 0) >= t["count"] > 0, (t, panel)
    assert page.eval_on_selector("canvas.fill", "c => c.dataset.headingsAlt") in ("panel", "canvas")
    page.context.close()

# ---- AC-352 の a11y 検査 ----

def _tree_report(page):
    return page.evaluate("""() => {
        const out = {dupIds: [], badControls: [], mismatch: [], headingsWithoutButton: [], badLevels: [], noName: []};
        const seen = new Set();
        for (const el of document.querySelectorAll('[id]')) { if (seen.has(el.id)) out.dupIds.push(el.id); seen.add(el.id); }
        for (const b of document.querySelectorAll('.tier-toggle')) {
            const id = b.getAttribute('aria-controls');
            if (!id || document.querySelectorAll('[id="' + CSS.escape(id) + '"]').length !== 1) out.badControls.push(id);
            const body = id && document.getElementById(id);
            const g = b.closest('[role=treeitem]');
            if (body && g && (body.parentElement !== g)) out.badControls.push('notchild:' + id);
            if (g && g.getAttribute('aria-expanded') !== b.getAttribute('aria-expanded')) out.mismatch.push(id);
            if (body && (body.hidden !== (b.getAttribute('aria-expanded') !== 'true'))) out.mismatch.push('hidden:' + id);
            if (!(b.getAttribute('aria-label') || b.textContent || '').trim()) out.noName.push(id);
            const h = b.parentElement;
            if (!h || h.getAttribute('role') !== 'heading' || !/^[2-9]$/.test(h.getAttribute('aria-level') || '')) out.badLevels.push(id);
            if (h && h.children.length !== 1) out.headingsWithoutButton.push(id);
        }
        for (const t of document.querySelectorAll('[role=tree]')) {
            if (!t.getAttribute('aria-label')) out.noName.push('tree');
        }
        return out;
    }""")


# FR-1063 AC-352: aria-controls の参照先が実在・一意で、aria-expanded と本体の hidden が一致し、見出しの入れ子が妥当（heading > button、レベルが深さ順）
@pytest.mark.parametrize("route", ["tables?tab=reqs", "implstatus", "dashboard", "map2d", "map3d"])
def test_ac352_aria_references_are_valid_and_unique(studio, route):
    page = _page(studio, route, 1280, 800)
    page.wait_for_selector(GROUP)
    # すべて開いてから検査する（畳んだ層も参照先が実在する）
    for _ in range(4):
        for b in page.locator('.tier-toggle[aria-expanded="false"]').all():
            if b.is_visible():
                b.click()
    rep = _tree_report(page)
    assert all(v == [] for v in rep.values()), rep
    page.context.close()


# FR-1063 AC-352: 見出しのレベルは親より深く（親+1）、tree の中に treeitem 以外の直下要素がない
def test_ac352_heading_levels_nest_by_depth_and_tree_children_are_treeitems(studio):
    page = _page(studio, "tables?tab=reqs", 1280, 800)
    page.wait_for_selector(GROUP)
    for b in page.locator('.tier-toggle[aria-expanded="false"]').all():
        b.click()
    bad = page.evaluate("""() => {
        const bad = [];
        for (const g of document.querySelectorAll('#view .tier-group')) {
            const lv = +g.querySelector(':scope > .tier-head').getAttribute('aria-level');
            const p = g.parentElement.closest('.tier-group');
            const plv = p ? +p.querySelector(':scope > .tier-head').getAttribute('aria-level') : 1;
            if (lv !== plv + 1) bad.push(g.dataset.tierPath);
        }
        for (const t of document.querySelectorAll('#view [role=tree]'))
            for (const c of t.children) if (c.getAttribute('role') !== 'treeitem') bad.push('child:' + c.className);
        return bad;
    }""")
    assert bad == []
    page.context.close()


# FR-1063 AC-352: キーボードだけで開閉でき（Enter / Space / → / ←）、フォーカスが見出しに残る
def test_ac352_keyboard_opens_and_closes_with_arrows_and_space(studio):
    page = _page(studio, "tables?tab=reqs", 1280, 800)
    page.wait_for_selector(GROUP)
    t = page.locator(f'{GROUP} [data-testid="tier-toggle"]').first
    t.focus()
    if t.get_attribute("aria-expanded") == "true":
        page.keyboard.press("ArrowLeft")
    assert t.get_attribute("aria-expanded") == "false"
    page.keyboard.press("ArrowRight")
    assert t.get_attribute("aria-expanded") == "true"
    page.keyboard.press("Space")
    assert t.get_attribute("aria-expanded") == "false"
    assert page.evaluate("() => document.activeElement.classList.contains('tier-toggle')")
    page.context.close()


# FR-1063 AC-352: 層の id（aria-controls の参照先）が renderTiers の複数回の呼び出し（同じミリ秒を含む）でも重複しない
def test_ac352_tier_ids_are_unique_across_renderTiers_calls_in_same_millisecond(studio):
    page = _page(studio, "tables?tab=reqs", 1280, 800)
    page.wait_for_selector(GROUP)
    res = page.evaluate("""async () => {
        const m = await import('/js/hier.js');
        const hier = window.eabkStore && window.eabkStore.model ? window.eabkStore.model.hierarchy : null;
        const sample = hier || {nodes: []};
        const realNow = Date.now; Date.now = () => 1700000000000;
        try {
            const a = m.renderTiers(sample), b = m.renderTiers(sample);
            const ids = [...a.querySelectorAll('.tier-body'), ...b.querySelectorAll('.tier-body')].map(e => e.id);
            return {n: ids.length, uniq: new Set(ids).size};
        } finally { Date.now = realNow; }
    }""")
    assert res["n"] == res["uniq"]
    page.context.close()


# ---- AC-350: 全画面で上位層の名称・順序・件数が FR-1062 の導出（/api/model の hierarchy）と一致 ----

def _derived_requirement_areas(page, base):
    h = page.evaluate("async (u) => (await (await fetch(u + '/api/model')).json()).hierarchy", base)
    return [(tuple(t["path"]), t["count"]) for t in h["tiers"] if t["path"][0] == "要求"]


def _screen_routes(page):
    hrefs = page.evaluate("""() => [...document.querySelectorAll('#nav a[href^="#/"]')]
        .filter(a => !a.hasAttribute('data-no-items')).map(a => a.getAttribute('href').slice(2))""")
    return sorted(set(hrefs))


def _req_areas_on_screen(page):
    return page.evaluate("""() => [...document.querySelectorAll('[data-testid="tier-group"][data-tier-level="area"]')]
        .map(g => [JSON.parse(g.dataset.tierPath), parseInt(g.dataset.count, 10), parseInt(g.dataset.shown ?? g.dataset.count, 10), g.innerText])
        .filter(([p]) => p[0] === '要求')""")


# FR-1063 AC-350: ナビ全 route と マップ 3D・RPG 風で、要求の上位層（領域）の名称・順序・件数が、導出（FR-1062）と一致する。
# 画面が項目を絞るときは、見出しの件数は導出の件数のままで、絞り込み後の件数（data-shown・「表示 n 件」）が別に示される。
def test_ac350_every_screen_matches_the_derivation_in_names_order_and_counts(studio):
    browser, url = studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_load_state("networkidle")
    derived = _derived_requirement_areas(page, url)
    assert derived
    routes = _screen_routes(page)
    seen = 0
    for r in routes + ["map3d"]:
        page.goto(f"{url}/#/{r}")
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_selector(GROUP, timeout=4000)
        except sync_api.TimeoutError:
            continue
        areas = _req_areas_on_screen(page)
        if not areas:
            continue
        seen += 1
        got = [(tuple(p), c) for p, c, _s, _t in areas]
        assert got == derived, f"{r}: 要求の上位層が導出と違う"
        for p, c, s, text in areas:
            assert s <= c
            if s != c:                                     # 絞り込み後の件数を、導出の件数と並べて見せる
                assert str(s) in text and str(c) in text
    assert seen >= 4
    # RPG 風: 会話ウィンドウの項目の上位層
    page.goto(f"{url}/#/maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.evaluate("() => window.eabkView.openTierDialog()")
    page.locator('[data-testid="rpg-dialog"]').wait_for()
    got = [(tuple(p), c) for p, c, _s, _t in _req_areas_on_screen(page)]
    assert got == derived
    page.context.close()


# FR-1063 AC-350: 絞り込みで 0 件になった層も、名称・順序・件数つきで残る（他の画面と同じ構成）
def test_ac350_tiers_emptied_by_a_screen_filter_stay_with_derived_count(studio):
    browser, url = studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(f"{url}/#/implstatus")
    page.wait_for_load_state("networkidle")
    derived = _derived_requirement_areas(page, url)
    areas = _req_areas_on_screen(page)
    assert [(tuple(p), c) for p, c, _s, _t in areas] == derived
    assert sum(s for _p, _c, s, _t in areas) <= sum(c for _p, c, _s, _t in areas)
    page.context.close()