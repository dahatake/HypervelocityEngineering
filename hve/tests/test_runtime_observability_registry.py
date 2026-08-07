"""FR-RTO-05: instance 単位の分離と run 単位の合算。

RED 先行。`RuntimeMetricsRegistry` と reducer の集計受入ケースは未実装。
"""

from __future__ import annotations

from hve import runtime_observability as rto


def _ctx(instance_id: str) -> rto.RuntimeContext:
    return rto.RuntimeContext(
        run_id="run-1", workflow_id=instance_id.split("#")[0], instance_id=instance_id, pid=1
    )


class TestReducerAggregation:
    """FR-RTO-05: 取得できた値だけを集計する（推定しない）。"""

    def test_assistant_usage_totals(self) -> None:
        m = rto.RuntimeMetrics()
        m.apply({"kind": "assistant_usage", "step": "1", "input": 10, "output": 3, "reasoning": 2})
        m.apply({"kind": "assistant_usage", "step": "1", "input": 5, "output": 1})
        assert m.input_tokens_total == 15
        assert m.output_tokens_total == 4
        assert m.reasoning_tokens_total == 2
        assert m.assistant_usage_count == 2

    def test_usage_credit_dedup_by_api_call_id(self) -> None:
        m = rto.RuntimeMetrics()
        payload = {"kind": "usage_credit", "step": "1", "api_call_id": "a1", "nano_aiu": 2_000_000_000}
        m.apply(payload)
        m.apply(dict(payload))
        assert m.aiu_nano_total == 2_000_000_000
        assert m.aiu_total == 2.0

    def test_quota_delta_uses_first_observation_as_baseline(self) -> None:
        m = rto.RuntimeMetrics()
        m.apply({"kind": "quota_snapshot", "step": "1", "quota_id": "q", "used_requests": 100})
        m.apply({"kind": "quota_snapshot", "step": "1", "quota_id": "q", "used_requests": 107})
        assert m.quota_used_delta_total == 7
        assert m.display_reqs == 7

    def test_display_reqs_falls_back_to_usage_count(self) -> None:
        m = rto.RuntimeMetrics()
        m.apply({"kind": "assistant_usage", "step": "1", "input": 1})
        assert m.display_reqs == 1

    def test_tool_and_skill_counts_follow_running_step(self) -> None:
        m = rto.RuntimeMetrics()
        m.apply({"kind": "step_status", "step": "1", "status": "running"})
        m.apply({"kind": "tool_invoked", "step": "1", "tool_name": "view"})
        m.apply({"kind": "tool_invoked", "step": "1", "tool_name": "view"})
        m.apply({"kind": "skill_invoked", "step": "1", "name": "code-query"})
        assert m.current_tool_counts() == {"view": 2}
        assert m.current_skill_counts() == {"code-query": 1}

    def test_parallel_steps_merge_counts(self) -> None:
        m = rto.RuntimeMetrics()
        m.apply({"kind": "step_status", "step": "1", "status": "running"})
        m.apply({"kind": "step_status", "step": "2", "status": "running"})
        m.apply({"kind": "tool_invoked", "step": "1", "tool_name": "view"})
        m.apply({"kind": "tool_invoked", "step": "2", "tool_name": "edit"})
        assert m.current_tool_counts() == {"view": 1, "edit": 1}


class TestRegistryInstanceIsolation:
    """FR-RTO-05: instance 単位で分離し run 単位で合算する。"""

    def test_events_route_by_instance_id(self) -> None:
        reg = rto.RuntimeMetricsRegistry()
        reg.apply(rto.build_event("assistant_usage", "1", _ctx("wf#APP-1"), input=10))
        reg.apply(rto.build_event("assistant_usage", "1", _ctx("wf#APP-2"), input=4))

        assert reg.for_instance("wf#APP-1").input_tokens_total == 10
        assert reg.for_instance("wf#APP-2").input_tokens_total == 4
        assert sorted(reg.instance_ids()) == ["wf#APP-1", "wf#APP-2"]

    def test_tool_counts_do_not_leak_between_instances(self) -> None:
        reg = rto.RuntimeMetricsRegistry()
        reg.apply(rto.build_event("step_status", "1", _ctx("wf#APP-1"), status="running"))
        reg.apply(rto.build_event("tool_invoked", "1", _ctx("wf#APP-1"), tool_name="view"))
        assert reg.for_instance("wf#APP-2").current_tool_counts() == {}

    def test_totals_aggregate_across_instances(self) -> None:
        reg = rto.RuntimeMetricsRegistry()
        reg.apply(rto.build_event("assistant_usage", "1", _ctx("wf#APP-1"), input=10, output=1))
        reg.apply(rto.build_event("assistant_usage", "1", _ctx("wf#APP-2"), input=4, output=2))
        reg.apply(rto.build_event("usage_credit", "1", _ctx("wf#APP-1"), api_call_id="a", nano_aiu=1_000_000_000))

        totals = reg.totals()
        assert totals.input_tokens_total == 14
        assert totals.output_tokens_total == 3
        assert totals.aiu_nano_total == 1_000_000_000

    def test_events_without_instance_id_use_default_bucket(self) -> None:
        reg = rto.RuntimeMetricsRegistry()
        reg.apply({"kind": "assistant_usage", "step": "1", "input": 7})
        assert reg.totals().input_tokens_total == 7
        assert reg.instance_ids() == [rto.DEFAULT_INSTANCE_ID]

    def test_unknown_kind_counted_in_totals(self) -> None:
        reg = rto.RuntimeMetricsRegistry()
        reg.apply(rto.build_event("brand_new_kind", "1", _ctx("wf")))
        assert reg.totals().unknown_kind_count == 1
