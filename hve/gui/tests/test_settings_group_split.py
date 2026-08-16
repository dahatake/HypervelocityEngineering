"""test_settings_group_split.py — FR-GUI-20 の RED テスト。

設定画面「一般」カテゴリの旧「自動プロンプト」ノードを廃止し、
`QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` へ
再編したうえで、`追加プロンプト` / `コンテキスト最大文字数` を `基本設定` へ移すことを検証する。

実装前は `_CATEGORY_TREE` と `_SECTION_FIELDS` が旧構成のため全件 RED となる。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _general_items():
    from hve.gui.settings_window import _CATEGORY_TREE

    return [items for label, items in _CATEGORY_TREE if label == "一般"][0]


class TestGeneralCategoryTree(unittest.TestCase):
    """「一般」カテゴリのノード構成。"""

    def test_auto_prompt_node_is_removed(self) -> None:
        labels = [name for name, _key in _general_items()]
        keys = [key for _name, key in _general_items()]
        self.assertNotIn("自動プロンプト", labels)
        self.assertNotIn("C3", keys)

    def test_new_nodes_exist(self) -> None:
        items = dict((key, name) for name, key in _general_items())
        self.assertEqual(items.get("QA"), "QA (質問票)")
        self.assertEqual(items.get("REVIEW"), "レビュー")
        self.assertEqual(items.get("KM"), "Knowledge Management")
        self.assertEqual(items.get("SELFIMPROVE"), "自己改善 (Self Improve)")

    def test_basic_settings_stays_first(self) -> None:
        self.assertEqual(_general_items()[0], ("基本設定", "C1"))

    def test_new_nodes_follow_basic_settings_in_order(self) -> None:
        keys = [key for _name, key in _general_items()]
        self.assertEqual(keys[:5], ["C1", "QA", "REVIEW", "KM", "SELFIMPROVE"])

    def test_section_factory_returns_dedicated_widgets(self) -> None:
        _get_app()
        from hve.gui.page_options import (
            _CKnowledgeManagement,
            _CQaPrompt,
            _CReviewPrompt,
            _CSelfImprove,
        )
        from hve.gui.settings_window import SettingsWindow

        window = SettingsWindow(repo_root=Path.cwd())
        try:
            expected = {
                "QA": _CQaPrompt,
                "REVIEW": _CReviewPrompt,
                "KM": _CKnowledgeManagement,
                "SELFIMPROVE": _CSelfImprove,
            }
            for key, cls in expected.items():
                with self.subTest(key=key):
                    self.assertIsInstance(window._sections.get(key), cls)
            self.assertNotIn("C3", window._sections)
        finally:
            window.close()
            window.deleteLater()


class TestSectionFieldsSplit(unittest.TestCase):
    """`_SECTION_FIELDS` の分割と `defaults()` 整合。"""

    def test_c3_key_is_removed(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        self.assertNotIn("C3", _SECTION_FIELDS)

    def test_qa_section_owns_the_two_qa_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        qa = _SECTION_FIELDS["QA"]
        self.assertEqual(qa["auto_qa"], "auto_qa")
        self.assertEqual(qa["qa_answer_mode"], "qa_answer_mode")

    def test_review_section_owns_the_three_review_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        review = _SECTION_FIELDS["REVIEW"]
        for key in (
            "auto_contents_review",
            "auto_coding_agent_review",
            "auto_coding_agent_review_auto_approval",
        ):
            with self.subTest(key=key):
                self.assertEqual(review[key], key)

    def test_km_section_owns_the_akm_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        km = _SECTION_FIELDS["KM"]
        self.assertEqual(km["qa_akm_background_merge"], "qa_akm_background_merge")
        self.assertEqual(km["akm_model"], "akm_model")
        self.assertEqual(km["akm_reasoning_effort"], "akm_effort")
        self.assertEqual(km["akm_context_tier"], "akm_context_tier")

    def test_self_improve_section_owns_the_four_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        si = _SECTION_FIELDS["SELFIMPROVE"]
        for key in (
            "self_improve",
            "self_improve_max_iterations",
            "self_improve_target_scope",
            "self_improve_goal",
        ):
            with self.subTest(key=key):
                self.assertEqual(si[key], key)

    def test_basic_section_owns_the_two_moved_keys(self) -> None:
        from hve.gui.settings_apply import _SECTION_FIELDS

        c1 = _SECTION_FIELDS["C1"]
        self.assertEqual(c1["additional_prompt"], "additional_prompt")
        self.assertEqual(c1["context_max_chars"], "context_max_chars")


class TestBasicSectionOwnsAdditionalPrompt(unittest.TestCase):
    """`_C1Basic` が移設された 2 ウィジェットを所有し、値を CLI へ渡す。"""

    def test_widgets_moved_to_basic_section(self) -> None:
        _get_app()
        from hve.gui.page_options import _C1Basic

        widget = _C1Basic()
        try:
            self.assertTrue(hasattr(widget, "additional_prompt"))
            self.assertTrue(hasattr(widget, "context_max_chars"))
        finally:
            widget.deleteLater()

    def test_to_args_moved_to_basic_section(self) -> None:
        _get_app()
        from hve.gui.orchestrate_args import OrchestrateArgs
        from hve.gui.page_options import _C1Basic

        widget = _C1Basic()
        try:
            widget.additional_prompt.setPlainText("追記テキスト")
            widget.context_max_chars.setValue(1234)
            args = OrchestrateArgs(workflow="aas")
            widget.to_args(args)
            self.assertEqual(args.additional_prompt, "追記テキスト")
            self.assertEqual(args.context_max_chars, 1234)
        finally:
            widget.deleteLater()


class TestSettingsWindowReloadModels(unittest.TestCase):
    """モデルコンボの再投入対象が新ノードへ追随していること。"""

    def test_reload_models_targets_basic_and_km(self) -> None:
        import inspect

        from hve.gui.settings_window import SettingsWindow

        source = inspect.getsource(SettingsWindow.reload_models)
        self.assertIn('"KM"', source)
        self.assertNotIn('"C3"', source)


if __name__ == "__main__":
    unittest.main()
