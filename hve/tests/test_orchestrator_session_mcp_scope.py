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
from pathlib import Path
from typing import Any

import pytest

from hve.orchestrator import _create_session_with_auto_reasoning_fallback
from hve.runner import _apply_repository_mcp_scope
from hve.workiq import WORKIQ_MCP_SERVER_NAME

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

_WORKIQ_SESSION_FUNCTIONS = (
    "_prefetch_workiq_detailed",
    "_run_akm_workiq_verification",
    "_run_akm_workiq_ingest",
    "_run_ard_workiq_usecase",
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


def test_declared_servers_are_injected_and_discovery_disabled(declared_repo: Path) -> None:
    """宣言分を明示し、自動探索を止める。"""
    kwargs = _create({"streaming": True})

    assert set(kwargs["mcp_servers"]) == set(_DECLARED_SERVERS)
    assert kwargs["enable_config_discovery"] is False


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


def test_workiq_aliases_are_dropped_from_declared_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """宣言側に Work IQ 別名があっても orchestrator セッションへは渡さない。"""
    _write_mcp_config(
        tmp_path,
        json.dumps(
            {
                "mcpServers": {
                    **_DECLARED_SERVERS,
                    "workiq": {"command": "npx", "args": ["-y", "@microsoft/workiq@latest"], "tools": ["*"]},
                    "workiq-preview": {"command": "npx", "args": ["-y", "@microsoft/workiq@preview"], "tools": ["*"]},
                }
            }
        ),
    )
    monkeypatch.chdir(tmp_path)

    kwargs = _create({"streaming": True})

    assert "workiq" not in kwargs["mcp_servers"]
    assert "workiq-preview" not in kwargs["mcp_servers"]


def test_azure_free_workflow_filter_is_applied(declared_repo: Path) -> None:
    """FR-CLI-79: Azure を利用しない Workflow では `azure` を渡さない。"""
    kwargs = _create({"streaming": True}, workflow_id="ard")

    assert "azure" not in kwargs["mcp_servers"]
    assert "microsoft-learn" in kwargs["mcp_servers"]


def test_unknown_workflow_id_keeps_all_declared_servers(declared_repo: Path) -> None:
    """Workflow ID が解決できない経路では全宣言サーバを渡す（宣言漏れ規則と同じ側）。"""
    kwargs = _create({"streaming": True}, workflow_id=None)

    assert set(kwargs["mcp_servers"]) == set(_DECLARED_SERVERS)


def test_explicit_caller_values_are_not_overridden(declared_repo: Path) -> None:
    """呼び出し側が明示した `mcp_servers` / `enable_config_discovery` を上書きしない。"""
    explicit = {"only-this": {"command": "noop"}}

    kwargs = _create({"streaming": True, "mcp_servers": explicit})

    assert kwargs["mcp_servers"] == explicit
    assert kwargs["enable_config_discovery"] is True


def test_workiq_sessions_merge_declared_servers_and_disable_discovery(
    declared_repo: Path,
) -> None:
    """Work IQ 専用セッションは `_hve_workiq` を保ったまま宣言分を併合し、自動探索を止める。"""
    opts: dict[str, Any] = {
        "streaming": True,
        "mcp_servers": {WORKIQ_MCP_SERVER_NAME: {"command": "npx", "tools": ["ask"]}},
    }

    _apply_repository_mcp_scope(opts, workflow_id="akm")

    assert opts["enable_config_discovery"] is False
    assert opts["mcp_servers"][WORKIQ_MCP_SERVER_NAME]["tools"] == ["ask"]
    assert "microsoft-learn" in opts["mcp_servers"]
    assert "azure" not in opts["mcp_servers"]


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


def test_workiq_session_paths_apply_the_shared_scope_helper() -> None:
    """Work IQ 専用 4 経路が共有ヘルパーを経由して宣言分を併合する。"""
    module = _orchestrator_module_ast()
    functions = {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    missing = [
        name
        for name in _WORKIQ_SESSION_FUNCTIONS
        if name not in functions
        or "_apply_repository_mcp_scope" not in _called_names(functions[name])
    ]

    assert missing == []
