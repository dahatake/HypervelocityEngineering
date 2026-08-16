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
    s.record_step_context("s1", 1000, 10000)
    s.record_step_model("s1", "gpt-x")
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
    assert wf_item.text(COL_MODEL) == "gpt-x×1"
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
    # Model 列も Top-N 表記のため、全件ポップアップ用の raw を保持する
    assert wf_item.data(COL_MODEL, Qt.ItemDataRole.UserRole) == {"gpt-x": 1}
    assert step_item.data(COL_MODEL, Qt.ItemDataRole.UserRole) == {"gpt-x": 1}


def test_view_dclick_opens_popup_for_model_column(qapp, monkeypatch):
    """Model セルの D-click で全件ポップアップを開く（Tools / Skills と同じ経路）。"""
    s = _state_with_history()
    v = StatsHistoryView(s)
    v.refresh()
    shown: list = []
    monkeypatch.setattr(
        "hve.gui.stats_history_view.QMessageBox.information",
        lambda parent, title, text: shown.append((title, text)),
    )

    step_item = v._tree.topLevelItem(0).child(0)
    v._on_item_double_clicked(step_item, COL_MODEL)
    assert shown and "gpt-x: 1" in shown[0][1]

    # 対象外の列では開かない
    shown.clear()
    v._on_item_double_clicked(step_item, COL_ELAPSED)
    assert shown == []


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


def _mkstep(step_id: str, finished_at, total_nano, own_nano=None, model_counts=None):
    return StepStatsSnapshot(
        step_id=step_id, step_title="", status="done", model="m",
        started_at=0.0, finished_at=finished_at, elapsed_sec=None,
        context_current=None, context_limit=None,
        tool_counts={}, skill_counts={}, sdk_aiu_total_nano=total_nano,
        aiu_nano_own=own_nano, model_counts=dict(model_counts or {}),
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
            _mkstep("s1", 1.0, 1_000_000_000, own_nano=1_000_000_000),
            _mkstep("s2", 2.0, 2_500_000_000, own_nano=1_500_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "2.5000 AIU"
    # Step は当該 Step へ帰属した実測消費のみ
    assert wf.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    assert wf.child(1).text(COL_AI_CREDIT) == "1.5000 AIU"


def test_step_row_shows_own_aiu(qapp):
    """Step 行の AI Credit 列は Step 実測値であり、隣接 Step の累積差分を用いない。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=9_000_000_000,
        steps=[
            # 累積は s1=8.0 / s2=9.0 だが、実測消費は 2.0 / 3.0（Fleet 分が累積に混在）。
            _mkstep("s1", 1.0, 8_000_000_000, own_nano=2_000_000_000),
            _mkstep("s2", 2.0, 9_000_000_000, own_nano=3_000_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.child(0).text(COL_AI_CREDIT) == "2.0000 AIU"
    assert wf.child(1).text(COL_AI_CREDIT) == "3.0000 AIU"


def test_step_row_shows_dash_when_own_aiu_unknown(qapp):
    """Step 実測値が無い場合は `-`（Workflow 累積で代用しない）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=5_000_000_000,
        steps=[_mkstep("fleet-step", 1.0, 5_000_000_000, own_nano=None)],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "5.0000 AIU"
    assert wf.child(0).text(COL_AI_CREDIT) == "-"


def test_view_orders_steps_by_finish_time(qapp):
    """挿入順と finished_at 順が逆でも、子行は finished_at 昇順で並ぶ。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=2_500_000_000,
        steps=[
            _mkstep("s_late", 2.0, 2_500_000_000, own_nano=1_500_000_000),
            _mkstep("s_early", 1.0, 1_000_000_000, own_nano=1_000_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert "s_early" in wf.child(0).text(COL_NAME)
    assert "s_late" in wf.child(1).text(COL_NAME)


def test_step_row_shows_model_counts(qapp):
    """Step 行のモデル列はモデル別呼び出し回数を表示する。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[_mkstep(
            "s1", 1.0, None,
            model_counts={"claude-opus-5": 42, "gpt-5.6-terra": 23},
        )],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    text = v._tree.topLevelItem(0).child(0).text(COL_MODEL)
    assert "claude-opus-5×42" in text
    assert "gpt-5.6-terra×23" in text


def test_step_row_model_shows_dash_when_unknown(qapp):
    """モデル帰属イベントが無い Step は `-`（グローバル値で代用しない）。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="claude-opus-5")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="claude-opus-5",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[_mkstep("fleet-step", 1.0, None)],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    assert v._tree.topLevelItem(0).child(0).text(COL_MODEL) == "-"


def test_workflow_row_aggregates_model_counts(qapp):
    """Workflow 親行のモデル列は子 Step の合計。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[
            _mkstep("s1", 1.0, None, model_counts={"claude-opus-5": 2}),
            _mkstep("s2", 2.0, None, model_counts={"claude-opus-5": 3, "gpt-5.6-terra": 1}),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    text = v._tree.topLevelItem(0).text(COL_MODEL)
    assert "claude-opus-5×5" in text
    assert "gpt-5.6-terra×1" in text


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
    """Workflow 親=未取得、Step 子=値あり。親 '-'、子は実測値で混在表示。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=None,
        steps=[
            _mkstep("s1", 1.0, 1_000_000_000, own_nano=1_000_000_000),
            _mkstep("s2", 2.0, 2_500_000_000, own_nano=1_500_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    wf = v._tree.topLevelItem(0)
    assert wf.text(COL_AI_CREDIT) == "-"
    assert wf.child(0).text(COL_AI_CREDIT) == "1.0000 AIU"
    assert wf.child(1).text(COL_AI_CREDIT) == "1.5000 AIU"
    # CSV: Workflow の AiuTotal は空、Step は累積と実測をそれぞれ別列で保持
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(build_csv(s.stats_history, now_monotonic=0.0))))
    assert rows[1][0] == "workflow" and rows[1][9] == "" and rows[1][10] == ""
    assert rows[2][0] == "step" and rows[2][9] == "1.000000" and rows[2][10] == "1.000000"
    assert rows[3][0] == "step" and rows[3][9] == "2.500000" and rows[3][10] == "1.500000"


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
    """子 Step 行も AI Credit 列（実測値）で数値ソートされる。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=10.0, sdk_aiu_total_nano=11_000_000_000,
        steps=[
            _mkstep("s_small", 1.0, 500_000_000, own_nano=500_000_000),
            _mkstep("s_large", 2.0, 10_000_000_000, own_nano=9_500_000_000),
            _mkstep("s_mid", 3.0, 11_000_000_000, own_nano=1_000_000_000),
        ],
    ))
    v = StatsHistoryView(s)
    v.refresh()
    v._tree.sortByColumn(COL_AI_CREDIT, Qt.SortOrder.AscendingOrder)
    wf = v._tree.topLevelItem(0)
    children_ids = [wf.child(i).text(COL_NAME).strip() for i in range(wf.childCount())]
    # 実測値昇順: s_small(0.5) < s_mid(1.0) < s_large(9.5)
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
            _mkstep("s1", 1.0, 1_000_000_000, own_nano=1_000_000_000,
                    model_counts={"gpt-x": 3}),
            _mkstep("s2", 2.0, 2_500_000_000, own_nano=1_500_000_000,
                    model_counts={"gpt-x": 2}),
        ],
    ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history).splitlines()))
    expected_header = [
        "Type", "Workflow", "Step", "Context", "Limit", "Pct", "Model",
        "ElapsedSec", "ElapsedHMS", "AiuTotal", "AiuOwn",
        "ToolsTop", "SkillsTop", "Status",
    ]
    assert rows[0] == expected_header
    # 全行 14 列
    for r in rows:
        assert len(r) == 14
    # ヘッダ + Workflow + Step×2 = 4 行
    assert len(rows) == 4
    # Workflow 行（idx=1）: AiuTotal=2.500000、AiuOwn=空、Model=子の合計
    assert rows[1][0] == "workflow"
    assert rows[1][1] == "WF"
    assert rows[1][2] == ""
    assert rows[1][6] == "gpt-x×5"
    assert rows[1][9] == "2.500000"
    assert rows[1][10] == ""
    # Step1: 累積 1.000000、実測 1.000000
    assert rows[2][0] == "step"
    assert rows[2][1] == "WF"
    assert rows[2][2] == "s1"
    assert rows[2][6] == "gpt-x×3"
    assert rows[2][9] == "1.000000"
    assert rows[2][10] == "1.000000"
    # Step2: 累積 2.500000、実測 1.500000
    assert rows[3][2] == "s2"
    assert rows[3][9] == "2.500000"
    assert rows[3][10] == "1.500000"


def test_build_csv_has_aiu_own_column():
    """CSV は `AiuOwn` 列を持ち、推定値である `AiuDeltaSincePrev` を持たない。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=1.0, sdk_aiu_total_nano=9_000_000_000,
        steps=[
            _mkstep("s1", 1.0, 8_000_000_000, own_nano=2_000_000_000),
            _mkstep("fleet-step", 2.0, 9_000_000_000, own_nano=None),
        ],
    ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history, now_monotonic=0.0).splitlines()))
    assert "AiuOwn" in rows[0]
    assert "AiuDeltaSincePrev" not in rows[0]
    own_idx = rows[0].index("AiuOwn")
    # 累積差分 (8.0-0=8.0) ではなく実測 2.0。
    assert rows[2][own_idx] == "2.000000"
    # 実測不可な Step は空欄（累積差分で補わない）。
    assert rows[3][own_idx] == ""


def test_build_csv_multiple_workflows_keep_row_structure(qapp):
    """複数 Workflow CSV: 行順・列数・実測値が Workflow を跨いでも崩れない。"""
    s = WorkbenchState(workflow_id="wf1", run_id="r1", model="m")
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf1", workflow_name="WF_A", run_id="r1", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=5_000_000_000,
        steps=[
            _mkstep("a1", 1.0, 2_000_000_000, own_nano=2_000_000_000),
            _mkstep("a2", 2.0, 5_000_000_000, own_nano=3_000_000_000),
        ],
    ))
    s.stats_history.append(WorkflowStatsSnapshot(
        workflow_id="wf2", workflow_name="WF_B", run_id="r2", model="m",
        started_at=0.0, elapsed_sec=2.0, sdk_aiu_total_nano=8_000_000_000,
        steps=[
            _mkstep("b1", 3.0, 6_000_000_000, own_nano=1_000_000_000),
            _mkstep("b2", 4.0, 8_000_000_000, own_nano=2_000_000_000),
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
    # 実測値は Workflow 跨ぎの累積に影響されない。
    assert rows[2][9] == "2.000000" and rows[2][10] == "2.000000"
    assert rows[3][9] == "5.000000" and rows[3][10] == "3.000000"
    assert rows[5][9] == "6.000000" and rows[5][10] == "1.000000"
    assert rows[6][9] == "8.000000" and rows[6][10] == "2.000000"


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
    # Workflow 行: ElapsedSec=0 (0-0), ElapsedHMS="00:00:00", AiuTotal/AiuOwn は空欄
    assert rows[1][7] == "0"
    assert rows[1][8] == "00:00:00"
    assert rows[1][9] == "" and rows[1][10] == ""
    # Step 行: ElapsedSec/ElapsedHMS は空（_mkstep の elapsed_sec=None で計算根拠なし）、AiuTotal/AiuOwn も空欄
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
            sdk_aiu_total_nano=None, model_counts={"=evil_model": 1},
        )],
    ))
    import csv as _csv
    rows = list(_csv.reader(build_csv(s.stats_history).splitlines()))
    # Workflow 行
    assert rows[1][1].startswith("'=")  # Workflow name
    assert rows[1][6].startswith("'=")  # Model（子のモデル別集計）
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
