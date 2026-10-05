"""FR-MCPLOG-01 / 02: orchestrator から MCP 通信ログを生成・結線・終了する。

知識探索セッション（FR-KD-03）の MCP イベントも同じ記録器へ渡す。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hve import mcp_io_log as mio
from hve import orchestrator
from hve.config import SDKConfig
from hve.console import Console

_ORCHESTRATOR_SOURCE = Path(orchestrator.__file__)

def _function_sources() -> dict:
    source = _ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return result


@pytest.fixture(autouse=True)
def _parent_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)


class TestAttachMcpIoLogging:
    def test_returns_logger_and_attaches_to_console(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False, quiet=False)
        logger = orchestrator._attach_mcp_io_logging(console, SDKConfig())

        assert logger is not None
        console.mcp_tool_request("azure", "t", tool_call_id="c1", arguments={"a": 1})
        logger.close()
        assert (tmp_path / "mcp-azure.log").is_file()

    def test_returns_none_without_work_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HVE_WORK_ROOT", raising=False)
        console = Console(verbose=False, quiet=False)
        assert orchestrator._attach_mcp_io_logging(console, SDKConfig()) is None

    def test_returns_none_for_dry_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False, quiet=False)
        assert orchestrator._attach_mcp_io_logging(console, SDKConfig(dry_run=True)) is None

    def test_warnings_are_routed_to_console(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False, quiet=False)
        seen: list = []
        monkeypatch.setattr(console, "warning", seen.append)

        logger = orchestrator._attach_mcp_io_logging(console, SDKConfig())
        assert logger is not None
        logger._max_bytes = 1
        console.mcp_tool_request("workiq", "ask", tool_call_id="c1", arguments={"q": "本文"})
        logger.close()
        assert seen and "MCP 通信ログ" in seen[0]


class TestRunWorkflowLifecycle:
    """FR-MCPLOG-02: run_workflow が生成と後始末を持つ。"""

    def test_run_workflow_attaches_and_closes(self) -> None:
        source = _function_sources()["_run_workflow_body"]
        assert "_attach_mcp_io_logging(" in source
        assert "_atexit.register(_mcp_io_logger.close)" in source
        assert "_mcp_io_logger.close()" in source


class TestKnowledgeDiscoverySessionWiring:
    """FR-MCPLOG-01 / FR-KD-03: StepRunner を経由しない知識探索セッションにも結線する。"""

    def test_discovery_session_events_reach_the_io_logger(self) -> None:
        source = _function_sources()["_run_orchestrator_knowledge_discovery"]
        assert 'logger.handle_event(event, step_id="orchestrator")' in source
        assert "event_sink=_sink" in source
        assert "attach_mcp_io_event_logger(" not in source

    def test_workiq_specific_session_helpers_are_removed(self) -> None:
        sources = _function_sources()
        for name in (
            "_create_orchestrator_workiq_session",
            "_run_akm_workiq_verification",
            "_run_akm_workiq_ingest",
            "_run_ard_workiq_usecase",
        ):
            assert name not in sources


class TestSharedHelperIsUsed:
    def test_orchestrator_uses_the_shared_attach_helper(self) -> None:
        assert hasattr(mio, "attach_mcp_io_event_logger")
        source = _ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")
        assert "from .mcp_io_log import" in source or "from mcp_io_log import" in source
