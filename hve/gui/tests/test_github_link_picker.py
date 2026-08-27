"""FR-GUI-32: 実行タスクへ関連付ける Issue / PR の選択（設定 C5）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def section(qapp):
    from hve.gui.page_options import _C5IssuePR

    widget = _C5IssuePR()
    widget.repo.setText("o/r")
    yield widget
    widget.deleteLater()


class _StubDialog:
    """`GitHubPickerDialog` の差し替え用。生成引数と戻り値を記録する。"""

    instances: List["_StubDialog"] = []
    accept = True
    number: Any = 123

    def __init__(self, repo, kind, parent=None) -> None:
        self.repo = repo
        self.kind = kind
        self.shutdown_called = False
        _StubDialog.instances.append(self)

    def exec(self) -> int:
        return (
            QDialog.DialogCode.Accepted
            if _StubDialog.accept
            else QDialog.DialogCode.Rejected
        )

    def selected_number(self):
        return _StubDialog.number

    def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.fixture
def stub_dialog(monkeypatch):
    from hve.gui import github_picker_dialog as module

    _StubDialog.instances = []
    _StubDialog.accept = True
    _StubDialog.number = 123
    monkeypatch.setattr(module, "GitHubPickerDialog", _StubDialog)
    return _StubDialog


class TestIssuePicker:
    def test_button_exists(self, section) -> None:
        assert section.pick_issue_button is not None

    def test_button_follows_issue_mode(self, section) -> None:
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("new"))
        assert not section.pick_issue_button.isEnabled()
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        assert section.pick_issue_button.isEnabled()

    def test_selection_fills_issue_number(self, section, stub_dialog) -> None:
        stub_dialog.number = 4242
        section._on_pick_issue_clicked()
        assert section.issue_number.text() == "4242"
        assert stub_dialog.instances[-1].kind == "issue"
        assert stub_dialog.instances[-1].repo == "o/r"

    def test_cancel_keeps_previous_value(self, section, stub_dialog) -> None:
        section.issue_number.setText("11")
        stub_dialog.accept = False
        section._on_pick_issue_clicked()
        assert section.issue_number.text() == "11"

    def test_no_selection_keeps_previous_value(self, section, stub_dialog) -> None:
        section.issue_number.setText("11")
        stub_dialog.number = None
        section._on_pick_issue_clicked()
        assert section.issue_number.text() == "11"

    def test_direct_input_is_still_available(self, section) -> None:
        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        section.issue_number.setText("777")
        assert section.issue_number.text() == "777"
        assert section.issue_number.isEnabled()

    def test_dialog_is_shut_down(self, section, stub_dialog) -> None:
        section._on_pick_issue_clicked()
        assert stub_dialog.instances[-1].shutdown_called


class TestPullRequestLink:
    def test_field_and_button_exist(self, section) -> None:
        assert section.linked_pr_number is not None
        assert section.pick_pr_button is not None

    def test_selection_fills_pr_number(self, section, stub_dialog) -> None:
        stub_dialog.number = 99
        section._on_pick_pull_request_clicked()
        assert section.linked_pr_number.text() == "99"
        assert stub_dialog.instances[-1].kind == "pr"

    def test_cancel_keeps_previous_value(self, section, stub_dialog) -> None:
        section.linked_pr_number.setText("5")
        stub_dialog.accept = False
        section._on_pick_pull_request_clicked()
        assert section.linked_pr_number.text() == "5"

    def test_persisted_as_c5_option(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS
        from hve.gui.settings_store import defaults

        assert _SECTION_FIELDS["C5"]["linked_pr_number"] == "linked_pr_number"
        assert defaults()["options"]["linked_pr_number"] == ""

    def test_round_trips_through_settings_apply(self, section) -> None:
        from hve.gui.settings_apply import apply_to_widgets, collect_from_widgets

        apply_to_widgets({"C5": section}, {"options": {"linked_pr_number": "321"}})
        assert section.linked_pr_number.text() == "321"
        assert collect_from_widgets({"C5": section})["linked_pr_number"] == "321"


class TestNoOrchestratorPropagation:
    """FR-GUI-32: PR 番号を Orchestrator へ伝達しないこと。"""

    def test_field_is_not_declared_on_orchestrate_args(self) -> None:
        from dataclasses import fields

        from hve.gui.orchestrate_args import OrchestrateArgs

        names = {f.name for f in fields(OrchestrateArgs)}
        assert not any("pr_number" in name for name in names), names

    def test_pr_number_does_not_reach_argv(self, section) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        section.issue_mode.setCurrentIndex(section.issue_mode.findData("existing"))
        section.issue_number.setText("12")
        section.linked_pr_number.setText("99")
        args = OrchestrateArgs(workflow="ard")
        section.to_args(args)
        argv = args.to_argv()
        assert "--pr-number" not in argv
        assert "99" not in argv
        assert "--issue-number" in argv

    def test_sdk_config_has_no_pr_number_field(self) -> None:
        from dataclasses import fields

        from hve.config import SDKConfig

        names = {f.name for f in fields(SDKConfig)}
        assert not any("pr_number" in name for name in names), names

    def test_collected_options_are_not_sent_as_cli_flags(self, section) -> None:
        from hve.gui.settings_apply import collect_from_widgets

        section.linked_pr_number.setText("99")
        collected: Dict[str, Any] = collect_from_widgets({"C5": section})
        assert collected["linked_pr_number"] == "99"
        # OrchestrateArgs に同名フィールドが無いこと（settings→args の橋渡し対象外）
        from hve.gui.orchestrate_args import OrchestrateArgs

        assert not hasattr(OrchestrateArgs(workflow="ard"), "linked_pr_number")
