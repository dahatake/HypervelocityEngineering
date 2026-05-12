"""test_app_arch_filter.py — hve/app_arch_filter.py のテスト"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


class TestResolveAppArchScope(unittest.TestCase):
    """resolve_app_arch_scope() のテスト。"""

    # ------------------------------------------------------------------
    # カタログ生成ヘルパー
    # ------------------------------------------------------------------

    def _make_catalog(self, rows: list[tuple[str, str, str]], tmp_path: Path) -> str:
        """仮の app-arch-catalog.md を生成してパスを返す。"""
        lines = [
            "# アプリケーション アーキテクチャ カタログ",
            "",
            "## A) サマリ表（全APP横断）",
            "",
            "| APP-ID | APP名 | 推薦アーキテクチャ | Confidence | 入力ステータス |",
            "|--------|-------|-------------------|-----------|-------------|",
        ]
        for app_id, name, arch in rows:
            lines.append(f"| {app_id} | {name} | {arch} | 高 | ✅完了 |")
        lines.append("")
        content = "\n".join(lines)
        p = tmp_path / "app-arch-catalog.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 1. web-cloud のみ抽出
    # ------------------------------------------------------------------

    def test_web_cloud_app_ids_only(self):
        """aad-web で Webフロントエンド + クラウド の APP-ID のみ抽出されること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
            ("APP-02", "Batch App", "データバッチ処理"),
        ], self._tmp)
        result = resolve_app_arch_scope("aad-web", catalog_path=cat)
        self.assertEqual(result.matched_app_ids, ["APP-01"])
        self.assertEqual(result.target_kind, "web-cloud")

    # ------------------------------------------------------------------
    # 2. batch のみ抽出
    # ------------------------------------------------------------------

    def test_batch_app_ids_only(self):
        """abd で データバッチ処理 の APP-ID のみ抽出されること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
            ("APP-02", "Batch App", "データバッチ処理"),
        ], self._tmp)
        result = resolve_app_arch_scope("abd", catalog_path=cat)
        self.assertEqual(result.matched_app_ids, ["APP-02"])
        self.assertEqual(result.target_kind, "batch")

    # ------------------------------------------------------------------
    # 3. 「バッチ」表記を batch として扱う
    # ------------------------------------------------------------------

    def test_batch_short_notation(self):
        """「バッチ」表記が batch として扱われること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-03", "Batch App 2", "バッチ"),
        ], self._tmp)
        result = resolve_app_arch_scope("abdv", catalog_path=cat)
        self.assertIn("APP-03", result.matched_app_ids)
        self.assertEqual(result.target_kind, "batch")

    # ------------------------------------------------------------------
    # 4. APP-ID 指定ありで一致するものだけ残す
    # ------------------------------------------------------------------

    def test_requested_app_ids_filtered(self):
        """requested_app_ids のうち推薦アーキテクチャが一致するもののみ matched に残ること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
            ("APP-02", "Batch App", "データバッチ処理"),
        ], self._tmp)
        result = resolve_app_arch_scope("aad-web", requested_app_ids=["APP-01", "APP-02"], catalog_path=cat)
        self.assertEqual(result.matched_app_ids, ["APP-01"])
        self.assertEqual(len(result.excluded_app_ids), 1)
        self.assertEqual(result.excluded_app_ids[0].app_id, "APP-02")
        self.assertEqual(result.excluded_app_ids[0].reason, "target_arch_mismatch")

    # ------------------------------------------------------------------
    # 5. APP-ID 指定ありで全件除外
    # ------------------------------------------------------------------

    def test_all_requested_app_ids_excluded(self):
        """全指定 APP-ID が推薦アーキテクチャ不一致で除外された場合、matched_app_ids が空になること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
        ], self._tmp)
        result = resolve_app_arch_scope("abd", requested_app_ids=["APP-01"], catalog_path=cat)
        self.assertEqual(result.matched_app_ids, [])
        self.assertEqual(len(result.excluded_app_ids), 1)

    # ------------------------------------------------------------------
    # 6. unknown APP-ID を返す
    # ------------------------------------------------------------------

    def test_unknown_app_ids(self):
        """catalog に存在しない APP-ID は unknown_app_ids に入ること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
        ], self._tmp)
        result = resolve_app_arch_scope("aad-web", requested_app_ids=["APP-01", "APP-99"], catalog_path=cat)
        self.assertIn("APP-01", result.matched_app_ids)
        self.assertIn("APP-99", result.unknown_app_ids)

    # ------------------------------------------------------------------
    # 7. catalog ファイルが存在しない
    # ------------------------------------------------------------------

    def test_catalog_not_found_raises(self):
        """catalog ファイルが存在しない場合 FileNotFoundError が発生すること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        with self.assertRaises(FileNotFoundError):
            resolve_app_arch_scope("aad-web", catalog_path="nonexistent/path.md")

    def test_catalog_not_found_dry_run_warns(self):
        """dry_run=True の場合、catalog 不在でも warning を出して空リストを返すこと。"""
        from hve.app_arch_filter import resolve_app_arch_scope
        import io
        import sys

        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            result = resolve_app_arch_scope(
                "aad-web", catalog_path="nonexistent/path.md", dry_run=True
            )
        self.assertEqual(result.matched_app_ids, [])
        self.assertIn("WARNING", stderr_capture.getvalue())

    # ------------------------------------------------------------------
    # 8. A) サマリ表（全APP横断）が存在しない
    # ------------------------------------------------------------------

    def test_missing_summary_section_raises(self):
        """A) サマリ表（全APP横断）セクションがない場合 ValueError が発生すること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        p = self._tmp / "app-arch-catalog.md"
        p.write_text("# カタログ\n\n## B) 詳細\n\n内容\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            resolve_app_arch_scope("aad-web", catalog_path=str(p))
        self.assertIn("サマリ表", str(ctx.exception))

    def test_loose_section_heading_accepted(self):
        """`## A) 選定結果一覧（サマリ表）` のような揺れ見出しも受理されること。"""
        from hve.app_arch_filter import resolve_app_arch_scope
        import io

        p = self._tmp / "app-arch-catalog.md"
        content = textwrap.dedent("""\
            # カタログ

            ## A) 選定結果一覧（サマリ表）

            | APP-ID | APP名 | 推薦アーキテクチャ | Confidence | 入力ステータス |
            |--------|-------|-------------------|-----------|-------------|
            | APP-01 | Web App | Webフロントエンド + クラウド | 高 | ✅完了 |
        """)
        p.write_text(content, encoding="utf-8")

        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            result = resolve_app_arch_scope("aad-web", catalog_path=str(p))
        self.assertEqual(result.matched_app_ids, ["APP-01"])
        self.assertIn("WARNING", stderr_capture.getvalue())
        self.assertIn("選定結果一覧", stderr_capture.getvalue())

    def test_canonical_section_heading_no_warning(self):
        from hve.app_arch_filter import resolve_app_arch_scope
        import io

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
        ], self._tmp)
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            resolve_app_arch_scope("aad-web", catalog_path=cat)
        self.assertNotIn("WARNING", stderr_capture.getvalue())

    def test_section_a_without_summary_keyword_raises(self):
        from hve.app_arch_filter import resolve_app_arch_scope

        p = self._tmp / "app-arch-catalog.md"
        p.write_text("# カタログ\n\n## A) 概要\n\n本文\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            resolve_app_arch_scope("aad-web", catalog_path=str(p))

    # ------------------------------------------------------------------
    # 9. APP-ID 列不在
    # ------------------------------------------------------------------

    def test_missing_appid_column_raises(self):
        """APP-ID 列がない場合 ValueError が発生すること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        p = self._tmp / "app-arch-catalog.md"
        content = textwrap.dedent("""\
            ## A) サマリ表（全APP横断）

            | アプリ名 | 推薦アーキテクチャ |
            |---------|-------------------|
            | テスト | Webフロントエンド + クラウド |
        """)
        p.write_text(content, encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            resolve_app_arch_scope("aad-web", catalog_path=str(p))
        self.assertIn("APP-ID", str(ctx.exception))

    # ------------------------------------------------------------------
    # 10. 推薦アーキテクチャ列不在
    # ------------------------------------------------------------------

    def test_missing_arch_column_raises(self):
        """推薦アーキテクチャ列がない場合 ValueError が発生すること。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        p = self._tmp / "app-arch-catalog.md"
        content = textwrap.dedent("""\
            ## A) サマリ表（全APP横断）

            | APP-ID | APP名 |
            |--------|-------|
            | APP-01 | テスト |
        """)
        p.write_text(content, encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            resolve_app_arch_scope("aad-web", catalog_path=str(p))
        self.assertIn("推薦アーキテクチャ", str(ctx.exception))

    # ------------------------------------------------------------------
    # to_dict / to_markdown_section のスモークテスト
    # ------------------------------------------------------------------

    def test_to_dict_keys(self):
        """to_dict() が必須キーを含むこと。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
        ], self._tmp)
        result = resolve_app_arch_scope("aad-web", catalog_path=cat)
        d = result.to_dict()
        for key in ("workflow_id", "target_kind", "target_architectures",
                    "matched_app_ids", "excluded_app_ids", "unknown_app_ids", "catalog_path"):
            self.assertIn(key, d)

    def test_to_markdown_section_contains_app_id(self):
        """to_markdown_section() が matched APP-ID を含むこと。"""
        from hve.app_arch_filter import resolve_app_arch_scope

        cat = self._make_catalog([
            ("APP-01", "Web App", "Webフロントエンド + クラウド"),
        ], self._tmp)
        result = resolve_app_arch_scope("aad-web", catalog_path=cat)
        section = result.to_markdown_section()
        self.assertIn("APP-01", section)

    def test_to_markdown_section_empty_when_no_match(self):
        """matched_app_ids が空の場合、to_markdown_section() は空文字列を返すこと。"""
        from hve.app_arch_filter import AppArchFilterResult

        r = AppArchFilterResult(
            workflow_id="abd",
            target_kind="batch",
            target_architectures=["データバッチ処理"],
            requested_app_ids=["APP-01"],
            matched_app_ids=[],
        )
        self.assertEqual(r.to_markdown_section(), "")


if __name__ == "__main__":
    unittest.main()
