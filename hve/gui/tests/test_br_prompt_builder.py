"""hve.gui.br_prompt_builder の単体テスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hve.gui.br_prompt_builder import SourceDoc, build_merge_prompt, read_source_docs
from hve.gui.business_requirement_template import BR_SECTIONS


class TestBrPromptBuilder(unittest.TestCase):
    def test_read_source_docs_skips_missing(self):
        result = read_source_docs([Path("/no/such/file.md")])
        self.assertEqual(result, [])

    def test_read_source_docs_reads_utf8(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# テスト本文\n日本語です。\n")
            tmp = Path(f.name)
        try:
            docs = read_source_docs([tmp])
            self.assertEqual(len(docs), 1)
            self.assertIn("日本語", docs[0].content)
        finally:
            tmp.unlink()

    def test_read_source_docs_truncates_long_text(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("a" * 100)
            tmp = Path(f.name)
        try:
            docs = read_source_docs([tmp], max_chars_per_doc=20)
            self.assertEqual(len(docs), 1)
            self.assertIn("切り詰め", docs[0].content)
        finally:
            tmp.unlink()

    def test_prompt_contains_target_heading(self):
        section = BR_SECTIONS[0]
        prompt = build_merge_prompt(
            section=section,
            sources=[SourceDoc("dummy.md", "content")],
            existing_section_text=None,
        )
        self.assertIn(section.heading, prompt)
        self.assertIn(section.section_id, prompt)

    def test_prompt_marks_existing_required_to_keep(self):
        section = BR_SECTIONS[0]
        prompt = build_merge_prompt(
            section=section,
            sources=[SourceDoc("dummy.md", "content")],
            existing_section_text="## 1. Executive Summary（要約）\n\n既存本文\n",
        )
        self.assertIn("既存章本文", prompt)
        self.assertIn("既存本文", prompt)
        self.assertIn("削除しない", prompt)

    def test_prompt_no_existing_falls_back(self):
        section = BR_SECTIONS[0]
        prompt = build_merge_prompt(
            section=section,
            sources=[SourceDoc("dummy.md", "content")],
            existing_section_text=None,
        )
        self.assertIn("既存章本文なし", prompt)

    def test_prompt_anti_fabrication_rules_present(self):
        section = BR_SECTIONS[0]
        prompt = build_merge_prompt(
            section=section,
            sources=[],
            existing_section_text=None,
        )
        # 捏造防止の主要キーワード
        self.assertIn("一般論", prompt)
        self.assertIn("[要追加確認]", prompt)
        self.assertIn("対象章のみ", prompt)

    def test_prompt_includes_context(self):
        section = BR_SECTIONS[0]
        prompt = build_merge_prompt(
            section=section,
            sources=[],
            existing_section_text=None,
            company_name="株式会社サンプル",
            target_business="ロイヤルティ事業",
        )
        self.assertIn("株式会社サンプル", prompt)
        self.assertIn("ロイヤルティ事業", prompt)


if __name__ == "__main__":
    unittest.main()
