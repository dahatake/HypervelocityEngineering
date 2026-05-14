"""controller.py — Workbench の Rich Live 駆動コントローラ。

WorkbenchState を保持し、Live で Layout を継続描画する。
screen=True 取得失敗時は self._active=False で plain 出力に降格する。

完了ライフサイクル:
  1. mark_all_done() を呼び出すと、`/exit` 待機モードに入る（state.all_done=True）。
  2. mark_all_done() は useractions レポートも保存する（冪等）。
  3. wait_for_exit(timeout) で `/exit` 入力を待機。
  4. __exit__ 内では request_exit() 受理後に KeyReader を停止する。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from rich.console import Console as RichConsole
from rich.live import Live

from .layout import make_layout, update_layout
from .state import WorkbenchState

if TYPE_CHECKING:
    pass


class WorkbenchController:
    def __init__(
        self,
        state: WorkbenchState,
        *,
        refresh_per_second: int = 10,
        flush_on_exit: bool = True,
    ) -> None:
        self.state = state
        self._refresh = refresh_per_second
        self._flush_on_exit = flush_on_exit
        self._lock = threading.RLock()
        # state.workflow_started_at* は state.__post_init__ で初期化済み

        self._layout = make_layout(state.body_window)
        update_layout(self._layout, self.state)

        self._live: Optional[Live] = None
        self._rich_console: Optional[RichConsole] = None
        self._active: bool = False
        self._fallback_lines: List[str] = []
        self._key_reader: Any = None
        self._report_path: Optional[Path] = None
        # 1 Hz 自動カウントアップ tick。
        self._tick_thread: Optional[threading.Thread] = None
        self._tick_stop: threading.Event = threading.Event()
        self._tick_interval: float = 1.0

    def __enter__(self) -> "WorkbenchController":
        try:
            self._rich_console = RichConsole()
            self._live = Live(
                self._layout,
                console=self._rich_console,
                refresh_per_second=self._refresh,
                screen=True,
                redirect_stdout=True,
                redirect_stderr=True,
                transient=False,
            )
            self._live.__enter__()
            self._active = True
        except Exception:
            self._active = False
            self._live = None
        if self._active:
            try:
                from hve.workbench.keyreader import KeyReader
                self._key_reader = KeyReader(self)
                self._key_reader.start()
            except Exception:
                self._key_reader = None
            # 1 Hz tick スレッド起動（TaskTree elapsed の自動カウントアップ用）
            try:
                self._tick_stop.clear()
                self._tick_thread = threading.Thread(
                    target=self._tick_loop, name="workbench-tick", daemon=True
                )
                self._tick_thread.start()
            except Exception:
                self._tick_thread = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # tick スレッドを先に停止（_refresh_layout を呼ばなくする）
        self._tick_stop.set()
        if self._tick_thread is not None:
            try:
                self._tick_thread.join(timeout=2.0)
            except Exception:
                pass
            self._tick_thread = None
        # KeyReader 停止は exit_requested 受理後（または __exit__ 到達時）に行う
        if self._key_reader is not None:
            try:
                self._key_reader.stop()
            except Exception:
                pass
            self._key_reader = None
        self.stop()

    # ------------------------------------------------------------------
    # 状態更新 public API
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._active

    @property
    def report_path(self) -> Optional[Path]:
        return self._report_path

    def append_body(self, line: str) -> None:
        with self._lock:
            self.state.append_body(line)
            if not self._active:
                self._fallback_lines.append(line)
                return
            self._refresh_layout()

    def set_step_status(self, step_id: str, status: str) -> None:
        with self._lock:
            self.state.set_step_status(step_id, status)  # type: ignore[arg-type]
            self._refresh_layout()

    def set_context(self, current: int, limit: int, msgs: int) -> None:
        with self._lock:
            self.state.set_context(current, limit, msgs)
            self._refresh_layout()

    def set_model(self, name: str) -> None:
        with self._lock:
            self.state.set_model(name)
            self._refresh_layout()

    def expand_steps(self, parent_id: str, child_keys: List[str]) -> None:
        with self._lock:
            self.state.expand_steps(parent_id, child_keys)
            self._refresh_layout()

    def increment_fanout_done(self, parent_id: str) -> None:
        with self._lock:
            self.state.increment_fanout_done(parent_id)
            self._refresh_layout()

    def mark_retry(self, step_id: str, retry_count: int) -> None:
        with self._lock:
            self.state.mark_retry(step_id, retry_count)
            self._refresh_layout()

    # ------------------------------------------------------------------
    # current_activity / サブタスク
    # ------------------------------------------------------------------

    def set_current_activity(self, step_id: str, activity: str) -> None:
        with self._lock:
            self.state.set_current_activity(step_id, activity)
            self._refresh_layout()

    def register_subtask(
        self,
        parent_id: str,
        child_id: str,
        title: str,
        kind: str = "subagent",
    ) -> None:
        with self._lock:
            self.state.register_subtask(parent_id, child_id, title, kind)  # type: ignore[arg-type]
            self._refresh_layout()

    def update_subtask(
        self,
        child_id: str,
        status: str,
        activity: Optional[str] = None,
    ) -> None:
        with self._lock:
            self.state.update_subtask_status(child_id, status, activity)  # type: ignore[arg-type]
            self._refresh_layout()

    # ------------------------------------------------------------------
    # スクロール
    # ------------------------------------------------------------------

    def scroll_up(self, n: int = 1) -> None:
        with self._lock:
            max_off = self.state.body.max_offset(self.state.body_window)
            self.state.scroll_offset = min(self.state.scroll_offset + n, max_off)
            self._refresh_layout()

    def scroll_down(self, n: int = 1) -> None:
        with self._lock:
            self.state.scroll_offset = max(self.state.scroll_offset - n, 0)
            self._refresh_layout()

    def page_up(self) -> None:
        self.scroll_up(self.state.body_window)

    def page_down(self) -> None:
        self.scroll_down(self.state.body_window)

    def home(self) -> None:
        with self._lock:
            self.state.scroll_offset = self.state.body.max_offset(self.state.body_window)
            self._refresh_layout()

    def end(self) -> None:
        with self._lock:
            self.state.scroll_offset = 0
            self._refresh_layout()

    # ------------------------------------------------------------------
    # UserActions
    # ------------------------------------------------------------------

    def append_user_action(
        self,
        level: str,
        message: str,
        *,
        step_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        with self._lock:
            self.state.append_user_action(
                level, message, step_id=step_id, category=category  # type: ignore[arg-type]
            )
            self._refresh_layout()

    def scroll_actions_up(self, n: int = 1) -> None:
        with self._lock:
            max_off = self.state.user_actions_max_offset()
            self.state.user_actions_scroll = min(self.state.user_actions_scroll + n, max_off)
            self._refresh_layout()

    def scroll_actions_down(self, n: int = 1) -> None:
        with self._lock:
            self.state.user_actions_scroll = max(self.state.user_actions_scroll - n, 0)
            self._refresh_layout()

    # ------------------------------------------------------------------
    # Command Input
    # ------------------------------------------------------------------

    def cmd_enter(self) -> None:
        with self._lock:
            self.state.cmd_enter()
            self._refresh_layout()

    def cmd_cancel(self) -> None:
        with self._lock:
            self.state.cmd_cancel()
            self._refresh_layout()

    def cmd_append(self, ch: str) -> None:
        with self._lock:
            self.state.cmd_append(ch)
            self._refresh_layout()

    def cmd_backspace(self) -> None:
        with self._lock:
            self.state.cmd_backspace()
            self._refresh_layout()

    def cmd_submit(self) -> str:
        """バッファを取り出してコマンドハンドラへディスパッチ。

        既知コマンド: `/help`, `/exit`（完了後のみ）
        """
        with self._lock:
            text = self.state.cmd_submit().strip()
            self._refresh_layout()
        if not text:
            return ""
        self._dispatch_command(text)
        return text

    def _dispatch_command(self, text: str) -> None:
        cmd = text.split()[0] if text else ""
        if cmd == "/help":
            self._cmd_help()
        elif cmd == "/exit":
            self._cmd_exit()
        else:
            self.append_user_action("WARN", f"unknown command: {text}  （/help で一覧）")

    def _cmd_help(self) -> None:
        if self.state.all_done:
            msg = (
                "commands: /exit (終了), /help  ｜ "
                "keys: ↑↓ body, [ ] actions, g/G top/bottom"
            )
        else:
            msg = (
                "commands: /help  ｜ "
                "keys: ↑↓ body, [ ] actions, g/G top/bottom, q detach  ｜ "
                "(全タスク完了後に /exit で終了)"
            )
        self.append_user_action("INFO", msg)

    def _cmd_exit(self) -> None:
        if not self.state.all_done:
            self.append_user_action(
                "WARN",
                "/exit: タスク実行中は終了できません（全タスク完了後に再度入力してください）",
            )
            return
        with self._lock:
            self.state.request_exit()
            self._refresh_layout()
        self.append_user_action("INFO", "/exit: 終了します")

    # ------------------------------------------------------------------
    # 完了 / 終了管理
    # ------------------------------------------------------------------

    def mark_all_done(self) -> None:
        """全タスク完了を宣言し、useractions レポートを保存する（冪等）。"""
        with self._lock:
            transitioned = self.state.mark_all_done()
            if not transitioned:
                self._refresh_layout()
                return
            # INFO はレポート保存より先に append し、保存内容に含める
            self.state.append_user_action(
                "INFO",  # type: ignore[arg-type]
                "すべてのタスクが完了しました。/exit で終了してください。",
            )
            self._refresh_layout()
        # state ロック外でレポート保存（I/O のため）
        self._save_report_if_needed()

    def request_exit(self) -> None:
        with self._lock:
            self.state.request_exit()
            self._refresh_layout()

    def wait_for_exit(self, timeout: Optional[float] = None) -> bool:
        """`state.exit_requested` を待機する。

        timeout=None / 0 は **無制限** 待機。負値は ValueError。
        Workbench が非アクティブ（Rich Live 取得失敗等）の場合は
        `/exit` 入力経路が存在しないため、即座に True を返す（ハング回避）。
        """
        if timeout is not None and timeout < 0:
            raise ValueError(f"wait_for_exit: timeout must be >= 0 or None, got {timeout!r}")
        if not self._active:
            # KeyReader が無いため /exit を受理する手段が無い。即時 return。
            return True
        infinite = timeout is None or timeout == 0
        deadline = None if infinite else (time.monotonic() + timeout)
        while True:
            if self.state.exit_requested:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def _save_report_if_needed(self) -> None:
        if self.state.report_saved:
            return
        try:
            from .report import save_useractions_report
            path = save_useractions_report(
                self.state,
                workflow_id=self.state.workflow_id or "unknown",
                run_id=self.state.run_id or "unknown",
                started_at_wall=self.state.workflow_started_at_wall,
            )
            # save_useractions_report は冪等 no-op 時に Path("") を返すが、
            # Path("") は Path(".") と等価で str() は "." になるため、
            # ファイル名が無い（parent + name が空）ことで識別する。
            if path.name:
                self._report_path = path
        except Exception as exc:  # pragma: no cover - I/O 障害時のみ
            try:
                self.append_user_action(
                    "ERROR",
                    f"useractions レポート保存失敗: {exc}",
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def pause(self) -> None:
        if self._key_reader is not None:
            try:
                self._key_reader.stop()
            except Exception:
                pass
        if self._active and self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._active = False

    def resume(self) -> None:
        if not self._active and self._live is not None:
            try:
                self._live.start()
                self._active = True
            except Exception:
                self._active = False
        if self._active and self._key_reader is not None:
            try:
                self._key_reader.start()
            except Exception:
                pass

    def stop(self) -> None:
        # 全 step が完了していて未保存なら、ここでフォールバック保存する
        try:
            if not self.state.report_saved:
                # all_done 明示 or 全 step 終端 のいずれかでフォールバック保存
                all_terminal = bool(self.state.steps) and all(
                    s.status in ("done", "failed", "skipped") for s in self.state.steps
                )
                # 例外早期 finally などで steps 未登録だが UserAction が残るケースも救済
                has_actions = bool(self.state.user_actions)
                if self.state.all_done or all_terminal or has_actions:
                    self._save_report_if_needed()
        except Exception:
            pass

        if self._live is not None and self._active:
            try:
                self._live.__exit__(None, None, None)
            except Exception:
                pass
        self._active = False
        self._live = None

        if self._flush_on_exit:
            import os as _os
            import sys
            try:
                _cap = int(_os.environ.get("HVE_WORKBENCH_FLUSH_MAX_LINES", "10000"))
            except ValueError:
                _cap = 10000
            if _cap < 0:
                _cap = 0
            total = len(self.state.body)
            window = total if _cap == 0 else min(total, _cap)
            if window < total:
                print(
                    f"[hve.workbench] (body の末尾 {window}/{total} 行のみ出力。"
                    f"HVE_WORKBENCH_FLUSH_MAX_LINES で上限変更可)",
                    file=sys.stdout,
                    flush=True,
                )
            for line in self.state.body.view(window=window, offset=0):
                if line:
                    print(line, file=sys.stdout, flush=True)
            for line in self._fallback_lines:
                print(line, file=sys.stdout, flush=True)
            self._fallback_lines.clear()
            if self._report_path is not None:
                try:
                    print(
                        f"[hve.workbench] useractions report: {self._report_path}",
                        file=sys.stdout,
                        flush=True,
                    )
                except Exception:
                    pass

    def _refresh_layout(self) -> None:
        if not self._active or self._live is None:
            return
        update_layout(self._layout, self.state)

    def _tick_loop(self) -> None:
        """1 Hz で layout を再描画し TaskTree elapsed をカウントアップさせる。

        all_done 後は各ノードの finished_at で凍結されるため再描画不要。
        例外は黙殺（tick そのものを起因とする崩壊を避ける）。
        """
        while not self._tick_stop.is_set():
            try:
                if self._active and not self.state.all_done:
                    with self._lock:
                        self._refresh_layout()
            except Exception:
                pass
            # wait はシグナルで即時解除可能
            if self._tick_stop.wait(self._tick_interval):
                break
