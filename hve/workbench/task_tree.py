"""task_tree.py — Workbench タスクツリーモデル + Renderer。

メイン（workflow）/ サブタスク（step / fan-out child / subagent）を階層構造で
保持し、行ベースで描画する。

表示書式（1 行）:
    {indent}{title} {hh:mm:ss} {status}: {activity}

`indent` は階層 0 で空、階層 1 で `|- `、階層 2 で `|  |- ` のように `|  ` を
ネストする。

オーバーフロー時の表示優先順位:
    (1) workflow ルート
    (2) status == "running"
    (3) status == "failed"
    (4) status == "done"  （新しい順）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from rich.text import Text


NodeKind = Literal["workflow", "step", "fanout_child", "subagent"]
NodeStatus = Literal["pending", "running", "done", "failed", "skipped"]


_STATUS_STYLE = {
    "pending": "dim white",
    "running": "bold yellow",
    "done": "bold green",
    "failed": "bold red",
    "skipped": "dim cyan",
}


def _format_elapsed(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


@dataclass
class TaskNode:
    id: str
    title: str
    status: NodeStatus = "pending"
    kind: NodeKind = "step"
    started_at_monotonic: Optional[float] = None
    finished_at_monotonic: Optional[float] = None
    current_activity: str = ""
    children: List["TaskNode"] = field(default_factory=list)


class TaskTree:
    """workflow ルート 1 つ + 任意階層のサブタスクを保持する汎用ツリー。"""

    def __init__(self) -> None:
        self._root: Optional[TaskNode] = None
        self._index: Dict[str, TaskNode] = {}
        self._parent: Dict[str, Optional[str]] = {}

    @property
    def root(self) -> Optional[TaskNode]:
        return self._root

    def add_root(self, node: TaskNode) -> None:
        node.kind = "workflow"
        self._root = node
        self._index[node.id] = node
        self._parent[node.id] = None

    def add_child(self, parent_id: str, node: TaskNode) -> bool:
        parent = self._index.get(parent_id)
        if parent is None:
            return False
        if node.id in self._index:
            return False
        parent.children.append(node)
        self._index[node.id] = node
        self._parent[node.id] = parent_id
        return True

    def update(self, node_id: str, **fields) -> bool:
        node = self._index.get(node_id)
        if node is None:
            return False
        for k, v in fields.items():
            if hasattr(node, k):
                setattr(node, k, v)
        return True

    def get(self, node_id: str) -> Optional[TaskNode]:
        return self._index.get(node_id)

    def _node_elapsed(self, node: TaskNode, now_monotonic: float) -> float:
        """単一ノードの elapsed 秒数（完了時は凍結、未開始は 0）。"""
        if node.started_at_monotonic is None:
            return 0.0
        if node.finished_at_monotonic is not None:
            return max(0.0, node.finished_at_monotonic - node.started_at_monotonic)
        return max(0.0, now_monotonic - node.started_at_monotonic)

    def aggregate_elapsed(self, node_id: str, now_monotonic: float) -> float:
        """階層的合計 elapsed: 葉ノードは自身の elapsed、内部ノードは子の sum。

        並列実行の場合 sum > wall になる（作業合計の意味）。
        """
        node = self._index.get(node_id)
        if node is None:
            return 0.0
        if not node.children:
            return self._node_elapsed(node, now_monotonic)
        return sum(
            self.aggregate_elapsed(c.id, now_monotonic) for c in node.children
        )

    def iter_flatten(self) -> List[TaskNode]:
        """root → 子の DFS 順で flat な list を返す。"""
        out: List[TaskNode] = []
        if self._root is None:
            return out

        def _walk(n: TaskNode) -> None:
            out.append(n)
            for c in n.children:
                _walk(c)

        _walk(self._root)
        return out

    def _depth_of(self, node_id: str) -> int:
        depth = 0
        cur = self._parent.get(node_id)
        while cur is not None:
            depth += 1
            cur = self._parent.get(cur)
        return depth

    def render_lines(
        self,
        now_monotonic: float,
        *,
        max_lines: int,
        max_width: int = 120,
    ) -> List[Text]:
        """ツリーを 1 行ごとの Rich.Text として返す。

        max_lines 超過時は優先順位ルールで圧縮し、末尾に `... (+N hidden)` を加える。
        """
        if max_lines <= 0 or self._root is None:
            return []

        all_nodes = self.iter_flatten()
        # workflow ルートは常に含める
        visible: List[TaskNode] = []
        if max_lines >= 1:
            visible.append(all_nodes[0])
        remaining = max_lines - 1
        rest = all_nodes[1:]
        hidden_count = 0
        if remaining > 0 and rest:
            running = [n for n in rest if n.status == "running"]
            failed = [n for n in rest if n.status == "failed"]
            done = [n for n in rest if n.status == "done"]
            pending = [n for n in rest if n.status in ("pending", "skipped")]
            ordered: List[TaskNode] = []
            ordered.extend(running)
            ordered.extend(failed)
            ordered.extend(reversed(done))  # 新しい順（list 末尾が新しい想定）
            ordered.extend(pending)
            # 末尾 hidden 行のための席を 1 行確保するか判定
            need_overflow_line = len(ordered) > remaining
            slot = remaining - (1 if need_overflow_line else 0)
            if slot < 0:
                slot = 0
            picked = ordered[:slot] if need_overflow_line else ordered[:remaining]
            hidden_count = len(ordered) - len(picked)
            # 元のツリー DFS 順に並び替えて表示の安定性を保つ
            picked_set = {id(n) for n in picked}
            visible.extend([n for n in rest if id(n) in picked_set])

        lines: List[Text] = []
        for node in visible:
            depth = self._depth_of(node.id)
            indent = "|  " * max(0, depth - 1) + ("|- " if depth >= 1 else "")
            if node.kind == "workflow":
                # ルートは階層的合計（並列実行で sum > wall になる）
                elapsed_sec = self.aggregate_elapsed(node.id, now_monotonic)
                elapsed_label = f"合計 {_format_elapsed(elapsed_sec)}"
            else:
                elapsed_sec = self._node_elapsed(node, now_monotonic)
                if node.started_at_monotonic is None:
                    elapsed_label = "00:00:00"
                else:
                    elapsed_label = _format_elapsed(elapsed_sec)
            style = _STATUS_STYLE.get(node.status, "white")
            text = Text()
            text.append(indent, style="dim")
            text.append(node.title, style=style)
            text.append(f"  {elapsed_label}", style="dim")
            text.append(f"  {node.status}", style=style)
            if node.current_activity:
                text.append(": ", style="dim")
                text.append(node.current_activity, style="white")
            if max_width > 0:
                text.truncate(max_width, overflow="ellipsis")
            lines.append(text)

        if hidden_count > 0:
            t = Text()
            t.append(f"... (+{hidden_count} hidden)", style="dim italic")
            lines.append(t)

        return lines


__all__ = ["TaskNode", "TaskTree", "NodeKind", "NodeStatus"]
