"""Branch creation policy tests for ``enable_auto_merge``.

``enable_auto_merge`` alone may create branches only for ASDW-WEB (step-scoped)
and ADFDV (workflow-wide). Explicit Issue/PR creation keeps the existing
workflow-wide branch behavior for every workflow.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import nullcontext
from dataclasses import dataclass
from unittest.mock import Mock, patch

from hve import orchestrator
from hve.config import SDKConfig
from hve.orchestrator_context import OrchestratorContext
from hve.workflow_registry import list_workflows


_PR_SKIPPED_MESSAGE = (
    "失敗 Step があるため PR 作成をスキップしました。"
    "auto-approve-ready ラベルは付与されません。"
)

_UNSET = object()


@dataclass(frozen=True)
class _StartupIssueStub:
    category: str
    field_name: str
    message: str
    remediation_hint: str


@dataclass(frozen=True)
class _StartupResultStub:
    issues: tuple[_StartupIssueStub, ...] = ()

    def is_ok(self) -> bool:
        return not self.issues


class _FakeRunner:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def set_fork_index(self, *args, **kwargs) -> None:
        pass

    async def run_step(self, *args, **kwargs) -> bool:
        return True


class _NoopDAGExecutor:
    def __init__(self, *args, failed: bool = False, **kwargs) -> None:
        self.completed: set[str] = set() if failed else {"1"}
        self.failed: set[str] = {"1"} if failed else set()
        self.skipped: set[str] = set()
        self.blocked: set[str] = set()

    def compute_waves(self):
        return []

    async def execute(self):
        return {}


class _ArchFilterResult:
    matched_app_ids = ["APP-01"]
    catalog_found = True

    def to_dict(self):
        return {"matched_app_ids": self.matched_app_ids}

    def to_markdown_section(self):
        return ""


def _run_workflow_with_fakes(
    workflow_id: str,
    *,
    failed: bool = False,
    dry_run: bool = False,
    create_pr: bool = False,
    dirty_hve_paths: list[str] | None = None,
    params: dict | None = None,
    startup_issues: tuple[_StartupIssueStub, ...] = (),
    orchestrator_ctx: OrchestratorContext | None = _UNSET,
):
    """``run_workflow`` を副作用なしで実行するための共通フェイク環境。

    ``dirty_hve_paths`` は FR-CLI-74 の dirty HVE source 検出結果を差し替える。
    既定は「clean」であり、本リポジトリの作業ツリーには一切触れない。

    ``orchestrator_ctx`` の既定は HVE CLI / GUI Orchestrator 配下を表す
    ``OrchestratorContext()``。``None`` を明示すると単独実行モードになる。
    """
    if orchestrator_ctx is _UNSET:
        orchestrator_ctx = OrchestratorContext(run_id="branch-mode-test")
    events: list[str] = []
    config = SDKConfig(
        enable_auto_merge=True,
        create_pr=create_pr,
        dry_run=dry_run,
        quiet=True,
        no_workbench=True,
        mdq_watch=False,
        github_token="test-token",
        repo="owner/repo",
    )
    console = Mock()

    def _checkout(*_args, **_kwargs):
        events.append("checkout")
        return True

    checkout = Mock(side_effect=_checkout)
    add_commit_push = Mock(return_value=False)
    push_branch = Mock(return_value=True)
    create_pr_mock = Mock(return_value=None)
    dirty_probe = Mock(return_value=list(dirty_hve_paths or []))
    subprocess_guard = Mock(
        side_effect=AssertionError(
            "run_workflow test helper must not invoke a real subprocess/network"
        )
    )

    resolve_selected_steps_impl = orchestrator.resolve_selected_steps

    def _resolve_selected_steps(*args, **kwargs):
        events.append("active_steps")
        return resolve_selected_steps_impl(*args, **kwargs)

    step_resolver = Mock(side_effect=_resolve_selected_steps)

    build_dag_plan_impl = orchestrator.build_dag_plan

    def _build_dag_plan(*args, **kwargs):
        events.append("dry_run_plan")
        return build_dag_plan_impl(*args, **kwargs)

    plan_builder = Mock(side_effect=_build_dag_plan)

    def _make_runner(*args, **kwargs):
        events.append("agent_runner")
        return _FakeRunner(*args, **kwargs)

    runner_factory = Mock(side_effect=_make_runner)

    def _validate_startup(*_args, **_kwargs):
        events.append("startup_validate")
        return _StartupResultStub(tuple(startup_issues))

    startup_validate = Mock(side_effect=_validate_startup)
    try:
        from hve import startup_preflight as startup_preflight_module
    except ImportError:
        startup_preflight_module = None
    startup_module_patch = (
        patch.object(
            startup_preflight_module,
            "validate_startup_configuration",
            startup_validate,
        )
        if startup_preflight_module is not None
        else nullcontext()
    )

    precheck_ok: dict[str, object] = {
        "should_abort": False,
        "error": None,
        "blocked": False,
        "blocked_step_ids": [],
    }

    def _expand_passthrough(workflow, active_steps, *_args, **_kwargs):
        return workflow, active_steps, None

    with (
        patch.object(orchestrator, "Console", return_value=console),
        patch.object(orchestrator, "StepRunner", runner_factory),
        patch.object(orchestrator, "resolve_selected_steps", step_resolver),
        patch.object(orchestrator, "build_dag_plan", plan_builder),
        patch.object(orchestrator.subprocess, "run", subprocess_guard),
        patch.object(
            orchestrator,
            "validate_startup_configuration",
            startup_validate,
            create=True,
        ),
        startup_module_patch,
        patch.object(
            orchestrator,
            "DAGExecutor",
            side_effect=lambda *args, **kwargs: _NoopDAGExecutor(
                *args, failed=failed, **kwargs
            ),
        ),
        patch.object(
            orchestrator,
            "_expand_workflow_for_dag",
            side_effect=_expand_passthrough,
        ),
        patch.object(orchestrator, "_detect_existing_artifacts", return_value={}),
        patch.object(
            orchestrator,
            "_check_workflow_input_artifacts",
            return_value=precheck_ok,
        ),
        patch.object(
            orchestrator,
            "_check_required_skills_for_active_steps",
            return_value=precheck_ok,
        ),
        patch.object(orchestrator, "_build_step_prompt", return_value="prompt"),
        patch.object(
            orchestrator,
            "resolve_app_arch_scope",
            return_value=_ArchFilterResult(),
        ),
        patch.object(orchestrator, "_git_checkout_new_branch", checkout),
        patch.object(orchestrator, "_git_add_commit_push", add_commit_push),
        patch.object(orchestrator, "_git_push_branch", push_branch),
        patch.object(orchestrator, "_create_pr_if_needed", create_pr_mock),
        patch.object(
            orchestrator,
            "_git_dirty_hve_source_paths",
            dirty_probe,
            create=True,
        ),
        patch("hve.workflow_registry.get_meta_dependencies", return_value=[]),
    ):
        result = asyncio.run(
            orchestrator.run_workflow(
                workflow_id=workflow_id,
                params=params or {"branch": "main", "selected_steps": ["1"]},
                config=config,
                orchestrator_ctx=orchestrator_ctx,
            )
        )

    return {
        "result": result,
        "console": console,
        "checkout": checkout,
        "add_commit_push": add_commit_push,
        "push_branch": push_branch,
        "create_pr": create_pr_mock,
        "dirty_probe": dirty_probe,
        "startup_validate": startup_validate,
        "step_resolver": step_resolver,
        "plan_builder": plan_builder,
        "runner_factory": runner_factory,
        "events": events,
    }


class TestWorkflowBranchMode(unittest.TestCase):
    def test_auto_merge_workflow_wide_branch_is_adfdv_only(self) -> None:
        """ASDW-WEB is false here because its auto-merge branches are step-scoped."""
        config = SDKConfig(enable_auto_merge=True)
        for workflow in list_workflows():
            with self.subTest(workflow=workflow.id):
                self.assertEqual(
                    orchestrator._uses_workflow_branch_mode(workflow.id, config),
                    workflow.id == "adfdv",
                )

    def test_explicit_issue_or_pr_creation_keeps_workflow_branch(self) -> None:
        for workflow in list_workflows():
            for explicit_config in (
                SDKConfig(create_issues=True, enable_auto_merge=True),
                SDKConfig(create_pr=True, enable_auto_merge=True),
            ):
                with self.subTest(
                    workflow=workflow.id,
                    create_issues=explicit_config.create_issues,
                    create_pr=explicit_config.create_pr,
                ):
                    self.assertTrue(
                        orchestrator._uses_workflow_branch_mode(
                            workflow.id, explicit_config
                        )
                    )

    def test_no_branch_flags_disable_workflow_branch_for_all_workflows(self) -> None:
        config = SDKConfig()
        for workflow in list_workflows():
            with self.subTest(workflow=workflow.id):
                self.assertFalse(
                    orchestrator._uses_workflow_branch_mode(workflow.id, config)
                )

    def _run_workflow_with_fakes(self, workflow_id: str, **kwargs):
        return _run_workflow_with_fakes(workflow_id, **kwargs)

    def test_auto_merge_does_not_run_branch_lifecycle_for_ard_or_aas(self) -> None:
        for workflow_id in ("ard", "aas"):
            with self.subTest(workflow=workflow_id):
                observed = self._run_workflow_with_fakes(workflow_id)
                observed["checkout"].assert_not_called()
                observed["add_commit_push"].assert_not_called()
                observed["push_branch"].assert_not_called()
                observed["create_pr"].assert_not_called()
                self.assertIsNone(observed["result"]["working_branch"])

    def test_auto_merge_keeps_adfdv_workflow_branch(self) -> None:
        observed = self._run_workflow_with_fakes("adfdv")
        observed["checkout"].assert_called_once()
        observed["add_commit_push"].assert_called_once()
        observed["create_pr"].assert_not_called()
        self.assertRegex(
            observed["result"]["working_branch"],
            r"^copilot-sdk/adfdv-[0-9a-f]{8}$",
        )

    def test_explicit_create_pr_keeps_ard_workflow_branch(self) -> None:
        observed = self._run_workflow_with_fakes("ard", create_pr=True)
        observed["checkout"].assert_called_once()
        observed["add_commit_push"].assert_called_once()
        observed["create_pr"].assert_not_called()
        self.assertRegex(
            observed["result"]["working_branch"],
            r"^copilot-sdk/ard-[0-9a-f]{8}$",
        )

    def test_auto_merge_dry_run_does_not_checkout(self) -> None:
        observed = self._run_workflow_with_fakes("adfdv", dry_run=True)
        observed["checkout"].assert_not_called()
        self.assertTrue(observed["result"]["dry_run"])

    def test_non_workflow_branch_failure_does_not_claim_pr_was_skipped(self) -> None:
        observed = self._run_workflow_with_fakes("ard", failed=True)
        messages = [
            str(call.args[0])
            for call in observed["console"].event.call_args_list
            if call.args
        ]
        self.assertNotIn(_PR_SKIPPED_MESSAGE, messages)

    def test_workflow_branch_failure_claims_pr_was_skipped(self) -> None:
        observed = self._run_workflow_with_fakes("adfdv", failed=True)
        messages = [
            str(call.args[0])
            for call in observed["console"].event.call_args_list
            if call.args
        ]
        self.assertIn(_PR_SKIPPED_MESSAGE, messages)


class TestStartupConfigurationPreflight(unittest.TestCase):
    """FR-CLI-82: active step 解決直後の共通 startup preflight。"""

    def test_run_workflow_passes_targeting_inputs_for_asdw_adfdv_and_ard(self) -> None:
        from hve.startup_preflight import github_write_required

        asdw = next(wf for wf in list_workflows() if wf.id == "asdw-web")
        remote_step_id = next(
            step.id
            for step in asdw.steps
            if not step.is_container and step.requires_remote_cicd
        )
        adfdv = next(wf for wf in list_workflows() if wf.id == "adfdv")
        adfdv_step_id = next(step.id for step in adfdv.steps if not step.is_container)
        cases = (
            ("asdw-web", remote_step_id, True),
            ("adfdv", adfdv_step_id, True),
            ("ard", "1", False),
        )

        for workflow_id, selected_step, expected_target in cases:
            with self.subTest(workflow=workflow_id, step=selected_step):
                observed = _run_workflow_with_fakes(
                    workflow_id,
                    dry_run=True,
                    params={"branch": "main", "selected_steps": [selected_step]},
                )

                observed["startup_validate"].assert_called_once()
                kwargs = observed["startup_validate"].call_args.kwargs
                self.assertEqual(kwargs["workflow"].id, workflow_id)
                self.assertIn(selected_step, kwargs["active_steps"])
                self.assertIs(kwargs["check_remote"], True)
                self.assertEqual(
                    github_write_required(
                        workflow=kwargs["workflow"],
                        active_steps=kwargs["active_steps"],
                        create_issues=kwargs["create_issues"],
                        create_pr=kwargs["create_pr"],
                        enable_auto_merge=kwargs["enable_auto_merge"],
                    ),
                    expected_target,
                )
                self.assertTrue(observed["result"].get("dry_run"))
                self.assertFalse(observed["result"].get("blocked"))

    def test_failure_blocks_before_plan_checkout_and_agent_runner(self) -> None:
        issue = _StartupIssueStub(
            category="setting",
            field_name="base_branch",
            message="remote branch does not exist",
            remediation_hint="push the configured base branch",
        )

        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                observed = _run_workflow_with_fakes(
                    "adfdv",
                    dry_run=dry_run,
                    startup_issues=(issue,),
                )

                observed["startup_validate"].assert_called_once()
                kwargs = observed["startup_validate"].call_args.kwargs
                self.assertEqual(kwargs["workflow"].id, "adfdv")
                self.assertTrue(kwargs["active_steps"])
                self.assertIs(kwargs["check_remote"], True)
                self.assertEqual(
                    observed["events"][:2],
                    ["active_steps", "startup_validate"],
                )
                self.assertNotIn("dry_run_plan", observed["events"])
                self.assertNotIn("checkout", observed["events"])
                self.assertNotIn("agent_runner", observed["events"])
                observed["plan_builder"].assert_not_called()
                observed["checkout"].assert_not_called()
                observed["runner_factory"].assert_not_called()

                result = observed["result"]
                self.assertTrue(result.get("blocked"))
                self.assertEqual(result.get("completed"), [])
                self.assertEqual(result.get("failed"), [])
                self.assertIn("base_branch", str(result.get("error") or ""))


_DIRTY_HVE_PATHS = [
    "hve/orchestrator.py",
    "mdq/cli.py",
    "hve-dev/requirement-definition.md",
    ".github/prompts/AppDesigner.prompt.md",
    ".github/skills/markdown-query/SKILL.md",
    ".github/scripts/validate-io-contracts.py",
    ".github/io-contracts/AppDesigner.yaml",
]


class TestDirtyHveSourcePreflight(unittest.TestCase):
    """FR-CLI-74: アプリ生成 run 開始時の dirty HVE source pre-flight。

    HVE ソース（``hve/`` / ``mdq/`` / ``hve-dev/`` / ``.github/prompts/`` /
    ``.github/skills/`` / ``.github/scripts/`` / ``.github/io-contracts/``）に
    未コミット変更がある場合、branch 作成および Agent セッション開始より前に
    検出した全パスを一括報告して停止する。override フラグは持たない。
    """

    def test_dirty_hve_sources_abort_before_branch_creation(self) -> None:
        """FR-CLI-74: dirty 検出時は branch 作成・Agent セッション開始より前に停止する。"""
        observed = _run_workflow_with_fakes(
            "adfdv", dirty_hve_paths=list(_DIRTY_HVE_PATHS)
        )

        observed["checkout"].assert_not_called()
        observed["add_commit_push"].assert_not_called()
        observed["push_branch"].assert_not_called()
        observed["create_pr"].assert_not_called()

        result = observed["result"]
        self.assertTrue(result.get("blocked"))
        self.assertEqual(result.get("completed"), [])
        self.assertEqual(result.get("failed"), [])
        self.assertTrue(result.get("error"))

    def test_dirty_hve_sources_are_reported_in_a_single_batch(self) -> None:
        """FR-CLI-74: 検出した全パスを 1 回のエラー報告にまとめる。"""
        observed = _run_workflow_with_fakes(
            "adfdv", dirty_hve_paths=list(_DIRTY_HVE_PATHS)
        )

        error = str(observed["result"].get("error") or "")
        for path in _DIRTY_HVE_PATHS:
            self.assertIn(path, error)

        batched = [
            str(call.args[0])
            for call in observed["console"].error.call_args_list
            if call.args and all(p in str(call.args[0]) for p in _DIRTY_HVE_PATHS)
        ]
        self.assertEqual(len(batched), 1, "全パスは 1 回で一括報告すること")

    def test_clean_hve_sources_do_not_block_the_run(self) -> None:
        """FR-CLI-74: HVE ソースが clean なら従来どおり branch 作成へ進む。"""
        observed = _run_workflow_with_fakes("adfdv", dirty_hve_paths=[])

        observed["dirty_probe"].assert_called()
        observed["checkout"].assert_called_once()
        self.assertIsNone(observed["result"].get("error"))
        self.assertFalse(observed["result"].get("blocked"))

    def test_dry_run_does_not_block_on_dirty_hve_sources(self) -> None:
        """FR-CLI-74: --dry-run は Agent を起動しないため停止対象外。"""
        observed = _run_workflow_with_fakes(
            "adfdv", dry_run=True, dirty_hve_paths=list(_DIRTY_HVE_PATHS)
        )

        self.assertTrue(observed["result"].get("dry_run"))
        self.assertIsNone(observed["result"].get("error"))
        observed["checkout"].assert_not_called()

    def test_guard_also_applies_without_workflow_branch_mode(self) -> None:
        """FR-CLI-74: branch を作らない run でも Agent セッション開始前に停止する。"""
        observed = _run_workflow_with_fakes(
            "ard", dirty_hve_paths=["hve/runner.py"]
        )

        self.assertTrue(observed["result"].get("blocked"))
        self.assertIn("hve/runner.py", str(observed["result"].get("error") or ""))


class TestDirtyHveSourceDetection(unittest.TestCase):
    """FR-CLI-74: HVE ソースの未コミット変更検出ロジック。"""

    _PORCELAIN = "\n".join(
        [
            " M hve/orchestrator.py",
            "?? mdq/new_module.py",
            "A  .github/prompts/AppDesigner.prompt.md",
            "R  docs/old.md -> .github/skills/markdown-query/SKILL.md",
            " M docs/catalog/app-catalog.md",
            " M src/app/main.ts",
            " M README.md",
            ' M "hve/tests/日本語 file.py"',
        ]
    )

    def _run_probe(self, stdout: str, **kwargs):
        completed = Mock()
        completed.returncode = 0
        completed.stdout = stdout
        completed.stderr = ""
        run_mock = Mock(return_value=completed)
        with patch.object(orchestrator.subprocess, "run", run_mock):
            paths = orchestrator._git_dirty_hve_source_paths(**kwargs)
        return paths, run_mock

    def test_only_hve_source_prefixes_are_reported(self) -> None:
        """FR-CLI-74: HVE ソース prefix 配下だけを検出し、生成物は無視する。"""
        paths, _ = self._run_probe(self._PORCELAIN)

        self.assertIn("hve/orchestrator.py", paths)
        self.assertIn("mdq/new_module.py", paths)
        self.assertIn(".github/prompts/AppDesigner.prompt.md", paths)
        self.assertIn(".github/skills/markdown-query/SKILL.md", paths)
        self.assertIn("hve/tests/日本語 file.py", paths)
        for generated in (
            "docs/catalog/app-catalog.md",
            "src/app/main.ts",
            "README.md",
            "docs/old.md",
        ):
            self.assertNotIn(generated, paths)

    def test_git_is_invoked_with_list_arguments(self) -> None:
        """NFR-SEC-03: git はリスト引数で起動し shell を経由しない。"""
        _, run_mock = self._run_probe(self._PORCELAIN)

        args, kwargs = run_mock.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][0], "git")
        self.assertIn("status", args[0])
        self.assertIn("--porcelain", args[0])
        self.assertNotIn("shell", kwargs)

    def test_explicit_target_output_paths_are_excluded(self) -> None:
        """FR-CLI-74: 利用者が明示指定した target 出力パスは対象外。"""
        paths, _ = self._run_probe(
            self._PORCELAIN, target_output_paths=["hve-dev", "mdq/new_module.py"]
        )

        self.assertNotIn("mdq/new_module.py", paths)
        self.assertIn("hve/orchestrator.py", paths)

    def test_gui_local_settings_files_are_not_reported(self) -> None:
        """FR-CLI-74: GUI の利用者ローカル設定は HVE ソースとして扱わない。"""
        paths, _ = self._run_probe(
            "\n".join(
                [
                    " M hve/.settings.txt",
                    "?? hve/.settings.txt.tmp",
                    " M hve/orchestrator.py",
                ]
            )
        )

        self.assertNotIn("hve/.settings.txt", paths)
        self.assertNotIn("hve/.settings.txt.tmp", paths)
        self.assertIn("hve/orchestrator.py", paths)

    def test_gui_local_settings_file_alone_does_not_block_the_run(self) -> None:
        """FR-CLI-74: 当該ファイルだけが未コミットなら停止対象は 0 件。"""
        paths, _ = self._run_probe(" M hve/.settings.txt")

        self.assertEqual(paths, [])

    def test_gui_local_settings_exclusion_is_scoped_to_the_dirty_preflight(self) -> None:
        """FR-CLI-74: 除外は run 開始前検査に限定し FR-CLI-75 へ波及させない。"""
        self.assertEqual(
            orchestrator._filter_hve_source_paths(
                ["hve/.settings.txt", "hve/.settings.txt.tmp"]
            ),
            ["hve/.settings.txt", "hve/.settings.txt.tmp"],
        )

    def test_git_failure_is_not_silently_swallowed_into_success(self) -> None:
        """git が失敗した場合は検出結果を捏造せず空扱いにする（fail-open は記録する）。"""
        completed = Mock()
        completed.returncode = 128
        completed.stdout = ""
        completed.stderr = "fatal: not a git repository"
        with patch.object(orchestrator.subprocess, "run", Mock(return_value=completed)):
            self.assertEqual(orchestrator._git_dirty_hve_source_paths(), [])


class _GitResult:
    """``subprocess.run`` の戻り値スタブ（実 git を起動しない）。"""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _is_unstage_command(argv: list[str]) -> bool:
    """index からの unstage 専用コマンドかを返す（作業ツリーは変更しない）。"""
    if argv[:2] == ["git", "reset"]:
        return "--hard" not in argv and "--merge" not in argv
    if argv[:2] == ["git", "restore"]:
        return "--staged" in argv and "--worktree" not in argv
    return False


class TestStagedHveSourceGuard(unittest.TestCase):
    """G-02 / FR-CLI-75: git staging 時の HVE source 混入拒否。

    ``_git_add_commit_push`` は ``git add`` の後・``git commit`` の前に staged
    パスを検査する。HVE ソース（``hve/`` / ``mdq/`` / ``hve-dev/`` /
    ``.github/prompts/`` / ``.github/skills/`` / ``.github/scripts/`` /
    ``.github/io-contracts/``）が staged に含まれる場合、index を unstage して
    commit / push を行わずに停止し、原因パスを利用者へ提示する。
    生成対象アプリの成果物（``src/**`` / ``docs/**``）のみの staging は従来どおり
    commit / push まで進む。override フラグは持たない。
    """

    def _run_commit_push(
        self,
        *,
        status_stdout: str,
        staged_stdout: str,
        **kwargs,
    ) -> dict:
        """``_git_add_commit_push`` を実 git なしで実行する。

        本テストは一切 index を触らない（``subprocess.run`` 自体を差し替える）ため、
        実リポジトリの staging area は汚れない。
        """
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):
            argv = [str(a) for a in args]
            calls.append(argv)
            self.assertEqual(argv[0], "git", f"git 以外のプロセスを起動した: {argv}")
            if "status" in argv and "--porcelain" in argv:
                return _GitResult(0, stdout=status_stdout)
            if "diff" in argv and "--cached" in argv and "--name-only" in argv:
                return _GitResult(0, stdout=staged_stdout)
            if "diff" in argv and "--cached" in argv and "--quiet" in argv:
                # --quiet は staged 差分ありで exit 1
                return _GitResult(1)
            return _GitResult(0)

        console = Mock()
        with patch.object(orchestrator.subprocess, "run", fake_run):
            result = orchestrator._git_add_commit_push(
                branch="copilot-sdk/staged-guard-test",
                commit_message="[TEST] staged HVE source guard",
                console=console,
                **kwargs,
            )
        return {"result": result, "calls": calls, "console": console}

    def _error_messages(self, console: Mock) -> list[str]:
        return [str(call.args[0]) for call in console.error.call_args_list if call.args]

    def test_staged_hve_source_blocks_commit_and_push(self) -> None:
        """G-02: staged に HVE ソースが混入したら commit / push を実行しない。"""
        observed = self._run_commit_push(
            status_stdout=" M src/app/index.tsx\n M hve/orchestrator.py\n",
            staged_stdout="src/app/index.tsx\nhve/orchestrator.py\n",
        )

        self.assertFalse(observed["result"])
        self.assertFalse(
            any(argv[:2] == ["git", "commit"] for argv in observed["calls"]),
            "HVE ソース混入時に commit を実行した",
        )
        self.assertFalse(
            any(argv[:2] == ["git", "push"] for argv in observed["calls"]),
            "HVE ソース混入時に push を実行した",
        )
        errors = self._error_messages(observed["console"])
        self.assertTrue(
            any("hve/orchestrator.py" in message for message in errors),
            f"原因パスが報告されていない: {errors}",
        )

    def test_staged_hve_source_resets_the_index_without_touching_worktree(self) -> None:
        """G-02: 混入検出時は index を unstage する（作業ツリーは破棄しない）。"""
        observed = self._run_commit_push(
            status_stdout=" M src/app/index.tsx\n M .github/prompts/AppDesigner.prompt.md\n",
            staged_stdout="src/app/index.tsx\n.github/prompts/AppDesigner.prompt.md\n",
        )

        self.assertFalse(observed["result"])
        unstage_calls = [
            argv for argv in observed["calls"] if _is_unstage_command(argv)
        ]
        self.assertEqual(
            len(unstage_calls), 1, f"index の unstage が 1 回でない: {observed['calls']}"
        )
        for argv in observed["calls"]:
            for destructive in ("checkout", "clean", "stash", "--hard"):
                self.assertNotIn(
                    destructive,
                    argv,
                    f"作業ツリーを破棄しうる git 操作を実行した: {argv}",
                )

    def test_target_only_staging_commits_and_pushes_as_before(self) -> None:
        """G-02: 生成対象アプリの成果物のみの staging は従来どおり commit / push する。"""
        observed = self._run_commit_push(
            status_stdout=" M src/app/index.tsx\n M docs/services/svc.md\n",
            staged_stdout="src/app/index.tsx\ndocs/services/svc.md\n",
        )

        self.assertTrue(observed["result"])
        self.assertTrue(
            any(argv[:2] == ["git", "commit"] for argv in observed["calls"]),
            "target-only staging で commit されなかった",
        )
        self.assertTrue(
            any(argv[:2] == ["git", "push"] for argv in observed["calls"]),
            "target-only staging で push されなかった",
        )
        self.assertFalse(
            any(_is_unstage_command(argv) for argv in observed["calls"]),
            "target-only staging で index を reset した",
        )
        self.assertEqual(self._error_messages(observed["console"]), [])

    def test_explicit_target_output_paths_are_not_treated_as_hve_source(self) -> None:
        """G-02: 利用者が明示指定した target 出力パスは混入判定の対象外（FR-CLI-74 と同一規則）。"""
        observed = self._run_commit_push(
            status_stdout=" M hve-dev/requirement-definition.md\n",
            staged_stdout="hve-dev/requirement-definition.md\n",
            target_output_paths=["hve-dev"],
        )

        self.assertTrue(observed["result"])
        self.assertTrue(any(argv[:2] == ["git", "commit"] for argv in observed["calls"]))
        self.assertFalse(any(_is_unstage_command(argv) for argv in observed["calls"]))

    def test_hve_source_excluded_from_staging_does_not_block_commit(self) -> None:
        """G-02: 作業ツリーに HVE ソースがあっても staged に含まれなければ commit する。

        ``ignore_paths`` の pathspec 除外により HVE ソースが stage されなかった場合、
        判定は staged パスに基づくため commit / push は従来どおり進む。
        """
        observed = self._run_commit_push(
            status_stdout=" M hve/orchestrator.py\n M src/app/index.tsx\n",
            staged_stdout="src/app/index.tsx\n",
            ignore_paths=["hve"],
        )

        self.assertTrue(observed["result"])
        self.assertTrue(
            any(
                "diff" in argv and "--cached" in argv and "--name-only" in argv
                for argv in observed["calls"]
            ),
            "staged パスを検査していない",
        )
        self.assertTrue(any(argv[:2] == ["git", "commit"] for argv in observed["calls"]))
        self.assertFalse(any(_is_unstage_command(argv) for argv in observed["calls"]))

    def test_ignore_paths_pathspec_exclusion_is_preserved(self) -> None:
        """NFR-SEC-03: 既存の ``git add`` pathspec 除外（``:!path``）を壊さない。"""
        observed = self._run_commit_push(
            status_stdout=" M src/app/index.tsx\n",
            staged_stdout="src/app/index.tsx\n",
            ignore_paths=["work", "qa"],
        )

        add_calls = [argv for argv in observed["calls"] if argv[:2] == ["git", "add"]]
        self.assertEqual(len(add_calls), 1)
        self.assertEqual(add_calls[0][:3], ["git", "add", "."])
        self.assertIn(":!work", add_calls[0])
        self.assertIn(":!qa", add_calls[0])
        self.assertTrue(observed["result"])


if __name__ == "__main__":
    unittest.main()
