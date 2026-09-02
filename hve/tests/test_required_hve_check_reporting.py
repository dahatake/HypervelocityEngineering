"""Required HVE checks must always report on pull requests."""

from __future__ import annotations

from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-python.yml"
_REQUIRED_JOB_NAMES = {"HVE Python Tests", "mdq index smoke test"}
_HEAVY_PATH_TOKENS = {
    "hve/",
    "hve-dev/",
    "cq/",
    "pyproject.toml",
    ".github/scripts/",
    ".github/prompts/",
    ".github/io-contracts/",
    ".github/workflows/",
    ".gitattributes",
}


def _workflow() -> dict:
    return yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_pull_request_trigger_cannot_skip_required_checks() -> None:
    data = _workflow()
    on = data["on"]
    assert "paths" not in on["pull_request"]
    assert on["pull_request"]["branches"] == ["main"]


def test_single_detector_preserves_the_previous_heavy_path_scope() -> None:
    data = _workflow()
    detector = data["jobs"]["detect-changes"]
    assert detector["outputs"]["run_heavy"] == "${{ steps.paths.outputs.run_heavy }}"
    script = next(
        step["run"]
        for step in detector["steps"]
        if step.get("id") == "paths"
    )
    for token in _HEAVY_PATH_TOKENS:
        assert token in script
    assert "gh api --paginate" in script
    assert ".previous_filename // empty" in script


def test_required_jobs_always_run_and_fail_closed_on_detection_error() -> None:
    data = _workflow()
    required_jobs = [
        job
        for job in data["jobs"].values()
        if job.get("name") in _REQUIRED_JOB_NAMES
    ]
    assert {job["name"] for job in required_jobs} == _REQUIRED_JOB_NAMES
    for job in required_jobs:
        assert job["needs"] == "detect-changes"
        assert "always()" in job["if"]
        gate = job["steps"][0]
        assert gate["name"] == "Require successful path detection"
        assert gate["env"]["DETECTION_RESULT"] == "${{ needs.detect-changes.result }}"
        assert '"${DETECTION_RESULT}" != "success"' in gate["run"]
        for step in job["steps"][1:]:
            assert step["if"] == "needs.detect-changes.outputs.run_heavy == 'true'"
