"""test_workflow_requirements_all_steps.py — FR-GUI-01 / FR-GUI-02 のテスト。

検証項目:
  1. Precheck が選択中ワークフローの **全 active step** を評価すること
  2. 必須入力キーが `StepDef.required_params`（FR-DAG-07）から導出されること
  3. GUI の監視対象ウィジェット表が `INPUT_FIELD_KEYS` を網羅すること
  4. バナー（代表 1 件表示）の従来挙動を壊さないこと

根拠: hve-dev/requirement-definition.md §6.4 FR-GUI-01 / FR-GUI-02
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui.workflow_step_requirements import (
    INPUT_FIELD_KEYS,
    registry_required_param_keys,
    summarize_all_requirements_for_selection,
    summarize_requirements_for_selection,
)
from hve.workflow_registry import get_workflow


def _get_app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


ASDW_STEP_1_3_PARAMS = tuple(get_workflow("asdw-web").get_step("1.3").required_params)


class TestRegistryRequiredParamKeys(unittest.TestCase):
    """FR-GUI-02: 必須キーはレジストリ宣言から導出する。"""

    def test_includes_asdw_step_1_3_params(self) -> None:
        keys = registry_required_param_keys()
        for key in ASDW_STEP_1_3_PARAMS:
            self.assertIn(key, keys)

    def test_input_field_keys_include_registry_keys(self) -> None:
        for key in registry_required_param_keys():
            self.assertIn(key, INPUT_FIELD_KEYS)

    def test_input_field_keys_keep_static_keys(self) -> None:
        for key in ("company_name", "target_business", "resource_group", "target_dirs"):
            self.assertIn(key, INPUT_FIELD_KEYS)

    def test_input_field_keys_are_unique(self) -> None:
        self.assertEqual(len(INPUT_FIELD_KEYS), len(set(INPUT_FIELD_KEYS)))


class TestSummarizeAllRequirements(unittest.TestCase):
    """FR-GUI-01: 全 active step を評価する。"""

    @staticmethod
    def _exists_all(_path: str) -> bool:
        return True

    def test_reports_step_1_3_param_gap(self) -> None:
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.1", "1.3"])],
            input_values={},
            file_exists=self._exists_all,
        )
        warn_labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertIn("resource_group", warn_labels)

    def test_declared_defaults_are_not_reported_as_missing(self) -> None:
        """既定値を持つキーは GUI 未入力でも不足としない（FR-DAG-07 が補完する）。"""
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.3"])],
            input_values={
                "resource_group": "rg-prod",
            },
            file_exists=self._exists_all,
        )
        warn_labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertNotIn("data_location", warn_labels)
        self.assertEqual(warn_labels, set())

    def test_step_without_declaration_is_unaffected(self) -> None:
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.1"])],
            input_values={"resource_group": "rg-prod"},
            file_exists=self._exists_all,
        )
        warn_labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertEqual(warn_labels, set())

    def test_covers_more_than_one_step(self) -> None:
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.1", "1.3"])],
            input_values={},
            file_exists=self._exists_all,
        )
        step_ids = {s.step_id for s in summaries}
        self.assertIn("1.1", step_ids)
        self.assertIn("1.3", step_ids)

    def test_fanout_child_step_id_is_normalized(self) -> None:
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.3/APP-009"])],
            input_values={"resource_group": "rg-prod"},
            file_exists=self._exists_all,
        )
        self.assertIn("1.3", {s.step_id for s in summaries})

    def test_empty_selection_returns_empty(self) -> None:
        self.assertEqual(
            summarize_all_requirements_for_selection([], file_exists=self._exists_all),
            [],
        )

    def test_banner_entry_point_still_returns_at_most_one(self) -> None:
        """バナーの代表 1 件表示は従来どおり維持する。"""
        summaries = summarize_requirements_for_selection(
            [("asdw-web", ["1.1", "1.3"])],
            input_values={},
            file_exists=self._exists_all,
        )
        self.assertLessEqual(len(summaries), 1)

    def test_duplicate_workflow_entries_do_not_duplicate_summaries(self) -> None:
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.3"]), ("asdw-web", ["1.3"])],
            input_values={"resource_group": "rg-prod"},
            file_exists=self._exists_all,
        )
        keys = [(s.workflow_id, s.step_id) for s in summaries]
        self.assertEqual(len(keys), len(set(keys)))

    def test_autopilot_mode_reports_params_without_reviving_file_requirements(self) -> None:
        """autopilot では個別 Step のファイル要件を復活させず、パラメータだけ検査する。"""
        summaries = summarize_all_requirements_for_selection(
            [("asdw-web", ["1.1", "1.3"])],
            input_values={},
            file_exists=lambda _p: False,
            autopilot_mode=True,
            autopilot_catalog_path="docs/catalog/app-arch-catalog.md",
        )
        labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertIn("resource_group", labels)
        self.assertNotIn("docs/catalog/app-catalog.md", labels)

    def test_downstream_workflow_file_requirements_are_not_checked(self) -> None:
        """ARD+AAS 同時選択時、AAS のファイル要件は上流が生成するため検査しない。"""
        summaries = summarize_all_requirements_for_selection(
            [("ard", ["3", "4"]), ("aas", ["1"])],
            input_values={},
            file_exists=lambda p: p == "docs/business-requirement.md",
        )
        labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertNotIn("docs/catalog/use-case-catalog.md", labels)

    def test_downstream_workflow_param_requirements_are_still_checked(self) -> None:
        """下流ワークフローでもパラメータ要件は検査する（上流が生成しないため）。"""
        summaries = summarize_all_requirements_for_selection(
            [("ard", ["3"]), ("asdw-web", ["1.3"])],
            input_values={},
            file_exists=lambda _p: True,
        )
        labels = {
            item.label
            for s in summaries
            for item in s.items
            if item.status == "warn"
        }
        self.assertIn("resource_group", labels)


class TestBannerInputWidgetCoverage(unittest.TestCase):
    """FR-GUI-02: 監視対象ウィジェット表が INPUT_FIELD_KEYS を網羅する。"""

    def test_widget_map_covers_all_input_field_keys(self) -> None:
        from hve.gui.page_options import OptionsPage

        _get_app()
        page = OptionsPage()
        try:
            widgets = page._banner_input_widgets()
            for key in INPUT_FIELD_KEYS:
                self.assertIn(key, widgets, f"{key} が監視対象ウィジェット表に無い")
        finally:
            page.deleteLater()

    def test_collect_banner_input_values_returns_registry_keys(self) -> None:
        from hve.gui.page_options import OptionsPage

        _get_app()
        page = OptionsPage()
        try:
            page.c_azure.data_resource_suffix.setText("app009")
            values = page._collect_banner_input_values()
            self.assertEqual(values.get("data_resource_suffix"), "app009")
            self.assertNotIn("data_verify_aci_image", values)
        finally:
            page.deleteLater()


class TestPrecheckRunnerUsesAllSteps(unittest.TestCase):
    """FR-GUI-01: run_step1_precheck が全 active step を評価する。"""
    def test_precheck_reports_step_1_3_param_gap(self) -> None:
        from hve.autopilot.precheck_runner import run_step1_precheck

        result = run_step1_precheck(
            ["asdw-web"],
            Path("."),
            steps_by_workflow={"asdw-web": ["1.1", "1.3"]},
            input_values={},
        )
        fields = {item.field_name for item in result.items}
        self.assertIn("resource_group", fields)

    def test_precheck_passes_when_all_provided(self) -> None:
        from hve.autopilot.precheck_runner import run_step1_precheck

        result = run_step1_precheck(
            ["asdw-web"],
            Path("."),
            steps_by_workflow={"asdw-web": ["1.3"]},
            input_values={
                "resource_group": "rg-prod",
            },
        )
        fields = {item.field_name for item in result.items}
        self.assertNotIn("data_verify_aci_image", fields)
        self.assertNotIn("resource_group", fields)


if __name__ == "__main__":
    unittest.main()
