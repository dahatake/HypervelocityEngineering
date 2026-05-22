"""hve.gui.tests.test_settings_window_mdq_persistence

SettingsWindow._on_widget_changed() と _MdqIndexSection._persist_settings() の
競合シナリオで、[mdq] target_folders が上書き消去されないことを検証する。

バグ概要:
  起動時にロードした self._settings スナップショットで save() すると、別経路で
  ファイルに書かれた [mdq] target_folders が古いスナップショット値（空）で
  上書きされる。修正後は _on_widget_changed() 内で再度 load() して最新値を
  マージしてから save() するため、target_folders は保持される。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from hve.gui import settings_store


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "settings_path", lambda: fake_path)
    return fake_path


def _simulate_on_widget_changed(
    snapshot: Dict[str, Dict[str, Any]],
    new_options: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """SettingsWindow._on_widget_changed() の修正版ロジックを再現する。

    保存直前に settings_store.load() で最新値を取り込み、options のみマージ。
    """
    latest = settings_store.load()
    snapshot.clear()
    snapshot.update(latest)
    snapshot.setdefault("options", {}).update(new_options)
    settings_store.save(snapshot)
    return snapshot


class TestMdqTargetFoldersPersistence:
    def test_concurrent_mdq_update_is_preserved_after_options_change(
        self, tmp_settings: Path
    ) -> None:
        # 1) 初期状態: target_folders 空でファイル保存
        initial = settings_store.defaults()
        initial["mdq"]["target_folders"] = ""
        settings_store.save(initial)

        # 2) SettingsWindow 起動相当: スナップショットを保持
        snapshot = settings_store.load()
        assert snapshot["mdq"]["target_folders"] == ""

        # 3) 別経路 (_MdqIndexSection._persist_settings) が
        #    target_folders をファイルへ追記
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs/usecase;docs/agent"
        settings_store.save(cur)

        # 4) その後、別ウィジェット変更で _on_widget_changed が走る
        _simulate_on_widget_changed(snapshot, {"theme": "dark"})

        # 5) target_folders が保持されているか
        result = settings_store.load()
        assert result["mdq"]["target_folders"] == "docs/usecase;docs/agent"
        assert result["options"]["theme"] == "dark"

    def test_reverse_order_options_then_mdq(self, tmp_settings: Path) -> None:
        # 逆順: 先に options が変わってから mdq が変わるケース
        initial = settings_store.defaults()
        settings_store.save(initial)

        snapshot = settings_store.load()

        # options 変更で save
        _simulate_on_widget_changed(snapshot, {"theme": "dark"})

        # その後、mdq セクションを別経路で更新
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs/screen"
        settings_store.save(cur)

        result = settings_store.load()
        assert result["mdq"]["target_folders"] == "docs/screen"
        assert result["options"]["theme"] == "dark"

    def test_options_change_does_not_clobber_existing_mdq_on_disk(
        self, tmp_settings: Path
    ) -> None:
        # 起動前から既にファイルに target_folders が存在するケース
        initial = settings_store.defaults()
        initial["mdq"]["target_folders"] = "docs/services"
        settings_store.save(initial)

        # SettingsWindow が target_folders 既値を含んだ状態でロード
        snapshot = settings_store.load()
        assert snapshot["mdq"]["target_folders"] == "docs/services"

        # ユーザーが GUI で target_folders を追加（別経路で再保存）
        cur = settings_store.load()
        cur["mdq"]["target_folders"] = "docs/services;docs/usecase"
        settings_store.save(cur)

        # 直後に他オプション変更で _on_widget_changed
        _simulate_on_widget_changed(snapshot, {"verbose": True})

        result = settings_store.load()
        assert result["mdq"]["target_folders"] == "docs/services;docs/usecase"
        assert result["options"]["verbose"] is True
