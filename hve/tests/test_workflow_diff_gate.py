"""§13.13 G-DIFF の共有 policy / matcher / identity 契約。"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from hve.workflow_registry import list_workflows

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _gate() -> ModuleType:
    """実装前 RED を collection error ではなく各受入ケースで観測する。"""
    return importlib.import_module("hve.workflow_diff_gate")


def _policy(**overrides: object) -> Any:
    gate = _gate()
    values: dict[str, object] = {
        "workflow_id": "aas",
        "exact_paths": ("docs/catalog/app-catalog.md",),
        "directory_paths": ("src/app/",),
        "glob_paths": ("qa/**/*.md",),
        "prefix_paths": ("docs/services/SVC-01",),
        "constrained_paths": (
            "docs-generated/files/{relative-path}.md",
            "docs-generated/components/{module-name}.md",
        ),
        "provenance": {},
    }
    values.update(overrides)
    return gate.WorkflowDiffPolicy(**values)


def _changed(path: str, status: str = "modified", previous: str | None = None) -> Any:
    gate = _gate()
    return gate.ChangedPath(path=path, status=status, previous_path=previous)


class TestWorkflowIdentity:
    def test_body_marker_resolves_registered_workflow(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="<!-- hve-workflow-id: aas -->",
            pr_title="generated outputs",
        )
        assert result.status == "PASS"
        assert result.workflow_id == "aas"
        assert not result.errors

    def test_unknown_marker_is_blocked(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="<!-- hve-workflow-id: not-a-workflow -->",
            pr_title="generated outputs",
        )
        assert result.status == "BLOCKED"
        assert result.workflow_id is None
        assert result.errors

    def test_conflicting_marker_and_title_are_blocked(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="<!-- hve-workflow-id: aas -->",
            pr_title="[ASDW] generated outputs",
        )
        assert result.status == "BLOCKED"
        assert result.errors

    @pytest.mark.parametrize(
        ("title", "workflow_id"),
        (
            ("[AAD] generated", "aad-web"),
            ("[AAD-WEB] generated", "aad-web"),
            ("[ASDW] generated", "asdw-web"),
            ("[ASDW-WEB] generated", "asdw-web"),
        ),
    )
    def test_legacy_title_prefixes_are_preserved(
        self, title: str, workflow_id: str
    ) -> None:
        result = _gate().resolve_managed_workflow_id(pr_body="", pr_title=title)
        assert result.status == "PASS"
        assert result.workflow_id == workflow_id

    def test_unmanaged_pr_is_na(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="ordinary maintenance",
            pr_title="Fix a typo",
        )
        assert result.status == "N/A"
        assert result.workflow_id is None

    def test_issue_title_and_state_label_resolve_the_same_workflow(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="",
            pr_title="generated outputs",
            issue_titles=("[AAS] Step.4.1 data model",),
            issue_labels=("aas:running",),
        )
        assert result.status == "PASS"
        assert result.workflow_id == "aas"

    def test_conflicting_issue_evidence_is_blocked(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="",
            pr_title="generated outputs",
            issue_titles=("[AAS] Step.4.1 data model",),
            issue_labels=("asdw-web:running",),
        )
        assert result.status == "BLOCKED"
        assert result.errors

    def test_multiple_body_markers_are_blocked_even_when_equal(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body=(
                "<!-- hve-workflow-id: aas -->\n"
                "<!-- hve-workflow-id: aas -->"
            ),
            pr_title="[AAS] generated outputs",
        )
        assert result.status == "BLOCKED"
        assert result.errors

    def test_unrelated_bracketed_title_is_unmanaged(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="",
            pr_title="[BUG] ordinary maintenance",
        )
        assert result.status == "N/A"
        assert result.workflow_id is None

    def test_prose_mentioning_marker_name_is_still_unmanaged(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="Document the hve-workflow-id contract for maintainers.",
            pr_title="Documentation update",
        )
        assert result.status == "N/A"
        assert result.workflow_id is None

    def test_malformed_html_marker_is_blocked(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="<!-- hve-workflow-id aas -->",
            pr_title="ordinary title",
        )
        assert result.status == "BLOCKED"
        assert result.errors

    def test_valid_and_malformed_markers_together_are_blocked(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body=(
                "<!-- hve-workflow-id: aas -->\n"
                "<!-- hve-workflow-id aas -->"
            ),
            pr_title="[AAS] generated outputs",
        )
        assert result.status == "BLOCKED"
        assert result.errors

    def test_legacy_alias_is_not_accepted_in_strong_marker(self) -> None:
        result = _gate().resolve_managed_workflow_id(
            pr_body="<!-- hve-workflow-id: aad -->",
            pr_title="[AAD] generated outputs",
        )
        assert result.status == "BLOCKED"
        assert result.errors

    @pytest.mark.parametrize(
        "kwargs",
        (
            {"pr_body": "", "pr_title": None},
            {"pr_body": "", "pr_title": "ordinary", "issue_titles": "[AAS]"},
            {"pr_body": "", "pr_title": "ordinary", "issue_labels": "aas:done"},
            {"pr_body": "", "pr_title": "ordinary", "issue_titles": (None,)},
            {"pr_body": "", "pr_title": "ordinary", "issue_labels": (1,)},
        ),
    )
    def test_malformed_pr_or_issue_metadata_is_blocked(self, kwargs: dict) -> None:
        result = _gate().resolve_managed_workflow_id(**kwargs)
        assert result.status == "BLOCKED"
        assert result.errors


class TestChangedPathMatching:
    def test_exact_directory_glob_prefix_and_constrained_paths_pass(self) -> None:
        gate = _gate()
        changed = [
            _changed("docs/catalog/app-catalog.md"),
            _changed("src/app/pages/index.tsx"),
            _changed("qa/report.md"),
            _changed("qa/nested/report.md"),
            _changed("qa/nested/deeper/report.md"),
            _changed("docs/services/SVC-01-member-description.md"),
            _changed("docs-generated/files/src/orders/handler.py.md"),
            _changed("docs-generated/components/orders.md"),
        ]
        result = gate.validate_changed_paths(_policy(), changed)
        assert result.status == "PASS"
        assert not result.violations
        assert set(result.allowed_by) == {item.path for item in changed}

    @pytest.mark.parametrize(
        "path",
        (
            "src/application.ts",
            "qa/report.jsonl",
            "docs-generated/components/orders/api.md",
            "README.md",
        ),
    )
    def test_near_misses_are_blocked(self, path: str) -> None:
        result = _gate().validate_changed_paths(_policy(), [_changed(path)])
        assert result.status == "BLOCKED"
        assert result.violations == (path,)

    def test_rename_requires_old_and_new_paths_to_be_allowed(self) -> None:
        gate = _gate()
        allowed = gate.validate_changed_paths(
            _policy(exact_paths=("docs/old.md", "docs/new.md")),
            [_changed("docs/new.md", "renamed", "docs/old.md")],
        )
        blocked = gate.validate_changed_paths(
            _policy(exact_paths=("docs/new.md",)),
            [_changed("docs/new.md", "renamed", "README.md")],
        )
        assert allowed.status == "PASS"
        assert blocked.status == "BLOCKED"
        assert blocked.violations == ("README.md",)

    def test_copied_path_without_source_is_fail_closed(self) -> None:
        result = _gate().validate_changed_paths(
            _policy(exact_paths=("docs/new.md",)),
            [_changed("docs/new.md", "copied")],
        )
        assert result.status == "BLOCKED"
        assert result.errors

    @pytest.mark.parametrize(
        ("status", "previous"),
        (
            ("added", None),
            ("removed", None),
            ("modified", None),
            ("changed", None),
            ("unchanged", None),
            ("renamed", "docs/old.md"),
            ("copied", "docs/old.md"),
        ),
    )
    def test_github_documented_statuses_are_accepted(
        self, status: str, previous: str | None
    ) -> None:
        result = _gate().validate_changed_paths(
            _policy(exact_paths=("docs/old.md", "docs/new.md")),
            [_changed("docs/new.md", status, previous)],
        )
        assert result.status == "PASS"
        assert not result.errors

    @pytest.mark.parametrize(
        "path",
        (
            "",
            "/absolute.md",
            "..\\escape.md",
            "docs/../escape.md",
            "docs//x.md",
            "a\x00b",
            "src/app/line\nbreak.ts",
            "src/app/line\rbreak.ts",
        ),
    )
    def test_unsafe_git_paths_are_fail_closed(self, path: str) -> None:
        result = _gate().validate_changed_paths(_policy(), [_changed(path)])
        assert result.status == "BLOCKED"
        assert result.errors

    @pytest.mark.parametrize("status", ("mystery", "type_change"))
    def test_unknown_api_status_is_fail_closed(self, status: str) -> None:
        result = _gate().validate_changed_paths(
            _policy(), [_changed("docs/catalog/app-catalog.md", status)]
        )
        assert result.status == "BLOCKED"
        assert result.errors

    def test_duplicates_are_removed_in_first_seen_order(self) -> None:
        gate = _gate()
        changed = [
            _changed("docs/catalog/app-catalog.md"),
            _changed("docs/catalog/app-catalog.md"),
            _changed("src/app/main.ts"),
        ]
        result = gate.validate_changed_paths(_policy(), changed)
        assert result.status == "PASS"
        assert result.checked_paths == (
            "docs/catalog/app-catalog.md",
            "src/app/main.ts",
        )


class TestRegistryPolicyResolution:
    def test_every_registered_workflow_builds_a_deterministic_policy(self) -> None:
        gate = _gate()
        for workflow in list_workflows():
            first = gate.build_workflow_diff_policy(workflow.id, _REPO_ROOT)
            second = gate.build_workflow_diff_policy(workflow.id, _REPO_ROOT)
            assert first == second
            assert first.workflow_id == workflow.id
            assert first.exact_paths or first.directory_paths or first.glob_paths or first.prefix_paths or first.constrained_paths

    def test_data_model_optional_sidecars_are_allowed(self) -> None:
        gate = _gate()
        expected = {
            "docs/catalog/data-model-service-stores.md",
            "docs/catalog/data-model-consistency-events.md",
            "docs/catalog/data-model-diagrams.md",
        }
        for workflow_id in ("aas", "ada"):
            policy = gate.build_workflow_diff_policy(workflow_id, _REPO_ROOT)
            assert expected <= set(policy.exact_paths)
            result = gate.validate_changed_paths(
                policy, [_changed(path, "removed") for path in sorted(expected)]
            )
            assert result.status == "PASS"

    def test_adoc_placeholders_are_constrained_not_repository_wide(self) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy("adoc", _REPO_ROOT)
        accepted = gate.validate_changed_paths(
            policy,
            [
                _changed("docs-generated/files/src/api/handler.py.md"),
                _changed("docs-generated/components/orders.md"),
            ],
        )
        rejected = gate.validate_changed_paths(
            policy, [_changed("docs-generated/components/orders/api.md")]
        )
        assert accepted.status == "PASS"
        assert rejected.status == "BLOCKED"

    def test_common_qa_allowance_is_markdown_only(self) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy("aas", _REPO_ROOT)
        assert gate.validate_changed_paths(
            policy, [_changed("qa/sub/review.md")]
        ).status == "PASS"
        assert gate.validate_changed_paths(
            policy, [_changed("qa/sub/evidence.jsonl")]
        ).status == "BLOCKED"

    def test_asdw_real_directory_and_segment_glob_contracts(self) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy("asdw-web", _REPO_ROOT)
        accepted = gate.validate_changed_paths(
            policy,
            [
                _changed("src/test/e2e/playwright/results/report.html"),
                _changed(
                    "src/infra/azure/create-azure-additional-resources/verify-network.sh"
                ),
            ],
        )
        rejected = gate.validate_changed_paths(
            policy,
            [
                _changed(
                    "src/infra/azure/create-azure-additional-resources/nested/verify-network.sh"
                )
            ],
        )
        assert accepted.status == "PASS"
        assert rejected.status == "BLOCKED"

    def test_akm_static_fanout_prefix_is_closed_to_declared_keys(self) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy("akm", _REPO_ROOT)
        assert gate.validate_changed_paths(
            policy, [_changed("knowledge/D01-business-rules.md")]
        ).status == "PASS"
        assert gate.validate_changed_paths(
            policy, [_changed("knowledge/D22-business-rules.md")]
        ).status == "BLOCKED"
        assert gate.validate_changed_paths(
            policy, [_changed("knowledge/D010-business-rules.md")]
        ).status == "BLOCKED"

    @pytest.mark.parametrize("workflow_id", ("asdw-web", "aagd"))
    def test_hve_source_is_blocked_even_when_a_broad_output_matches(
        self, workflow_id: str
    ) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy(workflow_id, _REPO_ROOT)
        result = gate.validate_changed_paths(
            policy, [_changed(".github/workflows/auto-approve-and-merge.yml")]
        )
        assert result.status == "BLOCKED"
        assert result.violations == (
            ".github/workflows/auto-approve-and-merge.yml",
        )

    @pytest.mark.parametrize(
        ("workflow_id", "path"),
        (
            ("asdw-web", ".github/workflows/deploy-app009.yml"),
            ("asdw-web", ".github/workflows/app009-ci.yml"),
            ("aagd", ".github/workflows/deploy-agent-AG-01.yml"),
        ),
    )
    def test_generated_app_workflows_remain_allowed(
        self, workflow_id: str, path: str
    ) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy(workflow_id, _REPO_ROOT)
        assert gate.validate_changed_paths(policy, [_changed(path)]).status == "PASS"

    def test_declared_directory_allows_nested_descendants(self) -> None:
        gate = _gate()
        policy = gate.build_workflow_diff_policy("adfdv", _REPO_ROOT)
        result = gate.validate_changed_paths(
            policy,
            [_changed("src/dataflow/JOB-01-orders/package/internal/module.py")],
        )
        assert result.status == "PASS"

    def test_unknown_workflow_is_fail_closed(self) -> None:
        result = _gate().validate_workflow_diff(
            "not-a-workflow",
            _REPO_ROOT,
            [_changed("docs/catalog/app-catalog.md")],
        )
        assert result.status == "BLOCKED"
        assert result.errors