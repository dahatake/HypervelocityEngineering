"""FR-KD-06 / FR-INPUT-05 / FR-CLI-76: 事前 QA の質問票 session と知識探索 session の分離。

real shipped AAGD Step / Skill manifest / Tool-Search policy を使い、SDK と外部 IO だけを fake にする。
質問票の生成は Step の resource を維持した sub-session で行い、知識源（`workiq` を含む）を外す。
知識源への問い合わせは知識探索 session（FR-KD-03）だけが行い、調査回答を QA へ記録する。
"""

from __future__ import annotations

import asyncio
import importlib
import json
import socket
import sqlite3
import subprocess
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from copilot.generated.rpc import (
    CurrentToolMetadata,
    MCPListToolsRequest,
    PermissionDecisionReject,
    SessionUpdateOptionsResult,
    ToolsGetCurrentMetadataResult,
)

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner

_WORKIQ = "workiq"
_LOCATOR = "https://contoso.sharepoint.com/sites/t20/approval"


def test_review_sub_session_is_left_to_the_generic_frcli76_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config = SDKConfig(workiq_enabled=True)
    runner = StepRunner(config=config, console=Console(verbose=False, quiet=True))
    with patch.object(
        runner, "_build_step_permission_handler", return_value="permission-handler"
    ):
        options = runner._build_sub_session_opts(config.model, step_id="1", suffix="review")

    assert "mcp_servers" not in options
    assert "enable_config_discovery" not in options
    assert "disabled_mcp_servers" not in options


@pytest.fixture(params=["2.3", "3"], ids=["aagd-2.3", "aagd-3"])
def shipped_aagd_runtime(request, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """T20 R1: real shipped Step/manifest/policy; only SDK and external IO are fake."""
    module = importlib.import_module("hve.runner")
    resolver = importlib.import_module("hve.skill_resolver")
    routing = importlib.import_module("hve.toolsearch.resource_routing")
    inventory = importlib.import_module("hve.toolsearch.resource_inventory")
    merger = importlib.import_module("hve.qa_merger")
    from hve.step_inputs import StepInputBundle
    from hve.workflow_registry import get_step

    repo = Path(__file__).resolve().parents[2]
    assert module.__file__ is not None
    assert Path(module.__file__).resolve() == repo / "hve" / "runner.py"
    resolver.load_skill_manifest.cache_clear()
    resolver.discover_available_skills.cache_clear()
    step = get_step("aagd", request.param)
    assert step is not None
    assert resolver.load_skill_manifest()["required_skills"]["aagd"][step.id] == ["microsoft-foundry"]
    required = StepRunner._get_required_skills_for_step("aagd", step.id, None)
    assert "microsoft-foundry" in required
    policy = module.ToolSearchPolicy.load(repo / "hve" / "toolsearch" / "policy.json")
    assert policy.required_mcp_servers_for_skills(required) == ("azure", "microsoft-learn")

    external = tmp_path / "external-skills"
    foundry = external / "microsoft-foundry"
    foundry.mkdir(parents=True)
    (foundry / "SKILL.md").write_text(
        "---\nname: microsoft-foundry\ndescription: Offline T20 fixture.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "_external_skills_root", lambda: external)
    for name, relative in resolver.discover_available_skills().items():
        if name in required:
            target = tmp_path / ".github" / "skills" / relative / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((repo / ".github" / "skills" / relative / "SKILL.md").read_bytes())
    assert resolver.get_skill_directory("microsoft-foundry") == foundry

    blocked = Mock(side_effect=AssertionError("T20 fake-only external boundary reached"))
    for owner, name in (
        (socket, "create_connection"), (socket, "getaddrinfo"),
        (sqlite3, "connect"), (subprocess, "Popen"), (subprocess, "run"),
        (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell"),
        (importlib.import_module("copilot"), "CopilotClient"),
        (module, "RunStateStore"), (module, "default_state_path"),
    ):
        monkeypatch.setattr(owner, name, blocked)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "t20-preqa")
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "t20-preqa"))
    config = SDKConfig(
        model="gpt-5.4", qa_model="gpt-5.5", run_id="t20-preqa", workiq_enabled=True,
        qa_answer_mode="autopilot", unattended=True, cloud_session_enabled=False,
        available_tools=["view"], excluded_tools=["write"],
    )
    monkeypatch.setattr(config, "get_qa_model", lambda: config.qa_model)
    monkeypatch.setattr(config, "resolve_token", lambda: "")
    monkeypatch.setattr(config, "tool_search_session_option", lambda: None)
    console = Mock(spec=Console, show_stream=False, verbose=False)
    runner = StepRunner(config=config, console=console, workflow_params={
        "step_input_bundles": {step.id: StepInputBundle("aagd", step.id, ())},
        "step_input_mcp_consent": True,
    })
    servers = ["azure", "microsoft-learn", _WORKIQ, "workiq-preview", "unclassified-peer"]

    def _snapshot():
        return inventory.ResourceSnapshot(
            plugin_state="ready", mcp_state="ready", skill_state="ready",
            skill_ownership_state="ready", plugins=(),
            mcp_servers=tuple(inventory.ResourceItem("mcp_server", name, True, "direct") for name in servers),
            skills=tuple(inventory.ResourceItem("skill", name, True, "direct") for name in required),
        )

    discovery = Mock(side_effect=lambda **_kwargs: _snapshot())
    monkeypatch.setattr(module, "discover_sdk_resources", discovery)
    qa_rel = f"qa/t20-preqa-{step.id}-pre-execution-qa.md"
    trace = SimpleNamespace(
        order=[], failure="", cleanup={}, cleanup_cancelled=[], qa_skills_available=True,
        guard_questionnaire_workiq=False, tool_results=[],
        questionnaire=merger.QAMerger.render_merged(merger.QADocument(questions=[
            merger.QAQuestion(no=no, question=f"Question {no}?", priority="高", default_answer="TBD")
            for no in (1, 2)
        ])),
    )
    creator = AsyncMock(wraps=module._create_session_with_auto_reasoning_fallback)
    monkeypatch.setattr(module, "_create_session_with_auto_reasoning_fallback", creator)
    monkeypatch.setattr(module, "_RUNNER_CLEANUP_TIMEOUT_SECONDS", 0.02)

    class FakeSession:
        def __init__(self, options):
            self.options = options
            self.kind = "discovery" if "tools" in options else "qa"
            self.initialized = False
            self.last_update = None
            self.listed_servers = []
            self.handlers = [options["on_event"]] if callable(options.get("on_event")) else []
            self.on = Mock(side_effect=self.handlers.append)
            self.send_and_wait = AsyncMock(side_effect=self.send)
            self.disconnect = AsyncMock(side_effect=self.close)
            self.delete = blocked
            self.rpc = SimpleNamespace(
                tools=SimpleNamespace(
                    initialize_and_validate=AsyncMock(side_effect=self.initialize),
                    get_current_metadata=AsyncMock(side_effect=self.current_metadata),
                ),
                skills=SimpleNamespace(list=AsyncMock(side_effect=self.skills)),
                mcp=SimpleNamespace(
                    list=AsyncMock(side_effect=self.list_servers),
                    list_tools=AsyncMock(side_effect=self.list_tools), disable=blocked,
                    oauth=SimpleNamespace(login=blocked),
                ),
                options=SimpleNamespace(update=AsyncMock(side_effect=self.update)),
            )

        async def skills(self, **_kwargs):
            trace.order.append((self.kind, "skills"))
            names = required if trace.qa_skills_available else []
            return SimpleNamespace(skills=[SimpleNamespace(name=name, enabled=True) for name in names])

        async def initialize(self, **_kwargs):
            trace.order.append((self.kind, "init"))
            self.initialized = True
            return SimpleNamespace()

        async def list_servers(self, **_kwargs):
            trace.order.append((self.kind, "list"))
            disabled = set(self.options.get("disabled_mcp_servers") or ())
            return SimpleNamespace(
                host=SimpleNamespace(),
                servers=[
                    SimpleNamespace(
                        name=name,
                        status="failed" if (name == _WORKIQ and trace.failure == "mcp-failed") else "connected",
                    )
                    for name in servers if name not in disabled
                ],
            )

        async def list_tools(self, request, **_kwargs):
            assert isinstance(request, MCPListToolsRequest)
            trace.order.append((self.kind, f"tools:{request.server_name}"))
            self.listed_servers.append(request.server_name)
            tools = list(dict.fromkeys(
                policy.tool_allowlist_for("knowledge", request.server_name)
                + policy.tool_allowlist_for("software-engineering", request.server_name)
            ))
            if self.kind == "discovery" and trace.failure == "missing-tools":
                tools = []
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in tools])

        async def update(self, request, **_kwargs):
            trace.order.append((self.kind, "ack"))
            self.last_update = request
            return SessionUpdateOptionsResult(success=True)

        async def current_metadata(self, **_kwargs):
            trace.order.append((self.kind, "metadata"))
            available = (
                None
                if self.last_update is None or self.last_update.available_tools is None
                else set(self.last_update.available_tools)
            )
            excluded = set(
                () if self.last_update is None else self.last_update.excluded_tools or ()
            )
            tools = []
            for server_name in dict.fromkeys(self.listed_servers):
                for tool_name in dict.fromkeys(
                    policy.tool_allowlist_for("knowledge", server_name)
                    + policy.tool_allowlist_for("software-engineering", server_name)
                ):
                    tool_id = f"mcp:{server_name}-{tool_name}"
                    if available is not None and tool_id not in available:
                        continue
                    if tool_id in excluded:
                        continue
                    tools.append(CurrentToolMetadata(
                        description="offline MCP tool",
                        name=f"mcp__{server_name}__{tool_name}",
                        mcp_server_name=server_name,
                        mcp_tool_name=tool_name,
                        namespaced_name=tool_id,
                    ))
            return ToolsGetCurrentMetadataResult(tools=tools)

        async def _call_tool(self, name, arguments):
            tool = next(t for t in self.options["tools"] if t.name == name)
            result = await tool.handler(SimpleNamespace(arguments=arguments))
            payload = json.loads(result.text_result_for_llm)
            trace.tool_results.append((name, payload))
            return payload

        def _emit(self, kind, **data):
            event = SimpleNamespace(type=SimpleNamespace(value=kind), data=SimpleNamespace(**data))
            for handler in tuple(self.handlers):
                handler(event)

        async def send(self, prompt, *, timeout):
            del timeout
            if module.PRE_EXECUTION_QA_PROMPT_V2 in prompt:
                trace.order.append((self.kind, "questionnaire"))
                assert self.kind == "qa", "questionnaire must not run in the knowledge discovery session"
                if trace.guard_questionnaire_workiq:
                    assert _WORKIQ in self.options.get("disabled_mcp_servers", []), (
                        "questionnaire can start workiq before custom-input consent"
                    )
                return SimpleNamespace(text=trace.questionnaire)
            trace.order.append((self.kind, "discover"))
            assert self.kind == "discovery"
            assert "T20 AAGD" in prompt and qa_rel in prompt
            if trace.failure == "cancel-discovery":
                raise asyncio.CancelledError("offline discovery cancellation")
            if trace.failure == "send-error":
                raise RuntimeError("offline discovery failure")
            read = await self._call_tool("hve_read_file", {"path": qa_rel})
            self._emit("tool.execution_start", mcp_server_name=_WORKIQ, mcp_tool_name="ask", tool_call_id="k1")
            self._emit(
                "tool.execution_complete", tool_call_id="k1", success=True,
                result=SimpleNamespace(content=f"承認方式は二段階です。出典: {_LOCATOR}", detailed_content=""),
            )
            await self._call_tool("hve_qa_answer", {
                "path": qa_rel,
                "base_sha256": read["sha256"],
                "answers": [
                    {"no": no, "answer": f"T20_TRUSTED_{no} 承認方式は二段階", "status": "Confirmed", "source_ids": ["L1"]}
                    for no in (1, 2)
                ],
                "sources": [{
                    "id": "L1", "kind": "mcp", "server": _WORKIQ, "tool": "ask",
                    "locator": _LOCATOR, "summary": "承認方式の記述",
                }],
            })
            return SimpleNamespace(text="done")

        async def close(self):
            trace.order.append((self.kind, "disconnect"))
            if trace.cleanup.get(self.kind) == "raise":
                raise RuntimeError("******")
            if trace.cleanup.get(self.kind) == "cancel":
                raise asyncio.CancelledError("offline cleanup cancellation")
            if trace.cleanup.get(self.kind) == "hang":
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    trace.cleanup_cancelled.append(self.kind)
                    raise

    class FakeClient:
        def __init__(self):
            self.sessions = []
            self.start = AsyncMock(side_effect=blocked)
            self.stop = AsyncMock(side_effect=blocked)
            self.force_stop = AsyncMock(side_effect=blocked)

        async def create_session(self, **options):
            created = FakeSession(options)
            trace.order.append((created.kind, "create"))
            if created.kind == "discovery" and trace.failure == "create":
                raise RuntimeError("offline discovery creation failed")
            self.sessions.append(created)
            return created

    async def main_send(prompt, *, timeout):
        del timeout
        if module.PRE_EXECUTION_QA_PROMPT_V2 in prompt:
            assert not trace.guard_questionnaire_workiq, (
                "custom-input questionnaire can start workiq through main reuse"
            )
            return SimpleNamespace(text=trace.questionnaire)

    client = FakeClient()
    main = SimpleNamespace(send_and_wait=AsyncMock(side_effect=main_send), disconnect=AsyncMock())

    def run():
        async def scenario():
            with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
                context = await runner._run_pre_execution_qa(
                    session=main, client=client, step_id=step.id,
                    original_prompt=f"T20 AAGD {step.id}", custom_agent=step.custom_agent,
                    workflow_id="aagd", current_phase=1, total_phases=2,
                )
                await main.send_and_wait(context, timeout=config.timeout_seconds)
                return context

        async def bounded():
            return await asyncio.wait_for(scenario(), timeout=5.0)

        return asyncio.run(bounded())

    yield SimpleNamespace(
        module=module, routing=routing, config=config, runner=runner, console=console,
        client=client, main=main, run=run, trace=trace, root=tmp_path, step=step,
        required=required, foundry=foundry, creator=creator, policy=policy,
        discovery=discovery, servers=servers, qa_rel=qa_rel, merger=merger,
    )
    blocked.assert_not_called()
    client.start.assert_not_awaited()
    client.stop.assert_not_awaited()
    client.force_stop.assert_not_awaited()
    main.disconnect.assert_not_awaited()
    resolver.discover_available_skills.cache_clear()


def trace_index(runtime, kind, action):
    return runtime.trace.order.index((kind, action))


def _kinds(runtime):
    return [s.kind for s in runtime.client.sessions]


@pytest.mark.parametrize("same_model", [False, True], ids=["qa-model", "shared-model"])
def test_shipped_aagd_pre_qa_separates_questionnaire_and_discovery(shipped_aagd_runtime, same_model):
    r = shipped_aagd_runtime
    if same_model:
        r.config.qa_model = r.config.model
    context = r.run()

    assert _kinds(r) == ["qa", "discovery"]
    qa, disc = r.client.sessions
    qa_call, disc_call = r.creator.await_args_list
    assert qa_call.kwargs["required_skills"] == r.required
    assert qa_call.kwargs["requires_external_skill_directories"] is True
    assert str(r.foundry) in qa.options["skill_directories"]
    assert not {"azure", "microsoft-learn"}.intersection(qa.options["disabled_mcp_servers"])
    assert _WORKIQ in qa.options["disabled_mcp_servers"]
    assert qa.options["available_tools"] == ["view"] and qa.options["excluded_tools"] == ["write"]
    assert disc_call.kwargs["use_resource_routing"] is False
    assert not disc_call.kwargs.get("required_skills")
    assert str(r.foundry) not in disc.options.get("skill_directories", [])
    assert "mcp_servers" not in disc.options and "excluded_tools" not in disc.options
    assert disc.options["enable_config_discovery"] is True
    assert disc.options["disabled_mcp_servers"] == sorted(set(r.servers) - {_WORKIQ})
    assert "mcp:workiq-ask" in disc.options["available_tools"]
    assert "custom:hve_qa_answer" in disc.options["available_tools"]
    assert "on_user_input_request" not in disc.options
    assert qa.options["model"] == disc.options["model"] == r.config.qa_model
    assert qa.options["session_id"] != disc.options["session_id"]
    assert trace_index(r, "qa", "questionnaire") < trace_index(r, "discovery", "create")
    assert trace_index(r, "discovery", "list") < trace_index(r, "discovery", "discover")
    assert [name for name, payload in r.trace.tool_results if not payload.get("ok")] == []
    qa.send_and_wait.assert_awaited_once()
    disc.send_and_wait.assert_awaited_once()
    assert r.runner._sub_sessions_created == 2
    for created in (qa, disc):
        created.disconnect.assert_awaited_once()
    answered = r.root / r.qa_rel
    assert context == "## 事前 QA 確認済み情報\n\n" + answered.read_text(encoding="utf-8")
    doc = r.merger.QAMerger.parse_qa_file(answered)
    assert [q.research_status for q in doc.questions] == ["Confirmed", "Confirmed"]
    assert [q.user_answer for q in doc.questions] == [
        "T20_TRUSTED_1 承認方式は二段階", "T20_TRUSTED_2 承認方式は二段階",
    ]
    r.console.prompt_yes_no.assert_not_called()
    r.main.send_and_wait.assert_awaited_once()


@pytest.mark.parametrize("shipped_aagd_runtime", ["2.3"], indirect=True)
@pytest.mark.parametrize("same_model", [False, True], ids=["qa-model", "same-model"])
@pytest.mark.parametrize("workiq_enabled", [True, False], ids=["workiq-on", "workiq-off"])
def test_t20r1_questionnaire_blocks_workiq_without_consent(
    shipped_aagd_runtime, monkeypatch, same_model, workiq_enabled,
):
    """FR-INPUT-05: 同意の無い custom input では知識源へ問い合わせず、質問票 session も `workiq` を外す。"""
    r = shipped_aagd_runtime
    r.config.available_tools = r.config.excluded_tools = None
    r.config.workiq_enabled = workiq_enabled
    r.trace.guard_questionnaire_workiq = True
    if same_model:
        r.config.qa_model = r.config.model
    monkeypatch.setattr(r.runner, "_workflow_params", MappingProxyType({
        **r.runner._workflow_params, "step_input_mcp_consent": False,
    }))

    context = r.run()

    assert _kinds(r) == ["qa"]
    qa = r.client.sessions[0]
    call = r.creator.await_args
    assert call.args[1]["disabled_mcp_servers"] == [_WORKIQ], "only the exact server is added before routing"
    assert call.kwargs["required_skills"] == r.required
    assert str(r.foundry) in qa.options["skill_directories"]
    assert not {"azure", "microsoft-learn"}.intersection(qa.options["disabled_mcp_servers"])
    # NFR-SEC-04: QA session も Step セッションと同じく CRITICAL なシェル操作だけを拒否する
    qa_handler = qa.options["on_permission_request"]
    assert isinstance(
        qa_handler(SimpleNamespace(kind="shell", full_command_text="az group delete --name rg"), {}),
        PermissionDecisionReject,
    )
    assert not isinstance(
        qa_handler(SimpleNamespace(kind="shell", full_command_text="pytest -q"), {}),
        PermissionDecisionReject,
    )
    assert ("qa", f"tools:{_WORKIQ}") not in r.trace.order
    assert not any(action == "discover" for _kind, action in r.trace.order)
    qa.disconnect.assert_awaited_once()
    r.main.send_and_wait.assert_awaited_once_with(context, timeout=r.config.timeout_seconds)
    assert context.startswith("## 事前 QA 確認済み情報")
    assert r.config.workiq_enabled is workiq_enabled
    assert r.config.available_tools is None and r.config.excluded_tools is None


@pytest.mark.parametrize("shipped_aagd_runtime", ["2.3"], indirect=True)
def test_t20r1_questionnaire_preserves_existing_disabled_servers(shipped_aagd_runtime, monkeypatch):
    r = shipped_aagd_runtime
    r.config.workiq_enabled = False
    existing = ["unclassified-peer"]
    build = r.runner._build_sub_session_opts

    def with_existing_exclusion(*args, **kwargs):
        options = build(*args, **kwargs)
        options["disabled_mcp_servers"] = existing
        return options

    monkeypatch.setattr(r.runner, "_build_sub_session_opts", with_existing_exclusion)
    r.run()

    assert existing == ["unclassified-peer"], "do not mutate caller-owned exclusions"
    assert r.creator.await_args.args[1]["disabled_mcp_servers"] == sorted({*existing, _WORKIQ})
    assert _kinds(r) == ["qa"]


@pytest.mark.parametrize("shipped_aagd_runtime", ["2.3"], indirect=True)
def test_t20r1_questionnaire_required_workiq_conflict_fails_closed(shipped_aagd_runtime):
    r = shipped_aagd_runtime
    r.config.available_tools = r.config.excluded_tools = None
    r.config.workiq_enabled = False
    policy = r.policy.to_dict()
    policy["required_mcp_servers_by_skill"]["microsoft-foundry"].append(_WORKIQ)
    override = r.root / ".toolsearch" / "policy.json"
    override.parent.mkdir()
    override.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(r.routing.ResourceRoutingError, match="required MCP server 'workiq' is disabled by the caller"):
        r.run()

    assert r.client.sessions == []
    assert r.creator.await_args.kwargs["required_skills"] == r.required
    r.main.send_and_wait.assert_not_awaited()


@pytest.mark.parametrize("shipped_aagd_runtime", ["2.3"], indirect=True)
def test_t20r1_no_input_no_source_keeps_main_reuse(shipped_aagd_runtime, monkeypatch):
    """custom input も知識源も無ければ、既存の same-model 契約どおり main session を再利用する。"""
    r = shipped_aagd_runtime
    r.config.qa_model = r.config.model
    r.config.available_tools = r.config.excluded_tools = None
    r.config.workiq_enabled = False
    monkeypatch.setattr(r.runner, "_workflow_params", MappingProxyType({
        "step_input_bundles": {}, "step_input_mcp_consent": False,
    }))

    context = r.run()

    assert r.runner._should_use_pre_qa_sub_session(r.config.qa_model, False) is False
    assert r.client.sessions == [] and r.runner._sub_sessions_created == 0
    r.creator.assert_not_awaited()
    assert r.main.send_and_wait.await_count == 2
    assert r.module.PRE_EXECUTION_QA_PROMPT_V2 in r.main.send_and_wait.await_args_list[0].args[0]
    assert r.main.send_and_wait.await_args_list[1].args[0] == context
    assert context.startswith("## 事前 QA 確認済み情報")



@pytest.mark.parametrize("case", ["off", "unavailable", "empty", "consent-denied", "dry-run"])
def test_shipped_aagd_skips_unneeded_discovery_session(shipped_aagd_runtime, monkeypatch, case):
    r = shipped_aagd_runtime
    if case == "off":
        r.config.workiq_enabled = False
    elif case == "unavailable":
        r.servers.remove(_WORKIQ)
    elif case == "empty":
        r.trace.questionnaire = ""
    elif case == "consent-denied":
        monkeypatch.setattr(r.runner, "_workflow_params", MappingProxyType({
            **r.runner._workflow_params, "step_input_mcp_consent": False,
        }))
    else:
        r.config.dry_run = True
    context = r.run()

    assert _kinds(r) == ["qa"]
    r.client.sessions[0].disconnect.assert_awaited_once()
    assert not any(action == "discover" for _kind, action in r.trace.order)
    r.main.send_and_wait.assert_awaited_once()
    assert bool(context) is (case != "empty")
    if case == "unavailable":
        assert any("workiq" in str(c) for c in r.console.warning.call_args_list)


@pytest.mark.parametrize("failure", ["create", "mcp-failed", "missing-tools", "send-error"])
def test_shipped_aagd_discovery_failure_retains_qa_and_main(shipped_aagd_runtime, failure):
    """FR-KD-06: 探索の失敗は警告だけにし、既定値候補で QA を確定して main へ進む（人を待たない）。"""
    r = shipped_aagd_runtime
    r.trace.failure = failure
    context = r.run()

    assert "事前 QA 確認済み情報" in context and "T20_TRUSTED" not in context
    doc = r.merger.QAMerger.parse_qa_file(r.root / r.qa_rel)
    assert [q.user_answer for q in doc.questions] == ["TBD", "TBD"]
    r.main.send_and_wait.assert_awaited_once()
    r.console.prompt_yes_no.assert_not_called()
    assert r.console.warning.call_count > 0
    for created in r.client.sessions:
        created.disconnect.assert_awaited_once()
    assert r.client.sessions[0].kind == "qa"
    if failure == "send-error":
        assert [q.research_status for q in doc.questions] == ["Unknown", "Unknown"]


def test_shipped_aagd_questionnaire_required_skill_failure_is_not_optional(shipped_aagd_runtime):
    r = shipped_aagd_runtime
    r.trace.qa_skills_available = False
    with pytest.raises(r.routing.ResourceRoutingError, match="required Skill runtime is unavailable"):
        r.run()

    assert _kinds(r) == ["qa"]
    r.client.sessions[0].disconnect.assert_awaited_once()
    r.client.sessions[0].send_and_wait.assert_not_awaited()
    r.main.send_and_wait.assert_not_awaited()


@pytest.mark.parametrize("consent", [False, True], ids=["deny", "allow"])
def test_shipped_aagd_resolves_consent_before_creating_discovery_session(
    shipped_aagd_runtime, monkeypatch, consent,
):
    r = shipped_aagd_runtime
    r.config.available_tools = r.config.excluded_tools = None
    r.trace.guard_questionnaire_workiq = True
    r.config.qa_answer_mode = "all"
    r.config.qa_auto_defaults = True
    r.config.unattended = False
    r.config.force_interactive = True
    monkeypatch.setattr(r.runner, "_workflow_params", MappingProxyType({
        **r.runner._workflow_params, "step_input_mcp_consent": None,
    }))

    def answer_consent(*_args, **_kwargs):
        assert _kinds(r) == ["qa"]
        assert ("qa", "questionnaire") in r.trace.order
        return consent

    r.console.prompt_yes_no.side_effect = answer_consent
    context = r.run()
    r.console.prompt_yes_no.assert_called_once()
    assert _kinds(r) == (["qa", "discovery"] if consent else ["qa"])
    assert ("T20_TRUSTED_1" in context) is consent
    assert "事前 QA 確認済み情報" in context


@pytest.mark.parametrize("kind", ["qa", "discovery"])
@pytest.mark.parametrize("cleanup", ["raise", "hang"])
def test_shipped_aagd_cleanup_is_bounded_and_does_not_skip_other_session(
    shipped_aagd_runtime, kind, cleanup,
):
    r = shipped_aagd_runtime
    r.trace.cleanup[kind] = cleanup
    context = r.run()

    assert "T20_TRUSTED_1" in context
    disconnects = [entry for entry in r.trace.order if entry[1] == "disconnect"]
    assert disconnects == [("discovery", "disconnect"), ("qa", "disconnect")]
    for created in r.client.sessions:
        created.disconnect.assert_awaited_once()
    if cleanup == "hang":
        assert r.trace.cleanup_cancelled == [kind], "bounded helper must cancel the hung disconnect"
    assert r.console.warning.call_count > 0
    r.main.send_and_wait.assert_awaited_once()


@pytest.mark.parametrize("phase", ["discovery", "cleanup"])
def test_shipped_aagd_cancellation_disconnects_both_sessions_once(shipped_aagd_runtime, phase):
    r = shipped_aagd_runtime
    if phase == "discovery":
        r.trace.failure = "cancel-discovery"
    else:
        r.trace.cleanup["discovery"] = "cancel"
    with pytest.raises(asyncio.CancelledError):
        r.run()

    assert _kinds(r) == ["qa", "discovery"]
    disconnects = [entry for entry in r.trace.order if entry[1] == "disconnect"]
    assert disconnects == [("discovery", "disconnect"), ("qa", "disconnect")]
    for created in r.client.sessions:
        created.disconnect.assert_awaited_once()
    r.main.send_and_wait.assert_not_awaited()
