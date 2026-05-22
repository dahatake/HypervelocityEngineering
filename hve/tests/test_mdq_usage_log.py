"""T1.2: mdq.usage_log と CLI 統合の単体テスト。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mdq import cli as mdq_cli
from mdq import usage_log


# ---------------------------------------------------------------------------
# usage_log モジュール単体
# ---------------------------------------------------------------------------

def test_append_record_writes_jsonl(tmp_path: Path) -> None:
    out = usage_log.append_record(
        command="search",
        args={"q": "test", "top_k": 5},
        elapsed_ms=12,
        result={"hit_count": 3, "snippet_chars": 100, "source_file_chars": 1000},
        exit_code=0,
        repo_root=tmp_path,
    )
    assert out is not None
    assert out == (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["command"] == "search"
    assert rec["args"]["q"] == "test"
    assert rec["elapsed_ms"] == 12
    assert rec["result"]["hit_count"] == 3
    assert rec["exit_code"] == 0
    assert "ts" in rec


def test_append_record_appends_multiple(tmp_path: Path) -> None:
    for i in range(3):
        usage_log.append_record(
            command="get",
            args={"chunk_id": f"id-{i}"},
            elapsed_ms=i,
            result={"found": True, "body_chars": 10 * i},
            exit_code=0,
            repo_root=tmp_path,
        )
    path = (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for i, ln in enumerate(lines):
        rec = json.loads(ln)
        assert rec["args"]["chunk_id"] == f"id-{i}"


def test_context_env_vars_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HVE_RUN_ID", "run-42")
    monkeypatch.setenv("HVE_WORKFLOW_ID", "aad-web")
    monkeypatch.setenv("HVE_STEP_ID", "step-2.1")
    # HVE_AGENT_ID は未設定 → 出力に含まれないこと
    monkeypatch.delenv("HVE_AGENT_ID", raising=False)
    usage_log.append_record(
        command="search",
        args={"q": "x"},
        elapsed_ms=1,
        result={"hit_count": 0, "snippet_chars": 0, "source_file_chars": 0},
        exit_code=0,
        repo_root=tmp_path,
    )
    path = (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["context"]["run_id"] == "run-42"
    assert rec["context"]["workflow_id"] == "aad-web"
    assert rec["context"]["step_id"] == "step-2.1"
    assert "agent_id" not in rec["context"]


def test_context_omitted_when_no_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("HVE_RUN_ID", "HVE_WORKFLOW_ID", "HVE_STEP_ID", "HVE_AGENT_ID"):
        monkeypatch.delenv(v, raising=False)
    usage_log.append_record(
        command="stats",
        args={},
        elapsed_ms=0,
        result={"files": 1, "chunks": 1},
        exit_code=0,
        repo_root=tmp_path,
    )
    path = (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert "context" not in rec


def test_append_record_swallows_write_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """書き込み失敗は呼び出し元に伝播させない（観測用ログの原則）。"""
    def _boom(*a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", _boom, raising=True)
    result = usage_log.append_record(
        command="search",
        args={"q": "x"},
        elapsed_ms=1,
        result={"hit_count": 0, "snippet_chars": 0, "source_file_chars": 0},
        exit_code=0,
        repo_root=tmp_path,
    )
    assert result is None


# ---------------------------------------------------------------------------
# CLI 統合: stats サブコマンド経由でレコードが書かれるか
# ---------------------------------------------------------------------------

def test_cmd_stats_writes_usage_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    # mdq stats を実行
    rc = mdq_cli.main(["stats"])
    assert rc == 0
    capsys.readouterr()  # stdout は捨てる

    log_path = (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    assert log_path.exists()
    rec = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["command"] == "stats"
    assert rec["exit_code"] == 0
    assert rec["result"]["files"] >= 0
    assert rec["result"]["chunks"] >= 0
    assert "elapsed_ms" in rec
