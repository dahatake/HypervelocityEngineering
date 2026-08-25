"""hve/mcp_io_log.py — MCP 通信の入出力ログ（FR-MCPLOG-01〜03）。

Copilot SDK セッションで観測した MCP の入出力を、表示用の切り詰めを行わずに
`work/run/<run-id>/mcp-<サーバー名>.log` へ全文で追記する。実行時 Observability
（`hve/runtime_observability.py`）とは別チャネルであり、FR-RTO-04 の allowlist は
適用しない。認証情報のマスクは `hve/workiq.py` の既存実装へ委譲する（FR-MAINT-07）。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from . import runtime_observability as _rto
except ImportError:  # pragma: no cover - script 実行経路
    import runtime_observability as _rto  # type: ignore[no-redef]

try:
    from .workiq import (
        _sanitize_diagnostic_text as _sanitize,
        extract_tool_metadata_from_event,
    )
except ImportError:  # pragma: no cover - script 実行経路
    from workiq import (  # type: ignore[no-redef]
        _sanitize_diagnostic_text as _sanitize,
        extract_tool_metadata_from_event,
    )

DEFAULT_MAX_BYTES = 32 * 1024 * 1024

_FILENAME_PREFIX = "mcp-"
_FILENAME_SUFFIX = ".log"
_HEADER_PREFIX = "=== "
_FIELD_SEPARATOR = " | "

_RECORD_MCP_REQUEST = "mcp_request"
_RECORD_MCP_RESPONSE = "mcp_response"
_RECORD_SERVER_STATUS = "mcp_server_status"
_RECORD_SESSION_PROMPT = "session_prompt"
_RECORD_SESSION_RESPONSE = "session_response"

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_server_name(name: str) -> str:
    """MCP サーバー名をファイル名に使える文字へ正規化する（別名へは写像しない）。"""
    cleaned = _UNSAFE_NAME_CHARS.sub("_", str(name or "").strip())
    return cleaned or "unknown"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class McpIoLogger:
    """MCP サーバーごとの追記ロガー。書き込み失敗を実行へ波及させない。"""

    def __init__(
        self,
        work_root: Optional[Path],
        *,
        dry_run: bool = False,
        max_bytes: int = DEFAULT_MAX_BYTES,
        warn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.pid = os.getpid()
        self._work_root = Path(work_root) if work_root is not None else None
        self._max_bytes = int(max_bytes)
        self._warn = warn
        self._lock = threading.Lock()
        self._handles: Dict[str, Any] = {}
        self._paths: Dict[str, Path] = {}
        self._written: Dict[str, int] = {}
        self._capped: set[str] = set()
        # (step_id, tool_call_id) -> (server, tool)。完了イベントの帰属に使う。
        self._pending: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._closed = False
        self._enabled = work_root is not None and not dry_run
        self._pid_suffix = _rto.is_child_process()

    @classmethod
    def from_env(
        cls,
        *,
        dry_run: bool = False,
        warn: Optional[Callable[[str], None]] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> "McpIoLogger":
        """FR-MCPLOG-02: `HVE_WORK_ROOT` 未設定時は無効化する。"""
        raw = os.environ.get("HVE_WORK_ROOT", "").strip()
        return cls(
            Path(raw) if raw else None,
            dry_run=dry_run,
            warn=warn,
            max_bytes=max_bytes,
        )

    # -- 状態 -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._closed

    def path_for(self, server: str) -> Optional[Path]:
        return self._paths.get(sanitize_server_name(server))

    # -- 記録 -----------------------------------------------------------

    def record_tool_request(
        self,
        server: str,
        tool: str,
        *,
        tool_call_id: str,
        step_id: str = "",
        arguments: Any = None,
    ) -> bool:
        written = self._write(
            server,
            _RECORD_MCP_REQUEST,
            [("tool", tool), ("call_id", tool_call_id), ("step", step_id)],
            _format_arguments(arguments),
        )
        if written and tool_call_id:
            with self._lock:
                self._pending[(step_id or "", str(tool_call_id))] = (
                    str(server),
                    str(tool or ""),
                )
        return written

    def record_tool_response(
        self,
        *,
        tool_call_id: str,
        success: bool,
        content: str = "",
        error: str = "",
        step_id: str = "",
    ) -> bool:
        with self._lock:
            correlated = self._pending.pop(
                (step_id or "", str(tool_call_id or "")), None
            )
        if correlated is None:
            # SDK の完了イベントは MCP サーバー名を持たないため、相関できない完了は
            # MCP 由来か組み込みツール由来かを判別できない（FR-MCPLOG-01）。
            return False
        server, tool = correlated
        return self._write(
            server,
            _RECORD_MCP_RESPONSE,
            [
                ("tool", tool),
                ("call_id", tool_call_id),
                ("success", "true" if success else "false"),
                ("step", step_id),
            ],
            content if success else (error or content),
        )

    def record_server_status(
        self,
        server: str,
        *,
        status: str,
        error: str = "",
        plugin_name: str = "",
        transport: str = "",
        source: str = "",
    ) -> bool:
        return self._write(
            server,
            _RECORD_SERVER_STATUS,
            [
                ("status", status),
                ("plugin", plugin_name),
                ("transport", transport),
                ("source", source),
            ],
            error,
        )

    def record_session_prompt(self, server: str, label: str, prompt: str) -> bool:
        if not prompt or not str(prompt).strip():
            return False
        return self._write(
            server, _RECORD_SESSION_PROMPT, [("label", label)], prompt
        )

    def record_session_response(self, server: str, label: str, response: str) -> bool:
        if not response or not str(response).strip():
            return False
        return self._write(
            server, _RECORD_SESSION_RESPONSE, [("label", label)], response
        )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            handles = list(self._handles.values())
            self._handles.clear()
        for handle in handles:
            try:
                handle.close()
            except OSError:
                pass

    # -- 内部 -----------------------------------------------------------

    def _write(
        self,
        server: str,
        kind: str,
        meta: List[Tuple[str, Any]],
        body: Any,
    ) -> bool:
        if not self.enabled:
            return False
        record = _build_record(server, kind, meta, body)
        encoded = len(record.encode("utf-8"))
        key = sanitize_server_name(server)

        with self._lock:
            if self._closed or key in self._capped:
                return False
            handle = self._open(key)
            if handle is None:
                return False
            if self._written[key] + encoded > self._max_bytes:
                self._capped.add(key)
                self._emit_warning(
                    f"MCP 通信ログ: {self._max_bytes} バイト上限に達したため追記を停止しました"
                    f"（{self._paths[key]}）"
                )
                return False
            try:
                handle.write(record)
                handle.flush()
            except (OSError, ValueError):
                self._drop_handle(key)
                return False
            self._written[key] += encoded
        return True

    def _open(self, key: str) -> Optional[Any]:
        handle = self._handles.get(key)
        if handle is not None:
            return handle
        if self._work_root is None:
            return None
        suffix = f"-{self.pid}" if self._pid_suffix else ""
        try:
            self._work_root.mkdir(parents=True, exist_ok=True)
            path = self._work_root / f"{_FILENAME_PREFIX}{key}{suffix}{_FILENAME_SUFFIX}"
            self._written[key] = path.stat().st_size if path.exists() else 0
            handle = path.open("a", encoding="utf-8", newline="\n")
        except OSError:
            self._enabled = False
            return None
        self._handles[key] = handle
        self._paths[key] = path
        return handle

    def _drop_handle(self, key: str) -> None:
        handle = self._handles.pop(key, None)
        if handle is None:
            return
        try:
            handle.close()
        except OSError:
            pass

    def _emit_warning(self, message: str) -> None:
        if self._warn is None:
            return
        try:
            self._warn(message)
        except Exception:
            pass


def _format_arguments(arguments: Any) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, (dict, list)):
        try:
            return json.dumps(arguments, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(arguments)
    return str(arguments)


def _header_value(value: Any) -> str:
    """ヘッダは 1 行固定のため、外部由来値の改行を潰す（FR-MCPLOG-02）。"""
    return re.sub(r"[\r\n]+", " ", str(value))


def _build_record(server: str, kind: str, meta: List[Tuple[str, Any]], body: Any) -> str:
    parts = [
        f"{_HEADER_PREFIX}{_utc_now_iso()}",
        kind,
        f"server={_header_value(server)}",
    ]
    for name, value in meta:
        if value is None or value == "":
            continue
        parts.append(f"{name}={_header_value(value)}")
    record = _FIELD_SEPARATOR.join(parts) + "\n"
    text = _sanitize(str(body)) if body else ""
    if text.strip():
        # 記録側は LF 固定（FR-MCPLOG-02）。本文由来の CR で行末が混在しないようにする。
        record += text.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"
    return record


# ---------------------------------------------------------------------------
# SDK セッションへの結線
# ---------------------------------------------------------------------------


def attach_mcp_io_event_logger(
    session: Any, logger: Optional[McpIoLogger], *, step_id: str = ""
) -> None:
    """`StepRunner` を経由しないセッション（orchestrator 側）へ記録経路を結線する。"""
    if logger is None or not getattr(logger, "enabled", False):
        return
    on = getattr(session, "on", None)
    if not callable(on):
        return

    def _handler(event: Any) -> None:
        try:
            _record_event(logger, event, step_id=step_id)
        except Exception:
            return

    try:
        on(_handler)
    except Exception:
        return


def _record_event(logger: McpIoLogger, event: Any, *, step_id: str) -> None:
    etype = _event_type(event)
    if etype == "tool.execution_start":
        metadata = extract_tool_metadata_from_event(event)
        if metadata is None or not metadata.mcp_server_name:
            return
        data = _event_data(event)
        logger.record_tool_request(
            metadata.mcp_server_name,
            metadata.tool_name or "",
            tool_call_id=_text(data, "tool_call_id", "toolCallId"),
            step_id=step_id,
            arguments=_value(data, "arguments"),
        )
        return

    if etype == "tool.execution_complete":
        data = _event_data(event)
        logger.record_tool_response(
            tool_call_id=_text(data, "tool_call_id", "toolCallId"),
            success=bool(_value(data, "success")),
            content=_text(_value(data, "result"), "content"),
            error=_error_message(_value(data, "error")),
            step_id=step_id,
        )
        return

    if etype == "session.mcp_servers_loaded":
        for server in _value(_event_data(event), "servers") or ():
            logger.record_server_status(
                _text(server, "name"),
                status=_enum_text(_value(server, "status")),
                error=_text(server, "error"),
                plugin_name=_text(server, "plugin_name", "pluginName"),
                transport=_enum_text(_value(server, "transport")),
                source=_enum_text(_value(server, "source")),
            )
        return

    if etype == "session.mcp_server_status_changed":
        data = _event_data(event)
        logger.record_server_status(
            _text(data, "server_name", "serverName"),
            status=_enum_text(_value(data, "status")),
            error=_text(data, "error"),
        )


def _event_type(event: Any) -> str:
    raw = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    return str(getattr(raw, "value", raw) or "")


def _event_data(event: Any) -> Any:
    return event.get("data") if isinstance(event, dict) else getattr(event, "data", None)


def _value(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            continue
        found = getattr(obj, name, None)
        if found is not None:
            return found
    return None


def _text(obj: Any, *names: str) -> str:
    found = _value(obj, *names)
    return "" if found is None else str(found)


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value) or "")


def _error_message(error: Any) -> str:
    if error is None:
        return ""
    return _text(error, "message") or str(error)


__all__ = [
    "DEFAULT_MAX_BYTES",
    "McpIoLogger",
    "attach_mcp_io_event_logger",
    "sanitize_server_name",
]
