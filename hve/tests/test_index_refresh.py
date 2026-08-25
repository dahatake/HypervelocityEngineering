"""FR-CLI-77: 起動時の索引差分更新（対象列挙・差分更新・バックグラウンド制御）。

RED 先行。`hve/index_refresh.py` は本テストの後に追加する。
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def _isolated_module_state(monkeypatch):
    """プロセス内 1 回だけ起動する状態をテストごとに戻す。"""
    from hve import index_refresh

    monkeypatch.delenv(index_refresh.ENV_FLAG, raising=False)
    index_refresh._thread = None
    index_refresh._done.set()
    yield
    index_refresh._thread = None
    index_refresh._done.set()


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _write_cq_config(repo: Path, *profiles: str) -> None:
    body = ['[index]', 'max_file_bytes = 1048576', '']
    for name in profiles:
        body += [f'[profiles.{name}]', 'roots = ["src"]', '']
    (repo / "cq.toml").write_text("\n".join(body), encoding="utf-8")


class TestEnumerateTargets:
    def test_mdq_targets_come_from_existing_per_strategy_dbs(self, tmp_path: Path):
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index-ja-jp-heading.sqlite")
        _touch(tmp_path / ".mdq" / "index-en-us-fixed_window.sqlite")

        found = {(t.engine, t.label) for t in index_refresh.enumerate_targets(tmp_path)}

        assert found == {("mdq", "ja-jp/heading"), ("mdq", "en-us/fixed_window")}

    def test_longest_strategy_suffix_wins(self, tmp_path: Path):
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index-ja-jp-heading_recursive.sqlite")

        labels = [t.label for t in index_refresh.enumerate_targets(tmp_path)]

        assert labels == ["ja-jp/heading_recursive"]

    def test_legacy_single_db_is_not_a_target(self, tmp_path: Path):
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index.sqlite")

        assert index_refresh.enumerate_targets(tmp_path) == []

    def test_graphrag_working_directory_is_not_a_target(self, tmp_path: Path):
        from hve import index_refresh

        (tmp_path / ".mdq" / "graphrag-ja-jp").mkdir(parents=True)

        assert index_refresh.enumerate_targets(tmp_path) == []

    def test_cq_target_requires_declaration_and_existing_db(self, tmp_path: Path):
        from hve import index_refresh

        _write_cq_config(tmp_path, "hve", "app")
        _touch(tmp_path / ".cq" / "index-hve.sqlite")

        found = {(t.engine, t.label) for t in index_refresh.enumerate_targets(tmp_path)}

        assert found == {("cq", "hve")}

    def test_undeclared_cq_db_is_not_a_target(self, tmp_path: Path):
        from hve import index_refresh

        _write_cq_config(tmp_path, "hve")
        _touch(tmp_path / ".cq" / "index-other.sqlite")

        assert index_refresh.enumerate_targets(tmp_path) == []

    def test_missing_cq_config_yields_no_cq_target(self, tmp_path: Path):
        from hve import index_refresh

        _touch(tmp_path / ".cq" / "index-hve.sqlite")

        assert index_refresh.enumerate_targets(tmp_path) == []


class TestRefreshAll:
    def _stub_builders(self, monkeypatch, calls: list):
        import cq.indexer
        import mdq.indexer
        import mdq.store

        monkeypatch.setattr(
            mdq.store, "open_store",
            lambda *a, **k: _FakeConn(), raising=True,
        )
        monkeypatch.setattr(
            mdq.indexer, "build_index",
            lambda *a, **k: calls.append(("mdq", a, k)) or {}, raising=True,
        )
        monkeypatch.setattr(
            cq.indexer, "build_index",
            lambda *a, **k: calls.append(("cq", a, k)) or _FakeReport(), raising=True,
        )

    def test_refresh_is_incremental(self, tmp_path: Path, monkeypatch):
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index-ja-jp-heading.sqlite")
        _write_cq_config(tmp_path, "hve")
        _touch(tmp_path / ".cq" / "index-hve.sqlite")
        calls: list = []
        self._stub_builders(monkeypatch, calls)

        index_refresh.refresh_all(tmp_path)

        assert [engine for engine, _a, _k in calls] == ["mdq", "cq"]
        for _engine, _args, kwargs in calls:
            assert kwargs.get("rebuild", False) is False

    def test_builders_receive_an_absolute_repo_root(self, tmp_path: Path, monkeypatch):
        """`mdq.indexer.build_index` は `path.relative_to(repo_root)` を行うため、
        相対パスのままだと解決済み絶対パスとの突合に失敗する。"""
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index-ja-jp-heading.sqlite")
        _write_cq_config(tmp_path, "hve")
        _touch(tmp_path / ".cq" / "index-hve.sqlite")
        calls: list = []
        self._stub_builders(monkeypatch, calls)
        monkeypatch.chdir(tmp_path)

        index_refresh.refresh_all(Path("."))

        assert calls, "builder が呼ばれていない"
        for _engine, args, _kwargs in calls:
            assert args[0].is_absolute(), args[0]

    def test_failure_of_one_target_does_not_stop_the_rest(
        self, tmp_path: Path, monkeypatch
    ):
        from hve import index_refresh

        _touch(tmp_path / ".mdq" / "index-ja-jp-heading.sqlite")
        _write_cq_config(tmp_path, "hve")
        _touch(tmp_path / ".cq" / "index-hve.sqlite")
        calls: list = []
        self._stub_builders(monkeypatch, calls)

        import mdq.indexer

        def _boom(*_a, **_k):
            raise RuntimeError("forced for test")

        monkeypatch.setattr(mdq.indexer, "build_index", _boom, raising=True)

        summary = index_refresh.refresh_all(tmp_path)

        assert [engine for engine, _a, _k in calls] == ["cq"]
        assert summary["refreshed"] == 1
        assert len(summary["failed"]) == 1

    def test_no_target_is_not_an_error(self, tmp_path: Path):
        from hve import index_refresh

        summary = index_refresh.refresh_all(tmp_path)

        assert summary["targets"] == 0
        assert summary["failed"] == []


class TestBackgroundLifecycle:
    def test_disabled_by_env(self, tmp_path: Path, monkeypatch):
        from hve import index_refresh

        monkeypatch.setenv(index_refresh.ENV_FLAG, "0")

        assert index_refresh.is_enabled() is False
        assert index_refresh.start_background(tmp_path) is False
        assert index_refresh.is_running() is False

    def test_enabled_by_default(self):
        from hve import index_refresh

        assert index_refresh.is_enabled() is True

    def test_starts_only_once_per_process(self, tmp_path: Path, monkeypatch):
        from hve import index_refresh

        release = threading.Event()
        monkeypatch.setattr(
            index_refresh, "refresh_all",
            lambda _root: release.wait(5) and {}, raising=True,
        )

        try:
            assert index_refresh.start_background(tmp_path) is True
            assert index_refresh.is_running() is True
            assert index_refresh.start_background(tmp_path) is False
        finally:
            release.set()
        assert index_refresh.wait_until_idle(5) is True
        assert index_refresh.is_running() is False

    def test_wait_until_idle_times_out_while_running(self, tmp_path: Path, monkeypatch):
        from hve import index_refresh

        release = threading.Event()
        monkeypatch.setattr(
            index_refresh, "refresh_all",
            lambda _root: release.wait(5) and {}, raising=True,
        )

        try:
            index_refresh.start_background(tmp_path)
            assert index_refresh.wait_until_idle(0.05) is False
        finally:
            release.set()
        index_refresh.wait_until_idle(5)

    def test_wait_until_idle_returns_true_when_never_started(self):
        from hve import index_refresh

        assert index_refresh.wait_until_idle(0) is True

    def test_exception_in_worker_still_clears_running(self, tmp_path: Path, monkeypatch):
        from hve import index_refresh

        def _boom(_root):
            raise RuntimeError("forced for test")

        monkeypatch.setattr(index_refresh, "refresh_all", _boom, raising=True)

        assert index_refresh.start_background(tmp_path) is True
        assert index_refresh.wait_until_idle(5) is True
        assert index_refresh.is_running() is False


class _FakeConn:
    def close(self) -> None:
        pass


class _FakeReport:
    def to_dict(self) -> dict:
        return {}
