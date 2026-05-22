"""FooterWidget の統計情報拡張に関する単体テスト。

- WorkbenchState.record_tool_call / record_skill_invoked のカウント挙動
- workbench_logger による Context / Tool / Skill ログ行のパース
- FooterWidget のレンダリング（項目名/値の色分けと Top-N 集計）
"""

from __future__ import annotations

import os
import sys

import pytest

# ヘッドレス環境用に offscreen platform を強制
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState  # noqa: E402
from hve.gui.workbench_logger import process_log_line  # noqa: E402
from hve.gui.workbench_widgets import FooterWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _make_state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r1", model="gpt-x")


def test_record_tool_call_per_step():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_tool_call("step-1", "edit_file")
    s.record_tool_call("step-1", "edit_file")
    s.record_tool_call("step-1", "grep")
    assert s.current_tool_counts() == {"edit_file": 2, "grep": 1}


def test_record_skill_invoked_per_step():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_skill_invoked("step-1", "task-questionnaire")
    s.record_skill_invoked("step-1", "task-questionnaire")
    assert s.current_skill_counts() == {"task-questionnaire": 2}


def test_counts_isolated_between_steps():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_tool_call("step-1", "edit_file")
    s.set_step_status("step-1", "done")  # current=None, last_known=step-1
    s.set_step_status("step-2", "running")
    s.record_tool_call("step-2", "bash")
    assert s.current_tool_counts() == {"bash": 1}


def test_last_known_step_kept_after_done():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_tool_call("step-1", "edit_file")
    s.set_step_status("step-1", "done")
    # current_running_step_id is None, but last_known_step_id keeps display
    assert s.current_tool_counts() == {"edit_file": 1}


def test_record_tool_call_uses_current_when_step_id_missing():
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.record_tool_call(None, "edit_file")
    s.record_tool_call("", "grep")
    assert s.current_tool_counts() == {"edit_file": 1, "grep": 1}


def test_record_tool_call_ignored_without_any_step():
    s = _make_state()
    # No running step at all -> no recording
    s.record_tool_call(None, "edit_file")
    assert s.tool_counts_by_step == {}


def test_parse_context_usage_line():
    s = _make_state()
    line = "  📏 [step-1] Context: 1234/8000 (15%) msgs=10"
    process_log_line(s, line)
    assert s.context_current == 1234
    assert s.context_limit == 8000
    assert s.context_msgs == 10


def test_parse_tool_invoke_stats_event():
    """runner が stats_event("tool_invoked", ...) を出した際の GUI 集計。"""
    s = _make_state()
    s.set_step_status("step-1", "running")
    process_log_line(
        s,
        '[hve:stats] {"kind":"tool_invoked","step":"step-1","tool_name":"edit_file"}',
    )
    process_log_line(
        s,
        '[hve:stats] {"kind":"tool_invoked","step":"step-1","tool_name":"edit_file"}',
    )
    process_log_line(
        s,
        '[hve:stats] {"kind":"tool_invoked","step":"step-1","tool_name":"bash"}',
    )
    assert s.current_tool_counts() == {"edit_file": 2, "bash": 1}


def test_legacy_tool_text_pattern_is_ignored():
    """旧 `🔧` テキストパターンは集計経路から削除済み。"""
    s = _make_state()
    s.set_step_status("step-1", "running")
    process_log_line(s, "  🔧 [step-1] edit_file(1) path/to/file.py")
    assert s.current_tool_counts() == {}


def test_parse_skill_invoke_stats_event():
    """console.skill_invoked / SKILL.md パス検出からの stats_event を GUI が集計。"""
    s = _make_state()
    s.set_step_status("step-1", "running")
    process_log_line(
        s,
        '[hve:stats] {"kind":"skill_invoked","step":"step-1","name":"task-questionnaire"}',
    )
    process_log_line(
        s,
        '[hve:stats] {"kind":"skill_invoked","step":"step-1","name":"task-dag-planning"}',
    )
    process_log_line(
        s,
        '[hve:stats] {"kind":"skill_invoked","step":"step-1","name":"task-questionnaire"}',
    )
    assert s.current_skill_counts() == {
        "task-questionnaire": 2,
        "task-dag-planning": 1,
    }


def test_step_status_stats_event_updates_running_step():
    """console.step_start が出す stats_event(step_status, running) で
    current_running_step_id が更新されることを検証。"""
    s = _make_state()
    process_log_line(
        s,
        '[hve:stats] {"kind":"step_status","step":"2.2","status":"running","title":"画面定義書"}',
    )
    assert s.current_running_step_id == "2.2"
    assert s.last_known_step_id == "2.2"
    # done へ遷移しても last_known は保持される
    process_log_line(
        s,
        '[hve:stats] {"kind":"step_status","step":"2.2","status":"done"}',
    )
    assert s.current_running_step_id is None
    assert s.last_known_step_id == "2.2"


def test_footer_widget_renders_label_and_value(qapp):
    s = _make_state()
    s.set_step_status("step-1", "running")
    s.set_context(1000, 4000, 5)
    s.record_tool_call("step-1", "edit_file")
    s.record_tool_call("step-1", "edit_file")
    s.record_tool_call("step-1", "grep")
    s.record_skill_invoked("step-1", "task-questionnaire")

    w = FooterWidget(s)
    html = w._label.text()

    # 項目名は濃色 bold、値は中間色で別 span に分離されていること
    assert "Context" in html
    assert "Tools (Step)" in html
    assert "Skills (Step)" in html
    assert "font-weight:bold" in html
    assert FooterWidget._LABEL_COLOR in html
    assert FooterWidget._VALUE_COLOR in html

    # Top-N 集計表現
    assert "edit_file×2" in html
    assert "grep×1" in html
    assert "task-questionnaire×1" in html


def test_footer_widget_topn_truncation(qapp):
    s = _make_state()
    s.set_step_status("step-1", "running")
    for i in range(FooterWidget._TOPN + 3):
        s.record_tool_call("step-1", f"tool_{i}")
    w = FooterWidget(s)
    html = w._label.text()
    assert "+3 more" in html


def test_footer_widget_dash_when_empty(qapp):
    s = _make_state()
    w = FooterWidget(s)
    html = w._label.text()
    # Tools/Skills は - 表示
    assert "Tools (Step)" in html
    assert "Skills (Step)" in html
    assert ">-<" in html  # value span with dash
