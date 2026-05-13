"""test_reconciler.py — Phase 5 (Resume 2-layer txn) Reconciler / GC のユニットテスト。"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from reconciler import (  # type: ignore[import-not-found]
    GcResult,
    ReconcileResult,
    gc_orphans,
    reconcile_all,
    reconcile_run,
)
from run_state import (  # type: ignore[import-not-found]
    DEFAULT_SESSION_ID_PREFIX,
    RunState,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeSDKClient:
    """ReconcileResult / GcResult 用の Fake SDK Client。"""

    def __init__(self, existing_sids: set, all_sids: Optional[list] = None) -> None:
        self.existing = set(existing_sids)
        self.all_sids = all_sids or list(existing_sids)
        self.deleted: List[str] = []

    async def get_session_metadata(self, sid: str):
        return object() if sid in self.existing else None

    async def list_sessions(self):
        # SDK の SessionMetadata-like なシンプル obj を返す
        class _M:
            def __init__(self, s):
                self.sessionId = s
        return [_M(s) for s in self.all_sids]

    async def delete_session(self, sid: str) -> None:
        self.deleted.append(sid)
        self.existing.discard(sid)


def _make_state_with_sids(work_dir: Path, run_id: str, sids_per_step: dict) -> RunState:
    state = RunState.new(
        run_id=run_id,
        workflow_id="aas",
        config=SDKConfig(),
        params={},
        selected_step_ids=list(sids_per_step.keys()),
        work_dir=work_dir,
    )
    for step_id, sid in sids_per_step.items():
        state.update_step(step_id, session_id=sid, status="running")
    return state


class TestReconcileRun(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_both_only(self) -> None:
        """state.json と SDK 両方に存在する sid は sessions_both に分類。"""
        run_id = "20260512T000000-rec01"
        state = _make_state_with_sids(
            self.work_dir, run_id,
            {"1.1": f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"},
        )
        client = _FakeSDKClient(existing_sids={f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"})
        result = _run(reconcile_run(state, sdk_client=client, dry_run=True))
        self.assertEqual(len(result.sessions_both), 1)
        self.assertEqual(result.sessions_state_only, [])
        self.assertEqual(result.sessions_sdk_only, [])

    def test_state_only_dry_run(self) -> None:
        """SDK 側に存在しない sid は sessions_state_only に分類、dry_run では state 変更なし。"""
        run_id = "20260512T000000-rec02"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"
        state = _make_state_with_sids(self.work_dir, run_id, {"1.1": sid})
        client = _FakeSDKClient(existing_sids=set())  # SDK 側になし
        result = _run(reconcile_run(state, sdk_client=client, dry_run=True))
        self.assertEqual(result.sessions_state_only, [sid])
        self.assertEqual(state.step_states["1.1"].status, "running")  # 未変更
        self.assertEqual(state.step_states["1.1"].session_id, sid)  # 未変更
        # actions_pending に記録されている
        self.assertTrue(any("pending" in a for a in result.actions_pending))

    def test_state_only_auto_fix(self) -> None:
        """dry_run=False で state_only の step が pending に戻る。"""
        run_id = "20260512T000000-rec03"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"
        state = _make_state_with_sids(self.work_dir, run_id, {"1.1": sid})
        client = _FakeSDKClient(existing_sids=set())
        result = _run(reconcile_run(state, sdk_client=client, dry_run=False))
        self.assertEqual(state.step_states["1.1"].status, "pending")
        self.assertIsNone(state.step_states["1.1"].session_id)
        self.assertFalse(state.step_states["1.1"].sdk_session_exists)
        self.assertTrue(result.actions_taken)

        # 永続化されている
        loaded = RunState.load(run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.step_states["1.1"].status, "pending")

    def test_sdk_only_detection(self) -> None:
        """SDK 側にしかない hve-* sid は sessions_sdk_only に列挙される。"""
        run_id = "20260512T000000-rec04"
        # state は空
        state = RunState.new(
            run_id=run_id, workflow_id="aas", config=SDKConfig(),
            params={}, selected_step_ids=["1"], work_dir=self.work_dir,
        )
        # SDK 側に勝手な orphan
        orphan = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-9"
        client = _FakeSDKClient(existing_sids={orphan}, all_sids=[orphan])

        async def _list():
            return await client.list_sessions()

        result = _run(reconcile_run(state, sdk_client=client, dry_run=True,
                                     sdk_list_sessions=_list))
        self.assertIn(orphan, result.sessions_sdk_only)

    def test_no_sdk_client_degraded(self) -> None:
        """sdk_client=None なら state 内 sid は unknown 扱い（Critical #2 修正後）。"""
        run_id = "20260512T000000-rec05"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"
        state = _make_state_with_sids(self.work_dir, run_id, {"1.1": sid})
        result = _run(reconcile_run(state, sdk_client=None, dry_run=True))
        # v1.0.2: SDK 未接続時は both ではなく unknown に分類する
        self.assertEqual(result.sessions_unknown, [sid])
        self.assertEqual(result.sessions_both, [])
        self.assertEqual(result.sessions_state_only, [])
        self.assertTrue(any("SDK 未接続" in p for p in result.actions_pending))


    def test_state_only_save_failure_rolls_back_in_memory(self) -> None:
        """state.update_step の save() が失敗したらメモリ上の変更もロールバックする。

        High（コードレビュー指摘）: 旧実装では update_step のメモリ変更は
        行われたが save() 失敗時にロールバックされず、ディスクとメモリが
        不整合になっていた。修正後は OSError を catch してメモリも元に戻す。
        """
        run_id = "20260512T000000-rec06"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"
        state = _make_state_with_sids(self.work_dir, run_id, {"1.1": sid})
        client = _FakeSDKClient(existing_sids=set())  # SDK 側になし → state_only

        # save() を強制的に OSError を投げるように patch
        original_status = state.step_states["1.1"].status
        original_sid = state.step_states["1.1"].session_id

        with mock.patch.object(state, "save",
                                side_effect=OSError("disk full simulated")):
            result = _run(reconcile_run(state, sdk_client=client, dry_run=False))

        # メモリ上の state は元の値にロールバックされている
        self.assertEqual(state.step_states["1.1"].status, original_status)
        self.assertEqual(state.step_states["1.1"].session_id, original_sid)
        # actions_taken には記録されない（save 失敗）
        self.assertEqual(result.actions_taken, [])
        # actions_pending に save 失敗 + ロールバック旨のメッセージ
        self.assertTrue(
            any("save 失敗" in p and "ロールバック" in p
                for p in result.actions_pending),
            f"actions_pending={result.actions_pending}",
        )

    def test_both_save_failure_rolls_back_sdk_session_index(self) -> None:
        """sessions_both 側の save 失敗時に sdk_session_index 変更がロールバックされる。"""
        run_id = "20260512T000000-rec07"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1-1"
        state = _make_state_with_sids(self.work_dir, run_id, {"1.1": sid})
        client = _FakeSDKClient(existing_sids={sid})  # 両方に存在

        # 最初の数回（update_step 内の save）は成功させ、最後の outer save だけ失敗
        original_save = state.save
        call_count = {"n": 0}

        def selective_failing_save():
            call_count["n"] += 1
            # 呼び出し順: 1回目 update_step 内 save (成功), 2回目 outer save (失敗)
            if call_count["n"] >= 2:
                raise OSError("disk full simulated")
            return original_save()

        original_index = dict(state.sdk_session_index)

        with mock.patch.object(state, "save", side_effect=selective_failing_save):
            result = _run(reconcile_run(state, sdk_client=client, dry_run=False))

        # sdk_session_index がロールバックされて元の値と等しい
        self.assertEqual(state.sdk_session_index, original_index)
        # actions_pending に save 失敗 + ロールバックメッセージ
        self.assertTrue(
            any("sdk_session_index" in p and "ロールバック" in p
                for p in result.actions_pending),
            f"actions_pending={result.actions_pending}",
        )



    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_multiple_runs(self) -> None:
        run_id_1 = "20260512T000000-recA"
        run_id_2 = "20260512T000000-recB"
        sid_1 = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id_1}-step-1"
        sid_2 = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id_2}-step-1"
        _make_state_with_sids(self.work_dir, run_id_1, {"1": sid_1})
        _make_state_with_sids(self.work_dir, run_id_2, {"1": sid_2})
        # 片方だけ SDK 側に存在
        client = _FakeSDKClient(existing_sids={sid_1})
        results = _run(reconcile_all(self.work_dir, sdk_client=client, dry_run=True))
        self.assertEqual(len(results), 2)
        self.assertIn(run_id_1, results)
        self.assertIn(run_id_2, results)

    def test_reconcile_all_detects_sdk_only_orphans(self) -> None:
        """Critical #3 (v1.0.2): reconcile_all で sdk_only も検出される。"""
        run_id = "20260512T000000-recAll"
        sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1"
        orphan_sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-99"
        _make_state_with_sids(self.work_dir, run_id, {"1": sid})
        client = _FakeSDKClient(
            existing_sids={sid, orphan_sid},
            all_sids=[sid, orphan_sid],
        )
        results = _run(reconcile_all(self.work_dir, sdk_client=client, dry_run=True))
        self.assertIn(orphan_sid, results[run_id].sessions_sdk_only)


class TestGcOrphans(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_orphan_detection_dry_run(self) -> None:
        run_id = "20260512T000000-gc01"
        protected_sid = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1"
        orphan_sid = f"{DEFAULT_SESSION_ID_PREFIX}-20260101T000000-old-step-1"
        external_sid = "external-tool-uuid-abc"
        _make_state_with_sids(self.work_dir, run_id, {"1": protected_sid})

        client = _FakeSDKClient(
            existing_sids={protected_sid, orphan_sid, external_sid},
            all_sids=[protected_sid, orphan_sid, external_sid],
        )
        result = _run(gc_orphans(self.work_dir, sdk_client=client, dry_run=True))
        # orphan のみ候補に挙がる
        self.assertEqual(result.candidates, [orphan_sid])
        self.assertEqual(result.deleted, [])
        self.assertTrue(result.dry_run)

    def test_orphan_actual_delete(self) -> None:
        run_id = "20260512T000000-gc02"
        protected = f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-1"
        orphan = f"{DEFAULT_SESSION_ID_PREFIX}-20260101T000000-old-step-1"
        _make_state_with_sids(self.work_dir, run_id, {"1": protected})
        client = _FakeSDKClient(
            existing_sids={protected, orphan},
            all_sids=[protected, orphan],
        )
        result = _run(gc_orphans(self.work_dir, sdk_client=client, dry_run=False))
        self.assertEqual(result.deleted, [orphan])
        self.assertNotIn(orphan, client.existing)
        # protected は削除されない
        self.assertIn(protected, client.existing)

    def test_no_sdk_client_returns_empty(self) -> None:
        result = _run(gc_orphans(self.work_dir, sdk_client=None, dry_run=True))
        self.assertEqual(result.candidates, [])

    def test_external_prefix_never_targeted(self) -> None:
        """hve- で始まらない sid は候補に上がらない。"""
        run_id = "20260512T000000-gc03"
        _make_state_with_sids(self.work_dir, run_id, {})
        external = "uuid-external-tool"
        client = _FakeSDKClient(existing_sids={external}, all_sids=[external])
        result = _run(gc_orphans(self.work_dir, sdk_client=client, dry_run=False))
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.deleted, [])


if __name__ == "__main__":
    unittest.main()
