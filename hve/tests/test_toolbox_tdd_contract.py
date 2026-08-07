"""TB-CAP の TDD RED 契約テスト。

FR-WF-AAGD-01 の前段として、実装前に Tool Search の期待が
テスト仕様と RED テストコードへ固定されることを Prompt レベルで検査する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parents[2] / ".github" / "prompts"


def _text(name: str) -> str:
    return (_PROMPTS / f"{name}.prompt.md").read_text(encoding="utf-8")


class TestTestSpecPrompt:
    """`Arch-TDD-TestSpec` が TB-CAP trace を条件付きで要求する。"""

    def test_requires_tb_cap_trace(self):
        assert "TB-CAP-01〜05" in _text("Arch-TDD-TestSpec")

    def test_trace_is_conditional_on_the_design(self):
        """TB-CAP の無い Agent へ不要なケースを作らせない。"""
        text = _text("Arch-TDD-TestSpec")
        assert "設計に TB-CAP がある場合だけ" in text
        assert "設計に TB-CAP が無い Agent" in text

    def test_requires_test_case_id_and_evidence(self):
        assert "Test Case ID と Evidence" in _text("Arch-TDD-TestSpec")

    def test_disabled_expects_absence_not_enabled_behavior(self):
        """`no` と enabled の期待を混在させない。"""
        text = _text("Arch-TDD-TestSpec")
        assert "Tool search: disabled" in text
        assert "存在しないこと" in text


class TestAgentTestCodingPrompt:
    """`Dev-Microservice-Azure-AgentTestCoding` が TB-CAP の RED を定義する。"""

    def test_generates_only_when_the_design_has_tb_cap(self):
        assert "設計に TB-CAP がある場合だけ生成する" in _text(
            "Dev-Microservice-Azure-AgentTestCoding"
        )

    @pytest.mark.parametrize(
        "marker",
        [
            "能力なし判断前に tool_search",
            "TB-CAP-03 の pin 一覧",
            "TB-CAP-04 の additional search text",
            "TB-CAP-05 の limit",
            "wildcard pin の拒否",
        ],
    )
    def test_enabled_red_cases(self, marker: str):
        assert marker in _text("Dev-Microservice-Azure-AgentTestCoding")

    def test_disabled_expects_absence(self):
        text = _text("Dev-Microservice-Azure-AgentTestCoding")
        assert "toolbox source" in text
        assert "tool_search 呼出が存在しないこと" in text

    def test_tool_calls_stay_mocked(self):
        """RED を live Foundry 依存にしない。"""
        assert "実接続を RED の失敗理由にしない" in _text(
            "Dev-Microservice-Azure-AgentTestCoding"
        )

    def test_completion_criteria_include_tb_cap(self):
        text = _text("Dev-Microservice-Azure-AgentTestCoding")
        assert "TB-CAP-01〜05" in text.split("# 8) 完了条件")[-1]
