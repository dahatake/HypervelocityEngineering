"""Revision history lives in its own file, outside the normative requirement text."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_HISTORY = _REPO_ROOT / "hve-dev" / "requirement-definition-history.md"
_VERSION_ROW = re.compile(r"^\| \d+\.\d+ \|")


def _section_11() -> str:
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")
    start = text.index("## 11. 改訂履歴")
    return text[start:text.index("\n## 12. ", start)]


def test_history_file_holds_the_revision_table() -> None:
    assert _HISTORY.is_file(), _HISTORY
    text = _HISTORY.read_text(encoding="utf-8-sig")
    assert "| バージョン | 日付 | 内容 |" in text
    assert any(_VERSION_ROW.match(line) for line in text.splitlines())


def test_requirement_definition_keeps_only_a_link_in_section_11() -> None:
    section = _section_11()
    assert [line for line in section.splitlines() if _VERSION_ROW.match(line)] == []
    assert "requirement-definition-history.md" in section
