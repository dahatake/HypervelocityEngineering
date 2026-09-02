"""FR-WF-ASDW-05: do not publish a rollback drill without its runtime assets."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "rollback-drill.yml"
_ACTIVE_REFERENCE_FILES = (
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "users-guide" / "workflow-reference.md",
)


def test_orphaned_rollback_drill_workflow_is_absent() -> None:
    assert not _WORKFLOW.exists()


def test_user_guides_do_not_advertise_the_removed_workflow() -> None:
    for path in _ACTIVE_REFERENCE_FILES:
        assert "rollback-drill.yml" not in path.read_text(encoding="utf-8")
