"""FR-CLI-89: CLI で新規 Root Issue を Copilot cloud agent へ割り当てる。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest

from hve import __main__ as hve_main
from hve import orchestrator
from hve.config import SDKConfig
from hve.github_api import GitHubAPIError


class _RecordingConsole:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def event(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.events.append(message)

    def warning(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.warnings.append(message)

    def error(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.errors.append(message)


def _parse(*extra: str):
    return hve_main._build_parser().parse_args(
        ["orchestrate", "--workflow", "aas", *extra]
    )


def _workflow(*, with_sub_issue: bool = False):
    steps = []
    if with_sub_issue:
        steps.append(
            SimpleNamespace(
                id="1",
                title="Step one",
                is_container=False,
                body_template_path="template.md",
            )
        )
    return SimpleNamespace(id="aas", steps=steps)


def _call_create_issues(
    config: SDKConfig,
    console: _RecordingConsole,
    *,
    with_sub_issue: bool = False,
):
    return orchestrator._create_issues_if_needed(
        wf=_workflow(with_sub_issue=with_sub_issue),
        params={"issue_title": "Root title"},
        active_steps={"1"} if with_sub_issue else set(),
        config=config,
        console=cast(Any, console),
        render_template_fn=lambda **_kwargs: "sub body",
        build_root_issue_body_fn=lambda *_args, **_kwargs: "root body",
    )


def test_parser_and_sdk_config_default_to_disabled() -> None:
    assert _parse().assign_copilot_agent is False
    assert SDKConfig().assign_copilot_agent is False


def test_option_parity_registers_assignment_as_user_facing_hve_only() -> None:
    import yaml  # type: ignore[import-untyped]  # pyright: ignore[reportMissingTypeStubs]

    fixture_path = Path(__file__).parent / "fixtures" / "option_parity_matrix.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in fixture["options"]
        if item["option_key"] == "assign_copilot_agent"
    )

    assert entry["issue_form_field_id"] is None
    assert entry["hve_config_attr"] == "assign_copilot_agent"
    assert entry["hve_cli_flag"] == "--assign-copilot-agent"
    assert entry["applies_to"] == "hve_only"


def test_build_config_propagates_valid_assignment_request() -> None:
    config = hve_main._build_config(
        _parse("--create-issues", "--assign-copilot-agent")
    )

    assert config.assign_copilot_agent is True


def test_assignment_without_create_issues_warns_and_is_ignored(capsys) -> None:
    config = hve_main._build_config(_parse("--assign-copilot-agent"))

    assert config.assign_copilot_agent is False
    stderr = capsys.readouterr().err
    assert "--assign-copilot-agent" in stderr
    assert "--create-issues" in stderr
    assert "無視" in stderr


def test_assignment_with_existing_root_warns_and_is_ignored(capsys) -> None:
    config = hve_main._build_config(
        _parse(
            "--create-issues",
            "--issue-number",
            "77",
            "--assign-copilot-agent",
        )
    )

    assert config.assign_copilot_agent is False
    stderr = capsys.readouterr().err
    assert "--assign-copilot-agent" in stderr
    assert "--issue-number" in stderr
    assert "無視" in stderr


def test_autopilot_chain_rejects_assignment_before_early_dispatch(capsys) -> None:
    args = hve_main._build_parser().parse_args(
        [
            "orchestrate",
            "--autopilot-chain",
            "aad-web",
            "--assign-copilot-agent",
        ]
    )

    with mock.patch.object(
        hve_main, "_cmd_orchestrate_autopilot_chain", return_value=0
    ) as autopilot_mock:
        result = hve_main._cmd_orchestrate(args)

    assert result == 1
    autopilot_mock.assert_not_called()
    stderr = capsys.readouterr().err
    assert "--autopilot-chain" in stderr
    assert "--assign-copilot-agent" in stderr
    assert "同時" in stderr


def test_assignment_failure_result_propagates_nonzero_cli_exit() -> None:
    args = _parse("--create-issues", "--assign-copilot-agent")
    error_message = "Root Issue #101 は作成済みですが割り当てに失敗しました。"

    with mock.patch.object(
        hve_main, "_run_startup_configuration_preflight", return_value=True
    ), mock.patch.object(
        hve_main, "_validate_auto_coding_agent_review", return_value=True
    ), mock.patch.object(
        hve_main, "_run_copilot_auth_preflight", return_value=True
    ), mock.patch.object(
        hve_main, "_run_workiq_auth_preflight", return_value=True
    ), mock.patch.object(
        hve_main, "_run_azure_auth_preflight", return_value=True
    ), mock.patch.object(
        orchestrator,
        "run_workflow",
        new=mock.AsyncMock(return_value={"error": error_message}),
    ):
        result = hve_main._cmd_orchestrate(args)

    assert result == 1


def test_new_root_is_assigned_before_any_sub_issue() -> None:
    console = _RecordingConsole()
    order: list[str] = []
    created = 0

    def _create_issue(**_kwargs):
        nonlocal created
        created += 1
        order.append("root-created" if created == 1 else "sub-created")
        return (100 + created, 1000 + created)

    def _assign(*_args, **_kwargs):
        order.append("root-assigned")
        return {"assignees": [{"login": "copilot-swe-agent[bot]"}]}

    config = SDKConfig(
        create_issues=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
        base_branch="develop",
    )
    with mock.patch.object(
        orchestrator, "create_issue", side_effect=_create_issue
    ), mock.patch.object(
        orchestrator, "assign_copilot_agent", side_effect=_assign
    ) as assign_mock, mock.patch.object(
        orchestrator, "link_sub_issue", return_value=True
    ):
        root, step_map = _call_create_issues(
            config, console, with_sub_issue=True
        )

    assert root == 101
    assert step_map == {"1": 102}
    assert order == ["root-created", "root-assigned", "sub-created"]
    assign_mock.assert_called_once_with(
        101,
        repo="owner/repo",
        token="token",
        base_branch="develop",
    )


def test_existing_root_is_never_assigned_even_if_config_is_forced_true() -> None:
    console = _RecordingConsole()
    config = SDKConfig(
        create_issues=True,
        issue_number=77,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
    )
    with mock.patch.object(
        orchestrator, "get_issue", return_value={"number": 77}
    ), mock.patch.object(
        orchestrator, "create_issue"
    ) as create_mock, mock.patch.object(
        orchestrator, "assign_copilot_agent"
    ) as assign_mock:
        root, step_map = _call_create_issues(config, console)

    assert root == 77
    assert step_map == {}
    create_mock.assert_not_called()
    assign_mock.assert_not_called()


def test_assignment_failure_stops_after_single_root_creation() -> None:
    console = _RecordingConsole()
    config = SDKConfig(
        create_issues=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
    )
    with mock.patch.object(
        orchestrator,
        "create_issue",
        side_effect=[(101, 1001), (102, 1002)],
    ) as create_mock, mock.patch.object(
        orchestrator,
        "assign_copilot_agent",
        side_effect=GitHubAPIError("assignment failed", 500),
    ), pytest.raises(orchestrator.RootIssueAssignmentError) as raised:
        _call_create_issues(config, console, with_sub_issue=True)

    message = str(raised.value)
    assert "Root Issue #101 は作成済み" in message
    assert "割り当てに失敗" in message
    assert raised.value.root_issue_num == 101
    assert create_mock.call_count == 1


def test_shared_api_assignment_response_is_not_revalidated() -> None:
    console = _RecordingConsole()
    config = SDKConfig(
        create_issues=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
    )
    with mock.patch.object(
        orchestrator, "create_issue", return_value=(101, 1001)
    ), mock.patch.object(
        orchestrator, "assign_copilot_agent", return_value=None
    ):
        root, step_map = _call_create_issues(config, console)

    assert root == 101
    assert step_map == {}
    assert any("割り当てました" in event for event in console.events)


def test_unexpected_assignment_exception_is_not_wrapped() -> None:
    console = _RecordingConsole()
    config = SDKConfig(
        create_issues=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
    )
    with mock.patch.object(
        orchestrator, "create_issue", return_value=(101, 1001)
    ), mock.patch.object(
        orchestrator,
        "assign_copilot_agent",
        side_effect=RuntimeError("unexpected assignment failure"),
    ), pytest.raises(RuntimeError, match="unexpected assignment failure"):
        _call_create_issues(config, console)


def test_assignment_error_retains_created_root_issue_number() -> None:
    error = orchestrator.RootIssueAssignmentError(
        root_issue_num=101,
        message="Root Issue #101 は作成済みですが割り当てに失敗しました。",
    )

    assert error.root_issue_num == 101
    assert str(error) == "Root Issue #101 は作成済みですが割り当てに失敗しました。"


def test_run_workflow_reports_target_and_cleans_up_hve_created_branch() -> None:
    message = (
        "Root Issue #101 は作成済みですが、Copilot cloud agent への"
        "割り当てに失敗したため run を停止します。"
    )
    assignment_error = orchestrator.RootIssueAssignmentError(
        root_issue_num=101,
        message=message,
    )
    console = mock.MagicMock()
    preflight = mock.MagicMock()
    preflight.is_ok.return_value = True
    config = SDKConfig(
        create_issues=True,
        create_pr=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
        quiet=True,
        mdq_watch=False,
        cq_watch=False,
    )
    with mock.patch.object(
        orchestrator, "Console", return_value=console
    ), mock.patch.object(
        orchestrator, "_attach_runtime_observability", return_value=None
    ), mock.patch.object(
        orchestrator, "_start_index_watchers_when_idle", return_value=None
    ), mock.patch.object(
        orchestrator, "validate_startup_configuration", return_value=preflight
    ), mock.patch.object(
        orchestrator, "_git_checkout_new_branch", return_value=True
    ), mock.patch.object(
        orchestrator, "_emit_github_target_event"
    ) as target_event_mock, mock.patch.object(
        orchestrator, "_git_delete_local_branch", return_value=True
    ) as cleanup_mock, mock.patch.object(
        orchestrator,
        "_create_issues_if_needed",
        side_effect=assignment_error,
    ), mock.patch.object(
        orchestrator, "_git_current_branch"
    ) as current_branch_mock:
        result = asyncio.run(
            orchestrator.run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=config,
            )
        )

    assert result["error"] == message
    assert result["completed"] == []
    assert result["root_issue_num"] == 101
    working_branch = result["working_branch"]
    assert working_branch.startswith("copilot-sdk/aas-")
    target_event_mock.assert_called_once_with(
        console,
        repo="owner/repo",
        issue_number=101,
        branch=working_branch,
        base_branch="main",
        created_by_hve=True,
        delete_local_merged_branch=True,
    )
    cleanup_mock.assert_called_once_with(working_branch, "main", console)
    current_branch_mock.assert_not_called()
    console.error.assert_called_with(message)


def test_run_workflow_keeps_user_owned_current_branch_on_assignment_failure() -> None:
    message = (
        "Root Issue #202 は作成済みですが、Copilot cloud agent への"
        "割り当てに失敗したため run を停止します。"
    )
    assignment_error = orchestrator.RootIssueAssignmentError(
        root_issue_num=202,
        message=message,
    )
    console = mock.MagicMock()
    preflight = mock.MagicMock()
    preflight.is_ok.return_value = True
    config = SDKConfig(
        create_issues=True,
        create_pr=True,
        create_working_branch=False,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
        quiet=True,
        mdq_watch=False,
        cq_watch=False,
    )
    with mock.patch.object(
        orchestrator, "Console", return_value=console
    ), mock.patch.object(
        orchestrator, "_attach_runtime_observability", return_value=None
    ), mock.patch.object(
        orchestrator, "_start_index_watchers_when_idle", return_value=None
    ), mock.patch.object(
        orchestrator, "validate_startup_configuration", return_value=preflight
    ), mock.patch.object(
        orchestrator, "_git_current_branch", return_value="feature/user-owned"
    ), mock.patch.object(
        orchestrator, "_emit_github_target_event"
    ) as target_event_mock, mock.patch.object(
        orchestrator, "_git_delete_local_branch"
    ) as cleanup_mock, mock.patch.object(
        orchestrator,
        "_create_issues_if_needed",
        side_effect=assignment_error,
    ):
        result = asyncio.run(
            orchestrator.run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=config,
            )
        )

    assert result["error"] == message
    assert result["root_issue_num"] == 202
    assert result["working_branch"] == "feature/user-owned"
    target_event_mock.assert_called_once_with(
        console,
        repo="owner/repo",
        issue_number=202,
        branch="feature/user-owned",
        base_branch="main",
        created_by_hve=False,
        delete_local_merged_branch=True,
    )
    cleanup_mock.assert_not_called()
    console.error.assert_called_with(message)


def test_dry_run_and_create_issues_disabled_have_no_assignment_side_effect() -> None:
    dry_config = SDKConfig(
        dry_run=True,
        create_issues=True,
        create_pr=True,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
        quiet=True,
        mdq_watch=False,
        cq_watch=False,
    )
    disabled_config = SDKConfig(
        create_issues=False,
        assign_copilot_agent=True,
        repo="owner/repo",
        github_token="token",
    )
    disabled_console = _RecordingConsole()
    with mock.patch.object(
        orchestrator, "create_issue"
    ) as create_mock, mock.patch.object(
        orchestrator, "assign_copilot_agent"
    ) as assign_mock:
        dry_result = asyncio.run(
            orchestrator.run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=dry_config,
            )
        )
        disabled_result = _call_create_issues(
            disabled_config, disabled_console
        )

    assert dry_result["dry_run"] is True
    assert disabled_result == (None, {})
    create_mock.assert_not_called()
    assign_mock.assert_not_called()