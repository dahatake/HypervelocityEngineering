"""Tests for the graphrag CLI integration (T5.3).

These tests drive ``mdq.cli.main`` end-to-end through the argument
parser with mock LLM/embedding backends, so they run without network
access. They cover:

- ``mdq index --strategy graphrag`` writes a LightRAG working directory
  and emits a structured JSON summary on stdout (exit 0).
- ``mdq search --strategy graphrag`` reads the working directory built
  above and emits an answer JSON line on stdout (exit 0).
- ``mdq search --strategy graphrag --format compact`` prints the bare
  answer text (no JSON envelope).
- ``mdq search --strategy graphrag`` against a non-existent working
  directory exits with code 2 and prints a structured error to stderr.
- The graphrag branch never touches SQLite: no ``.mdq/index-*.sqlite``
  file is created during a graphrag run.

The fixtures use ``--graphrag-working-dir`` to keep state inside
``tmp_path`` so the user's real ``.mdq/`` directory is untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# graphrag extras (numpy + lightrag-hku) are optional; skip if missing.
pytest.importorskip("numpy")
pytest.importorskip("lightrag")

from mdq import cli


def _run_cli(monkeypatch, tmp_path: Path, argv: list[str],
             capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Invoke ``mdq.cli.main`` with cwd=tmp_path and return (exit, out, err)."""
    monkeypatch.chdir(tmp_path)
    rc = cli.main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _make_corpus(tmp_path: Path) -> None:
    """Create a small users-guide corpus under tmp_path."""
    docs = tmp_path / "users-guide"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "intro.md").write_text(
        "# Intro\n\nmdq is a local-only Markdown query toolkit.\n",
        encoding="utf-8",
    )
    (docs / "graphrag.md").write_text(
        "# GraphRAG\n\nGraphRAG builds a knowledge graph over the corpus.\n",
        encoding="utf-8",
    )


def test_cli_index_graphrag_writes_storage_and_summary(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _make_corpus(tmp_path)
    working_dir = tmp_path / "gr-store"
    rc, out, _err = _run_cli(monkeypatch, tmp_path, [
        "index",
        "--strategy", "graphrag",
        "--root", "users-guide",
        "--graphrag-llm-provider", "mock",
        "--graphrag-embed-provider", "mock",
        "--graphrag-working-dir", str(working_dir),
        "--rebuild",
    ], capsys)
    assert rc == 0, f"index failed: rc={rc}"
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary["strategy"] == "graphrag"
    assert summary["files_total"] == 2
    assert summary["files_ok"] == 2
    assert summary["files_error"] == 0
    assert Path(summary["working_dir"]).resolve() == working_dir.resolve()
    assert working_dir.is_dir()
    # SQLite must NOT be touched by the graphrag pipeline.
    sqlite_files = list((tmp_path / ".mdq").glob("index-*.sqlite")) \
        if (tmp_path / ".mdq").exists() else []
    assert sqlite_files == [], (
        f"graphrag must not create SQLite indexes; found: {sqlite_files}"
    )


def test_cli_search_graphrag_jsonl_format(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _make_corpus(tmp_path)
    working_dir = tmp_path / "gr-store"
    common = [
        "--strategy", "graphrag",
        "--graphrag-llm-provider", "mock",
        "--graphrag-embed-provider", "mock",
        "--graphrag-working-dir", str(working_dir),
    ]
    rc, _out, _err = _run_cli(monkeypatch, tmp_path, [
        "index", *common, "--root", "users-guide", "--rebuild",
    ], capsys)
    assert rc == 0
    rc, out, _err = _run_cli(monkeypatch, tmp_path, [
        "search", *common, "--q", "What is mdq?", "--format", "jsonl",
    ], capsys)
    assert rc == 0, f"search failed: rc={rc}"
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["strategy"] == "graphrag"
    assert payload["mode"] == "local"
    assert isinstance(payload["answer"], str)
    assert "top_k" in payload


def test_cli_search_graphrag_compact_format(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _make_corpus(tmp_path)
    working_dir = tmp_path / "gr-store"
    common = [
        "--strategy", "graphrag",
        "--graphrag-llm-provider", "mock",
        "--graphrag-embed-provider", "mock",
        "--graphrag-working-dir", str(working_dir),
    ]
    _run_cli(monkeypatch, tmp_path, [
        "index", *common, "--root", "users-guide", "--rebuild",
    ], capsys)
    rc, out, _err = _run_cli(monkeypatch, tmp_path, [
        "search", *common, "--q", "Hi", "--format", "compact",
    ], capsys)
    assert rc == 0
    # The compact format prints the bare answer; it must not look like JSON.
    stdout = out.strip()
    assert stdout, "compact format produced no output"
    assert not stdout.startswith("{"), (
        f"compact format must not emit JSON envelope: {stdout!r}"
    )


def test_cli_search_graphrag_missing_working_dir_exits_2(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    working_dir = tmp_path / "never-created"
    rc, _out, err = _run_cli(monkeypatch, tmp_path, [
        "search",
        "--strategy", "graphrag",
        "--graphrag-llm-provider", "mock",
        "--graphrag-embed-provider", "mock",
        "--graphrag-working-dir", str(working_dir),
        "--q", "anything",
    ], capsys)
    assert rc == 2, f"expected exit 2, got {rc}"
    # Error payload must be structured JSON on stderr.
    err_line = err.strip().splitlines()[-1]
    payload = json.loads(err_line)
    assert payload["strategy"] == "graphrag"
    assert payload["error"] == "GraphRAGUnavailable"
    assert "working_dir" in payload["message"]


def test_cli_rejects_unsupported_query_mode(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """argparse must reject mode='mix' at parse time (R7)."""
    # argparse calls sys.exit(2) on invalid choice; capture via SystemExit.
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            "search",
            "--strategy", "graphrag",
            "--graphrag-query-mode", "mix",
            "--q", "x",
        ])
    assert exc_info.value.code == 2


def test_build_graphrag_index_refuses_rebuild_on_unrelated_dir(
    tmp_path: Path,
) -> None:
    """rebuild=True must refuse to rmtree a directory that lacks LightRAG marker files."""
    from mdq import indexer
    # Simulate a user accidentally pointing --graphrag-working-dir at an
    # unrelated populated directory (e.g. their home or project root).
    victim = tmp_path / "important-user-data"
    victim.mkdir()
    (victim / "precious.txt").write_text("do not delete me", encoding="utf-8")
    with pytest.raises(ValueError, match="--rebuild refused"):
        indexer.build_graphrag_index(
            tmp_path, ["users-guide"], victim, rebuild=True,
        )
    # The directory and its contents must be untouched.
    assert victim.exists()
    assert (victim / "precious.txt").read_text(encoding="utf-8") == "do not delete me"


def test_build_graphrag_index_allows_rebuild_on_empty_dir(
    tmp_path: Path,
) -> None:
    """rebuild=True must allow rmtree on an empty directory (common case)."""
    _make_corpus(tmp_path)
    working_dir = tmp_path / "empty-then-graphrag"
    working_dir.mkdir()
    # Run index with mock providers; this should succeed because the dir is empty.
    summary = _run_graphrag_index_directly(tmp_path, working_dir)
    assert summary["files_total"] == 2
    assert summary["files_ok"] == 2


def _run_graphrag_index_directly(repo_root: Path, working_dir: Path) -> dict:
    """Build a graphrag index with mock providers, bypassing the CLI."""
    from mdq import indexer, strategies_graphrag as gs
    gs.set_runtime_config(gs.GraphRAGConfig(
        llm_provider="mock", embed_provider="mock",
    ))
    try:
        return indexer.build_graphrag_index(
            repo_root, ["users-guide"], working_dir, rebuild=True,
        )
    finally:
        gs.clear_runtime_config()
