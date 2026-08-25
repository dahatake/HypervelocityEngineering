"""§13.13: Workflow完了ゲートの適用境界を固定する契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from hve import orchestrator
from hve.config import SDKConfig
from hve.fanout_expander import resolve_output_path_prefix_gates
from hve.orchestrator_context import OrchestratorContext
from hve.runner import _check_output_paths_gate
from hve.workflow_registry import get_workflow, list_workflows

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_STATE_TRANSITION_WORKFLOW = (
    _REPO_ROOT / ".github" / "workflows" / "state-transition-on-pr-merge.yml"
)
_STATUS_PATH = "knowledge/business-requirement-document-status.md"
_CLOUD_TITLE_PREFIX_MAP = (
    ("[ARD]", "ard"),
    ("[AAD-WEB]", "aad-web"),
    ("[ASDW-WEB]", "asdw-web"),
    ("[AAS]", "aas"),
    ("[ADFD]", "adfd"),
    ("[ADFDV]", "adfdv"),
    ("[AAG]", "aag"),
    ("[AAGD]", "aagd"),
    ("[AAR]", "aar"),
    ("[ADA]", "ada"),
    ("[AKM]", "akm"),
    ("[ADOC]", "adoc"),
)


def _gate_section() -> str:
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")
    start_heading = "### 13.13 ゲート条件（受入基準）"
    end_heading = "### 13.14 CONF —"
    start = text.index(start_heading) + len(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def _gate_line(gate_name: str) -> str:
    matches = [
        line
        for line in _gate_section().splitlines()
        if re.match(rf"^\d+\. \*\*{re.escape(gate_name)}\*\*:", line)
    ]
    assert len(matches) == 1
    return matches[0]


def _workflow_step(step_name: str) -> dict:
    workflow = yaml.safe_load(_STATE_TRANSITION_WORKFLOW.read_text(encoding="utf-8-sig"))
    steps = workflow["jobs"]["transition"]["steps"]
    matches = [
        step
        for step in steps
        if step.get("name") == step_name
    ]
    assert len(matches) == 1
    return matches[0]


def _transition_script() -> str:
    return _workflow_step("done 付与と残置ラベル整理").get("run", "")


class TestGateScopeRequirement:
    """規範文言のcharacterization。実装境界は後続クラスで別途検証する。"""
    def test_requirement_declares_non_applicable_gates_as_na(self) -> None:
        section = _gate_section()
        assert "適用可能なゲートだけ" in section
        assert "適用条件を満たさないゲートは `N/A`" in section
        assert "`N/A` のゲートだけを理由に `blocked` としてはならない" in section

    def test_g_lbl_is_cloud_only_and_cli_done_is_advisory(self) -> None:
        section = _gate_section()
        assert "Cloud Agent Orchestrator の完了判定に限り" in section
        assert "補助的な状態通知であり、本ゲートではない" in section
        assert "Issue 作成の有無にかかわらず `N/A`" in section

    def test_g_cons_is_akm_only(self) -> None:
        section = _gate_section()
        assert "AKM Workflow に限り" in section
        assert "AKM 以外では `N/A`" in section

    def test_g_diff_uses_actual_pr_result_and_covers_all_known_channels(self) -> None:
        line = _gate_line("G-DIFF")
        assert "当該 run で PR が実際に作成された場合に限り" in line
        assert "起動フラグ名ではなく PR 作成結果で判定" in line
        for token in ("`--create-pr`", "`--create-issues`", "`--enable-auto-merge`", "Cloud"):
            assert token in line
        assert "PR が作成されない local CLI / GUI 実行では `N/A`" in line


class TestGLblCloudTransition:
    def test_cloud_transition_cleans_nonterminal_labels_before_adding_done(self) -> None:
        script = _transition_script()
        label_vars = (
            "qa_drafting_label",
            "qa_ready_label",
            "ready_label",
            "running_label",
            "blocked_label",
        )
        cleanup_loop = "for stale in " + " ".join(
            f'"${{{label_var}}}"' for label_var in label_vars
        )
        assert cleanup_loop in script
        cleanup_index = script.index(cleanup_loop)
        cleanup_verify_index = script.index("labels_after_cleanup=$(fetch_labels)")
        add_done_index = script.index('--add-label "${done_label}"')
        post_done_verify_index = script.index("post_done_labels=$(fetch_labels)")
        assert cleanup_index < cleanup_verify_index < add_done_index < post_done_verify_index

    def test_cloud_transition_verifies_cleanup_and_fails_closed(self) -> None:
        script = _transition_script()
        assert script.count("=$(fetch_labels)") == 3
        assert "2>/dev/null || echo ''" not in script
        assert "grep -Fxq" in script
        assert "verification_failed=true" in script
        assert "残置ラベルの削除に失敗" in script
        assert script.count("exit 1") == 3
        assert "done_present=false" in script
        assert "rollback_failed=" in script
        post_failure = script.index('if [ "${add_failed}" = "true" ]')
        rollback_call = script.index("if ! rollback_done; then", post_failure)
        failure_exit = script.index("exit 1", rollback_call)
        assert post_failure < rollback_call < failure_exit

    def test_cloud_transition_reports_only_labels_actually_removed(self) -> None:
        script = _transition_script()
        assert "removed_labels=''" in script
        assert 'removed_labels="${removed_labels}${removed_labels:+,}${stale}"' in script
        assert "removed=[%s]" in script
        assert "removed=[%s,%s,%s,%s,%s]" not in script

    def test_state_transition_supports_every_cloud_workflow_prefix(self) -> None:
        detect_script = _workflow_step("系列プレフィックス判定").get("run", "")
        resolve_script = _workflow_step("PR body から parent-issue を解決").get("run", "")
        for title_token, prefix in _CLOUD_TITLE_PREFIX_MAP:
            assert f"('{title_token}', '{prefix}')" in detect_script
            assert repr(title_token) in resolve_script
            assert repr(prefix) in resolve_script
        assert "candidates = ['ard', 'aas', 'aad-web', 'asdw-web', 'adfd', 'adfdv', 'aag', 'aagd', 'aar', 'ada', 'akm', 'adoc', 'aad', 'asdw']" in detect_script

    def test_close_revalidates_g_lbl_before_and_after_closing(self) -> None:
        step = _workflow_step("Issue を冪等にクローズ")
        script = step.get("run", "")
        assert step.get("env", {}).get("PREFIX") == "${{ steps.detect-prefix.outputs.prefix }}"
        assert 'verify_g_lbl "${current_labels}"' in script
        assert 'verify_g_lbl "${post_close_labels}"' in script
        close_index = script.index('gh issue close "${ISSUE_NUMBER}"')
        assert script.index('verify_g_lbl "${current_labels}"') < close_index
        assert close_index < script.index('verify_g_lbl "${post_close_labels}"')
        assert 'gh issue reopen "${ISSUE_NUMBER}"' in script
        assert "g-lbl-invalid" in script
        assert "exit 1" in script


class TestGOutRuntimeResolvedScope:
    def test_non_fanout_template_is_not_a_runtime_gate(self, tmp_path: Path) -> None:
        workflow = get_workflow("adoc")
        assert workflow is not None
        step = workflow.get_step("2.1")
        assert step is not None
        assert not step.output_paths
        assert step.output_paths_template
        assert resolve_output_path_prefix_gates(step) == []
        assert _check_output_paths_gate(
            OrchestratorContext(), workflow, "2.1", tmp_path
        ) == []


class TestGConsRegistryScope:
    def test_only_akm_declares_the_consistency_status_output(self) -> None:
        owners: set[tuple[str, str, str]] = set()
        for workflow in list_workflows():
            for step in workflow.steps:
                if _STATUS_PATH in (step.output_paths or []):
                    owners.add((workflow.id, step.id, "output_paths"))
                if _STATUS_PATH in (step.output_paths_template or []):
                    owners.add((workflow.id, step.id, "output_paths_template"))
        assert owners == {
            ("akm", "1", "output_paths_template"),
            ("akm", "2", "output_paths"),
        }


class TestGDiffKnownPrChannels:
    def test_explicit_issue_or_pr_flags_use_workflow_branch_mode(self) -> None:
        for workflow in list_workflows():
            assert orchestrator._uses_workflow_branch_mode(
                workflow.id, SDKConfig(create_pr=True)
            )
            assert orchestrator._uses_workflow_branch_mode(
                workflow.id, SDKConfig(create_issues=True)
            )

    def test_auto_merge_pr_channels_remain_workflow_specific(self) -> None:
        config = SDKConfig(enable_auto_merge=True)
        assert orchestrator._uses_workflow_branch_mode("adfdv", config)
        # ASDW-WEBはStep単位PR経路であり、workflow-wide branchではない。
        assert not orchestrator._uses_workflow_branch_mode("asdw-web", config)
        for workflow in list_workflows():
            if workflow.id not in {"adfdv", "asdw-web"}:
                assert not orchestrator._uses_workflow_branch_mode(workflow.id, config)

    def test_no_pr_flags_leave_local_workflows_outside_pr_branch_mode(self) -> None:
        config = SDKConfig()
        assert all(
            not orchestrator._uses_workflow_branch_mode(workflow.id, config)
            for workflow in list_workflows()
        )
