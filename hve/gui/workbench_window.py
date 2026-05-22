"""hve.gui.workbench_window — WorkbenchWindow (QMainWindow)。

orchestrator サブプロセスを fork し、その stdout/stderr をリアルタイムで
QPlainTextEdit に表示するメインウィンドウ。

各ペインにコピーボタン（CopyButton）を配置する。
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .copy_button import CopyButton
from .fonts import preferred_log_font
from .state_bridge import SubprocessReader, launch_orchestrator
from .widgets.wrap_helpers import apply_cjk_wrap
from .wizard import WizardResult


# ログ最大行数（メモリ節約のため QPlainTextEdit の上限を設定）
_MAX_LOG_BLOCK_COUNT = 50_000


class _LogPane(QWidget):
    """ログ出力ペイン（QPlainTextEdit + コピーボタン）。"""

    def __init__(self, title: str = "ログ", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        header = QLabel(title)
        header.setStyleSheet("font-weight: bold; padding: 2px;")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        apply_cjk_wrap(self.log_view)
        self.log_view.setMaximumBlockCount(_MAX_LOG_BLOCK_COUNT)
        point_size = 9 if _is_windows() else 10
        self.log_view.setFont(preferred_log_font(point_size))

        copy_btn = CopyButton(
            get_text=lambda: self.log_view.toPlainText(),
            tooltip=self.tr("ログ全文をクリップボードにコピー"),
        )

        header_row = QHBoxLayout()
        header_row.addWidget(header)
        header_row.addStretch()
        header_row.addWidget(copy_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header_row)
        layout.addWidget(self.log_view)

    def append_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        # 末尾追従スクロール
        scrollbar = self.log_view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())


def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"


class _UserActionsPane(QWidget):
    """UserActions / コマンド入力ペイン（QTextEdit + コピーボタン）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        header = QLabel(self.tr("ユーザーアクション"))
        header.setStyleSheet("font-weight: bold; padding: 2px;")

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFixedHeight(120)
        apply_cjk_wrap(self.view)

        copy_btn = CopyButton(
            get_text=lambda: self.view.toPlainText(),
            tooltip=self.tr("アクション履歴をクリップボードにコピー"),
        )

        header_row = QHBoxLayout()
        header_row.addWidget(header)
        header_row.addStretch()
        header_row.addWidget(copy_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header_row)
        layout.addWidget(self.view)

    def append_action(self, level: str, message: str) -> None:
        import time
        ts = time.strftime("%H:%M:%S")
        self.view.append(f"[{ts}] [{level}] {message}")


class WorkbenchWindow(QMainWindow):
    """1 つの orchestrator セッションを管理するウィンドウ。

    Args:
        result: LaunchWizard から受け取ったウィザード結果
        session_index: 複数ウィンドウ管理用の番号（タイトルに表示）
        parent: 親ウィジェット（通常 None）

    Notes:
        ``result.autopilot_chain`` が非空のときはチェーン直列実行モードで動作し、
        各段の成功（exit code 0）後に次段を自動起動する。非ゼロ終了で中断し
        :attr:`chain_finished` を emit する。
    """

    chain_finished = Signal(int)  # Expose process completion signal
    status_changed = Signal(str)  # ステータスバーテキスト更新を他コンポーネントにブリッジ
    stage_advanced = Signal(str)  # Autopilot チェーンで次段ワークフローに進んだときに名前を通知

    def __init__(
        self,
        result: WizardResult,
        *,
        session_index: int = 1,
        env_overrides: Optional[Dict[str, str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._session_index = session_index
        self._reader: Optional[SubprocessReader] = None
        self._is_running = False
        # Issue-gui-session-workdir-isolation T5c:
        # GUI セッション work_root を子プロセスに伝搬するための env。
        self._env_overrides: Optional[Dict[str, str]] = (
            dict(env_overrides) if env_overrides else None
        )

        from .autopilot.chain_runner import ChainState
        chain = list(result.autopilot_chain) if result.autopilot_chain else []
        self._chain_state: Optional[ChainState] = ChainState(chain=chain) if chain else None
        if self._chain_state is not None:
            self._result.workflow = self._chain_state.current() or self._result.workflow

        title_suffix = result.workflow
        if self._chain_state is not None:
            title_suffix = "→".join(chain)
            if result.app_id:
                title_suffix = f"{result.app_id}: {title_suffix}"
        title = f"hve workbench [{session_index}] — {title_suffix}"
        self.setWindowTitle(title)

        # 横幅は設定に保存された値があればそれを使用、なければ既定 1100。
        try:
            from . import settings_store as _ss

            saved_width = int(_ss.get_option("workbench_window_width") or 0)
        except Exception:
            saved_width = 0
        initial_width = saved_width if saved_width > 0 else 1100
        self.resize(initial_width, 700)

        # ユーザーによる横幅変更を保存するためのデバウンス保存タイマー。
        self._width_save_timer = QTimer(self)
        self._width_save_timer.setSingleShot(True)
        self._width_save_timer.setInterval(300)
        self._width_save_timer.timeout.connect(self._persist_window_width)
        self._width_persist_enabled = False
        QTimer.singleShot(0, lambda: setattr(self, "_width_persist_enabled", True))

        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()

        QTimer.singleShot(0, self._start_orchestrator)

    # ------------------------------------------------------------------
    # UI セットアップ
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        self._log_pane = _LogPane("ログ")
        self._user_actions_pane = _UserActionsPane()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._log_pane)
        splitter.addWidget(self._user_actions_pane)
        splitter.setSizes([500, 120])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    def _setup_menu(self) -> None:
        menu_bar = self.menuBar()
        if menu_bar is None:
            return
        session_menu = menu_bar.addMenu("セッション")

        copy_cmd_action = QAction(self.tr("起動コマンドをコピー"), self)
        copy_cmd_action.triggered.connect(self._copy_launch_command)
        session_menu.addAction(copy_cmd_action)

        session_menu.addSeparator()

        stop_action = QAction(self.tr("セッションを停止"), self)
        stop_action.triggered.connect(self._stop_orchestrator)
        session_menu.addAction(stop_action)

    def _setup_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_label = QLabel(self.tr("起動中..."))
        sb.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # サブプロセス管理
    # ------------------------------------------------------------------

    def _start_orchestrator(self) -> None:
        argv = self._result.to_orchestrate_argv()
        try:
            proc = launch_orchestrator(argv, env_overrides=self._env_overrides)
        except OSError as e:
            self._log_pane.append_line(f"[ERROR] サブプロセス起動失敗: {e}")
            self._set_status("起動失敗")
            return

        self._reader = SubprocessReader(proc, parent=self)
        self._reader.line_received.connect(self._on_line_received)
        self._reader.finished_with_code.connect(self._on_process_finished)
        self._reader.start()
        self._is_running = True
        self._set_status(f"実行中 — workflow: {self._result.workflow}")
        self._user_actions_pane.append_action("INFO", f"セッション {self._session_index} 開始: {' '.join(argv)}")

    @Slot(str)
    def _on_line_received(self, line: str) -> None:
        # `[hve:stats] {...}` 行は GUI ログペインでは非表示（page_workbench と同仕様）。
        from .workbench_logger import is_stats_line
        if is_stats_line(line):
            return
        self._log_pane.append_line(line)

    @Slot(int)
    def _on_process_finished(self, returncode: int) -> None:
        self._is_running = False
        status_text = "完了" if returncode == 0 else f"終了 (code={returncode})"
        self._set_status(status_text)
        self._log_pane.append_line(f"\n--- セッション終了 (returncode={returncode}) ---")
        self._user_actions_pane.append_action(
            "INFO" if returncode == 0 else "WARN",
            f"セッション {self._session_index} 終了 (code={returncode})",
        )
        self.chain_finished.emit(returncode)  # Emit the completion signal

        # --- Autopilot チェーン進行制御 ---
        if self._chain_state is None:
            return

        from .autopilot.chain_runner import ChainEvent

        event = self._chain_state.on_stage_finished(returncode)
        self._release_reader()

        if event == ChainEvent.ADVANCED:
            next_wf = self._chain_state.current()
            if next_wf is None:
                self.chain_finished.emit(0)
                return
            self._result.workflow = next_wf
            self._log_pane.append_line(
                f"\n=== Autopilot: 次段へ遷移: {next_wf} ===\n"
            )
            self._set_status(self.tr("Autopilot: 次段起動 — %s") % next_wf)
            try:
                self.stage_advanced.emit(next_wf)
            except Exception:
                pass
            QTimer.singleShot(0, self._start_orchestrator)
        elif event == ChainEvent.COMPLETED:
            self._set_status(self.tr("[完了] Autopilot チェーン全段成功"))
            self._log_pane.append_line("\n=== Autopilot: チェーン全段完了 ===\n")
            self.chain_finished.emit(0)
        else:
            self._set_status(
                self.tr("[中断] Autopilot チェーン (exit code=%d)") % returncode
            )
            self._log_pane.append_line(
                f"\n=== Autopilot: 中断 (exit code={returncode}) ===\n"
            )
            self.chain_finished.emit(returncode)

    def _release_reader(self) -> None:
        reader = self._reader
        if reader is None:
            return
        try:
            reader.quit()
            reader.wait(2000)
        except Exception:
            pass
        try:
            reader.deleteLater()
        except Exception:
            pass
        self._reader = None

    def _stop_orchestrator(self) -> None:
        if self._reader is not None and self._is_running:
            self._reader.stop()
            self._set_status("停止要求済み")

    # ------------------------------------------------------------------
    # コピー操作
    # ------------------------------------------------------------------

    def _copy_launch_command(self) -> None:
        from PySide6.QtGui import QGuiApplication
        cmd = "python -m hve " + " ".join(self._result.to_orchestrate_argv())
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(cmd)
        self._set_status(f"コピー済み: {cmd}")

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        if hasattr(self, "_status_label"):
            self._status_label.setText(text)
        try:
            self.status_changed.emit(text)
        except Exception:
            pass

    def resizeEvent(self, event: "QResizeEvent") -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if getattr(self, "_width_persist_enabled", False):
            timer = getattr(self, "_width_save_timer", None)
            if timer is not None:
                timer.start()

    def _persist_window_width(self) -> None:
        w = int(self.width())
        if w < 200:
            return
        try:
            from . import settings_store as _ss

            _ss.set_option("workbench_window_width", w)
        except OSError:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """ウィンドウ閉じる時にサブプロセスをクリーンアップ。"""
        self._stop_orchestrator()
        super().closeEvent(event)
