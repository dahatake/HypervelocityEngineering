"""左 workflow チェック → 右 OptionsPage 即時同期の回帰テスト。

Step 1 右ペインは「ワークフロー単位の QGroupBox」で固有設定を表示する設計のため、
左の workflow 選択変更が `_workflow_group_boxes` に即時反映されることを検証する。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.gui.page_options import OptionsPage
from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_options_page_initially_empty(qapp) -> None:
    """workflow 未選択時は workflow group box が 1 つも作られない。"""
    options = OptionsPage()
    assert options._workflow_group_boxes == {}


def test_options_page_updates_on_set_workflows_ard(qapp) -> None:
    """ARD 選択 → `ard` の workflow group box が生成される。"""
    options = OptionsPage()
    options.set_workflows(["ard"], {"ard": "ARD"})
    assert "ard" in options._workflow_group_boxes
    # 他のワークフロー枠は作られない
    for other in ("aad-web", "asdw-web", "adfd", "adfdv", "akm", "aqod", "adoc"):
        assert other not in options._workflow_group_boxes


def test_options_page_updates_on_set_workflows_aad_web(qapp) -> None:
    """aad-web 選択 → `aad-web` の workflow group box が生成される。"""
    options = OptionsPage()
    options.set_workflows(["aad-web"], {"aad-web": "AAD Web"})
    assert "aad-web" in options._workflow_group_boxes


def test_options_page_clears_when_workflow_unset(qapp) -> None:
    """workflow を空に戻すと workflow group box は全て破棄される。"""
    options = OptionsPage()
    options.set_workflows(["aad-web"], {"aad-web": "AAD Web"})
    assert "aad-web" in options._workflow_group_boxes
    options.set_workflows([], {})
    assert options._workflow_group_boxes == {}


def test_options_page_category_groups_always_hidden(qapp) -> None:
    """旧カテゴリ枠 (C4 / C10〜C14) は workflow 選択に関係なく常時非表示。"""
    options = OptionsPage()
    options.set_workflows(["ard", "aad-web"], {"ard": "ARD", "aad-web": "AAD Web"})
    for key in ("C4", "C10", "C11", "C12", "C13", "C14"):
        g = options._category_groups.get(key)
        assert g is not None
        assert g.isHidden(), f"{key} should be hidden"


def test_workflow_select_page_has_no_autopilot_input_panel(qapp) -> None:
    """旧 AutopilotInputPanel は完全に削除されている。"""
    w = WorkflowSelectPage()
    assert not hasattr(w, "autopilot_input_panel")
    assert not hasattr(w, "_autopilot_input_panel")
    assert not hasattr(w, "_right_splitter")


def test_options_page_no_per_section_api(qapp) -> None:
    """OptionsPage の per-workflow セクション API も削除されている。"""
    options = OptionsPage()
    assert not hasattr(options, "create_per_workflow_section")
    assert not hasattr(options, "build_args_for_workflow_using_section")
