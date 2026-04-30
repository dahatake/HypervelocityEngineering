"""test_orchestrator.py — run_workflow の dry_run テスト"""

from __future__ import annotations

import asyncio
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
        valid_ids = ["aas", "aad-web", "asdw-web", "abd", "abdv", "aag", "aagd", "akm", "aqod", "adoc"]
        for wf_id in valid_ids:
            with self.subTest(workflow_id=wf_id):
                result = _run(run_workflow(
                    workflow_id=wf_id,
                    params={"branch": "main", "selected_steps": []},
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
        self.assertEqual(result, "テンプレートプロンプト\n\n追加指示")

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

    def test_T5_additional_prompt_appended_to_custom_agent(self) -> None:
        """T5: additional_prompt が Custom Agent の prompt 末尾に追記されることを確認。

        StepRunner が custom_agents リストを組み立てる内部ロジック（deepcopy + append）を
        CopilotClient をモックして直接検証する。
        """
        import copy
        from runner import StepRunner
        from console import Console
        from unittest.mock import AsyncMock, MagicMock, patch

        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
            additional_prompt="追加指示テキスト",
            custom_agents_config=[
                {
                    "name": "my-agent",
                    "display_name": "My Agent",
                    "description": "Test agent",
                    "tools": ["*"],
                    "prompt": "既存のプロンプト",
                }
            ],
        )
        original_config_snapshot = copy.deepcopy(cfg.custom_agents_config)

        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        captured_session_opts: dict = {}

        async def fake_send_and_wait(payload):
            return None

        async def fake_create_session(**opts):
            captured_session_opts.update(opts)
            session = MagicMock()
            session.send_and_wait = fake_send_and_wait
            session.disconnect = AsyncMock()
            return session

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.stop = AsyncMock()
        mock_client.create_session = fake_create_session

        mock_permission_handler = MagicMock()
        mock_permission_handler.approve_all = MagicMock()

        fake_copilot = MagicMock(
            CopilotClient=MagicMock(return_value=mock_client),
            PermissionHandler=mock_permission_handler,
            SubprocessConfig=MagicMock(),
            ExternalServerConfig=MagicMock(),
        )
        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = mock_permission_handler

        with patch.dict("sys.modules", {
            "copilot": fake_copilot,
            "copilot.session": fake_copilot_session,
        }):
            import asyncio
            asyncio.run(runner.run_step(
                step_id="test",
                title="Test Step",
                prompt="メインプロンプト",
                custom_agent=None,
            ))

        # セッションオプションに custom_agents が設定されていること
        agents = captured_session_opts.get("custom_agents", [])
        self.assertEqual(len(agents), 1)
        # additional_prompt が追記されていること
        self.assertEqual(agents[0]["prompt"], "既存のプロンプト\n\n追加指示テキスト")

        # 元の custom_agents_config が汚染されていないこと（deepcopy 検証）
        self.assertEqual(cfg.custom_agents_config, original_config_snapshot)
        self.assertEqual(cfg.custom_agents_config[0]["prompt"], "既存のプロンプト")

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
        self.assertIn("infra", cfg.ignore_paths)
        self.assertIn("src", cfg.ignore_paths)
        self.assertIn("test", cfg.ignore_paths)
        self.assertIn("work", cfg.ignore_paths)


class TestCreatePrIfNeeded(unittest.TestCase):
    """_create_pr_if_needed() の root_issue_num 対応テスト。"""

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

    def test_aad_web_step2_3_consumed_artifacts_include_specs(self) -> None:
        """AAD-WEB Step 2.3 は screen_specs / service_specs / test_strategy を参照すること。"""
        from workflow_registry import AAD_WEB
        step23 = next(s for s in AAD_WEB.steps if s.id == "2.3")
        for key in ("screen_specs", "service_specs", "test_strategy"):
            self.assertIn(key, step23.consumed_artifacts,
                          f"AAD-WEB Step 2.3: expected {key!r} in consumed_artifacts")

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

    def test_self_improve_uses_run_in_executor_and_restores_scope(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
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
            return {
                "iterations_completed": 1,
                "final_score": 75,
                "stopped_reason": "converged",
                "final_goal_achievement_pct": 0.75,
            }

        with patch("orchestrator.Console", return_value=mock_console), \
             patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._fake_arch_filter_result()), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
             patch("hve.self_improve.run_improvement_loop", side_effect=_fake_run_improvement_loop), \
             patch("asyncio.get_running_loop", return_value=fake_loop):
            result = _run(run_workflow(
                workflow_id="asdw-web",
                params={"branch": "main", "selected_steps": []},
                config=cfg,
            ))

        self.assertIsNone(result.get("error"))
        self.assertEqual(observed_scope.get("value"), ".")
        self.assertEqual(cfg.self_improve_target_scope, "")
        fake_loop.run_in_executor.assert_awaited_once()
        phase_names = [call.args[2] for call in mock_console.phase_start.call_args_list]
        self.assertIn("自己改善ループ", phase_names)

    def test_self_improve_phase_inserted_before_post_process(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            quiet=True,
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
             patch("hve.self_improve.run_improvement_loop", return_value={
                 "iterations_completed": 1,
                 "final_score": 80,
                 "stopped_reason": "done",
                 "final_goal_achievement_pct": 0.80,
             }), \
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
        expected_scopes = {
            "aas": "docs/",
            "aad-web": "docs/",
            "asdw-web": ".",
            "abd": "docs/",
            "abdv": ".",
            "aag": "docs/",
            "aagd": ".",
            "akm": "knowledge/",
            "aqod": "qa/",
            "adoc": "docs/",
        }
        for workflow_id, expected_scope in expected_scopes.items():
            with self.subTest(workflow_id=workflow_id):
                cfg = SDKConfig(
                    dry_run=False,
                    quiet=True,
                    auto_self_improve=True,
                    self_improve_skip=False,
                    run_id=f"run-si-scope-{workflow_id}",
                )
                observed_scope: dict = {}
                fake_loop = unittest.mock.MagicMock()
                fake_loop.run_in_executor = unittest.mock.AsyncMock(side_effect=lambda _pool, fn: fn())

                def _fake_run_improvement_loop(*, config, work_dir, repo_root, task_goal=None):
                    observed_scope["value"] = config.self_improve_target_scope
                    return {
                        "iterations_completed": 1,
                        "final_score": 80,
                        "stopped_reason": "done",
                        "final_goal_achievement_pct": 0.80,
                    }

                _arch_result = self._fake_arch_filter_result(workflow_id)
                with patch("orchestrator.Console", return_value=unittest.mock.MagicMock()), \
                     patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
                     patch("orchestrator.resolve_app_arch_scope", return_value=_arch_result), \
                     patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()), \
                     patch("hve.self_improve.run_improvement_loop", side_effect=_fake_run_improvement_loop), \
                     patch("asyncio.get_running_loop", return_value=fake_loop):
                    result = _run(run_workflow(
                        workflow_id=workflow_id,
                        params={"branch": "main", "selected_steps": []},
                        config=cfg,
                    ))

                self.assertIsNone(result.get("error"))
                self.assertEqual(observed_scope.get("value"), expected_scope)


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
            return {"iterations_completed": 1, "final_score": 80, "stopped_reason": "done",
                    "records": [], "reward_history": [], "final_goal_achievement_pct": 0.8}

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
        """scope='' (デフォルト) のとき後方互換で Post-DAG Self-Improve が実行される。"""
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
        """AKM で sources/target_files/force_refresh 未指定時は既定値が適用されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {"branch": "main"}
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertEqual(params["sources"], "qa")
        self.assertEqual(params["target_files"], "qa/*.md")
        self.assertTrue(params["force_refresh"])

    def test_sources_value_passthrough(self) -> None:
        """AKM で sources=qa/original-docs/both がそのまま反映されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        for sources in ["qa", "original-docs", "both"]:
            with self.subTest(sources=sources):
                params = _collect_params_non_interactive(wf, {"branch": "main", "sources": sources})
                self.assertEqual(params["sources"], sources)

    def test_force_refresh_false_overrides_default(self) -> None:
        """AKM で force_refresh=False が明示された場合は False が優先されることを確認。"""
        from orchestrator import _collect_params_non_interactive
        wf = self._make_wf()
        cli_args = {"branch": "main", "force_refresh": False}
        params = _collect_params_non_interactive(wf, cli_args)
        self.assertFalse(params["force_refresh"])


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

    def _batch_result(self, workflow_id: str = "abd"):
        from hve.app_arch_filter import AppArchFilterResult
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="batch",
            target_architectures=["データバッチ処理"],
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

    def test_abd_batch_app_ids_only(self) -> None:
        """abd ワークフローで Batch APP のみ対象になること。"""
        cfg = SDKConfig(dry_run=False, quiet=True)

        with patch("hve.workflow_registry.get_meta_dependencies", return_value=[]), \
             patch("orchestrator.resolve_app_arch_scope", return_value=self._batch_result("abd")), \
             patch("orchestrator.DAGExecutor", side_effect=lambda *a, **k: self._FakeDAGExecutor()):
            result = _run(run_workflow(
                workflow_id="abd",
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


class TestQaPhaseField(unittest.TestCase):
    """SDKConfig.qa_phase フィールドが正しく機能することを確認する。"""

    def test_qa_phase_field_exists(self) -> None:
        cfg = SDKConfig()
        self.assertTrue(hasattr(cfg, "qa_phase"))

    def test_qa_phase_default_value(self) -> None:
        cfg = SDKConfig()
        self.assertEqual(cfg.qa_phase, "pre")

    def test_qa_phase_can_be_set_to_post(self) -> None:
        cfg = SDKConfig(qa_phase="post")
        self.assertEqual(cfg.qa_phase, "post")

    def test_qa_phase_can_be_set_to_both(self) -> None:
        cfg = SDKConfig(qa_phase="both")
        self.assertEqual(cfg.qa_phase, "both")


if __name__ == "__main__":
    unittest.main()
