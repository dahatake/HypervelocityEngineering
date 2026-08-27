"""FR-GUI-43: Pull Request post-create metadata and partial success."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import github_pr_panel as module  # noqa: E402
from hve.gui.git_ops import PullRequestPreflight  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_service_partial_success_keeps_retry_payload(monkeypatch) -> None:
    calls = []

    def _metadata(*_a, **_kw):
        calls.append("metadata")
        raise module.github_service.github_api.GitHubAPIError("bad", 422)

    monkeypatch.setattr(
        module.github_service.github_api, "update_pull_request_metadata", _metadata
    )
    monkeypatch.setattr(
        module.github_service.github_api,
        "request_pull_request_reviewers",
        lambda *_a, **_kw: calls.append("reviewers") or {},
    )
    result = module.github_service.apply_pull_request_metadata(
        "o/r",
        7,
        labels=["bug"],
        assignees=["alice"],
        milestone=2,
        reviewers=["bob"],
        team_reviewers=["platform"],
    )
    assert calls == ["metadata", "reviewers"]
    assert result["warnings"] == [{"kind": "metadata"}]
    assert result["retry"]["pr_number"] == 7
    assert result["retry"]["labels"] == ["bug"]
    assert "reviewers" not in result["retry"]


def test_service_reviewer_failure_is_separate(monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service.github_api,
        "update_pull_request_metadata",
        lambda *_a, **_kw: {},
    )
    monkeypatch.setattr(
        module.github_service.github_api,
        "request_pull_request_reviewers",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            module.github_service.github_api.GitHubAPIError("bad", 422)
        ),
    )
    result = module.github_service.apply_pull_request_metadata(
        "o/r", 7, reviewers=["bob"], team_reviewers=["platform"]
    )
    assert result["warnings"] == [{"kind": "reviewers"}]
    assert result["retry"]["reviewers"] == ["bob"]
    assert result["retry"]["team_reviewers"] == ["platform"]


def test_gui_pull_request_create_disables_automatic_retry(monkeypatch) -> None:
    captured = {}

    def _create(title, body, head, base, **kwargs):
        captured.update(kwargs)
        return {"number": 7}

    monkeypatch.setattr(
        module.github_service.github_api, "create_pull_request_details", _create
    )
    result = module.github_service.create_pull_request(
        "o/r", "Title", "Body", "feature/x", "main"
    )
    assert result["number"] == 7
    assert captured["max_retries"] == 1


@pytest.fixture
def panel(qapp, monkeypatch, tmp_path: Path):
    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")
    widget.set_repository_root(tmp_path)
    widget.set_base_branch("main")
    monkeypatch.setattr(
        module.git_ops,
        "inspect_pull_request",
        lambda *_a, **_kw: PullRequestPreflight(
            "feature/x", "main", 2, 2, True, 0, "o/r"
        ),
    )
    monkeypatch.setattr(module.github_service, "find_open_pull_request", lambda *_a: None)
    monkeypatch.setattr(
        module.github_service,
        "get_repository_metadata",
        lambda *_a: {"default_branch": "main"},
    )
    monkeypatch.setattr(
        module.github_service,
        "compare_commits",
        lambda *_a: {"ahead_by": 2, "behind_by": 0},
    )
    monkeypatch.setattr(
        module.github_service,
        "list_pull_requests",
        lambda *_a, **_kw: [],
    )
    monkeypatch.setattr(
        widget,
        "_run",
        lambda task, ok, ng=None: _sync(widget, task, ok, ng),
    )
    return widget


def _sync(widget, task, ok, ng=None):
    try:
        result = task()
    except (GitHubServiceError, module.git_ops.GitOpsError) as exc:
        (ng or widget._show_error)(str(exc))
    else:
        ok(result)


def _fill_metadata(panel) -> None:
    panel.create_labels_edit.setText("bug, docs")
    panel.create_assignees_edit.setText("alice")
    panel.create_milestone_edit.setText("2")
    panel.create_reviewers_edit.setText("bob")
    panel.create_team_reviewers_edit.setText("platform")


def test_create_emits_pr_before_post_create_metadata(panel, monkeypatch) -> None:
    order = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: order.append("create") or {"number": 77},
    )
    monkeypatch.setattr(
        module.github_service,
        "apply_pull_request_metadata",
        lambda *_a, **_kw: order.append("metadata") or {"warnings": [], "retry": None},
    )
    panel.pull_request_created.connect(lambda _r: order.append("emit"))
    _fill_metadata(panel)
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert order[:3] == ["create", "emit", "metadata"]


def test_metadata_failure_keeps_pr_and_enables_retry(panel, monkeypatch) -> None:
    create_calls = []
    metadata_calls = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: create_calls.append(1) or {"number": 77},
    )
    monkeypatch.setattr(
        module.github_service,
        "apply_pull_request_metadata",
        lambda *_a, **kw: metadata_calls.append(kw)
        or {
            "warnings": [{"kind": "reviewers"}],
            "retry": {
                "pr_number": 77,
                "reviewers": ["bob"],
                "team_reviewers": ["platform"],
            },
        },
    )
    _fill_metadata(panel)
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert create_calls == [1]
    assert panel.retry_metadata_button.isEnabled()
    assert "#77" in panel.status_label.text()
    assert "レビュアー" in panel.status_label.text()

    panel.retry_pull_request_metadata()
    assert create_calls == [1]
    assert len(metadata_calls) == 2


def test_created_pr_url_is_kept_when_metadata_fails(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: {
            "number": 77,
            "html_url": "https://github.com/o/r/pull/77",
        },
    )
    monkeypatch.setattr(
        module.github_service,
        "apply_pull_request_metadata",
        lambda *_a, **_kw: {
            "warnings": [{"kind": "metadata"}],
            "retry": {"pr_number": 77, "labels": ["bug"]},
        },
    )
    panel.create_labels_edit.setText("bug")
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert panel._created_pr_url == "https://github.com/o/r/pull/77"
    assert "https://github.com/o/r/pull/77" in panel.created_pr_url_label.text()


def test_repo_or_task_change_clears_pending_retry(panel) -> None:
    panel._pending_pr_metadata = {
        "repo": "o/r",
        "pr_number": 77,
        "reviewers": ["bob"],
    }
    panel.retry_metadata_button.setEnabled(True)
    panel.set_task_target("o/r", 88)
    assert panel._pending_pr_metadata is None
    assert not panel.retry_metadata_button.isEnabled()

    panel._pending_pr_metadata = {
        "repo": "o/r",
        "pr_number": 77,
        "reviewers": ["bob"],
    }
    panel.retry_metadata_button.setEnabled(True)
    panel.set_repo("other/repo")
    assert panel._pending_pr_metadata is None
    assert not panel.retry_metadata_button.isEnabled()


def test_unclassified_post_create_failure_is_not_retryable(panel) -> None:
    panel._on_post_create_metadata(
        77,
        "o/r",
        {"warnings": [{"kind": "post_create_unknown"}], "retry": None},
    )
    assert panel._pending_pr_metadata is None
    assert not panel.retry_metadata_button.isEnabled()
    assert "再試行不可" in panel.status_label.text()


def test_metadata_fields_are_disabled_during_create(panel, monkeypatch) -> None:
    pending = {}
    monkeypatch.setattr(
        panel,
        "_run",
        lambda task, ok, ng=None: pending.update(task=task, ok=ok, ng=ng),
    )
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    for widget in (
        panel.create_labels_edit,
        panel.create_assignees_edit,
        panel.create_milestone_edit,
        panel.create_reviewers_edit,
        panel.create_team_reviewers_edit,
    ):
        assert not widget.isEnabled()
