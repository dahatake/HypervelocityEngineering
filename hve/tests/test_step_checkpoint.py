"""test_step_checkpoint.py — Phase 6 (Resume 2-layer txn) checkpoint marker のテスト。

`StepRunner._record_checkpoint` が以下を行うことを検証:
- `RunState.step_states[step_id].checkpoint_marker` を更新
- `RunJournal` が非 None なら journal にも記録
- 失敗時は warn のみで実行を継続（実行成功優先の原則）

Phase 6 では runner 内の各 phase 完了タイミングでの呼び出しは今後の TBD だが、
本テストでは基盤メソッドが正しく動作することを保証する。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from console import Console  # type: ignore[import-not-found]
from run_journal import RunJournal  # type: ignore[import-not-found]
from run_state import RunState, StepState  # type: ignore[import-not-found]
from runner import StepRunner  # type: ignore[import-not-found]


class TestRecordCheckpoint(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"
        self.run_id = "20260512T000000-cpoint01"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_state(self) -> RunState:
        return RunState.new(
            run_id=self.run_id,
            workflow_id="aas",
            config=SDKConfig(),
            params={},
            selected_step_ids=["1.1"],
            work_dir=self.work_dir,
        )

    def test_checkpoint_updates_state(self) -> None:
        state = self._make_state()
        state.save()
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=state,
        )
        runner._record_checkpoint("1.1", "main-task-response-received")
        self.assertEqual(
            state.step_states["1.1"].checkpoint_marker,
            "main-task-response-received",
        )

    def test_checkpoint_writes_to_journal(self) -> None:
        state = self._make_state()
        state.save()
        run_dir = self.work_dir / self.run_id
        journal = RunJournal(run_dir)
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=state,
            journal=journal,
        )
        runner._record_checkpoint("1.1", "qa-phase-done")
        # v1.0.3: 単発レコード step.checkpoint として記録される
        recs = journal.read_all()
        kinds = [r["kind"] for r in recs]
        self.assertIn("step.checkpoint", kinds)
        # begin/end は使われない
        self.assertNotIn("step.begin", kinds)
        self.assertNotIn("step.end", kinds)
        # payload の marker を確認
        cp_rec = next(r for r in recs if r["kind"] == "step.checkpoint")
        self.assertEqual(cp_rec["payload"]["marker"], "qa-phase-done")

    def test_checkpoint_with_only_state_no_journal(self) -> None:
        """journal=None でも state 更新は行われる。"""
        state = self._make_state()
        state.save()
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=state,
            journal=None,
        )
        runner._record_checkpoint("1.1", "review-phase-done")
        self.assertEqual(
            state.step_states["1.1"].checkpoint_marker,
            "review-phase-done",
        )
        # last_journal_seq は 0 のまま
        self.assertEqual(state.step_states["1.1"].last_journal_seq, 0)

    def test_checkpoint_with_only_journal_no_state(self) -> None:
        """resume_state=None でも journal は書かれる。"""
        run_dir = self.work_dir / self.run_id
        run_dir.mkdir(parents=True)
        journal = RunJournal(run_dir)
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=None,
            journal=journal,
        )
        runner._record_checkpoint("1.1", "main-task-response-received")
        recs = journal.read_all()
        self.assertTrue(any(r["kind"] == "step.checkpoint" for r in recs))

    def test_checkpoint_noop_when_both_none(self) -> None:
        """両方 None なら何もしない（実行成功優先）。"""
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=None,
            journal=None,
        )
        # 例外なく no-op
        runner._record_checkpoint("1.1", "any-marker")

    def test_step_state_persists_last_journal_seq(self) -> None:
        """checkpoint 記録後、state.step_states[*].last_journal_seq が journal seq と一致。"""
        state = self._make_state()
        state.save()
        run_dir = self.work_dir / self.run_id
        journal = RunJournal(run_dir)
        runner = StepRunner(
            config=SDKConfig(run_id=self.run_id),
            console=Console(quiet=True),
            resume_state=state,
            journal=journal,
        )
        runner._record_checkpoint("1.1", "main-task-response-received")
        runner._record_checkpoint("1.1", "qa-phase-done")
        # v1.0.3: 2 回呼んだので seq は 2（record_event は 1 回あたり 1 seq）
        self.assertGreaterEqual(state.step_states["1.1"].last_journal_seq, 2)
        # 永続化されている
        loaded = RunState.load(self.run_id, work_dir=self.work_dir)
        self.assertEqual(
            loaded.step_states["1.1"].checkpoint_marker,
            "qa-phase-done",
        )


if __name__ == "__main__":
    unittest.main()
