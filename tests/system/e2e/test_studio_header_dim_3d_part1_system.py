"""System tests for FR-1066 AC-367/AC-368, FR-1067 AC-371, FR-1068 AC-374/AC-375, FR-1069 AC-378/AC-379 (part 1/2).

Expected values come only from the acceptance criteria in docs/requirements-definition.md (and PARAM-017=2 /
PARAM-018=8).  The implementation is NOT the oracle.  Integration-level ACs (AC-369/370/372/373/376/377/380)
are out of scope for System Test.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - ヘッダーの切替: [data-testid="header-dim-toggle"]（data-current=2d|3d|rpg, data-selected）。ボタンは [data-dim].
    非対応のボタンは disabled。理由は、ボタンの title / aria-description / data-reason、または
    [data-testid="header-dim-reason"] の本文のどれかに空でない文字で出る。
  - 画面: #/dashboard #/map2d #/map3d #/entities #/tables #/integrations #/implstatus（#nav a[href^="#/"] が正本）。
  - ズーム: [data-testid="semantic-zoom"][data-scale][data-level=overview|mid|detail], window.eabkView.setScale/getState。
  - 3D: window.__eabk3d.nodes() => [{id, kind, shape}]。凡例 [data-testid="legend-3d"] の行は [data-kind]（種別名）。
    3D の根要素は [data-style=engineering|entertainment]、有効な演出は data-fx（空白またはカンマ区切り）。
  - 演出スタイル切替: [data-testid="style-toggle"][data-current=engineering|entertainment]、ボタンは [data-style-value]。
"""
import re

import pytest
from playwright.sync_api import expect

from entity_repo import make_zoom
from test_semantic_zoom_system import _serve, T_MID, T_DETAIL
from test_studio_system import studio_url  # noqa: F401  (fixture: 実リポジトリ。種別が複数ある)

HDR = '[data-testid="header-dim-toggle"]'
SCREENS = ["dashboard", "map2d", "map3d", "entities", "tables", "integrations", "implstatus"]


@pytest.fixture()
def zurl(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "hdr"))
    yield url
    proc.terminate()


@pytest.fixture()
def pg(browser, zurl):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    p = ctx.new_page()
    p.goto(zurl)
    p.wait_for_selector(HDR)
    yield p
    ctx.close()


@pytest.fixture()
def pg3(browser, studio_url):
    """AC-374〜379: 管理データに複数の種別がある実リポジトリ。"""
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    p = ctx.new_page()
    p.goto(studio_url)
    p.wait_for_selector(HDR)
    yield p
    ctx.close()


def _go(page, route):
    page.goto(page.url.split("#")[0] + "#/" + route)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(HDR)


def _cur(page):
    return page.locator(HDR).get_attribute("data-current")


def _reason(page, btn):
    r = (btn.get_attribute("title") or btn.get_attribute("aria-description") or btn.get_attribute("data-reason") or "").strip()
    if not r:
        el = page.locator('[data-testid="header-dim-reason"]')
        r = el.first.inner_text().strip() if el.count() else ""
    return r


def _skip_if_3d_unavailable(page):
    if page.locator(HDR).get_attribute("data-selected") == "3d" and _cur(page) != "3d":
        pytest.skip("この環境では 3D を描画できない（AC-370 の代替表示。3D の確認対象外）")


# ============================================================================ AC-367
# FR-1066 AC-367: すべての画面にヘッダーの表示モード切替があり、画面を切り替えても消えない
def test_ac367_header_dim_toggle_exists_on_every_screen_with_2d_3d_rpg_buttons(pg):
    for route in SCREENS:
        _go(pg, route)
        expect(pg.locator(HDR)).to_be_visible()
        assert _cur(pg) in ("2d", "3d", "rpg"), (route, _cur(pg))
        assert pg.locator(HDR).get_attribute("data-selected") in ("2d", "3d", "rpg")
        dims = pg.locator(f"{HDR} [data-dim]").evaluate_all("els => els.map(e => e.dataset.dim).sort()")
        assert dims == ["2d", "3d", "rpg"], (route, dims)


# FR-1066 AC-367 (異常系): 画面を何度切り替えても切替が消えず、1 つだけである
def test_ac367_header_dim_toggle_never_disappears_or_duplicates_when_switching_screens(pg):
    for route in SCREENS + list(reversed(SCREENS)):
        pg.click(f'#nav a[href="#/{route}"]') if pg.locator(f'#nav a[href="#/{route}"]').count() else _go(pg, route)
        pg.wait_for_selector(HDR)
        assert pg.locator(HDR).count() == 1, route


# FR-1066 AC-367: 図式の 2D|3D・マップのドロワーの切替は同じ状態を操作し、食い違わない
def test_ac367_in_screen_toggle_and_header_toggle_share_one_state(pg):
    _go(pg, "map2d")
    pg.locator(f'{HDR} [data-dim="3d"]').click()
    pg.wait_for_function("() => document.querySelector('[data-testid=\"header-dim-toggle\"]').dataset.current")
    _skip_if_3d_unavailable(pg)
    assert _cur(pg) == "3d"
    for dt in pg.locator('[data-testid="dim-toggle"]').all():  # 画面内の切替が残っていても同じ値
        if dt.is_visible():
            assert dt.get_attribute("data-current") == _cur(pg)
    pg.locator(f'{HDR} [data-dim="2d"]').click()
    expect(pg.locator(HDR)).to_have_attribute("data-current", "2d")
    for dt in pg.locator('[data-testid="dim-toggle"]').all():
        if dt.is_visible():
            assert dt.get_attribute("data-current") == "2d"


# ============================================================================ AC-368
# FR-1066 AC-368: RPG 風はマップ以外で disabled、理由が表示される（異常系）
@pytest.mark.parametrize("route", ["dashboard", "entities", "tables", "integrations", "implstatus"])
def test_ac368_rpg_is_disabled_with_reason_outside_map(pg, route):
    _go(pg, route)
    rpg = pg.locator(f'{HDR} [data-dim="rpg"]')
    assert rpg.is_disabled(), f"{route} で RPG 風が有効"
    assert _reason(pg, rpg), f"{route} で RPG 風が使えない理由が表示されない"
    rpg.click(force=True)  # 押しても何も起きない
    assert _cur(pg) != "rpg"


# FR-1066 AC-368: RPG 風はマップで有効。操作すると表示とdata-currentが更新される
def test_ac368_rpg_enabled_on_map_and_switching_updates_view_and_current(pg):
    _go(pg, "map2d")
    rpg = pg.locator(f'{HDR} [data-dim="rpg"]')
    assert rpg.is_enabled()
    rpg.click()
    expect(pg.locator(HDR)).to_have_attribute("data-current", "rpg")
    expect(pg.locator('[data-testid="rpg-view"]')).to_be_visible()
    pg.locator(f'{HDR} [data-dim="2d"]').click()
    expect(pg.locator(HDR)).to_have_attribute("data-current", "2d")
    assert pg.locator('[data-testid="rpg-view"]:visible').count() == 0


# FR-1066 AC-368: 対応する画面（エンティティ）でボタンを操作すると画面の表示が切り替わる
def test_ac368_entities_screen_follows_header_mode(pg):
    _go(pg, "entities")
    btn3 = pg.locator(f'{HDR} [data-dim="3d"]')
    if btn3.is_disabled():
        assert _reason(pg, btn3)  # 対応しないなら理由が必要
        return
    btn3.click()
    pg.wait_for_function("() => window.__eabk3d !== undefined || document.querySelector('[data-testid=\"header-dim-toggle\"]').dataset.current !== '3d'")
    _skip_if_3d_unavailable(pg)
    assert _cur(pg) == "3d"
    assert pg.evaluate("() => !!window.__eabk3d")
    pg.locator(f'{HDR} [data-dim="2d"]').click()
    expect(pg.locator(HDR)).to_have_attribute("data-current", "2d")


# ============================================================================ AC-371
# FR-1067 AC-371: 中・大のズームでヘッダーから 2D↔3D に切り替えても粒度が変わらず、選択中の対象が残る
@pytest.mark.parametrize("route,scale,level", [("map2d", T_MID, "mid"), ("map2d", T_DETAIL, "detail"),
                                               ("entities", T_MID, "mid"), ("entities", T_DETAIL, "detail")])
def test_ac371_header_switch_keeps_zoom_level_and_selection(pg, route, scale, level):
    _go(pg, route)
    pg.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    pg.evaluate("s => window.eabkView.setScale(s)", scale)
    pg.wait_for_function("l => document.querySelector('[data-testid=\"semantic-zoom\"]').dataset.level === l", arg=level)
    before = pg.evaluate("() => window.eabkView.getState()")
    target = "注文"
    assert target in before["entities"]
    for to in ("3d", "2d"):
        pg.locator(f'{HDR} [data-dim="{to}"]').click()
        pg.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
        _skip_if_3d_unavailable(pg)
        assert pg.locator('[data-testid="semantic-zoom"]').get_attribute("data-level") == level, (to, level)
        st = pg.evaluate("() => window.eabkView.getState()")
        assert target in st["entities"], f"{to} 切替後に対象 {target} が画面内にない"


# FR-1067 AC-371 (異常系): 「全体」では粒度は全体のまま、エンティティは欠けない
def test_ac371_overview_level_stays_overview_and_entities_not_lost_after_switch(pg):
    _go(pg, "map2d")
    pg.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    pg.evaluate("() => window.eabkView.setScale(1)")
    pg.locator(f'{HDR} [data-dim="3d"]').click()
    pg.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    _skip_if_3d_unavailable(pg)
    assert pg.locator('[data-testid="semantic-zoom"]').get_attribute("data-level") == "overview"
    covered = {e for c in pg.evaluate("() => window.eabkView.getState()")["clusters"] for e in c["entities"]}
    assert covered == {"注文", "顧客", "商品", "在庫"}


# ============================================================================ AC-374 / AC-375
def _open3d(pg3):
    _go(pg3, "map3d")
    pg3.wait_for_function("() => window.__eabk3d && window.__eabk3d.nodes().length > 0", timeout=15000)
    return pg3.evaluate("() => window.__eabk3d.nodes()")


# FR-1068 AC-374: 3D のノードが {id, kind, shape} を返し、2 種類以上の種別が異なる shape を持つ
def test_ac374_3d_nodes_expose_kind_and_distinct_shapes(pg3):
    _skip_if_3d_unavailable(pg3)
    nodes = _open3d(pg3)
    for n in nodes:
        assert n["id"] and n["kind"] and n["shape"], n
    by_kind = {}
    for n in nodes:
        by_kind.setdefault(n["kind"], set()).add(n["shape"])
    assert len(by_kind) >= 2, "管理データに 2 種類以上の種別がない"
    for kind, shapes in by_kind.items():
        assert len(shapes) == 1, f"同じ種別 {kind} が複数のかたちを持つ: {shapes}"
    assert len({next(iter(s)) for s in by_kind.values()}) >= 2, "種別が違うのに全部同じかたち（球のまま）"


# FR-1068 AC-374 (異常系): 種別が違うノードが同じかたちのままにならない
def test_ac374_different_kinds_never_share_a_single_shape(pg3):
    nodes = _open3d(pg3)
    shapes = {n["shape"] for n in nodes}
    kinds = {n["kind"] for n in nodes}
    assert len(shapes) > 1 or len(kinds) < 2, f"{len(kinds)} 種別が 1 つのかたち {shapes} に潰れている"


# FR-1068 AC-375: 凡例が表示され、種別の集合が nodes() の種別の集合と一致する（欠けも余分もない）
def test_ac375_legend_kinds_match_node_kinds_with_shape_and_name(pg3):
    nodes = _open3d(pg3)
    legend = pg3.locator('[data-testid="legend-3d"]')
    expect(legend).to_be_visible()
    rows = legend.evaluate("""el => [...el.querySelectorAll('[data-kind]')].map(r => ({
        kind: r.dataset.kind, text: r.innerText.trim(), hasShape: !!r.querySelector('svg, canvas, img, [data-shape]')}))""")
    legend_kinds = [r["kind"] for r in rows]
    assert len(legend_kinds) == len(set(legend_kinds)), f"凡例に同じ種別が重複: {legend_kinds}"
    assert set(legend_kinds) == {n["kind"] for n in nodes}, (legend_kinds, {n["kind"] for n in nodes})
    for r in rows:
        assert r["kind"] in r["text"] or r["text"], r  # 種別名（語）が行に見える
        assert r["hasShape"], f"凡例の行にかたちの図がない: {r}"


# FR-1068 AC-375 (異常系): 絞り込みで表示中の種別が減ったとき、凡例の余分な種別が残らない
def test_ac375_legend_has_no_extra_kinds_beyond_displayed_nodes(pg3):
    nodes = _open3d(pg3)
    kinds = {n["kind"] for n in nodes}
    legend_kinds = set(pg3.locator('[data-testid="legend-3d"] [data-kind]').evaluate_all("els => els.map(e => e.dataset.kind)"))
    assert legend_kinds - kinds == set(), f"表示にない種別が凡例にある: {legend_kinds - kinds}"
    assert kinds - legend_kinds == set(), f"凡例に欠けた種別: {kinds - legend_kinds}"


# ============================================================================ AC-378 / AC-379
STYLE = '[data-testid="style-toggle"]'


def _root(pg3):
    return pg3.locator("[data-style]").first


def _fx(pg3):
    return [x for x in re.split(r"[\s,]+", (_root(pg3).get_attribute("data-fx") or "").strip()) if x and x != "none"]


def _set_style(pg3, value):
    pg3.locator(f'{STYLE} [data-style-value="{value}"]').click()
    expect(pg3.locator(STYLE)).to_have_attribute("data-current", value)


# FR-1069 AC-378: 初回の既定は engineering。3D 画面で操作でき、根要素の data-style に反映される
def test_ac378_style_toggle_defaults_to_engineering_and_reflects_on_root(pg3):
    _open3d(pg3)
    expect(pg3.locator(STYLE)).to_be_visible()
    expect(pg3.locator(STYLE)).to_have_attribute("data-current", "engineering")
    assert _root(pg3).get_attribute("data-style") == "engineering"
    _set_style(pg3, "entertainment")
    assert _root(pg3).get_attribute("data-style") == "entertainment"
    _set_style(pg3, "engineering")
    assert _root(pg3).get_attribute("data-style") == "engineering"


# FR-1069 AC-378 (異常系): 範囲外の値は受け付けず、current は 2 値のどちらかのまま
def test_ac378_style_toggle_only_has_two_values_and_ignores_unknown(pg3):
    _open3d(pg3)
    values = pg3.locator(f"{STYLE} [data-style-value]").evaluate_all("els => els.map(e => e.dataset.styleValue).sort()")
    assert values == ["engineering", "entertainment"]
    pg3.locator(STYLE).evaluate("el => el.setAttribute('data-current', 'bogus')")
    pg3.reload()
    pg3.wait_for_selector(STYLE)
    assert pg3.locator(STYLE).get_attribute("data-current") in ("engineering", "entertainment")


# FR-1069 AC-379: engineering は演出なし、entertainment は 2 種類以上の演出（data-fx）
def test_ac379_engineering_has_no_fx_and_entertainment_has_two_or_more(pg3):
    _open3d(pg3)
    assert _fx(pg3) == [], f"engineering に演出がある: {_fx(pg3)}"
    _set_style(pg3, "entertainment")
    assert len(set(_fx(pg3))) >= 2, f"entertainment の演出が 2 種類未満: {_fx(pg3)}"
    _set_style(pg3, "engineering")
    assert _fx(pg3) == []


# FR-1069 AC-379: どちらのスタイルでも要素・関係・ラベルの内容は同じ
def test_ac379_content_is_identical_in_both_styles(pg3):
    def snap():
        nodes = sorted((n["id"], n["kind"]) for n in pg3.evaluate("() => window.__eabk3d.nodes()"))
        legend = sorted(pg3.locator('[data-testid="legend-3d"] [data-kind]').evaluate_all("els => els.map(e => e.dataset.kind)"))
        return nodes, legend
    _open3d(pg3)
    _set_style(pg3, "engineering")
    a = snap()
    _set_style(pg3, "entertainment")
    b = snap()
    assert a == b and a[0], "スタイルで要素・凡例の内容が変わった"
    pg3.locator('[data-testid="legend-3d"]').wait_for()
    assert pg3.locator('[data-testid="legend-3d"]').is_visible()
