"""test_resume_phase3.py — Phase 3 Resume 実行ロジックの統合テスト。

Phase 3 (Resume) で追加された 3 ファイル横断の振る舞いを検証する:

1. `DAGExecutor.on_step_complete` フックの呼び出し（completed/failed/skipped/blocked）
2. `StepRunner._create_or_resume_main_session` の resume / fallback 分岐
3. `StepRunner._mark_step_running` による state.json 更新
4. `_build_step_complete_callback` (orchestrator) による state.json 更新
5. `_restore_config_from_state` (orchestrator) による config 復元

Fake SDK は既存 `test_runner.py` の `TestRunStepWorkIqMcpHealthCheck` パターンを
踏襲し、`copilot` / `copilot.session` モジュールを差し替える。
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# orchestrator.py は `from hve.workflow_registry import ...` のような絶対 import を
# 含むため、repo root も sys.path に追加して `hve.*` を解決可能にする。
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from console import Console  # type: ignore[import-not-found]
from dag_executor import DAGExecutor, StepResult  # type: ignore[import-not-found]
from run_state import RunState, StepState, make_session_id  # type: ignore[import-not-found]
from runner import StepRunner  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# 共通スタブ
# ---------------------------------------------------------------------------


@dataclass
class _StepDef:
    id: str
    title: str
    custom_agent: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    is_container: bool = False
    body_template_path: Optional[str] = None
    skip_fallback_deps: List[str] = field(default_factory=list)
    block_unless: List[str] = field(default_factory=list)


class _WorkflowDef:
    """テスト用最小 WorkflowDef スタブ。"""

    def __init__(self, steps: List[_StepDef]) -> None:
        self.steps = steps
        self._index = {s.id: s for s in steps}

    def get_next_steps(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[_StepDef]:
        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing_ids = set(self._index.keys())

        result: List[_StepDef] = []
        for step in self.steps:
            if step.is_container:
                continue
            if step.id in completed or step.id in skipped:
                continue
            if not step.depends_on:
                result.append(step)
            else:
                deps_ok = all(
                    dep in effective_done or dep not in existing_ids
                    for dep in step.depends_on
                )
                if deps_ok:
                    result.append(step)
        return result


def _run(coro):
    return asyncio.run(coro)


def _make_state(
    work_dir: Path,
    run_id: str = "20260507T120000-phase3a",
    workflow_id: str = "akm",
    selected: Optional[List[str]] = None,
) -> RunState:
    return RunState.new(
        run_id=run_id,
        workflow_id=workflow_id,
        config=SDKConfig(),
        params={},
        selected_step_ids=selected or ["1", "2", "3"],
        work_dir=work_dir,
    )


# ---------------------------------------------------------------------------
# 3.A: DAGExecutor.on_step_complete フック
# ---------------------------------------------------------------------------


class TestDAGExecutorOnStepComplete(unittest.TestCase):
    """on_step_complete フックが completed/failed/skipped/blocked で呼ばれることを検証。"""

    def setUp(self) -> None:
        self.received: List[StepResult] = []

    def _callback(self, result: StepResult) -> None:
        self.received.append(result)

    def test_callback_invoked_on_success(self) -> None:
        wf = _WorkflowDef([
            _StepDef(id="1", title="S1"),
            _StepDef(id="2", title="S2", depends_on=["1"]),
        ])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            on_step_complete=self._callback,
        )
        _run(executor.execute())

        ids = [r.step_id for r in self.received]
        self.assertEqual(set(ids), {"1", "2"})
        self.assertTrue(all(r.success for r in self.received))

    def test_callback_invoked_on_failure(self) -> None:
        wf = _WorkflowDef([_StepDef(id="1", title="S1")])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return False

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},
            on_step_complete=self._callback,
        )
        _run(executor.execute())

        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].step_id, "1")
        self.assertFalse(self.received[0].success)

    def test_callback_invoked_on_inactive_skip(self) -> None:
        """active でないステップは skipped として通知される。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="S1"),
            _StepDef(id="2", title="S2"),
        ])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},  # "2" は inactive
            on_step_complete=self._callback,
        )
        _run(executor.execute())

        skipped_ids = [r.step_id for r in self.received if r.skipped]
        self.assertIn("2", skipped_ids)

    def test_callback_exception_does_not_stop_execution(self) -> None:
        """コールバック内の例外は実行を止めない（warn 出力のみ）。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="S1"),
            _StepDef(id="2", title="S2", depends_on=["1"]),
        ])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        def bad_callback(result: StepResult) -> None:
            raise RuntimeError("intentional")

        console = unittest.mock.MagicMock()
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            on_step_complete=bad_callback,
            console=console,
        )
        results = _run(executor.execute())

        # 両ステップとも完了している
        self.assertIn("1", results)
        self.assertIn("2", results)
        self.assertTrue(results["1"].success)
        self.assertTrue(results["2"].success)
        # warn が呼ばれている（例外を握り潰した証拠）
        self.assertTrue(console.warning.called)

    def test_no_callback_works_normally(self) -> None:
        """on_step_complete=None でも従来通り動作する（後方互換）。"""
        wf = _WorkflowDef([_StepDef(id="1", title="S1")])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},
        )
        results = _run(executor.execute())
        self.assertTrue(results["1"].success)


# ---------------------------------------------------------------------------
# 3.C / 3.D: StepRunner の resume_state 注入と resume_session 分岐
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, label: str = "main") -> None:
        self.label = label

    async def send_and_wait(self, *args, **kwargs):
        return None

    async def disconnect(self):
        return None

    def on(self, handler):
        return None


class _FakeClient:
    """create_session / resume_session の呼び出しを記録する Fake SDK Client。"""

    def __init__(
        self,
        *,
        resume_should_fail: bool = False,
    ) -> None:
        self.create_session_kwargs: List[Dict[str, Any]] = []
        self.resume_session_calls: List[Dict[str, Any]] = []
        self._resume_should_fail = resume_should_fail

    async def start(self):
        return None

    async def stop(self):
        return None

    async def create_session(self, **kwargs):
        self.create_session_kwargs.append(kwargs)
        return _FakeSession(label="main-create")

    async def resume_session(self, session_id, **kwargs):
        call = {"session_id": session_id, **kwargs}
        self.resume_session_calls.append(call)
        if self._resume_should_fail:
            raise RuntimeError("simulated resume failure")
        return _FakeSession(label="main-resume")


def _install_fake_copilot(monkeypatch_target: Dict[str, Any]) -> None:
    """`copilot` / `copilot.session` モジュールを Fake で差し替える。"""
    fake_copilot = types.ModuleType("copilot")
    fake_copilot.CopilotClient = lambda config=None: monkeypatch_target["client"]
    fake_copilot.SubprocessConfig = lambda **kwargs: object()
    fake_copilot.ExternalServerConfig = lambda **kwargs: object()

    fake_copilot_session = types.ModuleType("copilot.session")

    class _PermissionHandler:
        @staticmethod
        async def approve_all(*args, **kwargs):
            return True

    fake_copilot_session.PermissionHandler = _PermissionHandler

    monkeypatch_target["fake_copilot"] = fake_copilot
    monkeypatch_target["fake_copilot_session"] = fake_copilot_session


class TestStepRunnerResumeBranch(unittest.TestCase):
    """resume_state の status と session_id 一致による resume_session 呼び出しを検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_runner(
        self,
        *,
        resume_state: Optional[RunState],
        run_id: str = "run-resume-test",
    ) -> StepRunner:
        cfg = SDKConfig(
            dry_run=False,
            model="claude-opus-4.7",
            workiq_enabled=False,
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
            run_id=run_id,
        )
        console = Console(verbose=False, quiet=True)
        return StepRunner(config=cfg, console=console, resume_state=resume_state)

    def _expected_session_id(self, run_id: str, step_id: str) -> str:
        return make_session_id(run_id=run_id, step_id=step_id)

    def test_no_resume_state_uses_create_session(self) -> None:
        """resume_state=None なら create_session のみが呼ばれる（後方互換）。"""
        runner = self._make_runner(resume_state=None)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(client.create_session_kwargs), 1)
        self.assertEqual(len(client.resume_session_calls), 0)
        # 決定論的 session_id が付与されている
        self.assertEqual(
            client.create_session_kwargs[0].get("session_id"),
            self._expected_session_id(runner.config.run_id, "1.1"),
        )

    def test_completed_step_does_not_resume(self) -> None:
        """resume_state が "completed" の step は resume_session が呼ばれない。

        本来 completed なら orchestrator 側で executor.completed に登録され
        run_step に到達しないが、StepRunner 単独では call sites が判定する。
        ここでは「直接呼んでも resume にはならない」ことを確認する。
        """
        run_id = "run-completed-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])
        sid = self._expected_session_id(run_id, "1.1")
        state.update_step("1.1", status="completed", session_id=sid)

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertEqual(len(client.resume_session_calls), 0)
        self.assertEqual(len(client.create_session_kwargs), 1)

    def test_failed_step_uses_resume_session(self) -> None:
        """resume_state の step が "failed" なら resume_session() が呼ばれる。"""
        run_id = "run-failed-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])
        sid = self._expected_session_id(run_id, "1.1")
        state.update_step("1.1", status="failed", session_id=sid)

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertEqual(len(client.resume_session_calls), 1)
        self.assertEqual(client.resume_session_calls[0]["session_id"], sid)
        self.assertEqual(len(client.create_session_kwargs), 0)

    def test_running_step_uses_resume_session(self) -> None:
        """resume_state の step が "running" なら resume_session() が呼ばれる。"""
        run_id = "run-running-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])
        sid = self._expected_session_id(run_id, "1.1")
        state.update_step("1.1", status="running", session_id=sid)

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertEqual(len(client.resume_session_calls), 1)

    def test_resume_session_failure_falls_back_to_create_session(self) -> None:
        """resume_session が例外を投げたら create_session にフォールバックする。"""
        run_id = "run-fallback-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])
        sid = self._expected_session_id(run_id, "1.1")
        state.update_step("1.1", status="failed", session_id=sid)

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient(resume_should_fail=True)
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            result = asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertTrue(result)
        self.assertEqual(len(client.resume_session_calls), 1)
        # フォールバックで create_session が呼ばれた
        self.assertEqual(len(client.create_session_kwargs), 1)

    def test_session_id_mismatch_uses_create_session(self) -> None:
        """state の session_id が現在の決定論的 ID と一致しない場合は新規作成する。"""
        run_id = "run-mismatch-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])
        # 別の session_id を保存しておく
        state.update_step("1.1", status="failed", session_id="hve-old-different-step-1.1")

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        self.assertEqual(len(client.resume_session_calls), 0)
        self.assertEqual(len(client.create_session_kwargs), 1)

    def test_running_state_persisted_before_session_creation(self) -> None:
        """セッション作成前に state.json が "running" に更新される。"""
        run_id = "run-running-persist-test"
        state = _make_state(self.work_dir, run_id=run_id, selected=["1.1"])

        runner = self._make_runner(resume_state=state, run_id=run_id)
        client = _FakeClient()
        target = {"client": client}
        _install_fake_copilot(target)

        with unittest.mock.patch.dict(
            sys.modules,
            {"copilot": target["fake_copilot"], "copilot.session": target["fake_copilot_session"]},
        ):
            asyncio.run(runner.run_step("1.1", "テスト", "プロンプト"))

        # state.json が "running" に更新され、session_id が記録されている
        st = state.step_states["1.1"]
        # _create_or_resume_main_session 呼び出し時点で running になっており、
        # その後は execute 側のフックで上書きされるが、ここでは StepRunner.run_step 単独
        # 呼び出しで完了通知フックは無いため running のまま残るか、状態は session_id が
        # 必ず保存されていることを確認する
        self.assertEqual(
            st.session_id,
            self._expected_session_id(run_id, "1.1"),
        )
        self.assertIsNotNone(st.started_at)


# ---------------------------------------------------------------------------
# 3.E: _restore_config_from_state ヘルパー
# ---------------------------------------------------------------------------


class TestRestoreConfigFromState(unittest.TestCase):
    """orchestrator._restore_config_from_state による SDKConfig 復元を検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_snapshot_state(
        self,
        *,
        run_id: str = "20260507T130000-restore",
        config: Optional[SDKConfig] = None,
    ) -> RunState:
        return RunState.new(
            run_id=run_id,
            workflow_id="akm",
            config=config or SDKConfig(),
            params={},
            selected_step_ids=["1"],
            work_dir=self.work_dir,
        )

    def test_run_id_is_restored(self) -> None:
        from orchestrator import _restore_config_from_state  # type: ignore[import-not-found]

        state = self._make_snapshot_state(run_id="20260507T130000-restore")
        cfg = SDKConfig()
        _restore_config_from_state(cfg, state)
        self.assertEqual(cfg.run_id, "20260507T130000-restore")

    def test_model_is_restored(self) -> None:
        from orchestrator import _restore_config_from_state  # type: ignore[import-not-found]

        original = SDKConfig(model="claude-opus-4.7", max_parallel=7)
        state = self._make_snapshot_state(config=original)
        # 別 config に復元
        cfg = SDKConfig()
        _restore_config_from_state(cfg, state)
        self.assertEqual(cfg.model, "claude-opus-4.7")
        self.assertEqual(cfg.max_parallel, 7)

    def test_github_token_is_not_restored(self) -> None:
        """機密情報は snapshot に含まれず復元もされない。"""
        from orchestrator import _restore_config_from_state  # type: ignore[import-not-found]

        original = SDKConfig(github_token="ghp_secret_should_not_persist")
        state = self._make_snapshot_state(config=original)
        # snapshot に github_token が無いことを直接確認
        self.assertNotIn("github_token", state.config_snapshot)

        cfg = SDKConfig()  # 環境変数からの取得のみ
        _restore_config_from_state(cfg, state)
        # 復元後も github_token は元 SDKConfig が持つ値（snapshot からは復元されない）
        self.assertNotEqual(cfg.github_token, "ghp_secret_should_not_persist")

    def test_unknown_snapshot_keys_are_ignored(self) -> None:
        """SDKConfig に存在しない snapshot キーは無視される（schema 互換性）。"""
        from orchestrator import _restore_config_from_state  # type: ignore[import-not-found]

        state = self._make_snapshot_state()
        state.config_snapshot["__nonexistent_field__"] = "should be ignored"
        cfg = SDKConfig()
        # 例外を投げない
        _restore_config_from_state(cfg, state)
        self.assertFalse(hasattr(cfg, "__nonexistent_field__"))


# ---------------------------------------------------------------------------
# 3.B: _build_step_complete_callback による state.json 更新
# ---------------------------------------------------------------------------


class TestBuildStepCompleteCallback(unittest.TestCase):
    """orchestrator._build_step_complete_callback の振る舞いを検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_completed_result_persists_completed_status(self) -> None:
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir)
        console = unittest.mock.MagicMock()
        cb = _build_step_complete_callback(state, console)

        cb(StepResult(step_id="1", success=True, elapsed=2.5))

        # 永続化を確認: 別インスタンスで読み戻す
        reloaded = RunState.load(state.run_id, work_dir=self.work_dir)
        st = reloaded.step_states["1"]
        self.assertEqual(st.status, "completed")
        self.assertAlmostEqual(st.elapsed_seconds or 0.0, 2.5)
        self.assertIsNotNone(st.completed_at)

    def test_failed_result_persists_failed_status_and_error(self) -> None:
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir)
        console = unittest.mock.MagicMock()
        cb = _build_step_complete_callback(state, console)

        cb(StepResult(
            step_id="1", success=False, elapsed=1.0,
            error="RuntimeError: boom",
        ))

        reloaded = RunState.load(state.run_id, work_dir=self.work_dir)
        st = reloaded.step_states["1"]
        self.assertEqual(st.status, "failed")
        self.assertIn("boom", st.error_summary or "")

    def test_skipped_result_persists_skipped_status(self) -> None:
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir)
        console = unittest.mock.MagicMock()
        cb = _build_step_complete_callback(state, console)

        cb(StepResult(
            step_id="1", success=False, elapsed=0.0, skipped=True,
            state="skipped", reason="inactive",
        ))

        reloaded = RunState.load(state.run_id, work_dir=self.work_dir)
        st = reloaded.step_states["1"]
        self.assertEqual(st.status, "skipped")
        self.assertEqual(st.skip_reason, "inactive")

    def test_blocked_result_persists_blocked_status(self) -> None:
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir)
        console = unittest.mock.MagicMock()
        cb = _build_step_complete_callback(state, console)

        cb(StepResult(
            step_id="1", success=False, elapsed=0.0,
            state="blocked", reason="blocked_by_failed_dependency",
        ))

        reloaded = RunState.load(state.run_id, work_dir=self.work_dir)
        st = reloaded.step_states["1"]
        self.assertEqual(st.status, "blocked")
        self.assertEqual(st.skip_reason, "blocked_by_failed_dependency")

    def test_callback_swallows_io_errors(self) -> None:
        """state.update_step が例外を投げても callback は throw しない。"""
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir)
        console = unittest.mock.MagicMock()
        # update_step を例外を投げるように差し替え
        with unittest.mock.patch.object(
            state, "update_step", side_effect=OSError("disk full")
        ):
            cb = _build_step_complete_callback(state, console)
            # 例外を投げないこと
            cb(StepResult(step_id="1", success=True, elapsed=0.5))
        self.assertTrue(console.warning.called)


# ---------------------------------------------------------------------------
# 統合: DAGExecutor + on_step_complete + RunState の連携
# ---------------------------------------------------------------------------


class TestDAGExecutorWithRunStateCallback(unittest.TestCase):
    """DAGExecutor と RunState コールバックが完全に連携することを E2E で検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_completed_steps_persisted_to_state_json(self) -> None:
        """DAG 全完了時に state.json に全 step が completed として記録される。"""
        from orchestrator import _build_step_complete_callback  # type: ignore[import-not-found]

        state = _make_state(self.work_dir, selected=["1", "2"])
        console = unittest.mock.MagicMock()
        wf = _WorkflowDef([
            _StepDef(id="1", title="S1"),
            _StepDef(id="2", title="S2", depends_on=["1"]),
        ])

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            on_step_complete=_build_step_complete_callback(state, console),
        )
        _run(executor.execute())

        reloaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(reloaded.step_states["1"].status, "completed")
        self.assertEqual(reloaded.step_states["2"].status, "completed")

    def test_pre_registered_completed_steps_are_skipped(self) -> None:
        """resume_state.completed を executor.completed に事前登録すると再実行されない。"""
        state = _make_state(self.work_dir, selected=["1", "2"])
        # step "1" を完了済みとして state に登録
        state.update_step("1", status="completed")

        execution_order: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            execution_order.append(step_id)
            return True

        wf = _WorkflowDef([
            _StepDef(id="1", title="S1"),
            _StepDef(id="2", title="S2", depends_on=["1"]),
        ])

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
        )
        # orchestrator 側のロジックを再現: completed を事前登録
        executor.completed.add("1")

        _run(executor.execute())

        # "1" は再実行されず、"2" のみ実行される
        self.assertNotIn("1", execution_order)
        self.assertIn("2", execution_order)


if __name__ == "__main__":
    unittest.main()
