"""FR-MAINT-15: the golden gates in test-hve-python.yml use the requirement's minimums."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-python.yml"
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"


def _requirement_block() -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("- **FR-MAINT-15**")]
    assert len(starts) == 1, starts
    block = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line)
    return "\n".join(block)


def _requirement_counts(label: str) -> tuple[int, int]:
    match = re.search(rf"\*\*{label}(\d+) 問中 (\d+) 問\*\*", _requirement_block())
    assert match, label
    return int(match.group(1)), int(match.group(2))


def _golden_step(job_id: str) -> dict:
    jobs = yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)["jobs"]
    steps = [step for step in jobs[job_id]["steps"] if "FR-MAINT-15" in step.get("name", "")]
    assert len(steps) == 1, f"{job_id}: {len(steps)} golden steps"
    return steps[0]


def test_mdq_smoke_gates_the_mdq_golden_set_at_the_required_minimum() -> None:
    total, minimum = _requirement_counts("")
    queries = json.loads((_REPO_ROOT / "mdq" / "golden-queries.json").read_text(encoding="utf-8"))["queries"]
    assert total == len(queries)
    step = _golden_step("mdq-smoke")
    assert "--golden mdq/golden-queries.json" in step["run"]
    assert "--scenarios mdq_auto" in step["run"]
    assert step["env"]["MIN_TOPK"] == str(minimum)


def test_cq_job_gates_each_profile_at_the_required_minimum() -> None:
    profiles = Counter(q["profile"] for q in json.loads(
        (_REPO_ROOT / "cq" / "golden-queries.json").read_text(encoding="utf-8")
    ))
    step = _golden_step("cq-python-tests")
    assert '--baseline ""' in step["run"]
    for profile in ("hve", "app"):
        total, minimum = _requirement_counts(f"{profile} ")
        assert total == profiles[profile], profile
        assert step["env"][f"MIN_TOPK_{profile.upper()}"] == str(minimum), profile
