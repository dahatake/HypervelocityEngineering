"""Tests for hve.gui.app_catalog_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui import app_catalog_loader


SAMPLE = """# Application Architecture Catalog

## A) サマリ表（全APP横断）

| APP-ID | APP名 | 推薦アーキテクチャ | Confidence |
|---|---|---|---|
| APP-01 | 会員・同意管理 | Webフロントエンド + クラウド | 低 |
| APP-02 | ロイヤルティ台帳 | Webフロントエンド + クラウド | 低 |
| APP-10 | 会員サポート AI | Webフロントエンド + クラウド | 低 |

## B) 各APP詳細

| APP-ID | 結論 |
|---|---|
| APP-01 | Webフロントエンド + クラウド |
"""


def test_parse_summary_table():
    entries = app_catalog_loader.parse(SAMPLE)
    ids = [e.app_id for e in entries]
    assert ids == ["APP-01", "APP-02", "APP-10"]
    assert entries[0].name == "会員・同意管理"
    assert entries[0].display_label == "APP-01: 会員・同意管理"


def test_parse_empty_returns_empty():
    assert app_catalog_loader.parse("") == []
    assert app_catalog_loader.parse("# no tables\n") == []


def test_load_missing_file_returns_empty(tmp_path):
    app_catalog_loader.clear_cache()
    entries = app_catalog_loader.load_app_entries(tmp_path)
    assert entries == []


def test_load_and_cache(tmp_path):
    app_catalog_loader.clear_cache()
    catalog_dir = tmp_path / "docs" / "catalog"
    catalog_dir.mkdir(parents=True)
    p = catalog_dir / "app-arch-catalog.md"
    p.write_text(SAMPLE, encoding="utf-8")

    first = app_catalog_loader.load_app_entries(tmp_path)
    assert [e.app_id for e in first] == ["APP-01", "APP-02", "APP-10"]

    # ファイル削除後もキャッシュから返る
    p.unlink()
    cached = app_catalog_loader.load_app_entries(tmp_path)
    assert [e.app_id for e in cached] == ["APP-01", "APP-02", "APP-10"]

    # キャッシュクリア後は空
    app_catalog_loader.clear_cache(tmp_path)
    assert app_catalog_loader.load_app_entries(tmp_path) == []


def test_duplicate_ids_take_first():
    text = """| APP-ID | APP名 |
|---|---|
| APP-01 | first |
| APP-01 | second |
"""
    entries = app_catalog_loader.parse(text)
    assert len(entries) == 1
    assert entries[0].name == "first"


def test_parse_extracts_architecture_column():
    entries = app_catalog_loader.parse(SAMPLE)
    assert entries[0].architecture == "Webフロントエンド + クラウド"
    assert entries[1].architecture == "Webフロントエンド + クラウド"


def test_parse_two_column_table_backward_compat():
    """3 列目がない catalog でも architecture='' で抽出される（後方互換）。"""
    text = """| APP-ID | APP名 |
|---|---|
| APP-01 | foo |
"""
    entries = app_catalog_loader.parse(text)
    assert len(entries) == 1
    assert entries[0].architecture == ""
    assert entries[0].display_label == "APP-01: foo"


def test_display_label_with_kind():
    entry = app_catalog_loader.AppEntry(
        app_id="APP-01", name="foo", architecture="Webフロントエンド + クラウド"
    )
    assert entry.display_label_with_kind("web-cloud") == "APP-01: foo [web-cloud]"
    assert entry.display_label_with_kind("") == "APP-01: foo"
