"""Disposable EABK target repositories for the entity features (FR-1020..FR-1024, NFR-COMPAT-003).

Test-oracle helper only.  The documents are built from the structure of docs/requirements-definition.md
(用語表 3.3 / 状態表 3.4 / 利用シナリオ 5 / 各要求の `対象エンティティ` 欄) and docs/catalog.md (テーブル表).

ASSUMED CONTRACT (not stated in the requirements; adjust here once the implementation fixes it):
  * optional fields on a requirement:  `- エンティティの使い方: 注文（作成）、顧客（参照）`
                                       `- 利用シナリオ: 1、2`
  * commands (docs/catalog.md has no command name yet):
      python scripts/entities.py list  [--repo DIR]   # entity ledger (FR-1020)
      python scripts/entities.py check [--repo DIR]   # enterprise data catalog reconciliation (FR-1023)
      python scripts/entities.py todo  [--repo DIR]   # ToDo rows in question-sheet form (FR-1024)
    run with cwd = the target repository, `scripts/` copied from the toolkit.
  * Studio hash route for the CRUD matrix: `#/entities`.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
SEP = "\u3000"  # full-width space used between fields of a requirement

DOC = "docs/requirements-definition.md"
CAT = "docs/catalog.md"


def _req(rid: str, title: str, entities: str, usage: str | None, scen: str | None, acn: int) -> str:
    lines = [
        f"#### {rid} {title}",
        f"- 要求: {title}を行える。",
        f"- 決定状態: 承認済み（依頼 2026-10-14）{SEP}出自: 依頼原文{SEP}優先度: MUST（テスト用）",
        f"- 上位: G-001{SEP}出典: 依頼原文{SEP}対象エンティティ: {entities}{SEP}関係する状態: なし{SEP}参照パラメータ: なし{SEP}関連する既存資産: なし",
    ]
    if usage:
        lines.append(f"- エンティティの使い方: {usage}")
    if scen:
        lines.append(f"- 利用シナリオ: {scen}")
    lines += [f"- 受入基準 AC-{acn:03d}: {title}が完了する。", "  - 検証レベル: system", ""]
    return "\n".join(lines)


def build_doc(entities: dict[str, str], states: list[tuple[str, str, str]], reqs: list[str]) -> str:
    gl = "\n".join(f"| {n} | {d} | なし |" for n, d in entities.items())
    st = "\n".join(f"| {e} | {s} | {c} |" for e, s, c in states)
    return (
        "# 要求定義書\n\n## 3. 前提・制約\n\n### 3.3 用語\n\n| 用語 | 定義 | 禁止同義語 |\n|---|---|---|\n"
        + (gl + "\n" if gl else "")
        + "\n### 3.4 状態\n\n| 対象エンティティ | 状態 | 遷移の条件 |\n|---|---|---|\n"
        + (st + "\n" if st else "")
        + "\n## 5. 利用シナリオ\n\n1. 利用者が注文を登録する。\n2. 担当者が在庫を確認する。\n\n"
        + "## 6. 要求\n\n### 6.1 機能要求\n\n"
        + "\n".join(reqs)
        + "\n"
    )


def build_catalog(tables: list[tuple[str, str, str]], reqids: list[str]) -> str:
    rows = "\n".join(f"| {r} | 題名 | 承認済み | 未実装 | 未実装 | なし |" for r in reqids)
    tb = "\n".join(f"| {n} | {f} | 台帳 | {r} |" for n, f, r in tables)
    return (
        "# カタログ\n\n## 機能\n\n| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
        + (rows + "\n" if rows else "")
        + "\n## API・イベント\n\n| 名前 | 定義ファイル | 関連する要求 ID |\n|---|---|---|\n"
        + "\n## テーブル\n\n| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |\n|---|---|---|---|\n"
        + (tb + "\n" if tb else "")
        + "\n## 共通部品\n\n| 名前 | 定義ファイル | 関連する要求 ID |\n|---|---|---|\n"
    )


def _base(root: Path, doc_path: str = DOC, cat_path: str = CAT, config_extra: dict | None = None) -> None:
    shutil.copytree(SOURCE / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__", "hooks"))
    mf = {
        "requirements": doc_path,
        "catalog": cat_path,
        "id_registry": "docs/id-registry.md",
        "run_history": "docs/run-history.md",
        "ledger": "tests/system/ledger.json",
        "manual_tests": "docs/manual-tests.md",
    }
    cfg = {"management_files": mf, "base_branch": "main", "work": {"dir": "work", "retention_days": 14}}
    cfg.update(config_extra or {})
    (root / "scripts" / "ebak.config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def make_standard(root: Path) -> Path:
    """3 entities: 注文 (all info), 顧客 (usage missing / no table / no description), 在庫 (unused)."""
    root.mkdir(parents=True, exist_ok=True)
    _base(root)
    (root / "docs").mkdir(exist_ok=True)
    reqs = [
        _req("FR-001", "注文登録", "注文、顧客", "注文（作成）", "1", 1),
        _req("FR-002", "注文照会", "注文", "注文（参照）", "1", 2),
        _req("FR-003", "画面表示のみ", "なし", None, None, 3),
    ]
    (root / DOC).write_text(
        build_doc(
            {"注文": "購入者が確定した購入内容", "在庫": "倉庫にある商品の数量"},
            [("注文", "確定", "支払いが完了したとき"), ("注文", "出荷済み", "倉庫から出荷されたとき")],
            reqs,
        ),
        encoding="utf-8",
    )
    (root / CAT).write_text(
        build_catalog([("orders", "db/orders.sql", "FR-001、FR-002")], ["FR-001", "FR-002", "FR-003"]),
        encoding="utf-8",
    )
    return root


def make_other(root: Path) -> Path:
    """Different management file paths, 0 entities, no catalog tables, no optional fields, no enterprise-catalog setting."""
    root.mkdir(parents=True, exist_ok=True)
    _base(root, "spec/req.md", "spec/cat.md")
    (root / "spec").mkdir(exist_ok=True)
    (root / "spec" / "req.md").write_text(build_doc({}, [], [_req("FR-001", "ほげ", "なし", None, None, 1)]), encoding="utf-8")
    # catalog absent on purpose
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts
    }


def run_entities(root: Path, *args: str):
    import os
    import subprocess

    return subprocess.run(
        [sys.executable, "scripts/entities.py", *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONUTF8="1"),
    )
