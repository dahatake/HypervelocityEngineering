"""hve.workbench — Workbench 風ターミナル UI パッケージ。

公開 API:
  RingBuffer, StepView, WorkbenchState, UserAction, TaskNode, TaskTree,
  clamp_body_window, BODY_WINDOW_MIN/MAX/DEFAULT, WorkbenchController,
  KeyReader (optional), save_useractions_report
"""

from .buffer import RingBuffer
from .state import (
    BODY_WINDOW_DEFAULT,
    BODY_WINDOW_MAX,
    BODY_WINDOW_MIN,
    StepView,
    UserAction,
    WorkbenchState,
    clamp_body_window,
)
from .task_tree import TaskNode, TaskTree

try:
    from .controller import WorkbenchController  # noqa: F401
    _HAS_CONTROLLER = True
except ImportError:
    _HAS_CONTROLLER = False

try:
    from .keyreader import KeyReader  # noqa: F401
    _HAS_KEYREADER = True
except ImportError:
    _HAS_KEYREADER = False

try:
    from .report import save_useractions_report  # noqa: F401
    _HAS_REPORT = True
except ImportError:
    _HAS_REPORT = False

__all__ = [
    "RingBuffer",
    "StepView",
    "UserAction",
    "WorkbenchState",
    "TaskNode",
    "TaskTree",
    "clamp_body_window",
    "BODY_WINDOW_DEFAULT",
    "BODY_WINDOW_MIN",
    "BODY_WINDOW_MAX",
]
if _HAS_CONTROLLER:
    __all__.append("WorkbenchController")
if _HAS_KEYREADER:
    __all__.append("KeyReader")
if _HAS_REPORT:
    __all__.append("save_useractions_report")
