"""hve.gui.br_prompt_builder — 章単位マージプロンプトの組み立て。

`.github/prompts/Arch-ARD-BusinessAnalysis-Targeted.prompt.md` の Prompt をベースに、
1 章分のマージ指示を組み立てる純関数を提供する。

設計判断:
- 章単位 fan-out のため、1 章分のコンテキストのみ LLM に渡す。
- 既存章本文がある場合は「既存記述の保持 + 追加情報のマージ」を指示。
- 添付資料の本文は呼び出し側が事前に読み込み・連結して渡す。
- 出力は H2 見出しから始まる Markdown のみ。
- 捏造防止のため、添付資料・既存章以外の情報の参照を明示的に禁止する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    from ..prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level import compatibility
    from hve.prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]

try:
    from .business_requirement_template import BRSection
except ImportError:  # pragma: no cover - top-level import compatibility
    from hve.gui.business_requirement_template import BRSection  # type: ignore[import-not-found,no-redef]


_MERGE_PROMPT_TEMPLATE = load_prompt_file("runtime/gui/br-merge-section.prompt.md")


def _fragment(name: str) -> str:
    """1 行の固定フラグメントを、末尾改行を除いた形で返す。"""
    return load_prompt_file(f"runtime/gui/{name}.prompt.md").rstrip("\n")


_SUBHEADINGS_LABEL = _fragment("br-merge-subheadings-label")
_CONTEXT_HEADING = _fragment("br-merge-context-heading")
_CONTEXT_COMPANY = _fragment("br-merge-context-company")
_CONTEXT_BUSINESS = _fragment("br-merge-context-business")
_SOURCES_EMPTY = _fragment("br-merge-sources-empty")
_SOURCE_HEADING = _fragment("br-merge-source-heading")
_EXISTING_PRESENT = _fragment("br-merge-existing-present")
_EXISTING_ABSENT = _fragment("br-merge-existing-absent")
_TRUNCATION_NOTICE = _fragment("br-merge-truncation-notice")


@dataclass
class SourceDoc:
    """添付資料 1 件分の本文と表示名。"""

    display_name: str
    content: str  # Markdown 化済みの本文


def read_source_docs(paths: List[Path], max_chars_per_doc: int = 50000) -> List[SourceDoc]:
    """添付ファイル群を読み込んで SourceDoc リストを作る。

    - UTF-8 で読み込めないファイルはスキップ（捏造禁止）。
    - 1 ファイルあたり max_chars_per_doc で切り詰める（トークン上限保護）。
    """
    result: List[SourceDoc] = []
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) > max_chars_per_doc:
            notice = _TRUNCATION_NOTICE.format(original_chars=len(text))
            text = text[:max_chars_per_doc] + f"\n\n{notice}\n"
        result.append(SourceDoc(display_name=p.name, content=text))
    return result


def build_merge_prompt(
    section: BRSection,
    sources: List[SourceDoc],
    existing_section_text: Optional[str],
    target_business: Optional[str] = None,
    company_name: Optional[str] = None,
) -> str:
    """1 章分のマージプロンプトを組み立てる。

    出力は LLM に渡す単一の文字列。
    """
    subheadings_block = ""
    if section.subheadings:
        subheadings_lines = [_SUBHEADINGS_LABEL]
        subheadings_lines.extend(f"  - `### {sub}`" for sub in section.subheadings)
        subheadings_block = "\n".join(subheadings_lines) + "\n"

    context_lines: List[str] = []
    if company_name:
        context_lines.append(_CONTEXT_COMPANY.format(company_name=company_name))
    if target_business:
        context_lines.append(_CONTEXT_BUSINESS.format(target_business=target_business))
    context_section = ""
    if context_lines:
        context_section = _CONTEXT_HEADING + "\n" + "\n".join(context_lines) + "\n\n"

    if not sources:
        sources_block = _SOURCES_EMPTY + "\n"
    else:
        source_parts: List[str] = []
        for i, src in enumerate(sources, 1):
            source_parts.extend(
                [
                    _SOURCE_HEADING.format(index=i, display_name=src.display_name),
                    "```text",
                    src.content,
                    "```",
                    "",
                ]
            )
        sources_block = "\n".join(source_parts) + "\n"

    if existing_section_text and existing_section_text.strip():
        existing_section_block = (
            _EXISTING_PRESENT
            + "\n```markdown\n"
            + f"{existing_section_text.rstrip()}\n"
            + "```\n\n"
        )
    else:
        existing_section_block = _EXISTING_ABSENT + "\n\n"

    return _MERGE_PROMPT_TEMPLATE.format(
        section_id=section.section_id,
        section_heading=section.heading,
        subheadings_block=subheadings_block,
        section_description=section.description,
        context_section=context_section,
        sources_block=sources_block,
        existing_section_block=existing_section_block,
    )
