"""FR-CQ-17: 意味検索のベクトル格納（RED）。

ベクトルは本体索引とは**別ファイル** `.cq/vectors-<profile>.sqlite` に置く。
本体の `chunks` に列を足すと `SCHEMA_VERSION` を上げることになり、`store.py` が
既存の `.cq/index-*.sqlite` を fail-closed で拒否して、**意味検索を使わない利用者
にも全再構築を強制する**（hve profile でフル 106 秒）。

分離した代償として同期ずれが起きうるので、chunk 本文の SHA-1 を一緒に持ち、
一致しない行は「無い」ものとして扱う（fail-soft）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cq import vectors


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    return tmp_path / ".cq" / "vectors-test.sqlite"


def _write(db: Path, rows) -> None:
    with vectors.open_store(db) as conn:
        vectors.replace(conn, "m", rows)


class TestStorage:
    def test_the_path_is_separate_from_the_main_index(self) -> None:
        assert vectors.db_path_for("hve") == Path(".cq") / "vectors-hve.sqlite"

    def test_vectors_round_trip(self, db: Path) -> None:
        _write(db, [("c1", "a.py", "sha1", [0.6, 0.8]), ("c2", "b.py", "sha2", [0.0, 1.0])])
        loaded = vectors.read_all(db, "m", {"a.py": "sha1", "b.py": "sha2"})
        assert sorted(loaded) == ["c1", "c2"]
        assert [round(float(v), 4) for v in loaded["c1"]] == [0.6, 0.8]

    def test_a_chunk_whose_file_changed_is_ignored(self, db: Path) -> None:
        """`chunk_id` はパスと順番から作られるので、編集後も同じ id が残る。

        本体索引だけ再構築された場合に古いベクトルを使うと、正しい場所を指さない
        chunk_id へ当たって誤答になる。
        """
        _write(db, [("c1", "a.py", "old", [1.0, 0.0])])
        assert vectors.read_all(db, "m", {"a.py": "new"}) == {}

    def test_replacing_prunes_rows_that_are_gone(self, db: Path) -> None:
        _write(db, [("c1", "a.py", "sha1", [1.0, 0.0]), ("c2", "b.py", "sha2", [0.0, 1.0])])
        _write(db, [("c1", "a.py", "sha1", [1.0, 0.0])])
        assert sorted(vectors.read_all(db, "m", {"a.py": "sha1", "b.py": "sha2"})) == ["c1"]

    def test_the_model_is_recorded(self, db: Path) -> None:
        """次元の異なるモデルで作ったベクトルを混ぜるとクエリ側で落ちる。"""
        _write(db, [("c1", "a.py", "sha1", [1.0, 0.0])])
        with vectors.open_store(db) as conn:
            assert vectors.model_of(conn) == "m"

    def test_a_missing_store_reads_as_empty(self, tmp_path: Path) -> None:
        """ベクトルを作っていない利用者でも検索は成立する。"""
        assert vectors.read_all(tmp_path / "absent.sqlite", "m", {}) == {}

    def test_a_store_built_with_another_model_is_ignored(self, db: Path) -> None:
        _write(db, [("c1", "a.py", "sha1", [1.0, 0.0])])
        assert vectors.read_all(db, "other-model", {"a.py": "sha1"}) == {}


class TestSimilarity:
    def test_the_nearest_row_is_first(self) -> None:
        pool = {"far": [0.0, 1.0], "near": [1.0, 0.0], "mid": [0.7071, 0.7071]}
        ranked = vectors.rank([1.0, 0.0], pool, top_k=3)
        assert [key for key, _ in ranked] == ["near", "mid", "far"]

    def test_top_k_is_respected(self) -> None:
        pool = {str(i): [1.0, float(i)] for i in range(10)}
        assert len(vectors.rank([1.0, 0.0], pool, top_k=3)) == 3

    def test_ties_are_broken_deterministically(self) -> None:
        pool = {"b": [1.0, 0.0], "a": [1.0, 0.0]}
        assert [key for key, _ in vectors.rank([1.0, 0.0], pool, top_k=2)] == ["a", "b"]

    def test_an_empty_pool_yields_nothing(self) -> None:
        assert vectors.rank([1.0, 0.0], {}, top_k=5) == []
