"""workiq.py — Work IQ の capability 判定と実行単位の無効化（FR-CLI-81 / FR-CLI-91）。

Work IQ への問い合わせは HVE が組み立てず、知識探索エージェント（FR-KD）が
読み取り専用の知識源として自分で行う。本モジュールに残すのは、Copilot CLI に
設定された exact ``workiq`` の有無の判定、利用できない実行での Work IQ 値の除去、
および SDK tool lifecycle イベントのメタデータ抽出（FR-MCPLOG / FR-KD-04 共通）だけとする。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

WORKIQ_CANONICAL_SERVER_NAME: str = "workiq"
WORKIQ_MCP_SERVER_NAME: str = WORKIQ_CANONICAL_SERVER_NAME
# Work IQ 専用の discovery / cache は持たず、FR-TS-12 の共有 snapshot を射影する。
_WORKIQ_STATIC_PROBE_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class WorkIQToolEventMetadata:
    """SDK tool lifecycleイベントから抽出した安全なメタデータ。"""

    event_type: str
    tool_name: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    mcp_server_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    success: object = None


@dataclass(frozen=True)
class WorkIQCapability:
    """SDK discoveryで確認したWork IQ設定有無の安全なsnapshot。"""

    state: str
    reason_code: str
    enabled_server_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkIQDisableResult:
    """実行単位のWork IQ無効化結果。"""

    sources_became_empty: bool = False


def _capability(
    state: str,
    *,
    enabled_server_names: Sequence[str] = (),
) -> WorkIQCapability:
    """外部通知へ許可されたstate/reasonだけを持つsnapshotを作る。"""
    return WorkIQCapability(
        state=state,
        reason_code=state,
        enabled_server_names=tuple(enabled_server_names),
    )


def probe_workiq_plugin_capability(
    *,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
    github_token: Optional[str] = None,
    timeout: float = _WORKIQ_STATIC_PROBE_TIMEOUT_SECONDS,
    working_directory: str | Path | None = None,
    client_factory: Optional[Callable[..., Any]] = None,
    force_refresh: bool = False,
) -> WorkIQCapability:
    """FR-TS-12 の共有 snapshot から exact ``workiq`` の設定有無だけを射影する。

    Work IQ 専用の client start / ``mcp.discover`` / cache は持たず、
    process 共有 snapshot の MCP 部分だけを読む互換 adapter である。
    snapshot の MCP が ``unverified`` なら不在と捏造せず ``unverified`` を返す。
    """
    try:
        probe_cwd = str(Path(working_directory or Path.cwd()).resolve())
    except (OSError, RuntimeError):
        return _capability("unverified")

    try:
        snapshot = _resolve_resource_snapshot_sync(
            working_directory=probe_cwd,
            cli_path=cli_path,
            cli_url=cli_url,
            github_token=github_token,
            client_factory=client_factory,
            force_refresh=force_refresh,
            timeout=timeout,
        )
    except Exception:
        return _capability("unverified")
    return workiq_capability_from_snapshot(snapshot)


def workiq_capability_from_snapshot(snapshot: Any) -> WorkIQCapability:
    """共有 resource snapshot を ``WorkIQCapability`` へ射影する。

    Plugin / Skill 側の取得可否は Work IQ の判定に影響させない（FR-TS-12 の
    kind 独立契約）。
    """
    if getattr(snapshot, "mcp_state", None) != "ready":
        return _capability("unverified")

    enabled_names: set[str] = set()
    for item in getattr(snapshot, "mcp_servers", None) or ():
        name = getattr(item, "name", None)
        if not isinstance(name, str) or not name:
            return _capability("unverified")
        if getattr(item, "enabled", None) is True:
            enabled_names.add(name)

    state = (
        "ready" if WORKIQ_CANONICAL_SERVER_NAME in enabled_names else "not-configured"
    )
    return _capability(state, enabled_server_names=tuple(sorted(enabled_names)))


def _resolve_resource_snapshot_sync(**kwargs: Any) -> Any:
    """同期 entrypoint から共有 snapshot を取得し、既存 event loop を入れ子にしない。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _discover_resources(**kwargs)

    result: list[Any] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            result.append(_discover_resources(**kwargs))
        except BaseException as exc:  # 呼出側でunverifiedへ正規化する
            errors.append(exc)

    worker = threading.Thread(target=run, name="hve-workiq-discovery", daemon=True)
    worker.start()
    worker.join()
    if errors:
        raise errors[0]
    if not result:
        raise RuntimeError("Work IQ discovery returned no result")
    return result[0]


def _discover_resources(**kwargs: Any) -> Any:
    """worker thread 側で loop を持たないことを前提に共有実装を呼ぶ。"""
    try:
        from .toolsearch.resource_inventory import discover_sdk_resources
    except ImportError:  # pragma: no cover - flat-load compatibility
        from toolsearch.resource_inventory import discover_sdk_resources  # type: ignore[import-not-found,no-redef]

    snapshot = discover_sdk_resources(**kwargs)
    if inspect.isawaitable(snapshot):  # pragma: no cover - loop 無し前提で到達しない
        snapshot.close()  # type: ignore[attr-defined]
        raise RuntimeError("resource snapshot must be resolved outside a running loop")
    return snapshot


def _without_workiq_source(value: object) -> tuple[object, bool]:
    """sources値からworkiqだけを除去し、明示値が空になったか返す。"""
    valid_non_workiq = {"qa", "original-docs", "both"}
    if isinstance(value, str):
        tokens = [part.strip() for part in re.split(r"[,\s]+", value) if part.strip()]
        kept = [token for token in tokens if token.lower() != "workiq"]
        has_effective_source = any(
            token.strip().lower() in valid_non_workiq for token in kept
        )
        return (",".join(kept) or None), bool(tokens and not has_effective_source)
    if isinstance(value, (list, tuple, set)):
        tokens = list(value)
        kept = [token for token in tokens if str(token).strip().lower() != "workiq"]
        if isinstance(value, tuple):
            normalized: object = tuple(kept)
        elif isinstance(value, set):
            normalized = set(kept)
        else:
            normalized = kept
        has_effective_source = any(
            str(token).strip().lower() in valid_non_workiq for token in kept
        )
        return normalized, bool(tokens and not has_effective_source)
    return value, False


def _without_workiq_name(value: object) -> object:
    """``knowledge_sources``（文字列または列）から ``workiq`` だけを除く。"""
    if isinstance(value, str):
        kept = [t.strip() for t in value.split(",") if t.strip() and t.strip() != "workiq"]
        return ",".join(kept) or None
    if isinstance(value, (list, tuple)):
        kept_list = [t for t in value if str(t).strip() != "workiq"]
        return tuple(kept_list) if isinstance(value, tuple) else kept_list
    return value


def disable_workiq_for_run(
    target: object,
    params: Optional[dict[str, Any]] = None,
) -> WorkIQDisableResult:
    """保存元を変えず、渡されたruntime object/dictのWork IQ値だけを除去する。

    対象は ``workiq`` / ``workiq_enabled``、``knowledge_sources`` 中の ``workiq``、
    AKM ``sources`` 中の ``workiq``、ARD ``ard_workiq_enabled`` とする（FR-CLI-81 / FR-KD-10）。
    """
    for name in ("workiq", "workiq_enabled"):
        if hasattr(target, name):
            setattr(target, name, False)
    if hasattr(target, "knowledge_sources"):
        setattr(target, "knowledge_sources", _without_workiq_name(getattr(target, "knowledge_sources")))

    sources_became_empty = False
    if hasattr(target, "sources"):
        normalized, became_empty = _without_workiq_source(getattr(target, "sources"))
        setattr(target, "sources", normalized)
        sources_became_empty = sources_became_empty or became_empty

    if params is not None:
        if "sources" in params:
            normalized, became_empty = _without_workiq_source(params.get("sources"))
            params["sources"] = normalized
            sources_became_empty = sources_became_empty or became_empty
        params["ard_workiq_enabled"] = False

    return WorkIQDisableResult(sources_became_empty=sources_became_empty)


def _get_event_type(event: object) -> Optional[str]:
    """SDK イベントから event.type を文字列として取り出す。"""
    try:
        if isinstance(event, dict):
            etype_obj = event.get("type")
        else:
            etype_obj = getattr(event, "type", None)
        if etype_obj is None:
            return None
        etype = getattr(etype_obj, "value", etype_obj)
        return str(etype) if etype is not None else None
    except Exception:
        return None


def _get_event_data(event: object) -> object:
    """SDK イベントから data を取り出す。"""
    if isinstance(event, dict):
        return event.get("data")
    return getattr(event, "data", None)


def _get_data_value(data: object, *names: str) -> object:
    """イベント data から指定名の最初の非空値を型を保って取り出す。"""
    try:
        if data is None:
            return None
        if isinstance(data, dict):
            for name in names:
                value = data.get(name)
                if value is not None and value != "":
                    return value
            return None
        for name in names:
            value = getattr(data, name, None)
            if value is not None and value != "":
                return value
        return None
    except Exception:
        return None


def _get_data_field(data: object, *names: str) -> Optional[str]:
    """イベント data からcanonicalなplain stringだけを取り出す。"""
    value = _get_data_value(data, *names)
    if type(value) is not str or not value or value != value.strip():
        return None
    return value


def extract_tool_metadata_from_event(event: object) -> Optional[WorkIQToolEventMetadata]:
    """SDK tool lifecycleイベントから相関可能なメタデータを抽出する。

    startではMCP server/tool名とcall ID、completeではcall IDとsuccessを取得する。
    Work IQ判定は別helperがstartのexact identityで行う。
    """
    try:
        event_type = _get_event_type(event)
        if event_type not in {"tool.execution_start", "tool.execution_complete"}:
            return None
        data = _get_event_data(event)
        if data is None:
            return None
        tool_call_id = _get_data_field(data, "tool_call_id", "toolCallId")
        if event_type == "tool.execution_complete":
            return WorkIQToolEventMetadata(
                event_type=event_type,
                tool_call_id=tool_call_id,
                success=_get_data_value(data, "success"),
            )
        legacy_tool_name = _get_data_field(data, "tool_name", "toolName", "name")
        mcp_tool_name = _get_data_field(data, "mcp_tool_name", "mcpToolName")
        mcp_server_name = _get_data_field(data, "mcp_server_name", "mcpServerName")
        tool_name = mcp_tool_name or legacy_tool_name
        if not tool_name and not mcp_server_name and tool_call_id is None:
            return None
        return WorkIQToolEventMetadata(
            event_type=event_type,
            tool_name=tool_name,
            mcp_tool_name=mcp_tool_name,
            mcp_server_name=mcp_server_name,
            tool_call_id=tool_call_id,
        )
    except Exception:
        return None


def extract_tool_name_from_event(event: object) -> Optional[str]:
    """SDK イベントオブジェクトからツール名を抽出する共通ヘルパー。

    従来の ``tool_name`` / ``toolName`` / ``name`` に加え、MCP tool イベントの
    ``mcp_tool_name`` / ``mcpToolName`` に対応する。

    Returns:
        ツール名文字列、または抽出できない場合は None。
    """
    metadata = extract_tool_metadata_from_event(event)
    return metadata.tool_name if metadata else None
