"""T-C1 / T-C2: deferred fan-out 判定の単体テスト。

orchestrator._expand_workflow_for_dag が、empty_fanout_ids のうち
「同一実行内の upstream step が入力ファイルを生成する見込みのもの」を
deferred_fanout_ids として識別し、active_step_ids から discard しないことを検証する。
"""
from __future__ import annotations

from pathlib import Path

from hve.orchestrator import _expand_workflow_for_dag
from hve.workflow_registry import get_workflow, StepDef, WorkflowDef, _make_state_labels


def test_ard_step_4_2_is_deferred_when_skeleton_not_yet_generated(tmp_path: Path) -> None:
    """ARD Step 4.2 は use-case-skeleton.md が未生成でも deferred として active に残る。"""
    wf = get_workflow("ard")
    active = {"4.1", "4.2", "4.3"}
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(wf, active, tmp_path)

    assert "4.2" in info.empty_fanout_ids, "skeleton 不在で 4.2 は empty 判定されるはず"
    assert "4.2" in info.deferred_fanout_ids, "4.2 は deferred 判定されるべき"
    assert "4.2" in expanded_active, "deferred は active から discard されない"


def test_non_deferred_empty_fanout_is_discarded(tmp_path: Path) -> None:
    """upstream に入力生成 step が無い fan-out base は従来通り active から除外される。"""
    # use_case_skeleton parser を使うが、depends_on 上流に skeleton.md を作る step が無い
    isolated = StepDef(
        id="A",
        title="lonely fanout",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_parser="use_case_skeleton",
    )
    wf = WorkflowDef(
        id="test_iso",
        name="t",
        label_prefix="t",
        state_labels=_make_state_labels("t"),
        params=[],
        steps=[isolated],
    )
    _, expanded_active, info = _expand_workflow_for_dag(wf, {"A"}, tmp_path)

    assert "A" in info.empty_fanout_ids
    assert "A" not in info.deferred_fanout_ids, "上流が無いので deferred にならない"
    assert "A" not in expanded_active, "非 deferred の empty は discard される"


def test_deferred_fanout_ids_default_empty(tmp_path: Path) -> None:
    """fanout が 1 件も無い workflow では deferred_fanout_ids は空。"""
    plain = StepDef(id="P", title="p", custom_agent=None, consumed_artifacts=[])
    wf = WorkflowDef(
        id="test_plain",
        name="t",
        label_prefix="t",
        state_labels=_make_state_labels("t"),
        params=[],
        steps=[plain],
    )
    _, _, info = _expand_workflow_for_dag(wf, {"P"}, tmp_path)
    # fanout_map が空 → info はそのまま返るが deferred_fanout_ids は default
    assert info.deferred_fanout_ids == []


def test_deferred_detection_uses_transitive_depends(tmp_path: Path) -> None:
    """直接依存ではなく推移依存（A→B→C で A の出力が C の parser 入力）でも検出される。"""
    producer = StepDef(
        id="UP",
        title="upstream",
        custom_agent=None,
        consumed_artifacts=[],
        output_paths=["docs/catalog/use-case-skeleton.md"],
    )
    middle = StepDef(
        id="MID",
        title="middle",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["UP"],
    )
    consumer = StepDef(
        id="DOWN",
        title="downstream fanout",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["MID"],
        fanout_parser="use_case_skeleton",
    )
    wf = WorkflowDef(
        id="test_transitive",
        name="t",
        label_prefix="t",
        state_labels=_make_state_labels("t"),
        params=[],
        steps=[producer, middle, consumer],
    )
    _, expanded_active, info = _expand_workflow_for_dag(
        wf, {"UP", "MID", "DOWN"}, tmp_path
    )
    assert "DOWN" in info.deferred_fanout_ids
    assert "DOWN" in expanded_active


def test_deferred_detection_matches_output_paths_template(tmp_path: Path) -> None:
    """upstream の output_paths_template の {key} 置換パターンも一致判定する。"""
    producer = StepDef(
        id="UP2",
        title="upstream template",
        custom_agent=None,
        consumed_artifacts=[],
        # screen_catalog parser の入力 'docs/catalog/screen-catalog-APP-*.md' と
        # template 'docs/catalog/screen-catalog-{key}.md' が一致するか
        fanout_static_keys=["APP-01", "APP-02"],
        output_paths_template=["docs/catalog/screen-catalog-{key}.md"],
    )
    consumer = StepDef(
        id="DOWN2",
        title="downstream",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["UP2"],
        fanout_parser="screen_catalog",
    )
    wf = WorkflowDef(
        id="test_template",
        name="t",
        label_prefix="t",
        state_labels=_make_state_labels("t"),
        params=[],
        steps=[producer, consumer],
    )
    _, expanded_active, info = _expand_workflow_for_dag(
        wf, {"UP2", "DOWN2"}, tmp_path
    )
    # UP2 は static_keys 持ちなので展開され empty にならない（active から残る）
    # DOWN2 は parser=screen_catalog で empty かつ deferred 判定されるべき
    assert "DOWN2" in info.empty_fanout_ids
    assert "DOWN2" in info.deferred_fanout_ids
    assert "DOWN2" in expanded_active
