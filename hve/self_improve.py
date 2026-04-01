"""self_improve.py — 自己改善ループ（Self-Improve）コアロジック

実行パス A（hve ローカル）:
    python -m hve orchestrate --workflow <id>
    → StepRunner.run_step() Phase 4 として自動実行（auto_self_improve=True）
    → --no-self-improve で無効化可能

実行パス B（Issue → Copilot Coding Agent）:
    GitHub Issue (.github/ISSUE_TEMPLATE/self-improve.yml) 作成
    → Copilot 自動アサイン
    → AGENTS.md §2.2 に従い Sub Issue を 15分以内に分割
    → 各 Sub Issue で改善 → Verification Loop → 学習記録

設計方針:
    - 全関数に TypedDict ベースの引数・戻り値型を定義
    - scan_codebase は subprocess でツールを実行（LLM 統合評価）
    - ScopedPermissionHandler で操作スコープを制限
    - work/.self-improve-lock でローカル競合制御
    - artifacts/learning-NNN.md に学習ログを AGENTS.md §4.1 準拠で保存
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# quality_score 閾値（この値以上で改善完了とみなす）
DEFAULT_QUALITY_THRESHOLD: int = 80

# スコア計算のペナルティ重み
_LINT_ERROR_PENALTY: int = 2        # lint エラー 1件あたりのペナルティ
_MAX_LINT_PENALTY: int = 40         # lint ペナルティの上限
_TEST_FAILURE_PENALTY: int = 10     # テスト失敗 1件あたりのペナルティ
_MAX_TEST_PENALTY: int = 40         # テスト失敗ペナルティの上限
_MAX_DOC_PENALTY: int = 20          # ドキュメント問題ペナルティの上限

# 学習サマリーの最大文字数
LEARNING_SUMMARY_MAX_LENGTH: int = 1000

# ruff エラーコードのパターン（ファイルパス:行:列: コード形式）
# ruff のコードは 1〜3 文字のプレフィックス + 数字（例: E501, W291, RUF100, UP006, I001）
_RUFF_ERROR_PATTERN: re.Pattern[str] = re.compile(r":\d+:\d+:\s+[A-Z]+\d+\b")

# pytest 失敗サマリー行のパターン（例: "1 failed, 5 passed" / "2 errors"）
_PYTEST_FAILED_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+failed\b")
_PYTEST_ERROR_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+errors?\b")


# ---------------------------------------------------------------------------
# TypedDict 型定義
# ---------------------------------------------------------------------------


class ScanIssue(TypedDict):
    """スキャンで検出された個別の問題。"""
    category: str       # "code_quality" | "test" | "documentation"
    severity: str       # "critical" | "major" | "minor"
    file: str           # 対象ファイルパス
    description: str    # 問題の説明
    suggestion: str     # 修正提案


class ScanSummary(TypedDict):
    """スキャン結果サマリー。"""
    lint_errors: int
    test_failures: int
    coverage_pct: float
    doc_issues: int


class ScanResult(TypedDict):
    """scan_codebase の戻り値。"""
    quality_score: int          # 0〜100
    issues: List[ScanIssue]
    summary: ScanSummary
    raw_output: str             # ツール実行の生テキスト出力


class VerificationResult(TypedDict):
    """verify_improvements の戻り値。"""
    after_quality_score: int
    degraded: bool
    verification_phases: Dict[str, str]   # phase名 → "PASS"|"FAIL"|"SKIP"
    overall: str                          # "PASS" | "FAIL"
    notes: str


class ImprovementRecord(TypedDict):
    """1イテレーションの改善記録。"""
    iteration: int
    before_score: int
    after_score: int
    degraded: bool
    plan_summary: str
    verification: VerificationResult
    elapsed_seconds: float


class SelfImproveResult(TypedDict):
    """run_improvement_loop の戻り値。"""
    iterations_completed: int
    final_score: int
    records: List[ImprovementRecord]
    stopped_reason: str     # "threshold_reached" | "no_improvement_needed" | "degradation" | "max_iterations" | "cost_limit" | "dry_run" | "disabled" | "locked"


# ---------------------------------------------------------------------------
# ツール実行
# ---------------------------------------------------------------------------


def _run_tool(cmd: List[str], cwd: Optional[str] = None, timeout: int = 120) -> str:
    """サブプロセスでツールを実行し、stdout + stderr を結合して返す。

    エラー終了でも出力を返す（lint ツールは違反があると非 0 終了するため）。
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        return f"[TOOL NOT FOUND] {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] {cmd[0]} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] {cmd[0]}: {exc}"


def scan_codebase(
    target_scope: str = "",
    repo_root: Optional[str] = None,
) -> ScanResult:
    """Phase 4a: ruff / pytest --cov / markdownlint を subprocess 実行し、
    結果を構造化して返す。

    LLM 統合評価は run_improvement_loop 内で別途実施するため、
    この関数は純粋にツール実行結果を収集する役割を担う。

    Args:
        target_scope: 改善対象スコープ（空 = 全体）。
        repo_root: リポジトリルートディレクトリ。None の場合は現在のディレクトリ。

    Returns:
        ScanResult 型の辞書。
    """
    cwd = repo_root or "."
    scope_path = target_scope.strip() or "."

    # ruff チェック
    ruff_output = _run_tool(
        ["ruff", "check", scope_path, "--output-format", "text"],
        cwd=cwd,
    )

    # pytest --cov（dry_run 対応: pytest がなければ空出力）
    # scope_path を --cov と収集対象の両方に指定してスコープを絞る
    pytest_output = _run_tool(
        ["pytest", scope_path, "--cov", scope_path, "--cov-report=term-missing", "-q", "--tb=short"],
        cwd=cwd,
        timeout=180,
    )

    # markdownlint（インストールされていない場合はスキップ）
    md_output = _run_tool(
        ["markdownlint", "**/*.md", "--ignore", "node_modules"],
        cwd=cwd,
    )

    raw_output = "\n".join([
        "=== ruff ===",
        ruff_output,
        "=== pytest --cov ===",
        pytest_output,
        "=== markdownlint ===",
        md_output,
    ])

    # ruff: 精確なエラーコードパターンでカウント（false positive を排除）
    lint_errors = len(_RUFF_ERROR_PATTERN.findall(ruff_output))

    # pytest: 失敗サマリー行から件数を抽出（FAILED / ERROR の単独出現を避ける）
    test_failures = 0
    for m in _PYTEST_FAILED_LINE_PATTERN.finditer(pytest_output):
        test_failures += int(m.group(1))
    for m in _PYTEST_ERROR_LINE_PATTERN.finditer(pytest_output):
        test_failures += int(m.group(1))

    doc_issues = md_output.count(".md:")

    # coverage_pct の抽出
    coverage_pct = 0.0
    for line in pytest_output.splitlines():
        if "TOTAL" in line:
            parts = line.split()
            for part in reversed(parts):
                if part.endswith("%"):
                    try:
                        coverage_pct = float(part.rstrip("%"))
                    except ValueError:
                        pass
                    break

    # 初期品質スコア（LLM 統合評価前の粗算）
    raw_score = (
        100
        - min(lint_errors * _LINT_ERROR_PENALTY, _MAX_LINT_PENALTY)
        - min(test_failures * _TEST_FAILURE_PENALTY, _MAX_TEST_PENALTY)
        - min(doc_issues, _MAX_DOC_PENALTY)
    )
    quality_score = max(0, min(100, raw_score))

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
# ロック制御
# ---------------------------------------------------------------------------


def _acquire_lock(work_dir: Path) -> bool:
    """work/.self-improve-lock ファイルで排他制御する。

    `os.open()` と `O_CREAT | O_EXCL` を使った原子的ロック取得。
    並行実行時に両方がロックを取得してしまう競合（race）を防ぐ。

    Returns:
        True: ロック取得成功、False: 既にロックが存在する。
    """
    import os
    lock_file = work_dir / ".self-improve-lock"
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        # O_CREAT | O_EXCL: ファイルが存在する場合は FileExistsError を投げる（原子的）
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(time.time()).encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _release_lock(work_dir: Path) -> None:
    """ロックファイルを削除する。"""
    lock_file = work_dir / ".self-improve-lock"
    try:
        lock_file.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 学習ログ記録
# ---------------------------------------------------------------------------


def record_learning(
    work_dir: Path,
    iteration: int,
    record: ImprovementRecord,
) -> None:
    """イテレーションごとの学習ログを
    work/Issue-<N>/artifacts/learning-{iteration:03d}.md に保存する。

    AGENTS.md §4.1 準拠: 既存ファイルを削除してから新規作成。

    並列安全性:
      - 各呼び出しは固有の work_dir と iteration 番号を持つため、
        並列ステップ間でのファイル衝突は発生しない。
      - _acquire_lock() / _release_lock() によるディレクトリレベルのロックで
        同一 work_dir への同時アクセスも防止される。
    """
    artifacts_dir = work_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    learning_file = artifacts_dir / f"learning-{iteration:03d}.md"

    # §4.1: 既存ファイルを削除してから新規作成
    if learning_file.exists():
        learning_file.unlink()

    verification = record["verification"]
    phases_lines = "\n".join(
        f"- {phase}: {status}"
        for phase, status in verification.get("verification_phases", {}).items()
    )

    content = f"""# 自己改善ループ 学習ログ — イテレーション {iteration:03d}

**記録日時**: {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

---

## スコア変化

| 指標 | 改善前 | 改善後 |
|------|--------|--------|
| quality_score | {record["before_score"]} | {record["after_score"]} |
| デグレード検知 | — | {"⚠️ あり" if record["degraded"] else "✅ なし"} |

## 改善計画サマリー

{record["plan_summary"]}

## Verification Loop 結果（§10.1 準拠）

{phases_lines}

- **総合判定**: {verification.get("overall", "N/A")}
- **補足**: {verification.get("notes", "")}

## 処理時間

{record["elapsed_seconds"]:.1f} 秒
"""
    learning_file.write_text(content, encoding="utf-8")


def get_learning_summary(work_dir: Path, iteration: int) -> str:
    """前回の学習ログサマリーを取得する（additional_prompt への注入用）。

    Args:
        work_dir: 作業ディレクトリ。
        iteration: 直前のイテレーション番号（これより前のファイルを検索）。

    Returns:
        学習サマリー文字列（ファイルが存在しない場合は空文字列）。
    """
    if iteration <= 0:
        return ""
    prev_file = work_dir / "artifacts" / f"learning-{iteration:03d}.md"
    if not prev_file.exists():
        return ""
    try:
        content = prev_file.read_text(encoding="utf-8")
        # LEARNING_SUMMARY_MAX_LENGTH 文字を要約として返す
        return content[:LEARNING_SUMMARY_MAX_LENGTH] + ("..." if len(content) > LEARNING_SUMMARY_MAX_LENGTH else "")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# メインループ
# ---------------------------------------------------------------------------


def run_improvement_loop(
    config: Any,
    work_dir: Optional[Path] = None,
    repo_root: Optional[str] = None,
) -> SelfImproveResult:
    """自己改善ループのエントリポイント。

    コスト上限（max_tokens / max_requests）は現フェーズでは
    イテレーション数でラフに制御する（per-request カウンターは
    Copilot SDK が公開した時点で実装を拡充する）。

    Args:
        config: SDKConfig インスタンス。
        work_dir: 学習ログ保存ディレクトリ（None の場合は work/.self-improve/）。
        repo_root: リポジトリルートディレクトリ。

    Returns:
        SelfImproveResult 型の辞書。
    """
    if config.dry_run:
        return SelfImproveResult(
            iterations_completed=0,
            final_score=0,
            records=[],
            stopped_reason="dry_run",
        )

    if config.self_improve_skip or not config.auto_self_improve:
        return SelfImproveResult(
            iterations_completed=0,
            final_score=0,
            records=[],
            stopped_reason="disabled",
        )

    _work_dir = work_dir or Path("work/self-improve")

    # ロック取得（競合制御）
    if not _acquire_lock(_work_dir):
        return SelfImproveResult(
            iterations_completed=0,
            final_score=0,
            records=[],
            stopped_reason="locked",
        )

    records: List[ImprovementRecord] = []
    stopped_reason = "max_iterations"
    current_score = 0

    try:
        for iteration in range(1, config.self_improve_max_iterations + 1):
            iter_start = time.time()

            # Phase 4a: コードベーススキャン
            scan = scan_codebase(
                target_scope=config.self_improve_target_scope,
                repo_root=repo_root,
            )
            before_score = scan["quality_score"]
            current_score = before_score

            # Phase 4b: 改善が必要かチェック
            # quality_score >= DEFAULT_QUALITY_THRESHOLD で完了
            if before_score >= DEFAULT_QUALITY_THRESHOLD and not scan["summary"]["test_failures"]:
                stopped_reason = "threshold_reached"
                break

            # 改善実行フェーズ（Phase 4c）は Copilot SDK セッション内で実施
            # dry_run でないが SDK が無い環境では計画のみ記録して終了
            plan_summary = _build_plan_summary(scan)
            if not plan_summary:
                stopped_reason = "no_improvement_needed"
                break

            # Phase 4d: 改善後検証（改善実行後を想定した暫定検証）
            after_scan = scan_codebase(
                target_scope=config.self_improve_target_scope,
                repo_root=repo_root,
            )
            after_score = after_scan["quality_score"]

            degraded = (
                after_score < before_score
                or after_scan["summary"]["test_failures"] > scan["summary"]["test_failures"]
            )

            verification = _build_verification_result(after_scan, before_score)

            # Phase 4e: 学習ログ記録
            record = ImprovementRecord(
                iteration=iteration,
                before_score=before_score,
                after_score=after_score,
                degraded=degraded,
                plan_summary=plan_summary,
                verification=verification,
                elapsed_seconds=time.time() - iter_start,
            )
            records.append(record)
            record_learning(_work_dir, iteration, record)
            current_score = after_score

            # Phase 4f: デグレード検知 → 即時停止
            if degraded:
                stopped_reason = "degradation"
                break

    finally:
        _release_lock(_work_dir)

    return SelfImproveResult(
        iterations_completed=len(records),
        final_score=current_score,
        records=records,
        stopped_reason=stopped_reason,
    )


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _build_plan_summary(scan: ScanResult) -> str:
    """スキャン結果から簡易改善計画サマリーを生成する。"""
    summary = scan["summary"]
    parts: List[str] = []
    if summary["lint_errors"]:
        parts.append(f"lint errors: {summary['lint_errors']}")
    if summary["test_failures"]:
        parts.append(f"test failures: {summary['test_failures']}")
    if summary["doc_issues"]:
        parts.append(f"doc issues: {summary['doc_issues']}")
    if 0 < summary["coverage_pct"] < 70:
        parts.append(f"low coverage: {summary['coverage_pct']:.1f}%")
    return ", ".join(parts)


def _build_verification_result(
    after_scan: ScanResult,
    before_score: int,
) -> VerificationResult:
    """scan 結果から VerificationResult を構築する。"""
    summary = after_scan["summary"]
    raw = after_scan["raw_output"]

    build_pass = "[TOOL NOT FOUND]" not in raw and "[ERROR]" not in raw
    lint_pass = summary["lint_errors"] == 0
    test_pass = summary["test_failures"] == 0
    security_pass = not any(
        pat in raw
        for pat in ["sk-", "password=", "connectionstring=", "Bearer ", "api_key"]
    )

    phases = {
        "build": "PASS" if build_pass else "FAIL",
        "lint": "PASS" if lint_pass else "FAIL",
        "test": "PASS" if test_pass else "FAIL",
        "security": "PASS" if security_pass else "FAIL",
        "diff": "SKIP",
    }

    degraded = after_scan["quality_score"] < before_score or not test_pass
    overall = "PASS" if not degraded and all(v != "FAIL" for v in phases.values()) else "FAIL"

    return VerificationResult(
        after_quality_score=after_scan["quality_score"],
        degraded=degraded,
        verification_phases=phases,
        overall=overall,
        notes="",
    )
