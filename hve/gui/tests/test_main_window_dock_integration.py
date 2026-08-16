"""hve.gui.main_window の Phase D 統合 smoke test。

Dock 統合（FileTreePanel / MarkdownPreviewPanel / TopFileTogglesBar / 双方向トグル）が
MainWindow に正しく組み込まれていること、および既存 _stack 動作に影響しない
ことを確認する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(qapp, monkeypatch, tmp_path):
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

    # repo_root を構築時に渡す。__init__ 内の GuiSessionWorkdir.create() が
    # work/run/<id>/ を作成するため、tmp_path で隔離して実リポジトリ汚染を防ぐ。
    win = MainWindow(repo_root=tmp_path)
    yield win
    win.deleteLater()


def test_main_window_has_top_file_toggles_and_docks(main_window) -> None:
    assert main_window._top_file_toggles is not None
    assert main_window._file_tree_dock is not None
    assert main_window._preview_dock is not None


def test_dock_binders_created(main_window) -> None:
    # TopFileTogglesBar.bind() が 2 本のバインダを作る
    assert len(main_window._top_file_toggles._binders) == 2


def test_docks_initially_visible_by_default(main_window) -> None:
    """既定設定で Explorer は表示、Preview は最小化（Wave C T09 で変更）。

    Note: MainWindow を show() していないため isVisible() は常に False。
    setVisible(False) を明示的に呼んでいない＝表示意図あり、を isHidden() で確認する。
    """
    assert main_window._file_tree_dock.isHidden() is False
    # Preview は既定で最小化（ファイル選択時に自動 show される）。
    assert main_window._preview_dock.isHidden() is True


def test_top_file_toggles_match_dock_visibility(main_window) -> None:
    """初期状態でトグルボタンの checked が Dock visibility と一致する。"""
    assert main_window._top_file_toggles.btn_explorer.isChecked() is True
    # Wave C T09: Preview の既定は非表示
    assert main_window._top_file_toggles.btn_preview.isChecked() is False


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

    # Dock が show され、TopFileTogglesBar ボタンも追随する
    assert main_window._preview_dock.isHidden() is False
    assert main_window._top_file_toggles.btn_preview.isChecked() is True
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


def test_copilot_dock_receives_workbench_page_reference(qapp, monkeypatch, tmp_path: Path) -> None:
    """Steering 機能配線（T11）: CopilotChatPanel.set_workbench_page が
    WorkbenchPage インスタンスで呼び出されることを確認する。

    ``CopilotChatPanel`` に ``set_workbench_page`` が未実装（T13未実施）の場合でも
    ``AttributeError`` にならず安全にスキップされることも合わせて確認する。
    """
    from hve.gui import settings_store

    _real_defaults = settings_store.defaults()
    monkeypatch.setattr(
        settings_store,
        "load",
        lambda: {k: dict(v) for k, v in _real_defaults.items()},
    )
    monkeypatch.setattr(
        settings_store,
        "get_option",
        lambda key, *, settings=None: _real_defaults["options"].get(key),  # noqa: ARG005
    )
    monkeypatch.setattr(settings_store, "set_option", lambda *a, **k: None)
    monkeypatch.setattr(settings_store, "save", lambda *a, **k: None)

    import hve.gui.main_window as main_window_mod

    calls: list = []

    class _FakeCopilotChatPanel(QDockWidget):
        def __init__(self, parent=None, *, repo_root=None) -> None:  # noqa: ARG002
            super().__init__("GitHub Copilot Chat", parent)

        def hide(self) -> None:  # QDockWidget.hide をそのまま使う
            super().hide()

        def set_workbench_page(self, page) -> None:
            calls.append(page)

    monkeypatch.setattr(main_window_mod, "CopilotChatPanel", _FakeCopilotChatPanel)

    from hve.gui.main_window import MainWindow

    win = MainWindow(repo_root=tmp_path)
    try:
        assert len(calls) == 1
        assert calls[0] is win._page_workbench
    finally:
        win.deleteLater()


def test_copilot_dock_without_set_workbench_page_does_not_raise(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    """set_workbench_page 未実装の CopilotChatPanel でも MainWindow 生成が
    AttributeError にならないことを確認する（後方互換フォールバック）。
    """
    from hve.gui import settings_store

    _real_defaults = settings_store.defaults()
    monkeypatch.setattr(
        settings_store,
        "load",
        lambda: {k: dict(v) for k, v in _real_defaults.items()},
    )
    monkeypatch.setattr(
        settings_store,
        "get_option",
        lambda key, *, settings=None: _real_defaults["options"].get(key),  # noqa: ARG005
    )
    monkeypatch.setattr(settings_store, "set_option", lambda *a, **k: None)
    monkeypatch.setattr(settings_store, "save", lambda *a, **k: None)

    import hve.gui.main_window as main_window_mod

    class _NoSetterCopilotChatPanel(QDockWidget):
        def __init__(self, parent=None, *, repo_root=None) -> None:  # noqa: ARG002
            super().__init__("GitHub Copilot Chat", parent)

    monkeypatch.setattr(main_window_mod, "CopilotChatPanel", _NoSetterCopilotChatPanel)

    from hve.gui.main_window import MainWindow

    win = MainWindow(repo_root=tmp_path)  # AttributeError にならないこと
    win.deleteLater()


def test_copilot_dock_can_reach_the_job_interaction_api(main_window) -> None:
    """FR-GUI-13: Copilot パネルは Workbench 経由でジョブ対話 API へ到達できる。"""
    page = main_window._page_workbench
    assert page.job_targets() == []
    assert page.job_channel_dir("asdw-web") is None
    assert page.session_work_root() is not None
    assert main_window._copilot_dock._workbench_page is page


def test_main_window_allocates_isolated_job_channels(main_window, tmp_path: Path) -> None:
    """FR-GUI-13: instance ごとに異なる IPC ディレクトリを払い出して登録する。"""
    first = main_window._allocate_job_channel("aad-web#APP-001")
    second = main_window._allocate_job_channel("aad-web#APP-002")
    assert first != second
    assert Path(first).is_dir() and Path(second).is_dir()
    assert main_window._page_workbench.job_channel_dir("aad-web#APP-001") == first
    assert main_window._page_workbench.job_channel_dir("aad-web#APP-002") == second
