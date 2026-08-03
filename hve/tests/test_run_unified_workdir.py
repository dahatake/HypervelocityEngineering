"""CLI/GUI 起動時の run-id 採番 + HVE_WORK_ROOT 設定の統合テスト。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hve import split_fork
from hve.__main__ import _ensure_run_workdir_env
from hve.gui.session_workdir import GuiSessionWorkdir


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("HVE_WORK_ROOT", raising=False)
    monkeypatch.delenv("HVE_RUN_ID", raising=False)
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    split_fork._reset_run_id_cache()
    yield
    split_fork._reset_run_id_cache()


class TestCLIEntrypoint:
    """`_ensure_run_workdir_env` の CLI 起動時挙動。"""

    def test_sets_work_root_and_run_id_when_unset(self, monkeypatch):
        monkeypatch.setenv("HVE_RUN_ID", "test-run-1")
        _ensure_run_workdir_env()
        assert os.environ.get("HVE_RUN_ID") == "test-run-1"
        work_root = Path(os.environ["HVE_WORK_ROOT"])
        assert work_root.parts[-3:] == ("work", "run", "test-run-1")
        assert work_root.is_dir()

    def test_respects_preset_work_root(self, monkeypatch, tmp_path):
        custom = tmp_path / "custom-root"
        custom.mkdir()
        monkeypatch.setenv("HVE_WORK_ROOT", str(custom))
        _ensure_run_workdir_env()
        # 既設定は変更されない
        assert Path(os.environ["HVE_WORK_ROOT"]) == custom

    def test_generates_new_run_id_when_unset(self, monkeypatch):
        _ensure_run_workdir_env()
        rid = os.environ.get("HVE_RUN_ID")
        assert rid is not None
        # generate_run_id 形式: YYYYMMDDTHHMMSS-xxxxxx (22 文字)
        assert len(rid) == 22


class TestGUIPropagation:
    """GuiSessionWorkdir の env_overrides が HVE_RUN_ID を含むこと。"""

    def test_env_overrides_propagates_run_id(self, tmp_path):
        s = GuiSessionWorkdir.create(tmp_path)
        env = s.env_overrides()
        assert env["HVE_RUN_ID"] == s.session_run_id
        assert env["HVE_WORK_ROOT"] == str(s.work_root)

    def test_session_id_has_no_gui_prefix(self, tmp_path):
        s = GuiSessionWorkdir.create(tmp_path)
        assert not s.session_run_id.startswith("gui-")

    def test_work_root_under_run_subdir(self, tmp_path):
        s = GuiSessionWorkdir.create(tmp_path)
        assert s.work_root.parts[-3:-1] == ("work", "run")
        assert s.work_root.is_dir()


class TestEndToEndChain:
    """GUI 起動 → CLI 子プロセス継承時に run-id が共有されることを確認。"""

    def test_cli_inherits_gui_work_root(self, tmp_path, monkeypatch):
        gui = GuiSessionWorkdir.create(tmp_path)
        # GUI が子プロセス env を設定する想定
        for k, v in gui.env_overrides().items():
            monkeypatch.setenv(k, v)
        # CLI ハンドラ呼び出し
        _ensure_run_workdir_env()
        # GUI 設定値が尊重される
        assert os.environ["HVE_WORK_ROOT"] == str(gui.work_root)
        assert os.environ["HVE_RUN_ID"] == gui.session_run_id
