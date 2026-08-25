# pyright: reportMissingTypeStubs=false
"""G-DIFF trusted Cloud workflow の静的・合成実行契約。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "validate-workflow-diff.yml"
_AUTO_APPROVE_PATH = _REPO_ROOT / ".github" / "workflows" / "auto-approve-and-merge.yml"
_BRANCH_PROTECTION = _REPO_ROOT / ".github" / "branch-protection-main.json"
_VALIDATOR = _REPO_ROOT / ".github" / "scripts" / "validate-workflow-diff.py"
_AAS_ALLOWED_PATH = "docs/catalog/app-arch-catalog.md"


def _workflow() -> tuple[dict[str, Any], str]:
    text = _WORKFLOW_PATH.read_text(encoding="utf-8-sig")
    value = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(value, dict)
    return value, text


def _steps() -> list[dict[str, Any]]:
    workflow, _ = _workflow()
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and set(jobs) == {"g-diff"}
    job = jobs["g-diff"]
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def test_workflow_trigger_permissions_context_and_concurrency() -> None:
    workflow, _ = _workflow()
    assert workflow["name"] == "Workflow Diff Gate"
    assert set(workflow["on"]) == {"pull_request_target"}
    assert set(workflow["on"]["pull_request_target"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "edited",
        "ready_for_review",
    }
    assert workflow["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
        "issues": "read",
    }
    assert workflow["concurrency"] == {
        "group": "workflow-diff-${{ github.event.pull_request.number }}",
        "cancel-in-progress": "true",
    }
    job = workflow["jobs"]["g-diff"]
    assert job["name"] == "G-DIFF"
    assert job["runs-on"] == "ubuntu-latest"
    assert "continue-on-error" not in job


def test_base_and_subject_are_isolated_noncredential_checkouts() -> None:
    checkouts = [step for step in _steps() if step.get("uses") == "actions/checkout@v4"]
    assert len(checkouts) == 2
    trusted = next(step for step in checkouts if step["with"].get("path") == "trusted")
    subject = next(step for step in checkouts if step["with"].get("path") == "subject")
    assert trusted["with"] == {
        "repository": "${{ github.repository }}",
        "ref": "${{ github.event.pull_request.base.sha }}",
        "path": "trusted",
        "fetch-depth": "1",
        "persist-credentials": "false",
        "submodules": "false",
    }
    assert subject["with"] == {
        "repository": "${{ github.event.pull_request.head.repo.full_name }}",
        "ref": "${{ github.event.pull_request.head.sha }}",
        "path": "subject",
        "fetch-depth": "1",
        "persist-credentials": "false",
        "submodules": "false",
    }


def test_metadata_collection_uses_github_api_pagination_and_strips_patch() -> None:
    scripts = [
        str(step.get("with", {}).get("script", ""))
        for step in _steps()
        if step.get("uses") == "actions/github-script@v7"
    ]
    assert len(scripts) == 1
    script = scripts[0]
    assert "github.paginate(" in script
    assert "github.rest.pulls.listFiles" in script
    assert "per_page: 100" in script
    assert "changed_files" in script
    assert "3000" in script
    assert "filename" in script and "status" in script and "previous_filename" in script
    assert "patch:" not in script
    assert "closingIssuesReferences" in script
    assert "parent-issue" in script
    assert "issue_titles" in script and "issue_labels" in script


def test_validator_executes_only_trusted_code_with_subject_as_data() -> None:
    runs = [str(step.get("run", "")) for step in _steps() if "run" in step]
    validator_runs = [run for run in runs if "validate-workflow-diff.py" in run]
    assert len(validator_runs) == 1
    run = validator_runs[0]
    assert "set -euo pipefail" in run
    assert 'python -I "$GITHUB_WORKSPACE/trusted/.github/scripts/validate-workflow-diff.py"' in run
    assert '--root "$GITHUB_WORKSPACE/subject"' in run
    assert "--pr-metadata-file" in run
    assert "--changed-files-file" in run
    assert "GITHUB_STEP_SUMMARY" in run
    assert "python -m json.tool" in run
    assert "validator result was empty or invalid" in run
    assert "$GITHUB_WORKSPACE/subject/.github/scripts" not in run
    assert "PYTHONPATH" not in run or "$GITHUB_WORKSPACE/subject" not in run
    for command in runs:
        assert not re.search(r"(?:python|bash|sh|pwsh|source)\s+[^\n]*subject/[^\n]*\.(?:py|sh|ps1)", command)
        assert "${{ github.event.pull_request.body }}" not in command
        assert "continue-on-error" not in command
        assert "|| true" not in command


def test_no_subject_executable_is_referenced_anywhere() -> None:
    _, text = _workflow()
    forbidden = (
        "subject/.github/scripts/",
        "subject/hve/",
        "PYTHONPATH=$GITHUB_WORKSPACE/subject",
        "source $GITHUB_WORKSPACE/subject",
    )
    for token in forbidden:
        assert token not in text


def _seed_subject(root: Path) -> None:
    (root / "docs" / "catalog").mkdir(parents=True)
    (root / "docs" / "catalog" / "app-catalog.md").write_text(
        "| APP-ID | Name |\n|---|---|\n| APP-009 | Demo |\n",
        encoding="utf-8",
        newline="\n",
    )


def _run_fixture(tmp_path: Path, metadata: dict[str, object], files: list[dict[str, object]]) -> subprocess.CompletedProcess[str]:
    subject = tmp_path / "subject"
    _seed_subject(subject)
    metadata_path = tmp_path / "metadata.json"
    files_path = tmp_path / "files.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8", newline="\n")
    files_path.write_text(json.dumps(files), encoding="utf-8", newline="\n")
    return subprocess.run(
        [
            sys.executable,
            str(_VALIDATOR),
            "--root",
            str(subject),
            "--pr-metadata-file",
            str(metadata_path),
            "--changed-files-file",
            str(files_path),
            "--format",
            "json",
        ],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("metadata", "files", "status", "returncode"),
    (
        (
            {
                "title": "[AAS] generated",
                "body": "<!-- hve-workflow-id: aas -->",
                "issue_titles": [],
                "issue_labels": [],
                "changed_files": 1,
            },
            [{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
            "PASS",
            0,
        ),
        (
            {
                "title": "[AAS] generated",
                "body": "<!-- hve-workflow-id: aas -->",
                "issue_titles": [],
                "issue_labels": [],
                "changed_files": 1,
            },
            [{"filename": "README.md", "status": "modified"}],
            "BLOCKED",
            1,
        ),
        (
            {
                "title": "Ordinary maintenance",
                "body": "",
                "issue_titles": [],
                "issue_labels": [],
                "changed_files": 1,
            },
            [{"filename": "hve/runner.py", "status": "modified"}],
            "N/A",
            0,
        ),
    ),
)
def test_synthetic_cloud_fixture(
    tmp_path: Path,
    metadata: dict[str, object],
    files: list[dict[str, object]],
    status: str,
    returncode: int,
) -> None:
    result = _run_fixture(tmp_path, metadata, files)
    assert result.returncode == returncode, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == status


def _auto_approve_job() -> tuple[dict[str, Any], str]:
    text = _AUTO_APPROVE_PATH.read_text(encoding="utf-8-sig")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    job = workflow["jobs"]["approve-and-merge"]
    assert isinstance(job, dict)
    return job, text


def _auto_approve_step(name: str) -> dict[str, Any]:
    job, _ = _auto_approve_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_auto_approve_directly_runs_trusted_g_diff() -> None:
    job, text = _auto_approve_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    g_diff = next(step for step in steps if step.get("id") == "check-g-diff")
    run = str(g_diff.get("run", ""))
    assert 'python -I "$GITHUB_WORKSPACE/trusted/.github/scripts/validate-workflow-diff.py"' in run
    assert '--root "$GITHUB_WORKSPACE/subject"' in run
    assert "g_diff_passed=" in run
    assert "<!-- hve-workflow-diff-gate-blocked -->" in run
    assert "continue-on-error" not in g_diff
    assert "$GITHUB_WORKSPACE/subject/.github/scripts" not in text


def test_auto_approve_uses_isolated_subject_checkout() -> None:
    job, _ = _auto_approve_job()
    steps = job["steps"]
    checkouts = [step for step in steps if step.get("uses") == "actions/checkout@v4"]
    trusted = next(step for step in checkouts if step["with"].get("path") == "trusted")
    subject = next(step for step in checkouts if step["with"].get("path") == "subject")
    assert trusted["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert subject["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    assert subject["with"]["persist-credentials"] == "false"
    assert subject["with"]["submodules"] == "false"


def test_every_approve_merge_side_effect_requires_g_diff_pass() -> None:
    job, _ = _auto_approve_job()
    steps = job["steps"]
    protected_names = {
        "PR を Approve",
        "Auto-merge を有効化（squash）",
        "サマリーコメントを PR に投稿",
    }
    protected = [step for step in steps if step.get("name") in protected_names]
    assert {step["name"] for step in protected} == protected_names
    for step in protected:
        condition = str(step.get("if", ""))
        assert "steps.check-g-diff.outputs.g_diff_passed == 'true'" in condition
        assert "steps.check-check-runs.outputs.checks_passed == 'true'" in condition
        assert "steps.check-check-runs.outputs.checks_passed != 'false'" not in condition


def test_auto_approve_check_run_gate_blocks_an_empty_or_missing_g_diff_set() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert 'relevant_count=$(printf \'%s\' "${relevant_checks}" | jq \'length\')' in run
    assert "g_diff_passed_count=$(printf '%s' \"${relevant_checks}\" | jq '" in run
    assert 'select((.name // "") == "G-DIFF")' in run
    assert 'select((.status // "") == "completed")' in run
    assert 'select((.conclusion // "") == "success")' in run
    assert 'if [ "${relevant_count}" -eq 0 ] || [ "${g_diff_passed_count}" -eq 0 ]; then' in run
    assert 'blocked="true"' in run


def test_auto_approve_check_run_gate_blocks_pending_checks() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert 'select((.status // "") != "completed")' in run
    assert 'pending_count=$(printf \'%s\' "${pending_checks}" | jq \'length\')' in run
    assert 'if [ "${pending_count}" -gt 0 ]; then' in run
    assert 'blocked="true"' in run


def test_auto_approve_check_run_gate_boundedly_retries_missing_or_pending_checks() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert 'check_runs_max_attempts=30' in run
    assert 'check_runs_retry_seconds=10' in run
    assert 'while [ "${attempt}" -le "${check_runs_max_attempts}" ]; do' in run
    assert 'retryable="true"' in run
    assert (
        'if [ "${retryable}" = "true" ] && [ "${failed_count}" -eq 0 ] '
        '&& [ "${attempt}" -lt "${check_runs_max_attempts}" ]; then'
        in run
    )
    assert 'sleep "${check_runs_retry_seconds}"' in run


def test_auto_approve_check_run_gate_excludes_only_the_exact_current_run() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert 'current_run_prefix="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/"' in run
    assert "startswith($current_run_prefix)" in run
    assert "startswith($current_run_url)" not in run


def test_auto_approve_check_run_gate_uses_a_success_allowlist() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert '(["success", "neutral", "skipped"] | index($check.conclusion)) == null' in run
    assert 'select((.status // "") == "completed")' in run


def test_auto_approve_check_run_gate_fails_closed_on_api_or_schema_error() -> None:
    run = str(
        _auto_approve_step("Check-run 失敗確認（auto-approve 前提条件）").get(
            "run", ""
        )
    )
    assert "gh api --paginate" in run
    assert "jq -e -s" in run
    assert 'echo "checks_passed=false" >> "${GITHUB_OUTPUT}"' in run
    assert "check-runs API の取得または応答検証に失敗しました" in run
    assert '"エラー詳細: \\`${api_err_msg}\\`"' not in run
    assert "詳細は trusted workflow log を確認してください" in run


def test_branch_protection_requires_exact_g_diff_context_once() -> None:
    data = json.loads(_BRANCH_PROTECTION.read_text(encoding="utf-8-sig"))
    contexts = data["required_status_checks"]["contexts"]
    assert contexts.count("Workflow Diff Gate / G-DIFF") == 1
