"""hve.autopilot.precheck_model — Step 1 事前検証結果のデータモデル（Qt 非依存）。

Step 1 [次へ] 押下時の `run_step1_precheck()`（旧名: ``run_autopilot_precheck()``）が本モデルを返却し、
GUI 層（`precheck_dialog`）が不足項目をカテゴリ別に表示する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PrecheckCategory(str, Enum):
    """不足項目のカテゴリ。"""

    FILE = "file"
    """orchestrator step の required_artifacts で実存しないファイル。"""

    WIZARD_INPUT = "wizard_input"
    """Wizard Step 2 の必須入力フィールドで未入力。"""

    SETTING = "setting"
    """workflow-specific 必須設定（例: ARD target_business）。"""

    AUTH = "auth"
    """必須認証プロバイダで未認証。"""


@dataclass(frozen=True)
class PrecheckItem:
    """precheck で検出された不足項目 1 件。"""

    category: PrecheckCategory
    workflow_id: str
    """対象 workflow ID（auth など workflow 非依存の場合は空文字列）。"""

    step_id: Optional[str] = None
    """対象 orchestrator step ID（該当しない場合は None）。"""

    field_name: str = ""
    """不足しているファイルパス / フィールド名 / プロバイダ ID 等。"""

    description: str = ""
    """ユーザー向け説明（日本語）。"""

    remediation_hint: str = ""
    """修正手順のヒント（日本語）。"""

    soft: bool = False
    """workflow-level の soft 依存（不足でも警告のみ）かどうか。"""


@dataclass(frozen=True)
class AutopilotPrecheckResult:
    """`run_step1_precheck()`（旧名: ``run_autopilot_precheck()``）の戻り値。"""

    items: List[PrecheckItem] = field(default_factory=list)

    def is_ok(self) -> bool:
        """不足項目が 0 件なら True。"""
        return not self.items

    def by_category(self, category: PrecheckCategory) -> List[PrecheckItem]:
        return [it for it in self.items if it.category is category]

    def by_workflow(self, workflow_id: str) -> List[PrecheckItem]:
        return [it for it in self.items if it.workflow_id == workflow_id]

    def count(self) -> int:
        return len(self.items)


__all__ = [
    "PrecheckCategory",
    "PrecheckItem",
    "AutopilotPrecheckResult",
]
