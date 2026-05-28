"""test_app_id_picker_dialog.py — AppIdPickerDialog の単体テスト (offscreen)。

実行: QT_QPA_PLATFORM=offscreen pytest hve/gui/tests/test_app_id_picker_dialog.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication

from hve.gui.autopilot.app_id_picker_dialog import (
    AppIdPickerDialog,
    format_remaining,
)


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class FormatRemainingTests(unittest.TestCase):
    """``format_remaining`` 純ロジックの境界値テスト（Qt 非依存）。"""

    def test_zero(self) -> None:
        self.assertEqual(format_remaining(0), "00:00")

    def test_under_minute(self) -> None:
        self.assertEqual(format_remaining(59), "00:59")

    def test_one_minute(self) -> None:
        self.assertEqual(format_remaining(60), "01:00")

    def test_mixed(self) -> None:
        self.assertEqual(format_remaining(65), "01:05")

    def test_five_minutes(self) -> None:
        self.assertEqual(format_remaining(300), "05:00")

    def test_negative_clamped_to_zero(self) -> None:
        self.assertEqual(format_remaining(-5), "00:00")


class AppIdPickerDialogTests(unittest.TestCase):
    """``AppIdPickerDialog`` の UI 振る舞いテスト。"""

    def setUp(self) -> None:
        _get_app()

    def _make_entries(self):
        return [
            ("APP-01", "WebApp"),
            ("APP-02", "Dataflow"),
            ("APP-03", "WebApp"),
        ]

    def test_initial_all_checked(self) -> None:
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=300)
        try:
            self.assertEqual(
                dlg.selected_app_ids(), ["APP-01", "APP-02", "APP-03"]
            )
        finally:
            dlg.deleteLater()

    def test_individual_uncheck_reflected(self) -> None:
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=300)
        try:
            item = dlg._list.item(1)  # type: ignore[attr-defined]
            self.assertIsNotNone(item)
            assert item is not None
            item.setCheckState(Qt.CheckState.Unchecked)
            self.assertEqual(dlg.selected_app_ids(), ["APP-01", "APP-03"])
        finally:
            dlg.deleteLater()

    def test_all_unchecked_returns_empty(self) -> None:
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=300)
        try:
            for i in range(dlg._list.count()):  # type: ignore[attr-defined]
                dlg._list.item(i).setCheckState(  # type: ignore[union-attr,attr-defined]
                    Qt.CheckState.Unchecked
                )
            self.assertEqual(dlg.selected_app_ids(), [])
        finally:
            dlg.deleteLater()

    def test_timeout_sanitize_zero(self) -> None:
        """timeout_sec=0 は 1 にサニタイズされる（即 accept 連鎖を防ぐ）。"""
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=0)
        try:
            self.assertEqual(dlg._remaining, 1)  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_timeout_sanitize_negative(self) -> None:
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=-10)
        try:
            self.assertEqual(dlg._remaining, 1)  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_timeout_sanitize_invalid_type(self) -> None:
        dlg = AppIdPickerDialog(
            None, self._make_entries(), timeout_sec="abc"  # type: ignore[arg-type]
        )
        try:
            self.assertEqual(dlg._remaining, 1)  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_on_tick_decrements(self) -> None:
        """_on_tick 1 回呼び出しで remaining が 1 減少し、ラベルが更新される。"""
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=5)
        try:
            dlg._on_tick()  # type: ignore[attr-defined]
            self.assertEqual(dlg._remaining, 4)  # type: ignore[attr-defined]
            self.assertIn("04", dlg._remaining_label.text())  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_on_tick_auto_accept_at_zero(self) -> None:
        """残り 1 から tick すると 0 到達で accept 経路を通る。"""
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=1)
        accepted = []
        dlg.accepted.connect(lambda: accepted.append(True))
        try:
            dlg._on_tick()  # type: ignore[attr-defined]
            QCoreApplication.processEvents()
            self.assertTrue(accepted)
            # タイマーは done() override で停止する
            self.assertFalse(dlg._timer.isActive())  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_reject_stops_timer(self) -> None:
        """reject 経路でも done() override が timer を停止する。"""
        dlg = AppIdPickerDialog(None, self._make_entries(), timeout_sec=300)
        try:
            self.assertTrue(dlg._timer.isActive())  # type: ignore[attr-defined]
            dlg.reject()
            self.assertFalse(dlg._timer.isActive())  # type: ignore[attr-defined]
        finally:
            dlg.deleteLater()

    def test_entry_without_architecture(self) -> None:
        """architecture が空文字でも表示できる。"""
        dlg = AppIdPickerDialog(
            None, [("APP-99", "")], timeout_sec=300
        )
        try:
            self.assertEqual(dlg.selected_app_ids(), ["APP-99"])
        finally:
            dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
