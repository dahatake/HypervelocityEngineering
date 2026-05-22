from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_workflow_select import WorkflowSelectPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_autopilot_default_off(qapp) -> None:
    page = WorkflowSelectPage()
    assert page.is_autopilot_enabled() is False


def test_autopilot_toggle_keeps_workflow_checkboxes_enabled(qapp) -> None:
    page = WorkflowSelectPage()

    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == "aad-web":
            btn.setChecked(True)
            break

    page._autopilot_cb.setChecked(True)  # type: ignore[attr-defined]

    assert page.is_autopilot_enabled() is True
    assert any(btn.isEnabled() for btn in page._group.buttons())  # type: ignore[attr-defined]


def test_autopilot_disables_step_groups_added_later(qapp) -> None:
    page = WorkflowSelectPage()
    page._autopilot_cb.setChecked(True)  # type: ignore[attr-defined]

    for btn in page._group.buttons():  # type: ignore[attr-defined]
        if btn.property("workflow_id") == "aad-web":
            btn.setChecked(True)
            break

    grp = page._step_groups.get("aad-web")  # type: ignore[attr-defined]
    assert grp is not None
    assert grp.isEnabled() is False


def test_autopilot_catalog_path_field(qapp) -> None:
    page = WorkflowSelectPage()
    page.set_autopilot_catalog_path("docs/catalog/custom.md")
    assert page.autopilot_catalog_path() == "docs/catalog/custom.md"


def test_autopilot_signal_emitted(qapp) -> None:
    page = WorkflowSelectPage()
    got = []
    page.autopilot_changed.connect(lambda enabled, path: got.append((enabled, path)))

    page._autopilot_cb.setChecked(True)  # type: ignore[attr-defined]
    page._autopilot_catalog_edit.setText("x.md")  # type: ignore[attr-defined]

    assert got
    assert got[-1] == (True, "x.md")