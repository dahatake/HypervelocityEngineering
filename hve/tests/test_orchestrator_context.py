"""OrchestratorContext と split_fork.compute_waves のユニットテスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator_context import OrchestratorContext, is_active  # type: ignore[import-not-found]
from split_fork import SubIssueDef, SubIssuesParseError, compute_waves  # type: ignore[import-not-found]


class TestOrchestratorContext(unittest.TestCase):
    def test_defaults(self):
        ctx = OrchestratorContext()
        self.assertTrue(ctx.split_fork_enabled)
        self.assertEqual(ctx.split_fork_depth, 0)
        self.assertEqual(ctx.split_fork_max_depth, 2)
        self.assertGreaterEqual(ctx.max_parallel_subtasks, 1)

    def test_with_increased_depth(self):
        ctx = OrchestratorContext(split_fork_depth=1)
        nxt = ctx.with_increased_depth()
        self.assertEqual(nxt.split_fork_depth, 2)
        # 元 ctx は不変
        self.assertEqual(ctx.split_fork_depth, 1)

    def test_is_active(self):
        self.assertFalse(is_active(None))
        self.assertTrue(is_active(OrchestratorContext()))


def _sub(i: int, deps: list[int] | None = None) -> SubIssueDef:
    return SubIssueDef(index=i, title=f"sub-{i}", depends_on=deps or [])


class TestComputeWaves(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(compute_waves([]), [])

    def test_no_deps_single_wave(self):
        waves = compute_waves([_sub(1), _sub(2), _sub(3)])
        self.assertEqual(len(waves), 1)
        self.assertEqual([s.index for s in waves[0]], [1, 2, 3])

    def test_linear_chain(self):
        waves = compute_waves([_sub(1), _sub(2, [1]), _sub(3, [2])])
        self.assertEqual([[s.index for s in w] for w in waves], [[1], [2], [3]])

    def test_diamond(self):
        # 1 → 2,3 → 4
        subs = [_sub(1), _sub(2, [1]), _sub(3, [1]), _sub(4, [2, 3])]
        waves = compute_waves(subs)
        self.assertEqual([[s.index for s in w] for w in waves], [[1], [2, 3], [4]])

    def test_self_reference_rejected(self):
        with self.assertRaises(SubIssuesParseError):
            compute_waves([_sub(1, [1])])

    def test_unknown_index_rejected(self):
        with self.assertRaises(SubIssuesParseError):
            compute_waves([_sub(1, [99])])

    def test_cycle_rejected(self):
        with self.assertRaises(SubIssuesParseError):
            compute_waves([_sub(1, [2]), _sub(2, [1])])


if __name__ == "__main__":
    unittest.main()
