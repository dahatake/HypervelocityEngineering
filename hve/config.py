"""config.py — SDKConfig: 全オプションを集約する dataclass"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    model: str = "claude-opus-4.6"          # デフォルトモデル
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

    @classmethod
    def from_env(cls) -> "SDKConfig":
        """環境変数から SDKConfig を構築する。"""
        import os
        return cls(
            github_token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
            repo=os.environ.get("REPO", ""),
            cli_path=os.environ.get("COPILOT_CLI_PATH"),
            review_model=os.environ.get("REVIEW_MODEL") or None,
            qa_model=os.environ.get("QA_MODEL") or None,
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
