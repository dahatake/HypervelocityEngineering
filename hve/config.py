"""config.py — SDKConfig: 全オプションを集約する dataclass"""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MODEL: str = "claude-opus-4.7"

# --- Self-Improve scope 定数 ---
# self_improve_scope の許可値。
# ""         : デフォルト（後方互換）。auto_self_improve=True 時に Step-level と Post-DAG の両方が実行される。
# "disabled" : auto_self_improve の値に関係なく Self-Improve を一切実行しない。
# "step"     : Step-level（runner.py Phase 4）のみ実行する。Post-DAG はスキップ。
# "workflow" : Post-DAG（orchestrator.py）のみ実行する。Step-level はスキップ。
#              Issue Template 経路（GitHub Actions `self-improve` ジョブ）推奨値。
VALID_SELF_IMPROVE_SCOPES: tuple[str, ...] = ("", "disabled", "step", "workflow")

# --- Self-Improve 対象パス定数 ---
# self_improve_target_scope の "*" 展開先。
# ⚠️ docs-generated はリポジトリに存在しない可能性あり。
# 実装側で「存在するパスのみ採用、非存在は警告ログを出してスキップ」とする。
SELF_IMPROVE_WILDCARD_PATHS: List[str] = [
    "data", "docs", "docs-generated", "knowledge", "src",
]

# Self-Improve 対象パスの常時除外ディレクトリ（先頭セグメント一致）
SELF_IMPROVE_EXCLUDED_TOP_DIRS: List[str] = ["work"]

# 新スコープ解決器のフィーチャーフラグ環境変数名
SELF_IMPROVE_NEW_SCOPE_RESOLVER_ENV: str = "HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER"

# ワークフロー種別に応じたデフォルト target_scope（フィーチャーフラグ ON 時のフォールバック用）
SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS: Dict[str, str] = {
    "aas": "docs/", "aad-web": "docs/", "asdw-web": ".",
    "abd": "docs/", "abdv": ".",
    "aag": "docs/", "aagd": ".",
    "akm": "knowledge/", "aqod": "qa/", "adoc": "docs/",
}

MODEL_AUTO_VALUE: str = "Auto"
MODEL_CHOICES: tuple[str, ...] = (
    "gpt-5.5",
    "claude-opus-4.7",
    "claude-opus-4.6",
    "claude-sonnet-4.6",
    "gpt-5.4",
    "gpt-5.3-codex",
    "gemini-2.5-pro",
)


def normalize_model(name: str) -> str:
    """モデル ID を正規化する（パススルー実装）。
    Wave 4: claude-opus-4-7 後方互換レイヤ削除済み。現在は入力をそのまま返す。
    """
    if not name:
        return name
    return name


def _normalize_model_with_warning(name: Optional[str]) -> Optional[str]:
    """モデル名を正規化する（後方互換ラッパー）。"""
    if name is None:
        return None
    return normalize_model(name)


def generate_run_id() -> str:
    """ワークフロー実行ごとのユニークID。

    タイムスタンプ（人間可読 + ソート可能）+ UUID短縮（衝突防止）
    例: "20260413T143022-a1b2c3"
    """
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}-{short_uuid}"


def _env_bool(name: str, default: bool = False) -> bool:
    """環境変数を bool として読む。

    - 未設定（None）の場合は default を返す。
    - "true"・"1"・"yes" (大小文字不問) → True。
    - それ以外（"false"・"0"・"no"・空文字・その他の値） → False。
    - 例: "maybe" や "2" などの未知値も False として扱う。
    """
    import os
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes")


@dataclass
class SDKConfig:
    # --- 基本設定 ---
    model: str = DEFAULT_MODEL              # デフォルトモデル
    review_model: Optional[str] = None      # レビュー専用モデル（未指定時は model）
    qa_model: Optional[str] = None          # QA 専用モデル（未指定時は model）
    timeout_seconds: float = 21600.0        # セッションの idle タイムアウト
    base_branch: str = "main"               # ベースブランチ
    cli_path: Optional[str] = None          # Copilot CLI のパス (COPILOT_CLI_PATH)
    cli_url: Optional[str] = None           # 外部 CLI サーバー URL (例: localhost:4321)
    github_token: str = ""                  # GH_TOKEN / GITHUB_TOKEN
    repo: str = ""                          # owner/repo 形式

    # --- 並列実行 ---
    max_parallel: int = 15                  # 並列上限 (デフォルト: 15)

    # --- Post-step 自動プロンプト ---
    auto_qa: bool = False                   # QA 自動投入（デフォルト: 無効）
    auto_contents_review: bool = False      # Review 自動投入（デフォルト: 無効）
    qa_answer_mode: Optional[str] = None    # QA 回答モード: "all" = 全問まとめて, "one" = 1問ずつ, None = 実行時に選択
    qa_auto_defaults: bool = False          # True: QA Phase 2b で全問デフォルト値を自動採用（設定元: __main__.py wizard / 消費先: runner.py _collect_qa_answers）

    force_interactive: bool = False         # True のとき sys.stdin.isatty() 判定をバイパスしてインタラクティブモードを強制する（--force-interactive）
    qa_input_timeout_seconds: float = 300.0  # QA 回答入力専用タイムアウト秒数（デフォルト: 300 秒）

    # --- Code Review Agent ---
    auto_coding_agent_review: bool = False              # Code Review Agent 呼び出し（デフォルト: 無効）
    auto_coding_agent_review_auto_approval: bool = False  # 自動承認（デフォルト: 無効）
    review_timeout_seconds: float = 7200.0              # Code Review Agent レビュー待ちタイムアウト（セッション idle タイムアウトとは別設定）
    review_base_ref: str = "HEAD~1"                     # git diff の基点 (例: "HEAD~1", "main", "origin/main")

    # --- Issue/PR 作成 ---
    create_issues: bool = False             # デフォルト: 作成しない
    create_pr: bool = False                 # デフォルト: 作成しない
    ignore_paths: List[str] = field(default_factory=lambda: ["docs", "images", "infra", "qa", "src", "test", "work"])
    # qa/ は PR commit 対象外（ignore_paths に含まれる）。
    # 例外: AQOD ワークフローでは qa/ の成果物が主成果物となる場合がある。
    #   → auto-aqod.yml が qa/ を commit 対象に含めるかどうかはワークフロー設定で制御する。
    #   → runner.py は qa/ に質問票・QA マージファイルを保存するが、
    #     それらは hve ローカル実行時の作業ファイルであり、通常は commit しない。
    # Skill work-artifacts-layout §4.1 の delete→create ルールは Git 上の成果物更新フローを指す。
    # runner.py の qa/ ファイル書き込みは QAMerger.save_merged() を使用し、
    #   - 実行時ファイル: run_id + step_id を含むユニークパスに保存（通常は衝突しない）
    #   - 同一 run_id/step_id での再実行時: 一時ファイル書き込み → read-back 検証 → os.replace() による
    #     アトミック rename（既存ファイルの原子的上書き）で保存する。

    # --- Console 出力 ---
    verbose: bool = True                    # レガシー互換。出力レベルは verbosity が主制御
    quiet: bool = False                     # レガシー互換。出力レベルは verbosity が主制御
    show_stream: bool = False               # トークンストリーム表示（デフォルト: 無効）
    show_reasoning: bool = True             # 推論（Thinking）表示（デフォルト: 有効）
    log_level: str = "error"                # CLI ログレベル (none/error/warning/info/debug/all)
    verbosity: int = 1                      # Console verbosity: 0=quiet, 1=compact, 2=normal, 3=verbose

    # --- SDK ---
    cli_args: List[str] = field(default_factory=list)
    # SubprocessConfig.cli_args に渡す追加 CLI 引数。例:
    # ["--log-dir", "/path/to/logs"]  でログファイル永続化
    # ["--some-flag"]                 で診断オプション有効化

    # --- MCP Servers ---
    mcp_servers: Optional[Dict[str, Any]] = None
    # Copilot SDK の mcp_servers 形式。例:
    # {
    #     "filesystem": {
    #         "type": "local",
    #         "command": "npx",
    #         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    #         "tools": ["*"],
    #     },
    #     "github": {
    #         "type": "http",
    #         "url": "https://api.githubcopilot.com/mcp/",
    #         "headers": {"Authorization": "Bearer ${TOKEN}"},
    #         "tools": ["*"],
    #     },
    # }

    # --- Custom Agents グローバル定義 ---
    custom_agents_config: Optional[List[Dict[str, Any]]] = None
    # セッション横断で全ステップに適用する追加 Agent 定義
    # Copilot SDK の custom_agents 形式。例:
    # [
    #     {
    #         "name": "researcher",
    #         "display_name": "Research Agent",
    #         "description": "Explores codebases...",
    #         "tools": ["grep", "glob", "view"],
    #         "prompt": "You are a research assistant...",
    #     },
    # ]

    # --- 追加プロンプト ---
    additional_prompt: Optional[str] = None  # 全 Custom Agent の prompt 末尾に追記する文字列

    # --- Work IQ (Microsoft 365 データ参照) ---
    workiq_enabled: bool = False                          # Work IQ 連携の有効/無効（後方互換の総合フラグ）
    workiq_qa_enabled: Optional[bool] = None              # QA フェーズ用 Work IQ（None = workiq_enabled を継承）
    workiq_akm_review_enabled: Optional[bool] = None      # AKM 実行後レビュー用 Work IQ（None = workiq_enabled を継承）
    workiq_tenant_id: Optional[str] = None                # Entra テナント ID（任意）
    workiq_prompt_qa: Optional[str] = None                # QA 用カスタムプロンプト（None = デフォルト）
    workiq_prompt_km: Optional[str] = None                # KM 用カスタムプロンプト（None = デフォルト）
    workiq_prompt_review: Optional[str] = None            # Review 用カスタムプロンプト（None = デフォルト）
    workiq_draft_mode: bool = False                       # QA: 質問ごとの回答ドラフト生成モード
    workiq_draft_output_dir: str = "qa"                   # Work IQ 補助レポート出力先ディレクトリ（互換のため設定名は据え置き）
    workiq_per_question_timeout: float = 900.0            # QA: 質問ごとの Work IQ クエリタイムアウト秒数
    workiq_max_draft_questions: int = 10                  # QA: ドラフト生成対象の最大質問数（Wave 2: 30→10 に削減）
    # Wave 2-6: デフォルトを 30 から 10 に削減。WORKIQ_MAX_DRAFT_QUESTIONS 環境変数で上書き可能。
    # 重要度フィルタ（workiq_priority_filter）により "最重要"/"高" の質問を優先し、不足分は残りの質問で補填する。
    workiq_priority_filter: bool = True                   # Work IQ: 高優先度の質問を優先して抽出し、最大件数に満たない分は他の質問で補填する

    # --- QA フェーズ制御 ---
    qa_phase: str = "pre"                                 # QA フェーズ: "pre"=実行前のみ, "post"=実行後のみ, "both"=前後両方
    # 推奨デフォルト: "pre"（主タスク実行前の準備重視・トークン節約）
    # 設定方法: HVE_QA_PHASE 環境変数（"pre"/"post"/"both"）または SDKConfig.from_env() 経由
    # 不正値は from_env() で "pre" にフォールバックする
    # AKM ワークフロー: 事前 QA は qa_phase の指定に従う / 事後 QA は常にスキップする
    # AQOD ワークフロー: 事前 QA は常にスキップ / 事後 QA は aqod_post_qa_enabled で制御する

    # --- AQOD 専用 ---
    aqod_post_qa_enabled: bool = False                    # AQOD: メインタスク完了後の事後 QA をオプトイン実行する
    # True: AQOD で事後 QA を実行する（qa_phase の値には依存しない）
    # False (デフォルト): AQOD では事後 QA を実行しない

    # --- Self-Improve ---
    auto_self_improve: bool = False             # デフォルト: 無効。Issue Template / CLI --self-improve / HVE_AUTO_SELF_IMPROVE で有効化
    self_improve_max_iterations: int = 3        # 最大イテレーション数
    tdd_max_retries: int = 5                    # TDD GREEN フェーズの最大リトライ回数。HVE_TDD_MAX_RETRIES 環境変数で上書き可能
    self_improve_quality_threshold: int = 80    # ゴール達成率閾値（この値以上で完了。goal_achievement_pct * 100 と比較）
    self_improve_max_tokens: int = 500_000      # コストハードリミット（トークン上限）
    self_improve_max_requests: int = 50         # コストハードリミット（リクエスト上限）
    self_improve_target_scope: str = ""
    # 改善対象スコープ。受理する形式:
    #   - ""       : (新仕様) そのステップの成果物。取得不能時は SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS。work/ 配下は常に除外。
    #                (旧仕様) リポジトリ全体（フィーチャーフラグ OFF 時）
    #   - "*"      : SELF_IMPROVE_WILDCARD_PATHS（実在するもののみ。存在しないパスは警告ログ）
    #   - "src/ docs/" : カンマ/空白区切りの複数パス（先頭が "-" のトークンは拒否）
    # 内部的には _resolve_target_scope_paths() で List[str] に正規化される。
    self_improve_goal: str = ""                 # タスク固有ゴールの説明（空 = ワークフロー ID から自動生成）
    self_improve_success_criteria: List[str] = field(default_factory=list)  # 自動検索で得た success_criteria（空 = ワークフロー標準を使用）
    self_improve_skip: bool = False             # --no-self-improve で True
    self_improve_scope: str = "workflow"        # 実行単位: "" (後方互換), "disabled", "step", "workflow"
    # HVE_SELF_IMPROVE_SCOPE 環境変数でも指定可能。
    # "workflow"  : Post-DAG（orchestrator.py）のみ実行。Issue Template 経路推奨。Wave 2 以降デフォルト。
    # ""          : 後方互換。auto_self_improve=True 時に Step-level と Post-DAG の両方が実行される（非推奨）。
    # "disabled"  : Self-Improve を一切実行しない（auto_self_improve の値に関係なく）。
    # "step"      : Step-level（runner.py Phase 4）のみ実行。Issue Template 外のローカル実行向け。

    # --- 実行 ID ---
    run_id: str = ""                        # ワークフロー実行ごとのユニークID（空の場合は run_workflow() で自動生成）

    # --- その他 ---
    max_diff_chars: int = 80_000            # git diff の最大文字数（トークン上限対策）。HVE_MAX_DIFF_CHARS 環境変数で上書き可能

    # --- コンテキスト最適化 ---
    reuse_context_filtering: bool = True    # True: ステップ依存関係ベースの reuse_context フィルタリング（HVE_REUSE_CONTEXT_FILTERING）
    # デフォルト true（consumed_artifacts アノテーション済みのステップのみフィルタリング）。
    # consumed_artifacts=None のステップは後方互換で全成果物を渡す。false にすると全ステップに全成果物を渡す（旧挙動）。

    # --- セキュリティ ---
    model_override: Optional[str] = None    # 緊急回避用モデル上書き。設定時は Issue Template の選択より優先される。HVE_MODEL_OVERRIDE 環境変数で設定
    # ※ プロンプトサニタイズの有効/無効は HVE_PROMPT_SANITIZATION 環境変数で直接制御する（security.is_sanitization_enabled() 参照）

    # --- メイン成果物改善制御 ---
    apply_qa_improvements_to_main: bool = False   # QA 結果をメイン成果物へ反映（デフォルト: 無効）
    apply_review_improvements_to_main: bool = True  # レビュー指摘をメイン成果物へ反映（デフォルト: 有効）
    apply_self_improve_to_main: bool = True       # Self-Improve 計画をメイン成果物へ反映（デフォルト: 有効）

    # --- 前提成果物チェック（Phase 8） ---
    require_input_artifacts: bool = False
    # False (デフォルト): 不足 artifact を warning として出力して続行する。
    # True (strict mode): 不足 artifact がある場合に実行を中断する。
    # 設定方法: HVE_REQUIRE_INPUT_ARTIFACTS 環境変数（"true"/"1"/"yes"）。
    # consumed_artifacts=None のステップは後方互換としてチェック対象外。
    # consumed_artifacts=[] のステップは前提成果物なしとして扱い、不足なし。

    # --- 全自動モード ---
    unattended: bool = False                # True の場合、実行中のインタラクティブ入力を全てスキップ

    # --- その他 ---
    dry_run: bool = False                   # ドライラン

    def __post_init__(self) -> None:
        # SDKConfig は from_env() 以外（直接コンストラクタ呼び出し）でも利用されるため、
        # 空文字モデルはここでも Auto に寄せて挙動を統一する。
        if not self.model:
            self.model = MODEL_AUTO_VALUE
        # "Auto" は GitHub 側の Auto Model Selection に委譲するため固定モデルへ解決しない。
        # 正規化後に空文字になった場合も DEFAULT_MODEL へ固定せず Auto にフォールバックする。
        if self.model != MODEL_AUTO_VALUE:
            self.model = _normalize_model_with_warning(self.model) or MODEL_AUTO_VALUE
        if self.review_model != MODEL_AUTO_VALUE:
            self.review_model = _normalize_model_with_warning(self.review_model)
        if self.qa_model != MODEL_AUTO_VALUE:
            self.qa_model = _normalize_model_with_warning(self.qa_model)
        # model_override が設定されている場合、model フィールドを上書きする。
        # Issue Template の選択（AUTO 含む）よりも優先される緊急回避手段。
        if self.model_override:
            normalized = _normalize_model_with_warning(self.model_override) or None
            self.model_override = normalized  # 正規化後の値を self.model_override にも反映
            if normalized:
                self.model = normalized
        # self_improve_scope は from_env() と同様に正規化してから検証し、
        # 直接コンストラクタ呼び出し時も挙動を統一する。
        self.self_improve_scope = (self.self_improve_scope or "").strip().lower()
        if self.self_improve_scope not in VALID_SELF_IMPROVE_SCOPES:
            import warnings
            warnings.warn(
                f"self_improve_scope='{self.self_improve_scope}' は無効な値です。"
                f"有効な値: {VALID_SELF_IMPROVE_SCOPES}。"
                f"'' (後方互換) にフォールバックします。",
                stacklevel=2,
            )
            self.self_improve_scope = ""

    def is_workiq_qa_enabled(self) -> bool:
        """QA フェーズで Work IQ を使うかを返す（旧 workiq_enabled と互換）。"""
        return self.workiq_enabled if self.workiq_qa_enabled is None else self.workiq_qa_enabled

    def is_workiq_akm_review_enabled(self) -> bool:
        """AKM 実行後レビューで Work IQ を使うかを返す（旧 workiq_enabled と互換）。"""
        return self.workiq_enabled if self.workiq_akm_review_enabled is None else self.workiq_akm_review_enabled

    @classmethod
    def from_env(cls) -> "SDKConfig":
        """環境変数から SDKConfig を構築する。"""
        import os
        raw_model = os.environ.get("MODEL")
        if raw_model is None or raw_model.strip() == "":
            env_model = MODEL_AUTO_VALUE
        else:
            env_model = _normalize_model_with_warning(raw_model) or MODEL_AUTO_VALUE
        try:
            env_workiq_per_question_timeout = float(
                os.environ.get("WORKIQ_PER_QUESTION_TIMEOUT", "900.0")
            )
        except (TypeError, ValueError):
            env_workiq_per_question_timeout = 900.0
        try:
            env_workiq_max_draft_questions = int(
                os.environ.get("WORKIQ_MAX_DRAFT_QUESTIONS", "10")
            )
        except (TypeError, ValueError):
            env_workiq_max_draft_questions = 10

        _valid_qa_phases = ("pre", "post", "both")
        _raw_qa_phase = os.environ.get("HVE_QA_PHASE", "pre").strip().lower()
        if _raw_qa_phase and _raw_qa_phase not in _valid_qa_phases:
            import warnings
            warnings.warn(
                f"HVE_QA_PHASE='{_raw_qa_phase}' は無効な値です。"
                f"有効な値: {_valid_qa_phases}。'pre' にフォールバックします。",
                stacklevel=2,
            )
        env_qa_phase = _raw_qa_phase if _raw_qa_phase in _valid_qa_phases else "pre"

        _raw_si_scope = os.environ.get("HVE_SELF_IMPROVE_SCOPE", "").strip().lower()
        if _raw_si_scope and _raw_si_scope not in VALID_SELF_IMPROVE_SCOPES:
            import warnings
            warnings.warn(
                f"HVE_SELF_IMPROVE_SCOPE='{_raw_si_scope}' は無効な値です。"
                f"有効な値: {VALID_SELF_IMPROVE_SCOPES}。"
                f"'' (後方互換) にフォールバックします。",
                stacklevel=2,
            )
        # Wave 2-5: HVE_SELF_IMPROVE_SCOPE 未設定時は "workflow" をデフォルトとする。
        # "" を明示的に設定した場合は後方互換（Step-level + Post-DAG 両方実行）。
        if not _raw_si_scope:
            env_si_scope = "workflow"
        else:
            env_si_scope = _raw_si_scope if _raw_si_scope in VALID_SELF_IMPROVE_SCOPES else ""

        try:
            env_max_diff_chars = int(os.environ.get("HVE_MAX_DIFF_CHARS", "80000"))
        except (TypeError, ValueError):
            env_max_diff_chars = 80_000

        def _env_bool_or_none(name: str) -> Optional[bool]:
            raw = os.environ.get(name)
            if raw is None or raw.strip() == "":
                return None
            return raw.strip().lower() in ("true", "1", "yes")

        return cls(
            model=env_model,
            github_token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
            repo=os.environ.get("REPO", ""),
            cli_path=os.environ.get("COPILOT_CLI_PATH"),
            review_model=_normalize_model_with_warning(os.environ.get("REVIEW_MODEL") or None),
            qa_model=_normalize_model_with_warning(os.environ.get("QA_MODEL") or None),
            show_reasoning=os.environ.get("SHOW_REASONING", "true").lower() in ("true", "1", "yes"),
            workiq_enabled=os.environ.get("WORKIQ_ENABLED", "").lower() in ("true", "1", "yes"),
            workiq_qa_enabled=_env_bool_or_none("WORKIQ_QA_ENABLED"),
            workiq_akm_review_enabled=_env_bool_or_none("WORKIQ_AKM_REVIEW_ENABLED"),
            workiq_tenant_id=os.environ.get("WORKIQ_TENANT_ID") or None,
            workiq_prompt_qa=os.environ.get("WORKIQ_PROMPT_QA") or None,
            workiq_prompt_km=os.environ.get("WORKIQ_PROMPT_KM") or None,
            workiq_prompt_review=os.environ.get("WORKIQ_PROMPT_REVIEW") or None,
            workiq_draft_mode=os.environ.get("WORKIQ_DRAFT_MODE", "").lower() in ("true", "1", "yes"),
            workiq_draft_output_dir=os.environ.get("WORKIQ_DRAFT_OUTPUT_DIR", "qa"),
            workiq_per_question_timeout=env_workiq_per_question_timeout,
            workiq_max_draft_questions=env_workiq_max_draft_questions,
            workiq_priority_filter=_env_bool("WORKIQ_PRIORITY_FILTER", default=True),
            qa_phase=env_qa_phase,
            aqod_post_qa_enabled=os.environ.get("HVE_AQOD_POST_QA", "").lower() in ("true", "1", "yes"),
            auto_self_improve=os.environ.get("HVE_AUTO_SELF_IMPROVE", "").lower() in ("true", "1", "yes"),
            tdd_max_retries=int(os.environ.get("HVE_TDD_MAX_RETRIES", "5")),
            max_diff_chars=env_max_diff_chars,
            reuse_context_filtering=_env_bool("HVE_REUSE_CONTEXT_FILTERING", default=True),
            model_override=_normalize_model_with_warning(os.environ.get("HVE_MODEL_OVERRIDE") or None),
            apply_qa_improvements_to_main=_env_bool("HVE_APPLY_QA_IMPROVEMENTS_TO_MAIN", default=False),
            apply_review_improvements_to_main=_env_bool("HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN", default=True),
            apply_self_improve_to_main=_env_bool("HVE_APPLY_SELF_IMPROVE_TO_MAIN", default=True),
            self_improve_scope=env_si_scope,
            require_input_artifacts=_env_bool("HVE_REQUIRE_INPUT_ARTIFACTS", default=False),
        )

    def get_review_model(self) -> str:
        """レビュー用モデルを返す。

        敵対的レビュー（auto_contents_review）および
        Code Review Agent（auto_coding_agent_review）で使用する。
        """
        return self.review_model or self.model

    def get_qa_model(self) -> str:
        """QA 用モデルを返す。

        QA 質問票生成（auto_qa）で使用する。
        """
        return self.qa_model or self.model

    def resolve_token(self) -> str:
        """有効なトークンを返す。"""
        if self.github_token:
            return self.github_token
        import os
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
