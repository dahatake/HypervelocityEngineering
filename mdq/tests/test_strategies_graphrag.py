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


def test_build_rag_loads_the_llm_before_indexing(tmp_path, monkeypatch) -> None:
    """セッション開始時に LLM を 1 度呼び、モデル読み込みを前倒しすること。

    Ollama は初回呼び出しでモデルを読み込む（7B で実測約 2 分）。LightRAG は
    抽出呼び出しを並列に発行し Ollama はそれを直列化するため、読み込みが
    待ち行列の中に入ると後続要求がタイムアウトする。LightRAG 側の worker
    タイムアウトが上限になるので、タイムアウト値の引き上げでは解決しない。
    """
    import asyncio

    from mdq import graphrag_runtime as runtime

    calls: list[str] = []

    async def _completion(prompt, system_prompt=None, history_messages=None,
                          **_kwargs):
        calls.append(str(prompt))
        return "ok"

    monkeypatch.setattr(
        runtime, "get_completion_func", lambda *_a, **_k: _completion
    )

    rag = asyncio.run(gs._build_rag(tmp_path / "wd", gs.GraphRAGConfig(
        llm_provider="mock", embed_provider="mock", embed_mock_dim=8,
    )))
    asyncio.run(rag.finalize_storages())

    assert calls, "セッション開始時に LLM を呼んでいない（読み込みが後続要求へ相乗り）"


def test_build_rag_does_not_queue_requests_behind_each_other(
    tmp_path, monkeypatch
) -> None:
    """LLM 呼び出しの同時実行数を Ollama の直列処理に合わせること。

    LightRAG の既定は 4 並列だが Ollama は既定で 1 件ずつ処理する
    (``OLLAMA_NUM_PARALLEL=1``)。並列に投げると 3 件が待ち行列に入り、
    待ち時間まで各要求の経過時間に含まれてタイムアウトする。直列化しても
    Ollama 側の実効スループットは変わらない。
    """
    import asyncio

    import lightrag

    captured: dict = {}
    real_cls = lightrag.LightRAG

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(lightrag, "LightRAG", _spy)

    rag = asyncio.run(gs._build_rag(tmp_path / "wd", gs.GraphRAGConfig(
        llm_provider="mock", embed_provider="mock", embed_mock_dim=8,
    )))
    asyncio.run(rag.finalize_storages())

    assert captured.get("llm_model_max_async") == 1


def test_build_rag_does_not_process_documents_concurrently(
    tmp_path, monkeypatch
) -> None:
    """文書の同時処理数も Ollama の直列処理へ合わせること。

    LLM 呼び出しを直列化しても、LightRAG が既定で 3 文書を同時処理すると
    各文書の呼び出しが互いの後ろに並び、待ち時間が LightRAG 自身の実行
    タイムアウト (240 秒) を超える。実文書 1 件の抽出は実測 107.8 秒。
    """
    import asyncio

    import lightrag

    captured: dict = {}
    real_cls = lightrag.LightRAG

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(lightrag, "LightRAG", _spy)

    rag = asyncio.run(gs._build_rag(tmp_path / "wd", gs.GraphRAGConfig(
        llm_provider="mock", embed_provider="mock", embed_mock_dim=8,
    )))
    asyncio.run(rag.finalize_storages())

    assert captured.get("max_parallel_insert") == 1


def test_build_rag_propagates_the_configured_timeout(tmp_path, monkeypatch) -> None:
    """設定したタイムアウトが LightRAG 側の実行タイムアウトにも効くこと。

    LightRAG は自身の ``default_llm_timeout`` (既定 240 秒) で LLM 呼び出しを
    打ち切る。mdq 側の HTTP タイムアウトだけを延ばしても LightRAG 側が先に
    発火するため、``--graphrag-timeout`` が実質無効になる。
    """
    import asyncio

    import lightrag

    captured: dict = {}
    real_cls = lightrag.LightRAG

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(lightrag, "LightRAG", _spy)

    rag = asyncio.run(gs._build_rag(tmp_path / "wd", gs.GraphRAGConfig(
        llm_provider="mock", embed_provider="mock", embed_mock_dim=8,
        llm_timeout=1234.0, embed_timeout=567.0,
    )))
    asyncio.run(rag.finalize_storages())

    assert captured.get("default_llm_timeout") == 1234
    assert captured.get("default_embedding_timeout") == 567


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
