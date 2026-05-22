"""hve.tests.test_autopilot_cli — `--autopilot-chain` CLI 引数の単体テスト。

Qt 非依存で動作することを保証する（PySide6 を import しない）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from hve.autopilot import AutopilotPlan, AppChain
from hve.autopilot.cli_runner import CliAutopilotRunner, CliRunSummary


class _FakeProc:
    _pid = 9000

    def __init__(self, exit_code: int = 0) -> None:
        _FakeProc._pid += 1
        self.pid = _FakeProc._pid
        self._exit_code = exit_code
        self._polled = False

    def poll(self):
        # 1 回目は None（実行中扱い）、2 回目以降は exit_code
        if not self._polled:
            self._polled = True
            return None
        return self._exit_code

    def terminate(self) -> None:
        pass


def _plan(app_ids: List[str], chain: List[str], max_parallel: int = 4) -> AutopilotPlan:
    return AutopilotPlan(
        catalog_path=Path("docs/catalog/app-arch-catalog.md"),
        catalog_exists=True,
        requires_aas=False,
        app_chains=[
            AppChain(app_id=aid, architecture="Webフロントエンド + クラウド",
                     workflows=list(chain))
            for aid in app_ids
        ],
        max_parallel=max_parallel,
    )


def test_cli_runner_no_apps_returns_zero_total() -> None:
    plan = _plan([], chain=["aad-web"])
    runner = CliAutopilotRunner(plan, poll_interval_sec=0.0)
    summary = runner.run()
    assert isinstance(summary, CliRunSummary)
    assert summary.total_apps == 0
    assert summary.completed_apps == 0
    assert summary.aborted_apps == []
    assert summary.success is True


def test_cli_runner_all_success_chain() -> None:
    plan = _plan(["APP-01", "APP-02"], chain=["aad-web", "asdw-web"], max_parallel=2)
    launched: List[List[str]] = []

    def fake_popen(argv):
        launched.append(list(argv))
        return _FakeProc(exit_code=0)

    runner = CliAutopilotRunner(
        plan,
        popen_factory=fake_popen,
        poll_interval_sec=0.0,
    )
    summary = runner.run()
    assert summary.success
    assert summary.total_apps == 2
    assert summary.completed_apps == 2
    assert summary.aborted_apps == []
    # 各 APP × 2 段 = 4 回起動
    assert len(launched) == 4
    # argv の workflow / app-ids 配置を確認
    workflows = sorted([argv[argv.index("--workflow") + 1] for argv in launched])
    assert workflows == ["aad-web", "aad-web", "asdw-web", "asdw-web"]


def test_cli_runner_abort_propagates_exit_code() -> None:
    plan = _plan(["APP-01"], chain=["aad-web", "asdw-web"])

    call_count = {"n": 0}

    def fake_popen(argv):
        call_count["n"] += 1
        # 1 段目は失敗
        return _FakeProc(exit_code=7 if call_count["n"] == 1 else 0)

    runner = CliAutopilotRunner(plan, popen_factory=fake_popen, poll_interval_sec=0.0)
    summary = runner.run()
    assert not summary.success
    assert summary.aborted_apps == ["APP-01"]
    assert summary.aborted_codes == {"APP-01": 7}
    # 1 段目で abort したので 2 段目（asdw-web）は起動されない
    assert call_count["n"] == 1


def test_cli_runner_argv_factory_override() -> None:
    plan = _plan(["APP-X"], chain=["aad-web"])
    captured: List = []

    def argv_factory(app_id, wf_id):
        captured.append((app_id, wf_id))
        return ["custom", "--app", app_id, "--wf", wf_id]

    runner = CliAutopilotRunner(
        plan,
        argv_factory=argv_factory,
        popen_factory=lambda argv: _FakeProc(exit_code=0),
        poll_interval_sec=0.0,
    )
    summary = runner.run()
    assert summary.success
    assert captured == [("APP-X", "aad-web")]


# --- CLI 引数統合（実プロセス起動）-----------------------------------------


def test_cli_autopilot_dry_run_exits_zero(tmp_path: Path) -> None:
    """`--autopilot-chain ... --autopilot-dry-run` がカタログ不在でも exit=0 で終了する。"""
    catalog = tmp_path / "missing-catalog.md"
    result = subprocess.run(
        [
            sys.executable, "-m", "hve", "orchestrate",
            "--autopilot-chain", "aad-web,asdw-web",
            "--autopilot-dry-run",
            "--autopilot-catalog", str(catalog),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    # 計画サマリが標準出力に含まれる
    assert "Autopilot Chain Plan" in result.stdout
    assert "catalog_exists: False" in result.stdout


def test_cli_autopilot_chain_and_workflow_are_mutually_exclusive() -> None:
    """`--autopilot-chain` と `--workflow` の同時指定は exit=1 になる。"""
    result = subprocess.run(
        [
            sys.executable, "-m", "hve", "orchestrate",
            "--autopilot-chain", "aad-web",
            "--workflow", "aad",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 1


def test_cli_orchestrate_requires_either_workflow_or_autopilot_chain() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "hve", "orchestrate"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 1
