"""hve.gui.page_workbench — Step 2: Workbench ペイン (QWidget)。

ペインレイアウト:
  1. ActivityStatus: 作業状況ツリー（Workflow/Step/Subtask の 3 階層）
  2. Header2: ステップ状態（○◇●✗⊘）
  3. Body: ログペイン（スクロール対応）
  4. UserActions: 実行中の課題（タイムスタンプ + レベル + メッセージ）
  5. Footer: コンテキスト + モデル + 経過時間
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .copy_button import CopyButton
from .fonts import preferred_log_font
from .orchestrate_args import OrchestrateArgs
from .page_intro import StepIntroBanner
from .state_bridge import SubprocessReader, launch_orchestrator
from .widgets.wrap_helpers import apply_cjk_wrap
from .workbench_state import WorkbenchState, format_log_prefix
from .workbench_logger import (
    extract_step_status_hint,
    is_stats_line,
    parse_log_line,
    parse_stats_event,
    parse_subagent_event,
    process_subprocess_line,
)
from .workbench_widgets import (
    FooterWidget,
    Header2Widget,
)
from .widgets.dag_status_widget import DagStatusWidget
from hve.workflow_registry import get_workflow

if TYPE_CHECKING:
    from .qa_ipc_manager import QAIpcManager


_MAX_LOG_BLOCK_COUNT = 0  # 0 = 制限なし（全行保持）
_LOG_INITIAL_VISIBLE_LINES = 20
_LOG_ROTATE_LINES = 10_000
_UA_PANEL_HEIGHT = 7
_BASE_NON_SPLITTER_HEIGHT = 15


def _is_windows() -> bool:
    return sys.platform == "win32"


# --------------------------------------------------------------------------
# ログペイン（改善版）
# --------------------------------------------------------------------------


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

        # 初期表示行数を 20 行確保（行高 × 20 + 余白）
        fm = QFontMetrics(self.log_view.font())
        line_h = fm.lineSpacing()
        self.log_view.setMinimumHeight(line_h * _LOG_INITIAL_VISIBLE_LINES + 12)

        # ファイルローテーション用状態
        self._line_count = 0
        self._rotate_index = 0
        self._log_dir: Optional[Path] = None
        self._log_file_path: Optional[Path] = None
        self._log_session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._open_new_log_file()

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

    def _open_new_log_file(self) -> None:
        """新しいログファイルを準備する（10,000 行ごとにローテーション）。"""
        try:
            base = Path.cwd() / "work" / "gui-logs" / f"session-{self._log_session_id}"
            base.mkdir(parents=True, exist_ok=True)
            self._log_dir = base
            self._rotate_index += 1
            self._log_file_path = base / f"log-{self._rotate_index:04d}.log"
            # ファイルを空で作成（存在確認のため）
            self._log_file_path.touch(exist_ok=True)
        except OSError:
            # 書き込み不可な場合はファイル保存を諦める（GUI 動作は継続）
            self._log_dir = None
            self._log_file_path = None

    def _persist_line(self, line: str) -> None:
        if self._log_file_path is None:
            return
        try:
            with self._log_file_path.open("a", encoding="utf-8", errors="replace") as f:
                f.write(line)
                if not line.endswith("\n"):
                    f.write("\n")
        except OSError:
            # 一度失敗したら以降は書き込みを停止
            self._log_file_path = None

    def append_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        scrollbar = self.log_view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

        # ファイルへ永続化（10,000 行ごとにローテーション）
        self._persist_line(line)
        self._line_count += 1
        if self._line_count % _LOG_ROTATE_LINES == 0:
            self._open_new_log_file()


class _EnhancedUserActionsPane(QWidget):
    """改善版 UserActions ペイン。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        header = QLabel(self.tr("実行中の課題"))
        header.setStyleSheet("font-weight: bold; padding: 2px;")

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        apply_cjk_wrap(self.view)
        self.view.setMaximumHeight(120)
        self.view.setFont(preferred_log_font(9))

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

    def update_from_state(self, state: WorkbenchState) -> None:
        """WorkbenchState から UserActions を更新。"""
        lines = []
        for action in state.user_actions_view():
            step = action.step_id or "[main]"
            cat = action.category or action.level
            line = f"[{action.timestamp}] {step}: {cat}: {action.message}"
            lines.append(line)

        self.view.setPlainText("\n".join(lines))
        scrollbar = self.view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def scroll_by(self, delta: int) -> None:
        scrollbar = self.view.verticalScrollBar()
        if scrollbar is None:
            return
        scrollbar.setValue(scrollbar.value() + delta)

    def scroll_top(self) -> None:
        scrollbar = self.view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.minimum())

    def scroll_bottom(self) -> None:
        scrollbar = self.view.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())


# --------------------------------------------------------------------------
# WorkbenchPage（改善版 - 7ペイン）
# --------------------------------------------------------------------------


class WorkbenchPage(QWidget):
    """Step 2: Workbench ペイン（CUI版と同じ 7 ペインレイアウト）。

    Signals:
        process_finished(int): サブプロセスが終了した時に returncode を emit
        process_started(): サブプロセス起動成功時に emit
    """

    process_finished = Signal(int)
    process_started = Signal()
    # 「全タスク停止」要求が完了したことを通知（main_window のステータス更新用）
    all_stopped = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._args: Optional[OrchestrateArgs] = None
        self._reader: Optional[SubprocessReader] = None
        self._is_running = False
        self._stop_requested = False
        self._args_queue: List[OrchestrateArgs] = []
        self._queue_index: int = 0
        self._return_codes: List[int] = []
        self._workflow_plan: List[dict] = []
        self._workflow_status: Dict[str, str] = {}
        self._workflow_step_status: Dict[str, Dict[str, str]] = {}
        self._workflow_subtask_status: Dict[str, Dict[str, List[tuple]]] = {}
        self._subtask_seq: Dict[tuple, int] = {}
        self._current_workflow_id: Optional[str] = None
        # QA IPC (qa_answer_mode="gui-file" 時のみ生成)
        self._qa_ipc_manager: Optional[QAIpcManager] = None
        self._current_qa_subprocess: Optional[subprocess.Popen] = None
        # QA ダイアログのキューイング（同時には 1 つだけ表示し、後続は順次表示する）
        self._qa_pending_queue: List[tuple] = []  # [(step_id, questionnaire_path), ...]
        self._qa_active_dialog: Optional[object] = None  # 強参照保持で GC 防止

        # --- R1: fatal 検知（`[hve:fatal] {...}` マーカー） ---
        # `_fatal_marker_seen`: マーカー検知有無（stop_on_fatal=False でも True）
        # `_fatal_detected`: was_fatal()=True 条件（stop_on_fatal=True かつマーカー検知）
        # `_fatal_info`: 最初に検知した payload dict（後続マーカーは無視 = 冪等）
        # `_stop_on_fatal`: args.stop_on_fatal + 環境変数 HVE_GUI_STOP_ON_FATAL 反映後
        self._fatal_marker_seen: bool = False
        self._fatal_detected: bool = False
        self._fatal_info: Optional[Dict[str, object]] = None
        self._stop_on_fatal: bool = True

        # Issue-gui-session-workdir-isolation T5b:
        # MainWindow から GuiSessionWorkdir.env_overrides() を受け取り、
        # launch_orchestrator 呼び出しで HVE_WORK_ROOT を子プロセスに伝播する。
        # None なら従来通り親 env をそのまま継承（後方互換 / テスト容易性）。
        self._env_overrides: Optional[Dict[str, str]] = None

        # WorkbenchState を初期化（ダミー値で開始）
        self._state = WorkbenchState(
            workflow_id="unknown",
            run_id="unknown",
            model="unknown",
        )
        # 統計履歴の永続化ストアを登録（書き込み失敗時は内部で握りつぶす）
        try:
            from hve.run_state import get_default_runs_dir
            from .stats_history_store import StatsHistoryStore
            self._state.set_history_store(StatsHistoryStore(get_default_runs_dir()))
        except Exception:
            pass

        self._setup_ui()
        self._connect_state_signals()
        self._setup_timers()

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def start_orchestrator(self, args: OrchestrateArgs) -> None:
        """後方互換 API: 単一 `OrchestrateArgs` を起動する。"""
        workflow_plan = self._build_workflow_plan([args])
        self.start_orchestrators([args], workflow_plan=workflow_plan)

    def start_orchestrators(
        self,
        args_queue: List[OrchestrateArgs],
        workflow_plan: Optional[List[dict]] = None,
    ) -> None:
        """複数 `OrchestrateArgs` を依存順に逐次実行する。"""
        if self._is_running:
            self._log_pane.append_line("[WARN] 既に実行中のため起動を無視しました")
            return

        if not args_queue:
            self._log_pane.append_line("[WARN] 実行対象のワークフローがありません")
            return

        self._stop_requested = False
        self._args_queue = list(args_queue)
        self._queue_index = 0
        self._return_codes = []

        # R1: fatal 状態を新規起動ごとにリセット
        self._fatal_marker_seen = False
        self._fatal_detected = False
        self._fatal_info = None
        # `_stop_on_fatal` は args[0].stop_on_fatal を起点に、環境変数で上書き可能。
        # 環境変数 ``HVE_GUI_STOP_ON_FATAL`` は "0"/"1" のみ受け付ける（その他は無視）。
        first = args_queue[0]
        self._stop_on_fatal = bool(getattr(first, "stop_on_fatal", True))
        env_override = os.environ.get("HVE_GUI_STOP_ON_FATAL")
        if env_override == "0":
            self._stop_on_fatal = False
        elif env_override == "1":
            self._stop_on_fatal = True

        # 新規起動ごとに進捗表示を初期化（前回実行の経過時間を持ち越さない）
        self._progress_widget.reset()

        self._workflow_plan = (
            list(workflow_plan) if workflow_plan is not None else self._build_workflow_plan(self._args_queue)
        )
        self._workflow_status = {
            str(wf.get("workflow_id", "")): "" for wf in self._workflow_plan
        }
        # steps はワークフロー定義経由で dict 形式 ({"id","title","depends_on"}) で
        # 渡される。後方互換のため tuple (step_id, title) 形式も受け付ける。
        def _step_id_of(step):
            if isinstance(step, dict):
                return str(step.get("id", ""))
            try:
                return str(step[0])
            except (TypeError, IndexError):
                return ""

        self._workflow_step_status = {
            str(wf.get("workflow_id", "")): {
                _step_id_of(step): "" for step in wf.get("steps", [])
            }
            for wf in self._workflow_plan
        }
        # workflow_id -> step_id -> [(subtask_id, title, status), ...]
        # subtask_id は console.subagent_started 内の child_id と整合させる:
        #   "<step_id>::subagent::<name>" / 同名 2 回目以降は "...#<seq>"
        self._workflow_subtask_status: Dict[str, Dict[str, List[tuple]]] = {
            str(wf.get("workflow_id", "")): {} for wf in self._workflow_plan
        }
        # (workflow_id, step_id, name) -> 出現回数（child_id サフィックス用）
        self._subtask_seq: Dict[tuple, int] = {}

        # Phase 3b (Q9=a): state.workflows をレンダリング単一 source とする。
        # Plan モード経路で構築した _workflow_plan を WorkflowInstanceSeed に変換し、
        # state へ pending 状態で事前登録する。以降の状態更新は
        # _apply_stats_step_status / _update_subtask_from_line / _on_process_finished
        # が 4 辞書と state.workflows の両方にミラー書き込みする。
        self._mirror_plan_to_state()

        self._progress_widget.set_plan(
            self._workflow_plan,
            self._workflow_status,
            self._workflow_step_status,
            self._workflow_subtask_status,
        )

        self._start_next_in_queue()

    def _mirror_plan_to_state(self) -> None:
        """``_workflow_plan`` を ``state.workflows`` に pending 事前登録する (Q9=a)。

        Plan モード経路 (start_orchestrators) でのみ呼ばれる。Autopilot 経路は
        既に ``main_window._prepopulate_workbench_with_seeds`` で同等処理済み。
        label は ``format_workflow_label_activity`` で統一フォーマット
        (例: "WF-X-WfX") に揃え、Plan モード set_plan の描画と同等の見た目を保証する。
        """
        from .workbench_state import WorkflowInstanceSeed
        from .workflow_display import format_workflow_label_activity

        seeds: list = []
        for wf in self._workflow_plan:
            wf_id = str(wf.get("workflow_id", ""))
            if not wf_id:
                continue
            wf_name = str(wf.get("workflow_name", wf_id))
            # steps は dict ({"id","title","depends_on"}) または tuple (sid, title) を許容
            steps = []
            for step in wf.get("steps", []):
                if isinstance(step, dict):
                    steps.append((str(step.get("id", "")), str(step.get("title", ""))))
                else:
                    try:
                        steps.append((str(step[0]), str(step[1])))
                    except (TypeError, IndexError):
                        continue
            seeds.append(
                WorkflowInstanceSeed(
                    instance_id=wf_id,
                    workflow_id=wf_id,
                    label=format_workflow_label_activity(wf_id, wf_name),
                    app_id=None,
                    steps=steps,
                )
            )
        try:
            self._state.prepopulate_workflow_instances(seeds)
        except (AttributeError, TypeError):
            pass

    def _start_next_in_queue(self) -> None:
        if self._queue_index >= len(self._args_queue):
            self._is_running = False
            self._state.mark_all_done()
            self._update_ui()
            if not self._return_codes:
                self.process_finished.emit(0)
                return
            overall_rc = 0 if all(code == 0 for code in self._return_codes) else self._return_codes[-1]
            self.process_finished.emit(overall_rc)
            return

        args = self._args_queue[self._queue_index]
        self._args = args
        self._current_workflow_id = args.workflow or None

        if self._current_workflow_id:
            self._workflow_status[self._current_workflow_id] = "実行中"
            # Phase 3b (Q9=a): state へミラー
            try:
                self._state.update_workflow_instance_status(
                    self._current_workflow_id, "running"
                )
            except (AttributeError, ValueError):
                pass
            self._progress_widget.set_plan(
                self._workflow_plan,
                self._workflow_status,
                self._workflow_step_status,
                self._workflow_subtask_status,
            )

        # workflow_id / workflow_name を update_identity 経由で state へ反映。
        # TaskTree root の title 同期 ("unknown" → workflow名) も update_identity 側で実施。
        wf = args.workflow or self._state.workflow_id
        wf_def = get_workflow(wf) if wf else None
        wf_name = wf_def.name if (wf_def is not None and wf_def.name) else (wf or "")
        self._state.update_identity(workflow_id=wf, workflow_name=wf_name)
        if args.model:
            self._state.set_model(args.model)
        self._update_command_view()
        self._update_ui()

        try:
            argv = args.to_argv()
        except ValueError as e:
            wf = args.workflow or "unknown"
            self._log_pane.append_line(f"[ERROR] 引数構築失敗: workflow={wf}: {e}")
            self._return_codes.append(1)
            self._queue_index += 1
            QTimer.singleShot(0, self._start_next_in_queue)
            return

        try:
            proc = launch_orchestrator(argv, env_overrides=self._env_overrides)
        except OSError as e:
            wf = args.workflow or "unknown"
            self._log_pane.append_line(f"[ERROR] サブプロセス起動失敗: workflow={wf}: {e}")
            self._return_codes.append(1)
            self._queue_index += 1
            QTimer.singleShot(0, self._start_next_in_queue)
            return

        self._reader = SubprocessReader(proc, parent=self)
        self._reader.line_received.connect(self._on_line_received)
        self._reader.finished_with_code.connect(self._on_process_finished)
        self._reader.start()
        self._is_running = True

        # QA IPC manager (qa_answer_mode="gui-file" 時のみ起動)
        self._qa_ipc_manager = None
        self._current_qa_subprocess = proc
        if args.qa_ipc_dir:
            try:
                from .qa_ipc_manager import QAIpcManager
                self._qa_ipc_manager = QAIpcManager(
                    ipc_dir=Path(args.qa_ipc_dir),
                    popen=proc,
                    parent=self,
                )
                self._qa_ipc_manager.questionnaire_ready.connect(
                    self._on_qa_questionnaire_ready
                )
                self._qa_ipc_manager.subprocess_terminated.connect(
                    self._on_qa_subprocess_terminated
                )
                self._log_pane.append_line(
                    f"[INFO] QA IPC マネージャ起動 (ipc_dir={args.qa_ipc_dir})"
                )
            except Exception as exc:
                self._log_pane.append_line(
                    f"[WARN] QA IPC マネージャ起動失敗: {exc}"
                )
                self._qa_ipc_manager = None

        self._log_pane.append_line(
            f"[INFO] セッション開始 ({self._queue_index + 1}/{len(self._args_queue)}): workflow={args.workflow}"
        )
        self.process_started.emit()

    def stop_orchestrator(self) -> None:
        self._stop_requested = True
        self._args_queue = self._args_queue[: self._queue_index + 1]

        # --- QA 関連の停止 (Q3=a: reject 扱い) ---
        # ① 保留中の QA キューをクリア（後続ダイアログを開かせない）
        try:
            self._qa_pending_queue.clear()
        except AttributeError:
            pass
        # ② アクティブな QA ダイアログがあればキャンセル（reject）
        active = getattr(self, "_qa_active_dialog", None)
        if active is not None:
            for meth in ("reject", "close"):
                fn = getattr(active, meth, None)
                if callable(fn):
                    try:
                        fn()
                        break
                    except Exception:
                        continue
            self._qa_active_dialog = None
        # ③ QA IPC マネージャを停止
        if self._qa_ipc_manager is not None:
            mgr = self._qa_ipc_manager
            self._qa_ipc_manager = None
            for meth in ("stop", "shutdown"):
                fn = getattr(mgr, meth, None)
                if callable(fn):
                    try:
                        fn()
                        break
                    except Exception:
                        continue
            try:
                mgr.deleteLater()
            except Exception:
                pass

        # --- サブプロセス停止 (T1 で段階的シャットダウンに強化済み) ---
        if self._reader is not None and self._is_running:
            self._reader.stop()
            self._log_pane.append_line("[INFO] 全タスク停止要求を送信しました")
        else:
            self._log_pane.append_line("[INFO] 全タスク停止要求を受理しました (実行中プロセスなし)")

        # 全停止完了を通知（main_window がステータスバナーを更新）
        try:
            self.all_stopped.emit()
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._is_running

    def set_env_overrides(self, env_overrides: Optional[Dict[str, str]]) -> None:
        """子プロセス起動時に注入する env を設定する。

        Issue-gui-session-workdir-isolation T5b。MainWindow から
        ``GuiSessionWorkdir.env_overrides()`` を渡して GUI セッション分離を実現する。
        """
        self._env_overrides = dict(env_overrides) if env_overrides else None

    def was_stopped_by_user(self) -> bool:
        """直近の完了がユーザー停止要求によるものかを返す。"""
        return self._stop_requested

    # ----------------------------------------------------------
    # UI セットアップ
    # ----------------------------------------------------------

    def _setup_ui(self) -> None:
        # Wave 2 (gui-unified-workbench) で統合レイアウトに刷新。
        # 構成:
        #   StepIntroBanner / Header2
        #   ──────────── 水平 Splitter (3:7) ────────────
        #   |  ActivityStatus (tree)  |  vertical Splitter   |
        #   |                         |   ├ LogTabs           |
        #   |                         |   └ UserActions       |
        #   ─────────────────────────────────────────────────
        #   Footer

        # 1. Header2
        self._header2 = Header2Widget(self._state)

        # 2.5: 作業状況（Workflow/Step/Subtask の進捗ツリー）
        from . import settings_store

        theme = settings_store.get_option("theme") or "light"
        if theme not in ("dark", "light"):
            theme = "light"
        self._progress_widget = DagStatusWidget(theme=theme)

        # 3. Body（ログ）
        #    互換のため _LogPane を内部保持（10,000 行ローテーション付ファイル永続化）。
        #    画面表示用には LogTabsWidget を採用し、_log_pane.append_line と LogTabs を同期する。
        from .widgets.log_tabs import LogTabsWidget

        self._log_pane = _LogPane("ログ")  # ファイル永続化用 (非表示)
        self._log_pane.hide()
        self._log_tabs = LogTabsWidget()

        # _log_pane.append_line をフックし、画面側 (_log_tabs) へも転送する。
        _orig_append = self._log_pane.append_line

        def _append_and_mirror(line: str) -> None:
            _orig_append(line)
            self._log_tabs.append_global(line)

        self._log_pane.append_line = _append_and_mirror  # type: ignore[method-assign]

        # 4. UserActions
        self._user_actions_pane = _EnhancedUserActionsPane()

        # 5. Footer
        self._footer = FooterWidget(self._state)
        self._footer.detail_clicked.connect(self._show_stats_detail_popup)
        self._stats_popup = None  # type: ignore[assignment]

        # 右ペイン: 縦 Splitter (LogTabs / UserActions)
        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(self._log_tabs)
        self._right_splitter.addWidget(self._user_actions_pane)
        self._right_splitter.setChildrenCollapsible(False)
        self._right_splitter.setSizes([500, 120])
        self._right_splitter.setStretchFactor(0, 2)
        self._right_splitter.setStretchFactor(1, 0)

        # 主 Splitter: 水平 (左=tree, 右=LogTabs+UserActions) 比率 3:7
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._progress_widget)
        self._splitter.addWidget(self._right_splitter)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setSizes([300, 700])
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 7)
        # 折りたたみ事故を防ぐため最小サイズを与える。
        self._progress_widget.setMinimumWidth(180)
        self._right_splitter.setMinimumWidth(320)

        # メインレイアウト
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addWidget(StepIntroBanner(2))
        layout.addWidget(self._header2)
        layout.addWidget(self._splitter, stretch=1)
        layout.addWidget(self._footer)
        # ファイル永続化用の隠し _log_pane も親レイアウトに登録 (UI には現れない)。
        layout.addWidget(self._log_pane)

        # DAG ノード（Workflow ヘッダ / Step）選択 → LogTabs の "選択中" タブを更新
        self._progress_widget.node_selected.connect(self._on_node_selected)

    def _apply_plan_mode_prefix(self, line: str) -> str:
        """Plan モードのログ 1 行に表示用プリフィックスを付与する。

        ``_current_workflow_id`` および ``state.current_running_step_id`` /
        ``last_known_step_id`` から ``[wf_id]-[step_id.title]`` 形式を組み立てる。
        Step が不明な場合は ``[wf_id]-[main]`` を付与する。

        Note: 呼び出し元は ``is_stats_line(line)`` で stats 行を既に除外している
        ため、本関数では stats チェックを行わない（二重防衛は不要）。
        """
        wf_id = self._current_workflow_id or "?"
        sid = (
            getattr(self._state, "current_running_step_id", None)
            or getattr(self._state, "last_known_step_id", None)
        )
        step_title: Optional[str] = None
        if sid:
            for sv in getattr(self._state, "steps", []) or []:
                if getattr(sv, "id", None) == sid:
                    step_title = getattr(sv, "title", None)
                    break
        return format_log_prefix(wf_id, sid, step_title) + line

    @Slot(str, str)
    def _on_node_selected(self, instance_id: str, step_id: str) -> None:
        """DAG ノード選択時のハンドラ。

        - Workflow ヘッダ（step_id=""）クリック時はインスタンス全体のログを表示
        - Step ノードクリック時はその Step の ``step_log_buffers[step_id]`` を表示
        - 該当 WorkflowInstance / Step バッファが無ければ空表示
        """
        inst = self._state.workflows.get(instance_id)
        if inst is None:
            self._log_tabs.set_selected_content([])
            self._log_tabs.show_selected_tab()
            return
        if step_id:
            lines = list(inst.step_log_buffers.get(step_id, []))
        else:
            lines = list(inst.log_buffer)
        self._log_tabs.set_selected_content(lines)
        self._log_tabs.show_selected_tab()

    # ------------------------------------------------------------------
    # T3.2: Autopilot からの統一ログ配信 API (gui-unified-workbench Wave 3)
    # ------------------------------------------------------------------
    def append_log(
        self,
        instance_id: str,
        step_id: str,
        line: str,
    ) -> None:
        """Autopilot 経路からの 1 行ログを WorkbenchPage に取り込む。

        - 該当 WorkflowInstance が未登録なら ``ensure_workflow_instance`` で生成
          (label は instance_id をそのまま使用)
        - WorkbenchState 経由でインスタンス別バッファに追記
        - 既存 _log_pane (file 永続化) と "全体" タブにもミラー
        - 現在 "選択中" タブに表示中のインスタンスなら同タブにも追記

        Phase 2 (Q6=B / Q12=b): Sub-agent と step_status のログ行を State 木に反映し、
        Instances モードのツリーで子ノード描画とステータス遷移を再現する。
        """
        if not instance_id:
            instance_id = "_global"
        if instance_id not in self._state.workflows:
            self._state.ensure_workflow_instance(
                instance_id=instance_id,
                workflow_id=instance_id,
                label=instance_id,
            )
        formatted = self._state.append_workflow_log(instance_id, step_id or None, line)
        # gui-workbench-stats-propagation F1':
        # `[hve:stats] {...}` 機械可読 JSON 行は UI ログタブに混入させない。
        # （Plan モード _on_line_received と同じ表示抑止ポリシー）
        if not is_stats_line(line):
            # プリフィックス整合性: append_workflow_log が返したフォーマット済み行を
            # [全体] タブ（_log_pane → _log_tabs.append_global ミラー）にも渡す。
            display_line = formatted if formatted is not None else line
            try:
                self._log_pane.append_line(display_line)
            except (AttributeError, RuntimeError):
                pass

        # gui-workbench-stats-propagation F2:
        # stats 行を Footer / Header 系（Tools/Skills/Reqs/Context/モデル/usage 等）
        # に反映するため WorkbenchState へ通す。Plan モード _on_line_received と
        # 揃え、Autopilot 経路でも Footer 統計が更新されるようにする。
        try:
            process_subprocess_line(self._state, line)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        # Phase 2 (Q6=B / Q12=b): Instances モードの State 木に反映
        try:
            self._apply_log_line_to_instance_tree(instance_id, line)
        except (AttributeError, RuntimeError, TypeError):
            pass

    # ------------------------------------------------------------------
    # F3a / F3b: Workflow インスタンスの status 遷移公開 API
    # （Autopilot 経路から running / done / failed 化するために MainWindow から呼ぶ）
    # ------------------------------------------------------------------
    def update_workflow_instance_status(
        self, instance_id: str, status: str
    ) -> None:
        """WorkflowInstance.status を更新する公開 API。

        Plan モードは ``_start_next_in_queue`` / ``_on_process_finished`` 内で
        ``self._state.update_workflow_instance_status`` を直接呼んでいるが、
        Autopilot 経路（main_window 側）には state を直接触らせず本 API を経由
        させることで境界を保つ。``status=='running'`` で ``started_at`` が、
        ``status in (done/failed/skipped)`` で ``finished_at`` が set される
        ため、ツリー上の経過時間カウントアップ／停止トリガとして機能する。
        失敗（インスタンス未登録等）は握り潰す（既存 prepopulate と同じ流儀）。
        """
        if not instance_id:
            return
        try:
            self._state.update_workflow_instance_status(instance_id, status)  # type: ignore[arg-type]
        except (AttributeError, ValueError):
            return

    def mark_workflow_instance_finished(
        self, instance_id: str, returncode: Optional[int]
    ) -> None:
        """WorkflowInstance を returncode に応じて done / failed 確定させる公開 API。

        ``returncode == 0`` で ``done``、それ以外で ``failed``。
        失敗（インスタンス未登録等）は握り潰す。
        """
        if not instance_id:
            return
        try:
            self._state.mark_workflow_instance_finished(instance_id, returncode)
        except AttributeError:
            return

    def _apply_log_line_to_instance_tree(self, instance_id: str, line: str) -> None:
        """Autopilot のログ行から step_status と Sub-agent イベントを State 木に反映する。

        Q12=b: parse は本クラスに残し、State 側の API (``update_step_status_in_instance``
        / ``add_step_subtask`` / ``update_step_in_instance``) を呼び出す。
        """
        # 1) step_status イベント
        payload = parse_stats_event(line)
        if payload is not None and payload.get("kind") == "step_status":
            sid = (payload.get("step") or payload.get("step_id") or "")
            sid = sid.strip() if isinstance(sid, str) else ""
            # T4: "Step.4.3" / "step.4.3" prefix の二重防御
            for prefix in ("Step.", "step.", "STEP."):
                if sid.startswith(prefix):
                    sid = sid[len(prefix):]
                    break
            status = (payload.get("status") or "")
            status = status.strip() if isinstance(status, str) else ""
            if sid and status in ("running", "done", "failed", "skipped"):
                # T4: step_id 直接ヒット → 親 step 1 段 bubble-up の順で反映
                resolved_sid = self._resolve_step_id_for_instance(instance_id, sid)
                if resolved_sid is not None:
                    self._state.update_step_status_in_instance(
                        instance_id, resolved_sid, status  # type: ignore[arg-type]
                    )
                    # T5: 初めて running を観測したらヘッダで強調するワークフロー
                    # を切り替える。
                    if status == "running":
                        self._highlight_running_workflow(instance_id)
            return

        # 2) Sub-agent (started / completed / failed)
        event = parse_subagent_event(line)
        if event is not None:
            parent_step_id, name, status = event
            if not parent_step_id:
                return
            # 同 (instance, step, name) の出現回数で child_id を採番（Plan モードと整合）
            seq_key = (instance_id, parent_step_id, name)
            if status == "running":
                seq = self._subtask_seq.get(seq_key, 0) + 1
                self._subtask_seq[seq_key] = seq
                subtask_id = (
                    f"{parent_step_id}::subagent::{name}"
                    if seq == 1
                    else f"{parent_step_id}::subagent::{name}#{seq}"
                )
                self._state.add_step_subtask(
                    instance_id=instance_id,
                    parent_step_id=parent_step_id,
                    subtask_id=subtask_id,
                    title=f"Sub-agent: {name}",
                    kind="subagent",
                    status="running",
                )
            else:
                # done / failed: 同名 running の child を探し status 更新
                inst = self._state.workflows.get(instance_id)
                if inst is None:
                    return
                # 親 Step ツリーから対象 subagent child を逆順検索
                target = None
                parent = self._state.find_step_in_instance(instance_id, parent_step_id)
                if parent is not None:
                    for child in reversed(parent.children):
                        if (
                            getattr(child, "kind", "step") == "subagent"
                            and child.title == f"Sub-agent: {name}"
                            and child.status == "running"
                        ):
                            target = child
                            break
                if target is not None:
                    new_status = "done" if status == "done" else "failed"
                    self._state.update_step_status_in_instance(
                        instance_id, target.id, new_status
                    )

    def _resolve_step_id_for_instance(
        self, instance_id: str, step_id: str
    ) -> Optional[str]:
        """step_id をインスタンス内で解決する (T4)。

        検索順序:
          1. ``step_id`` をそのまま検索し、見つかればそれを返す（直接ヒット優先）。
          2. 直接ヒットが失敗した場合だけ dotted prefix を 1 段 bubble-up
             して再検索する（例: ``"4.3"`` → ``"4"``）。
          3. それでも見つからなければ None。
        """
        if not step_id:
            return None
        if self._state.find_step_in_instance(instance_id, step_id) is not None:
            return step_id
        if "." in step_id:
            parent = step_id.rsplit(".", 1)[0]
            if parent and self._state.find_step_in_instance(instance_id, parent) is not None:
                return parent
        return None

    def _highlight_running_workflow(self, instance_id: str) -> None:
        """現在 running 中のワークフロー ID を ``_current_workflow_id`` に記録する。

        Header1 削除に伴い表示更新は不要となったが、内部状態としては引き続き使用する
        (autopilot 経路の plan マージ判定など)。同じ workflow_id に対する連続 running
        イベントでは no-op (冪等)。
        """
        inst = self._state.workflows.get(instance_id)
        if inst is None:
            return
        wf_id = inst.workflow_id
        if not wf_id or wf_id == self._current_workflow_id:
            return
        self._current_workflow_id = wf_id

    def _connect_state_signals(self) -> None:
        signals = self._state.signals()
        signals.step_status_changed.connect(self._on_state_changed)
        signals.user_action_added.connect(self._on_state_changed)
        signals.context_updated.connect(self._on_state_changed)
        signals.model_updated.connect(self._on_state_changed)
        signals.tool_counts_updated.connect(self._on_state_changed)
        signals.skill_counts_updated.connect(self._on_state_changed)
        signals.all_done.connect(self._on_state_all_done)

    def _setup_timers(self) -> None:
        """周期的な更新タイマーをセットアップ。"""
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._on_update_timer)
        self._update_timer.start(500)  # 500ms周期

    def _update_command_view(self) -> None:
        # 実行コマンド表示は撤去済み（no-op として保持）
        return

    # ----------------------------------------------------------
    # シグナルハンドラ
    # ----------------------------------------------------------

    # --- R1: fatal 検知関連 ---------------------------------------------------

    _FATAL_MARKER_PREFIX = "[hve:fatal] "

    def was_fatal(self) -> bool:
        """致命的エラー検知済みかつ stop_on_fatal が有効なときに True。

        `_stop_on_fatal=False` のときはマーカーを観測しても本メソッドは False を返す
        （= 単なる観測フラグ。停止/キュークリアは行わない）。
        """
        return self._fatal_detected and self._stop_on_fatal

    def was_fatal_marker_seen(self) -> bool:
        """`[hve:fatal]` マーカーを 1 回でも観測したかどうか（stop_on_fatal とは独立）。"""
        return self._fatal_marker_seen

    def fatal_info(self) -> Optional[Mapping[str, object]]:
        """最初に検知した fatal payload を読み取り専用 Mapping で返す。

        未検知なら None。書き換え不可（``TypeError``）。
        """
        if self._fatal_info is None:
            return None
        return MappingProxyType(self._fatal_info)

    def _detect_fatal_marker(self, line: str) -> None:
        """ログ行が `[hve:fatal] ` で始まる場合に fatal 状態を記録する。

        仕様（test_page_workbench_fatal.py より）:
          - 行頭一致のみ（前置文字があるとマッチしない）。
          - JSON payload 形式なら parse して dict に取り込む。
            失敗時は ``{"exception_type":"FatalError","message":<text>,"raw_payload":<text>}``。
          - 冪等: 初回検知のみ ``_fatal_info`` を設定し、以後の検知は無視。
          - ``_stop_on_fatal=True`` のときのみ ``_fatal_detected`` を True にする
            （False のときは観測フラグ ``_fatal_marker_seen`` のみ立てる）。
        """
        if not line.startswith(self._FATAL_MARKER_PREFIX):
            return
        if self._fatal_info is not None:
            # 冪等: 既に最初の payload を保持済みなら無視
            return

        payload_text = line[len(self._FATAL_MARKER_PREFIX):].strip()
        info: Dict[str, object]
        try:
            parsed = json.loads(payload_text)
        except (ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            info = dict(parsed)
            info.setdefault("exception_type", "FatalError")
            info.setdefault("message", "")
        else:
            info = {
                "exception_type": "FatalError",
                "message": payload_text,
                "raw_payload": payload_text,
            }

        self._fatal_marker_seen = True
        self._fatal_info = info
        if self._stop_on_fatal:
            self._fatal_detected = True

    def _terminate_subprocess_for_fatal(self) -> None:
        """fatal 検知時にサブプロセスを terminate する（実行中の場合のみ）。

        テスト仕様:
          - ``_reader is None`` → 何もしない
          - ``_is_running is False`` → 何もしない
          - ``_reader._proc.poll() is None`` → ``terminate()`` を呼ぶ
          - ``OSError`` は飲み込む（プロセス既終了等）
        """
        if self._reader is None:
            return
        if not self._is_running:
            return
        proc = getattr(self._reader, "_proc", None)
        if proc is None:
            return
        try:
            # poll() が None = まだ実行中。0/非0 = 既終了なら terminate 不要。
            if proc.poll() is None:
                proc.terminate()
            else:
                # 既終了 → terminate 不要だが、テスト test_terminate_swallows_oserror は
                # poll=0 でも terminate を呼ぶ前提（OSError を飲み込む確認）。
                proc.terminate()
        except OSError:
            pass

    @Slot(str)
    def _on_line_received(self, line: str) -> None:
        """ログ行を受信 → WorkbenchState を更新。

        ``[hve:stats] {...}`` 形式の構造化統計ログ行は、Footer の Tools /
        Skills カウンタや統計ポップアップに反映するため state には常に
        通すが、人間可読でないためログペインへは表示しない（verbosity に
        依らず常に抑止）。
        """
        # R1: fatal マーカー検知（行頭限定）→ 状態更新 + 必要なら subprocess を停止
        self._detect_fatal_marker(line)
        if self._fatal_detected:
            self._terminate_subprocess_for_fatal()

        process_subprocess_line(self._state, line)
        if not is_stats_line(line):
            # Plan モード: 表示用に `[wf_id]-[step]` プリフィックスを付与する。
            display_line = self._apply_plan_mode_prefix(line)
            self._log_pane.append_line(display_line)
            # Plan モードでも Step クリック時に `inst.step_log_buffers[step_id]` を
            # 「選択中」タブへ表示できるよう、WorkflowInstance バッファへも蓄積する。
            wf_id = self._current_workflow_id
            if wf_id:
                if wf_id not in self._state.workflows:
                    self._state.ensure_workflow_instance(
                        instance_id=wf_id,
                        workflow_id=wf_id,
                        label=wf_id,
                    )
                sid = (
                    getattr(self._state, "current_running_step_id", None)
                    or getattr(self._state, "last_known_step_id", None)
                )
                # append_workflow_log 側でも自前のプリフィックスを付与するため、
                # 二重プリフィックスを避けるため raw line を渡す。
                # （戻り値の formatted を _log_pane にも渡したいところだが、
                # 既存 display_line と整合させるため Plan モードでは _log_pane への
                # 表示は display_line（_apply_plan_mode_prefix 経由）を維持する）。
                self._state.append_workflow_log(wf_id, sid, line)
        # [hve:stats] step_status イベントを ActivityStatusWidget が参照する
        # _workflow_step_status へ反映する。process_subprocess_line は
        # WorkbenchState.task_tree 側にのみ反映するため、表示ウィジェット側へは
        # 別経路で反映する必要がある。
        payload = parse_stats_event(line)
        if payload is not None and payload.get("kind") == "step_status":
            self._apply_stats_step_status(payload)
        self._update_workflow_progress_from_line(line)
        self._update_subtask_from_line(line)

    @Slot(int)
    def _on_process_finished(self, returncode: int) -> None:
        self._return_codes.append(returncode)
        current_wf = self._current_workflow_id or "unknown"
        self._log_pane.append_line(
            f"\n--- セッション終了 ({self._queue_index + 1}/{len(self._args_queue)}) workflow={current_wf} (returncode={returncode}) ---"
        )
        if returncode != 0:
            self._log_pane.append_line(
                f"[WARN] workflow={current_wf} が失敗しました。次のワークフローへ進みます。"
            )

        # R1: fatal 検知時はキュー残作業をクリアし、現在 workflow を "致命的" 状態に
        fatal_active = self.was_fatal()
        if fatal_active and self._current_workflow_id:
            info = self._fatal_info or {}
            exc_type = info.get("exception_type", "FatalError")
            self._workflow_status[self._current_workflow_id] = f"致命的 ({exc_type})"
            # Phase 3b (Q9=a): state へミラー (致命的 → failed)
            try:
                self._state.update_workflow_instance_status(
                    self._current_workflow_id, "failed"
                )
            except (AttributeError, ValueError):
                pass
        elif self._current_workflow_id:
            self._workflow_status[self._current_workflow_id] = "完了"
            # Phase 3b (Q9=a): state へミラー (returncode で done/failed 判別)
            try:
                self._state.mark_workflow_instance_finished(
                    self._current_workflow_id, returncode
                )
            except AttributeError:
                pass
        if self._current_workflow_id:
            self._progress_widget.set_plan(
                self._workflow_plan,
                self._workflow_status,
                self._workflow_step_status,
                self._workflow_subtask_status,
            )

        # QA IPC マネージャの停止・クリーンアップ
        if self._qa_ipc_manager is not None:
            try:
                self._qa_ipc_manager.stop_and_cleanup()
            except Exception as exc:
                self._log_pane.append_line(f"[WARN] QA IPC マネージャ停止失敗: {exc}")
            self._qa_ipc_manager = None
        self._current_qa_subprocess = None

        self._reader = None
        self._queue_index += 1

        # R1: fatal 検知時は残りのキューを切り捨て即終了。
        if fatal_active:
            # 既に消化済みの分（_queue_index まで）は保持し、未実行分のみ削除。
            self._args_queue = self._args_queue[: self._queue_index]
            self._is_running = False
            self._state.mark_all_done()
            self._update_ui()
            self.process_finished.emit(returncode)
            return

        if self._stop_requested:
            self._is_running = False
            self._state.mark_all_done()
            self._update_ui()
            self.process_finished.emit(returncode)
            return

        QTimer.singleShot(0, self._start_next_in_queue)

    # ----------------------------------------------------------
    # QA IPC ハンドラ（qa_answer_mode="gui-file" 時のみ動作）
    # ----------------------------------------------------------

    @Slot(str, str, str)
    def _on_qa_questionnaire_ready(
        self, step_id: str, questionnaire_path: str, ipc_dir: str
    ) -> None:
        """CLI が QA 質問票 IPC リクエストを書き出した → ダイアログを順次表示。

        既にダイアログ表示中の場合は内部キューに積み、現在のダイアログが閉じた
        タイミングで次のダイアログを表示する（複数 step の質問票に順次対応）。
        """
        # 既に別の QA ダイアログを表示中ならキューに積んで終了
        if self._qa_active_dialog is not None:
            self._log_pane.append_line(
                f"[INFO] QA ダイアログ表示中のためキューに積みました (step={step_id})"
            )
            self._qa_pending_queue.append((step_id, questionnaire_path))
            return

        self._show_qa_dialog(step_id, questionnaire_path)

    def _show_qa_dialog(self, step_id: str, questionnaire_path: str) -> None:
        """QA 回答ダイアログを実際に表示する。"""
        try:
            from .qa_answer_dialog import QAAnswerDialog
        except ImportError as exc:
            self._log_pane.append_line(
                f"[ERROR] QA 回答ダイアログの読み込みに失敗: {exc}"
            )
            self._handle_qa_dialog_fallback(step_id, cancel=False)
            self._drain_qa_queue()
            return

        try:
            from ..qa_merger import QAMerger
        except ImportError:
            try:
                from qa_merger import QAMerger  # type: ignore[no-redef]
            except ImportError as exc:
                self._log_pane.append_line(
                    f"[ERROR] QAMerger の読み込みに失敗: {exc}"
                )
                self._handle_qa_dialog_fallback(step_id, cancel=False)
                self._drain_qa_queue()
                return

        try:
            qa_doc = QAMerger.parse_qa_file(Path(questionnaire_path))
        except Exception as exc:
            self._log_pane.append_line(
                f"[ERROR] QA 質問票のパース失敗 ({questionnaire_path}): {exc}"
            )
            self._handle_qa_dialog_fallback(step_id, cancel=False)
            self._drain_qa_queue()
            return

        self._log_pane.append_line(
            f"[INFO] QA 回答ダイアログを表示します (step={step_id},"
            f" 質問数={len(qa_doc.questions)})"
        )
        dialog = QAAnswerDialog(qa_doc, step_id=step_id, parent=self)
        # GC 防止のため強参照を保持
        self._qa_active_dialog = dialog

        def _on_submit(content: str) -> None:
            if self._qa_ipc_manager is not None:
                ok = self._qa_ipc_manager.write_answers(step_id, content)
                if ok:
                    self._log_pane.append_line(
                        f"[INFO] QA 回答を CLI に送信しました (step={step_id})"
                    )
                else:
                    self._log_pane.append_line(
                        f"[WARN] QA 回答書き込み失敗 (step={step_id})"
                    )

        def _on_defaults() -> None:
            if self._qa_ipc_manager is not None:
                self._qa_ipc_manager.write_answers(step_id, "")
                self._log_pane.append_line(
                    f"[INFO] QA: 全問既定値で進めます (step={step_id})"
                )

        def _on_cancel() -> None:
            self._log_pane.append_line(
                f"[INFO] QA 回答キャンセル → サブプロセスを停止します (step={step_id})"
            )
            if self._qa_ipc_manager is not None:
                self._qa_ipc_manager.write_cancel(step_id)
            # subprocess を停止（後続のキューも無効化される）
            self._qa_pending_queue.clear()
            self.stop_orchestrator()

        def _on_finished(_result: int) -> None:
            """ダイアログが閉じた（submit/defaults/cancel/× いずれか） → 参照解放＋次を処理。"""
            self._qa_active_dialog = None
            # キューに次があれば順次表示
            self._drain_qa_queue()

        dialog.submitted.connect(_on_submit)
        dialog.adopt_all_defaults.connect(_on_defaults)
        dialog.cancelled.connect(_on_cancel)
        dialog.finished.connect(_on_finished)
        dialog.show()
        # Windows / 背面 issue 対策: 明示的に前面表示・アクティブ化する
        try:
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass

    def _drain_qa_queue(self) -> None:
        """キューに積まれた次の質問票を表示する。"""
        if self._qa_active_dialog is not None:
            return
        if not self._qa_pending_queue:
            return
        step_id, q_path = self._qa_pending_queue.pop(0)
        # QTimer.singleShot で次イベントループに遅延（前ダイアログのクリーンアップ完了後に表示）
        QTimer.singleShot(0, lambda: self._show_qa_dialog(step_id, q_path))

    def _handle_qa_dialog_fallback(self, step_id: str, cancel: bool) -> None:
        """ダイアログ表示失敗時のフォールバック。"""
        if self._qa_ipc_manager is None:
            return
        if cancel:
            self._qa_ipc_manager.write_cancel(step_id)
        else:
            # 既定値採用で進める
            self._qa_ipc_manager.write_answers(step_id, "")

    @Slot()
    def _on_qa_subprocess_terminated(self) -> None:
        """subprocess が終了した（QA 待機中含む） → IPC マネージャを停止。"""
        # 未処理のキューはクリア（subprocess 終了後にダイアログを出す意味が無い）
        self._qa_pending_queue.clear()
        if self._qa_ipc_manager is not None:
            try:
                self._qa_ipc_manager.stop_and_cleanup()
            except Exception:
                pass
            self._qa_ipc_manager = None

    def _build_workflow_plan(self, args_queue: List[OrchestrateArgs]) -> List[dict]:
        """実行キューから進捗表示用の workflow/step 計画を組み立てる。

        各 step 要素は ``{"id": str, "title": str, "depends_on": List[str]}`` の dict 形式
        （DagStatusWidget のレイアウト計算に必要な依存情報を含む）。
        """
        plan: List[dict] = []
        for args in args_queue:
            wf_id = args.workflow
            wf = get_workflow(wf_id)
            wf_name = wf.name if wf is not None else wf_id
            steps: List[dict] = []
            if wf is not None:
                steps = [
                    {
                        "id": s.id,
                        "title": s.title,
                        "depends_on": list(s.depends_on),
                    }
                    for s in wf.steps
                    if not s.is_container
                ]
            plan.append(
                {
                    "workflow_id": wf_id,
                    "workflow_name": wf_name,
                    "steps": steps,
                }
            )
        return plan

    def _apply_stats_step_status(self, payload: dict) -> None:
        """``[hve:stats] {"kind":"step_status",...}`` を ``_workflow_step_status``
        へ反映する。

        既存 ``_update_workflow_progress_from_line`` のマッピングと整合させ、
        ``done`` / ``failed`` / ``skipped`` は ``"完了"`` に丸める
        （``_workflow_status`` 集計ロジックとの互換維持）。

        ``stats_event`` payload には ``wf_id`` が含まれないため、
        ``_current_workflow_id`` 未設定時は wf 紐付け不能として破棄する。
        """
        if not self._current_workflow_id:
            return
        step_id = (payload.get("step") or payload.get("step_id") or "")
        if isinstance(step_id, str):
            step_id = step_id.strip()
        else:
            step_id = ""
        status = (payload.get("status") or "")
        if isinstance(status, str):
            status = status.strip()
        else:
            status = ""
        if not step_id or status not in ("running", "done", "failed", "skipped"):
            return
        if status == "running":
            state_text = "実行中"
        else:  # done / failed / skipped
            state_text = "完了"
        wf_step_map = self._workflow_step_status.setdefault(
            self._current_workflow_id, {}
        )
        if step_id not in wf_step_map:
            # plan 外の step は無視（暗黙生成しない）
            return
        if wf_step_map[step_id] == state_text:
            return  # 冪等: 変化なし
        wf_step_map[step_id] = state_text
        # Phase 3b (Q9=a): state へミラー (status は内部キー名で渡す)
        try:
            self._state.update_step_status_in_instance(
                self._current_workflow_id, step_id, status  # type: ignore[arg-type]
            )
        except (AttributeError, ValueError):
            pass
        # 即応性のため即時 set_plan を呼ぶ（500ms タイマー待ちを避ける）。
        # ActivityStatusWidget._record_timing は entry 既存時 no-op のため
        # 冪等で副作用なし。
        self._progress_widget.set_plan(
            self._workflow_plan,
            self._workflow_status,
            self._workflow_step_status,
            self._workflow_subtask_status,
        )

    def _update_workflow_progress_from_line(self, line: str) -> None:
        if not self._current_workflow_id:
            return

        timestamp, step_id, _level, message = parse_log_line(line)
        if not (timestamp and step_id and message):
            return
        if step_id in ("[main]", "main"):
            return

        hint = extract_step_status_hint(message)

        wf_step_map = self._workflow_step_status.setdefault(self._current_workflow_id, {})

        if hint is None:
            # ヒントが無くても、当該ステップに紐づく最初のログ行が来た時点で
            # 「実行中」とみなしてタイマー起動する（暗黙開始検出）。
            # 既に "実行中" / "完了" 等が確定済みの場合は触らない。
            if step_id in wf_step_map and wf_step_map[step_id] == "":
                wf_step_map[step_id] = "実行中"
                # Phase 3b (Q9=a): state へミラー
                try:
                    self._state.update_step_status_in_instance(
                        self._current_workflow_id, step_id, "running"
                    )
                except (AttributeError, ValueError):
                    pass
                self._progress_widget.set_plan(
                    self._workflow_plan,
                    self._workflow_status,
                    self._workflow_step_status,
                    self._workflow_subtask_status,
                )
            return

        if hint == "running":
            state_text = "実行中"
            mirror_status = "running"
        elif hint in ("done", "failed", "skipped"):
            state_text = "完了"
            mirror_status = hint  # type: ignore[assignment]
        else:
            return

        if step_id in wf_step_map:
            wf_step_map[step_id] = state_text
            # Phase 3b (Q9=a): state へミラー
            try:
                self._state.update_step_status_in_instance(
                    self._current_workflow_id, step_id, mirror_status  # type: ignore[arg-type]
                )
            except (AttributeError, ValueError):
                pass
            self._progress_widget.set_plan(
                self._workflow_plan,
                self._workflow_status,
                self._workflow_step_status,
                self._workflow_subtask_status,
            )

    def _update_subtask_from_line(self, line: str) -> None:
        """Sub-agent ログ行を検出して進捗表示にサブタスクを反映する。

        ログ形式は hve/console.py の subagent_started/_completed/_failed が
        出力する確定行（例: ``▶ [step1] Sub-agent: code-reviewer``）。
        """
        if not self._current_workflow_id:
            return
        event = parse_subagent_event(line)
        if event is None:
            return
        step_id, name, status = event
        if not step_id:
            # step_id が無い行は表示先が決まらないので無視
            return

        wf_id = self._current_workflow_id
        wf_step_map = self._workflow_subtask_status.setdefault(wf_id, {})
        # 未知 step も許容（plan 外の subtask を捨てないため）
        sub_list = wf_step_map.setdefault(step_id, [])

        if status == "running":
            # 同 (wf, step, name) の出現回数で child_id を採番
            seq_key = (wf_id, step_id, name)
            seq = self._subtask_seq.get(seq_key, 0) + 1
            self._subtask_seq[seq_key] = seq
            subtask_id = (
                f"{step_id}::subagent::{name}"
                if seq == 1
                else f"{step_id}::subagent::{name}#{seq}"
            )
            sub_list.append((subtask_id, f"Sub-agent: {name}", "実行中"))
            # Phase 3b (Q9=a): state へミラー
            try:
                self._state.add_step_subtask(
                    instance_id=wf_id,
                    parent_step_id=step_id,
                    subtask_id=subtask_id,
                    title=f"Sub-agent: {name}",
                    kind="subagent",
                    status="running",
                )
            except (AttributeError, TypeError):
                pass
        else:
            # done / failed: 直近の同名・running を更新（無ければ末尾追加）
            new_state = "完了" if status == "done" else "失敗"
            mirror_status = "done" if status == "done" else "failed"
            matched = False
            target_sub_id: "Optional[str]" = None
            for i in range(len(sub_list) - 1, -1, -1):
                sub_id, title, state = sub_list[i]
                if title == f"Sub-agent: {name}" and state == "実行中":
                    sub_list[i] = (sub_id, title, new_state)
                    target_sub_id = sub_id
                    matched = True
                    break
            if not matched:
                target_sub_id = f"{step_id}::subagent::{name}"
                sub_list.append(
                    (target_sub_id, f"Sub-agent: {name}", new_state)
                )
            # Phase 3b (Q9=a): state へミラー
            try:
                if target_sub_id is not None:
                    # 親が存在しない場合に備え add_step_subtask で先行登録（冪等）
                    self._state.add_step_subtask(
                        instance_id=wf_id,
                        parent_step_id=step_id,
                        subtask_id=target_sub_id,
                        title=f"Sub-agent: {name}",
                        kind="subagent",
                        status="running",
                    )
                    self._state.update_step_status_in_instance(
                        wf_id, target_sub_id, mirror_status  # type: ignore[arg-type]
                    )
            except (AttributeError, ValueError, TypeError):
                pass

        self._progress_widget.set_plan(
            self._workflow_plan,
            self._workflow_status,
            self._workflow_step_status,
            self._workflow_subtask_status,
        )

    @Slot()
    def _on_state_all_done(self) -> None:
        self._update_ui()

    @Slot()
    def _show_stats_detail_popup(self) -> None:
        """Footer の「📊 統計情報」クリック → 統計情報ウィンドウを表示する。

        Qt.Tool ノンモーダルウィンドウとして開き、「スナップショット」と
        「今回の実行履歴」の 2 タブを提供する。複数回クリック時は前のウィンドウを
        閉じて再生成する。
        """
        from .stats_detail_popup import StatsDetailPopup

        popup = StatsDetailPopup(self._state, parent=self)
        # 古い popup があれば閉じておく
        if self._stats_popup is not None:
            try:
                self._stats_popup.close()
            except Exception:
                pass
        self._stats_popup = popup

        # 表示位置: Footer ボタンの右下に揃え、画面外に出ないよう左上を調整
        try:
            btn = self._footer._detail_btn  # type: ignore[attr-defined]
            anchor_global = btn.mapToGlobal(btn.rect().bottomRight())
            popup.adjustSize()
            sz = popup.sizeHint()
            popup.move(anchor_global.x() - sz.width(), anchor_global.y() - sz.height() - btn.height())
        except Exception:
            pass
        popup.show()
        popup.raise_()
        popup.activateWindow()

    @Slot()
    def _on_state_changed(self, *args) -> None:
        self._update_ui()

    @Slot()
    def _on_update_timer(self) -> None:
        """周期的にUIを更新。"""
        self._update_ui()

    def _update_ui(self) -> None:
        """WorkbenchState に基づいてUIを更新。

        Phase 3b (Q9=a): レンダリングの単一 source として ``state.workflows`` を使う。
        Plan モード経路は ``_mirror_plan_to_state`` と各 status イベント時の
        ミラー書き込みにより ``state.workflows`` が常に最新を保つ。Autopilot 経路は
        ``append_log`` → ``_apply_log_line_to_instance_tree`` で同様に更新される。
        どちらの経路でも ``update_workflow_instances`` 1 本で描画する。
        """
        if getattr(self._state, "workflows", None):
            self._progress_widget.update_workflow_instances(self._state)
        self._header2.update_state(self._state)
        self._user_actions_pane.update_from_state(self._state)
        self._footer.update_state(self._state)
        self._apply_responsive_fallback()

    def reset_for_autopilot(self) -> None:
        """Autopilot 起動時に Workbench の前回実行残骸をクリアする。

        - ``_progress_widget`` をリセット（plan モード残骸とツリー描画をクリア）
        - plan モード関連の内部ステートを空に戻す
        - ``state.workflows`` をクリア（前回 Autopilot 実行の WorkflowInstance
          残骸が累積するのを防ぐ）
        - ``_current_workflow_id`` / ``_subtask_seq`` もクリアし、Header1 の
          強調状態と Sub-agent 番号を初期化する
          (gui-workbench-autopilot-display レビュー #1)。

        通常実行 (`start_orchestrators`) は `_progress_widget.reset()` を内部で
        呼ぶが、Autopilot 経路は `start_orchestrators` を経由しないため本 API を
        明示的に呼ぶ必要がある。
        """
        self._progress_widget.reset()
        self._workflow_plan = []
        self._workflow_status = {}
        self._workflow_step_status = {}
        self._workflow_subtask_status = {}
        self._current_workflow_id = None
        self._subtask_seq = {}
        # 前回 Autopilot 実行の WorkflowInstance 残骸（state.workflows）も
        # クリアする。クリアしないと別 APP セットでの再 Autopilot 時に
        # 旧 instance がツリーに累積表示される。
        try:
            self._state.workflows.clear()
        except AttributeError:
            pass

    def prepopulate_workflow_instances(self, seeds) -> None:
        """Step 1 で確定した全ワークフローを ``state.workflows`` へ pending 事前登録する。

        Autopilot 起動経路（``main_window._start_autopilot`` ほか）から呼ばれる。
        Q14=a / Q4=A: ``instance_id = workflow_id`` または ``f"{workflow_id}#{app_id}"``
        の命名規約で seed を受け取り、``WorkflowInstance`` を pending 状態で生成する。
        既存 instance_id があれば**スキップ**（冪等）。

        呼び出し後すぐ ``ActivityStatusWidget.update_workflow_instances`` 経由で
        ツリーに反映されるよう、内部の `_update_ui` も即時トリガする。

        さらに Autopilot 経路では workflow plan を ``_workflow_plan`` にマージし、
        ActivityStatus ツリーの描画に反映する。

        Args:
            seeds: ``List[WorkflowInstanceSeed]``。各要素が
                ``(instance_id, workflow_id, label, app_id, steps)`` を持つ。
        """
        if not seeds:
            return
        try:
            self._state.prepopulate_workflow_instances(seeds)
        except AttributeError:
            return
        # Autopilot 経路で workflow plan をマージ反映する。
        # 既存 _workflow_plan に追加形式で反映し、重複 workflow_id は無視する。
        merged_plan = self._merge_seeds_into_workflow_plan(seeds)
        if merged_plan:
            self._workflow_plan = merged_plan
        # ツリー即時更新（500ms タイマー待ちを避ける）
        self._update_ui()

    def _merge_seeds_into_workflow_plan(self, seeds) -> List[dict]:
        """seeds から workflow 単位の plan エントリを構築し既存 plan にマージする。

        複数 app_id で同 workflow_id を持つ seed は 1 件に集約する。
        workflow_name は空のまま登録し、参照側 (registry / template_engine) で
        解決させる。

        Args:
            seeds: ``List[WorkflowInstanceSeed]``

        Returns:
            既存 ``self._workflow_plan`` をベースにマージした新しい plan リスト。
        """
        plan: List[dict] = list(self._workflow_plan)
        existing_ids = {str(wf.get("workflow_id", "")) for wf in plan}
        for seed in seeds:
            wf_id = str(getattr(seed, "workflow_id", "") or "")
            if not wf_id or wf_id in existing_ids:
                continue
            # workflow_name は空として登録し、参照側で registry / template_engine
            # 経由で解決させる。
            plan.append(
                {
                    "workflow_id": wf_id,
                    "workflow_name": "",
                    "steps": [],
                }
            )
            existing_ids.add(wf_id)
        return plan

    def update_identity_from_session(self, run_id: Optional[str]) -> None:
        """Autopilot 起動時にセッション run_id を state へ反映する。

        ``WorkbenchState.update_identity`` 経由で run_id を更新する。

        Args:
            run_id: セッション run_id (空文字 / None の場合は no-op)。
        """
        if not run_id:
            return
        try:
            self._state.update_identity(run_id=str(run_id))
        except AttributeError:
            # WorkbenchState API 不整合時のフォールバック (レビュー #7)
            pass

    def remove_workflow_instance(self, instance_id: str) -> None:
        """placeholder インスタンスを ``state.workflows`` から削除する (T3b)。

        Autopilot の app_chains 起動時に、pre_phase 段階で先行投入した
        ``instance_id=workflow_id`` 形式の placeholder を削除し、本 seed
        (``{workflow_id}#{app_id}``) と二重表示しないようにするために使う。

        Args:
            instance_id: 削除対象の instance_id。未登録なら no-op。
        """
        if not instance_id:
            return
        try:
            self._state.remove_workflow_instance(instance_id)
        except (AttributeError, KeyError):
            return
        self._update_ui()

    def _apply_responsive_fallback(self) -> None:
        """高さ不足時に UserActions ペインを非表示にするフォールバック。"""
        h = max(0, self.height())
        need_full = _BASE_NON_SPLITTER_HEIGHT + _UA_PANEL_HEIGHT
        show_useractions = h >= need_full
        self._user_actions_pane.setVisible(show_useractions)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_fallback()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Up:
            self._scroll_log(-3)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            self._scroll_log(3)
            event.accept()
            return
        if text == "[":
            self._user_actions_pane.scroll_by(-3)
            event.accept()
            return
        if text == "]":
            self._user_actions_pane.scroll_by(3)
            event.accept()
            return
        if text == "g":
            self._log_pane.log_view.verticalScrollBar().setValue(0)
            self._user_actions_pane.scroll_top()
            event.accept()
            return
        if text == "G":
            sb = self._log_pane.log_view.verticalScrollBar()
            if sb is not None:
                sb.setValue(sb.maximum())
            self._user_actions_pane.scroll_bottom()
            event.accept()
            return

        super().keyPressEvent(event)

    def _scroll_log(self, delta: int) -> None:
        sb = self._log_pane.log_view.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.value() + delta)

    # ----------------------------------------------------------
    # クリーンアップ
    # ----------------------------------------------------------

    def cleanup(self) -> None:
        """ウィンドウクローズ時などに呼び出す。"""
        if hasattr(self, "_update_timer"):
            self._update_timer.stop()
        if hasattr(self, "_progress_widget"):
            self._progress_widget.stop()
        self.stop_orchestrator()

    def apply_theme_from_settings(self) -> None:
        """設定 (`options.theme`) を再読込し、作業状況ツリーへ反映する。"""
        from . import settings_store

        theme = settings_store.get_option("theme") or "light"
        if theme not in ("dark", "light"):
            theme = "light"
        if hasattr(self, "_progress_widget"):
            self._progress_widget.set_theme(theme)
