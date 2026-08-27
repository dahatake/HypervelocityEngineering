"""AAR（Agentic Retrieval Add-on）ワークフローの契約テスト。

AAR は「既に API / データ資産があるアプリへ Agentic Retrieval だけを後付けする」
ための単独ワークフロー。AAD-WEB / ASDW-WEB を最初から流し直さずに済むことが
存在理由であり、以下を固定する。

- 既存 Agent を再利用し、新規 Agent は必要最小限に留めていること
- 実測評価 Step（reasoning effort 比較）が最終段にあること
- `enable_agentic_retrieval=no` で全 Step が無効化されること
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.workflow_registry import (
    get_workflow,
    list_workflows,
    resolve_disabled_step_ids,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_ID = "aar"

# 既存ワークフローと共有する Agent（AAR のために新規作成していないもの）
_REUSED_AGENTS = {
    "Arch-AgenticRetrieval-Detail",
    "Dev-Microservice-Azure-AgenticRetrievalDesign",
    "Dev-Microservice-Azure-AgenticRetrievalDeploy",
    "Arch-TDD-TestSpec",
    "QA-RequirementsConformanceEval",
}
# AAR のために新規作成した Agent
_NEW_AGENTS = {
    "Dev-Microservice-Azure-AgenticRetrievalTestCoding",
    "QA-AgenticRetrievalEval",
}


@pytest.fixture(scope="module")
def workflow():
    return get_workflow(_WORKFLOW_ID)


class TestRegistration:
    def test_is_listed(self):
        """GUI / CLI は list_workflows() を読むため、登録だけで両面に現れる。"""
        assert _WORKFLOW_ID in {w.id for w in list_workflows()}

    def test_has_resource_group_param(self, workflow):
        """デプロイ Step を含むため resource_group が必須パラメータ。"""
        assert "resource_group" in workflow.params


class TestAgentReuse:
    def test_reuses_existing_agents(self, workflow):
        agents = {s.custom_agent for s in workflow.steps if s.custom_agent}
        assert _REUSED_AGENTS <= agents

    def test_introduces_only_the_two_planned_agents(self, workflow):
        """新規 Agent が増えていないこと（Step を足すたび Agent を作らない）。"""
        agents = {s.custom_agent for s in workflow.steps if s.custom_agent}
        assert agents - _REUSED_AGENTS == _NEW_AGENTS

    @pytest.mark.parametrize("agent", sorted(_NEW_AGENTS))
    def test_new_agent_prompt_exists(self, agent: str):
        path = _REPO_ROOT / ".github" / "prompts" / f"{agent}.prompt.md"
        assert path.exists(), f"{agent} の Prompt が存在しない"


class TestEvaluationStep:
    """実測評価が無いと reasoning effort の選択を裏付けられない。"""

    def test_retrieval_evaluation_precedes_conformance(self, workflow):
        assert workflow.steps[-2].custom_agent == "QA-AgenticRetrievalEval"
        assert workflow.steps[-1].custom_agent == "QA-RequirementsConformanceEval"

    def test_evaluation_depends_on_deploy(self, workflow):
        """デプロイ済みリソースが無ければ実測できない。"""
        eval_step = next(
            s for s in workflow.steps if s.custom_agent == "QA-AgenticRetrievalEval"
        )
        deploy_ids = {
            s.id
            for s in workflow.steps
            if s.custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDeploy"
        }
        assert set(eval_step.depends_on) & deploy_ids

    def test_conformance_depends_on_retrieval_evaluation(self, workflow):
        eval_step = next(
            s for s in workflow.steps if s.custom_agent == "QA-AgenticRetrievalEval"
        )
        conformance = workflow.steps[-1]
        assert eval_step.id in conformance.depends_on

    def test_evaluation_prompt_forbids_unmeasured_numbers(self):
        """「測っていない数値を書かない」が Prompt に明記されている。"""
        text = (
            _REPO_ROOT / ".github" / "prompts" / "QA-AgenticRetrievalEval.prompt.md"
        ).read_text(encoding="utf-8")
        assert "未測定" in text
        assert "minimal" in text and "low" in text


class TestTestCodingStepIsRed:
    def test_test_coding_precedes_deploy(self, workflow):
        """TDD RED: テストはデプロイより前に書く。"""
        order = [s.id for s in workflow.steps]
        tc = next(
            s
            for s in workflow.steps
            if s.custom_agent == "Dev-Microservice-Azure-AgenticRetrievalTestCoding"
        )
        dp = next(
            s
            for s in workflow.steps
            if s.custom_agent == "Dev-Microservice-Azure-AgenticRetrievalDeploy"
        )
        assert order.index(tc.id) < order.index(dp.id)

    def test_prompt_rejects_skip_as_red(self):
        text = (
            _REPO_ROOT
            / ".github"
            / "prompts"
            / "Dev-Microservice-Azure-AgenticRetrievalTestCoding.prompt.md"
        ).read_text(encoding="utf-8")
        assert "skip は RED ではない" in text


class TestCrossSourceRequirementIsEnforced:
    """ユーザー要件（横断・最小クエリ回数）が Prompt で必須化されている。"""

    @pytest.mark.parametrize(
        "prompt_name",
        [
            "Dev-Microservice-Azure-AgenticRetrievalTestCoding",
            "QA-AgenticRetrievalEval",
        ],
    )
    def test_prompt_requires_cross_source_verification(self, prompt_name: str):
        text = (
            _REPO_ROOT / ".github" / "prompts" / f"{prompt_name}.prompt.md"
        ).read_text(encoding="utf-8")
        assert "Knowledge Source" in text
        assert "\u6a2a\u65ad" in text, "横断検証の要求が無い"


class TestDisabledByConfig:
    def test_all_steps_disabled_when_no(self, workflow):
        disabled = resolve_disabled_step_ids(
            _WORKFLOW_ID, {"enable_agentic_retrieval": "no"}
        )
        assert disabled == {s.id for s in workflow.steps}

    def test_no_steps_disabled_when_yes(self, workflow):
        assert not resolve_disabled_step_ids(
            _WORKFLOW_ID, {"enable_agentic_retrieval": "yes"}
        )


class TestTemplatesExist:
    def test_every_step_template_is_present(self, workflow):
        for step in workflow.steps:
            assert step.body_template_path, f"Step {step.id} に template 宣言が無い"
            path = _REPO_ROOT / step.body_template_path
            assert path.exists(), f"{path} が存在しない"
