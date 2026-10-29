"""System tests for FR-1080 (AC-438..AC-444) and NFR-UX-018 (AC-445, AC-447) (run 202610300421).

期待値は要求定義書の受入基準だけから決める。AC-446 は manual（フレームレートは人が測る）なのでここでは扱わない。
AC-445 / AC-447 は検証レベル=integration だが、test-designer が変更できるのは tests/system/ のみのため
（hook G-5）、test_studio_header_row_integration.py と同じ流儀でここに置く。実装者が EABK-Studio/tests へ移してよい。
パラメータ: PARAM-058=600ms（トランジション上限）、PARAM-037=1ms（動きの軽減時の切替上限）、PARAM-056=150（Graph の描画ノード数目安）。
Run: python -m pytest tests/system/e2e/test_studio_dynamic_viz_system.py -q
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "EABK-Studio" / "tests"))
from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: E402,F401

JS_DIR = REPO / "EABK-Studio" / "web" / "js"
P058 = 600
P037 = 1
VIZ_ROUTES = ["dashboard", "implstatus", "map2d", "diagrams", "mapgraph"]  # insights は dashboard / tables 内。ルートは下の ROOTS で確認
VIZ_MODULES = ["graph.js", "dashboard.js", "insights.js", "map2d.js", "diagrams.js", "implstatus.js"]
STATES = {"idle", "enter", "update", "exit"}
GRAPH = '[data-testid="graph-view"]'
NODE = '[data-testid="graph-node"]'
FILTER_BTN = '[data-testid="graph-filter"] button'


def _open_graph(studio, **kw):
    page = _open(studio, "map2d?dim=graph", **kw)
    page.wait_for_selector(GRAPH)
    return page


def _settle(page, sel=GRAPH, timeout=8000):
    page.wait_for_function("(s) => document.querySelector(s)?.dataset.vizTransition === 'settled'", arg=sel, timeout=timeout)


def _ids(page):
    return page.evaluate("() => [...document.querySelectorAll('[data-testid=\"graph-node\"]')].map(g => g.dataset.nodeId)")


def _reduced_context(studio):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"{url}/#/map2d?dim=graph")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(GRAPH)
    return page


# FR-1080 AC-438 AC-441: 全対象のルート要素が data-viz / data-viz-state を公開し、絞り込みで enter・update・exit と data-viz-count が合い、戻すと元に戻る。
def test_ac438_ac441_roots_expose_viz_and_filter_joins_by_key(studio):
    # 対象一覧は描画関数を持つ JS から導出（1 つも漏れない）。各モジュールが data-viz を公開する。
    for name in VIZ_MODULES:
        assert "data-viz" in (JS_DIR / name).read_text(encoding="utf-8"), f"{name} が data-viz を公開していない"
    for route in VIZ_ROUTES:
        page = _open(studio, route)
        page.wait_for_selector("[data-viz]")
        roots = page.evaluate("() => [...document.querySelectorAll('[data-viz]')].map(e => [e.dataset.viz, e.dataset.vizState])")
        assert roots and all(n and s in STATES for n, s in roots), (route, roots)
        page.context.close()
    page = _open_graph(studio)
    _settle(page)
    before = _ids(page)
    assert before and page.locator(GRAPH).get_attribute("data-viz") and int(page.locator(GRAPH).get_attribute("data-viz-count")) == len(before)
    first = page.locator(NODE).first
    first.evaluate("e => e.__keep = 'same'")
    btns = page.locator(FILTER_BTN)
    assert btns.count() >= 1
    btns.first.click()  # 種類で絞る（既存の絞り込み規則）
    _settle(page)
    after = _ids(page)
    assert set(after) < set(before) and len(after) < len(before)  # 該当しなくなった要素は取り除かれる（exit 後）
    assert page.locator('[data-viz-state="exit"]').count() == 0
    assert int(page.locator(GRAPH).get_attribute("data-viz-count")) == len(after)
    # キーが同じ要素は DOM 要素が再利用される（update）
    kept = page.locator(NODE).first.get_attribute("data-node-id")
    if kept == first.get_attribute("data-node-id"):
        assert first.evaluate("e => e.__keep") == "same"
    # フィルタを戻すと元の状態に戻る
    page.locator('[data-testid="graph-filter"] button').last.click()
    _settle(page)
    assert sorted(_ids(page)) == sorted(before)
    assert int(page.locator(GRAPH).get_attribute("data-viz-count")) == len(before)
    # 異常系: 存在しない種類（クエリ）でも例外・重複なし
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(page.url.split("#")[0] + "#/map2d?dim=graph&q=__no_such_id__")
    page.wait_for_load_state("networkidle")
    assert errors == []
    ids = _ids(page)
    assert len(ids) == len(set(ids))
    page.context.close()


# FR-1080 AC-439: 状態変化は PARAM-058 以内のトランジションで running → settled。最終状態はトランジションなしの描画と同一。
def test_ac439_transition_runs_then_settles_with_same_final_state(studio):
    page = _open_graph(studio)
    _settle(page)
    page.evaluate("""() => { window.__seen = []; new MutationObserver(() => window.__seen.push(document.querySelector('[data-testid=graph-view]').dataset.vizTransition))
        .observe(document.querySelector('[data-testid=graph-view]'), {attributes: true, attributeFilter: ['data-viz-transition']}); }""")
    page.locator(FILTER_BTN).first.click()
    page.wait_for_function("() => window.__seen.includes('running')", timeout=2000)
    t0 = page.evaluate("() => performance.now()")
    _settle(page, timeout=P058 + 2000)
    assert page.evaluate("() => performance.now()") - t0 <= P058 + 500
    animated = page.evaluate("() => [...document.querySelectorAll('[data-testid=graph-node]')].map(g => [g.dataset.nodeId, g.getAttribute('transform')])")
    # 動きなし（reduced-motion）で同じ操作をしたときの最終結果と一致する
    ref = _reduced_context(studio)
    ref.locator(FILTER_BTN).first.click()
    _settle(ref)
    plain = ref.evaluate("() => [...document.querySelectorAll('[data-testid=graph-node]')].map(g => [g.dataset.nodeId, g.getAttribute('transform')])")
    assert sorted(i for i, _ in animated) == sorted(i for i, _ in plain)
    page.context.close()
    ref.context.close()


# FR-1080 AC-440: ホバー・フォーカスで強調（data-hover）、他を減光、role=tooltip が名前と値を示し、離れる・Esc で消える。
def test_ac440_hover_and_focus_highlight_with_tooltip_that_closes(studio):
    page = _open_graph(studio)
    _settle(page)
    node = page.locator(NODE).first
    node.hover()
    page.wait_for_selector('[role="tooltip"]')
    assert node.get_attribute("data-hover") == "true"
    assert page.locator('[role="tooltip"]').first.inner_text().strip()
    assert page.locator('[data-hover="true"]').count() >= 1
    page.mouse.move(2, 2)
    page.wait_for_function("() => !document.querySelector('[role=tooltip]:not([hidden])')")
    assert page.locator('[data-hover="true"]').count() == 0
    node.focus()  # キーボード
    page.wait_for_selector('[role="tooltip"]')
    assert node.get_attribute("data-hover") == "true"
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('[role=tooltip]:not([hidden])')")
    # 他のルートのチャート要素（ダッシュボード）でも同じ
    d = _open(studio, "dashboard")
    seg = d.locator('[data-testid="chart-segment"]').first
    seg.hover()
    d.wait_for_selector('[role="tooltip"]')
    assert seg.get_attribute("data-hover") == "true"
    page.context.close()
    d.context.close()


# FR-1080 AC-442: ホイールで拡大縮小、ドラッグで移動、data-zoom / data-pan、リセットで初期、選択と絞り込みは保たれる。
@pytest.mark.parametrize("route", ["map2d?dim=graph", "map2d", "diagrams"])
def test_ac442_wheel_zoom_drag_pan_reset_keep_state(studio, route):
    page = _open(studio, route)
    host = page.locator("[data-zoom]").first
    host.wait_for(timeout=8000)
    z0, p0 = host.get_attribute("data-zoom"), host.get_attribute("data-pan")
    box = host.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.wheel(0, -400)
    page.wait_for_function("(z) => document.querySelector('[data-zoom]').dataset.zoom !== z", arg=z0)
    assert float(host.get_attribute("data-zoom")) > float(z0)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 80, cy + 60, steps=6)
    page.mouse.up()
    assert host.get_attribute("data-pan") != p0
    page.locator('[data-testid="viz-reset"], [data-action="reset-view"]').first.click()
    page.wait_for_function("([z, p]) => { const e = document.querySelector('[data-zoom]'); return e.dataset.zoom === z && e.dataset.pan === p; }", arg=[z0, p0])
    page.context.close()


def test_ac442_zoom_pan_keep_graph_selection_and_filter(studio):
    page = _open_graph(studio)
    _settle(page)
    page.locator(FILTER_BTN).first.click()
    _settle(page)
    shown = _ids(page)
    page.locator(NODE).first.click()
    sel = page.locator(f'{NODE}[aria-pressed="true"]').count()
    box = page.locator(GRAPH).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, -300)
    page.mouse.wheel(0, 150)
    assert _ids(page) == shown
    assert page.locator(f'{NODE}[aria-pressed="true"]').count() == sel
    assert page.locator(GRAPH).get_attribute("data-filtered") == "true"
    page.context.close()


# FR-1080 AC-443: force 風（data-layout=force、data-viz-alpha が収まり settled）、ドラッグで再加熱し、離すと収まる。
def test_ac443_graph_force_layout_cools_reheats_on_drag_and_settles(studio):
    page = _open_graph(studio)
    g = page.locator(GRAPH)
    assert g.get_attribute("data-layout") == "force"
    _settle(page, timeout=15000)
    assert float(g.get_attribute("data-viz-alpha")) < 0.05
    node = page.locator(NODE).first
    b = node.bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y + 40, steps=5)
    assert float(g.get_attribute("data-viz-alpha")) > 0.05  # 再加熱
    assert g.get_attribute("data-viz-transition") == "running"
    page.mouse.up()
    _settle(page, timeout=15000)
    page.context.close()


# FR-1080 AC-444: 動きの軽減では全対象が data-reduced-motion=true を公開し、即時（PARAM-037）に切り替わり、情報は同一。
def test_ac444_reduced_motion_switches_immediately_with_same_information(studio):
    page = _reduced_context(studio)
    g = page.locator(GRAPH)
    assert g.get_attribute("data-reduced-motion") == "true"
    _settle(page, timeout=2000)
    assert float(g.get_attribute("data-viz-alpha")) <= 0.05
    n_before = len(_ids(page))
    page.locator(FILTER_BTN).first.click()
    page.wait_for_function("() => document.querySelector('[data-testid=graph-view]').dataset.vizTransition === 'settled'", timeout=P037 * 1000 + 500)
    assert int(g.get_attribute("data-viz-count")) == len(_ids(page)) < n_before
    page.locator(NODE).first.hover()
    page.wait_for_selector('[role="tooltip"]')
    assert page.locator('[role="tooltip"]').first.inner_text().strip()
    for route in VIZ_ROUTES:
        p = _open(studio, route)
        p.close()
    for route in VIZ_ROUTES:
        browser, url = studio
        ctx = browser.new_context(reduced_motion="reduce")
        p = ctx.new_page()
        p.goto(f"{url}/#/{route}")
        p.wait_for_selector("[data-viz]")
        flags = p.evaluate("() => [...document.querySelectorAll('[data-viz]')].map(e => e.dataset.reducedMotion)")
        assert flags and set(flags) == {"true"}, (route, flags)
        ctx.close()
    page.context.close()


# NFR-UX-018 AC-445: d3 を同梱・追加せず、外部ネットワーク要求が 0 件。
def test_ac445_no_d3_no_new_dependency_no_external_requests(studio):
    web = REPO / "EABK-Studio" / "web"
    files = [p for p in web.rglob("*") if p.is_file()]
    assert not [p for p in files if re.search(r"(^|[-_.])d3([-_.]|$)", p.name.lower())]
    assert not [p for p in files if p.name in {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bower.json", "importmap.json"}]
    for p in web.rglob("*.js"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"""from\s+['"]d3|require\(['"]d3|import\(['"]https?:""", text), p.name
    browser, url = studio
    for route in ["dashboard", "implstatus", "map2d", "mapgraph", "diagrams", "entities", "tables", "source"]:
        ctx = browser.new_context()
        page = ctx.new_page()
        external = []
        page.on("request", lambda r: external.append(r.url) if not r.url.startswith(url) and not r.url.startswith(("data:", "blob:", "about:")) else None)
        page.goto(f"{url}/#/{route}")
        page.wait_for_load_state("networkidle")
        assert external == [], (route, external)
        ctx.close()


# NFR-UX-018 AC-447: 変更中にさらに変更（連続の絞り込み・再読込）しても、中断して最新へ向かい、重複・exit の取り残し・例外がない。
def test_ac447_rapid_changes_interrupt_and_converge_without_duplicates_or_errors(studio):
    page = _open_graph(studio)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _settle(page)
    all_ids = sorted(_ids(page))
    btns = page.locator(FILTER_BTN)
    n = btns.count()
    for i in range(12):  # トランジションの完了を待たず連打する
        page.locator(FILTER_BTN).nth(i % max(n, 1)).click()
    page.locator(FILTER_BTN).last.click()  # 最後は「戻す」
    _settle(page, timeout=P058 + 5000)
    ids = _ids(page)
    assert len(ids) == len(set(ids))
    assert page.locator('[data-viz-state="exit"]').count() == 0
    assert int(page.locator(GRAPH).get_attribute("data-viz-count")) == len(ids)
    assert errors == []
    page.reload()
    page.wait_for_selector(GRAPH)
    for _ in range(3):
        page.reload()
    page.wait_for_selector(GRAPH)
    _settle(page, timeout=P058 + 5000)
    assert sorted(_ids(page)) == all_ids or len(_ids(page)) == len(set(_ids(page)))
    assert errors == []
    page.context.close()
