"""hve.gui.markdown_preview.markdown_loader のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui.markdown_preview.markdown_loader import (
    LoaderKind,
    MarkdownLoader,
)


@pytest.fixture
def loader() -> MarkdownLoader:
    return MarkdownLoader()


def test_missing_file_returns_missing(loader: MarkdownLoader, tmp_path: Path) -> None:
    result = loader.load(tmp_path / "nonexistent.md")
    assert result.kind == LoaderKind.MISSING
    assert result.raw_text is None
    assert result.error and "見つかりません" in result.error


def test_markdown_file_is_classified(loader: MarkdownLoader, tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text("# Title\n", encoding="utf-8")
    result = loader.load(p)
    assert result.kind == LoaderKind.MARKDOWN
    assert result.raw_text == "# Title\n"


def test_python_file_is_classified_as_code(loader: MarkdownLoader, tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_text("print('hi')\n", encoding="utf-8")
    result = loader.load(p)
    assert result.kind == LoaderKind.CODE


def test_unknown_extension_is_plain(loader: MarkdownLoader, tmp_path: Path) -> None:
    p = tmp_path / "note.unknownext"
    p.write_text("plain content", encoding="utf-8")
    result = loader.load(p)
    assert result.kind == LoaderKind.PLAIN
    assert result.raw_text == "plain content"


def test_binary_file_is_detected(loader: MarkdownLoader, tmp_path: Path) -> None:
    p = tmp_path / "bin.dat"
    p.write_bytes(b"\x00\x01\x02hello")
    result = loader.load(p)
    assert result.kind == LoaderKind.BINARY
    assert result.raw_text is None


def test_oversize_file_is_detected(tmp_path: Path) -> None:
    p = tmp_path / "big.md"
    p.write_text("x" * 200, encoding="utf-8")
    loader = MarkdownLoader(max_bytes=100)
    result = loader.load(p)
    assert result.kind == LoaderKind.OVERSIZE
    assert result.size_bytes == 200


def test_cp932_fallback_decoding(tmp_path: Path) -> None:
    """utf-8 デコード失敗時は cp932 にフォールバック。"""
    p = tmp_path / "sjis.txt"
    # 「日本語」 cp932 バイト列
    p.write_bytes("日本語".encode("cp932"))
    loader = MarkdownLoader()
    result = loader.load(p)
    assert result.kind == LoaderKind.PLAIN
    assert result.raw_text == "日本語"


def test_directory_is_treated_as_missing(loader: MarkdownLoader, tmp_path: Path) -> None:
    result = loader.load(tmp_path)
    assert result.kind == LoaderKind.MISSING
