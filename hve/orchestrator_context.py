"""Orchestrator 実行コンテキスト。

`HVE_ORCHESTRATOR_ACTIVE` 環境変数の置き換え。Orchestrator (CLI `hve orchestrate` /
Cloud Agent Orchestrator) が起動時に生成し、`StepRunner` / `check_plan_md_metadata`
等へ明示的引数として伝播させる。

設計方針 (copilot-instructions.md §0 / plan メモ参照):
  - **None == 単独実行モード**: Agent 直接起動・テスト等。Split Mode 検出時は
    plan.md + subissues.md のみ作成して停止する従来挙動。
  - **インスタンス有り == Orchestrator 配下**: Split Mode 検出時に subissues.md から
    サブタスクを並列実行し、全完了後に親 Step を完了扱いで後続へ進める。

`HVE_SPLIT_FORK_ENABLED` / `HVE_SPLIT_FORK_DEPTH` / `HVE_SPLIT_FORK_MAX_DEPTH` も
このコンテキストへ統合する（環境変数を参照しない）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class OrchestratorContext:
    """Orchestrator 配下で伝播される実行コンテキスト。

    Attributes:
        run_id: 親 run の識別子（observability 用）。
        split_fork_enabled: Split Mode 検出時にサブタスクを fork 実行するか。
            既定 True。False の場合は単独実行モードと同等に plan.md/subissues.md
            のみ作成して停止する（テスト・デバッグ用途）。
        split_fork_depth: 現在の fork 再帰深度（0 起点）。サブタスク内で更に
            SPLIT が発生したケース用。
        split_fork_max_depth: 再帰深度上限。超えた場合は fork せず失敗扱い。
        max_parallel_subtasks: 同一 wave 内で並列実行するサブタスク数の上限。
    """

    run_id: str = ""
    split_fork_enabled: bool = True
    split_fork_depth: int = 0
    split_fork_max_depth: int = 2
    max_parallel_subtasks: int = 4

    def with_increased_depth(self) -> "OrchestratorContext":
        """再帰サブタスク向けに `split_fork_depth + 1` の新インスタンスを返す。"""
        return replace(self, split_fork_depth=self.split_fork_depth + 1)


def is_active(ctx: Optional[OrchestratorContext]) -> bool:
    """`ctx is not None` のショートカット（読みやすさのため）。"""
    return ctx is not None
