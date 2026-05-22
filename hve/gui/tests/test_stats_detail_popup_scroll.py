"""StatsDetailPopup の 1Hz tick 時にスクロール位置が保持されることを検証する。

修正前は ``_on_tick`` がスナップショットタブを ``removeTab``/``insertTab`` で
丸ごと差し替えるため、内部の ``QScrollArea`` も再生成され縦スクロール位置が
強制的に 0 に戻っていた。本テストはリグレッション防止のためのもの。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QScrollArea

from hve.gui.stats_detail_popup import StatsDetailPopup
from hve.gui.workbench_state import WorkbenchState


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def test_on_tick_preserves_vertical_scroll_position() -> None:
    _ensure_qapp()
    state = WorkbenchState(workflow_id="wf", run_id="r1", model="gpt-x")
    popup = StatsDetailPopup(state)
    try:
        # show() しないと isVisible() が False で _on_tick が早期 return する
        popup.show()
        QCoreApplication.processEvents()

        tabs = popup._tabs
        assert tabs is not None
        scroll = tabs.widget(0)
        assert isinstance(scroll, QScrollArea)

        # スクロール可能になるよう内部 widget を大きくレイアウトしておく
        inner = scroll.widget()
        assert inner is not None
        inner.setMinimumHeight(3000)
        QCoreApplication.processEvents()

        vbar = scroll.verticalScrollBar()
        assert vbar is not None
        # スクロール範囲が確保されたことを確認したうえで任意の正値を設定
        assert vbar.maximum() > 0, "テスト前提: スクロール範囲が確保されていない"
        target = min(150, vbar.maximum())
        vbar.setValue(target)
        assert vbar.value() == target

        # tick 実行（タブ再構築が走る）
        popup._on_tick()
        # singleShot(0) で復元されるため processEvents を回す
        for _ in range(3):
            QCoreApplication.processEvents()

        new_scroll = tabs.widget(0)
        assert isinstance(new_scroll, QScrollArea)
        new_inner = new_scroll.widget()
        assert new_inner is not None
        new_inner.setMinimumHeight(3000)
        QCoreApplication.processEvents()
        for _ in range(3):
            QCoreApplication.processEvents()

        new_vbar = new_scroll.verticalScrollBar()
        assert new_vbar is not None
        assert new_vbar.value() == target, (
            f"スクロール位置が保持されていない: expected={target}, actual={new_vbar.value()}"
        )
    finally:
        popup.close()
        popup.deleteLater()
        QCoreApplication.processEvents()
