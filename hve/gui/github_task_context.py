"""Run-scoped GitHub task association for the GUI (FR-GUI-40)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

__all__ = ["GitHubTaskContext", "GitHubTaskContextKey", "GitHubTaskContextStore"]

_VALID_SOURCES = frozenset({"manual", "created_in_hub", "orchestrator"})
_UNSET = object()


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


@dataclass(frozen=True)
class GitHubTaskContextKey:
    session_run_id: str
    workflow_id: str = ""
    instance_id: str = ""


@dataclass(frozen=True)
class GitHubTaskContext:
    key: GitHubTaskContextKey
    repo: str = ""
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    head_branch: str = ""
    base_branch: str = ""
    source: str = "manual"
    generation: int = 0


class GitHubTaskContextStore:
    """Keep GitHub associations isolated within one GUI session."""

    def __init__(self, session_run_id: str) -> None:
        run_id = (session_run_id or "").strip()
        if not run_id:
            raise ValueError("session_run_id is required")
        self._session_run_id = run_id
        self._contexts: dict[GitHubTaskContextKey, GitHubTaskContext] = {}
        self._event_orders: dict[GitHubTaskContextKey, tuple[str, int, int]] = {}
        self._current_key = GitHubTaskContextKey(run_id)
        self._contexts[self._current_key] = GitHubTaskContext(self._current_key)

    def current(self) -> GitHubTaskContext:
        return self._contexts[self._current_key]

    def get(self, key: GitHubTaskContextKey) -> GitHubTaskContext:
        return self._contexts.get(key, GitHubTaskContext(key))

    def for_task(self, workflow_id: str, instance_id: str = "") -> GitHubTaskContext:
        key = GitHubTaskContextKey(
            self._session_run_id,
            (workflow_id or "").strip(),
            (instance_id or workflow_id or "").strip(),
        )
        context = self._contexts.get(key)
        if context is not None:
            return context
        return self._contexts[GitHubTaskContextKey(self._session_run_id)]

    def select(self, key: GitHubTaskContextKey) -> GitHubTaskContext:
        if key.session_run_id != self._session_run_id:
            raise ValueError("task context belongs to another GUI session")
        self._current_key = key
        context = self._contexts.get(key)
        if context is None:
            default = self._contexts[GitHubTaskContextKey(self._session_run_id)]
            context = replace(default, key=key)
            self._contexts[key] = context
        return context

    def set_manual(
        self,
        *,
        workflow_id: str = "",
        instance_id: str = "",
        repo: str = "",
        issue_number: Any = _UNSET,
        pr_number: Any = _UNSET,
        source: str = "manual",
        expected_generation: Optional[int] = None,
    ) -> Optional[GitHubTaskContext]:
        key = GitHubTaskContextKey(
            self._session_run_id,
            (workflow_id or "").strip(),
            (instance_id or workflow_id or "").strip(),
        )
        return self._update(
            key,
            repo=repo,
            issue_number=issue_number,
            pr_number=pr_number,
            source=source,
            expected_generation=expected_generation,
        )

    def apply_github_target(
        self,
        payload: Any,
        *,
        fallback_workflow_id: str = "",
        fallback_instance_id: str = "",
    ) -> Optional[GitHubTaskContext]:
        if not isinstance(payload, dict) or payload.get("kind") != "github_target":
            return None
        event_run_id = str(payload.get("run_id") or "").strip()
        if event_run_id and event_run_id != self._session_run_id:
            return None
        workflow_id = str(payload.get("workflow_id") or fallback_workflow_id or "").strip()
        instance_id = str(
            payload.get("instance_id") or fallback_instance_id or workflow_id
        ).strip()
        key = GitHubTaskContextKey(self._session_run_id, workflow_id, instance_id)
        order = self._event_order(payload)
        previous_order = self._event_orders.get(key)
        if order is not None and previous_order is not None and order <= previous_order:
            return None
        current = self.get(key)
        issue = _positive_int(payload.get("issue_number"))
        pull = _positive_int(payload.get("pr_number"))
        context = replace(
            current,
            repo=str(payload.get("repo") or current.repo).strip(),
            issue_number=issue if issue is not None else current.issue_number,
            pr_number=pull if pull is not None else current.pr_number,
            head_branch=str(payload.get("branch") or current.head_branch).strip(),
            base_branch=str(payload.get("base_branch") or current.base_branch).strip(),
            source="orchestrator",
            generation=current.generation + 1,
        )
        self._contexts[key] = context
        if order is not None:
            self._event_orders[key] = order
        self._current_key = key
        return context

    def clear_issue(
        self, *, expected_generation: Optional[int] = None
    ) -> Optional[GitHubTaskContext]:
        return self._update_current(
            issue_number=None,
            source="manual",
            expected_generation=expected_generation,
            clear_issue=True,
        )

    def clear_pull_request(
        self, *, expected_generation: Optional[int] = None
    ) -> Optional[GitHubTaskContext]:
        return self._update_current(
            pr_number=None,
            source="manual",
            expected_generation=expected_generation,
            clear_pr=True,
        )

    def _update(
        self,
        key: GitHubTaskContextKey,
        *,
        repo: str,
        issue_number: Any,
        pr_number: Any,
        source: str,
        expected_generation: Optional[int],
    ) -> Optional[GitHubTaskContext]:
        self.select(key)
        current = self.current()
        if expected_generation is not None and expected_generation != current.generation:
            return None
        resolved_source = source if source in _VALID_SOURCES else "manual"
        resolved_issue = self._manual_number(issue_number, current.issue_number)
        resolved_pull = self._manual_number(pr_number, current.pr_number)
        context = replace(
            current,
            repo=(repo or current.repo).strip(),
            issue_number=resolved_issue,
            pr_number=resolved_pull,
            source=resolved_source,
            generation=current.generation + 1,
        )
        self._contexts[key] = context
        return context

    def _update_current(
        self,
        *,
        source: str,
        expected_generation: Optional[int],
        issue_number: Optional[int] = None,
        pr_number: Optional[int] = None,
        clear_issue: bool = False,
        clear_pr: bool = False,
    ) -> Optional[GitHubTaskContext]:
        current = self.current()
        if expected_generation is not None and expected_generation != current.generation:
            return None
        context = replace(
            current,
            issue_number=None if clear_issue else issue_number or current.issue_number,
            pr_number=None if clear_pr else pr_number or current.pr_number,
            source=source if source in _VALID_SOURCES else "manual",
            generation=current.generation + 1,
        )
        self._contexts[self._current_key] = context
        return context

    @staticmethod
    def _manual_number(value: Any, current: Optional[int]) -> Optional[int]:
        if value is _UNSET or value is None:
            return current
        number = _positive_int(value)
        if number is None:
            raise ValueError("GitHub issue and pull request numbers must be positive integers")
        return number

    @staticmethod
    def _event_order(payload: dict[str, Any]) -> Optional[tuple[str, int, int]]:
        timestamp = payload.get("ts")
        pid = payload.get("pid")
        sequence = payload.get("seq")
        if (
            not isinstance(timestamp, str)
            or not timestamp
            or isinstance(pid, bool)
            or not isinstance(pid, int)
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
        ):
            return None
        return timestamp, pid, sequence
