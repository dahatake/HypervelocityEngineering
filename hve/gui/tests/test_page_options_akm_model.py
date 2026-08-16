"""test_page_options_akm_model.py — AKM 用実行品質設定の GUI 契約。

FR-GUI-17: FR-QA-04 の `akm_model` / `akm_reasoning_effort` / `akm_context_tier` を
設定画面と Step 1 右ペインの双方で選択でき、`auto_qa` とマージ設定の連動で活性化する。

実装前は `_C3AutoPrompt` に該当ウィジェットが無いため全件 RED となる。
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


def _visible_c3_titles(page: OptionsPage) -> List[str]:
    titles: List[str] = []
    for lf in page.c3.findChildren(_LabeledField):
        if not lf.isVisible():
            continue
        lbl = lf.findChild(QLabel)
        if lbl is None:
            continue
        titles.append(lbl.text().split("  *")[0].strip())
    return titles


class TestAkmModelWidgetsExist(unittest.TestCase):
    """3 項目のウィジェットが存在し、既定が「継承」であること。"""

    def test_widgets_exist(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            self.assertTrue(hasattr(page.c3, "akm_model"))
            self.assertTrue(hasattr(page.c3, "akm_effort"))
            self.assertTrue(hasattr(page.c3, "akm_context_tier"))
        finally:
            page.deleteLater()

    def test_model_default_is_inherit(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            self.assertEqual(page.c3.akm_model.currentIndex(), 0)
            self.assertIsNone(page.c3.akm_model.currentData())
        finally:
            page.deleteLater()

    def test_context_tier_default_is_inherit(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            self.assertEqual(page.c3.akm_context_tier.currentIndex(), 0)
            self.assertIsNone(page.c3.akm_context_tier.currentData())
        finally:
            page.deleteLater()

    def test_context_tier_offers_both_tiers(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            values = [
                page.c3.akm_context_tier.itemData(i)
                for i in range(page.c3.akm_context_tier.count())
            ]
            self.assertEqual(values, [None, "default", "long_context"])
        finally:
            page.deleteLater()

    def test_effort_disabled_while_model_inherits(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            self.assertIsNone(page.c3.akm_model.currentData())
            self.assertFalse(page.c3.akm_effort.isEnabled())
            self.assertIsNone(page.c3.akm_effort.currentData())
        finally:
            page.deleteLater()


class TestAkmModelVisibleInRightPane(unittest.TestCase):
    """3 項目が全ワークフローで Step 1 右ペインの共通枠へ表示されること。"""

    def test_model_visible_for_every_workflow(self) -> None:
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                page.set_workflows([wf], {wf: wf})
                self.assertIn(
                    _AKM_MODEL_FIELD_TITLE, _visible_c3_titles(page),
                    f"{wf} で AKM 用モデルが右ペインに表示されていません",
                )
        finally:
            page.deleteLater()

    def test_context_tier_visible_for_every_workflow(self) -> None:
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                page.set_workflows([wf], {wf: wf})
                self.assertIn(
                    _AKM_CONTEXT_TIER_FIELD_TITLE, _visible_c3_titles(page),
                    f"{wf} で AKM 用コンテキスト階層が右ペインに表示されていません",
                )
        finally:
            page.deleteLater()

    def test_effort_visible_for_every_workflow(self) -> None:
        """effort は「AKM 用モデル」行の内部ウィジェットのため可視性を直接検証する。"""
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                page.set_workflows([wf], {wf: wf})
                self.assertTrue(
                    page.c3.akm_effort.isVisible(),
                    f"{wf} で AKM 用 effort が右ペインに表示されていません",
                )
        finally:
            page.deleteLater()


class TestAkmModelAutoQaGating(unittest.TestCase):
    """`auto_qa` が「有効にする」かつマージ有効のときだけ活性化すること。"""

    def test_disabled_when_auto_qa_unselected(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.c3.auto_qa.set_tristate(None)
            self.assertFalse(page.c3.akm_model.isEnabled())
            self.assertFalse(page.c3.akm_context_tier.isEnabled())
        finally:
            page.deleteLater()

    def test_disabled_when_auto_qa_off(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.c3.auto_qa.set_tristate(False)
            self.assertFalse(page.c3.akm_model.isEnabled())
            self.assertFalse(page.c3.akm_context_tier.isEnabled())
        finally:
            page.deleteLater()

    def test_enabled_when_auto_qa_on(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.c3.auto_qa.set_tristate(True)
            # FR-QA-05: マージを有効にしない限り AKM 子実行自体が起きない。
            page.c3.qa_akm_background_merge.setChecked(True)
            self.assertTrue(page.c3.akm_model.isEnabled())
            self.assertTrue(page.c3.akm_context_tier.isEnabled())
        finally:
            page.deleteLater()


class TestAkmModelArgsPropagation(unittest.TestCase):
    """選択値が `OrchestrateArgs` と CLI argv へ伝播すること。"""

    def _select_model(self, page: OptionsPage, model_id: str) -> None:
        index = page.c3.akm_model.findData(model_id)
        self.assertGreaterEqual(index, 0, f"モデル {model_id} が選択肢にありません")
        page.c3.akm_model.setCurrentIndex(index)

    def test_values_reach_args(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)
            self._select_model(page, "claude-opus-4.6")
            page.c3.akm_context_tier.setCurrentIndex(
                page.c3.akm_context_tier.findData("default"))

            args = page.build_args_for_workflow("aas")
            self.assertEqual(args.akm_model, "claude-opus-4.6")
            self.assertEqual(args.akm_context_tier, "default")
        finally:
            page.deleteLater()

    def test_inherit_leaves_args_none(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            page.c3.qa_akm_background_merge.setChecked(True)

            args = page.build_args_for_workflow("aas")
            self.assertIsNone(args.akm_model)
            self.assertIsNone(args.akm_reasoning_effort)
            self.assertIsNone(args.akm_context_tier)
        finally:
            page.deleteLater()

    def test_auto_qa_off_suppresses_values(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["aas"], {"aas": "AAS"})
            page.c3.auto_qa.set_tristate(True)
            self._select_model(page, "claude-opus-4.6")
            page.c3.akm_context_tier.setCurrentIndex(
                page.c3.akm_context_tier.findData("default"))

            page.c3.auto_qa.set_tristate(False)
            args = page.build_args_for_workflow("aas")
            self.assertIsNone(args.akm_model)
            self.assertIsNone(args.akm_reasoning_effort)
            self.assertIsNone(args.akm_context_tier)
        finally:
            page.deleteLater()

    def test_argv_round_trip(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(
            workflow="aas",
            akm_model="claude-opus-4.6",
            akm_reasoning_effort="medium",
            akm_context_tier="default",
        ).to_argv()
        self.assertIn("--akm-model", argv)
        self.assertEqual(argv[argv.index("--akm-model") + 1], "claude-opus-4.6")
        self.assertIn("--akm-reasoning-effort", argv)
        self.assertEqual(argv[argv.index("--akm-reasoning-effort") + 1], "medium")
        self.assertIn("--akm-context-tier", argv)
        self.assertEqual(argv[argv.index("--akm-context-tier") + 1], "default")

    def test_argv_omits_unset_values(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(workflow="aas").to_argv()
        self.assertNotIn("--akm-model", argv)
        self.assertNotIn("--akm-reasoning-effort", argv)
        self.assertNotIn("--akm-context-tier", argv)


class TestAkmModelSettingsDefaults(unittest.TestCase):
    """設定ストアの既定値と復元マッピング。"""

    def test_store_defaults_are_inherit(self) -> None:
        from hve.gui import settings_store

        options = settings_store.defaults()["options"]
        self.assertEqual(options["akm_model"], "")
        self.assertEqual(options["akm_reasoning_effort"], "")
        self.assertEqual(options["akm_context_tier"], "")

    def test_settings_apply_maps_all_three(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        km = _SECTION_FIELDS["KM"]
        self.assertEqual(km["akm_model"], "akm_model")
        self.assertEqual(km["akm_reasoning_effort"], "akm_effort")
        self.assertEqual(km["akm_context_tier"], "akm_context_tier")


if __name__ == "__main__":
    unittest.main()
