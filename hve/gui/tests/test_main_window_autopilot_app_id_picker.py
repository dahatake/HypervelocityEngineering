"""test_main_window_autopilot_app_id_picker.py — AAS 完了後の APP-ID 選択ダイアログ
の main_window 統合テスト。

検証対象:
  - `MainWindow._should_show_app_id_picker`
  - `MainWindow._show_app_id_picker_for_catalog`

設定 `autopilot_show_app_id_picker` の ON/OFF、`pre_phases` への AAS 含有有無、
catalog の存在 / パース失敗 / 0 件、timeout 設定の異常値などを分岐ごとに確認する。

`AppIdPickerDialog.exec()` 自体は別ファイル `test_app_id_picker_dialog.py` で
カバー済みのため本ファイルではダイアログ起動はモック化する。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402
from hve.autopilot.plan_model import AutopilotSelection  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_main_window(tmp_path: Path) -> MainWindow:
    win = MainWindow()
    win._repo_root = str(tmp_path)
    return win


def _valid_catalog_text() -> str:
    """`parse_catalog` がパース可能な最小カタログ文字列。

    `## A) サマリ表（全APP横断）` セクションと `APP-ID` / `推薦アーキテクチャ`
    列を含むテーブルが必須。
    """
    return (
        "# Application Architecture Catalog\n"
        "\n"
        "## A) サマリ表（全APP横断）\n"
        "\n"
        "| APP-ID | APP名 | 推薦アーキテクチャ |\n"
        "|---|---|---|\n"
        "| APP-01 | App One | Azure App Service (Web) |\n"
        "| APP-02 | App Two | Azure Functions (Dataflow) |\n"
    )


# ---------------------------------------------------------------------------
# _should_show_app_id_picker
# ---------------------------------------------------------------------------

class TestShouldShowAppIdPicker:
    def test_setting_off_returns_none(self, qapp, tmp_path: Path) -> None:
        """設定 autopilot_show_app_id_picker=False のとき None。"""
        win = _make_main_window(tmp_path)
        catalog = tmp_path / "catalog.md"
        catalog.write_text(_valid_catalog_text(), encoding="utf-8")
        sel = AutopilotSelection(
            run_ard=False, run_aas=True, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        with patch(
            "hve.gui.settings_store.get_option",
            side_effect=lambda k, **kw: False
            if k == "autopilot_show_app_id_picker" else 300,
        ):
            result = win._should_show_app_id_picker(sel, catalog)
        assert result is None

    def test_aas_not_in_pre_phases_returns_none(
        self, qapp, tmp_path: Path
    ) -> None:
        """selection.pre_phases() に "aas" が無いとき None。"""
        win = _make_main_window(tmp_path)
        catalog = tmp_path / "catalog.md"
        catalog.write_text(_valid_catalog_text(), encoding="utf-8")
        # ARD のみ + downstream → pre_phases=["ard"]
        sel = AutopilotSelection(
            run_ard=True, run_aas=False, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        result = win._should_show_app_id_picker(sel, catalog)
        assert result is None

    def test_catalog_not_exists_returns_none(self, qapp, tmp_path: Path) -> None:
        """catalog ファイル不在のとき None。"""
        win = _make_main_window(tmp_path)
        sel = AutopilotSelection(
            run_ard=False, run_aas=True, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        result = win._should_show_app_id_picker(
            sel, tmp_path / "missing.md"
        )
        assert result is None

    def test_catalog_parse_error_returns_none(
        self, qapp, tmp_path: Path
    ) -> None:
        """catalog のパース失敗（ValueError）のとき None。"""
        win = _make_main_window(tmp_path)
        catalog = tmp_path / "broken.md"
        catalog.write_text("invalid content", encoding="utf-8")
        sel = AutopilotSelection(
            run_ard=False, run_aas=True, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        result = win._should_show_app_id_picker(sel, catalog)
        assert result is None

    def test_catalog_empty_returns_none(self, qapp, tmp_path: Path) -> None:
        """catalog パース成功・0 件のとき None（parse_catalog を空 dict にモック）。"""
        win = _make_main_window(tmp_path)
        catalog = tmp_path / "catalog.md"
        catalog.write_text(_valid_catalog_text(), encoding="utf-8")
        sel = AutopilotSelection(
            run_ard=False, run_aas=True, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        with patch("hve.app_arch_filter.parse_catalog", return_value={}):
            result = win._should_show_app_id_picker(sel, catalog)
        assert result is None

    def test_returns_entries_when_all_conditions_met(
        self, qapp, tmp_path: Path
    ) -> None:
        """設定 ON + AAS in pre_phases + catalog 非空 → entries を返す。"""
        win = _make_main_window(tmp_path)
        catalog = tmp_path / "catalog.md"
        catalog.write_text(_valid_catalog_text(), encoding="utf-8")
        sel = AutopilotSelection(
            run_ard=False, run_aas=True, run_aad_web=True,
            run_asdw_web=False, run_abd=False, run_abdv=False,
        )
        result = win._should_show_app_id_picker(sel, catalog)
        assert result is not None
        assert len(result) >= 1
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)
        app_ids = [aid for aid, _ in result]
        assert "APP-01" in app_ids


# ---------------------------------------------------------------------------
# _show_app_id_picker_for_catalog
# ---------------------------------------------------------------------------

class TestShowAppIdPickerForCatalog:
    def _entries(self):
        return [("APP-01", "Web"), ("APP-02", "Dataflow")]

    def test_accepted_returns_selected_list(
        self, qapp, tmp_path: Path
    ) -> None:
        """exec=Accepted → selected_app_ids() の戻り値を返す。"""
        win = _make_main_window(tmp_path)
        dlg_mock = MagicMock()
        dlg_mock.exec.return_value = QDialog.DialogCode.Accepted
        dlg_mock.selected_app_ids.return_value = ["APP-01"]
        with patch(
            "hve.gui.autopilot.app_id_picker_dialog.AppIdPickerDialog",
            return_value=dlg_mock,
        ):
            result = win._show_app_id_picker_for_catalog(self._entries())
        assert result == ["APP-01"]

    def test_rejected_returns_none(self, qapp, tmp_path: Path) -> None:
        """exec=Rejected → None を返す。"""
        win = _make_main_window(tmp_path)
        dlg_mock = MagicMock()
        dlg_mock.exec.return_value = QDialog.DialogCode.Rejected
        with patch(
            "hve.gui.autopilot.app_id_picker_dialog.AppIdPickerDialog",
            return_value=dlg_mock,
        ):
            result = win._show_app_id_picker_for_catalog(self._entries())
        assert result is None

    def test_accepted_with_empty_selection_returns_empty_list(
        self, qapp, tmp_path: Path
    ) -> None:
        """exec=Accepted + 全 OFF → ``[]`` を返す（呼び元で skip 扱い）。"""
        win = _make_main_window(tmp_path)
        dlg_mock = MagicMock()
        dlg_mock.exec.return_value = QDialog.DialogCode.Accepted
        dlg_mock.selected_app_ids.return_value = []
        with patch(
            "hve.gui.autopilot.app_id_picker_dialog.AppIdPickerDialog",
            return_value=dlg_mock,
        ):
            result = win._show_app_id_picker_for_catalog(self._entries())
        assert result == []

    @pytest.mark.parametrize(
        "raw_value,expected_timeout",
        [
            (60, 60),
            ("120", 120),
            ("abc", 300),  # 非数値 → 300
            (None, 300),   # None → 300
            (0, 300),      # 0 以下 → 300
            (-50, 300),    # 負値 → 300
        ],
    )
    def test_timeout_setting_fallback(
        self, qapp, tmp_path: Path, raw_value: Any, expected_timeout: int
    ) -> None:
        """異常値・正常値の timeout 設定が正しく AppIdPickerDialog に渡る。"""
        win = _make_main_window(tmp_path)
        dlg_mock = MagicMock()
        dlg_mock.exec.return_value = QDialog.DialogCode.Rejected
        captured = {}

        def _capture_ctor(parent, entries, **kwargs):
            captured["timeout_sec"] = kwargs.get("timeout_sec")
            return dlg_mock

        with patch(
            "hve.gui.settings_store.get_option",
            side_effect=lambda k, **kw: raw_value
            if k == "autopilot_app_id_picker_timeout_sec" else True,
        ), patch(
            "hve.gui.autopilot.app_id_picker_dialog.AppIdPickerDialog",
            side_effect=_capture_ctor,
        ):
            win._show_app_id_picker_for_catalog(self._entries())
        assert captured["timeout_sec"] == expected_timeout
