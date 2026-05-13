"""test_run_journal.py — Phase 3 (Resume 2-layer txn) RunJournal のユニットテスト。"""

from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_journal import (  # type: ignore[import-not-found]
    JOURNAL_FILENAME,
    ROTATE_SIZE_BYTES,
    JournalError,
    RunJournal,
    scan_archive_for_pending,
)


class TestRunJournalBasic(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "20260512T000000-test01"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_begin_creates_journal_file(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="delete-hard", target="run-1", payload={"x": 1})
        self.assertEqual(seq, 1)
        self.assertTrue((self.run_dir / JOURNAL_FILENAME).exists())

    def test_begin_step_end_roundtrip(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="delete-hard", target="run-1", payload={})
        j.step(seq, kind="delete-hard.sdk-deleted", target="sid-1")
        j.step(seq, kind="delete-hard.dir-removed", target="run-1")
        j.end(seq)
        recs = j.read_all()
        self.assertEqual(len(recs), 4)
        kinds = [r["kind"] for r in recs]
        self.assertEqual(kinds, [
            "delete-hard.begin",
            "delete-hard.sdk-deleted",
            "delete-hard.dir-removed",
            "delete-hard.end",
        ])

    def test_seq_increments_monotonically(self) -> None:
        j = RunJournal(self.run_dir)
        s1 = j.begin(kind="op1", target="a")
        j.end(s1)
        s2 = j.begin(kind="op2", target="b")
        s3 = j.begin(kind="op3", target="c")
        self.assertEqual(s1, 1)
        self.assertEqual(s2, 2)
        self.assertEqual(s3, 3)

    def test_seq_resumes_from_existing_records(self) -> None:
        """別インスタンスで journal を開いても seq は連番継続。"""
        j1 = RunJournal(self.run_dir)
        j1.begin(kind="op1", target="")
        j1.end(1)
        # 別インスタンス
        j2 = RunJournal(self.run_dir)
        new_seq = j2.begin(kind="op2", target="")
        self.assertEqual(new_seq, 2)

    def test_end_auto_infers_kind_from_begin(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="my-op", target="x")
        j.end(seq)
        recs = j.read_all()
        self.assertEqual(recs[-1]["kind"], "my-op.end")

    def test_end_without_begin_raises(self) -> None:
        j = RunJournal(self.run_dir)
        with self.assertRaises(JournalError):
            j.end(99)

    def test_end_explicit_kind(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="op", target="")
        j.end(seq, kind="op.completed", target="x", payload={"result": "ok"})
        recs = j.read_all()
        self.assertEqual(recs[-1]["kind"], "op.completed")
        self.assertEqual(recs[-1]["payload"]["result"], "ok")

    def test_invalid_seq_raises(self) -> None:
        j = RunJournal(self.run_dir)
        with self.assertRaises(ValueError):
            j.step(0, kind="x")
        with self.assertRaises(ValueError):
            j.end(-1)


class TestPendingIntents(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "run"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_journal_no_pending(self) -> None:
        j = RunJournal(self.run_dir)
        self.assertEqual(j.pending_intents(), [])

    def test_in_flight_begin_is_pending(self) -> None:
        j = RunJournal(self.run_dir)
        j.begin(kind="op", target="t1", payload={"x": 1})
        pending = j.pending_intents()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["seq"], 1)
        self.assertEqual(pending[0]["kind"], "op.begin")
        self.assertEqual(pending[0]["target"], "t1")

    def test_completed_begin_not_pending(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="op", target="t1")
        j.end(seq)
        self.assertEqual(j.pending_intents(), [])

    def test_multiple_concurrent_intents(self) -> None:
        j = RunJournal(self.run_dir)
        s1 = j.begin(kind="op1", target="a")
        s2 = j.begin(kind="op2", target="b")
        j.end(s1)
        # s2 still pending
        pending = j.pending_intents()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["seq"], 2)

    def test_corrupted_lines_skipped(self) -> None:
        j = RunJournal(self.run_dir)
        j.begin(kind="op", target="x")
        # 破損行を直接追加
        with (self.run_dir / JOURNAL_FILENAME).open("a", encoding="utf-8") as f:
            f.write("not-valid-json\n")
            f.write("{partial\n")
        # 破損行は無視され pending は変わらない
        pending = j.pending_intents()
        self.assertEqual(len(pending), 1)


class TestRecordsForAndReadAll(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "run"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_records_for_specific_seq(self) -> None:
        j = RunJournal(self.run_dir)
        s1 = j.begin(kind="op1", target="a")
        s2 = j.begin(kind="op2", target="b")
        j.step(s1, kind="op1.progress")
        j.end(s1)
        recs_s1 = j.records_for(s1)
        self.assertEqual(len(recs_s1), 3)
        kinds = [r["kind"] for r in recs_s1]
        self.assertEqual(kinds, ["op1.begin", "op1.progress", "op1.end"])


class TestArchive(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        self.run_dir = self.work_dir / "runs" / "20260512T000000-archive01"
        self.archive_dir = self.work_dir / "journal-archive"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_archive_moves_journal(self) -> None:
        j = RunJournal(self.run_dir)
        seq = j.begin(kind="op", target="x")
        j.end(seq)
        result = j.archive(self.archive_dir)
        self.assertIsNotNone(result)
        self.assertTrue(result.exists())
        self.assertFalse((self.run_dir / JOURNAL_FILENAME).exists())
        # archive ファイル名は run_id + timestamp
        self.assertIn("20260512T000000-archive01", result.name)
        self.assertTrue(result.name.endswith(".jsonl"))

    def test_archive_no_journal_returns_none(self) -> None:
        j = RunJournal(self.run_dir)
        result = j.archive(self.archive_dir)
        self.assertIsNone(result)


class TestRotate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "run"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_small_journal_not_rotated(self) -> None:
        j = RunJournal(self.run_dir)
        j.begin(kind="op", target="")
        result = j.rotate_if_needed()
        self.assertIsNone(result)

    def test_large_journal_rotated_to_gzip(self) -> None:
        # ROTATE_SIZE_BYTES を意図的に小さくして検証
        from run_journal import RunJournal as RJ
        import run_journal
        original = run_journal.ROTATE_SIZE_BYTES
        try:
            run_journal.ROTATE_SIZE_BYTES = 100  # 100 bytes
            j = RJ(self.run_dir)
            for i in range(20):
                j.begin(kind=f"op{i}", target="x" * 20, payload={"k": "v" * 10})
            # サイズが 100 を超えるはず
            result = j.rotate_if_needed()
            self.assertIsNotNone(result)
            self.assertTrue(result.name.endswith(".jsonl.gz"))
            self.assertTrue(result.exists())
            # gzip として読める
            with gzip.open(result, "rb") as f:
                data = f.read().decode("utf-8")
            self.assertIn("op0.begin", data)
            # 元ファイルは消えている
            self.assertFalse((self.run_dir / JOURNAL_FILENAME).exists())
        finally:
            run_journal.ROTATE_SIZE_BYTES = original

    def test_rotate_auto_triggers_in_append(self) -> None:
        """Critical #4 (v1.0.2): _ROTATE_CHECK_INTERVAL 経過時に rotate が
        自動発火することを検証する。"""
        from run_journal import RunJournal as RJ
        import run_journal
        orig_size = run_journal.ROTATE_SIZE_BYTES
        orig_interval = run_journal._ROTATE_CHECK_INTERVAL
        try:
            run_journal.ROTATE_SIZE_BYTES = 50
            run_journal._ROTATE_CHECK_INTERVAL = 5  # 5 レコードごとに stat
            j = RJ(self.run_dir)
            for i in range(20):
                j.begin(kind=f"op{i}", target="x" * 50, payload={"key": "v" * 30})
            # rotate ファイルが生成されているはず
            rotated = list(self.run_dir.glob("journal.*.jsonl.gz"))
            self.assertGreaterEqual(len(rotated), 1)
        finally:
            run_journal.ROTATE_SIZE_BYTES = orig_size
            run_journal._ROTATE_CHECK_INTERVAL = orig_interval


class TestScanArchiveForPending(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.archive_dir = Path(self._tmp.name) / "journal-archive"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_records(self, name: str, records: list) -> Path:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        p = self.archive_dir / name
        with p.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return p

    def test_archive_with_unmatched_begin_is_pending(self) -> None:
        self._write_records("a.jsonl", [
            {"seq": 1, "kind": "op.begin", "target": "x"},
            # end が無い
        ])
        result = scan_archive_for_pending(self.archive_dir)
        self.assertEqual(len(result), 1)

    def test_complete_archive_not_pending(self) -> None:
        self._write_records("a.jsonl", [
            {"seq": 1, "kind": "op.begin", "target": "x"},
            {"seq": 1, "kind": "op.end", "target": "x"},
        ])
        result = scan_archive_for_pending(self.archive_dir)
        self.assertEqual(result, [])

    def test_missing_dir_returns_empty(self) -> None:
        result = scan_archive_for_pending(self.archive_dir / "nonexistent")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
