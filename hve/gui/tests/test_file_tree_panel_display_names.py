"""hve.gui.file_explorer.file_tree_panel._resolve_display_name のユニットテスト。

ルート行の表示名を ``display_names`` マッピングで上書きする機能を検証する。
"""

from __future__ import annotations

from pathlib import Path

from hve.gui.file_explorer.file_tree_panel import _resolve_display_name


def test_returns_path_name_when_no_mapping(tmp_path: Path) -> None:
    """display_names=None のとき path.name を返す（従来挙動）。"""
    assert _resolve_display_name(tmp_path, None) == tmp_path.name


def test_returns_path_name_when_mapping_misses(tmp_path: Path) -> None:
    """マッピングにキーが無いとき path.name にフォールバックする。"""
    other = tmp_path / "other"
    other.mkdir()
    result = _resolve_display_name(tmp_path, {other.resolve(): "別名"})
    assert result == tmp_path.name


def test_returns_mapped_name_when_mapping_hits(tmp_path: Path) -> None:
    """マッピングに該当キーがあるとき上書きされた表示名を返す。"""
    label = "作業フォルダー (gui-20260522T171854-6e7c48)"
    result = _resolve_display_name(tmp_path, {tmp_path.resolve(): label})
    assert result == label


def test_mapping_key_is_resolved_path(tmp_path: Path) -> None:
    """非正規化パスを渡しても resolve() 済みキーでマッチする。"""
    label = "作業フォルダー (gui-xxx)"
    sub = tmp_path / "sub"
    sub.mkdir()
    # 入力は ``..`` 経由の非正規化パス、マッピングキーは resolve() 済み
    indirect = sub / ".." / "sub"
    result = _resolve_display_name(indirect, {sub.resolve(): label})
    assert result == label


def test_fallback_to_str_when_name_empty(tmp_path: Path) -> None:
    """path.name が空（ドライブルート等）の場合 str(path) を返す。

    Windows のドライブルート（例: ``C:\\``）は ``Path.name == ""`` になる。
    """

    class _NoName:
        """name が空文字を返す Path 互換のスタブ。"""

        name = ""

        def __str__(self) -> str:
            return "<root>"

        def resolve(self) -> "_NoName":
            return self

    result = _resolve_display_name(_NoName(), None)  # type: ignore[arg-type]
    assert result == "<root>"
