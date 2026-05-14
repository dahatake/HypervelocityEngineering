"""buffer.py — Workbench 用 RingBuffer（list ベース、無制限モード対応）。

固定容量 / 無制限のいずれかで履歴行を保持し、ビューポート（window+offset）で
固定行数を返す。短い場合は空文字列でパディングし Body 高厳守を保証する。

無制限モード（capacity=None / 負値）では list が線形に増えるため、
`HVE_WORKBENCH_BODY_WARN_LINES`（既定 100,000 行）を超えると stderr に
1 度だけ警告を出力する（テスト容易性のため引数 `warn_threshold` で上書き可）。
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional


def _resolve_default_warn_threshold() -> int:
    raw = os.environ.get("HVE_WORKBENCH_BODY_WARN_LINES", "").strip()
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return 100_000


class RingBuffer:
    """append-only / amortized O(1) push の履歴バッファ（list ベース）。

    - `capacity=None` または `capacity<0` で **無制限モード**。
    - 要素はプレーン文字列（ANSI シーケンス含可）。描画側で必要なら
      Rich `Text.from_ansi` で変換する。
    """

    def __init__(
        self,
        capacity: Optional[int] = 10000,
        *,
        warn_threshold: Optional[int] = None,
    ) -> None:
        if capacity is not None and capacity == 0:
            raise ValueError("capacity must be >= 1 or None for unlimited")
        # 負値は無制限扱い
        if capacity is not None and capacity < 0:
            capacity = None
        self._capacity: Optional[int] = capacity
        self._buf: List[str] = []
        self._warn_threshold: int = (
            warn_threshold if warn_threshold is not None else _resolve_default_warn_threshold()
        )
        self._warned: bool = False

    @property
    def capacity(self) -> Optional[int]:
        return self._capacity

    def __len__(self) -> int:
        return len(self._buf)

    def append(self, line: str) -> None:
        """1 行追加する。改行を含む場合は分割して複数行として追加する。"""
        if "\n" in line:
            for part in line.split("\n"):
                self._append_single(part)
        else:
            self._append_single(line)

    def _append_single(self, line: str) -> None:
        self._buf.append(line)
        if self._capacity is not None:
            overflow = len(self._buf) - self._capacity
            if overflow > 0:
                del self._buf[:overflow]
        else:
            if not self._warned and len(self._buf) > self._warn_threshold:
                self._warned = True
                try:
                    print(
                        f"[hve.workbench] WARN: body buffer exceeded "
                        f"{self._warn_threshold} lines (unlimited mode). "
                        f"Memory usage may grow linearly.",
                        file=sys.stderr,
                        flush=True,
                    )
                except Exception:
                    pass

    def view(self, window: int, offset: int = 0) -> List[str]:
        """末尾から `offset` 行戻った位置を最下行とする `window` 行を返す。

        - `offset=0`: 末尾追従（最新 `window` 行）
        - `offset>0`: 過去スクロール
        - 不足分は末尾を空文字列でパディングし、必ず長さ `window` のリストを返す
        - 内部 list の直接スライスで O(window) コピーを保証する
        """
        if window < 0:
            raise ValueError("window must be >= 0")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if window == 0:
            return []

        size = len(self._buf)
        end = max(0, size - offset)
        start = max(0, end - window)
        snapshot = self._buf[start:end]
        if len(snapshot) < window:
            snapshot = snapshot + [""] * (window - len(snapshot))
        return snapshot

    def max_offset(self, window: int) -> int:
        """指定 window で許容される最大 offset（先頭まで戻った状態）。"""
        return max(0, len(self._buf) - window)

    def clear(self) -> None:
        self._buf.clear()
        self._warned = False
