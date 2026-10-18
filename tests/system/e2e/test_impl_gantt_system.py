"""System tests for FR-1061 AC-337 (Gantt chart view on the implementation-status screen).

Expected values come only from docs/requirements-definition.md (FR-1061: start =
min(history[].at) over the requirement's ledger cases; end = max(last_run_at,
history[].at); requirements without cases are "undated" and counted, not drawn)
and from tests/system/ledger.json as the input data.

Markup contract (the DOM is not implemented yet; the implementer must conform or
report a CONFLICT, not edit this oracle):
  impl-gantt            the chart container
  impl-gantt-axis       <select> choosing the vertical axis; option values all|goal|priority
  impl-gantt-bar        one per dated requirement row: data-req, data-start, data-end (ISO 8601), data-state
  impl-gantt-group      heading row of a goal/priority group: data-group; its requirement bars are descendants
  impl-gantt-undated    element with data-count = number of undated approved FRs
The Gantt view is chosen with a control whose accessible name contains 「ガント」.
"""
import json
import re
from datetime import datetime

import pytest
from playwright.sync_api import expect

from test_studio_system import ROOT, page, studio_url  # noqa: F401  (fixtures)
from test_impl_status_system import _open, STATES


def _requirements():
    """{FR id: priority word} for approved FRs only."""
    text = (ROOT / "docs" / "requirements-definition.md").read_text(encoding="utf-8")
    out = {}
    for block in re.split(r"(?m)^#### ", text)[1:]:
        m = re.match(r"(FR-\d+) ", block)
        s = re.search(r"- 決定状態: (\S+)", block)
        if m and s and s.group(1).startswith("承認済み"):
            p = re.search(r"優先度: ([A-Z]+)", block)
            out[m.group(1)] = p.group(1) if p else None
    return out


def _ts(value):
    return datetime.fromisoformat(value)


def _expected_dates():
    """{FR id: (start, end)} derived from the ledger by the FR-1061 rule."""
    approved = _requirements()
    ledger = json.loads((ROOT / "tests" / "system" / "ledger.json").read_text(encoding="utf-8"))
    stamps = {}
    for case in ledger["cases"]:
        points = []
        for h in case.get("history", []):
            try:
                points.append(_ts(h["at"]))
            except (KeyError, ValueError, TypeError):
                pass
        ends = list(points)
        try:
            ends.append(_ts(case["last_run_at"]))
        except (KeyError, ValueError, TypeError):
            pass
        if not points and not ends:
            continue
        for req in case.get("requirement_ids", []):
            if req in approved:
                s = stamps.setdefault(req, [[], []])
                s[0].extend(points)
                s[1].extend(ends)
    return {r: (min(s[0] or s[1]), max(s[1] or s[0])) for r, s in stamps.items()}


def _open_gantt(page):
    _open(page)
    page.get_by_role("button", name=re.compile("ガント")).or_(
        page.get_by_role("tab", name=re.compile("ガント"))
    ).or_(page.get_by_role("link", name=re.compile("ガント"))).first.click()
    expect(page.locator('[data-testid="impl-gantt"]')).to_be_visible()


def _axis(page, value):
    page.locator('[data-testid="impl-gantt-axis"]').select_option(value)


def _bars(page):
    return page.locator('[data-testid="impl-gantt"] [data-testid="impl-gantt-bar"]').all()


# FR-1061 AC-337
def test_gantt_overall_axis_one_row_per_dated_fr_with_dates_from_ledger(page):
    _open_gantt(page)
    _axis(page, "all")
    expected = _expected_dates()
    assert expected, "ledger must yield at least one dated requirement"
    bars = {b.get_attribute("data-req"): b for b in _bars(page)}
    assert set(bars) == set(expected)  # one row per FR; FRs without cases are not drawn
    assert len(bars) == len(_bars(page))
    for req, (start, end) in expected.items():
        assert _ts(bars[req].get_attribute("data-start")) == start, req
        assert _ts(bars[req].get_attribute("data-end")) == end, req
        assert bars[req].get_attribute("data-state") in STATES


# FR-1061 AC-337 (abnormal side: requirements without ledger cases / not approved are not drawn, counted as undated)
def test_gantt_undated_count_matches_approved_frs_without_cases_and_excludes_unapproved(page):
    _open_gantt(page)
    _axis(page, "all")
    approved = _requirements()
    dated = set(_expected_dates())
    undated = page.locator('[data-testid="impl-gantt-undated"]')
    expect(undated).to_be_visible()
    assert int(undated.get_attribute("data-count")) == len(set(approved) - dated)
    ids = {b.get_attribute("data-req") for b in _bars(page)}
    assert ids <= set(approved)


# FR-1061 AC-337
def test_gantt_axis_offers_overall_goal_priority_and_groups_have_member_rows(page):
    _open_gantt(page)
    values = page.locator('[data-testid="impl-gantt-axis"] option').evaluate_all("els => els.map(e => e.value)")
    assert {"all", "goal", "priority"} <= set(values)
    dated = set(_expected_dates())
    for axis in ("goal", "priority"):
        _axis(page, axis)
        groups = page.locator('[data-testid="impl-gantt-group"]').all()
        assert groups, axis
        under = set()
        for g in groups:
            members = {b.get_attribute("data-req") for b in g.locator('[data-testid="impl-gantt-bar"]').all()}
            assert members, f"{axis}: empty group {g.get_attribute('data-group')}"
            under |= members
        assert under == dated, axis  # every dated FR appears under at least one heading
    # priority axis: each requirement sits under the heading of its own priority
    _axis(page, "priority")
    priorities = _requirements()
    for g in page.locator('[data-testid="impl-gantt-group"]').all():
        name = g.get_attribute("data-group")
        for b in g.locator('[data-testid="impl-gantt-bar"]').all():
            assert priorities[b.get_attribute("data-req")] == name


# FR-1061 AC-337 (dates stay the same on every axis)
def test_gantt_bar_dates_are_identical_across_axes(page):
    _open_gantt(page)
    expected = _expected_dates()
    for axis in ("all", "goal", "priority"):
        _axis(page, axis)
        for b in _bars(page):
            start, end = expected[b.get_attribute("data-req")]
            assert _ts(b.get_attribute("data-start")) == start
            assert _ts(b.get_attribute("data-end")) == end
