"""FR-INPUT-05 — custom input Step のQA強制とMCP同意境界。"""

from __future__ import annotations

from hve.step_inputs import (
    STEP_INPUT_MCP_CONSENT_PROMPT,
    build_cloud_step_input_section,
    should_offer_step_input_mcp,
)


def test_custom_input_enables_pre_qa_without_saved_auto_qa() -> None:
    from hve.runner import _should_run_pre_execution_qa

    assert _should_run_pre_execution_qa(
        auto_qa=False,
        workflow_id="aas",
        custom_agent="Arch-ArchitectureCandidateAnalyzer",
        prompt="task",
        has_step_inputs=True,
    ) is True


def test_unrelated_step_keeps_existing_auto_qa_behavior() -> None:
    from hve.runner import _should_run_pre_execution_qa

    assert _should_run_pre_execution_qa(
        auto_qa=False,
        workflow_id="aas",
        custom_agent="Arch-ArchitectureCandidateAnalyzer",
        prompt="task",
        has_step_inputs=False,
    ) is False


def test_mcp_offer_requires_questions_ready_adapter_and_no_prior_decision() -> None:
    assert STEP_INPUT_MCP_CONSENT_PROMPT == "MCP経由で情報を補填しますか?"
    assert should_offer_step_input_mcp(
        has_step_inputs=True,
        question_count=1,
        adapter_ready=True,
        consent=None,
    ) is True
    assert should_offer_step_input_mcp(
        has_step_inputs=True,
        question_count=0,
        adapter_ready=True,
        consent=None,
    ) is False
    assert should_offer_step_input_mcp(
        has_step_inputs=True,
        question_count=1,
        adapter_ready=False,
        consent=None,
    ) is False
    assert should_offer_step_input_mcp(
        has_step_inputs=True,
        question_count=1,
        adapter_ready=True,
        consent=False,
    ) is False


def test_cloud_custom_input_uses_exact_consent_and_manual_qa_fallback() -> None:
    section = build_cloud_step_input_section(
        """### Step Input Files

docs-original/input.md

### Step Input Bindings

{"step_id":"1","role":"additional","file":1}
""",
        "aas",
    )

    assert STEP_INPUT_MCP_CONSENT_PROMPT in section
    assert "質問が0件ならメインタスクへ進む" in section
    assert "手動QAへ戻し" in section
    assert "MCP補填をCloud対応済みと表示しない" in section
