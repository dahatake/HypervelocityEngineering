"""test_fork_session_id.py — Fork-integration T4.1.

`runner.StepRunner._make_fork_session_id` および `set_fork_index` /
`_make_step_session_id` のフォーク対応を検証する。

DoD (T4.1):
- `_make_fork_session_id(step_id, fork_index, suffix)` が決定論的に session_id を返す
- 同 step_id × 異なる fork_index で別 session_id が返る
- メインセッション ID とフォーク ID が衝突しない
- `set_fork_index()` 後に `_make_step_session_id()` が自動で `-fork{N}` suffix を付与する
- `fork_index=0` でリセットすると元のメイン session_id に戻る
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_runner(run_id: str = "20260512T031415-abc123"):
    """テスト用の最小 StepRunner を作る（重い依存を回避するため import 後にスタブ）。"""
    from config import SDKConfig  # type: ignore[import-not-found]
    import runner as runner_module  # type: ignore[import-not-found]

    config = SDKConfig(run_id=run_id, github_token="x", repo="o/r")
    # `StepRunner.__init__` は console を要求するが MagicMock で十分
    return runner_module.StepRunner(config=config, console=MagicMock())


class TestMakeForkSessionId(unittest.TestCase):
    """`_make_fork_session_id` の基本挙動。"""

    def test_returns_distinct_session_id_for_fork(self) -> None:
        runner = _make_runner()
        main_id = runner._make_step_session_id("2.3")
        fork_id = runner._make_fork_session_id("2.3", fork_index=1)
        self.assertNotEqual(main_id, fork_id)
        self.assertIn("fork1", fork_id)
        self.assertIn("step-2.3", fork_id)

    def test_determinism(self) -> None:
        runner = _make_runner(run_id="run-X")
        a = runner._make_fork_session_id("1.1", fork_index=1)
        b = runner._make_fork_session_id("1.1", fork_index=1)
        self.assertEqual(a, b)

    def test_different_fork_indices_yield_different_ids(self) -> None:
        runner = _make_runner()
        sid1 = runner._make_fork_session_id("1.1", fork_index=1)
        sid2 = runner._make_fork_session_id("1.1", fork_index=2)
        self.assertNotEqual(sid1, sid2)

    def test_zero_or_negative_fork_index_raises(self) -> None:
        runner = _make_runner()
        with self.assertRaises(ValueError):
            runner._make_fork_session_id("1.1", fork_index=0)
        with self.assertRaises(ValueError):
            runner._make_fork_session_id("1.1", fork_index=-1)

    def test_suffix_combined_with_fork(self) -> None:
        runner = _make_runner()
        sid = runner._make_fork_session_id("1.1", fork_index=1, suffix="qa")
        # suffix と fork が両方含まれる
        self.assertIn("qa", sid)
        self.assertIn("fork1", sid)


class TestSetForkIndexAndMainSessionId(unittest.TestCase):
    """`set_fork_index` → `_make_step_session_id` の連携。"""

    def test_set_fork_index_adds_fork_suffix(self) -> None:
        runner = _make_runner()
        main_id = runner._make_step_session_id("3.0T")
        runner.set_fork_index("3.0T", 1)
        forked_id = runner._make_step_session_id("3.0T")
        self.assertNotEqual(main_id, forked_id)
        self.assertIn("fork1", forked_id)

    def test_reset_returns_main_session_id(self) -> None:
        runner = _make_runner()
        main_id = runner._make_step_session_id("3.0T")
        runner.set_fork_index("3.0T", 1)
        self.assertNotEqual(main_id, runner._make_step_session_id("3.0T"))
        runner.set_fork_index("3.0T", 0)
        self.assertEqual(main_id, runner._make_step_session_id("3.0T"))

    def test_fork_index_does_not_leak_across_step_ids(self) -> None:
        runner = _make_runner()
        runner.set_fork_index("A", 1)
        # B には fork suffix が付かない
        self.assertNotIn("fork1", runner._make_step_session_id("B"))
        # A には付く
        self.assertIn("fork1", runner._make_step_session_id("A"))

    def test_negative_fork_index_raises(self) -> None:
        runner = _make_runner()
        with self.assertRaises(ValueError):
            runner.set_fork_index("X", -1)


if __name__ == "__main__":
    unittest.main()
