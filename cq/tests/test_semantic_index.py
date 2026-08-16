"""FR-CQ-17: 索引時のベクトル生成（RED）。

埋め込みは既定 OFF。前回の実測で hve profile の索引時間が **+401.8 秒**、
ベクトルが 20.8 MiB 増えることが分かっているため、使わない利用者に払わせない。

埋め込み対象テキストは `name + signature + doc_head`（doc が無ければ本文先頭）。
前回 NO-GO の PoC は `name + signature + text[:512]` でコード本体を混ぜており、
日本語 natural 2/2 が圏外だった。本リポジトリの `doc_head` は hve profile で
6,273 件中 5,432 件（86.6%）が日本語なので、doc を主にすると日本語クエリと
同一言語で照合できる経路ができる、というのが今回の仮説。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, semantic_index, store, vectors

_DB = Path(".cq") / "index-test.sqlite"
_VEC = Path(".cq") / "vectors-test.sqlite"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "ledger.py").write_text(
        "def grant(amount):\n"
        '    """ポイントを付与する。"""\n'
        "    return amount\n"
        "\n"
        "\n"
        "def revoke(amount):\n"
        '    """付与済みポイントを取り消す。"""\n'
        "    return -amount\n",
        encoding="utf-8",
    )
    indexer.build_index(
        tmp_path, config.resolve_profile(tmp_path, "test"), db_path=tmp_path / _DB
    )
    return tmp_path


class _FakeProvider:
    """呼び出し回数と入力テキストを記録する決定的な provider。"""

    model = "fake"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def embed(self, texts):
        import numpy as np

        batch = list(texts)
        self.seen.extend(batch)
        rows = [
            np.array([float(len(t) % 7), float(sum(map(ord, t)) % 11), 1.0], dtype="float32")
            for t in batch
        ]
        matrix = np.asarray(rows, dtype="float32")
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class TestEmbeddingText:
    def test_the_docstring_is_what_gets_embedded(self, repo: Path) -> None:
        provider = _FakeProvider()
        semantic_index.build(repo, "test", provider,
                             db_path=repo / _DB, vector_path=repo / _VEC)
        assert any("ポイントを付与する" in text for text in provider.seen)

    def test_the_name_and_signature_are_included(self, repo: Path) -> None:
        provider = _FakeProvider()
        semantic_index.build(repo, "test", provider,
                             db_path=repo / _DB, vector_path=repo / _VEC)
        assert any("def grant(amount)" in text for text in provider.seen)

    def test_a_chunk_without_a_docstring_falls_back_to_its_body(self, repo: Path) -> None:
        (repo / "pkg" / "plain.py").write_text(
            "def undocumented():\n    marker_token = 1\n    return marker_token\n",
            encoding="utf-8",
        )
        indexer.build_index(
            repo, config.resolve_profile(repo, "test"), db_path=repo / _DB
        )
        provider = _FakeProvider()
        semantic_index.build(repo, "test", provider,
                             db_path=repo / _DB, vector_path=repo / _VEC)
        assert any("marker_token" in text for text in provider.seen)


class TestBuild:
    def test_every_chunk_gets_a_vector(self, repo: Path) -> None:
        written = semantic_index.build(repo, "test", _FakeProvider(),
                                       db_path=repo / _DB, vector_path=repo / _VEC)
        with store.open_store(repo / _DB, create=False) as conn:
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert written == chunks

    def test_the_vectors_are_readable_afterwards(self, repo: Path) -> None:
        semantic_index.build(repo, "test", _FakeProvider(),
                             db_path=repo / _DB, vector_path=repo / _VEC)
        with store.open_store(repo / _DB, create=False) as conn:
            fresh = {r["path"]: r["sha1"] for r in conn.execute("SELECT path, sha1 FROM files")}
        assert vectors.read_all(repo / _VEC, "fake", fresh)

    def test_rebuilding_after_an_edit_refreshes_the_vectors(self, repo: Path) -> None:
        semantic_index.build(repo, "test", _FakeProvider(),
                             db_path=repo / _DB, vector_path=repo / _VEC)
        (repo / "pkg" / "ledger.py").write_text(
            "def grant(amount):\n"
            '    """まったく別の説明に書き換えた。"""\n'
            "    return amount\n",
            encoding="utf-8",
        )
        indexer.build_index(
            repo, config.resolve_profile(repo, "test"), db_path=repo / _DB
        )
        with store.open_store(repo / _DB, create=False) as conn:
            fresh = {r["path"]: r["sha1"] for r in conn.execute("SELECT path, sha1 FROM files")}
        assert vectors.read_all(repo / _VEC, "fake", fresh) == {}
        semantic_index.build(repo, "test", _FakeProvider(),
                             db_path=repo / _DB, vector_path=repo / _VEC)
        assert vectors.read_all(repo / _VEC, "fake", fresh)
