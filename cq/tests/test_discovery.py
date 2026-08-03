"""Contracts for cq file discovery and exclusion rules (FR-CQ-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cq import config, discovery


def _profile(**kwargs) -> config.Profile:
    defaults = dict(
        name="test",
        roots=("pkg/",),
        exclude=config.BUILTIN_EXCLUDES,
        max_file_bytes=1024,
    )
    defaults.update(kwargs)
    return config.Profile(**defaults)


def _seed(root: Path, rel: str, size: int = 10) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x" * size, encoding="utf-8")


class TestEnumerationSource:
    def test_default_lister_uses_git_tracked_and_unignored_files(self) -> None:
        """ignore 設定を迂回する独自走査を持たない（FR-CQ-03）。"""
        assert discovery.GIT_LIST_COMMAND == (
            "git", "ls-files", "--cached", "--others", "--exclude-standard",
        )

    def test_only_files_under_the_profile_roots_are_kept(self, tmp_path: Path) -> None:
        for rel in ("pkg/a.py", "other/b.py"):
            _seed(tmp_path, rel)
        found = discovery.iter_files(
            tmp_path, _profile(), lister=lambda _: ("pkg/a.py", "other/b.py")
        )
        assert [f.path for f in found] == ["pkg/a.py"]

    def test_only_known_source_extensions_are_kept(self, tmp_path: Path) -> None:
        for rel in ("pkg/a.py", "pkg/readme.md", "pkg/data.csv", "pkg/x.cs"):
            _seed(tmp_path, rel)
        found = discovery.iter_files(
            tmp_path, _profile(),
            lister=lambda _: ("pkg/a.py", "pkg/readme.md", "pkg/data.csv", "pkg/x.cs"),
        )
        assert sorted(f.path for f in found) == ["pkg/a.py", "pkg/x.cs"]

    def test_markdown_and_tabular_files_are_never_indexed(self, tmp_path: Path) -> None:
        """FR-CQ-01: .md と CSV / TSV は mdq の担当。"""
        for rel in ("pkg/spec.md", "pkg/inventory.csv", "pkg/inventory.tsv"):
            _seed(tmp_path, rel)
        found = discovery.iter_files(
            tmp_path, _profile(),
            lister=lambda _: ("pkg/spec.md", "pkg/inventory.csv", "pkg/inventory.tsv"),
        )
        assert found == ()


class TestExclusions:
    @pytest.mark.parametrize("rel", [
        "pkg/vendor/lib/thing.js",
        "pkg/sub/vendor/thing.py",
        "pkg/bundle.min.js",
        "pkg/bundle.js.map",
    ])
    def test_vendored_and_generated_files_are_excluded(self, tmp_path: Path, rel: str) -> None:
        _seed(tmp_path, rel)
        assert discovery.iter_files(tmp_path, _profile(), lister=lambda _: (rel,)) == ()

    @pytest.mark.parametrize("rel", [
        "pkg/.env",
        "pkg/.env.production",
        "pkg/server.pem",
        "pkg/private.key",
        "pkg/cert.pfx",
        "pkg/id_rsa",
    ])
    def test_credential_bearing_files_are_excluded(self, tmp_path: Path, rel: str) -> None:
        _seed(tmp_path, rel)
        assert discovery.iter_files(tmp_path, _profile(), lister=lambda _: (rel,)) == ()

    def test_oversized_files_are_excluded(self, tmp_path: Path) -> None:
        _seed(tmp_path, "pkg/big.py", size=5000)
        _seed(tmp_path, "pkg/small.py", size=10)
        found = discovery.iter_files(
            tmp_path, _profile(max_file_bytes=1024),
            lister=lambda _: ("pkg/big.py", "pkg/small.py"),
        )
        assert [f.path for f in found] == ["pkg/small.py"]

    def test_declared_excludes_are_applied(self, tmp_path: Path) -> None:
        _seed(tmp_path, "pkg/i18n/messages.py")
        _seed(tmp_path, "pkg/app.py")
        profile = _profile(exclude=config.BUILTIN_EXCLUDES + ("pkg/i18n/**",))
        found = discovery.iter_files(
            tmp_path, profile, lister=lambda _: ("pkg/i18n/messages.py", "pkg/app.py")
        )
        assert [f.path for f in found] == ["pkg/app.py"]

    def test_unreadable_file_is_skipped_rather_than_indexed(self, tmp_path: Path) -> None:
        """判定に失敗したファイルは索引しない（fail-closed）。"""
        _seed(tmp_path, "pkg/a.py")
        found = discovery.iter_files(
            tmp_path, _profile(), lister=lambda _: ("pkg/a.py", "pkg/vanished.py")
        )
        assert [f.path for f in found] == ["pkg/a.py"]

    def test_unsafe_paths_are_skipped(self, tmp_path: Path) -> None:
        _seed(tmp_path, "pkg/a.py")
        found = discovery.iter_files(
            tmp_path, _profile(), lister=lambda _: ("pkg/a.py", "../escape.py", "/abs.py")
        )
        assert [f.path for f in found] == ["pkg/a.py"]


class TestExclusionPatterns:
    """拡張子 allowlist ではなく、除外パターン自体が働いていることを直接検証する。"""

    @pytest.mark.parametrize("rel", [
        "vendor/thing.js",
        "pkg/vendor/thing.js",
        "pkg/sub/vendor/deep/thing.js",
        "node_modules/lib/index.js",
        "pkg/bundle.min.js",
        ".env",
        "pkg/.env",
        ".env.production.js",
        "pkg/.env.local.js",
        "server.pem",
        "pkg/private.key",
        "id_rsa",
        "pkg/id_rsa.pub",
    ])
    def test_builtin_patterns_match(self, rel: str) -> None:
        assert discovery.is_excluded(rel, config.BUILTIN_EXCLUDES) is True

    @pytest.mark.parametrize("rel", [
        "pkg/app.js",
        "pkg/vendors.js",
        "pkg/environment.py",
        "pkg/keyring.py",
    ])
    def test_similar_names_are_not_excluded(self, rel: str) -> None:
        assert discovery.is_excluded(rel, config.BUILTIN_EXCLUDES) is False

    def test_matching_is_case_sensitive(self) -> None:
        """OS によって索引対象が変わらないこと（fnmatch の case-folding 回避）。"""
        assert discovery.is_excluded("pkg/BUNDLE.MIN.JS", ("*.min.js",)) is False
        assert discovery.is_excluded("pkg/bundle.min.js", ("*.min.js",)) is True

    def test_every_builtin_pattern_can_actually_fire(self) -> None:
        """拡張子 allowlist で先に落ちるため発火し得ないパターンを残さない。"""
        samples = {
            "**/vendor/**": "vendor/x.js",
            "**/node_modules/**": "node_modules/x.js",
            "*.min.js": "x.min.js",
            "**/.env": ".env",
            "**/.env.*": ".env.local.js",
            "*.pem": "x.pem",
            "*.key": "x.key",
            "*.pfx": "x.pfx",
            "*.p12": "x.p12",
            "**/id_rsa*": "id_rsa",
        }
        assert set(samples) == set(config.BUILTIN_EXCLUDES)
        for pattern, rel in samples.items():
            assert discovery.is_excluded(rel, (pattern,)) is True, pattern


class TestTestPathDetection:
    """検索と俯瞰マップが共有する単一判定（二重定義の禁止）。"""

    @pytest.mark.parametrize("path", [
        "hve/tests/test_x.py", "tests/smoke.py", "src/test/ui/a.js",
        "test/helper.js", "pkg/test_helpers.py", "src/test/api/SVC-02.Tests/X.cs",
        "pkg/thing_test.go", "src/app/a.test.js", "src/app/a.spec.js",
    ])
    def test_test_paths_are_flagged(self, path: str) -> None:
        assert _evaluate(path) == 1

    @pytest.mark.parametrize("path", [
        "hve/runner.py", "src/api/SVC-02/Program.cs", "cq/search.py",
        "src/app/latest.js", "pkg/contest.py",
    ])
    def test_implementation_paths_are_not_flagged(self, path: str) -> None:
        assert _evaluate(path) == 0

    def test_single_definition_is_reused_by_consumers(self) -> None:
        from cq import repomap, search

        expression = discovery.test_path_sql("x")
        assert search._test_rank("x") == expression
        assert repomap._test_path("x") == f"{expression} = 1"


def _evaluate(path: str) -> int:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t(p TEXT)")
        conn.execute("INSERT INTO t(p) VALUES (?)", (path,))
        return conn.execute(f"SELECT {discovery.test_path_sql('p')} FROM t").fetchone()[0]
    finally:
        conn.close()


class TestDiscoveredFile:
    def test_language_is_resolved_from_the_extension(self, tmp_path: Path) -> None:
        for rel, lang in (("pkg/a.py", "python"), ("pkg/b.cs", "csharp"), ("pkg/c.js", "javascript")):
            _seed(tmp_path, rel)
            found = discovery.iter_files(tmp_path, _profile(), lister=lambda _, r=rel: (r,))
            assert found[0].lang == lang

    def test_size_and_mtime_are_captured(self, tmp_path: Path) -> None:
        _seed(tmp_path, "pkg/a.py", size=42)
        found = discovery.iter_files(tmp_path, _profile(), lister=lambda _: ("pkg/a.py",))
        assert found[0].size_bytes == 42
        assert found[0].mtime > 0

    def test_results_are_deterministic(self, tmp_path: Path) -> None:
        for rel in ("pkg/b.py", "pkg/a.py"):
            _seed(tmp_path, rel)
        listed = ("pkg/b.py", "pkg/a.py")
        first = discovery.iter_files(tmp_path, _profile(), lister=lambda _: listed)
        second = discovery.iter_files(tmp_path, _profile(), lister=lambda _: listed)
        assert first == second
        assert [f.path for f in first] == ["pkg/a.py", "pkg/b.py"]
