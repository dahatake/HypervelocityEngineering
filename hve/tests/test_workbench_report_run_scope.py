from __future__ import annotations

from pathlib import Path

from hve.workbench.report import save_tasktree_report, save_useractions_report
from hve.workbench.state import UserAction, WorkbenchState


def _state() -> WorkbenchState:
    state = WorkbenchState(workflow_id="wf", run_id="run-1", model="model")
    state.user_actions.append(
        UserAction(
            timestamp="12:00:00",
            level="INFO",
            message="hello",
            step_id="1",
        )
    )
    return state


def test_useractions_report_defaults_to_resolved_work_root(monkeypatch, tmp_path: Path):
    work_root = tmp_path / "work" / "run" / "test-run"
    monkeypatch.setenv("HVE_WORK_ROOT", str(work_root))

    path = save_useractions_report(
        _state(),
        workflow_id="aad-web",
        run_id="test-run",
        started_at_wall=1_700_000_000.0,
    )

    assert path.parent == work_root / "aad-web"
    assert path.name.endswith("-useractions-report.md")
    assert path.is_file()
    assert not (tmp_path / "work" / "aad-web").exists()


def test_tasktree_report_defaults_to_resolved_work_root(monkeypatch, tmp_path: Path):
    work_root = tmp_path / "work" / "run" / "test-run"
    monkeypatch.setenv("HVE_WORK_ROOT", str(work_root))

    path = save_tasktree_report(
        _state(),
        workflow_id="aad-web",
        run_id="test-run",
        started_at_wall=1_700_000_000.0,
    )

    assert path.parent == work_root / "aad-web"
    assert path.name.endswith("-tasktree-report.md")
    assert path.is_file()
    assert not (tmp_path / "work" / "aad-web").exists()


def test_explicit_base_dir_remains_supported(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "ignored"))
    explicit = tmp_path / "custom"

    path = save_useractions_report(
        _state(),
        workflow_id="wf",
        run_id="run-1",
        started_at_wall=1_700_000_000.0,
        base_dir=explicit,
    )

    assert path.parent == explicit / "wf"


def test_tasktree_explicit_base_dir_remains_supported(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "ignored"))
    explicit = tmp_path / "custom"

    path = save_tasktree_report(
        _state(),
        workflow_id="wf",
        run_id="run-1",
        started_at_wall=1_700_000_000.0,
        base_dir=explicit,
    )

    assert path.parent == explicit / "wf"
