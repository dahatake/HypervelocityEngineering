"""FR-MDQ-09: 索引と作業ツリーの乖離検知。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mdq import freshness, store


def _indexed_store(tmp_path: Path, rel: str, body: str):
    """``rel`` を実ファイルとして作り、その stat 値で索引に登録した store を返す。"""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    stat = target.stat()
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    store.upsert_file(conn, rel, "sha-placeholder", stat.st_mtime,
                      stat.st_size, None)
    conn.commit()
    return conn, target


def test_reports_no_drift_for_an_untouched_tree(tmp_path: Path) -> None:
    conn, _ = _indexed_store(tmp_path, "docs/a.md", "hello\n")
    try:
        report = freshness.check(tmp_path, conn)
        assert report.is_fresh
        assert report.changed == ()
        assert report.warning() is None
    finally:
        conn.close()


def test_detects_a_size_change(tmp_path: Path) -> None:
    conn, target = _indexed_store(tmp_path, "docs/a.md", "hello\n")
    try:
        target.write_text("hello world\n", encoding="utf-8")
        report = freshness.check(tmp_path, conn)
        assert report.changed == ("docs/a.md",)
        assert not report.is_fresh
    finally:
        conn.close()


def test_does_not_read_file_contents(tmp_path: Path) -> None:
    """内容だけ変えて size と mtime を戻すと乖離として報告しない。

    内容ハッシュを読んでいないことの証明（FR-MDQ-09 (1)）。
    """
    conn, target = _indexed_store(tmp_path, "docs/a.md", "aaaaa\n")
    try:
        stat = target.stat()
        target.write_text("bbbbb\n", encoding="utf-8")  # 同じ長さ
        os.utime(target, (stat.st_atime, stat.st_mtime))
        assert freshness.check(tmp_path, conn).is_fresh
    finally:
        conn.close()


def test_detects_a_file_that_disappeared(tmp_path: Path) -> None:
    conn, target = _indexed_store(tmp_path, "docs/a.md", "hello\n")
    try:
        target.unlink()
        assert freshness.check(tmp_path, conn).changed == ("docs/a.md",)
    finally:
        conn.close()


def test_ignores_files_absent_from_the_index(tmp_path: Path) -> None:
    """索引に無い新規ファイルは検知対象にしない（FR-MDQ-09 (2)）。"""
    conn, _ = _indexed_store(tmp_path, "docs/a.md", "hello\n")
    try:
        (tmp_path / "docs" / "new.md").write_text("new\n", encoding="utf-8")
        assert freshness.check(tmp_path, conn).is_fresh
    finally:
        conn.close()


def test_warning_carries_the_count_and_a_recovery_hint(tmp_path: Path) -> None:
    conn, target = _indexed_store(tmp_path, "docs/a.md", "hello\n")
    try:
        target.write_text("hello world\n", encoding="utf-8")
        warning = freshness.check(tmp_path, conn).warning()
        assert warning is not None
        assert warning["warning"] == "stale"
        assert warning["changed"] == 1
        assert "mdq index" in warning["hint"]
    finally:
        conn.close()


def test_a_broken_store_is_reported_as_fresh_instead_of_raising(
    tmp_path: Path,
) -> None:
    """検知処理の失敗が検索を止めないこと（FR-MDQ-09 (6)）。"""

    class _Broken:
        def execute(self, *args, **kwargs):
            raise RuntimeError("boom")

    assert freshness.check(tmp_path, _Broken()).is_fresh


def test_cli_exposes_a_switch_to_disable_the_check() -> None:
    from mdq import cli

    parser = cli.build_parser()
    args = parser.parse_args(["search", "--q", "x"])
    assert args.freshness_check is True
    args = parser.parse_args(["search", "--q", "x", "--no-freshness-check"])
    assert args.freshness_check is False


def test_warning_is_written_to_stderr_not_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ヒットの JSONL を出す stdout へ混入させないこと（FR-MDQ-09 (3)）。"""
    freshness.emit_warning({"warning": "stale", "changed": 2, "hint": "run x"})
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stale" in captured.err
