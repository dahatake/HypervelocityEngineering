"""FR-STATE-04: Workflow 進捗の run スコープ保存。

§5.6 が全廃した SDK セッションの復元は行わない。保存するのは「どの Step が
成功したか」という HVE 自身が所有する進捗だけで、再実行時は未完了 Step を
新しいセッションで実行する。
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


def completed_steps(run_id: str, *, path: _PathLike = None) -> Optional[frozenset]:
    """成功した step_id の集合。当該 run の記録が 1 件も無い場合は ``None``。"""
    try:
        raw = _resolve(path).read_text(encoding="utf-8")
    except OSError:
        return None

    found = False
    succeeded: set = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("run_id") != run_id:
            continue
        found = True
        step_id = record.get("step_id")
        if record.get("status") == STATUS_SUCCEEDED and isinstance(step_id, str):
            succeeded.add(step_id)
    return frozenset(succeeded) if found else None
