"""hve.gui.tests.test_settings_store_migration — Q9=b 廃止キーマイグレーション。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hve.gui import settings_store


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """テスト用に ``settings_store.settings_path()`` を tmp_path に差し替える。"""
    fake_path = tmp_path / ".settings.txt"

    def _patched() -> Path:
        return fake_path

    monkeypatch.setattr(settings_store, "settings_path", _patched)
    return fake_path


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


class TestObsoleteKeyMigration:
    def test_removes_mcp_config_from_options(self, tmp_settings: Path) -> None:
        _write(
            tmp_settings,
            "[options]\nmcp_config = /tmp/x.json\nverbose = true\n",
        )
        merged = settings_store.load()
        # ロード結果には廃止キーが残らない
        assert "mcp_config" not in merged["options"]
        # 既存の正規キーは保持される
        assert merged["options"]["verbose"] is True
        # 物理ファイルからも削除されていること
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "mcp_config" not in on_disk
        assert "verbose" in on_disk

    def test_removes_workiq_tenant_id_from_options(self, tmp_settings: Path) -> None:
        _write(
            tmp_settings,
            "[options]\nworkiq_tenant_id = some-tenant\n",
        )
        merged = settings_store.load()
        assert "workiq_tenant_id" not in merged["options"]
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "workiq_tenant_id" not in on_disk

    def test_removes_both_keys_in_one_pass(self, tmp_settings: Path) -> None:
        _write(
            tmp_settings,
            "[options]\nmcp_config = /tmp/x.json\nworkiq_tenant_id = t1\nrepo = owner/r\n",
        )
        merged = settings_store.load()
        assert "mcp_config" not in merged["options"]
        assert "workiq_tenant_id" not in merged["options"]
        assert merged["options"]["repo"] == "owner/r"
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "mcp_config" not in on_disk
        assert "workiq_tenant_id" not in on_disk
        assert "repo" in on_disk

    def test_no_migration_when_keys_absent(self, tmp_settings: Path) -> None:
        original = "[options]\nrepo = owner/r\n"
        _write(tmp_settings, original)
        before_mtime = tmp_settings.stat().st_mtime_ns
        settings_store.load()
        after_mtime = tmp_settings.stat().st_mtime_ns
        # マイグレーション対象キーが無いときはファイル書き換えが発生しない
        assert before_mtime == after_mtime

    def test_no_settings_file_no_error(self, tmp_settings: Path) -> None:
        # tmp_settings は未作成
        assert not tmp_settings.exists()
        merged = settings_store.load()
        # defaults() がそのまま返り、廃止キーは含まれない
        assert "mcp_config" not in merged["options"]
        assert "workiq_tenant_id" not in merged["options"]
