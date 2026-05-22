"""hve.gui.br_parser — `docs/business-requirement.md` の章単位パーサ。

H2 見出しを境界として既存 BR ファイルを章別 dict に分解する純関数を提供する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional


# H2 見出しを検出する正規表現（行頭の `## ` で始まり、`### ` ではない）
_H2_PATTERN = re.compile(r"^##\s+(?!#)(.+?)\s*$", re.MULTILINE)


def parse_existing_br(text: str) -> Dict[str, str]:
    """BR Markdown 本文を H2 章ごとに分解する。

    返り値:
        { 見出し文字列（"## " を含まない）: 章本文（見出し行を含む） }

    H2 見出しが 1 つもない場合は空 dict を返す。
    H1（"# ..."）以前のプリアンブルは無視する（章単位処理対象外）。
    """
    if not text:
        return {}

    matches = list(_H2_PATTERN.finditer(text))
    if not matches:
        return {}

    result: Dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[heading] = text[start:end].rstrip() + "\n"
    return result


def read_existing_br(path: Path) -> Dict[str, str]:
    """ファイルから既存 BR を読み取って章別 dict にする。

    ファイルが存在しない、または空の場合は空 dict を返す。
    """
    if not path.exists() or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    return parse_existing_br(text)


def find_section_text(sections: Dict[str, str], expected_heading: str) -> Optional[str]:
    """期待する見出しに最も近い章本文を探す。

    完全一致を優先し、無ければ先頭の番号（"1. " 等）でゆるく一致させる。
    """
    if expected_heading in sections:
        return sections[expected_heading]
    # 先頭の番号で前方一致
    prefix_match = re.match(r"^(\d+(?:\.\d+)*\.)", expected_heading)
    if prefix_match:
        prefix = prefix_match.group(1)
        for k, v in sections.items():
            if k.startswith(prefix):
                return v
    return None


def extract_preamble(text: str) -> str:
    """既存 BR 本文から H2 以前のプリアンブル（H1 タイトル + 導入文）を抽出する。

    H2 が無い場合は全文をプリアンブルとして返す。
    既存記述削除禁止の原則を守るため、生成時に保持する。
    """
    if not text:
        return ""
    m = _H2_PATTERN.search(text)
    if m is None:
        return text.rstrip()
    return text[: m.start()].rstrip()


def read_preamble(path: Path) -> str:
    """ファイルから既存 BR のプリアンブルを読み取る。"""
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return extract_preamble(text)
