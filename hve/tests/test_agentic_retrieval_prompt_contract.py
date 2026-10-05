"""Agentic Retrieval 方針・検索契約・Deploy AC 証跡パスを固定する。

FR-WF-AAG-03 / FR-WF-AAG-04。
注入された方針を Agent が解釈できること、および Knowledge Source の下限と
索引契約が設計 Prompt に明示されていることを確認する。AAR / ASDW が共有する
Deploy Prompt の AC 証跡は Orchestrator gate が探索する Issue 直下へ出力させる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parents[2] / ".github" / "prompts"


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def design_prompt() -> str:
    return _read("Arch-AIAgentDesign-Step3.prompt.md")


@pytest.fixture(scope="module")
def agent_deploy_prompt() -> str:
    return _read("Dev-Microservice-Azure-AgentDeploy.prompt.md")


@pytest.fixture(scope="module")
def agentic_retrieval_deploy_prompt() -> str:
    return _read("Dev-Microservice-Azure-AgenticRetrievalDeploy.prompt.md")


class TestDesignPromptPolicy:
    def test_declares_the_injected_policy(self, design_prompt: str):
        assert "Agentic Retrieval 方針" in design_prompt

    @pytest.mark.parametrize("value", ["`auto`", "`yes`", "`no`"])
    def test_lists_all_three_values(self, design_prompt: str, value: str):
        assert value in design_prompt

    def test_forbids_rounding_unknown_values(self, design_prompt: str):
        section = design_prompt.split("Agentic Retrieval 方針", 1)[1]
        assert "blocked" in section


class TestDesignPromptSearchContract:
    def test_requires_at_least_two_knowledge_sources(self, design_prompt: str):
        assert "Knowledge Source" in design_prompt
        assert "2 件以上" in design_prompt

    def test_requires_the_index_semantic_configuration_label(self, design_prompt: str):
        assert "Index semantic configuration" in design_prompt


class TestDeployPromptPolicy:
    def test_declares_the_injected_policy(self, agent_deploy_prompt: str):
        assert "Agentic Retrieval 方針" in agent_deploy_prompt

    def test_states_that_ar_cap_values_are_machine_verified(
        self, agent_deploy_prompt: str
    ):
        assert "AR-CAP-01" in agent_deploy_prompt
        assert "Knowledge base name" in agent_deploy_prompt


class TestDeployAcReportPath:
    def test_agentic_retrieval_report_is_in_issue_root(
        self, agentic_retrieval_deploy_prompt: str
    ) -> None:
        """AAR/ASDW の共有 Deploy prompt は gate が探索する Issue 直下へ出力する。"""
        assert "{WORK}ac-verification.md" in agentic_retrieval_deploy_prompt
        assert (
            "{WORK}artifacts/ac-verification.md"
            not in agentic_retrieval_deploy_prompt
        )

    def test_no_deploy_prompt_places_ac_report_under_artifacts(self) -> None:
        """同じパスドリフトを他の Deploy prompt に再導入しない。"""
        offenders = [
            path.name
            for path in sorted(_PROMPTS.rglob("*Deploy*.prompt.md"))
            if "{WORK}artifacts/ac-verification.md"
            in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"Deploy prompts with nested AC reports: {offenders}"
