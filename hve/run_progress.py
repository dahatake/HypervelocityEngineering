"""FR-CLI-86: Legacy Workflow進捗の明示的なrun/workflowスコープ読取。

新しいdurable executionの列挙・importには使用しない。`--resume-run`で利用者が
明示した既存JSONLだけを読み、同じrun IDでも別WorkflowのStepを混在させない。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

SCHEMA_VERSION = 1
DEFAULT_PROGRESS_PATH = Path(__file__).resolve().parent / ".run-progress.jsonl"

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

_PathLike = Union[str, Path, None]


def _resolve(path: _PathLike) -> Path:
    return DEFAULT_PROGRESS_PATH if path is None else Path(path)


def record_step(
    run_id: str,
    workflow_id: str,
    step_id: str,
    status: str,
    *,
    path: _PathLike = None,
) -> None:
    """1 Step の完了状態を追記する。書き込み失敗で run を止めない（FR-STATE-04）。"""
    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "workflow_id": workflow_id,
        "step_id": step_id,
        "status": status,
    }
    try:
        with open(_resolve(path), "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return


def completed_steps(
    run_id: str,
    workflow_id: str,
    *,
    path: _PathLike = None,
) -> Optional[frozenset[str]]:
    """当該legacy run/Workflowで成功したStep集合。記録なしは``None``。"""
    try:
        raw = _resolve(path).read_text(encoding="utf-8")
    except OSError:
        return None

    found = False
    succeeded: set[str] = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if (
            not isinstance(record, dict)
            or record.get("run_id") != run_id
            or record.get("workflow_id") != workflow_id
        ):
            continue
        found = True
        step_id = record.get("step_id")
        if record.get("status") == STATUS_SUCCEEDED and isinstance(step_id, str):
            succeeded.add(step_id)
    return frozenset(succeeded) if found else None
