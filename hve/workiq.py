"""workiq.py — Work IQ (Microsoft 365) 連携モジュール

Microsoft Work IQ MCP サーバーを介して M365 データ（メール・チャット・会議・ファイル）を
読み取り専用で参照し、QA / KM / Original Docs レビューの補助情報として利用する。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .console import Console

_workiq_available_cache: Optional[bool] = None
_workiq_cache_lock = threading.Lock()
_SHELL_ON_WINDOWS = (os.name == "nt")
_WORKIQ_QUERY_INTERVAL_SECONDS: float = 2.0

# Work IQ MCP 関連定数（runner.py / workiq.py の両方から参照する）
WORKIQ_MCP_SERVER_NAME: str = "_hve_workiq"
WORKIQ_MCP_TOOL_NAMES: tuple[str, ...] = (
    "ask_work_iq",
)


def _sanitize_diagnostic_text(text: str) -> str:
    """診断用テキストに含まれる代表的な機微情報を最低限マスクする。

    stderr・例外メッセージ等の診断出力から認証トークン・パスワード・JWT 等を
    最低限マスクする。完全なサニタイズは保証しないため、診断以外の用途で使用しないこと。
    """
    if not text:
        return ""
    sanitized = text
    # Authorization: Bearer xxx / Basic xxx 等
    sanitized = re.sub(
        r"(?i)\b(authorization\s*:\s*)(bearer|basic)\s+([A-Za-z0-9._~+/=-]+)",
        r"\1\2 [REDACTED]",
        sanitized,
    )
    # token=..., api_key=..., password=..., secret=... 等の key=value 形式
    sanitized = re.sub(
        r"(?i)\b(token|access_token|refresh_token|id_token|api[_-]?key|apikey|password|passwd|pwd|secret|client[_-]?secret)\b(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        sanitized,
    )
    # JWT 形式 (eyJ...)
    sanitized = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b",
        "[REDACTED]",
        sanitized,
    )
    return sanitized


def _truncate_diagnostic_text(text: str, max_len: int = 200) -> str:
    """診断テキストを最低限サニタイズしたうえで安全に短縮する。

    npx / node のプロセス出力（stderr / stdout）や例外メッセージを
    診断情報として表示するためのヘルパー。代表的な認証トークンや
    シークレット値を最低限マスクしてから短縮する。
    """
    if not text:
        return ""
    text = _sanitize_diagnostic_text(text.strip())
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def resolve_npx_command() -> Optional[str]:
    """Work IQ 起動用の npx コマンドパスを解決する。

    優先順位:
    1. ``WORKIQ_NPX_COMMAND`` 環境変数
    2. Windows: ``npx.cmd`` → ``npx.exe`` → ``npx`` の順で shutil.which()
    3. 非 Windows: ``shutil.which("npx")``

    Windows PowerShell では ``npx`` が ``npx.ps1`` に解決され、
    Execution Policy によりブロックされる場合がある。
    ``npx.cmd`` を優先することでこの問題を回避できる。

    Returns:
        解決済みコマンドパス、または None（未検出時）
    """
    override = os.environ.get("WORKIQ_NPX_COMMAND")
    if override:
        return override
    if _SHELL_ON_WINDOWS:
        return shutil.which("npx.cmd") or shutil.which("npx.exe") or shutil.which("npx")
    return shutil.which("npx")

_WORKIQ_PROMPT_HEADER: str = (
    f"Microsoft 365 のデータ検索には MCP サーバー `{WORKIQ_MCP_SERVER_NAME}` が提供する以下のツールを使用してください。\n"
    f"利用可能なツール: {', '.join(WORKIQ_MCP_TOOL_NAMES)}\n"
    "※ `workiq` という単独のツール名は存在しません。必ず上記のいずれかのツールを呼び出してください。\n"
    "ツールを呼び出さずに「workiq ツールが存在しない」と結論しないでください。\n"
)

# F1: 役割プライミング + F7: 検索戦略指示
_WORKIQ_ROLE_PROMPT: str = (
    "\nあなたは Microsoft 365 のリサーチアシスタントです。\n"
    "- 一次情報の引用と要約のみを行い、推測・解釈・追加助言はしないでください。\n"
    "- 個人情報（氏名・メール本文・添付内容など）は最低限の引用に留め、要約してください。\n"
    "- 検索キーワードは原文・同義語・略称・英訳の少なくとも 2 通りで試行してください。\n"
    "- 1 回の `ask_work_iq` で十分な結果が得られない場合、観点を変えて再度呼び出してください（最大 3 回）。\n"
)

# F2+F3+F4: 出力スキーマ＋ステータスラベル＋件数/長さ上限
_WORKIQ_OUTPUT_SCHEMA_PROMPT: str = (
    "\n## 出力フォーマット（厳守）\n"
    "1 行目に以下のいずれかの STATUS ラベルを必ず付けてください:\n"
    "- `STATUS: FOUND` — 関連情報が見つかった\n"
    "- `STATUS: NOT_FOUND` — 検索したが関連情報なし\n"
    "- `STATUS: UNAVAILABLE` — ツール未公開・認証失敗・タイムアウト等で検索自体が実行できなかった\n"
    "- `STATUS: PARTIAL` — 一部のソース（例: メールのみ）でしか検索できなかった\n"
    "\n2 行目以降は以下の Markdown 表で報告してください（**最大 5 件、各セルは 200 字以内**）:\n"
    "\n| 種別 | 情報ソース | 日時 | パス/場所 | 関連観点 |\n"
    "|---|---|---:|---|---|\n"
    "| メール / Teams / 会議 / ファイル / Loop | 件名・送信者・会議名・ファイル名等 | YYYY-MM-DD HH:MM | URL/パス | 1 行で要点 |\n"
    "\n表の下に `**補足**:` を 1 ブロックだけ追加してよい（任意・最大 5 行）。\n"
    "`STATUS: NOT_FOUND` / `STATUS: UNAVAILABLE` の場合は表を省略し、理由を 1〜3 行で記載してください。\n"
)

# F5: Few-shot 例（FOUND と UNAVAILABLE）
_WORKIQ_FEWSHOT_PROMPT: str = (
    "\n## 例\n"
    "### 例1（見つかった場合）\n"
    "STATUS: FOUND\n"
    "| 種別 | 情報ソース | 日時 | パス/場所 | 関連観点 |\n"
    "|---|---|---:|---|---|\n"
    "| メール | 件名: 連携設計レビュー / 送信者: yamada@example.com | 2026-04-20 10:15 | Outlook | API契約合意状況 |\n"
    "| ファイル | API仕様書_v1.2.docx | 2026-04-22 | SharePoint/Docs | エンドポイント一覧 |\n"
    "**補足**: 2件とも署名前ドラフトのため確定情報ではない。\n"
    "\n### 例2（ツール未接続の場合）\n"
    "STATUS: UNAVAILABLE\n"
    "ask_work_iq ツールが現在のセッションに公開されていないため、Microsoft 365 を検索できませんでした。\n"
)

DEFAULT_WORKIQ_QA_PROMPT: str = (
    _WORKIQ_PROMPT_HEADER
    + _WORKIQ_ROLE_PROMPT
    + "\nまず `ask_work_iq` ツールを呼び出し、"
    "メール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下の質問に関連する情報がないか調査してください。\n"
    + _WORKIQ_OUTPUT_SCHEMA_PROMPT
    + _WORKIQ_FEWSHOT_PROMPT
    + "\n質問一覧:\n{target_content}"
)

DEFAULT_WORKIQ_KM_PROMPT: str = (
    _WORKIQ_PROMPT_HEADER
    + _WORKIQ_ROLE_PROMPT
    + "\nまず `ask_work_iq` ツールを呼び出し、"
    "メール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下の Knowledge 項目に関連する情報がないか調査してください。\n"
    + _WORKIQ_OUTPUT_SCHEMA_PROMPT
    + _WORKIQ_FEWSHOT_PROMPT
    + "\nKnowledge 項目:\n{target_content}"
)

DEFAULT_WORKIQ_REVIEW_PROMPT: str = (
    _WORKIQ_PROMPT_HEADER
    + _WORKIQ_ROLE_PROMPT
    + "\nまず `ask_work_iq` ツールを呼び出し、"
    "メール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下のドキュメント内容と矛盾する情報や、補足すべき最新情報がないか調査してください。\n"
    + _WORKIQ_OUTPUT_SCHEMA_PROMPT
    + _WORKIQ_FEWSHOT_PROMPT
    + "\nドキュメント概要:\n{target_content}"
)


@dataclass(frozen=True)
class WorkIQQueryTarget:
    """互換ヘルパー用の Work IQ 問い合わせ対象。"""

    d_class_id: str
    document_name: str
    requiredness: str
    current_status: str
    focus_points: tuple[str, ...] = ()
    known_gaps: tuple[str, ...] = ()


@dataclass
class WorkIQDiagnosticCheck:
    """Work IQ 診断の個別チェック結果。"""

    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str = ""
    command: Optional[str] = None


@dataclass
class WorkIQDiagnosticReport:
    """Work IQ 診断レポート（全チェック結果の集約）。"""

    checks: list[WorkIQDiagnosticCheck]


@dataclass(frozen=True)
class WorkIQToolEventMetadata:
    """SDK tool.execution_start イベントから抽出した安全なツールメタデータ。"""

    event_type: str
    tool_name: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    mcp_server_name: Optional[str] = None


@dataclass
class WorkIQQueryResult:
    """Work IQ クエリ結果（詳細情報付き）。"""

    content: str
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


@dataclass
class WorkIQPrefetchResult:
    """Work IQ 詳細取得の結果。

    safe_to_inject:
        True の場合のみ、content をプロンプトへ注入してよい。
        tool_called=True かつ content 非空の場合のみ True になる。
        tool_called=False の場合は content があっても False（LLM がツールを
        呼ばずに応答した可能性があるため、M365 信頼データとして扱わない）。
    result_source:
        結果の出典を示す文字列。"tool_execution"（MCP ツール呼び出し確認済み）、
        "llm_text"（LLM テキストのみ、ツール未確認）、None（エラー/未取得）。
    event_subscription_succeeded:
        セッションへのイベントリスナー登録が成功したかどうか。
        False の場合、tool_called は常に False になる可能性がある。
    """

    content: str = ""
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    mcp_server_found: bool = False
    mcp_status: Optional[str] = None
    mcp_error: Optional[str] = None
    tool_called: bool = False
    called_tools: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    safe_to_inject: bool = False
    result_source: Optional[str] = None
    event_subscription_succeeded: bool = False


_WORKIQ_STATUS_PRIORITY: dict[str, int] = {
    "Unknown": 0,
    "NotStarted": 1,
    "Tentative": 2,
    "Confirmed": 3,
}

_WORKIQ_REQUIREDNESS_PRIORITY: dict[str, int] = {
    "Core": 0,
    "Conditional": 1,
    "Optional": 2,
}

_WORKIQ_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_AKM_MASTER_LIST_PATH = Path("template") / "business-requirement-document-master-list.md"
_DEFAULT_AKM_STATUS_PATH = Path("knowledge") / "business-requirement-document-status.md"


def build_akm_workiq_query_targets(
    master_list_text: str,
    status_text: str = "",
    *,
    include_confirmed: bool = False,
    max_targets: Optional[int] = None,
) -> list[WorkIQQueryTarget]:
    """互換ヘルパー用の Work IQ 問い合わせ対象一覧を構築する。"""
    definitions = _parse_akm_master_list(master_list_text)
    status_map = _parse_akm_status_overview(status_text)

    targets: list[WorkIQQueryTarget] = []
    for d_class_id, definition in definitions.items():
        current_status, known_gaps = status_map.get(d_class_id, ("Unknown", ()))
        if not include_confirmed and current_status == "Confirmed":
            continue
        targets.append(WorkIQQueryTarget(
            d_class_id=d_class_id,
            document_name=definition["document_name"],
            requiredness=definition["requiredness"],
            current_status=current_status,
            focus_points=definition["focus_points"],
            known_gaps=known_gaps,
        ))

    targets.sort(key=lambda target: (
        _WORKIQ_STATUS_PRIORITY.get(target.current_status, 99),
        _WORKIQ_REQUIREDNESS_PRIORITY.get(target.requiredness, 99),
        target.d_class_id,
    ))
    if max_targets is not None:
        return targets[:max_targets]
    return targets


def build_akm_workiq_query_targets_from_files(
    master_list_path: str | Path | None = None,
    status_path: str | Path | None = None,
    *,
    repo_root: str | Path | None = None,
    include_confirmed: bool = False,
    max_targets: Optional[int] = None,
) -> list[WorkIQQueryTarget]:
    """互換ヘルパー用の Work IQ 対象をファイルから構築する。"""
    resolved_repo_root = Path(repo_root) if repo_root is not None else _WORKIQ_REPO_ROOT
    resolved_master_path = _resolve_workiq_repo_path(
        resolved_repo_root,
        master_list_path or _DEFAULT_AKM_MASTER_LIST_PATH,
    )
    master_list_text = _read_workiq_text_file(resolved_master_path)
    if not master_list_text:
        return []

    resolved_status_path = _resolve_workiq_repo_path(
        resolved_repo_root,
        status_path or _DEFAULT_AKM_STATUS_PATH,
    )
    status_text = _read_workiq_text_file(resolved_status_path)
    return build_akm_workiq_query_targets(
        master_list_text,
        status_text,
        include_confirmed=include_confirmed,
        max_targets=max_targets,
    )


def render_akm_workiq_query_target(target: WorkIQQueryTarget) -> str:
    """Work IQ 問い合わせ対象を target_content 文字列へ整形する。"""
    lines = [
        "[D クラス]",
        f"- ID: {target.d_class_id}",
        f"- 文書名: {target.document_name}",
        f"- 必須度: {target.requiredness}",
        f"- 現在状態: {target.current_status}",
    ]

    if target.focus_points:
        lines.extend([
            "",
            "[調査観点]",
            *[f"- {point}" for point in target.focus_points],
        ])
    if target.known_gaps:
        lines.extend([
            "",
            "[既知の不足]",
            *[f"- {gap}" for gap in target.known_gaps],
        ])

    return "\n".join(lines)


def _parse_akm_master_list(master_list_text: str) -> dict[str, dict[str, Any]]:
    """master list Markdown から D クラス定義を抽出する。"""
    result: dict[str, dict[str, Any]] = {}
    if not master_list_text or not master_list_text.strip():
        return result

    section_matches = list(re.finditer(r"^###\s+(D\d{2})\.\s+(.+?)\s*$", master_list_text, flags=re.MULTILINE))
    for index, match in enumerate(section_matches):
        d_class_id = match.group(1).strip()
        document_name = match.group(2).strip()
        section_start = match.end()
        section_end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(master_list_text)
        section_text = master_list_text[section_start:section_end]

        requiredness = _extract_markdown_field(section_text, "必須度") or "Core"
        minimum_contents = _extract_markdown_field(section_text, "最低内容") or ""
        focus_points = tuple(_split_markdown_list_items(minimum_contents, limit=5))

        result[d_class_id] = {
            "document_name": document_name,
            "requiredness": requiredness,
            "focus_points": focus_points,
        }

    return result


def _parse_akm_status_overview(status_text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """status Markdown の D クラス一覧表から状態と不足項目を抽出する。"""
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    if not status_text or not status_text.strip():
        return result

    for line in status_text.splitlines():
        if not line.startswith("| D"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 8:
            continue
        d_class_id = cells[0]
        current_status = _normalize_workiq_status(cells[3])
        gap_text = cells[-1]
        known_gaps = tuple(_split_markdown_list_items(gap_text, limit=3)) if gap_text and gap_text != "なし" else ()
        result[d_class_id] = (current_status, known_gaps)

    return result


def _extract_markdown_field(section_text: str, field_name: str) -> str:
    match = re.search(rf"\*\*{re.escape(field_name)}:\*\*\s*(.+)", section_text)
    return match.group(1).strip() if match else ""


def _normalize_workiq_status(raw_status: str) -> str:
    match = re.search(r"(Confirmed|Tentative|Unknown|NotStarted)", raw_status)
    return match.group(1) if match else "Unknown"


def _split_markdown_list_items(raw_text: str, *, limit: int) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for piece in re.split(r"[、,。\n]\s*", raw_text):
        candidate = piece.strip(" -*`\t ")
        if not candidate or candidate == "なし" or candidate in seen:
            continue
        seen.add(candidate)
        items.append(candidate)
        if len(items) >= limit:
            break
    return items


def _resolve_workiq_repo_path(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _read_workiq_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def is_workiq_available() -> bool:
    """@microsoft/workiq CLI が利用可能かを検出する。

    ``npx -y @microsoft/workiq version`` の成功（exit code 0）を確認する。

    .. important::
        この関数が True を返しても、以下は保証されない:

        - 認証済みであること（M365 / Entra ID への有効なトークンが存在すること）
        - MCP サーバーとして起動できること（``npx @microsoft/workiq mcp`` が成功すること）
        - SDK セッションに接続できること（Copilot SDK の create_session で connected になること）
        - MCP ツールが公開されること（session.rpc.mcp.list() で tools が列挙されること）
        - MCP ツールが実際に実行されること（tool.execution_start イベントが発火すること）

        CLI の存在確認のみ行うため、MCP 連携の動作確認には
        ``python -m hve workiq-doctor --sdk-probe`` を使用すること。
    """
    global _workiq_available_cache
    if _workiq_available_cache is not None:
        return _workiq_available_cache
    with _workiq_cache_lock:
        if _workiq_available_cache is not None:
            return _workiq_available_cache

        npx_cmd = resolve_npx_command()
        if not npx_cmd:
            _workiq_available_cache = False
            return False

        try:
            result = subprocess.run(
                [npx_cmd, "-y", "@microsoft/workiq", "version"],
                capture_output=True,
                text=True,
                timeout=30,
                shell=_SHELL_ON_WINDOWS,
            )
            _workiq_available_cache = (result.returncode == 0)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError, OSError):
            _workiq_available_cache = False

        return _workiq_available_cache


def workiq_login(console: "Console", timeout: float = 600.0) -> bool:
    """Work IQ の認証を実行する（同期関数）。"""
    if _is_headless_environment():
        console.warning(
            "ヘッドレス環境（SSH / CI 等）を検出しました。"
            "Work IQ のブラウザ認証はスキップします。"
            "事前に `workiq accept-eula && workiq ask -q test` で認証を完了してください。"
        )
        return _has_cached_token()

    npx_cmd = resolve_npx_command()
    if npx_cmd is None:
        console.warning(
            "npx が見つかりません。Node.js をインストールしてください。\n"
            "  Windows の場合は npx.cmd が利用できるか確認してください:\n"
            "    where.exe npx.cmd\n"
            "  または WORKIQ_NPX_COMMAND 環境変数で npx の絶対パスを指定できます:\n"
            "    set WORKIQ_NPX_COMMAND=C:\\path\\to\\npx.cmd  (cmd)\n"
            "    $env:WORKIQ_NPX_COMMAND='C:\\path\\to\\npx.cmd'  (PowerShell)\n"
            "  詳細: python -m hve workiq-doctor"
        )
        return False

    try:
        eula_result = subprocess.run(
            [npx_cmd, "-y", "@microsoft/workiq", "accept-eula"],
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=_SHELL_ON_WINDOWS,
        )
        if eula_result.returncode != 0:
            _stderr_short = _truncate_diagnostic_text(eula_result.stderr)
            console.warning(
                f"Work IQ EULA 承認に失敗しました (exit={eula_result.returncode})。"
                + (f"\n  stderr: {_stderr_short}" if _stderr_short else "")
                + "\n  詳細: python -m hve workiq-doctor"
            )
            return False
        result = subprocess.run(
            [npx_cmd, "-y", "@microsoft/workiq", "ask", "-q", "ping"],
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=_SHELL_ON_WINDOWS,
        )
        if result.returncode != 0:
            _stderr_short = _truncate_diagnostic_text(result.stderr)
            console.warning(
                f"Work IQ 認証に失敗しました (exit={result.returncode})。"
                + (f"\n  stderr: {_stderr_short}" if _stderr_short else "")
                + "\n  詳細: python -m hve workiq-doctor"
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        console.warning(f"Work IQ 認証がタイムアウトしました ({timeout:.0f}秒)。")
        return False
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        console.warning(f"Work IQ 認証に失敗しました: {exc}")
        return False


def _get_event_type(event: object) -> Optional[str]:
    """SDK イベントから event.type を文字列として取り出す。"""
    try:
        if isinstance(event, dict):
            etype_obj = event.get("type")
        else:
            etype_obj = getattr(event, "type", None)
        if etype_obj is None:
            return None
        etype = getattr(etype_obj, "value", etype_obj)
        return str(etype) if etype is not None else None
    except Exception:
        return None


def _get_event_data(event: object) -> object:
    """SDK イベントから data を取り出す。"""
    if isinstance(event, dict):
        return event.get("data")
    return getattr(event, "data", None)


def _get_data_field(data: object, *names: str) -> Optional[str]:
    """イベント data から指定名の最初の非空値を安全に取り出す。"""
    try:
        if data is None:
            return None
        if isinstance(data, dict):
            for name in names:
                value = data.get(name)
                if value is not None and value != "":
                    return str(value)
            return None
        for name in names:
            value = getattr(data, name, None)
            if value is not None and value != "":
                return str(value)
        return None
    except Exception:
        return None


def extract_tool_metadata_from_event(event: object) -> Optional[WorkIQToolEventMetadata]:
    """SDK tool.execution_start イベントから MCP 対応のツールメタデータを抽出する。

    GitHub Copilot SDK の MCP tool イベントでは、従来の ``tool_name`` ではなく
    ``mcp_tool_name`` / ``mcp_server_name`` が設定される場合がある。HVE は両形式を
    同じヘルパーで扱い、MCP server 名が存在する場合は `_hve_workiq` だけを Work IQ
    として扱う。
    """
    try:
        event_type = _get_event_type(event)
        if event_type != "tool.execution_start":
            return None
        data = _get_event_data(event)
        if data is None:
            return None
        legacy_tool_name = _get_data_field(data, "tool_name", "toolName", "name")
        mcp_tool_name = _get_data_field(data, "mcp_tool_name", "mcpToolName")
        mcp_server_name = _get_data_field(data, "mcp_server_name", "mcpServerName")
        tool_name = mcp_tool_name or legacy_tool_name
        if not tool_name and not mcp_server_name:
            return None
        return WorkIQToolEventMetadata(
            event_type=event_type,
            tool_name=tool_name,
            mcp_tool_name=mcp_tool_name,
            mcp_server_name=mcp_server_name,
        )
    except Exception:
        return None


def extract_tool_name_from_event(event: object) -> Optional[str]:
    """SDK イベントオブジェクトからツール名を抽出する共通ヘルパー。

    従来の ``tool_name`` / ``toolName`` / ``name`` に加え、MCP tool イベントの
    ``mcp_tool_name`` / ``mcpToolName`` に対応する。

    Returns:
        ツール名文字列、または抽出できない場合は None。
    """
    metadata = extract_tool_metadata_from_event(event)
    return metadata.tool_name if metadata else None


def is_workiq_tool_name(tool_name: str) -> bool:
    """ツール名が Work IQ MCP ツールであるかを判定する共通ヘルパー。

    ``WORKIQ_MCP_TOOL_NAMES`` に含まれる場合 True を返す。
    """
    return tool_name in WORKIQ_MCP_TOOL_NAMES


def _is_workiq_tool_metadata(metadata: Optional[WorkIQToolEventMetadata]) -> bool:
    """抽出済みメタデータが `_hve_workiq` の Work IQ tool 呼び出しか判定する。"""
    if metadata is None or not metadata.tool_name:
        return False
    if metadata.mcp_server_name and metadata.mcp_server_name != WORKIQ_MCP_SERVER_NAME:
        return False
    return is_workiq_tool_name(metadata.tool_name)


def is_workiq_tool_event(event: object) -> bool:
    """SDK イベントが Work IQ MCP tool 呼び出しか判定する。"""
    return _is_workiq_tool_metadata(extract_tool_metadata_from_event(event))


def extract_workiq_tool_name_from_event(event: object) -> Optional[str]:
    """SDK イベントが Work IQ tool 呼び出しならツール名を返す。"""
    metadata = extract_tool_metadata_from_event(event)
    if metadata is None:
        return None
    if not _is_workiq_tool_metadata(metadata):
        return None
    return metadata.tool_name


def format_sdk_event_trace_line(event: object) -> str:
    """診断用に SDK イベントの安全な概要だけを文字列化する。

    prompt・arguments・result・message 本文などの値は含めない。
    """
    event_type = _get_event_type(event) or "unknown"
    metadata = extract_tool_metadata_from_event(event)
    parts = [f"type={event_type}"]
    if metadata:
        if metadata.tool_name:
            parts.append(f"tool={metadata.tool_name}")
        if metadata.mcp_tool_name:
            parts.append(f"mcp_tool={metadata.mcp_tool_name}")
        if metadata.mcp_server_name:
            parts.append(f"mcp_server={metadata.mcp_server_name}")
    return ", ".join(parts)


def run_workiq_event_extractor_self_test() -> WorkIQDiagnosticCheck:
    """Work IQ event extractor が代表的な SDK/MCP 形式を検出できるか自己診断する。"""
    class _EventType:
        def __init__(self, value: str) -> None:
            self.value = value

    class _Event:
        def __init__(self, event_type: object, data: object) -> None:
            self.type = event_type
            self.data = data

    class _Data:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    cases = [
        (
            "legacy_tool_name",
            _Event(_EventType("tool.execution_start"), _Data(tool_name="ask_work_iq")),
            "ask_work_iq",
            True,
        ),
        (
            "mcp_snake_case",
            _Event(
                _EventType("tool.execution_start"),
                _Data(mcp_tool_name="ask_work_iq", mcp_server_name=WORKIQ_MCP_SERVER_NAME),
            ),
            "ask_work_iq",
            True,
        ),
        (
            "mcp_camel_case_dict",
            {"type": "tool.execution_start", "data": {"mcpToolName": "ask_work_iq", "mcpServerName": WORKIQ_MCP_SERVER_NAME}},
            "ask_work_iq",
            True,
        ),
        (
            "other_mcp_server",
            _Event(
                _EventType("tool.execution_start"),
                _Data(mcp_tool_name="ask_work_iq", mcp_server_name="other_server"),
            ),
            "ask_work_iq",
            False,
        ),
        (
            "non_tool_event",
            _Event(_EventType("assistant.message_delta"), _Data(tool_name="ask_work_iq")),
            None,
            False,
        ),
    ]
    failures: list[str] = []
    for name, event, expected_tool, expected_is_workiq in cases:
        actual_tool = extract_tool_name_from_event(event)
        actual_is_workiq = is_workiq_tool_event(event)
        if actual_tool != expected_tool or actual_is_workiq != expected_is_workiq:
            failures.append(
                f"{name}: tool={actual_tool!r}/{expected_tool!r}, "
                f"is_workiq={actual_is_workiq!r}/{expected_is_workiq!r}"
            )
    if failures:
        return WorkIQDiagnosticCheck(
            name="event_extractor_self_test",
            status="FAIL",
            detail="; ".join(failures),
        )
    return WorkIQDiagnosticCheck(
        name="event_extractor_self_test",
        status="PASS",
        detail="tool_name / mcp_tool_name / mcp_server_name の代表形式を検出できました",
    )


def build_workiq_mcp_config(tenant_id: Optional[str] = None, *, tools_all: bool = False) -> dict:
    """Work IQ MCP サーバー設定 dict を返す。

    Args:
        tenant_id: マルチテナント環境でのテナント ID（省略時は既定テナント）。
        tools_all: True の場合、tools を ``["*"]``（全ツール許可）にする。
            **診断・切り分け用途のみ**。本番では最小権限の固定 allowlist（既定値）を使うこと。

    Returns:
        Copilot SDK の ``mcp_servers`` に渡す dict。
    """
    npx_cmd = resolve_npx_command() or "npx"
    args = ["-y", "@microsoft/workiq", "mcp"]
    if tenant_id:
        args.extend(["-t", tenant_id])

    tools: list = ["*"] if tools_all else list(WORKIQ_MCP_TOOL_NAMES)

    return {
        WORKIQ_MCP_SERVER_NAME: {
            "type": "local",  # Copilot SDK の MCP ローカルサーバー設定に必要
            "command": npx_cmd,
            "args": args,
            "tools": tools,
        }
    }


async def query_workiq_detailed(
    session: Any,
    query: str,
    timeout: float = 900.0,
) -> WorkIQQueryResult:
    """Work IQ 経由で M365 データを問い合わせ、詳細結果を返す。

    session は ``send_and_wait(prompt: str, timeout: float)`` を持つオブジェクトを想定する。
    失敗時は ``content=""`` と ``error=<短縮した例外詳細>`` を返す。
    """
    _start = time.monotonic()
    try:
        response = await session.send_and_wait(query, timeout=timeout)
        _elapsed = time.monotonic() - _start
        if response is None:
            return WorkIQQueryResult(content="", elapsed_seconds=_elapsed)
        data = getattr(response, "data", None)
        if data is not None:
            for attr in ("content", "message"):
                val = getattr(data, attr, None)
                if val is not None:
                    return WorkIQQueryResult(
                        content=sanitize_workiq_result(str(val)),
                        elapsed_seconds=_elapsed,
                    )
        for attr in ("content", "text", "message"):
            val = getattr(response, attr, None)
            if val is not None:
                return WorkIQQueryResult(
                    content=sanitize_workiq_result(str(val)),
                    elapsed_seconds=_elapsed,
                )
        return WorkIQQueryResult(content="", elapsed_seconds=_elapsed)
    except Exception as exc:  # Work IQ 失敗時は本処理を継続（graceful degradation）
        _elapsed = time.monotonic() - _start
        error_detail = _truncate_diagnostic_text(str(exc), max_len=300)
        logging.getLogger(__name__).warning(
            "query_workiq_detailed failed", exc_info=True
        )
        return WorkIQQueryResult(content="", error=error_detail, elapsed_seconds=_elapsed)


async def query_workiq(
    session: Any,
    query: str,
    timeout: float = 900.0,
) -> str:
    """Work IQ 経由で M365 データを問い合わせる。

    session は ``send_and_wait(prompt: str, timeout: float)`` を持つオブジェクトを想定する。
    後方互換性維持のため ``query_workiq_detailed()`` のラッパーとして実装する。
    """
    result = await query_workiq_detailed(session, query, timeout=timeout)
    return result.content


async def query_workiq_per_question(
    session: Any,
    questions: list[tuple[int, str]],
    prompt_template: str,
    timeout: float = 900.0,
    max_questions: int = 30,
) -> dict[int, str]:
    """質問ごとに Work IQ クエリを実行して結果を返す。"""
    if not questions or max_questions <= 0:
        return {}

    limited = questions[:max_questions]
    results: dict[int, str] = {}
    for idx, (question_no, question_text) in enumerate(limited):
        try:
            _target_content = f"Q{question_no}: {question_text}"
            _query = prompt_template.format(target_content=_target_content)
            _result = await query_workiq(session, _query, timeout=timeout)
            if _result and _result.strip():
                results[question_no] = _result.strip()
        except Exception:
            # 個別質問の失敗は他の質問処理へ波及させない
            continue
        finally:
            if idx < len(limited) - 1:
                await asyncio.sleep(_WORKIQ_QUERY_INTERVAL_SECONDS)

    return results


def format_workiq_draft_answers(
    questions: list[dict[str, Any]],
    per_question_results: dict[int, str],
) -> str:
    """Work IQ の質問別結果を回答ドラフト Markdown に整形する。"""
    lines = [
        "# Work IQ 回答ドラフト",
        "",
        "> ⚠️ このファイルは Work IQ の自動生成ドラフトです。必ず人間がレビューしてから採用してください。",
        "",
    ]

    if not questions:
        lines.extend([
            "## 対象質問",
            "- なし",
        ])
        return "\n".join(lines)

    for q in questions:
        no = int(q.get("no", 0) or 0)
        question = str(q.get("question", "")).strip()
        default = str(q.get("default", "")).strip()
        context = per_question_results.get(no, "").strip()

        lines.append(f"## Q{no}: {question or '(質問本文なし)'}")
        if context:
            lines.extend([
                "",
                "### Work IQ 調査結果",
                context,
                "",
                "### 回答ドラフト（候補）",
                f"- 既定値候補: {default or '（既定値候補なし）'}",
                "",
            ])
        else:
            lines.extend([
                "",
                "### Work IQ 調査結果",
                "- 関連情報なし",
                "",
                "### 回答ドラフト（候補）",
                f"- 既定値候補: {default or '（既定値候補なし）'}",
                "",
            ])

    return "\n".join(lines).rstrip() + "\n"


_MAX_WORKIQ_CONTEXT_LENGTH: int = 10_000

_WORKIQ_ERROR_INDICATORS: tuple[str, ...] = (
    "アクセスできない",
    "実行できません",
    "ツールが見つかりません",
    "利用できません",
    "利用できず",
    "接続できません",
    "認証に失敗",
    "未実施",
    "調査不能",
    "調査不可",
    "公開されていない",
    "公開されていません",
    "tool is not available",
    "cannot access",
    "not authenticated",
)

_WORKIQ_DATA_INDICATORS: tuple[str, ...] = (
    "メール件名",
    "送信者",
    "会議名",
    "ファイル名",
    "ask_work_iq",
)

_NEGATIVE_CONTEXT_PATTERNS: tuple[str, ...] = (
    "できない", "できません", "できず", "不可", "不能",
    "場合は", "場合に", "例えば", "のように",
    "いただければ", "ソース（", "ソース:", "（例",
    "未実施", "調査不能", "調査不可",
    "公開されていない", "公開されていません",
    "for example", "e.g.", "such as", "like",
    "if you", "if the", "when you", "in case",
    "please provide", "please specify", "you can use",
    "not available", "cannot", "unable to",
    "not authenticated", "not configured", "not enabled",
)


def is_workiq_error_response(context: str) -> bool:
    """Work IQ 応答がエラーテキスト主体かをヒューリスティックに判定する。

    エラー指標語句を含む場合、データ指標語句が「否定・例示・仮定」の
    文脈で出現しているかを検査し、実データが含まれていない場合に True を返す。
    """
    if not context or not context.strip():
        return False
    # F3: 明示 STATUS ラベルがあれば優先判定（ヒューリスティック前に確定させる）
    # 先頭行の大文字小文字・余分な空白を無視してラベルを抽出する
    head = context.lstrip().splitlines()[0]
    _status_match = re.match(r"^\s*STATUS\s*:\s*(\w+)", head, re.IGNORECASE)
    if _status_match:
        label = _status_match.group(1).upper()
        if label == "UNAVAILABLE":
            return True
        if label in ("FOUND", "PARTIAL", "NOT_FOUND"):
            # NOT_FOUND は「正しく検索した上で関連情報なし」なのでエラー扱いしない
            return False
    # 以降は既存ヒューリスティック（後方互換のため温存）
    has_error = any(p in context for p in _WORKIQ_ERROR_INDICATORS)
    if not has_error:
        return False

    # データ指標語句が実データとして（否定・例示文脈外で）出現しているかを判定
    real_data_count = 0
    for indicator in _WORKIQ_DATA_INDICATORS:
        pos = context.find(indicator)
        while pos >= 0:
            value_segment = context[pos + len(indicator):min(len(context), pos + len(indicator) + 40)]
            # 「メール件名: ...」のような値付きフィールド形式は実データとみなす
            if value_segment.lstrip().startswith((':', '：')):
                real_data_count += 1
                break
            # 指標語句の前後100文字を文脈ウィンドウとして取得
            ctx_start = max(0, pos - 100)
            ctx_end = min(len(context), pos + len(indicator) + 100)
            surrounding = context[ctx_start:ctx_end]
            # 否定・例示文脈内でなければ実データとカウント
            if not any(neg in surrounding for neg in _NEGATIVE_CONTEXT_PATTERNS):
                real_data_count += 1
                break  # この指標語句については1件見つかれば十分
            # 同一指標語句の次の出現位置を検索
            pos = context.find(indicator, pos + len(indicator))

    return real_data_count == 0


def _escape_workiq_sandbox_tags(text: Optional[str]) -> Optional[str]:
    """Work IQ コンテンツ中のサンドボックスタグをエスケープする。

    `<workiq_reference_data>` / `</workiq_reference_data>` を含む応答や
    knowledge/Dxx-*.md の内容が入力された場合、そのままプロンプトに
    埋め込むとサンドボックスタグの整合性が崩れ、後続テキストが
    LLM 指示として有効化される（プロンプトインジェクション）。

    本関数は両方のタグを `workiq_reference_data_escaped` に置換し、
    タグの構造を保ちつつ意味を無効化する。

    大文字小文字を区別しない（HTML タグの慣習に合わせる）。

    Note:
        本関数は `enrich_prompt_with_workiq()` および
        `orchestrator._run_akm_workiq_verification()` から呼び出される。
        新規箇所で Work IQ データや外部ファイル内容を
        `WORKIQ_CONTEXT_INJECTION_PROMPT` /
        `AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT` に埋め込む際も
        必ず本関数を経由すること。
    """
    if not text:
        return text

    def _replace(m: re.Match) -> str:
        tag = m.group(0)
        # タグ名の大文字小文字に合わせてサフィックスを決定
        suffix = "_ESCAPED" if tag.isupper() else "_escaped"
        return re.sub(r"workiq_reference_data", lambda inner_match: inner_match.group(0) + suffix, tag, flags=re.IGNORECASE)

    return re.sub(r"</?workiq_reference_data>", _replace, text, flags=re.IGNORECASE)


def enrich_prompt_with_workiq(
    workiq_context: str,
    original_prompt: str,
    context_type: str = "参考情報",
) -> str:
    """Work IQ 結果をプロンプト先頭に注入する。"""
    if not workiq_context or not workiq_context.strip():
        return original_prompt
    if is_workiq_error_response(workiq_context):
        return original_prompt

    truncated = _truncate_workiq_context(workiq_context, _MAX_WORKIQ_CONTEXT_LENGTH)
    truncated = _escape_workiq_sandbox_tags(truncated)  # プロンプトインジェクション対策

    try:
        from .prompts import WORKIQ_CONTEXT_INJECTION_PROMPT
    except ImportError:
        from prompts import WORKIQ_CONTEXT_INJECTION_PROMPT  # type: ignore[no-redef]

    injection = WORKIQ_CONTEXT_INJECTION_PROMPT.format(
        context_type=context_type,
        workiq_context=truncated,
    )
    return injection + original_prompt


def get_workiq_prompt_template(
    mode: str,
    config_override: Optional[str] = None,
) -> str:
    """モード別の Work IQ プロンプトテンプレートを返す。"""
    if config_override:
        return config_override

    templates = {
        "qa": DEFAULT_WORKIQ_QA_PROMPT,
        "km": DEFAULT_WORKIQ_KM_PROMPT,
        "review": DEFAULT_WORKIQ_REVIEW_PROMPT,
    }
    return templates.get(mode, DEFAULT_WORKIQ_QA_PROMPT)


def save_workiq_result(
    run_id: str,
    step_id: str,
    mode: str,
    result: str,
    *,
    is_error: bool = False,
    base_dir: str = "qa",
) -> Optional[Path]:
    """Work IQ クエリ結果をファイルに永続化する。"""
    if not result or not result.strip():
        return None

    safe_run_id = re.sub(r"[^A-Za-z0-9\-_]", "", run_id) or "unknown"
    safe_step_id = re.sub(r"[^A-Za-z0-9\-_.]", "", step_id) or "unknown"
    safe_mode = re.sub(r"[^A-Za-z0-9\-_.]", "", mode) or "unknown"
    target_dir = Path(str(base_dir).strip() or "qa")

    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-ERROR" if is_error else ""
    out_path = target_dir / f"{safe_run_id}-{safe_step_id}-workiq-{safe_mode}{suffix}.md"

    try:
        truncated_result = _truncate_workiq_context(result, 50_000)
        header = (
            "# Work IQ 調査結果\n\n"
            f"- **run_id**: {safe_run_id}\n"
            f"- **step_id**: {safe_step_id}\n"
            f"- **mode**: {mode}\n"
            f"- **timestamp**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
            + ("⚠️ **STATUS: ERROR**\n\n" if is_error else "")
            + "---\n\n"
        )
        out_path.write_text(header + truncated_result, encoding="utf-8")
        return out_path
    except OSError:
        return None


def sanitize_workiq_result(text: str) -> str:
    """Work IQ 結果から制御文字と ANSI エスケープを除去する。"""
    no_ansi = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", no_ansi)


def _truncate_workiq_context(text: str, max_length: int) -> str:
    """Work IQ コンテキストを先頭 + 末尾で切り詰める。"""
    if len(text) <= max_length:
        return text
    head_size = max_length * 3 // 4
    omit_msg = f"\n\n... (中略: 全体 {len(text):,} 文字) ...\n\n"
    tail_size = max_length - head_size - len(omit_msg)
    if tail_size <= 0:
        return text[:max_length]
    return text[:head_size] + omit_msg + text[-tail_size:]


def _is_headless_environment() -> bool:
    """ヘッドレス環境（ブラウザ認証不可）を検出する。"""
    if os.environ.get("CI"):
        return True
    if os.environ.get("SSH_TTY") or os.environ.get("SSH_CLIENT"):
        return True
    if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def _has_cached_token() -> bool:
    """Work IQ のトークンキャッシュ有無を確認する（best-effort）。"""
    home = Path.home()
    candidates = [
        home / ".workiq",
        home / ".config" / "workiq",
    ]
    return any(p.exists() for p in candidates)


def probe_workiq_mcp_startup(
    npx_cmd: str,
    tenant_id: Optional[str] = None,
    timeout_seconds: float = 5.0,
) -> WorkIQDiagnosticCheck:
    """``npx @microsoft/workiq mcp`` の起動確認を行う（数秒で打ち切る）。

    MCP サーバーは長時間起動型のため ``subprocess.Popen()`` で起動し、
    ``timeout_seconds`` 秒待つ。timeout まで生存していれば PASS、
    即時終了かつ returncode != 0 なら FAIL とする。
    プロセスは最後に必ず terminate / kill する。
    """
    args = [npx_cmd, "-y", "@microsoft/workiq", "mcp"]
    if tenant_id:
        args.extend(["-t", tenant_id])
    if _SHELL_ON_WINDOWS:
        import subprocess as _sp
        cmd_str = _sp.list2cmdline(args)
    else:
        import shlex
        cmd_str = shlex.join(args)

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=_SHELL_ON_WINDOWS,
        )
        try:
            proc.wait(timeout=timeout_seconds)
            # timeout 前にプロセスが終了した
            # MCP サーバーは長時間起動プロセスのため、即時終了は exit code に関わらず WARN/FAIL
            stderr_raw = b""
            if proc.stderr:
                try:
                    stderr_raw = proc.stderr.read(4096)
                except OSError:
                    pass
            stderr_short = _truncate_diagnostic_text(
                stderr_raw.decode("utf-8", errors="replace")
            )
            if proc.returncode != 0:
                return WorkIQDiagnosticCheck(
                    name="mcp_startup",
                    status="FAIL",
                    detail=(
                        f"MCP プロセスが即座に終了しました (exit={proc.returncode})"
                        + (f"\n  stderr: {stderr_short}" if stderr_short else "")
                    ),
                    command=cmd_str,
                )
            # exit=0 でも即時終了はサーバーとして異常（WARN）
            return WorkIQDiagnosticCheck(
                name="mcp_startup",
                status="WARN",
                detail=(
                    "MCP プロセスが即座に終了しました (exit=0)。"
                    "MCP サーバーは長時間起動プロセスのため、即時終了は正常ではありません。"
                    + (f"\n  stderr: {stderr_short}" if stderr_short else "")
                ),
                command=cmd_str,
            )
        except subprocess.TimeoutExpired:
            # timeout まで生存 → 起動成功とみなす
            return WorkIQDiagnosticCheck(
                name="mcp_startup",
                status="PASS",
                detail=f"MCP プロセスが {timeout_seconds:.0f}秒間起動し続けました",
                command=cmd_str,
            )
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    try:
                        proc.wait(timeout=1.0)
                    except (subprocess.TimeoutExpired, OSError):
                        pass
                except OSError:
                    pass
            try:
                proc.communicate(timeout=0.1)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass
    except (FileNotFoundError, OSError) as exc:
        return WorkIQDiagnosticCheck(
            name="mcp_startup",
            status="FAIL",
            detail=f"MCP プロセスの起動に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command=cmd_str,
        )


async def probe_workiq_copilot_session(
    *,
    tenant_id: Optional[str] = None,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
    github_token: Optional[str] = None,
    timeout: float = 30.0,
) -> list[WorkIQDiagnosticCheck]:
    """Copilot SDK セッション内で `_hve_workiq` が connected かを検証する（--sdk-probe 用）。

    以下のチェックを順番に実施する:
    1. copilot_sdk_import: Copilot SDK を import できるか
    2. copilot_client_start: CopilotClient.start() が成功するか
    3. copilot_mcp_session: create_session(mcp_servers=...) が成功するか
    4. copilot_mcp_list: session.rpc.mcp.list() が成功するか
    5. copilot_mcp_status: _hve_workiq が connected か
    6. copilot_mcp_tool_count: (best-effort) srv.tools が取得できる場合にツール公開数を確認する。
       0 件の場合は M365 未認証の可能性として WARN を追加する。
    """
    checks: list[WorkIQDiagnosticCheck] = []

    # 1. SDK import
    try:
        import importlib
        copilot_mod = importlib.import_module("copilot")
        copilot_session_mod = importlib.import_module("copilot.session")
        CopilotClient = copilot_mod.CopilotClient
        SubprocessConfig = copilot_mod.SubprocessConfig
        ExternalServerConfig = copilot_mod.ExternalServerConfig
        PermissionHandler = copilot_session_mod.PermissionHandler
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_sdk_import",
            status="PASS",
            detail="Copilot SDK を import しました",
        ))
    except ImportError as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_sdk_import",
            status="FAIL",
            detail=f"Copilot SDK の import に失敗しました: {exc}",
        ))
        return checks

    # 2. CopilotClient.start()
    try:
        if cli_url:
            sdk_cfg = ExternalServerConfig(url=cli_url)
        else:
            sdk_cfg = SubprocessConfig(
                cli_path=cli_path,
                github_token=github_token or None,
                log_level="error",
            )
        client = CopilotClient(config=sdk_cfg)
        await asyncio.wait_for(client.start(), timeout=timeout)
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_client_start",
            status="PASS",
            detail="CopilotClient.start() 成功",
        ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_client_start",
            status="FAIL",
            detail=f"CopilotClient.start() に失敗しました: {_truncate_diagnostic_text(str(exc))}",
        ))
        return checks

    session = None
    try:
        # 3. create_session
        try:
            _mcp = build_workiq_mcp_config(tenant_id=tenant_id)
            session = await asyncio.wait_for(
                client.create_session(
                    on_permission_request=PermissionHandler.approve_all,
                    streaming=True,
                    mcp_servers=_mcp,
                ),
                timeout=timeout,
            )
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_mcp_session",
                status="PASS",
                detail="create_session(mcp_servers=...) 成功",
            ))
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_mcp_session",
                status="FAIL",
                detail=f"create_session に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))
            return checks

        # 4. mcp.list()
        try:
            mcp_list = await asyncio.wait_for(session.rpc.mcp.list(), timeout=timeout)
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_mcp_list",
                status="PASS",
                detail=f"session.rpc.mcp.list() 成功 (サーバー数: {len(mcp_list.servers)})",
            ))
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_mcp_list",
                status="FAIL",
                detail=f"session.rpc.mcp.list() に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))
            return checks

        # 5. _hve_workiq status
        wiq_found = False
        for srv in mcp_list.servers:
            if srv.name == WORKIQ_MCP_SERVER_NAME:
                wiq_found = True
                srv_status = srv.status.value if hasattr(srv.status, "value") else str(srv.status)
                srv_error = getattr(srv, "error", None)
                if srv_status == "connected":
                    checks.append(WorkIQDiagnosticCheck(
                        name="copilot_mcp_status",
                        status="PASS",
                        detail=f"{WORKIQ_MCP_SERVER_NAME} は Copilot SDK セッション内で connected です",
                    ))
                    # ツール公開数を確認（best-effort: SDK がツール情報を返す場合のみ）
                    srv_tools = getattr(srv, "tools", None)
                    if srv_tools is not None:
                        tool_count = len(srv_tools)
                        if tool_count == 0:
                            checks.append(WorkIQDiagnosticCheck(
                                name="copilot_mcp_tool_count",
                                status="WARN",
                                detail=(
                                    f"{WORKIQ_MCP_SERVER_NAME} のツール公開数が 0 です。\n"
                                    "M365 認証が完了していない可能性があります。\n"
                                    "  対処: npx -y @microsoft/workiq login を実行してください。"
                                ),
                            ))
                        else:
                            checks.append(WorkIQDiagnosticCheck(
                                name="copilot_mcp_tool_count",
                                status="PASS",
                                detail=f"{WORKIQ_MCP_SERVER_NAME} は {tool_count} 個のツールを公開しています",
                            ))
                else:
                    checks.append(WorkIQDiagnosticCheck(
                        name="copilot_mcp_status",
                        status="FAIL",
                        detail=(
                            f"{WORKIQ_MCP_SERVER_NAME} status={srv_status}"
                            + (f", error={_truncate_diagnostic_text(str(srv_error))}" if srv_error else "")
                        ),
                    ))
                break
        if not wiq_found:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_mcp_status",
                status="FAIL",
                detail=f"Copilot SDK セッションの MCP 一覧に {WORKIQ_MCP_SERVER_NAME} が存在しません",
            ))

    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception:
                pass
        try:
            await client.stop()
        except Exception:
            pass

    return checks


async def probe_workiq_copilot_tool_invocation(
    *,
    tenant_id: Optional[str] = None,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
    github_token: Optional[str] = None,
    timeout: float = 60.0,
    trace_events: bool = False,
    tools_all: bool = False,
) -> list[WorkIQDiagnosticCheck]:
    """Copilot SDK セッションで Work IQ MCP tool が実際に呼び出されるか検証する。

    既存の ``--sdk-probe`` は MCP server の connected 状態のみを確認する。
    この probe は短い診断プロンプトを送信し、SDK の ``tool.execution_start`` イベント上で
    `_hve_workiq` の tool 呼び出しを観測できるかを確認する。
    """
    checks: list[WorkIQDiagnosticCheck] = []
    trace_lines: list[str] = []
    called_tools: list[str] = []

    try:
        import importlib
        copilot_mod = importlib.import_module("copilot")
        copilot_session_mod = importlib.import_module("copilot.session")
        CopilotClient = copilot_mod.CopilotClient
        SubprocessConfig = copilot_mod.SubprocessConfig
        ExternalServerConfig = copilot_mod.ExternalServerConfig
        PermissionHandler = copilot_session_mod.PermissionHandler
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_tool_probe_import",
            status="PASS",
            detail="Copilot SDK を import しました",
        ))
    except ImportError as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_tool_probe_import",
            status="FAIL",
            detail=f"Copilot SDK の import に失敗しました: {exc}",
        ))
        return checks

    try:
        if cli_url:
            sdk_cfg = ExternalServerConfig(url=cli_url)
        else:
            sdk_cfg = SubprocessConfig(
                cli_path=cli_path,
                github_token=github_token or None,
                log_level="error",
            )
        client = CopilotClient(config=sdk_cfg)
        await asyncio.wait_for(client.start(), timeout=timeout)
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_tool_probe_client_start",
            status="PASS",
            detail="CopilotClient.start() 成功",
        ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_tool_probe_client_start",
            status="FAIL",
            detail=f"CopilotClient.start() に失敗しました: {_truncate_diagnostic_text(str(exc))}",
        ))
        return checks

    session = None
    try:
        try:
            _mcp = build_workiq_mcp_config(tenant_id=tenant_id, tools_all=tools_all)
            session = await asyncio.wait_for(
                client.create_session(
                    on_permission_request=PermissionHandler.approve_all,
                    streaming=True,
                    mcp_servers=_mcp,
                ),
                timeout=timeout,
            )
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_session",
                status="PASS",
                detail=(
                    "create_session(mcp_servers=...) 成功"
                    + (" (tools=['*'])" if tools_all else "")
                ),
            ))
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_session",
                status="FAIL",
                detail=f"create_session に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))
            return checks

        try:
            mcp_list = await asyncio.wait_for(session.rpc.mcp.list(), timeout=timeout)
            wiq_found = False
            for srv in mcp_list.servers:
                if srv.name != WORKIQ_MCP_SERVER_NAME:
                    continue
                wiq_found = True
                srv_status = srv.status.value if hasattr(srv.status, "value") else str(srv.status)
                srv_error = getattr(srv, "error", None)
                if srv_status == "connected":
                    checks.append(WorkIQDiagnosticCheck(
                        name="copilot_tool_probe_mcp_status",
                        status="PASS",
                        detail=f"{WORKIQ_MCP_SERVER_NAME} は connected です",
                    ))
                    # ツール公開数を確認（best-effort: SDK がツール情報を返す場合のみ）
                    srv_tools = getattr(srv, "tools", None)
                    if srv_tools is not None:
                        tool_count = len(srv_tools)
                        if tool_count == 0:
                            checks.append(WorkIQDiagnosticCheck(
                                name="copilot_tool_probe_tool_count",
                                status="WARN",
                                detail=(
                                    f"{WORKIQ_MCP_SERVER_NAME} のツール公開数が 0 です。\n"
                                    "M365 認証が完了していない可能性があります。\n"
                                    "  対処: npx -y @microsoft/workiq login を実行してください。"
                                ),
                            ))
                        else:
                            checks.append(WorkIQDiagnosticCheck(
                                name="copilot_tool_probe_tool_count",
                                status="PASS",
                                detail=f"{WORKIQ_MCP_SERVER_NAME} は {tool_count} 個のツールを公開しています",
                            ))
                else:
                    checks.append(WorkIQDiagnosticCheck(
                        name="copilot_tool_probe_mcp_status",
                        status="FAIL",
                        detail=(
                            f"{WORKIQ_MCP_SERVER_NAME} status={srv_status}"
                            + (f", error={_truncate_diagnostic_text(str(srv_error))}" if srv_error else "")
                        ),
                    ))
                    return checks
                break
            if not wiq_found:
                checks.append(WorkIQDiagnosticCheck(
                    name="copilot_tool_probe_mcp_status",
                    status="FAIL",
                    detail=f"Copilot SDK セッションの MCP 一覧に {WORKIQ_MCP_SERVER_NAME} が存在しません",
                ))
                return checks
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_mcp_status",
                status="FAIL",
                detail=f"session.rpc.mcp.list() に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))
            return checks

        def _on_event(event: object) -> None:
            if trace_events and len(trace_lines) < 30:
                trace_lines.append(format_sdk_event_trace_line(event))
            tool_name = extract_workiq_tool_name_from_event(event)
            if tool_name:
                called_tools.append(tool_name)

        try:
            session.on(_on_event)
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_event_subscription",
                status="PASS",
                detail="session.on(...) によるイベント購読に成功しました",
            ))
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_event_subscription",
                status="WARN",
                detail=f"イベント購読に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))

        probe_prompt = (
            "診断専用です。`ask_work_iq` ツールを1回だけ呼び出してください。"
            "引数 `question` は `ping` としてください。ツール結果の要約のみ短く返してください。"
            "ツールが利用できない場合はその理由を一文で返してください。"
        )
        try:
            await asyncio.wait_for(
                session.send_and_wait(probe_prompt, timeout=timeout),
                timeout=timeout + 5.0,
            )
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_send",
                status="PASS",
                detail="診断プロンプトの send_and_wait が完了しました",
            ))
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe_send",
                status="FAIL",
                detail=f"診断プロンプト送信に失敗しました: {_truncate_diagnostic_text(str(exc), max_len=300)}",
            ))

        if called_tools:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_invocation",
                status="PASS",
                detail=f"SDK イベント上で Work IQ tool 呼び出しを確認: {', '.join(called_tools)}",
            ))
        else:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_invocation",
                status="FAIL",
                detail=(
                    "SDK イベント上で Work IQ MCP tool 呼び出しを確認できませんでした。\n"
                    "  考えられる原因:\n"
                    "  1. Work IQ ツールが LLM のツール一覧に公開されていない（M365 未認証の可能性）\n"
                    "  2. LLM が tool を呼ばなかった（プロンプト不足）\n"
                    "  3. SDK イベント形式が想定と異なる\n"
                    "  対処: `npx -y @microsoft/workiq login` でログイン後に再試行、"
                    "または `--sdk-tool-probe-tools-all` で再試行してください。"
                ),
            ))

        if trace_events:
            trace_detail = "\n".join(trace_lines) if trace_lines else "イベントは観測されませんでした"
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_sdk_event_trace",
                status="PASS" if trace_lines else "WARN",
                detail=trace_detail,
            ))
    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception:
                pass
        try:
            await client.stop()
        except Exception:
            pass

    return checks


def run_workiq_diagnostics(
    *,
    tenant_id: Optional[str] = None,
    skip_mcp_probe: bool = False,
    mcp_probe_timeout: float = 5.0,
    sdk_probe: bool = False,
    sdk_probe_timeout: float = 30.0,
    event_extractor_self_test: bool = False,
    sdk_tool_probe: bool = False,
    sdk_tool_probe_timeout: float = 60.0,
    sdk_event_trace: bool = False,
    sdk_tool_probe_tools_all: bool = False,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
    github_token: Optional[str] = None,
) -> WorkIQDiagnosticReport:
    """Work IQ 連携に関する診断チェックを実行し、レポートを返す。

    診断は失敗しても途中で例外終了せず、結果を check として返す。
    トークン・認証情報などの機微情報を出力しない。
    sdk_probe=True の場合は Copilot SDK セッション検証も実施する。
    """
    import platform
    import sys as _sys

    checks: list = []

    # 1. OS / Python 情報
    checks.append(WorkIQDiagnosticCheck(
        name="os_info",
        status="PASS",
        detail=f"OS: {platform.system()} {platform.release()}, Python: {_sys.version.split()[0]}",
    ))

    if event_extractor_self_test:
        checks.append(run_workiq_event_extractor_self_test())

    # 2. WORKIQ_NPX_COMMAND 環境変数
    env_override = os.environ.get("WORKIQ_NPX_COMMAND")
    if env_override:
        checks.append(WorkIQDiagnosticCheck(
            name="env_workiq_npx_command",
            status="PASS",
            detail=f"WORKIQ_NPX_COMMAND 設定済み: {env_override}",
        ))
    else:
        checks.append(WorkIQDiagnosticCheck(
            name="env_workiq_npx_command",
            status="SKIP",
            detail="WORKIQ_NPX_COMMAND 未設定（通常設定は不要。npx が見つからない場合に使用）",
        ))

    # 3. resolve_npx_command()
    npx_cmd = resolve_npx_command()
    if npx_cmd:
        checks.append(WorkIQDiagnosticCheck(
            name="resolve_npx",
            status="PASS",
            detail=f"npx 解決済み: {npx_cmd}",
            command=npx_cmd,
        ))
    else:
        checks.append(WorkIQDiagnosticCheck(
            name="resolve_npx",
            status="FAIL",
            detail=(
                "npx が見つかりません。Node.js をインストールしてください。\n"
                "  Windows の場合は 'where.exe npx.cmd' で確認し、\n"
                "  WORKIQ_NPX_COMMAND=C:\\path\\to\\npx.cmd で指定できます。"
            ),
        ))
        for name in ("node_version", "npm_version", "workiq_version", "workiq_eula", "workiq_ping", "mcp_startup"):
            checks.append(WorkIQDiagnosticCheck(name=name, status="SKIP", detail="npx 未解決のためスキップ"))
        if sdk_probe:
            checks.append(WorkIQDiagnosticCheck(name="copilot_sdk_probe", status="SKIP", detail="npx 未解決のためスキップ"))
        if sdk_tool_probe:
            checks.append(WorkIQDiagnosticCheck(name="copilot_tool_invocation", status="SKIP", detail="npx 未解決のためスキップ"))
        if sdk_event_trace:
            checks.append(WorkIQDiagnosticCheck(name="copilot_sdk_event_trace", status="SKIP", detail="npx 未解決のためスキップ"))
        return WorkIQDiagnosticReport(checks=checks)

    # 4. node -v
    try:
        node_result = subprocess.run(
            ["node", "-v"],
            capture_output=True, text=True, timeout=10,
            shell=_SHELL_ON_WINDOWS,
        )
        if node_result.returncode == 0:
            checks.append(WorkIQDiagnosticCheck(
                name="node_version",
                status="PASS",
                detail=f"node: {node_result.stdout.strip()}",
                command="node -v",
            ))
        else:
            checks.append(WorkIQDiagnosticCheck(
                name="node_version",
                status="WARN",
                detail=f"node -v が失敗しました (exit={node_result.returncode})",
                command="node -v",
            ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="node_version",
            status="WARN",
            detail=f"node -v の実行に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command="node -v",
        ))

    # 5. npm -v
    try:
        npm_result = subprocess.run(
            ["npm", "-v"],
            capture_output=True, text=True, timeout=10,
            shell=_SHELL_ON_WINDOWS,
        )
        if npm_result.returncode == 0:
            checks.append(WorkIQDiagnosticCheck(
                name="npm_version",
                status="PASS",
                detail=f"npm: {npm_result.stdout.strip()}",
                command="npm -v",
            ))
        else:
            checks.append(WorkIQDiagnosticCheck(
                name="npm_version",
                status="WARN",
                detail=f"npm -v が失敗しました (exit={npm_result.returncode})",
                command="npm -v",
            ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="npm_version",
            status="WARN",
            detail=f"npm -v の実行に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command="npm -v",
        ))

    # 6. npx -y @microsoft/workiq version
    try:
        ver_result = subprocess.run(
            [npx_cmd, "-y", "@microsoft/workiq", "version"],
            capture_output=True, text=True, timeout=60,
            shell=_SHELL_ON_WINDOWS,
        )
        if ver_result.returncode == 0:
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_version",
                status="PASS",
                detail=f"workiq version: {ver_result.stdout.strip()[:100]}",
                command=f"{npx_cmd} -y @microsoft/workiq version",
            ))
        else:
            stderr_short = _truncate_diagnostic_text(ver_result.stderr)
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_version",
                status="FAIL",
                detail=(
                    f"workiq version が失敗しました (exit={ver_result.returncode})"
                    + (f"\n  stderr: {stderr_short}" if stderr_short else "")
                ),
                command=f"{npx_cmd} -y @microsoft/workiq version",
            ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="workiq_version",
            status="FAIL",
            detail=f"workiq version の実行に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command=f"{npx_cmd} -y @microsoft/workiq version",
        ))

    # 7. accept-eula
    try:
        eula_result = subprocess.run(
            [npx_cmd, "-y", "@microsoft/workiq", "accept-eula"],
            capture_output=True, text=True, timeout=60,
            shell=_SHELL_ON_WINDOWS,
        )
        if eula_result.returncode == 0:
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_eula",
                status="PASS",
                detail="accept-eula 成功",
                command=f"{npx_cmd} -y @microsoft/workiq accept-eula",
            ))
        else:
            stderr_short = _truncate_diagnostic_text(eula_result.stderr)
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_eula",
                status="FAIL",
                detail=(
                    f"accept-eula が失敗しました (exit={eula_result.returncode})"
                    + (f"\n  stderr: {stderr_short}" if stderr_short else "")
                ),
                command=f"{npx_cmd} -y @microsoft/workiq accept-eula",
            ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="workiq_eula",
            status="FAIL",
            detail=f"accept-eula の実行に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command=f"{npx_cmd} -y @microsoft/workiq accept-eula",
        ))

    # 8. ask -q ping
    try:
        ping_result = subprocess.run(
            [npx_cmd, "-y", "@microsoft/workiq", "ask", "-q", "ping"],
            capture_output=True, text=True, timeout=60,
            shell=_SHELL_ON_WINDOWS,
        )
        if ping_result.returncode == 0:
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_ping",
                status="PASS",
                detail="ask -q ping 成功",
                command=f"{npx_cmd} -y @microsoft/workiq ask -q ping",
            ))
        else:
            stderr_short = _truncate_diagnostic_text(ping_result.stderr)
            checks.append(WorkIQDiagnosticCheck(
                name="workiq_ping",
                status="FAIL",
                detail=(
                    f"ask -q ping が失敗しました (exit={ping_result.returncode})"
                    + (f"\n  stderr: {stderr_short}" if stderr_short else "")
                ),
                command=f"{npx_cmd} -y @microsoft/workiq ask -q ping",
            ))
    except Exception as exc:
        checks.append(WorkIQDiagnosticCheck(
            name="workiq_ping",
            status="FAIL",
            detail=f"ask -q ping の実行に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            command=f"{npx_cmd} -y @microsoft/workiq ask -q ping",
        ))

    # 9. MCP 設定プレビュー
    mcp_config = build_workiq_mcp_config(tenant_id=tenant_id)
    _wiq_cfg = mcp_config[WORKIQ_MCP_SERVER_NAME]
    checks.append(WorkIQDiagnosticCheck(
        name="mcp_config",
        status="PASS",
        detail=(
            f"MCP config: command={_wiq_cfg['command']}, "
            f"args={_wiq_cfg['args']}, type={_wiq_cfg.get('type', '未設定')}"
        ),
    ))

    # 10. MCP 起動確認
    if skip_mcp_probe:
        checks.append(WorkIQDiagnosticCheck(
            name="mcp_startup",
            status="SKIP",
            detail="--skip-mcp-probe が指定されたためスキップ",
        ))
    else:
        mcp_check = probe_workiq_mcp_startup(
            npx_cmd=npx_cmd,
            tenant_id=tenant_id,
            timeout_seconds=mcp_probe_timeout,
        )
        checks.append(mcp_check)

    # 11. SDK セッション検証 (--sdk-probe 時のみ)
    if sdk_probe:
        try:
            sdk_checks = asyncio.run(
                probe_workiq_copilot_session(
                    tenant_id=tenant_id,
                    cli_path=cli_path,
                    cli_url=cli_url,
                    github_token=github_token,
                    timeout=sdk_probe_timeout,
                )
            )
            checks.extend(sdk_checks)
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_sdk_probe",
                status="FAIL",
                detail=f"SDK probe に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))

    # 12. SDK tool invocation 検証 (--sdk-tool-probe 時のみ)
    if sdk_tool_probe:
        try:
            sdk_tool_checks = asyncio.run(
                probe_workiq_copilot_tool_invocation(
                    tenant_id=tenant_id,
                    cli_path=cli_path,
                    cli_url=cli_url,
                    github_token=github_token,
                    timeout=sdk_tool_probe_timeout,
                    trace_events=sdk_event_trace,
                    tools_all=sdk_tool_probe_tools_all,
                )
            )
            checks.extend(sdk_tool_checks)
        except Exception as exc:
            checks.append(WorkIQDiagnosticCheck(
                name="copilot_tool_probe",
                status="FAIL",
                detail=f"SDK tool probe に失敗しました: {_truncate_diagnostic_text(str(exc))}",
            ))
    elif sdk_event_trace:
        checks.append(WorkIQDiagnosticCheck(
            name="copilot_sdk_event_trace",
            status="SKIP",
            detail="--sdk-event-trace は --sdk-tool-probe と組み合わせて使用してください",
        ))

    return WorkIQDiagnosticReport(checks=checks)
