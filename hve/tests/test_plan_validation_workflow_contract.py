"""Plan Validation が大規模 PR の変更ファイルをページング取得する契約。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "plan-validation-and-labeling.yml"


def _run_script(job_name: str) -> str:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"][job_name]["steps"]
    scripts = [str(step["run"]) for step in steps if "run" in step]
    assert len(scripts) == 1
    return scripts[0]


@pytest.mark.parametrize("job_name", ("validate-plan", "check-split-mode"))
def test_validation_jobs_page_through_pull_request_files(job_name: str) -> None:
    script = _run_script(job_name)

    assert "gh pr diff" not in script
    assert script.count("gh api --paginate") == 1
    assert (
        '"/repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/files?per_page=100"'
        in script
    )
    assert "--jq '.[].filename'" in script


@pytest.mark.parametrize("job_name", ("validate-plan", "check-split-mode"))
def test_validation_jobs_fail_closed_on_partial_file_enumeration(
    job_name: str,
) -> None:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    step = next(
        step
        for step in workflow["jobs"][job_name]["steps"]
        if "run" in step
    )
    script = str(step["run"])

    assert step["env"]["EXPECTED_CHANGED_FILES"] == "${{ github.event.pull_request.changed_files }}"
    assert 'ACTUAL_CHANGED_FILES=$(printf \'%s\\n\' "$ALL_CHANGED" | grep -c . || true)' in script
    assert 'if [ "$ACTUAL_CHANGED_FILES" -ne "$EXPECTED_CHANGED_FILES" ]; then' in script
    assert "Pull Request files API が一部のファイルしか返しませんでした" in script
