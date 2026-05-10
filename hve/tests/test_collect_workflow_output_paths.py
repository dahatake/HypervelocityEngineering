"""test_collect_workflow_output_paths.py — collect_workflow_output_paths の単体テスト

orchestrator.collect_workflow_output_paths を直接インポートしてテストする。
実ワークフロー定義（AAS など output_paths あり）と output_paths 未設定の
モックワークフローの両ケースを検証する。
"""

from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator import collect_workflow_output_paths
from workflow_registry import StepDef, WorkflowDef


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------


class TestCollectWorkflowOutputPaths(unittest.TestCase):
    """collect_workflow_output_paths の動作検証。"""

    # --- 実ワークフロー定義（AAS）を使うケース ---

    def test_aas_returns_nonempty_list(self) -> None:
        """AAS ワークフローの output_paths は空でないリストを返す。"""
        result = collect_workflow_output_paths("aas")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0, "AAS の output_paths が空です")

    def test_aas_contains_app_catalog(self) -> None:
        """AAS Step 1 の output_paths は app-catalog.md を含む。"""
        result = collect_workflow_output_paths("aas")
        self.assertIn("docs/catalog/app-catalog.md", result)

    def test_aas_no_duplicates(self) -> None:
        """重複パスが除去されていること。"""
        result = collect_workflow_output_paths("aas")
        self.assertEqual(len(result), len(set(result)), "重複パスが含まれています")

    def test_aas_order_preserved(self) -> None:
        """順序が保持されること（最初の出現順）。"""
        result = collect_workflow_output_paths("aas")
        seen = []
        for p in result:
            self.assertNotIn(p, seen, f"重複パス: {p}")
            seen.append(p)

    # --- 存在しないワークフロー ID ---

    def test_unknown_workflow_returns_empty(self) -> None:
        """存在しない workflow_id は空リストを返す。"""
        result = collect_workflow_output_paths("nonexistent-workflow-id")
        self.assertEqual(result, [])

    # --- output_paths 未設定の Step が混在するモックワークフロー ---

    def test_mixed_output_paths_steps(self) -> None:
        """output_paths あり/なしの Step が混在しても安全に動作する。"""
        mock_wf = WorkflowDef(
            id="mock-wf",
            name="Mock Workflow",
            label_prefix="mock",
            state_labels={},
            params=[],
            steps=[
                StepDef(
                    id="1",
                    title="Step with paths",
                    custom_agent=None,
                    output_paths=["docs/step1-output.md"],
                ),
                StepDef(
                    id="2",
                    title="Step without paths",
                    custom_agent=None,
                    output_paths=[],  # 空リスト
                ),
                StepDef(
                    id="3",
                    title="Step with more paths",
                    custom_agent=None,
                    output_paths=["docs/step3-output.md", "docs/step3-output2.md"],
                ),
            ],
        )
        with patch("orchestrator.get_workflow", return_value=mock_wf):
            result = collect_workflow_output_paths("mock-wf")
        self.assertEqual(
            result,
            ["docs/step1-output.md", "docs/step3-output.md", "docs/step3-output2.md"],
        )

    def test_all_empty_output_paths_returns_empty(self) -> None:
        """全 Step の output_paths が空の場合は空リストを返す。"""
        mock_wf = WorkflowDef(
            id="mock-empty",
            name="Mock Empty",
            label_prefix="mock-empty",
            state_labels={},
            params=[],
            steps=[
                StepDef(id="1", title="Step A", custom_agent=None, output_paths=[]),
                StepDef(id="2", title="Step B", custom_agent=None, output_paths=[]),
            ],
        )
        with patch("orchestrator.get_workflow", return_value=mock_wf):
            result = collect_workflow_output_paths("mock-empty")
        self.assertEqual(result, [])

    def test_duplicate_paths_deduplicated(self) -> None:
        """複数 Step が同一パスを持つ場合は重複除去される。"""
        mock_wf = WorkflowDef(
            id="mock-dup",
            name="Mock Dup",
            label_prefix="mock-dup",
            state_labels={},
            params=[],
            steps=[
                StepDef(
                    id="1",
                    title="Step A",
                    custom_agent=None,
                    output_paths=["docs/shared.md", "docs/a.md"],
                ),
                StepDef(
                    id="2",
                    title="Step B",
                    custom_agent=None,
                    output_paths=["docs/shared.md", "docs/b.md"],
                ),
            ],
        )
        with patch("orchestrator.get_workflow", return_value=mock_wf):
            result = collect_workflow_output_paths("mock-dup")
        # docs/shared.md は1回だけ（最初の出現位置を維持）
        self.assertEqual(
            result,
            ["docs/shared.md", "docs/a.md", "docs/b.md"],
        )

    def test_none_output_paths_handled_safely(self) -> None:
        """output_paths が None（getattr フォールバック）でもクラッシュしない。"""
        # StepDef はデフォルト factory で空リストを生成するが、
        # 後方互換や動的追加で None になる可能性を想定してテスト
        mock_step = StepDef(id="1", title="Step", custom_agent=None)
        # 強制的に None を設定
        object.__setattr__(mock_step, "output_paths", None)
        mock_wf = WorkflowDef(
            id="mock-none",
            name="Mock None",
            label_prefix="mock-none",
            state_labels={},
            params=[],
            steps=[mock_step],
        )
        with patch("orchestrator.get_workflow", return_value=mock_wf):
            # None でもクラッシュしないこと
            result = collect_workflow_output_paths("mock-none")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
