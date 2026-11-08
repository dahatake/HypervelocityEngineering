"""Integration tests for FR-1079 (Graph display mode) and FR-1066 (header switch has Graph).
Run: python -m pytest EABK-Studio/tests/test_graph_mode_ui.py -q"""
import socket
import subprocess
import sys
import time

import pytest

from test_links_wrap_status_ui import ROOT, studio, _open, sync_api  # noqa: F401
from entity_repo import make_large

HDR = '[data-testid="header-dim-toggle"]'
GRAPH = '[data-testid="graph-view"]'
NODE = '[data-testid="graph-node"]'
JS = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "web" / "js").glob("*.js")}


def _xs(page):
    return page.evaluate("""() => [...document.querySelectorAll('[data-testid="graph-node"]')].map(g => {
        const m = /translate\\(([-\\d.]+) ([-\\d.]+)\\)/.exec(g.getAttribute('transform')); return {id: g.dataset.nodeId, type: g.dataset.type, x: +m[1], y: +m[2]}; })""")


def _open_graph(studio, route, lang=None):
    page = _open(studio, route, lang=lang)
    page.locator(f'{HDR} [data-dim="graph"]').click()
    page.wait_for_selector(GRAPH)
    return page


# FR-1066 AC-367 AC-368 AC-369: four buttons with words, Graph has an icon, a label and a reason where unavailable (JA and EN).
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac369_header_has_graph_button_with_word_label_icon_and_reason(studio, lang):
    page = _open(studio, "tables", lang=lang)
    b = page.locator(f'{HDR} [data-dim="graph"]')
    assert "GRAPH" in b.inner_text().upper() and b.get_attribute("aria-label") and b.locator("svg").count() == 1
    assert b.is_disabled() and b.get_attribute("data-reason")
    assert page.locator(HDR).get_attribute("data-current") == "2d"
    page.context.close()


# FR-1079 AC-425: the map has a Graph route that is the same map item, and ?dim=graph reaches it.
def test_ac425_map_graph_route_alias_and_nav_stay_consistent(studio):
    page = _open(studio, "map2d?dim=graph")
    page.wait_for_selector(GRAPH)
    assert page.evaluate("() => location.hash").startswith("#/mapgraph")
    assert page.locator(HDR).get_attribute("data-current") == "graph"
    assert page.locator('#nav a[data-nav="map"]').get_attribute("aria-current") == "page"
    page.locator(f'{HDR} [data-dim="2d"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.current === '2d'")
    assert page.locator(f"{GRAPH}:visible").count() == 0
    page.context.close()


# FR-1079 AC-425: the command box has a Graph command; layers / ctx do not offer Graph.
def test_ac425_command_box_switches_to_graph_and_layers_disable_it(studio):
    page = _open(studio, "map2d")
    page.locator("#q").fill(">Graph")
    page.locator("#q").press("Enter")
    page.wait_for_selector(GRAPH)
    page.close()
    for r in ("diagrams?kind=layers", "diagrams?kind=ctx"):
        p = _open(studio, r)
        b = p.locator(f'{HDR} [data-dim="graph"]')
        assert b.is_disabled() and b.get_attribute("data-reason")
        p.context.close()


# FR-1079 AC-426: the trace graph goes goal → requirement → AC (→ System Test) left to right; each node has an icon and ID + title words.
def test_ac426_map_graph_is_layered_left_to_right_with_icons_and_words(studio):
    page = _open_graph(studio, "map2d")
    nodes = _xs(page)
    assert nodes and {"req", "ac"} <= {n["type"] for n in nodes}
    x = {}
    for n in nodes:
        x.setdefault(n["type"], set()).add(n["x"])
    order = [t for t in ("goal", "req", "ac", "case") if t in x]
    for a, b in zip(order, order[1:]):
        assert max(x[a]) < min(x[b]), (a, b, x)
    for edge in page.locator('[data-testid="graph-edge"]').evaluate_all("els => els.map(e => [e.dataset.from, e.dataset.to, e.getAttribute('marker-end')])"):
        assert edge[2].startswith("url(#")
    first = page.locator(NODE).first
    assert first.locator("svg").count() == 1 and first.locator("text.gv-id").text_content().strip()
    assert first.get_attribute("aria-label").split()[0]   # the kind word comes first, so same-shaped nodes differ by words too
    kinds = {n.get_attribute("aria-label").split()[0] for n in page.locator(NODE).all()}
    assert len(kinds) >= 2
    page.context.close()


# FR-1079 AC-427: click and Tab + Enter select through the store (the drawer opens), the selected node is emphasised, Tab goes in reading order.
def test_ac427_select_by_click_and_keyboard_opens_drawer_and_emphasises(studio):
    page = _open_graph(studio, "map2d")
    nodes = page.locator(NODE)
    ids = [n["id"] for n in _xs(page)]
    assert ids == [g.get_attribute("data-node-id") for g in nodes.all()]          # DOM (= Tab) order is the reading order
    xs = [n["x"] for n in _xs(page)]
    assert xs == sorted(xs)
    assert all(g.get_attribute("tabindex") == "0" and g.get_attribute("role") == "button" for g in nodes.all())
    nodes.nth(1).click()
    page.wait_for_selector("#drawer:not([hidden])")
    assert page.locator(f'{NODE}[aria-pressed="true"]').count() == 1
    target = ids[0]
    page.locator(f'{NODE}[data-node-id="{target}"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_function("(id) => document.querySelector('.gv-node.sel')?.dataset.nodeId === id", arg=target)
    page.keyboard.press("Tab")
    page.context.close()


# FR-1079 AC-428: JA and EN, dark and light, no external fetch, nothing animated under reduced motion.
@pytest.mark.parametrize("lang", [None, "en"])
@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_ac428_both_languages_and_themes_without_outside_requests(studio, lang, scheme):
    browser, url = studio
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, color_scheme=scheme, reduced_motion="reduce")
    page = ctx.new_page()
    outside = []
    page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(url) and not r.url.startswith("data:") and not r.url.startswith("blob:") else None)
    if lang == "en":
        page.goto(url)
        page.evaluate("() => localStorage.setItem('eabk-studio.lang','en')")
        page.reload()
    page.goto(f"{url}/#/mapgraph")
    page.reload()
    page.wait_for_selector(GRAPH)
    assert outside == []
    legend = page.locator(".gv-legend").inner_text()
    assert ("Goal" in legend or "Functional" in legend) if lang == "en" else ("要求" in legend or "目的" in legend)
    g = page.locator(NODE).first
    assert g.locator("svg.gv-ico").evaluate("e => getComputedStyle(e).stroke") != "none"
    contrast = page.evaluate("""() => { const c = s => { const m = s.match(/[\\d.]+/g).map(Number); return m.slice(0, 3).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); };
        const L = a => .2126 * a[0] + .7152 * a[1] + .0722 * a[2]; const e = document.querySelector('.gv-edge'), s = document.querySelector('.gv-scroll');
        const a = L(c(getComputedStyle(e).stroke)), b = L(c(getComputedStyle(s).backgroundColor)); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); }""")
    assert contrast >= 3, contrast       # the edge is readable against the canvas (WCAG 1.4.11)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.gv-node')).animationName") == "none"
    ctx.close()


# FR-1079 AC-428: the Graph icon and the node icons come from the bundled set; the force layout is deterministic and does not move.
def test_ac428_layouts_are_deterministic_and_icons_are_bundled(studio):
    page = _open(studio, "tables")
    out = page.evaluate("""async () => {
        const g = await import('/js/graph.js');
        const nodes = Array.from({length: 40}, (_, i) => ({id: 'N' + i, type: 'entity'}));
        const edges = nodes.slice(1).map((n, i) => ({from: 'N' + Math.floor(i / 2), to: n.id}));
        const a = JSON.stringify([...g.forceLayout(nodes, edges).pos]), b = JSON.stringify([...g.forceLayout(nodes, edges).pos]);
        const l = g.layeredLayout(nodes, edges);
        const cyc = g.layeredLayout([{id: 'a'}, {id: 'b'}], [{from: 'a', to: 'b'}, {from: 'b', to: 'a'}]);
        return {same: a === b, layers: l.layers, root: l.pos.get('N0').x, leaf: l.pos.get('N39').x, cyc: cyc.layers};
    }""")
    assert out["same"] and out["layers"] >= 4 and out["leaf"] > out["root"] and out["cyc"] == 2   # cycles do not hang
    assert "fetch(" not in JS["graph.js"] and "http" not in JS["graph.js"] and "import(" not in JS["graph.js"]
    for k in ("graph:", "ac:", "state:", "component:"):
        assert k in JS["ui.js"]
    page.context.close()


@pytest.fixture(scope="module")
def big(tmp_path_factory, studio):
    repo = make_large(tmp_path_factory.mktemp("big") / "r", entities=300, columns=600)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield studio[0], f"http://127.0.0.1:{port}"
    proc.terminate()


# FR-1079 AC-429: over PARAM-056 (150 nodes) the narrowing is the neighbourhood or a type, and the selected node never disappears.
def test_ac429_narrow_function_rules(studio):
    page = _open(studio, "tables")
    out = page.evaluate("""async () => {
        const g = await import('/js/graph.js');
        const nodes = [], edges = [];
        for (let i = 0; i < 100; i++) nodes.push({id: 'R' + i, type: 'req'});
        for (let i = 0; i < 120; i++) { nodes.push({id: 'A' + i, type: 'ac'}); edges.push({from: 'R' + (i % 100), to: 'A' + i}); }
        const near = g.narrow(nodes, edges, {selected: 'R5'});
        const typed = g.narrow(nodes, edges, {selected: 'A119', mode: 'type', type: 'req'});
        const small = g.narrow(nodes.slice(0, 150), edges, {});
        return {cap: g.GRAPH_CAP, near: [near.mode, near.nodes.length, near.nodes.some(x => x.id === 'R5')],
                typed: [typed.mode, typed.nodes.length, typed.nodes.some(x => x.id === 'A119')], small: [small.mode, small.nodes.length]};
    }""")
    assert out["cap"] == 150
    assert out["near"] == ["near", 3, True]     # R5 and the two ACs that hang on it
    assert out["typed"] == ["type", 101, True]     # the 100 requirements plus the selected node, which never disappears
    assert out["small"] == [None, 150]
    page.context.close()


def test_ac429_large_map_graph_is_narrowed_with_reason_total_and_keeps_selection(big):
    browser, url = big
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"{url}/#/mapgraph")
    page.wait_for_selector(GRAPH)
    assert int(page.locator(GRAPH).get_attribute("data-total")) > 150
    assert page.locator(GRAPH).get_attribute("data-filtered") == "true"
    assert page.locator(NODE).count() <= 150
    note = page.locator('[data-testid="graph-filter"]').inner_text()
    assert page.locator(GRAPH).get_attribute("data-total") in note and "150" in note
    chips = page.locator("[data-filter-type]")
    assert chips.count() >= 2
    chips.nth(1).click()
    page.wait_for_selector(f'{GRAPH}[data-filtered="true"]')
    first = page.locator(NODE).first
    sid = first.get_attribute("data-node-id")
    first.click()
    page.wait_for_selector("#drawer:not([hidden])")
    assert page.locator(f'{NODE}[data-node-id="{sid}"][aria-pressed="true"]').count() == 1
    assert page.locator('[data-testid="graph-filter"]').count() == 1          # still narrowed
    assert page.locator("[data-filter-type][aria-pressed=\"true\"]").count() == 1   # and the chosen narrowing is kept
    page.context.close()


# Wiring: Graph is a header mode, the map route and command exist, and Graph is not a semantic-zoom mode.
def test_graph_wiring():
    assert "'graph'" in JS["dim.js"] and "hdim.reason.graph" in JS["dim.js"]
    assert "mapgraph" in JS["app.js"] and "cmd.dim.graph" in JS["app.js"]
    assert "graphView" in JS["diagrams.js"] and "graphView" in JS["entities.js"] and "graphView" in JS["mapgraph.js"]
    for k in ("hdim.reason.graph", "graph.filter.note", "cmd.dim.graph"):
        assert JS["i18n.js"].count(f"'{k}'") == 2      # JA and EN
