"""Integration tests for FR-1063 AC-348 AC-349 (一覧・表・実装状態・ダッシュボードなどでの上位層の表示)."""
import re

import pytest

from test_links_wrap_status_ui import ROOT, REPO, studio, _open, sync_api  # noqa: F401

GROUP = '[data-testid="tier-group"]'


def _groups(page):
    return page.evaluate("""() => [...document.querySelectorAll('[data-testid="tier-group"]')].map(g => ({
        level: g.dataset.tierLevel, path: JSON.parse(g.dataset.tierPath), count: parseInt(g.dataset.count, 10), text: g.innerText}))""")


# FR-1063 AC-348: 表の行は上位層の見出しの下にあり、見出しの件数の合計は行数と一致する（未分類も隠さない）
def test_ac348_table_rows_sit_under_tier_headings_and_counts_add_up(studio):
    page = _open(studio, "tables")
    page.wait_for_selector(GROUP)
    areas = [g for g in _groups(page) if g["level"] == "area"]
    assert areas and all(str(g["count"]) in g["text"] for g in areas)
    rows = page.locator('[data-testid="tier-item"]').count()
    assert rows == sum(g["count"] for g in areas)
    page.context.close()


# FR-1063 AC-348: 見出しの開閉（Enter / Space のキーボード操作）で行が現れ、隠れる
def test_ac348_heading_toggles_rows_by_keyboard(studio):
    page = _open(studio, "tables")
    page.wait_for_selector(GROUP)
    area = page.locator(f'{GROUP}[data-tier-level="area"]').first
    toggle = area.locator('[data-testid="tier-toggle"]').first
    toggle.focus()
    open_before = toggle.get_attribute("aria-expanded")
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") != open_before
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") == open_before
    page.context.close()


# FR-1063 AC-348: 階層に載らない表（ファイルなど）は表の名前の下の「未分類」に置かれ、隠されない
def test_ac348_rows_without_a_tier_are_explicitly_unclassified(studio):
    page = _open(studio, "tables?tab=files")
    page.wait_for_selector(GROUP)
    un = [g for g in _groups(page) if g["level"] == "area" and g["path"][-1] == "未分類"]
    assert un and sum(g["count"] for g in un) == page.locator('[data-testid="tier-item"]').count()
    page.context.close()


# FR-1063 AC-349: 実装状態では層ごとの状態の内訳が件数で示され、合計が層の件数と一致する
def test_ac349_implstatus_breakdown_sums_to_tier_count(studio):
    page = _open(studio, "implstatus")
    page.wait_for_selector(GROUP)
    rows = page.evaluate("""() => [...document.querySelectorAll('[data-testid="tier-group"]')].map(g => {
        const b = g.querySelector('[data-testid="tier-status-breakdown"]');
        return {count: parseInt(g.dataset.count, 10), nums: b ? (b.innerText.match(/\\d+/g) || []).map(Number) : null};})""")
    assert rows and all(r["nums"] and sum(r["nums"]) == r["count"] for r in rows)
    page.context.close()


# FR-1063 AC-349: ダッシュボード・図式・ソース対応・整合性保守でも上位層の見出しに件数が示される
@pytest.mark.parametrize("route", ["dashboard", "diagrams?kind=goals", "source", "maintenance", "integrations", "entities"])
def test_ac349_other_screens_show_tier_headings_with_counts(studio, route):
    page = _open(studio, route)
    page.wait_for_selector(GROUP)
    gs = _groups(page)
    assert gs and all(re.search(rf"\b{g['count']}\b", g["text"]) for g in gs)
    page.context.close()


# FR-1063 AC-349 / AC-352: 英語表示では未分類・種類の名称が英語になる
def test_ac349_tier_names_follow_language(studio):
    page = _open(studio, "tables?tab=files", lang="en")
    page.wait_for_selector(GROUP)
    txt = " ".join(g["text"] for g in _groups(page))
    assert "Unclassified" in txt and "未分類" not in txt
    page.context.close()
