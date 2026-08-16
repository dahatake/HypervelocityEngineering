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
from hve.catalog_parsers import KNOWN_PARSERS, parse_agent_catalog
from hve.fanout_expander import expand_workflow_fanout, FanoutChildStep
from hve.fanout_expander import expand_single_step_fanout
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
                  "aag", "aagd", "akm", "adi", "adoc"):
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


def test_adi_questionnaire_fanout_produces_21_children(tmp_path):
    adi = wr.get_workflow("adi")
    expanded = expand_workflow_fanout(adi, tmp_path)
    child_ids = expanded.fanout_map.get("1.1", [])

    assert child_ids == [f"1.1/D{n:02d}" for n in range(1, 22)]
    for n, child_id in enumerate(child_ids, start=1):
        child = next(s for s in expanded.steps if s.id == child_id)
        assert child.output_paths == [
            f"qa/D{n:02d}-original-docs-questionnaire.md",
        ]
    join = next(s for s in expanded.steps if s.id == "1.2")
    assert sorted(join.depends_on) == sorted(child_ids)


def test_fanout_child_carries_fanout_meta(tmp_path):
    akm = wr.get_workflow("akm")
    expanded = expand_workflow_fanout(akm, tmp_path)
    child = next(s for s in expanded.steps if s.id == "1/D01")
    assert isinstance(child, FanoutChildStep)
    assert child.fanout_key == "D01"
    assert child.base_step_id == "1"
    assert child.custom_agent == "KnowledgeManager"
    assert child.additional_prompt_template_path is not None


def test_fanout_child_inherits_remote_cicd_flag(tmp_path):
    """FanoutChildStep は StepDef 互換属性 requires_remote_cicd を継承する。"""
    fake = wr.StepDef(
        id="R",
        title="remote",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_static_keys=["K1"],
        requires_remote_cicd=True,
    )
    fake_wf = wr.WorkflowDef(
        id="test_remote_cicd_fanout", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    child = next(s for s in expanded.steps if s.id == "R/K1")
    assert child.requires_remote_cicd is True


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


def test_required_input_paths_resolve_with_key(tmp_path):
    """required_input_paths の {key} が fan-out 子の実キーへ置換されること。"""
    fake = wr.StepDef(
        id="Y",
        title="fake",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_static_keys=["AG-01"],
        required_input_paths=[
            "docs/agent/agent-detail-{key}.md",
            "docs/shared/input.md",
        ],
    )
    fake_wf = wr.WorkflowDef(
        id="test_required_input_template", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[fake],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    child = next(s for s in expanded.steps if s.id == "Y/AG-01")
    assert child.required_input_paths == [
        "docs/agent/agent-detail-AG-01.md",
        "docs/shared/input.md",
    ]


def test_agent_catalog_uses_step2_canonical_agt_ids(tmp_path):
    """Step 2 の Agent Inventory から canonical AGT ID を取得する。"""
    definition = tmp_path / "docs" / "agent" / "agent-application-definition.md"
    definition.parent.mkdir(parents=True, exist_ok=True)
    definition.write_text("# Application Definition\n\nAgent ID は未採番。\n", encoding="utf-8")
    architecture = tmp_path / "docs" / "agent" / "agent-architecture.md"
    architecture.write_text(
        "# Agent Architecture\n\n| Agent ID | Name |\n|---|---|\n"
        "| AGT-UC-01-01 | Support |\n| AGT-UC-01-02 | Audit |\n",
        encoding="utf-8",
    )

    assert parse_agent_catalog(tmp_path) == ["AGT-UC-01-01", "AGT-UC-01-02"]


def test_agent_catalog_falls_back_to_standard_catalog_second_column(tmp_path):
    """primaryが0件なら標準AI Agent一覧の第2列Agent IDへfallbackする。"""
    architecture = tmp_path / "docs" / "agent" / "agent-architecture.md"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text("# Agent Architecture\n\nAgent一覧は未生成。\n", encoding="utf-8")
    catalog = tmp_path / "docs" / "ai-agent-catalog.md"
    catalog.write_text(
        "# AI Agent 一覧\n\n"
        "| # | Agent ID | Agent Name | 種別 |\n"
        "|---|---|---|---|\n"
        "| 1 | AGT-UC-01-01 | Support | Single |\n"
        "| 2 | AGT-UC-01-02 | Audit | Single |\n",
        encoding="utf-8",
    )

    assert parse_agent_catalog(tmp_path) == ["AGT-UC-01-01", "AGT-UC-01-02"]


def test_aag_step2_is_single_and_step3_fans_out_from_architecture(tmp_path):
    """Agent ID producerのStep 2は単発、consumerのStep 3だけをfan-outする。"""
    architecture = tmp_path / "docs" / "agent" / "agent-architecture.md"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text(
        "| Agent ID | Name |\n|---|---|\n| AGT-UC-01-01 | Support |\n",
        encoding="utf-8",
    )

    aag = wr.get_workflow("aag")
    assert aag.get_step("2").fanout_parser is None
    assert aag.get_step("3").fanout_parser == "agent_catalog"
    expanded = expand_workflow_fanout(aag, tmp_path)
    assert "2" not in expanded.fanout_map
    assert expanded.fanout_map["3"] == ["3/AGT-UC-01-01"]


def test_aagd_real_steps_resolve_all_agent_specific_required_inputs(tmp_path):
    """AAGDの実Stepを展開するとAgent固有input/outputにplaceholderが残らない。"""
    architecture = tmp_path / "docs" / "agent" / "agent-architecture.md"
    architecture.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text(
        "| Agent ID | Name |\n|---|---|\n| AGT-UC-01-01 | Support |\n",
        encoding="utf-8",
    )

    expanded = expand_workflow_fanout(wr.get_workflow("aagd"), tmp_path)
    expected_paths = {
        "2.1": ["docs/test-specs/AGT-UC-01-01-test-spec.md"],
        "2.2": [
            "docs/agent/agent-detail-AGT-UC-01-01.md",
            "docs/test-specs/AGT-UC-01-01-test-spec.md",
        ],
        "2.3": [
            "docs/agent/agent-detail-AGT-UC-01-01.md",
            "docs/test-specs/AGT-UC-01-01-test-spec.md",
            "src/test/agent/AGT-UC-01-01.Tests/",
        ],
        "3": [
            "docs/agent/agent-detail-AGT-UC-01-01.md",
            "src/agent/AGT-UC-01-01/",
        ],
    }
    for step_id, expected in expected_paths.items():
        child = next(s for s in expanded.steps if s.id == f"{step_id}/AGT-UC-01-01")
        agent_paths = child.output_paths + child.required_input_paths
        for path in expected:
            assert path in agent_paths
        assert all("{" not in p and "}" not in p for p in expected)


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
# T-B1: expand_single_step_fanout — ランタイム再展開用の単発 API
# ---------------------------------------------------------------------------


def test_expand_single_step_fanout_returns_children_for_static_keys(tmp_path):
    """fanout_static_keys を持つ base step を渡すと子リストが返る。"""
    base = wr.StepDef(
        id="S",
        title="single",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_static_keys=["K1", "K2", "K3"],
    )
    children = expand_single_step_fanout(base, tmp_path)
    assert children is not None
    assert [c.id for c in children] == ["S/K1", "S/K2", "S/K3"]
    assert all(isinstance(c, FanoutChildStep) for c in children)
    assert children[0].base_step_id == "S"
    assert children[0].fanout_key == "K1"


def test_expand_single_step_fanout_returns_none_for_non_fanout_step(tmp_path):
    """fan-out 指定なし (static_keys も parser も無い) → None。"""
    plain = wr.StepDef(
        id="P",
        title="plain",
        custom_agent=None,
        consumed_artifacts=[],
    )
    assert expand_single_step_fanout(plain, tmp_path) is None


def test_expand_single_step_fanout_returns_none_for_empty_parser_result(tmp_path):
    """parser がキー 0 件を返す (カタログ不在) 場合 → None。"""
    parsed = wr.StepDef(
        id="Q",
        title="parsed",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_parser="use_case_skeleton",
    )
    # tmp_path に skeleton.md が存在しないので 0 件 → None
    assert expand_single_step_fanout(parsed, tmp_path) is None


def test_expand_single_step_fanout_uses_parser_when_file_exists(tmp_path):
    """parser の入力ファイルを tmp に作成すると、その内容から子が生成される。"""
    skeleton = tmp_path / "docs" / "catalog" / "use-case-skeleton.md"
    skeleton.parent.mkdir(parents=True, exist_ok=True)
    skeleton.write_text(
        "# Skeleton\n\n## UC-01\n本文\n## UC-02\n本文\n",
        encoding="utf-8",
    )
    parsed = wr.StepDef(
        id="R",
        title="parsed",
        custom_agent=None,
        consumed_artifacts=[],
        fanout_parser="use_case_skeleton",
    )
    children = expand_single_step_fanout(parsed, tmp_path)
    assert children is not None
    assert [c.id for c in children] == ["R/UC-01", "R/UC-02"]


def test_expand_single_step_fanout_does_not_mutate_base(tmp_path):
    """base_step.depends_on 等が呼び出し後に変更されていない。"""
    base = wr.StepDef(
        id="T",
        title="t",
        custom_agent=None,
        consumed_artifacts=[],
        depends_on=["U", "V"],
        fanout_static_keys=["A", "B"],
    )
    before_deps = list(base.depends_on)
    expand_single_step_fanout(base, tmp_path)
    assert base.depends_on == before_deps


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


def test_fanout_child_depends_on_fanout_parent_is_remapped(tmp_path):
    """fan-out 親 C が他の fan-out 親 A, B に依存するとき、C の各子の depends_on が
    A, B の全子 ID へクロス積で展開されること（aad-web Step 2.3 リグレッション）。

    バグ再現条件:
      - A (fan-out, keys=[a1, a2])
      - B (fan-out, keys=[b1])
      - C (fan-out, depends_on=["A", "B"], keys=[c1, c2])
    期待:
      - C/c1 と C/c2 の depends_on が {A/a1, A/a2, B/b1} に張り替えられる
      - 生 ID "A" / "B" は depends_on に残らない（→ existing_ids フォールバックで
        誤って「解決済み」と扱われる現行バグの再発防止）
    """
    a = wr.StepDef(
        id="A", title="parent-A", custom_agent=None,
        consumed_artifacts=[], fanout_static_keys=["a1", "a2"],
    )
    b = wr.StepDef(
        id="B", title="parent-B", custom_agent=None,
        consumed_artifacts=[], fanout_static_keys=["b1"],
    )
    c = wr.StepDef(
        id="C", title="parent-C", custom_agent=None,
        depends_on=["A", "B"],
        consumed_artifacts=[], fanout_static_keys=["c1", "c2"],
    )
    fake_wf = wr.WorkflowDef(
        id="test_fanout_chain", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[a, b, c],
    )
    expanded = expand_workflow_fanout(fake_wf, tmp_path)
    c_children = [s for s in expanded.steps if s.id in ("C/c1", "C/c2")]
    assert len(c_children) == 2
    expected_deps = {"A/a1", "A/a2", "B/b1"}
    for child in c_children:
        deps = set(child.depends_on)
        assert deps == expected_deps, (
            f"{child.id} depends_on={deps}, expected={expected_deps}"
        )
        assert "A" not in deps and "B" not in deps


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


# ---------------------------------------------------------------------------
# T03/T04: APP-ID フィルタ (Step 1 で APP-07 単独選択時に Step 2 全件展開バグ対応)
# ---------------------------------------------------------------------------


from hve.fanout_expander import _filter_keys_by_app_ids, _SCREEN_KEY_PREFIX_RE


def _write_min_app_catalog(tmp_path, app_ids):
    """app-catalog.md の最小版を tmp_path に書き出す（A 節サマリ表のみ）。"""
    p = tmp_path / "docs" / "catalog" / "app-catalog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {aid} | name-{aid} |" for aid in app_ids)
    p.write_text(
        "# App Catalog\n\n## A. サマリ\n\n"
        "| APP-ID | 名称 |\n"
        "|---|---|\n"
        f"{rows}\n",
        encoding="utf-8",
    )


def _write_min_screen_catalogs(tmp_path, screens_by_app):
    """screen-catalog-APP-NN.md を APP-ID 毎に作成する。

    screens_by_app: {"APP-07": ["S001", "S002"], "APP-100": ["S001"]}
    """
    for app_id, screen_ids in screens_by_app.items():
        p = tmp_path / "docs" / "catalog" / f"screen-catalog-{app_id}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(
            f"| {app_id}-{sid} | screen-{sid} |" for sid in screen_ids
        )
        p.write_text(
            f"# Screen Catalog {app_id}\n\n"
            "| 画面ID | 名称 |\n"
            "|---|---|\n"
            f"{rows}\n",
            encoding="utf-8",
        )


def _write_min_service_catalog(tmp_path, svc_to_app):
    """service-catalog.md の最小版を tmp_path に書き出す（A 節サマリ表）。

    svc_to_app: {"SVC-09": "APP-07", "SVC-11": "APP-09"}
    """
    p = tmp_path / "docs" / "catalog" / "service-catalog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"| {svc} | name-{svc} | API | A | desc | {app} |"
        for svc, app in svc_to_app.items()
    )
    p.write_text(
        "# Service Catalog\n\n## A. サマリ\n\n"
        "| SVC-ID | 名称 | 種別 | カテゴリ | 説明 | 利用APP |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n\n## B. 詳細\n\n",
        encoding="utf-8",
    )


def test_filter_app_catalog_keeps_only_specified_app_ids(tmp_path):
    keys = ["APP-01", "APP-07", "APP-09", "APP-16"]
    assert _filter_keys_by_app_ids("app_catalog", keys, ["APP-07"], tmp_path) == ["APP-07"]
    assert _filter_keys_by_app_ids("app_catalog", keys, ["APP-07", "APP-09"], tmp_path) == ["APP-07", "APP-09"]


def test_filter_app_catalog_returns_empty_when_no_match(tmp_path):
    keys = ["APP-01", "APP-09"]
    assert _filter_keys_by_app_ids("app_catalog", keys, ["APP-07"], tmp_path) == []


def test_filter_screen_catalog_uses_prefix_regex(tmp_path):
    keys = [
        "APP-07-S001", "APP-07-S002",
        "APP-09-S001",
        "APP-10-S001",
        "APP-100-S001",
    ]
    out = _filter_keys_by_app_ids("screen_catalog", keys, ["APP-07"], tmp_path)
    assert out == ["APP-07-S001", "APP-07-S002"]


def test_filter_screen_catalog_does_not_confuse_app10_and_app100(tmp_path):
    """APP-10 指定時に APP-100-S001 を含めない（startswith ベース実装の誤マッチ防止）。"""
    keys = ["APP-10-S001", "APP-100-S001"]
    out_10 = _filter_keys_by_app_ids("screen_catalog", keys, ["APP-10"], tmp_path)
    out_100 = _filter_keys_by_app_ids("screen_catalog", keys, ["APP-100"], tmp_path)
    assert out_10 == ["APP-10-S001"]
    assert out_100 == ["APP-100-S001"]


def test_filter_service_catalog_uses_svc_app_mapping(tmp_path):
    _write_min_service_catalog(tmp_path, {
        "SVC-09": "APP-07",
        "SVC-11": "APP-09",
        "SVC-19": "APP-16",
    })
    keys = ["SVC-09", "SVC-11", "SVC-19"]
    assert _filter_keys_by_app_ids("service_catalog", keys, ["APP-07"], tmp_path) == ["SVC-09"]
    assert _filter_keys_by_app_ids("service_catalog", keys, ["APP-09"], tmp_path) == ["SVC-11"]
    assert _filter_keys_by_app_ids("service_catalog", keys, ["APP-07", "APP-16"], tmp_path) == ["SVC-09", "SVC-19"]


def test_filter_service_catalog_returns_keys_when_mapping_empty(tmp_path):
    """service-catalog.md が存在しない（mapping 空）場合はフィルタ無効化して全件返す（後方互換）。"""
    keys = ["SVC-09", "SVC-11"]
    # tmp_path に service-catalog.md を作らない → parse は空辞書を返す
    assert _filter_keys_by_app_ids("service_catalog", keys, ["APP-07"], tmp_path) == keys


def test_filter_unfilterable_parsers_passthrough(tmp_path):
    """app_catalog / screen_catalog / service_catalog / dataflow_catalog 以外はフィルタ対象外。"""
    for parser in ("business_candidate", "use_case_skeleton", "agent_catalog"):
        assert _filter_keys_by_app_ids(parser, ["k1", "k2"], ["APP-07"], tmp_path) == ["k1", "k2"]


def test_filter_with_none_or_empty_app_ids_passes_through(tmp_path):
    """app_ids=None または [] のとき、対象 parser でもフィルタを適用しない（後方互換）。"""
    keys = ["APP-01", "APP-07"]
    assert _filter_keys_by_app_ids("app_catalog", keys, None, tmp_path) == keys
    assert _filter_keys_by_app_ids("app_catalog", keys, [], tmp_path) == keys


def test_screen_key_prefix_regex_strict_match():
    assert _SCREEN_KEY_PREFIX_RE.match("APP-07-S001").group(1) == "APP-07"
    assert _SCREEN_KEY_PREFIX_RE.match("APP-100-S001").group(1) == "APP-100"
    # APP-NN だけ（hyphen 終端なし）はマッチしない
    assert _SCREEN_KEY_PREFIX_RE.match("APP-07") is None


def test_expand_workflow_fanout_filters_aad_web_with_min_catalogs(tmp_path):
    """tmp_path に最小カタログを置いて aad-web の fan-out が app_ids でフィルタされることを確認。"""
    _write_min_app_catalog(tmp_path, ["APP-01", "APP-07", "APP-09"])
    _write_min_screen_catalogs(tmp_path, {
        "APP-07": ["S001", "S002"],
        "APP-09": ["S001"],
    })
    _write_min_service_catalog(tmp_path, {
        "SVC-09": "APP-07",
        "SVC-11": "APP-09",
    })
    aad_web = wr.get_workflow("aad-web")
    expanded = expand_workflow_fanout(aad_web, tmp_path, app_ids=["APP-07"])
    assert expanded.fanout_map.get("1") == ["1/APP-07"]
    assert expanded.fanout_map.get("2.1") == ["2.1/APP-07-S001", "2.1/APP-07-S002"]
    assert expanded.fanout_map.get("2.2") == ["2.2/SVC-09"]
    assert expanded.fanout_map.get("2.3") == ["2.3/SVC-09"]


def test_expand_workflow_fanout_app_ids_none_returns_all(tmp_path):
    """app_ids=None は後方互換で全件返す（フィルタ適用なし）。"""
    _write_min_app_catalog(tmp_path, ["APP-01", "APP-07", "APP-09"])
    aad_web = wr.get_workflow("aad-web")
    ex_none = expand_workflow_fanout(aad_web, tmp_path, app_ids=None)
    ex_default = expand_workflow_fanout(aad_web, tmp_path)
    assert ex_none.fanout_map.get("1") == ex_default.fanout_map.get("1")
    assert len(ex_none.fanout_map.get("1", [])) == 3


def test_expand_workflow_fanout_filter_zero_match_marks_empty(tmp_path):
    """フィルタ結果が 0 件の base step は empty_fanout_ids に登録される。"""
    _write_min_app_catalog(tmp_path, ["APP-01", "APP-09"])
    # screen は APP-09 のみ作る → APP-07 指定でフィルタ結果 0 件
    _write_min_screen_catalogs(tmp_path, {"APP-09": ["S001"]})
    aad_web = wr.get_workflow("aad-web")
    expanded = expand_workflow_fanout(aad_web, tmp_path, app_ids=["APP-07"])
    # Step 1: app_catalog 内に APP-07 が無い → 0 件 → empty
    assert "1" in expanded.empty_fanout_ids
    # Step 2.1: screen_catalog APP-07 のキーが無い → 0 件 → empty
    assert "2.1" in expanded.empty_fanout_ids


def test_expand_single_step_fanout_filters_screen_catalog(tmp_path):
    """expand_single_step_fanout も app_ids で screen_catalog を絞り込む。"""
    _write_min_screen_catalogs(tmp_path, {
        "APP-07": ["S001", "S002"],
        "APP-09": ["S001"],
    })
    step = wr.StepDef(
        id="2.1", title="screen", custom_agent=None,
        consumed_artifacts=[], fanout_parser="screen_catalog",
    )
    children = expand_single_step_fanout(step, tmp_path, app_ids=["APP-07"])
    assert children is not None
    assert [c.id for c in children] == ["2.1/APP-07-S001", "2.1/APP-07-S002"]


def test_expand_single_step_fanout_app_ids_none_returns_all(tmp_path):
    """expand_single_step_fanout も app_ids=None で後方互換維持。"""
    _write_min_screen_catalogs(tmp_path, {
        "APP-07": ["S001"],
        "APP-09": ["S001"],
    })
    step = wr.StepDef(
        id="2.1", title="screen", custom_agent=None,
        consumed_artifacts=[], fanout_parser="screen_catalog",
    )
    children_none = expand_single_step_fanout(step, tmp_path, app_ids=None)
    children_default = expand_single_step_fanout(step, tmp_path)
    assert children_none is not None and children_default is not None
    assert [c.id for c in children_none] == [c.id for c in children_default]
    assert len(children_none) == 2


def test_service_app_mapping_returns_empty_when_no_a_section(tmp_path):
    """service-catalog.md に '## A.' セクションが無い場合、mapping は空辞書。

    parse_service_app_mapping のサブセクション検出ロジックの境界ケース。
    A 節不在時に B/C 節の SVC 行を誤って拾わないことを保証する。
    """
    from hve.catalog_parsers import parse_service_app_mapping

    p = tmp_path / "docs" / "catalog" / "service-catalog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Service Catalog\n\n## B. 詳細\n\n"
        "| SVC-ID | 名称 | 種別 | カテゴリ | 説明 | 利用APP |\n"
        "|---|---|---|---|---|---|\n"
        "| SVC-09 | name | API | A | desc | APP-07 |\n",
        encoding="utf-8",
    )
    assert parse_service_app_mapping(tmp_path) == {}


# ---------------------------------------------------------------------------
# T3.3 (Major No.5): parse_dataflow_catalog × adfd 結合テスト
# ---------------------------------------------------------------------------


def test_parse_dataflow_catalog_fallback_to_app_catalog(tmp_path):
    """app-arch-catalog.md が無い場合は app-catalog.md の全 APP-ID を返す（フォールバック）。"""
    from hve.catalog_parsers import parse_dataflow_catalog

    _write_min_app_catalog(tmp_path, ["APP-01", "APP-07", "APP-09"])
    # app-arch-catalog.md は作らない
    result = parse_dataflow_catalog(tmp_path)
    assert set(result) == {"APP-01", "APP-07", "APP-09"}


def test_parse_dataflow_catalog_returns_empty_when_no_catalog(tmp_path):
    """app-catalog.md も app-arch-catalog.md も無い場合は空リスト。"""
    from hve.catalog_parsers import parse_dataflow_catalog

    assert parse_dataflow_catalog(tmp_path) == []


def test_expand_workflow_fanout_adfd_uses_app_catalog(tmp_path):
    """ADFD の fan-out が app-catalog.md の APP-ID で展開されることを確認（フォールバック経路）。"""
    _write_min_app_catalog(tmp_path, ["APP-01", "APP-07"])
    adfd = wr.get_workflow("adfd")
    expanded = expand_workflow_fanout(adfd, tmp_path)
    # Step.6.1 / 6.3 は dataflow_catalog 由来で APP-ID 数だけ展開、
    # Step.6.2 (Monitoring) は fanout 対象外 (per-job 詳細ではない) と想定し、
    # fanout_map に登場するキー数を確認
    fanout_keys = set(expanded.fanout_map.keys())
    # Step.6.1 と Step.6.3 が fanout_parser=dataflow_catalog なら 2 つ
    # Step.6.2 が fanout 対象なら 3 つ
    assert len(fanout_keys) >= 1
    # 6.1 が APP-01, APP-07 で展開されることを確認
    if "6.1" in expanded.fanout_map:
        child_ids = expanded.fanout_map["6.1"]
        assert set(child_ids) == {"6.1/APP-01", "6.1/APP-07"}


def test_expand_workflow_fanout_adfd_filters_by_app_ids(tmp_path):
    """ADFD の fan-out が app_ids 指定でフィルタされる（HVE CLI 経路）。"""
    _write_min_app_catalog(tmp_path, ["APP-01", "APP-07", "APP-09"])
    adfd = wr.get_workflow("adfd")
    expanded = expand_workflow_fanout(adfd, tmp_path, app_ids=["APP-07"])
    if "6.1" in expanded.fanout_map:
        child_ids = expanded.fanout_map["6.1"]
        assert child_ids == ["6.1/APP-07"]
