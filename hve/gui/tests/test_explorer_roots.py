"""hve.gui.explorer_roots のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui.explorer_roots import ensure_roots, parse_roots, resolve_explorer_roots


def test_parse_roots_empty(tmp_path: Path) -> None:
    assert parse_roots("", repo_root=tmp_path) == []
    assert parse_roots("   ", repo_root=tmp_path) == []
    assert parse_roots(";;", repo_root=tmp_path) == []


def test_parse_roots_relative(tmp_path: Path) -> None:
    result = parse_roots("docs;qa;knowledge", repo_root=tmp_path)
    assert result == [
        (tmp_path / "docs").resolve(),
        (tmp_path / "qa").resolve(),
        (tmp_path / "knowledge").resolve(),
    ]


def test_parse_roots_dedup(tmp_path: Path) -> None:
    result = parse_roots("docs;docs;qa", repo_root=tmp_path)
    assert result == [(tmp_path / "docs").resolve(), (tmp_path / "qa").resolve()]


def test_parse_roots_absolute(tmp_path: Path) -> None:
    abs_dir = tmp_path / "external"
    result = parse_roots(f"docs;{abs_dir}", repo_root=tmp_path)
    assert result == [(tmp_path / "docs").resolve(), abs_dir.resolve()]


def test_ensure_roots_creates_missing(tmp_path: Path) -> None:
    targets = [tmp_path / "a", tmp_path / "b" / "c"]
    ensure_roots(targets)
    assert targets[0].is_dir()
    assert targets[1].is_dir()


def test_ensure_roots_skips_existing(tmp_path: Path) -> None:
    existing = tmp_path / "already"
    existing.mkdir()
    (existing / "file.txt").write_text("keep")
    ensure_roots([existing])
    assert (existing / "file.txt").read_text() == "keep"


def test_ensure_roots_no_gitkeep_created(tmp_path: Path) -> None:
    new_dir = tmp_path / "fresh"
    ensure_roots([new_dir])
    assert new_dir.is_dir()
    assert not (new_dir / ".gitkeep").exists()


def test_resolve_explorer_roots_creates_and_returns_dirs(tmp_path: Path) -> None:
    raw = "docs;knowledge;qa"
    result = resolve_explorer_roots(raw, repo_root=tmp_path)
    expected = [tmp_path / "docs", tmp_path / "knowledge", tmp_path / "qa"]
    assert result == [p.resolve() for p in expected]
    for p in expected:
        assert p.is_dir()


def test_resolve_explorer_roots_with_extra_roots_first(tmp_path: Path) -> None:
    work_root = tmp_path / "work" / "gui-runs" / "session-1"
    work_root.mkdir(parents=True)
    result = resolve_explorer_roots(
        "docs;qa", repo_root=tmp_path, extra_roots=[work_root]
    )
    assert result[0] == work_root.resolve()
    assert result[1] == (tmp_path / "docs").resolve()


def test_resolve_explorer_roots_dedup_across_extra_and_raw(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    result = resolve_explorer_roots(
        "docs", repo_root=tmp_path, extra_roots=[docs]
    )
    assert result == [docs.resolve()]


def test_resolve_explorer_roots_filters_non_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ファイルが既に存在する場合、ensure_roots は OSError を握り潰し、
    # resolve_explorer_roots は is_dir() == False のものを除外する。
    conflict = tmp_path / "conflict"
    conflict.write_text("i am a file")
    result = resolve_explorer_roots("conflict;docs", repo_root=tmp_path)
    # conflict はファイルなので除外、docs はディレクトリとして作成され採用。
    assert (tmp_path / "docs").is_dir()
    assert conflict.resolve() not in result
    assert (tmp_path / "docs").resolve() in result
