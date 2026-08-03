"""self_improve.py — 自己改善ループ（Self-Improve）コアロジック

実行パス A（hve ローカル）:
    python -m hve orchestrate --workflow <id>
    → StepRunner.run_step() Phase 4 として自動実行（auto_self_improve=True）
    → --no-self-improve で無効化可能

実行パス B（Issue → Copilot cloud agent）:
    GitHub Issue (.github/ISSUE_TEMPLATE/self-improve.yml) 作成
    → Copilot 自動アサイン
    → .github/skills/task-dag-planning/SKILL.md §2.2 に従い Sub Issue を 1責務・最小コンテキスト（task_scope=single）単位に分割
    → 各 Sub Issue で改善 → Verification Loop → 学習記録

設計方針:
    - 全関数に TypedDict ベースの引数・戻り値型を定義
    - scan_codebase は subprocess でツールを実行（LLM 統合評価）
    - ScopedPermissionHandler で操作スコープを制限
    - work_dir/.self-improve-lock でローカル競合制御
    - artifacts/learning-NNN.md に学習ログを Skill work-artifacts-layout §4.1 準拠で保存
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any, Dict, List, NotRequired, Optional, TypedDict

try:
    from .config import generate_run_id
except ImportError:
    from config import generate_run_id  # type: ignore[no-redef]


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

# Copilot SDK mutation は必ず有限時間で終了させる。config.timeout_seconds が
# これより大きい場合も Self-Improve 1 mutation の上限はこの値に制限する。
_MUTATION_TIMEOUT_SECONDS: float = 900.0

_MUTATION_STATUSES = {
    "MUTATED",
    "PARTIAL_FAILURE",
    "IMPROVEMENT_NOT_NEEDED",
}
_MUTATION_RESPONSE_FIELDS = {
    "status",
    "changed_files",
    "failed_changes",
    "no_change_reason",
    "response_summary",
}
_CRITERION_EVALUATOR_TYPES = {
    "schema",
    "rule",
    "tool-result",
    "test",
    "human-approval",
}
_EVIDENCE_KINDS = {
    "field-value",
    "tool-result",
    "test-result",
    "approval",
    "file-diff",
}
_EVALUATOR_EVIDENCE_KIND = {
    "schema": "field-value",
    "rule": "field-value",
    "tool-result": "tool-result",
    "test": "test-result",
    "human-approval": "approval",
}

# ruff エラーコードのパターン（ファイルパス:行:列: コード形式）
# ruff のコードは 1〜3 文字のプレフィックス + 数字（例: E501, W291, RUF100, UP006, I001）
_RUFF_ERROR_PATTERN: re.Pattern[str] = re.compile(r":\d+:\d+:\s+[A-Z]+\d+\b")

# pytest 失敗サマリー行のパターン（例: "1 failed, 5 passed" / "2 errors"）
_PYTEST_FAILED_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+failed\b")
_PYTEST_ERROR_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+errors?\b")
_PYTEST_EXECUTED_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d+)\s+(?:passed|failed)\b"
)
_PYTEST_SKIPPED_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d+)\s+(?:skipped|xfailed|xpassed)\b"
)
_DOTNET_PASSED_PATTERN: re.Pattern[str] = re.compile(
    r"\bPassed:\s*(\d+)\b", re.IGNORECASE
)
_DOTNET_FAILED_PATTERN: re.Pattern[str] = re.compile(
    r"\bFailed:\s*(\d+)\b", re.IGNORECASE
)
_DOTNET_SKIPPED_PATTERN: re.Pattern[str] = re.compile(
    r"\bSkipped:\s*(\d+)\b", re.IGNORECASE
)
_DOTNET_ERROR_PATTERN: re.Pattern[str] = re.compile(
    r"\berror\s+(?:[A-Z]{1,8}\d{2,}|MSB\d+|NETSDK\d+)\b",
    re.IGNORECASE,
)
_TOOL_EXIT_CODE_PATTERN: re.Pattern[str] = re.compile(
    r"\[HVE_TOOL_EXIT_CODE=(?P<code>-?\d+)\]"
)

# ---------------------------------------------------------------------------
# ゴール自動検索用マッピング定数
# ---------------------------------------------------------------------------

# ワークフロー → 代表 Custom Agent ファイル名リスト
# （workflow_registry.py の custom_agent 設定から最初の 2 件を採用）
_WORKFLOW_AGENT_MAP: Dict[str, List[str]] = {
    "aas":      ["Arch-ApplicationAnalytics.agent.md",
                 "Arch-ArchitectureCandidateAnalyzer.agent.md"],
    "aad-web":  ["Arch-UI-List.agent.md",
                 "Arch-Microservice-ServiceDetail.agent.md"],
    "asdw-web": ["Dev-Microservice-Azure-ServiceCoding-AzureFunctions.agent.md",
                 "Dev-Microservice-Azure-ComputeDesign.agent.md"],
    "adfd":      ["Arch-Dataflow-AppSpec.agent.md",
                 "Arch-Dataflow-MonitoringDesign.agent.md",
                 "Arch-Dataflow-TDD-TestSpec.agent.md"],
    "adfdv":     ["Dev-Dataflow-DataServiceSelect.agent.md",
                 "Dev-Dataflow-DataDeploy.agent.md",
                 "Dev-Dataflow-FunctionsDeploy.agent.md"],
    "aag":      ["Arch-AIAgentDesign-Step1.agent.md", "Arch-AIAgentDesign-Step2.agent.md", "Arch-AIAgentDesign-Step3.agent.md"],
    "aagd":     ["Dev-Microservice-Azure-AgentCoding.agent.md"],
    "akm":      ["KnowledgeManager.agent.md"],
    "aqod":     ["QA-DocConsistency.agent.md"],
    "adoc":     ["Doc-ArchOverview.agent.md",
                 "Doc-FileSummary.agent.md"],
}

# ワークフロー → 参照 .github/skills/ サブパス
_WORKFLOW_SKILLS_MAP: Dict[str, List[str]] = {
    "aas":      ["planning/task-dag-planning",
                 "planning/architecture-questionnaire"],
    "aad-web":  ["planning/task-dag-planning",
                 "planning/microservice-design-guide"],
    "asdw-web": ["planning/microservice-design-guide"],
    "adfd":      ["planning/dataflow-design-guide"],
    "adfdv":     ["planning/dataflow-design-guide",
                 "testing/test-strategy-template"],
    "aag":      ["planning/task-dag-planning"],
    "aagd":     ["testing/test-strategy-template"],
    "akm":      ["planning/knowledge-management"],
    "aqod":     ["planning/knowledge-lookup"],
    "adoc":     ["planning/task-dag-planning"],
}

# ワークフロー → 参照 docs/ ファイル/ディレクトリパス
# （存在しない場合は skip するため推測記載でも安全）
_WORKFLOW_DOCS_MAP: Dict[str, List[str]] = {
    "aas":      ["docs/catalog/use-case-catalog.md",
                 "docs/catalog/app-catalog.md"],
    "aad-web":  ["docs/catalog/app-catalog.md"],
    "asdw-web": ["docs/services"],
    "adfd":      ["docs/dataflow"],
    "adfdv":     ["docs/dataflow"],
    "aag":      ["docs/agent"],
    "aagd":     ["docs/agent"],
    "akm":      [],
    "aqod":     [],
    "adoc":     ["docs/catalog"],
}

# ワークフロー → 参照 knowledge/ D-class プレフィックスリスト
_WORKFLOW_KNOWLEDGE_MAP: Dict[str, List[str]] = {
    "aas":      ["D01", "D02", "D05"],
    "aad-web":  ["D05", "D07", "D11"],
    "asdw-web": ["D05", "D07", "D10"],
    "adfd":      ["D04", "D05", "D08"],
    "adfdv":     ["D04", "D08"],
    "aag":      ["D05", "D07", "D18"],
    "aagd":     ["D05", "D07", "D18"],
    "akm":      ["D01", "D02", "D03"],
    "aqod":     ["D01", "D02"],
    "adoc":     ["D19"],
}

# YAML frontmatter の description: フィールド抽出パターン
_FRONTMATTER_DESC_PATTERN: re.Pattern[str] = re.compile(
    r"^---\s*\n.*?^description:\s*(.+?)$.*?^---",
    re.MULTILINE | re.DOTALL,
)


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
    tool_status: NotRequired[Dict[str, str]]
    tool_exit_codes: NotRequired[Dict[str, Optional[int]]]
    tests_collected: NotRequired[int]
    tests_skipped: NotRequired[int]
    metric_status: NotRequired[Dict[str, str]]


class VerificationResult(TypedDict):
    """verify_improvements の戻り値。"""
    after_quality_score: int
    degraded: bool
    verification_phases: Dict[str, str]   # phase名 → "PASS"|"FAIL"|"SKIP"
    overall: str                          # "PASS" | "FAIL" | "BLOCKED"
    notes: str


class TaskGoal(TypedDict):
    """タスク固有のゴール定義（TDD の成功条件 + RL の報酬重み）。

    TDD 的アプローチ:
      - goal_description: ゴールを自然言語で定義する（テストを書く前に書く仕様に相当）
      - success_criteria:  GREEN になるべき検証条件リスト（RED→GREEN の合格基準）
      - tdd_phase: 現在のフェーズ — GREEN（テスト通過を目指す）| REFACTOR（品質向上）

    RL 的アプローチ:
      - reward_weights: lint / test / documentation ごとの報酬寄与度（合計 = 1.0）
        ワークフロー目的に合わせて設定し、タスクに適した報酬関数を実現する
    """
    goal_description: str            # ゴールの自然言語説明
    success_criteria: List[str]      # 成功条件リスト（TDD の RED→GREEN 合格基準）
    criterion_definitions: NotRequired[List[Dict[str, Any]]]  # 決定的 evaluator / evidence 契約
    reward_weights: Dict[str, float] # カテゴリ別報酬重み（lint / test / documentation の合計 = 1.0）
    tdd_phase: str                   # TDD フェーズ: "GREEN" | "REFACTOR"


class RewardSignal(TypedDict):
    """1イテレーションの強化学習報酬シグナル。

    報酬設計:
      - reward: 今回の goal_achievement_pct 改善量 × 100（負 = デグレード）
      - plateau_detected: 直近 PLATEAU_WINDOW イテレーション全て PLATEAU_EPSILON 未満
        → RL の収束判定として使用し、無駄なイテレーションを削減する
    """
    reward: float                    # 今回の報酬（goal_achievement_pct の改善量 × 100）
    cumulative_reward: float         # 累積報酬
    goal_achievement_pct: float      # タスクゴール達成率（0.0〜1.0）
    tdd_phase: str                   # このイテレーションの TDD フェーズ
    plateau_detected: bool           # 報酬プラトー検知フラグ（RL 収束判定）


class ImprovementRecord(TypedDict):
    """1イテレーションの改善記録。"""
    iteration: int
    before_score: int
    after_score: int
    degraded: bool
    plan_summary: str
    verification: VerificationResult
    reward_signal: RewardSignal      # RL 報酬シグナル（タスクゴールに基づく）
    elapsed_seconds: float
    plan: NotRequired[Dict[str, Any]]
    changed_files: NotRequired[List[str]]
    preexisting_changed_files: NotRequired[List[str]]
    failed_changes: NotRequired[List[Dict[str, str]]]
    before_criteria: NotRequired[List[Dict[str, Any]]]
    after_criteria: NotRequired[List[Dict[str, Any]]]
    protected_artifact_delta: NotRequired[List[Dict[str, Any]]]


class SelfImproveResult(TypedDict):
    """run_improvement_loop の戻り値。"""
    iterations_completed: int
    final_score: int
    records: List[ImprovementRecord]
    stopped_reason: str     # 成功・上限・degradation・blocked 等の有限な停止理由
    reward_history: List[float]        # イテレーションごとの報酬履歴（RL）
    final_goal_achievement_pct: float  # 最終タスクゴール達成率（0.0〜1.0）
    final_criterion_results: NotRequired[List[Dict[str, Any]]]
    final_verification: NotRequired[VerificationResult]
    blocked_reason: NotRequired[str]


class TaskGoalDiscoveryResult(TypedDict):
    """discover_task_goal_from_docs の戻り値。"""
    task_goal: TaskGoal
    sources: List[str]   # 参照したファイルの相対パスリスト


# ---------------------------------------------------------------------------
# ワークフロー固有タスクゴール定義
# ---------------------------------------------------------------------------

# ワークフロー ID → デフォルト TaskGoal のマッピング。
# TDD の成功条件（success_criteria）と RL の報酬重み（reward_weights）を
# 各ワークフローの目的に合わせて設定する。
_WORKFLOW_TASK_GOALS: Dict[str, "TaskGoal"] = {
    "aas": TaskGoal(
        goal_description="アーキテクチャ設計文書（docs/）が構造的に完全で整合性があること",
        success_criteria=[
            "docs/catalog/ 配下のカタログファイルに矛盾がない",
            "markdownlint エラーが 0 件",
            "各文書に必須セクション（目的・スコープ・設計判断）が含まれる",
        ],
        reward_weights={"lint": 0.2, "test": 0.1, "documentation": 0.7},
        tdd_phase="GREEN",
    ),
    "aad-web": TaskGoal(
        goal_description="Web アプリ設計文書（docs/）が業務要件と整合し品質基準を満たすこと",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "各設計文書に業務要件への参照（Ref: D0x）が含まれる",
            "API 仕様・データモデル・UI 仕様が相互に整合している",
        ],
        reward_weights={"lint": 0.2, "test": 0.1, "documentation": 0.7},
        tdd_phase="GREEN",
    ),
    "asdw-web": TaskGoal(
        goal_description="バックエンド/フロントエンドのコードとテストが全て GREEN になること",
        success_criteria=[
            "pytest テスト失敗 0 件",
            "ruff lint エラー 0 件",
            "テストカバレッジ 70% 以上",
        ],
        reward_weights={"lint": 0.3, "test": 0.5, "documentation": 0.2},
        tdd_phase="GREEN",
    ),
    "adfd": TaskGoal(
        goal_description="データフロー設計文書（docs/dataflow/）が仕様要件を満たし整合していること",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "各データフローアプリ仕様書に入力・処理・出力の 3 セクションが存在する",
        ],
        reward_weights={"lint": 0.2, "test": 0.1, "documentation": 0.7},
        tdd_phase="GREEN",
    ),
    "adfdv": TaskGoal(
        goal_description="バッチ実装のテストが全て GREEN になること",
        success_criteria=[
            "pytest テスト失敗 0 件",
            "ruff lint エラー 0 件",
            "テストカバレッジ 70% 以上",
        ],
        reward_weights={"lint": 0.3, "test": 0.5, "documentation": 0.2},
        tdd_phase="GREEN",
    ),
    "aag": TaskGoal(
        goal_description="エージェント設計文書（docs/agent/）が完全で実装可能なレベルであること",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "各エージェント定義に入力・出力・ツール・判断基準が明記されている",
        ],
        criterion_definitions=[
            {
                "criterion_id": "AAG-DOC-LINT",
                "description": "AAG成果物のmarkdownlintエラーが0件",
                "required_for_done": True,
                "evaluator_type": "rule",
                "evaluation": {
                    "metric": "doc_issues",
                    "operator": "eq",
                    "expected": 0,
                },
                "evidence_required": {
                    "kind": "field-value",
                    "reference": "scan.summary.doc_issues",
                },
                "failure_action": "continue",
                "source": "hve.self_improve._WORKFLOW_TASK_GOALS[aag]",
            },
        ],
        reward_weights={"lint": 0.2, "test": 0.1, "documentation": 0.7},
        tdd_phase="GREEN",
    ),
    "aagd": TaskGoal(
        goal_description="エージェント実装のテストと設計文書が整合し品質基準を満たすこと",
        success_criteria=[
            "pytest テスト失敗 0 件",
            "ruff lint エラー 0 件",
            "markdownlint エラーが 0 件",
        ],
        criterion_definitions=[
            {
                "criterion_id": "AAGD-TESTS",
                "description": "AAGD成果物のtest失敗が0件",
                "required_for_done": True,
                "evaluator_type": "test",
                "evaluation": {
                    "metric": "test_failures",
                    "operator": "eq",
                    "expected": 0,
                },
                "evidence_required": {
                    "kind": "test-result",
                    "reference": "scan.summary.test_failures",
                },
                "failure_action": "continue",
                "source": "hve.self_improve._WORKFLOW_TASK_GOALS[aagd]",
            },
            {
                "criterion_id": "AAGD-BUILD-LINT",
                "description": "AAGD成果物の言語別build/lintエラーが0件",
                "required_for_done": True,
                "evaluator_type": "rule",
                "evaluation": {
                    "metric": "lint_errors",
                    "operator": "eq",
                    "expected": 0,
                },
                "evidence_required": {
                    "kind": "field-value",
                    "reference": "scan.summary.lint_errors",
                },
                "failure_action": "continue",
                "source": "hve.self_improve._WORKFLOW_TASK_GOALS[aagd]",
            },
            {
                "criterion_id": "AAGD-DOC-LINT",
                "description": "AAGD成果物のmarkdownlintエラーが0件",
                "required_for_done": True,
                "evaluator_type": "rule",
                "evaluation": {
                    "metric": "doc_issues",
                    "operator": "eq",
                    "expected": 0,
                },
                "evidence_required": {
                    "kind": "field-value",
                    "reference": "scan.summary.doc_issues",
                },
                "failure_action": "continue",
                "source": "hve.self_improve._WORKFLOW_TASK_GOALS[aagd]",
            },
        ],
        reward_weights={"lint": 0.3, "test": 0.4, "documentation": 0.3},
        tdd_phase="GREEN",
    ),
    "akm": TaskGoal(
        goal_description="knowledge/ D01〜D21 の内容が業務要件と整合し矛盾がないこと",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "D01〜D21 の全ファイルに必須セクションが存在する",
            "knowledge/ 内に矛盾する記述がない",
        ],
        reward_weights={"lint": 0.1, "test": 0.0, "documentation": 0.9},
        tdd_phase="GREEN",
    ),
    "aqod": TaskGoal(
        goal_description="qa/ の質問票・回答が業務要件分析として十分な深さと品質を持つこと",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "qa/ 配下の全ファイルに質問・回答・根拠の 3 要素が含まれる",
        ],
        reward_weights={"lint": 0.1, "test": 0.0, "documentation": 0.9},
        tdd_phase="GREEN",
    ),
    "adoc": TaskGoal(
        goal_description="docs/ 配下の全文書が markdownlint 準拠で内容が完全であること",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "全文書に目的・対象・内容の 3 セクションが存在する",
        ],
        reward_weights={"lint": 0.2, "test": 0.0, "documentation": 0.8},
        tdd_phase="GREEN",
    ),
}

# デフォルト TaskGoal（ワークフロー固有定義がない場合）
_DEFAULT_TASK_GOAL: "TaskGoal" = TaskGoal(
    goal_description="コードベース全体の品質（lint / test / documentation）を改善すること",
    success_criteria=[
        "ruff lint エラー 0 件",
        "pytest テスト失敗 0 件",
        "markdownlint エラー 0 件",
    ],
    reward_weights={"lint": 0.4, "test": 0.4, "documentation": 0.2},
    tdd_phase="GREEN",
)

# RL プラトー検知パラメータ
_PLATEAU_EPSILON: float = 2.0   # この値未満の報酬が連続すると収束とみなす
_PLATEAU_WINDOW: int = 2        # 連続チェックするイテレーション数

# LLM ゴール生成プロンプトテンプレート（discover_task_goal_with_llm で使用）
_LLM_GOAL_PROMPT_TEMPLATE = """\
あなたはソフトウェア品質改善の専門家です。
以下のリポジトリドキュメントを参照し、ワークフロー「{workflow_id}」の自己改善ループの
ゴールと成功条件を定義してください。

## ワークフロー ID
{workflow_id}

## 参照ドキュメント（抜粋）
{context}

## 出力フォーマット
JSON のみを出力してください。説明文・前置き・コードフェンス記号は不要です。
{{
  "goal_description": "ゴールを日本語1文で記述（例: 'knowledge/ D01〜D21 の内容が業務要件と整合していること'）",
  "success_criteria": [
    "成功条件1（具体的・検証可能な条件）",
    "成功条件2",
    "成功条件3"
  ]
}}
"""


# ---------------------------------------------------------------------------
# タスクゴール関連ヘルパー
# ---------------------------------------------------------------------------


def define_task_goal(
    workflow_id: str = "",
    user_goal_description: str = "",
) -> "TaskGoal":
    """ワークフロー ID とユーザー記述からタスク固有のゴールを定義する（TDD 的アプローチ）。

    優先順位:
      1. _WORKFLOW_TASK_GOALS[workflow_id] からデフォルトを取得
      2. user_goal_description が非空なら goal_description を上書き
      3. どちらもない場合は _DEFAULT_TASK_GOAL を使用

    Args:
        workflow_id: ワークフロー識別子（例: "akm", "asdw-web"）。
        user_goal_description: ユーザーが指定したゴール説明（任意）。

    Returns:
        TaskGoal 型の辞書。
    """
    base = dict(_WORKFLOW_TASK_GOALS.get(workflow_id, _DEFAULT_TASK_GOAL))
    if user_goal_description:
        base["goal_description"] = user_goal_description
    return TaskGoal(**base)  # type: ignore[misc]


def discover_task_goal_from_docs(
    workflow_id: str,
    target_scope: str = "",
    repo_root: str = ".",
) -> "TaskGoalDiscoveryResult":
    """ファイル静的解析（LLM 不使用）でタスクゴールを自動生成する。

    参照優先順位:
      1. .github/agents/<name>.agent.md の YAML frontmatter description:
      2. .github/skills/<subpath>/SKILL.md の YAML frontmatter description:
      3. knowledge/D??-*.md の H1 タイトル（最大 3 件）
      4. docs/ 配下のファイルの H1 タイトル（最大 2 件）

    - 全て失敗した場合は define_task_goal(workflow_id) にフォールバック
    - ファイル不存在・読み取りエラーは個別スキップ（例外を伝播させない）
    - 新ワークフロー追加時は _WORKFLOW_AGENT_MAP / _WORKFLOW_SKILLS_MAP /
      _WORKFLOW_DOCS_MAP / _WORKFLOW_KNOWLEDGE_MAP を全て更新すること

    Args:
        workflow_id: ワークフロー識別子。
        target_scope: 改善対象スコープ（現在は未使用、将来の拡張用）。
        repo_root: リポジトリルートディレクトリ。

    Returns:
        TaskGoalDiscoveryResult — task_goal と参照ソースリスト。
    """
    import glob as _glob_mod
    repo = Path(repo_root)
    sources: List[str] = []
    goal_description: str = ""
    extra_criteria: List[str] = []

    def _rel(p: Path) -> str:
        """repo_root 基準の相対パス文字列を返す。"""
        try:
            return str(p.relative_to(repo.resolve())).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    def _extract_frontmatter_desc(filepath: Path) -> str:
        """YAML frontmatter の description: を抽出する。空文字 = 取得失敗。"""
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            m = _FRONTMATTER_DESC_PATTERN.search(text)
            if m:
                return m.group(1).strip()[:200]
        except OSError:
            pass
        return ""

    def _extract_h1(filepath: Path) -> str:
        """ファイルの最初の H1 行（# ...）を返す。"""
        try:
            for line in filepath.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()[:80]
        except OSError:
            pass
        return ""

    # ── 1. Agent ファイルから goal_description を取得 ──────────────
    agent_dir = repo / ".github" / "agents"
    for agent_filename in _WORKFLOW_AGENT_MAP.get(workflow_id, []):
        agent_path = agent_dir / agent_filename
        desc = _extract_frontmatter_desc(agent_path)
        if desc:
            goal_description = desc
            sources.append(_rel(agent_path))
            break  # 最初にヒットした 1 件のみ使用

    # ── 2. Skills ファイルから goal_description を補完 ────────────
    if not goal_description:
        skills_dir = repo / ".github" / "skills"
        _skill_subpaths: List[str] = []
        try:
            try:
                from .skill_resolver import get_skill_subpaths_for_workflow
            except ImportError:
                from skill_resolver import get_skill_subpaths_for_workflow  # type: ignore[no-redef]
            _skill_subpaths = get_skill_subpaths_for_workflow(workflow_id)
        except Exception:
            _skill_subpaths = []

        # 共通 resolver が利用不能な場合のみ legacy マップへフォールバック
        if not _skill_subpaths:
            _skill_subpaths = list(_WORKFLOW_SKILLS_MAP.get(workflow_id, []))

        for skill_subpath in _skill_subpaths:
            skill_path = skills_dir / skill_subpath / "SKILL.md"
            desc = _extract_frontmatter_desc(skill_path)
            if desc:
                goal_description = desc
                sources.append(_rel(skill_path))
                break

    # ── 3. knowledge/ D-class H1 タイトルを success_criteria に追記 ──
    knowledge_dir = repo / "knowledge"
    d_prefixes = _WORKFLOW_KNOWLEDGE_MAP.get(workflow_id, [])
    added_knowledge = 0
    for d_prefix in d_prefixes:
        if added_knowledge >= 3:
            break
        matches = sorted(knowledge_dir.glob(f"{d_prefix}-*.md"))
        for km_path in matches[:1]:
            h1 = _extract_h1(km_path)
            if h1:
                extra_criteria.append(f"{d_prefix}: {h1[:80]}")
                sources.append(_rel(km_path))
                added_knowledge += 1

    # ── 4. docs/ ファイルの H1 タイトルを補助参照 ─────────────────
    added_docs = 0
    for doc_path_str in _WORKFLOW_DOCS_MAP.get(workflow_id, []):
        if added_docs >= 2:
            break
        doc_path = repo / doc_path_str
        if doc_path.is_file():
            h1 = _extract_h1(doc_path)
            if h1:
                sources.append(_rel(doc_path))
                added_docs += 1
        elif doc_path.is_dir():
            for md_file in sorted(doc_path.glob("*.md"))[:1]:
                h1 = _extract_h1(md_file)
                if h1:
                    sources.append(_rel(md_file))
                    added_docs += 1

    # ── ゴール組み立て ────────────────────────────────────────────
    base_goal = define_task_goal(workflow_id=workflow_id)

    if goal_description:
        success_criteria = list(base_goal["success_criteria"])
        for c in extra_criteria:
            if c not in success_criteria:
                success_criteria.append(c)
        task_goal = TaskGoal(
            goal_description=goal_description,
            success_criteria=success_criteria,
            reward_weights=base_goal["reward_weights"],
            tdd_phase=base_goal["tdd_phase"],
        )
        if base_goal.get("criterion_definitions"):
            task_goal["criterion_definitions"] = list(
                base_goal["criterion_definitions"]
            )
    else:
        task_goal = base_goal

    return TaskGoalDiscoveryResult(task_goal=task_goal, sources=sources)


async def discover_task_goal_with_llm(
    workflow_id: str,
    model: str = "",
    cli_path: str = "",
    github_token: str = "",
    cli_url: str = "",
    target_scope: str = "",
    repo_root: str = ".",
    timeout: float = 60.0,
) -> "TaskGoalDiscoveryResult":
    """LLM を使用してタスクゴールを自動生成する。

    静的解析（discover_task_goal_from_docs）でソースファイルを収集し、
    その内容を Copilot SDK 経由で LLM に渡してゴール文字列と成功条件を生成する。

    失敗時（SDK 未インストール・LLM エラー・JSON パース失敗）は
    discover_task_goal_from_docs の結果にフォールバックする。

    Args:
        workflow_id: ワークフロー識別子。
        model: 使用モデル（空文字 = Auto）。
        cli_path: Copilot CLI のパス。
        github_token: GitHub トークン。
        cli_url: 外部 CLI サーバー URL（空文字 = subprocess モード）。
        target_scope: 改善対象スコープ。
        repo_root: リポジトリルートディレクトリ。
        timeout: LLM 呼び出しタイムアウト（秒）。

    Returns:
        TaskGoalDiscoveryResult — task_goal と参照ソースリスト。
    """
    # まず静的解析でソースと基底ゴールを取得
    static_result = discover_task_goal_from_docs(
        workflow_id=workflow_id,
        target_scope=target_scope,
        repo_root=repo_root,
    )
    sources = static_result["sources"]
    base_goal = static_result["task_goal"]

    # ソースファイルの内容を LLM コンテキストとして収集
    _MAX_CHARS_PER_FILE = 600
    _MAX_TOTAL_CHARS = 3000
    context_parts: List[str] = []
    total_chars = 0
    repo = Path(repo_root)
    for src_rel in sources:
        if total_chars >= _MAX_TOTAL_CHARS:
            break
        src_path = repo / src_rel
        try:
            text = src_path.read_text(encoding="utf-8", errors="replace")
            snippet = text[:_MAX_CHARS_PER_FILE]
            context_parts.append(f"### {src_rel}\n{snippet}")
            total_chars += len(snippet)
        except OSError:
            continue

    if not context_parts:
        # ソースが取れなかった場合は静的結果をそのまま返す
        return static_result

    context_text = "\n\n".join(context_parts)
    prompt = _LLM_GOAL_PROMPT_TEMPLATE.format(
        workflow_id=workflow_id,
        context=context_text,
    )

    # Copilot SDK 経由で LLM を呼び出す
    try:
        import copilot  # noqa: F401  # type: ignore[import]
        from copilot.session import PermissionHandler  # type: ignore[import]
    except ImportError:
        # SDK 未インストール: 静的結果にフォールバック
        return static_result

    # to_wire_model / Cloud Session helper を遅延 import する（相対 / 絶対の両方に対応）
    try:
        from .config import SDKConfig, to_wire_model
        from .cloud_session import (
            acquire_cloud_session_slot,
            attach_cloud_session_event_logger,
            attach_cloud_session_limiter_release,
            build_cloud_session_options,
            is_policy_blocked_error,
        )
    except ImportError:
        from config import SDKConfig, to_wire_model  # type: ignore[no-redef]
        from cloud_session import (  # type: ignore[no-redef]
            acquire_cloud_session_slot,
            attach_cloud_session_event_logger,
            attach_cloud_session_limiter_release,
            build_cloud_session_options,
            is_policy_blocked_error,
        )

    cloud_config = SDKConfig.from_env()

    async def _create_session_with_auto_reasoning_fallback(_client: Any, _opts: Dict[str, Any]) -> Any:
        """create_session を呼び出し、SDK が reasoning_effort を未サポートの場合は除外して再試行する。

        検出条件は TypeError 文言 `unexpected keyword argument` と
        `reasoning_effort` の両方を要求し、誤検出を防ぐ。
        """
        opts = dict(_opts)
        cloud_injected = False
        had_streaming_before_cloud = "streaming" in opts
        streaming_before_cloud = opts.get("streaming")
        if "cloud" not in opts:
            cloud_opts = build_cloud_session_options(
                cloud_config,
                step_id="self_improve",
                subtask_kind="self_improve",
            )
            if cloud_opts is not None:
                opts["cloud"] = cloud_opts
                cloud_injected = True
                opts["streaming"] = True
        async def _attempt(payload: Dict[str, Any]) -> Any:
            limiter = None
            try:
                if "cloud" in payload:
                    limiter = await acquire_cloud_session_slot(cloud_config)
                session = await _client.create_session(**payload)
                if "cloud" in payload:
                    attach_cloud_session_event_logger(
                        session,
                        step_id="self_improve",
                        subtask_kind="self_improve",
                    )
                    if limiter is not None:
                        attach_cloud_session_limiter_release(session, limiter)
                        limiter = None
                return session
            except TypeError as exc:
                if limiter is not None:
                    limiter.release_slot()
                msg = str(exc)
                if (
                    "unexpected keyword argument" in msg
                    and "cloud" in msg
                    and "cloud" in payload
                ):
                    stripped = {k: v for k, v in payload.items() if k != "cloud"}
                    if cloud_injected:
                        if had_streaming_before_cloud:
                            stripped["streaming"] = streaming_before_cloud
                        else:
                            stripped.pop("streaming", None)
                    return await _attempt(stripped)
                if (
                    "unexpected keyword argument" in msg
                    and "reasoning_effort" in msg
                    and "reasoning_effort" in payload
                ):
                    stripped = {k: v for k, v in payload.items() if k != "reasoning_effort"}
                    return await _attempt(stripped)
                raise
            except Exception as exc:
                if limiter is not None:
                    limiter.release_slot()
                if is_policy_blocked_error(exc):
                    raise
                if "cloud" in payload and cloud_injected:
                    stripped = {k: v for k, v in payload.items() if k != "cloud"}
                    if had_streaming_before_cloud:
                        stripped["streaming"] = streaming_before_cloud
                    else:
                        stripped.pop("streaming", None)
                    return await _attempt(stripped)
                raise

        return await _attempt(opts)

    client = None
    session = None
    try:
        try:
            from .copilot_client_factory import create_copilot_client
        except ImportError:  # pragma: no cover
            from copilot_client_factory import create_copilot_client  # type: ignore[no-redef]
        client = create_copilot_client(
            cli_path=cli_path or None,
            cli_url=cli_url or None,
            github_token=github_token or None,
            log_level="error",
        )
        await client.start()

        session_opts: Dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": False,
        }
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(model)
        if _wire_model:
            session_opts["model"] = _wire_model

        # Phase 2 (Resume): このセッションはワークフロー実行前のゴール探索専用で
        # run_id 文脈を持たないため、決定論的 session_id は付与しない（SDK が自動採番する）。
        # Resume 対象外（一回きりの診断的呼び出し）。
        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)
        response = await session.send_and_wait(prompt, timeout=timeout)

        # レスポンステキストを抽出
        raw_text = _extract_llm_response_text(response)

    except Exception as exc:
        if is_policy_blocked_error(exc):
            raise
        # LLM 呼び出し失敗: 静的結果にフォールバック
        return static_result
    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception:
                pass
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass

    # JSON パース
    parsed = _parse_llm_goal_json(raw_text)
    if parsed is None:
        return static_result

    goal_description = (parsed.get("goal_description") or "").strip()
    raw_criteria = parsed.get("success_criteria")
    success_criteria: List[str] = (
        [str(c) for c in raw_criteria if c]
        if isinstance(raw_criteria, list)
        else []
    )

    if not goal_description:
        return static_result

    # success_criteria が空の場合は base_goal のものを使用
    if not success_criteria:
        success_criteria = list(base_goal["success_criteria"])

    task_goal = TaskGoal(
        goal_description=goal_description,
        success_criteria=success_criteria,
        reward_weights=base_goal["reward_weights"],
        tdd_phase=base_goal["tdd_phase"],
    )
    if base_goal.get("criterion_definitions"):
        task_goal["criterion_definitions"] = list(
            base_goal["criterion_definitions"]
        )
    return TaskGoalDiscoveryResult(task_goal=task_goal, sources=sources)


def _extract_llm_response_text(response: Any) -> str:
    """LLM レスポンスオブジェクトからテキストを抽出する（runner._extract_text と同等）。"""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    data = getattr(response, "data", None)
    if data is not None:
        for attr in ("content", "message"):
            val = getattr(data, attr, None)
            if val is not None:
                return str(val)
    for attr in ("content", "text", "message"):
        val = getattr(response, attr, None)
        if val is not None:
            return str(val)
    return ""


def _parse_llm_goal_json(text: str) -> Optional[Dict[str, Any]]:
    """LLM レスポンスから goal_description / success_criteria を含む JSON を抽出してパースする。

    ```json ... ``` フェンス内、または裸の `{...}` の両方に対応する。
    パース失敗時は None を返す。
    """
    import json as _json

    # コードフェンスを除去
    _fence = re.compile(r"```(?:json)?\s*\n?")
    m = _fence.search(text)
    search_text = text[m.end():] if m else text

    # `{` から始まる JSON オブジェクトを深さカウントで抽出
    start = search_text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(search_text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_str = search_text[start:i + 1]
                try:
                    return _json.loads(json_str)
                except _json.JSONDecodeError:
                    return None
    return None


def _compute_goal_achievement(scan: "ScanResult", task_goal: "TaskGoal") -> float:
    """タスクゴールの達成率を計算する（0.0〜1.0）。

    各カテゴリのペナルティをゴールの reward_weights で重み付けして集計する。
    reward_weights の合計が 0 の場合は 0.0 を返す（ゼロ除算防止）。

    Args:
        scan: スキャン結果。
        task_goal: タスク固有ゴール。

    Returns:
        達成率 0.0〜1.0。
    """
    summary = scan["summary"]
    weights = task_goal["reward_weights"]

    # lint コンポーネント（0.0〜1.0）
    lint_score = max(
        0.0,
        1.0 - min(summary["lint_errors"] * _LINT_ERROR_PENALTY, _MAX_LINT_PENALTY) / 100.0,
    )
    # test コンポーネント（0.0〜1.0）
    test_score = max(
        0.0,
        1.0 - min(summary["test_failures"] * _TEST_FAILURE_PENALTY, _MAX_TEST_PENALTY) / 100.0,
    )
    # documentation コンポーネント（0.0〜1.0）
    doc_score = max(
        0.0,
        1.0 - min(summary["doc_issues"], _MAX_DOC_PENALTY) / 100.0,
    )

    total_weight = (
        weights.get("lint", 0.0)
        + weights.get("test", 0.0)
        + weights.get("documentation", 0.0)
    )
    if total_weight <= 0:
        return 0.0

    weighted = (
        lint_score * weights.get("lint", 0.0)
        + test_score * weights.get("test", 0.0)
        + doc_score * weights.get("documentation", 0.0)
    ) / total_weight

    return min(1.0, max(0.0, weighted))


def calculate_reward(
    before_scan: "ScanResult",
    after_scan: "ScanResult",
    task_goal: "TaskGoal",
    reward_history: List[float],
) -> "RewardSignal":
    """タスクゴールに基づく強化学習の報酬シグナルを計算する。

    報酬 = (after_goal_achievement_pct - before_goal_achievement_pct) × 100

    TDD フェーズ判定:
      - test 重みが 0 より大きく、かつテスト失敗 0 件 → REFACTOR フェーズへ移行
      - それ以外は task_goal.tdd_phase を維持

    プラトー検知（RL 収束判定）:
      - 直近 _PLATEAU_WINDOW イテレーション（現在含む）の報酬が全て _PLATEAU_EPSILON 未満
        → plateau_detected=True（無駄なイテレーションを削減）

    Args:
        before_scan: 改善前スキャン結果。
        after_scan: 改善後スキャン結果。
        task_goal: タスク固有ゴール。
        reward_history: これまでの報酬履歴（今回の値は含まない）。

    Returns:
        RewardSignal 型の辞書。
    """
    before_pct = _compute_goal_achievement(before_scan, task_goal)
    after_pct = _compute_goal_achievement(after_scan, task_goal)
    reward = (after_pct - before_pct) * 100.0
    cumulative = sum(reward_history) + reward

    # TDD フェーズ判定: テスト成功 → REFACTOR へ昇格
    test_weight = task_goal["reward_weights"].get("test", 0.0)
    tdd_phase = (
        "REFACTOR"
        if test_weight > 0 and after_scan["summary"]["test_failures"] == 0
        else task_goal["tdd_phase"]
    )

    # プラトー検知
    recent = reward_history[-(_PLATEAU_WINDOW - 1):] + [reward]
    plateau_detected = (
        len(recent) >= _PLATEAU_WINDOW
        and all(r < _PLATEAU_EPSILON for r in recent)
    )

    return RewardSignal(
        reward=reward,
        cumulative_reward=cumulative,
        goal_achievement_pct=after_pct,
        tdd_phase=tdd_phase,
        plateau_detected=plateau_detected,
    )


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
        output = (result.stdout or "") + (result.stderr or "")
        return f"{output}\n[HVE_TOOL_EXIT_CODE={result.returncode}]"
    except FileNotFoundError:
        return f"[TOOL NOT FOUND] {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] {cmd[0]} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return f"[ERROR] {cmd[0]}: {exc}"


def _tool_exit_code(output: str) -> Optional[int]:
    match = _TOOL_EXIT_CODE_PATTERN.search(output)
    return int(match.group("code")) if match else None


def _classify_tool_status(
    tool: str,
    output: str,
    *,
    tests_collected: int = 0,
) -> str:
    """Tool出力をPASS/FAIL/NO_TESTS/BLOCKED/UNAVAILABLEへ正規化する。"""
    if "[TOOL NOT FOUND]" in output:
        return "UNAVAILABLE"
    if "[TIMEOUT]" in output or "[ERROR]" in output:
        return "BLOCKED"
    returncode = _tool_exit_code(output)
    # 既存unit testのmock出力はmarkerを持たない。実processは必ずmarkerを持つ。
    if returncode is None:
        return "PASS"
    if tool in {"pytest", "dotnet-test"}:
        if returncode == 0:
            return "PASS" if tests_collected > 0 else "NO_TESTS"
        if returncode == 1:
            return "FAIL"
        if returncode == 5:
            return "NO_TESTS"
        return "BLOCKED"
    if returncode == 0:
        return "PASS"
    if returncode == 1:
        return "FAIL"
    return "BLOCKED"


def _aggregate_tool_status(statuses: List[str]) -> str:
    """複数Tool/projectの状態を最も安全側の1値へ集約する。"""
    if not statuses:
        return "SKIP"
    priority = {
        "UNAVAILABLE": 6,
        "BLOCKED": 5,
        "FAIL": 4,
        "NO_TESTS": 3,
        "PASS": 2,
        "SKIP": 1,
    }
    return max(statuses, key=lambda item: priority.get(item, 5))


def _aggregate_exit_code(outputs: List[str]) -> Optional[int]:
    codes = [_tool_exit_code(output) for output in outputs]
    concrete = [code for code in codes if code is not None]
    if not concrete:
        return None
    return next((code for code in concrete if code != 0), 0)


def _scope_files(repo_root: Path, scope_paths: List[str]) -> List[tuple[str, Path]]:
    """resolved scope内をreparse非追従でwalkし、実ファイルを列挙する。"""
    repo = repo_root.resolve()
    files: Dict[str, Path] = {}
    for scope in scope_paths:
        lexical_scope = repo / scope
        if _path_has_symlink_component(scope, repo):
            continue
        full = lexical_scope.resolve()
        try:
            full.relative_to(repo)
        except ValueError:
            continue
        if full.is_file():
            candidates = [lexical_scope]
        elif full.is_dir():
            candidates = []
            for root_text, dirnames, filenames in os.walk(
                lexical_scope,
                topdown=True,
                followlinks=False,
            ):
                root_path = Path(root_text)
                dirnames[:] = [
                    name for name in dirnames
                    if not _is_symlink_or_junction(root_path / name)
                ]
                candidates.extend(
                    root_path / filename
                    for filename in filenames
                    if not _is_symlink_or_junction(root_path / filename)
                )
        else:
            candidates = []
        for lexical_candidate in candidates:
            try:
                lexical_relative = lexical_candidate.relative_to(repo)
                lexical_text = str(lexical_relative).replace("\\", "/")
                if _path_has_symlink_component(lexical_text, repo):
                    continue
                resolved = lexical_candidate.resolve()
                relative = resolved.relative_to(repo)
                resolved.relative_to(full if full.is_dir() else full.parent)
            except (OSError, ValueError):
                continue
            if not resolved.is_file():
                continue
            relative_text = str(relative).replace("\\", "/")
            if relative_text.startswith("work/"):
                continue
            files[relative_text] = resolved
    return [(relative, files[relative]) for relative in sorted(files)]


def _is_csharp_test_project(relative: str, path: Path) -> bool:
    lowered = relative.casefold().replace("\\", "/")
    if (
        "test" in path.stem.casefold()
        or any(
            part in {"test", "tests"} or part.endswith(".tests")
            for part in lowered.split("/")[:-1]
        )
    ):
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "microsoft.net.test.sdk" in text.casefold()


def _run_dotnet_projects(
    verb: str,
    projects: List[str],
    *,
    cwd: str,
    timeout: int,
) -> List[str]:
    return [
        _run_tool(["dotnet", verb, project, "--nologo"], cwd=cwd, timeout=timeout)
        for project in projects
    ]


# ---------------------------------------------------------------------------
# 新スコープ解決ヘルパー（フィーチャーフラグ: HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER）
# ---------------------------------------------------------------------------


def _is_new_resolver_enabled() -> bool:
    """フィーチャーフラグの判定。Phase 1 では opt-in。"""
    try:
        from .config import SELF_IMPROVE_NEW_SCOPE_RESOLVER_ENV
    except ImportError:
        from config import SELF_IMPROVE_NEW_SCOPE_RESOLVER_ENV  # type: ignore[no-redef]
    return os.environ.get(SELF_IMPROVE_NEW_SCOPE_RESOLVER_ENV, "0") == "1"


def _resolve_target_scope_paths(
    target_scope: str,
    step_output_paths: Optional[List[str]] = None,
    workflow_default: str = "",
    repo_root: str = ".",
) -> List[str]:
    """target_scope の入力値を実スキャン対象パスのリストへ正規化する。

    解決ルール:
      1. target_scope が "" → step_output_paths を採用。
         空または None → workflow_default にフォールバック。
         workflow_default も空 → 縮小フォールバック（[]）。
      2. target_scope が "*" → SELF_IMPROVE_WILDCARD_PATHS のうち実在するもの。
      3. それ以外 → カンマ/空白で分割した複数パス。

    全ケース共通:
      - 入力を NFKC 正規化（全角 → 半角）
      - "-" で始まるトークンは ValueError
      - 重複除去（順序保持）
      - SELF_IMPROVE_EXCLUDED_TOP_DIRS（先頭セグメント "work"）を除外
      - 存在しないパスは警告ログを出力してスキップ

    Returns:
        List[str]: 実スキャン対象パスのリスト。空 = スキャンスキップ。

    Raises:
        ValueError: 入力に "-" で始まる危険なトークンが含まれる場合。
    """
    try:
        from .config import SELF_IMPROVE_WILDCARD_PATHS, SELF_IMPROVE_EXCLUDED_TOP_DIRS
    except ImportError:
        from config import SELF_IMPROVE_WILDCARD_PATHS, SELF_IMPROVE_EXCLUDED_TOP_DIRS  # type: ignore[no-redef]

    raw = unicodedata.normalize("NFKC", target_scope or "").strip()

    # ── パス候補の決定 ──
    if raw == "":
        if step_output_paths:
            candidates: List[str] = list(step_output_paths)
        elif workflow_default:
            candidates = [workflow_default]
        else:
            candidates = []
    elif raw == "*":
        candidates = list(SELF_IMPROVE_WILDCARD_PATHS)
    else:
        candidates = [p for p in re.split(r"[,\s]+", raw) if p]

    # ── 危険文字バリデーション ──
    for token in candidates:
        if token.startswith("-"):
            raise ValueError(
                f"target_scope に '-' で始まるトークンは指定できません: {token!r}"
            )

    # ── dedup（順序保持）──
    candidates = list(dict.fromkeys(candidates))

    # ── 正規化、work/ 除外、存在チェック ──
    repo = Path(repo_root).resolve()
    excluded_tops = set(SELF_IMPROVE_EXCLUDED_TOP_DIRS)

    resolved: List[str] = []
    for p in candidates:
        normalized = p.strip().replace("\\", "/")

        # leading "./" prefix を除去（"lstrip" は使わず 1 回だけ除去）
        if normalized.startswith("./"):
            normalized = normalized[2:]

        if not normalized:
            continue

        # Unix / Windows drive / UNC の絶対パスは全て拒否する。
        if (
            normalized.startswith("/")
            or Path(normalized).is_absolute()
            or PureWindowsPath(normalized).is_absolute()
            or bool(re.match(r"^[A-Za-z]:", normalized))
        ):
            print(
                f"[self-improve] target_scope: '{p}' は絶対パスのためスキップします",
                flush=True,
            )
            continue

        try:
            parts = Path(normalized).parts
        except (ValueError, OSError):
            continue

        # パストラバーサル（".." 含む）は拒否
        if ".." in parts:
            print(
                f"[self-improve] target_scope: '{p}' はパストラバーサル（'..'）を含むためスキップします",
                flush=True,
            )
            continue

        if parts and parts[0].casefold() in {item.casefold() for item in excluded_tops}:
            print(
                f"[self-improve] target_scope: '{p}' は除外対象（先頭セグメントが {', '.join(sorted(excluded_tops))} 内）",
                flush=True,
            )
            continue

        if _path_has_symlink_component(normalized, repo):
            print(
                f"[self-improve] target_scope: '{p}' はsymlink/junctionを含むためスキップします",
                flush=True,
            )
            continue

        full = (repo / normalized).resolve()
        try:
            full.relative_to(repo)
        except ValueError:
            print(
                f"[self-improve] target_scope: '{p}' はリポジトリ外へ解決されるためスキップします",
                flush=True,
            )
            continue
        if not full.exists():
            print(
                f"[self-improve] target_scope: '{p}' は存在しないためスキップします",
                flush=True,
            )
            continue

        resolved.append(normalized)

    return resolved


def _empty_scan_result(error_note: str = "") -> "ScanResult":
    """スキャン対象なし時に返す空の ScanResult。"""
    return ScanResult(
        quality_score=100,
        issues=[],
        summary={
            "lint_errors": 0,
            "test_failures": 0,
            "coverage_pct": 0.0,
            "doc_issues": 0,
        },
        raw_output=f"[SCAN SKIPPED] {error_note}" if error_note else "[SCAN SKIPPED]",
        tool_status={
            "ruff": "SKIP",
            "pytest": "SKIP",
            "dotnet_build": "SKIP",
            "dotnet_test": "SKIP",
            "markdownlint": "SKIP",
            "lint": "SKIP",
            "test": "SKIP",
            "documentation": "SKIP",
        },
        tool_exit_codes={
            "ruff": None,
            "pytest": None,
            "dotnet_build": None,
            "dotnet_test": None,
            "markdownlint": None,
        },
        tests_collected=0,
        tests_skipped=0,
        metric_status={
            "lint_errors": "SKIP",
            "test_failures": "SKIP",
            "doc_issues": "SKIP",
        },
    )



def scan_codebase(
    target_scope: str = "",
    repo_root: Optional[str] = None,
    step_output_paths: Optional[List[str]] = None,
    workflow_default: str = "",
    resolved_scope_paths: Optional[List[str]] = None,
) -> ScanResult:
    """Phase 4a: ruff / pytest --cov / markdownlint を subprocess 実行し、
    結果を構造化して返す。

    LLM 統合評価は run_improvement_loop 内で別途実施するため、
    この関数は純粋にツール実行結果を収集する役割を担う。

    Args:
        target_scope: 改善対象スコープ。
        repo_root: リポジトリルートディレクトリ。None の場合は現在のディレクトリ。
        step_output_paths: ステップ成果物パス（新仕様フラグ ON 時・未入力時に使用）。
        workflow_default: ワークフローデフォルトパス（フォールバック）。
        resolved_scope_paths: 呼び出し元が解決済みの強制scope。指定時はfeature flagに
            関係なく同じ複数pathをSCAN/VERIFYへ使用する。

    Returns:
        ScanResult 型の辞書。
    """
    cwd = repo_root or "."
    language_aware = resolved_scope_paths is not None
    python_files: List[str] = []
    python_test_files: List[str] = []
    csharp_files: List[str] = []
    csharp_projects: List[str] = []
    csharp_test_projects: List[str] = []
    markdown_files: List[str] = []
    dotnet_build_outputs: List[str] = []
    dotnet_test_outputs: List[str] = []

    if resolved_scope_paths is not None or _is_new_resolver_enabled():
        try:
            scope_paths = _resolve_target_scope_paths(
                "" if resolved_scope_paths is not None else target_scope,
                step_output_paths=(
                    resolved_scope_paths
                    if resolved_scope_paths is not None
                    else step_output_paths
                ),
                workflow_default=(
                    "" if resolved_scope_paths is not None else workflow_default
                ),
                repo_root=cwd,
            )
        except ValueError as e:
            print(f"[self-improve] {e}", flush=True)
            return _empty_scan_result(error_note=str(e))

        if not scope_paths:
            print("[self-improve] スキャン対象パスが空のためスキップします", flush=True)
            return _empty_scan_result(error_note="no_scope")

        if language_aware:
            inventory = _scope_files(Path(cwd), scope_paths)
            python_files = [
                relative for relative, path in inventory
                if path.suffix.casefold() == ".py"
            ]
            python_test_files = [
                relative for relative in python_files
                if _is_test_artifact(relative)
            ]
            csharp_files = [
                relative for relative, path in inventory
                if path.suffix.casefold() == ".cs"
            ]
            csharp_project_rows = [
                (relative, path) for relative, path in inventory
                if path.suffix.casefold() == ".csproj"
            ]
            csharp_projects = [relative for relative, _path in csharp_project_rows]
            csharp_test_projects = [
                relative for relative, path in csharp_project_rows
                if _is_csharp_test_project(relative, path)
            ]
            markdown_files = [
                relative for relative, path in inventory
                if path.suffix.casefold() in {".md", ".mdx"}
            ]

            ruff_output = (
                _run_tool(
                    [
                        "ruff", "check", *python_files,
                        "--output-format", "text", "--exclude", "work",
                    ],
                    cwd=cwd,
                )
                if python_files
                else "[SCAN SKIPPED] no Python files"
            )
            pytest_output = (
                _run_tool(
                    [
                        "pytest", *python_test_files,
                        "-q", "--tb=short", "--ignore=work",
                    ],
                    cwd=cwd,
                    timeout=180,
                )
                if python_test_files
                else "[SCAN SKIPPED] no Python tests"
            )
            if csharp_projects:
                dotnet_build_outputs = _run_dotnet_projects(
                    "build",
                    csharp_projects,
                    cwd=cwd,
                    timeout=300,
                )
            elif csharp_files:
                dotnet_build_outputs = [
                    "[ERROR] dotnet: C# source exists without a .csproj"
                ]
            if csharp_test_projects:
                dotnet_test_outputs = _run_dotnet_projects(
                    "test",
                    csharp_test_projects,
                    cwd=cwd,
                    timeout=300,
                )
            elif csharp_files or csharp_projects:
                dotnet_test_outputs = [
                    "no C# test project found\n[HVE_TOOL_EXIT_CODE=5]"
                ]
            md_output = (
                _run_tool(
                    [
                        "markdownlint", *markdown_files,
                        "--ignore", "node_modules", "--ignore", "work",
                    ],
                    cwd=cwd,
                )
                if markdown_files
                else "[SCAN SKIPPED] no Markdown files"
            )
        else:
            # ── opt-in新仕様（後方互換）: scope pathを各Toolへ渡す ──
            ruff_output = _run_tool(
                ["ruff", "check", *scope_paths, "--output-format", "text", "--exclude", "work"],
                cwd=cwd,
            )

            pytest_args: List[str] = list(scope_paths)
            if scope_paths != ["."]:
                for p in scope_paths:
                    pytest_args += ["--cov", p]
                pytest_args += ["--cov-report=term-missing"]
            pytest_args += ["-q", "--tb=short", "--ignore=work"]
            pytest_output = _run_tool(["pytest", *pytest_args], cwd=cwd, timeout=180)

            md_targets: List[str] = []
            for p in scope_paths:
                full_p = (Path(cwd) / p).resolve()
                if full_p.is_file():
                    md_targets.append(p)
                else:
                    md_targets.append(f"{p.rstrip('/')}/**/*.md" if p != "." else "**/*.md")
            if not md_targets:
                md_targets = ["**/*.md"]
            md_output = _run_tool(
                ["markdownlint", *md_targets, "--ignore", "node_modules", "--ignore", "work"],
                cwd=cwd,
            )
    else:
        # ── 旧仕様（後方互換）: コマンド引数も元のまま維持 ──
        scope_path = target_scope.strip() or "."

        ruff_output = _run_tool(
            ["ruff", "check", scope_path, "--output-format", "text"],
            cwd=cwd,
        )

        pytest_output = _run_tool(
            ["pytest", scope_path, "--cov", scope_path, "--cov-report=term-missing", "-q", "--tb=short"],
            cwd=cwd,
            timeout=180,
        )

        md_output = _run_tool(
            ["markdownlint", "**/*.md", "--ignore", "node_modules"],
            cwd=cwd,
        )

    raw_output = "\n".join([
        "=== ruff ===",
        ruff_output,
        "=== pytest --cov ===",
        pytest_output,
        "=== dotnet build ===",
        "\n".join(dotnet_build_outputs) or "[SCAN SKIPPED] no C# projects",
        "=== dotnet test ===",
        "\n".join(dotnet_test_outputs) or "[SCAN SKIPPED] no C# tests",
        "=== markdownlint ===",
        md_output,
    ])

    # ruff: 精確なエラーコードパターンでカウント（false positive を排除）
    lint_errors = len(_RUFF_ERROR_PATTERN.findall(ruff_output))
    dotnet_build_text = "\n".join(dotnet_build_outputs)
    dotnet_test_text = "\n".join(dotnet_test_outputs)
    lint_errors += len(_DOTNET_ERROR_PATTERN.findall(dotnet_build_text))

    # pytest: 失敗サマリー行から件数を抽出（FAILED / ERROR の単独出現を避ける）
    test_failures = 0
    for m in _PYTEST_FAILED_LINE_PATTERN.finditer(pytest_output):
        test_failures += int(m.group(1))
    for m in _PYTEST_ERROR_LINE_PATTERN.finditer(pytest_output):
        test_failures += int(m.group(1))
    test_failures += sum(
        int(match.group(1))
        for match in _DOTNET_FAILED_PATTERN.finditer(dotnet_test_text)
    )

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

    tests_collected = sum(
        int(match.group(1))
        for match in _PYTEST_EXECUTED_PATTERN.finditer(pytest_output)
    )
    tests_collected += sum(
        int(match.group(1))
        for pattern in (_DOTNET_PASSED_PATTERN, _DOTNET_FAILED_PATTERN)
        for match in pattern.finditer(dotnet_test_text)
    )
    tests_skipped = sum(
        int(match.group(1))
        for match in _PYTEST_SKIPPED_PATTERN.finditer(pytest_output)
    )
    tests_skipped += sum(
        int(match.group(1))
        for match in _DOTNET_SKIPPED_PATTERN.finditer(dotnet_test_text)
    )
    tool_exit_codes = {
        "ruff": _tool_exit_code(ruff_output),
        "pytest": _tool_exit_code(pytest_output),
        "dotnet_build": _aggregate_exit_code(dotnet_build_outputs),
        "dotnet_test": _aggregate_exit_code(dotnet_test_outputs),
        "markdownlint": _tool_exit_code(md_output),
    }
    if language_aware:
        python_executed = sum(
            int(match.group(1))
            for match in _PYTEST_EXECUTED_PATTERN.finditer(pytest_output)
        )
        ruff_status = (
            _classify_tool_status("ruff", ruff_output)
            if python_files else "SKIP"
        )
        pytest_status = (
            _classify_tool_status(
                "pytest", pytest_output, tests_collected=python_executed,
            )
            if python_test_files else "NO_TESTS"
        )
        dotnet_build_status = (
            _aggregate_tool_status([
                _classify_tool_status("dotnet-build", output)
                for output in dotnet_build_outputs
            ])
            if csharp_files or csharp_projects else "SKIP"
        )
        dotnet_test_status = (
            _aggregate_tool_status([
                _classify_tool_status(
                    "dotnet-test",
                    output,
                    tests_collected=sum(
                        int(match.group(1))
                        for pattern in (_DOTNET_PASSED_PATTERN, _DOTNET_FAILED_PATTERN)
                        for match in pattern.finditer(output)
                    ),
                )
                for output in dotnet_test_outputs
            ])
            if csharp_files or csharp_projects else "NO_TESTS"
        )
        markdown_status = (
            _classify_tool_status("markdownlint", md_output)
            if markdown_files else "SKIP"
        )
        lint_components = [
            status for enabled, status in (
                (bool(python_files), ruff_status),
                (bool(csharp_files or csharp_projects), dotnet_build_status),
            ) if enabled
        ]
        test_components = [
            status for enabled, status in (
                (bool(python_files), pytest_status),
                (bool(csharp_files or csharp_projects), dotnet_test_status),
            ) if enabled
        ]
        tool_status = {
            "ruff": ruff_status,
            "pytest": pytest_status,
            "dotnet_build": dotnet_build_status,
            "dotnet_test": dotnet_test_status,
            "markdownlint": markdown_status,
            "lint": _aggregate_tool_status(lint_components),
            "test": (
                _aggregate_tool_status(test_components)
                if test_components else "NO_TESTS"
            ),
            "documentation": markdown_status,
        }
    else:
        ruff_status = _classify_tool_status("ruff", ruff_output)
        pytest_status = _classify_tool_status(
            "pytest",
            pytest_output,
            tests_collected=tests_collected,
        )
        markdown_status = _classify_tool_status("markdownlint", md_output)
        tool_status = {
            "ruff": ruff_status,
            "pytest": pytest_status,
            "dotnet_build": "SKIP",
            "dotnet_test": "NO_TESTS",
            "markdownlint": markdown_status,
            "lint": ruff_status,
            "test": pytest_status,
            "documentation": markdown_status,
        }

    if tool_status["lint"] == "FAIL" and lint_errors == 0:
        lint_errors = 1
    if tool_status["test"] == "FAIL" and test_failures == 0:
        test_failures = 1
    if tool_status["documentation"] == "FAIL" and doc_issues == 0:
        doc_issues = 1

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
        tool_status=tool_status,
        tool_exit_codes=tool_exit_codes,
        tests_collected=tests_collected,
        tests_skipped=tests_skipped,
        metric_status={
            "lint_errors": tool_status["lint"],
            "test_failures": tool_status["test"],
            "doc_issues": tool_status["documentation"],
        },
    )


# ---------------------------------------------------------------------------
# ロック制御
# ---------------------------------------------------------------------------


def _acquire_lock(work_dir: Path) -> bool:
    """work_dir/.self-improve-lock ファイルで排他制御する。

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
    record: "ImprovementRecord",
    task_goal: Optional["TaskGoal"] = None,
) -> None:
    """イテレーションごとの学習ログを
    work/run/<run-id>/<Agent>/Issue-<N>/artifacts/learning-{iteration:03d}.md に保存する。

    Skill work-artifacts-layout §4.1 準拠: 既存ファイルを削除してから新規作成。
    TDD フェーズ・RL 報酬シグナルも含めて記録する。

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

    # RL 報酬セクション
    reward = record.get("reward_signal", {})
    reward_section = ""
    if reward:
        reward_section = f"""
## RL 報酬シグナル（強化学習）

| 指標 | 値 |
|------|-----|
| TDD フェーズ | {reward.get('tdd_phase', 'N/A')} |
| ゴール達成率 | {reward.get('goal_achievement_pct', 0) * 100:.1f}% |
| 今回の報酬 | {reward.get('reward', 0):.2f} |
| 累積報酬 | {reward.get('cumulative_reward', 0):.2f} |
| プラトー検知 | {"⚠️ あり（収束）" if reward.get('plateau_detected') else "✅ なし"} |
"""

    # タスクゴールセクション
    goal_section = ""
    if task_goal:
        criteria_lines = "\n".join(f"- {c}" for c in task_goal.get("success_criteria", []))
        goal_section = f"""
## タスクゴール（TDD 成功条件）

**ゴール**: {task_goal.get('goal_description', '')}

**成功条件 (GREEN 判定基準)**:
{criteria_lines}
"""

    content = f"""# 自己改善ループ 学習ログ — イテレーション {iteration:03d}

**記録日時**: {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

---
{goal_section}
## スコア変化

| 指標 | 改善前 | 改善後 |
|------|--------|--------|
| quality_score | {record["before_score"]} | {record["after_score"]} |
| デグレード検知 | — | {"⚠️ あり" if record["degraded"] else "✅ なし"} |
{reward_section}
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
# Post-DAG Self-Improve 契約ヘルパー（Sub-18）
# ---------------------------------------------------------------------------


def _utc_timestamp() -> str:
    """Criterion/Evidence 共通の ISO 8601 UTC timestamp を返す。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _criterion_definitions(task_goal: "TaskGoal") -> List[Dict[str, Any]]:
    raw = dict(task_goal).get("criterion_definitions", [])
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _criterion_result(
    definition: Dict[str, Any],
    status: str,
    evidence: List[Dict[str, Any]],
    reason: str,
) -> Dict[str, Any]:
    evaluator = definition.get("evaluator_type")
    if evaluator not in _CRITERION_EVALUATOR_TYPES:
        evaluator = "rule"
    criterion_id = definition.get("criterion_id")
    if not isinstance(criterion_id, str) or not criterion_id:
        criterion_id = "invalid-criterion"
    return {
        "criterion_id": criterion_id,
        "required_for_done": definition.get("required_for_done") is True,
        "evaluator_type": evaluator,
        "status": status,
        "evidence": evidence,
        "evaluated_at": _utc_timestamp(),
        "reason": reason,
    }


def _public_evidence(
    raw: Dict[str, Any],
    *,
    status: Optional[str] = None,
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    observed_at = raw.get("observed_at")
    if _parse_utc_timestamp(observed_at) is None:
        observed_at = _utc_timestamp()
    kind = raw.get("kind")
    if kind not in _EVIDENCE_KINDS:
        kind = "field-value"
    reference = raw.get("reference")
    if not isinstance(reference, str) or not reference:
        reference = "self-improve-evaluator"
    raw_summary = raw.get("summary")
    if not isinstance(raw_summary, str) or not raw_summary:
        raw_summary = "criterion evidence"
    evidence_status = status or raw.get("status")
    if evidence_status not in {"PASS", "FAIL", "BLOCKED"}:
        evidence_status = "BLOCKED"
    return {
        "kind": kind,
        "reference": reference,
        "status": evidence_status,
        "summary": summary or raw_summary,
        "observed_at": observed_at,
    }


def _compare_metric(observed: Any, operator: str, expected: Any) -> bool:
    """TaskGoal evaluation の小さな決定表。例外は FAIL として扱う。"""
    try:
        if operator == "eq":
            return observed == expected
        if operator == "ne":
            return observed != expected
        if operator == "lt":
            return observed < expected
        if operator == "lte":
            return observed <= expected
        if operator == "gt":
            return observed > expected
        if operator == "gte":
            return observed >= expected
        if operator == "contains":
            return expected in observed
    except (TypeError, ValueError):
        return False
    return False


def _metric_tool_status(scan: "ScanResult", metric: str) -> str:
    metric_status = scan.get("metric_status", {})
    if isinstance(metric_status, dict) and metric in metric_status:
        return str(metric_status[metric])
    tool_status = scan.get("tool_status", {})
    if not isinstance(tool_status, dict):
        return "PASS"
    aggregate_key = {
        "lint_errors": "lint",
        "test_failures": "test",
        "doc_issues": "documentation",
    }.get(metric)
    legacy_key = {
        "lint_errors": "ruff",
        "test_failures": "pytest",
        "doc_issues": "markdownlint",
    }.get(metric)
    if aggregate_key and aggregate_key in tool_status:
        return str(tool_status[aggregate_key])
    if legacy_key and legacy_key in tool_status:
        return str(tool_status[legacy_key])
    return "PASS"


def _validated_evidence_error(
    definition: Dict[str, Any],
    evidence: Dict[str, Any],
) -> str:
    evaluator = definition.get("evaluator_type")
    required = definition.get("evidence_required")
    if not isinstance(required, dict):
        return "evidence_requirement_invalid"

    required_kind = required.get("kind")
    required_reference = required.get("reference")
    if evidence.get("kind") != required_kind:
        return "evidence_kind_mismatch"
    if required_kind != _EVALUATOR_EVIDENCE_KIND.get(str(evaluator)):
        return "evidence_kind_mismatch"

    validation = evidence.get("validation")
    if not isinstance(validation, dict):
        return "validated_evidence_metadata_missing"
    if validation.get("reference_exists") is not True:
        return "test_report_missing" if evaluator == "test" else "evidence_reference_missing"
    if validation.get("reference_known") is not True:
        return "tool_result_unknown" if evaluator == "tool-result" else "evidence_reference_unknown"
    if evaluator == "human-approval" and validation.get("approval_valid") is not True:
        return "approval_invalid"

    if evaluator == "human-approval":
        valid_until_raw = validation.get("valid_until")
        if valid_until_raw:
            valid_until = _parse_utc_timestamp(valid_until_raw)
            observed_at = _parse_utc_timestamp(evidence.get("observed_at"))
            if valid_until is None or observed_at is None:
                return "approval_invalid"
            # 判定を決定的にするため、wall clock ではなく当該 Evidence の観測時刻で
            # approval の有効性を検証する。
            if valid_until < observed_at:
                return "approval_expired"

    if evidence.get("reference") != required_reference:
        return "evidence_reference_mismatch"
    if validation.get("outcome") != "VALID":
        reason = validation.get("reason")
        return reason if isinstance(reason, str) and reason else "validated_evidence_invalid"
    if evidence.get("status") not in {"PASS", "FAIL", "BLOCKED"}:
        return "evidence_status_invalid"
    return ""


def _evaluate_criteria(
    scan: "ScanResult",
    task_goal: "TaskGoal",
) -> List[Dict[str, Any]]:
    """scan の決定的 field または validated evidence だけで criterion を評価する。"""
    results: List[Dict[str, Any]] = []
    definitions = _criterion_definitions(task_goal)
    validated_by_id = scan.get("validated_criterion_evidence", {})  # type: ignore[typeddict-item]
    if not isinstance(validated_by_id, dict):
        validated_by_id = {}
    unvalidated_by_id = scan.get("criterion_evidence", {})  # type: ignore[typeddict-item]
    if not isinstance(unvalidated_by_id, dict):
        unvalidated_by_id = {}

    for definition in definitions:
        evaluator = definition.get("evaluator_type")
        criterion_id = definition.get("criterion_id")
        if evaluator not in _CRITERION_EVALUATOR_TYPES:
            results.append(_criterion_result(
                definition,
                "BLOCKED",
                [],
                "criterion evaluator_type is invalid",
            ))
            continue
        if not isinstance(criterion_id, str) or not criterion_id:
            results.append(_criterion_result(
                definition,
                "BLOCKED",
                [],
                "criterion_id is missing",
            ))
            continue

        evaluation = definition.get("evaluation")
        evaluation_dict = evaluation if isinstance(evaluation, dict) else {}
        metric = evaluation_dict.get("metric")
        if isinstance(metric, str) and metric:
            if metric not in scan["summary"]:
                results.append(_criterion_result(
                    definition,
                    "NOT_EVALUATED",
                    [],
                    f"scan.summary.{metric} evidence is unavailable",
                ))
                continue
            observed = scan["summary"][metric]  # type: ignore[literal-required]
            metric_tool_status = _metric_tool_status(scan, metric)
            operator = str(evaluation_dict.get("operator", "eq"))
            expected = evaluation_dict.get("expected")
            if operator not in {"eq", "ne", "lt", "lte", "gt", "gte", "contains"}:
                results.append(_criterion_result(
                    definition,
                    "BLOCKED",
                    [],
                    "criterion evaluation operator is invalid",
                ))
                continue
            if metric_tool_status in {
                "UNAVAILABLE", "BLOCKED", "NO_TESTS", "SKIP",
            }:
                evidence = [{
                    "kind": _EVALUATOR_EVIDENCE_KIND[evaluator],
                    "reference": f"scan.summary.{metric}",
                    "status": "BLOCKED",
                    "summary": (
                        f"required metric tool status={metric_tool_status}; "
                        f"observed={observed!r}"
                    ),
                    "observed_at": _utc_timestamp(),
                }]
                results.append(_criterion_result(
                    definition,
                    "BLOCKED",
                    evidence,
                    f"required metric tool was not executable: {metric_tool_status}",
                ))
                continue
            passed = (
                metric_tool_status != "FAIL"
                and _compare_metric(observed, operator, expected)
            )
            required_evidence = definition.get("evidence_required")
            required_kind = (
                required_evidence.get("kind")
                if isinstance(required_evidence, dict)
                else _EVALUATOR_EVIDENCE_KIND[evaluator]
            )
            reference = (
                required_evidence.get("reference")
                if isinstance(required_evidence, dict)
                else f"scan.summary.{metric}"
            )
            if (
                required_kind != _EVALUATOR_EVIDENCE_KIND[evaluator]
                or not isinstance(reference, str)
                or not reference
                or reference != f"scan.summary.{metric}"
            ):
                results.append(_criterion_result(
                    definition,
                    "BLOCKED",
                    [],
                    "evidence requirement does not match evaluator_type",
                ))
                continue
            status = "PASS" if passed else "FAIL"
            evidence = [{
                "kind": required_kind,
                "reference": reference,
                "status": status,
                "summary": (
                    f"tool_status={metric_tool_status}; observed={observed!r}; "
                    f"operator={operator}; expected={expected!r}"
                ),
                "observed_at": _utc_timestamp(),
            }]
            results.append(_criterion_result(
                definition,
                status,
                evidence,
                "deterministic scan metric satisfied" if passed else "deterministic scan metric did not satisfy criterion",
            ))
            continue

        raw_evidence_list = validated_by_id.get(criterion_id, [])
        if not isinstance(raw_evidence_list, list) or not raw_evidence_list:
            unvalidated_note = (
                "; unvalidated criterion_evidence was ignored"
                if unvalidated_by_id.get(criterion_id)
                else ""
            )
            results.append(_criterion_result(
                definition,
                "NOT_EVALUATED",
                [],
                "validated evidence is required but unavailable" + unvalidated_note,
            ))
            continue

        raw_evidence = raw_evidence_list[0]
        if not isinstance(raw_evidence, dict):
            results.append(_criterion_result(
                definition,
                "BLOCKED",
                [],
                "validated evidence item is invalid",
            ))
            continue
        error = _validated_evidence_error(definition, raw_evidence)
        if error:
            results.append(_criterion_result(
                definition,
                "BLOCKED",
                [_public_evidence(raw_evidence, status="BLOCKED", summary=error)],
                error,
            ))
            continue
        evidence_status = str(raw_evidence.get("status"))
        results.append(_criterion_result(
            definition,
            evidence_status,
            [_public_evidence(raw_evidence)],
            "validated criterion evidence satisfied" if evidence_status == "PASS" else "validated criterion evidence did not pass",
        ))
    return results


def _required_criteria_all_pass(results: List[Dict[str, Any]]) -> bool:
    required = [item for item in results if item.get("required_for_done") is True]
    return bool(required) and all(
        item.get("status") == "PASS"
        and isinstance(item.get("evidence"), list)
        and bool(item["evidence"])
        and all(
            isinstance(evidence, dict) and evidence.get("status") == "PASS"
            for evidence in item["evidence"]
        )
        for item in required
    )


def _required_criteria_unverifiable(results: List[Dict[str, Any]]) -> bool:
    return any(
        item.get("required_for_done") is True
        and item.get("status") in {"BLOCKED", "NOT_EVALUATED"}
        for item in results
    )


def _missing_required_criteria_results(reason_code: str) -> List[Dict[str, Any]]:
    """required criterion不在を空配列ではなく構造化BLOCKED evidenceで返す。"""
    definition = {
        "criterion_id": "GOAL-CONTRACT-REQUIRED-CRITERIA",
        "required_for_done": True,
        "evaluator_type": "rule",
    }
    evidence = [{
        "kind": "field-value",
        "reference": "task_goal.criterion_definitions",
        "status": "BLOCKED",
        "summary": reason_code,
        "observed_at": _utc_timestamp(),
    }]
    return [_criterion_result(definition, "BLOCKED", evidence, reason_code)]


def _scan_gate_failure(
    scan: "ScanResult",
    task_goal: Optional["TaskGoal"] = None,
) -> str:
    validator_errors = scan.get("contract_validator_errors", 0)  # type: ignore[typeddict-item]
    if not isinstance(validator_errors, (int, float, str)):
        return "contract_validator_error"
    try:
        if int(validator_errors or 0) > 0:
            return "contract_validator_error"
    except ValueError:
        return "contract_validator_error"
    if str(scan.get("security_status", "")).upper() == "FAIL":  # type: ignore[typeddict-item]
        return "security_failure"
    required_metrics = {
        str(item.get("evaluation", {}).get("metric"))
        for item in (
            _criterion_definitions(task_goal)
            if task_goal is not None
            else []
        )
        if item.get("required_for_done") is True
        and isinstance(item.get("evaluation"), dict)
        and item.get("evaluation", {}).get("metric")
    }
    for metric in sorted(required_metrics):
        status = _metric_tool_status(scan, metric)
        if status in {"UNAVAILABLE", "BLOCKED", "NO_TESTS", "SKIP"}:
            return f"required_tool_not_executed: {metric} ({status})"
    verification = _build_verification_result(scan, scan["quality_score"])
    if verification["verification_phases"].get("security") == "FAIL":
        return "security_failure"
    return ""


def _blocked_criterion_results(
    task_goal: "TaskGoal",
    reason_code: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for definition in _criterion_definitions(task_goal):
        evaluator = definition.get("evaluator_type")
        required = definition.get("evidence_required")
        kind = required.get("kind") if isinstance(required, dict) else None
        if kind not in _EVIDENCE_KINDS:
            kind = _EVALUATOR_EVIDENCE_KIND.get(str(evaluator), "field-value")
        reference = required.get("reference") if isinstance(required, dict) else None
        if not isinstance(reference, str) or not reference:
            reference = "self-improve-gate"
        evidence = [{
            "kind": kind,
            "reference": reference,
            "status": "BLOCKED",
            "summary": reason_code,
            "observed_at": _utc_timestamp(),
        }]
        results.append(_criterion_result(definition, "BLOCKED", evidence, reason_code))
    return results


def _empty_verification() -> "VerificationResult":
    return VerificationResult(
        after_quality_score=0,
        degraded=False,
        verification_phases={
            "build": "SKIP",
            "lint": "SKIP",
            "test": "SKIP",
            "security": "SKIP",
            "diff": "SKIP",
        },
        overall="BLOCKED",
        notes="not evaluated",
    )


def _blocked_verification(
    scan: Optional["ScanResult"],
    reason_code: str,
) -> "VerificationResult":
    result = (
        _build_verification_result(scan, scan["quality_score"])
        if scan is not None
        else _empty_verification()
    )
    result["overall"] = "BLOCKED"
    result["notes"] = reason_code
    return result


def _normalize_mutation_path(
    path: Any,
    repo_root: Path,
    *,
    allow_work: bool = False,
) -> str:
    if not isinstance(path, str):
        raise ValueError("mutation path must be a string")
    normalized = unicodedata.normalize("NFKC", path).strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or "\x00" in normalized
        or normalized.startswith("/")
        or PureWindowsPath(normalized).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", normalized))
    ):
        raise ValueError("unsafe absolute or empty mutation path")
    parts = Path(normalized).parts
    if ".." in parts:
        raise ValueError("unsafe traversal mutation path")
    if not allow_work and parts and parts[0].casefold() == "work":
        raise ValueError("work/ is not a mutation target")
    repo = repo_root.resolve()
    resolved = (repo / normalized).resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise ValueError("mutation path resolves outside repository") from exc
    return "/".join(part for part in parts if part not in ("", "."))


def _is_windows_reparse_point(path: Path) -> bool:
    """Python 3.11でもWindows junction/reparse pointを検出する。"""
    try:
        attributes = int(getattr(os.lstat(path), "st_file_attributes", 0))
    except (OSError, TypeError, ValueError):
        return False
    reparse_flag = int(
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    )
    return bool(attributes & reparse_flag)


def _is_symlink_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
    except OSError:
        return True
    return _is_windows_reparse_point(path)


def _path_has_symlink_component(path: str, repo_root: Path) -> bool:
    """repo相対pathの既存componentにsymlink/junctionがあればTrue。"""
    current = repo_root.resolve()
    for part in Path(path).parts:
        if part in ("", "."):
            continue
        current = current / part
        if _is_symlink_or_junction(current):
            return True
    return False


def _path_in_scope(path: str, scope_paths: List[str], repo_root: Path) -> bool:
    try:
        normalized = _normalize_mutation_path(path, repo_root)
    except ValueError:
        return False
    repo = repo_root.resolve()
    candidate = (repo / normalized).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError:
        return False
    for scope in scope_paths:
        scope_norm = scope.strip().replace("\\", "/").rstrip("/") or "."
        if scope_norm == ".":
            return True
        try:
            scope_norm = _normalize_mutation_path(scope_norm, repo_root)
        except ValueError:
            continue
        if _path_has_symlink_component(scope_norm, repo):
            continue
        scope_path = repo / scope_norm
        scope_canonical = scope_path.resolve()
        try:
            scope_canonical.relative_to(repo)
        except ValueError:
            continue
        if candidate == scope_canonical:
            return True
        # file scope が mutation で削除された後も directory scope へ昇格させない。
        if scope_path.is_dir() or not Path(scope_norm).suffix:
            try:
                candidate.relative_to(scope_canonical)
                return True
            except ValueError:
                pass
    return False


_MUTATION_PERMISSION_PATH_KEYS = (
    "path", "filePath", "file_path", "targetPath", "target_path",
)
_MUTATION_PERMISSION_COMMAND_KEYS = ("command", "cmd", "script")
_MUTATION_PERMISSION_PATCH_RE = re.compile(
    r"^\*\*\*\s+(?:Add|Update|Delete|Move)\s+File:\s+(.+?)\s*$",
    re.MULTILINE,
)


def _mutation_permission_allowed(
    request: Any,
    handler: Any,
    scope_paths: List[str],
    repo_root: Path,
) -> bool:
    """Mutation sessionのcommand実行とscope外file accessを事前拒否する。"""
    operation = handler._extract_operation(request)
    if re.search(
        r"\bgit\s+(?:add|commit|push|reset|checkout|clean|restore|stash|"
        r"switch|merge|rebase|cherry-pick|rm|mv)\b",
        operation,
        re.IGNORECASE,
    ):
        return False

    if isinstance(request, dict):
        tool_name = str(
            request.get("tool_name") or request.get("toolName") or ""
        )
        arguments = request.get("arguments") or {}
    else:
        tool_name = str(
            getattr(request, "tool_name", "")
            or getattr(request, "toolName", "")
        )
        arguments = getattr(request, "arguments", {}) or {}
    if not isinstance(arguments, dict):
        return False

    # Mutation phaseはfile toolだけで変更する。shell経由の副作用を許可しない。
    if any(str(arguments.get(key) or "").strip() for key in _MUTATION_PERMISSION_COMMAND_KEYS):
        return False

    paths = [
        str(arguments[key])
        for key in _MUTATION_PERMISSION_PATH_KEYS
        if arguments.get(key)
    ]
    patch_text = arguments.get("input") or arguments.get("patch") or ""
    if isinstance(patch_text, str):
        for match in _MUTATION_PERMISSION_PATCH_RE.finditer(patch_text):
            patch_path = match.group(1).strip()
            if " -> " in patch_path:
                source_path, destination_path = patch_path.split(" -> ", 1)
                paths.extend((source_path.strip(), destination_path.strip()))
            else:
                paths.append(patch_path)

    is_file_mutation = any(
        token in tool_name.lower()
        for token in ("write", "edit", "create", "delete", "patch", "replace", "move", "rename")
    )
    if is_file_mutation and not paths:
        return False

    for path in paths:
        try:
            normalized = _normalize_mutation_path(path, repo_root)
        except ValueError:
            return False
        if not _path_in_scope(normalized, scope_paths, repo_root):
            return False

    return bool(handler.handle(request))


def _parse_mutation_response(
    raw_text: str,
    repo_root: Path,
    scope_paths: List[str],
) -> Dict[str, Any]:
    """Copilot mutation response を追加文なしの厳格 JSON object として検証する。"""
    try:
        payload = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("mutation response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("mutation response must be a JSON object")
    if set(payload) != _MUTATION_RESPONSE_FIELDS:
        raise ValueError("mutation response fields do not match schema")

    status = payload.get("status")
    changed_files = payload.get("changed_files")
    failed_changes = payload.get("failed_changes")
    no_change_reason = payload.get("no_change_reason")
    response_summary = payload.get("response_summary")
    if status not in _MUTATION_STATUSES:
        raise ValueError("mutation response status is invalid")
    if not isinstance(changed_files, list) or not all(isinstance(item, str) for item in changed_files):
        raise ValueError("changed_files must be a string array")
    if not isinstance(failed_changes, list):
        raise ValueError("failed_changes must be an object array")
    if (
        not isinstance(no_change_reason, str)
        or not isinstance(response_summary, str)
        or not response_summary.strip()
    ):
        raise ValueError("mutation response string fields are invalid")

    normalized_changed: List[str] = []
    for item in changed_files:
        normalized = _normalize_mutation_path(item, repo_root)
        if not _path_in_scope(normalized, scope_paths, repo_root):
            raise ValueError("claimed changed path is outside target scope")
        normalized_changed.append(normalized)
    if len(set(normalized_changed)) != len(normalized_changed):
        raise ValueError("changed_files contains duplicates")

    normalized_failed: List[Dict[str, str]] = []
    for item in failed_changes:
        if not isinstance(item, dict) or set(item) != {"path", "error"}:
            raise ValueError("failed_changes item does not match schema")
        failed_path = _normalize_mutation_path(item.get("path"), repo_root)
        error = item.get("error")
        if not isinstance(error, str) or not error.strip():
            raise ValueError("failed_changes error must be non-empty")
        if not _path_in_scope(failed_path, scope_paths, repo_root):
            raise ValueError("failed path is outside target scope")
        normalized_failed.append({"path": failed_path, "error": error})
    failed_paths = [item["path"] for item in normalized_failed]
    if len(set(failed_paths)) != len(failed_paths):
        raise ValueError("failed_changes contains duplicate paths")
    if set(normalized_changed) & set(failed_paths):
        raise ValueError("a path cannot be both changed and failed")

    if status == "MUTATED" and (
        not normalized_changed or normalized_failed or no_change_reason
    ):
        raise ValueError("MUTATED status invariants are invalid")
    if status == "PARTIAL_FAILURE" and (
        not normalized_failed or no_change_reason
    ):
        raise ValueError("PARTIAL_FAILURE status invariants are invalid")
    if status == "IMPROVEMENT_NOT_NEEDED" and (
        normalized_changed or normalized_failed or not no_change_reason.strip()
    ):
        raise ValueError("IMPROVEMENT_NOT_NEEDED status invariants are invalid")

    return {
        "status": status,
        "changed_files": normalized_changed,
        "failed_changes": normalized_failed,
        "no_change_reason": no_change_reason,
        "response_summary": response_summary,
    }


def _git_name_list(repo_root: Path, args: List[str]) -> List[str]:
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def _git_worktree_state(repo_root: Path) -> Dict[str, str]:
    """HEAD に対する dirty path と現在内容の fingerprint を返す（read-only）。"""
    tracked = _git_name_list(
        repo_root,
        ["diff", "--name-only", "-z", "HEAD", "--"],
    )
    untracked = _git_name_list(
        repo_root,
        ["ls-files", "--others", "--exclude-standard", "-z", "--"],
    )
    state: Dict[str, str] = {}
    for raw_path in dict.fromkeys([*tracked, *untracked]):
        try:
            # Git state は許可リストではなく実変更の正本なので work/ も保持する。
            # 後段の _path_in_scope が work/ を scope外として block する。
            path = _normalize_mutation_path(
                raw_path,
                repo_root,
                allow_work=True,
            )
        except ValueError:
            # Git 自身が repo 内 path を返すが、不正名だけは安全に除外する。
            continue
        full_path = repo_root / path
        if not full_path.exists():
            state[path] = "<deleted>"
            continue
        if not full_path.is_file():
            state[path] = "<non-file>"
            continue
        try:
            state[path] = hashlib.sha256(full_path.read_bytes()).hexdigest()
        except OSError:
            state[path] = "<unreadable>"
    return state


def _git_iteration_delta(
    before: Dict[str, str],
    after: Dict[str, str],
) -> List[str]:
    return sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


def _iter_scope_files(repo_root: Path, scope_paths: List[str]) -> List[Path]:
    return [path for _relative, path in _scope_files(repo_root, scope_paths)]


def _is_test_artifact(path: str) -> bool:
    lowered = path.replace("\\", "/").casefold()
    parts = lowered.split("/")
    name = parts[-1]
    return (
        any(part in {"test", "tests"} or part.endswith(".tests") for part in parts[:-1])
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
        or name.endswith("tests.cs")
    )


_TEST_SKIP_PATTERNS = (
    re.compile(r"@\s*pytest\.mark\.skip(?:if)?\b", re.IGNORECASE),
    re.compile(r"\bpytest\.skip\s*\(", re.IGNORECASE),
    re.compile(r"@\s*unittest\.skip(?:if|unless)?\b", re.IGNORECASE),
    re.compile(r"\[\s*(?:Fact|Theory)\s*\([^\]]*\bSkip\s*=", re.IGNORECASE),
    re.compile(r"\b(?:test|it|describe)\.skip\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:xit|xdescribe)\s*\(", re.IGNORECASE),
)


def _test_skip_marker_count(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in _TEST_SKIP_PATTERNS)


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _capture_protected_artifacts(
    repo_root: Path,
    scope_paths: List[str],
    task_goal: "TaskGoal",
) -> Dict[str, Any]:
    """弱体化してはならない criterion/test/policy の小さな baseline を採る。"""
    files = _iter_scope_files(repo_root, scope_paths)
    by_rel = {
        str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/"): path
        for path in files
    }

    # Criterion source は宣言scope外でも比較対象に含める（変更された場合は
    # scope外diff gateも同時に作動する）。
    criterion_sources: Dict[str, Dict[str, Any]] = {}
    declared_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for definition in _criterion_definitions(task_goal):
        source = definition.get("source")
        if not isinstance(source, str) or not source:
            continue
        try:
            source_rel = _normalize_mutation_path(source, repo_root)
        except ValueError:
            continue
        declared_by_source.setdefault(source_rel, []).append(definition)

    for source_rel, declared_definitions in declared_by_source.items():
        source_path = repo_root / source_rel
        payload = _read_json_object(source_path)
        raw_definitions = payload.get("criterion_definitions", []) if payload else []
        if not isinstance(raw_definitions, list):
            raw_definitions = []
        definitions_for_snapshot = (
            raw_definitions if source_path.is_file() else declared_definitions
        )
        criterion_sources[source_rel] = {
            "exists": source_path.is_file(),
            "definitions": {
                str(item.get("criterion_id")): {
                    "required_for_done": item.get("required_for_done"),
                    "evaluator_type": item.get("evaluator_type"),
                    "evidence_required": item.get("evidence_required"),
                }
                for item in definitions_for_snapshot
                if isinstance(item, dict) and item.get("criterion_id")
            }
        }

    tests: Dict[str, str] = {}
    policies: Dict[str, Dict[str, Any]] = {}
    for rel, path in by_rel.items():
        if _is_test_artifact(rel):
            try:
                tests[rel] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        if path.suffix.casefold() == ".json":
            payload = _read_json_object(path)
            if payload is not None:
                policies[rel] = payload
    return {
        "criterion_sources": criterion_sources,
        "tests": tests,
        "policies": policies,
    }


def _policy_values(payload: Any, key: str) -> List[Any]:
    found: List[Any] = []
    if isinstance(payload, dict):
        for current_key, value in payload.items():
            if str(current_key).casefold() == key.casefold():
                found.append(value)
            found.extend(_policy_values(value, key))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(_policy_values(value, key))
    return found


def _string_set(values: List[Any]) -> set[str]:
    result: set[str] = set()
    for value in values:
        if isinstance(value, list):
            result.update(str(item) for item in value)
        elif isinstance(value, str):
            result.add(value)
    return result


def _protected_artifact_delta(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []

    before_sources = before.get("criterion_sources", {})
    after_sources = after.get("criterion_sources", {})
    for path, before_source in before_sources.items():
        after_source = after_sources.get(path, {})
        before_definitions = before_source.get("definitions", {})
        after_definitions = after_source.get("definitions", {})
        for criterion_id, baseline in before_definitions.items():
            current = after_definitions.get(criterion_id)
            if (
                current != baseline
                or (
                    before_source.get("exists") is True
                    and after_source.get("exists") is not True
                )
            ):
                deltas.append({
                    "kind": "criterion-definition-changed",
                    "path": path,
                    "criterion_id": criterion_id,
                    "summary": "required criterion definition was deleted or changed",
                })

    before_tests: Dict[str, str] = before.get("tests", {})
    after_tests: Dict[str, str] = after.get("tests", {})
    after_hashes: Dict[str, List[str]] = {}
    for path, text in after_tests.items():
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        after_hashes.setdefault(digest, []).append(path)
    for path, baseline_text in before_tests.items():
        current_text = after_tests.get(path)
        if current_text is None:
            digest = hashlib.sha256(baseline_text.encode("utf-8")).hexdigest()
            renamed_to = [candidate for candidate in after_hashes.get(digest, []) if candidate != path]
            deltas.append({
                "kind": "test-renamed" if renamed_to else "test-deleted",
                "path": path,
                "renamed_to": renamed_to[0] if renamed_to else "",
                "summary": "protected test artifact was renamed" if renamed_to else "protected test artifact was deleted",
            })
            continue
        if _test_skip_marker_count(current_text) > _test_skip_marker_count(baseline_text):
            deltas.append({
                "kind": "test-skip-added",
                "path": path,
                "summary": "test skip marker was added",
            })

    before_policies: Dict[str, Dict[str, Any]] = before.get("policies", {})
    after_policies: Dict[str, Dict[str, Any]] = after.get("policies", {})
    for path, baseline in before_policies.items():
        current = after_policies.get(path, {})
        before_permissions = _string_set(_policy_values(baseline, "permissions"))
        after_permissions = _string_set(_policy_values(current, "permissions"))
        if after_permissions - before_permissions:
            deltas.append({
                "kind": "permission-expanded",
                "path": path,
                "summary": "permission set expanded",
            })
        before_roles = _string_set(_policy_values(baseline, "rbac_roles"))
        after_roles = _string_set(_policy_values(current, "rbac_roles"))
        if after_roles - before_roles:
            deltas.append({
                "kind": "rbac-expanded",
                "path": path,
                "summary": "RBAC role set expanded",
            })
        before_hitl = _policy_values(baseline, "hitl_required")
        after_hitl = _policy_values(current, "hitl_required")
        if any(value is True for value in before_hitl) and not any(value is True for value in after_hitl):
            deltas.append({
                "kind": "hitl-weakened",
                "path": path,
                "summary": "HITL requirement was disabled or removed",
            })
        before_guardrail = _policy_values(baseline, "guardrail_enabled")
        after_guardrail = _policy_values(current, "guardrail_enabled")
        if any(value is True for value in before_guardrail) and not any(value is True for value in after_guardrail):
            deltas.append({
                "kind": "guardrail-weakened",
                "path": path,
                "summary": "guardrail was disabled or removed",
            })
        before_approvals = _string_set(_policy_values(baseline, "approval_conditions"))
        after_approvals = _string_set(_policy_values(current, "approval_conditions"))
        if before_approvals - after_approvals:
            deltas.append({
                "kind": "approval-condition-removed",
                "path": path,
                "summary": "approval condition was removed",
            })
    return deltas


def _build_iteration_plan(
    scan: "ScanResult",
    criterion_results: List[Dict[str, Any]],
    task_goal: "TaskGoal",
) -> Dict[str, Any]:
    failed = [
        item for item in criterion_results
        if item.get("status") == "FAIL"
    ]
    criterion_ids = [str(item.get("criterion_id")) for item in failed]
    root_cause = "; ".join(
        str(item.get("reason") or item.get("criterion_id")) for item in failed
    ) or _build_plan_summary(scan, task_goal) or "quality threshold is not yet satisfied"
    return {
        "criterion_ids": criterion_ids,
        "root_cause": root_cause,
        "minimal_change": "Change only the resolved target paths needed to satisfy the failed criteria.",
    }


def _build_mutation_prompt(
    scan: "ScanResult",
    task_goal: "TaskGoal",
    criterion_results: List[Dict[str, Any]],
    plan: Dict[str, Any],
    scope_paths: List[str],
    learning_summary: str,
) -> str:
    definitions = _criterion_definitions(task_goal)
    return f"""You are executing HVE Post-DAG Self-Improve MUTATE.
Perform actual minimal file edits. Do not merely describe changes.
Only edit the resolved repository-relative target paths listed below. Never edit work/,
tests to weaken/skip them, criterion definitions, permissions, RBAC, HITL, approvals,
or guardrails. Do not commit, revert, reset, clean, or discard pre-existing changes.

## Goal
{task_goal.get('goal_description', '')}

## Resolved target paths
{json.dumps(scope_paths, ensure_ascii=False, indent=2)}

## Criterion definitions (source/evaluator/evidence are binding)
{json.dumps(definitions, ensure_ascii=False, indent=2)}

## Before criterion results
{json.dumps(criterion_results, ensure_ascii=False, indent=2)}

## Scan summary
{json.dumps(scan.get('summary', {}), ensure_ascii=False, indent=2)}

## Plan
{json.dumps(plan, ensure_ascii=False, indent=2)}

## Previous learning summary
{learning_summary[:LEARNING_SUMMARY_MAX_LENGTH]}

After editing, return exactly one JSON object and no Markdown/code fence:
{{
  "status": "MUTATED|PARTIAL_FAILURE|IMPROVEMENT_NOT_NEEDED",
  "changed_files": ["repo/relative/path"],
  "failed_changes": [{{"path": "repo/relative/path", "error": "short error"}}],
  "no_change_reason": "non-empty only for IMPROVEMENT_NOT_NEEDED",
  "response_summary": "short non-sensitive summary"
}}
"""


def _object_value(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _response_usage_tokens(response: Any) -> Optional[int]:
    data = _object_value(response, "data")
    usage = _object_value(data, "usage") if data is not None else None
    if usage is None:
        usage = _object_value(response, "usage")
    if usage is None:
        return None
    total = _object_value(usage, "total_tokens", "totalTokens")
    if total is not None:
        try:
            parsed = int(total)
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None
    input_tokens = _object_value(usage, "input_tokens", "inputTokens")
    output_tokens = _object_value(usage, "output_tokens", "outputTokens")
    if input_tokens is None or output_tokens is None:
        return None
    try:
        parsed_input = int(input_tokens)
        parsed_output = int(output_tokens)
    except (TypeError, ValueError):
        return None
    if parsed_input < 0 or parsed_output < 0:
        return None
    return parsed_input + parsed_output


def _finite_mutation_timeout(config: Any) -> float:
    try:
        configured = float(getattr(config, "timeout_seconds", _MUTATION_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        configured = _MUTATION_TIMEOUT_SECONDS
    if not math.isfinite(configured) or configured <= 0:
        configured = _MUTATION_TIMEOUT_SECONDS
    return min(configured, _MUTATION_TIMEOUT_SECONDS)


def _criteria_pass_to_fail(
    before: List[Dict[str, Any]],
    after: List[Dict[str, Any]],
) -> bool:
    before_by_id = {item.get("criterion_id"): item for item in before}
    after_by_id = {item.get("criterion_id"): item for item in after}
    return any(
        item.get("required_for_done") is True
        and item.get("status") == "PASS"
        and after_by_id.get(criterion_id, {}).get("status") != "PASS"
        for criterion_id, item in before_by_id.items()
    )


# ---------------------------------------------------------------------------
# メインループ
# ---------------------------------------------------------------------------


def run_improvement_loop(
    config: Any,
    work_dir: Optional[Path] = None,
    repo_root: Optional[str] = None,
    task_goal: Optional["TaskGoal"] = None,
) -> "SelfImproveResult":
    """自己改善ループのエントリポイント。

        各イテレーションを SCAN → PLAN → Copilot SDK MUTATE → VERIFY →
        Git DIFF の順に実行する。TaskGoal の required criterion は決定的な
        scan field または validated evidence だけで評価し、score より先に判定する。

    停止条件の優先順位:
            1. degradation / protected artifact の弱体化
            2. partial failure / scope外diff / evidence不足等の blocked
            3. threshold_reached / no_improvement_needed
            4. plateau_reached / cost_limit / max_iterations

        request/token 上限は実 send 回数と SDK response usage metadata で計測する。

    Args:
        config: SDKConfig インスタンス。
        work_dir: 学習ログ保存ディレクトリ（None の場合は `work/run/<run-id>/self-improve/`）。
        repo_root: リポジトリルートディレクトリ。
        task_goal: タスク固有ゴール。None の場合は config の workflow_id と goal から自動生成。

    Returns:
        SelfImproveResult 型の辞書。
    """
    _empty_result = SelfImproveResult(
        iterations_completed=0,
        final_score=0,
        records=[],
        stopped_reason="",
        reward_history=[],
        final_goal_achievement_pct=0.0,
        final_criterion_results=[],
        final_verification=_empty_verification(),
        blocked_reason="",
    )

    if config.dry_run:
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "dry_run"})

    if config.self_improve_skip or not config.auto_self_improve:
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "disabled"})

    # scope="disabled" の場合は実行しない
    _si_scope = getattr(config, "self_improve_scope", "")
    if _si_scope == "disabled":
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "disabled"})

    _run_id = getattr(config, "run_id", "")
    if not _run_id:
        _run_id = generate_run_id()
        setattr(config, "run_id", _run_id)
    if work_dir is None:
        try:
            from hve.split_fork import resolve_work_root as _rwr
        except ImportError:  # pragma: no cover - script execution path
            from split_fork import resolve_work_root as _rwr  # type: ignore[no-redef]
        _work_dir = _rwr() / "self-improve"
    else:
        _work_dir = work_dir

    # ロック取得（競合制御）
    if not _acquire_lock(_work_dir):
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "locked"})

    effective_repo = Path(repo_root or ".").resolve()

    # 追跡性: 現在のブランチを記録（直接 push のリスクをユーザーに明示する）
    # ⚠️ self-improve はカレントブランチへ直接コミット/push する可能性があります。
    #    重要なブランチ（main 等）で実行する場合はあらかじめ別ブランチを作成してください。
    try:
        _current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(effective_repo),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        _current_branch = "(unknown)"
    print(
        f"[self-improve] run_id={_run_id} / branch={_current_branch} / "
        f"work_dir={_work_dir}\n"
        "⚠️  self-improve はこのブランチに直接変更を加えます。"
        " 重要なブランチで実行する場合は事前に別ブランチを作成してください。",
        flush=True,
    )

    # タスクゴールの確定（TDD 的: ループ開始前に成功条件を定義する）
    _workflow_id = getattr(config, "workflow_id", "")
    _user_goal = getattr(config, "self_improve_goal", "")
    effective_goal: "TaskGoal" = task_goal or define_task_goal(_workflow_id, _user_goal)

    records: List["ImprovementRecord"] = []
    reward_history: List[float] = []
    stopped_reason = "max_iterations"
    blocked_reason = ""
    current_score = 0
    final_goal_achievement_pct = 0.0
    final_criterion_results: List[Dict[str, Any]] = []
    final_verification = _empty_verification()
    request_count = 0
    token_count = 0

    try:
        max_iterations = max(0, int(getattr(config, "self_improve_max_iterations", 0)))
        max_requests = int(getattr(config, "self_improve_max_requests", 0))
        max_tokens = int(getattr(config, "self_improve_max_tokens", 0))
    except (TypeError, ValueError):
        max_iterations = 0
        max_requests = 0
        max_tokens = 0
    threshold = float(getattr(
        config,
        "self_improve_quality_threshold",
        DEFAULT_QUALITY_THRESHOLD,
    ))
    timeout = _finite_mutation_timeout(config)

    try:
        scope_paths = _resolve_target_scope_paths(
            getattr(config, "self_improve_target_scope", ""),
            step_output_paths=getattr(config, "_resolved_step_output_paths", None),
            workflow_default=getattr(config, "_resolved_workflow_default", ""),
            repo_root=str(effective_repo),
        )
    except ValueError as exc:
        scope_paths = []
        blocked_reason = f"target_scope_invalid: {exc}"

    # AAG/AAGDではworkflow registry由来の出力pathを変更可能範囲の上限とする。
    # 明示target_scopeはその部分集合への絞り込みだけを許可し、"."や"*"で
    # 他workflow成果物へ拡張できないようにする。
    scope_ceiling_raw = getattr(config, "_resolved_scope_ceiling_paths", None)
    if scope_paths and scope_ceiling_raw is not None:
        try:
            scope_ceiling = _resolve_target_scope_paths(
                "",
                step_output_paths=list(scope_ceiling_raw),
                workflow_default="",
                repo_root=str(effective_repo),
            )
        except (TypeError, ValueError):
            scope_ceiling = []
        outside_ceiling = [
            path
            for path in scope_paths
            if not _path_in_scope(path, scope_ceiling, effective_repo)
        ]
        if not scope_ceiling or outside_ceiling:
            scope_paths = []
            blocked_reason = (
                "target_scope_exceeds_workflow_outputs"
                + (f": {', '.join(outside_ceiling)}" if outside_ceiling else "")
            )

    scope_precondition_error = str(
        getattr(config, "_resolved_scope_precondition_error", "") or ""
    )
    if scope_precondition_error:
        scope_paths = []
        blocked_reason = scope_precondition_error

    required_definitions = [
        item
        for item in _criterion_definitions(effective_goal)
        if item.get("required_for_done") is True
    ]
    require_deterministic_criteria = _workflow_id in {"aag", "aagd"}
    if require_deterministic_criteria and not required_definitions:
        blocked_reason = blocked_reason or "goal_contract_required_criteria_missing"
        final_criterion_results = _missing_required_criteria_results(
            blocked_reason
        )
        final_verification = _blocked_verification(None, blocked_reason)
        scope_paths = []

    # 初回SCANで終了する場合は SDK resource を一切作らない。
    sdk_loop: Optional[asyncio.AbstractEventLoop] = None
    mutation_client: Any = None
    mutation_session: Any = None
    permission_handler: Any = None

    def _run_async(awaitable: Any, wait_timeout: float) -> Any:
        if sdk_loop is None:  # pragma: no cover - caller invariant
            raise RuntimeError("mutation event loop is not initialized")
        return sdk_loop.run_until_complete(
            asyncio.wait_for(awaitable, timeout=wait_timeout)
        )

    def _ensure_mutation_session() -> Any:
        nonlocal sdk_loop, mutation_client, mutation_session, permission_handler
        if mutation_session is not None:
            return mutation_session
        if sdk_loop is None:
            sdk_loop = asyncio.new_event_loop()
        try:
            from .copilot_client_factory import create_copilot_client
            from .config import to_wire_model
            from .permission_handler import ScopedPermissionHandler
        except ImportError:
            from copilot_client_factory import create_copilot_client  # type: ignore[no-redef]
            from config import to_wire_model  # type: ignore[no-redef]
            from permission_handler import ScopedPermissionHandler  # type: ignore[no-redef, import-not-found]

        mutation_client = create_copilot_client(
            cli_path=getattr(config, "cli_path", None),
            cli_url=getattr(config, "cli_url", None),
            github_token=getattr(config, "github_token", "") or None,
            log_level=getattr(config, "log_level", "error"),
            cli_args=getattr(config, "cli_args", None),
            working_directory=str(effective_repo),
        )
        _run_async(mutation_client.start(), timeout)
        permission_handler = ScopedPermissionHandler(strict=False)

        def _mutation_permission(request: Any) -> bool:
            return _mutation_permission_allowed(
                request,
                permission_handler,
                scope_paths,
                effective_repo,
            )

        session_options: Dict[str, Any] = {
            "on_permission_request": _mutation_permission,
            "streaming": False,
        }
        wire_model = to_wire_model(getattr(config, "model", ""))
        if wire_model:
            session_options["model"] = wire_model
        if getattr(config, "available_tools", None) is not None:
            session_options["available_tools"] = config.available_tools
        if getattr(config, "excluded_tools", None) is not None:
            session_options["excluded_tools"] = config.excluded_tools
        mutation_session = _run_async(
            mutation_client.create_session(**session_options),
            timeout,
        )
        return mutation_session

    initial_dirty_state: Dict[str, str] = {}

    try:
        if not scope_paths:
            stopped_reason = "blocked"
            blocked_reason = blocked_reason or "target_scope_empty_or_unsafe"
            if not final_criterion_results:
                final_criterion_results = _blocked_criterion_results(
                    effective_goal,
                    blocked_reason,
                )
            if not final_criterion_results:
                final_criterion_results = _missing_required_criteria_results(
                    blocked_reason,
                )
            final_verification = _blocked_verification(None, blocked_reason)
        else:
            initial_dirty_state = _git_worktree_state(effective_repo)

        while scope_paths and len(records) < max_iterations:
            iteration = len(records) + 1
            iter_start = time.time()

            # SCAN
            scan = scan_codebase(
                target_scope=config.self_improve_target_scope,
                repo_root=str(effective_repo),
                step_output_paths=getattr(config, "_resolved_step_output_paths", None),
                workflow_default=getattr(config, "_resolved_workflow_default", ""),
                resolved_scope_paths=scope_paths,
            )
            before_score = scan["quality_score"]
            current_score = before_score
            goal_achievement = _compute_goal_achievement(scan, effective_goal)
            final_goal_achievement_pct = goal_achievement
            before_criteria = _evaluate_criteria(scan, effective_goal)
            final_criterion_results = before_criteria
            final_verification = _build_verification_result(scan, before_score)

            gate_failure = _scan_gate_failure(scan, effective_goal)
            if gate_failure:
                stopped_reason = "blocked"
                blocked_reason = gate_failure
                final_criterion_results = _blocked_criterion_results(
                    effective_goal,
                    gate_failure,
                )
                final_verification = _blocked_verification(scan, gate_failure)
                break
            if _required_criteria_unverifiable(before_criteria):
                stopped_reason = "blocked"
                blocked_reason = "required_criterion_validated_evidence_missing"
                final_verification = _blocked_verification(scan, blocked_reason)
                break
            if (
                (
                    _required_criteria_all_pass(before_criteria)
                    if required_definitions
                    else not require_deterministic_criteria
                )
                and scan["summary"]["test_failures"] == 0
                and final_verification["overall"] == "PASS"
                and goal_achievement * 100 >= threshold
            ):
                stopped_reason = (
                    "no_improvement_needed" if not records else "threshold_reached"
                )
                break
            if max_requests <= request_count or max_tokens <= token_count:
                stopped_reason = "cost_limit"
                break

            # PLAN
            plan = _build_iteration_plan(scan, before_criteria, effective_goal)
            plan_summary = _build_plan_summary(scan, effective_goal) or str(plan["root_cause"])
            prompt_paths = list(scope_paths)
            for path in _iter_scope_files(effective_repo, scope_paths):
                rel = str(path.resolve().relative_to(effective_repo)).replace("\\", "/")
                if rel not in prompt_paths:
                    prompt_paths.append(rel)
            prompt = _build_mutation_prompt(
                scan,
                effective_goal,
                before_criteria,
                plan,
                prompt_paths,
                get_learning_summary(_work_dir, len(records)),
            )
            iteration_git_before = _git_worktree_state(effective_repo)
            protected_before = _capture_protected_artifacts(
                effective_repo,
                scope_paths,
                effective_goal,
            )

            # MUTATE
            try:
                session = _ensure_mutation_session()
                request_count += 1
                response = _run_async(
                    session.send_and_wait(prompt, timeout=timeout),
                    timeout + 1.0,
                )
                mutation = _parse_mutation_response(
                    _extract_llm_response_text(response),
                    effective_repo,
                    scope_paths,
                )
            except Exception as exc:
                stopped_reason = "blocked"
                blocked_reason = f"mutation_failed: {type(exc).__name__}: {exc}"
                final_verification = _blocked_verification(scan, blocked_reason)
                break

            used_tokens = _response_usage_tokens(response)
            if used_tokens is None:
                stopped_reason = "blocked"
                blocked_reason = "mutation usage metadata is missing or invalid"
                final_verification = _blocked_verification(scan, blocked_reason)
                break
            token_count += used_tokens

            if mutation["status"] == "IMPROVEMENT_NOT_NEEDED":
                stopped_reason = "blocked"
                blocked_reason = "late_improvement_not_needed_without_passing_scan"
                final_verification = _blocked_verification(scan, blocked_reason)
                break

            iteration_git_after = _git_worktree_state(effective_repo)
            actual_changed_files = _git_iteration_delta(
                iteration_git_before,
                iteration_git_after,
            )
            protected_after = _capture_protected_artifacts(
                effective_repo,
                scope_paths,
                effective_goal,
            )
            protected_delta = _protected_artifact_delta(
                protected_before,
                protected_after,
            )

            # VERIFY（partial failure でも診断目的で一度だけ実行する）
            after_scan = scan_codebase(
                target_scope=config.self_improve_target_scope,
                repo_root=str(effective_repo),
                step_output_paths=getattr(config, "_resolved_step_output_paths", None),
                workflow_default=getattr(config, "_resolved_workflow_default", ""),
                resolved_scope_paths=scope_paths,
            )
            after_score = after_scan["quality_score"]
            final_goal_achievement_pct = _compute_goal_achievement(after_scan, effective_goal)
            after_criteria = _evaluate_criteria(after_scan, effective_goal)
            final_criterion_results = after_criteria
            outside_scope = [
                path for path in actual_changed_files
                if not _path_in_scope(path, scope_paths, effective_repo)
            ]
            response_diff_mismatch = (
                set(actual_changed_files) != set(mutation["changed_files"])
            )
            degraded = (
                after_score < before_score
                or after_scan["summary"]["test_failures"] > scan["summary"]["test_failures"]
                or _criteria_pass_to_fail(before_criteria, after_criteria)
                or bool(protected_delta)
            )
            verification = _build_verification_result(after_scan, before_score)
            verification["degraded"] = degraded
            verification["verification_phases"]["diff"] = (
                "PASS"
                if actual_changed_files and not outside_scope and not response_diff_mismatch
                else "FAIL"
            )

            reward_signal = calculate_reward(scan, after_scan, effective_goal, reward_history)
            reward_history.append(reward_signal["reward"])

            # TDD フェーズを effective_goal へ反映（GREEN → REFACTOR への昇格）
            if reward_signal["tdd_phase"] != effective_goal["tdd_phase"]:
                effective_goal = TaskGoal(**{**dict(effective_goal), "tdd_phase": reward_signal["tdd_phase"]})  # type: ignore[misc]

            record = ImprovementRecord(
                iteration=iteration,
                before_score=before_score,
                after_score=after_score,
                degraded=degraded,
                plan_summary=plan_summary,
                verification=verification,
                reward_signal=reward_signal,
                elapsed_seconds=time.time() - iter_start,
                plan=plan,
                changed_files=actual_changed_files,
                preexisting_changed_files=sorted(initial_dirty_state),
                failed_changes=mutation["failed_changes"],
                before_criteria=before_criteria,
                after_criteria=after_criteria,
                protected_artifact_delta=protected_delta,
            )
            records.append(record)
            record_learning(_work_dir, iteration, record, effective_goal)
            current_score = after_score
            final_verification = verification

            # degradation は score 上昇より強い停止条件。
            if degraded:
                stopped_reason = "degradation"
                verification["overall"] = "FAIL"
                verification["notes"] = "protected artifact or required criterion degraded"
                break
            if mutation["status"] == "PARTIAL_FAILURE":
                stopped_reason = "blocked"
                blocked_reason = "mutation_partial_failure"
                verification["overall"] = "BLOCKED"
                verification["notes"] = blocked_reason
                break
            if not actual_changed_files:
                stopped_reason = "blocked"
                blocked_reason = "mutation_no_diff"
                verification["overall"] = "BLOCKED"
                verification["notes"] = blocked_reason
                break
            if outside_scope:
                stopped_reason = "blocked"
                blocked_reason = "scope_outside_diff: " + ", ".join(outside_scope)
                verification["overall"] = "BLOCKED"
                verification["notes"] = blocked_reason
                break
            if response_diff_mismatch:
                stopped_reason = "blocked"
                blocked_reason = "mutation_response_diff_mismatch"
                verification["overall"] = "BLOCKED"
                verification["notes"] = blocked_reason
                break
            after_gate_failure = _scan_gate_failure(after_scan, effective_goal)
            if after_gate_failure:
                stopped_reason = "blocked"
                blocked_reason = after_gate_failure
                final_criterion_results = _blocked_criterion_results(
                    effective_goal,
                    after_gate_failure,
                )
                final_verification = _blocked_verification(after_scan, after_gate_failure)
                break
            if _required_criteria_unverifiable(after_criteria):
                stopped_reason = "blocked"
                blocked_reason = "required_criterion_validated_evidence_missing"
                verification["overall"] = "BLOCKED"
                verification["notes"] = blocked_reason
                break
            if (
                (
                    _required_criteria_all_pass(after_criteria)
                    if required_definitions
                    else not require_deterministic_criteria
                )
                and after_scan["summary"]["test_failures"] == 0
                and verification["overall"] == "PASS"
                and final_goal_achievement_pct * 100 >= threshold
            ):
                stopped_reason = "threshold_reached"
                break
            if reward_signal["plateau_detected"]:
                stopped_reason = "plateau_reached"
                break
            if max_requests <= request_count or max_tokens <= token_count:
                stopped_reason = "cost_limit"
                break

    finally:
        if sdk_loop is not None:
            if mutation_session is not None:
                try:
                    _run_async(mutation_session.disconnect(), min(timeout, 30.0))
                except Exception:
                    pass
            if mutation_client is not None:
                try:
                    _run_async(mutation_client.stop(), min(timeout, 30.0))
                except Exception:
                    pass
            try:
                sdk_loop.close()
            except Exception:
                pass
        _release_lock(_work_dir)

    return SelfImproveResult(
        iterations_completed=len(records),
        final_score=current_score,
        records=records,
        stopped_reason=stopped_reason,
        reward_history=reward_history,
        final_goal_achievement_pct=final_goal_achievement_pct,
        final_criterion_results=final_criterion_results,
        final_verification=final_verification,
        blocked_reason=blocked_reason,
    )


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _build_plan_summary(scan: "ScanResult", task_goal: Optional["TaskGoal"] = None) -> str:
    """スキャン結果から改善計画サマリーを生成する。

    task_goal がある場合はゴール残差（未達成の成功条件）も返す。
    """
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
    if task_goal:
        # ゴールの説明を先頭に追加（TDD 的: 何のために改善するかを明示）
        goal_context = f"[goal: {task_goal['goal_description'][:80]}]"
        parts = [goal_context] + parts
    return ", ".join(parts)


def _build_verification_result(
    after_scan: ScanResult,
    before_score: int,
) -> VerificationResult:
    """scan 結果から VerificationResult を構築する。"""
    summary = after_scan["summary"]
    raw = after_scan["raw_output"]
    tool_status = after_scan.get("tool_status", {})
    if not isinstance(tool_status, dict):
        tool_status = {}
    ruff_status = str(tool_status.get("ruff", "PASS"))
    pytest_status = str(tool_status.get("pytest", "PASS"))
    markdown_status = str(tool_status.get("markdownlint", "PASS"))
    lint_status = str(tool_status.get("lint", ruff_status))
    test_status = str(tool_status.get("test", pytest_status))
    documentation_status = str(
        tool_status.get("documentation", markdown_status)
    )
    dotnet_build_status = str(tool_status.get("dotnet_build", "SKIP"))

    build_pass = (
        "[TOOL NOT FOUND]" not in raw
        and "[ERROR]" not in raw
        and "[TIMEOUT]" not in raw
        and not any(
            status in {"BLOCKED", "UNAVAILABLE"}
            for status in (
                lint_status,
                test_status,
                documentation_status,
                dotnet_build_status,
            )
        )
    )
    lint_pass = summary["lint_errors"] == 0 and lint_status == "PASS"
    test_pass = summary["test_failures"] == 0 and test_status == "PASS"
    doc_pass = (
        summary["doc_issues"] == 0
        and documentation_status == "PASS"
    )
    security_pass = not any(
        pat in raw
        for pat in ["sk-", "password=", "connectionstring=", "Bearer ", "api_key"]
    )

    phases = {
        "build": "PASS" if build_pass else "FAIL",
        "lint": (
            "SKIP" if lint_status == "SKIP" else "PASS" if lint_pass else "FAIL"
        ),
        "test": (
            "SKIP"
            if test_status in {"NO_TESTS", "SKIP"}
            else "PASS" if test_pass else "FAIL"
        ),
        "documentation": (
            "SKIP"
            if documentation_status == "SKIP"
            else "PASS" if doc_pass else "FAIL"
        ),
        "security": "PASS" if security_pass else "FAIL",
        "diff": "SKIP",
    }

    degraded = (
        after_scan["quality_score"] < before_score
        or phases["test"] == "FAIL"
    )
    overall = "PASS" if not degraded and all(v != "FAIL" for v in phases.values()) else "FAIL"

    return VerificationResult(
        after_quality_score=after_scan["quality_score"],
        degraded=degraded,
        verification_phases=phases,
        overall=overall,
        notes="",
    )
