"""FR-GUI-04: GUI から `cq` 索引を操作するサービス層の契約。

RED 先行。実装 (`hve/gui/cq_index_service.py`) は Sub-005 で追加する。

検証観点:
  (a) profile 一覧が `cq` の設定ファイル由来であること
  (b) 索引未生成時に索引ディレクトリ / DB を副作用で作らないこと
      （`mdq` 側で実際に起きた `.mdq/` 汚染バグと同型の回帰防止）
  (c) 設定不在・未知 profile で例外を送出せずエラー情報を返すこと
  (d) 索引構築 → 統計取得の往復が成立すること
  (e) DB パスが `cq.store.db_path_for` 由来であること
  (f) 検索プレビューが `cq.search.Hit.to_dict()` の形をそのまま返すこと
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cq import search as cq_search  # noqa: E402
from cq import store as cq_store  # noqa: E402
from cq.config import CONFIG_FILENAMES  # noqa: E402


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """`git ls-files` で列挙できる最小リポジトリを作る。"""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[index]\n"
        "max_file_bytes = 4096\n"
        "\n"
        "[profiles.main]\n"
        "roots = ['pkg']\n"
        "\n"
        "[profiles.extra]\n"
        "roots = ['other']\n"
        "exclude = ['other/skip/**']\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "def alpha():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "b.py").write_text(
        "class Beta:\n    pass\n", encoding="utf-8"
    )
    return tmp_path


class TestListProfiles:
    def test_profiles_come_from_the_config_file(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        result = cq_index_service.list_profiles(repo)

        assert result["error"] is None
        # 設定ファイルの宣言順を保持する（辞書順へ並べ替えない）。
        assert list(result["profiles"]) == ["main", "extra"]
        assert result["profiles"]["main"]["roots"] == ("pkg/",)
        assert result["profiles"]["main"]["max_file_bytes"] == 4096
        assert Path(result["config_path"]) == repo / "cq.toml"

    def test_declared_excludes_are_visible_alongside_builtin_ones(
        self, repo: Path
    ) -> None:
        from hve.gui import cq_index_service

        result = cq_index_service.list_profiles(repo)

        assert "other/skip/**" in result["profiles"]["extra"]["exclude"]

    def test_missing_config_is_reported_without_raising(self, tmp_path: Path) -> None:
        from hve.gui import cq_index_service

        result = cq_index_service.list_profiles(tmp_path)

        assert result["profiles"] == {}
        assert result["config_path"] is None
        assert isinstance(result["error"], str) and result["error"]
        assert result["config_candidates"] == [
            rel.as_posix() for rel in CONFIG_FILENAMES
        ]

    def test_missing_config_does_not_create_an_index_directory(
        self, tmp_path: Path
    ) -> None:
        from hve.gui import cq_index_service

        cq_index_service.list_profiles(tmp_path)

        assert list(tmp_path.iterdir()) == []


class TestStatsSideEffects:
    def test_stats_for_a_missing_index_creates_nothing(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        stats = cq_index_service.get_index_stats(repo, "main")

        assert stats["db_exists"] is False
        assert stats["files"] == 0
        assert stats["symbols"] == 0
        assert stats["chunks"] == 0
        assert stats["db_mtime"] == "未作成"
        assert not (repo / ".cq").exists(), (
            f"索引ディレクトリが副作用で作成された: {sorted(p.name for p in repo.iterdir())}"
        )

    def test_all_profile_stats_creates_nothing(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        result = cq_index_service.get_index_stats_all_profiles(repo)

        assert sorted(result) == ["extra", "main"]
        for name in ("extra", "main"):
            assert result[name]["db_exists"] is False
            assert result[name]["files"] == 0
        assert not (repo / ".cq").exists()

    def test_unknown_profile_is_reported_without_raising(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        stats = cq_index_service.get_index_stats(repo, "no-such-profile")

        assert isinstance(stats["error"], str) and stats["error"]
        assert stats["db_exists"] is False
        assert not (repo / ".cq").exists()


class TestBuildAndStats:
    def test_build_then_stats_roundtrip(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        report = cq_index_service.build(repo, "main", rebuild=False)

        assert report["indexed"] == 1
        assert report["symbols"] >= 1
        assert report["elapsed_ms"] >= 0
        assert report["error"] is None

        stats = cq_index_service.get_index_stats(repo, "main")
        assert stats["db_exists"] is True
        assert stats["files"] == 1
        assert stats["symbols"] >= 1
        assert stats["chunks"] >= 1
        assert stats["schema_version"] == cq_store.SCHEMA_VERSION
        assert stats["by_parser"].get("ast") == 1
        assert stats["db_mtime"] != "未作成"

    def test_second_build_skips_unchanged_files(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        cq_index_service.build(repo, "main", rebuild=False)
        report = cq_index_service.build(repo, "main", rebuild=False)

        assert report["indexed"] == 0
        assert report["skipped"] == 1

    def test_build_on_missing_config_is_reported_without_raising(
        self, tmp_path: Path
    ) -> None:
        from hve.gui import cq_index_service

        report = cq_index_service.build(tmp_path, "main", rebuild=False)

        assert isinstance(report["error"], str) and report["error"]
        assert report["indexed"] == 0
        assert not (tmp_path / ".cq").exists()

    def test_db_path_is_resolved_by_cq_store(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        stats = cq_index_service.get_index_stats(repo, "main")

        assert Path(stats["db_path"]) == (repo / cq_store.db_path_for("main")).resolve()

    def test_delete_removes_the_index_database(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        cq_index_service.build(repo, "main", rebuild=False)
        db = (repo / cq_store.db_path_for("main")).resolve()
        assert db.exists()

        removed = cq_index_service.delete_index_db(repo, "main")

        assert str(db) in removed
        assert not db.exists()
        assert cq_index_service.get_index_stats(repo, "main")["db_exists"] is False

    def test_delete_on_a_missing_database_is_a_no_op(self, repo: Path) -> None:
        from hve.gui import cq_index_service

        assert cq_index_service.delete_index_db(repo, "main") == []


class TestSearchPreview:
    def test_preview_returns_cq_hit_payloads(self, repo: Path) -> None:
        """ヒットは `cq.search.Hit.to_dict()` の形のまま返す（第2スキーマを作らない）。"""
        from hve.gui import cq_index_service

        cq_index_service.build(repo, "main", rebuild=False)
        result = cq_index_service.search_preview(repo, "main", "alpha", top_k=3)

        assert result["error"] is None
        assert result["hits"], "既知シンボルの検索で 0 件になった"
        first = result["hits"][0]
        assert first["path"] == "pkg/a.py"
        assert first["lines"][0] <= first["lines"][1]
        assert first["route"] in cq_search.ROUTES

    def test_preview_without_an_index_is_reported_without_raising(
        self, repo: Path
    ) -> None:
        from hve.gui import cq_index_service

        result = cq_index_service.search_preview(repo, "main", "alpha", top_k=3)

        assert result["hits"] == []
        assert isinstance(result["error"], str) and result["error"]
