"""FR-CQ-06: 自然文経路が 0 件のときの連言→選言の緩和（RED）。

BM25 の既定は語の連言（暗黙 AND）であり、語数が増えるほど 0 件になりやすい。
0 件のときに限り 1 回だけ選言へ緩和して再試行し、緩和で得たヒットは呼び出し側が
判別できる標識を持つ。ただし CJK を含むクエリでは緩和しない（誤った上位ヒットを
返すより 0 件を返すという既存方針の維持）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, search, store

_DB = Path(".cq") / "index-test.sqlite"


class _CountingConnection:
    """全文検索クエリの発行回数と MATCH 式を記録する薄い proxy。"""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.fts_matches: list[str] = []

    def execute(self, sql, params=()):
        if "chunks_fts MATCH" in sql:
            self.fts_matches.append(str(params[0]) if params else "")
        return self._inner.execute(sql, params)

    def close(self) -> None:
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture()
def fts_probe(monkeypatch):
    """`search` が開く接続を差し替えて MATCH 式の発行を観測する。"""
    seen: list[_CountingConnection] = []
    original = store.open_store

    def _open(path, *, create: bool = True):
        proxy = _CountingConnection(original(path, create=create))
        seen.append(proxy)
        return proxy

    monkeypatch.setattr(store, "open_store", _open)

    def matches() -> list[str]:
        return [m for conn in seen for m in conn.fts_matches]

    return matches


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    # 語が 2 つのチャンクへ分かれるので、4 語の連言はどのチャンクにも一致しない。
    (tmp_path / "pkg" / "alpha.py").write_text(
        'def compute_alpha_beta(payload):\n'
        '    """Alpha beta computation for the ledger."""\n'
        "    return payload\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "gamma.py").write_text(
        'def compute_gamma_delta(payload):\n'
        '    """Gamma delta computation for the ledger."""\n'
        "    return payload\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, **kwargs)


def test_conjunction_that_matches_nothing_is_retried_as_disjunction(repo: Path) -> None:
    """4 語の連言はどのチャンクにも一致しないが、選言なら到達できる。"""
    hits = _search(repo, query="alpha beta gamma delta")
    assert hits, "緩和されていないため 0 件のままになっている"
    assert {h.path for h in hits} == {"pkg/alpha.py", "pkg/gamma.py"}
    assert all(h.route == "bm25" for h in hits)


def test_relaxed_hits_carry_a_machine_readable_marker(repo: Path) -> None:
    hits = _search(repo, query="alpha beta gamma delta")
    assert hits
    assert all(h.to_dict().get("match") == "or-fallback" for h in hits)


def test_conjunction_hit_is_not_relaxed(repo: Path) -> None:
    """連言で引けるクエリは緩和経路へ入らない（無駄な再試行をしない）。"""
    hits = _search(repo, query="alpha beta")
    assert hits
    assert hits[0].path == "pkg/alpha.py"
    assert all("match" not in h.to_dict() for h in hits)


def test_single_term_query_is_not_relaxed(repo: Path) -> None:
    """語が 1 つなら連言と選言が同義なので再試行しない。"""
    hits = _search(repo, query="zzunmatchedterm")
    assert hits == []


def test_query_with_cjk_is_not_relaxed(repo: Path) -> None:
    """選言なら到達できるが、CJK を含むクエリでは 0 件を維持する。"""
    hits = _search(repo, query="検索 alpha gamma")
    assert hits == [], f"CJK クエリが緩和されている: {[(h.path, h.route) for h in hits]}"


@pytest.mark.parametrize(
    "query",
    [
        "検索 alpha gamma",      # 漢字
        "あ alpha gamma",         # ひらがな
        "カ alpha gamma",         # カタカナ
        "검색 alpha gamma",       # ハングル
    ],
)
def test_cjk_detection_covers_the_scripts_named_by_the_requirement(
    repo: Path, query: str
) -> None:
    assert _search(repo, query=query) == []


def test_disjunction_that_still_matches_nothing_terminates(repo: Path) -> None:
    """緩和しても 0 件なら、そこで終了する（再試行は 1 回まで）。"""
    hits = _search(repo, query="zzunmatched yyunmatched")
    assert hits == []


class TestQueryCount:
    """緩和の有無を、全文検索クエリの発行回数そのもので検証する。"""

    def test_relaxation_issues_exactly_two_queries(self, repo: Path, fts_probe) -> None:
        _search(repo, query="alpha beta gamma delta", auto_reindex_limit=-1)
        matches = fts_probe()
        assert len(matches) == 2, f"連言 1 回 + 選言 1 回のはずが {matches}"
        assert " OR " not in matches[0]
        assert " OR " in matches[1]

    def test_conjunction_hit_issues_only_one_query(self, repo: Path, fts_probe) -> None:
        _search(repo, query="alpha beta", auto_reindex_limit=-1)
        matches = fts_probe()
        assert len(matches) == 1, f"連言で引けたのに再試行している: {matches}"

    def test_single_term_issues_only_one_query(self, repo: Path, fts_probe) -> None:
        _search(repo, query="zzunmatchedterm", auto_reindex_limit=-1)
        matches = fts_probe()
        assert len(matches) == 1, f"1 語なのに再試行している: {matches}"

    def test_cjk_query_issues_only_one_query(self, repo: Path, fts_probe) -> None:
        _search(repo, query="検索 alpha gamma", auto_reindex_limit=-1)
        matches = fts_probe()
        assert len(matches) == 1, f"CJK クエリで再試行している: {matches}"

    def test_relaxation_that_matches_nothing_stops_at_two(
        self, repo: Path, fts_probe
    ) -> None:
        _search(repo, query="zzunmatched yyunmatched", auto_reindex_limit=-1)
        matches = fts_probe()
        assert len(matches) == 2, f"再試行が 1 回を超えている: {matches}"
