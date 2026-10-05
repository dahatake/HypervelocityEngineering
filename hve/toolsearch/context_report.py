"""HVE Tool Search — Step 実行セッションのコンテキスト内訳の実測（FR-TS-11）。

`session.metadata.contextInfo`（`toolDefinitionsTokens` は "excludes deferred tools"）と
`session.metadata.getContextAttribution` を唯一の情報源とし、推定トークンでは代替しない。
プロンプトは送らないためモデル推論は発生しない。
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from copilot.generated.rpc import MetadataContextInfoRequest

from ..config import SDKConfig, to_wire_model
from ..copilot_client_factory import create_copilot_client
from ..security import sanitize_diagnostic_text
from .policy import ToolSearchPolicy
from .resource_inventory import discover_sdk_resources
from .resource_routing import create_session_from_route, resolve_resource_route

BUILTIN_LAYER = "(builtin)"
_TOOL_DEFINITION_PREFIX = "toolDefinition:"
_SYSTEM_PROMPT_ID = "system:systemPrompt"

CONNECT_TIMEOUT_SECONDS = 60.0


class ContextReportError(RuntimeError):
    """実測に失敗した。推定値で埋めずに呼び出し側へ返す。"""


@dataclass(frozen=True)
class Layer:
    name: str
    tool_count: int
    tokens: int


@dataclass(frozen=True)
class ContextReport:
    model_name: str
    limit: int
    total_tokens: int
    system_tokens: int
    tool_definitions_tokens: int
    mcp_tools_tokens: int
    conversation_tokens: int
    system_prompt_tokens: int | None
    layers: tuple[Layer, ...]
    unconnected: tuple[str, ...]
    requested_model: str | None = None
    workflow_id: str | None = None
    step_id: str | None = None
    required_mcp_servers: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "requested_model": self.requested_model,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "required_mcp_servers": list(self.required_mcp_servers),
            "required_skills": list(self.required_skills),
            "limit": self.limit,
            "total_tokens": self.total_tokens,
            "system_tokens": self.system_tokens,
            "tool_definitions_tokens": self.tool_definitions_tokens,
            "mcp_tools_tokens": self.mcp_tools_tokens,
            "conversation_tokens": self.conversation_tokens,
            "system_prompt_tokens": self.system_prompt_tokens,
            "layers": [
                {"name": layer.name, "tool_count": layer.tool_count, "tokens": layer.tokens}
                for layer in self.layers
            ],
            "unconnected": list(self.unconnected),
        }


@dataclass(frozen=True)
class ContextRuntimeMeasurement:
    report: ContextReport
    connected_mcp_servers: tuple[str, ...]
    enabled_skills: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "connected_mcp_servers": list(self.connected_mcp_servers),
            "enabled_skills": list(self.enabled_skills),
        }


@dataclass(frozen=True)
class ContextComparison:
    off: ContextRuntimeMeasurement | None
    on: ContextRuntimeMeasurement | None
    comparable: bool
    reason: str | None
    runtime_resources: Mapping[str, Any]
    reduction: Mapping[str, int | float | None]
    off_error: str | None = None
    on_error: str | None = None

    def has_failures(self) -> bool:
        return bool(self.off_error or self.on_error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "off": None if self.off is None else self.off.to_dict(),
            "on": None if self.on is None else self.on.to_dict(),
            "off_error": self.off_error,
            "on_error": self.on_error,
            "comparable": self.comparable,
            "reason": self.reason,
            "runtime_resources": dict(self.runtime_resources),
            "reduction": dict(self.reduction),
        }


def build_report(
    *,
    context_info: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    tools: Sequence[Any],
    connected: Iterable[str],
    declared: Iterable[str],
    requested_model: str | None = None,
    workflow_id: str | None = None,
    step_id: str | None = None,
    required_mcp_servers: Iterable[str] = (),
    required_skills: Iterable[str] = (),
) -> ContextReport:
    server_of = {
        str(getattr(tool, "name", "")): (getattr(tool, "mcp_server_name", None) or BUILTIN_LAYER)
        for tool in tools
    }
    counts: dict[str, int] = {}
    tokens: dict[str, int] = {}
    system_prompt_tokens: int | None = None

    for entry in entries:
        entry_id = str(entry.get("id", ""))
        if entry_id == _SYSTEM_PROMPT_ID:
            system_prompt_tokens = int(entry.get("tokens", 0))
            continue
        if entry.get("kind") != "toolDefinition":
            continue
        name = entry_id[len(_TOOL_DEFINITION_PREFIX):] if entry_id.startswith(
            _TOOL_DEFINITION_PREFIX
        ) else str(entry.get("label", ""))
        server = server_of.get(name, BUILTIN_LAYER)
        counts[server] = counts.get(server, 0) + 1
        tokens[server] = tokens.get(server, 0) + int(entry.get("tokens", 0))

    layers = tuple(
        Layer(name=server, tool_count=counts[server], tokens=tokens[server])
        for server in sorted(counts, key=lambda s: (-tokens[s], s))
    )
    connected_set = {str(name) for name in connected}
    unconnected = tuple(
        name for name in sorted({str(n) for n in declared}) if name not in connected_set
    )
    return ContextReport(
        model_name=str(context_info.get("modelName", "")),
        limit=int(context_info.get("limit", 0)),
        total_tokens=int(context_info.get("totalTokens", 0)),
        system_tokens=int(context_info.get("systemTokens", 0)),
        tool_definitions_tokens=int(context_info.get("toolDefinitionsTokens", 0)),
        mcp_tools_tokens=int(context_info.get("mcpToolsTokens", 0)),
        conversation_tokens=int(context_info.get("conversationTokens", 0)),
        system_prompt_tokens=system_prompt_tokens,
        layers=layers,
        unconnected=unconnected,
        requested_model=requested_model,
        workflow_id=workflow_id,
        step_id=step_id,
        required_mcp_servers=tuple(
            dict.fromkeys(str(name) for name in required_mcp_servers)
        ),
        required_skills=tuple(dict.fromkeys(str(name) for name in required_skills)),
    )


def _layer_label(name: str) -> str:
    return "組み込みツール定義 (builtin)" if name == BUILTIN_LAYER else name


def render_text(report: ContextReport) -> str:
    lines = [
        "Step 実行セッションのコンテキスト内訳（実測）",
        f"  Workflow              : {report.workflow_id or '未指定'}",
        f"  Step                  : {report.step_id or 'Workflow 全体'}",
        f"  Required MCP          : {', '.join(report.required_mcp_servers) or 'なし'}",
        f"  Required Skill        : {', '.join(report.required_skills) or 'なし'}",
        f"  モデル (トークナイザ): {report.model_name}",
        f"  セッションの設定モデル: {report.requested_model or '未指定 (SDK 既定)'}",
        f"  コンテキスト上限      : {report.limit:,} tokens",
        "",
        f"  合計                  : {report.total_tokens:,} tokens",
        f"  システムプロンプト等  : {report.system_tokens:,} tokens",
        f"  ツール定義            : {report.tool_definitions_tokens:,} tokens",
        f"  うち MCP              : {report.mcp_tools_tokens:,} tokens",
        f"  会話                  : {report.conversation_tokens:,} tokens",
        "",
        "  ツール定義の層別内訳（上記とは別のトークナイザで計測されるため合計は一致しない）",
        f"  {'層':<28}{'ツール数':>8}{'tokens':>12}",
    ]
    for layer in report.layers:
        lines.append(f"  {_layer_label(layer.name):<28}{layer.tool_count:>8}{layer.tokens:>12,}")
    if not report.layers:
        lines.append("  (データ不足)")
    lines += ["", "  未接続の宣言済み MCP サーバー"]
    lines.append("  " + (", ".join(report.unconnected) if report.unconnected else "なし"))
    return "\n".join(lines)


def render_json(report: ContextReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _null_reduction() -> dict[str, int | float | None]:
    return {
        "total_tokens_saved": None,
        "total_tokens_rate": None,
        "tool_definitions_tokens_saved": None,
        "tool_definitions_tokens_rate": None,
    }


def _rate(*, saved: int, baseline: int) -> float | None:
    if baseline == 0:
        return None
    return saved / baseline


def build_comparison(
    *,
    off: ContextRuntimeMeasurement | None,
    on: ContextRuntimeMeasurement | None,
    off_error: str | None = None,
    on_error: str | None = None,
) -> ContextComparison:
    runtime_resources: dict[str, Any] = {
        "off_connected_mcp_servers": None if off is None else list(off.connected_mcp_servers),
        "on_connected_mcp_servers": None if on is None else list(on.connected_mcp_servers),
        "off_enabled_skills": None if off is None else list(off.enabled_skills),
        "on_enabled_skills": None if on is None else list(on.enabled_skills),
        "connected_mcp_servers_match": None,
        "enabled_skills_match": None,
    }
    comparable = False
    reason = None
    reduction = _null_reduction()

    if off_error or on_error:
        reason = "measurement_failed"
    elif off is None or on is None:
        reason = "measurement_missing"
    else:
        mcp_match = off.connected_mcp_servers == on.connected_mcp_servers
        skills_match = off.enabled_skills == on.enabled_skills
        runtime_resources["connected_mcp_servers_match"] = mcp_match
        runtime_resources["enabled_skills_match"] = skills_match
        if not mcp_match or not skills_match:
            reason = "runtime_resource_drift"
        else:
            comparable = True
            total_tokens_saved = off.report.total_tokens - on.report.total_tokens
            tool_definitions_tokens_saved = (
                off.report.tool_definitions_tokens - on.report.tool_definitions_tokens
            )
            reduction = {
                "total_tokens_saved": total_tokens_saved,
                "total_tokens_rate": _rate(
                    saved=total_tokens_saved,
                    baseline=off.report.total_tokens,
                ),
                "tool_definitions_tokens_saved": tool_definitions_tokens_saved,
                "tool_definitions_tokens_rate": _rate(
                    saved=tool_definitions_tokens_saved,
                    baseline=off.report.tool_definitions_tokens,
                ),
            }

    return ContextComparison(
        off=off,
        on=on,
        comparable=comparable,
        reason=reason,
        runtime_resources=runtime_resources,
        reduction=reduction,
        off_error=off_error,
        on_error=on_error,
    )


def render_comparison_json(comparison: ContextComparison) -> str:
    return json.dumps(comparison.to_dict(), ensure_ascii=False, indent=2)


def render_comparison_text(comparison: ContextComparison) -> str:
    def _format_measurement(
        label: str,
        measurement: ContextRuntimeMeasurement | None,
        error: str | None,
    ) -> list[str]:
        lines = [f"{label}:"]
        if measurement is None:
            lines.append(f"  実測失敗: {error}" if error else "  実測値なし")
            return lines
        lines.append(f"  接続 MCP   : {', '.join(measurement.connected_mcp_servers) or 'なし'}")
        lines.append(f"  有効 Skill : {', '.join(measurement.enabled_skills) or 'なし'}")
        lines.extend(f"  {line}" for line in render_text(measurement.report).splitlines())
        return lines

    lines = [
        "Tool Search OFF / ON コンテキスト比較（実測）",
        f"  判定: {'比較可能' if comparison.comparable else '比較不能'}",
        f"  comparable: {'true' if comparison.comparable else 'false'}",
        f"  reason: {comparison.reason or 'none'}",
    ]
    if comparison.comparable:
        lines.extend(
            (
                f"  total_tokens_saved: {comparison.reduction['total_tokens_saved']}",
                f"  total_tokens_rate: {comparison.reduction['total_tokens_rate']}",
                f"  tool_definitions_tokens_saved: {comparison.reduction['tool_definitions_tokens_saved']}",
                f"  tool_definitions_tokens_rate: {comparison.reduction['tool_definitions_tokens_rate']}",
            )
        )
    else:
        lines.append("  削減値: 算出なし（比較不能）")
    lines.append("")
    lines.extend(_format_measurement("OFF", comparison.off, comparison.off_error))
    lines.append("")
    lines.extend(_format_measurement("ON", comparison.on, comparison.on_error))
    return "\n".join(lines)


async def _connected_servers(session: Any) -> set[str]:
    listing = await session.rpc.mcp.list(timeout=CONNECT_TIMEOUT_SECONDS)
    servers = getattr(listing, "servers", None)
    if not isinstance(servers, (list, tuple)):
        raise ContextReportError("MCP runtime schema is invalid.")
    connected: set[str] = set()
    for server in servers:
        status = getattr(server, "status", None)
        if str(getattr(status, "value", status) or "").casefold() != "connected":
            continue
        name = getattr(server, "name", None)
        if not isinstance(name, str) or not name:
            raise ContextReportError("MCP runtime schema is invalid.")
        connected.add(name)
    return connected


async def _enabled_skills(session: Any) -> tuple[str, ...]:
    response = await session.rpc.skills.list()
    skills = getattr(response, "skills", None)
    if not isinstance(skills, (list, tuple)):
        raise ContextReportError("Skill runtime schema is invalid.")
    enabled: list[str] = []
    for skill in skills:
        name = getattr(skill, "name", None)
        flag = getattr(skill, "enabled", None)
        if not isinstance(name, str) or not isinstance(flag, bool):
            raise ContextReportError("Skill runtime schema is invalid.")
        if flag and name not in enabled:
            enabled.append(name)
    return tuple(sorted(enabled))


def session_options(config: Any) -> dict[str, Any]:
    opts: dict[str, Any] = {"streaming": True}
    wire_model = to_wire_model(getattr(config, "model", None))
    if wire_model:
        opts["model"] = wire_model
    tier = getattr(config, "context_tier", None)
    if tier:
        opts["context_tier"] = tier
    return opts


def _normalized_defer_threshold(config: Any) -> int | None:
    raw = getattr(config, "tool_search_defer_threshold", None)
    if raw is None:
        return None
    try:
        threshold = int(raw)
    except (TypeError, ValueError):
        return None
    return threshold if threshold > 0 else None


async def _measure_once(
    *,
    repo_root: Path,
    config: Any,
    session_options: Mapping[str, Any],
    workflow_id: str,
    route: Any,
    tool_search_enabled: bool,
    tool_search_defer_threshold: int | None,
    step_id: str | None = None,
) -> ContextRuntimeMeasurement:
    client = None
    session = None
    try:
        client = create_copilot_client(
            cli_path=config.cli_path,
            cli_url=config.cli_url,
            github_token=config.resolve_token() or None,
            log_level="error",
            cli_args=getattr(config, "cli_args", []),
        )
        await client.start()
        session = await create_session_from_route(
            client=client,
            session_options=dict(session_options),
            route=route,
            tool_search_enabled=tool_search_enabled,
            tool_search_defer_threshold=tool_search_defer_threshold,
        )
        declared = set(getattr(route, "enabled_mcp_servers", ()))
        # Routing initialized selected MCPs, even if all were subsequently disabled.
        if not declared:
            await session.rpc.tools.initialize_and_validate(timeout=CONNECT_TIMEOUT_SECONDS)
        connected = await _connected_servers(session)
        info = await session.rpc.metadata.context_info(
            MetadataContextInfoRequest(output_token_limit=0, prompt_token_limit=0),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
        attribution = await session.rpc.metadata.get_context_attribution(
            timeout=CONNECT_TIMEOUT_SECONDS
        )
        metadata = await session.rpc.tools.get_current_metadata(timeout=CONNECT_TIMEOUT_SECONDS)
        if info.context_info is None:
            raise ContextReportError(
                "ランタイムがコンテキスト内訳を返しませんでした。"
                "SDK の metadata.context_info は、セッションが未初期化（最初のターン前でシステムプロンプトと"
                "ツール情報が未キャッシュ）の間は null を返します。モデル呼び出しは課金されるため、"
                "このコマンドでは送信しません。"
            )
        entries = [
            entry.to_dict()
            for entry in (
                attribution.context_attribution.entries
                if attribution.context_attribution is not None
                else []
            )
        ]
        report = build_report(
            context_info=info.context_info.to_dict(),
            entries=entries,
            tools=list(metadata.tools or []),
            connected=connected,
            declared=declared,
            requested_model=session_options.get("model"),
            workflow_id=workflow_id,
            step_id=step_id,
            required_mcp_servers=getattr(route, "required_mcp_servers", ()),
            required_skills=getattr(route, "required_skills", ()),
        )
        return ContextRuntimeMeasurement(
            report=report,
            connected_mcp_servers=tuple(sorted(connected)),
            enabled_skills=await _enabled_skills(session),
        )
    except ContextReportError:
        raise
    except Exception as exc:
        detail = sanitize_diagnostic_text(str(exc))
        suffix = f": {detail}" if detail else ""
        raise ContextReportError(
            f"実測に失敗しました: {type(exc).__name__}{suffix}"
        ) from exc
    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception:
                pass
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass


async def _prepare_measurement_context(
    *,
    repo_root: Path | str,
    workflow_id: str,
    step_id: str | None = None,
) -> tuple[Path, Any, dict[str, Any], Any]:
    try:
        required_skills: tuple[str, ...] = ()
        optional_skills: tuple[str, ...] = ()
        if step_id:
            from ..skill_resolver import (
                get_optional_skills_for_step,
                get_required_skills_for_step,
            )
            from ..workflow_registry import get_step

            base_step_id = str(step_id).split("/", 1)[0]
            step = get_step(workflow_id, base_step_id)
            if step is None:
                raise ContextReportError(
                    f"unknown Step for workflow {workflow_id!r}: {step_id!r}"
                )
            if getattr(step, "is_container", False):
                raise ContextReportError(
                    f"container Step cannot be measured for workflow "
                    f"{workflow_id!r}: {step_id!r}"
                )
            required_skills = tuple(
                get_required_skills_for_step(
                    workflow_id=workflow_id,
                    step_id=base_step_id,
                    step_declared_required=list(
                        getattr(step, "required_skills", ()) or ()
                    ),
                )
            )
            optional_skills = tuple(
                get_optional_skills_for_step(workflow_id, base_step_id)
            )
        root = Path(repo_root).resolve()
        config = SDKConfig.from_env()
        opts = session_options(config)
        if step_id:
            from ..runner import StepRunner

            StepRunner._add_required_external_skill_directories(
                opts,
                list(required_skills),
            )
            StepRunner._add_available_optional_external_skill_directories(
                opts,
                list(optional_skills),
            )
        snapshot_result = discover_sdk_resources(
            working_directory=root,
            cli_path=config.cli_path,
            cli_url=config.cli_url,
            github_token=config.resolve_token() or None,
        )
        if inspect.isawaitable(snapshot_result):
            snapshot = await snapshot_result
        else:
            snapshot = snapshot_result
        route = resolve_resource_route(
            snapshot=snapshot,
            policy=ToolSearchPolicy.load(repo_root=root),
            workflow_id=workflow_id,
            required_skills=required_skills,
            optional_skills=optional_skills,
        )
        return root, config, opts, route
    except ContextReportError:
        raise
    except Exception as exc:
        detail = sanitize_diagnostic_text(str(exc))
        suffix = f": {detail}" if detail else ""
        raise ContextReportError(
            f"実測の準備に失敗しました: {type(exc).__name__}{suffix}"
        ) from exc


async def collect(
    *,
    repo_root: Path | str,
    workflow_id: str,
    step_id: str | None = None,
) -> ContextReport:
    root, config, opts, route = await _prepare_measurement_context(
        repo_root=repo_root,
        workflow_id=workflow_id,
        step_id=step_id,
    )
    measurement = await _measure_once(
        repo_root=root,
        config=config,
        session_options=opts,
        workflow_id=workflow_id,
        route=route,
        tool_search_enabled=bool(getattr(config, "tool_search", False)),
        tool_search_defer_threshold=_normalized_defer_threshold(config),
        step_id=step_id,
    )
    return measurement.report


async def collect_comparison(
    *,
    repo_root: Path | str,
    workflow_id: str,
    step_id: str | None = None,
) -> ContextComparison:
    root, config, opts, route = await _prepare_measurement_context(
        repo_root=repo_root,
        workflow_id=workflow_id,
        step_id=step_id,
    )
    off: ContextRuntimeMeasurement | None = None
    on: ContextRuntimeMeasurement | None = None
    off_error: str | None = None
    on_error: str | None = None

    try:
        off = await _measure_once(
            repo_root=root,
            config=config,
            session_options=opts,
            workflow_id=workflow_id,
            route=route,
            tool_search_enabled=False,
            tool_search_defer_threshold=None,
            step_id=step_id,
        )
    except ContextReportError as exc:
        off_error = str(exc)

    try:
        on = await _measure_once(
            repo_root=root,
            config=config,
            session_options=opts,
            workflow_id=workflow_id,
            route=route,
            tool_search_enabled=True,
            tool_search_defer_threshold=_normalized_defer_threshold(config),
            step_id=step_id,
        )
    except ContextReportError as exc:
        on_error = str(exc)

    return build_comparison(off=off, on=on, off_error=off_error, on_error=on_error)


__all__ = [
    "BUILTIN_LAYER",
    "ContextComparison",
    "ContextReport",
    "ContextReportError",
    "ContextRuntimeMeasurement",
    "Layer",
    "build_comparison",
    "build_report",
    "collect",
    "collect_comparison",
    "render_comparison_json",
    "render_comparison_text",
    "render_json",
    "render_text",
]
