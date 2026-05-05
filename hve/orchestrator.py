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
import functools
import glob as _glob
import json
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
    from .config import MODEL_AUTO_VALUE, SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS
    from .console import Console, timestamp_prefix
    from .prompts import CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT, AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT
    from .runner import StepRunner, _is_review_fail, _extract_text
    from .dag_executor import DAGExecutor
    from .dag_planner import build_dag_plan
except ImportError:
    from config import MODEL_AUTO_VALUE, SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompts import CODE_REVIEW_AGENT_FIX_PROMPT, CODE_REVIEW_CLI_PROMPT, AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT  # type: ignore[no-redef]
    from runner import StepRunner, _is_review_fail, _extract_text  # type: ignore[no-redef]
    from dag_executor import DAGExecutor  # type: ignore[no-redef]
    from dag_planner import build_dag_plan  # type: ignore[no-redef]

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
    add_labels,
    api_call,
    create_issue,
    link_sub_issue,
    post_comment,
    create_pull_request,
)
from hve.app_arch_filter import resolve_app_arch_scope


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
    # app_ids/app_id は AAD-WEB・ASDW-WEB・ABD・ABDV で使用。
    # 未指定時は app-arch filter で推薦アーキテクチャに合致する APP-ID が自動選択される。
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
) -> tuple[Optional[int], Dict[str, int]]:
    """create_issues=True の場合のみ Root Issue + Sub-Issue を作成する。

    Returns:
        (root_issue_num, step_issue_map)
    """
    if not config.create_issues:
        return None, {}

    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning("create_issues=True ですが GH_TOKEN または REPO が未設定のため Issue 作成をスキップします。")
        return None, {}

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

    step_issue_map: Dict[str, int] = {}

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
            execution_mode="github",
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
        step_issue_map[step.id] = sub_num
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

    return root_issue_num, step_issue_map


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
    execution_mode: str = "local",
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
                execution_mode=execution_mode,
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


# -----------------------------------------------------------------------
# 前提成果物チェック（Phase 8）
# -----------------------------------------------------------------------

# artifact key → 期待ファイルパス / glob パターン（メッセージ表示用）
# _detect_existing_artifacts() の検索パスと同期して維持する。
_ARTIFACT_KEY_TO_EXPECTED_PATH: Dict[str, str] = {
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
    "service_specs": "docs/services/*.md",
    "screen_specs": "docs/screen/*.md",
    "test_specs": "docs/test-specs/*.md",
    "src_files": "src/**/*",
    "test_files": "test/**/*",
    "knowledge": "knowledge/*.md",
    "agent_specs": "docs/agent/*.md",
    "batch_job_specs": "docs/batch/jobs/*.md",
    "doc_generated": "docs-generated/**/*.md",
}

# artifact key → 生成ワークフロー（確認済みのもののみ記載）
# workflow_registry.py の FULL_PIPELINE 定義および各ワークフローの出力から確認。
# 値の意味:
#   "<workflow_id>"  — そのワークフローが生成する成果物
#   "user_provided"  — ワークフローでは生成されない。ユーザーが事前に手動で用意する成果物
#   None             — 生成ワークフロー未確認（ユーザー提供またはワークフロー生成の可能性あり）
_ARTIFACT_KEY_TO_GENERATING_WORKFLOW: Dict[str, Optional[str]] = {
    "app_catalog": "aas",
    "service_catalog": "aas",
    "data_model": "aas",
    "domain_analytics": "aas",
    "screen_catalog": "aad-web",
    "test_strategy": "aas",
    "service_catalog_matrix": "aas",
    "use_case_catalog": "user_provided",  # ユーザーが手動で作成するユースケースカタログ
    "batch_job_catalog": "abd",
    "batch_service_catalog": "abd",
    "batch_data_model": "abd",
    "batch_domain_analytics": "abd",
    "service_specs": "aad-web",
    "screen_specs": "aad-web",
    "test_specs": "aad-web",        # aad-web Step 2.3 / asdw-web 内でも生成されるが確定できない
    "src_files": None,              # 要確認: ユーザーコードまたは asdw-web / abdv の出力
    "test_files": None,             # 要確認: ユーザーコードまたは asdw-web / abdv の出力
    "knowledge": "akm",
    "agent_specs": "aag",
    "batch_job_specs": "abd",
    "doc_generated": "adoc",
}


def check_step_input_artifacts(
    step,
    existing_artifacts: dict,
) -> dict:
    """ステップの前提成果物が存在するかチェックする。

    Args:
        step: StepDef インスタンス。
        existing_artifacts: _detect_existing_artifacts() が返す dict。

    Returns:
        {
            "missing": [{"key": str, "expected": str, "next_workflow": str | None}],
            "skipped_none": bool,  # True = consumed_artifacts=None → 後方互換でスキップ
        }

    セマンティクス:
        consumed_artifacts=None → 後方互換モード。チェックをスキップして skipped_none=True。
        consumed_artifacts=[]   → 前提成果物なし。missing=[].
        consumed_artifacts=[k]  → 各キーを existing_artifacts で照合。
        未知のキー               → expected = "(不明: 要確認)" で missing に追加。
    """
    if step.consumed_artifacts is None:
        return {"missing": [], "skipped_none": True}

    missing = []
    for key in step.consumed_artifacts:
        if key not in existing_artifacts:
            expected = _ARTIFACT_KEY_TO_EXPECTED_PATH.get(key, f"(不明: 要確認 key={key!r})")
            next_wf = _ARTIFACT_KEY_TO_GENERATING_WORKFLOW.get(key)  # None は未確認
            missing.append({
                "key": key,
                "expected": expected,
                "next_workflow": next_wf,
            })

    return {"missing": missing, "skipped_none": False}


def _check_workflow_input_artifacts(
    wf,
    active_steps: Set[str],
    existing_artifacts: dict,
    config: "SDKConfig",
    console: "Console",
) -> dict:
    """ワークフロー実行前に**ルートステップ**の前提成果物をチェックする。

    チェック対象をルートステップ（depends_on=[] の非コンテナ Step）に限定する理由:
    非ルートステップが consumed_artifacts に列挙した成果物は、同一ワークフロー内の
    先行ステップが生成する場合がある。ワークフロー開始前の時点でそれらが存在しないのは
    正常であり、不足扱いにすると正当な実行でも中断されてしまう。
    ルートステップの前提成果物は外部ワークフローが生成するものであり、開始前に
    存在しない場合は真に前提が満たされていない。

    警告モード（require_input_artifacts=False、デフォルト）:
        不足成果物を console.warning で出力して続行する。

    Strict モード（require_input_artifacts=True）:
        不足成果物がある場合は console.error で出力し、should_abort=True を返す。

    Args:
        wf: WorkflowDef インスタンス。
        active_steps: 実行対象のステップ ID セット。
        existing_artifacts: _detect_existing_artifacts() が返す dict。
        config: SDKConfig。require_input_artifacts フラグを参照する。
        console: Console インスタンス。

    Returns:
        {"should_abort": bool, "error": str | None}
    """
    all_missing: List[dict] = []

    for step in wf.steps:
        # ルートステップ（depends_on=[] の非コンテナ）のみチェック対象とする。
        # 非ルートステップは同ワークフロー内の先行ステップが成果物を生成するため除外。
        if step.is_container or step.id not in active_steps or step.depends_on:
            continue
        result = check_step_input_artifacts(step, existing_artifacts)
        if result["skipped_none"]:
            continue
        for m in result["missing"]:
            all_missing.append({**m, "step_id": step.id})

    if not all_missing:
        return {"should_abort": False, "error": None}

    # メッセージ構築
    lines = [
        f"前提成果物チェック: 以下の成果物が見つかりません（{len(all_missing)} 件）:",
    ]
    for item in all_missing:
        next_wf = item.get("next_workflow")
        if next_wf == "user_provided":
            hint = " → この成果物はワークフローでは生成されません。事前に手動で準備してください"
        elif next_wf:
            hint = f" → 先に '{next_wf}' ワークフローを実行してください"
        else:
            hint = " → 生成ワークフローを確認してください（ユーザー提供またはワークフロー生成の可能性あり）"
        lines.append(
            f"  - key={item['key']!r}, 期待パス: {item['expected']}"
            f" (Step {item['step_id']}){hint}"
        )

    if config.require_input_artifacts:
        lines.append(
            "\nstrict モード (HVE_REQUIRE_INPUT_ARTIFACTS=true) のため実行を中断します。"
            "\n警告モードで実行するには HVE_REQUIRE_INPUT_ARTIFACTS=false（デフォルト）を設定してください。"
        )
        msg = "\n".join(lines)
        console.error(msg)
        return {"should_abort": True, "error": msg}
    else:
        lines.append(
            "\n(warning モード: 続行します。strict モードにするには HVE_REQUIRE_INPUT_ARTIFACTS=true を設定してください)"
        )
        msg = "\n".join(lines)
        console.warning(msg)
        return {"should_abort": False, "error": None}


def _compute_step_additional_prompt(
    step,
    existing_artifacts: dict,
    config: "SDKConfig",
    base_additional_prompt: Optional[str],
) -> Optional[str]:
    """ステップの additional_prompt を計算する。

    HVE_REUSE_CONTEXT_FILTERING が有効で consumed_artifacts がアノテーション済みの場合、
    consumed_artifacts に指定されたキーのみを含む reuse_context を構築する。
    それ以外の場合は base_additional_prompt をそのまま返す（後方互換）。

    Args:
        step: StepDef インスタンス。
        existing_artifacts: _detect_existing_artifacts() が返す dict。
        config: SDKConfig。reuse_context_filtering フラグを参照する。
        base_additional_prompt: フィルタリングしない場合に使用する additional_prompt。

    Returns:
        フィルタリング済み additional_prompt または base_additional_prompt。
    """
    if step.consumed_artifacts is None:
        # Wave 2: consumed_artifacts=None は後方互換（全成果物注入）を意味する。
        # トークン増大の原因になるため、警告を出してどの Step が全成果物注入になっているか可視化する。
        import warnings as _warnings
        _warnings.warn(
            f"Step.{step.id}: consumed_artifacts=None — 後方互換モードで全成果物を注入します。"
            f"トークン削減のため consumed_artifacts を明示定義してください。",
            stacklevel=2,
        )
    if not (config.reuse_context_filtering and existing_artifacts and step.consumed_artifacts is not None):
        return base_additional_prompt

    # consumed_artifacts に未知キーが含まれている場合は警告
    missing_keys = [k for k in step.consumed_artifacts if k not in existing_artifacts]
    if missing_keys:
        import warnings as _warnings
        _warnings.warn(
            f"Step.{step.id}: consumed_artifacts に未知のキーが含まれています: {missing_keys}。"
            f"利用可能なキー: {sorted(existing_artifacts.keys())}",
            stacklevel=2,
        )

    # アノテーション済み: consumed_artifacts キーのみでフィルタリング
    filtered_artifacts = {
        k: v for k, v in existing_artifacts.items()
        if k in step.consumed_artifacts
    }
    step_reuse_context = _build_reuse_context(filtered_artifacts)
    result = ((config.additional_prompt or "") + step_reuse_context).strip() or None
    # Wave 2-3: context injection サイズを記録（デバッグ可視化）
    _injection_chars = len(step_reuse_context)
    if _injection_chars > 0:
        import logging as _logging
        _logging.getLogger(__name__).debug(
            "Step.%s context_injection: artifacts=%s chars=%d",
            step.id, list(filtered_artifacts.keys()), _injection_chars,
        )
    return result


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


async def _prefetch_workiq(
    config: SDKConfig,
    query: str,
    console: Console,
    timeout: float = 900.0,
) -> str:
    """Work IQ を別セッションで事前呼び出しし、結果テキストを返す（後方互換ラッパー）。

    NOTE: 現行の production コードから直接呼び出されていません（テストのみ）。
    現行ワークフロー実行経路では Work IQ は QA フェーズ専用であり、
    orchestrator からの直接呼び出しは行いません。
    """
    result = await _prefetch_workiq_detailed(config, query, console, timeout=timeout)
    return result.content


async def _prefetch_workiq_detailed(
    config: SDKConfig,
    query: str,
    console: Console,
    timeout: float = 900.0,
) -> "WorkIQPrefetchResult":
    """Work IQ を別セッションで呼び出し、詳細結果を返す後方互換ヘルパー。

    NOTE: 現行の production コードから直接呼び出されていません（テストのみ）。
    現行のワークフロー実行経路では Work IQ を QA フェーズ専用にしているため、
    orchestrator からこのヘルパーを直接呼び出してプロンプト注入する処理は行わない。
    Work IQ の利用は runner.py の QA フェーズ（run_step() 内）でのみ行われる。
    """
    try:
        from .workiq import (
            build_workiq_mcp_config, query_workiq,
            WorkIQPrefetchResult, WORKIQ_MCP_SERVER_NAME,
            extract_workiq_tool_name_from_event,
        )
    except ImportError:
        from workiq import (  # type: ignore[no-redef]
            build_workiq_mcp_config, query_workiq,
            WorkIQPrefetchResult, WORKIQ_MCP_SERVER_NAME,
            extract_workiq_tool_name_from_event,
        )

    _start = time.monotonic()

    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため Work IQ 事前取得をスキップします。"
        )
        return WorkIQPrefetchResult(
            error_type="sdk_import_failure",
            error_message="Copilot SDK が利用できません",
            elapsed_seconds=time.monotonic() - _start,
        )

    if config.cli_url:
        sdk_cfg = ExternalServerConfig(url=config.cli_url)
    else:
        sdk_cfg = SubprocessConfig(
            cli_path=config.cli_path,
            github_token=config.resolve_token() or None,
            log_level="error",
        )

    client = CopilotClient(config=sdk_cfg)
    await client.start()

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id)
        _session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
        }
        # Auto 選択時は model 引数を省略し、GitHub 側の Auto model selection に委譲する。
        if config.model and config.model != MODEL_AUTO_VALUE:
            _session_opts["model"] = config.model
        session = await client.create_session(**_session_opts)

        # ツール呼び出し追跡
        _called_tools: list = []
        _event_subscription_succeeded = False

        def _on_event(event: object) -> None:
            tool_name = extract_workiq_tool_name_from_event(event)
            if tool_name:
                _called_tools.append(tool_name)

        try:
            session.on(_on_event)
            _event_subscription_succeeded = True
        except Exception:
            pass

        try:
            # MCP ステータス確認（runner.py run_step() と同等のチェック）
            try:
                mcp_list = await session.rpc.mcp.list()
                wiq_found = False
                mcp_status = None
                mcp_error = None
                for srv in mcp_list.servers:
                    if srv.name == WORKIQ_MCP_SERVER_NAME:
                        # SDK 実装差異により enum もしくは文字列で返るため両対応する
                        mcp_status = srv.status.value if hasattr(srv.status, "value") else str(srv.status)
                        mcp_error = getattr(srv, "error", None)
                        if mcp_status != "connected":
                            console.warning(
                                f"Work IQ prefetch: MCP サーバー状態 = {mcp_status}"
                                + (f" — {mcp_error}" if mcp_error else "")
                                + "\n  診断コマンド: python -m hve workiq-doctor --sdk-probe --sdk-tool-probe --sdk-event-trace"
                                + "\n  Windows の場合は npx.cmd -y @microsoft/workiq mcp を手動確認してください"
                            )
                            return WorkIQPrefetchResult(
                                error_type="mcp_not_connected",
                                error_message=f"MCP status={mcp_status}" + (f", error={mcp_error}" if mcp_error else ""),
                                mcp_server_found=True,
                                mcp_status=mcp_status,
                                mcp_error=str(mcp_error) if mcp_error else None,
                                elapsed_seconds=time.monotonic() - _start,
                            )
                        wiq_found = True
                        break
                if not wiq_found:
                    console.warning(
                        f"Work IQ prefetch: MCP サーバー '{WORKIQ_MCP_SERVER_NAME}' がセッション一覧に存在しません\n"
                        "  診断コマンド: python -m hve workiq-doctor --sdk-probe --sdk-tool-probe --sdk-event-trace\n"
                        "  Windows の場合は WORKIQ_NPX_COMMAND=npx.cmd を試してください"
                    )
                    return WorkIQPrefetchResult(
                        error_type="mcp_not_found",
                        error_message=f"MCP サーバー '{WORKIQ_MCP_SERVER_NAME}' がセッション一覧に存在しません",
                        mcp_server_found=False,
                        elapsed_seconds=time.monotonic() - _start,
                    )
            except Exception as mcp_err:
                console.warning(
                    f"Work IQ prefetch: MCP ステータス確認失敗: {mcp_err}\n"
                    "  診断コマンド: python -m hve workiq-doctor --sdk-probe --sdk-tool-probe --sdk-event-trace"
                )
                return WorkIQPrefetchResult(
                    error_type="mcp_list_failure",
                    error_message=str(mcp_err),
                    elapsed_seconds=time.monotonic() - _start,
                )

            console.workiq_prompt(query, label="Work IQ プロンプト [prefetch]")
            result_text = await query_workiq(session, query, timeout=timeout)
            console.workiq_response(result_text or "", label="Work IQ 応答 [prefetch]")
            _elapsed = time.monotonic() - _start
            _tool_called = bool(_called_tools)

            if not _tool_called:
                # tool_called=False の場合: result_text の有無に関わらず未観測として扱う。
                # LLM がツールを呼ばずに説明文のみ返した可能性があるため、
                # M365 信頼データとして扱わない（safe_to_inject=False）。
                _has_text = bool(result_text)
                if _has_text:
                    console.warning(
                        "⚠️ Work IQ prefetch: Work IQ MCP ツール呼び出しを SDK イベント上で確認できませんでした。\n"
                        "  LLM がツールを呼ばずに応答した、またはイベント検出に失敗した可能性があります。\n"
                        "  テキスト応答は Work IQ 由来のデータとして扱いません。\n"
                        "  診断コマンド: python -m hve workiq-doctor --event-extractor-self-test --sdk-tool-probe --sdk-event-trace"
                    )
                else:
                    console.warning(
                        "⚠️ Work IQ prefetch: ツールが呼び出されませんでした。\n"
                        "  エージェントが Work IQ 指示を実行しなかった可能性があります。\n"
                        "  診断コマンド: python -m hve workiq-doctor --event-extractor-self-test --sdk-tool-probe --sdk-event-trace"
                    )
                return WorkIQPrefetchResult(
                    content=result_text or "",
                    error_type="tool_not_invoked",
                    error_message=(
                        "Work IQ MCP ツール呼び出しを SDK イベント上で確認できませんでした。 "
                        "LLM がツールを呼ばずに応答した、またはイベント検出に失敗した可能性があります。"
                    ),
                    mcp_server_found=True,
                    mcp_status="connected",
                    tool_called=False,
                    called_tools=[],
                    elapsed_seconds=_elapsed,
                    safe_to_inject=False,
                    result_source="llm_text" if _has_text else None,
                    event_subscription_succeeded=_event_subscription_succeeded,
                )

            return WorkIQPrefetchResult(
                content=result_text,
                success=bool(result_text),
                mcp_server_found=True,
                mcp_status="connected",
                tool_called=_tool_called,
                called_tools=list(_called_tools),
                elapsed_seconds=_elapsed,
                safe_to_inject=bool(result_text),
                result_source="tool_execution" if _tool_called else None,
                event_subscription_succeeded=_event_subscription_succeeded,
            )
        finally:
            await session.disconnect()
    except Exception as exc:
        console.warning(f"Work IQ 事前取得に失敗しました: {exc}")
        return WorkIQPrefetchResult(
            error_type="query_exception",
            error_message=str(exc),
            elapsed_seconds=time.monotonic() - _start,
        )
    finally:
        await client.stop()


def _append_workiq_prefetch_log(
    log_path: Path,
    *,
    event_type: str,
    query_label: str,
    content: str = "",
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    resolved_npx_command: Optional[str] = None,
    tenant_id_specified: bool = False,
    tool_called: Optional[bool] = None,
    called_tools: Optional[list] = None,
    mcp_status: Optional[str] = None,
    event_subscription_succeeded: Optional[bool] = None,
    result_source: Optional[str] = None,
    safe_to_inject: Optional[bool] = None,
) -> None:
    """Work IQ prefetch の prompt / result / error を JSONL へ追記する。

    エラーイベント（event_type が ``.error`` で終わるもの）または
    error_type が指定されている場合は content が空でも書き込む。機微情報は含めないこと。
    """
    is_error_event = event_type.endswith(".error") or event_type.endswith("_error") or error_type is not None
    if not is_error_event and (not content or not content.strip()):
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "eventType": event_type,
        "queryLabel": query_label,
    }
    if content:
        record["content"] = content
    if error_type:
        record["errorType"] = error_type
    if error_message:
        record["message"] = error_message
    if resolved_npx_command:
        record["resolvedNpxCommand"] = resolved_npx_command
    if tenant_id_specified:
        record["tenantIdSpecified"] = True
    if tool_called is not None:
        record["toolCalled"] = tool_called
    if called_tools is not None:
        record["calledTools"] = called_tools
    if mcp_status is not None:
        record["mcpStatus"] = mcp_status
    if event_subscription_succeeded is not None:
        record["eventSubscriptionSucceeded"] = event_subscription_succeeded
    if result_source is not None:
        record["resultSource"] = result_source
    if safe_to_inject is not None:
        record["safeToInject"] = safe_to_inject
    try:
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return


# -----------------------------------------------------------------------
# AKM Work IQ 検証フェーズ
# -----------------------------------------------------------------------

_AKM_WORKIQ_DXX_MAX_CONTENT_LENGTH: int = 30_000
"""Dxx ファイル全文の切り詰め上限（Work IQ 検証用）。"""

_AKM_WORKIQ_SUMMARY_MAX_LENGTH: int = 3_000
"""Work IQ クエリに送る Dxx 要約の最大長。"""

_AKM_WORKIQ_QUERY_INTERVAL: float = 2.0
"""Dxx 間のクエリインターバル（秒）。"""


def _summarize_dxx_for_query(filepath: Path, content: str) -> str:
    """Dxx ファイルの内容から Work IQ クエリ用の要約を生成する。

    タイトル行 + 各セクション見出し + 未解決/仮定項目の先頭数行を抽出し、
    _AKM_WORKIQ_SUMMARY_MAX_LENGTH 以内に収める。
    """
    lines = content.splitlines()
    summary_parts: list[str] = []

    # タイトル行（# で始まる最初の行）
    for line in lines[:5]:
        if line.startswith("# "):
            summary_parts.append(line)
            break

    # セクション見出し + 直後の内容を抽出
    in_section = False
    section_lines: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if section_lines:
                summary_parts.extend(section_lines[:5])
            summary_parts.append(line)
            section_lines = []
            in_section = True
        elif in_section:
            stripped = line.strip()
            if stripped:
                section_lines.append(line)
    if section_lines:
        summary_parts.extend(section_lines[:5])

    summary = "\n".join(summary_parts)
    if len(summary) > _AKM_WORKIQ_SUMMARY_MAX_LENGTH:
        summary = summary[:_AKM_WORKIQ_SUMMARY_MAX_LENGTH] + "\n...(truncated)"
    return summary


async def _run_akm_workiq_verification(
    config: SDKConfig,
    console: Console,
    workiq_report_paths: Set[str],
) -> None:
    """AKM Post-DAG: Work IQ で knowledge/Dxx ドキュメントの妥当性を検証・修正する。

    AKM の各ステップにおける事後 QA フェーズ（Phase 2）は廃止されたため、
    本関数が AKM 後の Work IQ 経由検証の唯一の経路である。

    各 Dxx ファイルについて:
    1. Work IQ に KM 用プロンプトで検証クエリを送信
    2. 有効な情報が見つかった場合、Copilot セッションで Dxx ファイルを更新
    3. 更新箇所に情報ソースを付与
    """
    try:
        from .workiq import (
            build_workiq_mcp_config, query_workiq,
            get_workiq_prompt_template, save_workiq_result,
            is_workiq_error_response, is_workiq_available,
            WORKIQ_MCP_SERVER_NAME, _escape_workiq_sandbox_tags,
        )
    except ImportError:
        from workiq import (  # type: ignore[no-redef]
            build_workiq_mcp_config, query_workiq,
            get_workiq_prompt_template, save_workiq_result,
            is_workiq_error_response, is_workiq_available,
            WORKIQ_MCP_SERVER_NAME, _escape_workiq_sandbox_tags,
        )

    if not is_workiq_available():
        console.warning("Work IQ が利用できないため AKM Work IQ 検証をスキップします。")
        return

    # Dxx ファイル一覧を取得（business-requirement-document-status.md を除外）
    dxx_files = sorted(
        p for p in Path("knowledge").glob("D??-*.md")
        if p.name != "business-requirement-document-status.md"
    )
    if not dxx_files:
        console.warning("knowledge/ 配下に Dxx ファイルが見つかりません。検証をスキップします。")
        return

    console.event(f"AKM Work IQ 検証: {len(dxx_files)} 件の Dxx ファイルを検証します")

    # SDK / セッション準備
    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため AKM Work IQ 検証をスキップします。"
        )
        return

    if config.cli_url:
        sdk_cfg = ExternalServerConfig(url=config.cli_url)
    else:
        sdk_cfg = SubprocessConfig(
            cli_path=config.cli_path,
            github_token=config.resolve_token() or None,
            log_level="error",
        )

    client = CopilotClient(config=sdk_cfg)
    await client.start()

    verified_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        # Work IQ MCP 付きセッションを作成
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
        }
        if config.model and config.model != MODEL_AUTO_VALUE:
            session_opts["model"] = config.model

        session = await client.create_session(**session_opts)

        try:
            # MCP 接続確認
            try:
                mcp_list = await session.rpc.mcp.list()
                wiq_found = False
                for srv in mcp_list.servers:
                    if srv.name == WORKIQ_MCP_SERVER_NAME:
                        mcp_status = srv.status.value if hasattr(srv.status, "value") else str(srv.status)
                        if mcp_status != "connected":
                            console.warning(
                                f"AKM Work IQ 検証: MCP サーバー状態 = {mcp_status}。検証をスキップします。"
                            )
                            return
                        wiq_found = True
                        break
                if not wiq_found:
                    console.warning(
                        f"AKM Work IQ 検証: MCP サーバー '{WORKIQ_MCP_SERVER_NAME}' が見つかりません。検証をスキップします。"
                    )
                    return
            except Exception as mcp_err:
                console.warning(f"AKM Work IQ 検証: MCP ステータス確認失敗: {mcp_err}")
                return

            console.event("AKM Work IQ 検証: MCP 接続確認完了")

            # 各 Dxx ファイルを順次処理
            for idx, dxx_path in enumerate(dxx_files):
                dxx_filename = dxx_path.name
                dxx_filepath = str(dxx_path).replace("\\", "/")

                console.event(f"  [{idx + 1}/{len(dxx_files)}] {dxx_filename} を検証中...")

                try:
                    dxx_content = dxx_path.read_text(encoding="utf-8")
                except OSError as read_err:
                    console.warning(f"  {dxx_filename}: ファイル読み取り失敗: {read_err}")
                    error_count += 1
                    continue

                if not dxx_content.strip():
                    console.warning(f"  {dxx_filename}: ファイルが空です。スキップします。")
                    skipped_count += 1
                    continue

                # (2) Work IQ 検証クエリ
                dxx_summary = _summarize_dxx_for_query(dxx_path, dxx_content)
                km_prompt_template = get_workiq_prompt_template(
                    "km", config.workiq_prompt_km
                )
                workiq_query = km_prompt_template.format(target_content=dxx_summary)
                console.workiq_prompt(
                    workiq_query,
                    label=f"Work IQ プロンプト [{dxx_filename.split('-')[0]} KM]",
                )

                try:
                    workiq_result = await query_workiq(
                        session, workiq_query,
                        timeout=config.workiq_per_question_timeout,
                    )
                except Exception as wiq_err:
                    console.warning(f"  {dxx_filename}: Work IQ クエリ失敗: {wiq_err}")
                    error_count += 1
                    if idx < len(dxx_files) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                console.workiq_response(
                    workiq_result or "",
                    label=f"Work IQ 応答 [{dxx_filename.split('-')[0]} KM]",
                )

                # 結果を保存
                _d_class_id = dxx_filename.split("-")[0]  # "D01", "D02", etc.
                save_path = save_workiq_result(
                    config.run_id, "1", f"km-verify-{_d_class_id}",
                    workiq_result or "",
                    is_error=is_workiq_error_response(workiq_result or ""),
                    base_dir=config.workiq_draft_output_dir or "qa",
                )
                if save_path:
                    workiq_report_paths.add(str(save_path))

                verified_count += 1

                # (3) 応答判定
                if not workiq_result or not workiq_result.strip():
                    console.event(f"  {dxx_filename}: Work IQ 応答なし。スキップします。")
                    skipped_count += 1
                    if idx < len(dxx_files) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                if is_workiq_error_response(workiq_result):
                    console.warning(f"  {dxx_filename}: Work IQ エラー応答。スキップします。")
                    skipped_count += 1
                    if idx < len(dxx_files) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                # 「関連情報なし」判定
                _no_info_keywords = ("関連情報なし", "関連する情報は見つかりませんでした", "該当する情報はありません")
                _result_lower = workiq_result.strip()
                if any(kw in _result_lower for kw in _no_info_keywords):
                    console.event(f"  {dxx_filename}: 関連情報なし")
                    if idx < len(dxx_files) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                # (4) Dxx ファイル更新
                console.event(f"  {dxx_filename}: Work IQ 関連情報あり → ファイル更新を実行")

                # Dxx 内容を切り詰め
                _dxx_for_prompt = dxx_content
                if len(_dxx_for_prompt) > _AKM_WORKIQ_DXX_MAX_CONTENT_LENGTH:
                    _dxx_for_prompt = _dxx_for_prompt[:_AKM_WORKIQ_DXX_MAX_CONTENT_LENGTH] + "\n...(truncated)"

                update_prompt = AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT.format(
                    dxx_filename=dxx_filename,
                    dxx_content=_escape_workiq_sandbox_tags(_dxx_for_prompt),
                    dxx_filepath=dxx_filepath,
                    workiq_result=_escape_workiq_sandbox_tags(workiq_result),
                )

                try:
                    update_response = await session.send_and_wait(
                        update_prompt, timeout=config.timeout_seconds
                    )
                    update_output = _extract_text(update_response)
                    if update_output:
                        updated_count += 1
                        console.event(f"  {dxx_filename}: 更新完了")
                    else:
                        console.warning(f"  {dxx_filename}: 更新応答が空でした")
                except Exception as upd_err:
                    console.warning(f"  {dxx_filename}: ファイル更新失敗: {upd_err}")
                    error_count += 1

                if idx < len(dxx_files) - 1:
                    await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)

        finally:
            await session.disconnect()
    except Exception as exc:
        console.warning(f"AKM Work IQ 検証中にエラーが発生しました: {exc}")
        error_count += 1
    finally:
        await client.stop()

    console.event(
        f"AKM Work IQ 検証完了: 検証={verified_count}, 更新={updated_count}, "
        f"スキップ={skipped_count}, エラー={error_count}"
    )


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

    console = Console(
        verbose=config.verbose,
        quiet=config.quiet,
        show_stream=config.show_stream,
        show_reasoning=config.show_reasoning,
        verbosity=config.verbosity,
    )
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
    if config.auto_qa and config.qa_phase in ("pre", "both"):
        _phases.append("実行計画 → DAG 実行（事前 QA + Work IQ → 各ステップ実行）")
    else:
        _phases.append("実行計画 → DAG 実行")
    if workflow_id == "akm" and config.is_workiq_akm_review_enabled() and not config.dry_run:
        _phases.append("AKM Work IQ 検証")
    _si_scope = config.self_improve_scope
    _workflow_si_allowed = _si_scope in ("", "workflow")
    if config.auto_self_improve and not config.self_improve_skip and not config.dry_run and _workflow_si_allowed:
        # Post-DAG の前（"後処理 (git push + PR)" の前）に挿入
        # create_issues/create_pr の場合は後処理の前、そうでなければ末尾
        idx = len(_phases)
        if config.create_issues or config.create_pr:
            # "後処理 (git push + PR)" の前に挿入
            for i, phase_name in enumerate(_phases):
                if "後処理" in phase_name:
                    idx = i
                    break
        _phases.insert(idx, "自己改善ループ")
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
    # Agent プロンプトでは done ラベル付与を要求しない（付与は orchestrator 側で実施）。
    execution_mode = "local"

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

    # --- 2.5. 推薦アーキテクチャ APP-ID フィルタ ---
    _ARCH_FILTER_WORKFLOWS = {"aad-web", "asdw-web", "abd", "abdv"}
    if wf.id in _ARCH_FILTER_WORKFLOWS:
        _requested_ids = effective_params.get("app_ids") or (
            [effective_params["app_id"]] if effective_params.get("app_id") else None
        )
        try:
            _filter_result = resolve_app_arch_scope(
                workflow_id=wf.id,
                requested_app_ids=_requested_ids,
                dry_run=config.dry_run,
            )
        except (FileNotFoundError, ValueError) as _filter_exc:
            console.error(f"app-arch filter エラー: {_filter_exc}")
            elapsed = time.time() - start_total
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "elapsed_total": elapsed,
                "error": str(_filter_exc),
            }

        if _filter_result.matched_app_ids:
            effective_params["app_ids"] = _filter_result.matched_app_ids
            effective_params["app_id"] = (
                _filter_result.matched_app_ids[0]
                if len(_filter_result.matched_app_ids) == 1
                else ""
            )
        elif _filter_result.catalog_found:
            # catalog が存在して 0 件 → DAG を実行しない
            _reason = "対象アーキテクチャに一致する APP-ID がありません"
            console.warning(
                f"推薦アーキテクチャ APP-ID フィルタ: 対象 APP-ID が 0 件のためスキップします（{_reason}）"
            )
            elapsed = time.time() - start_total
            _zero_match_result = {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "elapsed_total": elapsed,
                "skipped_reason": _reason,
            }
            if config.dry_run:
                _zero_match_result["dry_run"] = True
            return _zero_match_result
        else:
            # catalog が存在しない（dry_run=True の場合は warning 継続済み）
            # params は変更しない（従来互換）
            pass

        effective_params["app_arch_filter"] = _filter_result.to_dict()
        effective_params["app_arch_scope_section"] = _filter_result.to_markdown_section()

    # --- 3. ステップフィルタリング ---
    p = _next_phase()
    phase_start = time.time()
    console.phase_start(p, _total_phases, "ステップフィルタリング")

    selected_step_ids: List[str] = effective_params.get("selected_steps") or []
    active_steps: Set[str] = resolve_selected_steps(wf, selected_step_ids)

    console.event(f"実行対象ステップ数: {len(active_steps)}")
    console.phase_end(p, _total_phases, "ステップフィルタリング", time.time() - phase_start)

    dry_run_plan = build_dag_plan(
        wf,
        active_steps,
        max_parallel=config.max_parallel,
        max_parallel_source="config",
    )

    # --- dry_run: 実行計画表示のみ ---
    if config.dry_run:
        _print_dry_run_plan(wf, active_steps, config, console, dry_run_plan)
        elapsed = time.time() - start_total
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": list(active_steps),
            "elapsed_total": elapsed,
            "dry_run": True,
            "dag_plan_waves": len(dry_run_plan.waves),
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

    root_issue_num, step_issue_map = _create_issues_if_needed(
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

    # --- メタワークフロー前提チェック ---
    from hve.workflow_registry import get_meta_dependencies

    deps = get_meta_dependencies(workflow_id)
    if deps:
        glob_cache: Dict[str, bool] = {}

        def _artifact_exists(pattern: str) -> bool:
            if pattern not in glob_cache:
                glob_cache[pattern] = next(_glob.iglob(pattern), None) is not None
            return glob_cache[pattern]

        missing_artifacts: List[str] = []
        for dep in deps:
            for pattern in dep.required_artifacts:
                if not _artifact_exists(pattern):
                    missing_artifacts.append(f"  - {pattern} (required by {dep.workflow_id})")

        if missing_artifacts:
            msg = "以下の前提成果物が見つかりません:\n" + "\n".join(missing_artifacts)
            soft_only = all(
                d.soft for d in deps
                if any(not _artifact_exists(p) for p in d.required_artifacts)
            )
            if soft_only:
                console.warning(msg + "\n(soft dependency のため続行します)")
            else:
                console.error(msg)
                if not config.dry_run:
                    return {
                        "workflow_id": workflow_id,
                        "completed": [],
                        "failed": [],
                        "skipped": [],
                        "elapsed_total": time.time() - start_total,
                        "error": msg,
                    }

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

    # --- Phase 8: ステップ前提成果物チェック ---
    _artifact_check = _check_workflow_input_artifacts(
        wf=wf,
        active_steps=active_steps,
        existing_artifacts=existing_artifacts,
        config=config,
        console=console,
    )
    if _artifact_check["should_abort"]:
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "elapsed_total": time.time() - start_total,
            "error": _artifact_check["error"],
        }

    # ステップ → プロンプト の事前構築
    step_prompts: Dict[str, str] = {}
    workiq_report_paths: Set[str] = set()
    # Wave 2-3 / 2-7: context injection サイズの観測カウンタ
    _w2_none_steps: int = 0          # consumed_artifacts=None のステップ数
    _w2_injection_total: int = 0     # context injection 合計文字数
    _w2_injection_max: int = 0       # context injection 最大文字数（1 step あたり）
    for step in wf.steps:
        if step.is_container or step.id not in active_steps:
            continue
        # Wave 2-2: consumed_artifacts=None ステップをカウント
        if step.consumed_artifacts is None:
            _w2_none_steps += 1
        step_additional = _compute_step_additional_prompt(
            step=step,
            existing_artifacts=existing_artifacts,
            config=config,
            base_additional_prompt=effective_additional_prompt,
        )
        # Wave 2-3: context injection は共通 additional prompt を除いた、
        # ステップ固有の追加コンテキスト分のみを計上する
        _base_additional_chars = len(effective_additional_prompt) if effective_additional_prompt else 0
        if step_additional:
            if _base_additional_chars > 0 and step_additional.startswith(effective_additional_prompt or ""):
                _injection_chars = len(step_additional) - _base_additional_chars
            else:
                _injection_chars = len(step_additional)
        else:
            _injection_chars = 0
        _w2_injection_total += _injection_chars
        if _injection_chars > _w2_injection_max:
            _w2_injection_max = _injection_chars
        step_prompts[step.id] = _build_step_prompt(
            step=step,
            params=effective_params,
            root_issue_num=root_issue_num,
            render_template_fn=render_template,
            wf=wf,
            additional_prompt=step_additional,
            execution_mode=execution_mode,
        )

    dag_plan = build_dag_plan(
        wf,
        active_steps,
        step_prompts=step_prompts,
        max_parallel=config.max_parallel,
        max_parallel_source="config",
    )

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
            workflow_id=workflow_id,
        )

    executor = DAGExecutor(
        workflow=wf,
        run_step_fn=run_step_fn,
        active_step_ids=active_steps,
        max_parallel=config.max_parallel,
        console=console,
        step_prompts=step_prompts,
        dag_plan=dag_plan,
    )

    # 実行計画を事前表示
    waves = executor.compute_waves()
    if waves:
        console.execution_plan(waves, len(active_steps), config.max_parallel)

    results = await executor.execute()
    if config.create_issues and step_issue_map:
        token = config.resolve_token()
        repo = config.repo
        if token and repo:
            done_label = f"{wf.label_prefix}:done"
            for step_id in executor.completed:
                issue_num = step_issue_map.get(step_id)
                if issue_num is None:
                    continue
                ok = add_labels(
                    issue_num=issue_num,
                    labels=[done_label],
                    repo=repo,
                    token=token,
                )
                if not ok:
                    console.warning(
                        f"Step.{step_id} の Sub-Issue #{issue_num} へのラベル付与に失敗しました。"
                    )
    console.phase_end(p, _total_phases, "実行計画 → DAG 実行", time.time() - phase_start_dag)

    # --- AQOD 成果物検証（warning のみ、hard fail なし）---
    aqod_validation_result: Optional[dict] = None
    if workflow_id == "aqod" and not config.dry_run:
        try:
            try:
                from .artifact_validation import validate_aqod_run
            except ImportError:
                from artifact_validation import validate_aqod_run  # type: ignore[no-redef]
            aqod_validation_result = validate_aqod_run(qa_dir="qa", run_id=config.run_id)
            _av_overall = aqod_validation_result.get("overall", "FAIL")
            _av_found = aqod_validation_result.get("artifacts_found", 0)
            _av_passed = aqod_validation_result.get("passed", 0)
            if _av_overall == "PASS":
                console.event(
                    f"✅ AQOD 成果物検証 PASS: {_av_passed}/{_av_found} 件の QA-DocConsistency-*.md が有効です。"
                )
            elif _av_overall == "WARN":
                console.warning(
                    f"⚠️ AQOD 成果物検証 WARN: {_av_passed}/{_av_found} 件が有効（一部に問題あり）。"
                )
            else:
                console.warning(
                    "⚠️ AQOD 成果物検証 FAIL: QA-DocConsistency-*.md が見つからないか、必須要件を満たしていません。\n"
                    "   execution-qa-merged.md は HVE 実行補助 QA であり、AQOD 本体成果物ではありません。\n"
                    "   AQOD 本体成果物は qa/QA-DocConsistency-*.md です。"
                )
            for vr in (aqod_validation_result.get("validation_results") or []):
                for err in (vr.get("errors") or []):
                    console.warning(f"  [検証エラー] {vr.get('path')}: {err}")
                for warn in (vr.get("warnings") or []):
                    console.warning(f"  [検証警告] {vr.get('path')}: {warn}")
        except Exception as av_exc:
            console.warning(f"AQOD 成果物検証中にエラーが発生しました（無視して続行）: {av_exc}")

    # --- AKM Work IQ 検証（AKM 実行後レビュー Work IQ が有効な場合）---
    if workflow_id == "akm" and config.is_workiq_akm_review_enabled() and not config.dry_run:
        p = _next_phase()
        phase_start_akm_wiq = time.time()
        console.phase_start(p, _total_phases, "AKM Work IQ 検証")
        try:
            await _run_akm_workiq_verification(
                config=config,
                console=console,
                workiq_report_paths=workiq_report_paths,
            )
        except Exception as akm_wiq_exc:
            console.warning(
                f"AKM Work IQ 検証中にエラーが発生しました（無視して続行）: {akm_wiq_exc}"
            )
        console.phase_end(p, _total_phases, "AKM Work IQ 検証", time.time() - phase_start_akm_wiq)

    # PR 作成フェーズで参照するため事前初期化（auto_self_improve=False 時の NameError 防止）
    si_task_goal: Optional["TaskGoal"] = None
    si_disc_sources: List[str] = []

    # --- Self-Improve（オプション） ---
    # scope が "" または "workflow" の場合のみ実行。"step" / "disabled" の場合はスキップ。
    _si_scope = config.self_improve_scope
    _workflow_si_allowed = _si_scope in ("", "workflow")
    if config.auto_self_improve and not config.self_improve_skip and not config.dry_run and not _workflow_si_allowed:
        console.event(
            f"Post-DAG Self-Improve をスキップ "
            f"(self_improve_scope={_si_scope!r} — workflow-level は実行しない)"
        )
    if config.auto_self_improve and not config.self_improve_skip and not config.dry_run and _workflow_si_allowed:
        p = _next_phase()
        phase_start_si = time.time()
        console.phase_start(p, _total_phases, "自己改善ループ")

        from hve.self_improve import (
            run_improvement_loop, define_task_goal, TaskGoal,
            discover_task_goal_from_docs,
        )

        # ワークフロー種別に応じたデフォルト target_scope（config.py の定数を使用）
        _si_scope_defaults = SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS

        def _collect_workflow_output_paths(wf_id: str) -> List[str]:
            """ワークフローの全ステップの output_paths を集約する。
            現状 Step に output_paths 属性はないため空リストを返す。
            """
            return []

        _workflow_outputs = _collect_workflow_output_paths(workflow_id)
        _workflow_default = _si_scope_defaults.get(workflow_id, "")

        # 既存挙動互換: target_scope が空かつ outputs も取れない場合は _si_scope_defaults を使う
        effective_si_scope = (
            config.self_improve_target_scope
            or (_workflow_default if not _workflow_outputs else "")
        )
        orig_scope = config.self_improve_target_scope
        config.self_improve_target_scope = effective_si_scope

        # scan_codebase に渡せるよう一時属性として保持（設定前の値を退避）
        _prev_resolved_step_paths = getattr(config, "_resolved_step_output_paths", None)
        _prev_resolved_wf_default = getattr(config, "_resolved_workflow_default", "")
        config._resolved_step_output_paths = _workflow_outputs  # type: ignore[attr-defined]
        config._resolved_workflow_default = _workflow_default  # type: ignore[attr-defined]

        # タスクゴールを確定する（TDD 的: ループ開始前に成功条件を定義）
        _user_goal = getattr(config, "self_improve_goal", "")
        if _user_goal:
            # ユーザー指定ゴールを優先
            task_goal = define_task_goal(
                workflow_id=workflow_id,
                user_goal_description=_user_goal,
            )
        else:
            # ドキュメントから自動生成（非対話モードでも実行）
            try:
                _disc_result = discover_task_goal_from_docs(
                    workflow_id=workflow_id,
                    target_scope=effective_si_scope,
                    repo_root=".",
                )
                task_goal = _disc_result["task_goal"]
                si_disc_sources = _disc_result["sources"]
                console.event(
                    f"自己改善ゴールを自動生成しました: "
                    f"{task_goal['goal_description'][:80]}"
                )
            except Exception as _disc_exc:
                console.warning(
                    f"ゴール自動検索に失敗しました: {_disc_exc}。標準ゴールを使用します。"
                )
                task_goal = define_task_goal(workflow_id=workflow_id)

        # config.self_improve_success_criteria が指定されていれば success_criteria を上書き
        _override_criteria = getattr(config, "self_improve_success_criteria", [])
        if _override_criteria:
            task_goal = TaskGoal(
                goal_description=task_goal["goal_description"],
                success_criteria=_override_criteria,
                reward_weights=task_goal["reward_weights"],
                tdd_phase=task_goal["tdd_phase"],
            )

        si_task_goal = task_goal

        # workflow_id をループ内で参照できるよう config に一時設定
        _prev_workflow_id = getattr(config, "workflow_id", "")
        config.workflow_id = workflow_id  # type: ignore[attr-defined]

        try:
            # run_improvement_loop は同期関数（内部で subprocess.run を使用）のため、
            # asyncio イベントループをブロックしないようスレッドプールに委譲する
            loop = asyncio.get_running_loop()
            si_result = await loop.run_in_executor(
                None,
                functools.partial(
                    run_improvement_loop,
                    config=config,
                    work_dir=Path(f"work/self-improve/run-{config.run_id}"),
                    repo_root=".",
                    task_goal=task_goal,
                ),
            )
        finally:
            config.self_improve_target_scope = orig_scope  # 復元
            config.workflow_id = _prev_workflow_id  # type: ignore[attr-defined]
            config._resolved_step_output_paths = _prev_resolved_step_paths  # type: ignore[attr-defined]
            config._resolved_workflow_default = _prev_resolved_wf_default  # type: ignore[attr-defined]

        console.event(
            f"Self-Improve 完了: {si_result['iterations_completed']} イテレーション, "
            f"最終スコア={si_result['final_score']}, "
            f"ゴール達成率={si_result['final_goal_achievement_pct'] * 100:.1f}%, "
            f"終了理由={si_result['stopped_reason']}"
        )
        console.phase_end(p, _total_phases, "自己改善ループ", time.time() - phase_start_si)

    # --- 8. Post-DAG: 統一後処理 ---
    code_review_error: Optional[str] = None
    pr_number: Optional[int] = None
    pr_error: Optional[str] = None

    if working_branch:
        p = _next_phase()
        phase_start_post = time.time()
        console.phase_start(p, _total_phases, "後処理 (git push + PR)")
        _ignore_paths_for_commit = list(config.ignore_paths or [])
        if (
            config.create_pr
            and config.auto_qa
            and workflow_id == "aqod"
            and "qa" in _ignore_paths_for_commit
        ):
            # AQOD の Phase 2 QA で生成される qa/ 成果物を
            # PR 作成時にコミット対象へ含めるため、qa を除外対象から外す。
            _ignore_paths_for_commit = [p for p in _ignore_paths_for_commit if p != "qa"]

        prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
        display_name_for_commit = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)
        pushed = _git_add_commit_push(
            branch=working_branch,
            commit_message=f"[{prefix}] {display_name_for_commit} — SDK ローカル実行の成果物",
            console=console,
            ignore_paths=_ignore_paths_for_commit,
        )
        if pushed:
            pr_number = _create_pr_if_needed(
                wf=wf,
                head_branch=working_branch,
                base_branch=config.base_branch,
                config=config,
                console=console,
                root_issue_num=root_issue_num,
                workiq_report_paths=sorted(workiq_report_paths),
                task_goal=si_task_goal,
                goal_sources=si_disc_sources,
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
    blocked_ids = list(getattr(executor, "blocked", set()))

    console.summary({
        "success": len(completed_ids),
        "failed": len(failed_ids),
        "skipped": len(skipped_ids),
        "total_elapsed": elapsed_total,
    })

    # Wave 2-7: 計測サマリーをログ出力
    _w2_si_scope = config.self_improve_scope or "(後方互換: step+workflow)"
    console.event(
        f"[Wave2] context_injection: none_steps={_w2_none_steps}, "
        f"total_chars={_w2_injection_total}, max_chars={_w2_injection_max}, "
        f"self_improve_scope={_w2_si_scope!r}"
    )

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
        "blocked": blocked_ids,
        "elapsed_total": elapsed_total,
        "code_review_error": code_review_error,
        "pr_number": pr_number,
        "root_issue_num": root_issue_num,
        "working_branch": working_branch,
        "error": pr_error,
        "aqod_validation": aqod_validation_result,
        # Wave 2-7: 計測項目
        "w2_none_steps": _w2_none_steps,
        "w2_injection_total_chars": _w2_injection_total,
        "w2_injection_max_chars": _w2_injection_max,
        "w2_self_improve_scope": config.self_improve_scope,
    }


# -----------------------------------------------------------------------
# ドライラン計画表示
# -----------------------------------------------------------------------

def _print_dry_run_plan(wf, active_steps: Set[str], config: SDKConfig, console: Console, dag_plan=None) -> None:
    """ドライラン時に DAG の波（Wave）を表示する。"""
    console.event(f"[DRY RUN] orchestrate: workflow={wf.id}")
    console.event("[DRY RUN] DAG Traversal:")

    if dag_plan is not None:
        for wave in dag_plan.waves:
            labels = " ‖ ".join(f"Step.{step_id}" for step_id in wave.step_ids)
            console.event(f"[DRY RUN]   Wave {wave.index}: {labels}")
        console.event(
            f"[DRY RUN] Plan summary: active={len(dag_plan.active_step_ids)}, "
            f"auto_skipped={len(dag_plan.auto_skipped_step_ids)}, waves={len(dag_plan.waves)}"
        )
        return

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


def _get_git_diff(base_ref: str, console: Console, max_diff_chars: int = _MAX_DIFF_CHARS) -> str:
    """git diff base_ref との差分テキストを返す。差分なし/エラーは空文字を返す。

    Args:
        base_ref: git diff の基点 (例: "HEAD~1", "main", "origin/main")
        console: コンソール出力用
        max_diff_chars: 差分の最大文字数（デフォルト: _MAX_DIFF_CHARS）

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
        if len(diff) > max_diff_chars:
            console.warning(
                f"差分が {len(diff)} 文字を超えるため {max_diff_chars} 文字にトリミングします。"
            )
            diff = diff[:max_diff_chars] + "\n... (truncated)"
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
    diff = _get_git_diff(config.review_base_ref, console, config.max_diff_chars)
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
    workiq_report_paths: Optional[List[str]] = None,
    task_goal: Optional["TaskGoal"] = None,
    goal_sources: Optional[List[str]] = None,
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
    if task_goal:
        body_lines.extend([
            "",
            "## 自己改善ゴール",
            "",
            f"**ゴール説明**: {task_goal['goal_description']}",
            "",
            "**成功条件:**",
        ])
        for crit in (task_goal.get("success_criteria") or []):
            body_lines.append(f"- {crit}")
        body_lines.append(f"\n**TDD フェーズ**: `{task_goal.get('tdd_phase', 'GREEN')}`")
        _goal_srcs = goal_sources or []
        if _goal_srcs:
            body_lines.extend(["", "**参照ソース:**"])
            for src in _goal_srcs[:5]:
                body_lines.append(f"- `{src}`")
            if len(_goal_srcs) > 5:
                body_lines.append(f"  - ...他 {len(_goal_srcs) - 5} 件")
    if config.workiq_enabled or config.is_workiq_qa_enabled() or config.is_workiq_akm_review_enabled():
        discovered_paths: Set[str] = set(workiq_report_paths or [])
        run_id = config.run_id
        draft_output_dir = (config.workiq_draft_output_dir or "").strip() or "qa"
        normalized_output_dir = Path(draft_output_dir).as_posix().lstrip("./")
        if run_id:
            report_globs = [
                str(Path(draft_output_dir) / f"{run_id}-*-workiq-*.md"),
                str(Path(draft_output_dir) / f"{run_id}-*-workiq-*.jsonl"),
            ]
            for report_glob in report_globs:
                for path in sorted(_glob.glob(report_glob)):
                    discovered_paths.add(path)
        ignore_roots = tuple((p or "").strip().strip("/\\") for p in (config.ignore_paths or []))
        filtered_paths = []
        for p in sorted(discovered_paths):
            normalized = Path(p).as_posix().lstrip("./")
            is_workiq_report = (
                normalized_output_dir
                and normalized.startswith(f"{normalized_output_dir}/")
                and "-workiq-" in Path(normalized).name
            )
            if normalized.startswith("work/"):
                # work/ は中間成果物（既定で ignore）で PR 本文の参照対象外とする。
                continue
            if (not is_workiq_report) and any(
                root and (normalized == root or normalized.startswith(f"{root}/"))
                for root in ignore_roots
            ):
                continue
            filtered_paths.append(normalized)
        if filtered_paths:
            body_lines.extend([
                "",
                "## Work IQ レポート",
                "以下の補助レポートを参照してレビューしてください:",
            ])
            body_lines.extend([f"- `{p}`" for p in filtered_paths])
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
