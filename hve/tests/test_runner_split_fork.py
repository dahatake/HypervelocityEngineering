"""hve/runner.py の Phase 1.5 (SPLIT-fork) 統合テスト。

SDK は実呼出しせず unittest.mock で fake セッションを構築する。
"""
from __future__ import annotations

import asyncio
import os
import unittest
import unittest.mock
from pathlib import Path
from typing import Any, List

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SDKConfig  # type: ignore[import-not-found]
from console import Console  # type: ignore[import-not-found]
from runner import StepRunner  # type: ignore[import-not-found]
from orchestrator_context import OrchestratorContext as _OrchestratorContext  # type: ignore[import-not-found]


def OrchestratorContext(*args: Any, **kwargs: Any) -> _OrchestratorContext:
    """Legacy split-fork tests explicitly opt in to the disabled-by-default path."""
    kwargs.setdefault("split_fork_enabled", True)
    return _OrchestratorContext(*args, **kwargs)


_SUBISSUES_2 = """\
<!-- parent_issue: TBD -->

<!-- subissue -->
<!-- title: First Sub -->
<!-- custom_agent: Arch-UI-Detail -->
## Sub-001
- AC: 何か作る

<!-- subissue -->
<!-- title: Second Sub -->
<!-- custom_agent: Arch-UI-Detail -->
<!-- depends_on: 1 -->
## Sub-002
- AC: もう一つ作る
"""


_SUBISSUES_1 = """\
<!-- parent_issue: TBD -->

<!-- subissue -->
<!-- title: Only Sub -->
<!-- custom_agent: Arch-UI-Detail -->
## Sub-001
- AC: ひとつだけ作る
"""


def _make_runner(
    tmp_path: Path,
    model: str = "claude-opus-4.7",
    *,
    orchestrator_ctx: OrchestratorContext | None = None,
) -> StepRunner:
    cfg = SDKConfig(model=model, run_id="run-split-fork-it", timeout_seconds=1)
    console = Console(verbose=False, quiet=True)
    return StepRunner(
        config=cfg, console=console, orchestrator_ctx=orchestrator_ctx,
    )


class _FakeSession:
    """SDK session の最小 fake。"""

    def __init__(self, response_text: str = "ok") -> None:
        self.response_text = response_text
        self.sent: List[str] = []
        self.disconnected = False

    def on(self, handler: Any) -> None:
        pass

    async def send_and_wait(self, prompt: str, timeout: float | None = None) -> Any:
        self.sent.append(prompt)
        # _extract_text が見るのは .text 属性または str
        resp = unittest.mock.MagicMock()
        resp.text = self.response_text
        return resp

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeFleetRpc:
    def __init__(self, started: bool = True) -> None:
        self.started = started
        self.requests: List[Any] = []

    async def start(self, request: Any) -> Any:
        self.requests.append(request)
        resp = unittest.mock.MagicMock()
        resp.started = self.started
        return resp


class _FakeFleetSession:
    def __init__(self, started: bool = True) -> None:
        self.fleet_rpc = _FakeFleetRpc(started=started)
        self.rpc = unittest.mock.MagicMock()
        self.rpc.fleet = self.fleet_rpc
        self.handlers: List[Any] = []
        self.sent: List[str] = []

    def on(self, handler: Any) -> Any:
        self.handlers.append(handler)
        return lambda: None

    async def send_and_wait(self, prompt: str, timeout: float | None = None) -> Any:
        self.sent.append(prompt)
        resp = unittest.mock.MagicMock()
        resp.text = "ok"
        return resp


class TestMaybeRunSplitForkDisabled(unittest.IsolatedAsyncioTestCase):
    """Orchestrator 未配下 / 機能 OFF で素通しすることを確認。"""

    async def test_ctx_none_returns_true_without_io(self):
        """orchestrator_ctx=None（単独実行モード）では素通し。"""
        runner = _make_runner(Path("."), orchestrator_ctx=None)
        result = await runner._maybe_run_split_fork(
            session=_FakeFleetSession(),
            step_id="2.1",
            custom_agent="Arch-UI-Detail",
        )
        self.assertTrue(result)

    async def test_split_fork_disabled_returns_true(self):
        """ctx.split_fork_enabled=False では素通し。"""
        ctx = OrchestratorContext(run_id="r", split_fork_enabled=False)
        runner = _make_runner(Path("."), orchestrator_ctx=ctx)
        result = await runner._maybe_run_split_fork(
            session=_FakeFleetSession(),
            step_id="2.1",
            custom_agent="Arch-UI-Detail",
        )
        self.assertTrue(result)

    async def test_split_fork_disabled_does_not_warn(self):
        """ctx.split_fork_enabled=False では WARN を出さず event で記録する（回帰）。

        CLI / GUI 標準経路では split_fork_enabled=False が正常値であり、毎ステップ
        console.warning（GUI「実行中の課題」へ流れる）を出していたノイズの回帰を防ぐ。
        """
        ctx = OrchestratorContext(run_id="r", split_fork_enabled=False)
        runner = _make_runner(Path("."), orchestrator_ctx=ctx)
        with unittest.mock.patch.object(
            runner.console, "warning"
        ) as mock_warning, unittest.mock.patch.object(
            runner.console, "event"
        ) as mock_event:
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
        self.assertTrue(result)
        mock_warning.assert_not_called()
        mock_event.assert_called_once()
        self.assertIn("legacy split-fork", mock_event.call_args.args[0])


class TestMaybeRunSplitForkNoSubissues(unittest.IsolatedAsyncioTestCase):
    """subissues.md 不在のとき True を返し副作用なし。"""

    async def test_no_subissues_returns_true(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertTrue(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestMaybeRunSplitForkSuccess(unittest.IsolatedAsyncioTestCase):
    """subissues.md 2 件、両方とも completion-report 出力で成功するシナリオ。"""

    async def test_two_subtasks_succeed(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-screen-detail-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            for idx in (1, 2):
                sub_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-screen-detail-step-2.1" / f"sub-{idx:03d}"
                sub_dir.mkdir(parents=True)
                (sub_dir / "completion-report.md").write_text(
                    "# Sub Report\n\n<!-- validation-confirmed -->\n",
                    encoding="utf-8",
                )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            fleet_session = _FakeFleetSession()

            result = await runner._maybe_run_split_fork(
                session=fleet_session,
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )

            self.assertTrue(result)
            self.assertEqual(len(fleet_session.fleet_rpc.requests), 1)
            self.assertIn("sub-001", fleet_session.fleet_rpc.requests[0].prompt)
            self.assertIn("sub-002", fleet_session.fleet_rpc.requests[0].prompt)
            self.assertEqual(runner._sub_sessions_created, 0)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root

    async def test_single_subtask_uses_parent_session_without_fleet(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-single-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_1, encoding="utf-8")
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )
            sub_dir = work_dir / "sub-001"
            sub_dir.mkdir(parents=True)
            (sub_dir / "completion-report.md").write_text(
                "<!-- validation-confirmed -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            parent_session = _FakeFleetSession()
            result = await runner._maybe_run_split_fork(
                session=parent_session,
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )

            self.assertTrue(result)
            self.assertEqual(len(parent_session.fleet_rpc.requests), 0)
            self.assertEqual(len(parent_session.sent), 1)
            self.assertIn("Sub-001", parent_session.sent[0])
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestMaybeRunSplitForkPartialFail(unittest.IsolatedAsyncioTestCase):
    """サブタスク 1 件が completion-report 未生成 → False 返却。"""

    async def test_one_missing_completion_report_fails(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-screen-detail-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            sub_dir1 = work_dir / "sub-001"
            sub_dir1.mkdir()
            (sub_dir1 / "completion-report.md").write_text(
                "<!-- validation-confirmed -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)

            async def _fake_create(client, opts):
                return _FakeSession()

            import types
            fake_copilot_session = types.ModuleType("copilot.session")

            class _PermissionHandler:
                @staticmethod
                async def approve_all(*args, **kwargs):
                    return True

            fake_copilot_session.PermissionHandler = _PermissionHandler

            with unittest.mock.patch(
                "runner._create_session_with_auto_reasoning_fallback",
                side_effect=_fake_create,
            ), unittest.mock.patch.dict(
                sys.modules, {"copilot.session": fake_copilot_session}
            ):
                result = await runner._maybe_run_split_fork(
                    session=_FakeFleetSession(),
                    step_id="2.1",
                    custom_agent="Arch-UI-Detail",
                )

            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestMaybeRunSplitForkMaxDepth(unittest.IsolatedAsyncioTestCase):
    """深度上限到達 → False。"""

    async def test_max_depth_returns_false(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-screen-detail-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(
                run_id="r", split_fork_depth=2, split_fork_max_depth=2,
            )
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestMaybeRunSplitForkParseError(unittest.IsolatedAsyncioTestCase):
    """subissues.md の title 欠落で SubIssuesParseError → False。"""

    async def test_invalid_subissues_fails(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-broken-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(
                "<!-- subissue -->\n<!-- labels: x -->\n## Sub-001\n",
                encoding="utf-8",
            )
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root

    async def test_parse_failure_renames_work_dir(self):
        """P-D: パース失敗時に work dir を `.failed-<timestamp>` にリネームする。"""
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            parent_dir = Path(tmpdir) / "work" / "Arch-UI-Detail"
            work_dir = parent_dir / "Issue-run-split-fork-it-broken-pd-step-2.1"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(
                "<!-- parent_issue: 1 -->\n\n"
                "| id | depends_on | input | output |\n"
                "|---|---|---|---|\n"
                "| W1 | - | a.md | b.md |\n"
                "| W2 | - | c.md | d.md |\n",
                encoding="utf-8",
            )
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
            self.assertFalse(
                work_dir.exists(),
                f"元の work_dir が残存している: {work_dir}",
            )
            failed_dirs = [
                d for d in parent_dir.iterdir()
                if d.is_dir() and d.name.startswith("Issue-run-split-fork-it-broken-pd-step-2.1.failed-")
            ]
            self.assertEqual(
                len(failed_dirs), 1,
                f"`.failed-*` ディレクトリが期待通り生成されていない: "
                f"{[d.name for d in parent_dir.iterdir()]}",
            )
            self.assertTrue((failed_dirs[0] / "subissues.md").is_file())
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestResolveWorkRootOverride(unittest.IsolatedAsyncioTestCase):
    """HVE_WORK_ROOT 環境変数で work_root を上書きできることを確認。"""

    async def test_env_var_override(self):
        import tempfile
        try:
            from hve.split_fork import resolve_work_root  # type: ignore[import-not-found]
        except ImportError:
            from split_fork import resolve_work_root  # type: ignore[import-not-found,no-redef]
        tmpdir = tempfile.mkdtemp()
        orig = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = tmpdir
        try:
            self.assertEqual(str(resolve_work_root()), str(Path(tmpdir).resolve()))
        finally:
            if orig is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig


class TestFallbackGlobDiscovery(unittest.IsolatedAsyncioTestCase):
    """custom_agent が None でも work/<任意>/Issue-*/subissues.md が拾えることを確認。"""

    async def test_fallback_glob_finds_subissues_when_custom_agent_none(self):
        import tempfile
        try:
            from hve.split_fork import discover_subissues_md_verbose  # type: ignore[import-not-found]
        except ImportError:
            from split_fork import discover_subissues_md_verbose  # type: ignore[import-not-found,no-redef]
        tmpdir = tempfile.mkdtemp()
        work_root = Path(tmpdir)
        # agent ディレクトリ配下に配置（custom_agent=None でも fallback で拾えること）
        sub_dir = work_root / "Some-Agent" / "Issue-xyz"
        sub_dir.mkdir(parents=True)
        (sub_dir / "subissues.md").write_text("dummy", encoding="utf-8")

        result = discover_subissues_md_verbose(
            work_root=work_root,
            custom_agent=None,
            parent_step_id="2.1",
        )
        self.assertIsNotNone(result.path)
        self.assertEqual(result.matched_pattern, "fallback-glob")


class TestSplitRequiredInconsistency(unittest.IsolatedAsyncioTestCase):
    """plan.md が SPLIT_REQUIRED 宣言だが subissues.md 不在 → Step 失敗化。"""

    async def test_plan_declares_split_but_no_subissues_fails(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            plan_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-run-split-fork-it-xyz-step-2.1"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n# Plan\n",
                encoding="utf-8",
            )
            # subissues.md は意図的に書かない

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestCrossRunIsolation(unittest.IsolatedAsyncioTestCase):
    """別 run の壊れた subissues.md を現在ステップから誤検出しないこと。"""

    async def test_other_run_subissues_is_ignored(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            other_dir = (
                Path(tmpdir) / "work" / "Arch-TDD-TestSpec"
                / "Issue-OTHERRUN-step-2-3"
            )
            other_dir.mkdir(parents=True)
            (other_dir / "subissues.md").write_text(
                "<!-- parent_issue: 1 -->\n\n"
                "| id | depends_on | input | output |\n"
                "|---|---|---|---|\n"
                "| W1 | - | a.md | b.md |\n",
                encoding="utf-8",
            )
            (Path(tmpdir) / "work" / "Arch-UI-List").mkdir(parents=True)

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="1",
                custom_agent="Arch-UI-List",
            )
            self.assertTrue(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestFailedDirIsIgnored(unittest.IsolatedAsyncioTestCase):
    """`.failed-*` 退避ディレクトリは探索から常に除外されること。"""

    async def test_failed_dir_is_ignored(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            failed_dir = (
                Path(tmpdir) / "work" / "Arch-UI-List"
                / "Issue-run-split-fork-it-step-1.failed-20260519T000000"
            )
            failed_dir.mkdir(parents=True)
            (failed_dir / "subissues.md").write_text(
                "<!-- subissue -->\n<!-- labels: x -->\n## Sub-001\n",
                encoding="utf-8",
            )
            (failed_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="1",
                custom_agent="Arch-UI-List",
            )
            self.assertTrue(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestNonSplitStepShortCircuit(unittest.IsolatedAsyncioTestCase):
    """plan.md が SPLIT_REQUIRED 非宣言なら discovery 自体が走らないこと。"""

    async def test_non_split_step_skips_discovery(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            other_dir = (
                Path(tmpdir) / "work" / "Arch-UI-Detail"
                / "Issue-run-split-fork-it-other-step-2.1"
            )
            other_dir.mkdir(parents=True)
            (other_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")
            (Path(tmpdir) / "work" / "Arch-UI-List").mkdir(parents=True)

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)

            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="1",
                custom_agent="Arch-UI-List",
            )
            self.assertTrue(result)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestStepScopeIsolation(unittest.IsolatedAsyncioTestCase):
    """同一 Agent × 別ステップが SPLIT_REQUIRED 宣言済みでも、本ステップ（非宣言）で
    fork が発火しないこと。"""

    async def test_other_step_split_required_does_not_trigger(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            other_step_dir = (
                Path(tmpdir) / "work" / "Arch-UI-Detail"
                / "Issue-run-split-fork-it-other-step-2.2"
            )
            other_step_dir.mkdir(parents=True)
            (other_step_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )
            (other_step_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertTrue(result)
            self.assertEqual(runner._sub_sessions_created, 0)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestStepSuffixRegex(unittest.TestCase):
    """`matches_step_scope` の境界判定。"""

    def _check(self, step_id, dir_name, expected):
        try:
            from hve.split_fork import matches_step_scope  # type: ignore[import-not-found]
        except ImportError:
            from split_fork import matches_step_scope  # type: ignore[import-not-found,no-redef]
        self.assertEqual(
            matches_step_scope(dir_name, step_id), expected,
            f"step_id={step_id!r} dir={dir_name!r} expected={expected}",
        )

    def test_exact_match_at_end(self):
        self._check("1", "Issue-r-step-1", True)

    def test_match_followed_by_failed_marker(self):
        self._check("1", "Issue-r-step-1.failed-20260101", True)

    def test_short_id_does_not_match_longer_step(self):
        self._check("1", "Issue-r-step-12", False)
        self._check("1", "Issue-r-step-1-2", False)

    def test_multilevel_step_id(self):
        self._check("2.1", "Issue-r-screen-step-2.1", True)
        self._check("2.1", "Issue-r-screen-step-2.1.failed-20260101", True)

    def test_none_or_empty_step_id_passes(self):
        self._check(None, "anything", True)
        self._check("", "anything", True)

    def test_web_ui_style_dir_without_step_token_passes(self):
        """Web UI 方式 `Issue-<番号>` 形式（step- トークンなし）はフィルタを通過する。"""
        self._check("2.1", "Issue-58", True)
        self._check("1", "Issue-42", True)
        self._check("1.1", "Issue-screen-detail", True)
        self._check("1.1", "Issue-arch-data-58", True)

    def test_cli_style_dir_with_step_token_filters_strictly(self):
        self._check("2", "Issue-r-step-1", False)
        self._check("2", "Issue-r-step-2", True)


class TestWebUIStyleIssueNaming(unittest.IsolatedAsyncioTestCase):
    """Web UI 方式 `Issue-<番号>` 形式（step- トークンなし）で fork が発火すること。"""

    async def test_web_ui_issue_dir_can_fork(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        os.environ["HVE_WORK_ROOT"] = str(Path(tmpdir) / "work")
        try:
            work_dir = (
                Path(tmpdir) / "work" / "Arch-UI-Detail"
                / "Issue-run-split-fork-it-58"
            )
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")
            (work_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8",
            )
            for idx in (1, 2):
                sub_dir = work_dir / f"sub-{idx:03d}"
                sub_dir.mkdir(parents=True)
                (sub_dir / "completion-report.md").write_text(
                    "<!-- validation-confirmed -->\n", encoding="utf-8",
                )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            fleet_session = _FakeFleetSession()

            result = await runner._maybe_run_split_fork(
                session=fleet_session,
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertTrue(result)
            self.assertEqual(len(fleet_session.fleet_rpc.requests), 1)
            self.assertEqual(runner._sub_sessions_created, 0)
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestRunScopedWorkRootInconsistency(unittest.IsolatedAsyncioTestCase):
    """T-C1.3 必須テスト 4: work_root が run_id を含む形式でも、
    現在 Agent の SPLIT_REQUIRED plan.md + subissues.md 不在は整合性違反として
    `_maybe_run_split_fork` が False を返すこと。

    T-C1.2 の runner.py 修正で plan_globs を `work_root / custom_agent / Issue-*`
    に絞り込み、`work_root_contains_run_id` 時は run_id フィルタを skip するよう
    変更したため、`Issue-0` 形式の plan.md も整合性違反として検出される。
    """

    async def test_run_scoped_inconsistency_detected_for_issue_zero(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        # _make_runner の SDKConfig.run_id と一致させ、work_root_contains_run_id が
        # True を返す状況を再現する (= 真因と同じ run-scoped work_root レイアウト)。
        run_id = "run-split-fork-it"
        scoped_work_root = Path(tmpdir) / "work" / "runs" / run_id
        os.environ["HVE_WORK_ROOT"] = str(scoped_work_root)
        try:
            custom_agent = "Arch-ApplicationAnalytics"
            plan_path = scoped_work_root / custom_agent / "Issue-0" / "plan.md"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n# Plan\n",
                encoding="utf-8",
            )
            # subissues.md は意図的に作らない (整合性違反状態)

            ctx = OrchestratorContext(run_id=run_id)
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="1",
                custom_agent=custom_agent,
            )
            self.assertFalse(
                result,
                "run-scoped work_root + Issue-0 形式の整合性違反が検出されていない",
            )
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


class TestOtherAgentPlanDoesNotPolluteCurrentStep(unittest.IsolatedAsyncioTestCase):
    """T-C1.3 必須テスト 5: 同 run 内に別 Agent の SPLIT_REQUIRED plan.md
    （+ subissues.md 不在）があっても、現在 Step (custom_agent=AgentA) は
    plan_globs の custom_agent 絞り込みにより影響を受けず素通し (True) される。
    """

    async def test_other_agents_split_plan_does_not_pollute_current_step(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        orig_work_root = os.environ.pop("HVE_WORK_ROOT", None)
        # _make_runner の SDKConfig.run_id と一致させて run-scoped work_root を作る。
        run_id = "run-split-fork-it"
        scoped_work_root = Path(tmpdir) / "work" / "runs" / run_id
        os.environ["HVE_WORK_ROOT"] = str(scoped_work_root)
        try:
            agent_a_dir = scoped_work_root / "AgentA" / "Issue-0"
            agent_b_dir = scoped_work_root / "AgentB" / "Issue-0"
            agent_a_dir.mkdir(parents=True)
            agent_b_dir.mkdir(parents=True)
            # AgentA: SPLIT 判定なし (通常完了状態)
            (agent_a_dir / "plan.md").write_text(
                "# normal plan (no SPLIT)\n", encoding="utf-8"
            )
            # AgentB: SPLIT_REQUIRED 宣言 + subissues.md なし (整合性違反状態)
            (agent_b_dir / "plan.md").write_text(
                "<!-- split_decision: SPLIT_REQUIRED -->\n", encoding="utf-8"
            )

            ctx = OrchestratorContext(run_id=run_id)
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                session=_FakeFleetSession(),
                step_id="1",
                custom_agent="AgentA",
            )
            self.assertTrue(
                result,
                "別 Agent (AgentB) の SPLIT_REQUIRED plan.md による誤検出で "
                "現 Agent (AgentA) のステップが失敗扱いになっている",
            )
        finally:
            os.chdir(orig_cwd)
            if orig_work_root is None:
                os.environ.pop("HVE_WORK_ROOT", None)
            else:
                os.environ["HVE_WORK_ROOT"] = orig_work_root


if __name__ == "__main__":
    unittest.main()
