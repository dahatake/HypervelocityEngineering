"""FR-RTO-05: CUI Workbench が実行時集計を保持し、Footer / `/stats` へ供給する。

RED 先行。`WorkbenchState.set_runtime_metrics` / `metrics_snapshot` は未実装。
"""

from __future__ import annotations

from hve import runtime_observability as rto
from hve.workbench.controller import WorkbenchController
from hve.workbench.state import StepView, WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(
        workflow_id="asdw-web",
        run_id="run-1",
        model="claude-opus-4.7",
        steps=[StepView(id="1", title="設計")],
    )


def _registry_with_events() -> rto.RuntimeMetricsRegistry:
    registry = rto.RuntimeMetricsRegistry()
    registry.apply({"kind": "step_status", "step": "1", "status": "running"})
    registry.apply({"kind": "assistant_usage", "step": "1", "input": 120, "output": 30})
    registry.apply({"kind": "tool_invoked", "step": "1", "tool_name": "view"})
    registry.apply({"kind": "skill_invoked", "step": "1", "name": "code-query"})
    registry.apply(
        {"kind": "usage_credit", "step": "1", "api_call_id": "a1", "nano_aiu": 1_500_000_000}
    )
    return registry


class TestStateHoldsMetrics:
    def test_defaults_to_none(self) -> None:
        assert _state().runtime_metrics is None

    def test_snapshot_is_none_when_not_attached(self) -> None:
        assert _state().metrics_snapshot() is None

    def test_snapshot_exposes_totals(self) -> None:
        state = _state()
        state.set_runtime_metrics(_registry_with_events())

        snapshot = state.metrics_snapshot()
        assert snapshot is not None
        assert snapshot.input_tokens_total == 120
        assert snapshot.output_tokens_total == 30
        assert snapshot.aiu_total == 1.5
        assert snapshot.current_tool_counts() == {"view": 1}
        assert snapshot.current_skill_counts() == {"code-query": 1}

    def test_snapshot_survives_broken_registry(self) -> None:
        class _Broken:
            def totals(self):
                raise RuntimeError("boom")

        state = _state()
        state.set_runtime_metrics(_Broken())
        assert state.metrics_snapshot() is None


class TestControllerWiring:
    def test_controller_attaches_metrics_to_state(self) -> None:
        controller = WorkbenchController(_state())
        registry = _registry_with_events()
        controller.set_runtime_metrics(registry)

        assert controller.state.runtime_metrics is registry
        assert controller.state.metrics_snapshot().input_tokens_total == 120


class TestFooterRendering:
    """FR-RTO-05: Footer は同一集計を表示し、未取得値は `-` にする。"""

    def _plain(self, state: WorkbenchState) -> str:
        from hve.workbench.layout import render_footer

        return render_footer(state).plain

    def test_without_metrics_keeps_existing_segments(self) -> None:
        text = self._plain(_state())
        assert "Context:" in text
        assert "model:" in text
        assert "elapsed:" in text

    def test_shows_tokens_credit_and_activity(self) -> None:
        state = _state()
        state.set_runtime_metrics(_registry_with_events())
        text = self._plain(state)

        assert "tokens: in 120 / out 30" in text
        assert "1.5000 AIU" in text
        assert "view×1" in text
        assert "code-query×1" in text

    def test_unavailable_credit_is_dash(self) -> None:
        registry = rto.RuntimeMetricsRegistry()
        registry.apply({"kind": "step_status", "step": "1", "status": "running"})
        state = _state()
        state.set_runtime_metrics(registry)
        text = self._plain(state)

        assert "AI Credit: -" in text
        assert "Tools: -" in text
        assert "Skills: -" in text

    def test_reqs_uses_quota_delta(self) -> None:
        registry = rto.RuntimeMetricsRegistry()
        registry.apply({"kind": "quota_snapshot", "step": "1", "quota_id": "q", "used_requests": 10})
        registry.apply({"kind": "quota_snapshot", "step": "1", "quota_id": "q", "used_requests": 13})
        state = _state()
        state.set_runtime_metrics(registry)

        assert "Reqs: 3" in self._plain(state)


class TestStatsCommand:
    """FR-RTO-05: `/stats` で詳細スナップショットを表示する。"""

    def _messages(self, controller: WorkbenchController) -> str:
        return "\n".join(a.message for a in controller.state.user_actions)

    def test_help_lists_stats_command(self) -> None:
        controller = WorkbenchController(_state())
        controller._dispatch_command("/help")
        assert "/stats" in self._messages(controller)

    def test_stats_reports_snapshot(self) -> None:
        controller = WorkbenchController(_state())
        controller.set_runtime_metrics(_registry_with_events())
        controller._dispatch_command("/stats")

        text = self._messages(controller)
        assert "tokens in=120" in text
        assert "out=30" in text
        assert "1.5000 AIU" in text
        assert "view×1" in text

    def test_stats_without_metrics_reports_unavailable(self) -> None:
        controller = WorkbenchController(_state())
        controller._dispatch_command("/stats")

        assert "未取得" in self._messages(controller)

    def test_unknown_command_still_warns(self) -> None:
        controller = WorkbenchController(_state())
        controller._dispatch_command("/nope")

        assert "unknown command" in self._messages(controller)
