"""T5 (gui-status-banner): StatusBanner / MainWindow 連携のテスト。

検証観点:
1. StatusBanner 単体 — set_status / apply_theme / 全幅 Expanding
2. MainWindow 配置 — central layout 内で nav 行の直前に配置されている
3. MainWindow._set_status — kind/message が StatusBanner に反映される
4. QStatusBar 撤去 — 左側に _status_label 相当のラベルが追加されていない
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from hve.gui.status_banner import StatusBanner  # noqa: E402
from hve.gui.status_kind import StatusKind  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# T5-1: StatusBanner 単体
# ---------------------------------------------------------------------------
def test_status_banner_default_state(qapp):
    banner = StatusBanner()
    try:
        assert banner.current_kind() is StatusKind.IDLE
        assert banner.status_label.text() == "待機"
        assert banner.description_label.text() == ""
    finally:
        banner.deleteLater()


def test_status_banner_set_status_updates_labels(qapp):
    banner = StatusBanner()
    try:
        banner.set_status(StatusKind.ERROR, "ARD が exit code=1 で終了しました")
        assert banner.current_kind() is StatusKind.ERROR
        assert banner.status_label.text() == "失敗"
        assert banner.description_label.text() == "ARD が exit code=1 で終了しました"
        # 配色（赤系）が stylesheet に反映されていることを確認
        ss = banner.styleSheet()
        assert "#ffebee" in ss  # light error background
    finally:
        banner.deleteLater()


def test_status_banner_full_width_size_policy(qapp):
    banner = StatusBanner()
    try:
        assert banner.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        # 高さは最小 40px（adversarial review #4 修正後、コンテンツ駆動の伸長は許容）
        assert banner.minimumHeight() == 40
        # 縦方向は Fixed ポリシー（sizeHint に拘束される）
        assert banner.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    finally:
        banner.deleteLater()


def test_status_banner_apply_dark_theme(qapp):
    banner = StatusBanner()
    try:
        banner.set_status(StatusKind.ERROR, "x")
        banner.apply_theme("dark")
        ss = banner.styleSheet()
        # ダークテーマでは error 背景が #b71c1c
        assert "#b71c1c" in ss
    finally:
        banner.deleteLater()


def test_status_banner_rejects_invalid_kind(qapp):
    banner = StatusBanner()
    try:
        with pytest.raises(TypeError):
            banner.set_status("error", "msg")  # type: ignore[arg-type]
    finally:
        banner.deleteLater()


# ---------------------------------------------------------------------------
# T5-2 / T5-3 / T5-4: MainWindow 連携
# ---------------------------------------------------------------------------
@pytest.fixture
def main_window(qapp, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from hve.gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


def test_main_window_has_status_banner_above_nav(main_window):
    """T5-2: バナーが central layout 内で nav 行 (QHBoxLayout) の直前に配置されている。"""
    central = main_window.centralWidget()
    layout = central.layout()
    assert isinstance(layout, QVBoxLayout)

    banner_index = None
    nav_index = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        w = item.widget()
        if isinstance(w, StatusBanner):
            banner_index = i
        elif item.layout() is not None and isinstance(item.layout(), QHBoxLayout):
            # nav は QHBoxLayout として addLayout されている
            nav_index = i
    assert banner_index is not None, "StatusBanner が central layout に存在しない"
    assert nav_index is not None, "nav の QHBoxLayout が見つからない"
    assert banner_index == nav_index - 1, "StatusBanner は nav 行の直前に配置されること"


def test_main_window_set_status_reflects_on_banner(main_window):
    """T5-3: `_set_status(kind, msg)` がバナーに反映される。"""
    main_window._set_status(StatusKind.ERROR, "ARD が exit code=1 で終了しました")
    assert main_window._status_banner.current_kind() is StatusKind.ERROR
    assert main_window._status_banner.status_label.text() == "失敗"
    # 互換: _status_label は description_label を指す
    assert main_window._status_label is main_window._status_banner.description_label
    assert "ARD" in main_window._status_label.text()


def test_qstatusbar_has_no_left_status_label(main_window):
    """T5-4: QStatusBar 左側から _status_label 相当の QLabel が撤去されている。

    認証ステータス表示は廃止済み。残置するのは
    [利用できるモデルの取得] ボタンのみ。
    """
    sb = main_window.statusBar()
    labels = sb.findChildren(QLabel)
    # 旧 _status_label（初期値「ワークフローを選択してください」）が QStatusBar 内に居ないこと
    for lab in labels:
        # _status_label は description_label にエイリアスされており、
        # それは StatusBanner の子であって QStatusBar の子ではない
        assert lab is not main_window._status_banner.description_label
        assert lab is not main_window._status_banner.status_label


def test_refresh_navigation_does_not_overwrite_completed_status(main_window, monkeypatch):
    """Adversarial review #1/#2 regression:

    Step 2 表示中に process が走っていない（完了済み）状態では、
    `_refresh_navigation` がバナーの完了状態（例: SUCCESS）を `RUNNING/実行中` で
    上書きしてはならない。
    """
    # Step 2 へ切替
    from hve.gui.main_window import _STEP_WORKBENCH
    main_window._stack.setCurrentIndex(_STEP_WORKBENCH)

    # WorkbenchPage の is_running を False にスタブ（処理完了済みの状態）
    monkeypatch.setattr(
        main_window._page_workbench, "is_running", lambda: False
    )

    # 完了状態を明示的に設定
    main_window._set_status(StatusKind.SUCCESS, "Step 2: 完了 (all workflows succeeded)")
    assert main_window._status_banner.current_kind() is StatusKind.SUCCESS

    # _refresh_navigation を呼んでも SUCCESS が保持されること（RUNNING に上書きされない）
    main_window._refresh_navigation()
    assert main_window._status_banner.current_kind() is StatusKind.SUCCESS, (
        "_refresh_navigation が完了状態を RUNNING/実行中 で上書きしている "
        "（adversarial review Critical #1/#2 退行）"
    )
    assert "完了" in main_window._status_label.text()
