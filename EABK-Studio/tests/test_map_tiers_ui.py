"""Integration tests for FR-1063 AC-345 / AC-346 / AC-347 (マップ 2D・3D・RPG 風の上位層の表示).
Run: python -m pytest EABK-Studio/tests/test_map_tiers_ui.py -q"""
import re

import pytest

from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: F401
from entity_repo import make_large

GROUP = '[data-testid="tier-group"]'


def _groups(page, level=None):
    sel = GROUP + (f'[data-tier-level="{level}"]' if level else "")
    return page.evaluate(
        """(sel) => [...document.querySelectorAll(sel)].map(g => ({
            level: g.dataset.tierLevel, path: JSON.parse(g.dataset.tierPath), count: parseInt(g.dataset.count, 10)}))""", sel)


# FR-1063 AC-345: 2D の項目が上位層でまとまり、名称・件数が見え、開閉で項目が現れる／隠れる
def test_ac345_map2d_tiers_group_items_with_name_count_and_toggle(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector(GROUP)
    hier = page.evaluate("() => window.eabkStore ? 0 : 0")  # noqa: F841
    areas = _groups(page, "area")
    assert areas and all(g["count"] > 0 for g in areas)
    first = page.locator(f'{GROUP}[data-tier-level="area"]').first
    toggle = first.locator('[data-testid="tier-toggle"]').first
    assert re.search(r"\(\d+\)", toggle.get_attribute("aria-label"))      # 名称と件数が支援技術に伝わる
    if toggle.get_attribute("aria-expanded") == "true":
        toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() == 0
    toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() == int(first.get_attribute("data-count"))
    page.context.close()


# FR-1063 AC-346: 3D は 2D と同じ上位層の構成で、開閉状態は画面をまたいで保たれる
def test_ac346_map3d_same_tiers_as_2d_and_open_state_kept(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector(GROUP)
    s2 = _groups(page)
    page.locator(f'{GROUP}[data-tier-level="area"] [data-testid="tier-toggle"]').first.click()
    opened = page.locator(f'{GROUP}[data-tier-level="area"]').first.get_attribute("data-tier-path")
    page.goto(page.url.split("#")[0] + "#/map3d")
    page.wait_for_selector(GROUP)
    assert _groups(page) == s2
    g = page.locator(f'{GROUP}[data-tier-level="area"]').first
    assert g.get_attribute("data-tier-path") == opened and g.locator('[data-testid="tier-toggle"]').first.get_attribute("aria-expanded") == "true"
    page.context.close()


# FR-1063 AC-347: RPG 風はスタートメニューから項目の上位層を会話ウィンドウに出し、城・街・住人の件数は変わらない
def test_ac347_rpg_tier_dialog_keeps_place_counts_and_closes_with_escape(studio):
    page = _open(studio, "maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    before = page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }")
    page.keyboard.press("Space")
    page.get_by_text("項目の上位層").first.click()
    dlg = page.locator('[data-testid="rpg-dialog"]')
    dlg.wait_for()
    assert dlg.locator(GROUP).count() > 0 and dlg.locator('[data-testid="tier-toggle"]').first.get_attribute("aria-label")
    page.keyboard.press("ArrowDown")                                       # 木の中の矢印は木の操作（歩かない）
    assert page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }") == before
    page.keyboard.press("Escape")
    assert dlg.is_hidden()
    page.context.close()
