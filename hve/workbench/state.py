"""state.py — Workbench 表示状態モデル。

UI 描画から完全に独立した data-only モデル。Layout/Controller 層は
本モジュールの状態を読み取って描画する。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from .buffer import RingBuffer
from .task_tree import TaskNode, TaskTree


StepStatus = Literal["pending", "running", "done", "failed", "skipped"]
ActionLevel = Literal["INFO", "WARN", "ERROR"]
StepKind = Literal["step", "fanout_child", "subagent"]

_VALID_STATUS: frozenset = frozenset(
    {"pending", "running", "done", "failed", "skipped"}
)


# Body コンテンツ行数の許容範囲（要件: 10〜20 行）。
BODY_WINDOW_MIN = 10
BODY_WINDOW_MAX = 20
BODY_WINDOW_DEFAULT = 20

# UserActions ペインの仕様定数。
USER_ACTIONS_VISIBLE = 5
USER_ACTIONS_CAPACITY = 50

# 自動 all_done フォールバック条件で使う閾値（秒）
_AUTO_ALL_DONE_MIN_ELAPSED = 3.0
_AUTO_ALL_DONE_QUIET_PERIOD = 1.0


@dataclass
class StepView:
    """Header#2 / TaskTree に表示する 1 ステップの状態。"""

    id: str
    title: str
    status: StepStatus = "pending"
    current_activity: str = ""
    started_at: Optional[float] = None  # time.monotonic()
    parent_id: Optional[str] = None
    kind: StepKind = "step"


@dataclass
class UserAction:
    """UserActions ペインの 1 レコード。"""

    timestamp: str  # "HH:MM:SS"
    level: ActionLevel
    message: str
    step_id: Optional[str] = None
    category: Optional[str] = None  # 表示優先: category > level


def clamp_body_window(value: int) -> int:
    if value < BODY_WINDOW_MIN:
        return BODY_WINDOW_MIN
    if value > BODY_WINDOW_MAX:
        return BODY_WINDOW_MAX
    return value


@dataclass
class WorkbenchState:
    """Workbench 全体の表示状態。"""

    workflow_id: str
    run_id: str
    model: str
    workflow_name: str = ""
    steps: List[StepView] = field(default_factory=list)
    body: RingBuffer = field(default_factory=lambda: RingBuffer(10000))
    body_window: int = BODY_WINDOW_DEFAULT
    scroll_offset: int = 0
    context_current: int = 0
    context_limit: int = 0
    context_msgs: int = 0
    current_running_step_id: Optional[str] = None

    # --- UserActions ---
    user_actions: List[UserAction] = field(default_factory=list)
    user_actions_scroll: int = 0

    # --- Command Input ---
    cmd_mode: bool = False
    cmd_buffer: str = ""

    # --- 完了 / 終了管理 ---
    workflow_started_at: float = field(default_factory=time.monotonic)
    workflow_started_at_wall: float = field(default_factory=time.time)
    all_done: bool = False
    exit_requested: bool = False
    report_saved: bool = False

    # --- TaskTree ---
    task_tree: TaskTree = field(default_factory=TaskTree)

    # 自動 all_done フォールバック用
    _last_status_change_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.body_window = clamp_body_window(self.body_window)
        # task_tree の root を初期化（workflow_name 未設定なら workflow_id を使用）
        if self.task_tree.root is None:
            title = self.workflow_name or self.workflow_id or "workflow"
            self.task_tree.add_root(
                TaskNode(
                    id="__workflow__",
                    title=title,
                    status="running",
                    kind="workflow",
                    started_at_monotonic=self.workflow_started_at,
                )
            )

    # -- 状態更新 API --------------------------------------------------

    def set_step_status(self, step_id: str, status: StepStatus) -> None:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        for s in self.steps:
            if s.id == step_id:
                s.status = status
                if status == "running" and s.started_at is None:
                    s.started_at = time.monotonic()
                break
        else:
            return

        if status == "running":
            self.current_running_step_id = step_id
        elif self.current_running_step_id == step_id:
            self.current_running_step_id = None

        # TaskTree にもステップノードを登録/更新
        node = self.task_tree.get(step_id)
        if node is None:
            self.task_tree.add_child(
                "__workflow__",
                TaskNode(
                    id=step_id,
                    title=self._step_title(step_id),
                    status=status,
                    kind="step",
                    started_at_monotonic=time.monotonic() if status == "running" else None,
                    finished_at_monotonic=(
                        time.monotonic() if status in ("done", "failed", "skipped") else None
                    ),
                ),
            )
        else:
            updates = {"status": status}
            if status == "running" and node.started_at_monotonic is None:
                updates["started_at_monotonic"] = time.monotonic()
            if status in ("done", "failed", "skipped") and node.finished_at_monotonic is None:
                updates["finished_at_monotonic"] = time.monotonic()
            self.task_tree.update(step_id, **updates)

        self._last_status_change_at = time.monotonic()

    def _step_title(self, step_id: str) -> str:
        for s in self.steps:
            if s.id == step_id:
                return f"{s.id}.{s.title}"
        return step_id

    def append_body(self, line: str) -> None:
        self.body.append(line)

    def set_context(self, current: int, limit: int, msgs: int) -> None:
        self.context_current = current
        self.context_limit = limit
        self.context_msgs = msgs

    def set_model(self, name: str) -> None:
        self.model = name

    def expand_steps(self, parent_id: str, child_keys: List[str]) -> None:
        for s in self.steps:
            if s.id == parent_id:
                setattr(s, "_fanout_total", len(child_keys))
                setattr(s, "_fanout_done", 0)
                setattr(s, "_fanout_keys", list(child_keys))
                break

    def increment_fanout_done(self, parent_id: str) -> None:
        for s in self.steps:
            if s.id == parent_id and hasattr(s, "_fanout_total"):
                done = getattr(s, "_fanout_done", 0) + 1
                setattr(s, "_fanout_done", done)
                if done >= getattr(s, "_fanout_total", 0):
                    s.status = "done"
                break

    def mark_retry(self, step_id: str, retry_count: int) -> None:
        for s in self.steps:
            if s.id == step_id:
                if retry_count and retry_count > 0:
                    setattr(s, "_retry_count", int(retry_count))
                else:
                    if hasattr(s, "_retry_count"):
                        try:
                            delattr(s, "_retry_count")
                        except AttributeError:
                            pass
                break

    # ------------------------------------------------------------------
    # current_activity / サブタスク
    # ------------------------------------------------------------------

    def set_current_activity(self, step_id: str, activity: str) -> None:
        for s in self.steps:
            if s.id == step_id:
                s.current_activity = activity
                break
        node = self.task_tree.get(step_id)
        if node is not None:
            self.task_tree.update(step_id, current_activity=activity)

    def register_subtask(
        self,
        parent_id: str,
        child_id: str,
        title: str,
        kind: StepKind = "subagent",
    ) -> None:
        # 既に登録済みなら no-op
        if self.task_tree.get(child_id) is not None:
            return
        # 親が未登録なら workflow ルートにぶら下げる
        parent = self.task_tree.get(parent_id) or self.task_tree.root
        parent_actual = parent.id if parent is not None else "__workflow__"
        self.task_tree.add_child(
            parent_actual,
            TaskNode(
                id=child_id,
                title=title,
                status="running",
                kind=kind,
                started_at_monotonic=time.monotonic(),
            ),
        )

    def update_subtask_status(
        self,
        child_id: str,
        status: StepStatus,
        activity: Optional[str] = None,
    ) -> None:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        updates: dict = {"status": status}
        if activity is not None:
            updates["current_activity"] = activity
        if status in ("done", "failed", "skipped"):
            node = self.task_tree.get(child_id)
            if node is not None and node.finished_at_monotonic is None:
                updates["finished_at_monotonic"] = time.monotonic()
        self.task_tree.update(child_id, **updates)
        self._last_status_change_at = time.monotonic()

    # ------------------------------------------------------------------
    # 完了 / 終了
    # ------------------------------------------------------------------

    def mark_all_done(self) -> bool:
        """すべて完了扱いにする（冪等: 2 回目以降は False を返す）。"""
        if self.all_done:
            return False
        self.all_done = True
        now = time.monotonic()
        # workflow ルートを done に + 完了時刻を凍結
        root = self.task_tree.root
        if root is not None:
            root_updates: dict = {}
            if root.status == "running":
                root_updates["status"] = "done"
            if root.finished_at_monotonic is None:
                root_updates["finished_at_monotonic"] = now
            if root_updates:
                self.task_tree.update(root.id, **root_updates)
        # 残存する running サブタスクを done に集約 + 完了時刻記録
        for node in list(self.task_tree.iter_flatten()):
            if node.status == "running":
                updates: dict = {"status": "done"}
                if node.finished_at_monotonic is None:
                    updates["finished_at_monotonic"] = now
                self.task_tree.update(node.id, **updates)
        return True

    def request_exit(self) -> None:
        self.exit_requested = True

    def check_auto_all_done(self, now: Optional[float] = None) -> bool:
        """`steps` が空でなく、全 done/failed/skipped、3 秒経過、1 秒静止の 4 条件 AND。"""
        if self.all_done:
            return False
        if not self.steps:
            return False
        if not all(s.status in ("done", "failed", "skipped") for s in self.steps):
            return False
        cur = now if now is not None else time.monotonic()
        if (cur - self.workflow_started_at) < _AUTO_ALL_DONE_MIN_ELAPSED:
            return False
        if (cur - self._last_status_change_at) < _AUTO_ALL_DONE_QUIET_PERIOD:
            return False
        return True

    # ------------------------------------------------------------------
    # UserActions API
    # ------------------------------------------------------------------

    def append_user_action(
        self,
        level: ActionLevel,
        message: str,
        *,
        step_id: Optional[str] = None,
        category: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if timestamp is None:
            timestamp = time.strftime("%H:%M:%S")
        self.user_actions.append(
            UserAction(
                timestamp=timestamp,
                level=level,
                message=str(message),
                step_id=step_id,
                category=category,
            )
        )
        overflow = len(self.user_actions) - USER_ACTIONS_CAPACITY
        if overflow > 0:
            del self.user_actions[:overflow]
        self.user_actions_scroll = 0

    def user_actions_max_offset(self) -> int:
        return max(0, len(self.user_actions) - USER_ACTIONS_VISIBLE)

    def user_actions_view(self) -> List[UserAction]:
        total = len(self.user_actions)
        if total == 0:
            return []
        offset = max(0, min(self.user_actions_scroll, self.user_actions_max_offset()))
        end = total - offset
        start = max(0, end - USER_ACTIONS_VISIBLE)
        return list(self.user_actions[start:end])

    # ------------------------------------------------------------------
    # Command Input API
    # ------------------------------------------------------------------

    def cmd_enter(self) -> None:
        self.cmd_mode = True
        self.cmd_buffer = ""

    def cmd_cancel(self) -> None:
        self.cmd_mode = False
        self.cmd_buffer = ""

    def cmd_append(self, ch: str) -> None:
        if not self.cmd_mode:
            return
        if not ch:
            return
        if len(ch) == 1 and ord(ch) < 0x20:
            return
        self.cmd_buffer += ch

    def cmd_backspace(self) -> None:
        if not self.cmd_mode:
            return
        if self.cmd_buffer:
            self.cmd_buffer = self.cmd_buffer[:-1]

    def cmd_submit(self) -> str:
        text = self.cmd_buffer
        self.cmd_mode = False
        self.cmd_buffer = ""
        return text
