"""test_page_options_km_background_merge.py — FR-QA-05 / FR-GUI-20 の GUI 契約。

QA 回答を Knowledge Management へバックグラウンドでマージするかどうかを、
設定画面の `Knowledge Management` ノードと Step 1 右ペインの「共通設定」枠の
双方から選択できることを検証する。

実装前は該当ウィジェットが存在しないため全件 RED となる。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from hve.gui.page_options import (  # noqa: E402
    _AKM_CONTEXT_TIER_FIELD_TITLE,
    _AKM_MODEL_FIELD_TITLE,
    _AUTO_QA_FIELD_TITLE,
    _QA_AKM_MERGE_FIELD_TITLE,
    _QA_ANSWER_MODE_FIELD_TITLE,
    OptionsPage,
    _LabeledField,
)

_ALL_WORKFLOWS = (
    "ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
    "aag", "aagd", "aar", "akm", "adi", "adoc",
)

_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _visible_common_titles(page: OptionsPage) -> List[str]:
    titles: List[str] = []
    for lf in page.c3.findChildren(_LabeledField):
        if not lf.isVisible():
            continue
        lbl = lf.findChild(QLabel)
        if lbl is None:
            continue
        titles.append(lbl.text().split("  *")[0].strip())
    return titles


class TestKmMergeWidgetExists(unittest.TestCase):
    """ウィジェットの存在と既定値。"""

    def test_widget_exists_on_the_km_section(self) -> None:
        _get_app()
        from hve.gui.page_options import _CKnowledgeManagement

        widget = _CKnowledgeManagement()
        try:
            self.assertTrue(hasattr(widget, "qa_akm_background_merge"))
            self.assertFalse(widget.qa_akm_background_merge.isChecked())
        finally:
            widget.deleteLater()

    def test_widget_is_reachable_from_the_common_section(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            self.assertFalse(page.c3.qa_akm_background_merge.isChecked())
        finally:
            page.deleteLater()


class TestKmMergeVisibleInRightPane(unittest.TestCase):
    """Step 1 右ペインの共通枠での可視と表示順（FR-GUI-20）。"""

    _EXPECTED_ORDER = [
        _AUTO_QA_FIELD_TITLE,
        _QA_ANSWER_MODE_FIELD_TITLE,
        _QA_AKM_MERGE_FIELD_TITLE,
        _AKM_MODEL_FIELD_TITLE,
        _AKM_CONTEXT_TIER_FIELD_TITLE,
        "追加プロンプト",
    ]

    def test_visible_for_all_workflows_in_the_declared_order(self) -> None:
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                with self.subTest(workflow=wf):
                    page.set_workflows([wf], {wf: wf})
                    self.assertEqual(_visible_common_titles(page), self._EXPECTED_ORDER)
        finally:
            page.deleteLater()

    def test_labels_use_the_spelled_out_terms(self) -> None:
        self.assertEqual(_AUTO_QA_FIELD_TITLE, "QA (質問票) 自動投入")
        self.assertEqual(_QA_ANSWER_MODE_FIELD_TITLE, "QA (質問票) 回答モード")
        self.assertEqual(_AKM_MODEL_FIELD_TITLE, "Knowledge Management 用モデル")
        self.assertEqual(
            _AKM_CONTEXT_TIER_FIELD_TITLE, "Knowledge Management 用コンテキスト階層",
        )
        self.assertEqual(
            _QA_AKM_MERGE_FIELD_TITLE,
            "QA (質問票) を Knowledge Management へバックグラウンドでマージする",
        )


class TestKmMergeGating(unittest.TestCase):
    """`auto_qa` 連動と、マージ無効時の AKM 実行品質の非活性化。"""

    def test_disabled_while_auto_qa_is_unselected(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            self.assertFalse(page.c3.qa_akm_background_merge.isEnabled())
        finally:
            page.deleteLater()

    def test_enabled_when_auto_qa_is_on(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            self.assertTrue(page.c3.qa_akm_background_merge.isEnabled())
        finally:
            page.deleteLater()

    def test_akm_quality_stays_disabled_while_merge_is_off(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            self.assertFalse(page.c3.qa_akm_background_merge.isChecked())
            self.assertFalse(page.c3.akm_model.isEnabled())
            self.assertFalse(page.c3.akm_context_tier.isEnabled())
        finally:
            page.deleteLater()

    def test_akm_quality_activates_when_merge_is_on(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)
            self.assertTrue(page.c3.akm_model.isEnabled())
            self.assertTrue(page.c3.akm_context_tier.isEnabled())
        finally:
            page.deleteLater()


class TestKmMergeArgsPropagation(unittest.TestCase):
    """`OrchestrateArgs` と argv への伝播。"""

    def test_value_reaches_args(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)
            args = page.build_args_for_workflow("aas")
            self.assertTrue(args.qa_akm_background_merge)
        finally:
            page.deleteLater()

    def test_value_is_false_by_default(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            args = page.build_args_for_workflow("aas")
            self.assertFalse(args.qa_akm_background_merge)
        finally:
            page.deleteLater()

    def test_auto_qa_off_suppresses_the_value(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)
            page.c3.auto_qa.set_tristate(False)
            args = page.build_args_for_workflow("aas")
            self.assertFalse(args.qa_akm_background_merge)
        finally:
            page.deleteLater()

    def test_merge_off_suppresses_akm_quality_values(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)
            index = page.c3.akm_context_tier.findData("default")
            page.c3.akm_context_tier.setCurrentIndex(index)
            page.c3.qa_akm_background_merge.setChecked(False)
            args = page.build_args_for_workflow("aas")
            self.assertIsNone(args.akm_model)
            self.assertIsNone(args.akm_reasoning_effort)
            self.assertIsNone(args.akm_context_tier)
        finally:
            page.deleteLater()

    def test_argv_round_trip(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(workflow="aas", qa_akm_background_merge=True).to_argv()
        self.assertIn("--qa-akm-background-merge", argv)

    def test_argv_omits_the_flag_when_disabled(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(workflow="aas").to_argv()
        self.assertNotIn("--qa-akm-background-merge", argv)


class TestKmMergeSettingsDefaults(unittest.TestCase):
    """設定ストアの既定値。"""

    def test_store_default_is_false(self) -> None:
        from hve.gui import settings_store

        self.assertIs(
            settings_store.defaults()["options"]["qa_akm_background_merge"], False,
        )


if __name__ == "__main__":
    unittest.main()
