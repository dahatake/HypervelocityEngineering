"""hve.gui.br_generator の単体テスト（Copilot SDK モック）。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hve.gui.br_generator import (
    BRGenerationConfig,
    _assemble_output,
    _generate_one_section,
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


class _FakeSession:
    async def send_and_wait(self, _prompt: str, *, timeout: int):
        return SimpleNamespace(text="## 1. Executive Summary\n\n本文\n")

    async def disconnect(self) -> None:
        return None


class TestRoutingContract(unittest.TestCase):
    def test_generate_one_section_passes_ard_workflow_and_runtime_config(self) -> None:
        copilot = types.ModuleType("copilot")
        session_module = types.ModuleType("copilot.session")

        class _PermissionHandler:
            approve_all = staticmethod(lambda *_args, **_kwargs: True)

        session_module.PermissionHandler = _PermissionHandler
        copilot.session = session_module

        create = AsyncMock(return_value=_FakeSession())
        with patch.dict(
            sys.modules,
            {"copilot": copilot, "copilot.session": session_module},
        ), patch(
            "hve.orchestrator._create_session_with_auto_reasoning_fallback",
            new=create,
        ):
            result = asyncio.run(
                _generate_one_section(
                    client=object(),
                    section=BR_SECTIONS[0],
                    sources=[],
                    existing_section_text=None,
                    config=BRGenerationConfig(
                        repo_root=Path("."),
                        source_paths=[],
                        model="gpt-5.4",
                        cli_path="sdk-copilot",
                        cli_url="http://runtime.example",
                        github_token="token",
                        timeout_seconds=123,
                    ),
                    progress_callback=None,
                    completed_counter=[0],
                    total=1,
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(create.await_args.kwargs["workflow_id"], "ard")
        runtime_config = create.await_args.kwargs.get("config")
        self.assertIsNotNone(runtime_config)
        self.assertEqual(runtime_config.model, "gpt-5.4")
        self.assertEqual(runtime_config.cli_path, "sdk-copilot")
        self.assertEqual(runtime_config.cli_url, "http://runtime.example")
        self.assertEqual(runtime_config.github_token, "token")


if __name__ == "__main__":
    unittest.main()
