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
from typing import Iterable, List, Optional, Set

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import app_catalog_loader
from ..app_catalog_loader import AppEntry

try:
    # architecture 文字列 → kind ("web-cloud" / "batch") へ正規化
    from hve.app_arch_filter import classify_architecture as _classify_architecture
except ImportError:  # pragma: no cover - import 失敗時は kind フィルタ無効化
    def _classify_architecture(_arch: str) -> str:  # type: ignore[misc]
        return ""


class AppIdChecklist(QWidget):
    """APP-ID 選択チェックボックスリスト。"""

    selection_changed = Signal(str)  # CSV 文字列

    def __init__(
        self,
        repo_root: Path,
        *,
        architecture_kinds: Optional[Iterable[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._repo_root = Path(repo_root)
        self._entries: List[AppEntry] = []
        self._checkboxes: List[QCheckBox] = []
        self._suppress_signal = False
        # 表示対象のアーキテクチャ kind 集合。空集合 / None なら全 kind 表示。
        self._architecture_kinds: Optional[Set[str]] = (
            set(architecture_kinds) if architecture_kinds else None
        )
        # kind 切替で一時的に非表示となった APP-ID のチェック状態を保持するための
        # 永続セレクション集合（フィルタを跨いだ選択保持に使用）。
        self._persistent_selection: Set[str] = set()

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
        """カタログを再読込してチェックボックスを再構築する。

        ``architecture_kinds`` が指定されているとき、各エントリの architecture を
        ``classify_architecture()`` で kind に変換し、当該 kind 集合に含まれる
        エントリのみ表示する。architecture が空文字（旧 catalog 形式）の場合は
        フィルタを通す（後方互換）。
        """
        # 既存チェックボックスを削除
        for cb in self._checkboxes:
            self._items_layout.removeWidget(cb)
            cb.deleteLater()
        self._checkboxes = []

        all_entries = app_catalog_loader.load_app_entries(self._repo_root)
        if self._architecture_kinds:
            kinds = self._architecture_kinds
            self._entries = [
                e for e in all_entries
                if (not e.architecture)  # 旧 catalog 形式は通す（後方互換）
                or _classify_architecture(e.architecture) in kinds
            ]
        else:
            self._entries = list(all_entries)

        if not self._entries:
            self._empty_label.setVisible(True)
            self._select_all.setEnabled(False)
            return

        self._empty_label.setVisible(False)
        self._select_all.setEnabled(True)
        for e in self._entries:
            kind = _classify_architecture(e.architecture) if e.architecture else ""
            label = e.display_label_with_kind(kind)
            cb = QCheckBox(label)
            cb.setProperty("app_id", e.app_id)
            cb.stateChanged.connect(self._on_item_changed)
            self._items_layout.addWidget(cb)
            self._checkboxes.append(cb)

    def set_architecture_kinds(self, kinds: Optional[Iterable[str]]) -> None:
        """表示対象の architecture kind 集合を切り替えてリロードする。

        ``None`` / 空集合 を渡すと全 kind 表示（フィルタ無効化）。
        既に同じ集合が設定されている場合は no-op（チェック状態保持）。

        フィルタ切替で一時的に非表示になった APP-ID のチェック状態は
        ``_persistent_selection`` に保持され、再表示時に自動復元される。
        """
        new_set: Optional[Set[str]] = set(kinds) if kinds else None
        if new_set == self._architecture_kinds:
            return
        self._architecture_kinds = new_set
        self.reload()
        # 永続セレクションから表示中エントリのチェック状態を復元
        if self._persistent_selection:
            self._suppress_signal = True
            try:
                for cb in self._checkboxes:
                    cb.setChecked(cb.property("app_id") in self._persistent_selection)
                # 全選択トグル状態を再計算
                all_on = bool(self._checkboxes) and all(
                    cb.isChecked() for cb in self._checkboxes
                )
                self._select_all.setChecked(all_on)
            finally:
                self._suppress_signal = False

    def selected_csv(self) -> str:
        """選択された APP-ID の CSV を返す。空のときは空文字列。

        フィルタで非表示中の APP-ID も ``_persistent_selection`` から復元される
        ため、kind 切替を跨いだ選択は失われない。出力順は表示中エントリ →
        非表示永続エントリ（アルファベット順）の順。
        """
        visible_ids = [
            cb.property("app_id") for cb in self._checkboxes if cb.isChecked()
        ]
        visible_set = set(visible_ids)
        hidden_ids = sorted(self._persistent_selection - visible_set)
        return ",".join(visible_ids + hidden_ids)

    def set_selected_csv(self, csv: str) -> None:
        """CSV 文字列から選択状態を復元する。

        表示中の APP-ID はチェックボックスに反映。表示外の ID は
        ``_persistent_selection`` に保持し、フィルタ切替で再表示時に自動復元される。
        """
        ids = {s.strip() for s in csv.split(",") if s.strip()}
        # 永続セレクションを上書き（フィルタ外含む全指定 ID）
        self._persistent_selection = set(ids)
        self._suppress_signal = True
        try:
            visible_target_count = 0
            for cb in self._checkboxes:
                target = cb.property("app_id") in ids
                cb.setChecked(target)
                if target:
                    visible_target_count += 1
            # 表示中の全項目が ON のときのみ全選択も ON にする
            all_on = bool(self._checkboxes) and visible_target_count == len(self._checkboxes)
            self._select_all.setChecked(all_on)
        finally:
            self._suppress_signal = False

    # ----------------------------------------------------------
    # シグナルハンドラ
    # ----------------------------------------------------------

    def _refresh_persistent_selection(self) -> None:
        """表示中チェック状態を ``_persistent_selection`` に反映する。

        ユーザー操作で表示中の APP-ID 選択が変わったとき、フィルタ外 ID の
        永続状態を維持したまま、表示中 ID の状態だけを上書きする。
        """
        visible_ids = {cb.property("app_id") for cb in self._checkboxes}
        checked_visible = {
            cb.property("app_id") for cb in self._checkboxes if cb.isChecked()
        }
        # フィルタ外 ID は維持、表示中 ID のみ上書き
        self._persistent_selection = (
            self._persistent_selection - visible_ids
        ) | checked_visible

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
        self._refresh_persistent_selection()
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
        self._refresh_persistent_selection()
        self.selection_changed.emit(self.selected_csv())
