"""T1.4: run_journal.read_mdq_usage_records / KIND_MDQ_* 定数のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hve import run_journal


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_kind_constants_defined() -> None:
    assert run_journal.KIND_MDQ_SEARCH == "mdq.search"
    assert run_journal.KIND_MDQ_GET == "mdq.get"
    assert run_journal.KIND_MDQ_INDEX == "mdq.index"
    assert run_journal.KIND_MDQ_LIST == "mdq.list"
    assert run_journal.KIND_MDQ_STATS == "mdq.stats"
    assert run_journal.KIND_MDQ_WATCH == "mdq.watch"
    assert run_journal.MDQ_USAGE_LOG_RELATIVE == ".mdq/usage.jsonl"


def test_read_returns_empty_when_file_missing(tmp_path: Path) -> None:
    result = run_journal.read_mdq_usage_records(tmp_path)
    assert result == []


def test_read_returns_all_records(tmp_path: Path) -> None:
    log_path = tmp_path / ".mdq" / "usage.jsonl"
    _write_jsonl(log_path, [
        {"ts": "2026-05-01T00:00:00+00:00", "command": "search", "result": {}},
        {"ts": "2026-05-02T00:00:00+00:00", "command": "get", "result": {}},
    ])
    result = run_journal.read_mdq_usage_records(tmp_path)
    assert len(result) == 2
    assert result[0]["command"] == "search"
    assert result[1]["command"] == "get"


def test_read_filters_by_run_id(tmp_path: Path) -> None:
    log_path = tmp_path / ".mdq" / "usage.jsonl"
    _write_jsonl(log_path, [
        {"ts": "t1", "command": "search", "context": {"run_id": "r1"}},
        {"ts": "t2", "command": "search", "context": {"run_id": "r2"}},
        {"ts": "t3", "command": "get", "context": {"run_id": "r1"}},
        {"ts": "t4", "command": "stats"},  # context 無し
    ])
    result = run_journal.read_mdq_usage_records(tmp_path, run_id="r1")
    assert len(result) == 2
    assert all(r["context"]["run_id"] == "r1" for r in result)


def test_read_filters_by_workflow_id(tmp_path: Path) -> None:
    log_path = tmp_path / ".mdq" / "usage.jsonl"
    _write_jsonl(log_path, [
        {"ts": "t1", "command": "search", "context": {"workflow_id": "aad-web"}},
        {"ts": "t2", "command": "search", "context": {"workflow_id": "adfd"}},
    ])
    result = run_journal.read_mdq_usage_records(tmp_path, workflow_id="aad-web")
    assert len(result) == 1
    assert result[0]["context"]["workflow_id"] == "aad-web"


def test_read_filters_by_since_iso(tmp_path: Path) -> None:
    log_path = tmp_path / ".mdq" / "usage.jsonl"
    _write_jsonl(log_path, [
        {"ts": "2026-05-01T00:00:00+00:00", "command": "search"},
        {"ts": "2026-05-10T00:00:00+00:00", "command": "search"},
        {"ts": "2026-05-15T00:00:00+00:00", "command": "search"},
    ])
    result = run_journal.read_mdq_usage_records(
        tmp_path, since_iso="2026-05-10T00:00:00+00:00"
    )
    assert len(result) == 2


def test_read_skips_malformed_lines(tmp_path: Path) -> None:
    log_path = tmp_path / ".mdq" / "usage.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"ts":"t1","command":"search"}\n'
        "not-a-json-line\n"
        '{"ts":"t2","command":"get"}\n'
        '"a-string-not-a-dict"\n',
        encoding="utf-8",
    )
    result = run_journal.read_mdq_usage_records(tmp_path)
    assert len(result) == 2
    assert result[0]["command"] == "search"
    assert result[1]["command"] == "get"
