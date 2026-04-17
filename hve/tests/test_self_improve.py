"""test_self_improve.py — self_improve モジュールのユニット・統合テスト

テスト方針:
- scan_codebase は subprocess をモックして実行
- run_improvement_loop は dry_run=True モードで統合テスト
- ScopedPermissionHandler の許可/拒否ロジックをユニットテスト
- record_learning の学習ログ保存（tmp ディレクトリ使用）
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig, generate_run_id
from self_improve import (
    ScanResult,
    ScanSummary,
    ImprovementRecord,
    VerificationResult,
    SelfImproveResult,
    scan_codebase,
    record_learning,
    get_learning_summary,
    run_improvement_loop,
    _acquire_lock,
    _release_lock,
    _build_plan_summary,
    _build_verification_result,
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
        """ruff の出力から lint_errors が正しくカウントされる（精確な ruff フォーマット、複数文字コード対応）。"""
        # ruff の実際の出力形式: path/file.py:line:col: CODE message
        # 単文字プレフィックス (E501, W291) と複数文字プレフィックス (RUF100, UP006, I001) の両方を含む
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
        """pytest の出力から test_failures が正しくカウントされる（サマリー行形式）。"""
        # pytest の実際のサマリー行: "1 failed, 5 passed in 0.12s"
        mock_run.side_effect = lambda cmd, **kw: (
            "FAILED tests/test_foo.py::test_bar - AssertionError\n1 failed, 5 passed in 0.12s"
            if "pytest" in cmd
            else ""
        )
        result = scan_codebase()
        self.assertEqual(result["summary"]["test_failures"], 1)

    @patch("self_improve._run_tool")
    def test_test_errors_plural_counted(self, mock_run: MagicMock) -> None:
        """pytest の出力から test_failures が複数形 "errors" でも正しくカウントされる。"""
        mock_run.side_effect = lambda cmd, **kw: (
            "2 errors in 0.12s"
            if "pytest" in cmd
            else ""
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
        """pytest --cov の TOTAL 行からカバレッジ率が抽出される。"""
        pytest_output = (
            "Name       Stmts   Miss  Cover\n"
            "TOTAL        100     10    90%\n"
        )
        mock_run.side_effect = lambda cmd, **kw: pytest_output if "pytest" in cmd else ""
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

    def test_auto_self_improve_default_true(self) -> None:
        """auto_self_improve はデフォルトで True。"""
        self.assertTrue(self.cfg.auto_self_improve)

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
        """run_id が設定されている場合、内部解決された work_dir にそれが反映される。"""
        cfg = SDKConfig(run_id="20260413T120000-test01")
        captured_work_dir: dict[str, Path | None] = {"path": None}

        def _capture_acquire_lock(work_dir: Path) -> bool:
            captured_work_dir["path"] = work_dir
            return False  # ロック失敗 → "locked" 早期リターン（ループ不要）

        with patch("self_improve._acquire_lock", side_effect=_capture_acquire_lock):
            result = run_improvement_loop(cfg)

        # _acquire_lock が False を返した場合は "locked" で返る
        self.assertEqual(result["stopped_reason"], "locked")
        self.assertIsNotNone(captured_work_dir["path"])
        self.assertIn(cfg.run_id, str(captured_work_dir["path"]))

    def test_explicit_work_dir_overrides_run_id(self) -> None:
        """work_dir を明示的に渡した場合は run_id よりも優先される。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            cfg = SDKConfig(run_id="20260413T120000-test02", dry_run=True)
            result = run_improvement_loop(cfg, work_dir=work_dir)
            # dry_run=True なので dry_run で返る
            self.assertEqual(result["stopped_reason"], "dry_run")


if __name__ == "__main__":
    unittest.main()
