"""System tests for FR-1031 AC-188, FR-1032 AC-191, FR-1033 AC-194, FR-1034 AC-199/AC-200.

Expected values come only from the acceptance criteria in docs/requirements-definition.md and
PARAM-017=2 / PARAM-018=8.  The implementation is NOT the oracle.

PROVISIONAL CONTRACT (仮置き。実装者が確認し、食い違えば CONFLICT として返す。この oracle は実装に合わせて直さない):
  - ID リンク: <a> 要素（role=link）。本文がその ID、href が詳細への移動先。
  - ダッシュボードのチップ: [data-testid="history-chip"][data-kind=decision|run|requirement|impl]
    （枠は [data-testid="history-box"]）。
  - 実装状態: [data-testid="impl-bar-segment"][data-scope][data-state][data-count]、
    [data-testid="impl-kanban-column"][data-state][data-count]、[data-testid="impl-kanban-card"][data-req]、
    該当/非該当は [data-match="true|false"]。適用中の表示は [data-testid="impl-filter-status"]。
  - アーキテクチャ図: route #/map2d?view=arch / #/map3d?view=arch、window.eabkView.getState() が
    {level, locations:[{kind,name,apps,data,links:[{to,direction}]}], entities, columns}。
    配置先の記載の仮置き表記: catalog の「配置先」節の箇条書き（_placement_section 参照。Q-014 の回答待ち）。
"""
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import _base, make_zoom, DOC, CAT  # noqa: F401
from test_studio_system import ROOT, STUDIO, page, studio_url  # noqa: F401  (fixtures)

MISSING_ID = "FR-" + "9" * 4  # 実在しない ID
T_MID, T_DETAIL = 2, 8  # PARAM-017, PARAM-018
ID_RE = re.compile(r"^(G|FR|NFR(?:-[A-Z]+)?|AC|Q|PARAM|SRC|E2E|IT)-\d+$")


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


def _placement_section():
    return (
        "\n## 配置先（仮置き表記）\n"
        "- 配置先: PC / フォルダ: data/orders / データ: 注文\n"
        "- 配置先: ブラウザー / Local Storage: eabk.filters / データ: 絞り込み\n"
        "- 配置先: Power Platform / 環境: 開発 / データ: 顧客\n"
        "- 配置先: Azure / サービス: Azure SQL / アプリ: 注文API（.NET MAUI on Windows） / データ: 商品\n"
        "- 通信: 注文API → Azure SQL（送信）\n"
    )


@pytest.fixture()
def arch_url(tmp_path):
    repo = make_zoom(tmp_path / "arch")
    cat = repo / CAT
    cat.write_text(cat.read_text(encoding="utf-8") + _placement_section(), encoding="utf-8")
    proc, url = _serve(repo)
    yield url
    proc.terminate()


# FR-1031 AC-188
def test_ac188_ids_are_links_on_every_screen_and_work_by_click_and_keyboard(page):
    seen = 0
    for route in ("dashboard", "tables?tab=reqs", "impl-status", "map2d?select=FR-001"):
        page.goto(page.url.split("#")[0] + "#/" + route)
        page.wait_for_load_state("networkidle")
        ids = page.locator("#view").get_by_text(ID_RE)
        for i in range(min(ids.count(), 5)):
            el = ids.nth(i)
            if not el.is_visible():
                continue
            txt = el.inner_text().strip()
            # 実在する ID は <a>（リンク）であり、同じ対象の詳細へ移動する
            link = page.locator("#view a", has_text=re.compile(rf"^{re.escape(txt)}$")).first
            assert link.count() == 1, f"{route}: {txt} is not a link"
            seen += 1
    assert seen > 0


# FR-1031 AC-188
def test_ac188_click_and_enter_open_same_target_detail(page):
    page.goto(page.url + "#/tables?tab=reqs")
    link = page.locator("#view a", has_text=re.compile(r"^FR-001$")).first
    link.click()
    expect(page.locator("#drawer")).to_contain_text("FR-001")
    page.keyboard.press("Escape")
    link.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#drawer")).to_contain_text("FR-001")


# FR-1031 AC-188 (abnormal: 実在しない ID はリンクにせず、リンク切れも作らない)
def test_ac188_nonexistent_id_is_not_a_link(page):
    page.goto(page.url + "#/tables?tab=reqs&q=" + MISSING_ID)
    page.wait_for_load_state("networkidle")
    assert page.locator("#view a", has_text=re.compile(re.compile("^" + MISSING_ID + "$"))).count() == 0


# FR-1031 AC-188 (graph legend / chip / diagram label)
def test_ac188_legend_chip_and_diagram_label_ids_are_links(page):
    page.goto(page.url + "#/map2d?select=FR-001")
    page.wait_for_load_state("networkidle")
    assert page.locator("#view a, #view [role=link]", has_text=re.compile(r"(FR|AC|G)-\d+")).count() >= 1
    page.goto(page.url.split("#")[0] + "#/dashboard")
    page.wait_for_load_state("networkidle")
    chips = page.locator('[data-testid="history-chip"] a, [data-testid="history-chip"][role=link]')
    assert chips.count() >= 1


def _long_repo(tmp_path):
    """Long ID / long title / many items for FR-1032 (長い連続文字列を含む)."""
    repo = make_zoom(tmp_path / "wrap")
    doc = repo / DOC
    long_id = "X" * 120
    extra = "".join(
        f"\n#### FR-{900 + i} {long_id}{i} " + "とても長い題名" * 12 + "\n- 決定状態: 承認済み\n"
        for i in range(40)
    )
    doc.write_text(doc.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return repo


# FR-1032 AC-191
def test_ac191_dashboard_chips_stay_inside_their_boxes_with_long_data(browser, tmp_path):
    proc, url = _serve(_long_repo(tmp_path))
    try:
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.goto(f"{url}/#/dashboard")
        page.wait_for_load_state("networkidle")
        kinds = {c.get_attribute("data-kind") for c in page.locator('[data-testid="history-chip"]').all()}
        assert {"decision", "run", "requirement", "impl"} <= kinds
        bad = page.evaluate(
            """() => [...document.querySelectorAll('[data-testid="history-chip"]')].filter(c => {
                const b = c.closest('[data-testid="history-box"]'); if (!b) return true;
                const r = c.getBoundingClientRect(), o = b.getBoundingClientRect();
                return r.left < o.left - 0.5 || r.right > o.right + 0.5 || c.scrollWidth > c.clientWidth + 1;
            }).map(c => c.dataset.kind)"""
        )
        assert bad == []
        # 横スクロールが発生しない
        assert page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        page.context.close()
    finally:
        proc.terminate()


# FR-1033 AC-194
def test_ac194_overall_segment_click_applies_state_across_kanban_list_and_other_graphs(page):
    page.get_by_role("link", name="実装状態").first.click()
    expect(page.locator("#view")).to_contain_text("実装状態")
    seg = page.locator('[data-testid="impl-bar-segment"][data-scope="all"]').first
    state, count = seg.get_attribute("data-state"), int(seg.get_attribute("data-count"))
    seg.click()
    expect(page.locator('[data-testid="impl-filter-status"]')).to_contain_text(state)
    # かんばん: 該当状態の列の件数が区間と一致し、該当カードだけが該当
    col = page.locator(f'[data-testid="impl-kanban-column"][data-state="{state}"]')
    assert int(col.get_attribute("data-count")) == count
    assert page.locator('[data-testid="impl-kanban-card"][data-match="true"]').count() == count
    # 目的別・優先度別の他のグラフ: 該当状態の区間の合計 = 区間の件数
    for scope in ("goal", "priority"):
        total = sum(
            int(e.get_attribute("data-count"))
            for e in page.locator(f'[data-testid="impl-bar-segment"][data-scope="{scope}"][data-state="{state}"][data-match="true"]').all()
        )
        assert total == count, scope


# FR-1033 AC-194 (abnormal: 再クリックで元に戻る)
def test_ac194_reclick_restores_all_views(page):
    page.get_by_role("link", name="実装状態").first.click()
    seg = page.locator('[data-testid="impl-bar-segment"][data-scope="all"]').first
    before = page.locator('[data-testid="impl-kanban-card"][data-match="true"]').count()
    seg.click()
    seg.click()
    assert page.locator('[data-testid="impl-kanban-card"][data-match="false"]').count() == 0
    assert page.locator('[data-testid="impl-kanban-card"]').count() >= before


def _state(page, scale):
    page.evaluate("s => window.eabkView.setScale(s)", scale)
    return page.evaluate("() => window.eabkView.getState()")


def _open_arch(browser, url, route):
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"{url}/#/{route}?view=arch")
    page.wait_for_selector('[data-testid="semantic-zoom"][data-ready="true"]')
    return page


# FR-1034 AC-199
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_ac199_architecture_diagram_shows_locations_apps_data_and_links(browser, arch_url, route):
    page = _open_arch(browser, arch_url, route)
    st = _state(page, 1)
    locs = {(l["kind"], l["name"]): l for l in st["locations"]}
    assert ("PC", "data/orders") in locs  # PC はフォルダ単位
    assert any(k == "ブラウザー" and n == "eabk.filters" for k, n in locs)  # Local Storage のデータ名単位
    assert ("Power Platform", "開発") in locs  # 環境単位
    azure = locs[("Azure", "Azure SQL")]  # サービス単位
    assert "商品" in azure["data"]
    page_app = [l for l in st["locations"] if "注文API" in " ".join(l.get("apps", []))]
    assert page_app  # 実行するアプリ
    out = [x for l in st["locations"] for x in l.get("links", []) if x["direction"] == "送信"]
    assert out  # 通信先と方向
    page.context.close()


# FR-1034 AC-199 (abnormal: 記載のない配置は推測して描かない)
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_ac199_unlisted_location_is_not_invented(browser, arch_url, route):
    page = _open_arch(browser, arch_url, route)
    st = _state(page, 1)
    kinds = {l["kind"] for l in st["locations"]}
    assert kinds <= {"PC", "ブラウザー", "Power Platform", "Azure"}
    assert all("在庫" not in l["data"] for l in st["locations"])  # 在庫には配置の記載がない
    page.context.close()


# FR-1034 AC-200
@pytest.mark.parametrize("route", ["map2d", "map3d"])
def test_ac200_zoom_thresholds_switch_locations_entities_then_features_and_columns(browser, arch_url, route):
    page = _open_arch(browser, arch_url, route)
    for scale, level in [(1, "overview"), (1.99, "overview"), (T_MID, "mid"), (7.99, "mid"), (T_DETAIL, "detail"), (20, "detail")]:
        st = _state(page, scale)
        assert st["level"] == level, (scale, st["level"])
    ov = _state(page, 1)
    assert ov["locations"] and not ov.get("columns")
    mid = _state(page, T_MID)
    assert {"注文", "顧客", "商品"} <= set(mid["entities"])
    assert any(l.get("links") for l in mid["locations"])  # 通信・関係線を含む
    big = _state(page, T_DETAIL)
    cols = {c["name"]: c for c in big["columns"]["注文"]}
    assert "id" in cols and "customer_id" in cols  # 同じ ID で列まで辿れる
    page.context.close()


