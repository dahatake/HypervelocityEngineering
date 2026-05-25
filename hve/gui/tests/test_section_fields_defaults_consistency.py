"""hve.gui.tests.test_section_fields_defaults_consistency

設定ウィジェット ↔ 永続化の整合性回帰防止テスト。

検証内容:
  1. _SECTION_FIELDS の全 opt_key が defaults()["options"] (または "mdq") に存在すること
     → 不在キーは _coerce(default=None) フォールバックで型情報が失われ、
       bool 値の round-trip が壊れる（"false" 文字列 → bool("false")=True 反転）。
  2. _SECTION_FIELDS の opt_key が _OBSOLETE_KEYS と排他であること
     → UI に残置しつつ obsolete 指定すると保存しても次回ロードで削除される。
  3. C4 _C4WorkIQ の bool 値 (workiq, workiq_draft) の round-trip
     save → load → apply で False が False を維持すること（B2 root-cause 回帰防止）。
  4. C4 _C4WorkIQ.workiq_prompt_review の文字列 round-trip
     （B1 回帰防止: _SECTION_FIELDS["C4"] への登録漏れ検出）。
  5. C5 enable_auto_merge の bool round-trip（横展開バグ回帰防止）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui import settings_apply, settings_store


# ---------------------------------------------------------------------------
# 1. _SECTION_FIELDS × defaults() 整合性
# ---------------------------------------------------------------------------
def test_section_fields_keys_exist_in_defaults() -> None:
    """全 _SECTION_FIELDS の opt_key が defaults() の "options" または "mdq" に存在する。"""
    defaults = settings_store.defaults()
    known_keys = set(defaults["options"].keys()) | set(defaults["mdq"].keys())
    missing: list[tuple[str, str]] = []
    for sec_key, fields in settings_apply._SECTION_FIELDS.items():
        for opt_key in fields.keys():
            if opt_key not in known_keys:
                missing.append((sec_key, opt_key))
    assert not missing, (
        "以下の _SECTION_FIELDS キーが defaults() に未登録です。"
        " _coerce(default=None) フォールバックにより型情報が失われ、"
        " bool 値が文字列で round-trip して反転する原因になります:\n"
        + "\n".join(f"  - [{sec}] {key}" for sec, key in missing)
    )


def test_section_fields_keys_not_obsolete() -> None:
    """_SECTION_FIELDS のキーは _OBSOLETE_KEYS と排他であること。"""
    obsolete = settings_store._OBSOLETE_KEYS.get("options", set())
    conflicts: list[tuple[str, str]] = []
    for sec_key, fields in settings_apply._SECTION_FIELDS.items():
        for opt_key in fields.keys():
            if opt_key in obsolete:
                conflicts.append((sec_key, opt_key))
    assert not conflicts, (
        "_SECTION_FIELDS と _OBSOLETE_KEYS が重複しています "
        "（保存しても次回ロードで削除される矛盾状態）:\n"
        + "\n".join(f"  - [{sec}] {key}" for sec, key in conflicts)
    )


# ---------------------------------------------------------------------------
# 2. Bool 値 round-trip テスト（QApplication 必須）
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake_path)
    return fake_path


@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _save_then_reload_via_widget(
    section_key: str, widget_factory, options_to_save: dict
) -> dict:
    """save -> load -> apply_to_widgets -> collect_from_widgets の往復を実行。

    SettingsWindow._on_widget_changed の保存パス (collect_from_widgets +
    settings_store.save) と質的に同値。テストではイベントループを
    介さず settings_store.save を直接呼ぶことで離散性を確保している。

    戻り値: collect 後の options dict（該当セクション分のみ）
    """
    # 1. 保存
    snapshot = settings_store.load()
    snapshot.setdefault("options", {}).update(options_to_save)
    settings_store.save(snapshot)

    # 2. 再ロード + ウィジェットへ反映
    reloaded = settings_store.load()
    widget = widget_factory()
    sections = {section_key: widget}
    settings_apply.apply_to_widgets(sections, reloaded)

    # 3. ウィジェットから値を読み取り
    collected = settings_apply.collect_from_widgets(sections)
    return collected


def test_c4_workiq_bool_roundtrip_false(tmp_settings: Path, qapp) -> None:
    """workiq=False, workiq_draft=False が save→load で False を維持する。

    B2 root-cause 回帰: defaults 未登録時に _coerce が "false" 文字列を返し
    bool("false")=True で反転していた。
    """
    from hve.gui.page_options import _C4WorkIQ

    collected = _save_then_reload_via_widget(
        "C4",
        _C4WorkIQ,
        {"workiq": False, "workiq_draft": False},
    )
    assert collected["workiq"] is False, (
        f"workiq=False が round-trip 後に {collected['workiq']!r} に反転"
    )
    assert collected["workiq_draft"] is False, (
        f"workiq_draft=False が round-trip 後に {collected['workiq_draft']!r} に反転"
    )


def test_c4_workiq_prompt_review_roundtrip(tmp_settings: Path, qapp) -> None:
    """workiq_prompt_review の文字列値が save→load で保持される。

    B1 回帰防止: _SECTION_FIELDS["C4"] への登録漏れ検出。
    """
    from hve.gui.page_options import _C4WorkIQ

    expected = "カスタムレビュー用プロンプト本文"
    collected = _save_then_reload_via_widget(
        "C4",
        _C4WorkIQ,
        {"workiq_prompt_review": expected},
    )
    assert collected.get("workiq_prompt_review") == expected, (
        f"workiq_prompt_review が保存→ロード後に欠落: {collected.get('workiq_prompt_review')!r}"
    )


def test_c5_enable_auto_merge_bool_roundtrip_false(tmp_settings: Path, qapp) -> None:
    """enable_auto_merge=False が save→load で False を維持する（横展開バグ回帰防止）。"""
    from hve.gui.page_options import _C5IssuePR

    collected = _save_then_reload_via_widget(
        "C5",
        _C5IssuePR,
        {"enable_auto_merge": False},
    )
    assert collected["enable_auto_merge"] is False, (
        f"enable_auto_merge=False が round-trip 後に {collected['enable_auto_merge']!r} に反転"
    )


# ---------------------------------------------------------------------------
# 3. _FilePickerWidget round-trip テスト（敵対的レビュー No.1 回帰防止）
# ---------------------------------------------------------------------------
# _FilePickerWidget は QWidget サブクラスで text()/setText() を duck-type 公開する。
# 旧 _get/_set は isinstance(QLineEdit) で判定しており FilePicker をスルーしていた
# ため、以下のキーが保存・復元されない隠れバグがあった。
#   - workiq_draft_output_dir (C4)
#   - target_files / custom_source_dir (C11)
#   - target_scope (C12)
#   - target_dirs (C13)
#   - target_business (C14)

@pytest.mark.parametrize(
    "section_key,widget_factory_name,option_key",
    [
        ("C4", "_C4WorkIQ", "workiq_draft_output_dir"),
        ("C11", "_C11AKM", "target_files"),
        ("C11", "_C11AKM", "custom_source_dir"),
        ("C12", "_C12AQOD", "target_scope"),
        ("C13", "_C13ADOC", "target_dirs"),
        ("C14", "_C14ARD", "target_business"),
    ],
)
def test_filepicker_widgets_roundtrip(
    tmp_settings: Path, qapp, section_key: str, widget_factory_name: str, option_key: str
) -> None:
    """_FilePickerWidget ベースの全キーが save→load で文字列値を保持する。

    敵対的レビュー No.1 (Critical) 回帰防止: isinstance(QLineEdit) で誤判定し
    値が None で保存されていた。
    """
    from hve.gui import page_options

    widget_factory = getattr(page_options, widget_factory_name)
    expected = f"some/test/path/{option_key}"
    collected = _save_then_reload_via_widget(
        section_key,
        widget_factory,
        {option_key: expected},
    )
    assert collected.get(option_key) == expected, (
        f"{option_key} (FilePicker) が round-trip で欠落: "
        f"{collected.get(option_key)!r} (expected {expected!r})"
    )
