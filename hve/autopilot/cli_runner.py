"""hve.autopilot.cli_runner — Qt 非依存の Autopilot 実行ランナー（CLI 用）。

`hve.gui.autopilot.child_launcher.AutopilotController` の Qt 非依存版。
QObject / QTimer / Signal を使わず、ブロッキングなポーリングループで
APP 単位の並列レーン × チェーン内直列実行を行う。

CLI から `python -m hve orchestrate --autopilot-chain <wfA,wfB,...>` で
呼び出される。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from hve import runtime_observability as rto

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


# FR-CLI-80: NFR-TIME-02 の Cloud 側ジョブタイムアウト（360 分）と同値。
# CLI の既定タイムアウトは無入出力時間ベース（NFR-TIME-01）のため lane 全体を拘束しない。
# 本定数は観測専用で、超過しても lane を停止させない。
LANE_WALL_CLOCK_WARN_SECONDS: float = 360 * 60


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
        echo: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._plan = plan
        self._argv_factory = argv_factory
        self._popen_factory = popen_factory or self._default_popen
        self._poll_interval = poll_interval_sec
        self._progress_cb = progress_callback
        # 子の通常ログは親の stdout へ再出力する（既定）。
        self._echo = echo if echo is not None else print
        # FR-RTO-05: instance = workflow_id#app_id 単位で集計する。
        self.runtime_metrics = rto.RuntimeMetricsRegistry()
        self._readers: Dict[str, threading.Thread] = {}
        self._states: Dict[str, ChainState] = {
            c.app_id: ChainState(chain=list(c.workflows))
            for c in plan.app_chains
        }
        self._pending: List[str] = [c.app_id for c in plan.app_chains]
        self._running: Dict[str, subprocess.Popen] = {}
        self._clock = clock
        self._lane_started_at: Dict[str, float] = {}
        self._done = 0
        self._summary = CliRunSummary(total_apps=len(self._states))

    def _child_env(self) -> dict:
        """FR-RTO-02: 子プロセスにだけ stats 配信を許可する。"""
        env = os.environ.copy()
        env[rto.STATS_STREAM_ENV] = "1"
        return env

    def _default_popen(self, argv: List[str]) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-m", "hve", *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=self._child_env(),
            **_detached_popen_kwargs(),
        )

    def _consume_child_line(self, app_id: str, workflow_id: str, line: str) -> None:
        """子 1 行を集計へ反映し、観測行以外を再出力する。"""
        payload = rto.parse_stats_line(line)
        if payload is not None:
            instance_id = rto.make_instance_id(workflow_id, app_id)
            self.runtime_metrics.for_instance(instance_id).apply(payload)
            return
        if self._echo is None:
            return
        try:
            self._echo(f"[{app_id}][{workflow_id}] {line}")
        except Exception:
            pass

    def _drain_child(self, app_id: str, workflow_id: str, proc: subprocess.Popen) -> None:
        stream = getattr(proc, "stdout", None)
        if stream is None:
            return
        try:
            for raw in stream:
                self._consume_child_line(app_id, workflow_id, raw.rstrip("\r\n"))
        except (OSError, ValueError):
            pass

    def runtime_summary(self) -> str:
        """FR-RTO-05: run 全体の集計サマリー。"""
        return rto.format_runtime_summary(self.runtime_metrics.totals())

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
        proc = self._popen_factory(argv)
        # lane の起点は chain 内の最初の Workflow 起動時とする（FR-CLI-80）。
        self._lane_started_at.setdefault(app_id, self._clock())
        self._running[app_id] = proc
        if getattr(proc, "stdout", None) is not None:
            reader = threading.Thread(
                target=self._drain_child,
                args=(app_id, wf, proc),
                name=f"autopilot-drain-{app_id}",
                daemon=True,
            )
            self._readers[app_id] = reader
            reader.start()

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

    def _warn_if_lane_ran_long(self, app_id: str) -> None:
        """FR-CLI-80: lane の経過時間を観測し、超過時に警告だけ出す（停止しない）。"""
        started = self._lane_started_at.pop(app_id, None)
        if started is None:
            return
        try:
            elapsed = self._clock() - started
            if elapsed <= LANE_WALL_CLOCK_WARN_SECONDS:
                return
            self._echo(
                f"[{app_id}] ⚠ lane の経過時間が {elapsed / 60:.0f} 分に達しました"
                f"（目安 {LANE_WALL_CLOCK_WARN_SECONDS / 60:.0f} 分）。"
            )
        except Exception:
            # 観測の失敗で実行を止めない
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
            reader = self._readers.pop(app_id, None)
            if reader is not None:
                reader.join(timeout=2.0)
            self._done += 1
            self._warn_if_lane_ran_long(app_id)
            state = self._states[app_id]
            if state.aborted_code is not None:
                self._summary.aborted_apps.append(app_id)
                self._summary.aborted_codes[app_id] = state.aborted_code
            else:
                self._summary.completed_apps += 1
            self._notify_progress()

        for app_id in relaunch:
            self._running.pop(app_id, None)
            reader = self._readers.pop(app_id, None)
            if reader is not None:
                reader.join(timeout=2.0)
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
