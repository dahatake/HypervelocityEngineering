"""Contracts for the token-budgeted repository map (FR-CQ-09)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cq import config, indexer, repomap

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text(
        "def popular():\n    return 1\n\n\ndef lonely():\n    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "caller.py").write_text(
        "from pkg import core\n"
        "\n"
        "\n"
        "def one():\n    return core.popular()\n"
        "\n"
        "\n"
        "def two():\n    return core.popular()\n"
        "\n"
        "\n"
        "def three():\n    return core.popular()\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite")
    return tmp_path


def _db(repo: Path) -> Path:
    return repo / ".cq" / "index-test.sqlite"


class TestRanking:
    def test_most_referenced_symbol_comes_first(self, repo: Path) -> None:
        entries = repomap.build(_db(repo), max_tokens=4000).entries
        names = [e.name for e in entries if e.path == "pkg/core.py"]
        assert names[0] == "popular"

    def test_reference_counts_are_reported(self, repo: Path) -> None:
        entries = repomap.build(_db(repo), max_tokens=4000).entries
        popular = next(e for e in entries if e.name == "popular")
        assert popular.callers == 3
        lonely = next(e for e in entries if e.name == "lonely")
        assert lonely.callers == 0

    def test_same_file_references_do_not_count(self, repo: Path) -> None:
        """自ファイル内の呼び出しは「コードベースから参照されている」証拠にならない。"""
        (repo / "pkg" / "solo.py").write_text(
            "def helper():\n    return 1\n\n\ndef a():\n    return helper()\n"
            "\n\ndef b():\n    return helper()\n",
            encoding="utf-8",
        )
        profile = config.resolve_profile(repo, "test")
        indexer.build_index(repo, profile, db_path=_db(repo))
        entries = repomap.build(_db(repo), max_tokens=8000).entries
        helper = next(e for e in entries if e.name == "helper")
        assert helper.callers == 0

    def test_common_names_are_damped_by_definition_count(self, repo: Path) -> None:
        """`get` のような汎用名が名前衝突だけで上位に来ないこと。"""
        for index in range(5):
            (repo / "pkg" / f"dup{index}.py").write_text(
                "class Holder:\n    def get(self):\n        return 1\n", encoding="utf-8"
            )
        (repo / "pkg" / "users.py").write_text(
            "from pkg import dup0\n\n\ndef use():\n    return dup0.Holder().get()\n",
            encoding="utf-8",
        )
        profile = config.resolve_profile(repo, "test")
        indexer.build_index(repo, profile, db_path=_db(repo))
        entries = {e.name: e for e in repomap.build(_db(repo), max_tokens=8000).entries}
        assert entries["get"].score < entries["popular"].score

    def test_test_code_is_excluded(self, repo: Path) -> None:
        (repo / "pkg" / "tests").mkdir()
        (repo / "pkg" / "tests" / "helpers.py").write_text(
            "def only_for_tests():\n    return 1\n", encoding="utf-8"
        )
        profile = config.resolve_profile(repo, "test")
        indexer.build_index(repo, profile, db_path=_db(repo))
        entries = repomap.build(_db(repo), max_tokens=8000).entries
        assert "only_for_tests" not in {e.name for e in entries}

    def test_paths_filter_narrows_the_map(self, repo: Path) -> None:
        entries = repomap.build(_db(repo), max_tokens=4000, paths="pkg/core.py").entries
        assert {e.path for e in entries} == {"pkg/core.py"}


class TestBudget:
    def test_output_stays_within_the_budget(self, repo: Path) -> None:
        result = repomap.build(_db(repo), max_tokens=40)
        assert result.tokens <= 40

    def test_dropped_count_is_reported(self, repo: Path) -> None:
        full = repomap.build(_db(repo), max_tokens=4000)
        tight = repomap.build(_db(repo), max_tokens=40)
        assert tight.dropped == len(full.entries) - len(tight.entries)
        assert tight.dropped > 0

    def test_lowest_ranked_symbols_are_dropped_first(self, repo: Path) -> None:
        tight = repomap.build(_db(repo), max_tokens=40)
        assert "lonely" not in {e.name for e in tight.entries}

    def test_nothing_is_dropped_when_the_budget_is_ample(self, repo: Path) -> None:
        assert repomap.build(_db(repo), max_tokens=4000).dropped == 0


class TestRendering:
    def test_bodies_are_never_included(self, repo: Path) -> None:
        text = repomap.render(repomap.build(_db(repo), max_tokens=4000))
        assert "return 1" not in text
        assert "return core.popular()" not in text

    def test_definition_lines_are_included(self, repo: Path) -> None:
        text = repomap.render(repomap.build(_db(repo), max_tokens=4000))
        assert "def popular()" in text
        assert "pkg/core.py" in text

    def test_dropped_count_is_rendered(self, repo: Path) -> None:
        text = repomap.render(repomap.build(_db(repo), max_tokens=40))
        assert "dropped" in text

    def test_rendering_is_deterministic(self, repo: Path) -> None:
        first = repomap.render(repomap.build(_db(repo), max_tokens=4000))
        second = repomap.render(repomap.build(_db(repo), max_tokens=4000))
        assert first == second


class TestCli:
    def test_map_command_renders_text(self, repo: Path, capsys) -> None:
        from cq import cli

        code = cli.main([
            "map", "--profile", "test", "--repo-root", str(repo),
            "--db", str(_db(repo)), "--max-tokens", "4000",
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "def popular()" in out
        assert "return 1" not in out

    def test_map_command_supports_json(self, repo: Path, capsys) -> None:
        from cq import cli

        code = cli.main([
            "map", "--profile", "test", "--repo-root", str(repo),
            "--db", str(_db(repo)), "--max-tokens", "4000", "--format", "json",
        ])
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["dropped"] == 0
        assert any(e["name"] == "popular" for e in payload["entries"])

    def test_non_ascii_output_survives_redirection(self, repo: Path, tmp_path: Path) -> None:
        """Windows の cp932 既定でも折り畳み記号・日本語を出力できること。"""
        (repo / "pkg" / "jp.py").write_text(
            'def 日本語関数():\n    """日本語の説明。"""\n    return 1\n', encoding="utf-8"
        )
        profile = config.resolve_profile(repo, "test")
        indexer.build_index(repo, profile, db_path=_db(repo))
        target = tmp_path / "out.txt"
        env = dict(os.environ)
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)
        with target.open("wb") as handle:
            completed = subprocess.run(
                [sys.executable, "-m", "cq", "map", "--profile", "test",
                 "--repo-root", str(repo), "--db", str(_db(repo)), "--max-tokens", "4000"],
                stdout=handle, stderr=subprocess.PIPE, cwd=REPO_ROOT, env=env,
            )
        assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
        assert repomap.FOLD_MARKER in target.read_text(encoding="utf-8")
