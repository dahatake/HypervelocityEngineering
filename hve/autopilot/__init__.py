"""hve.autopilot — Qt 非依存の Autopilot コアロジック（GUI / CLI 共通）。

GUI (`hve.gui.autopilot`) と CLI (`hve.__main__ --autopilot-chain`) の双方から
利用される、PySide6 に依存しない計画生成・チェーン状態機械・プランレビューを提供する。
"""

from .plan_model import (
    AppChain,
    AutopilotPlan,
    AutopilotSelection,
    SkippedApp,
    chain_for_kind,
    default_selection,
)
from .planner import build_plan, default_catalog_path
from .chain_runner import ChainEvent, ChainState, ChainSummary, summarize
from .plan_review_model import (
    AutopilotPlanReview,
    FileStatus,
    GapSuggestion,
    ParameterCategory,
    ParameterEntry,
    PlannedInput,
    PlannedOutput,
)
from .plan_review_runner import build_step1_plan_review

__all__ = [
    "AppChain",
    "AutopilotPlan",
    "AutopilotSelection",
    "SkippedApp",
    "chain_for_kind",
    "default_selection",
    "build_plan",
    "default_catalog_path",
    "ChainEvent",
    "ChainState",
    "ChainSummary",
    "summarize",
    "AutopilotPlanReview",
    "FileStatus",
    "GapSuggestion",
    "ParameterCategory",
    "ParameterEntry",
    "PlannedInput",
    "PlannedOutput",
    "build_step1_plan_review",
]
