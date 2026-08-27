"""FR-GUI-42: GitHub Hub direct PR creation UI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import github_pr_panel as module  # noqa: E402
from hve.gui.git_ops import GitOpsError, PullRequestPreflight  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch, tmp_path: Path):
    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")
    widget.set_repository_root(tmp_path)
    widget.set_base_branch("main")
    monkeypatch.setattr(widget, "_run", lambda task, ok, ng=None: _sync(widget, task, ok, ng))
    monkeypatch.setattr(module.github_service, "list_pull_requests", lambda *_a, **_kw: [])
    monkeypatch.setattr(module.github_service, "get_repository_metadata", lambda repo: {"default_branch": "main"})
    monkeypatch.setattr(module.github_service, "compare_commits", lambda repo, base, head: {"ahead_by": 2, "behind_by": 0, "files": [{}, {}]})
    monkeypatch.setattr(module.github_service, "find_open_pull_request", lambda repo, head, base: None)
    monkeypatch.setattr(
        module.git_ops,
        "inspect_pull_request",
        lambda root, base: PullRequestPreflight(
            "feature/x", base, 2, 2, True, 0, "o/r"
        ),
    )
    return widget


def _sync(widget, task, ok, ng=None):
    try:
        result = task()
    except (GitHubServiceError, GitOpsError) as exc:
        (ng or widget._show_error)(str(exc))
    else:
        ok(result)


def test_create_form_uses_current_branch_and_defaults(panel) -> None:
    assert panel.create_base_edit.text() == "main"
    assert panel.create_head_label.text()
    assert panel.create_draft_checkbox.isChecked() is False
    assert panel.create_close_issue_checkbox.isChecked() is False
    assert panel.create_pull_request_button is not None


def test_explicit_title_generation_uses_shared_helper(panel, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        module,
        "generate_github_title",
        lambda kind, body, **kwargs: calls.append((kind, body)) or "Generated PR title",
    )
    panel.create_title_edit.setText("old title")
    panel.create_body_edit.set_text("Body")
    panel.generate_pull_request_title()
    assert calls == [("pull_request", "Body")]
    assert panel.create_title_edit.text() == "Generated PR title"


def test_title_generation_requires_body(panel, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        module,
        "generate_github_title",
        lambda *_a, **_kw: calls.append(1),
    )
    panel.create_body_edit.set_text("")
    panel.generate_pull_request_title()
    assert calls == []
    assert "本文" in panel.status_label.text()


def test_default_template_is_loaded_without_overwriting_user_text(panel, tmp_path: Path) -> None:
    template = tmp_path / ".github" / "pull_request_template.md"
    template.parent.mkdir(exist_ok=True)
    template.write_text("## Template\n", encoding="utf-8")
    panel.load_default_template()
    assert panel.create_body_edit.text() == "## Template\n"
    panel.create_body_edit.set_text("user body")
    template.write_text("changed", encoding="utf-8")
    panel.load_default_template()
    assert panel.create_body_edit.text() == "user body"


def test_preflight_displays_compare_summary(panel) -> None:
    panel.refresh_create_preflight()
    text = panel.create_compare_label.text()
    assert "feature/x" in text
    assert "main" in text
    assert "2" in text


def test_dirty_worktree_blocks_create(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.git_ops,
        "inspect_pull_request",
        lambda *_a, **_kw: (_ for _ in ()).throw(GitOpsError("未コミットの変更があります")),
    )
    called = []
    monkeypatch.setattr(module.github_service, "create_pull_request", lambda *_a, **_kw: called.append(1))
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert called == []
    assert "未コミット" in panel.status_label.text()


def test_target_repo_must_match_local_origin(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.git_ops,
        "inspect_pull_request",
        lambda root, base: PullRequestPreflight(
            "feature/x", base, 2, 2, True, 0, "other/repo"
        ),
    )
    called = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: called.append(1),
    )
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert called == []
    assert "一致しません" in panel.status_label.text()


def test_remote_compare_with_no_ahead_commit_blocks_create(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "compare_commits",
        lambda *_a, **_kw: {"ahead_by": 0, "behind_by": 0, "files": []},
    )
    called = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: called.append(1),
    )
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert called == []
    assert "新しい commit" in panel.status_label.text()


@pytest.mark.parametrize(
    "preflight",
    [
        PullRequestPreflight("feature/x", "main", 2, 2, False, 2, "o/r"),
        PullRequestPreflight("feature/x", "main", 2, 2, True, 2, "o/r"),
    ],
)
def test_unpublished_or_unpushed_branch_blocks_create(panel, monkeypatch, preflight) -> None:
    monkeypatch.setattr(module.git_ops, "inspect_pull_request", lambda *_a: preflight)
    called = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: called.append(1),
    )
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert called == []
    assert "push" in panel.status_label.text()


@pytest.mark.parametrize("draft", [False, True])
def test_create_normal_or_draft_and_link(panel, monkeypatch, draft) -> None:
    created = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda repo, title, body, head, base, draft=False: created.append(
            (repo, title, body, head, base, draft)
        )
        or {"number": 77, "html_url": "https://github.com/o/r/pull/77"},
    )
    emitted = []
    panel.pull_request_created.connect(emitted.append)
    panel.create_title_edit.setText("Title")
    panel.create_body_edit.set_text("Body")
    panel.create_draft_checkbox.setChecked(draft)
    panel.create_pull_request()
    assert created == [("o/r", "Title", "Body", "feature/x", "main", draft)]
    assert emitted[-1]["number"] == 77
    assert emitted[-1]["source"] == "created_in_hub"


def test_related_issue_closes_only_default_branch(panel, monkeypatch) -> None:
    bodies = []
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda repo, title, body, head, base, draft=False: bodies.append(body)
        or {"number": 77},
    )
    panel.create_title_edit.setText("Title")
    panel.create_body_edit.set_text("Body")
    panel.create_issue_edit.setText("41")
    panel.create_close_issue_checkbox.setChecked(True)
    panel.create_pull_request()
    assert bodies[-1].startswith("Closes #41")

    panel.set_base_branch("develop")
    panel.create_title_edit.setText("Title")
    panel.create_body_edit.set_text("Body")
    panel.create_issue_edit.setText("41")
    panel.create_pull_request()
    assert bodies[-1].startswith("#41")
    assert "Closes #41" not in bodies[-1]


def test_existing_open_pull_request_is_selected_without_create(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "find_open_pull_request",
        lambda repo, head, base: {"number": 9, "html_url": "https://github.com/o/r/pull/9"},
    )
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request",
        lambda *_a, **_kw: pytest.fail("must not create duplicate"),
    )
    emitted = []
    panel.pull_request_created.connect(emitted.append)
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert emitted[-1] == {
        "number": 9,
        "repo": "o/r",
        "source": "created_in_hub",
    }
    assert "既存" in panel.status_label.text()


def test_create_is_disabled_while_request_is_pending(panel, monkeypatch) -> None:
    pending = {}
    monkeypatch.setattr(panel, "_run", lambda task, ok, ng=None: pending.update(task=task, ok=ok, ng=ng))
    panel.create_title_edit.setText("Title")
    panel.create_pull_request()
    assert not panel.create_pull_request_button.isEnabled()
    assert not panel.create_title_edit.isEnabled()


@pytest.mark.parametrize("change", ["repo", "base"])
def test_stale_create_result_is_not_linked_after_target_change(
    panel, monkeypatch, change
) -> None:
    pending: dict[str, object] = {}
    monkeypatch.setattr(
        panel,
        "_run",
        lambda task, ok, ng=None: pending.update(task=task, ok=ok, ng=ng),
    )
    panel.create_title_edit.setText("Title")
    emitted: list[dict] = []
    panel.pull_request_created.connect(emitted.append)
    panel.create_pull_request()
    if change == "repo":
        panel.set_repo("other/repo")
    else:
        panel.set_base_branch("develop")
    pending["ok"](
        {
            "pull_request": {"number": 77},
            "local": PullRequestPreflight(
                "feature/x", "main", 2, 2, True, 0, "o/r"
            ),
        }
    )
    assert emitted == []
    assert panel._linked_number is None
    assert "#77" in panel.status_label.text()
    assert "関連付けません" in panel.status_label.text()


def test_stale_preflight_failure_does_not_replace_new_target_status(
    panel, monkeypatch
) -> None:
    pending: dict[str, object] = {}
    monkeypatch.setattr(
        panel,
        "_run",
        lambda task, ok, ng=None: pending.update(ok=ok, ng=ng),
    )
    panel.refresh_create_preflight()
    panel.set_base_branch("develop")
    panel.status_label.setText("new target")
    pending["ng"]("old failure")
    assert panel.status_label.text() == "new target"


def test_current_preflight_failure_clears_previous_compare(
    panel, monkeypatch
) -> None:
    pending: dict[str, object] = {}
    monkeypatch.setattr(
        panel,
        "_run",
        lambda task, ok, ng=None: pending.update(ok=ok, ng=ng),
    )
    panel.create_compare_label.setText("old compare")
    panel.refresh_create_preflight()
    pending["ng"]("failed")
    assert "old compare" not in panel.create_compare_label.text()
    assert "失敗" in panel.create_compare_label.text()
