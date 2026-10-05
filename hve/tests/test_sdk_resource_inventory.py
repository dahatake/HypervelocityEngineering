"""FR-TS-12: GitHub Copilot SDK resource inventory の RED 契約テスト。

すべて SDK 1.0.11 の API shape に合わせた test double であり、実 runtime、
network、model、auth、MCP connection は起動しない。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_SAFE_RESOURCE_FIELDS = {
    "kind", "name", "enabled", "source_kind", "plugin_marketplace",
    "owner_plugin", "plugin_version", "description",
}
_CORE_RESOURCE_FIELDS = {"kind", "name", "enabled", "source_kind"}


def _inventory_module():
    return importlib.import_module("hve.toolsearch.resource_inventory")


def _server_plugin(name: str = "docs-plugin", *, marketplace: str = "trusted", enabled: bool = True, version: str | None = "1.2.3", **unsafe: Any) -> SimpleNamespace:
    return SimpleNamespace(name=name, marketplace=marketplace, enabled=enabled, version=version, direct_source_id=unsafe.get("direct_source_id", "direct-secret-id"), config=unsafe.get("config"), command=unsafe.get("command"), url=unsafe.get("url"), args=unsafe.get("args"), env=unsafe.get("env"), headers=unsafe.get("headers"), credential=unsafe.get("credential"))


def _session_plugin(name: str = "docs-plugin", *, marketplace: str = "trusted", enabled: bool = True, version: str | None = "1.2.3") -> SimpleNamespace:
    return SimpleNamespace(enabled=enabled, marketplace=marketplace, name=name, version=version)


def _mcp(name: str = "knowledge-mcp", *, enabled: bool = True, source: str = "plugin", owner: str | None = "docs-plugin", version: str | None = "1.2.3", **unsafe: Any) -> SimpleNamespace:
    return SimpleNamespace(name=name, enabled=enabled, source=source, source_plugin=owner, source_plugin_version=version, type=unsafe.get("type", "stdio"), config=unsafe.get("config"), command=unsafe.get("command"), url=unsafe.get("url"), args=unsafe.get("args"), env=unsafe.get("env"), headers=unsafe.get("headers"), credential=unsafe.get("credential"))


def _server_skill(name: str = "answer-docs", *, enabled: bool = True, source: str = "plugin", description: str = "Answer from approved documentation", **unsafe: Any) -> SimpleNamespace:
    return SimpleNamespace(name=name, enabled=enabled, source=source, description=description, user_invocable=True, path=unsafe.get("path", "C:/secret/plugin/SKILL.md"), project_path=unsafe.get("project_path", "C:/secret/repo"), argument_hint=unsafe.get("argument_hint", "raw arguments"), command_name=unsafe.get("command_name", "answer"), config=unsafe.get("config"), command=unsafe.get("command"), url=unsafe.get("url"), args=unsafe.get("args"), env=unsafe.get("env"), headers=unsafe.get("headers"), credential=unsafe.get("credential"))


def _session_skill(name: str = "answer-docs", *, plugin_name: str | None = "docs-plugin", enabled: bool = True, source: str = "plugin", description: str = "Answer from approved documentation") -> SimpleNamespace:
    return SimpleNamespace(name=name, enabled=enabled, source=source, description=description, plugin_name=plugin_name, user_invocable=True, path="C:/secret/session/SKILL.md", argument_hint="raw arguments", command_name="answer")


class _AsyncCall:
    def __init__(self, value: Any = None, *, error: BaseException | None = None, pending: bool = False) -> None:
        self.value, self.error, self.pending, self.cancelled = value, error, pending, False

    async def _result(self) -> Any:
        if self.pending:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.error is not None:
            raise self.error
        return self.value


class _AsyncNoParams(_AsyncCall):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[float | None] = []

    async def __call__(self, *, timeout: float | None = None) -> Any:
        self.calls.append(timeout)
        return await self._result()


class _AsyncOneParam(_AsyncCall):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[Any, float | None]] = []

    async def __call__(self, params: Any, *, timeout: float | None = None) -> Any:
        self.calls.append((params, timeout))
        return await self._result()


class _Forbidden:
    def __init__(self, message: str) -> None:
        self.message = message

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(self.message)


class _NoPromptSession:
    def __init__(self, *, plugins: list[Any] | None = None, skills: list[Any] | None = None, plugins_error: BaseException | None = None, skills_error: BaseException | None = None, skills_pending: bool = False, disconnect_pending: bool = False) -> None:
        self.rpc = SimpleNamespace(plugins=SimpleNamespace(list=_AsyncNoParams(SimpleNamespace(plugins=plugins or []), error=plugins_error)), skills=SimpleNamespace(list=_AsyncNoParams(SimpleNamespace(skills=skills or []), error=skills_error, pending=skills_pending)), mcp=_Forbidden("inventory session must not connect to or query MCP"))
        self.disconnect_calls, self.disconnect_pending, self.disconnect_cancelled = 0, disconnect_pending, False

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        if self.disconnect_pending:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.disconnect_cancelled = True
                raise

    async def send(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("inventory session must not send a prompt")

    async def send_and_wait(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("inventory session must not send a prompt")


class _FakeClient:
    def __init__(self, *, mcps: list[Any] | None = None, plugins: list[Any] | None = None, skills: list[Any] | None = None, session: _NoPromptSession | None = None, mcp_error: BaseException | None = None, plugins_error: BaseException | None = None, skills_error: BaseException | None = None, skill_discovery_errors: list[str] | None = None, create_error: BaseException | None = None, start_pending: bool = False, create_pending: bool = False, stop_pending: bool = False) -> None:
        self.rpc = SimpleNamespace(mcp=SimpleNamespace(discover=_AsyncOneParam(SimpleNamespace(servers=mcps or []), error=mcp_error)), plugins=SimpleNamespace(list=_AsyncNoParams(SimpleNamespace(plugins=plugins or []), error=plugins_error), install=_Forbidden("inventory must not install plugins"), enable=_Forbidden("inventory must not enable plugins")), skills=SimpleNamespace(discover=_AsyncOneParam(SimpleNamespace(skills=skills or [], errors=skill_discovery_errors or []), error=skills_error), enable=_Forbidden("inventory must not enable skills")))
        self.session, self.create_error = session or _NoPromptSession(), create_error
        self.create_session_calls: list[dict[str, Any]] = []
        self.start_calls, self.start_pending, self.start_cancelled = 0, start_pending, False
        self.create_pending, self.create_cancelled = create_pending, False
        self.stop_calls, self.stop_pending, self.stop_cancelled = 0, stop_pending, False

    async def start(self) -> None:
        self.start_calls += 1
        if self.start_pending:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.start_cancelled = True
                raise

    async def create_session(self, **kwargs: Any) -> _NoPromptSession:
        self.create_session_calls.append(kwargs)
        if self.create_pending:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.create_cancelled = True
                raise
        if self.create_error is not None:
            raise self.create_error
        return self.session

    async def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_pending:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.stop_cancelled = True
                raise


def _resolve_result(result: Any) -> Any:
    return asyncio.run(result) if inspect.isawaitable(result) else result


def _discover(tmp_path: Path, client: _FakeClient, **kwargs: Any):
    result = _inventory_module().discover_sdk_resources(working_directory=tmp_path, cli_path=kwargs.pop("cli_path", "C:/fake/copilot.exe"), client_factory=lambda **_factory_kwargs: client, force_refresh=kwargs.pop("force_refresh", True), **kwargs)
    return _resolve_result(result)


def test_snapshot_has_core_fields_and_no_fields_outside_safe_allowlist(tmp_path: Path) -> None:
    snapshot = _discover(tmp_path, _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=_NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()])))
    assert (snapshot.plugin_state, snapshot.mcp_state, snapshot.skill_state) == ("ready", "ready", "ready")
    for resource in (*snapshot.plugins, *snapshot.mcp_servers, *snapshot.skills):
        assert _CORE_RESOURCE_FIELDS <= set(vars(resource)) <= _SAFE_RESOURCE_FIELDS


def test_uses_server_scoped_sdk_apis_and_one_no_prompt_all_mcp_disabled_session(tmp_path: Path) -> None:
    session = _NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()])
    client = _FakeClient(mcps=[_mcp("alpha"), _mcp("beta", enabled=False)], plugins=[_server_plugin()], skills=[_server_skill()], session=session)
    snapshot = _discover(tmp_path, client)
    assert snapshot.mcp_state == "ready"
    assert len(client.create_session_calls) == 1
    options = client.create_session_calls[0]
    assert options["working_directory"] == str(tmp_path.resolve())
    assert options["enable_config_discovery"] is True and options["enable_skills"] is True
    assert options["request_extensions"] is False
    assert set(options["disabled_mcp_servers"]) == {"alpha", "beta"}
    assert options.get("mcp_servers") is None and options.get("on_mcp_auth_request") is None
    assert len(session.rpc.plugins.list.calls) == len(session.rpc.skills.list.calls) == 1


@pytest.mark.parametrize("create_error", [None, RuntimeError("session-create-secret")])
def test_always_cleans_up_session_and_client(tmp_path: Path, create_error: BaseException | None) -> None:
    session = _NoPromptSession()
    client = _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=session, create_error=create_error)
    snapshot = _discover(tmp_path, client)
    assert client.stop_calls == 1
    assert session.disconnect_calls == (0 if create_error is not None else 1)
    assert "session-create-secret" not in repr(snapshot)


def test_partial_failure_is_kind_scoped_and_does_not_discard_other_resources(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient(
        mcps=[_mcp()],
        plugins=[_server_plugin()],
        skills_error=RuntimeError("private path C:/secret/SKILL.md"),
        session=_NoPromptSession(
            plugins=[_session_plugin()],
            skills_error=RuntimeError("still private"),
        ),
    )
    with caplog.at_level("DEBUG"):
        snapshot = _discover(tmp_path, client)
    assert snapshot.plugin_state == "ready"
    assert snapshot.mcp_state == "ready"
    assert snapshot.skill_state == "unverified"
    assert [item.name for item in snapshot.plugins] == ["docs-plugin"]
    assert [item.name for item in snapshot.mcp_servers] == ["knowledge-mcp"]
    captured = capsys.readouterr()
    observable = repr(snapshot) + captured.out + captured.err + caplog.text
    assert "private path" not in observable and "still private" not in observable


@pytest.mark.parametrize(
    ("failed_kind", "failure_kwargs"),
    [
        ("mcp", {"mcp_error": RuntimeError("private MCP config")}),
        ("plugin", {"plugins_error": RuntimeError("private Plugin config")}),
    ],
)
def test_mcp_and_plugin_partial_failures_preserve_every_other_kind(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    failed_kind: str,
    failure_kwargs: dict[str, BaseException],
) -> None:
    client = _FakeClient(
        mcps=[_mcp()],
        plugins=[_server_plugin()],
        skills=[_server_skill()],
        session=_NoPromptSession(
            plugins=[_session_plugin()],
            skills=[_session_skill()],
        ),
        **failure_kwargs,
    )
    with caplog.at_level("DEBUG"):
        snapshot = _discover(tmp_path, client)
    expected_states = {"plugin": "ready", "mcp": "ready", "skill": "ready"}
    expected_states[failed_kind] = "unverified"
    assert snapshot.plugin_state == expected_states["plugin"]
    assert snapshot.mcp_state == expected_states["mcp"]
    assert snapshot.skill_state == expected_states["skill"]
    assert [item.name for item in snapshot.skills] == ["answer-docs"]
    captured = capsys.readouterr()
    observable = repr(snapshot) + captured.out + captured.err + caplog.text
    assert "private MCP config" not in observable and "private Plugin config" not in observable


def test_server_skill_load_errors_mark_only_skills_unverified_without_leaking(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient(
        mcps=[_mcp()],
        plugins=[_server_plugin()],
        skills=[_server_skill()],
        skill_discovery_errors=["malformed C:/secret/SKILL.md"],
        session=_NoPromptSession(
            plugins=[_session_plugin()],
            skills=[_session_skill()],
        ),
    )
    with caplog.at_level("DEBUG"):
        snapshot = _discover(tmp_path, client)
    assert snapshot.skill_state == "unverified"
    assert [item.name for item in snapshot.skills] == ["answer-docs"]
    captured = capsys.readouterr()
    observable = repr(snapshot) + captured.out + captured.err + caplog.text
    assert "malformed" not in observable and "C:/secret" not in observable


def test_snapshot_drops_direct_ids_transport_and_skill_paths(tmp_path: Path) -> None:
    snapshot = _discover(
        tmp_path,
        _FakeClient(
            mcps=[_mcp()],
            plugins=[_server_plugin()],
            skills=[_server_skill()],
            session=_NoPromptSession(
                plugins=[_session_plugin()],
                skills=[_session_skill()],
            ),
        ),
    )
    rendered = repr(snapshot)
    for sentinel in ("direct-secret-id", "C:/secret", "stdio"):
        assert sentinel not in rendered


def test_raw_sdk_configuration_and_credentials_never_reach_observable_output(tmp_path: Path) -> None:
    unsafe = {"config": {"raw-config-sentinel": True}, "command": "raw-command-sentinel", "url": "https://raw-url-sentinel.invalid/private", "args": ["raw-args-sentinel"], "env": {"RAW_ENV_SENTINEL": "raw-env-value-sentinel"}, "headers": {"Authorization": "raw-header-sentinel"}, "credential": "raw-credential-sentinel"}
    snapshot = _discover(tmp_path, _FakeClient(mcps=[_mcp(**unsafe)], plugins=[_server_plugin(**unsafe)], skills=[_server_skill(**unsafe)], session=_NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()])))
    rendered = repr(snapshot)
    for sentinel in ("raw-config-sentinel", "raw-command-sentinel", "raw-url-sentinel", "raw-args-sentinel", "RAW_ENV_SENTINEL", "raw-env-value-sentinel", "raw-header-sentinel", "raw-credential-sentinel", "C:/secret", "stdio", "direct-secret-id"):
        assert sentinel not in rendered


def test_process_cache_is_keyed_by_runtime_and_working_directory_and_force_refreshes(tmp_path: Path) -> None:
    clients: list[_FakeClient] = []
    def factory(**_kwargs: Any) -> _FakeClient:
        client = _FakeClient(); clients.append(client); return client
    module = _inventory_module()
    first = _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path="C:/runtime-a.exe", client_factory=factory, force_refresh=True))
    second = _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path="C:/runtime-a.exe", client_factory=factory))
    assert second == first and len(clients) == 1
    _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path="C:/runtime-b.exe", client_factory=factory))
    _resolve_result(module.discover_sdk_resources(working_directory=tmp_path / "other", cli_path="C:/runtime-a.exe", client_factory=factory))
    _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path="C:/runtime-a.exe", client_factory=factory, force_refresh=True))
    assert len(clients) == 4


def test_unverified_snapshot_is_not_negatively_cached_so_later_callers_can_retry(tmp_path: Path) -> None:
    """D-01B回帰: fan-out並行実行で最初のcallerがclient接続自体に一時的に
    失敗しても（resource contentionを想定）、同一(runtime, working_directory)
    キーの後続callerはprocess cacheから失敗を継承せず、独立に再discovery
    できなければならない。client接続後に判明した個別kindのunverified
    （環境固有の安定した特性）は対象外とし、既存どおりcacheを維持する。"""
    module = _inventory_module()
    cli_path = "C:/fake/negative-cache-test.exe"

    class _StartFailsClient:
        def __init__(self) -> None:
            self.start_calls = 0

        async def start(self) -> None:
            self.start_calls += 1
            raise RuntimeError("transient connection contention")

    failing_client = _StartFailsClient()
    first = _resolve_result(
        module.discover_sdk_resources(
            working_directory=tmp_path,
            cli_path=cli_path,
            client_factory=lambda **_kwargs: failing_client,
            force_refresh=True,
        )
    )
    assert first.mcp_state == "unverified"

    succeeding_client = _FakeClient(mcps=[_mcp()])
    second = _resolve_result(
        module.discover_sdk_resources(
            working_directory=tmp_path,
            cli_path=cli_path,
            client_factory=lambda **_kwargs: succeeding_client,
        )
    )
    assert succeeding_client.start_calls == 1, "cacheから短絡され再discoveryされなかった"
    assert second.mcp_state == "ready"


def test_deadline_expired_snapshot_is_not_cached_so_a_later_caller_can_retry(tmp_path: Path) -> None:
    """resume 並列起動の回帰: 負荷で共有 deadline が切れて欠けた snapshot を以後へ継承しない。"""
    module = _inventory_module()
    cli_path = "C:/fake/deadline-cache-test.exe"
    slow = _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=_NoPromptSession(skills_pending=True))
    first = _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path=cli_path, client_factory=lambda **_kwargs: slow, force_refresh=True, timeout=0.01))
    assert first.skill_ownership_state == "unverified"

    healthy = _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=_NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()]))
    second = _resolve_result(module.discover_sdk_resources(working_directory=tmp_path, cli_path=cli_path, client_factory=lambda **_kwargs: healthy))
    assert healthy.start_calls == 1, "期限切れの snapshot が cache から継承された"
    assert second.mcp_state == second.skill_state == "ready"


def test_default_shared_deadline_leaves_headroom_over_measured_discovery_time() -> None:
    assert _inventory_module().DEFAULT_DEADLINE_SECONDS >= 30.0


def test_process_cache_never_writes_to_disk_or_starts_background_threads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    monkeypatch.setattr(Path, "write_text", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write")))
    monkeypatch.setattr(Path, "write_bytes", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write")))
    monkeypatch.setattr(threading.Thread, "__init__", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("thread")))
    _discover(tmp_path, _FakeClient())
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before


def test_session_skill_ownership_is_supplemented_only_when_plugin_identity_is_unique(tmp_path: Path) -> None:
    unique = _discover(tmp_path / "unique", _FakeClient(plugins=[_server_plugin()], skills=[_server_skill()], session=_NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()])))
    assert (unique.skills[0].owner_plugin, unique.skills[0].plugin_marketplace) == ("docs-plugin", "trusted")
    ambiguous = _discover(tmp_path / "ambiguous", _FakeClient(plugins=[_server_plugin(marketplace="market-a"), _server_plugin(marketplace="market-b")], skills=[_server_skill()], session=_NoPromptSession(plugins=[_session_plugin(marketplace="market-a"), _session_plugin(marketplace="market-b")], skills=[_session_skill()])))
    assert ambiguous.skills[0].owner_plugin is None and ambiguous.skills[0].plugin_marketplace is None


@pytest.mark.parametrize(
    ("server_plugins", "session_plugins", "server_skill", "session_skills"),
    [
        ([_server_plugin(), _server_plugin()], [_session_plugin(), _session_plugin()], _server_skill(), [_session_skill()]),
        ([_server_plugin()], [_session_plugin(name="other-plugin")], _server_skill(), [_session_skill()]),
        ([_server_plugin(enabled=True)], [_session_plugin(enabled=False)], _server_skill(), [_session_skill()]),
        ([_server_plugin(version="1.2.3")], [_session_plugin(version="9.9.9")], _server_skill(), [_session_skill()]),
        ([_server_plugin()], [_session_plugin()], _server_skill(source="project"), [_session_skill(source="project")]),
        ([_server_plugin()], [_session_plugin()], _server_skill(), [_session_skill(name="different-skill")]),
    ],
)
def test_skill_ownership_fails_closed_when_evidence_is_not_identical(
    tmp_path: Path,
    server_plugins: list[Any],
    session_plugins: list[Any],
    server_skill: Any,
    session_skills: list[Any],
) -> None:
    snapshot = _discover(
        tmp_path,
        _FakeClient(
            plugins=server_plugins,
            skills=[server_skill],
            session=_NoPromptSession(plugins=session_plugins, skills=session_skills),
        ),
    )
    assert snapshot.skills[0].owner_plugin is None
    assert snapshot.skills[0].plugin_marketplace is None
    assert snapshot.skills[0].plugin_version is None


def test_mcp_ownership_is_ignored_when_source_is_not_plugin(tmp_path: Path) -> None:
    snapshot = _discover(
        tmp_path,
        _FakeClient(
            mcps=[_mcp(source="workspace", owner="docs-plugin", version="1.2.3")],
        ),
    )
    assert snapshot.mcp_servers[0].owner_plugin is None
    assert snapshot.mcp_servers[0].plugin_marketplace is None
    assert snapshot.mcp_servers[0].plugin_version is None


def test_session_supplement_failure_keeps_server_scoped_state_without_guessing_owner(tmp_path: Path) -> None:
    snapshot = _discover(tmp_path, _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=_NoPromptSession(skills_error=RuntimeError("session skill failure"))))
    assert snapshot.skills[0].owner_plugin is None
    assert (snapshot.plugin_state, snapshot.mcp_state, snapshot.skill_state, snapshot.skill_ownership_state) == ("ready", "ready", "ready", "unverified")


def test_mcp_discovery_failure_does_not_create_an_ambient_inventory_session(tmp_path: Path) -> None:
    client = _FakeClient(mcp_error=RuntimeError("private MCP discovery failure"), plugins=[_server_plugin()], skills=[_server_skill()])
    snapshot = _discover(tmp_path, client)
    assert client.create_session_calls == []
    assert (snapshot.mcp_state, snapshot.plugin_state, snapshot.skill_state, snapshot.skill_ownership_state) == ("unverified", "ready", "ready", "unverified")


def test_rpc_calls_receive_one_nonincreasing_deadline_budget_and_pending_call_is_cancelled(tmp_path: Path) -> None:
    session = _NoPromptSession(plugins=[_session_plugin()], skills=[_session_skill()], skills_pending=True)
    client = _FakeClient(mcps=[_mcp()], plugins=[_server_plugin()], skills=[_server_skill()], session=session)
    snapshot = _discover(tmp_path, client, timeout=0.01)
    values = [client.rpc.mcp.discover.calls[0][1], client.rpc.plugins.list.calls[0], client.rpc.skills.discover.calls[0][1], session.rpc.plugins.list.calls[0], session.rpc.skills.list.calls[0]]
    assert all(value is not None and 0 <= value <= 0.01 for value in values)
    assert values == sorted(values, reverse=True)
    assert session.rpc.skills.list.cancelled is True and session.disconnect_calls == client.stop_calls == 1
    assert snapshot.skill_state == "ready" and snapshot.skill_ownership_state == "unverified"


@pytest.mark.parametrize("pending_stage", ["start", "create_session"])
def test_pending_client_start_or_session_creation_is_cancelled_by_shared_deadline_and_cleans_up(tmp_path: Path, pending_stage: str) -> None:
    client = _FakeClient(start_pending=pending_stage == "start", create_pending=pending_stage == "create_session")
    snapshot = _discover(tmp_path, client, timeout=0.01)
    assert client.start_cancelled is (pending_stage == "start")
    assert client.create_cancelled is (pending_stage == "create_session")
    assert client.stop_calls == 1 and client.session.disconnect_calls == 0
    expected = "unverified" if pending_stage == "start" else "ready"
    assert (snapshot.plugin_state, snapshot.mcp_state, snapshot.skill_state) == (expected, expected, expected)


def test_cleanup_is_bounded_by_the_same_deadline_and_cancelled_before_client_stop(tmp_path: Path) -> None:
    session = _NoPromptSession(disconnect_pending=True)
    client = _FakeClient(session=session)
    _discover(tmp_path, client, timeout=0.01)
    assert session.disconnect_calls == 1 and session.disconnect_cancelled is True and client.stop_calls == 1
