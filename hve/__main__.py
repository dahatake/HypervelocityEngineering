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

    # 基本実行 (デフォルト: claude-opus-4.6, 並列15, verbose, Issue/PR作成なし)
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

    # QA 要求分類（全ファイル）
    python -m hve orchestrate --workflow aqrc --scope all

    # QA 要求分類（指定ファイルのみ）
    python -m hve orchestrate --workflow aqrc --scope specified \\
      --target-files qa/AAS-Step1-context-review.md qa/AAD-Step1-2-service-list-context-review.md

    # QA 要求分類（既存 status.md を完全再生成）
    python -m hve orchestrate --workflow aqrc --scope all --force-refresh
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


def _ts() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


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
        help="ワークフロー ID: aas / aad / asdw / abd / abdv / aid / aqrc",
    )

    # モデル
    orch.add_argument(
        "--model", "-m",
        default="claude-opus-4.6",
        metavar="MODEL",
        help="使用するモデル名 (デフォルト: claude-opus-4.6)",
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
        help="詳細出力を強制有効化 (デフォルトは --quiet 未指定時に有効)",
    )
    orch.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="出力抑制 (デフォルト: 無効)",
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
        default=900.0,
        metavar="SECONDS",
        help="idle タイムアウト秒数 (デフォルト: 900)",
    )
    orch.add_argument(
        "--review-timeout",
        type=float,
        default=900.0,
        metavar="SECONDS",
        help="Code Review Agent レビュー完了待ちタイムアウト秒数 (デフォルト: 900)",
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
        help="アプリ ID (ASDW/ABDV 等で使用)",
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

    # AQRC 固有パラメータ
    orch.add_argument(
        "--scope",
        choices=["all", "specified"],
        default=None,
        help="AQRC: 分類対象スコープ (all=全ファイル, specified=指定ファイルのみ)",
    )
    orch.add_argument(
        "--target-files",
        nargs="+",
        default=None,
        metavar="FILE",
        help="AQRC: 対象ファイルパス (--scope specified 時に使用)",
    )
    orch.add_argument(
        "--force-refresh",
        action="store_true",
        default=False,
        help="AQRC: 既存 status.md を完全に再生成する",
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
        from .config import SDKConfig
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]

    # 環境変数から base 設定を読み込み
    cfg = SDKConfig.from_env()

    # CLI 引数で上書き
    cfg.model = args.model
    cfg.max_parallel = args.max_parallel
    cfg.auto_qa = args.auto_qa
    cfg.auto_contents_review = args.auto_contents_review
    cfg.auto_coding_agent_review = args.auto_coding_agent_review
    cfg.auto_coding_agent_review_auto_approval = args.auto_coding_agent_review_auto_approval
    cfg.create_issues = args.create_issues
    cfg.create_pr = args.create_pr
    cfg.verbose = args.verbose or not args.quiet  # verbose はデフォルト True; --quiet で抑制
    cfg.quiet = args.quiet
    cfg.show_stream = args.show_stream
    cfg.log_level = args.log_level
    cfg.timeout_seconds = args.timeout
    cfg.review_timeout_seconds = args.review_timeout
    cfg.base_branch = args.branch
    cfg.dry_run = args.dry_run
    cfg.additional_prompt = args.additional_prompt

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
    }

    # ステップ選択
    if args.steps:
        params["steps"] = [s.strip() for s in args.steps.split(",") if s.strip()]
    else:
        params["steps"] = []

    # ワークフロー固有
    if args.app_id:
        params["app_id"] = args.app_id
    if args.resource_group:
        params["resource_group"] = args.resource_group
    if args.batch_job_id:
        params["batch_job_id"] = args.batch_job_id
    if args.usecase_id:
        params["usecase_id"] = args.usecase_id

    # AQRC 固有パラメータ
    if getattr(args, "scope", None):
        params["scope"] = args.scope
    if getattr(args, "target_files", None):
        params["target_files"] = " ".join(args.target_files)
    params["force_refresh"] = getattr(args, "force_refresh", False)

    # Issue タイトル上書き
    if args.issue_title:
        params["issue_title"] = args.issue_title

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

    con = Console(verbose=True, quiet=False)

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

    # ── ステップ選択 ──────────────────────────────────────
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
    model_options = ["claude-opus-4.6", "claude-sonnet-4.6", "gpt-5.4", "gpt-5.3-codex", "gemini-2.5-pro"]
    model_idx = con.menu_select("使用するモデルを選択", model_options)
    model = model_options[model_idx]

    # ── オプション設定 ────────────────────────────────────
    branch = con.prompt_input("ベースブランチ", default="main")
    max_parallel = int(con.prompt_input("並列実行数", default="15") or "15")

    # ── ログレベル選択 ────────────────────────────────────
    log_level_options = ["none", "error", "warning", "info", "debug", "all"]
    log_level_default_idx = log_level_options.index("error")
    con._print(f"  {con.s.DIM}(デフォルト: error){con.s.RESET}", ts=False)
    log_level_idx = con.menu_select("Copilot CLI ログレベルを選択", log_level_options)
    log_level = log_level_options[log_level_idx]

    auto_qa = con.prompt_yes_no("QA 自動投入を有効にする？", default=False)
    auto_review = con.prompt_yes_no("Review 自動投入を有効にする？", default=False)
    create_issues = con.prompt_yes_no("GitHub Issue を作成する？", default=False)
    create_pr = con.prompt_yes_no("GitHub PR を作成する？", default=False) if not create_issues else True

    # ── Code Review Agent ─────────────────────────────
    auto_coding_agent_review = con.prompt_yes_no(
        "GitHub Copilot Code Review Agent（ローカル実行）を有効にする？", default=False
    )
    auto_coding_agent_review_auto_approval = False
    review_timeout = 900.0
    if auto_coding_agent_review:
        auto_coding_agent_review_auto_approval = con.prompt_yes_no(
            "Code Review Agent の修正提案を自動承認する？", default=False
        )
        review_timeout_str = con.prompt_input(
            "Review タイムアウト（秒。デフォルト: 900 = 15分）", default="900"
        )
        try:
            review_timeout = float(review_timeout_str or "900")
        except ValueError:
            con.warning("無効な値のため、デフォルトの 900 秒を使用します。")
            review_timeout = 900.0

    # ── リポジトリ入力（Issue/PR 作成時のみ） ─────────────
    repo_input = ""
    if create_issues or create_pr:
        repo_default = os.environ.get("REPO", "")
        repo_input = con.prompt_input("リポジトリ (owner/repo)", default=repo_default, required=True)

    dry_run = con.prompt_yes_no("ドライラン（実際の SDK 呼び出しをしない）？", default=False)

    # ── ワークフロー固有パラメータ ────────────────────────
    params_extra: dict = {}
    for param_name in wf.params:
        val = con.prompt_input(f"{param_name}", required=True)
        params_extra[param_name] = val

    # ── 追加プロンプト ────────────────────────────────────
    additional_prompt = con.prompt_input("追加プロンプト（省略可）")

    # ── 確認パネル ────────────────────────────────────────
    s = con.s
    step_display = ", ".join(selected_step_ids) if selected_step_ids else "全ステップ"
    summary_lines = [
        f"ワークフロー : {s.CYAN}{_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}{s.RESET} ({wf.id})",
        f"ステップ     : {step_display}",
        f"モデル       : {model}",
        f"ブランチ     : {branch}",
        f"並列数       : {max_parallel}",
        f"ログレベル   : {log_level}",
        f"QA 自動      : {'ON' if auto_qa else 'OFF'}",
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

    # ── SDKConfig 構築 ────────────────────────────────────
    cfg = SDKConfig.from_env()
    cfg.model = model
    cfg.max_parallel = max_parallel
    cfg.auto_qa = auto_qa
    cfg.auto_contents_review = auto_review
    cfg.create_issues = create_issues
    cfg.create_pr = create_pr or create_issues
    cfg.verbose = True
    cfg.quiet = False
    cfg.show_stream = False
    cfg.log_level = log_level
    cfg.base_branch = branch
    cfg.dry_run = dry_run
    cfg.auto_coding_agent_review = auto_coding_agent_review
    cfg.auto_coding_agent_review_auto_approval = (
        auto_coding_agent_review_auto_approval if auto_coding_agent_review else False
    )
    cfg.review_timeout_seconds = review_timeout
    cfg.additional_prompt = additional_prompt or None
    if repo_input:
        cfg.repo = repo_input
    elif not cfg.repo:
        cfg.repo = os.environ.get("REPO", "")

    # params dict 構築
    params: dict = {
        "branch": branch,
        "auto_qa": auto_qa,
        "auto_contents_review": auto_review,
        "steps": selected_step_ids,
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
    con.spinner_start("ワークフローを実行中...")
    try:
        result = asyncio.run(
            run_workflow(
                workflow_id=wf.id,
                params=params,
                config=cfg,
            )
        )
    except KeyboardInterrupt:
        con.spinner_stop()
        con._print(f"\n  {s.YELLOW}中断されました。{s.RESET}")
        return 1
    finally:
        con.spinner_stop()

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

    # バリデーション: aqrc の --scope specified には --target-files が必須
    if args.workflow == "aqrc" and getattr(args, "scope", None) == "specified" and not getattr(args, "target_files", None):
        print(
            f"{_ts()} ❌ --scope specified を指定した場合は --target-files でファイルパスを指定してください。",
            file=sys.stderr,
        )
        return 1

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
