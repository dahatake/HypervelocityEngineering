"""統計詳細ポップアップ・SDK イベント取り込みに関する単体テスト。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState  # noqa: E402
from hve.gui.workbench_logger import is_stats_line, process_log_line  # noqa: E402
from hve.gui.stats_detail_popup import (  # noqa: E402
    StatsDetailPopup,
    build_snapshot,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="gpt-x")


# ----------------------------------------------------------------------
# [hve:stats] JSON 行のパース
# ----------------------------------------------------------------------


def test_parse_session_usage_detail():
    s = _make_state()
    line = (
        '[hve:stats] {"kind":"session_usage_detail","step":"s1",'
        '"current":140700,"limit":1000000,"msgs":24,'
        '"system":53000,"tool_definitions":37000,"conversation":24000}'
    )
    process_log_line(s, line)
    assert s.context_system_tokens == 53000
    assert s.context_tool_definitions_tokens == 37000
    assert s.context_conversation_tokens == 24000


def test_parse_session_usage_detail_partial_keeps_old():
    s = _make_state()
    s.apply_session_usage_detail(system=100, tool_definitions=200, conversation=300)
    process_log_line(
        s,
        '[hve:stats] {"kind":"session_usage_detail","step":"s1","system":150}',
    )
    assert s.context_system_tokens == 150
    # None フィールドは上書きしない
    assert s.context_tool_definitions_tokens == 200
    assert s.context_conversation_tokens == 300


def test_parse_assistant_usage_accumulates():
    s = _make_state()
    process_log_line(
        s,
        '[hve:stats] {"kind":"assistant_usage","model":"gpt-5",'
        '"input":100,"output":50,"reasoning":10,"cache_read":80,"cache_write":5,'
        '"inter_token_latency_ms":12.5,'
        '"token_details":[{"type":"chat","count":40},{"type":"premium","count":5}]}',
    )
    process_log_line(
        s,
        '[hve:stats] {"kind":"assistant_usage","model":"gpt-5",'
        '"input":200,"output":100,"token_details":[{"type":"chat","count":60}]}',
    )
    assert s.assistant_input_tokens_total == 300
    assert s.assistant_output_tokens_total == 150
    assert s.assistant_reasoning_tokens_total == 10
    assert s.assistant_cache_read_total == 80
    assert s.assistant_cache_write_total == 5
    assert s.assistant_usage_count == 2
    assert s.assistant_inter_token_latency_ms_last == 12.5
    assert s.billing_token_totals == {"chat": 100, "premium": 5}
    assert s.model == "gpt-5"


def test_parse_assistant_ttft():
    s = _make_state()
    process_log_line(s, '[hve:stats] {"kind":"assistant_ttft","ttft_ms":820.0}')
    process_log_line(s, '[hve:stats] {"kind":"assistant_ttft","ttft_ms":640.0}')
    assert s.ttft_first_ms == 820.0
    assert s.ttft_last_ms == 640.0
    assert s.ttft_count == 2
    assert abs(s.ttft_sum_ms - 1460.0) < 0.001


def test_parse_compaction_complete():
    s = _make_state()
    process_log_line(
        s,
        '[hve:stats] {"kind":"compaction_complete","pre":8000,"post":3000,"removed":5000}',
    )
    assert s.compaction_count == 1
    assert s.compaction_tokens_removed_total == 5000


def test_parse_permission_count_takes_max():
    s = _make_state()
    process_log_line(s, '[hve:stats] {"kind":"permission_count","count":3}')
    process_log_line(s, '[hve:stats] {"kind":"permission_count","count":2}')
    # 累積カウンタなので max を保つ
    assert s.permission_count == 3


def test_stats_event_is_not_appended_to_body(monkeypatch):
    """stats 行は user_action にも state.body にも追加されない（機械可読出力のため）。"""
    s = _make_state()
    initial_actions = len(s.user_actions)
    initial_body = len(s.body)
    process_log_line(
        s,
        '[hve:stats] {"kind":"assistant_ttft","ttft_ms":100.0}',
    )
    assert len(s.user_actions) == initial_actions
    assert len(s.body) == initial_body


def test_is_stats_line_matches():
    """is_stats_line: stats 行はマッチ・通常行は非マッチ。"""
    assert is_stats_line('[hve:stats] {"kind":"assistant_ttft","ttft_ms":100.0}')
    # タイムスタンプ・インデント付きでもマッチ
    assert is_stats_line(
        '[13:49:27]   [hve:stats] {"kind":"tool_invoked","tool_name":"view"}'
    )
    # 通常ログ行は非マッチ
    assert not is_stats_line('[13:49:27] step-1: INFO: 通常ログメッセージ')
    assert not is_stats_line('')
    # `[hve:stats]` 文字列を含むが JSON が無い行は非マッチ
    assert not is_stats_line('about [hve:stats] format')


# ----------------------------------------------------------------------
# build_snapshot
# ----------------------------------------------------------------------


def test_build_snapshot_returns_all_sections():
    s = _make_state()
    sections, header = build_snapshot(s)
    titles = [sec.title for sec in sections]
    assert titles == [
        "System",
        "User Context",
        "Reasoning & Cache",
        "Latency",
        "Step Activity",
        "Compaction",
        "Permission",
        "その他",
    ]
    assert header == {"current": 0, "limit": 0, "pct": 0.0}


def test_build_snapshot_dash_for_unknown_values():
    s = _make_state()
    sections, _ = build_snapshot(s)
    # System Instructions などは SDK 未取得時 "-" を含む
    sys_section = next(sec for sec in sections if sec.title == "System")
    sys_text = " | ".join(it.value for it in sys_section.items)
    assert "-" in sys_text


def test_build_snapshot_other_diff_computed():
    s = _make_state()
    s.set_context(100_000, 1_000_000, 10)
    s.apply_session_usage_detail(system=30_000, tool_definitions=10_000, conversation=40_000)
    sections, _ = build_snapshot(s)
    other = next(sec for sec in sections if sec.title == "その他")
    # 100000 - (30000+10000) - 40000 = 20000
    assert "20,000" in other.items[0].value


def test_build_snapshot_other_dash_when_unknown():
    s = _make_state()
    s.set_context(100_000, 1_000_000, 10)
    # 詳細未提供 → その他は "-"
    sections, _ = build_snapshot(s)
    other = next(sec for sec in sections if sec.title == "その他")
    assert other.items[0].value == "-"


def test_build_snapshot_step_activity_uses_current_step():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_tool_call("step-1", "edit_file")
    s.record_skill_invoked("step-1", "task-questionnaire")
    sections, _ = build_snapshot(s)
    sa = next(sec for sec in sections if sec.title == "Step Activity")
    vals = {it.label: it.value for it in sa.items}
    assert vals["対象 Step"] == "step-1"
    assert "edit_file×1" in vals["Tools (Step)"]
    assert "task-questionnaire×1" in vals["Skills (Step)"]


# ----------------------------------------------------------------------
# StatsDetailPopup
# ----------------------------------------------------------------------


def test_popup_constructs_and_renders(qapp):
    s = _make_state()
    s.set_context(140_700, 1_000_000, 24)
    s.apply_session_usage_detail(system=53_000, tool_definitions=37_000, conversation=24_000)
    s.apply_assistant_usage(
        input_tokens=100,
        output_tokens=50,
        cache_read=80,
        token_details=[{"type": "chat", "count": 30}],
    )
    s.apply_ttft(820.0)

    popup = StatsDetailPopup(s)
    # ヘッダにトークン数が含まれる
    assert popup.findChild  # smoke
    # 表示文字列に値が含まれていることを確認
    labels = [w.text() for w in popup.findChildren(type(popup.findChild(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)))]
    text = " | ".join(labels)
    assert "140,700" in text
    assert "1,000,000" in text
    assert "53,000" in text  # System
    assert "37,000" in text  # Tool Definitions
    assert "820.0 ms" in text  # TTFT first
    assert "chat×30" in text  # billing
    popup.close()
