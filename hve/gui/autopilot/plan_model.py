"""hve.gui.autopilot.plan_model — `hve.autopilot.plan_model` への後方互換シム。

Qt 非依存のコアロジックは `hve.autopilot` に移動済み。本モジュールは既存の
import パス（`from hve.gui.autopilot.plan_model import ...`）を維持するための薄い
re-export ラッパーであり、新規コードでは `hve.autopilot` を直接 import すること。
"""

from hve.autopilot.plan_model import (  # noqa: F401
    AppChain,
    AutopilotPlan,
    AutopilotSelection,
    SkippedApp,
    chain_for_kind,
    default_selection,
)

__all__ = [
    "AppChain",
    "AutopilotPlan",
    "AutopilotSelection",
    "SkippedApp",
    "chain_for_kind",
    "default_selection",
]
