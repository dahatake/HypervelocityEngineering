"""FR-GUI-37: GUI-lifetime targeted branch cleanup monitor RED contract."""

from __future__ import annotations

import importlib
import inspect
from unittest.mock import Mock

import pytest


def _types():
    cleanup_module = importlib.import_module("hve.branch_cleanup")
    monitor_module = importlib.import_module("hve.gui.github_branch_cleanup_monitor")
    return cleanup_module.LocalBranchCleanupTarget, monitor_module.GitHubBranchCleanupMonitor


def _target(**overrides):
    target_type, _monitor_type = _types()
    values = {
        "repo": "owner/repo",
        "pr_number": 41,
        "branch": "copilot-sdk/aas-1234abcd",
        "base_branch": "main",
        "created_by_hve": True,
    }
    values.update(overrides)
    return target_type(**values)


def _pull_request(*, state: str = "open", merged: bool = False):
    return {
        "number": 41,
        "state": state,
        "merged": merged,
        "head": {
            "ref": "copilot-sdk/aas-1234abcd",
            "repo": {"full_name": "owner/repo"},
        },
        "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
    }


class TestTargetedPollingState:
    def test_new_target_is_polled_by_exact_pr_number(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        assert monitor.watch(_target(), now=100) is True

        requests = monitor.poll_due(now=100)

        assert len(requests) == 1
        assert requests[0].repo == "owner/repo"
        assert requests[0].pr_number == 41

    def test_inflight_target_is_not_polled_twice(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)

        assert len(monitor.poll_due(now=100)) == 1
        assert monitor.poll_due(now=200) == []

    def test_open_pr_is_rescheduled_only_after_interval(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)
        request = monitor.poll_due(now=100)[0]

        assert monitor.complete(request, pull_request=_pull_request(), now=105) is None
        assert monitor.poll_due(now=134.9) == []
        assert len(monitor.poll_due(now=135)) == 1

    def test_api_failure_is_best_effort_and_rescheduled(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)
        request = monitor.poll_due(now=100)[0]

        assert monitor.complete(
            request,
            error="temporary",
            retryable=True,
            now=105,
        ) is None
        assert monitor.poll_due(now=134.9) == []
        assert len(monitor.poll_due(now=135)) == 1

    def test_non_retryable_api_failure_stops_target(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)
        request = monitor.poll_due(now=100)[0]

        assert monitor.complete(
            request,
            error="not found",
            retryable=False,
            now=105,
        ) is None
        assert monitor.poll_due(now=1000) == []

    def test_merged_pr_emits_one_local_cleanup_request_and_stops_polling(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        target = _target()
        monitor.watch(target, now=100)
        request = monitor.poll_due(now=100)[0]
        pull_request = _pull_request(state="closed", merged=True)

        cleanup = monitor.complete(request, pull_request=pull_request, now=105)

        assert cleanup is not None
        assert cleanup.target == target
        assert cleanup.pull_request == pull_request
        assert monitor.poll_due(now=1000) == []

    def test_merged_completion_is_emitted_once_and_target_cannot_be_readded(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        target = _target()
        monitor.watch(target, now=100)
        request = monitor.poll_due(now=100)[0]
        pull_request = _pull_request(state="closed", merged=True)

        assert monitor.complete(request, pull_request=pull_request, now=105) is not None
        assert monitor.complete(request, pull_request=pull_request, now=106) is None
        assert monitor.watch(target, now=107) is False
        assert monitor.poll_due(now=1000) == []

    def test_closed_unmerged_pr_stops_without_cleanup(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)
        request = monitor.poll_due(now=100)[0]

        cleanup = monitor.complete(
            request,
            pull_request=_pull_request(state="closed", merged=False),
            now=105,
        )

        assert cleanup is None
        assert monitor.poll_due(now=1000) == []

    def test_malformed_or_wrong_number_response_stops_fail_closed(self) -> None:
        _target_type, monitor_type = _types()
        for response in ({}, {**_pull_request(), "number": 99}):
            monitor = monitor_type(enabled=True, poll_interval_seconds=30)
            monitor.watch(_target(), now=100)
            request = monitor.poll_due(now=100)[0]

            assert monitor.complete(request, pull_request=response, now=105) is None
            assert monitor.poll_due(now=1000) == []

    def test_replacing_inflight_target_invalidates_late_completion(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        old_target = _target()
        new_target = _target(branch="copilot-sdk/aas-5678efab")
        monitor.watch(old_target, now=100)
        old_request = monitor.poll_due(now=100)[0]

        assert monitor.watch(new_target, now=101) is True
        assert monitor.complete(
            old_request,
            pull_request=_pull_request(state="closed", merged=True),
            now=102,
        ) is None
        new_request = monitor.poll_due(now=102)[0]
        assert new_request.target == new_target

    def test_duplicate_watch_does_not_reset_an_inflight_target(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        target = _target()
        assert monitor.watch(target, now=100) is True
        request = monitor.poll_due(now=100)[0]

        assert monitor.watch(target, now=200) is False
        assert monitor.poll_due(now=200) == []
        assert monitor.complete(request, pull_request=_pull_request(), now=205) is None

    def test_targets_are_independent(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=100)
        monitor.watch(
            _target(pr_number=42, branch="copilot-sdk/aas-5678efab"),
            now=100,
        )

        requests = monitor.poll_due(now=100)

        assert {request.pr_number for request in requests} == {41, 42}
        by_number = {request.pr_number: request for request in requests}
        monitor.complete(
            by_number[41],
            error="temporary",
            retryable=True,
            now=105,
        )
        cleanup = monitor.complete(
            by_number[42],
            pull_request={
                **_pull_request(state="closed", merged=True),
                "number": 42,
                "head": {
                    "ref": "copilot-sdk/aas-5678efab",
                    "repo": {"full_name": "owner/repo"},
                },
            },
            now=105,
        )
        assert cleanup is not None
        assert cleanup.target.pr_number == 42
        assert monitor.poll_due(now=135)[0].pr_number == 41


class TestMonitorLifecycle:
    def test_disabled_monitor_does_not_register_target(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=False, poll_interval_seconds=30)

        assert monitor.watch(_target(), now=0) is False
        assert monitor.poll_due(now=100) == []

    def test_user_owned_current_branch_is_not_registered(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)

        assert monitor.watch(
            _target(created_by_hve=False, branch="feature/user-owned"),
            now=0,
        ) is False
        assert monitor.poll_due(now=100) == []

    @pytest.mark.parametrize("bad_number", [None, True, 0, -1, "41"])
    def test_invalid_target_number_is_not_registered(self, bad_number) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)

        assert monitor.watch(_target(pr_number=bad_number), now=0) is False
        assert monitor.poll_due(now=100) == []

    def test_close_stops_new_targets_and_due_requests(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=0)

        monitor.close()

        assert monitor.watch(_target(pr_number=42), now=1) is False
        assert monitor.poll_due(now=100) == []

    def test_inflight_completion_after_close_does_not_emit_cleanup(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=0)
        request = monitor.poll_due(now=0)[0]
        monitor.close()

        cleanup = monitor.complete(
            request,
            pull_request=_pull_request(state="closed", merged=True),
            now=1,
        )

        assert cleanup is None

    def test_poll_interval_must_be_positive(self) -> None:
        _target_type, monitor_type = _types()
        with pytest.raises(ValueError):
            monitor_type(enabled=True, poll_interval_seconds=0)

    def test_shutdown_closes_state_and_waits_active_workers_with_bound(self) -> None:
        _target_type, monitor_type = _types()
        monitor = monitor_type(enabled=True, poll_interval_seconds=30)
        monitor.watch(_target(), now=0)
        worker = Mock()
        monitor._workers.append(worker)

        monitor.shutdown(timeout_ms=321)

        worker.wait.assert_called_once_with(321)
        assert monitor._workers == []
        assert monitor.poll_due(now=100) == []

    def test_monitor_module_has_no_list_or_remote_delete_dependency(self) -> None:
        _target_type, monitor_type = _types()
        module = importlib.import_module(monitor_type.__module__)
        source = inspect.getsource(module)

        assert "GitHubWorker" in source
        assert "github_service.get_pull_request" in source
        assert "list_pull_requests" not in source
        assert "delete_branch_ref" not in source
        assert "_git_delete_remote_branch" not in source
        assert "git push origin --delete" not in source
        assert "git branch -D" not in source
        assert "subprocess" not in source
