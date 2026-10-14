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

# ---------------------------------------------------------------------------------------------
# FR-1025..FR-1030 / NFR-PERF-004 fixtures.  PROVISIONAL FORMAT (仮置き): the requirements leave the concrete
# notation to the implementation.  Assumed here, adjust once fixed:
#   * columns: under the catalog "テーブル" section, one sub-heading per table
#         ### 列: orders
#         対象エンティティ: 注文
#         | 列名 | 型 | キー | 参照先 | 説明 |
#         |---|---|---|---|---|
#         | id | int | 主キー | | 注文番号 |
#         | customer_id | int | 外部キー | 顧客.id | 購入者 |
#   * relations between entities: optional field on a requirement
#         - エンティティの関係: 注文→商品（参照）
#   * Studio contract (3D is a canvas, so state is read from a published object; also mirrored in DOM for 2D/entities):
#         [data-testid="semantic-zoom"]  attrs  data-scale (number)  data-level (overview|mid|detail)  data-ready ("true" when operable)
#         window.eabkView.setScale(n)    -> set magnification (1 = whole fits)
#         window.eabkView.getState()     -> {scale, level, clusters:[{id,count,entities:[name]}],
#                                            entities:[name], edges:[{from,to,kind}],  kind in 外部キー|参照|使用
#                                            columns:{<entity>:[{name,type,key,ref}]}}   (columns only at level "detail")
#         2D DOM: [data-entity="名"], [data-edge][data-from][data-to][data-kind], [data-column]
#   * routes: #/entities, #/map2d, #/map3d
# ---------------------------------------------------------------------------------------------
ZOOM_ENTITIES = {"注文": "購入内容", "顧客": "購入者", "商品": "販売品", "在庫": "倉庫の数量"}
ZOOM_COLUMNS = {
    "orders": ("注文", [("id", "int", "主キー", "", "注文番号"), ("customer_id", "int", "外部キー", "顧客.id", "購入者"), ("item", "text", "なし", "", "品目")]),
    "customers": ("顧客", [("id", "int", "主キー", "", "顧客番号"), ("name", "text", "なし", "", "氏名")]),
}


def _col_section(table: str, entity: str, cols: list[tuple[str, str, str, str, str]]) -> str:
    rows = "\n".join(f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in cols)
    return f"\n### 列: {table}\n対象エンティティ: {entity}\n| 列名 | 型 | キー | 参照先 | 説明 |\n|---|---|---|---|---|\n{rows}\n"


def make_zoom(root: Path) -> Path:
    """4 entities; 注文→顧客 (FK via column), 注文→商品 (requirement relation), 在庫 isolated; 商品 has no columns."""
    root.mkdir(parents=True, exist_ok=True)
    _base(root)
    (root / "docs").mkdir(exist_ok=True)
    reqs = [
        _req("FR-001", "注文登録", "注文、顧客", "注文（作成）", "1", 1),
        _req("FR-002", "商品登録", "商品", "商品（作成）", "1", 2).replace(
            "- 受入基準", "- エンティティの関係: 注文→商品（参照）\n- 受入基準", 1),
        _req("FR-003", "在庫確認", "在庫", "在庫（参照）", "2", 3),
    ]
    (root / DOC).write_text(build_doc(ZOOM_ENTITIES, [], reqs), encoding="utf-8")
    cat = build_catalog([("orders", "db/orders.sql", "FR-001"), ("customers", "db/customers.sql", "FR-001")], ["FR-001", "FR-002", "FR-003"])
    for t, (e, cols) in ZOOM_COLUMNS.items():
        cat += _col_section(t, e, cols)
    (root / CAT).write_text(cat, encoding="utf-8")
    return root


def make_large(root: Path, entities: int = 300, columns: int = 5000) -> Path:
    """PARAM-019 / PARAM-020 scale synthetic data: chain-linked clusters of 10 entities, columns spread evenly."""
    root.mkdir(parents=True, exist_ok=True)
    _base(root)
    (root / "docs").mkdir(exist_ok=True)
    names = {f"E{i:04d}": f"エンティティ{i}" for i in range(entities)}
    per, extra = divmod(columns, entities)
    reqs, tables, secs = [], [], []
    for i, n in enumerate(names):
        rel = f"- エンティティの関係: {n}→E{i - 1:04d}（参照）\n" if i % 10 else ""
        r = _req(f"FR-{i + 1:04d}", f"要求{i}", n, f"{n}（作成）", "1", i + 1)
        reqs.append(r.replace("- 受入基準", rel + "- 受入基準", 1) if rel else r)
        tables.append((f"t{i:04d}", f"db/t{i:04d}.sql", f"FR-{i + 1:04d}"))
        k = per + (1 if i < extra else 0)
        cols = [("id", "int", "主キー", "", "識別子")] + [(f"c{j}", "text", "なし", "", f"列{j}") for j in range(1, k)]
        secs.append(_col_section(f"t{i:04d}", n, cols))
    (root / DOC).write_text(build_doc(names, [], reqs), encoding="utf-8")
    (root / CAT).write_text(build_catalog(tables, [f"FR-{i + 1:04d}" for i in range(entities)]) + "".join(secs), encoding="utf-8")
    return root