"""ADR-0002 AKM 21 並列 DRY-RUN E2E テスト。

実 Copilot SDK を呼ばずに、AKM ワークフローを DAGExecutor 経由で実行し、
fan-out 子ステップが 21 件並列起動されることを確認する。
"""
from __future__ import annotations

import asyncio
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import pytest

from hve import workflow_registry as wr
from hve.console import Console
from hve.dag_executor import DAGExecutor


def test_akm_dryrun_invokes_21_children(tmp_path):
    akm = wr.get_workflow("akm")
    calls: List[Dict[str, Any]] = []

    async def run_step_fn(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0.001)
        return True

    console = Console(quiet=False, verbosity=1)
    console.set_run_id("test-run-AKM")

    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_step_fn,
        active_step_ids={"1", "2"},
        max_parallel=21,
        console=console,
        repo_root=tmp_path,
    )
    results = asyncio.run(executor.execute())

    # 21 子 + Step 2 = 22 ステップ実行
    assert len(calls) == 22
    child_ids = {c["step_id"] for c in calls if "/" in c["step_id"]}
    assert len(child_ids) == 21
    assert "1/D01" in child_ids
    assert "1/D21" in child_ids
    # join Step 2 が最後に実行されている (depends_on を満たす)
    assert "2" in {c["step_id"] for c in calls}
    # 結果がすべて success
    for cid in child_ids:
        assert results[cid].success
    assert results["2"].success


def test_akm_dryrun_stderr_emits_21_step_starts(tmp_path, capfd):
    """stderr に 21 件の step_start (fanout_key D01..D21) JSON が出ること。"""
    akm = wr.get_workflow("akm")

    # 構造化 JSON は verbose レベル (verbosity=3) のみで出力される
    console = Console(quiet=False, verbosity=3)
    console.set_run_id("test-run-stderr")

    async def run_step_fn(**kwargs):
        # StepRunner.run_step と同じく step_start を発火
        console.step_start(kwargs["step_id"], kwargs["title"], agent=kwargs.get("custom_agent"))
        console.step_end(kwargs["step_id"], "success", elapsed=0.0)
        return True

    executor = DAGExecutor(
        workflow=akm,
        run_step_fn=run_step_fn,
        active_step_ids={"1", "2"},
        max_parallel=21,
        console=console,
        repo_root=tmp_path,
    )
    asyncio.run(executor.execute())

    err = capfd.readouterr().err
    # stderr に JSON 行が含まれる
    step_start_lines = [
        line for line in err.splitlines()
        if line.startswith("{") and '"event": "step_start"' in line
    ]
    parsed = [json.loads(l) for l in step_start_lines]
    fanout_keys = {p["fanout_key"] for p in parsed if "fanout_key" in p}
    assert len(fanout_keys) == 21
    assert "D01" in fanout_keys
    assert "D21" in fanout_keys
    # run_id が含まれる
    for p in parsed:
        if "fanout_key" in p:
            assert p.get("run_id") == "test-run-stderr"
            assert p.get("parent_step_id") == "1"
