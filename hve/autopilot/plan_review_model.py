"""hve.autopilot.plan_review_model — Autopilot プランレビューのデータモデル（Qt 非依存）。

Step 1 [次へ] 押下時の Autopilot 統合事前検証で、以下を一覧化する:

  - 入力一覧（チェック済み全ステップの required_input_paths）
  - 出力一覧（チェック済み全ステップの output_paths、既存ファイルは流用可）
  - パラメータ一覧（Wizard Step 2 必須入力 + Workflow Settings）
  - ギャップ提案（不足入力に対する追加候補ステップ）

GUI 層（`hve.gui.autopilot.plan_review_dialog`）はこれを 4 タブで描画する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class FileStatus(str, Enum):
    """入力ファイルの状態。"""

    EXISTING_REUSABLE = "existing_reusable"
    """既存ファイルあり → 流用可能。"""

    MISSING_PRODUCED = "missing_produced"
    """不在だが、チェック済みの他ステップが生成予定。"""

    MISSING_GAP = "missing_gap"
    """不在かつ生成元なし → ギャップ提案の対象。"""

    UNKNOWN = "unknown"
    """output_paths 未宣言ステップが関与しており判定不能。"""


class ParameterCategory(str, Enum):
    """パラメータのカテゴリ。"""

    WIZARD = "wizard"
    """Wizard Step 2 入力。"""

    SETTING = "setting"
    """Workflow-specific 設定。"""


@dataclass(frozen=True)
class PlannedInput:
    """チェック済みステップが要求する 1 入力ファイル。"""

    workflow_id: str
    step_id: str
    path: str
    status: FileStatus
    producer: Optional[Tuple[str, str]] = None
    """``status == MISSING_PRODUCED`` の場合の (workflow_id, step_id)。"""


@dataclass(frozen=True)
class PlannedOutput:
    """チェック済みステップが生成予定の 1 出力ファイル。"""

    workflow_id: str
    step_id: str
    path: str
    already_exists: bool
    mtime_iso: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass(frozen=True)
class ParameterEntry:
    """1 パラメータの状態。"""

    workflow_id: str
    field_name: str
    category: ParameterCategory
    is_required: bool
    value_present: bool
    value_preview: Optional[str] = None
    """機密値は ``None``。"""


@dataclass(frozen=True)
class GapSuggestion:
    """ギャップ（不足入力）に対する追加ステップ候補。"""

    missing_path: str
    suggested_workflow_id: str
    suggested_step_id: str
    transitive_steps: List[str] = field(default_factory=list)
    """``suggested_step_id`` を有効化するために併せて ON にすべき depends_on 推移閉包。

    GUI 側「適用」時、当該 workflow について
    ``{suggested_step_id} ∪ transitive_steps`` のステップを有効化する。
    """


@dataclass(frozen=True)
class AutopilotPlanReview:
    """プランレビュー全体の集約結果。"""

    inputs: List[PlannedInput] = field(default_factory=list)
    outputs: List[PlannedOutput] = field(default_factory=list)
    parameters: List[ParameterEntry] = field(default_factory=list)
    gaps: List[GapSuggestion] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    """実行順に並べた workflow ID 列。

    GUI（Step1PlanReviewDialog）でプラン要約に表示し、
    「選択 ≠ 実行順」の乖離をユーザーが Step 1 で検出できるようにする。
    pre_phases（ARD/AAS）→ app_chains（aad-web/asdw-web 等）→ main_workflows
    の順で並べる。空 list の場合はプラン未解決として表示しない。
    """

    @property
    def has_blocking_gaps(self) -> bool:
        """ギャップ提案が 1 件以上ある場合 True。"""
        return bool(self.gaps)


__all__ = [
    "FileStatus",
    "ParameterCategory",
    "PlannedInput",
    "PlannedOutput",
    "ParameterEntry",
    "GapSuggestion",
    "AutopilotPlanReview",
]
