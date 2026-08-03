"""RED contracts for local checkpoint retention on live-phase failure (P16).

live deploy が失敗しても local generation checkpoint の成果物は保持し、
draft PR として残す。live 未達を auto-merge しない。
"""
from __future__ import annotations

import inspect
from typing import Any, List
from unittest.mock import MagicMock

import pytest

import hve.orchestrator as orchestrator
from hve.workflow_registry import (
    get_live_phase_step_ids,
    get_local_phase_step_ids,
    get_workflow,
)


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


def test_asdw_web_declares_local_generation_checkpoint() -> None:
    """ASDW-WEB は local generation checkpoint となる Step を宣言する。"""
    assert get_workflow("asdw-web").local_checkpoint_step_id == "4.2"


def test_local_phase_covers_checkpoint_and_its_dependencies() -> None:
    """local フェーズは checkpoint とその推移的依存で構成される。"""
    assert get_local_phase_step_ids("asdw-web") == frozenset(
        {"1.1", "1.2", "2.1", "2.3", "3.1", "3.2", "3.3", "4.1", "4.2"}
    )


def test_live_phase_is_the_complement_of_the_local_phase() -> None:
    """live フェーズは local フェーズの補集合（非コンテナ Step）である。"""
    assert get_live_phase_step_ids("asdw-web") == frozenset(
        {"1.3", "2.2", "2.4", "3.4", "3.5", "4.3", "4.4", "5.1", "5.2"}
    )


def test_phase_helpers_are_empty_for_workflows_without_checkpoint() -> None:
    """checkpoint を宣言しない workflow では phase 分割を行わない。"""
    assert get_local_phase_step_ids("aad-web") == frozenset()
    assert get_live_phase_step_ids("aad-web") == frozenset()


def test_retain_checkpoint_when_only_live_steps_failed() -> None:
    """live Step だけが失敗した場合は local checkpoint を保持する。"""
    assert orchestrator.should_retain_local_checkpoint("asdw-web", {"1.3"}) is True
    assert orchestrator.should_retain_local_checkpoint("asdw-web", {"3.4", "4.3"}) is True


def test_discard_checkpoint_when_a_local_step_failed() -> None:
    """local Step が失敗した場合は checkpoint 保持の対象外。"""
    assert orchestrator.should_retain_local_checkpoint("asdw-web", {"3.3"}) is False
    assert orchestrator.should_retain_local_checkpoint("asdw-web", {"1.3", "4.2"}) is False


def test_no_retention_without_failures_or_checkpoint() -> None:
    """失敗が無い場合と checkpoint 未宣言 workflow では保持判定を行わない。"""
    assert orchestrator.should_retain_local_checkpoint("asdw-web", set()) is False
    assert orchestrator.should_retain_local_checkpoint("aad-web", {"1"}) is False


def test_checkpoint_pr_is_created_as_draft(monkeypatch) -> None:
    """checkpoint 保持時は draft PR として作成する。"""
    captured: dict = {}

    def fake_create_pull_request(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 42

    monkeypatch.setattr(orchestrator, "create_pull_request", fake_create_pull_request)

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

    number = orchestrator._create_pr_if_needed(
        wf=get_workflow("asdw-web"),
        head_branch="feature/x",
        base_branch="main",
        config=config,
        console=_RecordingConsole(),
        all_steps_succeeded=False,
        local_checkpoint_only=True,
    )

    assert number == 42
    assert captured["draft"] is True


def test_failed_run_without_checkpoint_retention_creates_no_pr(monkeypatch) -> None:
    """checkpoint 保持でない失敗は従来どおり PR を作らない。"""

    def fail_if_called(**_kwargs: Any) -> int:
        raise AssertionError("失敗時に PR を作成した")

    monkeypatch.setattr(orchestrator, "create_pull_request", fail_if_called)

    assert (
        orchestrator._create_pr_if_needed(
            wf=get_workflow("asdw-web"),
            head_branch="feature/x",
            base_branch="main",
            config=MagicMock(),
            console=_RecordingConsole(),
            all_steps_succeeded=False,
        )
        is None
    )


def _pr_config() -> MagicMock:
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
    return config


def test_checkpoint_pr_is_never_auto_merged(monkeypatch) -> None:
    """checkpoint PR に検証マーカーと auto-merge ラベルを付けない。"""
    captured: dict = {}
    labelled: List[Any] = []

    def fake_create_pull_request(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(orchestrator, "create_pull_request", fake_create_pull_request)
    monkeypatch.setattr(
        orchestrator,
        "add_labels",
        lambda *args, **kwargs: labelled.append((args, kwargs)),
    )

    number = orchestrator._create_pr_if_needed(
        wf=get_workflow("asdw-web"),
        head_branch="feature/x",
        base_branch="main",
        config=_pr_config(),
        console=_RecordingConsole(),
        all_steps_succeeded=False,
        local_checkpoint_only=True,
    )

    assert number == 7
    assert captured["draft"] is True
    assert "<!-- validation-confirmed -->" not in captured["body"]
    assert labelled == []


def test_successful_run_still_gets_auto_merge_label(monkeypatch) -> None:
    """全 Step 成功時は従来どおり auto-approve-ready を付与し draft にしない。"""
    captured: dict = {}
    labelled: List[Any] = []

    def fake_create_pull_request(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 8

    monkeypatch.setattr(orchestrator, "create_pull_request", fake_create_pull_request)
    monkeypatch.setattr(
        orchestrator,
        "add_labels",
        lambda *args, **kwargs: labelled.append((args, kwargs)),
    )

    orchestrator._create_pr_if_needed(
        wf=get_workflow("asdw-web"),
        head_branch="feature/x",
        base_branch="main",
        config=_pr_config(),
        console=_RecordingConsole(),
        all_steps_succeeded=True,
    )

    assert "draft" not in captured
    assert "<!-- validation-confirmed -->" in captured["body"]
    assert labelled


def test_checkpoint_pr_is_excluded_from_failure_cleanup() -> None:
    """失敗時 PR cleanup を checkpoint PR に適用しない。"""
    source = inspect.getsource(orchestrator.run_workflow)
    cleanup_index = source.index("_cleanup_failed_pr_if_created(")
    guard_window = source[max(0, cleanup_index - 1500):cleanup_index]

    assert "local_checkpoint_only" in guard_window


def test_live_failure_keeps_local_checkpoint_commit() -> None:
    """live 失敗でも local checkpoint の commit / push をスキップしない。"""
    source = inspect.getsource(orchestrator.run_workflow)

    assert "should_retain_local_checkpoint(" in source
    # checkpoint 保持時は PR 作成をスキップせず draft PR を作る
    assert "local_checkpoint_only=" in source
