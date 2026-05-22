"""hve.autopilot.chain_runner — Autopilot チェーン直列実行の状態機械（Qt 非依存コア）。

後方互換のため `hve.gui.autopilot.chain_runner` 経由でも同じシンボルを参照可能。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ChainEvent(Enum):
    ADVANCED = "advanced"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class ChainState:
    chain: List[str]
    index: int = 0
    aborted_code: Optional[int] = None
    completed: bool = False

    def __post_init__(self) -> None:
        if not self.chain:
            raise ValueError("chain must contain at least 1 workflow id")

    def current(self) -> Optional[str]:
        if self.aborted_code is not None or self.completed:
            return None
        if 0 <= self.index < len(self.chain):
            return self.chain[self.index]
        return None

    def on_stage_finished(self, code: int) -> ChainEvent:
        if self.aborted_code is not None or self.completed:
            return ChainEvent.ABORTED if self.aborted_code is not None else ChainEvent.COMPLETED
        if code != 0:
            self.aborted_code = code
            return ChainEvent.ABORTED
        self.index += 1
        if self.index >= len(self.chain):
            self.completed = True
            return ChainEvent.COMPLETED
        return ChainEvent.ADVANCED

    def is_terminal(self) -> bool:
        return self.aborted_code is not None or self.completed


@dataclass(frozen=True)
class ChainSummary:
    chain: List[str]
    completed: bool
    aborted_at: Optional[str]
    aborted_code: Optional[int]


def summarize(state: ChainState) -> ChainSummary:
    aborted_at = None
    if state.aborted_code is not None and 0 <= state.index < len(state.chain):
        aborted_at = state.chain[state.index]
    return ChainSummary(
        chain=list(state.chain),
        completed=state.completed,
        aborted_at=aborted_at,
        aborted_code=state.aborted_code,
    )
