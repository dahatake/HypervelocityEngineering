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

# Fork-integration (M12): ホットパスでの動的 import を避けるため、モジュールトップで一度だけ解決する
try:
    from .run_state import make_session_id as _make_session_id  # type: ignore
    from .run_state import DEFAULT_SESSION_ID_PREFIX as _DEFAULT_SESSION_ID_PREFIX  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from run_state import make_session_id as _make_session_id  # type: ignore[no-redef]
        from run_state import DEFAULT_SESSION_ID_PREFIX as _DEFAULT_SESSION_ID_PREFIX  # type: ignore[no-redef]
    except ImportError:
        _make_session_id = None  # type: ignore[assignment]
        _DEFAULT_SESSION_ID_PREFIX = "hve"  # type: ignore[assignment]


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
        retry_count: int = 0,
        tokens: int = 0,
        forked_session_id: Optional[str] = None,
    ) -> None:
        self.step_id = step_id
        self.success = success
        self.elapsed = elapsed
        self.skipped = skipped
        self.error = error  # 失敗時の例外メッセージ（デバッグ用）
        self.state = state or ("skipped" if skipped else "success" if success else "failed")
        self.reason = reason
        # Fork-integration (T2.3): KPI フィールド（既定値で既存呼び出し互換を維持）
        self.retry_count = retry_count if isinstance(retry_count, int) and retry_count >= 0 else 0
        self.tokens = tokens if isinstance(tokens, int) and tokens >= 0 else 0
        self.forked_session_id = forked_session_id

    def __repr__(self) -> str:
        return (
            f"StepResult(step_id={self.step_id!r}, "
            f"success={self.success}, skipped={self.skipped}, state={self.state!r}, "
            f"elapsed={self.elapsed:.1f}s, retry_count={self.retry_count})"
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
        on_step_complete: Optional[Callable[[StepResult], None]] = None,
        repo_root: Optional[Any] = None,
        enable_fanout: bool = True,
        fork_on_retry: bool = False,
        fork_kpi_logger: Any = None,
        on_fork_retry: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self.workflow = workflow
        self.dag_plan = dag_plan
        self.run_step_fn = run_step_fn

        # ADR-0002: Fan-out 展開（既定で有効。リポジトリルートから動的解決パーサを呼ぶ）
        self._fanout_map: Dict[str, List[str]] = {}
        self._fanout_empty_ids: List[str] = []
        self._fanout_child_to_parent: Dict[str, str] = {}
        self._fanout_parent_remaining: Dict[str, Set[str]] = {}
        self._fanout_parent_failed: Set[str] = set()
        if enable_fanout and dag_plan is None:
            # dag_plan を併用する経路では事前展開で plan が壊れるため fan-out をスキップ
            try:
                from pathlib import Path as _Path
                from .fanout_expander import expand_workflow_fanout  # type: ignore[import]
            except ImportError:  # pragma: no cover
                try:
                    from fanout_expander import expand_workflow_fanout  # type: ignore[no-redef]
                except ImportError:
                    expand_workflow_fanout = None  # type: ignore[assignment]
            if expand_workflow_fanout is not None:
                _root = repo_root if repo_root is not None else _Path.cwd()
                expanded = expand_workflow_fanout(workflow, _root)
                self._fanout_map = dict(expanded.fanout_map)
                self._fanout_empty_ids = list(expanded.empty_fanout_ids)
                # 元 workflow.steps を差し替えるのではなく、ローカルに保持
                self._expanded_steps = expanded.steps
                # active_step_ids も展開: ベース ID が active なら全子もを active に
                _active = set(getattr(dag_plan, "active_step_ids", active_step_ids))
                for base_id, child_ids in self._fanout_map.items():
                    if base_id in _active and child_ids:
                        _active.update(child_ids)
                active_step_ids = _active
                # 親 → 残り子の管理
                for base_id, child_ids in self._fanout_map.items():
                    if child_ids:
                        self._fanout_parent_remaining[base_id] = set(child_ids)
                        for cid in child_ids:
                            self._fanout_child_to_parent[cid] = base_id
                if expanded.max_parallel:
                    max_parallel = expanded.max_parallel
            else:
                self._expanded_steps = list(getattr(workflow, "steps", []))
        else:
            self._expanded_steps = list(getattr(workflow, "steps", []))

        self.active_step_ids = set(getattr(dag_plan, "active_step_ids", active_step_ids))
        plan_max_parallel = getattr(dag_plan, "max_parallel", max_parallel)
        self._semaphore = asyncio.Semaphore(max(1, plan_max_parallel))
        self.console = console
        self._step_prompts: Dict[str, str] = self._freeze_prompts(step_prompts, dag_plan)
        self._workflow_step_index: Dict[str, Any] = {
            getattr(step, "id", ""): step for step in self._expanded_steps
        }

        # Phase 3 (Resume): ステップ完了/skip/blocked 通知の同期コールバック。
        # state.json への永続化など、実行中継ぎ込みたい副作用をフックする。
        # コールバック内の例外は実行を止めないよう warn ログのみで握り潰す。
        self._on_step_complete = on_step_complete

        # Fork-integration (T2.5/T2.6): フォーク機構
        self._fork_on_retry: bool = bool(fork_on_retry)
        self._fork_kpi_logger = fork_kpi_logger
        self._on_fork_retry = on_fork_retry

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

    def _emit_step_complete(self, result: StepResult) -> None:
        """`on_step_complete` フックを安全に呼ぶ。

        Phase 3 (Resume): state.json 更新などの副作用を発火するための同期フック。
        コールバック内の例外で DAG 実行が止まらないよう、warn を出して握り潰す。
        """
        if self._on_step_complete is None:
            return
        try:
            self._on_step_complete(result)
        except Exception as exc:  # pragma: no cover - 例外パスは E2E で確認
            if self.console is not None:
                self.console.warning(
                    f"on_step_complete フックの実行に失敗しました (step={result.step_id}): {exc}"
                )

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
        # ADR-0002 K-1: fan-out が 0 件で展開されたベース ID を自動 skip
        for empty_id in self._fanout_empty_ids:
            if empty_id in self.skipped or empty_id in self.completed:
                continue
            self.skipped.add(empty_id)
            _result = StepResult(
                empty_id, success=True, elapsed=0.0,
                skipped=True, state="skipped", reason="fanout-empty",
            )
            self._results[empty_id] = _result
            self._emit_step_complete(_result)
            if self.console is not None:
                try:
                    self.console.warning(
                        f"  ⏭️  [Step.{empty_id}] fan-out 展開キー 0 件のため skip (reason=fanout-empty)"
                    )
                except Exception:
                    pass

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
                    _skip_result = StepResult(
                        s.id,
                        success=False,
                        elapsed=0.0,
                        skipped=True,
                        state="skipped",
                        reason="inactive",
                    )
                    self._results[s.id] = _skip_result
                    # Phase 3 (Resume): skip も state.json に反映する
                    self._emit_step_complete(_skip_result)
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
        """Semaphore で並列数を制御しつつ 1 ステップを実行する。

        Fork-integration (T2.5): `fork_on_retry=True` かつ初回失敗時、`on_fork_retry`
        フックで runner にフォーク回数を通知してから `run_step_fn` を 1 回だけ再実行する。
        """
        async with self._semaphore:
            start = time.time()
            error_msg: Optional[str] = None
            # ADR-0002: fan-out 子ステップは追加メタ (fanout_key / base_step_id /
            # additional_prompt_template_path / per_key_mcp_servers) を渡す
            fanout_meta: Optional[Dict[str, Any]] = None
            if getattr(step, "fanout_key", "") and getattr(step, "base_step_id", ""):
                fanout_meta = {
                    "fanout_key": step.fanout_key,
                    "base_step_id": step.base_step_id,
                    "additional_prompt_template_path": getattr(step, "additional_prompt_template_path", None),
                    "per_key_mcp_servers": getattr(step, "per_key_mcp_servers", None),
                }
            _kwargs: Dict[str, Any] = dict(
                step_id=step.id,
                title=step.title,
                prompt=self._step_prompts.get(step.id, ""),
                custom_agent=step.custom_agent,
            )
            if fanout_meta is not None:
                _kwargs["fanout_meta"] = fanout_meta

            # 初回試行
            try:
                success = await self.run_step_fn(**_kwargs)
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

            # Fork-integration (T2.5): フラグ ON かつ初回失敗時に 1 回だけリトライ
            retry_count = 0
            forked_session_id: Optional[str] = None
            if (
                not success
                and self._fork_on_retry
                and not getattr(step, "is_container", False)
            ):
                retry_count = 1
                # runner にフォーク回数を通知（次の _make_step_session_id で `-fork1` suffix が付与される）
                fork_hook_failed = False
                if self._on_fork_retry is not None:
                    try:
                        self._on_fork_retry(step.id, retry_count)
                    except Exception as hook_exc:
                        fork_hook_failed = True
                        if self.console is not None:
                            self.console.warning(
                                f"on_fork_retry フック失敗 (step={step.id}): {hook_exc}。"
                                "リトライをスキップして初回失敗を最終結果とします（C19 対応）。"
                            )
                if fork_hook_failed:
                    # C19: フック失敗時は session_id が初回と同一になるためリトライをスキップ
                    retry_count = 0
                else:
                    if self.console is not None:
                        self.console.event(
                            f"  🔁 [Step.{step.id}] フォークリトライを実行します (fork_index=1)"
                        )
                    # C3: 同時並列発火を緩和するため軽微なジッターを入れる（最大 0.5 秒）
                    try:
                        import random as _random
                        await asyncio.sleep(_random.uniform(0.0, 0.5))
                    except Exception:
                        pass
                    error_msg = None
                    try:
                        success = await self.run_step_fn(**_kwargs)
                    except Exception as exc:
                        success = False
                        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                        if self.console is not None:
                            self.console.error(
                                f"Step.{step.id} フォークリトライで例外が発生しました: {exc}"
                            )
                    # フォーク session_id を推測（runner._make_fork_session_id と等価フォーマット）
                    forked_session_id = self._guess_forked_session_id(step.id, retry_count)
                    # C1: リトライ完了後は必ず fork_index をリセットし、後続の QA/Review 等の
                    # サブセッション ID に fork suffix が漏れないようにする
                    if self._on_fork_retry is not None:
                        try:
                            self._on_fork_retry(step.id, 0)
                        except Exception as reset_exc:  # pragma: no cover
                            if self.console is not None:
                                self.console.warning(
                                    f"on_fork_retry リセット失敗 (step={step.id}): {reset_exc}"
                                )

            elapsed = time.time() - start

            self.running.discard(step.id)
            if success:
                self.completed.add(step.id)
            else:
                self.failed.add(step.id)

            result = StepResult(
                step.id, success, elapsed,
                error=error_msg,
                retry_count=retry_count,
                forked_session_id=forked_session_id,
            )
            # Fork-integration (T2.4): KPI ロガーへ追記（enabled=False なら no-op）
            if self._fork_kpi_logger is not None:
                try:
                    self._fork_kpi_logger.log_step(
                        step_id=step.id,
                        session_id=self._guess_main_session_id(step.id),
                        forked_session_id=forked_session_id,
                        success=success,
                        retry_count=retry_count,
                        elapsed_seconds=elapsed,
                        tokens=0,  # SDK からトークン取得は将来拡張
                        fork_on_retry_enabled=self._fork_on_retry,
                    )
                except Exception as log_exc:  # pragma: no cover - ロガー例外は実行を止めない
                    if self.console is not None:
                        self.console.warning(
                            f"fork_kpi_logger 失敗 (step={step.id}): {log_exc}"
                        )
            # Phase 3 (Resume): completed / failed をフックで通知し state.json を更新する
            self._emit_step_complete(result)
            return result

    def _guess_main_session_id(self, step_id: str) -> Optional[str]:
        """KPI ログ用にメイン session_id を推測する。

        Fork-integration (T2.4): runner.py の `_make_step_session_id` と等価フォーマット
        を再現する。run_id / prefix が取得できない場合は None を返す。
        """
        return self._build_session_id_token(step_id, suffix="")

    def _guess_forked_session_id(self, step_id: str, fork_index: int) -> Optional[str]:
        """KPI ログ用に fork session_id を推測する。"""
        if fork_index < 1:
            return None
        return self._build_session_id_token(step_id, suffix=f"fork{fork_index}")

    def _build_session_id_token(self, step_id: str, suffix: str) -> Optional[str]:
        """runner._make_step_session_id と等価フォーマットを再現する内部ヘルパー。"""
        runner = getattr(self.run_step_fn, "__self__", None)
        if runner is None:
            return None
        config = getattr(runner, "config", None)
        if config is None:
            return None
        run_id = getattr(config, "run_id", "")
        if not run_id:
            return None
        if _make_session_id is None:  # pragma: no cover - import 失敗フォールバック
            return None
        prefix = (getattr(config, "session_id_prefix", "") or "").strip() or DEFAULT_SESSION_ID_PREFIX
        return make_session_id(run_id=run_id, step_id=step_id, suffix=suffix, prefix=prefix)

    def _get_next_steps(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[Any]:
        if self.dag_plan is None:
            # ADR-0002: fan-out 展開済みステップから次に起動可能なものを返す
            return self._get_next_steps_from_expanded(completed_step_ids, skipped_step_ids)

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
            _blocked_result = StepResult(
                step_id,
                success=False,
                elapsed=0.0,
                skipped=False,
                state="blocked",
                reason=reason,
            )
            self._results[step_id] = _blocked_result
            # Phase 3 (Resume): blocked も state.json に反映する
            self._emit_step_complete(_blocked_result)

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

    # ------------------------------------------------------------------
    # ADR-0002: fan-out 展開済みステップに対する _get_next_steps 実装
    # ------------------------------------------------------------------
    def _get_next_steps_from_expanded(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[Any]:
        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing_ids = set(self._workflow_step_index.keys())

        result: List[Any] = []
        for step in self._expanded_steps:
            if getattr(step, "is_container", False):
                continue
            sid = step.id
            if sid in completed or sid in skipped or sid in self.failed or sid in self.blocked:
                continue
            deps = list(getattr(step, "depends_on", []) or [])
            if not deps:
                result.append(step)
                continue
            deps_satisfied = all(
                dep in effective_done or dep not in existing_ids
                for dep in deps
            )
            if deps_satisfied:
                result.append(step)
        return result

    @staticmethod
    def _freeze_prompts(step_prompts: Optional[Dict[str, str]], dag_plan: Any = None) -> Dict[str, str]:
        prompts: Dict[str, str] = {}
        if dag_plan is not None:
            for prompt in getattr(dag_plan, "step_prompts", ()):
                prompts[prompt.step_id] = prompt.prompt
        if step_prompts:
            prompts.update(step_prompts)
        return prompts
