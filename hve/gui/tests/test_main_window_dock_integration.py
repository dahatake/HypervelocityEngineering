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
def main_window(qapp, monkeypatch):
    """ユーザーの実設定ファイルから独立した MainWindow を生成する。

    実環境の ``settings_store`` は ``~/.hve/settings.toml`` 等を読み込むため、
    file_explorer_visible / markdown_preview_visible 等がユーザー操作で変動した
    結果をテストが拾ってしまう。defaults() で固定して既定動作を検証する。
    """
    from hve.gui import settings_store

    _real_defaults = settings_store.defaults()
    monkeypatch.setattr(
        settings_store,
        "load",
        lambda: {k: dict(v) for k, v in _real_defaults.items()},
    )

    def _fake_get_option(key, *, settings=None):  # noqa: ARG001
        return _real_defaults["options"].get(key)

    monkeypatch.setattr(settings_store, "get_option", _fake_get_option)
    monkeypatch.setattr(settings_store, "set_option", lambda *a, **k: None)
    # 念のため save も無効化し、テスト中に実ユーザー設定ファイルへ書き込まない。
    monkeypatch.setattr(settings_store, "save", lambda *a, **k: None)

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
    """既定設定で Explorer は表示、Preview は最小化（Wave C T09 で変更）。

    Note: MainWindow を show() していないため isVisible() は常に False。
    setVisible(False) を明示的に呼んでいない＝表示意図あり、を isHidden() で確認する。
    """
    assert main_window._file_tree_dock.isHidden() is False
    # Preview は既定で最小化（ファイル選択時に自動 show される）。
    assert main_window._preview_dock.isHidden() is True


def test_activity_bar_buttons_match_dock_visibility(main_window) -> None:
    """初期状態でトグルボタンの checked が Dock visibility と一致する。"""
    assert main_window._activity_bar.btn_explorer.isChecked() is True
    # Wave C T09: Preview の既定は非表示
    assert main_window._activity_bar.btn_preview.isChecked() is False


def test_file_selected_routes_to_preview(main_window, qapp, tmp_path: Path) -> None:
    """FileTreePanel.file_selected が PreviewPanel.load_file へ接続されている。"""
    md = tmp_path / "doc.md"
    md.write_text("# T", encoding="utf-8")
    main_window._file_tree_dock.file_selected.emit(md)
    qapp.processEvents()
    assert main_window._preview_dock._current_path == md


def test_file_selected_auto_shows_minimized_preview(main_window, qapp, tmp_path: Path) -> None:
    """Wave C T09: Preview が最小化中でも file_selected で自動的に show される。"""
    # 事前条件: Preview は非表示
    main_window._preview_dock.setVisible(False)
    assert main_window._preview_dock.isHidden() is True

    md = tmp_path / "auto.md"
    md.write_text("auto", encoding="utf-8")
    main_window._file_tree_dock.file_selected.emit(md)
    qapp.processEvents()

    # Dock が show され、ActivityBar ボタンも追随する
    assert main_window._preview_dock.isHidden() is False
    assert main_window._activity_bar.btn_preview.isChecked() is True
    assert main_window._preview_dock._current_path == md


def test_reload_explorer_roots_updates_model(main_window, tmp_path: Path, monkeypatch) -> None:
    """Wave C T08: _reload_explorer_roots() が FileTreePanel.set_roots() を呼ぶ。"""
    new_dir = tmp_path / "new-root"
    new_dir.mkdir()

    # settings_store.get_option を一時的にスタブ化
    from hve.gui import settings_store

    def _fake_get_option(key, **_kwargs):
        if key == "explorer_roots":
            return str(new_dir)
        return settings_store.defaults()["options"].get(key)

    monkeypatch.setattr(settings_store, "get_option", _fake_get_option)
    main_window._reload_explorer_roots()

    roots = main_window._file_tree_dock._model.root_paths()
    assert new_dir.resolve() in roots


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
