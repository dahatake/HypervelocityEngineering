"""FIX-2: fan-out 展開後の表示ステップ総数が実行対象数と一致すること。

`orchestrator._expand_workflow_for_dag` は deferred fan-out のランタイム再展開に
備えて fan-out ベース ID を `active_step_ids` へ残す。そのため
`len(active_step_ids)` を実行計画パネルの合計・進捗の分母に使うと、展開済み
ベースの分だけ過大表示になる（AKM は 23 と表示されるが実行対象は 22）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional

from hve import workflow_registry as wr
from hve.dag_executor import DAGExecutor
from hve.dag_planner import build_dag_plan
from hve.orchestrator import _expand_workflow_for_dag


async def _noop_run_step(**_kwargs: Any) -> bool:
    return True


class _CountingConsole:
    """`dag_progress` の引数だけを記録する最小 Console スタブ。"""

    def __init__(self) -> None:
        self.progress_calls: List[tuple] = []

    def dag_progress(self, completed: int, running: int, total: int) -> None:
        self.progress_calls.append((completed, running, total))

    def __getattr__(self, _name: str):
        def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None

        return _noop


def _build_akm_executor(
    tmp_path: Path, console: Optional[Any] = None,
) -> DAGExecutor:
    akm = wr.get_workflow("akm")
    expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
        akm, {"1", "2"}, tmp_path,
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    return DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=_noop_run_step,
        active_step_ids=expanded_active,
        dag_plan=plan,
        console=console,
        repo_root=tmp_path,
    )


def _akm_expected_counts() -> tuple[int, int]:
    """AKM 定義から (active 総数, 実行対象数) を導出する。

    fan-out キー数の増減でテストが一斉に壊れないよう定数を直書きしない。
    active = ベース "1" + Step "2" + 子、実行対象 = 子 + Step "2"。
    """
    step1 = wr.get_workflow("akm").get_step("1")
    assert step1 is not None
    child_count = len(step1.fanout_static_keys or [])
    assert child_count > 0, "AKM Step.1 の fan-out キーが空になっている"
    return 2 + child_count, child_count + 1


def test_akm_active_ids_still_include_expanded_fanout_base(tmp_path: Path) -> None:
    """前提の固定: 展開済みベース ID は active に残るが wave には現れない。"""
    active_total, executable_total = _akm_expected_counts()
    executor = _build_akm_executor(tmp_path)

    assert "1" in executor.active_step_ids
    assert len(executor.active_step_ids) == active_total
    assert sum(len(w) for w in executor.compute_waves()) == executable_total


def test_akm_display_total_matches_executable_steps(tmp_path: Path) -> None:
    _, executable_total = _akm_expected_counts()
    executor = _build_akm_executor(tmp_path)

    assert executor.total_display_steps() == executable_total


def test_dag_progress_uses_display_total(tmp_path: Path) -> None:
    _, executable_total = _akm_expected_counts()
    console = _CountingConsole()
    executor = _build_akm_executor(tmp_path, console=console)

    asyncio.run(executor.execute())

    assert console.progress_calls, "dag_progress が一度も呼ばれていない"
    assert {total for _, _, total in console.progress_calls} == {executable_total}
    assert max(completed for completed, _, _ in console.progress_calls) == executable_total


# ---------------------------------------------------------------------------
# コンテナ step（active に入るが wave には現れない）
# ---------------------------------------------------------------------------


def test_container_steps_are_excluded_from_display_total(tmp_path: Path) -> None:
    container = wr.StepDef(id="G", title="group", custom_agent=None, is_container=True)
    child = wr.StepDef(
        id="G.1", title="child", custom_agent="DummyAgent", consumed_artifacts=[],
    )
    wf = wr.WorkflowDef(
        id="t_container",
        name="t_container",
        label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[],
        steps=[container, child],
    )
    expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
        wf, {"G", "G.1"}, tmp_path,
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=_noop_run_step,
        active_step_ids=expanded_active,
        dag_plan=plan,
        repo_root=tmp_path,
    )

    assert "G" in executor.active_step_ids
    assert executor.total_display_steps() == 1


def test_asdw_web_display_total_matches_wave_total(tmp_path: Path) -> None:
    """コンテナと fan-out ベースを同時に持つ実 workflow でも wave 総数と一致する。"""
    wf = wr.get_workflow("asdw-web")
    containers = {s.id for s in wf.steps if getattr(s, "is_container", False)}
    assert containers, "asdw-web にコンテナ step が存在する前提が崩れている"

    expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
        wf, {s.id for s in wf.steps}, tmp_path,
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=_noop_run_step,
        active_step_ids=expanded_active,
        dag_plan=plan,
        repo_root=tmp_path,
    )

    assert containers <= executor.active_step_ids
    assert executor.total_display_steps() == sum(
        len(w) for w in executor.compute_waves()
    )
    assert executor.total_display_steps() < len(executor.active_step_ids)


# ---------------------------------------------------------------------------
# deferred fan-out（空展開 base がランタイム再展開される経路）
# ---------------------------------------------------------------------------


def _build_deferred_workflow() -> wr.WorkflowDef:
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
        id="t_defer_count",
        name="t_defer_count",
        label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[],
        steps=[producer, fanout_base, consumer],
    )


def test_deferred_fanout_base_is_counted_before_expansion(tmp_path: Path) -> None:
    """展開前の deferred base は実行対象なのでカウントから落ちない。"""
    wf = _build_deferred_workflow()
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        wf, {"P", "F", "C"}, tmp_path,
    )
    assert "F" in info.deferred_fanout_ids

    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=_noop_run_step,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        deferred_fanout_ids=set(info.deferred_fanout_ids),
        enable_fanout=False,
    )

    assert executor.total_display_steps() == 3


def test_deferred_fanout_children_are_counted_after_expansion(tmp_path: Path) -> None:
    """ランタイム展開後は子もカウントされ、完了数が総数を超えない。"""
    wf = _build_deferred_workflow()
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        wf, {"P", "F", "C"}, tmp_path,
    )
    skeleton_path = tmp_path / "docs" / "catalog" / "use-case-skeleton.md"

    async def run_fn(**kwargs: Any) -> bool:
        if kwargs["step_id"] == "P":
            skeleton_path.parent.mkdir(parents=True, exist_ok=True)
            skeleton_path.write_text(
                "# Skeleton\n\n## UC-01\n本文\n## UC-02\n本文\n## UC-03\n本文\n",
                encoding="utf-8",
            )
        return True

    console = _CountingConsole()
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        deferred_fanout_ids=set(info.deferred_fanout_ids),
        enable_fanout=False,
        console=console,
    )

    asyncio.run(executor.execute())

    # P + 子 3 + F(集約) + C = 6
    assert executor.total_display_steps() == 6
    assert len(executor.completed) <= executor.total_display_steps()
    assert console.progress_calls
    assert all(
        completed <= total for completed, _, total in console.progress_calls
    ), f"完了数が総数を超えた: {console.progress_calls}"


def test_deferred_fanout_counts_stay_consistent_on_production_path(
    tmp_path: Path,
) -> None:
    """dag_plan 併用（production 経路）でも完了数が総数を超えない。"""
    wf = _build_deferred_workflow()
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        wf, {"P", "F", "C"}, tmp_path,
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    skeleton_path = tmp_path / "docs" / "catalog" / "use-case-skeleton.md"

    async def run_fn(**kwargs: Any) -> bool:
        if kwargs["step_id"] == "P":
            skeleton_path.parent.mkdir(parents=True, exist_ok=True)
            skeleton_path.write_text(
                "# Skeleton\n\n## UC-01\n本文\n## UC-02\n本文\n",
                encoding="utf-8",
            )
        return True

    console = _CountingConsole()
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        dag_plan=plan,
        repo_root=tmp_path,
        deferred_fanout_ids=set(info.deferred_fanout_ids),
        enable_fanout=False,
        console=console,
    )

    assert executor.total_display_steps() == 3

    asyncio.run(executor.execute())

    # P + 子 2 + F(集約) + C = 5
    assert executor.total_display_steps() == 5
    assert len(executor.completed) <= executor.total_display_steps()
    assert console.progress_calls
    assert all(
        completed <= total for completed, _, total in console.progress_calls
    ), f"完了数が総数を超えた: {console.progress_calls}"
