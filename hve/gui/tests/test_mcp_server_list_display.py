"""C7 SDK resource snapshot display UI の単体テスト。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _snapshot(*, mcp_state: str = "ready") -> ResourceSnapshot:
    return ResourceSnapshot(
        plugin_state="ready",
        mcp_state=mcp_state,
        skill_state="ready",
        skill_ownership_state="ready",
        plugins=(
            ResourceItem(
                kind="plugin",
                name="docs-plugin",
                enabled=True,
                source_kind="marketplace",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
            ),
        ),
        mcp_servers=(
            ResourceItem(
                kind="mcp_server",
                name="workiq",
                enabled=True,
                source_kind="plugin",
                owner_plugin="docs-plugin",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
            ),
        )
        if mcp_state == "ready"
        else (),
        skills=(
            ResourceItem(
                kind="skill",
                name="answer-docs",
                enabled=True,
                source_kind="plugin",
                owner_plugin="docs-plugin",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
                description="Answer from approved documentation",
            ),
        ),
    )


def test_snapshot_resources_are_displayed_as_read_only_lists_without_auth_buttons(qapp) -> None:
    from hve.gui.page_options import _C7Connection

    widget = _C7Connection()
    try:
        widget.set_resource_snapshot(_snapshot())
        texts = [label.text() for label in widget.findChildren(type(widget._mcp_section_label))]
        joined = "\n".join(texts)

        assert "workiq" in joined
        assert "docs-plugin" in joined
        assert "--mcp-config" not in joined
        assert "OAuth" not in joined
        assert widget.mcp_enabled_dict() == {}
        assert [button.text() for button in widget.findChildren(QPushButton)] == ["SDK Resources を再検出"]
    finally:
        widget.deleteLater()


def test_initial_construction_does_not_run_copilot_cli(qapp, monkeypatch) -> None:
    from hve.gui.copilot_cli_bridge import CopilotCliBridge
    from hve.gui.page_options import _C7Connection

    # FR-GUI-51: CLI subprocess による再列挙経路そのものが無い。
    assert not hasattr(CopilotCliBridge, "list_plugin_resources")
    monkeypatch.setattr(
        CopilotCliBridge,
        "_run",
        staticmethod(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run Copilot CLI"))),
    )

    widget = _C7Connection()
    try:
        assert "確認中" in widget._mcp_empty_label.text()
        assert "確認中" in widget._plugin_empty_label.text()
        assert "確認中" in widget._skill_empty_label.text()
    finally:
        widget.deleteLater()


def test_refresh_uses_one_app_level_callback_with_force_refresh_true(qapp) -> None:
    from hve.gui.page_options import _C7Connection

    calls: list[bool] = []
    widget = _C7Connection()
    try:
        widget.set_resource_refresh_callback(
            lambda force_refresh=True: calls.append(force_refresh) or True
        )
        widget._on_refresh_clicked()

        assert calls == [True]
        assert widget._refresh_btn.isEnabled() is False
        assert widget._refresh_status.text() == "再検出中..."
    finally:
        widget.deleteLater()


def test_refresh_failure_is_not_reported_as_empty_configuration(qapp) -> None:
    from hve.gui.page_options import _C7Connection

    widget = _C7Connection()
    try:
        widget.set_resource_snapshot(_snapshot(mcp_state="unverified"))

        assert "登録された" not in widget._mcp_empty_label.text()
        assert "確認できません" in widget._mcp_empty_label.text()
    finally:
        widget.deleteLater()
