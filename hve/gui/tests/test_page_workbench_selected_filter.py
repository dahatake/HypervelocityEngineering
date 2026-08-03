"""hve.gui.tests.test_page_workbench_selected_filter

「選択中」タブのフィルタロジック（``_filter_lines_for_step`` /
``_build_step_label_pattern``）の単体テスト。

autopilot 経路では fan-out 子ログが ``[main]`` プレフィックスへ落ち、行本文にのみ
``[<base>/<child>]`` ラベルが残る。選択したサブコンポーネント/サブプロセスに
関連する行を log_buffer から抽出できることを検証する。
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import (  # noqa: E402
    WorkbenchPage,
    _build_step_label_pattern,
)
from hve.gui.workbench_state import WorkflowInstance  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_inst() -> WorkflowInstance:
    return WorkflowInstance(instance_id="wf", workflow_id="wf", label="WF")


# ---------- _build_step_label_pattern（純関数・QApplication 不要） ----------


def test_pattern_matches_body_label_and_step_prefix():
    """本文ラベル ``[<id>]`` と ``[Step.<id>]`` の両形式にマッチする。"""
    pat = _build_step_label_pattern("4.1/APP-009-S010")
    assert pat.search("[ASDW-WEB] [main] 🔄 [4.1/APP-009-S010] ターン開始")
    assert pat.search("[ASDW-WEB] [main] ⏱ [Step.4.1/APP-009-S010] 0m 29s 経過...")


def test_pattern_excludes_sibling_ids():
    """別の fan-out 子 ID の行はマッチしない。"""
    pat = _build_step_label_pattern("4.1/APP-009-S010")
    assert pat.search("[ASDW-WEB] [main] [4.1/APP-009-S001] event") is None


def test_pattern_no_partial_prefix_match():
    """``4.1`` は ``[4.10]`` のような別 ID にマッチしない（末尾 ``]`` 固定）。"""
    pat = _build_step_label_pattern("4.1")
    assert pat.search("[4.1]") is not None
    assert pat.search("[4.10]") is None


def test_pattern_parent_matches_descendants():
    """親 step ``4.1`` は子孫 ``[4.1/...]`` にもマッチする。"""
    pat = _build_step_label_pattern("4.1")
    assert pat.search("[4.1/APP-009-S010]") is not None


# ---------- _filter_lines_for_step ----------


def test_filter_fanout_child_extracts_main_labeled_lines(qapp):
    """fan-out 子選択時、[main] へ落ちた本文ラベル行を抽出し、別子は除外する。"""
    page = WorkbenchPage()
    inst = _make_inst()
    inst.log_buffer = [
        "[ASDW-WEB] [main] 🔄 [4.1/APP-009-S010] ターン開始",
        "[ASDW-WEB] [main] 📏 [4.1/APP-009-S010] Context: 38815/922000",
        "[ASDW-WEB] [main] 🔄 [4.1/APP-009-S001] ターン開始",
    ]
    result = page._filter_lines_for_step(inst, "4.1/APP-009-S010")
    assert len(result) == 2
    assert all("S010" in ln for ln in result)
    assert all("S001" not in ln for ln in result)


def test_filter_parent_step_includes_descendants(qapp):
    """親 step 選択時、自身の行と子孫 fan-out 子の行を両方含める。"""
    page = WorkbenchPage()
    inst = _make_inst()
    inst.log_buffer = [
        "[ASDW-WEB] [4.1] base line",
        "[ASDW-WEB] [main] [4.1/APP-009-S010] child line",
    ]
    result = page._filter_lines_for_step(inst, "4.1")
    assert len(result) == 2


def test_filter_excludes_unlabeled_continuation_lines(qapp):
    """本文ラベルを持たない継続行（skill 単独行等）は抽出されない。"""
    page = WorkbenchPage()
    inst = _make_inst()
    inst.log_buffer = [
        "[ASDW-WEB] [main] 🔄 [4.1/APP-009-S010] ターン開始",
        "[ASDW-WEB] [main] skill",
    ]
    result = page._filter_lines_for_step(inst, "4.1/APP-009-S010")
    assert len(result) == 1
    assert "skill" not in "\n".join(result)


def test_filter_subagent_falls_back_to_parent(qapp):
    """subagent ノード（parent::subagent::name）は親 step_id にフォールバックする。"""
    page = WorkbenchPage()
    inst = _make_inst()
    inst.log_buffer = [
        "[ASDW-WEB] [4.1] parent line",
    ]
    result = page._filter_lines_for_step(inst, "4.1::subagent::worker-a")
    assert result == ["[ASDW-WEB] [4.1] parent line"]


def test_filter_empty_falls_back_to_step_log_buffers(qapp):
    """一致 0 行のときは step_log_buffers の完全一致バッファへフォールバックする。"""
    page = WorkbenchPage()
    inst = _make_inst()
    inst.log_buffer = ["[ASDW-WEB] [main] unrelated"]
    inst.step_log_buffers = {"9.9": ["[WF] [9.9] buffered"]}
    result = page._filter_lines_for_step(inst, "9.9")
    assert result == ["[WF] [9.9] buffered"]
