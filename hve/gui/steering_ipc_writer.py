"""hve.gui.steering_ipc_writer — Steering（実行中ワークフローへの割り込み送信）用
IPC リクエストファイルを書き込む後方互換ヘルパー。

スキーマ・ファイル名規約・アトミック書き込みの実装は
[hve/job_interaction_ipc.py](../job_interaction_ipc.py) に単一化されている
（FR-GUI-12 / FR-MAINT-07）。本モジュールは既存呼び出し元のための薄い委譲。
"""

from __future__ import annotations

from pathlib import Path

from hve.job_interaction_ipc import ACTION_STEER, write_request

__all__ = ["write_steering_request"]


def write_steering_request(ipc_dir: Path, step_id: str, text: str) -> Path:
    """Steering 割り込みリクエストを IPC ディレクトリへアトミックに書き込む。

    Args:
        ipc_dir: IPC ディレクトリ（存在しなければ作成する）。
        step_id: 対象ステップ識別子。`_poll_steering_ipc` 側と同一のサニタイズ
            規則でファイル名に組み込まれる。
        text: 割り込みメッセージ本文。

    Returns:
        書き込んだファイルの絶対パス。

    Raises:
        OSError: ディレクトリ作成またはファイル書き込みに失敗した場合。
    """
    return write_request(ipc_dir, step_id, text, action=ACTION_STEER)
