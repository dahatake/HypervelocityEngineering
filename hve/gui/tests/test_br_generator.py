"""hve.gui.br_generator の単体テスト（Copilot SDK モック）。"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hve.gui.br_generator import (
    BRGenerationConfig,
    _assemble_output,
    _placeholder_section,
    generate_business_requirement,
)
from hve.gui.business_requirement_template import BR_SECTIONS


class TestAssembleOutput(unittest.TestCase):
    def test_assemble_without_preamble(self):
        from hve.gui.br_generator import SectionResult

        results = [
            SectionResult(section=BR_SECTIONS[0], ok=True, text="## 1. ES\n\n本文\n"),
            SectionResult(section=BR_SECTIONS[1], ok=True, text="## 2. CO\n\n本文\n"),
        ]
        out = _assemble_output(results)
        self.assertIn("# Business Requirement Document", out)
        self.assertIn("## 1. ES", out)
        self.assertIn("## 2. CO", out)

    def test_placeholder_section_marks_unknown(self):
        text = _placeholder_section(BR_SECTIONS[0], "失敗理由")
        self.assertIn("[要追加確認]", text)
        self.assertIn("失敗理由", text)
        self.assertTrue(text.startswith(f"## {BR_SECTIONS[0].heading}"))


class TestGenerateBusinessRequirementErrors(unittest.TestCase):
    """SDK 不在・添付資料なし時のエラーパスを検証。"""

    def test_no_sources_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = BRGenerationConfig(repo_root=Path(tmp), source_paths=[])
            result = asyncio.run(generate_business_requirement(cfg))
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.error)

    def test_sdk_unavailable_returns_error(self):
        """copilot モジュールが import できない場合はエラーを返す。"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# dummy")
            tmp_src = Path(f.name)
        with tempfile.TemporaryDirectory() as tmp_root:
            cfg = BRGenerationConfig(
                repo_root=Path(tmp_root),
                source_paths=[tmp_src],
            )
            # copilot import を失敗させる
            import builtins
            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "copilot" or name.startswith("copilot."):
                    raise ImportError("forced for test")
                return real_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=fake_import):
                result = asyncio.run(generate_business_requirement(cfg))
            self.assertFalse(result.ok)
            self.assertIn("SDK", result.error or "")
        tmp_src.unlink()


if __name__ == "__main__":
    unittest.main()
