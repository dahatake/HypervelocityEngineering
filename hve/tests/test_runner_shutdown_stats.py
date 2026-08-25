"""FIX-1: `session.shutdown` の `code_changes.files_modified` は SDK 上 `list[str]`。

SDK (`copilot/generated/session_events.py` の `ShutdownCodeChanges`) は
`files_modified: list[str]` を返す。これを `int()` に渡すと `TypeError` となり、
`Console.shutdown_stats` の出力と直後の `premium_requests` stats_event が
まとめて失われる（GUI の Premium Requests 累積が常に 0 になる）。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


class _FakeEventType:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeEventData:
    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeEvent:
    def __init__(self, etype: str, data: Any = None) -> None:
        self.type = _FakeEventType(etype)
        self.data = data


def _shutdown_event(
    code_changes: Any,
    *,
    premium_requests: int = 0,
    api_duration_ms: int = 1234,
) -> _FakeEvent:
    return _FakeEvent(
        "session.shutdown",
        _FakeEventData(
            code_changes=code_changes,
            total_premium_requests=premium_requests,
            total_api_duration_ms=api_duration_ms,
        ),
    )


@pytest.fixture()
def runner(monkeypatch: pytest.MonkeyPatch) -> StepRunner:
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
    console = Console(verbose=False, quiet=False)
    step_runner = StepRunner(config=SDKConfig(dry_run=True), console=console)
    step_runner._current_step_id = "1.1"
    return step_runner


def _capture_shutdown_stats(step_runner: StepRunner) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []

    def _capture(
        step_id: str,
        lines_added: int,
        lines_removed: int,
        files_modified: int,
        premium_requests: int,
        api_duration_ms: int,
    ) -> None:
        calls.append({
            "step_id": step_id,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "files_modified": files_modified,
            "premium_requests": premium_requests,
            "api_duration_ms": api_duration_ms,
        })

    step_runner.console.shutdown_stats = _capture  # type: ignore[method-assign]
    return calls


def _capture_stats_events(step_runner: StepRunner) -> List[tuple]:
    seen: List[tuple] = []
    original = step_runner.console.stats_event

    def _capture(kind: str, step_id: str = "", **fields: Any):
        seen.append((kind, fields))
        return original(kind, step_id, **fields)

    step_runner.console.stats_event = _capture  # type: ignore[method-assign]
    return seen


class TestShutdownFilesModified:
    """SDK の `list[str]` を件数として扱い、例外で後続処理を落とさない。"""

    def test_list_files_modified_does_not_raise(self, runner: StepRunner) -> None:
        event = _shutdown_event(
            _FakeEventData(
                files_modified=["a.py", "b.py", "c.py"],
                lines_added=120,
                lines_removed=15,
            )
        )

        runner._handle_session_event(event)

    def test_list_files_modified_is_reported_as_count(self, runner: StepRunner) -> None:
        calls = _capture_shutdown_stats(runner)
        runner._handle_session_event(
            _shutdown_event(
                _FakeEventData(
                    files_modified=["a.py", "b.py", "c.py"],
                    lines_added=120,
                    lines_removed=15,
                )
            )
        )

        assert calls, "shutdown_stats が呼ばれていない"
        assert calls[0]["files_modified"] == 3
        assert calls[0]["lines_added"] == 120
        assert calls[0]["lines_removed"] == 15

    def test_numeric_files_modified_is_preserved(self, runner: StepRunner) -> None:
        calls = _capture_shutdown_stats(runner)
        runner._handle_session_event(
            _shutdown_event(
                _FakeEventData(files_modified=5, lines_added=1, lines_removed=2)
            )
        )

        assert calls[0]["files_modified"] == 5

    def test_missing_code_changes_reports_zero(self, runner: StepRunner) -> None:
        calls = _capture_shutdown_stats(runner)
        runner._handle_session_event(_shutdown_event(None))

        assert calls[0]["files_modified"] == 0
        assert calls[0]["lines_added"] == 0
        assert calls[0]["lines_removed"] == 0


class TestShutdownPremiumRequestsEvent:
    """`files_modified` の型に関わらず premium_requests の stats_event が発火する。"""

    def test_premium_requests_event_is_emitted(self, runner: StepRunner) -> None:
        seen = _capture_stats_events(runner)
        runner._handle_session_event(
            _shutdown_event(
                _FakeEventData(
                    files_modified=["a.py", "b.py"],
                    lines_added=3,
                    lines_removed=4,
                ),
                premium_requests=7,
            )
        )

        payloads = [fields for kind, fields in seen if kind == "premium_requests"]
        assert payloads, "premium_requests イベントが発火していない"
        assert payloads[0].get("count") == 7

    def test_no_premium_requests_event_when_zero(self, runner: StepRunner) -> None:
        seen = _capture_stats_events(runner)
        runner._handle_session_event(
            _shutdown_event(
                _FakeEventData(files_modified=[], lines_added=0, lines_removed=0),
                premium_requests=0,
            )
        )

        assert not [fields for kind, fields in seen if kind == "premium_requests"]
