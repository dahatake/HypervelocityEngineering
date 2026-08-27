"""Tests for hve.prompt_loader (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

import hve.prompt_loader as prompt_loader
from hve.prompt_loader import (
    load_prompt,
    load_prompt_file,
    substitute_work_placeholders,
)


def test_load_prompt_returns_content(tmp_path: Path) -> None:
    (tmp_path / "Foo.prompt.md").write_text("hello world", encoding="utf-8")
    assert load_prompt("Foo", prompts_dir=tmp_path) == "hello world"


def test_load_prompt_missing_returns_empty(tmp_path: Path) -> None:
    assert load_prompt("Missing", prompts_dir=tmp_path) == ""


def test_load_prompt_empty_name(tmp_path: Path) -> None:
    assert load_prompt("", prompts_dir=tmp_path) == ""


def test_load_prompt_file_accepts_repo_relative_github_prompts_prefix(
    tmp_path: Path,
) -> None:
    prompts_dir = tmp_path / "prompts"
    (prompts_dir / "runtime").mkdir(parents=True)
    (prompts_dir / "runtime" / "nested.prompt.md").write_text(
        "nested via canonical path", encoding="utf-8"
    )

    assert (
        load_prompt_file(
            ".github/prompts/runtime/nested.prompt.md", prompts_dir=prompts_dir
        )
        == "nested via canonical path"
    )


@pytest.mark.parametrize(
    "relative_path",
    ["runtime/nested.md", ".github/prompts/runtime/nested.md"],
)
def test_load_prompt_file_rejects_non_prompt_markdown_suffix(
    tmp_path: Path, relative_path: str
) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    with pytest.raises(ValueError, match=r"\.prompt\.md"):
        load_prompt_file(relative_path, prompts_dir=prompts_dir)


def test_load_prompt_file_rejects_windows_drive_relative_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Windows drive path"):
        load_prompt_file("C:relative.prompt.md", prompts_dir=tmp_path)


def test_load_prompt_file_rejects_unc_network_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative to the prompts root"):
        load_prompt_file("//server/share/prompt.prompt.md", prompts_dir=tmp_path)


def test_load_prompt_file_rejects_default_root_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside-prompts"
    repo_root.mkdir()
    outside.mkdir()
    (outside / "external.prompt.md").write_text("external", encoding="utf-8")
    monkeypatch.setattr(prompt_loader, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(prompt_loader, "_DEFAULT_PROMPTS_DIR", outside)

    with pytest.raises(ValueError, match="inside the repository root"):
        load_prompt_file("external.prompt.md")


def test_load_prompt_empty_existing_file_returns_empty_for_compatibility(
    tmp_path: Path,
) -> None:
    (tmp_path / "Blank.prompt.md").write_text("  \n", encoding="utf-8")

    assert load_prompt("Blank", prompts_dir=tmp_path) == ""


@pytest.mark.parametrize(
    "agent_name",
    ["runtime/Foo", r"runtime\Foo", "../Foo", "/Foo", "C:/Foo", "C:Foo"],
)
def test_load_prompt_rejects_unsafe_agent_names(
    tmp_path: Path, agent_name: str
) -> None:
    with pytest.raises(ValueError):
        load_prompt(agent_name, prompts_dir=tmp_path)


def test_load_prompt_real_agent_present() -> None:
    # Phase 1 で生成された実ファイルから 1 件確認（β オプションで本文を含む）
    text = load_prompt("Arch-UI-List")
    assert text != ""
    assert "## " in text  # at least one H2 section


def test_substitute_work_placeholders_replaces_run_id_and_identifier() -> None:
    text = "> **WORK**: `work/run/<run-id>/Agent/Issue-<識別子>/`"
    out = substitute_work_placeholders(text, run_id="issue-2748", identifier="0")
    assert out == "> **WORK**: `work/run/issue-2748/Agent/Issue-0/`"
    assert "<run-id>" not in out
    assert "<識別子>" not in out


def test_substitute_work_placeholders_multiple_occurrences() -> None:
    text = "work/run/<run-id>/A/Issue-<識別子>/ work/run/<run-id>/B/Issue-<識別子>/"
    out = substitute_work_placeholders(
        text, run_id="20260623T011027-e0a6e2", identifier="0"
    )
    assert out.count("20260623T011027-e0a6e2") == 2
    assert "<run-id>" not in out
    assert "<識別子>" not in out


def test_substitute_work_placeholders_empty_text() -> None:
    assert substitute_work_placeholders("", run_id="issue-1", identifier="0") == ""


def test_substitute_work_placeholders_empty_run_id_skips_run_id() -> None:
    text = "work/run/<run-id>/Issue-<識別子>/"
    out = substitute_work_placeholders(text, run_id="", identifier="0")
    # run_id が空のときは <run-id> を置換しない（誤った空文字置換を防ぐ）
    assert "<run-id>" in out
    assert "<識別子>" not in out


def test_substitute_work_placeholders_empty_identifier_skips_identifier() -> None:
    text = "work/run/<run-id>/Issue-<識別子>/"
    out = substitute_work_placeholders(text, run_id="issue-9", identifier="")
    # identifier が空のときは <識別子> を置換しない（誤った空文字置換を防ぐ）
    assert "<識別子>" in out
    assert "<run-id>" not in out


def test_substitute_work_placeholders_on_real_agent_prompt() -> None:
    # runner.py が行う load_prompt → substitute の統合動作を実プロンプトで検証。
    # 実 Agent プロンプトの WORK 定義 `work/run/<run-id>/<Agent>/Issue-<識別子>/`
    # が実値化され、プレースホルダが残らないことを確認する。
    body = load_prompt("Dev-Microservice-Azure-DataDesign")
    assert body != ""
    assert "<run-id>" in body  # 前提: 置換対象のプレースホルダが存在する
    out = substitute_work_placeholders(body, run_id="issue-2748", identifier="0")
    assert "work/run/issue-2748/" in out
    assert "<run-id>" not in out
    assert "<識別子>" not in out
