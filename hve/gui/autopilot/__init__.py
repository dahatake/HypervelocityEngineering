"""hve.gui.autopilot — GUI Orchestrator の Autopilot モード関連。"""

from .plan_model import (
  AppChain,
  AutopilotPlan,
  AutopilotSelection,
  SkippedApp,
  chain_for_kind,
  default_selection,
)
from .planner import build_plan, default_catalog_path
from .child_launcher import AutopilotController

__all__ = [
    "AppChain",
    "SkippedApp",
    "AutopilotPlan",
  "AutopilotSelection",
  "chain_for_kind",
  "default_selection",
    "build_plan",
  "default_catalog_path",
  "AutopilotController",
]
