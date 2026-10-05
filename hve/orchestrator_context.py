"""Orchestrator 実行コンテキスト。

`HVE_ORCHESTRATOR_ACTIVE` 環境変数の置き換え。CLI Orchestrator
(`hve orchestrate`) が起動時に生成し、`StepRunner` 等へ明示的引数として
伝播させる。

設計方針:
  - **None == 単独実行モード**: Agent 直接起動・テスト等。FR-WF-OUT-01 の
    成果物ゲートを適用しない。
  - **インスタンス有り == Orchestrator 配下**: run_id / continue_on_error 等を
    明示伝播する。分割は workflow DAG / fan-out で表現し、`subissues.md` を
    実行時に fork しない（FR-PLAN-01）。
"""

from __future__ import annotations

from dataclasses import dataclass
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


def is_active(ctx: Optional[OrchestratorContext]) -> bool:
    """`ctx is not None` のショートカット（読みやすさのため）。"""
    return ctx is not None
