"""System tests for FR-1053 AC-286 and FR-1055 AC-295 (EABK Studio「RPG 風」表示モード).

Expected values come only from the acceptance criteria in docs/requirements-definition.md.  The
implementation is NOT the oracle.  (AC-293 は検証レベル manual のため、このファイルの対象外。)

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - 切替: [data-testid="dim-toggle"] の中に [data-dim="2d"] / [data-dim="3d"] / [data-dim="rpg"]
    （本文に「2D」「3D」「RPG」）。現在の表示モードは [data-testid="dim-toggle"][data-current=2d|3d|rpg]。
    ルートは #/map2d（既定 2D）。
  - コマンド検索: Ctrl+K（PARAM-006）で開く入力欄 [data-testid="command-search"] に「RPG」と入れて Enter。
  - 公開状態 window.eabkView.getState():
      .dim, .selected（選択中のエンティティ名）, .scale
      .rpg = {map:{width,height,blocked:[[x,y],...]},           # 通れない地点（水・壁）
              player:{x,y,dir:"up|down|left|right"},
              places:[{id,kind:"castle|town",x,y}],              # 入口の位置
              dialog:{open,placeId}, menu:{open}, muted:bool}
  - RPG 風の領域 [data-testid="rpg-view"]、会話ウィンドウ [data-testid="rpg-dialog"]、
    スタートのメニュー [data-testid="rpg-menu"]。
  - キー割り当て（FR-1055 の適用方式）: 十字=方向キー、A=Enter、B=Esc、スタート=Space、セレクト=Shift。
"""
import pytest
from playwright.sync_api import expect

from entity_repo import make_zoom
from test_studio_links_wrap_status_arch_system import _serve  # noqa: F401

DIRS = {"ArrowUp": (0, -1), "ArrowDown": (0, 1), "ArrowLeft": (-1, 0), "ArrowRight": (1, 0)}


@pytest.fixture()
def rpg_url(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "rpg"))
    yield url
    proc.terminate()


def _open_map(browser, url):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector('[data-testid="dim-toggle"]')
    return page


def _current(page):
    return page.get_by_test_id("dim-toggle").get_attribute("data-current")


def _state(page):
    return page.evaluate("() => window.eabkView.getState()")


def _enter_rpg(page):
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').click()
    page.wait_for_selector('[data-testid="rpg-view"]')
    return _state(page)["rpg"]


def _press(page, key):
    page.keyboard.press(key)
    page.wait_for_timeout(350)  # 1 マス移動の完了待ち（押しっぱなし対策の間隔より長く）


def _walk_to(page, target):
    """方向キーだけで target(x,y) へ。公開状態の通行情報で幅優先探索し、実際のキー操作で歩く。"""
    rpg = _state(page)["rpg"]
    blocked = {tuple(b) for b in rpg["map"]["blocked"]}
    w, h = rpg["map"]["width"], rpg["map"]["height"]
    start = (rpg["player"]["x"], rpg["player"]["y"])
    prev, queue = {start: None}, [start]
    while queue:
        cur = queue.pop(0)
        if cur == target:
            break
        for key, (dx, dy) in DIRS.items():
            n = (cur[0] + dx, cur[1] + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in prev:
                prev[n] = (cur, key)
                queue.append(n)
    assert target in prev, f"到達できない入口 {target}"
    keys, cur = [], target
    while prev[cur]:
        cur, key = prev[cur][0], prev[cur][1]
        keys.append(key)
    for key in reversed(keys):
        _press(page, key)


# FR-1053 AC-286
def test_ac286_default_is_2d_and_rpg_selectable_by_toggle_keyboard_and_command_search(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    assert _current(page) == "2d"  # 最初に開いたときの既定は 2D
    for dim in ("2d", "3d", "rpg"):
        expect(page.locator(f'[data-testid="dim-toggle"] [data-dim="{dim}"]')).to_be_visible()
    # 切替操作（クリック）
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').click()
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "rpg")
    # キーボード（フォーカスして Enter）
    page.locator('[data-testid="dim-toggle"] [data-dim="3d"]').focus()
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "3d")
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').focus()
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "rpg")
    # コマンド検索
    page.locator('[data-testid="dim-toggle"] [data-dim="2d"]').click()
    page.keyboard.press("Control+k")
    page.get_by_test_id("command-search").type("RPG")
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "rpg")
    page.context.close()


# FR-1053 AC-286
def test_ac286_switching_keeps_2d_3d_content_selection_and_scale(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    page.evaluate("() => window.eabkView.setScale(3)")
    page.locator('[data-entity="注文"]').first.click()
    before = _state(page)
    assert before["selected"] == "注文"
    for dim in ("rpg", "3d", "rpg", "2d"):
        page.locator(f'[data-testid="dim-toggle"] [data-dim="{dim}"]').click()
        expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", dim)
        st = _state(page)
        assert st["selected"] == "注文"  # 選択中の対象が保たれる（NFR-UX-006）
        assert abs(st["scale"] - 3) < 1e-6  # 倍率に相当する位置が保たれる
    after = _state(page)
    assert set(after["entities"]) == set(before["entities"])  # 元の 2D の内容は変わらない
    assert {(e["from"], e["to"], e["kind"]) for e in after["edges"]} == {(e["from"], e["to"], e["kind"]) for e in before["edges"]}
    page.context.close()


# FR-1053 AC-286（異常系: 切替で入力中の内容が失われない）
def test_ac286_switching_does_not_lose_typed_input(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    box = page.locator('input[type="search"], [data-testid="search"]').first
    box.fill("注文")
    page.locator('[data-testid="dim-toggle"] [data-dim="rpg"]').click()
    expect(page.get_by_test_id("dim-toggle")).to_have_attribute("data-current", "rpg")
    page.locator('[data-testid="dim-toggle"] [data-dim="2d"]').click()
    assert page.locator('input[type="search"], [data-testid="search"]').first.input_value() == "注文"
    page.context.close()


# FR-1055 AC-295
def test_ac295_arrow_keys_move_player_one_cell_and_cannot_enter_blocked_cells(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    rpg = _enter_rpg(page)
    page.get_by_test_id("rpg-view").focus()
    blocked = {tuple(b) for b in rpg["map"]["blocked"]}
    w, h = rpg["map"]["width"], rpg["map"]["height"]
    assert blocked, "通れない地点（水・壁）がある"
    # 通れる隣接を 1 マス動く（各方向のうち、移動先が通れるもの）
    moved = 0
    for key, (dx, dy) in DIRS.items():
        p = _state(page)["rpg"]["player"]
        n = (p["x"] + dx, p["y"] + dy)
        if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked:
            _press(page, key)
            q = _state(page)["rpg"]["player"]
            assert (q["x"], q["y"]) == n  # 1 マス単位
            moved += 1
    assert moved >= 1
    # 通れない地点: 隣に blocked がある通行可能マスまで歩き、押しても動かない
    p = _state(page)["rpg"]["player"]
    goal = key_of = None
    for (bx, by) in sorted(blocked):
        for key, (dx, dy) in DIRS.items():
            c = (bx - dx, by - dy)
            if 0 <= c[0] < w and 0 <= c[1] < h and c not in blocked:
                goal, key_of = c, key
                break
        if goal:
            break
    _walk_to(page, goal)
    _press(page, key_of)
    q = _state(page)["rpg"]["player"]
    assert (q["x"], q["y"]) == goal  # 壁・水には入れない
    page.context.close()


# FR-1055 AC-295
def test_ac295_a_button_enters_place_and_b_button_closes_dialog(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    rpg = _enter_rpg(page)
    page.get_by_test_id("rpg-view").focus()
    place = rpg["places"][0]
    _walk_to(page, (place["x"], place["y"]))
    page.keyboard.press("Enter")  # A ボタン相当（決定・話す）
    expect(page.get_by_test_id("rpg-dialog")).to_be_visible()
    assert _state(page)["rpg"]["dialog"]["placeId"] == place["id"]
    page.keyboard.press("Escape")  # B ボタン相当（閉じる）
    expect(page.get_by_test_id("rpg-dialog")).to_be_hidden()
    p = _state(page)["rpg"]["player"]
    assert (p["x"], p["y"]) == (place["x"], place["y"])  # 閉じた後も位置が保たれる
    # もう 1 つの A ボタン相当: Z でも決定、X でも取消
    page.keyboard.press("z")
    expect(page.get_by_test_id("rpg-dialog")).to_be_visible()
    page.keyboard.press("x")
    expect(page.get_by_test_id("rpg-dialog")).to_be_hidden()
    page.context.close()


# FR-1055 AC-295
def test_ac295_start_opens_menu_b_goes_back_select_toggles_sound_without_mouse(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    _enter_rpg(page)
    page.get_by_test_id("rpg-view").focus()
    assert _state(page)["rpg"]["menu"]["open"] is False
    page.keyboard.press("Space")  # スタート
    expect(page.get_by_test_id("rpg-menu")).to_be_visible()
    page.keyboard.press("Escape")  # B ボタン相当（1 つ戻る）
    expect(page.get_by_test_id("rpg-menu")).to_be_hidden()
    muted = _state(page)["rpg"]["muted"]
    page.keyboard.press("Shift")  # セレクト（音の入切の選択）
    page.keyboard.press("Enter")
    assert _state(page)["rpg"]["muted"] is (not muted)
    page.context.close()


# FR-1055 AC-295（異常系: 地図の端でも外へ出ない・何もない場所での A ボタンは会話を開かない）
def test_ac295_edge_is_not_crossed_and_a_button_away_from_places_opens_nothing(browser, rpg_url):
    page = _open_map(browser, rpg_url)
    rpg = _enter_rpg(page)
    page.get_by_test_id("rpg-view").focus()
    w, h = rpg["map"]["width"], rpg["map"]["height"]
    for _ in range(max(w, h) + 2):
        _press(page, "ArrowLeft")
    p = _state(page)["rpg"]["player"]
    assert 0 <= p["x"] < w and 0 <= p["y"] < h
    places = {(pl["x"], pl["y"]) for pl in rpg["places"]}
    if (p["x"], p["y"]) not in places:
        page.keyboard.press("Enter")
        assert _state(page)["rpg"]["dialog"]["open"] is False
    page.context.close()
