"""Adversarial RED contracts for SDK resource routing (FR-TS-13)."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Mapping

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
from hve.toolsearch.policy import ToolSearchPolicy
from hve.workflow_registry import list_workflows

ROUTING_MODULE = "hve.toolsearch.resource_routing"
SE_WORKFLOWS = {"aas", "ada", "aad-web", "asdw-web", "adfd", "adfdv", "aag", "aagd", "aar", "adoc"}


def _router() -> Any:
    return importlib.import_module(ROUTING_MODULE)


def _dc_type(required: set[str]) -> type[Any]:
    module = importlib.import_module("hve.toolsearch.resource_inventory")
    for value in vars(module).values():
        if isinstance(value, type) and dataclasses.is_dataclass(value):
            if required <= {field.name for field in dataclasses.fields(value)}:
                return value
    raise AssertionError(f"resource_inventory dataclass missing {sorted(required)}")


def _resource(kind: str, name: str, *, enabled: bool = True) -> Any:
    cls = _dc_type({"kind", "name", "enabled", "source_kind"})
    values = {"kind": kind, "name": name, "enabled": enabled, "source_kind": "user", "plugin_marketplace": None, "owner_plugin": None, "plugin_version": None, "description": f"{name} description" if kind == "skill" else None}
    return cls(**{field.name: values.get(field.name) for field in dataclasses.fields(cls)})


def _snapshot(**overrides: Any) -> Any:
    cls = _dc_type({"plugin_state", "mcp_state", "skill_state", "skill_ownership_state", "plugins", "mcp_servers", "skills"})
    values = {
        "plugin_state": "ready", "mcp_state": "ready", "skill_state": "ready", "skill_ownership_state": "ready", "plugins": (),
        "mcp_servers": tuple(_resource("mcp_server", name, enabled=name != "disabled-mcp") for name in ("knowledge-mcp", "engineering-mcp", "shared-mcp", "unknown-mcp", "disabled-mcp", "required-empty-mcp", "optional-empty-mcp")),
        "skills": tuple(_resource("skill", name, enabled=name != "disabled-skill") for name in ("knowledge-skill", "engineering-skill", "shared-skill", "unknown-skill", "disabled-skill")),
    }
    values.update(overrides)
    return cls(**{field.name: values.get(field.name) for field in dataclasses.fields(cls)})


def _policy(
    *,
    required_mcp_servers_by_skill: Mapping[str, list[str]] | None = None,
) -> ToolSearchPolicy:
    return ToolSearchPolicy.from_dict({
        "version": 1, "limit": 5, "max_limit": 10, "tau": 0.4,
        "field_weights": {"name": 3.0, "additional_search_text": 2.5, "description": 2.0, "arg_terms": 1.0},
        "pins": {}, "additional_search_text": {}, "step_overrides": {},
        "resource_classifications": {
            "plugins": {},
            "mcp_servers": {"knowledge-mcp": "knowledge", "engineering-mcp": "software-engineering", "shared-mcp": "both", "unknown-mcp": "unclassified", "disabled-mcp": "both", "required-empty-mcp": "knowledge", "optional-empty-mcp": "knowledge"},
            "skills": {"knowledge-skill": "knowledge", "engineering-skill": "software-engineering", "shared-skill": "both", "unknown-skill": "unclassified", "disabled-skill": "both"},
        },
        "knowledge_tool_allowlists": {"knowledge-mcp": ["search", "read"], "shared-mcp": ["lookup"], "disabled-mcp": ["never"], "required-empty-mcp": [], "optional-empty-mcp": []},
        "software_engineering_tool_allowlists": {"engineering-mcp": ["inspect"], "shared-mcp": ["mutate"], "disabled-mcp": ["never"]},
        "required_mcp_servers_by_skill": dict(required_mcp_servers_by_skill or {}),
    })


def _build(workflow_id: str, *, snapshot: Any | None = None, **kwargs: Any) -> Any:
    return _router().build_resource_route(snapshot=snapshot or _snapshot(), policy=_policy(), workflow_id=workflow_id, **kwargs)


def _get(route: Any, name: str) -> Any:
    return route[name] if isinstance(route, Mapping) else getattr(route, name)


def _workflow_ids() -> set[str]:
    return {str(getattr(item, "id", getattr(item, "workflow_id", item))) for item in list_workflows()}


def test_workflow_id_routes_all_13_knowledge_exact_10_engineering_and_unknown_fails() -> None:
    assert len(_workflow_ids()) == 13
    for workflow_id in _workflow_ids():
        route = _build(workflow_id)
        assert "knowledge-mcp" in _get(route, "enabled_mcp_servers")
        assert "knowledge-skill" in _get(route, "enabled_skills")
        assert ("engineering-mcp" in _get(route, "enabled_mcp_servers")) is (workflow_id in SE_WORKFLOWS)
        assert ("engineering-skill" in _get(route, "enabled_skills")) is (workflow_id in SE_WORKFLOWS)
        assert "unknown-mcp" in _get(route, "disabled_mcp_servers")
        assert "unknown-skill" in _get(route, "disabled_skills")
    with pytest.raises(_router().ResourceRoutingError, match="workflow"):
        _build("unknown-workflow")


def test_both_uses_knowledge_allowlist_or_workflow_specific_union() -> None:
    assert set(_get(_build("ard"), "mcp_tool_allowlists")["shared-mcp"]) == {"lookup"}
    assert set(_get(_build("aas"), "mcp_tool_allowlists")["shared-mcp"]) == {"lookup", "mutate"}


@pytest.mark.parametrize(("key", "missing", "disabled"), [("required_mcp_servers", "missing-mcp", "disabled-mcp"), ("required_skills", "missing-skill", "disabled-skill")])
def test_required_mcp_and_skill_missing_or_disabled_fail_closed(key: str, missing: str, disabled: str) -> None:
    for name in (missing, disabled):
        with pytest.raises(_router().ResourceRoutingError, match=name):
            _build("aas", **{key: [name]})


def test_required_skill_outranks_classification_instead_of_failing_closed() -> None:
    """FR-TS-13 / FR-CLI-76: required Skill は分類より優先して候補へ残る。"""
    route = _build("aas", required_skills=["unknown-skill"])

    assert "unknown-skill" in _get(route, "enabled_skills")
    assert "unknown-skill" not in _get(route, "disabled_skills")

    # Knowledge 専用 Workflow でも同じ優先順位とし、未分類の非 required Skill は除外を維持する。
    knowledge_route = _build("ard", required_skills=["engineering-skill"])
    assert "engineering-skill" in _get(knowledge_route, "enabled_skills")
    assert "unknown-skill" in _get(knowledge_route, "disabled_skills")


@pytest.mark.parametrize(("key", "missing", "disabled", "field"), [("optional_mcp_servers", "missing-mcp", "disabled-mcp", "enabled_mcp_servers"), ("optional_skills", "missing-skill", "disabled-skill", "enabled_skills")])
def test_optional_mcp_and_skill_missing_or_disabled_are_excluded(key: str, missing: str, disabled: str, field: str) -> None:
    route = _build("aas", **{key: [missing, disabled]})
    assert missing not in _get(route, field)
    assert disabled not in _get(route, field)


def test_empty_allowlist_is_required_failure_and_optional_exclusion() -> None:
    with pytest.raises(_router().ResourceRoutingError, match="required-empty-mcp"):
        _build("ard", required_mcp_servers=["required-empty-mcp"])
    route = _build("ard", optional_mcp_servers=["optional-empty-mcp"])
    assert "optional-empty-mcp" not in _get(route, "enabled_mcp_servers")
    assert "optional-empty-mcp" in _get(route, "disabled_mcp_servers")


@pytest.mark.parametrize("field", ["mcp_state", "skill_state"])
def test_unverified_mcp_or_skill_fails_before_session(field: str) -> None:
    with pytest.raises(_router().ResourceRoutingError, match="unverified"):
        _build("ard", snapshot=_snapshot(**{field: "unverified"}))


def test_unverified_plugin_and_ownership_keep_only_exact_classifications() -> None:
    route = _build("ard", snapshot=_snapshot(plugin_state="unverified", skill_ownership_state="unverified"))
    assert set(_get(route, "enabled_mcp_servers")) == {"knowledge-mcp", "shared-mcp"}
    assert set(_get(route, "enabled_skills")) == {"knowledge-skill", "shared-skill"}


class FakeOptions:
    def __init__(self, fail: bool = False, *, response: Any = ...) -> None:
        self.fail = fail
        self.response = response
        self.updates: list[SessionUpdateOptionsParams] = []

    async def update(
        self, request: SessionUpdateOptionsParams, *, timeout: float | None = None
    ) -> SessionUpdateOptionsResult:
        assert type(request) is SessionUpdateOptionsParams
        self.updates.append(request)
        if self.fail:
            raise RuntimeError("update failed")
        if self.response is ...:
            return SessionUpdateOptionsResult(success=True)
        # Decode at the RPC boundary, including malformed responses, as SDK 1.0.11 does.
        return SessionUpdateOptionsResult.from_dict(self.response)


class FakeMCP:
    def __init__(
        self,
        tools: list[str] | Mapping[str, list[str]],
        list_fail: bool | set[str] = False,
        disable_fail: bool = False,
    ) -> None:
        self.tools, self.list_fail, self.disable_fail = tools, list_fail, disable_fail
        self.lists: list[MCPListToolsRequest] = []
        self.disables: list[MCPDisableRequest] = []
        self.list_calls = 0

    async def list(self, *, timeout: float | None = None) -> Any:
        self.list_calls += 1
        names = tuple(self.tools) if isinstance(self.tools, Mapping) else ("knowledge-mcp", "shared-mcp")
        return SimpleNamespace(
            servers=[
                SimpleNamespace(name=name, status=McpServerStatus.CONNECTED)
                for name in names
            ],
            host=SimpleNamespace(
                clients=list(names),
                disabled_servers=[],
                failed_servers={},
                filtered_servers=[],
                mcp3_p_enabled=True,
                needs_auth_servers={},
                pending_connections=[],
            ),
        )

    async def list_tools(
        self, request: MCPListToolsRequest, *, timeout: float | None = None
    ) -> Any:
        assert type(request) is MCPListToolsRequest
        self.lists.append(request)
        if self.list_fail is True or (
            isinstance(self.list_fail, set)
            and request.server_name in self.list_fail
        ):
            raise RuntimeError("list failed")
        tools = (
            self.tools.get(request.server_name, [])
            if isinstance(self.tools, Mapping)
            else self.tools
        )
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in tools])

    async def disable(
        self, request: MCPDisableRequest, *, timeout: float | None = None
    ) -> None:
        assert type(request) is MCPDisableRequest
        self.disables.append(request)
        if self.disable_fail:
            raise RuntimeError("disable failed")


class FakeSkills:
    def __init__(
        self,
        skills: list[tuple[str, bool]] | None = None,
        fail: bool = False,
    ) -> None:
        self.skills = skills or []
        self.fail = fail
        self.list_calls = 0

    async def list(self, *, timeout: float | None = None) -> Any:
        self.list_calls += 1
        if self.fail:
            raise RuntimeError("skill list failed")
        return SimpleNamespace(
            skills=[SimpleNamespace(name=name, enabled=enabled) for name, enabled in self.skills]
        )


class FakeTools:
    def __init__(self, mcp: FakeMCP, options: FakeOptions) -> None:
        self.mcp = mcp
        self.options = options
        self.initialize_calls = 0
        self.metadata_calls = 0

    async def initialize_and_validate(
        self, *, timeout: float | None = None
    ) -> ToolsInitializeAndValidateResult:
        self.initialize_calls += 1
        return ToolsInitializeAndValidateResult()

    async def get_current_metadata(
        self, *, timeout: float | None = None
    ) -> ToolsGetCurrentMetadataResult:
        self.metadata_calls += 1
        disabled = {request.server_name for request in self.mcp.disables}
        update = self.options.updates[-1] if self.options.updates else None
        available = None if update is None or update.available_tools is None else set(update.available_tools)
        excluded = set(() if update is None else update.excluded_tools or ())
        metadata = []
        server_names = tuple(dict.fromkeys(request.server_name for request in self.mcp.lists))
        for server_name in server_names:
            if server_name in disabled:
                continue
            tool_names = (
                self.mcp.tools.get(server_name, [])
                if isinstance(self.mcp.tools, Mapping)
                else self.mcp.tools
            )
            for tool_name in tool_names:
                tool_id = f"mcp:{server_name}-{tool_name}"
                if available is not None and tool_id not in available:
                    continue
                if tool_id in excluded:
                    continue
                metadata.append(
                    CurrentToolMetadata(
                        description="offline MCP tool",
                        name=f"mcp__{server_name}__{tool_name}",
                        mcp_server_name=server_name,
                        mcp_tool_name=tool_name,
                        namespaced_name=tool_id,
                    )
                )
        return ToolsGetCurrentMetadataResult(tools=metadata)


class FakeSession:
    def __init__(
        self,
        mcp: FakeMCP,
        options: FakeOptions,
        skills: FakeSkills | None = None,
    ) -> None:
        tools = FakeTools(mcp, options)
        self.rpc = SimpleNamespace(
            mcp=mcp, options=options, skills=skills or FakeSkills(), tools=tools
        )
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


def _one_server_route(required: bool, **filters: Any) -> Any:
    snapshot = _snapshot(mcp_servers=(_resource("mcp_server", "knowledge-mcp"),), skills=())
    if required:
        filters["required_mcp_servers"] = ["knowledge-mcp"]
    return _build("ard", snapshot=snapshot, **filters)


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("failure", ["list", "missing", "update"])
def test_list_missing_tool_and_update_failures_split_required_optional(required: bool, failure: str) -> None:
    route = _one_server_route(required)
    mcp = FakeMCP(["read"] if failure == "missing" else ["search", "read"], failure == "list")
    session = FakeSession(mcp, FakeOptions(failure == "update"))
    if required:
        with pytest.raises(_router().ResourceRoutingError, match="knowledge-mcp"):
            asyncio.run(_router().apply_resource_route(session=session, route=route))
        assert session.disconnect_calls == 1
    else:
        applied = asyncio.run(_router().apply_resource_route(session=session, route=route))
        assert "knowledge-mcp" in _get(applied, "disabled_mcp_servers")
        assert [request.server_name for request in mcp.disables] == ["knowledge-mcp"]


def test_sdk_types_source_qualified_exclusions_and_user_filter_intersection() -> None:
    route = _one_server_route(False, available_tools=["builtin-safe", "mcp:knowledge-mcp-search", "mcp:knowledge-mcp-write"], excluded_tools=["builtin-denied"])
    mcp, options = FakeMCP(["search", "read", "write"]), FakeOptions()
    asyncio.run(_router().apply_resource_route(session=FakeSession(mcp, options), route=route))
    assert [request.server_name for request in mcp.lists] == ["knowledge-mcp"]
    assert len(options.updates) == 1
    update = options.updates[0]
    assert set(update.available_tools or ()) == {"builtin-safe", "mcp:knowledge-mcp-search"}
    assert {"builtin-denied", "mcp:knowledge-mcp-write"} <= set(update.excluded_tools or ())


def test_allowlist_excludes_runtime_tools_when_user_available_filter_is_unset() -> None:
    route = _one_server_route(False)
    options = FakeOptions()

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(FakeMCP(["search", "read", "write"]), options),
            route=route,
        )
    )

    assert applied.available_tools is None
    assert applied.excluded_tools == ("mcp:knowledge-mcp-write",)
    assert options.updates[0].available_tools is None
    assert options.updates[0].excluded_tools == ["mcp:knowledge-mcp-write"]


def test_caller_excluded_tool_narrows_policy_allowlist_without_available_tools_override() -> None:
    """D-01A回帰: available_tools無指定でもexcluded_toolsだけでpolicy allowlist
    が狭まらなければならない（FR-TS-13: 利用者が明示したexcluded_toolsを分類
    routingが拡張してはならない）。"""
    route = _build(
        "ard",
        snapshot=_snapshot(mcp_servers=(_resource("mcp_server", "knowledge-mcp"),), skills=()),
        excluded_tools=["mcp:knowledge-mcp-read"],
    )

    assert _get(route, "mcp_tool_allowlists")["knowledge-mcp"] == ("search",)
    assert "knowledge-mcp" in _get(route, "enabled_mcp_servers")


def test_user_excluded_tool_wins_when_the_same_tool_is_available() -> None:
    route = _one_server_route(
        False,
        available_tools=["mcp:knowledge-mcp-search"],
        excluded_tools=["mcp:knowledge-mcp-search"],
    )
    options = FakeOptions()

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(FakeMCP(["search", "read"]), options),
            route=route,
        )
    )

    assert applied.available_tools == ()
    assert set(applied.excluded_tools or ()) == {
        "mcp:knowledge-mcp-read",
        "mcp:knowledge-mcp-search",
    }
    assert options.updates[0].available_tools == []


def test_optional_server_disable_failure_disconnects_and_fails_closed() -> None:
    route = _one_server_route(False)
    session = FakeSession(FakeMCP([], list_fail=True, disable_fail=True), FakeOptions())

    with pytest.raises(_router().ResourceRoutingError, match="could not be disabled"):
        asyncio.run(_router().apply_resource_route(session=session, route=route))

    assert session.disconnect_calls == 1


def test_missing_required_tools_error_lists_exact_names() -> None:
    route = _one_server_route(True)
    session = FakeSession(FakeMCP(["read"]), FakeOptions())

    with pytest.raises(_router().ResourceRoutingError) as captured:
        asyncio.run(_router().apply_resource_route(session=session, route=route))

    assert "knowledge-mcp" in str(captured.value)
    assert "search" in str(captured.value)
    assert session.disconnect_calls == 1


def test_two_servers_apply_one_aggregate_options_update() -> None:
    snapshot = _snapshot(
        mcp_servers=(
            _resource("mcp_server", "knowledge-mcp"),
            _resource("mcp_server", "shared-mcp"),
        ),
        skills=(),
    )
    route = _build("ard", snapshot=snapshot)
    options = FakeOptions()
    session = FakeSession(
        FakeMCP(
            {
                "knowledge-mcp": ["search", "read", "write"],
                "shared-mcp": ["lookup", "mutate"],
            }
        ),
        options,
    )

    applied = asyncio.run(
        _router().apply_resource_route(session=session, route=route)
    )

    assert len(options.updates) == 1
    assert set(applied.excluded_tools or ()) == {
        "mcp:knowledge-mcp-write",
        "mcp:shared-mcp-mutate",
    }


def test_empty_enabled_mcp_route_still_applies_caller_filters_once() -> None:
    route = _router().ResourceRoute(
        available_tools=("builtin-safe",),
        excluded_tools=("builtin-denied",),
    )
    options = FakeOptions()

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(FakeMCP([]), options),
            route=route,
        )
    )

    assert applied.available_tools == ("builtin-safe",)
    assert applied.excluded_tools == ("builtin-denied",)
    assert len(options.updates) == 1
    assert options.updates[0].available_tools == ["builtin-safe"]
    assert options.updates[0].excluded_tools == ["builtin-denied"]


def test_empty_enabled_mcp_route_without_filters_skips_empty_update() -> None:
    options = FakeOptions()

    asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(FakeMCP([]), options),
            route=_router().ResourceRoute(),
        )
    )

    assert options.updates == []


def test_empty_enabled_mcp_route_filter_update_failure_disconnects() -> None:
    session = FakeSession(FakeMCP([]), FakeOptions(fail=True))
    route = _router().ResourceRoute(excluded_tools=("builtin-denied",))

    with pytest.raises(_router().ResourceRoutingError, match="caller tool filters"):
        asyncio.run(_router().apply_resource_route(session=session, route=route))

    assert session.disconnect_calls == 1


def test_aggregate_update_failure_disables_all_remaining_optional_servers() -> None:
    snapshot = _snapshot(
        mcp_servers=(
            _resource("mcp_server", "knowledge-mcp"),
            _resource("mcp_server", "shared-mcp"),
        ),
        skills=(),
    )
    route = _build("ard", snapshot=snapshot)
    mcp = FakeMCP(
        {
            "knowledge-mcp": ["search", "read"],
            "shared-mcp": ["lookup"],
        }
    )

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(mcp, FakeOptions(fail=True)),
            route=route,
        )
    )

    assert applied.enabled_mcp_servers == ()
    assert set(applied.disabled_mcp_servers) == {"knowledge-mcp", "shared-mcp"}
    assert [request.server_name for request in mcp.disables] == [
        "knowledge-mcp",
        "shared-mcp",
    ]


def test_optional_verification_failure_removes_its_caller_available_tools() -> None:
    snapshot = _snapshot(
        mcp_servers=(
            _resource("mcp_server", "knowledge-mcp"),
            _resource("mcp_server", "shared-mcp"),
        ),
        skills=(),
    )
    route = _build(
        "ard",
        snapshot=snapshot,
        available_tools=[
            "mcp:knowledge-mcp-search",
            "mcp:shared-mcp-lookup",
        ],
    )
    mcp = FakeMCP(
        {
            "knowledge-mcp": ["search", "read"],
            "shared-mcp": ["lookup"],
        },
        list_fail={"knowledge-mcp"},
    )

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(mcp, FakeOptions()),
            route=route,
        )
    )

    assert applied.available_tools == ("mcp:shared-mcp-lookup",)
    assert applied.enabled_mcp_servers == ("shared-mcp",)
    assert "knowledge-mcp" in applied.disabled_mcp_servers


def test_longest_exact_server_prefix_owns_explicit_tool_id() -> None:
    allowlists = _router()._explicit_mcp_tool_allowlists(
        ["mcp:a-b-lookup", "mcp:a-search"],
        ["a", "a-b"],
    )

    assert allowlists == {"a": ("search",), "a-b": ("lookup",)}


def test_empty_server_name_cannot_own_an_explicit_tool_id() -> None:
    allowlists = _router()._explicit_mcp_tool_allowlists(
        ["mcp:-search", "mcp:a-read"],
        ["", "a"],
    )

    assert allowlists == {"a": ("read",)}


def test_available_tool_for_longer_server_is_not_filtered_by_shorter_server() -> None:
    route = _router().ResourceRoute(
        enabled_mcp_servers=("a", "a-b"),
        mcp_tool_allowlists={"a": ("search",), "a-b": ("lookup",)},
        available_tools=("mcp:a-b-lookup",),
    )
    options = FakeOptions()

    applied = asyncio.run(
        _router().apply_resource_route(
            session=FakeSession(
                FakeMCP({"a": ["search"], "a-b": ["lookup"]}),
                options,
            ),
            route=route,
        )
    )

    assert applied.available_tools == ("mcp:a-b-lookup",)
    assert len(options.updates) == 1


class FakeClient:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.calls: list[dict[str, Any]] = []

    async def create_session(self, **kwargs: Any) -> FakeSession:
        self.calls.append(kwargs)
        return self.session


def test_build_routed_session_options_applies_route_and_tool_search_directly() -> None:
    route = dataclasses.replace(
        _build("ard"),
        available_tools=("builtin-safe",),
        excluded_tools=("builtin-denied",),
    )

    options = _router().build_routed_session_options(
        session_options={"model": "fake", "mcp_servers": {"legacy": {}}},
        route=route,
        tool_search_enabled=True,
        tool_search_defer_threshold=30,
    )

    assert options["model"] == "fake"
    assert "mcp_servers" not in options
    assert options["enable_config_discovery"] is True
    assert options["request_extensions"] is False
    assert options["enable_skills"] is True
    assert options["disabled_mcp_servers"] == [*route.disabled_mcp_servers, "github-mcp-server"]
    assert options["disabled_skills"] == list(route.disabled_skills)
    assert options["available_tools"] == ["builtin-safe"]
    assert options["excluded_tools"] == ["builtin-denied"]
    assert options["tool_search"] == {"enabled": True, "defer_threshold": 30}


def test_build_routed_session_options_keeps_caller_request_extensions() -> None:
    """FR-MODEL-10: the caller's explicit value is not overwritten."""
    options = _router().build_routed_session_options(
        session_options={"model": "fake", "request_extensions": True},
        route=_build("ard"),
    )

    assert options["request_extensions"] is True


def test_build_routed_session_options_removes_disabled_tool_search_directly() -> None:
    options = _router().build_routed_session_options(
        session_options={"model": "fake", "tool_search": {"enabled": True}},
        tool_search_enabled=False,
    )

    assert options == {"model": "fake"}


@pytest.mark.parametrize(
    ("skills", "fail", "message"),
    [
        ([], False, "unavailable"),
        ([("knowledge-skill", False)], False, "unavailable"),
        ([], True, "could not be verified"),
    ],
)
def test_required_skill_runtime_failure_disconnects_session(
    skills: list[tuple[str, bool]],
    fail: bool,
    message: str,
) -> None:
    snapshot = _snapshot(
        mcp_servers=(),
        skills=(_resource("skill", "knowledge-skill"),),
    )
    session = FakeSession(FakeMCP([]), FakeOptions(), FakeSkills(skills, fail))

    with pytest.raises(_router().ResourceRoutingError, match=message):
        asyncio.run(
            _router().create_routed_session(
                client=FakeClient(session),
                session_options={"model": "fake"},
                snapshot=snapshot,
                policy=_policy(),
                workflow_id="ard",
                required_skills=["knowledge-skill"],
            )
        )

    assert session.disconnect_calls == 1


def test_required_skill_runtime_ready_allows_session_creation() -> None:
    snapshot = _snapshot(
        mcp_servers=(),
        skills=(_resource("skill", "knowledge-skill"),),
    )
    session = FakeSession(
        FakeMCP([]),
        FakeOptions(),
        FakeSkills([("knowledge-skill", True)]),
    )

    result = asyncio.run(
        _router().create_routed_session(
            client=FakeClient(session),
            session_options={"model": "fake"},
            snapshot=snapshot,
            policy=_policy(),
            workflow_id="ard",
            required_skills=["knowledge-skill"],
        )
    )

    assert result is session
    assert session.disconnect_calls == 0


def test_apply_resource_route_verifies_required_skills_for_resumed_sessions_too() -> None:
    route = _build("ard", required_skills=["knowledge-skill"])
    session = FakeSession(
        FakeMCP([]),
        FakeOptions(),
        FakeSkills([("knowledge-skill", False)]),
    )

    with pytest.raises(_router().ResourceRoutingError, match="required Skill runtime is unavailable"):
        asyncio.run(_router().apply_resource_route(session=session, route=route))

    assert session.disconnect_calls == 1


def test_public_route_resolution_helper_is_available_for_create_and_resume_paths() -> None:
    route = _router().resolve_resource_route(
        snapshot=_snapshot(),
        policy=_policy(),
        workflow_id="ard",
        required_mcp_servers=["knowledge-mcp"],
    )

    assert "knowledge-mcp" in _get(route, "enabled_mcp_servers")


def test_resolve_route_merges_explicit_and_required_skill_mcp_dependencies() -> None:
    route = _router().resolve_resource_route(
        snapshot=_snapshot(),
        policy=_policy(
            required_mcp_servers_by_skill={
                "knowledge-skill": ["knowledge-mcp", "shared-mcp"]
            }
        ),
        workflow_id="ard",
        required_mcp_servers=["shared-mcp"],
        required_skills=["knowledge-skill"],
    )

    assert route.required_mcp_servers == ("shared-mcp", "knowledge-mcp")
    assert route.enabled_mcp_servers[:2] == ("knowledge-mcp", "shared-mcp")


def test_required_skill_mcp_dependency_does_not_elevate_workflow_category() -> None:
    with pytest.raises(_router().ResourceRoutingError, match="engineering-mcp"):
        _router().resolve_resource_route(
            snapshot=_snapshot(),
            policy=_policy(
                required_mcp_servers_by_skill={
                    "engineering-skill": ["engineering-mcp"]
                }
            ),
            workflow_id="ard",
            required_skills=["engineering-skill"],
        )


def test_create_session_from_route_reuses_the_resolved_route_object() -> None:
    route = _build("ard", required_mcp_servers=["knowledge-mcp"])
    client = FakeClient(
        FakeSession(
            FakeMCP(["search", "read"]),
            FakeOptions(),
        )
    )

    result = asyncio.run(
        _router().create_session_from_route(
            client=client,
            session_options={"model": "fake"},
            route=route,
        )
    )

    assert result is client.session
    assert client.calls == [
        {
            "model": "fake",
            "enable_config_discovery": True,
            "request_extensions": False,
            "enable_skills": True,
            "disabled_mcp_servers": [*route.disabled_mcp_servers, "github-mcp-server"],
            "disabled_skills": list(route.disabled_skills),
        }
    ]
    assert len(client.session.rpc.options.updates) == 1


def test_create_routed_session_delegates_creation_to_create_session_from_route() -> None:
    module = _router()
    route = _build("ard")
    snapshot = _snapshot()
    session = FakeSession(FakeMCP([]), FakeOptions())
    client = FakeClient(session)

    async def _fake_create_session_from_route(**kwargs: Any) -> Any:
        assert kwargs["route"] is route
        return session

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(module, "resolve_resource_route", lambda **_kwargs: route)
        monkeypatch.setattr(module, "create_session_from_route", _fake_create_session_from_route)
        result = asyncio.run(
            module.create_routed_session(
                client=client,
                session_options={"model": "fake"},
                snapshot=snapshot,
                policy=_policy(),
                workflow_id="ard",
            )
        )

    assert result is session


@pytest.mark.parametrize(
    ("field", "name"),
    [("disabled_mcp_servers", "knowledge-mcp"), ("disabled_skills", "knowledge-skill")],
    ids=["mcp", "skill"],
)
def test_caller_disabled_resources_union_preserves_order_and_inputs(field: str, name: str) -> None:
    """FR-TS-13: caller exclusions precede route exclusions; exact duplicates alone collapse."""
    route = _build("ard")
    caller = {"model": "fake", field: [name, getattr(route, field)[0], name, name.upper()]}
    caller_before, route_before = deepcopy(caller), deepcopy(route)

    options = _router().build_routed_session_options(session_options=caller, route=route)

    assert caller == caller_before
    assert route == route_before
    builtin_exclusions = ("github-mcp-server",) if field == "disabled_mcp_servers" else ()
    assert options[field] == list(dict.fromkeys((
        *caller_before[field], *getattr(route, field), *builtin_exclusions,
    )))


@pytest.mark.parametrize("required_kind", ["mcp", "skill", "skill-dependency"])
@pytest.mark.parametrize("name_match", ["exact", "prefix", "different-case"])
def test_caller_disabled_required_conflict_is_exact_and_precreate(
    required_kind: str, name_match: str
) -> None:
    """FR-TS-13: even Skill-derived required MCP conflicts must stop before create."""
    module = _router()
    field = "disabled_skills" if required_kind == "skill" else "disabled_mcp_servers"
    name = "knowledge-skill" if required_kind == "skill" else "knowledge-mcp"
    disabled_name = {"exact": name, "prefix": "knowledge", "different-case": name.upper()}[name_match]
    route = module.resolve_resource_route(
        snapshot=_snapshot(),
        policy=_policy(required_mcp_servers_by_skill=(
            {"knowledge-skill": ["knowledge-mcp"]} if required_kind == "skill-dependency" else None
        )),
        workflow_id="ard",
        required_mcp_servers=["knowledge-mcp"] if required_kind == "mcp" else [],
        required_skills=[] if required_kind == "mcp" else ["knowledge-skill"],
    )
    session = FakeSession(
        FakeMCP({"knowledge-mcp": ["search", "read"], "shared-mcp": ["lookup"]}),
        FakeOptions(),
        FakeSkills([("knowledge-skill", True)]),
    )
    client = FakeClient(session)
    caller = {"model": "fake", field: [disabled_name]}
    caller_before, route_before = deepcopy(caller), deepcopy(route)

    if name_match == "exact":
        with pytest.raises(module.ResourceRoutingError, match=name):
            asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route))
        assert client.calls == []
        assert session.rpc.skills.list_calls == 0
        assert session.rpc.tools.initialize_calls == 0
        assert session.rpc.mcp.list_calls == 0
        assert session.rpc.mcp.lists == []
        assert session.rpc.options.updates == []
    else:
        result = asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route))
        assert result is session
        assert len(client.calls) == 1
        assert disabled_name in client.calls[0][field]
    assert session.disconnect_calls == 0
    assert caller == caller_before
    assert route == route_before


@pytest.mark.parametrize("disable_all", [False, True], ids=["some", "all"])
def test_create_session_from_route_does_not_verify_caller_disabled_optionals(
    monkeypatch: pytest.MonkeyPatch, disable_all: bool
) -> None:
    """FR-TS-13: exercise real create + apply, not just the SDK creation kwargs."""
    module = _router()
    route = _build("ard")
    caller = {
        "model": "fake",
        "disabled_mcp_servers": list(route.enabled_mcp_servers) if disable_all else ["knowledge-mcp"],
        "disabled_skills": list(route.enabled_skills) if disable_all else ["knowledge-skill"],
    }
    caller_before, route_before = deepcopy(caller), deepcopy(route)
    session = FakeSession(
        FakeMCP({"knowledge-mcp": ["search", "read"], "shared-mcp": ["lookup", "mutate"]}),
        FakeOptions(),
    )
    client = FakeClient(session)
    seen_routes = []
    apply_route = module.apply_resource_route

    async def record_apply(*, session: Any, route: Any, **kwargs: Any) -> Any:
        applied = await apply_route(session=session, route=route, **kwargs)
        seen_routes.append(applied)
        return applied

    monkeypatch.setattr(module, "apply_resource_route", record_apply)
    result = asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route))

    assert result is session
    assert caller == caller_before
    assert route == route_before
    expected_mcps = () if disable_all else ("shared-mcp",)
    expected_skills = () if disable_all else ("shared-skill",)
    assert [request.server_name for request in session.rpc.mcp.lists] == list(expected_mcps)
    assert session.rpc.mcp.disables == []
    assert session.disconnect_calls == 0
    assert len(seen_routes) == len(client.calls) == 1
    assert seen_routes[0].enabled_mcp_servers == expected_mcps
    assert seen_routes[0].enabled_skills == expected_skills
    for field in ("disabled_mcp_servers", "disabled_skills"):
        builtin_exclusions = ("github-mcp-server",) if field == "disabled_mcp_servers" else ()
        expected = list(dict.fromkeys((
            *caller_before[field], *getattr(route_before, field), *builtin_exclusions,
        )))
        assert client.calls[0][field] == expected
        assert tuple(getattr(seen_routes[0], field)) == tuple(expected)
    assert len(session.rpc.options.updates) == (0 if disable_all else 1)
    if disable_all:
        assert session.rpc.tools.initialize_calls == 0
        assert session.rpc.mcp.list_calls == 0


@pytest.mark.parametrize("field", ["available_tools", "excluded_tools"])
@pytest.mark.parametrize("value", [None, []], ids=["none", "empty"])
@pytest.mark.parametrize(
    "response",
    [{"success": True}, {"success": False}, {}],
    ids=["ack-true", "ack-false", "missing-success"],
)
def test_zero_mcp_caller_empty_filter_still_requires_ack(
    field: str, value: list[str] | None, response: dict[str, Any]
) -> None:
    """FR-TS-13: None skips ACK; explicit [] does not, even with zero selected MCPs."""
    module = _router()
    session = FakeSession(
        FakeMCP({}), FakeOptions(response=response), FakeSkills([("knowledge-skill", True)])
    )
    client = FakeClient(session)
    caller = {"model": "fake", field: value}
    caller_before = deepcopy(caller)
    kwargs = dict(
        client=client,
        session_options=caller,
        snapshot=_snapshot(mcp_servers=(), skills=(_resource("skill", "knowledge-skill"),)),
        policy=_policy(),
        workflow_id="ard",
        required_skills=["knowledge-skill"],
    )
    failed = value is not None and response.get("success") is not True

    if failed:
        with pytest.raises(module.ResourceRoutingError):
            asyncio.run(module.create_routed_session(**kwargs))
    else:
        assert asyncio.run(module.create_routed_session(**kwargs)) is session

    assert caller == caller_before
    assert client.calls[0][field] == value
    assert session.rpc.skills.list_calls == 1
    assert session.rpc.tools.initialize_calls == 0
    assert session.rpc.mcp.list_calls == 0
    assert session.rpc.mcp.lists == session.rpc.mcp.disables == []
    assert len(session.rpc.options.updates) == int(value is not None)
    assert session.disconnect_calls == int(failed)


@pytest.mark.parametrize(
    ("required_mcps", "required_skills", "filters", "fail_closed"),
    [
        pytest.param(("knowledge-mcp",), (), {}, True, id="required-mcp"),
        pytest.param((), ("knowledge-skill",), {}, False, id="unrelated-required-skill"),
        pytest.param((), (), {"available_tools": ["builtin-safe"]}, True, id="available"),
        pytest.param((), (), {"excluded_tools": ["builtin-denied"]}, True, id="excluded"),
        pytest.param((), (), {"available_tools": []}, True, id="available-empty"),
        pytest.param((), (), {"excluded_tools": []}, True, id="excluded-empty"),
        pytest.param((), (), {}, False, id="optional-no-filters"),
    ],
)
@pytest.mark.parametrize(
    ("response", "acknowledged"),
    [
        pytest.param({"success": True}, True, id="ack-true"),
        pytest.param({"success": False}, False, id="ack-false"),
        pytest.param({}, False, id="missing-success"),
        pytest.param({"success": "true"}, False, id="string-success"),
        pytest.param({"success": 1}, False, id="numeric-success"),
        pytest.param(None, False, id="null-response"),
    ],
)
def test_real_sdk_options_ack_uses_required_or_optional_failure_branch(
    required_mcps: tuple[str, ...],
    required_skills: tuple[str, ...],
    filters: dict[str, list[str]],
    fail_closed: bool,
    response: Any,
    acknowledged: bool,
) -> None:
    """FR-TS-13: real SDK False/decode failures cannot count as an applied filter."""
    module = _router()
    route = _build(
        "ard",
        snapshot=_snapshot(
            mcp_servers=(_resource("mcp_server", "knowledge-mcp"), _resource("mcp_server", "shared-mcp")),
            skills=(_resource("skill", "knowledge-skill"),),
        ),
        required_mcp_servers=required_mcps,
        required_skills=required_skills,
        **filters,
    )
    session = FakeSession(
        FakeMCP({"knowledge-mcp": ["search", "read", "write"], "shared-mcp": ["lookup", "mutate"]}),
        FakeOptions(response=response),
        FakeSkills([("knowledge-skill", True)]),
    )

    if not acknowledged and fail_closed:
        with pytest.raises(module.ResourceRoutingError):
            asyncio.run(module.apply_resource_route(session=session, route=route))
        assert session.disconnect_calls == 1
        assert session.rpc.mcp.disables == []
    else:
        applied = asyncio.run(module.apply_resource_route(session=session, route=route))
        assert session.disconnect_calls == 0
        assert applied.enabled_mcp_servers == (route.enabled_mcp_servers if acknowledged else ())
        expected_disabled = () if acknowledged else route.enabled_mcp_servers
        assert applied.disabled_mcp_servers == expected_disabled
        assert [request.server_name for request in session.rpc.mcp.disables] == list(expected_disabled)

    assert [request.server_name for request in session.rpc.mcp.lists] == list(route.enabled_mcp_servers)
    assert len(session.rpc.options.updates) == 1  # No per-server ACK or second-update rescue.
    assert {"mcp:knowledge-mcp-write", "mcp:shared-mcp-mutate"} <= set(
        session.rpc.options.updates[0].excluded_tools or ()
    )


@pytest.mark.parametrize("response", [{"success": False}, {}], ids=["ack-false", "missing-success"])
def test_optional_ack_failure_requires_successful_disable_before_continuing(response: dict[str, Any]) -> None:
    """FR-TS-13: optional ACK failure is recoverable only when disable succeeds."""
    module = _router()
    session = FakeSession(
        FakeMCP(["search", "read"], disable_fail=True), FakeOptions(response=response)
    )

    with pytest.raises(module.ResourceRoutingError, match="disabled"):
        asyncio.run(module.apply_resource_route(session=session, route=_one_server_route(False)))

    assert session.disconnect_calls == 1
    assert len(session.rpc.options.updates) == 1
    assert [request.server_name for request in session.rpc.mcp.disables] == ["knowledge-mcp"]


_BUILTIN_GITHUB = "github-mcp-server"
_BUILTIN_TOOLS = tuple(f"offline-tool-{index}" for index in range(6))


def _github_policy() -> ToolSearchPolicy:
    policy = _policy()
    return dataclasses.replace(
        policy,
        resource_classifications={
            **policy.resource_classifications,
            "mcp_servers": {
                **policy.resource_classifications["mcp_servers"],
                _BUILTIN_GITHUB: "knowledge",
            },
        },
        knowledge_tool_allowlists={
            **policy.knowledge_tool_allowlists,
            _BUILTIN_GITHUB: _BUILTIN_TOOLS,
        },
    )


@pytest.mark.parametrize("selection", ["optional", "missing-optional", "zero"])
@pytest.mark.parametrize("caller", [{}, {"disabled_mcp_servers": []}])
def test_builtin_undiscovered_is_disabled_without_caller_exclusions(
    selection: str, caller: dict[str, Any]
) -> None:
    module = _router()
    snapshot = _snapshot(
        mcp_servers=() if selection == "zero" else (_resource("mcp_server", "knowledge-mcp"),),
        skills=(),
    )
    route = module.resolve_resource_route(
        snapshot=snapshot, policy=_github_policy(), workflow_id="ard",
        optional_mcp_servers=[_BUILTIN_GITHUB] if selection == "missing-optional" else [],
    )
    before = deepcopy((route, caller, snapshot))

    restricted = module.restrict_resource_route(route=route, session_options=caller)

    assert restricted.disabled_mcp_servers == (_BUILTIN_GITHUB,)
    assert restricted.enabled_mcp_servers == (() if selection == "zero" else ("knowledge-mcp",))
    assert module.restrict_resource_route(route=restricted, session_options=caller) is restricted
    assert (route, caller, snapshot) == before


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_builtin_verified_enabled_is_preserved(required: bool) -> None:
    module = _router()
    route = module.resolve_resource_route(
        snapshot=_snapshot(mcp_servers=(_resource("mcp_server", _BUILTIN_GITHUB),), skills=()),
        policy=_github_policy(), workflow_id="ard",
        required_mcp_servers=[_BUILTIN_GITHUB] if required else [],
    )

    assert route.enabled_mcp_servers == (_BUILTIN_GITHUB,)
    assert route.mcp_tool_allowlists == {_BUILTIN_GITHUB: _BUILTIN_TOOLS}
    assert module.restrict_resource_route(route=route, session_options={}) is route
    client = FakeClient(FakeSession(FakeMCP({_BUILTIN_GITHUB: list(_BUILTIN_TOOLS)}), FakeOptions()))
    assert asyncio.run(module.create_session_from_route(client=client, session_options={}, route=route)) is client.session
    assert client.calls[0]["disabled_mcp_servers"] == []
    assert [request.server_name for request in client.session.rpc.mcp.lists] == [_BUILTIN_GITHUB]
    assert client.session.disconnect_calls == 0


@pytest.mark.parametrize("registered", [False, True], ids=["missing", "disabled"])
def test_builtin_required_unavailable_still_fails_precreate(registered: bool) -> None:
    module = _router()
    client = FakeClient(FakeSession(FakeMCP({}), FakeOptions()))
    with pytest.raises(module.ResourceRoutingError, match="github-mcp-server.*unavailable"):
        asyncio.run(module.create_routed_session(
            client=client, session_options={},
            snapshot=_snapshot(
                mcp_servers=(_resource("mcp_server", _BUILTIN_GITHUB, enabled=False),) if registered else (),
                skills=(),
            ),
            policy=_github_policy(), workflow_id="ard", required_mcp_servers=[_BUILTIN_GITHUB],
        ))
    assert client.calls == []
    assert client.session.rpc.tools.initialize_calls == 0


@pytest.mark.parametrize("disabled_name", [_BUILTIN_GITHUB, "github", _BUILTIN_GITHUB.upper()])
def test_builtin_required_caller_conflict_remains_exact_and_precreate(disabled_name: str) -> None:
    module = _router()
    route = module.resolve_resource_route(
        snapshot=_snapshot(mcp_servers=(_resource("mcp_server", _BUILTIN_GITHUB),), skills=()),
        policy=_github_policy(), workflow_id="ard", required_mcp_servers=[_BUILTIN_GITHUB],
    )
    caller = {"disabled_mcp_servers": [disabled_name]}
    before = deepcopy((route, caller))
    client = FakeClient(FakeSession(FakeMCP({_BUILTIN_GITHUB: list(_BUILTIN_TOOLS)}), FakeOptions()))
    if disabled_name == _BUILTIN_GITHUB:
        with pytest.raises(module.ResourceRoutingError, match="disabled by the caller"):
            asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route))
        assert client.calls == []
        assert client.session.rpc.tools.initialize_calls == 0
    else:
        assert asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route)) is client.session
        assert client.calls[0]["disabled_mcp_servers"] == [disabled_name]
    assert (route, caller) == before


@pytest.mark.parametrize("already_disabled", [False, True])
def test_builtin_default_union_is_exact_ordered_immutable_and_idempotent(already_disabled: bool) -> None:
    module = _router()
    route = module.ResourceRoute(
        enabled_mcp_servers=("caller-off", "github-mcp-server-longer"),
        disabled_mcp_servers=("route-off", _BUILTIN_GITHUB) if already_disabled else ("route-off",),
        enabled_skills=("caller-skill", "keep-skill"), disabled_skills=("route-skill",),
        mcp_tool_allowlists={"caller-off": ("read",), "github-mcp-server-longer": ("read",)},
        available_tools=("builtin-safe", "mcp:caller-off-read", "mcp:github-mcp-server-longer-read"),
        excluded_tools=("builtin-denied",),
    )
    caller = {
        "disabled_mcp_servers": ["caller-off", "route-off", "caller-off", _BUILTIN_GITHUB.upper()],
        "disabled_skills": ["caller-skill", "caller-skill"],
    }
    before = deepcopy((route, caller))
    restricted = module.restrict_resource_route(route=route, session_options=caller)

    assert restricted.disabled_mcp_servers == ("caller-off", "route-off", _BUILTIN_GITHUB.upper(), _BUILTIN_GITHUB)
    assert restricted.enabled_mcp_servers == ("github-mcp-server-longer",)
    assert restricted.disabled_skills == ("caller-skill", "route-skill")
    assert restricted.enabled_skills == ("keep-skill",)
    assert restricted.available_tools == ("builtin-safe", "mcp:github-mcp-server-longer-read")
    assert restricted.excluded_tools == route.excluded_tools
    assert restricted.mcp_tool_allowlists == route.mcp_tool_allowlists
    assert module.restrict_resource_route(route=restricted, session_options=caller) is restricted
    assert module.build_routed_session_options(session_options=caller, route=restricted)["disabled_mcp_servers"] == list(restricted.disabled_mcp_servers)
    assert (route, caller) == before


class FakeAmbientBuiltinTools(FakeTools):
    """Builtin metadata exists independently of discovery and mcp.list_tools."""

    def __init__(self, mcp: FakeMCP, options: FakeOptions) -> None:
        super().__init__(mcp, options)
        self.creation_disabled: tuple[str, ...] = ()
        self.ignore_creation_exclusion = False

    async def get_current_metadata(self, *, timeout: float | None = None) -> ToolsGetCurrentMetadataResult:
        response = await super().get_current_metadata(timeout=timeout)
        if self.ignore_creation_exclusion or _BUILTIN_GITHUB not in self.creation_disabled:
            assert response.tools is not None
            response.tools.extend(
                CurrentToolMetadata(
                    description="offline ambient builtin MCP tool", name=f"ambient-{name}",
                    mcp_server_name=_BUILTIN_GITHUB, mcp_tool_name=name,
                    namespaced_name=f"mcp:{_BUILTIN_GITHUB}-{name}",
                )
                for name in _BUILTIN_TOOLS
            )
        return response


class FakeAmbientBuiltinClient(FakeClient):
    def __init__(self) -> None:
        super().__init__(FakeSession(FakeMCP({"knowledge-mcp": ["search", "read"]}), FakeOptions()))
        self.session.rpc.tools = FakeAmbientBuiltinTools(self.session.rpc.mcp, self.session.rpc.options)

    async def create_session(self, **kwargs: Any) -> FakeSession:
        self.session.rpc.tools.creation_disabled = tuple(kwargs.get("disabled_mcp_servers", ()))
        return await super().create_session(**kwargs)


@pytest.mark.parametrize("mode", ["required", "optional", "zero"])
@pytest.mark.parametrize("caller_disables", [False, True], ids=["default", "caller-control"])
def test_builtin_exclusion_reaches_create_before_same_route_apply(
    monkeypatch: pytest.MonkeyPatch, mode: str, caller_disables: bool
) -> None:
    module = _router()
    route = module.ResourceRoute() if mode == "zero" else _one_server_route(mode == "required")
    caller = {"disabled_mcp_servers": [_BUILTIN_GITHUB]} if caller_disables else {}
    before = deepcopy((route, caller))
    client = FakeAmbientBuiltinClient()
    seen = []
    original_apply = module.apply_resource_route

    async def record_apply(*, session: Any, route: Any) -> Any:
        assert len(client.calls) == 1
        assert tuple(client.calls[0]["disabled_mcp_servers"]) == route.disabled_mcp_servers
        assert module.restrict_resource_route(route=route, session_options=caller) is route
        seen.append(route)
        return await original_apply(session=session, route=route)

    monkeypatch.setattr(module, "apply_resource_route", record_apply)
    assert asyncio.run(module.create_session_from_route(client=client, session_options=caller, route=route)) is client.session
    assert len(seen) == 1
    assert seen[0].disabled_mcp_servers == (_BUILTIN_GITHUB,)
    assert client.session.rpc.tools.creation_disabled == (_BUILTIN_GITHUB,)
    assert client.session.rpc.mcp.disables == []
    assert client.session.disconnect_calls == 0
    assert client.session.rpc.tools.initialize_calls == (0 if mode == "zero" else 1)
    assert client.session.rpc.tools.metadata_calls == (0 if mode == "zero" else 1)
    assert len(client.session.rpc.options.updates) == (0 if mode == "zero" else 1)
    assert [r.server_name for r in client.session.rpc.mcp.lists] == ([] if mode == "zero" else ["knowledge-mcp"])
    assert (route, caller) == before


@pytest.mark.parametrize("required", [False, True])
def test_builtin_extra_metadata_still_fails_after_one_refresh(required: bool) -> None:
    """FR-TS-13 (v3.07): unselected identities get one refresh, then fail closed."""
    module = _router()
    client = FakeAmbientBuiltinClient()
    client.session.rpc.tools.ignore_creation_exclusion = True
    with pytest.raises(module.ResourceRoutingError, match="outside the applied route") as captured:
        asyncio.run(module.create_session_from_route(
            client=client, session_options={"disabled_mcp_servers": [_BUILTIN_GITHUB]},
            route=_one_server_route(required),
        ))
    message = str(captured.value)
    for tool_name in _BUILTIN_TOOLS:
        assert f"{_BUILTIN_GITHUB}/{tool_name}" in message
    expected_identities = ", ".join(
        f"{_BUILTIN_GITHUB}/{tool_name}" for tool_name in sorted(_BUILTIN_TOOLS)
    )
    assert message.endswith(expected_identities)
    assert len(client.session.rpc.options.updates) == 1
    assert client.session.rpc.tools.initialize_calls == 2
    assert client.session.rpc.tools.metadata_calls == 2
    assert client.session.rpc.mcp.disables == []
    assert client.session.disconnect_calls == 1


def test_metadata_retry_error_lists_unexpected_exact_identities_in_order() -> None:
    module = _router()

    class SequenceTools:
        def __init__(self) -> None:
            self.metadata_calls = 0
            self.initialize_calls = 0

        async def get_current_metadata(
            self, *, timeout: float | None = None
        ) -> ToolsGetCurrentMetadataResult:
            self.metadata_calls += 1
            if self.metadata_calls == 1:
                return ToolsGetCurrentMetadataResult(tools=None)
            return ToolsGetCurrentMetadataResult(
                tools=[
                    CurrentToolMetadata(
                        description="must not be exposed",
                        name="zeta-write",
                        mcp_server_name="zeta",
                        mcp_tool_name="write",
                        namespaced_name="mcp:zeta-write",
                    ),
                    CurrentToolMetadata(
                        description="must not be exposed",
                        name="alpha-read",
                        mcp_server_name="alpha",
                        mcp_tool_name="read",
                        namespaced_name="mcp:alpha-read",
                    ),
                ]
            )

        async def initialize_and_validate(
            self, *, timeout: float | None = None
        ) -> ToolsInitializeAndValidateResult:
            self.initialize_calls += 1
            return ToolsInitializeAndValidateResult()

    tools = SequenceTools()
    session = SimpleNamespace(rpc=SimpleNamespace(tools=tools))

    with pytest.raises(module.ResourceRoutingError) as captured:
        asyncio.run(
            module._ensure_filtered_tool_metadata(
                session=session,
                expected=set(),
                deadline=module.time.monotonic() + 10,
            )
        )

    assert str(captured.value).endswith("alpha/read, zeta/write")
    assert "must not be exposed" not in str(captured.value)
    assert tools.metadata_calls == 2
    assert tools.initialize_calls == 1
