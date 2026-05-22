"""hve.gui.workbench_state — GUI向けのWorkbench状態管理。

CUI版 (hve.workbench.state) をGUI用に適応。
PySide6 Signal/Slot 対応のため、状態変更時に信号を emit する。
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from PySide6.QtCore import QObject, Signal

StepStatus = Literal["pending", "running", "done", "failed", "skipped"]
ActionLevel = Literal["INFO", "WARN", "ERROR"]
StepKind = Literal["step", "container", "fanout_child", "subagent"]


def format_log_prefix(
    workflow_id: str,
    step_id: Optional[str],
    step_title: Optional[str] = None,
) -> str:
    """ログ行に付与する ``[wf_id]-[step].`` 形式のプリフィックスを返す。

    - ``workflow_id`` 空文字時は ``[?]`` を出力
    - ``step_id`` 空・None 時は ``[main]``
    - ``step_title`` が与えられれば ``[step_id.step_title]``、無ければ ``[step_id]``

    末尾はスペース 1 文字を含むため、戻り値をそのまま ``prefix + line`` 連結できる。
    捏造防止のため、引数で受け取った値以外は構築しない。
    """
    wf = workflow_id or "?"
    if not step_id:
        step_part = "main"
    elif step_title:
        step_part = f"{step_id}.{step_title}"
    else:
        step_part = step_id
    return f"[{wf}]-[{step_part}] "

_VALID_STATUS: frozenset = frozenset(
    {"pending", "running", "done", "failed", "skipped"}
)

BODY_WINDOW_MIN = 10
BODY_WINDOW_MAX = 20
BODY_WINDOW_DEFAULT = 10

USER_ACTIONS_VISIBLE = 5
USER_ACTIONS_CAPACITY = 50


@dataclass
class StepView:
    """Header2 / TaskTree に表示する 1 ステップの状態。

    Phase 2 (Q7=B / Q10=a): ``children`` フィールドにより任意ネストの木構造を表現する。
    container Step は配下の通常 Step を ``children`` に保持し、Sub-agent / Fanout 子も
    親 Step の ``children`` として表現できる。深さに上限はない。
    """

    id: str
    title: str
    status: StepStatus = "pending"
    current_activity: str = ""
    started_at: Optional[float] = None  # time.monotonic()
    finished_at: Optional[float] = None
    parent_id: Optional[str] = None
    kind: StepKind = "step"
    children: List["StepView"] = field(default_factory=list)


@dataclass
class UserAction:
    """UserActions ペインの 1 レコード。"""

    timestamp: str  # "HH:MM:SS"
    level: ActionLevel
    message: str
    step_id: Optional[str] = None
    category: Optional[str] = None  # 表示優先: category > level


@dataclass
class SimpleRingBuffer:
    """簡易版 RingBuffer - ログ行を保持（GUIペイン用）。"""

    capacity: int = 10000
    lines: List[str] = field(default_factory=list)

    def append(self, line: str) -> None:
        """1 行追加。改行含む場合は分割。"""
        if "\n" in line:
            for part in line.split("\n"):
                self._append_single(part)
        else:
            self._append_single(line)

    def _append_single(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > self.capacity:
            self.lines.pop(0)

    def __len__(self) -> int:
        return len(self.lines)

    def view(self, window: int, offset: int = 0) -> List[str]:
        """末尾から offset 行戻った位置を最下行とする window 行を返す。"""
        if window < 0:
            window = 0
        if offset < 0:
            offset = 0

        total = len(self.lines)
        end_idx = total - offset
        start_idx = max(0, end_idx - window)

        view_lines = self.lines[start_idx:end_idx]
        # 不足分はパディング
        if len(view_lines) < window:
            view_lines = [""] * (window - len(view_lines)) + view_lines
        return view_lines

    def max_offset(self, window: int) -> int:
        """最大スクロール量を返す。"""
        return max(0, len(self.lines) - window)


@dataclass
class SimpleTaskNode:
    """簡易タスクツリーノード。"""

    id: str
    title: str
    status: StepStatus = "pending"
    kind: StepKind = "step"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    elapsed: float = 0.0
    current_activity: str = ""
    children: List[SimpleTaskNode] = field(default_factory=list)

    def elapsed_str(self, now: float = None) -> str:
        """経過時間を HH:MM:SS 形式で返す。"""
        if now is None:
            now = time.monotonic()
        if self.started_at is None:
            return "00:00:00"
        if self.finished_at is not None:
            elapsed = self.finished_at - self.started_at
        else:
            elapsed = now - self.started_at
        elapsed = max(0, elapsed)
        h = int(elapsed) // 3600
        m = (int(elapsed) % 3600) // 60
        s = int(elapsed) % 60
        return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class SimpleTaskTree:
    """簡易タスクツリー - CUI版の縮簡版。"""

    root: Optional[SimpleTaskNode] = None
    nodes: dict = field(default_factory=dict)  # id -> node

    def add_root(self, node: SimpleTaskNode) -> None:
        self.root = node
        self.nodes[node.id] = node

    def add_child(self, parent_id: str, child: SimpleTaskNode) -> None:
        parent = self.nodes.get(parent_id)
        if parent is None:
            if self.root is not None:
                parent = self.root
            else:
                return
        parent.children.append(child)
        self.nodes[child.id] = child

    def get(self, node_id: str) -> Optional[SimpleTaskNode]:
        return self.nodes.get(node_id)

    def update(self, node_id: str, **kwargs) -> None:
        node = self.get(node_id)
        if node is not None:
            for k, v in kwargs.items():
                if hasattr(node, k):
                    setattr(node, k, v)

    def total_nodes(self) -> int:
        return len(self.nodes)

    def flatten(self) -> List[SimpleTaskNode]:
        """DFS で全ノードを返す。"""
        result: List[SimpleTaskNode] = []

        def visit(node: SimpleTaskNode) -> None:
            result.append(node)
            for child in node.children:
                visit(child)

        if self.root is not None:
            visit(self.root)
        return result


@dataclass
class StepStatsSnapshot:
    """Step 完了時のスナップショット。捏造禁止のため未取得値は None。"""

    step_id: str
    step_title: str
    status: StepStatus
    model: str
    started_at: Optional[float]  # time.monotonic()
    finished_at: Optional[float]
    elapsed_sec: Optional[float]
    context_current: Optional[int]
    context_limit: Optional[int]
    tool_counts: Dict[str, int] = field(default_factory=dict)
    skill_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "step_title": self.step_title,
            "status": self.status,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": self.elapsed_sec,
            "context_current": self.context_current,
            "context_limit": self.context_limit,
            "tool_counts": dict(self.tool_counts),
            "skill_counts": dict(self.skill_counts),
        }


@dataclass
class WorkflowStatsSnapshot:
    """1 ワークフロー実行ぶんの統計スナップショット。"""

    workflow_id: str
    workflow_name: str
    run_id: str
    model: str
    started_at: float
    finished_at: Optional[float] = None
    elapsed_sec: Optional[float] = None
    context_current: Optional[int] = None
    context_limit: Optional[int] = None
    finalized: bool = False
    steps: List[StepStatsSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "run_id": self.run_id,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": self.elapsed_sec,
            "context_current": self.context_current,
            "context_limit": self.context_limit,
            "finalized": self.finalized,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class WorkflowInstance:
    """並列起動された 1 ワークフロー実行を表すインスタンス。

    Wave 1（gui-unified-workbench）で追加。既存単一 workflow 経路には影響しない。
    UI 側 (Wave 2 以降) がツリー＋ログタブで参照する。

    Attributes:
        instance_id: 一意キー。``{workflow_id}`` または並列時 ``{workflow_id}#{app_id}``。
        workflow_id: ワークフロー定義 ID。
        label: ツリー表示名（例 ``"Arch-Microservice (APP-01)"``）。
        app_id: 並列起動を区別する任意キー（``None`` 可）。
        status: ``pending`` / ``running`` / ``done`` / ``failed`` / ``skipped``。
        steps: ``OrderedDict[step_id, StepView]``。挿入順に表示する。
        log_buffer: ワークフロー横断ログ（全行保持・無制限）。
        step_log_buffers: ``step_id -> List[str]``。Step 配下ログ。
        returncode: 実行終了時の returncode（未終了は ``None``）。
        started_at / finished_at: ``time.monotonic()`` ベース。
    """

    instance_id: str
    workflow_id: str
    label: str
    app_id: Optional[str] = None
    status: StepStatus = "pending"
    steps: "OrderedDict[str, StepView]" = field(default_factory=OrderedDict)
    log_buffer: List[str] = field(default_factory=list)
    step_log_buffers: Dict[str, List[str]] = field(default_factory=dict)
    returncode: Optional[int] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


class WorkbenchStateSignals(QObject):
    """状態変更シグナル。"""

    step_status_changed = Signal(str, str)  # (step_id, status)
    user_action_added = Signal(str, str, str)  # (timestamp, level, message)
    context_updated = Signal(int, int, int)  # (current, limit, msgs)
    model_updated = Signal(str)  # model_name
    all_done = Signal()
    body_updated = Signal(str)  # log_line
    header_updated = Signal()  # workflow_id / workflow_name / run_id が更新された時
    tool_counts_updated = Signal(str, str)  # (step_id, tool_name)
    skill_counts_updated = Signal(str, str)  # (step_id, skill_name)
    stats_history_updated = Signal()  # stats_history への追加/更新時
    # 並列 Workflow 実行用（Wave 1 追加）。
    workflow_instance_changed = Signal(str)  # instance_id
    workflow_instance_log = Signal(str, str, str)  # (instance_id, step_id or "", line)


@dataclass
class WorkbenchState:
    """GUI向けのWorkbench状態管理。"""

    workflow_id: str
    run_id: str
    model: str
    workflow_name: str = ""
    steps: List[StepView] = field(default_factory=list)
    # 並列 Workflow 実行用インスタンス（Wave 1 追加）。
    # 既存単一 workflow 経路では空のまま使用される。
    workflows: "OrderedDict[str, WorkflowInstance]" = field(default_factory=OrderedDict)
    body: SimpleRingBuffer = field(default_factory=lambda: SimpleRingBuffer(10000))
    body_window: int = BODY_WINDOW_DEFAULT
    scroll_offset: int = 0
    context_current: int = 0
    context_limit: int = 0
    context_msgs: int = 0
    current_running_step_id: Optional[str] = None
    # Step 完了後も最後に running だった step の集計を表示し続けるための保持
    last_known_step_id: Optional[str] = None
    # step_id -> tool_name -> count
    tool_counts_by_step: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # step_id -> skill_name -> count
    skill_counts_by_step: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # SDK 由来の詳細トークン内訳（直近の session.usage_info から）
    context_system_tokens: Optional[int] = None
    context_tool_definitions_tokens: Optional[int] = None
    context_conversation_tokens: Optional[int] = None
    # assistant.usage の累積（Workflow 全体）
    assistant_input_tokens_total: int = 0
    assistant_output_tokens_total: int = 0
    assistant_reasoning_tokens_total: int = 0
    assistant_cache_read_total: int = 0
    assistant_cache_write_total: int = 0
    assistant_usage_count: int = 0  # assistant.usage 発火回数
    # 直近の inter_token_latency_ms（モデル応答品質の参考値）
    assistant_inter_token_latency_ms_last: Optional[float] = None
    # 課金カテゴリ別累積 token_count (token_type -> count)
    billing_token_totals: Dict[str, int] = field(default_factory=dict)
    # TTFT（time-to-first-token, ms）統計
    ttft_first_ms: Optional[float] = None
    ttft_last_ms: Optional[float] = None
    ttft_sum_ms: float = 0.0
    ttft_count: int = 0
    # コンパクション統計
    compaction_count: int = 0
    compaction_tokens_removed_total: int = 0
    # Permission リクエスト累積
    permission_count: int = 0

    # --- 料金 (Wave 3) ---
    # AI Credit 累計コスト。pricing が読み込まれていない / 計算不能な場合は None のまま (捏造禁止)
    cost_usd_total: Optional[float] = None
    cost_jpy_total: Optional[float] = None
    premium_requests_total: int = 0
    # 直近の calc_cost() 戻り値の method ("multiplier" / "token" / "unavailable")
    cost_method_last: str = ""
    # 直近で cost_usd=None になった理由 (UI 表示用)
    cost_unavailable_reason: str = ""
    # 料金表スナップショット (Optional[CopilotPricing] – 遅延 import のため型は object)
    pricing_snapshot: Optional[object] = None
    # 計算で使用する USD/JPY レート (Config から注入)
    pricing_usd_jpy_rate: Optional[float] = 150.0
    # 計算で使用する plan_id (空=自動推定)
    pricing_plan_id: str = ""

    # 実行履歴（Workflow 跨ぎ）
    stats_history: List["WorkflowStatsSnapshot"] = field(default_factory=list)
    # 永続化コールバック（T3で設定）: callable(workflow_snapshot) -> None
    _history_store: Optional[object] = None

    user_actions: List[UserAction] = field(default_factory=list)
    user_actions_scroll: int = 0

    task_tree: SimpleTaskTree = field(default_factory=SimpleTaskTree)
    task_tree_scroll: int = 0

    workflow_started_at: float = field(default_factory=time.monotonic)
    all_done: bool = False
    aborted: bool = False  # 致命的エラー検知で中止された場合 True
    exit_requested: bool = False

    _signals: WorkbenchStateSignals = field(default_factory=WorkbenchStateSignals)

    def __post_init__(self) -> None:
        if self.body_window < BODY_WINDOW_MIN:
            self.body_window = BODY_WINDOW_MIN
        if self.body_window > BODY_WINDOW_MAX:
            self.body_window = BODY_WINDOW_MAX

        # TaskTree の root を初期化
        if self.task_tree.root is None:
            title = self.workflow_name or self.workflow_id or "workflow"
            root = SimpleTaskNode(
                id="__workflow__",
                title=title,
                status="running",
                kind="workflow",
                started_at=self.workflow_started_at,
            )
            self.task_tree.add_root(root)

    def signals(self) -> WorkbenchStateSignals:
        """Signal emitter を取得。"""
        return self._signals

    def append_body(self, line: str) -> None:
        self.body.append(line)
        self._signals.body_updated.emit(line)

    def update_identity(
        self,
        *,
        workflow_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> bool:
        """workflow_id / workflow_name / run_id を更新し、変更時に
        ``header_updated`` シグナルを emit する。

        None を渡したフィールドは変更しない。実値が現在値と同じ場合も
        emit しない（不要な再描画を避ける）。TaskTree root の title が
        ダミー値 (``"unknown"`` / ``""`` / ``"workflow"``) のまま残って
        いる場合は、確定した workflow 名で再同期する。

        Returns:
            True なら header_updated を emit した（＝何か変わった）。
        """
        changed = False
        if workflow_id is not None and workflow_id != self.workflow_id:
            self.workflow_id = workflow_id
            changed = True
        if workflow_name is not None and workflow_name != self.workflow_name:
            self.workflow_name = workflow_name
            changed = True
        if run_id is not None and run_id != self.run_id:
            self.run_id = run_id
            changed = True

        if changed:
            root = self.task_tree.root
            if root is not None and root.title in ("unknown", "", "workflow"):
                desired = self.workflow_name or self.workflow_id
                if desired:
                    self.task_tree.update(root.id, title=desired)
            self._ensure_current_workflow_snapshot()
            self._signals.header_updated.emit()
        return changed

    def set_step_status(self, step_id: str, status: StepStatus) -> None:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")

        for s in self.steps:
            if s.id == step_id:
                s.status = status
                if status == "running" and s.started_at is None:
                    s.started_at = time.monotonic()
                break

        if status == "running":
            self.current_running_step_id = step_id
            self.last_known_step_id = step_id
        elif self.current_running_step_id == step_id:
            self.current_running_step_id = None

        # TaskTree 更新
        node = self.task_tree.get(step_id)
        if node is None:
            node = SimpleTaskNode(
                id=step_id,
                title=f"{step_id}",
                status=status,
                kind="step",
                started_at=time.monotonic() if status == "running" else None,
                finished_at=time.monotonic() if status in ("done", "failed", "skipped") else None,
            )
            self.task_tree.add_child("__workflow__", node)
        else:
            updates = {"status": status}
            if status == "running" and node.started_at is None:
                updates["started_at"] = time.monotonic()
            if status in ("done", "failed", "skipped") and node.finished_at is None:
                updates["finished_at"] = time.monotonic()
            self.task_tree.update(step_id, **updates)

        # 完了系遷移時に Step スナップショットを履歴に push
        if status in ("done", "failed", "skipped"):
            self._record_step_snapshot(step_id, status)

        self._signals.step_status_changed.emit(step_id, status)

    def add_user_action(
        self,
        timestamp: str,
        level: ActionLevel,
        message: str,
        step_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        action = UserAction(
            timestamp=timestamp,
            level=level,
            message=message,
            step_id=step_id,
            category=category,
        )
        self.user_actions.append(action)
        if len(self.user_actions) > USER_ACTIONS_CAPACITY:
            self.user_actions.pop(0)
        self._signals.user_action_added.emit(timestamp, level, message)

    def set_context(self, current: int, limit: int, msgs: int) -> None:
        self.context_current = current
        self.context_limit = limit
        self.context_msgs = msgs
        self._signals.context_updated.emit(current, limit, msgs)

    def record_tool_call(self, step_id: Optional[str], tool_name: str) -> None:
        """Step 単位のツール呼び出し回数を +1 する。

        step_id が None / 空の場合は current_running_step_id を代用し、
        それも無ければ記録しない。
        """
        sid = step_id or self.current_running_step_id
        if not sid or not tool_name:
            return
        bucket = self.tool_counts_by_step.setdefault(sid, {})
        bucket[tool_name] = bucket.get(tool_name, 0) + 1
        self._signals.tool_counts_updated.emit(sid, tool_name)

    def record_skill_invoked(self, step_id: Optional[str], skill_name: str) -> None:
        """Step 単位の Skill 読み込み回数を +1 する。"""
        sid = step_id or self.current_running_step_id
        if not sid or not skill_name:
            return
        bucket = self.skill_counts_by_step.setdefault(sid, {})
        bucket[skill_name] = bucket.get(skill_name, 0) + 1
        self._signals.skill_counts_updated.emit(sid, skill_name)

    def current_tool_counts(self) -> Dict[str, int]:
        """表示対象 Step （running または最後に running だった Step）のツール集計を返す。"""
        sid = self.current_running_step_id or self.last_known_step_id
        if not sid:
            return {}
        return dict(self.tool_counts_by_step.get(sid, {}))

    def current_skill_counts(self) -> Dict[str, int]:
        """表示対象 Step の Skill 集計を返す。"""
        sid = self.current_running_step_id or self.last_known_step_id
        if not sid:
            return {}
        return dict(self.skill_counts_by_step.get(sid, {}))

    def apply_session_usage_detail(
        self,
        *,
        system: Optional[int] = None,
        tool_definitions: Optional[int] = None,
        conversation: Optional[int] = None,
    ) -> None:
        """SDK ``session.usage_info`` 詳細を反映する。

        いずれも SDK 未提供時は None。None は上書きしない（既存値を保持）。
        """
        if system is not None:
            self.context_system_tokens = int(system)
        if tool_definitions is not None:
            self.context_tool_definitions_tokens = int(tool_definitions)
        if conversation is not None:
            self.context_conversation_tokens = int(conversation)

    def apply_assistant_usage(
        self,
        *,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        reasoning_tokens: Optional[int] = None,
        cache_read: Optional[int] = None,
        cache_write: Optional[int] = None,
        inter_token_latency_ms: Optional[float] = None,
        token_details: Optional[list] = None,
    ) -> None:
        """SDK ``assistant.usage`` を Workflow 全体へ累積する。"""
        self.assistant_usage_count += 1
        if input_tokens is not None:
            self.assistant_input_tokens_total += int(input_tokens)
        if output_tokens is not None:
            self.assistant_output_tokens_total += int(output_tokens)
        if reasoning_tokens is not None:
            self.assistant_reasoning_tokens_total += int(reasoning_tokens)
        if cache_read is not None:
            self.assistant_cache_read_total += int(cache_read)
        if cache_write is not None:
            self.assistant_cache_write_total += int(cache_write)
        if inter_token_latency_ms is not None:
            self.assistant_inter_token_latency_ms_last = float(inter_token_latency_ms)
        if token_details:
            for td in token_details:
                try:
                    t = str(td.get("type", "") or "")
                    c = int(td.get("count", 0) or 0)
                    if not t:
                        continue
                    self.billing_token_totals[t] = self.billing_token_totals.get(t, 0) + c
                except (AttributeError, TypeError, ValueError):
                    continue

    def apply_ttft(self, ttft_ms: float) -> None:
        """TTFT 観測値を統計に加える。"""
        try:
            v = float(ttft_ms)
        except (TypeError, ValueError):
            return
        if self.ttft_first_ms is None:
            self.ttft_first_ms = v
        self.ttft_last_ms = v
        self.ttft_sum_ms += v
        self.ttft_count += 1

    def apply_compaction(self, removed: int) -> None:
        self.compaction_count += 1
        try:
            self.compaction_tokens_removed_total += max(0, int(removed))
        except (TypeError, ValueError):
            pass

    def apply_permission_count(self, count: int) -> None:
        try:
            self.permission_count = max(self.permission_count, int(count))
        except (TypeError, ValueError):
            pass

    # --- 料金 (Wave 3) ---

    def set_pricing(
        self,
        pricing: Optional[object],
        *,
        usd_jpy_rate: Optional[float] = None,
        plan_id: Optional[str] = None,
    ) -> None:
        """料金表スナップショットおよび計算パラメータを注入する。

        pricing=None でも例外にせず、以降の計算は ``cost_method_last="unavailable"`` で
        記録される（捏造しない）。
        """
        self.pricing_snapshot = pricing
        if usd_jpy_rate is not None:
            self.pricing_usd_jpy_rate = float(usd_jpy_rate)
        if plan_id is not None:
            self.pricing_plan_id = str(plan_id)

    def apply_premium_requests(
        self,
        count: int,
        *,
        model: Optional[str] = None,
    ) -> None:
        """SDK ``session.shutdown`` で報告された premium_requests を累積コストへ反映する。

        - ``count`` は当該セッション分の総数（既存累積に対しては「増分」として加算）。
          複数 Step 間で同じ session が再利用されるケースは想定していないため単純加算。
        - ``model`` 未指定時は ``self.model`` を使う。
        - 料金表が未注入 / 計算不能な場合は ``cost_usd_total`` を None のまま保持し、
          ``cost_unavailable_reason`` に理由を記録する（捏造防止）。
        """
        try:
            n = int(count)
        except (TypeError, ValueError):
            return
        if n <= 0:
            return
        self.premium_requests_total += n

        # 料金計算（pricing 未注入 → unavailable）
        if self.pricing_snapshot is None:
            self.cost_method_last = "unavailable"
            self.cost_unavailable_reason = "pricing_not_loaded"
            return

        try:
            # 遅延 import: GUI 非依存テストのため
            from ..pricing import calc_cost  # type: ignore
        except Exception:  # pragma: no cover
            try:
                from hve.pricing import calc_cost  # type: ignore
            except Exception:
                self.cost_method_last = "unavailable"
                self.cost_unavailable_reason = "pricing_module_unavailable"
                return

        model_name = model or self.model
        try:
            br = calc_cost(
                model=model_name,
                premium_requests=n,
                pricing=self.pricing_snapshot,
                plan_id=self.pricing_plan_id or None,
                usd_jpy_rate=self.pricing_usd_jpy_rate,
            )
        except Exception as exc:  # pragma: no cover
            self.cost_method_last = "unavailable"
            self.cost_unavailable_reason = f"calc_error:{exc}"
            return

        self.cost_method_last = br.method
        if br.cost_usd is None:
            # 累積はそのまま (None → None) で残し、理由のみ更新
            self.cost_unavailable_reason = str((br.notes or {}).get("reason", "unknown"))
            return
        self.cost_unavailable_reason = ""
        # 既存累積 (None 可) に加算
        self.cost_usd_total = (self.cost_usd_total or 0.0) + float(br.cost_usd)
        if br.cost_jpy is not None:
            self.cost_jpy_total = (self.cost_jpy_total or 0.0) + float(br.cost_jpy)

    def set_model(self, name: str) -> None:
        self.model = name
        self._signals.model_updated.emit(name)

    def mark_all_done(self) -> None:
        if not self.all_done:
            self.all_done = True
            root = self.task_tree.root
            if root is not None:
                root.status = "done"
                root.finished_at = time.monotonic()
            self._finalize_current_workflow_snapshot()
            self._signals.all_done.emit()

    def mark_aborted(self) -> None:
        """致命的エラー検知による中止状態を記録し、`all_done` と同等の終了処理を走らせる。

        - ``aborted=True`` フラグを立て、UI 側で ``mark_all_done`` と区別して
          表示できるようにする。
        - TaskTree の root.status を ``failed`` にし、「完了」とは区別する。
        - Workbench UI スピナー/タイマー等のクリーンアップ处理は
          ``all_done`` シグナルに依存しているため、本メソッドも同シグナルを emit する。
        """
        if self.aborted and self.all_done:
            return
        self.aborted = True
        if not self.all_done:
            self.all_done = True
            root = self.task_tree.root
            if root is not None:
                root.status = "failed"
                root.finished_at = time.monotonic()
            self._finalize_current_workflow_snapshot()
            self._signals.all_done.emit()

    # ------------------------------------------------------------------
    # 統計履歴（stats_history）
    # ------------------------------------------------------------------

    def set_history_store(self, store: object) -> None:
        """履歴永続化ストアを登録する（T3 で実装）。

        store は ``save_step_snapshot(workflow, step)`` /
        ``save_workflow_snapshot(workflow)`` を備えるオブジェクト。
        書き込み失敗時に GUI を落とさないよう、呼び出し側で例外を握りつぶす想定。
        """
        self._history_store = store

    def _current_workflow_snapshot(self) -> Optional["WorkflowStatsSnapshot"]:
        if not self.stats_history:
            return None
        return self.stats_history[-1]

    def _ensure_current_workflow_snapshot(self) -> None:
        """現在の workflow_id に対応する snapshot を確保する。

        - 履歴が空、または末尾 snapshot の workflow_id/run_id が現値と異なれば
          新規 snapshot を追加。
        - 既存末尾 snapshot が未 finalize の場合は finalize して新規追加。
        """
        cur = self._current_workflow_snapshot()
        if cur is not None and cur.workflow_id == self.workflow_id and cur.run_id == self.run_id:
            # 同一実行: model 等の最新値を反映
            cur.workflow_name = self.workflow_name or cur.workflow_name
            cur.model = self.model or cur.model
            return
        # 別実行: 直前を finalize
        if cur is not None and not cur.finalized:
            self._finalize_current_workflow_snapshot()
        snap = WorkflowStatsSnapshot(
            workflow_id=self.workflow_id,
            workflow_name=self.workflow_name,
            run_id=self.run_id,
            model=self.model,
            started_at=time.monotonic(),
        )
        self.stats_history.append(snap)
        self._signals.stats_history_updated.emit()

    def _record_step_snapshot(self, step_id: str, status: StepStatus) -> None:
        """Step 完了系遷移時にスナップショットを履歴へ push する。"""
        # 履歴 snapshot が無ければ自動生成（識別子未確定でも記録できるよう）
        if self._current_workflow_snapshot() is None:
            self._ensure_current_workflow_snapshot()
        wf = self._current_workflow_snapshot()
        if wf is None:
            return

        # Step タイトル / 開始時刻は steps / task_tree から取得
        step_title = step_id
        started_at: Optional[float] = None
        for s in self.steps:
            if s.id == step_id:
                step_title = s.title or step_id
                started_at = s.started_at
                break
        node = self.task_tree.get(step_id)
        if node is not None:
            if started_at is None:
                started_at = node.started_at
            finished_at = node.finished_at
        else:
            finished_at = time.monotonic()

        elapsed: Optional[float] = None
        if started_at is not None and finished_at is not None:
            elapsed = max(0.0, finished_at - started_at)

        tool_counts = dict(self.tool_counts_by_step.get(step_id, {}))
        skill_counts = dict(self.skill_counts_by_step.get(step_id, {}))

        snap = StepStatsSnapshot(
            step_id=step_id,
            step_title=step_title,
            status=status,
            model=self.model,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_sec=elapsed,
            context_current=self.context_current or None,
            context_limit=self.context_limit or None,
            tool_counts=tool_counts,
            skill_counts=skill_counts,
        )
        wf.steps.append(snap)
        # Workflow 側の最新 Context も更新
        wf.context_current = self.context_current or wf.context_current
        wf.context_limit = self.context_limit or wf.context_limit
        wf.model = self.model or wf.model

        if self._history_store is not None:
            try:
                self._history_store.save_step_snapshot(wf, snap)  # type: ignore[attr-defined]
            except Exception:
                pass

        self._signals.stats_history_updated.emit()

    def _finalize_current_workflow_snapshot(self) -> None:
        wf = self._current_workflow_snapshot()
        if wf is None or wf.finalized:
            return
        wf.finished_at = time.monotonic()
        if wf.started_at is not None:
            wf.elapsed_sec = max(0.0, wf.finished_at - wf.started_at)
        wf.context_current = self.context_current or wf.context_current
        wf.context_limit = self.context_limit or wf.context_limit
        wf.model = self.model or wf.model
        wf.finalized = True

        if self._history_store is not None:
            try:
                self._history_store.save_workflow_snapshot(wf)  # type: ignore[attr-defined]
            except Exception:
                pass

        self._signals.stats_history_updated.emit()

    def user_actions_view(self) -> List[UserAction]:
        """ユーザーアクションビュー（スクロール対応）。"""
        visible_count = USER_ACTIONS_VISIBLE
        if len(self.user_actions) <= visible_count:
            return self.user_actions

        start_idx = max(0, len(self.user_actions) - visible_count - self.user_actions_scroll)
        return self.user_actions[start_idx : start_idx + visible_count]

    def user_actions_max_offset(self) -> int:
        return max(0, len(self.user_actions) - USER_ACTIONS_VISIBLE)

    def task_tree_total_nodes(self) -> int:
        return self.task_tree.total_nodes()

    def task_tree_max_offset(self, max_lines: int) -> int:
        """タスクツリーの最大スクロール量。"""
        return max(0, self.task_tree_total_nodes() - max_lines)


    # ------------------------------------------------------------------
    # 並列 Workflow インスタンス管理 (Wave 1: gui-unified-workbench)
    # ------------------------------------------------------------------

    def ensure_workflow_instance(
        self,
        instance_id: str,
        workflow_id: str,
        label: str,
        app_id: "Optional[str]" = None,
    ) -> "WorkflowInstance":
        """instance_id に対応する WorkflowInstance を保証する。既存があれば返す。"""
        inst = self.workflows.get(instance_id)
        if inst is None:
            inst = WorkflowInstance(
                instance_id=instance_id,
                workflow_id=workflow_id,
                label=label,
                app_id=app_id,
            )
            self.workflows[instance_id] = inst
            self._signals.workflow_instance_changed.emit(instance_id)
        return inst

    def append_workflow_log(
        self,
        instance_id: str,
        step_id: "Optional[str]",
        line: str,
    ) -> "Optional[str]":
        """ワークフローインスタンスへログ1行を追記する。

        UI 表示・コピー用に ``[workflow_id]-[step_id.title]`` のプリフィックスを付与する
        （Step 不明時は ``[wf]-[main]``）。``[hve:stats] {...}`` 行はプリフィックス対象外
        （UI 非表示行のため）。

        Returns:
            内部バッファへ格納したフォーマット済み行。``instance_id`` が未登録なら
            ``None``。呼び出し側は戻り値を [全体] ログタブ等の表示パスへ反映する
            ことで、プリフィックスの一貫性を保つ。
        """
        inst = self.workflows.get(instance_id)
        if inst is None:
            return None
        # stats 行はフィルタ済み JSON のため、プリフィックスを付与せずそのまま記録する。
        if line.startswith("[hve:stats]"):
            formatted = line
        else:
            step_title: Optional[str] = None
            if step_id:
                sv = inst.steps.get(step_id)
                if sv is not None:
                    step_title = getattr(sv, "title", None)
            formatted = format_log_prefix(inst.workflow_id, step_id, step_title) + line
        inst.log_buffer.append(formatted)
        if step_id:
            inst.step_log_buffers.setdefault(step_id, []).append(formatted)
        self._signals.workflow_instance_log.emit(instance_id, step_id or "", formatted)
        return formatted

    def update_workflow_instance_status(
        self,
        instance_id: str,
        status: "StepStatus",
    ) -> None:
        """インスタンス全体の status を更新する。"""
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        inst = self.workflows.get(instance_id)
        if inst is None:
            return
        if status == "running" and inst.started_at is None:
            inst.started_at = time.monotonic()
        if status in ("done", "failed", "skipped") and inst.finished_at is None:
            inst.finished_at = time.monotonic()
        inst.status = status
        self._signals.workflow_instance_changed.emit(instance_id)

    def mark_workflow_instance_finished(
        self,
        instance_id: str,
        returncode: "Optional[int]",
    ) -> None:
        """インスタンス終了記録。returncode==0 -> done、それ以外 -> failed。"""
        inst = self.workflows.get(instance_id)
        if inst is None:
            return
        inst.returncode = returncode
        status = "done" if returncode == 0 else "failed"
        self.update_workflow_instance_status(instance_id, status)

    def prepopulate_workflow_instances(
        self,
        seeds: "List[WorkflowInstanceSeed]",
    ) -> None:
        """Step 1 で確定した全ワークフロー（およびそのステップ）を pending 状態で
        ``self.workflows`` に事前登録する。

        Autopilot 起動経路で「現在実行中のワークフローのみ表示」される問題を解消するため、
        AutopilotPlan から導出した全 (instance_id, workflow_id, app_id, steps) を
        一括投入する。既存 instance_id があれば**上書きせずスキップ**する（重複呼び出し冪等）。

        各 seed の ``steps`` は ``WorkflowInstance.steps`` (OrderedDict[step_id, StepView])
        を pending 状態で充填する。挿入順は seeds の順を保つ（Q5=A: Step 1 依存ソート後の
        選択順）。

        Phase 2 (Q7=B / Q3=B): ``steps`` の各要素は以下のいずれかを受け付ける:

          * ``(step_id, title)``                        — 後方互換 (flat、kind="step")
          * ``(step_id, title, kind)``                  — kind 指定可
          * ``(step_id, title, kind, [child_step, ...])`` — 任意ネスト
          * :class:`StepSeed`                            — 推奨 (再帰構造)

        ``OrderedDict`` には root step のみが格納され、container 配下の子は
        ``StepView.children`` に再帰格納される（任意の深さ）。

        Args:
            seeds: 事前登録対象のワークフローインスタンス情報。
        """
        for seed in seeds:
            if seed.instance_id in self.workflows:
                continue
            inst = WorkflowInstance(
                instance_id=seed.instance_id,
                workflow_id=seed.workflow_id,
                label=seed.label or seed.instance_id,
                app_id=seed.app_id,
            )
            for raw in seed.steps:
                step_view = _step_seed_to_view(raw, parent_id=None)
                inst.steps[step_view.id] = step_view
            self.workflows[seed.instance_id] = inst
            self._signals.workflow_instance_changed.emit(seed.instance_id)

    def remove_workflow_instance(self, instance_id: str) -> None:
        """``self.workflows`` から指定 instance を削除し signal を emit する。

        gui-workbench-autopilot-display T3b: Autopilot の app_chains 起動時に、
        pre_phase 段階で先行投入した placeholder (``instance_id = workflow_id``)
        を本 seed (``{workflow_id}#{app_id}``) と衝突しないよう削除するために使う。
        未登録の instance_id に対しては no-op。
        """
        if not instance_id or instance_id not in self.workflows:
            return
        self.workflows.pop(instance_id, None)
        self._signals.workflow_instance_changed.emit(instance_id)

    # ------------------------------------------------------------------
    # Step ツリー操作 (Phase 2: Q6=B / Q7=B / Q12=b)
    # ------------------------------------------------------------------

    def find_step_in_instance(
        self,
        instance_id: str,
        step_id: str,
    ) -> "Optional[StepView]":
        """指定 instance の step ツリーから step_id を再帰検索する。"""
        inst = self.workflows.get(instance_id)
        if inst is None:
            return None
        for root in inst.steps.values():
            found = _find_step_recursive(root, step_id)
            if found is not None:
                return found
        return None

    def update_step_status_in_instance(
        self,
        instance_id: str,
        step_id: str,
        status: StepStatus,
    ) -> None:
        """instance のツリーから step を検索し、status を更新する（任意の深さ）。

        running 遷移時に ``started_at`` が未設定なら time.monotonic() を記録、
        終了状態 (done/failed/skipped) で ``finished_at`` を記録する。
        ``workflow_instance_changed`` signal を emit する。
        """
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        node = self.find_step_in_instance(instance_id, step_id)
        if node is None:
            return
        node.status = status
        if status == "running" and node.started_at is None:
            node.started_at = time.monotonic()
        if status in ("done", "failed", "skipped") and node.finished_at is None:
            node.finished_at = time.monotonic()
        self._signals.workflow_instance_changed.emit(instance_id)

    def add_step_subtask(
        self,
        instance_id: str,
        parent_step_id: "Optional[str]",
        subtask_id: str,
        title: str,
        kind: StepKind = "subagent",
        status: StepStatus = "running",
    ) -> "Optional[StepView]":
        """指定 instance の親 Step 配下に Subtask (Sub-agent / Fanout 子) を追加する。

        Q6=B / Q7=B / Q12=b: Plan モード固有だった ``_workflow_subtask_status`` 辞書を
        ``WorkflowInstance.steps`` 配下の ``StepView.children`` に統合する。

        - ``parent_step_id`` が None または見つからなければ追加しない（捏造防止）。
        - 同名 (id 一致) の child があれば作成せず既存を返す（冪等）。
        - 親が container でない場合も子を持てる（Q7=B 無制限ネスト）。

        Returns:
            追加 / 既存の StepView。失敗時 None。
        """
        if not parent_step_id:
            return None
        parent = self.find_step_in_instance(instance_id, parent_step_id)
        if parent is None:
            return None
        for existing in parent.children:
            if existing.id == subtask_id:
                return existing
        sub = StepView(
            id=subtask_id,
            title=title,
            status=status,
            parent_id=parent_step_id,
            kind=kind,
            started_at=time.monotonic() if status == "running" else None,
        )
        parent.children.append(sub)
        self._signals.workflow_instance_changed.emit(instance_id)
        return sub

    def update_step_in_instance(
        self,
        instance_id: str,
        step_id: str,
        **fields,
    ) -> None:
        """instance のツリーから step を検索し、任意フィールドを更新する。"""
        node = self.find_step_in_instance(instance_id, step_id)
        if node is None:
            return
        changed = False
        for k, v in fields.items():
            if hasattr(node, k) and getattr(node, k) != v:
                setattr(node, k, v)
                changed = True
        if changed:
            self._signals.workflow_instance_changed.emit(instance_id)


# ---------------------------------------------------------------------------
# 内部ヘルパ (StepSeed → StepView 変換 / ツリー検索)
# ---------------------------------------------------------------------------


def _step_seed_to_view(raw, parent_id: Optional[str]) -> "StepView":
    """``WorkflowInstanceSeed.steps`` の要素を ``StepView`` に変換する（再帰）。

    後方互換のため複数フォーマットを受け付ける:
      * StepSeed
      * (id, title)
      * (id, title, kind)
      * (id, title, kind, children)  children は再帰的に同フォーマット
    """
    if isinstance(raw, StepSeed):
        view = StepView(
            id=raw.id,
            title=raw.title,
            status="pending",
            parent_id=parent_id,
            kind=raw.kind,  # type: ignore[arg-type]
        )
        for child in raw.children:
            view.children.append(_step_seed_to_view(child, parent_id=raw.id))
        return view
    if isinstance(raw, tuple):
        if len(raw) == 2:
            sid, title = raw
            return StepView(id=sid, title=title, status="pending", parent_id=parent_id, kind="step")
        if len(raw) == 3:
            sid, title, kind = raw
            return StepView(
                id=sid, title=title, status="pending", parent_id=parent_id, kind=kind  # type: ignore[arg-type]
            )
        if len(raw) >= 4:
            sid, title, kind, children = raw[0], raw[1], raw[2], raw[3]
            view = StepView(
                id=sid, title=title, status="pending", parent_id=parent_id, kind=kind  # type: ignore[arg-type]
            )
            for child in (children or []):
                view.children.append(_step_seed_to_view(child, parent_id=sid))
            return view
    raise TypeError(f"Unsupported step seed format: {raw!r}")


def _find_step_recursive(node: "StepView", step_id: str) -> "Optional[StepView]":
    """StepView ツリーから step_id を再帰検索する（DFS）。"""
    if node.id == step_id:
        return node
    for child in node.children:
        found = _find_step_recursive(child, step_id)
        if found is not None:
            return found
    return None


@dataclass
class StepSeed:
    """``WorkflowInstanceSeed.steps`` の再帰木フォーマット (Phase 2: Q10=a)。

    container Step や Sub-agent / Fanout 子の事前登録に使う。``children`` に再帰的に
    別の ``StepSeed`` を持つことで任意ネストを表現できる（Q7=B 無制限ネスト）。
    """

    id: str
    title: str
    kind: str = "step"  # "step" | "container" | "fanout_child" | "subagent"
    children: List["StepSeed"] = field(default_factory=list)


@dataclass
class WorkflowInstanceSeed:
    """``prepopulate_workflow_instances`` 用の事前登録シード。

    Step 1 で確定した workflow 選択を ``WorkbenchState.workflows`` に流し込むための
    最小情報セット。``instance_id`` の命名規約は ``{workflow_id}`` (app_id なし) または
    ``{workflow_id}#{app_id}`` (Q14=a 採用)。
    """

    instance_id: str
    workflow_id: str
    label: str
    app_id: Optional[str] = None
    steps: List[tuple] = field(default_factory=list)  # List[(step_id, title)]
