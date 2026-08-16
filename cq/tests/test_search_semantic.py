"""FR-CQ-17: 意味検索経路（RED）。

意味検索は融合の 1 経路として参加する。Azure AI Search の Agentic Retrieval で
サブクエリが keyword / vector / hybrid のいずれでも走り、結果が 1 本のランキングへ
統合されるのと同じ形。単独の `--mode` にはしない（`--mode` は「単一経路の明示指定」
で `ROUTES` と 1:1 という既存の不変条件があるため）。

ベクトルが無い環境・別モデルで作られた環境では、警告もエラーも出さずに
語彙経路だけで答える（既定 OFF の機能が既存動作を壊さないこと）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, search, semantic_index

_DB = Path(".cq") / "index-test.sqlite"
_VEC = Path(".cq") / "vectors-test.sqlite"


class _FakeProvider:
    """語が 1 つでも重なれば近い、という決定的な擬似埋め込み。"""

    model = "fake"

    def __init__(self) -> None:
        self.vocabulary = ["付与", "取消", "grant", "revoke", "ポイント"]

    def embed(self, texts):
        import numpy as np

        rows = []
        for text in texts:
            row = [1.0 if word in text else 0.0 for word in self.vocabulary]
            rows.append(row + [0.01])
        matrix = np.asarray(rows, dtype="float32")
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    # 英語の識別子に日本語の docstring。語彙一致では日本語クエリが届かない構図。
    (tmp_path / "pkg" / "ledger.py").write_text(
        "def grant(amount):\n"
        '    """ポイントを付与する。"""\n'
        "    return amount\n"
        "\n"
        "\n"
        "def revoke(amount):\n"
        '    """ポイントを取消する。"""\n'
        "    return -amount\n",
        encoding="utf-8",
    )
    indexer.build_index(
        tmp_path, config.resolve_profile(tmp_path, "test"), db_path=tmp_path / _DB
    )
    return tmp_path


def _embed(repo: Path) -> None:
    semantic_index.build(repo, "test", _FakeProvider(),
                         db_path=repo / _DB, vector_path=repo / _VEC)


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, **kwargs)


class TestSemanticRoute:
    def test_a_japanese_query_reaches_english_code_through_the_docstring(
        self, repo: Path
    ) -> None:
        _embed(repo)
        assert _search(repo, query="ポイント 付与") == []  # 語彙経路だけでは届かない
        hits = _search(repo, query="ポイント 付与", semantic=True,
                       provider=_FakeProvider(), vector_path=repo / _VEC)
        assert hits
        assert hits[0].route == "semantic"
        assert hits[0].path == "pkg/ledger.py"
        assert hits[0].lines[0] == 1  # `grant` 側。`revoke` は 6 行目から。

    def test_the_semantic_route_appears_in_the_activity_record(self, repo: Path) -> None:
        _embed(repo)
        _search(repo, query="ポイント 付与", semantic=True,
                provider=_FakeProvider(), vector_path=repo / _VEC)
        assert "semantic" in {e["route"] for e in search.last_activity()["routes"]}

    def test_semantic_is_skipped_when_a_single_route_is_forced(self, repo: Path) -> None:
        """`--mode` は単一経路の明示指定なので、意味検索を混ぜない。"""
        _embed(repo)
        assert _search(repo, query="ポイント 付与", mode="bm25", semantic=True,
                       provider=_FakeProvider(), vector_path=repo / _VEC) == []


class TestDegradation:
    def test_an_absent_vector_store_degrades_to_the_lexical_routes(
        self, repo: Path
    ) -> None:
        hits = _search(repo, query="grant", semantic=True,
                       provider=_FakeProvider(), vector_path=repo / _VEC)
        assert {h.path for h in hits} == {"pkg/ledger.py"}
        assert "semantic" not in {h.route for h in hits}

    def test_a_store_from_another_model_is_ignored(self, repo: Path) -> None:
        _embed(repo)

        class _Other(_FakeProvider):
            model = "another-model"

        hits = _search(repo, query="ポイント 付与", semantic=True,
                       provider=_Other(), vector_path=repo / _VEC)
        assert hits == []

    def test_an_unavailable_backend_does_not_break_the_search(
        self, repo: Path, monkeypatch
    ) -> None:
        """`fastembed` 未導入でも検索そのものは成功しなければならない。

        導入済みの環境でも同じ経路を通すため provider の取得を差し替える。実物を
        読むと 240 MiB のモデルをロードしてしまい、検証内容も環境依存になる。
        """
        from cq import embeddings

        _embed(repo)

        def unavailable(*_args, **_kwargs):
            raise embeddings.EmbeddingsUnavailable("no backend")

        monkeypatch.setattr(embeddings, "get_provider", unavailable)
        hits = _search(repo, query="grant", semantic=True, vector_path=repo / _VEC)
        assert {h.path for h in hits} == {"pkg/ledger.py"}
        assert "semantic" not in {h.route for h in hits}

    def test_a_stale_vector_row_is_not_used(self, repo: Path) -> None:
        _embed(repo)
        (repo / "pkg" / "ledger.py").write_text(
            "def grant(amount):\n"
            '    """まったく別の説明。"""\n'
            "    return amount\n",
            encoding="utf-8",
        )
        indexer.build_index(
            repo, config.resolve_profile(repo, "test"), db_path=repo / _DB
        )
        hits = _search(repo, query="ポイント 付与", semantic=True,
                       provider=_FakeProvider(), vector_path=repo / _VEC)
        assert all(h.route != "semantic" for h in hits)
