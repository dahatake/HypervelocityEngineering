"""System E2E for FR-1011 (2D map node selection) and FR-1012 (placement diagram).

Expected values come only from docs/requirements-definition.md
(AC-077 / PARAM-009=12px, AC-080, AC-081).  The model oracle is /api/model;
the application is used only to find entry points (routes, drawer, tabs).
"""

import json
import re
import urllib.request

import pytest
from playwright.sync_api import expect

from test_studio_system import page, studio_url  # noqa: F401  (fixture reuse)

RADIUS = 12  # PARAM-009 (screen px)
TOL = 2


def _model(url):
    with urllib.request.urlopen(url + "/api/model") as r:
        return json.load(r)


def _node_ids(url):
    return {n["id"] for n in _model(url)["graph"]["nodes"]}


def _selected(page, ids):
    """Model ID of the selected node, read from the drawer heading
    (type label + ' · ' + ID).  Related IDs further down are ignored.
    Returns None when nothing is selected (drawer hidden/empty)."""
    sid = page.evaluate(
        "() => { const e = document.querySelector('#drawer:not([hidden]) .typ .mono');"
        " return e ? e.textContent.trim() : null; }")
    return sid if sid in ids else None


class _Map:
    def __init__(self, page, ids):
        self.page, self.ids = page, ids
        self.box = page.locator("canvas.fill").bounding_box()

    def on_canvas(self, x, y):
        """True only when the canvas itself is the topmost element at the point
        (toolbar, minimap, status, hints, persona band etc. overlay it)."""
        return self.page.evaluate(
            "([x, y]) => { const c = document.querySelector('canvas.fill');"
            " return document.elementFromPoint(x, y) === c; }",
            [self.box["x"] + x, self.box["y"] + y])

    def click(self, x, y):
        """Click only points where the canvas is topmost; otherwise do nothing."""
        if not self.on_canvas(x, y):
            return None
        self.page.mouse.click(self.box["x"] + x, self.box["y"] + y)
        return _selected(self.page, self.ids)


def _find_two_nodes(m):
    """Sweep with coarse clicks; a selection change can only come from a hit."""
    w, h = m.box["width"], m.box["height"]
    anchor = None
    y = 20
    while y < h - 20:
        x = 20
        while x < w - 20:
            got = m.click(x, y)
            if got and anchor is None:
                anchor = (got, x, y)
            elif got and anchor and got != anchor[0]:
                if abs(x - anchor[1]) + abs(y - anchor[2]) > 60:
                    return anchor, (got, x, y)
            x += 14
        y += 14
    return anchor, None


def _chord(m, anchor, node, axis):
    """Extent (px) along one axis where a click selects `node` (anchor reset before each probe)."""
    _, ax, ay = anchor
    hits = []
    for d in range(-34, 35):
        pt = (node[1] + d, node[2]) if axis == "x" else (node[1], node[2] + d)
        m.click(ax, ay)
        if m.click(*pt) == node[0]:
            hits.append(d)
    return (min(hits), max(hits)) if hits else None


VARIANTS = [
    ("default", 0, 1, None),
    ("zoom-out", -4, 1, None),
    ("zoom-in", 4, 1, None),
    ("css-ne-internal", 0, 2, "70%"),
]


# FR-1011 AC-077
@pytest.mark.parametrize("name,wheel,dpr,css_w", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_map2d_click_selects_node_within_fixed_px_radius(browser, studio_url, name, wheel, dpr, css_w):
    ctx = browser.new_context(viewport={"width": 1280, "height": 760}, device_scale_factor=dpr)
    page = ctx.new_page()
    try:
        page.goto(studio_url + "#/map2d")
        page.wait_for_load_state("networkidle")
        ids = _node_ids(studio_url)
        canvas = page.locator("canvas.fill")
        expect(canvas).to_be_visible()
        if css_w:
            canvas.evaluate("(c, w) => { c.style.width = w; }", css_w)
        b = canvas.bounding_box()
        for _ in range(abs(wheel)):
            page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            page.mouse.wheel(0, 300 if wheel > 0 else -300)
            page.wait_for_timeout(120)
        page.wait_for_timeout(600)
        m = _Map(page, ids)
        anchor, node = _find_two_nodes(m)
        assert anchor and node, "could not locate two selectable nodes by clicking"
        for axis in ("x", "y"):
            ext = _chord(m, anchor, node, axis)
            assert ext, f"{axis}: node not hit"
            if axis == "x":
                # probe the y chord through the node's centre column, not the sweep's first-hit point
                node = (node[0], node[1] + (ext[0] + ext[1]) // 2, node[2])
            chord = ext[1] - ext[0] + 1
            # The radius is a fixed screen distance, independent of zoom / CSS size.
            assert chord <= 2 * RADIUS + 1 + TOL, f"{name} {axis}: hit width {chord}px exceeds {2 * RADIUS}px"
    finally:
        ctx.close()


# FR-1011 AC-077 (abnormal: clicks outside the radius leave the selection unchanged)
def test_map2d_click_outside_radius_keeps_selection(page, studio_url):
    page.goto(studio_url + "#/map2d")
    page.wait_for_load_state("networkidle")
    ids = _node_ids(studio_url)
    m = _Map(page, ids)
    anchor, _ = _find_two_nodes(m)
    assert anchor
    _, ax, ay = anchor
    assert m.click(ax, ay) == anchor[0]
    w, h = m.box["width"], m.box["height"]
    for dx, dy in ((3, 3), (w - 3, 3), (3, h - 3), (w - 3, h - 3)):
        m.click(dx, dy)
        assert _selected(page, ids) == anchor[0], "selection changed by a click outside the radius"


# ----------------------------------------------------------------- FR-1012

def _open_placement(page):
    page.goto(page.url.split("#")[0] + "#/diagrams")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=re.compile("実装配置図|Placement")).first.click()
    return page.locator(".dgm")


def _opacities(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('.dgm [data-id]')].map(n => ({
            id: n.dataset.id, o: parseFloat(getComputedStyle(n).opacity)}))"""
    )


# FR-1012 AC-080
def test_placement_diagram_shows_three_layers_and_only_model_assets(page, studio_url):
    body = _open_placement(page)
    model = _model(studio_url)
    ids = {n["id"] for n in model["graph"]["nodes"]}
    expect(body).to_contain_text("画面")
    expect(body).to_contain_text("API")
    expect(body).to_contain_text("データ")
    shown = body.locator("[data-id]").evaluate_all("els => els.map(e => e.dataset.id)")
    assert shown, "no assets drawn in the placement diagram"
    assert not [s for s in shown if s not in ids], "assets drawn that are not in the model"
    types = {n["id"]: n["type"] for n in model["graph"]["nodes"]}
    shown_types = {types[s] for s in shown}
    assert "api" in shown_types and ({"table"} & shown_types or {"entity"} & shown_types)
    lines = body.locator("[data-a][data-b]").evaluate_all("els => els.map(e => [e.dataset.a, e.dataset.b])")
    assert lines, "no lines connecting layers"
    assert not [l for l in lines if l[0] not in ids or l[1] not in ids], "line to a non-model target"


# FR-1012 AC-080 (abnormal: re-rendering must not invent relations)
def test_placement_diagram_does_not_invent_relations_on_rerender(page):
    body = _open_placement(page)
    js = "els => els.map(e => e.dataset.a + '|' + e.dataset.b).sort()"
    first = body.locator("[data-a][data-b]").evaluate_all(js)
    page.get_by_role("button", name=re.compile("コンテキスト図|Context")).first.click()
    page.get_by_role("button", name=re.compile("実装配置図|Placement")).first.click()
    second = body.locator("[data-a][data-b]").evaluate_all(js)
    assert first == second


# FR-1012 AC-081
def test_placement_click_highlights_related_dims_others_and_clears(page):
    body = _open_placement(page)
    target = body.locator("[data-id]").first
    tid = target.get_attribute("data-id")
    assert len({round(o["o"], 2) for o in _opacities(page)}) == 1, "normal view must not dim anything"
    target.click()
    after = {o["id"]: o["o"] for o in _opacities(page)}
    assert after[tid] >= 0.99
    assert min(after.values()) < 0.5, "unrelated targets must be weakened"
    assert any(v >= 0.99 for k, v in after.items() if k != tid), "related assets must stay emphasized"
    page.keyboard.press("Escape")
    assert len({round(o["o"], 2) for o in _opacities(page)}) == 1, "deselect must return to normal view"


# FR-1012 AC-081 (non-click: keyboard and mapping-table row)
def test_placement_selectable_by_keyboard_and_table_row(page):
    body = _open_placement(page)
    focusable = body.locator("[data-id][tabindex], button[data-id], a[data-id]")
    assert focusable.count() > 0, "assets are not keyboard focusable"
    focusable.first.focus()
    page.keyboard.press("Enter")
    assert min(o["o"] for o in _opacities(page)) < 0.5
    page.keyboard.press("Escape")
    row = body.locator("table tbody tr").first
    expect(row).to_be_visible()
    row.click()
    assert min(o["o"] for o in _opacities(page)) < 0.5, "selecting a table row must highlight the same target"
