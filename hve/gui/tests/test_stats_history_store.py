"""StatsHistoryStore のテスト（T4）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hve.gui.stats_history_store import StatsHistoryStore, SCHEMA_VERSION
from hve.gui.workbench_state import StepStatsSnapshot, WorkflowStatsSnapshot


def _wf(workflow_id="wf1", run_id="r1", steps=None, finalized=False):
    return WorkflowStatsSnapshot(
        workflow_id=workflow_id,
        workflow_name="A",
        run_id=run_id,
        model="gpt-x",
        started_at=0.0,
        finished_at=1.0 if finalized else None,
        elapsed_sec=1.0 if finalized else None,
        context_current=100,
        context_limit=1000,
        finalized=finalized,
        steps=steps or [],
    )


def _step(step_id="s1", status="done"):
    return StepStatsSnapshot(
        step_id=step_id,
        step_title="S",
        status=status,
        model="gpt-x",
        started_at=0.0,
        finished_at=1.0,
        elapsed_sec=1.0,
        context_current=50,
        context_limit=1000,
        tool_counts={"read_file": 2},
        skill_counts={"sk": 1},
    )


def test_save_step_snapshot_creates_file(tmp_path: Path):
    store = StatsHistoryStore(tmp_path)
    wf = _wf(steps=[_step()])
    store.save_step_snapshot(wf, wf.steps[0])

    path = store.file_path("r1")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["workflows"]) == 1
    assert data["workflows"][0]["workflow_id"] == "wf1"
    assert data["workflows"][0]["steps"][0]["step_id"] == "s1"


def test_save_workflow_upserts_same_entry(tmp_path: Path):
    store = StatsHistoryStore(tmp_path)
    wf = _wf(steps=[_step("s1")])
    store.save_step_snapshot(wf, wf.steps[0])
    wf.steps.append(_step("s2"))
    store.save_step_snapshot(wf, wf.steps[1])
    wf.finalized = True
    wf.finished_at = 5.0
    wf.elapsed_sec = 5.0
    store.save_workflow_snapshot(wf)

    data = json.loads(store.file_path("r1").read_text(encoding="utf-8"))
    assert len(data["workflows"]) == 1
    assert len(data["workflows"][0]["steps"]) == 2
    assert data["workflows"][0]["finalized"] is True


def test_multiple_workflows_in_same_run(tmp_path: Path):
    store = StatsHistoryStore(tmp_path)
    store.save_workflow_snapshot(_wf(workflow_id="wf1", finalized=True))
    store.save_workflow_snapshot(_wf(workflow_id="wf2", finalized=True))
    data = json.loads(store.file_path("r1").read_text(encoding="utf-8"))
    ids = [w["workflow_id"] for w in data["workflows"]]
    assert ids == ["wf1", "wf2"]


def test_corrupt_existing_file_is_recreated(tmp_path: Path):
    store = StatsHistoryStore(tmp_path)
    p = store.file_path("r1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json{", encoding="utf-8")
    store.save_workflow_snapshot(_wf(finalized=True))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["workflows"]) == 1


def test_save_does_not_raise_on_oserror(tmp_path: Path, monkeypatch):
    store = StatsHistoryStore(tmp_path)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("hve.gui.stats_history_store.tempfile.mkstemp", boom)
    # 例外が伝播しないこと
    store.save_workflow_snapshot(_wf())
    store.save_step_snapshot(_wf(steps=[_step()]), _step())
