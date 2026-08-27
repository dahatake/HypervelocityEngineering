"""test_self_improve.py — self_improve モジュールのユニット・統合テスト

テスト方針:
- scan_codebase は subprocess をモックして実行
- run_improvement_loop は dry_run=True モードで統合テスト
- ScopedPermissionHandler の許可/拒否ロジックをユニットテスト
- record_learning の学習ログ保存（tmp ディレクトリ使用）
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig, generate_run_id
from self_improve import (
    ImprovementRecord,
    ScanResult,
    ScanSummary,
    SelfImproveResult,
    TaskGoal,
    VerificationResult,
    _acquire_lock,
    _build_plan_summary,
    _build_verification_result,
    _mutation_permission_allowed,
    _release_lock,
    get_learning_summary,
    record_learning,
    run_improvement_loop,
    scan_codebase,
)
from permission_handler import ScopedPermissionHandler, is_safe_command


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_scan_result(
    quality_score: int = 85,
    lint_errors: int = 0,
    test_failures: int = 0,
    coverage_pct: float = 90.0,
    doc_issues: int = 0,
    raw_output: str = "",
) -> ScanResult:
    summary: ScanSummary = {
        "lint_errors": lint_errors,
        "test_failures": test_failures,
        "coverage_pct": coverage_pct,
        "doc_issues": doc_issues,
    }
    return ScanResult(
        quality_score=quality_score,
        issues=[],
        summary=summary,
        raw_output=raw_output,
    )


# ---------------------------------------------------------------------------
# scan_codebase テスト（subprocess モック）
# ---------------------------------------------------------------------------


class TestScanCodebase(unittest.TestCase):
    """scan_codebase の subprocess 呼び出しをモックしてテスト。"""

    @patch("self_improve._run_tool")
    def test_returns_scan_result_type(self, mock_run: MagicMock) -> None:
        """scan_codebase が ScanResult 型の辞書を返す。"""
        mock_run.return_value = ""
        result = scan_codebase()
        self.assertIn("quality_score", result)
        self.assertIn("issues", result)
        self.assertIn("summary", result)
        self.assertIn("raw_output", result)

    @patch("self_improve._run_tool")
    def test_quality_score_in_range(self, mock_run: MagicMock) -> None:
        """quality_score は 0〜100 の範囲内である。"""
        mock_run.return_value = ""
        result = scan_codebase()
        self.assertGreaterEqual(result["quality_score"], 0)
        self.assertLessEqual(result["quality_score"], 100)

    @patch("self_improve._run_tool")
    def test_lint_errors_counted(self, mock_run: MagicMock) -> None:
        """ruff 出力から lint_errors を数える。"""
        mock_run.side_effect = lambda cmd, **kw: (
            "path/file.py:1:1: E501 line too long\n"
            "path/file.py:2:1: W291 trailing whitespace\n"
            "path/file.py:3:1: RUF100 unused noqa directive\n"
            "path/file.py:4:1: UP006 use 'list' instead of 'List'\n"
            "path/file.py:5:1: I001 import block is un-sorted\n"
            if "ruff" in cmd
            else ""
        )
        result = scan_codebase()
        self.assertEqual(result["summary"]["lint_errors"], 5)

    @patch("self_improve._run_tool")
    def test_test_failures_counted(self, mock_run: MagicMock) -> None:
        """pytest 出力から test_failures を数える。"""
        mock_run.side_effect = lambda cmd, **kw: (
            "FAILED tests/test_foo.py::test_bar - AssertionError\n"
            "1 failed, 5 passed in 0.12s"
            if "pytest" in cmd
            else ""
        )
        result = scan_codebase()
        self.assertEqual(result["summary"]["test_failures"], 1)

    @patch("self_improve._run_tool")
    def test_test_errors_plural_counted(self, mock_run: MagicMock) -> None:
        """pytest の複数形 errors も test_failures として数える。"""
        mock_run.side_effect = lambda cmd, **kw: (
            "2 errors in 0.12s" if "pytest" in cmd else ""
        )
        result = scan_codebase()
        self.assertEqual(result["summary"]["test_failures"], 2)

    @patch("self_improve._run_tool")
    def test_tool_not_found_handled(self, mock_run: MagicMock) -> None:
        """ツールが見つからない場合も例外を投げずに処理される。"""
        mock_run.return_value = "[TOOL NOT FOUND] ruff"
        result = scan_codebase()
        self.assertIn("quality_score", result)

    @patch("self_improve._run_tool")
    def test_coverage_pct_parsed(self, mock_run: MagicMock) -> None:
        """pytest --cov の TOTAL 行からカバレッジ率を抽出する。"""
        pytest_output = (
            "Name       Stmts   Miss  Cover\n"
            "TOTAL        100     10    90%\n"
        )
        mock_run.side_effect = (
            lambda cmd, **kw: pytest_output if "pytest" in cmd else ""
        )
        result = scan_codebase()
        self.assertAlmostEqual(result["summary"]["coverage_pct"], 90.0)


# ---------------------------------------------------------------------------
# run_improvement_loop テスト（dry_run モード）
# ---------------------------------------------------------------------------


class TestRunImprovementLoopDryRun(unittest.TestCase):
    """dry_run=True で run_improvement_loop を統合テスト。"""

    def _make_config(self, **kwargs) -> SDKConfig:
        return SDKConfig(dry_run=True, **kwargs)

    def test_dry_run_returns_dry_run_reason(self) -> None:
        """dry_run=True の場合、stopped_reason='dry_run' を返す。"""
        cfg = self._make_config()
        result = run_improvement_loop(cfg)
        self.assertEqual(result["stopped_reason"], "dry_run")
        self.assertEqual(result["iterations_completed"], 0)

    def test_self_improve_skip_returns_disabled(self) -> None:
        """self_improve_skip=True の場合、stopped_reason='disabled' を返す。"""
        cfg = SDKConfig(self_improve_skip=True)
        result = run_improvement_loop(cfg)
        self.assertEqual(result["stopped_reason"], "disabled")

    def test_auto_self_improve_false_returns_disabled(self) -> None:
        """auto_self_improve=False の場合、stopped_reason='disabled' を返す。"""
        cfg = SDKConfig(auto_self_improve=False)
        result = run_improvement_loop(cfg)
        self.assertEqual(result["stopped_reason"], "disabled")

    def test_result_has_required_keys(self) -> None:
        """SelfImproveResult が必須キーを全て持つ。"""
        cfg = self._make_config()
        result = run_improvement_loop(cfg)
        self.assertIn("iterations_completed", result)
        self.assertIn("final_score", result)
        self.assertIn("records", result)
        self.assertIn("stopped_reason", result)


class TestRunImprovementLoopRedContracts(unittest.TestCase):
    """Sub-17: Post-DAG Self-Improveの未実装契約をREDで固定する。"""

    @staticmethod
    def _active_config(max_iterations: int = 1) -> SDKConfig:
        return SDKConfig(
            dry_run=False,
            auto_self_improve=True,
            self_improve_skip=False,
            self_improve_scope="workflow",
            self_improve_max_iterations=max_iterations,
            self_improve_quality_threshold=100,
            self_improve_target_scope="docs/agent",
            run_id="sub17-red-contract",
        )

    @staticmethod
    def _criterion(
        criterion_id: str,
        *,
        metric: str | None,
        expected: int | float | None = 0,
        operator: str = "eq",
        evaluator_type: str = "rule",
    ) -> dict[str, Any]:
        evidence_kind = {
            "schema": "field-value",
            "rule": "field-value",
            "tool-result": "tool-result",
            "test": "test-result",
            "human-approval": "approval",
        }[evaluator_type]
        return {
            "criterion_id": criterion_id,
            "description": f"deterministic criterion {criterion_id}",
            "required_for_done": True,
            "evaluator_type": evaluator_type,
            "evaluation": {
                "metric": metric,
                "operator": operator,
                "expected": expected,
            },
            "evidence_required": {
                "kind": evidence_kind,
                "reference": f"scan.summary.{metric}" if metric else "semantic-evaluator",
            },
            "failure_action": "blocked",
            "source": "docs/agent/goal-contract.json",
        }

    @classmethod
    def _goal(
        cls,
        *criteria: dict[str, Any],
        weights: dict[str, float] | None = None,
    ) -> TaskGoal:
        payload: dict[str, Any] = {
            "goal_description": "Sub-17 deterministic goal",
            "success_criteria": [criterion["description"] for criterion in criteria],
            "criterion_definitions": list(criteria),
            "reward_weights": weights
            or {"lint": 1.0, "test": 0.0, "documentation": 0.0},
            "tdd_phase": "GREEN",
        }
        return cast(TaskGoal, payload)

    @staticmethod
    def _with_validated_criterion_evidence(
        scan: ScanResult,
        criterion_id: str,
        *,
        kind: str,
        reference: str,
        status: str = "PASS",
        validation_outcome: str = "VALID",
        validation_reason: str = "deterministic evaluator verified the reference",
        reference_exists: bool = True,
        reference_known: bool = True,
        approval_valid: bool = True,
        valid_until: str | None = None,
    ) -> ScanResult:
        """将来の公開SCAN契約 ``validated_criterion_evidence`` を生成する。

        このkeyはLLM入力やAgent自己申告ではなく、test/tool/approvalの実在性と
        有効性を確認した決定的evaluatorだけが生成できる。production未実装のため
        本helperを利用するテストは意図的REDである。
        """
        payload = cast(dict[str, Any], scan)
        evidence_by_criterion = payload.setdefault(
            "validated_criterion_evidence", {}
        )
        evidence_by_criterion[criterion_id] = [{
            "kind": kind,
            "reference": reference,
            "status": status,
            "summary": f"{criterion_id} deterministic evaluator result",
            "observed_at": "2026-07-10T00:00:00Z",
            "validation": {
                "validator": "deterministic-scan-evaluator",
                "outcome": validation_outcome,
                "reason": validation_reason,
                "reference_exists": reference_exists,
                "reference_known": reference_known,
                "approval_valid": approval_valid,
                "valid_until": valid_until,
            },
        }]
        return scan

    @staticmethod
    def _git_changed_paths(repo_root: str) -> list[str]:
        """HEADからのtracked差分とscope外untrackedをGit正本で列挙する。"""
        tracked = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        return sorted(dict.fromkeys(
            path.replace("\\", "/") for path in [*tracked, *untracked] if path
        ))

    @staticmethod
    def _assert_valid_criterion_result(result: dict[str, Any]) -> None:
        assert {
            "criterion_id",
            "required_for_done",
            "evaluator_type",
            "status",
            "evidence",
            "evaluated_at",
            "reason",
        }.issubset(result)
        assert result["status"] in {"PASS", "FAIL", "BLOCKED", "NOT_EVALUATED"}
        assert result["evaluator_type"] in {
            "schema", "rule", "tool-result", "test", "human-approval"
        }
        assert isinstance(result["criterion_id"], str) and result["criterion_id"]
        assert isinstance(result["required_for_done"], bool)
        assert isinstance(result["reason"], str)
        evaluated_at = datetime.fromisoformat(
            result["evaluated_at"].replace("Z", "+00:00")
        )
        assert evaluated_at.tzinfo == timezone.utc
        assert isinstance(result["evidence"], list)
        for evidence in result["evidence"]:
            assert {
                "kind", "reference", "status", "summary", "observed_at"
            }.issubset(evidence)
            assert evidence["kind"] in {
                "field-value", "tool-result", "test-result", "approval", "file-diff"
            }
            assert isinstance(evidence["reference"], str) and evidence["reference"]
            assert evidence["status"] in {"PASS", "FAIL", "BLOCKED"}
            assert isinstance(evidence["summary"], str) and evidence["summary"]
            observed_at = datetime.fromisoformat(
                evidence["observed_at"].replace("Z", "+00:00")
            )
            assert observed_at.tzinfo == timezone.utc

    def _assert_gate_blocked(
        self,
        result: dict[str, Any],
        session: "TestRunImprovementLoopRedContracts._MutationSession",
        reason_code: str,
    ) -> None:
        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(session.create_count, 0)
        self.assertEqual(session.send_count, 0)
        self.assertEqual(session.mutation_action_count, 0)
        criterion_results = result.get("final_criterion_results", [])
        self.assertTrue(criterion_results)
        for criterion_result in criterion_results:
            self.assertIn(
                criterion_result.get("status"), {"BLOCKED", "NOT_EVALUATED"}
            )
            self.assertIn(reason_code, str(criterion_result.get("reason", "")))
            blocked_evidence = [
                item for item in criterion_result.get("evidence", [])
                if item.get("status") == "BLOCKED"
            ]
            self.assertTrue(blocked_evidence)
            self.assertTrue(any(
                reason_code in str(item.get("summary", ""))
                for item in blocked_evidence
            ))
        verification = result.get("final_verification")
        if not isinstance(verification, dict):
            self.fail("final_verification must be a dict for a blocked gate")
        self.assertEqual(verification.get("overall"), "BLOCKED")
        self.assertIn(reason_code, str(verification.get("notes", "")))

    class _MutationSession:
        def __init__(
            self,
            response: dict[str, Any] | str | BaseException,
            mutation_action: Callable[[], Any] | None,
            events: list[str] | None,
            tokens_per_request: int = 0,
            usage_shape: str = "total",
        ) -> None:
            self.response = response
            self.mutation_action = mutation_action
            self.events = events
            self.prompts: list[str] = []
            self.timeouts: list[float | None] = []
            self.create_count = 0
            self.create_session_kwargs: list[dict[str, Any]] = []
            self.client_start_count = 0
            self.client_stop_count = 0
            self.disconnect_count = 0
            self.required_context_seen_before_mutation = False
            self.release_lock_mock = MagicMock()
            self.send_count = 0
            self.scan_count = 0
            self.mutation_action_count = 0
            self.tokens_per_request = tokens_per_request
            self.usage_shape = usage_shape

        async def send_and_wait(self, prompt: str, timeout: float | None = None):
            self.prompts.append(prompt)
            self.timeouts.append(timeout)
            self.send_count += 1
            self.required_context_seen_before_mutation = all(
                marker in prompt for marker in (
                    "CRIT-LINT",
                    "docs/agent/agent-detail-test.md",
                    "scan.summary.lint_errors",
                )
            )
            if self.events is not None:
                self.events.append("mutate")
            if isinstance(self.response, BaseException):
                raise self.response
            if self.mutation_action is not None:
                self.mutation_action_count += 1
                self.mutation_action()
            content = (
                self.response
                if isinstance(self.response, str)
                else json.dumps(self.response, ensure_ascii=False)
            )
            data = types.SimpleNamespace(content=content)
            if self.usage_shape == "total":
                data.usage = types.SimpleNamespace(
                    total_tokens=self.tokens_per_request
                )
            elif self.usage_shape == "split":
                input_tokens = self.tokens_per_request // 2
                data.usage = types.SimpleNamespace(
                    input_tokens=input_tokens,
                    output_tokens=self.tokens_per_request - input_tokens,
                )
            elif self.usage_shape != "missing":
                raise AssertionError(f"unknown usage_shape fixture: {self.usage_shape}")
            return types.SimpleNamespace(data=data)

        async def disconnect(self) -> None:
            self.disconnect_count += 1
            return None

    class _MutationClient:
        def __init__(
            self,
            session: "TestRunImprovementLoopRedContracts._MutationSession",
            *,
            start_error: BaseException | None = None,
            create_session_error: BaseException | None = None,
        ) -> None:
            self.session = session
            self.start_count = 0
            self.stop_count = 0
            self.start_error = start_error
            self.create_session_error = create_session_error

        async def start(self) -> None:
            self.start_count += 1
            self.session.client_start_count += 1
            if self.start_error is not None:
                raise self.start_error
            return None

        async def stop(self) -> None:
            self.stop_count += 1
            self.session.client_stop_count += 1
            return None

        async def create_session(self, **kwargs):
            self.session.create_count += 1
            self.session.create_session_kwargs.append(dict(kwargs))
            if self.create_session_error is not None:
                raise self.create_session_error
            return self.session

    def test_mutation_permission_rejects_command_and_scope_escape(self) -> None:
        handler = ScopedPermissionHandler(strict=False)
        root = Path.cwd().resolve()
        scope = ["docs/agent"]

        inside = types.SimpleNamespace(
            tool_name="create_file",
            arguments={"path": "docs/agent/generated.md"},
        )
        outside = types.SimpleNamespace(
            tool_name="create_file",
            arguments={"path": "README.md"},
        )
        shell = types.SimpleNamespace(
            tool_name="powershell",
            arguments={"command": "Set-Content docs/agent/generated.md x"},
        )
        inside_patch = types.SimpleNamespace(
            tool_name="apply_patch",
            arguments={
                "input": "*** Begin Patch\n*** Update File: docs/agent/generated.md\n*** End Patch"
            },
        )
        outside_patch = types.SimpleNamespace(
            tool_name="apply_patch",
            arguments={
                "input": "*** Begin Patch\n*** Update File: README.md\n*** End Patch"
            },
        )
        inside_move = types.SimpleNamespace(
            tool_name="apply_patch",
            arguments={
                "input": (
                    "*** Begin Patch\n"
                    "*** Move File: docs/agent/old.md -> docs/agent/new.md\n"
                    "*** End Patch"
                )
            },
        )
        outside_move = types.SimpleNamespace(
            tool_name="apply_patch",
            arguments={
                "input": (
                    "*** Begin Patch\n"
                    "*** Move File: docs/agent/old.md -> README.md\n"
                    "*** End Patch"
                )
            },
        )

        self.assertTrue(_mutation_permission_allowed(inside, handler, scope, root))
        self.assertFalse(_mutation_permission_allowed(outside, handler, scope, root))
        self.assertFalse(_mutation_permission_allowed(shell, handler, scope, root))
        self.assertTrue(_mutation_permission_allowed(inside_patch, handler, scope, root))
        self.assertFalse(_mutation_permission_allowed(outside_patch, handler, scope, root))
        self.assertTrue(_mutation_permission_allowed(inside_move, handler, scope, root))
        self.assertFalse(_mutation_permission_allowed(outside_move, handler, scope, root))

    def _run(
        self,
        scans: list[ScanResult],
        *,
        goal: TaskGoal,
        mutation_result: dict[str, Any] | str | BaseException | None = None,
        mutation_action: Callable[[], Any] | None = None,
        max_iterations: int = 1,
        max_requests: int | None = None,
        max_tokens: int | None = None,
        tokens_per_request: int = 0,
        usage_shape: str = "total",
        client_start_error: BaseException | None = None,
        create_session_error: BaseException | None = None,
        repo_root: str | None = None,
        target_scope: str = "docs/agent",
        resolved_paths: list[str] | None = None,
        scope_ceiling: list[str] | None = None,
        workflow_id: str | None = None,
        scope_precondition_error: str = "",
        events: list[str] | None = None,
        preexisting_action: Callable[[], Any] | None = None,
        tool_search: bool | None = None,
    ):
        cfg = self._active_config(max_iterations=max_iterations)
        if tool_search is not None:
            cfg.tool_search = tool_search
        if workflow_id is not None:
            cfg.workflow_id = workflow_id  # type: ignore[attr-defined]
        if max_requests is not None:
            cfg.self_improve_max_requests = max_requests
        if max_tokens is not None:
            cfg.self_improve_max_tokens = max_tokens
        cfg.self_improve_target_scope = target_scope
        if resolved_paths is not None:
            cfg._resolved_step_output_paths = resolved_paths  # type: ignore[attr-defined]
            cfg._resolved_workflow_default = ""  # type: ignore[attr-defined]
        if scope_ceiling is not None:
            cfg._resolved_scope_ceiling_paths = scope_ceiling  # type: ignore[attr-defined]
        if scope_precondition_error:
            cfg._resolved_scope_precondition_error = scope_precondition_error  # type: ignore[attr-defined]
        if repo_root is None:
            repo_context = tempfile.TemporaryDirectory()
            effective_repo = repo_context.name
        else:
            repo_context = None
            effective_repo = repo_root
        target_rel = "docs/agent/agent-detail-test.md"
        if resolved_paths:
            first_scope = resolved_paths[0].replace("\\", "/").rstrip("/")
            target_rel = (
                first_scope
                if Path(first_scope).suffix
                else f"{first_scope}/self-improve-mutation.txt"
            )
        target_file = Path(effective_repo, target_rel)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if not target_file.exists():
            target_file.write_text("before\n", encoding="utf-8")

        response = (
            mutation_result
            if mutation_result is not None
            else {
                "status": "MUTATED",
                "changed_files": [target_rel],
                "failed_changes": [],
                "no_change_reason": "",
                "response_summary": "mutation applied",
            }
        )
        session = self._MutationSession(
            response,
            mutation_action,
            events,
            tokens_per_request=tokens_per_request,
            usage_shape=usage_shape,
        )
        client = self._MutationClient(
            session,
            start_error=client_start_error,
            create_session_error=create_session_error,
        )

        default_action = mutation_action
        if (
            default_action is None
            and isinstance(response, dict)
            and response.get("status") != "IMPROVEMENT_NOT_NEEDED"
            and response.get("changed_files")
        ):
            default_action = lambda: target_file.write_text(
                target_file.read_text(encoding="utf-8") + "after\n",
                encoding="utf-8",
            )
            session.mutation_action = default_action

        if not (Path(effective_repo) / ".git").exists():
            subprocess.run(
                ["git", "init", "-q"], cwd=effective_repo, check=True,
                capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "sub17@example.invalid"],
                cwd=effective_repo, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Sub-17 Test"],
                cwd=effective_repo, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "add", "."], cwd=effective_repo, check=True,
                capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "baseline"],
                cwd=effective_repo, check=True, capture_output=True, text=True,
            )

        if preexisting_action is not None:
            preexisting_action()

        scan_iter = iter(scans)
        last_scan = scans[-1]
        scan_count = 0

        def _next_scan(*args, **kwargs):
            nonlocal scan_count
            scan_count += 1
            if events is not None:
                events.append("scan")
            return next(scan_iter, last_scan)

        release_lock = MagicMock()
        real_check_output = subprocess.check_output

        def _check_output(command, *args, **kwargs):
            if list(command) == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
                return "test-branch"
            return real_check_output(command, *args, **kwargs)

        try:
            with tempfile.TemporaryDirectory() as work_dir, \
                 patch("self_improve.scan_codebase", side_effect=_next_scan), \
                 patch("copilot_client_factory.create_copilot_client", return_value=client), \
                 patch("self_improve.record_learning"), \
                 patch("self_improve._acquire_lock", return_value=True), \
                 patch("self_improve._release_lock", release_lock), \
                 patch("self_improve.subprocess.check_output", side_effect=_check_output):
                result = run_improvement_loop(
                    cfg,
                    work_dir=Path(work_dir),
                    repo_root=effective_repo,
                    task_goal=goal,
                )
        finally:
            if repo_context is not None:
                repo_context.cleanup()
        session.release_lock_mock = release_lock
        session.scan_count = scan_count
        return result, session

    def test_scan_plan_mutate_verify_order(self) -> None:
        events: list[str] = []
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=100, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [before, after],
            goal=self._goal(criterion),
            events=events,
        )

        self.assertEqual(events, ["scan", "mutate", "scan"])
        prompt = session.prompts[0]
        self.assertIn("CRIT-LINT", prompt)
        self.assertIn("docs/agent/agent-detail-test.md", prompt)
        self.assertIn("scan.summary.lint_errors", prompt)
        self.assertTrue(session.required_context_seen_before_mutation)
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        plan = records[0].get("plan", {})
        self.assertEqual(plan.get("criterion_ids"), ["CRIT-LINT"])
        self.assertTrue(plan.get("root_cause"))
        self.assertTrue(plan.get("minimal_change"))
        self.assertEqual(session.client_start_count, 1)
        self.assertEqual(session.disconnect_count, 1)
        self.assertEqual(session.client_stop_count, 1)
        session.release_lock_mock.assert_called_once()

    def test_mutation_session_includes_tool_search_when_enabled(self) -> None:
        """FR-MODEL-04: Self-Improve セッションへも tool_search を伝搬する。"""
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=100, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        _result, session = self._run(
            [before, after],
            goal=self._goal(criterion),
            tool_search=True,
        )
        self.assertTrue(session.create_session_kwargs)
        self.assertEqual(
            session.create_session_kwargs[0].get("tool_search"), {"enabled": True}
        )

    def test_mutation_session_includes_tool_search_by_default(self) -> None:
        """FR-MODEL-04: 既定（有効）で Self-Improve セッションへも伝搬する。"""
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=100, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        _result, session = self._run([before, after], goal=self._goal(criterion))
        self.assertTrue(session.create_session_kwargs)
        self.assertEqual(
            session.create_session_kwargs[0].get("tool_search"), {"enabled": True}
        )

    def test_mutation_session_omits_tool_search_when_disabled(self) -> None:
        """FR-MODEL-06: 明示的な無効化は Self-Improve セッションへも渡さない。"""
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=100, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        _result, session = self._run(
            [before, after],
            goal=self._goal(criterion),
            tool_search=False,
        )
        self.assertTrue(session.create_session_kwargs)
        self.assertNotIn("tool_search", session.create_session_kwargs[0])

    def test_threshold_requires_required_criterion_evidence(self) -> None:
        perfect_scan = _make_scan_result(quality_score=100)
        semantic = self._criterion(
            "CRIT-SEMANTIC", metric=None, evaluator_type="rule"
        )
        result, session = self._run(
            [perfect_scan],
            goal=self._goal(semantic),
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(session.create_count, 0)
        self.assertEqual(session.send_count, 0)
        self.assertEqual(session.mutation_action_count, 0)
        self.assertEqual(session.scan_count, 1)
        criterion_results = result.get("final_criterion_results", [])
        self.assertEqual(len(criterion_results), 1)
        self._assert_valid_criterion_result(criterion_results[0])
        self.assertEqual(criterion_results[0]["criterion_id"], "CRIT-SEMANTIC")
        self.assertEqual(criterion_results[0]["status"], "NOT_EVALUATED")
        self.assertEqual(criterion_results[0]["evidence"], [])
        self.assertIn("evidence", criterion_results[0]["reason"].lower())

    def test_missing_required_criterion_definitions_fail_closed(self) -> None:
        goal = cast(TaskGoal, {
            "goal_description": "goal without deterministic definitions",
            "success_criteria": ["natural language only"],
            "reward_weights": {
                "lint": 1.0,
                "test": 0.0,
                "documentation": 0.0,
            },
            "tdd_phase": "GREEN",
        })
        result, session = self._run(
            [_make_scan_result(quality_score=100)],
            goal=goal,
            workflow_id="aag",
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(
            result.get("blocked_reason"),
            "goal_contract_required_criteria_missing",
        )
        self.assertEqual(session.scan_count, 0)
        self.assertEqual(session.send_count, 0)
        final_results = result.get("final_criterion_results", [])
        self.assertEqual(len(final_results), 1)
        self.assertEqual(final_results[0].get("status"), "BLOCKED")
        self.assertTrue(final_results[0].get("evidence"))

    def test_non_agent_workflow_without_definitions_keeps_legacy_opt_in(self) -> None:
        goal = cast(TaskGoal, {
            "goal_description": "legacy non-agent goal",
            "success_criteria": ["legacy metric threshold"],
            "reward_weights": {
                "lint": 1.0,
                "test": 0.0,
                "documentation": 0.0,
            },
            "tdd_phase": "GREEN",
        })
        result, session = self._run(
            [_make_scan_result(quality_score=100)],
            goal=goal,
            workflow_id="aas",
        )

        self.assertEqual(result.get("stopped_reason"), "no_improvement_needed")
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(session.send_count, 0)

    def test_required_test_without_collection_is_blocked(self) -> None:
        scan = _make_scan_result(quality_score=100)
        cast(dict[str, Any], scan)["tool_status"] = {
            "ruff": "PASS",
            "pytest": "NO_TESTS",
            "markdownlint": "PASS",
        }
        criterion = self._criterion(
            "CRIT-TEST",
            metric="test_failures",
            evaluator_type="test",
        )
        result, session = self._run(
            [scan],
            goal=self._goal(criterion),
            workflow_id="aagd",
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertIn(
            "required_tool_not_executed: test_failures (NO_TESTS)",
            str(result.get("blocked_reason", "")),
        )
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(session.send_count, 0)

    def test_required_tool_unavailable_is_blocked(self) -> None:
        scan = _make_scan_result(quality_score=100)
        cast(dict[str, Any], scan)["tool_status"] = {
            "ruff": "PASS",
            "pytest": "PASS",
            "markdownlint": "UNAVAILABLE",
        }
        criterion = self._criterion("CRIT-DOC", metric="doc_issues")
        result, session = self._run(
            [scan],
            goal=self._goal(criterion),
            workflow_id="aag",
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertIn(
            "required_tool_not_executed: doc_issues (UNAVAILABLE)",
            str(result.get("blocked_reason", "")),
        )
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(session.send_count, 0)

    def test_aag_and_aagd_default_goals_emit_required_evidence(self) -> None:
        from self_improve import (
            _evaluate_criteria,
            _required_criteria_all_pass,
            define_task_goal,
            discover_task_goal_from_docs,
        )

        perfect_scan = _make_scan_result(quality_score=100)
        for workflow_id in ("aag", "aagd"):
            with self.subTest(workflow_id=workflow_id):
                goal = define_task_goal(workflow_id)
                definitions = goal.get("criterion_definitions", [])
                self.assertTrue(definitions)
                self.assertTrue(all(
                    item.get("required_for_done") is True
                    for item in definitions
                ))
                results = _evaluate_criteria(perfect_scan, goal)
                self.assertEqual(len(results), len(definitions))
                self.assertTrue(_required_criteria_all_pass(results))
                self.assertTrue(all(item.get("evidence") for item in results))

                discovered = discover_task_goal_from_docs(
                    workflow_id,
                    repo_root=str(Path.cwd()),
                )["task_goal"]
                self.assertEqual(
                    discovered.get("criterion_definitions"),
                    definitions,
                )

    def test_llm_goal_discovery_preserves_required_definitions(self) -> None:
        from self_improve import (
            define_task_goal,
            discover_task_goal_with_llm,
        )

        class _PermissionHandler:
            approve_all = staticmethod(lambda request: True)

        class _Session:
            async def send_and_wait(self, prompt: str, timeout: float):
                return types.SimpleNamespace(
                    data=types.SimpleNamespace(content=json.dumps({
                        "goal_description": "LLM-refined AAG goal",
                        "success_criteria": ["refined criterion"],
                    }))
                )

            async def disconnect(self) -> None:
                return None

        class _Client:
            async def start(self) -> None:
                return None

            async def create_session(self, **kwargs):
                return _Session()

            async def stop(self) -> None:
                return None

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = _PermissionHandler

        with tempfile.TemporaryDirectory() as repo:
            source = Path(repo, "docs", "agent", "source.md")
            source.parent.mkdir(parents=True)
            source.write_text("# AAG source\n", encoding="utf-8")
            base_goal = define_task_goal("aag")
            static_result = {
                "task_goal": base_goal,
                "sources": ["docs/agent/source.md"],
            }
            with patch.dict(
                sys.modules,
                {
                    "copilot": fake_copilot,
                    "copilot.session": fake_copilot_session,
                },
            ), patch(
                "self_improve.discover_task_goal_from_docs",
                return_value=static_result,
            ), patch(
                "copilot_client_factory.create_copilot_client",
                return_value=_Client(),
            ):
                result = asyncio.run(discover_task_goal_with_llm(
                    workflow_id="aag",
                    repo_root=repo,
                ))

        self.assertEqual(
            result["task_goal"].get("criterion_definitions"),
            base_goal.get("criterion_definitions"),
        )

    def test_llm_goal_discovery_waits_for_cloud_session_readiness(self) -> None:
        """discover_task_goal_with_llm も orchestrator/runner と同じ Cloud Session readiness 待機を行う。"""
        from self_improve import (
            define_task_goal,
            discover_task_goal_with_llm,
        )

        class _PermissionHandler:
            approve_all = staticmethod(lambda request: True)

        class _FakeCloud:
            pass

        class _Session:
            async def send_and_wait(self, prompt: str, timeout: float):
                return types.SimpleNamespace(
                    data=types.SimpleNamespace(content=json.dumps({
                        "goal_description": "LLM-refined AAG goal",
                        "success_criteria": ["refined criterion"],
                    }))
                )

            async def disconnect(self) -> None:
                return None

        class _Client:
            async def start(self) -> None:
                return None

            async def create_session(self, **kwargs):
                return _Session()

            async def stop(self) -> None:
                return None

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = _PermissionHandler

        waited_sessions: list[object] = []

        async def fake_wait(session, **_kwargs):
            waited_sessions.append(session)

        with tempfile.TemporaryDirectory() as repo:
            source = Path(repo, "docs", "agent", "source.md")
            source.parent.mkdir(parents=True)
            source.write_text("# AAG source\n", encoding="utf-8")
            base_goal = define_task_goal("aag")
            static_result = {
                "task_goal": base_goal,
                "sources": ["docs/agent/source.md"],
            }
            with patch.dict(
                sys.modules,
                {
                    "copilot": fake_copilot,
                    "copilot.session": fake_copilot_session,
                },
            ), patch(
                "self_improve.discover_task_goal_from_docs",
                return_value=static_result,
            ), patch(
                "copilot_client_factory.create_copilot_client",
                return_value=_Client(),
            ), patch(
                "cloud_session.build_cloud_session_options",
                return_value=_FakeCloud(),
            ), patch(
                "cloud_session.wait_for_cloud_session_ready",
                new=fake_wait,
            ):
                asyncio.run(discover_task_goal_with_llm(
                    workflow_id="aag",
                    repo_root=repo,
                ))

        self.assertEqual(len(waited_sessions), 1)

    def test_llm_goal_discovery_readiness_wait_uses_default_timeout(self) -> None:
        """discover_task_goal_with_llm も timeout を明示せず既定値（60秒）に委ねる。"""
        from self_improve import (
            define_task_goal,
            discover_task_goal_with_llm,
        )

        class _PermissionHandler:
            approve_all = staticmethod(lambda request: True)

        class _FakeCloud:
            pass

        class _Session:
            async def send_and_wait(self, prompt: str, timeout: float):
                return types.SimpleNamespace(
                    data=types.SimpleNamespace(content=json.dumps({
                        "goal_description": "LLM-refined AAG goal",
                        "success_criteria": ["refined criterion"],
                    }))
                )

            async def disconnect(self) -> None:
                return None

        class _Client:
            async def start(self) -> None:
                return None

            async def create_session(self, **kwargs):
                return _Session()

            async def stop(self) -> None:
                return None

        fake_copilot = types.ModuleType("copilot")
        fake_copilot_session = types.ModuleType("copilot.session")
        fake_copilot_session.PermissionHandler = _PermissionHandler

        calls: list[tuple[tuple, dict]] = []

        async def fake_wait(*args, **kwargs):
            calls.append((args, kwargs))

        with tempfile.TemporaryDirectory() as repo:
            source = Path(repo, "docs", "agent", "source.md")
            source.parent.mkdir(parents=True)
            source.write_text("# AAG source\n", encoding="utf-8")
            base_goal = define_task_goal("aag")
            static_result = {
                "task_goal": base_goal,
                "sources": ["docs/agent/source.md"],
            }
            with patch.dict(
                sys.modules,
                {
                    "copilot": fake_copilot,
                    "copilot.session": fake_copilot_session,
                },
            ), patch(
                "self_improve.discover_task_goal_from_docs",
                return_value=static_result,
            ), patch(
                "copilot_client_factory.create_copilot_client",
                return_value=_Client(),
            ), patch(
                "cloud_session.build_cloud_session_options",
                return_value=_FakeCloud(),
            ), patch(
                "cloud_session.wait_for_cloud_session_ready",
                new=fake_wait,
            ):
                asyncio.run(discover_task_goal_with_llm(
                    workflow_id="aag",
                    repo_root=repo,
                ))

        self.assertEqual(len(calls), 1)
        _args, kwargs = calls[0]
        self.assertNotIn("timeout", kwargs)

    def test_explicit_scope_cannot_expand_workflow_output_ceiling(self) -> None:
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [_make_scan_result(quality_score=100)],
            goal=self._goal(criterion),
            target_scope=".",
            resolved_paths=["docs/agent"],
            scope_ceiling=["docs/agent"],
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertIn(
            "target_scope_exceeds_workflow_outputs",
            str(result.get("blocked_reason", "")),
        )
        self.assertEqual(session.scan_count, 0)
        self.assertEqual(session.send_count, 0)
        final_results = result.get("final_criterion_results", [])
        self.assertTrue(final_results)
        self.assertTrue(all(
            item.get("status") == "BLOCKED" and item.get("evidence")
            for item in final_results
        ))

    def test_required_agent_fanout_empty_blocks_before_scan(self) -> None:
        criterion = self._criterion("CRIT-DOC", metric="doc_issues")
        result, session = self._run(
            [_make_scan_result(quality_score=100)],
            goal=self._goal(criterion),
            workflow_id="aag",
            scope_precondition_error=(
                "required_agent_fanout_empty: AAG agent detail is missing"
            ),
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertIn(
            "required_agent_fanout_empty",
            str(result.get("blocked_reason", "")),
        )
        self.assertEqual(session.scan_count, 0)
        self.assertEqual(session.send_count, 0)
        final_results = result.get("final_criterion_results", [])
        self.assertTrue(final_results)
        self.assertTrue(all(item.get("status") == "BLOCKED" for item in final_results))

    def test_initial_all_criteria_pass_has_evidence_and_no_improvement_needed(self) -> None:
        perfect_scan = _make_scan_result(quality_score=100)
        test_criterion = self._criterion(
            "CRIT-TEST", metric="test_failures", evaluator_type="test"
        )
        result, session = self._run(
            [perfect_scan],
            goal=self._goal(test_criterion),
        )

        self.assertEqual(result.get("stopped_reason"), "no_improvement_needed")
        self.assertEqual(session.create_count, 0)
        self.assertEqual(session.send_count, 0)
        self.assertEqual(session.scan_count, 1)
        criterion_results = result.get("final_criterion_results", [])
        self.assertEqual(len(criterion_results), 1)
        criterion_result = criterion_results[0]
        self._assert_valid_criterion_result(criterion_result)
        self.assertEqual(criterion_result["status"], "PASS")
        self.assertEqual(
            criterion_result["evaluator_type"],
            test_criterion["evaluator_type"],
        )
        self.assertTrue(criterion_result["evidence"])
        evidence = criterion_result["evidence"][0]
        self.assertEqual(evidence["kind"], "test-result")
        self.assertEqual(evidence["reference"], "scan.summary.test_failures")
        self.assertEqual(evidence["status"], "PASS")

    def test_late_improvement_not_needed_cannot_claim_success(self) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=100, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [before, after],
            goal=self._goal(criterion),
            mutation_result={
                "status": "IMPROVEMENT_NOT_NEEDED",
                "changed_files": [],
                "failed_changes": [],
                "no_change_reason": "IMPROVEMENT_NOT_NEEDED",
                "response_summary": "no mutation required",
            },
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(result.get("iterations_completed"), 0)
        final_results = result.get("final_criterion_results", [])
        self.assertEqual(len(final_results), 1)
        self.assertEqual(final_results[0].get("status"), "FAIL")

    def test_improvement_not_needed_with_unmet_criterion_is_blocked(self) -> None:
        unchanged = _make_scan_result(quality_score=80, lint_errors=1)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [unchanged, unchanged],
            goal=self._goal(criterion),
            mutation_result={
                "status": "IMPROVEMENT_NOT_NEEDED",
                "changed_files": [],
                "failed_changes": [],
                "no_change_reason": "IMPROVEMENT_NOT_NEEDED",
                "response_summary": "no mutation required",
            },
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(result.get("stopped_reason"), "blocked")

    def test_no_diff_without_improvement_not_needed_is_blocked(self) -> None:
        unchanged = _make_scan_result(quality_score=80, lint_errors=1)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        claimed = "docs/agent/agent-detail-test.md"
        result, session = self._run(
            [unchanged, unchanged],
            goal=self._goal(criterion),
            mutation_result={
                "status": "MUTATED",
                "changed_files": [claimed],
                "failed_changes": [],
                "no_change_reason": "",
                "response_summary": "claimed mutation but performed no write",
            },
            mutation_action=lambda: None,
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.mutation_action_count, 1)
        self.assertEqual(session.scan_count, 2)
        self.assertEqual(result.get("stopped_reason"), "blocked")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("changed_files"), [])

    def test_mutation_partial_failure_preserves_paths_and_stops(self) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=90, lint_errors=1)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        changed = "docs/agent/agent-detail-test.md"
        failed = {
            "path": "docs/agent/agent-detail-other.md",
            "error": "write failed",
        }
        result, session = self._run(
            [before, after, after, after],
            goal=self._goal(criterion),
            mutation_result={
                "status": "PARTIAL_FAILURE",
                "changed_files": [changed],
                "failed_changes": [failed],
                "no_change_reason": "",
                "response_summary": "partial mutation",
            },
            max_iterations=2,
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.mutation_action_count, 1)
        self.assertIn(session.scan_count, {1, 2})
        self.assertEqual(result.get("stopped_reason"), "blocked")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("changed_files"), [changed])
        self.assertEqual(records[0].get("failed_changes"), [failed])
        self.assertEqual(session.client_start_count, 1)
        self.assertEqual(session.disconnect_count, 1)
        self.assertEqual(session.client_stop_count, 1)
        session.release_lock_mock.assert_called_once()

    def test_mutation_exception_cleans_up_session(self) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=1)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [before, before, before, before],
            goal=self._goal(criterion),
            mutation_result=RuntimeError("mutation failed"),
            max_iterations=2,
        )

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(session.client_start_count, 1)
        self.assertEqual(session.disconnect_count, 1)
        self.assertEqual(session.client_stop_count, 1)
        session.release_lock_mock.assert_called_once()

    def test_invalid_mutation_result_is_blocked_and_cleans_up(self) -> None:
        # changed_files / failed_changes はmutation responseの出力境界である。
        # target_scope入力を検証するtest_scope_resolver_*とは別契約として保持する。
        invalid_results: tuple[tuple[str, dict[str, Any] | str], ...] = (
            ("plain-text", "mutation complete"),
            ("malformed-json", "{not-json"),
            ("json-array", "[]"),
            (
                "unknown-status",
                {
                    "status": "DONE",
                    "changed_files": [],
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "invalid status",
                },
            ),
            (
                "missing-field",
                {
                    "status": "MUTATED",
                    "changed_files": ["docs/agent/agent-detail-test.md"],
                },
            ),
            (
                "changed-files-string",
                {
                    "status": "MUTATED",
                    "changed_files": "docs/agent/agent-detail-test.md",
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "wrong changed_files type",
                },
            ),
            (
                "failed-changes-string",
                {
                    "status": "PARTIAL_FAILURE",
                    "changed_files": [],
                    "failed_changes": "write failed",
                    "no_change_reason": "",
                    "response_summary": "wrong failed_changes type",
                },
            ),
            (
                "failed-change-missing-error",
                {
                    "status": "PARTIAL_FAILURE",
                    "changed_files": [],
                    "failed_changes": [{"path": "docs/agent/failed.md"}],
                    "no_change_reason": "",
                    "response_summary": "invalid failed change item",
                },
            ),
            (
                "mutated-with-failed-change",
                {
                    "status": "MUTATED",
                    "changed_files": ["docs/agent/agent-detail-test.md"],
                    "failed_changes": [{
                        "path": "docs/agent/failed.md",
                        "error": "write failed",
                    }],
                    "no_change_reason": "",
                    "response_summary": "status invariant violation",
                },
            ),
            (
                "partial-failure-without-failure",
                {
                    "status": "PARTIAL_FAILURE",
                    "changed_files": ["docs/agent/agent-detail-test.md"],
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "status invariant violation",
                },
            ),
            (
                "not-needed-with-changed-file",
                {
                    "status": "IMPROVEMENT_NOT_NEEDED",
                    "changed_files": ["docs/agent/agent-detail-test.md"],
                    "failed_changes": [],
                    "no_change_reason": "all criteria pass",
                    "response_summary": "status invariant violation",
                },
            ),
            (
                "not-needed-with-failed-change",
                {
                    "status": "IMPROVEMENT_NOT_NEEDED",
                    "changed_files": [],
                    "failed_changes": [{
                        "path": "docs/agent/failed.md",
                        "error": "write failed",
                    }],
                    "no_change_reason": "all criteria pass",
                    "response_summary": "status invariant violation",
                },
            ),
            (
                "mutation-response-absolute-changed-path",
                {
                    "status": "MUTATED",
                    "changed_files": ["C:/outside.md"],
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "unsafe path",
                },
            ),
            (
                "mutation-response-traversal-changed-path",
                {
                    "status": "MUTATED",
                    "changed_files": ["../outside.md"],
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "unsafe path",
                },
            ),
            (
                "absolute-failed-path",
                {
                    "status": "PARTIAL_FAILURE",
                    "changed_files": [],
                    "failed_changes": [{
                        "path": "/outside.md",
                        "error": "write failed",
                    }],
                    "no_change_reason": "",
                    "response_summary": "unsafe path",
                },
            ),
        )
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        for case, mutation_result in invalid_results:
            with self.subTest(case=case):
                result, session = self._run(
                    [
                        _make_scan_result(quality_score=80, lint_errors=1),
                        _make_scan_result(quality_score=80, lint_errors=1),
                    ],
                    goal=self._goal(criterion),
                    mutation_result=mutation_result,
                    mutation_action=lambda: None,
                    max_iterations=2,
                )

                self.assertEqual(session.send_count, 1)
                self.assertEqual(session.scan_count, 1)
                self.assertEqual(result.get("stopped_reason"), "blocked")
                self.assertEqual(result.get("iterations_completed"), 0)
                self.assertEqual(session.client_start_count, 1)
                self.assertEqual(session.disconnect_count, 1)
                self.assertEqual(session.client_stop_count, 1)
                session.release_lock_mock.assert_called_once()

    def test_lifecycle_failures_cleanup_only_created_resources(self) -> None:
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        before = _make_scan_result(quality_score=80, lint_errors=1)
        cases: tuple[
            tuple[str, str, str, str, dict[str, Any], str],
            ...,
        ] = (
            ("client-start", RuntimeError("start failed"), None, None, 0, 0),
            ("create-session", None, RuntimeError("create failed"), None, 1, 0),
            ("send", None, None, RuntimeError("send failed"), 1, 1),
            ("send-timeout", None, None, TimeoutError("send timed out"), 1, 1),
            ("lifecycle-response-parse", None, None, "{malformed-json", 1, 1),
        )
        for (
            case,
            start_error,
            create_error,
            response,
            expected_create_count,
            expected_disconnect_count,
        ) in cases:
            with self.subTest(case=case):
                result, session = self._run(
                    [before, before],
                    goal=self._goal(criterion),
                    mutation_result=response,
                    client_start_error=start_error,
                    create_session_error=create_error,
                    max_iterations=2,
                )

                self.assertEqual(result.get("stopped_reason"), "blocked")
                self.assertEqual(session.client_start_count, 1)
                self.assertEqual(session.create_count, expected_create_count)
                self.assertEqual(
                    session.send_count,
                    1 if case in {"send", "send-timeout", "lifecycle-response-parse"} else 0,
                )
                self.assertEqual(session.disconnect_count, expected_disconnect_count)
                self.assertEqual(session.client_stop_count, 1)
                self.assertEqual(session.mutation_action_count, 0)
                self.assertEqual(session.scan_count, 1)
                session.release_lock_mock.assert_called_once()

    def test_send_and_wait_receives_finite_positive_timeout(self) -> None:
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [
                _make_scan_result(quality_score=80, lint_errors=1),
                _make_scan_result(quality_score=90, lint_errors=0),
            ],
            goal=self._goal(criterion),
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(len(session.timeouts), 1)
        timeout = session.timeouts[0]
        self.assertIsInstance(timeout, (int, float))
        self.assertGreater(cast(float, timeout), 0)
        self.assertLess(cast(float, timeout), float("inf"))
        self.assertIn(result.get("stopped_reason"), {
            "threshold_reached", "max_iterations", "blocked"
        })

    def test_required_criterion_pass_to_fail_is_degradation_even_if_score_rises(self) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=0, doc_issues=1)
        after = _make_scan_result(quality_score=90, lint_errors=1, doc_issues=0)
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        documentation = self._criterion("CRIT-DOC", metric="doc_issues")
        result, session = self._run(
            [before, after],
            goal=self._goal(lint, documentation),
        )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(result.get("stopped_reason"), "degradation")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        statuses = {
            item["criterion_id"]: item["status"]
            for item in records[0].get("before_criteria", [])
        }
        after_statuses = {
            item["criterion_id"]: item["status"]
            for item in records[0].get("after_criteria", [])
        }
        self.assertEqual(statuses.get("CRIT-LINT"), "PASS")
        self.assertEqual(after_statuses.get("CRIT-LINT"), "FAIL")

    def test_test_failure_increase_is_degradation(self) -> None:
        before = _make_scan_result(
            quality_score=80, test_failures=0, doc_issues=1
        )
        after = _make_scan_result(
            quality_score=90, test_failures=1, doc_issues=0
        )
        test_criterion = self._criterion(
            "CRIT-TEST", metric="test_failures", evaluator_type="test"
        )
        documentation = self._criterion("CRIT-DOC", metric="doc_issues")
        result, _ = self._run(
            [before, after],
            goal=self._goal(test_criterion, documentation),
        )

        self.assertEqual(result.get("stopped_reason"), "degradation")

    def test_plateau_requires_two_valid_mutation_iterations(self) -> None:
        scans = [
            _make_scan_result(quality_score=80, doc_issues=10),
            _make_scan_result(quality_score=81, doc_issues=9),
            _make_scan_result(quality_score=81, doc_issues=9),
            _make_scan_result(quality_score=82, doc_issues=8),
        ]
        documentation = self._criterion("CRIT-DOC", metric="doc_issues")
        result, session = self._run(
            scans,
            goal=self._goal(
            documentation,
                weights={"lint": 0.0, "test": 0.0, "documentation": 1.0},
            ),
            max_iterations=3,
        )

        self.assertEqual(session.send_count, 2)
        self.assertEqual(session.scan_count, 4)
        self.assertEqual(result.get("iterations_completed"), 2)
        records = result.get("records", [])
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.get("changed_files") for record in records))
        self.assertEqual(result.get("stopped_reason"), "plateau_reached")

    def test_max_iterations_counts_only_valid_mutation_iterations(self) -> None:
        scans = [
            _make_scan_result(quality_score=60, lint_errors=20),
            _make_scan_result(quality_score=70, lint_errors=15),
            _make_scan_result(quality_score=70, lint_errors=15),
            _make_scan_result(quality_score=80, lint_errors=10),
            _make_scan_result(quality_score=80, lint_errors=10),
            _make_scan_result(quality_score=90, lint_errors=5),
        ]
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            scans,
            goal=self._goal(lint),
            max_iterations=2,
        )

        self.assertEqual(session.send_count, 2)
        self.assertEqual(session.scan_count, 4)
        self.assertEqual(result.get("iterations_completed"), 2)
        records = result.get("records", [])
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.get("changed_files") for record in records))
        self.assertEqual(result.get("stopped_reason"), "max_iterations")

    def test_criterion_definition_weakening_is_degradation(self) -> None:
        changes: tuple[tuple[str, Any], ...] = (
            ("required_for_done", False),
            ("evaluator_type", "human-approval"),
            ("evidence_required", {}),
        )
        for field, weakened_value in changes:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as repo:
                criterion = self._criterion(
                    "CRIT-LINT", metric="lint_errors"
                )
                goal = self._goal(criterion)
                contract_path = Path(repo, "docs/agent/goal-contract.json")
                contract_path.parent.mkdir(parents=True, exist_ok=True)
                contract_path.write_text(
                    json.dumps(
                        {"criterion_definitions": [criterion]},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )

                def _weaken(
                    *,
                    key=field,
                    value=weakened_value,
                ) -> None:
                    payload = json.loads(
                        contract_path.read_text(encoding="utf-8")
                    )
                    payload["criterion_definitions"][0][key] = value
                    contract_path.write_text(
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        encoding="utf-8",
                    )

                result, session = self._run(
                    [
                        _make_scan_result(quality_score=80, lint_errors=1),
                        _make_scan_result(quality_score=90, lint_errors=0),
                    ],
                    goal=goal,
                    repo_root=repo,
                    target_scope="",
                    resolved_paths=["docs/agent/goal-contract.json"],
                    mutation_action=_weaken,
                )

                self.assertEqual(session.send_count, 1)
                self.assertEqual(result.get("stopped_reason"), "degradation")
                records = result.get("records", [])
                self.assertEqual(len(records), 1)
                delta = records[0].get("protected_artifact_delta", [])
                self.assertTrue(
                    any(
                        item.get("kind") == "criterion-definition-changed"
                        and item.get("path") == "docs/agent/goal-contract.json"
                        for item in delta
                    ),
                    delta,
                )

    def test_required_criterion_deletion_is_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            first = self._criterion("CRIT-LINT", metric="lint_errors")
            second = self._criterion(
                "CRIT-TEST", metric="test_failures", evaluator_type="test"
            )
            goal = self._goal(first, second)
            contract_path = Path(repo, "docs/agent/goal-contract.json")
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            contract_path.write_text(
                json.dumps(
                    {"criterion_definitions": [first, second]},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            def _delete_criterion() -> None:
                payload = json.loads(contract_path.read_text(encoding="utf-8"))
                payload["criterion_definitions"].pop()
                contract_path.write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )

            result, session = self._run(
                [
                    _make_scan_result(quality_score=80, lint_errors=1),
                    _make_scan_result(quality_score=90, lint_errors=0),
                ],
                goal=goal,
                repo_root=repo,
                target_scope="",
                resolved_paths=["docs/agent/goal-contract.json"],
                mutation_action=_delete_criterion,
            )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(result.get("stopped_reason"), "degradation")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        delta = records[0].get("protected_artifact_delta", [])
        self.assertTrue(
            any(
                item.get("kind") == "criterion-definition-changed"
                and item.get("path") == "docs/agent/goal-contract.json"
                for item in delta
            ),
            delta,
        )

    def test_evaluator_types_require_matching_evidence(self) -> None:
        evaluator_cases = {
            "CRIT-SCHEMA": ("schema", "field-value", "schema-check"),
            "CRIT-RULE": ("rule", "field-value", "rule-check"),
            "CRIT-TOOL": ("tool-result", "tool-result", "tool-result-42"),
            "CRIT-TEST": ("test", "test-result", "tests/agent-report.md"),
            "CRIT-APPROVAL": ("human-approval", "approval", "approval-42"),
        }
        definitions = [
            self._criterion(cid, metric=None, evaluator_type=evaluator)
            for cid, (evaluator, _kind, _reference) in evaluator_cases.items()
        ]
        scan = _make_scan_result(quality_score=100)
        for definition in definitions:
            evaluator, kind, reference = evaluator_cases[
                definition["criterion_id"]
            ]
            definition["evidence_required"] = {
                "kind": kind,
                "reference": reference,
            }
            self._with_validated_criterion_evidence(
                scan,
                definition["criterion_id"],
                kind=kind,
                reference=reference,
                valid_until=(
                    "2026-07-11T00:00:00Z"
                    if evaluator == "human-approval" else None
                ),
            )

        result, session = self._run(
            [scan],
            goal=self._goal(*definitions),
        )

        self.assertEqual(session.send_count, 0)
        self.assertEqual(result.get("stopped_reason"), "no_improvement_needed")
        final_results = result.get("final_criterion_results", [])
        self.assertEqual(len(final_results), len(evaluator_cases))
        by_id = {item["criterion_id"]: item for item in final_results}
        for cid, (evaluator, kind, reference) in evaluator_cases.items():
            self._assert_valid_criterion_result(by_id[cid])
            self.assertEqual(by_id[cid]["evaluator_type"], evaluator)
            self.assertEqual(by_id[cid]["status"], "PASS")
            self.assertEqual(by_id[cid]["evidence"][0]["kind"], kind)
            self.assertEqual(by_id[cid]["evidence"][0]["reference"], reference)

    def test_unvalidated_llm_criterion_evidence_cannot_pass(self) -> None:
        criterion = self._criterion("CRIT-SEMANTIC", metric=None)
        scan = _make_scan_result(quality_score=100)
        cast(dict[str, Any], scan)["criterion_evidence"] = {
            "CRIT-SEMANTIC": [{
                "kind": "field-value",
                "reference": "semantic-evaluator",
                "status": "PASS",
                "summary": "LLM claims criterion passed",
                "observed_at": "2026-07-10T00:00:00Z",
            }]
        }

        result, session = self._run([scan], goal=self._goal(criterion))

        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertEqual(session.create_count, 0)
        self.assertEqual(session.send_count, 0)
        final_results = result.get("final_criterion_results", [])
        self.assertEqual(len(final_results), 1)
        self.assertIn(
            final_results[0].get("status"), {"BLOCKED", "NOT_EVALUATED"}
        )
        reason = str(final_results[0].get("reason", "")).lower()
        self.assertIn("validated", reason)
        self.assertIn("evidence", reason)

    def test_invalid_validated_evidence_is_blocked(self) -> None:
        cases = (
            (
                "missing-test-report",
                "test",
                "test-result",
                "tests/missing-report.xml",
                {"reference_exists": False},
                "test_report_missing",
            ),
            (
                "unknown-tool-id",
                "tool-result",
                "tool-result",
                "unknown-tool-result-99",
                {"reference_known": False},
                "tool_result_unknown",
            ),
            (
                "invalid-approval",
                "human-approval",
                "approval",
                "approval-invalid",
                {"approval_valid": False},
                "approval_invalid",
            ),
            (
                "expired-approval",
                "human-approval",
                "approval",
                "approval-expired",
                {"valid_until": "2026-07-09T23:59:59Z"},
                "approval_expired",
            ),
            (
                "kind-mismatch",
                "tool-result",
                "test-result",
                "tool-result-42",
                {},
                "evidence_kind_mismatch",
            ),
            (
                "reference-mismatch",
                "test",
                "test-result",
                "tests/other-report.xml",
                {},
                "evidence_reference_mismatch",
            ),
        )
        for (
            case,
            evaluator_type,
            evidence_kind,
            actual_reference,
            validation_overrides,
            expected_reason,
        ) in cases:
            with self.subTest(case=case):
                criterion = self._criterion(
                    "CRIT-EVIDENCE", metric=None, evaluator_type=evaluator_type
                )
                required_kind = {
                    "test": "test-result",
                    "tool-result": "tool-result",
                    "human-approval": "approval",
                }[evaluator_type]
                required_reference = {
                    "test": "tests/agent-report.xml",
                    "tool-result": "tool-result-42",
                    "human-approval": "approval-42",
                }[evaluator_type]
                criterion["evidence_required"] = {
                    "kind": required_kind,
                    "reference": required_reference,
                }
                scan = _make_scan_result(quality_score=100)
                self._with_validated_criterion_evidence(
                    scan,
                    "CRIT-EVIDENCE",
                    kind=evidence_kind,
                    reference=actual_reference,
                    validation_outcome="INVALID",
                    validation_reason=expected_reason,
                    **validation_overrides,
                )

                result, session = self._run(
                    [scan], goal=self._goal(criterion)
                )

                self.assertEqual(result.get("stopped_reason"), "blocked")
                self.assertEqual(session.create_count, 0)
                self.assertEqual(session.send_count, 0)
                self.assertEqual(session.mutation_action_count, 0)
                final_results = result.get("final_criterion_results", [])
                self.assertEqual(len(final_results), 1)
                self.assertIn(
                    final_results[0].get("status"),
                    {"BLOCKED", "NOT_EVALUATED"},
                )
                self.assertIn(
                    expected_reason,
                    str(final_results[0].get("reason", "")),
                )

    def test_test_skip_permission_and_hitl_weakening_is_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            detail = Path(repo, "docs/agent/agent-detail-test.md")
            test_file = Path(repo, "src/test/agent/AG-01.Tests/test_agent.py")
            policy_file = Path(repo, "src/agent/AG-01/policy.json")
            detail.parent.mkdir(parents=True, exist_ok=True)
            test_file.parent.mkdir(parents=True, exist_ok=True)
            policy_file.parent.mkdir(parents=True, exist_ok=True)
            detail.write_text("detail\n", encoding="utf-8")
            test_file.write_text(
                "def test_required():\n    assert True\n", encoding="utf-8"
            )
            policy_file.write_text(
                json.dumps({
                    "permissions": ["read"],
                    "hitl_required": True,
                    "approval_conditions": ["owner-review"],
                }),
                encoding="utf-8",
            )

            def _weaken_protection() -> None:
                test_file.write_text(
                    "import pytest\n\n@pytest.mark.skip(reason='weakening')\n"
                    "def test_required():\n    assert True\n",
                    encoding="utf-8",
                )
                policy_file.write_text(
                    json.dumps({
                        "permissions": ["read", "write"],
                        "hitl_required": False,
                    }),
                    encoding="utf-8",
                )

            lint = self._criterion("CRIT-LINT", metric="lint_errors")
            result, session = self._run(
                [
                    _make_scan_result(quality_score=80, lint_errors=1),
                    _make_scan_result(quality_score=90, lint_errors=0),
                ],
                goal=self._goal(lint),
                repo_root=repo,
                target_scope="",
                resolved_paths=[
                    "docs/agent/agent-detail-test.md",
                    "src/test/agent/AG-01.Tests",
                    "src/agent/AG-01",
                ],
                mutation_action=_weaken_protection,
            )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(result.get("stopped_reason"), "degradation")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        kinds = {
            item.get("kind")
            for item in records[0].get("protected_artifact_delta", [])
        }
        self.assertTrue({
            "test-skip-added",
            "permission-expanded",
            "hitl-weakened",
            "approval-condition-removed",
        }.issubset(kinds), kinds)

    def test_language_independent_test_skip_markers_are_degradation(self) -> None:
        marker_cases = (
            (
                "pytest-skip-call",
                "test_agent.py",
                "def test_required():\n    assert True\n",
                "import pytest\n\ndef test_required():\n    pytest.skip('disabled')\n",
            ),
            (
                "pytest-skipif",
                "test_agent.py",
                "def test_required():\n    assert True\n",
                "import pytest\n\n@pytest.mark.skipif(True, reason='disabled')\n"
                "def test_required():\n    assert True\n",
            ),
            (
                "unittest-skip",
                "test_agent.py",
                "import unittest\n\nclass T(unittest.TestCase):\n"
                "    def test_required(self):\n        self.assertTrue(True)\n",
                "import unittest\n\nclass T(unittest.TestCase):\n"
                "    @unittest.skip('disabled')\n"
                "    def test_required(self):\n        self.assertTrue(True)\n",
            ),
            (
                "xunit-skip",
                "AgentTests.cs",
                "[Fact]\npublic void Required() { Assert.True(true); }\n",
                "[Fact(Skip = \"disabled\")]\n"
                "public void Required() { Assert.True(true); }\n",
            ),
            (
                "typescript-skip",
                "agent.test.ts",
                "test('required', () => expect(true).toBe(true));\n",
                "test.skip('required', () => expect(true).toBe(true));\n",
            ),
        )
        for case, filename, baseline, weakened in marker_cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as repo:
                test_dir = Path(repo, "src/test/agent/AG-01.Tests")
                test_dir.mkdir(parents=True, exist_ok=True)
                test_file = test_dir / filename
                test_file.write_text(baseline, encoding="utf-8")

                result, session = self._run(
                    [
                        _make_scan_result(quality_score=80, lint_errors=1),
                        _make_scan_result(quality_score=90, lint_errors=0),
                    ],
                    goal=self._goal(
                        self._criterion("CRIT-LINT", metric="lint_errors")
                    ),
                    repo_root=repo,
                    target_scope="",
                    resolved_paths=["src/test/agent/AG-01.Tests"],
                    mutation_action=lambda: test_file.write_text(
                        weakened, encoding="utf-8"
                    ),
                )

                self.assertEqual(session.send_count, 1)
                self.assertEqual(result.get("stopped_reason"), "degradation")
                records = result.get("records", [])
                self.assertEqual(len(records), 1)
                kinds = {
                    item.get("kind")
                    for item in records[0].get("protected_artifact_delta", [])
                }
                self.assertIn("test-skip-added", kinds)

    def test_test_deletion_rbac_and_guardrail_weakening_is_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            detail = Path(repo, "docs/agent/agent-detail-test.md")
            test_file = Path(repo, "src/test/agent/AG-01.Tests/test_agent.py")
            policy_file = Path(repo, "src/agent/AG-01/policy.json")
            detail.parent.mkdir(parents=True, exist_ok=True)
            test_file.parent.mkdir(parents=True, exist_ok=True)
            policy_file.parent.mkdir(parents=True, exist_ok=True)
            detail.write_text("detail\n", encoding="utf-8")
            test_file.write_text(
                "def test_required():\n    assert True\n",
                encoding="utf-8",
            )
            policy_file.write_text(
                json.dumps({
                    "rbac_roles": ["Agent Data Reader"],
                    "guardrail_enabled": True,
                }),
                encoding="utf-8",
            )

            def _weaken_protection() -> None:
                test_file.unlink()
                policy_file.write_text(
                    json.dumps({
                        "rbac_roles": ["Owner"],
                        "guardrail_enabled": False,
                    }),
                    encoding="utf-8",
                )

            lint = self._criterion("CRIT-LINT", metric="lint_errors")
            result, session = self._run(
                [
                    _make_scan_result(quality_score=80, lint_errors=1),
                    _make_scan_result(quality_score=90, lint_errors=0),
                ],
                goal=self._goal(lint),
                repo_root=repo,
                target_scope="",
                resolved_paths=[
                    "docs/agent/agent-detail-test.md",
                    "src/test/agent/AG-01.Tests",
                    "src/agent/AG-01",
                ],
                mutation_action=_weaken_protection,
            )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(result.get("stopped_reason"), "degradation")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        kinds = {
            item.get("kind")
            for item in records[0].get("protected_artifact_delta", [])
        }
        self.assertTrue({
            "test-deleted",
            "rbac-expanded",
            "guardrail-weakened",
        }.issubset(kinds), kinds)

    def test_test_rename_is_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            test_dir = Path(repo, "src/test/agent/AG-01.Tests")
            test_dir.mkdir(parents=True, exist_ok=True)
            original = test_dir / "test_required.py"
            renamed = test_dir / "helper_required.py"
            original.write_text(
                "def test_required():\n    assert True\n", encoding="utf-8"
            )

            result, session = self._run(
                [
                    _make_scan_result(quality_score=80, lint_errors=1),
                    _make_scan_result(quality_score=90, lint_errors=0),
                ],
                goal=self._goal(
                    self._criterion("CRIT-LINT", metric="lint_errors")
                ),
                repo_root=repo,
                target_scope="",
                resolved_paths=["src/test/agent/AG-01.Tests"],
                mutation_action=lambda: original.rename(renamed),
            )

        self.assertEqual(session.send_count, 1)
        self.assertEqual(result.get("stopped_reason"), "degradation")
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        kinds = {
            item.get("kind")
            for item in records[0].get("protected_artifact_delta", [])
        }
        self.assertIn("test-renamed", kinds)

    def test_cost_limit_stops_before_additional_mutation(self) -> None:
        scans = [
            _make_scan_result(quality_score=60, lint_errors=20),
            _make_scan_result(quality_score=70, lint_errors=15),
            _make_scan_result(quality_score=70, lint_errors=15),
        ]
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            scans,
            goal=self._goal(lint),
            max_iterations=3,
            max_requests=1,
        )

        self.assertEqual(session.create_count, 1)
        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.mutation_action_count, 1)
        self.assertEqual(session.scan_count, 2)
        self.assertEqual(result.get("iterations_completed"), 1)
        self.assertEqual(result.get("stopped_reason"), "cost_limit")

    def test_token_limit_stops_before_additional_mutation(self) -> None:
        scans = [
            _make_scan_result(quality_score=60, lint_errors=20),
            _make_scan_result(quality_score=70, lint_errors=15),
            _make_scan_result(quality_score=70, lint_errors=15),
        ]
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        for usage_shape in ("total", "split"):
            with self.subTest(usage_shape=usage_shape):
                result, session = self._run(
                    scans,
                    goal=self._goal(lint),
                    max_iterations=3,
                    max_tokens=5,
                    tokens_per_request=6,
                    usage_shape=usage_shape,
                )

                self.assertEqual(session.create_count, 1)
                self.assertEqual(session.send_count, 1)
                self.assertEqual(session.mutation_action_count, 1)
                self.assertEqual(session.scan_count, 2)
                self.assertEqual(result.get("iterations_completed"), 1)
                self.assertEqual(result.get("stopped_reason"), "cost_limit")

    def test_missing_usage_metadata_blocks_before_verification(self) -> None:
        before = _make_scan_result(quality_score=60, lint_errors=20)
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        result, session = self._run(
            [before, before],
            goal=self._goal(lint),
            max_iterations=2,
            max_tokens=5,
            usage_shape="missing",
        )

        self.assertEqual(session.create_count, 1)
        self.assertEqual(session.send_count, 1)
        self.assertEqual(session.mutation_action_count, 1)
        self.assertEqual(session.scan_count, 1)
        self.assertEqual(result.get("iterations_completed"), 0)
        self.assertEqual(result.get("stopped_reason"), "blocked")
        self.assertIn("usage", str(result.get("blocked_reason", "")).lower())

    def test_zero_budget_blocks_before_session_creation(self) -> None:
        before = _make_scan_result(quality_score=60, lint_errors=20)
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        budget_cases = (
            ("request", 0, None),
            ("token", None, 0),
        )
        for budget_name, max_requests, max_tokens in budget_cases:
            with self.subTest(budget=budget_name):
                result, session = self._run(
                    [before],
                    goal=self._goal(lint),
                    max_iterations=2,
                    max_requests=max_requests,
                    max_tokens=max_tokens,
                )

                self.assertEqual(session.create_count, 0)
                self.assertEqual(session.send_count, 0)
                self.assertEqual(session.mutation_action_count, 0)
                self.assertEqual(session.scan_count, 1)
                self.assertEqual(result.get("iterations_completed"), 0)
                self.assertEqual(result.get("stopped_reason"), "cost_limit")

    def test_contract_validator_error_prevents_success(self) -> None:
        scan = _make_scan_result(quality_score=100)
        cast(dict[str, Any], scan)["contract_validator_errors"] = 1
        criterion = self._criterion(
            "CRIT-TEST", metric="test_failures", evaluator_type="test"
        )

        result, session = self._run([scan], goal=self._goal(criterion))

        self.assertEqual(session.scan_count, 1)
        self._assert_gate_blocked(
            result,
            session,
            "contract_validator_error",
        )

    def test_security_failure_prevents_success(self) -> None:
        scan = _make_scan_result(
            quality_score=100,
            raw_output="security scan: FAIL credential-like material detected",
        )
        cast(dict[str, Any], scan)["security_status"] = "FAIL"
        criterion = self._criterion(
            "CRIT-TEST", metric="test_failures", evaluator_type="test"
        )

        result, session = self._run([scan], goal=self._goal(criterion))

        self.assertEqual(session.scan_count, 1)
        self._assert_gate_blocked(
            result,
            session,
            "security_failure",
        )

    def test_mutation_prompt_receives_resolved_aag_and_aagd_scope(self) -> None:
        """Sub-18へ宣言済みpathを入力として渡す契約だけを検証する。

        mutation実装が各pathを正しく利用・変更するかはSub-18の責務とする。
        """
        from self_improve import _resolve_target_scope_paths

        agent_key = "AG-01"
        scopes = {
            "aag": [
                "docs/agent/agent-application-definition.md",
                "docs/agent/agent-architecture.md",
                "docs/ai-agent-catalog.md",
                f"docs/agent/agent-detail-{agent_key}.md",
            ],
            "aagd": [
                "docs/agent/agent-application-definition.md",
                f"docs/test-specs/{agent_key}-test-spec.md",
                f"src/test/agent/{agent_key}.Tests",
                f"src/agent/{agent_key}",
            ],
        }
        lint = self._criterion("CRIT-LINT", metric="lint_errors")
        for workflow_id, declared_paths in scopes.items():
            with self.subTest(workflow_id=workflow_id), \
                    tempfile.TemporaryDirectory() as repo:
                for declared in declared_paths:
                    path = Path(repo, declared)
                    if path.suffix:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("test", encoding="utf-8")
                    else:
                        path.mkdir(parents=True, exist_ok=True)
                resolved_paths = _resolve_target_scope_paths(
                    "", declared_paths, "", repo
                )
                self.assertEqual(resolved_paths, declared_paths)
                result, session = self._run(
                    [
                        _make_scan_result(quality_score=80, lint_errors=1),
                        _make_scan_result(quality_score=90, lint_errors=1),
                    ],
                    goal=self._goal(lint),
                    repo_root=repo,
                    target_scope="",
                    resolved_paths=resolved_paths,
                )

                self.assertEqual(session.send_count, 1)
                prompt = session.prompts[0]
                for declared in declared_paths:
                    self.assertIn(declared.replace("\\", "/"), prompt)
                self.assertNotEqual(
                    result.get("stopped_reason"),
                    "threshold_reached",
                )

    def test_mutation_permission_rejects_repo_internal_symlink_escape(self) -> None:
        handler = ScopedPermissionHandler(strict=False)
        with tempfile.TemporaryDirectory() as repo:
            root = Path(repo)
            allowed = root / "docs" / "agent"
            requested = allowed / "link" / "escaped.md"
            outside = root / "src" / "other" / "escaped.md"
            allowed.mkdir(parents=True)
            outside.parent.mkdir(parents=True)

            real_resolve = Path.resolve

            def _resolve(path: Path, *args, **kwargs) -> Path:
                if path == requested:
                    return real_resolve(outside, *args, **kwargs)
                return real_resolve(path, *args, **kwargs)

            request = types.SimpleNamespace(
                tool_name="create_file",
                arguments={"path": "docs/agent/link/escaped.md"},
            )
            with patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=_resolve,
            ):
                self.assertFalse(
                    _mutation_permission_allowed(
                        request,
                        handler,
                        ["docs/agent"],
                        root,
                    )
                )

    def test_scope_outside_diff_is_blocked_and_recorded(self) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=90, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        cases = (
            ("tracked-modification", "README.md", "modify"),
            ("untracked-addition", "outside-untracked.txt", "create"),
            ("tracked-deletion", "outside-delete.txt", "delete"),
        )
        for case, outside_rel, action_kind in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as repo:
                outside = Path(repo, outside_rel)
                if action_kind in {"modify", "delete"}:
                    outside.write_text("before\n", encoding="utf-8")

                def _mutate_outside_scope() -> None:
                    if action_kind == "delete":
                        outside.unlink()
                    else:
                        outside.write_text("after\n", encoding="utf-8")

                result, session = self._run(
                    [before, after],
                    goal=self._goal(criterion),
                    repo_root=repo,
                    mutation_result={
                        "status": "MUTATED",
                        "changed_files": [
                            "docs/agent/agent-detail-test.md"
                        ],
                        "failed_changes": [],
                        "no_change_reason": "",
                        "response_summary": "claimed in-scope mutation",
                    },
                    mutation_action=_mutate_outside_scope,
                )

                self.assertIn(outside_rel, self._git_changed_paths(repo))

            self.assertEqual(session.send_count, 1)
            self.assertEqual(result.get("stopped_reason"), "blocked")
            records = result.get("records", [])
            self.assertEqual(len(records), 1)
            self.assertIn(outside_rel, records[0].get("changed_files", []))
            self.assertNotEqual(
                records[0].get("changed_files"),
                ["docs/agent/agent-detail-test.md"],
            )

    def test_preexisting_diff_is_preserved_and_excluded_from_iteration_delta(
        self,
    ) -> None:
        before = _make_scan_result(quality_score=80, lint_errors=1)
        after = _make_scan_result(quality_score=90, lint_errors=0)
        criterion = self._criterion("CRIT-LINT", metric="lint_errors")
        target_rel = "docs/agent/agent-detail-test.md"
        preexisting_rel = "docs/preexisting.md"
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, target_rel)
            preexisting = Path(repo, preexisting_rel)
            preexisting.parent.mkdir(parents=True, exist_ok=True)
            preexisting.write_text("baseline\n", encoding="utf-8")

            def _make_preexisting_dirty() -> None:
                preexisting.write_text(
                    "baseline\npreexisting dirty change\n",
                    encoding="utf-8",
                )

            def _mutate_target() -> None:
                target.write_text(
                    target.read_text(encoding="utf-8") + "iteration change\n",
                    encoding="utf-8",
                )

            result, session = self._run(
                [before, after],
                goal=self._goal(criterion),
                repo_root=repo,
                mutation_result={
                    "status": "MUTATED",
                    "changed_files": [target_rel],
                    "failed_changes": [],
                    "no_change_reason": "",
                    "response_summary": "in-scope mutation",
                },
                mutation_action=_mutate_target,
                preexisting_action=_make_preexisting_dirty,
            )

            self.assertEqual(
                self._git_changed_paths(repo),
                sorted([preexisting_rel, target_rel]),
            )
            self.assertIn(
                "preexisting dirty change",
                preexisting.read_text(encoding="utf-8"),
            )

        self.assertEqual(session.send_count, 1)
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("changed_files"), [target_rel])
        self.assertEqual(
            records[0].get("preexisting_changed_files"),
            [preexisting_rel],
        )

    def test_scope_resolver_rejects_windows_absolute_and_unc_paths(self) -> None:
        from self_improve import _resolve_target_scope_paths

        with tempfile.TemporaryDirectory() as repo:
            outside = Path(repo).parent / "sub17-outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                self.assertEqual(
                    _resolve_target_scope_paths(
                        str(outside.resolve()), None, "", repo
                    ),
                    [],
                )
                self.assertEqual(
                    _resolve_target_scope_paths(
                        r"\\server\share\agent-detail.md", None, "", repo
                    ),
                    [],
                )
            finally:
                outside.unlink(missing_ok=True)

    def test_scope_resolver_rejects_resolved_path_escape(self) -> None:
        from self_improve import _resolve_target_scope_paths

        with tempfile.TemporaryDirectory() as repo, \
                tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside, "secret.md")
            outside_file.write_text("outside", encoding="utf-8")
            link = Path(repo, "docs", "agent", "escaped.md")
            link.parent.mkdir(parents=True)
            link.write_text("link placeholder", encoding="utf-8")

            real_resolve = Path.resolve

            def _resolve(path: Path, *args, **kwargs) -> Path:
                if path == link:
                    return outside_file.resolve()
                return real_resolve(path, *args, **kwargs)

            with patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=_resolve,
            ):
                self.assertEqual(
                    _resolve_target_scope_paths(
                        "docs/agent/escaped.md", None, "", repo
                    ),
                    [],
                )

    def test_scope_resolver_rejects_repo_internal_symlink_scope(self) -> None:
        from self_improve import _resolve_target_scope_paths

        with tempfile.TemporaryDirectory() as repo:
            Path(repo, "docs", "agent-link").mkdir(parents=True)
            with patch(
                "self_improve._path_has_symlink_component",
                return_value=True,
            ):
                self.assertEqual(
                    _resolve_target_scope_paths(
                        "docs/agent-link", None, "", repo
                    ),
                    [],
                )

    def test_windows_reparse_detection_does_not_require_path_is_junction(
        self,
    ) -> None:
        from self_improve import _is_windows_reparse_point

        fake_stat = types.SimpleNamespace(st_file_attributes=0x0400)
        with patch("self_improve.os.lstat", return_value=fake_stat):
            self.assertTrue(
                _is_windows_reparse_point(Path("docs/agent-junction"))
            )


# ---------------------------------------------------------------------------
# record_learning テスト
# ---------------------------------------------------------------------------


class TestRecordLearning(unittest.TestCase):
    """学習ログの保存・読み込みをテスト。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._work_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_record(self, iteration: int = 1) -> ImprovementRecord:
        verification: VerificationResult = {
            "after_quality_score": 85,
            "degraded": False,
            "verification_phases": {
                "build": "PASS",
                "lint": "PASS",
                "test": "PASS",
                "security": "PASS",
                "diff": "SKIP",
            },
            "overall": "PASS",
            "notes": "テスト補足",
        }
        return ImprovementRecord(
            iteration=iteration,
            before_score=70,
            after_score=85,
            degraded=False,
            plan_summary="lint errors: 5 を修正",
            verification=verification,
            elapsed_seconds=12.3,
        )

    def test_record_creates_file(self) -> None:
        """record_learning がファイルを作成する。"""
        record_learning(self._work_dir, 1, self._make_record(1))
        expected = self._work_dir / "artifacts" / "learning-001.md"
        self.assertTrue(expected.exists())

    def test_record_file_not_empty(self) -> None:
        """作成された学習ログファイルは空でない。"""
        record_learning(self._work_dir, 1, self._make_record(1))
        content = (self._work_dir / "artifacts" / "learning-001.md").read_text(encoding="utf-8")
        self.assertGreater(len(content), 0)

    def test_record_overwrites_existing(self) -> None:
        """§4.1 準拠: 既存ファイルを削除して新規作成する（上書きではなく delete → create）。"""
        artifacts_dir = self._work_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        old_file = artifacts_dir / "learning-001.md"
        old_file.write_text("古いコンテンツ", encoding="utf-8")

        record_learning(self._work_dir, 1, self._make_record(1))
        content = old_file.read_text(encoding="utf-8")
        self.assertNotIn("古いコンテンツ", content)

    def test_record_contains_iteration_number(self) -> None:
        """学習ログにイテレーション番号が含まれる。"""
        record_learning(self._work_dir, 3, self._make_record(3))
        content = (self._work_dir / "artifacts" / "learning-003.md").read_text(encoding="utf-8")
        self.assertIn("003", content)

    def test_get_learning_summary_returns_empty_for_iteration_zero(self) -> None:
        """イテレーション 0 の場合、空文字列を返す。"""
        summary = get_learning_summary(self._work_dir, 0)
        self.assertEqual(summary, "")

    def test_get_learning_summary_returns_content(self) -> None:
        """記録済みの学習ログサマリーを返す。"""
        record_learning(self._work_dir, 1, self._make_record(1))
        summary = get_learning_summary(self._work_dir, 1)
        self.assertGreater(len(summary), 0)

    def test_get_learning_summary_missing_file(self) -> None:
        """ファイルが存在しない場合は空文字列を返す。"""
        summary = get_learning_summary(self._work_dir, 99)
        self.assertEqual(summary, "")


# ---------------------------------------------------------------------------
# ロック制御テスト
# ---------------------------------------------------------------------------


class TestLockControl(unittest.TestCase):
    """work_dir/.self-improve-lock の排他制御をテスト。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._work_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_acquire_lock_succeeds(self) -> None:
        """ロックが存在しない場合、取得できる。"""
        self.assertTrue(_acquire_lock(self._work_dir))

    def test_acquire_lock_fails_when_locked(self) -> None:
        """ロックが既に存在する場合、取得に失敗する。"""
        _acquire_lock(self._work_dir)
        self.assertFalse(_acquire_lock(self._work_dir))

    def test_release_lock(self) -> None:
        """ロックを解放後は再度取得できる。"""
        _acquire_lock(self._work_dir)
        _release_lock(self._work_dir)
        self.assertTrue(_acquire_lock(self._work_dir))

    def test_release_lock_idempotent(self) -> None:
        """ロックが存在しない状態で release しても例外が発生しない。"""
        _release_lock(self._work_dir)  # ロックなし状態で解放

    def test_acquire_lock_creates_lockfile(self) -> None:
        """ロック取得後、ロックファイルが作成され、タイムスタンプが書き込まれる。"""
        _acquire_lock(self._work_dir)
        lock_file = self._work_dir / ".self-improve-lock"
        self.assertTrue(lock_file.exists())
        content = lock_file.read_text(encoding="utf-8")
        # ロックファイルにはタイムスタンプ（float 文字列）が書き込まれる
        self.assertTrue(len(content) > 0, "ロックファイルの内容が空")
        float(content)  # タイムスタンプとして parse できること

    def test_acquire_lock_atomic_prevents_double_acquire(self) -> None:
        """O_EXCL による原子的ロック: 連続2回の取得は2回目が失敗する。"""
        first = _acquire_lock(self._work_dir)
        second = _acquire_lock(self._work_dir)
        self.assertTrue(first)
        self.assertFalse(second)


# ---------------------------------------------------------------------------
# _build_plan_summary テスト
# ---------------------------------------------------------------------------


class TestBuildPlanSummary(unittest.TestCase):
    """_build_plan_summary の出力をテスト。"""

    def test_empty_summary_for_no_issues(self) -> None:
        """問題がない場合、空文字列を返す。"""
        scan = _make_scan_result()
        summary = _build_plan_summary(scan)
        self.assertEqual(summary, "")

    def test_lint_errors_in_summary(self) -> None:
        """lint_errors がある場合、サマリーに含まれる。"""
        scan = _make_scan_result(lint_errors=5)
        summary = _build_plan_summary(scan)
        self.assertIn("lint errors: 5", summary)

    def test_test_failures_in_summary(self) -> None:
        """test_failures がある場合、サマリーに含まれる。"""
        scan = _make_scan_result(test_failures=2)
        summary = _build_plan_summary(scan)
        self.assertIn("test failures: 2", summary)

    def test_low_coverage_in_summary(self) -> None:
        """カバレッジが低い場合、サマリーに含まれる。"""
        scan = _make_scan_result(coverage_pct=60.0)
        summary = _build_plan_summary(scan)
        self.assertIn("low coverage", summary)

    def test_high_coverage_not_in_summary(self) -> None:
        """カバレッジが十分高い場合、サマリーに含まれない。"""
        scan = _make_scan_result(coverage_pct=95.0)
        summary = _build_plan_summary(scan)
        self.assertNotIn("low coverage", summary)


# ---------------------------------------------------------------------------
# ScopedPermissionHandler テスト
# ---------------------------------------------------------------------------


class TestScopedPermissionHandler(unittest.TestCase):
    """ScopedPermissionHandler の許可/拒否ロジックをテスト。"""

    def setUp(self) -> None:
        self.handler = ScopedPermissionHandler(strict=True)

    def test_allows_ruff(self) -> None:
        """ruff コマンドを許可する。"""
        self.assertTrue(self.handler._evaluate("ruff check ."))

    def test_allows_pytest(self) -> None:
        """pytest コマンドを許可する。"""
        self.assertTrue(self.handler._evaluate("pytest --cov hve/"))

    def test_allows_grep(self) -> None:
        """grep コマンドを許可する。"""
        self.assertTrue(self.handler._evaluate("grep -rn pattern ."))

    def test_denies_rm_rf(self) -> None:
        """rm -rf / は拒否する（CRITICAL）。"""
        self.assertFalse(self.handler._evaluate("rm -rf /"))

    def test_denies_rm_rf_home(self) -> None:
        """rm -rf ~ は拒否する（CRITICAL）。"""
        self.assertFalse(self.handler._evaluate("rm -rf ~"))

    def test_denies_git_push_force(self) -> None:
        """git push --force は拒否する（HIGH）。"""
        self.assertFalse(self.handler._evaluate("git push --force"))

    def test_denies_git_reset_hard(self) -> None:
        """git reset --hard は拒否する（HIGH）。"""
        self.assertFalse(self.handler._evaluate("git reset --hard"))

    def test_denies_az_delete(self) -> None:
        """az resource delete は拒否する（CRITICAL）。"""
        self.assertFalse(self.handler._evaluate("az resource delete --ids /subscriptions/xxx"))

    def test_denies_drop_table(self) -> None:
        """DROP TABLE は拒否する（CRITICAL）。"""
        self.assertFalse(self.handler._evaluate("DROP TABLE users"))

    def test_denied_operations_recorded(self) -> None:
        """拒否した操作が記録される。"""
        self.handler._evaluate("rm -rf /")
        self.assertGreater(len(self.handler.denied_operations), 0)

    def test_clear_denied(self) -> None:
        """denied_operations をクリアできる。"""
        self.handler._evaluate("rm -rf /")
        self.handler.clear_denied()
        self.assertEqual(len(self.handler.denied_operations), 0)

    def test_non_strict_mode_allows_unknown(self) -> None:
        """strict=False の場合、CRITICAL/HIGH 以外は許可する。"""
        handler = ScopedPermissionHandler(strict=False)
        self.assertTrue(handler._evaluate("some unknown command"))

    def test_strict_mode_denies_unknown(self) -> None:
        """strict=True の場合、許可リスト外（unknown）の操作は拒否する。"""
        # setUp では strict=True のハンドラが生成される
        self.assertFalse(self.handler._evaluate("some unknown command xyz"))
        self.assertTrue(
            any("STRICT_DENIED" in op for op in self.handler.denied_operations),
            "拒否理由に STRICT_DENIED が含まれるべき",
        )

    def test_strict_mode_allows_ruff(self) -> None:
        """strict=True の場合でも、許可リスト内のコマンドは許可する。"""
        self.assertTrue(self.handler._evaluate("ruff check ."))

    def test_strict_mode_allows_pytest(self) -> None:
        """strict=True の場合でも、pytest は許可する。"""
        self.assertTrue(self.handler._evaluate("pytest tests/ -q"))

    def test_strict_mode_allows_grep(self) -> None:
        """strict=True の場合でも、grep は許可する。"""
        self.assertTrue(self.handler._evaluate("grep -rn pattern src/"))

    def test_strict_mode_allows_when_tool_name_prefix(self) -> None:
        """_extract_operation が tool_name プレフィックスを付与しても、
        コマンド部分で許可リスト判定が機能する。"""
        # tool_name が "shell" の場合 _extract_operation は "shell ruff check ." のような文字列を返す
        self.assertTrue(self.handler._evaluate("shell ruff check ."))
        self.assertTrue(self.handler._evaluate("bash pytest tests/ -q"))

    def test_strict_mode_denies_write_outside_allowed_paths(self) -> None:
        """strict=True の場合、許可パス外への書き込みは拒否する。"""
        self.assertFalse(self.handler._evaluate("write to /etc/passwd"))
        self.assertTrue(
            any("PATH_DENIED" in op or "STRICT_DENIED" in op for op in self.handler.denied_operations)
        )

    def test_strict_mode_allows_write_to_work(self) -> None:
        """strict=True の場合、work/ への書き込みは許可する。"""
        self.assertTrue(self.handler._evaluate("write work/self-improve/learning.md"))

    def test_permission_request_dict_critical_denied(self) -> None:
        """dict 形式の PermissionRequest でも operation が正しく解釈され、
        CRITICAL 操作は拒否される。"""
        permission_request = {
            "operation": "rm -rf /",
            "reason": "test for critical operation",
        }
        self.assertFalse(self.handler._evaluate(permission_request))

    def test_permission_request_dict_safe_allowed_non_strict(self) -> None:
        """dict 形式の PermissionRequest で安全な操作は non-strict では許可される。"""
        handler = ScopedPermissionHandler(strict=False)
        permission_request = {
            "operation": "read file.py",
            "reason": "inspection",
        }
        self.assertTrue(handler._evaluate(permission_request))


class TestIsSafeCommand(unittest.TestCase):
    """is_safe_command スタンドアロン関数のテスト。"""

    def test_safe_ruff(self) -> None:
        self.assertTrue(is_safe_command("ruff check ."))

    def test_unsafe_rm_rf(self) -> None:
        self.assertFalse(is_safe_command("rm -rf /"))

    def test_unsafe_git_force(self) -> None:
        self.assertFalse(is_safe_command("git push --force origin main"))

    def test_safe_grep(self) -> None:
        self.assertTrue(is_safe_command("grep -rn pattern src/"))


# ---------------------------------------------------------------------------
# _build_verification_result テスト
# ---------------------------------------------------------------------------


class TestBuildVerificationResult(unittest.TestCase):
    """_build_verification_result の出力をテスト。"""

    def test_pass_when_no_issues(self) -> None:
        """問題がない場合、overall='PASS' を返す。"""
        scan = _make_scan_result(quality_score=90)
        result = _build_verification_result(scan, before_score=80)
        self.assertEqual(result["overall"], "PASS")
        self.assertFalse(result["degraded"])

    def test_fail_when_degraded(self) -> None:
        """スコアが悪化した場合、degraded=True かつ overall='FAIL' を返す。"""
        scan = _make_scan_result(quality_score=70)
        result = _build_verification_result(scan, before_score=80)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["overall"], "FAIL")

    def test_fail_when_test_failures(self) -> None:
        """テスト失敗がある場合、overall='FAIL' を返す。"""
        scan = _make_scan_result(quality_score=85, test_failures=2)
        result = _build_verification_result(scan, before_score=80)
        self.assertEqual(result["verification_phases"]["test"], "FAIL")

    def test_lint_fail_when_lint_errors(self) -> None:
        """lint エラーがある場合、lint フェーズが FAIL になる。"""
        scan = _make_scan_result(quality_score=85, lint_errors=3)
        result = _build_verification_result(scan, before_score=80)
        self.assertEqual(result["verification_phases"]["lint"], "FAIL")

    def test_security_fail_on_secret_pattern(self) -> None:
        """シークレットパターンが含まれる場合、security フェーズが FAIL になる。"""
        scan = _make_scan_result(raw_output="password=secret123")
        result = _build_verification_result(scan, before_score=80)
        self.assertEqual(result["verification_phases"]["security"], "FAIL")

    def test_has_required_keys(self) -> None:
        """VerificationResult が必須キーを全て持つ。"""
        scan = _make_scan_result()
        result = _build_verification_result(scan, before_score=80)
        self.assertIn("after_quality_score", result)
        self.assertIn("degraded", result)
        self.assertIn("verification_phases", result)
        self.assertIn("overall", result)
        self.assertIn("notes", result)


# ---------------------------------------------------------------------------
# SDKConfig self_improve フィールドのデフォルト値テスト
# ---------------------------------------------------------------------------


class TestSDKConfigSelfImproveDefaults(unittest.TestCase):
    """SDKConfig の self_improve フィールドのデフォルト値を検証する。"""

    def setUp(self) -> None:
        self.cfg = SDKConfig()

    def test_auto_self_improve_default_false(self) -> None:
        """auto_self_improve はデフォルトで False。"""
        self.assertFalse(self.cfg.auto_self_improve)

    def test_self_improve_max_iterations_default(self) -> None:
        """self_improve_max_iterations のデフォルトは 3。"""
        self.assertEqual(self.cfg.self_improve_max_iterations, 3)

    def test_self_improve_max_tokens_default(self) -> None:
        """self_improve_max_tokens のデフォルトは 500_000。"""
        self.assertEqual(self.cfg.self_improve_max_tokens, 500_000)

    def test_self_improve_max_requests_default(self) -> None:
        """self_improve_max_requests のデフォルトは 50。"""
        self.assertEqual(self.cfg.self_improve_max_requests, 50)

    def test_self_improve_target_scope_default_empty(self) -> None:
        """self_improve_target_scope のデフォルトは空文字列。"""
        self.assertEqual(self.cfg.self_improve_target_scope, "")

    def test_self_improve_skip_default_false(self) -> None:
        """self_improve_skip のデフォルトは False。"""
        self.assertFalse(self.cfg.self_improve_skip)

    def test_no_self_improve_sets_skip(self) -> None:
        """--no-self-improve フラグ相当: self_improve_skip=True で disabled になる。"""
        cfg = SDKConfig(self_improve_skip=True)
        result = run_improvement_loop(cfg)
        self.assertEqual(result["stopped_reason"], "disabled")


# ---------------------------------------------------------------------------
# generate_run_id テスト
# ---------------------------------------------------------------------------


class TestGenerateRunId(unittest.TestCase):
    """generate_run_id の出力形式を検証する。"""

    def test_format_matches_timestamp_uuid(self) -> None:
        """生成される run_id が '<timestamp>-<uuid6>' 形式である。"""
        import re
        run_id = generate_run_id()
        # 例: "20260413T143022-a1b2c3"
        self.assertRegex(run_id, r"^\d{8}T\d{6}-[0-9a-f]{6}$")

    def test_uniqueness(self) -> None:
        """連続して生成した run_id が異なる（UUID部分で衝突しない）。"""
        ids = [generate_run_id() for _ in range(10)]
        self.assertEqual(len(set(ids)), 10)

    def test_run_id_field_default_empty(self) -> None:
        """SDKConfig.run_id のデフォルトは空文字列。"""
        cfg = SDKConfig()
        self.assertEqual(cfg.run_id, "")

    def test_run_id_can_be_set(self) -> None:
        """SDKConfig.run_id に任意の値を設定できる。"""
        cfg = SDKConfig(run_id="20260413T000000-abc123")
        self.assertEqual(cfg.run_id, "20260413T000000-abc123")


# ---------------------------------------------------------------------------
# run_improvement_loop の run_id 伝播テスト
# ---------------------------------------------------------------------------


class TestRunImprovementLoopRunId(unittest.TestCase):
    """run_improvement_loop が run_id に基づいた work_dir を使用することを検証。"""

    def test_run_id_in_work_dir_path(self) -> None:
        """env HVE_RUN_ID が設定されている場合、解決された work_dir にそれが反映される。"""
        cfg = SDKConfig(run_id="20260413T120000-test01", auto_self_improve=True)
        captured_work_dir: dict[str, Path | None] = {"path": None}

        def _capture_acquire_lock(work_dir: Path) -> bool:
            captured_work_dir["path"] = work_dir
            return False  # ロック失敗 → "locked" 早期リターン（ループ不要）

        from hve import split_fork as _sf
        _sf._reset_run_id_cache()
        # patch.dict は終了時に元の値を復元するため、HVE_WORK_ROOT も含めて完全制御する。
        with patch.dict(
            "os.environ",
            {"HVE_RUN_ID": "20260413T120000-test01"},
            clear=False,
        ), patch("self_improve._acquire_lock", side_effect=_capture_acquire_lock):
            # HVE_WORK_ROOT を一時的に除外（patch.dict の clear=False では削除は復元される）
            import os as _os
            _saved_wr = _os.environ.pop("HVE_WORK_ROOT", None)
            try:
                result = run_improvement_loop(cfg)
            finally:
                if _saved_wr is not None:
                    _os.environ["HVE_WORK_ROOT"] = _saved_wr
        _sf._reset_run_id_cache()

        self.assertEqual(result["stopped_reason"], "locked")
        self.assertIsNotNone(captured_work_dir["path"])
        self.assertIn("20260413T120000-test01", str(captured_work_dir["path"]))

    def test_explicit_work_dir_overrides_run_id(self) -> None:
        """work_dir を明示的に渡した場合は run_id よりも優先される。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            cfg = SDKConfig(run_id="20260413T120000-test02", dry_run=True)
            result = run_improvement_loop(cfg, work_dir=work_dir)
            # dry_run=True なので dry_run で返る
            self.assertEqual(result["stopped_reason"], "dry_run")


# ---------------------------------------------------------------------------
# self_improve_scope テスト
# ---------------------------------------------------------------------------


class TestSelfImproveScopeConfig(unittest.TestCase):
    """SDKConfig.self_improve_scope フィールドの検証。"""

    def test_default_scope_workflow(self) -> None:
        """Wave 2: デフォルトの self_improve_scope は "workflow"（Post-DAG のみ実行）。"""
        cfg = SDKConfig()
        self.assertEqual(cfg.self_improve_scope, "workflow")

    def test_valid_scopes(self) -> None:
        """許可値（disabled / step / workflow / ""）はそのまま設定できる。"""
        for scope in ("", "disabled", "step", "workflow"):
            cfg = SDKConfig(self_improve_scope=scope)
            self.assertEqual(cfg.self_improve_scope, scope)

    def test_scope_normalized_case_insensitive(self) -> None:
        """大文字・末尾スペース付きの scope も正規化される。"""
        cfg = SDKConfig(self_improve_scope="Workflow")
        self.assertEqual(cfg.self_improve_scope, "workflow")
        cfg2 = SDKConfig(self_improve_scope=" step ")
        self.assertEqual(cfg2.self_improve_scope, "step")

    def test_invalid_scope_falls_back_to_empty(self) -> None:
        """無効な scope 値は警告を出して空文字列にフォールバックする。"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = SDKConfig(self_improve_scope="invalid-value")
        self.assertEqual(cfg.self_improve_scope, "")
        self.assertTrue(any("invalid-value" in str(warning.message) for warning in w))

    def test_from_env_reads_hve_self_improve_scope(self) -> None:
        """HVE_SELF_IMPROVE_SCOPE 環境変数が from_env() で読まれる。"""
        with patch.dict(os.environ, {"HVE_SELF_IMPROVE_SCOPE": "workflow"}):
            cfg = SDKConfig.from_env()
        self.assertEqual(cfg.self_improve_scope, "workflow")

    def test_from_env_invalid_scope_falls_back(self) -> None:
        """HVE_SELF_IMPROVE_SCOPE に無効値を設定すると '' にフォールバックする。"""
        import warnings
        with patch.dict(os.environ, {"HVE_SELF_IMPROVE_SCOPE": "bad-scope"}):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                cfg = SDKConfig.from_env()
        self.assertEqual(cfg.self_improve_scope, "")
        self.assertTrue(any("bad-scope" in str(warning.message) for warning in w))

    def test_from_env_missing_scope_defaults_workflow(self) -> None:
        """Wave 2: HVE_SELF_IMPROVE_SCOPE が未設定の場合は "workflow" になる。"""
        env = {k: v for k, v in os.environ.items() if k != "HVE_SELF_IMPROVE_SCOPE"}
        with patch.dict(os.environ, env, clear=True):
            cfg = SDKConfig.from_env()
        self.assertEqual(cfg.self_improve_scope, "workflow")


class TestRunImprovementLoopAutoFalse(unittest.TestCase):
    """auto_self_improve=False の場合は scope に関係なく実行されない。"""

    def _run_with_scope(self, scope: str) -> str:
        cfg = SDKConfig(auto_self_improve=False, self_improve_scope=scope)
        result = run_improvement_loop(cfg)
        return result["stopped_reason"]

    def test_disabled_scope_auto_false(self) -> None:
        self.assertEqual(self._run_with_scope("disabled"), "disabled")

    def test_step_scope_auto_false(self) -> None:
        self.assertEqual(self._run_with_scope("step"), "disabled")

    def test_workflow_scope_auto_false(self) -> None:
        self.assertEqual(self._run_with_scope("workflow"), "disabled")

    def test_empty_scope_auto_false(self) -> None:
        self.assertEqual(self._run_with_scope(""), "disabled")


class TestRunImprovementLoopDisabledScope(unittest.TestCase):
    """scope='disabled' の場合は auto_self_improve の値に関係なく実行されない。"""

    def test_disabled_scope_blocks_execution(self) -> None:
        """scope='disabled' は auto_self_improve=True でも実行しない。"""
        cfg = SDKConfig(auto_self_improve=True, self_improve_scope="disabled")
        result = run_improvement_loop(cfg)
        self.assertEqual(result["stopped_reason"], "disabled")


# ---------------------------------------------------------------------------
# _resolve_target_scope_paths テスト
# ---------------------------------------------------------------------------


class TestResolveTargetScopePaths(unittest.TestCase):
    """_resolve_target_scope_paths の単体テスト。"""

    def setUp(self) -> None:
        from self_improve import _resolve_target_scope_paths
        self.resolve = _resolve_target_scope_paths
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir_obj.name
        # 実在パスを準備
        for p in ["src", "docs", "knowledge", "data", "hve"]:
            Path(self.tmpdir, p).mkdir(exist_ok=True)

    def tearDown(self) -> None:
        self._tmpdir_obj.cleanup()

    def test_empty_with_step_outputs(self) -> None:
        result = self.resolve("", ["docs"], "docs/", self.tmpdir)
        self.assertEqual(result, ["docs"])

    def test_step_output_paths_takes_precedence_over_workflow_default(self) -> None:
        """step_output_paths が指定された場合、workflow_default は無視される。"""
        result = self.resolve("", ["src"], "docs", self.tmpdir)
        self.assertEqual(result, ["src"])
        self.assertNotIn("docs", result)

    def test_empty_no_outputs_with_default(self) -> None:
        result = self.resolve("", None, "docs", self.tmpdir)
        self.assertEqual(result, ["docs"])

    def test_empty_no_outputs_no_default(self) -> None:
        result = self.resolve("", None, "", self.tmpdir)
        self.assertEqual(result, [])  # 縮小フォールバック

    def test_wildcard(self) -> None:
        result = self.resolve("*", None, "", self.tmpdir)
        # docs-generated は存在しないため除外される
        self.assertIn("data", result)
        self.assertIn("docs", result)
        self.assertIn("knowledge", result)
        self.assertIn("src", result)
        self.assertNotIn("docs-generated", result)

    def test_wildcard_normalize_fullwidth(self) -> None:
        result = self.resolve("＊", None, "", self.tmpdir)
        self.assertIn("src", result)

    def test_multiple_paths_space(self) -> None:
        result = self.resolve("src hve", None, "", self.tmpdir)
        self.assertEqual(result, ["src", "hve"])

    def test_multiple_paths_comma(self) -> None:
        result = self.resolve("src,hve", None, "", self.tmpdir)
        self.assertEqual(result, ["src", "hve"])

    def test_excludes_work(self) -> None:
        Path(self.tmpdir, "work").mkdir(exist_ok=True)
        result = self.resolve("src work", None, "", self.tmpdir)
        self.assertEqual(result, ["src"])

    def test_dedup(self) -> None:
        result = self.resolve("src src", None, "", self.tmpdir)
        self.assertEqual(result, ["src"])

    def test_rejects_dash_token(self) -> None:
        with self.assertRaises(ValueError):
            self.resolve("src --exclude foo", None, "", self.tmpdir)

    def test_skips_nonexistent(self) -> None:
        result = self.resolve("nonexistent", None, "", self.tmpdir)
        self.assertEqual(result, [])

    def test_step_output_includes_work_excluded(self) -> None:
        Path(self.tmpdir, "work").mkdir(exist_ok=True)
        result = self.resolve("", ["src", "work/cache"], "", self.tmpdir)
        self.assertEqual(result, ["src"])

    def test_dotslash_prefix_stripped(self) -> None:
        """'./src' は 'src' として解決される。"""
        result = self.resolve("./src", None, "", self.tmpdir)
        self.assertEqual(result, ["src"])

    def test_absolute_path_skipped(self) -> None:
        """絶対パスはスキップされる。"""
        result = self.resolve("/etc/passwd", None, "", self.tmpdir)
        self.assertEqual(result, [])

    def test_path_traversal_skipped(self) -> None:
        """'..' を含むパスはスキップされる。"""
        result = self.resolve("../src", None, "", self.tmpdir)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# scan_codebase フィーチャーフラグ分岐テスト
# ---------------------------------------------------------------------------


class TestScanCodebaseFeatureFlag(unittest.TestCase):
    """scan_codebase のフィーチャーフラグ分岐テスト。"""

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "0"})
    @patch("self_improve._run_tool")
    def test_legacy_mode_uses_single_path(self, mock_run: MagicMock) -> None:
        mock_run.return_value = ""
        scan_codebase(target_scope="src/")
        # 旧仕様: ruff check src/ ... という単一パス引数
        first_call_args = mock_run.call_args_list[0].args[0]
        self.assertIn("src/", first_call_args)

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "0"})
    @patch("self_improve._run_tool")
    def test_legacy_mode_no_work_exclude(self, mock_run: MagicMock) -> None:
        """旧仕様では ruff に --exclude work を付与しない。"""
        mock_run.return_value = ""
        scan_codebase(target_scope="src/")
        ruff_args = mock_run.call_args_list[0].args[0]
        self.assertNotIn("--exclude", ruff_args)
        self.assertNotIn("--ignore=work", ruff_args)

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "0"})
    @patch("self_improve._run_tool")
    def test_legacy_mode_no_ignore_work_pytest(self, mock_run: MagicMock) -> None:
        """旧仕様では pytest に --ignore=work を付与しない。"""
        mock_run.return_value = ""
        scan_codebase(target_scope="src/")
        pytest_args = mock_run.call_args_list[1].args[0]
        self.assertNotIn("--ignore=work", pytest_args)

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "1"})
    @patch("self_improve._run_tool")
    def test_new_mode_skips_when_empty(self, mock_run: MagicMock) -> None:
        result = scan_codebase(
            target_scope="",
            step_output_paths=None,
            workflow_default="",
        )
        # スキャンスキップで _run_tool は呼ばれない
        mock_run.assert_not_called()
        self.assertEqual(result["quality_score"], 100)
        self.assertIn("[SCAN SKIPPED]", result["raw_output"])

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "0"})
    @patch("self_improve._run_tool")
    def test_resolved_scope_forces_scoped_scan_when_flag_off(
        self,
        mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = ""
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "docs", "agent")
            target.mkdir(parents=True)
            Path(target, "test_agent.py").write_text(
                "def test_agent():\n    assert True\n",
                encoding="utf-8",
            )
            Path(target, "agent.md").write_text("# Agent\n", encoding="utf-8")
            scan_codebase(
                target_scope="",
                repo_root=repo,
                resolved_scope_paths=["docs/agent"],
            )

        self.assertEqual(mock_run.call_count, 3)
        ruff_args = mock_run.call_args_list[0].args[0]
        pytest_args = mock_run.call_args_list[1].args[0]
        markdown_args = mock_run.call_args_list[2].args[0]
        self.assertIn("docs/agent/test_agent.py", ruff_args)
        self.assertIn("docs/agent/test_agent.py", pytest_args)
        self.assertIn("docs/agent/agent.md", markdown_args)
        self.assertNotIn(".", ruff_args)

    @patch.dict(os.environ, {"HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER": "0"})
    @patch("self_improve._run_tool")
    def test_pytest_no_collection_is_not_pass_evidence(
        self,
        mock_run: MagicMock,
    ) -> None:
        mock_run.side_effect = (
            lambda command, **kwargs: (
                "no tests ran\n[HVE_TOOL_EXIT_CODE=5]"
                if command[0] == "pytest"
                else "[HVE_TOOL_EXIT_CODE=0]"
            )
        )
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "docs", "agent")
            target.mkdir(parents=True)
            Path(target, "test_agent.py").write_text(
                "def test_agent():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["docs/agent"],
            )

        self.assertEqual(result.get("tests_collected"), 0)
        self.assertEqual(result.get("tool_status", {}).get("pytest"), "NO_TESTS")
        verification = _build_verification_result(result, before_score=100)
        self.assertEqual(verification["verification_phases"]["test"], "SKIP")

    @patch("self_improve._run_tool")
    def test_all_skipped_python_suite_is_no_tests(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[0] == "pytest":
                return "2 skipped in 0.01s\n[HVE_TOOL_EXIT_CODE=0]"
            return "[HVE_TOOL_EXIT_CODE=0]"

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            test_file = Path(repo, "src", "test", "agent", "test_agent.py")
            test_file.parent.mkdir(parents=True)
            test_file.write_text(
                "def test_agent():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/test/agent"],
            )

        self.assertEqual(result.get("tests_collected"), 0)
        self.assertEqual(result.get("tests_skipped"), 2)
        self.assertEqual(result.get("tool_status", {}).get("test"), "NO_TESTS")

    @patch("self_improve._run_tool")
    def test_docs_only_aag_verification_can_pass(
        self,
        mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = "[HVE_TOOL_EXIT_CODE=0]"
        with tempfile.TemporaryDirectory() as repo:
            detail = Path(repo, "docs", "agent", "agent-detail-AGT-01.md")
            detail.parent.mkdir(parents=True)
            detail.write_text("# Agent Detail\n", encoding="utf-8")
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["docs/agent/agent-detail-AGT-01.md"],
            )

        verification = _build_verification_result(result, before_score=100)
        self.assertEqual(verification["verification_phases"]["lint"], "SKIP")
        self.assertEqual(verification["verification_phases"]["test"], "SKIP")
        self.assertEqual(
            verification["verification_phases"]["documentation"],
            "PASS",
        )
        self.assertFalse(verification["degraded"])
        self.assertEqual(verification["overall"], "PASS")

    @patch("self_improve._run_tool")
    def test_csharp_scope_uses_dotnet_build_and_test(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[:2] == ["dotnet", "build"]:
                return "Build succeeded.\n[HVE_TOOL_EXIT_CODE=0]"
            if command[:2] == ["dotnet", "test"]:
                return (
                    "Passed: 2, Failed: 0, Skipped: 0, Total: 2\n"
                    "[HVE_TOOL_EXIT_CODE=0]"
                )
            raise AssertionError(f"unexpected tool call: {command}")

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            project = Path(repo, "src", "test", "agent", "AGT-01.Tests")
            project.mkdir(parents=True)
            Path(project, "AGT-01.Tests.csproj").write_text(
                "<Project><ItemGroup><PackageReference "
                "Include=\"Microsoft.NET.Test.Sdk\" /></ItemGroup></Project>",
                encoding="utf-8",
            )
            Path(project, "AgentTests.cs").write_text(
                "public class AgentTests {}\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/test/agent/AGT-01.Tests"],
            )

        commands = [call.args[0] for call in mock_run.call_args_list]
        self.assertTrue(any(command[:2] == ["dotnet", "build"] for command in commands))
        self.assertTrue(any(command[:2] == ["dotnet", "test"] for command in commands))
        self.assertEqual(result.get("tool_status", {}).get("lint"), "PASS")
        self.assertEqual(result.get("tool_status", {}).get("test"), "PASS")
        self.assertEqual(result.get("tests_collected"), 2)

    @patch("self_improve._run_tool")
    def test_mixed_scope_blocks_python_code_without_python_tests(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[0] == "ruff":
                return "[HVE_TOOL_EXIT_CODE=0]"
            if command[:2] == ["dotnet", "build"]:
                return "Build succeeded.\n[HVE_TOOL_EXIT_CODE=0]"
            if command[:2] == ["dotnet", "test"]:
                return (
                    "Passed: 1, Failed: 0, Skipped: 0, Total: 1\n"
                    "[HVE_TOOL_EXIT_CODE=0]"
                )
            if command[0] == "markdownlint":
                return "[HVE_TOOL_EXIT_CODE=0]"
            raise AssertionError(f"unexpected call: {command}")

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            python_impl = Path(repo, "src", "agent", "AGT-01", "agent.py")
            python_impl.parent.mkdir(parents=True)
            python_impl.write_text("VALUE = 1\n", encoding="utf-8")
            csharp = Path(repo, "src", "test", "agent", "AGT-01.Tests")
            csharp.mkdir(parents=True)
            Path(csharp, "AGT-01.Tests.csproj").write_text(
                "<Project><ItemGroup><PackageReference "
                "Include=\"Microsoft.NET.Test.Sdk\" /></ItemGroup></Project>",
                encoding="utf-8",
            )
            Path(csharp, "Tests.cs").write_text(
                "public class Tests {}\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/agent/AGT-01", "src/test/agent/AGT-01.Tests"],
            )

        self.assertEqual(result.get("tool_status", {}).get("pytest"), "NO_TESTS")
        self.assertEqual(result.get("tool_status", {}).get("dotnet_test"), "PASS")
        self.assertEqual(result.get("tool_status", {}).get("test"), "NO_TESTS")

    def test_scope_inventory_excludes_nested_reparse_directory(self) -> None:
        from self_improve import _scope_files

        with tempfile.TemporaryDirectory() as repo:
            scope = Path(repo, "docs", "agent")
            nested = scope / "linked-other-agent"
            nested.mkdir(parents=True)
            (scope / "allowed.md").write_text("# Allowed\n", encoding="utf-8")
            (nested / "escaped.md").write_text("# Escaped\n", encoding="utf-8")

            real_detector = __import__("self_improve")._is_symlink_or_junction

            def _detector(path: Path) -> bool:
                if path == nested:
                    return True
                return real_detector(path)

            with patch(
                "self_improve._is_symlink_or_junction",
                side_effect=_detector,
            ):
                files = _scope_files(Path(repo), ["docs/agent"])

        relative = [path for path, _full in files]
        self.assertEqual(relative, ["docs/agent/allowed.md"])

    @patch("self_improve._run_tool")
    def test_exit_one_without_parseable_count_cannot_pass_required_metric(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[0] == "ruff":
                return "unexpected lint failure\n[HVE_TOOL_EXIT_CODE=1]"
            if command[0] == "pytest":
                return "1 passed in 0.01s\n[HVE_TOOL_EXIT_CODE=0]"
            return "[HVE_TOOL_EXIT_CODE=0]"

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "src", "agent", "AGT-01")
            target.mkdir(parents=True)
            Path(target, "agent.py").write_text("VALUE = 1\n", encoding="utf-8")
            Path(target, "test_agent.py").write_text(
                "def test_agent():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/agent/AGT-01"],
            )

        self.assertEqual(result.get("tool_status", {}).get("lint"), "FAIL")
        self.assertEqual(result["summary"]["lint_errors"], 1)
        from self_improve import _evaluate_criteria, define_task_goal
        criteria = _evaluate_criteria(result, define_task_goal("aagd"))
        by_id = {item["criterion_id"]: item for item in criteria}
        self.assertEqual(by_id["AAGD-BUILD-LINT"]["status"], "FAIL")
        self.assertEqual(
            by_id["AAGD-BUILD-LINT"]["evidence"][0]["status"],
            "FAIL",
        )

    @patch("self_improve._run_tool")
    def test_pytest_exit_one_without_count_is_required_failure(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[0] == "ruff":
                return "[HVE_TOOL_EXIT_CODE=0]"
            if command[0] == "pytest":
                return "unparseable Python test failure\n[HVE_TOOL_EXIT_CODE=1]"
            return "[HVE_TOOL_EXIT_CODE=0]"

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "src", "agent", "AGT-01")
            target.mkdir(parents=True)
            Path(target, "agent.py").write_text("VALUE = 1\n", encoding="utf-8")
            Path(target, "test_agent.py").write_text(
                "def test_agent():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/agent/AGT-01"],
            )

        self.assertEqual(result.get("tool_status", {}).get("test"), "FAIL")
        self.assertGreaterEqual(result["summary"]["test_failures"], 1)
        from self_improve import _evaluate_criteria, define_task_goal
        by_id = {
            item["criterion_id"]: item
            for item in _evaluate_criteria(result, define_task_goal("aagd"))
        }
        self.assertEqual(by_id["AAGD-TESTS"]["status"], "FAIL")
        self.assertEqual(by_id["AAGD-TESTS"]["evidence"][0]["status"], "FAIL")

    @patch("self_improve._run_tool")
    def test_dotnet_test_exit_one_without_count_is_required_failure(
        self,
        mock_run: MagicMock,
    ) -> None:
        def _result(command, **kwargs):
            if command[:2] == ["dotnet", "build"]:
                return "Build succeeded.\n[HVE_TOOL_EXIT_CODE=0]"
            if command[:2] == ["dotnet", "test"]:
                return "unparseable .NET test failure\n[HVE_TOOL_EXIT_CODE=1]"
            raise AssertionError(f"unexpected call: {command}")

        mock_run.side_effect = _result
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "src", "test", "agent", "AGT-01.Tests")
            target.mkdir(parents=True)
            Path(target, "AGT-01.Tests.csproj").write_text(
                "<Project><ItemGroup><PackageReference "
                "Include=\"Microsoft.NET.Test.Sdk\" /></ItemGroup></Project>",
                encoding="utf-8",
            )
            Path(target, "Tests.cs").write_text(
                "public class Tests {}\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/test/agent/AGT-01.Tests"],
            )

        self.assertEqual(result.get("tool_status", {}).get("test"), "FAIL")
        self.assertGreaterEqual(result["summary"]["test_failures"], 1)
        from self_improve import _evaluate_criteria, define_task_goal
        by_id = {
            item["criterion_id"]: item
            for item in _evaluate_criteria(result, define_task_goal("aagd"))
        }
        self.assertEqual(by_id["AAGD-TESTS"]["status"], "FAIL")
        self.assertEqual(by_id["AAGD-TESTS"]["evidence"][0]["status"], "FAIL")


# ---------------------------------------------------------------------------
# FR-CLI-64: scan_codebase による security_status の設定
# ---------------------------------------------------------------------------


class TestScanSecurityStatus(unittest.TestCase):
    """解決済み scope の対象ファイルへ秘密情報パターン検査を行い、
    結果を ScanResult.security_status へ設定することを検証する（FR-CLI-64）。
    """

    @staticmethod
    def _write(repo: str, relative: str, text: str) -> None:
        path = Path(repo, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    @patch("self_improve._run_tool")
    def test_security_status_pass_without_secret(self, mock_run: MagicMock) -> None:
        mock_run.return_value = "[HVE_TOOL_EXIT_CODE=0]"
        with tempfile.TemporaryDirectory() as repo:
            self._write(repo, "src/api/handler.py", "def handler():\n    return 1\n")
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/api"],
            )
        self.assertEqual(result.get("security_status"), "PASS")

    @patch("self_improve._run_tool")
    def test_security_status_fail_on_secret_in_scope_file(
        self, mock_run: MagicMock,
    ) -> None:
        mock_run.return_value = "[HVE_TOOL_EXIT_CODE=0]"
        with tempfile.TemporaryDirectory() as repo:
            self._write(
                repo,
                "src/api/handler.py",
                'TOKEN = "sk-sample-not-a-real-key"\n',
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/api"],
            )
        self.assertEqual(result.get("security_status"), "FAIL")

    @patch("self_improve._run_tool")
    def test_security_status_ignores_out_of_scope_file(
        self, mock_run: MagicMock,
    ) -> None:
        """scope 外のパターンを停止理由にしない。"""
        mock_run.return_value = "[HVE_TOOL_EXIT_CODE=0]"
        with tempfile.TemporaryDirectory() as repo:
            self._write(repo, "src/api/handler.py", "def handler():\n    return 1\n")
            self._write(
                repo,
                "src/other/legacy.py",
                'TOKEN = "sk-sample-not-a-real-key"\n',
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/api"],
            )
        self.assertEqual(result.get("security_status"), "PASS")

    def test_empty_scan_result_security_status_is_skip(self) -> None:
        """未検査を PASS としてはならない（fail-open 防止）。"""
        from self_improve import _empty_scan_result
        self.assertEqual(_empty_scan_result("no_scope").get("security_status"), "SKIP")


# ---------------------------------------------------------------------------
# FR-CLI-65: coverage 成功条件の criterion 化
# ---------------------------------------------------------------------------


class TestCoverageCriterion(unittest.TestCase):
    """success_criteria のカバレッジ 70% 以上を決定的に評価する（FR-CLI-65）。"""

    @staticmethod
    def _coverage_definition(workflow_id: str) -> dict[str, Any]:
        from self_improve import _criterion_definitions, define_task_goal
        for item in _criterion_definitions(define_task_goal(workflow_id)):
            evaluation = item.get("evaluation")
            if isinstance(evaluation, dict) and evaluation.get("metric") == "coverage_pct":
                return item
        raise AssertionError(f"{workflow_id} に coverage_pct criterion がありません")

    @staticmethod
    def _scan_with_coverage(coverage_pct: float, test_status: str = "PASS"):
        scan = _make_scan_result(quality_score=100, coverage_pct=coverage_pct)
        raw = cast(dict[str, Any], scan)
        raw["tool_status"] = {
            "ruff": "PASS",
            "pytest": test_status,
            "dotnet_build": "SKIP",
            "dotnet_test": "NO_TESTS",
            "markdownlint": "PASS",
            "lint": "PASS",
            "test": test_status,
            "documentation": "PASS",
        }
        raw["metric_status"] = {
            "lint_errors": "PASS",
            "test_failures": test_status,
            "doc_issues": "PASS",
            "coverage_pct": test_status,
        }
        return scan

    def test_asdw_web_and_adfdv_declare_coverage_criterion(self) -> None:
        for workflow_id in ("asdw-web", "adfdv"):
            with self.subTest(workflow_id=workflow_id):
                definition = self._coverage_definition(workflow_id)
                self.assertTrue(definition.get("required_for_done"))
                self.assertEqual(definition["evaluation"]["operator"], "gte")
                self.assertEqual(definition["evaluation"]["expected"], 70)
                self.assertEqual(
                    definition["evidence_required"]["reference"],
                    "scan.summary.coverage_pct",
                )

    def _coverage_result(self, workflow_id: str, scan) -> dict[str, Any]:
        from self_improve import _evaluate_criteria, define_task_goal
        criterion_id = self._coverage_definition(workflow_id)["criterion_id"]
        for item in _evaluate_criteria(scan, define_task_goal(workflow_id)):
            if item["criterion_id"] == criterion_id:
                return item
        raise AssertionError(f"{criterion_id} が評価されていません")

    def test_coverage_criterion_passes_at_threshold(self) -> None:
        result = self._coverage_result("asdw-web", self._scan_with_coverage(70.0))
        self.assertEqual(result["status"], "PASS")

    def test_coverage_criterion_fails_below_threshold(self) -> None:
        result = self._coverage_result("asdw-web", self._scan_with_coverage(69.9))
        self.assertEqual(result["status"], "FAIL")

    def test_coverage_criterion_blocked_when_tests_not_executed(self) -> None:
        """test 未実行時の coverage 0.0 を FAIL として扱わない。"""
        scan = self._scan_with_coverage(0.0, test_status="NO_TESTS")
        result = self._coverage_result("adfdv", scan)
        self.assertEqual(result["status"], "BLOCKED")

    @patch("self_improve._run_tool")
    def test_scan_codebase_sets_coverage_metric_status(
        self, mock_run: MagicMock,
    ) -> None:
        """metric_status.coverage_pct が test ツールの実行状態を反映する。"""
        mock_run.side_effect = lambda command, **kwargs: (
            "no tests ran\n[HVE_TOOL_EXIT_CODE=5]"
            if command[0] == "pytest"
            else "[HVE_TOOL_EXIT_CODE=0]"
        )
        with tempfile.TemporaryDirectory() as repo:
            target = Path(repo, "src", "api")
            target.mkdir(parents=True)
            Path(target, "test_handler.py").write_text(
                "def test_handler():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_codebase(
                repo_root=repo,
                resolved_scope_paths=["src/api"],
            )
        metric_status = result.get("metric_status", {})
        self.assertEqual(
            metric_status.get("coverage_pct"),
            result.get("tool_status", {}).get("test"),
        )
        self.assertEqual(metric_status.get("coverage_pct"), "NO_TESTS")


if __name__ == "__main__":
    unittest.main()
