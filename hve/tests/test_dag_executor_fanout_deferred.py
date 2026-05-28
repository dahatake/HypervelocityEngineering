"""T-F1: deferred fan-out のランタイム再展開 E2E テスト。

orchestrator._expand_workflow_for_dag が deferred と判定した fan-out base が、
DAGExecutor の execute() 中に upstream step の出力に応じて動的展開され、
子 step → base 集約完了 → 下流 step の順で正しく実行されることを検証する。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from hve import workflow_registry as wr
from hve.dag_executor import DAGExecutor
from hve.orchestrator import _expand_workflow_for_dag


def _build_deferred_test_workflow() -> wr.WorkflowDef:
    """producer → fanout_base (parser=use_case_skeleton) → consumer の最小 workflow。"""
    producer = wr.StepDef(
        id="P",
        title="producer",
        custom_agent=None,
        consumed_artifacts=[],
        output_paths=["docs/catalog/use-case-skeleton.md"],
    )
    fanout_base = wr.StepDef(
        id="F",
        title="fanout base",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["P"],
        fanout_parser="use_case_skeleton",
    )
    consumer = wr.StepDef(
        id="C",
        title="consumer",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["F"],
    )
    return wr.WorkflowDef(
        id="t_defer",
        name="t_defer",
        label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[],
        steps=[producer, fanout_base, consumer],
    )


def test_deferred_fanout_runtime_expansion_full_flow(tmp_path: Path) -> None:
    """deferred fan-out base が producer 完了後に動的展開され、子→base集約→consumer が動く。"""
    wf = _build_deferred_test_workflow()

    # Step 1: orchestrator が deferred 判定
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        wf, {"P", "F", "C"}, tmp_path
    )
    assert "F" in info.deferred_fanout_ids
    assert "F" in expanded_active

    # Step 2: producer 実行時に skeleton.md を生成する run_step_fn
    skeleton_path = tmp_path / "docs" / "catalog" / "use-case-skeleton.md"
    call_order: List[str] = []
    dynamic_expand_calls: List[tuple] = []

    async def run_fn(**kwargs: Any) -> bool:
        sid = kwargs["step_id"]
        call_order.append(sid)
        if sid == "P":
            skeleton_path.parent.mkdir(parents=True, exist_ok=True)
            skeleton_path.write_text(
                "# Skeleton\n\n## UC-01\n本文\n## UC-02\n本文\n## UC-03\n本文\n",
                encoding="utf-8",
            )
        return True

    def on_expand(base_id: str, child_ids: List[str]) -> None:
        dynamic_expand_calls.append((base_id, list(child_ids)))

    # Step 3: DAGExecutor 起動（dag_plan=None でテスト fallback 経路）
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        deferred_fanout_ids=info.deferred_fanout_ids,
        on_dynamic_expand=on_expand,
        workflow_id="t_defer",
        enable_fanout=False,  # orchestrator 側で展開済みなので executor 内で再展開しない
    )

    asyncio.run(executor.execute())

    # ----- 検証 -----
    # 1. producer / 子3つ / consumer がそれぞれ 1 回ずつ呼ばれた
    assert "P" in call_order
    children = [s for s in call_order if s.startswith("F/")]
    assert sorted(children) == ["F/UC-01", "F/UC-02", "F/UC-03"]
    assert "C" in call_order
    # F (base) 自体は run_step_fn として呼ばれない
    assert "F" not in call_order

    # 2. 実行順序: P → 子 (全件) → C
    p_idx = call_order.index("P")
    c_idx = call_order.index("C")
    assert p_idx < c_idx
    for child in children:
        ci = call_order.index(child)
        assert p_idx < ci < c_idx, (
            f"{child} が producer/consumer の間で実行されていない: order={call_order}"
        )

    # 3. on_dynamic_expand コールバックが 1 回発火
    assert len(dynamic_expand_calls) == 1
    assert dynamic_expand_calls[0][0] == "F"
    assert sorted(dynamic_expand_calls[0][1]) == ["F/UC-01", "F/UC-02", "F/UC-03"]

    # 4. base F が completed に昇格（fanout-aggregated）
    assert "F" in executor.completed
    assert executor._results["F"].reason == "fanout-aggregated"
    # 5. consumer が completed
    assert "C" in executor.completed


def test_deferred_fanout_skipped_when_input_remains_empty(tmp_path: Path) -> None:
    """upstream 完了後も入力ファイルが空なら、deferred fan-out base は skip 化される。"""
    wf = _build_deferred_test_workflow()
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        wf, {"P", "F", "C"}, tmp_path
    )
    assert "F" in info.deferred_fanout_ids

    # producer は何も生成しない（skeleton.md を作らない）
    call_order: List[str] = []

    async def run_fn(**kwargs: Any) -> bool:
        call_order.append(kwargs["step_id"])
        return True

    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        deferred_fanout_ids=info.deferred_fanout_ids,
        workflow_id="t_defer",
        enable_fanout=False,
    )
    asyncio.run(executor.execute())

    # P は実行された
    assert "P" in call_order
    # F の子は存在しない
    assert not any(s.startswith("F/") for s in call_order)
    # F は skipped（reason=fanout-empty）
    assert "F" in executor.skipped
    assert executor._results["F"].reason == "fanout-empty"
    # C (depends_on=["F"]) は F が skipped なので effective_done に含まれ実行される
    assert "C" in call_order
