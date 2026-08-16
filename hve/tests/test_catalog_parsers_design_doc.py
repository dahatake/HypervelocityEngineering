"""test_catalog_parsers_design_doc.py — ADI fan-out parser の単体テスト。

``parse_design_doc_inventory`` が Step 1 の出力（design-doc-inventory.md）から
``DOC-NNNN`` を抽出できることを検証する。
"""

from __future__ import annotations

from pathlib import Path

from hve.catalog_parsers import parse_catalog, parse_design_doc_inventory

_REL = "docs/catalog/design-doc-inventory.md"


def _write(root: Path, text: str) -> None:
    p = root / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_extracts_ids_from_table(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "# 設計書インベントリ\n\n"
        "| doc_id | 文書 | 形式 |\n"
        "| --- | --- | --- |\n"
        "| DOC-0001 | 倉庫マスタ取り込み処理 | .md |\n"
        "| DOC-0002 | 店舗マスタ取り込み処理 | .md |\n",
    )

    assert parse_design_doc_inventory(tmp_path) == ["DOC-0001", "DOC-0002"]


def test_falls_back_to_headings(tmp_path: Path) -> None:
    _write(tmp_path, "# インベントリ\n\n## DOC-0003 A\n\n## DOC-0004 B\n")

    assert parse_design_doc_inventory(tmp_path) == ["DOC-0003", "DOC-0004"]


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert parse_design_doc_inventory(tmp_path) == []


def test_duplicates_are_removed_in_order(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "| doc_id |\n| --- |\n| DOC-0002 |\n| DOC-0001 |\n| DOC-0002 |\n",
    )

    assert parse_design_doc_inventory(tmp_path) == ["DOC-0002", "DOC-0001"]


def test_registered_in_parse_catalog(tmp_path: Path) -> None:
    _write(tmp_path, "| doc_id |\n| --- |\n| DOC-0007 |\n")

    assert parse_catalog("design_doc_inventory", tmp_path) == ["DOC-0007"]
