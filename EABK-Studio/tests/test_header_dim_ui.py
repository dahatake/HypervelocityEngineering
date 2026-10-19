"""Integration tests for FR-1066 (header display-mode switch) and FR-1067 (zoom carried across modes)."""
import pytest

from test_links_wrap_status_ui import ROOT, REPO, studio, _open, sync_api  # noqa: F401

HDR = '[data-testid="header-dim-toggle"]'
JS = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "web" / "js").glob("*.js")}


# FR-1066 AC-369: three buttons with the words 2D / 3D / RPG, labelled, JA and EN both have the reason text.
@pytest.mark.parametrize("lang", [None, "en"])
def test_ac369_header_toggle_has_words_labels_and_reason_in_both_languages(studio, lang):
    page = _open(studio, "tables", lang=lang)
    box = page.locator(HDR)
    for d in ("2d", "3d", "rpg"):
        b = box.locator(f'[data-dim="{d}"]')
        assert d.upper() in b.inner_text()
        assert b.get_attribute("aria-label")
    rpg = box.locator('[data-dim="rpg"]')
    assert rpg.is_disabled() and rpg.get_attribute("data-reason")
    assert box.locator('[data-dim="2d"]').get_attribute("aria-pressed") == "true"
    page.context.close()


# FR-1066 AC-369: Tab focuses an enabled button and Enter switches; the command box reaches the same switch.
def test_ac369_keyboard_and_command_box_operate_the_header_toggle(studio):
    page = _open(studio, "diagrams?kind=ctx&dim=2d")
    page.locator(f'{HDR} [data-dim="3d"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.selected === '3d'")
    page.locator("#q").fill(">2D")
    page.locator("#q").press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.selected === '2d'")
    page.context.close()


# FR-1066 AC-368: only the map enables RPG; the header stays through screen changes.
def test_ac368_rpg_only_on_map_and_header_survives_navigation(studio):
    page = _open(studio, "map2d")
    assert page.locator(f'{HDR} [data-dim="rpg"]').is_enabled()
    page.locator('#nav a[data-nav="tables"]').click()
    page.wait_for_selector(f'{HDR} [data-dim="rpg"]:disabled')
    assert page.locator(HDR).count() == 1
    page.context.close()


# FR-1066 AC-370 / FR-1067 AC-373: wiring — the choice is kept apart from what is shown; the zoom state is one shared singleton.
def test_ac370_ac373_selected_is_kept_apart_from_current_and_zoom_state_is_shared():
    assert "data-selected" in JS["dim.js"] and "selected" in JS["diagrams.js"] and "wanted" in JS["entities.js"]
    assert "export const view" in JS["semzoom.js"]
    for f in ("map2d.js", "map3d.js", "entities.js"):
        assert "mountShell" in JS[f]
    assert "publishDim" in JS["app.js"] and "headerDimToggle" in JS["app.js"]


# FR-1067 AC-372 AC-373: the zoom level survives 2D -> RPG -> 2D on the map.
def test_ac373_zoom_level_is_restored_after_rpg(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    page.evaluate("() => window.eabkView.setScale(3)")
    before = page.locator('[data-testid="semantic-zoom"]').get_attribute("data-level")
    page.locator(f'{HDR} [data-dim="rpg"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=header-dim-toggle]').dataset.current === 'rpg'")
    page.locator(f'{HDR} [data-dim="2d"]').click()
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    assert page.locator('[data-testid="semantic-zoom"]').get_attribute("data-level") == before
    page.context.close()
