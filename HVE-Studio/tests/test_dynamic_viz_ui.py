"""FR-1080 / NFR-UX-018: 動的な可視化の小部品（js/viz.js）を、Graph・マップ 2D・図式以外の可視化要素（ダッシュボード・表・実装状態・インサイト）で確かめる。
AC-445 / AC-447 は検証レベル integration なので、system test（tests/system/e2e/test_studio_dynamic_viz_system.py）から移して置く。
Run: python -m pytest EABK-Studio/tests/test_dynamic_viz_ui.py -q
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: E402,F401

WEB = Path(__file__).resolve().parents[1] / "web"
P058 = 600
STATES = {"idle", "enter", "update", "exit"}
ROUTES = ["dashboard", "tables?tab=reqs", "implstatus", "placement?kind=runtime", "diagrams?kind=er"]
ROW = 'tr[data-testid="tier-item"]'


def _settled(page, sel="[data-viz]", timeout=4000):
    page.wait_for_function("(s) => [...document.querySelectorAll(s)].every(e => e.dataset.vizTransition === 'settled')", arg=sel, timeout=timeout)


def _search(page, q):
    page.evaluate("(q) => { const i = document.querySelector('.tbar input[type=search]'); i.value = q; i.dispatchEvent(new Event('input', {bubbles: true})); }", q)


# FR-1080 AC-438: 各ルート要素が data-viz / data-viz-state / data-viz-count を公開し、同じキーの要素は再利用され、消える要素は exit の後に取り除かれる。
def test_ac438_roots_expose_viz_and_keyed_join_reuses_elements(studio):
    for route in ROUTES:
        page = _open(studio, route)
        page.wait_for_selector("[data-viz]")
        roots = page.evaluate("() => [...document.querySelectorAll('[data-viz]')].map(e => [e.dataset.viz, e.dataset.vizState, e.dataset.vizCount])")
        assert roots and all(n and s in STATES and c is not None for n, s, c in roots), (route, roots)
        page.context.close()
    page = _open(studio, "tables?tab=reqs")
    page.wait_for_selector(ROW)
    ids = page.evaluate(f"() => [...document.querySelectorAll('{ROW}')].map(r => r.dataset.id)")
    assert len(ids) >= 3
    page.evaluate(f"() => {{ const r = document.querySelector('{ROW}'); r.__keep = 'same'; window.__first = r.dataset.id; }}")
    _search(page, page.evaluate("() => window.__first"))
    page.wait_for_function(f"() => document.querySelectorAll('{ROW}').length < {len(ids)}")
    _settled(page)
    assert page.evaluate(f"() => document.querySelector('{ROW}').__keep") == "same"  # update: DOM 要素の再利用
    assert page.locator('[data-viz-state="exit"]').count() == 0 and page.locator("[data-viz-ghost]").count() == 0
    assert int(page.locator('[data-viz="tables"]').get_attribute("data-viz-count")) == page.locator(ROW).count()
    _search(page, "")  # 戻すと元の件数
    page.wait_for_function(f"() => document.querySelectorAll('{ROW}').length === {len(ids)}")
    page.context.close()


# FR-1080 AC-439: 変化は PARAM-058 以内に running → settled。最終状態は補間なしと同じ。
def test_ac439_transition_runs_then_settles_with_final_state_equal_to_plain(studio):
    page = _open(studio, "tables?tab=reqs")
    page.wait_for_selector(ROW)
    total = page.locator(ROW).count()
    page.evaluate("() => { window.__seen = []; new MutationObserver(() => window.__seen.push(document.querySelector('[data-viz=tables]').dataset.vizTransition)).observe(document.querySelector('[data-viz=tables]'), {attributes: true, attributeFilter: ['data-viz-transition']}); }")
    _search(page, "FR-")
    page.wait_for_function("() => window.__seen.length > 0", timeout=2000)
    t0 = page.evaluate("() => performance.now()")
    _settled(page, timeout=P058 + 2000)
    assert page.evaluate("() => performance.now()") - t0 <= P058 + 500
    assert page.evaluate("() => window.__seen.includes('running')") or page.locator(ROW).count() == total
    animated = page.evaluate(f"() => [...document.querySelectorAll('{ROW}')].map(r => r.dataset.id + '|' + r.innerText)")
    page.context.close()
    p2 = _open(studio, "tables?tab=reqs")
    p2.wait_for_selector(ROW)
    _search(p2, "FR-")
    _settled(p2)
    plain = p2.evaluate(f"() => [...document.querySelectorAll('{ROW}')].map(r => r.dataset.id + '|' + r.innerText)")
    assert animated == plain
    p2.context.close()


# FR-1080 AC-440: ホバー・フォーカスで強調（data-hover）、減光、role=tooltip、離れる・Esc で消える。
def test_ac440_hover_focus_highlight_dim_and_tooltip(studio):
    page = _open(studio, "dashboard")
    segs = page.locator('[data-testid="chart-segment"]')
    page.wait_for_selector('[data-testid="chart-segment"]')
    first = segs.first
    first.hover()
    page.wait_for_selector('[role="tooltip"]:not([hidden])')
    assert first.get_attribute("data-hover") == "true"
    assert page.locator('[role="tooltip"]:not([hidden])').first.inner_text().strip() == first.get_attribute("aria-label")
    assert page.locator('[data-dim="true"]').count() >= 1
    page.mouse.move(1, 1)
    page.wait_for_function("() => !document.querySelector('[role=tooltip]:not([hidden])')")
    assert page.locator('[data-hover="true"]').count() == 0
    first.focus()  # キーボード
    page.wait_for_selector('[role="tooltip"]:not([hidden])')
    assert first.get_attribute("data-hover") == "true"
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('[role=tooltip]:not([hidden])')")
    assert page.locator('[data-hover="true"]').count() == 0
    page.context.close()


# FR-1080 AC-444: 動きの軽減では全対象が data-reduced-motion=true、補間なしの即時切替、情報は同一。
def test_ac444_reduced_motion_flags_and_instant_switch(studio):
    browser, url = studio
    for route in ROUTES:
        ctx = browser.new_context(reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(f"{url}/#/{route}")
        page.wait_for_selector("[data-viz]")
        flags = page.evaluate("() => [...document.querySelectorAll('[data-viz]')].map(e => e.dataset.reducedMotion)")
        assert flags and set(flags) == {"true"}, (route, flags)
        if route.startswith("tables"):
            page.wait_for_selector(ROW)
            _search(page, "FR-")
            page.wait_for_function("() => document.querySelector('[data-viz=tables]').dataset.vizTransition === 'settled'", timeout=1500)
            assert page.evaluate("() => document.getAnimations().length") == 0
            assert page.locator("[data-viz-ghost]").count() == 0
            assert int(page.locator('[data-viz="tables"]').get_attribute("data-viz-count")) == page.locator(ROW).count()
        ctx.close()


# NFR-UX-018 AC-445: d3 を同梱・追加せず、外部ネットワーク要求が 0 件。
def test_ac445_no_d3_no_new_dependency_no_external_requests(studio):
    files = [p for p in WEB.rglob("*") if p.is_file()]
    assert not [p for p in files if re.search(r"(^|[-_.])d3([-_.]|$)", p.name.lower())]
    assert not [p for p in files if p.name in {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bower.json", "importmap.json"}]
    for p in WEB.rglob("*.js"):
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
    page = _open(studio, "tables?tab=reqs")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.wait_for_selector(ROW)
    all_ids = sorted(page.evaluate(f"() => [...document.querySelectorAll('{ROW}')].map(r => r.dataset.id)"))
    for i in range(12):  # トランジションの完了を待たず連打する
        _search(page, ["FR-", "NFR", "AC-", "zzz", "FR-0", ""][i % 6])
    _search(page, "")  # 最後は「戻す」
    _settled(page, timeout=P058 + 5000)
    ids = page.evaluate(f"() => [...document.querySelectorAll('{ROW}')].map(r => r.dataset.id)")
    assert sorted(ids) == all_ids and len(ids) == len(set(ids))
    assert page.locator('[data-viz-state="exit"]').count() == 0 and page.locator("[data-viz-ghost]").count() == 0
    assert int(page.locator('[data-viz="tables"]').get_attribute("data-viz-count")) == len(ids)
    assert errors == []
    for _ in range(3):  # 連続の再読込
        page.reload()
    page.wait_for_selector(ROW)
    _settled(page, timeout=P058 + 5000)
    assert errors == []
    page.context.close()
