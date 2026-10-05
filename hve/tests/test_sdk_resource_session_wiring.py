"""FR-MODEL-04: `tool_search_defer_threshold` の 3 面配線と全ローカル Session への伝搬契約。

対象:
- `SDKConfig` の既定値 / 環境変数 / `tool_search_session_option()` の単一組み立て
- `orchestrate` CLI の `--tool-search-defer-threshold`
- GUI の `OrchestrateArgs` / 設定ストア / 永続化セクション / Prompt 版 allowlist
- ローカル orchestrator セッション（ARD 補助 / Fleet 親 / Code Review）への伝搬
- Cloud Session へはローカル固有キーを渡さないこと

main セッション / サブセッション（Pre-QA / Review）の伝搬は、
既存の fake SDK harness を持つ `test_runner.py` 側で検査する。
"""

from __future__ import annotations

import asyncio
import importlib
import types
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest
from copilot.generated.rpc import CurrentToolMetadata, ToolsGetCurrentMetadataResult

from hve.config import SDKConfig
from hve.console import Console
from hve.gui import settings_apply, settings_store
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot

_main = importlib.import_module("hve.__main__")

_ENV_KEY = "HVE_TOOL_SEARCH_DEFER_THRESHOLD"


def _config(**overrides: Any) -> SDKConfig:
    return SDKConfig(**overrides)


class TestConfigDeferThreshold(unittest.TestCase):
    """SDKConfig が閾値の唯一の組み立て口であること。"""

    def test_default_is_unset(self) -> None:
        self.assertIsNone(_config().tool_search_defer_threshold)

    def test_option_omits_threshold_when_unset(self) -> None:
        self.assertEqual(
            _config(tool_search=True).tool_search_session_option(),
            {"enabled": True},
        )

    def test_option_includes_positive_threshold(self) -> None:
        self.assertEqual(
            _config(tool_search=True, tool_search_defer_threshold=30).tool_search_session_option(),
            {"enabled": True, "defer_threshold": 30},
        )

    def test_option_is_none_when_tool_search_disabled(self) -> None:
        """FR-MODEL-06: 明示的な無効化は閾値指定でも tool_search を送らない。"""
        cfg = _config(tool_search=False, tool_search_defer_threshold=30)
        self.assertIsNone(cfg.tool_search_session_option())

    def test_option_omits_non_positive_threshold(self) -> None:
        for value in (0, -1):
            with self.subTest(value=value):
                self.assertEqual(
                    _config(tool_search=True, tool_search_defer_threshold=value).tool_search_session_option(),
                    {"enabled": True},
                )

    def test_option_omits_bool_threshold(self) -> None:
        """bool は int の派生型だが閾値として意味を持たないため送らない。"""
        self.assertEqual(
            _config(tool_search=True, tool_search_defer_threshold=True).tool_search_session_option(),
            {"enabled": True},
        )


class TestConfigDeferThresholdFromEnv(unittest.TestCase):
    """環境変数は正の整数だけを採用し、それ以外は SDK 既定へ委譲する。"""

    def _from_env(self, raw: str | None) -> Any:
        env: Dict[str, str] = {} if raw is None else {_ENV_KEY: raw}
        with mock.patch.dict("os.environ", env, clear=False):
            if raw is None:
                import os

                os.environ.pop(_ENV_KEY, None)
            return SDKConfig.from_env().tool_search_defer_threshold

    def test_unset_env_is_none(self) -> None:
        self.assertIsNone(self._from_env(None))

    def test_positive_env_is_applied(self) -> None:
        self.assertEqual(self._from_env("25"), 25)

    def test_zero_and_negative_env_fall_back_to_sdk_default(self) -> None:
        for raw in ("0", "-5"):
            with self.subTest(raw=raw):
                self.assertIsNone(self._from_env(raw))

    def test_non_integer_env_falls_back_to_sdk_default(self) -> None:
        for raw in ("abc", "1.5", "   "):
            with self.subTest(raw=raw):
                self.assertIsNone(self._from_env(raw))


class TestCliDeferThreshold(unittest.TestCase):
    """`orchestrate` の CLI フラグが SDKConfig へ届くこと。"""

    def _parse(self, extra: list[str]):
        return _main._build_parser().parse_args(["orchestrate", "--workflow", "ard", *extra])

    def test_flag_sets_config_value(self) -> None:
        args = self._parse(["--tool-search-defer-threshold", "30"])
        self.assertEqual(args.tool_search_defer_threshold, 30)
        self.assertEqual(_main._build_config(args).tool_search_defer_threshold, 30)

    def test_absent_flag_leaves_config_default(self) -> None:
        args = self._parse([])
        self.assertIsNone(args.tool_search_defer_threshold)
        self.assertIsNone(_main._build_config(args).tool_search_defer_threshold)

    def test_non_positive_value_is_rejected(self) -> None:
        for raw in ("0", "-1"):
            with self.subTest(raw=raw):
                with self.assertRaises(SystemExit):
                    self._parse(["--tool-search-defer-threshold", raw])

    def test_non_integer_value_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            self._parse(["--tool-search-defer-threshold", "abc"])


class TestGuiDeferThreshold(unittest.TestCase):
    """GUI の引数組み立てと設定永続化に閾値が載ること。"""

    def test_argv_includes_positive_threshold(self) -> None:
        argv = OrchestrateArgs(workflow="ard", tool_search_defer_threshold=30).to_argv()
        self.assertIn("--tool-search-defer-threshold", argv)
        self.assertEqual(argv[argv.index("--tool-search-defer-threshold") + 1], "30")

    def test_argv_omits_unset_or_non_positive_threshold(self) -> None:
        for value in (None, 0):
            with self.subTest(value=value):
                argv = OrchestrateArgs(workflow="ard", tool_search_defer_threshold=value).to_argv()
                self.assertNotIn("--tool-search-defer-threshold", argv)

    def test_store_default_exists(self) -> None:
        self.assertIn("tool_search_defer_threshold", settings_store.defaults()["options"])

    def test_persisted_by_the_toolsearch_section(self) -> None:
        self.assertIn(
            "tool_search_defer_threshold",
            settings_apply._SECTION_FIELDS["TOOLSEARCH"],
        )

    def test_is_overridable_from_prompt_requests(self) -> None:
        """FR-LOCAL-SURFACE-01 (a): shared setting として run 単位上書きできる。"""
        from hve.prompt_request import ALLOWED_SETTINGS_OVERRIDES

        self.assertIn("tool_search_defer_threshold", ALLOWED_SETTINGS_OVERRIDES)

    def test_saved_setting_reaches_orchestrate_args(self) -> None:
        from hve.gui.orchestrate_args import args_from_settings

        args = args_from_settings(
            {"options": {"tool_search_defer_threshold": 42}},
            workflow="ard",
        )
        self.assertEqual(args.tool_search_defer_threshold, 42)

    def test_saved_zero_is_normalized_to_unset(self) -> None:
        """QSpinBox 既定 0 は「未指定」として扱う（`_ZERO_MEANS_UNSET` 規約）。

        GUI 側のブリッジは 0 を `None` のまま残すため、Prompt 側だけ `0` になると
        同じ保存値に対して面ごとに値表現が食い違う。
        """
        from hve.gui.orchestrate_args import args_from_settings

        args = args_from_settings(
            {"options": {"tool_search_defer_threshold": 0}},
            workflow="ard",
        )
        self.assertIsNone(args.tool_search_defer_threshold)
        self.assertNotIn("--tool-search-defer-threshold", args.to_argv())


class _FakeSession:
    def __init__(self, options: Dict[str, Any] | None = None) -> None:
        self.options = options or {}
        self.calls: list[str] = []
        self.handlers: list[Any] = []
        self.initialized = False
        self.listed_servers: list[str] = []
        self.last_update: Any = None
        self.rpc = types.SimpleNamespace(
            tools=types.SimpleNamespace(
                initialize_and_validate=mock.AsyncMock(side_effect=self._initialize),
                get_current_metadata=mock.AsyncMock(side_effect=self._get_current_metadata),
            ),
            mcp=types.SimpleNamespace(
                list=mock.AsyncMock(side_effect=self._list_servers),
                list_tools=mock.AsyncMock(side_effect=self._list_tools),
                disable=mock.AsyncMock(side_effect=AssertionError("unexpected disable")),
                enable=mock.AsyncMock(side_effect=AssertionError("MCP must not be restored")),
            ),
            options=types.SimpleNamespace(
                update=mock.AsyncMock(side_effect=self._update),
            ),
        )

    async def _initialize(self, *, timeout: float) -> None:
        assert timeout > 0
        self.calls.append("initialize")
        self.initialized = True

    async def _list_servers(self, *, timeout: float) -> Any:
        assert timeout > 0 and self.initialized
        self.calls.append("mcp.list")
        return types.SimpleNamespace(
            host=types.SimpleNamespace(),
            servers=[
                types.SimpleNamespace(
                    name=name,
                    status="disabled" if name in self.options.get("disabled_mcp_servers", ()) else "connected",
                )
                for name in ("workiq", "other-knowledge", "unknown")
            ],
        )

    async def _list_tools(self, request: Any, *, timeout: float) -> Any:
        assert timeout > 0 and self.initialized
        assert request.server_name not in self.options.get("disabled_mcp_servers", ())
        self.calls.append(f"mcp.list_tools:{request.server_name}")
        self.listed_servers.append(request.server_name)
        return types.SimpleNamespace(tools=[
            types.SimpleNamespace(name="ask" if request.server_name == "workiq" else "search"),
            types.SimpleNamespace(name="write"),
        ])

    async def _update(self, request: Any, *, timeout: float) -> Any:
        assert timeout > 0
        self.calls.append("options.update")
        self.last_update = request
        return types.SimpleNamespace(success=True)

    async def _get_current_metadata(
        self, *, timeout: float
    ) -> ToolsGetCurrentMetadataResult:
        assert timeout > 0 and self.initialized
        self.calls.append("tools.get_current_metadata")
        available = (
            None
            if self.last_update is None or self.last_update.available_tools is None
            else set(self.last_update.available_tools)
        )
        excluded = set(
            () if self.last_update is None else self.last_update.excluded_tools or ()
        )
        tools = []
        for server_name in dict.fromkeys(self.listed_servers):
            tool_name = "ask" if server_name == "workiq" else "search"
            tool_id = f"mcp:{server_name}-{tool_name}"
            if available is not None and tool_id not in available:
                continue
            if tool_id in excluded:
                continue
            tools.append(
                CurrentToolMetadata(
                    description="offline MCP tool",
                    name=f"mcp__{server_name}__{tool_name}",
                    mcp_server_name=server_name,
                    mcp_tool_name=tool_name,
                    namespaced_name=tool_id,
                )
            )
        return ToolsGetCurrentMetadataResult(tools=tools)

    def on(self, handler: Any) -> Any:
        self.handlers.append(handler)
        if "cloud" in self.options:
            handler(types.SimpleNamespace(
                type=types.SimpleNamespace(value="session.start"),
                data=types.SimpleNamespace(producer="copilot-agent"),
            ))
        return lambda: self.handlers.remove(handler)

    async def send_and_wait(self, _prompt: str, *, timeout: float) -> Any:
        assert timeout > 0
        self.calls.append("send")
        return types.SimpleNamespace(content="合格判定: PASS", data=None)

    async def disconnect(self) -> None:
        self.calls.append("disconnect")


class _FakeClient:
    def __init__(self) -> None:
        self.create_session_kwargs: list[Dict[str, Any]] = []
        self.sessions: list[_FakeSession] = []
        self.start_count = 0
        self.stop_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    async def create_session(self, **kwargs: Any) -> _FakeSession:
        self.create_session_kwargs.append(kwargs)
        session = _FakeSession(kwargs)
        self.sessions.append(session)
        if kwargs.get("on_event") is not None:
            session.on(kwargs["on_event"])
        return session


class _CloudRejectingClient(_FakeClient):
    async def create_session(self, **kwargs: Any) -> _FakeSession:
        if "cloud" in kwargs:
            self.create_session_kwargs.append(kwargs)
            raise TypeError(
                "create_session() got an unexpected keyword argument 'cloud'"
            )
        return await super().create_session(**kwargs)


class TestCloudToLocalResourceRoutingFallback(unittest.TestCase):
    """FR-TS-13: Cloud失敗後のlocal fallbackもshared routeを通す。"""

    def _assert_fallback_routes(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        client = _CloudRejectingClient()
        routed_session = _FakeSession()
        snapshot = object()
        policy = object()
        create_routed_session = mock.AsyncMock(return_value=routed_session)
        policy_loader = mock.Mock(return_value=policy)

        with mock.patch.object(
            module,
            "discover_sdk_resources",
            create=True,
            return_value=snapshot,
        ) as discover, mock.patch.object(
            module,
            "ToolSearchPolicy",
            create=True,
            new=types.SimpleNamespace(load=policy_loader),
        ), mock.patch.object(
            module,
            "create_routed_session",
            create=True,
            new=create_routed_session,
        ):
            result = asyncio.run(
                module._create_session_with_auto_reasoning_fallback(
                    client,
                    {
                        "streaming": False,
                        "cloud": {"repository": "owner/name"},
                    },
                    config=_config(tool_search=True),
                    step_id="1.1",
                    workflow_id="ard",
                    subtask_kind="main",
                )
            )

        self.assertIs(result, routed_session)
        self.assertEqual(len(client.create_session_kwargs), 1)
        self.assertIn("cloud", client.create_session_kwargs[0])
        discover.assert_called_once()
        policy_loader.assert_called_once()
        create_routed_session.assert_awaited_once()
        routed_options = create_routed_session.await_args.kwargs["session_options"]
        self.assertNotIn("cloud", routed_options)
        self.assertFalse(routed_options["streaming"])

    def test_runner_cloud_fallback_uses_shared_resource_routing(self) -> None:
        self._assert_fallback_routes("hve.runner")

    def test_orchestrator_cloud_fallback_uses_shared_resource_routing(self) -> None:
        self._assert_fallback_routes("hve.orchestrator")


class TestOrchestratorSessionDeferThreshold(unittest.TestCase):
    """ARD 補助 / Fleet 親 / Code Review が使う共通ヘルパーへの伝搬。"""

    def _create(self, cfg: SDKConfig | None) -> Dict[str, Any]:
        return self._create_with(cfg, {"streaming": True})

    def _create_with(
        self, cfg: SDKConfig | None, session_options: Dict[str, Any]
    ) -> Dict[str, Any]:
        orchestrator = importlib.import_module("hve.orchestrator")
        client = _FakeClient()
        asyncio.run(
            orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                session_options,
                config=cfg,
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        )
        self.assertTrue(client.create_session_kwargs)
        return client.create_session_kwargs[0]

    def test_threshold_is_propagated(self) -> None:
        kwargs = self._create(_config(tool_search=True, tool_search_defer_threshold=30))
        self.assertEqual(kwargs.get("tool_search"), {"enabled": True, "defer_threshold": 30})

    def test_enabled_without_threshold(self) -> None:
        kwargs = self._create(_config(tool_search=True))
        self.assertEqual(kwargs.get("tool_search"), {"enabled": True})

    def test_disabled_tool_search_sends_no_key(self) -> None:
        kwargs = self._create(_config(tool_search=False, tool_search_defer_threshold=30))
        self.assertNotIn("tool_search", kwargs)

    def test_absent_config_sends_no_key(self) -> None:
        self.assertNotIn("tool_search", self._create(None))

    def test_cloud_session_does_not_receive_the_local_key(self) -> None:
        """FR-MODEL-04: Cloud Session は本要件の対象外で、ローカル固有キーを渡さない。"""
        kwargs = self._create_with(
            _config(tool_search=True, tool_search_defer_threshold=30),
            {"streaming": True, "cloud": {"repository": "owner/name"}},
        )
        self.assertNotIn("tool_search", kwargs)


class TestOrchestratorSessionResourceRouting(unittest.TestCase):
    """FR-TS-13: local orchestrator session は resource_routing SSOT を通す。"""

    def test_local_session_uses_shared_resource_routing_helper(self) -> None:
        orchestrator = importlib.import_module("hve.orchestrator")
        client = _FakeClient()
        routed_session = _FakeSession()
        snapshot = object()
        policy = object()
        create_routed_session = mock.AsyncMock(return_value=routed_session)
        policy_loader = mock.Mock(return_value=policy)

        with mock.patch.object(
            orchestrator,
            "discover_sdk_resources",
            create=True,
            return_value=snapshot,
        ) as discover, mock.patch.object(
            orchestrator,
            "ToolSearchPolicy",
            create=True,
            new=types.SimpleNamespace(load=policy_loader),
        ), mock.patch.object(
            orchestrator,
            "create_routed_session",
            create=True,
            new=create_routed_session,
        ):
            result = asyncio.run(
                orchestrator._create_session_with_auto_reasoning_fallback(
                    client,
                    {"streaming": True},
                    config=_config(tool_search=True, tool_search_defer_threshold=30),
                    step_id="orchestrator",
                    workflow_id="ard",
                    subtask_kind="orchestrator",
                )
            )

        self.assertIs(result, routed_session)
        self.assertFalse(client.create_session_kwargs)
        discover.assert_called_once()
        policy_loader.assert_called_once()
        create_routed_session.assert_awaited_once()
        kwargs = create_routed_session.await_args.kwargs
        self.assertIs(kwargs["client"], client)
        self.assertIs(kwargs["snapshot"], snapshot)
        self.assertIs(kwargs["policy"], policy)
        self.assertEqual(kwargs["workflow_id"], "ard")
        self.assertNotIn("mcp_servers", kwargs["session_options"])
        self.assertEqual(
            kwargs["session_options"].get("tool_search"),
            {"enabled": True, "defer_threshold": 30},
        )

    def test_local_session_propagates_required_and_optional_skills_to_routing(self) -> None:
        orchestrator = importlib.import_module("hve.orchestrator")
        client = _FakeClient()
        routed_session = _FakeSession()
        snapshot = object()
        policy = object()
        create_routed_session = mock.AsyncMock(return_value=routed_session)
        policy_loader = mock.Mock(return_value=policy)

        with mock.patch.object(
            orchestrator,
            "discover_sdk_resources",
            create=True,
            return_value=snapshot,
        ) as discover, mock.patch.object(
            orchestrator,
            "ToolSearchPolicy",
            create=True,
            new=types.SimpleNamespace(load=policy_loader),
        ), mock.patch.object(
            orchestrator,
            "create_routed_session",
            create=True,
            new=create_routed_session,
        ):
            result = asyncio.run(
                orchestrator._create_session_with_auto_reasoning_fallback(
                    client,
                    {"streaming": True},
                    config=_config(tool_search=True),
                    step_id="orchestrator",
                    workflow_id="ard",
                    subtask_kind="orchestrator",
                    required_skills=["knowledge-management"],
                    optional_skills=["knowledge-lookup"],
                )
            )

        self.assertIs(result, routed_session)
        discover.assert_called_once()
        create_routed_session.assert_awaited_once()
        kwargs = create_routed_session.await_args.kwargs
        self.assertEqual(kwargs["required_skills"], ["knowledge-management"])
        self.assertEqual(kwargs["optional_skills"], ["knowledge-lookup"])

    def test_cloud_session_skips_shared_resource_routing_helper(self) -> None:
        orchestrator = importlib.import_module("hve.orchestrator")
        client = _FakeClient()
        create_routed_session = mock.AsyncMock(return_value=_FakeSession())

        with mock.patch.object(
            orchestrator,
            "discover_sdk_resources",
            create=True,
        ) as discover, mock.patch.object(
            orchestrator,
            "create_routed_session",
            create=True,
            new=create_routed_session,
        ):
            kwargs = TestOrchestratorSessionDeferThreshold()._create_with(
                _config(tool_search=True, tool_search_defer_threshold=30),
                {"streaming": True, "cloud": {"repository": "owner/name"}},
            )

        discover.assert_not_called()
        create_routed_session.assert_not_awaited()
        self.assertEqual(kwargs["cloud"], {"repository": "owner/name"})


class TestFleetParentSessionDeferThreshold(unittest.TestCase):
    """Fleet 親は `config=None` で共通ヘルパーを呼ぶため、呼び出し側注入が要る。

    FR-MODEL-04 は Fleet 親も伝搬対象に含める。ここは
    `_build_fleet_wave_runner` の内側クロージャで、SDK Fleet backend を
    実体化せずに実行できないため、既存の
    `test_orchestrator_fanout_repo_root.py` と同じ AST 検査で注入の実在を確認する。
    """

    def _fleet_function(self) -> Any:
        import ast

        source = _orchestrator_source()
        tree = ast.parse(source)
        targets = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_fleet_wave_runner"
        ]
        self.assertTrue(targets, "_build_fleet_wave_runner が見つかりません")
        return ast.walk(targets[0])

    def test_fleet_parent_assigns_tool_search_from_the_single_builder(self) -> None:
        import ast

        calls = [
            node
            for node in self._fleet_function()
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tool_search_session_option"
        ]
        self.assertTrue(
            calls,
            "Fleet 親セッションが SDKConfig.tool_search_session_option() を呼んでいません",
        )

    def test_fleet_parent_sets_the_tool_search_session_key(self) -> None:
        import ast

        assigned = [
            node
            for node in self._fleet_function()
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "session_opts"
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "tool_search"
        ]
        self.assertTrue(
            assigned,
            "Fleet 親セッションの session_opts へ tool_search が載っていません",
        )

    def test_fleet_parent_calls_shared_helper_with_workflow_id(self) -> None:
        import ast

        helper_calls = [
            node
            for node in self._fleet_function()
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_create_session_with_auto_reasoning_fallback"
        ]
        self.assertTrue(helper_calls, "Fleet 親が共有 helper を呼んでいません")
        self.assertTrue(
            any(
                any(keyword.arg == "workflow_id" for keyword in call.keywords)
                for call in helper_calls
            ),
            "Fleet 親が workflow_id を共有 helper へ渡していません",
        )

    def test_fleet_parent_disables_cloud_injection_without_dropping_config(self) -> None:
        import ast

        helper_calls = [
            node
            for node in self._fleet_function()
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_create_session_with_auto_reasoning_fallback"
        ]
        self.assertTrue(helper_calls, "Fleet 親が共有 helper を呼んでいません")
        self.assertTrue(
            any(
                any(keyword.arg == "config" and isinstance(keyword.value, ast.Name) and keyword.value.id == "config" for keyword in call.keywords)
                and any(keyword.arg == "allow_cloud_session_injection" for keyword in call.keywords)
                for call in helper_calls
            ),
            "Fleet 親が config を保持したまま cloud injection 無効化を指定していません",
        )


class TestCodeReviewSessionRouting(unittest.TestCase):
    def test_code_review_calls_shared_helper_with_workflow_id(self) -> None:
        import ast

        source = _orchestrator_source()
        tree = ast.parse(source)
        targets = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_request_code_review"
        ]
        self.assertTrue(targets, "_request_code_review が見つかりません")
        helper_calls = [
            node
            for node in ast.walk(targets[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_create_session_with_auto_reasoning_fallback"
        ]
        self.assertTrue(helper_calls, "Code Review が共有 helper を呼んでいません")
        self.assertTrue(
            any(
                any(keyword.arg == "workflow_id" for keyword in call.keywords)
                for call in helper_calls
            ),
            "Code Review session が workflow_id を共有 helper へ渡していません",
        )


@pytest.fixture
def routed_resources(monkeypatch):
    """Discovery だけを隔離し、route の解決・初期化・ACK は実装を通す。"""
    snapshot = ResourceSnapshot(
        plugin_state="ready",
        mcp_state="ready",
        skill_state="ready",
        skill_ownership_state="ready",
        plugins=(),
        mcp_servers=tuple(
            ResourceItem("mcp_server", name, True, "user")
            for name in ("workiq", "other-knowledge", "unknown")
        ),
        skills=(),
    )
    policy = replace(
        ToolSearchPolicy.load(),
        resource_classifications={
            "plugins": {},
            "mcp_servers": {"workiq": "knowledge", "other-knowledge": "knowledge"},
            "skills": {},
        },
        knowledge_tool_allowlists={"workiq": ("ask",), "other-knowledge": ("search",)},
    )
    discoveries = {}
    monkeypatch.setattr(SDKConfig, "resolve_token", lambda _self: None)
    for name in ("hve.runner", "hve.orchestrator"):
        module = importlib.import_module(name)
        discoveries[name] = mock.Mock(return_value=snapshot)
        monkeypatch.setattr(module, "discover_sdk_resources", discoveries[name])
        monkeypatch.setattr(
            module, "ToolSearchPolicy",
            types.SimpleNamespace(load=lambda **_kwargs: policy),
        )
    return discoveries


def _assert_runtime_ready(session, servers=("workiq",)) -> None:
    expected = ["initialize"]
    for name in servers:
        expected.extend(("mcp.list", f"mcp.list_tools:{name}"))
    expected.extend(("options.update", "tools.get_current_metadata"))
    assert session.calls[:len(expected)] == expected
    session.rpc.tools.initialize_and_validate.assert_awaited_once()
    session.rpc.tools.get_current_metadata.assert_awaited_once()
    session.rpc.options.update.assert_awaited_once()
    session.rpc.mcp.disable.assert_not_awaited()
    session.rpc.mcp.enable.assert_not_awaited()


@pytest.mark.parametrize("consumer", ["runner", "orchestrator"])
def test_local_consumers_apply_real_readiness_before_send(
    consumer: str, routed_resources,
) -> None:
    """FR-TS-13: caller 除外と filter を維持し、共有 gate 後だけ send する。"""
    module_name = f"hve.{consumer}"
    module = importlib.import_module(module_name)
    client = _FakeClient()
    options = {
        "streaming": False,
        "disabled_mcp_servers": ["other-knowledge"],
        "available_tools": ["builtin:view", "mcp:workiq-ask"],
        "excluded_tools": ["builtin:shell"],
    }

    async def exercise():
        session = await module._create_session_with_auto_reasoning_fallback(
            client, options, config=_config(),
            workflow_id="aag", step_id="1", subtask_kind="main",
        )
        await session.send_and_wait("offline consumer", timeout=0.1)
        return session

    session = asyncio.run(exercise())
    _assert_runtime_ready(session)
    assert session.calls[-1] == "send"
    routed_resources[module_name].assert_called_once()
    created = client.create_session_kwargs[0]
    assert created["disabled_mcp_servers"] == ["other-knowledge", "unknown", "github-mcp-server"]
    assert created["enable_skills"] is True
    assert created["enable_config_discovery"] is True
    assert "mcp_servers" not in created
    update = session.rpc.options.update.await_args.args[0]
    assert update.available_tools == options["available_tools"]
    assert update.excluded_tools == ["builtin:shell", "mcp:workiq-write"]


@pytest.mark.parametrize("module_name", ["hve.runner", "hve.orchestrator"])
def test_cloud_fallback_applies_real_readiness_before_local_send(
    module_name: str, routed_resources,
) -> None:
    """FR-TS-13: Cloud 拒否からの再試行も実 router を省略しない。"""
    module = importlib.import_module(module_name)
    client = _CloudRejectingClient()

    async def exercise():
        session = await module._create_session_with_auto_reasoning_fallback(
            client,
            {
                "streaming": False,
                "cloud": {"repository": "owner/name"},
                "disabled_mcp_servers": ["other-knowledge"],
            },
            config=_config(), workflow_id="ard", step_id="1", subtask_kind="main",
        )
        await session.send_and_wait("offline fallback", timeout=0.1)
        return session

    session = asyncio.run(exercise())
    _assert_runtime_ready(session)
    assert session.calls[-1] == "send"
    assert len(client.create_session_kwargs) == 2
    assert "cloud" in client.create_session_kwargs[0]
    local = client.create_session_kwargs[1]
    assert "cloud" not in local
    assert "mcp_servers" not in local
    assert local["disabled_mcp_servers"] == ["other-knowledge", "unknown", "github-mcp-server"]
    assert local["streaming"] is False
    routed_resources[module_name].assert_called_once()


def test_code_review_runs_real_readiness_before_review_turn(routed_resources, monkeypatch):
    orchestrator = importlib.import_module("hve.orchestrator")
    client = _FakeClient()
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", lambda *_a, **_k: client)
    monkeypatch.setattr(orchestrator, "_get_git_diff", lambda *_a: "offline test diff")
    repair_approval = mock.Mock(
        side_effect=AssertionError("Code Review PASS must not request repair approval"),
    )
    monkeypatch.setattr(orchestrator.sys.stdin, "isatty", repair_approval)

    result = asyncio.run(orchestrator._request_code_review(
        None, _config(tool_search_defer_threshold=30),
        Console(verbose=False, quiet=True), workflow_id="ard",
    ))

    assert result is None
    repair_approval.assert_not_called()
    assert len(client.sessions) == 1
    session = client.sessions[0]
    _assert_runtime_ready(session, ("workiq", "other-knowledge"))
    assert session.calls.count("send") == 1
    assert session.calls[-2:] == ["send", "disconnect"]
    assert client.start_count == client.stop_count == 1
    assert client.create_session_kwargs[0]["tool_search"]["defer_threshold"] == 30
    routed_resources["hve.orchestrator"].assert_called_once()


def test_fleet_parent_runs_real_readiness_before_fleet_start(
    routed_resources, monkeypatch, tmp_path,
):
    """外側の run_workflow は実行せず、製品の Fleet closure だけを駆動する。"""
    import ast
    from hve import fleet_mode, run_paths

    orchestrator = importlib.import_module("hve.orchestrator")
    client = _FakeClient()
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", lambda *_a, **_k: client)
    monkeypatch.setattr(
        orchestrator, "build_cloud_session_options",
        mock.Mock(side_effect=AssertionError("Fleet must remain local")),
    )
    monkeypatch.setattr(run_paths, "resolve_work_root", lambda: tmp_path)
    monkeypatch.setattr(fleet_mode, "check_subtask_completion", lambda *_a: (True, ""))
    monkeypatch.setattr(fleet_mode, "build_dag_wave_fleet_prompt", lambda **_k: types.SimpleNamespace(
        prompt="offline fleet", task_step_ids=("1", "2"),
        report_dirs={"1": "Issue-1", "2": "Issue-2"},
    ))

    async def start(session, _prompt):
        _assert_runtime_ready(session, ("workiq", "other-knowledge"))
        session.calls.append("fleet.start")
        return types.SimpleNamespace(started=True)

    monkeypatch.setattr(fleet_mode, "start_fleet", start)
    node = next(
        node for node in ast.walk(ast.parse(_orchestrator_source()))
        if isinstance(node, ast.FunctionDef) and node.name == "_build_fleet_wave_runner"
    )
    scope = dict(
        vars(orchestrator),
        config=_config(fleet_mode_enabled=True, cloud_session_enabled=True, tool_search_defer_threshold=30),
        console=Console(verbose=False, quiet=True), workflow_id="ard",
        step_prompts={"1": "first", "2": "second"}, effective_params={},
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), orchestrator.__file__, "exec"), scope)
    run_wave = scope["_build_fleet_wave_runner"]()
    results = asyncio.run(run_wave([types.SimpleNamespace(id="1"), types.SimpleNamespace(id="2")], 1))

    assert set(results) == {"1", "2"}
    assert all(result.success for result in results.values())
    assert client.sessions[0].calls[-2:] == ["fleet.start", "disconnect"]
    assert client.start_count == client.stop_count == 1
    created = client.create_session_kwargs[0]
    assert "cloud" not in created
    assert "mcp_servers" not in created
    assert created["disabled_mcp_servers"] == ["unknown", "github-mcp-server"]
    assert created["tool_search"] == {"enabled": True, "defer_threshold": 30}
    routed_resources["hve.orchestrator"].assert_called_once()


def test_knowledge_discovery_uses_one_unrouted_session_without_mcp_restore(
    routed_resources, monkeypatch, tmp_path,
):
    """FR-KD-03 / FR-CLI-76: 知識探索は 1 セッションだけを作り、MCP 構成を復元・再有効化しない。"""
    orchestrator = importlib.import_module("hve.orchestrator")
    client = _FakeClient()
    factory = mock.Mock(return_value=client)
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", factory)
    monkeypatch.chdir(tmp_path)
    config = _config(cloud_session_enabled=True, workiq_enabled=True, run_id="kd-wiring")
    console = Console(verbose=False, quiet=True)

    result = asyncio.run(orchestrator._run_orchestrator_knowledge_discovery(
        config, console, mode="knowledge", label="akm", goal="不明点を調べる",
    ))

    assert result is not None and result.ran is True
    factory.assert_called_once()
    assert client.start_count == client.stop_count == 1
    assert len(client.create_session_kwargs) == 1
    options = client.create_session_kwargs[0]
    assert "mcp_servers" not in options and "cloud" not in options
    assert options["enable_config_discovery"] is True
    assert options["disabled_mcp_servers"] == ["other-knowledge", "unknown"]
    assert "mcp:workiq-ask" in options["available_tools"]
    assert "custom:hve_knowledge_write" in options["available_tools"]
    session = client.sessions[0]
    assert session.calls[:3] == ["initialize", "mcp.list", "mcp.list_tools:workiq"]
    assert session.calls[-1] == "disconnect"
    session.rpc.mcp.enable.assert_not_awaited()
    session.rpc.mcp.disable.assert_not_awaited()
    routed_resources["hve.orchestrator"].assert_called_once()


def _orchestrator_source() -> str:
    from pathlib import Path

    import hve.orchestrator as _orch

    return Path(_orch.__file__).read_text(encoding="utf-8")


def _creation_event(event_type: str, **data: Any) -> Any:
    return types.SimpleNamespace(
        type=types.SimpleNamespace(value=event_type),
        data=types.SimpleNamespace(**data),
    )


def _emit_creation_events(session: _FakeSession, events: tuple[Any, ...]) -> None:
    """登録済み handler へだけ配信し、後からの on() に replay しない。"""
    for event in events:
        for handler in tuple(session.handlers):
            handler(event)


class _CreationEventClient(_FakeClient):
    """T20 reviewR3: 実 SDK を起動せず create / init / send 中に発火する。"""

    def __init__(
        self, *, create_events: tuple[Any, ...], init_events: tuple[Any, ...],
        send_events: tuple[Any, ...] = (), init_error: BaseException | None = None,
    ) -> None:
        super().__init__()
        self.create_events = create_events
        self.init_events = init_events
        self.send_events = send_events
        self.init_error = init_error

    async def create_session(self, **kwargs: Any) -> _FakeSession:
        session = await super().create_session(**kwargs)

        async def initialize(*, timeout: float) -> None:
            assert timeout > 0
            session.calls.append("initialize")
            _emit_creation_events(session, self.init_events)
            if self.init_error is not None:
                raise self.init_error
            session.initialized = True

        session.rpc.tools.initialize_and_validate.side_effect = initialize
        original_send = session.send_and_wait

        async def send(prompt: str, *, timeout: float) -> Any:
            _emit_creation_events(session, self.send_events)
            return await original_send(prompt, timeout=timeout)

        session.send_and_wait = mock.AsyncMock(side_effect=send)
        _emit_creation_events(session, self.create_events)
        return session


def _creation_event_fleet_runner(orchestrator, client, console, monkeypatch, tmp_path):
    """既存の AST 足場と同様、run_workflow を呼ばず製品 closure だけを読む。"""
    import ast
    from hve import fleet_mode, run_paths

    assert Path(orchestrator.__file__).resolve() == (
        Path(__file__).resolve().parents[1] / "orchestrator.py"
    ), "Fleet must exercise the same worktree as this test"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", lambda *_a, **_k: client)
    monkeypatch.setattr(
        orchestrator, "build_cloud_session_options",
        mock.Mock(side_effect=AssertionError("Fleet must remain local")),
    )
    monkeypatch.setattr(
        orchestrator, "acquire_cloud_session_slot",
        mock.AsyncMock(side_effect=AssertionError("Local Fleet must not acquire a cloud slot")),
    )
    monkeypatch.setattr(run_paths, "resolve_work_root", lambda: tmp_path)
    monkeypatch.setattr(fleet_mode, "check_subtask_completion", lambda *_a: (True, ""))
    monkeypatch.setattr(fleet_mode, "build_dag_wave_fleet_prompt", lambda **_k: types.SimpleNamespace(
        prompt="offline fleet", task_step_ids=("1", "2"),
        report_dirs={"1": "Issue-1", "2": "Issue-2"},
    ))
    node = next(
        node for node in ast.walk(ast.parse(_orchestrator_source()))
        if isinstance(node, ast.FunctionDef) and node.name == "_build_fleet_wave_runner"
    )
    scope = dict(
        vars(orchestrator),
        config=_config(fleet_mode_enabled=True, cloud_session_enabled=True, timeout_seconds=1),
        console=console, workflow_id="ard",
        step_prompts={"1": "first", "2": "second"}, effective_params={},
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), orchestrator.__file__, "exec"), scope)
    return scope["_build_fleet_wave_runner"]()


@pytest.mark.parametrize("init_outcome", ["ready", "cancelled"])
def test_fleet_parent_handles_create_and_init_events_once(
    init_outcome, routed_resources, monkeypatch, tmp_path,
):
    """FR-TS-13 / FR-RTO-07: early event の実処理・帰属と cancel 非継続。"""
    from copilot.session import PermissionHandler
    from hve import fleet_mode

    orchestrator = importlib.import_module("hve.orchestrator")
    console = mock.Mock(spec=Console)
    console.show_stream = False
    create_events = (
        _creation_event("tool.execution_start", tool_call_id="worker-1", tool_name="runSubagent", arguments="Step.1"),
        _creation_event("subagent.started", tool_call_id="worker-1", agent_display_name="Worker A"),
    )
    init_events = (
        _creation_event("tool.execution_start", tool_call_id="worker-2", tool_name="runSubagent", arguments="Step.2"),
        _creation_event("subagent.started", tool_call_id="worker-2", agent_display_name="Worker B"),
        _creation_event("tool.execution_start", tool_call_id="tool-1", parent_tool_call_id="worker-1", tool_name="view"),
        _creation_event("tool.execution_start", tool_call_id="tool-2", parent_tool_call_id="worker-2", tool_name="edit"),
        _creation_event("subagent.completed", tool_call_id="worker-1", agent_display_name="Worker A"),
    )
    cancelled = init_outcome == "cancelled"
    if cancelled:
        init_events += (
            _creation_event("subagent.failed", tool_call_id="worker-2", agent_display_name="Worker B", error="offline init cancelled"),
        )
    late_events = (
        _creation_event("tool.execution_start", tool_call_id="tool-3", parent_tool_call_id="worker-2", tool_name="view"),
        _creation_event("subagent.completed", tool_call_id="worker-2", agent_display_name="Worker B"),
    )
    client = _CreationEventClient(
        create_events=create_events, init_events=init_events,
        init_error=asyncio.CancelledError("offline init cancelled") if cancelled else None,
    )
    handled = []
    real_handle_event = fleet_mode.FleetEventCollector.handle_event

    def record_handling(collector, event):
        real_handle_event(collector, event)
        handled.append((collector, event))

    monkeypatch.setattr(fleet_mode.FleetEventCollector, "handle_event", record_handling)

    async def start(session, _prompt):
        _assert_runtime_ready(session, ("workiq", "other-knowledge"))
        session.calls.append("fleet.start")
        _emit_creation_events(session, late_events)
        return types.SimpleNamespace(started=True)

    start_fleet = mock.AsyncMock(side_effect=start)
    monkeypatch.setattr(fleet_mode, "start_fleet", start_fleet)
    run_wave = _creation_event_fleet_runner(orchestrator, client, console, monkeypatch, tmp_path)
    steps = [types.SimpleNamespace(id="1"), types.SimpleNamespace(id="2")]
    if cancelled:
        with pytest.raises(asyncio.CancelledError, match="offline init cancelled"):
            asyncio.run(run_wave(steps, 1))
        start_fleet.assert_not_awaited()
        assert client.sessions[0].calls == ["initialize", "disconnect"]
        client.sessions[0].rpc.options.update.assert_not_awaited()
    else:
        results = asyncio.run(run_wave(steps, 1))
        assert set(results) == {"1", "2"}
        assert all(result.success for result in results.values())
        start_fleet.assert_awaited_once()
        assert client.sessions[0].calls[-2:] == ["fleet.start", "disconnect"]

    assert client.start_count == client.stop_count == 1
    assert len(client.sessions) == len(client.create_session_kwargs) == 1
    assert "send" not in client.sessions[0].calls
    assert "cloud" not in client.create_session_kwargs[0]
    assert client.create_session_kwargs[0]["on_permission_request"] is PermissionHandler.approve_all
    routed_resources["hve.orchestrator"].assert_called_once()
    # kwargs の存在だけでも、dict の冪等な上書きだけでも二重登録を見逃す。
    expected_events = create_events + init_events + (() if cancelled else late_events)
    assert [event for _collector, event in handled] == list(expected_events)
    collector = handled[0][0]
    assert all(owner is collector for owner, _event in handled)
    assert collector.running == {}
    assert collector.completed == (
        {"worker-1": "Worker A"} if cancelled
        else {"worker-1": "Worker A", "worker-2": "Worker B"}
    )
    assert collector.failed == (
        {"worker-2": "Worker B: offline init cancelled"} if cancelled else {}
    )
    assert console.subagent_started.call_args_list == [
        mock.call("Worker A", "Worker A"), mock.call("Worker B", "Worker B"),
    ]
    expected_tools = [
        mock.call("tool_invoked", step_id="1", tool_name="view"),
        mock.call("tool_invoked", step_id="2", tool_name="edit"),
    ]
    if not cancelled:
        expected_tools.append(mock.call("tool_invoked", step_id="2", tool_name="view"))
    assert console.stats_event.call_args_list == expected_tools


@pytest.mark.parametrize("init_outcome", ["ready", "init-failed"])
def test_code_review_handles_create_and_init_logs_once(
    init_outcome, routed_resources, monkeypatch, tmp_path,
):
    """FR-TS-13: create / init の session.log を失わず、失敗時は送信しない。"""
    orchestrator = importlib.import_module("hve.orchestrator")
    assert Path(orchestrator.__file__).resolve() == (
        Path(__file__).resolve().parents[1] / "orchestrator.py"
    ), "Code Review must exercise the same worktree as this test"
    monkeypatch.chdir(tmp_path)
    failed = init_outcome == "init-failed"
    client = _CreationEventClient(
        create_events=(_creation_event("session.log", level="info", message="review-create"),),
        init_events=(_creation_event("session.log", level="warning", message="review-initialize"),),
        send_events=(_creation_event("session.log", level="info", message="review-turn"),),
        init_error=RuntimeError("offline init failed") if failed else None,
    )
    console = mock.Mock(spec=Console)
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", lambda *_a, **_k: client)
    monkeypatch.setattr(orchestrator, "_get_git_diff", lambda *_a: "offline test diff")
    monkeypatch.setattr(orchestrator, "build_cloud_session_options", lambda *_a, **_k: None)
    result = asyncio.run(orchestrator._request_code_review(
        None, _config(cloud_session_enabled=False, unattended=True),
        console, workflow_id="ard",
    ))

    assert len(client.sessions) == len(client.create_session_kwargs) == 1
    assert client.start_count == client.stop_count == 1
    routed_resources["hve.orchestrator"].assert_called_once()
    session = client.sessions[0]
    session.rpc.tools.initialize_and_validate.assert_awaited_once()
    expected_logs = [
        mock.call("review", "[info] review-create"),
        mock.call("review", "[warning] review-initialize"),
    ]
    if failed:
        assert result is not None and "ResourceRoutingError" in result
        assert session.calls == ["initialize", "disconnect"]
        session.rpc.options.update.assert_not_awaited()
        session.rpc.mcp.list.assert_not_awaited()
    else:
        assert result is None
        _assert_runtime_ready(session, ("workiq", "other-knowledge"))
        assert session.calls.count("send") == 1
        assert session.calls[-2:] == ["send", "disconnect"]
        expected_logs.append(mock.call("review", "[info] review-turn"))
    # 製品の _review_session_event による Console 転送の内容・順序・回数を検証。
    assert console.cli_log.call_args_list == expected_logs


@pytest.mark.parametrize("init_failed", [False, True], ids=["ready", "init-failed"])
def test_code_review_redacts_create_and_init_logs(
    init_failed, routed_resources, monkeypatch, tmp_path,
):
    """T20R3: early diagnostic のダミー秘密情報を Console へ渡さない。"""
    orchestrator = importlib.import_module("hve.orchestrator")
    assert Path(orchestrator.__file__).resolve() == (
        Path(__file__).resolve().parents[1] / "orchestrator.py"
    ), "Code Review must exercise the same worktree as this test"
    monkeypatch.chdir(tmp_path)
    client = _CreationEventClient(
        create_events=(_creation_event(
            "session.log", level="info",
            message="review-create Authorization: Bearer synthetic-create-secret",
        ),),
        init_events=(_creation_event(
            "session.log", level="warning",
            message="review-initialize password=synthetic-init-secret",
        ),),
        init_error=RuntimeError("offline init failed") if init_failed else None,
    )
    console = mock.Mock(spec=Console)
    monkeypatch.setattr(orchestrator, "_create_copilot_client_from_config", lambda *_a, **_k: client)
    monkeypatch.setattr(orchestrator, "_get_git_diff", lambda *_a: "offline test diff")
    monkeypatch.setattr(orchestrator, "build_cloud_session_options", lambda *_a, **_k: None)

    result = asyncio.run(orchestrator._request_code_review(
        None, _config(cloud_session_enabled=False, unattended=True),
        console, workflow_id="ard",
    ))

    assert console.cli_log.call_args_list == [
        mock.call("review", "[info] review-create Authorization: Bearer [REDACTED]"),
        mock.call("review", "[warning] review-initialize password=[REDACTED]"),
    ]
    assert client.start_count == client.stop_count == 1
    if init_failed:
        assert result is not None and "ResourceRoutingError" in result
        assert client.sessions[0].calls == ["initialize", "disconnect"]
    else:
        assert result is None
        assert client.sessions[0].calls[-2:] == ["send", "disconnect"]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
