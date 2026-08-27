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
    2. Issue 作成（Root + Sub-Issue。指定時は新規 Root を Copilot cloud agent へ割当）
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
import ntpath
import os
import shutil
import subprocess
import sys
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple, Union
from urllib.parse import quote

# -----------------------------------------------------------------------
# 内部モジュールのインポート（相対 / 絶対 の両方に対応）
# -----------------------------------------------------------------------
try:
    from .config import SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS, to_wire_model
    from .console import Console, timestamp_prefix
    from .prompt_loader import load_prompt_file
    from .prompts import (
        CODE_REVIEW_AGENT_FIX_PROMPT,
        CODE_REVIEW_CLI_PROMPT,
        AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT,
        AKM_WORKIQ_INGEST_PROMPT,
        ARD_WORKIQ_USECASE_PROMPT,
        ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT,
    )
    from .runner import StepRunner, _is_review_fail, _extract_text, _apply_fanout_prompt_template, _apply_repository_mcp_scope
    from .dag_executor import DAGExecutor, StepResult
    from .dag_planner import build_dag_plan
    from .run_state import DEFAULT_SESSION_ID_PREFIX, make_session_id
    from . import run_progress
    from . import approval
    from . import rework
    from .orchestrator_context import OrchestratorContext
    from .mcp_io_log import McpIoLogger, attach_mcp_io_event_logger
    from .startup_preflight import (
        format_startup_preflight_errors,
        github_write_required,
        validate_startup_configuration,
    )
    from .github_title_generator import (
        GitHubTitleGenerationError,
        generate_github_title,
    )
    from . import index_refresh
except ImportError:
    from config import SDKConfig, generate_run_id, SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS, to_wire_model  # type: ignore[no-redef]
    from console import Console, timestamp_prefix  # type: ignore[no-redef]
    from prompt_loader import load_prompt_file  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        CODE_REVIEW_AGENT_FIX_PROMPT,
        CODE_REVIEW_CLI_PROMPT,
        AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT,
        AKM_WORKIQ_INGEST_PROMPT,
        ARD_WORKIQ_USECASE_PROMPT,
        ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT,
    )
    from runner import StepRunner, _is_review_fail, _extract_text, _apply_fanout_prompt_template, _apply_repository_mcp_scope  # type: ignore[no-redef]
    from dag_executor import DAGExecutor, StepResult  # type: ignore[no-redef]
    from dag_planner import build_dag_plan  # type: ignore[no-redef]
    from run_state import DEFAULT_SESSION_ID_PREFIX, make_session_id  # type: ignore[no-redef]
    from orchestrator_context import OrchestratorContext  # type: ignore[no-redef]
    from mcp_io_log import McpIoLogger, attach_mcp_io_event_logger  # type: ignore[no-redef]
    from startup_preflight import (  # type: ignore[no-redef]
        format_startup_preflight_errors,
        github_write_required,
        validate_startup_configuration,
    )
    from github_title_generator import (  # type: ignore[no-redef]
        GitHubTitleGenerationError,
        generate_github_title,
    )
    import index_refresh  # type: ignore[no-redef]

# -----------------------------------------------------------------------
# hve 内部モジュール（旧 .github/cli/ から移植済み）
# -----------------------------------------------------------------------
from hve.workflow_registry import (  # noqa: F401
    ADI_DEFAULT_DEPTH as _ADI_DEFAULT_DEPTH,
    ADI_DEFAULT_TARGET_SCOPE as _ADI_DEFAULT_TARGET_SCOPE,
    AKM_DEFAULT_SOURCES as _AKM_DEFAULT_SOURCES,
    AKM_DEFAULT_TARGET_FILES as _AKM_DEFAULT_TARGET_FILES,
    ARD_DEFAULT_ANALYSIS_PURPOSE as _ARD_DEFAULT_ANALYSIS_PURPOSE,
    ARD_DEFAULT_GROUP_IDS,
    ARD_DEFAULT_SURVEY_PERIOD_YEARS as _ARD_DEFAULT_SURVEY_PERIOD_YEARS,
    ARD_DEFAULT_TARGET_REGION as _ARD_DEFAULT_TARGET_REGION,
    get_local_phase_step_ids,
    get_workflow,
    WorkflowDef,
    list_workflows,
)
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
    assign_copilot_agent,
    create_issue,
    get_issue,
    link_sub_issue,
    post_comment,
    create_pull_request,
    get_pull_request,
    list_issue_comments,
    list_check_runs_for_ref,
)
from hve.app_arch_filter import resolve_app_arch_scope
from hve.cloud_session import (
    acquire_cloud_session_slot,
    apply_cloud_session_auto_routing,
    attach_cloud_session_event_logger,
    attach_cloud_session_limiter_release,
    build_cloud_session_options,
    is_policy_blocked_error,
    resolve_cloud_repository,
    should_use_cloud_session,
    wait_for_cloud_session_ready,
)


# -----------------------------------------------------------------------
# 定数
# -----------------------------------------------------------------------

_VALID_WORKFLOWS = [wf.id for wf in list_workflows()]


# -----------------------------------------------------------------------
# SDK ヘルパー
# -----------------------------------------------------------------------
def _create_copilot_client_from_config(
    config: SDKConfig,
    *,
    log_level: str = "error",
    cli_args: Optional[List[str]] = None,
) -> Any:
    """SDK 1.0.0 RuntimeConnection API で CopilotClient を生成する。"""
    try:
        from .copilot_client_factory import create_copilot_client
    except ImportError:  # pragma: no cover
        from copilot_client_factory import create_copilot_client  # type: ignore[no-redef]

    return create_copilot_client(
        cli_path=config.cli_path,
        cli_url=config.cli_url,
        github_token=config.resolve_token() or None,
        log_level=log_level,
        cli_args=cli_args,
    )


async def _create_session_with_auto_reasoning_fallback(
    client: Any,
    session_opts: Dict[str, Any],
    *,
    config: Optional[SDKConfig] = None,
    step_id: Optional[str] = None,
    subtask_kind: Optional[str] = None,
    console: Optional[Any] = None,
    workflow_id: Optional[str] = None,
) -> Any:
    """create_session を呼び出し、SDK が reasoning_effort を未サポートの場合は除外して再試行する。

    SDK バージョン < 0.3.0 互換のための防御。reasoning_effort が opts に
    含まれない場合は単純な create_session 呼び出しと等価。

    検出条件は Python の組み込み TypeError 文言
    (`got an unexpected keyword argument`) と `reasoning_effort` の両方が
    含まれる場合に限定する。

    併せて、Skill レジストリへ `.github/skills` を登録する
    (`skill_directories` / `enable_config_discovery`) を呼び出し側で
    未指定の場合のみ自動注入する。CLI のスキル発見は深さ 1
    (`<root>/<name>/SKILL.md`) のみ走査するため、`skill_directories`
    には root に加えて各カテゴリ直下サブフォルダも列挙する。SDK が
    当該引数を未サポートの場合は TypeError を契機に剥がして再試行する。
    """
    from pathlib import Path as _Path

    _opts_with_skills = dict(session_opts)
    # context_tier: ユーザー設定 (SDKConfig.context_tier) を create_session へ伝播する。
    # truthy のときのみ注入し、呼び出し側が明示済みなら尊重する。
    if config is not None and getattr(config, "context_tier", None) and "context_tier" not in _opts_with_skills:
        _opts_with_skills["context_tier"] = config.context_tier
    _cloud_injected = False
    _had_streaming_before_cloud = "streaming" in _opts_with_skills
    _streaming_before_cloud = _opts_with_skills.get("streaming")
    if config is not None and "cloud" not in _opts_with_skills:
        _cloud_opts = build_cloud_session_options(
            config,
            step_id=step_id,
            subtask_kind=subtask_kind,
        )
        if _cloud_opts is not None:
            _opts_with_skills["cloud"] = _cloud_opts
            _cloud_injected = True
            _opts_with_skills["streaming"] = True
        elif should_use_cloud_session(config, step_id=step_id, subtask_kind=subtask_kind) and console is not None:
            owner, name, _branch = resolve_cloud_repository(config)
            try:
                if not owner or not name:
                    console.warning(
                        "Cloud Session repository owner/name が解決できないため、ローカルセッションにフォールバックします。"
                    )
                else:
                    console.warning(
                        "Cloud Session 型が現在の Copilot SDK で利用できないため、ローカルセッションにフォールバックします。"
                    )
            except Exception:
                pass
    if "skill_directories" not in _opts_with_skills:
        _skills_dir = _Path.cwd() / ".github" / "skills"
        if _skills_dir.is_dir():
            # CLI のスキル発見は深さ 1 (`<root>/<name>/SKILL.md`) のみ走査するため、
            # root に加えて各カテゴリ直下サブフォルダも列挙し、ネスト配置スキル
            # (`<root>/<category>/<name>/SKILL.md`) を発見可能にする。
            # SKILL.md 不在のサブフォルダを渡しても無害（CLI 側で無視される）。
            _opts_with_skills["skill_directories"] = [str(_skills_dir)] + [
                str(p) for p in sorted(_skills_dir.iterdir()) if p.is_dir()
            ]
    # FR-CLI-76 (v2.51): 呼び出し側が MCP を指定していないときは、リポジトリ宣言分だけを
    # 公開してワークスペース / ユーザースコープ / プラグイン由来の自動探索を止める。
    # 縮約の実装は runner の単一ヘルパーに限る（FR-MAINT-07）。
    if (
        "mcp_servers" not in _opts_with_skills
        and "enable_config_discovery" not in _opts_with_skills
    ):
        _apply_repository_mcp_scope(_opts_with_skills, workflow_id=workflow_id)
    if "enable_config_discovery" not in _opts_with_skills:
        _opts_with_skills["enable_config_discovery"] = True

    async def _attempt(opts: Dict[str, Any]) -> Any:
        limiter = None
        try:
            if "cloud" in opts and config is not None:
                limiter = await acquire_cloud_session_slot(config)
            session = await client.create_session(**opts)
            if "cloud" in opts:
                attach_cloud_session_event_logger(
                    session,
                    step_id=step_id,
                    subtask_kind=subtask_kind,
                )
                await wait_for_cloud_session_ready(session)
                if limiter is not None:
                    attach_cloud_session_limiter_release(session, limiter)
                    limiter = None
            return session
        except TypeError as exc:
            if limiter is not None:
                limiter.release_slot()
            msg = str(exc)
            if "unexpected keyword argument" not in msg:
                raise
            # Skill 系 / config discovery を未サポートの SDK に対するフォールバック
            for _kw in ("skill_directories", "enable_config_discovery", "disabled_skills", "custom_agent", "cloud", "context_tier"):
                if _kw in msg and _kw in opts:
                    if _kw == "cloud" and console is not None:
                        try:
                            console.warning(
                                "Cloud Session は現在の Copilot SDK で未サポートのため、ローカルセッションにフォールバックします。"
                            )
                        except Exception:
                            pass
                    _stripped = {k: v for k, v in opts.items() if k != _kw}
                    if _kw == "cloud" and _cloud_injected:
                        if _had_streaming_before_cloud:
                            _stripped["streaming"] = _streaming_before_cloud
                        else:
                            _stripped.pop("streaming", None)
                    return await _attempt(_stripped)
            if "reasoning_effort" in msg and "reasoning_effort" in opts:
                _stripped = {k: v for k, v in opts.items() if k != "reasoning_effort"}
                return await _attempt(_stripped)
            raise
        except Exception as exc:
            if limiter is not None:
                limiter.release_slot()
            if is_policy_blocked_error(exc) and console is not None:
                try:
                    console.warning(
                        "Cloud Session が組織ポリシーでブロックされました（policy_blocked）。リトライせず停止します。"
                    )
                except Exception:
                    pass
                raise
            if "cloud" in opts and _cloud_injected:
                if console is not None:
                    try:
                        console.warning(
                            f"Cloud Session の準備に失敗したため、ローカルセッションにフォールバックします ({type(exc).__name__})。"
                        )
                    except Exception:
                        pass
                stripped = {k: v for k, v in opts.items() if k != "cloud"}
                if _had_streaming_before_cloud:
                    stripped["streaming"] = _streaming_before_cloud
                else:
                    stripped.pop("streaming", None)
                return await _attempt(stripped)
            raise

    return await _attempt(_opts_with_skills)


def _apply_reasoning_effort(
    session_opts: Dict[str, Any],
    config: Any,
    *,
    model_value: Optional[str] = None,
    kind: str = "main",
) -> None:
    """ユーザー指定の reasoning_effort を session_opts へ適用する。

    優先順位:
      1. ユーザーが明示指定した reasoning_effort (config.{kind}_reasoning_effort) を適用。
      2. 未指定 → 何もしない（SDK/サーバ既定動作。Auto モデル時はサーバ側 Auto Model
         Selection がモデル毎に適切な effort を選ぶ）。

    Args:
        session_opts: SDK create_session に渡す dict (in-place 更新)。
        config: SDKConfig 互換 (reasoning_effort / review_reasoning_effort / qa_reasoning_effort 属性を参照)。
        model_value: 評価対象のモデル文字列（後方互換のため受け取るが現実装では未使用）。
        kind: "main" | "review" | "qa"。
    """
    if kind == "review":
        user_effort = getattr(config, "review_reasoning_effort", None)
    elif kind == "qa":
        user_effort = getattr(config, "qa_reasoning_effort", None)
    else:
        user_effort = getattr(config, "reasoning_effort", None)

    if user_effort:
        session_opts["reasoning_effort"] = user_effort


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
# orchestrator レベルの SDK セッション ID ヘルパー
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
# `_AKM_DEFAULT_SOURCES` / `_AKM_DEFAULT_TARGET_FILES` と ADI / ARD の既定値は
# workflow_registry からの alias import（FR-MAINT-07 / TBD-27）。
# sources マルチ値の正規化順序（出力順は固定）
_AKM_SOURCES_ORDER = ("workiq", "qa", "original-docs")
_AKM_SOURCES_VALID = frozenset(_AKM_SOURCES_ORDER)


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
            return "docs-original/*"
    # 0 件（workiq のみ）または複数 → 既定パターンなし
    return ""


def _normalize_adi_target_scope(value: Any) -> str:
    """ADIの対象スコープを安全なPOSIX相対ディレクトリへ正規化する。

    空値は ``docs-original/`` とし、同ディレクトリまたは配下だけを許可する。
    絶対パス、drive path、親参照、NUL、prefix衝突はfail-closedで拒否する。
    """
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        return _ADI_DEFAULT_TARGET_SCOPE
    normalized = raw.replace("\\", "/")
    if (
        "\x00" in normalized
        or normalized.startswith("/")
        or bool(ntpath.splitdrive(normalized)[0])
    ):
        raise ValueError(
            "ADI target_scope は docs-original/ 配下のリポジトリ相対パスで指定してください"
        )

    parts: List[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("ADI target_scope に親ディレクトリ参照 '..' は指定できません")
        parts.append(part)
    if not parts or parts[0] != "docs-original":
        raise ValueError("ADI target_scope は docs-original/ またはその配下だけを指定できます")
    return "/".join(parts).rstrip("/") + "/"


# -----------------------------------------------------------------------
# パラメータ収集（非対話モード対応）
# -----------------------------------------------------------------------

# FR-LOCAL-SURFACE-01 (b): `WorkflowDef.params` が宣言していても、Workflow 固有の
# 収集分岐が扱っていない workflow param。直接 CLI / GUI / Prompt 版の 3 面から
# 指定できるようにするため、明示指定があるときだけ params へ投影する。
# 新しい workflow param を CLI へ出したときは、ここへ key を追加する。
_PROJECTED_WORKFLOW_PARAMS: Tuple[str, ...] = (
    "create_remote_mcp_server",
    "tdd_max_retries",
)


def project_declared_workflow_params(
    params: dict,
    workflow_id: Optional[str],
    getter: Callable[[str], Any],
) -> None:
    """registry 宣言済みで未処理の workflow param を明示指定時だけ投影する。

    直接 CLI (`_build_params`) と非対話収集 (`_collect_params_non_interactive`)
    の両方から呼ばれる単一実装（FR-MAINT-07）。

    Args:
        params: 投影先。既に値が入っている key は上書きしない。
        workflow_id: 対象 Workflow ID。registry に無ければ何もしない。
        getter: key を受け取り CLI 指定値を返す callable。未指定は None。
    """
    if not workflow_id:
        return
    try:
        wf = get_workflow(workflow_id)
    except Exception:
        return
    if wf is None:
        return
    declared = set(wf.params or ())
    for key in _PROJECTED_WORKFLOW_PARAMS:
        if key not in declared or key in params:
            continue
        value = getter(key)
        if value is not None:
            params[key] = value


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
        steps_value = list(ARD_DEFAULT_GROUP_IDS)
    params: dict = {
        "branch": args.get("branch", "main"),
        "selected_steps": steps_value,
        "skip_review": not args.get("auto_contents_review", False),
        "skip_qa": not args.get("auto_qa", False),
    }
    if args.get("resume_run"):
        params["resume_run"] = args["resume_run"]
    if args.get("approval_gates"):
        params["approval_gates"] = True
    if args.get("input_aliases"):
        params["input_aliases"] = args["input_aliases"]

    # ワークフロー固有パラメータ
    # app_ids/app_id は AAD-WEB・ASDW-WEB・ADFD・ADFDV で使用。
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
    for key in (
        "data_location",
        "data_resource_suffix",
        "data_vnet_cidr",
        "data_private_endpoint_subnet_cidr",
        "data_aci_subnet_cidr",
    ):
        if args.get(key) is not None:
            params[key] = args[key]
    if args.get("usecase_id"):
        params["usecase_id"] = args["usecase_id"]
    if args.get("app_id"):
        params["app_id"] = args["app_id"]

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
    elif wf.id == "adi":
        # 空を許容する（FR-WF-ADI-11: purpose が空のときは must を付与しない）。
        params["purpose"] = args.get("purpose") or ""
        params["target_scope"] = (
            args.get("target_scope") or _ADI_DEFAULT_TARGET_SCOPE
        )
        params["depth"] = args.get("depth") or _ADI_DEFAULT_DEPTH
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
        recommendation_id = str(args.get("target_recommendation_id") or "").strip()
        if recommendation_id:
            params["target_recommendation_id"] = recommendation_id
        attached = args.get("attached_docs")
        params["attached_docs"] = attached if attached else []
        params["include_kpi_okr"] = bool(args.get("include_kpi_okr", False))
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

    # FR-LOCAL-SURFACE-01 (b): registry が宣言していて、上の Workflow 固有
    # 分岐で未処理の param を CLI 引数から投影する。
    project_declared_workflow_params(params, wf.id, args.get)

    # Issue タイトル上書き
    if args.get("issue_title"):
        params["issue_title"] = args["issue_title"]

    return params


def _validate_asdw_data_deploy_requested_app_scope(params: Mapping[str, Any]) -> Optional[str]:
    """Reject an explicit ASDW app scope that would be normalized inconsistently."""
    selected = params.get("app_ids")
    singular = params.get("app_id")
    if selected is None or singular is None:
        return None
    if (
        type(selected) is not list
        or len(selected) != 1
        or type(selected[0]) is not str
        or type(singular) is not str
        or selected[0] != singular
    ):
        return (
            "ASDW-WEB requires --app-id to match the one selected value in "
            "--app-ids before scope filtering."
        )
    return None


def _is_non_interactive(wf, cli_args: Optional[dict]) -> bool:
    """非対話モードで実行すべきかを判定する。

    cli_args が None でなければ非対話モードとみなす。
    ワークフロー固有パラメータ（app_id, resource_group 等）は全て任意入力であり、
    未指定でも非対話モードで進める。
    """
    return cli_args is not None


def _apply_interactive_review_choice(config: SDKConfig, effective_params: dict) -> None:
    """対話ウィザードのレビュー選択を HVE Phase 3 設定へ同期する。"""
    config.auto_contents_review = not bool(
        effective_params.get("skip_review", False)
    )


# -----------------------------------------------------------------------
# Protected artifact guard（local generation checkpoint の成果物保持）
# -----------------------------------------------------------------------

# local 生成フェーズの成果物ルート。live deploy 失敗や再実行でこれらが
# 失われたまま stage / commit / push されるのを防ぐ。
PROTECTED_ARTIFACT_ROOTS: Tuple[str, ...] = ("src/api", "src/app", "src/test")

# ルート -> そのルート配下に存在した相対パス集合
ProtectedArtifactManifest = Dict[str, FrozenSet[str]]


def capture_protected_artifact_manifest(
    repo_root: Optional[Union[str, Path]] = None,
) -> ProtectedArtifactManifest:
    """保護対象ルート配下のファイル一覧を manifest として記録する。

    存在しないルートは記録しない（未生成のものを欠落扱いしないため）。
    """
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    manifest: ProtectedArtifactManifest = {}
    for protected in PROTECTED_ARTIFACT_ROOTS:
        base = root / protected
        if not base.is_dir():
            continue
        files = {
            f"{protected}/{path.relative_to(base).as_posix()}"
            for path in base.rglob("*")
            if path.is_file()
        }
        manifest[protected] = frozenset(files)
    return manifest


def check_protected_artifact_regression(
    baseline: Optional[ProtectedArtifactManifest],
    repo_root: Optional[Union[str, Path]] = None,
) -> List[str]:
    """baseline 時点の成果物が失われていないかを検査する。

    - 保護ルートの全消失
    - 成功済み local 出力（baseline に存在したファイル）の欠落

    のいずれかを検出した場合にエラーメッセージ一覧を返す。追加生成は違反にしない。
    """
    if not baseline:
        return []
    current = capture_protected_artifact_manifest(repo_root)
    errors: List[str] = []
    for protected in PROTECTED_ARTIFACT_ROOTS:
        expected = baseline.get(protected)
        if not expected:
            continue
        present = current.get(protected, frozenset())
        if not present:
            errors.append(
                f"local generation checkpoint 後に保護成果物 '{protected}' が全消失しました。"
                " stage / commit / push を中止します。"
            )
            continue
        missing = sorted(expected - present)
        if missing:
            listed = ", ".join(missing[:10])
            suffix = f" ほか {len(missing) - 10} 件" if len(missing) > 10 else ""
            errors.append(
                "local generation checkpoint 後に成功済み local 出力が欠落しました"
                f"（{protected}）: {listed}{suffix}。stage / commit / push を中止します。"
            )
    return errors

def should_retain_local_checkpoint(
    workflow_id: str,
    failed_step_ids: Any,
) -> bool:
    """live Step のみが失敗した場合に local checkpoint を保持すべきか判定する。

    local Step が 1 つでも失敗している場合、checkpoint 自体が未完成のため
    保持対象にしない。checkpoint を宣言しない workflow でも False を返す。
    """
    failed = {str(step_id) for step_id in (failed_step_ids or [])}
    if not failed:
        return False
    local_ids = get_local_phase_step_ids(workflow_id)
    if not local_ids:
        return False
    return not (failed & local_ids)


# -----------------------------------------------------------------------
# Git ヘルパー
# -----------------------------------------------------------------------

def _git_unmerged_paths() -> List[str]:
    """Git index に残っている未解決パスを返す。

    Branch 作成前の fail-fast 用。dirty worktree 全般は HVE の正常系でも
    あり得るため、unmerged entry のみを対象にする。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    paths: List[str] = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _format_git_unmerged_index_error(paths: List[str]) -> str:
    """未解決 index のユーザー向けエラーメッセージを整形する。"""
    lines = [
        "Git index に未解決コンフリクトがあります。ブランチを作成できません。",
        "以下を解決してから再実行してください:",
    ]
    lines.extend(f"  - {path}" for path in paths)
    return "\n".join(lines)


# HVE 自身のソースツリー（FR-CLI-74 / FR-CLI-75）。
# アプリ生成 run はこれらを成果物として扱わない。未コミット変更や staging 混入は
# 生成対象アプリの branch / commit / PR を汚染するため、fail-closed で拒否する。
_HVE_SOURCE_PATH_PREFIXES: Tuple[str, ...] = (
    "hve/",
    "mdq/",
    "hve-dev/",
    ".github/prompts/",
    ".github/skills/",
    ".github/scripts/",
    ".github/io-contracts/",
)

# HVE ソース配下にあるが、GUI が実行時に書き換える利用者ローカル設定であり
# 生成対象アプリの成果物にはならない。未コミットのまま run を止めると GUI を
# 起動できなくなるため FR-CLI-74 の対象外とする。FR-CLI-75 の staged 検査には
# 適用しない（強制 stage された場合は引き続き生成アプリの commit / PR への混入を拒む）。
_HVE_LOCAL_RUNTIME_PATHS: Tuple[str, ...] = (
    "hve/.settings.txt",
    "hve/.settings.txt.tmp",
)


def _normalize_repo_relative_path(path: str) -> str:
    """git 出力のパスをリポジトリ相対の POSIX 形式へ正規化する。"""
    normalized = str(path).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _parse_git_status_path(line: str) -> str:
    """``git status --porcelain`` の 1 行から対象パスを取り出す。

    rename エントリ (``R  old -> new``) は **新しい方** のパスを返す。
    空白等を含み引用符で囲まれたパスは引用符を外す。
    """
    if len(line) < 4:
        return ""
    entry = line[3:]
    if " -> " in entry:
        entry = entry.split(" -> ", 1)[1]
    entry = entry.strip()
    if len(entry) >= 2 and entry.startswith('"') and entry.endswith('"'):
        entry = entry[1:-1]
    return _normalize_repo_relative_path(entry)


def _is_hve_source_path(path: str) -> bool:
    """パスが HVE 自身のソースツリーに属するかを返す。"""
    normalized = _normalize_repo_relative_path(path)
    if not normalized:
        return False
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in _HVE_SOURCE_PATH_PREFIXES
    )


def _is_under_any_path(path: str, roots: Optional[List[str]]) -> bool:
    """``path`` が ``roots`` のいずれかと一致、またはその配下かを返す。"""
    if not roots:
        return False
    normalized = _normalize_repo_relative_path(path)
    for root in roots:
        root_normalized = _normalize_repo_relative_path(str(root)).rstrip("/")
        if not root_normalized:
            continue
        if normalized == root_normalized or normalized.startswith(root_normalized + "/"):
            return True
    return False


def _filter_hve_source_paths(
    paths: List[str],
    target_output_paths: Optional[List[str]] = None,
) -> List[str]:
    """HVE ソースパスだけを重複なく抽出する（target 出力パスは対象外）。"""
    selected: List[str] = []
    for path in paths:
        if not _is_hve_source_path(path):
            continue
        if _is_under_any_path(path, target_output_paths):
            # FR-CLI-74: 利用者が明示的に指定した target 出力パスは対象外。
            continue
        if path not in selected:
            selected.append(path)
    return selected


def _git_dirty_hve_source_paths(
    target_output_paths: Optional[List[str]] = None,
    timeout: int = 30,
    *,
    cwd: Optional[Path] = None,
) -> List[str]:
    """HVE 自身のソースに残る未コミット変更パスを返す（FR-CLI-74）。

    未追跡ファイルも対象にする。git 引数はリストで渡すため shell を経由しない
    （NFR-SEC-03）。git が利用できない / リポジトリ外で実行された場合は空リストを
    返し、ワークフロー実行そのものは阻害しない。
    ``_HVE_LOCAL_RUNTIME_PATHS``（GUI の利用者ローカル設定）は報告しない。
    """
    command = [
        "git",
        "-c",
        "core.quotePath=false",
        "status",
        "--porcelain",
        "--untracked-files=all",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    parsed = [
        parsed_path
        for parsed_path in (_parse_git_status_path(line) for line in result.stdout.splitlines())
        if parsed_path
    ]
    return [
        path
        for path in _filter_hve_source_paths(parsed, target_output_paths)
        if path not in _HVE_LOCAL_RUNTIME_PATHS
    ]


def _format_dirty_hve_source_error(paths: List[str]) -> str:
    """dirty HVE source のユーザー向けエラーメッセージを整形する（一括報告）。"""
    lines = [
        f"HVE ソースに未コミット変更があります（{len(paths)} 件）。"
        "アプリ生成 run は開始できません。",
        "以下を全て commit / revert してから再実行してください:",
    ]
    lines.extend(f"  - {path}" for path in paths)
    lines.append(
        "HVE ソースの未コミット変更は生成対象アプリの branch / commit / PR へ"
        "混入するため、この検査を無効化するオプションはありません。"
    )
    return "\n".join(lines)


def _format_staged_hve_source_error(paths: List[str]) -> str:
    """staged HVE source のユーザー向けエラーメッセージを整形する（一括報告）。"""
    lines = [
        f"HVE ソースが staging に混入しています（{len(paths)} 件）。"
        "commit / push を中止し、index を unstage します。",
        "以下を commit 対象から外してから再実行してください:",
    ]
    lines.extend(f"  - {path}" for path in paths)
    lines.append(
        "HVE ソースの変更は生成対象アプリの commit / PR へ混入するため、"
        "この検査を無効化するオプションはありません。"
    )
    return "\n".join(lines)


def _status_may_stage_hve_source(
    status_stdout: str,
    target_output_paths: Optional[List[str]] = None,
) -> bool:
    """``git add`` 後に HVE ソースが staged になり得るかを返す（FR-CLI-75）。

    ``git add .`` が stage するのは ``git status --porcelain`` が報告した変更だけ
    なので、その一覧に HVE ソース候補が 1 件も無ければ staged にもなり得ない。
    判定は ``_filter_hve_source_paths`` を再利用する（二重定義しない）。
    未追跡ディレクトリが 1 行に畳まれる場合（``?? .github/``）は配下に HVE ソースを
    含み得るため候補として扱う（fail-closed）。
    """
    paths = [
        parsed
        for parsed in (_parse_git_status_path(line) for line in status_stdout.splitlines())
        if parsed
    ]
    if _filter_hve_source_paths(paths, target_output_paths):
        return True
    return any(
        path.endswith("/") and prefix.startswith(path)
        for path in paths
        for prefix in _HVE_SOURCE_PATH_PREFIXES
    )


def _explicit_target_output_paths(params: Optional[Mapping[str, Any]]) -> List[str]:
    """利用者が明示指定した target 出力パスを返す（FR-CLI-74 の対象外判定用）。"""
    raw = (params or {}).get("target_files")
    if isinstance(raw, str):
        candidates: List[str] = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        candidates = [str(item) for item in raw]
    else:
        return []
    return [candidate.strip() for candidate in candidates if str(candidate).strip()]


def _validated_qa_include_paths(paths: Optional[Iterable[Union[str, Path]]]) -> List[str]:
    """明示 stage を許可する qa/ Markdown のリポジトリ相対パスを返す。"""
    result: List[str] = []
    for value in paths or []:
        raw = str(value)
        if not raw or raw != raw.strip() or "\x00" in raw:
            raise ValueError("QA include path が不正です")
        posix = raw.replace("\\", "/")
        drive, _ = ntpath.splitdrive(raw)
        parts = posix.split("/")
        if drive or posix.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"QA include path は安全な相対パスではありません: {raw}")
        if parts[0] != "qa" or not posix.lower().endswith(".md"):
            raise ValueError(f"QA include path は qa/ 配下の Markdown ではありません: {raw}")
        if posix not in result:
            result.append(posix)
    return result


def _should_enable_qa_akm_dispatch(
    *, auto_qa: bool, workflow_id: str, dry_run: bool,
    qa_akm_background_merge: bool,
) -> bool:
    """QA 起点 AKM を生成する実行だけを判定する（FR-QA-05 の唯一の判定点）。"""
    return bool(
        auto_qa
        and qa_akm_background_merge
        and workflow_id != "akm"
        and not dry_run
    )


def _resolve_max_parallel(
    *, workflow: Any, config_max_parallel: int, ard_force_serial: bool,
) -> Tuple[int, str]:
    """DAG の並列上限と解決根拠を返す（FR-DAG-03 の唯一の解決点）。

    `WorkflowDef.max_parallel` の宣言は利用者設定より優先する。asdw-web の 1 は
    同一 worktree の並列書込みを避ける安全制約であり、緩められてはならない。
    """
    if ard_force_serial:
        return 1, "ard-serial"
    declared = getattr(workflow, "max_parallel", None)
    if declared:
        return int(declared), "workflow"
    return int(config_max_parallel), "config"


def _git_checkout_new_branch(new_branch: str, base_branch: str, console: Console) -> bool:
    """ローカルで新ブランチを作成し checkout する。

    git fetch origin {base_branch} を事前に実行し、
    origin/{base_branch} からブランチを作成する。
    失敗した場合はローカルの base_branch でフォールバックする。
    """
    try:
        unmerged_paths = _git_unmerged_paths()
        if unmerged_paths:
            console.error(_format_git_unmerged_index_error(unmerged_paths))
            return False

        # fetch して最新の origin/{base_branch} を取得
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", base_branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        fetch_ok = fetch_result.returncode == 0
        if not fetch_ok:
            console.warning(f"git fetch origin {base_branch} に失敗しました（ローカルブランチでフォールバック）: {fetch_result.stderr.strip()}")

        # origin/{base_branch} からブランチ作成を試みる（fetch 成功時のみ）
        if fetch_ok:
            result = subprocess.run(
                ["git", "checkout", "-b", new_branch, f"origin/{base_branch}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if result.returncode == 0:
                console.event(f"ブランチ '{new_branch}' を 'origin/{base_branch}' から作成し checkout しました。")
                return True
            console.warning(f"origin/{base_branch} からのブランチ作成に失敗。ローカルブランチでフォールバック: {result.stderr.strip()}")

        # フォールバック: ローカルの base_branch から作成
        fallback = subprocess.run(
            ["git", "checkout", "-b", new_branch, base_branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
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
    protected_baseline: Optional["ProtectedArtifactManifest"] = None,
    repo_root: Optional[Union[str, Path]] = None,
    target_output_paths: Optional[List[str]] = None,
    include_paths: Optional[List[str]] = None,
) -> bool:
    """変更を add + commit + push する。差分がなければ False を返す。

    ignore_paths に指定されたパスは git add の pathspec 除外で無視する。
    push 時は -u オプションを付与してリモートブランチをトラッキングする。

    protected_baseline を渡した場合、local generation checkpoint 時点の成果物が
    失われていないかを **git add より前** に検査し、違反時は index を触らずに
    False を返す。

    ``git add`` の後・``git commit`` の前に staged パスを検査し、HVE ソースが
    混入していれば index を unstage して commit / push せずに False を返す
    （FR-CLI-75）。``target_output_paths`` は FR-CLI-74 と同じ規則で検査対象から
    除外する。
    """
    validated_include_paths = _validated_qa_include_paths(include_paths)
    if protected_baseline is not None:
        guard_errors = check_protected_artifact_regression(protected_baseline, repo_root)
        if guard_errors:
            for guard_error in guard_errors:
                console.error(guard_error)
            return False
    try:
        # 差分確認
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
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
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if add_result.returncode != 0:
            console.error(f"git add に失敗しました: {add_result.stderr.strip()}")
            return False
        if validated_include_paths:
            include_result = subprocess.run(
                ["git", "add", "--", *validated_include_paths],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if include_result.returncode != 0:
                console.error(
                    "検証済み QA ファイルの git add に失敗しました: "
                    f"{include_result.stderr.strip()}"
                )
                return False

        # FR-CLI-75: staging へ混入した HVE ソースを commit 前に拒否する。
        # add 前の status に HVE ソース候補が無ければ staged にもなり得ないため、
        # その場合だけ追加の git 呼び出しを省く。
        if _status_may_stage_hve_source(status.stdout, target_output_paths):
            staged_result = subprocess.run(
                ["git", "-c", "core.quotePath=false", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if staged_result.returncode != 0:
                console.error(
                    "staged パスを確認できないため commit を中止しました: "
                    f"{staged_result.stderr.strip()}"
                )
                return False
            staged_hve_paths = _filter_hve_source_paths(
                [
                    _normalize_repo_relative_path(line)
                    for line in staged_result.stdout.splitlines()
                    if line.strip()
                ],
                target_output_paths,
            )
            if staged_hve_paths:
                console.error(_format_staged_hve_source_error(staged_hve_paths))
                # index からの unstage のみ。--hard 等は使わず作業ツリーは変更しない。
                reset_result = subprocess.run(
                    ["git", "reset", "--mixed", "--quiet"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                )
                if reset_result.returncode == 0:
                    console.warning(
                        "staged 変更を unstage しました（作業ツリーのファイルは変更していません）。"
                    )
                else:
                    console.error(
                        "index の unstage に失敗しました。`git reset` を手動で実行してください: "
                        f"{reset_result.stderr.strip()}"
                    )
                return False

        # ステージングエリアの差分確認（除外後に差分がなければスキップ）
        cached_diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if cached_diff.returncode == 0:
            console.warning("除外パスを適用後、コミット対象のステージング変更がありません。")
            return False

        # git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if commit_result.returncode != 0:
            console.error(f"git commit に失敗しました: {commit_result.stderr.strip()}")
            return False
        console.event(f"変更をコミットしました: {commit_message}")

        # git push（-u でリモートブランチをトラッキング）
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
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


def _git_push_branch(branch: str, console: Console) -> bool:
    """現在の HEAD を origin/<branch> へ push する（差分なしブランチ作成にも使う）。"""
    try:
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
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
        console.error("git push がタイムアウトしました。")
        return False


def _git_current_branch(console: Console) -> Optional[str]:
    """現在 checkout されているブランチ名を返す。detached HEAD は None。"""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            console.warning(f"現在ブランチの取得に失敗しました: {result.stderr.strip()}")
            return None
        branch = result.stdout.strip()
        return branch or None
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return None
    except subprocess.TimeoutExpired:
        console.error("git branch がタイムアウトしました。")
        return None


def _git_has_uncommitted_changes(console: Console) -> bool:
    """未コミット変更（未追跡を含む）があるかを返す。取得失敗時は安全側で True。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            console.warning(f"git status の取得に失敗しました: {result.stderr.strip()}")
            return True
        return bool(result.stdout.strip())
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return True
    except subprocess.TimeoutExpired:
        console.error("git status がタイムアウトしました。")
        return True


def _git_checkout_existing_branch(branch: str, console: Console) -> bool:
    """既存ローカルブランチへ checkout する。"""
    try:
        result = subprocess.run(
            ["git", "checkout", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            console.warning(f"'{branch}' への checkout に失敗しました: {result.stderr.strip()}")
            return False
        console.event(f"'{branch}' へ checkout しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git checkout がタイムアウトしました。")
        return False


def _git_remote_branch_ahead(branch: str, console: Console) -> bool:
    """origin/<branch> がローカル <branch> より先行している場合 True を返す。"""
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if fetch.returncode != 0:
            console.warning(f"git fetch origin {branch} に失敗しました: {fetch.stderr.strip()}")
            return False

        local_rev = subprocess.run(
            ["git", "rev-parse", branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        remote_rev = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if local_rev.returncode != 0 or remote_rev.returncode != 0:
            return False
        local_sha = local_rev.stdout.strip()
        remote_sha = remote_rev.stdout.strip()
        if not local_sha or not remote_sha or local_sha == remote_sha:
            return False

        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", local_sha, remote_sha],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return ancestor.returncode == 0
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git remote branch 状態確認がタイムアウトしました。")
        return False


def _git_checkout_base_branch(base_branch: str, console: Console) -> bool:
    """base_branch へ checkout する。"""
    try:
        checkout = subprocess.run(
            ["git", "checkout", base_branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if checkout.returncode != 0:
            console.warning(
                f"'{base_branch}' への checkout に失敗しました: {checkout.stderr.strip()}"
            )
            return False
        console.event(f"'{base_branch}' へ checkout しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git checkout がタイムアウトしました。")
        return False


def _git_pull_ff_only_base_branch(base_branch: str, console: Console) -> bool:
    """base_branch を origin/<base_branch> から fast-forward のみで更新する。"""
    try:
        pull = subprocess.run(
            ["git", "pull", "--ff-only", "origin", base_branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if pull.returncode != 0:
            console.warning(
                f"'{base_branch}' の fast-forward 更新に失敗しました: {pull.stderr.strip()}"
            )
            return False
        console.event(f"'{base_branch}' を origin/{base_branch} へ fast-forward 更新しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git pull がタイムアウトしました。")
        return False


def _git_delete_local_branch(working_branch: str, base_branch: str, console: Console) -> bool:
    """作業ブランチをローカル削除する（FR-CLI-34）。

    `git checkout <base>` → `git branch -D <branch>` の実行は
    [hve/branch_cleanup.py](hve/branch_cleanup.py) の単一 core へ委譲する
    （FR-MAINT-07）。失敗した場合は警告して False を返す。
    """
    try:
        from .branch_cleanup import delete_local_branch
    except ImportError:  # pragma: no cover - script 実行経路
        from branch_cleanup import delete_local_branch  # type: ignore[no-redef]

    result = delete_local_branch(working_branch, base_branch)
    if not result.deleted:
        console.warning(
            f"作業ブランチ '{working_branch}' のローカル削除を中止しました: {result.reason}"
        )
        return False
    console.event(f"マージ済みの作業ブランチ '{working_branch}' をローカルから削除しました。")
    return True


def _git_delete_remote_branch(working_branch: str, console: Console) -> bool:
    """作業ブランチを origin から削除する（失敗 PR cleanup 用）。"""
    try:
        delete = subprocess.run(
            ["git", "push", "origin", "--delete", working_branch],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if delete.returncode != 0:
            console.warning(
                f"作業ブランチ '{working_branch}' のリモート削除に失敗しました: {delete.stderr.strip()}"
            )
            return False
        console.event(f"作業ブランチ '{working_branch}' を origin から削除しました。")
        return True
    except FileNotFoundError:
        console.error("git コマンドが見つかりません。")
        return False
    except subprocess.TimeoutExpired:
        console.error("git 操作がタイムアウトしました。")
        return False


def _cleanup_failed_pr_if_created(
    pr_number: int,
    working_branch: Optional[str],
    config: SDKConfig,
    console: Console,
) -> None:
    """失敗 Step 後に PR が作成済みだった場合の best-effort cleanup。

    GitHub の PR は通常 API で物理削除できないため、実質的な撤去として
    自動化ラベル除去 → PR close → remote/local head branch 削除を試みる。
    各処理の失敗は cleanup 全体を止めず warning として記録する。
    """
    token = config.resolve_token()
    repo = config.repo
    if token and repo:
        for label in (
            "auto-approve-ready",
            "auto-qa",
            "adversarial-review",
            "auto-context-review",  # 旧PR cleanup用の後方互換
        ):
            try:
                api_call(
                    "DELETE",
                    f"https://api.github.com/repos/{repo}/issues/{pr_number}/labels/{quote(label, safe='')}",
                    token=token,
                    max_retries=1,
                )
                console.event(f"PR #{pr_number} から '{label}' ラベルを削除しました。")
            except GitHubAPIError as exc:
                if exc.status != 404:
                    console.warning(f"PR #{pr_number} の '{label}' ラベル削除に失敗しました: {exc}")
        try:
            api_call(
                "PATCH",
                f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
                data={"state": "closed"},
                token=token,
                max_retries=1,
            )
            console.event(
                f"PR #{pr_number} を close しました（GitHub PR は物理削除ではなく close がサポートされた撤去手段です）。"
            )
        except GitHubAPIError as exc:
            console.warning(f"PR #{pr_number} の close に失敗しました: {exc}")
    else:
        console.warning("GH_TOKEN または REPO が未設定のため、PR close / ラベル削除をスキップします。")

    if working_branch:
        _git_delete_remote_branch(working_branch, console)
        _git_delete_local_branch(working_branch, config.base_branch, console)


def _wait_pr_merged_and_delete_local_branch(
    pr_number: int,
    working_branch: str,
    config: SDKConfig,
    console: Console,
    poll_interval: float = 15.0,
    timeout: float = 600.0,
) -> bool:
    """PR の merged を検知して作業ブランチをローカル削除する（FR-CLI-34）。

    リモートの auto-approve-and-merge 完了（PR が merged）を最大 ``timeout`` 秒、
    ``poll_interval`` 秒間隔でポーリングする。merged 検知時のみ削除する。
    未マージ（closed 等）・タイムアウト・状態取得失敗・中断時は削除せず警告する。
    リモートブランチは削除しない（github.com の自動削除設定に委ねる）。
    """
    if not _wait_pr_merged(
        pr_number=pr_number,
        config=config,
        console=console,
        poll_interval=poll_interval,
        timeout=timeout,
    ):
        return False
    # FR-CLI-34: 適格性判定は共通 core の単一実装で行う（FR-MAINT-07）。
    if not _is_local_cleanup_eligible(pr_number, working_branch, config, console):
        return False
    _git_delete_local_branch(working_branch, config.base_branch, console)
    return True


def _is_local_cleanup_eligible(
    pr_number: int,
    working_branch: str,
    config: SDKConfig,
    console: Console,
) -> bool:
    """PR の実体と対象 branch が cleanup 条件を満たすかを共通 core で判定する。

    取得に失敗した場合は削除しない（fail-closed）。
    """
    try:
        from .branch_cleanup import LocalBranchCleanupTarget, is_cleanup_eligible
    except ImportError:  # pragma: no cover - script 実行経路
        from branch_cleanup import (  # type: ignore[no-redef]
            LocalBranchCleanupTarget,
            is_cleanup_eligible,
        )

    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning("GH_TOKEN または REPO が未設定のため、ローカル branch を削除しません。")
        return False
    try:
        pull_request = get_pull_request(pr_number, repo=repo, token=token)
    except GitHubAPIError as exc:
        console.warning(f"PR #{pr_number} の再取得に失敗したため削除しません: {exc}")
        return False

    result = is_cleanup_eligible(
        LocalBranchCleanupTarget(
            repo=repo,
            pr_number=pr_number,
            branch=working_branch,
            base_branch=config.base_branch,
            created_by_hve=True,
        ),
        pull_request,
    )
    if not result.deleted:
        console.warning(
            f"作業ブランチ '{working_branch}' は cleanup 条件を満たしません: {result.reason}"
        )
        return False
    return True


def _wait_pr_merged(
    pr_number: int,
    config: SDKConfig,
    console: Console,
    poll_interval: float = 15.0,
    timeout: float = 600.0,
    require_check_runs: bool = True,
) -> bool:
    """PR の merged と、必要に応じて merge commit の check-run 成功を待機する。"""
    deploy_gate_block_marker = "<!-- auto-approve-deploy-gate-blocked -->"
    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning(
            "GH_TOKEN または REPO が未設定のため、PR マージ完了待機をスキップします。"
        )
        return False
    console.event(
        f"PR #{pr_number} のマージ完了を待機します（最大 {int(timeout)} 秒）。"
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pr = get_pull_request(pr_number, repo=repo, token=token)
        except GitHubAPIError as exc:
            console.warning(
                f"PR #{pr_number} の状態取得に失敗しました: {exc}"
            )
            return False
        if pr.get("merged"):
            merge_ref = str(pr.get("merge_commit_sha") or "").strip()
            if require_check_runs and merge_ref and not _wait_check_runs_success(
                merge_ref, config, console, poll_interval=poll_interval, timeout=timeout
            ):
                console.warning(
                    f"PR #{pr_number} はマージ済みですが、merge commit の check-run 成功を確認できません。"
                )
                return False
            return True
        if pr.get("state") == "closed":
            console.warning(
                f"PR #{pr_number} はマージされずクローズされました。"
            )
            return False
        try:
            comments = list_issue_comments(pr_number, repo=repo, token=token)
        except GitHubAPIError as exc:
            console.warning(
                f"PR #{pr_number} のコメント取得に失敗しました: {exc}"
            )
            comments = []
        if any(deploy_gate_block_marker in str(c.get("body") or "") for c in comments):
            console.warning(
                f"PR #{pr_number} は auto-approve Deploy/AC gate で停止しています。"
            )
            return False
        time.sleep(poll_interval)
    console.warning(
        f"PR #{pr_number} のマージを {int(timeout)} 秒以内に確認できませんでした。"
    )
    return False


def _wait_check_runs_success(
    ref: str,
    config: SDKConfig,
    console: Console,
    poll_interval: float = 15.0,
    timeout: float = 600.0,
) -> bool:
    """merge commit の check-runs が失敗していないことを確認する。"""
    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        console.warning("GH_TOKEN または REPO が未設定のため check-run 確認をスキップできません。")
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            runs = list_check_runs_for_ref(ref, repo=repo, token=token)
        except GitHubAPIError as exc:
            console.warning(f"check-runs API の取得に失敗しました: {exc}")
            return False

        if not runs:
            console.warning("check-run が見つからないため、post-merge 検証成功とは判定しません。")
            return False

        failed = [
            r for r in runs
            if str(r.get("conclusion") or "").lower()
            in {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
        ]
        if failed:
            names = ", ".join(str(r.get("name") or "unknown") for r in failed[:5])
            console.warning(f"失敗 check-run を検出しました: {names}")
            return False

        incomplete = [r for r in runs if str(r.get("status") or "").lower() != "completed"]
        if not incomplete:
            return True
        time.sleep(poll_interval)
    console.warning(f"check-run の完了を {int(timeout)} 秒以内に確認できませんでした。")
    return False


# -----------------------------------------------------------------------
# Issue/PR 作成ヘルパー
# -----------------------------------------------------------------------

class RootIssueResolutionError(Exception):
    """FR-GUI-25: 指定された既存 Issue を Root Issue として解決できない。

    誤った番号のまま Sub-Issue を無関係な Issue へ紐付けることを防ぐため、
    Root Issue の新規作成へフォールバックせず実行を中止する。
    """


class RootIssueAssignmentError(Exception):
    """FR-CLI-89: 作成済み Root Issue の Copilot 割当を確認できない。"""

    def __init__(self, root_issue_num: int, message: str) -> None:
        super().__init__(message)
        self.root_issue_num = root_issue_num


def _assign_new_root_issue_to_copilot(
    root_issue_num: int,
    repo: str,
    token: str,
    base_branch: str,
    console: Console,
) -> None:
    """当該 run が新規作成した Root Issue だけを Copilot へ割り当てる。"""
    try:
        assign_copilot_agent(
            root_issue_num,
            repo=repo,
            token=token,
            base_branch=base_branch,
        )
    except GitHubAPIError as exc:
        raise RootIssueAssignmentError(
            root_issue_num=root_issue_num,
            message=(
                f"Root Issue #{root_issue_num} は作成済みですが、Copilot cloud agent への"
                f"割り当てに失敗したため run を停止します: {exc}"
            ),
        ) from exc

    console.event(
        f"Root Issue #{root_issue_num} を Copilot cloud agent へ割り当てました。"
    )


def _resolve_existing_root_issue(
    issue_number: int,
    repo: str,
    token: str,
    console: Console,
) -> int:
    """既存 Issue を Root Issue として解決する（FR-GUI-25）。"""
    try:
        issue = get_issue(issue_number, repo=repo, token=token)
    except GitHubAPIError as exc:
        raise RootIssueResolutionError(
            f"既存 Issue #{issue_number} を取得できませんでした: {exc}"
        ) from exc

    if "pull_request" in issue:
        raise RootIssueResolutionError(
            f"#{issue_number} は Pull Request です。Root Issue には Issue 番号を指定してください。"
        )

    number = issue.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        raise RootIssueResolutionError(
            f"既存 Issue #{issue_number} のレスポンスに number がありません。"
        )

    title = str(issue.get("title") or "")
    console.event(f"既存 Issue #{number} を Root Issue として使用します。{title}".rstrip())
    return number


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

    ``config.issue_number`` が指定されている場合は Root Issue を新規作成せず、
    当該の既存 Issue を Root Issue として扱う（FR-GUI-25）。``create_pr`` だけの
    run では Issue を一切作成せず、指定 Issue を PR の closing target として返す。

    Returns:
        (root_issue_num, step_issue_map)

    Raises:
        RootIssueResolutionError: 指定された既存 Issue を解決できない場合。
        RootIssueAssignmentError: 新規 Root Issue の Copilot 割当を確認できない場合。
    """
    if config.dry_run:
        return None, {}

    link_only = not config.create_issues and bool(config.create_pr) and config.issue_number is not None
    if not config.create_issues and not link_only:
        return None, {}

    token = config.resolve_token()
    repo = config.repo
    if not token or not repo:
        if link_only:
            console.warning(
                "GH_TOKEN または REPO が未設定のため既存 Issue の解決をスキップします。"
                " PR 作成も同条件でスキップされます。"
            )
        else:
            console.warning("create_issues=True ですが GH_TOKEN または REPO が未設定のため Issue 作成をスキップします。")
        return None, {}

    prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())

    if config.issue_number is not None:
        root_issue_num = _resolve_existing_root_issue(
            config.issue_number, repo, token, console
        )
        if link_only:
            return root_issue_num, {}
    else:
        console.event("Root Issue を作成中...")
        root_body = build_root_issue_body_fn(wf, params)
        if params.get("issue_title"):
            root_title = params["issue_title"]
        else:
            fallback_title = f"[{prefix}] {_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}"
            root_title = _generate_gui_issue_title(
                fallback_title=fallback_title,
                issue_body=root_body,
                required_prefix=f"[{prefix}] ",
                config=config,
                console=console,
            )
        root_issue_num, _ = create_issue(
            title=root_title,
            body=root_body,
            labels=[],
            repo=repo,
            token=token,
        )
        console.event(f"Root Issue #{root_issue_num} を作成しました。")
        if bool(getattr(config, "assign_copilot_agent", False)):
            _assign_new_root_issue_to_copilot(
                root_issue_num,
                repo,
                token,
                config.base_branch,
                console,
            )

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


def _collect_deploy_ac_verification_lines(max_lines: int = 30) -> List[str]:
    """run scoped ``ac-verification.md`` から AC テーブル行だけを収集する。

    PR body 用の短い検証サマリーとして使うため、AC 行以外はコピーしない。
    これによりログ内のシークレットや任意テキストを PR body に載せるリスクを抑える。
    """
    if max_lines <= 0:
        return []
    try:
        from hve.split_fork import resolve_work_root
    except Exception:
        return []
    try:
        work_root = resolve_work_root()
    except Exception:
        return []
    if not work_root.exists():
        return []

    rows: List[str] = []
    for report_path in sorted(work_root.glob("**/ac-verification.md")):
        if len(rows) > max_lines:
            break
        try:
            text = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not cells:
                continue
            ac_id = cells[0]
            if not (ac_id.startswith("AC-") or ac_id.startswith("AC4B-")):
                continue
            rows.append("| " + " | ".join(cells[:3]) + " |")
            if len(rows) > max_lines:
                break

    if len(rows) > max_lines:
        return rows[:max_lines] + [f"...（{max_lines} 行上限で省略）"]
    return rows


# -----------------------------------------------------------------------
# Fan-out 事前展開（ADR-0002 / 修正タスク fanout-fix）
# -----------------------------------------------------------------------
#
# 背景:
# - dag_executor.py の fan-out 展開は ``dag_plan is None`` 経路でのみ動作する。
# - production の orchestrator は常に ``dag_plan`` を渡すため、fan-out は未起動。
# - 修正方針 (C): orchestrator が ``build_dag_plan`` 直前に workflow を事前展開し、
#   active_step_ids にも子 ID を同期して追加する。
#
def _expand_workflow_for_dag(
    workflow: Any,
    active_step_ids: Set[str],
    repo_root: Any,
    *,
    app_ids: Optional[List[str]] = None,
) -> Tuple[Any, Set[str], Any]:
    """fan-out 展開済み workflow と拡張済み active_step_ids を返す。

    Args:
        workflow: 元の WorkflowDef（``_ard_force_serial`` 等の deepcopy 改変後）。
        active_step_ids: フィルタ済みアクティブ step_id 集合（ベース ID を含む）。
        repo_root: catalog_parsers がカタログファイルを探すルート。
        app_ids: GUI / CLI で指定された対象 APP-ID リスト。``None`` または空
            リストの場合はフィルタを適用せず全 fan-out キーを展開する（後方互換）。
            指定がある場合は ``expand_workflow_fanout`` 経由で
            ``_APP_ID_FILTERABLE_PARSERS`` 対象 parser の展開キーを絞り込む。

    Returns:
        ``(expanded_workflow, expanded_active_step_ids, info)``
        - ``expanded_workflow``: 子 step を含む新 WorkflowDef
          （fan-out 親 ID は steps から除外、K-1 空展開時のみ残置）。
        - ``expanded_active_step_ids``: ベース ID に含まれる fan-out 親に対応する
          子 ID を追加した集合（DAGExecutor L138-141 と同じロジック）。
        - ``info``: ``ExpandedWorkflow``（fanout_map / empty_fanout_ids を保持）。

    フォールバック:
        展開中に例外が出た場合は ``(workflow, active_step_ids, None)`` を返す。
        呼び出し側で warning を出力すること。
    """
    try:
        from .fanout_expander import expand_workflow_fanout  # type: ignore[import]
    except ImportError:  # pragma: no cover
        from fanout_expander import expand_workflow_fanout  # type: ignore[no-redef]
    try:
        from .workflow_registry import WorkflowDef  # type: ignore[import]
    except ImportError:  # pragma: no cover
        from workflow_registry import WorkflowDef  # type: ignore[no-redef]
    try:
        from .catalog_parsers import get_parser_input_path  # type: ignore[import]
    except ImportError:  # pragma: no cover
        from catalog_parsers import get_parser_input_path  # type: ignore[no-redef]

    info = expand_workflow_fanout(workflow, repo_root, app_ids=app_ids)

    # fan-out が 1 件もなかった場合は元 workflow をそのまま返す
    if not info.fanout_map:
        return workflow, set(active_step_ids), info

    # 新 WorkflowDef（展開後 steps を持つ）を構築
    expanded_workflow = WorkflowDef(
        id=getattr(workflow, "id", "unknown"),
        name=getattr(workflow, "name", ""),
        label_prefix=getattr(workflow, "label_prefix", ""),
        state_labels=dict(getattr(workflow, "state_labels", {}) or {}),
        params=list(getattr(workflow, "params", []) or []),
        steps=info.steps,
        max_parallel=getattr(workflow, "max_parallel", None),
    )

    # active_step_ids 拡張: ベース ID が active なら子 ID もすべて active
    # （dag_executor.py L138-141 と同じロジック）
    expanded_active: Set[str] = set(active_step_ids)
    for base_id, child_ids in info.fanout_map.items():
        if base_id in expanded_active and child_ids:
            expanded_active.update(child_ids)

    # T-C1: deferred fan-out 判定
    # empty_fanout_ids のうち、同一実行内の upstream step が入力ファイルを生成する
    # 見込みのものは active から discard せず保持する。DAGExecutor が upstream 完了後に
    # ランタイム再展開する（T-D2）。
    #
    # 判定: base_step.fanout_parser の入力パス（catalog_parsers.get_parser_input_path）が、
    # base_step の depends_on 推移閉包に含まれるいずれかの step の output_paths
    # （または output_paths_template の {key} 置換後パターン）と一致するかを fnmatch 照合する。
    deferred_fanout_ids: List[str] = []
    if info.empty_fanout_ids:
        # 元 workflow.steps から ID → step の索引を作る（展開前の状態）
        _orig_steps_by_id: Dict[str, Any] = {s.id: s for s in workflow.steps}

        def _transitive_deps(start_id: str) -> Set[str]:
            seen: Set[str] = set()
            stack: List[str] = [start_id]
            while stack:
                cur = stack.pop()
                step = _orig_steps_by_id.get(cur)
                if step is None:
                    continue
                for dep in getattr(step, "depends_on", []) or []:
                    if dep in seen:
                        continue
                    seen.add(dep)
                    stack.append(dep)
            return seen

        def _step_produces_path(step: Any, target_path: str) -> bool:
            """step が target_path（fnmatch パターン可）を output に持つかを判定。"""
            import fnmatch as _fnmatch
            outputs: List[str] = list(getattr(step, "output_paths", []) or [])
            tmpl: List[str] = list(getattr(step, "output_paths_template", []) or [])
            for o in outputs:
                if o == target_path or _fnmatch.fnmatch(o, target_path) or _fnmatch.fnmatch(target_path, o):
                    return True
            for t in tmpl:
                # {key} を * に置換して glob 比較
                pat = t.replace("{key}", "*")
                if _fnmatch.fnmatch(target_path, pat) or _fnmatch.fnmatch(pat, target_path):
                    return True
            return False

        for empty_id in info.empty_fanout_ids:
            base = _orig_steps_by_id.get(empty_id)
            if base is None:
                continue
            parser_name = getattr(base, "fanout_parser", None)
            if not parser_name:
                continue
            input_path = get_parser_input_path(parser_name)
            if not input_path:
                continue
            # base の depends_on 推移閉包の中に input_path を output に持つ step があるか
            upstream_ids = _transitive_deps(empty_id)
            if any(
                _step_produces_path(_orig_steps_by_id[uid], input_path)
                for uid in upstream_ids
                if uid in _orig_steps_by_id
            ):
                deferred_fanout_ids.append(empty_id)

    info.deferred_fanout_ids = deferred_fanout_ids

    # K-1: 0 件展開のベース ID は active から除外し auto_skipped 化する
    # （dag_executor.py L274-283 の _fanout_empty_ids skip に相当）
    # ただし deferred_fanout_ids に該当するものは保持する（T-C1）。
    _deferred_set = set(deferred_fanout_ids)
    for empty_id in info.empty_fanout_ids:
        if empty_id in _deferred_set:
            continue
        expanded_active.discard(empty_id)

    return expanded_workflow, expanded_active, info


# -----------------------------------------------------------------------
# プロンプト構築
# -----------------------------------------------------------------------

# 全 Step プロンプト先頭に注入する言語ルール。
# 思考プロセス（reasoning / chain-of-thought）も日本語で行わせるため、
# モデルが reasoning を開始する前に確実に届くよう、Step プロンプト本文の
# 冒頭に常時付与する。固有名詞・コマンド・パス等は英語のまま許容する。
_LANGUAGE_DIRECTIVE_JA: str = load_prompt_file(
    "runtime/orchestrator/language-directive-ja.prompt.md"
)
_FALLBACK_STEP_BODY_TEMPLATE: str = load_prompt_file(
    "runtime/orchestrator/fallback-step-body.prompt.md"
)
_FALLBACK_METADATA_BRANCH: str = load_prompt_file(
    "runtime/orchestrator/fallback-metadata-branch.prompt.md"
).rstrip("\n")
_FALLBACK_METADATA_RESOURCE_GROUP: str = load_prompt_file(
    "runtime/orchestrator/fallback-metadata-resource-group.prompt.md"
).rstrip("\n")
_FALLBACK_METADATA_APP_ID: str = load_prompt_file(
    "runtime/orchestrator/fallback-metadata-app-id.prompt.md"
).rstrip("\n")
_REUSE_CONTEXT_TEMPLATE: str = load_prompt_file(
    "runtime/orchestrator/reuse-context.prompt.md"
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

    `step.body_template_path` が宣言されている場合はテンプレートを展開して返す。
    展開に失敗した場合（例外送出・空文字列 / None）は簡易プロンプトへ
    フォールバックせず、DAG 実行前にエラーとして停止させる (FR-CLI-71)。
    `body_template_path` が宣言されていない Step は従来どおり
    「Step.{id}: タイトル」を先頭行とし、利用可能であれば
    branch / resource_group / app_id などのステップ情報を続けた
    複数行のシンプルなプロンプトを組み立てて返す。
    いずれの場合も additional_prompt が指定された場合は、
    末尾に空行を挟んで追記する。

    FR-PROMPT-09: 当該 Step の必須入力に関係する入力別名だけを、決定的な
    addendum として追記する。ファイル本文は埋め込まない。
    """
    try:
        from .input_aliases import build_alias_addendum
    except ImportError:  # pragma: no cover - script 実行経路
        from input_aliases import build_alias_addendum  # type: ignore[no-redef]

    addendum = build_alias_addendum(step, _alias_resolver_for_params(params))
    if addendum:
        additional_prompt = (
            addendum + "\n\n" + additional_prompt if additional_prompt else addendum
        )

    if step.body_template_path:
        prompt = render_template_fn(
            template_path=step.body_template_path,
            root_issue_num=root_issue_num or 0,
            params=params,
            wf=wf,
            execution_mode=execution_mode,
        )
        # FR-CLI-71: `render_template` はテンプレートが存在しない / 空の場合に
        # fail-closed で例外を送出する。壊れた縮退プロンプトで Agent セッションを
        # 開始しないため、空文字列になる経路も同じく停止させる。
        if not prompt:
            raise ValueError(
                f"Step.{step.id}: body_template_path のレンダリング結果が空です: "
                f"{step.body_template_path}"
            )
        if additional_prompt:
            prompt = prompt + "\n\n" + additional_prompt
        return _LANGUAGE_DIRECTIVE_JA + prompt

    # body_template_path 未宣言 Step: シンプルなプロンプト（FR-CLI-71 の対象外）
    metadata_lines: List[str] = []
    if params.get("branch"):
        metadata_lines.append(
            _FALLBACK_METADATA_BRANCH.format(branch=params["branch"])
        )
    if params.get("resource_group"):
        metadata_lines.append(
            _FALLBACK_METADATA_RESOURCE_GROUP.format(
                resource_group=params["resource_group"]
            )
        )
    app_ids = params.get("app_ids", [])
    if app_ids:
        metadata_lines.append(
            _FALLBACK_METADATA_APP_ID.format(
                app_ids=", ".join(f"`{aid}`" for aid in app_ids)
            )
        )
    elif params.get("app_id"):
        metadata_lines.append(
            _FALLBACK_METADATA_APP_ID.format(app_ids=f"`{params['app_id']}`")
        )
    fallback = _FALLBACK_STEP_BODY_TEMPLATE.format(
        step_id=step.id,
        step_title=step.title,
        step_metadata_block=("\n" + "\n".join(metadata_lines)) if metadata_lines else "",
    )
    if additional_prompt:
        fallback = fallback + "\n\n" + additional_prompt
    return _LANGUAGE_DIRECTIVE_JA + fallback


# -----------------------------------------------------------------------
# 既存成果物検出・再利用コンテキスト
# -----------------------------------------------------------------------

def _collect_file_samples(root: str, limit: int = 10, exclude_prefixes: tuple = ()) -> list:
    """指定ディレクトリから最大 limit 件のファイルパスを収集して返す。

    大規模リポジトリでの全列挙を避けるため、limit 件見つかった時点で走査を打ち切る。
    呼び出し側で artifact 種別に応じた limit を渡すこと（Sub-1 A-3）:
      - "src" → 50（実装ファイルは数が多い）
      - "src/test" → 30（テストはやや少ない）
      - その他 → 10（catalog など）

    exclude_prefixes: 走査結果からこのプレフィックスで始まるパスを除外する
    （例: src 走査時に src/test/ を除外）。
    """
    from pathlib import Path
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    files: list = []
    for path in root_path.rglob("*"):
        if path.is_file():
            p = str(path).replace("\\", "/")
            if exclude_prefixes and any(p.startswith(pref) for pref in exclude_prefixes):
                continue
            files.append(str(path))
            if len(files) >= limit:
                break
    return files


def _alias_resolver_for_params(params: Optional[dict]):
    """workflow params から入力別名の**単一の**解決器を作る（FR-PROMPT-09）。

    前提成果物判定・meta 依存判定・Step Prompt・Fleet の必須入力表示は、
    すべてこの関数が返す解決器を通す。判定ごとに別実装を持たせない。
    """
    try:
        from .input_aliases import resolver_from_params
    except ImportError:  # pragma: no cover - script 実行経路
        from input_aliases import resolver_from_params  # type: ignore[no-redef]

    return resolver_from_params(params or {})


def _artifact_pattern_exists(pattern: str, resolver=None) -> bool:
    """成果物パターンの実在を判定する。別名が宣言されていれば実ファイルを見る。"""
    actual = resolver.actual_for(pattern) if resolver else None
    if actual is not None:
        return os.path.exists(actual)
    return next(_glob.iglob(pattern), None) is not None


def _detect_existing_artifacts(workflow_id: str, params: dict) -> dict:
    """既存の成果物を検出し、再利用可能なファイルリストを返す。"""
    existing: dict = {}
    resolver = _alias_resolver_for_params(params)

    catalog_files = {
        "app_catalog": "docs/catalog/app-catalog.md",
        "service_catalog": "docs/catalog/service-catalog.md",
        "data_model": "docs/catalog/data-model.md",
        "domain_analytics": "docs/catalog/domain-analytics.md",
        "test_strategy": "docs/catalog/test-strategy.md",
        "service_catalog_matrix": "docs/catalog/service-catalog-matrix.md",
        "use_case_catalog": "docs/catalog/use-case-catalog.md",
        "persona_catalog": "docs/catalog/persona-catalog.md",
        "dataflow_catalog": "docs/catalog/app-catalog.md",  # ADFD は AAS の共通カタログを SoT として参照
        "batch_service_catalog": "docs/dataflow/dataflow-service-catalog.md",
        "batch_data_model": "docs/dataflow/dataflow-data-model.md",
        "batch_domain_analytics": "docs/dataflow/dataflow-domain-analytics.md",
    }

    for key, path in catalog_files.items():
        actual = resolver.actual_for(path)
        if actual is not None:
            if os.path.exists(actual):
                existing[key] = actual
        elif os.path.exists(path):
            existing[key] = path

    # screen_catalog は per-APP 分割形式 (Arch-UI-List Step 1 fan-out)
    # 1 件以上ヒットしたファイル一覧を返す。
    screen_catalogs = _glob.glob("docs/catalog/screen-catalog-APP-*.md")
    if screen_catalogs:
        existing["screen_catalog"] = screen_catalogs

    # APP別要求定義書は per-APP 分割形式 (ARD Step 4.2 fan-out)
    app_requirements = [
        p.replace("\\", "/")
        for p in _glob.glob("docs/architectural-requirements-app-*.md")
    ]
    if app_requirements:
        existing["app_requirements"] = app_requirements

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
    # src/test/ は test_files 側で扱うため除外する。
    src_files = _collect_file_samples("src", limit=50, exclude_prefixes=("src/test/",))
    if src_files:
        existing["src_files"] = src_files

    # テストコードの検出（上限付き早期終了。Sub-1 A-3: 種別別動的上限）
    test_files = _collect_file_samples("src/test", limit=30)
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

    # データフローアプリ仕様書の検出
    dataflow_specs = _glob.glob("docs/dataflow/apps/*.md")
    if dataflow_specs:
        existing["dataflow_specs"] = dataflow_specs

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
    "screen_catalog": "docs/catalog/screen-catalog-APP-*.md",
    "app_requirements": "docs/architectural-requirements-app-*.md",
    "test_strategy": "docs/catalog/test-strategy.md",
    "service_catalog_matrix": "docs/catalog/service-catalog-matrix.md",
    "use_case_catalog": "docs/catalog/use-case-catalog.md",
    "persona_catalog": "docs/catalog/persona-catalog.md",
    "dataflow_catalog": "docs/catalog/app-catalog.md",  # ADFD は AAS の共通カタログを SoT として参照
    "batch_service_catalog": "docs/dataflow/dataflow-service-catalog.md",
    "batch_data_model": "docs/dataflow/dataflow-data-model.md",
    "batch_domain_analytics": "docs/dataflow/dataflow-domain-analytics.md",
    "service_specs": "docs/services/*.md",
    "screen_specs": "docs/screen/*.md",
    "test_specs": "docs/test-specs/*.md",
    "src_files": "src/**/*",
    "test_files": "src/test/**/*",
    "knowledge": "knowledge/*.md",
    "agent_specs": "docs/agent/*.md",
    "dataflow_specs": "docs/dataflow/apps/*.md",
    "doc_generated": "docs-generated/**/*.md",
}

# artifact key → 生成ワークフロー（確認済みのもののみ記載）
# workflow_registry.py の FULL_PIPELINE 定義および各ワークフローの出力から確認。
# 値の意味:
#   "<workflow_id>"  — そのワークフローが生成する成果物
#   "user_provided"  — ワークフローでは生成されない。ユーザーが事前に手動で用意する成果物
#   None             — 生成ワークフロー未確認（ユーザー提供またはワークフロー生成の可能性あり）
_ARTIFACT_KEY_TO_GENERATING_WORKFLOW: Dict[str, Optional[str]] = {
    "app_catalog": "ard",  # ARD Step 4.1 (Arch-ApplicationAnalytics) で生成（旧仕様では aas Step 1）
    "service_catalog": "aas",
    "data_model": "aas",
    "domain_analytics": "aas",
    "screen_catalog": "aad-web",
    "app_requirements": "ard",  # ARD Step 4.2 (Arch-ApplicationRequirementDefinition) で生成
    "test_strategy": "aas",
    "service_catalog_matrix": "aas",
    "use_case_catalog": "ard",  # ARD Step 3.3 で生成（旧仕様では user_provided）
    "persona_catalog": "aas",   # T-H3: AAS Step 8 (Arch-PersonaCatalog) で生成
    "dataflow_catalog": "ard",  # docs/catalog/app-catalog.md を ARD Step 4.1 が生成（旧仕様では aas Step.1）
    "batch_service_catalog": "adfd",
    "batch_data_model": "adfd",
    "batch_domain_analytics": "adfd",
    "service_specs": "aad-web",
    "screen_specs": "aad-web",
    "test_specs": "aad-web",        # aad-web Step 2.3 / asdw-web 内でも生成されるが確定できない
    "src_files": None,              # 要確認: ユーザーコードまたは asdw-web / adfdv の出力
    "test_files": None,             # 要確認: ユーザーコードまたは asdw-web / adfdv の出力
    "knowledge": "akm",
    "agent_specs": "aag",
    "dataflow_specs": "adfd",
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
        {"should_abort": bool, "error": str | None,
         "blocked": bool, "blocked_step_ids": List[str]}

        ``blocked`` は新 status ``"blocked"`` の入口フラグ。strict モードで
        consumed_artifacts 不足を検出した場合に True となり、``blocked_step_ids``
        に該当ルートステップ ID が列挙される。上位レイヤー (``_run_workflow``) は
        この情報を結果 dict の ``"blocked"`` キーに伝播し、後続レイヤーが
        「failed と区別された停止」として扱える。

        warning モード時、または missing が無い場合は ``blocked=False`` /
        ``blocked_step_ids=[]``。
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
        return {
            "should_abort": False,
            "error": None,
            "blocked": False,
            "blocked_step_ids": [],
        }

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

    # 重複なしの順序保持リスト (検出順)
    blocked_step_ids: List[str] = []
    for item in all_missing:
        sid = item.get("step_id")
        if sid and sid not in blocked_step_ids:
            blocked_step_ids.append(sid)

    if config.require_input_artifacts:
        lines.append(
            "\nstrict モード (HVE_REQUIRE_INPUT_ARTIFACTS=true) のため実行を中断します "
            "(status=blocked)。"
            "\n警告モードで実行するには HVE_REQUIRE_INPUT_ARTIFACTS=false（デフォルト）を設定してください。"
        )
        msg = "\n".join(lines)
        console.error(msg)
        return {
            "should_abort": True,
            "error": msg,
            "blocked": True,
            "blocked_step_ids": blocked_step_ids,
        }
    else:
        lines.append(
            "\n(warning モード: 続行します。strict モードにするには HVE_REQUIRE_INPUT_ARTIFACTS=true を設定してください)"
        )
        msg = "\n".join(lines)
        console.warning(msg)
        return {
            "should_abort": False,
            "error": None,
            "blocked": False,
            "blocked_step_ids": [],
        }


def _check_required_skills_for_active_steps(
    wf,
    workflow_id: str,
    active_steps: Set[str],
    console: "Console",
) -> dict:
    """active step に required_skills があれば、存在する skill 名かを事前検証する。

    Returns:
        dict: ``should_abort`` / ``error`` / ``blocked`` / ``blocked_step_ids``
        を含む結果。``blocked`` は T-H1H2b で追加されたフィールドで、strict
        モードかつ必須 Skill 不足を検出した場合に True となる。``blocked_step_ids``
        には該当 step ID が wf.steps 順で重複除去されて列挙される。上位レイヤー
        (``run_workflow``) は ``failed`` と区別して「停止」として扱える。
    """
    try:
        try:
            from .skill_resolver import get_required_skills_for_step, validate_skill_names
        except ImportError:
            from skill_resolver import get_required_skills_for_step, validate_skill_names  # type: ignore[no-redef]
    except Exception as exc:
        console.warning(
            f"Skill resolver の読み込みに失敗したため skill 事前検証をスキップします: {exc}"
        )
        return {"should_abort": False, "error": None, "blocked": False, "blocked_step_ids": []}

    resolved_workflow_id = getattr(wf, "id", None)
    if not isinstance(resolved_workflow_id, str) or not resolved_workflow_id:
        resolved_workflow_id = workflow_id
    active_base_step_ids = {
        str(active_step_id).split("/", 1)[0]
        for active_step_id in active_steps
    }
    missing_rows: List[Dict[str, Any]] = []
    for step in wf.steps:
        if step.is_container or step.id not in active_base_step_ids:
            continue

        declared = list(getattr(step, "required_skills", []) or [])
        required = get_required_skills_for_step(
            workflow_id=resolved_workflow_id,
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
        return {"should_abort": False, "error": None, "blocked": False, "blocked_step_ids": []}

    lines = ["必須 skill が見つかりません。以下を修正してください:"]
    for row in missing_rows:
        suggest = row.get("suggestions") or []
        suggest_text = f" (候補: {', '.join(suggest)})" if suggest else ""
        lines.append(
            f"  - Step.{row['step_id']} {row['step_title']}: {row['skill']}{suggest_text}"
        )

    msg = "\n".join(lines)
    console.error(msg)
    # T-H1H2b: 順序保持 dedup で blocked step ID を列挙
    blocked_step_ids: List[str] = []
    for row in missing_rows:
        sid = row.get("step_id")
        if sid and sid not in blocked_step_ids:
            blocked_step_ids.append(sid)
    return {
        "should_abort": True,
        "error": msg + " (status=blocked)",
        "blocked": True,
        "blocked_step_ids": blocked_step_ids,
    }


def _check_required_workflow_params_for_active_steps(
    wf,
    active_steps: Set[str],
    params: Mapping[str, Any],
    console: "Console",
) -> dict:
    """active step が宣言した必須 Workflow パラメータを実行開始前に検査する（FR-DAG-08）。

    `StepDef.required_params`（FR-DAG-07）を単一情報源として、値が
    未設定 / ``None`` / 空白のみ / ``str`` 以外のいずれかであるキーを不足として扱う。

    **不足は全件を 1 回で報告する**。1 件ずつしか報告しないと、利用者は
    不足件数と同じ回数だけ長時間ワークフローを再実行することになる。

    Returns:
        dict: ``should_abort`` / ``error`` / ``blocked`` / ``blocked_step_ids``。
        本チェックは常に strict（不足があれば ``should_abort=True``）である。
        必須パラメータは同一ワークフロー内の先行 Step では解消され得ないため、
        警告降格の余地がない。
    """
    try:
        from .workflow_registry import steps_declaring_params
    except ImportError:
        from workflow_registry import steps_declaring_params  # type: ignore[no-redef]

    missing_rows: List[Dict[str, Any]] = []
    for step in steps_declaring_params(wf, active_steps):
        for key in step.required_params:
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                continue
            missing_rows.append(
                {
                    "step_id": step.id,
                    "step_title": getattr(step, "title", step.id),
                    "param": key,
                    "has_default": key in step.default_params,
                }
            )

    if not missing_rows:
        return {
            "should_abort": False,
            "error": None,
            "blocked": False,
            "blocked_step_ids": [],
        }

    lines = [
        f"必須パラメータが未指定です（{len(missing_rows)} 件）。"
        "以下を全て指定してから再実行してください:",
    ]
    for row in missing_rows:
        note = "（既定値あり。指定値が不正の可能性）" if row["has_default"] else ""
        lines.append(
            f"  - Step.{row['step_id']} {row['step_title']}: {row['param']}{note}"
        )
    msg = "\n".join(lines)
    console.error(msg)

    blocked_step_ids: List[str] = []
    for row in missing_rows:
        sid = row["step_id"]
        if sid not in blocked_step_ids:
            blocked_step_ids.append(sid)
    return {
        "should_abort": True,
        "error": msg + " (status=blocked)",
        "blocked": True,
        "blocked_step_ids": blocked_step_ids,
    }


def _check_dirty_hve_sources(
    console: "Console",
    target_output_paths: Optional[List[str]] = None,
) -> dict:
    """HVE ソースの未コミット変更を run 開始前に検査する（FR-CLI-74）。

    HVE ソース（``hve/`` / ``mdq/`` / ``hve-dev/`` / ``.github/prompts/`` /
    ``.github/skills/`` / ``.github/scripts/`` / ``.github/io-contracts/``）に
    未コミット変更があるまま run を開始すると、その差分が生成対象アプリの
    branch / commit / PR に混入する。**検出した全パスを 1 回で一括報告する**。
    1 件ずつ報告すると、利用者は件数と同じ回数だけ run をやり直すことになる。

    利用者が明示的に指定した target 出力パス配下は対象外とする。
    GUI の利用者ローカル設定（``_HVE_LOCAL_RUNTIME_PATHS``）も対象外とする。

    本チェックは常に strict であり、無効化するフラグは提供しない
    （FR-CLI-74: 「新しい override フラグを追加してはならない」）。

    Returns:
        dict: ``should_abort`` / ``error`` / ``blocked`` / ``blocked_step_ids``。
        ``blocked_step_ids`` は Step 単位ではなくリポジトリ単位の停止のため
        センチネル ``"hve-source-dirty"`` を返す。
    """
    dirty_paths = _git_dirty_hve_source_paths(target_output_paths=target_output_paths)
    if not dirty_paths:
        return {
            "should_abort": False,
            "error": None,
            "blocked": False,
            "blocked_step_ids": [],
        }

    msg = _format_dirty_hve_source_error(dirty_paths)
    console.error(msg)
    return {
        "should_abort": True,
        "error": msg + " (status=blocked)",
        "blocked": True,
        "blocked_step_ids": ["hve-source-dirty"],
    }


def _format_qa_akm_failure_warning(
    failed: List[Dict[str, Any]],
    reason: str,
) -> str:
    """QA 起点 AKM 子実行の失敗報告を組み立てる（FR-QA-07）。

    子ログの本文は展開せず、保存先パスと ``returncode`` だけを出す。
    バッチ実行では複数の QA ファイルが同一の子実行を共有するため、保存先単位で束ねる。
    """
    lines = [
        f"QA 起点 AKM は {len(failed)} 件失敗しました"
        f"（source Workflow は継続、境界={reason}）。"
    ]
    grouped: Dict[tuple, List[str]] = {}
    for item in failed:
        key = (int(item.get("returncode", -1)), str(item.get("log_path", "")))
        grouped.setdefault(key, []).append(str(item.get("file", "")))
    for (returncode, log_path), files in grouped.items():
        location = log_path or "（子ログ未保存: 子プロセスを起動できませんでした）"
        lines.append(
            f"  - returncode={returncode} 対象 {len(files)} 件 / ログ: {location}"
        )
    lines.append(
        "  子が status=blocked で停止した場合は HVE ソースの未コミット変更"
        "（FR-CLI-74）が最も多い原因です。`git status --porcelain hve mdq hve-dev .github` を確認してください。"
    )
    return "\n".join(lines)


def _format_qa_akm_skip_warning(
    skipped: List[Dict[str, Any]],
    reason: str,
) -> str:
    """登録時点の事前判定で起動しなかった登録を報告する（FR-QA-07）。

    実行失敗とは別件として扱う。子を起動していないため `returncode` は意味を持たない。
    """
    files = [str(item.get("file", "")) for item in skipped]
    lines = [
        f"QA 起点 AKM の登録を {len(skipped)} 件スキップしました"
        f"（source Workflow は継続、境界={reason}）。"
    ]
    for path in files:
        lines.append(f"  - {path}")
    lines.append(
        "  HVE ソースに未コミット変更があるためです（FR-CLI-74）。"
        "`git status --porcelain hve mdq hve-dev .github` を確認し、"
        "コミットまたは退避してから `--workflow akm` で手動取り込みしてください。"
    )
    return "\n".join(lines)


def _collect_workflow_output_paths_by_step(
    workflow_id: str,
    repo_root: Path | str = ".",
) -> Tuple[Any, Dict[str, List[str]], List[str]]:
    """ベース Step ID → 具体 output_paths と fan-out キー一覧を収集する。

    ``collect_workflow_output_paths``（平坦なリスト）と
    ``workflow_output_paths_cover_workflow``（被覆判定）が同一の収集規則を
    共有するための内部ヘルパー。fan-out は全ワークフローに対して試みる。
    ワークフローが見つからない場合は ``(None, {}, [])`` を返す。
    """
    wf = get_workflow(workflow_id)
    if wf is None:
        return None, {}, []

    by_step: Dict[str, List[str]] = {}

    def _record(step_id: str, paths: Any) -> None:
        bucket = by_step.setdefault(step_id, [])
        for path in paths or []:
            if path not in bucket:
                bucket.append(path)

    # 固定成果物は fan-out 親にも定義されるため、展開前に必ず収集する。
    for step in wf.steps:
        _record(step.id, getattr(step, "output_paths", None))

    fanout_keys: List[str] = []
    try:
        try:
            from .fanout_expander import expand_workflow_fanout
        except ImportError:  # pragma: no cover - script execution
            from fanout_expander import expand_workflow_fanout  # type: ignore[no-redef]

        expanded = expand_workflow_fanout(wf, Path(repo_root))
        for step in expanded.steps:
            base_id = str(getattr(step, "base_step_id", "") or step.id)
            _record(base_id, getattr(step, "output_paths", None))
            key = str(getattr(step, "fanout_key", "") or "")
            if key and key not in fanout_keys:
                fanout_keys.append(key)
    except Exception:
        # catalog が未生成・不正でも固定成果物の収集は維持する。
        # 実行時 fan-out と同様、scope 解決だけを理由に workflow を停止しない。
        fanout_keys = []

    return wf, by_step, fanout_keys


def collect_workflow_output_paths(
    workflow_id: str,
    repo_root: Path | str = ".",
) -> List[str]:
    """ワークフローの全ステップの具体的な output_paths を集約して返す。

    全 StepDef の固定 output_paths に加え、catalog を使って fan-out を展開し、
    ``output_paths_template`` の ``{key}`` を解決する。AAGD の実装・テスト
    ディレクトリは既存 StepDef の downstream input 契約から補完する。
    重複を除去し、最初の出現順を維持する。ワークフローが見つからない場合は
    空リストを返す。

    Self-Improve の target scope 解決（run_workflow 内）から呼び出されるほか、
    テストから直接インポートして利用することができる。
    """
    wf, by_step, fanout_keys = _collect_workflow_output_paths_by_step(
        workflow_id,
        repo_root=repo_root,
    )
    if wf is None:
        return []

    seen: Set[str] = set()
    result: List[str] = []

    def _append(paths: Any) -> None:
        for path in paths or []:
            if path not in seen:
                seen.add(path)
                result.append(path)

    for step in wf.steps:
        _append(getattr(step, "output_paths", None))
    for step in wf.steps:
        _append(by_step.get(step.id))

    if workflow_id == "aagd":
        # 現行 AAGD StepDef はこれらを downstream required_input_paths として
        # 宣言している。Self-Improve scope には生成物側として明示的に含める。
        for key in fanout_keys:
            _append([
                f"src/test/agent/{key}.Tests",
                f"src/agent/{key}",
            ])

    return result


def workflow_output_paths_cover_workflow(
    workflow_id: str,
    repo_root: Path | str = ".",
) -> bool:
    """収集した具体 path が workflow 全体を代表しうるかを判定する。

    Self-Improve の target scope は「その workflow が生成した成果物の集合」を
    代表しなければならない。部分的な ``output_paths`` 宣言をそのまま scope と
    して採用すると、未宣言 Step の成果物が恒久的に scope 外へ落ちる
    （例: ADFDV で末尾の QA Step だけ宣言すると scope が既定の ``"."`` から
    レビュー文書 2 件へ縮小する）。

    判定規則: workflow の DAG 根（依存を持たない非コンテナ Step）が **すべて**
    1 件以上の具体 path を寄与していること。根は必ず実行され基盤成果物を
    生成するため、根の成果物すら含まない集合は workflow の末端断片であり
    全体を代表しない。fan-out Step は展開に成功して初めて寄与とみなす
    （catalog 未生成で展開できない場合、宣言した ``{key}`` 成果物が scope から
    欠落し、宣言と実 scope が不一致になるため）。

    False のとき呼び出し側は ``SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS`` の
    既定ディレクトリ（floor）へフォールバックする。
    """
    wf, by_step, _ = _collect_workflow_output_paths_by_step(
        workflow_id,
        repo_root=repo_root,
    )
    if wf is None:
        return False

    root_ids = [step.id for step in wf.get_root_steps()]
    if not root_ids:
        return False
    return all(by_step.get(step_id) for step_id in root_ids)


def _self_improve_result_succeeded(
    result: Optional[Dict[str, Any]],
    task_goal: Optional[Any],
) -> bool:
    """Post-DAG Self-Improveが上位workflowを成功させてよいか判定する。"""
    if not isinstance(result, dict):
        return False
    if result.get("stopped_reason") not in {
        "no_improvement_needed",
        "threshold_reached",
    }:
        return False
    if result.get("blocked_reason"):
        return False

    verification = result.get("final_verification")
    if (
        not isinstance(verification, dict)
        or verification.get("overall") != "PASS"
    ):
        return False

    goal_definitions = (
        task_goal.get("criterion_definitions", [])
        if isinstance(task_goal, dict)
        else []
    )
    required_ids = {
        item.get("criterion_id")
        for item in goal_definitions
        if isinstance(item, dict)
        and item.get("required_for_done") is True
        and isinstance(item.get("criterion_id"), str)
        and item.get("criterion_id")
    }
    if required_ids:
        criterion_results = result.get("final_criterion_results", [])
        if not isinstance(criterion_results, list):
            return False
        by_id = {
            item.get("criterion_id"): item
            for item in criterion_results
            if isinstance(item, dict)
        }
        for criterion_id in required_ids:
            criterion = by_id.get(criterion_id, {})
            evidence = criterion.get("evidence", [])
            if (
                criterion.get("status") != "PASS"
                or not isinstance(evidence, list)
                or not evidence
                or any(
                    not isinstance(item, dict)
                    or item.get("status") != "PASS"
                    for item in evidence
                )
            ):
                return False
        if (
            not isinstance(verification, dict)
            or verification.get("overall") != "PASS"
        ):
            return False
    return True


def _agent_fanout_scope_precondition_error(
    workflow_id: str,
    output_paths: List[str],
    repo_root: Path,
) -> str:
    """AAG/AAGDの固定成果物と全fan-out keyの実体を確認する。"""
    try:
        from .self_improve import _path_has_symlink_component
    except ImportError:  # pragma: no cover - top-level module import compatibility
        from self_improve import _path_has_symlink_component  # type: ignore[no-redef]

    def _real_file(relative: str) -> bool:
        return (
            not _path_has_symlink_component(relative, repo_root)
            and (repo_root / relative).is_file()
        )

    def _real_dir(relative: str) -> bool:
        return (
            not _path_has_symlink_component(relative, repo_root)
            and (repo_root / relative).is_dir()
        )

    if workflow_id == "aag":
        fixed = {
            "docs/agent/agent-application-definition.md",
            "docs/agent/agent-architecture.md",
            "docs/ai-agent-catalog.md",
        }
        details = [
            path for path in output_paths
            if path.startswith("docs/agent/agent-detail-")
            and path.endswith(".md")
        ]
        aag_missing = sorted(
            path for path in [*fixed, *details]
            if path not in output_paths or not _real_file(path)
        )
        if not details:
            aag_missing.append("docs/agent/agent-detail-{key}.md")
        if aag_missing:
            return "required_agent_fanout_incomplete: " + ", ".join(aag_missing)
        return ""
    if workflow_id == "aagd":
        agent_keys = {
            path.removeprefix("src/agent/").rstrip("/")
            for path in output_paths if path.startswith("src/agent/")
        }
        test_keys = {
            path.removeprefix("src/test/agent/").removesuffix(".Tests").rstrip("/")
            for path in output_paths
            if path.startswith("src/test/agent/") and path.rstrip("/").endswith(".Tests")
        }
        spec_keys = {
            path.removeprefix("docs/test-specs/").removesuffix("-test-spec.md")
            for path in output_paths
            if path.startswith("docs/test-specs/") and path.endswith("-test-spec.md")
        }
        all_keys = agent_keys | test_keys | spec_keys
        aagd_missing: List[str] = []
        definition = "docs/agent/agent-application-definition.md"
        if definition not in output_paths or not _real_file(definition):
            aagd_missing.append(definition)
        if not all_keys:
            aagd_missing.append("{agent-key}")
        if agent_keys != all_keys or test_keys != all_keys or spec_keys != all_keys:
            aagd_missing.append("fanout-key-set-mismatch")
        for key in sorted(all_keys):
            expected = (
                (f"docs/test-specs/{key}-test-spec.md", _real_file),
                (f"src/test/agent/{key}.Tests", _real_dir),
                (f"src/agent/{key}", _real_dir),
            )
            aagd_missing.extend(path for path, predicate in expected if not predicate(path))
        if aagd_missing:
            return "required_agent_fanout_incomplete: " + ", ".join(sorted(set(aagd_missing)))
        return ""
    return ""


def _uses_workflow_branch_mode(workflow_id: str, config: "SDKConfig") -> bool:
    """DAG 全体を 1 本の作業ブランチで実行する従来モードかを返す。"""
    return github_write_required(
        workflow=get_workflow(workflow_id),
        active_steps=(),
        create_issues=bool(config.create_issues),
        create_pr=bool(config.create_pr),
        enable_auto_merge=bool(getattr(config, "enable_auto_merge", False)),
    )


def _remote_cicd_step_ids(wf: Any, active_steps: Set[str]) -> Set[str]:
    """active_steps のうち Step 単位 remote CI/CD 対象 ID を返す。"""
    return {
        s.id for s in getattr(wf, "steps", [])
        if not getattr(s, "is_container", False)
        and s.id in active_steps
        and bool(getattr(s, "requires_remote_cicd", False))
    }


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
    # ただし `_ARTIFACT_KEY_TO_EXPECTED_PATH` に登録済みのキーは「同一ワークフロー内の
    # 先行 Step が生成するが現時点ではディスクに存在しない」forward-reference として
    # 正常扱いし、警告を抑制する（false-positive の主要因だった）。
    truly_unknown = [
        k for k in step.consumed_artifacts
        if k not in existing_artifacts and k not in _ARTIFACT_KEY_TO_EXPECTED_PATH
    ]
    if truly_unknown:
        import warnings as _warnings
        _warnings.warn(
            f"Step.{step.id}: consumed_artifacts に未知のキーが含まれています: {truly_unknown}。"
            f"登録済みキー: {sorted(_ARTIFACT_KEY_TO_EXPECTED_PATH.keys())}",
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


# NOTE: subissues.md フォーマット遵守は Skill 経由の規約で担保する:
#   - Skill `task-dag-planning` §subissues.md 作成規約（SKILL.md 本体に明記）
#   - Skill `agent-common-preamble` §subissues.md コミット前バリデーション
#     （`.github/scripts/{bash,powershell}/validate-subissues.{sh,ps1}` を全 Agent 必須化）
# FR-CLI-70: CLI / GUI 実行経路 (`_build_step_prompt`) では subissues.md の
# フォーマット例をインライン注入しない。CLI / GUI Orchestrator 配下では
# workflow DAG / fan-out で分割を表現し、`subissues.md` runtime fork は
# legacy / 明示 opt-in であるため、常時注入は誤った作業指示になる。
# 失敗時は `parse_subissues_md` がテーブル形式を検知して actionable なエラーを返す (P-A)。


# Sub-2 (A-2): step 種別ごとの再利用ルール文（既存成果物再利用のヒント）。
# キー = step_kind、値 = 末尾に付与する箇条書きルール文の行リスト。
# default はワークフロー単位 (`_build_reuse_context` 直接呼び出し) で使用される長文。
_REUSE_RULES_BY_KIND: Dict[str, List[str]] = {
    "catalog": load_prompt_file(
        "runtime/orchestrator/reuse-rules-catalog.prompt.md"
    ).splitlines(),
    "tests": load_prompt_file(
        "runtime/orchestrator/reuse-rules-tests.prompt.md"
    ).splitlines(),
    "code": load_prompt_file(
        "runtime/orchestrator/reuse-rules-code.prompt.md"
    ).splitlines(),
    "docs": load_prompt_file(
        "runtime/orchestrator/reuse-rules-docs.prompt.md"
    ).splitlines(),
    "default": load_prompt_file(
        "runtime/orchestrator/reuse-rules-default.prompt.md"
    ).splitlines(),
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

    artifact_lines: List[str] = []

    for key, paths in existing_artifacts.items():
        if isinstance(paths, list):
            for p in paths[:10]:  # 上限10件表示
                artifact_lines.append(f"- `{p}`")
            if len(paths) > 10:
                artifact_lines.append(f"  ...他 {len(paths) - 10} ファイル")
        else:
            artifact_lines.append(f"- `{paths}`")

    rules = _REUSE_RULES_BY_KIND.get(step_kind, _REUSE_RULES_BY_KIND["default"])
    return _REUSE_CONTEXT_TEMPLATE.format(
        artifact_lines="\n".join(artifact_lines),
        reuse_rules="\n".join(rules),
    )


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
            format_workiq_tool_not_invoked_warning,
        )
    except ImportError:
        from workiq import (  # type: ignore[no-redef]
            build_workiq_mcp_config, query_workiq,
            WorkIQPrefetchResult, WORKIQ_MCP_SERVER_NAME,
            extract_workiq_tool_name_from_event,
            format_workiq_tool_not_invoked_warning,
        )

    _start = time.monotonic()

    try:
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

    try:
        client = _create_copilot_client_from_config(config, log_level="error")
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため Work IQ 事前取得をスキップします。"
        )
        return WorkIQPrefetchResult(
            error_type="sdk_import_failure",
            error_message="Copilot SDK が利用できません",
            elapsed_seconds=time.monotonic() - _start,
        )
    await client.start()

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id, request_timeout=config.workiq_request_timeout)
        _session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            # Phase 2 (Resume): 決定論的 session_id を付与
            "session_id": _orchestrator_session_id(
                config, "orchestrator", suffix="workiq-prefetch"
            ),
        }
        # FR-CLI-76 (v2.51): `mcp_servers` を明示する経路は共通の縮約が効かないため、
        # プラグイン由来の `workiq` が併存する。宣言分を併合して自動探索を止める。
        _apply_repository_mcp_scope(_session_opts)
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        # 明示モデル時はそのまま渡す。空 / None は payload から省略（CLI 既定動作）。
        _wire_model = to_wire_model(config.model)
        if _wire_model:
            _session_opts["model"] = _wire_model
        _apply_reasoning_effort(_session_opts, config, kind="main")
        session = await _create_session_with_auto_reasoning_fallback(
            client,
            _session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="orchestrator",
            console=console,
        )
        attach_mcp_io_event_logger(session, console.mcp_io_logger, step_id="orchestrator")

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
                console.warning(
                    format_workiq_tool_not_invoked_warning(
                        "prefetch",
                        detail=(
                            ""
                            if _has_text
                            else "エージェントが Work IQ 指示を実行しませんでした（応答本文もありません）。"
                        ),
                    )
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
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため AKM Work IQ 検証をスキップします。"
        )
        return

    client = _create_copilot_client_from_config(config, log_level="error")
    await client.start()

    verified_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        # Work IQ MCP 付きセッションを作成
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id, request_timeout=config.workiq_request_timeout)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            # Phase 2 (Resume): 決定論的 session_id を付与
            "session_id": _orchestrator_session_id(
                config, "akm-verify", suffix="workiq"
            ),
        }
        # FR-CLI-76 (v2.51): `mcp_servers` を明示する経路は共通の縮約が効かないため、
        # プラグイン由来の `workiq` が併存する。宣言分を併合して自動探索を止める。
        _apply_repository_mcp_scope(session_opts, workflow_id="akm")
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(config.model)
        if _wire_model:
            session_opts["model"] = _wire_model
        _apply_reasoning_effort(session_opts, config, kind="main")

        session = await _create_session_with_auto_reasoning_fallback(
            client,
            session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="orchestrator",
            console=console,
        )
        attach_mcp_io_event_logger(session, console.mcp_io_logger, step_id="orchestrator")

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
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning(
            "Copilot SDK が利用できないため AKM Work IQ 取り込みをスキップします。"
        )
        return

    client = _create_copilot_client_from_config(config, log_level="error")
    await client.start()

    queried_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id, request_timeout=config.workiq_request_timeout)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            "session_id": _orchestrator_session_id(
                config, "akm-ingest", suffix="workiq"
            ),
        }
        # FR-CLI-76 (v2.51): `mcp_servers` を明示する経路は共通の縮約が効かないため、
        # プラグイン由来の `workiq` が併存する。宣言分を併合して自動探索を止める。
        _apply_repository_mcp_scope(session_opts, workflow_id="akm")
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(config.model)
        if _wire_model:
            session_opts["model"] = _wire_model
        _apply_reasoning_effort(session_opts, config, kind="main")

        session = await _create_session_with_auto_reasoning_fallback(
            client,
            session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="orchestrator",
            console=console,
        )
        attach_mcp_io_event_logger(session, console.mcp_io_logger, step_id="orchestrator")

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
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning("Copilot SDK が利用できないため ARD Work IQ ユースケース取得をスキップします。")
        return

    client = _create_copilot_client_from_config(config, log_level="error")
    await client.start()

    try:
        _mcp = build_workiq_mcp_config(tenant_id=config.workiq_tenant_id, request_timeout=config.workiq_request_timeout)
        session_opts: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "streaming": True,
            "mcp_servers": _mcp,
            "session_id": _orchestrator_session_id(
                config, "ard-workiq", suffix="usecase"
            ),
        }
        # FR-CLI-76 (v2.51): `mcp_servers` を明示する経路は共通の縮約が効かないため、
        # プラグイン由来の `workiq` が併存する。宣言分を併合して自動探索を止める。
        _apply_repository_mcp_scope(session_opts, workflow_id="ard")
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(config.model)
        if _wire_model:
            session_opts["model"] = _wire_model
        _apply_reasoning_effort(session_opts, config, kind="main")

        session = await _create_session_with_auto_reasoning_fallback(
            client,
            session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="orchestrator",
            console=console,
        )
        attach_mcp_io_event_logger(session, console.mcp_io_logger, step_id="orchestrator")

        try:
            console.workiq_prompt(
                workiq_query, label="Work IQ プロンプト [ARD usecase]"
            )
            workiq_result = await query_workiq(
                session, workiq_query,
                timeout=config.workiq_per_question_timeout,
            )
            console.workiq_response(
                workiq_result or "", label="Work IQ 応答 [ARD usecase]"
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


# --- ARD: Step 1.2 → Step 2 bridging hook ---
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
    """選択 SR + Step 1.2 出力から target_business 説明文を生成する。"""
    sr_id = str(getattr(selected_sr, "id", "SR-UNKNOWN"))
    sr_title = str(getattr(selected_sr, "title", "")).strip() or sr_id

    if config.dry_run:
        return f"[dry-run] target_business based on {sr_id}: {sr_title}"

    try:
        business_requirement_content = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        console.warning(f"Step 1.2 出力の読み込みに失敗したため SR タイトルで代替します: {exc}")
        return sr_title

    try:
        from copilot.session import PermissionHandler
    except ImportError:
        console.warning("Copilot SDK が利用できないため SR タイトルで代替します。")
        return sr_title

    client = _create_copilot_client_from_config(
        config,
        log_level="error",
        cli_args=config.cli_args,
    )
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
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(config.model)
        if _wire_model:
            session_opts["model"] = _wire_model
        _apply_reasoning_effort(session_opts, config, kind="main")
        session = await _create_session_with_auto_reasoning_fallback(
            client,
            session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="orchestrator",
            console=console,
            workflow_id="ard",
        )
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
    """ARD グループ 1（実 Step 1 → 1.1 → 1.2）完了直後の SR 抽出・選択・target_business 生成。

    SR の抽出元 `docs/company-business-requirement.md` の producer は Step 1.2 のため、
    本フックは Step 1.2 完了時にのみ呼ばれる。
    """
    if (params.get("target_business", "") or "").strip():
        console.status("target_business が指定済みのため、SR からの自動生成をスキップします。")
        return

    output_path = Path("docs/company-business-requirement.md")
    if not output_path.exists():
        console.warning("Step 1.2 出力ファイルが見つかりません。Step 2 は既存 target_business で継続します。")
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

    # FR-WF-ARD-03: 明示 SR-ID はグループ 1 + 2 の bridge 選択だけに使う。
    # Step 1.2 後の hook 自体はグループ 1 + 4 等でも target_business を補完するため、
    # bridge 外では明示 ID を選択層へ渡さない。
    selected_steps = {
        str(step_id) for step_id in (params.get("selected_steps") or [])
    }
    selection_params = params
    if "2" not in selected_steps and params.get("target_recommendation_id"):
        selection_params = dict(params)
        selection_params.pop("target_recommendation_id", None)

    selected_sr = _select_recommendation(
        recommendations=recommendations,
        config=config,
        params=selection_params,
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




def _resolve_config_disabled_steps(
    wf: Any,
    workflow_id: str,
    config: Any,
) -> FrozenSet[str]:
    """`StepDef.disabled_when_config` と設定値から無効化 Step ID を解決する。

    宣言されたキーだけを設定オブジェクトから読み、値が一致する Step を返す。
    宣言が無い workflow では設定を一切参照しない。

    Args:
        wf: WorkflowDef。
        workflow_id: ワークフロー ID（後方互換エイリアス可）。
        config: SDKConfig 等の設定オブジェクト。

    Returns:
        無効化する Step ID の集合。該当なしなら空集合。
    """
    declared_keys = {
        key
        for step in getattr(wf, "steps", [])
        for key in (getattr(step, "disabled_when_config", None) or {})
    }
    if not declared_keys or config is None:
        return frozenset()
    try:
        from .workflow_registry import resolve_disabled_step_ids
    except ImportError:  # pragma: no cover - script execution
        from workflow_registry import resolve_disabled_step_ids  # type: ignore[no-redef]
    config_values = {
        key: getattr(config, key) for key in declared_keys if hasattr(config, key)
    }
    if not config_values:
        return frozenset()
    return resolve_disabled_step_ids(workflow_id, config_values)


def _should_use_statusline(console: Any, config: SDKConfig) -> bool:
    """FR-RTO-02: Workbench を使わない実行で 1 行ステータスラインを使うか判定する。

    `quiet` / `final_only` では追加表示をしない（NFR-OBS-03 と矛盾させない）。
    """
    if getattr(config, "quiet", False) or getattr(console, "quiet", False):
        return False
    if getattr(config, "final_only", False) or getattr(console, "final_only", False):
        return False
    if not getattr(config, "pricing_statusline_enabled", True):
        return False
    workbench_active = getattr(console, "workbench_enabled", False) and not getattr(
        config, "no_workbench", False
    )
    return not workbench_active


def _build_statusline_state(metrics: Any, *, workflow_started_at: float) -> Any:
    """FR-RTO-05: 集計から StatusLine 表示状態を作る（未取得値は埋めない）。"""
    try:
        from .statusline import StatusLineState
    except ImportError:  # pragma: no cover - script 実行経路
        from statusline import StatusLineState  # type: ignore[no-redef]

    return StatusLineState(
        workflow_started_at=workflow_started_at,
        context_current=metrics.context_current,
        context_limit=metrics.context_limit,
        tokens_in=metrics.input_tokens_total,
        tokens_out=metrics.output_tokens_total,
        aiu_total=metrics.aiu_total if metrics.aiu_nano_total > 0 else None,
        premium_requests_total=metrics.display_reqs,
    )


def _attach_runtime_statusline(console: Any, config: SDKConfig, *, workflow_started_at: float) -> Any:
    """Workbench 無効時の TTY で 1Hz ステータスラインを開始する。"""
    if not _should_use_statusline(console, config):
        return None
    try:
        from .statusline import StatusLine
    except ImportError:  # pragma: no cover - script 実行経路
        from statusline import StatusLine  # type: ignore[no-redef]

    registry = console.runtime_metrics()
    status_line = StatusLine(
        state_provider=lambda: _build_statusline_state(
            registry.totals(), workflow_started_at=workflow_started_at
        )
    )
    if not status_line.enabled:
        return None
    status_line.start()
    return status_line


def _format_runtime_summary(metrics: Any) -> str:
    """FR-RTO-05: 実行終了時の 1 行サマリー（整形は core 実装に単一化）。"""
    try:
        from .runtime_observability import format_runtime_summary
    except ImportError:  # pragma: no cover - script 実行経路
        from runtime_observability import format_runtime_summary  # type: ignore[no-redef]

    return format_runtime_summary(metrics)


def _emit_runtime_summary(console: Any, config: SDKConfig) -> None:
    """非 TTY 実行の終了時にだけ、集計を 1 回出力する（FR-RTO-02）。"""
    if getattr(config, "quiet", False) or getattr(console, "quiet", False):
        return
    if getattr(config, "final_only", False) or getattr(console, "final_only", False):
        return
    if getattr(console, "_is_tty", False):
        return
    try:
        metrics = console.runtime_metrics().totals()
    except Exception:
        return
    try:
        console.status(_format_runtime_summary(metrics))
    except Exception:
        pass


def _attach_runtime_observability(
    console: Console,
    config: SDKConfig,
    workflow_id: str,
    *,
    app_ids: Optional[List[str]] = None,
) -> Optional[Any]:
    """FR-RTO-03 / FR-RTO-06: 観測イベントの記録器を生成し Console へ接続する。

    `HVE_WORK_ROOT` 未設定時と dry-run では記録せず ``None`` を返す。
    """
    try:
        from .runtime_observability import RuntimeEventRecorder, make_instance_id
    except ImportError:  # pragma: no cover - script 実行経路
        from runtime_observability import RuntimeEventRecorder, make_instance_id  # type: ignore[no-redef]

    # APP スコープが 1 件に確定しているときだけ instance を APP 単位へ細分化する。
    single_app_id = app_ids[0] if app_ids and len(app_ids) == 1 else None
    try:
        console.set_runtime_identity(
            workflow_id=workflow_id,
            instance_id=make_instance_id(workflow_id, single_app_id),
        )
    except AttributeError:  # pragma: no cover - 旧 Console 互換
        pass

    recorder = RuntimeEventRecorder.from_env(
        dry_run=bool(getattr(config, "dry_run", False)),
        repo_root=Path.cwd(),
        warn=getattr(console, "warning", None),
    )
    if not recorder.enabled:
        recorder.close()
        return None
    console.attach_event_recorder(recorder)
    return recorder


def _emit_github_target_event(
    console: Any,
    *,
    repo: Any = None,
    issue_number: Any = None,
    pr_number: Any = None,
    branch: Any = None,
    base_branch: Any = None,
    created_by_hve: Any = None,
    delete_local_merged_branch: Any = None,
) -> None:
    """FR-RTO-08: 確定した GitHub target を既存の観測イベント経路で 1 件通知する。

    値の検証は `runtime_observability.github_target_fields` の単一実装へ委譲する
    （FR-MAINT-07）。確定値が 1 件も無い場合は送出しない。送出失敗は実行へ
    波及させないが、例外型名だけを警告として残す（NFR-RTO-03 / FR-RTO-04）。
    """
    try:
        from .runtime_observability import GITHUB_TARGET_KIND, github_target_fields
    except ImportError:  # pragma: no cover - script 実行経路
        try:
            from runtime_observability import (  # type: ignore[no-redef]
                GITHUB_TARGET_KIND,
                github_target_fields,
            )
        except ImportError:
            return

    fields = github_target_fields(
        repo=repo,
        issue_number=issue_number,
        pr_number=pr_number,
        branch=branch,
        base_branch=base_branch,
        created_by_hve=created_by_hve,
        delete_local_merged_branch=delete_local_merged_branch,
    )
    if not fields:
        return
    emit = getattr(console, "stats_event", None)
    if emit is None:
        return
    try:
        emit(GITHUB_TARGET_KIND, **fields)
    except Exception as exc:
        # 送出失敗で Workflow を止めない。本文は残さず例外型名だけを通知する。
        warn = getattr(console, "warning", None)
        if warn is not None:
            try:
                warn(f"GitHub target イベントの送出に失敗しました（{type(exc).__name__}）。実行は継続します。")
            except Exception:
                pass


def _attach_mcp_io_logging(console: Console, config) -> Optional[Any]:
    """FR-MCPLOG-01 / 02: MCP 通信ログの記録器を生成し Console へ接続する。

    `HVE_WORK_ROOT` 未設定時と dry-run では記録せず ``None`` を返す。
    """
    logger = McpIoLogger.from_env(
        dry_run=bool(getattr(config, "dry_run", False)),
        warn=getattr(console, "warning", None),
    )
    if not logger.enabled:
        logger.close()
        return None
    console.attach_mcp_io_logger(logger)
    return logger


def _start_index_watchers(config) -> None:
    """起動時の索引差分更新を待ってから mdq / cq watcher を起動する（FR-CLI-77）。

    同一の索引 DB へ 2 つの書き込み経路を同時に存在させないため、待ち合わせは
    watcher の生成より前に行う。
    """
    index_refresh.wait_until_idle()

    # ファイル追加・更新・削除を OS イベントで検知し索引を逐次更新する。
    # 既存の `python -m mdq index` / `python -m cq index` による手動更新は維持される。
    # watchdog 未導入や起動失敗は警告ログのみで本体実行を妨げない。
    # Cloud Agent / GitHub Actions では本機能を使用しない（config.mdq_watch=False で無効化）。
    _mdq_watcher = None
    if getattr(config, "mdq_watch", True):
        try:
            from mdq.watcher import MdqWatcher  # type: ignore
            from mdq.cli import DEFAULT_ROOTS as _MDQ_ROOTS  # type: ignore
            from mdq.store import DEFAULT_DB_PATH as _MDQ_DB  # type: ignore
            _mdq_watcher = MdqWatcher(
                repo_root=Path.cwd(),
                roots=_MDQ_ROOTS,
                db_path=_MDQ_DB,
                debounce_ms=getattr(config, "mdq_watch_debounce_ms", 500),
            )
            if not _mdq_watcher.start():
                _mdq_watcher = None
        except Exception as exc:  # pragma: no cover - defensive
            print(f"WARN: mdq watcher 起動をスキップしました ({exc})", file=sys.stderr)
            _mdq_watcher = None
    # 本関数は watcher を起動したらすぐ戻るため、停止は atexit で回収する。
    if _mdq_watcher is not None:
        import atexit as _atexit
        _atexit.register(_mdq_watcher.stop)

    # cq は設定不在を fail-closed で拒否するため（FR-CQ-01）、設定が無い
    # リポジトリでは警告のみで本体実行を継続する。
    _cq_watcher = None
    if getattr(config, "cq_watch", True):
        try:
            from cq import config as _cq_config  # type: ignore
            from cq import store as _cq_store  # type: ignore
            from cq.watcher import DEFAULT_DEBOUNCE_MS as _CQ_DEBOUNCE  # type: ignore
            from cq.watcher import CqWatcher  # type: ignore
            _cq_repo_root = Path.cwd()
            _cq_profile_name = next(iter(_cq_config.resolve_profiles(_cq_repo_root)))
            _cq_watcher = CqWatcher(
                _cq_repo_root,
                _cq_config.resolve_profile(_cq_repo_root, _cq_profile_name),
                db_path=_cq_repo_root / _cq_store.db_path_for(_cq_profile_name),
                debounce_ms=getattr(config, "cq_watch_debounce_ms", _CQ_DEBOUNCE),
            )
            if not _cq_watcher.start():
                _cq_watcher = None
        except Exception as exc:  # pragma: no cover - defensive
            print(f"WARN: cq watcher 起動をスキップしました ({exc})", file=sys.stderr)
            _cq_watcher = None
    if _cq_watcher is not None:
        import atexit as _atexit
        _atexit.register(_cq_watcher.stop)


def _start_index_watchers_when_idle(config):
    """watcher 起動を専用スレッドへ退避する。待ち合わせで本体実行を止めないため。"""
    if getattr(config, "dry_run", False):
        return None
    if not getattr(config, "mdq_watch", True) and not getattr(config, "cq_watch", True):
        return None
    import threading as _threading

    thread = _threading.Thread(
        target=_start_index_watchers, args=(config,),
        name="hve-index-watchers", daemon=True,
    )
    thread.start()
    return thread


async def run_workflow(
    workflow_id: str,
    params: Optional[dict] = None,
    config: Optional[SDKConfig] = None,
    *,
    orchestrator_ctx: Optional["OrchestratorContext"] = None,
) -> dict:
    """ワークフローを SDK でローカル実行する。

    --create-issues 時のフロー:
      1. 新ブランチ作成 + checkout
        2. Issue 作成（Root + Sub-Issue。指定時は新規 Root を Copilot cloud agent へ割当）
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
          workflow_id, completed, failed, skipped, blocked, elapsed_total,
          code_review_error, pr_number, root_issue_num, working_branch, error

        ``blocked`` (T-H1H2b): strict モードで Pre-check (入力成果物または
        必須 Skill) 失敗を検出した場合に該当 step ID のリストが入る。上位
        レイヤーは ``failed`` と区別して「停止」として扱える。それ以外は空配列。
    """
    if config is None:
        config = SDKConfig()

    # AAG/AAGD は生成する Agent の能力契約を既定で Post-DAG 再評価する。
    # 明示的な --no-self-improve / scope=disabled は安全弁として優先する。
    # 呼び出し元の config を別 workflow で再利用しても既定値を汚染しないよう、
    # 自動有効化は shallow copy 上だけで行う。
    if (
        workflow_id in {"aag", "aagd"}
        and not config.self_improve_skip
        and config.self_improve_scope != "disabled"
    ):
        config = copy.copy(config)
        config.auto_self_improve = True

    # run_id が未設定の場合、ワークフロー実行開始時に1回生成する（並列安全性）
    if not config.run_id:
        config.run_id = generate_run_id()

    # GUI/外部プロセスから run_id を観測できるよう、確定後に 1 行のマーカーを
    # stderr へ出力する（GUI は stderr=STDOUT で受け取る）。
    # フォーマットは workbench_logger._RUN_ID_PATTERN と一致させること。
    try:
        print(f"[hve] run_id={config.run_id}", file=sys.stderr, flush=True)
    except Exception:
        pass

    # markdown-query Skill 利用ログ (.mdq/usage.jsonl) と run_journal の
    # 紐付けのため、子プロセスへ実行コンテキストを環境変数で伝播する。
    # 設定は os.environ への書き込みに留め、Skill / CLI 側で読み取る。
    # 既知の制約: 本関数は async で複数の return path を持つため env の
    # 完全な復元 (try/finally) は v1.1 スコープ外。同一プロセスで複数
    # workflow を直列実行する場合、最後に設定された run_id が残る点に注意。
    # 通常運用 (1 プロセス = 1 workflow) では問題ない。
    try:
        os.environ["HVE_RUN_ID"] = str(config.run_id)
        os.environ["HVE_WORKFLOW_ID"] = str(workflow_id)
    except Exception:
        pass

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

    # FR-RTO-03 / FR-RTO-06: 実行時観測イベントの記録器を接続する。
    # 早期 return が多い関数のため、mdq / cq watcher と同じく atexit でも閉じる。
    _rt_recorder = _attach_runtime_observability(
        console,
        config,
        workflow_id,
        app_ids=(params or {}).get("app_ids"),
    )
    if _rt_recorder is not None:
        import atexit as _atexit

        _atexit.register(_rt_recorder.close)

    # FR-MCPLOG-01 / 02: MCP 通信ログも同じライフサイクルで扱う。
    _mcp_io_logger = _attach_mcp_io_logging(console, config)
    if _mcp_io_logger is not None:
        import atexit as _atexit

        _atexit.register(_mcp_io_logger.close)

    start_total = time.time()
    _start_monotonic = time.monotonic()

    # --- mdq / cq リアルタイム索引更新（HVE CLI Orchestrator 限定）---
    # 起動時の索引差分更新（FR-CLI-77）が終わるまで watcher を起動しない。
    _start_index_watchers_when_idle(config)

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

    _workflow_branch_mode = _uses_workflow_branch_mode(wf.id, config)
    # FR-CLI-83: 明示的な Issue / PR 作成でだけ current branch mode を選べる。
    # remote CI/CD の実行契約（ADFDV / Step-scoped）が要求する branch は無効化しない。
    _explicit_github_write = bool(config.create_issues or config.create_pr)
    _reuse_current_branch = (
        _workflow_branch_mode
        and _explicit_github_write
        and not bool(getattr(config, "create_working_branch", True))
    )

    # フェーズ構成の動的算出
    _phases: List[str] = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
    if _workflow_branch_mode:
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
        if _workflow_branch_mode:
            # "後処理 (git push + PR)" の前に挿入
            for i, phase_name in enumerate(_phases):
                if "後処理" in phase_name:
                    idx = i
                    break
        _phases.insert(idx, "自己改善ループ")
    if _workflow_branch_mode:
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

    params_were_provided = params is not None
    if params is None:
        params = {}
    # Agent プロンプトでは done ラベル付与を要求しない（付与は orchestrator 側で実施）。
    execution_mode = "local"

    # dry_run 時は常に非対話モード（インタラクティブプロンプト不要）
    # CLI 引数が揃っていれば非対話モード、そうでなければ対話モード
    if config.dry_run or _is_non_interactive(
        wf,
        params if params_were_provided else None,
    ):
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
        _apply_interactive_review_choice(config, effective_params)

    if wf.id == "adi":
        try:
            effective_params["target_scope"] = _normalize_adi_target_scope(
                effective_params.get("target_scope")
            )
        except ValueError as exc:
            error = str(exc)
            console.error(error)
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "elapsed_total": time.time() - start_total,
                "error": error,
            }

    # dry_run を params に反映
    if config.dry_run:
        effective_params["dry_run"] = True

    console.phase_end(p, _total_phases, "パラメータ収集", time.time() - phase_start)

    # --- 2.5. 推薦アーキテクチャ APP-ID フィルタ ---
    _ARCH_FILTER_WORKFLOWS = {"aad-web", "asdw-web", "adfd", "adfdv"}
    if wf.id in _ARCH_FILTER_WORKFLOWS:
        if wf.id == "asdw-web":
            _app_scope_error = _validate_asdw_data_deploy_requested_app_scope(
                effective_params
            )
            if _app_scope_error:
                console.error(_app_scope_error)
                elapsed = time.time() - start_total
                return {
                    "workflow_id": workflow_id,
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "elapsed_total": elapsed,
                    "error": _app_scope_error,
                }
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
    # ARD: グループ ID (1/2/3/4) を現行の実 Step ID
    # (1,1.1,1.2 / 2 / 2.1 / 3.1,3.2,3.3) に展開する。
    # Wizard / CLI 側はグループ ID を返す契約のため、フィルタ前にここで展開する。
    # 既に実 Step ID が直接渡された場合は素通し（後方互換）。
    # 展開ロジックは hve.workflow_registry の SSOT (expand_group_step_ids) を使用。
    if workflow_id == "ard" and selected_step_ids:
        from hve.workflow_registry import expand_group_step_ids
        _expanded: List[str] = expand_group_step_ids("ard", selected_step_ids)
        # ARD Step 2.1 (KPI/OKR、任意): 以下のいずれかで active_steps に含まれる。
        #   (a) `include_kpi_okr=True` パラメータ（CLI `--include-kpi-okr` / 対話ウィザード）
        #   (b) `selected_steps` のグループ "3" または実 Step "2.1" が直接選択される。
        # Step 2.1 は Step 2 出力（または skip_fallback で Step 1.2 出力）を入力として
        # docs/recommended-kpi-okr.md を生成し、後続 Step 3.x / aas が任意参照する。
        _include_kpi_okr = bool(effective_params.get("include_kpi_okr", False))
        _kpi_step_selected_directly = (
            "3" in selected_step_ids or "2.1" in selected_step_ids
        )
        if _kpi_step_selected_directly and not _include_kpi_okr:
            # GUI / CLI 経路: "3" が直接選択されたら include_kpi_okr フラグも True に同期させ、
            # 後続の任意参照（Step 3.x / aas）が一貫して動作するようにする。
            effective_params["include_kpi_okr"] = True
            _include_kpi_okr = True
        _has_step2_or_group4 = any(
            sid == "2" or sid in {"3.1", "3.2", "3.3"}
            for sid in _expanded
        )
        if _include_kpi_okr and _has_step2_or_group4:
            if "2.1" not in _expanded:
                # Step 2 の直後、Step 3.x の直前に挿入する（実行順序の見やすさのため）
                _insert_idx = len(_expanded)
                for _i, _sid in enumerate(_expanded):
                    if _sid in {"3.1", "3.2", "3.3"}:
                        _insert_idx = _i
                        break
                _expanded.insert(_insert_idx, "2.1")
        elif _include_kpi_okr and not _has_step2_or_group4 and not _kpi_step_selected_directly:
            console.warning(
                "include_kpi_okr=True が指定されましたが、Step 2 / Step 4 が選択されていないため "
                "Step 2.1 (KPI/OKR 定義) は実行されません。"
            )
        _seen: Set[str] = set()
        selected_step_ids = []
        for step_id in _expanded:
            if step_id in _seen:
                continue
            _seen.add(step_id)
            selected_step_ids.append(step_id)
    active_steps: Set[str] = resolve_selected_steps(wf, selected_step_ids)

    # FR-CLI-86: `--resume-run` 指定時は当該 run で成功済みの Step を実行対象から外す。
    # 記録が 1 件も無い run-id は fail-closed とし、全 Step の再実行へ縮退させない。
    _resume_run_id = str(effective_params.get("resume_run") or "").strip()
    if _resume_run_id:
        _done = run_progress.completed_steps(_resume_run_id)
        if _done is None:
            _resume_error = (
                f"--resume-run に指定された run-id の進捗記録が見つかりません: {_resume_run_id}"
            )
            console.error(_resume_error)
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "blocked": sorted(active_steps),
                "elapsed_total": time.time() - start_total,
                "error": _resume_error,
            }
        _resume_skipped = sorted(active_steps & _done)
        if _resume_skipped:
            active_steps -= _done
            console.event(
                "再実行で成功済みとしてスキップするステップ: " + ", ".join(_resume_skipped)
            )

    # FR-CLI-87: 承認ゲートは既定無効。有効時だけ Wave 境界で確認を出す。
    _approval_gates_enabled = bool(effective_params.get("approval_gates"))

    # 設定値による Step 無効化: `StepDef.disabled_when_config` の宣言に一致する Step を
    # 実行対象から外す。外された Step は DAG 上 skip 扱いとなり、依存先としては解決済みと
    # みなされるため下流 Step は到達不能にならない。
    _config_disabled = _resolve_config_disabled_steps(wf, workflow_id, config)
    _disabled_active = sorted(active_steps & _config_disabled)
    if _disabled_active:
        active_steps -= _config_disabled
        console.event(
            "設定により無効化したステップ: " + ", ".join(_disabled_active)
        )

    # --- FR-CLI-82: GitHub 書き込み設定の起動前整合性 preflight ---
    # active step 解決後、dry-run 計画・branch 作成・Agent session より前に行う。
    # CLI / GUI Orchestrator 配下は remote まで検証し、ライブラリ直接呼び出しは
    # 副作用を増やさないためローカル判定だけに限定する。
    _startup_check = validate_startup_configuration(
        workflow=wf,
        active_steps=active_steps,
        create_issues=bool(config.create_issues),
        create_pr=bool(config.create_pr),
        enable_auto_merge=bool(getattr(config, "enable_auto_merge", False)),
        repo=config.repo,
        token=config.resolve_token(),
        base_branch=config.base_branch,
        create_working_branch=bool(
            getattr(config, "create_working_branch", True)
        ),
        check_remote=orchestrator_ctx is not None,
        repo_root=Path.cwd(),
    )
    if not _startup_check.is_ok():
        _startup_error = format_startup_preflight_errors(_startup_check)
        console.error(_startup_error)
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "blocked": sorted(active_steps),
            "elapsed_total": time.time() - start_total,
            "error": _startup_error,
        }

    # --- FR-DAG-07 / FR-DAG-08: Step パラメータ契約の既定値適用と pre-flight ---
    # DAG 実行はもちろん dry-run 計画表示よりも前に判定する。判定材料は起動時点で
    # 出揃っており、Step 実行時まで遅らせると長時間実行の全損を招くため。
    # 対象は下流へ渡る正本（StepRunner へ workflow_params として渡る）effective_params。
    try:
        from .workflow_registry import apply_step_default_params
    except ImportError:
        from workflow_registry import apply_step_default_params  # type: ignore[no-redef]
    _applied_defaults = apply_step_default_params(wf, active_steps, effective_params)
    if _applied_defaults:
        console.event(
            "既定値を適用したパラメータ: " + ", ".join(_applied_defaults)
        )
    _param_check = _check_required_workflow_params_for_active_steps(
        wf=wf,
        active_steps=active_steps,
        params=effective_params,
        console=console,
    )
    if _param_check["should_abort"]:
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "blocked": list(_param_check["blocked_step_ids"]),
            "elapsed_total": time.time() - start_total,
            "error": _param_check["error"],
        }

    _ard_force_serial = (
        workflow_id == "ard"
        and "1.2" in active_steps
        and "2" in active_steps
        and not (effective_params.get("target_business", "") or "").strip()
    )
    effective_max_parallel, _max_parallel_source = _resolve_max_parallel(
        workflow=wf,
        config_max_parallel=config.max_parallel,
        ard_force_serial=_ard_force_serial,
    )
    wf_for_dag = wf
    if _ard_force_serial:
        # bridge mode: target_business 未指定 + グループ 1 & Step 2 同時実行時、
        # Step 2 を Step 1.2（SR 抽出元の producer）に依存させて直列化する。
        # Step 2.1 は静的に depends_on=["2"] のため Step 2 完了後に自動的に直列化される
        # （effective_max_parallel=1 のため Step 2.1 と Step 3.1 は順次実行）。
        try:
            wf_for_dag = copy.deepcopy(wf)
            _step2 = wf_for_dag.get_step("2")
            if _step2 is not None and "1.2" not in (_step2.depends_on or []):
                _step2.depends_on = list(_step2.depends_on or []) + ["1.2"]
        except Exception as exc:
            console.warning(f"ARD 直列DAGの構築に失敗したため通常DAGで続行します: {exc}")
            wf_for_dag = wf
            _ard_force_serial = False
            effective_max_parallel, _max_parallel_source = _resolve_max_parallel(
                workflow=wf,
                config_max_parallel=config.max_parallel,
                ard_force_serial=False,
            )

    console.event(f"実行対象ステップ数: {len(active_steps)}")
    if _ard_force_serial:
        console.event("ARD bridge mode: Step 1.2 → Step 2 → Step 2.1 を直列実行します。")
    console.phase_end(p, _total_phases, "ステップフィルタリング", time.time() - phase_start)

    # Fan-out 事前展開（fanout-fix）:
    # build_dag_plan / DAGExecutor は dag_plan 併用時に fan-out 自動展開を行わないため、
    # orchestrator 側で expand_workflow_fanout を呼び active_steps も同期拡張する。
    # 注: dry-run 経路（直後の dry_run_plan）と本番経路（後段の dag_plan）の両方が
    # 展開後 wf_for_dag / active_steps を参照するため、ここで一度だけ展開する。
    # APP-ID フィルタ:
    #   effective_params["app_ids"] が指定されている場合（GUI で Step 1 の対象
    #   APP-ID を選択した場合）、その APP-ID に紐付く fan-out キーのみに絞り込む。
    #   未指定の場合は全 fan-out キーを展開する（後方互換）。
    #   詳細: hve/fanout_expander.py _APP_ID_FILTERABLE_PARSERS 参照。
    _expand_info: Any = None
    try:
        _expanded_wf, _expanded_active, _expand_info = _expand_workflow_for_dag(
            wf_for_dag, active_steps, Path.cwd(),
            app_ids=effective_params.get("app_ids"),
        )
        wf_for_dag = _expanded_wf
        active_steps = _expanded_active
    except Exception as exc:
        console.warning(
            f"fan-out 事前展開に失敗したため非展開 workflow で続行します: {exc}"
        )

    # GUI Workbench 進捗集約用に fan-out 親 → 子 ID マップを 1 回だけ通知する。
    # GUI 側 (_apply_stats_fanout_init) は受信した child_ids をベース step の
    # subtask として seed し、以降の child 単位 step_status から base 状態を
    # 集約する（fan-out 子の進捗が UI に反映されない不具合の対応）。
    if _expand_info is not None:
        for _base_id, _child_ids in (getattr(_expand_info, "fanout_map", {}) or {}).items():
            if not _child_ids:
                continue
            try:
                console.stats_event(
                    "fanout_init",
                    step_id=_base_id,
                    workflow_id=workflow_id,
                    base_id=_base_id,
                    child_ids=list(_child_ids),
                )
            except Exception:
                # emit 失敗は実行を止めない（GUI 側は subtask 未seed のままで縮退動作）
                pass

    dry_run_plan = build_dag_plan(
        wf_for_dag,
        active_steps,
        max_parallel=effective_max_parallel,
        max_parallel_source=_max_parallel_source,
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

    # --- FR-CLI-74: dirty HVE source pre-flight ---
    # branch 作成（workflow-wide / Step 単位 CI/CD の両方）および Agent セッション
    # 開始より前に実行する。
    #
    # --dry-run は直前で return 済み: Agent を起動せず branch も commit も作らないため、
    # HVE ソースの未コミット変更が生成対象アプリへ混入する経路が無く、停止する理由がない。
    #
    # 適用範囲は HVE CLI / GUI Orchestrator 配下（`orchestrator_ctx` あり）の
    # アプリ生成 run。`orchestrator_ctx is None` は orchestrator_context モジュールが
    # 定義するとおり「単独実行モード（ライブラリ直接呼び出し・テスト等）」であり、
    # HVE 自身のリポジトリ状態を前提にできないため対象外とする。
    # FR-CLI-75 の staging 検査（`_git_add_commit_push`）でも同じ除外パスを使う。
    _target_output_paths = _explicit_target_output_paths(params)
    if orchestrator_ctx is not None:
        _hve_source_check = _check_dirty_hve_sources(
            console=console,
            target_output_paths=_target_output_paths,
        )
        if _hve_source_check["should_abort"]:
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "blocked": list(_hve_source_check["blocked_step_ids"]),
                "elapsed_total": time.time() - start_total,
                "error": _hve_source_check["error"],
            }

    # ASDW-WEB github.com CI/CD: workflow 全体ではなく、remote CI/CD が必要な
    # Step だけ一時ブランチを作成する。create_pr/create_issues は従来の
    # workflow-wide branch mode を優先する。
    step_scoped_cicd_branches: Dict[str, str] = {}
    # local generation checkpoint（最初の Deploy wave 直前）で記録する成果物 manifest。
    # 以降の stage / commit / push はこれを基準に成果物欠落を拒否する。
    protected_baseline: Optional[ProtectedArtifactManifest] = None
    if (
        wf.id == "asdw-web"
        and getattr(config, "enable_auto_merge", False)
        and not _workflow_branch_mode
    ):
        prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper()).lower()
        for step_id in sorted(_remote_cicd_step_ids(wf_for_dag, active_steps)):
            safe_step_id = step_id.replace(".", "-").replace("/", "-").lower()
            step_scoped_cicd_branches[step_id] = (
                f"copilot-sdk/{prefix}-step-{safe_step_id}-{uuid.uuid4().hex[:8]}"
            )
        if step_scoped_cicd_branches:
            console.event(
                "ASDW-WEB Step 単位 CI/CD ブランチ: "
                + ", ".join(f"Step.{sid}={branch}" for sid, branch in step_scoped_cicd_branches.items())
            )
            unmerged_paths = _git_unmerged_paths()
            if unmerged_paths:
                error = _format_git_unmerged_index_error(unmerged_paths)
                console.error(error)
                elapsed = time.time() - start_total
                return {
                    "workflow_id": workflow_id,
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "blocked": [],
                    "elapsed_total": elapsed,
                    "error": error,
                }

    # --- 4. 新ブランチ作成（--create-issues / --create-pr、または
    #         ADFDV で --enable-auto-merge（全自動）時） ---
    working_branch: Optional[str] = None
    # FR-CLI-83 / FR-GUI-37: HVE がこの run で作成した branch だけを自動 cleanup 対象にする。
    hve_created_branch = False
    if _workflow_branch_mode:
        p = _next_phase()
        phase_start = time.time()
        console.phase_start(p, _total_phases, "ブランチ作成")

        if _reuse_current_branch:
            working_branch = _git_current_branch(console)
            if not working_branch:
                elapsed = time.time() - start_total
                return {
                    "workflow_id": workflow_id,
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "elapsed_total": elapsed,
                    "error": "現在のブランチを特定できないため current branch mode を継続できません。",
                }
            console.event(f"現在のブランチ '{working_branch}' を PR head として使用します。")
        else:
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
            hve_created_branch = True
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

    try:
        root_issue_num, step_issue_map = _create_issues_if_needed(
            wf=wf,
            params=effective_params,
            active_steps=active_steps,
            config=config,
            console=console,
            render_template_fn=render_template,
            build_root_issue_body_fn=build_root_issue_body,
        )
    except RootIssueResolutionError as issue_exc:
        # FR-GUI-25: 既存 Root の解決失敗は fail-closed とし、
        # Root Issue の新規作成へフォールバックしない。
        console.error(str(issue_exc))
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "elapsed_total": time.time() - start_total,
            "error": str(issue_exc),
        }
    except RootIssueAssignmentError as issue_exc:
        # FR-CLI-89: Root は作成済み。target を通知して同じ Root を再作成せず停止する。
        root_issue_num = issue_exc.root_issue_num
        console.error(str(issue_exc))
        _emit_github_target_event(
            console,
            repo=config.repo,
            issue_number=root_issue_num,
            branch=working_branch,
            base_branch=config.base_branch,
            created_by_hve=hve_created_branch,
            delete_local_merged_branch=bool(
                getattr(config, "delete_local_merged_branch", True)
            ),
        )
        # current branch mode は利用者所有 branch のため削除しない。
        if hve_created_branch and working_branch:
            _git_delete_local_branch(working_branch, config.base_branch, console)
        return {
            "workflow_id": workflow_id,
            "completed": [],
            "failed": [],
            "skipped": [],
            "elapsed_total": time.time() - start_total,
            "root_issue_num": root_issue_num,
            "working_branch": working_branch,
            "error": str(issue_exc),
        }

    if config.create_issues:
        console.phase_end(p, _total_phases, "Issue 作成", time.time() - phase_start_issue)

    # FR-RTO-08: Root Issue と作業 branch が確定した時点で GUI へ target を通知する。
    _emit_github_target_event(
        console,
        repo=config.repo,
        issue_number=root_issue_num,
        branch=working_branch,
        base_branch=config.base_branch,
        created_by_hve=hve_created_branch,
        delete_local_merged_branch=bool(getattr(config, "delete_local_merged_branch", True)),
    )

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
        "docs/dataflow",
        "docs/dataflow/apps",
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
        _alias_resolver = _alias_resolver_for_params(effective_params)

        def _artifact_exists(pattern: str) -> bool:
            if pattern not in glob_cache:
                glob_cache[pattern] = _artifact_pattern_exists(pattern, _alias_resolver)
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

    qa_akm_coordinator: Optional[Any] = None
    qa_akm_include_paths: List[str] = []

    def _submit_qa_akm(path: Path) -> None:
        if qa_akm_coordinator is None:
            raise RuntimeError("QA 起点 AKM coordinator が初期化されていません")
        qa_akm_coordinator.submit(path)
        for validated in _validated_qa_include_paths([path]):
            if validated not in qa_akm_include_paths:
                qa_akm_include_paths.append(validated)

    qa_akm_dispatcher = (
        _submit_qa_akm
        if _should_enable_qa_akm_dispatch(
            auto_qa=config.auto_qa,
            workflow_id=workflow_id,
            dry_run=config.dry_run,
            qa_akm_background_merge=config.qa_akm_background_merge,
        )
        else None
    )
    runner = StepRunner(
        config=config,
        console=console,
        orchestrator_ctx=orchestrator_ctx,
        workflow_params=effective_params,
        qa_akm_dispatcher=qa_akm_dispatcher,
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

    # GUI 設定 [mdq] target_folders が非空時、Markdown-Query Skill 強制ブロックを前置する。
    # 設定が空のとき、もしくは読込失敗時は何もしない（要件: 「設定がなければ、何もしない」）。
    try:
        from .gui import settings_store as _mdq_settings_store
        from . import mdq_enforcement as _mdq_enforcement
        _mdq_block = _mdq_enforcement.build_enforcement_prompt(
            _mdq_settings_store.get_mdq_target_folders()
        )
    except Exception:
        _mdq_block = None
    if _mdq_block:
        if effective_additional_prompt:
            effective_additional_prompt = _mdq_block + "\n\n" + effective_additional_prompt
        else:
            effective_additional_prompt = _mdq_block

    # --- Phase 8: ステップ前提成果物チェック ---
    # local 実行モード (continue_on_error=True) では Pre-check 失敗を警告に降格し
    # 続行する（R1: Step 自体の失敗時の停止は維持。`--strict` でオプトアウト可）。
    _continue_on_error = bool(
        getattr(orchestrator_ctx, "continue_on_error", False)
    )
    _precheck_warnings: List[str] = []

    _artifact_check = _check_workflow_input_artifacts(
        wf=wf,
        active_steps=active_steps,
        existing_artifacts=existing_artifacts,
        config=config,
        console=console,
    )
    if _artifact_check["should_abort"]:
        if _continue_on_error:
            _precheck_warnings.append(
                "[Pre-check: 入力成果物不足] " + (_artifact_check.get("error") or "")
            )
            try:
                console.warning(
                    "⚠️ Pre-check (入力成果物) 失敗を警告に降格して続行します "
                    "（continue-on-precheck モード）。"
                )
            except Exception:
                pass
        else:
            # T-H1H2b: strict モードで artifact 不足を検出した場合、
            # 結果 dict の "blocked" キーに該当ルートステップ ID を含めて返す。
            # 後続レイヤーは "failed" と区別して「停止」として扱える。
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "blocked": list(_artifact_check.get("blocked_step_ids", [])),
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
        if _continue_on_error:
            _precheck_warnings.append(
                "[Pre-check: 必須 Skill 不足] " + (_skill_check.get("error") or "")
            )
            try:
                console.warning(
                    "⚠️ Pre-check (必須 Skill) 失敗を警告に降格して続行します "
                    "（continue-on-precheck モード）。"
                )
            except Exception:
                pass
        else:
            # T-H1H2b: strict モードで Skill 不足を検出した場合も artifact 不足と同様
            # 結果 dict の "blocked" キーに該当 step ID を含めて返す。
            return {
                "workflow_id": workflow_id,
                "completed": [],
                "failed": [],
                "skipped": [],
                "blocked": list(_skill_check.get("blocked_step_ids", [])),
                "elapsed_total": time.time() - start_total,
                "error": _skill_check["error"],
            }

    # Pre-check 警告を additional_prompt に注入し、LLM が認識できるようにする
    # （R1 緩和策: 必須入力が無い状態でも品質を保つため "TBD" 記載で続行可と伝達）。
    if _precheck_warnings:
        _warn_block = (
            "\n\n## Pre-check 警告（continue-on-precheck モード）\n"
            "以下の Pre-check が失敗しましたが、警告に降格して続行しています。"
            "対応する成果物・Skill が未確定の場合は `TBD（推論: <根拠>）` と"
            "明記したうえで続行してください。\n\n"
            + "\n\n".join(_precheck_warnings)
        )
        effective_additional_prompt = (
            (effective_additional_prompt or "") + _warn_block
        ).strip()

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
        step_params = effective_params
        if step.id in step_scoped_cicd_branches:
            step_params = dict(effective_params)
            step_params["branch"] = step_scoped_cicd_branches[step.id]
        # FR-CLI-71: プロンプトテンプレート展開失敗は DAG 実行前に停止させる。
        # ここで握り潰すと壊れた縮退プロンプトで Agent セッションが開始される。
        try:
            step_prompts[step.id] = _build_step_prompt(
                step=step,
                params=step_params,
                root_issue_num=root_issue_num,
                render_template_fn=render_template,
                wf=wf,
                additional_prompt=step_additional,
                execution_mode=execution_mode,
            )
        except Exception as exc:
            console.error(
                f"Step.{step.id} のプロンプトテンプレート展開に失敗しました: "
                f"template={step.body_template_path} ({type(exc).__name__}: {exc})"
            )
            raise

    # Fan-out 子ステップへ base prompt を伝播（fanout-fix）:
    # step_prompts は wf.steps（非展開）を反復するためベース ID 分のみ構築済み。
    # 展開後 wf_for_dag.steps に存在する子 ID は空 prompt で起動してしまうため、
    # ここで base prompt を子 ID にコピーする。
    # runner._apply_fanout_prompt_template が fanout_meta から
    # addendum ({{key}} 置換済み) を base prompt の前段に付与する。
    if _expand_info is not None and getattr(_expand_info, "fanout_map", None):
        for _base_id, _child_ids in _expand_info.fanout_map.items():
            if _base_id in step_prompts:
                for _cid in _child_ids:
                    if _cid not in step_prompts:
                        step_prompts[_cid] = step_prompts[_base_id]

    dag_plan = build_dag_plan(
        wf_for_dag,
        active_steps,
        step_prompts=step_prompts,
        max_parallel=effective_max_parallel,
        max_parallel_source=_max_parallel_source,
    )

    # --- 6-7. DAGExecutor 実行 ---
    def _drain_qa_akm(reason: str) -> List[Dict[str, Any]]:
        if qa_akm_coordinator is None:
            return []
        drained = qa_akm_coordinator.drain()
        skipped = [item for item in drained if item.get("skipped")]
        failed = [
            item for item in drained
            if not item.get("skipped") and int(item.get("returncode", -1)) != 0
        ]
        if skipped:
            console.warning(_format_qa_akm_skip_warning(skipped, reason))
        if failed:
            console.warning(_format_qa_akm_failure_warning(failed, reason))
        return drained

    step_scoped_cicd_pr_numbers: Dict[str, int] = {}

    def _step_scoped_cicd_ignore_paths() -> List[str]:
        # remote CI/CD Step の branch には src/infra/azure や app/api 実装を含める。
        return [p for p in (config.ignore_paths or []) if p != "src"]

    def _prepare_step_scoped_cicd_branch(step_id: str) -> bool:
        branch = step_scoped_cicd_branches.get(step_id)
        if not branch:
            return True
        _drain_qa_akm(f"Step.{step_id} branch 作成前")
        console.event(f"Step.{step_id}: remote CI/CD 用ブランチ '{branch}' を作成します。")
        if not _git_checkout_new_branch(branch, config.base_branch, console):
            return False
        pushed = _git_add_commit_push(
            branch=branch,
            commit_message=f"[ASDW-WEB] Step.{step_id} remote CI/CD 前の成果物",
            console=console,
            ignore_paths=_step_scoped_cicd_ignore_paths(),
            protected_baseline=protected_baseline,
            target_output_paths=_target_output_paths,
            include_paths=qa_akm_include_paths,
        )
        if not pushed:
            # 差分がない場合でも remote workflow の --ref で参照できるよう branch 自体は push する。
            return _git_push_branch(branch, console)
        return True

    def _finalize_step_scoped_cicd_branch(step_id: str, step_success: bool) -> bool:
        branch = step_scoped_cicd_branches.get(step_id)
        if not branch:
            return step_success
        _drain_qa_akm(f"Step.{step_id} branch 終了前")
        if not step_success:
            console.warning(
                f"Step.{step_id} が失敗したため PR 作成をスキップし、base branch へ戻ります。"
            )
            _git_checkout_base_branch(config.base_branch, console)
            return False

        if _git_remote_branch_ahead(branch, console):
            console.event(
                f"Step.{step_id}: remote CI/CD ブランチ '{branch}' は Agent により更新済みのため、"
                "stale local branch の final push をスキップします。"
            )
        else:
            current_branch = _git_current_branch(console)
            if current_branch != branch:
                if _git_has_uncommitted_changes(console):
                    console.error(
                        f"Step.{step_id}: 現在ブランチが '{current_branch or 'detached HEAD'}' で、"
                        f"期待する Step ブランチ '{branch}' ではありません。未コミット変更があるため final push を中止します。"
                    )
                    return False
                if not _git_checkout_existing_branch(branch, console):
                    return False

            pushed = _git_add_commit_push(
                branch=branch,
                commit_message=f"[ASDW-WEB] Step.{step_id} remote CI/CD 成果物",
                console=console,
                ignore_paths=_step_scoped_cicd_ignore_paths(),
                protected_baseline=protected_baseline,
                target_output_paths=_target_output_paths,
                include_paths=qa_akm_include_paths,
            )
            if not pushed and not _git_push_branch(branch, console):
                return False

        pr_num = _create_pr_if_needed(
            wf=wf,
            head_branch=branch,
            base_branch=config.base_branch,
            config=config,
            console=console,
            root_issue_num=root_issue_num,
            workiq_report_paths=sorted(workiq_report_paths),
            task_goal=None,
            goal_sources=[],
            all_steps_succeeded=True,
        )
        if pr_num is None:
            _git_checkout_base_branch(config.base_branch, console)
            return False
        step_scoped_cicd_pr_numbers[step_id] = pr_num
        if not _wait_pr_merged(pr_num, config, console, require_check_runs=False):
            _git_checkout_base_branch(config.base_branch, console)
            return False
        if getattr(config, "delete_local_merged_branch", True):
            if not _git_delete_local_branch(branch, config.base_branch, console):
                return False
        else:
            if not _git_checkout_base_branch(config.base_branch, console):
                return False
        return _git_pull_ff_only_base_branch(config.base_branch, console)

    async def run_step_fn(
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
        fanout_meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        _prompt = prompt

        # --- ARD: Step 1.2 → Step 2 bridging hook ---
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
                # FR-CLI-71: 展開失敗時はフォールバックせず、原因テンプレートを
                # 1 行で提示したうえで例外をそのまま伝播させる。
                try:
                    _prompt = _build_step_prompt(
                        step=step,
                        params=effective_params,
                        root_issue_num=root_issue_num,
                        render_template_fn=render_template,
                        wf=wf,
                        additional_prompt=step_additional,
                        execution_mode=execution_mode,
                    )
                except Exception as exc:
                    console.error(
                        f"Step.{step_id} のプロンプトテンプレート展開に失敗しました: "
                        f"template={step.body_template_path} ({type(exc).__name__}: {exc})"
                    )
                    raise

        if not _prepare_step_scoped_cicd_branch(step_id):
            return False

        success = await runner.run_step(
            step_id=step_id,
            title=title,
            prompt=_prompt,
            custom_agent=custom_agent,
            workflow_id=workflow_id,
            fanout_meta=fanout_meta,
        )
        if workflow_id == "ard" and step_id == "1.2" and success:
            await _on_ard_step1_completed(
                config=config,
                params=effective_params,
                console=console,
            )
        success = _finalize_step_scoped_cicd_branch(step_id, success)
        return success

    def _record_run_progress(result: StepResult) -> None:
        """FR-STATE-04: Step の完了状態を進捗ストアへ記録する。"""
        if getattr(config, "dry_run", False) or result.skipped:
            return
        run_progress.record_step(
            config.run_id,
            workflow_id,
            result.step_id,
            run_progress.STATUS_SUCCEEDED if result.success else run_progress.STATUS_FAILED,
        )

    def _on_wave_start(executable_steps: List[Any], wave_index: int) -> None:
        nonlocal protected_baseline
        # FR-CLI-87: approval_gate を宣言した Step を含む Wave は実行前に承認を求める。
        if _approval_gates_enabled and approval.wave_requires_approval(executable_steps):
            approval.request_wave_approval(
                executable_steps,
                wave_index,
                interactive=approval.stdin_is_interactive(),
                console=console,
            )
            run_progress.record_step(
                config.run_id,
                workflow_id,
                f"approval:{wave_index}",
                run_progress.STATUS_SUCCEEDED,
            )
        # enable_auto_merge（全自動）時、Deploy Step を含む wave の前に生成済み
        # workflow/成果物を push する（Deploy Agent の `gh workflow run --ref` 用）。
        # enable_auto_merge OFF はリポジトリ操作を手動とするため push しない。
        if (
            getattr(config, "enable_auto_merge", False)
            and working_branch
        ):
            from hve.artifact_validation import wave_has_deploy_step

            if wave_has_deploy_step(executable_steps):
                _drain_qa_akm(f"deploy wave {wave_index} push 前")
                # 最初の Deploy wave 直前 = local generation checkpoint。
                # この時点の local 成果物を baseline として固定する。
                if protected_baseline is None:
                    protected_baseline = capture_protected_artifact_manifest()
                    console.event(
                        "  🔒 local generation checkpoint の成果物を記録しました: "
                        + ", ".join(
                            f"{root}({len(files)})"
                            for root, files in sorted(protected_baseline.items())
                        )
                    )
                # Deploy Agent が `gh workflow run` で実行する workflow は
                # src/infra/azure/*.sh 等を参照するため、Deploy 境界 push では
                # 既定 ignore_paths から "src" を除外して Deploy 成果物を含める。
                _deploy_ignore = [
                    p for p in (config.ignore_paths or []) if p != "src"
                ]
                _git_add_commit_push(
                    branch=working_branch,
                    commit_message=(
                        "[HVE] github.com CI/CD: Deploy 前のローカル成果物を push"
                        f" (wave {wave_index})"
                    ),
                    console=console,
                    ignore_paths=_deploy_ignore,
                    protected_baseline=protected_baseline,
                    target_output_paths=_target_output_paths,
                    include_paths=qa_akm_include_paths,
                )
        routing = apply_cloud_session_auto_routing(
            config,
            executable_steps,
            workflow_id=workflow_id,
            wave_index=wave_index,
            parallel_limit=effective_max_parallel,
            local_min=1,
        )
        if not routing:
            return
        if min(len(executable_steps), max(1, int(effective_max_parallel or 1))) <= 1:
            # 単一 task wave / 実効並列数 1 は原則 local。通常ログは増やさない。
            return
        cloud_ids = sorted([sid for sid, use_cloud in routing.items() if use_cloud])
        local_ids = sorted([sid for sid, use_cloud in routing.items() if not use_cloud])
        try:
            console.event(
                "  ☁️ Cloud Session 自動振り分け: "
                f"cloud={cloud_ids or ['(manual/none)']} / local={local_ids or ['(manual/none)']}"
            )
        except Exception:
            pass

    def _build_fleet_wave_runner() -> Optional[Callable[[List[Any], int], Any]]:
        """Build an optional SDK Fleet backend for workflow-level DAG waves."""
        if not bool(getattr(config, "fleet_mode_enabled", False)):
            return None

        repo_root = Path.cwd()

        async def _fleet_wave_runner(executable_steps: List[Any], wave_index: int) -> Optional[Dict[str, StepResult]]:
            if len(executable_steps) <= 1:
                return None
            try:
                from copilot.session import PermissionHandler  # type: ignore[import]
            except ImportError:
                console.warning(
                    "Fleet mode requested but GitHub Copilot SDK is unavailable. "
                    "Falling back to normal DAG execution."
                )
                return None
            try:
                from .fleet_mode import (
                    DagWaveFleetTask,
                    FleetEventCollector,
                    build_dag_wave_fleet_prompt,
                    format_fleet_wave_skipped_phases_warning,
                    start_fleet,
                )
                from .split_fork import check_subtask_completion, resolve_work_root
            except ImportError:  # pragma: no cover
                from fleet_mode import (  # type: ignore[no-redef]
                    DagWaveFleetTask,
                    FleetEventCollector,
                    build_dag_wave_fleet_prompt,
                    format_fleet_wave_skipped_phases_warning,
                    start_fleet,
                )
                from split_fork import check_subtask_completion, resolve_work_root  # type: ignore[no-redef]

            tasks = []
            for step in executable_steps:
                prompt_text = step_prompts.get(step.id, "")
                fanout_meta: Optional[Dict[str, Any]] = None
                if getattr(step, "fanout_key", "") and getattr(step, "base_step_id", ""):
                    fanout_meta = {
                        "fanout_key": step.fanout_key,
                        "base_step_id": step.base_step_id,
                        "additional_prompt_template_path": getattr(step, "additional_prompt_template_path", None),
                        "per_key_mcp_servers": getattr(step, "per_key_mcp_servers", None),
                    }
                    prompt_text = _apply_fanout_prompt_template(
                        prompt=prompt_text,
                        fanout_meta=fanout_meta,
                        console=console,
                    )
                tasks.append(DagWaveFleetTask(
                    step_id=step.id,
                    title=getattr(step, "title", step.id),
                    prompt=prompt_text,
                    custom_agent=getattr(step, "custom_agent", None),
                    fanout_key=(fanout_meta or {}).get("fanout_key", ""),
                    base_step_id=(fanout_meta or {}).get("base_step_id", ""),
                    output_paths=tuple(getattr(step, "output_paths", []) or []),
                    required_input_paths=tuple(
                        _alias_resolver_for_params(effective_params).resolve_paths(
                            getattr(step, "required_input_paths", []) or []
                        )
                    ),
                ))

            try:
                fleet_run_id = config.run_id or generate_run_id()
                # Worker prompt の completion_report 指示先と parent 側の
                # check_subtask_completion 監視先を必ず同じ root に揃える。
                work_root = resolve_work_root()
                fleet_plan = build_dag_wave_fleet_prompt(
                    tasks=tasks,
                    workflow_id=workflow_id,
                    wave_index=wave_index,
                    repo_root=repo_root,
                    run_id=fleet_run_id,
                    work_root=work_root,
                )
            except ValueError as exc:
                console.warning(
                    f"Fleet wave prompt could not be built (wave={wave_index}): {exc}. "
                    "Falling back to normal DAG execution."
                )
                return None

            client = _create_copilot_client_from_config(config, log_level=config.log_level)
            session = None
            unsubscribe = None
            started_at = time.time()
            try:
                await client.start()
                session_opts: Dict[str, Any] = {
                    "on_permission_request": PermissionHandler.approve_all,
                    "streaming": True,
                    "session_id": make_session_id(
                        run_id=fleet_run_id,
                        step_id=f"fleet-wave-{wave_index}",
                        prefix=(config.session_id_prefix or DEFAULT_SESSION_ID_PREFIX),
                    ),
                }
                _wire_model = to_wire_model(config.model)
                if _wire_model:
                    session_opts["model"] = _wire_model
                # Fleet parent session does not receive project MCP servers by default.
                # This keeps the opt-in Fleet backend narrower than normal per-step
                # sessions and avoids broad MCP/tool exposure from one parent prompt.
                # Individual standard Step execution still receives configured MCP servers.
                if config.available_tools:
                    session_opts["available_tools"] = list(config.available_tools)
                if config.excluded_tools:
                    session_opts["excluded_tools"] = list(config.excluded_tools)
                if config.auto_compaction:
                    session_opts["infinite_sessions"] = {"enabled": True}
                _apply_reasoning_effort(session_opts, config, model_value=config.model, kind="main")

                session = await _create_session_with_auto_reasoning_fallback(
                    client,
                    session_opts,
                    config=None,  # Fleet mode is a local SDK backend, not SDK Cloud Sessions.
                    step_id=f"fleet-wave-{wave_index}",
                    subtask_kind="fleet",
                    console=console,
                )
                collector = FleetEventCollector(
                    console=console,
                    wave_index=wave_index,
                    step_ids=tuple(fleet_plan.task_step_ids),
                )
                maybe_unsubscribe = session.on(collector.handle_event)
                if callable(maybe_unsubscribe):
                    unsubscribe = maybe_unsubscribe
                work_root_resolved = work_root.resolve()
                for report_dir in fleet_plan.report_dirs.values():
                    report_path = (work_root / report_dir).resolve()
                    report_path.relative_to(work_root_resolved)
                    if report_path.exists():
                        shutil.rmtree(report_path)
                    report_path.mkdir(parents=True, exist_ok=True)
                fleet_step_ids = list(fleet_plan.task_step_ids)
                display_step_ids = fleet_step_ids[:10]
                if len(fleet_step_ids) > len(display_step_ids):
                    display_step_ids.append(
                        f"...(+{len(fleet_step_ids) - len(display_step_ids)})"
                    )
                # 所要時間の計測はシステム時刻変更の影響を受けない monotonic を使う。
                fleet_start_request_at = time.monotonic()
                console.status(
                    f"Fleet wave {wave_index}: Fleet 起動要求を送信します "
                    f"steps={display_step_ids}"
                )
                outcome = await start_fleet(session, fleet_plan.prompt)
                fleet_start_elapsed = time.monotonic() - fleet_start_request_at
                if not outcome.started:
                    console.warning(
                        f"Fleet mode did not start for wave={wave_index} "
                        f"after {fleet_start_elapsed:.1f}s: {outcome.reason}. "
                        "Falling back to normal DAG execution."
                    )
                    return None
                skipped_phases_warning = format_fleet_wave_skipped_phases_warning(
                    wave_index=wave_index,
                    auto_qa=bool(getattr(config, "auto_qa", False)),
                    auto_contents_review=bool(
                        getattr(config, "auto_contents_review", False)
                    ),
                )
                if skipped_phases_warning:
                    console.warning(skipped_phases_warning)
                console.status(
                    f"Fleet wave {wave_index}: Fleet 起動完了 "
                    f"({fleet_start_elapsed:.1f}s)。completion-report 待機を開始します"
                )

                deadline = time.monotonic() + max(1.0, float(config.timeout_seconds or 1.0))
                completion_state: Dict[str, tuple[bool, str]] = {}
                # GUI Workbench が無音に見えないようにするための低頻度 heartbeat。
                # 大量 fan-out でログが埋まらないよう 30 秒間隔に固定する。
                heartbeat_interval = 30.0
                last_heartbeat_at = 0.0
                while True:
                    completion_state = {
                        step_id: check_subtask_completion(work_root, report_dir)
                        for step_id, report_dir in fleet_plan.report_dirs.items()
                    }
                    now = time.monotonic()
                    if now - last_heartbeat_at >= heartbeat_interval:
                        missing_ids = [
                            step_id
                            for step_id, (ok, _reason) in completion_state.items()
                            if not ok
                        ]
                        if missing_ids:
                            display_ids = missing_ids[:10]
                            if len(missing_ids) > len(display_ids):
                                display_ids.append(f"...(+{len(missing_ids) - len(display_ids)})")
                            # collector.handle_event は同一イベントループスレッドで呼ばれ
                            # （SDK は call_soon_threadsafe でループへ戻す）、この set() 区間に
                            # await が無いため反復中の dict 変更は起こらない（ロック不要）。
                            running_names = sorted(set(collector.running.values()))
                            display_running = running_names[:10]
                            if len(running_names) > len(display_running):
                                display_running.append(
                                    f"...(+{len(running_names) - len(display_running)})"
                                )
                            console.status(
                                f"Fleet wave {wave_index}: completion-report 待機中 "
                                f"missing={display_ids} "
                                f"実行中={display_running} 完了={len(collector.completed)}"
                            )
                        last_heartbeat_at = now
                    if all(ok for ok, _reason in completion_state.values()):
                        break
                    if collector.has_failed:
                        break
                    if time.monotonic() >= deadline:
                        break
                    await asyncio.sleep(0.5)

                results: Dict[str, StepResult] = {}
                for step_id in fleet_plan.task_step_ids:
                    ok, reason = completion_state.get(step_id, (False, "completion state missing"))
                    success = bool(ok)
                    failure_reason = reason
                    if not success and collector.has_failed:
                        failure_reason = f"{reason}; fleet_failed={collector.failed}"
                    results[step_id] = StepResult(
                        step_id,
                        success=success,
                        elapsed=time.time() - started_at,
                        error=None if success else failure_reason,
                        state="success" if success else "failed",
                        reason="fleet-wave" if success else failure_reason,
                    )
                if collector.has_failed:
                    console.error(f"Fleet wave failed (wave={wave_index}): {collector.failed}")
                return results
            finally:
                if callable(unsubscribe):
                    try:
                        unsubscribe()
                    except Exception:
                        pass
                if session is not None:
                    try:
                        await session.disconnect()
                    except Exception as cleanup_exc:
                        console.warning(f"[cleanup] fleet session.disconnect() failed: {cleanup_exc}")
                try:
                    await client.stop()
                except Exception as cleanup_exc:
                    console.warning(f"[cleanup] fleet client.stop() failed: {cleanup_exc}")

        return _fleet_wave_runner

    executor = DAGExecutor(
        workflow=wf_for_dag,
        run_step_fn=run_step_fn,
        active_step_ids=active_steps,
        max_parallel=effective_max_parallel,
        console=console,
        step_prompts=step_prompts,
        dag_plan=dag_plan,
        repo_root=Path.cwd(),
        # FR-STATE-04: 既存フック経由で進捗を記録する（dry-run は除く）。
        on_step_complete=_record_run_progress,
        # Fork-integration (T2.6/T2.8): フィーチャフラグ off （既定）で旧挙動と完全一致
        fork_on_retry=bool(getattr(config, "fork_on_retry", False)),
        fork_kpi_logger=_build_fork_kpi_logger(config),
        on_fork_retry=runner.set_fork_index,
        # T-E1: deferred fan-out ランタイム再展開
        deferred_fanout_ids=set(getattr(_expand_info, "deferred_fanout_ids", []) or []),
        on_wave_start=_on_wave_start,
        fleet_wave_runner=_build_fleet_wave_runner(),
        workflow_id=workflow_id,
        # APP-ID フィルタ (fan-out 子ステップを GUI 選択 APP-ID のみに絞る):
        # deferred fan-out のランタイム再展開時にも同じ app_ids で絞り込むため、
        # DAGExecutor に保持させる。事前展開 (L3237 の _expand_workflow_for_dag) と
        # 同じ effective_params["app_ids"] を伝播。
        app_ids=effective_params.get("app_ids"),
        # per-step wall-clock タイムアウト（ハングした 1 ステップが DAG 全体を
        # 無期限停止させるのを防ぐ）。config 既定 7200s / None・<=0 で無効。
        step_timeout_seconds=getattr(config, "step_timeout_seconds", None),
    )

    # 実行計画を事前表示
    waves = executor.compute_waves()
    if waves:
        console.execution_plan(waves, executor.total_display_steps(), effective_max_parallel)

    # Workbench UI の起動（TTY/quiet/final_only/HVE_NO_WORKBENCH 等で自動降格）
    _wb = None
    if getattr(console, "workbench_enabled", False) and not getattr(config, "no_workbench", False):
        try:
            from hve.workbench import WorkbenchController, WorkbenchState, StepView
            # Phase 6: fan-out 事前展開後のステップを Header#2 に表示する。
            # executor 構築時に _expanded_steps / active_step_ids が
            # fanout_expander により展開済み（dag_plan 併用時は展開なし）。
            _expanded_steps = getattr(executor, "_expanded_steps", None) or list(wf.steps)
            _active_for_view = set(getattr(executor, "active_step_ids", active_steps))
            steps_view = [
                StepView(id=s.id, title=s.title, status="pending")
                for s in _expanded_steps
                if s.id in _active_for_view and not getattr(s, "is_container", False)
            ]
            wb_state = WorkbenchState(
                workflow_id=workflow_id,
                workflow_name=getattr(wf, "name", "") or "",
                run_id=str(config.run_id),
                model=getattr(config, "model", "unknown"),
                steps=steps_view,
                body_window=int(getattr(config, "workbench_body_lines", 10)),
            )
            # --workbench-history 配線: 既定 RingBuffer の容量を置換する
            _hist = int(getattr(config, "workbench_history", 10000) or 10000)
            if _hist < 0:
                # 負値 → 無制限バッファ
                from hve.workbench import RingBuffer as _RingBuffer
                wb_state.body = _RingBuffer(capacity=None)
            elif _hist > 0 and _hist != wb_state.body.capacity:
                from hve.workbench import RingBuffer as _RingBuffer
                wb_state.body = _RingBuffer(capacity=_hist)
            _wb = WorkbenchController(
                wb_state,
                flush_on_exit=bool(getattr(config, "workbench_flush_on_exit", True)),
            )
            _wb.__enter__()
            if _wb.active:
                console.attach_workbench(_wb)
                # Phase 6+: 動的 retry fork (fork_on_retry=True 時) を Header#2 に反映。
                # DAGExecutor は構築済みのため、コールバックを事後注入する。
                # retry 通知は Header#2 のラベルだけでなく UserActions にも残す。
                def _on_retry_with_ua(sid: str, retry_n: int) -> None:
                    try:
                        _wb.mark_retry(sid, retry_n)  # type: ignore[union-attr]
                    except Exception:
                        pass
                    if retry_n and retry_n > 0:
                        try:
                            _wb.append_user_action(  # type: ignore[union-attr]
                                "WARN",
                                f"step {sid}: retry #{retry_n}",
                                step_id=sid,
                            )
                        except Exception:
                            pass
                try:
                    executor._on_fork_retry_ui = _on_retry_with_ua  # type: ignore[attr-defined]
                except Exception:  # pragma: no cover
                    pass
        except Exception as _wb_exc:  # pragma: no cover
            # Workbench 起動失敗は plain にフォールバック（ログのみ）
            try:
                console.warning(f"Workbench UI 起動失敗、plain 出力に降格します: {_wb_exc}")
            except Exception:
                pass
            _wb = None

    # Workbench を使わない TTY 実行では 1Hz ステータスラインを主表示とする。
    _status_line = None
    if _wb is None:
        try:
            _status_line = _attach_runtime_statusline(
                console, config, workflow_started_at=_start_monotonic
            )
        except Exception:
            _status_line = None

    # ここより前の計画・UI構築失敗では worker を作らない。Step 実行 callback が
    # 発火し得る executor.execute() の直前にだけ生成する。
    if qa_akm_dispatcher is not None:
        try:
            from .qa_akm_dispatch import QaAkmCoordinator
        except ImportError:  # pragma: no cover - top-level module compatibility
            from qa_akm_dispatch import QaAkmCoordinator  # type: ignore[no-redef]
        qa_akm_coordinator = QaAkmCoordinator(
            config, repo_root=Path.cwd(), warn=console.warning,
        )

    _dag_execution_finished = False
    try:
        # T4: continue_on_error=True かつ executor 側で fatal 例外が発生した場合は
        # 残ステップを skip マークして exit 0 相当で正常終了する（Q6=B）。
        # recoverable 例外は従来通り再送出。
        try:
            results = await executor.execute()
        except approval.ApprovalDeclined as _approval_exc:
            # FR-CLI-87: 承認拒否は停止条件。continue_on_error の fatal 縮退へ
            # 落とさず、blocked として返す。
            _approval_error = str(_approval_exc)
            console.error(_approval_error)
            # 拒否も `approval:<wave_index>` で残し、どの Wave で停止したかを復元可能にする。
            run_progress.record_step(
                config.run_id,
                workflow_id,
                f"approval:{_approval_exc.wave_index}",
                run_progress.STATUS_FAILED,
            )
            return {
                "workflow_id": workflow_id,
                "completed": sorted(getattr(executor, "_results", {}) or {}),
                "failed": [],
                "skipped": [],
                "blocked": sorted(active_steps),
                "elapsed_total": time.time() - start_total,
                "error": _approval_error,
            }
        except BaseException as _exec_exc:  # noqa: BLE001
            try:
                from .error_severity import classify_error as _classify_err
            except ImportError:  # pragma: no cover
                from error_severity import classify_error as _classify_err  # type: ignore[no-redef]
            _severity = _classify_err(_exec_exc)
            if _continue_on_error and _severity == "fatal":
                try:
                    console.error(
                        f"⚠️ 致命的エラーを検出: {type(_exec_exc).__name__}: {_exec_exc} "
                        "（残ステップを skip マークして正常終了します）"
                    )
                except Exception:
                    pass
                # GUI Orchestrator が致命的エラー発生を検知して
                # 後続ワークフローのキュー実行を停止できるよう、stdout に
                # 構造化マーカーを 1 行出力する（console 経由ではなく素の
                # print を使うことで timestamp/絵文字置換等の影響を避ける）。
                #
                # 出力条件:
                #   - GUI 経路 (cfg.no_workbench=True / `--workbench=off`) → 必須
                #   - CLI 経路 (Workbench UI 起動 or 通常 plain 出力) → ノイズ抑制のため出さない
                #   - 環境変数 HVE_EMIT_FATAL_MARKER=1 で強制 ON (E2E テスト用)
                #
                # NOTE: ensure_ascii=True にして Windows + cp932 環境で
                # `_configure_stdio_encoding` の errors="replace" による
                # 多バイト文字置換が起きても JSON 構造が壊れないようにする。
                try:
                    import os as _os_fatal
                    _force_marker = (
                        _os_fatal.environ.get("HVE_EMIT_FATAL_MARKER", "")
                        .strip().lower()
                        in {"1", "true", "yes"}
                    )
                    _gui_mode = bool(getattr(config, "no_workbench", False))
                    if _force_marker or _gui_mode:
                        import json as _json_fatal
                        import sys as _sys_fatal
                        _fatal_payload = _json_fatal.dumps(
                            {
                                "kind": "fatal_abort",
                                "exception_type": type(_exec_exc).__name__,
                                "message": str(_exec_exc),
                            },
                            ensure_ascii=True,
                        )
                        print(
                            f"[hve:fatal] {_fatal_payload}",
                            file=_sys_fatal.stdout,
                            flush=True,
                        )
                except Exception:
                    pass
                # 残ステップを skip マーク
                _all_step_ids = {
                    s.id for s in wf.steps
                    if not s.is_container and s.id in active_steps
                }
                _processed = (
                    set(executor.completed)
                    | set(executor.failed)
                    | set(executor.skipped)
                )
                for _sid in sorted(_all_step_ids - _processed):
                    try:
                        executor.skipped.add(_sid)
                        from .dag_executor import StepResult as _SR
                    except ImportError:  # pragma: no cover
                        from dag_executor import StepResult as _SR  # type: ignore[no-redef]
                    _skip_res = _SR(
                        _sid, success=True, elapsed=0.0,
                        skipped=True, state="skipped",
                        reason="fatal-abort",
                    )
                    executor._results[_sid] = _skip_res
                results = dict(getattr(executor, "_results", {}) or {})
            else:
                raise
        _dag_execution_finished = True
        # FR-DAG-09: 差戻し先を決定して提示するだけとし、自動再実行は行わない。
        try:
            _rework_message = rework.format_rework_suggestion(
                workflow_id,
                rework.resolve_rework_targets(
                    wf.steps,
                    [sid for sid, res in (results or {}).items() if getattr(res, "success", False)],
                    Path.cwd(),
                ),
            )
            if _rework_message:
                console.event(_rework_message)
        except Exception:
            pass
    finally:
        if qa_akm_coordinator is not None and not _dag_execution_finished:
            qa_akm_coordinator.cancel()
        # StatusLine を先に止め、後続の確定行と描画が衝突しないようにする。
        if _status_line is not None:
            try:
                _status_line.stop()
            except Exception:
                pass
        # Workbench UI を停止し Console から detach
        if _wb is not None:
            # 全タスク完了を宣言し、useractions レポートを保存（冪等）。
            # その後 /exit 入力を待機する。
            try:
                _wb.mark_all_done()
            except Exception:
                pass
            import os as _os
            import sys as _sys
            _t = _os.environ.get("HVE_WORKBENCH_EXIT_TIMEOUT", "").strip()
            _timeout: float = 0.0
            if _t:
                try:
                    _timeout = float(_t)
                    if _timeout < 0:
                        raise ValueError(
                            f"HVE_WORKBENCH_EXIT_TIMEOUT must be >= 0, got {_t!r}"
                        )
                except ValueError as _ve:
                    print(
                        f"[hve.workbench] WARN: HVE_WORKBENCH_EXIT_TIMEOUT 不正値 {_t!r} → 無制限待機で続行 ({_ve})",
                        file=_sys.stderr,
                        flush=True,
                    )
                    _timeout = 0.0
            try:
                _wb.wait_for_exit(timeout=_timeout)
            except Exception as _we:
                print(
                    f"[hve.workbench] WARN: wait_for_exit 失敗 → 続行 ({_we})",
                    file=_sys.stderr,
                    flush=True,
                )
            try:
                console.detach_workbench()
            except Exception:
                pass
            try:
                _wb.__exit__(None, None, None)
            except Exception:
                pass

    if qa_akm_coordinator is not None:
        _drain_qa_akm("DAG 完了後")
        qa_akm_coordinator.cancel()

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

    # --- ADI 原本質問票成果物検証（warning のみ、hard fail なし）---
    _active_base_step_ids = {
        str(step_id).split("/", 1)[0] for step_id in active_steps
    }
    _adi_questionnaire_steps_active = bool(
        workflow_id == "adi"
        and {"1.1", "1.2"} & _active_base_step_ids
    )
    original_docs_questionnaire_validation_result: Optional[dict] = None
    adi_questionnaire_include_paths: List[str] = []
    if _adi_questionnaire_steps_active and not config.dry_run:
        try:
            try:
                from .artifact_validation import validate_original_docs_questionnaire_run
            except ImportError:
                from artifact_validation import validate_original_docs_questionnaire_run  # type: ignore[no-redef]
            original_docs_questionnaire_validation_result = (
                validate_original_docs_questionnaire_run(
                    qa_dir="qa",
                    run_id=config.run_id,
                )
            )
            _av_overall = original_docs_questionnaire_validation_result.get("overall", "FAIL")
            _av_found = original_docs_questionnaire_validation_result.get("artifacts_found", 0)
            _av_passed = original_docs_questionnaire_validation_result.get("passed", 0)
            if _av_overall == "PASS":
                console.event(
                    f"✅ ADI 原本質問票検証 PASS: {_av_passed}/{_av_found} 件が有効です。"
                )
            elif _av_overall == "WARN":
                console.warning(
                    f"⚠️ ADI 原本質問票検証 WARN: {_av_passed}/{_av_found} 件が有効（一部に問題あり）。"
                )
            else:
                console.warning(
                    "⚠️ ADI 原本質問票検証 FAIL: Step 1.1 / 1.2 の成果物が見つからないか、"
                    "必須要件を満たしていません。\n"
                    "   execution-qa-merged.md は HVE 実行補助 QA であり、"
                    "ADI のmain成果物ではありません。"
                )
            for vr in (
                original_docs_questionnaire_validation_result.get("validation_results")
                or []
            ):
                for err in (vr.get("errors") or []):
                    console.warning(f"  [検証エラー] {vr.get('path')}: {err}")
                for warn in (vr.get("warnings") or []):
                    console.warning(f"  [検証警告] {vr.get('path')}: {warn}")
        except Exception as av_exc:
            console.warning(
                "ADI 原本質問票検証中にエラーが発生しました"
                f"（無視して続行）: {av_exc}"
            )

        # qa/ は通常のcommit対象外なので、ADIのmain成果物だけを安全な明示pathで追加する。
        if "1.1" in _active_base_step_ids:
            adi_questionnaire_include_paths.extend(
                path
                for path in (
                    f"qa/D{number:02d}-original-docs-questionnaire.md"
                    for number in range(1, 22)
                )
                if Path(path).is_file()
            )
        if "1.2" in _active_base_step_ids:
            cross_path = "qa/original-docs-cross-questionnaire.md"
            if Path(cross_path).is_file():
                adi_questionnaire_include_paths.append(cross_path)

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
    si_result: Optional[Dict[str, Any]] = None
    si_error: Optional[str] = None

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

        _self_improve_repo_root = Path(__file__).resolve().parent.parent
        _workflow_outputs = collect_workflow_output_paths(
            workflow_id,
            repo_root=_self_improve_repo_root,
        )
        _workflow_default = _si_scope_defaults.get(workflow_id, "")

        # 部分的な output_paths 宣言をそのまま scope にすると、未宣言 Step の
        # 成果物が scope 外へ落ちる。DAG 根を被覆できた場合のみパス直指定へ
        # 切り替え、それ以外は既定ディレクトリを floor として維持する。
        _outputs_cover_workflow = bool(_workflow_outputs) and (
            workflow_output_paths_cover_workflow(
                workflow_id,
                repo_root=_self_improve_repo_root,
            )
        )

        # target_scope が明示指定されている場合はそれを優先する。
        # 未指定かつ output_paths が workflow 全体を被覆できた場合は
        # scope 文字列は不要（パス直指定）。
        # 被覆できない場合（未宣言・部分宣言・fan-out 展開失敗）は
        # workflow_default へフォールバックする。
        effective_si_scope = (
            config.self_improve_target_scope
            or (_workflow_default if not _outputs_cover_workflow else "")
        )
        orig_scope = config.self_improve_target_scope
        config.self_improve_target_scope = effective_si_scope

        # scan_codebase に渡せるよう一時属性として保持（設定前の値を退避）
        _prev_resolved_step_paths = getattr(config, "_resolved_step_output_paths", None)
        _prev_resolved_wf_default = getattr(config, "_resolved_workflow_default", "")
        _prev_scope_ceiling_paths = getattr(
            config,
            "_resolved_scope_ceiling_paths",
            None,
        )
        _prev_scope_precondition_error = getattr(
            config,
            "_resolved_scope_precondition_error",
            "",
        )
        config._resolved_step_output_paths = _workflow_outputs  # type: ignore[attr-defined]
        config._resolved_workflow_default = _workflow_default  # type: ignore[attr-defined]
        config._resolved_scope_ceiling_paths = (  # type: ignore[attr-defined]
            _workflow_outputs if workflow_id in {"aag", "aagd"} else None
        )
        config._resolved_scope_precondition_error = (  # type: ignore[attr-defined]
            _agent_fanout_scope_precondition_error(
                workflow_id,
                _workflow_outputs,
                _self_improve_repo_root,
            )
        )

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
                    repo_root=str(_self_improve_repo_root),
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
            _existing_criterion_definitions = task_goal.get(
                "criterion_definitions",
                [],
            )
            task_goal = TaskGoal(
                goal_description=task_goal["goal_description"],
                success_criteria=_override_criteria,
                reward_weights=task_goal["reward_weights"],
                tdd_phase=task_goal["tdd_phase"],
            )
            if _existing_criterion_definitions:
                task_goal["criterion_definitions"] = list(
                    _existing_criterion_definitions
                )

        si_task_goal = task_goal

        # workflow_id をループ内で参照できるよう config に一時設定
        _prev_workflow_id = getattr(config, "workflow_id", "")
        config.workflow_id = workflow_id  # type: ignore[attr-defined]

        try:
            # run_improvement_loop は同期関数（内部で subprocess.run を使用）のため、
            # asyncio イベントループをブロックしないようスレッドプールに委譲する
            loop = asyncio.get_running_loop()
            try:
                from .split_fork import resolve_work_root as _rwr
            except ImportError:  # pragma: no cover - top-level module import compatibility
                from split_fork import resolve_work_root as _rwr  # type: ignore[no-redef]
            si_result = await loop.run_in_executor(
                None,
                functools.partial(
                    run_improvement_loop,
                    config=config,
                    work_dir=_rwr() / "self-improve",
                    repo_root=str(_self_improve_repo_root),
                    task_goal=task_goal,
                ),
            )
            if si_result is None:  # pragma: no cover - defensive executor boundary
                si_result = {
                    "iterations_completed": 0,
                    "final_score": 0,
                    "records": [],
                    "stopped_reason": "blocked",
                    "reward_history": [],
                    "final_goal_achievement_pct": 0.0,
                    "final_criterion_results": [],
                    "final_verification": {"overall": "BLOCKED"},
                    "blocked_reason": "self_improve_executor_returned_none",
                }
        finally:
            config.self_improve_target_scope = orig_scope  # 復元
            config.workflow_id = _prev_workflow_id  # type: ignore[attr-defined]
            config._resolved_step_output_paths = _prev_resolved_step_paths  # type: ignore[attr-defined]
            config._resolved_workflow_default = _prev_resolved_wf_default  # type: ignore[attr-defined]
            config._resolved_scope_ceiling_paths = _prev_scope_ceiling_paths  # type: ignore[attr-defined]
            config._resolved_scope_precondition_error = _prev_scope_precondition_error  # type: ignore[attr-defined]

        console.event(
            f"Self-Improve 完了: {si_result['iterations_completed']} イテレーション, "
            f"最終スコア={si_result['final_score']}, "
            f"ゴール達成率={si_result['final_goal_achievement_pct'] * 100:.1f}%, "
            f"終了理由={si_result['stopped_reason']}"
        )
        if not _self_improve_result_succeeded(si_result, si_task_goal):
            si_error = (
                "Post-DAG Self-Improve が成功条件を満たさず停止しました: "
                f"reason={si_result.get('stopped_reason', 'unknown')}, "
                f"blocked_reason={si_result.get('blocked_reason', '') or 'none'}"
            )
            console.error(si_error)
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
        if config.enable_auto_merge and "src" in _ignore_paths_for_commit:
            # enable_auto_merge（全自動）時は Deploy 成果物（src/infra/azure 等）を PR に
            # 含めるため src を除外対象から外す。Deploy 境界 push に加え、create_pr 等で
            # working_branch が作られる経路でも最終 push に Deploy 成果物を含める。
            _ignore_paths_for_commit = [p for p in _ignore_paths_for_commit if p != "src"]

        prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
        display_name_for_commit = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)
        if si_error:
            pushed = False
            pr_error = si_error
            console.warning(
                "Self-Improve 未達のため commit / push / PR 作成をスキップしました。"
            )
        else:
            pushed = _git_add_commit_push(
                branch=working_branch,
                commit_message=f"[{prefix}] {display_name_for_commit} — SDK ローカル実行の成果物",
                console=console,
                ignore_paths=_ignore_paths_for_commit,
                protected_baseline=protected_baseline,
                target_output_paths=_target_output_paths,
                include_paths=[
                    *qa_akm_include_paths,
                    *adi_questionnaire_include_paths,
                ],
            )
        if pushed:
            # live フェーズだけが失敗した場合、local generation checkpoint の
            # 成果物は完成しているため破棄せず draft PR として残す。
            retain_checkpoint = should_retain_local_checkpoint(
                wf.id, getattr(executor, "failed", None)
            )
            if executor.failed and not retain_checkpoint:
                pr_error = "失敗 Step があるため PR 作成をスキップしました。"
                console.warning(pr_error)
            else:
                if retain_checkpoint:
                    console.warning(
                        "live フェーズの Step が失敗しました。local generation checkpoint の"
                        "成果物を draft PR として保持します（auto-merge しません）。"
                    )
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
                    all_steps_succeeded=not executor.failed,
                    local_checkpoint_only=retain_checkpoint,
                )
                if pr_number is None:
                    pr_error = "PR 作成に失敗しました。ログを確認してください。"
                elif config.auto_coding_agent_review:
                    code_review_error = await _request_code_review(
                        pr_number=pr_number,
                        config=config,
                        console=console,
                    )
                # FR-RTO-08: PR 番号が確定した時点で target を再通知する。
                _emit_github_target_event(
                    console,
                    repo=config.repo,
                    issue_number=root_issue_num,
                    pr_number=pr_number,
                    branch=working_branch,
                    base_branch=config.base_branch,
                    created_by_hve=hve_created_branch,
                    delete_local_merged_branch=bool(
                        getattr(config, "delete_local_merged_branch", True)
                    ),
                )
            if pr_number is not None and executor.failed and not retain_checkpoint:
                console.warning("失敗 Step がある状態で PR が作成済みのため、cleanup を実行します。")
                _cleanup_failed_pr_if_created(
                    pr_number,
                    working_branch if hve_created_branch else None,
                    config,
                    console,
                )
                pr_number = None
                pr_error = "失敗 Step があるため作成済み PR を close / branch cleanup しました。"
            # FR-CLI-34: enable_auto_merge による auto-approve-and-merge 完了を検知し、
            # 今回作成した作業ブランチをローカルのみ削除する（既定有効・全 Step 成功時のみ）。
            # マージ検知はポーリングのため、最大 timeout 秒ブロックしうる。
            if (
                pr_number is not None
                and working_branch
                and hve_created_branch
                and getattr(config, "delete_local_merged_branch", True)
                and getattr(config, "enable_auto_merge", False)
                and not executor.failed
            ):
                if not _wait_pr_merged_and_delete_local_branch(
                    pr_number=pr_number,
                    working_branch=working_branch,
                    config=config,
                    console=console,
                ):
                    pr_error = "PR マージ後の check-run 成功を確認できませんでした。"
        else:
            if not si_error:
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
    if si_error and "self-improve" not in blocked_ids:
        blocked_ids.append("self-improve")

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
        if getattr(config, "enable_auto_merge", False) and not failed_ids:
            console.event("auto-approve-ready ラベルにより自動 Approve & merge されます。")
        elif getattr(config, "enable_auto_merge", False) and failed_ids:
            console.event("失敗 Step があるため auto-approve-ready ラベルは付与されません。レビューしてください。")
        else:
            console.event("PR のレビューとマージはご自身で実施してください。")
    if step_scoped_cicd_pr_numbers:
        console.event(
            "Step 単位 CI/CD PR: "
            + ", ".join(f"Step.{sid}=#{num}" for sid, num in sorted(step_scoped_cicd_pr_numbers.items()))
        )
    elif failed_ids and (working_branch or step_scoped_cicd_branches):
        console.event("失敗 Step があるため PR 作成をスキップしました。auto-approve-ready ラベルは付与されません。")

    _emit_runtime_summary(console, config)
    if _rt_recorder is not None:
        _rt_recorder.close()
    if _mcp_io_logger is not None:
        _mcp_io_logger.close()
    return {
        "workflow_id": workflow_id,
        "completed": completed_ids,
        "failed": failed_ids,
        "skipped": skipped_ids,
        "blocked": blocked_ids,
        "elapsed_total": elapsed_total,
        "code_review_error": code_review_error,
        "pr_number": pr_number,
        "step_pr_numbers": dict(step_scoped_cicd_pr_numbers),
        "root_issue_num": root_issue_num,
        "working_branch": working_branch,
        "error": pr_error or si_error,
        "original_docs_questionnaire_validation": (
            original_docs_questionnaire_validation_result
        ),
        # criteria evidence と停止理由を含む Post-DAG Self-Improve の正本結果。
        "self_improve_result": si_result,
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
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
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
    try:
        client = _create_copilot_client_from_config(
            config,
            log_level=_effective_log_level,
            cli_args=config.cli_args,
        )
    except ImportError:
        return (
            "GitHub Copilot SDK がインストールされていません。\n"
            "  pip install github-copilot-sdk  # または適切なパッケージ名で再試行してください。"
        )
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
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(_review_model)
        if _wire_model:
            _review_session_opts["model"] = _wire_model
        _apply_reasoning_effort(_review_session_opts, config, model_value=_review_model, kind="review")
        session = await _create_session_with_auto_reasoning_fallback(
            client,
            _review_session_opts,
            config=config,
            step_id="orchestrator",
            subtask_kind="review",
            console=console,
        )
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
        try:
            from .runner import format_exception_for_log
        except ImportError:
            from runner import format_exception_for_log  # type: ignore[no-redef]
        error_msg = (
            "Code Review Agent の実行中にエラーが発生しました: "
            f"{format_exception_for_log(exc)}"
        )
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

def _generate_gui_title(
    *,
    target_kind: str,
    target_label: str,
    fallback_title: str,
    source_text: str,
    required_prefix: str,
    config: SDKConfig,
    console: Console,
) -> str:
    if not os.environ.get("HVE_GUI_SESSION_ID", "").strip():
        return fallback_title
    console.event(f"Copilot CLI で {target_label} タイトルを生成中...")
    try:
        title = generate_github_title(
            target_kind,
            source_text,
            fallback_title=fallback_title,
            required_prefix=required_prefix,
            cli_path=config.cli_path,
        )
    except GitHubTitleGenerationError:
        console.warning(
            f"Copilot CLI で {target_label} タイトルを生成できなかったため、"
            "既定タイトルを使用します。"
        )
        return fallback_title
    console.event(f"Copilot CLI で {target_label} タイトルを生成しました。")
    return title


def _generate_gui_issue_title(
    *,
    fallback_title: str,
    issue_body: str,
    required_prefix: str,
    config: SDKConfig,
    console: Console,
) -> str:
    """GUI 子プロセスの Root Issue title を生成する（FR-GUI-39）。"""
    return _generate_gui_title(
        target_kind="issue",
        target_label="Root Issue",
        fallback_title=fallback_title,
        source_text=issue_body,
        required_prefix=required_prefix,
        config=config,
        console=console,
    )


def _generate_gui_pr_title(
    *,
    fallback_title: str,
    pr_body: str,
    required_prefix: str,
    config: SDKConfig,
    console: Console,
) -> str:
    """GUI 子プロセスの PR title だけを Copilot CLI で生成する（FR-GUI-39）。"""
    return _generate_gui_title(
        target_kind="pull_request",
        target_label="PR",
        fallback_title=fallback_title,
        source_text=pr_body,
        required_prefix=required_prefix,
        config=config,
        console=console,
    )

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
    all_steps_succeeded: bool = True,
    local_checkpoint_only: bool = False,
) -> Optional[int]:
    """PR を作成する。

    Args:
        all_steps_succeeded: 全 Step が成功したか。False の場合は PR を作成しない
            （失敗成果物の PR 化と auto-merge 誤発火を防ぐ fail-closed 条件）。
        local_checkpoint_only: live フェーズだけが失敗し、local generation
            checkpoint の成果物を draft PR として残す場合に True。
            この PR は auto-merge しない。

    Returns:
        PR 番号 (int) または None（作成失敗時）
    """
    if not all_steps_succeeded and not local_checkpoint_only:
        console.warning("失敗 Step があるため PR 作成をスキップします。")
        return None

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

    if getattr(config, "enable_auto_merge", False) and all_steps_succeeded and not local_checkpoint_only:
        # 案 P: auto-approve-and-merge ワークフローは検証マーカーを要求する。
        # HVE ローカル実行（TDD GREEN 等）の検証を経た成果物として付与し、
        # auto-approve-ready ラベルと併せて自動 Approve & merge を発火させる。
        # 失敗 Step がある場合は検証未達のため付与しない（誤った auto-merge を防止）。
        ac_lines = _collect_deploy_ac_verification_lines()
        if ac_lines:
            body_lines.extend([
                "",
                "## Deploy AC Verification",
                "`ac-verification.md` の AC-ID / 内容 / 状態のみを転記します。",
                "",
            ])
            body_lines.extend(ac_lines)
        body_lines.append("")
        body_lines.append("<!-- validation-confirmed -->")

    pr_body = "\n".join(body_lines)
    fallback_title = f"[{prefix}] {display_name}"
    title = _generate_gui_pr_title(
        fallback_title=fallback_title,
        pr_body=pr_body,
        required_prefix=f"[{prefix}] ",
        config=config,
        console=console,
    )
    if local_checkpoint_only:
        title += " — local checkpoint (draft)"

    try:
        _pr_kwargs: Dict[str, Any] = {
            "title": title,
            "body": pr_body,
            "head": head_branch,
            "base": base_branch,
            "repo": repo,
            "token": token,
        }
        if local_checkpoint_only:
            _pr_kwargs["draft"] = True
        pr_num = create_pull_request(**_pr_kwargs)
        console.event(f"PR #{pr_num} を作成しました。")
        # 案 P: enable_auto_merge（全自動）かつ全 Step 成功時のみ auto-approve-ready
        # ラベルを付与し、auto-approve-and-merge ワークフローによる自動 Approve & merge
        # を発火させる。失敗 Step がある場合は付与しない（誤った auto-merge を防止）。
        if getattr(config, "enable_auto_merge", False) and all_steps_succeeded and not local_checkpoint_only:
            try:
                add_labels(pr_num, ["auto-approve-ready"], repo=repo, token=token)
                console.event(
                    f"PR #{pr_num} に auto-approve-ready ラベルを付与しました。"
                )
            except Exception as exc:  # noqa: BLE001 - ラベル付与失敗は PR 作成成功を妨げない
                console.warning(
                    f"auto-approve-ready ラベルの付与に失敗しました: {exc}"
                )
        return pr_num
    except GitHubAPIError as exc:
        console.error(f"PR 作成中にエラーが発生しました: {exc}")
        return None
