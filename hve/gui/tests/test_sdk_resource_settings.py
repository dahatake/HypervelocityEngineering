"""FR-GUI-53: Tool-Search resource editor and settings wiring."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QTableWidget  # noqa: E402

from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hve.gui import settings_store

    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / "settings.json")


@pytest.fixture()
def editable_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from hve.toolsearch.policy import ToolSearchPolicy

    target = tmp_path / "policy.json"
    raw = json.loads(ToolSearchPolicy.default_path().read_text(encoding="utf-8"))
    raw["resource_classifications"]["plugins"]["docs-plugin"] = "knowledge"
    raw["step_overrides"]["asdw-web:1.2"]["note"] = "keep-me"
    target.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path",
        staticmethod(lambda repo_root=None: target),
    )
    return target


def _snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        plugin_state="ready",
        mcp_state="ready",
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
        ),
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


def _row_for_name(widget, name: str) -> int:
    for row in range(widget._resource_table.rowCount()):
        item = widget._resource_table.item(row, 1)
        if item is not None and item.text() == name:
            return row
    raise AssertionError(f"resource row not found: {name}")


def test_toolsearch_section_adds_sdk_resources_tab_and_safe_columns_only(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        assert widget.tab_labels() == (
            "基本",
            "SDK Resources",
            "Skill Layer",
            "ポリシー",
            "統計情報",
            "コンテキスト内訳",
        )
        assert widget._resource_table.columnCount() == 8
        assert [
            widget._resource_table.horizontalHeaderItem(i).text()
            for i in range(widget._resource_table.columnCount())
        ] == [
            "kind",
            "name",
            "source_kind",
            "plugin_marketplace",
            "owner_plugin",
            "enabled",
            "effective_category",
            "individual_override",
        ]
        widget.set_resource_snapshot(_snapshot())
        visible = "\n".join(
            widget._resource_table.item(row, column).text()
            for row in range(widget._resource_table.rowCount())
            for column in range(widget._resource_table.columnCount())
        )
        assert "1.2.3" not in visible
        assert "Answer from approved documentation" not in visible
    finally:
        widget.deleteLater()


def test_resource_tab_exposes_only_classification_allowlists_and_read_only_refresh(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        resource_tab = widget._tabs.widget(1)
        assert resource_tab is not None
        assert resource_tab.findChildren(QComboBox) == [
            widget._resource_classification_combo
        ]
        assert set(resource_tab.findChildren(QTableWidget)) == {
            widget._resource_table,
            widget._knowledge_allowlists._table,
            widget._software_allowlists._table,
        }
        assert sorted(
            button.text() for button in resource_tab.findChildren(QPushButton)
        ) == [
            "SDK Resources を再検出",
            "行を追加",
            "行を追加",
            "選択行を削除",
            "選択行を削除",
        ]
    finally:
        widget.deleteLater()


def test_resource_editor_uses_owner_plugin_fallback_until_exact_override_is_set(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.set_resource_snapshot(_snapshot())
        row = _row_for_name(widget, "answer-docs")
        widget._resource_table.selectRow(row)
        qapp.processEvents()

        assert widget._resource_classification_combo.currentData() == ""
        assert "effective=knowledge" in widget._resource_selected_label.text()

        index = widget._resource_classification_combo.findData("software-engineering")
        widget._resource_classification_combo.setCurrentIndex(index)
        assert widget._resource_classifications["skills"]["answer-docs"] == "software-engineering"
        assert "effective=software-engineering" in widget._resource_selected_label.text()
    finally:
        widget.deleteLater()


def test_unverified_plugin_ownership_is_not_used_for_effective_category(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    snapshot = _snapshot()
    snapshot = ResourceSnapshot(
        plugin_state="unverified",
        mcp_state=snapshot.mcp_state,
        skill_state=snapshot.skill_state,
        skill_ownership_state="unverified",
        plugins=snapshot.plugins,
        mcp_servers=snapshot.mcp_servers,
        skills=snapshot.skills,
    )
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.set_resource_snapshot(snapshot)
        row = _row_for_name(widget, "answer-docs")
        assert widget._resource_table.item(row, 6).text() == "unclassified"
        assert widget._resource_table.item(row, 7).text() == ""
    finally:
        widget.deleteLater()


def test_unverified_kinds_are_shown_as_unconfirmed_not_empty(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.set_resource_snapshot(
            ResourceSnapshot(
                plugin_state="unverified",
                mcp_state="unverified",
                skill_state="unverified",
                skill_ownership_state="unverified",
                plugins=(),
                mcp_servers=(),
                skills=(),
            )
        )
        text = widget._resource_state_label.text()
        assert "未確認" in text
        assert "0 件" not in text
        assert "unverified" not in text
    finally:
        widget.deleteLater()


def test_resource_tab_explains_plugin_limit_cloud_boundary_and_next_session(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        text = widget._resource_scope_note.text()
        assert "hook" in text
        assert "agent" in text
        assert "instruction" in text
        assert "Cloud Session" in text
        assert "次に開始" in text
    finally:
        widget.deleteLater()


def test_save_policy_preserves_extra_and_nested_step_override_metadata(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.set_resource_snapshot(_snapshot())
        row = _row_for_name(widget, "answer-docs")
        widget._resource_table.selectRow(row)
        qapp.processEvents()
        widget._resource_classification_combo.setCurrentIndex(
            widget._resource_classification_combo.findData("software-engineering")
        )
        widget._knowledge_allowlists.add_row("docs", "search read_document")
        widget._software_allowlists.add_row("build", "compile, test")

        widget.save_policy()
        raw = json.loads(editable_policy.read_text(encoding="utf-8"))
        assert raw["_comment"]
        assert raw["step_overrides"]["asdw-web:1.2"]["note"] == "keep-me"
        assert raw["resource_classifications"]["skills"]["answer-docs"] == "software-engineering"
        assert raw["knowledge_tool_allowlists"]["docs"] == ["search", "read_document"]
        assert raw["software_engineering_tool_allowlists"]["build"] == ["compile", "test"]
        assert raw["required_mcp_servers_by_skill"] == {
            "microsoft-foundry": ["azure", "microsoft-learn"]
        }
    finally:
        widget.deleteLater()


def test_policy_reload_refreshes_effective_and_override_columns_for_all_rows(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.set_resource_snapshot(_snapshot())
        row = _row_for_name(widget, "answer-docs")
        assert widget._resource_table.item(row, 6).text() == "knowledge"
        assert widget._resource_table.item(row, 7).text() == ""

        raw = json.loads(editable_policy.read_text(encoding="utf-8"))
        raw["resource_classifications"]["skills"]["answer-docs"] = "both"
        editable_policy.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        widget.reload_policy()

        row = _row_for_name(widget, "answer-docs")
        assert widget._resource_table.item(row, 6).text() == "both"
        assert widget._resource_table.item(row, 7).text() == "both"
    finally:
        widget.deleteLater()


def test_resource_refresh_button_uses_app_level_callback_with_force_refresh_true(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    calls: list[bool] = []
    try:
        widget.set_resource_refresh_callback(lambda force_refresh=True: calls.append(force_refresh) or True)
        widget.set_resource_snapshot(_snapshot())
        widget._resource_refresh_button.click()
        assert calls == [True]
        assert "開始" in widget._resource_result_label.text()
    finally:
        widget.deleteLater()


def test_resource_refresh_button_is_disabled_until_snapshot_arrives(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        assert widget._resource_snapshot is None
        assert not widget._resource_refresh_button.isEnabled()
        widget.set_resource_snapshot(_snapshot())
        assert widget._resource_refresh_button.isEnabled()
        widget.set_resource_snapshot(
            ResourceSnapshot(
                plugin_state="unverified",
                mcp_state="unverified",
                skill_state="unverified",
                skill_ownership_state="unverified",
                plugins=(),
                mcp_servers=(),
                skills=(),
            )
        )
        assert widget._resource_refresh_button.isEnabled()
    finally:
        widget.deleteLater()


def test_settings_window_shares_same_snapshot_object_with_c7_and_toolsearch_sections(
    qapp, patched_settings, editable_policy
) -> None:
    from hve.gui.settings_window import SettingsWindow

    snapshot = _snapshot()
    window = SettingsWindow(repo_root=_REPO_ROOT)
    try:
        window.set_resource_refresh_callback(lambda force_refresh=True: bool(force_refresh))
        window.set_resource_snapshot(snapshot)

        c7 = window._sections["C7"]
        toolsearch = window._sections["TOOLSEARCH"]
        assert c7._resource_snapshot is snapshot
        assert toolsearch._resource_snapshot is snapshot
        assert c7._resource_refresh_callback is not None
        assert toolsearch._resource_refresh_callback is not None
    finally:
        window.deleteLater()
