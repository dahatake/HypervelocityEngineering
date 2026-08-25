"""`session.mcp_servers_loaded` の接続失敗警告の文言契約（F-09）。

実 run で `MCP サーバー 'workiq' 接続失敗 (status=failed): ... MCP error -32001` が
欠陥として計上されたが、実際には Work IQ は best-effort（FR-QA-03 / FR-QA-06）で
実行は継続する。Work IQ 系サーバーに限って非致命であることを警告文へ明示する。

Work IQ 以外（`azure` 等）へ同じ注記を付けてはならない。ASDW DataDeploy / Foundry
経路は fail-closed ガード（FR-TS-03）を持ち、接続失敗が無害とは限らないため。
"""

from __future__ import annotations

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.workiq import WORKIQ_MCP_SERVER_NAMES

NON_FATAL_MARKER = "実行は継続します"


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
def runner_and_warnings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
    console = Console(verbose=False, quiet=False)
    warnings: list[str] = []
    console.warning = lambda msg: warnings.append(msg)  # type: ignore[method-assign]
    step_runner = StepRunner(config=SDKConfig(dry_run=True), console=console)
    step_runner._current_step_id = "1.1"
    return step_runner, warnings


def _failed_event(name: str, error: str | None = None) -> _FakeEvent:
    return _FakeEvent(
        "session.mcp_servers_loaded",
        _FakeEventData(
            servers=[_FakeEventData(name=name, status="failed", error=error)]
        ),
    )


class TestWorkIQConnectionWarningIsMarkedNonFatal:
    """Work IQ 系サーバーの接続失敗は非致命であることを警告文へ明示する。"""

    @pytest.mark.parametrize("server_name", sorted(WORKIQ_MCP_SERVER_NAMES))
    def test_every_workiq_alias_is_marked_non_fatal(
        self, runner_and_warnings, server_name: str
    ) -> None:
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _failed_event(server_name, "MCP error -32001: Request timed out")
        )

        assert len(warnings) == 1
        assert NON_FATAL_MARKER in warnings[0], warnings[0]

    def test_original_error_text_is_preserved(self, runner_and_warnings) -> None:
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _failed_event("_hve_workiq", "MCP error -32001: Request timed out")
        )

        assert "MCP error -32001: Request timed out" in warnings[0]
        assert "_hve_workiq" in warnings[0]

    def test_marker_is_applied_per_server_not_per_event(self, runner_and_warnings) -> None:
        """実 run と同じく `workiq` と `azure` が同一イベントに同居する場合の判定。

        `azure` は fail-closed ガードを持つため無害と書いてはならない。
        """
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_servers_loaded",
                _FakeEventData(
                    servers=[
                        _FakeEventData(
                            name="workiq",
                            status="failed",
                            error="MCP error -32001: Request timed out",
                        ),
                        _FakeEventData(
                            name="azure",
                            status="failed",
                            error="initialize handshake did not complete within 60000 ms",
                        ),
                    ]
                ),
            )
        )

        assert len(warnings) == 2
        workiq_warning = next(w for w in warnings if "workiq" in w)
        azure_warning = next(w for w in warnings if "azure" in w)
        assert NON_FATAL_MARKER in workiq_warning, workiq_warning
        assert NON_FATAL_MARKER not in azure_warning, azure_warning

    def test_needs_auth_status_is_also_marked(self, runner_and_warnings) -> None:
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_servers_loaded",
                _FakeEventData(
                    servers=[
                        _FakeEventData(name="workiq", status="needs-auth", error=None)
                    ]
                ),
            )
        )

        assert len(warnings) == 1
        assert NON_FATAL_MARKER in warnings[0], warnings[0]


class TestStatusChangedWarningIsMarkedNonFatal:
    """`session.mcp_server_status_changed` 側も同じ非致命の注記を出す。

    判定対象は HVE 自身が注入する `_hve_workiq` のみ。他の Work IQ 別名を
    warning へ格上げすると、従来 `console.event` だったものが GUI の
    「実行中の課題」へ流れて警告ノイズが増えるため広げない。
    """

    def test_hve_workiq_status_change_is_marked_non_fatal(self, runner_and_warnings) -> None:
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_server_status_changed",
                _FakeEventData(server_name="_hve_workiq", status="failed"),
            )
        )

        assert len(warnings) == 1
        assert NON_FATAL_MARKER in warnings[0], warnings[0]

    def test_other_workiq_alias_stays_an_event_not_a_warning(
        self, runner_and_warnings
    ) -> None:
        runner, warnings = runner_and_warnings

        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_server_status_changed",
                _FakeEventData(server_name="workiq", status="failed"),
            )
        )

        assert warnings == []
