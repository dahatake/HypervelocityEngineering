"""test_run_state_phase1.py — Phase 1 (Resume 2-layer txn) のユニットテスト。

schema_version 2.0 化に伴う以下を検証:
- 旧 schema_version="1.0" の state.json が ValueError で拒否される
- 新フィールド (Intent / LockInfo / checkpoint_marker / journal_path 等) の round-trip
- 新フィールドが未指定の場合のデフォルト値
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    SCHEMA_VERSION,
    Intent,
    LockInfo,
    RunState,
    StepState,
    _SUPPORTED_SCHEMA_VERSIONS,
)


class TestSchemaVersionGuard(unittest.TestCase):
    """schema_version 拒否ロジックの検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_current_schema_version_is_2_0(self) -> None:
        self.assertEqual(SCHEMA_VERSION, "2.0")
        self.assertIn("2.0", _SUPPORTED_SCHEMA_VERSIONS)

    def test_old_schema_1_0_rejected_with_value_error(self) -> None:
        """schema_version='1.0' の state.json は読み込み時に ValueError を投げる。"""
        old_state = {
            "schema_version": "1.0",
            "run_id": "20260101T000000-old",
            "session_name": "old session",
            "workflow_id": "aas",
            "status": "paused",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:00:00+00:00",
            "host": {},
            "config_snapshot": {},
            "params_snapshot": {},
            "selected_step_ids": [],
            "step_states": {},
        }
        run_dir = self.work_dir / "20260101T000000-old"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps(old_state), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            RunState.load("20260101T000000-old", work_dir=self.work_dir)
        msg = str(ctx.exception)
        self.assertIn("schema_version", msg)
        self.assertIn("1.0", msg)

    def test_missing_schema_version_rejected(self) -> None:
        """schema_version キー欠落は ValueError。"""
        broken_state = {
            "run_id": "20260101T000000-nover",
            "session_name": "",
            "workflow_id": "aas",
            "status": "paused",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:00:00+00:00",
            "host": {},
            "config_snapshot": {},
            "params_snapshot": {},
            "selected_step_ids": [],
            "step_states": {},
        }
        run_dir = self.work_dir / "20260101T000000-nover"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps(broken_state), encoding="utf-8")
        with self.assertRaises(ValueError):
            RunState.load("20260101T000000-nover", work_dir=self.work_dir)

    def test_future_schema_version_rejected(self) -> None:
        """未知の将来バージョン (3.0) も ValueError。"""
        future_state = {
            "schema_version": "3.0",
            "run_id": "20260101T000000-fut",
            "session_name": "",
            "workflow_id": "aas",
            "status": "paused",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:00:00+00:00",
            "host": {},
            "config_snapshot": {},
            "params_snapshot": {},
            "selected_step_ids": [],
            "step_states": {},
        }
        run_dir = self.work_dir / "20260101T000000-fut"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps(future_state), encoding="utf-8")
        with self.assertRaises(ValueError):
            RunState.load("20260101T000000-fut", work_dir=self.work_dir)

    def test_save_then_load_uses_schema_2_0(self) -> None:
        """RunState.new で作成し save → load が schema 2.0 で成立する。"""
        state = RunState.new(
            run_id="20260507T000000-aaaaaa",
            workflow_id="akm",
            config=SDKConfig(),
            params={},
            selected_step_ids=["1.1"],
            work_dir=self.work_dir,
        )
        state.save()
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.schema_version, "2.0")


class TestNewFieldsRoundtrip(unittest.TestCase):
    """Phase 1 で追加された全フィールドの round-trip。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make(self) -> RunState:
        return RunState.new(
            run_id="20260507T000000-bbbbbb",
            workflow_id="akm",
            config=SDKConfig(),
            params={},
            selected_step_ids=["1.1", "1.2"],
            work_dir=self.work_dir,
        )

    def test_runstate_new_defaults(self) -> None:
        state = self._make()
        self.assertIsNone(state.journal_path)
        self.assertEqual(state.intent_log, [])
        self.assertEqual(state.sdk_session_index, {})
        self.assertIsNone(state.lock_holder)

    def test_stepstate_new_defaults(self) -> None:
        state = self._make()
        st = state.step_states["1.1"]
        self.assertIsNone(st.checkpoint_marker)
        self.assertEqual(st.last_journal_seq, 0)
        self.assertIsNone(st.sdk_session_exists)

    def test_runstate_new_fields_roundtrip(self) -> None:
        state = self._make()
        state.journal_path = "work/runs/20260507T000000-bbbbbb/journal.jsonl"
        state.intent_log = [
            Intent(seq=1, kind="delete-hard", target="some-sid",
                   started_at="2026-05-12T00:00:00+00:00",
                   completed_at=None, payload={"session_ids": ["s1", "s2"]}),
        ]
        state.sdk_session_index = {"hve-sid-1": "2026-05-12T00:00:00+00:00"}
        state.lock_holder = LockInfo(
            pid=12345, hostname_hash="abcdef0123456789",
            acquired_at="2026-05-12T00:00:00+00:00",
            heartbeat_at="2026-05-12T00:00:30+00:00",
        )
        state.save()

        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.journal_path, state.journal_path)
        self.assertEqual(len(loaded.intent_log), 1)
        self.assertEqual(loaded.intent_log[0].seq, 1)
        self.assertEqual(loaded.intent_log[0].kind, "delete-hard")
        self.assertIsNone(loaded.intent_log[0].completed_at)
        self.assertEqual(loaded.intent_log[0].payload["session_ids"], ["s1", "s2"])
        self.assertEqual(loaded.sdk_session_index, state.sdk_session_index)
        self.assertIsNotNone(loaded.lock_holder)
        self.assertEqual(loaded.lock_holder.pid, 12345)
        self.assertEqual(loaded.lock_holder.hostname_hash, "abcdef0123456789")

    def test_stepstate_new_fields_roundtrip(self) -> None:
        state = self._make()
        state.update_step("1.1",
                          checkpoint_marker="main-task-response-received",
                          last_journal_seq=42,
                          sdk_session_exists=True)
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        st = loaded.step_states["1.1"]
        self.assertEqual(st.checkpoint_marker, "main-task-response-received")
        self.assertEqual(st.last_journal_seq, 42)
        self.assertTrue(st.sdk_session_exists)

    def test_stepstate_negative_last_journal_seq_normalized(self) -> None:
        st = StepState(status="pending", last_journal_seq=-5)
        self.assertEqual(st.last_journal_seq, 0)


class TestIntentDataclass(unittest.TestCase):
    """Intent dataclass の基本動作。"""

    def test_intent_defaults(self) -> None:
        intent = Intent(seq=1, kind="test")
        self.assertEqual(intent.target, "")
        self.assertEqual(intent.started_at, "")
        self.assertIsNone(intent.completed_at)
        self.assertEqual(intent.payload, {})

    def test_intent_in_flight_detection(self) -> None:
        """completed_at is None なら in-flight。"""
        in_flight = Intent(seq=1, kind="delete-hard", started_at="t1")
        completed = Intent(seq=2, kind="delete-hard", started_at="t1", completed_at="t2")
        self.assertIsNone(in_flight.completed_at)
        self.assertIsNotNone(completed.completed_at)


class TestLockInfoDataclass(unittest.TestCase):
    """LockInfo dataclass の基本動作。"""

    def test_lockinfo_required_fields(self) -> None:
        li = LockInfo(pid=1, hostname_hash="h", acquired_at="t1")
        self.assertEqual(li.heartbeat_at, "")

    def test_lockinfo_full(self) -> None:
        li = LockInfo(pid=99, hostname_hash="abc", acquired_at="t1", heartbeat_at="t2")
        self.assertEqual(li.pid, 99)
        self.assertEqual(li.heartbeat_at, "t2")


if __name__ == "__main__":
    unittest.main()
