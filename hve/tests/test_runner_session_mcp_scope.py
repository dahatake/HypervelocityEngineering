"""FR-CLI-76 / FR-TS-13: Step 実行セッションは shared resource routing を使う。"""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from hve.runner import _create_session_with_auto_reasoning_fallback

class _RecordingClient:
    def __init__(self) -> None:
        self.create_session_kwargs: list[dict[str, Any]] = []

    async def create_session(self, **kwargs: Any) -> object:
        self.create_session_kwargs.append(kwargs)
        return object()


def _make_repo(root: Path) -> None:
    skill_dir = root / ".github" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill.\n---\n# demo\n", encoding="utf-8"
    )


def _create(client: _RecordingClient, opts: dict[str, Any]) -> dict[str, Any]:
    asyncio.run(_create_session_with_auto_reasoning_fallback(client, opts))
    return client.create_session_kwargs[-1]


def _create_with_routing_probe(
    opts: dict[str, Any],
    *,
    workflow_id: str = "ard",
):
    runner = importlib.import_module("hve.runner")
    client = _RecordingClient()
    routed_session = object()
    snapshot = object()
    policy = object()
    create_routed_session = AsyncMock(return_value=routed_session)

    with patch.object(
        runner,
        "discover_sdk_resources",
        return_value=snapshot,
    ) as discover, patch.object(
        runner,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: policy),
    ), patch.object(
        runner,
        "create_routed_session",
        new=create_routed_session,
    ):
        result = asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                opts,
                config=runner.SDKConfig(),
                workflow_id=workflow_id,
            )
        )

    return result, client, discover, create_routed_session, snapshot, policy


@pytest.fixture
def declared_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_known_workflow_uses_shared_resource_routing_instead_of_repository_injection(
    declared_repo: Path,
) -> None:
    result, client, discover, create_routed_session, snapshot, policy = _create_with_routing_probe(
        {"streaming": True}
    )

    assert result is not None
    assert client.create_session_kwargs == []
    discover.assert_called_once()
    create_routed_session.assert_awaited_once()
    kwargs = create_routed_session.await_args.kwargs
    assert kwargs["snapshot"] is snapshot
    assert kwargs["policy"] is policy
    assert kwargs["workflow_id"] == "ard"
    assert "mcp_servers" not in kwargs["session_options"]


def test_preseeded_enable_config_discovery_does_not_bypass_shared_routing(
    declared_repo: Path,
) -> None:
    _result, client, discover, create_routed_session, _snapshot, _policy = _create_with_routing_probe(
        {"streaming": True, "enable_config_discovery": True}
    )

    assert client.create_session_kwargs == []
    discover.assert_called_once()
    create_routed_session.assert_awaited_once()


def test_preseeded_disabled_mcp_servers_does_not_bypass_shared_routing(
    declared_repo: Path,
) -> None:
    _result, client, discover, create_routed_session, _snapshot, _policy = _create_with_routing_probe(
        {"streaming": True, "disabled_mcp_servers": ["azure"]}
    )

    assert client.create_session_kwargs == []
    discover.assert_called_once()
    create_routed_session.assert_awaited_once()


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
    _make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps({"mcpServers": []}),
        json.dumps({"servers": {"azure": {"command": "npx"}}}),
        json.dumps({"mcpServers": {}}),
        "{ not json",
    ],
)
def test_malformed_repository_mcp_config_keeps_config_discovery_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    _make_repo(tmp_path)
    (tmp_path / ".github" / ".mcp.json").write_text(payload, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    kwargs = _create(_RecordingClient(), {"streaming": True})

    assert "mcp_servers" not in kwargs
    assert kwargs["enable_config_discovery"] is True


def test_skill_directories_are_still_injected_when_config_discovery_is_disabled(
    declared_repo: Path,
) -> None:
    _result, _client, _discover, create_routed_session, _snapshot, _policy = _create_with_routing_probe(
        {"streaming": True}
    )
    kwargs = create_routed_session.await_args.kwargs["session_options"]

    assert kwargs["enable_config_discovery"] is True
    assert str(declared_repo / ".github" / "skills") in kwargs["skill_directories"]


def test_shared_routing_helper_no_longer_reads_repository_mcp_json() -> None:
    import inspect
    import hve.runner as runner_module

    source = inspect.getsource(runner_module._create_session_with_auto_reasoning_fallback)

    assert ".mcp.json" not in source
    assert "session_options[\"mcp_servers\"]" not in source


def test_foundry_required_step_uses_required_mcp_server_names_instead_of_raw_configs() -> None:
    runner = importlib.import_module("hve.runner")
    client = _RecordingClient()
    routed_session = object()
    create_routed_session = AsyncMock(return_value=routed_session)

    with patch.object(runner, "discover_sdk_resources", return_value=object()), patch.object(
        runner,
        "ToolSearchPolicy",
        new=SimpleNamespace(load=lambda **_kwargs: object()),
    ), patch.object(runner, "create_routed_session", new=create_routed_session):
        asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                client,
                {"streaming": True},
                config=runner.SDKConfig(),
                workflow_id="aagd",
                required_mcp_servers=["azure", "microsoft-learn"],
            )
        )

    assert create_routed_session.await_args is not None
    assert create_routed_session.await_args.kwargs["required_mcp_servers"] == ["azure", "microsoft-learn"]
