"""FR-LOCAL-SURFACE-01: GUI の Workflow 固有値を宣言元だけへ射影する。"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui.page_options import OptionsPage
from hve.workflow_registry import list_workflows


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _set_akm_values(page: OptionsPage) -> None:
    page.c11.sources_qa.setChecked(True)
    page.c11.sources_original_docs.setChecked(False)
    page.c11.sources_workiq.setChecked(True)
    page.c11.target_files.setText("qa/member.md")
    page.c11.force_refresh.set_tristate(True)
    page.c11.custom_source_dir.setText("docs/custom")


def _akm_values(args) -> dict:
    return {
        "sources": args.sources,
        "target_files": args.target_files,
        "force_refresh": args.force_refresh,
        "custom_source_dir": args.custom_source_dir,
    }


def test_gui_scopes_akm_params_to_akm(qapp) -> None:
    page = OptionsPage()
    try:
        _set_akm_values(page)
        actual = {
            workflow.id: _akm_values(page.build_args_for_workflow(workflow.id))
            for workflow in list_workflows()
        }
        empty = {
            "sources": None,
            "target_files": [],
            "force_refresh": None,
            "custom_source_dir": [],
        }
        expected = {
            workflow.id: (
                {
                    "sources": "workiq,qa",
                    "target_files": ["qa/member.md"],
                    "force_refresh": True,
                    "custom_source_dir": ["docs/custom"],
                }
                if workflow.id == "akm"
                else empty
            )
            for workflow in list_workflows()
        }
        mismatches = {
            workflow_id: {"actual": values, "expected": expected[workflow_id]}
            for workflow_id, values in actual.items()
            if values != expected[workflow_id]
        }

        assert mismatches == {}
    finally:
        page.deleteLater()
