"""hve.gui.steering_ipc_writer — Steering（実行中ワークフローへの割り込み送信）用
IPC リクエストファイルを書き込む薄いヘルパー。

`hve/runner.py` の `_poll_steering_ipc()` が polling するファイル名パターン
（``steering-<safe_step_id>-<epoch_ms>.request.json``）に合わせて書き込む。
ファイル名サニタイズは `_poll_steering_ipc()` 側と同一の正規表現
（``[^A-Za-z0-9_.-]`` を ``-`` に置換）を用いて、両者のファイル名解決を一致させる。

書き込みは tmp ファイル + ``os.replace`` によるアトミック書き込み（既存
`hve/runner.py` `_collect_qa_answers_via_ipc` の `_atomic_write` と同一パターン）。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

__all__ = ["write_steering_request"]


def write_steering_request(ipc_dir: Path, step_id: str, text: str) -> Path:
    """Steering 割り込みリクエストを IPC ディレクトリへアトミックに書き込む。

    Args:
        ipc_dir: IPC ディレクトリ（存在しなければ作成する）。
        step_id: 対象ステップ識別子。`hve/runner.py::_poll_steering_ipc` 側と
            同一のサニタイズ規則でファイル名に組み込まれる。
        text: 割り込みメッセージ本文。

    Returns:
        書き込んだファイルの絶対パス。

    Raises:
        OSError: ディレクトリ作成またはファイル書き込みに失敗した場合。
    """
    ipc_dir = Path(ipc_dir)
    ipc_dir.mkdir(parents=True, exist_ok=True)
    safe_step_id = re.sub(r"[^A-Za-z0-9_.-]", "-", str(step_id))
    epoch_ms = int(time.time() * 1000)
    path = ipc_dir / f"steering-{safe_step_id}-{epoch_ms}.request.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
