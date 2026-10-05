"""FR-TS-13: generic local session routing no longer depends on repository MCP config injection."""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import types
from pathlib import Path
from typing import Any
from unittest import mock



class _FakeSession:
    pass


class _FakeClient:
    def __init__(self) -> None:
        self.create_session_kwargs: list[dict[str, Any]] = []

    async def create_session(self, **kwargs: Any) -> _FakeSession:
        self.create_session_kwargs.append(kwargs)
        return _FakeSession()


def _function_calls(module_path: Path, function_name: str) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    targets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    assert targets, f"{function_name} が見つかりません"
    names: set[str] = set()
    for node in ast.walk(targets[0]):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _runner_source_path() -> Path:
    import hve.runner as runner

    return Path(runner.__file__)


def _orchestrator_source_path() -> Path:
    import hve.orchestrator as orchestrator

    return Path(orchestrator.__file__)


def _context_report_source_path() -> Path:
    import hve.toolsearch.context_report as context_report

    return Path(context_report.__file__)


def test_runner_local_session_uses_shared_resource_routing_runtime() -> None:
    runner = importlib.import_module("hve.runner")
    client = _FakeClient()
    routed_session = _FakeSession()
    snapshot = object()
    policy = object()
    create_routed_session = mock.AsyncMock(return_value=routed_session)
    policy_loader = mock.Mock(return_value=policy)

    with mock.patch.object(
        runner,
        "discover_sdk_resources",
        create=True,
        return_value=snapshot,
    ) as discover, mock.patch.object(
        runner,
        "ToolSearchPolicy",
        create=True,
        new=types.SimpleNamespace(load=policy_loader),
    ), mock.patch.object(
        runner,
        "create_routed_session",
        create=True,
        new=create_routed_session,
    ):
        result = asyncio.run(
            runner._create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True},
                config=runner.SDKConfig(),
                step_id="1.1",
                workflow_id="ard",
                subtask_kind="main",
            )
        )

    assert result is routed_session
    assert client.create_session_kwargs == []
    discover.assert_called_once()
    policy_loader.assert_called_once()
    create_routed_session.assert_awaited_once()
    kwargs = create_routed_session.await_args.kwargs
    assert kwargs["client"] is client
    assert kwargs["snapshot"] is snapshot
    assert kwargs["policy"] is policy
    assert kwargs["workflow_id"] == "ard"
    assert "mcp_servers" not in kwargs["session_options"]


def test_runner_local_session_helper_no_longer_calls_legacy_repository_mcp_scope() -> None:
    calls = _function_calls(
        _runner_source_path(),
        "_create_session_with_auto_reasoning_fallback",
    )

    assert "_apply_repository_mcp_scope" not in calls
    assert "_read_repository_mcp_config" not in calls
    assert "create_routed_session" in calls
    assert "discover_sdk_resources" in calls


def test_runner_local_session_helper_exposes_use_resource_routing_as_a_keyword_parameter() -> None:
    runner = importlib.import_module("hve.runner")

    signature = inspect.signature(
        runner._create_session_with_auto_reasoning_fallback
    )

    parameter = signature.parameters.get("use_resource_routing")
    assert parameter is not None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is True


def test_orchestrator_local_session_helper_no_longer_calls_legacy_repository_mcp_scope() -> None:
    calls = _function_calls(
        _orchestrator_source_path(),
        "_create_session_with_auto_reasoning_fallback",
    )

    assert "_apply_repository_mcp_scope" not in calls
    assert "_read_repository_mcp_config" not in calls
    assert "create_routed_session" in calls
    assert "discover_sdk_resources" in calls


def test_context_report_no_longer_uses_legacy_repository_mcp_config_loader() -> None:
    calls = _function_calls(_context_report_source_path(), "collect")

    assert "_read_repository_mcp_config" not in calls


def test_sdkconfig_no_longer_exposes_runtime_mcp_servers_field() -> None:
    from dataclasses import fields

    from hve.config import SDKConfig

    assert "mcp_servers" not in {field.name for field in fields(SDKConfig)}


def test_repository_pinned_mcp_config_file_has_been_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert not (repo_root / ".github" / ".mcp.json").exists()
