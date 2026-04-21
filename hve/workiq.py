"""workiq.py — Work IQ (Microsoft 365) 連携モジュール

Microsoft Work IQ MCP サーバーを介して M365 データ（メール・チャット・会議・ファイル）を
読み取り専用で参照し、QA / KM / Original Docs レビューの補助情報として利用する。
"""

from __future__ import annotations

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

DEFAULT_WORKIQ_QA_PROMPT: str = (
    "Microsoft 365 の workiq ツールを使用して検索してください。\n"
    "過去1か月のメール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下の質問に関連する情報がないか調査してください。\n"
    "見つかった場合は、情報ソース（メール件名・送信者・日時、会議名・日時、"
    "ファイル名・パス等）とともに報告してください。\n"
    "見つからなかった場合は「関連情報なし」と報告してください。\n\n"
    "質問一覧:\n{target_content}"
)

DEFAULT_WORKIQ_KM_PROMPT: str = (
    "Microsoft 365 の workiq ツールを使用して検索してください。\n"
    "過去1か月のメール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下の Knowledge 項目に関連する情報がないか調査してください。\n"
    "見つかった場合は、情報ソース（メール件名・送信者・日時、会議名・日時、"
    "ファイル名・パス等）とともに報告してください。\n"
    "見つからなかった場合は「関連情報なし」と報告してください。\n\n"
    "Knowledge 項目:\n{target_content}"
)

DEFAULT_WORKIQ_REVIEW_PROMPT: str = (
    "Microsoft 365 の workiq ツールを使用して検索してください。\n"
    "過去1か月のメール、Teams チャット、会議、SharePoint/OneDrive のファイルの中に、"
    "以下のドキュメント内容と矛盾する情報や、補足すべき最新情報がないか調査してください。\n"
    "見つかった場合は、情報ソース（メール件名・送信者・日時、会議名・日時、"
    "ファイル名・パス等）とともに報告してください。\n"
    "見つからなかった場合は「関連情報なし」と報告してください。\n\n"
    "ドキュメント概要:\n{target_content}"
)


def is_workiq_available() -> bool:
    """@microsoft/workiq が利用可能かを検出する。"""
    global _workiq_available_cache
    if _workiq_available_cache is not None:
        return _workiq_available_cache
    with _workiq_cache_lock:
        if _workiq_available_cache is not None:
            return _workiq_available_cache

        if not shutil.which("npx"):
            _workiq_available_cache = False
            return False

        try:
            result = subprocess.run(
                ["npx", "-y", "@microsoft/workiq", "version"],
                capture_output=True,
                text=True,
                timeout=30,
                shell=_SHELL_ON_WINDOWS,
            )
            _workiq_available_cache = (result.returncode == 0)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError, OSError):
            _workiq_available_cache = False

        return _workiq_available_cache


def workiq_login(console: "Console", timeout: float = 120.0) -> bool:
    """Work IQ の認証を実行する（同期関数）。"""
    if _is_headless_environment():
        console.warning(
            "ヘッドレス環境（SSH / CI 等）を検出しました。"
            "Work IQ のブラウザ認証はスキップします。"
            "事前に `workiq accept-eula && workiq ask -q test` で認証を完了してください。"
        )
        return _has_cached_token()

    try:
        subprocess.run(
            ["npx", "-y", "@microsoft/workiq", "accept-eula"],
            timeout=timeout,
            check=True,
            capture_output=True,
            shell=_SHELL_ON_WINDOWS,
        )
        result = subprocess.run(
            ["npx", "-y", "@microsoft/workiq", "ask", "-q", "ping"],
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=_SHELL_ON_WINDOWS,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        console.warning(f"Work IQ 認証がタイムアウトしました ({timeout:.0f}秒)。")
        return False
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        console.warning(f"Work IQ 認証に失敗しました: {exc}")
        return False


def build_workiq_mcp_config(tenant_id: Optional[str] = None) -> dict:
    """Work IQ MCP サーバー設定 dict を返す（読み取り専用ツールのみ）。"""
    args = ["-y", "@microsoft/workiq", "mcp"]
    if tenant_id:
        args.extend(["-t", tenant_id])

    return {
        "_hve_workiq": {
            "command": "npx",
            "args": args,
            "tools": [
                "search_emails",
                "search_messages",
                "search_meetings",
                "search_files",
                "search_people",
                "get_calendar",
                "ask",
            ],
        }
    }


async def query_workiq(
    session: Any,
    query: str,
    timeout: float = 120.0,
) -> str:
    """Work IQ 経由で M365 データを問い合わせる。

    session は `send_and_wait(prompt: str, timeout: float)` を持つオブジェクトを想定する。
    """
    try:
        response = await session.send_and_wait(query, timeout=timeout)
        if response is None:
            return ""
        data = getattr(response, "data", None)
        if data is not None:
            for attr in ("content", "message"):
                val = getattr(data, attr, None)
                if val is not None:
                    return sanitize_workiq_result(str(val))
        for attr in ("content", "text", "message"):
            val = getattr(response, attr, None)
            if val is not None:
                return sanitize_workiq_result(str(val))
        return ""
    except Exception:  # Work IQ 失敗時は本処理を継続（graceful degradation）
        return ""


_MAX_WORKIQ_CONTEXT_LENGTH: int = 10_000


def enrich_prompt_with_workiq(
    workiq_context: str,
    original_prompt: str,
    context_type: str = "参考情報",
) -> str:
    """Work IQ 結果をプロンプト先頭に注入する。"""
    if not workiq_context or not workiq_context.strip():
        return original_prompt

    truncated = _truncate_workiq_context(workiq_context, _MAX_WORKIQ_CONTEXT_LENGTH)

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
    base_dir: str = "work",
) -> Optional[Path]:
    """Work IQ クエリ結果をファイルに永続化する。"""
    if not result or not result.strip():
        return None

    safe_run_id = re.sub(r"[^A-Za-z0-9\-_]", "", run_id) or "unknown"
    safe_step_id = re.sub(r"[^A-Za-z0-9\-_.]", "", step_id) or "unknown"

    out_dir = Path(base_dir) / safe_run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"workiq-{safe_step_id}-{mode}.md"

    try:
        truncated_result = _truncate_workiq_context(result, 50_000)
        header = (
            "# Work IQ 調査結果\n\n"
            f"- **run_id**: {safe_run_id}\n"
            f"- **step_id**: {safe_step_id}\n"
            f"- **mode**: {mode}\n"
            f"- **timestamp**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
            "---\n\n"
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
