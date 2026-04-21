"""orchestrator.py — メインオーケストレーション

既存 CLI 版 (.github/cli/orchestrate.py) と同等の機能を
Copilot SDK でローカル実行するバージョン。

主な違い:
  - copilot_assign() は使用しない（全てローカル実行）
  - Issue/PR 作成はオプション（デフォルト: 作成しない）
  - 並列実行は asyncio.Semaphore で制御
  - Console 出力で進捗を表示

--create-issues 時のフロー:
  1. 新ブランチ作成 + checkout
  2. Issue 作成（Root + Sub-Issue。Copilot アサインなし）
  3. DAG 全ステップ実行
  4. git add（無視パス除外）+ commit + push（-u オプション付き）
  5. PR 作成（Issue 番号を PR body に記載）
  6. Code Review Agent レビュー（--auto-coding-agent-review 時のみ）
  7. サマリー出力（PR のレビュー・マージはユーザーに委任）
"""

from __future__ import annotations

import asyncio
import glob as _glob
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set

# -----------------------------------------------------------------------
# 内部モジュールのインポート（相対 / 絶対 の両方に対応）
# -----------------------------------------------------------------------
try:
    from .config import SDKConfig, generate_run_id
    from .console import Console, timestamp_prefix
    from .prompts import CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT
    from .runner import StepRunner, _is_review_fail, _extract_text
    from .dag_executor import DAGExecutor
except ImportError:
    from config import SDKConfig, generate_run_id  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompts import CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT  # type: ignore[no-redef]
    from runner import StepRunner, _is_review_fail, _extract_text  # type: ignore[no-redef]
    from dag_executor import DAGExecutor  # type: ignore[no-redef]

# -----------------------------------------------------------------------
# hve 内部モジュール（旧 .github/cli/ から移植済み）
# -----------------------------------------------------------------------
from hve.workflow_registry import get_workflow, WorkflowDef, list_workflows  # noqa: F401
from hve.template_engine import (
    render_template,
    resolve_selected_steps,
    build_root_issue_body,
    collect_params as cli_collect_params,
    _WORKFLOW_DISPLAY_NAMES,
    _WORKFLOW_PREFIX,
)
from hve.github_api import (
    GitHubAPIError,
    api_call,
    create_issue,
    link_sub_issue,
    post_comment,
    create_pull_request,
)


# -----------------------------------------------------------------------
# 定数
# -----------------------------------------------------------------------

_VALID_WORKFLOWS = [wf.id for wf in list_workflows()]

# Code Review Agent の GitHub ユーザー名候補
_COPILOT_USERNAMES = (
    "copilot",
    "github-copilot[bot]",
    "copilot[bot]",
    "copilot-swe-agent[bot]",
    "copilot-pull-request-reviewer[bot]",
)

# git diff の最大文字数（トークン上限対策）
_MAX_DIFF_CHARS = 80_000

# AKM デフォルト値
_AKM_DEFAULT_SOURCES = "qa"
_AKM_DEFAULT_TARGET_FILES = "qa/*.md"
_AQOD_DEFAULT_TARGET_SCOPE = "original-docs/"
_AQOD_DEFAULT_DEPTH = "standard"


def _default_akm_target_files(sources: str) -> str:
    """AKM の sources に応じた target_files 既定値を返す。"""
    if sources == "original-docs":
        return "original-docs/*"
    if sources == "both":
        return ""
    return _AKM_DEFAULT_TARGET_FILES


# -----------------------------------------------------------------------
# パラメータ収集（非対話モード対応）
# -----------------------------------------------------------------------

def _collect_params_non_interactive(
    wf,  # WorkflowDef
    cli_args: Optional[dict] = None,
) -> dict:
    """CLI 引数からパラメータを構築する（非対話モード）。

    全ての値が CLI 引数から提供されている場合に使用する。
    """
    args = cli_args or {}
    # 'steps' (CLI側) と 'selected_steps' (orchestrate.py側) の両キーに対応
    steps_value = args.get("steps") or args.get("selected_steps") or []
    params: dict = {
        "branch": args.get("branch", "main"),
        "selected_steps": steps_value,
        "skip_review": not args.get("auto_contents_review", False),
        "skip_qa": not args.get("auto_qa", False),
        "additional_comment": args.get("additional_comment", ""),
    }

    # ワークフロー固有パラメータ
    if args.get("app_ids"):
        params["app_ids"] = args["app_ids"]  # リストとしてそのまま渡す
        if len(args["app_ids"]) == 1:
            params["app_id"] = args["app_ids"][0]
    elif args.get("app_id"):
        params["app_ids"] = [args["app_id"]]
        params["app_id"] = args["app_id"]
    if args.get("resource_group"):
        params["resource_group"] = args["resource_group"]
    if args.get("usecase_id"):
        params["usecase_id"] = args["usecase_id"]
    if args.get("batch_job_id"):
        params["batch_job_id"] = args["batch_job_id"]

    # AKM 固有パラメータ
    if wf.id == "akm":
        params["sources"] = args.get("sources") or _AKM_DEFAULT_SOURCES
        params["target_files"] = args.get("target_files") or _default_akm_target_files(params["sources"])
        params["custom_source_dir"] = args.get("custom_source_dir") or ""
        force_refresh = args.get("force_refresh", None)
        params["force_refresh"] = True if force_refresh is None else force_refresh
        params["enable_auto_merge"] = args.get("enable_auto_merge", False)
    elif wf.id == "aqod":
        params["target_scope"] = args.get("target_scope") or _AQOD_DEFAULT_TARGET_SCOPE
        params["depth"] = args.get("depth") or _AQOD_DEFAULT_DEPTH
        params["focus_areas"] = args.get("focus_areas") or ""
    else:
        if args.get("sources"):
            params["sources"] = args["sources"]
        if args.get("target_files"):
            params["target_files"] = args["target_files"]
        if args.get("custom_source_dir"):
            params["custom_source_dir"] = args["custom_source_dir"]
        if args.get("target_scope"):
            params["target_scope"] = args["target_scope"]
        if args.get("depth"):
            params["depth"] = args["depth"]
        if args.get("focus_areas"):
            params["focus_areas"] = args["focus_areas"]
        # 非 AKM では、CLI で明示された場合のみ force_refresh をパラメータに含める
        if "force_refresh" in args:
            params["force_refresh"] = args["force_refresh"]

    # Issue タイトル上書き
    if args.get("issue_title"):
        params["issue_title"] = args["issue_title"]

    return params


def _is_non_interactive(wf, cli_args: Optional[dict]) -> bool:
    """非対話モードで実行すべきかを判定する。

    cli_args が None でなければ非対話モードとみなす。
    ワークフロー固有パラメータ（app_id, resource_group 等）は全て任意入力であり、
    未指定でも非対話モードで進める。
    """
    return cli_args is not None


# -----------------------------------------------------------------------
# Git ヘルパー
# -----------------------------------------------------------------------

def _git_checkout_new_branch(new_branch: str, base_branch: str, console: Console) -> bool:
    """ローカルで新ブランチを作成し checkout する。

    git fetch origin {base_branch} を事前に実行し、
    origin/{base_branch} からブランチを作成する。
    失敗した場合はローカルの base_branch でフォールバックする。
    """
    try:
        # fetch して最新の origin/{base_branch} を取得
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", base_branch],
            capture_output=True, text=True, timeout=60,
        )
        fetch_ok = fetch_result.returncode == 0
        if not fetch_ok:
            console.warning(f"git fetch origin {base_branch} に失敗しました（ローカルブランチでフォールバック）: {fetch_result.stderr.strip()}")

        # origin/{base_branch} からブランチ作成を試みる（fetch 成功時のみ）
        if fetch_ok:
            result = subprocess.run(
                ["git", "checkout", "-b", new_branch, f"origin/{base_branch}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                console.event(f"ブランチ '{new_branch}' を 'origin/{base_branch}' から作成し checkout しました。")
                return True
            console.warning(f"origin/{base_branch} からのブランチ作成に失敗。ローカルブランチでフォールバック: {result.stderr.strip()}")

        # フォールバック: ローカルの base_branch から作成
        fallback = subprocess.run(
            ["git", "checkout", "-b", new_branch, base_branch],
            capture_output=True, text=True, timeout=30,
        )
        if fallback.returncode != 0:
            console.error(f"ブランチ作成に失敗しました: {fallback.stderr.strip()}")
            return False
        console.event(f"ブランチ '{new_branch}' を '{base_branch}' から作成し checkout しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。PATH に git が含まれているか確認してください。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git checkout がタイムアウトしました。")
        return False


def _git_add_commit_push(
    branch: str,
    commit_message: str,
    console: Console,
    ignore_paths: Optional[List[str]] = None,
) -> bool:
    """変更を add + commit + push する。差分がなければ False を返す。

    ignore_paths に指定されたパスは git add の pathspec 除外で無視する。
    push 時は -u オプションを付与してリモートブランチをトラッキングする。
    """
    try:
        # 差分確認
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
        if not status.stdout.strip():
            console.warning("コミット対象の変更がありません。")
            return False

        # git add（除外パス付き）
        # subprocess.run はリスト呼び出しのため shell インジェクションは発生しない。
        # 各パスはそのまま git の pathspec 引数として渡す。
        add_args = ["git", "add", "."]
        if ignore_paths:
            for p in ignore_paths:
                # パスの先頭・末尾の空白と null バイトを除去
                sanitized = p.strip().replace("\x00", "")
                if sanitized:
                    add_args.append(f":!{sanitized}")
        add_result = subprocess.run(
            add_args,
            capture_output=True, text=True, timeout=30,
        )
        if add_result.returncode != 0:
            console.error(f"git add に失敗しました: {add_result.stderr.strip()}")
            return False

        # ステージングエリアの差分確認（除外後に差分がなければスキップ）
        cached_diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        if cached_diff.returncode == 0:
            console.warning("除外パスを適用後、コミット対象のステージング変更がありません。")
            return False

        # git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True, text=True, timeout=60,
        )
        if commit_result.returncode != 0:
            console.error(f"git commit に失敗しました: {commit_result.stderr.strip()}")
            return False
        console.event(f"変更をコミットしました: {commit_message}")

        # git push（-u でリモートブランチをトラッキング）
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True, text=True, timeout=120,
        )
        if push_result.returncode != 0:
            console.error(f"git push に失敗しました: {push_result.stderr.strip()}")
            return False
        console.event(f"ブランチ '{branch}' を push しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git 操作がタイムアウトしました。")
        return False


# -----------------------------------------------------------------------
# Issue/PR 作成ヘルパー
# -----------------------------------------------------------------------

def _create_issues_if_needed(
    wf,
    params: dict,
    active_steps: Set[str],
    config: SDKConfig,
    console: Console,
    render_template_fn,
    build_root_issue_body_fn,
) -> Optional[int]:
    """create_issues=True の場合のみ Root Issue + Sub-Issue を作成する。

    Returns:
        root_issue_num (int) または None（作成しない場合）
    """
    if not config.create_issues:
        return None

    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning("create_issues=True ですが GH_TOKEN または REPO が未設定のため Issue 作成をスキップします。")
        return None

    console.event("Root Issue を作成中...")
    root_body = build_root_issue_body_fn(wf, params)
    prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
    if params.get("issue_title"):
        root_title = params["issue_title"]
    else:
        root_title = f"[{prefix}] {_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}"
    root_issue_num, _ = create_issue(
        title=root_title,
        body=root_body,
        labels=[],
        repo=repo,
        token=token,
    )
    console.event(f"Root Issue #{root_issue_num} を作成しました。")

    # Sub-Issue 作成（active_steps に含まれるステップのみ）
    for step in wf.steps:
        if step.is_container:
            continue
        if step.id not in active_steps:
            continue
        if not step.body_template_path:
            continue

        body = render_template_fn(
            template_path=step.body_template_path,
            root_issue_num=root_issue_num,
            params=params,
            wf=wf,
        )
        step_title = f"[{prefix}] Step.{step.id} {step.title}"
        sub_num, sub_id = create_issue(
            title=step_title,
            body=body,
            labels=[],
            repo=repo,
            token=token,
        )
        console.event(f"Sub-Issue #{sub_num} (Step.{step.id}) を作成しました。")
        # 親子リンク（ベストエフォート）
        try:
            link_sub_issue(
                parent_num=root_issue_num,
                child_id=sub_id,
                repo=repo,
                token=token,
            )
        except Exception as exc:
            console.warning(f"Sub-Issue #{sub_num} の親子リンクに失敗しました: {exc}")

    return root_issue_num


# -----------------------------------------------------------------------
# プロンプト構築
# -----------------------------------------------------------------------

def _build_step_prompt(
    step,
    params: dict,
    root_issue_num: Optional[int],
    render_template_fn,
    wf,
    additional_prompt: Optional[str] = None,
) -> str:
    """ステップのプロンプト文字列を構築する。

    テンプレートが存在する場合はそれを展開して返す。
    テンプレートが存在しない場合やレンダリングに失敗した場合は、
    「Step.{id}: タイトル」を先頭行とし、利用可能であれば
    branch / resource_group / app_id などのステップ情報を続けた
    複数行のシンプルなプロンプトを組み立てて返す。
    いずれの場合も additional_prompt が指定された場合は、
    末尾に空行を挟んで追記する。
    """
    if step.body_template_path:
        try:
            prompt = render_template_fn(
                template_path=step.body_template_path,
                root_issue_num=root_issue_num or 0,
                params=params,
                wf=wf,
            )
            if prompt:
                if additional_prompt:
                    prompt = prompt + "\n\n" + additional_prompt
                return prompt
        except Exception:
            pass

    # フォールバック: シンプルなプロンプト
    parts = [f"# Step.{step.id}: {step.title}\n"]
    if params.get("branch"):
        parts.append(f"対象ブランチ: `{params['branch']}`")
    if params.get("resource_group"):
        parts.append(f"リソースグループ: `{params['resource_group']}`")
    app_ids = params.get("app_ids", [])
    if app_ids:
        parts.append(f"APP-ID: {', '.join(f'`{aid}`' for aid in app_ids)}")
    elif params.get("app_id"):
        parts.append(f"APP-ID: `{params['app_id']}`")
    fallback = "\n".join(parts)
    if additional_prompt:
        fallback = fallback + "\n\n" + additional_prompt
    return fallback


# -----------------------------------------------------------------------
# 既存成果物検出・再利用コンテキスト
# -----------------------------------------------------------------------

def _collect_file_samples(root: str, limit: int = 10) -> list:
    """指定ディレクトリから最大 limit 件のファイルパスを収集して返す。

    大規模リポジトリでの全列挙を避けるため、limit 件見つかった時点で走査を打ち切る。
    """
    from pathlib import Path
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    files: list = []
    for path in root_path.rglob("*"):
        if path.is_file():
            files.append(str(path))
            if len(files) >= limit:
                break
    return files


def _detect_existing_artifacts(workflow_id: str, params: dict) -> dict:
    """既存の成果物を検出し、再利用可能なファイルリストを返す。"""
    existing: dict = {}

    catalog_files = {
        "app_catalog": "docs/catalog/app-catalog.md",
        "service_catalog": "docs/catalog/service-catalog.md",
        "data_model": "docs/catalog/data-model.md",
        "domain_analytics": "docs/catalog/domain-analytics.md",
        "screen_catalog": "docs/catalog/screen-catalog.md",
        "test_strategy": "docs/catalog/test-strategy.md",
        "service_catalog_matrix": "docs/catalog/service-catalog-matrix.md",
        "use_case_catalog": "docs/catalog/use-case-catalog.md",
        "batch_job_catalog": "docs/batch/batch-job-catalog.md",
        "batch_service_catalog": "docs/batch/batch-service-catalog.md",
        "batch_data_model": "docs/batch/batch-data-model.md",
        "batch_domain_analytics": "docs/batch/batch-domain-analytics.md",
    }

    for key, path in catalog_files.items():
        if os.path.exists(path):
            existing[key] = path

    # サービス詳細仕様書の検出
    service_specs = _glob.glob("docs/services/*.md")
    if service_specs:
        existing["service_specs"] = service_specs

    # 画面定義書の検出
    screen_specs = _glob.glob("docs/screen/*.md")
    if screen_specs:
        existing["screen_specs"] = screen_specs

    # テスト仕様書の検出
    test_specs = _glob.glob("docs/test-specs/*.md")
    if test_specs:
        existing["test_specs"] = test_specs

    # ソースコードの検出（上限付き早期終了）
    src_files = _collect_file_samples("src")
    if src_files:
        existing["src_files"] = src_files

    # テストコードの検出（上限付き早期終了）
    test_files = _collect_file_samples("test")
    if test_files:
        existing["test_files"] = test_files

    # knowledge/ フォルダーの検出
    knowledge_files = _glob.glob("knowledge/*.md")
    if knowledge_files:
        existing["knowledge"] = knowledge_files

    # Agent 設計書の検出
    agent_specs = _glob.glob("docs/agent/*.md")
    if agent_specs:
        existing["agent_specs"] = agent_specs

    # バッチジョブ仕様書の検出
    batch_job_specs = _glob.glob("docs/batch/jobs/*.md")
    if batch_job_specs:
        existing["batch_job_specs"] = batch_job_specs

    # ADOC (docs-generated/) の既存成果物検出
    if workflow_id == "adoc":
        doc_gen_files = [
            p.replace("\\", "/")
            for p in _glob.glob("docs-generated/**/*.md", recursive=True)
        ]
        if doc_gen_files:
            existing["doc_generated"] = doc_gen_files

    return existing


def _build_reuse_context(existing_artifacts: dict) -> str:
    """既存成果物の再利用コンテキストをプロンプトに追加する文字列を生成。"""
    if not existing_artifacts:
        return ""

    lines = [
        "\n\n## 🔄 既存成果物（再利用対象）",
        "以下の成果物が既に存在します。これらを参照・再利用してください：",
        "",
    ]

    for key, paths in existing_artifacts.items():
        if isinstance(paths, list):
            for p in paths[:10]:  # 上限10件表示
                lines.append(f"- `{p}`")
            if len(paths) > 10:
                lines.append(f"  ...他 {len(paths) - 10} ファイル")
        else:
            lines.append(f"- `{paths}`")

    lines.extend([
        "",
        "**再利用ルール:**",
        "- 既存のドキュメント/コード構造を尊重し、差分のみを更新する",
        "- 新規 APP-ID に関する追記は、既存ファイルのフォーマットに従う",
        "- Catalog ファイルは既存エントリを保持したまま、新規エントリを追加する",
        "- テスト仕様書・テストコードは既存分を維持し、新規分のみ追加する",
        "- `docs/catalog/app-catalog.md` の既存アプリケーション定義を参照し、一貫性を保つ",
    ])

    return "\n".join(lines)


# -----------------------------------------------------------------------
# メインオーケストレーション
# -----------------------------------------------------------------------

async def run_workflow(
    workflow_id: str,
    params: Optional[dict] = None,
    config: Optional[SDKConfig] = None,
) -> dict:
    """ワークフローを SDK でローカル実行する。

    --create-issues 時のフロー:
      1. 新ブランチ作成 + checkout
      2. Issue 作成（Root + Sub-Issue。Copilot アサインなし）
      3. DAG 全ステップ実行
      4. git add（無視パス除外）+ commit + push（-u オプション付き）
      5. PR 作成（Issue 番号を PR body に記載）
      6. Code Review Agent レビュー（--auto-coding-agent-review 時のみ）
      7. サマリー出力（PR のレビュー・マージはユーザーに委任）

    --create-pr のみの場合も同一ブランチ作成フローを使用。

    処理フロー:
    1. ワークフロー定義取得
    2. パラメータ収集
    3. ステップフィルタリング
    4. 新ブランチ作成（--create-issues または --create-pr 時）
    4.5. Issue 作成（--create-issues 時）
    5-7. DAGExecutor で全ステップ実行
    8. Post-DAG 後処理（git push + PR 作成）
    9. サマリー表示

    Returns:
        結果情報の dict:
          workflow_id, completed, failed, skipped, elapsed_total,
          code_review_error, pr_number, root_issue_num, working_branch, error
    """
    if config is None:
        config = SDKConfig()

    # run_id が未設定の場合、ワークフロー実行開始時に1回生成する（並列安全性）
    if not config.run_id:
        config.run_id = generate_run_id()

    console = Console(verbose=config.verbose, quiet=config.quiet, show_stream=config.show_stream,
                      verbosity=config.verbosity)
    start_total = time.time()

    # --- 1. ワークフロー定義取得 ---
    wf = get_workflow(workflow_id)
    if wf is None:
        console.error(f"ワークフロー '{workflow_id}' が見つかりません。有効なID: {_VALID_WORKFLOWS}")
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "elapsed_total": 0.0,
            "error": f"Unknown workflow: {workflow_id}",
        }

    display_name = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)
    console.header(f"Copilot SDK Orchestrator: [{wf.id.upper()}] {display_name}")

    # フェーズ構成の動的算出
    _phases: List[str] = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
    if config.create_issues or config.create_pr:
        _phases.append("ブランチ作成")
    if config.create_issues:
        _phases.append("Issue 作成")
    _phases.append("実行計画 → DAG 実行")
    if config.create_issues or config.create_pr:
        _phases.append("後処理 (git push + PR)")
    _phases.append("サマリー")
    _total_phases = len(_phases)
    _phase_idx = 0

    def _next_phase() -> int:
        nonlocal _phase_idx
        _phase_idx += 1
        return _phase_idx

    # Phase 1: ワークフロー定義取得 ✓ (既に取得済み)
    p = _next_phase()
    console.phase_end(p, _total_phases, "ワークフロー定義取得", time.time() - start_total)

    # --- 2. パラメータ収集 ---
    p = _next_phase()
    phase_start = time.time()
    console.phase_start(p, _total_phases, "パラメータ収集")

    if params is None:
        params = {}

    # dry_run 時は常に非対話モード（インタラクティブプロンプト不要）
    # CLI 引数が揃っていれば非対話モード、そうでなければ対話モード
    if config.dry_run or _is_non_interactive(wf, params):
        effective_params = _collect_params_non_interactive(wf, params)
    else:
        try:
            effective_params = cli_collect_params(
                wf,
                will_create_pr=(config.create_issues or config.create_pr),
            )
        except (KeyboardInterrupt, EOFError):
            console.warning("入力がキャンセルされました。")
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "elapsed_total": time.time() - start_total,
            }
        # CLI 引数の値で上書き（明示的に指定された値を優先）
        for k, v in params.items():
            if v is not None and v != "" and v != []:
                effective_params[k] = v
        # 'steps' キー（CLI側）→ 'selected_steps'（orchestrate.py側）の正規化
        if "steps" in params and params["steps"]:
            effective_params["selected_steps"] = params["steps"]

    # dry_run を params に反映
    if config.dry_run:
        effective_params["dry_run"] = True

    console.phase_end(p, _total_phases, "パラメータ収集", time.time() - phase_start)

    # --- 3. ステップフィルタリング ---
    p = _next_phase()
    phase_start = time.time()
    console.phase_start(p, _total_phases, "ステップフィルタリング")

    selected_step_ids: List[str] = effective_params.get("selected_steps") or []
    active_steps: Set[str] = resolve_selected_steps(wf, selected_step_ids)

    console.event(f"実行対象ステップ数: {len(active_steps)}")
    console.phase_end(p, _total_phases, "ステップフィルタリング", time.time() - phase_start)

    # --- dry_run: 実行計画表示のみ ---
    if config.dry_run:
        _print_dry_run_plan(wf, active_steps, config, console)
        elapsed = time.time() - start_total
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": list(active_steps),
            "elapsed_total": elapsed,
            "dry_run": True,
        }

    # --- 4. 新ブランチ作成（--create-issues または --create-pr 時） ---
    working_branch: Optional[str] = None
    if config.create_issues or config.create_pr:
        p = _next_phase()
        phase_start = time.time()
        console.phase_start(p, _total_phases, "ブランチ作成")

        prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
        working_branch = f"copilot-sdk/{prefix.lower()}-{uuid.uuid4().hex[:8]}"
        if not _git_checkout_new_branch(working_branch, config.base_branch, console):
            elapsed = time.time() - start_total
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "elapsed_total": elapsed,
                "error": f"ブランチ '{working_branch}' の作成に失敗しました。",
            }
        effective_params["branch"] = working_branch
        console.phase_end(p, _total_phases, "ブランチ作成", time.time() - phase_start)

    # --- 4.5. Issue 作成（--create-issues 時のみ） ---
    if config.create_issues:
        p = _next_phase()
        phase_start_issue = time.time()
        console.phase_start(p, _total_phases, "Issue 作成")

    root_issue_num = _create_issues_if_needed(
        wf=wf,
        params=effective_params,
        active_steps=active_steps,
        config=config,
        console=console,
        render_template_fn=render_template,
        build_root_issue_body_fn=build_root_issue_body,
    )

    if config.create_issues:
        console.phase_end(p, _total_phases, "Issue 作成", time.time() - phase_start_issue)

    # --- 5. StepRunner 準備 + DAG 実行 ---
    p = _next_phase()
    phase_start_dag = time.time()
    console.phase_start(p, _total_phases, "実行計画 → DAG 実行")

    # --- 成果物ディレクトリの事前作成 ---
    _REQUIRED_DIRS = [
        "docs/catalog",
        "docs/batch",
        "docs/batch/jobs",
        "docs/services",
        "docs/screen",
        "docs/test-specs",
        "docs/agent",
        "docs/azure",
        "docs/usecase",
        "docs-generated",
        "docs-generated/files",
        "docs-generated/components",
        "docs-generated/architecture",
        "docs-generated/guides",
    ]
    for _dir in _REQUIRED_DIRS:
        os.makedirs(_dir, exist_ok=True)
    console.event(f"成果物ディレクトリを確認/作成しました（{len(_REQUIRED_DIRS)} 件）")

    runner = StepRunner(config=config, console=console)

    # 既存成果物を検出し、2度目実行時の再利用コンテキストを additional_prompt に追記
    existing_artifacts = _detect_existing_artifacts(workflow_id, effective_params)
    reuse_context = _build_reuse_context(existing_artifacts)
    if reuse_context:
        artifact_count = sum(
            len(v) if isinstance(v, list) else 1
            for v in existing_artifacts.values()
        )
        console.event(f"既存成果物を検出しました（{artifact_count} 件）。再利用モードで実行します。")
        effective_additional_prompt = (
            (config.additional_prompt or "") + reuse_context
        ).strip() or None
    else:
        effective_additional_prompt = config.additional_prompt

    # ステップ → プロンプト の事前構築
    step_prompts: Dict[str, str] = {}
    for step in wf.steps:
        if step.is_container or step.id not in active_steps:
            continue
        step_prompts[step.id] = _build_step_prompt(
            step=step,
            params=effective_params,
            root_issue_num=root_issue_num,
            render_template_fn=render_template,
            wf=wf,
            additional_prompt=effective_additional_prompt,
        )
        step_prompt = step_prompts[step.id]

        # Work IQ: KM / AQOD ワークフロー用のコンテキスト事前注入
        if config.workiq_enabled and workflow_id in ("akm", "aqod"):
            try:
                from .workiq import (
                    is_workiq_available, get_workiq_prompt_template,
                )
            except ImportError:
                from workiq import (  # type: ignore[no-redef]
                    is_workiq_available, get_workiq_prompt_template,
                )

            if is_workiq_available():
                _wiq_mode = "km" if workflow_id == "akm" else "review"
                _wiq_template = get_workiq_prompt_template(
                    _wiq_mode,
                    config.workiq_prompt_km if _wiq_mode == "km" else config.workiq_prompt_review,
                )
                _topic_raw = step_prompt[:500]
                _last_period = max(_topic_raw.rfind("。"), _topic_raw.rfind("\n"))
                _topic_summary = _topic_raw[:_last_period + 1] if _last_period > 100 else _topic_raw

                _wiq_query = _wiq_template.format(target_content=_topic_summary)

                _workiq_instruction = (
                    "まず最初に、以下の Work IQ 問い合わせを実行してください。\n"
                    "結果をこのタスクの参考情報として使用し、関連情報がある場合は"
                    "「理由」欄に情報ソースとともに記載してください。\n\n"
                    f"--- Work IQ 問い合わせ ---\n{_wiq_query}\n--- Work IQ 問い合わせ終了 ---\n\n"
                    "上記の問い合わせ完了後、以下のメインタスクを実行してください:\n\n"
                )
                step_prompt = _workiq_instruction + step_prompt
                step_prompts[step.id] = step_prompt

    # --- 6-7. DAGExecutor 実行 ---
    async def run_step_fn(
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
    ) -> bool:
        return await runner.run_step(
            step_id=step_id,
            title=title,
            prompt=prompt,
            custom_agent=custom_agent,
        )

    executor = DAGExecutor(
        workflow=wf,
        run_step_fn=run_step_fn,
        active_step_ids=active_steps,
        max_parallel=config.max_parallel,
        console=console,
        step_prompts=step_prompts,
    )

    # 実行計画を事前表示
    waves = executor.compute_waves()
    if waves:
        console.execution_plan(waves, len(active_steps), config.max_parallel)

    results = await executor.execute()
    console.phase_end(p, _total_phases, "実行計画 → DAG 実行", time.time() - phase_start_dag)

    # --- 8. Post-DAG: 統一後処理 ---
    code_review_error: Optional[str] = None
    pr_number: Optional[int] = None
    pr_error: Optional[str] = None

    if working_branch:
        p = _next_phase()
        phase_start_post = time.time()
        console.phase_start(p, _total_phases, "後処理 (git push + PR)")

        prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
        display_name_for_commit = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)
        pushed = _git_add_commit_push(
            branch=working_branch,
            commit_message=f"[{prefix}] {display_name_for_commit} — SDK ローカル実行の成果物",
            console=console,
            ignore_paths=config.ignore_paths,
        )
        if pushed:
            pr_number = _create_pr_if_needed(
                wf=wf,
                head_branch=working_branch,
                base_branch=config.base_branch,
                config=config,
                console=console,
                root_issue_num=root_issue_num,
            )
            if pr_number is None:
                pr_error = "PR 作成に失敗しました。ログを確認してください。"
            elif config.auto_coding_agent_review:
                code_review_error = await _request_code_review(
                    pr_number=pr_number,
                    config=config,
                    console=console,
                )
        else:
            console.warning("コミット対象の変更がないため PR 作成をスキップしました。")
        console.phase_end(p, _total_phases, "後処理 (git push + PR)", time.time() - phase_start_post)

    # --- 9. サマリー ---
    p = _next_phase()
    console.phase_start(p, _total_phases, "サマリー")

    elapsed_total = time.time() - start_total
    completed_ids = list(executor.completed)
    failed_ids = list(executor.failed)
    skipped_ids = list(executor.skipped)

    console.summary({
        "success": len(completed_ids),
        "failed": len(failed_ids),
        "skipped": len(skipped_ids),
        "total_elapsed": elapsed_total,
    })

    if root_issue_num:
        console.event(f"Root Issue #{root_issue_num} が作成されています。")
    if working_branch:
        console.event(f"作業ブランチ: {working_branch}")
    if config.ignore_paths:
        console.event(f"除外パス: {', '.join(config.ignore_paths)}")
    if pr_number:
        console.event(f"PR #{pr_number} が作成されています。")
        console.event("PR のレビューとマージはご自身で実施してください。")

    return {
        "workflow_id": workflow_id,
        "completed": completed_ids,
        "failed": failed_ids,
        "skipped": skipped_ids,
        "elapsed_total": elapsed_total,
        "code_review_error": code_review_error,
        "pr_number": pr_number,
        "root_issue_num": root_issue_num,
        "working_branch": working_branch,
        "error": pr_error,
    }


# -----------------------------------------------------------------------
# ドライラン計画表示
# -----------------------------------------------------------------------

def _print_dry_run_plan(wf, active_steps: Set[str], config: SDKConfig, console: Console) -> None:
    """ドライラン時に DAG の波（Wave）を表示する。"""
    console.event(f"[DRY RUN] orchestrate: workflow={wf.id}")
    console.event("[DRY RUN] DAG Traversal:")

    completed: Set[str] = set()
    skipped: Set[str] = set()
    wave = 1

    while True:
        next_steps = wf.get_next_steps(
            completed_step_ids=list(completed),
            skipped_step_ids=list(skipped),
        )

        # active でないステップを自動スキップ
        for s in next_steps:
            if s.id not in active_steps and s.id not in skipped and s.id not in completed:
                skipped.add(s.id)

        executable = [
            s for s in next_steps
            if s.id in active_steps
            and s.id not in completed
            and s.id not in skipped
        ]

        if not executable and not [s for s in next_steps if s.id not in completed and s.id not in skipped]:
            break
        if not executable:
            # スキップのみで進む
            for s in next_steps:
                if s.id not in completed:
                    skipped.add(s.id)
            continue

        wave_label = " ‖ ".join(f"Step.{s.id}" for s in executable)
        depends = " AND ".join(executable[0].depends_on) if executable[0].depends_on else "root"
        console.event(f"[DRY RUN]   Wave {wave}: {wave_label} (depends_on: {depends})")

        for s in executable:
            console.event(f"[DRY RUN] Would execute: Step.{s.id} - {s.title}")
            completed.add(s.id)

        wave += 1

    if config.create_issues:
        console.event("[DRY RUN] --- Issue 作成 + ローカル実行モード ---")
        console.event(f"[DRY RUN]   1. '{config.base_branch}' から新規ブランチを作成")
        console.event("[DRY RUN]   2. Root Issue + Sub-Issue を作成（Copilot アサインなし）")
        console.event("[DRY RUN]   3. DAG 全ステップ実行")
        console.event("[DRY RUN]   4. 変更を commit + push（除外パス適用）")
        if config.ignore_paths:
            console.event(f"[DRY RUN]      除外パス: {', '.join(config.ignore_paths)}")
        console.event("[DRY RUN]   5. PR の作成（Issue 番号を PR body に記載）")
        if config.auto_coding_agent_review:
            console.event("[DRY RUN]   6. Code Review Agent (ローカル CLI SDK) でレビュー実行")
            console.event(f"[DRY RUN]      git diff {config.review_base_ref} で差分取得")
        console.event("[DRY RUN]   ⚠️ PR のレビュー・マージはユーザーが実施してください")
        console.event("[DRY RUN] ⚠️ 前提: PR 作成には GH_TOKEN と --repo が必要です（Code Review Agent レビュー自体はローカル実行のみで完結します）")
    elif config.create_pr:
        console.event("[DRY RUN] --- ローカル実行 + PR モード ---")
        console.event("[DRY RUN] 全ステップ完了後に以下を実行:")
        console.event(f"[DRY RUN]   1. '{config.base_branch}' から新規ブランチを作成")
        console.event("[DRY RUN]   2. DAG 全ステップ実行")
        console.event("[DRY RUN]   3. 変更を commit + push")
        console.event("[DRY RUN]   4. PR の作成")
        if config.auto_coding_agent_review:
            console.event("[DRY RUN]   5. Code Review Agent (ローカル CLI SDK) でレビュー実行")
            console.event(f"[DRY RUN]      git diff {config.review_base_ref} で差分取得")
            console.event(f"[DRY RUN]   レビュータイムアウト: {config.review_timeout_seconds}s")
            if config.auto_coding_agent_review_auto_approval:
                console.event("[DRY RUN]   6. 修正プランの自動承認 + 同一セッション内でローカル修正実行")
            else:
                console.event("[DRY RUN]   6. 修正プランの確認プロンプト（対話）")
        console.event("[DRY RUN] ⚠️ 前提: PR 作成には GH_TOKEN と --repo が必要です（Code Review Agent レビュー自体はローカル実行のみで完結します）")


# -----------------------------------------------------------------------
# Code Review Agent サポート
# -----------------------------------------------------------------------


def _get_git_diff(base_ref: str, console: Console) -> str:
    """git diff base_ref との差分テキストを返す。差分なし/エラーは空文字を返す。

    Args:
        base_ref: git diff の基点 (例: "HEAD~1", "main", "origin/main")
        console: コンソール出力用

    Returns:
        差分テキスト（空文字は差分なし or エラー）
    """
    try:
        result = subprocess.run(
            ["git", "diff", base_ref],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.warning(f"git diff {base_ref} に失敗: {result.stderr.strip()}")
            return ""
        diff = result.stdout.strip()
        if len(diff) > _MAX_DIFF_CHARS:
            console.warning(
                f"差分が {len(diff)} 文字を超えるため {_MAX_DIFF_CHARS} 文字にトリミングします。"
            )
            diff = diff[:_MAX_DIFF_CHARS] + "\n... (truncated)"
        return diff
    except subprocess.TimeoutExpired:
        console.warning("git diff がタイムアウトしました。")
        return ""
    except FileNotFoundError:
        console.warning("git コマンドが見つかりません。")
        return ""


async def _request_code_review(
    pr_number: Optional[int],
    config: SDKConfig,
    console: Console,
) -> Optional[str]:
    """Copilot CLI SDK セッションでローカルに Code Review を実行する。

    git diff でレビュー対象差分を取得し、Copilot CLI セッションに
    /review コマンドとして送信する。GitHub API / PR は使用しない。

    処理フロー:
    1. git diff {config.review_base_ref} で差分テキストを取得
    2. Copilot CLI SDK インポート確認
    3. CopilotClient セッション開始
    4. /review プロンプト送信（差分埋め込み）
    5. PASS/FAIL 判定 → FAIL 時は修正実行

    Args:
        pr_number: 参照用のみ（API 呼び出しには使わない）。省略可。
        config: SDKConfig
        console: コンソール出力用

    Returns:
        None = 成功, str = エラーメッセージ
    """
    # 1. git diff で差分を取得
    diff = _get_git_diff(config.review_base_ref, console)
    if not diff:
        console.warning("レビュー対象の差分がありません。Code Review をスキップします。")
        return None

    # 2. Copilot CLI SDK インポート確認（runner.py と同じパターン）
    try:
        from copilot import CopilotClient  # type: ignore[import]
        from copilot import SubprocessConfig, ExternalServerConfig  # type: ignore[import]
        from copilot.session import PermissionHandler  # type: ignore[import]
    except ImportError:
        return (
            "GitHub Copilot SDK がインストールされていません。\n"
            "  pip install github-copilot-sdk  # または適切なパッケージ名で再試行してください。"
        )

    # 3. CopilotClient セッション開始
    # verbosity >= 3 (verbose) かつデフォルトの log_level ("error") の場合のみ debug に昇格。
    # ユーザーが明示的に log_level を指定している場合はそれを尊重する。
    _effective_log_level = (
        "debug"
        if config.verbosity >= 3 and config.log_level == "error"
        else config.log_level
    )
    if config.cli_url:
        sdk_config = ExternalServerConfig(url=config.cli_url)
    else:
        sdk_config = SubprocessConfig(
            cli_path=config.cli_path,
            github_token=config.resolve_token() or None,
            log_level=_effective_log_level,
            cli_args=config.cli_args,
        )
    client = CopilotClient(config=sdk_config)
    await client.start()

    session = None
    try:
        session = await client.create_session(
            model=config.get_review_model(),
            on_permission_request=PermissionHandler.approve_all,
            streaming=True,
        )
        if config.get_review_model() != config.model:
            console.event(f"Code Review Agent モデル: {config.get_review_model()}")

        # session.log イベントを Console に転送（CLI ログを表示するため）
        def _review_session_event(event: Any) -> None:
            etype = getattr(getattr(event, "type", None), "value", "") or ""
            data = getattr(event, "data", None)
            if etype == "session.log":
                level = getattr(data, "level", None) or "info"
                message = getattr(data, "message", None) or ""
                if message:
                    console.cli_log("review", f"[{level}] {message}")

        session.on(_review_session_event)

        # 4. /review プロンプト送信
        review_prompt = CODE_REVIEW_CLI_PROMPT.format(diff=diff)
        console.event("Copilot CLI Code Review Agent を実行中...")
        review_response = await session.send_and_wait(
            review_prompt, timeout=config.review_timeout_seconds
        )
        review_content = _extract_text(review_response)

        console.event("=== Code Review Agent レビュー結果 ===")
        print(f"{timestamp_prefix()} {review_content}")

        # 5. FAIL 判定 → 修正実行
        if not _is_review_fail(review_content):
            console.event("✅ Code Review: PASS（Critical 指摘なし）")
        else:
            approve = False
            if config.auto_coding_agent_review_auto_approval:
                console.event(
                    "auto_coding_agent_review_auto_approval=True のため、"
                    "全ての指摘を自動修正します。"
                )
                approve = True
            elif config.unattended:
                console.warning(
                    "全自動モードのため Code Review の修正確認をスキップします。"
                )
            else:
                console.warning(
                    "Code Review Agent の指摘があります。修正を実行しますか？ [y/N]: "
                )
                if not sys.stdin.isatty():
                    console.warning("stdin が非対話モードのため、修正をスキップします。")
                else:
                    def _read_answer() -> str:
                        try:
                            return sys.stdin.readline().rstrip("\n").strip().lower()
                        except EOFError:
                            return ""

                    loop = asyncio.get_running_loop()
                    try:
                        answer = await asyncio.wait_for(
                            loop.run_in_executor(None, _read_answer),
                            timeout=60.0,
                        )
                    except asyncio.TimeoutError:
                        console.warning("入力タイムアウト (60s)。修正をスキップします。")
                        answer = ""
                    if answer in ("y", "yes"):
                        approve = True

            if approve:
                fix_prompt = CODE_REVIEW_AGENT_FIX_PROMPT.format(
                    review_comments=review_content
                )
                # 6. 同一セッション内で修正を実行
                await session.send_and_wait(
                    fix_prompt, timeout=config.review_timeout_seconds
                )
                console.event("✅ Code Review Agent による修正が完了しました。")
            else:
                console.event("修正をスキップしました。")

    except Exception as exc:
        error_msg = f"Code Review Agent の実行中にエラーが発生しました: {exc}"
        console.error(error_msg)
        return error_msg
    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception as cleanup_exc:
                console.warning(f"[cleanup] session.disconnect() failed: {cleanup_exc}")
        try:
            await client.stop()
        except Exception as cleanup_exc:
            console.warning(f"[cleanup] client.stop() failed: {cleanup_exc}")

    return None


# -----------------------------------------------------------------------
# PR 作成
# -----------------------------------------------------------------------

def _create_pr_if_needed(
    wf,
    head_branch: str,
    base_branch: str,
    config: SDKConfig,
    console: Console,
    root_issue_num: Optional[int] = None,
) -> Optional[int]:
    """PR を作成する。

    Returns:
        PR 番号 (int) または None（作成失敗時）
    """
    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning("GH_TOKEN または REPO が未設定のため PR 作成をスキップします。")
        return None

    if head_branch == base_branch:
        console.error(
            f"head ブランチ '{head_branch}' と base ブランチ '{base_branch}' が同一です。"
            " PR を作成できません。"
        )
        return None

    prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
    display_name = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)

    body_lines = [
        f"SDK オーケストレーター ({wf.id}) による自動実行の PR。",
        "",
        f"ブランチ: `{head_branch}` → `{base_branch}`",
    ]
    if root_issue_num:
        body_lines.append("")
        body_lines.append(f"Closes #{root_issue_num}")

    try:
        pr_num = create_pull_request(
            title=f"[{prefix}] {display_name}",
            body="\n".join(body_lines),
            head=head_branch,
            base=base_branch,
            repo=repo,
            token=token,
        )
        console.event(f"PR #{pr_num} を作成しました。")
        return pr_num
    except GitHubAPIError as exc:
        console.error(f"PR 作成中にエラーが発生しました: {exc}")
        return None
