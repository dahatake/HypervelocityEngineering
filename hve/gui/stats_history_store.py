"""hve.gui.stats_history_store — Step 2 統計履歴の永続化ストア。

Workflow / Step スナップショットを ``session-state/runs/<run_id>/stats-history.json``
に逐次書き出す。書式は ``{"schema_version": 1, "workflows": [...]}``。

- Step 完了時: 対象 Workflow エントリの ``steps`` に追記
- Workflow 完了時 (``finalized=True``): 対象 Workflow エントリの全フィールドを更新
- 書き込みは atomic（temp → os.replace）。失敗時は WARN ログのみで例外を握りつぶす

捏造防止: SDK 未取得値は WorkbenchState 側で None のまま渡されるので JSON null として保存する。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from hve.gui.workbench_state import StepStatsSnapshot, WorkflowStatsSnapshot

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FILENAME = "stats-history.json"


class StatsHistoryStore:
    """``session-state/runs/<run_id>/stats-history.json`` への永続化。"""

    def __init__(self, runs_dir: Path) -> None:
        """`runs_dir` は ``session-state/runs`` ルート。``run_id`` サブディレクトリは
        ``save_*`` 時に必要に応じて作成する。
        """
        self._runs_dir = Path(runs_dir)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def save_step_snapshot(
        self, workflow: WorkflowStatsSnapshot, step: StepStatsSnapshot
    ) -> None:
        """Step 完了スナップショットを永続化する。"""
        try:
            self._write_workflow(workflow)
        except Exception as e:  # 書き込み失敗時に GUI を落とさない
            logger.warning("stats_history_store.save_step_snapshot failed: %s", e)

    def save_workflow_snapshot(self, workflow: WorkflowStatsSnapshot) -> None:
        """Workflow 完了スナップショットを永続化する。"""
        try:
            self._write_workflow(workflow)
        except Exception as e:
            logger.warning("stats_history_store.save_workflow_snapshot failed: %s", e)

    def file_path(self, run_id: str) -> Path:
        """対象 run_id の永続化ファイルパスを返す。"""
        return self._runs_dir / run_id / FILENAME

    # ------------------------------------------------------------------
    # 内部実装
    # ------------------------------------------------------------------

    def _write_workflow(self, workflow: WorkflowStatsSnapshot) -> None:
        run_id = workflow.run_id or "unknown"
        path = self.file_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = self._read_existing(path)
        workflows = data.setdefault("workflows", [])

        # workflow_id + run_id をキーとして upsert
        idx = self._find_workflow_index(workflows, workflow.workflow_id, workflow.run_id)
        wd = workflow.to_dict()
        if idx is None:
            workflows.append(wd)
        else:
            workflows[idx] = wd

        data["schema_version"] = SCHEMA_VERSION
        self._atomic_write(path, data)

    @staticmethod
    def _read_existing(path: Path) -> dict:
        if not path.exists():
            return {"schema_version": SCHEMA_VERSION, "workflows": []}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"schema_version": SCHEMA_VERSION, "workflows": []}
            data.setdefault("workflows", [])
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("stats-history.json read failed (%s); recreating", e)
            return {"schema_version": SCHEMA_VERSION, "workflows": []}

    @staticmethod
    def _find_workflow_index(
        workflows: list, workflow_id: str, run_id: str
    ) -> Optional[int]:
        for i, w in enumerate(workflows):
            if w.get("workflow_id") == workflow_id and w.get("run_id") == run_id:
                return i
        return None

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        # 同一ディレクトリ内 tempfile → os.replace
        fd, tmp_path = tempfile.mkstemp(
            prefix=".stats-history-", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
