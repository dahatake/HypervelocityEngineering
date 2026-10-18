"""Integration tests for FR-1063 AC-345 / AC-346 / AC-347 (マップ 2D・3D・RPG 風の上位層の表示).
Run: python -m pytest EABK-Studio/tests/test_map_tiers_ui.py -q"""
import json
import re
import socket
import subprocess
import sys
import time

import pytest

from test_links_wrap_status_ui import ROOT, studio, _open, sync_api  # noqa: F401
from entity_repo import make_standard, DOC

GROUP = '[data-testid="tier-group"]'


def _groups(page, level=None):
    sel = GROUP + (f'[data-tier-level="{level}"]' if level else "")
    return page.evaluate(
        """(sel) => [...document.querySelectorAll(sel)].map(g => ({
            level: g.dataset.tierLevel, path: JSON.parse(g.dataset.tierPath), count: parseInt(g.dataset.count, 10)}))""", sel)


# FR-1063 AC-345: 2D の項目が上位層でまとまり、名称・件数が見え、開閉で項目が現れる／隠れる
def test_ac345_map2d_tiers_group_items_with_name_count_and_toggle(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector(GROUP)
    hier = page.evaluate("() => window.eabkStore ? 0 : 0")  # noqa: F841
    areas = _groups(page, "area")
    assert areas and all(g["count"] > 0 for g in areas)
    first = page.locator(f'{GROUP}[data-tier-level="area"]').first
    toggle = first.locator('[data-testid="tier-toggle"]').first
    assert re.search(r"\(\d+\)", toggle.get_attribute("aria-label"))      # 名称と件数が支援技術に伝わる
    if toggle.get_attribute("aria-expanded") == "true":
        toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() == 0
    toggle.click()
    assert first.locator('[data-testid="tier-item"]:visible').count() == int(first.get_attribute("data-count"))
    page.context.close()


# FR-1063 AC-346: 3D は 2D と同じ上位層の構成で、開閉状態は画面をまたいで保たれる
def test_ac346_map3d_same_tiers_as_2d_and_open_state_kept(studio):
    page = _open(studio, "map2d")
    page.wait_for_selector(GROUP)
    s2 = _groups(page)
    page.locator(f'{GROUP}[data-tier-level="area"] [data-testid="tier-toggle"]').first.click()
    opened = page.locator(f'{GROUP}[data-tier-level="area"]').first.get_attribute("data-tier-path")
    page.goto(page.url.split("#")[0] + "#/map3d")
    page.wait_for_selector(GROUP)
    assert _groups(page) == s2
    g = page.locator(f'{GROUP}[data-tier-level="area"]').first
    assert g.get_attribute("data-tier-path") == opened and g.locator('[data-testid="tier-toggle"]').first.get_attribute("aria-expanded") == "true"
    page.context.close()


# FR-1063 AC-347: RPG 風はスタートメニューから項目の上位層を会話ウィンドウに出し、城・街・住人の件数は変わらない
def test_ac347_rpg_tier_dialog_keeps_place_counts_and_closes_with_escape(studio):
    page = _open(studio, "maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    page.get_by_test_id("rpg-view").focus()
    before = page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }")
    page.keyboard.press("Space")
    page.get_by_text("項目の上位層").first.click()
    dlg = page.locator('[data-testid="rpg-dialog"]')
    dlg.wait_for()
    assert dlg.locator(GROUP).count() > 0 and dlg.locator('[data-testid="tier-toggle"]').first.get_attribute("aria-label")
    page.keyboard.press("ArrowDown")                                       # 木の中の矢印は木の操作（歩かない）
    assert page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }") == before
    page.keyboard.press("Escape")
    assert dlg.is_hidden()
    page.context.close()


# ---- 地図本体（層ごとの列・円盤）で、点が上位層ごとにまとまり、見出しで畳める
@pytest.fixture(scope="module")
def graph_studio(tmp_path_factory, studio):
    """関係を持たない（意味的ズームでなく関係グラフになる）対象。要求の 領域 の欄を 2 つに分ける。"""
    repo = make_standard(tmp_path_factory.mktemp("tiers") / "r")
    doc = repo / DOC
    out, n = [], 0
    for line in doc.read_text(encoding="utf-8").split("\n"):
        if line.startswith("- 上位:"):
            n += 1
            line += f"\u3000領域: {'アルファ' if n % 2 else 'ベータ'}"
        out.append(line)
    doc.write_text("\n".join(out), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(ROOT / "studio.py"), "--repo", str(repo), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield studio[0], f"http://127.0.0.1:{port}", n
    proc.terminate()


def _tiers2d(page):
    return json.loads(page.eval_on_selector("canvas.fill", "c => c.dataset.tiers"))


def _req_areas(tiers):
    return {t["path"][2]: t["count"] for t in tiers if t["path"][0] == "要求"}


# FR-1063 AC-345: 2D マップ本体で、要求の点が領域ごとの帯に区切られ（1 列にフラットに並ばない）、名称と件数が帯の見出しにある
def test_ac345_map2d_canvas_groups_requirement_points_by_area_with_count(graph_studio):
    browser, url, nreq = graph_studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector("canvas.fill")
    page.wait_for_function("() => document.querySelector('canvas.fill').dataset.tiers")
    areas = _req_areas(_tiers2d(page))
    assert {"アルファ", "ベータ"} <= set(areas), areas
    assert areas["アルファ"] + areas["ベータ"] == nreq
    assert all(not t["collapsed"] for t in _tiers2d(page))
    page.context.close()


# FR-1063 AC-345: 領域を畳むと下位の点が件数つきの塊に集約され、開くと点に戻る（パネルの木と同じ状態。キーボードで操作できる）
def test_ac345_map2d_collapse_and_expand_area_keeps_count_and_syncs_with_panel(graph_studio):
    browser, url, nreq = graph_studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector("canvas.fill")
    page.wait_for_function("() => document.querySelector('canvas.fill').dataset.tiers")
    grp = page.locator(f'{GROUP}[data-tier-level="area"][data-tier-path*="アルファ"]').first
    toggle = grp.locator('[data-testid="tier-toggle"]').first
    toggle.click(); toggle.click()          # 既定（地図は開く・パネルの領域は閉じる）→ 開く → 畳む
    page.wait_for_timeout(200)
    a = next(t for t in _tiers2d(page) if t["path"][2] == "アルファ" and t["path"][0] == "要求")
    assert a["collapsed"] and a["count"] == _req_areas(_tiers2d(page))["アルファ"]
    assert toggle.get_attribute("aria-expanded") == "false"
    toggle.click()
    page.wait_for_timeout(200)
    assert not next(t for t in _tiers2d(page) if t["path"][2] == "アルファ" and t["path"][0] == "要求")["collapsed"]
    page.context.close()


# FR-1063 AC-345: 見出しをキャンバス上でダブルクリックすると、領域が畳まれる（点が塊になり、記号 ▸ と件数が見出しに出る）
def test_ac345_map2d_click_area_heading_on_canvas_collapses_it(graph_studio):
    browser, url, nreq = graph_studio
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector("canvas.fill")
    page.evaluate("() => { const d = document.querySelector('.maptiers'); if (d) d.open = false; }")
    page.wait_for_timeout(600)
    box = page.locator("canvas.fill").bounding_box()
    hits = page.eval_on_selector("canvas.fill", "c => c.tierHits")
    ok = [h for h in hits if h["path"][0] == "要求" and 0 < h["x"] < box["width"] and 0 < h["y"] < box["height"]
          and page.evaluate("([x, y]) => document.elementFromPoint(x, y).tagName", [box["x"] + h["x"], box["y"] + h["y"]]) == "CANVAS"]
    assert ok, "押せる見出しがない"
    page.mouse.dblclick(box["x"] + ok[0]["x"], box["y"] + ok[0]["y"])
    page.wait_for_timeout(400)
    assert any(t["collapsed"] and t["path"] == ok[0]["path"] for t in _tiers2d(page))
    page.context.close()


# FR-1063 AC-346: 3D の層の円盤も、2D と同じ上位層（名称・件数）で点をまとめ、畳むと塊になる
def test_ac346_map3d_clusters_follow_same_tiers_as_2d_and_collapse(graph_studio):
    browser, url, nreq = graph_studio
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector("canvas.fill")
    page.wait_for_function("() => document.querySelector('canvas.fill').dataset.tiers")
    t2 = sorted((tuple(t["path"]), t["count"]) for t in _tiers2d(page) if t["path"][0] == "要求")
    page.goto(f"{url}/#/map3d")
    page.wait_for_selector(".map3d")
    page.wait_for_function("() => document.querySelector('.map3d').dataset.tiers")
    t3 = json.loads(page.eval_on_selector(".map3d", "c => c.dataset.tiers"))
    assert sorted((tuple(t["path"]), t["count"]) for t in t3 if t["path"][0] == "要求") == t2
    grp = page.locator(f'{GROUP}[data-tier-level="area"][data-tier-path*="ベータ"]').first
    toggle = grp.locator('[data-testid="tier-toggle"]').first
    toggle.click(); toggle.click()
    page.wait_for_timeout(300)
    t3 = json.loads(page.eval_on_selector(".map3d", "c => c.dataset.tiers"))
    assert next(t for t in t3 if t["path"][2] == "ベータ" and t["path"][0] == "要求")["collapsed"]
    page.context.close()


# FR-1063 AC-347: RPG 風の城・街・住人の会話から、その関連する要求の上位層（名称・件数）を辿れる。城・街・住人の件数は変わらない
def test_ac347_rpg_place_tier_dialog_lists_tiers_of_related_requirements(studio):
    page = _open(studio, "maprpg")
    page.wait_for_selector('[data-testid="rpg-view"][data-ready="true"]')
    before = page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }")
    page.evaluate("() => window.eabkView.openTierDialog('G-001')")
    dlg = page.locator('[data-testid="rpg-dialog"]')
    dlg.wait_for()
    assert "G-001" in dlg.inner_text()
    assert dlg.locator(GROUP).count() > 0
    assert all(re.search(r"\d", t) for t in dlg.locator(f'{GROUP}[data-tier-level="kind"]').all_inner_texts())
    assert page.evaluate("() => { const r = window.eabkView.getState().rpg; return [r.places.length, r.residents.length]; }") == before
    page.context.close()
