"""test_agent_capability_steps.py — AAGD Step.6 / Step.7 の契約テスト。

AG-CAP-10（検索経路の適正化実測）と AG-CAP-09 の Microsoft 365 公開が、
registry / template / Prompt / io-contract / validator / runner gate へ
一貫して配線されていることを固定する。
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import (
    _validate_ai_agent_distribution,
    validate_m365_publish_report,
    validate_route_rightsizing_report,
)
from hve.workflow_registry import get_workflow

_REPO = Path(__file__).resolve().parents[2]
_PROMPTS = _REPO / ".github" / "prompts"
_TEMPLATES = _REPO / ".github" / "scripts" / "templates" / "aagd"
_CONTRACTS = _REPO / ".github" / "io-contracts"
_BASH_REGISTRY = _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
_CLOUD_WORKFLOW = _REPO / ".github" / "workflows" / "auto-ai-agent-dev-reusable.yml"

_STEPS = {
    "6": ("QA-AgentRouteRightsizingEval", "docs/agent/route-rightsizing-report.md"),
    "7": ("Dev-Agent-M365Publish", "docs/agent/m365-publish-report.md"),
}


def _step(step_id: str):
    workflow = get_workflow("aagd")
    assert workflow is not None
    for step in workflow.steps:
        if step.id == step_id:
            return step
    raise AssertionError(f"aagd Step.{step_id} が未登録")


class TestRegistryWiring(unittest.TestCase):
    def test_steps_are_registered_with_expected_agent_and_output(self) -> None:
        for step_id, (agent, output) in _STEPS.items():
            with self.subTest(step=step_id):
                step = _step(step_id)
                self.assertEqual(step.custom_agent, agent)
                self.assertEqual(step.output_paths, [output])

    def test_steps_depend_on_deploy_not_on_optional_eval(self) -> None:
        """Step.4 は enable_tool_search=no で外れるため依存先にしない。"""
        for step_id in _STEPS:
            with self.subTest(step=step_id):
                self.assertEqual(_step(step_id).depends_on, ["3"])

    def test_steps_are_not_fanned_out(self) -> None:
        """非機能・配布はアプリケーション単位の判定であり要素単位に割らない。"""
        for step_id in _STEPS:
            with self.subTest(step=step_id):
                step = _step(step_id)
                self.assertIsNone(step.fanout_parser)
                self.assertFalse(step.output_paths_template)

    def test_steps_require_the_capability_contract_skill(self) -> None:
        for step_id in _STEPS:
            with self.subTest(step=step_id):
                self.assertIn("ai-agent-capability-contract", _step(step_id).required_skills)


class TestPromptAndTemplate(unittest.TestCase):
    def test_prompt_files_exist(self) -> None:
        for _step_id, (agent, _output) in _STEPS.items():
            with self.subTest(agent=agent):
                self.assertTrue((_PROMPTS / f"{agent}.prompt.md").is_file())

    def test_template_paths_match_the_registry(self) -> None:
        for step_id in _STEPS:
            with self.subTest(step=step_id):
                step = _step(step_id)
                self.assertEqual(step.body_template_path, f"templates/aagd/step-{step_id}.md")
                self.assertTrue((_TEMPLATES / f"step-{step_id}.md").is_file())

    def test_io_contracts_exist_and_declare_the_output(self) -> None:
        for step_id, (agent, output) in _STEPS.items():
            with self.subTest(step=step_id):
                path = _CONTRACTS / f"{agent}--aagd--{step_id}.yaml"
                self.assertTrue(path.is_file(), path)
                self.assertIn(output, path.read_text(encoding="utf-8"))

    def test_rightsizing_prompt_requires_two_or_more_rungs(self) -> None:
        text = (_PROMPTS / "QA-AgentRouteRightsizingEval.prompt.md").read_text(encoding="utf-8")
        self.assertIn("2 行以上必須", text)
        self.assertIn("INSUFFICIENT", text)
        self.assertIn("search-routing.md", text)

    def test_publish_prompt_forbids_secret_metadata_and_version_reuse(self) -> None:
        text = (_PROMPTS / "Dev-Agent-M365Publish.prompt.md").read_text(encoding="utf-8")
        self.assertIn("公開メタデータへ secret", text)
        self.assertIn("同じ版を再利用しない", text)
        self.assertIn("削除・置換しない", text)


class TestCloudSurface(unittest.TestCase):
    def test_bash_registry_declares_both_steps(self) -> None:
        text = _BASH_REGISTRY.read_text(encoding="utf-8")
        for step_id, (agent, _output) in _STEPS.items():
            with self.subTest(step=step_id):
                self.assertIn(f'"id":"{step_id}","title":', text)
                self.assertIn(f'"custom_agent":"{agent}"', text)

    def test_reusable_workflow_creates_and_chains_both_steps(self) -> None:
        text = _CLOUD_WORKFLOW.read_text(encoding="utf-8")
        for step_id in _STEPS:
            with self.subTest(step=step_id):
                self.assertRegex(text, rf'"\[AAGD\] Step\.{step_id}: ')
                self.assertIn(f"S{step_id}_NUM", text)
        # Step.5 → 6 → 7 の順で活性化されること。
        self.assertIn(r"get_sub_issue_number '\[AAGD\] Step\.6:'", text)
        self.assertIn(r"get_sub_issue_number '\[AAGD\] Step\.7:'", text)
        transition = text.split('case "${STEP_MATCH}" in', 1)[-1]
        order = [transition.index(f'"{step_id}")') for step_id in ("5", "6", "7")]
        self.assertEqual(order, sorted(order), "遷移分岐は Step.5 → 6 → 7 の順で定義する")


def _distribution_section(components: str, channels: str = "Agent Plugins") -> str:
    return f"""- Channels: {channels}
- Plugin manifest: name は fan-out キーの小文字化。破壊的変更で minor を上げる
- Plugin components: {components}
- MCP exposure: streamable-http で orders の read Tool だけを公開する
- M365 publish: shared スコープで公開し、版は minor を上げる
- Metadata visibility: name と description のみを公開する
- Decision source: docs/agent/agent-architecture.md#Distribution
"""


class TestDistributionContractParsing(unittest.TestCase):
    """AG-CAP-09 設計側の `mcp.json` 要否判定（実装ゲートへ伝搬される）。"""

    def _parse(self, components: str) -> tuple[bool, list[str]]:
        metadata: dict = {}
        errors = _validate_ai_agent_distribution(_distribution_section(components), metadata)
        return bool(metadata["mcp_config_required"]), errors

    def test_explicit_required_selects_mcp_config(self) -> None:
        required, errors = self._parse("skills/: required, mcp.json: required")
        self.assertTrue(required)
        self.assertEqual(errors, [])

    def test_english_not_required_does_not_select(self) -> None:
        required, errors = self._parse("skills/: required, mcp.json: not-required")
        self.assertFalse(required)
        self.assertEqual(errors, [])

    def test_japanese_negation_does_not_select(self) -> None:
        """ラベル正規化は非 ASCII を落とすため、否定語を推測で判定しない。"""
        for components in (
            "mcp.json: 不要",
            "mcp.json: なし",
            "skills/ のみ（mcp.json は不要）",
        ):
            with self.subTest(components=components):
                required, _errors = self._parse(components)
                self.assertFalse(required)

    def test_missing_mcp_exposure_is_rejected_when_selected(self) -> None:
        metadata: dict = {}
        section = _distribution_section("mcp.json: required").replace(
            "- MCP exposure: streamable-http で orders の read Tool だけを公開する\n", ""
        )
        errors = _validate_ai_agent_distribution(section, metadata)
        self.assertTrue(metadata["mcp_config_required"])
        self.assertTrue(any("meaningful MCP exposure" in e for e in errors), errors)

    def test_missing_required_label_is_reported(self) -> None:
        metadata: dict = {}
        section = _distribution_section("mcp.json: not-required").replace(
            "- Decision source: docs/agent/agent-architecture.md#Distribution\n", ""
        )
        errors = _validate_ai_agent_distribution(section, metadata)
        self.assertTrue(any("missing meaningful Decision source" in e for e in errors), errors)

    def test_m365_channel_requires_publish_plan(self) -> None:
        metadata: dict = {}
        section = _distribution_section(
            "mcp.json: not-required", channels="Microsoft 365"
        ).replace("- M365 publish: shared スコープで公開し、版は minor を上げる\n", "")
        errors = _validate_ai_agent_distribution(section, metadata)
        self.assertTrue(any("meaningful M365 publish" in e for e in errors), errors)


def _rightsizing_report(rows: str, **overrides: str) -> str:
    labels = {
        "Schema-Version": "1",
        "Workflow": "aagd",
        "Step": "6",
        "Agent": "QA-AgentRouteRightsizingEval",
        "Measured-At": "2026-08-18T10:00:00Z",
        "Dataset": "業務問い合わせ実記録からの抽出",
        "Dataset-Size": "120",
        "Secret-Redaction": "confirmed",
    }
    labels.update(overrides)
    header = "\n".join(f"- {key}: {value}" for key, value in labels.items())
    return f"""# Route rightsizing report

{header}

| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |
|---|---|---|---|---|---|---|
{rows}

- Conclusion: KEEP
- Rationale: 段 4 は正答率が目標を下回り要件を満たさない。
- Recommended-Route: Agentic Retrieval（既定）
"""


_TWO_RUNGS = (
    "| 2 | Agentic Retrieval | 0.91 | 4200 | 3.1s | KEEP | run-a |\n"
    "| 4 | Cosmos DB hybrid | 0.72 | 900 | 0.6s | KEEP | run-b |"
)


def _validate_rightsizing(text: str) -> list[str]:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "route-rightsizing-report.md"
        path.write_text(text, encoding="utf-8")
        return validate_route_rightsizing_report(path, workflow_id="aagd", step_id="6")


class TestRouteRightsizingReport(unittest.TestCase):
    def test_valid_report_passes(self) -> None:
        self.assertEqual(_validate_rightsizing(_rightsizing_report(_TWO_RUNGS)), [])

    def test_missing_file_is_reported(self) -> None:
        errors = validate_route_rightsizing_report(
            Path("does-not-exist.md"), workflow_id="aagd", step_id="6"
        )
        self.assertTrue(any("not found" in e for e in errors), errors)

    def test_single_rung_is_rejected(self) -> None:
        """1 段だけの測定は比較ではない（AG-CAP-10 の中核契約）。"""
        rows = "| 2 | Agentic Retrieval | 0.91 | 4200 | 3.1s | KEEP | run-a |"
        errors = _validate_rightsizing(_rightsizing_report(rows))
        self.assertTrue(any("2 or more rungs" in e for e in errors), errors)

    def test_unknown_judgement_is_rejected(self) -> None:
        rows = _TWO_RUNGS.replace("| KEEP | run-b |", "| GOOD | run-b |")
        errors = _validate_rightsizing(_rightsizing_report(rows))
        self.assertTrue(any("'Judgement' must be one of" in e for e in errors), errors)

    def test_keep_without_metrics_is_rejected(self) -> None:
        rows = (
            "| 2 | Agentic Retrieval | 0.91 | 4200 | 3.1s | KEEP | run-a |\n"
            "| 4 | Cosmos DB hybrid |  |  |  | KEEP | run-b |"
        )
        errors = _validate_rightsizing(_rightsizing_report(rows))
        self.assertTrue(any("requires measured" in e for e in errors), errors)

    def test_not_measured_without_reason_is_rejected(self) -> None:
        rows = (
            "| 2 | Agentic Retrieval | 0.91 | 4200 | 3.1s | KEEP | run-a |\n"
            "| 4 | Cosmos DB hybrid |  |  |  | NOT_MEASURED |  |"
        )
        errors = _validate_rightsizing(_rightsizing_report(rows))
        self.assertTrue(any("requires a reason" in e for e in errors), errors)

    def test_missing_condition_label_is_rejected(self) -> None:
        text = _rightsizing_report(_TWO_RUNGS).replace("- Dataset-Size: 120\n", "")
        errors = _validate_rightsizing(text)
        self.assertTrue(any("'Dataset-Size' is missing" in e for e in errors), errors)

    def test_unconfirmed_redaction_is_rejected(self) -> None:
        errors = _validate_rightsizing(
            _rightsizing_report(_TWO_RUNGS, **{"Secret-Redaction": "skipped"})
        )
        self.assertTrue(any("must be confirmed" in e for e in errors), errors)

    def test_missing_recommended_route_is_rejected(self) -> None:
        text = _rightsizing_report(_TWO_RUNGS).replace(
            "- Recommended-Route: Agentic Retrieval（既定）\n", ""
        )
        errors = _validate_rightsizing(text)
        self.assertTrue(any("'Recommended-Route' is missing" in e for e in errors), errors)


def _publish_report(rows: str, **overrides: str) -> str:
    labels = {
        "Schema-Version": "1",
        "Workflow": "aagd",
        "Step": "7",
        "Agent": "Dev-Agent-M365Publish",
        "Published-At": "2026-08-18T10:00:00Z",
        "Publish-Scope": "shared",
        "Auth-Scheme": "Entra delegated",
        "Secret-Redaction": "confirmed",
    }
    labels.update(overrides)
    header = "\n".join(f"- {key}: {value}" for key, value in labels.items())
    return f"""# M365 publish report

{header}

| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |
|---|---|---|---|---|---|---|
{rows}

- Conclusion: 共有スコープで公開した。
- Rationale: 設計 Section 7.8 の Channels が Microsoft 365 を採用している。
- Consumer-Setup: Teams のアプリ一覧から追加し、初回のみ同意を求められる。
"""


_PUBLISHED_ROW = "| ag-01 | Microsoft 365 | shared | 1.0.0 | PUBLISHED | not-required | publish-log-a |"


def _validate_publish(text: str) -> list[str]:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "m365-publish-report.md"
        path.write_text(text, encoding="utf-8")
        return validate_m365_publish_report(path, workflow_id="aagd", step_id="7")


class TestM365PublishReport(unittest.TestCase):
    def test_valid_report_passes(self) -> None:
        self.assertEqual(_validate_publish(_publish_report(_PUBLISHED_ROW)), [])

    def test_not_selected_row_passes_with_reason(self) -> None:
        row = "| ag-01 | Microsoft 365 | n/a |  | NOT_SELECTED | n/a | 設計が当該チャネルを採っていない |"
        self.assertEqual(_validate_publish(_publish_report(row)), [])

    def test_missing_file_is_reported(self) -> None:
        errors = validate_m365_publish_report(
            Path("does-not-exist.md"), workflow_id="aagd", step_id="7"
        )
        self.assertTrue(any("not found" in e for e in errors), errors)

    def test_published_without_app_version_is_rejected(self) -> None:
        """版の再利用を防ぐため、公開したなら版が必ず要る。"""
        row = "| ag-01 | Microsoft 365 | shared |  | PUBLISHED | not-required | publish-log-a |"
        errors = _validate_publish(_publish_report(row))
        self.assertTrue(any("requires an App Version" in e for e in errors), errors)

    def test_not_selected_without_reason_is_rejected(self) -> None:
        row = "| ag-01 | Microsoft 365 | n/a |  | NOT_SELECTED | n/a |  |"
        errors = _validate_publish(_publish_report(row))
        self.assertTrue(any("requires a reason" in e for e in errors), errors)

    def test_unknown_judgement_is_rejected(self) -> None:
        row = _PUBLISHED_ROW.replace("PUBLISHED", "LIVE")
        errors = _validate_publish(_publish_report(row))
        self.assertTrue(any("'Judgement' must be one of" in e for e in errors), errors)

    def test_missing_consumer_setup_is_rejected(self) -> None:
        text = _publish_report(_PUBLISHED_ROW)
        text = re.sub(r"- Consumer-Setup:.*\n", "", text)
        errors = _validate_publish(text)
        self.assertTrue(any("'Consumer-Setup' is missing" in e for e in errors), errors)

    def test_wrong_step_label_is_rejected(self) -> None:
        errors = _validate_publish(_publish_report(_PUBLISHED_ROW, Step="5"))
        self.assertTrue(any("'Step' must be '7'" in e for e in errors), errors)


class TestRunnerGateWiring(unittest.TestCase):
    def _runner(self):
        from hve.runner import StepRunner

        return StepRunner.__new__(StepRunner)

    def test_gate_is_noop_for_other_agents(self) -> None:
        runner = self._runner()
        self.assertEqual(
            runner._run_agent_capability_report_gate("6", "QA-ToolSearchEval", "aagd"), []
        )

    def test_gate_is_noop_for_other_workflows(self) -> None:
        runner = self._runner()
        self.assertEqual(
            runner._run_agent_capability_report_gate("6", "QA-AgentRouteRightsizingEval", "aar"),
            [],
        )

    def test_gate_rejects_a_missing_report(self) -> None:
        runner = self._runner()
        with TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                errors = runner._run_agent_capability_report_gate(
                    "7", "Dev-Agent-M365Publish", "aagd"
                )
            finally:
                os.chdir(cwd)
        self.assertTrue(errors)
        self.assertTrue(any("not found" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
