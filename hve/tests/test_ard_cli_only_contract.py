"""FR-WF-ARD-01: 旧CLI専用制約を廃止しCloud経路を必須化する契約。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_DISPATCHER = _WORKFLOWS_DIR / "auto-orchestrator-dispatcher.yml"
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"


def _dispatcher_text() -> str:
    return _DISPATCHER.read_text(encoding="utf-8")


def _mapping_block(text: str, name: str, opener: str, closer: str) -> str:
    start = text.index(f"{name} = {opener}")
    return text[start : text.index(closer, start) + 1]


def test_dispatcher_trigger_map_registers_ard() -> None:
    block = _mapping_block(_dispatcher_text(), "trigger_map", "[", "]")
    assert "('auto-requirement-definition',       'ARD')" in block

def test_dispatcher_done_map_registers_ard() -> None:
    block = _mapping_block(_dispatcher_text(), "done_map", "{", "}")
    assert "'ard:done':      'ARD'" in block

def test_ard_reusable_workflow_exists_and_is_dispatched() -> None:
    reusable = _WORKFLOWS_DIR / "auto-requirement-definition-reusable.yml"
    assert reusable.is_file()
    assert "auto-requirement-definition-reusable.yml" in _dispatcher_text()


def test_requirement_definition_declares_three_execution_surfaces() -> None:
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("- **FR-WF-ARD-01**:"))
    assert "CLI / GUI / Cloud Orchestrator" in line
    assert "専用 Issue Form" in line


@pytest.mark.parametrize(
    "target",
    ("AAS", "AAD-WEB", "ASDW-WEB", "ADFD", "ADFDV", "AAG", "AAGD", "AAR", "ADA", "ADOC", "AKM"),
)
def test_other_cloud_targets_are_preserved(target: str) -> None:
    block = _mapping_block(_dispatcher_text(), "trigger_map", "[", "]")
    assert re.search(rf"'{re.escape(target)}'", block)
