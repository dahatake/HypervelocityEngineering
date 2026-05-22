"""hve.gui.br_parser の単体テスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hve.gui.br_parser import (
    extract_preamble,
    find_section_text,
    parse_existing_br,
    read_existing_br,
    read_preamble,
)


SAMPLE_BR = """# Business Requirement Document

何かのプリアンブル。

## 1. Executive Summary（要約）

要約本文 line1。
要約本文 line2。

## 2. Company Overview（企業概要）

企業概要本文。

### 2.1 サブ見出しは H3 なので章境界にならない

サブ章本文。

## 3. As-Is Analysis（現状分析）

現状分析。
"""


class TestBrParser(unittest.TestCase):
    def test_parse_empty(self):
        self.assertEqual(parse_existing_br(""), {})

    def test_parse_no_h2(self):
        self.assertEqual(parse_existing_br("# title\n\n本文のみ"), {})

    def test_parse_three_sections(self):
        result = parse_existing_br(SAMPLE_BR)
        self.assertEqual(len(result), 3)
        self.assertIn("1. Executive Summary（要約）", result)
        self.assertIn("2. Company Overview（企業概要）", result)
        self.assertIn("3. As-Is Analysis（現状分析）", result)

    def test_h3_is_part_of_parent_h2(self):
        """H3 はその上位 H2 章の本文に含まれる。"""
        result = parse_existing_br(SAMPLE_BR)
        s2 = result["2. Company Overview（企業概要）"]
        self.assertIn("### 2.1", s2)

    def test_section_text_starts_with_heading(self):
        result = parse_existing_br(SAMPLE_BR)
        self.assertTrue(result["1. Executive Summary（要約）"].startswith("## 1. Executive Summary"))

    def test_read_existing_br_missing_file(self):
        self.assertEqual(read_existing_br(Path("/no/such/file.md")), {})

    def test_read_existing_br_roundtrip(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_BR)
            tmp = Path(f.name)
        try:
            result = read_existing_br(tmp)
            self.assertEqual(len(result), 3)
        finally:
            tmp.unlink()

    def test_find_section_exact(self):
        sections = parse_existing_br(SAMPLE_BR)
        text = find_section_text(sections, "1. Executive Summary（要約）")
        self.assertIsNotNone(text)
        self.assertIn("要約本文", text)

    def test_find_section_prefix_match(self):
        """見出し文言が異なっても先頭番号で前方一致する。"""
        sections = parse_existing_br(SAMPLE_BR)
        text = find_section_text(sections, "1. Executive Summary（概要違い）")
        self.assertIsNotNone(text)

    def test_find_section_not_found(self):
        sections = parse_existing_br(SAMPLE_BR)
        self.assertIsNone(find_section_text(sections, "99. 存在しない章"))

    def test_extract_preamble_with_h1(self):
        """H1 タイトル + 導入文がプリアンブルとして抽出される。"""
        preamble = extract_preamble(SAMPLE_BR)
        self.assertIn("# Business Requirement Document", preamble)
        self.assertIn("何かのプリアンブル", preamble)
        # H2 章本文は含まない
        self.assertNotIn("## 1. Executive Summary", preamble)

    def test_extract_preamble_empty_input(self):
        self.assertEqual(extract_preamble(""), "")

    def test_extract_preamble_no_h2(self):
        """H2 が無い場合は全文が preamble。"""
        text = "# Title\n\n本文のみ\n"
        self.assertEqual(extract_preamble(text), text.rstrip())

    def test_read_preamble_missing_file(self):
        self.assertEqual(read_preamble(Path("/no/such/file.md")), "")


if __name__ == "__main__":
    unittest.main()
