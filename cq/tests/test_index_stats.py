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
