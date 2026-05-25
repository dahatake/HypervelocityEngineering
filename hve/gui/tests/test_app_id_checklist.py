"""Tests for hve.gui.widgets.app_id_checklist — architecture_kinds フィルタ動作。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# PySide6 が無い CI 環境ではスキップ
PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import app_catalog_loader  # noqa: E402
from hve.gui.widgets.app_id_checklist import AppIdChecklist  # noqa: E402


SAMPLE = """# Application Architecture Catalog

## A) サマリ表（全APP横断）

| APP-ID | APP名 | 推薦アーキテクチャ |
|---|---|---|
| APP-01 | web-1 | Webフロントエンド + クラウド |
| APP-02 | batch-1 | データデータフロー処理 |
| APP-03 | web-2 | Webフロントエンド + クラウド |
"""


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _setup_catalog(tmp_path: Path) -> Path:
    app_catalog_loader.clear_cache()
    catalog_dir = tmp_path / "docs" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "app-arch-catalog.md").write_text(SAMPLE, encoding="utf-8")
    return tmp_path


def test_checklist_no_filter_shows_all(qapp, tmp_path):
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root)
    ids = [cb.property("app_id") for cb in cl._checkboxes]
    assert sorted(ids) == ["APP-01", "APP-02", "APP-03"]


def test_checklist_filters_by_web_cloud(qapp, tmp_path):
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root, architecture_kinds={"web-cloud"})
    ids = [cb.property("app_id") for cb in cl._checkboxes]
    assert sorted(ids) == ["APP-01", "APP-03"]


def test_checklist_filters_by_batch(qapp, tmp_path):
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root, architecture_kinds={"batch"})
    ids = [cb.property("app_id") for cb in cl._checkboxes]
    assert ids == ["APP-02"]


def test_checklist_set_architecture_kinds_switches(qapp, tmp_path):
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root, architecture_kinds={"web-cloud"})
    assert sorted(cb.property("app_id") for cb in cl._checkboxes) == ["APP-01", "APP-03"]
    cl.set_architecture_kinds({"batch"})
    assert [cb.property("app_id") for cb in cl._checkboxes] == ["APP-02"]
    cl.set_architecture_kinds(None)
    assert sorted(cb.property("app_id") for cb in cl._checkboxes) == [
        "APP-01", "APP-02", "APP-03",
    ]


def test_checklist_preserves_selection_across_kind_switch(qapp, tmp_path):
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root, architecture_kinds={"web-cloud"})
    cl.set_selected_csv("APP-01")
    cl.set_architecture_kinds({"web-cloud", "batch"})
    # APP-01 のチェックは引き継がれる
    assert cl.selected_csv() == "APP-01"


def test_checklist_persists_cross_kind_selection(qapp, tmp_path):
    """フィルタ外で選択された APP-ID が kind 切替後に復元されること（#6 修正）。"""
    root = _setup_catalog(tmp_path)
    cl = AppIdChecklist(root)  # 全 kind 表示
    # web-cloud (APP-01) と batch (APP-02) を両方選択
    cl.set_selected_csv("APP-01,APP-02")
    # batch のみに絞る → 表示上は APP-02 のみチェック
    cl.set_architecture_kinds({"batch"})
    visible_checked = [
        cb.property("app_id") for cb in cl._checkboxes if cb.isChecked()
    ]
    assert visible_checked == ["APP-02"]
    # selected_csv() は永続セレクション込みで APP-01 も返す
    assert "APP-01" in cl.selected_csv()
    # web-cloud に戻すと APP-01 のチェックが復活
    cl.set_architecture_kinds({"web-cloud"})
    visible_checked = [
        cb.property("app_id") for cb in cl._checkboxes if cb.isChecked()
    ]
    assert "APP-01" in visible_checked
