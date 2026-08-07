"""Wave 2 T2.2: LogTabsWidget の単体テスト。"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.widgets.log_tabs import LogTabsWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_two_tabs_present(qapp):
    w = LogTabsWidget()
    try:
        assert w._tabs.count() == 2
        assert w._tabs.tabText(0) == "全体"
        assert w._tabs.tabText(1) == "選択中"
    finally:
        w.deleteLater()


def test_append_global_appends_and_tail_follows(qapp):
    w = LogTabsWidget()
    try:
        w.append_global("line-1")
        w.append_global("line-2")
        qapp.processEvents()
        text = w.global_text()
        assert "line-1" in text and "line-2" in text
        sb = w._global_view.verticalScrollBar()
        # 末尾追従: 最大値に到達
        assert sb is None or sb.value() == sb.maximum()
    finally:
        w.deleteLater()


def test_append_global_coalesces_tail_follow(qapp, monkeypatch):
    """NFR-OBS-09 (3): 同一イベントループ内の連続追記の末尾追従を 1 回へ合体する。"""
    calls: list[int] = []
    original = LogTabsWidget._follow_tail_now

    def counting(self) -> None:
        calls.append(1)
        original(self)

    monkeypatch.setattr(LogTabsWidget, "_follow_tail_now", counting)

    w = LogTabsWidget()
    try:
        for i in range(5):
            w.append_global(f"coalesce-{i}")
        # 追記中は末尾追従を実行せず保留する
        assert calls == []
        assert w._tail_pending is True
        qapp.processEvents()
        # 5 回の追記に対し末尾追従は 1 回だけ実行される
        assert len(calls) == 1
        assert w._tail_pending is False
        sb = w._global_view.verticalScrollBar()
        assert sb is None or sb.value() == sb.maximum()
    finally:
        w.deleteLater()


def test_set_selected_content_replaces(qapp):
    w = LogTabsWidget()
    try:
        w.set_selected_content(["a", "b", "c"])
        text = w.selected_text()
        assert text == "a\nb\nc"
        # 差し替え: 別 lines で上書きされる
        w.set_selected_content(["x"])
        assert w.selected_text() == "x"
    finally:
        w.deleteLater()


def test_set_selected_content_accepts_string(qapp):
    w = LogTabsWidget()
    try:
        w.set_selected_content("single-line")
        assert w.selected_text() == "single-line"
    finally:
        w.deleteLater()


def test_clear_restores_placeholder(qapp):
    w = LogTabsWidget()
    try:
        w.append_global("g")
        w.set_selected_content(["s"])
        w.clear()
        assert w.global_text() == ""
        assert "選択" in w.selected_text() or "（" in w.selected_text()
    finally:
        w.deleteLater()


def test_copy_button_uses_active_tab(qapp):
    w = LogTabsWidget()
    try:
        w.append_global("G")
        w.set_selected_content(["S"])
        w._tabs.setCurrentIndex(LogTabsWidget.GLOBAL_TAB)
        assert w._copy_current_tab_text() == "G"
        w._tabs.setCurrentIndex(LogTabsWidget.SELECTED_TAB)
        assert w._copy_current_tab_text() == "S"
    finally:
        w.deleteLater()
