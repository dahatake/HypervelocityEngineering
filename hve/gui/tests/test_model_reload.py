"""test_model_reload.py — `_C1Basic.reload_models()` の単体テスト (offscreen)。

`_load_model_choices` を monkeypatch で差し替え、コンボボックスの再投入挙動を検証する。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication

from hve.gui import page_options
from hve.gui.page_options import _C1Basic


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


INITIAL = ["Auto", "m1", "m2"]
EXPANDED = ["Auto", "m1", "m2", "m3"]
REMOVED = ["Auto", "m1", "m3"]
EMPTY_LIKE = ["Auto"]


class TestC1BasicReloadModels(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        # __init__ 時の choices を固定
        self._patcher = patch.object(
            page_options, "_load_model_choices", return_value=list(INITIAL)
        )
        self._patcher.start()
        self.widget = _C1Basic()

    def tearDown(self) -> None:
        self._patcher.stop()
        self.widget.deleteLater()

    # ----- 件数 -----
    def test_initial_counts(self) -> None:
        # main: Auto + m1, m2 = 3
        self.assertEqual(self.widget.model.count(), 3)
        # secondary: 継承 + m1, m2 = 3 (Auto は除外)
        self.assertEqual(self.widget.review_model.count(), 3)
        self.assertEqual(self.widget.qa_model.count(), 3)

    def test_count_updates_on_expansion(self) -> None:
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EXPANDED)
        ):
            self.widget.reload_models()
        self.assertEqual(self.widget.model.count(), 4)
        self.assertEqual(self.widget.review_model.count(), 4)
        self.assertEqual(self.widget.qa_model.count(), 4)

    # ----- 選択値の保持 -----
    def test_preserves_selection_when_still_present(self) -> None:
        # m1 を選択
        self.widget.model.setCurrentIndex(1)
        self.assertEqual(self.widget.model.currentData(), "m1")
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EXPANDED)
        ):
            self.widget.reload_models()
        self.assertEqual(self.widget.model.currentData(), "m1")

    def test_preserves_inherit_in_secondary(self) -> None:
        # review_model は既定 index=0=継承 (userData=None) のまま
        self.assertIsNone(self.widget.review_model.currentData())
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EXPANDED)
        ):
            self.widget.reload_models()
        self.assertIsNone(self.widget.review_model.currentData())

    # ----- 不在時のフォールバック -----
    def test_falls_back_when_selection_removed(self) -> None:
        # m2 を選択 → 新リストから m2 を削除
        self.widget.model.setCurrentIndex(2)
        self.assertEqual(self.widget.model.currentData(), "m2")
        with patch.object(
            page_options, "_load_model_choices", return_value=list(REMOVED)
        ):
            self.widget.reload_models()
        # main は Auto に戻る
        self.assertEqual(self.widget.model.currentIndex(), 0)
        self.assertEqual(self.widget.model.currentData(), "Auto")

    def test_secondary_falls_back_to_inherit_when_removed(self) -> None:
        # qa_model で m2 を選択 (index 2: 継承=0, m1=1, m2=2)
        self.widget.qa_model.setCurrentIndex(2)
        self.assertEqual(self.widget.qa_model.currentData(), "m2")
        with patch.object(
            page_options, "_load_model_choices", return_value=list(REMOVED)
        ):
            self.widget.reload_models()
        # 継承 (userData=None) にフォールバック
        self.assertEqual(self.widget.qa_model.currentIndex(), 0)
        self.assertIsNone(self.widget.qa_model.currentData())

    # ----- シグナル抑止 -----
    def test_no_signal_emitted_during_reload_when_value_preserved(self) -> None:
        self.widget.model.setCurrentIndex(1)  # m1
        spy: list[int] = []
        self.widget.model.currentIndexChanged.connect(lambda i: spy.append(i))
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EXPANDED)
        ):
            self.widget.reload_models()
        # blockSignals 内で再投入され、復元値も同一 → emit されない
        self.assertEqual(spy, [])

    def test_no_signal_emitted_during_reload_on_fallback(self) -> None:
        # 削除されるケースでも blockSignals により emit ゼロ件であること
        self.widget.model.setCurrentIndex(2)  # m2
        spy: list[int] = []
        self.widget.model.currentIndexChanged.connect(lambda i: spy.append(i))
        with patch.object(
            page_options, "_load_model_choices", return_value=list(REMOVED)
        ):
            self.widget.reload_models()
        self.assertEqual(spy, [])

    # ----- 空相当時の維持 -----
    def test_empty_like_keeps_existing(self) -> None:
        before_main = self.widget.model.count()
        before_review = self.widget.review_model.count()
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EMPTY_LIKE)
        ):
            self.widget.reload_models()
        self.assertEqual(self.widget.model.count(), before_main)
        self.assertEqual(self.widget.review_model.count(), before_review)

    # ----- 継承項目の重複検知 -----
    def test_secondary_inherit_item_not_duplicated(self) -> None:
        with patch.object(
            page_options, "_load_model_choices", return_value=list(EXPANDED)
        ):
            self.widget.reload_models()
        for combo in (self.widget.review_model, self.widget.qa_model):
            inherit_count = sum(
                1 for i in range(combo.count()) if combo.itemData(i) is None
            )
            self.assertEqual(inherit_count, 1)

    # ----- 例外伝播なし -----
    def test_exception_in_loader_is_swallowed(self) -> None:
        with patch.object(
            page_options, "_load_model_choices", side_effect=RuntimeError("boom")
        ):
            try:
                self.widget.reload_models()
            except Exception:  # pragma: no cover
                self.fail("reload_models must swallow loader exceptions")
        # 既存リストが維持されること
        self.assertEqual(self.widget.model.count(), 3)


if __name__ == "__main__":
    unittest.main()
