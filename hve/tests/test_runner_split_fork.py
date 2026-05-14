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
from orchestrator_context import OrchestratorContext  # type: ignore[import-not-found]


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


def _make_runner(
    tmp_path: Path,
    model: str = "claude-opus-4.7",
    *,
    orchestrator_ctx: OrchestratorContext | None = None,
) -> StepRunner:
    cfg = SDKConfig(model=model, run_id="run-split-fork-it")
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


class TestMaybeRunSplitForkDisabled(unittest.IsolatedAsyncioTestCase):
    """Orchestrator 未配下 / 機能 OFF で素通しすることを確認。"""

    async def test_ctx_none_returns_true_without_io(self):
        """orchestrator_ctx=None（単独実行モード）では素通し。"""
        runner = _make_runner(Path("."), orchestrator_ctx=None)
        result = await runner._maybe_run_split_fork(
            client=unittest.mock.MagicMock(),
            step_id="2.1",
            custom_agent="Arch-UI-Detail",
        )
        self.assertTrue(result)

    async def test_split_fork_disabled_returns_true(self):
        """ctx.split_fork_enabled=False では素通し。"""
        ctx = OrchestratorContext(run_id="r", split_fork_enabled=False)
        runner = _make_runner(Path("."), orchestrator_ctx=ctx)
        result = await runner._maybe_run_split_fork(
            client=unittest.mock.MagicMock(),
            step_id="2.1",
            custom_agent="Arch-UI-Detail",
        )
        self.assertTrue(result)


class TestMaybeRunSplitForkNoSubissues(unittest.IsolatedAsyncioTestCase):
    """subissues.md 不在のとき True を返し副作用なし。"""

    async def test_no_subissues_returns_true(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                client=unittest.mock.MagicMock(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertTrue(result)
        finally:
            os.chdir(orig_cwd)


class TestMaybeRunSplitForkSuccess(unittest.IsolatedAsyncioTestCase):
    """subissues.md 2 件、両方とも completion-report 出力で成功するシナリオ。"""

    async def test_two_subtasks_succeed(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-screen-detail"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")

            for idx in (1, 2):
                sub_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-screen-detail" / f"sub-{idx:03d}"
                sub_dir.mkdir(parents=True)
                (sub_dir / "completion-report.md").write_text(
                    "# Sub Report\n\n<!-- validation-confirmed -->\n",
                    encoding="utf-8",
                )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)

            fake_sessions: List[_FakeSession] = []

            async def _fake_create(client, opts):
                s = _FakeSession()
                fake_sessions.append(s)
                return s

            with unittest.mock.patch(
                "runner._create_session_with_auto_reasoning_fallback",
                side_effect=_fake_create,
            ):
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
                    result = await runner._maybe_run_split_fork(
                        client=unittest.mock.MagicMock(),
                        step_id="2.1",
                        custom_agent="Arch-UI-Detail",
                    )

            self.assertTrue(result)
            self.assertEqual(len(fake_sessions), 2)
            self.assertEqual(runner._sub_sessions_created, 2)
            for s in fake_sessions:
                self.assertTrue(s.disconnected)
        finally:
            os.chdir(orig_cwd)


class TestMaybeRunSplitForkPartialFail(unittest.IsolatedAsyncioTestCase):
    """サブタスク 1 件が completion-report 未生成 → False 返却。"""

    async def test_one_missing_completion_report_fails(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-screen-detail"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")

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
                    client=unittest.mock.MagicMock(),
                    step_id="2.1",
                    custom_agent="Arch-UI-Detail",
                )

            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)


class TestMaybeRunSplitForkMaxDepth(unittest.IsolatedAsyncioTestCase):
    """深度上限到達 → False。"""

    async def test_max_depth_returns_false(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-screen-detail"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(_SUBISSUES_2, encoding="utf-8")

            ctx = OrchestratorContext(
                run_id="r", split_fork_depth=2, split_fork_max_depth=2,
            )
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                client=unittest.mock.MagicMock(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)


class TestMaybeRunSplitForkParseError(unittest.IsolatedAsyncioTestCase):
    """subissues.md の title 欠落で SubIssuesParseError → False。"""

    async def test_invalid_subissues_fails(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            work_dir = Path(tmpdir) / "work" / "Arch-UI-Detail" / "Issue-broken"
            work_dir.mkdir(parents=True)
            (work_dir / "subissues.md").write_text(
                "<!-- subissue -->\n<!-- labels: x -->\n## Sub-001\n",
                encoding="utf-8",
            )

            ctx = OrchestratorContext(run_id="r")
            runner = _make_runner(Path(tmpdir), orchestrator_ctx=ctx)
            result = await runner._maybe_run_split_fork(
                client=unittest.mock.MagicMock(),
                step_id="2.1",
                custom_agent="Arch-UI-Detail",
            )
            self.assertFalse(result)
        finally:
            os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
