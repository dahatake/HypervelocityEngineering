"""FR-QA-11: QA 質問票の内容をコメントへ二重に投稿させない（N4-4 / D11）。"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_QA_PROMPTS = (
    _ROOT / ".github" / "prompts" / "runtime" / "qa" / "pre-execution.prompt.md",
    _ROOT / ".github" / "prompts" / "cloud" / "copilot-auto-feedback-auto-qa.prompt.md",
)


@pytest.mark.parametrize("path", _QA_PROMPTS, ids=lambda p: p.name)
def test_qa_prompt_posts_link_and_summary_instead_of_full_copy(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "省略なく" not in text
    assert "サマリーのみの投稿は禁止" not in text
    assert "ファイルへのリンク" in text
    assert "質問数・未回答数の要約" in text


@pytest.mark.parametrize("path", _QA_PROMPTS, ids=lambda p: p.name)
def test_qa_prompt_keeps_qa_file_as_the_source_of_truth(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "`qa/` 配下に保存した回答ファイルのパスをこのコメント内に明記" in text
