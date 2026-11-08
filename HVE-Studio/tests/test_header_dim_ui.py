"""Integration tests for FR-1066 (mode switch) and FR-1067 (zoom carried across modes)."""
import pytest

from test_links_wrap_status_ui import ROOT, studio, _open, sync_api  # noqa: F401

HDR = '[data-testid="header-dim-toggle"]'
JS = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "web" / "js").glob("*.js")}


# FR-1066 AC-367 / AC-369: only supported modes are labelled, keyboard-accessible and announced in JA and EN.
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac367_ac369_header_toggle_exposes_only_2d_3d_graph_with_accessible_reasons(studio, lang):
    page = _open(studio, "tables", lang=lang)
    box = page.locator(HDR)
    buttons = box.locator("[data-dim]")
    assert [buttons.nth(i).get_attribute("data-dim") for i in range(buttons.count())] == ["2d", "3d", "graph"]
    assert "RPG" not in box.inner_text().upper()
    for dim in ("2d", "3d", "graph"):
        button = box.locator(f'[data-dim="{dim}"]')
        assert dim.upper() in button.inner_text()
        assert button.get_attribute("aria-label")
    assert box.locator('[data-dim="2d"]').get_attribute("aria-pressed") == "true"
    for dim in ("3d", "graph"):
        disabled = box.locator(f'[data-dim="{dim}"]')
        assert disabled.is_disabled() and disabled.get_attribute("data-reason")
    page.context.close()


# FR-1066 AC-369: Tab/Enter and command search reach the same remaining modes; no retired-mode command is offered.
def test_ac369_keyboard_and_command_box_operate_remaining_modes(studio):
    page = _open(studio, "diagrams?kind=ctx&dim=2d")
    page.locator(f'{HDR} [data-dim="3d"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.selected === '3d'")
    page.locator("#q").fill(">2D")
    page.locator("#q").press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.selected === '2d'")
    page.locator("#q").fill(">rpg")
    assert page.locator('[data-testid="command-item"]').count() == 0
    page.context.close()


# FR-1066 AC-286 / AC-367: an old URL or stored old selection resolves to the default 2D view after reload.
def test_ac286_legacy_map_route_and_query_do_not_restore_retired_mode(studio):
    page = _open(studio, "maprpg")
    page.wait_for_selector(f'{HDR}[data-current="2d"]')
    assert page.locator(f'{HDR} [data-dim="rpg"]').count() == 0
    page.reload()
    page.wait_for_selector(f'{HDR}[data-current="2d"]')
    page.goto(page.url.split("#")[0] + "#/map2d?dim=rpg")
    page.wait_for_selector(f'{HDR}[data-current="2d"]')
    assert page.locator(f'{HDR} [data-selected="rpg"]').count() == 0
    page.context.close()


# FR-1066 AC-295: legacy controls do not trigger special view/audio behavior or block ordinary input.
def test_ac295_legacy_keys_do_not_start_special_mode_and_leave_search_usable(studio):
    page = _open(studio, "map2d")
    page.add_init_script("""
      window.__audioStarts = 0;
      for (const name of ["AudioBufferSourceNode", "OscillatorNode"]) {
        const start = window[name]?.prototype?.start;
        if (start) window[name].prototype.start = function (...args) {
          window.__audioStarts++;
          return start.apply(this, args);
        };
      }
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (...args) {
        window.__audioStarts++;
        return play.apply(this, args);
      };
    """)
    page.reload()
    page.wait_for_selector(HDR)
    page.locator("body").click(position={"x": 4, "y": 4})
    for key in ("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "w", "a", "s", "d", "Enter", "z", "Escape", "x", "Space", "Shift"):
        page.keyboard.press(key)
    assert page.locator(f'{HDR}[data-current="2d"]').count() == 1
    assert page.locator(f'{HDR} [data-dim="rpg"]').count() == 0
    assert page.locator('.rpg, [data-testid^="rpg-"]').count() == 0
    assert page.evaluate("() => window.__audioStarts") == 0
    assert page.evaluate("() => window.eabkView.getState().rpg") is None
    page.locator("#q").fill("requirements")
    assert page.locator("#q").input_value() == "requirements"
    assert page.locator("#results").inner_text()
    page.context.close()


# FR-1066 AC-370 / FR-1067 AC-373: the chosen mode, actual mode and shared zoom state remain separate.
def test_ac370_ac373_selected_is_kept_apart_from_current_and_zoom_state_is_shared():
    assert "data-selected" in JS["dim.js"] and "selected" in JS["diagrams.js"] and "wanted" in JS["entities.js"]
    assert "export const view" in JS["semzoom.js"]
    for f in ("map2d.js", "map3d.js", "entities.js"):
        assert "mountShell" in JS[f]
    assert "publishDim" in JS["app.js"] and "headerDimToggle" in JS["app.js"]
    assert "rpg" not in JS["dim.js"].lower()


# FR-1067 AC-373: zoom is restored after leaving a zoom-capable map for a screen without zoom and returning.
def test_ac373_zoom_level_is_restored_after_zoomless_screen(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    page.evaluate("() => window.eabkView.setScale(3)")
    before = page.locator('[data-testid="semantic-zoom"]').get_attribute("data-level")
    page.locator('#nav a[data-nav="tables"]').click()
    page.wait_for_selector('#nav a[data-nav="tables"].on')
    page.locator('#nav a[data-nav="map"]').click()
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    assert page.locator('[data-testid="semantic-zoom"]').get_attribute("data-level") == before
    page.context.close()
