# pyright: reportMissingTypeStubs=false
"""FR-CLOUD-42: 定期運用 workflow の起動契約。"""

from __future__ import annotations

from pathlib import Path
import re

import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_REQUIREMENTS = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_HITL_WORKFLOW = "auto-blocked-to-human-required.yml"
_REMOVED_WORKFLOWS = {"audit-plans.yml", "tdd-retry-metrics.yml"}


def _load_on(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get(True, {}) or data.get("on", {})


def test_requirement_declares_the_no_schedule_policy() -> None:
    text = _REQUIREMENTS.read_text(encoding="utf-8-sig")
    requirement = next(
        line for line in text.splitlines() if line.startswith("- **FR-CLOUD-42**")
    )
    assert _HITL_WORKFLOW in requirement
    assert "有効な `schedule` を持ってはならない" in requirement
    assert "`workflow_dispatch` 専用" in requirement


def test_repository_managed_workflows_have_no_active_schedule() -> None:
    schedule_line = re.compile(r"^\s+schedule:\s*$", re.MULTILINE)
    paths = [*_WORKFLOWS.glob("*.yml"), *_WORKFLOWS.glob("*.yaml")]
    scheduled = {
        path.name
        for path in paths
        if schedule_line.search(path.read_text(encoding="utf-8"))
    }
    assert scheduled == set()
    hitl_on = _load_on(_WORKFLOWS / _HITL_WORKFLOW)
    assert set(hitl_on) == {"workflow_dispatch"}
    assert "sla_hours" in hitl_on["workflow_dispatch"]["inputs"]


def test_removed_periodic_workflows_are_absent() -> None:
    paths = [*_WORKFLOWS.glob("*.yml"), *_WORKFLOWS.glob("*.yaml")]
    present = {path.name for path in paths}
    assert not (_REMOVED_WORKFLOWS & present)


def test_manual_and_event_fallbacks_are_preserved() -> None:
    assert set(_load_on(_WORKFLOWS / "aas-timeout-monitor.yml")) == {
        "workflow_dispatch"
    }
    assert set(_load_on(_WORKFLOWS / "auto-qa-timeout-watcher.yml")) == {
        "workflow_dispatch"
    }
    label_on = _load_on(_WORKFLOWS / "label-consistency-audit.yml")
    assert set(label_on) == {"workflow_dispatch", "issues"}
    assert set(label_on["issues"]["types"]) == {"labeled", "unlabeled", "closed"}


def test_manual_qa_watcher_cannot_be_silently_disabled() -> None:
    text = (_WORKFLOWS / "auto-qa-timeout-watcher.yml").read_text(encoding="utf-8")
    assert "ENABLE_QA_TIMEOUT_WATCHER" not in text


def test_aas_manual_input_is_validated_before_any_side_effect() -> None:
    path = _WORKFLOWS / "aas-timeout-monitor.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = data["jobs"]["monitor"]["steps"]
    names = [step["name"] for step in steps]
    validate_index = names.index("Validate timeout_hours")
    label_index = names.index("Ensure aas:timeout label exists")
    detect_index = names.index("Detect and handle timed-out AAS issues")
    validation = '[[ "${TIMEOUT_HOURS}" =~ ^[1-9][0-9]*$ ]]'
    assert validation in steps[validate_index]["run"]
    assert validate_index < label_index < detect_index
    assert "gh label" in steps[label_index]["run"]
    assert "CUTOFF_EPOCH=" in steps[detect_index]["run"]
    assert "--limit 1000" in steps[detect_index]["run"]


def test_local_only_azure_skills_have_no_sync_workflow() -> None:
    requirement = _REQUIREMENTS.read_text(encoding="utf-8")
    assert "`sync-azure-skills.yml` を保持してはならない" in requirement
    assert not (_WORKFLOWS / "sync-azure-skills.yml").exists()
