"""test_page_options_context_tier.py — `_C1Basic` の context_tier コンボ検証。

設定画面（C1 基本設定）/ Step 1 右ペインで共有される `_C1Basic` に追加した
context_tier 選択ボックスの既定値・項目・`to_args` 反映を検証する。
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
from hve.gui.page_options import _C1Basic  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class TestC1BasicContextTier(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        # モデルキャッシュ非依存で _C1Basic を構築する
        self._patch_choices = patch.object(
            page_options, "_load_model_choices", return_value=["Auto"]
        )
        self._patch_entries = patch.object(
            page_options, "_load_model_entries_map", return_value={}
        )
        self._patch_choices.start()
        self._patch_entries.start()
        self.w = _C1Basic()

    def tearDown(self) -> None:
        self._patch_choices.stop()
        self._patch_entries.stop()

    def test_has_two_items(self) -> None:
        values = [self.w.context_tier.itemData(i) for i in range(self.w.context_tier.count())]
        self.assertEqual(values, ["default", "long_context"])

    def test_default_selection_is_long_context(self) -> None:
        self.assertEqual(self.w.context_tier.currentData(), "long_context")

    def test_to_args_reflects_default(self) -> None:
        args = OrchestrateArgs(workflow="aas")
        self.w.to_args(args)
        self.assertEqual(args.context_tier, "long_context")

    def test_to_args_reflects_explicit_default_value(self) -> None:
        idx = self.w.context_tier.findData("default")
        self.w.context_tier.setCurrentIndex(idx)
        args = OrchestrateArgs(workflow="aas")
        self.w.to_args(args)
        self.assertEqual(args.context_tier, "default")


if __name__ == "__main__":
    unittest.main()
