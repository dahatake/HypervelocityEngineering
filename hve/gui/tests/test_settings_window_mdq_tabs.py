"""hve.gui.tests.test_settings_window_mdq_tabs

_MdqIndexSection のタブ化（基本 / インデックス管理 / 統計情報）の smoke テスト。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QTabWidget,
    QTextBrowser,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_mdq_section_has_three_tabs(qapp, tmp_path: Path, monkeypatch):
    from hve.gui import settings_store
    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )

    # 自動再生成スレッドの起動を抑止するため、latest.md を新鮮な状態で配置
    report_dir = tmp_path / "tools" / "skills" / "markdown_query" / "usage-report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.md").write_text("# dummy\n", encoding="utf-8")

    from hve.gui.settings_window import _MdqIndexSection

    section = _MdqIndexSection(repo_root=tmp_path)

    tab_widgets = section.findChildren(QTabWidget)
    assert len(tab_widgets) == 1, f"expected 1 QTabWidget, got {len(tab_widgets)}"
    tabs = tab_widgets[0]
    assert tabs.count() == 3, f"expected 3 tabs, got {tabs.count()}"

    # 翻訳器非ロード前提のため日本語ソース文字列が返る
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert labels == ["基本", "インデックス管理", "統計情報"], labels

    # 後方互換: settings_apply が参照する属性
    assert hasattr(section, "mdq_watch")
    assert hasattr(section, "mdq_watch_debounce_ms")

    basic_tab = tabs.widget(0)
    index_tab = tabs.widget(1)
    stats_tab = tabs.widget(2)

    # 基本タブ: 言語と Strategy の QComboBox
    assert basic_tab.findChildren(QComboBox), "基本タブに QComboBox が無い"

    # インデックス管理タブ: 改名後の見出し存在＋旧名残存なし
    index_label_texts = [lbl.text() for lbl in index_tab.findChildren(QLabel)]
    assert any("<b>リアルタイム更新</b>" == t for t in index_label_texts), (
        f"改名後の見出し『リアルタイム更新』が見つからない: {index_label_texts}"
    )
    assert not any("リアルタイム索引更新" in t for t in index_label_texts), (
        f"旧名『リアルタイム索引更新』が残存している: {index_label_texts}"
    )
    assert any("mdq リアルタイム更新" == t for t in index_label_texts), (
        "LabeledField の title『mdq リアルタイム更新』が見つからない"
    )
    assert not any("mdq リアルタイム索引更新" in t for t in index_label_texts), (
        "旧 title『mdq リアルタイム索引更新』が残存している"
    )

    # 統計情報タブ: QTextBrowser
    assert stats_tab.findChildren(QTextBrowser), "統計情報タブに QTextBrowser が無い"


def test_bulk_build_ui_moved_to_index_tab_db_group(qapp, tmp_path: Path, monkeypatch):
    """T6 構造変更: 一括ビルド UI は basic タブから消え、index タブの

    「インデックス DB の管理」QGroupBox 内に存在することを検証する。
    """
    from hve.gui import settings_store
    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    report_dir = tmp_path / "tools" / "skills" / "markdown_query" / "usage-report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.md").write_text("# dummy\n", encoding="utf-8")

    from hve.gui.settings_window import _MdqIndexSection

    section = _MdqIndexSection(repo_root=tmp_path)
    tabs = section.findChildren(QTabWidget)[0]
    basic_tab = tabs.widget(0)
    index_tab = tabs.widget(1)

    # basic タブのレイアウト上に _build_strategies_list が存在しないこと
    # (widget は生成されるが addWidget されないため、basic_tab を ancestor に持たない)
    bulk_list = section._build_strategies_list
    parent = bulk_list.parentWidget()
    # basic_tab が祖先に含まれないこと
    ancestors: list = []
    p = parent
    while p is not None:
        ancestors.append(p)
        p = p.parentWidget()
    assert basic_tab not in ancestors, (
        "一括ビルド _build_strategies_list が basic タブ配下に残存している"
    )

    # index タブ配下に「インデックス DB の管理」QGroupBox があり、
    # その内部に _build_strategies_list と差分更新/完全再ビルド/DB削除/一括ビルド
    # 全 4 ボタンが存在すること
    groups = [
        g for g in index_tab.findChildren(QGroupBox)
        if g.title() == "インデックス DB の管理"
    ]
    assert len(groups) == 1, (
        f"index タブに 'インデックス DB の管理' QGroupBox が見つからない: "
        f"{[g.title() for g in index_tab.findChildren(QGroupBox)]}"
    )
    db_group = groups[0]
    lists_in_group = db_group.findChildren(QListWidget)
    assert bulk_list in lists_in_group, (
        "_build_strategies_list が DB管理 GroupBox 内に存在しない"
    )
    # 4 ボタンの存在確認
    for btn_name in (
        "_btn_incremental_refresh",
        "_btn_force_rebuild",
        "_btn_delete_db",
        "_btn_bulk_build",
    ):
        btn = getattr(section, btn_name)
        anc: list = []
        p = btn.parentWidget()
        while p is not None:
            anc.append(p)
            p = p.parentWidget()
        assert db_group in anc, (
            f"{btn_name} が DB管理 GroupBox 配下に存在しない"
        )
