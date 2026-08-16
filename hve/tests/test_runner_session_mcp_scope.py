"""FR-CLI-76: Step 実行セッションへ公開する MCP サーバをリポジトリ宣言分に限定する契約。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from hve.runner import _create_session_with_auto_reasoning_fallback

_DECLARED_SERVERS = {
    "azure": {"command": "npx", "args": ["-y", "@azure/mcp@latest", "server", "start"]},
    "microsoft-learn": {"type": "http", "url": "https://learn.microsoft.com/api/mcp"},
}


class _RecordingClient:
    def __init__(self) -> None:
        self.create_session_kwargs: list[dict[str, Any]] = []

    async def create_session(self, **kwargs: Any) -> object:
        self.create_session_kwargs.append(kwargs)
        return object()


def _make_repo(root: Path, *, mcp_config: str | None) -> None:
    skill_dir = root / ".github" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill.\n---\n# demo\n", encoding="utf-8"
    )
    if mcp_config is not None:
        (root / ".github" / ".mcp.json").write_text(mcp_config, encoding="utf-8")


def _create(client: _RecordingClient, opts: dict[str, Any]) -> dict[str, Any]:
    asyncio.run(_create_session_with_auto_reasoning_fallback(client, opts))
    return client.create_session_kwargs[-1]


@pytest.fixture
def declared_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _make_repo(tmp_path, mcp_config=json.dumps({"mcpServers": _DECLARED_SERVERS}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_repository_mcp_servers_are_injected_when_caller_omits_them(declared_repo: Path) -> None:
    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert kwargs["mcp_servers"] == _DECLARED_SERVERS


def test_config_discovery_is_disabled_when_repository_mcp_is_injected(declared_repo: Path) -> None:
    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert kwargs["enable_config_discovery"] is False


def test_explicit_mcp_servers_are_not_overridden(declared_repo: Path) -> None:
    explicit = {"only-this": {"command": "noop"}}

    kwargs = _create(_RecordingClient(), {"streaming": True, "mcp_servers": explicit})

    assert kwargs["mcp_servers"] == explicit
    assert kwargs["enable_config_discovery"] is True


def test_explicit_config_discovery_is_not_overridden(declared_repo: Path) -> None:
    kwargs = _create(
        _RecordingClient(), {"streaming": True, "enable_config_discovery": True}
    )

    assert kwargs["enable_config_discovery"] is True
    assert "mcp_servers" not in kwargs


def test_missing_repository_mcp_config_keeps_config_discovery_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_repo(tmp_path, mcp_config=None)
    monkeypatch.chdir(tmp_path)

    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps({"mcpServers": []}),
        json.dumps({"servers": _DECLARED_SERVERS}),
        json.dumps({"mcpServers": {}}),
        "{ not json",
    ],
)
def test_malformed_repository_mcp_config_keeps_config_discovery_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    _make_repo(tmp_path, mcp_config=payload)
    monkeypatch.chdir(tmp_path)

    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


def test_skill_directories_are_still_injected_when_config_discovery_is_disabled(
    declared_repo: Path,
) -> None:
    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert kwargs["enable_config_discovery"] is False
    assert str(declared_repo / ".github" / "skills") in kwargs["skill_directories"]


def test_declared_mcp_servers_specify_a_tools_allowlist() -> None:
    """`tools` キーが無い MCP サーバは明示指定しても起動されない（実測）。"""
    repo_root = Path(__file__).resolve().parents[2]
    declared = json.loads((repo_root / ".github" / ".mcp.json").read_text(encoding="utf-8"))

    missing = [
        name for name, config in declared["mcpServers"].items() if "tools" not in config
    ]

    assert missing == []


def test_foundry_required_azure_config_specifies_a_tools_allowlist() -> None:
    from hve.runner import _FOUNDRY_REQUIRED_AZURE_MCP_CONFIG

    assert "tools" in _FOUNDRY_REQUIRED_AZURE_MCP_CONFIG
