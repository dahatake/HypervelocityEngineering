"""test_recovery.py — Phase 4 (Resume 2-layer txn) recovery のユニットテスト。

`recover_pending_on_startup` の以下シナリオを検証:
- begin のみで end がない archive ファイルを検出して recovery
- SDK 削除途中でクラッシュした状態からの完遂
- 安全ガード: hve prefix で始まらない session_id は SDK 削除しない
- 完全成功フロー（end まで書かれている archive は no-op）
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from recovery import recover_pending_on_startup  # type: ignore[import-not-found]


def _write_archive(archive_dir: Path, name: str, records: List[dict]) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    p = archive_dir / name
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


class TestRecoveryBasic(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_root = Path(self._tmp.name)
        self.work_dir = self.work_root / "runs"
        self.archive_dir = self.work_root / "journal-archive"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_no_archive_dir_returns_empty(self) -> None:
        results = await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
        )
        self.assertEqual(results, [])

    async def test_completed_archive_not_recovered(self) -> None:
        _write_archive(self.archive_dir, "a.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": "run-x",
             "payload": {"session_ids": []}},
            {"seq": 1, "kind": "delete-hard.end", "target": "run-x", "payload": {}},
        ])
        results = await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
        )
        # scan_archive_for_pending が空を返すので results も空
        self.assertEqual(results, [])

    async def test_pending_dir_removal_recovered(self) -> None:
        """begin だけで end がなく、run_dir も残っているケースを recovery する。"""
        # 残存 run_dir を作る
        run_id = "20260512T000000-recov01"
        run_dir = self.work_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text("{}", encoding="utf-8")  # dummy
        # archive: begin だけ
        archive_path = _write_archive(self.archive_dir, "a.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": run_id,
             "payload": {"session_ids": [], "is_hard": False}},
        ])
        results = await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
        )
        self.assertEqual(len(results), 1)
        self.assertIn(1, results[0]["recovered_seqs"])
        self.assertFalse(run_dir.exists())
        # archive ファイルには end レコードが追加されている
        with archive_path.open("r", encoding="utf-8") as f:
            kinds = [json.loads(line)["kind"] for line in f if line.strip()]
        self.assertIn("delete-hard.end", kinds)
        self.assertIn("delete-hard.dir-removed", kinds)

    async def test_pending_sdk_delete_recovered(self) -> None:
        """SDK 削除が完了しなかった session_id を再削除する。"""
        run_id = "20260512T000000-recov02"
        run_dir = self.work_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text("{}", encoding="utf-8")

        archive_path = _write_archive(self.archive_dir, "b.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": run_id,
             "payload": {"session_ids": ["hve-sid-A", "hve-sid-B"], "is_hard": True}},
            # sid-A だけは成功済み
            {"seq": 1, "kind": "delete-hard.sdk-deleted", "target": "hve-sid-A",
             "payload": {}},
        ])

        deleted: List[str] = []
        existence_map = {"hve-sid-B": True}  # まだ存在

        async def fake_delete(sid: str) -> None:
            deleted.append(sid)
            existence_map[sid] = False

        async def fake_exists(sid: str) -> bool:
            return existence_map.get(sid, False)

        results = await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
            sdk_delete_session=fake_delete,
            sdk_session_exists=fake_exists,
        )
        self.assertEqual(len(results), 1)
        self.assertIn(1, results[0]["recovered_seqs"])
        # sid-A は既に sdk-deleted 記録あり → 再削除されない
        # sid-B は再削除される
        self.assertEqual(deleted, ["hve-sid-B"])

    async def test_safe_prefix_guard(self) -> None:
        """hve prefix で始まらない session_id は SDK 削除しない。"""
        run_id = "20260512T000000-recov03"
        archive_path = _write_archive(self.archive_dir, "c.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": run_id,
             "payload": {"session_ids": ["external-tool-session"], "is_hard": True}},
        ])

        deleted: List[str] = []

        async def fake_delete(sid: str) -> None:
            deleted.append(sid)

        async def fake_exists(sid: str) -> bool:
            return True

        results = await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
            sdk_delete_session=fake_delete,
            sdk_session_exists=fake_exists,
        )
        self.assertEqual(deleted, [])  # 削除されない
        self.assertTrue(any("prefix" in e for e in results[0]["errors"]))

    async def test_idempotent_already_absent(self) -> None:
        """SDK 側で既に削除済みなら no-op で sdk-deleted ステップを記録。"""
        run_id = "20260512T000000-recov04"
        archive_path = _write_archive(self.archive_dir, "d.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": run_id,
             "payload": {"session_ids": ["hve-sid-X"], "is_hard": True}},
        ])

        deleted: List[str] = []

        async def fake_delete(sid: str) -> None:
            deleted.append(sid)

        async def fake_exists(sid: str) -> bool:
            return False  # 既に存在しない

        await recover_pending_on_startup(
            work_dir=self.work_dir,
            archive_dir=self.archive_dir,
            sdk_delete_session=fake_delete,
            sdk_session_exists=fake_exists,
        )
        # delete は呼ばれない（idempotent）
        self.assertEqual(deleted, [])
        # archive には sdk-deleted ステップが追加されている
        with archive_path.open("r", encoding="utf-8") as f:
            kinds = [json.loads(line)["kind"] for line in f if line.strip()]
        self.assertIn("delete-hard.sdk-deleted", kinds)
        self.assertIn("delete-hard.end", kinds)


    async def test_unsafe_run_id_skips_rmtree(self) -> None:
        """不正な run_id（パストラバーサル含む）はディレクトリ削除を一切試行せずスキップする。

        Critical（コードレビュー指摘）: `_safe_run_id_component` の ValueError が
        旧実装では `except (OSError, ValueError)` で握りつぶされていた。修正後は
        try ブロックの外で安全性チェックを行い、即座に continue する。
        """
        run_id = "20260512T000000-recov05"
        # 攻撃的な run_id を target に持つ begin。`_safe_run_id_component` は
        # 許可文字 [A-Za-z0-9\-_] 以外を全て strip し、結果が空なら ValueError。
        # `///...` は全文字が除去されて空になるため ValueError が発生する。
        bad_target = "///...."
        archive_path = _write_archive(self.archive_dir, "e.jsonl", [
            {"seq": 1, "kind": "delete-hard.begin", "target": bad_target,
             "payload": {"session_ids": [], "is_hard": False}},
        ])

        # rmtree が一度でも呼ばれたら検知する
        rmtree_called: List[str] = []
        original_rmtree = __import__("shutil").rmtree

        def tracking_rmtree(path, *args, **kwargs):
            rmtree_called.append(str(path))
            return original_rmtree(path, *args, **kwargs)

        with mock.patch("recovery.shutil.rmtree", side_effect=tracking_rmtree):
            results = await recover_pending_on_startup(
                work_dir=self.work_dir,
                archive_dir=self.archive_dir,
            )

        # rmtree は呼ばれていない（不正 run_id では削除を試行しない）
        self.assertEqual(rmtree_called, [])
        # errors に「不正なrun_id」が記録されている
        self.assertEqual(len(results), 1)
        self.assertTrue(
            any("不正なrun_id" in e for e in results[0]["errors"]),
            f"errors={results[0]['errors']}",
        )


if __name__ == "__main__":
    unittest.main()