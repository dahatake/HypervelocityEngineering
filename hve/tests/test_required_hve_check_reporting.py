"""Required HVE checks must always report on pull requests."""

from __future__ import annotations

from fnmatch import fnmatchcase
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest
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

# FR-MAINT-12: explicit names keep missing/new documents from hiding RED cases.
_ACTIVE_SELFTEST_PATHS = (
    "tests/README.md",
    "tests/prompt-version/README.md",
    "tests/prompt-version/01-request-contract.md",
    "tests/prompt-version/02-plan-and-approval-gate.md",
    "tests/prompt-version/03-multi-workflow-order.md",
    "tests/prompt-version/04-input-alias.md",
    "tests/prompt-version/05-gui-settings-reuse.md",
    "tests/prompt-version/06-agent-skill-behavior.md",
    "tests/prompt-version/07-docs-coverage.md",
    "tests/prompt-version/08-e2e-smoke.md",
    "tests/prompt-version/09-full-system-test.md",
    "tests/[cli]SystemTest - Full.txt",
    "tests/[gui]SystemTest - Full.txt",
)
_CI_PATH_CASES = (
    *((path, True) for path in _ACTIVE_SELFTEST_PATHS),
    ("hve/tests/test_required_hve_check_reporting.py", True),
    ("cq/tests/test_search.py", True),
    (".github/workflows/test-hve-python.yml", True),
    # FR-MAINT-15: the golden gates must run when the search engines or their config change.
    ("mdq/search.py", True),
    ("mdq/golden-queries.json", True),
    ("tools/skills/markdown_query/benchmark.py", True),
    ("mdq.toml", True),
    ("cq.toml", True),
    # Historical copies (including brackets) and lane source are not active input.
    *((f"tests/run/t22/snapshot/{path}", False) for path in _ACTIVE_SELFTEST_PATHS),
    ("tests/run/README.md", False),
    ("tests/run/t22/artifacts/report.json", False),
    ("tests/run/t22/artifacts/stdout.log", False),
    ("tests/run/t22/lanes/CASE-01/hve/runner.py", False),
    ("tests/run/t22/lanes/CASE-01/.github/workflows/test-hve-python.yml", False),
    ("docs/README.md", False),
    ("src/unrelated.py", False),
    ("other/tests/README.md", False),
    ("tests/unrelated.txt", False),
    ("tests/prompt-version/unrelated.md", False),
    ("tests/prompt-version/10-unrelated.md", False),
    ("tests/prompt-version/archive/01-request-contract.md", False),
    ("tests/[cli]SystemTest - Full.txt.bak", False),
    ("tests/[gui]SystemTest - Full.txt.bak", False),
    *((f"tests/x{mode}]SystemTest - Full.txt", False) for mode in ("cli", "gui")),
    *((f"tests/[{mode}xSystemTest - Full.txt", False) for mode in ("cli", "gui")),
    *((f"tests/{letter}SystemTest - Full.txt", False) for letter in "cligu"),
    ("tests/cliSystemTest - Full.txt", False),
    ("tests/guiSystemTest - Full.txt", False),
)


def _workflow() -> dict:
    return yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _push_path_matches(path: str, pattern: str) -> bool:
    """Match this workflow's glob subset, preserving / and escaped brackets."""
    assert all("**" not in part or part == "**" for part in pattern.split("/")), (
        "Unsupported embedded ** pattern: " + pattern
    )
    assert not any(char in pattern for char in "?+"), "Unsupported glob: " + pattern
    # fnmatch alone crosses / and treats an unescaped [cli] as a character class.
    pattern = pattern.replace(r"\[", "[[]").replace(r"\]", "[]]")
    parts, globs = path.split("/"), pattern.split("/")

    def match(parts: list[str], globs: list[str]) -> bool:
        if not globs:
            return not parts
        if globs[0] == "**":
            return any(match(parts[i:], globs[1:]) for i in range(len(parts) + 1))
        return bool(parts) and fnmatchcase(parts[0], globs[0]) and match(parts[1:], globs[1:])

    return match(parts, globs)


@pytest.mark.parametrize("path, expected", _CI_PATH_CASES)
def test_push_paths_select_active_selftest_inputs_not_evidence(path: str, expected: bool) -> None:
    selected = False
    for pattern in _workflow()["on"]["push"]["paths"]:
        excluded = pattern.startswith("!")
        if _push_path_matches(path, pattern[1:] if excluded else pattern):
            selected = not excluded
    assert selected is expected, path


@pytest.mark.parametrize("path, expected", _CI_PATH_CASES)
def test_pr_detector_selects_active_selftest_inputs_not_evidence(path: str, expected: bool) -> None:
    script = next(
        step["run"] for step in _workflow()["jobs"]["detect-changes"]["steps"]
        if step.get("id") == "paths"
    )
    cases = re.findall(r'case "\$\{path\}" in\s*\n.*?\besac\b', script, re.DOTALL)
    assert len(cases) == 1, "Expected the single existing path detector case block"
    git_bash = next(
        (str(candidate) for candidate in (
            Path("C:/Program Files/Git/bin/bash.exe"),
            Path("C:/Program Files/Git/usr/bin/bash.exe"),
        ) if candidate.is_file()),
        None,
    )
    bash = (git_bash or shutil.which("bash")) if os.name == "nt" else shutil.which("bash")
    assert bash is not None, "Bash is required to verify quoted case patterns; do not skip"
    # Execute the real arms/bodies, with their quoting intact and break in a loop.
    # No gh/API calls: only a positional filename enters the extracted case block.
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-c",
         'set -euo pipefail\nrun_heavy=false\nfor path in "$@"; do\n'
         + cases[0] + '\ndone\nprintf "%s" "$run_heavy"', "path-detector-test", path],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(expected).lower(), (path, result.stdout, result.stderr)


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
