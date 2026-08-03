"""StatsHistoryView のテスト（T8）。"""

from __future__ import annotations

import io
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.stats_history_view import (  # noqa: E402
    COL_AI_CREDIT,
    COL_CONTEXT,
    COL_ELAPSED,
    COL_MODEL,
    COL_NAME,
    COL_SKILLS,
    COL_TOOLS,
    StatsHistoryView,
    _agg_workflow_counts,
    _aiu_sort_key,
    _compute_step_prev_map,
    _csv_aiu,
    _csv_counts_topn,
    _csv_pct,
    _csv_safe_int,
    _fmt_aiu,
    _fmt_context,
    _fmt_counts,
    _fmt_elapsed,
    _sanitize_csv_cell,
    _sorted_steps_by_finish,
    _step_aiu_delta_nano,
    build_csv,
)
from hve.gui.workbench_state import (  # noqa: E402
    StepView,
    WorkbenchState,
    WorkflowStatsSnapshot,
    StepStatsSnapshot,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _state_with_history() -> WorkbenchState:
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    s.steps.append(StepView(id="s1", title="Step 1"))
    s.update_identity(workflow_id="wf1", workflow_name="WF A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_context(1000, 10000, 5)
    s.record_tool_call("s1", "read_file")
    s.record_tool_call("s1", "read_file")
    s.record_skill_invoked("s1", "task-questionnaire")
    s.set_step_status("s1", "done")
    s.mark_all_done()
    return s


# ----------------------------------------------------------------------
# フォーマッタ
# ----------------------------------------------------------------------


def test_fmt_context():
    assert _fmt_context(None, None) == "-"
    assert _fmt_context(0, 0) == "0"
    assert _fmt_context(1000, 10000) == "1,000 / 10,000 (10%)"


def test_fmt_elapsed():
    assert _fmt_elapsed(None) == "-"
    assert _fmt_elapsed(0) == "00:00:00"
    assert _fmt_elapsed(3661) == "01:01:01"


def test_fmt_counts_topn_and_more():
    counts = {f"t{i}": (10 - i) for i in range(8)}
    text = _fmt_counts(counts, top=5)
    # Top 5 (t0..t4) のみ + "+3 more"
    assert "t0×10" in text
    assert "t4×6" in text
    assert "t5" not in text
    assert "+3 more" in text


def test_fmt_counts_empty():
    assert _fmt_counts({}) == "-"


def test_agg_workflow_counts():
    wf = WorkflowStatsSnapshot(
        workflow_id="w", workflow_name="", run_id="r", model="m", started_at=0.0,
        steps=[
            StepStatsSnapshot(
                step_id="s1", step_title="", status="done", model="m",
                started_at=0, finished_at=1, elapsed_sec=1,
                context_current=None, context_limit=None,
                tool_counts={"a": 1, "b": 2}, skill_counts={"x": 1},
            ),
            StepStatsSnapshot(
                step_id="s2", step_title="", status="done", model="m",
                started_at=1, finished_at=2, elapsed_sec=1,
                context_current=None, context_limit=None,
                tool_counts={"a": 3}, skill_counts={"y": 2},
            ),
        ],
    )
    assert _agg_workflow_counts(wf, "tool_counts") == {"a": 4, "b": 2}
    assert _agg_workflow_counts(wf, "skill_counts") == {"x": 1, "y": 2}


# ----------------------------------------------------------------------
# View
# ----------------------------------------------------------------------


def test_view_renders_workflow_and_step_rows(qapp):
    s = _state_with_history()
    v = StatsHistoryView(s)
    v.refresh()

    assert v._tree.topLevelItemCount() == 1
    wf_item = v._tree.topLevelItem(0)
    assert "WF A" in wf_item.text(COL_NAME)
    assert wf_item.text(COL_MODEL) == "gpt-x"
    assert "10,000" in wf_item.text(COL_CONTEXT)
    assert "read_file×2" in wf_item.text(COL_TOOLS)
    assert "task-questionnaire×1" in wf_item.text(COL_SKILLS)

    # Step 子行
    assert wf_item.childCount() == 1
    step_item = wf_item.child(0)
    assert "s1" in step_item.text(COL_NAME)
    assert "read_file×2" in step_item.text(COL_TOOLS)
    assert step_item.text(COL_ELAPSED) != "-"


def test_view_updates_on_signal(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    v = StatsHistoryView(s)
    assert v._tree.topLevelItemCount() == 0

    s.update_identity(workflow_id="wf1", workflow_name="WF A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    # スロットルなしで即時更新を確認するため refresh() を呼ぶ
    v.refresh()
    assert v._tree.topLevelItemCount() == 1
    assert v._tree.topLevelItem(0).childCount() == 1


def test_view_multiple_workflows(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="gpt-x")
    s.update_identity(workflow_id="wf1", workflow_name="A", run_id="r1")
    s.set_step_status("s1", "running")
    s.set_step_status("s1", "done")
    s.mark_all_done()
    s.all_done = False
    s.update_identity(workflow_id="wf2", workflow_name="B", run_id="r2")
    s.set_step_status("s2", "running")
    s.set_step_status("s2", "done")

    v = StatsHistoryView(s)
    v.refresh()
    assert v._tree.topLevelItemCount() == 2


def test_view_userrole_data_for_dclick(qapp):
    s = _state_with_history()
    v = StatsHistoryView(s)
    v.refresh()
    wf_item = v._tree.topLevelItem(0)
    counts = wf_item.data(COL_TOOLS, Qt.ItemDataRole.UserRole)
    assert counts == {"read_file": 2}
    step_item = wf_item.child(0)
    sk = step_item.data(COL_SKILLS, Qt.ItemDataRole.UserRole)
    assert sk == {"task-questionnaire": 1}


def test_view_empty_state(qapp):
    s = WorkbenchState(workflow_id="wf", run_id="r", model="m")
    v = StatsHistoryView(s)
    v.refresh()
    assert v._tree.topLevelItemCount() == 0


# ----------------------------------------------------------------------
# AI Credit フォーマッタ
# ----------------------------------------------------------------------


def test_fmt_aiu():
    assert _fmt_aiu(None) == "-"
    # 0 や負値も「未取得」と同等扱いで "-"（実装仕様）
    assert _fmt_aiu(0) == "-"
    assert _fmt_aiu(-100) == "-"
    assert _fmt_aiu(1_000_000_000) == "1.0000 AIU"
    assert _fmt_aiu(2_500_000_000) == "2.5000 AIU"


# ----------------------------------------------------------------------
# Step 並び替えと差分計算
# ----------------------------------------------------------------------


def _mkstep(step_id: str, finished_at, total_nano):
    return StepStatsSnapshot(
        step_id=step_id, step_title="", status="done", model="m",
        started_at=0.0, finished_at=finished_at, elapsed_sec=None,
        context_current=None, context_limit=None,
        tool_counts={}, skill_counts={}, sdk_aiu_total_nano=total_nano,
    )


def test_sorted_steps_by_finish_handles_none_and_reorder():
    # 挿入順は s3(finished=3), s1(finished=1), s2(finished=None)
    steps = [
        _mkstep("s3", 3.0, 3_000_000_000),
        _mkstep("s1", 1.0, 1_000_000_000),
        _mkstep("s2", None, None),
    ]
    sorted_ids = [st.step_id for st in _sorted_steps_by_finish(steps)]
    # finished_at None は末尾。1 → 3 → None。
    assert sorted_ids == ["s1", "s3", "s2"]


def test_sorted_steps_by_finish_is_stable_for_ties_and_none():
    """安定ソート: finished_at が同値・None の Step は元順序を保持。"""
    steps = [
        _mkstep("a", 1.0, 1),
        _mkstep("b", 1.0, 2),       # a と同じ finished_at
        _mkstep("c", None, 3),      # None 1
        _mkstep("d", 2.0, 4),
        _mkstep("e", None, 5),      # None 2
    ]
    sorted_ids = [st.step_id for st in _sorted_steps_by_finish(steps)]
    # 1.0 (a, b 順保持), 2.0, None (c, e 順保持)
    assert sorted_ids == ["a", "b", "d", "c", "e"]


def test_step_aiu_delta_nano_first_step_equals_total():
    cur = _mkstep("s1", 1.0, 2_000_000_000)
    # 最初の Step（prev=None）は累積=差分とみなす
    assert _step_aiu_delta_nano(cur, None) == 2_000_000_000


def test_step_aiu_delta_nano_normal_diff():
    prev = _mkstep("s1", 1.0, 1_000_000_000)
    cur = _mkstep("s2", 2.0, 2_500_000_000)
    assert _step_aiu_delta_nano(cur, prev) == 1_500_000_000


def test_step_aiu_delta_nano_returns_none_when_prev_unknown():
    """前 Step の AIU が None の場合、現 Step の累積を差分に流用してはならない（捏造禁止）。"""
    prev = _mkstep("s1", 1.0, None)
    cur = _mkstep("s2", 2.0, 2_000_000_000)
    assert _step_aiu_delta_nano(cur, prev) is None


def test_step_aiu_delta_nano_returns_none_for_negative_or_zero_current():
    prev = _mkstep("s1", 1.0, 1_000_000_000)
    cur_zero = _mkstep("s2", 2.0, 0)
    cur_neg = _mkstep("s2", 2.0, -1)
    assert _step_aiu_delta_nano(cur_zero, prev) is None
    assert _step_aiu_delta_nano(cur_neg, prev) is None


def test_step_aiu_delta_nano_returns_none_for_zero_delta():
    """累積が前 Step と完全に同じ（消費 0）。仕様: 0 以下は None。"""
    prev = _mkstep("s1", 1.0, 1_000_000_000)
    cur = _mkstep("s2", 2.0, 1_000_000_000)
    assert _step_aiu_delta_nano(cur, prev) is None


def test_step_aiu_delta_nano_returns_none_for_negative_delta():
    """累積が前 Step より減るのは異常（補正のみ等）。差分は None。"""
    prev = _mkstep("s1", 1.0, 2_000_000_000)
    cur = _mkstep("s2", 2.0, 1_000_000_000)
    assert _step_aiu_delta_nano(cur, prev) is None


def test_compute_step_prev_map_within_single_workflow():
    """単一 Workflow: 最初の Step は prev=None、以降は finished_at 順の前 Step。"""
    s1 = _mkstep("s1", 1.0, 1_000_000_000)
    s2 = _mkstep("s2", 2.0, 2_000_000_000)
    s3 = _mkstep("s3", 3.0, 3_000_000_000)
    wf = WorkflowStatsSnapshot(
        workflow_id="wf", workflow_name="WF", run_id="r", model="m",
        started_at=0.0, steps=[s1, s2, s3],
    )
    prev_map = _compute_step_prev_map([wf])
    assert prev_map[id(s1)] is None
    assert prev_map[id(s2)] is s1
    assert prev_map[id(s3)] is s2


def test_compute_step_prev_map_across_multiple_workflows():
    """複数 Workflow 跨ぎでも finished_at 順で前 Step を返す。"""
    a1 = _mkstep("a1", 1.0, 2_000_000_000)
    a2 = _mkstep("a2", 2.0, 5_000_000_000)
    b1 = _mkstep("b1", 3.0, 6_000_000_000)  # 累積: 前 wf の a2 から +1.0
    b2 = _mkstep("b2", 4.0, 8_000_000_000)
    wfA = WorkflowStatsSnapshot(
        workflow_id="wfA", workflow_name="A", run_id="rA", model="m",
        started_at=0.0, steps=[a1, a2],
    )
    wfB = WorkflowStatsSnapshot(
        workflow_id="wfB", workflow_name="B", run_id="rB", model="m",
        started_at=2.5, steps=[b1, b2],
    )
    prev_map = _compute_step_prev_map([wfA, wfB])
    # Workflow A 内
    assert prev_map[id(a1)] is None
    assert prev_map[id(a2)] is a1
    # Workflow B の最初 Step b1 の前は Workflow A の最終 Step a2（跨ぎ）
    assert prev_map[id(b1)] is a2
    assert prev_map[id(b2)] is b1


def test_compute_step_prev_map_handles_finished_at_none_at_end():
    """finished_at=None の Step は末尾扱い。"""
    s1 = _mkstep("s1", 1.0, 1_000_000_000)
    s2 = _mkstep("s2", None, 2_000_000_000)
    wf = WorkflowStatsSnapshot(
        workflow_id="wf", workflow_name="WF", run_id="r", model="m",
        started_at=0.0, steps=[s1, s2],
    )
    prev_map = _compute_step_prev_map([wf])
    assert prev_map[id(s1)] is None
    assert prev_map[id(s2)] is s1


def test_compute_step_prev_map_empty_history():
    assert _compute_step_prev_map([]) == {}


def test_aiu_sort_key_unifies_unknown_zero_negative_to_minus_one():
    """ソートキー: None / 0 / 負値は全て -1（表示の `-` と整合、Minor No.5 修正）。"""
    assert _aiu_sort_key(None) == -1
    assert _aiu_sort_key(0) == -1
    assert _aiu_sort_key(-1_000) == -1
    assert _aiu_sort_key(1_000) == 1_000
    assert _aiu_sort_key("not int") == -1  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# View の AI Credit 列セル
# ----------------------------------------------------------------------


def test_view_renders_aiu_for_workflow_and_steps(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=2_500_000_000,
        steps=[
            _mkstep("s1", 1.0, 1_000_000_000),
            _mkstep("s2", 2.0, 2_500_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "2.5000 AIU"
    # Workflow 親には差分を出さない
    assert "+" not in wf.text(COL_AI_CREDIT)
    # Step は「該当 Step の消費分（差分）のみ」
    assert wf.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    assert wf.child(1).text(COL_AI_CREDIT) == "1.5000 AIU"


def test_view_aiu_diff_uses_finish_order_not_insertion_order(qapp):
    """挿入順と finished_at 順が逆でも、差分は finished_at 順で計算される。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=2_500_000_000,
        steps=[
            _mkstep("s_late", 2.0, 2_500_000_000),   # 後完了だが先頭に挿入
            _mkstep("s_early", 1.0, 1_000_000_000),  # 先完了だが末尾に挿入
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    # 子は finished_at 昇順
    assert "s_early" in wf.child(0).text(COL_NAME)
    assert "s_late" in wf.child(1).text(COL_NAME)
    # s_early は最初の Step → 消費分 = 累積 1.0
    assert wf.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    # s_late は消費分 = 2.5 - 1.0 = 1.5
    assert wf.child(1).text(COL_AI_CREDIT) == "1.5000 AIU"


def test_view_aiu_unknown_shows_dash(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[_mkstep("s1", 1.0, None)],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "-"
    assert wf.child(0).text(COL_AI_CREDIT) == "-"


def test_view_aiu_workflow_unknown_but_step_known(qapp):
    """Workflow 親=未取得、Step 子=値あり。親 '-', 子 '累積 (+差分)' で混在表示。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[
            _mkstep("s1", 1.0, 1_000_000_000),
            _mkstep("s2", 2.0, 2_500_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "-"
    assert wf.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    assert wf.child(1).text(COL_AI_CREDIT) == "1.5000 AIU"
    # CSV では Workflow AiuTotal は空、Step は値あり（CSV は累積+差分を別列で維持）
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(build_csv(s.stats_history, now_monotonic=0.0))))
    assert rows[1][0] == "workflow" and rows[1][9] == "" and rows[1][10] == ""
    assert rows[2][0] == "step" and rows[2][9] == "1.000000" and rows[2][10] == "1.000000"
    assert rows[3][0] == "step" and rows[3][9] == "2.500000" and rows[3][10] == "1.500000"


def test_view_step_known_total_but_unknown_delta_shows_dash(qapp):
    """累積は既知でも差分が計算不能（直前 Step 未取得）な Step は `-`（累積で代用しない=捏造禁止）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=2_000_000_000,
        steps=[
            _mkstep("s_unknown", 1.0, None),         # 累積=未取得
            _mkstep("s_known", 2.0, 2_000_000_000),  # 累積=2.0 だが直前(s_unknown)が未取得→差分不能
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    # s_unknown: 累積 None → 差分 None → `-`
    assert wf.child(0).text(COL_AI_CREDIT) == "-"
    # s_known: 累積 2.0 は既知だが、直前 Step 未取得のため差分計算不能 → `-`
    assert wf.child(1).text(COL_AI_CREDIT) == "-"


def test_view_aiu_diff_continues_across_workflows(qapp):
    """View でも Workflow 跨ぎで前 Step との差分を計算する（Critical No.1 修正の検証）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    # 累積動作: a1=2.0, a2=5.0 / b1=6.0（5.0+1.0）, b2=8.0（5.0+3.0）
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wfA", workflow_name="A", run_id="rA", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=5_000_000_000,
        steps=[
            _mkstep("a1", 1.0, 2_000_000_000),
            _mkstep("a2", 2.0, 5_000_000_000),
        ],
    ))
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wfB", workflow_name="B", run_id="rB", model="m",
        started_at=2.5, elapsed_sec=2.0, sdk_aiu_total_nano=8_000_000_000,
        steps=[
            _mkstep("b1", 3.0, 6_000_000_000),
            _mkstep("b2", 4.0, 8_000_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    # Workflow B の Tree item は 2 番目
    wfB_item = v._tree.topLevelItem(1)
    # b1 は前 Workflow の a2（累積 5.0）との差分 = 1.0 を表示
    assert wfB_item.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    # b2 は b1（累積 6.0）との差分 = 2.0
    assert wfB_item.child(1).text(COL_AI_CREDIT) == "2.0000 AIU"


def test_view_aiu_column_sorts_numerically(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    for wf_id, name, total in [
        ("w1", "A_small", 500_000_000),
        ("w2", "B_large", 10_000_000_000),
        ("w3", "C_mid", 2_500_000_000),
    ]:
        s.stats_history.append(WorkflowStatsSnapshot(
            workflow_id=wf_id, workflow_name=name, run_id="r1", model="m",
            started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=total, steps=[],
        ))
    v = StatsHistoryView(s)
    v.refresh()
    v._tree.sortByColumn(COL_AI_CREDIT, Qt.SortOrder.AscendingOrder)
    names_asc = [v._tree.topLevelItem(i).text(COL_NAME) for i in range(3)]
    # 文字列ソート (10 < 2 < 5) ではなく数値ソート (0.5 < 2.5 < 10.0)
    assert names_asc == ["[Workflow] A_small", "[Workflow] C_mid", "[Workflow] B_large"]
    v._tree.sortByColumn(COL_AI_CREDIT, Qt.SortOrder.DescendingOrder)
    names_desc = [v._tree.topLevelItem(i).text(COL_NAME) for i in range(3)]
    assert names_desc == ["[Workflow] B_large", "[Workflow] C_mid", "[Workflow] A_small"]


def test_view_aiu_column_sorts_step_children_numerically(qapp):
    """子 Step 行も AI Credit 列で数値ソートされる。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=10.0, sdk_aiu_total_nano=11_000_000_000,
        steps=[
            # 完了順は s_small → s_large → s_mid（累積も同順）。
            # ソートは「差分」基準: s_small=0.5, s_large=9.5, s_mid=1.0
            _mkstep("s_small", 1.0, 500_000_000),       # 累積 0.5 / 差分 0.5
            _mkstep("s_large", 2.0, 10_000_000_000),    # 累積 10.0 / 差分 9.5
            _mkstep("s_mid", 3.0, 11_000_000_000),      # 累積 11.0 / 差分 1.0
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    v._tree.sortByColumn(COL_AI_CREDIT, Qt.SortOrder.AscendingOrder)
    wf = v._tree.topLevelItem(0)
    children_ids = [wf.child(i).text(COL_NAME).strip() for i in range(wf.childCount())]
    # 差分昇順: s_small(0.5) < s_mid(1.0) < s_large(9.5)
    assert children_ids == ["s_small", "s_mid", "s_large"]


# ----------------------------------------------------------------------
# CSV ヘルパー
# ----------------------------------------------------------------------


def test_csv_pct_unknown_and_normal():
    assert _csv_pct(None, None) == ""
    assert _csv_pct(0, 0) == ""
    # 実装は .1f 固定（Excel 解析時の統一フォーマット）
    assert _csv_pct(1000, 10000) == "10.0"
    assert _csv_pct(123, 10000) == "1.2"


def test_csv_aiu_unknown_and_normal():
    assert _csv_aiu(None) == ""
    assert _csv_aiu(1_000_000_000) == "1.000000"
    assert _csv_aiu(2_500_000_000) == "2.500000"


def test_csv_safe_int():
    assert _csv_safe_int(None) == ""
    assert _csv_safe_int(0) == "0"
    assert _csv_safe_int(1000) == "1000"


def test_csv_counts_topn():
    counts = {f"t{i}": (10 - i) for i in range(8)}
    out = _csv_counts_topn(counts, top=3)
    # 完全一致: Top 3 + " +5 more"（実装仕様: CSV にも +N more を含める）
    assert out == "t0×10, t1×9, t2×8 +5 more"


def test_csv_counts_topn_empty():
    assert _csv_counts_topn({}) == ""


def test_csv_counts_topn_within_topn_no_more_suffix():
    """要素数が top 以下なら `+N more` は付かない。"""
    out = _csv_counts_topn({"a": 3, "b": 2}, top=5)
    assert out == "a×3, b×2"


def test_sanitize_csv_cell_prepends_quote_for_injection():
    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        assert _sanitize_csv_cell(prefix + "evil").startswith("'")
    # 通常文字列は変更しない
    assert _sanitize_csv_cell("normal text") == "normal text"
    assert _sanitize_csv_cell("") == ""


def test_build_csv_headers_and_basic_row():
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="gpt-x",
        started_at=0.0, elapsed_sec=10.0, sdk_aiu_total_nano=2_500_000_000,
        context_current=1000, context_limit=10000,
        steps=[
            _mkstep("s1", 1.0, 1_000_000_000),
            _mkstep("s2", 2.0, 2_500_000_000),
        ],
    ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history).splitlines()))
    expected_header = [
        "Type", "Workflow", "Step", "Context", "Limit", "Pct", "Model",
        "ElapsedSec", "ElapsedHMS", "AiuTotal", "AiuDeltaSincePrev",
        "ToolsTop", "SkillsTop", "Status",
    ]
    assert rows[0] == expected_header
    # 全行 14 列
    for r in rows:
        assert len(r) == 14
    # ヘッダ + Workflow + Step×2 = 4 行
    assert len(rows) == 4
    # Workflow 行（idx=1）: AiuTotal=2.500000、AiuDelta=空
    assert rows[1][0] == "workflow"
    assert rows[1][1] == "WF"
    assert rows[1][2] == ""
    assert rows[1][9] == "2.500000"
    assert rows[1][10] == ""
    # Step1: 累積 1.000000、差分 1.000000
    assert rows[2][0] == "step"
    assert rows[2][1] == "WF"
    assert rows[2][2] == "s1"
    assert rows[2][9] == "1.000000"
    assert rows[2][10] == "1.000000"
    # Step2: 累積 2.500000、差分 1.500000
    assert rows[3][2] == "s2"
    assert rows[3][9] == "2.500000"
    assert rows[3][10] == "1.500000"


def test_build_csv_multiple_workflows_diff_continues_across_workflows(qapp):
    """複数 Workflow CSV: ``sdk_aiu_total_nano`` は WorkbenchState 通算累積。

    Workflow 切替時に backend 側でリセットされないため、Workflow 跨ぎでも
    「直前 Step との差分」で正しい単独消費量を表示する必要がある。
    """
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    # 累積動作を模した値: a1=2.0, a2=5.0 / b1=6.0, b2=8.0（5.0 + 1.0, 5.0 + 3.0）
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF_A", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=5_000_000_000,
        steps=[
            _mkstep("a1", 1.0, 2_000_000_000),
            _mkstep("a2", 2.0, 5_000_000_000),
        ],
    ))
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf2", workflow_name="WF_B", run_id="r2", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=8_000_000_000,
        steps=[
            _mkstep("b1", 3.0, 6_000_000_000),
            _mkstep("b2", 4.0, 8_000_000_000),
        ],
    ))
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(build_csv(s.stats_history, now_monotonic=0.0))))
    # ヘッダ + 2 Workflow + 4 Step = 7 行、14 列
    assert len(rows) == 7
    assert [len(r) for r in rows] == [14] * 7
    # 順序: header, WF_A, a1, a2, WF_B, b1, b2
    assert [r[0] for r in rows] == ["Type", "workflow", "step", "step", "workflow", "step", "step"]
    assert [r[1] for r in rows] == ["Workflow", "WF_A", "WF_A", "WF_A", "WF_B", "WF_B", "WF_B"]
    assert [r[2] for r in rows] == ["Step", "", "a1", "a2", "", "b1", "b2"]
    # a1: 累積 2.0, 差分 2.0（最初の Step）
    assert rows[2][2] == "a1"
    assert rows[2][9] == "2.000000"
    assert rows[2][10] == "2.000000"
    # a2: 累積 5.0, 差分 3.0（5.0 - 2.0）
    assert rows[3][2] == "a2"
    assert rows[3][9] == "5.000000"
    assert rows[3][10] == "3.000000"
    # b1: 累積 6.0, 差分 1.0（6.0 - 5.0、Workflow 跨ぎで a2 との差分を計算）
    assert rows[5][2] == "b1"
    assert rows[5][9] == "6.000000"
    assert rows[5][10] == "1.000000"
    # b2: 累積 8.0, 差分 2.0（8.0 - 6.0）
    assert rows[6][2] == "b2"
    assert rows[6][9] == "8.000000"
    assert rows[6][10] == "2.000000"


def test_build_csv_empty_history():
    csv_text = build_csv([])
    import csv as _csv
    rows = list(_csv.reader(csv_text.splitlines()))
    # ヘッダ 1 行のみ
    assert len(rows) == 1
    assert rows[0][0] == "Type" and rows[0][-1] == "Status"
    assert len(rows[0]) == 14


def test_build_csv_unknown_values_are_empty():
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model=None,
        started_at=0.0, elapsed_sec=None, sdk_aiu_total_nano=None,
        steps=[_mkstep("s1", None, None)],
    ))
    import csv as _csv
    # now_monotonic を明示して実時刻に依存させない
    rows = list(_csv.reader(build_csv(s.stats_history, now_monotonic=0.0).splitlines()))
    # Workflow 行: ElapsedSec=0 (0-0), ElapsedHMS="00:00:00", AiuTotal/AiuDelta は空欄
    assert rows[1][7] == "0"
    assert rows[1][8] == "00:00:00"
    assert rows[1][9] == "" and rows[1][10] == ""
    # Step 行: ElapsedSec/ElapsedHMS は空（_mkstep の elapsed_sec=None で計算根拠なし）、AiuTotal/AiuDelta も空欄
    assert rows[2][7] == "" and rows[2][8] == ""
    assert rows[2][9] == "" and rows[2][10] == ""


def test_build_csv_preserves_commas_and_newlines_in_names():
    """Workflow 名 / Step ID にカンマ・改行が含まれても CSV 構造が壊れない。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF, A\nB", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=1_000_000_000,
        steps=[StepStatsSnapshot(
            step_id="s,1\nx", step_title="", status="done", model="m",
            started_at=0.0, finished_at=1.0, elapsed_sec=1.0,
            context_current=None, context_limit=None,
            tool_counts={}, skill_counts={}, sdk_aiu_total_nano=1_000_000_000,
        )],
    ))
    import csv as _csv
    import io as _io
    # 引用内改行を保持するため splitlines() ではなく StringIO を直接渡す
    rows = list(_csv.reader(_io.StringIO(build_csv(s.stats_history))))
    # ヘッダ + Workflow + Step = 3 行、各 14 列
    assert len(rows) == 3
    assert [len(r) for r in rows] == [14, 14, 14]
    # 元の名前が復元される（CSV パーサで RFC 4180 準拠デコード）
    assert rows[1][1] == "WF, A\nB"
    assert rows[2][2] == "s,1\nx"


def test_build_csv_sanitizes_formula_injection_in_all_text_columns():
    """Workflow 名 / Step ID / Model / Status / Tools / Skills すべてに injection sanitize 適用。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="=BAD_WF", run_id="r1", model="=BAD_MODEL",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[StepStatsSnapshot(
            step_id="=BAD_STEP", step_title="", status="=BAD_STATUS", model="=BAD_MODEL2",
            started_at=0.0, finished_at=1.0, elapsed_sec=1.0,
            context_current=None, context_limit=None,
            tool_counts={"=evil_tool": 1}, skill_counts={"=evil_skill": 1},
            sdk_aiu_total_nano=None,
        )],
    ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history).splitlines()))
    # Workflow 行
    assert rows[1][1].startswith("'=")  # Workflow name
    assert rows[1][6].startswith("'=")  # Model
    # Tools / Skills は集計後の文字列が ' 始まりに（先頭の "=evil..." を sanitize）
    assert rows[1][11].startswith("'=")  # ToolsTop
    assert rows[1][12].startswith("'=")  # SkillsTop
    # Step 行
    assert rows[2][1].startswith("'=")  # Workflow name（重出）
    assert rows[2][2].startswith("'=")  # Step ID
    assert rows[2][6].startswith("'=")  # Model
    assert rows[2][11].startswith("'=")  # ToolsTop
    assert rows[2][12].startswith("'=")  # SkillsTop
    assert rows[2][13].startswith("'=")  # Status


def test_build_csv_uses_provided_now_monotonic_for_deterministic_output():
    """build_csv は now_monotonic を引数で受け取り、外部時刻に依存しない（純粋関数性）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=100.0, elapsed_sec=None,  # elapsed_sec=None なら now_monotonic から計算
        sdk_aiu_total_nano=None, steps=[],
    ))
    a = build_csv(s.stats_history, now_monotonic=110.0)
    b = build_csv(s.stats_history, now_monotonic=110.0)
    assert a == b  # 決定的
    # ElapsedSec = 10 (110 - 100)
    import csv as _csv
    rows = list(_csv.reader(a.splitlines()))
    assert rows[1][7] == "10"


def test_build_csv_handles_many_workflows_and_steps_structure():
    """構造的劣化検出: 50 Workflow × 10 Step の履歴で行数・列数が崩れない。"""
    s = WorkbenchState(workflow_id="x", run_id="r", model="m")
    for i in range(50):
        s.stats_history.append(WorkflowStatsSnapshot(
            workflow_id=f"w{i}", workflow_name=f"W{i}", run_id="r", model="m",
            started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=(i + 1) * 1_000_000_000,
            steps=[
                _mkstep(f"s{i}_{j}", float(j), (j + 1) * 100_000_000)
                for j in range(10)
            ],
        ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history).splitlines()))
    # ヘッダ + 50 Workflow + 50×10 Step = 1 + 50 + 500 = 551 行
    assert len(rows) == 1 + 50 + 500
    assert all(len(r) == 14 for r in rows)


def test_view_csv_text_exposes_csv(qapp):
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=1_000_000_000,
        steps=[_mkstep("s1", 1.0, 1_000_000_000)],
    ))
    v = StatsHistoryView(s)
    txt = v._csv_text()
    assert txt.splitlines()[0].startswith("Type,Workflow,Step,")
    assert "WF" in txt
    assert "s1" in txt


def test_view_csv_text_propagates_exception(qapp):
    """build_csv が壊れた場合、無音で空文字を返さず例外を伝播する（CopyButton が tooltip 表示）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    v = StatsHistoryView(s)

    class _Boom:
        @property
        def stats_history(self):
            raise RuntimeError("boom")

    v._state = _Boom()
    with pytest.raises(RuntimeError, match="boom"):
        v._csv_text()
