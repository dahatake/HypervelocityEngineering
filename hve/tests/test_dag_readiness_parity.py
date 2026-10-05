"""FR-DAG-10: 起動可能判定（①②③）と ``hve.dag_readiness`` の一致テスト。

期待値の表は、委譲前の 3 関数の出力を固定したものである。
- ① ``WorkflowDef.get_next_steps``
- ② ``DAGExecutor._get_next_steps``（dag_plan あり）
- ③ ``DAGExecutor._get_next_steps_from_expanded``（dag_plan なし）

単一実装の import はテスト関数の内部で行う。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from hve.dag_executor import DAGExecutor
from hve.dag_planner import build_dag_plan
from hve.workflow_registry import StepDef, WorkflowDef


def _step(step_id: str, deps: tuple = (), *, container: bool = False, block_unless: tuple = ()) -> StepDef:
    return StepDef(
        id=step_id,
        title=step_id,
        custom_agent=None,
        depends_on=list(deps),
        is_container=container,
        block_unless=list(block_unless),
    )


def _workflow(steps: List[StepDef]) -> WorkflowDef:
    return WorkflowDef(id="parity", name="parity", label_prefix="parity", state_labels={}, params=[], steps=steps)


async def _noop_step(*_args: Any, **_kwargs: Any) -> bool:
    return True


def _fork_join() -> List[StepDef]:
    return [_step("a"), _step("b", ("a",)), _step("c", ("a",)), _step("d", ("b", "c"))]


# (ケース, 対象, Step 定義, 状態, 期待値)。
# 対象: 1=①、2=②、3=③、N=dag_plan なしの ``_get_next_steps``（C8）。
# 状態のキー: completed / skipped / failed / blocked / running /
#   dynamic（動的な子の id → 依存。None は Step index に無い子）/ unordered（順序を比べない）
CASES: List[tuple] = [
    ("C1-fork", "123", _fork_join, {"completed": ["a"]}, ["b", "c"]),
    ("C1-and-wait", "123", _fork_join, {"completed": ["a", "b"]}, ["c"]),
    ("C1-join", "123", _fork_join, {"completed": ["a", "b", "c"]}, ["d"]),
    ("C2-skipped-dep", "123", _fork_join, {"completed": ["a"], "skipped": ["b", "c"]}, ["d"]),
    ("C3-unknown-dep", "123", lambda: [_step("x", ("ghost",))], {}, ["x"]),
    (
        "C4-block-unless-skipped",
        "2",
        lambda: [_step("a"), _step("b", ("a",), block_unless=("a",))],
        {"skipped": ["a"]},
        [],
    ),
    (
        "C4-block-unless-completed",
        "2",
        lambda: [_step("a"), _step("b", ("a",), block_unless=("a",))],
        {"completed": ["a"]},
        ["b"],
    ),
    (
        "C5-failed-blocked",
        "23",
        lambda: [_step("a"), _step("b", ("a",)), _step("c", ("a",)), _step("e", ("a",))],
        {"completed": ["a"], "failed": ["b"], "blocked": ["c"]},
        ["e"],
    ),
    (
        "C6-container-pending",
        "23",
        lambda: [_step("p", container=True), _step("q", ("p",))],
        {},
        [],
    ),
    (
        "C6-container-completed",
        "23",
        lambda: [_step("p", container=True), _step("q", ("p",))],
        {"completed": ["p"]},
        ["q"],
    ),
    (
        "C7-dynamic-overlay",
        "2",
        lambda: [_step("a"), _step("z", ("a",))],
        {"completed": ["a"], "running": ["f-2"], "dynamic": {"f-1": ["a"], "f-2": ["a"], "f-3": None}},
        ["z", "f-1"],
    ),
    ("C8-plan-none", "N", _fork_join, {"completed": ["a"], "failed": ["b"]}, ["c"]),
    ("C9-input-order", "123", lambda: [_step("z"), _step("m"), _step("a")], {}, ["z", "m", "a"]),
    ("C10-running-plan-node", "2", _fork_join, {"completed": ["a"], "running": ["b"]}, ["b", "c"]),
    (
        "C11-sibling-dynamic-dep",
        "2",
        lambda: [_step("a")],
        # _dynamic_child_ids は set のため、動的な子どうしの順序は定義されない
        {"completed": ["a"], "dynamic": {"f-1": ["a"], "f-2": ["f-1"]}, "unordered": True},
        ["f-1", "f-2"],
    ),
    (
        "C12-plan-wave-ignores-block-unless",
        "1",
        lambda: [_step("a"), _step("b", ("a",), block_unless=("a",))],
        {"skipped": ["a"]},
        ["b"],
    ),
    # 循環する依存は起動候補にならず、例外も出さない（優先順位計算を使わない理由）
    ("C14-cycle", "123", lambda: [_step("a", ("b",)), _step("b", ("a",))], {}, []),
]

PARAMS = [
    pytest.param(case, target, steps, state, expected, id=f"{case}-{target}")
    for case, targets, steps, state, expected in CASES
    for target in targets
]


def _executor(steps: List[StepDef], *, with_plan: bool, state: Dict[str, Any]) -> DAGExecutor:
    workflow = _workflow(steps)
    active = {step.id for step in steps if not step.is_container}
    executor = DAGExecutor(
        workflow=workflow,
        run_step_fn=_noop_step,
        active_step_ids=active,
        dag_plan=build_dag_plan(workflow, active) if with_plan else None,
        enable_fanout=False,
    )
    executor.failed = set(state.get("failed", ()))
    executor.blocked = set(state.get("blocked", ()))
    executor.running = set(state.get("running", ()))
    for child_id, deps in state.get("dynamic", {}).items():
        executor._dynamic_child_ids.add(child_id)
        if deps is not None:
            executor._workflow_step_index[child_id] = _step(child_id, tuple(deps))
    return executor


def _current_ids(target: str, steps: List[StepDef], state: Dict[str, Any]) -> List[str]:
    completed = list(state.get("completed", ()))
    skipped = list(state.get("skipped", ()))
    if target == "1":
        return [s.id for s in _workflow(steps).get_next_steps(completed, skipped)]
    if target == "2":
        executor = _executor(steps, with_plan=True, state=state)
        return [s.id for s in executor._get_next_steps(completed, skipped)]
    executor = _executor(steps, with_plan=False, state=state)
    if target == "N":
        return [s.id for s in executor._get_next_steps(completed, skipped)]
    return [s.id for s in executor._get_next_steps_from_expanded(completed, skipped)]


def _single_impl_ids(target: str, steps: List[StepDef], state: Dict[str, Any]) -> List[str]:
    from hve.dag_readiness import select_ready_ids

    nodes = [
        {
            "id": s.id,
            "deps": list(s.depends_on),
            # ① は block_unless を見ない（D13）
            "block_unless": list(s.block_unless) if target == "2" else [],
            "container": s.is_container,
        }
        for s in steps
    ]
    known_ids = {s.id for s in steps}
    dynamic = state.get("dynamic", {})
    nodes += [
        {"id": child_id, "deps": list(deps), "block_unless": [], "container": False}
        for child_id, deps in dynamic.items()
        if deps is not None
    ]
    excluded = set() if target == "1" else set(state.get("failed", ())) | set(state.get("blocked", ()))
    excluded |= set(state.get("running", ())) & set(dynamic)
    return select_ready_ids(
        nodes,
        known_ids=known_ids,
        completed=set(state.get("completed", ())),
        skipped=set(state.get("skipped", ())),
        excluded=excluded,
    )


@pytest.mark.parametrize("case,target,steps,state,expected", PARAMS)
def test_current_readiness_matches_expected_table(case, target, steps, state, expected) -> None:
    actual = _current_ids(target, steps(), state)
    assert (sorted(actual) if state.get("unordered") else actual) == expected


@pytest.mark.parametrize("case,target,steps,state,expected", PARAMS)
def test_single_impl_matches_expected_table(case, target, steps, state, expected) -> None:
    actual = _single_impl_ids(target, steps(), state)
    assert (sorted(actual) if state.get("unordered") else actual) == expected


def _spy(calls: List[Any]):
    def select_ready_ids(nodes, **kwargs):
        calls.append((list(nodes), kwargs))
        return []

    return select_ready_ids


def test_c13_plan_readiness_delegation(monkeypatch) -> None:
    calls: List[Any] = []
    monkeypatch.setattr("hve.dag_readiness.select_ready_ids", _spy(calls))
    assert _workflow(_fork_join()).get_next_steps([]) == []
    assert calls


def test_c13_executor_readiness_delegation(monkeypatch) -> None:
    calls: List[Any] = []
    monkeypatch.setattr("hve.dag_executor.select_ready_ids", _spy(calls))
    assert _executor(_fork_join(), with_plan=True, state={})._get_next_steps([]) == []
    assert calls


def test_c13_expanded_readiness_delegation(monkeypatch) -> None:
    calls: List[Any] = []
    monkeypatch.setattr("hve.dag_executor.select_ready_ids", _spy(calls))
    assert _executor(_fork_join(), with_plan=False, state={})._get_next_steps_from_expanded([]) == []
    assert calls
