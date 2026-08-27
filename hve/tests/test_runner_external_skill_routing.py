"""T4: main/sub-sessionへのexternal Skill directory routing契約。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner, _repository_skill_directories


class _FakeSession:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.rpc = types.SimpleNamespace(
            mcp=types.SimpleNamespace(list=self._list_mcp_servers)
        )

    async def _list_mcp_servers(self):
        return types.SimpleNamespace(
            servers=[
                types.SimpleNamespace(
                    name="azure",
                    status=types.SimpleNamespace(value="connected"),
                    error=None,
                ),
                types.SimpleNamespace(
                    name="microsoft-learn",
                    status=types.SimpleNamespace(value="connected"),
                    error=None,
                ),
            ]
        )

    async def send_and_wait(self, prompt: str, **_kwargs):
        self.prompts.append(prompt)
        if "合格判定" in prompt:
            return types.SimpleNamespace(
                data=types.SimpleNamespace(content="- 合格判定: ✅ PASS")
            )
        return None

    async def disconnect(self) -> None:
        return None

    def on(self, _handler) -> None:
        return None


class _FakeClient:
    def __init__(self, *, reject_skill_directories: bool = False) -> None:
        self.create_session_kwargs: list[dict] = []
        self.sessions: list[_FakeSession] = []
        self.reject_skill_directories = reject_skill_directories

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def create_session(self, **kwargs):
        self.create_session_kwargs.append(kwargs)
        if self.reject_skill_directories and "skill_directories" in kwargs:
            raise TypeError(
                "create_session() got an unexpected keyword argument "
                "'skill_directories'"
            )
        session = _FakeSession()
        self.sessions.append(session)
        return session


def _fake_copilot_modules(client: _FakeClient):
    copilot: Any = types.ModuleType("copilot")
    copilot.CopilotClient = lambda **_kwargs: client

    class _RuntimeConnection:
        @staticmethod
        def for_stdio(**_kwargs):
            return object()

        @staticmethod
        def for_uri(*_args, **_kwargs):
            return object()

    copilot.RuntimeConnection = _RuntimeConnection
    session: Any = types.ModuleType("copilot.session")

    class _PermissionHandler:
        @staticmethod
        async def approve_all(*_args, **_kwargs):
            return True

    session.PermissionHandler = _PermissionHandler
    return copilot, session


def _write_external_skill(root: Path, name: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\n---\n# Test skill\n",
        encoding="utf-8",
    )
    return directory


# 利用者環境へインストールされる Skill。CI には存在しないので実在を要求できない。
_KNOWN_EXTERNAL_SKILLS = frozenset({"microsoft-foundry", "azure-ai"})


def _runner(
    *,
    review_model: str | None = None,
    qa_model: str | None = None,
) -> StepRunner:
    return StepRunner(
        config=SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            review_model=review_model,
            qa_model=qa_model,
            auto_qa=qa_model is not None,
            auto_contents_review=review_model is not None,
            auto_self_improve=False,
            run_id="20260720T000000-external-routing",
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
        patch.object(runner, "_check_diff_after_improvement", return_value=[]),
    )


def test_main_session_adds_required_and_available_optional_external_skills_only() -> None:
    runner = _runner()
    client = _FakeClient()
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        foundry = _write_external_skill(external_root, "microsoft-foundry")
        azure_ai = _write_external_skill(external_root, "azure-ai")
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
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T4 main routing probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    assert len(client.create_session_kwargs) == 1
    directories = client.create_session_kwargs[0]["skill_directories"]
    assert str(foundry) in directories
    assert str(azure_ai) in directories
    assert str(external_root) not in directories
    prompt = client.sessions[0].prompts[0]
    assert "このステップで必須の skill 名" in prompt
    assert "`microsoft-foundry`" in prompt
    assert "条件付き候補 skill 名" in prompt
    assert "`azure-ai`" in prompt


def test_review_sub_session_receives_required_external_skill_but_not_optional_candidate() -> None:
    runner = _runner(review_model="gpt-5.4")
    client = _FakeClient()
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        foundry = _write_external_skill(external_root, "microsoft-foundry")
        azure_ai = _write_external_skill(external_root, "azure-ai")
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
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T4 review routing probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    assert len(client.create_session_kwargs) == 2
    main_directories = client.create_session_kwargs[0]["skill_directories"]
    review_directories = client.create_session_kwargs[1]["skill_directories"]
    assert str(foundry) in main_directories
    assert str(azure_ai) in main_directories
    assert str(foundry) in review_directories
    assert str(azure_ai) not in review_directories


def test_pre_qa_sub_session_receives_required_external_skill_but_not_optional_candidate() -> None:
    runner = _runner(qa_model="gpt-5.4")
    client = _FakeClient()
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        foundry = _write_external_skill(external_root, "microsoft-foundry")
        azure_ai = _write_external_skill(external_root, "azure-ai")
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
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T4 pre-QA routing probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    assert len(client.create_session_kwargs) == 2
    main_directories = client.create_session_kwargs[0]["skill_directories"]
    pre_qa_directories = client.create_session_kwargs[1]["skill_directories"]
    assert str(foundry) in main_directories
    assert str(azure_ai) in main_directories
    assert str(foundry) in pre_qa_directories
    assert str(azure_ai) not in pre_qa_directories
    assert str(external_root) not in pre_qa_directories


def test_optional_only_external_skill_allows_sdk_skill_directory_fallback() -> None:
    runner = _runner()
    client = _FakeClient(reject_skill_directories=True)
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        azure_ai = _write_external_skill(external_root, "azure-ai")
        gates = _gate_patches(runner)
        with patch.dict(
            sys.modules,
            {"copilot": copilot, "copilot.session": copilot_session},
        ), patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.skill_resolver.get_required_skills_for_step",
            return_value=["microservice-design-guide"],
        ), patch(
            "hve.skill_resolver._external_skills_root",
            return_value=external_root,
        ), patch(
            "hve.prompt_loader.load_prompt",
            return_value="",
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T4 optional fallback probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    assert len(client.create_session_kwargs) == 2
    assert str(azure_ai) in client.create_session_kwargs[0]["skill_directories"]
    assert "skill_directories" not in client.create_session_kwargs[1]


def test_required_external_skill_rejects_sdk_skill_directory_fallback() -> None:
    runner = _runner()
    client = _FakeClient(reject_skill_directories=True)
    copilot, copilot_session = _fake_copilot_modules(client)

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        foundry = _write_external_skill(external_root, "microsoft-foundry")
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
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "T4 required fallback rejection probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is False
    assert len(client.create_session_kwargs) == 1
    assert str(foundry) in client.create_session_kwargs[0]["skill_directories"]


def _repository_skills_root() -> Path:
    return Path.cwd() / ".github" / "skills"


def test_repository_skill_directories_default_exposes_root_only() -> None:
    """FR-CLI-73: Step コンテキスト無しでは `.github/skills` root のみを公開する。

    `.github/skills` 直下の全ディレクトリを無条件に公開してはならない。
    """
    root = _repository_skills_root()
    assert root.is_dir()

    directories = _repository_skill_directories()

    assert directories == [str(root)]


def test_repository_skill_directories_scope_to_declared_skills() -> None:
    """FR-CLI-73: 宣言された Skill のディレクトリだけを root に追加公開する。

    `test-strategy-template` は `.github/skills/testing/` 配下にあるため、
    CLI の深さ 1 探索用に `testing` を公開する必要がある。一方、宣言されて
    いない `harness` / `output` / `azure-skills` は公開してはならない。
    """
    root = _repository_skills_root()
    assert root.is_dir()

    directories = _repository_skill_directories(["test-strategy-template"])

    assert str(root) in directories
    assert str(root / "testing") in directories
    assert str(root / "harness") not in directories
    assert str(root / "output") not in directories
    assert str(root / "azure-skills") not in directories
    assert str(root / "knowledge-management") not in directories


def test_declared_required_repository_skills_stay_resolvable(tmp_path) -> None:
    """FR-CLI-73: `required_skills` で宣言された Skill は必ず解決可能である。

    公開範囲の縮約後も、当該 Step の必須 Skill は
    (a) `skill_resolver` で解決でき、
    (b) repository-owned なら公開ディレクトリ集合から探索可能でなければならない。

    external Skill は利用者環境へインストールされるもので CI には存在しないため、
    既知の名前だけを external として扱い、インストール済みルートを注入して
    fail-closed 解決が成立することを固定する。未知の名前はタイプミスとして落とす。
    """
    from hve.skill_resolver import _skills_root, discover_available_skills, get_skill_directory

    required = StepRunner._get_required_skills_for_step("aagd", "2.3", None)
    assert "test-strategy-template" in required
    assert "ai-agent-capability-contract" in required

    directories = set(_repository_skill_directories(required))
    available = discover_available_skills()

    external_root = tmp_path / "agents-skills"
    external_root.mkdir()
    for skill in required:
        subpath = available.get(skill)
        if subpath is None:
            assert skill in _KNOWN_EXTERNAL_SKILLS, f"unknown required skill: {skill}"
            _write_external_skill(external_root, skill)
            assert (
                get_skill_directory(skill, external_skills_root=external_root)
                is not None
            ), f"unresolvable required external skill: {skill}"
            continue
        assert get_skill_directory(skill) is not None, f"unresolvable required skill: {skill}"
        skill_dir = _skills_root() / subpath
        assert str(skill_dir.parent) in directories, (
            f"required repository skill is not discoverable: {skill}"
        )


def test_main_session_skill_directories_exclude_undeclared_repository_skills() -> None:
    """FR-CLI-73: セッションへ無関係な repository Skill ディレクトリを渡さない。"""
    runner = _runner()
    client = _FakeClient()
    copilot, copilot_session = _fake_copilot_modules(client)
    root = _repository_skills_root()

    with tempfile.TemporaryDirectory() as temp_dir:
        external_root = Path(temp_dir) / "skills"
        _write_external_skill(external_root, "microsoft-foundry")
        _write_external_skill(external_root, "azure-ai")
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
        ), gates[0], gates[1], gates[2], gates[3], gates[4], gates[5]:
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "FR-CLI-73 repository skill scope probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

    assert result is True
    directories = client.create_session_kwargs[0]["skill_directories"]
    assert str(root) in directories
    assert str(root / "testing") in directories
    assert str(root / "harness") not in directories
    assert str(root / "output") not in directories
    assert str(root / "azure-skills") not in directories
    assert str(root / "observability") not in directories
    assert str(root / "cicd") not in directories
