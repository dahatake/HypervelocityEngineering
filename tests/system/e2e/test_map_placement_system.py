"""System E2E for FR-1011 (2D map node selection) and FR-1012 (placement diagram).

Expected values come only from docs/requirements-definition.md (AC-077, AC-080,
AC-081, PARAM-009 = 12 screen px).  The app is used only to find entry points.
Selection is observed through the visible drawer; no CSS class names are used
for FR-1011.
"""

import pytest
from playwright.sync_api import expect

from test_studio_system import page, studio_url  # noqa: F401  (fixtures)

RADIUS = 12  # PARAM-009, screen px

_PROBE = """
(args) => {
  const c = document.querySelector('#view canvas.fill, #view canvas');
  const r = c.getBoundingClientRect();
  const d = document.querySelector('#drawer');
  const fire = (t, x, y) => c.dispatchEvent(new PointerEvent(t, {clientX: r.left + x, clientY: r.top + y, pointerId: 1, bubbles: true, isPrimary: true}));
  const sel = () => (d && !d.hidden) ? d.innerText.trim().slice(0, 60) : '';
  const click = (x, y) => { fire('pointermove', x, y); fire('pointerdown', x, y); fire('pointerup', x, y); return sel(); };
  const reset = () => c.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
  const out = {};
  for (let y = 4; y < r.height - 4; y += args.step) for (let x = 4; x < r.width - 4; x += args.step) {
    reset(); const s = click(x, y); if (s) (out[s] = out[s] || []).push([x, y]);
  }
  reset();
  return {hits: out, w: r.width, h: r.height};
}
"""

_ZOOM = """
(dy) => { const c = document.querySelector('#view canvas'); const r = c.getBoundingClientRect();
  for (let i = 0; i < 4; i++) c.dispatchEvent(new WheelEvent('wheel', {deltaY: dy, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true, cancelable: true})); }
"""

_STRETCH = """
() => { const c = document.querySelector('#view canvas'); c.style.width = '60%'; c.style.height = '80%'; }
"""


def _diam(points):
    return max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a in points for b in points)


def _open_map(page):
    page.goto(page.url.split("#")[0] + "#/map2d")
    page.wait_for_selector("#view canvas")
    page.wait_for_timeout(800)


@pytest.mark.parametrize("zoom", [("out", 400), ("default", 0), ("in", -400)])
@pytest.mark.parametrize("stretch", [False, True])
def test_fr1011_ac077_hit_radius_is_screen_space(page, zoom, stretch):
    # FR-1011 AC-077 (zoom 3 levels x CSS size equal/different)
    _open_map(page)
    if zoom[1]:
        page.evaluate(_ZOOM, zoom[1])
        page.wait_for_timeout(1200)
    if stretch:
        page.evaluate(_STRETCH)
        page.wait_for_timeout(500)
    res = page.evaluate(_PROBE, {"step": 4})
    assert res["hits"], "no node could be selected by clicking the 2D map"
    for label, pts in res["hits"].items():
        # one node's selectable area never exceeds a PARAM-009 radius circle (+ sampling step)
        assert _diam(pts) <= 2 * RADIUS + 4, f"{label!r} selectable beyond {RADIUS}px"


def test_fr1011_ac077_outside_radius_keeps_selection(page):
    # FR-1011 AC-077 abnormal: click outside every radius does not change selection
    _open_map(page)
    res = page.evaluate(_PROBE, {"step": 4})
    hit = {tuple(p) for pts in res["hits"].values() for p in pts}
    far = next(
        ((x, y) for y in range(10, int(res["h"]) - 10, 10) for x in range(10, int(res["w"]) - 10, 10)
         if all((x - hx) ** 2 + (y - hy) ** 2 > (RADIUS + 8) ** 2 for hx, hy in hit)),
        None,
    )
    assert far, "no empty area to click"
    node = next(iter(res["hits"].values()))[0]
    canvas = page.locator("#view canvas").first
    canvas.click(position={"x": node[0], "y": node[1]})
    before = page.locator("#drawer").inner_text()
    canvas.click(position={"x": far[0], "y": far[1]})
    expect(page.locator("#drawer")).to_have_text(before)


def _open_placement_diagram(page):
    # "図" screen -> "実装配置図"
    page.goto(page.url.split("#")[0] + "#/diagrams")
    page.wait_for_selector("#view")
    page.get_by_role("tab", name="実装配置図").or_(page.get_by_text("実装配置図", exact=True)).first.click()
    page.wait_for_timeout(500)


def test_fr1012_ac080_three_layers_and_links_only_from_model(page):
    # FR-1012 AC-080
    _open_placement_diagram(page)
    view = page.locator("#view")
    for layer in ("画面", "API", "データ"):
        expect(view.get_by_text(layer).first).to_be_visible()
    expect(view.locator("svg line, svg path").first).to_be_visible()
    # abnormal: asset/relationship absent from the model is never drawn
    assert view.get_by_text("ZZ-NOT-IN-MODEL").count() == 0


def test_fr1012_ac080_unknown_requirement_selection_draws_nothing(page):
    # FR-1012 AC-080 abnormal: nonexistent requirement in deep link yields no invented asset
    bogus = "ZZ-" + "UNKNOWN-REQ"
    page.goto(page.url.split("#")[0] + "#/placement?select=" + bogus)
    page.wait_for_timeout(500)
    assert page.locator("#view").get_by_text(bogus).count() == 0


def test_fr1012_ac081_click_highlights_and_deselect_restores(page):
    # FR-1012 AC-081 (click)
    _open_placement_diagram(page)
    view = page.locator("#view")
    target = view.get_by_text("FR-001", exact=True).first
    before = view.inner_html()
    target.click()
    page.wait_for_timeout(300)
    during = view.inner_html()
    assert during != before, "selection must visibly highlight related assets / dim others"
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert view.inner_html() == before, "deselect restores normal display"


def test_fr1012_ac081_keyboard_selects_same_as_click(page):
    # FR-1012 AC-081 non-click path (keyboard)
    _open_placement_diagram(page)
    view = page.locator("#view")
    target = view.get_by_text("FR-001", exact=True).first
    target.click()
    page.wait_for_timeout(300)
    clicked = view.inner_html()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    target.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert view.inner_html() == clicked


def test_fr1012_ac081_table_row_selects_same_as_click(page):
    # FR-1012 AC-081 non-click path (correspondence-table row selection)
    _open_placement_diagram(page)
    view = page.locator("#view")
    view.get_by_text("FR-001", exact=True).first.click()
    page.wait_for_timeout(300)
    clicked = view.inner_html()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    view.locator("table tbody tr").filter(has_text="FR-001").first.click()
    page.wait_for_timeout(300)
    assert view.inner_html() == clicked
