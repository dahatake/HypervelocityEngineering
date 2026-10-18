"""System tests for FR-1014 AC-091 (implementation-status screen).

Expected values come only from docs/requirements-definition.md.  The screen is
reached the way a user does (navigation link named 「実装状態」).  Bars/columns are
read through `data-state` attributes on elements with the roles named below;
this is the only contract assumed about the markup (to be confirmed by the
implementer; if it differs, report a CONFLICT instead of editing this oracle).
"""
import re

import pytest
from playwright.sync_api import expect

from test_studio_system import ROOT, page, studio_url  # noqa: F401  (fixtures)

STATES = (
    "未着手",
    "実装登録済み・試験未登録",
    "実装登録済み・試験未合格",
    "試験 pass 済み",
    "実装登録済み・system 試験対象外",
)


def _approved_requirement_count():
    text = (ROOT / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    count = 0
    for block in re.split(r"(?m)^#### ", text)[1:]:
        if re.match(r"(FR|NFR)-[A-Z0-9-]*\d+ ", block):
            m = re.search(r"- 決定状態: (\S+)", block)
            if m and m.group(1).startswith("承認済み"):
                count += 1
    return count


def _open(page):
    page.get_by_role("link", name="実装状態").first.click()
    expect(page.locator("#view")).to_contain_text("実装状態")


def _counts(page, kind):
    """kind: 'bar-segment' or 'kanban-column' -> {state: count} for the overall scope."""
    out = {}
    for el in page.locator(f'[data-testid="impl-{kind}"][data-scope="all"]').all():
        out[el.get_attribute("data-state")] = int(el.get_attribute("data-count"))
    return out


# FR-1014 AC-091
def test_impl_status_screen_shows_bars_and_kanban_for_all_scopes(page):
    _open(page)
    view = page.locator("#view")
    for state in STATES:
        expect(view).to_contain_text(state)
    for scope in ("all", "goal", "priority"):
        assert page.locator(f'[data-testid="impl-bar"][data-scope="{scope}"]').count() >= 1, scope
    assert page.locator('[data-testid="impl-kanban-column"]').count() >= 1


# FR-1014 AC-091
def test_impl_status_bar_segments_equal_kanban_columns_and_sum_to_approved_total(page):
    _open(page)
    bars = _counts(page, "bar-segment")
    columns = _counts(page, "kanban-column")
    assert bars == columns
    assert set(bars) <= set(STATES)
    assert sum(bars.values()) == _approved_requirement_count()


# FR-1014 AC-091
def test_impl_status_card_selection_opens_requirement_detail_and_links_views(page):
    _open(page)
    card = page.locator('[data-testid="impl-kanban-card"]').first
    req_id = card.get_attribute("data-req")
    assert re.match(r"(NFR-[A-Z0-9]+-\d+|FR-\d+)$", req_id)
    card.click()
    expect(page.locator("#drawer")).to_contain_text(req_id)
    # selection is shared with other representations (map keeps the selection)
    page.locator('a[href="#/map2d"]').click()
    expect(page.locator("#drawer")).to_contain_text(req_id)


# FR-1014 AC-091 (abnormal: a requirement that is not approved must not be counted)
def test_impl_status_excludes_non_approved_requirements_from_cards(page):
    _open(page)
    ids = {c.get_attribute("data-req") for c in page.locator('[data-testid="impl-kanban-card"]').all()}
    text = (ROOT / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    for block in re.split(r"(?m)^#### ", text)[1:]:
        m = re.match(r"((?:FR|NFR-[A-Z0-9]+)-\d+) ", block)
        s = re.search(r"- 決定状態: (\S+)", block)
        if m and s and not s.group(1).startswith("承認済み"):
            assert m.group(1) not in ids
    assert len(ids) == _approved_requirement_count()
