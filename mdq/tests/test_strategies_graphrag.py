"""Tests for ``mdq.strategies_graphrag`` (T5.2).

Coverage targets:

- ``GraphRAGConfig`` defaults & ambient config (set/get/clear) round-trip.
- ``_validate_query_mode`` allow-list (R7: local/naive only).
- ``insert_paths_sync`` end-to-end with mock providers, including
  per-file status ("ok"/"skipped: empty"/"error: file not found") and
  ``progress_callback`` per-file invocation.
- ``query_sync`` end-to-end with mock providers and missing-working-dir
  failure path.

All tests use the deterministic mock LLM/embedding backends (no Ollama
calls), so they run without network access and without a model server.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

# graphrag extras (numpy + lightrag-hku) are optional; skip if missing.
pytest.importorskip("numpy")
pytest.importorskip("lightrag")

from mdq import strategies_graphrag as gs


# --- Config & ambient runtime --------------------------------------------


def test_config_defaults_are_local_loopback() -> None:
    cfg = gs.GraphRAGConfig()
    assert cfg.llm_provider == "ollama"
    assert cfg.embed_provider == "ollama"
    assert cfg.llm_base_url.startswith("http://127.0.0.1")
    assert cfg.embed_base_url.startswith("http://127.0.0.1")
    assert cfg.allow_remote_ollama is False
    assert cfg.query_mode == "local"


def test_runtime_config_set_get_clear_cycle() -> None:
    gs.clear_runtime_config()
    assert isinstance(gs.get_runtime_config(), gs.GraphRAGConfig)
    custom = gs.GraphRAGConfig(llm_model="custom-model")
    gs.set_runtime_config(custom)
    assert gs.get_runtime_config().llm_model == "custom-model"
    gs.clear_runtime_config()
    # After clear, default values are returned (not the previously set value).
    assert gs.get_runtime_config().llm_model == gs.GraphRAGConfig().llm_model


# --- _validate_query_mode (R7) -------------------------------------------


@pytest.mark.parametrize("mode", ["local", "naive"])
def test_validate_query_mode_allowed(mode: str) -> None:
    assert gs._validate_query_mode(mode) == mode


@pytest.mark.parametrize(
    "mode", ["global", "hybrid", "mix", "bypass", "Local", ""]
)
def test_validate_query_mode_rejected(mode: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        gs._validate_query_mode(mode)


def test_allowed_query_modes_is_immutable_set() -> None:
    """The allow-list must be a frozenset so callers cannot mutate it."""
    assert isinstance(gs.ALLOWED_QUERY_MODES, frozenset)
    assert gs.ALLOWED_QUERY_MODES == frozenset({"local", "naive"})


# --- end-to-end: insert + query with mock backends -----------------------


def _mock_config() -> gs.GraphRAGConfig:
    """Build a config that uses mock backends (no network)."""
    return gs.GraphRAGConfig(
        llm_provider="mock",
        embed_provider="mock",
        embed_mock_dim=64,
    )


def _make_files(root: Path, contents: dict[str, str]) -> list[Path]:
    """Materialise files under ``root`` and return their absolute paths."""
    paths: list[Path] = []
    for name, body in contents.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    return paths


@pytest.fixture(autouse=True)
def _suppress_lightrag_runtime_warnings():
    """LightRAG emits 'no rerank model' warnings at import-time on some
    versions. Tests assert behaviour, not the warning surface."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def test_insert_paths_sync_inserts_files(tmp_path: Path) -> None:
    paths = _make_files(tmp_path / "corpus", {
        "a.md": "# A\nalpha content paragraph",
        "b.md": "# B\nbeta content paragraph",
    })
    working_dir = tmp_path / "graphrag-store"
    result = gs.insert_paths_sync(working_dir, paths, config=_mock_config())
    assert set(result.keys()) == {str(p) for p in paths}
    assert all(v == "ok" for v in result.values()), result
    # LightRAG persists files into working_dir; confirm storage exists.
    assert working_dir.is_dir()
    files_in_wd = list(working_dir.iterdir())
    assert files_in_wd, "LightRAG should have written storage files"


def test_insert_paths_sync_missing_file_is_per_file_error(tmp_path: Path) -> None:
    """Missing files must be reported as 'error: file not found', not
    'skipped: empty' (the latter would imply we opened an empty file)."""
    good = _make_files(tmp_path / "c", {"good.md": "# G\nbody"})[0]
    missing = tmp_path / "c" / "absent.md"
    working_dir = tmp_path / "wd"
    result = gs.insert_paths_sync(
        working_dir, [good, missing], config=_mock_config()
    )
    assert result[str(good)] == "ok"
    assert result[str(missing)] == "error: file not found"


def test_insert_paths_sync_empty_file_is_skipped(tmp_path: Path) -> None:
    paths = _make_files(tmp_path / "c", {"empty.md": "   \n\n  "})
    working_dir = tmp_path / "wd"
    result = gs.insert_paths_sync(working_dir, paths, config=_mock_config())
    assert result[str(paths[0])] == "skipped: empty"


def test_insert_paths_sync_progress_callback_per_file(tmp_path: Path) -> None:
    paths = _make_files(tmp_path / "c", {
        "1.md": "# A\nx",
        "2.md": "# B\ny",
        "3.md": "# C\nz",
    })
    working_dir = tmp_path / "wd"
    calls: list[tuple[str, int, int, str]] = []

    def cb(path: str, cur: int, tot: int, status: str) -> None:
        calls.append((path, cur, tot, status))

    gs.insert_paths_sync(
        working_dir, paths, config=_mock_config(), progress_callback=cb
    )
    assert len(calls) == 3
    # callbacks are 1-based and the totals match the input length.
    assert [c[1] for c in calls] == [1, 2, 3]
    assert all(c[2] == 3 for c in calls)
    assert all(c[3] == "ok" for c in calls)


def test_insert_paths_sync_progress_callback_exceptions_swallowed(
    tmp_path: Path,
) -> None:
    """A buggy callback must not abort the batch."""
    paths = _make_files(tmp_path / "c", {"1.md": "# A\nx", "2.md": "# B\ny"})
    working_dir = tmp_path / "wd"

    def bad_cb(path, cur, tot, status):  # noqa: ARG001
        raise RuntimeError("boom")

    result = gs.insert_paths_sync(
        working_dir, paths, config=_mock_config(), progress_callback=bad_cb
    )
    assert all(v == "ok" for v in result.values())


def test_query_sync_after_insert_returns_string(tmp_path: Path) -> None:
    paths = _make_files(tmp_path / "c", {
        "doc.md": "# Title\nThis text mentions Alice and Bob.\n",
    })
    working_dir = tmp_path / "wd"
    cfg = _mock_config()
    gs.insert_paths_sync(working_dir, paths, config=cfg)
    answer = gs.query_sync(working_dir, "Tell me about Alice.", config=cfg)
    assert isinstance(answer, str)
    # Mock LLM may produce a no-context response; the contract is just that
    # a string is returned (already asserted via isinstance above).


def test_query_sync_missing_working_dir_raises(tmp_path: Path) -> None:
    cfg = _mock_config()
    with pytest.raises(gs.GraphRAGUnavailable, match="working_dir"):
        gs.query_sync(tmp_path / "never-created", "anything", config=cfg)


def test_query_sync_rejects_disallowed_mode(tmp_path: Path) -> None:
    """R7: 'mix'/'global'/'hybrid' are blocked before any LightRAG call."""
    paths = _make_files(tmp_path / "c", {"d.md": "# D\nbody"})
    working_dir = tmp_path / "wd"
    cfg = _mock_config()
    gs.insert_paths_sync(working_dir, paths, config=cfg)
    with pytest.raises(ValueError, match="not allowed"):
        gs.query_sync(working_dir, "q", mode="mix", config=cfg)
