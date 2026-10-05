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
            "[options]\nmcp_config = /tmp/x.json\ncreate_issues = true\n",
        )
        merged = settings_store.load()
        # ロード結果には廃止キーが残らない
        assert "mcp_config" not in merged["options"]
        # 既存の正規キーは保持される
        assert merged["options"]["create_issues"] is True
        # 物理ファイルからも削除されていること
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "mcp_config" not in on_disk
        assert "create_issues" in on_disk

    @pytest.mark.parametrize(
        "key,value",
        (
            ("workiq_tenant_id", "some-tenant"),
            ("workiq_request_timeout", "300"),
            ("workiq_prompt_review", "legacy review"),
        ),
    )
    def test_removes_obsolete_workiq_runtime_key_from_options(
        self,
        tmp_settings: Path,
        key: str,
        value: str,
    ) -> None:
        _write(
            tmp_settings,
            f"[options]\n{key} = {value}\n",
        )
        merged = settings_store.load()
        assert key not in merged["options"]
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert key not in on_disk

    def test_removes_all_obsolete_workiq_keys_in_one_pass(self, tmp_settings: Path) -> None:
        _write(
            tmp_settings,
            "[options]\n"
            "mcp_config = /tmp/x.json\n"
            "workiq_tenant_id = t1\n"
            "workiq_request_timeout = 300\n"
            "workiq_prompt_review = review\n"
            "repo = owner/r\n",
        )
        merged = settings_store.load()
        for key in (
            "mcp_config",
            "workiq_tenant_id",
            "workiq_request_timeout",
            "workiq_prompt_review",
        ):
            assert key not in merged["options"]
        assert merged["options"]["repo"] == "owner/r"
        on_disk = tmp_settings.read_text(encoding="utf-8")
        for key in (
            "mcp_config",
            "workiq_tenant_id",
            "workiq_request_timeout",
            "workiq_prompt_review",
        ):
            assert key not in on_disk
        assert "repo" in on_disk

    def test_save_does_not_reintroduce_obsolete_workiq_keys(
        self,
        tmp_settings: Path,
    ) -> None:
        settings_store.save(
            {
                "options": {
                    "repo": "owner/repo",
                    "workiq_tenant_id": "tenant",
                    "workiq_request_timeout": 300,
                    "workiq_prompt_review": "review",
                }
            }
        )

        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "repo = owner/repo" in on_disk
        assert "workiq_tenant_id" not in on_disk
        assert "workiq_request_timeout" not in on_disk
        assert "workiq_prompt_review" not in on_disk

    def test_removes_data_verify_aci_image_from_options(
        self, tmp_settings: Path
    ) -> None:
        """FR-GUI-03: 入力欄を廃止した key は `_OBSOLETE_KEYS` で除去する。

        検証イメージは導出値であり Workflow パラメータではないため
        （FR-WF-ASDW-02）、保存値が残ると UI から修正できない値が居座る。
        """
        _write(
            tmp_settings,
            "[options]\ndata_verify_aci_image = example.azurecr.io/verify:v1\n"
            "resource_group = rg-dev\n",
        )

        merged = settings_store.load()

        assert "data_verify_aci_image" not in merged["options"]
        assert merged["options"]["resource_group"] == "rg-dev"
        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "data_verify_aci_image" not in on_disk
        assert "resource_group" in on_disk


class TestSelfImproveSettingsRemoval:
    def test_removed_self_improve_keys_are_dropped_from_settings(
        self,
        tmp_settings: Path,
    ) -> None:
        _write(
            tmp_settings,
            "[options]\n"
            "self_improve = on\n"
            "no_self_improve = true\n"
            "self_improve_max_iterations = 7\n"
            "self_improve_target_scope = hve\n"
            "self_improve_goal = x\n"
            "repo = owner/r\n",
        )

        merged = settings_store.load()

        on_disk = tmp_settings.read_text(encoding="utf-8")
        assert "self_improve" not in on_disk
        assert "no_self_improve" not in on_disk
        assert not [key for key in merged["options"] if "self_improve" in key]
        assert merged["options"]["repo"] == "owner/r"

    def test_missing_settings_has_no_self_improve_keys(self, tmp_settings: Path) -> None:
        assert not tmp_settings.exists()
        merged = settings_store.load()
        assert not [key for key in merged["options"] if "self_improve" in key]

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


class TestExplorerRootsMigration:
    def test_migrates_legacy_original_docs_root(self, tmp_settings: Path) -> None:
        _write(
            tmp_settings,
            "[options]\n"
            "explorer_roots = docs;docs-generated;knowledge;original-docs;qa;users-guide\n",
        )

        merged = settings_store.load()

        expected = "docs;docs-generated;knowledge;docs-original;qa;users-guide"
        assert merged["options"]["explorer_roots"] == expected
        assert f"explorer_roots = {expected}" in tmp_settings.read_text(encoding="utf-8")

    def test_preserves_nonlegacy_original_docs_subpath(self, tmp_settings: Path) -> None:
        original = "[options]\nexplorer_roots = docs;custom/original-docs;docs-original\n"
        _write(tmp_settings, original)
        before_mtime = tmp_settings.stat().st_mtime_ns

        merged = settings_store.load()

        assert merged["options"]["explorer_roots"] == "docs;custom/original-docs;docs-original"
        assert tmp_settings.stat().st_mtime_ns == before_mtime
