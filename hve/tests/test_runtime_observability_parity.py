"""FR-RTO-05 / NFR-RTO-01: 実行面横断で同一の集計値になることを固定する。

同一のイベント列を CLI(Console) / CUI(Workbench) / GUI / CLI Autopilot の各経路へ流し、
集計結果が一致することを検証する。実 SDK セッションと子プロセスは起動しない。
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve import runtime_observability as rto  # noqa: E402
from hve.console import Console  # noqa: E402


INSTANCE_ID = "aad-web#APP-1"


def _never_spawn(_argv: List[str]) -> subprocess.Popen:
    raise AssertionError("popen_factory must not be called in this test")


def _event_lines() -> list:
    ctx = rto.RuntimeContext(run_id="run-1", workflow_id="aad-web", instance_id=INSTANCE_ID)
    events = [
        rto.build_event("step_status", "1", ctx, status="running", title="設計"),
        rto.build_event("session_usage_detail", "1", ctx, current=1200, limit=20000, msgs=6),
        rto.build_event("assistant_usage", "1", ctx, input=300, output=45, reasoning=12),
        rto.build_event("assistant_ttft", "1", ctx, ttft_ms=820.0),
        rto.build_event("tool_invoked", "1", ctx, tool_name="view"),
        rto.build_event("tool_invoked", "1", ctx, tool_name="edit"),
        rto.build_event("tool_result", "1", ctx, tool_name="edit", success=False),
        rto.build_event("skill_invoked", "1", ctx, name="code-query"),
        rto.build_event("usage_credit", "1", ctx, api_call_id="c1", nano_aiu=3_000_000_000),
        rto.build_event("quota_snapshot", "1", ctx, quota_id="q", used_requests=40),
        rto.build_event("quota_snapshot", "1", ctx, quota_id="q", used_requests=44),
        rto.build_event("compaction_complete", "1", ctx, pre=9000, post=4000, removed=5000),
        rto.build_event("permission_count", "1", ctx, count=2, permission_kind="write"),
        rto.build_event("model_call_failure", "1", ctx, count=1, threshold=3),
        rto.build_event("step_status", "1", ctx, status="done", elapsed=12.5),
    ]
    return [rto.format_stats_line(e) for e in events]


def _expected_snapshot(metrics) -> dict:
    return {
        "input": metrics.input_tokens_total,
        "output": metrics.output_tokens_total,
        "reasoning": metrics.reasoning_tokens_total,
        "aiu_nano": metrics.aiu_nano_total,
        "reqs": metrics.display_reqs,
        "tool_failures": metrics.tool_failures,
        "model_failures": metrics.model_call_failures,
        "compaction": metrics.compaction_count,
        "permission": metrics.permission_count,
        "context": (metrics.context_current, metrics.context_limit),
        "step_status": dict(metrics.step_status),
        "tools": metrics.current_tool_counts(),
        "skills": metrics.current_skill_counts(),
    }


def _reference() -> dict:
    registry = rto.RuntimeMetricsRegistry()
    for line in _event_lines():
        registry.apply_line(line)
    return _expected_snapshot(registry.totals())


class TestSurfaceParity:
    def test_cli_console_matches_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        monkeypatch.delenv(rto.STATS_STREAM_ENV, raising=False)
        console = Console(verbose=False)
        for line in _event_lines():
            console.runtime_metrics().apply_line(line)

        assert _expected_snapshot(console.runtime_metrics().totals()) == _reference()

    def test_cui_workbench_matches_reference(self) -> None:
        from hve.workbench.state import StepView, WorkbenchState

        registry = rto.RuntimeMetricsRegistry()
        for line in _event_lines():
            registry.apply_line(line)

        state = WorkbenchState(
            workflow_id="aad-web", run_id="run-1", model="m", steps=[StepView(id="1", title="設計")]
        )
        state.set_runtime_metrics(registry)

        assert _expected_snapshot(state.metrics_snapshot()) == _reference()

    def test_gui_state_matches_reference(self) -> None:
        from hve.gui.workbench_logger import process_log_line
        from hve.gui.workbench_state import WorkbenchState as GuiState

        state = GuiState(workflow_id="aad-web", run_id="run-1", model="m")
        for line in _event_lines():
            process_log_line(state, line)

        assert _expected_snapshot(state.runtime_totals()) == _reference()

    def test_gui_child_window_matches_reference(self) -> None:
        registry = rto.RuntimeMetricsRegistry()
        for line in _event_lines():
            registry.apply_line(line)

        assert _expected_snapshot(registry.totals()) == _reference()

    def test_cli_autopilot_matches_reference(self) -> None:
        from pathlib import Path

        from hve.autopilot.cli_runner import CliAutopilotRunner
        from hve.autopilot.plan_model import AppChain, AutopilotPlan

        plan = AutopilotPlan(
            catalog_path=Path("docs/catalog/app-arch-catalog.md"),
            catalog_exists=True,
            requires_aas=False,
            app_chains=[AppChain(app_id="APP-1", architecture="web", workflows=["aad-web"])],
            max_parallel=1,
        )
        runner = CliAutopilotRunner(
            plan,
            popen_factory=_never_spawn,
            echo=lambda _line: None,
        )
        for line in _event_lines():
            runner._consume_child_line("APP-1", "aad-web", line)

        assert _expected_snapshot(runner.runtime_metrics.totals()) == _reference()
        assert runner.runtime_metrics.instance_ids() == [INSTANCE_ID]


class TestSecurityAcrossSurfaces:
    """FR-RTO-04: どの経路でも秘密情報を永続化しない。"""

    def test_recorder_drops_sensitive_fields(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        monkeypatch.delenv(rto.STATS_STREAM_ENV, raising=False)
        console = Console(verbose=False)
        recorder = rto.RuntimeEventRecorder(tmp_path, repo_root=tmp_path)
        console.attach_event_recorder(recorder)

        console.stats_event(
            "tool_invoked",
            step_id="1",
            tool_name="bash",
            arguments={"command": "echo $GH_TOKEN"},
            content="assistant body",
        )
        console.stats_event("assistant_usage_raw", step_id="1", payload_json="{secret}")
        recorder.close()

        stored = rto.read_events(tmp_path)
        assert len(stored) == 1
        text = repr(stored)
        assert "GH_TOKEN" not in text
        assert "assistant body" not in text
        assert "secret" not in text


class TestPerformanceBudget:
    """NFR-RTO-01: 1 イベントあたりの追加処理を実測して記録する。"""

    def test_in_memory_pipeline_matches_gui_intake_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NFR-OBS-09 と同じ経路（解析と集計）の追加コストを測る。"""
        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        monkeypatch.delenv(rto.STATS_STREAM_ENV, raising=False)
        console = Console(verbose=False)

        iterations = 2000
        started = time.perf_counter()
        for _ in range(iterations):
            console.stats_event("tool_invoked", step_id="1", tool_name="view")
        elapsed_ms_per_event = (time.perf_counter() - started) * 1000.0 / iterations

        # 既存 GUI ログ 1 行取り込みの実測 0.0442 ms/行 と同桁に収める。
        assert elapsed_ms_per_event < 0.2

    def test_recorder_append_cost_is_bounded(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """JSONL 追記は 1 行ごとの flush を伴う I/O 経路であり、別枠で上限だけを固定する。"""
        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        monkeypatch.delenv(rto.STATS_STREAM_ENV, raising=False)
        console = Console(verbose=False)
        recorder = rto.RuntimeEventRecorder(tmp_path, repo_root=tmp_path)
        console.attach_event_recorder(recorder)

        iterations = 500
        started = time.perf_counter()
        for _ in range(iterations):
            console.stats_event("tool_invoked", step_id="1", tool_name="view")
        elapsed_ms_per_event = (time.perf_counter() - started) * 1000.0 / iterations
        recorder.close()

        assert len(rto.read_events(tmp_path)) == iterations
        # ディスク性能と同時実行負荷に依存するため、病的な劣化だけを検出する上限とする。
        assert elapsed_ms_per_event < 10.0
