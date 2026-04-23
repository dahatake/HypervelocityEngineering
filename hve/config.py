"""config.py — SDKConfig: 全オプションを集約する dataclass"""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MODEL: str = "claude-opus-4.7"
MODEL_AUTO_VALUE: str = "Auto"
LEGACY_MODEL_ID: str = "claude-opus-4-7"
MODEL_CHOICES: tuple[str, ...] = (
    "claude-opus-4.7",
    "claude-opus-4.6",
    "claude-sonnet-4.6",
    "gpt-5.4",
    "gpt-5.3-codex",
    "gemini-2.5-pro",
)
_MODEL_ALIASES = {
    LEGACY_MODEL_ID: "claude-opus-4.7",
}
_DEPRECATED_MODEL_WARNED: set[str] = set()


def normalize_model(name: str) -> str:
    """旧ハイフン区切りのモデル ID をドット区切りへ正規化する。
    Copilot CLI の /model 実機出力に合わせた後方互換レイヤ。
    """
    if not name:
        return name
    return _MODEL_ALIASES.get(name, name)


def _normalize_model_with_warning(name: Optional[str]) -> Optional[str]:
    """モデル名を正規化し、旧表記を 1 回だけ警告出力する。"""
    if name is None:
        return None
    normalized = normalize_model(name)
    if normalized != name and name not in _DEPRECATED_MODEL_WARNED:
        print(f"WARNING: '{name}' is deprecated; use '{normalized}'", file=sys.stderr)
        _DEPRECATED_MODEL_WARNED.add(name)
    return normalized


def generate_run_id() -> str:
    """ワークフロー実行ごとのユニークID。

    タイムスタンプ（人間可読 + ソート可能）+ UUID短縮（衝突防止）
    例: "20260413T143022-a1b2c3"
    """
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}-{short_uuid}"


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

    # --- Console 出力 ---
    verbose: bool = True                    # レガシー互換。出力レベルは verbosity が主制御
    quiet: bool = False                     # レガシー互換。出力レベルは verbosity が主制御
    show_stream: bool = False               # トークンストリーム表示（デフォルト: 無効）
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
    workiq_enabled: bool = False                          # Work IQ 連携の有効/無効
    workiq_tenant_id: Optional[str] = None                # Entra テナント ID（任意）
    workiq_prompt_qa: Optional[str] = None                # QA 用カスタムプロンプト（None = デフォルト）
    workiq_prompt_km: Optional[str] = None                # KM 用カスタムプロンプト（None = デフォルト）
    workiq_prompt_review: Optional[str] = None            # Review 用カスタムプロンプト（None = デフォルト）
    workiq_query_timeout_seconds: float = 120.0           # Work IQ クエリタイムアウト秒数
    workiq_draft_mode: bool = False                       # QA: 質問ごとの回答ドラフト生成モード
    workiq_draft_output_dir: str = "qa"                   # QA: 回答ドラフト出力先ディレクトリ
    workiq_per_question_timeout: float = 60.0             # QA: 質問ごとの Work IQ クエリタイムアウト秒数
    workiq_max_draft_questions: int = 30                  # QA: ドラフト生成対象の最大質問数

    # --- Self-Improve ---
    auto_self_improve: bool = True              # 自己改善ループ（デフォルト: 有効）
    self_improve_max_iterations: int = 3        # 最大イテレーション数
    self_improve_max_tokens: int = 500_000      # コストハードリミット（トークン上限）
    self_improve_max_requests: int = 50         # コストハードリミット（リクエスト上限）
    self_improve_target_scope: str = ""         # 改善対象スコープ（空 = 全体）
    self_improve_skip: bool = False             # --no-self-improve で True

    # --- 実行 ID ---
    run_id: str = ""                        # ワークフロー実行ごとのユニークID（空の場合は run_workflow() で自動生成）

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
                os.environ.get("WORKIQ_PER_QUESTION_TIMEOUT", "60.0")
            )
        except (TypeError, ValueError):
            env_workiq_per_question_timeout = 60.0
        try:
            env_workiq_max_draft_questions = int(
                os.environ.get("WORKIQ_MAX_DRAFT_QUESTIONS", "30")
            )
        except (TypeError, ValueError):
            env_workiq_max_draft_questions = 30
        return cls(
            model=env_model,
            github_token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
            repo=os.environ.get("REPO", ""),
            cli_path=os.environ.get("COPILOT_CLI_PATH"),
            review_model=_normalize_model_with_warning(os.environ.get("REVIEW_MODEL") or None),
            qa_model=_normalize_model_with_warning(os.environ.get("QA_MODEL") or None),
            workiq_enabled=os.environ.get("WORKIQ_ENABLED", "").lower() in ("true", "1", "yes"),
            workiq_tenant_id=os.environ.get("WORKIQ_TENANT_ID") or None,
            workiq_prompt_qa=os.environ.get("WORKIQ_PROMPT_QA") or None,
            workiq_prompt_km=os.environ.get("WORKIQ_PROMPT_KM") or None,
            workiq_prompt_review=os.environ.get("WORKIQ_PROMPT_REVIEW") or None,
            workiq_draft_mode=os.environ.get("WORKIQ_DRAFT_MODE", "").lower() in ("true", "1", "yes"),
            workiq_draft_output_dir=os.environ.get("WORKIQ_DRAFT_OUTPUT_DIR", "qa"),
            workiq_per_question_timeout=env_workiq_per_question_timeout,
            workiq_max_draft_questions=env_workiq_max_draft_questions,
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
