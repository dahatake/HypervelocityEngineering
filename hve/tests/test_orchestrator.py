"""test_orchestrator.py — run_workflow の dry_run テスト"""

from __future__ import annotations

import asyncio
import inspect
import io
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from orchestrator import run_workflow


def _run(coro):
    return asyncio.run(coro)


def _declared_required_params(workflow_id: str) -> dict:
    """FR-DAG-07 宣言に基づく必須パラメータをテスト用に埋める。

    FR-DAG-08 の pre-flight は DAG 実行前に不足を blocked とするため、
    宣言を持つ Workflow を扱うテストは必須値を提供する必要がある。
    既定値があるキーは宣言値を、ないキーはテスト用のプレースホルダを使う。
    """
    from workflow_registry import get_workflow

    wf = get_workflow(workflow_id)
    values: dict = {}
    if wf is None:
        return values
    for step in wf.steps:
        for key in getattr(step, "required_params", ()) or ():
            if key in values:
                continue
            declared_default = (getattr(step, "default_params", {}) or {}).get(key)
            values[key] = declared_default or f"test-{key.replace('_', '-')}"
    return values


class TestContextInjectionMetricsOutput(unittest.TestCase):
    def test_emit_context_injection_metrics_writes_stderr_and_summary(self) -> None:
        from orchestrator import _emit_context_injection_metrics

        console = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as td:
            summary_path = os.path.join(td, "step-summary.md")
            stderr_buffer = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}, clear=False), \
                    patch("sys.stderr", stderr_buffer):
                _emit_context_injection_metrics(
                    none_steps=1,
                    total_chars=240000,
                    max_chars=20000,
                    self_improve_scope="workflow",
                    phase_breakdown={"1": 120000, "2": 120000},
                    console=console,
                )

            stderr_output = stderr_buffer.getvalue()
            self.assertIn("context_injection", stderr_output)
            self.assertIn("phase_breakdown=1=120000, 2=120000", stderr_output)
            summary = Path(summary_path).read_text(encoding="utf-8")
            self.assertIn("## Wave2 Context Injection Metrics", summary)
            self.assertIn("- total_chars: 240000", summary)
            self.assertIn("- phase_breakdown: 1=120000, 2=120000", summary)

class TestPrefetchWorkIQ(unittest.TestCase):
    def test_returns_empty_when_copilot_sdk_missing(self) -> None:
        from orchestrator import _prefetch_workiq

        cfg = SDKConfig(dry_run=True)
        console = unittest.mock.Mock()
        with patch.dict(sys.modules, {"copilot": None}):
            result = _run(_prefetch_workiq(cfg, "query", console, timeout=1))
        self.assertEqual(result, "")
        console.warning.assert_called_once()

    def test_returns_query_result_when_successful(self) -> None:
        from orchestrator import _prefetch_workiq

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            async def disconnect(self):
                return None

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}), \
                patch("workiq.query_workiq", new=unittest.mock.AsyncMock(return_value="m365 context")):
            result = _run(_prefetch_workiq(cfg, "query", console, timeout=1))

        self.assertEqual(result, "m365 context")

    def test_returns_empty_when_workiq_mcp_not_connected(self) -> None:
        from orchestrator import _prefetch_workiq

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "disconnected"
                    error = "connection failed"

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            async def disconnect(self):
                return None

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}):
            result = _run(_prefetch_workiq(cfg, "query", console, timeout=1))

        self.assertEqual(result, "")
        console.warning.assert_called()

    def test_returns_empty_when_workiq_mcp_not_found(self) -> None:
        from orchestrator import _prefetch_workiq

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "other-server"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            async def disconnect(self):
                return None

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}):
            result = _run(_prefetch_workiq(cfg, "query", console, timeout=1))

        self.assertEqual(result, "")
        console.warning.assert_called()


class TestRunWorkflowDryRun(unittest.TestCase):
    """run_workflow の dry_run=True テスト。

    dry_run=True の場合、SDK 呼び出しをせずに実行計画を表示して終了する。
    """

    def _make_config(self, **kwargs) -> SDKConfig:
        cfg = SDKConfig(dry_run=True, quiet=True, **kwargs)
        return cfg

    def test_dry_run_returns_dict(self) -> None:
        """dry_run=True で dict が返ることを確認。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "steps": [], "selected_steps": []},
            config=cfg,
        ))
        self.assertIsInstance(result, dict)
        self.assertIn("workflow_id", result)
        self.assertEqual(result["workflow_id"], "aas")
        self.assertIn("dag_plan_waves", result)

    def test_dry_run_flag_in_result(self) -> None:
        """dry_run=True の場合、結果に dry_run フラグが含まれる。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertTrue(result.get("dry_run"))

    def test_dry_run_aad_web_workflow(self) -> None:
        """aad-web ワークフローの dry_run テスト。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="aad-web",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertEqual(result["workflow_id"], "aad-web")
        self.assertNotIn("error", result)

    def test_dry_run_invalid_workflow(self) -> None:
        """存在しないワークフロー ID の場合 error キーが返る。"""
        cfg = self._make_config()
        result = _run(run_workflow(
            workflow_id="nonexistent_workflow",
            params={},
            config=cfg,
        ))
        self.assertIn("error", result)

    def test_dry_run_does_not_call_sdk(self) -> None:
        """dry_run=True では SDK (CopilotClient) が呼ばれないことを確認。"""
        cfg = self._make_config()

        with patch.dict("sys.modules", {"copilot": None}):
            # copilot モジュールが無くても dry_run は正常に動作する
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))
        self.assertTrue(result.get("dry_run"))
        # failed がないことを確認
        self.assertEqual(result.get("failed", []), [])

    def test_dry_run_with_step_filter(self) -> None:
        """ステップフィルタ付き dry_run テスト。"""
        cfg = self._make_config()
        # AAS は Step.1 と Step.2 を持つ
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": ["1"]},
            config=cfg,
        ))
        self.assertEqual(result["workflow_id"], "aas")
        self.assertNotIn("error", result)

    def test_dry_run_all_valid_workflows(self) -> None:
        """全ての有効なワークフロー ID で dry_run が正常に動作することを確認。"""
        cfg = self._make_config()
        valid_ids = ["ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv", "aag", "aagd", "akm", "aqod", "adoc"]
        for wf_id in valid_ids:
            with self.subTest(workflow_id=wf_id):
                result = _run(run_workflow(
                    workflow_id=wf_id,
                    params={
                        "branch": "main",
                        "selected_steps": [],
                        **_declared_required_params(wf_id),
                    },
                    config=cfg,
                ))
                self.assertEqual(result["workflow_id"], wf_id, f"{wf_id} の workflow_id が不正")
                self.assertNotIn("error", result, f"{wf_id} でエラーが発生: {result.get('error')}")

    def test_workiq_prefetch_is_not_called_for_aqod_or_akm(self) -> None:
        """通常経路では AQOD/AKM ともに Work IQ 事前フェッチを実行しない。"""
        cfg = SDKConfig(dry_run=False, quiet=True, workiq_enabled=True)
        mock_prefetch = unittest.mock.AsyncMock()

        class FakeDAGExecutor:
            def __init__(self):
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {"completed": [], "failed": [], "skipped": []}

        with patch("orchestrator._prefetch_workiq_detailed", new=mock_prefetch), \
             patch("orchestrator._run_akm_workiq_verification", new=unittest.mock.AsyncMock()), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: FakeDAGExecutor()) as mock_dag_executor:
            _run(run_workflow(
                workflow_id="aqod",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

            _run(run_workflow(
                workflow_id="akm",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

            mock_prefetch.assert_not_awaited()
            self.assertEqual(mock_dag_executor.call_count, 2)
            self.assertEqual(mock_dag_executor.call_args_list[0].kwargs["workflow"].id, "aqod")
            self.assertEqual(mock_dag_executor.call_args_list[1].kwargs["workflow"].id, "akm")
            self.assertIsNotNone(mock_dag_executor.call_args_list[0].kwargs["dag_plan"])
            self.assertIsNotNone(mock_dag_executor.call_args_list[1].kwargs["dag_plan"])

    def test_fleet_mode_passes_wave_runner_to_dag_executor(self) -> None:
        """--fleet-mode 相当の設定時のみ DAGExecutor に fleet_wave_runner を渡す。"""
        captured_kwargs = []

        class FakeDAGExecutor:
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {}

        cfg = SDKConfig(dry_run=False, quiet=True, fleet_mode_enabled=True)
        with patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: FakeDAGExecutor(*a, **k)):
            _run(run_workflow(
                workflow_id="aqod",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertTrue(captured_kwargs)
        self.assertTrue(callable(captured_kwargs[0].get("fleet_wave_runner")))

    def test_fleet_mode_disabled_passes_no_wave_runner(self) -> None:
        captured_kwargs = []

        class FakeDAGExecutor:
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {}

        cfg = SDKConfig(dry_run=False, quiet=True, fleet_mode_enabled=False)
        with patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: FakeDAGExecutor(*a, **k)):
            _run(run_workflow(
                workflow_id="aqod",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertTrue(captured_kwargs)
        self.assertIsNone(captured_kwargs[0].get("fleet_wave_runner"))

    def test_fleet_wave_runner_passes_resolved_work_root_to_prompt_builder(self) -> None:
        captured_kwargs = []
        captured_build_kwargs = {}

        class FakeDAGExecutor:
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {}

        def fake_build_dag_wave_fleet_prompt(*args, **kwargs):
            captured_build_kwargs.update(kwargs)
            raise ValueError("stop after capture")

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        setattr(fake_copilot, "__path__", [])
        setattr(fake_copilot, "session", fake_copilot_session)

        class FakePermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        setattr(fake_copilot_session, "PermissionHandler", FakePermissionHandler)

        cfg = SDKConfig(dry_run=False, quiet=True, fleet_mode_enabled=True)
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work" / "runs" / "gui-run"
            with patch.dict(os.environ, {"HVE_WORK_ROOT": str(work_root)}, clear=False):
                with patch(
                    "orchestrator.DAGExecutor",
                    side_effect=lambda *a, **k: FakeDAGExecutor(*a, **k),
                ):
                    _run(run_workflow(
                        workflow_id="aqod",
                        params={"branch": "main", "selected_steps": []},
                        config=cfg,
                    ))

                wave_runner = captured_kwargs[0]["fleet_wave_runner"]
                fake_steps = [
                    types.SimpleNamespace(id="1/D01", title="D01", custom_agent=None),
                    types.SimpleNamespace(id="1/D02", title="D02", custom_agent=None),
                ]
                with patch.dict(
                    sys.modules,
                    {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
                    clear=False,
                ), patch(
                    "fleet_mode.build_dag_wave_fleet_prompt",
                    side_effect=fake_build_dag_wave_fleet_prompt,
                ):
                    result = _run(wave_runner(fake_steps, 1))

        self.assertIsNone(result)
        self.assertEqual(captured_build_kwargs["work_root"], work_root.resolve())

    def test_fleet_wave_runner_emits_completion_report_wait_heartbeat(self) -> None:
        captured_kwargs = []
        status_lines: list[str] = []

        class FakeDAGExecutor:
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {}

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        setattr(fake_copilot, "__path__", [])
        setattr(fake_copilot, "session", fake_copilot_session)

        class FakePermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        setattr(fake_copilot_session, "PermissionHandler", FakePermissionHandler)

        class FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

        class FakeSession:
            def on(self, _handler):
                return lambda: None

            async def disconnect(self):
                return None

        cfg = SDKConfig(dry_run=False, quiet=True, fleet_mode_enabled=True)
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work" / "runs" / "gui-run"
            with patch.dict(os.environ, {"HVE_WORK_ROOT": str(work_root)}, clear=False):
                with patch(
                    "orchestrator.DAGExecutor",
                    side_effect=lambda *a, **k: FakeDAGExecutor(*a, **k),
                ):
                    _run(run_workflow(
                        workflow_id="aqod",
                        params={"branch": "main", "selected_steps": []},
                        config=cfg,
                    ))

                wave_runner = captured_kwargs[0]["fleet_wave_runner"]
                captured_kwargs[0]["console"].status = status_lines.append
                fake_steps = [
                    types.SimpleNamespace(id="1/D01", title="D01", custom_agent=None),
                    types.SimpleNamespace(id="1/D02", title="D02", custom_agent=None),
                ]
                call_count = {"n": 0}

                def fake_check_subtask_completion(_work_root, _report_dir):
                    call_count["n"] += 1
                    if call_count["n"] <= 2:
                        return False, "missing"
                    return True, "OK"

                with patch.dict(
                    sys.modules,
                    {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
                    clear=False,
                ), patch(
                    "orchestrator._create_copilot_client_from_config",
                    return_value=FakeClient(),
                ), patch(
                    "orchestrator._create_session_with_auto_reasoning_fallback",
                    new=unittest.mock.AsyncMock(return_value=FakeSession()),
                ), patch(
                    "fleet_mode.start_fleet",
                    new=unittest.mock.AsyncMock(
                        return_value=types.SimpleNamespace(started=True, reason="")
                    ),
                ), patch(
                    "split_fork.check_subtask_completion",
                    side_effect=fake_check_subtask_completion,
                ), patch(
                    "orchestrator.asyncio.sleep",
                    new=unittest.mock.AsyncMock(),
                ):
                    result = _run(wave_runner(fake_steps, 1))

        self.assertEqual(set(result.keys()), {"1/D01", "1/D02"})
        self.assertTrue(
            any("Fleet 起動要求を送信します" in line for line in status_lines)
        )
        self.assertTrue(
            any("Fleet 起動完了" in line for line in status_lines)
        )
        self.assertTrue(
            any("completion-report 待機中" in line for line in status_lines)
        )

    def test_fleet_wave_runner_does_not_emit_start_complete_when_start_fails(self) -> None:
        captured_kwargs = []
        status_lines: list[str] = []

        class FakeDAGExecutor:
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                self.completed = set()
                self.failed = set()
                self.skipped = set()

            def compute_waves(self):
                return []

            async def execute(self):
                return {}

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        setattr(fake_copilot, "__path__", [])
        setattr(fake_copilot, "session", fake_copilot_session)

        class FakePermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        setattr(fake_copilot_session, "PermissionHandler", FakePermissionHandler)

        class FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

        class FakeSession:
            def on(self, _handler):
                return lambda: None

            async def disconnect(self):
                return None

        cfg = SDKConfig(dry_run=False, quiet=True, fleet_mode_enabled=True)
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work" / "runs" / "gui-run"
            with patch.dict(os.environ, {"HVE_WORK_ROOT": str(work_root)}, clear=False):
                with patch(
                    "orchestrator.DAGExecutor",
                    side_effect=lambda *a, **k: FakeDAGExecutor(*a, **k),
                ):
                    _run(run_workflow(
                        workflow_id="aqod",
                        params={"branch": "main", "selected_steps": []},
                        config=cfg,
                    ))

                wave_runner = captured_kwargs[0]["fleet_wave_runner"]
                captured_kwargs[0]["console"].status = status_lines.append
                fake_steps = [
                    types.SimpleNamespace(id="1/D01", title="D01", custom_agent=None),
                    types.SimpleNamespace(id="1/D02", title="D02", custom_agent=None),
                ]
                with patch.dict(
                    sys.modules,
                    {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
                    clear=False,
                ), patch(
                    "orchestrator._create_copilot_client_from_config",
                    return_value=FakeClient(),
                ), patch(
                    "orchestrator._create_session_with_auto_reasoning_fallback",
                    new=unittest.mock.AsyncMock(return_value=FakeSession()),
                ), patch(
                    "fleet_mode.start_fleet",
                    new=unittest.mock.AsyncMock(
                        return_value=types.SimpleNamespace(started=False, reason="nope")
                    ),
                ):
                    result = _run(wave_runner(fake_steps, 1))

        self.assertIsNone(result)
        self.assertTrue(
            any("Fleet 起動要求を送信します" in line for line in status_lines)
        )
        self.assertFalse(any("Fleet 起動完了" in line for line in status_lines))
        self.assertFalse(
            any("completion-report 待機中" in line for line in status_lines)
        )

    def test_dry_run_with_auto_coding_agent_review(self) -> None:
        """dry_run=True + auto_coding_agent_review=True で Code Review Agent が呼ばれないことを確認。"""
        cfg = self._make_config(auto_coding_agent_review=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run なので Code Review Agent 関連処理はスキップされ、通常の dry_run 結果が返る
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("failed", []), [])


class TestRunWorkflowFanout(unittest.TestCase):
    def test_aad_web_fanout_meta_is_forwarded_to_step_runner(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            mdq_watch=False,
            run_id="fanout-meta-forward-test",
        )
        calls: list[dict] = []

        class FakeStepRunner:
            def __init__(self, *args, **kwargs):
                pass

            def set_fork_index(self, *args, **kwargs):
                pass

            async def run_step(self, **kwargs):
                calls.append(kwargs)
                return True

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
            patch.dict(
                "catalog_parsers._PARSERS",
                {"service_catalog": lambda _repo_root: ["SVC-FANOUT-TEST"]},
                clear=False,
            ), \
            patch("orchestrator.StepRunner", FakeStepRunner):
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": ["1", "2.2"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), [])
        self.assertTrue(calls)
        # Step 1 is now per-APP fan-out (`1/APP-XX`); Step 2.2 is per-service fan-out
        # (`2.2/SVC-XX`). 旧来の base step (id == "1") は存在しなくなったため、
        # fanout_meta が両 fan-out で正しく伝播されることだけを検証する。
        step1_fanout_calls = [c for c in calls if str(c["step_id"]).startswith("1/")]
        step22_fanout_calls = [c for c in calls if str(c["step_id"]).startswith("2.2/")]
        base_only_calls = [c for c in calls if c["step_id"] == "1"]
        self.assertEqual(base_only_calls, [],
                         "Step 1 should no longer be invoked as a non-fanout base step")
        self.assertTrue(step1_fanout_calls,
                        "Step 1 should now invoke per-APP fanout children (1/APP-XX)")
        self.assertTrue(step22_fanout_calls)
        for call in step1_fanout_calls:
            fanout_meta = call.get("fanout_meta")
            if fanout_meta is None:
                self.fail("Step 1 fanout_meta is required")
            self.assertEqual(fanout_meta["base_step_id"], "1")
            self.assertEqual(fanout_meta["fanout_key"], call["step_id"].split("/", 1)[1])
        for call in step22_fanout_calls:
            fanout_meta = call.get("fanout_meta")
            if fanout_meta is None:
                self.fail("Step 2.2 fanout_meta is required")
            self.assertEqual(fanout_meta["base_step_id"], "2.2")
            self.assertEqual(fanout_meta["fanout_key"], call["step_id"].split("/", 1)[1])


class TestRunWorkflowAsdwDataDeployAppScope(unittest.TestCase):
    def test_asdw_data_deploy_runner_receives_single_canonical_app_scope(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            mdq_watch=False,
            run_id="asdw-data-deploy-app-scope-test",
        )
        runner_params: list[dict] = []

        class FakeStepRunner:
            def __init__(self, *args, **kwargs):
                runner_params.append(dict(kwargs["workflow_params"]))

            def set_fork_index(self, *args, **kwargs):
                pass

            async def run_step(self, **_kwargs):
                return True

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
            patch("orchestrator.StepRunner", FakeStepRunner):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={
                    "branch": "main",
                    "app_ids": ["APP-009"],
                    "app_id": "APP-009",
                    "selected_steps": ["1.3"],
                    **_declared_required_params("asdw-web"),
                    "resource_group": "test-resource-group",
                },
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), [])
        self.assertEqual(len(runner_params), 1)
        self.assertEqual(runner_params[0]["app_ids"], ["APP-009"])
        self.assertEqual(runner_params[0]["app_id"], "APP-009")


class TestRunWorkflowConfig(unittest.TestCase):
    """config パラメータの伝播テスト。"""

    def test_default_config_used_when_none(self) -> None:
        """config=None の場合、デフォルト SDKConfig が使われることを確認。"""
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": [], "dry_run": True},
            config=SDKConfig(dry_run=True, quiet=True),
        ))
        self.assertIsInstance(result, dict)

    def test_create_issues_false_by_default(self) -> None:
        """create_issues=False のデフォルト値テスト（Issue が作成されないことを確認）。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=False)
        # root_issue_num が None のはず
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run なので failed は空
        self.assertEqual(result.get("failed", []), [])


class TestRunWorkflowMetaDependencies(unittest.TestCase):
    """run_workflow のメタワークフロー前提チェック。"""

    class _FakeDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = set()
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {"completed": [], "failed": [], "skipped": []}

    def _fake_arch_filter_result(self):
        """テスト用のダミー AppArchFilterResult を返す。"""
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id="aad-web",
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=None,
            matched_app_ids=["APP-01"],
        )

    def test_hard_dependency_missing_returns_error(self) -> None:
        from hve.workflow_registry import WorkflowDependency

        cfg = SDKConfig(dry_run=False, quiet=True)
        missing_path = os.path.join(tempfile.gettempdir(), "__hve_missing_artifact__")
        deps = [WorkflowDependency(workflow_id="aas", required_artifacts=[missing_path], soft=False)]

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=deps), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._fake_arch_filter_result()), \
             patch("orchestrator.DAGExecutor") as mock_dag_executor:
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertIn("error", result)
        self.assertIn("__hve_missing_artifact__", result["error"])
        self.assertEqual(result["completed"], [])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["skipped"], [])
        mock_dag_executor.assert_not_called()

    def test_soft_dependency_missing_continues(self) -> None:
        from hve.workflow_registry import WorkflowDependency

        cfg = SDKConfig(dry_run=False, quiet=True)
        missing_path = os.path.join(tempfile.gettempdir(), "__hve_soft_missing_artifact__")
        deps = [WorkflowDependency(workflow_id="aas", required_artifacts=[missing_path], soft=True)]

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=deps), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._fake_arch_filter_result()), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()) as mock_dag_executor:
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        mock_dag_executor.assert_called_once()

    def test_hard_dependency_present_continues(self) -> None:
        from hve.workflow_registry import WorkflowDependency

        cfg = SDKConfig(dry_run=False, quiet=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = os.path.join(tmpdir, "hve-meta-dep-present-artifact.txt")
            with open(artifact_path, "w", encoding="utf-8") as f:
                f.write("ok")
            deps = [WorkflowDependency(workflow_id="aas", required_artifacts=[artifact_path], soft=False)]

            with patch("hve.workflow_registry.get_meta_dependencies", return_value=deps), \
                 patch("orchestrator.resolve_app_arch_scope", return_value=self._fake_arch_filter_result()), \
                 patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()) as mock_dag_executor:
                result = _run(run_workflow(
                    workflow_id="aad-web",
                    params={"branch": "main", "selected_steps": []},
                    config=cfg,
                ))

        self.assertIsNone(result.get("error"))
        mock_dag_executor.assert_called_once()


class TestAdditionalPrompt(unittest.TestCase):
    """additional_prompt の動作テスト。"""

    def _build_mock_step(self, step_id: str = "1", title: str = "Test Step"):
        """テスト用のステップモックを生成する。"""
        from unittest.mock import MagicMock
        step = MagicMock()
        step.id = step_id
        step.title = title
        step.body_template_path = None  # フォールバックプロンプトを使用
        step.depends_on = []
        step.is_container = False
        return step

    def _build_mock_wf(self, step_id: str = "1"):
        """テスト用のワークフローモックを生成する。"""
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "aas"
        return wf

    def test_T1_additional_prompt_none_no_change(self) -> None:
        """T1: additional_prompt=None の場合、プロンプトに変更がないことを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result_with_none = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt=None,
        )
        result_no_arg = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
        )
        # additional_prompt=None と引数省略は同じ結果であること
        self.assertEqual(result_with_none, result_no_arg)
        # "追加指示" という文字列が含まれていないことを確認
        self.assertNotIn("追加指示", result_with_none)

    def test_T2_additional_prompt_appended_to_prompt(self) -> None:
        """T2: additional_prompt が指定された場合、プロンプト末尾に追記されることを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt="追加指示",
        )
        self.assertTrue(result.endswith("\n\n追加指示"))

    def test_T2_additional_prompt_appended_to_template_prompt(self) -> None:
        """T2: テンプレートプロンプトにも additional_prompt が追記されることを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        step.body_template_path = "dummy_template.md"
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "テンプレートプロンプト",
            wf=wf,
            additional_prompt="追加指示",
        )
        # 言語ルール（_LANGUAGE_DIRECTIVE_JA）が冒頭に注入された上で末尾が追加指示で終わる
        self.assertTrue(result.endswith("テンプレートプロンプト\n\n追加指示"))

    def test_template_prompt_passes_execution_mode(self) -> None:
        from orchestrator import _build_step_prompt

        step = self._build_mock_step()
        step.body_template_path = "dummy_template.md"
        wf = self._build_mock_wf()
        params = {"branch": "main"}
        captured = {}

        def _fake_render_template(**kwargs):
            captured.update(kwargs)
            return "テンプレートプロンプト"

        _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=_fake_render_template,
            wf=wf,
            execution_mode="github",
        )
        self.assertEqual(captured.get("execution_mode"), "github")

    def test_T3_issue_title_none_dry_run_no_error(self) -> None:
        """T3: issue_title=None かつ dry_run=True の場合でもエラーにならないことを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=True)
        # dry_run=True なので Issue 作成はスキップされるが、エラーにならないことを確認する
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run では issue_title のパスを通らないが、結果として dict が返ることを確認
        self.assertIsInstance(result, dict)

    def test_T4_issue_title_propagated_to_params(self) -> None:
        """T4: issue_title がパラメータに伝搬されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        from unittest.mock import MagicMock

        wf = MagicMock()
        wf.id = "aas"

        cli_args = {
            "branch": "main",
            "steps": [],
            "auto_contents_review": False,
            "auto_qa": False,
            "issue_title": "カスタムタイトル",
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params.get("issue_title"), "カスタムタイトル")

    def test_T4_issue_title_not_in_params_when_none(self) -> None:
        """T4: issue_title が未指定の場合、params に含まれないことを確認。"""
        from orchestrator import _collect_params_non_interactive
        from unittest.mock import MagicMock

        wf = MagicMock()
        wf.id = "aas"

        cli_args = {
            "branch": "main",
            "steps": [],
            "auto_contents_review": False,
            "auto_qa": False,
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertNotIn("issue_title", params)

    # NOTE: test_T5_additional_prompt_appended_to_custom_agent was removed in Phase 8 S-2.
    # Custom Agent 廃止後、SDK へ `custom_agents` キーを渡す経路が削除されたため、
    # custom_agents_config フィールドおよび当該テストは廃止された。

    def test_T6_additional_prompt_empty_string_no_append(self) -> None:
        """T6: additional_prompt が空文字の場合、追記されないことを確認。"""
        from orchestrator import _build_step_prompt
        step = self._build_mock_step()
        wf = self._build_mock_wf()
        params = {"branch": "main"}

        result_none = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt=None,
        )
        result_empty = _build_step_prompt(
            step=step,
            params=params,
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=wf,
            additional_prompt="",
        )
        # 空文字と None は同じ結果（追記なし）
        self.assertEqual(result_none, result_empty)

    # ------------------------------------------------------------------
    # NOTE: P-B の subissues.md フォーマット最小例インライン注入テスト
    # (test_PB_subissues_hint_*) は FR-CLI-70 により廃止された。
    # 後継は TestBuildStepPromptContract::test_FR_CLI_70_* を参照。
    # ------------------------------------------------------------------


class TestBuildStepPromptContract(unittest.TestCase):
    """`_build_step_prompt` の規範契約テスト（FR-CLI-70 / FR-CLI-71）。"""

    def _build_mock_step(
        self,
        step_id: str = "1",
        title: str = "Test Step",
        body_template_path=None,
        custom_agent: str = "Arch-TDD-TestSpec",
        is_container: bool = False,
    ):
        from unittest.mock import MagicMock
        step = MagicMock()
        step.id = step_id
        step.title = title
        step.body_template_path = body_template_path
        step.depends_on = []
        step.is_container = is_container
        step.custom_agent = custom_agent
        return step

    def _build_mock_wf(self):
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "aas"
        return wf

    # ------------------------------------------------------------------
    # FR-CLI-70: subissues.md フォーマット例を Step プロンプトへ注入しない
    # ------------------------------------------------------------------

    def test_FR_CLI_70_template_prompt_has_no_subissues_format_hint(self) -> None:
        """FR-CLI-70: CLI / GUI 実行経路が組み立てる Step プロンプトに
        `subissues.md` のフォーマット例を注入してはならない（template 経路）。

        CLI / GUI Orchestrator 配下では workflow DAG / fan-out で分割を表現し、
        `subissues.md` runtime fork は legacy / 明示 opt-in であるため、
        常時注入は誤った作業指示になる。分割手順の参照が必要な場合は
        Skill `task-dag-planning` に委ねる。
        """
        from orchestrator import _build_step_prompt

        step = self._build_mock_step(body_template_path="dummy_template.md")
        result = _build_step_prompt(
            step=step,
            params={"branch": "main"},
            root_issue_num=None,
            render_template_fn=lambda **kw: "テンプレート本文",
            wf=self._build_mock_wf(),
            additional_prompt="追加指示",
        )
        self.assertNotIn("<!-- subissue -->", result)
        self.assertNotIn("subissues.md", result)
        self.assertNotIn("Markdown テーブル形式は禁止", result)
        # additional_prompt が末尾に付与される既存挙動は維持する
        self.assertTrue(result.endswith("テンプレート本文\n\n追加指示"))

    def test_FR_CLI_70_fallback_prompt_has_no_subissues_format_hint(self) -> None:
        """FR-CLI-70: `body_template_path` 未宣言 Step の簡易プロンプトにも
        `subissues.md` のフォーマット例を注入してはならない。"""
        from orchestrator import _build_step_prompt

        step = self._build_mock_step(body_template_path=None)
        result = _build_step_prompt(
            step=step,
            params={"branch": "main"},
            root_issue_num=None,
            render_template_fn=lambda **kw: "",
            wf=self._build_mock_wf(),
            additional_prompt=None,
        )
        self.assertNotIn("<!-- subissue -->", result)
        self.assertNotIn("subissues.md", result)

    def test_FR_CLI_70_no_subissues_hint_symbols_in_orchestrator(self) -> None:
        """FR-CLI-70: 注入用のデッドコード（定数 / ヘルパー）を残さない。"""
        import orchestrator

        self.assertFalse(hasattr(orchestrator, "_SUBISSUES_FORMAT_HINT"))
        self.assertFalse(hasattr(orchestrator, "_subissues_format_hint_for_step"))

    # ------------------------------------------------------------------
    # FR-CLI-71: template render 失敗時は fail-fast（簡易プロンプトへ落ちない）
    # ------------------------------------------------------------------

    def test_FR_CLI_71_template_render_exception_propagates(self) -> None:
        """FR-CLI-71: `body_template_path` 宣言済み Step でレンダリングが例外を
        送出した場合、簡易プロンプトへフォールバックせず例外を上位へ伝播する。

        壊れた縮退プロンプトで Agent セッションを開始してはならない。
        既存の例外型はそのまま伝播させる（ラップしない）。
        """
        from orchestrator import _build_step_prompt

        step = self._build_mock_step(body_template_path="broken_template.md")

        def _raise(**kw):
            raise RuntimeError("template boom")

        with self.assertRaises(RuntimeError) as ctx:
            _build_step_prompt(
                step=step,
                params={"branch": "main"},
                root_issue_num=None,
                render_template_fn=_raise,
                wf=self._build_mock_wf(),
                additional_prompt="追加指示",
            )
        self.assertEqual(str(ctx.exception), "template boom")

    def test_FR_CLI_71_template_render_empty_is_failure(self) -> None:
        """FR-CLI-71: `body_template_path` 宣言済み Step でレンダリング結果が
        空文字列 / None の場合も「レンダリング失敗」とみなし fail-fast する。

        `render_template` はテンプレートファイルが存在しない / 空の場合に
        空文字列を返すため、これを簡易プロンプトで代替すると壊れた縮退
        プロンプトになる。エラーメッセージにはテンプレートパスを含める。
        """
        from orchestrator import _build_step_prompt

        for _rendered in ("", None):
            with self.subTest(rendered=_rendered):
                step = self._build_mock_step(body_template_path="empty_template.md")
                with self.assertRaises(ValueError) as ctx:
                    _build_step_prompt(
                        step=step,
                        params={"branch": "main"},
                        root_issue_num=None,
                        render_template_fn=lambda **kw: _rendered,
                        wf=self._build_mock_wf(),
                    )
                self.assertIn("empty_template.md", str(ctx.exception))

    def test_FR_CLI_71_step_without_template_path_uses_fallback_prompt(self) -> None:
        """FR-CLI-71: `body_template_path` が宣言されていない Step が簡易プロンプトを
        使う挙動は本要件の対象外であり、従来どおり許容する。"""
        from orchestrator import _build_step_prompt

        step = self._build_mock_step(step_id="7", title="No Template", body_template_path=None)

        def _must_not_be_called(**kw):  # pragma: no cover - 呼ばれないことの明示
            raise AssertionError("render_template_fn should not be called")

        result = _build_step_prompt(
            step=step,
            params={"branch": "main", "resource_group": "rg-test"},
            root_issue_num=None,
            render_template_fn=_must_not_be_called,
            wf=self._build_mock_wf(),
            additional_prompt="追加指示",
        )
        self.assertIn("# Step.7: No Template", result)
        self.assertIn("対象ブランチ: `main`", result)
        self.assertIn("リソースグループ: `rg-test`", result)
        self.assertTrue(result.endswith("\n\n追加指示"))


class TestCopilotUsernames(unittest.TestCase):
    """`_COPILOT_USERNAMES` の内容テスト。"""

    def test_contains_pull_request_reviewer_bot(self) -> None:
        """`copilot-pull-request-reviewer[bot]` が含まれていることを確認。"""
        from orchestrator import _COPILOT_USERNAMES
        self.assertIn("copilot-pull-request-reviewer[bot]", _COPILOT_USERNAMES)

    def test_contains_existing_names(self) -> None:
        """既存のユーザー名候補が引き続き含まれていることを確認。"""
        from orchestrator import _COPILOT_USERNAMES
        for name in ("copilot", "github-copilot[bot]", "copilot[bot]", "copilot-swe-agent[bot]"):
            with self.subTest(name=name):
                self.assertIn(name, _COPILOT_USERNAMES)


class TestGetGitDiff(unittest.TestCase):
    """`_get_git_diff()` のテスト。"""

    def _make_console(self):
        from console import Console
        return Console(quiet=True)

    def test_returns_empty_string_when_no_diff(self) -> None:
        """差分なしの場合に空文字を返すことを確認。"""
        from orchestrator import _get_git_diff
        console = self._make_console()

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff("HEAD~1", console)

        self.assertEqual(result, "")

    def test_returns_diff_text(self) -> None:
        """差分がある場合に差分テキストを返すことを確認。"""
        from orchestrator import _get_git_diff
        console = self._make_console()

        diff_text = "diff --git a/foo.py b/foo.py\n+new line"
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = diff_text
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff("HEAD~1", console)

        self.assertEqual(result, diff_text)

    def test_trims_diff_at_80000_chars(self) -> None:
        """差分が 80,000 文字超の場合にトリミングすることを確認。"""
        from orchestrator import _get_git_diff, _MAX_DIFF_CHARS
        console = self._make_console()

        long_diff = "x" * 90_000
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = long_diff
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff("HEAD~1", console)

        _truncation_suffix = "\n... (truncated)"
        self.assertEqual(len(result), _MAX_DIFF_CHARS + len(_truncation_suffix))
        self.assertTrue(result.endswith("... (truncated)"))

    def test_returns_empty_on_nonzero_returncode(self) -> None:
        """git diff が失敗した場合に空文字を返すことを確認。"""
        from orchestrator import _get_git_diff
        console = self._make_console()

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: bad revision"

        with patch("subprocess.run", return_value=mock_result):
            result = _get_git_diff("HEAD~1", console)

        self.assertEqual(result, "")

    def test_returns_empty_on_timeout(self) -> None:
        """git diff がタイムアウトした場合に空文字を返すことを確認。"""
        from orchestrator import _get_git_diff
        import subprocess
        console = self._make_console()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            result = _get_git_diff("HEAD~1", console)

        self.assertEqual(result, "")

    def test_returns_empty_when_git_not_found(self) -> None:
        """git コマンドが見つからない場合に空文字を返すことを確認。"""
        from orchestrator import _get_git_diff
        console = self._make_console()

        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = _get_git_diff("HEAD~1", console)

        self.assertEqual(result, "")


class TestDeleteLocalMergedBranch(unittest.TestCase):
    """FR-CLI-34: マージ検知によるローカル作業ブランチ削除のテスト。"""

    def _make_console(self):
        from console import Console
        return Console(quiet=True)

    def _cfg(self, **kw) -> SDKConfig:
        return SDKConfig(repo="o/r", github_token="tok", base_branch="main", quiet=True, **kw)

    # --- _git_delete_local_branch ---
    def test_delete_checkout_then_branch_d(self) -> None:
        """base へ checkout 後に git branch -D で削除する。"""
        from orchestrator import _git_delete_local_branch
        console = self._make_console()
        ok = unittest.mock.MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", side_effect=[ok, ok]) as mrun:
            result = _git_delete_local_branch("work-br", "main", console)
        self.assertTrue(result)
        self.assertEqual(mrun.call_count, 2)
        self.assertEqual(mrun.call_args_list[0][0][0], ["git", "checkout", "main"])
        self.assertEqual(mrun.call_args_list[1][0][0], ["git", "branch", "-D", "work-br"])

    def test_delete_checkout_fail_skips_delete(self) -> None:
        """checkout 失敗時はブランチ削除（branch -D）を実行しない。"""
        from orchestrator import _git_delete_local_branch
        console = self._make_console()
        fail = unittest.mock.MagicMock(returncode=1, stdout="", stderr="err")
        with patch("subprocess.run", side_effect=[fail]) as mrun:
            result = _git_delete_local_branch("work-br", "main", console)
        self.assertFalse(result)
        self.assertEqual(mrun.call_count, 1)

    # --- _wait_pr_merged_and_delete_local_branch ---
    def test_merged_triggers_delete(self) -> None:
        """PR が merged のとき作業ブランチを削除する。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": True, "state": "closed", "merge_commit_sha": "abc123"}), \
                patch("orchestrator._wait_check_runs_success", return_value=True), \
                patch("orchestrator._git_delete_local_branch", return_value=True) as mdel:
            result = _wait_pr_merged_and_delete_local_branch(7, "work-br", self._cfg(), console, poll_interval=0, timeout=10)
        self.assertTrue(result)
        mdel.assert_called_once_with("work-br", "main", console)

    def test_merged_failed_checks_no_delete(self) -> None:
        """PR が merged でも merge commit の check-run 失敗時は削除しない。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": True, "state": "closed", "merge_commit_sha": "abc123"}), \
                patch("orchestrator._wait_check_runs_success", return_value=False), \
                patch("orchestrator._git_delete_local_branch") as mdel:
            result = _wait_pr_merged_and_delete_local_branch(7, "work-br", self._cfg(), console, poll_interval=0, timeout=10)
        self.assertFalse(result)
        mdel.assert_not_called()

    def test_wait_check_runs_success_completed(self) -> None:
        """merge commit の check-runs が全て成功系なら True。"""
        from orchestrator import _wait_check_runs_success
        console = self._make_console()
        with patch("orchestrator.list_check_runs_for_ref", return_value=[
            {"name": "build", "status": "completed", "conclusion": "success"},
            {"name": "lint", "status": "completed", "conclusion": "skipped"},
        ]):
            self.assertTrue(_wait_check_runs_success("abc123", self._cfg(), console, poll_interval=0, timeout=10))

    def test_wait_check_runs_failure_returns_false(self) -> None:
        """失敗系 conclusion があれば False。"""
        from orchestrator import _wait_check_runs_success
        console = self._make_console()
        with patch("orchestrator.list_check_runs_for_ref", return_value=[
            {"name": "deploy", "status": "completed", "conclusion": "failure"},
        ]):
            self.assertFalse(_wait_check_runs_success("abc123", self._cfg(), console, poll_interval=0, timeout=10))

    def test_wait_check_runs_empty_returns_false(self) -> None:
        """check-run が 0 件なら検証不能として False。"""
        from orchestrator import _wait_check_runs_success
        console = self._make_console()
        with patch("orchestrator.list_check_runs_for_ref", return_value=[]):
            self.assertFalse(_wait_check_runs_success("abc123", self._cfg(), console, poll_interval=0, timeout=10))

    def test_wait_pr_merged_can_skip_check_run_requirement(self) -> None:
        """Step 単位 CI/CD では merge 後 check-run 確認を呼ばず merged を成功扱いできる。"""
        from orchestrator import _wait_pr_merged
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": True, "state": "closed", "merge_commit_sha": "abc123"}), \
                patch("orchestrator._wait_check_runs_success", return_value=False) as mchecks:
            result = _wait_pr_merged(
                7,
                self._cfg(),
                console,
                poll_interval=0,
                timeout=10,
                require_check_runs=False,
            )
        self.assertTrue(result)
        mchecks.assert_not_called()

    def test_wait_pr_merged_requires_check_runs_by_default(self) -> None:
        """通常経路は従来どおり merge commit の check-run 未確認なら False。"""
        from orchestrator import _wait_pr_merged
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": True, "state": "closed", "merge_commit_sha": "abc123"}), \
                patch("orchestrator._wait_check_runs_success", return_value=False) as mchecks:
            result = _wait_pr_merged(
                7,
                self._cfg(),
                console,
                poll_interval=0,
                timeout=10,
            )
        self.assertFalse(result)
        mchecks.assert_called_once()

    def test_wait_pr_merged_stops_on_auto_approve_deploy_gate_block(self) -> None:
        """auto-approve の Deploy/AC gate 停止コメントを検出したら timeout まで待たない。"""
        from orchestrator import _wait_pr_merged
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": False, "state": "open"}), \
                patch("orchestrator.list_issue_comments", return_value=[{"body": "<!-- auto-approve-deploy-gate-blocked -->"}]) as mcomments, \
                patch("orchestrator.time.sleep") as msleep:
            result = _wait_pr_merged(
                7,
                self._cfg(),
                console,
                poll_interval=15,
                timeout=600,
                require_check_runs=False,
            )

        self.assertFalse(result)
        mcomments.assert_called_once()
        msleep.assert_not_called()

    def test_wait_pr_merged_comment_api_error_keeps_existing_timeout_path(self) -> None:
        """コメント取得失敗は fail-fast 条件にせず、従来の timeout path にフォールバックする。"""
        from orchestrator import _wait_pr_merged
        from hve.github_api import GitHubAPIError

        console = self._make_console()
        with patch("orchestrator.time.monotonic", side_effect=[0, 0, 11]), \
                patch("orchestrator.get_pull_request", return_value={"merged": False, "state": "open"}), \
                patch("orchestrator.list_issue_comments", side_effect=GitHubAPIError("boom", 500)) as mcomments, \
                patch("orchestrator.time.sleep") as msleep:
            result = _wait_pr_merged(
                7,
                self._cfg(),
                console,
                poll_interval=0,
                timeout=10,
                require_check_runs=False,
            )

        self.assertFalse(result)
        mcomments.assert_called_once()
        msleep.assert_called_once_with(0)

    def test_unmerged_closed_no_delete(self) -> None:
        """PR が closed かつ未マージのとき削除しない。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": False, "state": "closed"}), \
                patch("orchestrator._git_delete_local_branch") as mdel:
            _wait_pr_merged_and_delete_local_branch(7, "work-br", self._cfg(), console, poll_interval=0, timeout=10)
        mdel.assert_not_called()

    def test_timeout_no_delete(self) -> None:
        """タイムアウト時は削除しない。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        console = self._make_console()
        with patch("orchestrator.get_pull_request", return_value={"merged": False, "state": "open"}), \
                patch("orchestrator._git_delete_local_branch") as mdel:
            _wait_pr_merged_and_delete_local_branch(7, "work-br", self._cfg(), console, poll_interval=0, timeout=0)
        mdel.assert_not_called()

    def test_api_error_no_delete(self) -> None:
        """PR 状態取得失敗時は削除しない。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        from hve.github_api import GitHubAPIError
        console = self._make_console()
        with patch("orchestrator.get_pull_request", side_effect=GitHubAPIError("boom", 500)), \
                patch("orchestrator._git_delete_local_branch") as mdel:
            _wait_pr_merged_and_delete_local_branch(7, "work-br", self._cfg(), console, poll_interval=0, timeout=10)
        mdel.assert_not_called()

    def test_skips_when_repo_missing(self) -> None:
        """repo 未設定時はポーリングせずスキップする。"""
        from orchestrator import _wait_pr_merged_and_delete_local_branch
        console = self._make_console()
        with patch("orchestrator.get_pull_request") as mget, \
                patch("orchestrator._git_delete_local_branch") as mdel:
            _wait_pr_merged_and_delete_local_branch(
                7, "work-br",
                SDKConfig(repo="", github_token="", base_branch="main", quiet=True),
                console, poll_interval=0, timeout=10,
            )
        mget.assert_not_called()
        mdel.assert_not_called()


class TestRequestCodeReviewSDK(unittest.TestCase):
    """`_request_code_review()` の新 SDK ローカル実行テスト。"""

    def _make_config(self, **kwargs) -> SDKConfig:
        cfg = SDKConfig(quiet=True, **kwargs)
        return cfg

    def test_skips_when_no_diff(self) -> None:
        """差分なしの場合に None を返してスキップすることを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        self.assertIsNone(result)

    def test_returns_error_on_import_error(self) -> None:
        """SDK が未インストールの場合にエラーメッセージを返すことを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/foo.py b/foo.py\n+new line"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result), \
             patch.dict("sys.modules", {"copilot": None}):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        self.assertIsInstance(result, str)
        self.assertIn("GitHub Copilot SDK", result)

    def test_no_fix_when_pass(self) -> None:
        """PASS 判定時は修正プロンプトを送信しないことを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/foo.py b/foo.py\n+new line"
        mock_result.stderr = ""

        # PASS レビュー応答（合格判定: ✅ PASS）
        pass_response = unittest.mock.MagicMock()
        pass_data = unittest.mock.MagicMock()
        pass_data.content = "### サマリー\n- Critical: 0件\n- 合格判定: ✅ PASS"
        pass_response.data = pass_data

        mock_session = unittest.mock.AsyncMock()
        mock_session.on = unittest.mock.MagicMock()
        mock_session.send_and_wait = unittest.mock.AsyncMock(return_value=pass_response)

        mock_client = unittest.mock.AsyncMock()
        mock_client.create_session = unittest.mock.AsyncMock(return_value=mock_session)

        mock_copilot = unittest.mock.MagicMock()
        mock_copilot.CopilotClient.return_value = mock_client
        mock_copilot.PermissionHandler = unittest.mock.MagicMock()
        mock_copilot.SubprocessConfig = unittest.mock.MagicMock()
        mock_copilot.ExternalServerConfig = unittest.mock.MagicMock()

        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = mock_copilot.PermissionHandler

        with patch("subprocess.run", return_value=mock_result), \
             patch.dict("sys.modules", {"copilot": mock_copilot, "copilot.session": fake_copilot_session}):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        self.assertIsNone(result)
        # PASS なので send_and_wait は 1 回だけ（レビュー用のみ）
        self.assertEqual(mock_session.send_and_wait.call_count, 1)

    def test_auto_approval_sends_fix_prompt_on_fail(self) -> None:
        """FAIL + auto_approval=True の場合、修正プロンプトを自動送信することを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config(auto_coding_agent_review_auto_approval=True)
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/foo.py b/foo.py\n+new line"
        mock_result.stderr = ""

        # FAIL レビュー応答
        fail_response = unittest.mock.MagicMock()
        fail_data = unittest.mock.MagicMock()
        fail_data.content = "### サマリー\n- Critical: 1件\n- 合格判定: ❌ FAIL"
        fail_response.data = fail_data

        fix_response = unittest.mock.MagicMock()
        fix_data = unittest.mock.MagicMock()
        fix_data.content = "修正しました。"
        fix_response.data = fix_data

        mock_session = unittest.mock.AsyncMock()
        mock_session.on = unittest.mock.MagicMock()
        mock_session.send_and_wait = unittest.mock.AsyncMock(
            side_effect=[fail_response, fix_response]
        )

        mock_client = unittest.mock.AsyncMock()
        mock_client.create_session = unittest.mock.AsyncMock(return_value=mock_session)

        mock_copilot = unittest.mock.MagicMock()
        mock_copilot.CopilotClient.return_value = mock_client
        mock_copilot.PermissionHandler = unittest.mock.MagicMock()
        mock_copilot.SubprocessConfig = unittest.mock.MagicMock()
        mock_copilot.ExternalServerConfig = unittest.mock.MagicMock()

        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = mock_copilot.PermissionHandler

        with patch("subprocess.run", return_value=mock_result), \
             patch.dict("sys.modules", {"copilot": mock_copilot, "copilot.session": fake_copilot_session}):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        self.assertIsNone(result)
        # FAIL なので send_and_wait は 2 回（レビュー + 修正）
        self.assertEqual(mock_session.send_and_wait.call_count, 2)

    def test_works_without_gh_token_and_repo(self) -> None:
        """GH_TOKEN / repo が未設定でも正常動作することを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        # GH_TOKEN も repo も未設定
        config = self._make_config(github_token="", repo="")
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""  # 差分なし → スキップ
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        # 差分なしでスキップ → None を返す（エラーにならない）
        self.assertIsNone(result)

    def test_pr_number_is_optional(self) -> None:
        """pr_number が None でも正常動作することを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            # pr_number=None でもエラーにならない
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        self.assertIsNone(result)
    def test_returns_error_string_on_session_exception(self) -> None:
        """create_session() が例外を投げた場合、Optional[str] エラーメッセージを返すことを確認。"""
        from orchestrator import _request_code_review
        from console import Console

        config = self._make_config()
        console = Console(quiet=True)

        mock_client = unittest.mock.AsyncMock()
        mock_client.create_session = unittest.mock.AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        mock_copilot = unittest.mock.MagicMock()
        mock_copilot.CopilotClient.return_value = mock_client
        mock_copilot.PermissionHandler = unittest.mock.MagicMock()
        mock_copilot.SubprocessConfig = unittest.mock.MagicMock()
        mock_copilot.ExternalServerConfig = unittest.mock.MagicMock()

        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = mock_copilot.PermissionHandler

        mock_git_result = unittest.mock.MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "diff --git a/foo.py b/foo.py\n+new"
        mock_git_result.stderr = ""

        with patch("subprocess.run", return_value=mock_git_result), \
             patch.dict("sys.modules", {"copilot": mock_copilot, "copilot.session": fake_copilot_session}):
            result = _run(_request_code_review(pr_number=None, config=config, console=console))

        # 例外は呼び出し元に伝播せず、エラーメッセージ文字列として返される
        self.assertIsInstance(result, str)
        self.assertIn("エラー", result)




    def test_dry_run_create_issues_shows_new_flow(self) -> None:
        """dry_run=True + create_issues=True で新フロー表示がエラーなく動作することを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True, create_issues=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("failed", []), [])

    def test_result_includes_root_issue_num_key(self) -> None:
        """dry_run の結果 dict に root_issue_num キーが含まれないことを確認。"""
        cfg = SDKConfig(dry_run=True, quiet=True)
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=cfg,
        ))
        # dry_run では Post-DAG 処理は実行されないため root_issue_num キーは含まれない
        self.assertNotIn("root_issue_num", result)

    def test_ignore_paths_default_in_config(self) -> None:
        """SDKConfig の ignore_paths にデフォルト値が設定されていることを確認。"""
        cfg = SDKConfig()
        self.assertIsNotNone(cfg.ignore_paths)
        self.assertIn("docs", cfg.ignore_paths)
        self.assertIn("images", cfg.ignore_paths)
        self.assertIn("src", cfg.ignore_paths)
        self.assertIn("work", cfg.ignore_paths)
        self.assertNotIn("infra", cfg.ignore_paths)
        self.assertNotIn("test", cfg.ignore_paths)


class TestCreatePrIfNeeded(unittest.TestCase):
    """_create_pr_if_needed() の root_issue_num 対応テスト。"""

    class _FailedDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = set()
            self.failed = {"1"}
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {}

    def test_run_workflow_does_not_create_pr_when_steps_failed(self) -> None:
        """失敗 Step がある場合、create_pr=True でも PR 作成経路へ入らない。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            create_pr=True,
            github_token="ghp_test",
            repo="owner/repo",
        )

        with patch("orchestrator._git_checkout_new_branch", return_value=True), \
             patch("orchestrator._git_add_commit_push", return_value=True), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FailedDAGExecutor()), \
             patch("orchestrator._create_pr_if_needed") as mock_create_pr:
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": ["1"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), ["1"])
        self.assertIsNone(result.get("pr_number"))
        self.assertEqual(result.get("error"), "失敗 Step があるため PR 作成をスキップしました。")
        mock_create_pr.assert_not_called()

    def test_non_target_auto_merge_does_not_enter_branch_or_pr_flow(self) -> None:
        """AAS では enable_auto_merge 単独で branch / PR 経路へ入らない。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )

        with patch("orchestrator._git_checkout_new_branch", return_value=True) as mock_checkout, \
             patch("orchestrator._git_add_commit_push", return_value=True) as mock_add_commit_push, \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FailedDAGExecutor()), \
             patch("orchestrator._create_pr_if_needed") as mock_create_pr:
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": ["1"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), ["1"])
        self.assertIsNone(result.get("pr_number"))
        self.assertIsNone(result.get("error"))
        mock_checkout.assert_not_called()
        mock_add_commit_push.assert_not_called()
        mock_create_pr.assert_not_called()

    def test_cleanup_failed_pr_closes_pr_and_deletes_branches(self) -> None:
        """作成済み失敗 PR cleanup はラベル削除・PR close・branch 削除を試みる。"""
        from orchestrator import _cleanup_failed_pr_if_created
        from console import Console
        from unittest.mock import patch as _patch

        cfg = SDKConfig(quiet=True, github_token="ghp_test", repo="owner/repo")
        console = Console(quiet=True)

        with _patch("orchestrator.api_call", return_value={}) as mock_api, \
             _patch("orchestrator._git_delete_remote_branch", return_value=True) as mock_remote_delete, \
             _patch("orchestrator._git_delete_local_branch", return_value=True) as mock_local_delete:
            _cleanup_failed_pr_if_created(123, "copilot-sdk/asdw-web-deadbeef", cfg, console)

        methods = [call.args[0] for call in mock_api.call_args_list]
        self.assertEqual(methods.count("DELETE"), 4)
        self.assertIn("PATCH", methods)
        deleted_urls = [
            call.args[1]
            for call in mock_api.call_args_list
            if call.args[0] == "DELETE"
        ]
        self.assertTrue(
            any(url.endswith("/labels/adversarial-review") for url in deleted_urls)
        )
        mock_remote_delete.assert_called_once_with("copilot-sdk/asdw-web-deadbeef", console)
        mock_local_delete.assert_called_once_with("copilot-sdk/asdw-web-deadbeef", "main", console)

    def test_cleanup_failed_pr_without_token_still_deletes_branches(self) -> None:
        """GH_TOKEN/REPO が無い場合も branch cleanup は試みる。"""
        from orchestrator import _cleanup_failed_pr_if_created
        from console import Console
        from unittest.mock import patch as _patch

        cfg = SDKConfig(quiet=True, github_token="", repo="")
        console = Console(quiet=True)

        with _patch("orchestrator.api_call") as mock_api, \
             _patch("orchestrator._git_delete_remote_branch", return_value=True) as mock_remote_delete, \
             _patch("orchestrator._git_delete_local_branch", return_value=True) as mock_local_delete:
            _cleanup_failed_pr_if_created(123, "copilot-sdk/asdw-web-deadbeef", cfg, console)

        mock_api.assert_not_called()
        mock_remote_delete.assert_called_once_with("copilot-sdk/asdw-web-deadbeef", console)
        mock_local_delete.assert_called_once_with("copilot-sdk/asdw-web-deadbeef", "main", console)

    def test_pr_body_includes_related_issue(self) -> None:
        """root_issue_num が指定された場合、PR body に 'Related Issue: #N' が含まれることを確認。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(quiet=True, github_token="ghp_test", repo="owner/repo")
        console = Console(quiet=True)

        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 42

        wf = MagicMock()
        wf.id = "aas"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/aas-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=99,
            )

        self.assertEqual(pr_num, 42)
        self.assertIn("Closes #99", captured_body.get("body", ""))

    def test_pr_body_without_root_issue(self) -> None:
        """root_issue_num が None の場合、PR body に 'Related Issue' が含まれないことを確認。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(quiet=True, github_token="ghp_test", repo="owner/repo")
        console = Console(quiet=True)

        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 43

        wf = MagicMock()
        wf.id = "aas"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/aas-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=None,
            )

        self.assertEqual(pr_num, 43)
        self.assertNotIn("Related Issue", captured_body.get("body", ""))

    def test_pr_body_includes_deploy_ac_verification_when_auto_merge(self) -> None:
        """enable_auto_merge=True + 全 Step 成功時、PR body に AC 検証行を転記する。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work" / "run" / "run-1"
            report = work_root / "Dev-Dataflow-FunctionsDeploy" / "Issue-step-3" / "ac-verification.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                "# AC verification\n"
                "| AC-2 | verify-batch-resources.sh GREEN | ✅ | ok |\n"
                "| AC-3 | Azure resources exist | ✅ | ok |\n"
                "secret=SHOULD_NOT_BE_COPIED\n",
                encoding="utf-8",
            )

            cfg = SDKConfig(
                quiet=True,
                github_token="ghp_test",
                repo="owner/repo",
                enable_auto_merge=True,
            )
            console = Console(quiet=True)
            captured_body: dict = {}

            def fake_create_pull_request(title, body, head, base, repo, token):
                captured_body["body"] = body
                return 46

            wf = MagicMock()
            wf.id = "adfdv"

            with patch.dict(os.environ, {"HVE_WORK_ROOT": str(work_root)}, clear=False), \
                 _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request), \
                 _patch("orchestrator.add_labels", return_value=True):
                pr_num = _create_pr_if_needed(
                    wf=wf,
                    head_branch="copilot-sdk/adfdv-abc12345",
                    base_branch="main",
                    config=cfg,
                    console=console,
                    all_steps_succeeded=True,
                )

        body = captured_body.get("body", "")
        self.assertEqual(pr_num, 46)
        self.assertIn("## Deploy AC Verification", body)
        self.assertIn("| AC-2 | verify-batch-resources.sh GREEN | ✅ |", body)
        self.assertIn("| AC-3 | Azure resources exist | ✅ |", body)
        self.assertNotIn("| AC-2 | verify-batch-resources.sh GREEN | ✅ | ok |", body)
        self.assertNotIn("SHOULD_NOT_BE_COPIED", body)

    def test_create_pr_if_needed_skips_when_steps_failed(self) -> None:
        """失敗 Step がある場合、_create_pr_if_needed 自体も PR を作成しない。"""
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(
            quiet=True,
            github_token="ghp_test",
            repo="owner/repo",
            enable_auto_merge=True,
        )
        console = Console(quiet=True)
        wf = MagicMock()
        wf.id = "adfdv"

        with _patch("orchestrator.create_pull_request") as mock_create_pull_request, \
             _patch("orchestrator.add_labels") as mock_add_labels:
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/adfdv-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                all_steps_succeeded=False,
            )

        self.assertIsNone(pr_num)
        mock_create_pull_request.assert_not_called()
        mock_add_labels.assert_not_called()


class TestAsdwStepScopedCicd(unittest.TestCase):
    """ASDW-WEB github.com CI/CD の Step 単位 branch lifecycle テスト。"""

    class _ArchFilterResult:
        matched_app_ids = ["APP-01"]
        catalog_found = True

        def to_dict(self):
            return {"matched_app_ids": self.matched_app_ids}

        def to_markdown_section(self):
            return ""

    class _NoopDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = {"1.3"}
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {}

    class _RunRemoteStepDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.run_step_fn = kwargs["run_step_fn"]
            self.completed = set()
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            ok = await self.run_step_fn(
                "3.4",
                "Azure Compute Deploy",
                "prompt",
                custom_agent="Dev-Microservice-Azure-ComputeDeploy-AzureFunctions",
            )
            if ok:
                self.completed.add("3.4")
            else:
                self.failed.add("3.4")
            return {}

    class _FakeRunner:
        def __init__(self, *args, **kwargs):
            pass

        def set_fork_index(self, *args, **kwargs):
            return None

        async def run_step(self, *args, **kwargs):
            return True

    def test_asdw_auto_merge_without_remote_cicd_step_does_not_create_branch(self) -> None:
        """ASDW-WEB で remote CI/CD 対象 Step が無ければ enable_auto_merge でも branch を作らない。"""
        for wf_id in ("asdw-web", "asdw"):
            with self.subTest(wf_id=wf_id):
                cfg = SDKConfig(
                    dry_run=False,
                    quiet=True,
                    enable_auto_merge=True,
                    github_token="ghp_test",
                    repo="owner/repo",
                )
                with patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()), \
                     patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
                     patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._NoopDAGExecutor()), \
                     patch("orchestrator._git_checkout_new_branch") as mock_checkout:
                    result = _run(run_workflow(
                        workflow_id=wf_id,
                        params={"branch": "main", "selected_steps": ["1.3"]},
                        config=cfg,
                    ))

                self.assertEqual(result.get("failed"), [])
                self.assertIsNone(result.get("working_branch"))
                mock_checkout.assert_not_called()

    def test_asdw_remote_cicd_step_uses_step_scoped_branch_pr_and_base_update(self) -> None:
        """ASDW-WEB remote CI/CD Step は Step 専用 branch → push → PR → merge 待機 → base 更新を行う。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        captured_prompt_branches: dict = {}

        def _fake_build_step_prompt(**kwargs):
            step = kwargs["step"]
            captured_prompt_branches[step.id] = kwargs["params"].get("branch")
            return f"prompt-{step.id}"

        with (
            patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()),
            patch("hve.workflow_registry.get_meta_dependencies", return_value=[]),
            patch("orchestrator._git_unmerged_paths", return_value=[]),
            patch("orchestrator.StepRunner", side_effect=lambda *a, **k: self._FakeRunner()),
            patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._RunRemoteStepDAGExecutor(*a, **k)),
            patch("orchestrator._build_step_prompt", side_effect=_fake_build_step_prompt),
            patch("orchestrator._git_checkout_new_branch", return_value=True) as mock_checkout,
            patch("orchestrator._git_add_commit_push", return_value=False) as mock_add_commit_push,
            patch("orchestrator._git_push_branch", return_value=True) as mock_push_branch,
            patch("orchestrator._git_remote_branch_ahead", return_value=False),
            patch("orchestrator._git_has_uncommitted_changes", return_value=False),
            patch("orchestrator._git_checkout_existing_branch", return_value=True),
            patch("orchestrator._create_pr_if_needed", return_value=101) as mock_create_pr,
            patch("orchestrator._wait_pr_merged", return_value=True) as mock_wait_merged,
            patch("orchestrator._git_delete_local_branch", return_value=True) as mock_delete_local,
            patch("orchestrator._git_pull_ff_only_base_branch", return_value=True) as mock_pull,
        ):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": ["3.4"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), [])
        self.assertIsNone(result.get("working_branch"))
        self.assertEqual(result.get("step_pr_numbers"), {"3.4": 101})
        step_branch = captured_prompt_branches["3.4"]
        self.assertRegex(step_branch, r"^copilot-sdk/asdw-web-step-3-4-[0-9a-f]{8}$")
        mock_checkout.assert_called_once_with(step_branch, "main", unittest.mock.ANY)
        self.assertEqual(mock_add_commit_push.call_count, 2)
        for call in mock_add_commit_push.call_args_list:
            self.assertEqual(call.kwargs["branch"], step_branch)
            self.assertNotIn("src", call.kwargs["ignore_paths"])
        self.assertEqual(mock_push_branch.call_count, 2)
        mock_create_pr.assert_called_once()
        self.assertEqual(mock_create_pr.call_args.kwargs["head_branch"], step_branch)
        mock_wait_merged.assert_called_once_with(
            101, cfg, unittest.mock.ANY, require_check_runs=False
        )
        mock_delete_local.assert_called_once_with(step_branch, "main", unittest.mock.ANY)
        mock_pull.assert_called_once_with("main", unittest.mock.ANY)

    def test_asdw_remote_cicd_remote_ahead_skips_stale_finalize_push(self) -> None:
        """Agent が remote Step branch を先に進めた場合、stale local branch を push しない。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        captured_prompt_branches: dict = {}

        def _fake_build_step_prompt(**kwargs):
            step = kwargs["step"]
            captured_prompt_branches[step.id] = kwargs["params"].get("branch")
            return f"prompt-{step.id}"

        with (
            patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()),
            patch("hve.workflow_registry.get_meta_dependencies", return_value=[]),
            patch("orchestrator._git_unmerged_paths", return_value=[]),
            patch("orchestrator.StepRunner", side_effect=lambda *a, **k: self._FakeRunner()),
            patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._RunRemoteStepDAGExecutor(*a, **k)),
            patch("orchestrator._build_step_prompt", side_effect=_fake_build_step_prompt),
            patch("orchestrator._git_checkout_new_branch", return_value=True),
            patch("orchestrator._git_add_commit_push", return_value=True) as mock_add_commit_push,
            patch("orchestrator._git_push_branch", return_value=True) as mock_push_branch,
            patch("orchestrator._git_remote_branch_ahead", return_value=True, create=True) as mock_remote_ahead,
            patch("orchestrator._create_pr_if_needed", return_value=101) as mock_create_pr,
            patch("orchestrator._wait_pr_merged", return_value=True),
            patch("orchestrator._git_delete_local_branch", return_value=True),
            patch("orchestrator._git_pull_ff_only_base_branch", return_value=True),
        ):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": ["3.4"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), [])
        step_branch = captured_prompt_branches["3.4"]
        mock_remote_ahead.assert_called_once_with(step_branch, unittest.mock.ANY)
        self.assertEqual(mock_add_commit_push.call_count, 1)
        mock_push_branch.assert_not_called()
        mock_create_pr.assert_called_once()

    def test_asdw_remote_cicd_current_branch_drift_with_changes_fails_fast(self) -> None:
        """Agent 実行後に current branch が drift し未コミット差分がある場合、final push しない。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        captured_prompt_branches: dict = {}

        def _fake_build_step_prompt(**kwargs):
            step = kwargs["step"]
            captured_prompt_branches[step.id] = kwargs["params"].get("branch")
            return f"prompt-{step.id}"

        with (
            patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()),
            patch("hve.workflow_registry.get_meta_dependencies", return_value=[]),
            patch("orchestrator._git_unmerged_paths", return_value=[]),
            patch("orchestrator.StepRunner", side_effect=lambda *a, **k: self._FakeRunner()),
            patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._RunRemoteStepDAGExecutor(*a, **k)),
            patch("orchestrator._build_step_prompt", side_effect=_fake_build_step_prompt),
            patch("orchestrator._git_checkout_new_branch", return_value=True),
            patch("orchestrator._git_add_commit_push", return_value=True) as mock_add_commit_push,
            patch("orchestrator._git_push_branch", return_value=True) as mock_push_branch,
            patch("orchestrator._git_remote_branch_ahead", return_value=False, create=True),
            patch("orchestrator._git_current_branch", return_value="main", create=True) as mock_current_branch,
            patch("orchestrator._git_has_uncommitted_changes", return_value=True, create=True),
            patch("orchestrator._create_pr_if_needed", return_value=101) as mock_create_pr,
            patch("orchestrator._wait_pr_merged", return_value=True),
            patch("orchestrator._git_delete_local_branch", return_value=True),
            patch("orchestrator._git_pull_ff_only_base_branch", return_value=True),
        ):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": ["3.4"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), ["3.4"])
        self.assertIn("3.4", captured_prompt_branches)
        mock_current_branch.assert_called_once()
        self.assertEqual(mock_add_commit_push.call_count, 1)
        mock_push_branch.assert_not_called()
        mock_create_pr.assert_not_called()

    def test_asdw_remote_cicd_unmerged_index_stops_before_dag_execution(self) -> None:
        """未解決 index がある場合は Step scoped CI/CD の DAG 実行前に停止する。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        with patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator._git_unmerged_paths", return_value=["src/api/SVC-13/Functions.cs"]), \
             patch("orchestrator.DAGExecutor") as mock_dag_executor, \
             patch("orchestrator._git_checkout_new_branch") as mock_checkout:
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": ["3.4"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), [])
        self.assertEqual(result.get("blocked"), [])
        self.assertIn("Git index", result.get("error", ""))
        self.assertIn("src/api/SVC-13/Functions.cs", result.get("error", ""))
        mock_dag_executor.assert_not_called()
        mock_checkout.assert_not_called()

    def test_asdw_remote_cicd_pr_creation_failure_returns_to_base_branch(self) -> None:
        """Step 実行成功後に PR 作成へ失敗した場合も local は base branch へ戻す。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            enable_auto_merge=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        with (
            patch("orchestrator.resolve_app_arch_scope", return_value=self._ArchFilterResult()),
            patch("hve.workflow_registry.get_meta_dependencies", return_value=[]),
            patch("orchestrator._git_unmerged_paths", return_value=[]),
            patch("orchestrator.StepRunner", side_effect=lambda *a, **k: self._FakeRunner()),
            patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._RunRemoteStepDAGExecutor(*a, **k)),
            patch("orchestrator._git_checkout_new_branch", return_value=True),
            patch("orchestrator._git_add_commit_push", return_value=True),
            patch("orchestrator._git_remote_branch_ahead", return_value=False),
            patch("orchestrator._git_has_uncommitted_changes", return_value=False),
            patch("orchestrator._git_checkout_existing_branch", return_value=True),
            patch("orchestrator._create_pr_if_needed", return_value=None),
            patch("orchestrator._git_checkout_base_branch", return_value=True) as mock_checkout_base,
        ):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": ["3.4"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed"), ["3.4"])
        mock_checkout_base.assert_called_once_with("main", unittest.mock.ANY)


class TestDoneLabeling(unittest.TestCase):
    class _FakeDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = {"1"}
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {}

    def test_agent_prompt_execution_mode_is_local_even_when_create_issues_true(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            create_issues=True,
            github_token="ghp_test",
            repo="owner/repo",
        )
        captured_modes = []

        def _fake_build_step_prompt(**kwargs):
            captured_modes.append(kwargs.get("execution_mode"))
            return "dummy prompt"

        with patch("orchestrator._git_checkout_new_branch", return_value=True), \
             patch("orchestrator._git_add_commit_push", return_value=False), \
             patch("orchestrator._create_issues_if_needed", return_value=(123, {})), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("orchestrator._build_step_prompt", side_effect=_fake_build_step_prompt):
            _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": ["1"]},
                config=cfg,
            ))

        self.assertTrue(captured_modes)
        self.assertTrue(all(mode == "local" for mode in captured_modes))

    def test_adds_done_label_after_completed_step_in_github_mode(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            create_issues=True,
            github_token="ghp_test",
            repo="owner/repo",
        )

        with patch("orchestrator._git_checkout_new_branch", return_value=True), \
             patch("orchestrator._git_add_commit_push", return_value=False), \
             patch("orchestrator._create_issues_if_needed", return_value=(123, {"1": 456})), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("orchestrator.add_labels", return_value=True) as mock_add_labels:
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": ["1"]},
                config=cfg,
            ))

        self.assertEqual(result.get("failed", []), [])
        mock_add_labels.assert_called_once_with(
            issue_num=456,
            labels=["aas:done"],
            repo="owner/repo",
            token="ghp_test",
        )

    def test_pr_body_includes_workiq_reports_when_enabled(self) -> None:
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(
            quiet=True,
            github_token="ghp_test",
            repo="owner/repo",
            workiq_enabled=True,
            run_id="run-123",
        )
        console = Console(quiet=True)
        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 44

        wf = MagicMock()
        wf.id = "akm"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/akm-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=None,
                workiq_report_paths=["qa/run-123-1-workiq-qa.md"],
            )

        self.assertEqual(pr_num, 44)
        self.assertIn("## Work IQ レポート", captured_body.get("body", ""))
        self.assertIn("qa/run-123-1-workiq-qa.md", captured_body.get("body", ""))

    def test_pr_body_uses_draft_output_dir_and_filters_ignored_paths(self) -> None:
        from orchestrator import _create_pr_if_needed
        from console import Console
        from unittest.mock import MagicMock, patch as _patch

        cfg = SDKConfig(
            quiet=True,
            github_token="ghp_test",
            repo="owner/repo",
            workiq_enabled=True,
            run_id="run-abc",
            workiq_draft_output_dir="qa",
            ignore_paths=["work"],
        )
        console = Console(quiet=True)
        captured_body: dict = {}

        def fake_create_pull_request(title, body, head, base, repo, token):
            captured_body["body"] = body
            return 45

        wf = MagicMock()
        wf.id = "aqod"

        with _patch("orchestrator.create_pull_request", side_effect=fake_create_pull_request), \
             _patch("orchestrator._glob.glob", side_effect=[
                 [
                     "qa/run-abc-1-workiq-qa-draft.md",
                     "qa/run-abc-1-workiq-qa.md",
                 ],
                 [
                     "qa/run-abc-2-workiq-qa-draft.jsonl",
                 ],
             ]):
            pr_num = _create_pr_if_needed(
                wf=wf,
                head_branch="copilot-sdk/aqod-abc12345",
                base_branch="main",
                config=cfg,
                console=console,
                root_issue_num=None,
                workiq_report_paths=["qa/run-abc-1-workiq-qa.md"],
            )

        self.assertEqual(pr_num, 45)
        body = captured_body.get("body", "")
        self.assertIn("qa/run-abc-1-workiq-qa-draft.md", body)
        self.assertIn("qa/run-abc-1-workiq-qa.md", body)
        self.assertIn("qa/run-abc-2-workiq-qa-draft.jsonl", body)
        self.assertNotIn("work/run-abc/workiq-1-review.md", body)


class TestDetectExistingArtifacts(unittest.TestCase):
    """_detect_existing_artifacts() のテスト。"""

    def test_returns_empty_when_no_artifacts(self) -> None:
        """成果物が存在しない場合、空の辞書を返すことを確認。"""
        from orchestrator import _detect_existing_artifacts
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = _detect_existing_artifacts("asdw", {})
            finally:
                os.chdir(original_cwd)

        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_detects_existing_catalog(self) -> None:
        """app-catalog.md が存在する場合に検出されることを確認。"""
        from orchestrator import _detect_existing_artifacts
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_dir = os.path.join(tmpdir, "docs", "catalog")
            os.makedirs(catalog_dir)
            catalog_path = os.path.join(catalog_dir, "app-catalog.md")
            with open(catalog_path, "w") as f:
                f.write("# App Catalog\n")

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = _detect_existing_artifacts("asdw", {})
            finally:
                os.chdir(original_cwd)

        self.assertIn("app_catalog", result)
        self.assertEqual(result["app_catalog"], "docs/catalog/app-catalog.md")

    def test_detects_docs_generated_artifacts(self) -> None:
        """docs-generated 配下の成果物が検出されることを確認。"""
        from orchestrator import _detect_existing_artifacts
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "docs-generated", "guides")
            os.makedirs(out_dir)
            out_path = os.path.join(out_dir, "onboarding.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("# onboarding\n")

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = _detect_existing_artifacts("adoc", {})
            finally:
                os.chdir(original_cwd)

        self.assertIn("doc_generated", result)
        self.assertEqual(result["doc_generated"], ["docs-generated/guides/onboarding.md"])

    def test_does_not_detect_docs_generated_for_non_adoc(self) -> None:
        """ADOC 以外では docs-generated を検出しないこと。"""
        from orchestrator import _detect_existing_artifacts
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "docs-generated", "guides")
            os.makedirs(out_dir)
            out_path = os.path.join(out_dir, "onboarding.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("# onboarding\n")

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = _detect_existing_artifacts("aas", {})
            finally:
                os.chdir(original_cwd)

        self.assertNotIn("doc_generated", result)

    def test_doc_generated_path_is_normalized(self) -> None:
        """doc_generated のパスが / 区切りに正規化されること。"""
        from orchestrator import _detect_existing_artifacts
        from unittest.mock import patch

        with patch("orchestrator._glob.glob", return_value=[r"docs-generated\guides\onboarding.md"]):
            result = _detect_existing_artifacts("adoc", {})
        self.assertEqual(result["doc_generated"], ["docs-generated/guides/onboarding.md"])


class TestBuildReuseContext(unittest.TestCase):
    """_build_reuse_context() のテスト。"""

    def test_empty_artifacts_returns_empty_string(self) -> None:
        """成果物が空の場合、空文字を返すことを確認。"""
        from orchestrator import _build_reuse_context
        result = _build_reuse_context({})
        self.assertEqual(result, "")

    def test_non_empty_artifacts_returns_context(self) -> None:
        """成果物がある場合、再利用コンテキスト文字列を返すことを確認。"""
        from orchestrator import _build_reuse_context
        artifacts = {
            "app_catalog": "docs/catalog/app-catalog.md",
            "service_specs": ["docs/services/SVC-01.md", "docs/services/SVC-02.md"],
        }
        result = _build_reuse_context(artifacts)
        self.assertIn("🔄 既存成果物", result)
        self.assertIn("docs/catalog/app-catalog.md", result)
        self.assertIn("docs/services/SVC-01.md", result)
        self.assertIn("再利用ルール", result)

    def test_list_truncated_at_10(self) -> None:
        """リスト型の成果物が 10 件以上ある場合、省略表示されることを確認。"""
        from orchestrator import _build_reuse_context
        artifacts = {
            "src_files": [f"src/file{i}.py" for i in range(15)],
        }
        result = _build_reuse_context(artifacts)
        self.assertIn("...他 5 ファイル", result)


class TestBuildReuseContextStepKind(unittest.TestCase):
    """Sub-2 (A-2): _build_reuse_context() の step_kind 別簡素化テスト。

    step_kind ごとに再利用ルール文が切り替わり、default よりも短くなることを検証する。
    """

    def setUp(self) -> None:
        from orchestrator import _build_reuse_context
        self._build = _build_reuse_context
        self._artifacts = {
            "app_catalog": "docs/catalog/app-catalog.md",
        }

    def test_default_kind_uses_long_rules(self) -> None:
        result = self._build(self._artifacts, step_kind="default")
        # default のルール文は 5 項目（既存と同等）
        self.assertIn("既存のドキュメント/コード構造を尊重", result)
        self.assertIn("Catalog ファイルは既存エントリ", result)

    def test_catalog_kind_short(self) -> None:
        result = self._build(self._artifacts, step_kind="catalog")
        self.assertIn("Catalog ファイルは既存エントリ", result)
        # default 専用のルールが含まれないこと
        self.assertNotIn("既存のドキュメント/コード構造を尊重", result)
        # default より短いことを確認
        default_result = self._build(self._artifacts, step_kind="default")
        self.assertLess(len(result), len(default_result))

    def test_tests_kind_short(self) -> None:
        result = self._build(self._artifacts, step_kind="tests")
        self.assertIn("テスト仕様書・テストコード", result)
        default_result = self._build(self._artifacts, step_kind="default")
        self.assertLess(len(result), len(default_result))

    def test_code_kind_short(self) -> None:
        result = self._build(self._artifacts, step_kind="code")
        self.assertIn("既存コード構造", result)
        default_result = self._build(self._artifacts, step_kind="default")
        self.assertLess(len(result), len(default_result))

    def test_docs_kind_short(self) -> None:
        result = self._build(self._artifacts, step_kind="docs")
        self.assertIn("既存ドキュメント構造", result)
        default_result = self._build(self._artifacts, step_kind="default")
        self.assertLess(len(result), len(default_result))

    def test_unknown_kind_falls_back_to_default(self) -> None:
        result = self._build(self._artifacts, step_kind="unknown_kind")
        default_result = self._build(self._artifacts, step_kind="default")
        self.assertEqual(result, default_result)

    def test_empty_artifacts_returns_empty_regardless_of_kind(self) -> None:
        for kind in ("default", "catalog", "tests", "code", "docs"):
            with self.subTest(kind=kind):
                self.assertEqual(self._build({}, step_kind=kind), "")


class TestInferStepKind(unittest.TestCase):
    """Sub-2 (A-2): _infer_step_kind() の判定ロジックテスト。"""

    def test_none_or_empty_returns_default(self) -> None:
        from orchestrator import _infer_step_kind
        self.assertEqual(_infer_step_kind(None), "default")
        self.assertEqual(_infer_step_kind([]), "default")

    def test_test_majority_returns_tests(self) -> None:
        from orchestrator import _infer_step_kind
        self.assertEqual(_infer_step_kind(["test_files", "test_specs"]), "tests")
        self.assertEqual(_infer_step_kind(["test_files", "test_specs", "app_catalog"]), "tests")

    def test_src_majority_returns_code(self) -> None:
        from orchestrator import _infer_step_kind
        self.assertEqual(_infer_step_kind(["src_files"]), "code")

    def test_doc_majority_returns_docs(self) -> None:
        from orchestrator import _infer_step_kind
        self.assertEqual(_infer_step_kind(["knowledge"]), "docs")
        self.assertEqual(_infer_step_kind(["doc_generated"]), "docs")

    def test_catalog_majority_returns_catalog(self) -> None:
        from orchestrator import _infer_step_kind
        self.assertEqual(
            _infer_step_kind(["app_catalog", "service_catalog", "data_model"]),
            "catalog",
        )

    def test_mixed_returns_default(self) -> None:
        from orchestrator import _infer_step_kind
        # 種別が均等に混在する場合は default に倒れる
        self.assertEqual(
            _infer_step_kind(["src_files", "test_files", "app_catalog", "knowledge"]),
            "default",
        )


class TestReuseContextFiltering(unittest.TestCase):
    """HVE_REUSE_CONTEXT_FILTERING フィーチャーフラグのテスト。

    _compute_step_additional_prompt() を経由して実装ロジックを直接検証する。
    """

    def _make_step(self, step_id: str, consumed_artifacts=None):
        """テスト用 StepDef を生成する。"""
        from workflow_registry import StepDef
        return StepDef(
            id=step_id,
            title=f"Step {step_id}",
            custom_agent="TestAgent",
            consumed_artifacts=consumed_artifacts,
        )

    def _make_artifacts(self):
        return {
            "app_catalog": "docs/catalog/app-catalog.md",
            "service_specs": ["docs/services/SVC-01.md"],
        }

    # ------------------------------------------------------------------
    # フラグ OFF: 旧挙動（base_additional_prompt そのまま返す）
    # ------------------------------------------------------------------

    def test_flag_off_returns_base_additional_prompt(self) -> None:
        """フラグ OFF の場合、base_additional_prompt がそのまま返ること。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=[])
        cfg = SDKConfig(reuse_context_filtering=False)
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "base_prompt")
        self.assertEqual(result, "base_prompt")

    def test_flag_off_with_none_consumed_returns_base(self) -> None:
        """フラグ OFF + consumed_artifacts=None でも base_additional_prompt を返すこと。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=None)
        cfg = SDKConfig(reuse_context_filtering=False)
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "base_prompt")
        self.assertEqual(result, "base_prompt")

    # ------------------------------------------------------------------
    # フラグ ON + consumed_artifacts=None: 後方互換（全成果物）
    # ------------------------------------------------------------------

    def test_flag_on_none_consumed_artifacts_fallback_to_base(self) -> None:
        """フラグ ON + consumed_artifacts=None（未アノテーション）の場合、後方互換で base を返すこと。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=None)
        cfg = SDKConfig(reuse_context_filtering=True)
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "base_prompt")
        self.assertEqual(result, "base_prompt")

    # ------------------------------------------------------------------
    # フラグ ON + consumed_artifacts=[]: reuse_context なし
    # ------------------------------------------------------------------

    def test_flag_on_empty_consumed_artifacts_omits_reuse_context(self) -> None:
        """フラグ ON + consumed_artifacts=[] のステップには reuse_context が付かないこと。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=[])
        cfg = SDKConfig(reuse_context_filtering=True, additional_prompt="user_prompt")
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "user_prompt")
        # reuse_context は空なので、additional_prompt が除去された None または "user_prompt" 相当
        # _build_reuse_context({}) == "" なので ("user_prompt" + "").strip() == "user_prompt"
        self.assertEqual(result, "user_prompt")

    def test_flag_on_empty_consumed_no_base_returns_none(self) -> None:
        """フラグ ON + consumed_artifacts=[] + base が None の場合、None が返ること。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=[])
        cfg = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, None)
        # ("" + "").strip() == "" → None
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # フラグ ON + consumed_artifacts=[key]: 指定キーのみ
    # ------------------------------------------------------------------

    def test_flag_on_filtered_consumed_artifacts(self) -> None:
        """フラグ ON + consumed_artifacts=["app_catalog"] のステップには app_catalog のみ含む reuse_context が付くこと。"""
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("4", consumed_artifacts=["app_catalog"])
        cfg = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        result = _compute_step_additional_prompt(step, self._make_artifacts(), cfg, None)
        self.assertIsNotNone(result)
        self.assertIn("app-catalog.md", result)
        self.assertNotIn("SVC-01.md", result)

    def test_flag_on_full_context_smaller_than_partial(self) -> None:
        """フラグ ON でフィルタリングすると、全成果物を渡す場合よりプロンプトが短くなること。"""
        from orchestrator import _compute_step_additional_prompt
        from orchestrator import _build_reuse_context as _brc
        from config import SDKConfig
        artifacts = {
            "app_catalog": "docs/catalog/app-catalog.md",
            "service_catalog": "docs/catalog/service-catalog.md",
            "service_specs": [f"docs/services/SVC-{i:02d}.md" for i in range(5)],
            "doc_generated": [f"docs-generated/file{i}.md" for i in range(3)],
        }
        cfg_off = SDKConfig(reuse_context_filtering=False, additional_prompt=None)
        cfg_on = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        step = self._make_step("4", consumed_artifacts=["doc_generated"])

        # フラグ OFF は base_additional_prompt をそのまま返す
        # テスト用 base として全成果物の reuse_context 文字列を使用
        base_with_all = _brc(artifacts)  # 全成果物入りの大きな文字列
        result_off = _compute_step_additional_prompt(step, artifacts, cfg_off, base_with_all)
        self.assertEqual(result_off, base_with_all)

        # フラグ ON は doc_generated のみを含む reuse_context を構築
        result_filtered = _compute_step_additional_prompt(step, artifacts, cfg_on, base_with_all)
        self.assertIsNotNone(result_filtered)
        self.assertIn("docs-generated/file0.md", result_filtered)
        self.assertLess(len(result_filtered), len(base_with_all))

    # ------------------------------------------------------------------
    # 未知キーの警告
    # ------------------------------------------------------------------

    def test_unknown_key_emits_warning(self) -> None:
        """consumed_artifacts に存在しないキーが含まれる場合、UserWarning が発行されること。"""
        import warnings
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("X", consumed_artifacts=["nonexistent_key"])
        cfg = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _compute_step_additional_prompt(step, self._make_artifacts(), cfg, None)
        self.assertTrue(
            any("nonexistent_key" in str(w.message) for w in caught),
            f"期待する警告が発行されませんでした。発行された警告: {[str(w.message) for w in caught]}",
        )

    def test_known_key_no_warning(self) -> None:
        """consumed_artifacts のキーが全て存在する場合、警告は発行されないこと。"""
        import warnings
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("4", consumed_artifacts=["app_catalog"])
        cfg = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _compute_step_additional_prompt(step, self._make_artifacts(), cfg, None)
        self.assertFalse(
            any("consumed_artifacts" in str(w.message) for w in caught),
            f"不要な警告が発行されました: {[str(w.message) for w in caught]}",
        )

    # ------------------------------------------------------------------
    # Wave 2-2: consumed_artifacts=None 後方互換警告テスト
    # ------------------------------------------------------------------

    def test_none_consumed_emits_backward_compat_warning(self) -> None:
        """Wave 2-2: consumed_artifacts=None のステップで後方互換警告が発行されること。"""
        import warnings
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=None)
        cfg = SDKConfig(reuse_context_filtering=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "base")
        self.assertTrue(
            any("後方互換モード" in str(w.message) or "consumed_artifacts=None" in str(w.message) for w in caught),
            f"後方互換警告が発行されませんでした: {[str(w.message) for w in caught]}",
        )

    def test_empty_list_consumed_no_backward_compat_warning(self) -> None:
        """Wave 2-2: consumed_artifacts=[] のステップでは後方互換警告が発行されないこと。"""
        import warnings
        from orchestrator import _compute_step_additional_prompt
        from config import SDKConfig
        step = self._make_step("1", consumed_artifacts=[])
        cfg = SDKConfig(reuse_context_filtering=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _compute_step_additional_prompt(step, self._make_artifacts(), cfg, "base")
        self.assertFalse(
            any("後方互換モード" in str(w.message) for w in caught),
            f"不要な後方互換警告: {[str(w.message) for w in caught]}",
        )

    # ------------------------------------------------------------------
    # SDKConfig / 環境変数
    # ------------------------------------------------------------------

    def test_sdkconfig_reuse_context_filtering_default_true(self) -> None:
        """SDKConfig のデフォルトは reuse_context_filtering=True であること。"""
        from config import SDKConfig
        cfg = SDKConfig()
        self.assertTrue(cfg.reuse_context_filtering)

    def test_sdkconfig_from_env_reads_flag(self) -> None:
        """環境変数 HVE_REUSE_CONTEXT_FILTERING=true で SDKConfig.reuse_context_filtering=True になること。"""
        import os
        from config import SDKConfig
        with unittest.mock.patch.dict(os.environ, {"HVE_REUSE_CONTEXT_FILTERING": "true"}):
            cfg = SDKConfig.from_env()
        self.assertTrue(cfg.reuse_context_filtering)

    def test_sdkconfig_from_env_reads_flag_false(self) -> None:
        """環境変数 HVE_REUSE_CONTEXT_FILTERING=false で SDKConfig.reuse_context_filtering=False になること。"""
        import os
        from config import SDKConfig
        with unittest.mock.patch.dict(os.environ, {"HVE_REUSE_CONTEXT_FILTERING": "false"}):
            cfg = SDKConfig.from_env()
        self.assertFalse(cfg.reuse_context_filtering)

    def test_sdkconfig_from_env_default_true(self) -> None:
        """環境変数 HVE_REUSE_CONTEXT_FILTERING 未設定の場合 True（デフォルト有効）であること。"""
        import os
        from config import SDKConfig
        env = {k: v for k, v in os.environ.items() if k != "HVE_REUSE_CONTEXT_FILTERING"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            cfg = SDKConfig.from_env()
        self.assertTrue(cfg.reuse_context_filtering)

    # ------------------------------------------------------------------
    # ワークフロー定義アノテーション確認
    # ------------------------------------------------------------------

    def test_adoc_steps_have_consumed_artifacts_annotated(self) -> None:
        """ADOC 全ステップに consumed_artifacts アノテーションが設定されていること。"""
        from workflow_registry import ADOC
        for step in ADOC.steps:
            if step.is_container:
                continue
            self.assertIsNotNone(
                step.consumed_artifacts,
                f"ADOC Step {step.id} の consumed_artifacts が未アノテーション（None）",
            )

    def test_adoc_early_steps_consume_no_artifacts(self) -> None:
        """ADOC Step 1-3.x（ソースコード分析フェーズ）は consumed_artifacts=[] であること。"""
        from workflow_registry import ADOC
        early_step_ids = {"1", "2.1", "2.2", "2.3", "2.4", "2.5",
                          "3.1", "3.2", "3.3", "3.4", "3.5"}
        for step in ADOC.steps:
            if step.id in early_step_ids:
                self.assertEqual(
                    step.consumed_artifacts, [],
                    f"ADOC Step {step.id}: consumed_artifacts={step.consumed_artifacts!r}, expected []",
                )

    def test_adoc_late_steps_consume_doc_generated(self) -> None:
        """ADOC Step 4 以降（統合・横断分析フェーズ）は consumed_artifacts=['doc_generated'] であること。"""
        from workflow_registry import ADOC
        late_step_ids = {"4", "5.1", "5.2", "5.3", "5.4", "6.1", "6.2", "6.3"}
        for step in ADOC.steps:
            if step.id in late_step_ids:
                self.assertEqual(
                    step.consumed_artifacts, ["doc_generated"],
                    f"ADOC Step {step.id}: consumed_artifacts={step.consumed_artifacts!r}, expected ['doc_generated']",
                )

    def test_aas_steps_have_consumed_artifacts_annotated(self) -> None:
        """AAS ワークフローステップは consumed_artifacts が明示アノテーション済みであること。
        Phase 8 で全 AAS ステップに consumed_artifacts を設定した。
        """
        from workflow_registry import AAS
        for step in AAS.steps:
            if step.is_container:
                continue
            self.assertIsNotNone(
                step.consumed_artifacts,
                f"AAS Step {step.id} の consumed_artifacts が未アノテーション（None）",
            )
            self.assertIsInstance(
                step.consumed_artifacts,
                list,
                f"AAS Step {step.id} の consumed_artifacts がリストでない: {step.consumed_artifacts!r}",
            )

    def test_filtering_token_reduction_for_adoc(self) -> None:
        """ADOC 早期ステップでフィルタリング ON 時にトークン削減効果があること（文字列長比較）。"""
        from orchestrator import _compute_step_additional_prompt
        from orchestrator import _build_reuse_context as _brc
        from config import SDKConfig
        # 典型的な既存成果物（AAS / AAD 実行後の状態）
        artifacts = {
            "app_catalog": "docs/catalog/app-catalog.md",
            "service_catalog": "docs/catalog/service-catalog.md",
            "data_model": "docs/catalog/data-model.md",
            "domain_analytics": "docs/catalog/domain-analytics.md",
            "service_specs": [f"docs/services/SVC-{i:02d}.md" for i in range(5)],
            "doc_generated": [f"docs-generated/file{i}.md" for i in range(3)],
        }
        # フラグ OFF 相当の base（全成果物入り）: run_workflow が構築する effective_additional_prompt と等価
        base_with_all = _brc(artifacts)

        cfg_off = SDKConfig(reuse_context_filtering=False, additional_prompt=None)
        cfg_on = SDKConfig(reuse_context_filtering=True, additional_prompt=None)

        # ADOC Step 1: consumed_artifacts=[] → reuse_context なし
        # フラグ ON + consumed_artifacts=[] + config.additional_prompt=None → ("" + "").strip() = "" → None
        step1 = self._make_step("1", consumed_artifacts=[])
        result_step1 = _compute_step_additional_prompt(step1, artifacts, cfg_on, base_with_all)
        self.assertIsNone(result_step1)

        # ADOC Step 4: consumed_artifacts=["doc_generated"] → doc_generated のみ
        step4 = self._make_step("4", consumed_artifacts=["doc_generated"])
        result_step4 = _compute_step_additional_prompt(step4, artifacts, cfg_on, base_with_all)
        self.assertIsNotNone(result_step4)
        self.assertIn("docs-generated/file0.md", result_step4)

        # フラグ OFF（= base_with_all をそのまま返す）と比較して短い
        result_off = _compute_step_additional_prompt(step4, artifacts, cfg_off, base_with_all)
        self.assertEqual(result_off, base_with_all)
        self.assertLess(len(result_step4), len(result_off))

    def test_aad_web_steps_have_consumed_artifacts_annotated(self) -> None:
        """AAD-WEB 全ステップに consumed_artifacts アノテーションが設定されていること。"""
        from workflow_registry import AAD_WEB
        for step in AAD_WEB.steps:
            if step.is_container:
                continue
            self.assertIsNotNone(
                step.consumed_artifacts,
                f"AAD-WEB Step {step.id} の consumed_artifacts が未アノテーション（None）",
            )

    def test_aad_web_step1_consumed_artifacts(self) -> None:
        """AAD-WEB Step 1 は app_catalog / service_catalog / data_model / domain_analytics を参照すること。"""
        from workflow_registry import AAD_WEB
        step1 = next(s for s in AAD_WEB.steps if s.id == "1")
        for key in ("app_catalog", "service_catalog", "data_model", "domain_analytics"):
            self.assertIn(key, step1.consumed_artifacts,
                          f"AAD-WEB Step 1: expected {key!r} in consumed_artifacts")

    def test_aad_web_step2_3_consumed_artifacts_include_service_specs(self) -> None:
        """AAD-WEB Step 2.3 (サービス TDD) は service_specs / test_strategy を参照すること。"""
        from workflow_registry import AAD_WEB
        step23 = next(s for s in AAD_WEB.steps if s.id == "2.3")
        for key in ("service_specs", "test_strategy"):
            self.assertIn(key, step23.consumed_artifacts,
                          f"AAD-WEB Step 2.3: expected {key!r} in consumed_artifacts")

    def test_aad_web_step2_4_consumed_artifacts_include_screen_specs(self) -> None:
        """AAD-WEB Step 2.4 (画面 TDD) は screen_specs / test_strategy を参照すること。"""
        from workflow_registry import AAD_WEB
        step24 = next(s for s in AAD_WEB.steps if s.id == "2.4")
        for key in ("screen_specs", "test_strategy"):
            self.assertIn(key, step24.consumed_artifacts,
                          f"AAD-WEB Step 2.4: expected {key!r} in consumed_artifacts")

    def test_aad_web_filtering_reduces_context(self) -> None:
        """AAD-WEB Step 1（filtered）は全成果物渡しより短いコンテキストになること。"""
        from orchestrator import _compute_step_additional_prompt, _build_reuse_context as _brc
        from config import SDKConfig
        from workflow_registry import AAD_WEB
        # 典型的な AAS 実行後の成果物
        artifacts = {
            "app_catalog": "docs/catalog/app-catalog.md",
            "service_catalog": "docs/catalog/service-catalog.md",
            "data_model": "docs/catalog/data-model.md",
            "domain_analytics": "docs/catalog/domain-analytics.md",
            "test_strategy": "docs/catalog/test-strategy.md",
            "service_specs": [f"docs/services/SVC-{i:02d}.md" for i in range(5)],
            "screen_specs": [f"docs/screen/SCR-{i:02d}.md" for i in range(3)],
        }
        base_with_all = _brc(artifacts)
        cfg_on = SDKConfig(reuse_context_filtering=True, additional_prompt=None)
        cfg_off = SDKConfig(reuse_context_filtering=False, additional_prompt=None)

        step1 = next(s for s in AAD_WEB.steps if s.id == "1")
        result_on = _compute_step_additional_prompt(step1, artifacts, cfg_on, base_with_all)
        result_off = _compute_step_additional_prompt(step1, artifacts, cfg_off, base_with_all)

        # フィルタリング ON では全成果物より短い
        self.assertIsNotNone(result_on)
        self.assertLess(len(result_on), len(result_off))
        # Step 1 に不要な screen_specs は含まれない
        self.assertNotIn("SCR-00.md", result_on)
        # Step 1 に必要な app_catalog は含まれる
        self.assertIn("app-catalog.md", result_on)


class TestCollectParamsNonInteractiveAppIds(unittest.TestCase):
    """_collect_params_non_interactive() の app_ids 対応テスト。"""

    def _make_wf(self):
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "asdw"
        return wf

    def test_app_ids_list_passed_through(self) -> None:
        """app_ids リストがそのまま params に設定されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {
            "branch": "main",
            "app_ids": ["APP-01", "APP-02"],
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params["app_ids"], ["APP-01", "APP-02"])

    def test_app_ids_single_also_sets_app_id(self) -> None:
        """app_ids に1件のみの場合、app_id にも設定されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {
            "branch": "main",
            "app_ids": ["APP-01"],
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params["app_ids"], ["APP-01"])
        self.assertEqual(params.get("app_id"), "APP-01")

    def test_app_id_legacy_normalised_to_app_ids(self) -> None:
        """旧 app_id が app_ids リストに正規化されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {
            "branch": "main",
            "app_id": "APP-05",
        }
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params["app_ids"], ["APP-05"])
        self.assertEqual(params["app_id"], "APP-05")

    def test_usecase_id_is_carried_for_aag(self) -> None:
        """AAG/AAGD 用 usecase_id がそのまま伝播されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        from unittest.mock import MagicMock

        wf = MagicMock()
        wf.id = "aag"
        params = _collect_params_non_interactive(
            wf,
            {"branch": "main", "app_id": "APP-05", "usecase_id": "UC-100"},
        )
        self.assertEqual(params["usecase_id"], "UC-100")


class TestRunWorkflowSelfImprove(unittest.TestCase):
    """run_workflow の Self-Improve フェーズテスト。"""

    class _FakeDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = set()
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {"completed": [], "failed": [], "skipped": []}

    @staticmethod
    def _successful_si_result(task_goal, **overrides):
        definitions = task_goal.get("criterion_definitions", []) if task_goal else []
        criteria = [
            {
                "criterion_id": item["criterion_id"],
                "required_for_done": item.get("required_for_done") is True,
                "status": "PASS",
                "evidence": [{"status": "PASS", "reference": "test-double"}],
            }
            for item in definitions
            if item.get("criterion_id")
        ]
        result = {
            "iterations_completed": 0,
            "final_score": 100,
            "records": [],
            "stopped_reason": "no_improvement_needed",
            "reward_history": [],
            "final_goal_achievement_pct": 1.0,
            "final_criterion_results": criteria,
            "final_verification": {"overall": "PASS"},
            "blocked_reason": "",
        }
        result.update(overrides)
        return result

    def _fake_arch_filter_result(self, workflow_id: str = "asdw-web"):
        """テスト用のダミー AppArchFilterResult を返す。"""
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=None,
            matched_app_ids=["APP-01"],
        )

    def _run_default_self_improve_case(
        self,
        workflow_id: str,
        *,
        self_improve_skip: bool = False,
        self_improve_scope: str = "workflow",
        success_criteria: list[str] | None = None,
        goal_capture: dict | None = None,
    ) -> bool:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=False,
            self_improve_skip=self_improve_skip,
            self_improve_scope=self_improve_scope,
            self_improve_success_criteria=success_criteria or [],
            run_id=f"run-si-default-{workflow_id}",
        )
        called = {"value": False}
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(
            side_effect=lambda _pool, fn: fn()
        )

        def _fake_run_improvement_loop(**kwargs):
            called["value"] = True
            if goal_capture is not None:
                goal_capture.update(kwargs["task_goal"])
            return self._successful_si_result(kwargs.get("task_goal"))

        with tempfile.TemporaryDirectory() as hve_work_root, \
             patch.dict(os.environ, {"HVE_WORK_ROOT": hve_work_root}, clear=False), \
             patch("orchestrator.Console", return_value=unittest.mock.MagicMock()), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch(
                 "orchestrator.resolve_app_arch_scope",
                 return_value=self._fake_arch_filter_result(workflow_id),
             ), \
             patch(
                 "orchestrator.DAGExecutor",
                 side_effect=lambda *a, **k: self._FakeDAGExecutor(),
             ), \
             patch(
                 "hve.self_improve.run_improvement_loop",
                 side_effect=_fake_run_improvement_loop,
             ), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id=workflow_id,
                params={
                    "branch": "main",
                    "selected_steps": [],
                    **_declared_required_params(workflow_id),
                },
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        self.assertFalse(
            cfg.auto_self_improve,
            "workflow-specific default must not mutate the caller's config",
        )
        return called["value"]

    def test_aag_and_aagd_enable_post_dag_self_improve_by_default(self) -> None:
        for workflow_id in ("aag", "aagd"):
            with self.subTest(workflow_id=workflow_id):
                self.assertTrue(
                    self._run_default_self_improve_case(workflow_id),
                    f"{workflow_id} must enable Post-DAG Self-Improve by default",
                )

    def test_aag_and_aagd_explicit_skip_disables_default_self_improve(self) -> None:
        for workflow_id in ("aag", "aagd"):
            with self.subTest(workflow_id=workflow_id):
                self.assertFalse(
                    self._run_default_self_improve_case(
                        workflow_id,
                        self_improve_skip=True,
                    )
                )

    def test_aag_and_aagd_disabled_scope_disables_default_self_improve(self) -> None:
        for workflow_id in ("aag", "aagd"):
            with self.subTest(workflow_id=workflow_id):
                self.assertFalse(
                    self._run_default_self_improve_case(
                        workflow_id,
                        self_improve_scope="disabled",
                    )
                )

    def test_aag_and_aagd_criteria_override_preserves_definitions(self) -> None:
        for workflow_id in ("aag", "aagd"):
            with self.subTest(workflow_id=workflow_id):
                observed_goal: dict = {}
                self.assertTrue(
                    self._run_default_self_improve_case(
                        workflow_id,
                        success_criteria=["operator override"],
                        goal_capture=observed_goal,
                    )
                )
                self.assertEqual(
                    observed_goal.get("success_criteria"),
                    ["operator override"],
                )
                definitions = observed_goal.get("criterion_definitions", [])
                self.assertTrue(definitions)
                self.assertTrue(all(
                    item.get("required_for_done") is True
                    for item in definitions
                ))

    def test_non_agent_workflow_remains_disabled_by_default(self) -> None:
        from workflow_registry import list_workflows

        non_agent_workflows = [
            workflow.id
            for workflow in list_workflows()
            if workflow.id not in {"aag", "aagd"}
        ]
        self.assertTrue(non_agent_workflows)
        for workflow_id in non_agent_workflows:
            with self.subTest(workflow_id=workflow_id):
                self.assertFalse(
                    self._run_default_self_improve_case(workflow_id),
                    f"{workflow_id} must retain its disabled default",
                )

    def test_self_improve_uses_run_in_executor_and_restores_scope(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=True,
            self_improve_skip=False,
            run_id="run-si-test",
        )
        mock_console = unittest.mock.MagicMock()
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(side_effect=lambda _pool, fn: fn())
        observed_scope: dict = {}

        def _fake_run_improvement_loop(*, config, work_dir, repo_root, task_goal=None):
            observed_scope["value"] = config.self_improve_target_scope
            return self._successful_si_result(task_goal)

        with patch("orchestrator.Console", return_value=mock_console), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._fake_arch_filter_result()), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("hve.self_improve.run_improvement_loop", side_effect=_fake_run_improvement_loop), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={
                    "branch": "main",
                    "selected_steps": [],
                    **_declared_required_params("asdw-web"),
                },
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        # ASDW-WEB は固定 output_paths を持つため、scope文字列ではなく
        # _resolved_step_output_paths の具体pathを使用する。
        self.assertEqual(observed_scope.get("value"), "")
        self.assertEqual(cfg.self_improve_target_scope, "")
        fake_loop.run_in_executor.assert_awaited_once()
        self.assertEqual(
            result["self_improve_result"]["stopped_reason"],
            "no_improvement_needed",
        )
        phase_names = [call.args[2] for call in mock_console.phase_start.call_args_list]
        self.assertIn("自己改善ループ", phase_names)

    def test_self_improve_phase_inserted_before_post_process(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=True,
            self_improve_skip=False,
            create_pr=True,
            run_id="run-si-post-order",
        )
        mock_console = unittest.mock.MagicMock()
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(side_effect=lambda _pool, fn: fn())

        with patch("orchestrator.Console", return_value=mock_console), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator._git_checkout_new_branch", return_value=True), \
             patch("orchestrator._git_add_commit_push", return_value=False), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch(
                 "hve.self_improve.run_improvement_loop",
                 side_effect=lambda **kwargs: self._successful_si_result(
                     kwargs.get("task_goal")
                 ),
             ), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        phase_names = [call.args[2] for call in mock_console.phase_start.call_args_list]
        self.assertIn("自己改善ループ", phase_names)
        self.assertIn("後処理 (git push + PR)", phase_names)
        self.assertLess(
            phase_names.index("自己改善ループ"),
            phase_names.index("後処理 (git push + PR)"),
        )

    def test_self_improve_blocked_propagates_to_workflow_and_skips_push(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=True,
            self_improve_skip=False,
            create_pr=True,
            run_id="run-si-blocked",
        )
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(
            side_effect=lambda _pool, fn: fn()
        )
        blocked_result = {
            "iterations_completed": 0,
            "final_score": 100,
            "records": [],
            "stopped_reason": "blocked",
            "reward_history": [],
            "final_goal_achievement_pct": 1.0,
            "final_criterion_results": [{
                "criterion_id": "CRIT-REQUIRED",
                "required_for_done": True,
                "status": "BLOCKED",
                "evidence": [{"status": "BLOCKED"}],
            }],
            "final_verification": {"overall": "BLOCKED"},
            "blocked_reason": "required_tool_not_executed",
        }

        with patch("orchestrator.Console", return_value=unittest.mock.MagicMock()), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator._git_checkout_new_branch", return_value=True), \
             patch("orchestrator._git_add_commit_push") as mock_push, \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("hve.self_improve.run_improvement_loop", return_value=blocked_result), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        mock_push.assert_not_called()
        self.assertIn("self-improve", result.get("blocked", []))
        self.assertIn("Self-Improve", str(result.get("error", "")))
        self.assertIsNone(result.get("pr_number"))
        self.assertEqual(
            result.get("self_improve_result", {}).get("stopped_reason"),
            "blocked",
        )

    def test_self_improve_success_gate_requires_evidence_and_verification(self) -> None:
        from orchestrator import _self_improve_result_succeeded

        goal = {
            "criterion_definitions": [{
                "criterion_id": "CRIT-REQUIRED",
                "required_for_done": True,
            }],
        }
        valid = {
            "stopped_reason": "threshold_reached",
            "blocked_reason": "",
            "final_criterion_results": [{
                "criterion_id": "CRIT-REQUIRED",
                "status": "PASS",
                "evidence": [{"status": "PASS"}],
            }],
            "final_verification": {"overall": "PASS"},
        }
        self.assertTrue(_self_improve_result_succeeded(valid, goal))

        for case, overrides in (
            ("blocked-stop", {"stopped_reason": "blocked"}),
            ("missing-evidence", {"final_criterion_results": []}),
            ("failed-verification", {"final_verification": {"overall": "FAIL"}}),
            ("missing-verification", {"final_verification": None}),
            ("blocked-reason", {"blocked_reason": "scope_empty"}),
        ):
            with self.subTest(case=case):
                candidate = dict(valid)
                candidate.update(overrides)
                self.assertFalse(
                    _self_improve_result_succeeded(candidate, goal)
                )

    def test_dry_run_does_not_insert_self_improve_phase(self) -> None:
        cfg = SDKConfig(
            dry_run=True,
            quiet=True,
            auto_self_improve=True,
            self_improve_skip=False,
        )
        mock_console = unittest.mock.MagicMock()
        with patch("orchestrator.Console", return_value=mock_console):
            result = _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertTrue(result.get("dry_run"))
        phase_names = [call.args[2] for call in mock_console.phase_start.call_args_list]
        self.assertNotIn("自己改善ループ", phase_names)

    def test_self_improve_default_scope_per_workflow(self) -> None:
        # workflows で output_paths が定義済みの場合、effective_si_scope は "" となり
        # _resolved_step_output_paths にパス一覧が格納される（AAS が対象）。
        # output_paths 未定義の workflow は SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS の値を使う。
        expected_scopes = {
            "aas": "",        # output_paths 定義済み → scope="" でパス直指定
            "aad-web": "",    # Sub-7 (C-4): Step 3 で output_paths 定義済み → scope=""
            "asdw-web": "",  # 固定 output_paths 定義済み → scope=""でパス直指定
            "adfd": "",       # 固定 output_paths 定義済み → scope=""でパス直指定
            "adfdv": ".",
            "aag": "",       # output_paths 定義済み → docs/agent系をパス直指定
            "aagd": "",      # output_paths 定義済み → AAGD成果物をパス直指定
            "akm": "knowledge/",
        }
        for workflow_id, expected_scope in expected_scopes.items():
            with self.subTest(workflow_id=workflow_id):
                cfg = SDKConfig(
                    dry_run=False,
                    quiet=True,
                    no_workbench=True,
                    mdq_watch=False,
                    auto_self_improve=True,
                    self_improve_skip=False,
                    run_id=f"run-si-scope-{workflow_id}",
                )
                observed_scope: dict = {}
                fake_loop = unittest.mock.MagicMock()
                fake_loop.run_in_executor = unittest.mock.AsyncMock(side_effect=lambda _pool, fn: fn())

                def _fake_run_improvement_loop(*, config, work_dir, repo_root, task_goal=None):
                    observed_scope["value"] = config.self_improve_target_scope
                    observed_scope["resolved_paths"] = getattr(config, "_resolved_step_output_paths", None)
                    return self._successful_si_result(task_goal)

                _arch_result = self._fake_arch_filter_result(workflow_id)
                with tempfile.TemporaryDirectory() as hve_work_root, \
                     patch.dict(os.environ, {"HVE_WORK_ROOT": hve_work_root}, clear=False), \
                     patch("orchestrator.Console", return_value=unittest.mock.MagicMock()), \
                     patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
                     patch("orchestrator.resolve_app_arch_scope", return_value=_arch_result), \
                     patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
                     patch("hve.self_improve.run_improvement_loop", side_effect=_fake_run_improvement_loop), \
                     patch("asyncio.get_running_loop", return_value=fake_loop):
                    result = _run(run_workflow(
                        workflow_id=workflow_id,
                        params={
                            "branch": "main",
                            "selected_steps": [],
                            **_declared_required_params(workflow_id),
                        },
                        config=cfg,
                    ))

                self.assertIsNone(result.get("error"))
                self.assertEqual(observed_scope.get("value"), expected_scope)
                # output_paths 定義済みワークフローは _resolved_step_output_paths に非空リストが入る
                if expected_scope == "":
                    self.assertIsInstance(observed_scope.get("resolved_paths"), list)
                    self.assertGreater(len(observed_scope.get("resolved_paths") or []), 0)

    @staticmethod
    def _workflow_with_step_outputs(workflow_id: str, overrides: dict):
        """実 WorkflowDef を複製し、指定 Step の出力宣言だけ差し替える。

        `hve/workflow_registry.py` は本タスクで編集できないため、
        「将来 output_paths を宣言した状態」をテスト内のダミー定義で再現する。
        """
        import dataclasses

        from workflow_registry import get_workflow as _real_get_workflow

        wf = _real_get_workflow(workflow_id)
        assert wf is not None, workflow_id
        steps = [
            dataclasses.replace(step, **overrides[step.id])
            if step.id in overrides else step
            for step in wf.steps
        ]
        return dataclasses.replace(wf, steps=steps)

    def _capture_self_improve_scope(
        self,
        workflow_id: str,
        *,
        workflow_override=None,
    ) -> dict:
        """run_workflow を実行し Self-Improve へ渡された scope を観測する。"""
        import workflow_registry as _workflow_registry

        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=True,
            self_improve_skip=False,
            run_id=f"run-si-cover-{workflow_id}",
        )
        observed: dict = {}
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(
            side_effect=lambda _pool, fn: fn()
        )

        def _fake_run_improvement_loop(*, config, work_dir, repo_root, task_goal=None):
            observed["scope"] = config.self_improve_target_scope
            observed["resolved_paths"] = list(
                getattr(config, "_resolved_step_output_paths", None) or []
            )
            return self._successful_si_result(task_goal)

        _real_get_workflow = _workflow_registry.get_workflow

        def _patched_get_workflow(requested_id: str):
            if workflow_override is not None and requested_id == workflow_id:
                return workflow_override
            return _real_get_workflow(requested_id)

        with tempfile.TemporaryDirectory() as hve_work_root, \
             patch.dict(os.environ, {"HVE_WORK_ROOT": hve_work_root}, clear=False), \
             patch("orchestrator.Console", return_value=unittest.mock.MagicMock()), \
             patch("orchestrator.get_workflow", side_effect=_patched_get_workflow), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch(
                 "orchestrator.resolve_app_arch_scope",
                 return_value=self._fake_arch_filter_result(workflow_id),
             ), \
             patch(
                 "orchestrator.DAGExecutor",
                 side_effect=lambda *a, **k: self._FakeDAGExecutor(),
             ), \
             patch(
                 "hve.self_improve.run_improvement_loop",
                 side_effect=_fake_run_improvement_loop,
             ), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id=workflow_id,
                params={
                    "branch": "main",
                    "selected_steps": [],
                    **_declared_required_params(workflow_id),
                },
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        return observed

    def test_partial_output_paths_declaration_keeps_workflow_default_scope(self) -> None:
        """部分的な output_paths 宣言で Self-Improve scope を縮小させない。"""
        cases = {
            "adfdv": (
                ".",
                {
                    "4.1": {"output_paths": ["docs/azure/waf-review.md"]},
                    "4.2": {"output_paths": ["docs/azure/dependency-review.md"]},
                },
            ),
            "akm": (
                "knowledge/",
                {
                    "2": {
                        "output_paths": [
                            "knowledge/business-requirement-document-status.md",
                        ],
                    },
                },
            ),
        }
        for workflow_id, (expected_scope, overrides) in cases.items():
            with self.subTest(workflow_id=workflow_id):
                observed = self._capture_self_improve_scope(
                    workflow_id,
                    workflow_override=self._workflow_with_step_outputs(
                        workflow_id,
                        overrides,
                    ),
                )
                self.assertEqual(
                    observed.get("scope"),
                    expected_scope,
                    f"{workflow_id}: 部分宣言で target scope が縮小した",
                )

    def test_complete_output_paths_declaration_switches_to_path_scope(self) -> None:
        """全 root Step が宣言されたら具体 path 直指定へ切り替わる。"""
        adfdv_observed = self._capture_self_improve_scope(
            "adfdv",
            workflow_override=self._workflow_with_step_outputs(
                "adfdv",
                {
                    "1.1": {"output_paths": ["docs/azure/azure-services-data.md"]},
                    "4.1": {"output_paths": ["docs/azure/waf-review.md"]},
                    "4.2": {"output_paths": ["docs/azure/dependency-review.md"]},
                },
            ),
        )
        self.assertEqual(adfdv_observed.get("scope"), "")
        self.assertIn(
            "docs/azure/azure-services-data.md",
            adfdv_observed.get("resolved_paths") or [],
        )

        akm_observed = self._capture_self_improve_scope(
            "akm",
            workflow_override=self._workflow_with_step_outputs(
                "akm",
                {
                    "1": {
                        "output_paths_template": ["knowledge/{key}-knowledge.md"],
                    },
                    "2": {
                        "output_paths": [
                            "knowledge/business-requirement-document-status.md",
                        ],
                    },
                },
            ),
        )
        self.assertEqual(akm_observed.get("scope"), "")
        akm_paths = akm_observed.get("resolved_paths") or []
        # AKM Step 1 は fanout_static_keys D01〜D21。collector が AAG/AAGD 以外でも
        # fan-out 展開しなければ 21 件の具体 path は scope に載らない。
        for key in (f"D{n:02d}" for n in range(1, 22)):
            self.assertIn(f"knowledge/{key}-knowledge.md", akm_paths)

    def test_fanout_expansion_failure_is_not_treated_as_complete_scope(self) -> None:
        """fan-out 展開が失敗したら宣言と実 scope の不一致を許さない。"""
        from orchestrator import (
            collect_workflow_output_paths,
            workflow_output_paths_cover_workflow,
        )

        override = self._workflow_with_step_outputs(
            "aagd",
            {
                "1": {
                    "output_paths": [],
                    "output_paths_template": ["docs/agent/agent-detail-{key}.md"],
                    "fanout_parser": "agent_catalog",
                },
                "3": {"output_paths": ["docs/agent/agent-deploy-report.md"]},
            },
        )

        with tempfile.TemporaryDirectory() as repo:
            with patch("orchestrator.get_workflow", return_value=override):
                collected = collect_workflow_output_paths("aagd", repo_root=Path(repo))
                self.assertEqual(collected, ["docs/agent/agent-deploy-report.md"])
                self.assertFalse(
                    workflow_output_paths_cover_workflow("aagd", repo_root=Path(repo)),
                    "agent catalog 未生成のまま具体 path を scope として採用してはならない",
                )

        with tempfile.TemporaryDirectory() as repo:
            catalog = Path(repo, "docs/agent/agent-architecture.md")
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text("## AGT-01\n\nAgent inventory.\n", encoding="utf-8")
            with patch("orchestrator.get_workflow", return_value=override):
                collected = collect_workflow_output_paths("aagd", repo_root=Path(repo))
                self.assertIn("docs/agent/agent-detail-AGT-01.md", collected)
                self.assertTrue(
                    workflow_output_paths_cover_workflow("aagd", repo_root=Path(repo))
                )

    def test_declared_workflows_keep_path_directed_scope(self) -> None:
        """既存の宣言済み workflow は従来どおり具体 path 直指定を維持する。"""
        from orchestrator import workflow_output_paths_cover_workflow

        repo_root = Path(__file__).resolve().parent.parent.parent
        for workflow_id in ("aas", "aad-web", "asdw-web", "adfd", "aag", "aagd"):
            with self.subTest(workflow_id=workflow_id, covered=True):
                self.assertTrue(
                    workflow_output_paths_cover_workflow(
                        workflow_id,
                        repo_root=repo_root,
                    )
                )
        for workflow_id in ("adfdv", "akm"):
            with self.subTest(workflow_id=workflow_id, covered=False):
                self.assertFalse(
                    workflow_output_paths_cover_workflow(
                        workflow_id,
                        repo_root=repo_root,
                    )
                )

        for workflow_id in ("aas", "asdw-web", "aag"):
            with self.subTest(workflow_id=workflow_id, end_to_end=True):
                observed = self._capture_self_improve_scope(workflow_id)
                self.assertEqual(observed.get("scope"), "")
                self.assertTrue(observed.get("resolved_paths"))

    def test_aag_and_aagd_self_improve_scope_contains_declared_capability_artifacts(self) -> None:
        """Sub-17 RED: collectorは実在fan-out成果物を具体pathで返す。"""
        from orchestrator import collect_workflow_output_paths

        signature = inspect.signature(collect_workflow_output_paths)
        self.assertIn(
            "repo_root",
            signature.parameters,
            "collector must accept repo_root without relying on process CWD",
        )

        with tempfile.TemporaryDirectory() as repo:
            agent_key = "AG-01"
            concrete = {
                "aag": {
                    "docs/agent/agent-application-definition.md",
                    "docs/agent/agent-architecture.md",
                    "docs/ai-agent-catalog.md",
                    f"docs/agent/agent-detail-{agent_key}.md",
                },
                "aagd": {
                    "docs/agent/agent-application-definition.md",
                    f"docs/test-specs/{agent_key}-test-spec.md",
                    f"src/test/agent/{agent_key}.Tests",
                    f"src/agent/{agent_key}",
                    f"docs/agent/tool-search-eval/{agent_key}-eval-report.md",
                },
            }
            catalog = Path(
                repo,
                "docs/agent/agent-application-definition.md",
            )
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text(
                f"## {agent_key}\n\nAgent catalog fixture.\n",
                encoding="utf-8",
            )
            for paths in concrete.values():
                for relative in paths:
                    path = Path(repo, relative)
                    if relative.startswith(("src/agent/", "src/test/agent/")):
                        path.mkdir(parents=True, exist_ok=True)
                    elif not path.exists():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("test", encoding="utf-8")

            for workflow_id, expected_paths in concrete.items():
                with self.subTest(workflow_id=workflow_id):
                    actual = set(collect_workflow_output_paths(
                        workflow_id,
                        repo_root=Path(repo),
                    ))
                    self.assertEqual(
                        actual,
                        expected_paths,
                        f"{workflow_id} Self-Improve scope must exactly match "
                        "the concrete paths declared by StepDef outputs",
                    )
                    self.assertFalse(
                        any("{" in path or "}" in path for path in actual),
                        actual,
                    )

    def test_agent_fanout_scope_precondition_requires_concrete_artifacts(self) -> None:
        from orchestrator import _agent_fanout_scope_precondition_error

        key = "AGT-01"
        with tempfile.TemporaryDirectory() as repo:
            root = Path(repo)
            aag_paths = [
                "docs/agent/agent-application-definition.md",
                "docs/agent/agent-architecture.md",
                "docs/ai-agent-catalog.md",
                f"docs/agent/agent-detail-{key}.md",
            ]
            self.assertIn(
                "required_agent_fanout_incomplete",
                _agent_fanout_scope_precondition_error("aag", aag_paths, root),
            )
            for relative in aag_paths:
                artifact = root / relative
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text("# Artifact\n", encoding="utf-8")
            self.assertEqual(
                _agent_fanout_scope_precondition_error("aag", aag_paths, root),
                "",
            )

            aagd_paths = [
                "docs/agent/agent-application-definition.md",
                f"docs/test-specs/{key}-test-spec.md",
                f"src/test/agent/{key}.Tests",
                f"src/agent/{key}",
            ]
            self.assertIn(
                "required_agent_fanout_incomplete",
                _agent_fanout_scope_precondition_error("aagd", aagd_paths, root),
            )
            spec = root / f"docs/test-specs/{key}-test-spec.md"
            spec.parent.mkdir(parents=True, exist_ok=True)
            spec.write_text("# Test Spec\n", encoding="utf-8")
            (root / f"src/test/agent/{key}.Tests").mkdir(parents=True)
            (root / f"src/agent/{key}").mkdir(parents=True)
            self.assertEqual(
                _agent_fanout_scope_precondition_error("aagd", aagd_paths, root),
                "",
            )

            with patch(
                "self_improve._path_has_symlink_component",
                return_value=True,
            ):
                self.assertIn(
                    "required_agent_fanout_incomplete",
                    _agent_fanout_scope_precondition_error(
                        "aag",
                        aag_paths,
                        root,
                    ),
                )

            second = "AGT-02"
            incomplete_paths = [
                *aagd_paths,
                f"docs/test-specs/{second}-test-spec.md",
                f"src/test/agent/{second}.Tests",
                f"src/agent/{second}",
            ]
            (root / f"docs/test-specs/{second}-test-spec.md").write_text(
                "# Test Spec\n",
                encoding="utf-8",
            )
            (root / f"src/test/agent/{second}.Tests").mkdir(parents=True)
            error = _agent_fanout_scope_precondition_error(
                "aagd",
                incomplete_paths,
                root,
            )
            self.assertIn("required_agent_fanout_incomplete", error)
            self.assertIn(f"src/agent/{second}", error)


class TestRunWorkflowSelfImproveScope(unittest.TestCase):
    """run_workflow の Self-Improve scope 制御テスト。"""

    class _FakeDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = set()
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {"completed": [], "failed": [], "skipped": []}

    def _fake_arch_filter_result(self, workflow_id: str = "aas"):
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=None,
            matched_app_ids=["APP-01"],
        )

    def _run_with_scope(self, scope: str, workflow_id: str = "aas"):
        """指定 scope で run_workflow を実行し (si_called, phase_names) を返す。"""
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            no_workbench=True,
            mdq_watch=False,
            auto_self_improve=True,
            self_improve_skip=False,
            run_id=f"run-scope-{scope or 'default'}-{workflow_id}",
            self_improve_scope=scope,
        )
        si_called = {"value": False}
        fake_loop = unittest.mock.MagicMock()
        fake_loop.run_in_executor = unittest.mock.AsyncMock(
            side_effect=lambda _pool, fn: (si_called.__setitem__("value", True) or None) or fn()
        )

        def _fake_run_improvement_loop(*, config, work_dir, repo_root, **kwargs):
            si_called["value"] = True
            return {
                "iterations_completed": 0,
                "final_score": 100,
                "stopped_reason": "no_improvement_needed",
                "records": [],
                "reward_history": [],
                "final_goal_achievement_pct": 1.0,
                "final_criterion_results": [],
                "final_verification": {"overall": "PASS"},
                "blocked_reason": "",
            }

        mock_console = unittest.mock.MagicMock()
        with patch("orchestrator.Console", return_value=mock_console), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope",
                   return_value=self._fake_arch_filter_result(workflow_id)), \
             patch("orchestrator.DAGExecutor",
                   side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("hve.self_improve.run_improvement_loop",
                   side_effect=_fake_run_improvement_loop), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id=workflow_id,
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        phase_names = [call.args[2] for call in mock_console.phase_start.call_args_list]
        return si_called["value"], phase_names

    def test_scope_workflow_runs_post_dag(self) -> None:
        """scope='workflow' のとき Post-DAG Self-Improve が実行される。"""
        si_called, phase_names = self._run_with_scope("workflow")
        self.assertTrue(si_called, "Post-DAG Self-Improve が呼ばれること")
        self.assertIn("自己改善ループ", phase_names)

    def test_scope_step_skips_post_dag(self) -> None:
        """scope='step' のとき Post-DAG Self-Improve はスキップされる。"""
        si_called, phase_names = self._run_with_scope("step")
        self.assertFalse(si_called, "Post-DAG Self-Improve が呼ばれないこと")
        self.assertNotIn("自己改善ループ", phase_names)

    def test_scope_disabled_skips_post_dag(self) -> None:
        """scope='disabled' のとき Post-DAG Self-Improve はスキップされる。"""
        si_called, phase_names = self._run_with_scope("disabled")
        self.assertFalse(si_called, "Post-DAG Self-Improve が呼ばれないこと")
        self.assertNotIn("自己改善ループ", phase_names)

    def test_scope_empty_runs_post_dag_backward_compat(self) -> None:
        """scope='' (後方互換値) のとき Post-DAG Self-Improve が実行される。
        Wave 2 以降のデフォルトは 'workflow' だが、'' を明示指定した場合は後方互換で動作する。"""
        si_called, phase_names = self._run_with_scope("")
        self.assertTrue(si_called, "後方互換: Post-DAG Self-Improve が呼ばれること")
        self.assertIn("自己改善ループ", phase_names)



    """_collect_params_non_interactive() の AKM デフォルト適用テスト。"""

    def _make_wf(self):
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "akm"
        return wf

    def test_defaults_applied_when_akm_params_not_specified(self) -> None:
        """AKM で sources/target_files/force_refresh 未指定時は既定値が適用されることを確認。

        Work IQ 入力対応に伴い、既定 sources は ``qa,original-docs`` のマルチ値、
        target_files は空（複数 non-workiq ソースのため単一パターンなし）となる。
        force_refresh の既定は False（差分マージ）。
        """
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {"branch": "main"}
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params["sources"], "qa,original-docs")
        self.assertEqual(params["target_files"], "")
        self.assertFalse(params["force_refresh"])

    def test_sources_value_passthrough(self) -> None:
        """AKM で sources=qa/original-docs/both が正規化形式で反映されることを確認。

        後方互換: ``both`` は ``qa,original-docs`` に正規化される。
        単一値は正規化後もそのまま維持される。
        """
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        expected = {
            "qa": "qa",
            "original-docs": "original-docs",
            "both": "qa,original-docs",
        }
        for sources, expected_value in expected.items():
            with self.subTest(sources=sources):
                params = _collect_params_non_interactive(wf, {"branch": "main", "sources": sources})
                self.assertEqual(params["sources"], expected_value)

    def test_force_refresh_false_overrides_default(self) -> None:
        """AKM で force_refresh=False が明示された場合は False が反映されることを確認（既定も False）。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {"branch": "main", "force_refresh": False}
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertFalse(params["force_refresh"])

    def test_force_refresh_true_overrides_default(self) -> None:
        """AKM で force_refresh=True が明示された場合は True が既定 (False) を上書きすることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {"branch": "main", "force_refresh": True}
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertTrue(params["force_refresh"])


class TestCollectParamsNonInteractiveAqodDefaults(unittest.TestCase):
    """_collect_params_non_interactive() の AQOD デフォルト適用テスト。"""

    def _make_wf(self):
        from unittest.mock import MagicMock
        wf = MagicMock()
        wf.id = "aqod"
        return wf

    def test_defaults_applied_when_aqod_params_not_specified(self) -> None:
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        params = _collect_params_non_interactive(wf, {"branch": "main"})
        self.assertEqual(params["target_scope"], "original-docs/")
        self.assertEqual(params["depth"], "standard")
        self.assertEqual(params["focus_areas"], "")

    def test_custom_values_passthrough(self) -> None:
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        params = _collect_params_non_interactive(
            wf,
            {
                "branch": "main",
                "target_scope": "original-docs/sub/",
                "depth": "lightweight",
                "focus_areas": "冪等性",
            },
        )
        self.assertEqual(params["target_scope"], "original-docs/sub/")
        self.assertEqual(params["depth"], "lightweight")
        self.assertEqual(params["focus_areas"], "冪等性")


class TestAppArchFilterInOrchestrator(unittest.TestCase):
    """run_workflow の app-arch filter 統合テスト。"""

    class _FakeDAGExecutor:
        def __init__(self, *args, **kwargs):
            self.completed = set()
            self.failed = set()
            self.skipped = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {"completed": [], "failed": [], "skipped": []}

    def _web_result(self, workflow_id: str = "aad-web"):
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=None,
            matched_app_ids=["APP-01"],
        )

    def _batch_result(self, workflow_id: str = "adfd"):
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="batch",
            target_architectures=["データデータフロー処理"],
            requested_app_ids=None,
            matched_app_ids=["APP-02"],
        )

    def _empty_result(self, workflow_id: str = "aad-web"):
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=["APP-02"],
            matched_app_ids=[],
        )

    def test_aad_web_runs_arch_filter(self) -> None:
        """aad-web ワークフローで DAG 実行前に app-arch filter が走ること。"""
        cfg = SDKConfig(dry_run=False, quiet=True)
        _called_with: dict = {}

        def _fake_filter(workflow_id, requested_app_ids=None, catalog_path=None, dry_run=False):
            _called_with["workflow_id"] = workflow_id
            return self._web_result(workflow_id)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", side_effect=_fake_filter), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()):
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertEqual(_called_with.get("workflow_id"), "aad-web")
        self.assertIsNone(result.get("error"))

    def test_asdw_web_rejects_direct_app_scope_mismatch_before_filter_or_runner(self) -> None:
        cfg = SDKConfig(dry_run=False, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope") as mock_filter, \
             patch("orchestrator.StepRunner") as mock_runner:
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={
                    "branch": "main",
                    "selected_steps": ["1.3"],
                    "app_ids": ["APP-009"],
                    "app_id": "APP-010",
                    "resource_group": "test-resource-group",
                },
                config=cfg,
            ))

        self.assertIn("--app-id to match", result["error"])
        mock_filter.assert_not_called()
        mock_runner.assert_not_called()

    def test_abd_batch_app_ids_only(self) -> None:
        """adfd ワークフローで Batch APP のみ対象になること。"""
        cfg = SDKConfig(dry_run=False, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._batch_result("adfd")), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()):
            result = _run(run_workflow(
                workflow_id="adfd",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        self.assertIsNone(result.get("skipped_reason"))

    def test_zero_match_no_dag_execution(self) -> None:
        """対象 0 件時に DAGExecutor が呼ばれないこと。"""
        cfg = SDKConfig(dry_run=False, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._empty_result()), \
             patch("orchestrator.DAGExecutor") as mock_dag:
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        mock_dag.assert_not_called()
        self.assertEqual(result.get("skipped_reason"), "対象アーキテクチャに一致する APP-ID がありません")
        self.assertEqual(result.get("completed"), [])
        self.assertEqual(result.get("failed"), [])
        self.assertEqual(result.get("skipped"), [])

    def test_catalog_missing_non_dry_run_returns_error(self) -> None:
        """catalog 不在 + 非 dry-run は error を返すこと。"""
        cfg = SDKConfig(dry_run=False, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", side_effect=FileNotFoundError("catalog not found")), \
             patch("orchestrator.DAGExecutor") as mock_dag:
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        mock_dag.assert_not_called()
        self.assertIn("error", result)

    def test_catalog_missing_dry_run_continues(self) -> None:
        """catalog 不在 + dry-run は warning 継続（スキップしないこと）。"""
        from hve.app_arch_filter import AppArchFilterResult
        cfg = SDKConfig(dry_run=True, quiet=True)
        # catalog_found=False: カタログ不在時に dry_run=True で返す空結果
        _missing = AppArchFilterResult(
            workflow_id="aad-web",
            target_kind="web-cloud",
            target_architectures=["Webフロントエンド + クラウド"],
            requested_app_ids=None,
            matched_app_ids=[],
            catalog_found=False,
        )

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=_missing), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("orchestrator.Console", return_value=unittest.mock.MagicMock()):
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        # dry_run=True では正常終了扱い（0件スキップではなく通常実行継続）
        self.assertTrue(result.get("dry_run"))
        self.assertIsNone(result.get("error"))

    def test_zero_match_dry_run_is_success(self) -> None:
        """対象 0 件 + dry-run は成功扱いになること（dry_run キーが True で返ること）。"""
        cfg = SDKConfig(dry_run=True, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._empty_result()), \
             patch("orchestrator.DAGExecutor") as mock_dag:
            result = _run(run_workflow(
                workflow_id="aad-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        # エラーではなく skipped_reason が設定される
        self.assertNotIn("error", result)
        self.assertEqual(result.get("skipped_reason"), "対象アーキテクチャに一致する APP-ID がありません")
        self.assertTrue(result.get("dry_run"))
        mock_dag.assert_not_called()


class TestPrefetchWorkIQDetailed(unittest.TestCase):
    """Phase 4: _prefetch_workiq_detailed() のテスト。"""

    def test_returns_empty_result_when_sdk_missing(self) -> None:
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True)
        console = unittest.mock.Mock()
        with patch.dict(sys.modules, {"copilot": None}):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))
        self.assertEqual(result.content, "")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "sdk_import_failure")
        console.warning.assert_called_once()

    def test_returns_success_result_when_tool_called(self) -> None:
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()
                self._handlers: list = []

            def on(self, handler):
                self._handlers.append(handler)

            def _fire_tool_event(self, tool_name: str) -> None:
                """登録済みハンドラーに tool.execution_start イベントを送る。"""
                event = types.SimpleNamespace(
                    type=types.SimpleNamespace(value="tool.execution_start"),
                    data=types.SimpleNamespace(
                        mcp_tool_name=tool_name,
                        mcp_server_name="_hve_workiq",
                    ),
                )
                for h in self._handlers:
                    h(event)

            async def disconnect(self):
                return None

        _session_ref: list = []

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                s = _FakeSession()
                _session_ref.append(s)
                return s

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        async def _fake_query_workiq(session, query, timeout=120.0):
            # ツール呼び出しイベントをシミュレートしてから結果を返す
            if _session_ref:
                _session_ref[0]._fire_tool_event("ask_work_iq")
            return "m365 context"

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}), \
                patch("workiq.query_workiq", new=_fake_query_workiq):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))

        self.assertEqual(result.content, "m365 context")
        self.assertTrue(result.success)
        self.assertTrue(result.tool_called)
        self.assertTrue(result.safe_to_inject)
        self.assertEqual(result.result_source, "tool_execution")
        self.assertTrue(result.mcp_server_found)
        self.assertEqual(result.mcp_status, "connected")

    def test_returns_mcp_not_connected_result(self) -> None:
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "disconnected"
                    error = "connection failed"

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            def on(self, handler):
                pass

            async def disconnect(self):
                return None

        class _FakeClient:
            async def start(self): return None
            async def stop(self): return None
            async def create_session(self, **kwargs): return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs): return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))

        self.assertEqual(result.content, "")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "mcp_not_connected")
        self.assertTrue(result.mcp_server_found)
        self.assertEqual(result.mcp_status, "disconnected")
        console.warning.assert_called()

    def test_returns_mcp_not_found_result(self) -> None:
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "other-server"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            def on(self, handler):
                pass

            async def disconnect(self): return None

        class _FakeClient:
            async def start(self): return None
            async def stop(self): return None
            async def create_session(self, **kwargs): return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs): return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))

        self.assertEqual(result.content, "")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "mcp_not_found")
        self.assertFalse(result.mcp_server_found)
        console.warning.assert_called()

    def test_backward_compatible_prefetch_workiq_returns_str(self) -> None:
        """後方互換ラッパー _prefetch_workiq() が str を返すことを確認。"""
        from orchestrator import _prefetch_workiq

        cfg = SDKConfig(dry_run=True)
        console = unittest.mock.Mock()
        with patch.dict(sys.modules, {"copilot": None}):
            result = _run(_prefetch_workiq(cfg, "query", console, timeout=1))
        self.assertIsInstance(result, str)
        self.assertEqual(result, "")

    def test_tool_not_invoked_returns_error_type(self) -> None:
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            def on(self, handler):
                pass

            async def disconnect(self): return None

        class _FakeClient:
            async def start(self): return None
            async def stop(self): return None
            async def create_session(self, **kwargs): return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs): return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}), \
                patch("workiq.query_workiq", new=unittest.mock.AsyncMock(return_value="")):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))

        # ツール未呼び出し + 空結果 → tool_not_invoked
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "tool_not_invoked")
        self.assertFalse(result.tool_called)

    def test_tool_not_invoked_but_llm_text_returned_is_not_safe_to_inject(self) -> None:
        """MCP connected, send_and_wait が非空テキストを返すが tool.execution_start が発火しない場合:
        - tool_called=False
        - safe_to_inject=False
        - result_source="llm_text"
        - enrich_prompt_with_workiq() が呼ばれない（上位処理で安全注入されない）
        """
        from orchestrator import _prefetch_workiq_detailed

        cfg = SDKConfig(dry_run=True, model="gpt-4.1")
        console = unittest.mock.Mock()

        class _FakeSession:
            def __init__(self) -> None:
                class _Srv:
                    name = "_hve_workiq"
                    status = "connected"
                    error = None

                class _Mcp:
                    async def list(self):
                        return types.SimpleNamespace(servers=[_Srv()])

                class _Rpc:
                    mcp = _Mcp()

                self.rpc = _Rpc()

            def on(self, handler):
                # イベントハンドラーを登録するが、ツールイベントは発火しない
                pass

            async def disconnect(self): return None

        class _FakeClient:
            async def start(self): return None
            async def stop(self): return None
            async def create_session(self, **kwargs): return _FakeSession()

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()
        fake_copilot.ExternalServerConfig = lambda **kwargs: object()

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs): return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        # MCP connected + send_and_wait は非空テキストを返すが tool event は発火しない
        llm_text = "Work IQ に接続できました。関連情報はありません。"
        with patch.dict(sys.modules, {"copilot": fake_copilot, "copilot.session": fake_copilot_session}), \
                patch("workiq.build_workiq_mcp_config", return_value={"_hve_workiq": {}}), \
                patch("workiq.query_workiq", new=unittest.mock.AsyncMock(return_value=llm_text)):
            result = _run(_prefetch_workiq_detailed(cfg, "query", console, timeout=1))

        # tool.execution_start が未観測 → safe_to_inject=False
        self.assertFalse(result.tool_called)
        self.assertFalse(result.safe_to_inject)
        self.assertEqual(result.result_source, "llm_text")
        self.assertEqual(result.error_type, "tool_not_invoked")
        # content は保持されるが注入しない
        self.assertEqual(result.content, llm_text)
        # 上位処理では safe_to_inject=False なのでプロンプト注入しない。
        console.warning.assert_called()


if __name__ == "__main__":
    unittest.main()
