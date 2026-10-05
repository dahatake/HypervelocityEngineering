"""hve/runner.py の実行モード制約と成果物ゲート（T4 + T5）の単体テスト。

T4: `_build_execution_mode_constraint_suffix` — prompt 末尾に注入する制約文
T5: `_check_output_paths_gate` — output_paths の欠落で Step を fail 化
    (FR-WF-OUT-01: 宣言 path が 1 件でも欠落したら fail)
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator_context import OrchestratorContext  # type: ignore[import-not-found]
from runner import (  # type: ignore[import-not-found]
    _build_execution_mode_constraint_suffix,
    _check_output_paths_gate,
)


@dataclass
class _FakeStep:
    id: str
    output_paths: List[str] = field(default_factory=list)


@dataclass
class _FakeWorkflow:
    steps: List[_FakeStep]


def _wf(*step_pairs: tuple) -> _FakeWorkflow:
    return _FakeWorkflow(steps=[_FakeStep(id=sid, output_paths=list(paths)) for sid, paths in step_pairs])


class TestBuildExecutionModeConstraintSuffix(unittest.TestCase):
    """T4: prompt 末尾注入の条件分岐。"""

    def test_returns_empty_when_ctx_is_none(self) -> None:
        # 単独実行モード（Agent 直接起動）では何も注入しない
        self.assertEqual(_build_execution_mode_constraint_suffix(None), "")

    def test_injects_constraint_for_cli_gui_default(self) -> None:
        # CLI/GUI Orchestrator 配下では注入する
        ctx = OrchestratorContext()
        suffix = _build_execution_mode_constraint_suffix(ctx)
        self.assertIn("## 実行モード制約", suffix)
        self.assertIn("output_paths", suffix)
        self.assertNotIn("SPLIT_REQUIRED", suffix)
        self.assertNotIn("**", suffix, "強調表現を使わず理由付きの 1 文で伝える")
        self.assertTrue(suffix.startswith("\n\n"), "prompt 末尾追加用に先頭は改行で始まる")


class TestSplitForkPathRemoved(unittest.TestCase):
    """FR-PLAN-01: CLI / GUI は subissues.md を実行時に fork しない。"""

    def test_orchestrator_context_has_no_split_fork_fields(self) -> None:
        fields = set(OrchestratorContext.__dataclass_fields__)
        self.assertFalse(
            {"split_fork_enabled", "split_fork_depth", "split_fork_max_depth"} & fields
        )

    def test_split_fork_module_is_removed(self) -> None:
        import importlib.util

        self.assertIsNone(importlib.util.find_spec("hve.split_fork"))

    def test_runner_has_no_split_fork_phase(self) -> None:
        import runner  # type: ignore[import-not-found]

        self.assertFalse(hasattr(runner.StepRunner, "_maybe_run_split_fork"))

    def test_split_fork_prompts_are_removed(self) -> None:
        # FR-PROMPT-SRC-01 従属項目: production caller を失った Prompt を保持しない。
        fleet_dir = Path(__file__).resolve().parents[2] / ".github" / "prompts" / "runtime" / "fleet"
        for name in ("subtask.prompt.md", "split-fleet.prompt.md", "split-fleet-todo.prompt.md"):
            self.assertFalse((fleet_dir / name).exists(), name)
        for name in ("dag-wave.prompt.md", "dag-wave-task.prompt.md"):
            self.assertTrue((fleet_dir / name).is_file(), name)


class TestCheckOutputPathsGate(unittest.TestCase):
    """T5: output_paths 欠落の検出（FR-WF-OUT-01: 1 件でも欠落したら fail）。"""

    def setUp(self) -> None:
        self._tmp = Path(__file__).resolve().parent / "_tmp_output_gate"
        self._tmp.mkdir(parents=True, exist_ok=True)
        # 既存ファイル掃除
        for p in self._tmp.rglob("*"):
            if p.is_file():
                p.unlink()

    def tearDown(self) -> None:
        for p in sorted(self._tmp.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        if self._tmp.exists():
            self._tmp.rmdir()

    def test_pass_when_ctx_is_none(self) -> None:
        # 単独実行モードは従来通り pass（本ゲートを通さない）
        wf = _wf(("1", ["docs/catalog/app-catalog.md"]))
        self.assertEqual(_check_output_paths_gate(None, wf, "1", self._tmp), [])

    def test_pass_when_no_output_paths_declared(self) -> None:
        # output_paths が空の Step は従来通り pass
        ctx = OrchestratorContext()
        wf = _wf(("1", []))
        self.assertEqual(_check_output_paths_gate(ctx, wf, "1", self._tmp), [])

    def test_fail_when_all_outputs_missing(self) -> None:
        # CLI/GUI 配下 + 宣言あり + 全欠落 → fail（missing list を返す）
        ctx = OrchestratorContext()
        wf = _wf(("1", ["docs/a.md", "docs/b.md"]))
        result = _check_output_paths_gate(ctx, wf, "1", self._tmp)
        self.assertEqual(result, ["docs/a.md", "docs/b.md"])

    def test_fail_when_one_declared_output_is_missing(self) -> None:
        # FR-WF-OUT-01: 1 つ存在しても、残りが欠落していれば fail（欠落 path のみを返す）
        ctx = OrchestratorContext()
        (self._tmp / "docs").mkdir(exist_ok=True)
        (self._tmp / "docs" / "a.md").write_text("# present\n", encoding="utf-8")
        wf = _wf(("1", ["docs/a.md", "docs/b.md"]))
        self.assertEqual(
            _check_output_paths_gate(ctx, wf, "1", self._tmp),
            ["docs/b.md"],
        )

    def test_fail_reports_only_missing_paths(self) -> None:
        # 報告対象は欠落 path のみ。存在する宣言 path を羅列してはならない。
        ctx = OrchestratorContext()
        (self._tmp / "docs").mkdir(exist_ok=True)
        (self._tmp / "docs" / "a.md").write_text("# present\n", encoding="utf-8")
        wf = _wf(("1", ["docs/a.md", "docs/b.md", "docs/c.md"]))
        self.assertEqual(
            _check_output_paths_gate(ctx, wf, "1", self._tmp),
            ["docs/b.md", "docs/c.md"],
        )

    def test_pass_when_all_declared_outputs_exist(self) -> None:
        # 宣言した path が全て存在する場合のみ pass
        ctx = OrchestratorContext()
        (self._tmp / "docs").mkdir(exist_ok=True)
        (self._tmp / "docs" / "a.md").write_text("# present\n", encoding="utf-8")
        (self._tmp / "docs" / "b.md").write_text("# present\n", encoding="utf-8")
        wf = _wf(("1", ["docs/a.md", "docs/b.md"]))
        self.assertEqual(_check_output_paths_gate(ctx, wf, "1", self._tmp), [])

    def test_pass_when_unknown_step_id(self) -> None:
        # 不明な step_id は output_paths 取得不可 → 空リスト → pass
        ctx = OrchestratorContext()
        wf = _wf(("1", ["docs/a.md"]))
        self.assertEqual(_check_output_paths_gate(ctx, wf, "9", self._tmp), [])

    def test_pass_when_workflow_is_none(self) -> None:
        # workflow_id が解決できず workflow=None の場合も AttributeError を投げず pass。
        # run_step() 内で `workflow_registry.get_workflow(workflow_id)` が None を返した
        # ケースを想定（旧 `self.workflow` AttributeError 回帰防止）。
        ctx = OrchestratorContext()
        self.assertEqual(_check_output_paths_gate(ctx, None, "1", self._tmp), [])


if __name__ == "__main__":
    unittest.main()
