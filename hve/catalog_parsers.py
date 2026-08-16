"""catalog_parsers.py — Fan-out 用カタログパーサ集約 (ADR-0002 G-1)

各ワークフローの fan-out キーを動的に解決するためのパーサを 1 モジュールに集約する。
カタログファイルが存在しない場合は空リストを返し、呼び出し側で K-1 (fanout-empty)
として skip 処理する前提。

== 公開 API ==
- parse_catalog(kind: str, repo_root: Path) -> List[str]
- KNOWN_PARSERS : 登録済みパーサ名のフローズンセット

== 登録パーサ ==
- "app_catalog"        : docs/catalog/app-catalog.md
- "screen_catalog"     : docs/catalog/screen-catalog-APP-*.md（per-APP 直読み、合成キー ``APP-NN-S###`` を返却）
- "service_catalog"    : docs/catalog/service-catalog.md
- "dataflow_catalog"  : docs/catalog/app-catalog.md（AAS の共通カタログを SoT として参照）
- "agent_catalog"      : docs/agent/agent-architecture.md（Step 2 の Agent Inventory）
- "design_doc_inventory" : docs/catalog/design-doc-inventory.md（ADI Step 1 の原本目録）

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
_SCREEN_LOCAL_ID_PATTERN = r"S\d{3,}"
_SCREEN_CATALOG_FILE_PATTERN = re.compile(r"^screen-catalog-(APP-\d{2,3})\.md$")
_SERVICE_ID_PATTERN = r"SVC-[A-Za-z0-9_\-]+"
_APP_ID_PATTERN_DATAFLOW = r"JOB-[A-Za-z0-9_\-]+"
_AGENT_ID_PATTERN = r"(?:AGT|AG)-[A-Za-z0-9_\-]+"
# Sub-9 (D-2 / ADR-0003): ARD fan-out 用 ID パターン
_BIZ_ID_PATTERN = r"BIZ-\d{2,3}"
_UC_ID_PATTERN = r"UC-[A-Za-z0-9_\-]+"
# ADI fan-out 用 ID パターン（FR-WF-ADI-08）
_DOC_ID_PATTERN = r"DOC-\d{4}"


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
    """docs/catalog/screen-catalog-APP-*.md 群から ``APP-NN-S###`` 形式の合成キーを抽出する。

    画面 ID は per-APP ファイル内で ``S001`` 形式の安定採番（APP スコープ内で一意）で
    定義されているため、ファイル名から抽出した APP-ID と組み合わせて全体で一意の
    fan-out キーを構築する。
    """
    catalog_dir = repo_root / "docs" / "catalog"
    if not catalog_dir.is_dir():
        return []
    local_pat = re.compile(_SCREEN_LOCAL_ID_PATTERN)
    found: List[str] = []
    seen: set = set()
    # ファイル名昇順で安定した順序を保証
    for path in sorted(catalog_dir.glob("screen-catalog-APP-*.md")):
        m = _SCREEN_CATALOG_FILE_PATTERN.match(path.name)
        if not m:
            continue
        app_id = m.group(1)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        local_ids: List[str] = []
        local_seen: set = set()
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                continue
            if re.match(r"^\|\s*[-:\s|]+\s*\|?$", s):
                continue
            cols = [c.strip() for c in s.strip("|").split("|")]
            if not cols:
                continue
            cell = cols[0]
            for lm in local_pat.finditer(cell):
                val = lm.group(0)
                if val in local_seen:
                    continue
                local_seen.add(val)
                local_ids.append(val)
        for sid in local_ids:
            key = f"{app_id}-{sid}"
            if key in seen:
                continue
            seen.add(key)
            found.append(key)
    return found


def parse_service_catalog(repo_root: Path) -> List[str]:
    """docs/catalog/service-catalog.md から ``SVC-*`` 形式の ID を抽出する。"""
    text = _read_text(repo_root, "docs/catalog/service-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_SERVICE_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_SERVICE_ID_PATTERN)
    return ids


def parse_service_app_mapping(repo_root: Path) -> Dict[str, List[str]]:
    """docs/catalog/service-catalog.md A 節サマリ表から ``SVC-NN`` → ``[APP-NN, ...]`` を抽出する。

    fan-out 展開時の APP-ID フィルタ（app_ids 指定時に該当 APP に紐付く SVC のみ残す）
    で参照される。SVC→APP は service-catalog.md 上で 1:1 を原則とするが、将来複数
    APP に跨る SVC が出現しても破綻しないよう戻り値型を ``Dict[str, List[str]]``
    とし、カンマ / 読点 / 全角カンマ区切りを許容する。

    実装方針:
    - A. サマリ 節（``## A. サマリ`` 以降、``## B.`` 直前まで）のテーブルのみ対象。
    - ヘッダ行から「利用APP」列の 0-indexed 位置を動的検出する（列追加/順序変更に耐性）。
    - SVC-NN 形式の行のみ拾い、利用APP セルから ``APP-\\d{2,3}`` を全件抽出。
    - ファイル不在 / セクション不在 / 列不在の場合は空辞書を返す（呼び出し側で
      フィルタなし扱い）。
    """
    text = _read_text(repo_root, "docs/catalog/service-catalog.md")
    if text is None:
        return {}

    in_summary = False
    header_seen = False
    app_col_idx: Optional[int] = None
    mapping: Dict[str, List[str]] = {}
    svc_pat = re.compile(r"^SVC-\d{2,3}$")
    app_pat = re.compile(_APP_ID_PATTERN)

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## A.") or s.startswith("## A "):
            in_summary = True
            header_seen = False
            app_col_idx = None
            continue
        if in_summary and s.startswith("## ") and not (s.startswith("## A.") or s.startswith("## A ")):
            break
        if not in_summary:
            continue
        if not s.startswith("|"):
            continue
        if re.match(r"^\|\s*[-:\s|]+\s*\|?$", s):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if not header_seen:
            for i, c in enumerate(cols):
                if "利用APP" in c or "利用 APP" in c:
                    app_col_idx = i
                    break
            header_seen = True
            continue
        if app_col_idx is None:
            continue
        if not cols or not svc_pat.match(cols[0]):
            continue
        if app_col_idx >= len(cols):
            continue
        cell = cols[app_col_idx]
        app_ids: List[str] = []
        seen: set = set()
        for m in app_pat.finditer(cell):
            v = m.group(0)
            if v in seen:
                continue
            seen.add(v)
            app_ids.append(v)
        if app_ids:
            mapping[cols[0]] = app_ids
    return mapping


def parse_dataflow_catalog(repo_root: Path) -> List[str]:
    """ADFD fan-out 用に APP-ID を抽出する。

    T3.3 (Phase-3) 以降、ADFD は AAS が SoT として生成する共通カタログを参照する。

    優先順:
      1. ``docs/catalog/app-arch-catalog.md`` があれば、推薦アーキテクチャ
         ``データデータフロー処理`` / ``バッチ`` に該当する APP-ID のみ抽出。
      2. 未生成の場合は ``docs/catalog/app-catalog.md`` の全 APP-ID を返す（フォールバック）。

    関数名と ``dataflow_catalog`` parser キーは fan-out 経路の互換性維持のため残置している。
    """
    # 1) 推薦アーキテクチャでフィルタできる場合はそれを優先
    try:
        from hve.app_arch_filter import resolve_app_arch_scope

        result = resolve_app_arch_scope(
            workflow_id="adfd",
            requested_app_ids=None,
            catalog_path=str(repo_root / "docs/catalog/app-arch-catalog.md"),
            dry_run=True,
        )
        if result.catalog_found and result.matched_app_ids:
            return list(result.matched_app_ids)
    except Exception:
        # フォールバックへ
        pass

    # 2) フォールバック: app-catalog.md から全 APP-ID
    text = _read_text(repo_root, "docs/catalog/app-catalog.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_APP_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_APP_ID_PATTERN)
    return ids


def parse_agent_catalog(repo_root: Path) -> List[str]:
    """AAG Step 2 以降の成果物から canonical ``AGT-*`` ID を抽出する。

    Step 2 は Agent ID を新規採番する producer なので fan-out しない。Step 3 と
    AAGD は Step 2 の ``agent-architecture.md`` を最優先で読む。再利用実行では
    ``ai-agent-catalog.md``、旧成果物との互換時だけ application definition へ
    fallback する。ファイルが存在しても ID が 0 件なら次候補を試す。
    """
    for rel_path in (
        "docs/agent/agent-architecture.md",
        "docs/ai-agent-catalog.md",
        "docs/agent/agent-application-definition.md",
    ):
        text = _read_text(repo_root, rel_path)
        if text is None:
            continue
        ids: List[str] = []
        # Agent Inventory / AI Agent一覧は連番列を持つ場合があるため、
        # canonical ID は第1列または第2列に限定して探索する。
        for column_index in (0, 1):
            for agent_id in _extract_ids_from_table(
                text,
                id_pattern=_AGENT_ID_PATTERN,
                column_index=column_index,
            ):
                if agent_id not in ids:
                    ids.append(agent_id)
        if not ids:
            ids = _extract_ids_from_headings(text, id_pattern=_AGENT_ID_PATTERN)
        if ids:
            return ids
    return []


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

    Sub-9 (D-2 / ADR-0003): ARD Step 4.2 fan-out 用。
    Step 4.1（ユースケース骨格抽出）の出力ファイルを parse する。
    既存 ``docs/catalog/use-case-catalog.md``（完成版）は対象外。
    """
    text = _read_text(repo_root, "docs/catalog/use-case-skeleton.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_UC_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_UC_ID_PATTERN)
    return ids


def parse_design_doc_inventory(repo_root: Path) -> List[str]:
    """docs/catalog/design-doc-inventory.md から ``DOC-NNNN`` 形式の ID を抽出する。

    ADI Step 2 / Step 5 の fan-out 用。Step 1（原本インベントリ）の出力を parse する。
    ファイル不在時は空リストを返し、呼び出し側で K-1 (fanout-empty) skip にフォールバック可能。
    """
    text = _read_text(repo_root, "docs/catalog/design-doc-inventory.md")
    if text is None:
        return []
    ids = _extract_ids_from_table(text, id_pattern=_DOC_ID_PATTERN)
    if not ids:
        ids = _extract_ids_from_headings(text, id_pattern=_DOC_ID_PATTERN)
    return ids


# ---------------------------------------------------------------------------
# レジストリ
# ---------------------------------------------------------------------------

_PARSERS: Dict[str, Callable[[Path], List[str]]] = {
    "app_catalog": parse_app_catalog,
    "screen_catalog": parse_screen_catalog,
    "service_catalog": parse_service_catalog,
    "dataflow_catalog": parse_dataflow_catalog,
    "agent_catalog": parse_agent_catalog,
    # Sub-9 (D-2 / ADR-0003): ARD fan-out 用
    "business_candidate": parse_business_candidate,
    "use_case_skeleton": parse_use_case_skeleton,
    # ADI fan-out 用
    "design_doc_inventory": parse_design_doc_inventory,
}

# Parser 名 → 主入力ファイルパス（リポジトリルートからの相対パス）の SSOT。
# orchestrator の deferred fan-out 判定（同一実行内の upstream step が入力を
# 生成するか）で参照する。各 parser の _read_text 呼び出し先と一致させること。
#
# - 単一ファイル parser: そのパス
# - glob 系 parser (screen_catalog): 代表 glob 文字列。判定側で fnmatch 比較する
# - 複数フォールバック parser (agent_catalog): primary パスのみ列挙
#   （fallback は registry 上で output_paths として宣言される運用前提）
_PARSER_INPUT_PATHS: Dict[str, str] = {
    "app_catalog": "docs/catalog/app-catalog.md",
    "screen_catalog": "docs/catalog/screen-catalog-APP-*.md",
    "service_catalog": "docs/catalog/service-catalog.md",
    "dataflow_catalog": "docs/catalog/app-catalog.md",
    "agent_catalog": "docs/agent/agent-architecture.md",
    "business_candidate": "docs/company-business-recommendation.md",
    "use_case_skeleton": "docs/catalog/use-case-skeleton.md",
    "design_doc_inventory": "docs/catalog/design-doc-inventory.md",
}

KNOWN_PARSERS: FrozenSet[str] = frozenset(_PARSERS.keys())


def get_parser_input_path(parser_name: str) -> Optional[str]:
    """Parser 名から主入力ファイルパス（リポジトリ相対）を返す。

    未登録 parser には None を返す。
    deferred fan-out 判定（orchestrator._expand_workflow_for_dag）が、
    fan-out base の上流 step の output_paths にこの戻り値が含まれるかを
    照合するために使用する。
    """
    return _PARSER_INPUT_PATHS.get(parser_name)


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
