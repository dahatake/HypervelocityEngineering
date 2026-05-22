"""Issue-gui-session-workdir-isolation T2/T3 — GuiSessionWorkdir のユニットテスト。"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from hve.gui.session_workdir import (
    ARCHIVE_DIRNAME,
    GUI_RUNS_DIRNAME,
    SESSION_ID_PREFIX,
    GuiSessionWorkdir,
)


class TestCreate:
    def test_creates_unique_work_root(self, tmp_path: Path):
        s1 = GuiSessionWorkdir.create(tmp_path)
        s2 = GuiSessionWorkdir.create(tmp_path)
        assert s1.session_run_id != s2.session_run_id
        assert s1.work_root.is_dir()
        assert s2.work_root.is_dir()
        assert s1.work_root != s2.work_root

    def test_session_id_has_gui_prefix(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path)
        assert s.session_run_id.startswith(SESSION_ID_PREFIX)

    def test_work_root_layout(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path)
        # work/gui-runs/<id>/
        assert s.work_root.parent.name == GUI_RUNS_DIRNAME
        assert s.work_root.parent.parent.name == "work"

    def test_invalid_policy_falls_back_to_keep(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path, cleanup_policy="invalid")
        assert s.cleanup_policy == "keep"

    def test_detects_existing_env_override(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HVE_WORK_ROOT", "/some/other/path")
        s = GuiSessionWorkdir.create(tmp_path)
        assert s.had_env_override is True


class TestEnvOverrides:
    def test_env_overrides_has_two_keys(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path)
        env = s.env_overrides()
        assert env["HVE_WORK_ROOT"] == str(s.work_root)
        assert env["HVE_GUI_SESSION_ID"] == s.session_run_id
        assert set(env.keys()) == {"HVE_WORK_ROOT", "HVE_GUI_SESSION_ID"}

    def test_apply_to_env_merges(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path)
        base = {"FOO": "bar"}
        merged = s.apply_to_env(base)
        assert merged["FOO"] == "bar"
        assert merged["HVE_WORK_ROOT"] == str(s.work_root)
        # 元 dict は不変
        assert "HVE_WORK_ROOT" not in base


class TestCleanup:
    def _make_file(self, s: GuiSessionWorkdir, rel: str = "sample.txt") -> Path:
        target = s.work_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hello", encoding="utf-8")
        return target

    def test_keep_no_op(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path, cleanup_policy="keep")
        self._make_file(s)
        s.cleanup()
        assert s.work_root.is_dir()

    def test_purge_removes(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path, cleanup_policy="purge")
        self._make_file(s)
        s.cleanup()
        assert not s.work_root.exists()

    def test_archive_zips_and_removes(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path, cleanup_policy="archive")
        self._make_file(s, "a/b/c.txt")
        s.cleanup()
        zip_path = s.work_root.parent / ARCHIVE_DIRNAME / f"{s.session_run_id}.zip"
        assert zip_path.is_file()
        assert not s.work_root.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            # zip 仕様準拠で必ず forward slash 区切りで格納されること（Adv. Review #3）
            assert "a/b/c.txt" in names

    def test_cleanup_missing_root_is_safe(self, tmp_path: Path):
        s = GuiSessionWorkdir.create(tmp_path, cleanup_policy="purge")
        s.cleanup()  # 削除
        s.cleanup()  # 2 回目: 例外を出さない
