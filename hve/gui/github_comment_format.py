"""hve.gui.github_comment_format — コンソール出力の PR コメント整形（FR-GUI-33）。

GUI から分離して検証できるよう、副作用を持たない純関数だけを置く。
PySide6 へは依存しない。
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = ["MAX_CONSOLE_LOG_LINES", "strip_ansi", "format_console_log_comment"]

# FR-GUI-33: 掲載は末尾 300 行まで。設定項目化しない。
MAX_CONSOLE_LOG_LINES = 300

# CSI / OSC を含む ANSI エスケープシーケンス。
_ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")

_FENCE_RUN_PATTERN = re.compile(r"^\s*(`{3,})", re.MULTILINE)


def strip_ansi(text: str) -> str:
    """ANSI エスケープシーケンスを除去する。"""
    return _ANSI_PATTERN.sub("", text or "")


def _fence_for(body: str) -> str:
    """本文中の最長バッククォート連より 1 つ長いフェンスを返す。"""
    longest = max((len(m.group(1)) for m in _FENCE_RUN_PATTERN.finditer(body)), default=0)
    return "`" * max(3, longest + 1)


def format_console_log_comment(
    text: str,
    *,
    run_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    max_lines: int = MAX_CONSOLE_LOG_LINES,
) -> str:
    """コンソール出力を Pull Request コメント本文へ整形する（FR-GUI-33）。

    Args:
        text: 実行面に表示されているコンソール出力の全文。
        run_id: GUI セッションの run-id。不明なら ``None``。
        workflow_id: 対象 Workflow ID。不明なら ``None``。
        max_lines: 掲載する末尾行数。

    Returns:
        Markdown のコメント本文。掲載を省略した場合はその旨を本文へ含める。
    """
    cleaned = strip_ansi(text or "")
    lines = cleaned.splitlines()
    total = len(lines)
    limit = max(1, int(max_lines))
    shown = lines[-limit:] if total > limit else lines
    omitted = total - len(shown)

    meta = [
        "| 項目 | 値 |",
        "| --- | --- |",
    ]
    if run_id:
        meta.append(f"| run-id | `{run_id}` |")
    if workflow_id:
        meta.append(f"| ワークフロー | `{workflow_id}` |")
    meta.append(f"| 総行数 | {total} |")
    meta.append(f"| 掲載行数 | {len(shown)} |")
    if omitted > 0:
        meta.append(f"| 省略行数 | 先頭 {omitted} 行を省略 |")

    body = "\n".join(shown)
    fence = _fence_for(body)
    summary = (
        f"コンソール出力（末尾 {len(shown)} 行 / 全 {total} 行）"
        if omitted > 0
        else f"コンソール出力（全 {total} 行）"
    )

    parts = [
        "### HVE コンソール出力",
        "",
        *meta,
        "",
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        f"{fence}text",
        body,
        fence,
        "",
        "</details>",
    ]
    return "\n".join(parts)
