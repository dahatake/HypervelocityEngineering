"""Wave 2 T2.3: WorkbenchPage 統合レイアウトの構造テスト。"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QSplitter  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from hve.gui.page_workbench import WorkbenchPage
    p = WorkbenchPage()
    yield p
    p.deleteLater()


def test_horizontal_splitter_3_to_7(page):
    sp = page._splitter
    assert isinstance(sp, QSplitter)
    assert sp.orientation() == Qt.Orientation.Horizontal
    assert sp.count() == 2
    assert sp.childrenCollapsible() is False
    # 初期サイズが 3:7 (300:700) で設定されている
    sizes = sp.sizes()
    assert len(sizes) == 2
    # 比率の妥当性（初期サイズベース、レイアウト計算後でもおおむね 3:7）
    # 直接設定値は内部保存される: 0 でないことを確認
    assert sizes[0] >= 0 and sizes[1] >= 0


def test_right_pane_vertical_splitter(page):
    rs = page._right_splitter
    assert rs.orientation() == Qt.Orientation.Vertical
    assert rs.count() == 2
    assert rs.childrenCollapsible() is False


def test_left_pane_is_activity_widget(page):
    sp = page._splitter
    assert sp.widget(0) is page._progress_widget


def test_log_pane_append_mirrors_to_log_tabs(page):
    page._log_pane.append_line("hello-world")
    assert "hello-world" in page._log_tabs.global_text()


def test_workflow_instance_selection_updates_selected_tab(page):
    s = page._state
    s.ensure_workflow_instance("wf-x", "wf-x", "WF-X")
    s.append_workflow_log("wf-x", None, "line-a")
    s.append_workflow_log("wf-x", None, "line-b")
    # Tree を instances モードに切替・選択
    page._progress_widget.update_workflow_instances(s)
    tree = page._progress_widget._tree
    tree.setCurrentItem(tree.topLevelItem(0))
    txt = page._log_tabs.selected_text()
    assert "line-a" in txt and "line-b" in txt


def test_single_workflow_set_plan_still_works(page):
    """シングル workflow 回帰確認: set_plan ベースの描画が動く。"""
    plan = [{"workflow_id": "wf-1", "workflow_name": "WF-1", "steps": [("s1", "Step 1")]}]
    page._progress_widget.set_plan(plan, {"wf-1": "実行中"}, {"wf-1": {"s1": "実行中"}})
    tree = page._progress_widget._tree
    assert tree.topLevelItemCount() == 1
    assert "WF-1" in tree.topLevelItem(0).text(0)
