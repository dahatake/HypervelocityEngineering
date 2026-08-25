"""CLI 対話ウィザードのワークフロー選択肢のカテゴリー表示（FR-GUI-21）。

`_workflow_options_with_categories` がカテゴリー順に並べ替え、
各選択肢へカテゴリー名の接頭辞を付けることを検証する。
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# __main__.py は Python の __main__ と名前が衝突するため importlib で直接ロードする
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_wizard_menu", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

_workflow_options_with_categories = _main_mod._workflow_options_with_categories


def _display_names() -> dict:
    from hve.template_engine import _WORKFLOW_DISPLAY_NAMES

    return _WORKFLOW_DISPLAY_NAMES


class _FakeStep:
    def __init__(self, is_container: bool = False) -> None:
        self.is_container = is_container


class _FakeWorkflow:
    def __init__(self, wf_id: str, step_count: int = 1) -> None:
        self.id = wf_id
        self.name = wf_id.upper()
        self.steps = [_FakeStep() for _ in range(step_count)]


class TestWizardWorkflowMenuCategories(unittest.TestCase):
    """選択肢の並び順・接頭辞・索引整合。"""

    def test_options_follow_category_order(self) -> None:
        from hve.workflow_registry import WORKFLOW_CATEGORIES, list_workflows

        ordered, options = _workflow_options_with_categories(
            list_workflows(), _display_names()
        )
        expected = [wf_id for _name, ids in WORKFLOW_CATEGORIES for wf_id in ids]
        self.assertEqual([wf.id for wf in ordered], expected)
        self.assertEqual(len(options), len(ordered))

    def test_every_option_has_category_prefix(self) -> None:
        from hve.workflow_registry import WORKFLOW_CATEGORIES, list_workflows

        category_of = {
            wf_id: name for name, ids in WORKFLOW_CATEGORIES for wf_id in ids
        }
        ordered, options = _workflow_options_with_categories(
            list_workflows(), _display_names()
        )
        for wf, option in zip(ordered, options):
            self.assertTrue(
                option.startswith(f"{category_of[wf.id]} > "),
                f"{wf.id}: {option!r} がカテゴリー接頭辞で始まっていない",
            )

    def test_ai_agent_workflows_are_grouped_together(self) -> None:
        from hve.workflow_registry import list_workflows

        ordered, _options = _workflow_options_with_categories(
            list_workflows(), _display_names()
        )
        ids = [wf.id for wf in ordered]
        self.assertEqual(ids[-4:], ["ada", "aag", "aagd", "aar"])

    def test_selected_index_resolves_to_the_displayed_workflow(self) -> None:
        from hve.workflow_registry import list_workflows

        ordered, options = _workflow_options_with_categories(
            list_workflows(), _display_names()
        )
        for index, wf in enumerate(ordered):
            self.assertIn(f"({wf.id} —", options[index])

    def test_uncategorized_workflow_falls_back_to_other_bucket(self) -> None:
        workflows = [_FakeWorkflow("ard"), _FakeWorkflow("zzz-unknown")]
        ordered, options = _workflow_options_with_categories(workflows, {})
        self.assertEqual([wf.id for wf in ordered], ["ard", "zzz-unknown"])
        self.assertTrue(options[-1].startswith("その他 > "))

    def test_container_steps_are_excluded_from_the_step_count(self) -> None:
        workflow = _FakeWorkflow("ard", step_count=0)
        workflow.steps = [_FakeStep(is_container=True), _FakeStep(), _FakeStep()]
        _ordered, options = _workflow_options_with_categories([workflow], {})
        self.assertIn("2 実行ステップ", options[0])


if __name__ == "__main__":
    unittest.main()
