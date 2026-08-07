"""FR-RTO-05: producer 側の観測イベント欠落を防ぐ（runner）。

RED 先行。`permission.requested` は `Console.stats_event` への引数衝突により
イベントが一度も発火していない。ツール失敗も観測イベントを持たない。
"""

from __future__ import annotations

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


class _FakeEventType:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeEventData:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeEvent:
    def __init__(self, etype: str, data=None) -> None:
        self.type = _FakeEventType(etype)
        self.data = data


@pytest.fixture()
def runner(monkeypatch: pytest.MonkeyPatch) -> StepRunner:
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
    console = Console(verbose=False, quiet=False)
    step_runner = StepRunner(config=SDKConfig(dry_run=True), console=console)
    step_runner._current_step_id = "1.1"
    return step_runner


def _totals(step_runner: StepRunner):
    return step_runner.console.runtime_metrics().totals()


class TestPermissionObservability:
    """permission.requested の観測イベントが実際に発火する。"""

    def test_permission_requested_is_counted(self, runner: StepRunner) -> None:
        event = _FakeEvent(
            "permission.requested",
            _FakeEventData(permission_request=_FakeEventData(kind="write")),
        )
        runner._handle_session_event(event)

        assert _totals(runner).permission_count == 1

    def test_permission_kind_is_reported_under_dedicated_key(self, runner: StepRunner) -> None:
        seen: list = []
        original = runner.console.stats_event

        def _capture(kind: str, step_id: str = "", **fields):
            seen.append((kind, fields))
            return original(kind, step_id, **fields)

        runner.console.stats_event = _capture  # type: ignore[method-assign]
        runner._handle_session_event(
            _FakeEvent(
                "permission.requested",
                _FakeEventData(permission_request=_FakeEventData(kind="write")),
            )
        )

        payloads = [fields for kind, fields in seen if kind == "permission_count"]
        assert payloads, "permission_count イベントが発火していない"
        assert payloads[0].get("permission_kind") == "write"
        assert "kind" not in payloads[0]


class TestToolFailureObservability:
    """ツール失敗も観測イベントとして数える。"""

    def test_tool_failure_is_counted(self, runner: StepRunner) -> None:
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(tool_name="bash", arguments={"command": "x"}, tool_call_id="c1"),
            )
        )
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(success=False, error=_FakeEventData(message="boom"), tool_call_id="c1"),
            )
        )

        totals = _totals(runner)
        assert totals.tool_failures == 1
        assert totals.tool_successes == 0

    def test_tool_success_is_counted(self, runner: StepRunner) -> None:
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(tool_name="view", arguments={}, tool_call_id="c2"),
            )
        )
        runner._handle_session_event(
            _FakeEvent("tool.execution_complete", _FakeEventData(success=True, tool_call_id="c2"))
        )

        totals = _totals(runner)
        assert totals.tool_successes == 1
        assert totals.tool_failures == 0

    def test_tool_failure_event_does_not_carry_arguments(self, runner: StepRunner) -> None:
        seen: list = []
        original = runner.console.stats_event

        def _capture(kind: str, step_id: str = "", **fields):
            seen.append((kind, fields))
            return original(kind, step_id, **fields)

        runner.console.stats_event = _capture  # type: ignore[method-assign]
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(tool_name="bash", arguments={"command": "secret"}, tool_call_id="c3"),
            )
        )
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(success=False, error=_FakeEventData(message="boom"), tool_call_id="c3"),
            )
        )

        failures = [fields for kind, fields in seen if kind == "tool_result" and not fields.get("success")]
        assert failures, "失敗時の tool_result イベントが発火していない"
        assert "arguments" not in failures[0]
        assert "error" not in failures[0]
