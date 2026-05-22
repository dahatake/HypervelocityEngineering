"""Wave 4 GUI: SettingsPricingTab の基本動作テスト (永続化なし)。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.settings_pricing_tab import SettingsPricingTab  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_settings_pricing_tab_defaults(qapp):
    tab = SettingsPricingTab()
    v = tab.values()
    assert v["pricing_usd_jpy_rate"] == 150.0
    assert v["pricing_currency"] == "auto"
    assert v["pricing_auto_refresh"] is True
    assert v["pricing_statusline_enabled"] is True


def test_settings_pricing_tab_custom_init(qapp):
    tab = SettingsPricingTab(
        usd_jpy_rate=155.5,
        currency="jpy",
        auto_refresh=False,
        statusline_enabled=False,
    )
    v = tab.values()
    assert v["pricing_usd_jpy_rate"] == 155.5
    assert v["pricing_currency"] == "jpy"
    assert v["pricing_auto_refresh"] is False
    assert v["pricing_statusline_enabled"] is False


def test_settings_pricing_tab_changes_emit_signal(qapp):
    tab = SettingsPricingTab()
    emitted = []
    tab.values_changed.connect(lambda: emitted.append(True))
    tab._rate_spin.setValue(160.0)
    assert len(emitted) >= 1
    assert tab.values()["pricing_usd_jpy_rate"] == 160.0
