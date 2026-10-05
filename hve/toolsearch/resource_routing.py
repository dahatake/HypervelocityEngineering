"""Policy-driven SDK resource routing for local Copilot sessions (FR-TS-13)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from copilot.generated.rpc import (
    MCPDisableRequest,
    MCPListToolsRequest,
    McpServerStatus,
    SessionUpdateOptionsParams,
)

from .policy import PolicyError, ToolSearchPolicy
from .resource_inventory import ResourceItem, ResourceSnapshot


_ROUTING_TIMEOUT_SECONDS = 60.0
# optional な MCP だけを選んだ route で、最初の initialize_and_validate に使う上限。
# 認証待ちの optional server が共有 deadline を使い切らないようにするため。
_OPTIONAL_INIT_BUDGET_SECONDS = 20.0
_ROUTING_POLL_INTERVAL_SECONDS = 0.5
# optional な MCP server が pending のままでも、共有 deadline の残りがこの秒数になった時点で
# 検証失敗として session 内で無効化し、その無効化を同じ deadline 内で終えるための予約。
_OPTIONAL_DISABLE_RESERVE_SECONDS = 10.0
_ROUTING_CLEANUP_TIMEOUT_SECONDS = 5.0
_SDK_BUILTIN_MCP_SERVERS = ("github-mcp-server",)


class ResourceRoutingError(RuntimeError):
    """Resource routing could not be applied without weakening the policy."""


@dataclass(frozen=True)
class ResourceRoute:
    """Resolved local-session resources and their runtime enforcement metadata."""

    enabled_mcp_servers: tuple[str, ...] = ()
    disabled_mcp_servers: tuple[str, ...] = ()
    enabled_skills: tuple[str, ...] = ()
    disabled_skills: tuple[str, ...] = ()
    mcp_tool_allowlists: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    required_mcp_servers: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()
    available_tools: tuple[str, ...] | None = None
    excluded_tools: tuple[str, ...] | None = None


def _names(values: Iterable[str] | None) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    return tuple(dict.fromkeys(str(value) for value in (values or ())))


def _mcp_server_for_tool_id(
    tool_id: str,
    server_names: Iterable[str],
) -> str | None:
    """Return the longest exact known server prefix for one SDK MCP tool ID."""
    matches = [
        server_name
        for server_name in _names(server_names)
        if server_name
        and tool_id.startswith(f"mcp:{server_name}-")
        and len(tool_id) > len(f"mcp:{server_name}-")
    ]
    if not matches:
        return None
    matches.sort(key=lambda value: len(value), reverse=True)
    return matches[0]


def _explicit_mcp_tool_allowlists(
    available_tools: Iterable[str] | None,
    server_names: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    allowlists: dict[str, list[str]] = {}
    tool_ids = [str(value) for value in (available_tools or ()) if isinstance(value, str)]
    known_server_names = _names(server_names)
    for server_name in known_server_names:
        if not server_name:
            continue
        prefix = f"mcp:{server_name}-"
        tools: list[str] = []
        for tool_id in tool_ids:
            if _mcp_server_for_tool_id(tool_id, known_server_names) != server_name:
                continue
            tool_name = tool_id[len(prefix):]
            if tool_name and tool_name not in tools:
                tools.append(tool_name)
        if tools:
            allowlists[str(server_name)] = tools
    return {name: tuple(tools) for name, tools in allowlists.items()}


def effective_resource_classification(
    policy: ToolSearchPolicy,
    snapshot: ResourceSnapshot,
    kind: str,
    resource: ResourceItem,
) -> str:
    """Resolve exact/verified-owner/unclassified resource metadata once."""
    exact = policy.resource_classifications.get(kind, {}).get(resource.name)
    if exact is not None:
        return exact

    owner_verified = snapshot.plugin_state == "ready"
    if kind == "skills":
        owner_verified = owner_verified and snapshot.skill_ownership_state == "ready"
    return policy.classification_for(
        kind,
        resource.name,
        owner_plugin=resource.owner_plugin if owner_verified else None,
    )


def _allowlist(
    policy: ToolSearchPolicy,
    workflow_id: str,
    classification: str,
    server_name: str,
) -> tuple[str, ...]:
    categories: list[str] = []
    if classification in ("knowledge", "both"):
        categories.append("knowledge")
    if classification in ("software-engineering", "both"):
        try:
            engineering_allowed = policy.classification_allowed(
                workflow_id, "software-engineering"
            )
        except PolicyError as exc:
            raise ResourceRoutingError(str(exc)) from exc
        if engineering_allowed:
            categories.append("software-engineering")

    tools: list[str] = []
    for category in categories:
        for tool in policy.tool_allowlist_for(category, server_name):
            if tool not in tools:
                tools.append(tool)
    return tuple(tools)


def _resolve_resources(
    *,
    resources: Sequence[ResourceItem],
    kind: str,
    snapshot: ResourceSnapshot,
    policy: ToolSearchPolicy,
    workflow_id: str,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    explicit_mcp_tool_allowlists: Mapping[str, tuple[str, ...]] | None = None,
    explicit_mcp_tool_exclusions: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    by_name = {resource.name: resource for resource in resources}
    enabled: list[str] = []
    disabled: list[str] = []
    allowlists: dict[str, tuple[str, ...]] = {}

    for name in required:
        resource = by_name.get(name)
        if resource is None or not resource.enabled:
            raise ResourceRoutingError(f"required {kind} resource {name!r} is unavailable")

    candidates = tuple(dict.fromkeys((*by_name, *required, *optional)))
    for name in candidates:
        resource = by_name.get(name)
        if resource is None or not resource.enabled:
            if name in required:
                raise ResourceRoutingError(f"required {kind} resource {name!r} is unavailable")
            if resource is not None:
                disabled.append(name)
            continue

        classification = effective_resource_classification(
            policy, snapshot, kind, resource
        )
        try:
            allowed = policy.classification_allowed(workflow_id, classification)
        except PolicyError as exc:
            raise ResourceRoutingError(str(exc)) from exc

        if kind == "skills" and name in required:
            # FR-TS-13 / FR-CLI-76: Step の required Skill は分類より優先して候補へ残す。
            # Skill には tool allowlist が無いため、fail-closed 条件は未登録・disabled
            # （上のループで検査済み）と session runtime 不在（apply 時に照合）に限る。
            allowed = True

        tools: tuple[str, ...] = ()
        if kind == "mcp_servers":
            policy_tools = _allowlist(policy, workflow_id, classification, name)
            explicit_tools = tuple((explicit_mcp_tool_allowlists or {}).get(name, ()))
            explicit_exclusions = set(
                (explicit_mcp_tool_exclusions or {}).get(name, ())
            )
            if allowed:
                tools = policy_tools
                if explicit_tools:
                    explicit_set = set(explicit_tools)
                    tools = tuple(
                        tool_name for tool_name in policy_tools if tool_name in explicit_set
                    )
                # enable/disableの判定はavailable_tools/policyの積集合のみで決める
                # （既存契約を維持）。excluded_toolsは「一覧に残すtool」だけを絞り、
                # 積集合の結果が0件になってもserverの有効/無効判定には影響させない。
                # 0件になった場合でもserverはenabledのまま残り、apply_resource_route
                # のruntime照合で当該serverの実toolがすべて除外対象になる
                # （FR-TS-13: 利用者が明示したavailable_tools/excluded_toolsを
                # 分類routingが拡張してはならない）。
                allowed = bool(tools)
                if explicit_exclusions:
                    tools = tuple(
                        tool_name for tool_name in tools if tool_name not in explicit_exclusions
                    )
            else:
                tools = ()

        if allowed:
            enabled.append(name)
            if kind == "mcp_servers":
                allowlists[name] = tools
        else:
            if name in required:
                raise ResourceRoutingError(
                    f"required {kind} resource {name!r} is not permitted"
                )
            disabled.append(name)

    return tuple(enabled), tuple(disabled), allowlists


def build_resource_route(
    *,
    snapshot: ResourceSnapshot,
    policy: ToolSearchPolicy,
    workflow_id: str,
    required_mcp_servers: Iterable[str] | None = None,
    optional_mcp_servers: Iterable[str] | None = None,
    required_skills: Iterable[str] | None = None,
    optional_skills: Iterable[str] | None = None,
    available_tools: Iterable[str] | None = None,
    excluded_tools: Iterable[str] | None = None,
) -> ResourceRoute:
    """Resolve a fail-closed resource route from one process snapshot."""

    if snapshot.mcp_state != "ready" or snapshot.skill_state != "ready":
        raise ResourceRoutingError("MCP or Skill resource inventory is unverified")

    required_mcps = _names(required_mcp_servers)
    optional_mcps = _names(optional_mcp_servers)
    required_skill_names = _names(required_skills)
    optional_skill_names = _names(optional_skills)
    explicit_mcp_tool_allowlists = _explicit_mcp_tool_allowlists(
        available_tools,
        (resource.name for resource in snapshot.mcp_servers),
    )
    explicit_mcp_tool_exclusions = _explicit_mcp_tool_allowlists(
        excluded_tools,
        (resource.name for resource in snapshot.mcp_servers),
    )

    try:
        policy.classification_allowed(workflow_id, "knowledge")
    except PolicyError as exc:
        raise ResourceRoutingError(str(exc)) from exc

    enabled_mcps, disabled_mcps, allowlists = _resolve_resources(
        resources=snapshot.mcp_servers,
        kind="mcp_servers",
        snapshot=snapshot,
        policy=policy,
        workflow_id=workflow_id,
        required=required_mcps,
        optional=optional_mcps,
        explicit_mcp_tool_allowlists=explicit_mcp_tool_allowlists,
        explicit_mcp_tool_exclusions=explicit_mcp_tool_exclusions,
    )
    enabled_skills, disabled_skills, _ = _resolve_resources(
        resources=snapshot.skills,
        kind="skills",
        snapshot=snapshot,
        policy=policy,
        workflow_id=workflow_id,
        required=required_skill_names,
        optional=optional_skill_names,
    )
    return ResourceRoute(
        enabled_mcp_servers=enabled_mcps,
        disabled_mcp_servers=disabled_mcps,
        enabled_skills=enabled_skills,
        disabled_skills=disabled_skills,
        mcp_tool_allowlists=allowlists,
        required_mcp_servers=required_mcps,
        required_skills=required_skill_names,
        available_tools=None if available_tools is None else _names(available_tools),
        excluded_tools=None if excluded_tools is None else _names(excluded_tools),
    )


def resolve_resource_route(
    *,
    snapshot: ResourceSnapshot,
    policy: ToolSearchPolicy,
    workflow_id: str,
    required_mcp_servers: Iterable[str] | None = None,
    optional_mcp_servers: Iterable[str] | None = None,
    required_skills: Iterable[str] | None = None,
    optional_skills: Iterable[str] | None = None,
    available_tools: Iterable[str] | None = None,
    excluded_tools: Iterable[str] | None = None,
) -> ResourceRoute:
    """Resolve the public create/resume route, including required Skill MCP dependencies."""

    try:
        mapped_required_mcps = policy.required_mcp_servers_for_skills(
            _names(required_skills)
        )
    except PolicyError as exc:
        raise ResourceRoutingError(str(exc)) from exc
    resolved_required_mcps = _names(
        (*_names(required_mcp_servers), *mapped_required_mcps)
    )

    return build_resource_route(
        snapshot=snapshot,
        policy=policy,
        workflow_id=workflow_id,
        required_mcp_servers=resolved_required_mcps,
        optional_mcp_servers=optional_mcp_servers,
        required_skills=required_skills,
        optional_skills=optional_skills,
        available_tools=available_tools,
        excluded_tools=excluded_tools,
    )


def restrict_resource_route(
    *,
    route: ResourceRoute,
    session_options: Mapping[str, Any],
) -> ResourceRoute:
    """Apply caller and unselected builtin exclusions before create/resume (FR-TS-13)."""

    caller_disabled_mcps = _names(session_options.get("disabled_mcp_servers"))
    caller_disabled_skills = _names(session_options.get("disabled_skills"))
    # SDK builtins may be absent from discovery; only a verified route can select them.
    builtin_disabled_mcps = tuple(
        name for name in _SDK_BUILTIN_MCP_SERVERS if name not in route.enabled_mcp_servers
    )
    if not caller_disabled_mcps and not caller_disabled_skills and not builtin_disabled_mcps:
        return route

    for kind, required, disabled in (
        ("MCP server", route.required_mcp_servers, caller_disabled_mcps),
        ("Skill", route.required_skills, caller_disabled_skills),
    ):
        for name in required:
            if name in disabled:
                raise ResourceRoutingError(
                    f"required {kind} {name!r} is disabled by the caller"
                )

    disabled_mcps = _names(
        (*caller_disabled_mcps, *route.disabled_mcp_servers, *builtin_disabled_mcps)
    )
    disabled_skills = _names((*caller_disabled_skills, *route.disabled_skills))
    available = route.available_tools
    if available is not None and caller_disabled_mcps:
        known_server_names = _names((*route.enabled_mcp_servers, *disabled_mcps))
        available = tuple(
            tool_id
            for tool_id in available
            if _mcp_server_for_tool_id(tool_id, known_server_names)
            not in caller_disabled_mcps
        )

    restricted_route = replace(
        route,
        enabled_mcp_servers=tuple(
            name for name in route.enabled_mcp_servers if name not in caller_disabled_mcps
        ),
        disabled_mcp_servers=disabled_mcps,
        enabled_skills=tuple(
            name for name in route.enabled_skills if name not in caller_disabled_skills
        ),
        disabled_skills=disabled_skills,
        available_tools=available,
    )
    return route if restricted_route == route else restricted_route


def build_routed_session_options(
    *,
    session_options: Mapping[str, Any],
    route: ResourceRoute | None = None,
    tool_search_enabled: bool | None = None,
    tool_search_defer_threshold: int | None = None,
) -> dict[str, Any]:
    """Build local SDK options while preserving caller-owned option fields."""

    options = dict(session_options)
    options.pop("mcp_servers", None)

    if tool_search_enabled is False:
        options.pop("tool_search", None)
    elif tool_search_enabled is True:
        tool_search: dict[str, Any] = {"enabled": True}
        if tool_search_defer_threshold is not None:
            tool_search["defer_threshold"] = tool_search_defer_threshold
        options["tool_search"] = tool_search

    if route is not None:
        route = restrict_resource_route(route=route, session_options=session_options)
        options["enable_config_discovery"] = True
        options.setdefault("request_extensions", False)
        options["enable_skills"] = True
        options["disabled_mcp_servers"] = list(route.disabled_mcp_servers)
        options["disabled_skills"] = list(route.disabled_skills)
        if route.available_tools is not None:
            options["available_tools"] = list(route.available_tools)
        if route.excluded_tools is not None:
            options["excluded_tools"] = list(route.excluded_tools)
    return options


def _tool_id(server_name: str, tool_name: str) -> str:
    return f"mcp:{server_name}-{tool_name}"


def _format_mcp_identities(identities: Iterable[tuple[str, str]]) -> str:
    return ", ".join(
        f"{server_name}/{tool_name}"
        for server_name, tool_name in sorted(identities)
    )


def _remaining_routing_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("resource routing deadline exceeded")
    return remaining


async def _routing_rpc(
    rpc: Callable[..., Awaitable[Any]], *args: Any, deadline: float
) -> Any:
    """Bound both SDK transport and await, rejecting replies after the deadline."""
    timeout = _remaining_routing_time(deadline)
    try:
        response = await asyncio.wait_for(rpc(*args, timeout=timeout), timeout=timeout)
    except Exception:
        _remaining_routing_time(deadline)
        raise
    _remaining_routing_time(deadline)
    return response


def _runtime_items(response: Any, field_name: str) -> dict[str, Any]:
    items = getattr(response, field_name, None)
    if not isinstance(items, list):
        raise ResourceRoutingError(f"{field_name} runtime response could not be verified")
    by_name: dict[str, Any] = {}
    for item in items:
        name = getattr(item, "name", None)
        if not isinstance(name, str) or not name.strip() or name in by_name:
            raise ResourceRoutingError(
                f"{field_name} runtime response has an invalid or duplicate exact name"
            )
        by_name[name] = item
    return by_name


def _parse_mcp_listing(response: Any) -> dict[str, McpServerStatus]:
    if getattr(response, "host", None) is None:
        raise ResourceRoutingError("MCP host is not initialized")
    try:
        return {
            name: McpServerStatus(getattr(server, "status", None))
            for name, server in _runtime_items(response, "servers").items()
        }
    except (TypeError, ValueError) as exc:
        raise ResourceRoutingError("MCP server status could not be verified") from exc


def _expected_mcp_metadata_identities(
    *,
    route: ResourceRoute,
    enabled: Iterable[str],
    available: Iterable[str] | None,
    excluded: Iterable[str],
) -> set[tuple[str, str]]:
    available_ids = None if available is None else set(available)
    excluded_ids = set(excluded)
    all_mcp_available = available_ids is not None and "mcp:*" in available_ids
    all_mcp_excluded = "mcp:*" in excluded_ids
    identities: set[tuple[str, str]] = set()
    for server_name in enabled:
        for tool_name in route.mcp_tool_allowlists.get(server_name, ()):
            tool_id = _tool_id(server_name, tool_name)
            if (
                available_ids is not None
                and not all_mcp_available
                and tool_id not in available_ids
            ):
                continue
            if not all_mcp_excluded and tool_id not in excluded_ids:
                identities.add((server_name, tool_name))
    return identities


def _parse_mcp_metadata_identities(
    response: Any,
) -> set[tuple[str, str]] | None:
    if not hasattr(response, "tools"):
        raise ResourceRoutingError("MCP tool metadata response could not be verified")
    tools = response.tools
    if tools is None:
        return None
    if not isinstance(tools, list):
        raise ResourceRoutingError("MCP tool metadata response could not be verified")

    identities: set[tuple[str, str]] = set()
    for tool in tools:
        if not hasattr(tool, "mcp_server_name") or not hasattr(tool, "mcp_tool_name"):
            raise ResourceRoutingError("MCP tool metadata response could not be verified")
        server_name = tool.mcp_server_name
        tool_name = tool.mcp_tool_name
        if server_name is None and tool_name is None:
            continue
        if server_name is None or tool_name is None:
            raise ResourceRoutingError("MCP tool metadata has an incomplete identity")
        if (
            not isinstance(server_name, str)
            or not server_name.strip()
            or not isinstance(tool_name, str)
            or not tool_name.strip()
        ):
            raise ResourceRoutingError("MCP tool metadata has an invalid identity")
        identity = (server_name, tool_name)
        if identity in identities:
            raise ResourceRoutingError("MCP tool metadata has a duplicate exact identity")
        identities.add(identity)
    return identities


async def _get_current_mcp_metadata_identities(
    session: Any, *, deadline: float
) -> set[tuple[str, str]] | None:
    try:
        response = await _routing_rpc(
            session.rpc.tools.get_current_metadata, deadline=deadline
        )
    except TimeoutError:
        raise
    except Exception as exc:
        raise ResourceRoutingError("MCP tool metadata could not be verified") from exc
    return _parse_mcp_metadata_identities(response)


async def _ensure_filtered_tool_metadata(
    *,
    session: Any,
    expected: set[tuple[str, str]],
    deadline: float,
) -> bool:
    actual = await _get_current_mcp_metadata_identities(session, deadline=deadline)
    if actual is not None and not actual - expected and expected.issubset(actual):
        return True

    try:
        await _routing_rpc(session.rpc.tools.initialize_and_validate, deadline=deadline)
    except TimeoutError:
        raise
    except Exception as exc:
        raise ResourceRoutingError(
            "MCP tool metadata reinitialization could not be verified"
        ) from exc

    actual = await _get_current_mcp_metadata_identities(session, deadline=deadline)
    if actual is None:
        return False
    unexpected = actual - expected
    if unexpected:
        raise ResourceRoutingError(
            "MCP tool metadata exposes tools outside the applied route: "
            + _format_mcp_identities(unexpected)
        )
    return expected.issubset(actual)


async def _disconnect_failed_session(session: Any) -> None:
    try:
        await asyncio.wait_for(
            session.disconnect(), timeout=_ROUTING_CLEANUP_TIMEOUT_SECONDS
        )
    except (Exception, asyncio.CancelledError):
        pass


async def _disable_optional_server(
    session: Any, server_name: str, *, deadline: float
) -> None:
    try:
        await _routing_rpc(
            session.rpc.mcp.disable,
            MCPDisableRequest(server_name=server_name),
            deadline=deadline,
        )
    except TimeoutError:
        raise
    except Exception as exc:
        raise ResourceRoutingError(
            f"optional MCP server {server_name!r} could not be disabled"
        ) from exc


async def _verify_required_skills(
    session: Any, route: ResourceRoute, *, deadline: float
) -> None:
    if not route.required_skills:
        return
    try:
        response = await _routing_rpc(session.rpc.skills.list, deadline=deadline)
        skills = _runtime_items(response, "skills")
        if any(not isinstance(getattr(skill, "enabled", None), bool) for skill in skills.values()):
            raise ResourceRoutingError("required Skill runtime could not be verified")
        runtime_skills = {name: skill.enabled for name, skill in skills.items()}
    except TimeoutError:
        raise
    except Exception as exc:
        raise ResourceRoutingError("required Skill runtime could not be verified") from exc

    unavailable = [
        name for name in route.required_skills if runtime_skills.get(name) is not True
    ]
    if unavailable:
        raise ResourceRoutingError(
            f"required Skill runtime is unavailable: {', '.join(unavailable)}"
        )


async def apply_resource_route(
    *, session: Any, route: ResourceRoute, deadline: float | None = None
) -> ResourceRoute:
    """Enforce resource readiness within one optional absolute monotonic deadline."""

    try:
        internal_deadline = time.monotonic() + _ROUTING_TIMEOUT_SECONDS
        deadline = internal_deadline if deadline is None else min(internal_deadline, deadline)
        _remaining_routing_time(deadline)
        await _verify_required_skills(session, route, deadline=deadline)

        enabled = list(route.enabled_mcp_servers)
        disabled = list(route.disabled_mcp_servers)
        available = None if route.available_tools is None else list(route.available_tools)
        excluded = [] if route.excluded_tools is None else list(route.excluded_tools)
        if available is not None and excluded:
            excluded_set = set(excluded)
            available = [tool_id for tool_id in available if tool_id not in excluded_set]
        required = set(route.required_mcp_servers)
        known_server_names = _names((*route.enabled_mcp_servers, *route.disabled_mcp_servers))
        verified_server = False
        reserve = min(_OPTIONAL_DISABLE_RESERVE_SECONDS, _ROUTING_TIMEOUT_SECONDS * 0.2)

        if enabled:
            optional_only = not required.intersection(enabled) and not (
                route.available_tools is not None or route.excluded_tools is not None
            )
            init_deadline = (
                min(deadline, time.monotonic() + _OPTIONAL_INIT_BUDGET_SECONDS)
                if optional_only
                else deadline
            )
            try:
                await _routing_rpc(
                    session.rpc.tools.initialize_and_validate, deadline=init_deadline
                )
            except TimeoutError:
                if init_deadline >= deadline:
                    raise
                # 認証待ち・失敗の optional server が初期化を止めている場合だけ、
                # その server を無効化して続ける。原因が見えない停止は従来どおり失敗。
                # pending の server は共有 deadline 内で状態が確定するまで待つ。
                while True:
                    listing = _parse_mcp_listing(
                        await _routing_rpc(session.rpc.mcp.list, deadline=deadline)
                    )
                    blocking = [
                        name
                        for name in enabled
                        if listing.get(name) in {McpServerStatus.NEEDS_AUTH, McpServerStatus.FAILED}
                    ]
                    if blocking:
                        break
                    pending = [
                        name for name in enabled if listing.get(name) == McpServerStatus.PENDING
                    ]
                    if not pending:
                        # 原因となる server が見えない。初期化そのものが遅いだけの可能性が
                        # あるため、残りの共有 deadline で初期化を待ち直す（停止はそこで判定）。
                        break
                    if _remaining_routing_time(deadline) <= reserve:
                        blocking = pending
                        break
                    await asyncio.sleep(
                        min(_ROUTING_POLL_INTERVAL_SECONDS, _remaining_routing_time(deadline))
                    )
                    _remaining_routing_time(deadline)
                for server_name in blocking:
                    await _disable_optional_server(session, server_name, deadline=deadline)
                    enabled.remove(server_name)
                    if server_name not in disabled:
                        disabled.append(server_name)
                    if available is not None:
                        available = [
                            tool_id
                            for tool_id in available
                            if _mcp_server_for_tool_id(tool_id, known_server_names)
                            != server_name
                        ]
                if enabled:
                    await _routing_rpc(
                        session.rpc.tools.initialize_and_validate, deadline=deadline
                    )
            except Exception as exc:
                raise ResourceRoutingError(
                    "MCP tool initialization could not be verified"
                ) from exc

        for server_name in tuple(enabled):
            expected = set(route.mcp_tool_allowlists.get(server_name, ()))
            try:
                while True:
                    response = await _routing_rpc(session.rpc.mcp.list, deadline=deadline)
                    status = _parse_mcp_listing(response).get(server_name)
                    if status == McpServerStatus.CONNECTED:
                        break
                    if status == McpServerStatus.NEEDS_AUTH:
                        raise ResourceRoutingError(
                            f"MCP server {server_name!r} requires authentication"
                        )
                    if status != McpServerStatus.PENDING:
                        raise ResourceRoutingError(
                            f"MCP server {server_name!r} is not connected"
                        )
                    if (
                        server_name not in required
                        and _remaining_routing_time(deadline) <= reserve
                    ):
                        raise ResourceRoutingError(
                            f"optional MCP server {server_name!r} is still pending"
                        )
                    await asyncio.sleep(
                        min(_ROUTING_POLL_INTERVAL_SECONDS, _remaining_routing_time(deadline))
                    )
                    _remaining_routing_time(deadline)

                response = await _routing_rpc(
                    session.rpc.mcp.list_tools,
                    MCPListToolsRequest(server_name=server_name),
                    deadline=deadline,
                )
                actual = set(_runtime_items(response, "tools"))
                missing = expected - actual
                if missing:
                    raise ResourceRoutingError(
                        f"MCP server {server_name!r} is missing required tools: "
                        + ", ".join(sorted(missing))
                    )

                allowed_ids = {_tool_id(server_name, name) for name in expected}
                actual_ids = {_tool_id(server_name, name) for name in actual}
                if available is not None:
                    available = [
                        tool_id
                        for tool_id in available
                        if _mcp_server_for_tool_id(tool_id, known_server_names)
                        != server_name
                        or tool_id in allowed_ids
                    ]
                for tool_id in sorted(actual_ids - allowed_ids):
                    if tool_id not in excluded:
                        excluded.append(tool_id)

                verified_server = True
            except TimeoutError:
                raise
            except Exception as exc:
                if server_name in required:
                    if isinstance(exc, ResourceRoutingError):
                        raise
                    raise ResourceRoutingError(
                        f"required MCP server {server_name!r} could not be applied"
                    ) from exc
                await _disable_optional_server(session, server_name, deadline=deadline)
                enabled.remove(server_name)
                if server_name not in disabled:
                    disabled.append(server_name)
                if available is not None:
                    available = [
                        tool_id
                        for tool_id in available
                        if _mcp_server_for_tool_id(tool_id, known_server_names)
                        != server_name
                    ]

        caller_filter_requested = (
            route.available_tools is not None or route.excluded_tools is not None
        )
        if verified_server or caller_filter_requested:
            try:
                acknowledgement = await _routing_rpc(
                    session.rpc.options.update,
                    SessionUpdateOptionsParams(
                        available_tools=available,
                        excluded_tools=excluded or None,
                    ),
                    deadline=deadline,
                )
                if getattr(acknowledgement, "success", None) is not True:
                    raise ResourceRoutingError("MCP routing options were not acknowledged")
            except TimeoutError:
                raise
            except Exception as exc:
                required_enabled = sorted(required.intersection(enabled))
                if required_enabled or caller_filter_requested or not enabled:
                    context = (
                        " for required MCP servers: " + ", ".join(required_enabled)
                        if required_enabled
                        else " for caller tool filters"
                    )
                    raise ResourceRoutingError(
                        "MCP routing options could not be applied" + context
                    ) from exc

                for server_name in tuple(enabled):
                    await _disable_optional_server(session, server_name, deadline=deadline)
                    enabled.remove(server_name)
                    if server_name not in disabled:
                        disabled.append(server_name)
                    excluded = [
                        tool_id
                        for tool_id in excluded
                        if _mcp_server_for_tool_id(tool_id, known_server_names)
                        != server_name
                    ]
                    if available is not None:
                        available = [
                            tool_id
                            for tool_id in available
                            if _mcp_server_for_tool_id(tool_id, known_server_names)
                            != server_name
                        ]

        if enabled:
            expected_metadata = _expected_mcp_metadata_identities(
                route=route,
                enabled=enabled,
                available=available,
                excluded=excluded,
            )
            metadata_ready = await _ensure_filtered_tool_metadata(
                session=session,
                expected=expected_metadata,
                deadline=deadline,
            )
            if not metadata_ready:
                required_enabled = sorted(required.intersection(enabled))
                if required_enabled or caller_filter_requested:
                    context = (
                        " for required MCP servers: " + ", ".join(required_enabled)
                        if required_enabled
                        else " for caller tool filters"
                    )
                    raise ResourceRoutingError(
                        "MCP tool metadata could not be applied" + context
                    )

                for server_name in tuple(enabled):
                    await _disable_optional_server(session, server_name, deadline=deadline)
                    enabled.remove(server_name)
                    if server_name not in disabled:
                        disabled.append(server_name)
                    excluded = [
                        tool_id
                        for tool_id in excluded
                        if _mcp_server_for_tool_id(tool_id, known_server_names)
                        != server_name
                    ]
                    if available is not None:
                        available = [
                            tool_id
                            for tool_id in available
                            if _mcp_server_for_tool_id(tool_id, known_server_names)
                            != server_name
                        ]

        applied_route = replace(
            route,
            enabled_mcp_servers=tuple(enabled),
            disabled_mcp_servers=tuple(disabled),
            available_tools=None if available is None else tuple(available),
            excluded_tools=None if not excluded else tuple(excluded),
        )
        _remaining_routing_time(deadline)
        return applied_route
    except (Exception, asyncio.CancelledError):
        await _disconnect_failed_session(session)
        raise


async def create_routed_session(
    *,
    client: Any,
    session_options: Mapping[str, Any],
    snapshot: ResourceSnapshot,
    policy: ToolSearchPolicy,
    workflow_id: str,
    required_mcp_servers: Iterable[str] | None = None,
    optional_mcp_servers: Iterable[str] | None = None,
    required_skills: Iterable[str] | None = None,
    optional_skills: Iterable[str] | None = None,
    tool_search_enabled: bool | None = None,
    tool_search_defer_threshold: int | None = None,
) -> Any:
    """Create a fully routed local session from one SDK resource snapshot."""

    route = resolve_resource_route(
        snapshot=snapshot,
        policy=policy,
        workflow_id=workflow_id,
        required_mcp_servers=required_mcp_servers,
        optional_mcp_servers=optional_mcp_servers,
        required_skills=required_skills,
        optional_skills=optional_skills,
        available_tools=session_options.get("available_tools"),
        excluded_tools=session_options.get("excluded_tools"),
    )
    return await create_session_from_route(
        client=client,
        session_options=session_options,
        route=route,
        tool_search_enabled=tool_search_enabled,
        tool_search_defer_threshold=tool_search_defer_threshold,
    )


async def create_session_from_route(
    *,
    client: Any,
    session_options: Mapping[str, Any],
    route: ResourceRoute,
    tool_search_enabled: bool | None = None,
    tool_search_defer_threshold: int | None = None,
) -> Any:
    """Create one local session from one already-resolved route.

    Cloud Session は FR-TS-13 の対象外であり、呼び出し側（runner / orchestrator）が
    routing 経路へ入る前に分岐するため、ここで cloud を扱う経路は存在しない。
    """

    route = restrict_resource_route(route=route, session_options=session_options)
    options = build_routed_session_options(
        session_options=session_options,
        route=route,
        tool_search_enabled=tool_search_enabled,
        tool_search_defer_threshold=tool_search_defer_threshold,
    )
    session = await client.create_session(**options)
    await apply_resource_route(session=session, route=route)
    return session


__all__ = [
    "ResourceRoute",
    "ResourceRoutingError",
    "apply_resource_route",
    "build_resource_route",
    "build_routed_session_options",
    "create_session_from_route",
    "create_routed_session",
    "effective_resource_classification",
    "resolve_resource_route",
    "restrict_resource_route",
]
