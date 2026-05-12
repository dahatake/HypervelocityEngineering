"""catalog_parsers.py — Fan-out 用カタログパーサ集約 (ADR-0002 G-1)

各ワークフローの fan-out キーを動的に解決するためのパーサを 1 モジュールに集約する。
カタログファイルが存在しない場合は空リストを返し、呼び出し側で K-1 (fanout-empty)
として skip 処理する前提。

== 公開 API ==
- parse_catalog(kind: str, repo_root: Path) -> List[str]
- KNOWN_PARSERS : 登録済みパーサ名のフローズンセット

== 登録パーサ ==
- "app_catalog"        : docs/catalog/app-catalog.md
- "screen_catalog"     : docs/catalog/screen-catalog.md
- "service_catalog"    : docs/catalog/service-catalog.md
- "batch_job_catalog"  : docs/batch/batch-job-catalog.md
- "agent_catalog"      : docs/agent/agent-application-definition.md

== 設計方針 ==
- カタログは必ず Markdown テーブルまたは見出し ``## {ID}`` 形式で ID を列挙する想定。
- パース失敗は ParserError に統一し、呼び出し側で K-1 skip にフォールバック可能。
- 重複 ID は除去し、出現順序を保持する。
- 捏造禁止: ファイル不在時は空リスト + warning ログ。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional


class CatalogParseError(Exception):
    """カタログの構造が想定外の場合に投げる例外。"""


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _read_text(repo_root: Path, rel_path: str) -> Optional[str]:
    """カタログを安全に読み込む。存在しない場合は None。"""
    p = (repo_root / rel_path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _extract_ids_from_table(
    text: str,
    *,
    id_pattern: str,
    column_index: int = 0,
) -> List[str]:
    """Markdown テーブルの指定列から id_pattern にマッチする値を順序付きで返す。

    Args:
        text: カタログ全文。
        id_pattern: ID として認める正規表現（^/$ なしの部分一致）。
        column_index: 0-indexed のテーブル列。
    """
    pat = re.compile(id_pattern)
    found: List[str] = []
    seen: set = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        # 区切り行（| --- | --- |）はスキップ
        if re.match(r"^\|\s*[-:\s|]+\s*\|?$", s):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if column_index >= len(cols):
            continue
        cell = cols[column_index]
        # セル内に含まれる ID を抽出（バッククォート/カッコ等は無視）
        for m in pat.finditer(cell):
            val = m.group(0)
            if val in seen:
                continue
            seen.add(val)
            found.append(val)
    return found


def _extract_ids_from_headings(text: str, *, id_pattern: str) -> List[str]:
    """``## {ID}`` または ``### {ID}`` 形式の見出しから id_pattern にマッチする値を返す。"""
    pat = re.compile(id_pattern)
    found: List[str] = []
    seen: set = set()
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("## ") or s.startswith("### ")):
            continue
        for m in pat.finditer(s):
            val = m.group(0)
            if val in seen:
                continue
            seen.add(val)
            found.append(val)
    return found


# ---------------------------------------------------------------------------
# パーサ実装
# ---------------------------------------------------------------------------

_APP_ID_PATTERN = r"APP-\d{2,3}"
_SCREEN_ID_PATTERN = r"SC-[A-Za-z0-9_\-]+"
_SERVICE_ID_PATTERN = r"SVC-[A-Za-z0-9_\-]+"
_BATCH_JOB_ID_PATTERN = r"JOB-[A-Za-z0-9_\-]+"
_AGENT_ID_PATTERN = r"AG-[A-Za-z0-9_\-]+"
# Sub-9 (D-2 / ADR-0003): ARD fan-out 用 ID パターン
_BIZ_ID_PATTERN = r"BIZ-\d{2,3}"
_UC_ID_PATTERN = r"UC-[A-Za-z0-9_\-]+"


def parse_app_catalog(repo_root: Path) -> List[str]:
    """docs/catalog/app-catalog.md から ``APP-NN`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/catalog/app-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_APP_ID_PATTERN)
    if not ids:
        # 見出し形式へフォールバック
        ids = _extract_ids_from_headings(text, id_pattern=_APP_ID_PATTERN)
    return ids


def parse_screen_catalog(repo_root: Path) -> List[str]:
    """docs/catalog/screen-catalog.md から ``SC-*`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/catalog/screen-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_SCREEN_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_SCREEN_ID_PATTERN)
    return ids


def parse_service_catalog(repo_root: Path) -> List[str]:
    """docs/catalog/service-catalog.md から ``SVC-*`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/catalog/service-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_SERVICE_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_SERVICE_ID_PATTERN)
    return ids


def parse_batch_job_catalog(repo_root: Path) -> List[str]:
    """docs/batch/batch-job-catalog.md から ``JOB-*`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/batch/batch-job-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_BATCH_JOB_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_BATCH_JOB_ID_PATTERN)
    return ids


def parse_agent_catalog(repo_root: Path) -> List[str]:
    """docs/agent/agent-application-definition.md から ``AG-*`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/agent/agent-application-definition.md")
    if text is None:
        # 後段 (Step 2 出力) のフォールバック
        text = _read_text(repo_root, "docs/agent/agent-architecture.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_AGENT_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_AGENT_ID_PATTERN)
    return ids


def parse_business_candidate(repo_root: Path) -> List[str]:
    """docs/company-business-recommendation.md から ``BIZ-NN`` 形式の ID を抽出する。

    Sub-9 (D-2 / ADR-0003): ARD Step 1.1 fan-out 用。
    Step 1（事業分野候補列挙）の出力ファイルを parse する。
    ファイル不在時は空リストを返し、呼び出し側で K-1 (fanout-empty) skip にフォールバック可能。
    """
    text = _read_text(repo_root, "docs/company-business-recommendation.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_BIZ_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_BIZ_ID_PATTERN)
    return ids


def parse_use_case_skeleton(repo_root: Path) -> List[str]:
    """docs/catalog/use-case-skeleton.md から ``UC-*`` 形式の ID を抽出する。

    Sub-9 (D-2 / ADR-0003): ARD Step 3.2 fan-out 用。
    Step 3.1（ユースケース骨格抽出）の出力ファイルを parse する。
    既存 ``docs/catalog/use-case-catalog.md``（完成版）は対象外。
    """
    text = _read_text(repo_root, "docs/catalog/use-case-skeleton.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_UC_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_UC_ID_PATTERN)
    return ids


# ---------------------------------------------------------------------------
# レジストリ
# ---------------------------------------------------------------------------

_PARSERS: Dict[str, Callable[[Path], List[str]]] = {
    "app_catalog": parse_app_catalog,
    "screen_catalog": parse_screen_catalog,
    "service_catalog": parse_service_catalog,
    "batch_job_catalog": parse_batch_job_catalog,
    "agent_catalog": parse_agent_catalog,
    # Sub-9 (D-2 / ADR-0003): ARD fan-out 用
    "business_candidate": parse_business_candidate,
    "use_case_skeleton": parse_use_case_skeleton,
}

KNOWN_PARSERS: FrozenSet[str] = frozenset(_PARSERS.keys())


def parse_catalog(kind: str, repo_root: Path) -> List[str]:
    """登録済みパーサを呼び出し、fan-out キーのリストを返す。

    Args:
        kind: パーサ名（KNOWN_PARSERS のいずれか）。
        repo_root: リポジトリルート絶対パス。

    Returns:
        ID 文字列の順序付きリスト。カタログ不在時は空リスト。

    Raises:
        CatalogParseError: 未登録の kind が指定された場合。
    """
    fn = _PARSERS.get(kind)
    if fn is None:
        raise CatalogParseError(
            f"未登録の fanout_parser '{kind}'. 有効値: {sorted(KNOWN_PARSERS)}"
        )
    return fn(repo_root)
