"""GUI / CLI / Prompt 版フルシステムテストの画像証跡契約。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUI_PROMPT = _REPO_ROOT / "tests/[gui]SystemTest - Full.txt"
_CLI_PROMPT = _REPO_ROOT / "tests/[cli]SystemTest - Full.txt"
_PROMPT_FULL = _REPO_ROOT / "tests/prompt-version/09-full-system-test.md"
_PROMPT_INDEX = _REPO_ROOT / "tests/prompt-version/README.md"

_SURFACE_PROMPTS = (_GUI_PROMPT, _CLI_PROMPT, _PROMPT_FULL)


def _read(path: Path) -> str:
    assert path.is_file(), f"フルシステムテスト Prompt が未作成: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _screenshot_section(path: Path) -> str:
    if not path.is_file():
        pytest.skip("Prompt の存在確認テストで報告済み")
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"^## スクリーンショット証跡\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        pytest.skip("スクリーンショット証跡節の存在確認テストで報告済み")
    body = match.group("body").strip()
    assert body, f"{path.relative_to(_REPO_ROOT)} のスクリーンショット証跡節が空"
    return body


@pytest.mark.parametrize("path", _SURFACE_PROMPTS, ids=lambda path: path.name)
def test_each_surface_has_a_full_system_test_prompt(path: Path):
    assert _read(path).strip()


@pytest.mark.parametrize("path", _SURFACE_PROMPTS, ids=lambda path: path.name)
def test_each_surface_has_a_screenshot_evidence_section(path: Path):
    if not path.is_file():
        pytest.skip("Prompt の存在確認テストで報告済み")
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^## スクリーンショット証跡\s*$", text, re.MULTILINE), (
        f"{path.relative_to(_REPO_ROOT)} に '## スクリーンショット証跡' が無い"
    )


@pytest.mark.parametrize("path", _SURFACE_PROMPTS, ids=lambda path: path.name)
def test_each_surface_defines_the_common_screenshot_evidence_contract(path: Path):
    body = _screenshot_section(path)
    for token in (
        "開始前",
        "実行開始",
        "実行中",
        "完了",
        "FAIL",
        "BLOCKED",
        "interrupted",
        "停止",
        "再開",
        "artifacts/screenshots/",
        "manifest.json",
        "取得時刻",
        "画面状態",
        "Requirement-ID",
        "実測結果の直後",
        "相対リンク",
        "alt text",
        "caption",
        "機微情報",
        "NOT_MEASURED",
        "SHA-256",
        "PNG",
        "終了コード",
        "stdout",
        "stderr",
        "代替しない",
        "ポーリングごとの大量取得は行わない",
        "共有 manifest",
        "直接更新しない",
        "取得数",
        "掲載数",
        "画像不要数",
        "取得不能数",
        "壊れたリンク数",
    ):
        assert token in body, f"{path.relative_to(_REPO_ROOT)} の画像証跡契約に {token!r} が無い"
    assert re.search(
        r"(?:取得不能|安全な取得が不可能).*?NOT_MEASURED",
        body,
        re.DOTALL,
    ), f"{path.relative_to(_REPO_ROOT)} に取得不能時の NOT_MEASURED 契約が無い"
    assert re.search(
        r"(?:視覚確認|視覚要件).*?(?:受入条件|必須).*?BLOCKED",
        body,
        re.DOTALL,
    ), f"{path.relative_to(_REPO_ROOT)} に視覚確認必須時の BLOCKED 契約が無い"
    assert re.search(
        r"(?:終了コード|stdout|stderr|ログ).*?代替しない",
        body,
        re.DOTALL,
    ), f"{path.relative_to(_REPO_ROOT)} に画像が実行証跡を代替しない契約が無い"


@pytest.mark.parametrize("path", _SURFACE_PROMPTS, ids=lambda path: path.name)
def test_each_surface_shows_a_relative_markdown_image_example(path: Path):
    body = _screenshot_section(path)
    assert re.search(
        r"!\[[^\]]+\]\((?!https?://|/)[^)]*screenshots/[^)]+\.png\)",
        body,
    ), f"{path.relative_to(_REPO_ROOT)} に相対 Markdown 画像の例が無い"


def test_gui_prompt_names_gui_specific_visual_states():
    body = _screenshot_section(_GUI_PROMPT)
    for token in ("設定画面", "Workflow", "Step", "Workbench", "ダイアログ"):
        assert token in body


def test_cli_prompt_names_terminal_specific_visual_states():
    body = _screenshot_section(_CLI_PROMPT)
    for token in ("端末", "plan", "確認", "進捗", "エラー"):
        assert token in body


def test_prompt_full_integrates_images_with_existing_case_evidence():
    text = _read(_PROMPT_FULL)
    body = _screenshot_section(_PROMPT_FULL)
    for token in (
        "CASE-ID",
        "plan 提示",
        "承認待ち",
        "委譲",
        "stale",
        "case 専用",
        "evidence_paths",
        "共有 manifest",
        "更新しない",
    ):
        assert token in body

    for contract_anchor in (
        "## Phase 0. 計画のみ（承認前）",
        "## Phase 1. 承認後の実 run",
        "## 各 case の検証と敵対的レビュー",
        "## 最終レポート",
        "## 完了条件",
    ):
        anchor = text.split(contract_anchor, 1)
        assert len(anchor) == 2, f"Prompt 版に既存アンカーが無い: {contract_anchor}"
        nearby = anchor[1].split("\n## ", 1)[0]
        assert "スクリーンショット" in nearby, (
            f"{contract_anchor} にスクリーンショット証跡が統合されていない"
        )


def test_prompt_index_announces_the_full_test_screenshot_contract():
    text = _read(_PROMPT_INDEX)
    row = next(
        (
            line
            for line in text.splitlines()
            if line.lstrip().startswith("|")
            and "[09-full-system-test.md]" in line
        ),
        "",
    )
    assert row, "Prompt 版索引に 09-full-system-test.md の表行が無い"
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    assert len(cells) == 3, "Prompt 版索引の 09 表行は 3 列でなければならない"
    assert re.fullmatch(r"\[[^]]+\]\(09-full-system-test\.md\)", cells[0]), (
        "Prompt 版索引の 09 表行が正しい相対リンクを持たない"
    )
    for token in ("スクリーンショット", "artifacts/screenshots/", "機微情報"):
        assert token in cells[1], f"Prompt 版索引の 09 説明セルに {token!r} が無い"
