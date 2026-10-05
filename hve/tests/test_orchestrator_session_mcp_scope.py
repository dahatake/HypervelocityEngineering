"""FR-CLI-76 (v2.51): orchestrator が生成するセッションの MCP 自動探索を停止する契約。

[hve/orchestrator.py](hve/orchestrator.py) の `_create_session_with_auto_reasoning_fallback` は
[hve/runner.py](hve/runner.py) の同名関数と別実装で、リポジトリ宣言の読み取りを行わず
`enable_config_discovery` を常に `True` としていた。その結果、ARD の `target_business` 生成・
Fleet wave 親・Code Review Agent の各セッションが、Work IQ 設定の有効・無効に関わらず
利用者グローバル設定およびプラグイン由来の MCP サーバ（実測環境では `workiq`）を
自動探索で取り込み得た。
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from inspect import signature
from pathlib import Path
from typing import Any
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec, patch

import pytest

from hve.orchestrator import _create_session_with_auto_reasoning_fallback
from hve import orchestrator, runner
from hve.config import SDKConfig
from hve.console import Console

_DECLARED_SERVERS = {
    "azure": {
        "command": "npx",
        "args": ["-y", "@azure/mcp@latest", "server", "start"],
        "tools": ["*"],
    },
    "microsoft-learn": {
        "type": "http",
        "url": "https://learn.microsoft.com/api/mcp",
        "tools": ["*"],
    },
}

_REMOVED_WORKIQ_SESSION_FUNCTIONS = (
    "_run_akm_workiq_verification",
    "_run_akm_workiq_ingest",
    "_run_ard_workiq_usecase",
    "_create_orchestrator_workiq_session",
)


class _RecordingClient:
    def __init__(self) -> None:
        self.create_session_kwargs: list[dict[str, Any]] = []

    async def create_session(self, **kwargs: Any) -> object:
        self.create_session_kwargs.append(kwargs)
        return object()


def _write_mcp_config(root: Path, payload: str | None) -> None:
    skill_dir = root / ".github" / "skills" / "demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill.\n---\n# demo\n", encoding="utf-8"
    )
    if payload is not None:
        (root / ".github" / ".mcp.json").write_text(payload, encoding="utf-8")


def _create(opts: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    client = _RecordingClient()
    asyncio.run(_create_session_with_auto_reasoning_fallback(client, opts, **kwargs))
    return client.create_session_kwargs[-1]


@pytest.fixture
def declared_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _write_mcp_config(tmp_path, json.dumps({"mcpServers": _DECLARED_SERVERS}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_local_sessions_use_shared_resource_routing_instead_of_declared_injection(
    declared_repo: Path,
) -> None:
    """generic local session は `.mcp.json` を複製せず shared routing helper を使う。"""
    client = _RecordingClient()
    routed_session = object()
    snapshot = object()
    policy = object()
    create_routed_session = AsyncMock(return_value=routed_session)

    with patch.object(
        orchestrator,
        "discover_sdk_resources",
        return_value=snapshot,
    ) as discover, patch.object(
        orchestrator,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: policy),
    ), patch.object(
        orchestrator,
        "create_routed_session",
        new=create_routed_session,
    ):
        result = asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True},
                config=SDKConfig(),
                workflow_id="ard",
            )
        )

    assert result is routed_session
    assert client.create_session_kwargs == []
    discover.assert_called_once()
    create_routed_session.assert_awaited_once()
    kwargs = create_routed_session.await_args.kwargs
    assert kwargs["workflow_id"] == "ard"
    assert "mcp_servers" not in kwargs["session_options"]
    assert kwargs["session_options"]["enable_config_discovery"] is True


def test_local_helper_routes_even_when_caller_preseeds_disabled_mcp_servers(
    declared_repo: Path,
) -> None:
    client = _RecordingClient()
    create_routed_session = AsyncMock(return_value=object())

    with patch.object(
        orchestrator,
        "discover_sdk_resources",
        return_value=object(),
    ) as discover, patch.object(
        orchestrator,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch.object(
        orchestrator,
        "create_routed_session",
        new=create_routed_session,
    ):
        asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True, "disabled_mcp_servers": ["azure"]},
                config=SDKConfig(),
                workflow_id="ard",
            )
        )

    assert client.create_session_kwargs == []
    discover.assert_called_once()
    create_routed_session.assert_awaited_once()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        json.dumps({"mcpServers": {}}),
        json.dumps({"mcpServers": []}),
        json.dumps({"servers": _DECLARED_SERVERS}),
        "{ not json",
    ],
)
def test_missing_declaration_keeps_discovery_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str | None
) -> None:
    """宣言が無い / 空 / 壊れている場合は従来どおり自動探索を残す（回帰回避）。"""
    _write_mcp_config(tmp_path, payload)
    monkeypatch.chdir(tmp_path)

    kwargs = _create({"streaming": True})

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


def test_repository_mcp_contents_do_not_leak_into_shared_routing_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generic routed session は repository MCP config の raw contents を複製しない。"""
    _write_mcp_config(
        tmp_path,
        json.dumps(
            {
                "mcpServers": {
                    **_DECLARED_SERVERS,
                    "workiq": {"type": "http"},
                    "workiq-preview": {"type": "http"},
                }
            }
        ),
    )
    monkeypatch.chdir(tmp_path)

    client = _RecordingClient()
    create_routed_session = AsyncMock(return_value=object())
    with patch.object(
        orchestrator,
        "discover_sdk_resources",
        return_value=object(),
    ), patch.object(
        orchestrator,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch.object(
        orchestrator,
        "create_routed_session",
        new=create_routed_session,
    ):
        asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True},
                config=SDKConfig(),
                workflow_id="ard",
            )
        )

    kwargs = create_routed_session.await_args.kwargs
    assert "mcp_servers" not in kwargs["session_options"]


def test_azure_free_workflow_filter_is_applied(declared_repo: Path) -> None:
    """Azure-free workflow でも filtering は shared routing へ委譲する。"""
    client = _RecordingClient()
    create_routed_session = AsyncMock(return_value=object())
    with patch.object(
        orchestrator,
        "discover_sdk_resources",
        return_value=object(),
    ), patch.object(
        orchestrator,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch.object(
        orchestrator,
        "create_routed_session",
        new=create_routed_session,
    ):
        asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True},
                config=SDKConfig(),
                workflow_id="ard",
            )
        )

    kwargs = create_routed_session.await_args.kwargs
    assert kwargs["workflow_id"] == "ard"
    assert "mcp_servers" not in kwargs["session_options"]


def test_unknown_workflow_id_keeps_all_declared_servers(declared_repo: Path) -> None:
    """Workflow ID 不明時は分類を推測せず routed helper を使わない。"""
    kwargs = _create({"streaming": True}, workflow_id=None)

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


def test_explicit_caller_values_are_not_overridden(declared_repo: Path) -> None:
    """呼び出し側が明示した `mcp_servers` / `enable_config_discovery` を上書きしない。"""
    explicit = {"only-this": {"command": "noop"}}

    kwargs = _create({"streaming": True, "mcp_servers": explicit})

    assert kwargs["mcp_servers"] == explicit
    assert kwargs["enable_config_discovery"] is True


def _orchestrator_module_ast() -> ast.Module:
    source = (Path(__file__).resolve().parents[1] / "orchestrator.py").read_text(encoding="utf-8")
    return ast.parse(source)


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_reduction_is_implemented_once() -> None:
    """FR-MAINT-07: 縮約の判定は runner の単一実装に限る（orchestrator で再実装しない）。"""
    called = _called_names(_orchestrator_module_ast())

    assert "_read_repository_mcp_config" not in called
    assert "_filter_mcp_servers_for_session" not in called


def test_dead_workiq_prefetch_surface_is_removed() -> None:
    functions = {
        node.name
        for node in ast.walk(_orchestrator_module_ast())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    from hve import workiq

    assert "_prefetch_workiq" not in functions
    assert "_prefetch_workiq_detailed" not in functions
    for name in _REMOVED_WORKIQ_SESSION_FUNCTIONS:
        assert name not in functions
    assert not hasattr(workiq, "WorkIQPrefetchResult")


class _OfflineWorkIQClient:
    def __init__(self) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.force_stop = AsyncMock()
        self.create_session = AsyncMock()


@pytest.fixture
def offline_workiq(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """T14: SDK起動・認証・runtime検査を必ずfake境界で遮断する。"""
    permission_module = ModuleType("copilot.session")
    setattr(permission_module, "PermissionHandler", SimpleNamespace(approve_all=Mock()))
    monkeypatch.setitem(sys.modules, "copilot.session", permission_module)
    monkeypatch.setattr(SDKConfig, "resolve_token", Mock(return_value=""))

    client = _OfflineWorkIQClient()
    session = SimpleNamespace(disconnect=AsyncMock(), on=Mock())
    client.create_session.return_value = session
    create = AsyncMock(return_value=session)
    factory = Mock(return_value=client)
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", factory)
    monkeypatch.setattr(orchestrator, "_create_session_with_auto_reasoning_fallback", create)
    return SimpleNamespace(
        client=client,
        session=session,
        create=create,
        factory=factory,
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )


def _patch_workiq_bounded_cleanup(
    monkeypatch: pytest.MonkeyPatch, *, run_helpers: bool = False
) -> SimpleNamespace:
    """既存定義と既存import aliasだけをpatchし、未定義属性は追加しない。"""
    def replace(name: str) -> Any:
        original = getattr(runner, name)
        replacement = create_autospec(
            original,
            spec_set=True,
            return_value=None,
            side_effect=original if run_helpers else None,
        )
        for alias, value in tuple(vars(orchestrator).items()):
            if value is original:
                monkeypatch.setattr(orchestrator, alias, replacement)
        monkeypatch.setattr(runner, name, replacement)
        return replacement

    return SimpleNamespace(
        disconnect=replace("_disconnect_session_bounded"),
        stop=replace("_stop_client_bounded"),
    )


def _assert_bounded_cleanup_target(helper: Any, parameter: str, target: object) -> None:
    helper.assert_awaited_once()
    call = helper.await_args
    arguments = signature(helper).bind(*call.args, **call.kwargs).arguments
    assert arguments[parameter] is target


def test_shared_workiq_close_bounds_hanging_client_stop(
    offline_workiq: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """既存bounded helperをstrict mockにし、直stopのhangだけをwatchdogで捕捉する。"""
    cleanup = _patch_workiq_bounded_cleanup(monkeypatch)

    async def hang() -> None:
        await asyncio.Future()

    offline_workiq.client.stop.side_effect = hang

    async def close() -> None:
        try:
            await asyncio.wait_for(
                orchestrator._close_orchestrator_session(
                    offline_workiq.client, offline_workiq.session
                ),
                timeout=1.0,
            )
        except TimeoutError:
            pytest.fail("client.stop() hung instead of using the existing bounded helper")

    asyncio.run(close())

    _assert_bounded_cleanup_target(cleanup.disconnect, "session", offline_workiq.session)
    _assert_bounded_cleanup_target(cleanup.stop, "client", offline_workiq.client)
    offline_workiq.client.stop.assert_not_awaited()


def test_shared_workiq_close_without_owner_only_disconnects_session(
    offline_workiq: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """clientを所有しないcloseはsessionだけを閉じ、client停止を行わない。"""
    cleanup = _patch_workiq_bounded_cleanup(monkeypatch)

    asyncio.run(orchestrator._close_orchestrator_session(None, offline_workiq.session))

    _assert_bounded_cleanup_target(cleanup.disconnect, "session", offline_workiq.session)
    cleanup.stop.assert_not_awaited()
    offline_workiq.client.stop.assert_not_awaited()


def test_shared_workiq_close_masks_cleanup_failures(
    offline_workiq: SimpleNamespace,
) -> None:
    """NFR-SEC-01: reused bounded cleanup masks both stop failure diagnostics."""
    console = Mock(spec=Console)
    dummy_secret = "T14SECRET"
    offline_workiq.client.stop.side_effect = RuntimeError(
        f"Authorization: Bearer {dummy_secret}"
    )
    offline_workiq.client.force_stop.side_effect = RuntimeError(
        f"Authorization: Bearer {dummy_secret}"
    )

    asyncio.run(orchestrator._close_orchestrator_session(
        offline_workiq.client, offline_workiq.session, console=console,
    ))

    offline_workiq.session.disconnect.assert_awaited_once()
    offline_workiq.client.stop.assert_awaited_once()
    offline_workiq.client.force_stop.assert_awaited_once()
    assert console.warning.call_count == 2, "both cleanup failures must remain observable"
    for call in console.warning.call_args_list:
        assert dummy_secret not in str(call)
    for method in ("stop", "force_stop"):
        console.warning.assert_any_call(
            f"[cleanup] client.{method}() failed: Authorization: Bearer [REDACTED]"
        )
