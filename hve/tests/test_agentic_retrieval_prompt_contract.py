"""Agentic Retrieval 方針と検索契約の Prompt 側記述を固定する。

FR-WF-AAG-03 / FR-WF-AAG-04。
注入された方針を Agent が解釈できること、および Knowledge Source の下限と
索引契約が設計 Prompt に明示されていることを確認する。
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
def deploy_prompt() -> str:
    return _read("Dev-Microservice-Azure-AgentDeploy.prompt.md")


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
    def test_declares_the_injected_policy(self, deploy_prompt: str):
        assert "Agentic Retrieval 方針" in deploy_prompt

    def test_states_that_ar_cap_values_are_machine_verified(self, deploy_prompt: str):
        assert "AR-CAP-01" in deploy_prompt
        assert "Knowledge base name" in deploy_prompt
