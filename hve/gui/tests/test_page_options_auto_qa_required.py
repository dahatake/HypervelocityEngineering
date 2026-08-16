"""test_page_options_auto_qa_required.py — QA 自動投入を右ペインの必須選択にする契約。

FR-GUI-16: QA 自動投入（`auto_qa`）は QA 回答から AKM 差分同期を起動するかどうかを
決める設定であり、実行前に必ず明示選択させる。Step 1 右ペインの共通枠へ常時表示し、
未選択のままでは `validate()` が実行を許可しない。
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
    _AUTO_QA_FIELD_TITLE,
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


def _auto_qa_label_text(page: OptionsPage) -> str:
    for lf in page.c3.findChildren(_LabeledField):
        lbl = lf.findChild(QLabel)
        if lbl is None:
            continue
        if lbl.text().split("  *")[0].strip() == _AUTO_QA_FIELD_TITLE:
            return lbl.text()
    return ""


class TestAutoQaVisibleInRightPane(unittest.TestCase):
    """QA 自動投入がワークフロー選択時に右ペインへ表示されること。"""

    def test_visible_for_every_workflow(self) -> None:
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                page.set_workflows([wf], {wf: wf})
                self.assertIn(
                    _AUTO_QA_FIELD_TITLE, _visible_c3_titles(page),
                    f"{wf} で QA 自動投入が右ペインに表示されていません",
                )
        finally:
            page.deleteLater()

    def test_qa_answer_mode_visible_for_every_workflow(self) -> None:
        _get_app()
        page = OptionsPage()
        page.show()
        try:
            for wf in _ALL_WORKFLOWS:
                page.set_workflows([wf], {wf: wf})
                self.assertIn(
                    _QA_ANSWER_MODE_FIELD_TITLE, _visible_c3_titles(page),
                    f"{wf} で QA 回答モードが右ペインに表示されていません",
                )
        finally:
            page.deleteLater()

    def test_marked_as_required(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})
            self.assertIn("*必須", _auto_qa_label_text(page))
        finally:
            page.deleteLater()


class TestAutoQaRequiredValidation(unittest.TestCase):
    """未選択のままでは実行を許可しないこと。"""

    def test_unselected_blocks_validate(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})
            page.c3.auto_qa.set_tristate(None)
            ok, msg = page.validate()
            self.assertFalse(ok)
            self.assertIn(_AUTO_QA_FIELD_TITLE, msg)
        finally:
            page.deleteLater()

    def test_enabled_selection_allows_validate(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})
            page.c3.auto_qa.set_tristate(True)
            ok, _msg = page.validate()
            self.assertTrue(ok)
        finally:
            page.deleteLater()

    def test_disabled_selection_allows_validate(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})
            page.c3.auto_qa.set_tristate(False)
            ok, _msg = page.validate()
            self.assertTrue(ok)
        finally:
            page.deleteLater()


class TestAutoQaSelectionPropagation(unittest.TestCase):
    """選択値が `OrchestrateArgs` と QA 回答モードの活性へ伝播すること。"""

    def test_build_args_reflects_selection(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})

            page.c3.auto_qa.set_tristate(True)
            self.assertTrue(page.build_args_for_workflow("akm").auto_qa)

            page.c3.auto_qa.set_tristate(False)
            self.assertFalse(page.build_args_for_workflow("akm").auto_qa)

            page.c3.auto_qa.set_tristate(None)
            self.assertFalse(page.build_args_for_workflow("akm").auto_qa)
        finally:
            page.deleteLater()

    def test_qa_answer_mode_enabled_only_when_enabled(self) -> None:
        _get_app()
        page = OptionsPage()
        try:
            page.set_workflows(["akm"], {"akm": "AKM"})

            page.c3.auto_qa.set_tristate(None)
            self.assertFalse(page.c3.qa_answer_mode.isEnabled())

            page.c3.auto_qa.set_tristate(True)
            self.assertTrue(page.c3.qa_answer_mode.isEnabled())

            page.c3.auto_qa.set_tristate(False)
            self.assertFalse(page.c3.qa_answer_mode.isEnabled())
        finally:
            page.deleteLater()


class TestAutoQaSettingsDefault(unittest.TestCase):
    """既定値は未選択であり、明示選択を強制すること。"""

    def test_default_is_unselected(self) -> None:
        from hve.gui import settings_store

        self.assertEqual(settings_store.defaults()["options"]["auto_qa"], "")


if __name__ == "__main__":
    unittest.main()
