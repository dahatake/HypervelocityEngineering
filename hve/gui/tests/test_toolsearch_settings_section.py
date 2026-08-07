"""FR-GUI-07: GUI 設定画面の Tool-Search セクションの契約。

検証観点:
  (a) 3 タブ構成（基本 / ポリシー / 統計情報）
  (b) `settings_apply` が参照する `tool_search` / `tool_search_ranking` の公開
  (c) 設定入力欄が設定画面の単独所有であること（Step 1 右ペインと二重に持たない）
  (d) `policy.json` は読み取り専用で、読めないときに既定値を推測しないこと
  (e) 統計は `hve.toolsearch.dashboard` を単一の情報源とし、GUI で再実装しないこと
  (f) 収集済みイベントが無いとき 0 で埋めず「データ不足」を表示すること
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from hve.gui import settings_store

    fake = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake)
    return fake


@pytest.fixture()
def section(qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    monkeypatch.setenv("HVE_TOOLSEARCH_EVENTS", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("HVE_TOOLSEARCH_USAGE", str(tmp_path / "usage.jsonl"))
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    yield widget
    widget.deleteLater()


# ---------------------------------------------------------------------------
# (a) タブ構成
# ---------------------------------------------------------------------------


def test_has_three_tabs(section) -> None:
    assert section.tab_count() == 3


def test_tab_labels(section) -> None:
    assert section.tab_labels() == ("基本", "ポリシー", "統計情報")


# ---------------------------------------------------------------------------
# (b) settings_apply 契約
# ---------------------------------------------------------------------------


def test_exposes_the_widgets_settings_apply_binds_to(section) -> None:
    from PySide6.QtWidgets import QCheckBox, QComboBox

    assert isinstance(section.tool_search, QCheckBox)
    assert isinstance(section.tool_search_ranking, QComboBox)


def test_ranking_combo_offers_both_modes(section) -> None:
    values = [
        section.tool_search_ranking.itemData(i)
        for i in range(section.tool_search_ranking.count())
    ]
    assert values == ["sdk", "hve"]


def test_settings_apply_maps_this_section() -> None:
    from hve.gui.settings_apply import _SECTION_FIELDS

    assert _SECTION_FIELDS["TOOLSEARCH"] == {
        "tool_search": "tool_search",
        "tool_search_ranking": "tool_search_ranking",
    }


def test_defaults_include_the_ranking_key() -> None:
    from hve.gui import settings_store

    assert settings_store.defaults()["options"]["tool_search_ranking"] == "sdk"


def test_fresh_default_enables_tool_search() -> None:
    """FR-MODEL-04: 新規プロファイルの初期値は有効。"""
    from hve.gui import settings_store

    assert settings_store.defaults()["options"]["tool_search"] is True


def test_saved_disabled_value_is_preserved(patched_settings: Path) -> None:
    """FR-MODEL-06: 保存済みの false を既定有効化で上書きしない。"""
    from hve.gui import settings_store

    patched_settings.write_text(
        "[options]\ntool_search = false\n", encoding="utf-8"
    )
    assert settings_store.load()["options"]["tool_search"] is False


# ---------------------------------------------------------------------------
# (c) 二重管理の禁止（FR-MAINT-07）
# ---------------------------------------------------------------------------


def test_autopilot_section_no_longer_owns_tool_search() -> None:
    from hve.gui.settings_apply import _SECTION_FIELDS

    assert "tool_search" not in _SECTION_FIELDS["AUTOPILOT"]


def test_step1_pane_has_no_duplicate_input() -> None:
    source = (_REPO_ROOT / "hve" / "gui" / "page_options.py").read_text(encoding="utf-8")
    assert "self.tool_search_ranking = QComboBox()" not in source
    # Foundry Toolbox 側（生成する AI Agent 向け）は別ドメインなので残る。
    assert "self.enable_tool_search = QComboBox()" in source


def test_registered_in_the_skills_registry() -> None:
    from hve.gui import settings_window  # noqa: F401 - 登録の副作用が必要
    from hve.gui.skill_sections import get_registry

    entry = get_registry().get("TOOLSEARCH")
    assert entry is not None
    assert entry.label == "Tool-Search"


# ---------------------------------------------------------------------------
# (d) policy.json は読み取り専用
# ---------------------------------------------------------------------------


def test_policy_view_is_read_only(section) -> None:
    assert section.policy_view.isReadOnly()


def test_policy_view_shows_the_real_values(section) -> None:
    text = section.policy_view.toPlainText()
    assert "limit" in text
    assert "tau" in text
    assert "field_weights" in text


def test_policy_view_shows_the_source_path(section) -> None:
    assert "policy.json" in section.policy_path_label.text()


def test_unreadable_policy_does_not_fabricate_defaults(
    qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    broken = tmp_path / "policy.json"
    broken.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path", staticmethod(lambda: broken)
    )
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        text = widget.policy_view.toPlainText()
        assert "読み込めません" in text
        assert str(broken) in text
    finally:
        widget.deleteLater()


# ---------------------------------------------------------------------------
# (e)(f) 統計
# ---------------------------------------------------------------------------


def test_stats_view_is_read_only(section) -> None:
    assert section.stats_view.isReadOnly()


def test_stats_are_not_loaded_until_the_tab_is_opened(section) -> None:
    """イベントログは無制限に伸びるので、設定画面を開いただけでは読まない。"""
    assert section.stats_view.toPlainText() == ""


def test_opening_the_stats_tab_loads_them(section) -> None:
    section._tabs.setCurrentIndex(2)
    assert "検索回数" in section.stats_view.toPlainText()


def test_empty_store_shows_no_data_rather_than_zero(section) -> None:
    section.reload_stats()
    assert "データ不足" in section.stats_view.toPlainText()


def test_stats_come_from_the_dashboard_module(section, tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "kind": "toolsearch.query",
                "ts": "2026-08-04T00:00:00Z",
                "run_id": "r1",
                "workflow_id": "ard",
                "step_id": "1.1",
                "query": "リソースを一覧したい",
                "hits": ["azmcp_group_list"],
                "scores": [3.5],
                "latency_ms": 4.0,
                "catalog": {"total": 39, "pinned": 7, "searchable": 32, "dropped": 0,
                            "deferred": 32, "mcp": 4, "native": 4, "skill": 31},
                "tokens": {"baseline": 5072, "exposed": 1084},
                "warnings": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    section.reload_stats()
    text = section.stats_view.toPlainText()
    assert "検索回数" in text
    assert "リソースを一覧したい" in text


def test_gui_does_not_reimplement_aggregation() -> None:
    """FR-MAINT-07: 集計・整形は dashboard / stats に一本化する。"""
    source = (
        _REPO_ROOT / "hve" / "gui" / "toolsearch_settings_section.py"
    ).read_text(encoding="utf-8")
    assert "from ..toolsearch.dashboard import" in source
    for forbidden in ("Counter(", "def _percentile", "def _aggregate"):
        assert forbidden not in source


def test_shows_the_collection_paths(section) -> None:
    text = section.paths_label.text()
    assert "events.jsonl" in text
    assert "usage.jsonl" in text


def test_html_export_writes_a_self_contained_file(section, tmp_path: Path) -> None:
    out = tmp_path / "dash.html"
    section.export_html(out)
    body = out.read_text(encoding="utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "https://" not in body


def test_clear_events_removes_the_store(section, tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("{}\n", encoding="utf-8")
    section.clear_events()
    assert not events.exists()


def test_clear_events_tolerates_a_missing_store(section, tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").unlink(missing_ok=True)
    section.clear_events()


def test_reload_tolerates_a_broken_store(section, tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").write_text("{ broken\n", encoding="utf-8")
    section.reload_stats()
    assert section.stats_view.toPlainText()
