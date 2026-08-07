"""FR-GUI-04 / FR-MAINT-07: 索引統計集計の単一実装契約。

統計集計は `cq/cli.py` の private 関数にだけ存在していたため、GUI から
再利用すると同一ルールが 2 面に生まれる。集計は `cq.store.index_stats` を
単一実装とし、CLI はそれを呼ぶだけであることを検証する。
"""

from __future__ import annotations

import json
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import cli, config, indexer, store


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "def alpha():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "b.py").write_text(
        "class Beta:\n    def run(self):\n        return 2\n", encoding="utf-8"
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=_db(tmp_path))
    return tmp_path


def _db(repo: Path) -> Path:
    return repo / ".cq" / "index-test.sqlite"


@pytest.fixture()
def polyglot_repo(tmp_path: Path) -> Path:
    """C# と Java はどちらも `tree-sitter` パーサだから、パーサ別集計では区別できない。"""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "def alpha():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "b.cs").write_text(
        "class Beta\n{\n    void Run()\n    {\n    }\n}\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "c.java").write_text(
        "class Gamma {\n    void run() {\n    }\n}\n", encoding="utf-8"
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=_db(tmp_path))
    return tmp_path


class TestIndexStats:
    def test_reports_every_table_and_the_schema_version(self, repo: Path) -> None:
        report = store.index_stats(_db(repo))

        for table in store.STATS_TABLES:
            assert isinstance(report[table], int)
        assert report["files"] == 2
        assert report["symbols"] == 3
        assert report["chunks"] > 0
        assert report["schema_version"] == store.SCHEMA_VERSION
        assert report["by_parser"] == {"ast": 2}
        assert report["db"] == str(_db(repo))

    def test_missing_index_raises_instead_of_reporting_zero(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(store.StoreError):
            store.index_stats(tmp_path / ".cq" / "absent.sqlite")

        assert not (tmp_path / ".cq").exists()

    def test_every_counted_table_exists_in_the_schema(self, repo: Path) -> None:
        """集計対象名と実スキーマのさらしを検出する。"""
        with closing(store.open_store(_db(repo), create=False)) as conn:
            actual = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

        assert set(store.STATS_TABLES) <= actual


class TestCliDelegates:
    def test_cli_output_equals_the_single_implementation(
        self, repo: Path, capsys
    ) -> None:
        assert cli.main([
            "stats", "--profile", "test", "--repo-root", str(repo),
            "--db", str(_db(repo)),
        ]) == 0
        emitted = json.loads(capsys.readouterr().out)

        assert emitted == store.index_stats(_db(repo))

    def test_cli_has_no_private_stats_implementation(self) -> None:
        assert not hasattr(cli, "_stats"), (
            "cq/cli.py に統計集計の第2実装が残っている（FR-MAINT-07）"
        )


class TestLanguageBreakdown:
    """FR-CQ-15: パーサ別集計だけでは言語ごとのフィデリティを判別できない。"""

    def test_reports_a_language_breakdown(self, polyglot_repo: Path) -> None:
        report = store.index_stats(_db(polyglot_repo))

        python = report["by_lang"]["python"]
        assert python["files"] == 1
        assert python["symbols"] == 1
        assert python["chunks"] >= 1
        assert python["by_parser"] == {"ast": 1}

    def test_separates_languages_that_share_a_parser(
        self, polyglot_repo: Path
    ) -> None:
        report = store.index_stats(_db(polyglot_repo))

        assert report["by_parser"]["tree-sitter"] == 2
        assert report["by_lang"]["csharp"]["by_parser"] == {"tree-sitter": 1}
        assert report["by_lang"]["java"]["by_parser"] == {"tree-sitter": 1}

    def test_language_totals_match_the_overall_totals(
        self, polyglot_repo: Path
    ) -> None:
        """言語別の合計が全体合計と一致しない場合、集計が行を重複または欠落させている。"""
        report = store.index_stats(_db(polyglot_repo))

        for key in ("files", "symbols", "chunks"):
            assert sum(
                entry[key] for entry in report["by_lang"].values()
            ) == report[key], key

    def test_uses_the_indexed_language_without_reclassifying(
        self, polyglot_repo: Path
    ) -> None:
        """統計側で拡張子から言語を再判定してはならない。"""
        with closing(store.open_store(_db(polyglot_repo), create=False)) as conn:
            conn.execute(
                "UPDATE files SET lang = 'renamed' WHERE path = 'pkg/a.py'"
            )
            conn.commit()

        report = store.index_stats(_db(polyglot_repo))

        assert "renamed" in report["by_lang"]
        assert "python" not in report["by_lang"]
