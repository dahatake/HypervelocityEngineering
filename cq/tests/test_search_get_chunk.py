"""RED contracts for the reusable CQ chunk lookup API (FR-CQ-13)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from cq import cli, store
from cq.search import ChunkPayload, get_chunk



@pytest.fixture()
def indexed_chunk(tmp_path: Path) -> tuple[Path, ChunkPayload]:
    db_path = tmp_path / ".cq" / "index-test.sqlite"
    with closing(store.open_store(db_path)) as conn:
        # `parser` belongs to `files`, not `chunks`: the exact payload assertion
        # below therefore detects an implementation that forgets the required JOIN.
        conn.execute(
            "INSERT INTO files(path, lang, sha1, mtime, size_bytes, parser) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("pkg/service.py", "python", "abc123", 1.0, 48, "tree-sitter"),
        )
        conn.execute(
            "INSERT INTO chunks("
            "chunk_id, path, symbol_id, name, signature, ident_text, "
            "start_line, end_line, token_est, text"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "chunk-1",
                "pkg/service.py",
                None,
                "grant_points",
                "def grant_points(self, amount):",
                "grant points",
                4,
                5,
                12,
                "def grant_points(self, amount):\n    return amount",
            ),
        )
        conn.commit()
    expected: ChunkPayload = {
        "chunk_id": "chunk-1",
        "path": "pkg/service.py",
        "lines": [4, 5],
        "text": "def grant_points(self, amount):\n    return amount",
        "parser": "tree-sitter",
    }
    return db_path, expected


def test_get_chunk_returns_exact_public_shape(
    indexed_chunk: tuple[Path, ChunkPayload],
) -> None:
    db_path, expected = indexed_chunk

    payload = get_chunk(db_path, "chunk-1")

    assert payload == expected
    assert set(payload) == {"chunk_id", "path", "lines", "text", "parser"}


def test_get_chunk_returns_none_for_an_unknown_id(
    indexed_chunk: tuple[Path, ChunkPayload],
) -> None:
    db_path, _ = indexed_chunk

    assert get_chunk(db_path, "missing") is None


def test_cli_get_delegates_to_shared_api_and_preserves_output(
    indexed_chunk: tuple[Path, ChunkPayload],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    db_path, _ = indexed_chunk
    calls: list[tuple[Path, str]] = []
    delegated: ChunkPayload = {
        "chunk_id": "delegated-id",
        "path": "delegated/result.py",
        "lines": [40, 41],
        "text": "def delegated():\n    return 'sentinel'",
        "parser": "lite",
    }

    def fake_get_chunk(path: Path, chunk_id: str) -> ChunkPayload:
        calls.append((path, chunk_id))
        return delegated

    monkeypatch.setattr(cli, "get_chunk", fake_get_chunk)

    code = cli.main(
        [
            "get",
            "--chunk-id",
            "chunk-1",
            "--profile",
            "test",
            "--repo-root",
            str(tmp_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert calls == [(db_path, "chunk-1")]
    assert captured.out == (
        "# delegated/result.py:40-41\n"
        "def delegated():\n"
        "    return 'sentinel'\n"
    )
    assert captured.err == ""


def test_cli_get_preserves_unknown_id_error_contract(
    indexed_chunk: tuple[Path, ChunkPayload],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    db_path, _ = indexed_chunk
    calls: list[tuple[Path, str]] = []

    def fake_get_chunk(path: Path, chunk_id: str) -> None:
        calls.append((path, chunk_id))
        return None

    monkeypatch.setattr(cli, "get_chunk", fake_get_chunk)

    code = cli.main(
        [
            "get",
            "--chunk-id",
            "chunk-1",
            "--profile",
            "test",
            "--repo-root",
            str(tmp_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert calls == [(db_path, "chunk-1")]
    assert captured.out == ""
    assert captured.err == "error: unknown chunk id: chunk-1\n"
