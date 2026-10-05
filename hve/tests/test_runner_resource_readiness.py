"""T10 RED: Main の create/init より前のイベント登録 (FR-MCPLOG-01)。

実 run_step → _create_main_session → shared creation helper を通す。
SDK/探索/認証/DB は fake-only。テスト実行と RED 確認は親タスクが行う。
"""

from __future__ import annotations

import asyncio
import importlib
import socket
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest


def _event(kind: str, **data: Any) -> SimpleNamespace:
    return SimpleNamespace(type=SimpleNamespace(value=kind), data=SimpleNamespace(**data))


def _statuses(console: Any) -> list[tuple[str, str]]:
    return [(call.args[0], call.kwargs["status"]) for call in console.mcp_server_status.call_args_list]


@pytest.fixture(params=[
    pytest.param(
        ("Authorization: Bearer T10SECRET", "T10SECRET", "Authorization: Bearer [REDACTED]"),
        id="bearer",
    ),
    pytest.param(
        ("password=T10PASSWORD", "T10PASSWORD", "password=[REDACTED]"),
        id="password",
    ),
])
def dummy_secret_diagnostic(request: pytest.FixtureRequest) -> SimpleNamespace:
    """Synthetic diagnostic values only; never use real credentials."""
    error, secret, masked = request.param
    return SimpleNamespace(error=error, secret=secret, masked=masked)


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = importlib.import_module("hve.runner")
    # Flat `runner` and another editable worktree must never escape our patches.
    assert module.StepRunner.__module__ == "hve.runner"
    assert module.StepRunner.run_step.__globals__ is vars(module)
    assert Path(module.__file__).resolve() == Path(__file__).resolve().parents[1] / "runner.py"
    factory_module = importlib.import_module("hve.copilot_client_factory")
    blocked = Mock(side_effect=AssertionError("T10 fake-only external boundary reached"))
    for owner, name in (
        (socket, "create_connection"), (socket, "getaddrinfo"),
        (sqlite3, "connect"), (subprocess, "Popen"), (subprocess, "run"),
        (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell"),
        (module, "RunStateStore"), (module, "default_state_path"),
        (importlib.import_module("copilot"), "CopilotClient"),
        (module, "execute_pipeline"), (module, "_resolve_asdw_data_deploy_subscription_id"),
    ):
        monkeypatch.setattr(owner, name, blocked)
    monkeypatch.chdir(tmp_path)
    for key, value in (
        ("HVE_RUN_ID", "t10-readiness"),
        ("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "t10-readiness")),
        ("HVE_STEP_ID", ""), ("HVE_AGENT_ID", ""),
    ):
        monkeypatch.setenv(key, value)

    console = Mock(spec=module.Console, show_stream=False, verbose=False)
    config = module.SDKConfig(
        dry_run=False, model="gpt-5.4", run_id="t10-readiness",
        auto_qa=False, auto_contents_review=False,
        available_tools=["view"], excluded_tools=["write"],
    )
    monkeypatch.setattr(config, "resolve_token", Mock(return_value=""))
    monkeypatch.setattr(config, "tool_search_session_option", Mock(return_value=None))
    runner = module.StepRunner(config, console, workflow_params={"app_ids": ["APP-009"]})
    workflow = SimpleNamespace(
        id="t10-readiness",
        steps=[SimpleNamespace(id="1.1", output_paths=[], required_skills=["test-required"])],
    )
    monkeypatch.setattr(importlib.import_module("hve.workflow_registry"), "get_workflow", Mock(return_value=workflow))
    monkeypatch.setattr(importlib.import_module("hve.prompt_loader"), "load_prompt", Mock(return_value=""))
    permission = Mock(return_value={"kind": "denied-by-test-guard"})
    permission_factory = Mock(return_value=permission)
    monkeypatch.setattr(runner, "_build_step_permission_handler", permission_factory)
    monkeypatch.setattr(runner, "_get_required_skills_for_step", Mock(return_value=["test-required"]))
    monkeypatch.setattr(runner, "_get_optional_skills_for_step", Mock(return_value=[]))
    monkeypatch.setattr(runner, "_add_required_external_skill_directories", Mock(return_value=False))
    monkeypatch.setattr(runner, "_poll_steering_ipc", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "_repository_skill_directories", Mock(return_value=[]))
    monkeypatch.setattr(module, "build_cloud_session_options", Mock(return_value=None))
    monkeypatch.setattr(module, "should_use_cloud_session", Mock(return_value=False))
    monkeypatch.setattr(module, "discover_sdk_resources", Mock(return_value=object()))
    monkeypatch.setattr(module, "ToolSearchPolicy", SimpleNamespace(load=Mock(return_value=object())))

    trace = SimpleNamespace(create_events=[], init_events=[], send_events=[], order=[])
    handlers: list[Any] = []

    def emit(events):
        for event in events:
            for handler in tuple(handlers):
                handler(event)

    def subscribe(handler):
        handlers.append(handler)
        return lambda: handlers.remove(handler)

    async def send(_prompt, *, timeout):
        trace.order.append("send")
        emit(trace.send_events)
        return SimpleNamespace(text="fake main response")

    async def initialize(**_kwargs):
        trace.order.append("init")
        emit(trace.init_events)
        trace.at_init = _statuses(console)

    session = SimpleNamespace(
        on=Mock(side_effect=subscribe), send_and_wait=AsyncMock(side_effect=send),
        disconnect=AsyncMock(),
        rpc=SimpleNamespace(tools=SimpleNamespace(initialize_and_validate=AsyncMock(side_effect=initialize))),
    )

    class FakeClient:
        def __init__(self):
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.force_stop = AsyncMock()
            self.create_kwargs: list[dict[str, Any]] = []

        async def create_session(self, **kwargs):
            trace.order.append("create")
            self.create_kwargs.append(dict(kwargs))
            trace.initial_state = (runner._current_step_id, runner._sub_sessions_created)
            handler = kwargs.get("on_event")
            if callable(handler):
                handlers.append(handler)  # SDK registration, not a later session.on().
            runner._current_step_id = "other-step"  # Expose an unbound callback.
            emit(trace.create_events)  # No replay after create returns.
            trace.at_create = _statuses(console)
            return session

    client = FakeClient()
    factory = Mock(return_value=client)
    monkeypatch.setattr(factory_module, "create_copilot_client", factory)

    async def create_routed(**kwargs):
        assert kwargs["client"] is client, "shared creation must receive the fake client"
        created = await kwargs["client"].create_session(**kwargs["session_options"])
        # The real routing algorithm has separate tests; retain its init-before-return seam.
        await created.rpc.tools.initialize_and_validate()
        return created

    routed = AsyncMock(side_effect=create_routed)
    monkeypatch.setattr(module, "create_routed_session", routed)

    def run(step_id="1.1", custom_agent=None):
        async def scenario():
            # Windows asyncio needs its internal socketpair before this guard is installed.
            with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
                return await runner.run_step(step_id, "T10 Main", "fake task", custom_agent=custom_agent, workflow_id=workflow.id)

        result = asyncio.run(scenario())
        blocked.assert_not_called()
        assert result is True, console.error.call_args_list
        console.error.assert_not_called()
        factory.assert_called_once()
        client.start.assert_awaited_once()
        assert len(client.create_kwargs) == 1
        routed.assert_awaited_once()
        session.send_and_wait.assert_awaited_once()
        session.disconnect.assert_awaited_once()
        client.stop.assert_awaited_once()

    yield SimpleNamespace(
        module=module, runner=runner, console=console, trace=trace, client=client,
        session=session, routed=routed, permission=permission,
        permission_factory=permission_factory, run=run,
    )
    blocked.assert_not_called()


def test_main_observes_mcp_loaded_before_create_returns(runtime):
    runtime.trace.create_events.append(_event(
        "session.mcp_servers_loaded",
        servers=[SimpleNamespace(name="test-mcp", status="connected")],
    ))
    runtime.run()

    assert callable(runtime.client.create_kwargs[0].get("on_event")), "Main create must receive on_event"
    assert runtime.trace.at_create == [("test-mcp", "connected")], "create-time events must not be lost"


def test_main_observes_status_during_required_resource_initialization(runtime):
    runtime.trace.init_events.append(_event(
        "session.mcp_server_status_changed", server_name="test-mcp", status="connected",
    ))
    runtime.run()

    routed = runtime.routed.await_args.kwargs
    assert routed["workflow_id"] == "t10-readiness"
    assert routed["required_skills"] == ["test-required"]
    assert routed["required_mcp_servers"] is None
    handler = routed["session_options"].get("on_event")
    assert callable(handler), "Main callback must reach shared init, not only the returned session"
    assert runtime.client.create_kwargs[0].get("on_event") is handler
    assert runtime.trace.order == ["create", "init", "send"]
    assert runtime.trace.at_init == [("test-mcp", "connected")]


def test_main_callback_state_is_initialized_and_bound_before_create(runtime):
    runner = runtime.runner
    runner._sub_sessions_created = 7
    runtime.trace.create_events.extend([
        _event("permission.requested", permission_request=SimpleNamespace(kind="write")),
        _event("skill.invoked", name="test-required"),
        _event("tool.execution_start", mcp_server_name="workiq", mcp_tool_name="ask", tool_call_id="create-call"),
        _event("tool.execution_complete", tool_call_id="create-call", success=True),
    ])
    runtime.run()

    assert runtime.trace.initial_state == ("1.1", 0)
    assert runner._permission_count == 1, "create-time callback must use initialized counters"
    assert runner._skill_invoked_seen.get("1.1") == {"test-required"}
    assert not hasattr(runner, "_workiq_called_tools"), "Work IQ 専用の証跡追跡は廃止した（FR-KD-10）"
    runtime.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=1, permission_kind="write")


def test_main_does_not_register_a_second_handler_after_create(runtime):
    runtime.trace.send_events.append(_event(
        "session.mcp_server_status_changed", server_name="test-mcp", status="connected",
    ))
    runtime.run()

    runtime.session.on.assert_not_called()
    assert _statuses(runtime.console) == [("test-mcp", "connected")], "each event must be dispatched exactly once"


@pytest.mark.parametrize("phase", ["create", "init"])
@pytest.mark.parametrize(
    "event_type",
    ["session.mcp_servers_loaded", "session.mcp_server_status_changed"],
    ids=["loaded", "status-changed"],
)
@pytest.mark.parametrize("status", ["failed", "needs-auth"])
def test_main_masks_mcp_error_diagnostics_before_console(
    runtime,
    dummy_secret_diagnostic: SimpleNamespace,
    phase: str,
    event_type: str,
    status: str,
) -> None:
    """NFR-SEC-01 / FR-MCPLOG-03: Console arguments must already be masked."""
    data = {"error": dummy_secret_diagnostic.error, "status": status}
    if event_type == "session.mcp_servers_loaded":
        event = _event(event_type, servers=[SimpleNamespace(name="workiq", **data)])
    else:
        event = _event(event_type, server_name="workiq", **data)
    getattr(runtime.trace, f"{phase}_events").append(event)
    runtime.run()

    warnings = runtime.console.warning.call_args_list
    assert warnings, "MCP failure diagnostics must not be dropped"
    assert all(dummy_secret_diagnostic.secret not in str(call) for call in warnings)
    if event_type == "session.mcp_servers_loaded":
        assert any(dummy_secret_diagnostic.masked in call.args[0] for call in warnings)
    runtime.console.mcp_server_status.assert_called_once()
    status_call = runtime.console.mcp_server_status.call_args
    assert status_call.args == ("workiq",)
    assert status_call.kwargs["status"] == status
    assert dummy_secret_diagnostic.secret not in str(status_call)
    assert status_call.kwargs["error"] == dummy_secret_diagnostic.masked


@pytest.mark.parametrize("phase", ["create", "init"])
@pytest.mark.parametrize("event_type", ["session.error", "session.log"])
def test_main_masks_early_session_diagnostics_before_console(
    runtime,
    dummy_secret_diagnostic: SimpleNamespace,
    phase: str,
    event_type: str,
) -> None:
    """T20 R2 / NFR-SEC-01: the early callback must not expose raw diagnostics."""
    event = _event(
        event_type, message=dummy_secret_diagnostic.error,
        error_type="resource_initialization", level="warning",
    )
    getattr(runtime.trace, f"{phase}_events").append(event)
    runtime.run()

    if event_type == "session.error":
        runtime.console.session_error.assert_called_once_with(
            "resource_initialization", dummy_secret_diagnostic.masked,
        )
    else:
        runtime.console.cli_log.assert_called_once_with(
            "1.1", f"[warning] {dummy_secret_diagnostic.masked}",
        )
    assert dummy_secret_diagnostic.secret not in str(runtime.console.mock_calls)
    runtime.session.on.assert_not_called()


def test_data_deploy_preserves_guards_without_double_dispatch(runtime, monkeypatch):
    # Synthetic workflow: exercise the retained SDK options branch, never the native Azure pipeline.
    monkeypatch.setattr(runtime.module, "_resolve_asdw_data_deploy_subscription_id", Mock(return_value="00000000-0000-0000-0000-000000000001"))
    monkeypatch.setattr(runtime.module, "build_asdw_data_deploy_bootstrap_context", Mock(return_value={}))
    monkeypatch.setattr(runtime.module, "_validate_asdw_data_deploy_runtime_context", Mock(return_value=[]))
    for name in (
        "_run_asdw_data_verify_contract_gate", "_run_asdw_data_producer_contract_gate",
        "_run_asdw_data_deploy_preflight_failure_gate", "_run_deploy_ac_gate",
    ):
        monkeypatch.setattr(runtime.runner, name, Mock(return_value=[]))
    runtime.trace.create_events.append(_event(
        "session.mcp_servers_loaded", servers=[SimpleNamespace(name="test-mcp", status="pending")],
    ))
    runtime.trace.send_events.append(_event(
        "session.mcp_server_status_changed", server_name="test-mcp", status="connected",
    ))
    runtime.run("1.3", "Dev-Microservice-Azure-DataDeploy")

    opts = runtime.client.create_kwargs[0]
    assert opts["enable_config_discovery"] is False
    assert opts["on_permission_request"] is runtime.permission
    runtime.permission_factory.assert_called_once_with("1.3", "Dev-Microservice-Azure-DataDeploy")
    assert opts["streaming"] is True
    assert opts["available_tools"] == ["view"] and opts["excluded_tools"] == ["write"]
    assert callable(opts.get("on_event"))
    assert runtime.trace.at_create == [("test-mcp", "pending")]
    assert _statuses(runtime.console) == [("test-mcp", "pending"), ("test-mcp", "connected")]
    runtime.session.on.assert_not_called()


# T11: exercise Pre-QA directly, without changing the T10 Main runtime fixture.
@pytest.fixture
def pre_qa_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = importlib.import_module("hve.runner")
    assert module.StepRunner._run_pre_execution_qa.__globals__ is vars(module)
    assert Path(module.__file__).resolve() == Path(__file__).resolve().parents[1] / "runner.py"
    blocked = Mock(side_effect=AssertionError("T11 fake-only external boundary reached"))
    for owner, name in (
        (socket, "create_connection"), (socket, "getaddrinfo"),
        (sqlite3, "connect"), (subprocess, "Popen"), (subprocess, "run"),
        (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell"),
        (importlib.import_module("copilot"), "CopilotClient"),
        (module, "RunStateStore"), (module, "default_state_path"),
        (module, "discover_sdk_resources"), (module, "run_knowledge_discovery"),
    ):
        monkeypatch.setattr(owner, name, blocked)
    monkeypatch.chdir(tmp_path)
    config = module.SDKConfig(
        model="gpt-5.4", qa_model="gpt-5.5", run_id="t11-preqa",
        workiq_enabled=False,
        qa_answer_mode="autopilot", unattended=True,
        available_tools=["view"], excluded_tools=["write"],
    )
    monkeypatch.setattr(config, "get_qa_model", Mock(side_effect=lambda: config.qa_model))
    monkeypatch.setattr(config, "resolve_token", Mock(return_value=""))
    monkeypatch.setattr(config, "tool_search_session_option", Mock(return_value=None))
    console = Mock(spec=module.Console, show_stream=False, verbose=False)
    runner = module.StepRunner(config, console)
    permission = Mock(return_value={"kind": "denied-by-test-guard"})
    monkeypatch.setattr(runner, "_build_step_permission_handler", Mock(return_value=permission))
    monkeypatch.setattr(runner, "_get_required_skills_for_step", Mock(return_value=["test-required"]))
    monkeypatch.setattr(runner, "_get_optional_skills_for_step", Mock(return_value=["test-optional"]))
    monkeypatch.setattr(runner, "_add_required_external_skill_directories", Mock(return_value=False))
    trace = SimpleNamespace(
        create_events=[], init_events=[], send_events=[], questionnaire="", order=[],
        query_create_events=[], query_init_events=[],
    )
    handlers: list[Any] = []
    query_handlers: list[Any] = []

    def emit(events, callbacks=handlers):
        for event in events:
            for handler in tuple(callbacks):
                handler(event)

    def make_session(callbacks):
        async def send(_prompt, *, timeout):
            trace.order.append("send")
            emit(trace.send_events, callbacks)
            return SimpleNamespace(text=trace.questionnaire)

        return SimpleNamespace(
            on=Mock(side_effect=callbacks.append),
            send_and_wait=AsyncMock(side_effect=send), disconnect=AsyncMock(),
        )

    session = make_session(handlers)
    query_session = make_session(query_handlers)
    # Main already owns its T10 creation-time callback; Pre-QA must not add one.
    main = make_session([lambda event: runner._handle_session_event_for_step(event, "1.1")])
    client = SimpleNamespace()

    async def create(_client, options, **_kwargs):
        is_query = options.get("available_tools") == ["mcp:workiq-ask"]
        callbacks = query_handlers if is_query else handlers
        trace.order.append("query-create" if is_query else "create")
        handler = options.get("on_event")
        if callable(handler):
            callbacks.append(handler)  # Consume the creation option, not session.on().
        runner._current_step_id = "other-step"
        emit(trace.query_create_events if is_query else trace.create_events, callbacks)
        trace.at_create = _statuses(console)
        trace.order.append("query-init" if is_query else "init")
        emit(trace.query_init_events if is_query else trace.init_events, callbacks)
        trace.at_init = _statuses(console)
        return query_session if is_query else session

    creator = AsyncMock(side_effect=create)
    monkeypatch.setattr(module, "_create_session_with_auto_reasoning_fallback", creator)

    def run():
        async def scenario():
            # Allow asyncio's own Windows socketpair before blocking all task connects.
            with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
                return await runner._run_pre_execution_qa(
                    session=main, client=client, step_id="1.1", original_prompt="T11 task",
                    custom_agent="T11-Agent", workflow_id="t11-preqa",
                    current_phase=1, total_phases=2, main_session_id="t11-main",
                )

        context = asyncio.run(scenario())
        blocked.assert_not_called()
        console.error.assert_not_called()
        return context

    yield SimpleNamespace(
        module=module, runner=runner, config=config, console=console, trace=trace,
        session=session, main=main, client=client, creator=creator,
        permission=permission, emit=emit, run=run, root=tmp_path,
        query_session=query_session, emit_query=lambda events: emit(events, query_handlers),
    )
    blocked.assert_not_called()


def test_pre_qa_passes_bound_callback_before_session_creation(pre_qa_runtime):
    """FR-MCPLOG-01: create/init events are observed once and belong to this Step."""
    r = pre_qa_runtime
    r.trace.create_events.extend([
        _event("session.mcp_servers_loaded", servers=[SimpleNamespace(name="test-mcp", status="pending")]),
        _event("permission.requested", permission_request=SimpleNamespace(kind="write")),
    ])
    r.trace.init_events.extend([
        _event("session.mcp_server_status_changed", server_name="test-mcp", status="connected"),
        _event("skill.invoked", name="test-required"),
    ])
    r.trace.send_events.append(_event("permission.requested", permission_request=SimpleNamespace(kind="read")))
    assert r.run() == ""

    r.creator.assert_awaited_once()
    call = r.creator.await_args
    assert call.args[0] is r.client
    opts = call.args[1]
    assert callable(opts.get("on_event")), "Pre-QA must bind on_event before entering the creation helper"
    assert opts["on_permission_request"] is r.permission
    assert opts["model"] == "gpt-5.5" and opts["streaming"] is True
    assert opts["available_tools"] == ["view"] and opts["excluded_tools"] == ["write"]
    assert "mcp_servers" not in opts and "cloud" not in opts, "shared helper still owns discovery/cloud routing"
    assert call.kwargs["config"] is r.config
    assert call.kwargs["step_id"] == "1.1" and call.kwargs["workflow_id"] == "t11-preqa"
    assert call.kwargs["subtask_kind"] == "pre_qa"
    assert call.kwargs["required_skills"] == ["test-required"]
    assert call.kwargs["optional_skills"] == ["test-optional"]
    assert r.trace.order == ["create", "init", "send"]
    assert r.trace.at_create == [("test-mcp", "pending")]
    assert r.trace.at_init == [("test-mcp", "pending"), ("test-mcp", "connected")]
    assert r.runner._skill_invoked_seen == {"1.1": {"test-required"}}
    assert r.runner._permission_count == 2
    r.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=1, permission_kind="write")
    r.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=2, permission_kind="read")
    r.session.on.assert_not_called()
    r.session.send_and_wait.assert_awaited_once()
    r.session.disconnect.assert_awaited_once()
    r.main.send_and_wait.assert_not_awaited()
    r.main.on.assert_not_called()
    r.main.disconnect.assert_not_awaited()
    assert r.runner._sub_sessions_created == 1


def test_pre_qa_main_reuse_does_not_add_event_subscription(pre_qa_runtime):
    r = pre_qa_runtime
    r.config.qa_model = r.config.model
    r.runner._current_step_id = "other-step"
    r.trace.send_events.append(_event("permission.requested", permission_request=SimpleNamespace(kind="read")))
    assert r.run() == ""

    r.creator.assert_not_awaited()
    r.main.on.assert_not_called()
    r.main.send_and_wait.assert_awaited_once()
    r.main.disconnect.assert_not_awaited()
    r.session.on.assert_not_called()
    r.session.send_and_wait.assert_not_awaited()
    r.session.disconnect.assert_not_awaited()
    assert r.trace.order == ["send"]
    assert r.runner._permission_count == 1
    assert r.runner._sub_sessions_created == 0
    r.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=1, permission_kind="read")


def test_pre_qa_discovery_receives_step_bound_event_sink_and_adopts_research(pre_qa_runtime, monkeypatch):
    """FR-KD-06 / FR-MCPLOG-01: 知識探索は質問票の後に 1 回だけ実行し、イベントは Step 1.1 に帰属する。"""
    r = pre_qa_runtime
    r.config.workiq_enabled = True
    merger = importlib.import_module("hve.qa_merger")
    kf = importlib.import_module("hve.knowledge_files")
    (r.root / "README.md").write_text("承認方式は二段階\n", encoding="utf-8")
    r.trace.questionnaire = merger.QAMerger.render_merged(merger.QADocument(questions=[
        merger.QAQuestion(no=no, question=f"Question {no}?", priority="高", default_answer="TBD")
        for no in (1, 2)
    ]))
    monkeypatch.setattr(r.module, "discover_sdk_resources", Mock(return_value=SimpleNamespace()))
    qa_rel = "qa/t11-preqa-1.1-pre-execution-qa.md"
    calls = []

    async def fake_discovery(request, **kwargs):
        calls.append((request, kwargs))
        assert r.trace.order == ["create", "init", "send"], "discovery must start after the questionnaire"
        assert (request.mode, request.label, list(request.sources), request.qa_path) == ("qa", "1.1", ["workiq"], qa_rel)
        assert "T11 task" in request.goal
        assert kwargs["base_session_options"]["model"] == "gpt-5.5"
        r.runner._current_step_id = "other-step"
        kwargs["event_sink"](_event("permission.requested", permission_request=SimpleNamespace(kind="read")))
        current = kf.read_file(r.root, qa_rel)
        assert current["exists"] and "調査回答" not in current["content"]
        kf.update_qa_research(
            r.root, qa_rel, base_sha256=current["sha256"],
            answers=[kf.ResearchAnswer(no=1, answer="T11_TRUSTED", status="Confirmed", source_ids=("L1",))],
            sources=[kf.SourceEntry(id="L1", kind="repo", server="", tool="", locator="README.md", summary="承認方式")],
        )
        return SimpleNamespace(ran=True)

    monkeypatch.setattr(r.module, "run_knowledge_discovery", fake_discovery)
    context = r.run()

    assert len(calls) == 1
    assert r.creator.await_count == 1
    assert "workiq" in r.creator.await_args.args[1]["disabled_mcp_servers"]
    r.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=1, permission_kind="read")
    answered = r.root / qa_rel
    doc = merger.QAMerger.parse_qa_file(answered)
    assert [q.user_answer for q in doc.questions] == ["T11_TRUSTED", "TBD"]
    assert [q.research_status for q in doc.questions] == ["Confirmed", ""]
    assert context == "## 事前 QA 確認済み情報\n\n" + answered.read_text(encoding="utf-8")
    r.session.disconnect.assert_awaited_once()
    r.console.prompt_yes_no.assert_not_called()


# T12: keep the T10/T11 fixtures intact; extend only the fake review boundary.
@pytest.fixture
def review_runtime(runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    r = runtime
    config = r.runner.config
    config.auto_contents_review = True
    config.review_model = "gpt-5.5"
    config.run_id = "t12-review"
    monkeypatch.setattr(config, "get_review_model", Mock(side_effect=lambda: config.review_model))
    monkeypatch.setenv("HVE_RUN_ID", "t12-review")
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "t12-review"))
    monkeypatch.setattr(importlib.import_module("hve.workflow_registry"), "get_workflow", Mock(return_value=SimpleNamespace(
        id="t12-review", steps=[SimpleNamespace(id="1.1", output_paths=[], required_skills=["test-required"])],
    )))
    blocked = Mock(side_effect=AssertionError("T12 fake-only socket boundary reached"))
    trace = SimpleNamespace(create_events=[], init_events=[], send_events=[], init_failure=None)
    handlers: list[Any] = []

    def emit(events):
        for event in events:
            for handler in tuple(handlers):
                handler(event)

    async def initialize(**_kwargs):
        r.trace.order.append("review-init")
        emit(trace.init_events)
        trace.at_init = _statuses(r.console)
        if trace.init_failure is not None:
            raise trace.init_failure

    async def send(_prompt, *, timeout):
        r.trace.order.append("review-send")
        emit(trace.send_events)
        return SimpleNamespace(text="- 合格判定: PASS")

    review = SimpleNamespace(
        on=Mock(side_effect=handlers.append), send_and_wait=AsyncMock(side_effect=send),
        disconnect=AsyncMock(),
        rpc=SimpleNamespace(tools=SimpleNamespace(initialize_and_validate=AsyncMock(side_effect=initialize))),
    )
    original_create = r.client.create_session

    async def create(**kwargs):
        if kwargs.get("session_id") != r.runner._make_step_session_id("1.1", suffix="review"):
            return await original_create(**kwargs)
        r.trace.order.append("review-create")
        r.client.create_kwargs.append(dict(kwargs))
        trace.initial_state = (r.runner._permission_count, r.runner._sub_sessions_created)
        handler = kwargs.get("on_event")
        if callable(handler):
            handlers.append(handler)  # SDK consumes on_event before create/init; no replay.
        r.runner._current_step_id = "other-step"
        emit(trace.create_events)
        trace.at_create = _statuses(r.console)
        return review

    monkeypatch.setattr(r.client, "create_session", AsyncMock(side_effect=create))
    creator = AsyncMock(wraps=r.module._create_session_with_auto_reasoning_fallback)
    monkeypatch.setattr(r.module, "_create_session_with_auto_reasoning_fallback", creator)
    original_main_send = r.session.send_and_wait.side_effect

    async def send_main(prompt, *, timeout):
        reused_for_review = r.session.send_and_wait.await_count > 1
        if reused_for_review:
            r.trace.send_events[:] = trace.send_events
        response = await original_main_send(prompt, timeout=timeout)
        return SimpleNamespace(text="- 合格判定: PASS") if reused_for_review else response

    r.session.send_and_wait.side_effect = send_main

    def run(*, expected=True):
        async def scenario():
            # Keep asyncio's Windows socketpair outside the task connection guard.
            with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
                return await r.runner.run_step(
                    "1.1", "T12 Review", "fake task", custom_agent="T12-Agent", workflow_id="t12-review",
                )

        result = asyncio.run(scenario())
        blocked.assert_not_called()
        assert result is expected, r.console.error.call_args_list
        if expected:
            r.console.error.assert_not_called()
        r.client.start.assert_awaited_once()
        r.session.disconnect.assert_awaited_once()
        r.client.stop.assert_awaited_once()

    r.review = review
    r.review_trace = trace
    r.creator = creator
    r.run = run
    yield r
    blocked.assert_not_called()


def test_review_receives_bound_callback_before_create_and_init(review_runtime):
    """FR-MCPLOG-01: creation-time observation retains the existing routing contract."""
    r = review_runtime
    r.review_trace.create_events.extend([
        _event("session.mcp_servers_loaded", servers=[SimpleNamespace(name="test-mcp", status="pending")]),
        _event("permission.requested", permission_request=SimpleNamespace(kind="write")),
    ])
    r.review_trace.init_events.extend([
        _event("session.mcp_server_status_changed", server_name="test-mcp", status="connected"),
        _event("skill.invoked", name="test-required"),
    ])
    r.run()

    assert r.creator.await_count == 2
    creation = r.creator.await_args
    opts = creation.args[1]
    assert creation.args[0] is r.client
    assert callable(opts.get("on_event")), "Review must register on_event before entering the creation helper"
    assert r.client.create_kwargs[1]["on_event"] is opts["on_event"]
    assert r.routed.await_args.kwargs["session_options"]["on_event"] is opts["on_event"]
    assert opts["model"] == "gpt-5.5" and opts["streaming"] is True
    assert opts["on_permission_request"] is r.permission
    r.permission_factory.assert_any_call("1.1", "T12-Agent")
    assert opts["available_tools"] == ["view"] and opts["excluded_tools"] == ["write"]
    assert "cloud" not in opts and "mcp_servers" not in opts
    assert creation.kwargs["config"] is r.runner.config
    assert creation.kwargs["step_id"] == "1.1" and creation.kwargs["workflow_id"] == "t12-review"
    assert creation.kwargs["subtask_kind"] == "review"
    assert creation.kwargs["required_skills"] == ["test-required"]
    assert creation.kwargs["optional_skills"] == []
    assert creation.kwargs["requires_external_skill_directories"] is False
    assert r.trace.order == ["create", "init", "send", "review-create", "review-init", "review-send"]
    assert r.review_trace.at_create == [("test-mcp", "pending")]
    assert r.review_trace.at_init == [("test-mcp", "pending"), ("test-mcp", "connected")]
    assert r.runner._skill_invoked_seen == {"1.1": {"test-required"}}
    r.console.stats_event.assert_any_call("permission_count", step_id="1.1", count=1, permission_kind="write")
    r.session.on.assert_not_called()
    r.review.on.assert_not_called()
    r.review.send_and_wait.assert_awaited_once()
    r.review.disconnect.assert_awaited_once()
    assert r.runner._sub_sessions_created == 1
    assert "fake main response" in r.review.send_and_wait.await_args.args[0]
    r.console.review_result.assert_called_once_with("- 合格判定: PASS")


def test_review_early_callback_preserves_main_state_without_duplicate_dispatch(review_runtime):
    r = review_runtime
    r.trace.send_events.extend([
        _event("permission.requested", permission_request=SimpleNamespace(kind="read")),
        _event("tool.execution_start", mcp_server_name="workiq", mcp_tool_name="ask", tool_call_id="main-call"),
        _event("tool.execution_complete", tool_call_id="main-call", success=True),
    ])
    r.review_trace.create_events.extend([
        _event("permission.requested", permission_request=SimpleNamespace(kind="write")),
        _event("tool.execution_start", mcp_server_name="workiq", mcp_tool_name="ask", tool_call_id="review-call"),
    ])
    r.review_trace.init_events.append(_event("tool.execution_complete", tool_call_id="review-call", success=True))
    r.review_trace.send_events.append(_event("permission.requested", permission_request=SimpleNamespace(kind="read")))
    r.run()

    assert r.review_trace.initial_state == (1, 0)
    assert r.runner._permission_count == 3, "Main state must survive early review callbacks, without duplicate delivery"
    counts = [call for call in r.console.stats_event.call_args_list if call.args[0] == "permission_count"]
    assert [(call.kwargs["step_id"], call.kwargs["count"]) for call in counts] == [("1.1", 1), ("1.1", 2), ("1.1", 3)]
    r.session.on.assert_not_called()
    r.review.on.assert_not_called()


def test_review_initialization_failure_retains_early_diagnostics_and_cleanup(review_runtime):
    """FR-MCPLOG-03 / NFR-SEC-01: early failure metadata is observable and masked."""
    r = review_runtime
    r.review_trace.create_events.append(_event(
        "session.mcp_servers_loaded",
        servers=[SimpleNamespace(name="test-mcp", status="failed", error="password=T12_REVIEW_SECRET")],
    ))
    r.review_trace.init_events.append(_event(
        "session.error", error_type="resource_initialization", message="T12 review initialization failed",
    ))
    r.review_trace.init_failure = RuntimeError("T12 review initialization failed")
    r.run(expected=False)

    assert r.review_trace.at_create == [("test-mcp", "failed")], "failure before helper return must retain early diagnostics"
    r.console.mcp_server_status.assert_called_once()
    assert r.console.mcp_server_status.call_args.kwargs["error"] == "password=[REDACTED]"
    assert "T12_REVIEW_SECRET" not in str(r.console.warning.call_args_list)
    r.console.session_error.assert_called_once_with("resource_initialization", "T12 review initialization failed")
    r.console.error.assert_called_once()
    assert "RuntimeError: T12 review initialization failed" in r.console.error.call_args.args[0]
    assert r.creator.await_args.kwargs["subtask_kind"] == "review"
    assert r.creator.await_args.kwargs["step_id"] == "1.1"
    assert r.creator.await_args.kwargs["workflow_id"] == "t12-review"
    r.review.send_and_wait.assert_not_awaited()
    r.review.on.assert_not_called()
    # The helper never returned ownership of a review session to run_step.
    r.review.disconnect.assert_not_awaited()
    assert r.runner._sub_sessions_created == 0
    assert r.console.step_end.call_args.args == ("1.1", "failed")


def test_review_same_model_still_uses_review_sub_session(review_runtime):
    """FR-CLI-92: review_model がメインモデルと同一でも評価はサブセッションで行う。"""
    r = review_runtime
    r.runner.config.review_model = r.runner.config.model
    r.run()

    assert r.creator.await_count == 2
    assert r.creator.await_args.kwargs["subtask_kind"] == "review"
    assert r.trace.order == ["create", "init", "send", "review-create", "review-init", "review-send"]
    r.session.send_and_wait.assert_awaited_once()
    r.review.send_and_wait.assert_awaited_once()
    assert r.review.send_and_wait.await_args.args[0] != r.module.REVIEW_PROMPT
    r.review.disconnect.assert_awaited_once()
    assert r.runner._sub_sessions_created == 1
    r.console.review_result.assert_called_once_with("- 合格判定: PASS")