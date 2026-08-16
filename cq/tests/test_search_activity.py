"""FR-CQ-16: 融合検索の実行内訳（activity log）と CLI 配線。

Azure AI Search の Agentic Retrieval が「どのサブクエリをどの知識源へ投げ、何件
返ったか」を activity log として任意で返すのと同じ情報を、ローカルでも出せるように
する。既定の応答は 800 token 予算なので、常時ではなく `--explain` 指定時だけ
最終行へ 1 行で出す。

統合は `--semantic` を付けたときにだけ起きるので、実行内訳もそのときだけ残る。
"""

from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from cq import cli, config, indexer, search, semantic_index

_DB = Path(".cq") / "index-test.sqlite"
_VEC = Path(".cq") / "vectors-test.sqlite"


class _FakeProvider:
    model = "fake"
    vocabulary = ("ledger", "posting", "audit")

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
    (tmp_path / "pkg" / "ledger.py").write_text(
        "def ledger(amount):\n"
        "    \"\"\"Exact symbol match lives here.\"\"\"\n"
        "    return amount\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "posting.py").write_text(
        "def post_entry(amount):\n"
        "    \"\"\"The ledger keeps every posting for audit.\"\"\"\n"
        "    return amount\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    semantic_index.build(tmp_path, "test", _FakeProvider(),
                         db_path=tmp_path / _DB, vector_path=tmp_path / _VEC)
    return tmp_path


def _fused(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, semantic=True,
                         provider=_FakeProvider(), vector_path=repo / _VEC, **kwargs)


def _run_cli(repo: Path, *argv: str) -> list[dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main([
            *argv, "--profile", "test",
            "--repo-root", str(repo), "--db", str(repo / _DB),
        ])
    assert code == 0, buffer.getvalue()
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


@pytest.fixture()
def fake_provider(monkeypatch):
    """CLI 経由では provider を渡せないので差し替える。

    差し替えないと実モデル（240 MiB）をロードし、テストが遅くなるうえに
    fastembed の導入状態とベクトルのモデル名に依存してしまう。
    """
    from cq import embeddings

    monkeypatch.setattr(embeddings, "get_provider", lambda *a, **k: _FakeProvider())
    monkeypatch.setattr(
        "cq.vectors.db_path_for", lambda profile: Path(".cq") / "vectors-test.sqlite"
    )


class TestActivityRecord:
    def test_a_plain_search_records_no_activity(self, repo: Path) -> None:
        search.search(repo, "test", query="ledger", db_path=repo / _DB)
        assert search.last_activity() is None

    def test_a_fused_search_records_every_route_it_ran(self, repo: Path) -> None:
        _fused(repo, query="ledger")
        activity = search.last_activity()
        assert activity is not None
        assert [entry["route"] for entry in activity["routes"]] == [
            "symbol", "substr", "bm25", "path", "semantic"
        ]
        assert all(isinstance(entry["hits"], int) for entry in activity["routes"])

    def test_the_counts_cover_the_returned_hits(self, repo: Path) -> None:
        """リテラル一致は融合を通さず先頭へ置くので、内訳も分かれる。"""
        hits = _fused(repo, query="ledger", top_k=50)
        activity = search.last_activity()
        assert activity["literal"] + activity["merged"] >= len(hits)
        assert activity["literal"] >= 1


class TestExplainFlag:
    def test_explain_appends_the_activity_as_the_last_line(
        self, repo: Path, fake_provider
    ) -> None:
        lines = _run_cli(repo, "search", "--q", "ledger", "--semantic", "--explain")
        assert "routes" in lines[-1]
        assert lines[-1]["literal"] + lines[-1]["merged"] >= 1

    def test_without_explain_the_activity_is_not_printed(
        self, repo: Path, fake_provider
    ) -> None:
        lines = _run_cli(repo, "search", "--q", "ledger", "--semantic")
        assert all("routes" not in line for line in lines)

    def test_explain_without_semantic_prints_nothing_extra(self, repo: Path) -> None:
        """統合が起きない検索には内訳が無い。"""
        lines = _run_cli(repo, "search", "--q", "ledger", "--explain")
        assert all("routes" not in line for line in lines)

    def test_the_fuse_flag_no_longer_exists(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            _run_cli(repo, "search", "--q", "ledger", "--fuse")
