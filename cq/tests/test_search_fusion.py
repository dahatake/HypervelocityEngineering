"""FR-CQ-16: 複数経路を同時に実行して順位で融合する検索。

統合は **意味検索層を含むときにだけ**行う。golden 56 問の実測で、語彙経路だけを
統合した結果は逐次 fallback と **56 問すべてで順位が完全に一致**し、応答トークン
だけが 2.2〜2.4 倍に増えた。単独で有効化する `--fuse` は測って外した。

Azure AI Search の Agentic Retrieval が「サブクエリを並列実行し統合ランキングへ
まとめる」形をとるのと同じ構造を、LLM もクラウドも使わずローカルで実現している。
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
    vocabulary = ("ledger", "posting", "archive", "notes", "audit")

    def embed(self, texts):
        import numpy as np

        rows = [[1.0 if w in t else 0.0 for w in self.vocabulary] + [0.01] for t in texts]
        matrix = np.asarray(rows, dtype="float32")
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    # `ledger` は名前・本文・パスの 3 箇所に散らばる。経路ごとに別の勝者が出る。
    (tmp_path / "pkg" / "ledger.py").write_text(
        "def ledger(amount):\n"
        "    \"\"\"Exact symbol match lives here.\"\"\"\n"
        "    return amount\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "posting.py").write_text(
        "def post_entry(amount):\n"
        "    \"\"\"The ledger keeps every posting for audit.\"\"\"\n"
        "    total = amount\n"
        "    return total\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "ledger_archive.py").write_text(
        "def archive(rows):\n    return list(rows)\n", encoding="utf-8"
    )
    # 名前以外の 3 経路（path / substr / bm25）すべてに現れるファイル。
    # 順位の逆数和を素朴に取ると、リテラル一致 1 件よりこちらが上へ来てしまう。
    (tmp_path / "pkg" / "ledger_notes.py").write_text(
        "def notes():\n"
        "    \"\"\"ledger ledger ledger notes about the ledger.\"\"\"\n"
        "    return \"ledger\"\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    semantic_index.build(tmp_path, "test", _FakeProvider(),
                         db_path=tmp_path / _DB, vector_path=tmp_path / _VEC)
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, **kwargs)


def _fused(repo: Path, **kwargs):
    return _search(repo, semantic=True, provider=_FakeProvider(),
                   vector_path=repo / _VEC, **kwargs)


class TestFusionIsTiedToSemantic:
    def test_there_is_no_standalone_fuse_switch(self, repo: Path) -> None:
        """語彙経路だけの統合は逐次 fallback と 56/56 問で同順位だった（実測）。"""
        with pytest.raises(TypeError):
            _search(repo, query="ledger", fuse=True)

    def test_a_plain_search_records_no_activity(self, repo: Path) -> None:
        _search(repo, query="ledger")
        assert search.last_activity() is None

    def test_semantic_turns_the_fusion_on(self, repo: Path) -> None:
        _fused(repo, query="ledger", top_k=10)
        activity = search.last_activity()
        assert activity is not None
        assert "semantic" in {entry["route"] for entry in activity["routes"]}


class TestFusedExecution:
    def test_fusion_reaches_hits_that_the_sequential_chain_never_runs(
        self, repo: Path
    ) -> None:
        """逐次 fallback は `symbol` が当たった時点で止まるため後続経路を見ない。"""
        sequential = {h.path for h in _search(repo, query="ledger")}
        fused = {h.path for h in _fused(repo, query="ledger", top_k=10)}
        assert sequential < fused

    def test_every_route_contributes_to_one_ranked_list(self, repo: Path) -> None:
        hits = _fused(repo, query="ledger", top_k=10)
        assert {h.route for h in hits} >= {"symbol", "path"}

    def test_the_same_location_is_reported_once(self, repo: Path) -> None:
        keys = [(h.path, tuple(h.lines)) for h in _fused(repo, query="ledger", top_k=10)]
        assert len(keys) == len(set(keys))

    def test_ranking_is_deterministic(self, repo: Path) -> None:
        first = [(h.path, h.lines, round(h.score, 6))
                 for h in _fused(repo, query="ledger", top_k=10)]
        second = [(h.path, h.lines, round(h.score, 6))
                  for h in _fused(repo, query="ledger", top_k=10)]
        assert first == second

    def test_top_k_is_respected(self, repo: Path) -> None:
        assert len(_fused(repo, query="ledger", top_k=2)) <= 2

    def test_scores_are_ordered_descending(self, repo: Path) -> None:
        scores = [h.score for h in _fused(repo, query="ledger", top_k=10)]
        assert scores == sorted(scores, reverse=True)

    def test_an_explicit_mode_still_runs_a_single_route(self, repo: Path) -> None:
        """`--mode` は「単一経路の明示指定」なので融合の対象外にする。"""
        assert {h.route for h in _fused(repo, query="ledger", mode="symbol", top_k=10)} \
            == {"symbol"}

    def test_a_literal_match_still_wins(self, repo: Path) -> None:
        """リテラル一致の経路を近似一致と同列に融合すると順位が壊れる。

        実測（golden 56 問）: 全経路を等価に融合すると `symbol` intent の top-1 が
        1.00 → 0.77、`substr` が 1.00 → 0.57 へ退行した。問いの文字列そのものを
        含む場所は 1 経路しか返さないので、順位の逆数和では構造的に不利になる。
        """
        assert _fused(repo, query="ledger", top_k=10)[0].route == "symbol"

    def test_literal_hits_keep_their_own_order(self, repo: Path) -> None:
        literal = _search(repo, query="ledger", mode="symbol", top_k=10)
        fused = _fused(repo, query="ledger", top_k=10)
        assert [h.path for h in fused][: len(literal)] == [h.path for h in literal]

    def test_a_nonsense_query_still_returns_nearest_neighbours(self, repo: Path) -> None:
        """コサインには閾値が無いので、意味検索は常に最近傍を返す。

        語彙経路は 0 件を返すが、`--semantic` を付けると何かは必ず返る。
        この差を知らないと「ヒットしたから関連がある」と誤読する。
        """
        assert _search(repo, query="qqqzzz_absent_token") == []
        assert _fused(repo, query="qqqzzz_absent_token") != []

    def test_regex_is_not_fused_with_text_routes(self, repo: Path) -> None:
        """正規表現は他経路と入力が違うので、融合対象にすると意味が変わる。"""
        assert {h.route for h in _fused(repo, regex=r"def ledger\(", top_k=10)} \
            == {"regex"}
