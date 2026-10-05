"""T5: Foundry required Step の Azure / Microsoft Learn MCP routing 契約。"""

from __future__ import annotations

import asyncio
import inspect
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import (
    StepRunner,
)
from hve.toolsearch.resource_routing import ResourceRoutingError

class _Mcp:
    def __init__(self, servers, events: list[str]) -> None:
        self._servers = servers
        self._events = events
        self.calls = 0

    async def list(self):
        self.calls += 1
        self._events.append("mcp.list")
        return types.SimpleNamespace(servers=self._servers)


class _Session:
    def __init__(self, servers) -> None:
        self.events: list[str] = []
        self.mcp = _Mcp(servers, self.events)
        self.rpc = types.SimpleNamespace(mcp=self.mcp)
        self.send_calls = 0

    async def send_and_wait(self, _prompt: str, **_kwargs):
        self.send_calls += 1
        self.events.append("send_and_wait")
        return None

    async def disconnect(self) -> None:
        return None

    def on(self, _handler) -> None:
        return None


class _Client:
    def __init__(self, servers) -> None:
        self._servers = servers
        self.create_session_kwargs: list[dict] = []
        self.sessions: list[_Session] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def create_session(self, **kwargs):
        self.create_session_kwargs.append(kwargs)
        session = _Session(self._servers)
        self.sessions.append(session)
        return session


def _server(name: str, status: str = "connected"):
    return types.SimpleNamespace(
        name=name,
        status=types.SimpleNamespace(value=status),
        error=None,
    )


def _fake_copilot_modules(client: _Client):
    copilot: object = types.ModuleType("copilot")
    setattr(copilot, "CopilotClient", lambda **_kwargs: client)

    class _RuntimeConnection:
        @staticmethod
        def for_stdio(**_kwargs):
            return object()

        @staticmethod
        def for_uri(*_args, **_kwargs):
            return object()

    setattr(copilot, "RuntimeConnection", _RuntimeConnection)
    session: object = types.ModuleType("copilot.session")

    class _PermissionHandler:
        @staticmethod
        async def approve_all(*_args, **_kwargs):
            return True

    setattr(session, "PermissionHandler", _PermissionHandler)
    return copilot, session


def _write_foundry_skill(root: Path) -> None:
    skill_dir = root / "microsoft-foundry"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: microsoft-foundry\n---\n# Test skill\n",
        encoding="utf-8",
    )


def _runner() -> StepRunner:
    return StepRunner(
        config=SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            run_id="20260720T000000-foundry-mcp",
        ),
        console=Console(verbose=False, quiet=True),
    )


def _gate_patches(runner: StepRunner):
    return (
        patch.object(runner, "_run_asdw_data_verify_contract_gate", return_value=[]),
        patch.object(runner, "_run_ai_agent_capability_gate", return_value=[]),
        patch.object(runner, "_run_tdd_report_gate", return_value=[]),
        patch.object(runner, "_run_asdw_ui_red_unresolved_contract_gate", return_value=[]),
        patch.object(runner, "_run_deploy_ac_gate", return_value=[]),
    )


def test_foundry_runner_source_no_longer_uses_repository_pinned_mcp_helpers() -> None:
    import hve.runner as runner_module

    source = inspect.getsource(runner_module)

    assert "_load_trusted_foundry_mcp_servers" not in source
    assert "_require_trusted_foundry_mcp_servers" not in source
    assert "_FOUNDRY_REQUIRED_MCP_SERVERS" not in source
    assert "_ASDW_DATA_DEPLOY_REQUIRED_MCP_SERVERS" not in source
    assert "_verify_foundry_required_session_mcp_servers" not in source
    assert ".mcp.json" not in source


def test_foundry_required_main_session_delegates_skill_to_shared_route() -> None:
    runner = _runner()
    client = _Client([_server("azure"), _server("microsoft-learn"), _server("context7")])
    copilot, copilot_session = _fake_copilot_modules(client)
    routed_session = _Session([_server("azure"), _server("microsoft-learn"), _server("context7")])

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        _write_foundry_skill(external_root)
        gates = _gate_patches(runner)
        with patch.dict(
            sys.modules,
            {"copilot": copilot, "copilot.session": copilot_session},
        ), patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.skill_resolver._external_skills_root",
            return_value=external_root,
        ), patch(
            "hve.prompt_loader.load_prompt",
            return_value="",
        ), patch(
            "hve.runner.discover_sdk_resources",
            return_value=object(),
        ), patch(
            "hve.runner.ToolSearchPolicy",
            new=types.SimpleNamespace(load=lambda **_kwargs: object()),
        ), patch(
            "hve.runner.create_routed_session",
            new=AsyncMock(return_value=routed_session),
        ) as create, gates[0], gates[1], gates[2], gates[3], gates[4]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T5 Foundry MCP routing probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    assert create.await_args is not None
    kwargs = create.await_args.kwargs
    assert kwargs["required_mcp_servers"] is None
    assert "microsoft-foundry" in kwargs["required_skills"]
    assert "mcp_servers" not in kwargs["session_options"]
    assert client.create_session_kwargs == []
    assert routed_session.mcp.calls == 0
    assert routed_session.send_calls == 1
    assert routed_session.events == ["send_and_wait"]


def test_foundry_required_run_step_stops_before_main_turn_when_shared_route_fails() -> None:
    runner = _runner()
    client = _Client([])
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        _write_foundry_skill(external_root)
        gates = _gate_patches(runner)
        with patch.dict(
            sys.modules,
            {"copilot": copilot, "copilot.session": copilot_session},
        ), patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.skill_resolver._external_skills_root",
            return_value=external_root,
        ), patch(
            "hve.prompt_loader.load_prompt",
            return_value="",
        ), patch(
            "hve.runner.discover_sdk_resources",
            return_value=object(),
        ), patch(
            "hve.runner.ToolSearchPolicy",
            new=types.SimpleNamespace(load=lambda **_kwargs: object()),
        ), patch(
            "hve.runner.create_routed_session",
            new=AsyncMock(
                side_effect=ResourceRoutingError(
                    "required MCP server 'tenant-foundry' could not be applied"
                )
            ),
        ), gates[0], gates[1], gates[2], gates[3], gates[4]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T5 unavailable MCP probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is False
    assert len(client.sessions) == 0


def test_foundry_required_fanout_overrides_cannot_replace_policy_dependency() -> None:
    runner = _runner()
    client = _Client([_server("azure"), _server("microsoft-learn")])
    copilot, copilot_session = _fake_copilot_modules(client)
    routed_session = _Session([_server("azure"), _server("microsoft-learn")])

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        _write_foundry_skill(external_root)
        gates = _gate_patches(runner)
        with patch.dict(
            sys.modules,
            {"copilot": copilot, "copilot.session": copilot_session},
        ), patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.skill_resolver._external_skills_root",
            return_value=external_root,
        ), patch(
            "hve.prompt_loader.load_prompt",
            return_value="",
        ), patch(
            "hve.runner.discover_sdk_resources",
            return_value=object(),
        ), patch(
            "hve.runner.ToolSearchPolicy",
            new=types.SimpleNamespace(load=lambda **_kwargs: object()),
        ), patch(
            "hve.runner.create_routed_session",
            new=AsyncMock(return_value=routed_session),
        ) as create, gates[0], gates[1], gates[2], gates[3], gates[4]:
            result = asyncio.run(
                runner.run_step(
                    "2.3/AGENT-1",
                    "Foundry agent coding",
                    "T5 fanout MCP probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                    fanout_meta={
                        "fanout_key": "AGENT-1",
                        "base_step_id": "2.3",
                        "per_key_mcp_servers": {
                            "AGENT-1": {
                                "azure": {"command": "attacker"},
                                "microsoft-learn": {
                                    "type": "http",
                                    "url": "https://attacker.example/mcp",
                                },
                                "context7": {"command": "per-key-context7"},
                            }
                        },
                    },
                )
            )

    assert result is True
    assert create.await_args is not None
    kwargs = create.await_args.kwargs
    assert kwargs["required_mcp_servers"] is None
    assert "microsoft-foundry" in kwargs["required_skills"]
    assert "mcp_servers" not in kwargs["session_options"]
    assert client.create_session_kwargs == []


def test_foundry_required_without_repository_mcp_config_still_uses_shared_routing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = _runner()
    client = _Client([_server("azure"), _server("microsoft-learn")])
    copilot, copilot_session = _fake_copilot_modules(client)
    external_root = tmp_path / "skills"
    _write_foundry_skill(external_root)
    gates = _gate_patches(runner)
    routed_session = _Session([_server("azure"), _server("microsoft-learn")])

    with patch.dict(
        sys.modules,
        {"copilot": copilot, "copilot.session": copilot_session},
    ), patch(
        "hve.copilot_client_factory.create_copilot_client",
        return_value=client,
    ), patch(
        "hve.skill_resolver._external_skills_root",
        return_value=external_root,
    ), patch(
        "hve.prompt_loader.load_prompt",
        return_value="",
    ), patch(
        "hve.runner._ensure_step_work_dir",
        return_value=tmp_path / "work" / "step",
    ), patch(
        "hve.runner.discover_sdk_resources",
        return_value=object(),
    ), patch(
        "hve.runner.ToolSearchPolicy",
        new=types.SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch(
        "hve.runner.create_routed_session",
        new=AsyncMock(return_value=routed_session),
    ) as create, gates[0], gates[1], gates[2], gates[3], gates[4]:
        result = asyncio.run(
            runner.run_step(
                "2.3",
                "Foundry agent coding",
                "T5 invalid config probe",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                workflow_id="aagd",
            )
        )

    assert result is True
    assert create.await_args is not None
    assert create.await_args.kwargs["required_mcp_servers"] is None
    assert "microsoft-foundry" in create.await_args.kwargs["required_skills"]
    assert client.create_session_kwargs == []


def test_foundry_required_unknown_fanout_mcp_metadata_is_ignored_by_shared_routing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = _runner()
    client = _Client([_server("azure"), _server("microsoft-learn")])
    copilot, copilot_session = _fake_copilot_modules(client)
    external_root = tmp_path / "skills"
    _write_foundry_skill(external_root)
    gates = _gate_patches(runner)
    routed_session = _Session([_server("azure"), _server("microsoft-learn")])

    with patch.dict(
        sys.modules,
        {"copilot": copilot, "copilot.session": copilot_session},
    ), patch(
        "hve.copilot_client_factory.create_copilot_client",
        return_value=client,
    ), patch(
        "hve.skill_resolver._external_skills_root",
        return_value=external_root,
    ), patch(
        "hve.prompt_loader.load_prompt",
        return_value="",
    ), patch(
        "hve.runner._ensure_step_work_dir",
        return_value=tmp_path / "work" / "step",
    ), patch(
        "hve.runner.discover_sdk_resources",
        return_value=object(),
    ), patch(
        "hve.runner.ToolSearchPolicy",
        new=types.SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch(
        "hve.runner.create_routed_session",
        new=AsyncMock(return_value=routed_session),
    ) as create, gates[0], gates[1], gates[2], gates[3], gates[4]:
        result = asyncio.run(
            runner.run_step(
                "2.3/AGENT-1",
                "Foundry agent coding",
                "T5 fanout metadata ignore probe",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                workflow_id="aagd",
                fanout_meta={
                    "fanout_key": "AGENT-1",
                    "base_step_id": "2.3",
                    "per_key_mcp_servers": {
                        "AGENT-1": {
                            "context7": {"command": "ignored"},
                        }
                    },
                },
            )
        )

    assert result is True
    assert create.await_args is not None
    assert create.await_args.kwargs["required_mcp_servers"] is None
    assert "microsoft-foundry" in create.await_args.kwargs["required_skills"]
    assert "mcp_servers" not in create.await_args.kwargs["session_options"]
    assert client.create_session_kwargs == []


def test_asdw_data_deploy_has_no_sub_session_mcp_special_case() -> None:
    """Step 1.3 は native pipeline 化され、sub-session の特別分岐を持たない。

    旧実装は DataDeploy だけ `enable_config_discovery=False` と
    microsoft-learn 固定の MCP を注入していたが、Step 1.3 はそもそも
    session を作らないため到達不能だった。一般 Step と同一経路に
    なっていること（= 死んだ分岐が復活していないこと）を固定する。
    """
    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    with patch.object(
        runner,
        "_build_step_permission_handler",
        return_value="permission-handler",
    ):
        data_deploy_options = runner._build_sub_session_opts(
            runner.config.model,
            step_id="1.3",
            suffix="pre-qa",
            custom_agent="Dev-Microservice-Azure-DataDeploy",
        )
        general_options = runner._build_sub_session_opts(
            runner.config.model,
            step_id="1.3",
            suffix="pre-qa",
            custom_agent="Dev-Microservice-Azure-DataTestCoding",
        )

    assert "enable_config_discovery" not in data_deploy_options
    assert "on_event" not in data_deploy_options
    assert data_deploy_options.keys() == general_options.keys()
    assert data_deploy_options.get("mcp_servers") == general_options.get(
        "mcp_servers"
    )
    assert not hasattr(runner, "_asdw_data_deploy_expected_mcp_servers")
    assert not hasattr(
        StepRunner, "_verify_asdw_data_deploy_session_mcp_servers"
    )


def test_asdw_data_deploy_never_opens_a_main_mcp_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Step 1.3 は HVE-owned native pipeline で実行され、main session を作らない。

    従来は main session を microsoft-learn のみに限定し config discovery を
    無効化する契約だったが、native 化により MCP 表面自体が存在しない
    （より強い隔離）。
    """
    monkeypatch.chdir(tmp_path)
    runner = _runner()
    monkeypatch.setenv("HVE_RUN_ID", runner.config.run_id)
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work"))
    runner._workflow_params = {
        "app_ids": ["APP-009"],
        "resource_group": "test-resource-group",
        "data_location": "japaneast",
        "data_resource_suffix": "app009",
        "data_vnet_cidr": "10.40.0.0/16",
        "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
        "data_aci_subnet_cidr": "10.40.2.0/24",
        "data_verify_aci_image": "registry.example/verify:v1",
    }
    client = _Client([_server("microsoft-learn")])
    copilot, copilot_session = _fake_copilot_modules(client)
    gates = _gate_patches(runner)

    with patch.dict(
        sys.modules,
        {"copilot": copilot, "copilot.session": copilot_session},
    ), patch(
        "hve.copilot_client_factory.create_copilot_client",
        return_value=client,
    ), patch.object(
        runner,
        "_build_step_permission_handler",
        return_value="permission-handler",
    ), patch(
        "hve.runner._validate_asdw_data_deploy_runtime_context",
        return_value=[],
    ), patch(
        "hve.prompt_loader.load_prompt",
        return_value="",
    ), patch(
        "hve.runner._ensure_step_work_dir",
        return_value=tmp_path / "work" / "step",
    ), patch(
        "hve.runner.ensure_asdw_data_producers",
        return_value=types.SimpleNamespace(
            status="reused",
            audit_mode="sql-ledger-digest",
        ),
    ), patch(
        "hve.runner._build_asdw_data_deploy_environment_snapshot",
        return_value={},
    ), patch(
        "hve.runner.execute_pipeline",
        return_value=(),
    ), gates[0], gates[1], gates[2], gates[3], gates[4]:
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Data deploy",
                "T5 ASDW main MCP probe",
                custom_agent="Dev-Microservice-Azure-DataDeploy",
                workflow_id="asdw-web",
            )
        )

    # native pipeline の stage 結果が空なので Step は失敗するが、
    # 重要なのは SDK セッションが一切作られないこと。
    assert result is False
    assert client.create_session_kwargs == []


def test_pre_qa_sub_session_does_not_copy_deprecated_mcp_timeout() -> None:
    """FR-KD-03: 事前 QA の sub-session は知識源を持たず、MCP request timeout も複製しない。"""
    config = SDKConfig(workiq_enabled=True)
    assert not hasattr(config, "workiq_request_timeout")
    runner = StepRunner(config=config, console=Console(verbose=False, quiet=True))
    with patch.object(
        runner,
        "_build_step_permission_handler",
        return_value="permission-handler",
    ):
        options = runner._build_sub_session_opts(
            config.model,
            step_id="1",
            suffix="pre-qa",
        )

    assert "mcp_servers" not in options
    assert "timeout" not in options
    assert not any("workiq" in str(tool) for tool in options.get("available_tools", []))


def test_knowledge_discovery_session_uses_sdk_discovery_without_mcp_timeout() -> None:
    """FR-KD-03: 知識探索セッションは SDK discovery を使い、HVE 独自の MCP 設定を作らない。"""
    from hve import knowledge_discovery as kd

    toolset = kd.DiscoveryToolset(
        mode="qa", repo_root=Path.cwd(), run_id="r1", label="1",
        usable=["workiq"], allowlists={"workiq": ["ask"]}, evidence=kd.SourceEvidence(),
    )
    options = kd.build_session_options(
        base={"model": "m", "on_user_input_request": object()},
        usable=["workiq"],
        allowlists={"workiq": ["ask"]},
        enabled_server_names=["workiq", "azure"],
        toolset=toolset,
        tools=[],
        permission_handler=lambda *_: None,
        on_event=lambda _event: None,
    )

    assert "mcp_servers" not in options
    assert "timeout" not in options
    assert "on_user_input_request" not in options
    assert options["enable_config_discovery"] is True
    assert options["disabled_mcp_servers"] == ["azure"]
    assert "mcp:workiq-ask" in options["available_tools"]


