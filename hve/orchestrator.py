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
import copy
import functools
import glob as _glob
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# -----------------------------------------------------------------------
# 内部モジュールのインポート（相対 / 絶対 の両方に対応）
# -----------------------------------------------------------------------
try:
    from .config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_AUTO_REASONING_EFFORT, SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS
    from .console import Console, timestamp_prefix
    from .prompts import (
        CODE_REVIEW_AGENT_FIX_PROMPT,
        CODE_REVIEW_CLI_PROMPT,
        AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT,
        AKM_WORKIQ_INGEST_PROMPT,
        ARD_WORKIQ_USECASE_PROMPT,
        ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT,
    )
    from .runner import StepRunner, _is_review_fail, _extract_text
    from .dag_executor import DAGExecutor, StepResult
    from .dag_planner import build_dag_plan
    from .run_state import DEFAULT_SESSION_ID_PREFIX, RunState, StepState, make_session_id
    from .keybind import KEY_CTRL_R, KeybindMonitor
except ImportError:
    from config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_AUTO_REASONING_EFFORT, SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        CODE_REVIEW_AGENT_FIX_PROMPT,
        CODE_REVIEW_CLI_PROMPT,
        AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT,
        AKM_WORKIQ_INGEST_PROMPT,
        ARD_WORKIQ_USECASE_PROMPT,
        ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT,
    )
    from runner import StepRunner, _is_review_fail, _extract_text  # type: ignore[no-redef]
    from dag_executor import DAGExecutor, StepResult  # type: ignore[no-redef]
    from dag_planner import build_dag_plan  # type: ignore[no-redef]
    from run_state import DEFAULT_SESSION_ID_PREFIX, RunState, StepState, make_session_id  # type: ignore[no-redef]
    from keybind import KEY_CTRL_R, KeybindMonitor  # type: ignore[no-redef]

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


# -----------------------------------------------------------------------
# SDK ヘルパー
# -----------------------------------------------------------------------
async def _create_session_with_auto_reasoning_fallback(client: Any, session_opts: Dict[str, Any]) -> Any:
    """create_session を呼び出し、SDK が reasoning_effort を未サポートの場合は除外して再試行する。

    SDK バージョン < 0.3.0 互換のための防御。reasoning_effort が opts に
    含まれない場合は単純な create_session 呼び出しと等価。

    検出条件は Python の組み込み TypeError 文言
    (`got an unexpected keyword argument`) と `reasoning_effort` の両方が
    含まれる場合に限定する。
    """
    try:
        return await client.create_session(**session_opts)
    except TypeError as exc:
        msg = str(exc)
        if (
            "unexpected keyword argument" in msg
            and "reasoning_effort" in msg
            and "reasoning_effort" in session_opts
        ):
            _opts = {k: v for k, v in session_opts.items() if k != "reasoning_effort"}
            return await client.create_session(**_opts)
        raise


# -----------------------------------------------------------------------
# Context Injection 計測ログ
# -----------------------------------------------------------------------
def _format_context_injection_phase_breakdown(phase_breakdown: Dict[str, int]) -> str:
    """context injection のフェーズ別内訳を整形する。"""
    if not phase_breakdown:
        return "(なし)"
    ordered = sorted(phase_breakdown.items(), key=lambda item: item[0])
    return ", ".join(f"{phase}={chars}" for phase, chars in ordered)


def _emit_context_injection_metrics(
    *,
    none_steps: int,
    total_chars: int,
    max_chars: int,
    self_improve_scope: str,
    phase_breakdown: Dict[str, int],
    console: "Console",
) -> None:
    """context injection 計測を console / stderr / GitHub summary に出力する。"""
    phase_breakdown_str = _format_context_injection_phase_breakdown(phase_breakdown)
    summary_line = (
        f"[Wave2] context_injection: none_steps={none_steps}, "
        f"total_chars={total_chars}, max_chars={max_chars}, "
        f"phase_breakdown={phase_breakdown_str}, self_improve_scope={self_improve_scope!r}"
    )
    console.event(summary_line)
    print(summary_line, file=sys.stderr, flush=True)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not step_summary_path:
        return

    try:
        with open(step_summary_path, "a", encoding="utf-8") as f:
            f.write("## Wave2 Context Injection Metrics\n")
            f.write(f"- none_steps: {none_steps}\n")
            f.write(f"- total_chars: {total_chars}\n")
            f.write(f"- max_chars: {max_chars}\n")
            f.write(f"- phase_breakdown: {phase_breakdown_str}\n")
            f.write(f"- self_improve_scope: `{self_improve_scope}`\n\n")
    except OSError as exc:
        console.warning(f"GITHUB_STEP_SUMMARY への書き込みに失敗しました: {exc}")


# -----------------------------------------------------------------------
# Phase 2 (Resume): orchestrator レベルの SDK セッション ID ヘルパー
# -----------------------------------------------------------------------
def _orchestrator_session_id(config: SDKConfig, step_id: str, suffix: str = "") -> str:
    """orchestrator から作成する補助セッション用の決定論的 session_id を返す。

    runner.py の `StepRunner._make_step_session_id` と同等仕様（同じ run_id +
    step_id 区別 + suffix を持つ）。

    補助セッション例:
      step_id="orchestrator", suffix="workiq-prefetch"
        → "hve-<run_id>-step-orchestrator-workiq-prefetch"
      step_id="akm-verify", suffix="dxx"
        → "hve-<run_id>-step-akm-verify-dxx"
    """
    prefix = (config.session_id_prefix or "").strip() or DEFAULT_SESSION_ID_PREFIX
    return make_session_id(
        run_id=config.run_id,
        step_id=step_id,
        suffix=suffix,
        prefix=prefix,
    )


# -----------------------------------------------------------------------
# Phase 3 (Resume): SDKConfig 復元ヘルパー
# -----------------------------------------------------------------------
async def _auto_reconcile_on_resume(state: RunState, config: SDKConfig) -> None:
    """Phase 5 (Resume 2-layer txn): Resume 開始直前の整合性チェック。

    state.json 内で `running|failed` のステップが SDK 側に存在しない場合、
    `pending` + `session_id=None` に戻して新規 `create_session` 経路へ送る。
    SDK の `get_session_metadata(sid)` を使った O(1) 存在確認（Phase 0 で確認済）。

    失敗は warn のみ。SDK 接続不可の場合は何もしない（既存の resume_session →
    create_session fallback で救済される）。
    """
    try:
        from copilot import CopilotClient, SubprocessConfig  # type: ignore[import]
    except ImportError:
        return  # SDK 未利用環境では何もしない

    try:
        from .reconciler import reconcile_run
    except ImportError:
        from reconciler import reconcile_run  # type: ignore[no-redef]

    sdk_config = SubprocessConfig(
        cli_path=config.cli_path,
        github_token=config.resolve_token() or None,
        log_level="error",
    )
    client = CopilotClient(config=sdk_config)
    try:
        await client.start()
        result = await reconcile_run(state, sdk_client=client, dry_run=False)
        if result.actions_taken:
            print(
                f"[reconcile] Resume 開始時: {len(result.actions_taken)} 件のステップを"
                f" pending に戻しました",
                file=sys.stderr,
            )
            for action in result.actions_taken:
                print(f"  - {action}", file=sys.stderr)
    finally:
        try:
            await client.stop()
        except Exception:  # pragma: no cover
            pass


def _restore_config_from_state(config: SDKConfig, state: RunState) -> None:
    """`state.config_snapshot` から `SDKConfig` のフィールドを復元する。

    Phase 3 (Resume): 別プロセス / 別 PC で resume する際、保存時の実行設定を
    復元する。ただし以下のフィールドは復元しない（snapshot にも含まれない）:
      - github_token : 機密情報。環境変数から再取得する。
      - repo         : テナント混入防止。環境変数 REPO から再取得する。
      - cli_path / cli_url : 環境固有のため現在値を尊重。
      - mcp_servers  : API キーや絶対パスを含むため現在の `config` を尊重。

    また、既に呼び出し側で明示的に設定された値（`generate_run_id()` を経由せず
    `SDKConfig(run_id=...)` のように直接渡された値）は **上書きされる**。
    Resume の本質は「保存時の実行コンテキストの厳密な再現」であるため。

    snapshot に存在しないキーや、`SDKConfig` 側に存在しない属性は無視する
    （schema バージョン差を吸収するため）。
    """
    snapshot = state.config_snapshot or {}
    if not snapshot:
        return
    for key, value in snapshot.items():
        if not hasattr(config, key):
            continue
        try:
            setattr(config, key, value)
        except (AttributeError, TypeError):
            # frozen フィールドや setter 制約がある場合はスキップ
            continue
    # run_id は確実に復元する（snapshot に含まれていなくても state.run_id を採用）
    config.run_id = state.run_id


def _build_step_complete_callback(
    state: RunState,
    console: Console,
) -> Callable[[StepResult], None]:
    """`DAGExecutor.on_step_complete` 用のコールバックを構築する。

    Phase 3 (Resume): 各ステップの完了/失敗/スキップ/blocked を state.json に
    永続化する。コールバック内の例外は warn のみで握り潰し、DAG 実行を
    止めない（state I/O 失敗で実行成果物を犠牲にしない）。
    """
    def _on_step_complete(result: StepResult) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            kwargs: Dict[str, Any] = {
                "completed_at": now,
                "elapsed_seconds": float(result.elapsed or 0.0),
            }
            if result.skipped:
                kwargs["status"] = "skipped"
                kwargs["skip_reason"] = result.reason or "inactive"
            elif result.state == "blocked":
                kwargs["status"] = "blocked"
                kwargs["skip_reason"] = result.reason or "blocked"
            elif result.success:
                kwargs["status"] = "completed"
                kwargs["error_summary"] = None
            else:
                kwargs["status"] = "failed"
                kwargs["error_summary"] = (
                    (result.error or "")[:500] if result.error else None
                )
            # Fork-integration (T2.2): retry_count / forked_session_id を state へ反映
            retry_count = getattr(result, "retry_count", 0)
            if isinstance(retry_count, int) and retry_count > 0:
                kwargs["retry_count"] = retry_count
            forked_sid = getattr(result, "forked_session_id", None)
            if forked_sid:
                kwargs["forked_session_id"] = forked_sid
            state.update_step(result.step_id, **kwargs)
        except Exception as exc:  # pragma: no cover - I/O 例外パスは E2E で確認
            console.warning(
                f"state.json への step 状態更新に失敗しました (step={result.step_id}): {exc}"
            )

    return _on_step_complete


def _build_fork_kpi_logger(config: SDKConfig) -> Any:
    """`DAGExecutor` 用の ForkKPILogger を構築する。

    Fork-integration (T2.4/T2.6): フラグ OFF 時は `None` を返してロガー呼び出し自体を
    完全スキップする（M5 対応: no-op 呼び出しのオーバーヘッド削減）。
    """
    if not bool(getattr(config, "fork_on_retry", False)):
        return None
    try:
        from .fork_kpi_logger import ForkKPILogger
    except ImportError:  # pragma: no cover
        from fork_kpi_logger import ForkKPILogger  # type: ignore[no-redef]
    return ForkKPILogger(
        enabled=True,
        run_id=getattr(config, "run_id", "") or "unknown",
    )

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
# Work IQ を入力ソースとして任意追加できるよう、既定は qa + original-docs のマルチ値（カンマ区切り）。
_AKM_DEFAULT_SOURCES = "qa,original-docs"
_AKM_DEFAULT_TARGET_FILES = "qa/*.md"
# sources マルチ値の正規化順序（出力順は固定）
_AKM_SOURCES_ORDER = ("workiq", "qa", "original-docs")
_AKM_SOURCES_VALID = frozenset(_AKM_SOURCES_ORDER)
_AQOD_DEFAULT_TARGET_SCOPE = "original-docs/"
_AQOD_DEFAULT_DEPTH = "standard"

# ARD デフォルト値
_ARD_DEFAULT_SURVEY_PERIOD_YEARS = 30
_ARD_DEFAULT_TARGET_REGION = "グローバル全体"
_ARD_DEFAULT_ANALYSIS_PURPOSE = "中長期成長戦略の立案"


def _normalize_akm_sources(value) -> list:
    """AKM の sources 値を正規化された list[str] に変換する。

    受理形式:
    - 文字列（カンマ / 空白区切り）または list[str]/tuple/set
    - 個別値: ``qa`` / ``original-docs`` / ``workiq`` / ``both``（後方互換 → ``qa,original-docs``）
    - 空入力 / None → 既定 ``["qa", "original-docs"]``

    Returns:
        順序固定 ``[workiq, qa, original-docs]`` のうち含まれるものを並べた ``list[str]``。
        不明なトークンは無視される。
    """
    if value is None:
        tokens: list = []
    elif isinstance(value, (list, tuple, set)):
        tokens = [str(v) for v in value]
    else:
        import re as _re
        tokens = [t for t in _re.split(r"[,\s]+", str(value)) if t]

    result_set: set = set()
    for token in tokens:
        t = token.strip().lower()
        if not t:
            continue
        if t == "both":
            result_set.add("qa")
            result_set.add("original-docs")
        elif t in _AKM_SOURCES_VALID:
            result_set.add(t)
        # 不明トークンは無視（後方互換性のため例外を出さない）

    if not result_set:
        return ["qa", "original-docs"]

    return [s for s in _AKM_SOURCES_ORDER if s in result_set]


def _default_akm_target_files(sources) -> str:
    """AKM の sources に応じた ``target_files`` 既定値を返す。

    ``sources`` は文字列（カンマ区切り）または ``list[str]`` を受け付ける。
    Work IQ のみ、または非 Work IQ ソースが複数の場合は既定パターンなし（``""``）。
    """
    normalized = _normalize_akm_sources(sources)
    non_workiq = [s for s in normalized if s != "workiq"]
    if len(non_workiq) == 1:
        if non_workiq[0] == "qa":
            return _AKM_DEFAULT_TARGET_FILES
        if non_workiq[0] == "original-docs":
            return "original-docs/*"
    # 0 件（workiq のみ）または複数 → 既定パターンなし
    return ""


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
    if wf.id == "ard" and not steps_value:
        target_business = args.get("target_business", "") or ""
        steps_value = ["2", "3"] if target_business.strip() else ["1", "2", "3"]
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
        # sources は内部表現を「正規化済みカンマ区切り文字列」に統一する。
        # 受理形式は qa / original-docs / workiq / both（後方互換）/ それらのカンマ・空白区切り組合せ。
        _raw_sources = args.get("sources") or _AKM_DEFAULT_SOURCES
        _normalized_sources = _normalize_akm_sources(_raw_sources)
        params["sources"] = ",".join(_normalized_sources)
        params["target_files"] = args.get("target_files") or _default_akm_target_files(_normalized_sources)
        params["custom_source_dir"] = args.get("custom_source_dir") or ""
        force_refresh = args.get("force_refresh", None)
        params["force_refresh"] = False if force_refresh is None else force_refresh
        params["enable_auto_merge"] = args.get("enable_auto_merge", False)
        # Work IQ 取り込み対象 Dxx を正規化リストとして params にも反映する。
        # config 側ヘルパで文字列／リストを ``["D01","D04",...]`` に正規化。
        _ingest_dxx_raw = args.get("workiq_akm_ingest_dxx")
        if _ingest_dxx_raw is not None:
            try:
                from .config import _parse_workiq_akm_ingest_dxx as _parse_dxx
            except ImportError:
                from config import _parse_workiq_akm_ingest_dxx as _parse_dxx  # type: ignore[no-redef]
            if isinstance(_ingest_dxx_raw, (list, tuple, set)):
                _joined = ",".join(str(x) for x in _ingest_dxx_raw)
            else:
                _joined = str(_ingest_dxx_raw)
            params["workiq_akm_ingest_dxx"] = _parse_dxx(_joined)
    elif wf.id == "aqod":
        params["target_scope"] = args.get("target_scope") or _AQOD_DEFAULT_TARGET_SCOPE
        params["depth"] = args.get("depth") or _AQOD_DEFAULT_DEPTH
        params["focus_areas"] = args.get("focus_areas") or ""
    elif wf.id == "ard":
        from datetime import date
        params["company_name"] = args.get("company_name", "") or ""
        params["target_business"] = args.get("target_business", "") or ""
        params["ard_workiq_enabled"] = bool(args.get("ard_workiq_enabled", False))
        params["survey_base_date"] = args.get("survey_base_date") or date.today().isoformat()
        params["survey_period_years"] = args.get("survey_period_years") or _ARD_DEFAULT_SURVEY_PERIOD_YEARS
        params["target_region"] = args.get("target_region") or _ARD_DEFAULT_TARGET_REGION
        params["analysis_purpose"] = args.get("analysis_purpose") or _ARD_DEFAULT_ANALYSIS_PURPOSE
        attached = args.get("attached_docs")
        params["attached_docs"] = attached if attached else []
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

# 全 Step プロンプト先頭に注入する言語ルール。
# 思考プロセス（reasoning / chain-of-thought）も日本語で行わせるため、
# モデルが reasoning を開始する前に確実に届くよう、Step プロンプト本文の
# 冒頭に常時付与する。固有名詞・コマンド・パス等は英語のまま許容する。
_LANGUAGE_DIRECTIVE_JA: str = (
    "## 出力言語ルール（最優先・思考プロセス含む）\n"
    "- 思考プロセス（reasoning / chain-of-thought / 内部独白）も日本語で行うこと。\n"
    "- ツール委譲の意図表明・計画の自問自答・推論の途中経過も日本語で記述する。\n"
    "- 固有名詞・コマンド名・ファイルパス・コード識別子・引用文は英語のままで構わない。\n"
    "\n"
)


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
                return _LANGUAGE_DIRECTIVE_JA + prompt
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
    return _LANGUAGE_DIRECTIVE_JA + fallback


# -----------------------------------------------------------------------
# 既存成果物検出・再利用コンテキスト
# -----------------------------------------------------------------------

def _collect_file_samples(root: str, limit: int = 10) -> list:
    """指定ディレクトリから最大 limit 件のファイルパスを収集して返す。

    大規模リポジトリでの全列挙を避けるため、limit 件見つかった時点で走査を打ち切る。
    呼び出し側で artifact 種別に応じた limit を渡すこと（Sub-1 A-3）:
      - "src" → 50（実装ファイルは数が多い）
      - "test" → 30（テストはやや少ない）
      - その他 → 10（catalog など）
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

    # ソースコードの検出（上限付き早期終了。Sub-1 A-3: 種別別動的上限）
    src_files = _collect_file_samples("src", limit=50)
    if src_files:
        existing["src_files"] = src_files

    # テストコードの検出（上限付き早期終了。Sub-1 A-3: 種別別動的上限）
    test_files = _collect_file_samples("test", limit=30)
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


def _check_required_skills_for_active_steps(
    wf,
    workflow_id: str,
    active_steps: Set[str],
    console: "Console",
) -> dict:
    """active step に required_skills があれば、存在する skill 名かを事前検証する。"""
    try:
        try:
            from .skill_resolver import get_required_skills_for_step, validate_skill_names
        except ImportError:
            from skill_resolver import get_required_skills_for_step, validate_skill_names  # type: ignore[no-redef]
    except Exception as exc:
        console.warning(
            f"Skill resolver の読み込みに失敗したため skill 事前検証をスキップします: {exc}"
        )
        return {"should_abort": False, "error": None}

    missing_rows: List[Dict[str, Any]] = []
    for step in wf.steps:
        if step.is_container or step.id not in active_steps:
            continue

        declared = list(getattr(step, "required_skills", []) or [])
        required = get_required_skills_for_step(
            workflow_id=workflow_id,
            step_id=step.id,
            step_declared_required=declared,
        )
        if not required:
            continue

        missing, _resolved, suggestions = validate_skill_names(required)
        for skill_name in missing:
            missing_rows.append(
                {
                    "step_id": step.id,
                    "step_title": step.title,
                    "skill": skill_name,
                    "suggestions": suggestions.get(skill_name, []),
                }
            )

    if not missing_rows:
        return {"should_abort": False, "error": None}

    lines = ["必須 skill が見つかりません。以下を修正してください:"]
    for row in missing_rows:
        suggest = row.get("suggestions") or []
        suggest_text = f" (候補: {', '.join(suggest)})" if suggest else ""
        lines.append(
            f"  - Step.{row['step_id']} {row['step_title']}: {row['skill']}{suggest_text}"
        )

    msg = "\n".join(lines)
    console.error(msg)
    return {"should_abort": True, "error": msg}


def collect_workflow_output_paths(workflow_id: str) -> List[str]:
    """ワークフローの全ステップの output_paths を集約して返す。

    全 StepDef を走査して output_paths を収集し、重複除去・順序維持したリストを返す。
    output_paths が未定義または空の Step が混在しても安全に動作する。
    ワークフローが見つからない場合は空リストを返す。

    Self-Improve の target scope 解決（run_workflow 内）から呼び出されるほか、
    テストから直接インポートして利用することができる。
    """
    wf = get_workflow(workflow_id)
    if wf is None:
        return []
    seen: dict = {}
    result: List[str] = []
    for step in wf.steps:
        paths = getattr(step, "output_paths", None) or []
        for p in paths:
            if p not in seen:
                seen[p] = True
                result.append(p)
    return result


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
    # Sub-2 (A-2): step 種別を consumed_artifacts から推定し、再利用ルール文を簡素化する
    step_kind = _infer_step_kind(step.consumed_artifacts)
    step_reuse_context = _build_reuse_context(filtered_artifacts, step_kind=step_kind)
    result = ((config.additional_prompt or "") + step_reuse_context).strip() or None
    # Wave 2-3: context injection サイズを記録（デバッグ可視化）
    _injection_chars = len(step_reuse_context)
    if _injection_chars > 0:
        import logging as _logging
        _logging.getLogger(__name__).debug(
            "Step.%s context_injection: artifacts=%s chars=%d kind=%s",
            step.id, list(filtered_artifacts.keys()), _injection_chars, step_kind,
        )
    return result


# Sub-2 (A-2): step 種別ごとの再利用ルール文（既存成果物再利用のヒント）。
# キー = step_kind、値 = 末尾に付与する箇条書きルール文の行リスト。
# default はワークフロー単位 (`_build_reuse_context` 直接呼び出し) で使用される長文。
_REUSE_RULES_BY_KIND: Dict[str, List[str]] = {
    "catalog": [
        "**再利用ルール:**",
        "- Catalog ファイルは既存エントリを保持したまま、新規エントリのみ追加する",
        "- 既存のテーブル構造・列順を維持する",
    ],
    "tests": [
        "**再利用ルール:**",
        "- テスト仕様書・テストコードは既存分を維持し、新規分のみ追加する",
        "- 既存テストの命名規則・assertion 形式に従う",
    ],
    "code": [
        "**再利用ルール:**",
        "- 既存コード構造（ディレクトリ・モジュール分割）を尊重し、差分のみを更新する",
        "- 公開 API のシグネチャ変更は最小限に抑える",
    ],
    "docs": [
        "**再利用ルール:**",
        "- 既存ドキュメント構造を尊重し、差分のみを更新する",
        "- セクション見出し・順序を維持する",
    ],
    "default": [
        "**再利用ルール:**",
        "- 既存のドキュメント/コード構造を尊重し、差分のみを更新する",
        "- 新規 APP-ID に関する追記は、既存ファイルのフォーマットに従う",
        "- Catalog ファイルは既存エントリを保持したまま、新規エントリを追加する",
        "- テスト仕様書・テストコードは既存分を維持し、新規分のみ追加する",
        "- `docs/catalog/app-catalog.md` の既存アプリケーション定義を参照し、一貫性を保つ",
    ],
}


def _infer_step_kind(consumed_artifacts: Optional[List[str]]) -> str:
    """consumed_artifacts キーから step 種別を推定する (Sub-2 A-2)。

    判定ルール（優先順位）:
      1. test_files / test_specs を主成分 → "tests"
      2. src_files を主成分 → "code"
      3. knowledge / doc_generated を主成分 → "docs"
      4. *_catalog / *_specs / *_matrix を主成分 → "catalog"
      5. それ以外（混在含む） → "default"

    「主成分」= 該当種別のキーが consumed_artifacts の半数以上を占める、
    または consumed_artifacts が空でも種別不明として "default" を返す。
    """
    if not consumed_artifacts:
        return "default"
    keys = set(consumed_artifacts)
    test_keys = {"test_files", "test_specs", "test_strategy"} & keys
    code_keys = {"src_files"} & keys
    doc_keys = {"knowledge", "doc_generated"} & keys
    catalog_keys = {k for k in keys if k.endswith("_catalog") or k.endswith("_specs") or k.endswith("_matrix")}

    total = len(keys)
    half = (total + 1) // 2  # 半数（切り上げ）

    if len(test_keys) >= half and test_keys:
        return "tests"
    if len(code_keys) >= half and code_keys:
        return "code"
    if len(doc_keys) >= half and doc_keys:
        return "docs"
    if len(catalog_keys) >= half and catalog_keys:
        return "catalog"
    return "default"


def _build_reuse_context(existing_artifacts: dict, step_kind: str = "default") -> str:
    """既存成果物の再利用コンテキストをプロンプトに追加する文字列を生成。

    Sub-2 (A-2): step_kind 引数で再利用ルール文を切替可能。
    後方互換: step_kind 省略時は "default"（既存の長文ルール）を使う。
    """
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

    rules = _REUSE_RULES_BY_KIND.get(step_kind, _REUSE_RULES_BY_KIND["default"])
    lines.append("")
    lines.extend(rules)

    return "\n".join(lines)


async def _prefetch_workiq(
    config: SDKConfig,
    query: str,
    console: Console,
    timeout: float = 1200.0,
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
    timeout: float = 1200.0,
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
            # Phase 2 (Resume): 決定論的 session_id を付与
            "session_id": _orchestrator_session_id(
                config, "orchestrator", suffix="workiq-prefetch"
            ),
        }
        # Auto 選択時は明示的に DEFAULT_MODEL + reasoning_effort=high を指定する。
        # CLI ユーザー設定 (~/.copilot/settings.json) で `claude-opus-4.7-high` 等の
        # reasoning_effort 固定バリアントが設定されていると、SDK 経由で渡した
        # reasoning_effort が CAPI 側で不整合となり 400 エラーになるため、
        # 無印バリアントを明示してユーザー設定を上書きする。
        if config.model and config.model != MODEL_AUTO_VALUE:
            _session_opts["model"] = config.model
        else:
            _session_opts["model"] = DEFAULT_MODEL
            _session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT
        session = await _create_session_with_auto_reasoning_fallback(client, _session_opts)

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
            # Phase 2 (Resume): 決定論的 session_id を付与
            "session_id": _orchestrator_session_id(
                config, "akm-verify", suffix="workiq"
            ),
        }
        # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避
        if config.model and config.model != MODEL_AUTO_VALUE:
            session_opts["model"] = config.model
        else:
            session_opts["model"] = DEFAULT_MODEL
            session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT

        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)

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


async def _run_akm_workiq_ingest(
    config: SDKConfig,
    console: Console,
    workiq_report_paths: Set[str],
) -> None:
    """AKM Pre-DAG: Work IQ を入力ソースとして ``knowledge/Dxx-*.md`` を起票・差分更新する。

    ``_run_akm_workiq_verification`` が DAG 後の妥当性検証であるのに対し、本関数は
    AKM メイン DAG の **前段** で実行される取り込みフェーズ。Work IQ から取得した
    情報のみを根拠として Dxx ファイルを新規作成または差分更新する。後段の
    qa/original-docs DAG ステージが Dxx を更にマージ更新する。

    対象 Dxx は ``config.workiq_akm_ingest_dxx`` で絞り込み、空（既定）の場合は全件。

    失敗時は warning で継続する（後段の qa/original-docs DAG を止めない）。
    """
    try:
        from .workiq import (
            build_workiq_mcp_config, query_workiq,
            get_workiq_prompt_template, save_workiq_result,
            is_workiq_error_response, is_workiq_available,
            WORKIQ_MCP_SERVER_NAME, _escape_workiq_sandbox_tags,
            build_akm_workiq_query_targets_from_files,
            render_akm_workiq_query_target,
        )
    except ImportError:
        from workiq import (  # type: ignore[no-redef]
            build_workiq_mcp_config, query_workiq,
            get_workiq_prompt_template, save_workiq_result,
            is_workiq_error_response, is_workiq_available,
            WORKIQ_MCP_SERVER_NAME, _escape_workiq_sandbox_tags,
            build_akm_workiq_query_targets_from_files,
            render_akm_workiq_query_target,
        )

    if not is_workiq_available():
        console.warning(
            "Work IQ が利用できないため AKM Work IQ 取り込みをスキップします。"
        )
        return

    # マスターリストから D クラス対象一覧を構築（既定で全件 = include_confirmed=True）。
    try:
        targets = build_akm_workiq_query_targets_from_files(include_confirmed=True)
    except Exception as build_err:
        console.warning(
            f"AKM Work IQ 取り込み: マスターリスト読み込み失敗: {build_err}"
        )
        return

    if not targets:
        console.warning(
            "AKM Work IQ 取り込み: マスターリストから D クラス対象が抽出できませんでした。スキップします。"
        )
        return

    # Dxx 絞り込みフィルタ（``config.workiq_akm_ingest_dxx`` が非空の場合のみ適用）。
    dxx_filter = list(getattr(config, "workiq_akm_ingest_dxx", []) or [])
    if dxx_filter:
        filter_set = {d.strip().upper() for d in dxx_filter if d}
        targets = [t for t in targets if t.d_class_id.upper() in filter_set]
        if not targets:
            console.warning(
                f"AKM Work IQ 取り込み: 指定された Dxx ({','.join(dxx_filter)}) "
                "に該当する対象がマスターリストに見つかりませんでした。スキップします。"
            )
            return

    console.event(
        f"AKM Work IQ 取り込み: {len(targets)} 件の D クラスを処理します"
        + (f"（Dxx フィルタ: {','.join(dxx_filter)}）" if dxx_filter else "（全件）")
    )

    # SDK / セッション準備（_run_akm_workiq_verification と同方式）。
    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため AKM Work IQ 取り込みをスキップします。"
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

    queried_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            "session_id": _orchestrator_session_id(
                config, "akm-ingest", suffix="workiq"
            ),
        }
        if config.model and config.model != MODEL_AUTO_VALUE:
            session_opts["model"] = config.model
        else:
            session_opts["model"] = DEFAULT_MODEL
            session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT

        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)

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
                                f"AKM Work IQ 取り込み: MCP サーバー状態 = {mcp_status}。取り込みをスキップします。"
                            )
                            return
                        wiq_found = True
                        break
                if not wiq_found:
                    console.warning(
                        f"AKM Work IQ 取り込み: MCP サーバー '{WORKIQ_MCP_SERVER_NAME}' が見つかりません。"
                        "取り込みをスキップします。"
                    )
                    return
            except Exception as mcp_err:
                console.warning(
                    f"AKM Work IQ 取り込み: MCP ステータス確認失敗: {mcp_err}"
                )
                return

            console.event("AKM Work IQ 取り込み: MCP 接続確認完了")

            knowledge_dir = Path("knowledge")
            for idx, target in enumerate(targets):
                d_class_id = target.d_class_id  # "D01" 等
                console.event(
                    f"  [{idx + 1}/{len(targets)}] {d_class_id} ({target.document_name}) を取り込み中..."
                )

                # Work IQ クエリ生成: マスターリスト由来の構造化対象情報を target_content として埋め込む。
                target_content = render_akm_workiq_query_target(target)
                km_prompt_template = get_workiq_prompt_template(
                    "km", config.workiq_prompt_km
                )
                workiq_query = km_prompt_template.format(target_content=target_content)
                console.workiq_prompt(
                    workiq_query,
                    label=f"Work IQ プロンプト [{d_class_id} KM ingest]",
                )

                try:
                    workiq_result = await query_workiq(
                        session, workiq_query,
                        timeout=config.workiq_per_question_timeout,
                    )
                except Exception as wiq_err:
                    console.warning(
                        f"  {d_class_id}: Work IQ クエリ失敗: {wiq_err}"
                    )
                    error_count += 1
                    if idx < len(targets) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                console.workiq_response(
                    workiq_result or "",
                    label=f"Work IQ 応答 [{d_class_id} KM ingest]",
                )

                # 結果を save（work IQ 補助レポートとして保存）。
                save_path = save_workiq_result(
                    config.run_id, "1", f"km-ingest-{d_class_id}",
                    workiq_result or "",
                    is_error=is_workiq_error_response(workiq_result or ""),
                    base_dir=config.workiq_draft_output_dir or "qa",
                )
                if save_path:
                    workiq_report_paths.add(str(save_path))

                queried_count += 1

                # 応答判定。
                if not workiq_result or not workiq_result.strip():
                    console.event(f"  {d_class_id}: Work IQ 応答なし。スキップします。")
                    skipped_count += 1
                    if idx < len(targets) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                if is_workiq_error_response(workiq_result):
                    console.warning(f"  {d_class_id}: Work IQ エラー応答。スキップします。")
                    skipped_count += 1
                    if idx < len(targets) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                _no_info_keywords = (
                    "関連情報なし",
                    "関連する情報は見つかりませんでした",
                    "該当する情報はありません",
                )
                if any(kw in workiq_result for kw in _no_info_keywords):
                    console.event(f"  {d_class_id}: 関連情報なし。スキップします。")
                    skipped_count += 1
                    if idx < len(targets) - 1:
                        await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)
                    continue

                # 既存ファイル状態を判定（新規作成 / 差分更新）。
                existing_files = sorted(knowledge_dir.glob(f"{d_class_id}-*.md"))
                existing_files = [
                    p for p in existing_files
                    if not p.name.endswith("-ChangeLog.md")
                ]
                if existing_files:
                    existing_path = existing_files[0]
                    try:
                        existing_content = existing_path.read_text(encoding="utf-8")
                    except OSError as read_err:
                        console.warning(
                            f"  {d_class_id}: 既存ファイル読み取り失敗: {read_err}"
                        )
                        existing_content = "(読み取り失敗)"
                    if len(existing_content) > _AKM_WORKIQ_DXX_MAX_CONTENT_LENGTH:
                        existing_content = (
                            existing_content[:_AKM_WORKIQ_DXX_MAX_CONTENT_LENGTH]
                            + "\n...(truncated)"
                        )
                    existing_status = (
                        f"既存ファイル: `{existing_path.as_posix()}`（差分更新）\n\n"
                        f"=== 既存内容 ===\n{existing_content}\n=== 既存内容ここまで ==="
                    )
                else:
                    existing_status = (
                        f"既存ファイル: なし（`knowledge/{d_class_id}-*.md` を新規作成する）"
                    )

                console.event(
                    f"  {d_class_id}: Work IQ 関連情報あり → ファイル"
                    + ("更新" if existing_files else "新規作成")
                    + "を実行"
                )

                update_prompt = AKM_WORKIQ_INGEST_PROMPT.format(
                    d_class_id=d_class_id,
                    document_name=target.document_name,
                    dxx_target_info=target_content,
                    existing_status=existing_status,
                    workiq_result=_escape_workiq_sandbox_tags(workiq_result),
                )

                try:
                    update_response = await session.send_and_wait(
                        update_prompt, timeout=config.timeout_seconds
                    )
                    update_output = _extract_text(update_response)
                    if update_output:
                        updated_count += 1
                        console.event(f"  {d_class_id}: 取り込み完了")
                    else:
                        console.warning(f"  {d_class_id}: 取り込み応答が空でした")
                except Exception as upd_err:
                    console.warning(f"  {d_class_id}: ファイル取り込み失敗: {upd_err}")
                    error_count += 1

                if idx < len(targets) - 1:
                    await asyncio.sleep(_AKM_WORKIQ_QUERY_INTERVAL)

        finally:
            await session.disconnect()
    except Exception as exc:
        console.warning(f"AKM Work IQ 取り込み中にエラーが発生しました: {exc}")
        error_count += 1
    finally:
        await client.stop()

    console.event(
        f"AKM Work IQ 取り込み完了: クエリ={queried_count}, 取り込み={updated_count}, "
        f"スキップ={skipped_count}, エラー={error_count}"
    )


async def _run_ard_workiq_usecase(
    config: SDKConfig,
    console: Console,
    params: dict,
    step2_issue_num: Optional[int],
    repo: str,
    token: str,
) -> None:
    """ARD Step.2: Work IQ 経由でユースケースカタログの参照情報を取得し、Step.2 Issue にコメントする。

    AKM パターン（verification + 通常実行）に倣い、Work IQ 結果を Issue コメントとして注入する。
    その後、通常の Custom Agent（Arch-ARD-UseCaseCatalog）が当該 Issue を参照しながら実行される。

    Args:
        config: SDKConfig インスタンス。
        console: Console インスタンス。
        params: ワークフローパラメータ（company_name 等）。
        step2_issue_num: Step.2 の Sub-Issue 番号。None の場合は GitHub へのコメント投稿をスキップし、
            Work IQ 結果はローカルログのみに出力する（Issue 未作成の dry_run なし実行等）。
        repo: リポジトリ（owner/repo 形式）。
        token: GitHub トークン。
    """
    try:
        from .workiq import (
            build_workiq_mcp_config, query_workiq,
            is_workiq_available, is_workiq_error_response,
            _escape_workiq_sandbox_tags,
        )
    except ImportError:
        from workiq import (  # type: ignore[no-redef]
            build_workiq_mcp_config, query_workiq,
            is_workiq_available, is_workiq_error_response,
            _escape_workiq_sandbox_tags,
        )

    if not is_workiq_available():
        console.warning("Work IQ 利用条件未充足のため通常実行に委譲 (is_workiq_available=False)")
        return

    company_name = (params.get("company_name", "") or "").strip()
    company_name_for_prompt = company_name or "未指定"

    # docs/company-business-requirement.md を読み込む
    business_req_path = Path("docs/company-business-requirement.md")
    if business_req_path.exists():
        try:
            business_requirement_content = business_req_path.read_text(encoding="utf-8")
        except Exception as read_err:
            console.warning(f"ARD Work IQ: docs/company-business-requirement.md 読み取り失敗: {read_err}")
            business_requirement_content = "(読み取り失敗)"
    else:
        console.warning("ARD Work IQ: docs/company-business-requirement.md が存在しません。")
        business_requirement_content = "(ファイルなし)"

    # Work IQ クエリ文を構築
    if company_name:
        workiq_query = (
            f"対象企業「{company_name}」のユースケース作成に役立つ情報を教えてください。"
            f"業務プロセス、顧客ニーズ、既存システム、利用シナリオ等に関する情報があればお知らせください。"
        )
    else:
        workiq_query = (
            "対象企業名は未指定です。"
            "汎用的なユースケース作成に役立つ情報として、業務プロセス、顧客ニーズ、"
            "既存システム、利用シナリオ等の観点で参照情報を提示してください。"
        )

    # SDK / セッション準備
    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning("Copilot SDK が利用できないため ARD Work IQ ユースケース取得をスキップします。")
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

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            "session_id": _orchestrator_session_id(
                config, "ard-workiq", suffix="usecase"
            ),
        }
        # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避
        if config.model and config.model != MODEL_AUTO_VALUE:
            session_opts["model"] = config.model
        else:
            session_opts["model"] = DEFAULT_MODEL
            session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT

        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)

        try:
            workiq_result = await query_workiq(
                session, workiq_query,
                timeout=config.workiq_per_question_timeout,
            )
        except Exception as wiq_err:
            console.warning(f"ARD Work IQ クエリ失敗: {wiq_err}")
            workiq_result = None
        finally:
            await session.disconnect()
    except Exception as exc:
        console.warning(f"ARD Work IQ セッション作成失敗: {exc}")
        workiq_result = None
    finally:
        await client.stop()

    if not workiq_result or not workiq_result.strip():
        console.warning("ARD Work IQ: 応答が空のためスキップします。")
        return

    if is_workiq_error_response(workiq_result):
        console.warning("ARD Work IQ: エラー応答を受信しました。スキップします。")
        return

    # ARD_WORKIQ_USECASE_PROMPT を構築して Step.2 Issue にコメント
    # プロンプトインジェクション対策: workiq_result と business_requirement_content をエスケープ
    safe_workiq_result = _escape_workiq_sandbox_tags(workiq_result) or workiq_result
    safe_biz_req = _escape_workiq_sandbox_tags(business_requirement_content) or business_requirement_content
    comment_body = ARD_WORKIQ_USECASE_PROMPT.format(
        business_requirement_content=safe_biz_req,
        company_name=company_name_for_prompt,
        workiq_result=safe_workiq_result,
    )

    if step2_issue_num and repo and token:
        try:
            post_comment(
                issue_num=step2_issue_num,
                body=comment_body,
                repo=repo,
                token=token,
            )
            console.event(
                f"ARD Work IQ: ユースケース参照情報を Step.2 Issue #{step2_issue_num} にコメントしました。"
            )
        except Exception as post_err:
            console.warning(f"ARD Work IQ: Issue コメント投稿失敗: {post_err}")
    else:
        console.event(
            "ARD Work IQ: Step.2 Issue 番号が不明のため、コメント投稿をスキップします（Work IQ 結果はローカルログのみ）。"
        )
        console.workiq_response(workiq_result, label="ARD Work IQ ユースケース参照情報")


# --- ARD: Step 1 → Step 2 bridging hook ---
def _select_recommendation(
    recommendations: list,
    config: SDKConfig,
    params: dict,
    console: Console,
):
    """ARD の Strategic Recommendation を 1 件選択する。"""
    if not recommendations:
        raise ValueError("recommendations must not be empty")

    explicit_id = (params.get("target_recommendation_id", "") or "").strip().upper()
    if explicit_id:
        for rec in recommendations:
            if str(getattr(rec, "id", "")).upper() == explicit_id:
                return rec
        console.warning(
            f"target_recommendation_id='{explicit_id}' に一致する SR がないため、先頭 SR を採用します。"
        )
        return recommendations[0]

    if getattr(config, "unattended", False):
        return recommendations[0]

    options = [f"{r.id}: {r.title}" for r in recommendations]
    selected_index = console.menu_select(
        "Step 2 で使用する Strategic Recommendation を選択してください",
        options,
        default_index=0,
    )
    if not (0 <= selected_index < len(recommendations)):
        return recommendations[0]
    return recommendations[selected_index]


async def _generate_target_business_from_sr(
    selected_sr,
    md_path: Path,
    config: SDKConfig,
    params: dict,
    console: Console,
) -> str:
    """選択 SR + Step1 出力から target_business 説明文を生成する。"""
    sr_id = str(getattr(selected_sr, "id", "SR-UNKNOWN"))
    sr_title = str(getattr(selected_sr, "title", "")).strip() or sr_id

    if config.dry_run:
        return f"[dry-run] target_business based on {sr_id}: {sr_title}"

    try:
        business_requirement_content = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        console.warning(f"Step 1 出力の読み込みに失敗したため SR タイトルで代替します: {exc}")
        return sr_title

    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning("Copilot SDK が利用できないため SR タイトルで代替します。")
        return sr_title

    if config.cli_url:
        sdk_cfg = ExternalServerConfig(url=config.cli_url)
    else:
        sdk_cfg = SubprocessConfig(
            cli_path=config.cli_path,
            github_token=config.resolve_token() or None,
            log_level="error",
            cli_args=config.cli_args,
        )

    client = CopilotClient(config=sdk_cfg)
    await client.start()
    try:
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "session_id": _orchestrator_session_id(
                config,
                "ard-target-business",
                suffix=sr_id.lower().replace(" ", "-"),
            ),
        }
        # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避
        if config.model and config.model != MODEL_AUTO_VALUE:
            session_opts["model"] = config.model
        else:
            session_opts["model"] = DEFAULT_MODEL
            session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT
        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)
        try:
            prompt = ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT.format(
                company_name=params.get("company_name", ""),
                selected_recommendation_id=sr_id,
                selected_recommendation_title=sr_title,
                business_requirement_content=business_requirement_content,
            )
            response = await session.send_and_wait(prompt, timeout=config.timeout_seconds)
            generated = (_extract_text(response) or "").strip()
            if generated:
                return generated
            console.warning("target_business 生成結果が空のため SR タイトルで代替します。")
            return sr_title
        finally:
            await session.disconnect()
    except Exception as exc:
        console.warning(f"target_business 生成に失敗したため SR タイトルで代替します: {exc}")
        return sr_title
    finally:
        await client.stop()


async def _on_ard_step1_completed(
    *,
    config: SDKConfig,
    params: dict,
    console: Console,
) -> None:
    """ARD Step 1 完了直後: SR 抽出・選択・target_business 生成。"""
    if (params.get("target_business", "") or "").strip():
        console.status("target_business が指定済みのため、SR からの自動生成をスキップします。")
        return

    output_path = Path("docs/company-business-requirement.md")
    if not output_path.exists():
        console.warning("Step 1 出力ファイルが見つかりません。Step 2 は既存 target_business で継続します。")
        return

    try:
        from .ard_recommendations import parse_recommendations, annotate_with_ids
    except ImportError:
        from ard_recommendations import parse_recommendations, annotate_with_ids  # type: ignore[no-redef]

    parsed = parse_recommendations(output_path)
    recommendations = annotate_with_ids(output_path)
    if not recommendations:
        recommendations = parsed
    if not recommendations:
        console.warning("Strategic Recommendations が抽出できなかったため target_business は変更しません。")
        return

    selected_sr = _select_recommendation(
        recommendations=recommendations,
        config=config,
        params=params,
        console=console,
    )
    params["target_business"] = await _generate_target_business_from_sr(
        selected_sr=selected_sr,
        md_path=output_path,
        config=config,
        params=params,
        console=console,
    )


async def _resolve_target_business_paths(params: dict, console: Console) -> None:
    """target_business がパス指定なら context テキストへ展開する。"""
    raw = params.get("target_business", "") or ""
    try:
        from .ard_target_business_resolver import is_path_like, resolve, to_context_text
    except ImportError:
        from ard_target_business_resolver import is_path_like, resolve, to_context_text  # type: ignore[no-redef]

    if not is_path_like(raw):
        return
    resolved = resolve(raw, base_dir=Path.cwd())
    params["target_business"] = to_context_text(resolved)
    console.status(
        f"target_business をパス展開しました: {len(resolved.files)} ファイル, "
        f"{resolved.total_size_bytes} bytes"
    )




async def run_workflow(
    workflow_id: str,
    params: Optional[dict] = None,
    config: Optional[SDKConfig] = None,
    *,
    resume_state: Optional[RunState] = None,
    session_name: Optional[str] = None,
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

    Phase 3 (Resume): `resume_state` を渡すと、その RunState の completed/skipped
    ステップを事前登録した上で残ステップだけを実行する。`config.run_id` と
    `params` は resume_state の値で上書きされる（途中までの実行コンテキストを
    厳密に再現するため）。

    Phase 4 (Resume): `session_name` を渡すと、新規 RunState 作成時の
    `session_name` フィールドに設定する。Wizard でユーザーが入力した名前を
    Resume 一覧の表示に使用するため。`resume_state` と併用された場合は
    既存の `session_name` を尊重し、`session_name` 引数は無視される。

    Returns:
        結果情報の dict:
          workflow_id, completed, failed, skipped, elapsed_total,
          code_review_error, pr_number, root_issue_num, working_branch, error
    """
    if config is None:
        config = SDKConfig()

    # Phase 3 (Resume): resume_state があれば config と params を復元する。
    # Resume 時は run_id を強制上書きし、params も snapshot を真とする
    # （途中までの実行コンテキストを破壊しないため）。
    if resume_state is not None:
        _restore_config_from_state(config, resume_state)
        if params is None:
            params = {}
        merged_params: dict = dict(resume_state.params_snapshot or {})
        merged_params.update(params)
        params = merged_params

        # Phase 5 (Resume 2-layer txn): SDK セッション実体との整合性チェック。
        # state_only な session_id は SDK 側で失われており、そのまま resume すると
        # `resume_session` 失敗 → `create_session` フォールバックの 2 回呼び出しが
        # 発生する。事前に pending に戻して create 経路に直接送ることで効率化する。
        # 失敗は warn のみで実行を継続（reconcile が無くても従来の fallback で救済可能）。
        try:
            await _auto_reconcile_on_resume(resume_state, config)
        except Exception as exc:  # pragma: no cover - top-level guard
            print(f"WARN: resume 開始時の auto-reconcile で例外: {exc}", file=sys.stderr)

    # run_id が未設定の場合、ワークフロー実行開始時に1回生成する（並列安全性）
    if not config.run_id:
        config.run_id = generate_run_id()

    console = Console(
        verbose=config.verbose,
        quiet=config.quiet,
        show_stream=config.show_stream,
        show_reasoning=config.show_reasoning,
        verbosity=config.verbosity,
        no_color=getattr(config, "no_color", None),
        screen_reader=getattr(config, "screen_reader", False),
        timestamp_style=getattr(config, "timestamp_style", "prefix"),
        final_only=getattr(config, "final_only", False),
    )
    # ADR-0002 D-3: 構造化ログに run_id を含めるため Console に伝搬する
    try:
        console.set_run_id(config.run_id)
    except Exception:
        pass
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
    if config.auto_qa:
        _phases.append("実行計画 → DAG 実行（事前 QA + Work IQ → 各ステップ実行）")
    else:
        _phases.append("実行計画 → DAG 実行")
    # AKM Work IQ 取り込み（DAG **前** に挿入。Work IQ 検証 (DAG 後) とは別フェーズ）。
    if workflow_id == "akm" and config.is_workiq_akm_ingest_enabled() and not config.dry_run:
        _akm_ingest_idx = next(
            (i for i, ph in enumerate(_phases) if "DAG 実行" in ph), len(_phases) - 1
        )
        _phases.insert(_akm_ingest_idx, "AKM Work IQ 取り込み")
    if workflow_id == "akm" and config.is_workiq_akm_review_enabled() and not config.dry_run:
        _phases.append("AKM Work IQ 検証")
    if workflow_id == "ard" and config.is_workiq_qa_enabled() and not config.dry_run:
        # ARD Work IQ は pre-DAG（Issue 作成後・Step.2 実行前）に挿入するため _phases への追加も DAG の前
        _ard_wiq_phase_idx = next(
            (i for i, ph in enumerate(_phases) if "DAG 実行" in ph), len(_phases) - 1
        )
        _phases.insert(_ard_wiq_phase_idx, "ARD Work IQ ユースケース参照")
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
    # ARD: グループ ID (1/2/3) を実 Step ID (1,1.1,1.2 / 2 / 3.1,3.2,3.3) に展開する。
    # Wizard / CLI 側はグループ ID を返す契約のため、フィルタ前にここで展開する。
    # 既に実 Step ID が直接渡された場合は fallback `[sid]` で素通し（後方互換）。
    if workflow_id == "ard" and selected_step_ids:
        _ARD_GROUP_MAP = {
            "1": ["1", "1.1", "1.2"],
            "2": ["2"],
            "3": ["3.1", "3.2", "3.3"],
        }
        _expanded: List[str] = []
        for _sid in selected_step_ids:
            _expanded.extend(_ARD_GROUP_MAP.get(_sid, [_sid]))
        _seen: Set[str] = set()
        selected_step_ids = [s for s in _expanded if not (s in _seen or _seen.add(s))]
    active_steps: Set[str] = resolve_selected_steps(wf, selected_step_ids)
    _ard_force_serial = (
        workflow_id == "ard"
        and "1" in active_steps
        and "2" in active_steps
        and not (effective_params.get("target_business", "") or "").strip()
    )
    effective_max_parallel = 1 if _ard_force_serial else config.max_parallel
    wf_for_dag = wf
    if _ard_force_serial:
        try:
            wf_for_dag = copy.deepcopy(wf)
            _step2 = wf_for_dag.get_step("2")
            if _step2 is not None and "1" not in (_step2.depends_on or []):
                _step2.depends_on = list(_step2.depends_on or []) + ["1"]
        except Exception as exc:
            console.warning(f"ARD 直列DAGの構築に失敗したため通常DAGで続行します: {exc}")
            wf_for_dag = wf
            _ard_force_serial = False
            effective_max_parallel = config.max_parallel

    console.event(f"実行対象ステップ数: {len(active_steps)}")
    if _ard_force_serial:
        console.event("ARD bridge mode: Step 1 → Step 2 → Step 3 を直列実行します。")
    console.phase_end(p, _total_phases, "ステップフィルタリング", time.time() - phase_start)

    dry_run_plan = build_dag_plan(
        wf_for_dag,
        active_steps,
        max_parallel=effective_max_parallel,
        max_parallel_source="ard-serial" if _ard_force_serial else "config",
    )

    # --- dry_run: 実行計画表示のみ ---
    if config.dry_run:
        _print_dry_run_plan(wf_for_dag, active_steps, config, console, dry_run_plan)
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

    # `workiq_report_paths` は ARD/AKM Work IQ 連携で共有するため Issue 作成前に初期化する。
    # （後段の Step 実行・DAG 後 verify でも同一インスタンスへ追記される）
    workiq_report_paths: Set[str] = set()

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

    # --- 4.6. ARD Work IQ ユースケース参照（Issue 作成後・Step.2 実行前）---
    # Step.2 の Issue にコメントを注入しておくことで、Custom Agent が参照できるようにする。
    _ard_workiq_enabled = bool(effective_params.get("ard_workiq_enabled", False))
    if (
        workflow_id == "ard"
        and "2" in active_steps
        and (_ard_workiq_enabled or config.is_workiq_qa_enabled())
        and not config.dry_run
    ):
        try:
            from .workiq import is_workiq_available
        except ImportError:
            from workiq import is_workiq_available  # type: ignore[no-redef]

        if is_workiq_available():
            p = _next_phase()
            phase_start_ard_wiq = time.time()
            console.phase_start(p, _total_phases, "ARD Work IQ ユースケース参照")
            _ard_step2_issue_num = step_issue_map.get("2") if step_issue_map else None
            _ard_repo = config.repo or ""
            _ard_token = config.resolve_token() or ""
            try:
                await _run_ard_workiq_usecase(
                    config=config,
                    console=console,
                    params=effective_params,
                    step2_issue_num=_ard_step2_issue_num,
                    repo=_ard_repo,
                    token=_ard_token,
                )
            except Exception as ard_wiq_exc:
                console.warning(
                    f"ARD Work IQ ユースケース参照中にエラーが発生しました（無視して続行）: {ard_wiq_exc}"
                )
            console.phase_end(p, _total_phases, "ARD Work IQ ユースケース参照", time.time() - phase_start_ard_wiq)
        else:
            console.warning("Work IQ 利用条件未充足のため通常実行に委譲 (is_workiq_available=False)")

    # --- 4.7. AKM Work IQ 取り込み（Issue 作成後・DAG 実行前）---
    # `sources` に `workiq` が含まれる or `workiq_akm_ingest_enabled=True` で実行される。
    # 後段の qa/original-docs を扱う DAG ステージが、本フェーズで生成・更新された
    # knowledge/Dxx-*.md を差分マージ更新する前提。失敗時は warning で継続。
    if (
        workflow_id == "akm"
        and config.is_workiq_akm_ingest_enabled()
        and not config.dry_run
    ):
        p = _next_phase()
        phase_start_akm_ingest = time.time()
        console.phase_start(p, _total_phases, "AKM Work IQ 取り込み")
        try:
            await _run_akm_workiq_ingest(
                config=config,
                console=console,
                workiq_report_paths=workiq_report_paths,
            )
        except Exception as akm_ingest_exc:
            console.warning(
                f"AKM Work IQ 取り込み中にエラーが発生しました（無視して続行）: {akm_ingest_exc}"
            )
        console.phase_end(p, _total_phases, "AKM Work IQ 取り込み", time.time() - phase_start_akm_ingest)

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

    # --- Phase 3 (Resume): RunState の確保と running 状態への遷移 ---
    # resume_state が None なら新規作成し、既存があれば最新の active_steps を反映する。
    # いずれの場合も status="running" にして即座に save する（クラッシュ時の resume の起点）。
    if resume_state is None:
        # Phase 4 (Resume): wizard / CLI から渡された session_name を優先し、
        # 未指定なら default_session_name() でワークフロー表示名 + 時刻を生成する。
        try:
            from .run_state import default_session_name
        except ImportError:
            from run_state import default_session_name  # type: ignore[no-redef]
        _wf_disp = _WORKFLOW_DISPLAY_NAMES.get(workflow_id, workflow_id)
        _effective_session_name = (session_name or "").strip() or default_session_name(
            workflow_id=workflow_id,
            params=effective_params,
            workflow_display_name=_wf_disp,
        )
        resume_state = RunState.new(
            run_id=config.run_id,
            workflow_id=workflow_id,
            config=config,
            params=effective_params,
            selected_step_ids=sorted(active_steps),
            session_name=_effective_session_name,
        )
    else:
        # 既存 resume_state を再開: active_steps の差分を吸収する
        # （DAG 構成変更や新規 step 追加にも追随）
        resume_state.selected_step_ids = sorted(active_steps)
        for sid in active_steps:
            if sid not in resume_state.step_states:
                resume_state.step_states[sid] = StepState(status="pending")
    resume_state.status = "running"
    resume_state.pause_reason = None
    try:
        resume_state.save()
    except Exception as exc:
        console.warning(f"state.json の初期保存に失敗しました: {exc}")

    # Phase 6 (Resume 2-layer txn): StepRunner に RunJournal を注入し、
    # 各 phase 完了時の checkpoint marker を `work/runs/<run_id>/journal.jsonl` に
    # 記録する。失敗は warn のみで実行を継続（runner 側 _record_checkpoint で握る）。
    try:
        try:
            from .run_journal import RunJournal
            from .run_state import sync_intent_log_from_journal
        except ImportError:
            from run_journal import RunJournal  # type: ignore[no-redef]
            from run_state import sync_intent_log_from_journal  # type: ignore[no-redef]
        _journal_run_dir = resume_state.state_path.parent
        _step_journal: Optional[Any] = RunJournal(_journal_run_dir)
        # resume_state に journal_path を記録（v0.5 fields）
        resume_state.journal_path = str(_step_journal.path.relative_to(_journal_run_dir.parent)) \
            if _journal_run_dir.parent in _step_journal.path.parents \
            else str(_step_journal.path)
        # v1.0.3 (Major #15): journal の pending intent を state.intent_log に同期。
        # クラッシュ復帰後の Resume 開始時に未完了 intent の可視化に役立つ。
        sync_intent_log_from_journal(resume_state, _step_journal)
        try:
            resume_state.save()
        except Exception:  # pragma: no cover
            pass
    except Exception as exc:  # pragma: no cover - 防御的 fallback
        console.warning(f"RunJournal 初期化に失敗（checkpoint 記録なしで続行）: {exc}")
        _step_journal = None

    runner = StepRunner(
        config=config,
        console=console,
        resume_state=resume_state,
        journal=_step_journal,
    )

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

    _skill_check = _check_required_skills_for_active_steps(
        wf=wf,
        workflow_id=workflow_id,
        active_steps=active_steps,
        console=console,
    )
    if _skill_check["should_abort"]:
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "elapsed_total": time.time() - start_total,
            "error": _skill_check["error"],
        }

    # ステップ → プロンプト の事前構築
    step_prompts: Dict[str, str] = {}
    # `workiq_report_paths` は 4.5 で初期化済み（ARD/AKM Work IQ 連携と共有）。
    # Wave 2-3 / 2-7: context injection サイズの観測カウンタ
    _w2_none_steps: int = 0          # consumed_artifacts=None のステップ数
    _w2_injection_total: int = 0     # context injection 合計文字数
    _w2_injection_max: int = 0       # context injection 最大文字数（1 step あたり）
    _w2_injection_phase_breakdown: Dict[str, int] = {}  # context injection フェーズ別内訳
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
        _phase = step.id.split(".", 1)[0]
        _w2_injection_phase_breakdown[_phase] = _w2_injection_phase_breakdown.get(_phase, 0) + _injection_chars
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
        wf_for_dag,
        active_steps,
        step_prompts=step_prompts,
        max_parallel=effective_max_parallel,
        max_parallel_source="ard-serial" if _ard_force_serial else "config",
    )

    # --- 6-7. DAGExecutor 実行 ---
    async def run_step_fn(
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
    ) -> bool:
        _prompt = prompt

        # --- ARD: Step 1 → Step 2 bridging hook ---
        if workflow_id == "ard" and step_id == "2":
            await _resolve_target_business_paths(effective_params, console)
            step = wf.get_step(step_id)
            if step is not None:
                step_additional = _compute_step_additional_prompt(
                    step=step,
                    existing_artifacts=existing_artifacts,
                    config=config,
                    base_additional_prompt=effective_additional_prompt,
                )
                _prompt = _build_step_prompt(
                    step=step,
                    params=effective_params,
                    root_issue_num=root_issue_num,
                    render_template_fn=render_template,
                    wf=wf,
                    additional_prompt=step_additional,
                    execution_mode=execution_mode,
                )

        success = await runner.run_step(
            step_id=step_id,
            title=title,
            prompt=_prompt,
            custom_agent=custom_agent,
            workflow_id=workflow_id,
        )
        if workflow_id == "ard" and step_id == "1" and success:
            await _on_ard_step1_completed(
                config=config,
                params=effective_params,
                console=console,
            )
        return success

    executor = DAGExecutor(
        workflow=wf_for_dag,
        run_step_fn=run_step_fn,
        active_step_ids=active_steps,
        max_parallel=effective_max_parallel,
        console=console,
        step_prompts=step_prompts,
        dag_plan=dag_plan,
        on_step_complete=_build_step_complete_callback(resume_state, console),
        repo_root=Path(__file__).resolve().parent.parent,
        # Fork-integration (T2.6/T2.8): フィーチャフラグ off （既定）で旧挙動と完全一致
        fork_on_retry=bool(getattr(config, "fork_on_retry", False)),
        fork_kpi_logger=_build_fork_kpi_logger(config),
        on_fork_retry=runner.set_fork_index,
    )

    # Phase 3 (Resume): 完了/スキップ済みステップを事前登録し、再実行を回避する。
    # DAG の next_steps 走査が completed/skipped を「依存解決済み」とみなすため、
    # ここで状態を流し込むだけで残ステップから自動で再開できる。
    _resume_completed_count = 0
    _resume_skipped_count = 0
    for sid, st in resume_state.step_states.items():
        if sid not in active_steps:
            continue
        if st.status == "completed":
            executor.completed.add(sid)
            _resume_completed_count += 1
        elif st.status == "skipped":
            executor.skipped.add(sid)
            _resume_skipped_count += 1
    if _resume_completed_count or _resume_skipped_count:
        _remaining = len(active_steps) - _resume_completed_count - _resume_skipped_count
        console.event(
            f"  ↻ Resume mode: 完了済み={_resume_completed_count} / "
            f"スキップ済み={_resume_skipped_count} / "
            f"残り実行={_remaining}"
        )

    # 実行計画を事前表示
    waves = executor.compute_waves()
    if waves:
        console.execution_plan(waves, len(active_steps), effective_max_parallel)

    # Phase 6 (Resume): Ctrl+R で graceful pause を可能にする。
    # KeybindMonitor は別スレッドで stdin を監視し、Ctrl+R 検出時に pause_event を
    # 立てる。メインループは executor.execute() と pause_event.wait() を競合させ、
    # pause が先に発火したら executor をキャンセルして state を paused に保存する。
    # 監視は実行中のみ有効にし、必ず finally で stop する（端末モード復元）。
    pause_event = asyncio.Event()
    monitor = KeybindMonitor()  # __init__ で env 判定（pytest / non-tty で自動無効化）

    if monitor.enabled:
        console.event(
            "  💡 実行中に Ctrl+R で state を保存して中断できます "
            "（再開は次回起動時の Resume プロンプトから）"
        )

    async def _on_ctrl_r() -> None:
        """Ctrl+R 検出時のハンドラー（asyncio ループ上で実行される）。"""
        if pause_event.is_set():
            return  # 二重押し防止
        pause_event.set()
        try:
            console.event(
                "\n  ⏸ Ctrl+R 検出: 実行中ステップの完了を待たず state を保存して中断します..."
            )
        except Exception:  # pragma: no cover
            pass

    monitor.register(KEY_CTRL_R, _on_ctrl_r)

    paused_by_user: bool = False
    try:
        monitor.start()
        executor_task = asyncio.create_task(executor.execute(), name="hve-executor")
        pause_task = asyncio.create_task(pause_event.wait(), name="hve-pause-wait")
        try:
            done, _pending = await asyncio.wait(
                [executor_task, pause_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            # 親（asyncio.run の cancel 等）から送られた場合は通常の cancel として伝播
            executor_task.cancel()
            pause_task.cancel()
            raise

        if pause_task in done and not executor_task.done():
            paused_by_user = True
            executor_task.cancel()
            try:
                await executor_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                # キャンセル / 実行中例外いずれも握り潰す（state 保存を優先）
                pass
            results = dict(getattr(executor, "_results", {}) or {})
        else:
            # 通常完了（または executor 側で例外）
            pause_task.cancel()
            try:
                await pause_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            results = await executor_task
    finally:
        monitor.stop()

    # Phase 6 (Resume): Ctrl+R で中断された場合は state を paused にして早期 return。
    if paused_by_user:
        # 実行中だったステップは failed にマークする（次回 resume で再実行対象）
        for sid in sorted(executor.running):
            try:
                resume_state.update_step(
                    sid,
                    status="failed",
                    error_summary="ユーザーにより Ctrl+R で中断",
                )
            except Exception as exc:  # pragma: no cover
                console.warning(
                    f"中断ステップ {sid} の state 更新に失敗しました: {exc}"
                )
        resume_state.status = "paused"
        resume_state.pause_reason = "ctrl+r"
        try:
            resume_state.save()
        except Exception as exc:
            console.warning(f"state.json の paused 保存に失敗しました: {exc}")

        completed_ids_paused = sorted(executor.completed)
        failed_ids_paused = sorted(executor.failed)
        skipped_ids_paused = sorted(executor.skipped)
        console.event(
            f"  ✅ state.json 保存完了: {resume_state.state_path}"
        )
        console.event(
            f"  📊 中断時点: 完了={len(completed_ids_paused)} / "
            f"失敗={len(failed_ids_paused)} / "
            f"スキップ={len(skipped_ids_paused)} / "
            f"残り={len(active_steps) - len(completed_ids_paused) - len(skipped_ids_paused)}"
        )
        console.phase_end(p, _total_phases, "実行計画 → DAG 実行 (paused)", time.time() - phase_start_dag)
        return {
            "workflow_id": workflow_id,
            "paused": True,
            "run_id": resume_state.run_id,
            "completed": completed_ids_paused,
            "failed": failed_ids_paused,
            "skipped": skipped_ids_paused,
            "blocked": [],
            "elapsed_total": time.time() - phase_start_dag,
            "code_review_error": None,
            "pr_number": None,
            "root_issue_num": None,
            "working_branch": None,
            "error": None,
            "aqod_validation": None,
        }

    # Phase 3 (Resume): DAG 実行完了後に status を確定する。
    # 失敗が 1 件でもあれば failed、全て成功 / skip ならば completed とする。
    # この後の Self-Improve や PR 作成は status に影響しない（あくまで DAG の達成度を反映）。
    resume_state.status = "failed" if executor.failed else "completed"
    try:
        resume_state.save()
    except Exception as exc:
        console.warning(f"state.json の最終保存に失敗しました: {exc}")
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

    # --- ARD Work IQ ユースケース参照は Phase 4.6（DAG 実行前）に移動済み ---

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

        _workflow_outputs = collect_workflow_output_paths(workflow_id)
        _workflow_default = _si_scope_defaults.get(workflow_id, "")

        # target_scope が明示指定されている場合はそれを優先する。
        # 未指定かつ output_paths が集約できた場合は scope 文字列は不要（パス直指定）。
        # output_paths が空の場合（output_paths 未設定ワークフロー）は workflow_default へフォールバック。
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
    _emit_context_injection_metrics(
        none_steps=_w2_none_steps,
        total_chars=_w2_injection_total,
        max_chars=_w2_injection_max,
        self_improve_scope=_w2_si_scope,
        phase_breakdown=_w2_injection_phase_breakdown,
        console=console,
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
        "w2_injection_phase_breakdown": _w2_injection_phase_breakdown,
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
        _review_model = config.get_review_model()
        _review_session_opts: Dict[str, Any] = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            # Phase 2 (Resume): 決定論的 session_id を付与
            "session_id": _orchestrator_session_id(
                config, "code-review", suffix="agent"
            ),
        }
        # Auto 経路では DEFAULT_MODEL を明示して CLI ユーザー設定の -high バリアント上書きを回避
        if _review_model and _review_model != MODEL_AUTO_VALUE:
            _review_session_opts["model"] = _review_model
        else:
            _review_session_opts["model"] = DEFAULT_MODEL
            _review_session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT
        session = await _create_session_with_auto_reasoning_fallback(client, _review_session_opts)
        if _review_model != config.model:
            console.event(f"Code Review Agent モデル: {_review_model}")

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
