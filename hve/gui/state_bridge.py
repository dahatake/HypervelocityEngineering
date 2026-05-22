"""hve.gui.state_bridge — orchestrator サブプロセスの stdout/stderr を
Qt シグナル経由で UI に非同期配信するブリッジ。

設計方針:
  - SubprocessReader (QThread) がサブプロセスの stdout を行単位で読み取り、
    line_received シグナルを emit する。
  - サブプロセス終了時は finished シグナルを emit。
  - WorkbenchWindow はこれを connect して QPlainTextEdit に append するだけでよい。

スレッド安全性:
  - SubprocessReader は専用 QThread で動作。
  - シグナル/スロット経由のため UI スレッドへの安全な伝播が保証される（Qt の
    キューデシリアライズ接続を自動使用）。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Dict, Optional

from PySide6.QtCore import QThread, Signal


_IS_WINDOWS = sys.platform == "win32"

# POSIX 専用シンボル（Windows の Pylance が `os.killpg` 等を未定義扱いするのを避けるため
# getattr で動的解決する。Windows では _IS_WINDOWS=True により下記参照経路に入らない）。
_os_getpgid = getattr(os, "getpgid", None)
_os_killpg = getattr(os, "killpg", None)
_SIGINT = getattr(signal, "SIGINT", None)
_SIGTERM = getattr(signal, "SIGTERM", None)
_SIGKILL = getattr(signal, "SIGKILL", None)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """サブプロセスとその全子孫を OS レベルで強制終了する（最終手段）。

    - Windows: ``taskkill /T /F /PID <pid>`` でプロセスツリー全体を強制終了。
    - POSIX  : ``os.killpg(pgid, SIGKILL)`` でプロセスグループ全体を強制終了。

    例外はすべて捕捉してログ無しで握りつぶす（ベストエフォート）。
    """
    pid = proc.pid
    try:
        if _IS_WINDOWS:
            # /T = ツリー終了, /F = 強制
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        else:
            if _os_getpgid is not None:
                try:
                    pgid = _os_getpgid(pid)
                except (ProcessLookupError, OSError):
                    pgid = pid
            else:
                pgid = pid
            if _os_killpg is not None and _SIGKILL is not None:
                try:
                    _os_killpg(pgid, _SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
    except (OSError, subprocess.SubprocessError):
        pass
    # 最終フォールバック
    try:
        proc.kill()
    except OSError:
        pass


class SubprocessReader(QThread):
    """サブプロセス stdout/stderr を行単位で読み取り Qt シグナルに変換する QThread。

    Usage:
        reader = SubprocessReader(proc)
        reader.line_received.connect(my_slot)
        reader.finished_with_code.connect(on_exit)
        reader.start()

    Args:
        proc: 既に起動済みの subprocess.Popen（stdout=PIPE, text=True 推奨）
        include_stderr: True の場合 stderr も同じシグナルで配信（stderr=STDOUT と組み合わせて使う）
    """

    # 1 行受信するたびに emit（行末改行なし）
    line_received = Signal(str)
    # サブプロセス終了時に returncode を emit
    finished_with_code = Signal(int)

    def __init__(
        self,
        proc: subprocess.Popen,
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._proc = proc

    def run(self) -> None:
        stdout = self._proc.stdout
        if stdout is None:
            self._proc.wait()
            self.finished_with_code.emit(self._proc.returncode or 0)
            return

        try:
            for raw_line in stdout:
                line = raw_line.rstrip("\n\r")
                self.line_received.emit(line)
        except ValueError:
            pass  # pipe が閉じた
        finally:
            self._proc.wait()
            self.finished_with_code.emit(self._proc.returncode or 0)

    def stop(self) -> None:
        """サブプロセスとその全子孫を段階的に終了してスレッドを停止する。

        段階:
          1. graceful: ``CTRL_BREAK_EVENT`` (Win) / ``SIGINT`` をプロセスグループへ送信
             → サブプロセス側 Python の ``KeyboardInterrupt`` 経由で ``finally`` ブロック
             （Copilot SDK ``client.stop()`` など）が実行される余地を与える。3 秒待機。
          2. terminate ツリー: 残っていれば ``taskkill /T /F`` (Win) / ``SIGTERM`` を
             プロセスグループへ送信。3 秒待機。
          3. kill: 最終手段で ``SIGKILL`` 相当（``taskkill /T /F`` 再送 or
             ``os.killpg(pgid, SIGKILL)`` + ``proc.kill()``）。
        """
        proc = self._proc
        pid = proc.pid

        # --- 段階 1: graceful (SIGINT 相当) ---
        try:
            if _IS_WINDOWS:
                # CREATE_NEW_PROCESS_GROUP で起動した場合のみ CTRL_BREAK_EVENT を
                # プロセスグループへ送れる。受信側は KeyboardInterrupt として扱う。
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                if _os_getpgid is not None:
                    try:
                        pgid = _os_getpgid(pid)
                    except (ProcessLookupError, OSError):
                        pgid = pid
                else:
                    pgid = pid
                if _os_killpg is not None and _SIGINT is not None:
                    _os_killpg(pgid, _SIGINT)
        except (OSError, ValueError, AttributeError):
            pass
        self.wait(3000)
        if not self.isRunning():
            return

        # --- 段階 2: terminate ツリー (SIGTERM 相当) ---
        try:
            if _IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            else:
                if _os_getpgid is not None:
                    try:
                        pgid = _os_getpgid(pid)
                    except (ProcessLookupError, OSError):
                        pgid = pid
                else:
                    pgid = pid
                if _os_killpg is not None and _SIGTERM is not None:
                    try:
                        _os_killpg(pgid, _SIGTERM)
                    except (ProcessLookupError, OSError):
                        pass
        except (OSError, subprocess.SubprocessError):
            pass
        self.wait(3000)
        if not self.isRunning():
            return

        # --- 段階 3: kill ツリー (SIGKILL 相当) ---
        _kill_process_tree(proc)
        self.wait(2000)


def launch_orchestrator(
    argv: list[str],
    *,
    env_overrides: Optional[Dict[str, str]] = None,
) -> subprocess.Popen:
    """orchestrator サブプロセスを起動して Popen を返す。

    Args:
        argv: `["orchestrate", "--workflow", "akm", ...]` 形式の引数リスト。
              先頭に `python -m hve` を自動付与する。
        env_overrides: 子プロセスの環境変数に追加マージする dict。
            Issue-gui-session-workdir-isolation T4a で追加。
            通常は ``GuiSessionWorkdir.env_overrides()`` を渡し
            ``HVE_WORK_ROOT`` / ``HVE_GUI_SESSION_ID`` を伝播する。
            None なら現行 ``os.environ`` をそのまま継承する（後方互換）。

    Note:
        設計書 §8.3 / §13.4 に従い、GUI モードでは `--workbench=off` を必ず付与する必要がある。
        通常は `OrchestrateArgs.to_argv()` が自動的に注入するため、本関数では追加の
        セーフティチェックとして `--workbench` 系フラグが含まれない場合に `--workbench=off`
        を末尾に追加する。
    """
    safe_argv = list(argv)
    if not any(a == "--workbench" or a.startswith("--workbench=") for a in safe_argv):
        safe_argv += ["--workbench", "off"]
    cmd = [sys.executable, "-m", "hve"] + safe_argv

    if env_overrides:
        env = os.environ.copy()
        env.update(env_overrides)
    else:
        env = None  # subprocess に None を渡すと親 env をそのまま継承

    # プロセスグループ化:
    #   - Windows: CREATE_NEW_PROCESS_GROUP により CTRL_BREAK_EVENT を子プロセス
    #     ツリーへ送信可能にする。
    #   - POSIX  : start_new_session=True により setsid() され、os.killpg() で
    #     子孫プロセスを含めた一括終了が可能になる。
    # これにより [停止] ボタンで orchestrator が起動した sub-agent / Copilot CLI 等の
    # 子孫プロセスもまとめて終了できる。
    extra_kwargs: dict = {}
    if sys.platform == "win32":
        extra_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        extra_kwargs["start_new_session"] = True

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # stderr も stdout にマージ
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # line-buffered
        env=env,
        **extra_kwargs,
    )
