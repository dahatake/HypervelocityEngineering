"""ADR-0002 T3D: fan-out サブステップの Resume 動作検証。

実 Copilot SDK は呼ばず、以下を確認する:
1. make_session_id() が fan-out step_id ``1/D01`` から決定論的 session_id を生成する
2. RunState に fan-out 子の StepState を保存・復元できる
3. DAGExecutor で完了/失敗を事前注入した状態で execute() を呼ぶと、
   - completed の子は再実行されない
   - failed の子は再実行される（後続 join Step 2 は failed 伝搬で起動しない）
   - 未実行の子は新規に実行される
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from hve import workflow_registry as wr
from hve.console import Console
from hve.dag_executor import DAGExecutor
from hve.run_state import RunState, StepState, make_session_id, DEFAULT_SESSION_ID_PREFIX


# ---------------------------------------------------------------------------
# make_session_id: fan-out step_id 対応
# ---------------------------------------------------------------------------

def test_make_session_id_normalizes_fanout_step_id():
    """fan-out 合成 step_id ``1/D01`` から決定論的 session_id を生成する。"""
    sid_a = make_session_id("20260511T000000-abc", "1/D01")
    sid_b = make_session_id("20260511T000000-abc", "1/D01")
    assert sid_a == sid_b  # 決定論的
    # `/` がパス安全文字に正規化されている（`/` を含まない）
    assert "/" not in sid_a
    assert "D01" in sid_a
    assert sid_a.startswith(f"{DEFAULT_SESSION_ID_PREFIX}-20260511T000000-abc-step-")


def test_make_session_id_distinct_per_fanout_key():
    """異なる fan-out キーは異なる session_id を生成する。"""
    sid_d01 = make_session_id("test-run", "1/D01")
    sid_d02 = make_session_id("test-run", "1/D02")
    assert sid_d01 != sid_d02
    assert "D01" in sid_d01
    assert "D02" in sid_d02


# ---------------------------------------------------------------------------
# RunState: fan-out 子の永続化
# ---------------------------------------------------------------------------

def test_run_state_can_persist_fanout_children(tmp_path):
    """fan-out 子 step_id (``1/D01``) を含む StepState を保存・ロードできる。"""
    run_id = "20260511T000000-test01"
    state = RunState.new(
        run_id=run_id,
        workflow_id="akm",
        params={},
        selected_step_ids=["1", "2"] + [f"1/D{n:02d}" for n in range(1, 22)],
        work_dir=tmp_path,
    )
    # 21 子 + Step 2 を登録
    for n in range(1, 22):
        key = f"D{n:02d}"
        cid = f"1/{key}"
        state.step_states[cid] = StepState(
            status="completed" if n <= 5 else ("failed" if n <= 10 else "pending"),
            session_id=make_session_id(state.run_id, cid),
        )
    state.save()

    # ロードして検証
    loaded = RunState.load(run_id, work_dir=tmp_path)
    assert "1/D01" in loaded.step_states
    assert loaded.step_states["1/D01"].status == "completed"
    assert loaded.step_states["1/D06"].status == "failed"
    assert loaded.step_states["1/D21"].status == "pending"
    # session_id が決定論的に再生成可能
    expected_sid = make_session_id(state.run_id, "1/D01")
    assert loaded.step_states["1/D01"].session_id == expected_sid


# ---------------------------------------------------------------------------
# DAGExecutor: completed/failed 事前注入で fan-out resume 動作
# ---------------------------------------------------------------------------

def test_dag_executor_skips_completed_fanout_children(tmp_path):
    """completed 状態の子は再実行されない。"""
    akm = wr.get_workflow("akm")
    calls: List[Dict[str, Any]] = []

    async def run_step_fn(**kwargs):
        calls.append(kwargs)
        return True

    console = Console(quiet=True, verbosity=0)
    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_step_fn,
        active_step_ids={"1", "2"},
        max_parallel=21,
        console=console,
        repo_root=tmp_path,
    )
    # Resume シミュレーション: D01〜D05 は完了済み
    for n in range(1, 6):
        executor.completed.add(f"1/D{n:02d}")
    asyncio.run(executor.execute())

    called_ids = {c["step_id"] for c in calls}
    # 完了済みは呼ばれていない
    for n in range(1, 6):
        assert f"1/D{n:02d}" not in called_ids
    # 残り 16 子 + Step 2 は呼ばれた
    for n in range(6, 22):
        assert f"1/D{n:02d}" in called_ids
    assert "2" in called_ids
    assert len(calls) == 17


def test_dag_executor_failed_fanout_blocks_downstream(tmp_path):
    """failed 状態の子があると後続 join Step は起動しない（N-1）。"""
    akm = wr.get_workflow("akm")
    calls: List[Dict[str, Any]] = []

    async def run_step_fn(**kwargs):
        calls.append(kwargs)
        return True

    console = Console(quiet=True, verbosity=0)
    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_step_fn,
        active_step_ids={"1", "2"},
        max_parallel=21,
        console=console,
        repo_root=tmp_path,
    )
    # Resume シミュレーション: D01 は失敗扱い、D02〜D05 完了、残り未実行
    executor.failed.add("1/D01")
    for n in range(2, 6):
        executor.completed.add(f"1/D{n:02d}")
    asyncio.run(executor.execute())

    called_ids = {c["step_id"] for c in calls}
    # D01 は再実行されない（failed は確定）
    assert "1/D01" not in called_ids
    # D02〜D05 も再実行されない（completed）
    for n in range(2, 6):
        assert f"1/D{n:02d}" not in called_ids
    # D06〜D21 は実行される
    for n in range(6, 22):
        assert f"1/D{n:02d}" in called_ids
    # Step 2 は failed 伝搬で起動しない（blocked）
    assert "2" not in called_ids
