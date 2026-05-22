"""hve.gui.file_explorer.file_tree_panel カスタムタイトルバーのテスト (Wave D T11/T12)。

「📁 ファイル」見出しと explorer/preview の横並びトグルが
- 正しく生成されること
- 対象 Dock の visibility と双方向同期すること
- ActivityBar のボタンとも整合した動作になること
を検証する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel_pair(qapp, tmp_path: Path):
    from hve.gui.file_explorer.file_tree_panel import FileTreePanel
    from hve.gui.markdown_preview.preview_panel import MarkdownPreviewPanel

    docs = tmp_path / "docs"
    docs.mkdir()
    explorer = FileTreePanel([docs])
    preview = MarkdownPreviewPanel()
    explorer.setup_file_section_title_bar(preview)
    yield explorer, preview
    explorer.deleteLater()
    preview.deleteLater()


def test_title_bar_widget_installed(panel_pair) -> None:
    explorer, _ = panel_pair
    tb = explorer.titleBarWidget()
    assert tb is not None
    assert tb.objectName() == "FileTreePanelTitleBar"


def test_title_label_present(panel_pair) -> None:
    explorer, _ = panel_pair
    tb = explorer.titleBarWidget()
    labels = [
        lbl.text() for lbl in tb.findChildren(QLabel)
        if "ファイル" in lbl.text()
    ]
    assert any("📁" in t and "ファイル" in t for t in labels)


def test_toggle_buttons_exist(panel_pair) -> None:
    explorer, _ = panel_pair
    assert explorer._tb_btn_explorer is not None
    assert explorer._tb_btn_preview is not None
    assert explorer._tb_btn_explorer.isCheckable()
    assert explorer._tb_btn_preview.isCheckable()


def test_preview_toggle_changes_preview_visibility(panel_pair, qapp) -> None:
    explorer, preview = panel_pair
    # 初期状態: preview は QDockWidget 単独の既定 (親無しで isHidden=True)
    initial = not preview.isHidden()
    explorer._tb_btn_preview.setChecked(not initial)
    qapp.processEvents()
    assert (not preview.isHidden()) == (not initial)


def test_explorer_toggle_changes_explorer_visibility(panel_pair, qapp) -> None:
    explorer, _ = panel_pair
    initial = not explorer.isHidden()
    explorer._tb_btn_explorer.setChecked(not initial)
    qapp.processEvents()
    assert (not explorer.isHidden()) == (not initial)


def test_dock_visibility_change_updates_toggle(panel_pair, qapp) -> None:
    explorer, preview = panel_pair
    # 外部から visibility を変更
    preview.setVisible(True)
    qapp.processEvents()
    assert explorer._tb_btn_preview.isChecked() is True
    preview.setVisible(False)
    qapp.processEvents()
    assert explorer._tb_btn_preview.isChecked() is False


def test_title_bar_buttons_mirror_activity_bar(qapp, tmp_path: Path, monkeypatch) -> None:
    """ActivityBar とタイトルバーの両ボタンが同一 Dock を制御するよう結線される。

    Note:
        offscreen テストモードでは ``QDockWidget.visibilityChanged`` シグナルが
        非ショー親の状況で発火せず、ボタン間の追随を検証することは不可能。
        本テストは「両ボタンが存在し、同じ Dock を制御するように結線されている」
        ことを Dock 状態の直接変化で確認するに留める。
    """
    from hve.gui import settings_store

    _defaults = settings_store.defaults()
    monkeypatch.setattr(settings_store, "load", lambda: {k: dict(v) for k, v in _defaults.items()})
    monkeypatch.setattr(
        settings_store,
        "get_option",
        lambda key, *, settings=None: _defaults["options"].get(key),
    )
    monkeypatch.setattr(settings_store, "set_option", lambda *a, **k: None)

    from hve.gui.main_window import MainWindow

    win = MainWindow()
    try:
        tb_btn = win._file_tree_dock._tb_btn_preview
        ab_btn = win._activity_bar.btn_preview

        # 両ボタンともチェック可能なトグル
        assert tb_btn.isCheckable() and ab_btn.isCheckable()

        # タイトルバーボタンを ON → Preview Dock が表示される
        # （事前に False にして toggled シグナルを確実に発火させる）
        tb_btn.setChecked(False)
        qapp.processEvents()
        tb_btn.setChecked(True)
        qapp.processEvents()
        assert win._preview_dock.isHidden() is False

        # ActivityBar 経由でも同じ Dock を制御できる（True→False で toggled を発火）
        ab_btn.setChecked(True)
        qapp.processEvents()
        ab_btn.setChecked(False)
        qapp.processEvents()
        assert win._preview_dock.isHidden() is True
    finally:
        win.deleteLater()
