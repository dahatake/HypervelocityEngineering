"""FR-GUI-36: 観測イベント → 自動進捗 Post の結線契約。"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from hve.gui.github_auto_post import AUTO_POST_TARGETS, GitHubAutoPostController


def _controller(mode: str = "both") -> GitHubAutoPostController:
    return GitHubAutoPostController(target_mode=mode, clock=lambda: "2026-08-26T00:00:00+00:00")


def _target_event(**fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": "github_target",
        "step": "",
        "run_id": "run-1",
        "workflow_id": "aas",
    }
    payload.update(fields)
    return payload


def _step_event(step: str, status: str, **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": "step_status",
        "step": step,
        "status": status,
        "run_id": "run-1",
        "workflow_id": "aas",
    }
    payload.update(fields)
    return payload


class TestDisabledByDefault:
    def test_target_values_are_the_four_documented_ones(self) -> None:
        assert AUTO_POST_TARGETS == ("off", "issue", "pr", "both")

    def test_default_mode_is_off(self) -> None:
        assert GitHubAutoPostController().target_mode == "off"

    def test_unknown_mode_falls_back_to_off(self) -> None:
        assert GitHubAutoPostController(target_mode="all").target_mode == "off"

    def test_off_never_produces_requests(self) -> None:
        controller = _controller("off")
        assert controller.handle_event(_target_event(issue_number=12, pr_number=34)) == []
        assert controller.handle_event(_step_event("1", "running")) == []
        assert controller.handle_event(_step_event("1", "done")) == []
        assert controller.finalize(overall_status="done", console_text="log") == []


class TestTargetSelection:
    def test_issue_mode_only_targets_issue(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12, pr_number=34))
        requests = controller.handle_event(_step_event("1", "running"))
        assert {request.kind for request in requests} == {"issue"}

    def test_pr_mode_only_targets_pull_request(self) -> None:
        controller = _controller("pr")
        controller.handle_event(_target_event(issue_number=12, pr_number=34))
        requests = controller.handle_event(_step_event("1", "running"))
        assert {request.kind for request in requests} == {"pr"}

    def test_both_mode_targets_issue_and_pull_request(self) -> None:
        controller = _controller("both")
        controller.handle_event(_target_event(issue_number=12, pr_number=34))
        requests = controller.handle_event(_step_event("1", "running"))
        assert {request.kind for request in requests} == {"issue", "pr"}

    def test_target_without_number_is_not_registered(self) -> None:
        controller = _controller("both")
        controller.handle_event(_target_event(issue_number=12))
        requests = controller.handle_event(_step_event("1", "running"))
        assert {request.kind for request in requests} == {"issue"}

    @pytest.mark.parametrize("value", [0, -1, True, "12", None])
    def test_invalid_number_is_ignored(self, value) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=value))
        assert controller.handle_event(_step_event("1", "running")) == []

    def test_late_pull_request_receives_only_the_final_update(self) -> None:
        controller = _controller("both")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)
        controller.handle_event(_step_event("1", "done"))
        controller.complete("issue", comment_id=500)

        # PR 番号は post-DAG ではじめて確定する。
        controller.handle_event(_target_event(issue_number=12, pr_number=34))
        requests = controller.finalize(overall_status="done", console_text="tail")
        by_kind = {request.kind: request for request in requests}
        assert by_kind["pr"].operation == "create"
        assert by_kind["pr"].target_number == 34
        assert by_kind["issue"].operation == "update"


class TestUpdateTriggers:
    def test_run_start_posts_once(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        assert len(controller.handle_event(_step_event("1", "running"))) == 1

    def test_non_terminal_updates_do_not_post(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        assert controller.handle_event(_step_event("2", "running")) == []
        assert controller.handle_event(_step_event("2", "queued")) == []

    @pytest.mark.parametrize("status", ["done", "failed", "skipped", "blocked"])
    def test_terminal_step_posts(self, status) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        assert len(controller.handle_event(_step_event("1", status))) == 1

    def test_unrelated_kinds_are_ignored(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        for kind in ("tool_invoked", "assistant_usage", "skill_invoked", "unknown"):
            assert controller.handle_event({"kind": kind, "step": "1"}) == []

    def test_step_event_without_step_id_is_ignored(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        assert controller.handle_event({"kind": "step_status", "step": "", "status": "done"}) == []


class TestBodyContent:
    def test_body_contains_run_and_step_table(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        request = controller.handle_event(_step_event("1", "running", elapsed=1.5))[0]

        assert "<!-- hve-progress:run=run-1 -->" in request.body
        assert "| workflow | `aas` |" in request.body
        assert "| `1` | running | 1.50s |" in request.body

    def test_interim_body_never_contains_console_text(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        request = controller.handle_event(_step_event("1", "running"))[0]
        assert "HVE コンソール出力" not in request.body

    def test_final_body_contains_console_tail(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        request = controller.finalize(overall_status="done", console_text="tail log")[0]
        assert "### HVE コンソール出力" in request.body
        assert "tail log" in request.body

    def test_final_body_masks_credentials(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        request = controller.finalize(
            overall_status="done", console_text="Authorization: Bearer abc.def-ghi"
        )[0]
        assert "abc.def-ghi" not in request.body
        assert "[REDACTED]" in request.body

    def test_steps_are_ordered_deterministically(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("2", "running"))
        controller.complete("issue", comment_id=500)
        controller.handle_event(_step_event("1", "done"))
        controller.complete("issue", comment_id=500)

        request = controller.finalize(overall_status="done")[0]
        assert request.body.index("| `1` |") < request.body.index("| `2` |")


class TestModeChangeDuringRun:
    def test_enabling_mid_run_starts_posting(self) -> None:
        controller = _controller("off")
        controller.handle_event(_target_event(issue_number=12))
        assert controller.handle_event(_step_event("1", "running")) == []

        controller.set_target_mode("issue")
        assert len(controller.handle_event(_step_event("1", "done"))) == 1

    def test_disabling_mid_run_stops_posting_without_deleting(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        assert controller.set_target_mode("off") == []
        assert controller.handle_event(_step_event("1", "done")) == []
        assert controller.finalize(overall_status="done") == []


class TestFailureAndShutdown:
    def test_create_failure_retries_as_create(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", error="network")

        retry = controller.handle_event(_step_event("1", "done"))
        assert retry[0].operation == "create"

    def test_update_failure_keeps_comment_id(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)
        controller.handle_event(_step_event("1", "done"))
        controller.complete("issue", error="network")

        retry = controller.finalize(overall_status="done")
        assert retry[0].operation == "update"
        assert retry[0].comment_id == 500

    def test_close_stops_all_new_requests(self) -> None:
        controller = _controller("both")
        controller.handle_event(_target_event(issue_number=12, pr_number=34))
        controller.close()

        assert controller.handle_event(_step_event("1", "done")) == []
        assert controller.finalize(overall_status="done", console_text="x") == []
        assert controller.set_target_mode("issue") == []

    def test_completion_after_close_does_not_emit(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.handle_event(_step_event("1", "done"))
        controller.close()

        assert controller.complete("issue", comment_id=500) is None


class TestBodySizeLimit:
    """GitHub の comment 上限を超えた本文を送らない。"""

    def test_body_is_truncated_to_the_comment_limit(self) -> None:
        from hve.gui.github_auto_post import MAX_COMMENT_CHARS

        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        controller.handle_event(_step_event("1", "running"))
        controller.complete("issue", comment_id=500)

        huge = "\n".join("x" * 4000 for _ in range(300))
        request = controller.finalize(overall_status="done", console_text=huge)[0]

        assert len(request.body) <= MAX_COMMENT_CHARS
        assert request.body.endswith("末尾を省略しました。")

    def test_normal_body_is_not_truncated(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        request = controller.handle_event(_step_event("1", "running"))[0]
        assert "末尾を省略しました。" not in request.body


class TestNoDirectApiUse:
    def test_module_does_not_import_github_api_or_pyside(self) -> None:
        import ast
        import inspect

        from hve.gui import github_auto_post

        tree = ast.parse(inspect.getsource(github_auto_post))
        imported: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)

        assert not any("github_api" in name for name in imported), imported
        assert not any("github_service" in name for name in imported), imported
        assert not any("PySide6" in name for name in imported), imported

    def test_requests_are_data_only(self) -> None:
        controller = _controller("issue")
        controller.handle_event(_target_event(issue_number=12))
        request = controller.handle_event(_step_event("1", "running"))[0]

        assert isinstance(request.target_number, int)
        assert isinstance(request.body, str)
        forbidden: List[str] = ["token", "Authorization"]
        assert all(word not in request.body for word in forbidden)
