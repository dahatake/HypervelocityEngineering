"""Studio system tests for FR-1027 AC-174, FR-1028 AC-177, FR-1029 AC-179, NFR-PERF-004 AC-183.

Expected values come from the acceptance criteria and PARAM-017=2 / PARAM-018=8 / PARAM-019=300 /
PARAM-020=5000 / PARAM-022=3 s only.  PROVISIONAL CONTRACT (仮置き, see tests/system/entity_repo.py header):
fixture notation for columns/relations, and the Studio state contract
    [data-testid="semantic-zoom"][data-scale][data-level][data-ready], window.eabkView.setScale/getState,
    2D DOM [data-entity] / [data-edge][data-from][data-to][data-kind] / [data-column], routes #/entities #/map2d #/map3d.
3D is a canvas, so it is verified only through window.eabkView.getState().
"""
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_large, make_zoom

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "EABK-Studio" / "studio.py"
T_MID, T_DETAIL = 2, 8  # PARAM-017, PARAM-018
ROUTES = ["entities", "map2d", "map3d"]
ALL = {"注文", "顧客", "商品", "在庫"}


def _serve(repo):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("EABK Studio did not start")


@pytest.fixture()
def zoom_url(tmp_path):
    proc, url = _serve(make_zoom(tmp_path / "zoom"))
    yield url
    proc.terminate()


def _open(browser, url, route):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"{url}/#/{route}")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    return page


def _state(page, scale):
    page.evaluate("s => window.eabkView.setScale(s)", scale)
    page.wait_for_function(
        "s => Math.abs(Number(document.querySelector('[data-testid=\"semantic-zoom\"]').dataset.scale) - s) < 1e-6", arg=scale)
    return page.evaluate("() => window.eabkView.getState()")


def _level(page):
    return page.locator('[data-testid="semantic-zoom"]').get_attribute("data-level")


def _edge_set(st):
    return {(e["from"], e["to"], e["kind"]) for e in st["edges"]}


# FR-1027 AC-174
@pytest.mark.parametrize("route", ROUTES)
def test_ac174_thresholds_switch_granularity_up_and_down_without_losing_entities(browser, zoom_url, route):
    page = _open(browser, zoom_url, route)
    up = [(1, "overview"), (1.99, "overview"), (T_MID, "mid"), (7.99, "mid"), (T_DETAIL, "detail"), (20, "detail")]
    down = list(reversed(up))
    for seq in (up, down):  # 倍率を上げても下げても同じ境界
        for scale, level in seq:
            st = _state(page, scale)
            assert st["level"] == level, (scale, st["level"])
            assert _level(page) == level  # 現在の粒度が識別できる
            covered = {e for c in st["clusters"] for e in c["entities"]} if level == "overview" else set(st["entities"])
            assert covered == ALL  # どの粒度でも欠けない
    page.context.close()


# FR-1027 AC-174 (content of each level)
@pytest.mark.parametrize("route", ROUTES)
def test_ac174_levels_show_clusters_then_edges_then_columns(browser, zoom_url, route):
    page = _open(browser, zoom_url, route)
    ov = _state(page, 1)
    sizes = sorted(c["count"] for c in ov["clusters"])
    assert sizes == [1, 3]  # 注文・顧客・商品 は連結、在庫は単独のクラスター
    mid = _state(page, T_MID)
    assert ("注文", "顧客", "外部キー") in _edge_set(mid)
    assert ("注文", "商品", "参照") in _edge_set(mid)
    assert not any("在庫" in (e["from"], e["to"]) for e in mid["edges"])  # 異常系: 関係のない在庫に線を作らない
    assert mid.get("columns") in (None, {}) or not mid["columns"].get("注文")  # 「中」では列を出さない
    big = _state(page, T_DETAIL)
    cols = {c["name"]: c for c in big["columns"]["注文"]}
    assert (cols["id"]["type"], cols["id"]["key"]) == ("int", "主キー")
    assert (cols["customer_id"]["key"], cols["customer_id"]["ref"]) == ("外部キー", "顧客.id")
    page.context.close()


# FR-1027 AC-174 (abnormal: out-of-range scale and unlisted columns are not invented)
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_ac174_below_whole_fit_stays_overview_and_undefined_columns_not_invented(browser, zoom_url, route):
    page = _open(browser, zoom_url, route)
    assert _state(page, 0.5)["level"] == "overview"  # 1 未満でも粒度は「全体」（欠けない）
    big = _state(page, T_DETAIL)
    assert not big["columns"].get("商品")  # 列未記載のエンティティに推測した列を出さない
    page.context.close()


# FR-1028 AC-177
def test_ac177_2d_mid_shows_labelled_typed_edges_and_highlights_direct_neighbours(browser, zoom_url):
    page = _open(browser, zoom_url, "map2d")
    _state(page, T_MID)
    fk = page.locator('[data-edge][data-from="注文"][data-to="顧客"]')
    ref = page.locator('[data-edge][data-from="注文"][data-to="商品"]')
    expect(fk).to_have_count(1)
    expect(ref).to_have_count(1)
    for loc, kind in ((fk, "外部キー"), (ref, "参照")):
        expect(loc).to_have_attribute("data-kind", kind)
        expect(loc).to_contain_text(kind)  # 色だけに依存せず語でも区別
        expect(loc).to_contain_text("注文")  # 両端のエンティティ名
    assert fk.get_attribute("data-kind") != ref.get_attribute("data-kind")
    page.locator('[data-entity="注文"]').first.click()
    for n in ("顧客", "商品"):
        expect(page.locator(f'[data-entity="{n}"]').first).to_have_attribute("data-highlight", "true")
    expect(page.locator('[data-entity="在庫"]').first).not_to_have_attribute("data-highlight", "true")
    page.context.close()


# FR-1028 AC-177 (abnormal: 使用 relation is marked as its own kind; unrelated pair has no edge)
def test_ac177_2d_usage_edges_distinct_and_no_edge_for_unrelated_entities(browser, zoom_url):
    page = _open(browser, zoom_url, "map2d")
    _state(page, T_MID)
    kinds = {e.get_attribute("data-kind") for e in page.locator("[data-edge]").all()}
    assert "外部キー" in kinds and "参照" in kinds
    assert "使用" in kinds  # 要求・テーブル・コンポーネントとの関係は「使用」
    expect(page.locator('[data-edge][data-from="顧客"][data-to="在庫"], [data-edge][data-from="在庫"]')).to_have_count(0)
    page.context.close()


# FR-1029 AC-179
def test_ac179_3d_state_shows_same_information_per_level_with_kind_and_ends(browser, zoom_url):
    page = _open(browser, zoom_url, "map3d")
    assert sorted(c["count"] for c in _state(page, 1)["clusters"]) == [1, 3]
    mid = _state(page, T_MID)
    assert mid["level"] == "mid"
    assert {("注文", "顧客", "外部キー"), ("注文", "商品", "参照")} <= _edge_set(mid)
    big = _state(page, T_DETAIL)
    assert big["level"] == "detail"
    ref = {c["name"]: c["ref"] for c in big["columns"]["注文"]}
    assert ref["customer_id"] == "顧客.id"
    assert {c["name"] for c in big["columns"]["顧客"]} == {"id", "name"}
    page.context.close()


# FR-1029 AC-179 (abnormal: 3D does not invent relations absent from the data; canvas is rendered)
def test_ac179_3d_no_invented_edges_and_canvas_present(browser, zoom_url):
    page = _open(browser, zoom_url, "map3d")
    expect(page.locator("canvas").first).to_be_visible()
    mid = _state(page, T_MID)
    assert all(k in ("外部キー", "参照", "使用") for _, _, k in _edge_set(mid))
    assert not any("在庫" in (a, b) and k != "使用" for a, b, k in _edge_set(mid))
    page.context.close()


@pytest.fixture(scope="module")
def large_url(tmp_path_factory):
    proc, url = _serve(make_large(tmp_path_factory.mktemp("large")))
    yield url
    proc.terminate()


# NFR-PERF-004 AC-183
@pytest.mark.parametrize("route", ROUTES)
def test_ac183_first_display_within_3s_at_300_entities_5000_columns(browser, large_url, route, record_property):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    t0 = time.perf_counter()
    page.goto(f"{large_url}/#/{route}")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]', timeout=30000)
    elapsed = time.perf_counter() - t0
    env = f"{platform.platform()} / python {platform.python_version()} / chromium {browser.version}"
    record_property("first_display_seconds", round(elapsed, 3))  # 測定した値と環境の記録
    record_property("environment", env)
    print(f"[AC-183] {route}: {elapsed:.3f}s on {env}")
    assert elapsed <= 3.0
    page.context.close()


# NFR-PERF-004 AC-183 (abnormal: data is not truncated at scale; 省略 is declared, counts stay full)
@pytest.mark.parametrize("route", ["entities", "map2d"])
def test_ac183_large_data_counts_are_complete_even_if_display_is_partial(browser, large_url, route):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"{large_url}/#/{route}")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]', timeout=30000)
    st = page.evaluate("() => window.eabkView.getState()")
    n = len(st["entities"]) if st["level"] != "overview" else sum(c["count"] for c in st["clusters"])
    assert n == 300
    page.context.close()
