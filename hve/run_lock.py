"""hve/run_lock.py — Phase 2 (Resume 2-layer txn): run_id 単位のクロスプロセスロック。

`<session-state-dir>/runs/<run_id>/.lock` ファイルに対して OS レベルのアドバイザリロックを取得し、
同一 `run_id` への並行 hve 実行（別プロセス / 別 PC）による state.json 競合を防ぐ。

== 設計 ==

- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` で排他的ノンブロッキングロック
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` で先頭 1 byte のロック（ファイル全体ロック）

ロックファイル内容は JSON で `{pid, hostname_hash, acquired_at, heartbeat_at}` を保持し、
他プロセスから読むことで stale 判定 (heartbeat 120 秒以上更新なし → 奪取可能) を行う。

== 並行安全性 ==

- `acquire()` は冪等ではない。同インスタンスで二重取得すると RuntimeError。
- `release()` は冪等。未取得状態で呼んでも例外は出ない。
- `with RunLock(run_id) as lock:` がプロセス終了時の解放を保証する。
- POSIX の `fcntl.flock` はプロセス単位なので、同一プロセス内の複数 fd で
  排他にならない仕様。本実装は同インスタンスへの二重取得を `_acquired` フラグで防ぐ。

== 既知の制約 ==

- NFS 等の分散ファイルシステムでは flock 挙動が未定義（C-01 マルチホスト前提外）。
- POSIX の flock は同一プロセス内のロックを互いに見ない（fcntl と異なる）。
  → 本実装は単一 RunLock インスタンスのみ使う前提。
"""

from __future__ import annotations

import datetime
import errno
import hashlib
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

LOCK_FILENAME: str = ".lock"
"""`<session-state-dir>/runs/<run_id>/.lock`"""

HEARTBEAT_INTERVAL_SECONDS: float = 30.0
"""heartbeat 更新間隔の推奨値（ユーザコードが呼び出す）。"""

STALE_TIMEOUT_SECONDS: float = 120.0
"""`heartbeat_at` がこの秒数以上更新されないロックは stale とみなし奪取可能。"""


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------

class RunLockError(RuntimeError):
    """ロック取得失敗時に投げられる例外。"""

    def __init__(self, message: str, *, held_by: Optional[dict] = None) -> None:
        super().__init__(message)
        self.held_by = held_by or {}


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hostname_hash_local() -> str:
    """`run_state._hostname_hash` と同等。循環 import を避けるため独自定義。"""
    import getpass
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown-host"
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown-user"
    return hashlib.sha256(f"{host}|{user}".encode("utf-8")).hexdigest()[:16]


def _parse_iso_utc(s: str) -> Optional[datetime.datetime]:
    """ISO 8601 UTC 文字列を datetime に変換。失敗時 None。"""
    if not s:
        return None
    try:
        normalized = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _is_stale(held_by: dict, *, timeout: float = STALE_TIMEOUT_SECONDS) -> bool:
    """既存ロック情報の heartbeat が timeout 秒以上更新されていないか判定。"""
    hb = held_by.get("heartbeat_at") or held_by.get("acquired_at") or ""
    parsed = _parse_iso_utc(hb)
    if parsed is None:
        # heartbeat 不明 → 安全側で stale と扱わない（誤奪取防止）
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - parsed).total_seconds() > timeout


# ---------------------------------------------------------------------------
# OS 抽象化
# ---------------------------------------------------------------------------

def _try_lock(fd: int) -> bool:
    """非ブロッキングで排他ロックを試みる。成功なら True。"""
    if sys.platform == "win32":
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            return True
        except OSError as exc:
            # 33 (EACCES) / 36 (EDEADLK) - 既にロック中
            if exc.errno in (errno.EACCES, errno.EDEADLK, 33, 36):
                return False
            raise
    else:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                return False
            raise


def _unlock(fd: int) -> None:
    """ロック解放。エラーは握り潰す（best-effort）。"""
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                # ファイル先頭にシークしてからアンロック（msvcrt の仕様）
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RunLock 本体
# ---------------------------------------------------------------------------

class RunLock:
    """`<session-state-dir>/runs/<run_id>/.lock` への排他ロック。

    使い方:
        with RunLock(run_id, work_dir) as lock:
            ...  # この区間は同 run_id への並行アクセスから保護される
            lock.heartbeat()  # 長時間ループ中に定期的に呼ぶ
    """

    def __init__(self, run_id: str, work_dir: Path) -> None:
        if not run_id:
            raise ValueError("run_id は必須です")
        self.run_id = run_id
        self.work_dir = Path(work_dir)
        self._lock_path = self.work_dir / run_id / LOCK_FILENAME
        self._fd: Optional[int] = None
        self._acquired: bool = False
        self._inst_lock = threading.Lock()
        self._pid = os.getpid()
        self._hostname_hash = _hostname_hash_local()
        self._acquired_at: str = ""

    # ----------------------------------------------------------------- API

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self, *, allow_stale_steal: bool = True) -> None:
        """ロックを取得する。

        Args:
            allow_stale_steal: stale lock を検出した場合に奪取するか。既定 True。
                stale 判定: 既存ロックの heartbeat が STALE_TIMEOUT_SECONDS 以上更新なし。

                Note: stale lock 奪取は best-effort であり、unlock→close→
                reopen→relock の間に別プロセスがロックを取得した場合は
                奪取失敗（RunLockError）となる。デッドロックは起きないが、
                呼び出し側は競合ケースを RunLockError として扱う必要がある。

        Raises:
            RunLockError: 他プロセスがロック中で stale でもない場合、
                または stale 奪取中に別プロセスがロックを取得した場合。
            RuntimeError: 既に同インスタンスで取得済みの場合。
        """
        with self._inst_lock:
            if self._acquired:
                raise RuntimeError(f"RunLock は既に取得済みです: {self._lock_path}")
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)

            # ロックファイルを開く（存在しなければ作成）
            # O_RDWR | O_CREAT で、書き込み時は明示 lseek+truncate
            fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                got = _try_lock(fd)
                if not got:
                    # 既存ロック情報を読む
                    held_by = self._read_lock_info_unsafe(fd)
                    if allow_stale_steal and _is_stale(held_by):
                        # stale lock を奪取
                        # 既存 fd は閉じて、再度 open + lock を試みる
                        # （別プロセスが既に解放済みなら今度は成功する）
                        _unlock(fd)
                        os.close(fd)
                        fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o644)
                        got = _try_lock(fd)
                        if not got:
                            held_by_2 = self._read_lock_info_unsafe(fd)
                            os.close(fd)
                            raise RunLockError(
                                f"stale lock 奪取試行後も取得失敗: {self._lock_path}",
                                held_by=held_by_2,
                            )
                    else:
                        os.close(fd)
                        raise RunLockError(
                            f"ロック取得失敗（別プロセスが保持中）: {self._lock_path}",
                            held_by=held_by,
                        )

                # ロック取得成功 → 情報を書き込む
                self._fd = fd
                self._acquired_at = _utc_now_iso()
                self._write_lock_info(fd, heartbeat_at=self._acquired_at)
                self._acquired = True
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise

    def heartbeat(self) -> None:
        """`heartbeat_at` を現在時刻で更新する。長時間ループ中に定期的に呼ぶ。

        未取得状態で呼ぶと RuntimeError。書き込み失敗は warn 相当（例外は再送出）。
        """
        with self._inst_lock:
            if not self._acquired or self._fd is None:
                raise RuntimeError("heartbeat() はロック未取得で呼べません")
            self._write_lock_info(self._fd, heartbeat_at=_utc_now_iso())

    def release(self) -> None:
        """ロックを解放する。冪等。"""
        with self._inst_lock:
            if not self._acquired or self._fd is None:
                self._acquired = False
                self._fd = None
                return
            try:
                _unlock(self._fd)
            finally:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
                self._acquired = False
                # ロックファイル自体は残す（他プロセスが open しても問題ない）

    def read_lock_info(self) -> dict:
        """現在のロックファイル内容を読む（取得失敗時の診断用）。"""
        if not self._lock_path.exists():
            return {}
        try:
            with self._lock_path.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            return {}

    # ----------------------------------------------------------- 内部実装

    def _read_lock_info_unsafe(self, fd: int) -> dict:
        """fd 経由でロック情報を読む（ロック失敗時の診断用）。"""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            data = os.read(fd, 4096).decode("utf-8")
            return json.loads(data) if data.strip() else {}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _write_lock_info(self, fd: int, *, heartbeat_at: str) -> None:
        """ロック情報を fd に書き込む（truncate + write + fsync）。"""
        info = {
            "pid": self._pid,
            "hostname_hash": self._hostname_hash,
            "acquired_at": self._acquired_at,
            "heartbeat_at": heartbeat_at,
            "run_id": self.run_id,
        }
        payload = json.dumps(info, ensure_ascii=False, indent=2)
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, payload.encode("utf-8"))
            try:
                os.fsync(fd)
            except OSError:
                pass
        except OSError as exc:
            raise RunLockError(f"ロック情報の書き込みに失敗: {exc}") from exc

    # ----------------------------------------------------------- context

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


__all__ = [
    "RunLock",
    "RunLockError",
    "LOCK_FILENAME",
    "HEARTBEAT_INTERVAL_SECONDS",
    "STALE_TIMEOUT_SECONDS",
]
