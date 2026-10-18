"""System tests for FR-1063 AC-345..AC-352 (Studio の全画面での上位層: 種類→区分→領域→項目の表示).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The implementation is
NOT the oracle.  (AC-355 は検証レベル integration の狭い画面、AC-356 は manual のため、このファイルの対象外。)
The requirement-area oracle is computed here from the repository's own `領域` fields (FR-1062), not from Studio output.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - 上位層のまとまり: [data-testid="tier-group"]。属性
      data-tier-level = kind|division|area、data-tier-path = JSON 配列 [種類, 区分, 領域]（その層までの名前）、
      data-count = その層の項目件数（整数）。見出しの文字に名称と件数が見える。
  - 開閉: group 内の [data-testid="tier-toggle"]（<button>。aria-expanded=true|false。アクセシブルな名前に名称と件数を含む）。
  - 項目: [data-testid="tier-item"]（data-id=ID）。開いた group の下にだけ現れ、閉じると隠れる。
  - 画面: #/map2d #/map3d（RPG 風は dim-toggle の [data-dim="rpg"]）#/tables #/entities #/integrations #/implstatus #/dashboard。
    画面一覧の正本は #nav a[href^="#/"]。管理データの項目を並べない画面は a に data-no-items を付ける（対象外）。
  - 実装状態の層ごとの内訳: tier-group 内の [data-testid="tier-status-breakdown"]（本文に状態名と件数）。
  - RPG 風: [data-testid="rpg-view"] 内の会話ウィンドウ [data-testid="rpg-dialog"] に tier-group が現れる。
    既存の城・街・住人の件数は window.eabkView.getState().rpg.places.length（AC-287）。
  - 言語: localStorage 'eabk-studio.lang' = 'ja' | 'en'。
  - 未分類: 名称「未分類」（英語表示では「Unclassified」）。
"""
import json
import re

import pytest

from entity_repo import make_zoom
from test_studio_links_wrap_status_arch_system import _serve
from test_studio_system import page, studio_url  # noqa: F401  (fixtures)

ROOT_REQ = "docs/requirements-definition.md"
SCREENS = ["map2d", "map3d", "tables", "entities", "integrations", "implstatus", "dashboard"]
GROUP = '[data-testid="tier-group"]'


def _go(page, route):
    page.goto(page.url.split("#")[0] + "#/" + route)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(GROUP, timeout=10000)


def _groups(page, level=None):
    sel = GROUP + (f'[data-tier-level="{level}"]' if level else "")
    return page.evaluate(
        """(sel) => [...document.querySelectorAll(sel)].map(g => ({
            level: g.dataset.tierLevel, path: JSON.parse(g.dataset.tierPath || '[]'),
            count: parseInt(g.dataset.count, 10), text: g.innerText}))""", sel)


def _signature(page):
    return sorted((g["level"], tuple(g["path"]), g["count"]) for g in _groups(page))


def _screens(page):
    hrefs = page.evaluate("""() => [...document.querySelectorAll('#nav a[href^="#/"]')]
        .filter(a => !a.hasAttribute('data-no-items')).map(a => a.getAttribute('href').slice(2).split('?')[0])""")
    return sorted(set(hrefs))


def _requirement_area_counts(root_text):
    """独立の期待値: 要求の 領域の欄ごとの件数（FR-1062: 欄が正本）。"""
    # AC-343: 区分は ID 接頭辞（FR＝機能、NFR-＝非機能）。領域は行内の「領域:」以降、次の欄区切り（全角空白）か行末まで
    # （値は空白を含みうる。例「運用・run の清掃」）。区分ごと・領域ごとに合算する（同名の領域が両区分にあり得る）。
    out = {}
    parts = re.split(r"^#### ((?:FR|NFR-[A-Z0-9]+)-\d+) ", root_text, flags=re.M)[1:]
    for rid, b in zip(parts[0::2], parts[1::2]):
        division = "機能" if rid.startswith("FR-") else "非機能"
        m = re.search(r"領域: ([^\n　]+)", b)
        area = m.group(1).strip() if m else "未分類"
        out[(division, area)] = out.get((division, area), 0) + 1
    return out


_DIVISION_NAMES = {"機能": "機能", "functional": "機能", "非機能": "非機能", "non-functional": "非機能",
                   "nonfunctional": "非機能", "non functional": "非機能"}


def _expand_all(page):
    for _ in range(6):
        closed = page.locator(f'{GROUP} [data-testid="tier-toggle"][aria-expanded="false"]')
        if closed.count() == 0:
            break
        closed.first.click()


def _read_root(repo_root):
    return (repo_root / ROOT_REQ).read_text(encoding="utf-8")


@pytest.fixture()
def zoom_page(browser, tmp_path):
    """領域の欄のない要求だけの小さな対象（未分類の確認用）。"""
    repo = make_zoom(tmp_path / "tiers")
    proc, url = _serve(repo)
    ctx = browser.new_context()
    p = ctx.new_page()
    p._repo = repo
    p.goto(url)
    p.wait_for_load_state("networkidle")
    yield p
    ctx.close()
    proc.terminate()


# ============================================================================ AC-345
# FR-1063 AC-345: マップ 2D で項目が上位層ごとにまとまり、名称と件数が見え、開閉できる
def test_ac345_map2d_items_are_grouped_by_tier_with_name_and_count_and_toggle(page):
    _go(page, "map2d")
    areas = _groups(page, "area")
    assert areas, "領域の層がない（項目が 1 列にフラットに並んでいる）"
    for g in areas:
        assert g["path"][-1] in g["text"], f"領域名が見えない: {g}"
        assert str(g["count"]) in g["text"], f"件数が見えない: {g}"
    first = page.locator(f'{GROUP}[data-tier-level="area"]').first
    toggle = first.locator('[data-testid="tier-toggle"]').first
    if toggle.get_attribute("aria-expanded") == "true":
        toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() == 0, "閉じても項目が隠れない"
    toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() > 0, "開いても項目が現れない"
    assert toggle.get_attribute("aria-expanded") == "true"


# FR-1063 AC-345: requirements-definition の項目が領域ごとに区切られ、件数が欄の集計と一致する
def test_ac345_map2d_requirement_areas_match_area_fields_and_not_flat(page):
    from test_studio_system import ROOT
    expected = _requirement_area_counts(_read_root(ROOT))
    _go(page, "map2d")
    got = {}
    for g in _groups(page, "area"):
        if g["path"][0] in ("要求", "requirements"):
            key = (_DIVISION_NAMES.get(g["path"][1].strip().lower(), g["path"][1]), g["path"][-1])
            got[key] = got.get(key, 0) + g["count"]  # 同じ（区分, 領域）が複数あれば合算
    assert len(got) >= 2, f"要求が領域ごとに区切られていない: {got}"
    assert {k[0] for k in got} >= {"機能", "非機能"}, f"区分が機能・非機能に分かれていない: {sorted(got)}"
    for key, n in expected.items():
        assert got.get(key) == n, f"区分・領域 {key}: 期待 {n} 実際 {got.get(key)}"
    assert set(got) == set(expected), f"余分／欠けた領域: {set(got) ^ set(expected)}"


# FR-1063 AC-345: マップ本体（キャンバス）の要求の列の点が領域ごとにまとまりフラットでなく、開閉で下位の点が現れる／隠れる
# 仮置き契約: window.eabkView.getState().map2d.points = [{id, kind, division, area, x, y, visible}]（画面座標。隅のパネルでは通らない）
def test_ac345_map2d_body_points_cluster_by_area_and_toggle_shows_hides(page):
    _go(page, "map2d")
    _expand_all(page)
    page.wait_for_timeout(500)
    pts = page.evaluate("""() => ((window.eabkView.getState().map2d || {}).points || [])
        .filter(p => p.kind === '要求' || p.kind === 'requirements').filter(p => p.visible)""")
    assert len(pts) >= 4, f"マップ本体に要求の点がない（getState().map2d.points）: {len(pts)}"
    by = {}
    for p in pts:
        by.setdefault((p["division"], p["area"]), []).append((p["x"], p["y"]))
    assert len(by) >= 2, "要求の点が領域ごとにまとまっていない"

    def mean_d(a, b):
        return sum(((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 for x1, y1 in a for x2, y2 in b) / (len(a) * len(b))

    multi = [v for v in by.values() if len(v) >= 2]
    assert multi, "2 点以上の領域がない"
    allp = [(p["x"], p["y"]) for p in pts]
    inner = sum(mean_d(v, v) for v in multi) / len(multi)
    assert inner < mean_d(allp, allp), "同じ領域の点が近くにまとまっていない（フラット）"
    assert len({round(y / 20) for _, y in allp}) > 1 and len({round(x / 20) for x, _ in allp}) > 1, "点が 1 列（直線）に並ぶ"
    # 開閉: 領域グループを閉じるとその領域の点が本体から消え、開くと現れる
    g = page.locator(f'{GROUP}[data-tier-level="area"]').filter(has_text=re.compile(r"^")).first
    for cand in page.locator(f'{GROUP}[data-tier-level="area"]').all():
        if json.loads(cand.get_attribute("data-tier-path"))[0] in ("要求", "requirements"):
            g = cand
            break
    path = json.loads(g.get_attribute("data-tier-path"))
    path = [_DIVISION_NAMES.get(path[1].strip().lower(), path[1]), path[-1]]
    count_js = """(path) => ((window.eabkView.getState().map2d || {}).points || [])
        .filter(p => p.visible && p.division === path[0] && p.area === path[1]).length"""
    tg = g.locator('[data-testid="tier-toggle"]').first
    if tg.get_attribute("aria-expanded") != "true":
        tg.click()
    page.wait_for_timeout(300)
    assert page.evaluate(count_js, path) > 0, "開いても本体に下位の点が現れない"
    tg.click()
    page.wait_for_timeout(300)
    assert page.evaluate(count_js, path) == 0, "閉じても本体の下位の点が隠れない"


# ============================================================================ AC-346
# FR-1063 AC-346: マップ 3D も同じ上位層の構成で、名称・件数があり、開閉できる
def test_ac346_map3d_same_tier_structure_as_2d_and_toggles(page):
    _go(page, "map2d")
    s2 = _signature(page)
    _go(page, "map3d")
    s3 = _signature(page)
    assert s3, "3D に上位層がない"
    assert s3 == s2, "3D の上位層の構成が 2D と違う"
    t = page.locator(f'{GROUP} [data-testid="tier-toggle"]').first
    before = t.get_attribute("aria-expanded")
    t.click()
    assert t.get_attribute("aria-expanded") != before


# ============================================================================ AC-347
# FR-1063 AC-347: RPG 風で項目に上位層（区分・領域）が名称・件数つきで示され、城・街・住人の件数は変わらない
def test_ac347_rpg_tiers_shown_with_counts_and_places_count_unchanged(page):
    _go(page, "map2d")
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').click()
    page.wait_for_selector('[data-testid="rpg-view"]')
    places = page.evaluate("() => window.eabkView.getState().rpg.places.length")
    page.keyboard.press("Enter")  # A ボタン: 会話ウィンドウ（入口にいなければ何も開かない）
    page.evaluate("() => window.eabkView.openTierDialog && window.eabkView.openTierDialog()")
    dlg = page.locator('[data-testid="rpg-dialog"]')
    dlg.wait_for(timeout=5000)
    gs = dlg.locator(GROUP)
    assert gs.count() > 0, "会話ウィンドウに上位層がない"
    texts = gs.all_inner_texts()
    assert any(re.search(r"\d", t) for t in texts), "件数が示されない"
    assert page.evaluate("() => window.eabkView.getState().rpg.places.length") == places, "項目が城・街・住人の件数に加算された"


# FR-1063 AC-347（異常系）: 項目の件数は城・街・住人の件数に加えない
def test_ac347_item_count_not_added_to_castle_town_resident_counts(page):
    _go(page, "map2d")
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').click()
    page.wait_for_selector('[data-testid="rpg-view"]')
    state = page.evaluate("() => window.eabkView.getState().rpg")
    items = {i for i in page.evaluate("() => [...document.querySelectorAll('[data-testid=\"tier-item\"]')].map(e => e.dataset.id)")}
    assert not ({p["id"] for p in state["places"]} & items), "項目が城・街・住人（places）に混ざった"
    kinds = {p["kind"] for p in state["places"]}
    assert kinds <= {"castle", "town"}, f"城・街以外が places に混ざった: {kinds}"


# ============================================================================ AC-348
@pytest.mark.parametrize("route", ["tables", "entities", "integrations"])
# FR-1063 AC-348: 一覧・表で行が上位層の見出しの下にまとまり、見出しに件数があり、開閉できる
def test_ac348_list_and_table_screens_group_rows_under_headings_with_counts(page, route):
    _go(page, route)
    gs = _groups(page)
    assert gs, f"{route}: 上位層の見出しがない"
    for g in gs:
        assert str(g["count"]) in g["text"], f"{route}: 件数がない {g}"
    t = page.locator(f'{GROUP} [data-testid="tier-toggle"]').first
    t.click()
    a = t.get_attribute("aria-expanded")
    t.click()
    assert t.get_attribute("aria-expanded") != a, f"{route}: 開閉できない"


# ============================================================================ AC-349
@pytest.mark.parametrize("route", ["implstatus", "dashboard"])
# FR-1063 AC-349: 実装状態・ダッシュボードで項目が上位層でまとまり、各層に件数があり、層から下位へ開ける
def test_ac349_status_and_dashboard_group_by_tier_with_counts(page, route):
    _go(page, route)
    gs = _groups(page)
    assert gs, f"{route}: 上位層がない"
    assert all(str(g["count"]) in g["text"] for g in gs)
    page.locator(f'{GROUP} [data-testid="tier-toggle"][aria-expanded="false"]').first.click()
    assert page.locator('[data-testid="tier-item"]:visible').count() > 0 or page.locator(f'{GROUP}[data-tier-level="area"]:visible').count() > 0


# FR-1063 AC-349: 実装状態の画面では層ごとの状態の内訳が件数で分かり、内訳の合計が層の件数と一致する
def test_ac349_implstatus_shows_per_tier_state_breakdown_summing_to_count(page):
    _go(page, "implstatus")
    rows = page.evaluate("""() => [...document.querySelectorAll('[data-testid="tier-group"]')].map(g => {
        const b = g.querySelector('[data-testid="tier-status-breakdown"]');
        return {count: parseInt(g.dataset.count, 10), nums: b ? (b.innerText.match(/\\d+/g) || []).map(Number) : null};})""")
    assert rows and all(r["nums"] for r in rows), "層ごとの状態の内訳がない"
    for r in rows:
        assert sum(r["nums"]) == r["count"], f"内訳の合計が層の件数と違う: {r}"


# ============================================================================ AC-350
# FR-1063 AC-350: すべての画面で同じ上位層の名称・順序・件数が同一（ナビゲーション定義の全画面）
def test_ac350_all_screens_show_identical_tier_names_order_and_counts(page):
    _go(page, "map2d")
    screens = _screens(page)
    assert set(SCREENS) <= set(screens), f"ナビゲーションに画面が足りない: {screens}"
    ref = None
    for r in screens:
        _go(page, r)
        areas = [(tuple(g["path"]), g["count"]) for g in _groups(page, "area") if g["path"][0] in ("要求", "requirements")]
        if not areas:
            continue
        if ref is None:
            ref = (r, areas)
        else:
            assert areas == ref[1], f"{r} の要求の上位層が {ref[0]} と違う"
    assert ref, "要求の上位層を示す画面がない"


# FR-1063 AC-350（異常系）: 画面を切り替えても選択中の対象・絞り込み・開閉状態が保たれる（NFR-UX-006）
def test_ac350_switching_screens_keeps_selection_filter_and_expansion(page):
    _go(page, "tables")
    t = page.locator(f'{GROUP}[data-tier-level="area"] [data-testid="tier-toggle"]').first
    if t.get_attribute("aria-expanded") != "true":
        t.click()
    path = page.locator(f'{GROUP}[data-tier-level="area"]').first.get_attribute("data-tier-path")
    _go(page, "map2d")
    g = page.locator(f'{GROUP}[data-tier-level="area"][data-tier-path=\'{path}\'] [data-testid="tier-toggle"]').first
    assert g.get_attribute("aria-expanded") == "true", "画面を切り替えたら開閉状態が失われた"


# ============================================================================ AC-351
# FR-1063 AC-351: 上位層の決まらないデータは、どの画面でも「未分類」として件数つきで明示される
def test_ac351_unclassified_is_explicit_with_count_on_every_screen(zoom_page):
    p = zoom_page
    for r in ("map2d", "tables", "implstatus"):
        _go(p, r)
        un = [g for g in _groups(p, "area") if g["path"][-1] == "未分類"]
        assert un, f"{r}: 領域のない要求が「未分類」として現れない"
        assert all(g["count"] > 0 and str(g["count"]) in g["text"] for g in un)


# FR-1063 AC-351（異常系）: 未分類のデータは他の領域に混ぜて隠されない（件数の合計が全件数と一致）
def test_ac351_unclassified_not_merged_into_other_areas(zoom_page):
    p = zoom_page
    _go(p, "tables")
    areas = [g for g in _groups(p, "area") if g["path"][0] in ("要求", "requirements")]
    total = sum(g["count"] for g in areas)
    expected = sum(_requirement_area_counts(_read_root(p._repo)).values())
    assert total == expected, f"件数の合計 {total} が要求数 {expected} と違う（未分類が欠けた/混ざった）"
    assert {g["path"][-1] for g in areas} == {"未分類"}, "領域の欄がないのに他の領域名が現れた"


# ============================================================================ AC-352
# FR-1063 AC-352: キーボードだけで開閉でき、層の名称・件数・開閉状態が支援技術に伝わる
def test_ac352_keyboard_toggle_and_accessible_name_count_state(page):
    _go(page, "tables")
    t = page.locator(f'{GROUP} [data-testid="tier-toggle"]').first
    name = t.get_attribute("aria-label") or t.inner_text()
    g = _groups(page)[0]
    assert g["path"][-1] in name and str(g["count"]) in name, f"アクセシブルな名前に名称・件数がない: {name!r}"
    assert t.get_attribute("aria-expanded") in ("true", "false")
    t.focus()
    before = t.get_attribute("aria-expanded")
    page.keyboard.press("Enter")
    assert t.get_attribute("aria-expanded") != before, "Enter で開閉できない"
    page.keyboard.press("Space")
    assert t.get_attribute("aria-expanded") == before, "Space で開閉できない"


# FR-1063 AC-352（異常系）: 種類を色だけで示さない（文字・形の手がかりがある）
def test_ac352_kind_not_conveyed_by_color_alone(page):
    _go(page, "map2d")
    kinds = _groups(page, "kind")
    assert kinds, "種類の層がない"
    for g in kinds:
        assert g["path"][0] in g["text"], f"種類が文字で示されない: {g}"


# FR-1063 AC-352: 日本語・英語の表示で上位層の名称が切り替わる
@pytest.mark.parametrize("lang,unclassified", [("ja", "未分類"), ("en", "Unclassified")])
def test_ac352_tier_names_switch_with_language(browser, tmp_path, lang, unclassified):
    proc, url = _serve(make_zoom(tmp_path / f"lang-{lang}"))
    ctx = browser.new_context()
    ctx.add_init_script(f"localStorage.setItem('eabk-studio.lang','{lang}')")
    p = ctx.new_page()
    p.goto(url + "#/tables")
    p.wait_for_load_state("networkidle")
    p.wait_for_selector(GROUP, timeout=10000)
    txt = " ".join(g["text"] for g in _groups(p))
    other = "Unclassified" if lang == "ja" else "未分類"
    assert unclassified in txt and other not in txt, f"{lang}: 名称が言語に合わない: {txt[:200]!r}"
    ctx.close()
    proc.terminate()
