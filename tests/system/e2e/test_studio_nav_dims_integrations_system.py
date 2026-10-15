"""System tests for FR-1040 AC-220, FR-1041 AC-226, FR-1042 AC-227 (EABK Studio).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The
implementation is NOT the oracle.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - 図式: route #/diagrams?kind=<ctx|goals|states|entities|components|layers>&dim=<2d|3d>
    （kind は既存の KINDS。dim 省略時は 2D）。
  - 2D/3D 切替: [data-testid="dim-toggle"] の中に [data-dim="2d"] / [data-dim="3d"] のボタン（本文に「2D」「3D」）。
    現在の次元は [data-testid="dim-toggle"][data-current=2d|3d]。
  - 図の内容: window.eabkView.getState().diagram = {kind, dim, elements:[{id,label}], relations:[{from,to}]}
    （3D は canvas なので、この公開状態で 2D と同じ内容かを比べる）。
  - 外部連携: ナビの項目名「外部連携」。一覧の行 [data-testid="integration-row"][data-id=INT-xxx]、
    CSV は「CSV」ボタン。カタログは docs/integrations.md（`#### INT-001 <名前>` ＋ `- <欄名>: 値`）、
    scripts/ebak.config.json の management_files.integrations で指定。欄名は AC-208 の語（連携先・方向・方式・
    データ分類・個人情報・認証認可・責任分界・状態・関連する要求）を使う。
  - 旧 URL: #/map2d, #/map3d, #/placement は別名として存続。新しい項目の正確なルート名は AC にないため問わず、
    表示内容（ID・次元・種類）と「エラーにならないこと」だけを見る。
"""
import json
import re

import pytest
from playwright.sync_api import expect

from entity_repo import _base, make_zoom, DOC, CAT  # noqa: F401
from test_studio_system import ROOT, STUDIO, page, studio_url  # noqa: F401  (fixtures)
from test_studio_links_wrap_status_arch_system import _serve

KINDS = ["ctx", "goals", "states", "entities", "components", "layers"]
ERROR_RE = re.compile(r"見つかりません|not found|404|undefined|Traceback|Error", re.I)

INTEGRATIONS = """# 外部連携カタログ

| ID | 名前 | 連携先 | 方向 | 状態 | 関連する要求 |
|---|---|---|---|---|---|
| INT-001 | 受注 API | 取引先 A | 受信 | 運用中 | FR-001 |
| INT-002 | 在庫ファイル | 倉庫システム B | 送信 | 検討中 | FR-003 |

#### INT-001 受注 API
- 連携先: 取引先 A
- 方向: 受信
- 方式: REST
- データ分類: 社外秘
- 個人情報: あり
- 認証認可: OAuth 2.0（秘密の保管場所: 鍵保管庫）
- 責任分界: 取引先 A は送信まで、当社は受信後
- 状態: 運用中
- 関連する要求: FR-001
- 頻度と量: TBD（Q-001）

#### INT-002 在庫ファイル
- 連携先: 倉庫システム B
- 方向: 送信
- 方式: ファイル
- データ分類: 公開
- 個人情報: なし
- 認証認可: なし
- 責任分界: 当社は出力まで
- 状態: 検討中
- 関連する要求: FR-003
"""


def _set_integrations(repo, with_catalog=True):
    cfg_path = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["management_files"]["integrations"] = "docs/integrations.md"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    if with_catalog:
        (repo / "docs" / "integrations.md").write_text(INTEGRATIONS, encoding="utf-8")


@pytest.fixture()
def int_url(tmp_path):
    repo = make_zoom(tmp_path / "int")
    _set_integrations(repo)
    proc, url = _serve(repo)
    yield url
    proc.terminate()


def _state(page):
    return page.evaluate("() => window.eabkView.getState().diagram")


def _open(page, kind, dim):
    page.goto(page.url.split("#")[0] + f"#/diagrams?kind={kind}&dim={dim}")
    page.wait_for_load_state("networkidle")


# FR-1040 AC-220
@pytest.mark.parametrize("kind", KINDS)
def test_ac220_each_diagram_shows_same_content_in_2d_and_3d(page, kind):
    _open(page, kind, "2d")
    toggle = page.get_by_test_id("dim-toggle")
    expect(toggle).to_have_attribute("data-current", "2d")
    two = _state(page)
    toggle.locator('[data-dim="3d"]').click()
    expect(toggle).to_have_attribute("data-current", "3d")
    three = _state(page)
    assert two["kind"] == three["kind"] == kind and three["dim"] == "3d"
    key = lambda s: (sorted((e["id"], e["label"]) for e in s["elements"]), sorted((r["from"], r["to"]) for r in s["relations"]))
    assert key(two) == key(three), "2D と 3D で図の要素・関係・ラベルが違う"
    toggle.locator('[data-dim="2d"]').click()
    expect(toggle).to_have_attribute("data-current", "2d")
    assert key(_state(page)) == key(two)


# FR-1040 AC-220 (abnormal: 不正な dim 指定は 2D に戻り、表示は壊れない)
def test_ac220_invalid_dimension_falls_back_to_2d_without_error(page):
    _open(page, "ctx", "4d")
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "2d")
    assert not ERROR_RE.search(page.locator("#view").inner_text())


# FR-1041 AC-226
@pytest.mark.parametrize("old,dim", [("map2d", "2d"), ("map3d", "3d")])
def test_ac226_old_map_urls_still_work_and_keep_select_and_dimension(page, old, dim):
    page.goto(page.url.split("#")[0] + f"#/{old}?select=FR-001")
    page.wait_for_load_state("networkidle")
    view = page.locator("#view")
    expect(view).to_contain_text("FR-001")
    assert not ERROR_RE.search(view.inner_text())
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", dim)


# FR-1041 AC-226
def test_ac226_old_placement_url_moves_to_diagram_layers_and_search_query_is_kept(page):
    base = page.url.split("#")[0]
    page.goto(base + "#/placement?kind=runtime")
    page.wait_for_load_state("networkidle")
    view = page.locator("#view")
    assert view.inner_text().strip() and not ERROR_RE.search(view.inner_text())
    assert _state(page)["kind"] == "layers"
    page.goto(base + "#/map2d?q=FR-002")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#view")).to_contain_text("FR-002")


# FR-1041 AC-226 (abnormal: 存在しない ID の ?select でもリンク切れ・例外にならない)
def test_ac226_old_url_with_unknown_select_does_not_break(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(page.url.split("#")[0] + "#/map2d?select=FR-" + "9" * 4)
    page.wait_for_load_state("networkidle")
    assert not errors
    assert page.locator("#view").inner_text().strip()


# FR-1041 AC-226
def test_ac226_legacy_screen_ids_remain_valid_in_screen_image_manifest():
    manifest = json.loads((ROOT / "users-guide" / "studio" / "screen-images.json").read_text(encoding="utf-8"))
    ids = {row["screen_id"] for row in manifest["screens"]}
    assert {"map2d", "map3d", "placement"} <= ids


# FR-1041 AC-226
def test_ac226_every_nav_item_is_reachable_by_keyboard_and_command_search(page):
    nav = page.locator("#nav")
    items = nav.locator("a, button")
    n = items.count()
    assert n >= 9, "ナビ項目が 9 項目未満"
    for i in range(n):
        label = items.nth(i).inner_text().strip()
        if not label:
            continue
        page.goto(page.url.split("#")[0] + "#/dashboard")
        page.keyboard.press("Control+k")
        page.keyboard.type(label)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        assert not ERROR_RE.search(page.locator("#view").inner_text()), label
        items.nth(i).focus()
        page.keyboard.press("Enter")
        assert page.locator("#view").inner_text().strip(), label


# FR-1042 AC-227
def test_ac227_integrations_list_shows_columns_and_detail_shows_16_viewpoints_links_and_responsibility(page, int_url):
    page.goto(int_url)
    page.wait_for_load_state("networkidle")
    page.locator("#nav").get_by_text("外部連携").first.click()
    rows = page.get_by_test_id("integration-row")
    expect(rows).to_have_count(2)
    row = page.locator('[data-testid="integration-row"][data-id="INT-001"]')
    for text in ("INT-001", "受注 API", "取引先 A", "受信", "REST", "社外秘", "あり", "運用中", "FR-001"):
        expect(row).to_contain_text(text)
    row.get_by_role("link", name="INT-001").click()
    drawer = page.locator("#drawer")
    for text in ("OAuth 2.0", "責任分界", "取引先 A は送信まで", "FR-001", "AC-001", "TBD"):
        expect(drawer).to_contain_text(text)


# FR-1042 AC-227
def test_ac227_integrations_sort_filter_and_csv(page, int_url):
    page.goto(int_url)
    page.wait_for_load_state("networkidle")
    page.locator("#nav").get_by_text("外部連携").first.click()
    page.locator("#view input").first.fill("倉庫")
    rows = page.get_by_test_id("integration-row")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_attribute("data-id", "INT-002")
    with page.expect_download() as d:
        page.get_by_role("button", name=re.compile("CSV")).click()
    assert d.value.suggested_filename.endswith(".csv")
    page.locator("#view input").first.fill("")
    page.locator("#view").get_by_role("columnheader", name=re.compile("ID")).first.click()
    ids = [r.get_attribute("data-id") for r in page.get_by_test_id("integration-row").all()]
    assert sorted(ids) == sorted(["INT-001", "INT-002"]) and len(ids) == 2


# FR-1042 AC-227 (abnormal: 一致しない絞り込みは 0 件で、エラーにならない)
def test_ac227_filter_with_no_match_shows_zero_rows_without_error(page, int_url):
    page.goto(int_url)
    page.wait_for_load_state("networkidle")
    page.locator("#nav").get_by_text("外部連携").first.click()
    page.locator("#view input").first.fill("存在しない連携先-zzz")
    expect(page.get_by_test_id("integration-row")).to_have_count(0)
    assert not ERROR_RE.search(page.locator("#view").inner_text())

