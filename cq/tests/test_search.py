"""Contracts for cq search, query routing and the CLI (FR-CQ-06 / NFR-CQ-01)."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from cq import cli, config, indexer, search

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SOURCES = (REPO_ROOT / "cq" / "__main__.py", REPO_ROOT / "cq" / "cli.py")
HEAVY_MODULES = {"tiktoken", "rank_bm25", "tree_sitter", "watchdog", "numpy", "fastembed"}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        'HEADER = "x-ms-version"\n'
        "\n"
        "\n"
        "def resolveUserProfile(member_id):\n"
        '    """Return the stored profile for a member."""\n'
        "    return {HEADER: member_id}\n"
        "\n"
        "\n"
        "class LedgerService:\n"
        "    def grant_points(self, amount):\n"
        "        return amount\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "other.py").write_text(
        "def unrelated():\n    return 0\n", encoding="utf-8"
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite")
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / ".cq" / "index-test.sqlite", **kwargs)


class TestRouting:
    def test_exact_symbol_wins(self, repo: Path) -> None:
        hits = _search(repo, query="grant_points")
        assert hits[0].route == "symbol"
        assert hits[0].path == "pkg/service.py"
        assert hits[0].lines == [10, 11]

    def test_punctuated_query_uses_the_substring_layer(self, repo: Path) -> None:
        hits = _search(repo, query="x-ms-version")
        assert hits[0].route == "substr"
        assert hits[0].path == "pkg/service.py"

    def test_natural_language_uses_bm25(self, repo: Path) -> None:
        hits = _search(repo, query="stored profile for a member")
        assert hits[0].route == "bm25"
        assert hits[0].path == "pkg/service.py"

    def test_split_words_reach_a_camel_case_identifier(self, repo: Path) -> None:
        hits = _search(repo, query="resolve user profile")
        assert hits
        assert hits[0].path == "pkg/service.py"

    def test_regex_mode_is_two_stage(self, repo: Path) -> None:
        hits = _search(repo, regex=r"^def resolve\w+")
        assert hits[0].route == "regex"
        assert hits[0].lines == [4, 4]

    def test_route_is_reported_on_every_hit(self, repo: Path) -> None:
        for hit in _search(repo, query="grant_points"):
            assert hit.route in search.ROUTES

    def test_explicit_mode_overrides_routing(self, repo: Path) -> None:
        hits = _search(repo, query="profile", mode="substr")
        assert all(h.route == "substr" for h in hits)

    def test_zero_hits_fall_back_to_another_layer(self, repo: Path) -> None:
        hits = _search(repo, query="HEADER")
        assert hits
        assert hits[0].route in {"symbol", "substr", "bm25"}

    def test_unknown_term_returns_no_hits(self, repo: Path) -> None:
        assert _search(repo, query="zzzznotpresentzzzz") == []


class TestSanitisation:
    def test_phrase_query_does_not_crash_the_ranking_layer(self, repo: Path) -> None:
        """`detail=column` ではフレーズが実行時エラーになるため送出してはならない。"""
        hits = _search(repo, query='"stored profile"', mode="bm25")
        assert isinstance(hits, list)

    @pytest.mark.parametrize("query", ["def f(", "a AND", "*", "NEAR(", "()", "x:y"])
    def test_fts_metacharacters_are_neutralised(self, repo: Path, query: str) -> None:
        assert isinstance(_search(repo, query=query), list)

    def test_short_substring_query_is_rejected(self, repo: Path) -> None:
        """trigram は 3 文字未満で索引を迂回して全走査になるため fail-closed。"""
        with pytest.raises(search.SearchError, match="at least 3"):
            _search(repo, query="ab", mode="substr")


class TestSymbolMatchQuality:
    """完全一致とフォールバックを呼び出し側が区別できること。"""

    def test_exact_qualname_is_marked_and_scored_one(self, repo: Path) -> None:
        hit = _search(repo, query="LedgerService.grant_points", mode="symbol")[0]
        assert hit.qualname == "LedgerService.grant_points"
        assert hit.extra["match"] == "qualname"
        assert hit.score == 1.0

    def test_name_fallback_is_marked_and_demoted(self, repo: Path) -> None:
        """存在しない qualname は末尾名で再探索されるが、完全一致と同じ顔をしてはならない。"""
        hits = _search(repo, query="NoSuchClass.grant_points", mode="symbol")
        assert hits
        assert hits[0].extra["match"] == "name-fallback"
        assert hits[0].score < 1.0


class TestRegexGuards:
    def test_invalid_regex_is_reported(self, repo: Path) -> None:
        with pytest.raises(search.SearchError, match="regex"):
            _search(repo, regex="([")

    def test_candidate_limit_is_reported(self, repo: Path) -> None:
        hits = _search(repo, regex=r"\w+", regex_max_candidates=1)
        assert any(h.truncated for h in hits)


class TestOutputShape:
    def test_hits_carry_the_parser_fidelity(self, repo: Path) -> None:
        assert _search(repo, query="grant_points")[0].parser == "ast"

    def test_snippet_is_a_small_window(self, repo: Path) -> None:
        hit = _search(repo, query="stored profile for a member")[0]
        assert 0 < len(hit.snippet.splitlines()) <= 7

    def test_top_k_is_honoured(self, repo: Path) -> None:
        assert len(_search(repo, query="return", top_k=1)) <= 1

    def test_max_tokens_caps_the_response(self, repo: Path) -> None:
        hits = _search(repo, query="return", top_k=20, max_tokens=1)
        assert len(hits) <= 1

    def test_hit_is_json_serialisable(self, repo: Path) -> None:
        payload = json.dumps(_search(repo, query="grant_points")[0].to_dict())
        assert json.loads(payload)["path"] == "pkg/service.py"


class TestMissingIndex:
    def test_absent_index_is_an_error_not_zero_hits(self, tmp_path: Path) -> None:
        (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
        with pytest.raises(Exception) as excinfo:
            search.search(tmp_path, "test", query="x", db_path=tmp_path / ".cq" / "absent.sqlite")
        assert "cq index" in str(excinfo.value)


class TestCli:
    def test_json_output_is_pure_ascii(self, capsys) -> None:
        """cp932 等のコンソールでも文字化けしないよう、非 ASCII は \\uXXXX へ退避する。"""
        cli._emit_line({"snippet": "// 出典: docs/spec.md#FR-01"})
        out = capsys.readouterr().out
        assert out.isascii(), out
        assert json.loads(out)["snippet"] == "// 出典: docs/spec.md#FR-01"

    def test_search_emits_jsonl(self, repo: Path, capsys) -> None:
        code = cli.main([
            "search", "--q", "grant_points", "--profile", "test",
            "--repo-root", str(repo), "--db", str(repo / ".cq" / "index-test.sqlite"),
        ])
        assert code == 0
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
        assert lines and lines[0]["path"] == "pkg/service.py"
        assert lines[0]["route"] == "symbol"

    def test_def_returns_signature_without_the_body(self, repo: Path, capsys) -> None:
        code = cli.main([
            "def", "--symbol", "LedgerService.grant_points", "--profile", "test",
            "--repo-root", str(repo), "--db", str(repo / ".cq" / "index-test.sqlite"),
        ])
        assert code == 0
        row = json.loads(capsys.readouterr().out.splitlines()[0])
        assert row["signature"].startswith("def grant_points")
        assert "return amount" not in json.dumps(row)

    def test_get_returns_the_full_chunk(self, repo: Path, capsys) -> None:
        cli.main([
            "search", "--q", "grant_points", "--profile", "test",
            "--repo-root", str(repo), "--db", str(repo / ".cq" / "index-test.sqlite"),
        ])
        hit = json.loads(capsys.readouterr().out.splitlines()[0])
        code = cli.main([
            "get", "--chunk-id", hit["chunk_id"], "--profile", "test",
            "--repo-root", str(repo), "--db", str(repo / ".cq" / "index-test.sqlite"),
        ])
        assert code == 0
        assert "return amount" in capsys.readouterr().out

    def test_stats_reports_the_index(self, repo: Path, capsys) -> None:
        assert cli.main([
            "stats", "--profile", "test", "--repo-root", str(repo),
            "--db", str(repo / ".cq" / "index-test.sqlite"),
        ]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["files"] == 2
        assert report["symbols"] > 0

    def test_missing_index_exits_non_zero(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
        code = cli.main([
            "search", "--q", "x", "--profile", "test", "--repo-root", str(tmp_path),
            "--db", str(tmp_path / ".cq" / "absent.sqlite"),
        ])
        assert code != 0


class TestStartupCost:
    @pytest.mark.parametrize("source", CLI_SOURCES)
    def test_entrypoints_do_not_import_optional_dependencies(self, source: Path) -> None:
        """検索経路の起動コストを増やさない（NFR-CQ-01）。"""
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & HEAVY_MODULES), sorted(imported & HEAVY_MODULES)

    def test_search_module_does_not_load_the_whole_index(self) -> None:
        """ランキングは SQLite 内で完結させる（NFR-CQ-01）。"""
        source = (REPO_ROOT / "cq" / "search.py").read_text(encoding="utf-8")
        assert "ORDER BY rank" in source
        assert "SELECT * FROM chunks" not in source
