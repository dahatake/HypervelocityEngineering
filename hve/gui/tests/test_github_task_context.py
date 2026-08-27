"""FR-GUI-40: run-scoped GitHub task context の契約テスト。"""

from __future__ import annotations

import pytest

from hve.gui.github_task_context import GitHubTaskContextKey, GitHubTaskContextStore


def test_default_context_is_session_scoped() -> None:
    store = GitHubTaskContextStore("run-1")
    context = store.current()
    assert context.key == GitHubTaskContextKey("run-1", "", "")
    assert context.source == "manual"


def test_workflow_and_instance_are_isolated() -> None:
    store = GitHubTaskContextStore("run-1")
    first = store.set_manual(
        workflow_id="asdw-web",
        instance_id="asdw-web#APP-001",
        issue_number=11,
    )
    second = store.set_manual(
        workflow_id="asdw-web",
        instance_id="asdw-web#APP-002",
        issue_number=22,
    )
    assert first is not None
    assert second is not None
    assert first.issue_number == 11
    assert second.issue_number == 22
    assert store.get(first.key).issue_number == 11
    assert store.get(second.key).issue_number == 22


def test_selecting_provisional_task_inherits_session_default() -> None:
    store = GitHubTaskContextStore("run-1")
    store.set_manual(issue_number=7, pr_number=8)
    selected = store.select(
        GitHubTaskContextKey("run-1", "asdw-web", "asdw-web#APP-009")
    )
    assert selected.issue_number == 7
    assert selected.pr_number == 8


def test_manual_partial_update_preserves_the_other_number() -> None:
    store = GitHubTaskContextStore("run-1")
    store.set_manual(issue_number=7, pr_number=8)
    updated = store.set_manual(issue_number=9, source="created_in_hub")
    assert updated is not None
    assert updated.issue_number == 9
    assert updated.pr_number == 8
    assert updated.source == "created_in_hub"


@pytest.mark.parametrize("value", [0, -1, False, "1"])
def test_invalid_manual_number_is_rejected_without_clearing(value) -> None:
    store = GitHubTaskContextStore("run-1")
    store.set_manual(issue_number=7)
    with pytest.raises(ValueError):
        store.set_manual(issue_number=value)
    assert store.current().issue_number == 7


def test_orchestrator_event_merges_later_pr_number() -> None:
    store = GitHubTaskContextStore("run-1")
    first = store.apply_github_target(
        {
            "kind": "github_target",
            "run_id": "run-1",
            "workflow_id": "asdw-web",
            "instance_id": "asdw-web#APP-009",
            "repo": "o/r",
            "issue_number": 41,
            "branch": "feature/x",
            "base_branch": "main",
        }
    )
    assert first is not None
    second = store.apply_github_target(
        {
            "kind": "github_target",
            "run_id": "run-1",
            "workflow_id": "asdw-web",
            "instance_id": "asdw-web#APP-009",
            "repo": "o/r",
            "pr_number": 42,
            "branch": "feature/x",
            "base_branch": "main",
        }
    )
    assert second is not None
    assert second.issue_number == 41
    assert second.pr_number == 42
    assert second.source == "orchestrator"


def test_stale_orchestrator_event_cannot_roll_back_context() -> None:
    store = GitHubTaskContextStore("run-1")
    current = store.apply_github_target(
        {
            "kind": "github_target",
            "run_id": "run-1",
            "workflow_id": "ard",
            "instance_id": "ard",
            "ts": "2026-08-26T10:00:02+00:00",
            "pid": 10,
            "seq": 2,
            "repo": "o/r",
            "branch": "new",
        }
    )
    stale = store.apply_github_target(
        {
            "kind": "github_target",
            "run_id": "run-1",
            "workflow_id": "ard",
            "instance_id": "ard",
            "ts": "2026-08-26T10:00:01+00:00",
            "pid": 10,
            "seq": 1,
            "repo": "old/repo",
            "branch": "old",
        }
    )
    assert current is not None
    assert stale is None
    assert store.current().repo == "o/r"
    assert store.current().head_branch == "new"


def test_other_session_event_is_rejected() -> None:
    store = GitHubTaskContextStore("run-1")
    assert store.apply_github_target(
        {"kind": "github_target", "run_id": "run-2", "workflow_id": "ard"}
    ) is None
    assert store.current().key == GitHubTaskContextKey("run-1", "", "")


def test_clear_and_generation_guard() -> None:
    store = GitHubTaskContextStore("run-1")
    initial = store.set_manual(issue_number=7, pr_number=8)
    assert initial is not None
    assert store.clear_issue(expected_generation=initial.generation - 1) is None
    assert store.current().issue_number == 7
    cleared = store.clear_issue(expected_generation=initial.generation)
    assert cleared is not None
    assert cleared.issue_number is None
    assert cleared.pr_number == 8
    assert cleared.generation == initial.generation + 1


def test_context_does_not_store_bodies_tokens_or_urls() -> None:
    store = GitHubTaskContextStore("run-1")
    context = store.apply_github_target(
        {
            "kind": "github_target",
            "run_id": "run-1",
            "workflow_id": "ard",
            "repo": "o/r",
            "issue_number": 1,
            "token": "secret",
            "body": "private",
            "html_url": "https://example.invalid/private",
        }
    )
    assert context is not None
    assert set(vars(context)) == {
        "key",
        "repo",
        "issue_number",
        "pr_number",
        "head_branch",
        "base_branch",
        "source",
        "generation",
    }
