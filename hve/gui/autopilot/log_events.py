"""Autopilot ログイベントの型定義と整形ユーティリティ。

Step 2 (実行中) のマスター画面 (AutopilotQueuePage) と各チェーン別ウィンドウ
(ChainLogWindow) で共通利用する。

ログ行の prefix 仕様 (Q5):
  ``[HH:MM:SS] [WORKFLOW_ID:APP_ID] <line>``

- WORKFLOW_ID / APP_ID は大文字化する。
- APP_ID が空（シリアル経路など app_id 概念がない場合）は ``[WORKFLOW_ID:-]``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LogLineEvent:
    """子プロセス stdout の 1 行を表すイベント。

    Attributes:
        app_id: APP 識別子。シリアル経路など app_id が無い場合は空文字列。
        workflow_id: ワークフロー ID（例 ``ard`` / ``aas``）。
        line: 行本体（改行除去済み）。
        ts: 受信時刻のエポック秒。0 のとき送信側で現在時刻を採用。
    """

    app_id: str
    workflow_id: str
    line: str
    ts: float = 0.0


def _fmt_ts(ts: float) -> str:
    if ts <= 0:
        ts = time.time()
    return time.strftime("%H:%M:%S", time.localtime(ts))


def format_prefix(workflow_id: str, app_id: str) -> str:
    """``[WORKFLOW_ID:APP_ID]`` 形式の prefix を返す（大文字化、空は ``-``）。"""
    wf = (workflow_id or "").upper() or "-"
    app = (app_id or "").upper() or "-"
    return f"[{wf}:{app}]"


def format_prefixed_line(event: LogLineEvent) -> str:
    """マスター画面ログ向けの整形済み 1 行を返す。"""
    return f"[{_fmt_ts(event.ts)}] {format_prefix(event.workflow_id, event.app_id)} {event.line}"
