"""test_orchestrator_resume.py — Phase 5 (Major #17): _auto_reconcile_on_resume の smoke test。

orchestrator.py の `_auto_reconcile_on_resume` が以下を満たすことを最小限検証:
- SDK が import 可能なら reconcile_run を呼ぶ
- 例外発生時も run_workflow を阻害しない（warn のみ）
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    DEFAULT_SESSION_ID_PREFIX,
    RunState,
)


def _make_state_with_sid(work_dir: Path, run_id: str, sid: str) -> RunState:
    state = RunState.new(
        run_id=run_id, workflow_id="aas", config=SDKConfig(),
        params={}, selected_step_ids=["1"], work_dir=work_dir,
    )
    state.update_step("1", session_id=sid, status="running")
    return state


class TestAutoReconcileOnResume(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auto_reconcile_returns_normally_without_sdk(self) -> None:
        """SDK 未インストール時は何もせず正常終了する。"""
        run_id = "20260512T000000-arc01"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1"
        state = _make_state_with_sid(self.work_dir, run_id, sid)
        config = SDKConfig()

        # copilot module の import を失敗させる
        original_copilot = sys.modules.pop("copilot", None)
        try:
            with mock.patch.dict(sys.modules, {"copilot": None}):
                from orchestrator import _auto_reconcile_on_resume  # type: ignore[import-not-found]
                # 例外なく完了
                asyncio.run(_auto_reconcile_on_resume(state, config))
        finally:
            if original_copilot is not None:
                sys.modules["copilot"] = original_copilot

        # state は変更されていない
        self.assertEqual(state.step_states["1"].status, "running")

    def test_auto_reconcile_resets_state_only_session(self) -> None:
        """SDK 側で消失した sid を持つ step が pending に戻る。"""
        run_id = "20260512T000000-arc02"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1"
        state = _make_state_with_sid(self.work_dir, run_id, sid)
        state.save()
        config = SDKConfig()

        # Fake SDK module
        class _FakeClient:
            async def start(self):
                pass

            async def stop(self):
                pass

            async def get_session_metadata(self, sid_arg: str):
                return None  # 存在しない

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()
        fake_copilot.SubprocessConfig = lambda **kwargs: object()

        with mock.patch.dict(sys.modules, {"copilot": fake_copilot}):
            from orchestrator import _auto_reconcile_on_resume  # type: ignore[import-not-found]
            asyncio.run(_auto_reconcile_on_resume(state, config))

        # state.step_states["1"] が pending に戻っている
        self.assertEqual(state.step_states["1"].status, "pending")
        self.assertIsNone(state.step_states["1"].session_id)


if __name__ == "__main__":
    unittest.main()
