"""RED contracts for the bounded Copilot SDK runtime (FR-RQ-03/NFR-RQ-01)."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Coroutine

import pytest
from copilot.session import PermissionDecisionUserNotAvailable
from copilot.session_events import SessionEventType

from hve.repository_query import (
    MIN_AI_CREDITS,
    RepositoryQueryConfigurationError,
    RepositoryQueryExecutionError,
    RepositoryQueryLimitError,
    RepositoryQueryOutputError,
    _SYSTEM_MESSAGE,
    run_repository_query,
)

TOOL_NAMES = (
    "search_markdown",
    "search_code",
    "open_evidence",
    "find_code_references",
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def async_test(
    function: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Any]:
    """Run one async test with stdlib only; pytest-asyncio is not a dependency."""

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


class FakeLedger:
    def __init__(self) -> None:
        self.rows = [
            {
                "ref_id": "E1",
                "source": "code",
                "path": "pkg/service.py",
                "lines": [1, 2],
                "chunk_id": "cq-1",
                "snippet": "def run():\n    return 1",
            }
        ]

    def evidence(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]


class FakeToolBundle:
    def __init__(self, *, tool_calls: int = 1, internal_searches: int = 1) -> None:
        self.ledger: Any = FakeLedger()
        self._activity = {
            "tool_calls": tool_calls,
            "internal_searches": internal_searches,
        }
        self.tools = [SimpleNamespace(name=name) for name in TOOL_NAMES]

    def sdk_tools(self) -> list[object]:
        return list(self.tools)

    def activity(self) -> dict[str, int]:
        return dict(self._activity)


class FakeSession:
    def __init__(
        self,
        raw: str,
        events: list[object] | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.raw = raw
        self.events = list(events or [])
        self.prompts: list[tuple[str, float]] = []
        self.abort_calls = 0
        self.disconnect_calls = 0
        self.calls = calls if calls is not None else []
        self.on_event = lambda _event: None

    async def send_and_wait(self, prompt: str, *, timeout: float) -> object:
        self.prompts.append((prompt, timeout))
        for event in self.events:
            self.on_event(event)
        return SimpleNamespace(data=SimpleNamespace(content=self.raw))

    async def abort(self) -> None:
        self.abort_calls += 1
        self.calls.append("session.abort")

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.calls.append("session.disconnect")


class FakeClient:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.start_calls = 0
        self.stop_calls = 0
        self.create_calls: list[dict[str, Any]] = []

    async def start(self) -> None:
        self.start_calls += 1
        self.session.calls.append("client.start")

    async def create_session(self, **kwargs: Any) -> FakeSession:
        self.create_calls.append(kwargs)
        self.session.calls.append("client.create_session")
        self.session.on_event = kwargs["on_event"]
        return self.session

    async def stop(self) -> None:
        self.stop_calls += 1
        self.session.calls.append("client.stop")


def _grounded_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "status": "answered",
        "grounding": "The implementation is grounded [E1].",
        "evidence_ids": ["E1"],
        "unresolved": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _usage_event(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    duration_ms: int = 0,
    event_type: object = "assistant.usage",
) -> object:
    return SimpleNamespace(
        type=event_type,
        data=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=None,
            duration=timedelta(milliseconds=duration_ms),
        ),
    )


async def _run(
    session: FakeSession,
    *,
    tools: FakeToolBundle | None = None,
    prompt: str = "ground this question",
) -> tuple[dict[str, Any], FakeClient]:
    client = FakeClient(session)
    result = await run_repository_query(
        prompt=prompt,
        tools=tools or FakeToolBundle(),
        model="gpt-5.6-sol",
        reasoning_effort="high",
        max_ai_credits=MIN_AI_CREDITS,
        timeout=30.0,
        client_factory=lambda: client,
    )
    return result, client


@async_test
async def test_creates_a_custom_only_fail_closed_session() -> None:
    session = FakeSession(_grounded_json())

    result, client = await _run(session)

    assert client.start_calls == 1
    assert len(client.create_calls) == 1
    options = client.create_calls[0]
    assert [tool.name for tool in options["tools"]] == list(TOOL_NAMES)
    assert options["available_tools"].to_list() == ["custom:*"]
    assert options["excluded_tools"].to_list() == ["builtin:*", "mcp:*"]
    assert options["model"] == "gpt-5.6-sol"
    assert options["reasoning_effort"] == "high"
    assert options["session_limits"] == {"max_ai_credits": MIN_AI_CREDITS}
    assert options["streaming"] is True
    assert options["enable_session_telemetry"] is False
    assert options["enable_config_discovery"] is False
    assert options["skip_custom_instructions"] is True
    assert options["enable_on_demand_instruction_discovery"] is False
    assert options["enable_file_hooks"] is False
    assert options["enable_host_git_operations"] is False
    assert options["enable_session_store"] is False
    assert options["enable_skills"] is False
    assert options["skill_directories"] == []
    assert options["plugin_directories"] == []
    assert options["instruction_directories"] == []
    assert options["mcp_servers"] == {}
    assert "untrusted data" in options["system_message"]["content"]
    assert '"unresolved":[]' in options["system_message"]["content"]
    decision = options["on_permission_request"](object(), object())
    assert isinstance(decision, PermissionDecisionUserNotAvailable)
    assert session.prompts == [("ground this question", 30.0)]
    assert result["status"] == "answered"


def test_system_message_prompt_uses_the_externalized_source() -> None:
    prompt_path = (
        REPO_ROOT
        / ".github"
        / "prompts"
        / "runtime"
        / "repository-query"
        / "system-message.prompt.md"
    )

    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert prompt_text == _SYSTEM_MESSAGE
    assert "Return exactly one JSON object" in prompt_text
    assert "Never invent paths, lines, or evidence IDs" in prompt_text
    assert "untrusted data" in prompt_text


@async_test
async def test_aggregates_usage_and_host_owned_evidence() -> None:
    session = FakeSession(
        _grounded_json(),
        events=[
            _usage_event(
                input_tokens=10,
                output_tokens=4,
                cache_read_tokens=3,
                duration_ms=125,
                event_type=SessionEventType.ASSISTANT_USAGE,
            ),
            _usage_event(
                input_tokens=7,
                output_tokens=2,
                cache_write_tokens=1,
                duration_ms=75,
            ),
        ],
    )

    result, _ = await _run(session)

    assert result == {
        "schema_version": 1,
        "status": "answered",
        "grounding": "The implementation is grounded [E1].",
        "evidence_ids": ["E1"],
        "unresolved": [],
        "evidence": [FakeLedger().rows[0]],
        "usage": {
            "llm_calls": 2,
            "tool_calls": 1,
            "internal_searches": 1,
            "input_tokens": 17,
            "output_tokens": 6,
            "cache_read_tokens": 3,
            "cache_write_tokens": 1,
            "duration_ms": 200,
        },
        "limits": {
            "max_ai_credits": MIN_AI_CREDITS,
            "timeout_seconds": 30.0,
            "custom_tool_calls": 6,
            "llm_calls": 10,
            "subqueries_per_search": 3,
            "hits_per_subquery": 3,
            "refs_per_open": 3,
            "tokens_per_subquery": 800,
        },
    }


@async_test
@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "invalid JSON"),
        (_grounded_json(evidence_ids=["E99"], grounding="claim [E99]"), "E99"),
        (
            _grounded_json(
                evidence_ids=["E1", "E99"],
                grounding="known [E1], invented [E99]",
            ),
            "E99",
        ),
        (_grounded_json(evidence_ids=["E1"], grounding="claim without citation"), "citation"),
        (_grounded_json(evidence_ids=["E1", "E1"]), "duplicate"),
        (_grounded_json(grounding="claim [ E1 ]"), "citation"),
        (_grounded_json(evidence_ids=[], grounding="none"), "evidence"),
        (_grounded_json(path="invented.py"), "unexpected field"),
        (_grounded_json(unresolved=["still unresolved"]), "unresolved"),
        (_grounded_json(status="partial", unresolved=[]), "unresolved"),
        (
            _grounded_json(
                status="insufficient_evidence",
                grounding="No evidence.",
                evidence_ids=[],
                unresolved=[],
            ),
            "unresolved",
        ),
        (
            _grounded_json(
                status="insufficient_evidence",
                grounding="incorrect [E1]",
                evidence_ids=["E1"],
                unresolved=["still unresolved"],
            ),
            "must not cite",
        ),
        (_grounded_json(grounding=""), "grounding"),
        (_grounded_json(status="unknown"), "status"),
        (_grounded_json(evidence_ids="E1"), "evidence_ids"),
        (_grounded_json(unresolved="none"), "unresolved"),
    ],
)
async def test_invalid_model_output_fails_without_a_repair_call(
    raw: str, message: str
) -> None:
    session = FakeSession(raw)
    client = FakeClient(session)

    with pytest.raises(RepositoryQueryOutputError, match=message):
        await run_repository_query(
            prompt="secret prompt text",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=lambda: client,
        )

    assert len(session.prompts) == 1
    assert session.disconnect_calls == 1
    assert client.stop_calls == 1


@async_test
async def test_insufficient_evidence_can_abstain_without_citations() -> None:
    session = FakeSession(
        _grounded_json(
            status="insufficient_evidence",
            grounding="No repository evidence answers the live question.",
            evidence_ids=[],
            unresolved=["live production trace is unavailable"],
        )
    )
    tools = FakeToolBundle(tool_calls=0, internal_searches=0)
    tools.ledger.rows = []

    result, _ = await _run(session, tools=tools)

    assert result["status"] == "insufficient_evidence"
    assert result["evidence"] == []


@async_test
async def test_partial_answer_requires_evidence_and_unresolved_items() -> None:
    session = FakeSession(
        _grounded_json(
            status="partial",
            grounding="The repository supports only this part [E1].",
            unresolved=["live state remains unavailable"],
        )
    )

    result, _ = await _run(session)

    assert result["status"] == "partial"
    assert result["evidence_ids"] == ["E1"]
    assert result["unresolved"] == ["live state remains unavailable"]


@async_test
async def test_eleventh_usage_event_aborts_and_fails_closed() -> None:
    session = FakeSession(
        _grounded_json(),
        events=[_usage_event(input_tokens=1, output_tokens=1) for _ in range(11)],
    )

    with pytest.raises(RepositoryQueryLimitError, match="llm_calls") as excinfo:
        await _run(session)

    assert vars(excinfo.value)["usage"] == {
        "llm_calls": 11,
        "tool_calls": 1,
        "internal_searches": 1,
        "input_tokens": 11,
        "output_tokens": 11,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "duration_ms": 0,
    }
    assert session.abort_calls == 1
    assert session.disconnect_calls == 1
    assert session.calls[-3:] == ["session.abort", "session.disconnect", "client.stop"]


@async_test
async def test_usage_limit_aborts_before_later_usage_events_are_processed() -> None:
    class YieldingSession(FakeSession):
        async def send_and_wait(self, prompt: str, *, timeout: float) -> object:
            self.prompts.append((prompt, timeout))
            for event in self.events:
                self.on_event(event)
                await asyncio.sleep(0)
                if self.abort_calls:
                    break
            return SimpleNamespace(data=SimpleNamespace(content=self.raw))

    session = YieldingSession(
        _grounded_json(),
        events=[_usage_event(input_tokens=1, output_tokens=1) for _ in range(14)],
    )

    with pytest.raises(RepositoryQueryLimitError, match="llm_calls") as excinfo:
        await _run(session)

    assert excinfo.value.actual == 11
    assert vars(excinfo.value)["usage"]["llm_calls"] == 11
    assert session.abort_calls == 1


@async_test
async def test_cap_error_actual_matches_usage_already_delivered_by_sdk() -> None:
    session = FakeSession(
        _grounded_json(),
        events=[_usage_event(input_tokens=1, output_tokens=1) for _ in range(14)],
    )

    with pytest.raises(RepositoryQueryLimitError, match="llm_calls") as excinfo:
        await _run(session)

    assert excinfo.value.actual == 14
    assert vars(excinfo.value)["usage"]["llm_calls"] == 14
    assert session.abort_calls == 1


@async_test
async def test_output_error_preserves_usage_for_failed_benchmark_run() -> None:
    session = FakeSession(
        "not json",
        events=[
            _usage_event(
                input_tokens=13,
                output_tokens=5,
                cache_read_tokens=7,
                duration_ms=25,
            )
        ],
    )

    with pytest.raises(RepositoryQueryOutputError, match="invalid JSON") as excinfo:
        await _run(session, tools=FakeToolBundle(tool_calls=3, internal_searches=4))

    assert vars(excinfo.value)["usage"] == {
        "llm_calls": 1,
        "tool_calls": 3,
        "internal_searches": 4,
        "input_tokens": 13,
        "output_tokens": 5,
        "cache_read_tokens": 7,
        "cache_write_tokens": 0,
        "duration_ms": 25,
    }


@async_test
async def test_abort_failure_does_not_mask_the_limit_error() -> None:
    class AbortFailingSession(FakeSession):
        async def abort(self) -> None:
            self.abort_calls += 1
            self.calls.append("session.abort")
            raise RuntimeError("abort detail must not win")

    session = AbortFailingSession(
        _grounded_json(),
        events=[_usage_event(input_tokens=1, output_tokens=1) for _ in range(11)],
    )

    with pytest.raises(RepositoryQueryLimitError, match="llm_calls"):
        await _run(session)

    assert session.abort_calls == 1
    assert session.disconnect_calls == 1


@async_test
async def test_cleanup_runs_when_send_fails() -> None:
    class FailingSession(FakeSession):
        async def send_and_wait(self, prompt: str, *, timeout: float) -> object:
            self.prompts.append((prompt, timeout))
            raise TimeoutError("sdk timeout")

    session = FailingSession(_grounded_json())
    client = FakeClient(session)

    with pytest.raises(RepositoryQueryExecutionError, match="TimeoutError") as excinfo:
        await run_repository_query(
            prompt="do not leak this prompt",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=lambda: client,
        )

    assert session.disconnect_calls == 1
    assert client.stop_calls == 1
    assert "sdk timeout" not in str(excinfo.value)


@async_test
async def test_client_stops_when_session_creation_fails() -> None:
    class FailingClient(FakeClient):
        async def create_session(self, **kwargs: Any) -> FakeSession:
            self.create_calls.append(kwargs)
            raise RuntimeError("create failed")

    session = FakeSession(_grounded_json())
    client = FailingClient(session)

    with pytest.raises(RepositoryQueryExecutionError, match="RuntimeError") as excinfo:
        await run_repository_query(
            prompt="question",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=lambda: client,
        )

    assert session.disconnect_calls == 0
    assert client.stop_calls == 1
    assert "create failed" not in str(excinfo.value)


@async_test
async def test_cleanup_failures_do_not_mask_an_output_error() -> None:
    class CleanupFailingSession(FakeSession):
        async def disconnect(self) -> None:
            self.disconnect_calls += 1
            raise RuntimeError("disconnect secret detail")

    class CleanupFailingClient(FakeClient):
        async def stop(self) -> None:
            self.stop_calls += 1
            raise RuntimeError("stop secret detail")

    session = CleanupFailingSession("not json")
    client = CleanupFailingClient(session)

    with pytest.raises(RepositoryQueryOutputError, match="invalid JSON") as excinfo:
        await run_repository_query(
            prompt="question",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=lambda: client,
        )

    assert session.disconnect_calls == 1
    assert client.stop_calls == 1
    assert "secret detail" not in str(excinfo.value)


@async_test
async def test_cleanup_failure_after_success_is_reported_without_raw_details() -> None:
    class StopFailingClient(FakeClient):
        async def stop(self) -> None:
            self.stop_calls += 1
            raise RuntimeError("raw cleanup detail")

    session = FakeSession(_grounded_json())
    client = StopFailingClient(session)

    with pytest.raises(RepositoryQueryExecutionError, match="SDK cleanup failed") as excinfo:
        await run_repository_query(
            prompt="question",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=lambda: client,
        )

    assert session.disconnect_calls == 1
    assert client.stop_calls == 1
    assert "raw cleanup detail" not in str(excinfo.value)


@async_test
@pytest.mark.parametrize(
    "rows",
    [
        [{"ref_id": "E0"}],
        [{"ref_id": "E1"}, {"ref_id": "E1"}],
        ["not-an-object"],
    ],
)
async def test_invalid_ledger_rows_fail_closed(rows: list[object]) -> None:
    tools = FakeToolBundle()
    tools.ledger = AnyLedger(rows)
    session = FakeSession(_grounded_json())

    with pytest.raises(RepositoryQueryOutputError, match="ledger evidence"):
        await _run(session, tools=tools)


class AnyLedger:
    """Intentionally violates the runtime protocol to exercise fail-closed validation."""

    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def evidence(self) -> Any:
        return self.rows


@async_test
@pytest.mark.parametrize(
    "overrides",
    [
        {"model": ""},
        {"model": " Auto "},
        {"reasoning_effort": ""},
        {"reasoning_effort": " AUTO "},
        {"max_ai_credits": 0},
        {"max_ai_credits": MIN_AI_CREDITS - 0.1},
        {"timeout": 0},
    ],
)
async def test_invalid_limits_fail_before_client_creation(
    overrides: dict[str, object]
) -> None:
    created = False

    def factory() -> FakeClient:
        nonlocal created
        created = True
        return FakeClient(FakeSession(_grounded_json()))

    params: dict[str, object] = {
        "prompt": "question",
        "tools": FakeToolBundle(),
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "max_ai_credits": MIN_AI_CREDITS,
        "timeout": 30.0,
        "client_factory": factory,
    }
    params.update(overrides)

    with pytest.raises(RepositoryQueryConfigurationError):
        await run_repository_query(**params)  # type: ignore[arg-type]

    assert created is False


@async_test
async def test_missing_sdk_ai_credit_capability_fails_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import copilot.session

    created = False

    def factory() -> FakeClient:
        nonlocal created
        created = True
        return FakeClient(FakeSession(_grounded_json()))

    monkeypatch.setattr(copilot.session, "SessionLimitsConfig", object)

    with pytest.raises(RepositoryQueryConfigurationError, match="max_ai_credits"):
        await run_repository_query(
            prompt="question",
            tools=FakeToolBundle(),
            model="gpt-5.6-sol",
            reasoning_effort="high",
            max_ai_credits=MIN_AI_CREDITS,
            timeout=30.0,
            client_factory=factory,
        )

    assert created is False


@async_test
async def test_raw_prompt_and_model_output_are_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_prompt = "PROMPT-SECRET-7f3a"
    secret_output = "OUTPUT-SECRET-a91c"
    session = FakeSession(secret_output)

    with pytest.raises(RepositoryQueryOutputError) as excinfo:
        await _run(session, prompt=secret_prompt)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_prompt not in str(excinfo.value)
    assert secret_output not in str(excinfo.value)
    assert secret_prompt not in rendered
    assert secret_output not in rendered
