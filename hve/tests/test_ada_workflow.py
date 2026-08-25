"""ADA (Agent Data Architecture) ワークフローの契約テスト。

ADA は AAS を基に、画面に依存する 3 Step を除外した AI Agent 向けの
データ資産設計ワークフロー。除外理由と再利用対象を固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.workflow_registry import (
    WORKFLOW_CATEGORIES,
    get_workflow,
    list_workflows,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ADA が AAS / AAD-WEB から再利用する Custom Agent。
# 新規 Agent は Step.8 の Arch-AgentDataAsset のみ。
# Step.1（Arch-ApplicationAnalytics）は ARD Step 4.1 へ移管され廃止済み。
_REUSED_AGENTS = {
    "2": "Arch-Microservice-DomainAnalytics",
    "3": "Arch-Microservice-ServiceIdentify",
    "4.1": "Arch-DataModeling",
    "4.2": "Arch-DataModeling",
    "5": "Arch-DataCatalog",
    "6": "Arch-PersonaCatalog",
    "7": "Arch-Microservice-ServiceDetail",
    "9": "Arch-TDD-TestStrategy",
}

_NEW_AGENT_STEP = "8"
_NEW_AGENT = "Arch-AgentDataAsset"


def _ada():
    return get_workflow("ada")


def _steps_by_id():
    return {step.id: step for step in _ada().steps}


def test_ada_is_registered_and_listed() -> None:
    assert "ada" in {wf.id for wf in list_workflows()}
    assert _ada().name == "Agent Data Architecture"
    assert _ada().label_prefix == "ada"


def test_ada_belongs_to_ai_agent_category() -> None:
    categories = dict(WORKFLOW_CATEGORIES)
    assert "ada" in categories["AI Agent"]
    # ADA は AI Agent 経路の起点なので AAG より前に並べる。
    ai_agent = categories["AI Agent"]
    assert ai_agent.index("ada") < ai_agent.index("aag")


def test_ada_has_nine_steps_in_expected_order() -> None:
    assert [s.id for s in _ada().steps] == [
        "2", "3", "4.1", "4.2", "5", "6", "7", "8", "9",
    ]


def test_ada_reuses_existing_agents_and_adds_only_one() -> None:
    steps = _steps_by_id()
    for step_id, agent in _REUSED_AGENTS.items():
        assert steps[step_id].custom_agent == agent, step_id
    assert steps[_NEW_AGENT_STEP].custom_agent == _NEW_AGENT

    new_agents = {
        s.custom_agent for s in _ada().steps
    } - set(_REUSED_AGENTS.values())
    assert new_agents == {_NEW_AGENT}


def test_ada_excludes_screen_dependent_artifacts() -> None:
    """AAS Step.1 / 5 / 8 相当の成果物を出力しないこと。"""
    produced = {
        path
        for step in _ada().steps
        for path in (step.output_paths or [])
    }
    for excluded in (
        "docs/catalog/app-arch-catalog.md",
        "docs/catalog/service-catalog-matrix.md",
        "docs/catalog/persona-screen-catalog.md",
    ):
        assert excluded not in produced


def test_ada_never_requires_screen_inputs() -> None:
    for step in _ada().steps:
        for path in step.required_input_paths:
            assert "screen" not in path, (step.id, path)
            assert "service-catalog-matrix" not in path, (step.id, path)


def test_ada_step7_fans_out_over_service_catalog() -> None:
    step = _steps_by_id()["7"]
    assert step.fanout_parser == "service_catalog"
    assert step.additional_prompt_template_path == "hve/prompt/fanout/ada/_common.md"
    assert step.output_paths_template == [
        "docs/services/{serviceId}-{serviceNameSlug}-description.md"
    ]


def test_ada_step8_publishes_capability_contract_skill() -> None:
    step = _steps_by_id()["8"]
    assert "ai-agent-capability-contract" in step.required_skills
    assert step.output_paths == ["docs/catalog/unstructured-data-catalog.md"]


def test_ada_test_strategy_depends_on_all_catalogs() -> None:
    step = _steps_by_id()["9"]
    assert sorted(step.depends_on) == ["6", "7", "8"]


@pytest.mark.parametrize("step_id", sorted(_REUSED_AGENTS) + [_NEW_AGENT_STEP])
def test_ada_body_templates_exist(step_id: str) -> None:
    step = _steps_by_id()[step_id]
    assert step.body_template_path == f"templates/ada/step-{step_id}.md"
    path = _REPO_ROOT / ".github" / "scripts" / step.body_template_path
    assert path.is_file(), path


def test_ada_fanout_common_prompt_exists() -> None:
    path = _REPO_ROOT / "hve" / "prompt" / "fanout" / "ada" / "_common.md"
    assert path.is_file(), path


def test_new_agent_prompt_exists() -> None:
    path = _REPO_ROOT / ".github" / "prompts" / f"{_NEW_AGENT}.prompt.md"
    assert path.is_file(), path


@pytest.mark.parametrize(
    "contract",
    [
        "Arch-Microservice-DomainAnalytics--ada--2",
        "Arch-Microservice-ServiceIdentify--ada--3",
        "Arch-DataModeling--ada--4.1",
        "Arch-DataModeling--ada--4.2",
        "Arch-DataCatalog--ada--5",
        "Arch-PersonaCatalog--ada--6",
        "Arch-Microservice-ServiceDetail--ada--7",
        "Arch-AgentDataAsset--ada--8",
        "Arch-TDD-TestStrategy--ada--9",
    ],
)
def test_ada_io_contracts_exist(contract: str) -> None:
    path = _REPO_ROOT / ".github" / "io-contracts" / f"{contract}.yaml"
    assert path.is_file(), path


def test_aag_inputs_are_rewired_to_ada_artifacts() -> None:
    """AAG は ADA 成果物を必須にし、画面・matrix・Azure 系を必須から外す。"""
    for step in get_workflow("aag").steps:
        required = set(step.required_input_paths)
        assert "docs/catalog/data-catalog.md" in required, step.id
        assert "docs/catalog/unstructured-data-catalog.md" in required, step.id
        assert "docs/catalog/persona-catalog.md" in required, step.id
        for removed in (
            "docs/catalog/screen-catalog-APP-*.md",
            "docs/catalog/service-catalog-matrix.md",
            "docs/screen/{screenId}-*.md",
            "docs/azure/azure-services-data.md",
            "docs/azure/azure-services-additional.md",
        ):
            assert removed not in required, (step.id, removed)


def test_aagd_inputs_do_not_require_screen_artifacts() -> None:
    for step in get_workflow("aagd").steps:
        for path in step.required_input_paths:
            assert "screen" not in path, (step.id, path)
            assert "service-catalog-matrix" not in path, (step.id, path)
