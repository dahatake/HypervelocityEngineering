"""Integration tests of the Studio semantic zoom (FR-1027 AC-175/176, FR-1028 AC-178, FR-1029 AC-180,
NFR-PERF-004 AC-184, NFR-UX-010 AC-185/186/187).  A real Studio server and Chromium (Playwright), the fixtures of
tests/system/entity_repo.py.  Thresholds: PARAM-017=2, PARAM-018=8, PARAM-021=100 ms."""
from __future__ import annotations

import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "system"))
from entity_repo import DOC, make_large, make_zoom, snapshot  # noqa: E402

STUDIO = ROOT / "EABK-Studio" / "studio.py"
SZ = '[data-testid="semantic-zoom"]'


def serve(repo: Path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open"], cwd=repo,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Studio did not start")


@pytest.fixture()
def zoom(tmp_path):
    repo = make_zoom(tmp_path / "zoom")
    proc, url = serve(repo)
    yield repo, url
    proc.terminate()


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    proc, url = serve(make_large(tmp_path_factory.mktemp("large")))
    yield url
    proc.terminate()


def open_page(browser, url, route, locale="ja-JP"):
    page = browser.new_context(viewport={"width": 1400, "height": 900}, locale=locale).new_page()
    page.goto(f"{url}/#/{route}")
    page.wait_for_selector(f'{SZ}[data-ready="true"]')
    return page


def state(page, scale=None):
    if scale is not None:
        page.evaluate("s => window.eabkView.setScale(s)", scale)
    return page.evaluate("() => window.eabkView.getState()")


# FR-1027 AC-175: zoom keeps the selection and the filter, the selected target stays on screen; wheel, buttons and keys all zoom
def test_ac175_zoom_keeps_selection_filter_and_target_on_screen(browser, zoom):
    page = open_page(browser, zoom[1], "map2d")
    state(page, 2)
    page.locator('[data-entity="顧客"]').first.click()
    page.locator(".sz-filter").fill("顧")
    for s in (3, 5, 9, 3, 2):
        st = state(page, s)
        assert st["selected"] == "顧客" and st["filter"] == "顧"
        box = page.locator('[data-entity="顧客"]').first.bounding_box()
        vp = page.locator('[data-testid="sz-viewport"]').bounding_box()
        assert box and vp["x"] <= box["x"] + box["width"] / 2 <= vp["x"] + vp["width"] and vp["y"] <= box["y"] + box["height"] / 2 <= vp["y"] + vp["height"]
    before = state(page)["scale"]
    page.locator('[data-testid="sz-zoom-in"]').click()
    after_button = state(page)["scale"]
    page.locator('[data-testid="sz-viewport"]').focus()
    page.keyboard.press("+")
    after_key = state(page)["scale"]
    page.mouse.move(700, 500)
    page.mouse.wheel(0, -300)
    page.wait_for_timeout(100)
    after_wheel = state(page)["scale"]
    assert before < after_button < after_key < after_wheel
    page.context.close()


# FR-1027 AC-176: cluster counts in the overview, every entity in exactly one cluster, zooming to a cluster reveals its entities
def test_ac176_overview_shows_cluster_counts_and_zooming_to_a_cluster_shows_entities(browser, zoom):
    page = open_page(browser, zoom[1], "map2d")
    state(page, 1)
    counts = sorted(int(c.get_attribute("data-count")) for c in page.locator("[data-cluster]").all())
    assert counts == [1, 3]
    assert "3" in page.locator('[data-cluster][data-count="3"]').first.text_content()
    st = state(page)
    names = [n for c in st["clusters"] for n in c["entities"]]
    assert sorted(names) == sorted(st["entities"]) and len(names) == len(set(names))
    big = [c for c in page.locator("[data-cluster]").all() if c.get_attribute("data-count") == "3"][0]
    big.click()
    st = state(page)
    assert st["level"] in ("mid", "detail") and page.locator('[data-entity="注文"]').count() == 1
    page.context.close()


# FR-1028 AC-178: the selected entity's columns are listed (name, type, key, reference), a reference can be followed,
# an entity without columns says so
def test_ac178_detail_lists_columns_and_references_can_be_followed(browser, zoom):
    page = open_page(browser, zoom[1], "map2d")
    state(page, 8)
    page.evaluate("() => window.eabkView.select('注文')")
    side = page.locator('[data-testid="sz-side"]')
    row = side.locator('tr[data-col-row="customer_id"]')
    expect(row).to_contain_text("int")
    expect(row).to_contain_text("外部キー")
    expect(row).to_contain_text("顧客.id")
    row.get_by_role("button", name="参照先へ移動: 顧客.id").click()
    st = state(page)
    assert st["selected"] == "顧客" and st["column"] == "id"
    assert page.locator('[data-column][data-col-entity="顧客"][data-name="id"]').count() == 1
    page.evaluate("() => window.eabkView.select('商品')")
    expect(side).to_contain_text("列未記載")
    expect(page.locator('[data-entity="商品"]')).to_contain_text("列未記載")
    page.context.close()


# FR-1029 AC-180: selection, level and filter survive 2D <-> 3D in both directions
@pytest.mark.parametrize("first,second", [("map2d", "map3d"), ("map3d", "map2d"), ("entities", "map3d")])
def test_ac180_selection_and_level_are_kept_when_switching_between_2d_and_3d(browser, zoom, first, second):
    page = open_page(browser, zoom[1], first)
    state(page, 3)
    page.evaluate("() => window.eabkView.select('顧客')")
    page.evaluate("() => window.eabkView.setFilter('客')")
    page.evaluate(f"() => {{ location.hash = '#/{second}'; }}")
    page.wait_for_selector(f'{SZ}[data-mode="{second}"][data-ready="true"]')
    st = state(page)
    assert (st["selected"], st["level"], st["scale"], st["filter"]) == ("顧客", "mid", 3, "客")
    assert page.locator(SZ).get_attribute("data-selected") == "顧客"
    page.evaluate(f"() => {{ location.hash = '#/{first}'; }}")
    page.wait_for_selector(f'{SZ}[data-mode="{first}"][data-ready="true"]')
    assert state(page)["selected"] == "顧客"
    page.context.close()


# NFR-PERF-004 AC-184: >= 20 zoom / pan / select operations at 300 entities x 5000 columns: p95 within PARAM-021 (100 ms);
# what is not drawn is declared, the counts stay complete
@pytest.mark.parametrize("route", ["entities", "map2d", "map3d"])
def test_ac184_operations_p95_within_100ms_and_omission_is_declared(browser, large, route, record_property):
    page = open_page(browser, large, route)
    js = """async (op) => { const t0 = performance.now(); op(); await new Promise((r) => requestAnimationFrame(r)); return performance.now() - t0; }"""
    times = {"zoom": [], "pan": [], "select": []}
    for i in range(24):
        times["zoom"].append(page.evaluate(f"() => ({js})(() => window.eabkView.setScale({2 + i * 0.5}))"))
    page.evaluate("() => window.eabkView.setScale(3)")
    for i in range(24):
        times["pan"].append(page.evaluate(f"""() => ({js})(() => document.querySelector('[data-testid="sz-viewport"]').dispatchEvent(new KeyboardEvent('keydown', {{ key: ['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'][{i} % 4], bubbles: true }})))"""))
    for i in range(24):
        times["select"].append(page.evaluate(f"() => ({js})(() => window.eabkView.select('E{i * 11:04d}'))"))
    p95 = {k: sorted(v)[int(len(v) * 0.95) - 1] for k, v in times.items()}
    record_property("p95_ms", str(p95))
    print(f"[AC-184] {route}: p95 ms {p95} median {statistics.median(times['zoom']):.1f}")
    assert all(v <= 100 for v in p95.values()), p95
    st = state(page)
    assert len(st["entities"]) == 300 and st["totals"] == {"entities": 300, "columns": 5000}
    assert sum(len(v) for v in st["columns"].values()) == 5000 or st["level"] != "detail"
    note = page.locator('[data-testid="sz-note"]').inner_text()
    assert "300" in note and ("省略" in note or "5000" in note)
    # an omitted target can be shown again by selecting it
    page.evaluate("() => window.eabkView.select('E0299')")
    assert state(page)["selected"] == "E0299"
    page.context.close()


# NFR-UX-010 AC-185: keyboard only: zoom, pan, level, select entity and column, follow the reference; the state is readable
def test_ac185_everything_works_from_the_keyboard_and_state_is_announced(browser, zoom):
    page = open_page(browser, zoom[1], "map2d")
    vp = page.locator('[data-testid="sz-viewport"]')
    vp.focus()
    page.keyboard.press("+")
    page.keyboard.press("ArrowRight")
    assert state(page)["scale"] > 1
    page.keyboard.press("3")
    assert state(page)["level"] == "detail"
    page.keyboard.press("2")
    assert state(page)["level"] == "mid"
    page.keyboard.press("n")  # next entity
    first = state(page)["selected"]
    assert first
    page.keyboard.press("n")
    assert state(page)["selected"] != first
    page.evaluate("() => window.eabkView.select('注文')")
    page.keyboard.press("3")
    page.keyboard.press(".")
    page.keyboard.press(".")  # id -> customer_id
    assert state(page)["column"] == "customer_id"
    page.keyboard.press("Enter")  # follow the reference
    st = state(page)
    assert (st["selected"], st["column"]) == ("顧客", "id")
    page.keyboard.press("Escape")
    assert state(page)["selected"] is None
    label = page.locator(SZ).get_attribute("aria-label")
    assert "粒度" in label and "倍率" in label
    expect(page.locator('[data-testid="sz-live"]')).to_contain_text("粒度")
    page.keyboard.press("0")
    assert state(page)["scale"] == 1
    page.context.close()


# NFR-UX-010 AC-186: the same content as tables, kinds also by word and mark, not by colour alone
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_ac186_alternative_table_has_clusters_relations_and_columns(browser, zoom, route):
    page = open_page(browser, zoom[1], route)
    page.locator('[data-testid="sz-alt"] summary').click()
    alt = page.locator('[data-testid="sz-alt"]')
    expect(alt.locator("[data-alt-cluster]")).to_have_count(2)
    texts = [r.inner_text() for r in alt.locator("[data-alt-edge]").all()]
    assert any("注文" in r and "顧客" in r and "外部キー" in r for r in texts)
    assert any("注文" in r and "商品" in r and "参照" in r for r in texts)
    assert any("使用" in r for r in texts)
    cols = " ".join(r.inner_text() for r in alt.locator("[data-alt-col]").all())
    assert "customer_id" in cols and "顧客.id" in cols and "列未記載" in cols
    page.evaluate("() => window.eabkView.setScale(2)")
    if route == "map2d":
        edge = page.locator('[data-edge][data-kind="外部キー"]').first
        assert "◆" in edge.text_content()  # 色だけでなく印と語
    page.context.close()


# NFR-UX-010 AC-187: JA / EN switch the level, the relation kinds and the column headings; no external traffic; no writes
def test_ac187_language_switch_changes_words_and_nothing_is_sent_or_written(browser, zoom):
    repo, url = zoom
    before = snapshot(repo)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="ja-JP")
    page = ctx.new_page()
    hosts = set()
    page.on("request", lambda r: hosts.add(r.url.split("/")[2]) if r.url.startswith("http") else None)
    page.goto(f"{url}/#/map2d")
    page.wait_for_selector(f'{SZ}[data-ready="true"]')
    state(page, 2)
    expect(page.locator('[data-testid="sz-level"]')).to_contain_text("粒度: 中")
    page.evaluate("() => window.eabkView.select('注文')")
    page.evaluate("() => window.eabkView.setScale(8)")
    expect(page.locator('[data-testid="sz-side"] thead')).to_contain_text("列名")
    page.locator("#lang").click()
    expect(page.locator('[data-testid="sz-level"]')).to_contain_text("Level: Detail")
    expect(page.locator('[data-testid="sz-side"] thead')).to_contain_text("Column")
    expect(page.locator('[data-testid="sz-side"] thead')).to_contain_text("References")
    state(page, 2)
    expect(page.locator('[data-edge][data-kind="外部キー"]').first).to_contain_text("Foreign key")
    page.locator("#lang").click()
    expect(page.locator('[data-testid="sz-level"]')).to_contain_text("粒度: 中")
    assert hosts <= {url.split("/")[2]}  # 外部へ通信しない
    assert snapshot(repo) == before        # 対象リポジトリを書き換えない
    ctx.close()


# FR-1027 AC-174 (threshold change): PARAM-017 / PARAM-018 move the switching scales
def test_ac174_thresholds_follow_the_parameters(browser, tmp_path):
    repo = make_zoom(tmp_path / "z")
    p = repo / DOC
    p.write_text(p.read_text(encoding="utf-8").replace("## 6. 要求", "### 3.2 パラメータ\n\n| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |\n|---|---|---|---|---|---|\n"
                 "| PARAM-017 | 中へ切り替わる倍率 | 3 | 倍 | テスト | 承認済み |\n| PARAM-018 | 大へ切り替わる倍率 | 5 | 倍 | テスト | 承認済み |\n\n## 6. 要求", 1), encoding="utf-8")
    proc, url = serve(repo)
    try:
        page = open_page(browser, url, "map2d")
        assert [state(page, s)["level"] for s in (2.5, 3, 4.9, 5)] == ["overview", "mid", "mid", "detail"]
        page.context.close()
    finally:
        proc.terminate()
