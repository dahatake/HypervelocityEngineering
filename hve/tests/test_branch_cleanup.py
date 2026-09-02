"""FR-CLI-34 / FR-GUI-37: shared local branch cleanup RED contract."""

from __future__ import annotations

import importlib
import subprocess
from unittest.mock import Mock

import pytest


def _types():
    module = importlib.import_module("hve.branch_cleanup")
    return module.LocalBranchCleanupTarget, module.cleanup_local_branch


def _target(**overrides):
    target_type, _cleanup = _types()
    values = {
        "repo": "owner/repo",
        "pr_number": 41,
        "branch": "copilot-sdk/aas-1234abcd",
        "base_branch": "main",
        "created_by_hve": True,
    }
    values.update(overrides)
    return target_type(**values)


def _pull_request(**overrides):
    values = {
        "number": 41,
        "state": "closed",
        "merged": True,
        "head": {
            "ref": "copilot-sdk/aas-1234abcd",
            "repo": {"full_name": "owner/repo"},
        },
        "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
    }
    values.update(overrides)
    return values


def _ok_result(returncode: int = 0, stderr: str = ""):
    result = Mock()
    result.returncode = returncode
    result.stdout = ""
    result.stderr = stderr
    return result


class TestCleanupEligibility:
    def test_hve_created_merged_same_repo_matching_head_is_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock(side_effect=[_ok_result(), _ok_result()])

        result = cleanup(_target(), _pull_request(), runner=runner)

        assert result.deleted is True
        assert runner.call_count == 2

    def test_current_branch_mode_is_never_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(
            _target(created_by_hve=False, branch="feature/user-owned"),
            _pull_request(
                head={"ref": "feature/user-owned", "repo": {"full_name": "owner/repo"}}
            ),
            runner=runner,
        )

        assert result.deleted is False
        runner.assert_not_called()

    def test_base_branch_is_never_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(
            _target(branch="main"),
            _pull_request(head={"ref": "main", "repo": {"full_name": "owner/repo"}}),
            runner=runner,
        )

        assert result.deleted is False
        runner.assert_not_called()

    @pytest.mark.parametrize(
        "pull_request",
        [
            _pull_request(state="open", merged=False),
            _pull_request(state="closed", merged=False),
            _pull_request(state="closed", merged="true"),
            {},
        ],
    )
    def test_unmerged_or_unknown_pull_request_is_not_deleted(self, pull_request) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(_target(), pull_request, runner=runner)

        assert result.deleted is False
        runner.assert_not_called()

    def test_fork_head_is_not_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(
            _target(),
            _pull_request(
                head={
                    "ref": "copilot-sdk/aas-1234abcd",
                    "repo": {"full_name": "someone/fork"},
                }
            ),
            runner=runner,
        )

        assert result.deleted is False
        runner.assert_not_called()

    @pytest.mark.parametrize("head", [None, {}, {"ref": "copilot-sdk/aas-1234abcd"}])
    def test_unknown_head_repository_is_not_deleted(self, head) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(_target(), _pull_request(head=head), runner=runner)

        assert result.deleted is False
        runner.assert_not_called()

    def test_mismatched_head_branch_is_not_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(
            _target(),
            _pull_request(head={"ref": "other", "repo": {"full_name": "owner/repo"}}),
            runner=runner,
        )

        assert result.deleted is False
        runner.assert_not_called()

    def test_mismatched_pr_number_is_not_deleted(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(_target(), _pull_request(number=99), runner=runner)

        assert result.deleted is False
        runner.assert_not_called()

    @pytest.mark.parametrize("bad_number", [None, True, 0, -1, "41"])
    def test_invalid_target_pr_number_is_not_deleted(self, bad_number) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(_target(pr_number=bad_number), _pull_request(), runner=runner)

        assert result.deleted is False
        runner.assert_not_called()

    @pytest.mark.parametrize(
        "base",
        [
            {"ref": "develop", "repo": {"full_name": "owner/repo"}},
            {"ref": "main", "repo": {"full_name": "someone/fork"}},
            {"ref": "main"},
            None,
        ],
    )
    def test_mismatched_or_unknown_base_is_not_deleted(self, base) -> None:
        _target_type, cleanup = _types()
        runner = Mock()

        result = cleanup(_target(), _pull_request(base=base), runner=runner)

        assert result.deleted is False
        runner.assert_not_called()

    def test_repository_comparison_is_case_insensitive(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock(side_effect=[_ok_result(), _ok_result()])

        result = cleanup(
            _target(repo="Owner/Repo"),
            _pull_request(
                head={
                    "ref": "copilot-sdk/aas-1234abcd",
                    "repo": {"full_name": "owner/repo"},
                }
            ),
            runner=runner,
        )

        assert result.deleted is True


class TestLocalDeleteCommand:
    def test_checkout_base_then_force_delete_local_branch(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock(side_effect=[_ok_result(), _ok_result()])

        result = cleanup(_target(), _pull_request(), runner=runner)

        assert result.deleted is True
        assert runner.call_args_list[0].args[0] == ["git", "checkout", "main"]
        assert runner.call_args_list[1].args[0] == [
            "git",
            "branch",
            "-D",
            "--",
            "copilot-sdk/aas-1234abcd",
        ]
        for call in runner.call_args_list:
            assert "shell" not in call.kwargs
            assert call.kwargs["capture_output"] is True
            assert call.kwargs["text"] is True
            assert call.kwargs["encoding"] == "utf-8"
            assert call.kwargs["errors"] == "replace"

    def test_checkout_failure_does_not_attempt_delete(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock(return_value=_ok_result(1, "checkout failed"))

        result = cleanup(_target(), _pull_request(), runner=runner)

        assert result.deleted is False
        assert runner.call_count == 1

    def test_delete_failure_is_reported_without_remote_cleanup(self) -> None:
        _target_type, cleanup = _types()
        runner = Mock(side_effect=[_ok_result(), _ok_result(1, "delete failed")])

        result = cleanup(_target(), _pull_request(), runner=runner)

        assert result.deleted is False
        commands = [call.args[0] for call in runner.call_args_list]
        assert not any("push" in command for command in commands)

    @pytest.mark.parametrize(
        "error",
        [FileNotFoundError("git"), subprocess.TimeoutExpired("git", 30)],
    )
    def test_git_start_or_timeout_failure_is_fail_closed(self, error) -> None:
        _target_type, cleanup = _types()
        runner = Mock(side_effect=error)

        result = cleanup(_target(), _pull_request(), runner=runner)

        assert result.deleted is False
        assert runner.call_count == 1
