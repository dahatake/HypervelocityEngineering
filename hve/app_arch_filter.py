"""app_arch_filter.py — 推薦アーキテクチャによる APP-ID フィルタリング

`docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` を正本として、
workflow に対応する推薦アーキテクチャの APP-ID のみを返す共通ロジック。

hve アプリケーションと GitHub Actions の双方から利用可能。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# workflow_id → 内部分類
_WORKFLOW_TARGET_KIND: Dict[str, str] = {
    "aad-web":  "web-cloud",
    "asdw-web": "web-cloud",
    "abd":      "batch",
    "abdv":     "batch",
}

# 推薦アーキテクチャ文字列 → 内部分類
_ARCH_KIND_MAP: Dict[str, str] = {
    "Webフロントエンド + クラウド":  "web-cloud",
    "Webフロントエンド+クラウド":    "web-cloud",
    "Webフロントエンド ＋ クラウド": "web-cloud",
    "データバッチ処理":              "batch",
    "バッチ":                        "batch",
}

_CATALOG_SECTION = "A) サマリ表（全APP横断）"
_DEFAULT_CATALOG_PATH = "docs/catalog/app-arch-catalog.md"


# ---------------------------------------------------------------------------
# 結果データクラス
# ---------------------------------------------------------------------------


@dataclass
class ExcludedAppId:
    app_id: str
    actual_architecture: str
    reason: str = "target_arch_mismatch"

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "actual_architecture": self.actual_architecture,
            "reason": self.reason,
        }


@dataclass
class AppArchFilterResult:
    workflow_id: str
    target_kind: str
    target_architectures: List[str]
    requested_app_ids: Optional[List[str]]
    matched_app_ids: List[str]
    excluded_app_ids: List[ExcludedAppId] = field(default_factory=list)
    unknown_app_ids: List[str] = field(default_factory=list)
    catalog_path: str = _DEFAULT_CATALOG_PATH
    catalog_found: bool = True

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "target_kind": self.target_kind,
            "target_architectures": self.target_architectures,
            "requested_app_ids": self.requested_app_ids,
            "matched_app_ids": self.matched_app_ids,
            "excluded_app_ids": [e.to_dict() for e in self.excluded_app_ids],
            "unknown_app_ids": self.unknown_app_ids,
            "catalog_path": self.catalog_path,
            "markdown_section": self.to_markdown_section(),
        }

    def to_markdown_section(self) -> str:
        """app-arch filter 結果を Markdown セクションとして返す。"""
        if not self.matched_app_ids:
            return ""

        arch_list = "、".join(self.target_architectures)
        id_list = ", ".join(f"`{aid}`" for aid in self.matched_app_ids)
        lines = [
            "",
            "## 推薦アーキテクチャ スコープ",
            f"- 推薦アーキテクチャ: **{arch_list}**",
            f"- 対象 APP-ID: {id_list}",
            f"- 正本: `{self.catalog_path}` の `{_CATALOG_SECTION}`",
        ]
        if self.excluded_app_ids:
            excluded = ", ".join(f"`{e.app_id}`" for e in self.excluded_app_ids)
            lines.append(f"- 対象外 APP-ID: {excluded}（推薦アーキテクチャ不一致）")
        if self.unknown_app_ids:
            unknown = ", ".join(f"`{aid}`" for aid in self.unknown_app_ids)
            lines.append(f"- 不明 APP-ID（catalog 未記載）: {unknown}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# catalog 読み取り
# ---------------------------------------------------------------------------


def _normalize_arch_whitespace(arch: str) -> str:
    """前後スペースを除去して空白を正規化する。"""
    return re.sub(r"\s+", " ", arch.strip())


def _classify_arch(arch: str) -> Optional[str]:
    """推薦アーキテクチャ文字列を内部分類に変換する。None = 未知。"""
    normalized = _normalize_arch_whitespace(arch)
    return _ARCH_KIND_MAP.get(normalized)


def _parse_catalog(catalog_path: str) -> Dict[str, str]:
    """catalog ファイルの `A) サマリ表（全APP横断）` を読み取り、
    APP-ID → 推薦アーキテクチャ のマップを返す。

    Raises:
        FileNotFoundError: catalog ファイルが存在しない
        ValueError: 必須セクション/列が不在または table が読めない
    """
    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(f"catalog ファイルが見つかりません: {catalog_path}")

    content = path.read_text(encoding="utf-8")

    # セクション抽出
    m = re.search(
        r"##\s*A\)\s*サマリ表（全APP横断）\s*\n(.*?)(?=\n##\s|\Z)",
        content,
        re.DOTALL,
    )
    if not m:
        raise ValueError(
            f"catalog に `{_CATALOG_SECTION}` セクションが見つかりません: {catalog_path}"
        )

    section = m.group(1)

    # Markdown table 行を収集
    table_lines = [
        line.strip() for line in section.splitlines()
        if line.strip().startswith("|")
    ]
    if len(table_lines) < 2:
        raise ValueError(
            f"`{_CATALOG_SECTION}` に Markdown テーブルが見つかりません: {catalog_path}"
        )

    # ヘッダ行（| APP-ID | APP名 | 推薦アーキテクチャ | ... |）
    header_line = table_lines[0]
    header_cols = [c.strip() for c in header_line.strip("|").split("|")]

    def _find_column_index(names: List[str]) -> int:
        for name in names:
            for i, h in enumerate(header_cols):
                if name in h:
                    return i
        return -1

    appid_col = _find_column_index(["APP-ID"])
    arch_col = _find_column_index(["推薦アーキテクチャ"])

    if appid_col < 0:
        raise ValueError(
            f"`{_CATALOG_SECTION}` に `APP-ID` 列が見つかりません: {catalog_path}"
        )
    if arch_col < 0:
        raise ValueError(
            f"`{_CATALOG_SECTION}` に `推薦アーキテクチャ` 列が見つかりません: {catalog_path}"
        )

    result: Dict[str, str] = {}

    # セパレータ行（|---|---| など）をスキップしてデータ行を処理
    for line in table_lines[1:]:
        if re.match(r"^\|[\s\-|]+\|$", line):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) <= max(appid_col, arch_col):
            continue
        app_id = cols[appid_col].strip()
        arch = cols[arch_col].strip()
        if app_id and arch and re.match(r"APP-\d+", app_id):
            result[app_id] = arch

    return result


# ---------------------------------------------------------------------------
# メイン API
# ---------------------------------------------------------------------------


def resolve_app_arch_scope(
    workflow_id: str,
    requested_app_ids: Optional[List[str]] = None,
    catalog_path: str = _DEFAULT_CATALOG_PATH,
    dry_run: bool = False,
) -> AppArchFilterResult:
    """推薦アーキテクチャに基づいて APP-ID をフィルタリングする。

    Args:
        workflow_id: ワークフロー ID（"aad-web", "asdw-web", "abd", "abdv"）
        requested_app_ids: 指定 APP-ID リスト。None / 空の場合は全 APP が対象。
        catalog_path: app-arch-catalog.md のパス（デフォルト: docs/catalog/app-arch-catalog.md）
        dry_run: True の場合、catalog 不在でも warning を出して空リストを返す。

    Returns:
        AppArchFilterResult

    Raises:
        FileNotFoundError: dry_run=False かつ catalog 不在
        ValueError: dry_run=False かつ必須セクション/列が不在
    """
    wf_lower = workflow_id.lower()
    target_kind = _WORKFLOW_TARGET_KIND.get(wf_lower)

    # 対応する推薦アーキテクチャ文字列のリスト
    target_architectures = [
        arch for arch, kind in _ARCH_KIND_MAP.items() if kind == target_kind
    ]

    empty_result = AppArchFilterResult(
        workflow_id=workflow_id,
        target_kind=target_kind or "",
        target_architectures=target_architectures,
        requested_app_ids=requested_app_ids,
        matched_app_ids=[],
        catalog_path=catalog_path,
        catalog_found=False,
    )

    # catalog 読み取り
    try:
        catalog: Dict[str, str] = _parse_catalog(catalog_path)
    except FileNotFoundError as exc:
        if dry_run:
            print(
                f"⚠️ WARNING: {exc}（dry-run モード: フィルタをスキップして続行します）",
                file=sys.stderr,
            )
            return empty_result
        raise
    except ValueError as exc:
        if dry_run:
            print(
                f"⚠️ WARNING: {exc}（dry-run モード: フィルタをスキップして続行します）",
                file=sys.stderr,
            )
            return empty_result
        raise

    # target_kind が不明なワークフローは全 APP を返す（filter 不要）
    if not target_kind:
        all_ids = list(catalog.keys())
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind="",
            target_architectures=[],
            requested_app_ids=requested_app_ids,
            matched_app_ids=all_ids if not requested_app_ids else [
                aid for aid in (requested_app_ids or []) if aid in catalog
            ],
            catalog_path=catalog_path,
        )

    # catalog から対象アーキテクチャの APP-ID を取得
    catalog_target_ids = [
        app_id
        for app_id, arch in catalog.items()
        if _classify_arch(arch) == target_kind
    ]

    if requested_app_ids:
        # 指定ありのケース: 指定 APP-ID を catalog で検証・フィルタ
        matched: List[str] = []
        excluded: List[ExcludedAppId] = []
        unknown: List[str] = []

        for aid in requested_app_ids:
            if aid not in catalog:
                unknown.append(aid)
            elif _classify_arch(catalog[aid]) == target_kind:
                matched.append(aid)
            else:
                excluded.append(ExcludedAppId(
                    app_id=aid,
                    actual_architecture=catalog[aid],
                ))

        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind=target_kind,
            target_architectures=target_architectures,
            requested_app_ids=requested_app_ids,
            matched_app_ids=matched,
            excluded_app_ids=excluded,
            unknown_app_ids=unknown,
            catalog_path=catalog_path,
        )
    else:
        # 指定なしのケース: catalog から対象アーキテクチャの全 APP-ID を返す
        return AppArchFilterResult(
            workflow_id=workflow_id,
            target_kind=target_kind,
            target_architectures=target_architectures,
            requested_app_ids=None,
            matched_app_ids=catalog_target_ids,
            catalog_path=catalog_path,
        )


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="推薦アーキテクチャによる APP-ID フィルタリング"
    )
    parser.add_argument("--workflow", required=True, help="ワークフロー ID (例: aad-web, abd)")
    parser.add_argument(
        "--app-ids",
        default=None,
        help="対象 APP-ID をカンマ区切りで指定（省略時: catalog から自動選択）",
    )
    parser.add_argument(
        "--catalog",
        default=_DEFAULT_CATALOG_PATH,
        help=f"app-arch-catalog.md のパス（デフォルト: {_DEFAULT_CATALOG_PATH}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="dry-run モード（catalog 不在でも warning 継続）",
    )
    args = parser.parse_args()

    requested: Optional[List[str]] = None
    if args.app_ids:
        requested = [s.strip() for s in args.app_ids.split(",") if s.strip()]

    try:
        result = resolve_app_arch_scope(
            workflow_id=args.workflow,
            requested_app_ids=requested,
            catalog_path=args.catalog,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
        sys.exit(1)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
