"""hve.gui.session_menu — ヘッダー「セッション」アイコン用の QMenu ビルダ。

旧 menuBar の「セッション」メニューを廃止し、ヘッダー右上のアイコンに統合する。
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QWidget


def build_session_menu(
    parent: QWidget,
    *,
    on_new_session: Optional[Callable[[], None]] = None,
    on_stop_session: Optional[Callable[[], None]] = None,
) -> QMenu:
    """セッション操作用の QMenu を構築して返す。"""
    menu = QMenu(parent.tr("セッション"), parent)

    new_action = QAction(parent.tr("新規セッション..."), parent)
    new_action.setShortcut(QKeySequence("Ctrl+N"))
    if on_new_session is not None:
        new_action.triggered.connect(on_new_session)
    menu.addAction(new_action)

    menu.addSeparator()

    stop_action = QAction(parent.tr("セッションを停止"), parent)
    if on_stop_session is not None:
        stop_action.triggered.connect(on_stop_session)
    menu.addAction(stop_action)

    return menu
