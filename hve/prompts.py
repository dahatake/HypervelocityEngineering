"""prompts.py — HVE 内部 runtime prompt の互換 facade。

本モジュールは既存の `*_PROMPT` / 補助定数 API を維持しつつ、QA / Review /
Self-Improve / Work IQ / ARD / AKM / Code Review などの固定 model-facing prompt
本文を `.github/prompts/runtime/**` から読み込む薄い互換層。
"""

from __future__ import annotations

try:
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level `import prompts` compatibility
    from prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]

# NOTE: 旧 QA_APPLY_PROMPT (post-QA / Phase 2) は 8beb0a4d で post-QA フェーズ廃止に伴い
# 機能としては unused となっていた死コードを 2026-05 削除済み (work/Issue-orchestration-refactor)。
# Pre-QA フローでは pre_qa_context を直接プロンプト先頭注入する方式に移行している。

# ---------------------------------------------------------------------------
# 共通禁止事項テキスト（質問票・レビュー・実装の各プロンプトから参照）
# ---------------------------------------------------------------------------

OVERENGINEERING_BAN_TEXT: str = load_prompt_file("runtime/shared/overengineering-ban.prompt.md")

OVERENGINEERING_BAN_TEXT_QA: str = load_prompt_file("runtime/qa/overengineering-ban.prompt.md")

QUESTIONNAIRE_DEPTH_RULES_TEXT: str = load_prompt_file("runtime/qa/questionnaire-depth-rules.prompt.md")


REVIEW_PROMPT: str = load_prompt_file("runtime/review/adversarial-review.prompt.md")

ADVERSARIAL_RECHECK_PROMPT: str = load_prompt_file("runtime/review/adversarial-recheck.prompt.md")

# ---------------------------------------------------------------------------
# QA v2 / マージ / 統合ドキュメント生成プロンプト
# ---------------------------------------------------------------------------

# 事前実行 QA プロンプト（メインタスク実行前に使用）
# QA_PROMPT_V2 と同一構造だが「成果物」ではなく「これから実行するタスクのプロンプト」に対して質問票を作成する
PRE_EXECUTION_QA_COMMENT_MARKER: str = "<!-- copilot-auto-pre-qa-posted -->"
PRE_EXECUTION_QA_PROMPT_V2: str = load_prompt_file("runtime/qa/pre-execution.prompt.md")


def render_pre_execution_qa_comment_body() -> str:
    """Issue 事前 QA コメント本文を返す。"""
    return f"{PRE_EXECUTION_QA_COMMENT_MARKER}\n@copilot\n\n{PRE_EXECUTION_QA_PROMPT_V2}"

QA_PROMPT_V2: str = load_prompt_file("runtime/qa/post-execution.prompt.md")

QA_MERGE_SAVE_PROMPT: str = load_prompt_file("runtime/qa/merge-save.prompt.md")

QA_CONSOLIDATE_PROMPT: str = load_prompt_file("runtime/qa/consolidate.prompt.md")


# ---------------------------------------------------------------------------
# Copilot CLI Code Review Agent 起動プロンプト（{diff} に git diff テキストを埋め込む）

CODE_REVIEW_CLI_PROMPT: str = load_prompt_file("runtime/review/code-review-cli.prompt.md")

# ---------------------------------------------------------------------------
# Self-Improve プロンプト定数
# ---------------------------------------------------------------------------

# Phase 4a: コードベーススキャン結果の LLM 統合評価プロンプト
# プレースホルダー: {scan_output} = ruff/pytest/markdownlint の実行結果テキスト
# プレースホルダー: {target_scope} = 改善対象スコープ（空 = 全体）
SELF_IMPROVE_SCAN_PROMPT: str = load_prompt_file("runtime/self-improve/scan.prompt.md")

# Phase 4b: 改善計画立案プロンプト
# プレースホルダー: {scan_result_json} = SELF_IMPROVE_SCAN_PROMPT の出力 JSON
# プレースホルダー: {iteration} = 現在のイテレーション番号
# プレースホルダー: {previous_learning} = 前回の学習サマリー（初回は空文字列）
SELF_IMPROVE_PLAN_PROMPT: str = load_prompt_file("runtime/self-improve/plan.prompt.md")

# Phase 4d: 改善後検証プロンプト（§10.1 Verification Loop 準拠）
# プレースホルダー: {before_score} = 改善前の quality_score
# プレースホルダー: {after_scan_output} = 改善後のツール実行結果
SELF_IMPROVE_VERIFY_PROMPT: str = load_prompt_file("runtime/self-improve/verify.prompt.md")


# ---------------------------------------------------------------------------
# メインタスク成果物改善プロンプト（Phase 2c / Phase 3 / Phase 4 共通）
# ---------------------------------------------------------------------------
# 使用条件:
#   - Phase 2c (QA Merge): config.apply_qa_improvements_to_main=True かつ merge_succeeded=True 後
#   - Phase 3 (Adversarial Review): config.apply_review_improvements_to_main=True かつ FAIL 判定後
#   - Phase 4 (Self-Improve): config.apply_self_improve_to_main=True かつ改善計画生成後
# 送信先: サブセッションではなく Phase 1 と同じメインセッション
# プレースホルダー:
#   {source_phase}       = 改善材料の出所フェーズ名（例: "Phase 2c QA Merge"）
#   {workflow_id}        = ワークフロー識別子（例: "adi", "aad-web"）
#   {step_id}            = ステップ識別子（例: "1.1"）
#   {step_title}         = ステップタイトル
#   {custom_agent}       = Custom Agent 名（省略可。"None" の場合あり）
#   {original_prompt}    = メインタスク実行時の元プロンプト
#   {main_output}        = メインタスクの実行結果（現在の成果物）
#   {improvement_context}= 改善材料（QA 結果 / レビュー指摘 / 改善計画）
MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT: str = load_prompt_file("runtime/self-improve/main-artifact-apply.prompt.md")


CODE_REVIEW_AGENT_FIX_PROMPT: str = load_prompt_file("runtime/review/code-review-agent-fix.prompt.md")


# ------------------------------------------------------------------
# Work IQ コンテキスト注入テンプレート
# ------------------------------------------------------------------

WORKIQ_CONTEXT_INJECTION_PROMPT: str = load_prompt_file("runtime/workiq/context-injection.prompt.md")


# ------------------------------------------------------------------
# AKM Work IQ 検証・更新プロンプト
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# ARD Work IQ ユースケース作成プロンプト
# ------------------------------------------------------------------

ARD_WORKIQ_USECASE_PROMPT: str = load_prompt_file("runtime/workiq/ard-usecase.prompt.md")


AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT: str = load_prompt_file("runtime/workiq/akm-verify-update.prompt.md")


# ---------------------------------------------------------------------------
# AKM Work IQ 取り込み（ingest）プロンプト
# ---------------------------------------------------------------------------
# AKM メイン DAG の **前段** で実行される Work IQ 取り込みフェーズ用プロンプト。
# 検証用 (AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT) と異なり、対象 Dxx ファイルがまだ
# 存在しない場合は **新規作成** することを許可する。既存の場合は **差分マージ** する。
#
# プレースホルダ:
# - {d_class_id}        : D クラス ID（例: "D01"）
# - {document_name}     : マスターリスト上の文書名（例: "事業意図・成功条件定義書"）
# - {dxx_target_info}   : マスターリストから抽出した最低内容・必須度等の構造化情報
# - {existing_status}   : 既存の `knowledge/Dxx-*.md` の内容（存在しない場合は "(未作成)"）
# - {workiq_result}     : Work IQ クエリ結果
AKM_WORKIQ_INGEST_PROMPT: str = load_prompt_file("runtime/workiq/akm-ingest.prompt.md")


# ---------------------------------------------------------------------------
# ARD Step 2: target_business 説明文生成プロンプト（PR#6）
# ---------------------------------------------------------------------------
# Step 1（Untargeted 事業分析）で生成された docs/company-business-requirement.md の
# Strategic Recommendations から、ユーザーが選択した 1 件（SR-ID）の内容を基に、
# Step 2（Targeted 事業分析）の target_business パラメータに使う「対象業務の説明文」を
# 生成するための補助セッション用プロンプト。
#
# 利用想定: orchestrator が _orchestrator_session_id() で軽量な補助セッションを起動し、
# このプロンプトを送信して短い説明文（数行程度）を取得し、target_business に注入する。
# 後続 Step 2 はその説明文を Targeted 分析の前提として使用する。
#
# プレースホルダ:
# - {company_name}                 : 対象企業名（必須）
# - {selected_recommendation_id}   : ユーザーが選択した推奨戦略 ID（例: "SR-1"）
# - {selected_recommendation_title}: 選択された推奨戦略のタイトル
# - {business_requirement_content} : docs/company-business-requirement.md の本文全体
#
# 捏造禁止ポリシー: 本プロンプトは business_requirement_content を一次情報として制約し、
# 本文に書かれていない事業領域・業務を勝手に作らないよう明示する。
# Work IQ QA / KM / Review の 3-mode 合成には含めず、orchestrator の ARD Step 2
# 補助セッションだけが直接参照する。
ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT: str = load_prompt_file(
        "runtime/orchestrator/ard-target-business.prompt.md"
)
