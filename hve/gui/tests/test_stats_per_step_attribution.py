"""FR-RTO-07: `[hve:stats]` イベントの Step 別帰属テスト。

`workbench_logger.process_log_line` が、構造化イベントの `step` フィールドを
`WorkbenchState` の Step 別バケットへ正しく振り分けることを固定する。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_logger import process_log_line  # noqa: E402
from hve.gui.workbench_state import WorkbenchState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf1", run_id="r1", model="unknown")


def _stats(payload: dict) -> str:
    return "[hve:stats] " + json.dumps(payload, ensure_ascii=False)


def test_session_usage_detail_records_step_context(qapp):
    """`session_usage_detail` の `step` で Context が Step 別に記録される。"""
    s = _state()
    process_log_line(s, _stats({
        "kind": "session_usage_detail", "step": "1",
        "current": 1000, "limit": 10000, "msgs": 5,
    }))
    process_log_line(s, _stats({
        "kind": "session_usage_detail", "step": "3.1",
        "current": 7000, "limit": 10000, "msgs": 9,
    }))

    assert s.context_by_step["1"] == (1000, 10000)
    assert s.context_by_step["3.1"] == (7000, 10000)


def test_session_usage_detail_keeps_latest_value_per_step(qapp):
    """同一 Step の再送では最新値で上書きする。"""
    s = _state()
    for current in (1000, 2000, 3000):
        process_log_line(s, _stats({
            "kind": "session_usage_detail", "step": "1",
            "current": current, "limit": 10000, "msgs": 1,
        }))

    assert s.context_by_step["1"] == (3000, 10000)


def test_usage_credit_records_step_credit(qapp):
    """`usage_credit` の `step` で AI Credit が Step 別に記録される。"""
    s = _state()
    process_log_line(s, _stats({
        "kind": "usage_credit", "step": "1",
        "api_call_id": "a1", "model": "claude-opus-5", "nano_aiu": 1_000_000_000,
    }))
    process_log_line(s, _stats({
        "kind": "usage_credit", "step": "3.1",
        "api_call_id": "a2", "model": "claude-opus-5", "nano_aiu": 2_000_000_000,
    }))

    assert s.aiu_nano_by_step["1"] == 1_000_000_000
    assert s.aiu_nano_by_step["3.1"] == 2_000_000_000
    assert s.sdk_aiu_total_nano == 3_000_000_000


def test_usage_credit_records_step_model(qapp):
    """モデル別回数を `usage_credit` の `step` / `model` から記録する。

    `assistant_usage` ではなく `usage_credit` を源とすることで、SDK Fleet mode 経路
    （`usage_credit` のみ発火）でも Model 列が埋まる。
    """
    s = _state()
    for i, model in enumerate(("claude-opus-5", "claude-opus-5", "gpt-5.6-terra")):
        process_log_line(s, _stats({
            "kind": "usage_credit", "step": "1",
            "api_call_id": f"a{i}", "model": model, "nano_aiu": 1,
        }))
    process_log_line(s, _stats({
        "kind": "usage_credit", "step": "3.1",
        "api_call_id": "b1", "model": "gpt-5.6-terra", "nano_aiu": 1,
    }))

    assert s.model_counts_by_step["1"] == {"claude-opus-5": 2, "gpt-5.6-terra": 1}
    assert s.model_counts_by_step["3.1"] == {"gpt-5.6-terra": 1}


def test_assistant_usage_does_not_double_count_step_model(qapp):
    """`assistant_usage` はモデル別回数を記録しない（`usage_credit` との二重計上防止）。"""
    s = _state()
    process_log_line(s, _stats({
        "kind": "assistant_usage", "step": "1",
        "model": "claude-opus-5", "input": 10, "output": 5,
    }))

    assert s.model_counts_by_step == {}
    # グローバルの現在モデル（Footer 用）は従来どおり更新される。
    assert s.model == "claude-opus-5"


def test_step_less_events_do_not_attribute_to_running_step(qapp):
    """`step` が空のイベントを実行中 Step へ誤帰属させない（Fleet wave 対策）。"""
    s = _state()
    s.set_step_status("2/APP-014", "running")

    process_log_line(s, _stats({
        "kind": "usage_credit", "step": "",
        "api_call_id": "f1", "model": "claude-opus-5", "nano_aiu": 5_000_000_000,
    }))
    process_log_line(s, _stats({
        "kind": "session_usage_detail", "step": "",
        "current": 9999, "limit": 10000, "msgs": 3,
    }))
    process_log_line(s, _stats({
        "kind": "assistant_usage", "step": "",
        "model": "claude-opus-5", "input": 1, "output": 1,
    }))

    assert s.aiu_nano_by_step == {}
    assert s.context_by_step == {}
    assert s.model_counts_by_step == {}
    # Workflow 累積へは計上される（FR-RTO-07）。
    assert s.sdk_aiu_total_nano == 5_000_000_000


def test_usage_credit_dedupe_is_shared_with_step_bucket(qapp):
    """同一 api_call_id の再送は Step 別バケットでも二重計上しない。"""
    s = _state()
    line = _stats({
        "kind": "usage_credit", "step": "1",
        "api_call_id": "a1", "model": "m", "nano_aiu": 1_000_000_000,
    })
    process_log_line(s, line)
    process_log_line(s, line)

    assert s.aiu_nano_by_step["1"] == 1_000_000_000
    assert s.sdk_aiu_total_nano == 1_000_000_000
