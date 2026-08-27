"""Bounded Copilot SDK runtime for the Repository Query measurement PoC."""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Protocol

from hve.copilot_client_factory import create_copilot_client
from hve.prompt_loader import load_prompt_file
from hve.repository_query_tools import RepositoryQueryLimitError

MAX_CUSTOM_TOOL_CALLS = 6
MAX_LLM_CALLS = 10
MAX_SUBQUERIES_PER_SEARCH = 3
MAX_HITS_PER_SUBQUERY = 3
MAX_REFS_PER_OPEN = 3
MAX_TOKENS_PER_SUBQUERY = 800
MIN_AI_CREDITS = 30.0
_ALLOWED_STATUSES = frozenset({"answered", "partial", "insufficient_evidence"})
_EVIDENCE_ID = re.compile(r"^E[1-9][0-9]*$")
_CITATION = re.compile(r"\[(E[1-9][0-9]*)\]")
_MODEL_FIELDS = frozenset({"status", "grounding", "evidence_ids", "unresolved"})

_SYSTEM_MESSAGE = load_prompt_file("runtime/repository-query/system-message.prompt.md")


class RepositoryQueryError(RuntimeError):
    """Base error for the bounded SDK runtime."""

    usage: dict[str, int] | None = None


class RepositoryQueryConfigurationError(RepositoryQueryError, ValueError):
    """Raised before client creation when fixed execution inputs are invalid."""


class RepositoryQueryOutputError(RepositoryQueryError):
    """Raised when model output cannot be accepted without a repair call."""


class RepositoryQueryExecutionError(RepositoryQueryError):
    """Raised with a sanitized SDK failure category, never raw SDK content."""


class Ledger(Protocol):
    def evidence(self) -> list[dict[str, Any]]: ...


class ToolBundle(Protocol):
    @property
    def ledger(self) -> Ledger: ...

    def sdk_tools(self) -> list[object]: ...

    def activity(self) -> dict[str, int]: ...


@dataclass
class UsageCollector:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    duration_ms: int = 0
    limit_error: RepositoryQueryLimitError | None = None
    abort_task: asyncio.Task[None] | None = None
    session: Any | None = None

    def bind_session(self, session: Any) -> None:
        self.session = session

    def _schedule_limit_abort(self) -> None:
        if self.session is None or self.abort_task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self.abort_task = loop.create_task(_abort_without_masking(self.session))

    async def ensure_limit_abort(self, session: Any) -> None:
        if self.abort_task is None:
            await _abort_without_masking(session)
        else:
            await self.abort_task

    def on_event(self, event: object) -> None:
        event_type = getattr(event, "type", "")
        event_name = getattr(event_type, "value", event_type)
        if event_name != "assistant.usage":
            return
        data = getattr(event, "data", None)
        self.llm_calls += 1
        self.input_tokens += _nonnegative_int(getattr(data, "input_tokens", None))
        self.output_tokens += _nonnegative_int(getattr(data, "output_tokens", None))
        self.cache_read_tokens += _nonnegative_int(
            getattr(data, "cache_read_tokens", None)
        )
        self.cache_write_tokens += _nonnegative_int(
            getattr(data, "cache_write_tokens", None)
        )
        self.duration_ms += _duration_ms(getattr(data, "duration", None))
        if self.llm_calls > MAX_LLM_CALLS:
            if self.limit_error is None:
                self.limit_error = RepositoryQueryLimitError(
                    "llm_calls", MAX_LLM_CALLS, self.llm_calls
                )
            else:
                self.limit_error.actual = self.llm_calls
            self._schedule_limit_abort()

    def to_dict(self, activity: dict[str, int]) -> dict[str, int]:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": int(activity.get("tool_calls", 0)),
            "internal_searches": int(activity.get("internal_searches", 0)),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "duration_ms": self.duration_ms,
        }


def _attach_failure_usage(
    error: RepositoryQueryError | RepositoryQueryLimitError,
    collector: UsageCollector,
    tools: ToolBundle,
) -> None:
    try:
        activity = tools.activity()
    except Exception:
        activity = {}
    error.usage = collector.to_dict(activity)


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _duration_ms(value: object) -> int:
    if isinstance(value, timedelta):
        return max(0, round(value.total_seconds() * 1000))
    return 0


def _validate_configuration(
    *,
    prompt: object,
    model: object,
    reasoning_effort: object,
    max_ai_credits: object,
    timeout: object,
) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise RepositoryQueryConfigurationError("prompt must be a non-empty string")
    if (
        not isinstance(model, str)
        or not model.strip()
        or model.strip().casefold() == "auto"
    ):
        raise RepositoryQueryConfigurationError("a fixed model is required")
    if (
        not isinstance(reasoning_effort, str)
        or not reasoning_effort.strip()
        or reasoning_effort.strip().casefold() == "auto"
    ):
        raise RepositoryQueryConfigurationError("a fixed reasoning effort is required")
    if (
        isinstance(max_ai_credits, bool)
        or not isinstance(max_ai_credits, (int, float))
        or not math.isfinite(float(max_ai_credits))
        or float(max_ai_credits) < MIN_AI_CREDITS
    ):
        raise RepositoryQueryConfigurationError(
            f"max_ai_credits must be at least {MIN_AI_CREDITS:g}"
        )
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or float(timeout) <= 0
    ):
        raise RepositoryQueryConfigurationError("timeout must be positive")


def _session_limits_config(max_ai_credits: float) -> dict[str, float]:
    """Build the SDK limit only after proving this SDK exposes the cap."""
    try:
        from copilot.session import SessionLimitsConfig
    except ImportError:
        raise RepositoryQueryConfigurationError(
            "SDK does not expose SessionLimitsConfig.max_ai_credits"
        ) from None
    annotations = getattr(SessionLimitsConfig, "__annotations__", None)
    if not isinstance(annotations, dict) or "max_ai_credits" not in annotations:
        raise RepositoryQueryConfigurationError(
            "SDK does not expose SessionLimitsConfig.max_ai_credits"
        )
    try:
        limits = SessionLimitsConfig(max_ai_credits=float(max_ai_credits))
    except (TypeError, ValueError):
        raise RepositoryQueryConfigurationError(
            "SDK cannot configure SessionLimitsConfig.max_ai_credits"
        ) from None
    if not isinstance(limits, dict) or limits.get("max_ai_credits") != float(
        max_ai_credits
    ):
        raise RepositoryQueryConfigurationError(
            "SDK cannot configure SessionLimitsConfig.max_ai_credits"
        )
    wire_limits: dict[str, float] = {}
    wire_limits["max_ai_credits"] = float(limits["max_ai_credits"])
    return wire_limits


def _deny_permission(*_args: object, **_kwargs: object) -> object:
    from copilot.session import PermissionDecisionUserNotAvailable

    del _args, _kwargs
    return PermissionDecisionUserNotAvailable()


def _extract_content(event: object) -> str:
    data = getattr(event, "data", None)
    content = getattr(data, "content", None)
    if not isinstance(content, str):
        raise RepositoryQueryOutputError("model response did not contain text content")
    return content


def _validate_model_output(raw: str, ledger_rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RepositoryQueryOutputError("invalid JSON model output") from None
    if not isinstance(payload, dict):
        raise RepositoryQueryOutputError("model output must be a JSON object")
    keys = set(payload)
    unexpected = keys - _MODEL_FIELDS
    missing = _MODEL_FIELDS - keys
    if unexpected:
        raise RepositoryQueryOutputError("unexpected field in model output")
    if missing:
        raise RepositoryQueryOutputError("missing field in model output")

    status = payload["status"]
    grounding = payload["grounding"]
    evidence_ids = payload["evidence_ids"]
    unresolved = payload["unresolved"]
    if status not in _ALLOWED_STATUSES:
        raise RepositoryQueryOutputError("status is not allowed")
    if not isinstance(grounding, str) or not grounding.strip():
        raise RepositoryQueryOutputError("grounding must be non-empty")
    if not isinstance(evidence_ids, list) or not all(
        isinstance(value, str) and _EVIDENCE_ID.fullmatch(value)
        for value in evidence_ids
    ):
        raise RepositoryQueryOutputError("evidence_ids must be an ID list")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise RepositoryQueryOutputError("duplicate evidence_ids are not allowed")
    if not isinstance(unresolved, list) or not all(
        isinstance(value, str) and value.strip() for value in unresolved
    ):
        raise RepositoryQueryOutputError("unresolved must be a string list")
    if status == "answered" and unresolved:
        raise RepositoryQueryOutputError("answered output must have no unresolved items")
    if status in {"partial", "insufficient_evidence"} and not unresolved:
        raise RepositoryQueryOutputError(f"{status} output requires unresolved items")
    if status in {"answered", "partial"} and not evidence_ids:
        raise RepositoryQueryOutputError(f"{status} output requires evidence")
    if status == "insufficient_evidence" and evidence_ids:
        raise RepositoryQueryOutputError(
            "insufficient_evidence output must not cite evidence"
        )

    citations = list(dict.fromkeys(_CITATION.findall(grounding)))
    if citations != evidence_ids:
        raise RepositoryQueryOutputError("citation IDs do not match evidence_ids")
    by_ref: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        if not isinstance(row, dict):
            raise RepositoryQueryOutputError("ledger evidence must be an object")
        ref_id = row.get("ref_id")
        if not isinstance(ref_id, str) or not _EVIDENCE_ID.fullmatch(ref_id):
            raise RepositoryQueryOutputError("ledger evidence has an invalid ref_id")
        if ref_id in by_ref:
            raise RepositoryQueryOutputError("ledger evidence has a duplicate ref_id")
        by_ref[ref_id] = row
    unknown = [ref_id for ref_id in evidence_ids if ref_id not in by_ref]
    if unknown:
        raise RepositoryQueryOutputError(
            f"unknown evidence ID: {unknown[0]}"
        )

    return {
        "status": status,
        "grounding": grounding,
        "evidence_ids": list(evidence_ids),
        "unresolved": list(unresolved),
        "evidence": [dict(by_ref[ref_id]) for ref_id in evidence_ids],
    }


def _limits(max_ai_credits: float, timeout: float) -> dict[str, int | float]:
    return {
        "max_ai_credits": max_ai_credits,
        "timeout_seconds": timeout,
        "custom_tool_calls": MAX_CUSTOM_TOOL_CALLS,
        "llm_calls": MAX_LLM_CALLS,
        "subqueries_per_search": MAX_SUBQUERIES_PER_SEARCH,
        "hits_per_subquery": MAX_HITS_PER_SUBQUERY,
        "refs_per_open": MAX_REFS_PER_OPEN,
        "tokens_per_subquery": MAX_TOKENS_PER_SUBQUERY,
    }


async def _abort_without_masking(session: Any) -> None:
    try:
        await session.abort()
    except Exception:
        pass


async def _cleanup(
    client: Any,
    session: Any | None,
    *,
    started: bool,
    suppress_errors: bool,
) -> None:
    failed = False
    if session is not None:
        try:
            await session.disconnect()
        except Exception:
            failed = True
    if started:
        try:
            await client.stop()
        except Exception:
            failed = True
    if failed and not suppress_errors:
        raise RepositoryQueryExecutionError("SDK cleanup failed")


async def run_repository_query(
    *,
    prompt: str,
    tools: ToolBundle,
    model: str,
    reasoning_effort: str,
    max_ai_credits: float,
    timeout: float,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one bounded Agentic query and return host-validated grounding."""
    _validate_configuration(
        prompt=prompt,
        model=model,
        reasoning_effort=reasoning_effort,
        max_ai_credits=max_ai_credits,
        timeout=timeout,
    )
    session_limits = _session_limits_config(float(max_ai_credits))
    from copilot import ToolSet

    factory = client_factory or create_copilot_client
    collector = UsageCollector()
    client = factory()
    session: Any | None = None
    started = False
    try:
        try:
            await client.start()
        except Exception as exc:
            raise RepositoryQueryExecutionError(
                f"SDK client start failed ({type(exc).__name__})"
            ) from None
        started = True
        try:
            session = await client.create_session(
                on_permission_request=_deny_permission,
                model=model.strip(),
                reasoning_effort=reasoning_effort.strip(),
                tools=tools.sdk_tools(),
                system_message={"mode": "replace", "content": _SYSTEM_MESSAGE},
                available_tools=ToolSet().add_custom("*"),
                excluded_tools=ToolSet().add_builtin("*").add_mcp("*"),
                streaming=True,
                session_limits=session_limits,
                enable_session_telemetry=False,
                enable_citations=False,
                enable_config_discovery=False,
                skip_custom_instructions=True,
                enable_on_demand_instruction_discovery=False,
                enable_file_hooks=False,
                enable_host_git_operations=False,
                enable_session_store=False,
                enable_skills=False,
                skill_directories=[],
                plugin_directories=[],
                instruction_directories=[],
                mcp_servers={},
                hooks=None,
                memory=None,
                on_event=collector.on_event,
            )
        except Exception as exc:
            raise RepositoryQueryExecutionError(
                f"SDK session creation failed ({type(exc).__name__})"
            ) from None
        collector.bind_session(session)
        try:
            event = await session.send_and_wait(prompt, timeout=float(timeout))
        except RepositoryQueryLimitError:
            await collector.ensure_limit_abort(session)
            raise
        except Exception as exc:
            if collector.limit_error is not None:
                await collector.ensure_limit_abort(session)
                raise collector.limit_error
            raise RepositoryQueryExecutionError(
                f"SDK query failed ({type(exc).__name__})"
            ) from None
        if collector.limit_error is not None:
            await collector.ensure_limit_abort(session)
            raise collector.limit_error
        activity = tools.activity()
        tool_calls = int(activity.get("tool_calls", 0))
        if tool_calls > MAX_CUSTOM_TOOL_CALLS:
            await _abort_without_masking(session)
            raise RepositoryQueryLimitError(
                "tool_calls", MAX_CUSTOM_TOOL_CALLS, tool_calls
            )
        model_output = _validate_model_output(
            _extract_content(event), tools.ledger.evidence()
        )
        result = {
            "schema_version": 1,
            **model_output,
            "usage": collector.to_dict(activity),
            "limits": _limits(float(max_ai_credits), float(timeout)),
        }
    except BaseException as exc:
        if isinstance(exc, (RepositoryQueryError, RepositoryQueryLimitError)):
            _attach_failure_usage(exc, collector, tools)
        await _cleanup(client, session, started=started, suppress_errors=True)
        raise
    else:
        try:
            await _cleanup(client, session, started=started, suppress_errors=False)
        except RepositoryQueryExecutionError as exc:
            _attach_failure_usage(exc, collector, tools)
            raise
        return result
