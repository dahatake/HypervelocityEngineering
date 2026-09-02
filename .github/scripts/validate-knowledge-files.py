#!/usr/bin/env python3
"""Validate D-class knowledge documents against their two canonical schemas."""

import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# 定数
# --------------------------------------------------------------------------- #

FILENAME_PATTERN = re.compile(r"^D\d{2}-.+\.md$")
CHANGELOG_SUFFIX = "-ChangeLog.md"

MAX_FILE_SIZE_CHARS = 20_000

MAIN_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("§1 目的と背景",       re.compile(r"^## 1\. 目的と背景", re.MULTILINE)),
    ("§2 要求項目",         re.compile(r"^## 2\. 要求項目（Confirmed）", re.MULTILINE)),
    ("§3 要求項目",         re.compile(r"^## 3\. 要求項目（Tentative", re.MULTILINE)),
    ("§4 未確定事項",       re.compile(r"^## 4\. 未確定事項（Unknown）", re.MULTILINE)),
    ("§5 最低内容カバー状況", re.compile(r"^## 5\. 最低内容カバー状況", re.MULTILINE)),
    ("§6 不足判定",         re.compile(r"^## 6\. 不足判定・推奨アクション", re.MULTILINE)),
    ("§7 状態サマリー",     re.compile(r"^## 7\. 状態サマリー", re.MULTILINE)),
    ("§8 関連文書",         re.compile(r"^## 8\. 関連文書", re.MULTILINE)),
]

CHANGELOG_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("全体更新履歴", re.compile(r"^## 全体更新履歴", re.MULTILINE)),
    ("要求項目別ログ", re.compile(r"^## 要求項目別ログ", re.MULTILINE)),
    ("付録 A", re.compile(r"^## 付録 A: マッピング詳細", re.MULTILINE)),
]

MAIN_METADATA_FIELDS = [
    "**D クラス**",
    "**文書名**",
    "**必須度**",
    "**総合状態**",
    "**Prompt投入可否**",
    "**関連 ADR / 未解決論点**",
]

CHANGELOG_METADATA_FIELDS = [
    "**対象ファイル**",
    "**カバー率（REQ単位）**",
    "**最終更新**",
    "**更新エージェント**",
    "**入力ソース**",
]

CHANGELOG_COMMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sources", re.compile(r"<!-- sources: (.+) -->")),
    ("generated_at", re.compile(r"<!-- generated_at: \S+ -->")),
    ("generator", re.compile(r"<!-- generator: \S.+ -->")),
]


# --------------------------------------------------------------------------- #
# 検証ロジック
# --------------------------------------------------------------------------- #

def _validate_patterns(
    content: str, patterns: list[tuple[str, re.Pattern[str]]]
) -> list[str]:
    errors: list[str] = []
    positions: list[tuple[str, int]] = []
    for name, pattern in patterns:
        match = pattern.search(content)
        if match is None:
            errors.append(f"[SECTION] 必須セクション「{name}」が見つかりません。")
        else:
            positions.append((name, match.start()))
    for (previous_name, previous), (name, position) in zip(positions, positions[1:]):
        if position < previous:
            errors.append(
                f"[SECTION] 必須セクション「{name}」は"
                f"「{previous_name}」より後に配置してください。"
            )
    return errors


def _validate_fields(content: str, fields: list[str]) -> list[str]:
    return [
        f"[METADATA] 必須フィールド「{field}」が見つかりません。"
        for field in fields
        if field not in content
    ]


def _validate_main(content: str) -> list[str]:
    errors: list[str] = []
    if len(content) > MAX_FILE_SIZE_CHARS:
        errors.append(
            f"[SIZE] ファイルサイズ {len(content)} 文字が上限 "
            f"{MAX_FILE_SIZE_CHARS} 文字を超えています。"
        )
    errors.extend(_validate_patterns(content, MAIN_SECTION_PATTERNS))
    errors.extend(_validate_fields(content, MAIN_METADATA_FIELDS))
    return errors


def _validate_changelog(content: str) -> list[str]:
    errors = _validate_patterns(content, CHANGELOG_SECTION_PATTERNS)
    errors.extend(_validate_fields(content, CHANGELOG_METADATA_FIELDS))

    comments: dict[str, re.Match[str]] = {}
    header_lines = content.splitlines()[:3]
    for index, (name, pattern) in enumerate(CHANGELOG_COMMENT_PATTERNS):
        match = pattern.fullmatch(header_lines[index]) if index < len(header_lines) else None
        if match is None:
            errors.append(
                f"[METADATA] 冒頭の必須コメント「{name}」が見つかりません。"
            )
        else:
            comments[name] = match

    sources_match = comments.get("sources")
    if sources_match is not None:
        try:
            sources = json.loads(sources_match.group(1))
        except json.JSONDecodeError:
            errors.append("[METADATA] sources は有効な JSON 配列ではありません。")
        else:
            if not isinstance(sources, list):
                errors.append("[METADATA] sources は JSON 配列でなければなりません。")
    return errors


def validate_file(path: Path) -> list[str]:
    """Validate one main document or ChangeLog and return all errors."""
    errors: list[str] = []

    if not FILENAME_PATTERN.match(path.name):
        errors.append(
            f"[FILENAME] '{path.name}' は D[0-9][0-9]-*.md パターンに合致しません。"
        )

    content = path.read_text(encoding="utf-8")
    if path.name.endswith(CHANGELOG_SUFFIX):
        errors.extend(_validate_changelog(content))
    else:
        errors.extend(_validate_main(content))
    return errors


def validate_pairs(paths: list[Path]) -> list[str]:
    """Require every main document and ChangeLog to have its counterpart."""
    names = {path.name for path in paths}
    errors: list[str] = []
    for path in paths:
        if path.name.endswith(CHANGELOG_SUFFIX):
            counterpart = path.name.removesuffix(CHANGELOG_SUFFIX) + ".md"
        else:
            counterpart = path.stem + CHANGELOG_SUFFIX
        if counterpart not in names:
            errors.append(
                f"[PAIR] '{path.name}' に対応する '{counterpart}' が見つかりません。"
            )
    return errors


def main(knowledge_dir: Path) -> int:
    """knowledge_dir 内の全 D??-*.md を検証する。終了コード: 0=成功, 1=エラー。"""
    target_files = sorted(knowledge_dir.glob("D[0-9][0-9]-*.md"))

    if not target_files:
        print(f"INFO: {knowledge_dir} に対象ファイルが見つかりませんでした。スキップします。")
        return 0

    total_errors = 0
    for file_path in target_files:
        errors = validate_file(file_path)
        if errors:
            total_errors += len(errors)
            print(f"\n❌ {file_path.name}")
            for err in errors:
                print(f"   {err}")
        else:
            print(f"✅ {file_path.name}")

    pair_errors = validate_pairs(target_files)
    if pair_errors:
        total_errors += len(pair_errors)
        print("\n❌ 本文 / ChangeLog ペア")
        for err in pair_errors:
            print(f"   {err}")

    print()
    if total_errors > 0:
        print(f"FAIL: {total_errors} 件のエラーが検出されました。")
        return 1
    else:
        print(f"PASS: {len(target_files)} ファイルすべてが検証を通過しました。")
        return 0


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent.parent
    knowledge_path = repo_root / "knowledge"

    if len(sys.argv) > 1:
        arg_path = Path(sys.argv[1])
        # Resolve relative paths against repo_root for consistent behaviour in CI and local runs
        knowledge_path = arg_path if arg_path.is_absolute() else (repo_root / arg_path)

    if not knowledge_path.is_dir():
        print(f"ERROR: ディレクトリが見つかりません: {knowledge_path}")
        sys.exit(1)

    sys.exit(main(knowledge_path))
