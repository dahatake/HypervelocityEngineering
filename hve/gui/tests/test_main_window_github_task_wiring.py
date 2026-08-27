"""FR-GUI-40: Workbench の github_target を GitHub Hub へ配線する。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve import runtime_observability as rto  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, tmp_path: Path, monkeypatch):
    from hve.gui import github_service, settings_store
    from hve.gui.github_threads import GitHubWorker
    from hve.gui.main_window import MainWindow

    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / ".settings.txt")
    monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
    monkeypatch.setattr(github_service, "list_issues", lambda *_a, **_kw: [])
    monkeypatch.setattr(github_service, "list_pull_requests", lambda *_a, **_kw: [])
    monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())
    win = MainWindow(repo_root=tmp_path)
    yield win
    if win._github_window is not None:
        win._github_window.close()
    win.deleteLater()


def _target_line(run_id: str, **fields) -> str:
    context = rto.RuntimeContext(
        run_id=run_id,
        workflow_id=str(fields.pop("workflow_id", "asdw-web")),
        instance_id=str(fields.pop("instance_id", "asdw-web#APP-009")),
    )
    return rto.format_stats_line(rto.build_github_target_event(context=context, **fields))


def test_event_before_hub_open_is_applied_when_opened(main_window) -> None:
    line = _target_line(
        main_window._session_workdir.session_run_id,
        repo="o/r",
        issue_number=41,
        pr_number=42,
        branch="feature/x",
        base_branch="main",
    )
    main_window._page_workbench.job_log_line.emit("asdw-web#APP-009", "", line)
    main_window._open_github_window()
    context = main_window._github_window.task_context()
    assert context.issue_number == 41
    assert context.pr_number == 42
    assert context.key.instance_id == "asdw-web#APP-009"


def test_event_updates_open_hub_without_persisting_linked_pr(
    main_window, monkeypatch
) -> None:
    from hve.gui import settings_store

    writes: list[tuple[str, object]] = []
    monkeypatch.setattr(
        settings_store, "set_option", lambda key, value: writes.append((key, value))
    )
    main_window._open_github_window()
    line = _target_line(
        main_window._session_workdir.session_run_id,
        workflow_id="ard",
        instance_id="ard",
        repo="o/r",
        pr_number=9,
        branch="topic",
        base_branch="main",
    )
    main_window._page_workbench.job_log_line.emit("ard", "", line)
    assert main_window._github_window.task_context().pr_number == 9
    assert not any(key == "linked_pr_number" for key, _value in writes)


def test_unrelated_stats_line_does_not_replace_current_context(main_window) -> None:
    main_window._open_github_window()
    before = main_window._github_window.task_context()
    line = rto.format_stats_line(
        rto.build_event(
            "step_status",
            context=rto.RuntimeContext(
                run_id=main_window._session_workdir.session_run_id,
                workflow_id="other",
                instance_id="other",
            ),
            status="running",
        )
    )
    main_window._page_workbench.job_log_line.emit("other", "", line)
    assert main_window._github_window.task_context() == before


def test_issue_snapshot_is_applied_only_to_github_creating_run(main_window) -> None:
    from hve.gui.orchestrate_args import OrchestrateArgs

    main_window._github_task_contexts.set_manual(issue_number=41)
    create_args = OrchestrateArgs(workflow="ard", create_pr=True)
    main_window._apply_github_task_context_to_args(create_args, "ard")
    assert create_args.issue_number == 41

    local_args = OrchestrateArgs(workflow="ard")
    main_window._apply_github_task_context_to_args(local_args, "ard")
    assert local_args.issue_number is None


def test_started_workflow_activates_provisional_context(main_window) -> None:
    main_window._github_task_contexts.set_manual(issue_number=41)
    main_window._page_workbench._current_workflow_id = "ard"
    main_window._on_github_workflow_process_started()
    current = main_window._github_task_contexts.current()
    assert current.key.workflow_id == "ard"
    assert current.key.instance_id == "ard"
    assert current.issue_number == 41


