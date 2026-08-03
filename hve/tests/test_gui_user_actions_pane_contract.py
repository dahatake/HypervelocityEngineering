"""Qt-free contract tests for GUI UserActions pane behavior.

These tests intentionally avoid importing ``hve.gui.page_workbench`` because
PySide6 is optional in some local test environments. They pin only the minimal
source-level contract needed for the Workbench UserActions pane.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAGE_WORKBENCH = _REPO_ROOT / "hve" / "gui" / "page_workbench.py"
_WORKBENCH_STATE = _REPO_ROOT / "hve" / "gui" / "workbench_state.py"


def _enhanced_user_actions_update_source() -> str:
    source = _PAGE_WORKBENCH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "_EnhancedUserActionsPane":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "update_from_state":
                    segment = ast.get_source_segment(source, item)
                    assert segment is not None
                    return segment
    raise AssertionError("_EnhancedUserActionsPane.update_from_state not found")


def _workbench_state_add_user_action_source() -> str:
    source = _WORKBENCH_STATE.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "WorkbenchState":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "add_user_action":
                    segment = ast.get_source_segment(source, item)
                    assert segment is not None
                    return segment
    raise AssertionError("WorkbenchState.add_user_action not found")


def test_gui_user_actions_pane_uses_retained_actions_not_last_five_view() -> None:
    update_source = _enhanced_user_actions_update_source()

    assert "state.user_actions_view()" not in update_source
    assert "for action in state.user_actions" in update_source


def test_gui_user_actions_pane_updates_header_with_total_count() -> None:
    update_source = _enhanced_user_actions_update_source()

    assert "len(state.user_actions)" in update_source
    assert "self._header.setText" in update_source
    assert "({total})" in update_source


def test_gui_user_actions_state_has_no_retention_limit() -> None:
    add_user_action_source = _workbench_state_add_user_action_source()

    assert "self.user_actions.append(action)" in add_user_action_source
    assert "USER_ACTIONS_CAPACITY" not in add_user_action_source
    assert ".pop(" not in add_user_action_source
