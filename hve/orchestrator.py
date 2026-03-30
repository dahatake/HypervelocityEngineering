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
    from .config import SDKConfig
    from .console import Console
    from .prompts import CODE_REVIEW_AGENT_FIX_PROMPT
    from .runner import StepRunner
    from .dag_executor import DAGExecutor
except ImportError:
    from config import SDKConfig  # type: ignore[no-redef]
    from console import Console  # type: ignore[no-redef]
    from prompts import CODE_REVIEW_AGENT_FIX_PROMPT  # type: ignore[no-redef]
    from runner import StepRunner  # type: ignore[no-redef]
    from dag_executor import DAGExecutor  # type: ignore[no-redef]

# -----------------------------------------------------------------------
# hve 内部モジュール（旧 .github/cli/ から移植済み）
# -----------------------------------------------------------------------
from hve.workflow_registry import get_workflow, WorkflowDef  # noqa: F401
from hve.template_engine import (
    render_template,
    resolve_selected_steps,
    build_root_issue_body,
    collect_params as cli_collect_params,
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

_VALID_WORKFLOWS = ["aas", "aad", "asdw", "abd", "abdv", "aid"]

_WORKFLOW_DISPLAY_NAMES: Dict[str, str] = {
    "aas": "Auto App Selection",
    "aad": "Auto App Design",
    "asdw": "Auto App Dev Microservice Azure",
    "abd": "Auto Batch Design",
    "abdv": "Auto Batch Dev",
    "aid": "Auto IoT Design",
}

_WORKFLOW_PREFIX: Dict[str, str] = {
    "aas": "AAS",
    "aad": "AAD",
    "asdw": "ASDW",
    "abd": "ABD",
    "abdv": "ABDV",
    "aid": "AID",
}

_TEMPLATES_BASE = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "templates"

# Code Review Agent の GitHub ユーザー名候補
_COPILOT_USERNAMES = (
    "copilot",
    "github-copilot[bot]",
    "copilot[bot]",
    "copilot-swe-agent[bot]",
    "copilot-pull-request-reviewer[bot]",
)


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
        "additional_comment": "",
    }

    # ワークフロー固有パラメータ
    if args.get("app_id"):
        params["app_id"] = args["app_id"]
    if args.get("resource_group"):
        params["resource_group"] = args["resource_group"]
    if args.get("usecase_id"):
        params["usecase_id"] = args["usecase_id"]
    if args.get("batch_job_id"):
        params["batch_job_id"] = args["batch_job_id"]

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
        except Exception:
            pass

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
    if params.get("app_id"):
        parts.append(f"APP-ID: `{params['app_id']}`")
    fallback = "\n".join(parts)
    if additional_prompt:
        fallback = fallback + "\n\n" + additional_prompt
    return fallback


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

    console = Console(verbose=config.verbose, quiet=config.quiet, show_stream=config.show_stream)
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

    # --- 2. パラメータ収集 ---
    if params is None:
        params = {}

    # dry_run 時は常に非対話モード（インタラクティブプロンプト不要）
    # CLI 引数が揃っていれば非対話モード、そうでなければ対話モード
    if config.dry_run or _is_non_interactive(wf, params):
        effective_params = _collect_params_non_interactive(wf, params)
    else:
        try:
            effective_params = cli_collect_params(wf)
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
        if "steps" in params and params["steps"] and "selected_steps" not in effective_params:
            effective_params["selected_steps"] = params["steps"]
        elif "steps" in params and params["steps"]:
            effective_params["selected_steps"] = params["steps"]

    # dry_run を params に反映
    if config.dry_run:
        effective_params["dry_run"] = True

    # --- 3. ステップフィルタリング ---
    selected_step_ids: List[str] = effective_params.get("selected_steps") or []
    active_steps: Set[str] = resolve_selected_steps(wf, selected_step_ids)

    console.event(f"実行対象ステップ数: {len(active_steps)}")

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

    # --- 4.5. Issue 作成（--create-issues 時のみ） ---
    root_issue_num = _create_issues_if_needed(
        wf=wf,
        params=effective_params,
        active_steps=active_steps,
        config=config,
        console=console,
        render_template_fn=render_template,
        build_root_issue_body_fn=build_root_issue_body,
    )

    # --- 5. StepRunner 準備 ---
    runner = StepRunner(config=config, console=console)

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
            additional_prompt=config.additional_prompt,
        )
        # ステップオブジェクトにプロンプトを注入（DAGExecutor が参照できるよう）
        step._prompt = step_prompts[step.id]

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
    )

    results = await executor.execute()

    # --- 8. Post-DAG: 統一後処理 ---
    code_review_error: Optional[str] = None
    pr_number: Optional[int] = None
    pr_error: Optional[str] = None

    if working_branch:
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

    # --- 9. サマリー ---
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
            console.event("[DRY RUN]   6. Code Review Agent へのレビュー依頼")
        console.event("[DRY RUN]   ⚠️ PR のレビュー・マージはユーザーが実施してください")
        console.event("[DRY RUN] ⚠️ 前提: GH_TOKEN と --repo が必要です")
    elif config.create_pr:
        console.event("[DRY RUN] --- ローカル実行 + PR モード ---")
        console.event("[DRY RUN] 全ステップ完了後に以下を実行:")
        console.event(f"[DRY RUN]   1. '{config.base_branch}' から新規ブランチを作成")
        console.event("[DRY RUN]   2. DAG 全ステップ実行")
        console.event("[DRY RUN]   3. 変更を commit + push")
        console.event("[DRY RUN]   4. PR の作成")
        if config.auto_coding_agent_review:
            console.event("[DRY RUN]   5. Code Review Agent へのレビュー依頼")
            console.event(f"[DRY RUN]   レビュータイムアウト: {config.review_timeout_seconds}s")
            if config.auto_coding_agent_review_auto_approval:
                console.event("[DRY RUN]   6. 修正プランの自動承認 + PR コメント投稿")
            else:
                console.event("[DRY RUN]   6. 修正プランの確認プロンプト（対話）")
        console.event("[DRY RUN] ⚠️ 前提: GH_TOKEN と --repo が必要です")


# -----------------------------------------------------------------------
# Code Review Agent サポート
# -----------------------------------------------------------------------


async def _request_code_review(
    pr_number: int,
    config: SDKConfig,
    console: Console,
) -> Optional[str]:
    """PR に Code Review Agent のレビューを依頼し、結果を待機する。

    処理フロー:
    1. Copilot をレビュアーとしてリクエスト
    2. レビュー完了をポーリング（COMMENTED 状態を待つ）
    3. レビュー結果を表示
    4. 修正処理（auto_approval または ユーザー確認）
       承認された場合、修正プロンプトを PR コメントとして投稿する

    Returns:
        None = 成功, str = エラーメッセージ
    """
    token = config.resolve_token()
    repo = config.repo

    if not token or not repo:
        return "GH_TOKEN または REPO が未設定のため Code Review Agent 処理をスキップします。"

    _GH_API = "https://api.github.com"

    # --- 1. Code Review Agent をレビュアーとしてリクエスト ---
    reviewer_candidates = ["copilot-pull-request-reviewer[bot]", "copilot"]
    request_succeeded = False
    last_exc: Optional[Exception] = None
    for reviewer in reviewer_candidates:
        try:
            api_call(
                "POST",
                f"{_GH_API}/repos/{repo}/pulls/{pr_number}/requested_reviewers",
                data={"reviewers": [reviewer]},
                token=token,
            )
            console.event(f"Code Review Agent ({reviewer}) にレビューを依頼しました。")
            request_succeeded = True
            break
        except Exception as exc:
            last_exc = exc
            console.event(f"レビュアー '{reviewer}' でのリクエストに失敗: {exc}")

    if not request_succeeded:
        error_detail = f": {last_exc}" if last_exc else ""
        console.error(
            f"Code Review Agent へのレビュー依頼に失敗しました{error_detail}\n"
            "リポジトリで Copilot Code Review が有効になっていることを確認してください。"
        )
        return f"Code Review Agent へのレビュー依頼に失敗しました{error_detail}"

    # --- 2. レビュー完了をポーリング ---
    console.event("Code Review Agent のレビュー完了を待機中...")
    poll_interval = 10
    timeout = config.review_timeout_seconds
    start_poll = time.time()
    review_id: Optional[int] = None

    while True:
        elapsed = time.time() - start_poll
        if elapsed > timeout:
            return f"タイムアウト ({timeout}s) になりました。レビューがまだ完了していません。"

        await asyncio.sleep(poll_interval)

        try:
            reviews = api_call(
                "GET",
                f"{_GH_API}/repos/{repo}/pulls/{pr_number}/reviews",
                token=token,
                max_retries=1,
            )
            copilot_reviews = [
                r for r in reviews  # type: ignore[union-attr]
                if r.get("state") == "COMMENTED"
                and r.get("user", {}).get("login", "").lower() in _COPILOT_USERNAMES
            ]
            if copilot_reviews:
                review_id = copilot_reviews[-1]["id"]
                console.event("Code Review Agent のレビューが完了しました。")
                break

        except Exception as exc:
            console.warning(f"レビューポーリング中にエラーが発生しました（次のサイクルで再試行）: {exc}")

    # --- 3. レビュー結果を取得・表示 ---
    review_body = ""
    try:
        review_detail = api_call(
            "GET",
            f"{_GH_API}/repos/{repo}/pulls/{pr_number}/reviews/{review_id}",
            token=token,
        )
        review_body = review_detail.get("body", "")  # type: ignore[union-attr]
    except Exception as exc:
        console.warning(f"レビュー本体の取得中にエラーが発生しました: {exc}")

    review_comments_text = ""
    try:
        comments = api_call(
            "GET",
            f"{_GH_API}/repos/{repo}/pulls/{pr_number}/comments",
            token=token,
        )
        if isinstance(comments, list) and comments:
            lines = []
            for c in comments:
                path = c.get("path", "")
                body = c.get("body", "")
                lines.append(f"- `{path}`: {body}")
            review_comments_text = "\n".join(lines)
    except Exception as exc:
        console.warning(f"レビューコメントの取得中にエラーが発生しました: {exc}")

    console.event("=== Code Review Agent レビュー結果 ===")
    if review_body:
        print(review_body)
    if review_comments_text:
        console.event("--- インラインコメント ---")
        print(review_comments_text)

    # --- 4. 修正処理 ---
    combined_comments = "\n".join(filter(None, [review_body, review_comments_text]))

    if config.auto_coding_agent_review_auto_approval:
        console.event(
            "auto_coding_agent_review_auto_approval=True のため、"
            "全ての修正プランを自動承認します。"
        )
    else:
        console.warning(
            "Code Review Agent のレビュー結果を確認しました。\n"
            "修正プロンプトを PR コメントとして投稿しますか？ [y/N]: "
        )
        if not sys.stdin.isatty():
            console.warning("stdin が非対話モードのため、修正をスキップします。")
            console.event("修正をスキップしました。")
            return None

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
        if answer not in ("y", "yes"):
            console.event("修正をスキップしました。")
            return None

    fix_prompt = CODE_REVIEW_AGENT_FIX_PROMPT.format(review_comments=combined_comments)
    try:
        post_comment(pr_number, fix_prompt, repo=repo, token=token)
        console.event(f"修正プロンプトを PR #{pr_number} にコメントとして投稿しました。")
        console.warning(
            "⚠️ 修正プロンプトは PR コメントとして投稿されました。\n"
            "   修正を自動実行するには、GitHub Copilot Coding Agent が\n"
            "   この PR に割り当てられている必要があります。"
        )
    except Exception as exc:
        console.warning(f"修正プロンプトの投稿中にエラーが発生しました: {exc}")
        console.event("修正プロンプト（PR コメント投稿失敗のためコンソールに出力）:")
        print(fix_prompt)

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
        body_lines.append(f"Related Issue: #{root_issue_num}")

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
    except Exception as exc:
        console.error(f"PR 作成中にエラーが発生しました: {exc}")
        return None
