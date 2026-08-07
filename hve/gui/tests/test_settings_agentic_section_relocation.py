"""hve.gui.tests.test_settings_agentic_section_relocation

設定画面の Agentic Retrieval セクション移設に関する回帰防止テスト。

検証内容:
  1. カテゴリツリーのグループラベルが「各サービス連携」であること（旧「連携」は無い）。
  2. 「各サービス連携」配下に ("Agentic Retrieval", "AGENTIC") が Azure の直後にあること。
  3. _C1Basic が Agentic Retrieval 系ウィジェットを持たず、enable_tool_search は持ち続けること。
  4. _CAgenticRetrieval が同ウィジェット群と to_args を持つこと。
  5. OptionsPage が新セクションを保持し、既定値では Agentic 系フラグを出さず、
     非既定値では argv へ出力すること（CLI 引数配線の維持）。
  6. Step 1 右ペインでは新セクション枠を表示しないこと。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

# _C1Basic から _CAgenticRetrieval へ移設したウィジェット属性。
_MOVED_WIDGETS = [
    "enable_agentic_retrieval",
    "agentic_data_source_modes",
    "foundry_mcp_integration",
    "agentic_data_sources_hint",
    "agentic_existing_design_diff_only",
    "foundry_sku_fallback_policy",
]

# 既定状態（全項目が「自動判定に従う」/「既定に従う」/ 空欄）で出てはならないフラグ。
_AGENTIC_FLAGS = [
    "--enable-agentic-retrieval",
    "--agentic-data-source-modes",
    "--foundry-mcp-integration",
    "--no-foundry-mcp-integration",
    "--agentic-data-sources-hint",
    "--agentic-existing-design-diff-only",
    "--no-agentic-existing-design-diff-only",
    "--foundry-sku-fallback-policy",
]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings_window(qapp, tmp_path: Path, monkeypatch):
    from hve.gui import settings_store
    from hve.gui.settings_window import SettingsWindow

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    win = SettingsWindow(repo_root=tmp_path)
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# 1-2. カテゴリツリー
# ---------------------------------------------------------------------------
def test_category_tree_renames_integration_group() -> None:
    """グループラベルが「各サービス連携」へ変更され、旧「連携」が残らないこと。"""
    from hve.gui.settings_window import _CATEGORY_TREE

    labels = [label for label, _items in _CATEGORY_TREE]
    assert "各サービス連携" in labels
    assert "連携" not in labels


def test_agentic_node_placed_after_azure() -> None:
    """「各サービス連携」配下で Agentic Retrieval が Azure の直後にあること。"""
    from hve.gui.settings_window import _CATEGORY_TREE

    groups = dict(_CATEGORY_TREE)
    assert "各サービス連携" in groups, f"グループが見つからない: {list(groups)}"
    items = groups["各サービス連携"]
    assert ("Agentic Retrieval", "AGENTIC") in items
    keys = [key for _name, key in items]
    assert keys.index("AGENTIC") == keys.index("AZURE") + 1


def test_settings_window_builds_agentic_section(settings_window) -> None:
    """AGENTIC ノードが _CAgenticRetrieval セクションとして構築されること。"""
    from hve.gui.page_options import _CAgenticRetrieval

    assert isinstance(settings_window._sections.get("AGENTIC"), _CAgenticRetrieval)


# ---------------------------------------------------------------------------
# 3-4. ウィジェット属性の所在
# ---------------------------------------------------------------------------
def test_c1_basic_lacks_agentic_widgets(qapp) -> None:
    """_C1Basic から Agentic 系のみが抜け、enable_tool_search は残ること。"""
    from hve.gui.page_options import _C1Basic

    w = _C1Basic()
    for key in _MOVED_WIDGETS:
        assert not hasattr(w, key), f"_C1Basic に属性 {key} が残存"
    assert hasattr(w, "enable_tool_search"), "_C1Basic から enable_tool_search を巻き込み移動している"


def test_agentic_section_owns_widgets(qapp) -> None:
    """_CAgenticRetrieval が移設先として全ウィジェットと to_args を持つこと。"""
    from hve.gui.page_options import _CAgenticRetrieval

    w = _CAgenticRetrieval()
    for key in _MOVED_WIDGETS:
        assert hasattr(w, key), f"_CAgenticRetrieval に属性 {key} が無い"
    assert callable(getattr(w, "to_args", None))
    assert not hasattr(w, "enable_tool_search"), "enable_tool_search は移設対象外"


# ---------------------------------------------------------------------------
# 5-6. argv 生成挙動と Step 1 表示
# ---------------------------------------------------------------------------
@pytest.fixture
def options_page(qapp, tmp_path: Path, monkeypatch):
    from hve.gui import settings_store
    from hve.gui.page_options import OptionsPage

    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    page = OptionsPage()
    yield page
    page.deleteLater()


def test_options_page_default_argv_has_no_agentic_flags(options_page) -> None:
    """OptionsPage が新セクションを保持し、既定 argv に Agentic 系フラグが出ないこと。"""
    from hve.gui.page_options import _CAgenticRetrieval

    assert isinstance(options_page.c_agentic, _CAgenticRetrieval)

    argv = options_page.build_args_for_workflow("asdw-web").to_argv()
    for flag in _AGENTIC_FLAGS:
        assert flag not in argv, f"既定状態で {flag} が argv へ出力された"


def test_options_page_emits_agentic_flags_when_selected(options_page) -> None:
    """非既定値を選ぶと argv へ反映されること（to_args 配線の断線検出）。"""
    sec = options_page.c_agentic
    sec.enable_agentic_retrieval.setCurrentIndex(
        sec.enable_agentic_retrieval.findData("no")
    )
    sec.foundry_mcp_integration.setCurrentIndex(
        sec.foundry_mcp_integration.findData(False)
    )
    sec.agentic_data_sources_hint.setText("Blob と Azure SQL")

    argv = options_page.build_args_for_workflow("asdw-web").to_argv()
    assert "--enable-agentic-retrieval" in argv
    assert argv[argv.index("--enable-agentic-retrieval") + 1] == "no"
    assert "--no-foundry-mcp-integration" in argv
    assert "--agentic-data-sources-hint" in argv
    assert argv[argv.index("--agentic-data-sources-hint") + 1] == "Blob と Azure SQL"


def test_agentic_group_hidden_in_step1_pane(options_page) -> None:
    """Step 1 右ペインで AGENTIC 枠を表示しないこと（C1 と同じ扱い）。"""
    from hve.gui import page_options

    assert "AGENTIC" in page_options._STEP2_HIDDEN_CATEGORIES
    group = options_page._category_groups.get("AGENTIC")
    assert group is not None
    assert group.isVisible() is False