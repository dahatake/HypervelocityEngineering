"""test_options_page_required_input_persistence.py — FR-GUI-06（永続化）のテスト。

Step 1 右ペインで入力した必須入力キーの値は設定ストアの `[options]` へ永続化し、
次回起動時に復元しなければならない。

検証項目:
  1. 全必須入力キーが `_SECTION_FIELDS` のいずれかのセクションに保存先を持つこと
  2. 右ペインの入力欄への入力が設定ストアへ保存されること
  3. 右ペイン経由の保存が他セクション（`[mdq]` / `[cq]`）を破壊しないこと
  4. 保存済みの値が起動時経路（`MainWindow` の設定反映）で右ペインへ復元されること

根拠: hve-dev/requirement-definition.md §6.4 FR-GUI-06 / FR-GUI-03
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui import settings_apply, settings_store


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake_path)
    return fake_path


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _required_input_values(page) -> Dict[str, str]:
    """必須入力キーごとに一意なテスト値を割り当てる。"""
    return {key: f"value-{key}" for key in page._banner_input_widgets()}


def test_every_required_input_key_has_a_persist_section(tmp_settings: Path, qapp) -> None:
    """必須入力キーはいずれかのセクション表に登録され、保存先を持つこと。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        missing: List[str] = [
            key
            for key in page._banner_input_widgets()
            if not any(
                key in fields for fields in settings_apply._SECTION_FIELDS.values()
            )
        ]
    finally:
        page.deleteLater()
    assert missing == [], f"保存先セクションが無い必須入力キー: {missing}"


def test_editing_required_input_saves_to_store(tmp_settings: Path, qapp) -> None:
    """右ペインの必須入力欄への入力が設定ストアへ保存されること。"""
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        expected = _required_input_values(page)
        for key, widget in page._banner_input_widgets().items():
            widget.setText(expected[key])
        stored = settings_store.load().get("options", {})
        unsaved = {
            key: stored.get(key) for key, value in expected.items() if stored.get(key) != value
        }
    finally:
        page.deleteLater()
    assert unsaved == {}, f"設定ストアへ保存されなかった必須入力キー: {unsaved}"


def test_saving_required_input_preserves_other_sections(
    tmp_settings: Path, qapp
) -> None:
    """右ペイン経由の保存が `[mdq]` / `[cq]` セクションを消去しないこと。"""
    from hve.gui.page_options import OptionsPage

    snapshot = settings_store.load()
    snapshot.setdefault("mdq", {})["target_folders"] = "docs"
    snapshot.setdefault("cq", {})["profile"] = "probe-profile"
    settings_store.save(snapshot)

    page = OptionsPage()
    try:
        page._banner_input_widgets()["resource_group"].setText("rg-probe")
        reloaded = settings_store.load()
    finally:
        page.deleteLater()
    assert reloaded.get("options", {}).get("resource_group") == "rg-probe"
    assert reloaded.get("mdq", {}).get("target_folders") == "docs"
    assert reloaded.get("cq", {}).get("profile") == "probe-profile"


def test_stored_required_input_restores_into_options_page(
    tmp_settings: Path, tmp_path: Path, qapp
) -> None:
    """保存済みの必須入力値が起動時経路で右ペインへ復元されること。"""
    from hve.gui.main_window import MainWindow
    from hve.gui.page_options import OptionsPage

    probe = OptionsPage()
    try:
        expected = _required_input_values(probe)
    finally:
        probe.deleteLater()

    snapshot = settings_store.load()
    snapshot.setdefault("options", {}).update(expected)
    settings_store.save(snapshot)

    window = MainWindow(repo_root=tmp_path)
    try:
        widgets = window._page_options._banner_input_widgets()
        not_restored = {
            key: widgets[key].text()
            for key, value in expected.items()
            if widgets[key].text() != value
        }
    finally:
        window.deleteLater()
    assert not_restored == {}, f"起動時に復元されなかった必須入力キー: {not_restored}"
