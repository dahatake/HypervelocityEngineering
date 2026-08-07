"""test_cloud_session.py — Cloud Session 設定と helper の単体テスト。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cloud_session import (  # type: ignore  # noqa: E402
    CloudSessionLimiter,
    apply_cloud_session_auto_routing,
    attach_cloud_session_limiter_release,
    compute_cloud_session_routing,
    extract_mission_control_url,
    build_cloud_session_options,
    format_cloud_session_event_line,
    is_policy_blocked_error,
    resolve_cloud_repository,
    should_use_cloud_session,
    wait_for_cloud_session_ready,
)
from config import SDKConfig  # type: ignore  # noqa: E402


class TestCloudSessionConfig(unittest.TestCase):
    def test_defaults_disabled(self) -> None:
        cfg = SDKConfig()
        self.assertFalse(cfg.cloud_session_enabled)
        self.assertIsNone(cfg.cloud_session_repository_owner)
        self.assertIsNone(cfg.cloud_session_repository_name)
        self.assertIsNone(cfg.cloud_session_repository_branch)
        self.assertEqual(cfg.cloud_session_max_concurrency, 5)
        self.assertEqual(cfg.cloud_session_step_overrides, {})
        self.assertEqual(cfg.cloud_session_subtask_overrides, {})

    def test_post_init_normalizes_strings_and_mappings(self) -> None:
        cfg = SDKConfig(
            cloud_session_enabled="yes",  # type: ignore[arg-type]
            cloud_session_repository_owner=" owner ",
            cloud_session_repository_name=" repo ",
            cloud_session_repository_branch=" main ",
            cloud_session_max_concurrency="0",  # type: ignore[arg-type]
            cloud_session_step_overrides='{"1": true, "2": "off", "x": "maybe"}',  # type: ignore[arg-type]
            cloud_session_subtask_overrides={"pre_qa": "on", "review": False},  # type: ignore[arg-type]
        )
        self.assertTrue(cfg.cloud_session_enabled)
        self.assertEqual(cfg.cloud_session_repository_owner, "owner")
        self.assertEqual(cfg.cloud_session_repository_name, "repo")
        self.assertEqual(cfg.cloud_session_repository_branch, "main")
        self.assertEqual(cfg.cloud_session_max_concurrency, 1)
        self.assertEqual(cfg.cloud_session_step_overrides, {"1": True, "2": False})
        self.assertEqual(cfg.cloud_session_subtask_overrides, {"pre_qa": True, "review": False})

    def test_from_env_reads_cloud_session_options(self) -> None:
        env = {
            "HVE_CLOUD_SESSION_ENABLED": "true",
            "HVE_CLOUD_SESSION_REPOSITORY_OWNER": "alice",
            "HVE_CLOUD_SESSION_REPOSITORY_NAME": "service",
            "HVE_CLOUD_SESSION_REPOSITORY_BRANCH": "feature/cloud",
            "HVE_CLOUD_SESSION_MAX_CONCURRENCY": "7",
            "GITHUB_COPILOT_INTEGRATION_ID": "integration-1",
            "COPILOT_MC_BASE_URL": "https://mc.example.test",
            "HVE_CLOUD_SESSION_STEP_OVERRIDES": '{"1": true, "2": false}',
            "HVE_CLOUD_SESSION_SUBTASK_OVERRIDES": '{"pre_qa": true}',
        }
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            cfg = SDKConfig.from_env()
        self.assertTrue(cfg.cloud_session_enabled)
        self.assertEqual(cfg.cloud_session_repository_owner, "alice")
        self.assertEqual(cfg.cloud_session_repository_name, "service")
        self.assertEqual(cfg.cloud_session_repository_branch, "feature/cloud")
        self.assertEqual(cfg.cloud_session_max_concurrency, 7)
        self.assertEqual(cfg.cloud_session_integration_id, "integration-1")
        self.assertEqual(cfg.cloud_session_mc_base_url, "https://mc.example.test")
        self.assertEqual(cfg.cloud_session_step_overrides, {"1": True, "2": False})
        self.assertEqual(cfg.cloud_session_subtask_overrides, {"pre_qa": True})

    def test_from_env_invalid_concurrency_falls_back_to_default(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"HVE_CLOUD_SESSION_MAX_CONCURRENCY": "invalid"}, clear=False):
            cfg = SDKConfig.from_env()
        self.assertEqual(cfg.cloud_session_max_concurrency, 5)


class TestCloudSessionHelpers(unittest.TestCase):
    def test_resolve_cloud_repository_prefers_explicit_values(self) -> None:
        cfg = SDKConfig(
            repo="fallback/repo",
            base_branch="main",
            cloud_session_repository_owner="explicit-owner",
            cloud_session_repository_name="explicit-repo",
            cloud_session_repository_branch="cloud-branch",
        )
        self.assertEqual(
            resolve_cloud_repository(cfg),
            ("explicit-owner", "explicit-repo", "cloud-branch"),
        )

    def test_resolve_cloud_repository_falls_back_to_repo_and_base_branch(self) -> None:
        cfg = SDKConfig(repo="owner/repo", base_branch="develop")
        self.assertEqual(resolve_cloud_repository(cfg), ("owner", "repo", "develop"))

    def test_resolve_cloud_repository_rejects_non_owner_repo_shape(self) -> None:
        cfg = SDKConfig(repo="owner/repo/extra", base_branch="main")
        self.assertEqual(resolve_cloud_repository(cfg), ("", "", "main"))

    def test_should_use_cloud_session_applies_step_then_subtask_override(self) -> None:
        cfg = SDKConfig(
            cloud_session_enabled=False,
            cloud_session_step_overrides={"1": True},
            cloud_session_subtask_overrides={"review": False},
        )
        self.assertTrue(should_use_cloud_session(cfg, step_id="1", subtask_kind="main"))
        self.assertFalse(should_use_cloud_session(cfg, step_id="1", subtask_kind="review"))

    def test_format_cloud_session_event_line_is_json_payload(self) -> None:
        line = format_cloud_session_event_line(
            step_id="1",
            subtask_kind="main",
            url="https://example.com/session",
        )
        prefix, payload_text = line.split(" ", 1)
        self.assertEqual(prefix, "[hve:cloud-session]")
        payload = json.loads(payload_text)
        self.assertEqual(payload["step_id"], "1")
        self.assertEqual(payload["subtask_kind"], "main")
        self.assertEqual(payload["url"], "https://example.com/session")

    def test_policy_blocked_detection_checks_attrs_and_message(self) -> None:
        exc_with_attr = RuntimeError("blocked")
        exc_with_attr.reason = "policy_blocked"  # type: ignore[attr-defined]
        self.assertTrue(is_policy_blocked_error(exc_with_attr))
        self.assertTrue(is_policy_blocked_error(RuntimeError("reason=policy_blocked")))
        self.assertFalse(is_policy_blocked_error(RuntimeError("network timeout")))

    def test_build_cloud_session_options_returns_none_when_sdk_lacks_cloud_types(self) -> None:
        cfg = SDKConfig(repo="owner/repo", cloud_session_enabled=True)
        fake_copilot = types.ModuleType("copilot")
        with unittest.mock.patch.dict(sys.modules, {"copilot": fake_copilot}):
            self.assertIsNone(build_cloud_session_options(cfg))

    def test_build_cloud_session_options_uses_sdk_cloud_types_when_available(self) -> None:
        # 実 SDK 全体ではなく、build_cloud_session_options が参照する最小 API
        # (CloudSessionOptions / CloudSessionRepository) だけを検証する fake。
        class FakeRepository:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeOptions:
            def __init__(self, *, repository):
                self.repository = repository

        fake_copilot = types.SimpleNamespace(
            CloudSessionOptions=FakeOptions,
            CloudSessionRepository=FakeRepository,
        )
        cfg = SDKConfig(repo="owner/repo", cloud_session_enabled=True)
        with unittest.mock.patch.dict(sys.modules, {"copilot": fake_copilot}):
            opts = build_cloud_session_options(cfg)
        self.assertIsInstance(opts, FakeOptions)
        self.assertEqual(opts.repository.kwargs, {"owner": "owner", "name": "repo", "branch": "main"})


class TestCloudSessionAutoRouting(unittest.TestCase):
    def test_single_task_wave_routes_local_by_default(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True)
        routing = apply_cloud_session_auto_routing(cfg, ["1"], workflow_id="wf", wave_index=1)
        self.assertEqual(routing, {"1": False})
        self.assertFalse(should_use_cloud_session(cfg, step_id="1", subtask_kind="main"))

    def test_parallel_wave_routes_balanced_cloud_and_local(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True, cloud_session_max_concurrency=5)
        routing = compute_cloud_session_routing(cfg, ["1", "2", "3", "4"], workflow_id="wf", wave_index=1)
        self.assertEqual(len(routing), 4)
        self.assertEqual(sum(1 for value in routing.values() if value), 2)
        self.assertGreaterEqual(sum(1 for value in routing.values() if not value), 1)

    def test_parallel_wave_respects_cloud_concurrency_and_local_minimum(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True, cloud_session_max_concurrency=1)
        routing = compute_cloud_session_routing(cfg, ["1", "2", "3", "4"], workflow_id="wf", wave_index=1)
        self.assertEqual(sum(1 for value in routing.values() if value), 1)
        self.assertGreaterEqual(sum(1 for value in routing.values() if not value), 1)

    def test_parallel_limit_one_routes_all_auto_steps_local(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True, cloud_session_max_concurrency=5)
        routing = compute_cloud_session_routing(
            cfg,
            ["1", "2", "3"],
            workflow_id="wf",
            wave_index=1,
            parallel_limit=1,
        )
        self.assertEqual(routing, {"1": False, "2": False, "3": False})

    def test_parallel_limit_batches_keep_at_least_one_local(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True, cloud_session_max_concurrency=5)
        step_ids = ["1", "2", "3", "4", "5", "6"]
        routing = compute_cloud_session_routing(
            cfg,
            step_ids,
            workflow_id="wf",
            wave_index=1,
            parallel_limit=2,
        )
        for batch_start in range(0, len(step_ids), 2):
            batch = step_ids[batch_start:batch_start + 2]
            self.assertTrue(any(not routing[step_id] for step_id in batch))
        self.assertEqual(sum(1 for value in routing.values() if value), 3)

    def test_cloud_concurrency_is_applied_per_effective_parallel_batch(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=True, cloud_session_max_concurrency=1)
        step_ids = ["1", "2", "3", "4"]
        routing = compute_cloud_session_routing(
            cfg,
            step_ids,
            workflow_id="wf",
            wave_index=1,
            parallel_limit=2,
        )
        for batch_start in range(0, len(step_ids), 2):
            batch = step_ids[batch_start:batch_start + 2]
            self.assertEqual(sum(1 for step_id in batch if routing[step_id]), 1)
        self.assertEqual(sum(1 for value in routing.values() if value), 2)

    def test_manual_step_override_wins_over_runtime_routing(self) -> None:
        cfg = SDKConfig(
            cloud_session_enabled=True,
            cloud_session_step_overrides={"1": True},
        )
        apply_cloud_session_auto_routing(cfg, ["1"], workflow_id="wf", wave_index=1)
        self.assertTrue(should_use_cloud_session(cfg, step_id="1", subtask_kind="main"))

    def test_disabled_cloud_session_does_not_auto_route(self) -> None:
        cfg = SDKConfig(cloud_session_enabled=False)
        routing = compute_cloud_session_routing(cfg, ["1", "2"], workflow_id="wf", wave_index=1)
        self.assertEqual(routing, {})


class TestCloudSessionLimiter(unittest.IsolatedAsyncioTestCase):
    async def test_limiter_tracks_active_count(self) -> None:
        limiter = CloudSessionLimiter(2)
        self.assertEqual(limiter.active_count, 0)
        async with limiter.acquire():
            self.assertEqual(limiter.active_count, 1)
        self.assertEqual(limiter.active_count, 0)

    async def test_limiter_clamps_invalid_concurrency(self) -> None:
        limiter = CloudSessionLimiter(0)
        self.assertEqual(limiter.max_concurrency, 1)

    async def test_limiter_release_attached_to_disconnect_runs_once(self) -> None:
        limiter = CloudSessionLimiter(2)
        await limiter.acquire_slot()

        class Session:
            async def disconnect(self) -> None:
                return None

        session = Session()
        attach_cloud_session_limiter_release(session, limiter)
        await session.disconnect()
        await session.disconnect()
        self.assertEqual(limiter.active_count, 0)


class TestCloudSessionEvents(unittest.TestCase):
    def test_extract_mission_control_url_from_remote_info_event(self) -> None:
        event = types.SimpleNamespace(
            type=types.SimpleNamespace(value="session.info"),
            data=types.SimpleNamespace(infoType="remote", url="https://mc.example/session"),
        )
        self.assertEqual(extract_mission_control_url(event), "https://mc.example/session")

    def test_extract_mission_control_url_ignores_non_remote_info(self) -> None:
        event = types.SimpleNamespace(
            type=types.SimpleNamespace(value="session.info"),
            data=types.SimpleNamespace(infoType="local", url="https://mc.example/session"),
        )
        self.assertEqual(extract_mission_control_url(event), "")


class _FakeEventSession:
    """on(handler) 呼び出し時に即座に事前設定イベントを配信するフェイクセッション。"""

    def __init__(self, event: object = None) -> None:
        self._event = event

    def on(self, handler):
        if self._event is not None:
            handler(self._event)
        return lambda: None


def _session_start_event(producer: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        type=types.SimpleNamespace(value="session.start"),
        data=types.SimpleNamespace(producer=producer),
    )


class TestWaitForCloudSessionReady(unittest.IsolatedAsyncioTestCase):
    """Cloud Session の初回送信レース対策（session.start producer==copilot-agent 待機）。"""

    async def test_resolves_when_copilot_agent_producer_starts(self) -> None:
        session = _FakeEventSession(_session_start_event("copilot-agent"))
        await wait_for_cloud_session_ready(session, timeout=1.0)

    async def test_times_out_on_other_producer(self) -> None:
        session = _FakeEventSession(_session_start_event("other-producer"))
        with self.assertRaises(TimeoutError):
            await wait_for_cloud_session_ready(session, timeout=0.05)

    async def test_times_out_when_no_event_fires(self) -> None:
        session = _FakeEventSession(None)
        with self.assertRaises(TimeoutError):
            await wait_for_cloud_session_ready(session, timeout=0.05)

    async def test_returns_immediately_when_session_has_no_on(self) -> None:
        # timeout は .on 欠如による早期 return 経路では参照されない（意図的に大きい値で明示）。
        await wait_for_cloud_session_ready("not-a-session", timeout=60.0)


class TestOrchestratorCloudSessionFallback(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_fallback_removes_cloud_injected_streaming_only(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def create_session(self, **kwargs):
                self.calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'cloud'")
                return "ok"

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build):
            result = await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertEqual(result, "ok")
        self.assertIn("cloud", client.calls[0])
        self.assertIn("streaming", client.calls[0])
        self.assertNotIn("cloud", client.calls[1])
        self.assertNotIn("streaming", client.calls[1])

    async def test_cloud_fallback_preserves_explicit_streaming(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def create_session(self, **kwargs):
                self.calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'cloud'")
                return "ok"

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build):
            await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto", "streaming": True},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertNotIn("cloud", client.calls[1])
        self.assertTrue(client.calls[1]["streaming"])

    async def test_cloud_and_reasoning_fallback_can_chain(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def create_session(self, **kwargs):
                self.calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'cloud'")
                if "reasoning_effort" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'reasoning_effort'")
                return "ok"

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build):
            result = await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto", "reasoning_effort": "high"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertEqual(result, "ok")
        self.assertEqual(len(client.calls), 3)
        self.assertIn("cloud", client.calls[0])
        self.assertIn("reasoning_effort", client.calls[1])
        self.assertNotIn("reasoning_effort", client.calls[2])

    async def test_cloud_session_waits_for_readiness_before_returning(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeSession:
            pass

        class FakeClient:
            async def create_session(self, **kwargs):
                return FakeSession()

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        waited_sessions: list[object] = []

        async def fake_wait(session, **_kwargs):
            waited_sessions.append(session)

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build), \
                unittest.mock.patch.object(orchestrator, "wait_for_cloud_session_ready", new=fake_wait):
            result = await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertEqual(len(waited_sessions), 1)
        self.assertIs(waited_sessions[0], result)

    async def test_cloud_session_readiness_timeout_falls_back_to_local(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def create_session(self, **kwargs):
                self.calls.append(dict(kwargs))
                return object()

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        async def fake_wait_timeout(session, **_kwargs):
            raise TimeoutError("readiness timeout")

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build), \
                unittest.mock.patch.object(orchestrator, "wait_for_cloud_session_ready", new=fake_wait_timeout):
            result = await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertIsNotNone(result)
        self.assertEqual(len(client.calls), 2)
        self.assertIn("cloud", client.calls[0])
        self.assertNotIn("cloud", client.calls[1])

    async def test_cloud_session_readiness_timeout_releases_limiter_slot(self) -> None:
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeSessionWithDisconnect:
            """disconnect() を持つセッション（release_slot が disconnect 経由でしか
            起きない現実的な形にするため、attach_cloud_session_limiter_release の
            即時解放フォールバックを意図的に迂回する）。"""

            async def disconnect(self) -> None:
                return None

        class FakeClient:
            async def create_session(self, **kwargs):
                return FakeSessionWithDisconnect()

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        async def fake_wait_timeout(session, **_kwargs):
            raise TimeoutError("readiness timeout")

        limiter = CloudSessionLimiter(1)

        async def fake_acquire(_config):
            await limiter.acquire_slot()
            return limiter

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build), \
                unittest.mock.patch.object(orchestrator, "wait_for_cloud_session_ready", new=fake_wait_timeout), \
                unittest.mock.patch.object(orchestrator, "acquire_cloud_session_slot", new=fake_acquire):
            await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertEqual(limiter.active_count, 0)

    async def test_cloud_session_readiness_wait_uses_default_timeout(self) -> None:
        """呼び出し元は timeout を明示せず、wait_for_cloud_session_ready の既定値（60秒）に委ねる。"""
        import orchestrator  # type: ignore

        class FakeCloud:
            pass

        class FakeSession:
            pass

        class FakeClient:
            async def create_session(self, **kwargs):
                return FakeSession()

        def fake_build(*_args, **_kwargs):
            return FakeCloud()

        calls: list[tuple[tuple, dict]] = []

        async def fake_wait(*args, **kwargs):
            calls.append((args, kwargs))

        client = FakeClient()
        with unittest.mock.patch.object(orchestrator, "build_cloud_session_options", new=fake_build), \
                unittest.mock.patch.object(orchestrator, "wait_for_cloud_session_ready", new=fake_wait):
            await orchestrator._create_session_with_auto_reasoning_fallback(
                client,
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="orchestrator",
                subtask_kind="orchestrator",
            )
        self.assertEqual(len(calls), 1)
        _args, kwargs = calls[0]
        self.assertNotIn("timeout", kwargs)


class TestSelfImproveCloudSessionPath(unittest.IsolatedAsyncioTestCase):
    async def test_discover_task_goal_injects_cloud_without_overriding_explicit_model(self) -> None:
        import self_improve  # type: ignore

        calls: list[dict] = []

        class FakeRepository:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeOptions:
            def __init__(self, *, repository):
                self.repository = repository

        class FakeSession:
            async def send_and_wait(self, *_args, **_kwargs):
                return '{"goal_description":"llm goal","success_criteria":["criterion"]}'

            async def disconnect(self):
                return None

        class FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                return FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.__dict__["CloudSessionOptions"] = FakeOptions
        fake_copilot.__dict__["CloudSessionRepository"] = FakeRepository
        fake_copilot_session = types.ModuleType("copilot.session")

        class PermissionHandler:
            approve_all = object()

        fake_copilot_session.__dict__["PermissionHandler"] = PermissionHandler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src.py").write_text("print('hello')", encoding="utf-8")
            static_result = {
                "task_goal": {
                    "goal_description": "static",
                    "success_criteria": ["static criterion"],
                    "reward_weights": {"goal": 1.0},
                    "tdd_phase": "green",
                },
                "sources": ["src.py"],
            }
            env = {
                "HVE_CLOUD_SESSION_ENABLED": "true",
                "REPO": "owner/repo",
                "MODEL": "env-model-should-not-win",
            }
            with unittest.mock.patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                    unittest.mock.patch.dict(os.environ, env, clear=False), \
                    unittest.mock.patch.object(self_improve, "discover_task_goal_from_docs", return_value=static_result), \
                    unittest.mock.patch("copilot_client_factory.create_copilot_client", return_value=FakeClient()):
                result = await self_improve.discover_task_goal_with_llm(
                    workflow_id="akm",
                    model="gpt-5.4",
                    repo_root=str(root),
                )

        self.assertEqual(result["task_goal"]["goal_description"], "llm goal")
        self.assertEqual(calls[0]["model"], "gpt-5.4")
        self.assertIn("cloud", calls[0])
        self.assertTrue(calls[0]["streaming"])

    async def test_discover_task_goal_cloud_fallback_preserves_explicit_streaming_false(self) -> None:
        import self_improve  # type: ignore

        calls: list[dict] = []

        class FakeRepository:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeOptions:
            def __init__(self, *, repository):
                self.repository = repository

        class FakeSession:
            async def send_and_wait(self, *_args, **_kwargs):
                return '{"goal_description":"llm goal","success_criteria":["criterion"]}'

            async def disconnect(self):
                return None

        class FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'cloud'")
                return FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.__dict__["CloudSessionOptions"] = FakeOptions
        fake_copilot.__dict__["CloudSessionRepository"] = FakeRepository
        fake_copilot_session = types.ModuleType("copilot.session")

        class PermissionHandler:
            approve_all = object()

        fake_copilot_session.__dict__["PermissionHandler"] = PermissionHandler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src.py").write_text("print('hello')", encoding="utf-8")
            static_result = {
                "task_goal": {
                    "goal_description": "static",
                    "success_criteria": ["static criterion"],
                    "reward_weights": {"goal": 1.0},
                    "tdd_phase": "green",
                },
                "sources": ["src.py"],
            }
            with unittest.mock.patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                    unittest.mock.patch.dict(os.environ, {"HVE_CLOUD_SESSION_ENABLED": "true", "REPO": "owner/repo"}, clear=False), \
                    unittest.mock.patch.object(self_improve, "discover_task_goal_from_docs", return_value=static_result), \
                    unittest.mock.patch("copilot_client_factory.create_copilot_client", return_value=FakeClient()):
                await self_improve.discover_task_goal_with_llm(
                    workflow_id="akm",
                    model="gpt-5.4",
                    repo_root=str(root),
                )

        self.assertIn("cloud", calls[0])
        self.assertNotIn("cloud", calls[1])
        self.assertFalse(calls[1]["streaming"])

    async def test_discover_task_goal_policy_blocked_is_not_static_fallback(self) -> None:
        import self_improve  # type: ignore

        class FakeRepository:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeOptions:
            def __init__(self, *, repository):
                self.repository = repository

        class FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                raise RuntimeError("policy_blocked")

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.__dict__["CloudSessionOptions"] = FakeOptions
        fake_copilot.__dict__["CloudSessionRepository"] = FakeRepository
        fake_copilot_session = types.ModuleType("copilot.session")

        class PermissionHandler:
            approve_all = object()

        fake_copilot_session.__dict__["PermissionHandler"] = PermissionHandler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src.py").write_text("print('hello')", encoding="utf-8")
            static_result = {
                "task_goal": {
                    "goal_description": "static",
                    "success_criteria": ["static criterion"],
                    "reward_weights": {"goal": 1.0},
                    "tdd_phase": "green",
                },
                "sources": ["src.py"],
            }
            with unittest.mock.patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                    unittest.mock.patch.dict(os.environ, {"HVE_CLOUD_SESSION_ENABLED": "true", "REPO": "owner/repo"}, clear=False), \
                    unittest.mock.patch.object(self_improve, "discover_task_goal_from_docs", return_value=static_result), \
                    unittest.mock.patch("copilot_client_factory.create_copilot_client", return_value=FakeClient()):
                with self.assertRaises(RuntimeError):
                    await self_improve.discover_task_goal_with_llm(
                        workflow_id="akm",
                        model="gpt-5.4",
                        repo_root=str(root),
                    )


if __name__ == "__main__":
    unittest.main()
