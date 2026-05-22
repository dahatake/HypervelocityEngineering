"""test_page_options_effort.py — `_C1Basic` の Effort / Context Size UI 連動テスト。

`_load_model_choices` / `_load_model_entries_map` を monkeypatch で差し替え、
モデル選択時の Effort コンボ・Context Size ラベルの挙動を検証する。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import page_options  # noqa: E402
from hve.gui.orchestrate_args import OrchestrateArgs  # noqa: E402
from hve.gui.page_options import _C1Basic, _format_context_size_label  # noqa: E402
from hve.models_api import ModelEntry  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


CHOICES = ["Auto", "model-with-effort", "model-no-effort", "model-unknown"]


def _make_entries_map() -> dict:
    return {
        "model-with-effort": ModelEntry(
            id="model-with-effort",
            name="Model With Effort",
            default_reasoning_effort="medium",
            supported_reasoning_efforts=["low", "medium", "high"],
            supports_reasoning_effort=True,
            max_context_window_tokens=200000,
        ),
        "model-no-effort": ModelEntry(
            id="model-no-effort",
            name="Model No Effort",
            supports_reasoning_effort=False,
            max_context_window_tokens=128000,
        ),
        # "model-unknown" は entries_map に無い（フォールバック候補）
    }


class TestC1BasicEffortRow(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self._patch_choices = patch.object(
            page_options, "_load_model_choices", return_value=list(CHOICES)
        )
        self._patch_entries = patch.object(
            page_options, "_load_model_entries_map", return_value=_make_entries_map()
        )
        self._patch_choices.start()
        self._patch_entries.start()
        self.widget = _C1Basic()

    def tearDown(self) -> None:
        self._patch_choices.stop()
        self._patch_entries.stop()
        self.widget.deleteLater()

    # ---- 初期状態（Auto 選択）----
    def test_initial_auto_disables_effort(self) -> None:
        self.assertEqual(self.widget.model.currentData(), "Auto")
        self.assertFalse(self.widget.effort.isEnabled())
        self.assertEqual(self.widget.context_size_label.text(), "")

    def test_secondary_inherit_disables_effort(self) -> None:
        # review/qa は初期 currentData=None（継承）
        self.assertIsNone(self.widget.review_model.currentData())
        self.assertFalse(self.widget.review_effort.isEnabled())
        # 「（モデル設定を継承）」固定表示が入っている
        self.assertEqual(self.widget.review_effort.count(), 1)
        self.assertIsNone(self.widget.review_effort.currentData())
        self.assertEqual(self.widget.review_context_size_label.text(), "")

    # ---- モデル変更 → Effort コンボに選択肢投入 ----
    def test_select_model_with_effort_populates_combo(self) -> None:
        # モデル選択を model-with-effort に切り替え
        idx = self.widget.model.findData("model-with-effort")
        self.assertGreaterEqual(idx, 0)
        self.widget.model.setCurrentIndex(idx)

        # 3 つの選択肢が入る
        self.assertTrue(self.widget.effort.isEnabled())
        self.assertEqual(self.widget.effort.count(), 3)
        # default_reasoning_effort="medium" が初期選択
        self.assertEqual(self.widget.effort.currentData(), "medium")
        # Context Size 上限が表示される（200K tokens (200,000)）
        text = self.widget.context_size_label.text()
        self.assertIn("200K", text)
        self.assertIn("200,000", text)

    # ---- 非対応モデルでは Effort 無効 ----
    def test_select_model_no_effort_disables_combo(self) -> None:
        idx = self.widget.model.findData("model-no-effort")
        self.widget.model.setCurrentIndex(idx)
        self.assertFalse(self.widget.effort.isEnabled())
        self.assertEqual(self.widget.effort.count(), 0)
        # Context Size は表示される（supports=False でも max_context_window_tokens があれば表示）
        self.assertIn("128K", self.widget.context_size_label.text())

    # ---- entries_map に無いモデル（FALLBACK 等）----
    def test_select_unknown_model_no_effort_no_context(self) -> None:
        idx = self.widget.model.findData("model-unknown")
        self.widget.model.setCurrentIndex(idx)
        self.assertFalse(self.widget.effort.isEnabled())
        self.assertEqual(self.widget.context_size_label.text(), "")

    # ---- to_args ----
    def test_to_args_reflects_effort(self) -> None:
        idx = self.widget.model.findData("model-with-effort")
        self.widget.model.setCurrentIndex(idx)
        # high に変更
        eff_idx = self.widget.effort.findData("high")
        self.widget.effort.setCurrentIndex(eff_idx)

        args = OrchestrateArgs(workflow="ard")
        self.widget.to_args(args)
        self.assertEqual(args.model, "model-with-effort")
        self.assertEqual(args.reasoning_effort, "high")
        # review/qa は継承 → None
        self.assertIsNone(args.review_reasoning_effort)
        self.assertIsNone(args.qa_reasoning_effort)

    def test_to_args_auto_returns_none_effort(self) -> None:
        args = OrchestrateArgs(workflow="ard")
        self.widget.to_args(args)
        # Auto モデル → effort=None
        self.assertIsNone(args.reasoning_effort)


class TestFormatContextSizeLabel(unittest.TestCase):
    def test_large(self) -> None:
        self.assertEqual(
            _format_context_size_label(200000),
            "Context Size: 200K tokens (200,000)",
        )

    def test_small(self) -> None:
        self.assertEqual(
            _format_context_size_label(500),
            "Context Size: 500 tokens",
        )

    def test_none(self) -> None:
        self.assertEqual(_format_context_size_label(None), "")

    def test_zero(self) -> None:
        self.assertEqual(_format_context_size_label(0), "")


if __name__ == "__main__":
    unittest.main()
