"""hve.gui.job_interaction_model — Copilot パネルへ公開するジョブ対話の値オブジェクト。

FR-GUI-13。`WorkbenchPage` が内部状態を露出せずに宛先を渡すための不変データ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["JobTarget"]


@dataclass(frozen=True)
class JobTarget:
    """対話送信または結果参照の対象となるジョブ。

    Attributes:
        instance_id: `WorkbenchState.workflows` のキー（並列時は ``<workflow>#<app>``）。
        workflow_id: ワークフロー定義 ID。
        label: 画面表示名。
        step_id: 実行中ステップ ID。``None`` はジョブ全体（完了後の参照用）。
        step_title: ステップ表示名。
        status: ``running`` / ``done`` / ``failed`` / ``skipped`` / ``blocked``。
        channel_dir: 当該 instance の IPC チャネル（未登録なら ``None``）。
        returncode: ジョブ終了コード（未終了なら ``None``）。
    """

    instance_id: str
    workflow_id: str
    label: str
    step_id: Optional[str]
    step_title: str
    status: str
    channel_dir: Optional[str]
    returncode: Optional[int] = None

    def is_sendable(self) -> bool:
        """実行中ステップかつ IPC チャネルが利用可能なときだけ送信できる。"""
        return bool(self.step_id) and self.status == "running" and bool(self.channel_dir)

    def display_name(self) -> str:
        if self.step_id is None:
            return self.label
        title = f" {self.step_title}" if self.step_title else ""
        return f"{self.label} / {self.step_id}{title}"
