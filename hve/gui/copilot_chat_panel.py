"""hve.gui.copilot_chat_panel — Copilot CLI 対話ドックと実行ジョブ連携。

構成（FR-GUI-10〜15 / FR-GUI-18）:
  - 「Copilot CLI」タブ: `copilot` の対話 TUI を PTY + xterm.js ビューへ埋め込み、
    1 本の永続セッションとして保持する。モデル選択・コンテキスト管理・権限・MCP・
    plugin・skill は CLI 側の機能をそのまま利用する（GUI 側で再実装しない）。
  - 「実行ジョブ」タブ: Visual Studio Code のチャットビューと同じ構成（会話ビュー /
    送信待ちキュー / 入力ボックス / 状態行）で、実行中のワークフローステップを
    宛先として選び、キュー追加 / 割り込み / 中断して送信 を IPC 経由で依頼する。
    完了ジョブは参照専用で、成果物パスを添えて新しい CLI セッションを開始できる。

セキュリティ:
  - PTY へは argv を配列で渡す（シェル連結しない）。
  - `--allow-all*` / `--yolo` / 非対話用フラグを GUI から暗黙付与しない。
  - 入力長は 8KB に制限する（添付パスを含めた送信本文で判定する）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hve.job_interaction_ipc import (
    JobInteractionRequest,
    cancel_request,
    list_acks,
    list_pending_requests,
    reorder_pending,
    write_request,
)

from .copilot_interactive_session import (
    CopilotInteractiveSession,
    CopilotInteractiveSessionError,
)
from .copilot_job_context import build_job_result_context
from .job_interaction_model import JobTarget
from .widgets.chat_input_box import ChatInputBox
from .widgets.chat_transcript import ChatTranscriptView

__all__ = ["CopilotChatPanel"]

_MAX_INPUT_BYTES = 8 * 1024
_ACK_POLL_INTERVAL_MS = 1000
_PENDING_LIST_MAX_HEIGHT = 84
_TURN_LABEL_MAX_CHARS = 60


def _elide_turn_text(text: str) -> str:
    """ターン見出し用に 1 行へ収める。改行以降と上限超過分は省略記号へ置き換える。"""
    first, separator, _rest = text.partition("\n")
    if len(first) > _TURN_LABEL_MAX_CHARS or separator:
        return first[:_TURN_LABEL_MAX_CHARS] + "…"
    return first


class CopilotChatPanel(QDockWidget):
    """右側にドッキングする Copilot 対話 / ジョブ連携パネル。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        repo_root: Optional[Path] = None,
        terminal_factory: Optional[Callable[[], QWidget]] = None,
        session_factory: Optional[Callable[[Any, Path], Any]] = None,
    ) -> None:
        super().__init__("GitHub Copilot", parent)
        self.setObjectName("CopilotChatDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )

        self._repo_root: Path = Path(repo_root) if repo_root else Path.cwd()
        self._workbench_page: Optional[Any] = None
        self._targets: List[JobTarget] = []
        self._terminal_factory = terminal_factory
        self._session_factory = session_factory or self._default_session_factory
        self._terminal_view: Optional[QWidget] = None
        self._session: Optional[Any] = None
        # request_id -> (channel_dir, action)
        self._pending_acks: Dict[str, Tuple[str, str]] = {}
        self._turn_index = -1

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_cli_tab(), self.tr("Copilot CLI"))
        self._tabs.addTab(self._build_job_tab(), self.tr("実行ジョブ"))
        self.setWidget(self._tabs)
        self.resize(520, 700)

        self._ack_timer = QTimer(self)
        self._ack_timer.setInterval(_ACK_POLL_INTERVAL_MS)
        self._ack_timer.timeout.connect(self.poll_acks)
        self._ack_timer.timeout.connect(self.refresh_pending_queue)
        self._ack_timer.start()

        self._update_cli_status()
        self._update_job_controls()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_cli_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._cli_status = QLabel()
        self._cli_status.setProperty("hveRole", "description")
        self._cli_status.setWordWrap(True)
        self._cli_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._cli_status.setAccessibleName(self.tr("Copilot CLI セッションの状態"))
        layout.addWidget(self._cli_status)

        self._cli_host = QWidget(page)
        self._cli_host_layout = QVBoxLayout(self._cli_host)
        self._cli_host_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._cli_host, 1)

        row = QHBoxLayout()
        self._cli_start_btn = QPushButton(self.tr("セッション開始"))
        self._cli_start_btn.setAccessibleName(self.tr("Copilot CLI セッションを開始"))
        self._cli_start_btn.clicked.connect(self._on_start_clicked)
        self._cli_stop_btn = QPushButton(self.tr("セッション停止"))
        self._cli_stop_btn.setAccessibleName(self.tr("Copilot CLI セッションを停止"))
        self._cli_stop_btn.setEnabled(False)
        self._cli_stop_btn.clicked.connect(self.stop_cli_session)
        row.addWidget(self._cli_start_btn)
        row.addWidget(self._cli_stop_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_job_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._job_tab_layout = layout

        layout.addLayout(self._build_job_header())

        self._turn_nav_bar = self._build_turn_nav_bar(page)
        layout.addWidget(self._turn_nav_bar)

        self._transcript = ChatTranscriptView(page)
        layout.addWidget(self._transcript, 1)
        scroll_bar = self._transcript.verticalScrollBar()
        if scroll_bar is not None:
            scroll_bar.valueChanged.connect(self._on_transcript_scrolled)

        self._pending_bar = self._build_pending_bar(page)
        layout.addWidget(self._pending_bar)

        self._input_box = ChatInputBox(page)
        self._input_box.submitted.connect(self._on_job_send_clicked)
        self._input_box.attach_requested.connect(self._on_attach_requested)
        layout.addWidget(self._input_box)

        self._status_footer = QLabel(page)
        self._status_footer.setProperty("hveRole", "description")
        self._status_footer.setWordWrap(True)
        self._status_footer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._status_footer.setAccessibleName(self.tr("選択したジョブの状態"))
        layout.addWidget(self._status_footer)
        return page

    def _build_job_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        target_label = QLabel(self.tr("対象ジョブ:"))
        self._target_combo = QComboBox()
        self._target_combo.setAccessibleName(self.tr("対話対象の実行ジョブ"))
        target_label.setBuddy(self._target_combo)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        refresh_btn = QPushButton(self.tr("更新"))
        refresh_btn.setAccessibleName(self.tr("実行ジョブ一覧を更新"))
        refresh_btn.clicked.connect(self.refresh_job_targets)

        self._overflow_menu = QMenu(self)
        self._overflow_menu.addAction(self.tr("会話をクリア"), self.clear_transcript)
        self._overflow_menu.addAction(self.tr("会話をコピー"), self.copy_transcript)
        self._open_result_action = self._overflow_menu.addAction(
            self.tr("結果を Copilot で開く"), self.open_selected_job_result
        )
        self._overflow_btn = QToolButton()
        self._overflow_btn.setText("⋯")
        self._overflow_btn.setAutoRaise(True)
        self._overflow_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._overflow_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._overflow_btn.setAccessibleName(self.tr("その他の操作"))
        self._overflow_btn.setToolTip(self.tr("その他の操作"))
        self._overflow_btn.setMenu(self._overflow_menu)

        row.addWidget(target_label)
        row.addWidget(self._target_combo, 1)
        row.addWidget(refresh_btn)
        row.addWidget(self._overflow_btn)
        return row

    def _build_turn_nav_bar(self, parent: QWidget) -> QWidget:
        """FR-GUI-18: 送信メッセージの現在位置と前後移動。"""
        bar = QWidget(parent)
        bar.setProperty("hveRole", "noteBox")
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(4)

        self._turn_label = QLabel(bar)
        self._turn_label.setProperty("hveRole", "description")
        self._turn_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._turn_label.setAccessibleName(self.tr("現在の送信メッセージ"))
        self._turn_position = QLabel(bar)
        self._turn_position.setAccessibleName(self.tr("送信メッセージの位置"))
        self._turn_prev_btn = QToolButton(bar)
        self._turn_prev_btn.setText("▲")
        self._turn_prev_btn.setAccessibleName(self.tr("前の送信メッセージへ"))
        self._turn_prev_btn.setToolTip(self.tr("前の送信メッセージへ"))
        self._turn_prev_btn.clicked.connect(self.goto_previous_turn)
        self._turn_next_btn = QToolButton(bar)
        self._turn_next_btn.setText("▼")
        self._turn_next_btn.setAccessibleName(self.tr("次の送信メッセージへ"))
        self._turn_next_btn.setToolTip(self.tr("次の送信メッセージへ"))
        self._turn_next_btn.clicked.connect(self.goto_next_turn)

        row.addWidget(self._turn_label, 1)
        row.addWidget(self._turn_position)
        row.addWidget(self._turn_prev_btn)
        row.addWidget(self._turn_next_btn)

        bar.hide()
        return bar

    def _build_pending_bar(self, parent: QWidget) -> QWidget:
        """FR-GUI-12 が許可する未消費要求の取り消し・並べ替えを提供する。"""
        bar = QWidget(parent)
        bar.setProperty("hveRole", "noteBox")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self._pending_list = QListWidget(bar)
        self._pending_list.setAccessibleName(self.tr("送信待ちのメッセージ"))
        self._pending_list.setMaximumHeight(_PENDING_LIST_MAX_HEIGHT)
        layout.addWidget(self._pending_list, 1)

        buttons = QVBoxLayout()
        buttons.setSpacing(2)
        self._pending_up_btn = QToolButton(bar)
        self._pending_up_btn.setText("↑")
        self._pending_up_btn.setAccessibleName(self.tr("送信待ちを上へ"))
        self._pending_up_btn.clicked.connect(lambda: self.move_selected_pending(-1))
        self._pending_down_btn = QToolButton(bar)
        self._pending_down_btn.setText("↓")
        self._pending_down_btn.setAccessibleName(self.tr("送信待ちを下へ"))
        self._pending_down_btn.clicked.connect(lambda: self.move_selected_pending(1))
        self._pending_cancel_btn = QToolButton(bar)
        self._pending_cancel_btn.setText("×")
        self._pending_cancel_btn.setAccessibleName(self.tr("送信待ちを取り消す"))
        self._pending_cancel_btn.clicked.connect(self.cancel_selected_pending)
        buttons.addWidget(self._pending_up_btn)
        buttons.addWidget(self._pending_down_btn)
        buttons.addWidget(self._pending_cancel_btn)
        layout.addLayout(buttons)

        bar.hide()
        return bar

    # ------------------------------------------------------------------
    # 公開 API（MainWindow から利用）
    # ------------------------------------------------------------------

    def set_repo_root(self, repo_root: Path) -> None:
        """リポジトリルートを更新する。"""
        self._repo_root = Path(repo_root)
        if self._session is not None:
            self._session.set_repo_root(self._repo_root)
        self._update_cli_status()

    def set_workbench_page(self, page: Any) -> None:
        """ジョブ対話 API を持つ WorkbenchPage を注入する。"""
        self._workbench_page = page
        signal = getattr(page, "job_log_line", None)
        if signal is not None and hasattr(signal, "connect"):
            try:
                signal.connect(self.on_job_log_line)
            except (RuntimeError, TypeError):
                pass
        self.refresh_job_targets()

    def shutdown(self) -> None:
        """パネルを終了する（対話セッションと ACK 監視を停止）。"""
        self._ack_timer.stop()
        session = self._session
        self._session = None
        if session is not None:
            session.stop()

    # ------------------------------------------------------------------
    # Copilot CLI タブ
    # ------------------------------------------------------------------

    def tab_titles(self) -> List[str]:
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def cli_status_text(self) -> str:
        return self._cli_status.text()

    def start_cli_session(self, initial_prompt: Optional[str] = None) -> bool:
        """永続対話セッションを開始する。成功したら True。"""
        session = self._ensure_session()
        if session is None:
            return False
        try:
            session.start(initial_prompt=initial_prompt)
        except CopilotInteractiveSessionError as exc:
            self._cli_status.setText(str(exc))
            return False
        self._update_cli_status()
        return True

    def stop_cli_session(self) -> None:
        if self._session is not None:
            self._session.stop()
        self._update_cli_status()

    def _on_start_clicked(self) -> None:
        self.start_cli_session()

    def _default_session_factory(self, view: Any, repo_root: Path) -> Any:
        return CopilotInteractiveSession(view, repo_root=repo_root, parent=self)

    def _ensure_session(self) -> Optional[Any]:
        if self._session is not None:
            return self._session
        view = self._ensure_terminal_view()
        if view is None:
            return None
        session = self._session_factory(view, self._repo_root)
        finished = getattr(session, "finished", None)
        if finished is not None and hasattr(finished, "connect"):
            try:
                finished.connect(self._on_session_finished)
            except (RuntimeError, TypeError):
                pass
        self._session = session
        return session

    def _ensure_terminal_view(self) -> Optional[QWidget]:
        if self._terminal_view is not None:
            return self._terminal_view
        factory = self._terminal_factory or self._default_terminal_factory
        try:
            view = factory()
        except Exception as exc:  # QtWebEngine 未導入・初期化失敗など
            self._cli_status.setText(
                self.tr("端末ビューを初期化できませんでした: {err}").format(err=exc)
            )
            return None
        self._cli_host_layout.addWidget(view)
        self._terminal_view = view
        return view

    def _default_terminal_factory(self) -> QWidget:
        # QtWebEngine の読み込みを CLI タブ利用時まで遅延させる。
        from .widgets.xterm_terminal_view import XtermTerminalView

        return XtermTerminalView(self._cli_host)

    def _on_session_finished(self, _code: int) -> None:
        self._update_cli_status()

    def _session_is_running(self) -> bool:
        session = self._session
        return session is not None and bool(session.is_running())

    def _update_cli_status(self) -> None:
        running = self._session_is_running()
        if running:
            self._cli_status.setText(
                self.tr(
                    "Copilot CLI 対話セッション実行中 / 作業ディレクトリ: {repo}"
                ).format(repo=self._repo_root)
            )
        else:
            self._cli_status.setText(
                self.tr(
                    "Copilot CLI 対話セッションは停止中です。"
                    "[セッション開始] で起動します（作業ディレクトリ: {repo}）。"
                ).format(repo=self._repo_root)
            )
        self._cli_start_btn.setEnabled(not running)
        self._cli_stop_btn.setEnabled(running)

    # ------------------------------------------------------------------
    # 実行ジョブタブ
    # ------------------------------------------------------------------

    def refresh_job_targets(self) -> None:
        """WorkbenchPage から宛先一覧を取り直す（選択は可能な限り維持）。"""
        previous = self.current_target()
        targets: List[JobTarget] = []
        page = self._workbench_page
        if page is not None:
            try:
                targets = list(page.job_targets())
            except (AttributeError, RuntimeError, TypeError):
                targets = []
        self._targets = targets

        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        for target in targets:
            self._target_combo.addItem(target.display_name())
        index = 0
        if previous is not None:
            for i, target in enumerate(targets):
                if (
                    target.instance_id == previous.instance_id
                    and target.step_id == previous.step_id
                ):
                    index = i
                    break
        self._target_combo.setCurrentIndex(index if targets else -1)
        self._target_combo.blockSignals(False)
        self._on_target_changed()

    def target_labels(self) -> List[str]:
        return [
            self._target_combo.itemText(i) for i in range(self._target_combo.count())
        ]

    def current_target(self) -> Optional[JobTarget]:
        index = self._target_combo.currentIndex()
        if 0 <= index < len(self._targets):
            return self._targets[index]
        return None

    def select_action(self, label: str) -> None:
        self._input_box.select_action(label)

    def job_log_text(self) -> str:
        return self._transcript.plain_text()

    def on_job_log_line(self, instance_id: str, step_id: str, line: str) -> None:
        """FR-GUI-13: 選択中の宛先に一致するログ行だけを追記する。"""
        target = self.current_target()
        if target is None or instance_id != target.instance_id:
            return
        if target.step_id and step_id != target.step_id:
            # 帰属が確定しない行は推測で表示しない。
            return
        self._transcript.append_log(line)

    def send_job_message(self, text: str) -> bool:
        """選択中の実行ジョブへ対話要求を書き出す。成功したら True。"""
        text = (text or "").strip()
        if not text:
            return False
        if len(text.encode("utf-8")) > _MAX_INPUT_BYTES:
            self._append_note(
                self.tr("入力が長すぎます（上限 {n} バイト）。").format(
                    n=_MAX_INPUT_BYTES
                )
            )
            return False
        target = self.current_target()
        if target is None or not target.is_sendable():
            self._append_note(
                self.tr(
                    "この宛先へは送信できません。実行中のステップと対話チャネルが必要です。"
                )
            )
            return False

        action = self._input_box.current_action()
        channel = str(target.channel_dir)
        request_id = uuid4().hex
        try:
            write_request(
                Path(channel),
                str(target.step_id),
                text,
                action=str(action),
                request_id=request_id,
            )
        except (OSError, ValueError) as exc:
            self._append_note(self.tr("送信に失敗しました: {err}").format(err=exc))
            return False

        self._pending_acks[request_id] = (channel, str(action))
        self._transcript.append_user(
            text,
            action_label=self._action_label(str(action)),
            request_id=request_id,
        )
        self._turn_index = self._transcript.user_turn_count() - 1
        self._refresh_turn_nav()
        self.refresh_pending_queue()
        return True

    def poll_acks(self) -> None:
        """Runner が書いた ACK を取り込み、受理/失敗を表示する。"""
        if not self._pending_acks:
            return
        channels = {channel for channel, _ in self._pending_acks.values()}
        for channel in channels:
            try:
                acks = list_acks(Path(channel))
            except OSError:
                continue
            for ack in acks:
                request_id = str(ack.get("request_id") or "")
                pending = self._pending_acks.pop(request_id, None)
                if pending is None:
                    continue
                status = str(ack.get("status"))
                detail = str(ack.get("detail") or "")
                if not self._transcript.update_ack(request_id, status, detail):
                    # 会話をクリア済みでも ACK を失わない。
                    self._append_note(
                        self.tr("→ {action}: {status}").format(
                            action=self._action_label(pending[1]),
                            status=self._format_ack_status(ack),
                        )
                    )

    @staticmethod
    def _format_ack_status(ack: Dict[str, Any]) -> str:
        status = str(ack.get("status"))
        detail = ack.get("detail") or ""
        return f"{status} ({detail})" if detail else status

    def open_selected_job_result(self) -> bool:
        """FR-GUI-14: 選択ジョブの成果物パスを添えて新しい CLI セッションを開く。"""
        target = self.current_target()
        if target is None:
            return False
        page = self._workbench_page
        work_root = None
        artifacts: Tuple[Path, ...] = ()
        if page is not None:
            try:
                work_root = page.session_work_root()
            except (AttributeError, RuntimeError):
                work_root = None
            try:
                artifacts = tuple(Path(p) for p in (page.session_artifacts() or ()))
            except (AttributeError, RuntimeError, TypeError):
                artifacts = ()
        if not work_root:
            self._append_note(self.tr("参照できる実行ディレクトリがまだありません。"))
            return False

        if self._session_is_running():
            if not self._confirm_session_restart():
                return False
            self.stop_cli_session()

        context = build_job_result_context(
            target,
            work_root=Path(work_root),
            returncode=target.returncode,
            artifacts=artifacts,
        )
        self._tabs.setCurrentIndex(0)
        return self.start_cli_session(context.prompt)

    def _confirm_session_restart(self) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Copilot セッションの再起動"),
            self.tr(
                "実行中の Copilot 対話セッションを終了して、"
                "ジョブ結果を新しいセッションで開きますか?"
            ),
        )
        return answer == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # 送信待ちキュー（FR-GUI-12 の未消費要求操作）
    # ------------------------------------------------------------------

    def refresh_pending_queue(self) -> None:
        """選択中の宛先の未消費要求を処理順で並べ直す。"""
        requests = self._pending_requests()
        previous = self._pending_list.currentRow()
        self._pending_list.clear()
        for request in requests:
            self._pending_list.addItem(request.text)
        if requests:
            self._pending_list.setCurrentRow(min(max(previous, 0), len(requests) - 1))
        self._pending_bar.setVisible(bool(requests))
        self._update_status_footer()

    def pending_request_labels(self) -> List[str]:
        return [
            self._pending_list.item(i).text() for i in range(self._pending_list.count())
        ]

    def select_pending_row(self, row: int) -> None:
        self._pending_list.setCurrentRow(row)

    def cancel_selected_pending(self) -> bool:
        """選択中の未消費要求を取り消す。成功したら True。"""
        target = self.current_target()
        requests = self._pending_requests()
        row = self._pending_list.currentRow()
        if target is None or not target.channel_dir or not 0 <= row < len(requests):
            return False
        try:
            cancelled = cancel_request(Path(target.channel_dir), requests[row].request_id)
        except OSError:
            cancelled = False
        self.refresh_pending_queue()
        return cancelled

    def move_selected_pending(self, delta: int) -> bool:
        """選択中の未消費要求の処理順を ``delta`` だけ入れ替える。"""
        target = self.current_target()
        requests = self._pending_requests()
        row = self._pending_list.currentRow()
        if target is None or not target.channel_dir or not target.step_id:
            return False
        if not 0 <= row < len(requests):
            return False
        new_row = row + delta
        if not 0 <= new_row < len(requests):
            return False

        request_ids = [request.request_id for request in requests]
        request_ids.insert(new_row, request_ids.pop(row))
        try:
            reordered = reorder_pending(
                Path(target.channel_dir), str(target.step_id), request_ids
            )
        except OSError:
            reordered = False
        self.refresh_pending_queue()
        if reordered:
            self._pending_list.setCurrentRow(new_row)
        return reordered

    def _pending_requests(self) -> List[JobInteractionRequest]:
        target = self.current_target()
        if target is None or not target.channel_dir or not target.step_id:
            return []
        try:
            return list(
                list_pending_requests(Path(target.channel_dir), str(target.step_id))
            )
        except OSError:
            return []

    # ------------------------------------------------------------------
    # 補助操作と状態行
    # ------------------------------------------------------------------

    def overflow_menu_labels(self) -> List[str]:
        return [action.text() for action in self._overflow_menu.actions()]

    def clear_transcript(self) -> None:
        """表示だけをリセットする（送信済み要求と IPC チャネルは触らない）。"""
        self._transcript.clear()
        self._turn_index = -1
        self._refresh_turn_nav()

    def copy_transcript(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._transcript.plain_text())

    def status_footer_text(self) -> str:
        return self._status_footer.text()

    # ------------------------------------------------------------------
    # ターンナビゲーション
    # ------------------------------------------------------------------

    def turn_label_text(self) -> str:
        return self._turn_label.text()

    def turn_position_text(self) -> str:
        return self._turn_position.text()

    def goto_previous_turn(self) -> bool:
        return self._goto_turn(self._turn_index - 1)

    def goto_next_turn(self) -> bool:
        return self._goto_turn(self._turn_index + 1)

    def _refresh_turn_nav(self) -> None:
        """送信メッセージの件数と現在位置を表示へ反映する。"""
        count = self._transcript.user_turn_count()
        if count == 0:
            self._turn_index = -1
            self._turn_label.clear()
            self._turn_position.clear()
            self._turn_nav_bar.hide()
            return
        self._turn_index = min(max(self._turn_index, 0), count - 1)
        self._turn_label.setText(
            _elide_turn_text(self._transcript.user_turn_text(self._turn_index))
        )
        self._turn_position.setText(f"{self._turn_index + 1}/{count}")
        self._turn_prev_btn.setEnabled(self._turn_index > 0)
        self._turn_next_btn.setEnabled(self._turn_index < count - 1)
        self._turn_nav_bar.show()

    def _goto_turn(self, index: int) -> bool:
        if not self._transcript.scroll_to_user_turn(index):
            return False
        # スクロールで発火する連動更新より後に確定させる（移動先と表示を一致させる）。
        self._turn_index = index
        self._refresh_turn_nav()
        return True

    def _on_transcript_scrolled(self) -> None:
        index = self._transcript.current_user_turn_index()
        if index >= 0:
            self._turn_index = index
        self._refresh_turn_nav()

    def _update_status_footer(self) -> None:
        target = self.current_target()
        if target is None:
            self._status_footer.setText(self.tr("対象ジョブが選択されていません。"))
            return
        channel = (
            self.tr("対話チャネル: 利用できます")
            if target.channel_dir
            else self.tr("対話チャネル: 利用できません")
        )
        self._status_footer.setText(
            self.tr("状態: {status} / {channel} / 送信待ち: {count} 件").format(
                status=target.status,
                channel=channel,
                count=self._pending_list.count(),
            )
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_job_send_clicked(self) -> None:
        if self.send_job_message(self._input_box.compose_text()):
            self._input_box.clear()

    def _on_attach_requested(self) -> None:
        """FR-GUI-18: 選んだファイルのパスだけを添付する（本文は読まない）。"""
        paths, _filter = QFileDialog.getOpenFileNames(
            self, self.tr("コンテキストを添付"), str(self._repo_root)
        )
        for path in paths:
            self._input_box.add_attachment(path)

    def _on_target_changed(self) -> None:
        target = self.current_target()
        lines: List[str] = []
        page = self._workbench_page
        if target is not None and page is not None:
            try:
                lines = list(page.job_log_snapshot(target))
            except (AttributeError, RuntimeError, TypeError):
                lines = []
        self._transcript.set_log_snapshot(lines)
        self._turn_index = -1
        self._refresh_turn_nav()
        self._update_job_controls()
        self.refresh_pending_queue()

    def _update_job_controls(self) -> None:
        target = self.current_target()
        self._input_box.set_sendable(target is not None and target.is_sendable())
        self._open_result_action.setEnabled(target is not None)
        self._update_status_footer()

    def _action_label(self, action: str) -> str:
        return self._input_box.action_label(action)

    def _append_note(self, text: str) -> None:
        self._transcript.append_notice(text)
