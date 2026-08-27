"""FR-GUI-37: MainWindow の cleanup monitor 結線契約。"""

from __future__ import annotations

import inspect
import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


def _source(name: str) -> str:
    from hve.gui import main_window

    return inspect.getsource(getattr(main_window.MainWindow, name))


def _target_event(**fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": "github_target",
        "step": "",
        "repo": "owner/repo",
        "pr_number": 41,
        "branch": "copilot-sdk/aas-1234abcd",
        "base_branch": "main",
        "created_by_hve": True,
        "delete_local_merged_branch": True,
    }
    payload.update(fields)
    return payload


class _Stub:
    """MainWindow のメソッドだけを借りる軽量スタブ。"""

    def __init__(self) -> None:
        from hve.gui import main_window

        self.polled: List[str] = []
        for name in ("_branch_cleanup_monitor", "_watch_branch_cleanup_target"):
            setattr(
                self,
                name,
                getattr(main_window.MainWindow, name).__get__(self),
            )
        self._BRANCH_CLEANUP_POLL_SECONDS = main_window.MainWindow._BRANCH_CLEANUP_POLL_SECONDS

    def _poll_branch_cleanup(self) -> None:
        self.polled.append("polled")


@pytest.fixture
def stub(monkeypatch):
    from hve.gui import settings_store

    monkeypatch.setattr(settings_store, "get_option", lambda key, default=None: True)
    return _Stub()


class TestTargetRegistration:
    def test_hve_created_target_is_registered(self, stub) -> None:
        stub._watch_branch_cleanup_target(_target_event())
        assert stub.polled == ["polled"]

    def test_user_owned_branch_is_not_registered(self, stub) -> None:
        stub._watch_branch_cleanup_target(_target_event(created_by_hve=False))
        assert stub.polled == []

    def test_disabled_delete_option_is_not_registered(self, stub) -> None:
        stub._watch_branch_cleanup_target(_target_event(delete_local_merged_branch=False))
        assert stub.polled == []

    def test_other_kinds_are_ignored(self, stub) -> None:
        stub._watch_branch_cleanup_target({"kind": "step_status", "step": "1"})
        assert stub.polled == []

    @pytest.mark.parametrize("missing", ["repo", "branch", "base_branch"])
    def test_incomplete_target_is_not_registered(self, stub, missing) -> None:
        payload = _target_event()
        payload.pop(missing)
        stub._watch_branch_cleanup_target(payload)
        assert stub.polled == []

    def test_duplicate_target_does_not_repoll(self, stub) -> None:
        stub._watch_branch_cleanup_target(_target_event())
        stub._watch_branch_cleanup_target(_target_event())
        assert stub.polled == ["polled"]

    def test_monitor_is_disabled_when_option_is_off(self, monkeypatch) -> None:
        from hve.gui import settings_store

        monkeypatch.setattr(settings_store, "get_option", lambda key, default=None: False)
        stub = _Stub()
        assert stub._branch_cleanup_monitor() is None
        stub._watch_branch_cleanup_target(_target_event())
        assert stub.polled == []


class TestWorkerBoundary:
    """FR-GUI-37: GUI thread で API / git を実行しない。"""

    def test_status_is_fetched_through_worker(self) -> None:
        source = _source("_poll_branch_cleanup")
        assert "GitHubWorker(" in source
        assert "build_status_task(request)" in source
        assert "worker.start()" in source

    def test_cleanup_is_delegated_to_shared_core_via_worker(self) -> None:
        source = _source("_on_branch_cleanup_status")
        assert "GitHubWorker(cleanup.run" in source
        assert "subprocess" not in source
        assert '"git"' not in source
        assert "git checkout" not in source
        assert "branch -D" not in source

    def test_no_list_api_is_used(self) -> None:
        for name in ("_poll_branch_cleanup", "_on_branch_cleanup_status"):
            source = _source(name)
            assert "list_pull_requests" not in source
            assert "list_issues" not in source

    def test_no_remote_branch_deletion(self) -> None:
        for name in ("_poll_branch_cleanup", "_on_branch_cleanup_status"):
            source = _source(name)
            assert "delete_branch" not in source
            assert "--delete" not in source


class TestShutdown:
    def test_close_shuts_down_monitor_with_bound(self) -> None:
        source = _source("_close_branch_cleanup_monitor")
        assert "shutdown(timeout_ms=" in source

    def test_close_event_stops_the_monitor(self) -> None:
        source = _source("closeEvent")
        assert "_close_branch_cleanup_monitor()" in source
