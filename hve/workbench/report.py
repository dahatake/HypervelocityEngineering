"""report.py — useractions レポート保存（冪等 + 排他制御）。

出力パス:
    work/<workflow_id>/<run_id>-<YYYYMMDD-HHMMSS>-useractions-report.md

衝突時は末尾に `-2`, `-3`... のサフィックスを付与する（O_EXCL 相当の排他作成）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .state import WorkbenchState


def _format_wall(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def _format_path_ts(epoch: float) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(epoch))


def _escape_cell(s: str) -> str:
    # Markdown テーブルセル内のパイプ / 改行を無害化
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _build_markdown(
    state: "WorkbenchState",
    *,
    workflow_id: str,
    run_id: str,
    started_at_wall: float,
    ended_at_wall: float,
) -> str:
    lines = []
    lines.append("# UserActions Report")
    lines.append("")
    lines.append(f"- workflow_id: {workflow_id}")
    lines.append(f"- run_id: {run_id}")
    lines.append(
        f"- started_at: {_format_wall(started_at_wall)} (local) / epoch={started_at_wall:.3f}"
    )
    lines.append(
        f"- ended_at: {_format_wall(ended_at_wall)} (local) / epoch={ended_at_wall:.3f}"
    )
    lines.append(f"- total: {len(state.user_actions)}")
    lines.append("")
    lines.append("## Records")
    lines.append("")
    lines.append("| # | timestamp | step | category/level | message |")
    lines.append("|---|-----------|------|----------------|---------|")
    for i, a in enumerate(state.user_actions, start=1):
        step = a.step_id or "[main]"
        cat = a.category or a.level
        lines.append(
            f"| {i} | {_escape_cell(a.timestamp)} | {_escape_cell(step)} | "
            f"{_escape_cell(cat)} | {_escape_cell(a.message)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _resolve_unique_path(base: Path) -> Path:
    """O_EXCL で作成可能なパスを返す（衝突時は -2, -3, ... 付与）。"""
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    i = 2
    while True:
        cand = parent / f"{stem}-{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1
        if i > 9999:
            raise RuntimeError(f"too many collisions for {base}")


def save_useractions_report(
    state: "WorkbenchState",
    *,
    workflow_id: str,
    run_id: str,
    started_at_wall: Optional[float] = None,
    base_dir: Path = Path("work"),
) -> Path:
    """useractions を Markdown レポートとして保存する。

    冪等性: `state.report_saved=True` の場合は no-op で `Path("")` を返す。
    呼び出し側はパスが必要なら別途記録すること。
    """
    if state.report_saved:
        return Path("")

    if started_at_wall is None:
        started_at_wall = state.workflow_started_at_wall
    ended_at_wall = time.time()

    ts = _format_path_ts(started_at_wall)
    target_dir = base_dir / workflow_id
    target_dir.mkdir(parents=True, exist_ok=True)
    base_path = target_dir / f"{run_id}-{ts}-useractions-report.md"

    content = _build_markdown(
        state,
        workflow_id=workflow_id,
        run_id=run_id,
        started_at_wall=started_at_wall,
        ended_at_wall=ended_at_wall,
    )

    # TOCTOU 回避: exists() で候補選定後も open("x") を FileExistsError で
    # リトライし、本当に作成できた path を採用する。
    last_err: Optional[Exception] = None
    for _ in range(10000):
        cand = _resolve_unique_path(base_path)
        try:
            with cand.open("x", encoding="utf-8") as f:
                f.write(content)
            state.report_saved = True
            return cand
        except FileExistsError as exc:
            last_err = exc
            continue
    raise RuntimeError(f"failed to create unique report path under {target_dir}: {last_err}")


__all__ = ["save_useractions_report"]
