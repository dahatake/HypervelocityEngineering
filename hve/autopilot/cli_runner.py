"""hve.autopilot.cli_runner — Qt 非依存の Autopilot 実行ランナー（CLI 用）。

`hve.gui.autopilot.child_launcher.AutopilotController` の Qt 非依存版。
QObject / QTimer / Signal を使わず、ブロッキングなポーリングループで
APP 単位の並列レーン × チェーン内直列実行を行う。

CLI から `python -m hve orchestrate --autopilot-chain <wfA,wfB,...>` で
呼び出される。
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .chain_runner import ChainState
from .plan_model import AutopilotPlan


def _detached_popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


@dataclass
class CliRunSummary:
    """CLI Autopilot 実行サマリ。"""

    total_apps: int = 0
    completed_apps: int = 0
    aborted_apps: List[str] = field(default_factory=list)
    aborted_codes: Dict[str, int] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return not self.aborted_apps and self.completed_apps == self.total_apps


class CliAutopilotRunner:
    """Qt 非依存の Autopilot 実行ランナー。

    AutopilotController と同じ「APP 単位の並列レーン + チェーン内直列」を
    ブロッキングポーリングで実現する。
    """

    def __init__(
        self,
        plan: AutopilotPlan,
        *,
        argv_factory: Optional[Callable[[str, str], List[str]]] = None,
        popen_factory: Optional[Callable[[List[str]], subprocess.Popen]] = None,
        poll_interval_sec: float = 0.1,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self._plan = plan
        self._argv_factory = argv_factory
        self._popen_factory = popen_factory or self._default_popen
        self._poll_interval = poll_interval_sec
        self._progress_cb = progress_callback
        self._states: Dict[str, ChainState] = {
            c.app_id: ChainState(chain=list(c.workflows))
            for c in plan.app_chains
        }
        self._pending: List[str] = [c.app_id for c in plan.app_chains]
        self._running: Dict[str, subprocess.Popen] = {}
        self._done = 0
        self._summary = CliRunSummary(total_apps=len(self._states))

    def _default_popen(self, argv: List[str]) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-m", "hve", *argv],
            stdout=None,
            stderr=None,
            **_detached_popen_kwargs(),
        )

    def _build_argv(self, app_id: str, workflow_id: str) -> List[str]:
        if self._argv_factory is not None:
            return self._argv_factory(app_id, workflow_id)
        return [
            "orchestrate",
            "--workflow",
            workflow_id,
            "--app-ids",
            app_id,
            "--workbench",
            "off",
        ]

    def _spawn_app_stage(self, app_id: str) -> None:
        state = self._states[app_id]
        wf = state.current()
        if wf is None:
            self._done += 1
            self._notify_progress()
            return
        argv = self._build_argv(app_id, wf)
        self._running[app_id] = self._popen_factory(argv)

    def _fill_slots(self) -> None:
        while self._pending and len(self._running) < self._plan.max_parallel:
            app_id = self._pending.pop(0)
            self._spawn_app_stage(app_id)

    def _notify_progress(self) -> None:
        if self._progress_cb is not None:
            try:
                self._progress_cb(self._done, len(self._states))
            except Exception:
                # progress callback の例外は実行に影響させない
                pass

    def _poll_once(self) -> None:
        total = len(self._states)
        completed: List[str] = []
        relaunch: List[str] = []

        for app_id, proc in list(self._running.items()):
            rc = proc.poll()
            if rc is None:
                continue
            event = self._states[app_id].on_stage_finished(rc)
            if event.name in ("COMPLETED", "ABORTED"):
                completed.append(app_id)
            else:
                relaunch.append(app_id)

        for app_id in completed:
            self._running.pop(app_id, None)
            self._done += 1
            state = self._states[app_id]
            if state.aborted_code is not None:
                self._summary.aborted_apps.append(app_id)
                self._summary.aborted_codes[app_id] = state.aborted_code
            else:
                self._summary.completed_apps += 1
            self._notify_progress()

        for app_id in relaunch:
            self._running.pop(app_id, None)
            self._spawn_app_stage(app_id)

        self._fill_slots()

    def run(self) -> CliRunSummary:
        total = len(self._states)
        if total == 0:
            self._notify_progress()
            return self._summary
        self._fill_slots()
        while self._done < total:
            self._poll_once()
            if self._done < total:
                time.sleep(self._poll_interval)
        return self._summary
