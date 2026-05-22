"""hve.gui.file_explorer.file_change_tracker — ファイル新規/更新/削除の状態管理。

ファイルツリー上で「最近作成・更新されたファイル」をバッジ表示するための
状態辞書を保持する純粋ロジック層。Qt 依存なし（テスト容易性のため）。

状態:
    - NEW:     直近で新規作成された
    - MODIFIED: 直近で更新された
    - NORMAL:  バッジ表示対象外（fade 完了後の既定状態）

状態遷移ルール（敵対的レビュー #11 反映）:
    - NORMAL + mark_created  → NEW       (fade_at = now + fade_seconds)
    - NORMAL + mark_modified → MODIFIED  (fade_at = now + fade_seconds)
    - NEW    + mark_modified → NEW のまま fade_at だけリセット
    - MODIFIED + mark_created → NEW      (再作成扱いで状態昇格)
    - 任意   + mark_deleted  → エントリ削除

時刻は呼び出し側から ``now`` を渡す（テスト容易性のため time.monotonic に依存しない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Optional

DEFAULT_FADE_SECONDS: float = 5.0


class ChangeState(Enum):
    """ファイル変更状態。"""

    NORMAL = "normal"
    NEW = "new"
    MODIFIED = "modified"


@dataclass(frozen=True)
class _Entry:
    state: ChangeState
    fade_at: float  # 単調時刻（秒）。この時刻を過ぎたら NORMAL に戻す。


class FileChangeTracker:
    """ファイルパスごとの変更状態を管理する。

    Args:
        fade_seconds: NEW / MODIFIED 状態を保持する秒数。
    """

    def __init__(self, fade_seconds: float = DEFAULT_FADE_SECONDS) -> None:
        if fade_seconds <= 0:
            raise ValueError("fade_seconds must be positive")
        self._fade_seconds = float(fade_seconds)
        self._entries: Dict[Path, _Entry] = {}

    # ------------------------------------------------------------------
    # 更新 API
    # ------------------------------------------------------------------

    def mark_created(self, path: Path, *, now: float) -> None:
        """ファイル新規作成を記録する。"""
        self._entries[Path(path)] = _Entry(
            state=ChangeState.NEW,
            fade_at=now + self._fade_seconds,
        )

    def mark_modified(self, path: Path, *, now: float) -> None:
        """ファイル更新を記録する。既存状態が NEW なら NEW のまま fade_at をリセット。"""
        key = Path(path)
        existing = self._entries.get(key)
        if existing is not None and existing.state == ChangeState.NEW:
            # NEW のまま fade_at だけリセット（書き込み中のファイルが多重通知される想定）
            self._entries[key] = _Entry(
                state=ChangeState.NEW,
                fade_at=now + self._fade_seconds,
            )
            return
        self._entries[key] = _Entry(
            state=ChangeState.MODIFIED,
            fade_at=now + self._fade_seconds,
        )

    def mark_deleted(self, path: Path) -> None:
        """ファイル削除を記録する（エントリ即除去）。"""
        self._entries.pop(Path(path), None)

    # ------------------------------------------------------------------
    # 時間経過処理
    # ------------------------------------------------------------------

    def tick(self, *, now: float) -> Iterable[Path]:
        """fade_at を過ぎたエントリを NORMAL に戻す。

        Returns:
            状態が NORMAL に戻った（= 再描画が必要な）パスのイテラブル。
        """
        faded = [p for p, e in self._entries.items() if now >= e.fade_at]
        for p in faded:
            del self._entries[p]
        return faded

    # ------------------------------------------------------------------
    # 参照 API
    # ------------------------------------------------------------------

    def state_of(self, path: Path) -> ChangeState:
        """指定パスの現在状態を返す（エントリ無しは NORMAL）。"""
        e = self._entries.get(Path(path))
        return e.state if e is not None else ChangeState.NORMAL

    def tracked_paths(self) -> Iterable[Path]:
        """現在バッジ表示中のパス一覧。"""
        return list(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)
