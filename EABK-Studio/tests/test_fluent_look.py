"""FR-1048 (AC-263..268) and NFR-PERF-006 (AC-275): the Fluent 2 look of EABK Studio (unit / integration).

The static checks read the style sheets and scripts (no browser); the browser check reuses the `studio` fixture.
Expected values come from the acceptance criteria and PARAM-032/039; the System Tests
(tests/system/e2e/test_studio_fluent_appearance_system.py) check the same against the whole app.
Run: python -m pytest EABK-Studio/tests -q
"""
import re
from pathlib import Path

from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: F401

WEB = Path(__file__).resolve().parents[1] / "web"
TOKENS = (WEB / "tokens.css").read_text(encoding="utf-8")
APP_CSS = (WEB / "app.css").read_text(encoding="utf-8")
JS_SRC = {p.name: p.read_text(encoding="utf-8") for p in (WEB / "js").glob("*.js")}
ICON_SIZES = {16, 20, 24}  # PARAM-039
P_MOTION_MS = 300  # PARAM-032


def _token(name):
    m = re.search(re.escape(name) + r":\s*([^;]+);", TOKENS)
    assert m, f"{name} が tokens.css に無い"
    return m.group(1).strip()


# FR-1048 AC-263: per-kind radius / stroke / elevation tokens; elevation has >= 3 steps in the stacking order.
def test_ac263_component_kind_tokens_and_three_or_more_elevation_steps():
    for name in ("--radius-control", "--radius-container", "--radius-overlay", "--radius-tooltip",
                 "--stroke-control", "--stroke-container", "--stroke-overlay",
                 "--elevation-card", "--elevation-flyout", "--elevation-overlay"):
        _token(name)
    assert len(re.findall(r"--shadow-\d:", TOKENS)) >= 3
    order = [int(re.search(r"--shadow-(\d)", _token(n)).group(1)) for n in ("--elevation-card", "--elevation-flyout", "--elevation-overlay")]
    assert order == sorted(order) and len(set(order)) == 3  # card < menu / tooltip < drawer / dialog


# FR-1048 AC-263: buttons never use the pill radius; cards and overlays use their kind's token.
def test_ac263_same_kind_uses_the_same_token_in_the_style_sheet():
    for sel in (".chip{", ".tabbtn{", ".impl-legend button{", ".theme-toggle button{", ".btn{"):
        rule = APP_CSS[APP_CSS.index(sel):].split("}", 1)[0]
        assert "radius-control" in rule or "radius-md" in rule, sel
        assert "radius-pill" not in rule, sel
    assert re.search(r"\.card\{[^}]*radius-container[^}]*elevation-card", APP_CSS)
    assert re.search(r"\.drawer\{[^}]*elevation-overlay", APP_CSS)


# FR-1048 AC-264: every interactive state is styled; disabled and selected are not colour only.
def test_ac264_states_are_styled_and_disabled_selected_are_not_color_only():
    for pseudo in (":hover", ":active", ":focus-visible", ":disabled", "[aria-disabled=true]", "[aria-pressed=true]", "[aria-current=page]"):
        assert pseudo in APP_CSS, pseudo
    assert re.search(r"button:disabled[^{]*\{[^}]*border-style:dashed", APP_CSS)
    assert re.search(r"\[aria-current=page\][^{]*\{[^}]*font-weight[^}]*text-decoration", APP_CSS)


# FR-1048 AC-265: durations and easing come from tokens (300 ms at most); only the progress spinner repeats.
def test_ac265_motion_tokens_within_limit_and_no_raw_durations():
    found = re.findall(r"(--duration-[\w-]+):\s*([\d.]+)(ms|s)\s*;", TOKENS)
    assert found
    for name, num, unit in found:
        assert float(num) * (1 if unit == "ms" else 1000) <= P_MOTION_MS, name
    for decl in re.findall(r"(?:transition|animation)(?:-duration)?:([^;}]+)", APP_CSS):
        assert not re.search(r"\d(ms|s)\b", re.sub(r"var\([^)]*\)", "", decl)), decl
    assert APP_CSS.count("infinite") == 1 and re.search(r"\.spin\{[^}]*infinite", APP_CSS)
    assert "--duration-instant" in APP_CSS[APP_CSS.index("prefers-reduced-motion"):]


# FR-1048 AC-266: layers fall back to opaque surfaces (no support / reduced transparency / forced colours).
def test_ac266_material_layers_and_opaque_fallbacks():
    assert "backdrop-filter" in APP_CSS and "prefers-reduced-transparency:reduce" in APP_CSS
    assert "@supports not (backdrop-filter" in APP_CSS
    forced = APP_CSS[APP_CSS.index("@media (forced-colors: active)"):]
    assert re.search(r"\.top,#nav,\.drawer,main#view\{background:Canvas", forced)
    assert "color-mix" in _token("--material-layer")
    assert re.search(r"\.top,\.drawer\{background:var\(--material-layer-opaque\)\}", APP_CSS)


# FR-1048 AC-268: one bundled icon set, only 16 / 20 / 24 px, nothing fetched; no emoji icons in the chrome.
def test_ac268_icons_are_one_bundled_set_with_allowed_sizes():
    ui = JS_SRC["ui.js"]
    assert "ICON_PATHS" in ui and "http" not in ui.split("const ICON_PATHS")[1].split("};")[0]
    sizes = {int(n) for n in re.findall(r"icon\([^)]*size: (\d+)", "".join(JS_SRC.values()))}
    assert sizes <= ICON_SIZES, sizes
    assert not re.search(r"[\U0001F300-\U0001FAFF\u2728]", JS_SRC["app.js"] + JS_SRC["dashboard.js"] + JS_SRC["dim.js"])
    assert "svgEl('svg'" not in JS_SRC["dim.js"]  # FR-1040 toggle icons come from the bundled set


# FR-1048 AC-267 AC-268: the error state has the common structure and keeps what was typed; the dashboard donut is not an svg.
def test_ac267_error_state_structure_keeps_input_and_ac268_icon_sizes(studio):
    browser, url = studio
    page = browser.new_context().new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.locator("#q").fill("FR-001")
    page.route("**/api/model", lambda r: r.abort())
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    panel = page.locator('[data-testid="state-panel"][data-state="error"]')
    panel.first.wait_for(state="visible")
    for part in ("icon", "heading", "description", "action"):
        assert panel.first.locator(f'[data-part="{part}"]').count() == 1
    assert page.locator("#q").input_value() == "FR-001"
    page.context.close()
    page = _open(studio, "dashboard")
    widths = page.evaluate("""() => [...document.querySelectorAll('#nav svg, .dim-ico, [data-part=icon] svg')].map(s => Math.round(s.getBoundingClientRect().width))""")
    assert widths and all(w in ICON_SIZES for w in widths), widths
    assert page.locator("#view .donut").count() >= 1
    view_widths = page.evaluate("() => [...document.querySelectorAll('#view svg')].map(s => Math.round(s.getBoundingClientRect().width))")
    assert all(w in ICON_SIZES for w in view_widths), view_widths  # no chart-sized svg on the dashboard
    page.context.close()


# NFR-PERF-006 AC-275: the nav items, their order and the legacy ids are unchanged by the look change.
def test_ac275_nav_items_and_legacy_routes_unchanged():
    app = JS_SRC["app.js"]
    assert "const NAV = ['dashboard', 'implstatus', 'map', 'diagrams', 'entities', 'integrations', 'source', 'tables', 'maintenance']" in app
    for legacy in ("map2d", "map3d", "placement"):
        assert re.search(rf"\b{legacy}: ", app)
