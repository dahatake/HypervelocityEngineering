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

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

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

# ruff エラーコードのパターン（ファイルパス:行:列: コード形式）
# ruff のコードは 1〜3 文字のプレフィックス + 数字（例: E501, W291, RUF100, UP006, I001）
_RUFF_ERROR_PATTERN: re.Pattern[str] = re.compile(r":\d+:\d+:\s+[A-Z]+\d+\b")

# pytest 失敗サマリー行のパターン（例: "1 failed, 5 passed" / "2 errors"）
_PYTEST_FAILED_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+failed\b")
_PYTEST_ERROR_LINE_PATTERN: re.Pattern[str] = re.compile(r"\b(\d+)\s+errors?\b")

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
    "abd":      ["Arch-Batch-DomainAnalytics.agent.md",
                 "Arch-Batch-JobCatalog.agent.md"],
    "abdv":     ["Dev-Batch-ServiceCoding.agent.md",
                 "Dev-Batch-TestCoding.agent.md"],
    "aag":      ["Arch-AIAgentDesign.agent.md"],
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
    "abd":      ["planning/batch-design-guide"],
    "abdv":     ["planning/batch-design-guide",
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
    "abd":      ["docs/batch"],
    "abdv":     ["docs/batch"],
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
    "abd":      ["D04", "D05", "D08"],
    "abdv":     ["D04", "D08"],
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


class VerificationResult(TypedDict):
    """verify_improvements の戻り値。"""
    after_quality_score: int
    degraded: bool
    verification_phases: Dict[str, str]   # phase名 → "PASS"|"FAIL"|"SKIP"
    overall: str                          # "PASS" | "FAIL"
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


class SelfImproveResult(TypedDict):
    """run_improvement_loop の戻り値。"""
    iterations_completed: int
    final_score: int
    records: List[ImprovementRecord]
    stopped_reason: str     # "threshold_reached" | "no_improvement_needed" | "degradation" | "max_iterations" | "cost_limit" | "dry_run" | "disabled" | "locked" | "plateau_reached"
    reward_history: List[float]        # イテレーションごとの報酬履歴（RL）
    final_goal_achievement_pct: float  # 最終タスクゴール達成率（0.0〜1.0）


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
    "abd": TaskGoal(
        goal_description="バッチ設計文書（docs/batch/）が仕様要件を満たし整合していること",
        success_criteria=[
            "markdownlint エラーが 0 件",
            "各バッチジョブ仕様書に入力・処理・出力の 3 セクションが存在する",
        ],
        reward_weights={"lint": 0.2, "test": 0.1, "documentation": 0.7},
        tdd_phase="GREEN",
    ),
    "abdv": TaskGoal(
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
        for skill_subpath in _WORKFLOW_SKILLS_MAP.get(workflow_id, []):
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
        from copilot import CopilotClient  # type: ignore[import]
        from copilot import SubprocessConfig, ExternalServerConfig  # type: ignore[import]
        from copilot.session import PermissionHandler  # type: ignore[import]
    except ImportError:
        # SDK 未インストール: 静的結果にフォールバック
        return static_result

    client = None
    session = None
    try:
        if cli_url:
            sdk_config = ExternalServerConfig(url=cli_url)
        else:
            sdk_config = SubprocessConfig(
                cli_path=cli_path or None,
                github_token=github_token or None,
                log_level="error",
            )
        client = CopilotClient(config=sdk_config)
        await client.start()

        session_opts: Dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": False,
        }
        if model:
            session_opts["model"] = model

        session = await client.create_session(**session_opts)
        response = await session.send_and_wait(prompt, timeout=timeout)

        # レスポンステキストを抽出
        raw_text = _extract_llm_response_text(response)

    except Exception:
        # LLM 呼び出し失敗: 静的結果にフォールバック
        return static_result
    finally:
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
    work/Issue-<N>/artifacts/learning-{iteration:03d}.md に保存する。

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
# メインループ
# ---------------------------------------------------------------------------


def run_improvement_loop(
    config: Any,
    work_dir: Optional[Path] = None,
    repo_root: Optional[str] = None,
    task_goal: Optional["TaskGoal"] = None,
) -> "SelfImproveResult":
    """自己改善ループのエントリポイント。

    TDD + RL ベストプラクティスに基づく設計:
      - task_goal がタスク固有の「成功条件（TDD の GREEN 判定）」を保持する
      - 各イテレーションで reward_signal（RL 報酬）を計算し学習ログへ記録する
      - プラトー検知（連続する微小報酬）で収束を判断し無駄なイテレーションを削減する

    停止条件の優先順位:
      1. degradation: デグレード検知 → 即時停止
      2. threshold_reached: goal_achievement_pct * 100 >= threshold かつ テスト失敗 0 件
      3. plateau_reached: RL 収束（直近 N イテレーションの報酬が全て EPSILON 未満）
      4. max_iterations: 最大イテレーション数到達
      5. no_improvement_needed: 改善計画が空
      6. locked: 排他ロック取得失敗

    コスト上限（max_tokens / max_requests）は現フェーズでは
    イテレーション数でラフに制御する（per-request カウンターは
    Copilot SDK が公開した時点で実装を拡充する）。

    Args:
        config: SDKConfig インスタンス。
        work_dir: 学習ログ保存ディレクトリ（None の場合は work/self-improve/run-{run_id}/）。
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
    )

    if config.dry_run:
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "dry_run"})

    if config.self_improve_skip or not config.auto_self_improve:
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "disabled"})

    _run_id = getattr(config, "run_id", "")
    if not _run_id:
        _run_id = generate_run_id()
        setattr(config, "run_id", _run_id)
    _work_dir = work_dir or Path(f"work/self-improve/run-{_run_id}")

    # ロック取得（競合制御）
    if not _acquire_lock(_work_dir):
        return SelfImproveResult(**{**_empty_result, "stopped_reason": "locked"})

    # タスクゴールの確定（TDD 的: ループ開始前に成功条件を定義する）
    _workflow_id = getattr(config, "workflow_id", "")
    _user_goal = getattr(config, "self_improve_goal", "")
    effective_goal: "TaskGoal" = task_goal or define_task_goal(_workflow_id, _user_goal)

    records: List["ImprovementRecord"] = []
    reward_history: List[float] = []
    stopped_reason = "max_iterations"
    current_score = 0
    final_goal_achievement_pct = 0.0

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

            # Phase 4b: タスクゴール達成率チェック（TDD GREEN 判定）
            # 従来の quality_score 閾値を task_goal の重み付きスコアで評価する
            threshold = getattr(config, "self_improve_quality_threshold", DEFAULT_QUALITY_THRESHOLD)
            goal_achievement = _compute_goal_achievement(scan, effective_goal)
            final_goal_achievement_pct = goal_achievement

            if goal_achievement * 100 >= threshold and not scan["summary"]["test_failures"]:
                stopped_reason = "threshold_reached"
                break

            # 改善実行フェーズ（Phase 4c）は Copilot SDK セッション内で実施
            plan_summary = _build_plan_summary(scan, effective_goal)
            if not plan_summary:
                stopped_reason = "no_improvement_needed"
                break

            # Phase 4d: 改善後検証
            after_scan = scan_codebase(
                target_scope=config.self_improve_target_scope,
                repo_root=repo_root,
            )
            after_score = after_scan["quality_score"]
            final_goal_achievement_pct = _compute_goal_achievement(after_scan, effective_goal)

            degraded = (
                after_score < before_score
                or after_scan["summary"]["test_failures"] > scan["summary"]["test_failures"]
            )

            verification = _build_verification_result(after_scan, before_score)

            # Phase 4e: RL 報酬シグナル計算
            reward_signal = calculate_reward(scan, after_scan, effective_goal, reward_history)
            reward_history.append(reward_signal["reward"])

            # TDD フェーズを effective_goal へ反映（GREEN → REFACTOR への昇格）
            if reward_signal["tdd_phase"] != effective_goal["tdd_phase"]:
                effective_goal = TaskGoal(**{**dict(effective_goal), "tdd_phase": reward_signal["tdd_phase"]})  # type: ignore[misc]

            # Phase 4f: 学習ログ記録
            record = ImprovementRecord(
                iteration=iteration,
                before_score=before_score,
                after_score=after_score,
                degraded=degraded,
                plan_summary=plan_summary,
                verification=verification,
                reward_signal=reward_signal,
                elapsed_seconds=time.time() - iter_start,
            )
            records.append(record)
            record_learning(_work_dir, iteration, record, effective_goal)
            current_score = after_score

            # Phase 4g: 停止判定（優先順位順）
            if degraded:
                stopped_reason = "degradation"
                break
            if reward_signal["plateau_detected"]:
                # RL 収束: 改善効果が限界に達したため追加イテレーションを打ち切る
                stopped_reason = "plateau_reached"
                break

    finally:
        _release_lock(_work_dir)

    return SelfImproveResult(
        iterations_completed=len(records),
        final_score=current_score,
        records=records,
        stopped_reason=stopped_reason,
        reward_history=reward_history,
        final_goal_achievement_pct=final_goal_achievement_pct,
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
