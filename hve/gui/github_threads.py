"""hve.gui.github_threads — GitHub API 呼び出しを GUI スレッド外で実行するワーカー。

FR-GUI-26 / FR-GUI-27 は GitHub API 呼び出しを GUI スレッドで行うことを禁じる。
本モジュールは `hve.gui.github_service` の関数呼び出しを 1 つの QThread へ載せ、
既存ワーカーと同じ `succeeded` / `failed` シグナル形状で結果を返す。
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Set

from PySide6.QtCore import QObject, QThread, Signal

from .github_service import GitHubServiceError

__all__ = ["GitHubWorker"]

# 実行中のワーカーへのモジュールレベル参照。
# 呼び出し側ウィジェットが破棄・GC されても、実行中の QThread が解放されて
# "QThread: Destroyed while thread is still running" でプロセスが異常終了するのを防ぐ。
_ACTIVE: Set["GitHubWorker"] = set()


class GitHubWorker(QThread):
    """`github_service` の呼び出しを 1 回実行して結果を通知するワーカー。

    Args:
        task: 引数なしで呼び出せる `github_service` 呼び出し（`functools.partial` 等）。
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[], Any], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._task = task
        self.finished.connect(self._unregister)

    def start(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        _ACTIVE.add(self)
        super().start(*args, **kwargs)

    def _unregister(self) -> None:
        _ACTIVE.discard(self)

    def run(self) -> None:  # type: ignore[override]
        try:
            result = self._task()
        except GitHubServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - ワーカースレッドの例外を UI へ伝える
            self.failed.emit(f"予期しないエラーが発生しました: {type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(result)
