"""test_run_state_helpers.py — Phase 1 (v1.0.3, Major #15/#16): intent_log /
lock_holder 同期ヘルパーのユニットテスト。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from run_journal import RunJournal  # type: ignore[import-not-found]
from run_lock import RunLock  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    LockInfo,
    RunState,
    record_lock_holder,
    sync_intent_log_from_journal,
)


class TestSyncIntentLog(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"
        self.run_id = "20260512T000000-helper01"
        self.run_dir = self.work_dir / self.run_id

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_state(self) -> RunState:
        return RunState.new(
            run_id=self.run_id,
            workflow_id="aas",
            config=SDKConfig(),
            params={},
            selected_step_ids=["1"],
            work_dir=self.work_dir,
        )

    def test_sync_from_empty_journal(self) -> None:
        state = self._make_state()
        state.save()
        journal = RunJournal(self.run_dir)
        sync_intent_log_from_journal(state, journal)
        self.assertEqual(state.intent_log, [])

    def test_sync_from_pending_intent(self) -> None:
        state = self._make_state()
        state.save()
        journal = RunJournal(self.run_dir)
        seq = journal.begin(kind="delete-hard", target=self.run_id,
                            payload={"session_ids": ["hve-sid-1"]})
        # end は書かない → pending
        sync_intent_log_from_journal(state, journal)
        self.assertEqual(len(state.intent_log), 1)
        self.assertEqual(state.intent_log[0].seq, seq)
        self.assertEqual(state.intent_log[0].kind, "delete-hard.begin")
        self.assertIsNone(state.intent_log[0].completed_at)

    def test_sync_excludes_completed_intent(self) -> None:
        state = self._make_state()
        state.save()
        journal = RunJournal(self.run_dir)
        seq = journal.begin(kind="op1", target="x")
        journal.end(seq)
        sync_intent_log_from_journal(state, journal)
        # 完了済みなので pending には含まれない → intent_log は空
        self.assertEqual(state.intent_log, [])

    def test_sync_failure_is_silent(self) -> None:
        """journal が壊れていても例外を出さない。"""
        state = self._make_state()
        state.save()

        class _BrokenJournal:
            def pending_intents(self):
                raise RuntimeError("broken")

        # 例外なく no-op
        sync_intent_log_from_journal(state, _BrokenJournal())
        self.assertEqual(state.intent_log, [])


class TestRecordLockHolder(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"
        self.run_id = "20260512T000000-lockholder01"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_after_acquire(self) -> None:
        state = RunState.new(
            run_id=self.run_id, workflow_id="aas", config=SDKConfig(),
            params={}, selected_step_ids=["1"], work_dir=self.work_dir,
        )
        with RunLock(self.run_id, self.work_dir) as lock:
            record_lock_holder(state, lock)
        self.assertIsNotNone(state.lock_holder)
        self.assertEqual(state.lock_holder.pid, os.getpid())
        self.assertTrue(state.lock_holder.hostname_hash)
        self.assertTrue(state.lock_holder.acquired_at)

    def test_record_handles_invalid_lock_silently(self) -> None:
        state = RunState.new(
            run_id=self.run_id, workflow_id="aas", config=SDKConfig(),
            params={}, selected_step_ids=["1"], work_dir=self.work_dir,
        )
        # 必要属性を持たないオブジェクトを渡しても例外を出さない
        record_lock_holder(state, object())
        # lock_holder は LockInfo として生成されるが pid=0 / hostname_hash="" になる
        self.assertIsNotNone(state.lock_holder)
        self.assertEqual(state.lock_holder.pid, 0)


if __name__ == "__main__":
    unittest.main()
