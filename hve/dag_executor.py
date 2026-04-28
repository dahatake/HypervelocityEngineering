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
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set


class StepResult:
    """ステップ実行結果。"""

    def __init__(
        self,
        step_id: str,
        success: bool,
        elapsed: float = 0.0,
        skipped: bool = False,
        error: Optional[str] = None,
        state: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.step_id = step_id
        self.success = success
        self.elapsed = elapsed
        self.skipped = skipped
        self.error = error  # 失敗時の例外メッセージ（デバッグ用）
        self.state = state or ("skipped" if skipped else "success" if success else "failed")
        self.reason = reason

    def __repr__(self) -> str:
        return (
            f"StepResult(step_id={self.step_id!r}, "
            f"success={self.success}, skipped={self.skipped}, state={self.state!r}, elapsed={self.elapsed:.1f}s)"
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
        step_prompts: Optional[Dict[str, str]] = None,
        dag_plan: Any = None,
    ) -> None:
        self.workflow = workflow
        self.dag_plan = dag_plan
        self.run_step_fn = run_step_fn
        self.active_step_ids = set(getattr(dag_plan, "active_step_ids", active_step_ids))
        plan_max_parallel = getattr(dag_plan, "max_parallel", max_parallel)
        self._semaphore = asyncio.Semaphore(max(1, plan_max_parallel))
        self.console = console
        self._step_prompts: Dict[str, str] = self._freeze_prompts(step_prompts, dag_plan)
        self._workflow_step_index: Dict[str, Any] = {
            getattr(step, "id", ""): step for step in getattr(workflow, "steps", [])
        }

        # 実行状態
        self.completed: Set[str] = set()
        self.skipped: Set[str] = set()
        self.failed: Set[str] = set()
        self.blocked: Set[str] = set()
        self.running: Set[str] = set()

        # 結果マップ (step_id → StepResult)
        self._results: Dict[str, StepResult] = {}

        # Wave / 進捗管理
        self._wave_counter: int = 0
        self._total_waves: int = 0

    def compute_waves(self) -> List[List[Any]]:
        """DAG を事前走査して Wave 分割を計算する。

        Returns:
            [[step, ...], [step, ...], ...] — 各内部リストが 1 Wave
        """
        if self.dag_plan is not None:
            return [
                [self._step_for_id(step_id) for step_id in wave.step_ids]
                for wave in getattr(self.dag_plan, "waves", ())
            ]

        completed: Set[str] = set()
        skipped: Set[str] = set()
        waves: List[List[Any]] = []

        while True:
            next_steps = self._get_next_steps(
                completed_step_ids=list(completed),
                skipped_step_ids=list(skipped),
            )

            # active でないステップを自動スキップ
            newly_skipped = False
            for s in next_steps:
                if (
                    s.id not in self.active_step_ids
                    and s.id not in skipped
                    and s.id not in completed
                ):
                    skipped.add(s.id)
                    newly_skipped = True

            executable = [
                s for s in next_steps
                if s.id in self.active_step_ids
                and s.id not in completed
                and s.id not in skipped
            ]

            if not executable:
                if newly_skipped:
                    # スキップにより後続ステップが解放される可能性がある
                    continue
                remaining = [
                    s for s in next_steps
                    if s.id not in completed and s.id not in skipped
                ]
                if not remaining:
                    break
                break

            waves.append(executable)
            for s in executable:
                completed.add(s.id)

        return waves

    async def execute(self) -> Dict[str, StepResult]:
        """DAG を走査し、全ステップを実行する。

        Returns:
            step_id → StepResult のマップ。
        """
        # Wave 事前計算
        waves = self.compute_waves()
        self._total_waves = len(waves)
        self._wave_counter = 0

        pending_tasks: Set[asyncio.Task] = set()
        HEARTBEAT_INTERVAL = 15  # 秒 — ローカル実行ではより頻繁なチェックで応答性を向上

        while True:
            next_steps = self._get_next_steps(
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
                    and s.id not in self.blocked
                    and s.id not in self.running
                ):
                    self.skipped.add(s.id)
                    self._results[s.id] = StepResult(
                        s.id,
                        success=False,
                        elapsed=0.0,
                        skipped=True,
                        state="skipped",
                        reason="inactive",
                    )
                    newly_skipped = True

            # 失敗ステップの後続を除外し、起動可能なステップを絞り込む
            executable = [
                s
                for s in next_steps
                if s.id in self.active_step_ids
                and s.id not in self.running
                and s.id not in self.completed
                and s.id not in self.failed
                and s.id not in self.blocked
                and s.id not in self.skipped
            ]

            if executable:
                self._wave_counter += 1
                if self.console is not None:
                    self.console.dag_wave_start(
                        self._wave_counter, self._total_waves, executable,
                    )

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
                self._mark_unresolved_active_steps()
                break

            if not pending_tasks:
                # executable のタスクをまだ作成したばかり（pending_tasks に追加済み）
                # → 次のイテレーションで wait する
                continue

            # 完了したタスクを1つ以上待つ（FIRST_COMPLETED + ハートビート）
            done, pending_tasks = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=HEARTBEAT_INTERVAL,
            )
            if not done:
                # タイムアウト — 実行中ステップの経過時間を表示
                if self.console is not None:
                    for step_id in list(self.running):
                        self.console.step_elapsed(step_id)
                continue
            for task in done:
                result: StepResult = task.result()
                self._results[result.step_id] = result

            # 進捗更新
            if self.console is not None:
                self.console.dag_progress(
                    len(self.completed), len(self.running),
                    len(self.active_step_ids),
                )

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
                    prompt=self._step_prompts.get(step.id, ""),
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
                        f"[{datetime.now().strftime('%H:%M:%S')}] ❌ ERROR: Step.{step.id} 例外: {error_msg}",
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

    def _get_next_steps(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[Any]:
        if self.dag_plan is None:
            return self.workflow.get_next_steps(completed_step_ids, skipped_step_ids)

        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing_ids = {node.id for node in getattr(self.dag_plan, "nodes", ())}
        result: List[Any] = []
        for node in getattr(self.dag_plan, "nodes", ()):
            if node.is_container:
                continue
            if node.id in completed or node.id in skipped or node.id in self.failed or node.id in self.blocked:
                continue
            if any(dep not in completed for dep in getattr(node, "block_unless", ())):
                continue
            deps_satisfied = all(
                dep in effective_done or dep not in existing_ids
                for dep in getattr(node, "depends_on", ())
            )
            if deps_satisfied:
                result.append(self._step_for_id(node.id))
        return result

    def _mark_unresolved_active_steps(self) -> None:
        if self.dag_plan is None:
            return
        for step_id in sorted(self.active_step_ids):
            if step_id in self.completed or step_id in self.failed or step_id in self.skipped or step_id in self.running:
                continue
            node = self.dag_plan.get_node(step_id)
            if node is None or node.is_container:
                continue
            reason = self._blocked_reason(node)
            self.blocked.add(step_id)
            self._results[step_id] = StepResult(
                step_id,
                success=False,
                elapsed=0.0,
                skipped=False,
                state="blocked",
                reason=reason,
            )

    def _blocked_reason(self, node: Any) -> str:
        if any(dep in self.failed for dep in getattr(node, "depends_on", ())):
            return "blocked_by_failed_dependency"
        if any(dep not in self.completed for dep in getattr(node, "block_unless", ())):
            return "blocked_by_block_unless"
        return "unresolved_dependencies"

    def _step_for_id(self, step_id: str) -> Any:
        step = self._workflow_step_index.get(step_id)
        if step is not None:
            return step
        if self.dag_plan is not None:
            node = self.dag_plan.get_node(step_id)
            if node is not None:
                return node
        raise KeyError(f"unknown DAG step id: {step_id}")

    @staticmethod
    def _freeze_prompts(step_prompts: Optional[Dict[str, str]], dag_plan: Any = None) -> Dict[str, str]:
        prompts: Dict[str, str] = {}
        if dag_plan is not None:
            for prompt in getattr(dag_plan, "step_prompts", ()):
                prompts[prompt.step_id] = prompt.prompt
        if step_prompts:
            prompts.update(step_prompts)
        return prompts
