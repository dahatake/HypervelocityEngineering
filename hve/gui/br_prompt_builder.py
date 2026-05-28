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

from .business_requirement_template import BRSection


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
            text = text[:max_chars_per_doc] + f"\n\n[... 切り詰め: 元 {len(text)} 文字]\n"
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
    # ヘッダー（役割・目的）
    parts: List[str] = []
    parts.append(
        "# 役割\n"
        "あなたはトップティア戦略コンサルティングファームのシニアパートナー兼ビジネスアナリストです。\n"
        "添付資料および既存章本文のみを根拠として、`docs/business-requirement.md` の 1 章分を"
        "統合・精緻化した Markdown を出力してください。\n"
    )

    # スコープと対象章の固定
    parts.append("# 対象章（この章のみを生成すること）")
    parts.append(f"- 章ID: {section.section_id}")
    parts.append(f"- 見出し: `## {section.heading}`")
    if section.subheadings:
        parts.append("- サブ見出し（必要に応じて使用）:")
        for sub in section.subheadings:
            parts.append(f"  - `### {sub}`")
    parts.append(f"- 章の目的: {section.description}")
    parts.append("")

    # 文脈情報（任意）
    context_lines: List[str] = []
    if company_name:
        context_lines.append(f"- 対象企業: {company_name}")
    if target_business:
        context_lines.append(f"- 対象事業・業務: {target_business}")
    if context_lines:
        parts.append("# 文脈情報")
        parts.extend(context_lines)
        parts.append("")

    # 添付資料
    parts.append("# 添付資料（一次情報・最優先で参照）")
    if not sources:
        parts.append("（添付資料なし）")
    else:
        for i, src in enumerate(sources, 1):
            parts.append(f"## 添付資料 {i}: {src.display_name}")
            parts.append("```text")
            parts.append(src.content)
            parts.append("```")
            parts.append("")

    # 既存章本文
    parts.append("# 既存章本文（保持必須）")
    if existing_section_text and existing_section_text.strip():
        parts.append(
            "以下は既存の `docs/business-requirement.md` における対象章の本文です。"
            "**この記述を削除せず**、添付資料からの追加情報をマージして精緻化してください。"
        )
        parts.append("```markdown")
        parts.append(existing_section_text.rstrip())
        parts.append("```")
    else:
        parts.append("（既存章本文なし。添付資料のみから本章を新規作成すること）")
    parts.append("")

    # 厳格ルール（捏造防止）
    parts.append("# 厳格ルール（必ず遵守）")
    parts.append(
        "1. 根拠は **添付資料および既存章本文のみ**。一般論・業界慣行・外部知識で空欄を埋めない。\n"
        "2. 出典のない記述は `[要追加確認]` を付け、断定しない。\n"
        "3. 既存章本文の記述を**削除しない**。矛盾がある場合は両方を残し「資料間で見解の相違あり」と注記。\n"
        "4. 出力は **対象章のみ**（他の章を生成しない）。\n"
        "5. 出力の先頭は必ず `## " + section.heading + "` とする（前後に余計な見出しや説明文を付けない）。\n"
        "6. 数値・固有名詞・日付は資料からの引用形で記録する。\n"
        "7. ファイル書き出し・添付ファイル生成・画像生成は行わない。テキストの構造化（表・Mermaid 等のテキスト図）のみ許可。\n"
        "8. 言語は日本語固定（固有名詞・規格名のみ原語可）。添付資料が外国語の場合は、固有名詞・原文引用は保持しつつ日本語で記述する。\n"
    )

    # 出力フォーマット指示
    parts.append("# 出力フォーマット")
    parts.append(
        f"- 先頭行: `## {section.heading}`\n"
        "- 続けて本文（箇条書き・表・必要に応じてサブ見出し H3 を使用）\n"
        "- 末尾に余計な締めの文（『以上です』等）を付けない\n"
    )

    return "\n".join(parts)
