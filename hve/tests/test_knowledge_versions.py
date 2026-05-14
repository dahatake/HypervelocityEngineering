"""test_knowledge_versions.py — knowledge_versions モジュールのテスト。

B4-1: knowledge 参照ファイルの SHA 収集ロジック
B4-2: 更新なし明示ロジック
B4-3: body / prompt / 生成指示への埋め込み
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_versions import (
    build_knowledge_reference_log_lines,
    build_knowledge_reference_section,
    collect_knowledge_file_shas,
    resolve_knowledge_paths_for_step,
)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "ci@example.com")
    _git(repo_root, "config", "user.name", "CI")


def _make_step(consumed_artifacts=None):
    """テスト用の簡易 StepDef を生成する。"""
    class FakeStep:
        def __init__(self, ca):
            self.id = "1.1"
            self.consumed_artifacts = ca
    return FakeStep(consumed_artifacts)


class TestCollectKnowledgeFileShas(unittest.TestCase):
    """collect_knowledge_file_shas のテスト。"""

    def test_tracked_file_returns_sha(self) -> None:
        """コミット済みファイルは status=tracked と正しい short_sha を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            (repo_root / "knowledge").mkdir()
            (repo_root / "knowledge" / "D01-overview.md").write_text("# D01\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add D01")
            commit_full = _git(repo_root, "rev-parse", "HEAD")

            entries = collect_knowledge_file_shas(["knowledge/D01-overview.md"], repo_root)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["path"], "knowledge/D01-overview.md")
            self.assertEqual(entry["sha"], commit_full)
            self.assertEqual(entry["short_sha"], commit_full[:7])
            self.assertEqual(entry["status"], "tracked")

    def test_missing_file_returns_missing_status(self) -> None:
        """存在しないファイルは status=missing を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            entries = collect_knowledge_file_shas(["knowledge/D99-nonexistent.md"], repo_root)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["status"], "missing")
            self.assertEqual(entries[0]["sha"], "-")
            self.assertEqual(entries[0]["short_sha"], "-")

    def test_untracked_file_returns_untracked_status(self) -> None:
        """git 追跡外のファイルは status=untracked を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01-untracked.md").write_text("# D01\n", encoding="utf-8")
            # git add しないまま
            entries = collect_knowledge_file_shas(["knowledge/D01-untracked.md"], repo_root)
            self.assertEqual(len(entries), 1)
            self.assertIn(entries[0]["status"], ("untracked", "staged"))
            self.assertEqual(entries[0]["sha"], "-")

    def test_empty_paths_returns_empty(self) -> None:
        """空リストは空のエントリを返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            entries = collect_knowledge_file_shas([], repo_root)
            self.assertEqual(entries, [])

    def test_unchanged_note_when_file_unchanged(self) -> None:
        """HEAD~1 と同じ SHA の場合は note='unchanged（更新なし）' を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01.md").write_text("# D01\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add D01")
            # HEAD~1 を作るための追加コミット（D01 は変更しない）
            (repo_root / "other.md").write_text("other\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add other")

            entries = collect_knowledge_file_shas(["knowledge/D01.md"], repo_root)
            self.assertEqual(len(entries), 1)
            self.assertIn("unchanged", entries[0]["note"])

    def test_updated_note_when_file_updated(self) -> None:
        """HEAD~1 より新しいコミットがある場合は note='updated（更新あり）' を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01.md").write_text("# D01 v1\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add D01 v1")

            # D01 を更新して HEAD を進める
            (knowledge_dir / "D01.md").write_text("# D01 v2\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "update D01 v2")

            entries = collect_knowledge_file_shas(["knowledge/D01.md"], repo_root)
            self.assertEqual(len(entries), 1)
            self.assertIn("updated", entries[0]["note"])

    def test_comparison_unavailable_when_no_previous_revision(self) -> None:
        """HEAD~1 が存在しない場合は note に 'comparison unavailable' を含むこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01.md").write_text("# D01\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add D01")  # 唯一のコミット -> HEAD~1 なし

            entries = collect_knowledge_file_shas(["knowledge/D01.md"], repo_root)
            self.assertEqual(len(entries), 1)
            self.assertIn("comparison unavailable", entries[0]["note"])


class TestResolveKnowledgePathsForStep(unittest.TestCase):
    """resolve_knowledge_paths_for_step のテスト。"""

    def test_consumed_artifacts_none_uses_existing_artifacts(self) -> None:
        """consumed_artifacts=None の場合、existing_artifacts['knowledge'] を使用すること。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            step = _make_step(consumed_artifacts=None)
            existing = {"knowledge": ["knowledge/D01.md", "knowledge/D02.md"]}
            paths = resolve_knowledge_paths_for_step(step, existing, repo_root)
            self.assertEqual(paths, ["knowledge/D01.md", "knowledge/D02.md"])

    def test_consumed_artifacts_includes_knowledge_key(self) -> None:
        """consumed_artifacts に 'knowledge' が含まれる場合、existing_artifacts['knowledge'] を返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            step = _make_step(consumed_artifacts=["knowledge", "app_catalog"])
            existing = {"knowledge": ["knowledge/D01.md"], "app_catalog": "docs/app-catalog.md"}
            paths = resolve_knowledge_paths_for_step(step, existing, repo_root)
            self.assertEqual(paths, ["knowledge/D01.md"])

    def test_consumed_artifacts_includes_knowledge_fallback_to_glob(self) -> None:
        """consumed_artifacts に 'knowledge' があるが existing_artifacts が空の場合は glob すること。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01-foo.md").write_text("# D01\n", encoding="utf-8")
            (knowledge_dir / "D02-bar.md").write_text("# D02\n", encoding="utf-8")
            step = _make_step(consumed_artifacts=["knowledge", "app_catalog"])
            # existing_artifacts に knowledge がない（空リスト）
            paths = resolve_knowledge_paths_for_step(step, {"app_catalog": "docs/app-catalog.md"}, repo_root)
            self.assertIn("knowledge/D01-foo.md", paths)
            self.assertIn("knowledge/D02-bar.md", paths)

    def test_consumed_artifacts_excludes_knowledge(self) -> None:
        """consumed_artifacts に 'knowledge' が含まれない場合、空リストを返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            step = _make_step(consumed_artifacts=["app_catalog"])
            existing = {"knowledge": ["knowledge/D01.md"], "app_catalog": "docs/app-catalog.md"}
            paths = resolve_knowledge_paths_for_step(step, existing, repo_root)
            self.assertEqual(paths, [])

    def test_consumed_artifacts_empty_list_returns_empty(self) -> None:
        """consumed_artifacts=[] の場合、空リストを返すこと。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            step = _make_step(consumed_artifacts=[])
            existing = {"knowledge": ["knowledge/D01.md"]}
            paths = resolve_knowledge_paths_for_step(step, existing, repo_root)
            self.assertEqual(paths, [])

    def test_consumed_artifacts_none_fallback_to_glob(self) -> None:
        """consumed_artifacts=None かつ existing_artifacts に 'knowledge' がない場合、
        repo_root の knowledge/*.md を glob すること。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            knowledge_dir = repo_root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "D01-foo.md").write_text("# D01\n", encoding="utf-8")
            (knowledge_dir / "D02-bar.md").write_text("# D02\n", encoding="utf-8")
            step = _make_step(consumed_artifacts=None)
            paths = resolve_knowledge_paths_for_step(step, {}, repo_root)
            self.assertIn("knowledge/D01-foo.md", paths)
            self.assertIn("knowledge/D02-bar.md", paths)


class TestBuildKnowledgeReferenceSection(unittest.TestCase):
    """build_knowledge_reference_section のテスト。"""

    def test_no_knowledge_context_returns_none_text(self) -> None:
        """has_knowledge_context=False の場合、'knowledge references: none' を返すこと。"""
        result = build_knowledge_reference_section([], has_knowledge_context=False)
        self.assertIn("knowledge references: none", result)
        self.assertIn("参照 knowledge 版数", result)

    def test_empty_entries_returns_none_text(self) -> None:
        """エントリが空の場合、'knowledge references: none' を返すこと。"""
        result = build_knowledge_reference_section([], has_knowledge_context=True)
        self.assertIn("knowledge references: none", result)

    def test_entries_produce_markdown_table(self) -> None:
        """エントリがある場合、Markdown テーブルを含む文字列を返すこと。"""
        entries = [
            {"path": "knowledge/D01.md", "sha": "abc1234" * 5 + "abc", "short_sha": "abc1234", "status": "tracked", "note": "unchanged（更新なし）"},
            {"path": "knowledge/D02.md", "sha": "def5678" * 5 + "def", "short_sha": "def5678", "status": "tracked", "note": "updated（更新あり）"},
        ]
        result = build_knowledge_reference_section(entries, has_knowledge_context=True)
        self.assertIn("## 参照 knowledge 版数", result)
        self.assertIn("| path | short_sha | status | note |", result)
        self.assertIn("knowledge/D01.md", result)
        self.assertIn("abc1234", result)
        self.assertIn("tracked", result)
        self.assertIn("unchanged", result)
        self.assertIn("knowledge/D02.md", result)
        self.assertIn("updated", result)

    def test_pipe_in_path_is_escaped(self) -> None:
        """パス内の '|' がエスケープされること（Markdown テーブル崩れ防止）。"""
        entries = [
            {"path": "knowledge/D|01.md", "sha": "-", "short_sha": "-", "status": "missing", "note": "-"},
        ]
        result = build_knowledge_reference_section(entries)
        self.assertIn("D\\|01.md", result)

    def test_section_header_is_present(self) -> None:
        """セクションヘッダ '## 参照 knowledge 版数' が常に含まれること。"""
        result_none = build_knowledge_reference_section([], has_knowledge_context=False)
        result_some = build_knowledge_reference_section(
            [{"path": "knowledge/D01.md", "sha": "abc", "short_sha": "abc1234", "status": "tracked", "note": "-"}],
        )
        self.assertIn("## 参照 knowledge 版数", result_none)
        self.assertIn("## 参照 knowledge 版数", result_some)


class TestBuildKnowledgeReferenceLogLines(unittest.TestCase):
    """build_knowledge_reference_log_lines のテスト。"""

    def test_empty_entries_returns_none_line(self) -> None:
        """エントリが空の場合、['knowledge references: none'] を返すこと。"""
        lines = build_knowledge_reference_log_lines([])
        self.assertEqual(lines, ["knowledge references: none"])

    def test_entries_produce_log_lines(self) -> None:
        """エントリがある場合、各パスの情報を含む行リストを返すこと。"""
        entries = [
            {"path": "knowledge/D01.md", "sha": "abc1234abcabc", "short_sha": "abc1234", "status": "tracked", "note": "unchanged（更新なし）"},
        ]
        lines = build_knowledge_reference_log_lines(entries)
        self.assertEqual(len(lines), 1)
        self.assertIn("knowledge/D01.md", lines[0])
        self.assertIn("abc1234", lines[0])
        self.assertIn("tracked", lines[0])
        self.assertIn("unchanged", lines[0])


if __name__ == "__main__":
    unittest.main()
