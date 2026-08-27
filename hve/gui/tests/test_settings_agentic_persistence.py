"""test_settings_agentic_persistence.py — FR-LOCAL-SURFACE-01 (a) の永続化テスト。

検証項目:
  1. Agentic Retrieval の 6 項目と `enable_tool_search` が設定ストア既定値にあること
  2. `settings_apply` の AGENTIC / C1 セクションが同キーを網羅すること
  3. QComboBox の userData がすべて往復可能な文字列であること
     （list / bool を userData へ置くと `settings_apply._set()` が復元できない）
  4. widget → 保存 → 別 widget へ復元、で選択が失われないこと
  5. 復元後の `to_args()` が CLI が期待する型（list / bool / None）へ戻すこと

根拠: hve-dev/requirement-definition.md §5.21 FR-LOCAL-SURFACE-01
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from hve.gui import settings_apply, settings_store
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.gui.page_options import _CAgenticRetrieval, _C1Basic


AGENTIC_KEYS = (
    "enable_agentic_retrieval",
    "agentic_data_source_modes",
    "foundry_mcp_integration",
    "agentic_data_sources_hint",
    "agentic_existing_design_diff_only",
    "foundry_sku_fallback_policy",
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class TestAgenticSettingsKeys(unittest.TestCase):
    """shared setting が既定値表とセクション表の両方へ登録されている。"""

    def test_defaults_contain_every_agentic_key(self) -> None:
        options = settings_store.defaults()["options"]
        for key in AGENTIC_KEYS:
            self.assertIn(key, options, f"{key} が設定ストア既定値に無い")

    def test_agentic_section_maps_every_agentic_key(self) -> None:
        section = settings_apply._SECTION_FIELDS["AGENTIC"]
        self.assertEqual(set(section), set(AGENTIC_KEYS))
        for key in AGENTIC_KEYS:
            self.assertEqual(section[key], key)

    def test_enable_tool_search_is_persisted_in_c1(self) -> None:
        options = settings_store.defaults()["options"]
        self.assertIn("enable_tool_search", options)
        self.assertEqual(options["enable_tool_search"], "auto")
        self.assertEqual(
            settings_apply._SECTION_FIELDS["C1"]["enable_tool_search"],
            "enable_tool_search",
        )

    def test_defaults_match_widget_initial_selection(self) -> None:
        """既定値は widget の初期選択と一致し、起動時に無言で選択が動かない。"""
        _app()
        widget = _CAgenticRetrieval()
        options = settings_store.defaults()["options"]
        for key in AGENTIC_KEYS:
            child = getattr(widget, key)
            self.assertEqual(
                settings_apply._get(child),
                options[key],
                f"{key} の既定値が widget 初期選択と食い違う",
            )


class TestAgenticUserDataIsRoundTrippable(unittest.TestCase):
    """userData は保存・復元できる文字列でなければならない。"""

    def test_every_combo_user_data_is_a_string(self) -> None:
        _app()
        widget = _CAgenticRetrieval()
        for key in AGENTIC_KEYS:
            child = getattr(widget, key)
            count = getattr(child, "count", None)
            if not callable(count):
                continue  # QLineEdit（agentic_data_sources_hint）
            for i in range(child.count()):
                data = child.itemData(i)
                self.assertIsInstance(
                    data,
                    str,
                    f"{key} の item {i} の userData が文字列でない: {data!r}",
                )


class TestAgenticRoundTrip(unittest.TestCase):
    """widget → 保存 → 別インスタンスへ復元で選択が保たれる。"""

    SELECTION = {
        "enable_agentic_retrieval": "yes",
        "agentic_data_source_modes": "indexer;push",
        "foundry_mcp_integration": "off",
        "agentic_data_sources_hint": "社内規程 PDF (Blob)",
        "agentic_existing_design_diff_only": "on",
        "foundry_sku_fallback_policy": "global_required",
    }

    def test_selection_survives_collect_and_apply(self) -> None:
        _app()
        source = _CAgenticRetrieval()
        for key, value in self.SELECTION.items():
            settings_apply._set(getattr(source, key), value)

        collected = settings_apply.collect_from_widgets({"AGENTIC": source})
        for key, value in self.SELECTION.items():
            self.assertEqual(collected[key], value)

        restored = _CAgenticRetrieval()
        settings_apply.apply_to_widgets({"AGENTIC": restored}, {"options": collected})
        for key, value in self.SELECTION.items():
            self.assertEqual(
                settings_apply._get(getattr(restored, key)),
                value,
                f"{key} が復元できていない",
            )

    def test_restored_widget_produces_cli_types(self) -> None:
        _app()
        restored = _CAgenticRetrieval()
        for key, value in self.SELECTION.items():
            settings_apply._set(getattr(restored, key), value)

        args = OrchestrateArgs(workflow="asdw-web")
        restored.to_args(args)

        self.assertEqual(args.enable_agentic_retrieval, "yes")
        self.assertEqual(args.agentic_data_source_modes, ["indexer", "push"])
        self.assertIs(args.foundry_mcp_integration, False)
        self.assertEqual(args.agentic_data_sources_hint, "社内規程 PDF (Blob)")
        self.assertIs(args.agentic_existing_design_diff_only, True)
        self.assertEqual(args.foundry_sku_fallback_policy, "global_required")

    def test_default_selection_passes_nothing_to_cli(self) -> None:
        """「既定に従う」のままなら CLI へ一切渡さない（既存挙動の維持）。"""
        _app()
        widget = _CAgenticRetrieval()
        args = OrchestrateArgs(workflow="asdw-web")
        widget.to_args(args)

        self.assertIsNone(args.enable_agentic_retrieval)
        self.assertIsNone(args.agentic_data_source_modes)
        self.assertIsNone(args.foundry_mcp_integration)
        self.assertIsNone(args.agentic_data_sources_hint)
        self.assertIsNone(args.agentic_existing_design_diff_only)
        self.assertIsNone(args.foundry_sku_fallback_policy)

    def test_enable_tool_search_round_trip(self) -> None:
        _app()
        source = _C1Basic()
        settings_apply._set(source.enable_tool_search, "no")
        collected = settings_apply.collect_from_widgets({"C1": source})
        self.assertEqual(collected["enable_tool_search"], "no")

        restored = _C1Basic()
        settings_apply.apply_to_widgets({"C1": restored}, {"options": collected})
        self.assertEqual(restored.enable_tool_search.currentData(), "no")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
