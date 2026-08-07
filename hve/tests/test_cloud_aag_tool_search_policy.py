"""Cloud AAG（Issue Form + `auto-ai-agent-design-reusable.yml`）の Tool Search 方針契約。

FR-WF-AAG-01 / FR-WF-AAGD-04。
Issue Form の選択値が Root タグ → Step.3 本文 → design validator まで
同じ値で届き、不正値が既定へ黙って化けないことを検査する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORM = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "ai-agent-design.yml"
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "auto-ai-agent-design-reusable.yml"


@pytest.fixture(scope="module")
def form_fields() -> dict:
    data = yaml.safe_load(_FORM.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data["body"] if "id" in item}


@pytest.fixture(scope="module")
def workflow() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


class TestIssueForm:
    def test_declares_the_tool_search_dropdown(self, form_fields):
        assert "enable_tool_search" in form_fields
        assert form_fields["enable_tool_search"]["type"] == "dropdown"

    @pytest.mark.parametrize("policy", ["auto", "yes", "no"])
    def test_offers_each_policy(self, form_fields, policy):
        options = form_fields["enable_tool_search"]["attributes"]["options"]
        assert any(option.startswith(policy) for option in options)

    def test_defaults_to_auto(self, form_fields):
        field = form_fields["enable_tool_search"]["attributes"]
        assert field["options"][field["default"]].startswith("auto")

    def test_distinguishes_from_the_hve_setting(self, form_fields):
        """HVE 自身の Tool Search 設定と混同させない。"""
        description = form_fields["enable_tool_search"]["attributes"]["description"]
        assert "HVE" in description

    def test_yaml_is_parseable(self):
        assert yaml.safe_load(_FORM.read_text(encoding="utf-8"))["body"]


class TestWorkflowWiring:
    def test_yaml_is_parseable(self):
        assert yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    def test_parses_the_form_value(self, workflow):
        assert "tool_search_policy" in workflow

    def test_missing_value_defaults_to_auto(self, workflow):
        assert 'tool_search_policy = "auto"' in workflow

    def test_invalid_value_fails(self, workflow):
        """既定へ丸めず Root 初期化を失敗させる。"""
        assert "Invalid tool search policy" in workflow

    def test_writes_the_root_metadata_tag(self, workflow):
        assert "tool-search-policy" in workflow

    def test_injects_only_into_step_3(self, workflow):
        """Step.1 / Step.2 へ不要な Toolbox 詳細を注入しない。"""
        assert "TOOL_SEARCH_SECTION" in workflow
        assert workflow.count('"${TOOL_SEARCH_SECTION}"') == 1
        body_s1 = workflow.split("BODY_S1=$(printf", 1)[1].split("create_issue", 1)[0]
        body_s2 = workflow.split("BODY_S2=$(printf", 1)[1].split("create_issue", 1)[0]
        assert "TOOL_SEARCH_SECTION" not in body_s1
        assert "TOOL_SEARCH_SECTION" not in body_s2

    def test_step_3_forbids_agent_side_override(self, workflow):
        section = workflow.split("TOOL_SEARCH_SECTION=$(printf", 1)[1].split("\n", 1)[0]
        assert "上書きしない" in section


class TestPostDagDesignGate:
    def test_runs_the_capability_validator(self, workflow):
        assert "validate-agent-contract.py" in workflow

    def test_passes_the_policy_to_the_validator(self, workflow):
        assert "--tool-search-policy" in workflow

    def test_covers_every_design_artifact(self, workflow):
        assert "docs/agent/agent-detail-*.md" in workflow

    def test_runs_before_self_improve(self, workflow):
        """design が不正なまま Self-Improve が走ると誤った改善を積む。"""
        gate = workflow.index("validate-agent-contract.py")
        self_improve = workflow.index("Run mandatory AAG Post-DAG Self-Improve")
        assert gate < self_improve

    def test_reads_the_policy_from_the_root_tag(self, workflow):
        assert "tool_search_policy=" in workflow
