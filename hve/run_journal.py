"""hve/run_journal.py — markdown-query Skill 利用ログの読み取りヘルパー。

mdq CLI が `<repo-root>/.mdq/usage.jsonl` へ追記する単発イベント
（`mdq.search` / `mdq.get` 等）を run_id / workflow_id で紐付けて読み込む。
mdq の利用統計（`mdq/usage_stats.py`）から参照される。

== レコードフォーマット ==

各行は 1 JSON オブジェクト:

```json
{"ts": "2026-05-12T00:00:00+00:00", "kind": "mdq.search",
 "context": {"run_id": "...", "workflow_id": "..."}, ...}
```
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mdq import usage_log as _mdq_usage_log


# markdown-query Skill 利用イベント種別（mdq CLI から ``.mdq/usage.jsonl`` へ
# 追記される単発イベント。識別子をここに集約して命名規約を一元化する）。
KIND_MDQ_SEARCH: str = "mdq.search"
KIND_MDQ_GET: str = "mdq.get"
KIND_MDQ_INDEX: str = "mdq.index"
KIND_MDQ_LIST: str = "mdq.list"
KIND_MDQ_STATS: str = "mdq.stats"
KIND_MDQ_WATCH: str = "mdq.watch"

MDQ_USAGE_LOG_RELATIVE: str = _mdq_usage_log.USAGE_LOG_RELATIVE
"""mdq 利用ログのリポジトリルート相対パス。正本は ``mdq.usage_log``（FR-KIT-05）。"""


def read_mdq_usage_records(
    repo_root: Path,
    *,
    run_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    since_iso: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """``.mdq/usage.jsonl`` のレコードを読み込んで返す。

    実装は書き込み側と同じ :func:`mdq.usage_log.read_records` に単一化されており（FR-KIT-05）、
    本関数は HVE 側の既存 API を維持するための委譲である。
    """
    return _mdq_usage_log.read_records(
        repo_root,
        run_id=run_id,
        workflow_id=workflow_id,
        since_iso=since_iso,
    )


__all__ = [
    "KIND_MDQ_SEARCH",
    "KIND_MDQ_GET",
    "KIND_MDQ_INDEX",
    "KIND_MDQ_LIST",
    "KIND_MDQ_STATS",
    "KIND_MDQ_WATCH",
    "MDQ_USAGE_LOG_RELATIVE",
    "read_mdq_usage_records",
]
