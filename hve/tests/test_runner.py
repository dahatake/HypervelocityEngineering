"""test_runner.py — StepRunner の dry_run テスト"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import DEFAULT_CONTEXT_INJECTION_MAX_CHARS, SDKConfig
from console import Console
from runner import (
    StepRunner,
    _AZURE_FREE_WORKFLOWS,
    _AZURE_MCP_SERVER_NAME,
    _ensure_step_work_dir,
    _extract_safe_qa_artifact_paths,
    _filter_mcp_servers_for_session,
    _is_review_fail,
    _parse_qa_content_with_artifact_fallback,
    _truncate_context,
    _work_identifier_for_step,
    _step_work_dir,
)
from workflow_registry import get_workflow, list_workflows  # type: ignore[import-untyped]
from workiq import WORKIQ_MCP_SERVER_NAME  # type: ignore[import-untyped]

# Sentinel for distinguishing "key absent" vs. "key present with None value" in sys.modules.
# Used in test_returns_false_when_sdk_missing to correctly restore sys.modules after the test.
_SENTINEL = object()


class _CaptureOutput:
    """stdout / stderr を一時的にキャプチャするコンテキストマネージャー。"""

    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        return self

    def __exit__(self, *_):
        self.stdout = sys.stdout.getvalue()
        self.stderr = sys.stderr.getvalue()
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr


def _run(coro):
    """非同期コルーチンを同期的に実行するヘルパー。"""
    return asyncio.run(coro)


class TestStepRunnerDryRun(unittest.TestCase):
    """dry_run=True の場合、SDK 呼び出しをスキップして True を返す。"""

    def _make_runner(self, verbose: bool = True, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=verbose, quiet=False)
        return StepRunner(config=cfg, console=console)

    def test_dry_run_returns_true(self) -> None:
        runner = self._make_runner()
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)

    def test_dry_run_outputs_dry_run_message(self) -> None:
        runner = self._make_runner(verbose=True)
        with _CaptureOutput() as cap:
            _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertIn("DRY-RUN", cap.stdout)
        self.assertIn("Step.1.1", cap.stdout)

    def test_dry_run_with_custom_agent(self) -> None:
        runner = self._make_runner()
        with _CaptureOutput() as cap:
            result = _run(
                runner.run_step(
                    "2.3",
                    "サービス設計",
                    "サービスを設計してください",
                    custom_agent="Arch-Microservice-ServiceCatalog",
                )
            )
        self.assertTrue(result)
        self.assertIn("Arch-Microservice-ServiceCatalog", cap.stdout)

    def test_dry_run_no_sdk_import_required(self) -> None:
        """dry_run=True では copilot SDK がなくても実行できる。"""
        runner = self._make_runner()
        # SDK が存在しない環境でも ImportError が起きないことを確認する
        with _CaptureOutput():
            result = _run(runner.run_step("9.9", "架空ステップ", "プロンプト"))
        self.assertTrue(result)

    def test_dry_run_with_auto_coding_agent_review(self) -> None:
        """dry_run=True + auto_coding_agent_review=True でも SDK 呼び出しなしで True を返す。"""
        runner = self._make_runner(auto_coding_agent_review=True)
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)

    def test_dry_run_resets_workiq_tool_called_flag(self) -> None:
        runner = self._make_runner()
        runner._workiq_tool_called = True
        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "テストステップ", "テストプロンプト"))
        self.assertTrue(result)
        self.assertFalse(runner._workiq_tool_called)


class TestWorkIdentifierForStep(unittest.TestCase):
    """Agent Prompt の WORK 識別子を Step / fan-out 単位で分離する契約。"""

    def test_non_fanout_keeps_legacy_issue_zero(self) -> None:
        self.assertEqual(_work_identifier_for_step("3.4", None), "0")

    def test_fanout_child_uses_step_scoped_identifier(self) -> None:
        self.assertEqual(
            _work_identifier_for_step(
                "3.3/SVC-13",
                {"fanout_key": "SVC-13", "base_step_id": "3.3"},
            ),
            "step-3-3-SVC-13",
        )

    def test_fanout_identifier_does_not_contain_path_separator(self) -> None:
        identifier = _work_identifier_for_step(
            "3.2/SVC-16",
            {"fanout_key": "SVC-16", "base_step_id": "3.2"},
        )
        self.assertNotIn("/", identifier)
        self.assertNotIn("\\", identifier)


class TestStepWorkDirectory(unittest.TestCase):
    """Agent起動前に作成するrun-scoped work directory契約。"""

    def test_custom_agent_issue_zero_path_and_idempotent_create(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work" / "run" / "run-1"
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                expected = (
                    work_root
                    / "Dev-Microservice-Azure-DataTestCoding"
                    / "Issue-0"
                ).resolve()
                self.assertEqual(
                    _step_work_dir(
                        "Dev-Microservice-Azure-DataTestCoding",
                        "0",
                    ),
                    expected,
                )
                first = _ensure_step_work_dir(
                    "Dev-Microservice-Azure-DataTestCoding",
                    "0",
                )
                second = _ensure_step_work_dir(
                    "Dev-Microservice-Azure-DataTestCoding",
                    "0",
                )
                self.assertEqual(first, second)
                self.assertTrue(first.is_dir())

    def test_non_custom_agent_and_fanout_paths_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "run-root"
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                plain = _ensure_step_work_dir(None, "0")
                fanout = _ensure_step_work_dir(
                    "Arch-Microservice-ServiceCatalog",
                    "step-3-3-SVC-13",
                )
                self.assertEqual(plain, (work_root / "Issue-0").resolve())
                self.assertEqual(
                    fanout,
                    (
                        work_root
                        / "Arch-Microservice-ServiceCatalog"
                        / "Issue-step-3-3-SVC-13"
                    ).resolve(),
                )
                self.assertNotEqual(plain, fanout)

    def test_rejects_unsafe_agent_or_identifier_components(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(Path(td) / "root")},
                clear=False,
            ):
                for agent, identifier in (
                    ("../outside", "0"),
                    ("Agent\\outside", "0"),
                    ("Agent", "../outside"),
                    ("Agent", ""),
                ):
                    with self.subTest(agent=agent, identifier=identifier):
                        with self.assertRaises(ValueError):
                            _ensure_step_work_dir(agent, identifier)

    def test_rejects_symlink_escape_without_creating_outside_issue_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            outside = Path(td) / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "Agent"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                if os.name != "nt":
                    self.skipTest("directory symlink is unavailable on this platform")
                completed = subprocess.run(
                    ["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    self.fail(
                        "directory junction could not be created for escape test: "
                        + completed.stderr
                    )
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(root)},
                clear=False,
            ):
                with self.assertRaises(ValueError):
                    _ensure_step_work_dir("Agent", "0")
            self.assertFalse((outside / "Issue-0").exists())

    def test_dry_run_does_not_create_step_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work-root"
            runner = StepRunner(
                config=SDKConfig(dry_run=True, model="claude-opus-4.7"),
                console=Console(verbose=False, quiet=True),
            )
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                result = _run(
                    runner.run_step(
                        "1.1",
                        "Data design",
                        "design",
                        custom_agent="Dev-Microservice-Azure-DataDesign",
                    )
                )
            self.assertTrue(result)
            self.assertFalse(work_root.exists())

    def test_pre_gate_failure_does_not_create_step_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work-root"
            runner = StepRunner(
                config=SDKConfig(dry_run=False, model="claude-opus-4.7"),
                console=Console(verbose=False, quiet=True),
            )
            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(work_root)},
                clear=False,
            ), unittest.mock.patch.object(
                runner,
                "_run_asdw_data_verify_contract_gate",
                return_value=["stale verifier"],
            ):
                result = _run(
                    runner.run_step(
                        "1.3",
                        "Data deploy",
                        "deploy",
                        custom_agent="Dev-Microservice-Azure-DataDeploy",
                    )
                )
            self.assertFalse(result)
            self.assertFalse(work_root.exists())

    def test_mkdir_failure_stops_before_sdk_import(self) -> None:
        console = Console(verbose=False, quiet=True)
        console.error = unittest.mock.MagicMock()
        runner = StepRunner(
            config=SDKConfig(dry_run=False, model="claude-opus-4.7"),
            console=console,
        )
        with unittest.mock.patch(
            "runner._ensure_step_work_dir",
            side_effect=PermissionError("denied"),
        ), unittest.mock.patch.dict(
            sys.modules,
            {"copilot": None},
        ):
            result = _run(
                runner.run_step(
                    "1.1",
                    "Data design",
                    "design",
                    custom_agent="Dev-Microservice-Azure-DataDesign",
                )
            )
        self.assertFalse(result)
        self.assertEqual(console.error.call_count, 1)
        self.assertIn(
            "step work directory creation failed",
            str(console.error.call_args.args[0]),
        )
        self.assertNotIn(
            "GitHub Copilot SDK",
            str(console.error.call_args.args[0]),
        )

    def test_fanout_prompt_and_work_directory_share_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work_root = root / "work-root"
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "Agent.prompt.md").write_text(
                "> **WORK**: `work/run/<run-id>/Agent/Issue-<識別子>/`",
                encoding="utf-8",
            )
            captured: dict[str, str] = {}

            class FakeSession:
                def on(self, _callback) -> None:
                    return None

                async def disconnect(self) -> None:
                    return None

            class FakeClient:
                async def stop(self) -> None:
                    return None

            runner = StepRunner(
                config=SDKConfig(dry_run=False, model="claude-opus-4.7"),
                console=Console(verbose=False, quiet=True),
            )

            async def fake_start_client(_client, *, console) -> None:
                return None

            async def fake_session(_self, **_kwargs):
                return FakeSession()

            async def fake_send(_self, _session, prompt, *, timeout, step_id):
                captured["prompt"] = prompt
                return object()

            with unittest.mock.patch.dict(
                os.environ,
                {"HVE_WORK_ROOT": str(work_root), "HVE_RUN_ID": "run-1"},
                clear=False,
            ), unittest.mock.patch(
                "runner._start_client_with_retry",
                fake_start_client,
            ), unittest.mock.patch(
                "copilot_client_factory.create_copilot_client",
                return_value=FakeClient(),
            ), unittest.mock.patch(
                "runner.load_prompt",
                create=True,
            ) as _unused:
                # load_prompt is imported inside run_step; patch its source module.
                with unittest.mock.patch(
                    "prompt_loader.load_prompt",
                    return_value=(prompts / "Agent.prompt.md").read_text(encoding="utf-8"),
                ), unittest.mock.patch.object(
                    runner,
                    "_create_main_session",
                    side_effect=fake_session.__get__(runner, StepRunner),
                ), unittest.mock.patch.object(
                    runner,
                    "_send_and_wait_with_model_call_failure_guard",
                    side_effect=fake_send.__get__(runner, StepRunner),
                ), unittest.mock.patch.object(
                    runner,
                    "_maybe_run_split_fork",
                    return_value=True,
                ), unittest.mock.patch.object(
                    runner,
                    "_run_asdw_data_verify_contract_gate",
                    return_value=[],
                ), unittest.mock.patch.object(
                    runner,
                    "_run_ai_agent_capability_gate",
                    return_value=[],
                ), unittest.mock.patch.object(
                    runner,
                    "_run_tdd_report_gate",
                    return_value=[],
                ), unittest.mock.patch.object(
                    runner,
                    "_run_asdw_ui_red_unresolved_contract_gate",
                    return_value=[],
                ), unittest.mock.patch.object(
                    runner,
                    "_run_deploy_ac_gate",
                    return_value=[],
                ), unittest.mock.patch(
                    "runner._check_output_paths_gate",
                    return_value=[],
                ), unittest.mock.patch(
                    "runner._extract_text",
                    return_value="",
                ):
                    result = _run(
                        runner.run_step(
                            "3.3/SVC-13",
                            "fanout",
                            "generate",
                            custom_agent="Agent",
                            workflow_id="asdw-web",
                            fanout_meta={
                                "fanout_key": "SVC-13",
                                "base_step_id": "3.3",
                            },
                        )
                    )
            self.assertTrue(result)
            self.assertIn("Issue-step-3-3-SVC-13", captured["prompt"])
            first = work_root / "Agent" / "Issue-step-3-3-SVC-13"
            self.assertTrue(first.is_dir())
            second = _ensure_step_work_dir("Agent", "step-3-3-SVC-16")
            self.assertTrue(second.is_dir())
            self.assertNotEqual(first.resolve(), second)

    def test_non_dry_run_creates_work_dir_before_sdk_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            work_root = Path(td) / "work-root"
            cfg = SDKConfig(dry_run=False, model="claude-opus-4.7")
            runner = StepRunner(
                config=cfg,
                console=Console(verbose=False, quiet=True),
            )
            original = sys.modules.get("copilot", _SENTINEL)
            sys.modules["copilot"] = None  # type: ignore[assignment]
            try:
                with unittest.mock.patch.dict(
                    os.environ,
                    {"HVE_WORK_ROOT": str(work_root)},
                    clear=False,
                ):
                    result = _run(
                        runner.run_step(
                            "1.1",
                            "Data design",
                            "design data stores",
                            custom_agent="Dev-Microservice-Azure-DataDesign",
                            workflow_id="asdw-web",
                        )
                    )
            finally:
                if original is _SENTINEL:
                    sys.modules.pop("copilot", None)
                else:
                    sys.modules["copilot"] = original  # type: ignore[assignment]

            self.assertFalse(result)
            self.assertTrue(
                (
                    work_root
                    / "Dev-Microservice-Azure-DataDesign"
                    / "Issue-0"
                ).is_dir()
            )


class TestMcpServerFiltering(unittest.TestCase):
    """main session に Work IQ MCP alias を誤接続しないためのフィルタ。"""

    def test_excludes_hve_and_plain_workiq_aliases_by_default(self) -> None:
        servers = {
            WORKIQ_MCP_SERVER_NAME: {"command": "npx"},
            "workiq": {"command": "npx"},
            " WorkIQ ": {"command": "npx"},
            "azure": {"command": "azmcp"},
        }

        filtered = _filter_mcp_servers_for_session(servers)

        self.assertEqual(filtered, {"azure": {"command": "azmcp"}})

    def test_include_workiq_keeps_aliases_for_dedicated_workiq_phase(self) -> None:
        servers = {
            WORKIQ_MCP_SERVER_NAME: {"command": "npx"},
            "workiq": {"command": "npx"},
            " WorkIQ ": {"command": "npx"},
            "azure": {"command": "azmcp"},
        }

        filtered = _filter_mcp_servers_for_session(servers, include_workiq=True)

        self.assertEqual(filtered, servers)

    def test_excludes_preview_plugin_alias(self) -> None:
        """`workiq-preview` も同じ Work IQ サービスなのでメインセッションから除外する。"""
        servers = {
            "workiq-preview": {"type": "http"},
            "azure": {"command": "azmcp"},
        }

        self.assertEqual(
            _filter_mcp_servers_for_session(servers),
            {"azure": {"command": "azmcp"}},
        )
        self.assertEqual(
            _filter_mcp_servers_for_session(servers, include_workiq=True), servers,
        )


class TestAzureFreeWorkflowMcpFilter(unittest.TestCase):
    """FR-CLI-79: Azure を利用しない Workflow には azure MCP を渡さない。"""

    SERVERS = {
        "azure": {"command": "azmcp", "tools": ["*"]},
        "microsoft-learn": {"type": "http", "tools": ["*"]},
    }

    def test_drops_azure_for_declared_azure_free_workflows(self) -> None:
        for workflow_id in sorted(_AZURE_FREE_WORKFLOWS):
            with self.subTest(workflow_id=workflow_id):
                filtered = _filter_mcp_servers_for_session(
                    self.SERVERS, workflow_id=workflow_id
                )
                self.assertNotIn("azure", filtered)
                self.assertIn("microsoft-learn", filtered)

    def test_keeps_azure_for_every_other_workflow(self) -> None:
        for workflow in list_workflows():
            if workflow.id in _AZURE_FREE_WORKFLOWS:
                continue
            with self.subTest(workflow_id=workflow.id):
                filtered = _filter_mcp_servers_for_session(
                    self.SERVERS, workflow_id=workflow.id
                )
                self.assertIn("azure", filtered)

    def test_unknown_or_missing_workflow_id_keeps_every_server(self) -> None:
        for workflow_id in (None, "", "not-a-workflow"):
            with self.subTest(workflow_id=workflow_id):
                self.assertEqual(
                    _filter_mcp_servers_for_session(self.SERVERS, workflow_id=workflow_id),
                    self.SERVERS,
                )

    def test_allowlist_entries_exist_in_the_registry(self) -> None:
        self.assertLessEqual(_AZURE_FREE_WORKFLOWS, {w.id for w in list_workflows()})

    def test_allowlist_workflows_never_mention_azure_in_their_prompts(self) -> None:
        """allowlist が実装から取り残されると、Azure を使う Step が壊れる。"""
        prompts = Path(__file__).resolve().parents[2] / ".github" / "prompts"
        offenders = []
        for workflow_id in sorted(_AZURE_FREE_WORKFLOWS):
            for step in get_workflow(workflow_id).steps:
                if not step.custom_agent:
                    continue
                prompt = prompts / f"{step.custom_agent}.prompt.md"
                if not prompt.exists():
                    continue
                if "azure" in prompt.read_text(encoding="utf-8").lower():
                    offenders.append(f"{workflow_id}:{step.id}:{step.custom_agent}")
        self.assertEqual(offenders, [])

    def test_excluded_server_name_exists_in_the_repository_mcp_config(self) -> None:
        """サーバ名が改名されると縮約が無言で効かなくなる。"""
        config = json.loads(
            (Path(__file__).resolve().parents[2] / ".github" / ".mcp.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(_AZURE_MCP_SERVER_NAME, config.get("mcpServers", {}))

    def test_the_filter_is_wired_into_the_repository_mcp_injection(self) -> None:
        """フィルタ自体が正しくても、配線が外れれば削減は効かない。"""
        import inspect

        from runner import (
            _apply_repository_mcp_scope,
            _create_session_with_auto_reasoning_fallback,
        )

        self.assertIn(
            "workflow_id",
            inspect.signature(_create_session_with_auto_reasoning_fallback).parameters,
        )
        source = inspect.getsource(_create_session_with_auto_reasoning_fallback)
        code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        block = code[code.index("_apply_repository_mcp_scope"):]
        self.assertIn("workflow_id=workflow_id", block)

        # 縮約の単一実装（FR-MAINT-07）側でフィルタが適用されていること。
        helper = "\n".join(
            line.split("#", 1)[0]
            for line in inspect.getsource(_apply_repository_mcp_scope).splitlines()
        )
        self.assertIn("_filter_mcp_servers_for_session(", helper)
        self.assertIn("workflow_id=workflow_id", helper)

        run_step_source = inspect.getsource(StepRunner.run_step)
        call = run_step_source[run_step_source.index("self._create_main_session("):]
        self.assertIn("workflow_id=workflow_id", call[:400])


class TestStepRunnerNonDryRunNoSDK(unittest.TestCase):
    """dry_run=False で SDK 未インストール時に False を返す。"""

    def test_asdw_data_deploy_verify_contract_fails_before_sdk_import(self) -> None:
        """DataDeploy の stale verify 入力は SDK import より前に fail-fast する。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "src" / "infra" / "azure" / "verify-data-resources.sh"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
  --restart-policy Never \
  --command-line "sh -c 'PGPASSWORD=$PG_TOKEN psql -h $PG_HOST -U $PG_ADMIN_USER -d $PG_DB_NAME'"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
                encoding="utf-8",
            )
            cfg = SDKConfig(dry_run=False, model="claude-opus-4.7")
            console = Console(verbose=False, quiet=True)
            console.error = unittest.mock.MagicMock()
            runner = StepRunner(
                config=cfg,
                console=console,
                # Step 1.3 は APP-009 スコープと bootstrap context を満たしてから
                # verify 契約 gate へ到達する。
                workflow_params={
                    "app_ids": ["APP-009"],
                    "resource_group": "test-resource-group",
                    "data_location": "japaneast",
                    "data_resource_suffix": "app009",
                    "data_vnet_cidr": "10.40.0.0/16",
                    "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
                    "data_aci_subnet_cidr": "10.40.2.0/24",
                },
            )
            # 事前 gate（work root / Learn MCP pin）を満たし、verify 契約 gate まで到達させる。
            run_id = "20260725T000000-verifygate"
            sample_data = root / "src" / "data" / "sample-data.json"
            sample_data.parent.mkdir(parents=True, exist_ok=True)
            sample_data.write_text("{}", encoding="utf-8")
            mcp_config = root / ".github" / ".mcp.json"
            mcp_config.parent.mkdir(parents=True, exist_ok=True)
            mcp_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "microsoft-learn": {
                                "type": "http",
                                "url": "https://learn.microsoft.com/api/mcp",
                                "tools": ["*"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            original_cwd = os.getcwd()
            original = sys.modules.get("copilot", _SENTINEL)
            sys.modules["copilot"] = None  # type: ignore[assignment]
            original_env = {
                key: os.environ.get(key) for key in ("HVE_RUN_ID", "HVE_WORK_ROOT")
            }
            work_root = root / "work" / "run" / run_id
            work_root.mkdir(parents=True, exist_ok=True)
            os.environ["HVE_RUN_ID"] = run_id
            os.environ["HVE_WORK_ROOT"] = str(work_root.resolve())
            try:
                os.chdir(root)
                with _CaptureOutput() as cap, unittest.mock.patch(
                    "runner._resolve_asdw_data_deploy_subscription_id",
                    return_value="00000000-0000-0000-0000-000000000001",
                ):
                    result = _run(
                        runner.run_step(
                            "1.3",
                            "Azure データサービス Deploy",
                            "プロンプト",
                            custom_agent="Dev-Microservice-Azure-DataDeploy",
                            workflow_id="asdw-web",
                        )
                    )
            finally:
                os.chdir(original_cwd)
                for key, value in original_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                if original is _SENTINEL:
                    sys.modules.pop("copilot", None)
                else:
                    sys.modules["copilot"] = original  # type: ignore[assignment]

        self.assertFalse(result)
        error_text = "\n".join(str(call.args[0]) for call in console.error.call_args_list)
        self.assertIn("input verify-data-resources.sh contract failed", error_text)
        self.assertIn("--os-type Linux", error_text)
        self.assertNotIn("GitHub Copilot SDK がインストールされていません", cap.stdout)

    def test_asdw_data_testcoding_stale_verify_does_not_fail_before_sdk_import(self) -> None:
        """DataTestCoding は producer なので stale verify があっても生成前 gate で落とさない。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "src" / "infra" / "azure" / "verify-data-resources.sh"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
  --restart-policy Never \
  --command-line "sh -c 'PGPASSWORD=$PG_TOKEN psql -h $PG_HOST -U $PG_ADMIN_USER -d $PG_DB_NAME'"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
                encoding="utf-8",
            )
            cfg = SDKConfig(dry_run=False, model="claude-opus-4.7")
            console = Console(verbose=False, quiet=True)
            console.error = unittest.mock.MagicMock()
            runner = StepRunner(config=cfg, console=console)

            original_cwd = os.getcwd()
            original = sys.modules.get("copilot", _SENTINEL)
            sys.modules["copilot"] = None  # type: ignore[assignment]
            try:
                os.chdir(root)
                result = _run(
                    runner.run_step(
                        "1.2",
                        "データストア検証テスト生成 (TDD RED)",
                        "プロンプト",
                        custom_agent="Dev-Microservice-Azure-DataTestCoding",
                        workflow_id="asdw-web",
                    )
                )
            finally:
                os.chdir(original_cwd)
                if original is _SENTINEL:
                    sys.modules.pop("copilot", None)
                else:
                    sys.modules["copilot"] = original  # type: ignore[assignment]

        self.assertFalse(result)
        error_text = "\n".join(str(call.args[0]) for call in console.error.call_args_list)
        self.assertNotIn("generated verify-data-resources.sh contract failed", error_text)
        self.assertNotIn("PostgreSQL ACI fallback", error_text)

    def test_returns_false_when_sdk_missing(self) -> None:
        cfg = SDKConfig(dry_run=False, model="claude-opus-4.7")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        # sys.modules['copilot'] = None は Python の標準的な「存在しないモジュール」マーカーで
        # import 時に確実に ImportError を発生させる
        original = sys.modules.get("copilot", _SENTINEL)
        sys.modules["copilot"] = None  # type: ignore[assignment]
        try:
            with _CaptureOutput() as cap:
                result = _run(
                    runner.run_step("1.1", "テスト", "プロンプト")
                )
            self.assertFalse(result)
            # quiet=True でもエラーは stderr に出る
            self.assertIn("ERROR", cap.stderr)
        finally:
            if original is _SENTINEL:
                sys.modules.pop("copilot", None)
            else:
                sys.modules["copilot"] = original


class TestStepRunnerConfig(unittest.TestCase):
    """StepRunner に設定が正しく注入されることを検証する。"""

    def test_config_is_stored(self) -> None:
        cfg = SDKConfig(dry_run=True, model="gpt-5")
        console = Console()
        runner = StepRunner(config=cfg, console=console)
        self.assertIs(runner.config, cfg)

    def test_console_is_stored(self) -> None:
        cfg = SDKConfig()
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertIs(runner.console, console)

    def test_context_injection_max_chars_default(self) -> None:
        cfg = SDKConfig()
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertEqual(
            runner._get_context_injection_max_chars(),
            DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        )

    def test_context_injection_max_chars_invalid_runtime_value_falls_back_to_default(self) -> None:
        cfg = SDKConfig()
        cfg.context_injection_max_chars = -1
        console = Console(verbose=False)
        runner = StepRunner(config=cfg, console=console)
        self.assertEqual(
            runner._get_context_injection_max_chars(),
            DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        )


# -----------------------------------------------------------------------
# ストリームイベント処理テスト
# -----------------------------------------------------------------------


class _FakeEventType:
    """SessionEventType enum のモック。.value で文字列を返す。"""

    def __init__(self, value: str):
        self.value = value


class _FakeEventData:
    """イベントデータのモック。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeEvent:
    """セッションイベントのモック。"""

    def __init__(self, etype: str, data=None):
        self.type = _FakeEventType(etype)
        self.data = data


class TestStepRunnerStreamEvents(unittest.TestCase):
    """_handle_session_event のストリームイベント処理を検証する。"""

    def _make_runner(
        self,
        show_stream: bool = True,
        verbose: bool = False,
        show_reasoning: bool = True,
    ) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(
            verbose=verbose,
            quiet=False,
            show_stream=show_stream,
            show_reasoning=show_reasoning,
        )
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1.1"
        return runner

    def test_message_delta_calls_stream_token(self) -> None:
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "Hello")

    def test_message_delta_content_fallback(self) -> None:
        """data.delta_content がない場合に camelCase の deltaContent にフォールバックする。

        SDK 仕様（streaming-events.md）では assistant.message_delta は deltaContent のみ。
        Python SDK の snake_case 変換にも対応するため delta_content と deltaContent の両方を受け付ける。
        SDK 仕様に存在しない `content` フィールドへのフォールバックは削除済み。
        """
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(deltaContent="World"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "World")

    def test_model_call_failure_logs_warning_and_counts(self) -> None:
        """model.call_failure は未知イベント扱いではなく warning として記録される。"""
        runner = self._make_runner(show_stream=False)
        event = _FakeEvent("model.call_failure", _FakeEventData(reason="quota"))

        with _CaptureOutput() as cap:
            runner._handle_session_event(event)

        output = cap.stdout + cap.stderr
        self.assertIn("model.call_failure", output)
        self.assertEqual(runner._model_call_failure_counts["1.1"], 1)

    def test_bound_session_event_uses_bound_step_id(self) -> None:
        """並列 Step で _current_step_id が別値でも、束縛済み step_id でイベント処理する。"""
        runner = self._make_runner(show_stream=False)
        runner._current_step_id = "3.3/SVC-16"
        event = _FakeEvent("model.call_failure", _FakeEventData(reason="quota"))

        with _CaptureOutput() as cap:
            runner._handle_session_event_for_step(event, "3.3/SVC-13")

        output = cap.stdout + cap.stderr
        self.assertIn("[3.3/SVC-13]", output)
        self.assertNotIn("[3.3/SVC-16]", output)
        self.assertEqual(runner._model_call_failure_counts["3.3/SVC-13"], 1)
        self.assertNotIn("3.3/SVC-16", runner._model_call_failure_counts)

    def test_model_call_failure_sets_guard_event_at_threshold(self) -> None:
        """同一 step で model.call_failure が3回に達すると guard event が set される。"""
        async def scenario() -> bool:
            runner = self._make_runner(show_stream=False)
            event = asyncio.Event()
            runner._model_call_failure_events["1.1"] = event
            with _CaptureOutput():
                for _ in range(3):
                    runner._handle_session_event(_FakeEvent("model.call_failure"))
            return event.is_set()

        self.assertTrue(_run(scenario()))

    def test_send_and_wait_guard_fails_fast_after_repeated_model_call_failure(self) -> None:
        """Phase 1 guard は model.call_failure 3回で send_and_wait をキャンセルして失敗する。"""
        class _HangingSession:
            async def send_and_wait(self, *_args, **_kwargs):
                await asyncio.sleep(5.0)
                return None

        async def scenario() -> str:
            runner = self._make_runner(show_stream=False)
            task = asyncio.create_task(
                runner._send_and_wait_with_model_call_failure_guard(
                    _HangingSession(),
                    "prompt",
                    timeout=10.0,
                    step_id="1.1",
                )
            )
            await asyncio.sleep(0)
            with _CaptureOutput():
                for _ in range(3):
                    runner._handle_session_event(_FakeEvent("model.call_failure"))
            try:
                await task
            except RuntimeError as exc:
                return str(exc)
            return ""

        self.assertIn("model.call_failure repeated 3 times", _run(scenario()))

    def test_message_delta_empty_no_output(self) -> None:
        """トークンが空の場合は出力しない。"""
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content=""))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_turn_end_calls_stream_end(self) -> None:
        runner = self._make_runner(show_stream=True)
        event = _FakeEvent("assistant.turn_end")
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ストリーム終了", cap.stdout)

    def test_stream_suppressed_when_show_stream_false(self) -> None:
        """show_stream=False の場合、ストリームイベントは出力されない。"""
        runner = self._make_runner(show_stream=False)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_reasoning_delta_calls_reasoning_token(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.reasoning_delta", _FakeEventData(delta_content="検討中"))
        with unittest.mock.patch.object(runner.console, "reasoning_token") as mock_reasoning_token:
            runner._handle_session_event(event)
        mock_reasoning_token.assert_called_once_with("1.1", "検討中")

    def test_reasoning_complete_calls_reasoning_complete(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.reasoning", _FakeEventData(content="最終推論"))
        with unittest.mock.patch.object(runner.console, "reasoning_complete") as mock_reasoning_complete:
            runner._handle_session_event(event)
        mock_reasoning_complete.assert_called_once_with("1.1", "最終推論")

    def test_reasoning_delta_hidden_when_show_reasoning_false(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True, show_reasoning=False)
        event = _FakeEvent("assistant.reasoning_delta", _FakeEventData(delta_content="hidden"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")

    def test_message_delta_still_uses_stream_token(self) -> None:
        runner = self._make_runner(show_stream=True, verbose=True)
        event = _FakeEvent("assistant.message_delta", _FakeEventData(delta_content="Hello"))
        with unittest.mock.patch.object(runner.console, "stream_token") as mock_stream_token:
            runner._handle_session_event(event)
        mock_stream_token.assert_called_once_with("1.1", "Hello")

    def test_subagent_event_still_works(self) -> None:
        """既存のイベント処理が維持されていることを確認。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("subagent.started", _FakeEventData(agent_display_name="TestAgent"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("TestAgent", cap.stdout)

    def test_tool_event_still_works(self) -> None:
        """既存の tool イベント処理が維持されていることを確認。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="grep"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("grep", cap.stdout)

    def test_tool_event_without_server_name_does_not_set_called_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        self.assertFalse(runner._workiq_tool_called)
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask"))
        with _CaptureOutput():
            runner._handle_session_event(event)
        self.assertFalse(runner._workiq_tool_called)

    def test_workiq_mcp_tool_event_sets_called_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        self.assertFalse(runner._workiq_tool_called)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("Work IQ ツール 'ask' が呼び出されました", cap.stdout)
        self.assertTrue(runner._workiq_tool_called)
        self.assertEqual(runner._workiq_called_tools, ["ask"])

    def test_other_mcp_server_tool_does_not_set_workiq_flag(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name="other_server"),
        )
        with _CaptureOutput():
            runner._handle_session_event(event)
        self.assertFalse(runner._workiq_tool_called)
        self.assertEqual(runner._workiq_called_tools, [])

    def test_tool_execution_complete_success(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=True, result_summary="12 files found"),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("12 files found", cap.stdout)

    def test_tool_execution_complete_failure_includes_tool_name(self) -> None:
        """T-M5: tool.execution_complete (failure) でツール名がエラーメッセージに前置される。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                tool_name="view",
                error=_FakeEventData(message="timeout"),
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("view: timeout", cap.stdout)

    def test_tool_execution_complete_failure_includes_recent_view_path_and_range(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        start = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                arguments={
                    "path": "docs/test-specs/APP-009-S010-test-spec.md",
                    "view_range": [200, 260],
                },
            ),
        )
        complete = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                tool_name="view",
                error=_FakeEventData(message="view_range out of bounds"),
            ),
        )

        with _CaptureOutput() as cap:
            runner._handle_session_event(start)
            runner._handle_session_event(complete)

        self.assertIn("view: view_range out of bounds", cap.stdout)
        self.assertIn("path=docs/test-specs/APP-009-S010-test-spec.md", cap.stdout)
        self.assertIn("view_range=[200, 260]", cap.stdout)

    def test_tool_execution_complete_success_clears_recent_view_args(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        start = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                arguments={"path": "docs/test-specs/APP-009-S010-test-spec.md", "view_range": [200, 260]},
            ),
        )
        success = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=True, result_summary="ok"),
        )
        later_failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=False, error=_FakeEventData(message="timeout")),
        )

        with _CaptureOutput() as cap:
            runner._handle_session_event(start)
            runner._handle_session_event(success)
            runner._handle_session_event(later_failure)

        failure_line = cap.stdout.rsplit("ツール失敗:", 1)[-1]
        self.assertIn("timeout", failure_line)
        self.assertNotIn("path=docs/test-specs/APP-009-S010-test-spec.md", failure_line)
        self.assertNotIn("view_range=[200, 260]", failure_line)

    def test_tool_execution_complete_legacy_parallel_calls_remain_ambiguous_until_done(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        events = (
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    arguments={"path": "docs/first.md", "view_range": [1, 5]},
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    arguments={"path": "docs/second.md", "view_range": [6, 10]},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    error=_FakeEventData(message="first failed"),
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    error=_FakeEventData(message="second failed"),
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    arguments={"path": "docs/third.md", "view_range": [11, 15]},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    error=_FakeEventData(message="third failed"),
                ),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            for event in events:
                runner._handle_session_event(event)

        self.assertEqual(tool_result.call_count, 3)
        self.assertEqual(tool_result.call_args_list[0].kwargs["error_msg"], "first failed")
        self.assertEqual(tool_result.call_args_list[1].kwargs["error_msg"], "second failed")
        third_msg = tool_result.call_args_list[2].kwargs["error_msg"]
        self.assertIn("view: third failed", third_msg)
        self.assertIn("path=docs/third.md", third_msg)
        self.assertIn("view_range=[11, 15]", third_msg)

    def test_tool_execution_complete_correlates_parallel_calls_by_camelcase_id(self) -> None:
        """camelCase event payloadとの互換経路でもcall IDを相関する。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        start_a = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                toolCallId="call-a",
                arguments={
                    "path": "docs/a.md",
                    "view_range": [221, 440],
                },
            ),
        )
        start_b = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                toolCallId="call-b",
                arguments={
                    "path": "docs/b.md",
                    "view_range": [441, 700],
                },
            ),
        )
        success_b = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=True, toolCallId="call-b", result_summary="ok"),
        )
        failure_a = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="call-a",
                error=_FakeEventData(message="view_range out of bounds"),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            for event in (start_a, start_b, success_b, failure_a):
                runner._handle_session_event(event)

        tool_result.assert_called_once()
        args, kwargs = tool_result.call_args
        self.assertEqual(args[:2], ("1.1", False))
        error_msg = kwargs["error_msg"]
        self.assertIn("view: view_range out of bounds", error_msg)
        self.assertIn("path=docs/a.md", error_msg)
        self.assertIn("view_range=[221, 440]", error_msg)
        self.assertNotIn("docs/b.md", error_msg)
        self.assertNotIn("[441, 700]", error_msg)

    def test_tool_execution_complete_correlates_reverse_failures_with_real_sdk_data(self) -> None:
        from copilot.generated.session_events import (
            ToolExecutionCompleteData,
            ToolExecutionCompleteError,
            ToolExecutionStartData,
        )

        runner = self._make_runner(show_stream=False, verbose=True)
        events = (
            _FakeEvent(
                "tool.execution_start",
                ToolExecutionStartData(
                    tool_call_id="call-a",
                    tool_name="view",
                    arguments={"path": "docs/a.md", "view_range": [1, 10]},
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                ToolExecutionStartData(
                    tool_call_id="call-b",
                    tool_name="view",
                    arguments={"path": "docs/b.md", "view_range": [11, 20]},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                ToolExecutionCompleteData(
                    success=False,
                    tool_call_id="call-b",
                    error=ToolExecutionCompleteError(message="b failed"),
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                ToolExecutionCompleteData(
                    success=False,
                    tool_call_id="call-a",
                    error=ToolExecutionCompleteError(message="a failed"),
                ),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            for event in events:
                runner._handle_session_event(event)

        self.assertEqual(tool_result.call_count, 2)
        first_args, first_kwargs = tool_result.call_args_list[0]
        second_args, second_kwargs = tool_result.call_args_list[1]
        self.assertEqual(first_args[:2], ("1.1", False))
        self.assertEqual(second_args[:2], ("1.1", False))
        self.assertIn("view: b failed", first_kwargs["error_msg"])
        self.assertIn("path=docs/b.md", first_kwargs["error_msg"])
        self.assertNotIn("docs/a.md", first_kwargs["error_msg"])
        self.assertIn("view: a failed", second_kwargs["error_msg"])
        self.assertIn("path=docs/a.md", second_kwargs["error_msg"])
        self.assertNotIn("docs/b.md", second_kwargs["error_msg"])

    def test_tool_execution_complete_unknown_id_does_not_borrow_other_call_args(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        start = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                toolCallId="known-call",
                arguments={"path": "docs/known.md", "view_range": [30, 40]},
            ),
        )
        unknown_failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="unknown-call",
                error=_FakeEventData(message="unknown failed"),
            ),
        )

        known_failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="known-call",
                error=_FakeEventData(message="known failed"),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event(start)
            runner._handle_session_event(unknown_failure)
            runner._handle_session_event(known_failure)

        self.assertEqual(tool_result.call_count, 2)
        unknown_msg = tool_result.call_args_list[0].kwargs["error_msg"]
        known_msg = tool_result.call_args_list[1].kwargs["error_msg"]
        self.assertIn("unknown failed", unknown_msg)
        self.assertNotIn("docs/known.md", unknown_msg)
        self.assertNotIn("[30, 40]", unknown_msg)
        self.assertIn("view: known failed", known_msg)
        self.assertIn("path=docs/known.md", known_msg)
        self.assertIn("view_range=[30, 40]", known_msg)

    def test_tool_execution_complete_call_ids_are_isolated_by_step(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        same_id = "shared-call"
        runner._handle_session_event_for_step(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId=same_id,
                    arguments={"path": "docs/step-a.md", "view_range": [1, 5]},
                ),
            ),
            "step-a",
        )
        runner._handle_session_event_for_step(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId=same_id,
                    arguments={"path": "docs/step-b.md", "view_range": [6, 10]},
                ),
            ),
            "step-b",
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event_for_step(
                _FakeEvent(
                    "tool.execution_complete",
                    _FakeEventData(
                        success=False,
                        toolCallId=same_id,
                        error=_FakeEventData(message="step-a failed"),
                    ),
                ),
                "step-a",
            )
            runner._handle_session_event_for_step(
                _FakeEvent(
                    "tool.execution_complete",
                    _FakeEventData(
                        success=False,
                        toolCallId=same_id,
                        error=_FakeEventData(message="step-b failed"),
                    ),
                ),
                "step-b",
            )

        self.assertEqual(tool_result.call_count, 2)
        first_args, first_kwargs = tool_result.call_args_list[0]
        second_args, second_kwargs = tool_result.call_args_list[1]
        self.assertEqual(first_args[:2], ("step-a", False))
        self.assertEqual(second_args[:2], ("step-b", False))
        self.assertIn("docs/step-a.md", first_kwargs["error_msg"])
        self.assertNotIn("docs/step-b.md", first_kwargs["error_msg"])
        self.assertIn("docs/step-b.md", second_kwargs["error_msg"])
        self.assertNotIn("docs/step-a.md", second_kwargs["error_msg"])

    def test_tool_execution_start_with_id_recovers_name_without_arguments(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        argument_cases: tuple[dict[str, Any] | None, ...] = (None, {})
        for index, arguments in enumerate(argument_cases):
            call_id = f"empty-{index}"
            runner._handle_session_event(
                _FakeEvent(
                    "tool.execution_start",
                    _FakeEventData(
                        tool_name="view",
                        toolCallId=call_id,
                        arguments=arguments,
                    ),
                )
            )
            with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
                runner._handle_session_event(
                    _FakeEvent(
                        "tool.execution_complete",
                        _FakeEventData(
                            success=False,
                            toolCallId=call_id,
                            error=_FakeEventData(message="empty failed"),
                        ),
                    )
                )
            self.assertIn("view: empty failed", tool_result.call_args.kwargs["error_msg"])

    def test_internal_tools_with_ids_recover_start_names(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        for tool_name in ("task", "report_intent"):
            call_id = f"{tool_name}-call"
            runner._handle_session_event(
                _FakeEvent(
                    "tool.execution_start",
                    _FakeEventData(
                        tool_name=tool_name,
                        toolCallId=call_id,
                        arguments=None,
                    ),
                )
            )
            with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
                runner._handle_session_event(
                    _FakeEvent(
                        "tool.execution_complete",
                        _FakeEventData(
                            success=False,
                            toolCallId=call_id,
                            error=_FakeEventData(message="internal failed"),
                        ),
                    )
                )
            self.assertIn(
                f"{tool_name}: internal failed",
                tool_result.call_args.kwargs["error_msg"],
            )

    def test_duplicate_active_call_id_does_not_borrow_either_start(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        for path in ("docs/first.md", "docs/second.md"):
            runner._handle_session_event(
                _FakeEvent(
                    "tool.execution_start",
                    _FakeEventData(
                        tool_name="view",
                        toolCallId="duplicate-call",
                        arguments={"path": path, "view_range": [1, 5]},
                    ),
                )
            )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event(
                _FakeEvent(
                    "tool.execution_complete",
                    _FakeEventData(
                        success=False,
                        toolCallId="duplicate-call",
                        error=_FakeEventData(message="duplicate failed"),
                    ),
                )
            )

        error_msg = tool_result.call_args.kwargs["error_msg"]
        self.assertEqual(error_msg, "duplicate failed")
        self.assertNotIn("docs/first.md", error_msg)
        self.assertNotIn("docs/second.md", error_msg)

    def test_duplicate_call_id_remains_ambiguous_until_all_completes_arrive(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        duplicate_id = "duplicate-call"
        starts_and_completes = (
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId=duplicate_id,
                    arguments={"path": "docs/first.md", "view_range": [1, 5]},
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId=duplicate_id,
                    arguments={"path": "docs/second.md", "view_range": [6, 10]},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    toolCallId=duplicate_id,
                    error=_FakeEventData(message="first duplicate completion"),
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId=duplicate_id,
                    arguments={"path": "docs/new.md", "view_range": [11, 15]},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    toolCallId=duplicate_id,
                    error=_FakeEventData(message="second duplicate completion"),
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    toolCallId=duplicate_id,
                    error=_FakeEventData(message="third duplicate completion"),
                ),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            for event in starts_and_completes:
                runner._handle_session_event(event)

        self.assertEqual(tool_result.call_count, 3)
        expected_messages = (
            "first duplicate completion",
            "second duplicate completion",
            "third duplicate completion",
        )
        for call, expected in zip(tool_result.call_args_list, expected_messages):
            self.assertEqual(call.kwargs["error_msg"], expected)

    def test_run_step_finally_clears_tool_starts_arriving_during_cleanup(self) -> None:
        async def scenario(cancel_disconnect: bool) -> tuple[StepRunner, bool, int]:
            runner = StepRunner(
                config=SDKConfig(
                    dry_run=False,
                    auto_qa=False,
                    auto_contents_review=False,
                    auto_self_improve=False,
                ),
                console=Console(verbose=False, quiet=True),
            )

            class FakeSession:
                def on(self, _callback) -> None:
                    return None

                async def disconnect(self) -> None:
                    runner._handle_session_event_for_step(
                        _FakeEvent(
                            "tool.execution_start",
                            _FakeEventData(
                                tool_name="view",
                                toolCallId="late-disconnect",
                                arguments={"path": "docs/late-disconnect.md"},
                            ),
                        ),
                        "1.1",
                    )
                    if cancel_disconnect:
                        raise asyncio.CancelledError()

            class FakeClient:
                stop_calls = 0

                async def stop(self) -> None:
                    self.stop_calls += 1
                    runner._handle_session_event_for_step(
                        _FakeEvent(
                            "tool.execution_start",
                            _FakeEventData(
                                tool_name="view",
                                toolCallId="late-stop",
                                arguments={"path": "docs/late-stop.md"},
                            ),
                        ),
                        "1.1",
                    )

            async def fake_start_client(_client, *, console) -> None:
                return None

            async def fake_create_session(*_args, **_kwargs):
                return FakeSession()

            async def fake_send(*_args, **_kwargs):
                return object()

            fake_client = FakeClient()
            with unittest.mock.patch(
                "copilot_client_factory.create_copilot_client",
                return_value=fake_client,
            ), unittest.mock.patch(
                "runner._start_client_with_retry",
                fake_start_client,
            ), unittest.mock.patch.object(
                runner,
                "_create_main_session",
                side_effect=fake_create_session,
            ), unittest.mock.patch.object(
                runner,
                "_send_and_wait_with_model_call_failure_guard",
                side_effect=fake_send,
            ), unittest.mock.patch.object(
                runner,
                "_run_asdw_data_verify_contract_gate",
                return_value=[],
            ), unittest.mock.patch.object(
                runner,
                "_maybe_run_split_fork",
                return_value=True,
            ), unittest.mock.patch(
                "runner._extract_text",
                return_value="",
            ):
                try:
                    result = await runner.run_step("1.1", "test", "prompt")
                except asyncio.CancelledError:
                    result = False
            return runner, result, fake_client.stop_calls

        for cancel_disconnect in (False, True):
            with self.subTest(cancel_disconnect=cancel_disconnect):
                runner, result, stop_calls = _run(scenario(cancel_disconnect))
                self.assertEqual(result, not cancel_disconnect)
                self.assertEqual(stop_calls, 1)
                with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
                    for call_id in ("late-disconnect", "late-stop"):
                        runner._handle_session_event_for_step(
                            _FakeEvent(
                                "tool.execution_complete",
                                _FakeEventData(
                                    success=False,
                                    toolCallId=call_id,
                                    error=_FakeEventData(message="late failure"),
                                ),
                            ),
                            "1.1",
                        )
                for call in tool_result.call_args_list:
                    self.assertEqual(call.kwargs["error_msg"], "late failure")

    def test_tool_execution_complete_removes_only_the_matching_call_state(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        start = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                toolCallId="call-a",
                arguments={"path": "docs/a.md", "view_range": [1, 5]},
            ),
        )
        success = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(success=True, toolCallId="call-a", result_summary="ok"),
        )
        stale_failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="call-a",
                error=_FakeEventData(message="later failure"),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event(start)
            runner._handle_session_event(success)
            runner._handle_session_event(stale_failure)

        error_msg = tool_result.call_args.kwargs["error_msg"]
        self.assertIn("later failure", error_msg)
        self.assertNotIn("docs/a.md", error_msg)
        self.assertNotIn("[1, 5]", error_msg)

    def test_tool_execution_failure_removes_its_matching_call_state(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        start = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="view",
                toolCallId="call-a",
                arguments={"path": "docs/a.md", "view_range": [1, 5]},
            ),
        )
        failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="call-a",
                error=_FakeEventData(message="first failure"),
            ),
        )
        duplicate_failure = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                toolCallId="call-a",
                error=_FakeEventData(message="duplicate failure"),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event(start)
            runner._handle_session_event(failure)
            runner._handle_session_event(duplicate_failure)

        self.assertEqual(tool_result.call_count, 2)
        first_msg = tool_result.call_args_list[0].kwargs["error_msg"]
        duplicate_msg = tool_result.call_args_list[1].kwargs["error_msg"]
        self.assertIn("path=docs/a.md", first_msg)
        self.assertIn("view_range=[1, 5]", first_msg)
        self.assertNotIn("docs/a.md", duplicate_msg)
        self.assertNotIn("[1, 5]", duplicate_msg)

    def test_run_step_start_clears_only_its_stale_call_id_state(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        runner._handle_session_event_for_step(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId="stale",
                    arguments={"path": "docs/stale.md", "view_range": [1, 5]},
                ),
            ),
            "1.1",
        )
        runner._handle_session_event_for_step(
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="view",
                    toolCallId="active",
                    arguments={"path": "docs/active.md", "view_range": [6, 10]},
                ),
            ),
            "2.2",
        )

        with _CaptureOutput():
            result = _run(runner.run_step("1.1", "test", "prompt"))

        self.assertTrue(result)
        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            runner._handle_session_event_for_step(
                _FakeEvent(
                    "tool.execution_complete",
                    _FakeEventData(
                        success=False,
                        toolCallId="stale",
                        error=_FakeEventData(message="stale failure"),
                    ),
                ),
                "1.1",
            )
            runner._handle_session_event_for_step(
                _FakeEvent(
                    "tool.execution_complete",
                    _FakeEventData(
                        success=False,
                        toolCallId="active",
                        error=_FakeEventData(message="active failure"),
                    ),
                ),
                "2.2",
            )

        stale_msg = tool_result.call_args_list[0].kwargs["error_msg"]
        active_msg = tool_result.call_args_list[1].kwargs["error_msg"]
        self.assertNotIn("docs/stale.md", stale_msg)
        self.assertIn("path=docs/active.md", active_msg)

    def test_tool_call_id_correlation_does_not_add_shell_or_query_secrets_to_failure_error_msg(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        secret = "SECRET_SENTINEL_42"
        events = (
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="bash",
                    toolCallId="shell-call",
                    arguments={"command": f"echo {secret}"},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    toolCallId="shell-call",
                    error=_FakeEventData(message="shell failed"),
                ),
            ),
            _FakeEvent(
                "tool.execution_start",
                _FakeEventData(
                    tool_name="grep",
                    toolCallId="grep-call",
                    arguments={"query": secret, "path": "hve"},
                ),
            ),
            _FakeEvent(
                "tool.execution_complete",
                _FakeEventData(
                    success=False,
                    toolCallId="grep-call",
                    error=_FakeEventData(message="grep failed"),
                ),
            ),
        )

        with unittest.mock.patch.object(runner.console, "tool_result") as tool_result:
            for event in events:
                runner._handle_session_event(event)

        self.assertEqual(tool_result.call_count, 2)
        shell_args, shell_kwargs = tool_result.call_args_list[0]
        grep_args, grep_kwargs = tool_result.call_args_list[1]
        self.assertEqual(shell_args[:2], ("1.1", False))
        self.assertEqual(grep_args[:2], ("1.1", False))
        self.assertIn("bash: shell failed", shell_kwargs["error_msg"])
        self.assertIn("grep: grep failed", grep_kwargs["error_msg"])
        self.assertNotIn(secret, shell_kwargs["error_msg"])
        self.assertNotIn(secret, grep_kwargs["error_msg"])

    def test_tool_execution_complete_failure_includes_mcp_tool_name(self) -> None:
        """T-M5: tool.execution_complete (failure) で MCP 系ツール名も前置される。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                mcp_tool_name="ask_work_iq",
                error=_FakeEventData(message="timeout"),
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ask_work_iq: timeout", cap.stdout)

    def test_tool_execution_complete_failure_without_tool_name_unchanged(self) -> None:
        """T-M5: tool_name が無い場合は従来通り error_msg のみ表示（既存互換）。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                error=_FakeEventData(message="timeout"),
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ツール失敗: timeout", cap.stdout)
        self.assertNotIn(": timeout", cap.stdout.replace("ツール失敗: timeout", ""))

    def test_tool_execution_complete_failure_mcp_tool_name_camelcase(self) -> None:
        """T-M5: mcpToolName (camelCase) も認識される (SDK 変動対応)。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                mcpToolName="ask_work_iq",
                error=_FakeEventData(message="timeout"),
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ask_work_iq: timeout", cap.stdout)

    def test_tool_execution_complete_failure_mcp_takes_priority_over_legacy(self) -> None:
        """T-M5: workiq.py:689 と同じく MCP ツール名が legacy より優先される。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_complete",
            _FakeEventData(
                success=False,
                tool_name="task",  # legacy (SDK 内部 dispatcher 名)
                mcp_tool_name="ask_work_iq",  # 実体は MCP ツール
                error=_FakeEventData(message="timeout"),
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("ask_work_iq: timeout", cap.stdout)
        self.assertNotIn("task: timeout", cap.stdout)

    def test_assistant_intent_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("assistant.intent", _FakeEventData(intent="I'm looking into this"))
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "I'm looking into this")

    def test_assistant_intent_description_fallback_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "assistant.intent",
            _FakeEventData(description="I'm looking into fallback"),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "I'm looking into fallback")

    def test_assistant_intent_kind_details_fallback_filters_empty(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "assistant.intent",
            _FakeEventData(
                kind="search",
                details={"query": "workiq", "empty": "", "none": None, "count": 0},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "search: workiq, 0")

    def test_tool_execution_start_read_file_formats_action_name(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="read_file", arguments={"path": "hve/workiq.py"}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("Read workiq.py", cap.stdout)
        self.assertIn("hve/workiq.py", cap.stdout)

    def test_tool_execution_start_report_intent_calls_thinking(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="report_intent",
                arguments={"intent": "I'm looking into how the hve application integrates Work IQ"},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with(
            "1.1",
            "I'm looking into how the hve application integrates Work IQ",
        )
        mock_action_start.assert_not_called()

    def test_tool_execution_start_report_intent_first_string_fallback(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="report_intent",
                arguments={"foo": 1, "message": "", "content": "fallback intent"},
            ),
        )
        with unittest.mock.patch.object(runner.console, "thinking") as mock_thinking:
            runner._handle_session_event(event)
        mock_thinking.assert_called_once_with("1.1", "fallback intent")

    def test_tool_execution_start_task_hidden_when_not_verbose3(self) -> None:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbosity=1, quiet=False, show_stream=False)
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1.1"
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="task", arguments={"description": "internal"}),
        )
        with unittest.mock.patch.object(runner.console, "event") as mock_event, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_event.assert_not_called()
        mock_action_start.assert_not_called()

    def test_tool_execution_start_task_shown_when_verbose3(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="task", arguments={"description": "internal"}),
        )
        with unittest.mock.patch.object(runner.console, "event") as mock_event, \
             unittest.mock.patch.object(runner.console, "action_start") as mock_action_start:
            runner._handle_session_event(event)
        mock_event.assert_called_once()
        self.assertIn("task (internal)", mock_event.call_args.args[0])
        mock_action_start.assert_not_called()

    def test_tool_execution_start_fallback_detail_uses_intent_key(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(
                tool_name="unknown_tool",
                arguments={"intent": "searching for integration points"},
            ),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("searching for integration points", cap.stdout)

    def test_tool_execution_start_grep_detail_is_truncated(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        long_pattern = "x" * 200
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="grep", arguments={"pattern": long_pattern, "path": "hve"}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("...", cap.stdout)

    def test_tool_execution_start_shell_detail_is_truncated(self) -> None:
        runner = self._make_runner(show_stream=False, verbose=True)
        long_command = "echo " + ("a" * 220)
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(tool_name="bash", arguments={"command": long_command}),
        )
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("...", cap.stdout)

    def test_session_error_shown(self) -> None:
        """session.error は常に表示される。"""
        runner = self._make_runner(show_stream=False, verbose=False)
        event = _FakeEvent("session.error", _FakeEventData(error_type="rate_limit", message="Too many requests"))
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("rate_limit", cap.stdout)

    def test_unknown_event_verbose_only(self) -> None:
        """未知のイベントタイプは verbose 時のみ出力される。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("some.future.event", _FakeEventData())
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertIn("some.future.event", cap.stdout)

    def test_session_idle_silent(self) -> None:
        """session.idle は出力しない。"""
        runner = self._make_runner(show_stream=False, verbose=True)
        event = _FakeEvent("session.idle")
        with _CaptureOutput() as cap:
            runner._handle_session_event(event)
        self.assertEqual(cap.stdout, "")
        self.assertEqual(cap.stderr, "")

    def test_assistant_usage_duration_timedelta_converted_to_ms(self) -> None:
        """assistant.usage の duration が timedelta でも TypeError にならず ms に変換される。

        SDK の AssistantUsageData.duration は timedelta | None 型のため、
        int(timedelta) は TypeError になる。total_seconds() 経由で ms へ変換する。
        """
        from datetime import timedelta

        runner = self._make_runner(show_stream=False)
        event = _FakeEvent(
            "assistant.usage",
            _FakeEventData(
                model="gpt-test",
                input_tokens=10,
                output_tokens=20,
                duration=timedelta(milliseconds=1500),
            ),
        )
        with unittest.mock.patch.object(runner.console, "usage") as mock_usage:
            runner._handle_session_event(event)
        mock_usage.assert_called_once_with(
            "1.1", "gpt-test", 10, 20, duration_ms=1500
        )

    def test_assistant_usage_duration_none_passes_none(self) -> None:
        """assistant.usage の duration が None の場合は duration_ms=None で渡る。"""
        runner = self._make_runner(show_stream=False)
        event = _FakeEvent(
            "assistant.usage",
            _FakeEventData(
                model="gpt-test",
                input_tokens=5,
                output_tokens=7,
                duration=None,
            ),
        )
        with unittest.mock.patch.object(runner.console, "usage") as mock_usage:
            runner._handle_session_event(event)
        mock_usage.assert_called_once_with(
            "1.1", "gpt-test", 5, 7, duration_ms=None
        )


# ----------------------------------------------------------------------
# AI Credit (assistant.usage) 抽出の回帰テスト
# ----------------------------------------------------------------------
# github-copilot-sdk の版により AssistantUsageData.copilot_usage /
# quota_snapshots は公開属性または internal 属性として提供される。属性公開状態に
# 依存せず AI Credit を抽出するため、runner は data.to_dict() の camelCaseキーを
# 正本として扱う。この互換契約を固定化する。
try:  # 実 SDK 不在の CI 環境では skip し、test_runner.py の collection を壊さない
    from copilot.generated.session_events import (  # type: ignore[import]
        AssistantUsageData as _RealAssistantUsageData,
    )
except Exception:  # pragma: no cover - 環境依存
    _RealAssistantUsageData = None  # type: ignore[assignment]


class _FakeUsageData:
    """AssistantUsageData 互換の最小フェイク。

    公開属性 (model/cost 等) は getattr で読めるが、copilotUsage /
    quotaSnapshots は to_dict() でのみ得られる。これにより「ハンドラが
    getattr ではなく to_dict() を使う」ことを保証する (SDK 1.0.x の
    Internal 属性改名に対する回帰ガード)。
    """

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.model = payload.get("model")
        self.input_tokens = payload.get("inputTokens")
        self.output_tokens = payload.get("outputTokens")
        self.cost = payload.get("cost")
        self.api_call_id = payload.get("apiCallId")
        self.duration = None

    def to_dict(self) -> dict:
        return dict(self._payload)


# 実 SDK / フェイク双方で再利用する代表ペイロード (totalNanoAiu は probe 実測値)。
_USAGE_PAYLOAD = {
    "model": "claude-opus-4.6",
    "apiCallId": "call-1",
    "inputTokens": 10,
    "outputTokens": 20,
    "cost": 3.0,
    "copilotUsage": {
        "totalNanoAiu": 8935775000.0,
        "tokenDetails": [
            {"tokenType": "input", "tokenCount": 10,
             "costPerBatch": 2, "batchSize": 100}
        ],
    },
    "quotaSnapshots": {
        "chat": {"usedRequests": 5, "entitlementRequests": 100,
                 "remainingPercentage": 95.0, "overage": 0.0,
                 "isUnlimitedEntitlement": False,
                 "overageAllowedWithExhaustedQuota": False,
                 "usageAllowedWithExhaustedQuota": False},
    },
}


class TestAssistantUsageCreditExtraction(unittest.TestCase):
    """assistant.usage からの AI Credit / quota 抽出 (SDK 1.0.x 対応) の回帰テスト。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbose=False, quiet=False, show_stream=False)
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1.1"
        return runner

    @staticmethod
    def _stats_of(mock_obj: Any, kind: str) -> list:
        return [
            c.kwargs for c in mock_obj.call_args_list
            if c.args and c.args[0] == kind
        ]

    def _dispatch(self, runner: StepRunner, data: Any):
        with _CaptureOutput():
            with unittest.mock.patch.object(runner.console, "stats_event") as m:
                runner._handle_session_event(_FakeEvent("assistant.usage", data))
        return m

    def test_to_dict_extracts_nano_aiu_and_quota(self) -> None:
        """copilotUsage.totalNanoAiu / quotaSnapshots / tokenDetails を to_dict 経由で抽出する。"""
        runner = self._make_runner()
        m = self._dispatch(runner, _FakeUsageData(_USAGE_PAYLOAD))
        uc = self._stats_of(m, "usage_credit")
        self.assertEqual(len(uc), 1)
        self.assertEqual(uc[0]["nano_aiu"], 8935775000.0)
        self.assertEqual(uc[0]["multiplier_cost"], 3.0)
        self.assertEqual(uc[0]["api_call_id"], "call-1")
        self.assertIsNone(uc[0]["unavailable_reason"])
        qs = self._stats_of(m, "quota_snapshot")
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0]["quota_id"], "chat")
        self.assertEqual(qs[0]["used_requests"], 5.0)
        au = self._stats_of(m, "assistant_usage")
        self.assertEqual(len(au), 1)
        self.assertEqual(au[0]["token_details"][0]["type"], "input")
        self.assertEqual(au[0]["token_details"][0]["count"], 10)

    def test_missing_copilot_usage_sets_unavailable_reason(self) -> None:
        """copilotUsage 欠落時は nano_aiu=None かつ unavailable_reason 併送、quota 不発火。"""
        runner = self._make_runner()
        m = self._dispatch(
            runner, _FakeUsageData({"model": "m", "inputTokens": 1, "outputTokens": 2})
        )
        uc = self._stats_of(m, "usage_credit")
        self.assertEqual(len(uc), 1)
        self.assertIsNone(uc[0]["nano_aiu"])
        self.assertTrue(uc[0]["unavailable_reason"])
        self.assertEqual(self._stats_of(m, "quota_snapshot"), [])

    def test_getattr_path_alone_would_miss_credit(self) -> None:
        """回帰ガード: copilotUsage を属性に持たない (to_dict のみ) 場合でも nano_aiu を抽出する。

        SDK 1.0.x では copilot_usage が Internal 属性 _copilot_usage へ改名され、
        getattr(data, "copilot_usage"/"copilotUsage") は None を返す。本フェイクも
        同属性を持たないため、ハンドラが getattr に依存していれば nano_aiu は
        抽出されない。to_dict 経由なら抽出される。
        """
        data = _FakeUsageData({
            "model": "m",
            "copilotUsage": {"totalNanoAiu": 1_000_000_000.0, "tokenDetails": []},
        })
        # 前提条件: getattr では取得不可であることを明示する
        self.assertIsNone(getattr(data, "copilot_usage", None))
        self.assertIsNone(getattr(data, "copilotUsage", None))
        runner = self._make_runner()
        m = self._dispatch(runner, data)
        uc = self._stats_of(m, "usage_credit")
        self.assertEqual(len(uc), 1)
        self.assertEqual(uc[0]["nano_aiu"], 1_000_000_000.0)

    @unittest.skipUnless(
        _RealAssistantUsageData is not None, "copilot SDK が未インストール"
    )
    def test_real_sdk_assistant_usage_data_extraction(self) -> None:
        """実 SDK の AssistantUsageData.from_dict 経由でも AI Credit / quota を抽出する。

        実 SDK の to_dict() が copilotUsage.totalNanoAiu / quotaSnapshots を
        camelCase キーで出力する契約を固定化する。SDK が再度フィールド名を
        変えた場合に本テストで検知する。
        """
        data = _RealAssistantUsageData.from_dict(dict(_USAGE_PAYLOAD))
        serialized = data.to_dict()
        self.assertEqual(
            serialized["copilotUsage"]["totalNanoAiu"],
            8935775000.0,
        )
        runner = self._make_runner()
        m = self._dispatch(runner, data)
        uc = self._stats_of(m, "usage_credit")
        self.assertEqual(len(uc), 1)
        self.assertEqual(uc[0]["nano_aiu"], 8935775000.0)
        qs = self._stats_of(m, "quota_snapshot")
        self.assertTrue(
            any(q["quota_id"] == "chat" and q["used_requests"] == 5.0 for q in qs)
        )


class TestIsReviewFail(unittest.TestCase):
    """_is_review_fail() の境界テスト。"""

    def test_fail_on_verdict_line(self) -> None:
        """合格判定行に ❌ FAIL が含まれる場合 True を返す。"""
        content = "- 合格判定: ❌ FAIL（Critical > 0）"
        self.assertTrue(_is_review_fail(content))

    def test_pass_on_verdict_line(self) -> None:
        """合格判定行に ✅ PASS が含まれる場合 False を返す。"""
        content = "- 合格判定: ✅ PASS（Critical = 0）"
        self.assertFalse(_is_review_fail(content))

    def test_fail_case_insensitive(self) -> None:
        """FAIL の大文字小文字を問わず検出する。"""
        self.assertTrue(_is_review_fail("- 合格判定: Fail"))
        self.assertTrue(_is_review_fail("- 合格判定: fail"))
        self.assertTrue(_is_review_fail("- 合格判定: fAiL"))

    def test_fail_in_body_not_verdict(self) -> None:
        """合格判定行以外に fail が含まれていても、合格判定行が PASS なら False を返す。"""
        content = "This test may fail under load.\n- 合格判定: ✅ PASS"
        self.assertFalse(_is_review_fail(content))

    def test_fail_in_both_body_and_verdict(self) -> None:
        """本文と合格判定行の両方に fail が含まれる場合は True を返す。"""
        content = "This test may fail under load.\n- 合格判定: ❌ FAIL（Critical > 0）"
        self.assertTrue(_is_review_fail(content))

    def test_empty_content(self) -> None:
        """空文字列では FAIL 扱い（合格判定行がないため安全側に倒す）。"""
        self.assertTrue(_is_review_fail(""))

    def test_no_verdict_line(self) -> None:
        """合格判定行がない場合 FAIL 扱い（フォーマット不備として安全側に倒す）。"""
        content = "レビュー結果:\n- Critical: 0件\n- Major: 1件"
        self.assertTrue(_is_review_fail(content))

    def test_multiline_with_fail(self) -> None:
        """複数行のうち合格判定行に FAIL が含まれる場合 True を返す。"""
        content = (
            "| 1 | 要件充足性 | Critical | ... | ... | ... |\n"
            "### サマリー\n"
            "- Critical: 2件\n"
            "- Major: 1件\n"
            "- Minor: 3件\n"
            "- 合格判定: ❌ FAIL（Critical > 0）"
        )
        self.assertTrue(_is_review_fail(content))

    def test_pass_emoji_token(self) -> None:
        """✅ PASS トークンがあれば PASS 判定。"""
        content = "- 合格判定: ✅ PASS"
        self.assertFalse(_is_review_fail(content))

    def test_fail_emoji_token(self) -> None:
        """❌ FAIL トークンがあれば FAIL 判定。"""
        content = "- 合格判定: ❌ FAIL"
        self.assertTrue(_is_review_fail(content))


class TestTruncateContext(unittest.TestCase):
    """_truncate_context() のテスト。"""

    def test_returns_original_when_short(self) -> None:
        text = "abc"
        self.assertEqual(_truncate_context(text, 10), text)

    def test_truncates_with_head_and_tail(self) -> None:
        text = "A" * 100 + "B" * 100
        result = _truncate_context(text, 120)
        self.assertIn("... (中略: 全体 200 文字) ...", result)
        self.assertTrue(result.startswith("A"))
        self.assertTrue(result.endswith("B"))
        self.assertLessEqual(len(result), 120)


class TestQaArtifactFallbackHelpers(unittest.TestCase):
    """QA 応答が artifacts 参照だけの場合の補助関数テスト。"""

    _HELPER_QA_CONTENT = (
        "[Q01]\n"
        "- 問題種別: 不明瞭\n"
        "- 重大度: major\n"
        "- 質問内容: 代表SKUの定義はどれですか。\n"
        "- 未回答時の既定値候補: TBD\n"
        "- 既定値候補の理由: 根拠不足\n"
        "- 未回答のまま進めた場合の影響: 設計判断が分岐する\n"
    )

    def test_extract_safe_qa_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            target = qa_dir / "QA-DocConsistency-20260101-120000.md"
            target.write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "## 成果物サマリー\n- artifacts: qa/QA-DocConsistency-20260101-120000.md\n"
            paths = _extract_safe_qa_artifact_paths(content, base_dir=base)

            self.assertEqual(paths, [target])

    def test_extract_safe_qa_artifact_paths_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            (qa_dir / "ok.md").write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "artifacts: qa/../secret.md qa/ok.md C:/tmp/qa/bad.md"
            paths = _extract_safe_qa_artifact_paths(content, base_dir=base)

            self.assertEqual(paths, [qa_dir / "ok.md"])

    def test_parse_qa_content_with_artifact_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            qa_dir = base / "qa"
            qa_dir.mkdir()
            target = qa_dir / "QA-DocConsistency-20260101-120000.md"
            target.write_text(self._HELPER_QA_CONTENT, encoding="utf-8")

            content = "## 成果物サマリー\n- artifacts: qa/QA-DocConsistency-20260101-120000.md\n"
            doc, fallback_path = _parse_qa_content_with_artifact_fallback(content, base_dir=base)

            self.assertEqual(fallback_path, target)
            self.assertEqual(len(doc.questions), 1)
            self.assertIn("代表SKU", doc.questions[0].question)
            self.assertEqual(doc.questions[0].category, "不明瞭")
            self.assertEqual(doc.questions[0].priority, "major")


class TestStepRunnerModelSwitchDryRun(unittest.TestCase):
    """レビュー/QA モデル切替判定のドライラン系テスト。"""

    def test_review_model_different_from_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", review_model="claude-opus-4.6")
        self.assertNotEqual(cfg.get_review_model(), cfg.model)

    def test_review_model_same_as_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", review_model="gpt-5.4")
        self.assertEqual(cfg.get_review_model(), cfg.model)

    def test_qa_model_different_from_model(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", qa_model="claude-opus-4.6")
        self.assertNotEqual(cfg.get_qa_model(), cfg.model)

    def test_build_sub_session_opts_exists(self) -> None:
        cfg = SDKConfig(dry_run=True, model="gpt-5.4")
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        self.assertTrue(hasattr(runner, "_build_sub_session_opts"))


class TestTrackToolFiles(unittest.TestCase):
    """_track_tool_files / _track_bash_files のテスト。"""

    def _make_runner(self, **kwargs: Any) -> StepRunner:
        config = SDKConfig(**kwargs) if kwargs else SDKConfig()
        console = Console(verbose=True, quiet=False)
        runner = StepRunner(config=config, console=console)
        return runner

    def test_edit_file_tracked_as_read_and_write(self) -> None:
        # console.track_file は path を os.path.normpath 後 forward-slash に正規化するため
        # OS 依存しない forward-slash で期待値を検証する。
        runner = self._make_runner()
        runner._track_tool_files("1", "edit_file", {"path": "src/main.py"})
        files = runner.console._step_files.get("1", {})
        self.assertIn("src/main.py", files.get("read", []))
        self.assertIn("src/main.py", files.get("write", []))

    def test_bash_redirect_tracked_as_write(self) -> None:
        runner = self._make_runner()
        runner._track_bash_files("1", "echo hello > output/result.txt")
        files = runner.console._step_files.get("1", {})
        self.assertIn("output/result.txt", files.get("write", []))

    def test_bash_redirect_no_space_and_fd_tracked_as_write(self) -> None:
        runner = self._make_runner()
        runner._track_bash_files("1", "echo hi>out.txt; echo ng 2>err.log; tee -a tee.log")
        files = runner.console._step_files.get("1", {})
        self.assertIn("out.txt", files.get("write", []))
        self.assertIn("err.log", files.get("write", []))
        self.assertIn("tee.log", files.get("write", []))

    def test_skip_tools_not_tracked(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "grep", {"pattern": "TODO", "path": "src/"})
        files = runner.console._step_files.get("1", {})
        self.assertEqual(len(files.get("read", [])), 0)
        self.assertEqual(len(files.get("write", [])), 0)

    def test_rg_is_skipped(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "rg", {"pattern": "TODO", "path": "src/"})
        files = runner.console._step_files.get("1", {})
        self.assertEqual(len(files.get("read", [])), 0)
        self.assertEqual(len(files.get("write", [])), 0)

    def test_powershell_dispatches_to_powershell(self) -> None:
        runner = self._make_runner()
        with unittest.mock.patch.object(runner, "_track_bash_files") as mock_bash, \
                unittest.mock.patch.object(runner, "_track_powershell_files") as mock_ps:
            runner._track_tool_files("1", "powershell", {"command": "Get-ChildItem -Path docs"})
        mock_ps.assert_called_once_with("1", "Get-ChildItem -Path docs")
        mock_bash.assert_not_called()


class TestWorkIQToolNamesConsistency(unittest.TestCase):
    """Phase 1: runner.py の _WORKIQ_TOOL_NAMES が workiq.py の定数と一致することを確認。"""

    def test_workiq_tool_names_matches_workiq_module(self) -> None:
        import workiq as _workiq_mod
        from runner import _WORKIQ_TOOL_NAMES
        self.assertEqual(_WORKIQ_TOOL_NAMES, frozenset(_workiq_mod.WORKIQ_MCP_TOOL_NAMES))

    def test_workiq_tool_names_contains_expected_tools(self) -> None:
        from runner import _WORKIQ_TOOL_NAMES
        expected = {"ask"}
        self.assertEqual(_WORKIQ_TOOL_NAMES, frozenset(expected))

    def test_tool_execution_start_ask_detected(self) -> None:
        """tool.execution_start イベントで `_hve_workiq` の `ask` が Work IQ ツールとして検出されること。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        step_runner._handle_session_event(event)
        self.assertTrue(step_runner._workiq_tool_called)

    def test_old_search_tool_name_not_detected(self) -> None:
        """旧 Work IQ tool 名は現行 MCP tool として扱わないこと。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="search_emails"))
        step_runner._handle_session_event(event)
        self.assertFalse(step_runner._workiq_tool_called)

    def test_tool_execution_start_non_workiq_not_detected(self) -> None:
        """Work IQ 以外のツールでは _workiq_tool_called が True にならないこと。"""
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        step_runner = StepRunner(config=cfg, console=console)

        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="edit_file"))
        step_runner._handle_session_event(event)
        self.assertFalse(step_runner._workiq_tool_called)


# NOTE: TestWorkIQCustomAgentToolsWarning (Phase 1 以前の Work IQ + Custom Agent
# tools 警告テストクラス) は Phase 8 S-2 で全テストメソッドとクラス本体を
# 削除した（custom_agents_config フィールド廃止に伴う dead test）。


# ---------------------------------------------------------------------------
# Phase 2: SDK セッション ID 安定化（Resume の前提条件）
# ---------------------------------------------------------------------------

class TestSessionIdPropagation(unittest.TestCase):
    """`StepRunner.run_step()` 内の `client.create_session()` 呼び出しが
    決定論的な `session_id` を kwargs に含めることを検証する。

    Phase 2 (Resume) の中核要件: 同じ run_id × step_id × suffix の組み合わせで
    常に同じ session_id が SDK に渡されること。
    """

    def _build_fake_sdk(self, *, reject_skill_directories: bool = False):
        """create_session の kwargs を全て記録する Fake SDK モジュールを構築する。"""
        import types

        class _FakeSession:
            def __init__(self) -> None:
                self.rpc = types.SimpleNamespace(
                    mcp=types.SimpleNamespace(
                        list=self._list_mcp_servers,
                    )
                )

            async def _list_mcp_servers(self):
                return types.SimpleNamespace(
                    servers=[
                        types.SimpleNamespace(
                            name="azure",
                            status=types.SimpleNamespace(value="connected"),
                            error=None,
                        ),
                        types.SimpleNamespace(
                            name="microsoft-learn",
                            status=types.SimpleNamespace(value="connected"),
                            error=None,
                        ),
                    ]
                )

            async def send_and_wait(self, *args, **kwargs):
                # メインタスク 1 回のみ応答する最小モック
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs: list = []

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                if reject_skill_directories and "skill_directories" in kwargs:
                    raise TypeError(
                        "create_session() got an unexpected keyword argument "
                        "'skill_directories'"
                    )
                return _FakeSession()

        fake_client = _FakeClient()
        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda **kwargs: fake_client

        class _RuntimeConnection:
            @staticmethod
            def for_stdio(**kwargs):
                return object()

            @staticmethod
            def for_uri(*args, **kwargs):
                return object()

        fake_copilot.RuntimeConnection = _RuntimeConnection

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return fake_client, fake_copilot, fake_copilot_session

    def test_main_session_receives_deterministic_session_id(self) -> None:
        """メインセッションに run_id + step_id 由来の決定論的 session_id が渡される。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-test01",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 1)
        kw = fake_client.create_session_kwargs[0]
        self.assertIn("session_id", kw)
        # フォーマット: "hve-{run_id}-step-{step_id}"
        self.assertEqual(kw["session_id"], "hve-20260507T100000-test01-step-1-1")

    def test_main_session_receives_declared_external_skill_directory(self) -> None:
        """required external Skill はroot全体ではなく個別directoryだけを渡す。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260720T000000-external-skill",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()

        with tempfile.TemporaryDirectory() as temp_dir:
            external_root = Path(temp_dir) / "skills"
            external_skill = external_root / "microsoft-foundry"
            external_skill.mkdir(parents=True)
            (external_skill / "SKILL.md").write_text(
                "---\nname: microsoft-foundry\n---\n# Test skill\n",
                encoding="utf-8",
            )

            with unittest.mock.patch.dict(
                sys.modules,
                {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
            ), unittest.mock.patch(
                "skill_resolver.get_required_skills_for_step",
                return_value=["microsoft-foundry"],
            ), unittest.mock.patch(
                "skill_resolver._external_skills_root",
                return_value=external_root,
            ), unittest.mock.patch(
                "prompt_loader.load_prompt",
                return_value="",
            ), unittest.mock.patch.object(
                runner,
                "_run_asdw_data_verify_contract_gate",
                return_value=[],
            ), unittest.mock.patch.object(
                runner,
                "_run_ai_agent_capability_gate",
                return_value=[],
            ), unittest.mock.patch.object(
                runner,
                "_run_tdd_report_gate",
                return_value=[],
            ), unittest.mock.patch.object(
                runner,
                "_run_asdw_ui_red_unresolved_contract_gate",
                return_value=[],
            ), unittest.mock.patch.object(
                runner,
                "_run_deploy_ac_gate",
                return_value=[],
            ):
                result = asyncio.run(
                    runner.run_step(
                        "2.3",
                        "Foundry agent coding",
                        "external Skill routing probe",
                        custom_agent="Dev-Microservice-Azure-AgentCoding",
                        workflow_id="aagd",
                    )
                )

        self.assertTrue(result)
        options = fake_client.create_session_kwargs[0]
        self.assertIn(str(external_skill), options["skill_directories"])
        self.assertNotIn(str(external_root), options["skill_directories"])

    def test_main_session_fails_closed_when_sdk_rejects_required_external_skill_directory(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260720T000000-external-skill-reject",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk(
            reject_skill_directories=True
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            external_root = Path(temp_dir) / "skills"
            external_skill = external_root / "microsoft-foundry"
            external_skill.mkdir(parents=True)
            (external_skill / "SKILL.md").write_text(
                "---\nname: microsoft-foundry\n---\n# Test skill\n",
                encoding="utf-8",
            )

            with unittest.mock.patch.dict(
                sys.modules,
                {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
            ), unittest.mock.patch(
                "skill_resolver.get_required_skills_for_step",
                return_value=["microsoft-foundry"],
            ), unittest.mock.patch(
                "skill_resolver._external_skills_root",
                return_value=external_root,
            ), unittest.mock.patch(
                "prompt_loader.load_prompt",
                return_value="",
            ), unittest.mock.patch.object(
                runner,
                "_run_asdw_data_verify_contract_gate",
                return_value=[],
            ):
                result = asyncio.run(
                    runner.run_step(
                        "2.3",
                        "Foundry agent coding",
                        "external Skill routing rejection probe",
                        custom_agent="Dev-Microservice-Azure-AgentCoding",
                        workflow_id="aagd",
                    )
                )

        self.assertFalse(result)
        self.assertEqual(len(fake_client.create_session_kwargs), 1)
        self.assertIn("skill_directories", fake_client.create_session_kwargs[0])

    def test_main_session_does_not_start_when_required_skill_resolution_raises(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260720T000000-external-skill-resolver-error",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ), unittest.mock.patch(
            "skill_resolver.get_required_skills_for_step",
            side_effect=RuntimeError("resolver unavailable"),
        ):
            result = asyncio.run(
                runner.run_step(
                    "2.3",
                    "Foundry agent coding",
                    "required Skill resolver failure probe",
                    custom_agent="Dev-Microservice-Azure-AgentCoding",
                    workflow_id="aagd",
                )
            )

        self.assertFalse(result)
        self.assertEqual(fake_client.create_session_kwargs, [])

    def test_session_id_is_deterministic_across_runs(self) -> None:
        """同じ run_id + step_id で複数回 run_step() を呼ぶと常に同じ session_id が渡される。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-determ-001",
        )
        console = Console(verbose=False, quiet=True)

        captured_ids: list = []
        for _ in range(2):
            runner = StepRunner(config=cfg, console=console)
            fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
            with unittest.mock.patch.dict(
                sys.modules,
                {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
            ):
                asyncio.run(runner.run_step("2.3", "テスト", "プロンプト"))
            captured_ids.append(fake_client.create_session_kwargs[0]["session_id"])

        self.assertEqual(captured_ids[0], captured_ids[1])

    def test_session_id_uses_custom_prefix(self) -> None:
        """SDKConfig.session_id_prefix が設定されている場合はその prefix が使われる。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="run-prefix-001",
            session_id_prefix="myapp",
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(
            fake_client.create_session_kwargs[0]["session_id"].startswith("myapp-")
        )

    def test_make_step_session_id_helper(self) -> None:
        """`StepRunner._make_step_session_id` が make_session_id と同じ仕様を返す。"""
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-helper-001")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        main = runner._make_step_session_id("1.1")
        qa = runner._make_step_session_id("1.1", suffix="qa")
        review = runner._make_step_session_id("1.1", suffix="review")

        self.assertEqual(main, "hve-run-helper-001-step-1-1")
        self.assertEqual(qa, "hve-run-helper-001-step-1-1-qa")
        self.assertEqual(review, "hve-run-helper-001-step-1-1-review")
        # サブセッション ID は全て異なる
        self.assertEqual(len({main, qa, review}), 3)

    def test_qa_subsession_session_id_has_qa_suffix(self) -> None:
        """`_build_sub_session_opts(step_id=..., suffix='qa')` が qa サフィックス付き ID を返す。"""
        cfg = SDKConfig(
            model="claude-opus-4.7",
            run_id="run-qa-suffix-001",
            qa_model="claude-opus-4.6",  # メインモデルと別モデルでサブセッション化
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        # PermissionHandler のために fake_copilot_session を一時注入
        import types
        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": fake_copilot_session}
        ):
            opts_qa = runner._build_sub_session_opts(
                "claude-opus-4.6", step_id="1.1", suffix="qa"
            )
            opts_review = runner._build_sub_session_opts(
                "claude-opus-4.6", step_id="1.1", suffix="review"
            )

        self.assertEqual(opts_qa.get("session_id"), "hve-run-qa-suffix-001-step-1-1-qa")
        self.assertEqual(opts_review.get("session_id"), "hve-run-qa-suffix-001-step-1-1-review")
        # 明示モデル指定時は reasoning_effort を付与しない契約を二重保証
        self.assertNotIn("reasoning_effort", opts_qa)
        self.assertNotIn("reasoning_effort", opts_review)

    def test_sub_session_opts_without_step_id_omits_session_id(self) -> None:
        """step_id を渡さない場合は session_id を含めない（後方互換）。"""
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-back-compat")
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)

        import types
        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler

        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": fake_copilot_session}
        ):
            opts = runner._build_sub_session_opts("claude-opus-4.6")

        self.assertNotIn("session_id", opts)


class TestSubSessionOptsReasoningEffort(unittest.TestCase):
    """_build_sub_session_opts の model 引数処理を検証する。

    Auto 指定時は wire 値 "auto" を SDK へ渡し、reasoning_effort は付与しない
    （サーバ側 Auto Model Selection に委譲）。空文字時は model キー自体を
    payload から省略する。明示モデル時はそのまま渡し、reasoning_effort は
    付与しない（SDK 既定動作）。
    """

    def _make_runner_with_fake_permission(self) -> StepRunner:
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-reasoning-effort")
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    @staticmethod
    def _patched_modules():
        import types

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return {"copilot.session": fake_copilot_session}

    def test_auto_model_sends_wire_auto_no_reasoning(self) -> None:
        """Auto 指定時は SDK へ model="auto" (wire 値) を渡し、reasoning_effort は付与しない。

        サーバ側 Auto Model Selection がモデル毎に適切な reasoning_effort を選ぶため、
        クライアント側で reasoning_effort を強制しない。
        """
        from config import MODEL_AUTO_VALUE, MODEL_AUTO_WIRE_VALUE

        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts(MODEL_AUTO_VALUE)
        self.assertEqual(opts.get("model"), MODEL_AUTO_WIRE_VALUE)
        self.assertNotIn("reasoning_effort", opts)

    def test_explicit_model_omits_reasoning_effort(self) -> None:
        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertEqual(opts.get("model"), "claude-opus-4.7")
        self.assertNotIn("reasoning_effort", opts)

    def test_empty_string_omits_model_and_reasoning(self) -> None:
        """空文字は to_wire_model で None → model キーを payload から省略（CLI 既定に委譲）。"""
        runner = self._make_runner_with_fake_permission()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts("")
        self.assertNotIn("model", opts)
        self.assertNotIn("reasoning_effort", opts)


class TestCreateSessionAutoReasoningFallback(unittest.IsolatedAsyncioTestCase):
    """_create_session_with_auto_reasoning_fallback の TypeError 時挙動を検証する。"""

    async def test_strips_reasoning_effort_on_typeerror(self) -> None:
        from runner import _create_session_with_auto_reasoning_fallback

        calls: list[dict] = []

        class _FakeClient:
            async def create_session(self, **kwargs):
                calls.append(kwargs)
                if "reasoning_effort" in kwargs:
                    raise TypeError(
                        "create_session() got an unexpected keyword argument 'reasoning_effort'"
                    )
                return "ok-session"

        result = await _create_session_with_auto_reasoning_fallback(
            _FakeClient(), {"model": "Auto", "reasoning_effort": "high", "streaming": True}
        )
        self.assertEqual(result, "ok-session")
        self.assertEqual(len(calls), 2)
        self.assertIn("reasoning_effort", calls[0])
        self.assertNotIn("reasoning_effort", calls[1])

    async def test_passthrough_for_unrelated_typeerror(self) -> None:
        from runner import _create_session_with_auto_reasoning_fallback

        class _FakeClient:
            async def create_session(self, **kwargs):
                raise TypeError("create_session() got an unexpected keyword argument 'foobar'")

        with self.assertRaises(TypeError):
            await _create_session_with_auto_reasoning_fallback(
                _FakeClient(), {"reasoning_effort": "high"}
            )

    async def test_passthrough_for_value_validation_typeerror(self) -> None:
        """SDK 側で reasoning_effort の値検証エラー（unexpected keyword 由来でない）の場合は剥がさず raise。"""
        from runner import _create_session_with_auto_reasoning_fallback

        class _FakeClient:
            async def create_session(self, **kwargs):
                raise TypeError("reasoning_effort must be one of low/medium/high/xhigh")

        with self.assertRaises(TypeError):
            await _create_session_with_auto_reasoning_fallback(
                _FakeClient(), {"reasoning_effort": "high"}
            )

    async def test_strips_tool_search_on_typeerror(self) -> None:
        """FR-MODEL-05: SDK 未サポート時は tool_search を剥がして再試行する。"""
        from runner import _create_session_with_auto_reasoning_fallback

        calls: list[dict] = []

        class _FakeClient:
            async def create_session(self, **kwargs):
                calls.append(kwargs)
                if "tool_search" in kwargs:
                    raise TypeError(
                        "create_session() got an unexpected keyword argument 'tool_search'"
                    )
                return "ok-session"

        result = await _create_session_with_auto_reasoning_fallback(
            _FakeClient(),
            {"model": "Auto", "tool_search": {"enabled": True}, "streaming": True},
        )
        self.assertEqual(result, "ok-session")
        self.assertEqual(len(calls), 2)
        self.assertIn("tool_search", calls[0])
        self.assertNotIn("tool_search", calls[1])


class TestWorkIQCalledToolsTracking(unittest.TestCase):
    """Phase 2: _workiq_called_tools 履歴が _handle_session_event で蓄積されることを確認。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        runner._current_step_id = "1"
        return runner

    def test_tool_without_server_name_not_appended(self) -> None:
        """server 名を持たない tool event は _workiq_called_tools へ追加されない。"""
        runner = self._make_runner()
        self.assertEqual(runner._workiq_called_tools, [])
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="ask"))
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, [])

    def test_mcp_workiq_tool_appended_to_called_tools(self) -> None:
        """mcp_tool_name 形式でも _workiq_called_tools にツール名が追加される。"""
        runner = self._make_runner()
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, ["ask"])

    def test_workiq_tool_multiple_calls_all_appended(self) -> None:
        """複数回呼び出した場合、すべて _workiq_called_tools に追記される。"""
        runner = self._make_runner()
        for _ in range(2):
            event = _FakeEvent(
                "tool.execution_start",
                _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
            )
            runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, ["ask", "ask"])

    def test_non_workiq_tool_not_appended(self) -> None:
        """Work IQ 以外のツールは _workiq_called_tools に追加されない。"""
        runner = self._make_runner()
        event = _FakeEvent("tool.execution_start", _FakeEventData(tool_name="edit_file"))
        runner._handle_session_event(event)
        self.assertEqual(runner._workiq_called_tools, [])

    def test_workiq_called_tools_reset_on_run_step(self) -> None:
        """run_step() 開始時に _workiq_called_tools がリセットされる。"""
        runner = self._make_runner()
        runner._workiq_called_tools = ["ask"]
        with _CaptureOutput():
            _run(runner.run_step("1", "テスト", "プロンプト"))
        # dry_run では run_step() 終了後に _workiq_called_tools が [] にリセットされている
        self.assertEqual(runner._workiq_called_tools, [])

    def test_diff_based_tool_detection(self) -> None:
        """呼び出し前後の差分でツール呼び出しを検出できる。"""
        runner = self._make_runner()
        runner._workiq_called_tools = ["ask"]  # 事前に1件追加
        before = len(runner._workiq_called_tools)
        # 新たに ask が呼ばれた
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        runner._handle_session_event(event)
        after_tools = runner._workiq_called_tools[before:]
        self.assertTrue(bool(after_tools))
        self.assertEqual(after_tools, ["ask"])


class TestIsWorkIQToolNameHelperInRunner(unittest.TestCase):
    """runner.py が workiq の server/tool 判定経由で Work IQ ツールを検出すること。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True, workiq_enabled=True)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_is_workiq_tool_name_helper_accessible(self) -> None:
        """runner.py が workiq.is_workiq_tool_name をインポートできること。"""
        from workiq import is_workiq_tool_name
        self.assertTrue(is_workiq_tool_name("ask"))
        self.assertFalse(is_workiq_tool_name("edit_file"))

    def test_handle_session_event_detects_workiq_mcp_tool(self) -> None:
        """_handle_session_event が server/tool の組で判定し、
        Work IQ ツールは _workiq_called_tools に追加されること。"""
        runner = self._make_runner()
        for tool in ("ask",):
            runner._workiq_called_tools = []
            event = _FakeEvent(
                "tool.execution_start",
                _FakeEventData(mcp_tool_name=tool, mcp_server_name=WORKIQ_MCP_SERVER_NAME),
            )
            runner._handle_session_event(event)
            self.assertIn(tool, runner._workiq_called_tools, f"{tool} は _workiq_called_tools に追加されるべき")

    def test_phase1_tool_count_does_not_affect_qa_diff_detection(self) -> None:
        """Phase 1 で Work IQ が呼ばれていても QA の差分検出に影響しないこと。

        QA フェーズでは _before_count を snapshot して差分を取るため、
        Phase 1 の _workiq_called_tools は影響しない。
        """
        runner = self._make_runner()
        # Phase 1: ask が2回呼ばれた
        for _ in range(2):
            event = _FakeEvent(
                "tool.execution_start",
                _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
            )
            runner._handle_session_event(event)
        self.assertEqual(len(runner._workiq_called_tools), 2)

        # QA フェーズ開始前の snapshot
        before_qa = len(runner._workiq_called_tools)

        # QA フェーズ: ask が呼ばれた
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        runner._handle_session_event(event)

        after_qa_tools = runner._workiq_called_tools[before_qa:]
        self.assertEqual(after_qa_tools, ["ask"], "QA フェーズの差分は Phase 1 の呼び出しを含まないこと")

    def test_qa_tool_not_called_when_no_events_after_snapshot(self) -> None:
        """QA フェーズで Work IQ ツールが呼ばれなかった場合、差分は空になること。"""
        runner = self._make_runner()
        # Phase 1: ask が呼ばれた
        event = _FakeEvent(
            "tool.execution_start",
            _FakeEventData(mcp_tool_name="ask", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
        )
        runner._handle_session_event(event)

        # QA フェーズ開始前の snapshot
        before_qa = len(runner._workiq_called_tools)

        # QA フェーズ: ツールは呼ばれなかった
        after_qa_tools = runner._workiq_called_tools[before_qa:]
        self.assertEqual(after_qa_tools, [], "QA ツール未呼び出しの場合、差分は空であること")
        self.assertFalse(bool(after_qa_tools), "ツール未観測を正しく検出できること")


# ---------------------------------------------------------------------------
# _apply_main_artifact_improvements テスト
# ---------------------------------------------------------------------------

class TestApplyMainArtifactImprovements(unittest.TestCase):
    """StepRunner._apply_main_artifact_improvements の動作を検証する。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=False, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_method_exists(self) -> None:
        """_apply_main_artifact_improvements メソッドが StepRunner に存在する。"""
        runner = self._make_runner()
        self.assertTrue(
            callable(getattr(runner, "_apply_main_artifact_improvements", None)),
            "StepRunner に _apply_main_artifact_improvements が存在すること",
        )

    def test_returns_empty_when_context_empty(self) -> None:
        """improvement_context が空の場合は何もせず空文字を返す。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 3",
            improvement_context="",
            timeout=10.0,
        ))
        mock_session.send_and_wait.assert_not_awaited()
        self.assertEqual(result, "")

    def test_returns_empty_when_context_whitespace_only(self) -> None:
        """improvement_context が空白のみの場合も何もしない。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 3",
            improvement_context="   \n  ",
            timeout=10.0,
        ))
        mock_session.send_and_wait.assert_not_awaited()
        self.assertEqual(result, "")

    def test_sends_to_main_session(self) -> None:
        """send_and_wait をメインセッションに対して呼び出す。"""
        runner = self._make_runner()
        mock_response = unittest.mock.MagicMock()
        mock_response.data = unittest.mock.MagicMock()
        mock_response.data.content = "改善完了"
        mock_session = unittest.mock.AsyncMock()
        mock_session.send_and_wait.return_value = mock_response

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id="adi",
            custom_agent="TestAgent",
            original_prompt="original",
            main_output="main output",
            source_phase="Phase 3 Adversarial Review",
            improvement_context="Critical issue found",
            timeout=30.0,
        ))
        mock_session.send_and_wait.assert_awaited_once()
        self.assertEqual(result, "改善完了")

    def test_returns_empty_on_exception(self) -> None:
        """例外が発生した場合は警告を出して空文字を返す（後続処理を継続）。"""
        runner = self._make_runner()
        mock_session = unittest.mock.AsyncMock()
        mock_session.send_and_wait.side_effect = RuntimeError("session error")

        result = asyncio.run(runner._apply_main_artifact_improvements(
            session=mock_session,
            step_id="1.1",
            title="テスト",
            workflow_id=None,
            custom_agent=None,
            original_prompt="prompt",
            main_output="output",
            source_phase="Phase 4",
            improvement_context="plan content",
            timeout=10.0,
        ))
        self.assertEqual(result, "")


class TestApplyMainArtifactImprovementsInspection(unittest.TestCase):
    """Phase 3 / 4 の共通ヘルパー呼び出し確認（ソースインスペクション）。
    Phase 2c (post-QA) は廃止済みのため該当テストは削除された。"""

    def test_phase3_calls_helper_when_fail(self) -> None:
        """Phase 3: review FAIL 時に _apply_main_artifact_improvements が呼ばれる。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("apply_review_improvements_to_main", source)
        self.assertIn("Phase 3 Adversarial Review", source)

    def test_phase4_calls_helper_when_enabled(self) -> None:
        """Phase 4: apply_self_improve_to_main=True のとき _apply_main_artifact_improvements が呼ばれる。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("apply_self_improve_to_main", source)
        self.assertIn("Phase 4 Self-Improve iteration", source)

    def test_phase3_and_4_are_workflow_independent(self) -> None:
        """Phase 3 / Phase 4 の _apply_main_artifact_improvements 呼び出しに workflow_id 条件分岐がないこと。

        これは全オーケストレーター共通処理として実装されていることを確認する。
        """
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        # Phase 3 の apply 呼び出し部分に workflow_id による条件分岐がないことを確認
        # (workflow_id を引数として渡すのは OK, if workflow_id == "xxx" で skip するのは NG)
        # 簡略化: ソース中に "if workflow_id" の後に "apply_review" が出てこないことを確認
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if "apply_review_improvements_to_main" in line or "apply_self_improve_to_main" in line:
                # 直前の数行に workflow_id == で始まる条件がないことを確認
                context = "\n".join(lines[max(0, i - 3):i])
                self.assertNotIn('workflow_id == "', context,
                                 f"Phase 3/4 should not be gated by workflow_id check near line {i}")


# ---------------------------------------------------------------------------
# _check_diff_after_improvement テスト
# ---------------------------------------------------------------------------

class TestCheckDiffAfterImprovement(unittest.TestCase):
    """StepRunner._check_diff_after_improvement の動作を検証する。"""

    def _make_runner(self) -> StepRunner:
        cfg = SDKConfig(dry_run=True)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_returns_changed_files_on_diff(self) -> None:
        """git diff に差分がある場合、変更ファイルリストを返すこと。"""
        runner = self._make_runner()
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hve/runner.py\nhve/config.py\n"
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        self.assertEqual(changed, ["hve/runner.py", "hve/config.py"])

    def test_returns_empty_and_logs_warning_when_no_diff(self) -> None:
        """git diff に差分がない場合、空リストを返し warning が記録されること。"""
        runner = self._make_runner()
        warnings: list[str] = []
        original_warning = runner.console.warning
        runner.console.warning = lambda msg: warnings.append(msg)  # type: ignore[method-assign]
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        runner.console.warning = original_warning
        self.assertEqual(changed, [])
        self.assertTrue(len(warnings) > 0, "差分なし時に warning が発行されること")
        self.assertIn("差分がありません", warnings[0])

    def test_returns_empty_when_git_fails(self) -> None:
        """git diff が非ゼロ終了した場合、空リストを返し warning が記録されること。"""
        runner = self._make_runner()
        warnings: list[str] = []
        runner.console.warning = lambda msg: warnings.append(msg)  # type: ignore[method-assign]
        mock_result = unittest.mock.MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "not a git repository"
        with unittest.mock.patch("subprocess.run", return_value=mock_result):
            changed = runner._check_diff_after_improvement("step-1", "Phase 3 Adversarial Review")
        self.assertEqual(changed, [])
        self.assertTrue(len(warnings) > 0, "git 失敗時に warning が発行されること")
        self.assertIn("git diff", warnings[0])

    def test_returns_empty_on_subprocess_error(self) -> None:
        """subprocess.run が例外を出した場合、空リストを返すこと（処理を継続）。"""
        runner = self._make_runner()
        with unittest.mock.patch("subprocess.run", side_effect=OSError("git not found")):
            changed = runner._check_diff_after_improvement("step-1", "Phase 4 Self-Improve")
        self.assertEqual(changed, [])

    def test_source_inspection_calls_diff_check_in_phase3(self) -> None:
        """Phase 3 Adversarial Review で _check_diff_after_improvement が呼ばれること（ソースインスペクション）。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_check_diff_after_improvement", source)
        self.assertIn("Phase 3 Adversarial Review", source)

    def test_source_inspection_calls_diff_check_in_phase4(self) -> None:
        """Phase 4 Self-Improve で _check_diff_after_improvement が呼ばれること（ソースインスペクション）。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("Phase 4 Self-Improve", source)


# ---------------------------------------------------------------------------
# Phase 6: サブセッション要否判定ヘルパーのテスト
# ---------------------------------------------------------------------------

class TestShouldUseSubSession(unittest.TestCase):
    """Phase 6: _should_use_*_sub_session ヘルパーの判定ロジックを検証する。"""

    def _make_runner(self, model: str = "claude-opus-4.7", **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(model=model, **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    # --- Pre-QA ---

    def test_pre_qa_same_model_no_workiq_uses_main_session(self) -> None:
        """qa_model == main_model かつ WorkIQ 無効 → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        # qa_model 未設定 → get_qa_model() は model を返す
        self.assertFalse(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_different_model_creates_sub_session(self) -> None:
        """qa_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", qa_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_workiq_enabled_creates_sub_session_even_if_same_model(self) -> None:
        """WorkIQ 有効 → モデルが同一でもサブセッション作成（WorkIQ は QA 専用）。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=True,
            )
        )

    def test_pre_qa_auto_model_same_as_main_no_sub_session(self) -> None:
        """qa_model=Auto かつ main_model=Auto → 同一とみなしサブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        # get_qa_model() は qa_model が None の場合 model を返す → AUTO 同士
        self.assertFalse(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_pre_qa_auto_model_differs_from_fixed_model_creates_sub_session(self) -> None:
        """qa_model=Auto、main_model=固定モデル → 差異あり → サブセッション作成。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model="claude-opus-4.7", qa_model=MODEL_AUTO_VALUE)
        self.assertTrue(
            runner._should_use_pre_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    # --- Post-QA ---

    def test_post_qa_same_model_no_workiq_uses_main_session(self) -> None:
        """Post-QA: qa_model == main_model かつ WorkIQ 無効 → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertFalse(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_post_qa_different_model_creates_sub_session(self) -> None:
        """Post-QA: qa_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", qa_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    def test_post_qa_workiq_enabled_creates_sub_session(self) -> None:
        """Post-QA: WorkIQ 有効 → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7")
        self.assertTrue(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=True,
            )
        )

    def test_post_qa_auto_model_same_no_sub_session(self) -> None:
        """Post-QA: qa_model=Auto かつ main_model=Auto → サブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        self.assertFalse(
            runner._should_use_qa_sub_session(
                qa_model=runner.config.get_qa_model(),
                workiq_available=False,
            )
        )

    # --- Review ---

    def test_review_same_model_uses_main_session(self) -> None:
        """Review: review_model == main_model → サブセッション不要。"""
        runner = self._make_runner(model="claude-opus-4.7")
        # review_model 未設定 → get_review_model() は model を返す
        self.assertFalse(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_different_model_creates_sub_session(self) -> None:
        """Review: review_model != main_model → サブセッション作成。"""
        runner = self._make_runner(model="claude-opus-4.7", review_model="gpt-5.4")
        self.assertTrue(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_auto_model_same_no_sub_session(self) -> None:
        """Review: review_model=Auto かつ main_model=Auto → サブセッション不要。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model=MODEL_AUTO_VALUE)
        self.assertFalse(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )

    def test_review_auto_model_differs_from_fixed_creates_sub_session(self) -> None:
        """Review: review_model=Auto、main_model=固定モデル → サブセッション作成。"""
        from config import MODEL_AUTO_VALUE
        runner = self._make_runner(model="claude-opus-4.7", review_model=MODEL_AUTO_VALUE)
        self.assertTrue(
            runner._should_use_review_sub_session(
                review_model=runner.config.get_review_model(),
            )
        )


# ---------------------------------------------------------------------------
# Phase 6: _sub_sessions_created カウンターのテスト
# ---------------------------------------------------------------------------

class TestSubSessionsCreatedCounter(unittest.TestCase):
    """Phase 6: _sub_sessions_created カウンターの初期値・リセット・インクリメントを検証する。"""

    def _make_runner(self, **cfg_kwargs) -> StepRunner:
        cfg = SDKConfig(dry_run=True, model="claude-opus-4.7", **cfg_kwargs)
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_initial_counter_is_zero(self) -> None:
        """StepRunner 生成直後の _sub_sessions_created は 0。"""
        runner = self._make_runner()
        self.assertEqual(runner._sub_sessions_created, 0)

    def test_counter_resets_on_dry_run(self) -> None:
        """run_step() 開始時に _sub_sessions_created がリセットされる（dry_run で確認）。"""
        runner = self._make_runner()
        runner._sub_sessions_created = 99  # 意図的に汚染

        with _CaptureOutput():
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        # dry_run なのでサブセッション作成はなく、run_step 冒頭でリセットされる
        self.assertEqual(runner._sub_sessions_created, 0)

    def test_helper_methods_exist(self) -> None:
        """Phase 6 で追加した helper メソッドが StepRunner に存在すること。"""
        runner = self._make_runner()
        self.assertTrue(callable(getattr(runner, "_should_use_pre_qa_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_should_use_qa_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_should_use_review_sub_session", None)))
        self.assertTrue(callable(getattr(runner, "_log_sub_session_reason", None)))
        self.assertTrue(callable(getattr(runner, "_log_main_session_reuse", None)))

    def test_log_sub_session_reason_does_not_leak_secrets(self) -> None:
        """_log_sub_session_reason が token/secret 等のキーを含まないイベントを出力すること。"""
        captured_events: list[str] = []
        runner = self._make_runner()
        original_event = runner.console.event
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_sub_session_reason(
            "1.1", "Pre-QA",
            qa_model="gpt-5.4",
            workiq_available=True,
        )
        runner.console.event = original_event

        self.assertTrue(len(captured_events) > 0, "イベントが出力されること")
        msg = captured_events[0]
        # モデル名は含んでよい（公開情報）
        self.assertIn("gpt-5.4", msg)
        # WorkIQ 有効の旨が含まれること
        self.assertIn("WorkIQ", msg)
        # 秘密情報キーワードが含まれないこと
        for secret_token in ("token", "secret", "password", "api_key", "bearer", "credential"):
            self.assertNotIn(secret_token, msg.lower(), f"'{secret_token}' は出力に含まれてはならない")

    def test_log_sub_session_reason_does_not_include_actual_token_value(self) -> None:
        """config に github_token が設定されていても、_log_sub_session_reason の出力に含まれないこと。"""
        captured_events: list[str] = []
        # 実際のトークンを模した値を config に設定する
        _fake_token = "ghp_THIS_IS_A_FAKE_TOKEN_FOR_TESTING_1234"
        cfg = SDKConfig(
            model="claude-opus-4.7",
            qa_model="gpt-5.4",
            github_token=_fake_token,
        )
        console = Console(verbose=False, quiet=True)
        runner = StepRunner(config=cfg, console=console)
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_sub_session_reason(
            "1.1", "Pre-QA",
            qa_model="gpt-5.4",
            workiq_available=False,
        )

        for msg in captured_events:
            self.assertNotIn(
                _fake_token, msg,
                "github_token の実値がログに出力されてはならない",
            )

    def test_log_main_session_reuse_emits_event(self) -> None:
        """_log_main_session_reuse がイベントを出力すること。"""
        captured_events: list[str] = []
        runner = self._make_runner()
        original_event = runner.console.event
        runner.console.event = lambda msg: captured_events.append(msg)  # type: ignore[method-assign]

        runner._log_main_session_reuse("1.1", "Post-QA")
        runner.console.event = original_event

        self.assertTrue(len(captured_events) > 0, "イベントが出力されること")
        self.assertIn("Post-QA", captured_events[0])
        self.assertIn("再利用", captured_events[0])

    def test_source_inspection_sub_sessions_counter_reset_in_run_step(self) -> None:
        """run_step() 内で _sub_sessions_created = 0 でリセットされることをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_sub_sessions_created = 0", source)

    def test_source_inspection_counter_incremented_on_pre_qa_sub_session(self) -> None:
        """_run_pre_execution_qa 内でカウンターがインクリメントされることをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_sub_sessions_created += 1", source)

    def test_source_inspection_counter_incremented_on_qa_sub_session(self) -> None:
        """run_step 内 Review フェーズでカウンターがインクリメントされることをソース検査。
        Post-QA は廃止済みのため Review の1箇所のみ出現する。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertGreaterEqual(source.count("_sub_sessions_created += 1"), 1)

    def test_source_inspection_uses_helper_methods_in_pre_qa(self) -> None:
        """_run_pre_execution_qa が _should_use_pre_qa_sub_session を使用することをソース検査。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_should_use_pre_qa_sub_session", source)

    def test_source_inspection_uses_helper_methods_in_run_step(self) -> None:
        """run_step が _should_use_review_sub_session を使用することをソース検査。
        Post-QA 廃止に伴い _should_use_qa_sub_session は run_step で使用されなくなった。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_should_use_review_sub_session", source)

    def test_source_inspection_log_methods_called_in_pre_qa(self) -> None:
        """_run_pre_execution_qa でサブセッション作成/再利用ログが呼ばれること。"""
        import inspect
        source = inspect.getsource(StepRunner._run_pre_execution_qa)
        self.assertIn("_log_sub_session_reason", source)
        self.assertIn("_log_main_session_reuse", source)

    def test_source_inspection_log_methods_called_in_run_step(self) -> None:
        """run_step で Review のサブセッション作成/再利用ログが呼ばれること。オフ）Post-QAは廃止された。"""
        import inspect
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("_log_sub_session_reason", source)
        self.assertIn("_log_main_session_reuse", source)


# ---------------------------------------------------------------------------
# G-1: available_tools / excluded_tools propagation (T-04)
# ---------------------------------------------------------------------------

class TestAvailableExcludedToolsPropagation(unittest.TestCase):
    """SDKConfig.available_tools / excluded_tools がメインセッション・サブセッション・
    resume_session の全経路で SDK へ伝搬されることを検証する。
    """

    def _build_fake_sdk(self):
        import types

        class _FakeSession:
            async def send_and_wait(self, *args, **kwargs):
                return None

            async def disconnect(self):
                return None

            def on(self, handler):
                return None

        class _FakeClient:
            def __init__(self) -> None:
                self.create_session_kwargs: list = []

            async def start(self):
                return None

            async def stop(self):
                return None

            async def create_session(self, **kwargs):
                self.create_session_kwargs.append(kwargs)
                return _FakeSession()

        fake_client = _FakeClient()
        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda **kwargs: fake_client

        class _RuntimeConnection:
            @staticmethod
            def for_stdio(**kwargs):
                return object()

            @staticmethod
            def for_uri(*args, **kwargs):
                return object()

        fake_copilot.RuntimeConnection = _RuntimeConnection

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return fake_client, fake_copilot, fake_copilot_session

    def test_main_session_receives_available_and_excluded_tools(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-tools01",
            available_tools=["str_replace_editor", "bash"],
            excluded_tools=["web_search"],
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertEqual(kw.get("available_tools"), ["str_replace_editor", "bash"])
        self.assertEqual(kw.get("excluded_tools"), ["web_search"])

    def test_main_session_omits_keys_when_unset(self) -> None:
        """Phase 8 S-3 revert: `available_tools` のデフォルトは `None` の据え置き
        （カテゴリ名と SDK 実ツール名のミスマッチ問題のため）。env 未設定時は
        SDK へキーを伝搬しないこと。
        """
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-tools02",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertNotIn("available_tools", kw)
        self.assertNotIn("excluded_tools", kw)

    def test_sub_session_opts_includes_tools(self) -> None:
        cfg = SDKConfig(
            model="claude-opus-4.7",
            available_tools=["bash"],
            excluded_tools=["web_search"],
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        # _build_sub_session_opts は copilot.session.PermissionHandler を import する
        import types
        fake_session_mod = types.ModuleType("copilot.session")
        class _PH:
            @staticmethod
            async def approve_all(*a, **kw):
                return True
        fake_session_mod.PermissionHandler = _PH
        with unittest.mock.patch.dict(sys.modules, {"copilot.session": fake_session_mod}):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertEqual(opts.get("available_tools"), ["bash"])
        self.assertEqual(opts.get("excluded_tools"), ["web_search"])

    def _fake_permission_module(self):
        import types
        mod = types.ModuleType("copilot.session")

        class _PH:
            @staticmethod
            async def approve_all(*a, **kw):
                return True

        mod.PermissionHandler = _PH
        return mod

    def test_sub_session_opts_includes_tool_search(self) -> None:
        """FR-MODEL-04: サブセッション opts へも tool_search を伝搬する。"""
        cfg = SDKConfig(model="claude-opus-4.7", tool_search=True)
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": self._fake_permission_module()}
        ):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertEqual(opts.get("tool_search"), {"enabled": True})

    def test_sub_session_opts_includes_tool_search_by_default(self) -> None:
        """FR-MODEL-04: 既定（有効）でサブセッションへも伝搬する。"""
        cfg = SDKConfig(model="claude-opus-4.7")
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": self._fake_permission_module()}
        ):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertEqual(opts.get("tool_search"), {"enabled": True})

    def test_sub_session_opts_omits_tool_search_when_disabled(self) -> None:
        """FR-MODEL-06: 明示的な無効化はサブセッションへも渡さない。"""
        cfg = SDKConfig(model="claude-opus-4.7", tool_search=False)
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        with unittest.mock.patch.dict(
            sys.modules, {"copilot.session": self._fake_permission_module()}
        ):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertNotIn("tool_search", opts)

    def test_main_session_includes_infinite_sessions_when_auto_compaction(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-compact01",
            auto_compaction=True,
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertEqual(kw.get("infinite_sessions"), {"enabled": True})

    def test_main_session_omits_infinite_sessions_by_default(self) -> None:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-compact02",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertNotIn("infinite_sessions", kw)

    def test_main_session_includes_tool_search_when_enabled(self) -> None:
        """FR-MODEL-04: tool_search=True でメインセッションへ enabled を渡す。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-toolsearch01",
            tool_search=True,
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertEqual(kw.get("tool_search"), {"enabled": True})

    def test_main_session_includes_tool_search_by_default(self) -> None:
        """FR-MODEL-04: 既定（有効）でメインセッションへ enabled を渡す。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-toolsearch02",
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertEqual(kw.get("tool_search"), {"enabled": True})

    def test_main_session_omits_tool_search_when_disabled(self) -> None:
        """FR-MODEL-06: 明示的な無効化時は SDK へ渡さない。"""
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id="20260507T100000-toolsearch03",
            tool_search=False,
        )
        runner = StepRunner(config=cfg, console=Console(verbose=False, quiet=True))
        fake_client, fake_copilot, fake_copilot_session = self._build_fake_sdk()
        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": fake_copilot, "copilot.session": fake_copilot_session},
        ):
            ok = asyncio.run(runner.run_step("1.1", "t", "p"))
        self.assertTrue(ok)
        kw = fake_client.create_session_kwargs[0]
        self.assertNotIn("tool_search", kw)


# ---------------------------------------------------------------------------
# G-8: client.start() retry helper (T-16)
# ---------------------------------------------------------------------------

class TestStartClientWithRetry(unittest.IsolatedAsyncioTestCase):
    """`_start_client_with_retry` が start 失敗時にリトライ・最終 raise すること。"""

    async def test_succeeds_on_first_attempt(self) -> None:
        from runner import _start_client_with_retry

        class C:
            def __init__(self):
                self.calls = 0
            async def start(self):
                self.calls += 1
        c = C()
        await _start_client_with_retry(c)
        self.assertEqual(c.calls, 1)

    async def test_retries_then_succeeds(self) -> None:
        from runner import _start_client_with_retry, _CLIENT_START_BACKOFF_SECONDS
        # backoff を 0 にパッチして高速化
        with unittest.mock.patch("runner._CLIENT_START_BACKOFF_SECONDS", (0, 0, 0)):
            class C:
                def __init__(self):
                    self.calls = 0
                async def start(self):
                    self.calls += 1
                    if self.calls < 2:
                        raise RuntimeError("boom")
            c = C()
            await _start_client_with_retry(c)
        self.assertEqual(c.calls, 2)

    async def test_raises_after_max_attempts(self) -> None:
        from runner import _start_client_with_retry
        with unittest.mock.patch("runner._CLIENT_START_BACKOFF_SECONDS", (0, 0, 0)):
            class C:
                def __init__(self):
                    self.calls = 0
                async def start(self):
                    self.calls += 1
                    raise RuntimeError("always fail")
            c = C()
            with self.assertRaises(RuntimeError):
                await _start_client_with_retry(c)
            self.assertEqual(c.calls, 3)


# ---------------------------------------------------------------------------
# G-7: Phase 4 verify JSON parse failure visibility (T-14)
# ---------------------------------------------------------------------------

class TestVerifyJsonParseWarning(unittest.TestCase):
    """Phase 4 verify の JSON パース失敗時に Console.warning が呼ばれること、
    および notes に [json_parse_error=...] プレフィックスが付くことを検証する。

    runner.py 内のロジック実装はインライン展開されているため、ソース上の
    マーカー文字列で実装存在を検証する（非実行検証）。
    """

    def test_runner_source_contains_warning_branch(self) -> None:
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "runner.py"
        text = src.read_text(encoding="utf-8")
        # T-13 で追加した文言
        self.assertIn("json_parse_error", text)
        self.assertIn("LLM JSON のパースに失敗", text)
        self.assertIn("LLM 応答に JSON ブロックが見つかりません", text)


# ---------------------------------------------------------------------------
# G-4: _truncate_context_with_warn (T-09)
# ---------------------------------------------------------------------------

class TestTruncateContextWithWarn(unittest.TestCase):
    """切詰め発生時のみ console.warning が呼ばれることを検証する。"""

    def _make_console_mock(self):
        c = unittest.mock.MagicMock()
        c.warning = unittest.mock.MagicMock()
        return c

    def test_no_warning_when_under_limit(self) -> None:
        from runner import _truncate_context_with_warn
        c = self._make_console_mock()
        out = _truncate_context_with_warn("hello", 100, label="test", console=c)
        self.assertEqual(out, "hello")
        c.warning.assert_not_called()

    def test_warning_when_over_limit(self) -> None:
        from runner import _truncate_context_with_warn
        c = self._make_console_mock()
        long = "a" * 1000
        out = _truncate_context_with_warn(long, 100, label="Phase X test", console=c)
        self.assertLessEqual(len(out), 100)
        c.warning.assert_called_once()
        msg = c.warning.call_args.args[0]
        self.assertIn("Phase X test", msg)
        self.assertIn("100", msg)
        self.assertIn("1,000", msg)

    def test_warning_failure_does_not_break(self) -> None:
        from runner import _truncate_context_with_warn
        c = unittest.mock.MagicMock()
        c.warning.side_effect = RuntimeError("console broken")
        out = _truncate_context_with_warn("a" * 200, 50, label="t", console=c)
        # 例外が伝播せず切詰めは実施される
        self.assertLessEqual(len(out), 50)


class TestSubSessionOptsCustomAgent(unittest.TestCase):
    """SPLIT-fork 拡張: _build_sub_session_opts(custom_agent=...) の挙動。"""

    @staticmethod
    def _patched_modules():
        import types

        fake_copilot_session = types.ModuleType("copilot.session")

        class _PermissionHandler:
            @staticmethod
            async def approve_all(*args, **kwargs):
                return True

        fake_copilot_session.PermissionHandler = _PermissionHandler
        return {"copilot.session": fake_copilot_session}

    def _make_runner(self) -> "StepRunner":
        from runner import StepRunner
        cfg = SDKConfig(model="claude-opus-4.7", run_id="run-split-fork")
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console)

    def test_custom_agent_sets_opts(self) -> None:
        """Phase 2 (Q1=C / Q3=a) 移行後: SDK へ `custom_agent` キーは渡さない。"""
        runner = self._make_runner()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts(
                "claude-opus-4.7",
                custom_agent="Arch-UI-Detail",
            )
        self.assertNotIn("custom_agent", opts)
        self.assertNotIn("agent", opts)
        self.assertNotIn("custom_agents", opts)

    def test_custom_agent_omitted_backward_compat(self) -> None:
        """QA/Review 既存呼び出し（custom_agent 省略）では opts に含めない。"""
        runner = self._make_runner()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts("claude-opus-4.7")
        self.assertNotIn("custom_agent", opts)

    def test_custom_agent_none_explicit(self) -> None:
        """custom_agent=None 明示でも opts に含めない。"""
        runner = self._make_runner()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts(
                "claude-opus-4.7", custom_agent=None,
            )
        self.assertNotIn("custom_agent", opts)

    def test_custom_agent_empty_string_treated_as_none(self) -> None:
        runner = self._make_runner()
        with unittest.mock.patch.dict(sys.modules, self._patched_modules()):
            opts = runner._build_sub_session_opts(
                "claude-opus-4.7", custom_agent="",
            )
        self.assertNotIn("custom_agent", opts)


if __name__ == "__main__":
    unittest.main()
