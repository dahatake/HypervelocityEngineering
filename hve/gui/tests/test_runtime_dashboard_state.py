"""FR-RTO-01 / FR-RTO-05: GUI が観測イベントを core 実装で解析し instance 単位で集計する。

RED 先行。GUI 側の runtime observability 配線は本テスト作成時点で未実装。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve import runtime_observability as rto  # noqa: E402
from hve.gui.workbench_logger import parse_stats_event  # noqa: E402
from hve.gui.workbench_state import WorkbenchState  # noqa: E402


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="run-1", model="m")


def _line(payload: dict) -> str:
    return rto.format_stats_line(payload)


class TestParserUsesCoreImplementation:
    """FR-MAINT-07: 解析は core 実装へ単一化する。"""

    def test_parse_stats_event_delegates_to_core(self) -> None:
        assert parse_stats_event is rto.parse_stats_line

    def test_envelope_line_is_parsed(self) -> None:
        ctx = rto.RuntimeContext(run_id="r", workflow_id="wf", instance_id="wf#APP-1")
        payload = rto.build_event("step_status", "1", ctx, status="running")
        parsed = parse_stats_event(_line(payload))
        assert parsed is not None
        assert parsed["instance_id"] == "wf#APP-1"
        assert parsed["status"] == "running"


class TestInstanceScopedMetrics:
    """FR-RTO-05: instance 単位で分離し run 単位で合算する。"""

    def test_state_exposes_runtime_registry(self) -> None:
        assert isinstance(_state().runtime_metrics, rto.RuntimeMetricsRegistry)

    def test_events_are_routed_by_instance(self) -> None:
        state = _state()
        ctx_a = rto.RuntimeContext(instance_id="wf#APP-1")
        ctx_b = rto.RuntimeContext(instance_id="wf#APP-2")
        state.apply_runtime_event(rto.build_event("assistant_usage", "1", ctx_a, input=10))
        state.apply_runtime_event(rto.build_event("assistant_usage", "1", ctx_b, input=4))

        assert state.runtime_metrics.for_instance("wf#APP-1").input_tokens_total == 10
        assert state.runtime_metrics.for_instance("wf#APP-2").input_tokens_total == 4
        assert state.runtime_metrics.totals().input_tokens_total == 14

    def test_instance_metrics_helper(self) -> None:
        state = _state()
        ctx = rto.RuntimeContext(instance_id="wf#APP-1")
        state.apply_runtime_event(rto.build_event("tool_invoked", "1", ctx, tool_name="view"))

        metrics = state.instance_metrics("wf#APP-1")
        assert metrics.tool_counts_by_step["1"] == {"view": 1}

    def test_unknown_kind_is_counted(self) -> None:
        state = _state()
        state.apply_runtime_event({"kind": "brand_new", "step": "1"})
        assert state.runtime_metrics.totals().unknown_kind_count == 1


class TestLogPipelineFeedsRegistry:
    """既存のログ取り込み経路から registry へ流れる。"""

    def test_process_log_line_updates_registry(self) -> None:
        from hve.gui.workbench_logger import process_log_line

        state = _state()
        ctx = rto.RuntimeContext(instance_id="wf#APP-1")
        process_log_line(state, _line(rto.build_event("assistant_usage", "1", ctx, input=7)))

        assert state.runtime_metrics.totals().input_tokens_total == 7

    def test_existing_gui_state_still_updated(self) -> None:
        from hve.gui.workbench_logger import process_log_line

        state = _state()
        process_log_line(state, '[hve:stats] {"kind":"assistant_usage","step":"1","input":5,"output":1}')

        assert state.assistant_input_tokens_total == 5
        assert state.runtime_metrics.totals().input_tokens_total == 5
