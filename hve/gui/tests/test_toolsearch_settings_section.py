"""FR-GUI-07: GUI 設定画面の Tool-Search セクションの契約。

検証観点:
  (a) 4 タブ構成（基本 / Skill Layer / ポリシー / 統計情報）
  (b) `settings_apply` が参照する `tool_search` / `tool_search_ranking` の公開
  (c) 設定入力欄が設定画面の単独所有であること（Step 1 右ペインと二重に持たない）
  (d) `policy.json` を表示・編集でき、検証を通った値だけを表示元と同一パスへ保存すること
  (e) 統計は `hve.toolsearch.dashboard` を単一の情報源とし、GUI で再実装しないこと
  (f) 収集済みイベントが無いとき 0 で埋めず「データ不足」を表示すること
  (g) Skill Layer は `workflow_defaults` / `required_skills` / `optional_skills` を閲覧専用表示すること
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


def _redirect_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """同梱 `policy.json` を壊さないよう、編集対象を一時コピーへ向ける。"""
    from hve.toolsearch.policy import ToolSearchPolicy

    target = tmp_path / "policy.json"
    target.write_text(
        ToolSearchPolicy.default_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path",
        staticmethod(lambda repo_root=None: target),
    )
    return target


@pytest.fixture()
def editable_section(qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    monkeypatch.setenv("HVE_TOOLSEARCH_EVENTS", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("HVE_TOOLSEARCH_USAGE", str(tmp_path / "usage.jsonl"))
    target = _redirect_policy(tmp_path, monkeypatch)
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    yield widget, target
    widget.deleteLater()


# ---------------------------------------------------------------------------
# (a) タブ構成
# ---------------------------------------------------------------------------


def test_has_five_tabs(section) -> None:
    assert section.tab_count() == 5


def test_tab_labels(section) -> None:
    assert section.tab_labels() == (
        "基本",
        "Skill Layer",
        "ポリシー",
        "統計情報",
        "コンテキスト内訳",
    )


def _open_tab(section, label: str) -> None:
    section._tabs.setCurrentIndex(section.tab_labels().index(label))


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
# (d) policy.json の表示と編集
# ---------------------------------------------------------------------------


def test_skill_layer_view_shows_manifest_summary(section) -> None:
    text = section.skill_layer_view.toPlainText()
    assert "Skill Layer" in text
    assert "workflow_defaults" in text
    assert "required_skills" in text
    assert "optional_skills" in text


def test_policy_tab_shows_the_source_path(section) -> None:
    assert "policy.json" in section.policy_path_label.text()


def test_policy_tab_shows_a_legend_for_pin_modes_and_thresholds(section) -> None:
    text = section.policy_legend_label.text()
    for token in ("always", "auto", "never", "limit", "tau"):
        assert token in text
    assert "tool-search.md" in text


def test_policy_tab_exposes_editable_scalars(editable_section) -> None:
    widget, _ = editable_section
    assert widget.policy_limit.value() == 5
    assert widget.policy_max_limit.value() == 10
    assert widget.policy_tau.value() == pytest.approx(0.4)
    for field in (widget.policy_limit, widget.policy_max_limit, widget.policy_tau):
        assert field.isEnabled()
        assert not field.isReadOnly()


def test_policy_tab_exposes_editable_field_weights(editable_section) -> None:
    widget, _ = editable_section
    assert set(widget.policy_weights) == {
        "name",
        "additional_search_text",
        "description",
        "arg_terms",
    }
    assert widget.policy_weights["name"].value() == pytest.approx(3.0)
    assert not widget.policy_weights["name"].isReadOnly()


def test_policy_tab_exposes_editable_tables(editable_section) -> None:
    widget, _ = editable_section
    assert widget.policy_pins.rows()["native:hve:*"] == "always"
    assert "native:hve:search_markdown" in widget.policy_search_text.rows()
    assert widget.policy_step_overrides.rows()["asdw-web:1.2"] == "pin_only"


def test_version_is_displayed_but_not_editable(editable_section) -> None:
    widget, _ = editable_section
    assert "1" in widget.policy_version_label.text()
    assert not hasattr(widget, "policy_version")


def test_save_writes_the_displayed_path(editable_section) -> None:
    widget, target = editable_section
    widget.policy_limit.setValue(3)
    widget.save_policy()
    assert json.loads(target.read_text(encoding="utf-8"))["limit"] == 3
    assert str(target) in widget.policy_path_label.text()


def test_save_preserves_unknown_top_level_keys(editable_section) -> None:
    widget, target = editable_section
    widget.policy_tau.setValue(0.5)
    widget.save_policy()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["_comment"]
    assert raw["tau"] == pytest.approx(0.5)


def test_table_edits_are_saved(editable_section) -> None:
    widget, target = editable_section
    widget.policy_pins.add_row("mcp:foo:*", "never")
    widget.policy_search_text.add_row("mcp:foo:bar", "分析 レポート")
    widget.policy_step_overrides.add_row("ard:1", "pin_only")
    widget.save_policy()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["pins"]["mcp:foo:*"] == "never"
    assert raw["additional_search_text"]["mcp:foo:bar"] == "分析 レポート"
    assert raw["step_overrides"]["ard:1"] == {"mode": "pin_only"}


def test_invalid_key_is_not_saved_and_reports_why(editable_section) -> None:
    widget, target = editable_section
    before = target.read_bytes()
    widget.policy_pins.add_row("execute_query", "always")
    widget.save_policy()
    assert target.read_bytes() == before
    assert "execute_query" in widget.policy_result_label.text()


def test_limit_above_max_limit_is_not_saved(editable_section) -> None:
    widget, target = editable_section
    before = target.read_bytes()
    widget.policy_limit.setValue(9)
    widget.policy_max_limit.setValue(4)
    widget.save_policy()
    assert target.read_bytes() == before
    assert "limit" in widget.policy_result_label.text()


def test_save_result_states_when_it_takes_effect(editable_section) -> None:
    widget, _ = editable_section
    widget.save_policy()
    assert "次に開始する Step 実行から" in widget.policy_result_label.text()


def test_untouched_decimals_are_not_rounded_on_save(
    qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """入力欄の桁数で既存の値を丸めない（要件: 値を丸めて保存してはならない）。"""
    from hve.gui.toolsearch_settings_section import ToolSearchSection
    from hve.toolsearch.policy import ToolSearchPolicy

    target = tmp_path / "policy.json"
    raw = json.loads(ToolSearchPolicy.default_path().read_text(encoding="utf-8"))
    raw["tau"] = 0.456
    raw["field_weights"]["name"] = 3.125
    target.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path",
        staticmethod(lambda repo_root=None: target),
    )
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.save_policy()
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved["tau"] == 0.456
        assert saved["field_weights"]["name"] == 3.125
    finally:
        widget.deleteLater()


def test_reload_discards_unsaved_edits(editable_section) -> None:
    widget, target = editable_section
    widget.policy_limit.setValue(9)
    widget.policy_pins.add_row("mcp:foo:*", "never")
    widget.reload_policy()
    assert widget.policy_limit.value() == 5
    assert "mcp:foo:*" not in widget.policy_pins.rows()
    assert json.loads(target.read_text(encoding="utf-8"))["limit"] == 5


def test_save_failure_does_not_crash_the_gui(
    editable_section, monkeypatch: pytest.MonkeyPatch
) -> None:
    widget, _ = editable_section

    def _boom(self, path) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr("hve.toolsearch.policy.ToolSearchPolicy.save", _boom)
    widget.save_policy()
    assert "read-only file system" in widget.policy_result_label.text()


def test_unreadable_policy_does_not_fabricate_defaults(
    qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    broken = tmp_path / "policy.json"
    broken.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path",
        staticmethod(lambda repo_root=None: broken),
    )
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        text = widget.policy_result_label.text()
        assert "読み込めません" in text
        assert str(broken) in text
    finally:
        widget.deleteLater()


def test_save_is_blocked_while_the_policy_is_unreadable(
    qapp, patched_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """読めなかった状態から保存すると、既存内容を空値で上書きしてしまうため禁止する。"""
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    broken = tmp_path / "policy.json"
    broken.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(
        "hve.toolsearch.policy.ToolSearchPolicy.default_path",
        staticmethod(lambda repo_root=None: broken),
    )
    widget = ToolSearchSection(repo_root=_REPO_ROOT)
    try:
        widget.save_policy()
        assert broken.read_text(encoding="utf-8") == "{ not json"
    finally:
        widget.deleteLater()


# ---------------------------------------------------------------------------
# (d-2) 編集項目の説明ヒント
# ---------------------------------------------------------------------------

_POLICY_HELP_KEYS = (
    "toolsearch.version",
    "toolsearch.limit",
    "toolsearch.max_limit",
    "toolsearch.tau",
    "toolsearch.field_weights",
    "toolsearch.pins",
    "toolsearch.additional_search_text",
    "toolsearch.step_overrides",
)


def test_every_policy_field_has_a_hint(editable_section) -> None:
    from hve.gui.help_popup import _entry_for_key

    widget, _ = editable_section
    assert set(widget.policy_help_keys()) == set(_POLICY_HELP_KEYS)
    for key in _POLICY_HELP_KEYS:
        entry = _entry_for_key(key)
        assert entry.short, key
        assert entry.guide_path == "tool-search.md", key


def test_policy_hints_come_from_help_content() -> None:
    """FR-MAINT-07: 説明文の本文を GUI セクション側へ二重に持たない。"""
    from hve.gui.help_content import toolsearch_policy_help

    source = (
        _REPO_ROOT / "hve" / "gui" / "toolsearch_settings_section.py"
    ).read_text(encoding="utf-8")
    for key in _POLICY_HELP_KEYS:
        name = key.split(".", 1)[1]
        assert toolsearch_policy_help(name).short not in source, key


def test_editor_choices_match_the_validator() -> None:
    """FR-MAINT-07: 選択肢を GUI と検証側で二重に持ったまま乖離させない。

    乖離すると GUI の入力が保存時に必ず `PolicyError` になるか、
    検証側が受け付ける値を GUI から選べなくなる。
    """
    from hve.gui import toolsearch_settings_section as section_module
    from hve.toolsearch import policy as policy_module

    assert set(section_module._WEIGHT_FIELDS) == set(policy_module._REQUIRED_WEIGHT_FIELDS)
    assert set(section_module._PIN_MODES) == set(policy_module._VALID_PIN_MODES)
    assert set(section_module._STEP_MODES) == set(policy_module._VALID_STEP_MODES)


# ---------------------------------------------------------------------------
# (g) Skill Layer / 別リポジトリでの利用
# ---------------------------------------------------------------------------


def test_extend_lists_discovered_skills_not_just_explicit_pins(section) -> None:
    """未 pin の Skill は auto 扱いなので Extend に並ぶ（以前は常に (none) だった）。"""
    text = section.skill_layer_view.toPlainText()
    extend_block = text.split("Extend / auto")[1]
    assert "(none)" not in extend_block.split("workflow_defaults")[0]


def test_missing_manifest_is_reported_instead_of_pretending_it_is_empty(
    qapp, patched_settings, tmp_path: Path
) -> None:
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    widget = ToolSearchSection(repo_root=tmp_path)
    try:
        text = widget.skill_layer_view.toPlainText()
        assert "does not exist in this repository" in text
    finally:
        widget.deleteLater()


def test_repo_local_policy_overrides_the_packaged_one(
    qapp, patched_settings, tmp_path: Path
) -> None:
    from hve.toolsearch.policy import ToolSearchPolicy
    from hve.gui.toolsearch_settings_section import ToolSearchSection

    local = tmp_path / ".toolsearch" / "policy.json"
    local.parent.mkdir(parents=True)
    local.write_text(
        (ToolSearchPolicy.default_path()).read_text(encoding="utf-8"), encoding="utf-8"
    )
    widget = ToolSearchSection(repo_root=tmp_path)
    try:
        assert str(local) in widget.policy_path_label.text()
    finally:
        widget.deleteLater()


def test_packaged_policy_is_used_when_the_repo_has_none(tmp_path: Path) -> None:
    from hve.toolsearch.policy import ToolSearchPolicy

    assert ToolSearchPolicy.default_path(tmp_path) == ToolSearchPolicy.default_path()


# ---------------------------------------------------------------------------
# (e)(f) 統計
# ---------------------------------------------------------------------------


def test_stats_view_is_read_only(section) -> None:
    assert section.stats_view.isReadOnly()


def test_stats_are_not_loaded_until_the_tab_is_opened(section) -> None:
    """イベントログは無制限に伸びるので、設定画面を開いただけでは読まない。"""
    assert section.stats_view.toPlainText() == ""


def test_opening_the_stats_tab_loads_them(section) -> None:
    _open_tab(section, "統計情報")
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
    for forbidden in ("Counter(", "def _percentile", "def _aggregate", "def _format_context"):
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


# ---------------------------------------------------------------------------
# FR-GUI-07 改訂: 実挙動と食い違わない説明 / 未充足の収集条件 / 凡例
# ---------------------------------------------------------------------------


def test_basic_tab_states_that_deferral_does_not_fire(section) -> None:
    """遅延ロードが発火しない実測を、実測日と CLI 版つきで明示する。"""
    text = section.basic_note.text()
    assert "1.0.79" in text
    assert "発火" in text


def test_basic_tab_warns_hve_ranking_increases_context(section) -> None:
    """`hve` ランキングがコンテキストを増やす実測を明示する。"""
    text = section.basic_note.text()
    assert "12,160" in text


def _select_ranking(section, value: str) -> None:
    for index in range(section.tool_search_ranking.count()):
        if section.tool_search_ranking.itemData(index) == value:
            section.tool_search_ranking.setCurrentIndex(index)
            return
    raise AssertionError(f"ranking {value!r} not offered")


def test_empty_stats_reports_disabled_tool_search_as_unmet(section) -> None:
    section.tool_search.setChecked(False)
    section.reload_stats()
    text = section.stats_diagnosis_label.text()
    assert "遅延ロード" in text


def test_empty_stats_reports_sdk_ranking_as_unmet(section) -> None:
    section.tool_search.setChecked(True)
    _select_ranking(section, "sdk")
    section.reload_stats()
    text = section.stats_diagnosis_label.text()
    assert "ランキング" in text


def test_empty_stats_does_not_assert_an_unobserved_cause(section) -> None:
    """設定条件が揃っているときは、観測していない原因を断定しない。"""
    section.tool_search.setChecked(True)
    _select_ranking(section, "hve")
    section.reload_stats()
    text = section.stats_diagnosis_label.text()
    assert "0 件" in text
    assert "確認できません" in text


def test_stats_diagnosis_is_silent_when_events_exist(section, tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"kind": "toolsearch.query", "ts": "2026-08-04T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    section.reload_stats()
    assert section.stats_diagnosis_label.text() == ""


def test_policy_tab_shows_a_legend_for_pin_modes_and_thresholds(section) -> None:
    text = section.policy_legend_label.text()
    for term in ("always", "auto", "never", "limit", "tau"):
        assert term in text


def test_skill_layer_tab_states_that_extend_depends_on_the_cli(section) -> None:
    text = section.skill_layer_note.text()
    assert "CLI" in text


# ---------------------------------------------------------------------------
# FR-GUI-07 / FR-TS-11: コンテキスト内訳の実測
# ---------------------------------------------------------------------------


def test_context_tab_does_not_measure_until_requested(section) -> None:
    """タブを開いただけでセッションを張らない。"""
    _open_tab(section, "コンテキスト内訳")
    assert section.context_view.toPlainText() == ""


def test_context_tab_renders_the_cli_payload_without_reaggregating(section) -> None:
    payload = "Step 実行セッションのコンテキスト内訳（実測）\n  azure  68  15,022"
    section.apply_context_result(0, payload, "")
    assert section.context_view.toPlainText() == payload


def test_context_tab_reports_failure_without_fabricating(section) -> None:
    section.apply_context_result(1, "", "❌ Copilot CLI を起動できません: RuntimeError: boom")
    assert "起動できません" in section.context_result_label.text()
    assert section.context_view.toPlainText() == ""


def test_context_measurement_uses_the_cli(section, qapp) -> None:
    """ボタンからの実経路（ワーカー経由）で CLI 出力をそのまま描画する。"""
    calls: list[int] = []

    def _fake_run():
        calls.append(1)
        return 0, "measured", ""

    section._run_context_command = _fake_run  # type: ignore[method-assign]
    section.measure_context()
    section.wait_for_context_measurement(5000)
    qapp.processEvents()
    assert calls == [1]
    assert section.context_view.toPlainText() == "measured"


def test_opening_the_context_tab_does_not_load_stats(section) -> None:
    """統計の読み込みはタブの位置（末尾かどうか）ではなく統計タブで判定する。"""
    _open_tab(section, "コンテキスト内訳")
    assert section.stats_view.toPlainText() == ""
