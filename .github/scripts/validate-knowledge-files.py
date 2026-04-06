#!/usr/bin/env python3
"""
validate-knowledge-files.py
knowledge/ フォルダーの D クラス要求定義書ドラフトファイルを検証するスクリプト。

検証項目:
  1. ファイル名が D[0-9][0-9]-*.md パターンに合致すること
  2. 必須セクション見出し（§1〜§8 + 付録 A）が存在すること
  3. metadata-block の必須フィールドが存在すること
  4. ファイルサイズが 20,000 文字以下であること
"""

import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# 定数
# --------------------------------------------------------------------------- #

FILENAME_PATTERN = re.compile(r"^D\d{2}-.+\.md$")

MAX_FILE_SIZE_CHARS = 20_000

# 必須セクション見出しを正規表現パターンで定義（行頭 ## から始まる見出し行を厳密に検索）
# §3 は長い括弧付きのヘッダーなので prefix match を使用（意図的）
REQUIRED_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("§1 目的と背景",       re.compile(r"^## 1\. 目的と背景", re.MULTILINE)),
    ("§2 確定事項",         re.compile(r"^## 2\. 確定事項（Confirmed）", re.MULTILINE)),
    ("§3 設計仮定",         re.compile(r"^## 3\. 設計仮定（Tentative", re.MULTILINE)),
    ("§4 未確定事項",       re.compile(r"^## 4\. 未確定事項（Unknown）", re.MULTILINE)),
    ("§5 最低内容カバー状況", re.compile(r"^## 5\. 最低内容カバー状況", re.MULTILINE)),
    ("§6 不足判定",         re.compile(r"^## 6\. 不足判定・推奨アクション", re.MULTILINE)),
    ("§7 状態サマリー",     re.compile(r"^## 7\. 状態サマリー", re.MULTILINE)),
    ("§8 関連文書",         re.compile(r"^## 8\. 関連文書", re.MULTILINE)),
    ("付録 A",              re.compile(r"^## 付録 A", re.MULTILINE)),
]

REQUIRED_METADATA_FIELDS = [
    "**D クラス**",
    "**文書名**",
    "**必須度**",
    "**総合状態**",
    "**カバー率**",
    "**最終更新**",
    "**更新エージェント**",
    "**入力ソース**",
    "**Prompt投入可否**",
    "**関連 ADR / 未解決論点**",
]


# --------------------------------------------------------------------------- #
# 検証ロジック
# --------------------------------------------------------------------------- #

def validate_file(path: Path) -> list[str]:
    """1 ファイルを検証し、エラーメッセージのリストを返す（空 = OK）。"""
    errors: list[str] = []

    # 1. ファイル名パターン
    if not FILENAME_PATTERN.match(path.name):
        errors.append(
            f"[FILENAME] '{path.name}' は D[0-9][0-9]-*.md パターンに合致しません。"
        )

    content = path.read_text(encoding="utf-8")

    # 2. ファイルサイズ
    if len(content) > MAX_FILE_SIZE_CHARS:
        errors.append(
            f"[SIZE] ファイルサイズ {len(content)} 文字が上限 {MAX_FILE_SIZE_CHARS} 文字を超えています。"
        )

    # 3. 必須セクション見出し（行頭 ## から始まる正規表現で厳密に検索）
    for section_name, pattern in REQUIRED_SECTION_PATTERNS:
        if not pattern.search(content):
            errors.append(f"[SECTION] 必須セクション「{section_name}」が見つかりません。")

    # 4. metadata-block 必須フィールド
    for field in REQUIRED_METADATA_FIELDS:
        if field not in content:
            errors.append(f"[METADATA] 必須フィールド「{field}」が見つかりません。")

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
