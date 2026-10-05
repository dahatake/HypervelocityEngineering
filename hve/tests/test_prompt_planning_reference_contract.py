"""Planning-reference contract (FR-PLAN-01).

``_TARGET_PROMPTS`` is the closed regression set of Prompts that write plans.
Each delegates planning to Skill ``task-dag-planning`` with one sentence and
does not copy mechanical split rules (``SPLIT_REQUIRED`` / ``task_scope`` /
``context_size``) that FR-PLAN-01 removed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_ROOT = _REPO_ROOT / ".github" / "prompts"

_TASK_DAG_SKILL = ".github/skills/task-dag-planning/SKILL.md"
_TASK_DAG_DETAIL = ".github/skills/_hve-plan-artifacts/hve-binding.md"
_PLAN_TEMPLATE = ".github/skills/_hve-plan-artifacts/plan-template.md"
_CANONICAL_PATHS = (_TASK_DAG_SKILL, _TASK_DAG_DETAIL, _PLAN_TEMPLATE)

_TARGET_PROMPTS = tuple(
    "Arch-AgenticRetrieval-Detail.prompt.md Arch-DataCatalog.prompt.md "
    "Arch-Dataflow-AppCatalog.prompt.md Arch-Dataflow-AppSpec.prompt.md Arch-Dataflow-DataModel.prompt.md "
    "Arch-Dataflow-MonitoringDesign.prompt.md Arch-Dataflow-ServiceCatalog.prompt.md Arch-Dataflow-TDD-TestSpec.prompt.md "
    "Arch-Dataflow-TestStrategy.prompt.md Arch-DataModeling.prompt.md Arch-ImprovementPlanner.prompt.md "
    "Arch-Microservice-DomainAnalytics.prompt.md Arch-Microservice-ServiceCatalog.prompt.md Arch-Microservice-ServiceIdentify.prompt.md "
    "Arch-Microservice-ServiceDetail.prompt.md Arch-TDD-TestStrategy.prompt.md Arch-UI-Detail.prompt.md Arch-UI-List.prompt.md "
    "Dev-Dataflow-DataServiceSelect.prompt.md Dev-Dataflow-TestCoding.prompt.md Dev-Microservice-Azure-AddServiceDeploy.prompt.md "
    "Dev-Microservice-Azure-ComputeDesign.prompt.md Dev-Microservice-Azure-UICoding.prompt.md QA-AzureArchitectureReview.prompt.md "
    "QA-AzureDependencyReview.prompt.md".split()
)

_DELEGATION_SENTENCE = "計画を書く場合は Skill `task-dag-planning` に従う"
_METADATA_FIELDS = ("task_scope", "context_size", "split_decision", "subissues_count", "implementation_files")
_METADATA_COMMENTS = tuple(f"<!-- {field}:" for field in _METADATA_FIELDS)
# FR-PLAN-01: 分割を機械的に強制する規則の語彙。Skill・Prompt・指示に置かない。
_FORBIDDEN_SPLIT_RULE_TOKENS = (
    "SPLIT_REQUIRED",
    "split_decision",
    "裁量で判定を覆さない",
    "## 分割判定",
    "task_scope=multi",
    "context_size=large",
    "subissues_count",
    "implementation_files",
)
_SCANNED_ROOTS = (
    _REPO_ROOT / ".github" / "skills",
    _REPO_ROOT / ".github" / "prompts",
)
_SCANNED_FILES = (_REPO_ROOT / ".github" / "copilot-instructions.md",)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _scanned_markdown() -> list[Path]:
    files = list(_SCANNED_FILES)
    for root in _SCANNED_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
        files.extend(sorted(root.rglob("*.yaml")))
    return files


def test_no_mechanical_split_rules_in_skills_prompts_and_instructions() -> None:
    offenders = []
    for path in _scanned_markdown():
        text = _read(path)
        for token in _FORBIDDEN_SPLIT_RULE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(_REPO_ROOT).as_posix()}: {token}")
    assert not offenders, "\n".join(offenders)


def test_gui_text_does_not_mention_removed_split_required() -> None:
    # v3.36: GUI の表示文言・翻訳ソース・コメントも撤去済みの判定名に触れない。
    gui_root = _REPO_ROOT / "hve" / "gui"
    offenders = []
    for path in sorted([*gui_root.rglob("*.py"), *gui_root.rglob("*.ts")]):
        relative = path.relative_to(gui_root)
        if relative.parts[0] == "tests":
            continue
        if "SPLIT_REQUIRED" in _read(path):
            offenders.append(path.relative_to(_REPO_ROOT).as_posix())
    assert not offenders, "\n".join(offenders)


def test_plan_template_keeps_completion_criteria_without_split_metadata() -> None:
    template = _read(_REPO_ROOT / _PLAN_TEMPLATE)
    assert "## 完了条件" in template, "FR-DOD-02"
    for marker in _METADATA_COMMENTS:
        assert marker not in template, marker
    assert "## 分割判定" not in template


def test_task_dag_skill_keeps_the_three_minimal_rules() -> None:
    skill = _read(_REPO_ROOT / _TASK_DAG_SKILL)
    for token in ("受入条件", "非対象", "exit code", "独立して検証できる"):
        assert token in skill, token


@pytest.mark.parametrize(
    "prompt_relative_path",
    _TARGET_PROMPTS,
    ids=lambda relative: Path(relative).stem,
)
def test_planning_prompts_delegate_with_one_sentence(prompt_relative_path: str) -> None:
    prompt_path = _PROMPTS_ROOT / prompt_relative_path
    assert prompt_path.is_file(), prompt_relative_path
    text = _read(prompt_path)
    assert text.count(_DELEGATION_SENTENCE) == 1, prompt_relative_path
    for marker in _METADATA_COMMENTS:
        assert marker not in text, marker
