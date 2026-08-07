"""FR-CQ-14: cq.usage_log と CLI 統合の単体テスト。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cq import cli as cq_cli
from cq import config, indexer, usage_log


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "class LedgerService:\n    def grant_points(self, amount):\n        return amount\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite")
    return tmp_path


def _records(repo_root: Path) -> list[dict]:
    path = (repo_root / usage_log.USAGE_LOG_RELATIVE).resolve()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# usage_log モジュール単体
# ---------------------------------------------------------------------------

def test_append_record_writes_jsonl(tmp_path: Path) -> None:
    out = usage_log.append_record(
        command="search",
        args={"q": "grant_points", "top_k": 5},
        elapsed_ms=12,
        result={"hit_count": 3},
        exit_code=0,
        repo_root=tmp_path,
    )
    assert out is not None
    assert out == (tmp_path / usage_log.USAGE_LOG_RELATIVE).resolve()
    rec = _records(tmp_path)[0]
    assert rec["command"] == "search"
    assert rec["args"]["q"] == "grant_points"
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
    assert [r["args"]["chunk_id"] for r in _records(tmp_path)] == ["id-0", "id-1", "id-2"]


def test_context_env_vars_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HVE_RUN_ID", "run-42")
    monkeypatch.setenv("HVE_WORKFLOW_ID", "asdw-web")
    monkeypatch.setenv("HVE_STEP_ID", "step-2.1")
    monkeypatch.delenv("HVE_AGENT_ID", raising=False)
    usage_log.append_record(
        command="search", args={"q": "x"}, elapsed_ms=1,
        result={"hit_count": 0}, exit_code=0, repo_root=tmp_path,
    )
    ctx = _records(tmp_path)[0]["context"]
    assert ctx["run_id"] == "run-42"
    assert ctx["workflow_id"] == "asdw-web"
    assert ctx["step_id"] == "step-2.1"
    assert "agent_id" not in ctx


def test_context_omitted_when_no_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HVE_RUN_ID", "HVE_WORKFLOW_ID", "HVE_STEP_ID", "HVE_AGENT_ID"):
        monkeypatch.delenv(name, raising=False)
    usage_log.append_record(
        command="stats", args={}, elapsed_ms=1,
        result={"files": 0}, exit_code=0, repo_root=tmp_path,
    )
    assert "context" not in _records(tmp_path)[0]


def test_append_record_swallows_write_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """書き込み失敗は呼び出し元に伝播させない（観測用ログの原則）。"""
    def _boom(*a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", _boom, raising=True)
    assert usage_log.append_record(
        command="search", args={"q": "x"}, elapsed_ms=1,
        result={"hit_count": 0}, exit_code=0, repo_root=tmp_path,
    ) is None


def test_usage_log_path_is_separate_from_mdq() -> None:
    """`mdq` の利用ログと同一ファイルへ混在させない（FR-CQ-14）。"""
    from mdq import usage_log as mdq_usage_log

    assert usage_log.USAGE_LOG_RELATIVE == ".cq/usage.jsonl"
    assert usage_log.USAGE_LOG_RELATIVE != mdq_usage_log.USAGE_LOG_RELATIVE


# ---------------------------------------------------------------------------
# CLI 統合
# ---------------------------------------------------------------------------

def test_cmd_stats_writes_usage_log(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cq_cli.main(["stats", "--profile", "test", "--repo-root", str(repo)]) == 0
    capsys.readouterr()
    rec = _records(repo)[0]
    assert rec["command"] == "stats"
    assert rec["exit_code"] == 0
    assert "files" in rec["result"]
    assert "chunks" in rec["result"]
    assert "elapsed_ms" in rec


def test_cmd_search_writes_usage_log(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cq_cli.main([
        "search", "--q", "grant_points", "--profile", "test", "--repo-root", str(repo),
    ]) == 0
    capsys.readouterr()
    rec = _records(repo)[0]
    assert rec["command"] == "search"
    # 記録されるキーは argparse の dest 名（`--q` の dest は `query`）。
    assert rec["args"]["query"] == "grant_points"
    assert rec["result"]["hit_count"] >= 1
    assert rec["exit_code"] == 0


def test_failed_command_is_recorded_with_its_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    assert cq_cli.main([
        "search", "--q", "x", "--profile", "test", "--repo-root", str(tmp_path),
        "--db", str(tmp_path / ".cq" / "absent.sqlite"),
    ]) == 2
    capsys.readouterr()
    rec = _records(tmp_path)[0]
    assert rec["command"] == "search"
    assert rec["exit_code"] == 2
