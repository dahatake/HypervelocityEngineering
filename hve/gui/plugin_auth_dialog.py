"""hve.gui.plugin_auth_dialog — Plugin / MCP Server 認証ダイアログ。

設計:
    - 上部: プロバイダ一覧テーブル (列: 名称 / 状態 / 動作)。
    - 下部: 進捗ログ (QPlainTextEdit, monospace)。
    - フッター: [全て認証] [キャンセル] [閉じる]。
    - 1 プロバイダごとに ``_AuthWorker`` (QThread) を生成し、
      ブロッキング呼び出しを UI スレッドから分離する。
    - キャンセルは ``cancel_check`` コールバック経由でプロバイダへ伝達 (Q10=A)。
      ただし Device Flow など外部サブプロセスのキャンセルはタイムアウトで対応する。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .auth_providers import AuthProvider, AuthResult, AuthState, provider_supports_interactive

__all__ = ["PluginAuthDialog"]


# 状態 → 表示文字列・色。
# Device Code パターン (GitHub Copilot OAuth Device Flow): 例 "1F2F-FDB4"
_DEVICE_CODE_RE = re.compile(r"\b([0-9A-Z]{4}-[0-9A-Z]{4})\b")
_DEVICE_URL_RE = re.compile(r"https?://\S*github\.com/login/device\S*", re.IGNORECASE)


_STATE_DISPLAY: Dict[AuthState, tuple[str, QColor]] = {
    AuthState.AUTHENTICATED: ("✅ 認証済み", QColor("#2e7d32")),
    AuthState.NOT_AUTHENTICATED: ("❌ 未認証", QColor("#c62828")),
    AuthState.EXPIRED: ("⚠️ 失効", QColor("#ef6c00")),
    AuthState.UNKNOWN: ("❔ 未確認", QColor("#616161")),
    AuthState.CHECKING: ("🔄 確認中…", QColor("#1565c0")),
    AuthState.NOT_APPLICABLE: ("— 対象外", QColor("#9e9e9e")),
}


class _AuthWorker(QThread):
    """1 プロバイダ分の authenticate() を実行するワーカー。"""

    progress = Signal(str)
    finished_with_result = Signal(object)  # AuthResult

    def __init__(
        self,
        provider: AuthProvider,
        *,
        timeout: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._timeout = timeout
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # type: ignore[override]
        def _on_progress(msg: str) -> None:
            self.progress.emit(msg)

        def _cancel_check() -> bool:
            return self._cancel

        try:
            result = self._provider.authenticate(
                timeout=self._timeout,
                on_progress=_on_progress,
                cancel_check=_cancel_check,
            )
        except Exception as exc:  # pragma: no cover - 防御的
            result = AuthResult(
                success=False,
                state=AuthState.UNKNOWN,
                message=f"{type(exc).__name__}: {exc}",
            )
        self.finished_with_result.emit(result)


class PluginAuthDialog(QDialog):
    """Plugin / MCP Server 認証ダイアログ (Q8=B: 状態に応じて UI を切替)。"""

    # ダイアログ全体が完了したことを親に通知 (再 force_refresh 等のフック用)
    completed = Signal()

    # 個別プロバイダの認証フローが 1 件完了するたびに発火 (T07)。
    # MainWindow 側で AuthMonitor.force_refresh() に接続することで、
    # PTY インタラクティブ認証 (T06) の直後にキャッシュ無効化 + 再チェックが走る。
    provider_authenticated = Signal(str, bool)  # (provider_id, success)

    # 列定義
    _COL_NAME = 0
    _COL_STATE = 1
    _COL_DETAIL = 2
    _COL_ACTION = 3

    def __init__(
        self,
        providers: List[AuthProvider],
        *,
        parent: Optional[QWidget] = None,
        per_provider_timeout: float = 600.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plugin / MCP Server 認証")
        self.resize(720, 540)
        self._providers = list(providers)
        self._per_provider_timeout = float(per_provider_timeout)
        self._workers: Dict[str, _AuthWorker] = {}
        self._row_by_id: Dict[str, int] = {}
        self._action_buttons: Dict[str, QPushButton] = {}
        self._latest_state: Dict[str, AuthState] = {}
        self._all_running = False
        self._all_queue: List[AuthProvider] = []

        self._build_ui()
        self._populate_table()

    # ------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "登録された Plugin / MCP Server の認証状態を一覧で確認・実行します。"
            "\n[認証] 各行で個別に実行 / [全て認証] 上から順に実行。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels(["プロバイダ", "状態", "詳細", "動作"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self._COL_NAME, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self._COL_STATE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self._COL_DETAIL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._COL_ACTION, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 2)

        # Device Code バナー (GitHub Copilot OAuth Device Flow 検出時のみ表示)
        self._device_banner = QFrame(self)
        self._device_banner.setFrameShape(QFrame.Shape.StyledPanel)
        self._device_banner.setStyleSheet(
            "QFrame { background-color: #fff8e1; border: 1px solid #ffb300; border-radius: 4px; }"
        )
        banner_layout = QHBoxLayout(self._device_banner)
        banner_layout.setContentsMargins(8, 6, 8, 6)
        self._device_label = QLabel("", self._device_banner)
        self._device_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._device_label.setWordWrap(True)
        self._device_code_label = QLabel("", self._device_banner)
        code_font = QFont("Consolas")
        code_font.setStyleHint(QFont.StyleHint.Monospace)
        code_font.setPointSize(14)
        code_font.setBold(True)
        self._device_code_label.setFont(code_font)
        self._device_code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._device_code_label.setStyleSheet("color: #bf360c;")
        self._device_copy_btn = QPushButton("コードをコピー", self._device_banner)
        self._device_copy_btn.clicked.connect(self._on_copy_device_code)
        self._device_open_btn = QPushButton("認証ページを開く", self._device_banner)
        self._device_open_btn.clicked.connect(self._on_open_device_url)
        banner_layout.addWidget(self._device_label, 1)
        banner_layout.addWidget(self._device_code_label)
        banner_layout.addWidget(self._device_copy_btn)
        banner_layout.addWidget(self._device_open_btn)
        self._device_banner.setVisible(False)
        self._device_code: str = ""
        self._device_url: str = "https://github.com/login/device"
        layout.addWidget(self._device_banner)

        log_label = QLabel("進捗ログ:")
        layout.addWidget(log_label)
        self._log_view = QPlainTextEdit(self)
        self._log_view.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log_view.setFont(mono)
        self._log_view.setMaximumBlockCount(2000)
        layout.addWidget(self._log_view, 3)

        footer = QHBoxLayout()
        self._btn_check_all = QPushButton("状態を再確認")
        self._btn_check_all.clicked.connect(self._on_check_all_clicked)
        footer.addWidget(self._btn_check_all)

        self._btn_auth_all = QPushButton("全て認証")
        self._btn_auth_all.clicked.connect(self._on_auth_all_clicked)
        footer.addWidget(self._btn_auth_all)

        footer.addStretch()

        self._btn_cancel = QPushButton("キャンセル")
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        self._btn_cancel.setEnabled(False)
        footer.addWidget(self._btn_cancel)

        self._btn_close = QPushButton("閉じる")
        self._btn_close.clicked.connect(self._on_close_clicked)
        footer.addWidget(self._btn_close)

        layout.addLayout(footer)

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._providers))
        for row, provider in enumerate(self._providers):
            self._row_by_id[provider.id] = row

            name_item = QTableWidgetItem(provider.display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, provider.id)
            self._table.setItem(row, self._COL_NAME, name_item)

            state_item = QTableWidgetItem(_STATE_DISPLAY[AuthState.UNKNOWN][0])
            state_item.setForeground(_STATE_DISPLAY[AuthState.UNKNOWN][1])
            self._table.setItem(row, self._COL_STATE, state_item)

            detail_item = QTableWidgetItem("")
            self._table.setItem(row, self._COL_DETAIL, detail_item)

            btn = QPushButton("認証")
            btn.clicked.connect(
                lambda _checked=False, pid=provider.id: self._start_auth(pid)
            )
            self._action_buttons[provider.id] = btn
            self._table.setCellWidget(row, self._COL_ACTION, btn)

            self._latest_state[provider.id] = AuthState.UNKNOWN

        # 初期状態の検出を非同期で。
        self._on_check_all_clicked()

    # ------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------
    def latest_states(self) -> Dict[str, AuthState]:
        return dict(self._latest_state)

    # ------------------------------------------------------------
    # ハンドラ
    # ------------------------------------------------------------
    def _append_log(self, msg: str) -> None:
        if msg:
            self._log_view.appendPlainText(msg)
            self._maybe_detect_device_code(msg)

    def _maybe_detect_device_code(self, msg: str) -> None:
        """ログ行から Device Code / URL を抽出しバナーに表示する。"""
        url_match = _DEVICE_URL_RE.search(msg)
        code_match = _DEVICE_CODE_RE.search(msg)
        if not (url_match or code_match):
            return
        if url_match:
            self._device_url = url_match.group(0)
        if code_match:
            self._device_code = code_match.group(1)
            self._device_code_label.setText(self._device_code)
        self._device_label.setText(
            f"GitHub の認証ページ ({self._device_url}) で以下のコードを入力してください:"
        )
        self._device_banner.setVisible(True)

    def _on_copy_device_code(self) -> None:
        if not self._device_code:
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(self._device_code)
            self._append_log(f"[clipboard] Device Code '{self._device_code}' をコピーしました")

    def _on_open_device_url(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl(self._device_url))

    def _set_row_state(self, provider_id: str, state: AuthState, detail: Optional[str] = None) -> None:
        row = self._row_by_id.get(provider_id)
        if row is None:
            return
        text, color = _STATE_DISPLAY[state]
        item = self._table.item(row, self._COL_STATE)
        if item is not None:
            item.setText(text)
            item.setForeground(color)
        if detail is not None:
            d_item = self._table.item(row, self._COL_DETAIL)
            if d_item is not None:
                d_item.setText(detail)
        self._latest_state[provider_id] = state

    def _on_check_all_clicked(self) -> None:
        # 各プロバイダの check_status をワーカースレッドで順次実行。
        # 軽量なため AuthMonitor は使わず内部で都度起動する。
        self._btn_check_all.setEnabled(False)
        self._append_log("---- 状態確認開始 ----")
        thread = _StatusCheckThread(self._providers, self)
        thread.progress_for.connect(self._on_check_progress)
        thread.finished.connect(lambda: self._btn_check_all.setEnabled(True))
        thread.start()
        self._status_thread = thread  # GC 防止

    @Slot(str, str, str)
    def _on_check_progress(self, provider_id: str, state_value: str, detail: str) -> None:
        try:
            state = AuthState(state_value)
        except ValueError:
            state = AuthState.UNKNOWN
        self._set_row_state(provider_id, state, detail)
        name = self._provider_name(provider_id)
        self._append_log(f"[{name}] {state.value} {detail}")

    def _provider_name(self, provider_id: str) -> str:
        for p in self._providers:
            if p.id == provider_id:
                return p.display_name
        return provider_id

    def _provider_by_id(self, provider_id: str) -> Optional[AuthProvider]:
        for p in self._providers:
            if p.id == provider_id:
                return p
        return None

    # ------- 個別認証 -------
    def _start_auth(self, provider_id: str) -> None:
        provider = self._provider_by_id(provider_id)
        if provider is None:
            return
        if provider_id in self._workers and self._workers[provider_id].isRunning():
            return
        self._set_row_state(provider_id, AuthState.CHECKING, "認証中…")
        btn = self._action_buttons.get(provider_id)
        if btn is not None:
            btn.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._append_log(f"---- 認証開始: {provider.display_name} ----")

        # T06: インタラクティブ拡張対応プロバイダなら PtyAuthSessionWidget を開く。
        if provider_supports_interactive(provider):
            plan = None
            try:
                plan = provider.build_interactive_plan({})  # type: ignore[attr-defined]
            except Exception as exc:
                self._append_log(
                    f"[{provider.display_name}] build_interactive_plan failed: {exc}"
                )
            if plan is not None:
                self._run_interactive(provider_id, plan)
                return
            # plan == None → 従来のワーカー経路へフォールバック
            self._append_log(
                f"[{provider.display_name}] 個別 manifest が未定義のため、疎通確認のみを行います。"
            )

        worker = _AuthWorker(provider, timeout=self._per_provider_timeout, parent=self)
        worker.progress.connect(
            lambda m, pid=provider_id: self._append_log(f"[{self._provider_name(pid)}] {m}")
        )
        worker.finished_with_result.connect(
            lambda result, pid=provider_id: self._on_auth_finished(pid, result)
        )
        self._workers[provider_id] = worker
        worker.start()

    def _run_interactive(self, provider_id: str, plan) -> None:  # noqa: ANN001
        """PtyAuthSessionWidget を開いてフローを実行し、結果を従来経路へ合流させる。"""
        # 遅延 import (PySide6 必須、CLI モード非破壊)
        from .pty_auth_session_widget import PtyAuthSessionWidget

        self._append_log(
            f"[{self._provider_name(provider_id)}] インタラクティブ認証フローを開始 "
            f"(manifest={plan.source_manifest_id or 'unknown'})"
        )
        dlg = PtyAuthSessionWidget(plan, parent=self)
        dlg.exec()
        result = dlg.final_result()
        self._append_log(
            f"[{self._provider_name(provider_id)}] {result.state.value}: {result.message or ''}"
        )
        self._on_auth_finished(provider_id, result)

    @Slot(object)
    def _on_auth_finished(self, provider_id: str, result: object) -> None:
        res: AuthResult = result  # type: ignore[assignment]
        detail = res.message or ""
        self._set_row_state(provider_id, res.state, detail)
        self._append_log(
            f"[{self._provider_name(provider_id)}] result: success={res.success} state={res.state.value}"
        )
        btn = self._action_buttons.get(provider_id)
        if btn is not None:
            btn.setEnabled(True)
            btn.setText("再認証" if res.success else "認証")
        self._workers.pop(provider_id, None)
        if not self._any_worker_running():
            self._btn_cancel.setEnabled(False)
        # T07: 個別認証完了を親 (MainWindow) に通知し、AuthMonitor をリフレッシュさせる
        self.provider_authenticated.emit(provider_id, bool(res.success))
        # 全件モード継続
        if self._all_running:
            self._continue_all()

    def _any_worker_running(self) -> bool:
        return any(w.isRunning() for w in self._workers.values())

    # ------- 全件認証 -------
    def _on_auth_all_clicked(self) -> None:
        if self._all_running:
            return
        self._all_queue = [
            p for p in self._providers
            if self._latest_state.get(p.id) is not AuthState.AUTHENTICATED
        ]
        if not self._all_queue:
            self._append_log("---- 全プロバイダ既に認証済みです ----")
            return
        self._all_running = True
        self._btn_auth_all.setEnabled(False)
        self._continue_all()

    def _continue_all(self) -> None:
        if not self._all_queue:
            self._all_running = False
            self._btn_auth_all.setEnabled(True)
            self._append_log("---- 全件認証 完了 ----")
            self.completed.emit()
            return
        nxt = self._all_queue.pop(0)
        self._start_auth(nxt.id)

    # ------- キャンセル / 閉じる -------
    def _on_cancel_clicked(self) -> None:
        self._all_running = False
        self._all_queue.clear()
        for pid, worker in list(self._workers.items()):
            if worker.isRunning():
                worker.cancel()
                self._append_log(f"[{self._provider_name(pid)}] キャンセル要求送信")
        self._btn_auth_all.setEnabled(True)

    def _on_close_clicked(self) -> None:
        self._on_cancel_clicked()
        # ワーカー終了を最大 3 秒だけ待つ。
        for worker in self._workers.values():
            worker.wait(3000)
        self.completed.emit()
        self.accept()

    # QDialog 標準クローズ (Esc / X ボタン) も同じ経路にする。
    def reject(self) -> None:  # type: ignore[override]
        self._on_cancel_clicked()
        for worker in self._workers.values():
            worker.wait(3000)
        self.completed.emit()
        super().reject()


# ---------------------------------------------------------------------------
# 補助ワーカー: 全 check_status を順次実行 (UI スレッドブロック回避)
# ---------------------------------------------------------------------------
class _StatusCheckThread(QThread):
    progress_for = Signal(str, str, str)  # (provider_id, state_value, detail)

    def __init__(self, providers: List[AuthProvider], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._providers = list(providers)

    def run(self) -> None:  # type: ignore[override]
        for p in self._providers:
            try:
                status = p.check_status(timeout=30.0)
                state_value = status.state.value
                detail = status.detail or ""
            except Exception as exc:  # pragma: no cover
                state_value = AuthState.UNKNOWN.value
                detail = f"{type(exc).__name__}: {exc}"
            self.progress_for.emit(p.id, state_value, detail)
