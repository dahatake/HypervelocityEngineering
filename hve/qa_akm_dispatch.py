"""QA 回答保存後に AKM を直列バックグラウンド実行する。

FR-QA-03: source Workflow の DAG は待たせず、共有 ``knowledge/`` への
書込みだけをリポジトリ単位で直列化する。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from .config import SDKConfig, generate_run_id
except ImportError:  # pragma: no cover - top-level module compatibility
    from config import SDKConfig, generate_run_id  # type: ignore[no-redef]


_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: Dict[str, threading.Lock] = {}
_SENTINEL = object()


def _scrub_and_remove(path: Path) -> None:
    """一時的な秘密設定をゼロ埋めしてから削除する。"""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    with open(path, "r+b", buffering=0) as stream:
        if size:
            stream.write(b"\0" * size)
            stream.flush()
            os.fsync(stream.fileno())
    path.unlink()


def _process_lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.Lock())


class RepositoryAkmLock:
    """同一リポジトリの AKM 書込みをプロセス間で排他する。"""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.path = self.repo_root / ".hve" / "qa-akm.lock"
        self._process_lock = _process_lock_for(self.path)
        self._stream: Optional[Any] = None
        self._acquired = False

    def acquire(self) -> None:
        self._process_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = open(self.path, "a+b", buffering=0)
            descriptor = self._stream.fileno()
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                fcntl = __import__("fcntl")
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._acquired = True
        except BaseException:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self._process_lock.release()
            raise

    def close(self) -> None:
        stream = self._stream
        if stream is None:
            return
        descriptor = stream.fileno()
        try:
            if self._acquired:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = __import__("fcntl")
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            self._acquired = False
            self._stream = None
            stream.close()
            self._process_lock.release()

    def __enter__(self) -> "RepositoryAkmLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


class QaAkmCoordinator:
    """検証済み QA ファイルを FIFO で AKM 子プロセスへ渡す。"""

    def __init__(
        self,
        config: SDKConfig,
        *,
        repo_root: Path,
        popen_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._config = config
        self._repo_root = Path(repo_root).resolve()
        self._popen_factory = popen_factory or subprocess.Popen
        self._queue: "queue.Queue[object]" = queue.Queue()
        self._state_lock = threading.Lock()
        self._results: List[Dict[str, Any]] = []
        self._reported_results = 0
        self._current_process: Optional[Any] = None
        self._cancelled = False
        self._sentinel_sent = False
        self._worker = threading.Thread(
            target=self._run,
            name="hve-qa-akm",
            daemon=True,
        )
        self._worker.start()

    def submit(self, qa_path: Path) -> None:
        with self._state_lock:
            if self._cancelled:
                raise RuntimeError("QA 起点 AKM coordinator は取消済みです")
        path = Path(qa_path)
        if ".." in path.parts:
            raise ValueError("QA ファイルパスに '..' は使用できません")
        resolved = path if path.is_absolute() else self._repo_root / path
        if resolved.is_symlink():
            raise ValueError("QA 同期対象にシンボリックリンクは使用できません")
        try:
            relative = resolved.resolve().relative_to(self._repo_root)
        except ValueError as exc:
            raise ValueError("QA ファイルはリポジトリ配下である必要があります") from exc
        if not relative.parts or relative.parts[0] != "qa" or relative.suffix.lower() != ".md":
            raise ValueError("AKM 同期対象は qa/ 配下の Markdown に限定されます")
        if not resolved.is_file():
            raise ValueError("AKM 同期対象の QA ファイルが存在しません")
        self._queue.put(relative)

    def drain(self) -> List[Dict[str, Any]]:
        self._queue.join()
        with self._state_lock:
            result = list(self._results[self._reported_results:])
            self._reported_results = len(self._results)
        return result

    def cancel(self) -> None:
        with self._state_lock:
            first_cancel = not self._cancelled
            self._cancelled = True
            process = self._current_process
        if process is not None and getattr(process, "returncode", None) is None:
            try:
                process.terminate()
            except OSError:
                pass

        if first_cancel:
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not _SENTINEL:
                    with self._state_lock:
                        self._results.append({"file": str(item), "returncode": -1, "cancelled": True})
                self._queue.task_done()
            with self._state_lock:
                if not self._sentinel_sent:
                    self._queue.put(_SENTINEL)
                    self._sentinel_sent = True
        self._worker.join(timeout=5)
        if self._worker.is_alive():
            with self._state_lock:
                process = self._current_process
            if process is not None and getattr(process, "returncode", None) is None:
                try:
                    process.kill()
                except OSError:
                    pass
            self._worker.join(timeout=5)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                path = Path(str(item))
                with self._state_lock:
                    cancelled = self._cancelled
                if cancelled:
                    with self._state_lock:
                        self._results.append({"file": str(path), "returncode": -1, "cancelled": True})
                    continue
                try:
                    self._execute(path)
                except Exception as exc:
                    with self._state_lock:
                        self._results.append({
                            "file": str(path),
                            "returncode": -1,
                            "error_type": type(exc).__name__,
                        })
            finally:
                self._queue.task_done()

    def _execute(self, qa_path: Path) -> None:
        run_id = f"qa-akm-{generate_run_id()}"
        work_root = self._repo_root / "work" / "run" / run_id
        work_root.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HVE_RUN_ID"] = run_id
        env["HVE_WORK_ROOT"] = str(work_root)
        env.pop("HVE_GUI_SESSION_ID", None)
        env.pop("HVE_STATS_STREAM", None)

        argv = self._build_argv(qa_path, work_root)
        mcp_path: Optional[Path] = None
        if self._config.mcp_servers:
            mcp_path = work_root / "mcp-config.json"
            descriptor = os.open(mcp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump({"mcpServers": self._config.mcp_servers}, stream, ensure_ascii=False)
                stream.write("\n")
            argv.extend(["--mcp-config", str(mcp_path)])

        returncode = -1
        error_type = ""
        try:
            process = self._popen_factory(
                argv,
                cwd=str(self._repo_root),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._state_lock:
                self._current_process = process
            returncode = int(process.wait())
        except Exception as exc:
            error_type = type(exc).__name__
        finally:
            with self._state_lock:
                self._current_process = None
            if mcp_path is not None:
                try:
                    _scrub_and_remove(mcp_path)
                except OSError as exc:
                    returncode = -1
                    error_type = type(exc).__name__
            with self._state_lock:
                result: Dict[str, Any] = {
                    "file": str(qa_path),
                    "returncode": returncode,
                }
                if error_type:
                    result["error_type"] = error_type
                self._results.append(result)

    def _build_argv(self, qa_path: Path, work_root: Path) -> List[str]:
        """許可した実行品質設定だけを子へ渡し、再帰・Git設定は渡さない。

        モデル / reasoning effort / context tier は AKM 専用設定（FR-QA-04）を
        優先し、未指定の項目だけメイン設定を継承する。
        """
        argv = [
            sys.executable,
            "-m",
            "hve",
            "orchestrate",
            "--workflow",
            "akm",
            "--sources",
            "qa",
            "--target-files",
            str(qa_path),
            "--no-force-refresh",
            "--workbench",
            "off",
        ]
        model = self._config.get_akm_model()
        if model:
            argv.extend(["--model", str(model)])
        reasoning_effort = (
            self._config.akm_reasoning_effort or self._config.reasoning_effort
        )
        if reasoning_effort:
            argv.extend(["--reasoning-effort", str(reasoning_effort)])
        context_tier = self._config.akm_context_tier or self._config.context_tier
        if context_tier:
            argv.extend(["--context-tier", str(context_tier)])
        if self._config.timeout_seconds and self._config.timeout_seconds > 0:
            argv.extend(["--timeout", str(self._config.timeout_seconds)])
        argv.append("--tool-search" if self._config.tool_search else "--no-tool-search")
        if self._config.tool_search_ranking:
            argv.extend(["--tool-search-ranking", str(self._config.tool_search_ranking)])
        if self._config.cli_path:
            argv.extend(["--cli-path", str(self._config.cli_path)])
        if self._config.cli_url:
            argv.extend(["--cli-url", str(self._config.cli_url)])
        return argv
