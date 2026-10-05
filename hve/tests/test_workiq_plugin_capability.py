"""FR-CLI-91: GitHub Copilot SDK discovery を正本とする Work IQ capability。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hve import workiq


class _FakeMcpApi:
    def __init__(self, owner: "_FakeClient", result: Any) -> None:
        self._owner = owner
        self._result = result

    async def discover(self, request: Any, *, timeout: float | None = None) -> Any:
        self._owner.discover_calls.append((request, timeout))
        if self._owner.discover_error is not None:
            raise self._owner.discover_error
        return self._result


class _FakeInventorySession:
    """FR-TS-12 が明示的に許可する no-prompt inventory session。

    ``send`` を持たせないことで、capability 射影がモデル問い合わせを
    行わないことを型レベルで固定する。
    """

    def __init__(self) -> None:
        self.disconnect_calls = 0
        self.rpc = SimpleNamespace()

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


class _FakeClient:
    def __init__(
        self,
        result: Any,
        *,
        start_error: BaseException | None = None,
        discover_error: BaseException | None = None,
        stop_error: BaseException | None = None,
    ) -> None:
        self.start_error = start_error
        self.discover_error = discover_error
        self.stop_error = stop_error
        self.start_calls = 0
        self.stop_calls = 0
        self.discover_calls: list[tuple[Any, float | None]] = []
        self.create_session_calls = 0
        self.sessions: list[_FakeInventorySession] = []
        self.rpc = SimpleNamespace(mcp=_FakeMcpApi(self, result))

    async def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error

    async def create_session(self, *_args: Any, **kwargs: Any) -> Any:
        self.create_session_calls += 1
        assert "prompt" not in kwargs, "inventory session must not carry a prompt"
        session = _FakeInventorySession()
        self.sessions.append(session)
        return session


def _server(
    name: str,
    *,
    enabled: bool = True,
    source: str = "plugin",
    **extra: Any,
) -> Any:
    return SimpleNamespace(name=name, enabled=enabled, source=source, **extra)


def _result(*servers: Any) -> Any:
    return SimpleNamespace(servers=list(servers))


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Work IQ 専用 cache は廃止し、FR-TS-12 の共有 snapshot cache を使う。"""
    from hve.toolsearch import resource_inventory

    resource_inventory._CACHE.clear()
    yield
    resource_inventory._CACHE.clear()


def _probe(
    tmp_path: Path,
    result: Any,
    **client_kwargs: Any,
) -> tuple[workiq.WorkIQCapability, _FakeClient, list[dict[str, Any]]]:
    client = _FakeClient(result, **client_kwargs)
    factory_calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> _FakeClient:
        factory_calls.append(dict(kwargs))
        return client

    capability = workiq.probe_workiq_plugin_capability(
        cli_path="sdk-runtime-copilot",
        github_token="test-token",
        working_directory=tmp_path,
        client_factory=factory,
        force_refresh=True,
    )
    return capability, client, factory_calls


def test_exact_enabled_workiq_is_ready(tmp_path: Path) -> None:
    capability, client, factory_calls = _probe(
        tmp_path,
        _result(_server("azure"), _server("workiq"), _server("github")),
    )

    assert capability.state == "ready"
    assert capability.reason_code == "ready"
    assert capability.enabled_server_names == ("azure", "github", "workiq")
    assert client.start_calls == 1
    assert client.stop_calls == 1
    # FR-TS-12 は no-prompt inventory session を明示的に許可する。禁止されているのは
    # prompt 送信であり、session は必ず切断される。
    assert all(session.disconnect_calls == 1 for session in client.sessions)
    assert all(not hasattr(session, "send") for session in client.sessions)
    assert len(client.discover_calls) == 1
    request, _timeout = client.discover_calls[0]
    assert request.working_directory == str(tmp_path.resolve())
    assert factory_calls == [
        {
            "cli_path": "sdk-runtime-copilot",
            "cli_url": None,
            "github_token": "test-token",
            "log_level": "error",
            "working_directory": str(tmp_path.resolve()),
        }
    ]


@pytest.mark.parametrize("source", ["plugin", "user", "workspace", "builtin"])
def test_source_kind_does_not_restrict_exact_workiq(
    tmp_path: Path,
    source: str,
) -> None:
    capability, _client, _factory_calls = _probe(
        tmp_path,
        _result(_server("workiq", source=source)),
    )

    assert capability.state == "ready"


@pytest.mark.parametrize(
    "servers",
    [
        (),
        (_server("workiq", enabled=False),),
        (_server("workiq-preview"),),
        (_server("_hve_workiq"),),
        (_server("azure"), _server("github")),
    ],
)
def test_absent_disabled_or_alias_only_is_not_configured(
    tmp_path: Path,
    servers: tuple[Any, ...],
) -> None:
    capability, client, _factory_calls = _probe(tmp_path, _result(*servers))

    assert capability.state == "not-configured"
    assert capability.reason_code == "not-configured"
    assert client.stop_calls == 1


def test_raw_transport_and_secret_metadata_are_not_retained(tmp_path: Path) -> None:
    capability, _client, _factory_calls = _probe(
        tmp_path,
        _result(
            _server(
                "workiq",
                type="stdio",
                command="secret-command",
                url="https://user:secret@example.test/mcp",
                headers={"Authorization": "Bearer SECRET"},
            )
        ),
    )

    rendered = repr(capability)
    assert capability.state == "ready"
    for forbidden in ("secret-command", "user:secret", "Bearer SECRET", "stdio"):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "result",
    [
        None,
        SimpleNamespace(),
        SimpleNamespace(servers=None),
        SimpleNamespace(servers={}),
        _result(SimpleNamespace(name=None, enabled=True)),
        _result(SimpleNamespace(name="workiq", enabled=1)),
    ],
)
def test_invalid_discovery_schema_is_unverified(tmp_path: Path, result: Any) -> None:
    capability, client, _factory_calls = _probe(tmp_path, result)

    assert capability.state == "unverified"
    assert capability.reason_code == "unverified"
    assert capability.enabled_server_names == ()
    assert client.stop_calls == 1


@pytest.mark.parametrize("stage", ["factory", "start", "discover"])
def test_sdk_failures_are_unverified_and_cleanup_created_clients(
    tmp_path: Path,
    stage: str,
) -> None:
    client = _FakeClient(
        _result(_server("workiq")),
        start_error=RuntimeError("start secret") if stage == "start" else None,
        discover_error=RuntimeError("discover secret") if stage == "discover" else None,
    )

    def factory(**_kwargs: Any) -> _FakeClient:
        if stage == "factory":
            raise RuntimeError("factory secret")
        return client

    capability = workiq.probe_workiq_plugin_capability(
        working_directory=tmp_path,
        client_factory=factory,
        force_refresh=True,
    )

    assert capability.state == "unverified"
    assert "secret" not in repr(capability)
    assert client.stop_calls == (0 if stage == "factory" else 1)


def test_cleanup_failure_does_not_replace_a_ready_result(tmp_path: Path) -> None:
    capability, client, _factory_calls = _probe(
        tmp_path,
        _result(_server("workiq")),
        stop_error=RuntimeError("cleanup failed"),
    )

    assert capability.state == "ready"
    assert client.stop_calls == 1


def test_process_cache_prevents_duplicate_discovery(tmp_path: Path) -> None:
    clients: list[_FakeClient] = []

    def factory(**_kwargs: Any) -> _FakeClient:
        client = _FakeClient(_result(_server("workiq")))
        clients.append(client)
        return client

    first = workiq.probe_workiq_plugin_capability(
        working_directory=tmp_path,
        client_factory=factory,
    )
    second = workiq.probe_workiq_plugin_capability(
        working_directory=tmp_path,
        client_factory=factory,
    )

    assert first == second
    assert len(clients) == 1
    assert len(clients[0].discover_calls) == 1


def test_sync_probe_is_safe_inside_an_existing_event_loop(tmp_path: Path) -> None:
    async def scenario() -> workiq.WorkIQCapability:
        return _probe(tmp_path, _result(_server("workiq")))[0]

    assert asyncio.run(scenario()).state == "ready"


def test_cli_url_is_delegated_to_the_sdk_factory(tmp_path: Path) -> None:
    client = _FakeClient(_result(_server("workiq")))
    calls: list[dict[str, Any]] = []

    capability = workiq.probe_workiq_plugin_capability(
        cli_url="http://127.0.0.1:4321",
        working_directory=tmp_path,
        client_factory=lambda **kwargs: calls.append(dict(kwargs)) or client,
        force_refresh=True,
    )

    assert capability.state == "ready"
    assert calls[0]["cli_url"] == "http://127.0.0.1:4321"
    assert calls[0]["cli_path"] is None


def test_unresolvable_working_directory_fails_before_client_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fail_resolve(_self: Path, *_args: Any, **_kwargs: Any) -> Path:
        raise OSError("unresolvable secret path")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    capability = workiq.probe_workiq_plugin_capability(
        working_directory=tmp_path,
        client_factory=lambda **kwargs: calls.append(dict(kwargs)),
        force_refresh=True,
    )

    assert capability.state == "unverified"
    assert calls == []
    assert "secret" not in repr(capability)
