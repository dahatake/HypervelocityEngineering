"""T04 offline contracts for FR-TS-13 session resource readiness (2026-09-06).

Source: hve-dev/requirement-definition.md, FR-TS-13 readiness amendment.
No test imports another test's Fake or starts an SDK client, auth, or model.
The R1 regression uses the EXISTING create_session_from_route API. Only tests
named deadline_keyword_contract require the proposed optional absolute deadline;
their pre-implementation TypeError is API-contract RED, not an R1 reproduction.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from copilot.generated.rpc import (
    CurrentToolMetadata,
    MCPDisableRequest,
    MCPListToolsRequest,
    McpServerStatus,
    SessionUpdateOptionsParams,
    SessionUpdateOptionsResult,
    ToolsGetCurrentMetadataResult,
    ToolsInitializeAndValidateResult,
)

from hve.toolsearch import resource_routing as routing


SERVER = "catalog-mcp"
PEER = "notes-mcp"
SKILL = "required-skill"
SAFETY_SECONDS = 2.0
RPC_PHASES = (
    "skills.list",
    "tools.initialize_and_validate",
    "mcp.list",
    "mcp.list_tools",
    "options.update",
    "tools.get_current_metadata",
)


@pytest.fixture(autouse=True)
def short_routing_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the 60 / 0.5 / 5 second internal budgets without a new API."""
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.1, raising=False)
    monkeypatch.setattr(routing, "_ROUTING_POLL_INTERVAL_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(routing, "_ROUTING_CLEANUP_TIMEOUT_SECONDS", 0.01, raising=False)


def _listing(*states: tuple[str, str]) -> SimpleNamespace:
    """Mirror MCPServerList.servers / host and the SDK status enum, not a dict."""
    return SimpleNamespace(
        servers=[
            SimpleNamespace(name=name, status=McpServerStatus(status))
            for name, status in states
        ],
        host=SimpleNamespace(
            clients=[name for name, status in states if status == "connected"],
            disabled_servers=[name for name, status in states if status == "disabled"],
            failed_servers={},
            filtered_servers=[],
            mcp3_p_enabled=True,
            needs_auth_servers={},
            pending_connections=[name for name, status in states if status == "pending"],
        ),
    )


def _metadata(
    *identities: tuple[str, str],
    deferred: bool = False,
) -> ToolsGetCurrentMetadataResult:
    return ToolsGetCurrentMetadataResult(
        tools=[
            CurrentToolMetadata(
                description="offline MCP tool",
                name=f"mcp__{server_name}__{tool_name}",
                defer_loading=deferred,
                mcp_server_name=server_name,
                mcp_tool_name=tool_name,
                namespaced_name=f"mcp:{server_name}-{tool_name}",
            )
            for server_name, tool_name in identities
        ]
    )


class FakeRPC:
    """A cold MCP host, explicit RPC responses, and an ordered call journal."""

    def __init__(
        self,
        *,
        servers: tuple[str, ...] = (SERVER,),
        initialized: bool = False,
    ) -> None:
        self.initialized = initialized
        self.init_behavior = "initialize"
        self.calls: list[str] = []
        self.timeouts: list[tuple[str, float | None]] = []
        self.active_servers = set(servers)
        self.metadata_responses: list[Any] | None = None
        self.metadata_index = 0
        self.last_update: SessionUpdateOptionsParams | None = None
        self.list_responses: list[Any] = [
            _listing(*((name, "connected") for name in servers))
        ]
        self.list_index = 0
        self.skill_response: Any = SimpleNamespace(
            skills=[SimpleNamespace(name=SKILL, enabled=True)]
        )
        self.tool_responses = {
            name: SimpleNamespace(
                tools=[SimpleNamespace(name=tool) for tool in ("search", "read", "write")]
            )
            for name in servers
        }
        self.ack = SessionUpdateOptionsResult(success=True)
        self.tools = SimpleNamespace(
            initialize_and_validate=AsyncMock(side_effect=self._initialize),
            get_current_metadata=AsyncMock(side_effect=self._metadata),
        )
        self.mcp = SimpleNamespace(
            list=AsyncMock(side_effect=self._list),
            list_tools=AsyncMock(side_effect=self._list_tools),
            disable=AsyncMock(side_effect=self._disable),
            oauth=SimpleNamespace(
                login=AsyncMock(side_effect=AssertionError("auth is forbidden"))
            ),
        )
        self.skills = SimpleNamespace(list=AsyncMock(side_effect=self._skills))
        self.options = SimpleNamespace(update=AsyncMock(side_effect=self._update))

    def _record(self, name: str, timeout: float | None) -> None:
        self.calls.append(name)
        self.timeouts.append((name, timeout))

    async def _initialize(
        self, *, timeout: float | None = None
    ) -> ToolsInitializeAndValidateResult:
        self._record("tools.initialize_and_validate", timeout)
        if self.init_behavior == "unsupported":
            raise NotImplementedError("offline unsupported initialization")
        if self.init_behavior == "initialize":
            self.initialized = True
        return ToolsInitializeAndValidateResult()

    async def _list(self, *, timeout: float | None = None) -> Any:
        self._record("mcp.list", timeout)
        if not self.initialized:
            return SimpleNamespace(servers=[], host=None)
        response = self.list_responses[min(self.list_index, len(self.list_responses) - 1)]
        self.list_index += 1
        return response

    async def _list_tools(
        self, request: MCPListToolsRequest, *, timeout: float | None = None
    ) -> Any:
        assert isinstance(request, MCPListToolsRequest)
        self._record(f"mcp.list_tools:{request.server_name}", timeout)
        if not self.initialized:
            raise RuntimeError("MCP host not initialized")
        # Cached tools deliberately do not prove connected status: the product
        # must inspect mcp.list rather than letting this Fake enforce readiness.
        return self.tool_responses[request.server_name]

    async def _disable(
        self, request: MCPDisableRequest, *, timeout: float | None = None
    ) -> Any:
        assert isinstance(request, MCPDisableRequest)
        self._record(f"mcp.disable:{request.server_name}", timeout)
        if not self.initialized:
            raise RuntimeError("No MCP host initialized")
        self.active_servers.discard(request.server_name)
        return SimpleNamespace()

    async def _skills(self, *, timeout: float | None = None) -> Any:
        self._record("skills.list", timeout)
        return self.skill_response

    async def _update(
        self, request: SessionUpdateOptionsParams, *, timeout: float | None = None
    ) -> SessionUpdateOptionsResult:
        assert isinstance(request, SessionUpdateOptionsParams)
        self._record("options.update", timeout)
        self.last_update = request
        return self.ack

    async def _metadata(self, *, timeout: float | None = None) -> Any:
        self._record("tools.get_current_metadata", timeout)
        if self.metadata_responses is not None:
            response = self.metadata_responses[
                min(self.metadata_index, len(self.metadata_responses) - 1)
            ]
            self.metadata_index += 1
            return response

        available = None
        excluded: set[str] = set()
        if self.last_update is not None:
            if self.last_update.available_tools is not None:
                available = set(self.last_update.available_tools)
            excluded = set(self.last_update.excluded_tools or ())
        identities: list[tuple[str, str]] = []
        for server_name in sorted(self.active_servers):
            for tool_name in ("search", "read"):
                tool_id = f"mcp:{server_name}-{tool_name}"
                if available is not None and tool_id not in available:
                    continue
                if tool_id not in excluded:
                    identities.append((server_name, tool_name))
        return _metadata(*identities)


class FakeSession:
    def __init__(self, rpc: FakeRPC) -> None:
        self.rpc = rpc
        self.disconnect = AsyncMock(side_effect=self._disconnect)
        self.send = AsyncMock(side_effect=AssertionError("send is forbidden"))
        self.send_and_wait = AsyncMock(side_effect=AssertionError("query is forbidden"))
        self.delete = AsyncMock(side_effect=AssertionError("disk deletion is forbidden"))

    async def _disconnect(self) -> None:
        self.rpc.calls.append("disconnect")


def _route(
    *,
    servers: tuple[str, ...] = (SERVER,),
    required: bool = True,
    skills: bool = False,
    available_tools: tuple[str, ...] | None = None,
    excluded_tools: tuple[str, ...] | None = None,
) -> routing.ResourceRoute:
    return routing.ResourceRoute(
        enabled_mcp_servers=servers,
        required_mcp_servers=servers if required else (),
        mcp_tool_allowlists={name: ("search", "read") for name in servers},
        enabled_skills=(SKILL,) if skills else (),
        required_skills=(SKILL,) if skills else (),
        available_tools=available_tools,
        excluded_tools=excluded_tools,
    )


def _assert_no_execution(session: FakeSession) -> None:
    session.send.assert_not_awaited()
    session.send_and_wait.assert_not_awaited()
    session.delete.assert_not_awaited()
    session.rpc.mcp.oauth.login.assert_not_awaited()


def _run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Outer safety only; its cancellation must never count as product timeout."""
    async def guarded() -> Any:
        safety_expired = asyncio.Event()
        alarm = asyncio.get_running_loop().call_later(SAFETY_SECONDS, safety_expired.set)
        try:
            result = await asyncio.wait_for(coroutine, timeout=SAFETY_SECONDS)
            assert not safety_expired.is_set(), "outer safety, not routing, enforced timeout"
            return result
        finally:
            alarm.cancel()

    return asyncio.run(guarded())


async def _must_fail(
    session: FakeSession, route: routing.ResourceRoute, **kwargs: Any
) -> BaseException:
    # The expectation is INSIDE _run's guard, so its TimeoutError cannot pass.
    # TypeError is intentionally excluded, including for the new deadline keyword.
    with pytest.raises((routing.ResourceRoutingError, TimeoutError)) as caught:
        await routing.apply_resource_route(session=session, route=route, **kwargs)
    assert session.disconnect.await_count == 1
    _assert_no_execution(session)
    return caught.value


def _method(rpc: FakeRPC, phase: str) -> AsyncMock:
    group, name = phase.split(".")
    return getattr(getattr(rpc, group), name)


async def _pause(seconds: float) -> None:
    ready = asyncio.Event()
    handle = asyncio.get_running_loop().call_later(seconds, ready.set)
    try:
        await ready.wait()
    finally:
        handle.cancel()


def _delay_response(method: AsyncMock, seconds: float) -> None:
    original: Any = method.side_effect

    async def delayed(*args: Any, **kwargs: Any) -> Any:
        response = await original(*args, **kwargs)
        await _pause(seconds)
        return response

    method.side_effect = delayed


def _advance_response_clock(
    method: AsyncMock, clock: list[float], seconds: float
) -> None:
    """Record the FakeRPC response before advancing routing's logical clock."""
    original: Any = method.side_effect

    async def advances_clock(*args: Any, **kwargs: Any) -> Any:
        response = await original(*args, **kwargs)
        clock[0] += seconds
        return response

    method.side_effect = advances_clock


def _hang(method: AsyncMock) -> asyncio.Event:
    original: Any = method.side_effect
    cancelled = asyncio.Event()

    async def blocked(*args: Any, **kwargs: Any) -> None:
        await original(*args, **kwargs)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    method.side_effect = blocked
    return cancelled


def test_r1_create_initializes_before_connection_and_tool_validation() -> None:
    """FR-TS-13: actual cold-host regression through the existing create API."""
    rpc = FakeRPC()
    session = FakeSession(rpc)
    cold_after_create: list[bool] = []

    async def create_session(**_options: Any) -> FakeSession:
        rpc.calls.append("create_session")
        rpc.initialized = False
        cold_after_create.append(not rpc.initialized)
        return session

    client = SimpleNamespace(create_session=AsyncMock(side_effect=create_session))
    result = _run(
        routing.create_session_from_route(
            client=client, session_options={}, route=_route(skills=True)
        )
    )

    assert result is session
    assert cold_after_create == [True]
    assert rpc.initialized is True
    assert rpc.calls == [
        "create_session",
        "skills.list",
        "tools.initialize_and_validate",
        "mcp.list",
        f"mcp.list_tools:{SERVER}",
        "options.update",
        "tools.get_current_metadata",
    ]
    assert rpc.options.update.await_count == 1
    assert rpc.options.update.await_args.args[0].excluded_tools == [f"mcp:{SERVER}-write"]
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


def test_zero_mcp_preserves_required_skill_validation_and_caller_filter_ack() -> None:
    session = FakeSession(FakeRPC(servers=()))
    route = _route(
        servers=(), skills=True,
        available_tools=("builtin-safe",), excluded_tools=("builtin-denied",),
    )

    applied = _run(routing.apply_resource_route(session=session, route=route))

    assert session.rpc.calls == ["skills.list", "options.update"]
    assert session.rpc.initialized is False
    assert applied.available_tools == ("builtin-safe",)
    update = session.rpc.options.update.await_args.args[0]
    assert update.available_tools == ["builtin-safe"]
    assert update.excluded_tools == ["builtin-denied"]
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize("state", ["missing", "disabled"])
def test_zero_mcp_required_skill_must_be_present_and_enabled(state: str) -> None:
    session = FakeSession(FakeRPC(servers=()))
    session.rpc.skill_response = SimpleNamespace(
        skills=[] if state == "missing" else [SimpleNamespace(name=SKILL, enabled=False)]
    )

    _run(_must_fail(session, _route(servers=(), skills=True)))

    assert session.rpc.calls == ["skills.list", "disconnect"]


@pytest.mark.parametrize(
    "invalid",
    [
        "missing-skills", "null-skills", "mapping-skills", "tuple-skills",
        "missing-name", "nonstring-name", "empty-name", "blank-name",
        "missing-enabled", "null-enabled", "integer-enabled", "string-enabled",
        "duplicate-same", "duplicate-disabled-first", "duplicate-disabled-last",
    ],
)
def test_zero_mcp_required_skill_runtime_schema_is_not_coerced(invalid: str) -> None:
    """FR-TS-13: validate the response, not a lossy name/enabled projection."""
    rpc = FakeRPC(servers=())
    response = rpc.skill_response
    skill = response.skills[0]
    if invalid == "missing-skills":
        del response.skills
    elif invalid == "null-skills":
        response.skills = None
    elif invalid == "mapping-skills":
        response.skills = {SKILL: skill}
    elif invalid == "tuple-skills":
        response.skills = (skill,)
    elif invalid in ("missing-name", "nonstring-name", "empty-name", "blank-name"):
        malformed = SimpleNamespace(enabled=True)
        if invalid != "missing-name":
            malformed.name = {
                "nonstring-name": 1, "empty-name": "", "blank-name": "  "
            }[invalid]
        # Keep the required Skill valid and present: malformed extra entries
        # must not disappear merely because the required name can be found.
        response.skills.append(malformed)
    elif invalid == "missing-enabled":
        del skill.enabled
    elif invalid in ("null-enabled", "integer-enabled", "string-enabled"):
        skill.enabled = {
            "null-enabled": None, "integer-enabled": 1, "string-enabled": "true"
        }[invalid]
    else:
        duplicate = SimpleNamespace(name=SKILL, enabled=invalid == "duplicate-same")
        # Exercise both orders so neither first-wins nor last-wins is valid.
        if invalid == "duplicate-disabled-first":
            response.skills.insert(0, duplicate)
        else:
            response.skills.append(duplicate)
    session = FakeSession(rpc)

    _run(_must_fail(session, _route(servers=(), skills=True)))

    assert rpc.calls == ["skills.list", "disconnect"]


@pytest.mark.parametrize(
    ("index", "state"),
    [(0, "enabled"), (0, "missing"), (1, "missing"), (0, "disabled"), (1, "disabled")],
    ids=["all-enabled", "first-missing", "second-missing", "first-disabled", "second-disabled"],
)
def test_zero_mcp_checks_every_required_skill(index: int, state: str) -> None:
    required_skills = (SKILL, "second-required-skill")
    rpc = FakeRPC(servers=())
    rpc.skill_response = SimpleNamespace(
        skills=[SimpleNamespace(name=name, enabled=True) for name in required_skills]
    )
    if state == "missing":
        del rpc.skill_response.skills[index]
    elif state == "disabled":
        rpc.skill_response.skills[index].enabled = False
    session = FakeSession(rpc)
    route = routing.ResourceRoute(
        enabled_mcp_servers=(),
        required_mcp_servers=(),
        mcp_tool_allowlists={},
        enabled_skills=required_skills,
        required_skills=required_skills,
        available_tools=None,
        excluded_tools=None,
    )

    if state == "enabled":
        _run(routing.apply_resource_route(session=session, route=route))
        assert rpc.calls == ["skills.list"]
        session.disconnect.assert_not_awaited()
        _assert_no_execution(session)
    else:
        _run(_must_fail(session, route))
        assert rpc.calls == ["skills.list", "disconnect"]


def test_zero_mcp_without_skills_or_filters_starts_no_rpc() -> None:
    session = FakeSession(FakeRPC(servers=()))

    applied = _run(routing.apply_resource_route(session=session, route=_route(servers=())))

    assert applied.enabled_mcp_servers == ()
    assert session.rpc.calls == []
    _assert_no_execution(session)


def test_zero_mcp_caller_filters_still_require_successful_ack() -> None:
    session = FakeSession(FakeRPC(servers=()))
    session.rpc.ack = SessionUpdateOptionsResult(success=False)

    _run(_must_fail(session, _route(servers=(), excluded_tools=("builtin-denied",))))

    assert session.rpc.calls == ["options.update", "disconnect"]


def test_pending_is_polled_until_connected_without_auth() -> None:
    rpc = FakeRPC(initialized=True)
    rpc.list_responses = [
        _listing((SERVER, state)) for state in ("pending", "pending", "connected")
    ]
    session = FakeSession(rpc)

    applied = _run(routing.apply_resource_route(session=session, route=_route()))

    assert applied.enabled_mcp_servers == (SERVER,)
    assert rpc.calls == [
        "tools.initialize_and_validate",
        "mcp.list", "mcp.list", "mcp.list",
        f"mcp.list_tools:{SERVER}",
        "options.update",
        "tools.get_current_metadata",
    ]
    rpc.mcp.disable.assert_not_awaited()
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize(
    "state", ["needs-auth", "failed", "disabled", "stopped", "not_configured", "absent"]
)
def test_nonconnected_server_is_disabled_or_stops_required_route(
    state: str, required: bool
) -> None:
    rpc = FakeRPC(servers=(SERVER, PEER), initialized=True)
    states = [] if state == "absent" else [(SERVER, state)]
    rpc.list_responses = [_listing(*states, (PEER, "connected"))]
    session = FakeSession(rpc)
    route = _route(servers=(SERVER, PEER), required=required)

    if required:
        _run(_must_fail(session, route))
        rpc.mcp.list_tools.assert_not_awaited()
        rpc.options.update.assert_not_awaited()
    else:
        applied = _run(routing.apply_resource_route(session=session, route=route))
        assert applied.enabled_mcp_servers == (PEER,)
        assert applied.disabled_mcp_servers == (SERVER,)
        assert [call.args[0].server_name for call in rpc.mcp.disable.await_args_list] == [SERVER]
        assert [call.args[0].server_name for call in rpc.mcp.list_tools.await_args_list] == [PEER]
        assert rpc.options.update.await_count == 1
        session.disconnect.assert_not_awaited()
        _assert_no_execution(session)
    assert rpc.mcp.list.await_count >= 1


def test_required_needs_auth_stops_without_polling() -> None:
    """FR-TS-13 (v3.07): HVE never authenticates, so needs-auth is not re-polled."""
    rpc = FakeRPC(initialized=True)
    rpc.list_responses = [_listing((SERVER, "needs-auth"))]
    session = FakeSession(rpc)

    error = _run(_must_fail(session, _route()))

    assert isinstance(error, routing.ResourceRoutingError)
    assert "requires authentication" in str(error)
    assert rpc.mcp.list.await_count == 1


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("behavior", ["absent", "unsupported", "noop"])
def test_missing_unsupported_or_noop_initialization_cannot_validate_cold_host(
    behavior: str, required: bool
) -> None:
    rpc = FakeRPC()
    if behavior == "absent":
        del rpc.tools.initialize_and_validate
    else:
        rpc.init_behavior = behavior
    session = FakeSession(rpc)

    _run(_must_fail(session, _route(required=required)))

    assert rpc.initialized is False
    rpc.mcp.list_tools.assert_not_awaited()
    rpc.options.update.assert_not_awaited()
    if behavior != "absent":
        assert rpc.tools.initialize_and_validate.await_count == 1
    if behavior == "noop":
        assert rpc.mcp.list.await_count >= 1


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize(
    "invalid",
    [
        "missing-servers", "null-servers", "mapping-servers",
        "duplicate-same", "duplicate-conflicting", "empty-name", "blank-name",
        "missing-status", "unknown-status", "host-none",
    ],
)
def test_invalid_mcp_listing_never_counts_as_connected(invalid: str, required: bool) -> None:
    rpc = FakeRPC(initialized=True)
    response = _listing((SERVER, "connected"))
    if invalid == "missing-servers":
        del response.servers
    elif invalid == "null-servers":
        response.servers = None
    elif invalid == "mapping-servers":
        response.servers = {SERVER: response.servers[0]}
    elif invalid == "duplicate-same":
        response.servers.append(SimpleNamespace(name=SERVER, status=McpServerStatus.CONNECTED))
    elif invalid == "duplicate-conflicting":
        # Last-wins dict conversion must not conceal a conflicting earlier entry.
        response.servers.insert(0, SimpleNamespace(name=SERVER, status=McpServerStatus.FAILED))
    elif invalid in ("empty-name", "blank-name"):
        response.servers.append(
            SimpleNamespace(name="" if invalid == "empty-name" else "  ", status=McpServerStatus.CONNECTED)
        )
    elif invalid == "missing-status":
        del response.servers[0].status
    elif invalid == "unknown-status":
        response.servers[0].status = SimpleNamespace(value="unexpected-status")
    else:
        # This Fake has a known initialized host despite the malformed listing.
        # FR-TS-13 permits optional continuation only after disable succeeds.
        response.host = None
    rpc.list_responses = [response]
    session = FakeSession(rpc)
    route = _route(required=required)

    if required:
        _run(_must_fail(session, route))
    else:
        applied = _run(routing.apply_resource_route(session=session, route=route))
        assert applied.enabled_mcp_servers == ()
        assert applied.disabled_mcp_servers == (SERVER,)
        assert [call.args[0].server_name for call in rpc.mcp.disable.await_args_list] == [SERVER]
        session.disconnect.assert_not_awaited()
        _assert_no_execution(session)
    rpc.mcp.list_tools.assert_not_awaited()
    rpc.options.update.assert_not_awaited()


def test_connected_required_server_still_needs_every_exact_allowlisted_tool() -> None:
    rpc = FakeRPC(initialized=True)
    rpc.tool_responses[SERVER] = SimpleNamespace(tools=[SimpleNamespace(name="read")])
    session = FakeSession(rpc)

    error = _run(_must_fail(session, _route()))

    assert SERVER in str(error)
    assert "search" in str(error)
    rpc.mcp.disable.assert_not_awaited()
    rpc.options.update.assert_not_awaited()


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("duplicate_name", ["search", "write"], ids=["allowlisted", "excluded"])
def test_duplicate_tool_name_is_invalid_even_with_every_allowlisted_tool(
    duplicate_name: str, required: bool
) -> None:
    """FR-TS-13: exact tool names must be unique within each server response."""
    rpc = FakeRPC(servers=(SERVER, PEER), initialized=True)
    rpc.tool_responses[SERVER].tools.append(SimpleNamespace(name=duplicate_name))
    session = FakeSession(rpc)
    route = _route(servers=(SERVER, PEER), required=required)
    names = [tool.name for tool in rpc.tool_responses[SERVER].tools]
    # Missing allowlisted tools must not accidentally explain this failure.
    assert set(route.mcp_tool_allowlists[SERVER]).issubset(names)
    assert names.count(duplicate_name) == 2

    if required:
        _run(_must_fail(session, route))
        rpc.mcp.disable.assert_not_awaited()
        rpc.options.update.assert_not_awaited()
        assert [call.args[0].server_name for call in rpc.mcp.list_tools.await_args_list] == [SERVER]
    else:
        applied = _run(routing.apply_resource_route(session=session, route=route))
        assert applied.enabled_mcp_servers == (PEER,)
        assert applied.disabled_mcp_servers == (SERVER,)
        assert [call.args[0].server_name for call in rpc.mcp.disable.await_args_list] == [SERVER]
        assert [call.args[0].server_name for call in rpc.mcp.list_tools.await_args_list] == [SERVER, PEER]
        rpc.options.update.assert_awaited_once()
        assert rpc.options.update.await_args.args[0].excluded_tools == [f"mcp:{PEER}-write"]
        session.disconnect.assert_not_awaited()
        _assert_no_execution(session)


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_pending_server_at_the_reserve_is_disabled_only_when_optional(
    required: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-09-30 改訂: optional の pending は共有 deadline の予約分の内側で無効化して続ける。

    required の pending は従来どおり失敗し、無効化の予算を新たに足さない。
    """
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.2, raising=False)
    rpc = FakeRPC(initialized=True)
    rpc.list_responses = [_listing((SERVER, "pending"))]
    session = FakeSession(rpc)

    if required:
        _run(_must_fail(session, _route(required=True)))
        rpc.mcp.disable.assert_not_awaited()
        return
    route = _run(routing.apply_resource_route(session=session, route=_route(required=False)))
    assert SERVER in route.disabled_mcp_servers
    assert rpc.mcp.disable.await_count == 1
    rpc.mcp.list_tools.assert_not_awaited()
    _assert_no_execution(session)


def test_expired_internal_budget_starts_no_new_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.0, raising=False)
    session = FakeSession(FakeRPC(initialized=True))

    _run(_must_fail(session, _route(skills=True)))

    assert session.rpc.calls == ["disconnect"]


@pytest.mark.parametrize("boundary", ["expired", "shorter", "cannot-extend"])
def test_deadline_keyword_contract_uses_earlier_absolute_deadline(
    boundary: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-TS-13 new keyword contract: TypeError RED is NOT evidence of R1."""
    internal = 0.01 if boundary == "cannot-extend" else 0.2
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", internal, raising=False)
    rpc = FakeRPC(servers=())
    session = FakeSession(rpc)
    if boundary != "expired":
        _delay_response(rpc.skills.list, 0.04)

    async def scenario() -> None:
        remaining = {"expired": -1.0, "shorter": 0.01, "cannot-extend": 0.2}[boundary]
        await _must_fail(
            session, _route(servers=(), skills=True), deadline=time.monotonic() + remaining
        )
        if boundary == "expired":
            assert rpc.calls == ["disconnect"]
        else:
            assert rpc.calls == ["skills.list", "disconnect"]

    _run(scenario())


@pytest.mark.parametrize("phases", ["skills-and-initialize", "two-servers"])
def test_one_shared_budget_is_not_reset_per_rpc_or_server(
    phases: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(routing, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 40.0, raising=False)
    servers = (SERVER, PEER) if phases == "two-servers" else (SERVER,)
    rpc = FakeRPC(servers=servers, initialized=True)
    session = FakeSession(rpc)
    if phases == "two-servers":
        _advance_response_clock(rpc.mcp.list_tools, clock, 25.0)
        timed_phases = tuple(f"mcp.list_tools:{name}" for name in servers)
    else:
        _advance_response_clock(rpc.skills.list, clock, 25.0)
        _advance_response_clock(rpc.tools.initialize_and_validate, clock, 25.0)
        timed_phases = ("skills.list", "tools.initialize_and_validate")

    error = _run(_must_fail(session, _route(servers=servers, skills=phases != "two-servers")))

    assert isinstance(error, TimeoutError)
    assert clock[0] == 50.0
    assert [(name, timeout) for name, timeout in rpc.timeouts if name in timed_phases] == [
        (timed_phases[0], 40.0), (timed_phases[1], 15.0),
    ]
    # An earlier scheduling overrun must not pass as proof of a shared budget.
    if phases == "two-servers":
        assert [call.args[0].server_name for call in rpc.mcp.list_tools.await_args_list] == list(servers)
    else:
        rpc.skills.list.assert_awaited_once()
        rpc.tools.initialize_and_validate.assert_awaited_once()
        rpc.mcp.list.assert_not_awaited()
    rpc.options.update.assert_not_awaited()
    rpc.mcp.disable.assert_not_awaited()


@pytest.mark.parametrize("last_phase", ["mcp.list_tools", "options.update"])
def test_connected_near_deadline_must_finish_tool_validation_and_ack(
    last_phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(routing, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 40.0, raising=False)
    rpc = FakeRPC(initialized=True)
    _advance_response_clock(rpc.mcp.list, clock, 25.0)
    _advance_response_clock(_method(rpc, last_phase), clock, 25.0)
    session = FakeSession(rpc)

    error = _run(_must_fail(session, _route()))

    assert isinstance(error, TimeoutError)
    assert clock[0] == 50.0
    timed_phases = (
        "mcp.list", f"mcp.list_tools:{SERVER}" if last_phase == "mcp.list_tools" else last_phase,
    )
    assert [(name, timeout) for name, timeout in rpc.timeouts if name in timed_phases] == [
        (timed_phases[0], 40.0), (timed_phases[1], 15.0),
    ]
    # Require the intended late phase, not just any earlier timeout.
    rpc.mcp.list.assert_awaited_once()
    _method(rpc, last_phase).assert_awaited_once()
    if last_phase == "mcp.list_tools":
        rpc.options.update.assert_not_awaited()
    else:
        rpc.mcp.list_tools.assert_awaited_once()
    rpc.mcp.disable.assert_not_awaited()


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("phase", RPC_PHASES)
def test_each_hanging_readiness_rpc_times_out_inside_the_shared_budget(
    phase: str, required: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.01, raising=False)
    rpc = FakeRPC(initialized=True)
    cancelled = _hang(_method(rpc, phase))
    session = FakeSession(rpc)

    async def scenario() -> None:
        await _must_fail(session, _route(required=required, skills=phase == "skills.list"))
        assert cancelled.is_set(), "the product must cancel the stalled RPC before returning"
        rpc.mcp.disable.assert_not_awaited()

    _run(scenario())


def test_optional_disable_hang_is_inside_the_same_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.01, raising=False)
    rpc = FakeRPC(initialized=True)
    rpc.mcp.list_tools.side_effect = RuntimeError("offline tool-list failure")
    cancelled = _hang(rpc.mcp.disable)
    session = FakeSession(rpc)

    async def scenario() -> None:
        await _must_fail(session, _route(required=False))
        assert rpc.mcp.disable.await_count == 1
        assert cancelled.is_set()
        rpc.options.update.assert_not_awaited()

    _run(scenario())


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("phase", RPC_PHASES)
def test_cancelled_error_is_cleaned_up_and_reraised_not_optional_failure(
    phase: str, required: bool
) -> None:
    rpc = FakeRPC(initialized=True)
    _method(rpc, phase).side_effect = asyncio.CancelledError("offline cancellation")
    session = FakeSession(rpc)

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            await routing.apply_resource_route(
                session=session, route=_route(required=required, skills=phase == "skills.list")
            )
        assert session.disconnect.await_count == 1
        rpc.mcp.disable.assert_not_awaited()
        _assert_no_execution(session)

    _run(scenario())


@pytest.mark.parametrize("phase", (*RPC_PHASES, "mcp.disable"))
def test_late_rpc_response_after_cancellation_never_returns_success(
    phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.01, raising=False)
    rpc = FakeRPC(initialized=True)
    if phase == "mcp.disable":
        rpc.mcp.list_tools.side_effect = RuntimeError("offline tool-list failure")
    method = _method(rpc, phase)
    original: Any = method.side_effect
    late_reply = asyncio.Event()
    calls_at_late_reply: list[str] = []

    async def returns_after_cancel(*args: Any, **kwargs: Any) -> Any:
        response = await original(*args, **kwargs)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Deliberately emulate a late transport reply, NOT successful cancellation.
            calls_at_late_reply[:] = rpc.calls
            late_reply.set()
            return response

    method.side_effect = returns_after_cancel
    session = FakeSession(rpc)

    async def scenario() -> None:
        await _must_fail(
            session, _route(required=phase != "mcp.disable", skills=phase == "skills.list")
        )
        assert late_reply.is_set()
        assert rpc.calls == [*calls_at_late_reply, "disconnect"]
        assert rpc.options.update.await_count <= 1
        if phase != "mcp.disable":
            rpc.mcp.disable.assert_not_awaited()
        else:
            assert rpc.mcp.disable.await_count == 1

    _run(scenario())


def test_disconnect_has_its_own_bounded_cleanup_timeout() -> None:
    session = FakeSession(FakeRPC(servers=()))
    session.rpc.skill_response = SimpleNamespace(skills=[])
    cancelled = _hang(session.disconnect)

    async def scenario() -> None:
        await _must_fail(session, _route(servers=(), skills=True))
        assert cancelled.is_set(), "disconnect must not wait for the outer safety guard"
        assert session.rpc.calls == ["skills.list", "disconnect"]

    _run(scenario())


def test_cleanup_can_finish_after_routing_deadline_without_new_resource_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(routing, "_ROUTING_CLEANUP_TIMEOUT_SECONDS", 0.1, raising=False)
    rpc = FakeRPC(servers=())
    cancelled = _hang(rpc.skills.list)
    session = FakeSession(rpc)
    cleanup_finished = asyncio.Event()

    async def disconnect() -> None:
        rpc.calls.append("disconnect")
        await _pause(0.025)
        cleanup_finished.set()

    session.disconnect.side_effect = disconnect

    async def scenario() -> None:
        await _must_fail(session, _route(servers=(), skills=True))
        assert cancelled.is_set()
        assert cleanup_finished.is_set(), "cleanup gets a separate budget after apply expires"
        assert rpc.calls == ["skills.list", "disconnect"]

    _run(scenario())


def test_post_filter_metadata_refreshes_once_when_selected_identity_is_missing() -> None:
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [
        ToolsGetCurrentMetadataResult(tools=[]),
        _metadata((SERVER, "search"), (SERVER, "read")),
    ]
    session = FakeSession(rpc)

    applied = _run(routing.apply_resource_route(session=session, route=_route()))

    assert applied.enabled_mcp_servers == (SERVER,)
    assert rpc.calls == [
        "tools.initialize_and_validate",
        "mcp.list",
        f"mcp.list_tools:{SERVER}",
        "options.update",
        "tools.get_current_metadata",
        "tools.initialize_and_validate",
        "tools.get_current_metadata",
    ]
    assert rpc.tools.initialize_and_validate.await_count == 2
    assert rpc.tools.get_current_metadata.await_count == 2
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize("deferred", [False, True], ids=["eager", "deferred"])
def test_post_filter_ready_or_deferred_metadata_skips_refresh(deferred: bool) -> None:
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [
        _metadata((SERVER, "search"), (SERVER, "read"), deferred=deferred)
    ]
    session = FakeSession(rpc)

    applied = _run(routing.apply_resource_route(session=session, route=_route()))

    assert applied.enabled_mcp_servers == (SERVER,)
    assert rpc.tools.initialize_and_validate.await_count == 1
    assert rpc.tools.get_current_metadata.await_count == 1
    assert rpc.calls[-1] == "tools.get_current_metadata"
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


def test_post_filter_metadata_uses_effective_caller_intersection() -> None:
    selected_id = f"mcp:{SERVER}-search"
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [_metadata((SERVER, "search"))]
    session = FakeSession(rpc)
    route = _route(
        available_tools=("builtin-safe", selected_id),
        excluded_tools=(f"mcp:{SERVER}-read",),
    )

    applied = _run(routing.apply_resource_route(session=session, route=route))

    assert applied.enabled_mcp_servers == (SERVER,)
    assert rpc.tools.initialize_and_validate.await_count == 1
    assert rpc.tools.get_current_metadata.await_count == 1
    assert rpc.last_update is not None
    assert rpc.last_update.available_tools == ["builtin-safe", selected_id]
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize(
    ("available_tools", "excluded_tools", "identities"),
    [
        (("mcp:*",), None, ((SERVER, "search"), (SERVER, "read"))),
        (None, ("mcp:*",), ()),
    ],
    ids=["available-source-wildcard", "excluded-source-wildcard"],
)
def test_post_filter_metadata_honors_sdk_mcp_source_wildcards(
    available_tools: tuple[str, ...] | None,
    excluded_tools: tuple[str, ...] | None,
    identities: tuple[tuple[str, str], ...],
) -> None:
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [_metadata(*identities)]
    session = FakeSession(rpc)

    applied = _run(
        routing.apply_resource_route(
            session=session,
            route=_route(
                required=False,
                available_tools=available_tools,
                excluded_tools=excluded_tools,
            ),
        )
    )

    assert applied.enabled_mcp_servers == (SERVER,)
    assert rpc.tools.initialize_and_validate.await_count == 1
    assert rpc.tools.get_current_metadata.await_count == 1
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


def test_post_filter_metadata_refresh_reuses_the_shared_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(routing, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 40.0, raising=False)
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [
        ToolsGetCurrentMetadataResult(tools=[]),
        _metadata((SERVER, "search"), (SERVER, "read")),
    ]
    _advance_response_clock(rpc.options.update, clock, 25.0)
    session = FakeSession(rpc)

    _run(routing.apply_resource_route(session=session, route=_route()))

    assert clock[0] == 25.0
    assert [
        (name, timeout)
        for name, timeout in rpc.timeouts
        if name in ("tools.get_current_metadata", "tools.initialize_and_validate")
    ] == [
        ("tools.initialize_and_validate", 40.0),
        ("tools.get_current_metadata", 15.0),
        ("tools.initialize_and_validate", 15.0),
        ("tools.get_current_metadata", 15.0),
    ]
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(tools={}),
        SimpleNamespace(
            tools=[SimpleNamespace(mcp_server_name=SERVER, mcp_tool_name=None)]
        ),
        _metadata((SERVER, "search"), (SERVER, "search"), (SERVER, "read")),
        _metadata((SERVER, "search"), (SERVER, "read"), (PEER, "search")),
    ],
    ids=["non-list", "one-sided", "duplicate", "unselected"],
)
def test_post_filter_metadata_rejects_malformed_duplicate_or_unselected_identity(
    response: Any, request: pytest.FixtureRequest
) -> None:
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [response]
    session = FakeSession(rpc)

    _run(_must_fail(session, _route()))

    # FR-TS-13 (v3.07): only an unselected identity earns the one refresh.
    refreshes = 1 if request.node.callspec.id == "unselected" else 0
    assert rpc.tools.initialize_and_validate.await_count == 1 + refreshes
    assert rpc.tools.get_current_metadata.await_count == 1 + refreshes
    assert rpc.calls[-1] == "disconnect"


def test_post_filter_metadata_refreshes_once_for_a_disabled_optional_server() -> None:
    """FR-TS-13 (v3.07): metadata keeps a disabled server until reinitialization."""
    rpc = FakeRPC(servers=(SERVER, PEER), initialized=True)
    rpc.tool_responses[PEER] = SimpleNamespace(tools=[SimpleNamespace(name="write")])
    rpc.metadata_responses = [
        _metadata((PEER, "read"), (PEER, "search"), (SERVER, "read"), (SERVER, "search")),
        _metadata((SERVER, "read"), (SERVER, "search")),
    ]
    session = FakeSession(rpc)

    applied = _run(
        routing.apply_resource_route(
            session=session, route=_route(servers=(SERVER, PEER), required=False)
        )
    )

    assert applied.enabled_mcp_servers == (SERVER,)
    assert applied.disabled_mcp_servers == (PEER,)
    assert rpc.tools.initialize_and_validate.await_count == 2
    assert rpc.tools.get_current_metadata.await_count == 2
    assert rpc.options.update.await_count == 1
    session.disconnect.assert_not_awaited()
    _assert_no_execution(session)


@pytest.mark.parametrize("mode", ["required", "optional", "caller-filter"])
def test_post_filter_metadata_missing_after_refresh_follows_required_optional_boundary(
    mode: str,
) -> None:
    rpc = FakeRPC(initialized=True)
    rpc.metadata_responses = [
        ToolsGetCurrentMetadataResult(tools=[]),
        ToolsGetCurrentMetadataResult(tools=[]),
    ]
    session = FakeSession(rpc)
    route = _route(
        required=mode == "required",
        available_tools=(f"mcp:{SERVER}-search",) if mode == "caller-filter" else None,
    )

    if mode == "optional":
        applied = _run(routing.apply_resource_route(session=session, route=route))
        assert applied.enabled_mcp_servers == ()
        assert applied.disabled_mcp_servers == (SERVER,)
        assert applied.excluded_tools is None
        assert [
            call.args[0].server_name for call in rpc.mcp.disable.await_args_list
        ] == [SERVER]
        session.disconnect.assert_not_awaited()
        _assert_no_execution(session)
    else:
        _run(_must_fail(session, route))
        rpc.mcp.disable.assert_not_awaited()
    assert rpc.tools.initialize_and_validate.await_count == 2
    assert rpc.tools.get_current_metadata.await_count == 2


@pytest.mark.parametrize("state", ["needs-auth", "failed"])
def test_optional_server_that_blocks_initialization_is_disabled_within_the_budget(
    state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-09-30 bugfix: an optional server needing auth must not exhaust the shared budget."""
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(routing, "_OPTIONAL_INIT_BUDGET_SECONDS", 0.05, raising=False)
    rpc = FakeRPC(servers=("workiq", SERVER), initialized=True)
    rpc.list_responses = [_listing(("workiq", state), (SERVER, "connected"))]
    first_init = {"done": False}
    original = rpc.tools.initialize_and_validate.side_effect

    async def blocks_until_disabled(*args: Any, **kwargs: Any) -> Any:
        if not first_init["done"]:
            first_init["done"] = True
            await original(*args, **kwargs)
            await asyncio.Event().wait()
        return await original(*args, **kwargs)

    rpc.tools.initialize_and_validate.side_effect = blocks_until_disabled
    session = FakeSession(rpc)

    async def scenario() -> None:
        route = await routing.apply_resource_route(
            session=session, route=_route(servers=("workiq", SERVER), required=False)
        )
        assert "workiq" in route.disabled_mcp_servers
        assert SERVER in route.enabled_mcp_servers
        assert "mcp.disable:workiq" in rpc.calls
        _assert_no_execution(session)

    _run(scenario())


def test_initialization_hang_with_all_servers_connected_still_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bounded optional init never treats a bare hang as readiness evidence."""
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 0.3, raising=False)
    monkeypatch.setattr(routing, "_OPTIONAL_INIT_BUDGET_SECONDS", 0.05, raising=False)
    rpc = FakeRPC(initialized=True)
    _hang(rpc.tools.initialize_and_validate)
    session = FakeSession(rpc)

    async def scenario() -> None:
        await _must_fail(session, _route(required=False))
        rpc.mcp.disable.assert_not_awaited()

    _run(scenario())


def test_pending_optional_server_is_disabled_once_it_needs_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-09-30 bugfix: 初期化の打ち切り時に pending でも、共有 deadline 内で needs-auth になれば無効化して続ける。"""
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(routing, "_OPTIONAL_INIT_BUDGET_SECONDS", 0.05, raising=False)
    rpc = FakeRPC(servers=("workiq", SERVER), initialized=True)
    rpc.list_responses = [
        _listing(("workiq", "pending"), (SERVER, "connected")),
        _listing(("workiq", "pending"), (SERVER, "connected")),
        _listing(("workiq", "needs-auth"), (SERVER, "connected")),
    ]
    first_init = {"done": False}
    original = rpc.tools.initialize_and_validate.side_effect

    async def blocks_until_disabled(*args: Any, **kwargs: Any) -> Any:
        if not first_init["done"]:
            first_init["done"] = True
            await original(*args, **kwargs)
            await asyncio.Event().wait()
        return await original(*args, **kwargs)

    rpc.tools.initialize_and_validate.side_effect = blocks_until_disabled
    session = FakeSession(rpc)

    async def scenario() -> None:
        route = await routing.apply_resource_route(
            session=session, route=_route(servers=("workiq", SERVER), required=False)
        )
        assert "workiq" in route.disabled_mcp_servers
        assert "mcp.disable:workiq" in rpc.calls

    _run(scenario())


def test_slow_initialization_with_connected_servers_gets_the_rest_of_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-09-30 bugfix: 初期化が打ち切り上限より遅いだけなら、残りの共有 deadline で待ち直す。"""
    monkeypatch.setattr(routing, "_ROUTING_TIMEOUT_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(routing, "_OPTIONAL_INIT_BUDGET_SECONDS", 0.05, raising=False)
    rpc = FakeRPC(initialized=True)
    original = rpc.tools.initialize_and_validate.side_effect
    calls = {"n": 0}

    async def slow_first(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        response = await original(*args, **kwargs)
        if calls["n"] == 1:
            await _pause(0.2)
        return response

    rpc.tools.initialize_and_validate.side_effect = slow_first
    session = FakeSession(rpc)
    route = _run(routing.apply_resource_route(session=session, route=_route(required=False)))
    assert route.enabled_mcp_servers == (SERVER,)
    rpc.mcp.disable.assert_not_awaited()
    _assert_no_execution(session)
