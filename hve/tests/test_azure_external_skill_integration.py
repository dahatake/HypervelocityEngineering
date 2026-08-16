"""T9: Azure external Skill routing のcross-layer統合契約。"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.skill_resolver import get_skill_directory
from hve.workflow_registry import get_workflow


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO_ROOT / "hve" / "skill_manifest.json"
_PINNED_AZURE = {
    "tools": ["*"],
    "command": "npx",
    "args": ["-y", "@azure/mcp@latest", "server", "start"],
}
_PINNED_LEARN = {
    "type": "http",
    "url": "https://learn.microsoft.com/api/mcp",
    "tools": ["*"],
}


class _Mcp:
    def __init__(self, servers, events: list[str]) -> None:
        self._servers = servers
        self._events = events

    async def list(self):
        self._events.append("mcp.list")
        return types.SimpleNamespace(servers=self._servers)


class _Session:
    def __init__(self, servers) -> None:
        self.events: list[str] = []
        self.prompts: list[str] = []
        self.rpc = types.SimpleNamespace(mcp=_Mcp(servers, self.events))

    async def send_and_wait(self, prompt: str, **_kwargs):
        self.prompts.append(prompt)
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


def _write_external_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\n---\n# Test skill\n",
        encoding="utf-8",
    )
    return skill_dir


def _runner(*, mcp_servers: dict | None = None) -> StepRunner:
    return StepRunner(
        config=SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260720T000000-integration",
            mcp_servers=mcp_servers or {},
        ),
        console=Console(verbose=False, quiet=True),
    )


def _gate_patches(runner: StepRunner):
    return (
        patch.object(runner, "_run_asdw_data_verify_contract_gate", return_value=[]),
        patch.object(runner, "_run_ai_agent_capability_gate", return_value=[]),
        patch.object(runner, "_run_tdd_report_gate", return_value=[]),
        patch.object(
            runner,
            "_run_asdw_ui_red_unresolved_contract_gate",
            return_value=[],
        ),
        patch.object(runner, "_run_deploy_ac_gate", return_value=[]),
    )


@contextmanager
def _patched_runtime(
    runner: StepRunner,
    client: _Client,
    external_root: Path,
    work_dir: Path,
) -> Iterator[None]:
    """Run one Step through the SDK boundary without starting a real client."""
    copilot, copilot_session = _fake_copilot_modules(client)
    gates = _gate_patches(runner)
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                sys.modules,
                {"copilot": copilot, "copilot.session": copilot_session},
            )
        )
        stack.enter_context(
            patch(
                "hve.copilot_client_factory.create_copilot_client",
                return_value=client,
            )
        )
        stack.enter_context(
            patch(
                "hve.skill_resolver._external_skills_root",
                return_value=external_root,
            )
        )
        stack.enter_context(
            patch("hve.prompt_loader.load_prompt", return_value="")
        )
        stack.enter_context(
            patch("hve.runner._ensure_step_work_dir", return_value=work_dir)
        )
        for gate in gates:
            stack.enter_context(gate)
        yield


def test_aagd_foundry_required_step_connects_manifest_skill_prompt_and_mcp_layers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """AAGD 2.3はexact Skill、Prompt guard、pinned MCPを一つのsessionへ統合する。"""
    monkeypatch.chdir(_REPO_ROOT)
    external_root = tmp_path / "skills"
    foundry = _write_external_skill(external_root, "microsoft-foundry")
    unrelated = _write_external_skill(external_root, "azure-storage")
    duplicate_repository_skill = _write_external_skill(
        external_root,
        "ai-agent-capability-contract",
    )
    assert get_skill_directory(
        "ai-agent-capability-contract",
        external_skills_root=external_root,
    ) == _REPO_ROOT / ".github" / "skills" / "ai-agent-capability-contract"

    runner = _runner(mcp_servers={"context7": {"command": "integration-context7"}})
    client = _Client(
        [_server("azure"), _server("microsoft-learn"), _server("context7")]
    )
    with _patched_runtime(runner, client, external_root, tmp_path / "work" / "step"):
        result = asyncio.run(
            runner.run_step(
                "2.3",
                "AI Agent implementation",
                "T9 AAGD cross-layer probe",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                workflow_id="aagd",
            )
        )

    assert result is True
    assert len(client.create_session_kwargs) == 1
    options = client.create_session_kwargs[0]
    directories = options["skill_directories"]
    assert str(foundry) in directories
    assert str(external_root) not in directories
    assert str(unrelated) not in directories
    assert str(duplicate_repository_skill) not in directories
    assert options["mcp_servers"] == {
        "context7": {"command": "integration-context7"},
        "azure": _PINNED_AZURE,
        "microsoft-learn": _PINNED_LEARN,
    }
    assert client.sessions[0].events == ["mcp.list", "send_and_wait"]
    prompt = client.sessions[0].prompts[0]
    assert "このステップで必須の skill 名" in prompt
    assert "`microsoft-foundry`" in prompt
    assert "条件付き候補 skill 名" in prompt
    assert "`azure-ai`" in prompt
    assert "`entra-agent-id`" in prompt
    assert "`azure-storage`" not in prompt


def test_aagd_foundry_required_step_stops_before_session_when_exact_skill_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """AAGD required Foundry Skillの欠落はoptional fallbackに降格しない。"""
    monkeypatch.chdir(_REPO_ROOT)
    external_root = tmp_path / "skills"
    external_root.mkdir()
    runner = _runner()
    client = _Client([_server("azure"), _server("microsoft-learn")])

    with _patched_runtime(runner, client, external_root, tmp_path / "work" / "step"):
        result = asyncio.run(
            runner.run_step(
                "2.3",
                "AI Agent implementation",
                "T9 required skill missing probe",
                custom_agent="Dev-Microservice-Azure-AgentCoding",
                workflow_id="aagd",
            )
        )

    assert result is False
    assert client.create_session_kwargs == []


def test_active_candidate_map_matches_prompt_boundaries_and_excludes_unsupported_lifecycle_skills() -> None:
    """active Step mapはPrompt境界に一致し、未対応lifecycleを候補化しない。"""
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    optional = manifest["optional_skills"]

    for workflow_id, candidates_by_step in optional.items():
        workflow = get_workflow(workflow_id)
        assert workflow is not None, workflow_id
        for step_id in candidates_by_step:
            assert workflow.get_step(step_id) is not None, (workflow_id, step_id)

    candidates = {
        skill
        for candidates_by_step in optional.values()
        for skills in candidates_by_step.values()
        for skill in skills
    }
    assert not candidates & {
        "azure-prepare",
        "azure-deploy",
        "azure-hosted-copilot-sdk",
        "azure-cloud-migrate",
        "azure-enterprise-infra-planner",
        "python-appservice-deploy",
        "airunway-aks-setup",
    }
    validate_coordinates = {
        (workflow_id, step_id)
        for workflow_id, candidates_by_step in optional.items()
        for step_id, skills in candidates_by_step.items()
        if "azure-validate" in skills
    }
    assert validate_coordinates == {("asdw-web", "5.2"), ("adfdv", "4.2")}
    routing = (
        _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md"
    ).read_text(encoding="utf-8")
    assert "`azure-prepare` と `azure-deploy` は" in routing
    assert "`azure-validate` はread-only readiness reviewに限り" in routing
    assert "`asdw-web:5.2` / `adfdv:4.2`" in routing
    assert manifest["required_skills"]["aagd"] == {
        "2.3": ["microsoft-foundry"],
        "3": ["microsoft-foundry"],
    }
    assert optional["aagd"] == {
        "2.3": ["azure-ai", "entra-agent-id"],
        "3": ["azure-diagnostics"],
    }
    assert optional["asdw-web"].get("1.3") is None

    design = (
        _REPO_ROOT
        / ".github"
        / "prompts"
        / "Dev-Microservice-Azure-AddServiceDesign.prompt.md"
    ).read_text(encoding="utf-8")
    deploy = (
        _REPO_ROOT
        / ".github"
        / "prompts"
        / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md"
    ).read_text(encoding="utf-8")
    coding = (
        _REPO_ROOT
        / ".github"
        / "prompts"
        / "Dev-Microservice-Azure-AgentCoding.prompt.md"
    ).read_text(encoding="utf-8")
    agent_deploy = (
        _REPO_ROOT
        / ".github"
        / "prompts"
        / "Dev-Microservice-Azure-AgentDeploy.prompt.md"
    ).read_text(encoding="utf-8")
    agent_red = (
        _REPO_ROOT
        / ".github"
        / "prompts"
        / "Dev-Microservice-Azure-AgentTestCoding.prompt.md"
    ).read_text(encoding="utf-8")
    assert "Microsoft Foundry 選定時の external meta skill 利用" in design
    assert "Microsoft Foundry 配置時の external meta skill 利用" in deploy
    assert "Microsoft Foundry required meta skill workflow" in coding
    assert "Microsoft Foundry required meta skill workflow" in agent_deploy
    assert "microsoft-foundry" not in agent_red


def test_asdw_data_deploy_keeps_external_skill_and_azure_mcp_out_of_main_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """ASDW 1.3 は native pipeline で実行され、main session 自体を作らない。

    従来は Learn-only 境界へ Foundry external Skill と Azure MCP を混入させない
    契約だったが、native 化により external Skill / MCP の注入先自体が存在しない
    （より強い隔離）。
    """
    monkeypatch.chdir(_REPO_ROOT)
    monkeypatch.setenv("HVE_RUN_ID", "20260720T000000-integration")
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work"))
    external_root = tmp_path / "skills"
    foundry = _write_external_skill(external_root, "microsoft-foundry")
    runner = _runner(
        mcp_servers={
            "azure": {"command": "untrusted-azure"},
            "microsoft-learn": {"url": "https://untrusted.example/mcp"},
            "context7": {"command": "integration-context7"},
        }
    )
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

    with _patched_runtime(runner, client, external_root, tmp_path / "work" / "step"), patch.object(
        runner,
        "_build_step_permission_handler",
        return_value="permission-handler",
    ), patch(
        "hve.runner._validate_asdw_data_deploy_runtime_context",
        return_value=[],
    ), patch(
        "hve.runner._build_asdw_data_deploy_environment_snapshot",
        return_value={},
    ), patch(
        "hve.runner.execute_pipeline",
        return_value=(),
    ):
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Azure data deploy",
                "T9 ASDW isolation probe",
                custom_agent="Dev-Microservice-Azure-DataDeploy",
                workflow_id="asdw-web",
            )
        )

    # stage 結果が空なので Step は失敗するが、重要なのは
    # external Skill / Azure MCP を持つ main session が一切作られないこと。
    assert result is False
    # 隔離の前提（注入元）が実在することを固定し、主張を空虚化させない:
    # Azure MCP は runner config に存在し、Foundry external Skill も disk 上に在る。
    assert "azure" in runner.config.mcp_servers
    assert foundry.exists()
    # それでも main session は 1 つも生成されない = 注入先が存在しない（より強い隔離）。
    assert client.create_session_kwargs == []
    assert client.sessions == []
