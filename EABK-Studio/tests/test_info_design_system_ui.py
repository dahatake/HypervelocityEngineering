"""Integration tests for FR-1050 AC-279 (unresolved IDs) and FR-1051 AC-282 (grouped table kinds keep state, keyboard)."""
import re

from test_links_wrap_status_ui import studio, _open, sync_api  # noqa: F401


# FR-1050 AC-279: an ID that does not exist is not a link, carries the word 未解決 (not colour alone).
def test_ac279_unknown_id_in_table_cell_is_marked_unresolved_not_link(studio):
    page = _open(studio, "tables?tab=decisions")
    page.locator("#view table tbody tr").first.wait_for()
    # a decision row targets FR-001 (exists); add an unknown ID via the filter-less text of the audit/ question tabs is data dependent,
    # so check the shared helper directly in the page.
    out = page.evaluate("""async () => {
      const x = await import('./js/xref.js');
      const ok = x.idsToNodes('FR-001 と FR-98765');
      return ok.map((n) => ({ tag: n.nodeType === 1 ? n.tagName : '#text', text: n.textContent, aria: n.getAttribute ? n.getAttribute('aria-label') : null, unresolved: n.dataset ? 'unresolved' in n.dataset : false }));
    }""")
    link = next(o for o in out if o["text"] == "FR-001")
    bad = next(o for o in out if o["tag"] == "SPAN")
    assert link["tag"] == "A"
    assert bad["tag"] == "SPAN" and bad["unresolved"] and "未解決" in bad["text"] and "未解決" in (bad["aria"] or "")
    page.context.close()


# FR-1050 AC-279: a link in a table works from the keyboard and keeps the selected target.
def test_ac279_table_id_link_opens_with_enter_and_keeps_selection(studio):
    page = _open(studio, "tables?tab=reqs")
    link = page.locator("#view tbody a.xref", has_text=re.compile(r"^FR-001$")).first
    link.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.getElementById('drawer').hidden")
    assert "FR-001" in page.locator("#drawer").inner_text()
    assert page.locator("#view").get_by_role("tab", name=re.compile("要求")).first.get_attribute("aria-selected") == "true"
    page.context.close()


# FR-1051 AC-280 AC-282: kinds sit under four named groups; choosing one by keyboard keeps filter and sort; groups are named in words.
def test_ac282_group_headings_keyboard_selection_keeps_filter_and_sort(studio):
    page = _open(studio, "tables?tab=reqs")
    groups = page.locator("#view [role=group]")
    assert groups.count() == 4
    names = [groups.nth(i).get_attribute("aria-label") for i in range(4)]
    assert names == ["要求", "設計", "証跡", "運用"]
    assert all(groups.nth(i).locator(".gh").inner_text() == names[i] for i in range(4))
    assert page.locator("#view [role=tab]").count() == page.locator("#view [role=group] [role=tab]").count()
    page.locator("#view input[type=search]").fill("FR-90")
    page.locator("#view th", has_text="ID").first.click()
    count_before = page.locator("#view .tbar .mini").first.inner_text()
    tab = page.locator("#view [role=group][data-group=evidence] [role=tab]").first
    tab.focus()
    page.keyboard.press("Enter")
    assert tab.get_attribute("aria-selected") == "true"
    page.locator("#view [role=group][data-group=req] [role=tab]").nth(1).focus()
    page.keyboard.press("Enter")
    assert page.locator("#view input[type=search]").input_value() == "FR-90"
    assert page.locator("#view .tbar .mini").first.inner_text() == count_before
    with page.expect_download() as dl:
        page.locator("#view button", has_text="CSV").click()
    assert dl.value.suggested_filename == "eabk-reqs.csv"
    page.context.close()


# FR-1050 AC-277: in every kind, an ID that exists in the data is a link (no plain-text IDs).
def test_ac277_every_kind_has_no_plain_text_existing_ids(studio):
    page = _open(studio, "tables")
    idre = re.compile(r"\b(?:G|FR|NFR(?:-[A-Z]+)?|AC|Q|PARAM|SRC|INT|E2E|IT)-\d+\b")
    tabs = page.locator("#view [role=tab]")
    assert tabs.count() == 18
    for i in range(tabs.count()):
        tabs.nth(i).click()
        for cell in page.locator("#view table td").all()[:300]:
            links = {a.strip() for a in cell.locator("a").all_inner_texts()}
            unresolved = " ".join(cell.locator("[data-unresolved]").all_inner_texts())
            for x in set(idre.findall(cell.inner_text())):
                assert x in links or x in unresolved, f"tab {i}: {x} is plain text"
    page.context.close()
