#!/usr/bin/env python3
"""Agent ヘディング正規化スクリプト（dry-run 既定）.

R07 タスクで策定した規格 (docs/agent-heading-standard.md) に基づき、
.github/agents/*.agent.md の H2 セクションを正規化する。

- 既定は dry-run: 書き込みを行わず unified diff を stdout に出力
- --apply で実際に書き込む（破壊的）
- スキップ対象: XML タグ系 5 ファイル + 先頭 H2 非標準 1 ファイル + 個別判断対象

使い方:
    python tools/normalize-agent-headings.py              # 全ファイルを dry-run
    python tools/normalize-agent-headings.py --file PATH  # 1 ファイルのみ dry-run
    python tools/normalize-agent-headings.py --apply      # 全ファイル書き込み (危険)
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".github" / "agents"

# XML タグ系 5 ファイル + 先頭非標準 1 ファイル（合計 6 件をスキップ）
SKIP_FILES = {
    "Arch-ArchitectureCandidateAnalyzer.agent.md",
    "Arch-TDD-TestSpec.agent.md",
    "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md",
    "Dev-Microservice-Azure-DataDeploy.agent.md",
    "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.agent.md",
}
# `## 0) モードディスパッチ` を先頭に持つファイルは個別判断のため自動検出してスキップ
NONSTANDARD_FIRST_H2 = "## 0) モードディスパッチ"

# リネームマッピング（R07-heading-mapping.md の「リネーム」エントリのみ反映）
# 「個別判断」エントリは含まない（破壊的なため S5d 手動対応）
RENAME_MAP: dict[str, str] = {
    # 目的系 → C1
    "## 1) 役割（このエージェントがやること）": "## 1) 目的と非目的",
    "## 1) 目的": "## 1) 目的と非目的",
    "## 1) 適用範囲（このエージェントの役割）": "## 1) 目的と非目的",
    "## 1. 概要": "## 1) 目的と非目的",
    # 入力系 → C2
    "## 1) 入力（置換必須）": "## 2) 入力（必ず参照）",
    "## 1) 入力（必読ソース）": "## 2) 入力（必ず参照）",
    "## 2) 入力（必読）": "## 2) 入力（必ず参照）",
    "## 2) 入力": "## 2) 入力（必ず参照）",
    # 出力系 → C3
    "## 出力方法": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 3) 出力先（成果物）": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 3) 成果物（必須）": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 5) 出力（copilot-instructions.md §8 準拠）": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 5) 出力ルール": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 4) 成果物保存": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 2) 成果物（固定）": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    "## 3) 出力（必須）": "## 3) 出力フォーマット（Markdown固定スキーマ）",
    # 手順系 → C4
    "## 3) 実行手順（決定的）": "## 4) 実行手順（順序固定）",
    "## 5) 作業手順（この順番で）": "## 4) 実行手順（順序固定）",
    "## 5) 実行フロー（DAG）": "## 4) 実行手順（順序固定）",
    "## 6) 実行手順（この順で）": "## 4) 実行手順（順序固定）",
    "## 5) 実行手順（この順で）": "## 4) 実行手順（順序固定）",
    "## 3) 実行手順": "## 4) 実行手順（順序固定）",
    # 品質系 → C5
    "## 4) 重要制約（品質と安全）": "## 5) 品質原則（必ず守る）",
    # チェック系 → C6
    "## 8) 最終チェックと品質レビュー（必須）": "## 6) セルフチェック（出力前に必ず確認）",
    # 完了系 → C7
    "## 8) 完了条件（DoD）": "## 7) 完了条件",
    # 禁止事項系 → C10
    "## 8) 禁止事項（このタスク固有）": "## 禁止事項",
    "## 7) 禁止事項（このタスク固有）": "## 禁止事項",
}


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_content(content: str) -> tuple[str, list[str]]:
    """ヘディング正規化を適用し、(新コンテンツ, 適用された変更リスト) を返す.

    リネームのみ実施し、セクションの並び替えは行わない（並び替えは破壊リスク大のため S5d 手動対応）。
    """
    changes: list[str] = []
    lines = content.splitlines(keepends=True)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped in RENAME_MAP:
            new_heading = RENAME_MAP[stripped]
            eol = line[len(stripped):]
            new_lines.append(new_heading + eol)
            changes.append(f"{stripped!r} -> {new_heading!r}")
        else:
            new_lines.append(line)
    return "".join(new_lines), changes


def should_skip(path: Path, content: str) -> str | None:
    if path.name in SKIP_FILES:
        return "XML タグ系スキップ対象"
    # 先頭 H2 が非標準かチェック
    for line in content.splitlines():
        if line.startswith("## "):
            if line.rstrip() == NONSTANDARD_FIRST_H2:
                return f"先頭非標準 H2: {NONSTANDARD_FIRST_H2}"
            break
    return None


def process_file(path: Path, *, apply: bool) -> dict:
    content = load_file(path)
    skip_reason = should_skip(path, content)
    if skip_reason:
        return {"file": path.name, "status": "skipped", "reason": skip_reason}

    new_content, changes = normalize_content(content)
    if not changes:
        return {"file": path.name, "status": "no-change", "changes": []}

    # 重複 H2 検出（S4 で発覚した安全策）
    new_h2s = [
        line.rstrip() for line in new_content.splitlines() if line.startswith("## ")
    ]
    if len(set(new_h2s)) < len(new_h2s):
        from collections import Counter

        dups = [h for h, c in Counter(new_h2s).items() if c > 1]
        return {
            "file": path.name,
            "status": "conflict",
            "changes": changes,
            "duplicates": dups,
        }

    diff = list(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            n=2,
        )
    )

    if apply:
        path.write_text(new_content, encoding="utf-8")
        status = "applied"
    else:
        status = "dry-run"

    return {
        "file": path.name,
        "status": status,
        "changes": changes,
        "diff": "".join(diff),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="実際に書き込む（既定は dry-run）")
    parser.add_argument("--file", type=Path, help="特定ファイルのみ処理（リポジトリ相対 or 絶対パス）")
    parser.add_argument("--summary-only", action="store_true", help="diff を表示せず件数のみ")
    args = parser.parse_args()

    if args.file:
        target_files = [args.file if args.file.is_absolute() else REPO_ROOT / args.file]
    else:
        target_files = sorted(AGENTS_DIR.glob("*.agent.md"))

    summary = {"total": 0, "skipped": 0, "no-change": 0, "changed": 0, "conflict": 0}
    detailed: list[dict] = []
    for path in target_files:
        summary["total"] += 1
        result = process_file(path, apply=args.apply)
        detailed.append(result)
        if result["status"] == "skipped":
            summary["skipped"] += 1
        elif result["status"] == "no-change":
            summary["no-change"] += 1
        elif result["status"] == "conflict":
            summary["conflict"] += 1
        else:
            summary["changed"] += 1

    # 出力
    for r in detailed:
        if r["status"] == "skipped":
            print(f"[SKIP] {r['file']}: {r['reason']}")
        elif r["status"] == "no-change":
            if not args.summary_only:
                print(f"[OK]   {r['file']}: no change")
        elif r["status"] == "conflict":
            print(
                f"[CONFLICT] {r['file']}: {len(r['changes'])} rename(s) "
                f"but produces duplicate H2: {r['duplicates']}"
            )
            print("           -> 手動修正必須 (S5d バケット)")
        else:
            print(f"[{r['status'].upper()}] {r['file']}: {len(r['changes'])} rename(s)")
            for c in r["changes"]:
                print(f"       {c}")
            if not args.summary_only and r.get("diff"):
                print(r["diff"])

    print()
    print("=" * 60)
    print(
        f"Total: {summary['total']}, Skipped: {summary['skipped']}, "
        f"NoChange: {summary['no-change']}, Changed: {summary['changed']}, "
        f"Conflict: {summary['conflict']}"
    )
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    if args.apply and summary["conflict"] > 0:
        print("WARNING: conflict ファイルは書き込みをスキップしました（手動修正必要）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
