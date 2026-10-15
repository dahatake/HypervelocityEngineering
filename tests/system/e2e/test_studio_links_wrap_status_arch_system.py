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
    # 決定記録（長い対象 ID・多数行）。書式は docs/requirements-definition.md の「決定記録」表と同じ
    decisions = "\n## 10. 決定記録\n\n| 日付 | 対象 ID | 決定 | 根拠（依頼・Q・承認依頼・包括承認） | run-id |\n|---|---|---|---|---|\n" + "".join(
        f"| 2026-10-{1 + i % 28:02d} | FR-{900 + i}、{long_id}{i} | 承認 | " + "長い根拠" * 12 + f" | 2026101{i % 10}0000 |\n"
        for i in range(30)
    )
    doc.write_text(doc.read_text(encoding="utf-8") + extra + decisions, encoding="utf-8")
    # 実行履歴（docs/run-history.md と同じ列。長い要求 ID 列・多数行）
    rows = "".join(
        f"| 20261015{i:04d} | 2026-10-15T05:00 | 2026-10-15T05:30 | abc{i:04d} | " + "長い結果" * 12
        + f" | {', '.join(f'FR-{900 + j}' for j in range(8))}, {long_id}{i} | 0 | 1/2 | 0.5h | 1/1 | 未取得 | 1 | 1/1 |\n"
        for i in range(30)
    )
    (repo / "docs" / "run-history.md").write_text(
        "# 実行履歴\n\n| run-id | 開始 | 終了 | HEAD | 結果 | 実装した要求 ID | BLOCKED | AC pass 率 | 経過時間 | 1 回目のゲート通過率 | AI クレジット | 人の介入 | 検証済み要求 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + rows,
        encoding="utf-8",
    )
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


def _rows(st):
    """アプリの行・データの行（実行場所・保存先・通信先と方向）を、比較できる形にそろえる。"""
    rows = set()
    for l in st["locations"]:
        for app in l.get("apps", []):
            rows.add(("app", l["kind"], l["name"], app))
        for data in l.get("data", []):
            rows.add(("data", l["kind"], l["name"], data))
        for link in l.get("links", []):
            rows.add(("link", l["kind"], l["name"], link["to"], link["direction"]))
    return rows


@pytest.fixture()
def dense_arch_url(tmp_path):
    repo = make_zoom(tmp_path / "arch-dense")
    cat = repo / CAT
    extra = "".join(
        f"- 配置先: Azure / サービス: Svc{i:02d} / アプリ: App{i:02d} / データ: Data{i:02d}\n"
        f"- 通信: App{i:02d} → Svc{i:02d}（送信）\n"
        for i in range(30)
    )
    cat.write_text(cat.read_text(encoding="utf-8") + _placement_section() + extra, encoding="utf-8")
    proc, url = _serve(repo)
    yield url
    proc.terminate()


# FR-1034 AC-207
def test_ac207_3d_shows_same_app_and_data_rows_as_2d_with_same_ids_and_names(browser, arch_url):
    p2 = _open_arch(browser, arch_url, "map2d")
    p3 = _open_arch(browser, arch_url, "map3d")
    for scale in (1, T_MID, T_DETAIL):
        s2, s3 = _state(p2, scale), _state(p3, scale)
        r2, r3 = _rows(s2), _rows(s3)
        assert r2, f"2D の行が空 (scale={scale})"
        assert r2 <= r3, f"3D で欠けた行 (scale={scale}): {sorted(r2 - r3)}"  # 2D で確認できる行が 3D で欠けない
        assert s3["level"] == s2["level"]
        assert set(s3["entities"]) == set(s2["entities"])  # 同じ ID・同じ名称
    # 実行場所・保存先・通信先と方向が 3D にある
    rows3 = _rows(_state(p3, 1))
    assert any(r[0] == "app" and "注文API" in r[3] for r in rows3)
    assert any(r[0] == "data" and r[2] == "Azure SQL" and r[3] == "商品" for r in rows3)
    assert any(r[0] == "link" and r[4] == "送信" for r in rows3)
    p2.context.close()
    p3.context.close()


# FR-1034 AC-207 (abnormal: 行が多く判読できなくても行を省かず、3 段の意味的ズーム（AC-200）で段階表示する)
def test_ac207_3d_with_many_rows_omits_no_row_and_stays_within_three_zoom_levels(browser, dense_arch_url):
    p2 = _open_arch(browser, dense_arch_url, "map2d")
    p3 = _open_arch(browser, dense_arch_url, "map3d")
    levels = set()
    union3 = set()
    for scale in (1, T_MID, T_DETAIL):
        s3 = _state(p3, scale)
        levels.add(s3["level"])
        union3 |= _rows(s3)
    assert levels == {"overview", "mid", "detail"}  # 4 段目を作らず、3 段で表示する
    all2 = set()
    for scale in (1, T_MID, T_DETAIL):
        all2 |= _rows(_state(p2, scale))
    assert len([r for r in all2 if r[0] == "app" and r[3].startswith("App")]) >= 30
    assert all2 <= union3, f"3D で省かれた行: {sorted(all2 - union3)[:5]}"
    p2.context.close()
    p3.context.close()


