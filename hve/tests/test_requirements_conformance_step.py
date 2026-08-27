"""ASDW-WEB 5.3 / ADFDV 4.3 / AAGD 5 / AAR 7（QA-RequirementsConformanceEval）の配線契約。

この Step の存在意義は「デプロイした構成が目標値を満たすかを実測で確かめる」こと。
設計文書の照合で完結する既存レビュー Step（WAF レビュー / 整合性チェック）と
役割が混ざらないよう、配線・成果物・禁止事項を固定する。

要件: hve-dev/requirement-definition.md §13.14（FR-WF-CONF-01〜06）
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hve.workflow_registry import get_workflow

_REPO = Path(__file__).resolve().parents[2]
_AGENT = "QA-RequirementsConformanceEval"
_PROMPT = _REPO / ".github" / "prompts" / f"{_AGENT}.prompt.md"
_SKILL = (
    _REPO
    / ".github"
    / "skills"
    / "testing"
    / "requirements-conformance-measurement"
    / "SKILL.md"
)

# FR-WF-CONF-01 の表をそのまま固定する。
_EXPECTED = {
    "asdw-web": {
        "step_id": "5.3",
        "depends_on": ["5.1", "5.2"],
        "output": "docs/azure/requirements-conformance-report.md",
        "template": ".github/prompts/steps/asdw-web/step-5.3.prompt.md",
    },
    "adfdv": {
        "step_id": "4.3",
        "depends_on": ["4.1", "4.2"],
        "output": "docs/dataflow/requirements-conformance-report.md",
        "template": ".github/prompts/steps/adfdv/step-4.3.prompt.md",
    },
    "aagd": {
        "step_id": "5",
        "depends_on": ["3"],
        "output": "docs/agent/requirements-conformance-report.md",
        "template": ".github/prompts/steps/aagd/step-5.prompt.md",
    },
    "aar": {
        "step_id": "7",
        "depends_on": ["6"],
        "output": "docs/azure/agentic-retrieval/requirements-conformance-report.md",
        "template": ".github/prompts/steps/aar/step-7.prompt.md",
    },
}

_WORKFLOW_IDS = sorted(_EXPECTED)


def _step(workflow_id: str):
    expected = _EXPECTED[workflow_id]
    for step in get_workflow(workflow_id).steps:
        if step.id == expected["step_id"]:
            return step
    raise AssertionError(
        f"{workflow_id} に Step.{expected['step_id']} が存在しない"
    )


@pytest.fixture(scope="module")
def prompt_text() -> str:
    return _PROMPT.read_text(encoding="utf-8")


@pytest.mark.parametrize("workflow_id", _WORKFLOW_IDS)
class TestRegistryWiring:
    def test_step_uses_the_shared_agent(self, workflow_id: str):
        """4 Workflow で同じ Agent を共有する（FR-WF-CONF-01）。"""
        assert _step(workflow_id).custom_agent == _AGENT

    def test_step_depends_on_expected_upstream(self, workflow_id: str):
        assert _step(workflow_id).depends_on == _EXPECTED[workflow_id]["depends_on"]

    def test_output_is_a_single_concrete_path(self, workflow_id: str):
        """非機能要件はアプリ単位の判定なので、成果物も 1 件に固定する。"""
        assert _step(workflow_id).output_paths == [_EXPECTED[workflow_id]["output"]]

    def test_step_does_not_fan_out(self, workflow_id: str):
        """要素単位へ分割すると同じ負荷条件を要素数分だけ測り直すことになる。"""
        step = _step(workflow_id)
        assert step.fanout_parser is None
        assert not step.fanout_static_keys

    def test_step_requires_the_measurement_skill(self, workflow_id: str):
        assert "requirements-conformance-measurement" in (
            _step(workflow_id).required_skills or []
        )

    def test_body_template_is_wired_and_exists(self, workflow_id: str):
        expected = _EXPECTED[workflow_id]["template"]
        step = _step(workflow_id)
        assert step.body_template_path == expected.removeprefix(
            ".github/scripts/"
        )
        assert (_REPO / expected).is_file()

    def test_io_contract_exists_and_declares_the_output(self, workflow_id: str):
        step_id = _EXPECTED[workflow_id]["step_id"]
        path = (
            _REPO
            / ".github"
            / "io-contracts"
            / f"{_AGENT}--{workflow_id}--{step_id}.yaml"
        )
        assert path.is_file(), f"{path} が無い"
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        outputs = [entry["path"] for entry in contract["outputs"]]
        assert outputs == [_EXPECTED[workflow_id]["output"]]


class TestConditionalExecution:
    def test_aar_step_follows_the_agentic_retrieval_policy(self):
        """AAR は Agentic Retrieval 専用 Workflow。方針が no なら全 Step が対象外。"""
        assert _step("aar").disabled_when_config == {
            "enable_agentic_retrieval": ["no"]
        }

    @pytest.mark.parametrize("workflow_id", ["asdw-web", "adfdv", "aagd"])
    def test_other_steps_are_unconditional(self, workflow_id: str):
        """tool search / Agentic Retrieval の方針に関係なく実測できる必要がある。"""
        assert not _step(workflow_id).disabled_when_config

    def test_aagd_depends_on_deploy_not_on_the_optional_eval_step(self):
        """AAGD Step 4 は enable_tool_search=no で外れるため依存先にしない。"""
        assert "4" not in _step("aagd").depends_on


class TestPromptContract:
    def test_prompt_exists(self):
        assert _PROMPT.is_file()

    def test_skill_exists(self):
        assert _SKILL.is_file()

    def test_prompt_fixes_the_four_judgement_values(self, prompt_text: str):
        for value in ("PASS", "FAIL", "NOT_MEASURED", "NO_TARGET"):
            assert value in prompt_text

    def test_prompt_forbids_deriving_targets_from_measurements(
        self, prompt_text: str
    ):
        """現状値を目標にすると改善余地の判定基準を失う（SRE Book Ch.4）。"""
        assert "逆算" in prompt_text

    def test_prompt_forbids_reporting_unmeasured_numbers(self, prompt_text: str):
        assert "測定していない数値" in prompt_text

    def test_prompt_does_not_require_creating_azure_resources(
        self, prompt_text: str
    ):
        """本 Step のための新規リソース作成を必須化しない（FR-WF-CONF-04）。"""
        assert "Azure リソースを新規作成しない" in prompt_text

    def test_prompt_declares_all_four_outputs(self, prompt_text: str):
        for expected in _EXPECTED.values():
            assert expected["output"] in prompt_text


class TestRunnerGateWiring:
    """成果物ゲートの対象表がレジストリからずれると、実測レポート無しで Step が通る。"""

    def test_gate_targets_match_the_registry(self):
        from hve.runner import StepRunner

        expected = {
            (workflow_id, _EXPECTED[workflow_id]["step_id"]): _EXPECTED[workflow_id][
                "output"
            ]
            for workflow_id in _WORKFLOW_IDS
        }
        assert StepRunner._REQUIREMENTS_CONFORMANCE_GATE_TARGETS == expected

    def test_gate_is_noop_for_other_agents(self):
        from hve.runner import StepRunner

        runner = StepRunner.__new__(StepRunner)
        assert (
            runner._run_requirements_conformance_gate(
                "5.3", "QA-AzureArchitectureReview", "asdw-web"
            )
            == []
        )

    def test_gate_rejects_a_missing_report(self, tmp_path, monkeypatch):
        from hve.runner import StepRunner

        runner = StepRunner.__new__(StepRunner)
        monkeypatch.chdir(tmp_path)
        errors = runner._run_requirements_conformance_gate(
            "5.3", "QA-RequirementsConformanceEval", "asdw-web"
        )
        assert errors
