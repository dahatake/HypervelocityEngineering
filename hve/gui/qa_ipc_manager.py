"""hve.gui.qa_ipc_manager — QA IPC ディレクトリ監視 + ファイル授受マネージャ。

設計:
    - CLI (`hve.runner._collect_qa_answers_via_ipc`) が `<ipc_dir>/<step_id>.request.json`
      を書き出すと、本マネージャが `questionnaire_ready(step_id, questionnaire_path)`
      シグナルを発火する。
    - GUI 側ハンドラが `QAAnswerDialog` を表示し、回答結果を `write_answers()` で書き出す。
    - キャンセル時は `write_cancel()` で sentinel ファイルを生成する。
    - CLI subprocess の終了を `Popen.poll()` で監視し、終了時は `subprocess_terminated()`
      シグナル発火してダイアログを閉じる。

ファイル監視の信頼性:
    - QFileSystemWatcher は Windows / WSL / ネットワークドライブで新規ファイル検出が
      不安定なため、QTimer (1 秒間隔) で IPC ディレクトリを再スキャンする補助 polling を
      併用する。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Set

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


_POLL_INTERVAL_MS = 1000  # IPC dir 補助 polling 間隔
_SUBPROC_POLL_INTERVAL_MS = 1000  # subprocess.poll() チェック間隔


class QAIpcManager(QObject):
    """IPC ディレクトリを監視し、QA 質問票出現/subprocess 終了を通知する。

    Signals:
        questionnaire_ready(str step_id, str questionnaire_path, str ipc_dir):
            <ipc_dir>/<step_id>.request.json を検出した
        subprocess_terminated():
            監視中の subprocess.Popen が終了した（poll() != None）
    """

    questionnaire_ready = Signal(str, str, str)
    subprocess_terminated = Signal()

    def __init__(
        self,
        ipc_dir: Path,
        popen: Optional[subprocess.Popen] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._ipc_dir = Path(ipc_dir)
        self._popen = popen
        self._processed_requests: Set[str] = set()
        self._stopped = False

        # 起動前 IPC dir クリア（残留ファイル防止）
        # ※ tempfile.mkdtemp で新規生成された前提だが念のため
        try:
            self._ipc_dir.mkdir(parents=True, exist_ok=True)
            for f in self._ipc_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

        # QFileSystemWatcher (補助シグナル)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(self._ipc_dir))
        self._watcher.directoryChanged.connect(self._scan_for_requests)

        # 補助 polling (Windows での新規ファイル検出取りこぼし対策)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._scan_for_requests)
        self._poll_timer.start()

        # subprocess 終了監視
        self._subproc_timer = QTimer(self)
        if self._popen is not None:
            self._subproc_timer.setInterval(_SUBPROC_POLL_INTERVAL_MS)
            self._subproc_timer.timeout.connect(self._check_subprocess)
            self._subproc_timer.start()

    # ------------------------------------------------------------------
    # 監視ループ
    # ------------------------------------------------------------------

    def _scan_for_requests(self) -> None:
        """ipc_dir 内の *.request.json をスキャンして未処理分を発火。"""
        if self._stopped:
            return
        try:
            files = list(self._ipc_dir.glob("*.request.json"))
        except OSError:
            return
        for f in files:
            key = str(f.resolve())
            if key in self._processed_requests:
                continue
            data = self._read_request(f)
            if data is None:
                continue
            step_id = str(data.get("step_id", ""))
            q_path = str(data.get("questionnaire_path", ""))
            if not step_id or not q_path:
                continue
            self._processed_requests.add(key)
            self.questionnaire_ready.emit(step_id, q_path, str(self._ipc_dir))

    @staticmethod
    def _read_request(path: Path) -> Optional[dict]:
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError):
            return None

    def _check_subprocess(self) -> None:
        if self._stopped or self._popen is None:
            return
        if self._popen.poll() is not None:
            self.subprocess_terminated.emit()
            self._subproc_timer.stop()

    # ------------------------------------------------------------------
    # GUI → CLI への書き込み (answers / cancel)
    # ------------------------------------------------------------------

    def write_answers(self, step_id: str, content: str) -> bool:
        """answers.md を tmp + os.replace でアトミック書き込み。"""
        return self._atomic_write(
            self._ipc_dir / f"{step_id}.answers.md", content
        )

    def write_cancel(self, step_id: str) -> bool:
        """cancel sentinel ファイル生成。"""
        return self._atomic_write(self._ipc_dir / f"{step_id}.cancel", "")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> bool:
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def stop_and_cleanup(self) -> None:
        """監視を停止し IPC ディレクトリを削除する。"""
        if self._stopped:
            return
        self._stopped = True
        try:
            self._poll_timer.stop()
        except Exception:
            pass
        try:
            self._subproc_timer.stop()
        except Exception:
            pass
        try:
            paths = self._watcher.directories()
            if paths:
                self._watcher.removePaths(paths)
        except Exception:
            pass

        # IPC dir 削除 (残ったファイルも掃除)
        try:
            if self._ipc_dir.exists():
                for f in self._ipc_dir.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                        except OSError:
                            pass
                try:
                    self._ipc_dir.rmdir()
                except OSError:
                    pass
        except OSError:
            pass

    @property
    def ipc_dir(self) -> Path:
        return self._ipc_dir
