"""Tests for hve.prompt_loader (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from hve.prompt_loader import load_prompt


def test_load_prompt_returns_content(tmp_path: Path) -> None:
    (tmp_path / "Foo.prompt.md").write_text("hello world", encoding="utf-8")
    assert load_prompt("Foo", prompts_dir=tmp_path) == "hello world"


def test_load_prompt_missing_returns_empty(tmp_path: Path) -> None:
    assert load_prompt("Missing", prompts_dir=tmp_path) == ""


def test_load_prompt_empty_name(tmp_path: Path) -> None:
    assert load_prompt("", prompts_dir=tmp_path) == ""


def test_load_prompt_real_agent_present() -> None:
    # Phase 1 で生成された実ファイルから 1 件確認（β オプションで本文を含む）
    text = load_prompt("Arch-UI-List")
    assert text != ""
    assert "## " in text  # at least one H2 section
