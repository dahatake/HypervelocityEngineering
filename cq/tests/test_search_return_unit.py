"""FR-CQ-06: 検索応答の返却単位を呼び出し側が選べること。

既定はヒット行を中心とする行範囲。チャンク単位を選ぶと、cAST が切り出した
構造チャンク（関数・クラス等）の本文全体を返す。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import cli, config, indexer, search

_MARKER = "returnunitmarker"
# ヒット行の前後に十分な行を持ち、行窓とチャンク全体が明確に異なる関数。
_LONG_FUNCTION = "\n".join(
    ["def long_operation(payload):"]
    + [f"    step_{i} = payload + {i}" for i in range(12)]
    + [f"    audit = '{_MARKER}'"]
    + [f"    tail_{i} = audit + str({i})" for i in range(12)]
    + ["    return audit"]
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        _LONG_FUNCTION + "\n\n\ndef short_helper():\n"
        f"    return '{_MARKER}'\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(
        tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite"
    )
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(
        repo, "test", db_path=repo / ".cq" / "index-test.sqlite", **kwargs
    )


def _long_hit(hits):
    match = next((h for h in hits if h.lines[0] == 1), None)
    assert match is not None, (
        f"long_operation のチャンク（行 1 始まり）が返らない: "
        f"{[(h.path, h.lines) for h in hits]}"
    )
    return match


def test_default_return_unit_is_a_line_window(repo: Path) -> None:
    hits = _search(repo, query="long_operation", max_tokens=100000)
    hit = _long_hit(hits)
    assert _MARKER not in hit.snippet, "既定でチャンク全体が返っている"
    assert len(hit.snippet.splitlines()) <= 2 * search.DEFAULT_SNIPPET_RADIUS + 1


def test_chunk_unit_returns_the_whole_chunk_body(repo: Path) -> None:
    hits = _search(
        repo, query="long_operation", max_tokens=100000, return_unit="chunk"
    )
    hit = _long_hit(hits)
    assert hit.snippet.startswith("def long_operation(payload):")
    assert _MARKER in hit.snippet
    assert hit.snippet.rstrip().endswith("return audit")


def test_ranking_is_unchanged_across_units(repo: Path) -> None:
    line = _search(repo, query=_MARKER, max_tokens=100000)
    chunk = _search(repo, query=_MARKER, max_tokens=100000, return_unit="chunk")
    assert [(h.path, h.lines, h.route) for h in line] == [
        (h.path, h.lines, h.route) for h in chunk
    ]
    assert [round(h.score, 6) for h in line] == [round(h.score, 6) for h in chunk]


def test_first_hit_survives_a_tiny_budget(repo: Path) -> None:
    hits = _search(repo, query=_MARKER, max_tokens=1, return_unit="chunk")
    assert len(hits) == 1


def test_chunk_unit_never_returns_more_hits_than_line_unit(repo: Path) -> None:
    line = _search(repo, query=_MARKER, max_tokens=60)
    chunk = _search(repo, query=_MARKER, max_tokens=60, return_unit="chunk")
    assert len(chunk) <= len(line)


def test_symbol_route_also_honours_the_chunk_unit(repo: Path) -> None:
    hits = _search(
        repo, query="long_operation", mode="symbol", max_tokens=100000,
        return_unit="chunk",
    )
    assert hits
    assert _MARKER in hits[0].snippet


def test_lines_describe_the_returned_excerpt(repo: Path) -> None:
    """`lines` は返した抜粋の範囲でなければならない（FR-CQ-06）。

    regex 経路は既定でマッチ行だけを `lines` に入れる。本文をチャンク全体へ
    広げたのに `lines` を据え置くと、消費側が抜粋の位置を誤認する。

    完全一致ではなく「抜粋より狭くない」ことを見る。`chunks.end_line` は
    末尾の空行の数え方でテキストの行数と 1 行ずれることがあり、それは
    チャンカ側の既存挙動で本テストの対象ではない。
    """
    hits = _search(
        repo, regex=_MARKER, max_tokens=100000, return_unit="chunk"
    )
    assert hits
    hit = hits[0]
    assert hit.route == "regex"
    assert hit.lines[0] < hit.lines[1], f"lines が単一行のまま: {hit.lines}"
    span = hit.lines[1] - hit.lines[0] + 1
    assert span >= len(hit.snippet.splitlines()), (
        f"lines={hit.lines} は抜粋 {len(hit.snippet.splitlines())} 行より狭い"
    )


def test_line_unit_keeps_the_regex_match_line(repo: Path) -> None:
    """既定では従来どおりマッチ行を指すこと（No.2 修正の巻き添え防止）。"""
    hits = _search(repo, regex=_MARKER, max_tokens=100000)
    assert hits
    assert hits[0].lines[0] == hits[0].lines[1]


def test_cli_exposes_return_unit_defaulting_to_line() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["search", "--q", "x"])
    assert args.return_unit == "line"
    args = parser.parse_args(["search", "--q", "x", "--return-unit", "chunk"])
    assert args.return_unit == "chunk"
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--q", "x", "--return-unit", "bogus"])


class TestSymbolUnit:
    """`symbol` 単位は本文を返さず、コードのメタ情報だけを返す（FR-CQ-17）。

    実測（golden 56 問 / top-3 / 既定経路）: 応答トークンの中央値が 159 → 66 へ
    落ち、`symbols` へ結合することで名前の付いたヒットが 31/80 → 62/80 になる。
    結合しないと 80 件中 49 件がパスと行番号だけになり、「関数名・引数名を返す」
    という用途を満たさない。
    """

    def test_the_cli_offers_the_symbol_unit(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["search", "--q", "x", "--return-unit", "symbol"])
        assert args.return_unit == "symbol"

    def test_no_body_is_returned(self, repo: Path) -> None:
        hits = _search(repo, query="long_operation", max_tokens=100000,
                       return_unit="symbol")
        assert hits
        assert all(h.snippet == "" for h in hits)
        assert all("snippet" not in h.to_dict() for h in hits)

    def test_the_symbol_name_and_signature_are_present(self, repo: Path) -> None:
        hits = _search(repo, query="long_operation", max_tokens=100000,
                       return_unit="symbol")
        payload = _long_hit(hits).to_dict()
        assert payload["qualname"] == "long_operation"
        assert payload["kind"] == "function"
        assert payload["signature"].startswith("def long_operation(payload)")

    def test_a_hit_without_a_symbol_still_returns_its_location(
        self, repo: Path
    ) -> None:
        """`symbols` に該当が無いチャンクもある。落とさず位置だけ返す。"""
        (repo / "pkg" / "settings.py").write_text(
            "SYMBOLLESS_MARKER = 1\nOTHER = 2\n", encoding="utf-8"
        )
        indexer.build_index(
            repo, config.resolve_profile(repo, "test"),
            db_path=repo / ".cq" / "index-test.sqlite",
        )
        hits = _search(repo, query="SYMBOLLESS_MARKER", max_tokens=100000,
                       return_unit="symbol")
        assert hits
        assert hits[0].path == "pkg/settings.py"
        assert hits[0].to_dict().get("qualname") is None

    def test_ranking_is_unchanged_across_units(self, repo: Path) -> None:
        line = _search(repo, query=_MARKER, max_tokens=100000)
        symbol = _search(repo, query=_MARKER, max_tokens=100000, return_unit="symbol")
        assert [(h.path, h.lines, h.route) for h in line] == [
            (h.path, h.lines, h.route) for h in symbol
        ]

    def test_it_costs_fewer_tokens_than_the_line_unit(self, repo: Path) -> None:
        import json

        line = _search(repo, query=_MARKER, max_tokens=100000)
        symbol = _search(repo, query=_MARKER, max_tokens=100000, return_unit="symbol")
        as_tokens = lambda hits: len(  # noqa: E731
            json.dumps([h.to_dict() for h in hits], ensure_ascii=True)
        )
        assert as_tokens(symbol) < as_tokens(line)
