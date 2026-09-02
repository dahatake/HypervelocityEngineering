"""Orchestrator 実行コンテキスト。

`HVE_ORCHESTRATOR_ACTIVE` 環境変数の置き換え。CLI Orchestrator
(`hve orchestrate`) が起動時に生成し、`StepRunner` / `check_plan_md_metadata`
等へ明示的引数として伝播させる。Cloud Agent Orchestrator は GitHub
Issue Template + GitHub Actions + Copilot Coding Agent の Sub-Issue 経路を
正とし、この runtime split-fork は標準経路では使用しない。

設計方針 (copilot-instructions.md §0 / plan メモ参照):
  - **None == 単独実行モード**: Agent 直接起動・テスト等。Split Mode 検出時は
    plan.md + subissues.md のみ作成して停止する従来挙動。
    - **インスタンス有り == Orchestrator 配下**: run_id / continue_on_error 等を
        明示伝播する。Split Mode runtime fork は legacy / 実験用途の明示 opt-in
        (`split_fork_enabled=True`) のみで動作し、CLI / GUI 標準経路では無効。

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
        execution_id: durable execution の識別子。通常実行では None。
        instance_id: durable workflow instance の識別子。通常実行では None。
        expected_state_version: state transition の CAS 期待値。通常実行では None。
        recovery_action: 承認済みの復旧 action。通常実行では None。
        lease_owner: 親 controller が取得した lease owner。通常実行では None。
        lease_generation: 親 controller が取得した lease generation。通常実行では None。
        split_fork_enabled: Split Mode 検出時にサブタスクを fork 実行するか。
            既定 False。CLI / GUI 標準経路では GitHub Sub-Issue 相当の
            runtime fork を行わない。True は legacy / 実験用途の明示 opt-in。
        split_fork_depth: 現在の fork 再帰深度（0 起点）。サブタスク内で更に
            SPLIT が発生したケース用。
        split_fork_max_depth: 再帰深度上限。超えた場合は fork せず失敗扱い。
        max_parallel_subtasks: 同一 wave 内で並列実行するサブタスク数の上限。
        continue_on_error: True の場合、Pre-check 失敗を警告に降格して続行する
            （`local` 実行モード既定、`--strict` でオプトアウト）。Step 自体の
            失敗時は本フラグに関わらず R1 に従いワークフローを停止する。
            `github` 実行モード（Cloud）では常に False。
    """

    run_id: str = ""
    execution_id: Optional[str] = None
    instance_id: Optional[str] = None
    expected_state_version: Optional[int] = None
    recovery_action: Optional[str] = None
    lease_owner: Optional[str] = None
    lease_generation: Optional[int] = None
    split_fork_enabled: bool = False
    split_fork_depth: int = 0
    split_fork_max_depth: int = 2
    max_parallel_subtasks: int = 4
    continue_on_error: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("expected_state_version", self.expected_state_version),
            ("lease_generation", self.lease_generation),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        if (self.lease_owner is None) != (self.lease_generation is None):
            raise ValueError("lease_owner and lease_generation must be provided together")
        if self.recovery_action not in {None, "reuse-session", "restart-step"}:
            raise ValueError("unsupported recovery_action")

    def with_increased_depth(self) -> "OrchestratorContext":
        """再帰サブタスク向けに `split_fork_depth + 1` の新インスタンスを返す。"""
        return replace(self, split_fork_depth=self.split_fork_depth + 1)


def is_active(ctx: Optional[OrchestratorContext]) -> bool:
    """`ctx is not None` のショートカット（読みやすさのため）。"""
    return ctx is not None
