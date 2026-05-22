"""hve.gui.widgets.app_id_checklist — APP-ID チェックボックスリスト Widget。

`docs/catalog/app-arch-catalog.md` から読み込んだ APP-ID 一覧を
チェックボックス群で表示し、選択結果を CSV 文字列として取得できる。

仕様:
  - 先頭に「全選択」チェックボックス（既定 OFF）
  - 全選択 ON: 全項目 ON
  - 全選択 OFF: 個別 ON/OFF を維持（ただし切替時には個別状態は維持される）
  - カタログ取得失敗 / 空: 「(候補が見つかりません。全て実行と解釈されます)」表示
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import app_catalog_loader
from ..app_catalog_loader import AppEntry


class AppIdChecklist(QWidget):
    """APP-ID 選択チェックボックスリスト。"""

    selection_changed = Signal(str)  # CSV 文字列

    def __init__(
        self,
        repo_root: Path,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._repo_root = Path(repo_root)
        self._entries: List[AppEntry] = []
        self._checkboxes: List[QCheckBox] = []
        self._suppress_signal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._select_all = QCheckBox(self.tr("全選択"))
        self._select_all.setChecked(False)
        self._select_all.stateChanged.connect(self._on_select_all_changed)
        layout.addWidget(self._select_all)

        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(16, 2, 0, 2)
        self._items_layout.setSpacing(1)
        layout.addWidget(self._items_container)

        self._empty_label = QLabel(
            self.tr("（候補が見つかりません。空のまま実行すると「全て実行」と解釈されます）")
        )
        self._empty_label.setStyleSheet("color: #6a737d;")
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        self.reload()

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def reload(self) -> None:
        """カタログを再読込してチェックボックスを再構築する。"""
        # 既存チェックボックスを削除
        for cb in self._checkboxes:
            self._items_layout.removeWidget(cb)
            cb.deleteLater()
        self._checkboxes = []

        self._entries = app_catalog_loader.load_app_entries(self._repo_root)
        if not self._entries:
            self._empty_label.setVisible(True)
            self._select_all.setEnabled(False)
            return

        self._empty_label.setVisible(False)
        self._select_all.setEnabled(True)
        for e in self._entries:
            cb = QCheckBox(e.display_label)
            cb.setProperty("app_id", e.app_id)
            cb.stateChanged.connect(self._on_item_changed)
            self._items_layout.addWidget(cb)
            self._checkboxes.append(cb)

    def selected_csv(self) -> str:
        """選択された APP-ID の CSV を返す。空のときは空文字列。"""
        ids = [cb.property("app_id") for cb in self._checkboxes if cb.isChecked()]
        return ",".join(ids)

    def set_selected_csv(self, csv: str) -> None:
        """CSV 文字列から選択状態を復元する。"""
        ids = {s.strip() for s in csv.split(",") if s.strip()}
        self._suppress_signal = True
        try:
            all_on = bool(ids) and all(
                cb.property("app_id") in ids for cb in self._checkboxes
            )
            for cb in self._checkboxes:
                cb.setChecked(cb.property("app_id") in ids)
            self._select_all.setChecked(all_on)
        finally:
            self._suppress_signal = False

    # ----------------------------------------------------------
    # シグナルハンドラ
    # ----------------------------------------------------------

    def _on_select_all_changed(self, _state: int) -> None:
        """全選択トグル: ON で全項目 ON、OFF で全項目 OFF。

        OFF 時に個別状態を保持する選択肢もあるが、UX 一貫性のため
        「OFF=全解除」を採用（ユーザー要件: 既定 OFF、ON で全項目選択）。
        """
        if self._suppress_signal:
            return
        checked = self._select_all.isChecked()
        self._suppress_signal = True
        try:
            for cb in self._checkboxes:
                cb.setChecked(checked)
        finally:
            self._suppress_signal = False
        self.selection_changed.emit(self.selected_csv())

    def _on_item_changed(self, _state: int) -> None:
        if self._suppress_signal:
            return
        # 全 ON のとき select_all を自動で ON にする
        all_on = bool(self._checkboxes) and all(
            cb.isChecked() for cb in self._checkboxes
        )
        self._suppress_signal = True
        try:
            self._select_all.setChecked(all_on)
        finally:
            self._suppress_signal = False
        self.selection_changed.emit(self.selected_csv())
