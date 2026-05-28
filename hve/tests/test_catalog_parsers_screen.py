"""parse_screen_catalog — per-APP screen-catalog ファイル直読みの単体テスト。"""
from __future__ import annotations

from pathlib import Path

from hve.catalog_parsers import parse_screen_catalog


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


_SAMPLE_APP06 = """# Screen Catalog — APP-06

## 2. 画面一覧

| screen_id | screen_name | 所属APP |
| --------- | ----------- | ------- |
| S001 | ランディング | APP-06 |
| S002 | ワンクリック会員登録 | APP-06 |
"""

_SAMPLE_APP09 = """# Screen Catalog — APP-09

| screen_id | screen_name | 所属APP |
| --------- | ----------- | ------- |
| S001 | チャット起動 | APP-09 |
| S002 | FAQ表示 | APP-09 |
"""

_SAMPLE_APP06_DUP = """# Screen Catalog — APP-06

| screen_id | name |
| --- | --- |
| S001 | a |
| S001 | a (duplicate) |
| S002 | b |
"""


def test_parse_screen_catalog_returns_composite_keys(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "catalog" / "screen-catalog-APP-06.md", _SAMPLE_APP06)
    _write(tmp_path / "docs" / "catalog" / "screen-catalog-APP-09.md", _SAMPLE_APP09)
    result = parse_screen_catalog(tmp_path)
    assert result == [
        "APP-06-S001",
        "APP-06-S002",
        "APP-09-S001",
        "APP-09-S002",
    ]


def test_parse_screen_catalog_empty_when_no_files(tmp_path: Path) -> None:
    # docs/catalog ディレクトリ自体が存在しない場合
    assert parse_screen_catalog(tmp_path) == []
    # ディレクトリは存在するが対象ファイルがない場合
    (tmp_path / "docs" / "catalog").mkdir(parents=True)
    assert parse_screen_catalog(tmp_path) == []


def test_parse_screen_catalog_dedup_within_app(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "catalog" / "screen-catalog-APP-06.md", _SAMPLE_APP06_DUP)
    result = parse_screen_catalog(tmp_path)
    assert result == ["APP-06-S001", "APP-06-S002"]
