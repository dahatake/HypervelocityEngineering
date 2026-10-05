"""GitHub Copilot SDK の read-only resource inventory（FR-TS-12）。

保持するのは分類に必要な安全な metadata だけである。SDK の生 payload、path、
transport 設定、credential、例外本文は snapshot やログへ残さない。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, TypeVar


ResourceKind = Literal["plugin", "mcp_server", "skill"]
ResourceState = Literal["ready", "unverified"]

# 実 SDK の探索は単独でも約 10〜12 秒かかり（2026-10-02 実測）、resume を並列に 2 本起動すると
# 15 秒を超えて MCP / Skill が unverified になったため、余裕を持たせた共有 deadline とする。
DEFAULT_DEADLINE_SECONDS = 45.0


@dataclass(frozen=True)
class ResourceItem:
    """分類へ渡してよい resource metadata の固定 allowlist。"""

    kind: ResourceKind
    name: str
    enabled: bool
    source_kind: str
    plugin_marketplace: str | None = None
    owner_plugin: str | None = None
    plugin_version: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ResourceSnapshot:
    """Plugin / MCP / Skill を独立状態で保持する process snapshot。"""

    plugin_state: ResourceState
    mcp_state: ResourceState
    skill_state: ResourceState
    skill_ownership_state: ResourceState
    plugins: tuple[ResourceItem, ...]
    mcp_servers: tuple[ResourceItem, ...]
    skills: tuple[ResourceItem, ...]


_CACHE: dict[tuple[str, str], ResourceSnapshot] = {}
_T = TypeVar("_T")


class _Deadline:
    def __init__(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._expires_at = loop.time() + max(0.0, seconds)
        self.expired = False

    def remaining(self) -> float:
        return max(0.0, self._expires_at - self._loop.time())

    async def wait(self, awaitable: Awaitable[_T]) -> _T:
        """同じ absolute deadline で await し、期限切れ task も確実に cancel する。"""
        task = asyncio.ensure_future(awaitable)
        remaining = self.remaining()
        if remaining > 0:
            try:
                return await asyncio.wait_for(task, timeout=remaining)
            except TimeoutError:
                self.expired = True
                raise

        # timeout=0 の wait_for は coroutine 本体を一度も開始しないことがある。
        # cleanup を含む呼出しを一度開始してから、追加予算を与えず cancel する。
        await asyncio.sleep(0)
        if task.done():
            return task.result()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self.expired = True
        raise TimeoutError


def discover_sdk_resources(
    *,
    working_directory: Path | str,
    cli_path: str | None = None,
    cli_url: str | None = None,
    github_token: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    force_refresh: bool = False,
    timeout: float = DEFAULT_DEADLINE_SECONDS,
) -> ResourceSnapshot | Awaitable[ResourceSnapshot]:
    """SDK resource を列挙する。

    通常の同期 caller には snapshot を直接返す。既存 event loop 内から呼ばれた場合は
    awaitable を返すため、GUI/async caller が nested ``asyncio.run`` を踏まない。
    """
    coroutine = _discover_sdk_resources(
        working_directory=working_directory,
        cli_path=cli_path,
        cli_url=cli_url,
        github_token=github_token,
        client_factory=client_factory,
        force_refresh=force_refresh,
        timeout=timeout,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    return coroutine


async def _discover_sdk_resources(
    *,
    working_directory: Path | str,
    cli_path: str | None,
    cli_url: str | None,
    github_token: str | None,
    client_factory: Callable[..., Any] | None,
    force_refresh: bool,
    timeout: float,
) -> ResourceSnapshot:
    root = str(Path(working_directory).expanduser().resolve())
    runtime = _runtime_cache_key(cli_path, cli_url)
    cache_key = (runtime, root)
    if not force_refresh and cache_key in _CACHE:
        return _CACHE[cache_key]

    if client_factory is None:
        from ..copilot_client_factory import create_copilot_client

        client_factory = create_copilot_client

    deadline = _Deadline(timeout)
    plugin_state: ResourceState = "unverified"
    mcp_state: ResourceState = "unverified"
    skill_state: ResourceState = "unverified"
    skill_ownership_state: ResourceState = "unverified"
    server_plugins: list[Any] = []
    discovered_mcps: list[Any] = []
    server_skills: list[Any] = []
    session_plugins: list[Any] | None = None
    session_skills: list[Any] | None = None
    session: Any = None
    client: Any = None
    started = False

    try:
        try:
            client = client_factory(
                cli_path=cli_path,
                cli_url=cli_url,
                github_token=github_token,
                log_level="error",
                working_directory=root,
            )
        except Exception:
            # 一時的な起動失敗をprocess cacheへ永続化しない（fan-out並行実行時の
            # 増幅を防ぐ）。次回同keyの呼び出しで再度discoveryを試みられるようにする。
            return _empty_snapshot()
        try:
            await deadline.wait(client.start())
            started = True
        except Exception:
            started = False

        if started:
            from copilot.generated.rpc import MCPDiscoverRequest, SkillsDiscoverRequest

            try:
                response = await deadline.wait(
                    client.rpc.mcp.discover(
                        MCPDiscoverRequest(working_directory=root),
                        timeout=deadline.remaining(),
                    )
                )
                discovered_mcps = _require_list(getattr(response, "servers", None))
                discovered_mcp_names = [
                    _safe_text(getattr(server, "name", None))
                    for server in discovered_mcps
                ]
                # name 欠落と enabled の型崩れはどちらも response schema の検証失敗であり、
                # 未設定と捏造せず unverified のままにする（FR-TS-12 / FR-CLI-91）。
                if all(discovered_mcp_names) and all(
                    isinstance(getattr(server, "enabled", None), bool)
                    for server in discovered_mcps
                ):
                    mcp_state = "ready"
            except Exception:
                discovered_mcps = []
                discovered_mcp_names = []

            try:
                response = await deadline.wait(
                    client.rpc.plugins.list(timeout=deadline.remaining())
                )
                server_plugins = _require_list(getattr(response, "plugins", None))
                plugin_state = "ready"
            except Exception:
                server_plugins = []

            try:
                response = await deadline.wait(
                    client.rpc.skills.discover(
                        SkillsDiscoverRequest(project_paths=[root]),
                        timeout=deadline.remaining(),
                    )
                )
                server_skills = _require_list(getattr(response, "skills", None))
                skill_state = (
                    "unverified" if (getattr(response, "errors", None) or ()) else "ready"
                )
            except Exception:
                server_skills = []

            if mcp_state == "ready":
                try:
                    session = await deadline.wait(
                        client.create_session(
                            working_directory=root,
                            enable_config_discovery=True,
                            request_extensions=False,
                            enable_skills=True,
                            disabled_mcp_servers=sorted(set(discovered_mcp_names)),
                        )
                    )
                except Exception:
                    session = None

            if session is not None:
                try:
                    response = await deadline.wait(
                        session.rpc.plugins.list(timeout=deadline.remaining())
                    )
                    session_plugins = list(getattr(response, "plugins", None) or ())
                except Exception:
                    session_plugins = None

                try:
                    response = await deadline.wait(
                        session.rpc.skills.list(timeout=deadline.remaining())
                    )
                    session_skills = list(getattr(response, "skills", None) or ())
                except Exception:
                    session_skills = None

        plugins = _plugin_items(server_plugins)
        mcp_servers = _mcp_items(discovered_mcps, server_plugins)
        skills, unresolved_due_to_session = _skill_items(
            server_skills,
            server_plugins,
            session_plugins,
            session_skills,
        )
        plugin_skill_present = any(item.source_kind == "plugin" for item in skills)
        if not plugin_skill_present or (
            session_plugins is not None and session_skills is not None
        ):
            skill_ownership_state = "ready"
        if unresolved_due_to_session:
            skill_ownership_state = "unverified"

        snapshot = ResourceSnapshot(
            plugin_state=plugin_state,
            mcp_state=mcp_state,
            skill_state=skill_state,
            skill_ownership_state=skill_ownership_state,
            plugins=plugins,
            mcp_servers=mcp_servers,
            skills=skills,
        )
        # client.start()自体が失敗した場合だけprocess cacheへ保持しない。
        # fan-out並行実行時の一時的な接続失敗（resource contention）が
        # 同一(runtime, root)キーの以後すべての呼び出しへ永続的に伝播することを防ぐ
        # （D-01B）。client起動後に判明した個別kindのunverified（discover自体の
        # schema不正等）は環境の安定した特性であり得るため、既存どおりcacheする。
        # 共有 deadline の期限切れで欠けた snapshot は一時的な負荷の結果であり、
        # 以後の caller へ継承させない（resume 並列起動時の unverified 固定化の防止）。
        if started and not deadline.expired:
            _CACHE[cache_key] = snapshot
        return snapshot
    finally:
        if session is not None:
            try:
                await deadline.wait(session.disconnect())
            except Exception:
                pass
        if client is not None:
            try:
                await deadline.wait(client.stop())
            except Exception:
                pass


def _runtime_cache_key(cli_path: str | None, cli_url: str | None = None) -> str:
    endpoint = f"|{cli_url}" if cli_url else ""
    if not cli_path:
        return f"<sdk-default>{endpoint}"
    return f"{Path(cli_path).expanduser().resolve()}{endpoint}"


def _empty_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        plugin_state="unverified",
        mcp_state="unverified",
        skill_state="unverified",
        skill_ownership_state="unverified",
        plugins=(),
        mcp_servers=(),
        skills=(),
    )


def _require_list(value: Any) -> list[Any]:
    """応答が list でなければ schema 検証失敗として扱う（0 件と混同しない）。"""
    if not isinstance(value, list):
        raise TypeError("SDK response field is not a list")
    return list(value)


def _safe_text(value: Any) -> str | None:
    """任意 object の ``str`` / ``repr`` を呼ばず、安全な文字列だけを受理する。"""
    if isinstance(value, str):
        return value
    if isinstance(value, Enum) and isinstance(value.value, str):
        return value.value
    return None


def _source(value: Any) -> str:
    return _safe_text(value) or "unknown"


def _enabled(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _plugin_identity(plugin: Any) -> tuple[str, str, bool, str | None] | None:
    name = _safe_text(getattr(plugin, "name", None))
    marketplace = _safe_text(getattr(plugin, "marketplace", None))
    if name is None or marketplace is None:
        return None
    return (
        name,
        marketplace,
        _enabled(getattr(plugin, "enabled", None)),
        _safe_text(getattr(plugin, "version", None)),
    )


def _unique_plugin(name: str, plugins: list[Any]) -> Any | None:
    matches = [plugin for plugin in plugins if _safe_text(getattr(plugin, "name", None)) == name]
    return matches[0] if len(matches) == 1 else None


def _plugin_items(plugins: list[Any]) -> tuple[ResourceItem, ...]:
    items: list[ResourceItem] = []
    for plugin in plugins:
        name = _safe_text(getattr(plugin, "name", None))
        marketplace = _safe_text(getattr(plugin, "marketplace", None))
        if name is None:
            continue
        items.append(
            ResourceItem(
                kind="plugin",
                name=name,
                enabled=_enabled(getattr(plugin, "enabled", None)),
                source_kind="marketplace" if marketplace else "direct",
                plugin_marketplace=marketplace or None,
                plugin_version=_safe_text(getattr(plugin, "version", None)),
            )
        )
    return tuple(items)


def _mcp_items(mcps: list[Any], plugins: list[Any]) -> tuple[ResourceItem, ...]:
    items: list[ResourceItem] = []
    for mcp in mcps:
        name = _safe_text(getattr(mcp, "name", None))
        source_kind = _source(getattr(mcp, "source", None))
        if name is None:
            continue
        owner: str | None = None
        marketplace: str | None = None
        version: str | None = None
        if source_kind == "plugin":
            candidate = _safe_text(getattr(mcp, "source_plugin", None))
            plugin = _unique_plugin(candidate, plugins) if candidate is not None else None
            if plugin is not None:
                owner = candidate
                marketplace = _safe_text(getattr(plugin, "marketplace", None)) or None
                version = _safe_text(getattr(mcp, "source_plugin_version", None))
        items.append(
            ResourceItem(
                kind="mcp_server",
                name=name,
                enabled=_enabled(getattr(mcp, "enabled", None)),
                source_kind=source_kind,
                plugin_marketplace=marketplace,
                owner_plugin=owner,
                plugin_version=version,
            )
        )
    return tuple(items)


def _skill_items(
    skills: list[Any],
    server_plugins: list[Any],
    session_plugins: list[Any] | None,
    session_skills: list[Any] | None,
) -> tuple[tuple[ResourceItem, ...], bool]:
    items: list[ResourceItem] = []
    unresolved_due_to_session = False
    for skill in skills:
        name = _safe_text(getattr(skill, "name", None))
        source_kind = _source(getattr(skill, "source", None))
        if name is None:
            continue
        owner: str | None = None
        marketplace: str | None = None
        version: str | None = None
        if source_kind == "plugin":
            if session_plugins is None or session_skills is None:
                unresolved_due_to_session = True
            else:
                owner, marketplace, version = _strict_skill_owner(
                    skill,
                    server_plugins,
                    session_plugins,
                    session_skills,
                )
        items.append(
            ResourceItem(
                kind="skill",
                name=name,
                enabled=_enabled(getattr(skill, "enabled", None)),
                source_kind=source_kind,
                plugin_marketplace=marketplace,
                owner_plugin=owner,
                plugin_version=version,
                description=_safe_text(getattr(skill, "description", None)),
            )
        )
    return tuple(items), unresolved_due_to_session


def _strict_skill_owner(
    server_skill: Any,
    server_plugins: list[Any],
    session_plugins: list[Any],
    session_skills: list[Any],
) -> tuple[str | None, str | None, str | None]:
    """server/session の同一証拠が一意な場合だけ Skill owner を補完する。"""
    name = _safe_text(getattr(server_skill, "name", None))
    matches = [
        skill
        for skill in session_skills
        if _safe_text(getattr(skill, "name", None)) == name
    ]
    if len(matches) != 1:
        return None, None, None
    session_skill = matches[0]
    owner = _safe_text(getattr(session_skill, "plugin_name", None))
    if owner is None or _source(getattr(session_skill, "source", None)) != "plugin":
        return None, None, None
    if not _same_skill_evidence(server_skill, session_skill):
        return None, None, None

    server_plugin = _unique_plugin(owner, server_plugins)
    session_plugin = _unique_plugin(owner, session_plugins)
    if server_plugin is None or session_plugin is None:
        return None, None, None
    server_identity = _plugin_identity(server_plugin)
    if server_identity is None or server_identity != _plugin_identity(session_plugin):
        return None, None, None
    return owner, server_identity[1] or None, server_identity[3]


def _same_skill_evidence(server_skill: Any, session_skill: Any) -> bool:
    fields = ("name", "source", "description")
    if any(
        _safe_text(getattr(server_skill, field, None))
        != _safe_text(getattr(session_skill, field, None))
        for field in fields
    ):
        return False
    return _enabled(getattr(server_skill, "enabled", None)) == _enabled(
        getattr(session_skill, "enabled", None)
    )


__all__ = [
    "DEFAULT_DEADLINE_SECONDS",
    "ResourceItem",
    "ResourceSnapshot",
    "discover_sdk_resources",
]
