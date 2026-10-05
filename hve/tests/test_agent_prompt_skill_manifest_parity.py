"""Agent prompt の「Agent 固有の Skills 依存」と skill_manifest.json の整合を検証する。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hve.skill_resolver import discover_available_skills, get_required_skills_for_step
from hve.workflow_registry import get_workflow

_PROMPTS = Path(__file__).resolve().parents[2] / ".github" / "prompts"
_SECTION_RE = re.compile(r"## Agent 固有の Skills 依存\n(.*?)(?=\n## |\n<|\Z)", re.DOTALL)
# 全 Agent 共通の基盤 Skill は Workflow 単位の公開対象にしない（システムテスト F-03 の対象外）。
_COMMON_SKILLS = frozenset({"agent-common-preamble", "work-artifacts-layout"})
_SKILL_RE = re.compile(r"^- `([a-z0-9-]+)`", re.MULTILINE)


def _declared_skills(agent: str) -> set[str]:
    text = (_PROMPTS / f"{agent}.prompt.md").read_text(encoding="utf-8")
    match = _SECTION_RE.search(text)
    assert match, f"{agent}: Skills 依存セクションがありません"
    return set(_SKILL_RE.findall(match.group(1)))


@pytest.mark.parametrize(
    ("workflow_id", "step_id"),
    [("aas", "1"), ("aas", "2.1"), ("ada", "2"), ("ada", "4.1")],
)
def test_agent_prompt_skills_are_exposed_to_steps(workflow_id: str, step_id: str) -> None:
    available = set(discover_available_skills())
    step = next(s for s in get_workflow(workflow_id).steps if s.id == step_id)
    assert step.custom_agent
    expected = (_declared_skills(step.custom_agent) & available) - _COMMON_SKILLS
    exposed = set(
        get_required_skills_for_step(
            workflow_id, step.id, step_declared_required=step.required_skills
        )
    )
    assert expected, step.custom_agent
    assert expected <= exposed, f"Skill 未公開: {sorted(expected - exposed)}"