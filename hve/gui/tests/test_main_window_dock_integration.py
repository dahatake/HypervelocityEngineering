"""hve.gui.main_window の Phase D 統合 smoke test。

Dock 統合（FileTreePanel / MarkdownPreviewPanel / ActivityBar / 双方向トグル）が
MainWindow に正しく組み込まれていること、および既存 _stack 動作に影響しない
ことを確認する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(qapp):
    from hve.gui.main_window import MainWindow

    win = MainWindow()
    yield win
    win.deleteLater()


def test_main_window_has_activity_bar_and_docks(main_window) -> None:
    assert main_window._activity_bar is not None
    assert main_window._file_tree_dock is not None
    assert main_window._preview_dock is not None


def test_dock_binders_created(main_window) -> None:
    assert len(main_window._dock_binders) == 2


def test_docks_initially_visible_by_default(main_window) -> None:
    """既定設定で Dock は表示（モック通り、起動直後から全コンポーネント可視）。

    Note: MainWindow を show() していないため isVisible() は常に False。
    setVisible(False) を明示的に呼んでいない＝表示意図あり、を isHidden() で確認する。
    """
    assert main_window._file_tree_dock.isHidden() is False
    assert main_window._preview_dock.isHidden() is False


def test_activity_bar_buttons_match_dock_visibility(main_window) -> None:
    """初期状態でトグルボタンの checked が Dock visibility と一致する。"""
    assert main_window._activity_bar.btn_explorer.isChecked() is True
    assert main_window._activity_bar.btn_preview.isChecked() is True


def test_file_selected_routes_to_preview(main_window, qapp, tmp_path: Path) -> None:
    """FileTreePanel.file_selected が PreviewPanel.load_file へ接続されている。"""
    md = tmp_path / "doc.md"
    md.write_text("# T", encoding="utf-8")
    main_window._file_tree_dock.file_selected.emit(md)
    qapp.processEvents()
    assert main_window._preview_dock._current_path == md


def test_existing_stack_still_functional(main_window) -> None:
    """既存 _stack(QStackedWidget) の WorkflowSelect / Workbench 切替が壊れていない。"""
    assert main_window._stack is not None
    assert main_window._stack.count() == 2
    # 初期は WorkflowSelectPage
    assert main_window._stack.currentIndex() == 0


def test_session_workdir_is_added_as_root(main_window) -> None:
    """GUI セッション work_root が FileTreePanel のルートとして登録される。"""
    roots = main_window._file_tree_dock._model.root_paths()
    assert main_window._session_workdir.work_root.resolve() in roots
