"""FR-LOCAL-SURFACE-01: GUI と Prompt の argv 完全一致契約。"""

from __future__ import annotations

from difflib import unified_diff

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui import settings_apply, settings_store
from hve.gui.orchestrate_args import args_from_settings
from hve.gui.page_options import OptionsPage
from hve.workflow_registry import list_workflows


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _sections(page: OptionsPage) -> dict:
    return {
        "C1": page.c1,
        "QA": page.c3,
        "REVIEW": page.c3,
        "KM": page.c3,
        "SELFIMPROVE": page.c3,
        "C4": page.c4,
        "C5": page.c5,
        "C7": page.c7,
        "AZURE": page.c_azure,
        "AGENTIC": page.c_agentic,
        "C10": page.c10,
        "C11": page.c11,
        "C13": page.c13,
        "C17": page.c17,
        "C14": page.c14,
    }


def _saved_settings(scenario: str) -> dict:
    saved = settings_store.defaults()
    if scenario == "non_defaults":
        saved["options"].update(
            {
                "auto_qa": "on",
                "qa_answer_mode": "autopilot",
                "self_improve": "on",
                "self_improve_max_iterations": 7,
                "self_improve_target_scope": "hve",
                "self_improve_goal": "設定面を改善する",
                "tool_search_ranking": "hve",
                "sources_qa": True,
                "sources_original_docs": False,
                "sources_workiq": True,
                "ignore_paths": "work/one work/two",
                "target_files": "qa/member-a.md qa/member-b.md",
                "force_refresh": "on",
                "custom_source_dir": "docs/custom-a docs/custom-b",
            }
        )
    return saved


@pytest.mark.parametrize("scenario", ["defaults", "non_defaults"])
def test_gui_and_prompt_generate_identical_argv(
    qapp, scenario: str, tmp_path, monkeypatch
) -> None:
    saved = _saved_settings(scenario)
    monkeypatch.setattr(settings_store, "_SETTINGS_PATH", tmp_path / ".settings.txt")
    settings_store.save(saved)
    saved = settings_store.load()

    page = OptionsPage()
    try:
        mismatch_groups = {}
        for workflow in list_workflows():
            page.set_workflow(workflow.id)
            settings_apply.apply_to_widgets(_sections(page), saved)

            gui_argv = page.build_args_for_workflow(workflow.id).to_argv()
            prompt_argv = args_from_settings(saved, workflow=workflow.id).to_argv()
            if gui_argv != prompt_argv:
                diff = tuple(
                    unified_diff(
                        gui_argv,
                        prompt_argv,
                        fromfile="gui",
                        tofile="prompt",
                        lineterm="",
                    )
                )
                mismatch_groups.setdefault(diff, []).append(workflow.id)

        mismatches = [
            {"workflows": workflow_ids, "diff": list(diff)}
            for diff, workflow_ids in mismatch_groups.items()
        ]

        assert mismatches == []
    finally:
        page.deleteLater()
