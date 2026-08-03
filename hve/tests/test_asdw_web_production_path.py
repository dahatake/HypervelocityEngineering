"""Production-path E2E for the ASDW-WEB local-first / live-last flow (P19).

clean な一時リポジトリに対し、HVE の production API だけを組み合わせて
local generation checkpoint → live failure → 成果物保持 までを再現する。

- Azure process は一切起動しない（fake subprocess のみ）
- private fixture から完成成果物を注入しない（テスト内で最小入力を生成する）
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock

import pytest

import hve.orchestrator as orchestrator
from hve.dag_executor import DAGExecutor
from hve.workflow_registry import (
    get_live_phase_step_ids,
    get_local_phase_step_ids,
    get_next_steps,
    get_workflow,
)

_WORKFLOW_ID = "asdw-web"


class _RecordingConsole:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.events: List[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def event(self, message: str) -> None:
        self.events.append(message)


def _write(root: Path, relative: str, content: str = "generated") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Path:
    """完成成果物を含まない clean checkout 相当のツリーを作る。"""
    (tmp_path / "docs" / "catalog").mkdir(parents=True)
    _write(tmp_path, "docs/catalog/app-catalog.md", "# app catalog\n")
    assert not (tmp_path / "src").exists()
    return tmp_path


def _walk_until(completed: List[str], stop_before: Set[str]) -> List[str]:
    """stop_before に属する Step が ready になるまで DAG を進める。"""
    while True:
        nexts = [s.id for s in get_next_steps(_WORKFLOW_ID, completed_step_ids=completed)]
        if not nexts or set(nexts) & stop_before:
            return nexts
        completed.extend(nexts)


def test_production_dag_completes_local_generation_before_any_live_step(clean_repo) -> None:
    """production DAG API は live Step より前に local 生成を完了させる。"""
    local_ids = get_local_phase_step_ids(_WORKFLOW_ID)
    live_ids = get_live_phase_step_ids(_WORKFLOW_ID)
    completed: List[str] = []

    ready_live = _walk_until(completed, set(live_ids))

    assert set(completed) == set(local_ids)
    assert ready_live == ["1.3"]


def test_local_checkpoint_manifest_is_captured_from_local_outputs(clean_repo) -> None:
    """local 生成後の成果物が checkpoint manifest に取り込まれる。"""
    assert orchestrator.capture_protected_artifact_manifest(clean_repo) == {}

    _write(clean_repo, "src/api/svc-a/handler.py")
    _write(clean_repo, "src/app/index.tsx")
    _write(clean_repo, "src/test/ui/home.spec.ts")

    manifest = orchestrator.capture_protected_artifact_manifest(clean_repo)

    assert set(manifest) == {"src/api", "src/app", "src/test"}
    assert orchestrator.check_protected_artifact_regression(manifest, clean_repo) == []


def test_live_failure_retains_local_checkpoint_and_blocks_auto_merge(clean_repo) -> None:
    """live Step の失敗は step-local に留まり、checkpoint を破棄しない。"""
    _write(clean_repo, "src/api/svc-a/handler.py")
    _write(clean_repo, "src/app/index.tsx")
    checkpoint = orchestrator.capture_protected_artifact_manifest(clean_repo)

    # Step 1.3（live）だけが失敗した状況
    assert orchestrator.should_retain_local_checkpoint(_WORKFLOW_ID, {"1.3"}) is True
    # checkpoint 成果物は失われていない
    assert orchestrator.check_protected_artifact_regression(checkpoint, clean_repo) == []


def test_local_failure_does_not_qualify_for_checkpoint_retention(clean_repo) -> None:
    """local Step が失敗した run は checkpoint 保持の対象にしない。"""
    assert orchestrator.should_retain_local_checkpoint(_WORKFLOW_ID, {"4.2"}) is False


def test_artifact_loss_after_checkpoint_blocks_stage_commit_push(clean_repo, monkeypatch) -> None:
    """checkpoint 後に成果物が失われた場合、production の push 経路が停止する。"""
    _write(clean_repo, "src/api/svc-a/handler.py")
    _write(clean_repo, "src/app/index.tsx")
    checkpoint = orchestrator.capture_protected_artifact_manifest(clean_repo)

    # live 失敗のリカバリ等で UI 成果物が消えた状況を再現する
    (clean_repo / "src" / "app" / "index.tsx").unlink()

    def fail_if_git_runs(args: Any, **_kwargs: Any):
        raise AssertionError(f"guard 違反時に git を実行した: {list(args)}")

    monkeypatch.setattr(orchestrator.subprocess, "run", fail_if_git_runs)
    console = _RecordingConsole()

    pushed = orchestrator._git_add_commit_push(
        branch="hve/asdw-web-run",
        commit_message="[ASDW-WEB] local checkpoint",
        console=console,
        protected_baseline=checkpoint,
        repo_root=clean_repo,
    )

    assert pushed is False
    assert any("src/app" in error for error in console.errors)


def test_checkpoint_push_succeeds_when_artifacts_are_intact(clean_repo, monkeypatch) -> None:
    """成果物が保持されていれば checkpoint の commit / push は成功する。"""
    _write(clean_repo, "src/api/svc-a/handler.py")
    checkpoint = orchestrator.capture_protected_artifact_manifest(clean_repo)
    calls: List[List[str]] = []

    class _Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args: Any, **_kwargs: Any):
        argv = list(args)
        calls.append(argv)
        assert argv[0] == "git", f"Azure / 外部プロセスを起動した: {argv}"
        if argv[:3] == ["git", "status", "--porcelain"]:
            return _Result(0, stdout=" M src/api/svc-a/handler.py\n")
        if argv == ["git", "diff", "--cached", "--quiet"]:
            return _Result(1)
        return _Result(0)

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)

    pushed = orchestrator._git_add_commit_push(
        branch="hve/asdw-web-run",
        commit_message="[ASDW-WEB] local checkpoint",
        console=_RecordingConsole(),
        protected_baseline=checkpoint,
        repo_root=clean_repo,
    )

    assert pushed is True
    assert any(argv[:2] == ["git", "commit"] for argv in calls)
    assert any(argv[:2] == ["git", "push"] for argv in calls)


def test_live_failure_produces_draft_pr_without_auto_merge(clean_repo, monkeypatch) -> None:
    """live 失敗時の checkpoint PR は draft で、auto-merge 対象にならない。"""
    from unittest.mock import MagicMock

    captured: Dict[str, Any] = {}
    labelled: List[Any] = []

    monkeypatch.setattr(
        orchestrator,
        "create_pull_request",
        lambda **kwargs: (captured.update(kwargs), 101)[1],
    )
    monkeypatch.setattr(
        orchestrator,
        "add_labels",
        lambda *args, **kwargs: labelled.append((args, kwargs)),
    )

    config = MagicMock()
    config.repo = "owner/repo"
    config.base_branch = "main"
    config.resolve_token.return_value = "token"
    config.workiq_enabled = False
    config.is_workiq_qa_enabled.return_value = False
    config.is_workiq_akm_review_enabled.return_value = False
    config.enable_auto_merge = True
    config.ignore_paths = []
    config.workiq_draft_output_dir = "qa"

    failed_steps = {"1.3"}
    retain = orchestrator.should_retain_local_checkpoint(_WORKFLOW_ID, failed_steps)
    pr_number = orchestrator._create_pr_if_needed(
        wf=get_workflow(_WORKFLOW_ID),
        head_branch="hve/asdw-web-run",
        base_branch="main",
        config=config,
        console=_RecordingConsole(),
        all_steps_succeeded=False,
        local_checkpoint_only=retain,
    )

    assert retain is True
    assert pr_number == 101
    assert captured["draft"] is True
    assert "<!-- validation-confirmed -->" not in captured["body"]
    assert labelled == []


def test_production_path_never_invokes_azure_processes(clean_repo, monkeypatch) -> None:
    """production path のどの分岐でも Azure CLI / az を起動しない。

    `orchestrator.subprocess` は subprocess モジュールそのものなので、
    ここでの patch は subprocess.run を使う全モジュールに効く。
    Popen / os.system / asyncio 経路も併せて塞ぎ、抜け道を残さない。
    """
    invoked: List[List[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def recording_run(args: Any, **_kwargs: Any):
        invoked.append(list(args))
        return _Result()

    def forbidden(*args: Any, **kwargs: Any):
        raise AssertionError(f"想定外のプロセス起動経路が使われた: {args} {kwargs}")

    monkeypatch.setattr(subprocess, "run", recording_run)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "call", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", forbidden)

    _write(clean_repo, "src/api/svc-a/handler.py")
    checkpoint = orchestrator.capture_protected_artifact_manifest(clean_repo)
    orchestrator.check_protected_artifact_regression(checkpoint, clean_repo)
    orchestrator._git_add_commit_push(
        branch="hve/asdw-web-run",
        commit_message="[ASDW-WEB] local checkpoint",
        console=_RecordingConsole(),
        protected_baseline=checkpoint,
        repo_root=clean_repo,
    )

    assert invoked, "production path が 1 度も外部コマンドを呼ばなかった"
    for argv in invoked:
        assert argv[0] == "git", f"Azure / 非 git プロセスを起動した: {argv}"
        assert not any(token == "az" for token in argv), f"Azure CLI を起動した: {argv}"


def test_clean_repo_has_no_preinjected_artifacts(clean_repo) -> None:
    """private fixture から完成成果物を注入していないことを固定する。"""
    assert not (clean_repo / "src").exists()
    assert not (clean_repo / "src" / "infra").exists()
    assert list(clean_repo.rglob("*.sh")) == []


def test_real_subprocess_module_is_used_by_production_code() -> None:
    """production code が本物の subprocess を参照していること（fake の取り違え防止）。"""
    assert orchestrator.subprocess is subprocess


def _run_production_dag(
    clean_repo: Path,
    *,
    failing_step_ids: Set[str],
) -> DAGExecutor:
    """本物の DAGExecutor で ASDW-WEB を実行する（Agent セッションのみ fake）。

    Step ごとに local 成果物を生成し、`failing_step_ids` の Step だけ失敗させる。
    Azure / SDK / ネットワークは一切使わない。
    """
    wf = get_workflow(_WORKFLOW_ID)
    started: List[str] = []
    local_ids = get_local_phase_step_ids(_WORKFLOW_ID)
    live_ids = get_live_phase_step_ids(_WORKFLOW_ID)
    outputs = {
        "3.3": "src/api/svc-a/handler.py",
        "4.2": "src/app/index.tsx",
        "4.1": "src/test/ui/home.spec.ts",
    }

    async def fake_run_step(step_id: str, *_args: Any, **_kwargs: Any) -> bool:
        started.append(step_id)
        if step_id in live_ids:
            # live Step 到達時点で local 生成が全て完了していること
            assert local_ids <= set(started), (
                f"live Step {step_id} が local 未完了で開始された: {sorted(started)}"
            )
        if step_id in outputs:
            _write(clean_repo, outputs[step_id])
        return step_id not in failing_step_ids

    executor = DAGExecutor(
        workflow=wf,
        run_step_fn=fake_run_step,
        active_step_ids={s.id for s in wf.steps if not s.is_container},
        max_parallel=wf.max_parallel or 1,
        console=MagicMock(),
        repo_root=str(clean_repo),
        enable_fanout=False,
    )
    asyncio.run(executor.execute())
    return executor


def test_production_dag_executor_runs_local_phase_before_live_phase(clean_repo) -> None:
    """本物の DAGExecutor が local 生成を完了してから live Step を開始する。"""
    executor = _run_production_dag(clean_repo, failing_step_ids=set())

    assert not executor.failed
    assert get_local_phase_step_ids(_WORKFLOW_ID) <= executor.completed
    assert get_live_phase_step_ids(_WORKFLOW_ID) <= executor.completed


def test_production_dag_live_failure_keeps_local_outputs_and_retains_checkpoint(
    clean_repo,
) -> None:
    """live Step の失敗が step-local に留まり、local 成果物と checkpoint が残る。"""
    executor = _run_production_dag(clean_repo, failing_step_ids={"1.3"})

    # local フェーズは完了済み
    assert get_local_phase_step_ids(_WORKFLOW_ID) <= executor.completed
    # 失敗は live Step のみ
    assert executor.failed
    assert not (executor.failed & get_local_phase_step_ids(_WORKFLOW_ID))
    # local 成果物は残っている
    manifest = orchestrator.capture_protected_artifact_manifest(clean_repo)
    assert set(manifest) == {"src/api", "src/app", "src/test"}
    assert orchestrator.check_protected_artifact_regression(manifest, clean_repo) == []
    # checkpoint 保持の対象と判定される
    assert orchestrator.should_retain_local_checkpoint(_WORKFLOW_ID, executor.failed) is True
