"""hve.gui.widgets.log_tabs — Wave 2 (gui-unified-workbench): "全体" / "選択中" 2 タブのログ表示ウィジェット。

WorkbenchPage の右ペインに配置される。

- "全体" タブ: 全 Workflow Instance を横断する追記型ログ (append のみ)。
- "選択中" タブ: ツリーで選択中の Workflow Instance のログ全文を差し替え表示。

API:
- :meth:`append_global` 1 行を全体タブへ追記する。末尾追従は次のイベントループで
  1 回だけ行い、同一イベントループ内の連続追記を合体する（NFR-OBS-09 (3)）。
- :meth:`set_selected_content` 選択中タブへ複数行を差し替え反映する。
- :meth:`clear` 両タブをクリアする。
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..copy_button import CopyButton
from ..fonts import preferred_log_font
from .wrap_helpers import apply_cjk_wrap


def _make_log_view() -> QPlainTextEdit:
    view = QPlainTextEdit()
    view.setReadOnly(True)
    apply_cjk_wrap(view)
    view.setMaximumBlockCount(0)  # 制限なし（全行保持）
    view.setFont(preferred_log_font(9))
    return view


class LogTabsWidget(QWidget):
    """全体 / 選択中 の 2 タブログビュー。"""

    GLOBAL_TAB = 0
    SELECTED_TAB = 1

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._global_view = _make_log_view()
        self._selected_view = _make_log_view()
        # 末尾追従の保留フラグ。同一イベントループ内の連続追記を 1 回へ合体する。
        self._tail_pending = False
        # 親を self にすることで、ウィジェット破棄後に保留中の追従が発火しない。
        self._tail_timer = QTimer(self)
        self._tail_timer.setSingleShot(True)
        self._tail_timer.timeout.connect(self._follow_tail_now)
        # "選択中" 初期表示メッセージ
        self._selected_placeholder = "（ツリーで Workflow を選択するとログを表示します）"
        # 選択済みだが該当ログが 0 行のときの表示（未選択と区別する）
        self._selected_empty_message = "（選択した項目に関連するログはありません）"
        self._selected_view.setPlainText(self._selected_placeholder)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._global_view, self.tr("全体"))
        self._tabs.addTab(self._selected_view, self.tr("選択中"))

        # コピーボタン (現在アクティブなタブの内容をコピー)
        self._copy_button = CopyButton(
            get_text=self._copy_current_tab_text,
            tooltip=self.tr("現在のタブの内容をクリップボードにコピー"),
        )

        header = QLabel(self.tr("ログ"))
        header.setStyleSheet("font-size: 12pt; font-weight: bold; padding: 2px;")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(header)
        header_row.addStretch(1)
        header_row.addWidget(self._copy_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header_row)
        layout.addWidget(self._tabs)

    # ---------- 公開 API ----------

    def append_global(self, line: str) -> None:
        """全体タブに 1 行追記する。末尾追従は次のイベントループで 1 回だけ行う。"""
        self._global_view.appendPlainText(line)
        if not self._tail_pending:
            self._tail_pending = True
            self._tail_timer.start(0)

    def _follow_tail_now(self) -> None:
        """保留中の末尾追従を実行する（NFR-OBS-09 (3)）。"""
        self._tail_pending = False
        sb = self._global_view.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def set_selected_content(self, lines: Iterable[str]) -> None:
        """選択中タブに複数行を差し替え反映し、末尾追従する。

        該当ログが 0 行（空）の場合は、未選択時プレースホルダと区別できる
        「関連ログなし」文言を表示する。
        """
        if isinstance(lines, str):
            text = lines
        else:
            text = "\n".join(str(x) for x in lines)
        if not text:
            text = self._selected_empty_message
        self._selected_view.setPlainText(text)
        sb = self._selected_view.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def clear(self) -> None:
        """両タブをクリア (選択中はプレースホルダ復元)。"""
        self._global_view.clear()
        self._selected_view.setPlainText(self._selected_placeholder)

    def show_selected_tab(self) -> None:
        """選択中タブをアクティブにする (ツリー選択時に呼ぶ)。"""
        self._tabs.setCurrentIndex(self.SELECTED_TAB)

    def global_text(self) -> str:
        return self._global_view.toPlainText()

    def global_scroll_bar(self):
        """全体タブの垂直スクロールバーを返す（未生成時は ``None``）。"""
        return self._global_view.verticalScrollBar()

    def selected_text(self) -> str:
        return self._selected_view.toPlainText()

    # ---------- 内部 ----------

    def _copy_current_tab_text(self) -> str:
        idx = self._tabs.currentIndex()
        if idx == self.SELECTED_TAB:
            return self._selected_view.toPlainText()
        return self._global_view.toPlainText()
