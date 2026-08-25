"""PowerShell workflow registry と Python 正本の完全パリティ契約。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hve.workflow_registry import get_workflow

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PS_REGISTRY = (
    _REPO_ROOT / ".github" / "scripts" / "powershell" / "lib" / "workflow-registry.ps1"
)
_WORKFLOW_START_RE = re.compile(
    r"^\$script:WorkflowRegistryData\['(?P<id>[^']+)'\]\s*=",
    re.MULTILINE,
)


def _workflow_blocks() -> dict[str, str]:
    text = _PS_REGISTRY.read_text(encoding="utf-8-sig")
    matches = list(_WORKFLOW_START_RE.finditer(text))
    assert matches, "PowerShell registry に workflow 定義がありません"
    return {
        match.group("id"): text[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        ]
        for index, match in enumerate(matches)
    }


def _quoted_arg(line: str, name: str) -> str:
    match = re.search(rf"-{re.escape(name)}\s+'([^']*)'", line)
    assert match is not None, f"-{name} が見つかりません: {line}"
    return match.group(1)


def _array_arg(line: str, name: str) -> list[str]:
    match = re.search(rf"-{re.escape(name)}\s+@\(([^)]*)\)", line)
    return re.findall(r"'([^']*)'", match.group(1)) if match else []


def _parse_workflow(workflow_id: str) -> dict:
    block = _workflow_blocks()[workflow_id]
    params_match = re.search(r"^\s*params\s*=\s*@\(([^)]*)\)", block, re.MULTILINE)
    assert params_match is not None, f"{workflow_id}: params が見つかりません"
    params = re.findall(r"'([^']*)'", params_match.group(1))

    steps = []
    for line in block.splitlines():
        if "(NewWorkflowStep " not in line:
            continue
        steps.append(
            {
                "id": _quoted_arg(line, "Id"),
                "title": _quoted_arg(line, "Title"),
                "custom_agent": _quoted_arg(line, "CustomAgent"),
                "depends_on": _array_arg(line, "DependsOn"),
                "skip_fallback_deps": _array_arg(line, "SkipFallbackDeps"),
                "block_unless": _array_arg(line, "BlockUnless"),
                "body_template_path": _quoted_arg(line, "BodyTemplatePath"),
            }
        )
    assert steps, f"{workflow_id}: Step が見つかりません"
    return {"params": params, "steps": steps}


@pytest.mark.parametrize("workflow_id", ("aas", "adfd", "adfdv", "ard"))
def test_powershell_registry_matches_python_ssot(workflow_id: str) -> None:
    workflow = get_workflow(workflow_id)
    assert workflow is not None
    actual = _parse_workflow(workflow_id)

    assert actual["params"] == workflow.params
    assert [step["id"] for step in actual["steps"]] == [
        step.id for step in workflow.steps
    ]
    for actual_step, expected_step in zip(actual["steps"], workflow.steps, strict=True):
        assert actual_step == {
            "id": expected_step.id,
            "title": expected_step.title,
            "custom_agent": expected_step.custom_agent,
            "depends_on": expected_step.depends_on,
            "skip_fallback_deps": expected_step.skip_fallback_deps,
            "block_unless": expected_step.block_unless,
            "body_template_path": expected_step.body_template_path,
        }
