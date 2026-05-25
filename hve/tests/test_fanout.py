"""ADR-0002 fan-out 機構の基本動作テスト。

実 Copilot SDK は呼び出さず、fanout_expander / DAGExecutor の DAG 計算と
StepDef メタ整合性のみを検証する。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from hve import workflow_registry as wr
from hve.catalog_parsers import KNOWN_PARSERS
from hve.fanout_expander import expand_workflow_fanout, FanoutChildStep
from hve.dag_executor import DAGExecutor, StepResult


# ---------------------------------------------------------------------------
# T5C: WorkflowDef × catalog_parsers 整合
# ---------------------------------------------------------------------------

def test_akm_has_fanout_21_keys():
    akm = wr.get_workflow("akm")
    step1 = akm.get_step("1")
    assert step1 is not None
    assert step1.fanout_static_keys is not None
    assert len(step1.fanout_static_keys) == 21
    assert step1.fanout_static_keys[0] == "D01"
    assert step1.fanout_static_keys[-1] == "D21"


def test_akm_has_review_join_step():
    akm = wr.get_workflow("akm")
    step2 = akm.get_step("2")
    assert step2 is not None
    assert "1" in step2.depends_on
    assert step2.custom_agent == "QA-DocConsistency"


def test_akm_max_parallel_is_21():
    akm = wr.get_workflow("akm")
    assert akm.max_parallel == 21


def test_all_known_fanout_parsers_registered():
    expected = {"app_catalog", "screen_catalog", "service_catalog",
                "dataflow_catalog", "agent_catalog"}
    assert expected.issubset(KNOWN_PARSERS)


def test_all_workflows_fanout_parsers_are_known():
    """全 WorkflowDef の fanout_parser 名が catalog_parsers に登録されている。"""
    for wf_id in ("ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
                  "aag", "aagd", "akm", "aqod", "adoc"):
        wf = wr.get_workflow(wf_id)
        for s in wf.steps:
            parser = getattr(s, "fanout_parser", None)
            if parser:
                assert parser in KNOWN_PARSERS, (
                    f"{wf_id} step {s.id}: 未登録 parser '{parser}'"
                )


# ---------------------------------------------------------------------------
# fanout_expander
# ---------------------------------------------------------------------------

def test_akm_fanout_expander_produces_21_children(tmp_path):
    akm = wr.get_workflow("akm")
    expanded = expand_workflow_fanout(akm, tmp_path)
    # Step 1 が 21 個に展開され、Step 2 が下流に残る
    child_ids = expanded.fanout_map.get("1", [])
    assert len(child_ids) == 21
    assert child_ids[0] == "1/D01"
    assert child_ids[-1] == "1/D21"
    # 展開後ステップは Step 2 (1) + 21 子 = 22
    step_ids = [s.id for s in expanded.steps]
    assert "2" in step_ids
    for cid in child_ids:
        assert cid in step_ids
    # Step 2 の depends_on が子 ID リストへ remapping されている
    step2 = next(s for s in expanded.steps if s.id == "2")
    assert sorted(step2.depends_on) == sorted(child_ids)


def test_fanout_child_carries_fanout_meta(tmp_path):
    akm = wr.get_workflow("akm")
    expanded = expand_workflow_fanout(akm, tmp_path)
    child = next(s for s in expanded.steps if s.id == "1/D01")
    assert isinstance(child, FanoutChildStep)
    assert child.fanout_key == "D01"
    assert child.base_step_id == "1"
    assert child.custom_agent == "KnowledgeManager"
    assert child.additional_prompt_template_path is not None


def test_fanout_empty_parser_marks_skip(tmp_path):
    """カタログファイルが存在しない fanout_parser は empty_fanout_ids に入る。"""
    # 動的 fanout を持つ仮 StepDef を作る
    fake = wr.StepDef(
        id="X", title="fake", custom_agent=None,
        fanout_parser="app_catalog",
    )
    fake_wf = wr.WorkflowDef(
        id="test", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    # tmp_path にカタログがないので 0 件 → empty
    assert "X" in expanded.empty_fanout_ids
    assert expanded.fanout_map.get("X") == []


# ---------------------------------------------------------------------------
# Sub-3 (Q3=b): output_paths_template の {key} 置換
# ---------------------------------------------------------------------------


def test_output_paths_template_resolves_with_key(tmp_path):
    """output_paths_template が fan-out 子で {key} 置換されること。"""
    fake = wr.StepDef(
        id="Y",
        title="fake",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_static_keys=["D01", "D02"],
        output_paths_template=["docs/foo/{key}-detail.md", "docs/bar/{key}.md"],
    )
    fake_wf = wr.WorkflowDef(
        id="test_template", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    child_d01 = next(s for s in expanded.steps if s.id == "Y/D01")
    child_d02 = next(s for s in expanded.steps if s.id == "Y/D02")
    assert child_d01.output_paths == ["docs/foo/D01-detail.md", "docs/bar/D01.md"]
    assert child_d02.output_paths == ["docs/foo/D02-detail.md", "docs/bar/D02.md"]


def test_output_paths_inherited_when_template_absent(tmp_path):
    """output_paths_template が None なら親 StepDef.output_paths を継承すること。"""
    fake = wr.StepDef(
        id="Z",
        title="fake",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_static_keys=["D01"],
        output_paths=["docs/parent-output.md"],
    )
    fake_wf = wr.WorkflowDef(
        id="test_inherit", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    child = next(s for s in expanded.steps if s.id == "Z/D01")
    assert child.output_paths == ["docs/parent-output.md"]


# ---------------------------------------------------------------------------
# DAGExecutor: AKM 21 並列の Wave 計算
# ---------------------------------------------------------------------------

def _make_dummy_run_step():
    calls: List[Dict[str, Any]] = []

    async def run(**kwargs):
        calls.append(kwargs)
        return True
    return run, calls


def test_dag_executor_expands_akm_to_21_parallel(tmp_path):
    akm = wr.get_workflow("akm")
    run_fn, calls = _make_dummy_run_step()
    # active_step_ids にはベース ID と Step 2 を入れる（展開後子も自動 active 化される）
    active = {"1", "2"}
    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_fn,
        active_step_ids=active,
        repo_root=tmp_path,
    )
    waves = executor.compute_waves()
    # 1 つ目の Wave は 21 個の子ステップ、2 つ目は Step 2
    assert len(waves) == 2
    assert len(waves[0]) == 21
    assert len(waves[1]) == 1
    assert waves[1][0].id == "2"


def test_dag_executor_runs_all_children(tmp_path):
    akm = wr.get_workflow("akm")
    run_fn, calls = _make_dummy_run_step()
    active = {"1", "2"}
    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_fn,
        active_step_ids=active,
        repo_root=tmp_path,
    )
    results = asyncio.run(executor.execute())
    # 21 子 + Step 2 = 22 ステップが実行された
    assert len(calls) == 22
    called_ids = {c["step_id"] for c in calls}
    assert "1/D01" in called_ids
    assert "1/D21" in called_ids
    assert "2" in called_ids
    # fanout_meta が子に渡され、Step 2 には渡されない
    for c in calls:
        if "/" in c["step_id"]:
            assert "fanout_meta" in c
            assert c["fanout_meta"]["base_step_id"] == "1"
        else:
            assert "fanout_meta" not in c


# ---------------------------------------------------------------------------
# Production 経路 (dag_plan 併用): orchestrator が fan-out を事前展開する
# ---------------------------------------------------------------------------

def test_prepare_workflow_for_dag_expands_active_and_steps(tmp_path):
    """orchestrator._expand_workflow_for_dag が steps と active_step_ids を
    fan-out 子で拡張すること。
    """
    from hve.orchestrator import _expand_workflow_for_dag  # T3a で追加予定

    akm = wr.get_workflow("akm")
    active = {"1", "2"}
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        akm, active, tmp_path
    )
    # active_step_ids に子 ID が含まれる
    assert "1/D01" in expanded_active
    assert "1/D21" in expanded_active
    # ベース ID "1" は steps から除外される（K-1 空展開時のみ残る）
    step_ids = {s.id for s in expanded_wf.steps}
    assert "1" not in step_ids
    assert "1/D01" in step_ids
    assert "2" in step_ids
    # info に fanout_map が含まれる
    assert "1" in info.fanout_map
    assert len(info.fanout_map["1"]) == 21


def test_prepare_workflow_then_build_dag_plan_produces_parallel_wave(tmp_path):
    """build_dag_plan が展開後 workflow から 21 並列子の Wave を生成すること。

    本来 production 経路 (orchestrator → build_dag_plan → DAGExecutor with dag_plan)
    が fan-out を起動できなかった根本問題の回帰テスト。
    """
    from hve.orchestrator import _expand_workflow_for_dag
    from hve.dag_planner import build_dag_plan

    akm = wr.get_workflow("akm")
    active = {"1", "2"}
    expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
        akm, active, tmp_path
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    # Wave 1 に 21 子ステップ、Wave 2 に Step 2
    wave_step_ids = [list(w.step_ids) for w in plan.waves]
    assert len(wave_step_ids) == 2
    assert len(wave_step_ids[0]) == 21
    assert all(sid.startswith("1/D") for sid in wave_step_ids[0])
    assert wave_step_ids[1] == ["2"]


def test_dag_executor_with_dag_plan_runs_fanout_children(tmp_path):
    """DAGExecutor が事前展開済み workflow + dag_plan で 21 子を実行する。"""
    from hve.orchestrator import _expand_workflow_for_dag
    from hve.dag_planner import build_dag_plan

    akm = wr.get_workflow("akm")
    active = {"1", "2"}
    expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
        akm, active, tmp_path
    )
    plan = build_dag_plan(expanded_wf, expanded_active)
    run_fn, calls = _make_dummy_run_step()
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        dag_plan=plan,  # production 経路
    )
    asyncio.run(executor.execute())
    called_ids = {c["step_id"] for c in calls}
    assert "1/D01" in called_ids
    assert "1/D21" in called_ids
    assert "2" in called_ids
    assert len(calls) == 22


def test_prepare_workflow_for_dag_handles_empty_fanout(tmp_path):
    """カタログファイルがない動的 fanout は empty とマークされ、active から除外される（K-1 skip）。"""
    from hve.orchestrator import _expand_workflow_for_dag

    fake = wr.StepDef(
        id="X", title="fake", custom_agent="DummyAgent",
        fanout_parser="app_catalog",
    )
    fake_wf = wr.WorkflowDef(
        id="t_empty", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        fake_wf, {"X"}, tmp_path
    )
    # 0 件展開 → ベース ID が info.empty_fanout_ids に記録され active から除外される
    assert "X" in info.empty_fanout_ids
    assert "X" not in expanded_active


def test_prepare_workflow_for_dag_remaps_downstream_depends_on(tmp_path):
    """fan-out 親に依存する下流ステップの depends_on が子 ID リストへ書き換わる。"""
    from hve.orchestrator import _expand_workflow_for_dag

    akm = wr.get_workflow("akm")
    expanded_wf, _, _ = _expand_workflow_for_dag(akm, {"1", "2"}, tmp_path)
    step2 = next(s for s in expanded_wf.steps if s.id == "2")
    # Step 2 の depends_on は元々 ["1"]、展開後は ["1/D01", ..., "1/D21"]
    assert "1" not in step2.depends_on
    assert "1/D01" in step2.depends_on
    assert len(step2.depends_on) == 21


def test_step_prompts_propagate_to_fanout_children():
    """fan-out 親の step_prompts が build_dag_plan を経由して子 ID にも届くこと。

    fanout-fix の回帰テスト: orchestrator が step_prompts を base ID のみ構築した状態
    （wf.steps を反復するため）でも、展開後 fanout_map を使った伝播ロジックで
    子 ID が base prompt を継承することを保証する。
    """
    from hve.orchestrator import _expand_workflow_for_dag
    from hve.dag_planner import build_dag_plan
    import tempfile
    from pathlib import Path as _Path

    akm = wr.get_workflow("akm")
    active = {"1", "2"}
    with tempfile.TemporaryDirectory() as td:
        expanded_wf, expanded_active, expand_info = _expand_workflow_for_dag(
            akm, active, _Path(td)
        )
        # orchestrator と同じ伝播ロジックを直接適用
        step_prompts = {"1": "BASE_PROMPT_FOR_STEP_1", "2": "BASE_PROMPT_FOR_STEP_2"}
        for base_id, child_ids in expand_info.fanout_map.items():
            if base_id in step_prompts:
                for cid in child_ids:
                    step_prompts.setdefault(cid, step_prompts[base_id])

        plan = build_dag_plan(expanded_wf, expanded_active, step_prompts=step_prompts)

    # 21 子全てに base prompt が伝播していること
    assert plan.prompt_for("1/D01") == "BASE_PROMPT_FOR_STEP_1"
    assert plan.prompt_for("1/D21") == "BASE_PROMPT_FOR_STEP_1"
    assert plan.prompt_for("2") == "BASE_PROMPT_FOR_STEP_2"


def test_dag_executor_passes_propagated_prompt_to_child(tmp_path):
    """fan-out 子に伝播された prompt が DAGExecutor 経由で run_step_fn に届くこと。"""
    from hve.orchestrator import _expand_workflow_for_dag
    from hve.dag_planner import build_dag_plan

    akm = wr.get_workflow("akm")
    active = {"1", "2"}
    expanded_wf, expanded_active, expand_info = _expand_workflow_for_dag(
        akm, active, tmp_path
    )
    step_prompts = {"1": "BASE_PROMPT_FOR_STEP_1", "2": "BASE_PROMPT_FOR_STEP_2"}
    for base_id, child_ids in expand_info.fanout_map.items():
        if base_id in step_prompts:
            for cid in child_ids:
                step_prompts.setdefault(cid, step_prompts[base_id])
    plan = build_dag_plan(expanded_wf, expanded_active, step_prompts=step_prompts)

    run_fn, calls = _make_dummy_run_step()
    executor = DAGExecutor(
        workflow=expanded_wf,
        run_step_fn=run_fn,
        active_step_ids=expanded_active,
        repo_root=tmp_path,
        dag_plan=plan,
    )
    asyncio.run(executor.execute())
    by_id = {c["step_id"]: c for c in calls}
    # 子も親と同じ base prompt を受け取る（空ではない）
    assert by_id["1/D01"]["prompt"] == "BASE_PROMPT_FOR_STEP_1"
    assert by_id["1/D21"]["prompt"] == "BASE_PROMPT_FOR_STEP_1"
    assert by_id["2"]["prompt"] == "BASE_PROMPT_FOR_STEP_2"
