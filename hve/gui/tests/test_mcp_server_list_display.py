"""MCP Server 一覧表示 UI の単体テスト。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_mcp_servers_are_displayed_as_list_not_toggles(qapp, monkeypatch) -> None:
    from hve.gui.copilot_cli_bridge import CopilotCliBridge
    from hve.gui.page_options import _C7Connection

    monkeypatch.setattr(
        CopilotCliBridge,
        "list_mcp_servers",
        classmethod(lambda cls, **_kwargs: {"azure": {}, "context7": {}}),
    )
    monkeypatch.setattr(CopilotCliBridge, "list_plugins", classmethod(lambda cls, **_kwargs: []))

    w = _C7Connection()
    try:
        assert "登録済み MCP Server" in w._mcp_section_label.text()
        checkboxes = w._mcp_container.findChildren(QCheckBox)
        assert checkboxes == []
        buttons = [b.text() for b in w._mcp_container.findChildren(QPushButton)]
        assert buttons.count("認証手順...") == 2
        assert w.mcp_enabled_dict() == {}
    finally:
        w.deleteLater()
