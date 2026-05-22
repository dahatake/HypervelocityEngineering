"""T8: settings_window の precheck_use_llm_judge トグル永続化テスト。

`_CAutopilotSection` 内に追加した `precheck_use_llm_judge` チェックボックスが、
- settings_store.defaults() に既定値 True を持つ
- settings_apply._SECTION_FIELDS["AUTOPILOT"] に登録されている
- apply_to_widgets / collect_from_widgets で双方向に値が反映される
ことを検証する（T7 で導入した配線の回帰防止）。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui import settings_apply, settings_store
from hve.gui.settings_window import _CAutopilotSection


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestPrecheckUseLlmJudgeSetting:
    def test_default_value_is_true(self, qapp) -> None:
        opts = settings_store.defaults()["options"]
        assert opts["precheck_use_llm_judge"] is True

    def test_section_fields_registers_key(self, qapp) -> None:
        fields = settings_apply._SECTION_FIELDS["AUTOPILOT"]
        assert fields.get("precheck_use_llm_judge") == "precheck_use_llm_judge"

    def test_widget_has_checkbox_attribute(self, qapp) -> None:
        from PySide6.QtWidgets import QCheckBox
        w = _CAutopilotSection()
        assert hasattr(w, "precheck_use_llm_judge")
        assert isinstance(w.precheck_use_llm_judge, QCheckBox)

    def test_apply_to_widgets_writes_value(self, qapp) -> None:
        w = _CAutopilotSection()
        settings_apply.apply_to_widgets(
            {"AUTOPILOT": w},
            {"options": {"precheck_use_llm_judge": False}},
        )
        assert w.precheck_use_llm_judge.isChecked() is False

        settings_apply.apply_to_widgets(
            {"AUTOPILOT": w},
            {"options": {"precheck_use_llm_judge": True}},
        )
        assert w.precheck_use_llm_judge.isChecked() is True

    def test_collect_from_widgets_reads_value(self, qapp) -> None:
        w = _CAutopilotSection()
        w.precheck_use_llm_judge.setChecked(True)
        out = settings_apply.collect_from_widgets({"AUTOPILOT": w})
        assert out["precheck_use_llm_judge"] is True

        w.precheck_use_llm_judge.setChecked(False)
        out = settings_apply.collect_from_widgets({"AUTOPILOT": w})
        assert out["precheck_use_llm_judge"] is False
