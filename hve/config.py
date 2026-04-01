"""config.py — SDKConfig: 全オプションを集約する dataclass"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SDKConfig:
    # --- 基本設定 ---
    model: str = "claude-opus-4.6"          # デフォルトモデル
    timeout_seconds: float = 7200.0         # セッションの idle タイムアウト
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

    # --- Code Review Agent ---
    auto_coding_agent_review: bool = False              # Code Review Agent 呼び出し（デフォルト: 無効）
    auto_coding_agent_review_auto_approval: bool = False  # 自動承認（デフォルト: 無効）
    review_timeout_seconds: float = 7200.0              # Code Review Agent レビュー待ちタイムアウト
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
        )

    def resolve_token(self) -> str:
        """有効なトークンを返す。"""
        if self.github_token:
            return self.github_token
        import os
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
