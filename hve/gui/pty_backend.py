"""hve.gui.pty_backend — PTY (擬似ターミナル) 抽象レイヤ。

Plugin / MCP Server のインタラクティブ認証（例: `az login` のサブスクリプション
選択、`copilot login` の Device Flow、`gh auth login`）を GUI 内で完走させる
ために、OS ごとに異なる PTY 実装を共通インターフェース `PtySession` で覆う。

設計方針:
    - Windows: ``pywinpty`` (ConPTY) を使用。Win10 1809+ で動作。
    - POSIX:  ``ptyprocess`` を使用 (`pexpect` の下位ライブラリで実績豊富)。
    - 両ライブラリは任意依存 (``[project.optional-dependencies] gui-pty``)。
      未インストール時は :func:`is_pty_available` が ``False`` を返し、
      呼び出し側でフォールバック処理 (疎通確認のみ等) を行う。
    - :class:`PtySession` の API は ``bytes`` ベースで統一する。文字列の
      エンコード判断は呼び出し側の責務 (xterm.js 連携ではバイナリのまま渡す)。

セキュリティ:
    - ``argv`` は常にリスト渡し (shell 経由ではない)。``shell=True`` 相当は提供しない。
    - 子プロセス kill 時は SIGTERM → 一定時間後 SIGKILL の順で確実に終了させる。
    - サブプロセス出力には Device Flow コード / トークン等の機密が含まれ得るため、
      本モジュール自体ではログを残さない (ロギングは呼び出し側の責務)。

Public API:
    - :func:`is_pty_available` — 必要な PTY バックエンドがインポート可能か。
    - :class:`PtyBackendError` — 共通例外。
    - :class:`PtySession` — Protocol 互換の抽象クラス。
    - :func:`spawn` — プラットフォームを自動判定して ``PtySession`` を返す。
"""

from __future__ import annotations

import os
import sys
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

__all__ = [
    "PtyBackendError",
    "PtySession",
    "is_pty_available",
    "missing_dependency_hint",
    "spawn",
]


class PtyBackendError(RuntimeError):
    """PTY バックエンド共通例外。"""


def _import_pywinpty():
    """``pywinpty`` パッケージ (実モジュール名は ``winpty``) を import する。"""
    import winpty  # type: ignore[import-not-found]

    return winpty


def _import_ptyprocess():
    """ptyprocess を import し、失敗時は ImportError を投げる。"""
    import ptyprocess  # type: ignore[import-not-found]

    return ptyprocess


def is_pty_available() -> bool:
    """現環境で PTY バックエンドが利用可能かを返す。

    Windows なら ``pywinpty``、POSIX なら ``ptyprocess`` が import 可能で
    あること。本関数自体はサブプロセスを起動しない (副作用なし)。
    """
    if sys.platform.startswith("win"):
        try:
            _import_pywinpty()
        except ImportError:
            return False
        return True
    try:
        _import_ptyprocess()
    except ImportError:
        return False
    return True


def missing_dependency_hint() -> str:
    """未インストール時にユーザーへ案内する文字列を返す。"""
    pkg = "pywinpty" if sys.platform.startswith("win") else "ptyprocess"
    return (
        f"PTY バックエンド '{pkg}' が見つかりません。"
        "インストール: pip install -e .[gui,gui-pty]"
    )


# ---------------------------------------------------------------------------
# 抽象基底クラス
# ---------------------------------------------------------------------------


class PtySession(ABC):
    """OS 別 PTY 実装の共通インターフェース。

    全メソッドは非同期ではない (Qt 側で ``QTimer`` ポーリングや
    ``QSocketNotifier`` と組み合わせて使う想定)。
    """

    @abstractmethod
    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        """利用可能な分を読み出す。データが無ければ ``b""`` を返す。

        実装上の注意 (レビュー No.4):
            - POSIX 実装 (``ptyprocess``) は ``select`` ベースで真の非ブロッキング。
            - Windows 実装 (``pywinpty``) は内部 ``read()`` が短時間ブロッキング
              (バックエンドの内部タイムアウト依存、概ね 1 秒以下) する場合がある。
              呼び出し側の Qt UI ループは ``QTimer`` ポーリング (20ms) を想定して
              いるため、Windows での出力が長時間来ない区間ではポーリング間隔が
              実質伸びる可能性がある。

        子プロセス終了後に残バッファが空になった場合も ``b""`` が返るため、
        :meth:`is_alive` と組み合わせて EOF を判定する。
        """

    @abstractmethod
    def write(self, data: bytes) -> int:
        """子プロセスの標準入力へバイト列を書き込む。書き込んだバイト数を返す。"""

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """端末サイズを変更する。xterm.js の ResizeObserver から呼ばれる。"""

    @abstractmethod
    def is_alive(self) -> bool:
        """子プロセスが生存しているか。"""

    @abstractmethod
    def exit_code(self) -> Optional[int]:
        """終了済みなら exit code を返す。生存中は ``None``。"""

    @abstractmethod
    def terminate(self) -> None:
        """穏便な終了要求 (SIGTERM 相当)。"""

    @abstractmethod
    def kill(self) -> None:
        """強制終了 (SIGKILL 相当)。"""

    # ------------------------------------------------------------
    # 便利ヘルパ (サブクラス共通)
    # ------------------------------------------------------------
    def close(self, *, grace_seconds: float = 2.0) -> Optional[int]:
        """``terminate`` → 一定時間待機 → ``kill`` の順で確実に終了させる。

        Returns:
            最終的な exit code。タイムアウト後も取れない場合は ``None``。
        """
        if not self.is_alive():
            return self.exit_code()
        try:
            self.terminate()
        except Exception:
            pass
        deadline = time.monotonic() + max(0.0, grace_seconds)
        while time.monotonic() < deadline:
            if not self.is_alive():
                return self.exit_code()
            time.sleep(0.05)
        try:
            self.kill()
        except Exception:
            pass
        return self.exit_code()


# ---------------------------------------------------------------------------
# Windows (ConPTY via pywinpty)
# ---------------------------------------------------------------------------


class _WindowsPtySession(PtySession):
    """``pywinpty`` (ConPTY) ベースの PTY セッション。"""

    def __init__(
        self,
        argv: List[str],
        *,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
        cols: int,
        rows: int,
    ) -> None:
        pywinpty = _import_pywinpty()
        # pywinpty 2.x/3.x の API: winpty.PtyProcess.spawn(argv, ..., dimensions=(rows, cols))
        try:
            self._proc = pywinpty.PtyProcess.spawn(
                argv,
                cwd=cwd,
                env=env,
                dimensions=(rows, cols),
            )
        except Exception as exc:
            raise PtyBackendError(f"pywinpty spawn failed: {exc}") from exc

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        try:
            # pywinpty の read() はブロッキング寄り。非ブロッキング読み出しは
            # `read(size, blocking=False)` 形式が無いため、isalive + 短いタイムアウト相当の
            # 読み出しに頼る。ここでは ``read`` を呼んで EOF/空文字を許容する。
            data = self._proc.read(max_bytes)
        except EOFError:
            return b""
        except Exception:
            return b""
        if data is None:
            return b""
        if isinstance(data, str):
            return data.encode("utf-8", errors="replace")
        return bytes(data)

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        try:
            # pywinpty.write は str を要求する版があるため両対応。
            n = self._proc.write(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            raise PtyBackendError(f"pywinpty write failed: {exc}") from exc
        if isinstance(n, int):
            return n
        return len(data)

    def resize(self, cols: int, rows: int) -> None:
        try:
            self._proc.setwinsize(rows, cols)
        except Exception:
            # サイズ変更の失敗は致命的でない (画面崩れのみ)
            pass

    def is_alive(self) -> bool:
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def exit_code(self) -> Optional[int]:
        try:
            return self._proc.exitstatus
        except Exception:
            return None

    def terminate(self) -> None:
        try:
            self._proc.terminate(force=False)
        except Exception:
            pass

    def kill(self) -> None:
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# POSIX (ptyprocess)
# ---------------------------------------------------------------------------


class _PosixPtySession(PtySession):
    """``ptyprocess`` ベースの PTY セッション。"""

    def __init__(
        self,
        argv: List[str],
        *,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
        cols: int,
        rows: int,
    ) -> None:
        ptyprocess = _import_ptyprocess()
        try:
            self._proc = ptyprocess.PtyProcess.spawn(
                argv,
                cwd=cwd,
                env=env,
                dimensions=(rows, cols),
            )
        except Exception as exc:
            raise PtyBackendError(f"ptyprocess spawn failed: {exc}") from exc

    def read_nowait(self, max_bytes: int = 4096) -> bytes:
        # ptyprocess は非ブロッキング select でデータ有無を判定可能。
        import select

        try:
            fd = self._proc.fd
        except AttributeError:
            return b""
        try:
            r, _, _ = select.select([fd], [], [], 0)
        except (OSError, ValueError):
            return b""
        if not r:
            return b""
        try:
            return os.read(fd, max_bytes)
        except (OSError, EOFError):
            return b""

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        try:
            return self._proc.write(data)
        except Exception as exc:
            raise PtyBackendError(f"ptyprocess write failed: {exc}") from exc

    def resize(self, cols: int, rows: int) -> None:
        try:
            self._proc.setwinsize(rows, cols)
        except Exception:
            pass

    def is_alive(self) -> bool:
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def exit_code(self) -> Optional[int]:
        try:
            return self._proc.exitstatus
        except Exception:
            return None

    def terminate(self) -> None:
        try:
            self._proc.terminate(force=False)
        except Exception:
            pass

    def kill(self) -> None:
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def spawn(
    argv: List[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    dimensions: Tuple[int, int] = (80, 24),
) -> PtySession:
    """プラットフォームを自動判定して :class:`PtySession` を起動する。

    Args:
        argv: 子プロセス引数リスト (リスト形式必須、shell 経由ではない)。
        cwd: 作業ディレクトリ。
        env: 環境変数辞書。``None`` なら現プロセスの環境を継承する OS 既定挙動。
        dimensions: ``(cols, rows)``。

    Raises:
        PtyBackendError: バックエンド不在または spawn 失敗。
    """
    if not argv:
        raise PtyBackendError("argv must be non-empty")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise PtyBackendError("argv must be a list[str]")

    cols, rows = dimensions
    cols = max(int(cols), 10)
    rows = max(int(rows), 5)

    if not is_pty_available():
        raise PtyBackendError(missing_dependency_hint())

    if sys.platform.startswith("win"):
        return _WindowsPtySession(argv, cwd=cwd, env=env, cols=cols, rows=rows)
    return _PosixPtySession(argv, cwd=cwd, env=env, cols=cols, rows=rows)
