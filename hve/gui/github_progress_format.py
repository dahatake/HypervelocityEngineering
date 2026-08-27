"""hve.gui.github_progress_format — 自動進捗コメントの Markdown 整形（FR-GUI-36）。

副作用のない純関数だけを置き、PySide6 へは依存しない。同じ入力からは常に同じ
本文を返す。token / prompt / 応答本文 / tool 入出力は引数に取らないため、構造上
コメント本文へ混入しない（FR-RTO-04 / NFR-SEC-01）。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from hve.gui.github_comment_format import format_console_log_comment
from hve.workiq import _sanitize_diagnostic_text

__all__ = [
    "FINAL_STATUSES",
    "PROGRESS_MARKER_PREFIX",
    "progress_marker",
    "format_progress_comment",
]

# run ごとの rolling comment を再特定するための隠しマーカー。
PROGRESS_MARKER_PREFIX = "<!-- hve-progress:run="

# Workflow 全体の終端状態。FR-GUI-36 の「最終更新」はこの集合に限る。
# Step 単位の terminal 状態（`skipped` / `blocked`）は Workflow の終了ではないため
# 含めない。interim で console を誤って付加しないための fail-closed な定義。
FINAL_STATUSES = frozenset({"done", "failed", "cancelled"})

# マーカー内でそのまま保持しても HTML コメントを壊さない文字。
# `>` を含めないため `-->` によるコメント早期終了を構造的に防ぐ。
_MARKER_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._:@/#-]")


def progress_marker(run_id: Any) -> str:
    """run を識別する隠しマーカーを返す。

    マーカーは後で抽出・照合するための識別子であり表セルではない。許可文字以外を
    `_` へ置換することで、HTML エンティティへの変換を伴わずに決定的な値を得る。
    """
    token = "" if run_id is None else str(run_id)
    return f"{PROGRESS_MARKER_PREFIX}{_MARKER_UNSAFE_RE.sub('_', token)} -->"


def _escape_cell(value: Any) -> str:
    """Markdown 表セルとして安全な文字列へ変換する。

    pipe / 改行 / HTML 特殊文字 / backtick をエスケープし、表崩れと HTML 注入を防ぐ。
    """
    text = "" if value is None else str(value)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("|", "&#124;").replace("`", "&#96;")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "<br>")


def _format_elapsed(value: Any) -> str:
    """経過秒を表示用へ整形する。取得できない場合は `-` を返す。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.2f}s"


def format_progress_comment(
    *,
    run_id: Any,
    workflow_id: Any,
    overall_status: Any,
    steps: Optional[Iterable[Mapping[str, Any]]],
    updated_at: Any,
    console_text: Optional[str] = None,
) -> str:
    """rolling 進捗コメントの本文を構築する（FR-GUI-36）。

    Args:
        run_id: GUI セッションの run-id。
        workflow_id: 対象 Workflow ID。
        overall_status: run 全体の状態。終端状態のときだけ `console_text` を採用する。
        steps: `step_id` / `status` / `elapsed` を持つ Step の並び。
        updated_at: 更新時刻（呼び出し側が決定した文字列）。
        console_text: 最終更新でだけ付加するコンソール出力。interim では無視する。

    Returns:
        Markdown のコメント本文。同じ入力からは常に同じ文字列を返す。
    """
    status_text = "" if overall_status is None else str(overall_status)

    lines = [
        progress_marker(run_id),
        "### HVE 実行進捗",
        "",
        "| 項目 | 値 |",
        "| --- | --- |",
        f"| run-id | `{_escape_cell(run_id)}` |",
        f"| workflow | `{_escape_cell(workflow_id)}` |",
        f"| 状態 | {_escape_cell(status_text)} |",
        f"| 更新時刻 | {_escape_cell(updated_at)} |",
        "",
        "| Step | Status | Elapsed |",
        "| --- | --- | --- |",
    ]

    for step in steps or ():
        if not isinstance(step, Mapping):
            continue
        lines.append(
            f"| `{_escape_cell(step.get('step_id'))}` "
            f"| {_escape_cell(step.get('status'))} "
            f"| {_format_elapsed(step.get('elapsed'))} |"
        )

    # FR-GUI-36: 最終更新だけコンソール末尾を付加する。interim では console_text を無視する。
    if console_text and status_text in FINAL_STATUSES:
        lines.extend(
            [
                "",
                format_console_log_comment(
                    _sanitize_diagnostic_text(console_text),
                    run_id=None if run_id is None else str(run_id),
                    workflow_id=None if workflow_id is None else str(workflow_id),
                ),
            ]
        )

    return "\n".join(lines)
