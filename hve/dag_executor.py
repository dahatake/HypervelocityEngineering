"""dag_executor.py — DAG 走査 + asyncio.Semaphore 並列実行エンジン

workflow_registry.py の WorkflowDef.get_next_steps() を使用して DAG を走査し、
依存関係が解決されたステップを asyncio.Semaphore で並列実行する。

依存パターン (workflow_registry.py 定義):
  - 順次 (sequential): A → B
  - 並列 fork: A → B‖C
  - AND join: A AND B → C
  - スキップフォールバック: skip_fallback_deps
"""

from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Callable, Coroutine, Dict, Optional, Set


class StepResult:
    """ステップ実行結果。"""

    def __init__(
        self,
        step_id: str,
        success: bool,
        elapsed: float = 0.0,
        skipped: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.step_id = step_id
        self.success = success
        self.elapsed = elapsed
        self.skipped = skipped
        self.error = error  # 失敗時の例外メッセージ（デバッグ用）

    def __repr__(self) -> str:
        return (
            f"StepResult(step_id={self.step_id!r}, "
            f"success={self.success}, skipped={self.skipped}, elapsed={self.elapsed:.1f}s)"
        )


class DAGExecutor:
    """DAG ベースの並列実行エンジン。

    使い方:
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=runner.run_step,
            active_step_ids=active_ids,
            max_parallel=15,
            console=console,
        )
        results = await executor.execute()

    設計:
        1. workflow.get_next_steps() で起動可能なステップを取得
        2. 起動可能かつ active_step_ids に含まれるステップのみ実行
        3. asyncio.Semaphore(max_parallel) で並列数を制御
        4. 完了したステップは completed に追加
        5. スキップされたステップは skipped に追加
        6. 失敗したステップは failed に追加（後続ステップは起動しない）
        7. 全ステップ完了（or 起動可能なステップがなくなる）まで繰り返し
    """

    def __init__(
        self,
        workflow: Any,  # WorkflowDef
        run_step_fn: Callable[..., Coroutine],
        active_step_ids: Set[str],
        max_parallel: int = 15,
        console: Any = None,
    ) -> None:
        self.workflow = workflow
        self.run_step_fn = run_step_fn
        self.active_step_ids = active_step_ids
        self._semaphore = asyncio.Semaphore(max(1, max_parallel))
        self.console = console

        # 実行状態
        self.completed: Set[str] = set()
        self.skipped: Set[str] = set()
        self.failed: Set[str] = set()
        self.running: Set[str] = set()

        # 結果マップ (step_id → StepResult)
        self._results: Dict[str, StepResult] = {}

    async def execute(self) -> Dict[str, StepResult]:
        """DAG を走査し、全ステップを実行する。

        Returns:
            step_id → StepResult のマップ。
        """
        pending_tasks: Set[asyncio.Task] = set()

        while True:
            next_steps = self.workflow.get_next_steps(
                completed_step_ids=list(self.completed),
                skipped_step_ids=list(self.skipped),
            )

            # active でないステップを自動スキップ
            newly_skipped = False
            for s in next_steps:
                if (
                    s.id not in self.active_step_ids
                    and s.id not in self.skipped
                    and s.id not in self.completed
                    and s.id not in self.failed
                    and s.id not in self.running
                ):
                    self.skipped.add(s.id)
                    self._results[s.id] = StepResult(s.id, success=False, elapsed=0.0, skipped=True)
                    newly_skipped = True

            # 失敗ステップの後続を除外し、起動可能なステップを絞り込む
            executable = [
                s
                for s in next_steps
                if s.id in self.active_step_ids
                and s.id not in self.running
                and s.id not in self.completed
                and s.id not in self.failed
                and s.id not in self.skipped
            ]

            if executable:
                if self.console is not None:
                    self.console.dag_batch(executable)

                for step in executable:
                    self.running.add(step.id)
                    task = asyncio.create_task(
                        self._run_with_semaphore(step),
                        name=f"step-{step.id}",
                    )
                    pending_tasks.add(task)

            if not pending_tasks and not executable:
                # 実行中タスクも起動可能ステップもない
                if newly_skipped:
                    # 今回のイテレーションで新たにスキップが発生した場合は
                    # 後続ステップが解放される可能性があるため再ループする
                    continue
                # 本当に完了（or デッドロック）
                break

            if not pending_tasks:
                # executable のタスクをまだ作成したばかり（pending_tasks に追加済み）
                # → 次のイテレーションで wait する
                continue

            # 完了したタスクを1つ以上待つ（FIRST_COMPLETED パターン）
            done, pending_tasks = await asyncio.wait(
                pending_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                result: StepResult = task.result()
                self._results[result.step_id] = result

        return self._results

    async def _run_with_semaphore(self, step: Any) -> StepResult:
        """Semaphore で並列数を制御しつつ 1 ステップを実行する。"""
        async with self._semaphore:
            start = time.time()
            error_msg: Optional[str] = None
            try:
                success: bool = await self.run_step_fn(
                    step_id=step.id,
                    title=step.title,
                    prompt=getattr(step, "_prompt", ""),
                    custom_agent=step.custom_agent,
                )
            except Exception as exc:
                success = False
                error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                if self.console is not None:
                    self.console.error(
                        f"Step.{step.id} で予期しない例外が発生しました: {exc}"
                    )
                else:
                    import sys as _sys
                    print(
                        f"❌ ERROR: Step.{step.id} 例外: {error_msg}",
                        file=_sys.stderr,
                        flush=True,
                    )
            elapsed = time.time() - start

            self.running.discard(step.id)
            if success:
                self.completed.add(step.id)
            else:
                self.failed.add(step.id)

            return StepResult(step.id, success, elapsed, error=error_msg)
