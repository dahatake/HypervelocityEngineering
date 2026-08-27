"""FR-CLI-82 startup configuration preflight の RED 契約テスト。

このファイルは実 Git / network を一切起動しない。すべての subprocess 呼び出しを
モックし、予定 API と fail-closed の判定契約だけを固定する。
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from hve import startup_preflight
from hve.startup_preflight import (
    github_write_required,
    validate_startup_configuration,
)
from hve.workflow_registry import WorkflowDef, get_workflow, list_workflows

_VALIDATE_PARAMETERS = (
    "workflow",
    "active_steps",
    "create_issues",
    "create_pr",
    "enable_auto_merge",
    "repo",
    "token",
    "base_branch",
    "create_working_branch",
    "check_remote",
    "repo_root",
)


def _workflow(workflow_id: str) -> WorkflowDef:
    workflow = get_workflow(workflow_id)
    assert workflow is not None, f"workflow が未登録: {workflow_id}"
    return workflow


def _completed(
    argv: list[str],
    returncode: int = 0,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        argv,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.fixture(autouse=True)
def git_run(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """startup_preflight から到達可能な subprocess.run を完全に遮断する。"""
    real_run = subprocess.run
    run_mock = Mock(name="subprocess.run")

    # ``import subprocess`` と ``from subprocess import run`` のどちらでも、
    # 実プロセスへ到達しないよう module-local alias も差し替える。
    direct_aliases = [
        name
        for name, value in vars(startup_preflight).items()
        if value is real_run
    ]
    monkeypatch.setattr(subprocess, "run", run_mock)
    for name in direct_aliases:
        monkeypatch.setattr(startup_preflight, name, run_mock)
    return run_mock


def _validate(
    repo_root: Path,
    *,
    workflow_id: str = "aas",
    active_steps: set[str] | None = None,
    create_issues: bool = False,
    create_pr: bool = False,
    enable_auto_merge: bool = False,
    repo: str = "owner/repo",
    token: str = "token-for-test",
    base_branch: str = "main",
    create_working_branch: bool = True,
    check_remote: bool = False,
):
    return validate_startup_configuration(
        workflow=_workflow(workflow_id),
        active_steps=set(active_steps or set()),
        create_issues=create_issues,
        create_pr=create_pr,
        enable_auto_merge=enable_auto_merge,
        repo=repo,
        token=token,
        base_branch=base_branch,
        create_working_branch=create_working_branch,
        check_remote=check_remote,
        repo_root=repo_root,
    )


def _assert_issue_shape(issue) -> None:
    assert issue.category in {"setting", "auth"}
    assert isinstance(issue.field_name, str) and issue.field_name
    assert isinstance(issue.message, str) and issue.message
    assert isinstance(issue.remediation_hint, str) and issue.remediation_hint


def _issue_for(result, field_name: str):
    matches = [issue for issue in result.issues if issue.field_name == field_name]
    assert len(matches) == 1, (
        f"{field_name!r} の issue は 1 件であること: "
        f"{[(issue.field_name, issue.message) for issue in result.issues]}"
    )
    return matches[0]


def _write_required(
    workflow: WorkflowDef,
    *,
    active_steps: set[str] | None = None,
    create_issues: bool = False,
    create_pr: bool = False,
    enable_auto_merge: bool = False,
) -> bool:
    return github_write_required(
        workflow=workflow,
        active_steps=set(active_steps or set()),
        create_issues=create_issues,
        create_pr=create_pr,
        enable_auto_merge=enable_auto_merge,
    )


class TestStartupPreflightApi:
    def test_validate_api_is_keyword_only_and_has_no_prompt_fields(self) -> None:
        signature = inspect.signature(validate_startup_configuration)

        assert tuple(signature.parameters) == _VALIDATE_PARAMETERS
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for parameter in signature.parameters.values()
        )
        assert not any("prompt" in name for name in signature.parameters)

    def test_normal_local_run_is_not_inspected_and_never_invokes_git(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(
            tmp_path,
            repo="",
            token="",
            base_branch="",
            check_remote=True,
        )

        assert result.is_ok()
        assert list(result.issues) == []
        git_run.assert_not_called()

    def test_check_remote_false_performs_only_local_validation(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(tmp_path, create_pr=True, check_remote=False)

        assert result.is_ok()
        assert list(result.issues) == []
        git_run.assert_not_called()


class TestGithubWriteRequired:
    @pytest.mark.parametrize("flag_name", ["create_issues", "create_pr"])
    def test_explicit_issue_or_pr_creation_targets_every_workflow(
        self,
        flag_name: str,
    ) -> None:
        for workflow in list_workflows():
            assert _write_required(
                workflow,
                create_issues=flag_name == "create_issues",
                create_pr=flag_name == "create_pr",
            ), workflow.id

    def test_auto_merge_is_adfdv_workflow_wide(self) -> None:
        for workflow in list_workflows():
            assert _write_required(
                workflow,
                enable_auto_merge=True,
            ) is (workflow.id == "adfdv"), workflow.id

    def test_auto_merge_requires_an_active_remote_cicd_step_elsewhere(self) -> None:
        observed_remote_steps: list[tuple[str, str]] = []

        for workflow in list_workflows():
            remote_step_ids = [
                step.id
                for step in workflow.steps
                if not step.is_container and step.requires_remote_cicd
            ]
            for step_id in remote_step_ids:
                observed_remote_steps.append((workflow.id, step_id))
                assert _write_required(
                    workflow,
                    active_steps={step_id},
                    enable_auto_merge=True,
                )
                assert not _write_required(
                    workflow,
                    active_steps={step_id},
                    enable_auto_merge=False,
                )

            if workflow.id != "adfdv":
                assert not _write_required(
                    workflow,
                    active_steps=set(),
                    enable_auto_merge=True,
                )

        assert observed_remote_steps, "requires_remote_cicd=True の Step が必要"


class TestLocalConfigurationValidation:
    def test_current_branch_mode_accepts_clean_non_base_branch_locally(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout="feature/current\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="",
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=False,
        )

        assert result.is_ok()
        assert [call.args[0] for call in git_run.call_args_list] == [
            ["git", "branch", "--show-current"],
            ["git", "status", "--porcelain", "--untracked-files=all"],
        ]

    @pytest.mark.parametrize(
        ("current_stdout", "status_stdout", "expected_field"),
        [
            ("\n", "", "current_branch"),
            ("main\n", "", "current_branch"),
            ("feature/current\n", " M src/app.py\n", "worktree"),
        ],
    )
    def test_current_branch_mode_rejects_detached_base_or_dirty_together(
        self,
        tmp_path: Path,
        git_run: Mock,
        current_stdout: str,
        status_stdout: str,
        expected_field: str,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout=current_stdout),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout=status_stdout,
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=False,
        )

        assert not result.is_ok()
        assert expected_field in {issue.field_name for issue in result.issues}

    def test_current_branch_mode_rejects_untracked_files(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout="feature/current\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="?? new-file.txt\n",
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=False,
        )

        assert "worktree" in {issue.field_name for issue in result.issues}

    def test_current_branch_probe_failures_are_fail_closed(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], returncode=128),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                returncode=128,
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=False,
        )

        assert {issue.field_name for issue in result.issues} >= {
            "current_branch",
            "worktree",
        }

    def test_repo_token_and_branch_issues_are_reported_together(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(
            tmp_path,
            create_issues=True,
            repo="owner-only",
            token="",
            base_branch="feature..broken",
            check_remote=False,
        )

        assert not result.is_ok()
        assert {issue.field_name for issue in result.issues} == {
            "repo",
            "token",
            "base_branch",
        }
        assert _issue_for(result, "repo").category == "setting"
        assert _issue_for(result, "token").category == "auth"
        assert _issue_for(result, "base_branch").category == "setting"
        for issue in result.issues:
            _assert_issue_shape(issue)
        git_run.assert_not_called()

    def test_local_and_origin_issues_are_reported_together(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.return_value = _completed(
            ["git", "remote", "get-url", "origin"],
            returncode=2,
            stderr="error: No such remote 'origin'",
        )

        result = _validate(
            tmp_path,
            create_issues=True,
            repo="owner-only",
            token="",
            base_branch="feature..broken",
            check_remote=True,
        )

        assert {issue.field_name for issue in result.issues} == {
            "repo",
            "token",
            "base_branch",
            "origin",
        }
        git_run.assert_called_once()

    @pytest.mark.parametrize(
        "repo",
        [
            "owner-only",
            "owner/repo/extra",
            "https://github.com/owner/repo",
            " owner/repo ",
            "./repo",
            "../repo",
            "owner/.",
            "owner/..",
        ],
    )
    def test_repo_must_be_exact_owner_slash_repo(
        self,
        repo: str,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(tmp_path, create_pr=True, repo=repo)

        assert not result.is_ok()
        assert _issue_for(result, "repo").category == "setting"
        git_run.assert_not_called()

    @pytest.mark.parametrize("token", [" ", "\t", "token with space", "token\n"])
    def test_token_must_not_be_blank_or_contain_whitespace(
        self,
        token: str,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(tmp_path, create_pr=True, token=token)

        assert not result.is_ok()
        assert _issue_for(result, "token").category == "auth"
        git_run.assert_not_called()

    @pytest.mark.parametrize(
        "base_branch",
        [
            "-leading",
            "feature lock",
            "feature..broken",
            "topic/.hidden",
            "release.lock/next",
        ],
    )
    def test_invalid_git_branch_names_are_rejected(
        self,
        base_branch: str,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(
            tmp_path,
            create_pr=True,
            base_branch=base_branch,
        )

        assert not result.is_ok()
        assert _issue_for(result, "base_branch").category == "setting"
        git_run.assert_not_called()

    def test_missing_values_are_not_replaced_with_implicit_defaults(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        result = _validate(
            tmp_path,
            create_pr=True,
            repo="",
            token="",
            base_branch="",
        )

        assert not result.is_ok()
        assert {issue.field_name for issue in result.issues} == {
            "repo",
            "token",
            "base_branch",
        }
        git_run.assert_not_called()


class TestRemoteConfigurationValidation:
    def test_current_branch_existing_remote_must_match_local_head(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        branch = "feature/current"
        local_sha = "1" * 40
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout=f"{branch}\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="",
            ),
            _completed(["git", "remote", "get-url", "origin"], stdout="git@example\n"),
            _completed(["git", "ls-remote"], stdout="base\trefs/heads/main\n"),
            _completed(["git", "rev-parse", "HEAD"], stdout=f"{local_sha}\n"),
            _completed(
                ["git", "ls-remote"],
                stdout=f"{local_sha}\trefs/heads/{branch}\n",
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=True,
        )

        assert result.is_ok()
        assert git_run.call_args_list[-1].args[0] == [
            "git",
            "ls-remote",
            "--exit-code",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
        ]

    def test_current_branch_missing_remote_is_allowed_for_first_push(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout="feature/new\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="",
            ),
            _completed(["git", "remote", "get-url", "origin"], stdout="git@example\n"),
            _completed(["git", "ls-remote"], stdout="base\trefs/heads/main\n"),
            _completed(["git", "rev-parse", "HEAD"], stdout=f"{'1' * 40}\n"),
            _completed(["git", "ls-remote"], returncode=2),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=True,
        )

        assert result.is_ok()

    @pytest.mark.parametrize(
        ("local_result", "remote_result"),
        [
            (
                _completed(["git", "rev-parse", "HEAD"], stdout=f"{'1' * 40}\n"),
                _completed(
                    ["git", "ls-remote"],
                    stdout=f"{'2' * 40}\trefs/heads/feature/current\n",
                ),
            ),
            (
                _completed(["git", "rev-parse", "HEAD"], returncode=128),
                _completed(["git", "ls-remote"], returncode=2),
            ),
            (
                _completed(["git", "rev-parse", "HEAD"], stdout=f"{'1' * 40}\n"),
                _completed(["git", "ls-remote"], returncode=128),
            ),
        ],
    )
    def test_current_branch_remote_mismatch_or_unverifiable_is_fail_closed(
        self,
        tmp_path: Path,
        git_run: Mock,
        local_result,
        remote_result,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout="feature/current\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="",
            ),
            _completed(["git", "remote", "get-url", "origin"], stdout="git@example\n"),
            _completed(["git", "ls-remote"], stdout="base\trefs/heads/main\n"),
            local_result,
            remote_result,
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=True,
        )

        assert not result.is_ok()
        assert "current_branch" in {issue.field_name for issue in result.issues}

    @pytest.mark.parametrize(
        "remote_stdout",
        [
            f"{'1' * 40}\trefs/heads/other\n",
            (
                f"{'1' * 40}\trefs/heads/feature/current\n"
                f"{'1' * 40}\trefs/heads/feature/current\n"
            ),
            "malformed\n",
        ],
    )
    def test_current_remote_response_must_be_one_exact_ref(
        self,
        tmp_path: Path,
        git_run: Mock,
        remote_stdout: str,
    ) -> None:
        git_run.side_effect = [
            _completed(["git", "branch", "--show-current"], stdout="feature/current\n"),
            _completed(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                stdout="",
            ),
            _completed(["git", "remote", "get-url", "origin"], stdout="git@example\n"),
            _completed(["git", "ls-remote"], stdout="base\trefs/heads/main\n"),
            _completed(["git", "rev-parse", "HEAD"], stdout=f"{'1' * 40}\n"),
            _completed(["git", "ls-remote"], stdout=remote_stdout),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            create_working_branch=False,
            check_remote=True,
        )

        assert "current_branch" in {issue.field_name for issue in result.issues}
    def test_remote_validation_uses_exact_non_interactive_git_commands(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        branch = "release/2026.08"
        git_run.side_effect = [
            _completed(
                ["git", "remote", "get-url", "origin"],
                stdout="https://github.com/owner/repo.git\n",
            ),
            _completed(
                ["git", "ls-remote"],
                stdout=f"0123456789abcdef\trefs/heads/{branch}\n",
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            base_branch=branch,
            check_remote=True,
        )

        assert result.is_ok()
        assert list(result.issues) == []
        assert git_run.call_count == 2

        expected_commands = [
            ["git", "remote", "get-url", "origin"],
            [
                "git",
                "ls-remote",
                "--exit-code",
                "--heads",
                "origin",
                f"refs/heads/{branch}",
            ],
        ]
        for call, expected_command in zip(
            git_run.call_args_list,
            expected_commands,
            strict=True,
        ):
            args, kwargs = call
            assert isinstance(args[0], list)
            assert args[0] == expected_command
            assert kwargs.get("shell", False) is False
            assert kwargs["check"] is False
            assert kwargs["timeout"] == 30
            assert Path(kwargs["cwd"]) == tmp_path
            assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"

    def test_missing_origin_is_reported_without_attempting_ls_remote(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        git_run.return_value = _completed(
            ["git", "remote", "get-url", "origin"],
            returncode=2,
            stderr="error: No such remote 'origin'",
        )

        result = _validate(
            tmp_path,
            create_pr=True,
            check_remote=True,
        )

        assert not result.is_ok()
        assert git_run.call_count == 1
        issue = _issue_for(result, "origin")
        assert issue.category == "setting"
        _assert_issue_shape(issue)

    def test_ls_remote_status_two_means_exact_branch_does_not_exist(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        branch = "release/missing"
        git_run.side_effect = [
            _completed(
                ["git", "remote", "get-url", "origin"],
                stdout="https://github.com/owner/repo.git\n",
            ),
            _completed(["git", "ls-remote"], returncode=2),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            base_branch=branch,
            check_remote=True,
        )

        assert not result.is_ok()
        assert git_run.call_count == 2, "local/main branch fallback を試行しないこと"
        issue = _issue_for(result, "base_branch")
        assert issue.category == "setting"
        assert branch in f"{issue.message}\n{issue.remediation_hint}"
        _assert_issue_shape(issue)
        assert git_run.call_args_list[1].args[0][-1] == f"refs/heads/{branch}"

    @pytest.mark.parametrize("returncode", [1, 128, 255])
    def test_other_ls_remote_failures_are_not_reported_as_branch_absence(
        self,
        returncode: int,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        branch = "release/unverifiable"
        git_run.side_effect = [
            _completed(
                ["git", "remote", "get-url", "origin"],
                stdout="https://github.com/owner/repo.git\n",
            ),
            _completed(
                ["git", "ls-remote"],
                returncode=returncode,
                stderr="fatal: authentication failed",
            ),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            base_branch=branch,
            check_remote=True,
        )

        assert not result.is_ok()
        assert git_run.call_count == 2
        assert len(result.issues) == 1
        issue = result.issues[0]
        _assert_issue_shape(issue)
        assert issue.category == "auth"
        assert issue.field_name != "base_branch"

    def test_ls_remote_timeout_is_reported_as_remote_unverifiable(
        self,
        tmp_path: Path,
        git_run: Mock,
    ) -> None:
        command = ["git", "ls-remote"]
        git_run.side_effect = [
            _completed(
                ["git", "remote", "get-url", "origin"],
                stdout="https://github.com/owner/repo.git\n",
            ),
            subprocess.TimeoutExpired(command, timeout=30),
        ]

        result = _validate(
            tmp_path,
            create_pr=True,
            check_remote=True,
        )

        assert not result.is_ok()
        issue = _issue_for(result, "remote")
        assert issue.category == "auth"
        assert issue.field_name != "base_branch"
