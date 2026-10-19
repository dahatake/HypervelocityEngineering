"""System tests for FR-1050 AC-277/278, FR-1051 AC-280/281, FR-1052 AC-283/284/285.

Expected values come only from the acceptance criteria in docs/requirements-definition.md.
The implementation is NOT the oracle.  (AC-279 / AC-282 are integration level and not covered here.)

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。oracle は実装に合わせて直さない):
  - ID リンク: <a>（本文がその ID）。未解決 ID は <a> でなく「未解決」の語/aria-label/title を伴う要素。
  - 「表」画面: route #/tables。種別の選択肢は role=group（名前=要求/設計/証跡/運用）の下。
  - 種別（?tab=）は reqs など既存のキーを使う（本テストは種別キーを前提にしない）。
  - パンくず: nav[aria-label] 内に「エンティティ」(a) と現在位置 [aria-current=page]。
  - ダッシュボードの区分: svg/要素のうち aria-label を持つ focusable 要素（tabindex または a/button）。
  - 外部連携の行: 各行に「詳細」の a/button。
"""
import json
import re

import pytest
from playwright.sync_api import expect

from entity_repo import make_standard, make_zoom
from test_studio_links_wrap_status_arch_system import _serve
from test_studio_system import page, studio_url  # noqa: F401  (fixtures)

ID_TOKEN = re.compile(r"\b(?:G|FR|NFR(?:-[A-Z]+)?|AC|Q|PARAM|SRC|INT|E2E|IT)-\d+\b")
GROUPS = ("要求", "設計", "証跡", "運用")
EXPECTED_KINDS = {  # AC-280 ［ASSUMPTION］ の分け方
    "要求": ["目的", "要求", "受入基準", "PARAM", "質問"],
    "設計": ["エンティティ", "共通部品", "API", "テーブル", "外部連携", "用語", "ペルソナ"],
    "証跡": ["試験ケース", "ファイル", "出典"],
    "運用": ["決定記録", "監査指摘", "実行履歴"],
}


def _integ_repo(tmp_path, related="FR-001、AC-001、FR-" + "9"*4 + ""):
    repo = make_zoom(tmp_path / "integ")
    cfg_path = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["management_files"]["integrations"] = "docs/integrations.md"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    (repo / "docs" / "integrations.md").write_text(
        "# 外部連携カタログ\n\n#### INT-001 受注 API\n- 連携先: 取引先 A\n- 方向: 受信\n- 状態: 運用中\n"
        f"- 関連する要求: {related}\n", encoding="utf-8")
    return repo


@pytest.fixture()
def integ_page(browser, tmp_path):
    proc, url = _serve(_integ_repo(tmp_path))
    ctx = browser.new_context()
    p = ctx.new_page()
    p.goto(url + "#/integrations")
    p.wait_for_load_state("networkidle")
    yield p
    ctx.close()
    proc.terminate()


# FR-1050 AC-277
def test_ac277_existing_ids_in_all_table_cells_are_links(page):
    page.goto(page.url.split("#")[0] + "#/tables")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#view [role=tab]")
    tabs = page.locator('#view [role=tab], #view [data-testid="table-kind"]')
    n = tabs.count()
    assert n >= 10, "表の種別の選択肢が見つからない"
    checked = 0
    for i in range(n):
        tabs.nth(i).click()
        page.wait_for_load_state("networkidle")
        for cell in page.locator("#view table td").all()[:200]:
            txt = cell.inner_text()
            ids = set(ID_TOKEN.findall(txt))
            if not ids:
                continue
            link_texts = {t.strip() for t in cell.locator("a").all_inner_texts()}
            unresolved = cell.locator('[data-unresolved], [aria-label*="未解決"], [title*="未解決"]').all_inner_texts()
            for x in ids:
                if x in " ".join(unresolved):
                    continue  # 実在しない ID は AC-279 の表示
                assert x in link_texts, f"kind#{i}: {x} is plain text in cell {txt!r}"
                checked += 1
    assert checked > 0


# FR-1050 AC-277 (abnormal: 実在しない ID はリンクにならない)
def test_ac277_nonexistent_id_in_table_is_not_a_link(page):
    page.goto(page.url.split("#")[0] + "#/tables?tab=reqs&q=FR-" + "9"*4 + "")
    page.wait_for_load_state("networkidle")
    assert page.locator("#view a", has_text=re.compile(r"^FR-" + "9"*4 + "$")).count() == 0


# FR-1050 AC-278
def test_ac278_integrations_related_ids_are_links(integ_page):
    p = integ_page
    for rid in ("FR-001", "AC-001", "INT-001"):
        link = p.locator("#view a", has_text=re.compile(rf"^{rid}$")).first
        expect(link, f"{rid} is not a link in the list").to_have_count(1)
    p.locator("#view a", has_text=re.compile(r"^INT-001$")).first.click()
    detail = p.locator("#drawer")
    for rid in ("FR-001", "AC-001"):
        expect(detail.locator("a", has_text=re.compile(rf"^{rid}$")).first).to_be_visible()


# FR-1050 AC-278 / AC-279 (abnormal: 実在しない関連要求は a にならず「未解決」を伴う)
def test_ac278_missing_related_id_is_unresolved_not_link(integ_page):
    p = integ_page
    assert p.locator("#view a", has_text=re.compile(r"^FR-" + "9"*4 + "$")).count() == 0
    el = p.locator("#view", has_text="FR-" + "9"*4 + "").first
    assert re.search("未解決", el.inner_html()), "未解決の表示がない"


# FR-1051 AC-280
def test_ac280_kinds_are_grouped_under_four_headings(page):
    page.goto(page.url.split("#")[0] + "#/tables")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#view [role=group] [role=tab]")
    seen = []
    for g in GROUPS:
        grp = page.locator("#view [role=group]").filter(has_text=g)
        assert grp.count() >= 1, f"グループ {g} がない"
        for kind in EXPECTED_KINDS[g]:
            assert grp.first.get_by_text(kind, exact=False).count() >= 1, f"{g} に {kind} がない"
            seen.append(kind)
    assert len(seen) == len(set(seen)) == 18  # AC 本文の列挙: 5+7+3+3
    # 見出しなしのフラットなタブ列がない: すべてのタブがグループの内側にある
    tabs = page.locator("#view [role=tab]")
    in_group = page.locator("#view [role=group] [role=tab]")
    assert tabs.count() == in_group.count() > 0


# FR-1051 AC-281
@pytest.mark.parametrize("lang,word,banned", [
    ("ja", "表", ("データ表", "全レコード", "Data tables")),
    ("en", None, ("データ表", "全レコード", "Data tables")),
])
def test_ac281_screen_name_is_unified(browser, studio_url, lang, word, banned):
    ctx = browser.new_context()
    ctx.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    p = ctx.new_page()
    p.goto(studio_url + "#/tables")
    p.wait_for_load_state("networkidle")
    p.wait_for_selector("#view [role=tab]")  # 表の画面が描画されるまで待つ
    nav = p.locator('nav a[href="#/tables"]').first
    def _strip(s):  # 絵文字・記号を除いた画面名
        return re.sub(r"[^\w]+", " ", s, flags=re.UNICODE).strip()
    nav_text = _strip(nav.inner_text())
    title = _strip(p.locator("#view h1").first.inner_text())
    if lang == "ja":
        assert word in nav_text and word in title
    else:
        assert nav_text in ("Table", "Tables") and title in ("Table", "Tables") and nav_text == title
    name_scope = nav_text + " " + title + " " + (nav.get_attribute("title") or "")
    for b in banned:
        assert b not in name_scope, f"画面名に別の語 {b} が併存"
    ctx.close()


# FR-1052 AC-283
def test_ac283_entity_detail_has_breadcrumb(browser, tmp_path):
    proc, url = _serve(make_standard(tmp_path / "std"))
    ctx = browser.new_context()
    p = ctx.new_page()
    try:
        p.goto(url + "/#/entities")
        p.wait_for_load_state("networkidle")
        p.get_by_text("注文", exact=True).first.click()
        nav = p.locator("nav[aria-label]").filter(has_text="エンティティ")
        expect(nav.first).to_be_visible()
        expect(nav.first.locator("[aria-current=page]")).to_contain_text("注文")
        back = nav.first.locator("a", has_text=re.compile(r"^エンティティ$"))
        assert back.count() == 1
        back.click()
        expect(p).to_have_url(re.compile(r"#/entities/?$"))
    finally:
        ctx.close()
        proc.terminate()


# FR-1052 AC-284
def test_ac284_dashboard_segments_focusable_named_and_labelled(page):
    page.goto(page.url.split("#")[0] + "#/dashboard")
    page.wait_for_load_state("networkidle")
    segs = page.locator('#view [data-testid="chart-segment"]')
    assert segs.count() >= 2, "ドーナツ・棒の区分が見つからない"
    for i in range(segs.count()):
        s = segs.nth(i)
        name = s.get_attribute("aria-label") or ""
        assert re.search(r"\d", name) and re.search(r"[^\d\s:：]", name), f"区分 {i} の名前と数値がない: {name!r}"
        tag = s.evaluate("e => e.tagName.toLowerCase()")
        assert tag in ("a", "button") or s.get_attribute("tabindex") is not None
    first = segs.first
    first.focus()
    assert first.evaluate("e => document.activeElement === e")
    labels = page.locator('#view [data-testid="chart-segment-label"]')
    assert labels.count() >= 1 and labels.first.is_visible()
    assert re.search(r"\d", labels.first.inner_text())


# FR-1052 AC-285
def test_ac285_integration_rows_have_keyboard_detail_control(integ_page):
    p = integ_page
    rows = p.locator('#view [data-testid="integration-row"], #view tbody tr')
    assert rows.count() >= 1
    btn = rows.first.locator("a, button").filter(has_text="詳細").first
    assert btn.count() == 1
    btn.focus()
    p.keyboard.press("Enter")
    expect(p.locator("#drawer")).to_contain_text("INT-001")
    p.keyboard.press("Escape")
    rows.first.click()  # 行のクリックでの動作は維持される
    expect(p.locator("#drawer")).to_contain_text("INT-001")


# FR-1052 AC-285 (abnormal: 連携が 0 件でも「詳細」の偽の操作を出さない)
def test_ac285_no_integrations_shows_no_detail_control(browser, tmp_path):
    repo = _integ_repo(tmp_path)
    (repo / "docs" / "integrations.md").write_text("# 外部連携カタログ\n", encoding="utf-8")
    proc, url = _serve(repo)
    ctx = browser.new_context()
    p = ctx.new_page()
    try:
        p.goto(url + "#/integrations")
        p.wait_for_load_state("networkidle")
        assert p.locator("#view a, #view button").filter(has_text=re.compile(r"^詳細$")).count() == 0
    finally:
        ctx.close()
        proc.terminate()

