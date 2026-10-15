"""System tests for NFR-UX-002 AC-015 / AC-041 and NFR-SEC-003 AC-042 (EABK Studio).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The
implementation is NOT the oracle.

PROVISIONAL CONTRACT (仮置き。AC に画面の部品名がないため。実装者が確認し、食い違えば CONFLICT として返す。
この oracle は実装に合わせて直さない):
  - レイアウト: window.eabkView.getState().layout = {id: <配置の識別子>, isDefault: bool}。
  - 変更操作: [data-testid="layout-change"]（既定でない別の配置へ切り替える）。
  - 既定へ戻す: [data-testid="layout-reset"]（同一表示中、再読込なしで行える）。
  - 保存先: ブラウザー（Local Storage）。別のブラウザー・端末 = 新しい browser context（保存領域が別）。
  - 検索語: ヘッダーの入力 input[type=search]。選択中の対象: ハッシュの select=<ID>。絞り込み: ハッシュの q=。
"""
import re

from playwright.sync_api import expect

from test_studio_system import page, studio_url  # noqa: F401  (fixtures)

FORBIDDEN = re.compile(r"認可済み|機密判定済み|アクセス許可済み|閲覧権限あり|authorized", re.I)


def _layout(page):
    return page.evaluate("() => window.eabkView.getState().layout")


def _change(page):
    page.get_by_test_id("layout-change").first.click()
    expect(page.get_by_test_id("layout-change").first).to_be_visible()
    assert _layout(page)["isDefault"] is False


# NFR-UX-002 AC-015
def test_ac015_changed_layout_is_restored_in_same_browser_after_reload(page):
    default = _layout(page)
    assert default["isDefault"] is True
    _change(page)
    changed = _layout(page)
    page.reload()
    page.wait_for_load_state("networkidle")
    assert _layout(page)["id"] == changed["id"] != default["id"]


# NFR-UX-002 AC-015 (別のブラウザー・端末には引き継がれない)
def test_ac015_changed_layout_is_not_carried_to_another_browser(page, browser, studio_url):
    _change(page)
    other = browser.new_context()
    try:
        p2 = other.new_page()
        p2.goto(studio_url)
        p2.wait_for_load_state("networkidle")
        assert _layout(p2)["isDefault"] is True
    finally:
        other.close()


# NFR-UX-002 AC-015 (abnormal: 壊れた保存値は既定で表示し、エラーにしない)
def test_ac015_corrupted_saved_layout_falls_back_to_default(page):
    _change(page)
    page.evaluate(
        "() => { for (const k of Object.keys(localStorage)) if (/layout/i.test(k)) localStorage.setItem(k, '{broken'); }"
    )
    page.reload()
    page.wait_for_load_state("networkidle")
    assert _layout(page)["isDefault"] is True
    assert not re.search(r"Traceback|undefined|Error", page.locator("#view").inner_text())


# NFR-UX-002 AC-041
def test_ac041_reset_restores_default_and_keeps_search_selection_and_filter(page):
    base = page.url.split("#")[0]
    page.goto(base + "#/tables?tab=reqs&q=FR-001&select=FR-001")
    page.wait_for_load_state("networkidle")
    box = page.locator("input[type=search]").first
    box.fill("FR-001")
    _change(page)
    page.get_by_test_id("layout-reset").first.click()
    assert _layout(page)["isDefault"] is True
    assert box.input_value() == "FR-001"
    h = page.evaluate("() => location.hash")
    assert "select=FR-001" in h and "q=FR-001" in h


# NFR-UX-002 AC-041 (abnormal: 既に既定のときの復元は何も壊さない)
def test_ac041_reset_when_already_default_changes_nothing(page):
    base = page.url.split("#")[0]
    page.goto(base + "#/tables?tab=reqs&q=FR-001")
    page.wait_for_load_state("networkidle")
    before = _layout(page)
    assert before["isDefault"] is True
    page.get_by_test_id("layout-reset").first.click()
    assert _layout(page) == before
    assert "q=FR-001" in page.evaluate("() => location.hash")


# NFR-SEC-003 AC-042
def test_ac042_all_managed_data_observable_and_no_authorization_claim(page):
    base = page.url.split("#")[0]
    for route in ("dashboard", "tables?tab=reqs", "impl-status"):
        page.goto(base + "#/" + route)
        page.wait_for_load_state("networkidle")
        assert not FORBIDDEN.search(page.locator("body").inner_text()), route
    page.goto(base + "#/tables?tab=reqs")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#view")).to_contain_text("FR-001")


# NFR-SEC-003 AC-042 (abnormal: レコード単位の許可範囲・機密区分の判定 UI を持たない)
def test_ac042_no_record_level_access_or_sensitivity_judgement_controls(page):
    page.goto(page.url.split("#")[0] + "#/tables?tab=reqs")
    page.wait_for_load_state("networkidle")
    assert page.locator('[data-testid*="access-control"], [data-testid*="sensitivity"], [data-testid*="permission"]').count() == 0
    page.locator("#view a", has_text=re.compile(r"^FR-001$")).first.click()
    assert not FORBIDDEN.search(page.locator("#drawer").inner_text())
