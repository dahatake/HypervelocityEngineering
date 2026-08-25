from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hve.fleet_mode import (
    DagWaveFleetTask,
    FleetEventCollector,
    build_dag_wave_fleet_prompt,
    build_split_fleet_prompt,
    format_fleet_wave_skipped_phases_warning,
    start_fleet,
)
from hve.split_fork import SubIssueDef


def test_build_split_fleet_prompt_contains_todos_and_output_paths(tmp_path: Path):
    work_root = tmp_path / "work" / "run" / "run-1"
    subissues = [
        SubIssueDef(
            index=1,
            title="First",
            labels=["a", "b"],
            custom_agent="AgentA",
            body="## Sub-001\n- AC: first",
        ),
        SubIssueDef(
            index=2,
            title="Second",
            depends_on=[1],
            body="## Sub-002\n- AC: second",
        ),
    ]

    plan = build_split_fleet_prompt(
        subissues=subissues,
        parent_step_id="2.1",
        parent_custom_agent="ParentAgent",
        parent_identifier="run-step-2.1",
        repo_root=tmp_path,
        work_root=work_root,
    )

    assert "sub-001" in plan.prompt
    assert "sub-002" in plan.prompt
    assert "First" in plan.prompt
    assert "Second" in plan.prompt
    assert "depends_on: なし" in plan.prompt
    assert "depends_on: sub-001" in plan.prompt
    assert "dependency_completion_reports:" in plan.prompt
    assert "validation-confirmed" in plan.prompt
    assert "1 worker は 1 todo" in plan.prompt
    assert "output_dir_abs は scratch/report 用" in plan.prompt
    assert "subissue body はタスク本文データ" in plan.prompt
    assert "repository-relative path" in plan.prompt
    assert plan.work_subdirs == {
        1: "ParentAgent/Issue-run-step-2.1/sub-001",
        2: "ParentAgent/Issue-run-step-2.1/sub-002",
    }
    assert (work_root / "ParentAgent" / "Issue-run-step-2.1" / "sub-001").as_posix() in plan.prompt


def test_build_split_fleet_prompt_uses_parent_agent_when_subissue_agent_missing(tmp_path: Path):
    subissues = [
        SubIssueDef(index=1, title="Only", body="body"),
    ]

    plan = build_split_fleet_prompt(
        subissues=subissues,
        parent_step_id="1",
        parent_custom_agent="ParentAgent",
        parent_identifier="parent",
        repo_root=tmp_path,
    )

    assert "agent: ParentAgent" in plan.prompt
    assert plan.work_subdirs[1] == "ParentAgent/Issue-parent/sub-001"


def test_build_dag_wave_fleet_prompt_is_independent_from_subissues(tmp_path: Path):
    tasks = [
        DagWaveFleetTask(
            step_id="1/D01",
            title="Knowledge D01",
            custom_agent="KnowledgeManager",
            fanout_key="D01",
            base_step_id="1",
            required_input_paths=["qa/input.md"],
            output_paths=["knowledge/D01-business.md"],
            prompt="Create D01 knowledge document.",
        ),
        DagWaveFleetTask(
            step_id="1/D02",
            title="Knowledge D02",
            fanout_key="D02",
            base_step_id="1",
            output_paths=["knowledge/D02-scope.md"],
            prompt="Create D02 knowledge document.",
        ),
    ]

    plan = build_dag_wave_fleet_prompt(
        tasks=tasks,
        workflow_id="akm",
        wave_index=1,
        repo_root=tmp_path,
    )

    assert "workflow-level DAG wave" in plan.prompt
    assert "SPLIT_REQUIRED / subissues.md / GitHub Sub-Issue 作成ではありません" in plan.prompt
    assert "Step.1/D01" in plan.prompt
    assert "Step.1/D02" in plan.prompt
    assert "fanout_key: D01" in plan.prompt
    assert "base_step_id: 1" in plan.prompt
    assert "knowledge/D01-business.md" in plan.prompt
    assert "qa/input.md" in plan.prompt
    assert "Create D02 knowledge document." in plan.prompt
    assert tuple(plan.task_step_ids) == ("1/D01", "1/D02")


def test_build_dag_wave_fleet_prompt_uses_work_root_for_report_dir_abs(tmp_path: Path):
    repo_root = tmp_path / "repo"
    work_root = repo_root / "work" / "run" / "gui-run"
    task = DagWaveFleetTask(
        step_id="2.1",
        title="KPI/OKR",
        prompt="Create KPI/OKR document.",
    )

    plan = build_dag_wave_fleet_prompt(
        tasks=[task],
        workflow_id="ard",
        wave_index=1,
        repo_root=repo_root,
        run_id="run-1",
        work_root=work_root,
    )

    report_dir = plan.report_dirs["2.1"]
    expected_report = (
        work_root / report_dir / "completion-report.md"
    ).resolve().as_posix()
    legacy_report = (
        repo_root / "work" / report_dir / "completion-report.md"
    ).resolve().as_posix()

    assert report_dir == "fleet/run-1/wave-001/2.1"
    assert expected_report in plan.prompt
    assert legacy_report not in plan.prompt


def test_build_dag_wave_fleet_prompt_rejects_empty_tasks(tmp_path: Path):
    with pytest.raises(ValueError, match="at least one"):
        build_dag_wave_fleet_prompt(
            tasks=[],
            workflow_id="akm",
            wave_index=1,
            repo_root=tmp_path,
        )


def test_build_dag_wave_fleet_prompt_rejects_duplicate_step_ids(tmp_path: Path):
    tasks = [
        DagWaveFleetTask(step_id="1/D01", title="A", prompt="a"),
        DagWaveFleetTask(step_id="1/D01", title="B", prompt="b"),
    ]

    with pytest.raises(ValueError, match="duplicate.*1/D01"):
        build_dag_wave_fleet_prompt(
            tasks=tasks,
            workflow_id="akm",
            wave_index=1,
            repo_root=tmp_path,
        )


def test_build_dag_wave_fleet_prompt_rejects_report_dir_collision(tmp_path: Path):
    tasks = [
        DagWaveFleetTask(step_id="a/b", title="A", prompt="a"),
        DagWaveFleetTask(step_id="a:b", title="B", prompt="b"),
    ]

    with pytest.raises(ValueError, match="report_dir collision"):
        build_dag_wave_fleet_prompt(
            tasks=tasks,
            workflow_id="akm",
            wave_index=1,
            repo_root=tmp_path,
        )


def test_build_dag_wave_fleet_prompt_sanitizes_run_id_in_report_dirs(tmp_path: Path):
    plan = build_dag_wave_fleet_prompt(
        tasks=[DagWaveFleetTask(step_id="1/D01", title="A", prompt="a")],
        workflow_id="akm",
        wave_index=1,
        repo_root=tmp_path,
        run_id="../bad\\run",
    )

    report_dir = plan.report_dirs["1/D01"]
    assert ".." not in report_dir
    assert "\\" not in report_dir
    assert report_dir.startswith("fleet/bad-run/wave-001/")


@pytest.mark.parametrize(
    "bad_path",
    ["/tmp/out.md", "C:/tmp/out.md", "../out.md", "docs/../out.md", ""],
)
def test_build_dag_wave_fleet_prompt_rejects_unsafe_paths(tmp_path: Path, bad_path: str):
    tasks = [
        DagWaveFleetTask(
            step_id="1/D01",
            title="A",
            prompt="a",
            output_paths=[bad_path],
        ),
    ]

    with pytest.raises(ValueError):
        build_dag_wave_fleet_prompt(
            tasks=tasks,
            workflow_id="akm",
            wave_index=1,
            repo_root=tmp_path,
        )


def test_build_dag_wave_fleet_prompt_normalizes_windows_separators(tmp_path: Path):
    tasks = [
        DagWaveFleetTask(
            step_id="1/D01",
            title="A",
            prompt="a",
            output_paths=[r"knowledge\D01.md"],
            required_input_paths=[r"qa\input.md"],
        ),
    ]

    plan = build_dag_wave_fleet_prompt(
        tasks=tasks,
        workflow_id="akm",
        wave_index=1,
        repo_root=tmp_path,
    )

    assert "knowledge/D01.md" in plan.prompt
    assert "qa/input.md" in plan.prompt


class _FakeFleetRpc:
    def __init__(self, *, started=True, error: Exception | None = None):
        self.started = started
        self.error = error
        self.requests = []

    async def start(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(started=self.started)


class _FakeSession:
    def __init__(self, fleet_rpc: _FakeFleetRpc):
        self.rpc = SimpleNamespace(fleet=fleet_rpc)


@pytest.mark.anyio
async def test_start_fleet_calls_rpc_with_fleet_start_request():
    fleet_rpc = _FakeFleetRpc(started=True)
    session = _FakeSession(fleet_rpc)

    outcome = await start_fleet(session, "hello fleet")

    assert outcome.started is True
    assert outcome.reason == ""
    assert len(fleet_rpc.requests) == 1
    assert fleet_rpc.requests[0].prompt == "hello fleet"


@pytest.mark.anyio
async def test_start_fleet_reports_started_false():
    fleet_rpc = _FakeFleetRpc(started=False)

    outcome = await start_fleet(_FakeSession(fleet_rpc), "prompt")

    assert outcome.started is False
    assert "started=False" in outcome.reason


@pytest.mark.anyio
async def test_start_fleet_reports_rpc_exception():
    fleet_rpc = _FakeFleetRpc(error=RuntimeError("boom"))

    outcome = await start_fleet(_FakeSession(fleet_rpc), "prompt")
    assert outcome.started is False
    assert "RuntimeError" in outcome.reason
    assert "boom" in outcome.reason


def test_fleet_event_collector_tracks_started_completed_and_failed():
    collector = FleetEventCollector()

    collector.handle_event(SimpleNamespace(
        type="subagent.started",
        data=SimpleNamespace(
            tool_call_id="tool-1",
            agent_display_name="Worker A",
        ),
    ))
    assert collector.running == {"tool-1": "Worker A"}

    collector.handle_event(SimpleNamespace(
        type="subagent.completed",
        data=SimpleNamespace(
            tool_call_id="tool-1",
            agent_display_name="Worker A",
        ),
    ))
    assert collector.running == {}
    assert collector.completed == {"tool-1": "Worker A"}

    collector.handle_event(SimpleNamespace(
        type="subagent.failed",
        data=SimpleNamespace(
            tool_call_id="tool-2",
            agent_display_name="Worker B",
            error="boom",
        ),
    ))
    assert collector.has_failed is True
    assert collector.failed == {"tool-2": "Worker B: boom"}


def test_fleet_event_collector_accepts_enum_like_event_type_and_camel_case_data():
    collector = FleetEventCollector()
    event_type = SimpleNamespace(value="subagent.started")

    collector.handle_event(SimpleNamespace(
        type=event_type,
        data=SimpleNamespace(
            toolCallId="tool-1",
            agentDisplayName="Worker A",
        ),
    ))

    assert collector.running == {"tool-1": "Worker A"}


def test_fleet_event_collector_keeps_terminal_states_exclusive():
    collector = FleetEventCollector()

    collector.handle_event(SimpleNamespace(
        type="subagent.completed",
        data=SimpleNamespace(tool_call_id="tool-1", agent_display_name="Worker A"),
    ))
    collector.handle_event(SimpleNamespace(
        type="subagent.failed",
        data=SimpleNamespace(tool_call_id="tool-1", agent_display_name="Worker A", error="late failure"),
    ))

    assert collector.running == {}
    assert collector.completed == {}
    assert collector.failed == {"tool-1": "Worker A: late failure"}


@pytest.fixture(autouse=True)
def _reset_emit_step_context():
    """各テストの前後で行帰属 ContextVar を初期化し、テスト間汚染を防ぐ。"""
    from hve.console import _CURRENT_EMIT_STEP_ID

    token = _CURRENT_EMIT_STEP_ID.set(None)
    try:
        yield
    finally:
        _CURRENT_EMIT_STEP_ID.reset(token)


class _FakeConsole:
    """FleetEventCollector の転送先 console をスタブし、呼び出しを記録する。"""

    def __init__(self, show_stream: bool = False) -> None:
        self.show_stream = show_stream
        self.calls: list = []
        self.ctx_at_call: list = []
        self.stats_events: list = []

    def _record(self, name: str, *args: object) -> None:
        # 呼び出し時点の行帰属 ContextVar をキャプチャする（帰属マーカー検証用）。
        from hve.console import _CURRENT_EMIT_STEP_ID

        self.ctx_at_call.append(_CURRENT_EMIT_STEP_ID.get())
        self.calls.append((name, *args))

    def subagent_started(self, step_id: str, name: str) -> None:
        self._record("subagent_started", step_id, name)

    def subagent_completed(self, step_id: str, name: str) -> None:
        self._record("subagent_completed", step_id, name)

    def subagent_failed(self, step_id: str, name: str, error: str = "") -> None:
        self._record("subagent_failed", step_id, name, error)

    def subagent_selected(self, step_id: str, name: str) -> None:
        self._record("subagent_selected", step_id, name)

    def tool(self, tool_name: str, step_id: str = "", args_summary: str = "") -> None:
        self._record("tool", tool_name, step_id)

    def final_message(self, step_id: str, content: str) -> None:
        self._record("final_message", step_id, content)

    def stream_token(self, step_id: str, token: str) -> None:
        self._record("stream_token", step_id, token)

    def stats_event(self, kind: str, step_id: str = "", **fields: object) -> None:
        self.stats_events.append((kind, step_id, fields))


def _event(etype: str, **data: object) -> SimpleNamespace:
    return SimpleNamespace(type=etype, data=SimpleNamespace(**data))


def test_collector_without_console_ignores_work_events():
    # 後方互換: console 未設定時は lifecycle のみ追跡し、作業イベントは無視（例外も無し）。
    collector = FleetEventCollector()
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))
    collector.handle_event(_event("assistant.message", parent_tool_call_id="t1", content="hi"))
    collector.handle_event(_event("assistant.message_delta", parent_tool_call_id="t1", delta_content="x"))
    assert collector.running == {"t1": "Worker A"}
    assert collector.completed == {}
    assert collector.failed == {}


def test_collector_forwards_lifecycle_to_console():
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("subagent.completed", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("subagent.failed", tool_call_id="t2", agent_display_name="Worker B", error="boom"))
    assert ("subagent_started", "Worker A", "Worker A") in console.calls
    assert ("subagent_completed", "Worker A", "Worker A") in console.calls
    assert ("subagent_failed", "Worker B", "Worker B", "boom") in console.calls


def test_collector_forwards_subagent_selected():
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.selected", agent_display_name="Worker A"))
    assert ("subagent_selected", "Worker A", "Worker A") in console.calls


def test_collector_forwards_tool_with_worker_label():
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))
    assert ("tool", "edit_file", "Worker A") in console.calls


def test_collector_tool_label_falls_back_to_wave_when_parent_unknown():
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=3)
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="unknown", tool_name="bash"))
    assert ("tool", "bash", "fleet-w3") in console.calls


def test_collector_forwards_assistant_message_when_not_streaming():
    console = _FakeConsole(show_stream=False)
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("assistant.message", parent_tool_call_id="t1", content="done"))
    assert ("final_message", "Worker A", "done") in console.calls


def test_collector_skips_final_message_when_streaming():
    # show_stream=True 時は delta を逐次出力するため、final_message の全文再表示はしない。
    console = _FakeConsole(show_stream=True)
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("assistant.message", parent_tool_call_id="t1", content="done"))
    assert not any(call[0] == "final_message" for call in console.calls)


def test_collector_forwards_message_delta_as_stream_token():
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("assistant.message_delta", parent_tool_call_id="t1", delta_content="tok"))
    assert ("stream_token", "Worker A", "tok") in console.calls


def test_collector_sets_and_restores_attribution_context():
    # 転送中だけ ContextVar が worker ラベルになり、転送後は元（None）へ復元されること。
    from hve.console import _CURRENT_EMIT_STEP_ID

    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))
    assert "Worker A" in console.ctx_at_call
    assert _CURRENT_EMIT_STEP_ID.get() is None


def test_collector_forwarding_does_not_break_on_console_method_error():
    # console メソッドが例外を投げても lifecycle 追跡は壊れない（転送は握り潰す）。
    class _BoomConsole(_FakeConsole):
        def __init__(self) -> None:
            super().__init__()
            self.raised = False

        def subagent_started(self, step_id: str, name: str) -> None:
            self.raised = True
            raise RuntimeError("boom")

    console = _BoomConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    assert console.raised  # 転送は実際に試みられた（vacuous pass 防止）
    assert collector.running == {"t1": "Worker A"}  # 例外でも lifecycle は壊れない


def test_collector_resolves_label_per_worker():
    # 複数 worker 同時実行時、各作業イベントのラベルが parent_tool_call_id ごとに
    # 正しく逆引きされること（先頭値への取り違え退行を検出する）。
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("subagent.started", tool_call_id="t2", agent_display_name="Worker B"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t2", tool_name="bash"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))
    assert ("tool", "bash", "Worker B") in console.calls
    assert ("tool", "edit_file", "Worker A") in console.calls


def test_collector_restores_attribution_context_on_console_error():
    # 作業イベントの転送中に console が例外を投げても、ContextVar は finally で
    # 必ず復元される（リークしない）。
    from hve.console import _CURRENT_EMIT_STEP_ID

    class _BoomConsole(_FakeConsole):
        def tool(self, tool_name: str, step_id: str = "", args_summary: str = "") -> None:
            raise RuntimeError("boom")

    collector = FleetEventCollector(console=_BoomConsole(), wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))
    assert _CURRENT_EMIT_STEP_ID.get() is None


def test_collector_streaming_shows_delta_and_suppresses_final_message():
    # show_stream=True 時は delta→stream_token が出つつ message→final_message は抑制され
    # （本文の二重表示防止）、という相互作用を併検する。
    console = _FakeConsole(show_stream=True)
    collector = FleetEventCollector(console=console, wave_index=1)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("assistant.message_delta", parent_tool_call_id="t1", delta_content="to"))
    collector.handle_event(_event("assistant.message", parent_tool_call_id="t1", content="token"))
    assert ("stream_token", "Worker A", "to") in console.calls
    assert not any(call[0] == "final_message" for call in console.calls)


# ----------------------------------------------------------------------
# FR-RTO-07: Fleet wave の AI Credit 回収
# ----------------------------------------------------------------------


class _UsageData(SimpleNamespace):
    """SDK ``AssistantUsageData`` 相当のスタブ（``to_dict()`` を持つ）。"""

    def __init__(self, *, copilot_usage: object = None, **attrs: object) -> None:
        super().__init__(**attrs)
        self._copilot_usage_dict = copilot_usage

    def to_dict(self) -> dict:
        return {} if self._copilot_usage_dict is None else {"copilotUsage": self._copilot_usage_dict}


def test_collector_emits_usage_credit_from_assistant_usage():
    """Fleet セッションの ``assistant.usage`` から ``usage_credit`` を発火する。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2)
    collector.handle_event(SimpleNamespace(
        type="assistant.usage",
        data=_UsageData(
            copilot_usage={"totalNanoAiu": 1_500_000_000},
            api_call_id="api-1",
            cost=0.5,
            model="claude-opus-5",
        ),
    ))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    _kind, _step, fields = credits[0]
    assert fields["nano_aiu"] == 1_500_000_000
    assert fields["api_call_id"] == "api-1"
    assert fields["multiplier_cost"] == 0.5
    assert fields["model"] == "claude-opus-5"


def test_collector_usage_credit_uses_empty_step_id():
    """Fleet 発火の ``usage_credit`` は Wave 内のいずれかの Step へ割り当ててはならない。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(SimpleNamespace(
        type="assistant.usage",
        data=_UsageData(
            copilot_usage={"totalNanoAiu": 2_000_000_000},
            api_call_id="api-2",
            model="claude-opus-5",
            parent_tool_call_id="t1",
        ),
    ))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    assert credits[0][1] == "", "Fleet worker → step_id の対応は解決不能なため空文字でなければならない"


def test_collector_does_not_emit_tool_invoked_for_unresolved_worker():
    """Step を解決できない Fleet worker の tool を誤帰属させない（``tool_invoked`` を出さない）。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_name="edit_file"))

    assert not any(ev[0] == "tool_invoked" for ev in console.stats_events)


def test_collector_usage_credit_reports_unavailable_reason():
    """``copilotUsage`` 欠落時は取得不能理由を併送する（捿造禁止）。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2)
    collector.handle_event(SimpleNamespace(
        type="assistant.usage",
        data=_UsageData(copilot_usage=None, api_call_id="api-3", model="claude-opus-5"),
    ))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    assert credits[0][2].get("unavailable_reason")


def test_collector_usage_credit_without_console_is_noop():
    """console 未設定時は従来どおり作業イベントを無視する（例外も出さない）。"""
    collector = FleetEventCollector()
    collector.handle_event(SimpleNamespace(
        type="assistant.usage",
        data=_UsageData(copilot_usage={"totalNanoAiu": 1}, api_call_id="api-4"),
    ))
    assert collector.running == {}


# ----------------------------------------------------------------------
# FR-RTO-07 (改訂 2.19): Fleet worker → Step 帰属
# ----------------------------------------------------------------------

_WAVE_STEP_IDS = ("2/APP-001", "2/APP-002", "2/APP-003")


def _spawn(tool_call_id: str, arguments: object) -> SimpleNamespace:
    """sub-agent を起動する親の tool call（``parent_tool_call_id`` なし）。"""
    return _event("tool.execution_start", tool_call_id=tool_call_id, tool_name="runSubagent", arguments=arguments)


def _worker_usage(parent_tool_call_id: str, *, nano_aiu: int = 1_000_000_000, api_call_id: str = "api-1") -> SimpleNamespace:
    return SimpleNamespace(
        type="assistant.usage",
        data=_UsageData(
            copilot_usage={"totalNanoAiu": nano_aiu},
            api_call_id=api_call_id,
            model="claude-opus-5",
            parent_tool_call_id=parent_tool_call_id,
        ),
    )


def test_collector_resolves_step_from_subagent_spawn_arguments():
    """起動 tool の引数から Wave の Step を一意に解決し、worker の消費を当該 Step へ帰属させる。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    collector.handle_event(_spawn("t1", {"prompt": "### task-002: Step.2/APP-002 \u3092実行する"}))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    assert credits[0][1] == "2/APP-002"
    assert credits[0][2]["nano_aiu"] == 1_000_000_000


def test_collector_emits_tool_invoked_for_resolved_worker():
    """解決済み worker の ``tool.execution_start`` を ``tool_invoked`` として当該 Step へ帰属させる。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    collector.handle_event(_spawn("t1", "### task-001: Step.2/APP-001"))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_call_id="w1", tool_name="edit_file"))

    tools = [ev for ev in console.stats_events if ev[0] == "tool_invoked"]
    assert len(tools) == 1
    assert tools[0][1] == "2/APP-001"
    assert tools[0][2]["tool_name"] == "edit_file"


def test_collector_does_not_attribute_when_multiple_steps_match():
    """引数が複数の Step に一致する場合はいずれへも割り当てない。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    collector.handle_event(_spawn("t1", "Step.2/APP-001 \u3068 Step.2/APP-003 \u306e両方"))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    assert credits[0][1] == ""


def test_collector_does_not_attribute_when_no_step_matches():
    """一致が 0 件の場合はいずれへも割り当てない。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    collector.handle_event(_spawn("t1", "\u4f55の Step も含まない指示"))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_call_id="w1", tool_name="edit_file"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert len(credits) == 1
    assert credits[0][1] == ""
    assert not any(ev[0] == "tool_invoked" for ev in console.stats_events)


def test_collector_step_match_requires_boundary():
    """``Step.2`` が ``Step.2/APP-001`` へ誤一致しない。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=("2", "2/APP-001"))
    collector.handle_event(_spawn("t1", "Step.2/APP-001 \u3060けを担当"))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert credits[0][1] == "2/APP-001"


def test_collector_does_not_persist_tool_arguments():
    """FR-RTO-04: 解決に用いた tool 引数を観測イベントへ含めない。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    secret = "SECRET_PROMPT_BODY_DO_NOT_PERSIST"
    collector.handle_event(_spawn("t1", {"prompt": f"Step.2/APP-001 {secret}"}))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))
    collector.handle_event(_event("tool.execution_start", parent_tool_call_id="t1", tool_call_id="w1", tool_name="edit_file"))

    serialized = json.dumps(console.stats_events, ensure_ascii=False, default=str)
    assert secret not in serialized


def test_collector_resolves_step_when_spawn_arrives_after_subagent_started():
    """起動 tool と ``subagent.started`` の到着順が逆でも解決できる。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2, step_ids=_WAVE_STEP_IDS)
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_spawn("t1", "Step.2/APP-003"))
    collector.handle_event(_worker_usage("t1"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert credits[0][1] == "2/APP-003"


def test_collector_without_step_ids_keeps_unattributed():
    """Wave の Step 集合が未注入なら従来どおり `step_id=""` で発火する。"""
    console = _FakeConsole()
    collector = FleetEventCollector(console=console, wave_index=2)
    collector.handle_event(_spawn("t1", "Step.2/APP-001"))
    collector.handle_event(_event("subagent.started", tool_call_id="t1", agent_display_name="Worker A"))
    collector.handle_event(_worker_usage("t1"))

    credits = [ev for ev in console.stats_events if ev[0] == "usage_credit"]
    assert credits[0][1] == ""


# ---------------------------------------------------------------------------
# FR-QA-03: Fleet wave で実行されないフェーズの警告
# ---------------------------------------------------------------------------

def test_skipped_phases_warning_is_empty_when_both_disabled():
    assert format_fleet_wave_skipped_phases_warning(
        wave_index=1, auto_qa=False, auto_contents_review=False
    ) == ""


def test_skipped_phases_warning_mentions_pre_qa():
    msg = format_fleet_wave_skipped_phases_warning(
        wave_index=2, auto_qa=True, auto_contents_review=False
    )
    assert "wave 2" in msg
    assert "事前 QA" in msg
    assert "敵対的レビュー" not in msg


def test_skipped_phases_warning_mentions_review():
    msg = format_fleet_wave_skipped_phases_warning(
        wave_index=3, auto_qa=False, auto_contents_review=True
    )
    assert "敵対的レビュー" in msg
    assert "事前 QA" not in msg


def test_skipped_phases_warning_mentions_both_and_workaround():
    msg = format_fleet_wave_skipped_phases_warning(
        wave_index=1, auto_qa=True, auto_contents_review=True
    )
    assert "事前 QA" in msg
    assert "敵対的レビュー" in msg
    assert "--no-fleet-mode" in msg


def test_orchestrator_emits_skipped_phases_warning_after_fleet_start():
    """警告は Fleet 起動成功を確認した後に 1 回だけ出す（FR-QA-03）。"""
    src = (Path(__file__).resolve().parents[1] / "orchestrator.py").read_text(encoding="utf-8")
    assert "format_fleet_wave_skipped_phases_warning" in src
    start_idx = src.index("if not outcome.started:")
    warn_idx = src.index("format_fleet_wave_skipped_phases_warning(", start_idx)
    status_idx = src.index("Fleet 起動完了", start_idx)
    assert start_idx < warn_idx < status_idx