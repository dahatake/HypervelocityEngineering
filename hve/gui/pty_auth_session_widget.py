"""hve.gui.pty_auth_session_widget — Plugin/MCP インタラクティブ認証ダイアログ。

設計:
    - 入力: ``InteractivePlan`` (T05) — 表示名 / notes_md / pre_commands / main_command。
    - 中身:
        1. 上部: 注意書き (Markdown → リッチテキスト)。
        2. 左: ステップ一覧 (現在ステップを強調表示)。
        3. 右: ``XtermTerminalView`` (T02) — PTY 出力描画 + 入力。
        4. 下: 「次へスキップ」「キャンセル」「閉じる」ボタン。
    - 実行:
        - キューから 1 コマンドずつ ``PtyAuthController`` (T03) で起動。
        - 出力は ``feed_output`` で xterm.js に流す。
        - ユーザー入力 (``user_input``) は controller の ``send_input`` へ。
        - 1 コマンド完了で次へ進む。失敗時は中断 (success=False)。
        - 全コマンド成功で ``accept()``、失敗 / キャンセルで ``reject()``。

出力:
    - ``final_result()`` で :class:`AuthResult` (T05 の AuthResult) を返す。
    - ``PluginAuthDialog`` 側はこれを ``_on_auth_finished`` 互換で扱う。

セキュリティ:
    - argv はすべて manifest 経由のリスト形式。shell 起動はしない。
    - 出力ログはダイアログ閉じると破棄 (機密混入対策)。
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import pty_backend
from .auth_providers import AuthResult, AuthState, InteractivePlan
from .pty_auth_controller import CommandSpec, PtyAuthController
from .widgets.xterm_terminal_view import XtermTerminalView

__all__ = ["PtyAuthSessionWidget"]


# レビュー No.21: ステップ状態を表す絵文字 prefix を定数化 (lstrip の暗黙挙動回避)。
_STEP_PREFIXES: tuple[str, ...] = ("✅ ", "⚠️ ", "🔄 ")


def _strip_step_prefix(text: str) -> str:
    for p in _STEP_PREFIXES:
        if text.startswith(p):
            return text[len(p):]
    return text


def _spec_label(spec: CommandSpec, index: int) -> str:
    """ステップリストに表示する 1 行ラベル。"""
    argv_str = " ".join(spec.argv[:4])
    if len(spec.argv) > 4:
        argv_str += " …"
    return f"{index + 1}. {argv_str}"


class PtyAuthSessionWidget(QDialog):
    """PTY ベースのインタラクティブ認証ダイアログ。"""

    def __init__(
        self,
        plan: InteractivePlan,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"認証フロー: {plan.display_name}")
        self.resize(1100, 640)
        self._plan = plan
        self._queue: List[CommandSpec] = list(plan.pre_commands)
        if plan.main_command is not None:
            self._queue.append(plan.main_command)
        self._current_index = -1
        self._step_results: List[bool] = []
        self._final: Optional[AuthResult] = None
        self._controller: Optional[PtyAuthController] = None
        self._force_skip_pending: bool = False

        self._build_ui()

        # PTY 不在環境では即座に失敗終了。
        if not pty_backend.is_pty_available():
            self._mark_final(False, pty_backend.missing_dependency_hint())
            return

        if not self._queue:
            # コマンドが無い (例: _default フォールバック) → 確認だけして即終了
            self._mark_final(True, "no commands defined; treating as success")
            return

        # 即時実行 (ユーザー操作不要)
        self._start_next()

    # ------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        if self._plan.notes_md:
            notes = QTextBrowser()
            notes.setOpenExternalLinks(False)
            notes.setMarkdown(self._plan.notes_md)
            notes.setMaximumHeight(160)
            notes.setWordWrapMode(QTextOption.WrapMode.WordWrap)
            layout.addWidget(notes)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左: ステップ一覧
        self._steps = QListWidget()
        self._steps.setMinimumWidth(260)
        for i, spec in enumerate(self._queue):
            item = QListWidgetItem(_spec_label(spec, i))
            self._steps.addItem(item)
        splitter.addWidget(self._steps)

        # 右: ターミナル
        self._term = XtermTerminalView()
        splitter.addWidget(self._term)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter, 1)

        self._status = QLabel("ステータス: 準備中...")
        font = self._status.font()
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._status.setFont(font)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._btn_skip = QPushButton("次へスキップ")
        self._btn_skip.clicked.connect(self._on_skip_clicked)
        self._btn_skip.setToolTip(
            "現在のステップを失敗扱いせず次へ進めます (例: 既に手動でログイン済みの場合)。"
        )
        btn_row.addWidget(self._btn_skip)

        btn_row.addStretch()

        self._btn_cancel = QPushButton("キャンセル")
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self._btn_cancel)

        self._btn_close = QPushButton("閉じる")
        self._btn_close.clicked.connect(self.reject)
        self._btn_close.setEnabled(False)
        btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

        # xterm.js 初期化完了は ready シグナルで分かる (現状は使用しない)
        self._term.user_input.connect(self._on_user_input)
        self._term.resized.connect(self._on_term_resized)

    # ------------------------------------------------------------
    # 公開
    # ------------------------------------------------------------
    def final_result(self) -> AuthResult:
        if self._final is not None:
            return self._final
        return AuthResult(
            success=False,
            state=AuthState.UNKNOWN,
            message="dialog closed before completion",
        )

    # ------------------------------------------------------------
    # ステップ駆動
    # ------------------------------------------------------------
    def _start_next(self) -> None:
        # T07 レビュー C2 修正: ステップ切替時に必ずフラグをクリア。
        # 「次へスキップ」→ コントローラ自然完了の競合で、未消費フラグが
        # 次ステップに持ち越されて誤って成功扱いになるバグを防ぐ。
        self._force_skip_pending = False
        self._current_index += 1
        if self._current_index >= len(self._queue):
            # 全完了
            ok = all(self._step_results) and bool(self._step_results)
            msg = "all steps succeeded" if ok else "some steps failed"
            self._mark_final(ok, msg)
            return

        spec = self._queue[self._current_index]
        self._highlight_step(self._current_index)
        self._term.feed_output(
            f"\r\n\x1b[1;36m==== Step {self._current_index + 1}/{len(self._queue)}: "
            f"{' '.join(spec.argv)}\x1b[0m\r\n".encode("utf-8")
        )
        self._status.setText(
            f"ステータス: 実行中 [{self._current_index + 1}/{len(self._queue)}] "
            f"{' '.join(spec.argv[:6])}"
        )

        controller = PtyAuthController(self)
        controller.output.connect(self._on_pty_output)
        controller.state_changed.connect(self._on_state_changed)
        controller.finished.connect(self._on_step_finished)
        self._controller = controller
        try:
            controller.start(spec)
        except Exception as exc:  # pragma: no cover - defensive
            self._step_results.append(False)
            self._mark_final(False, f"step start failed: {exc}")

    def _highlight_step(self, idx: int) -> None:
        for i in range(self._steps.count()):
            item = self._steps.item(i)
            if item is None:
                continue
            if i < idx:
                item.setText("✅ " + _strip_step_prefix(item.text()))
            elif i == idx:
                item.setText("🔄 " + _strip_step_prefix(item.text()))
        self._steps.setCurrentRow(idx)

    def _mark_step_outcome(self, idx: int, ok: bool) -> None:
        if 0 <= idx < self._steps.count():
            item = self._steps.item(idx)
            if item is not None:
                item.setText(("✅ " if ok else "⚠️ ") + _strip_step_prefix(item.text()))

    # ------------------------------------------------------------
    # コントローライベント
    # ------------------------------------------------------------
    @Slot(bytes)
    def _on_pty_output(self, data: bytes) -> None:
        self._term.feed_output(data)

    @Slot(str)
    def _on_state_changed(self, state: str) -> None:
        # ステータス行更新は finished で十分なため、ここではログのみ。
        # 必要なら詳細ステータス表示を追加する。
        _ = state

    @Slot(bool, str)
    def _on_step_finished(self, success: bool, message: str) -> None:
        # 「次へスキップ」が押されていた場合、結果を成功扱いに上書きする
        if self._force_skip_pending:
            self._force_skip_pending = False
            success = True
            message = f"skipped by user (original: {message})"
        self._step_results.append(success)
        self._mark_step_outcome(self._current_index, success)
        self._term.feed_output(
            (
                f"\r\n\x1b[{'32' if success else '31'}m"
                f"---- Step {self._current_index + 1} "
                f"{'OK' if success else 'FAILED'}: {message}\x1b[0m\r\n"
            ).encode("utf-8")
        )
        self._controller = None
        if not success:
            # 中断: 残ステップは未実行のまま、結果を確定
            self._mark_final(False, message)
            return
        self._start_next()

    # ------------------------------------------------------------
    # 端末入出力
    # ------------------------------------------------------------
    @Slot(bytes)
    def _on_user_input(self, data: bytes) -> None:
        if self._controller is not None:
            self._controller.send_input(data)

    @Slot(int, int)
    def _on_term_resized(self, cols: int, rows: int) -> None:
        if self._controller is not None:
            self._controller.resize(cols, rows)

    # ------------------------------------------------------------
    # ボタン
    # ------------------------------------------------------------
    def _on_skip_clicked(self) -> None:
        ctrl = self._controller
        if ctrl is None:
            return
        # 現在ステップを「成功扱い」で打ち切り、次へ進める。
        self._force_skip_pending = True
        ctrl.cancel()  # finished が来て _on_step_finished で成功扱いに上書きされる

    def _on_cancel_clicked(self) -> None:
        if self._controller is not None:
            self._controller.cancel()
        self._mark_final(False, "cancelled by user")

    # ------------------------------------------------------------
    # 終了処理
    # ------------------------------------------------------------
    def _mark_final(self, success: bool, message: str) -> None:
        if self._final is not None:
            return
        state = AuthState.AUTHENTICATED if success else AuthState.NOT_AUTHENTICATED
        self._final = AuthResult(success=success, state=state, message=message)
        self._status.setText(
            ("✅ 完了: " if success else "❌ 失敗: ") + message
        )
        self._btn_close.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_skip.setEnabled(False)
        if success:
            self.accept()
        # 失敗時は reject せず、ユーザーが「閉じる」を押すまでログを残す。

    def closeEvent(self, event) -> None:  # noqa: D401
        # レビュー No.11 修正: X ボタン / Esc / プログラム閉鎖の経路でも
        # final_result() が確定値を返すように _mark_final を呼ぶ。
        if self._controller is not None:
            self._controller.cancel()
        if self._final is None:
            self._mark_final(False, "dialog closed by user")
        super().closeEvent(event)
