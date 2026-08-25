"""FR-MCPLOG-01: runner の SDK イベント分岐から MCP 通信ログへ流す。

RED 先行。`StepRunner._handle_session_event` は本テスト作成時点で MCP 入出力を
ログへ記録しない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve import mcp_io_log as mio
from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


class _FakeEventType:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeData:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeEvent:
    def __init__(self, etype: str, data=None) -> None:
        self.type = _FakeEventType(etype)
        self.data = data


@pytest.fixture()
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
    console = Console(verbose=False, quiet=False)
    logger = mio.McpIoLogger(tmp_path)
    console.attach_mcp_io_logger(logger)
    runner = StepRunner(config=SDKConfig(dry_run=True), console=console)
    runner._current_step_id = "1.1"
    return runner, logger


def _read(tmp_path: Path, server: str) -> str:
    return (tmp_path / f"mcp-{server}.log").read_text(encoding="utf-8")


class TestRunnerMcpToolRecords:
    def test_mcp_tool_round_trip_is_recorded(self, tmp_path: Path, wired) -> None:
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(
                    tool_name="ask",
                    mcp_tool_name="ask",
                    mcp_server_name="_hve_workiq",
                    arguments={"query": "検索したい内容"},
                    tool_call_id="c1",
                ),
            )
        )
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_complete",
                _FakeData(
                    success=True,
                    tool_call_id="c1",
                    result=_FakeData(content="STATUS: FOUND"),
                ),
            )
        )
        logger.close()

        text = _read(tmp_path, "_hve_workiq")
        assert "検索したい内容" in text
        assert "STATUS: FOUND" in text
        assert "step=1.1" in text

    def test_failed_mcp_tool_records_error(self, tmp_path: Path, wired) -> None:
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(
                    tool_name="azmcp_group_list",
                    mcp_tool_name="azmcp_group_list",
                    mcp_server_name="azure",
                    arguments={"subscription": "sub-1"},
                    tool_call_id="c9",
                ),
            )
        )
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_complete",
                _FakeData(
                    success=False,
                    tool_call_id="c9",
                    error=_FakeData(message="RBAC 403"),
                ),
            )
        )
        logger.close()

        text = _read(tmp_path, "azure")
        assert "success=false" in text
        assert "RBAC 403" in text

    def test_builtin_tool_without_mcp_server_is_not_recorded(
        self, tmp_path: Path, wired
    ) -> None:
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(tool_name="view", arguments={"path": "a.md"}, tool_call_id="c2"),
            )
        )
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_complete",
                _FakeData(success=True, tool_call_id="c2", result=_FakeData(content="x")),
            )
        )
        logger.close()
        assert list(tmp_path.glob("mcp-*.log")) == []

    def test_arguments_are_not_truncated(self, tmp_path: Path, wired) -> None:
        runner, logger = wired
        payload = "う" * 20_000
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(
                    tool_name="ask",
                    mcp_tool_name="ask",
                    mcp_server_name="_hve_workiq",
                    arguments={"query": payload},
                    tool_call_id="c3",
                ),
            )
        )
        logger.close()
        assert payload in _read(tmp_path, "_hve_workiq")

    @pytest.mark.parametrize("tool", ["task", "report_intent"])
    def test_mcp_tool_sharing_a_builtin_name_is_still_recorded(
        self, tmp_path: Path, wired, tool: str
    ) -> None:
        """組み込みツールと同名の MCP ツールでも記録を落とさない。"""
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(
                    tool_name=tool,
                    mcp_tool_name=tool,
                    mcp_server_name="acme",
                    arguments={"intent": "調査中"},
                    tool_call_id="c4",
                ),
            )
        )
        logger.close()
        assert "調査中" in _read(tmp_path, "acme")


class TestRunnerMcpServerStatusRecords:
    def test_servers_loaded_is_recorded(self, tmp_path: Path, wired) -> None:
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_servers_loaded",
                _FakeData(
                    servers=[
                        _FakeData(
                            name="azure",
                            status=_FakeEventType("connected"),
                            error=None,
                            plugin_name=None,
                            transport=_FakeEventType("stdio"),
                            source=_FakeEventType("workspace"),
                        )
                    ]
                ),
            )
        )
        logger.close()

        header = _read(tmp_path, "azure").splitlines()[0]
        assert "| mcp_server_status |" in header
        assert "status=connected" in header
        assert "transport=stdio" in header

    def test_status_changed_is_recorded(self, tmp_path: Path, wired) -> None:
        runner, logger = wired
        runner._handle_session_event(
            _FakeEvent(
                "session.mcp_server_status_changed",
                _FakeData(
                    server_name="microsoft-learn",
                    status=_FakeEventType("failed"),
                    error="handshake timeout",
                ),
            )
        )
        logger.close()

        text = _read(tmp_path, "microsoft-learn")
        assert "status=failed" in text
        assert "handshake timeout" in text


class TestRunnerWithoutLogger:
    def test_events_are_handled_without_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
        monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
        runner = StepRunner(
            config=SDKConfig(dry_run=True), console=Console(verbose=False, quiet=False)
        )
        runner._current_step_id = "1.1"
        runner._handle_session_event(
            _FakeEvent(
                "tool.execution_start",
                _FakeData(
                    tool_name="ask",
                    mcp_server_name="_hve_workiq",
                    arguments={"query": "x"},
                    tool_call_id="c1",
                ),
            )
        )
