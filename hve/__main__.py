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

    # 基本実行 (デフォルト: Auto, 並列15, compact, Issue/PR作成なし)
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

    # ARD（要求定義の自動化）
    python -m hve orchestrate --workflow ard --company-name "株式会社サンプル"
    python -m hve orchestrate --workflow ard --company-name "株式会社サンプル" \\
      --target-business "ロイヤルティプログラム事業"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

try:
    from .config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_CHOICES, SDKConfig
except ImportError:
    from config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_CHOICES, SDKConfig  # type: ignore[no-redef]


def _ts() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


# -----------------------------------------------------------------------
# Auto モデル定数
# -----------------------------------------------------------------------

MODEL_AUTO = MODEL_AUTO_VALUE

# AKM デフォルト値
_AKM_DEFAULT_SOURCES = "qa"
_AKM_DEFAULT_TARGET_FILES = "qa/*.md"
_AKM_SOURCES_OPTIONS = [
    "qa のみ",
    "original-docs のみ",
    "両方",
]
_AKM_SOURCES_MAP = {
    "qa のみ": "qa",
    "original-docs のみ": "original-docs",
    "両方": "both",
}
_AQOD_DEFAULT_TARGET_SCOPE = "original-docs/"
_AQOD_DEFAULT_DEPTH = "standard"
_AQOD_DEPTH_CHOICES = ("standard", "lightweight")
_AQOD_DEPTH_MENU_OPTIONS = (
    "standard     — 全カテゴリ",
    "lightweight  — 不明瞭/矛盾のみ",
)
_ADOC_DOC_PURPOSE_CHOICES = ("all", "onboarding", "refactoring", "migration")
_ADOC_DOC_PURPOSE_MENU_OPTIONS = (
    "all         — 全用途",
    "onboarding  — 新規参画者向け",
    "refactoring — 改善・保守向け",
    "migration   — 移行計画向け",
)
_ADOC_DEFAULT_DOC_PURPOSE = "all"
_ADOC_MAX_FILE_LINES_CHOICES = (300, 500, 1000)
_ADOC_MAX_FILE_LINES_MENU_OPTIONS = (
    "300 行  — 小さめに分割",
    "500 行  — 既定",
    "1000 行 — 大きめに分割",
)
_ADOC_DEFAULT_MAX_FILE_LINES = 500
_ADOC_DEFAULT_EXCLUDE_PATTERNS = "node_modules/,vendor/,dist/,*.lock,__pycache__/"

# ARD デフォルト値
_ARD_DEFAULT_SURVEY_PERIOD_YEARS = 30
_ARD_DEFAULT_TARGET_REGION = "グローバル全体"
_ARD_DEFAULT_ANALYSIS_PURPOSE = "中長期成長戦略の立案"

_APP_ID_AUTO_HINTS = {
    "aad-web": "Webフロントエンド + クラウドの APP-ID を自動選択",
    "asdw-web": "Webフロントエンド + クラウドの APP-ID を自動選択",
    "abd": "データバッチ処理 / バッチの APP-ID を自動選択",
    "abdv": "データバッチ処理 / バッチの APP-ID を自動選択",
}

_PARAM_PROMPT_LABELS = {
    "app_ids": "対象 APP-ID",
    "app_id": "対象 APP-ID（単一）",
    "resource_group": "Azure リソースグループ名（任意）",
    "usecase_id": "対象ユースケースID（任意）",
    "batch_job_id": "対象バッチジョブID（カンマ区切り・任意）",
    "target_scope": "対象スコープ",
    "focus_areas": "重点観点（任意）",
    "target_dirs": "ドキュメント生成対象ディレクトリ（カンマ区切り。省略 = 全体）",
    "exclude_patterns": "除外パターン（カンマ区切り）",
    "issue_title": "GitHub Issue タイトル（任意）",
    "additional_comment": "GitHub Issue への追加コメント（任意）",
    "sources": "取り込みソース",
    "target_files": "対象ファイルパス",
    "force_refresh": "knowledge/ 完全再生成",
    "custom_source_dir": "追加ソースディレクトリ",
    "enable_auto_merge": "PR 自動 Approve & Auto-merge",
    "doc_purpose": "ドキュメント主目的",
    "max_file_lines": "大規模ファイル分割閾値",
    "create_remote_mcp_server": "Remote MCP Server を作成する",
    # ARD 固有
    "company_name": "対象企業名（Step 1 選択時は必須）",
    "target_business": "対象業務名",  # サフィックスは _build_target_business_label で動的付与
    "survey_base_date": "調査基準日（YYYY-MM-DD、任意）",
    "survey_period_years": "調査期間年数（任意）",
    "target_region": "対象地域（任意）",
    "analysis_purpose": "分析目的（任意）",
    "attached_docs": "添付資料のファイルパス（カンマ区切り・任意）",
}

_PARAM_DEFAULTS = {
    "resource_group": "",
    "usecase_id": "",
    "batch_job_id": "",
    "target_scope": _AQOD_DEFAULT_TARGET_SCOPE,
    "focus_areas": "",
    "target_dirs": "",
    "exclude_patterns": _ADOC_DEFAULT_EXCLUDE_PATTERNS,
    "create_remote_mcp_server": True,
    # ARD 固有
    "company_name": "",
    "target_business": "",
    "survey_base_date": "",  # 空 → orchestrator 側で today() を採用
    "survey_period_years": _ARD_DEFAULT_SURVEY_PERIOD_YEARS,
    "target_region": _ARD_DEFAULT_TARGET_REGION,
    "analysis_purpose": _ARD_DEFAULT_ANALYSIS_PURPOSE,
    "attached_docs": "",
}


def _split_csv(value: str) -> List[str]:
    """カンマ区切り文字列を空要素なしのリストに変換する。"""
    return [part.strip() for part in value.split(",") if part.strip()]


def _prompt_app_ids(con, wf_id: str) -> dict:
    """APP-ID を 1 回だけ尋ね、単一指定時は app_id も派生させる。"""
    auto_hint = _APP_ID_AUTO_HINTS.get(wf_id)
    if auto_hint:
        label = f"対象アプリケーション (APP-ID、カンマ区切り・任意。未指定時は {auto_hint})"
    else:
        label = "対象アプリケーション (APP-ID、カンマ区切り・任意)"
    raw = con.prompt_input(label, default="", required=False)
    app_ids = _split_csv(raw or "")
    if not app_ids:
        return {}
    params = {"app_ids": app_ids}
    if len(app_ids) == 1:
        params["app_id"] = app_ids[0]
    return params


def _prompt_param_input(con, param_name: str) -> str:
    """ワークフロー固有パラメータを内部名ではなく表示ラベルで入力させる。"""
    label = _PARAM_PROMPT_LABELS.get(param_name, param_name)
    default = _PARAM_DEFAULTS.get(param_name, "")
    return con.prompt_input(label, default=default, required=False)


def _build_target_business_label(con, selected_steps) -> str:
    """ARD ウィザードの target_business ラベルを Step 1 選択有無で切り替える。

    - Step 1 選択時: 補足説明を灰色（DIM）で付記し任意入力。
    - Step 1 非選択時: 必須マークは prompt_input 側の `required=True` で赤色付与。
    """
    s = getattr(con, "s", None)
    if "1" in selected_steps:
        if s is not None:
            return f"対象業務名 {s.DIM}（Step 1で作成される最上位の戦略的提言を基に LLM 生成された対象業務説明文）{s.RESET}"
        return "対象業務名（Step 1で作成される最上位の戦略的提言を基に LLM 生成された対象業務説明文）"
    return "対象業務名"


def _default_param_value(param_name: str):
    """クイック全自動で使うワークフロー固有パラメータ既定値。"""
    if param_name == "doc_purpose":
        return _ADOC_DEFAULT_DOC_PURPOSE
    if param_name == "max_file_lines":
        return _ADOC_DEFAULT_MAX_FILE_LINES
    return _PARAM_DEFAULTS.get(param_name, "")


def _format_param_value(value) -> str:
    """確認パネル用にパラメータ値を読みやすく整形する。"""
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(なし)"
    return str(value) if value else "(なし)"


def _format_param_label(param_name: str) -> str:
    """確認パネル用の表示名を返す。"""
    return _PARAM_PROMPT_LABELS.get(param_name, param_name)


def _step_options_with_groups(wf) -> tuple:
    """コンテナステップの見出しを使ってステップ選択肢を整形する。"""
    container_titles = {s.id: s.title for s in wf.steps if s.is_container}
    non_container_steps = [s for s in wf.steps if not s.is_container]
    options = []
    for step in non_container_steps:
        parent_id = step.id.split(".", 1)[0] if "." in step.id else ""
        parent_title = container_titles.get(parent_id)
        if parent_title:
            options.append(f"{parent_title} > [{step.id}] {step.title}")
        else:
            options.append(f"[{step.id}] {step.title}")
    return non_container_steps, options


def _collect_ard_wizard_params(con, *, is_quick_auto: bool) -> tuple[dict, list[str]]:
    """ARD ワークフロー固有のパラメータ収集と selected_steps 計算。

    Returns:
        (params, selected_steps) のタプル。
        - selected_steps: ウィザードでユーザーが選択した Step ID 一覧。
          Enter 時の初期値は ["2", "3"]。
    """
    from datetime import date

    params: dict = {}
    _ard_step_ids = ["1", "2", "3"]
    _ard_step_options = [
        "[1] 事業分析（対象業務 未定）",
        "[2] 事業分析（対象業務 指定済）",
        "[3] ユースケース作成",
    ]
    selected_indices = con.prompt_multi_select(
        "ARD で実行するステップを選択",
        _ard_step_options,
        default_indices=[1, 2],
    )
    selected_steps = [_ard_step_ids[i] for i in selected_indices if 0 <= i < len(_ard_step_ids)]
    if not selected_steps:
        selected_steps = ["2", "3"]

    requires_company_name = "1" in selected_steps
    requires_target_business = ("2" in selected_steps) and ("1" not in selected_steps)
    target_business_label = _build_target_business_label(con, selected_steps)

    if is_quick_auto:
        # Step 1 を選択した場合のみ company_name を必須とする。
        params["company_name"] = con.prompt_input(
            _PARAM_PROMPT_LABELS["company_name"],
            default="",
            required=requires_company_name,
        )
        if "2" in selected_steps:
            params["target_business"] = con.prompt_input(
                target_business_label,
                default="",
                required=requires_target_business,
            )
        else:
            params["target_business"] = ""
        params["survey_base_date"] = date.today().isoformat()
        params["survey_period_years"] = _ARD_DEFAULT_SURVEY_PERIOD_YEARS
        params["target_region"] = _ARD_DEFAULT_TARGET_REGION
        params["analysis_purpose"] = _ARD_DEFAULT_ANALYSIS_PURPOSE
        params["attached_docs"] = []
    else:
        params["company_name"] = con.prompt_input(
            _PARAM_PROMPT_LABELS["company_name"],
            default="",
            required=requires_company_name,
        )
        if "2" in selected_steps:
            params["target_business"] = con.prompt_input(
                target_business_label,
                default="",
                required=requires_target_business,
            )
        else:
            params["target_business"] = ""
        survey_base = con.prompt_input(
            _PARAM_PROMPT_LABELS["survey_base_date"],
            default=date.today().isoformat(), required=False,
        )
        params["survey_base_date"] = survey_base or date.today().isoformat()
        survey_years = con.prompt_input(
            _PARAM_PROMPT_LABELS["survey_period_years"],
            default=str(_ARD_DEFAULT_SURVEY_PERIOD_YEARS), required=False,
        )
        try:
            params["survey_period_years"] = int(survey_years)
        except (TypeError, ValueError):
            params["survey_period_years"] = _ARD_DEFAULT_SURVEY_PERIOD_YEARS
        params["target_region"] = con.prompt_input(
            _PARAM_PROMPT_LABELS["target_region"],
            default=_ARD_DEFAULT_TARGET_REGION, required=False,
        )
        params["analysis_purpose"] = con.prompt_input(
            _PARAM_PROMPT_LABELS["analysis_purpose"],
            default=_ARD_DEFAULT_ANALYSIS_PURPOSE, required=False,
        )
        attached_raw = con.prompt_input(
            _PARAM_PROMPT_LABELS["attached_docs"], default="", required=False,
        )
        params["attached_docs"] = _split_csv(attached_raw or "")

    return params, selected_steps


def _collect_generic_workflow_params(con, wf, *, is_quick_auto: bool) -> dict:
    """AKM/AQOD 以外のワークフロー固有パラメータを収集する。"""
    params: dict = {}
    if "app_ids" in wf.params or "app_id" in wf.params:
        if not is_quick_auto:
            params.update(_prompt_app_ids(con, wf.id))
    for param_name in wf.params:
        if param_name in ("app_ids", "app_id"):
            continue
        if is_quick_auto:
            params[param_name] = _default_param_value(param_name)
        elif param_name == "doc_purpose":
            params[param_name] = _prompt_valid_doc_purpose(con)
        elif param_name == "max_file_lines":
            params[param_name] = _prompt_valid_max_file_lines(con)
        elif param_name == "create_remote_mcp_server":
            params[param_name] = con.prompt_yes_no(
                _PARAM_PROMPT_LABELS["create_remote_mcp_server"],
                default=_PARAM_DEFAULTS["create_remote_mcp_server"],
            )
        else:
            params[param_name] = _prompt_param_input(con, param_name)
    return params


def _default_akm_target_files(sources: str) -> str:
    """AKM の sources に応じた target_files 既定値を返す。"""
    if sources == "original-docs":
        return "original-docs/*"
    if sources == "both":
        return ""
    return _AKM_DEFAULT_TARGET_FILES


def _prompt_valid_doc_purpose(con) -> str:
    """ADOC の doc_purpose をメニュー選択させる。"""
    default_idx = _ADOC_DOC_PURPOSE_CHOICES.index(_ADOC_DEFAULT_DOC_PURPOSE)
    selected_idx = con.menu_select(
        "ドキュメントの主目的を選択してください",
        list(_ADOC_DOC_PURPOSE_MENU_OPTIONS),
        allow_empty=True,
        default_index=default_idx,
    )
    return _ADOC_DOC_PURPOSE_CHOICES[default_idx if selected_idx == -1 else selected_idx]


def _prompt_valid_aqod_depth(con) -> str:
    """AQOD の depth をメニュー選択させる。"""
    default_idx = _AQOD_DEPTH_CHOICES.index(_AQOD_DEFAULT_DEPTH)
    selected_idx = con.menu_select(
        "分析の深さを選択してください",
        list(_AQOD_DEPTH_MENU_OPTIONS),
        allow_empty=True,
        default_index=default_idx,
    )
    return _AQOD_DEPTH_CHOICES[default_idx if selected_idx == -1 else selected_idx]


def _prompt_valid_max_file_lines(con) -> int:
    """ADOC の max_file_lines をメニュー選択させる。"""
    default_idx = _ADOC_MAX_FILE_LINES_CHOICES.index(_ADOC_DEFAULT_MAX_FILE_LINES)
    selected_idx = con.menu_select(
        "大規模ファイル分割閾値を選択してください",
        list(_ADOC_MAX_FILE_LINES_MENU_OPTIONS),
        allow_empty=True,
        default_index=default_idx,
    )
    return _ADOC_MAX_FILE_LINES_CHOICES[default_idx if selected_idx == -1 else selected_idx]


def _collect_agentic_retrieval_wizard_answers(con, wf_id: str, *, is_quick_auto: bool) -> dict:
    """Agentic Retrieval 関連の質問（Q1〜Q6）をウィザードで収集する。

    AAD-WEB は Q1・Q3 のみ（設計フェーズ）。ASDW-WEB は Q1〜Q6 全て。
    `is_quick_auto=True` のときは既定値をそのまま返す。

    Returns:
        ``normalize_agentic_retrieval_answers`` への入力に対応するキー辞書。
    """
    try:
        from .template_engine import _AGENTIC_RETRIEVAL_QUESTIONS, _AGENTIC_RETRIEVAL_KEYS_FOR
    except ImportError:
        from template_engine import _AGENTIC_RETRIEVAL_QUESTIONS, _AGENTIC_RETRIEVAL_KEYS_FOR  # type: ignore[no-redef]

    # 後方互換エイリアス解決
    _wf_id = {"aad": "aad-web", "asdw": "asdw-web"}.get(wf_id, wf_id)
    keys = _AGENTIC_RETRIEVAL_KEYS_FOR.get(_wf_id, [])
    if not keys:
        return {}

    answers: dict = {}
    if is_quick_auto:
        for key in keys:
            q = _AGENTIC_RETRIEVAL_QUESTIONS[key]
            kind = q["kind"]
            default = q["default"]
            if kind == "dropdown":
                opts = q["options"]
                answers[key] = opts[default]
            elif kind == "checkboxes":
                answers[key] = list(default) if isinstance(default, list) else [default] if default else []
            elif kind == "checkbox":
                answers[key] = default
            else:
                answers[key] = default
        return answers

    con._print(
        "\n  ─── Agentic Retrieval 設定 ───────────────────────────",
        ts=False,
    )
    for key in keys:
        q = _AGENTIC_RETRIEVAL_QUESTIONS[key]
        label = q["label"]
        desc = q["description"]
        kind = q["kind"]
        default = q["default"]
        prompt_text = f"{label}\n  {desc}"

        if kind == "dropdown":
            opts = q["options"]
            sel_idx = con.menu_select(prompt_text, opts, allow_empty=True, default_index=default)
            if sel_idx == -1:
                sel_idx = default
            answers[key] = opts[sel_idx]
        elif kind == "checkboxes":
            opts = q["options"]
            defaults_list = default if isinstance(default, list) else []
            sel_indices = con.prompt_multi_select(prompt_text, opts)
            if not sel_indices:
                # 未選択時は既定値を使用
                defaults_set = set(defaults_list)
                sel_indices = [i for i, o in enumerate(opts) if o in defaults_set] or [0]
            answers[key] = [opts[i] for i in sel_indices]
        elif kind == "checkbox":
            answers[key] = con.prompt_yes_no(prompt_text, default=default)
        else:
            answers[key] = con.prompt_input(prompt_text, default=str(default) if default else "")

    return answers




def _prompt_akm_params(
    con,
    is_quick_auto: bool,
    *,
    will_create_pr: bool = False,
) -> dict:
    """AKM ワークフローのパラメータを収集する。

    Args:
        con: Console インスタンス。
        is_quick_auto: クイック全自動モードの場合 True。
        will_create_pr: GitHub Issue または PR を作成する場合 True。
            False のときは `enable_auto_merge` プロンプトを表示せず False を採用する。
    """
    params: dict = {}

    if is_quick_auto:
        params["sources"] = _AKM_DEFAULT_SOURCES
        params["target_files"] = _default_akm_target_files(params["sources"])
        params["force_refresh"] = True
        params["custom_source_dir"] = ""
        params["enable_auto_merge"] = False
        return params

    sources_idx = con.menu_select(
        "取り込みソースを選択してください",
        _AKM_SOURCES_OPTIONS,
        default_index=0,
    )
    sources_display = _AKM_SOURCES_OPTIONS[sources_idx]
    params["sources"] = _AKM_SOURCES_MAP[sources_display]

    default_target = _default_akm_target_files(params["sources"])
    target_input = con.prompt_input(
        "対象ファイルパス（スペース区切り、省略時: デフォルト）",
        default=default_target,
    )
    target_input_strip = (target_input or "").strip()
    params["target_files"] = target_input_strip if target_input_strip else default_target

    params["force_refresh"] = con.prompt_yes_no(
        "既存 knowledge/ 出力を完全に再生成する？",
        default=True,
    )
    params["custom_source_dir"] = con.prompt_input(
        "追加ソースディレクトリ（スペース区切り・任意）",
        default="",
    )
    params["enable_auto_merge"] = False

    return params


def _resolve_model(model: str) -> tuple:
    """モデル名を解決する。

    Args:
        model: 入力モデル名。空文字または MODEL_AUTO の場合は Auto を返す。

    Returns:
        (resolved_model, display_name) のタプル。
    """
    if model in ("", MODEL_AUTO):
        return MODEL_AUTO_VALUE, MODEL_AUTO
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
    run_parser = sub.add_parser(
        "run",
        help="インタラクティブモードでワークフローを実行する (デフォルト)",
    )
    run_parser.add_argument(
        "--banner",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="banner",
        help="起動時バナー表示を制御する (--banner: 表示, --no-banner: 抑止, 省略時: 表示)",
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
            "aad(App Detail Design) / "
            "asdw(App Dev Microservice Azure) / "
            "abd(Batch Design) / "
            "abdv(Batch Dev) / "
            "akm(Knowledge Management) / "
            "aqod(Original Docs Review) / "
            "adoc(Source Codeからのドキュメント作成)"
        ),
    )

    # モデル
    orch.add_argument(
        "--model", "-m",
        default=None,
        metavar="MODEL",
        help="使用するモデル名 (デフォルト: Auto)。Auto を指定すると GitHub が最適モデルを自動選択します",
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
    orch.add_argument(
        "--workiq",
        action="store_true",
        default=False,
        help=(
            "Work IQ 経由の M365 データ（メール・チャット・会議・ファイル）参照を有効にする。"
            "QA フェーズと、AKM では実行後レビューの後方互換トリガーとしても扱う "
            "(デフォルト: 無効。@microsoft/workiq のインストールが必要)"
        ),
    )
    orch.add_argument(
        "--workiq-akm-review",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="AKM 実行後レビューで Work IQ 検証を有効/無効化する（未指定時は --workiq / WORKIQ_ENABLED を継承）",
    )
    orch.add_argument(
        "--workiq-draft",
        action="store_true",
        default=False,
        help="QA フェーズで質問ごとに Work IQ 回答ドラフトを生成する（デフォルト: 無効）",
    )
    orch.add_argument(
        "--workiq-draft-output-dir",
        default=None,
        metavar="DIR",
        help="Work IQ 補助レポートの出力先ディレクトリ（互換のためオプション名は据え置き。未指定時: 設定/環境変数、最終既定値 qa）",
    )
    orch.add_argument(
        "--workiq-tenant-id",
        default=None,
        metavar="TENANT_ID",
        help="Work IQ の Entra テナント ID（省略時: common）",
    )
    orch.add_argument(
        "--workiq-prompt-qa",
        default=None,
        metavar="PROMPT",
        help="Work IQ の QA 用プロンプトを上書きする（{target_content} プレースホルダ使用可。省略時: デフォルトプロンプト）",
    )
    orch.add_argument(
        "--workiq-prompt-km",
        default=None,
        metavar="PROMPT",
        help="Work IQ の KM 用プロンプトを上書きする（AKM 実行後レビューで使用）",
    )
    orch.add_argument(
        "--workiq-prompt-review",
        default=None,
        metavar="PROMPT",
        help="Work IQ の Original Docs レビュー用プロンプトを上書きする（互換用）",
    )
    orch.add_argument(
        "--workiq-per-question-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Work IQ: QA 質問ごとのクエリタイムアウト秒数（未指定時: 環境変数/設定（既定 1200 秒 = 20 分））",
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
            " ⚠️ PR 作成のみで自動マージは行いません（Issue Template の auto_merge とは異なります）。"
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
    orch.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="ANSI カラー出力を無効化する。NO_COLOR 環境変数（no-color.org 規格）でも制御可能 (デフォルト: 無効)",
    )
    orch.add_argument(
        "--banner",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="banner",
        help="起動時バナー表示を制御する (--banner: 表示, --no-banner: 抑止, 省略時: 既存の自動判定)",
    )
    orch.add_argument(
        "--screen-reader",
        action="store_true",
        default=False,
        help="スクリーンリーダー対応モード: 絵文字を日本語ラベルに置換し、スピナーを無効化する",
    )
    orch.add_argument(
        "--timestamp-style",
        choices=["prefix", "suffix", "off"],
        default="prefix",
        metavar="{prefix,suffix,off}",
        help="タイムスタンプ表示位置: prefix=行頭（デフォルト）/ suffix=行末（DIM）/ off=非表示",
    )
    orch.add_argument(
        "--final-only",
        action="store_true",
        default=False,
        help="DAG 完了時のサマリと各ステップの最終応答のみを出力する（CI/スクリプト連携用）",
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
        help=(
            "対象アプリケーション (APP-ID) — カンマ区切りで複数指定可。\n"
            "AAD-WEB/ASDW-WEB は Webフロントエンド + クラウド、\n"
            "ABD/ABDV は データバッチ処理/バッチ の APP-ID のみ採用します。\n"
            "未指定時は docs/catalog/app-arch-catalog.md から自動選択します。"
        ),
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
        help=(
            "バッチジョブ ID (ABDV 等で使用、カンマ区切り可)。"
            "APP-ID フィルタ後、対象 Batch APP の文脈で実行します。"
        ),
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
        "--enable-auto-merge",
        action="store_true",
        default=False,
        help="AKM: PR の自動 Approve & Auto-merge を有効にする (デフォルト: 無効)",
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

    # ARD 固有
    orch.add_argument(
        "--company-name",
        default=None,
        metavar="NAME",
        help="ARD: 対象企業名（Step 1 を実行する場合は必須）",
    )
    orch.add_argument(
        "--target-business",
        default=None,
        metavar="NAME",
        help=(
            "ARD: 対象業務名（省略時は Step 1 (Untargeted) → Step 2 (Targeted, 自動生成) → Step 3、"
            "指定時は Step 2 (Targeted) → Step 3）。"
            "値は文章のほか、フォルダパスまたは複数ファイルパス（カンマ区切り）も指定可能。"
        ),
    )
    orch.add_argument(
        "--survey-base-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="ARD: 調査基準日（省略時は実行日）",
    )
    orch.add_argument(
        "--survey-period-years",
        type=int,
        default=None,
        metavar="N",
        help="ARD: 調査期間年数（省略時は 30）",
    )
    orch.add_argument(
        "--target-region",
        default=None,
        metavar="REGION",
        help="ARD: 対象地域（省略時は『グローバル全体』）",
    )
    orch.add_argument(
        "--analysis-purpose",
        default=None,
        metavar="PURPOSE",
        help="ARD: 分析目的（省略時は『中長期成長戦略の立案』）",
    )
    orch.add_argument(
        "--target-recommendation-id",
        default=None,
        metavar="SR_ID",
        help=(
            "ARD: Step 1 完了後に採用する Strategic Recommendation の ID（例: SR-1）。"
            "指定時は対話モードでもこのIDを優先して採用。"
            "省略時は非対話モードでは最初の SR、対話モードではメニュー選択（既定: 先頭）を使用。"
        ),
    )
    orch.add_argument(
        "--attached-docs",
        default=None,
        metavar="PATHS",
        help="ARD: 添付資料パス（カンマ区切り・省略可）",
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
    orch.add_argument(
        "--context-max-chars",
        type=int,
        default=None,
        metavar="N",
        help="各フェーズで注入するコンテキストの最大文字数（未指定時: SDKConfig 既定値 20,000）",
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
        "--self-improve",
        action="store_true",
        default=False,
        help=(
            "自己改善ループ（Phase 4）を有効化する。"
            " --no-self-improve が同時に指定された場合は --no-self-improve に上書きされます。"
            " HVE_AUTO_SELF_IMPROVE=true 環境変数でも有効化できる。"
        ),
    )
    orch.add_argument(
        "--no-self-improve",
        action="store_true",
        default=False,
        help=(
            "自己改善ループ（Phase 4）を無効化する（--self-improve および HVE_AUTO_SELF_IMPROVE=true より優先）。"
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

    # --- workiq-doctor サブコマンド ---
    workiq_doctor = sub.add_parser(
        "workiq-doctor",
        help="Work IQ 連携の診断を実行する (Node.js / npx / @microsoft/workiq / MCP 起動確認)",
    )
    workiq_doctor.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="診断結果を JSON 形式で出力する",
    )
    workiq_doctor.add_argument(
        "--skip-mcp-probe",
        action="store_true",
        default=False,
        help="MCP サーバー起動確認をスキップする",
    )
    workiq_doctor.add_argument(
        "--tenant-id",
        default=None,
        metavar="TENANT_ID",
        help="Work IQ MCP 起動確認時に使用する Entra テナント ID",
    )
    workiq_doctor.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="MCP サーバー起動確認の待ち秒数（デフォルト: 5.0、0より大きい値を指定）",
    )
    workiq_doctor.add_argument(
        "--sdk-probe",
        action="store_true",
        default=False,
        help="Copilot SDK セッション内で _hve_workiq が connected かを追加検証する",
    )
    workiq_doctor.add_argument(
        "--sdk-probe-timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="SDK probe の最大待ち秒数（デフォルト: 30.0）",
    )
    workiq_doctor.add_argument(
        "--event-extractor-self-test",
        action="store_true",
        default=False,
        help="SDK tool イベント抽出ロジックの自己診断を追加実行する",
    )
    workiq_doctor.add_argument(
        "--sdk-tool-probe",
        action="store_true",
        default=False,
        help="Copilot SDK セッションで Work IQ MCP tool が実際に呼び出されるか検証する",
    )
    workiq_doctor.add_argument(
        "--sdk-tool-probe-timeout",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="SDK tool probe の最大待ち秒数（デフォルト: 60.0）",
    )
    workiq_doctor.add_argument(
        "--sdk-event-trace",
        action="store_true",
        default=False,
        help="SDK tool probe 中に観測したイベントの安全な概要を出力する（本文・arguments は出力しない）",
    )
    workiq_doctor.add_argument(
        "--sdk-tool-probe-tools-all",
        action="store_true",
        default=False,
        help="SDK tool probe の MCP 設定で tools=['*'] を使う（診断・切り分け用途のみ）",
    )

    # --- emit-prompt サブコマンド ---
    emit_prompt = sub.add_parser(
        "emit-prompt",
        help="hve/prompts.py を単一ソースとしてプロンプト本文を出力する",
    )
    emit_prompt.add_argument(
        "prompt_name",
        choices=("pre-qa",),
        help="出力するプロンプト名",
    )
    emit_prompt.add_argument(
        "--comment-body",
        action="store_true",
        default=False,
        help="Issue/PR コメント投稿用の前置き込みで出力する",
    )

    # --- resume サブコマンド (Phase 5) ---
    # `resume {list|show|rename|delete|continue}` を hve/resume_cli.py が定義する。
    try:
        from .resume_cli import add_resume_parser
    except ImportError:
        from resume_cli import add_resume_parser  # type: ignore[no-redef]
    add_resume_parser(sub)

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
        from .config import DEFAULT_MODEL, SDKConfig, normalize_model
    except ImportError:
        from config import DEFAULT_MODEL, SDKConfig, normalize_model  # type: ignore[no-redef]

    def _normalize_model_with_warning(model_name: Optional[str]) -> Optional[str]:
        if model_name is None:
            return None
        normalized = normalize_model(model_name)
        if normalized != model_name:
            print(f"WARNING: '{model_name}' is deprecated; use '{normalized}'", file=sys.stderr)
        return normalized

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
        cfg.model = MODEL_AUTO_VALUE
    # Auto モデル解決
    cfg.model, _ = _resolve_model(cfg.model)
    if cfg.model != MODEL_AUTO_VALUE:
        cfg.model = _normalize_model_with_warning(cfg.model) or DEFAULT_MODEL
    _raw_review_model = getattr(args, "review_model", None)
    if _raw_review_model:
        cfg.review_model, _ = _resolve_model(_raw_review_model)
        cfg.review_model = _normalize_model_with_warning(cfg.review_model)
    elif getattr(cfg, "review_model", None):
        cfg.review_model, _ = _resolve_model(cfg.review_model)
        cfg.review_model = _normalize_model_with_warning(cfg.review_model)
    _raw_qa_model = getattr(args, "qa_model", None)
    if _raw_qa_model:
        cfg.qa_model, _ = _resolve_model(_raw_qa_model)
        cfg.qa_model = _normalize_model_with_warning(cfg.qa_model)
    elif getattr(cfg, "qa_model", None):
        cfg.qa_model, _ = _resolve_model(cfg.qa_model)
        cfg.qa_model = _normalize_model_with_warning(cfg.qa_model)
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
    cfg.no_color = True if getattr(args, "no_color", False) else None
    cfg.show_banner = getattr(args, "banner", None)
    cfg.screen_reader = getattr(args, "screen_reader", False)
    cfg.timestamp_style = getattr(args, "timestamp_style", "prefix")
    cfg.final_only = getattr(args, "final_only", False)

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
    if getattr(args, "context_max_chars", None) is not None:
        cfg.context_injection_max_chars = args.context_max_chars

    # Self-Improve: 優先順位 --no-self-improve > --self-improve > HVE_AUTO_SELF_IMPROVE > デフォルト False
    if getattr(args, "no_self_improve", False):
        cfg.self_improve_skip = True
    elif getattr(args, "self_improve", False):
        cfg.auto_self_improve = True
        cfg.self_improve_skip = False

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

    # Work IQ
    if getattr(args, "workiq", False):
        cfg.workiq_enabled = True
        cfg.workiq_qa_enabled = True
    if getattr(args, "workiq_draft", False):
        cfg.workiq_enabled = True
        cfg.workiq_qa_enabled = True
        cfg.workiq_draft_mode = True
    if getattr(args, "workiq_akm_review", None) is not None:
        if args.workiq_akm_review and not cfg.workiq_enabled and cfg.workiq_qa_enabled is None:
            cfg.workiq_qa_enabled = False
        cfg.workiq_akm_review_enabled = args.workiq_akm_review
        cfg.workiq_enabled = cfg.is_workiq_qa_enabled() or cfg.is_workiq_akm_review_enabled()
    workiq_draft_output_dir = getattr(args, "workiq_draft_output_dir", None)
    if workiq_draft_output_dir is not None:
        cfg.workiq_draft_output_dir = workiq_draft_output_dir
    cfg.workiq_tenant_id = getattr(args, "workiq_tenant_id", None)
    cfg.workiq_prompt_qa = getattr(args, "workiq_prompt_qa", None)
    cfg.workiq_prompt_km = getattr(args, "workiq_prompt_km", None)
    cfg.workiq_prompt_review = getattr(args, "workiq_prompt_review", None)
    _workiq_pq_timeout = getattr(args, "workiq_per_question_timeout", None)
    if _workiq_pq_timeout is not None and _workiq_pq_timeout > 0:
        cfg.workiq_per_question_timeout = _workiq_pq_timeout
    # 旧 --aqod-post-qa / aqod_post_qa_enabled は廃止済み。

    # 無視パス（CLI 引数が指定された場合のみ上書き）
    if getattr(args, "ignore_paths", None):
        cfg.ignore_paths = args.ignore_paths
    if cfg.create_pr and cfg.workiq_enabled:
        workiq_output_dir = (cfg.workiq_draft_output_dir or "").strip().strip("/\\") or "qa"
        if workiq_output_dir in cfg.ignore_paths:
            cfg.ignore_paths = [p for p in cfg.ignore_paths if p != workiq_output_dir]

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
        params["enable_auto_merge"] = getattr(args, "enable_auto_merge", False)
    elif getattr(args, "workflow", None) == "aqod":
        params["target_scope"] = getattr(args, "target_scope", None) or _AQOD_DEFAULT_TARGET_SCOPE
        params["depth"] = getattr(args, "depth", None) or _AQOD_DEFAULT_DEPTH
        params["focus_areas"] = getattr(args, "focus_areas", None) or ""
    elif getattr(args, "workflow", None) == "ard":
        from datetime import date
        company_name = getattr(args, "company_name", None)
        target_business = getattr(args, "target_business", None) or ""
        requested_steps = list(params.get("steps") or [])
        normalized_steps = requested_steps
        if requested_steps:
            # ARD Step ID リネーム後の互換変換（旧指定: 1.1/1.2/2）
            legacy_mode = any(s in {"1.1", "1.2"} for s in requested_steps)
            mapped_steps: list[str] = []
            for sid in requested_steps:
                if sid == "1.1":
                    mapped_steps.append("1")
                elif sid == "1.2":
                    mapped_steps.append("2")
                elif sid == "2" and legacy_mode:
                    mapped_steps.append("3")
                else:
                    mapped_steps.append(sid)

            invalid_steps = [sid for sid in mapped_steps if sid not in {"1", "2", "3"}]
            if invalid_steps:
                raise SystemExit(
                    f"ERROR: ARD の無効な --steps が指定されました: {', '.join(invalid_steps)} "
                    "(有効値: 1,2,3)"
                )
            normalized_steps = mapped_steps
            params["steps"] = mapped_steps
        else:
            normalized_steps = ["2", "3"] if target_business.strip() else ["1", "2", "3"]

        if "1" in normalized_steps and not company_name:
            raise SystemExit(
                "ERROR: ARD Step 1 を実行する場合は --company-name が必須です"
            )

        params["company_name"] = company_name or ""
        params["target_business"] = target_business
        params["survey_base_date"] = (
            getattr(args, "survey_base_date", None) or date.today().isoformat()
        )
        params["survey_period_years"] = (
            getattr(args, "survey_period_years", None) or _ARD_DEFAULT_SURVEY_PERIOD_YEARS
        )
        params["target_region"] = (
            getattr(args, "target_region", None) or _ARD_DEFAULT_TARGET_REGION
        )
        params["analysis_purpose"] = (
            getattr(args, "analysis_purpose", None) or _ARD_DEFAULT_ANALYSIS_PURPOSE
        )
        target_recommendation_id = getattr(args, "target_recommendation_id", None)
        if target_recommendation_id:
            params["target_recommendation_id"] = target_recommendation_id
        attached = getattr(args, "attached_docs", None)
        params["attached_docs"] = _split_csv(attached) if attached else []
        if not params.get("steps"):
            params["steps"] = normalized_steps
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
        params["doc_purpose"] = getattr(args, "doc_purpose", None) or _ADOC_DEFAULT_DOC_PURPOSE
        params["max_file_lines"] = getattr(args, "max_file_lines", None) or _ADOC_DEFAULT_MAX_FILE_LINES

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

    if args.command == "workiq-doctor":
        return _cmd_workiq_doctor(args)

    if args.command == "emit-prompt":
        return _cmd_emit_prompt(args)

    if args.command == "resume":
        # Phase 5 (Resume): セッション管理 CLI ディスパッチャ
        try:
            from .resume_cli import dispatch as _resume_dispatch
        except ImportError:
            from resume_cli import dispatch as _resume_dispatch  # type: ignore[no-redef]
        return _resume_dispatch(args)

    # "run" サブコマンド、または引数なし → インタラクティブモード
    return _cmd_run_interactive(args)


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

    # 同時有効化警告: 敵対的レビュー（--auto-contents-review）と
    # Code Review Agent（--auto-coding-agent-review）が両方有効な場合、
    # 同一成果物に対してレビューセッションが重複しトークン消費・タスク回数が増える可能性がある。
    if getattr(args, "auto_contents_review", False):
        print(
            f"{_ts()} ⚠️  WARNING: --auto-contents-review（敵対的レビュー）と"
            " --auto-coding-agent-review（Code Review Agent）が同時に有効です。\n"
            "   同一成果物に対してレビューセッションが重複し、"
            "トークン消費・タスク回数が増える可能性があります。\n"
            "   通常はどちらか一方を選択することを推奨します。\n"
            "   （強制終了ではありません。このまま続行する場合は無視してください。）",
            file=sys.stderr,
        )

    return True


# -----------------------------------------------------------------------
# Phase 4 (Resume): Wizard Resume プロンプト用ヘルパー
# -----------------------------------------------------------------------

def _resume_selected_run(con: Any, state: Any) -> int:
    """選択された RunState を Resume 実行する。

    Phase 4 (Resume): Wizard で「再開」を選ばれた場合に呼ばれる。
    詳細を panel 表示 → 確認 → SDK バージョン警告 → 環境変数チェック → resume 実行。

    Args:
        con: Console インスタンス。
        state: RunState インスタンス。

    Returns:
        終了コード。0=成功 / 1=失敗（環境変数不足、resume 失敗、ユーザーキャンセル等）。
    """
    try:
        from .config import SDKConfig
        from .orchestrator import run_workflow
        from .run_state import (
            get_current_sdk_version,
            to_local_time_str,
        )
        from .template_engine import _WORKFLOW_DISPLAY_NAMES
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]
        from orchestrator import run_workflow  # type: ignore[no-redef]
        from run_state import (  # type: ignore[no-redef]
            get_current_sdk_version,
            to_local_time_str,
        )
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]

    s = con.s
    wf_disp = _WORKFLOW_DISPLAY_NAMES.get(state.workflow_id, state.workflow_id)
    progress = f"{state.completed_count}/{state.total_count or len(state.step_states)}"
    summary_lines = [
        f"セッション名 : {s.CYAN}{state.session_name or '(無名)'}{s.RESET}",
        f"Run ID       : {state.run_id}",
        f"ワークフロー : {wf_disp} ({state.workflow_id})",
        f"進捗         : {progress} ステップ完了",
        f"作成日時     : {to_local_time_str(state.created_at)}",
        f"最終更新     : {to_local_time_str(state.last_updated_at)}",
        f"ステータス   : {state.status}",
        f"中断理由     : {state.pause_reason or '(不明)'}",
        f"モデル       : {state.config_snapshot.get('model', '(snapshot に無し)')}",
    ]
    con.panel("再開するセッションの詳細", summary_lines)

    # SDK バージョン警告
    current_sdk = get_current_sdk_version()
    saved_sdk = state.host.copilot_sdk_version or "(不明)"
    if current_sdk != saved_sdk and saved_sdk != "(不明)":
        con.warning(
            f"SDK バージョン差異を検出: 保存時 {saved_sdk} → 現在 {current_sdk}\n"
            "   セッション形式の互換性が保証されない可能性があります。"
        )
        if not con.prompt_yes_no("それでも再開しますか？", default=False):
            con._print(f"  {s.YELLOW}キャンセルしました。{s.RESET}", ts=False)
            return 0

    if not con.prompt_yes_no("このセッションを再開しますか？", default=True):
        con._print(f"  {s.YELLOW}キャンセルしました。{s.RESET}", ts=False)
        return 0

    # 環境変数の必須チェック（PR/Issue 作成が有効だった場合）
    snap = state.config_snapshot or {}
    if snap.get("create_pr") or snap.get("create_issues"):
        if not os.environ.get("REPO"):
            con.error("REPO 環境変数が設定されていません。Resume できません。")
            return 1
        if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
            con.error("GH_TOKEN（または GITHUB_TOKEN）環境変数が設定されていません。Resume できません。")
            return 1

    # SDKConfig を環境から構築（_restore_config_from_state が snapshot を上書きする）
    cfg = SDKConfig.from_env()

    # ── 実行 ──────────────────────────────────────────────
    con._print("", ts=False)
    con._print(f"  {s.CYAN}↻ Resume mode: Run ID {state.run_id} を再開します...{s.RESET}", ts=False)
    try:
        result = asyncio.run(
            run_workflow(
                workflow_id=state.workflow_id,
                params=None,  # snapshot から復元される
                config=cfg,
                resume_state=state,
            )
        )
    except KeyboardInterrupt:
        con._print(
            f"\n  {s.YELLOW}中断されました（再度 hve を起動すると続きから再開できます）。{s.RESET}",
            ts=False,
        )
        return 1

    # ── 結果表示 ──────────────────────────────────────────
    if result.get("error"):
        con.error(str(result["error"]))
        return 1
    if result.get("code_review_error"):
        con.error(f"Code Review Agent エラー: {result['code_review_error']}")
        return 1
    if result.get("paused"):
        # Phase 6 (Resume): Ctrl+R による graceful pause
        con._print(
            f"\n  {s.YELLOW}⏸ セッションを一時停止しました。{s.RESET}\n"
            f"  Run ID: {result.get('run_id', '(不明)')}\n"
            f"  続きから再開するには `python -m hve` 起動時の Resume プロンプトを利用してください。\n",
            ts=False,
        )
        return 0
    if result.get("failed"):
        return 1
    con._print(f"\n  {s.GREEN}✓{s.RESET} Resume 完了\n")
    return 0


def _delete_run_interactive(con: Any, state: Any) -> bool:
    """選択された RunState を対話的に削除する（セッション管理メニュー用ヘルパー）。

    実体は `resume_cli._safe_remove_run_dir` / `_hard_delete_sdk_sessions` を再利用する。
    SDK セッション ID が含まれる場合のみ「--hard 相当」削除の有無を確認する。

    Returns:
        True: 削除成功 / False: キャンセルまたは失敗
    """
    try:
        from .resume_cli import _hard_delete_sdk_sessions, _safe_remove_run_dir
        from .run_state import DEFAULT_RUNS_DIR, DEFAULT_SESSION_ID_PREFIX
        from .template_engine import _WORKFLOW_DISPLAY_NAMES
    except ImportError:
        from resume_cli import _hard_delete_sdk_sessions, _safe_remove_run_dir  # type: ignore[no-redef]
        from run_state import DEFAULT_RUNS_DIR, DEFAULT_SESSION_ID_PREFIX  # type: ignore[no-redef]
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]

    s = con.s
    wf_disp = _WORKFLOW_DISPLAY_NAMES.get(state.workflow_id, state.workflow_id)
    con.panel("削除対象", [
        f"セッション名 : {state.session_name or '(無名)'}",
        f"Run ID       : {state.run_id}",
        f"ワークフロー : {wf_disp} ({state.workflow_id})",
        f"ステータス   : {state.status}",
    ])

    if not con.prompt_yes_no("本当に削除しますか？", default=False):
        con._print(f"  {s.YELLOW}キャンセルしました。{s.RESET}", ts=False)
        return False

    sdk_count = sum(
        1 for st in state.step_states.values()
        if st.session_id and st.session_id.startswith(DEFAULT_SESSION_ID_PREFIX)
    )
    hard = False
    if sdk_count > 0:
        hard = con.prompt_yes_no(
            f"SDK 側セッション {sdk_count} 件も削除しますか？（--hard 相当）",
            default=False,
        )

    if hard:
        sdk_failed_unexpectedly = False
        try:
            failed = asyncio.run(_hard_delete_sdk_sessions(state))
        except Exception as exc:  # pragma: no cover - asyncio 異常系
            con.warning(f"SDK 側セッション削除中に例外: {exc}")
            failed = []
            sdk_failed_unexpectedly = True
        for line in failed:
            con.warning(f"SDK 削除失敗: {line}")
        # SDK 側削除が完全に失敗した場合、work/runs/ を消すと
        # SDK 側の orphan を追跡できなくなるため、ディスク削除を抓潰す。
        if sdk_failed_unexpectedly:
            if not con.prompt_yes_no(
                "SDK 側削除が失敗しました。work/runs/ をそれでも削除しますか？",
                default=False,
            ):
            
                con._print(
                    f"  {s.YELLOW}work/runs/ の削除を中止しました。{s.RESET}",
                    ts=False,
                )
                return False

    try:
        _safe_remove_run_dir(state, DEFAULT_RUNS_DIR)
    except RuntimeError as exc:
        con.error(str(exc))
        return False
    except OSError as exc:
        con.error(f"ディレクトリ削除に失敗: {exc}")
        return False

    con._print(
        f"  {s.GREEN}✓{s.RESET} 削除しました (run_id={state.run_id})",
        ts=False,
    )
    return True


def _session_management_menu(con: Any) -> int:
    """セッション管理メニュー（実行/削除）。

    `is_resumable()` で絞込まれた Run（paused / running / failed）の一覧を表示し、
    選択されたセッションに対して以下のいずれかを実行する:

    - 実行（再開）: `_resume_selected_run` を呼ぶ。実行後の状態（完了 / 失敗 /
      pause）に関わらず本メニューに戻る。pause された場合は一覧に同じ Run が
      再表示される。
    - 削除: `_delete_run_interactive` を呼ぶ。SDK セッション ID が含まれていれば
      `--hard 相当` の追加削除を確認する。
    - メニューを抜ける: トップメニューの「メニューを抜ける」で return 0。

    一覧が空になった、もしくは「メニューを抜ける」が選ばれた時点で 0 を返す。
    """
    try:
        from .run_state import is_resumable, list_resumable_runs, to_local_time_str
        from .template_engine import _WORKFLOW_DISPLAY_NAMES
    except ImportError:
        from run_state import is_resumable, list_resumable_runs, to_local_time_str  # type: ignore[no-redef]
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]

    s = con.s
    while True:
        all_runs = list_resumable_runs()
        runs = [r for r in all_runs if is_resumable(r)]
        if not runs:
            if all_runs:
                con._print(
                    "  再開可能なセッションはありません（完了済みは表示しません）。",
                    ts=False,
                )
            else:
                con._print("  保存されているセッションはありません。", ts=False)
            return 0

        options: List[str] = []
        for r in runs:
            wf_disp = _WORKFLOW_DISPLAY_NAMES.get(r.workflow_id, r.workflow_id)
            progress = f"{r.completed_count}/{r.total_count or len(r.step_states)}"
            last_local = to_local_time_str(r.last_updated_at)
            options.append(
                f"{r.session_name or '(無名)'}  "
                f"{s.DIM}({wf_disp} / status={r.status} / 進捗 {progress} / "
                f"最終更新 {last_local}){s.RESET}"
            )
        back_idx = len(options)
        options.append("↩️  メニューを抜ける")

        idx = con.menu_select(
            "管理するセッションを選択してください",
            options,
            default_index=back_idx,
        )
        if idx == back_idx or idx < 0 or idx >= len(runs):
            return 0

        state = runs[idx]
        sub_options = [
            "▶ このセッションを実行（再開）",
            "🗑️  削除",
            "↩️  セッション一覧へ戻る",
        ]
        sub_idx = con.menu_select(
            f"'{state.session_name or state.run_id}' に対する操作",
            sub_options,
            default_index=2,
        )
        if sub_idx == 0:
            _resume_selected_run(con, state)
        elif sub_idx == 1:
            _delete_run_interactive(con, state)
        # sub_idx == 2 または想定外 → 一覧へ戻る（ループ継続）


def _show_resume_menu(con: Any, runs: list, *, allow_cancel: bool = False) -> Optional[int]:
    """再開可能 Run の一覧メニューを表示し、ユーザー選択をディスパッチする。"""
    try:
        from .run_state import to_local_time_str
        from .template_engine import _WORKFLOW_DISPLAY_NAMES
    except ImportError:
        from run_state import to_local_time_str  # type: ignore[no-redef]
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]

    s = con.s
    options: List[str] = []
    for r in runs:
        wf_disp = _WORKFLOW_DISPLAY_NAMES.get(r.workflow_id, r.workflow_id)
        progress = f"{r.completed_count}/{r.total_count or len(r.step_states)}"
        last_local = to_local_time_str(r.last_updated_at)
        options.append(
            f"{r.session_name or '(無名)'}  "
            f"{s.DIM}({wf_disp} / 進捗 {progress} / 最終更新 {last_local}){s.RESET}"
        )

    if allow_cancel:
        cancel_idx = len(options)
        options.append("↩️  キャンセル（元の画面へ戻る）")
        idx = con.menu_select(
            "再開可能なセッションがあります。選択してください",
            options,
            default_index=0,
        )
        if 0 <= idx < len(runs):
            return _resume_selected_run(con, runs[idx])
        if idx == cancel_idx:
            return None
        return None

    new_run_idx = len(options)
    mgmt_menu_idx = new_run_idx + 1
    options.append("➕ 新規実行を開始する")
    options.append("⚙️  セッション管理（実行/削除）")

    idx = con.menu_select(
        "再開可能なセッションがあります。選択してください",
        options,
        default_index=0,
    )

    if 0 <= idx < len(runs):
        return _resume_selected_run(con, runs[idx])
    if idx == new_run_idx:
        return None
    if idx == mgmt_menu_idx:
        return _session_management_menu(con)
    return None


def _show_resume_menu_on_demand(con: Any) -> Optional[int]:
    """Ctrl+R 押下時に呼ばれる、wizard 中盤以降からの再開メニュー呼び出し。"""
    try:
        from .run_state import list_resumable_runs
    except ImportError:
        from run_state import list_resumable_runs  # type: ignore[no-redef]

    try:
        runs = list_resumable_runs()
    except Exception as exc:  # pragma: no cover - I/O 異常系
        con.warning(f"再開可能セッションの一覧取得に失敗しました: {exc}")
        return None
    runs = [r for r in runs if r.status in {"paused", "running", "failed"}]
    if not runs:
        con._print("\n  再開可能なセッションはありません。\n", ts=False)
        return None
    return _show_resume_menu(con, runs, allow_cancel=True)


def _maybe_show_resume_prompt(con: Any) -> Optional[int]:
    """Wizard 起動時に Resume プロンプトを表示する。

    Phase 4 (Resume): `work/runs/` に再開可能な Run があれば、最初に
    「再開する／新規実行／管理画面」を選択させる。

    Returns:
        - None : 「新規実行」が選ばれた場合（呼び出し元は通常フローへフォールスルー）
        - int  : 「再開」または「管理画面」が選ばれた場合（呼び出し元は即座に return する）
    """
    try:
        from .run_state import is_resumable, list_resumable_runs
    except ImportError:
        from run_state import is_resumable, list_resumable_runs  # type: ignore[no-redef]

    try:
        all_runs = list_resumable_runs()
    except Exception as exc:  # pragma: no cover - I/O 異常系
        con.warning(f"再開可能セッションの一覧取得に失敗しました: {exc}")
        return None

    resumable = [r for r in all_runs if is_resumable(r)]
    if not resumable:
        return None

    return _show_resume_menu(con, resumable, allow_cancel=False)


def _cmd_run_interactive(args: "Optional[argparse.Namespace]" = None) -> int:
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
        from .keybind import KEY_CTRL_R, KeybindMonitor
        from .workiq import (
            get_workiq_prompt_template,
            is_workiq_available,
            workiq_login,
        )
    except ImportError:
        from console import Console  # type: ignore[no-redef]
        from config import SDKConfig  # type: ignore[no-redef]
        from workflow_registry import list_workflows, get_workflow  # type: ignore[no-redef]
        from template_engine import _WORKFLOW_DISPLAY_NAMES  # type: ignore[no-redef]
        from orchestrator import run_workflow  # type: ignore[no-redef]
        from keybind import KEY_CTRL_R, KeybindMonitor  # type: ignore[no-redef]
        from workiq import (  # type: ignore[no-redef]
            get_workiq_prompt_template,
            is_workiq_available,
            workiq_login,
        )

    con = Console(verbose=True, quiet=False, verbosity=3)  # wizard UI の表示は常に verbose（ワークフロー実行の verbosity はユーザー選択値で別途設定）

    # ── ウェルカムバナー ──────────────────────────────────
    if getattr(args, "banner", None) is not False:
        con.banner(
            "HVE CLI Orchestrator (GitHub Copilot SDK)",
            "ワークフローをインタラクティブに実行します",
        )

    # ── Phase 4 (Resume): 再開プロンプト ─────────────────
    # work/runs/ に再開可能な Run があれば、最初に「再開／新規／管理」を選択させる。
    # 「新規実行」が選ばれた場合のみ None が返り、通常フローへフォールスルーする。
    _resume_result = _maybe_show_resume_prompt(con)
    if _resume_result is not None:
        return _resume_result

    # ── Phase 8 (Resume): ウィザード中 Ctrl+R でオンデマンド再開メニュー ──
    resume_invoked: dict = {"rc": None}
    _resume_requested = threading.Event()
    _monitor_probe = KeybindMonitor()
    monitor = _monitor_probe
    wizard_loop: Optional[asyncio.AbstractEventLoop] = None
    wizard_loop_thread: Optional[threading.Thread] = None
    _orig_console_methods: dict[str, Any] = {}
    _keybind_cleaned_up = False

    async def _on_ctrl_r_in_wizard() -> None:
        _resume_requested.set()

    def _cleanup_wizard_keybind() -> None:
        nonlocal _keybind_cleaned_up
        if _keybind_cleaned_up:
            return
        _keybind_cleaned_up = True
        monitor.stop()
        for name, fn in _orig_console_methods.items():
            setattr(con, name, fn)
        if wizard_loop is not None:
            try:
                wizard_loop.call_soon_threadsafe(wizard_loop.stop)
            except RuntimeError:
                # loop が既に停止/close 済みの場合があるため cleanup では握り潰す
                pass
        if wizard_loop_thread is not None and wizard_loop_thread.is_alive():
            wizard_loop_thread.join(timeout=1.0)
        if wizard_loop is not None:
            try:
                wizard_loop.close()
            except RuntimeError:
                # 既に close 済み、または別スレッド終了直後の競合時は no-op
                pass

    def _short_circuit_input_result(method_name: str, kwargs: dict[str, Any]) -> Any:
        if method_name == "menu_select":
            default_index = kwargs.get("default_index")
            return 0 if default_index is None else default_index
        if method_name == "prompt_yes_no":
            return kwargs.get("default", False)
        if method_name == "prompt_multi_select":
            return []
        return kwargs.get("default", "")

    def _maybe_handle_resume_request() -> None:
        if not _resume_requested.is_set():
            return
        _resume_requested.clear()
        rc = _show_resume_menu_on_demand(con)
        if rc is not None:
            resume_invoked["rc"] = int(rc)

    def _get_default_if_resumed(method_name: str, kwargs: dict[str, Any]) -> Optional[Any]:
        if resume_invoked["rc"] is None:
            return None
        return _short_circuit_input_result(method_name, kwargs)

    def _wrap_console_input_method(name: str) -> None:
        fn = getattr(con, name, None)
        if not callable(fn):
            return
        _orig_console_methods[name] = fn
        method_name = name

        def _wrapped(*args, **kwargs):
            _short = _get_default_if_resumed(method_name, kwargs)
            if _short is not None:
                return _short
            _maybe_handle_resume_request()
            _short = _get_default_if_resumed(method_name, kwargs)
            if _short is not None:
                return _short
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                con.warning(f"ウィザード入力中にエラーが発生しました ({method_name}): {exc}")
                _cleanup_wizard_keybind()
                raise
            _maybe_handle_resume_request()
            _short = _get_default_if_resumed(method_name, kwargs)
            if _short is not None:
                return _short
            return result

        setattr(con, name, _wrapped)

    if _monitor_probe.enabled:
        wizard_loop = asyncio.new_event_loop()
        wizard_loop_thread = threading.Thread(
            target=wizard_loop.run_forever,
            name="hve-wizard-keybind-loop",
            daemon=True,
        )
        wizard_loop_thread.start()
        monitor = KeybindMonitor(wizard_loop)
        monitor.register(KEY_CTRL_R, _on_ctrl_r_in_wizard)
        monitor.start()
        for _method_name in ("menu_select", "prompt_yes_no", "prompt_input", "prompt_multi_select", "input"):
            _wrap_console_input_method(_method_name)
        con._print(
            "  💡 ウィザード中も Ctrl+R で保存済みセッションから再開できます",
            ts=False,
        )

    # ── ワークフロー選択 ──────────────────────────────────
    workflows = list_workflows()
    wf_options = [
        f"{_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}  {con.s.DIM}({wf.id} — {len([s for s in wf.steps if not s.is_container])} 実行ステップ){con.s.RESET}"
        for wf in workflows
    ]
    wf_idx = con.menu_select("ワークフローを選択してください", wf_options)
    selected_wf = workflows[wf_idx]
    wf = get_workflow(selected_wf.id)
    is_akm = (wf.id == "akm")
    is_aqod = (wf.id == "aqod")
    is_ard = (wf.id == "ard")
    is_single_step_workflow = is_akm or is_aqod

    # ── ステップ選択 ──────────────────────────────────────
    # AKM/AQOD はステップが 1 つのみのため、自動で全選択
    # ARD はワークフロー固有入力で Step 1/2/3 を選択する
    if is_single_step_workflow:
        selected_step_ids = []  # 空 = 全ステップ
    elif is_ard:
        selected_step_ids = []  # ARD: _collect_ard_wizard_params で後から設定
    else:
        non_container_steps, step_options = _step_options_with_groups(wf)
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
    model_idx = con.menu_select("使用するモデルを選択", model_options, default_index=0)
    model, model_display = _resolve_model(model_options[model_idx])
    review_model = None
    review_model_display = None
    qa_model = None
    qa_model_display = None

    # ── 実行モード選択 ────────────────────────────────────
    _exec_mode_options = [
        "クイック全自動  — デフォルト値で即実行（確認あり）",
        "カスタム全自動  — 全設定を手動入力後に自動実行",
        "手動           — 従来どおり（実行中も対話あり）",
    ]
    exec_mode_idx = con.menu_select("実行モードを選択", _exec_mode_options, default_index=2)
    is_quick_auto = (exec_mode_idx == 0)
    is_custom_auto = (exec_mode_idx == 1)
    is_manual = (exec_mode_idx == 2)
    is_any_auto = is_quick_auto or is_custom_auto
    workiq_additional_prompt = ""
    ard_workiq_enabled = False

    # ── オプション設定 ────────────────────────────────────
    if is_quick_auto:
        # クイック全自動: ステップ5〜7aをデフォルト値で自動設定
        branch = "main"
        max_parallel = 1 if is_single_step_workflow else 15
        verbosity_key = "normal"
        verbosity_value = 2  # normal（クイック全自動は長時間実行が前提のため、compact より情報量の多い normal を採用）
        timeout_val = 86400.0  # 24時間
        auto_qa = False
        qa_answer_mode = "all"
        force_interactive = False
        auto_review = False
        create_issues = False
        create_pr = False
        auto_coding_agent_review = False
        auto_coding_agent_review_auto_approval = False
        review_timeout = 7200.0
        repo_input = os.environ.get("REPO", "")
        dry_run = False
        workiq_enabled = False
        workiq_qa_enabled = False
        workiq_akm_review_enabled = False
        workiq_draft_mode = False
        workiq_per_question_timeout = 1200.0
        issue_title = ""
        issue_additional_comment = ""
        # ワークフロー固有パラメータ
        params_extra: dict = {}
        if is_akm:
            params_extra.update(_prompt_akm_params(con, is_quick_auto=True))
        elif is_aqod:
            params_extra["target_scope"] = _AQOD_DEFAULT_TARGET_SCOPE
            params_extra["depth"] = _AQOD_DEFAULT_DEPTH
            params_extra["focus_areas"] = ""
        elif is_ard:
            _ard_wf_params, _ard_steps = _collect_ard_wizard_params(con, is_quick_auto=True)
            params_extra.update(_ard_wf_params)
            selected_step_ids = _ard_steps
            ard_workiq_enabled = con.prompt_yes_no(
                "ARD で Work IQ への接続を有効にする？",
                default=False,
            )
            params_extra["ard_workiq_enabled"] = ard_workiq_enabled
            workiq_enabled = ard_workiq_enabled
            workiq_qa_enabled = ard_workiq_enabled
        elif wf.params:
            params_extra.update(_collect_generic_workflow_params(con, wf, is_quick_auto=True))
        # Agentic Retrieval 設定（AAD-WEB / ASDW-WEB）
        _agentic_answers: dict = {}
        if wf.id in ("aad-web", "asdw-web"):
            _agentic_answers = _collect_agentic_retrieval_wizard_answers(con, wf.id, is_quick_auto=True)
        additional_prompt = None
        # クイック全自動: 自己改善はデフォルト OFF
        auto_self_improve = False
        self_improve_max_iterations = 3
        self_improve_target_scope = ""
        self_improve_goal = ""
        _disc_goal = None
        _disc_criteria = None
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
        _raw_idx = con.menu_select(
            "コンソール出力レベルを選択",
            _verbosity_options,
            allow_empty=True,
            default_index=_VERBOSITY_DEFAULT,
        )
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
            qa_answer_mode = None
            force_interactive = False
            auto_review = False
            if is_akm:
                auto_qa = con.prompt_yes_no(
                    "AKM 実行前に QA（事前確認・質問票生成・回答）を実施する？",
                    default=False,
                )
                if auto_qa:
                    qa_answer_mode = "all"
            elif is_aqod:
                # AQOD は事前 QA スキップ・事後 QA (post-QA) 廃止のため、本体タスクのみ。
                auto_qa = False
            else:
                auto_qa = False
        else:
            auto_qa = con.prompt_yes_no(
                "QA 自動投入を有効にする？（質問票はステップ実行の前に作成されます）",
                default=False,
            )
            if auto_qa:
                # QA 自動投入 ON 時は全問デフォルト値を自動採用する一択。
                # Issue Template Workflow (auto-qa-default-answer.yml) と同じ動作。
                # prompt_answer_mode() / force_interactive プロンプトは不要。
                qa_answer_mode = "all"
                force_interactive = False
                use_different_qa_model = con.prompt_yes_no(
                    "QA にメインモデルとは別のモデルを使う？（n の場合、未指定なら環境変数 QA_MODEL を使用）",
                    default=False,
                )
                if use_different_qa_model:
                    _sub_model_options = model_options
                    qa_model_idx = con.menu_select("QA 用モデルを選択", _sub_model_options)
                    qa_model, qa_model_display = _resolve_model(_sub_model_options[qa_model_idx])
                    if qa_model == model:
                        qa_model = None
                        qa_model_display = None
            else:
                qa_answer_mode = None
                force_interactive = False
            auto_review = con.prompt_yes_no("Review 自動投入を有効にする？", default=False)
            if auto_review:
                use_different_review_model = con.prompt_yes_no(
                    "Review にメインモデルとは別のモデルを使う？（n の場合、未指定なら環境変数 REVIEW_MODEL を使用）",
                    default=False,
                )
                if use_different_review_model:
                    _sub_model_options = model_options
                    review_model_idx = con.menu_select("レビュー用モデルを選択", _sub_model_options)
                    review_model, review_model_display = _resolve_model(_sub_model_options[review_model_idx])
                    if review_model == model:
                        review_model = None
                        review_model_display = None

        # ── Work IQ 連携 ──────────────────────────────────────
        workiq_enabled = False
        workiq_qa_enabled = False
        workiq_akm_review_enabled = False
        workiq_draft_mode = False
        _show_workiq_option = auto_qa or is_akm or is_ard
        workiq_per_question_timeout = 1200.0

        if _show_workiq_option and is_workiq_available():
            if is_ard:
                ard_workiq_enabled = con.prompt_yes_no(
                    "ARD で Work IQ への接続を有効にする？",
                    default=False,
                )
                workiq_qa_enabled = ard_workiq_enabled
            elif is_akm:
                if auto_qa:
                    workiq_qa_enabled = con.prompt_yes_no(
                        "QA フェーズで Work IQ 経由の情報確認を有効にする？",
                        default=False,
                    )
                workiq_akm_review_enabled = con.prompt_yes_no(
                    "AKM 完了後に Work IQ で knowledge/ Dxx ドキュメントの妥当性を検証する？",
                    default=False,
                )
            else:
                workiq_qa_enabled = con.prompt_yes_no(
                    "QA フェーズで Work IQ 経由の情報確認を有効にする？",
                    default=False,
                )
            workiq_enabled = workiq_qa_enabled or workiq_akm_review_enabled
            if workiq_enabled:
                con.spinner_start("Work IQ へのログイン中...")
                login_ok = workiq_login(con)
                con.spinner_stop()
                if not login_ok:
                    con.warning(
                        "Work IQ へのログインに失敗しました。Work IQ 連携を無効にします。"
                    )
                    workiq_enabled = False
                else:
                    con.status("✅ Work IQ へのログインが完了しました")
                    if is_akm and not workiq_qa_enabled:
                        workiq_draft_mode = False
                    elif auto_qa and workiq_qa_enabled:
                        workiq_draft_mode = con.prompt_yes_no(
                            "Work IQ で回答ドラフトを自動生成する？",
                            default=False,
                        )
                    workiq_additional_prompt = con.prompt_input(
                        "Work IQ (Microsoft 365 Copilot) の末尾に追加するプロンプト（省略可）",
                        default="",
                    )
                    _wiq_pq_timeout_str = con.prompt_input(
                        "Work IQ タイムアウト（秒。デフォルト: 1200 = 20 分）",
                        default="1200",
                    )
                    try:
                        workiq_per_question_timeout = float(_wiq_pq_timeout_str or "1200")
                    except ValueError:
                        con.warning("無効な値のため、デフォルトの 1200 秒（20 分）を使用します。")
                        workiq_per_question_timeout = 1200.0
                    if workiq_per_question_timeout <= 0:
                        con.warning("0 以下の値は無効なため、デフォルトの 1200 秒（20 分）を使用します。")
                        workiq_per_question_timeout = 1200.0

        create_issues = con.prompt_yes_no("GitHub Issue を作成する？", default=False)
        create_pr = con.prompt_yes_no("GitHub PR を作成する？", default=False) if not create_issues else True
        issue_title = ""
        issue_additional_comment = ""
        if create_issues:
            issue_title = con.prompt_input(
                _PARAM_PROMPT_LABELS["issue_title"],
                default="",
            )
            issue_additional_comment = con.prompt_input(
                _PARAM_PROMPT_LABELS["additional_comment"],
                default="",
            )

        # ── リポジトリ入力（Issue/PR 作成時のみ） ─────────────
        repo_input = ""
        if create_issues or create_pr:
            repo_default = os.environ.get("REPO", "")
            repo_input = con.prompt_input("リポジトリ (owner/repo)", default=repo_default, required=True)

        akm_enable_auto_merge = False
        if is_akm and (create_issues or create_pr):
            akm_enable_auto_merge = con.prompt_yes_no(
                "PR の自動 Approve & Auto-merge を有効にする？",
                default=False,
            )

        # ── Code Review Agent ─────────────────────────────
        auto_coding_agent_review = con.prompt_yes_no(
            "GitHub Copilot Code Review Agent（ローカル実行）を有効にする？", default=False
        )
        auto_coding_agent_review_auto_approval = False
        review_timeout = 7200.0
        if auto_coding_agent_review:
            if is_any_auto:
                auto_coding_agent_review_auto_approval = True
            else:
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

        dry_run = con.prompt_yes_no("実行計画のプレビュー（実際の SDK 呼び出しをせず、DAG の実行計画のみ表示）？", default=False)

        # ── ワークフロー固有パラメータ ────────────────────────
        params_extra: dict = {}
        if is_akm:
            params_extra.update(
                _prompt_akm_params(
                    con,
                    is_quick_auto=False,
                    will_create_pr=(create_issues or create_pr),
                )
            )
            params_extra["enable_auto_merge"] = akm_enable_auto_merge
        elif is_aqod:
            params_extra["target_scope"] = con.prompt_input(
                _PARAM_PROMPT_LABELS["target_scope"], default=_AQOD_DEFAULT_TARGET_SCOPE
            )
            params_extra["depth"] = _prompt_valid_aqod_depth(con)
            params_extra["focus_areas"] = con.prompt_input(_PARAM_PROMPT_LABELS["focus_areas"], default="")
        elif is_ard:
            _ard_wf_params, _ard_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
            params_extra.update(_ard_wf_params)
            params_extra["ard_workiq_enabled"] = ard_workiq_enabled
            selected_step_ids = _ard_steps
        else:
            params_extra.update(_collect_generic_workflow_params(con, wf, is_quick_auto=False))
        # Agentic Retrieval 設定（AAD-WEB / ASDW-WEB）
        _agentic_answers: dict = {}
        if wf.id in ("aad-web", "asdw-web"):
            _agentic_answers = _collect_agentic_retrieval_wizard_answers(con, wf.id, is_quick_auto=False)

        if issue_title:
            params_extra["issue_title"] = issue_title
        if issue_additional_comment:
            params_extra["additional_comment"] = issue_additional_comment

        # ── 追加プロンプト ────────────────────────────────────
        additional_prompt = con.prompt_input("全てのステップでの Prompt の末尾に追加するプロンプト（省略可）")

        # ── 自己改善ループ ────────────────────────────────────
        auto_self_improve = con.prompt_yes_no("自己改善ループを有効にする？", default=False)
        self_improve_max_iterations = 3
        self_improve_target_scope = ""
        self_improve_goal = ""
        _disc_goal = None
        _disc_criteria = None
        if auto_self_improve:
            _si_iter_str = con.prompt_input("自己改善 最大繰り返し回数（例: 3 → 最大3回スキャン→改善→検証を繰り返す）", default="3")
            try:
                self_improve_max_iterations = int(_si_iter_str or "3")
            except ValueError:
                con.warning("無効な値のため、デフォルトの 3 を使用します。")
                self_improve_max_iterations = 3
            try:
                from hve.self_improve import _is_new_resolver_enabled as _si_flag
                _si_new_resolver = _si_flag()
            except Exception:
                _si_new_resolver = False
            if _si_new_resolver:
                _si_scope_prompt = (
                    "自己改善 対象パス（HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER=1 有効時の新仕様）\n"
                    "  - 未入力 : そのステップの成果物（work/ 配下は自動除外）\n"
                    "  - '*'    : data, docs, docs-generated, knowledge, src を一括対象（実在するもののみ）\n"
                    "  - 任意   : カンマ/空白区切りで複数パス可（例: 'src/ hve/'）\n"
                    "             ※ '-' で始まるトークンは禁止"
                )
            else:
                _si_scope_prompt = (
                    "自己改善 対象パス（例: src/  hve/  空=リポジトリ全体）\n"
                    "  ※ 新仕様（複数パス/ワイルドカード/work/ 除外）は HVE_SELF_IMPROVE_NEW_SCOPE_RESOLVER=1 で有効"
                )
            self_improve_target_scope = con.prompt_input(_si_scope_prompt, default="")
            self_improve_goal = con.prompt_input(
                "自己改善 ゴール説明（省略可 → ワークフロー種別から自動設定）\n"
                "  例: 'テスト失敗を 0 件にし lint エラーを解消する'\n"
                "  例: 'knowledge/ D01〜D21 の整合性を確保する'",
                default="",
            )
            if not self_improve_goal:
                from hve.self_improve import discover_task_goal_with_llm, discover_task_goal_from_docs
                _env_cfg = SDKConfig.from_env()
                con.spinner_start("自動ゴール探索中（LLM）...")
                try:
                    _disc_result = asyncio.run(discover_task_goal_with_llm(
                        workflow_id=wf.id,
                        model=model,
                        cli_path=_env_cfg.cli_path or "",
                        github_token=_env_cfg.resolve_token(),
                        cli_url=_env_cfg.cli_url or "",
                        target_scope=self_improve_target_scope,
                    ))
                except Exception as _disc_err:
                    con.warning(f"LLM によるゴール探索に失敗しました（{_disc_err}）。静的解析にフォールバックします。")
                    _disc_result = discover_task_goal_from_docs(
                        workflow_id=wf.id,
                        target_scope=self_improve_target_scope,
                    )
                finally:
                    con.spinner_stop()
                _disc_goal = _disc_result["task_goal"]
                _disc_criteria = _disc_goal.get("success_criteria") or None


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
        f"ブランチ     : {branch}",
        f"並列数       : {max_parallel}",
        f"出力レベル   : {verbosity_key}",
        f"タイムアウト  : {timeout_val:.0f} 秒",
        f"QA 自動      : {'ON' if auto_qa else 'OFF'}",
    ]
    if auto_qa:
        summary_lines.append(f"QA モデル    : {qa_model_display or '(メインと同じ)'}")
        summary_lines.append(f"QA 回答モード : 全問デフォルト自動採用")
        # force_interactive は auto_qa=True 時は常に False のため表示不要
    if workiq_enabled:
        if is_akm:
            summary_lines.append(f"Work IQ QA   : {'ON' if workiq_qa_enabled else 'OFF'}")
            summary_lines.append(f"Work IQ 検証 : {'ON' if workiq_akm_review_enabled else 'OFF'}")
        else:
            summary_lines.append(f"Work IQ     : {s.GREEN}ON{s.RESET}")
            summary_lines.append(f"Work IQ Draft: {'ON' if workiq_draft_mode else 'OFF'}")
        if workiq_additional_prompt:
            summary_lines.append(f"Work IQ Prompt: {workiq_additional_prompt[:50]}{'...' if len(workiq_additional_prompt) > 50 else ''}")
        summary_lines.append(f"Work IQ タイムアウト: {workiq_per_question_timeout:.0f} 秒")
    summary_lines += [
        f"Review 自動  : {'ON' if auto_review else 'OFF'}",
        f"Issue 作成   : {'ON' if create_issues else 'OFF'}",
        f"PR  作成     : {'ON' if create_pr else 'OFF'}",
        f"Code Review  : {'ON' if auto_coding_agent_review else 'OFF'}",
    ]
    if auto_review:
        summary_lines.append(f"レビューモデル: {review_model_display or '(メインと同じ)'}")
    if auto_coding_agent_review:
        summary_lines += [
            f"自動承認     : {'ON' if auto_coding_agent_review_auto_approval else 'OFF'}",
            f"タイムアウト : {review_timeout}s",
        ]
    summary_lines += [
        f"リポジトリ   : {repo_input or '(なし)'}",
        f"実行計画のプレビュー : {'ON' if dry_run else 'OFF'}",
        f"自己改善     : {'ON' if auto_self_improve else 'OFF'}",
    ]
    if auto_self_improve:
        summary_lines.append(f"自己改善 繰り返し上限: {self_improve_max_iterations} 回")
        try:
            from hve.self_improve import _is_new_resolver_enabled
            _new_resolver_on = _is_new_resolver_enabled()
        except Exception:
            _new_resolver_on = False
        if _new_resolver_on:
            try:
                from hve.self_improve import _resolve_target_scope_paths
                from hve.config import SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS
                _wf_default = SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS.get(wf.id, "")
                _resolved = _resolve_target_scope_paths(
                    self_improve_target_scope,
                    step_output_paths=None,
                    workflow_default=_wf_default,
                    repo_root=".",
                )
                _disp_resolved = ", ".join(_resolved) if _resolved else "(解決後に空 → スキャンスキップ)"
            except ValueError as _err:
                _disp_resolved = f"(エラー: {_err})"
            except Exception:
                _disp_resolved = self_improve_target_scope or "(空) = ステップ成果物"
            if self_improve_target_scope == "":
                summary_lines.append(f"自己改善 対象パス   : (空) → {_disp_resolved}")
            elif self_improve_target_scope == "*":
                summary_lines.append(f"自己改善 対象パス   : * → {_disp_resolved}")
            else:
                summary_lines.append(f"自己改善 対象パス   : {self_improve_target_scope} → {_disp_resolved}")
        else:
            # 旧仕様: 単一パス / 未入力=リポジトリ全体
            summary_lines.append(f"自己改善 対象パス   : {self_improve_target_scope or '(空) = リポジトリ全体'}")
        if self_improve_goal:
            _goal_disp = self_improve_goal[:60] + ("..." if len(self_improve_goal) > 60 else "")
            summary_lines.append(f"自己改善 ゴール     : {_goal_disp}")
        elif _disc_goal:
            _disp = (_disc_goal.get("goal_description", "") or "")[:60] + ("..." if len(_disc_goal.get("goal_description", "")) > 60 else "")
            summary_lines.append(f"自己改善 ゴール     : (自動検索: {_disp})")
        else:
            summary_lines.append(f"自己改善 ゴール     : (自動: ワークフロー '{wf.id}' の標準ゴール)")
    for k, v in params_extra.items():
        if k == "app_id" and params_extra.get("app_ids"):
            continue
        summary_lines.append(f"{_format_param_label(k)}: {_format_param_value(v)}")
    if additional_prompt:
        summary_lines.append(f"追加プロンプト（全Step）: {additional_prompt[:50]}{'...' if len(additional_prompt) > 50 else ''}")

    # Phase 4 (Resume): セッション名入力（Resume 一覧に表示する識別名）。
    # クイック全自動では既定（後で run_workflow が default_session_name で自動生成）。
    # カスタム全自動 / 手動では Enter で既定使用、入力で上書き。
    session_name_input: str = ""
    if not is_quick_auto:
        try:
            from .run_state import default_session_name
        except ImportError:
            from run_state import default_session_name  # type: ignore[no-redef]
        _wf_disp = _WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)
        _suggested = default_session_name(
            workflow_id=wf.id,
            params=params_extra,
            workflow_display_name=_wf_disp,
        )
        session_name_input = con.prompt_input(
            "セッション名（Resume 一覧の表示名）",
            default=_suggested,
        )
    if session_name_input:
        summary_lines.append(f"セッション名 : {session_name_input}")

    con.panel("実行設定", summary_lines)

    # ── 実行確認 ──────────────────────────────────────────
    if not con.prompt_yes_no("この設定で実行しますか？", default=True):
        con._print(f"\n  {s.YELLOW}キャンセルしました。{s.RESET}", ts=False)
        _cleanup_wizard_keybind()
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
    cfg.workiq_enabled = workiq_enabled
    cfg.workiq_qa_enabled = workiq_qa_enabled
    cfg.workiq_akm_review_enabled = workiq_akm_review_enabled
    cfg.workiq_draft_mode = workiq_draft_mode
    cfg.workiq_draft_output_dir = "qa"
    cfg.workiq_per_question_timeout = workiq_per_question_timeout
    cfg.force_interactive = force_interactive
    cfg.auto_contents_review = auto_review
    cfg.qa_answer_mode = qa_answer_mode
    cfg.create_issues = create_issues
    cfg.create_pr = create_pr or create_issues
    if cfg.create_pr and cfg.workiq_enabled:
        workiq_output_dir = (cfg.workiq_draft_output_dir or "").strip().strip("/\\") or "qa"
        if workiq_output_dir in cfg.ignore_paths:
            cfg.ignore_paths = [p for p in cfg.ignore_paths if p != workiq_output_dir]
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
    if workiq_additional_prompt:
        for attr, mode in [
            ("workiq_prompt_qa", "qa"),
            ("workiq_prompt_km", "km"),
            ("workiq_prompt_review", "review"),
        ]:
            base_prompt = getattr(cfg, attr, None) or get_workiq_prompt_template(mode)
            setattr(cfg, attr, base_prompt + "\n\n" + workiq_additional_prompt)
    cfg.additional_prompt = additional_prompt or None
    if repo_input:
        cfg.repo = repo_input
    elif not cfg.repo:
        cfg.repo = os.environ.get("REPO", "")

    # ── 自己改善ループ設定 ─────────────────────────────────
    if auto_self_improve:
        cfg.auto_self_improve = True
        cfg.self_improve_max_iterations = self_improve_max_iterations
        if self_improve_target_scope:
            cfg.self_improve_target_scope = self_improve_target_scope
        if self_improve_goal:
            cfg.self_improve_goal = self_improve_goal
        if _disc_criteria:
            cfg.self_improve_success_criteria = _disc_criteria

    # ── 全自動モードフラグを SDKConfig に反映 ─────────────
    cfg.unattended = is_any_auto
    if is_any_auto:
        cfg.force_interactive = False
        if cfg.auto_qa:
            cfg.qa_answer_mode = "all"  # 全自動モード時は QA 全問デフォルト値を一括採用（非TTY扱い）
        if cfg.auto_coding_agent_review:
            cfg.auto_coding_agent_review_auto_approval = True  # 自動承認を強制

    # ── 手動モード + QA 自動投入: QA 回答フェーズのみ非対話化 ─────
    # auto_qa=True のとき、QA Phase 2b での回答収集をスキップし
    # 全問デフォルト値を自動採用する（auto-qa-default-answer.yml と同等の動作）。
    # unattended=False のままにすることで、他のプロンプト（Review 等）は対話を維持する。
    if not is_any_auto and cfg.auto_qa:
        cfg.qa_auto_defaults = True

    # ── Agentic Retrieval 設定を SDKConfig に反映 ─────────
    if _agentic_answers:
        try:
            from .template_engine import normalize_agentic_retrieval_answers
        except ImportError:
            from template_engine import normalize_agentic_retrieval_answers  # type: ignore[no-redef]
        _normalized = normalize_agentic_retrieval_answers(_agentic_answers)
        # enable_agentic_retrieval: "する"→"yes", "しない"→"no", それ以外→"auto"
        _enable_raw = _normalized.get("enable_agentic_retrieval", "自動判定に従う")
        _enable_map = {"する": "yes", "しない": "no", "自動判定に従う": "auto"}
        cfg.enable_agentic_retrieval = _enable_map.get(_enable_raw, "auto")
        # agentic_data_source_modes: 選択肢テキスト→内部値に変換
        _mode_raw = _normalized.get("agentic_data_source_modes", ["Indexer (Pull)"])
        _mode_map = {"Indexer (Pull)": "indexer", "Push API": "push"}
        cfg.agentic_data_source_modes = [
            _mode_map.get(m, m.lower().replace(" ", "_")) for m in (_mode_raw if isinstance(_mode_raw, list) else [_mode_raw])
        ] or ["indexer"]
        # foundry_mcp_integration: "する"→True, それ以外→False
        _fmi_raw = _normalized.get("foundry_mcp_integration", "する")
        if isinstance(_fmi_raw, bool):
            cfg.foundry_mcp_integration = _fmi_raw
        else:
            cfg.foundry_mcp_integration = (_fmi_raw == "する")
        # agentic_data_sources_hint: str
        cfg.agentic_data_sources_hint = str(_normalized.get("agentic_data_sources_hint", "") or "")
        # agentic_existing_design_diff_only: bool
        cfg.agentic_existing_design_diff_only = bool(_normalized.get("agentic_existing_design_diff_only", False))
        # foundry_sku_fallback_policy: 選択肢テキスト→内部値に変換
        _fskp_raw = _normalized.get("foundry_sku_fallback_policy", "Standard 許容")
        _fskp_map = {
            "Global 必須（Standard 拒否）": "global_required",
            "Standard 許容": "standard_allowed",
        }
        cfg.foundry_sku_fallback_policy = _fskp_map.get(_fskp_raw, "standard_allowed")

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
            _cleanup_wizard_keybind()
            return 1

    if resume_invoked["rc"] is not None:
        _cleanup_wizard_keybind()
        return int(resume_invoked["rc"])

    # ── 実行 ──────────────────────────────────────────────
    _cleanup_wizard_keybind()
    con._print("", ts=False)
    try:
        result = asyncio.run(
            run_workflow(
                workflow_id=wf.id,
                params=params,
                config=cfg,
                session_name=session_name_input or None,
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
    if result.get("paused"):
        # Phase 6 (Resume): Ctrl+R による graceful pause
        con._print(
            f"\n  {s.YELLOW}⏸ セッションを一時停止しました。{s.RESET}\n"
            f"  Run ID: {result.get('run_id', '(不明)')}\n"
            f"  続きから再開するには `python -m hve` 起動時の Resume プロンプトを利用してください。\n",
            ts=False,
        )
        return 0
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
        from .config import SDKConfig, normalize_model
        from .console import Console
    except ImportError:
        from config import SDKConfig, normalize_model  # type: ignore[no-redef]
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
        if model != MODEL_AUTO_VALUE:
            normalized_model = normalize_model(model)
            if normalized_model != model:
                print(
                    f"{_ts()} ⚠️  '{model}' は旧表記です。'{normalized_model}' を使用します。"
                )
                model = normalized_model
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
            _session_kwargs = {"client": client}
            # Auto 選択時は model 引数を省略し、GitHub 側の Auto model selection に委譲する。
            if model != MODEL_AUTO_VALUE:
                _session_kwargs["model"] = model
            async with CopilotSession(**_session_kwargs) as session:
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


def _cmd_workiq_doctor(args: argparse.Namespace) -> int:
    """workiq-doctor サブコマンドのハンドラー。"""
    import dataclasses
    import json as _json_module

    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .workiq import run_workiq_diagnostics
    except ImportError:
        from workiq import run_workiq_diagnostics  # type: ignore[no-redef]

    tenant_id = getattr(args, "tenant_id", None)
    skip_mcp_probe = getattr(args, "skip_mcp_probe", False)
    timeout = getattr(args, "timeout", 5.0)
    if timeout <= 0:
        print(f"{_ts()} ⚠️  --timeout は 0 より大きい値を指定してください。デフォルト値 5.0 を使用します。", file=sys.stderr)
        timeout = 5.0
    as_json = getattr(args, "json", False)
    sdk_probe = getattr(args, "sdk_probe", False)
    sdk_probe_timeout = getattr(args, "sdk_probe_timeout", 30.0)
    if sdk_probe_timeout <= 0:
        print(f"{_ts()} ⚠️  --sdk-probe-timeout は 0 より大きい値を指定してください。デフォルト値 30.0 を使用します。", file=sys.stderr)
        sdk_probe_timeout = 30.0
    event_extractor_self_test = getattr(args, "event_extractor_self_test", False)
    sdk_tool_probe = getattr(args, "sdk_tool_probe", False)
    sdk_tool_probe_timeout = getattr(args, "sdk_tool_probe_timeout", 60.0)
    if sdk_tool_probe_timeout <= 0:
        print(f"{_ts()} ⚠️  --sdk-tool-probe-timeout は 0 より大きい値を指定してください。デフォルト値 60.0 を使用します。", file=sys.stderr)
        sdk_tool_probe_timeout = 60.0
    sdk_event_trace = getattr(args, "sdk_event_trace", False)
    sdk_tool_probe_tools_all = getattr(args, "sdk_tool_probe_tools_all", False)

    report = run_workiq_diagnostics(
        tenant_id=tenant_id,
        skip_mcp_probe=skip_mcp_probe,
        mcp_probe_timeout=timeout,
        sdk_probe=sdk_probe,
        sdk_probe_timeout=sdk_probe_timeout,
        event_extractor_self_test=event_extractor_self_test,
        sdk_tool_probe=sdk_tool_probe,
        sdk_tool_probe_timeout=sdk_tool_probe_timeout,
        sdk_event_trace=sdk_event_trace,
        sdk_tool_probe_tools_all=sdk_tool_probe_tools_all,
    )

    if as_json:
        print(_json_module.dumps(
            [dataclasses.asdict(c) for c in report.checks],
            ensure_ascii=False,
            indent=2,
        ))
        has_fail = any(c.status == "FAIL" for c in report.checks)
        return 1 if has_fail else 0

    _STATUS_ICONS = {
        "PASS": "✅",
        "FAIL": "❌",
        "WARN": "⚠️",
        "SKIP": "⏭️",
    }

    print(f"\n{'=' * 60}")
    print("  Work IQ 診断レポート (workiq-doctor)")
    print(f"{'=' * 60}")

    has_fail = False
    for check in report.checks:
        icon = _STATUS_ICONS.get(check.status, "?")
        print(f"\n[{check.status}] {icon} {check.name}")
        if check.detail:
            for line in check.detail.splitlines():
                print(f"       {line}")
        if check.command:
            print(f"       コマンド: {check.command}")
        if check.status == "FAIL":
            has_fail = True

    print(f"\n{'=' * 60}")
    if has_fail:
        print("診断結果: ❌ 失敗があります")
        print("\nヒント:")
        print("  Windows PowerShell で npx.ps1 が Execution Policy によりブロックされる場合:")
        print("    npx.cmd -y @microsoft/workiq mcp")
        print("  環境変数で npx コマンドを指定する場合:")
        print("    $env:WORKIQ_NPX_COMMAND='C:\\Program Files\\nodejs\\npx.cmd'  (PowerShell)")
        print("    set WORKIQ_NPX_COMMAND=C:\\Program Files\\nodejs\\npx.cmd  (cmd)")
        print("    [Environment]::SetEnvironmentVariable('WORKIQ_NPX_COMMAND', 'C:\\Program Files\\nodejs\\npx.cmd', 'User')")
    else:
        print("診断結果: ✅ 全チェック成功")
    print(f"{'=' * 60}\n")

    return 1 if has_fail else 0


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


def _cmd_emit_prompt(args: argparse.Namespace) -> int:
    """emit-prompt サブコマンドのハンドラー。"""
    try:
        from .prompts import PRE_EXECUTION_QA_PROMPT_V2, render_pre_execution_qa_comment_body
    except ImportError:
        from prompts import PRE_EXECUTION_QA_PROMPT_V2, render_pre_execution_qa_comment_body  # type: ignore[no-redef]

    output = render_pre_execution_qa_comment_body() if args.comment_body else PRE_EXECUTION_QA_PROMPT_V2
    print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
