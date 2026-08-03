from __future__ import annotations

import re
from pathlib import Path

from hve.workflow_registry import list_workflows


_ACTIONABLE_NON_RUN_WORK_RE = re.compile(
    r"work[/\\](?!run[/\\])(?:[A-Z][A-Za-z0-9_.-]+|Issue-|\{run_id\})"
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_prompts_do_not_instruct_actionable_non_run_work_paths() -> None:
    roots = [
        _REPO_ROOT / ".github" / "prompts",
        _REPO_ROOT / ".github" / "skills",
        _REPO_ROOT / "hve" / "prompt",
    ]
    findings: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(content.splitlines(), start=1):
                if _ACTIONABLE_NON_RUN_WORK_RE.search(line):
                    rel = path.relative_to(_REPO_ROOT).as_posix()
                    findings.append(f"{rel}:{line_no}: {line.strip()}")

    assert findings == []


def test_workflow_registry_does_not_declare_work_paths() -> None:
    findings: list[tuple[str, str, str]] = []
    for workflow in list_workflows():
        for step in workflow.steps:
            paths = (
                list(getattr(step, "output_paths", []) or [])
                + list(getattr(step, "required_input_paths", []) or [])
                + list(getattr(step, "output_paths_template", []) or [])
            )
            for raw_path in paths:
                normalized = str(raw_path).replace("\\", "/")
                if normalized.startswith("work/") or "/work/" in normalized:
                    findings.append((workflow.id, step.id, normalized))

    assert findings == []