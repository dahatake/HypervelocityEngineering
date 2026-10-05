"""P4-T63 RED: UI 生成 Prompt の視覚デザイン基準契約。"""
from __future__ import annotations

from pathlib import Path
import re


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS = _REPO_ROOT / ".github" / "prompts"

_UI_PROMPTS = (
    "Arch-UI-Detail.prompt.md",
    "Dev-Microservice-Azure-UICoding.prompt.md",
)
_BUSINESS_UI_KEYWORDS = ("一貫性", "可読性", "階層", "コントラスト")
_EXCLUDED_STYLES_HEADING_RE = re.compile(
    r"^#{2,6}\s+.*除外するスタイル.*$",
    re.MULTILINE,
)
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+\S+", re.MULTILINE)


def _excluded_styles_section(text: str) -> str:
    match = _EXCLUDED_STYLES_HEADING_RE.search(text)
    assert match is not None, "除外するスタイルの見出しがない"
    next_heading = re.search(r"^#{1,6}\s+", text[match.end() :], re.MULTILINE)
    if next_heading is None:
        return text[match.end() :]
    return text[match.end() : match.end() + next_heading.start()]


def test_ui_prompts_declare_excluded_styles() -> None:
    """UI 生成 Prompt は業務 UI 基準と除外スタイル一覧を明示する。"""
    for prompt_name in _UI_PROMPTS:
        text = (_PROMPTS / prompt_name).read_text(encoding="utf-8")

        missing_keywords = [
            keyword for keyword in _BUSINESS_UI_KEYWORDS if keyword not in text
        ]
        assert not missing_keywords, (
            f"{prompt_name}: 業務 UI 基準のキーワードが不足: {missing_keywords}"
        )

        section = _excluded_styles_section(text)
        items = _LIST_ITEM_RE.findall(section)
        assert len(items) >= 3, (
            f"{prompt_name}: 除外するスタイルの項目が 3 件未満: {len(items)}"
        )


def test_asdw_guide_describes_ui_criteria_rework_and_deny_layer() -> None:
    """P4-T72: ASDW-WEB ガイドが UI 基準・差戻し宣言の現状・破壊的操作の拒否を案内する。"""
    guide = (_REPO_ROOT / "users-guide" / "05-app-dev-microservice-azure.md").read_text(
        encoding="utf-8"
    )

    assert "除外するスタイル" in guide and "Dev-Microservice-Azure-UICoding.prompt.md" in guide
    assert "`rework_targets`" in guide and "Step 5.3" in guide
    assert "CRITICAL" in guide and "harness-safety-guard" in guide
