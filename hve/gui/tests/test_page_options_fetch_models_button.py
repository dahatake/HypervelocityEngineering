"""test_page_options_fetch_models_button.py — `_C1Basic` の「利用できるモデルの取得」ボタン検証。

設定画面（C1 基本設定）の最上部に追加した「利用できるモデルの取得」ボタンについて、
存在・配置（レイアウト最上部）・クリック時に `fetch_models_requested` シグナルが
emit されることを検証する（実際のフェッチ処理は MainWindow 側に一本化されており、
本クラスはボタン押下の通知のみを担うため、ここではシグナル emit のみを確認する）。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from hve.gui import page_options  # noqa: E402
from hve.gui.page_options import _C1Basic, _LabeledField  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class TestC1BasicFetchModelsButton(unittest.TestCase):
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

    def test_button_exists_with_expected_text(self) -> None:
        self.assertIsInstance(self.w.fetch_models_button, QPushButton)
        self.assertEqual(self.w.fetch_models_button.text(), "利用できるモデルの取得")

    def test_button_is_topmost_item_in_layout(self) -> None:
        layout = self.w.layout()
        first_item = layout.itemAt(0)
        self.assertIs(first_item.widget(), self.w.fetch_models_button)
        # 2番目の項目は「使用するモデル」の _LabeledField であること（ボタンの後退では無い）。
        second_item = layout.itemAt(1)
        self.assertIsInstance(second_item.widget(), _LabeledField)

    def test_click_emits_fetch_models_requested(self) -> None:
        received: list = []
        self.w.fetch_models_requested.connect(lambda: received.append(True))
        self.w.fetch_models_button.click()
        self.assertEqual(received, [True])

    def test_tooltip_matches_status_bar_button(self) -> None:
        self.assertEqual(
            self.w.fetch_models_button.toolTip(),
            "利用できるモデル一覧を取得しキャッシュへ保存します。",
        )


if __name__ == "__main__":
    unittest.main()
