"""hve.gui.business_requirement_template の単体テスト。"""

from __future__ import annotations

import unittest

from hve.gui.business_requirement_template import (
    BR_SECTIONS,
    BR_TEMPLATE_VERSION,
    section_count,
    section_headings,
)


class TestBusinessRequirementTemplate(unittest.TestCase):
    def test_section_count_is_seven(self):
        """sample/business-requirement.md の H2 構成に従い、章数は 7 章。"""
        self.assertEqual(section_count(), 7)

    def test_section_ids_unique(self):
        ids = [s.section_id for s in BR_SECTIONS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_section_id_format(self):
        for s in BR_SECTIONS:
            self.assertRegex(s.section_id, r"^S\d+$")

    def test_headings_start_with_number(self):
        """全章見出しは "1.", "2." ... のように番号で始まる。"""
        for s in BR_SECTIONS:
            self.assertRegex(s.heading, r"^\d+\.\s+")

    def test_heading_list_order(self):
        headings = section_headings()
        # 先頭の番号が単調増加
        nums = [int(h.split(".")[0]) for h in headings]
        self.assertEqual(nums, sorted(nums))

    def test_section_3_has_subheadings(self):
        """As-Is Analysis 章はサブ見出しを持つ（5 サブ章）。"""
        s3 = next(s for s in BR_SECTIONS if s.section_id == "S3")
        self.assertGreaterEqual(len(s3.subheadings), 3)

    def test_template_version_is_string(self):
        self.assertIsInstance(BR_TEMPLATE_VERSION, str)


if __name__ == "__main__":
    unittest.main()
