"""__main__.py — CLI エントリポイント

使い方:
    # (A) インタラクティブモード（推奨）
    python -m hve

    # (B) python -m で直接実行
    python -m hve orchestrate --workflow aad

    # (C) ディレクトリに移動して __main__.py を直接実行
    cd hve
    python __main__.py orchestrate --workflow aad

    # (D) フルパス指定
    python hve/__main__.py orchestrate --workflow aad

    # 基本実行 (デフォルト: claude-opus-4-7, 並列15, compact, Issue/PR作成なし)
    python -m hve orchestrate --workflow aad

    # QA + Review 有効
    python -m hve orchestrate --workflow aad --auto-qa --auto-contents-review

    # Issue 作成あり + MCP Server 設定ファイル指定
    python -m hve orchestrate --workflow asdw \\
      --create-issues --mcp-config mcp-servers.json

    # 並列数変更 + モデル変更
    python -m hve orchestrate --workflow aad \\
      --max-parallel 5 --model gpt-5.4

    # 出力抑制
    python -m hve orchestrate --workflow aad --quiet

    # 外部 CLI サーバー接続
    python -m hve orchestrate --workflow aad --cli-url localhost:4321

    # ドライラン
    python -m hve orchestrate --workflow aad --dry-run

    # 追加プロンプト付き
    python -m hve orchestrate --workflow aad \\
      --additional-prompt "Azure Japan East リージョンを前提にしてください"

    # Issue タイトル指定
    python -m hve orchestrate --workflow aad \\
      --create-issues --issue-title "Sprint 42: AAD 全ステップ実行"

    # Knowledge Management（デフォルト設定: sources=qa, target_files=qa/*.md, force_refresh=true）
    python -m hve orchestrate --workflow akm

    # original-docs 起点
    python -m hve orchestrate --workflow akm --sources original-docs

    # 両方 + custom source dir
    python -m hve orchestrate --workflow akm --sources both --custom-source-dir docs/specs

    # AQOD（original-docs 横断分析質問票）
    python -m hve orchestrate --workflow aqod
    python -m hve orchestrate --workflow aqod --target-scope original-docs/ --depth lightweight
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from .config import DEFAULT_MODEL, MODEL_CHOICES, SDKConfig
except ImportError:
    from config import DEFAULT_MODEL, MODEL_CHOICES, SDKConfig  # type: ignore[no-redef]


def _ts() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


# -----------------------------------------------------------------------
# Auto モデル定数
# -----------------------------------------------------------------------

MODEL_AUTO = "Auto"
_MODEL_AUTO_RESOLVED = DEFAULT_MODEL

# AKM デフォルト値
_AKM_DEFAULT_SOURCES = "qa"
_AKM_DEFAULT_TARGET_FILES = "qa/*.md"
_AQOD_DEFAULT_TARGET_SCOPE = "original-docs/"
_AQOD_DEFAULT_DEPTH = "standard"
_ADOC_DOC_PURPOSE_CHOICES = ("all", "onboarding", "refactoring", "migration")


def _default_akm_target_files(sources: str) -> str:
    """AKM の sources に応じた target_files 既定値を返す。"""
    if sources == "original-docs":
        return "original-docs/*"
    if sources == "both":
        return ""
    return _AKM_DEFAULT_TARGET_FILES


def _prompt_valid_doc_purpose(con) -> str:
    """ADOC の doc_purpose を許容値で入力させる。"""
    while True:
        val = (con.prompt_input("doc_purpose", default="all", required=False).strip() or "all")
        if val in _ADOC_DOC_PURPOSE_CHOICES:
            return val
        con.warning("doc_purpose は all / onboarding / refactoring / migration のいずれかを指定してください。")


def _prompt_valid_aqod_depth(con) -> str:
    """AQOD の depth を許容値で入力させる。"""
    valid_depths = {"standard", "lightweight"}
    while True:
        depth_input = con.prompt_input("depth", default=_AQOD_DEFAULT_DEPTH)
        depth = (depth_input or _AQOD_DEFAULT_DEPTH).strip().lower()
        if depth in valid_depths:
            return depth
        con.warning("depth は standard / lightweight のいずれかを指定してください。")


def _resolve_model(model: str) -> tuple:
    """モデル名を解決する。

    Args:
        model: 入力モデル名。MODEL_AUTO の場合は _MODEL_AUTO_RESOLVED に解決する。

    Returns:
        (resolved_model, display_name) のタプル。
    """
    if model == MODEL_AUTO:
        return _MODEL_AUTO_RESOLVED, MODEL_AUTO
    return model, model


# -----------------------------------------------------------------------
# argparse セットアップ
# -----------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """メイン ArgumentParser を構築する。"""
    parser = argparse.ArgumentParser(
        prog="hve",
        description="GitHub Copilot SDK ワークフローオーケストレーター",
    )

    sub = parser.add_subparsers(dest="command")

    # --- run サブコマンド (インタラクティブモード) ---
    sub.add_parser(
        "run",
        help="インタラクティブモードでワークフローを実行する (デフォルト)",
    )

    # --- orchestrate サブコマンド ---
    orch = sub.add_parser(
        "orchestrate",
        help="ワークフローを選択し、DAG に従って各ステップをローカル実行する",
    )

    # 必須
    orch.add_argument(
        "--workflow", "-w",
        required=True,
        metavar="WORKFLOW_ID",
        help=(
            "ワークフロー ID: "
            "aas(App Architecture Design) / "
            "aad(App Design) / "
            "asdw(App Dev Microservice Azure) / "
            "abd(Batch Design) / "
            "abdv(Batch Dev) / "
            "akm(Knowledge Management) / "
            "aqod(QA Original Docs Review) / "
            "adoc(App Documentation)"
        ),
    )

    # モデル
    orch.add_argument(
        "--model", "-m",
        default=None,
        metavar="MODEL",
        help=f"使用するモデル名 (デフォルト: {DEFAULT_MODEL})。Auto を指定するとデフォルトモデルが自動選択されます",
    )
    orch.add_argument(
        "--review-model",
        default=None,
        metavar="MODEL",
        help=(
            "敵対的レビュー（--auto-contents-review）および Code Review Agent"
            "（--auto-coding-agent-review）で使用するモデル（省略時は --model と同じ）"
        ),
    )
    orch.add_argument(
        "--qa-model",
        default=None,
        metavar="MODEL",
        help="QA 質問票生成（--auto-qa）で使用するモデル（省略時は --model と同じ）",
    )

    # 並列実行
    orch.add_argument(
        "--max-parallel",
        type=int,
        default=15,
        metavar="N",
        help="並列実行上限 (デフォルト: 15)",
    )

    # Post-step 自動プロンプト
    orch.add_argument(
        "--auto-qa",
        action="store_true",
        default=False,
        help="QA 自動投入を有効化 (デフォルト: 無効)",
    )
    orch.add_argument(
        "--force-interactive",
        action="store_true",
        default=False,
        help=(
            "QA 回答入力の TTY 判定をバイパスしてインタラクティブモードを強制する"
            " (デフォルト: 無効。IDE ターミナル等で stdin が非 TTY 扱いになる場合に使用)"
        ),
    )
    orch.add_argument(
        "--auto-contents-review",
        action="store_true",
        default=False,
        help="Review 自動投入を有効化 (デフォルト: 無効)",
    )
    orch.add_argument(
        "--auto-coding-agent-review",
        action="store_true",
        default=False,
        help=(
            "Copilot CLI SDK でローカルにコードレビューを実行する (デフォルト: 無効)。"
            "git diff を使用して差分を取得し、ローカルセッションでレビューする。"
            "GH_TOKEN / --repo は不要。"
        ),
    )
    orch.add_argument(
        "--auto-coding-agent-review-auto-approval",
        action="store_true",
        default=False,
        help="Code Review Agent の修正プランを全て自動承認 (デフォルト: 無効)",
    )

    # Issue/PR 作成
    orch.add_argument(
        "--create-issues",
        action="store_true",
        default=False,
        help=(
            "GitHub Issue を作成する (デフォルト: 作成しない)。"
            " 新規ブランチと PR が自動的に作成されます。"
            " --repo と GH_TOKEN が必要。"
        ),
    )
    orch.add_argument(
        "--create-pr",
        action="store_true",
        default=False,
        help=(
            "ローカル実行後に GitHub PR を作成する (デフォルト: 作成しない)。"
            " --branch から新ブランチを作成して作業し、完了後に PR をリクエスト。"
            " --repo と GH_TOKEN が必要。"
        ),
    )
    orch.add_argument(
        "--ignore-paths",
        nargs="+",
        default=None,
        metavar="PATH",
        help=(
            "git add 時に除外するパス (スペース区切りで複数指定可)。"
            " 未指定時は config のデフォルト値を使用。"
        ),
    )

    # 出力制御
    orch.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細出力 (--verbosity verbose と同等。--verbosity が指定された場合はそちらが優先)",
    )
    orch.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="出力抑制 (--verbosity quiet と同等。--verbosity が指定された場合はそちらが優先)",
    )
    orch.add_argument(
        "--verbosity",
        choices=["quiet", "compact", "normal", "verbose"],
        default=None,
        metavar="LEVEL",
        help=(
            "コンソール出力レベル: quiet (エラーのみ) / compact (重要イベントのみ、デフォルト) / "
            "normal (compact + intent/subagent) / verbose (全詳細)。"
            "--verbosity が最優先。未指定時は --verbose/--quiet フラグを参照"
        ),
    )
    orch.add_argument(
        "--show-stream",
        action="store_true",
        default=False,
        help="モデル応答のトークンストリーム表示を有効化 (デフォルト: 無効)",
    )
    orch.add_argument(
        "--log-level",
        default="error",
        choices=["none", "error", "warning", "info", "debug", "all"],
        metavar="LEVEL",
        help="Copilot CLI のログレベル: none/error/warning/info/debug/all (デフォルト: error)",
    )

    # MCP Server
    orch.add_argument(
        "--mcp-config",
        default=None,
        metavar="PATH",
        help="MCP Server 設定 JSON ファイルパス",
    )

    # CLI 接続
    orch.add_argument(
        "--cli-path",
        default=None,
        metavar="PATH",
        help="Copilot CLI 実行ファイルパス (省略時: PATH から自動検出)",
    )
    orch.add_argument(
        "--cli-url",
        default=None,
        metavar="URL",
        help="外部 CLI サーバー URL (例: localhost:4321)",
    )

    # タイムアウト
    orch.add_argument(
        "--timeout",
        type=float,
        default=21600.0,
        metavar="SECONDS",
        help="idle タイムアウト秒数 (デフォルト: 21600 = 6時間)",
    )
    orch.add_argument(
        "--review-timeout",
        type=float,
        default=7200.0,
        metavar="SECONDS",
        help="Code Review Agent レビュー完了待ちタイムアウト秒数 (デフォルト: 7200 = 2時間)",
    )

    # ブランチ
    orch.add_argument(
        "--branch",
        default="main",
        metavar="BRANCH",
        help="ベースブランチ (デフォルト: main)",
    )

    # ステップ選択
    orch.add_argument(
        "--steps",
        default=None,
        metavar="STEP_IDS",
        help="実行ステップをカンマ区切りで指定 (省略時: 全ステップ)",
    )

    # ワークフロー固有パラメータ
    orch.add_argument(
        "--app-id",
        default=None,
        metavar="APP_ID",
        help="アプリ ID (ASDW/ABDV 等で使用)。後方互換のため残す。複数指定は --app-ids を使用",
    )
    orch.add_argument(
        "--app-ids",
        default=None,
        metavar="APP_IDS",
        help="対象アプリケーション (APP-ID) — カンマ区切りで複数指定可 (例: APP-01,APP-02,APP-03)",
    )
    orch.add_argument(
        "--resource-group",
        default=None,
        metavar="RG",
        help="Azure リソースグループ名",
    )
    orch.add_argument(
        "--batch-job-id",
        default=None,
        metavar="JOB_ID",
        help="バッチジョブ ID (ABDV 等で使用、カンマ区切り可)",
    )
    orch.add_argument(
        "--usecase-id",
        default=None,
        metavar="UC_ID",
        help="ユースケース ID (ASDW 等で使用)",
    )

    # AKM 固有パラメータ
    orch.add_argument(
        "--sources",
        choices=["qa", "original-docs", "both"],
        default="qa",
        help="AKM: 取り込みソース (qa / original-docs / both)",
    )
    orch.add_argument(
        "--target-files",
        nargs="+",
        default=None,
        metavar="FILE",
        help="AKM: 対象ファイルパス (省略時: --sources で選択したソース配下の全件)",
    )
    orch.add_argument(
        "--force-refresh",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="AKM: 既存 status.md を完全に再生成する (デフォルト: 有効。--no-force-refresh で無効化)",
    )
    orch.add_argument(
        "--custom-source-dir",
        nargs="+",
        default=None,
        metavar="PATH",
        help="AKM: custom_source_dir 追加入力（複数指定可）",
    )
    orch.add_argument(
        "--target-scope",
        default=None,
        metavar="PATH",
        help="AQOD: チェック対象スコープ（省略時: original-docs/）",
    )
    orch.add_argument(
        "--depth",
        choices=["standard", "lightweight"],
        default=None,
        help="AQOD: 分析の深さ（standard / lightweight）",
    )
    orch.add_argument(
        "--focus-areas",
        default=None,
        metavar="TEXT",
        help="AQOD: 重点観点（任意）",
    )
    orch.add_argument(
        "--target-dirs",
        default=None,
        metavar="DIRS",
        help="ADOC: ドキュメント生成対象ディレクトリ（カンマ区切り。省略 = 全体）",
    )
    orch.add_argument(
        "--exclude-patterns",
        default=None,
        metavar="PATTERNS",
        help="ADOC: 除外パターン（カンマ区切り。デフォルト: node_modules/,vendor/,dist/,*.lock,__pycache__/）",
    )
    orch.add_argument(
        "--doc-purpose",
        choices=["all", "onboarding", "refactoring", "migration"],
        default=None,
        help="ADOC: ドキュメントの主目的",
    )
    orch.add_argument(
        "--max-file-lines",
        type=int,
        default=None,
        metavar="N",
        help="ADOC: 大規模ファイル分割閾値（行数。デフォルト: 500）",
    )

    # repo / token
    orch.add_argument(
        "--repo",
        default=None,
        metavar="OWNER/REPO",
        help="リポジトリ (owner/repo 形式, REPO 環境変数からも取得)",
    )

    # 追加プロンプト
    orch.add_argument(
        "--additional-prompt",
        default=None,
        metavar="PROMPT",
        help="全 Custom Agent の prompt 末尾に追記する文字列 (省略可)",
    )

    # 追加コメント
    orch.add_argument(
        "--additional-comment",
        default=None,
        metavar="COMMENT",
        help="追加コメント（Issue body の ## 追加コメント セクションに反映される）",
    )

    # Issue タイトル
    orch.add_argument(
        "--issue-title",
        default=None,
        metavar="TITLE",
        help=(
            "Issue 作成時の Root Issue タイトルを上書きする (省略可)。"
            "未指定時は '[PREFIX] ワークフロー名' を使用。"
        ),
    )

    # ドライラン
    orch.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="ドライラン（実際の SDK 呼び出しをしない）",
    )

    # Self-Improve
    orch.add_argument(
        "--no-self-improve",
        action="store_true",
        default=False,
        help=(
            "自己改善ループ（Phase 4）を無効化する（デフォルト: 有効）。"
            " auto_self_improve=True がデフォルトであり、このフラグで無効化できる。"
        ),
    )

    # --- qa-merge サブコマンド ---
    qa_merge = sub.add_parser(
        "qa-merge",
        help="qa/ 配下の質問票ファイルにユーザー回答をマージし、統合ドキュメントを生成する",
    )
    qa_merge.add_argument(
        "--qa-file",
        required=True,
        metavar="PATH",
        help="マージ対象の qa/ ファイルパス",
    )
    qa_merge.add_argument(
        "--answers-file",
        default=None,
        metavar="PATH",
        help="回答ファイルパス（番号: 選択肢 形式。省略時: デフォルト回答を採用）",
    )
    qa_merge.add_argument(
        "--use-defaults",
        action="store_true",
        default=False,
        help="全問デフォルト回答を採用する",
    )
    qa_merge.add_argument(
        "--skip-consistency",
        action="store_true",
        default=False,
        help="一貫性検証（LLM）をスキップし、マージのみ実行する",
    )
    qa_merge.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help=f"一貫性検証に使用するモデル（デフォルト: {DEFAULT_MODEL}）",
    )

    return parser


# -----------------------------------------------------------------------
# MCP 設定読み込み
# -----------------------------------------------------------------------

def _load_mcp_config(mcp_config_path: Optional[str]) -> Optional[dict]:
    """MCP Server 設定 JSON ファイルを読み込む。"""
    if not mcp_config_path:
        return None

    path = Path(mcp_config_path)
    if not path.exists():
        print(f"{_ts()} ⚠️  MCP 設定ファイルが見つかりません: {mcp_config_path}", file=sys.stderr)
        return None

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{_ts()} ❌ MCP 設定ファイルの読み込みに失敗しました: {exc}", file=sys.stderr)
        return None


# -----------------------------------------------------------------------
# SDKConfig 構築
# -----------------------------------------------------------------------

def _build_config(args: argparse.Namespace):
    """argparse の Namespace から SDKConfig を構築する。"""
    # モジュールのインポート
    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .config import DEFAULT_MODEL, MODEL_CHOICES, SDKConfig
    except ImportError:
        from config import DEFAULT_MODEL, MODEL_CHOICES, SDKConfig  # type: ignore[no-redef]

    # 環境変数から base 設定を読み込み
    cfg = SDKConfig.from_env()

    # CLI 引数で上書き
    env_model = os.environ.get("MODEL")
    cli_model = args.model
    # 優先順位: 明示 CLI > MODEL 環境変数 > 既定値
    if cli_model is not None:
        cfg.model = cli_model
    elif env_model:
        cfg.model = env_model
    else:
        cfg.model = DEFAULT_MODEL
    # Auto モデル解決
    cfg.model, _ = _resolve_model(cfg.model)
    _raw_review_model = getattr(args, "review_model", None)
    if _raw_review_model:
        cfg.review_model, _ = _resolve_model(_raw_review_model)
    elif getattr(cfg, "review_model", None):
        cfg.review_model, _ = _resolve_model(cfg.review_model)
    _raw_qa_model = getattr(args, "qa_model", None)
    if _raw_qa_model:
        cfg.qa_model, _ = _resolve_model(_raw_qa_model)
    elif getattr(cfg, "qa_model", None):
        cfg.qa_model, _ = _resolve_model(cfg.qa_model)
    cfg.max_parallel = args.max_parallel
    cfg.auto_qa = args.auto_qa
    cfg.force_interactive = getattr(args, "force_interactive", False)
    cfg.auto_contents_review = args.auto_contents_review
    cfg.auto_coding_agent_review = args.auto_coding_agent_review
    cfg.auto_coding_agent_review_auto_approval = args.auto_coding_agent_review_auto_approval
    cfg.create_issues = args.create_issues
    cfg.create_pr = args.create_pr
    cfg.verbose = args.verbose or not args.quiet  # verbose はデフォルト True; --quiet で抑制
    cfg.quiet = args.quiet
    cfg.show_stream = args.show_stream
    cfg.log_level = args.log_level

    # --verbosity 明示指定 > --verbose/--quiet フラグ > デフォルト
    _verbosity_map = {"quiet": 0, "compact": 1, "normal": 2, "verbose": 3}
    if getattr(args, "verbosity", None) is not None:
        cfg.verbosity = _verbosity_map[args.verbosity]
    elif args.quiet:
        cfg.verbosity = 0
    elif args.verbose:
        cfg.verbosity = 3
    else:
        cfg.verbosity = 1  # デフォルト: compact
    cfg.timeout_seconds = args.timeout
    cfg.review_timeout_seconds = args.review_timeout
    cfg.base_branch = args.branch
    cfg.dry_run = args.dry_run
    cfg.additional_prompt = args.additional_prompt

    # Self-Improve: --no-self-improve フラグで無効化
    cfg.self_improve_skip = getattr(args, "no_self_improve", False)

    if args.cli_path:
        cfg.cli_path = args.cli_path
    if args.cli_url:
        cfg.cli_url = args.cli_url

    # リポジトリ（CLI 引数 > 環境変数）
    if args.repo:
        cfg.repo = args.repo
    elif not cfg.repo:
        cfg.repo = os.environ.get("REPO", "")

    # MCP 設定
    mcp = _load_mcp_config(args.mcp_config)
    if mcp:
        cfg.mcp_servers = mcp

    # 無視パス（CLI 引数が指定された場合のみ上書き）
    if getattr(args, "ignore_paths", None):
        cfg.ignore_paths = args.ignore_paths

    return cfg


# -----------------------------------------------------------------------
# params dict 構築
# -----------------------------------------------------------------------

def _build_params(args: argparse.Namespace) -> dict:
    """CLI 引数からワークフローパラメータ dict を構築する。"""
    params: dict = {
        "branch": args.branch,
        "auto_qa": args.auto_qa,
        "auto_contents_review": args.auto_contents_review,
        "no_self_improve": getattr(args, "no_self_improve", False),
    }

    # ステップ選択
    if args.steps:
        params["steps"] = [s.strip() for s in args.steps.split(",") if s.strip()]
    else:
        params["steps"] = []

    # ワークフロー固有
    if getattr(args, "app_ids", None):
        params["app_ids"] = [s.strip() for s in args.app_ids.split(",") if s.strip()]
        if len(params["app_ids"]) == 1:
            params["app_id"] = params["app_ids"][0]
    elif args.app_id:
        params["app_ids"] = [args.app_id.strip()]
        params["app_id"] = args.app_id  # 後方互換
    if args.resource_group:
        params["resource_group"] = args.resource_group
    if args.batch_job_id:
        params["batch_job_id"] = args.batch_job_id
    if args.usecase_id:
        params["usecase_id"] = args.usecase_id

    # AKM 固有パラメータ
    if getattr(args, "workflow", None) == "akm":
        params["sources"] = getattr(args, "sources", None) or _AKM_DEFAULT_SOURCES
        target_files = getattr(args, "target_files", None)
        params["target_files"] = " ".join(target_files) if target_files else _default_akm_target_files(params["sources"])
        custom_source_dir = getattr(args, "custom_source_dir", None)
        params["custom_source_dir"] = " ".join(custom_source_dir) if custom_source_dir else ""
        # AKM では、フラグ未指定(None)の場合はデフォルトで True とする
        force_refresh = getattr(args, "force_refresh", None)
        params["force_refresh"] = True if force_refresh is None else force_refresh
    elif getattr(args, "workflow", None) == "aqod":
        params["target_scope"] = getattr(args, "target_scope", None) or _AQOD_DEFAULT_TARGET_SCOPE
        params["depth"] = getattr(args, "depth", None) or _AQOD_DEFAULT_DEPTH
        params["focus_areas"] = getattr(args, "focus_areas", None) or ""
    else:
        if getattr(args, "target_files", None):
            params["target_files"] = " ".join(args.target_files)
        if getattr(args, "custom_source_dir", None):
            params["custom_source_dir"] = " ".join(args.custom_source_dir)
        # 非 AKM では、CLI で明示された場合のみ force_refresh をパラメータに含める
        force_refresh = getattr(args, "force_refresh", None)
        if force_refresh is not None:
            params["force_refresh"] = force_refresh

    # ADOC 固有パラメータ
    if getattr(args, "workflow", None) == "adoc":
        params["target_dirs"] = getattr(args, "target_dirs", None) or ""
        params["exclude_patterns"] = getattr(args, "exclude_patterns", None) or "node_modules/,vendor/,dist/,*.lock,__pycache__/"
        params["doc_purpose"] = getattr(args, "doc_purpose", None) or "all"
        params["max_file_lines"] = getattr(args, "max_file_lines", None) or 500

    # Issue タイトル上書き
    if args.issue_title:
        params["issue_title"] = args.issue_title

    # 追加コメント
    if args.additional_comment:
        params["additional_comment"] = args.additional_comment

    return params


# -----------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """エントリポイント。

    Returns:
        終了コード (0: 成功, 1: 失敗)
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "orchestrate":
        return _cmd_orchestrate(args)

    if args.command == "qa-merge":
        return _cmd_qa_merge(args)

    # "run" サブコマンド、または引数なし → インタラクティブモード
    return _cmd_run_interactive()


def _validate_auto_coding_agent_review(args: argparse.Namespace, config: "SDKConfig") -> bool:
    """--auto-coding-agent-review の前提条件を検証する。

    Returns:
        True = バリデーション成功（実行続行）, False = バリデーション失敗（中断）
    """
    if not args.auto_coding_agent_review:
        if getattr(args, "auto_coding_agent_review_auto_approval", False):
            args.auto_coding_agent_review_auto_approval = False
        return True

    if not args.quiet:
        print(
            f"{_ts()} ℹ️  --auto-coding-agent-review が有効です。\n"
            "   Code Review Agent はローカルの GitHub Copilot CLI SDK で実行されます。",
            file=sys.stderr,
        )
    return True


def _cmd_run_interactive() -> int:
    """インタラクティブ wizard モードのハンドラー。

    GitHub Copilot CLI スタイルの対話型 UI でワークフローを選択・設定・実行する。
    """
    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .console import Console
        from .config import SDKConfig
        from .workflow_registry import list_workflows, get_workflow
        from .template_engine import _WORKFLOW_DISPLAY_NAMES
        from .orchestrator import run_workflow
    except ImportError:
        from console import Console  # type: ignore[no-redef]
        from config import SDKConfig  # type: ignore[no-redef]
        from workflow_registry import list_workflows, get_workflow  # type: ignore[no-redef]
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]
        from orchestrator import run_workflow  # type: ignore[no-redef]

    con = Console(verbose=True, quiet=False, verbosity=3)  # wizard UI の表示は常に verbose（ワークフロー実行の verbosity はユーザー選択値で別途設定）

    # ── ウェルカムバナー ──────────────────────────────────
    con.banner(
        "HVE — GitHub Copilot SDK Workflow Orchestrator",
        "ワークフローをインタラクティブに実行します",
    )

    # ── ワークフロー選択 ──────────────────────────────────
    workflows = list_workflows()
    wf_options = [
        f"{_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}  {con.s.DIM}({wf.id} — {len(wf.steps)} steps){con.s.RESET}"
        for wf in workflows
    ]
    wf_idx = con.menu_select("ワークフローを選択してください", wf_options)
    selected_wf = workflows[wf_idx]
    wf = get_workflow(selected_wf.id)
    is_akm = (wf.id == "akm")
    is_aqod = (wf.id == "aqod")
    is_single_step_workflow = is_akm or is_aqod

    # ── ステップ選択 ──────────────────────────────────────
    # AKM はステップが 1 つのみのため、自動で全選択
    if is_single_step_workflow:
        selected_step_ids = []  # 空 = 全ステップ
    else:
        non_container_steps = [s for s in wf.steps if not s.is_container]
        step_options = [f"[{s.id}] {s.title}" for s in non_container_steps]
        selected_indices = con.prompt_multi_select(
            f"実行するステップを選択（Enter = 全{len(non_container_steps)}ステップ）",
            step_options,
        )
        if selected_indices:
            selected_step_ids = [non_container_steps[i].id for i in selected_indices]
        else:
            selected_step_ids = []  # 空 = 全ステップ

    # ── モデル選択 ────────────────────────────────────────
    model_options = [MODEL_AUTO, *MODEL_CHOICES]
    model_idx = con.menu_select("使用するモデルを選択", model_options)
    model, model_display = _resolve_model(model_options[model_idx])
    review_model = None
    review_model_display = None
    qa_model = None
    qa_model_display = None
    use_different_models = con.prompt_yes_no(
        "レビュー/QA にメインモデルとは別のモデルを使う？", default=False
    )
    if use_different_models:
        _sub_model_options = model_options
        review_model_idx = con.menu_select("レビュー用モデルを選択", _sub_model_options)
        review_model, review_model_display = _resolve_model(_sub_model_options[review_model_idx])
        if review_model == model:
            review_model = None
            review_model_display = None
        qa_model_idx = con.menu_select("QA 用モデルを選択", _sub_model_options)
        qa_model, qa_model_display = _resolve_model(_sub_model_options[qa_model_idx])
        if qa_model == model:
            qa_model = None
            qa_model_display = None

    # ── 実行モード選択 ────────────────────────────────────
    _exec_mode_options = [
        "クイック全自動  — デフォルト値で即実行（確認あり）",
        "カスタム全自動  — 全設定を手動入力後に自動実行",
        "手動           — 従来どおり（実行中も対話あり）",
    ]
    exec_mode_idx = con.menu_select("実行モードを選択", _exec_mode_options)
    is_quick_auto = (exec_mode_idx == 0)
    is_custom_auto = (exec_mode_idx == 1)
    is_manual = (exec_mode_idx == 2)
    is_any_auto = is_quick_auto or is_custom_auto

    # ── オプション設定 ────────────────────────────────────
    if is_quick_auto:
        # クイック全自動: ステップ5〜7aをデフォルト値で自動設定
        branch = "main"
        max_parallel = 1 if is_single_step_workflow else 15
        verbosity_key = "normal"
        verbosity_value = 2  # normal（クイック全自動は長時間実行が前提のため、compact より情報量の多い normal を採用）
        timeout_val = 86400.0  # 24時間
        auto_qa = False
        qa_answer_mode = None
        force_interactive = False
        auto_review = False
        create_issues = False
        create_pr = False
        auto_coding_agent_review = False
        auto_coding_agent_review_auto_approval = False
        review_timeout = 7200.0
        repo_input = os.environ.get("REPO", "")
        dry_run = False
        # ワークフロー固有パラメータ
        params_extra: dict = {}
        if is_akm:
            params_extra["sources"] = _AKM_DEFAULT_SOURCES
            params_extra["target_files"] = _default_akm_target_files(params_extra["sources"])
            params_extra["force_refresh"] = True
        elif is_aqod:
            params_extra["target_scope"] = _AQOD_DEFAULT_TARGET_SCOPE
            params_extra["depth"] = _AQOD_DEFAULT_DEPTH
            params_extra["focus_areas"] = ""
        elif wf.params:
            # 非AKM かつ必須パラメータあり: 入力を求める（クイック全自動でも例外）
            for param_name in wf.params:
                if param_name == "doc_purpose":
                    val = _prompt_valid_doc_purpose(con)
                else:
                    val = con.prompt_input(f"{param_name}", required=True)
                params_extra[param_name] = val
        additional_prompt = None
    else:
        # カスタム全自動 or 手動: 既存のインタラクティブ入力フロー
        branch = con.prompt_input("ベースブランチ", default="main")
        if is_single_step_workflow:
            max_parallel = 1
        else:
            max_parallel = int(con.prompt_input("並列実行数", default="15") or "15")

        # ── 出力レベル選択（verbosity）────────────────────────
        _verbosity_options = [
            "quiet   — エラーのみ",
            "compact — 重要イベントのみ",
            "normal  — compact + intent/subagent",
            "verbose — 全詳細",
        ]
        _verbosity_keys = ["quiet", "compact", "normal", "verbose"]
        _VERBOSITY_DEFAULT = 1  # compact
        con._print(f"  {con.s.DIM}(Enter = compact){con.s.RESET}", ts=False)
        _raw_idx = con.menu_select("コンソール出力レベルを選択", _verbosity_options, allow_empty=True)
        verbosity_idx = _VERBOSITY_DEFAULT if _raw_idx == -1 else _raw_idx
        verbosity_key = _verbosity_keys[verbosity_idx]
        verbosity_value = verbosity_idx  # quiet=0, compact=1, normal=2, verbose=3

        # ── タイムアウト設定 ────────────────────────────────
        if is_custom_auto:
            _timeout_label = "セッション idle タイムアウト（秒。デフォルト: 86400 = 24時間）"
            _timeout_default = "86400"
            _timeout_fallback = 86400.0
        else:
            _timeout_label = "セッション idle タイムアウト（秒。デフォルト: 21600 = 6時間）"
            _timeout_default = "21600"
            _timeout_fallback = 21600.0
        timeout_str = con.prompt_input(_timeout_label, default=_timeout_default)
        try:
            timeout_val = float(timeout_str or _timeout_default)
        except ValueError:
            con.warning(f"無効な値のため、デフォルトの {_timeout_default} 秒を使用します。")
            timeout_val = _timeout_fallback
        if timeout_val <= 0:
            con.warning(f"0 以下のタイムアウト値は無効なため、デフォルトの {_timeout_default} 秒を使用します。")
            timeout_val = _timeout_fallback

        if is_single_step_workflow:
            auto_qa = False
            auto_review = False
            qa_answer_mode = None
            force_interactive = False
        else:
            auto_qa = con.prompt_yes_no("QA 自動投入を有効にする？", default=False)
            if auto_qa:
                qa_answer_mode = con.prompt_answer_mode()
                force_interactive = con.prompt_yes_no(
                    "インタラクティブ入力を強制する（IDE 等で stdin が非 TTY 扱いになる場合）？",
                    default=False,
                )
            else:
                qa_answer_mode = None
                force_interactive = False
            auto_review = con.prompt_yes_no("Review 自動投入を有効にする？", default=False)
        create_issues = con.prompt_yes_no("GitHub Issue を作成する？", default=False)
        create_pr = con.prompt_yes_no("GitHub PR を作成する？", default=False) if not create_issues else True

        # ── Code Review Agent ─────────────────────────────
        auto_coding_agent_review = con.prompt_yes_no(
            "GitHub Copilot Code Review Agent（ローカル実行）を有効にする？", default=False
        )
        auto_coding_agent_review_auto_approval = False
        review_timeout = 7200.0
        if auto_coding_agent_review:
            auto_coding_agent_review_auto_approval = con.prompt_yes_no(
                "Code Review Agent の修正提案を自動承認する？", default=False
            )
            review_timeout_str = con.prompt_input(
                "Review タイムアウト（秒。デフォルト: 7200 = 2時間）", default="7200"
            )
            try:
                review_timeout = float(review_timeout_str or "7200")
            except ValueError:
                con.warning("無効な値のため、デフォルトの 7200 秒を使用します。")
                review_timeout = 7200.0
            if review_timeout <= 0:
                con.warning("0 以下の値は無効なため、デフォルトの 7200 秒を使用します。")
                review_timeout = 7200.0

        # ── リポジトリ入力（Issue/PR 作成時のみ） ─────────────
        repo_input = ""
        if create_issues or create_pr:
            repo_default = os.environ.get("REPO", "")
            repo_input = con.prompt_input("リポジトリ (owner/repo)", default=repo_default, required=True)

        dry_run = con.prompt_yes_no("ドライラン（実際の SDK 呼び出しをしない）？", default=False)

        # ── ワークフロー固有パラメータ ────────────────────────
        params_extra: dict = {}
        if is_akm:
            # AKM の固有パラメータはデフォルト値で自動設定
            params_extra["sources"] = _AKM_DEFAULT_SOURCES
            params_extra["target_files"] = _default_akm_target_files(params_extra["sources"])
            params_extra["force_refresh"] = True
        elif is_aqod:
            params_extra["target_scope"] = con.prompt_input(
                "target_scope", default=_AQOD_DEFAULT_TARGET_SCOPE
            )
            params_extra["depth"] = _prompt_valid_aqod_depth(con)
            params_extra["focus_areas"] = con.prompt_input("focus_areas", default="")
        else:
            for param_name in wf.params:
                if param_name == "doc_purpose":
                    val = _prompt_valid_doc_purpose(con)
                else:
                    val = con.prompt_input(f"{param_name}", required=True)
                params_extra[param_name] = val

        # ── 追加プロンプト ────────────────────────────────────
        additional_prompt = con.prompt_input("追加プロンプト（省略可）")


    # ── 確認パネル ────────────────────────────────────────
    s = con.s
    step_display = ", ".join(selected_step_ids) if selected_step_ids else "全ステップ"
    summary_lines = []
    if is_quick_auto:
        summary_lines.append(f"実行モード   : {s.GREEN}クイック全自動{s.RESET}")
    elif is_custom_auto:
        summary_lines.append(f"実行モード   : {s.GREEN}カスタム全自動{s.RESET}")
    summary_lines += [
        f"ワークフロー : {s.CYAN}{_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}{s.RESET} ({wf.id})",
        f"ステップ     : {step_display}",
        f"モデル       : {model_display}",
        f"レビューモデル: {review_model_display or '(メインと同じ)'}",
        f"QA モデル    : {qa_model_display or '(メインと同じ)'}",
        f"ブランチ     : {branch}",
        f"並列数       : {max_parallel}",
        f"出力レベル   : {verbosity_key}",
        f"タイムアウト  : {timeout_val:.0f} 秒",
        f"QA 自動      : {'ON' if auto_qa else 'OFF'}",
    ]
    if auto_qa and qa_answer_mode:
        _qa_mode_display = "全問一括" if qa_answer_mode == "all" else "1問ずつ" if qa_answer_mode == "one" else qa_answer_mode
        summary_lines.append(f"QA 回答モード : {_qa_mode_display}")
    if auto_qa and force_interactive:
        summary_lines.append(f"強制インタラクティブ: ON")
    summary_lines += [
        f"Review 自動  : {'ON' if auto_review else 'OFF'}",
        f"Issue 作成   : {'ON' if create_issues else 'OFF'}",
        f"PR  作成     : {'ON' if create_pr else 'OFF'}",
        f"Code Review  : {'ON' if auto_coding_agent_review else 'OFF'}",
    ]
    if auto_coding_agent_review:
        summary_lines += [
            f"自動承認     : {'ON' if auto_coding_agent_review_auto_approval else 'OFF'}",
            f"タイムアウト : {review_timeout}s",
        ]
    summary_lines += [
        f"リポジトリ   : {repo_input or '(なし)'}",
        f"ドライラン   : {'ON' if dry_run else 'OFF'}",
    ]
    for k, v in params_extra.items():
        summary_lines.append(f"{k:<13}: {v}")
    if additional_prompt:
        summary_lines.append(f"追加プロンプト: {additional_prompt[:50]}{'...' if len(additional_prompt) > 50 else ''}")

    con.panel("実行設定", summary_lines)

    # ── 実行確認 ──────────────────────────────────────────
    if not con.prompt_yes_no("この設定で実行しますか？", default=True):
        con._print(f"\n  {s.YELLOW}キャンセルしました。{s.RESET}", ts=False)
        return 0

    if is_any_auto:
        con._print(f"\n  {s.GREEN}✓ 全自動モードで実行を開始します。実行中の入力は不要です。{s.RESET}", ts=False)

    # ── SDKConfig 構築 ────────────────────────────────────
    cfg = SDKConfig.from_env()
    cfg.model = model
    if review_model is not None:
        cfg.review_model = review_model
    if qa_model is not None:
        cfg.qa_model = qa_model
    cfg.max_parallel = max_parallel
    cfg.auto_qa = auto_qa
    cfg.force_interactive = force_interactive
    cfg.auto_contents_review = auto_review
    cfg.qa_answer_mode = qa_answer_mode
    cfg.create_issues = create_issues
    cfg.create_pr = create_pr or create_issues
    cfg.verbosity = verbosity_value
    cfg.verbose = verbosity_value >= 3
    cfg.quiet = verbosity_value == 0
    cfg.show_stream = False
    cfg.log_level = "error"
    cfg.base_branch = branch
    cfg.dry_run = dry_run
    cfg.auto_coding_agent_review = auto_coding_agent_review
    cfg.auto_coding_agent_review_auto_approval = (
        auto_coding_agent_review_auto_approval if auto_coding_agent_review else False
    )
    cfg.timeout_seconds = timeout_val
    cfg.review_timeout_seconds = review_timeout
    cfg.additional_prompt = additional_prompt or None
    if repo_input:
        cfg.repo = repo_input
    elif not cfg.repo:
        cfg.repo = os.environ.get("REPO", "")

    # ── 全自動モードフラグを SDKConfig に反映 ─────────────
    cfg.unattended = is_any_auto
    if is_any_auto:
        cfg.force_interactive = False
        if cfg.auto_qa:
            cfg.qa_answer_mode = "all"  # 全自動モード時は QA 全問デフォルト値を一括採用（非TTY扱い）
        if cfg.auto_coding_agent_review:
            cfg.auto_coding_agent_review_auto_approval = True  # 自動承認を強制

    # params dict 構築
    params: dict = {
        "branch": branch,
        "auto_qa": auto_qa,
        "auto_contents_review": auto_review,
        "steps": selected_step_ids,
        "qa_answer_mode": qa_answer_mode,
    }
    params.update(params_extra)

    # ── バリデーション ────────────────────────────────────
    if cfg.create_issues or cfg.create_pr:
        errors: List[str] = []
        if not cfg.repo:
            errors.append("  REPO 環境変数が必要です。")
        if not cfg.resolve_token():
            errors.append("  GH_TOKEN（または GITHUB_TOKEN）環境変数が必要です。")
        if errors:
            for e in errors:
                con.error(e)
            return 1

    # ── 実行 ──────────────────────────────────────────────
    con._print("", ts=False)
    try:
        result = asyncio.run(
            run_workflow(
                workflow_id=wf.id,
                params=params,
                config=cfg,
            )
        )
    except KeyboardInterrupt:
        con._print(f"\n  {s.YELLOW}中断されました。{s.RESET}")
        return 1

    # ── 結果表示 ──────────────────────────────────────────
    if result.get("error"):
        con.error(str(result["error"]))
        return 1
    if result.get("code_review_error"):
        con.error(f"Code Review Agent エラー: {result['code_review_error']}")
        return 1
    if result.get("failed"):
        return 1
    con._print(f"\n  {s.GREEN}✓{s.RESET} ワークフロー完了\n")
    return 0


def _cmd_qa_merge(args: argparse.Namespace) -> int:
    """qa-merge サブコマンドのハンドラー。

    qa/ ファイルにユーザー回答をマージして保存し、
    --skip-consistency 未指定時は CopilotSession で統合ドキュメントを生成する。
    """
    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .qa_merger import QAMerger
        from .prompts import QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT
    except ImportError:
        from qa_merger import QAMerger  # type: ignore[no-redef]
        from prompts import QA_MERGE_SAVE_PROMPT, QA_CONSOLIDATE_PROMPT  # type: ignore[no-redef]

    qa_path = Path(args.qa_file)
    if not qa_path.exists():
        print(f"{_ts()} ❌ qa/ ファイルが見つかりません: {qa_path}", file=sys.stderr)
        return 1

    # ── ファイルパース ────────────────────────────────────
    try:
        doc = QAMerger.parse_qa_file(qa_path)
    except Exception as exc:
        print(f"{_ts()} ❌ qa/ ファイルのパースに失敗しました: {exc}", file=sys.stderr)
        return 1

    # ── マージ済み判定 ────────────────────────────────────
    already_merged = any(q.user_answer is not None for q in doc.questions)
    if already_merged:
        print(
            f"{_ts()} ⚠️  ファイルには既にユーザー回答が含まれています: {qa_path}\n"
            "   再マージします（既存の回答は上書きされます）。",
            file=sys.stderr,
        )

    # ── 回答読み込み ──────────────────────────────────────
    answers: "dict[int, str]" = {}
    use_defaults = args.use_defaults

    if args.answers_file:
        answers_path = Path(args.answers_file)
        if not answers_path.exists():
            print(
                f"{_ts()} ❌ 回答ファイルが見つかりません: {answers_path}", file=sys.stderr
            )
            return 1
        answer_text = answers_path.read_text(encoding="utf-8")
        answers = QAMerger.parse_answers(answer_text)
        if not answers:
            print(
                f"{_ts()} ⚠️  回答ファイルに有効な回答が見つかりません。"
                " デフォルト回答を採用します。",
                file=sys.stderr,
            )
            use_defaults = True
    elif not use_defaults:
        # --answers-file も --use-defaults も未指定の場合はデフォルト採用
        use_defaults = True

    # ── マージ ────────────────────────────────────────────
    try:
        merged_doc = QAMerger.merge_answers(doc, answers, use_defaults=use_defaults)
        merged_content = QAMerger.render_merged(merged_doc)
    except Exception as exc:
        print(f"{_ts()} ❌ マージ処理に失敗しました: {exc}", file=sys.stderr)
        return 1

    # ── 保存（write → read-back → retry 3回） ────────────
    if not QAMerger.save_merged(merged_content, qa_path):
        print(f"{_ts()} ❌ ファイル保存に失敗しました: {qa_path}", file=sys.stderr)
        return 1

    print(f"{_ts()} ✅ マージ済みファイルを保存しました: {qa_path}")

    # ── 統合ドキュメント生成（--skip-consistency 未指定時） ──
    if args.skip_consistency:
        print(f"{_ts()} ℹ️  --skip-consistency が指定されました。統合ドキュメント生成をスキップします。")
        return 0

    consolidated_path = QAMerger.generate_consolidated_path(qa_path)

    try:
        from .config import SDKConfig
        from .console import Console
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]
        from console import Console  # type: ignore[no-redef]

    try:
        try:
            from copilot import CopilotClient, SubprocessConfig  # type: ignore[import]
            from copilot.session import CopilotSession  # type: ignore[import]
        except ImportError:
            # github_copilot_sdk パッケージ名でのフォールバック
            try:
                from github_copilot_sdk import CopilotClient, SubprocessConfig  # type: ignore[import]
                from github_copilot_sdk.session import CopilotSession  # type: ignore[import]
            except ImportError:
                print(
                    f"{_ts()} ⚠️  GitHub Copilot SDK が見つかりません。"
                    " 統合ドキュメント生成をスキップします。",
                    file=sys.stderr,
                )
                return 0

        model, _ = _resolve_model(args.model)  # _ = display name (unused here)
        cfg = SDKConfig.from_env()
        cfg.model = model

        sdk_cfg = SubprocessConfig(
            cli_path=cfg.cli_path,
            github_token=cfg.resolve_token() or None,
            log_level="error",
        )
        client = CopilotClient(config=sdk_cfg)

        async def _generate_consolidated() -> int:
            await client.start()
            async with CopilotSession(
                client=client,
                model=model,
            ) as session:
                consolidate_prompt = QA_CONSOLIDATE_PROMPT.format(
                    merged_qa_content=merged_content,
                )
                response = await session.send_and_wait(consolidate_prompt, timeout=1800.0)

                # 統合ドキュメントを保存
                if response:
                    content_text = ""
                    data = getattr(response, "data", None)
                    if data:
                        for attr in ("content", "message"):
                            val = getattr(data, attr, None)
                            if val:
                                content_text = str(val)
                                break
                    if not content_text:
                        content_text = str(response)

                    if QAMerger.save_merged(content_text, consolidated_path):
                        print(
                            f"{_ts()} ✅ 統合ドキュメントを保存しました: {consolidated_path}"
                        )
                    else:
                        print(
                            f"{_ts()} ⚠️  統合ドキュメントの保存に失敗しました。",
                            file=sys.stderr,
                        )
            await client.stop()
            return 0

        return asyncio.run(_generate_consolidated())

    except Exception as exc:
        print(
            f"{_ts()} ⚠️  統合ドキュメント生成に失敗しました（マージ済みファイルは保存済み）: {exc}",
            file=sys.stderr,
        )
        return 0


def _cmd_orchestrate(args: argparse.Namespace) -> int:
    """orchestrate サブコマンドのハンドラー。"""
    # バリデーション: --auto-coding-agent-review-auto-approval は --auto-coding-agent-review と併用必須
    if args.auto_coding_agent_review_auto_approval and not args.auto_coding_agent_review:
        print(
            f"{_ts()} ⚠️  --auto-coding-agent-review-auto-approval は --auto-coding-agent-review と"
            " 組み合わせて使用してください。\n"
            "   --auto-coding-agent-review が指定されていないため --auto-coding-agent-review-auto-approval は無視されます。",
            file=sys.stderr,
        )
        args.auto_coding_agent_review_auto_approval = False

    # --create-issues 指定時は必ず PR を作成する
    if args.create_issues:
        args.create_pr = True

    # インポート
    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .orchestrator import run_workflow
    except ImportError:
        from orchestrator import run_workflow  # type: ignore[no-redef]

    config = _build_config(args)
    params = _build_params(args)

    # バリデーション: --create-issues または --create-pr には GH_TOKEN と --repo が必要
    if config.create_issues or config.create_pr:
        errors: List[str] = []
        if not config.repo:
            errors.append("  --repo（または REPO 環境変数）が必要です。")
        if not config.resolve_token():
            errors.append("  GH_TOKEN（または GITHUB_TOKEN）環境変数が必要です。")
        if errors:
            print(
                f"{_ts()} ❌ --create-issues / --create-pr の前提条件が満たされていません:\n"
                + "\n".join(errors),
                file=sys.stderr,
            )
            return 1

    if not _validate_auto_coding_agent_review(args, config):
        return 1

    result = asyncio.run(
        run_workflow(
            workflow_id=args.workflow,
            params=params,
            config=config,
        )
    )

    # 終了コード判定
    if result.get("error"):
        return 1
    if result.get("failed"):
        return 1
    if result.get("code_review_error"):
        print(f"{_ts()} ⚠️  Code Review Agent でエラーが発生しました: {result['code_review_error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
