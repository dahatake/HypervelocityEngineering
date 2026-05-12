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
                "batch_job_catalog", "agent_catalog"}
    assert expected.issubset(KNOWN_PARSERS)


def test_all_workflows_fanout_parsers_are_known():
    """全 WorkflowDef の fanout_parser 名が catalog_parsers に登録されている。"""
    for wf_id in ("ard", "aas", "aad-web", "asdw-web", "abd", "abdv",
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
