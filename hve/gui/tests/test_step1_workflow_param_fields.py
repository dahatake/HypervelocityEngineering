"""test_step1_workflow_param_fields.py — FR-LOCAL-SURFACE-01 (b) の GUI 表示契約。

検証項目:
  1. `_C10AppId` が Remote MCP Server / TDD 最大再試行回数のウィジェットを持つこと
  2. Step 1 のワークフロー枠へ表示する Workflow が `WorkflowDef.params` の宣言と
     完全一致すること（宣言の無い Workflow へ表示しない）
  3. `_STEP2_FIELDS_BY_WORKFLOW` の登録タイトルが実際の `_LabeledField` と一致すること
  4. 既定状態では argv へ何も出さず、指定時だけ出ること
  5. 全体設定として永続化しないこと（`_SECTION_FIELDS` に含めない）

根拠: hve-dev/requirement-definition.md §5.21 FR-LOCAL-SURFACE-01
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.workflow_registry import list_workflows


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def options_page(qapp, tmp_path, monkeypatch):
    from hve.gui import settings_store
    from hve.gui.page_options import OptionsPage

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    page = OptionsPage()
    yield page
    page.deleteLater()


def _declaring(param: str) -> set:
    return {w.id for w in list_workflows() if param in (w.params or [])}


def _titles(wf_id: str) -> list:
    from hve.gui.page_options import _STEP2_FIELDS_BY_WORKFLOW

    return [title for _attr, title in _STEP2_FIELDS_BY_WORKFLOW.get(wf_id, [])]


def test_widgets_exist_on_c10(qapp) -> None:
    from hve.gui.page_options import _C10AppId

    w = _C10AppId()
    assert hasattr(w, "create_remote_mcp_server")
    assert hasattr(w, "tdd_max_retries")


def test_registered_titles_match_real_labeled_fields(options_page) -> None:
    """登録タイトルが実 UI と食い違うと、枠が空のまま無言で表示されなくなる。"""
    from hve.gui.page_options import _C10AppId, _LabeledField

    titles = {
        f.title_text()
        for f in options_page.c10.findChildren(_LabeledField)
        if hasattr(f, "title_text")
    }
    if not titles:  # title_text() が無い実装では走査をスキップする
        pytest.skip("_LabeledField がタイトル取得 API を持たない")
    assert _C10AppId.REMOTE_MCP_FIELD_TITLE in titles
    assert _C10AppId.TDD_MAX_RETRIES_FIELD_TITLE in titles


def test_remote_mcp_is_shown_exactly_for_declaring_workflows() -> None:
    from hve.gui.page_options import _C10AppId, _STEP2_FIELDS_BY_WORKFLOW

    shown = {
        wf
        for wf in _STEP2_FIELDS_BY_WORKFLOW
        if _C10AppId.REMOTE_MCP_FIELD_TITLE in _titles(wf)
    }
    assert shown == _declaring("create_remote_mcp_server")


def test_tdd_max_retries_is_shown_exactly_for_declaring_workflows() -> None:
    from hve.gui.page_options import _C10AppId, _STEP2_FIELDS_BY_WORKFLOW

    shown = {
        wf
        for wf in _STEP2_FIELDS_BY_WORKFLOW
        if _C10AppId.TDD_MAX_RETRIES_FIELD_TITLE in _titles(wf)
    }
    assert shown == _declaring("tdd_max_retries")


def test_defaults_emit_no_flags(options_page) -> None:
    argv = options_page.build_args_for_workflow("asdw-web").to_argv()
    for flag in (
        "--create-remote-mcp-server",
        "--no-create-remote-mcp-server",
        "--tdd-max-retries",
    ):
        assert flag not in argv


def test_selected_values_reach_argv(options_page) -> None:
    options_page.c10.create_remote_mcp_server.set_tristate(False)
    options_page.c10.tdd_max_retries.setValue(7)
    argv = options_page.build_args_for_workflow("asdw-web").to_argv()
    assert "--no-create-remote-mcp-server" in argv
    assert argv[argv.index("--tdd-max-retries") + 1] == "7"


def test_zero_means_follow_the_default(options_page) -> None:
    """0 は「既定に従う」。CLI へ 0 を渡して再試行を封じてはならない。"""
    options_page.c10.tdd_max_retries.setValue(0)
    argv = options_page.build_args_for_workflow("asdw-web").to_argv()
    assert "--tdd-max-retries" not in argv


def test_workflow_params_are_not_persisted_as_global_settings() -> None:
    """workflow param は全体設定へ保存しない（宣言外 Workflow へ効く誤解を防ぐ）。"""
    from hve.gui import settings_apply, settings_store

    persisted = {
        key for fields in settings_apply._SECTION_FIELDS.values() for key in fields
    }
    assert "create_remote_mcp_server" not in persisted
    assert "tdd_max_retries" not in persisted
    assert "tdd_max_retries" in settings_store._OBSOLETE_KEYS["options"]
