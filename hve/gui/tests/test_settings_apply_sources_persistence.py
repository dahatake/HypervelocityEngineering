"""hve.gui.tests.test_settings_apply_sources_persistence

C11 (_C11AKM) の sources_qa / sources_original_docs / sources_workiq
3 チェックボックスが settings_apply の汎用 autosave 経路に乗っており、
``collect_from_widgets`` / ``apply_to_widgets`` で双方向に値が反映される
ことを検証する。

過去実装では `_SECTION_FIELDS["C11"]` に未登録のため、これらは
``hve/.settings.txt`` に保存されていなかった（NOTE コメントで明示）。
本テストは登録漏れを再発させないための回帰防止。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from hve.gui import settings_apply, settings_store
from hve.gui.page_options import _C11AKM


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestC11SourcesPersistence:
    def test_section_fields_includes_three_sources_keys(self, qapp) -> None:
        fields = settings_apply._SECTION_FIELDS["C11"]
        assert fields["sources_qa"] == "sources_qa"
        assert fields["sources_original_docs"] == "sources_original_docs"
        assert fields["sources_workiq"] == "sources_workiq"

    def test_defaults_include_three_sources_keys(self, qapp) -> None:
        opts = settings_store.defaults()["options"]
        # _C11AKM の初期 setChecked と整合させる（qa=True, original_docs=True, workiq=False）
        assert opts["sources_qa"] is True
        assert opts["sources_original_docs"] is True
        assert opts["sources_workiq"] is False

    def test_collect_from_widgets_reads_sources(self, qapp) -> None:
        widget = _C11AKM()
        widget.sources_qa.setChecked(False)
        widget.sources_original_docs.setChecked(True)
        widget.sources_workiq.setChecked(True)

        out = settings_apply.collect_from_widgets({"C11": widget})
        assert out["sources_qa"] is False
        assert out["sources_original_docs"] is True
        assert out["sources_workiq"] is True

    def test_apply_to_widgets_writes_sources(self, qapp) -> None:
        widget = _C11AKM()
        settings_apply.apply_to_widgets(
            {"C11": widget},
            {
                "options": {
                    "sources_qa": False,
                    "sources_original_docs": False,
                    "sources_workiq": True,
                }
            },
        )
        assert widget.sources_qa.isChecked() is False
        assert widget.sources_original_docs.isChecked() is False
        assert widget.sources_workiq.isChecked() is True

    def test_c10_section_has_no_duplicate_app_id_entries(self, qapp) -> None:
        # dict リテラル重複が再混入していないことを確認（同名キー = 1 個のみ）。
        fields = settings_apply._SECTION_FIELDS["C10"]
        assert list(fields.keys()).count("app_id") == 1
