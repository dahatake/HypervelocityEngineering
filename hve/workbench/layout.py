"""layout.py — Workbench の Rich Layout 構築と各ペイン Renderable。

ペイン構成（上から）:
  1. header1     : 1 行（アプリ名 + workflow_id + run_id）
  2. header2     : 3 行（ステップ状態色付き）
  3. body        : body_window + 2 行（Panel 枠）
  4. tasktree    : 5 行（既定）/ 3〜12 で可変
  5. useractions : 5 行 + Panel 枠 2
  6. userinteraction : 1 行 + Panel 枠 2
  7. footer      : 1 行（Context + model + elapsed）

狭端末フォールバック優先順位: useractions → userinteraction → tasktree。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List, Optional

from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from .state import StepView, WorkbenchState


_STATUS_GLYPH = {
    "pending": ("○", "dim white"),
    "running": ("◇", "bold yellow"),
    "done": ("●", "bold green"),
    "failed": ("✗", "bold red"),
    "skipped": ("⊘", "dim cyan"),
}

HEADER2_MAX_LINES = 3
USER_ACTIONS_PANEL_HEIGHT = 5 + 2
USER_INTERACTION_PANEL_HEIGHT = 1 + 2

TASKTREE_DEFAULT_HEIGHT = 5
TASKTREE_MIN_HEIGHT = 3
TASKTREE_MAX_HEIGHT = 12


def _required_rows(body_window: int, tasktree_height: int) -> int:
    return (
        1
        + HEADER2_MAX_LINES
        + (body_window + 2)
        + (tasktree_height + 2)
        + USER_ACTIONS_PANEL_HEIGHT
        + USER_INTERACTION_PANEL_HEIGHT
        + 1
    )


def _clamp_tasktree_height(h: int) -> int:
    if h < TASKTREE_MIN_HEIGHT:
        return TASKTREE_MIN_HEIGHT
    if h > TASKTREE_MAX_HEIGHT:
        return TASKTREE_MAX_HEIGHT
    return h


def make_layout(
    body_window: int,
    *,
    console_height: Optional[int] = None,
    tasktree_height: int = TASKTREE_DEFAULT_HEIGHT,
) -> Layout:
    """7 ペイン Layout を構築する。

    端末高さが不足する場合のフォールバック順:
      フル → -useractions → -userinteraction → -tasktree（最後まで残す）。
    """
    tasktree_height = _clamp_tasktree_height(tasktree_height)
    layout = Layout()

    # フォールバック判定
    drop_useractions = False
    drop_userinteraction = False
    drop_tasktree = False
    if console_height is not None:
        try:
            ch = int(console_height)
            need_full = _required_rows(body_window, tasktree_height)
            if ch < need_full:
                drop_useractions = True
                need = need_full - USER_ACTIONS_PANEL_HEIGHT
                if ch < need:
                    drop_userinteraction = True
                    need -= USER_INTERACTION_PANEL_HEIGHT
                    if ch < need:
                        drop_tasktree = True
        except Exception:
            pass

    cols: List[Layout] = [
        Layout(name="header1", size=1),
        Layout(name="header2", size=HEADER2_MAX_LINES),
        Layout(name="body", size=body_window + 2),
    ]
    if not drop_tasktree:
        cols.append(Layout(name="tasktree", size=tasktree_height + 2))
    if not drop_useractions:
        cols.append(Layout(name="useractions", size=USER_ACTIONS_PANEL_HEIGHT))
    if not drop_userinteraction:
        cols.append(Layout(name="userinteraction", size=USER_INTERACTION_PANEL_HEIGHT))
    cols.append(Layout(name="footer", size=1))
    layout.split_column(*cols)
    return layout


# ------------------------------------------------------------------
# 各ペインの Renderable
# ------------------------------------------------------------------


def render_header1(state: "WorkbenchState") -> Text:
    t = Text()
    t.append("HVE CLI Orchestrator", style="bold cyan")
    name = (state.workflow_name or "").strip()
    if state.workflow_id:
        t.append(" : ", style="dim")
        if name:
            t.append(name, style="bold white")
            t.append(f" ({state.workflow_id})", style="dim")
        else:
            t.append(state.workflow_id, style="bold white")
    t.append("   ")
    t.append(f"[run {state.run_id}]", style="dim")
    return t


def render_header2(state: "WorkbenchState") -> Group:
    cells = []
    for s in state.steps:
        glyph, style = _STATUS_GLYPH[s.status]
        fanout_total = getattr(s, "_fanout_total", None)
        if fanout_total is not None:
            done = getattr(s, "_fanout_done", 0)
            label = f"{s.id}.{s.title} ({done}/{fanout_total})"
        else:
            label = f"{s.id}.{s.title}"
        retry_n = getattr(s, "_retry_count", 0)
        if retry_n and retry_n > 0:
            label = f"{label} (retry {retry_n})"

        if s.status == "running":
            cell = Group(Spinner("dots", text=Text(f" {label}", style=style)))
        else:
            cell = Text(f"{glyph} {label}", style=style)
        cells.append(cell)

    if not cells:
        return Group(Text(""))

    plain_total = sum(len(_extract_plain(c)) + 2 for c in cells)
    if plain_total > HEADER2_MAX_LINES * 100:
        return Group(_render_summary_line(state))

    table = Table.grid(padding=(0, 1))
    for cell in cells:
        table.add_column(no_wrap=False)
    table.add_row(*cells)
    return Group(table)


def _extract_plain(renderable) -> str:
    if isinstance(renderable, Text):
        return renderable.plain
    if isinstance(renderable, Spinner):
        return ""
    if isinstance(renderable, Group):
        try:
            return "".join(_extract_plain(r) for r in renderable.renderables)
        except Exception:
            return ""
    return ""


def _render_summary_line(state: "WorkbenchState") -> Text:
    total = len(state.steps)
    done = sum(1 for s in state.steps if s.status in ("done", "skipped"))
    failed = sum(1 for s in state.steps if s.status == "failed")
    t = Text()
    t.append(f"{done}/{total} done", style="bold green")
    if failed:
        t.append(f"  {failed} failed", style="bold red")
    if state.current_running_step_id:
        for s in state.steps:
            if s.id == state.current_running_step_id:
                t.append(f"   ▶ {s.id}.{s.title}", style="bold yellow")
                break
    return t


def render_body(state: "WorkbenchState") -> Panel:
    lines = state.body.view(window=state.body_window, offset=state.scroll_offset)
    text = Text("\n".join(lines))
    title = "output"
    if state.scroll_offset > 0:
        max_off = state.body.max_offset(state.body_window)
        title = f"output  [scroll -{state.scroll_offset}/{max_off}]"
    return Panel(text, title=title, title_align="left", border_style="dim", padding=(0, 1))


def render_task_tree(
    state: "WorkbenchState",
    *,
    max_lines: int = TASKTREE_DEFAULT_HEIGHT,
    max_width: int = 120,
) -> Panel:
    """タスクツリーペイン: workflow ルート + サブタスクを階層表示。"""
    lines = state.task_tree.render_lines(
        time.monotonic(),
        max_lines=max_lines,
        max_width=max_width,
    )
    if not lines:
        body = Text("（タスクなし）", style="dim")
    else:
        body = Group(*lines)
    title = "tasks"
    return Panel(body, title=title, title_align="left", border_style="dim", padding=(0, 1))


_LEVEL_STYLE = {
    "INFO": "cyan",
    "WARN": "yellow",
    "ERROR": "bold red",
}


def render_user_actions(state: "WorkbenchState") -> Panel:
    """UserActions ペイン: 書式 `[HH:MM:SS] {step_id|[main]}: {category|level}: {message}`。"""
    actions = state.user_actions_view()
    if not actions:
        body = Text("（通知はまだありません）", style="dim")
    else:
        lines: List[Text] = []
        for a in actions:
            step = a.step_id or "[main]"
            cat = a.category or a.level
            line = Text()
            line.append(f"[{a.timestamp}] ", style="dim")
            line.append(f"{step}", style="bold white")
            line.append(": ", style="dim")
            line.append(f"{cat}", style=_LEVEL_STYLE.get(a.level, "white"))
            line.append(": ", style="dim")
            line.append(a.message, style="white")
            lines.append(line)
        body = Group(*lines)
    title = "user actions"
    total = len(state.user_actions)
    max_off = state.user_actions_max_offset()
    if total > 0:
        if state.user_actions_scroll > 0:
            title = f"user actions  [scroll -{state.user_actions_scroll}/{max_off}] ({total})"
        else:
            title = f"user actions ({total})"
    return Panel(body, title=title, title_align="left", border_style="dim", padding=(0, 1))


# userinteraction ペインの待機時ヘルプ文（`/session-store` 削除済み）。
_USER_INTERACTION_HELP = (
    "Press `:` to enter command  |  /help  "
    "|  Esc to cancel  |  Scroll: ↑↓ body, [ ] actions, g/G top/bottom"
)

_USER_INTERACTION_HELP_DONE = (
    "> /exit  （タスク完了：/exit で終了 | スクロール可: ↑↓ body, [ ] actions, g/G）"
)


def render_user_interaction(state: "WorkbenchState") -> Panel:
    if state.cmd_mode:
        line = Text()
        line.append("> ", style="bold cyan")
        line.append(state.cmd_buffer, style="white")
        line.append("_", style="bold cyan")
    elif state.all_done:
        line = Text(_USER_INTERACTION_HELP_DONE, style="bold yellow")
    else:
        line = Text(_USER_INTERACTION_HELP, style="dim")
    title = "userinteraction"
    return Panel(line, title=title, title_align="left", border_style="dim", padding=(0, 1))


def render_footer(state: "WorkbenchState") -> Text:
    t = Text()
    if state.context_limit > 0:
        pct = state.context_current / state.context_limit * 100
        t.append("Context: ", style="dim")
        t.append(f"{state.context_current:,}/{state.context_limit:,}", style="white")
        t.append(f" ({pct:.0f}%)", style="bold yellow" if pct >= 80 else "dim")
    else:
        t.append("Context: -/-", style="dim")
    t.append("   ｜   ", style="dim")
    t.append("model: ", style="dim")
    t.append(state.model or "unknown", style="bold cyan")
    # elapsed
    elapsed_sec = max(0.0, time.monotonic() - state.workflow_started_at)
    total = int(elapsed_sec)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    t.append("   ｜   ", style="dim")
    t.append("elapsed: ", style="dim")
    t.append(f"{hh:02d}:{mm:02d}:{ss:02d}", style="bold white")
    return t


def update_layout(layout: Layout, state: "WorkbenchState") -> None:
    layout["header1"].update(render_header1(state))
    layout["header2"].update(render_header2(state))
    layout["body"].update(render_body(state))
    try:
        layout["tasktree"].update(
            render_task_tree(state, max_lines=TASKTREE_DEFAULT_HEIGHT)
        )
    except KeyError:
        pass
    try:
        layout["useractions"].update(render_user_actions(state))
    except KeyError:
        pass
    try:
        layout["userinteraction"].update(render_user_interaction(state))
    except KeyError:
        pass
    layout["footer"].update(render_footer(state))
