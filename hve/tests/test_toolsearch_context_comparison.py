"""FR-TS-11: Tool Search OFF / ON no-prompt context comparison contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from hve.toolsearch.context_report import (
    ContextReport,
    ContextReportError,
    ContextRuntimeMeasurement,
    Layer,
    _measure_once,
    build_comparison,
    collect_comparison,
    render_comparison_text,
)
from hve.toolsearch.resource_routing import ResourceRoute


def _report(*, total_tokens: int, tool_definitions_tokens: int) -> ContextReport:
    return ContextReport(
        model_name="claude-sonnet-4.5",
        requested_model="claude-opus-4.7",
        limit=128000,
        total_tokens=total_tokens,
        system_tokens=100,
        tool_definitions_tokens=tool_definitions_tokens,
        mcp_tools_tokens=50,
        conversation_tokens=0,
        system_prompt_tokens=75,
        layers=(Layer(name="azure", tool_count=2, tokens=tool_definitions_tokens),),
        unconnected=(),
    )


def _measurement(
    *,
    total_tokens: int,
    tool_definitions_tokens: int,
    mcp: tuple[str, ...] = ("azure",),
    skills: tuple[str, ...] = ("markdown-query",),
) -> ContextRuntimeMeasurement:
    return ContextRuntimeMeasurement(
        report=_report(
            total_tokens=total_tokens,
            tool_definitions_tokens=tool_definitions_tokens,
        ),
        connected_mcp_servers=mcp,
        enabled_skills=skills,
    )


class TestBuildComparison:
    def test_runtime_resources_match_before_reduction_is_reported(self) -> None:
        comparison = build_comparison(
            off=_measurement(total_tokens=400, tool_definitions_tokens=200),
            on=_measurement(total_tokens=300, tool_definitions_tokens=120),
        )

        assert comparison.comparable is True
        assert comparison.reason is None
        assert comparison.reduction["total_tokens_saved"] == 100
        assert comparison.reduction["tool_definitions_tokens_saved"] == 80
        assert comparison.reduction["total_tokens_rate"] == pytest.approx(0.25)
        assert comparison.reduction["tool_definitions_tokens_rate"] == pytest.approx(0.4)

    def test_zero_denominator_keeps_rate_null(self) -> None:
        comparison = build_comparison(
            off=_measurement(total_tokens=0, tool_definitions_tokens=0),
            on=_measurement(total_tokens=0, tool_definitions_tokens=0),
        )

        assert comparison.comparable is True
        assert comparison.reduction["total_tokens_saved"] == 0
        assert comparison.reduction["tool_definitions_tokens_saved"] == 0
        assert comparison.reduction["total_tokens_rate"] is None
        assert comparison.reduction["tool_definitions_tokens_rate"] is None

    def test_mcp_drift_marks_the_comparison_incomparable(self) -> None:
        comparison = build_comparison(
            off=_measurement(total_tokens=400, tool_definitions_tokens=200, mcp=("azure",)),
            on=_measurement(total_tokens=300, tool_definitions_tokens=120, mcp=("azure", "workiq")),
        )

        assert comparison.comparable is False
        assert "drift" in str(comparison.reason)
        assert all(value is None for value in comparison.reduction.values())

    def test_skill_drift_marks_the_comparison_incomparable(self) -> None:
        comparison = build_comparison(
            off=_measurement(total_tokens=400, tool_definitions_tokens=200),
            on=_measurement(
                total_tokens=300,
                tool_definitions_tokens=120,
                skills=("markdown-query", "code-query"),
            ),
        )

        assert comparison.comparable is False
        assert "drift" in str(comparison.reason)
        assert all(value is None for value in comparison.reduction.values())
        assert "比較不能" in render_comparison_text(comparison)

    def test_incomparable_text_reports_not_calculated_without_none_values(self) -> None:
        comparison = build_comparison(
            off=_measurement(total_tokens=400, tool_definitions_tokens=200),
            on=None,
            on_error="measurement failed",
        )

        text = render_comparison_text(comparison)
        assert "削減値: 算出なし" in text
        assert "total_tokens_saved: None" not in text

    def test_comparable_zero_savings_remains_an_explicit_zero(self) -> None:
        measurement = _measurement(total_tokens=400, tool_definitions_tokens=200)
        text = render_comparison_text(build_comparison(off=measurement, on=measurement))

        assert "total_tokens_saved: 0" in text


class _FakeConfig:
    model = "claude-opus-4.7"
    context_tier = "long_context"
    cli_path = None
    cli_url = None
    tool_search_defer_threshold = 30

    def resolve_token(self):
        return None


class TestCollectComparison:
    def test_snapshot_policy_and_route_are_resolved_once_and_reused(self) -> None:
        route = object()
        snapshot = object()
        policy = object()
        off = _measurement(total_tokens=400, tool_definitions_tokens=200)
        on = _measurement(total_tokens=300, tool_definitions_tokens=120)
        measure = AsyncMock(side_effect=[off, on])

        with patch(
            "hve.toolsearch.context_report.SDKConfig",
            new=SimpleNamespace(from_env=lambda: _FakeConfig()),
        ), patch(
            "hve.toolsearch.context_report.discover_sdk_resources",
            return_value=snapshot,
        ) as discover, patch(
            "hve.toolsearch.context_report.ToolSearchPolicy",
            new=SimpleNamespace(load=Mock(return_value=policy)),
        ), patch(
            "hve.toolsearch.context_report.resolve_resource_route",
            return_value=route,
        ) as resolve_route, patch(
            "hve.toolsearch.context_report._measure_once",
            measure,
        ):
            comparison = asyncio.run(
                collect_comparison(repo_root=Path.cwd(), workflow_id="ard")
            )

        assert comparison.comparable is True
        discover.assert_called_once()
        resolve_route.assert_called_once()
        assert measure.await_count == 2
        off_call = measure.await_args_list[0].kwargs
        on_call = measure.await_args_list[1].kwargs
        assert off_call["route"] is route
        assert on_call["route"] is route
        assert off_call["workflow_id"] == "ard"
        assert on_call["workflow_id"] == "ard"
        assert off_call["tool_search_enabled"] is False
        assert off_call["tool_search_defer_threshold"] is None
        assert on_call["tool_search_enabled"] is True
        assert on_call["tool_search_defer_threshold"] == 30
        assert off_call["session_options"] == on_call["session_options"]

    def test_step_scope_resolves_registry_skills_before_session_creation(
        self,
        tmp_path: Path,
    ) -> None:
        route = SimpleNamespace(required_mcp_servers=("tenant-foundry",))
        resolve_route = Mock(return_value=route)
        external_root = tmp_path / "skills"
        foundry_dir = external_root / "microsoft-foundry"
        foundry_dir.mkdir(parents=True)
        (foundry_dir / "SKILL.md").write_text(
            "---\nname: microsoft-foundry\n---\n# Test Skill\n",
            encoding="utf-8",
        )

        with patch(
            "hve.toolsearch.context_report.SDKConfig",
            new=SimpleNamespace(from_env=lambda: _FakeConfig()),
        ), patch(
            "hve.toolsearch.context_report.discover_sdk_resources",
            return_value=object(),
        ) as discover, patch(
            "hve.toolsearch.context_report.ToolSearchPolicy.load",
            return_value=object(),
        ), patch(
            "hve.toolsearch.context_report.resolve_resource_route",
            resolve_route,
        ), patch(
            "hve.skill_resolver._external_skills_root",
            return_value=external_root,
        ):
            prepared = asyncio.run(
                __import__(
                    "hve.toolsearch.context_report",
                    fromlist=["_prepare_measurement_context"],
                )._prepare_measurement_context(
                    repo_root=Path.cwd(),
                    workflow_id="aagd",
                    step_id="2.3/AG-01",
                )
            )

        assert prepared[-1] is route
        assert str(foundry_dir) in prepared[2]["skill_directories"]
        required = resolve_route.call_args.kwargs["required_skills"]
        optional = resolve_route.call_args.kwargs["optional_skills"]
        assert "microsoft-foundry" in required
        assert "agentic-retrieval-contract" in required
        assert "azure-ai" in optional
        discover.assert_called_once()

    def test_unknown_step_fails_before_resource_discovery(self) -> None:
        with patch(
            "hve.toolsearch.context_report.discover_sdk_resources"
        ) as discover:
            with pytest.raises(ContextReportError, match="unknown Step"):
                asyncio.run(
                    __import__(
                        "hve.toolsearch.context_report",
                        fromlist=["_prepare_measurement_context"],
                    )._prepare_measurement_context(
                        repo_root=Path.cwd(),
                        workflow_id="aagd",
                        step_id="missing",
                    )
                )

        discover.assert_not_called()

    def test_container_step_has_a_distinct_error_before_resource_discovery(self) -> None:
        with patch(
            "hve.toolsearch.context_report.discover_sdk_resources"
        ) as discover:
            with pytest.raises(ContextReportError, match="container Step"):
                asyncio.run(
                    __import__(
                        "hve.toolsearch.context_report",
                        fromlist=["_prepare_measurement_context"],
                    )._prepare_measurement_context(
                        repo_root=Path.cwd(),
                        workflow_id="asdw-web",
                        step_id="1",
                    )
                )

        discover.assert_not_called()

    def test_side_failure_keeps_the_other_side_and_returns_non_reduced_payload(self) -> None:
        route = object()
        on = _measurement(total_tokens=300, tool_definitions_tokens=120)
        measure = AsyncMock(side_effect=[ContextReportError("off boom"), on])

        with patch(
            "hve.toolsearch.context_report.SDKConfig",
            new=SimpleNamespace(from_env=lambda: _FakeConfig()),
        ), patch(
            "hve.toolsearch.context_report.discover_sdk_resources",
            return_value=object(),
        ), patch(
            "hve.toolsearch.context_report.ToolSearchPolicy",
            new=SimpleNamespace(load=Mock(return_value=object())),
        ), patch(
            "hve.toolsearch.context_report.resolve_resource_route",
            return_value=route,
        ), patch(
            "hve.toolsearch.context_report._measure_once",
            measure,
        ):
            comparison = asyncio.run(
                collect_comparison(repo_root=Path.cwd(), workflow_id="ard")
            )

        assert comparison.off is None
        assert comparison.on == on
        assert comparison.off_error == "off boom"
        assert comparison.comparable is False
        assert comparison.has_failures() is True
        assert all(value is None for value in comparison.reduction.values())

    def test_common_preparation_failure_is_reported_as_context_error(self) -> None:
        with patch(
            "hve.toolsearch.context_report.SDKConfig",
            new=SimpleNamespace(from_env=lambda: _FakeConfig()),
        ), patch(
            "hve.toolsearch.context_report.discover_sdk_resources",
            return_value=object(),
        ), patch(
            "hve.toolsearch.context_report.ToolSearchPolicy.load",
            side_effect=ValueError("invalid policy"),
        ):
            with pytest.raises(ContextReportError, match="準備に失敗"):
                asyncio.run(
                    collect_comparison(repo_root=Path.cwd(), workflow_id="ard")
                )


class _Entry:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeMetadataRPC:
    def __init__(self, events: list[str], connected: tuple[str, ...]) -> None:
        self.events = events
        self.connected = connected
        self._context_info = {
            "modelName": "claude-sonnet-4.5",
            "limit": 128000,
            "totalTokens": 280 + 120 * len(connected),
            "systemTokens": 100,
            "toolDefinitionsTokens": 80 + 120 * len(connected),
            "mcpToolsTokens": 120 * len(connected),
            "conversationTokens": 0,
        }

    async def context_info(self, *_args, **_kwargs):
        self.events.append("metadata.context_info")
        return SimpleNamespace(context_info=SimpleNamespace(to_dict=lambda: dict(self._context_info)))

    async def get_context_attribution(self, **_kwargs):
        self.events.append("metadata.get_context_attribution")
        return SimpleNamespace(
            context_attribution=SimpleNamespace(
                entries=[
                    _Entry({"id": "system:systemPrompt", "kind": "system", "tokens": 75}),
                    _Entry({"id": "toolDefinition:view", "kind": "toolDefinition", "label": "view", "tokens": 80}),
                ] + [
                    _Entry({"id": f"toolDefinition:{name}-search", "kind": "toolDefinition", "label": f"{name}-search", "tokens": 120})
                    for name in self.connected
                ],
            )
        )


class _FakeToolsRPC:
    def __init__(self, events: list[str], connected: tuple[str, ...]) -> None:
        self.events = events
        self.connected = connected

    async def initialize_and_validate(self, **_kwargs):
        self.events.append("tools.initialize")
        return None

    async def get_current_metadata(self, **_kwargs):
        self.events.append("tools.get_current_metadata")
        return SimpleNamespace(
            tools=[SimpleNamespace(name="view", mcp_server_name=None)] + [
                SimpleNamespace(name=f"{name}-search", mcp_server_name=name)
                for name in self.connected
            ]
        )


class _FakeMCPRPC:
    def __init__(
        self, events: list[str], connected: tuple[str, ...], *, invalid: bool = False
    ) -> None:
        self.events = events
        self.connected = connected
        self.invalid = invalid

    async def list(self, **_kwargs):
        self.events.append("mcp.list")
        if self.invalid:
            return SimpleNamespace(servers=None)
        return SimpleNamespace(
            servers=[
                SimpleNamespace(
                    name=name,
                    status=SimpleNamespace(value="connected"),
                )
                for name in self.connected
            ]
        )

    async def disable(self, request, **_kwargs):
        self.events.append(f"mcp.disable:{request.server_name}")
        self.connected = tuple(name for name in self.connected if name != request.server_name)


class _FakeSkillsRPC:
    def __init__(self, events: list[str], *, invalid: bool = False) -> None:
        self.events = events
        self.invalid = invalid

    async def list(self):
        self.events.append("skills.list")
        if self.invalid:
            return SimpleNamespace(skills=None)
        return SimpleNamespace(skills=[SimpleNamespace(name="markdown-query", enabled=True)])


class _FakeSession:
    def __init__(
        self,
        *,
        invalid_mcp: bool = False,
        invalid_skills: bool = False,
        connected: tuple[str, ...] = ("azure",),
    ) -> None:
        self.events: list[str] = []
        self.rpc = SimpleNamespace(
            mcp=_FakeMCPRPC(self.events, connected, invalid=invalid_mcp),
            metadata=_FakeMetadataRPC(self.events, connected),
            tools=_FakeToolsRPC(self.events, connected),
            skills=_FakeSkillsRPC(self.events, invalid=invalid_skills),
        )
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.events.append("session.disconnect")
        self.disconnect_calls += 1


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.start_calls = 0
        self.stop_calls = 0

    def factory(self, **_kwargs):
        self.session.events.append("client.factory")
        return self

    async def start(self) -> None:
        self.session.events.append("client.start")
        self.start_calls += 1

    async def stop(self) -> None:
        self.session.events.append("client.stop")
        self.stop_calls += 1


async def _create_ready_session(
    *,
    client: _FakeClient,
    session_options,
    route: ResourceRoute,
    tool_search_enabled,
    tool_search_defer_threshold,
):
    """Model the shared creator's completed readiness, not its implementation."""
    session = client.session
    session.events.append("creator.enter")
    if route.enabled_mcp_servers:
        await session.rpc.tools.initialize_and_validate()
        for name in route.enabled_mcp_servers:
            if name not in session.rpc.mcp.connected:
                assert name not in route.required_mcp_servers
                await session.rpc.mcp.disable(SimpleNamespace(server_name=name))
    session.events.append("creator.ready")
    return session


async def _bounded_measurement(coroutine):
    # Do not shorten the product deadline: that would let the old 60s poll go green.
    try:
        return await asyncio.wait_for(coroutine, timeout=0.25)
    except asyncio.TimeoutError as exc:
        raise AssertionError(
            "Context measurement must not repeat MCP readiness after the shared creator"
        ) from exc


def _measure_ready_session(session: _FakeSession, route: ResourceRoute):
    client = _FakeClient(session)
    options = {
        "streaming": True,
        "model": _FakeConfig.model,
        "context_tier": _FakeConfig.context_tier,
    }
    with patch(
        "hve.toolsearch.context_report.create_copilot_client",
        side_effect=client.factory,
    ) as factory, patch(
        "hve.toolsearch.context_report.create_session_from_route",
        side_effect=_create_ready_session,
    ) as creator:
        measurement = asyncio.run(
            _bounded_measurement(
                _measure_once(
                    repo_root=Path(__file__).resolve().parents[2],
                    config=_FakeConfig(),
                    session_options=options,
                    workflow_id="ard",
                    route=route,
                    tool_search_enabled=True,
                    tool_search_defer_threshold=30,
                )
            )
        )

    factory.assert_called_once()
    creator.assert_awaited_once_with(
        client=client,
        session_options=options,
        route=route,
        tool_search_enabled=True,
        tool_search_defer_threshold=30,
    )
    assert client.start_calls == client.stop_calls == session.disconnect_calls == 1
    assert session.events[:3] == ["client.factory", "client.start", "creator.enter"]
    assert session.events[-2:] == ["session.disconnect", "client.stop"]
    return measurement


class TestMeasureOnce:
    def test_connected_mcp_reuses_shared_readiness(self) -> None:
        """FR-TS-11/13: observe once after the shared creator, without reinitializing."""
        session = _FakeSession()
        route = ResourceRoute(
            enabled_mcp_servers=("azure",),
            required_mcp_servers=("azure",),
        )

        measurement = _measure_ready_session(session, route)

        assert session.events.count("tools.initialize") == 1
        assert session.events.count("mcp.list") == 1
        assert (
            session.events.index("tools.initialize")
            < session.events.index("creator.ready")
            < session.events.index("mcp.list")
            < session.events.index("metadata.context_info")
        )
        assert measurement.connected_mcp_servers == ("azure",)
        assert measurement.report.unconnected == ()
        assert measurement.report.required_mcp_servers == ("azure",)
        assert measurement.report.total_tokens == 400

    def test_disabled_optional_mcp_keeps_original_declaration_without_rewaiting(self) -> None:
        """FR-TS-11/13: disabled-and-absent is missing, not a new 60s wait or init."""
        session = _FakeSession(connected=())
        route = ResourceRoute(enabled_mcp_servers=("workiq",))

        measurement = _measure_ready_session(session, route)

        assert session.events.count("tools.initialize") == 1
        assert session.events.count("mcp.disable:workiq") == 1
        assert session.events.count("mcp.list") == 1
        assert (
            session.events.index("tools.initialize")
            < session.events.index("mcp.disable:workiq")
            < session.events.index("creator.ready")
            < session.events.index("mcp.list")
            < session.events.index("metadata.context_info")
        )
        assert route.enabled_mcp_servers == ("workiq",)
        assert measurement.connected_mcp_servers == ()
        assert measurement.report.unconnected == ("workiq",)
        assert measurement.report.layers == (Layer(name="(builtin)", tool_count=1, tokens=80),)

    def test_zero_mcp_initializes_builtin_context_once(self) -> None:
        """FR-TS-11: no MCP readiness does not mean builtin context is initialized."""
        session = _FakeSession(connected=())

        measurement = _measure_ready_session(session, ResourceRoute())

        assert session.events.count("tools.initialize") == 1
        assert session.events.count("mcp.list") == 1
        assert session.events.index("creator.ready") < session.events.index("mcp.list")
        assert (
            session.events.index("creator.ready")
            < session.events.index("tools.initialize")
            < session.events.index("metadata.context_info")
        )
        assert measurement.connected_mcp_servers == ()
        assert measurement.report.unconnected == ()
        assert measurement.report.tool_definitions_tokens == 80
        assert measurement.report.mcp_tools_tokens == 0
        assert measurement.report.layers == (Layer(name="(builtin)", tool_count=1, tokens=80),)

    def test_off_on_runtime_drift_survives_shared_readiness(self) -> None:
        """FR-TS-11: real measurements, not a mocked _measure_once, must retain drift."""
        off_session = _FakeSession(connected=("azure", "workiq"))
        on_session = _FakeSession(connected=("azure",))
        off_client = _FakeClient(off_session)
        on_client = _FakeClient(on_session)
        clients = iter((off_client, on_client))
        root = Path(__file__).resolve().parents[2]
        config = _FakeConfig()
        options = {
            "streaming": True,
            "model": config.model,
            "context_tier": config.context_tier,
        }
        route = ResourceRoute(
            enabled_mcp_servers=("azure", "workiq"),
            required_mcp_servers=("azure",),
        )

        def client_factory(**kwargs):
            return next(clients).factory(**kwargs)

        with patch(
            "hve.toolsearch.context_report._prepare_measurement_context",
            AsyncMock(return_value=(root, config, options, route)),
        ) as prepare, patch(
            "hve.toolsearch.context_report.create_copilot_client",
            side_effect=client_factory,
        ) as factory, patch(
            "hve.toolsearch.context_report.create_session_from_route",
            side_effect=_create_ready_session,
        ) as creator:
            comparison = asyncio.run(
                _bounded_measurement(collect_comparison(repo_root=root, workflow_id="ard"))
            )

        prepare.assert_awaited_once()
        assert factory.call_count == creator.await_count == 2
        off_call, on_call = (call.kwargs for call in creator.await_args_list)
        assert off_call["client"] is off_client
        assert on_call["client"] is on_client
        assert off_call["route"] is on_call["route"] is route
        assert off_call["session_options"] == on_call["session_options"] == options
        assert off_call["tool_search_enabled"] is False
        assert off_call["tool_search_defer_threshold"] is None
        assert on_call["tool_search_enabled"] is True
        assert on_call["tool_search_defer_threshold"] == 30
        for client in (off_client, on_client):
            session = client.session
            assert client.start_calls == client.stop_calls == session.disconnect_calls == 1
            assert session.events.count("tools.initialize") == 1
            assert session.events.count("mcp.list") == 1
            assert (
                session.events.index("tools.initialize")
                < session.events.index("creator.ready")
                < session.events.index("mcp.list")
                < session.events.index("metadata.context_info")
            )
        assert on_session.events.count("mcp.disable:workiq") == 1
        assert route.enabled_mcp_servers == ("azure", "workiq")
        # A swallowed timeout/measurement failure is not evidence of resource drift.
        assert comparison.has_failures() is False
        assert comparison.off_error is comparison.on_error is None
        assert comparison.off is not None and comparison.on is not None
        assert comparison.off.connected_mcp_servers == ("azure", "workiq")
        assert comparison.on.connected_mcp_servers == ("azure",)
        assert comparison.off.report.unconnected == ()
        assert comparison.on.report.unconnected == ("workiq",)
        assert comparison.comparable is False
        assert comparison.reason == "runtime_resource_drift"
        assert comparison.runtime_resources["connected_mcp_servers_match"] is False
        assert comparison.runtime_resources["enabled_skills_match"] is True
        assert all(value is None for value in comparison.reduction.values())

    def test_runtime_exception_is_sanitized_before_comparison_output(self) -> None:
        client = _FakeClient(_FakeSession())

        with patch(
            "hve.toolsearch.context_report.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.toolsearch.context_report.create_session_from_route",
            AsyncMock(
                side_effect=RuntimeError(
                    "Authorization: Bearer secret-value"
                )
            ),
        ):
            with pytest.raises(ContextReportError) as captured:
                asyncio.run(
                    __import__(
                        "hve.toolsearch.context_report",
                        fromlist=["_measure_once"],
                    )._measure_once(
                        repo_root=Path.cwd(),
                        config=_FakeConfig(),
                        session_options={"streaming": True},
                        workflow_id="ard",
                        route=object(),
                        tool_search_enabled=True,
                        tool_search_defer_threshold=30,
                    )
                )

        assert "secret-value" not in str(captured.value)
        assert "[REDACTED]" in str(captured.value)
        assert client.stop_calls == 1

    def test_cleanup_runs_when_skills_schema_is_invalid(self) -> None:
        session = _FakeSession(invalid_skills=True)
        client = _FakeClient(session)

        with patch(
            "hve.toolsearch.context_report.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.toolsearch.context_report.create_session_from_route",
            AsyncMock(return_value=session),
        ):
            with pytest.raises(ContextReportError, match="Skill"):
                asyncio.run(
                    __import__("hve.toolsearch.context_report", fromlist=["_measure_once"])._measure_once(
                        repo_root=Path.cwd(),
                        config=_FakeConfig(),
                        session_options={"streaming": True, "model": "claude-opus-4.7"},
                        workflow_id="ard",
                        route=object(),
                        tool_search_enabled=True,
                        tool_search_defer_threshold=30,
                    )
                )

        assert session.disconnect_calls == 1
        assert client.stop_calls == 1

    def test_cleanup_runs_when_connected_mcp_schema_is_invalid(self) -> None:
        session = _FakeSession(invalid_mcp=True)
        client = _FakeClient(session)

        with patch(
            "hve.toolsearch.context_report.create_copilot_client",
            return_value=client,
        ), patch(
            "hve.toolsearch.context_report.create_session_from_route",
            AsyncMock(return_value=session),
        ):
            with pytest.raises(ContextReportError, match="MCP"):
                asyncio.run(
                    __import__("hve.toolsearch.context_report", fromlist=["_measure_once"])._measure_once(
                        repo_root=Path.cwd(),
                        config=_FakeConfig(),
                        session_options={"streaming": True, "model": "claude-opus-4.7"},
                        workflow_id="ard",
                        route=object(),
                        tool_search_enabled=False,
                        tool_search_defer_threshold=None,
                    )
                )

        assert session.disconnect_calls == 1
        assert client.stop_calls == 1