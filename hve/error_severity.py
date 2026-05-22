"""エラーの致命度分類モジュール。

`local` 実行モード（CLI / GUI）における continue-on-precheck 戦略で使用する。
致命的（fatal）エラーのみがワークフロー実行を中断させ、それ以外（recoverable）
は呼び出し側で個別に判断する。

設計方針:
  - **fatal**: ワークフローを継続できない物理的・論理的不可能性
    - `KeyboardInterrupt` / `SystemExit`: ユーザー明示中断
    - `OSError` のうち回復不能なもの（ENOSPC, EIO, EROFS 等）
    - `FileNotFoundError`: workflow yaml 等の必須リソース欠落
    - `PermissionError`: アクセス拒否
  - **recoverable**: 個別 step の失敗扱いとして処理可能なもの
    - `RuntimeError` / `ValueError` / `TypeError` 等の汎用例外
    - `asyncio.TimeoutError` / `ConnectionError` 等の一時的障害

判定は呼び出し側の意図を変えないよう、純粋関数として実装する。
"""

from __future__ import annotations

import asyncio
import errno
from typing import Literal

Severity = Literal["fatal", "recoverable"]

# OSError.errno が以下の値の場合は fatal 扱い（回復不能と判断）。
_FATAL_OSERROR_ERRNOS = frozenset(
    {
        errno.ENOSPC,  # No space left on device
        errno.EIO,     # I/O error
        errno.EROFS,   # Read-only file system
        errno.ENOMEM,  # Out of memory
    }
)


def classify_error(exc: BaseException) -> Severity:
    """例外を fatal / recoverable に分類する。

    Args:
        exc: 分類対象の例外。

    Returns:
        "fatal" または "recoverable"。
    """
    # ① 明示中断系は最優先で fatal
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return "fatal"

    # ② FileNotFoundError / PermissionError は OSError のサブクラスだが
    #    意味的に常に fatal（必須リソース欠落・権限不足）。
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return "fatal"

    # ③ ConnectionError は OSError のサブクラスだが、一時的障害として recoverable。
    if isinstance(exc, ConnectionError):
        return "recoverable"

    # ④ asyncio.TimeoutError は一時的障害として recoverable。
    #    Python 3.11+ では `asyncio.TimeoutError` は `TimeoutError` のエイリアス。
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "recoverable"

    # ⑤ その他の OSError は errno で判定。
    if isinstance(exc, OSError):
        if exc.errno in _FATAL_OSERROR_ERRNOS:
            return "fatal"
        return "recoverable"

    # ⑥ 残りは recoverable（RuntimeError / ValueError / TypeError 等）。
    return "recoverable"


def is_fatal(exc: BaseException) -> bool:
    """`classify_error(exc) == "fatal"` のショートカット。"""
    return classify_error(exc) == "fatal"
