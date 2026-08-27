"""FR-CLI-87: Wave 境界の承認ゲート（CLI 同期）。

`on_wave_start` フックから呼ばれ、拒否と非対話を ``ApprovalDeclined`` で伝える。
DAG 実行側は同例外だけを握り潰さずに伝播させる。
"""

from __future__ import annotations

import sys
from typing import Any, Iterable, Optional


class ApprovalDeclined(Exception):
    """承認が得られなかった（拒否、または非対話で確認できなかった）。"""

    def __init__(self, message: str, *, wave_index: Optional[int] = None) -> None:
        super().__init__(message)
        # FR-CLI-87: 拒否も `approval:<wave_index>` で記録するため、例外が wave を搬送する。
        self.wave_index = wave_index


def _step_ids(steps: Iterable[Any]) -> list:
    ids = []
    for step in steps:
        step_id = getattr(step, "id", None) or getattr(step, "step_id", None)
        if step_id:
            ids.append(str(step_id))
    return ids


def wave_requires_approval(steps: Iterable[Any]) -> bool:
    """Wave に `approval_gate` を宣言した Step が含まれるか。"""
    return any(bool(getattr(step, "approval_gate", False)) for step in steps)


def request_wave_approval(
    steps: Iterable[Any],
    wave_index: int,
    *,
    interactive: bool,
    console: Optional[Any] = None,
    input_fn: Any = input,
) -> None:
    """承認を求める。得られない場合は ``ApprovalDeclined`` を送出する。"""
    ids = _step_ids(steps)
    label = ", ".join(ids) if ids else f"wave {wave_index}"

    if not interactive:
        raise ApprovalDeclined(
            f"承認ゲート（wave {wave_index}: {label}）を確認できません。"
            " 標準入力が対話可能ではないため停止しました。",
            wave_index=wave_index,
        )

    if console is not None:
        console.event(f"承認ゲート: wave {wave_index} の実行前確認が必要です（{label}）")
    try:
        answer = input_fn(f"wave {wave_index} を実行しますか？ [y/N]: ")
    except (EOFError, KeyboardInterrupt) as exc:
        raise ApprovalDeclined(
            f"承認ゲート（wave {wave_index}: {label}）の入力が中断されました。",
            wave_index=wave_index,
        ) from exc

    if str(answer).strip().lower() not in ("y", "yes"):
        raise ApprovalDeclined(
            f"承認ゲート（wave {wave_index}: {label}）が承認されませんでした。",
            wave_index=wave_index,
        )


def stdin_is_interactive() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False
