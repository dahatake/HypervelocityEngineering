"""ASDW-WEB Step.1.2/1.3 の Azure Policy/private Skill routing 契約。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.orchestrator import _check_required_skills_for_active_steps
from hve.runner import StepRunner
from hve.skill_resolver import (
    get_required_skills_for_step,
    load_skill_manifest,
    validate_skill_names,
)
from hve.workflow_registry import (
    canonicalize_workflow_id,
    get_step,
    get_workflow,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO_ROOT / "hve" / "skill_manifest.json"
_EXPECTED = ["microservice-design-guide", "azure-cli-deploy-scripts"]
_DATA_STEP_AGENTS = {
    "1.2": "Dev-Microservice-Azure-DataTestCoding",
    "1.3": "Dev-Microservice-Azure-DataDeploy",
}


def test_asdw_data_steps_require_the_policy_private_connectivity_skill() -> None:
    load_skill_manifest.cache_clear()
    for step_id in ("1.2", "1.3"):
        assert get_required_skills_for_step(
            "asdw-web", step_id, step_declared_required=[]
        ) == _EXPECTED


def test_asdw_alias_and_canonical_id_resolve_identical_data_step_skills() -> None:
    load_skill_manifest.cache_clear()
    for step_id in _DATA_STEP_AGENTS:
        assert get_required_skills_for_step(
            "asdw", step_id, step_declared_required=[]
        ) == get_required_skills_for_step(
            "asdw-web", step_id, step_declared_required=[]
        ) == _EXPECTED


def test_workflow_alias_canonicalization_is_registry_owned() -> None:
    assert canonicalize_workflow_id("ASDW") == "asdw-web"
    assert canonicalize_workflow_id("ASDW-WEB") == "asdw-web"
    assert canonicalize_workflow_id("unknown-workflow") == "unknown-workflow"


def test_asdw_data_step_routing_is_manifest_only_not_registry_duplicate() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    required = manifest["required_skills"]["asdw-web"]
    assert required["1.2"] == ["azure-cli-deploy-scripts"]
    assert required["1.3"] == ["azure-cli-deploy-scripts"]
    for step_id in _DATA_STEP_AGENTS:
        step = get_step("asdw-web", step_id)
        assert step is not None
        assert step.required_skills == []


def test_policy_private_skill_is_scoped_to_exact_manifest_coordinates() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    skill_name = "azure-cli-deploy-scripts"
    coordinates = {
        (workflow_id, step_id)
        for workflow_id, steps in manifest["required_skills"].items()
        for step_id, skills in steps.items()
        if skill_name in skills
    }
    assert coordinates == {("asdw-web", "1.2"), ("asdw-web", "1.3")}
    assert all(
        skill_name not in skills
        for skills in manifest["workflow_defaults"].values()
    )
    assert get_required_skills_for_step("asdw-web", "1.1", []) == [
        "microservice-design-guide"
    ]
    assert skill_name not in get_required_skills_for_step("aad-web", "1.2", [])


def test_policy_private_skill_names_are_discoverable() -> None:
    missing, _resolved, _suggestions = validate_skill_names(_EXPECTED)
    assert missing == []


@pytest.mark.parametrize("workflow_id", ["asdw-web", "asdw"])
def test_orchestrator_precheck_routes_data_step_skills_for_aliases(
    workflow_id: str,
) -> None:
    captured: list[list[str]] = []

    def _capture(skill_names: list[str]):
        captured.append(list(skill_names))
        return [], {}, {}

    with patch(
        "hve.skill_resolver.get_required_skills_for_step",
        wraps=get_required_skills_for_step,
    ) as resolver_spy, patch(
        "hve.skill_resolver.validate_skill_names",
        side_effect=_capture,
    ):
        result = _check_required_skills_for_active_steps(
            wf=get_workflow(workflow_id),
            workflow_id=workflow_id,
            active_steps=set(_DATA_STEP_AGENTS),
            console=MagicMock(),
        )

    assert result["should_abort"] is False
    assert captured == [_EXPECTED, _EXPECTED]
    assert [
        call.kwargs["workflow_id"] for call in resolver_spy.call_args_list
    ] == ["asdw-web", "asdw-web"]


def test_orchestrator_precheck_validates_fanout_child_against_base_step_skills() -> None:
    with patch(
        "hve.skill_resolver.validate_skill_names",
        return_value=(["knowledge-management"], {}, {"knowledge-management": []}),
    ):
        result = _check_required_skills_for_active_steps(
            wf=get_workflow("akm"),
            workflow_id="akm",
            active_steps={"1/D01"},
            console=MagicMock(),
        )

    assert result["should_abort"] is True
    assert result["blocked"] is True
    assert result["blocked_step_ids"] == ["1"]


class _PromptCaptureSession:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def send_and_wait(self, prompt: str, **_kwargs):
        self.prompts.append(prompt)
        return None

    def on(self, _handler):
        return None

    async def disconnect(self):
        return None


class _PromptCaptureClient:
    def __init__(self) -> None:
        self.session = _PromptCaptureSession()

    async def start(self):
        return None

    async def stop(self):
        return None

    async def create_session(self, **_kwargs):
        return self.session


def _capture_runner_main_prompt(workflow_id: str, step_id: str) -> str:
    fake_client = _PromptCaptureClient()
    fake_copilot = types.ModuleType("copilot")
    fake_copilot_session = cast(Any, types.ModuleType("copilot.session"))

    class _PermissionHandler:
        @staticmethod
        async def approve_all(*_args, **_kwargs):
            return True

    fake_copilot_session.PermissionHandler = _PermissionHandler
    config = SDKConfig(
        dry_run=False,
        model="claude-opus-4.7",
        auto_qa=False,
        auto_contents_review=False,
        auto_self_improve=False,
        run_id=f"t04-{workflow_id}-{step_id.replace('.', '-')}",
    )
    runner = StepRunner(
        config=config,
        console=Console(verbose=False, quiet=True),
        workflow_params={"resource_group": "test-resource-group"},
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.dict(
            os.environ,
            {"HVE_RUN_ID": config.run_id},
            clear=False,
        ), patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=fake_client,
        ), patch(
            "hve.prompt_loader.load_prompt",
            return_value="",
        ), patch(
            "hve.runner._ensure_step_work_dir",
            return_value=Path(temp_dir) / "work" / "step",
        ), patch(
            "hve.workflow_registry.get_step",
            wraps=get_step,
        ) as get_step_spy, patch(
            "hve.skill_resolver.get_required_skills_for_step",
            wraps=get_required_skills_for_step,
        ) as resolver_spy, patch(
            "hve.workflow_registry.canonicalize_workflow_id",
            wraps=canonicalize_workflow_id,
        ), patch(
            "hve.runner._validate_asdw_data_deploy_runtime_context",
            return_value=[],
        ), patch.object(
            runner,
            "_build_step_permission_handler",
            return_value="permission-handler",
        ), patch.object(
            runner,
            "_run_asdw_data_verify_contract_gate",
            return_value=[],
        ), patch(
            "hve.runner._build_asdw_data_deploy_environment_snapshot",
            return_value={},
        ), patch(
            "hve.runner.ensure_asdw_data_producers",
            return_value=types.SimpleNamespace(
                status="reused",
                audit_mode="sql-ledger-digest",
            ),
        ), patch.object(
            runner,
            "_run_tdd_report_gate",
            return_value=[],
        ), patch.object(
            runner,
            "_run_deploy_ac_gate",
            return_value=[],
        ):
            succeeded = asyncio.run(
                runner.run_step(
                    step_id=step_id,
                    title=f"ASDW data Step.{step_id}",
                    prompt="T04 production prompt probe",
                    custom_agent=_DATA_STEP_AGENTS[step_id],
                    workflow_id=workflow_id,
                )
            )

    assert succeeded is True
    assert len(fake_client.session.prompts) == 1
    get_step_spy.assert_called_once_with("asdw-web", step_id)
    assert resolver_spy.call_args.kwargs["workflow_id"] == "asdw-web"
    return fake_client.session.prompts[0]


@pytest.mark.parametrize("workflow_id", ["asdw-web", "asdw"])
@pytest.mark.parametrize("step_id", ["1.2"])
def test_runner_final_prompt_includes_data_step_skill_guard(
    workflow_id: str,
    step_id: str,
) -> None:
    """SDK セッションを使う data Step の final prompt に skill ガードが含まれる。

    Step 1.3（APP-009）は HVE-owned native pipeline で実行され SDK セッションを
    作らないため、final prompt の契約対象外。当該契約は
    `hve/tests/test_runner_asdw_data_pipeline.py` が固定する。
    """
    prompt = _capture_runner_main_prompt(workflow_id, step_id)
    assert "## Skill 利用ガード" in prompt
    assert "このステップで必須の skill 名" in prompt
    for skill_name in _EXPECTED:
        assert f"`{skill_name}`" in prompt


def test_data_deploy_step_requires_the_skill_guard_without_an_sdk_session() -> None:
    """Step 1.3 の skill 契約は registry 側で保持される。

    native pipeline 化で SDK prompt が無くなっても、必須 skill 宣言自体は
    失われていないことを固定する。
    """
    resolved = get_required_skills_for_step(
        workflow_id="asdw-web",
        step_id="1.3",
    )
    for skill_name in _EXPECTED:
        assert skill_name in resolved


def test_template_engine_uses_registry_alias_canonicalizer() -> None:
    from hve import template_engine

    with patch.object(
        template_engine,
        "canonicalize_workflow_id",
        return_value="asdw-web",
    ) as canonicalize_spy:
        block = template_engine.format_agentic_retrieval_block("legacy-asdw")

    canonicalize_spy.assert_called_once_with("legacy-asdw")
    assert block


def test_cli_wizard_uses_registry_alias_canonicalizer() -> None:
    from hve import __main__ as cli_main

    with patch.object(
        cli_main,
        "canonicalize_workflow_id",
        return_value="asdw-web",
    ) as canonicalize_spy:
        answers = cli_main._collect_agentic_retrieval_wizard_answers(
            MagicMock(),
            "legacy-asdw",
            is_quick_auto=True,
        )

    canonicalize_spy.assert_called_once_with("legacy-asdw")
    assert answers
