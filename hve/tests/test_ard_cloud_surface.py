"""FR-WF-ARD-01 / FR-COMMON-01 のCloud対応契約RED。"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from hve.dag_parity import extract_bash_workflow_steps
from hve.workflow_registry import ARD


_REPO = Path(__file__).resolve().parents[2]
_DISPATCHER = _REPO / ".github" / "workflows" / "auto-orchestrator-dispatcher.yml"
_REUSABLE = _REPO / ".github" / "workflows" / "auto-requirement-definition-reusable.yml"
_PREFLIGHT = _REPO / ".github" / "workflows" / "check-app-requirements-reusable.yml"
_STATE_TRANSITION = _REPO / ".github" / "workflows" / "state-transition-on-pr-merge.yml"
_ISSUE_FORM = _REPO / ".github" / "ISSUE_TEMPLATE" / "auto-requirement-definition.yml"
_LABELS = _REPO / ".github" / "labels.json"
_QA_FEEDBACK = _REPO / ".github" / "workflows" / "copilot-auto-feedback.yml"
_QA_TIMEOUT = _REPO / ".github" / "workflows" / "auto-qa-timeout-watcher.yml"
_BASH_REGISTRY = _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
_CLOUD_SCRIPT = _REPO / ".github" / "scripts" / "bash" / "ard-cloud.sh"


def test_ard_cloud_files_exist() -> None:
    assert _REUSABLE.is_file()
    assert _ISSUE_FORM.is_file()


def test_dispatcher_routes_ard_trigger_done_closed_and_reusable_job() -> None:
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert "('auto-requirement-definition'," in text and "'ARD'" in text
    assert "'ard:done':" in text
    assert "('[ARD]', 'ARD')" in text
    assert "auto-requirement-definition-reusable.yml" in text
    assert "ard:qa-ready" in text


def test_ard_state_and_qa_labels_are_declared() -> None:
    text = _LABELS.read_text(encoding="utf-8")
    for label in (
        "auto-requirement-definition",
        "ard:initialized",
        "ard:ready",
        "ard:running",
        "ard:done",
        "ard:blocked",
        "ard:qa-ready",
        "ard:qa-drafting",
        "ard:qa-timeout",
    ):
        assert f'"name": "{label}"' in text

    assert '"ard:qa-ready"' in _QA_FEEDBACK.read_text(encoding="utf-8")
    timeout = _QA_TIMEOUT.read_text(encoding="utf-8")
    assert '"ard:qa-ready" "ard:qa-drafting"' in timeout


def test_issue_form_declares_five_groups_and_default_two_through_five() -> None:
    text = _ISSUE_FORM.read_text(encoding="utf-8")
    for group in range(1, 6):
        assert re.search(rf"Group\s*{group}\b", text, re.IGNORECASE)
    assert "未選択" in text
    assert "2〜5" in text or "2-5" in text
    assert "Group 1" in text and "opt-in" in text


def test_reusable_workflow_matches_python_and_bash_registries() -> None:
    text = _REUSABLE.read_text(encoding="utf-8")
    script = _CLOUD_SCRIPT.read_text(encoding="utf-8")
    python_ids = {step.id for step in ARD.steps if not step.is_container}
    bash_ids = set(extract_bash_workflow_steps(_BASH_REGISTRY, "ard"))
    assert python_ids == bash_ids
    assert "ard-cloud.sh initialize" in text
    assert "ard-cloud.sh advance" in text
    assert 'create_issue "[ARD] Step.${sid}: ${title}"' in script
    assert 'wf_json=$(get_workflow "ard")' in script
    registry_text = _BASH_REGISTRY.read_text(encoding="utf-8")
    for step in ARD.steps:
        if step.custom_agent:
            assert step.custom_agent in registry_text
    assert "timeout-minutes: 360" in text


def test_reusable_workflow_carries_all_ard_parameters() -> None:
    text = _REUSABLE.read_text(encoding="utf-8")
    for token in (
        "company_name",
        "target_business",
        "survey_base_date",
        "survey_period_years",
        "target_region",
        "analysis_purpose",
        "target_recommendation_id",
        "attached_docs",
        "include_kpi_okr",
    ):
        assert token in text


def test_dispatcher_runs_shared_requirement_preflight_for_nine_downstream_workflows() -> None:
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert "check-app-requirements-reusable.yml" in text
    for workflow_id in (
        "AAS", "ADA", "AAD-WEB", "ASDW-WEB", "ADFD", "ADFDV", "AAG", "AAGD", "AAR"
    ):
        assert workflow_id in text
    assert "mode: ${{ needs.detect.outputs.mode }}" in text


def test_shared_preflight_uses_common_scope_and_trace_validators() -> None:
    text = _PREFLIGHT.read_text(encoding="utf-8")
    for symbol in (
        "extract_application_requirement_app_ids",
        "resolve_application_requirement_app_ids",
        "build_application_requirement_context",
        "validate_application_requirement_trace_block",
        "validate_requirement_coverage",
        "resolve_app_arch_scope",
    ):
        assert symbol in text
    assert "Checkout trusted validator" in text
    assert "Checkout validation subject as data" in text
    assert "python3 -I -" in text
    assert 'completion_mode = os.environ.get("MODE")' in text
    assert 'workflow_id == "ard"' in text
    assert 'completion_pr_number="${candidate_pr_number}"' in text
    assert 'if not os.environ.get("COMPLETION_PR_NUMBER")' in text


def test_pr_merge_validates_ard_42_coverage_and_downstream_trace_before_done() -> None:
    text = _STATE_TRANSITION.read_text(encoding="utf-8")
    validate = text.index("Validate APP requirement completion contract")
    done = text.index("done 付与と残置ラベル整理")
    assert validate < done
    assert "validate_requirement_coverage" in text
    assert "validate_application_requirement_trace_block" in text
    assert 'workflow_id == "ard"' in text
    assert r'^\[ARD\]\s+Step\.4\.2:' in text
    assert "Checkout trusted APP requirement validator" in text
    assert "Checkout PR head as validation data" in text
    assert "persist-credentials: false" in text
    assert "app-requirement-completion-failed" in text


def test_new_cloud_python_heredocs_compile() -> None:
    paths = (_CLOUD_SCRIPT, _PREFLIGHT, _STATE_TRANSITION)
    total = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\n\s*PY\s*$", text, re.MULTILINE | re.DOTALL)
        total += len(blocks)
        for index, block in enumerate(blocks, start=1):
            compile(textwrap.dedent(block), f"{path.name}:PY:{index}", "exec")
    assert total >= 5


def test_per_app_cloud_workflows_embed_app_scope_in_step_issue_bodies() -> None:
    """Cloud は fan-out key ごとの子 Issue を作らず、固定 Step Issue だけを作る。

    そのため実効 APP スコープは Step Issue body の app-ids metadata から復元でき、
    共有 preflight / completion gate が `fanout_meta=None` で呼ぶ形が成立する。
    """
    for name in (
        "auto-agent-data-architecture-reusable.yml",  # ADA
        "auto-agentic-retrieval-reusable.yml",  # AAR
        "auto-ai-agent-design-reusable.yml",  # AAG
        "auto-ai-agent-dev-reusable.yml",  # AAGD
        "auto-app-detail-design-web-reusable.yml",  # AAD-WEB
        "auto-app-dev-microservice-web-reusable.yml",  # ASDW-WEB
        "auto-dataflow-dev-reusable.yml",  # ADFDV
    ):
        text = (_REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "<!-- app-ids: %s -->" in text, name

    # AAS / ADFD は app-catalog の生成側で、Step Issue 時点では対象 APP が確定しない。
    # FR-APPREQ-03 の「実効 app_ids が空の横断 Step は分類内の全 APP」条項へ委ねる。
    for name in (
        "auto-app-selection-reusable.yml",  # AAS
        "auto-dataflow-design-reusable.yml",  # ADFD
    ):
        text = (_REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "<!-- app-ids: %s -->" not in text, name

    for path in (_PREFLIGHT, _STATE_TRANSITION):
        assert "fanout_meta=None" in path.read_text(encoding="utf-8"), path.name
