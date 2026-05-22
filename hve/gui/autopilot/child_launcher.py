"""Autopilot child process launcher (parallel APP lanes, serial in-lane)."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from hve.autopilot.chain_runner import ChainState
from hve.autopilot.plan_model import AutopilotPlan
from .log_events import LogLineEvent


def _detached_popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


class AutopilotController(QObject):
    progress = Signal(int, int)  # done, total
    finished = Signal()
    # 子プロセス stdout 1 行分。マスター画面/各チェーン Window への配信用 (Q1/Q2/Q5)。
    log_line = Signal(object)  # LogLineEvent
    # チェーン (= 1 app_id) 完了通知 (app_id, returncode)。WorkbenchPage 側で進捗集計に
    # 用いる。returncode は最終ステージの rc。
    chain_finished = Signal(str, int)

    def __init__(
        self,
        plan: AutopilotPlan,
        *,
        argv_factory: Optional[Callable[[str, str], List[str]]] = None,
        popen_factory: Optional[Callable[[List[str]], subprocess.Popen]] = None,
        env_overrides: Optional[Dict[str, str]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._plan = plan
        self._argv_factory = argv_factory
        # Issue-gui-session-workdir-isolation T4b:
        # GuiSessionWorkdir.env_overrides() を MainWindow から伝搬する。
        # None なら従来通り親 env をそのまま継承する（後方互換）。
        self._env_overrides: Optional[Dict[str, str]] = (
            dict(env_overrides) if env_overrides else None
        )
        self._popen_factory = popen_factory or self._default_popen
        self._states: Dict[str, ChainState] = {
            c.app_id: ChainState(chain=list(c.workflows))
            for c in plan.app_chains
        }
        self._pending: List[str] = [c.app_id for c in plan.app_chains]
        self._running: Dict[str, subprocess.Popen] = {}
        # app_id -> 現在実行中の workflow_id（log_line emit 時に prefix へ含めるため）
        self._current_wf: Dict[str, str] = {}
        # app_id -> SubprocessReader（stdout を行単位で読み出すバックグラウンドスレッド）
        self._readers: Dict[str, object] = {}
        self._done = 0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        total = len(self._states)
        if total == 0:
            self.progress.emit(0, 0)
            self.finished.emit()
            return
        self._fill_slots()
        self._timer.start()

    def cancel_all(self) -> None:
        self._pending.clear()
        for proc in list(self._running.values()):
            try:
                proc.terminate()
            except OSError:
                pass
        self._running.clear()
        # SubprocessReader を停止（terminate 後の wait 完了まで内部でブロック）
        for reader in list(self._readers.values()):
            try:
                reader.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._readers.clear()
        self._current_wf.clear()
        if self._timer.isActive():
            self._timer.stop()
        self.finished.emit()

    def _default_popen(self, argv: List[str]) -> subprocess.Popen:
        if self._env_overrides:
            env = os.environ.copy()
            env.update(self._env_overrides)
        else:
            env = None
        return subprocess.Popen(
            [sys.executable, "-m", "hve", *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
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
            self.progress.emit(self._done, len(self._states))
            return
        argv = self._build_argv(app_id, wf)
        proc = self._popen_factory(argv)
        self._running[app_id] = proc
        self._current_wf[app_id] = wf
        # stdout を読み出す SubprocessReader を開始し、行ごとに log_line を emit する。
        # state_bridge.SubprocessReader は QThread ベース。テスト等で popen_factory が
        # PIPE 無しの Popen を返す場合は stdout=None となり、SubprocessReader は何も
        # emit せずに finished_with_code のみ通知する（既存仕様）。
        try:
            from ..state_bridge import SubprocessReader

            reader = SubprocessReader(proc, parent=self)

            def _emit(line: str, _app=app_id, _wf=wf) -> None:
                self.log_line.emit(LogLineEvent(app_id=_app, workflow_id=_wf, line=line))

            reader.line_received.connect(_emit)
            self._readers[app_id] = reader
            reader.start()
        except Exception:
            # ログ読み出しが構築できなくても本体のポーリングは継続する。
            pass

    def _fill_slots(self) -> None:
        while self._pending and len(self._running) < self._plan.max_parallel:
            app_id = self._pending.pop(0)
            self._spawn_app_stage(app_id)

    def _poll(self) -> None:
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
            proc_done = self._running.pop(app_id, None)
            self._current_wf.pop(app_id, None)
            reader = self._readers.pop(app_id, None)
            if reader is not None:
                try:
                    reader.wait(1000)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._done += 1
            self.progress.emit(self._done, total)
            try:
                rc = proc_done.returncode if proc_done is not None else 0
            except AttributeError:
                rc = 0
            self.chain_finished.emit(app_id, int(rc or 0))

        for app_id in relaunch:
            self._running.pop(app_id, None)
            self._current_wf.pop(app_id, None)
            reader = self._readers.pop(app_id, None)
            if reader is not None:
                try:
                    reader.wait(1000)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._spawn_app_stage(app_id)

        self._fill_slots()

        if self._done >= total:
            if self._timer.isActive():
                self._timer.stop()
            self.finished.emit()
