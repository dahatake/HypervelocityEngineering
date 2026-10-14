"""Studio system tests for FR-1021 AC-154, FR-1022 AC-157, NFR-COMPAT-003 AC-168 (screen side).

Expected values come from the acceptance criteria only.  The route `#/entities` for the
entity x use-case matrix is a provisional contract (see tests/system/entity_repo.py).
Studio is started against a disposable repository, never against this checkout.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from entity_repo import make_other, make_standard

ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "EABK-Studio" / "studio.py"


def _serve(repo):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(repo), "--port", str(port), "--no-open"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    end = time.time() + 10
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("EABK Studio did not start")


@pytest.fixture()
def std_page(browser, tmp_path):
    proc, url = _serve(make_standard(tmp_path / "std"))
    page = browser.new_context().new_page()
    page.goto(url + "/#/entities")
    page.wait_for_load_state("networkidle")
    yield page
    page.context.close()
    proc.terminate()


@pytest.fixture()
def other_page(browser, tmp_path):
    proc, url = _serve(make_other(tmp_path / "oth"))
    page = browser.new_context().new_page()
    page.goto(url + "/#/entities")
    page.wait_for_load_state("networkidle")
    yield page
    page.context.close()
    proc.terminate()


# FR-1021 AC-154
def test_ac154_matrix_rows_columns_and_crud_words_not_color_only(std_page):
    body = std_page.locator("body")
    for text in ("注文", "顧客", "在庫", "FR-001", "FR-002"):
        expect(body).to_contain_text(text)
    row = std_page.get_by_role("row").filter(has_text="注文").first
    expect(row).to_contain_text("作成")  # 語（色だけに依存しない）
    expect(row).to_contain_text("参照")
    cust = std_page.get_by_role("row").filter(has_text="顧客").first
    expect(cust).to_contain_text("使用（使い方未記載）")


# FR-1021 AC-154 (abnormal: no relation in the data -> empty cell, nothing invented)
def test_ac154_unrelated_pairs_are_empty_and_unknown_relations_not_shown(std_page):
    stock = std_page.get_by_role("row").filter(has_text="在庫").first
    for word in ("作成", "参照", "更新", "削除", "使用"):
        expect(stock).not_to_contain_text(word)
    order = std_page.get_by_role("row").filter(has_text="注文").first
    expect(order).not_to_contain_text("削除")  # 管理データにない関係は表示されない
    expect(order).not_to_contain_text("更新")


# FR-1022 AC-157
def test_ac157_entity_detail_shows_all_items_with_source_locations(std_page):
    std_page.get_by_text("注文", exact=True).first.click()
    detail = std_page.locator("#drawer, main").filter(has_text="購入者が確定した購入内容").first
    for text in (
        "購入者が確定した購入内容",  # 説明
        "確定", "支払いが完了したとき",  # 状態と遷移の条件
        "出荷済み",
        "FR-001", "注文登録", "承認済み", "作成",  # 使う要求（ID・題名・決定状態・使い方）
        "FR-002", "注文照会",
        "orders",  # 管理テーブル
        "requirements-definition.md",  # 出典（ファイル）
    ):
        expect(detail).to_contain_text(text)
    expect(detail).to_contain_text("利用シナリオ")


# FR-1022 AC-157 (abnormal: empty items are identified, not blank)
def test_ac157_missing_items_are_marked_none_or_unwritten(std_page):
    std_page.get_by_text("顧客", exact=True).first.click()
    detail = std_page.locator("#drawer, main").filter(has_text="顧客").first
    expect(detail).to_contain_text("未記載")  # 説明・テーブルがない
    expect(detail).to_contain_text("なし")  # 状態がない等


# NFR-COMPAT-003 AC-168
def test_ac168_zero_entities_shows_guidance_without_error_or_repo_specific_names(other_page):
    body = other_page.locator("body")
    expect(body).to_contain_text("エンティティなし")
    for foreign in ("run 清掃", "EABK run", "データ層", "正常完了 run"):
        expect(body).not_to_contain_text(foreign)
    expect(body).not_to_contain_text("Traceback")
