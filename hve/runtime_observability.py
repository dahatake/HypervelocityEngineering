"""hve/runtime_observability.py — 実行時観測イベントの単一実装（FR-RTO-01）。

`[hve:stats]` 行の構築・解析と、実行面横断で同じ集計値を得るための reducer を
1 箇所へ集約する（FR-MAINT-07）。既存の `kind` / `step` キーと行形式は変更しない
（NFR-RTO-02）。GUI / PySide6 に依存しない。
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional, Set

SCHEMA_VERSION = 1

STATS_PREFIX = "[hve:stats] "

# FR-RTO-08: GitHub の Root Issue / PR / 作業 branch 確定を通知する唯一の kind。
GITHUB_TARGET_KIND = "github_target"

# FR-RTO-02: Dashboard を持つ親が子プロセスへ stats 配信を許可する唯一のマーカー。
STATS_STREAM_ENV = "HVE_STATS_STREAM"

# GUI が子プロセスへ注入する起源識別子（`hve/gui/session_workdir.py` env_overrides）。
GUI_SESSION_ENV = "HVE_GUI_SESSION_ID"

_STATS_STREAM_TRUTHY = ("1", "true", "True")


def is_child_process() -> bool:
    """親プロセスから起動され作業ディレクトリを共有する子プロセスかを返す。

    GUI Autopilot の子は `HVE_GUI_SESSION_ID` だけを、CLI Autopilot の子は
    `HVE_STATS_STREAM` だけを継承するため、両方を条件とする（FR-MCPLOG-02）。
    判定は `hve/console.py` の stats 配信可否と共通の単一実装とする（FR-MAINT-07）。
    """
    if os.environ.get(GUI_SESSION_ENV, "").strip():
        return True
    return os.environ.get(STATS_STREAM_ENV, "").strip() in _STATS_STREAM_TRUTHY

# 既存 producer（hve/console.py / hve/runner.py / hve/dag_executor.py）が発火する kind。
KNOWN_KINDS = frozenset(
    {
        "step_status",
        "fanout_init",
        "tool_invoked",
        "tool_result",
        "skill_invoked",
        "file_io",
        "assistant_usage",
        "assistant_ttft",
        "usage_credit",
        "quota_snapshot",
        "session_usage_detail",
        "compaction_complete",
        "permission_count",
        "premium_requests",
        "model_call_failure",
        "assistant_usage_raw",
        "debug_env",
        "assistant_usage_raw_err",
        # FR-RTO-08: GitHub の Root Issue / PR / 作業 branch の確定を通知する。
        GITHUB_TARGET_KIND,
    }
)

_TERMINAL_STATUSES = frozenset({"done", "failed", "skipped", "blocked"})

# 先頭の `[HH:MM:SS] ` と行頭インデントは任意（既存 GUI パーサと同じ許容範囲）。
_STATS_LINE_RE = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*\[hve:stats\]\s*(?P<json>\{.*\})\s*$"
)


def make_instance_id(workflow_id: str, app_id: Optional[str] = None) -> str:
    """FR-RTO-01: instance_id は workflow_id、APP 並列時のみ `workflow_id#app_id`。"""
    wf = (workflow_id or "").strip()
    app = (app_id or "").strip()
    return f"{wf}#{app}" if app else wf


@dataclass
class RuntimeContext:
    """1 プロセス分の実行識別子と連番。"""

    run_id: str = ""
    workflow_id: str = ""
    instance_id: str = ""
    pid: int = field(default_factory=os.getpid)
    _seq: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    kind: str,
    step_id: str = "",
    context: Optional[RuntimeContext] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """観測イベント payload を構築する。

    既存契約との互換のため `kind` / `step` は常に含め、`None` のフィールドは落とす。
    """
    ctx = context if context is not None else RuntimeContext()
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": _utc_now_iso(),
        "seq": ctx.next_seq(),
        "pid": int(ctx.pid),
        "kind": str(kind),
        "step": step_id or "",
    }
    for key, value in (
        ("run_id", ctx.run_id),
        ("workflow_id", ctx.workflow_id),
        ("instance_id", ctx.instance_id),
    ):
        if value:
            payload[key] = value
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    return payload


def format_stats_line(payload: Dict[str, Any]) -> str:
    """payload を既存の `[hve:stats] {...}` 1 行形式へ整形する。"""
    return STATS_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


# FR-RTO-08: `owner/repo` のみを許可し、remote URL や余分な階層を弾く。
_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _positive_int_or_none(value: Any) -> Optional[int]:
    """`bool` を除く正の整数だけを返す。推定変換は行わない。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def github_target_fields(
    *,
    repo: Any = None,
    issue_number: Any = None,
    pr_number: Any = None,
    branch: Any = None,
    base_branch: Any = None,
    created_by_hve: Any = None,
    delete_local_merged_branch: Any = None,
) -> Dict[str, Any]:
    """FR-RTO-08: GitHub target イベントへ載せてよいフィールドだけを返す。

    確定した値だけを残し、未確定・不正値のキーは省略する（推定で補わない）。
    token / 本文 / URL は引数に取らないため、構造上イベントへ混入しない。
    値検証の単一実装とし、producer 側で同等の検証を再実装してはならない
    （FR-MAINT-07）。
    """
    fields: Dict[str, Any] = {}
    if isinstance(repo, str) and _REPO_SLUG_RE.match(repo):
        fields["repo"] = repo

    issue = _positive_int_or_none(issue_number)
    if issue is not None:
        fields["issue_number"] = issue
    pull = _positive_int_or_none(pr_number)
    if pull is not None:
        fields["pr_number"] = pull

    branch_name = branch.strip() if isinstance(branch, str) else ""
    if branch_name:
        fields["branch"] = branch_name
    base_name = base_branch.strip() if isinstance(base_branch, str) else ""
    if base_name:
        fields["base_branch"] = base_name

    # branch が未確定なら created_by_hve は意味を持たないため送出しない。
    if branch_name and isinstance(created_by_hve, bool):
        fields["created_by_hve"] = created_by_hve
    if isinstance(delete_local_merged_branch, bool):
        fields["delete_local_merged_branch"] = delete_local_merged_branch
    return fields


def build_github_target_event(
    *,
    repo: Any = None,
    issue_number: Any = None,
    pr_number: Any = None,
    branch: Any = None,
    base_branch: Any = None,
    created_by_hve: Any = None,
    delete_local_merged_branch: Any = None,
    context: Optional[RuntimeContext] = None,
) -> Dict[str, Any]:
    """FR-RTO-08: GitHub target lifecycle イベントを構築する。"""
    fields = github_target_fields(
        repo=repo,
        issue_number=issue_number,
        pr_number=pr_number,
        branch=branch,
        base_branch=base_branch,
        created_by_hve=created_by_hve,
        delete_local_merged_branch=delete_local_merged_branch,
    )
    return build_event(GITHUB_TARGET_KIND, context=context, **fields)


def _attr(data: Any, *names: str) -> Any:
    """SDK data オブジェクトから snake_case / camelCase 属性を安全に取得する。"""
    if data is None:
        return None
    for name in names:
        value = getattr(data, name, None)
        if value is not None:
            return value
    return None


def extract_usage_credit_fields(data: Any) -> Optional[Dict[str, Any]]:
    """SDK ``assistant.usage`` データから ``usage_credit`` イベント用の値を抽出する。

    FR-MAINT-07: 通常 Step 実行（`hve/runner.py`）と SDK Fleet mode
    （`hve/fleet_mode.py`）の双方から呼ばれる単一実装。

    SDK 1.0.x では ``copilot_usage`` が Internal 属性へ改名されており getattr では
    取得できないため、公開シリアライズ契約 ``to_dict()`` の camelCase キーから読む。

    Returns:
        ``api_call_id`` / ``model`` / ``multiplier_cost`` / ``nano_aiu`` /
        ``unavailable_reason`` の dict。いずれの課金値も取得できない場合は ``None``。
        FR-RTO-04 の allowlist に従い、本文系フィールドは一切含めない。
    """
    if data is None:
        return None

    usage_dict: Dict[str, Any] = {}
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        try:
            serialized = to_dict()
        except Exception:
            serialized = None
        if isinstance(serialized, dict):
            usage_dict = serialized

    copilot_usage = usage_dict.get("copilotUsage")
    if not isinstance(copilot_usage, dict):
        copilot_usage = None

    api_call_id = _attr(data, "api_call_id", "apiCallId")
    multiplier_cost = _attr(data, "cost")
    nano_aiu = copilot_usage.get("totalNanoAiu") if copilot_usage is not None else None
    unavailable_reason = (
        None
        if copilot_usage is not None
        else "SDK assistant.usage provided no copilotUsage (totalNanoAiu unavailable)"
    )

    if api_call_id is None and multiplier_cost is None and nano_aiu is None and unavailable_reason is None:
        return None

    model = _attr(data, "model")
    return {
        "api_call_id": str(api_call_id) if api_call_id is not None else None,
        "model": str(model) if model is not None else None,
        "multiplier_cost": _as_float(multiplier_cost),
        "nano_aiu": _as_float(nano_aiu),
        "unavailable_reason": unavailable_reason,
    }


def parse_stats_line(line: str) -> Optional[Dict[str, Any]]:
    """`[hve:stats] {...}` 行を payload dict へ解析する。副作用なし。"""
    match = _STATS_LINE_RE.match(line)
    if not match:
        return None
    try:
        payload = json.loads(match.group("json"))
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_stats_line(line: str) -> bool:
    return bool(_STATS_LINE_RE.match(line))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class RuntimeMetrics:
    """FR-RTO-05: 実行面横断で同一の集計値を得るための reducer。"""

    step_status: Dict[str, str] = field(default_factory=dict)
    running_steps: Set[str] = field(default_factory=set)
    last_step_id: Optional[str] = None

    context_current: int = 0
    context_limit: int = 0
    context_msgs: int = 0

    input_tokens_total: int = 0
    output_tokens_total: int = 0
    reasoning_tokens_total: int = 0
    cache_read_total: int = 0
    cache_write_total: int = 0
    assistant_usage_count: int = 0

    ttft_first_ms: Optional[float] = None
    ttft_last_ms: Optional[float] = None

    aiu_nano_total: int = 0
    multiplier_cost_total: float = 0.0
    credit_unavailable_reason: str = ""
    premium_requests_total: int = 0

    tool_counts_by_step: Dict[str, Dict[str, int]] = field(default_factory=dict)
    skill_counts_by_step: Dict[str, Dict[str, int]] = field(default_factory=dict)

    compaction_count: int = 0
    compaction_tokens_removed: int = 0
    permission_count: int = 0
    model_call_failures: int = 0
    tool_successes: int = 0
    tool_failures: int = 0

    unknown_kinds: Set[str] = field(default_factory=set)
    unknown_kind_count: int = 0

    _seen_api_call_ids: Set[str] = field(default_factory=set, repr=False)
    _quota_baseline: Dict[str, int] = field(default_factory=dict, repr=False)
    _quota_latest: Dict[str, int] = field(default_factory=dict, repr=False)

    # -- 集約プロパティ -------------------------------------------------

    @property
    def aiu_total(self) -> float:
        return self.aiu_nano_total / 1_000_000_000.0

    @property
    def quota_used_delta_total(self) -> int:
        total = 0
        for quota_id, latest in self._quota_latest.items():
            total += max(0, latest - self._quota_baseline.get(quota_id, 0))
        return total

    @property
    def display_reqs(self) -> int:
        """Reqs 表示値。優先順位は既存 GUI Footer と同一（捏造しない）。"""
        if self.premium_requests_total > 0:
            return self.premium_requests_total
        delta = self.quota_used_delta_total
        if delta > 0:
            return delta
        return self.assistant_usage_count

    def current_tool_counts(self) -> Dict[str, int]:
        return self._counts_for_display(self.tool_counts_by_step)

    def current_skill_counts(self) -> Dict[str, int]:
        return self._counts_for_display(self.skill_counts_by_step)

    def _counts_for_display(self, source: Dict[str, Dict[str, int]]) -> Dict[str, int]:
        # 並列実行中は単一 step へ寄せると偏るため running 全体を合算する。
        if len(self.running_steps) >= 2:
            merged: Dict[str, int] = {}
            for step_id in self.running_steps:
                for name, count in source.get(step_id, {}).items():
                    merged[name] = merged.get(name, 0) + count
            return merged
        target: Optional[str] = None
        if len(self.running_steps) == 1:
            target = next(iter(self.running_steps))
        target = target or self.last_step_id
        return dict(source.get(target, {})) if target else {}

    # -- 適用 -----------------------------------------------------------

    def apply(self, payload: Dict[str, Any]) -> bool:
        """1 イベントを反映する。既知 kind を処理したら True。"""
        if not isinstance(payload, dict):
            return False
        kind = str(payload.get("kind") or "")
        if kind not in KNOWN_KINDS:
            self.unknown_kinds.add(kind)
            self.unknown_kind_count += 1
            return False

        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(payload)
        return True

    def apply_line(self, line: str) -> bool:
        payload = parse_stats_line(line)
        if payload is None:
            return False
        return self.apply(payload)

    # -- kind 別ハンドラ -------------------------------------------------

    @staticmethod
    def _step_of(payload: Dict[str, Any]) -> str:
        value = payload.get("step") or payload.get("step_id") or ""
        return value.strip() if isinstance(value, str) else ""

    def _on_step_status(self, payload: Dict[str, Any]) -> None:
        step_id = self._step_of(payload)
        status = payload.get("status")
        status = status.strip() if isinstance(status, str) else ""
        if not step_id or not status:
            return
        self.step_status[step_id] = status
        if status == "running":
            self.running_steps.add(step_id)
            self.last_step_id = step_id
        elif status in _TERMINAL_STATUSES:
            self.running_steps.discard(step_id)

    def _on_session_usage_detail(self, payload: Dict[str, Any]) -> None:
        self.context_current = _as_int(payload.get("current"), self.context_current)
        self.context_limit = _as_int(payload.get("limit"), self.context_limit)
        self.context_msgs = _as_int(payload.get("msgs"), self.context_msgs)

    def _on_assistant_usage(self, payload: Dict[str, Any]) -> None:
        self.assistant_usage_count += 1
        self.input_tokens_total += _as_int(payload.get("input"))
        self.output_tokens_total += _as_int(payload.get("output"))
        self.reasoning_tokens_total += _as_int(payload.get("reasoning"))
        self.cache_read_total += _as_int(payload.get("cache_read"))
        self.cache_write_total += _as_int(payload.get("cache_write"))

    def _on_assistant_ttft(self, payload: Dict[str, Any]) -> None:
        value = _as_float(payload.get("ttft_ms"))
        if value is None:
            return
        if self.ttft_first_ms is None:
            self.ttft_first_ms = value
        self.ttft_last_ms = value

    def _on_usage_credit(self, payload: Dict[str, Any]) -> None:
        reason = payload.get("unavailable_reason")
        if reason and not self.credit_unavailable_reason:
            self.credit_unavailable_reason = str(reason)
        api_call_id = payload.get("api_call_id")
        if api_call_id:
            key = str(api_call_id)
            if key in self._seen_api_call_ids:
                return
            self._seen_api_call_ids.add(key)
        nano = _as_float(payload.get("nano_aiu"))
        if nano and nano > 0:
            self.aiu_nano_total += int(nano)
        cost = _as_float(payload.get("multiplier_cost"))
        if cost and cost > 0:
            self.multiplier_cost_total += cost

    def _on_quota_snapshot(self, payload: Dict[str, Any]) -> None:
        quota_id = payload.get("quota_id")
        if not quota_id:
            return
        key = str(quota_id)
        used = _as_int(payload.get("used_requests"))
        self._quota_baseline.setdefault(key, used)
        self._quota_latest[key] = used

    def _on_premium_requests(self, payload: Dict[str, Any]) -> None:
        count = _as_int(payload.get("count"))
        if count > 0:
            self.premium_requests_total += count

    def _on_tool_invoked(self, payload: Dict[str, Any]) -> None:
        name = payload.get("tool_name")
        if not name:
            return
        self._increment(self.tool_counts_by_step, self._step_of(payload), str(name))

    def _on_skill_invoked(self, payload: Dict[str, Any]) -> None:
        name = payload.get("name")
        if not name:
            return
        self._increment(self.skill_counts_by_step, self._step_of(payload), str(name))

    def _increment(self, source: Dict[str, Dict[str, int]], step_id: str, name: str) -> None:
        key = step_id or self.last_step_id or ""
        if not key:
            return
        bucket = source.setdefault(key, {})
        bucket[name] = bucket.get(name, 0) + 1

    def _on_compaction_complete(self, payload: Dict[str, Any]) -> None:
        self.compaction_count += 1
        self.compaction_tokens_removed += max(0, _as_int(payload.get("removed")))

    def _on_permission_count(self, payload: Dict[str, Any]) -> None:
        self.permission_count = max(self.permission_count, _as_int(payload.get("count")))

    def _on_model_call_failure(self, payload: Dict[str, Any]) -> None:
        self.model_call_failures += 1

    def _on_tool_result(self, payload: Dict[str, Any]) -> None:
        if payload.get("success"):
            self.tool_successes += 1
        else:
            self.tool_failures += 1


DEFAULT_INSTANCE_ID = "__default__"


class RuntimeMetricsRegistry:
    """FR-RTO-05: instance 単位で分離し、run 単位で合算する。"""

    def __init__(self) -> None:
        self._instances: "OrderedDict[str, RuntimeMetrics]" = OrderedDict()
        self._lock = threading.Lock()

    def for_instance(self, instance_id: str) -> RuntimeMetrics:
        key = (instance_id or "").strip() or DEFAULT_INSTANCE_ID
        with self._lock:
            metrics = self._instances.get(key)
            if metrics is None:
                metrics = RuntimeMetrics()
                self._instances[key] = metrics
            return metrics

    def instance_ids(self) -> list:
        with self._lock:
            return list(self._instances)

    def apply(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        instance_id = payload.get("instance_id") or payload.get("workflow_id") or ""
        return self.for_instance(str(instance_id)).apply(payload)

    def apply_line(self, line: str) -> bool:
        payload = parse_stats_line(line)
        if payload is None:
            return False
        return self.apply(payload)

    def totals(self) -> RuntimeMetrics:
        """run 全体の合算。値が一意に定まらない項目は埋めない（FR-RTO-05）。"""
        total = RuntimeMetrics()
        with self._lock:
            items = list(self._instances.items())

        for instance_id, metrics in items:
            total.input_tokens_total += metrics.input_tokens_total
            total.output_tokens_total += metrics.output_tokens_total
            total.reasoning_tokens_total += metrics.reasoning_tokens_total
            total.cache_read_total += metrics.cache_read_total
            total.cache_write_total += metrics.cache_write_total
            total.assistant_usage_count += metrics.assistant_usage_count
            total.aiu_nano_total += metrics.aiu_nano_total
            total.multiplier_cost_total += metrics.multiplier_cost_total
            total.premium_requests_total += metrics.premium_requests_total
            total.compaction_count += metrics.compaction_count
            total.compaction_tokens_removed += metrics.compaction_tokens_removed
            total.permission_count += metrics.permission_count
            total.model_call_failures += metrics.model_call_failures
            total.tool_successes += metrics.tool_successes
            total.tool_failures += metrics.tool_failures
            total.unknown_kind_count += metrics.unknown_kind_count
            total.unknown_kinds |= metrics.unknown_kinds
            total.running_steps |= metrics.running_steps
            total.step_status.update(metrics.step_status)
            if metrics.last_step_id:
                total.last_step_id = metrics.last_step_id
            if metrics.ttft_first_ms is not None and total.ttft_first_ms is None:
                total.ttft_first_ms = metrics.ttft_first_ms
            if metrics.ttft_last_ms is not None:
                total.ttft_last_ms = metrics.ttft_last_ms
            if metrics.credit_unavailable_reason and not total.credit_unavailable_reason:
                total.credit_unavailable_reason = metrics.credit_unavailable_reason
            _merge_counts(total.tool_counts_by_step, metrics.tool_counts_by_step)
            _merge_counts(total.skill_counts_by_step, metrics.skill_counts_by_step)
            for quota_id, used in metrics._quota_latest.items():
                scoped = f"{instance_id}:{quota_id}"
                total._quota_latest[scoped] = used
                total._quota_baseline[scoped] = metrics._quota_baseline.get(quota_id, used)

        # Context は instance ごとの現在値であり、合算に意味がない。
        # 一意に定まる単一 instance のときだけ引き継ぐ。
        if len(items) == 1:
            only = items[0][1]
            total.context_current = only.context_current
            total.context_limit = only.context_limit
            total.context_msgs = only.context_msgs
        return total


def _merge_counts(target: Dict[str, Dict[str, int]], source: Dict[str, Dict[str, int]]) -> None:
    for step_id, counts in source.items():
        bucket = target.setdefault(step_id, {})
        for name, count in counts.items():
            bucket[name] = bucket.get(name, 0) + count


def format_counts_topn(counts: Dict[str, int], *, top: int = 3, empty: str = "-") -> str:
    """`名前×回数` の Top-N 表記。未取得は `empty`（推定しない）。"""
    if not counts:
        return empty
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    head = items[:top]
    text = ", ".join(f"{name}×{count}" for name, count in head)
    rest = len(items) - len(head)
    return f"{text} +{rest}" if rest > 0 else text


def format_runtime_summary(metrics: "RuntimeMetrics") -> str:
    """FR-RTO-05: 実行時集計の 1 行サマリー。未取得値は `-`。"""
    credit = f"{metrics.aiu_total:.4f} AIU" if metrics.aiu_nano_total > 0 else "-"
    reqs = metrics.display_reqs
    context = (
        f"{metrics.context_current:,}/{metrics.context_limit:,}"
        if metrics.context_limit > 0
        else "-/-"
    )
    return (
        "📊 実行時統計: "
        f"tokens in={metrics.input_tokens_total:,} out={metrics.output_tokens_total:,}"
        f"  ｜  AI Credit {credit}"
        f"  ｜  Reqs {reqs if reqs > 0 else '-'}"
        f"  ｜  Context {context}"
        f"  ｜  tool 失敗 {metrics.tool_failures}"
        f"  ｜  model 失敗 {metrics.model_call_failures}"
    )


# ---------------------------------------------------------------------------
# 永続化（FR-RTO-03 / FR-RTO-04 / FR-RTO-06）
# ---------------------------------------------------------------------------

OBSERVABILITY_DIRNAME = "observability"
DEFAULT_MAX_BYTES = 32 * 1024 * 1024

_ENVELOPE_KEYS = frozenset(
    {"schema_version", "ts", "seq", "pid", "run_id", "workflow_id", "instance_id", "kind", "step"}
)

# 既存 producer が発火するフィールドのうち、状態・時刻・数値・識別子だけを許可する。
_METRIC_KEYS = frozenset(
    {
        "status", "title", "elapsed",
        "base_id", "child_ids",
        "tool_name", "action_name", "success",
        "name", "source",
        "path", "mode",
        "model", "input", "output", "reasoning", "cache_read", "cache_write",
        "inter_token_latency_ms", "ttft_ms",
        "api_call_id", "multiplier_cost", "nano_aiu", "unavailable_reason",
        "quota_id", "used_requests", "entitlement_requests", "remaining_percentage",
        "overage", "is_unlimited_entitlement", "overage_allowed_with_exhausted_quota",
        "usage_allowed_with_exhausted_quota", "reset_date_iso",
        "current", "limit", "msgs", "system", "tool_definitions", "conversation",
        "pre", "post", "removed",
        "count", "threshold",
        "permission_kind", "exception_type",
    }
)

# FR-RTO-08: GitHub target lifecycle だけに許可するキー。他 kind が同名キーを
# 持っても永続化されないよう、kind 限定の allowlist として分離する。
_GITHUB_TARGET_KEYS = frozenset(
    {
        "repo", "issue_number", "pr_number", "branch", "base_branch",
        "created_by_hve", "delete_local_merged_branch",
    }
)

_PERSISTABLE_KEYS = _ENVELOPE_KEYS | _METRIC_KEYS

# 生 SDK ペイロード・env dump は本文を含みうるため、イベントごと保存しない。
_NON_PERSISTED_KINDS = frozenset({"assistant_usage_raw", "debug_env", "assistant_usage_raw_err"})

_PATH_KEYS = frozenset({"path"})

# シェルのコマンド文字列から抽出したトークンには `$p` や `` `$p)) `` のような変数・式が
# 混じる。実パスではないため保存しない（FR-RTO-04 の fail-closed）。
_SHELL_EXPRESSION_CHARS_RE = re.compile(r"[$`'\"()]")


def is_plain_repo_path_token(value: Any) -> bool:
    """シェルの変数・式・引用や括弧を含まない、素のパス表記かを返す。"""
    return isinstance(value, str) and bool(value) and not _SHELL_EXPRESSION_CHARS_RE.search(value)


def _to_repo_relative(value: Any, repo_root: Optional[Path]) -> Optional[str]:
    """リポジトリルート配下へ相対化する。できない場合は None（保存しない）。"""
    if not is_plain_repo_path_token(value):
        return None
    try:
        path = Path(value)
    except (OSError, ValueError):
        return None
    if not path.is_absolute():
        # `src/../../etc` のようなルート外への離脱を正規化して弾く。
        normalized = PurePosixPath(os.path.normpath(path.as_posix()).replace(os.sep, "/"))
        text = normalized.as_posix()
        if text == ".." or text.startswith("../") or normalized.is_absolute():
            return None
        return text
    if repo_root is None:
        return None
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except (OSError, ValueError):
        return None


def sanitize_event(
    payload: Dict[str, Any], repo_root: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """FR-RTO-04: allowlist に載ったキーだけを残した payload を返す。

    保存対象外の kind、または dict でない入力には None を返す。
    """
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind or kind in _NON_PERSISTED_KINDS:
        return None

    root = Path(repo_root).resolve() if repo_root is not None else None
    # FR-RTO-08: GitHub target のキーは当該 kind のときだけ許可する。
    persistable = _PERSISTABLE_KEYS
    if kind == GITHUB_TARGET_KIND:
        persistable = _PERSISTABLE_KEYS | _GITHUB_TARGET_KEYS
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if key not in persistable:
            continue
        if key in _PATH_KEYS:
            relative = _to_repo_relative(value, root)
            if relative is not None:
                clean[key] = relative
            continue
        if key == "child_ids":
            if isinstance(value, list):
                clean[key] = [str(item) for item in value if isinstance(item, str)]
            continue
        clean[key] = value
    return clean


class RuntimeEventRecorder:
    """run-scoped な JSONL 追記器。書き込み失敗は実行へ波及させない（NFR-RTO-03）。"""

    def __init__(
        self,
        work_root: Optional[Path],
        *,
        repo_root: Optional[Path] = None,
        dry_run: bool = False,
        max_bytes: int = DEFAULT_MAX_BYTES,
        warn: Optional[Any] = None,
    ) -> None:
        self.pid = os.getpid()
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self._max_bytes = int(max_bytes)
        self._warn = warn
        self._lock = threading.Lock()
        self._handle: Optional[Any] = None
        self._path: Optional[Path] = None
        self._written_bytes = 0
        self._capped = False
        self._closed = False
        self._enabled = bool(work_root) and not dry_run
        if self._enabled and work_root is not None:
            self._open(Path(work_root))

    @classmethod
    def from_env(
        cls,
        *,
        dry_run: bool = False,
        repo_root: Optional[Path] = None,
        warn: Optional[Any] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> "RuntimeEventRecorder":
        """FR-RTO-03: `HVE_WORK_ROOT` 未設定時は無効化する。"""
        raw = os.environ.get("HVE_WORK_ROOT", "").strip()
        return cls(
            Path(raw) if raw else None,
            repo_root=repo_root if repo_root is not None else Path.cwd(),
            dry_run=dry_run,
            max_bytes=max_bytes,
            warn=warn,
        )

    # -- 状態 -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._closed and self._handle is not None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    # -- 内部 -----------------------------------------------------------

    def _open(self, work_root: Path) -> None:
        try:
            target_dir = work_root / OBSERVABILITY_DIRNAME
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / f"events-{self.pid}.jsonl"
            self._written_bytes = path.stat().st_size if path.exists() else 0
            self._handle = path.open("a", encoding="utf-8", newline="\n")
            self._path = path
        except OSError:
            self._disable()

    def _disable(self) -> None:
        handle, self._handle = self._handle, None
        self._enabled = False
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def _emit_warning(self, message: str) -> None:
        if self._warn is None:
            return
        try:
            self._warn(message)
        except Exception:
            pass

    # -- 記録 -----------------------------------------------------------

    def record(self, payload: Dict[str, Any]) -> bool:
        if not self.enabled or self._capped:
            return False
        clean = sanitize_event(payload, self._repo_root)
        if clean is None:
            return False
        try:
            line = json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n"
        except (TypeError, ValueError):
            return False
        encoded_length = len(line.encode("utf-8"))

        with self._lock:
            if self._handle is None or self._capped:
                return False
            if self._written_bytes + encoded_length > self._max_bytes:
                self._capped = True
                self._emit_warning(
                    f"runtime observability: {self._max_bytes} バイト上限に達したため追記を停止しました"
                    f"（{self._path}）"
                )
                return False
            try:
                self._handle.write(line)
                self._handle.flush()
            except (OSError, ValueError):
                self._disable()
                return False
            self._written_bytes += encoded_length
        return True

    def close(self) -> None:
        with self._lock:
            self._closed = True
            handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def __enter__(self) -> "RuntimeEventRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def read_events(work_root: Path) -> list:
    """run 配下の観測イベントを読み込む。壊れた行は捨てる。

    プロセス内は `seq` により厳密、プロセス間の時刻順序は近似（FR-RTO-03）。
    """
    directory = Path(work_root) / OBSERVABILITY_DIRNAME
    if not directory.is_dir():
        return []
    events: list = []
    for path in sorted(directory.glob("events-*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    events.sort(key=lambda e: (str(e.get("ts") or ""), int(e.get("pid") or 0), int(e.get("seq") or 0)))
    return events


__all__ = [
    "DEFAULT_INSTANCE_ID",
    "DEFAULT_MAX_BYTES",
    "GITHUB_TARGET_KIND",
    "GUI_SESSION_ENV",
    "OBSERVABILITY_DIRNAME",
    "SCHEMA_VERSION",
    "STATS_PREFIX",
    "STATS_STREAM_ENV",
    "KNOWN_KINDS",
    "RuntimeContext",
    "RuntimeEventRecorder",
    "RuntimeMetrics",
    "RuntimeMetricsRegistry",
    "build_event",
    "build_github_target_event",
    "format_counts_topn",
    "format_runtime_summary",
    "format_stats_line",
    "github_target_fields",
    "is_child_process",
    "is_stats_line",
    "make_instance_id",
    "parse_stats_line",
    "read_events",
    "sanitize_event",
]
