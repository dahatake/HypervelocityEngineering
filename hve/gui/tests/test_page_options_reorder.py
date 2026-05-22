"""test_page_options_reorder.py — Step 2 カテゴリ表示順並べ替えテスト。

`OptionsPage._reorder_visible_categories` が選択 Workflow の正準順
(ARD 先頭) でカテゴリ QGroupBox を並べ替えることを検証する。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402

from hve.gui.page_options import OptionsPage  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _visible_order(page: OptionsPage) -> List[str]:
    """`_groups_layout` 上の QGroupBox を出現順に並べ、_category_groups の
    キーに逆引きしたリストを返す (`_last_ordered_keys` 由来ではなく実レイアウト順)。
    """
    layout = page._groups_layout  # type: ignore[attr-defined]
    inverse = {id(g): k for k, g in page._category_groups.items()}
    keys: List[str] = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        w = item.widget() if item is not None else None
        if isinstance(w, QGroupBox):
            k = inverse.get(id(w))
            if k is not None:
                keys.append(k)
    return keys


class TestReorderVisibleCategories(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self.page = OptionsPage()

    def tearDown(self) -> None:
        self.page.deleteLater()

    def test_ard_only_puts_c14_first_among_visible(self) -> None:
        self.page.set_workflows(["ard"])
        order = _visible_order(self.page)
        # 表示中の Workflow 固有カテゴリ (C14) が先頭にあること
        visible = [k for k in order if self.page._category_groups[k].isVisibleTo(self.page)]
        # 表示中のカテゴリ集合に C14 が含まれ、かつ先頭が C14 であること
        self.assertIn("C14", visible)
        self.assertEqual(visible[0], "C14")

    def test_ard_plus_akm_orders_c14_before_c11(self) -> None:
        self.page.set_workflows(["akm", "ard"])  # 入力順は逆でも正準順で並ぶ
        order = _visible_order(self.page)
        # 物理レイアウト上で C14 が C11 より前
        self.assertLess(order.index("C14"), order.index("C11"))

    def test_akm_only_places_c4_after_c11(self) -> None:
        self.page.set_workflows(["akm"])
        order = _visible_order(self.page)
        # AKM は C4 オーナーなので C11 の直後に C4 が挿入される
        self.assertLess(order.index("C11"), order.index("C4"))

    def test_aqod_only_no_c4_owner_no_c4_in_visible(self) -> None:
        self.page.set_workflows(["aqod"])
        # AQOD は C4 を所有しないので C4 は非表示 (visible_categories に含まれない)
        self.assertFalse(
            self.page._category_groups["C4"].isVisibleTo(self.page)
        )

    def test_idempotent_no_reorder_on_repeat(self) -> None:
        self.page.set_workflows(["ard", "akm"])
        order1 = _visible_order(self.page)
        last1 = list(getattr(self.page, "_last_ordered_keys", []))
        # 同じ並びを再適用しても結果が変わらない
        self.page._reorder_visible_categories(["ard", "akm"], set(self.page._category_groups.keys()))
        order2 = _visible_order(self.page)
        self.assertEqual(order1, order2)
        self.assertEqual(last1, getattr(self.page, "_last_ordered_keys", []))


if __name__ == "__main__":
    unittest.main()
