"""__main__.py — CLI エントリポイント

使い方:
    # (A) GUI モード（引数なし時の既定。PySide6 未導入時は自動で CLI へフォールバック）
    python -m hve
    python -m hve gui   # 明示指定（後方互換）

    # (B) CLI 対話ウィザードモード
    python -m hve cli

    # (C) python -m で直接実行（サブコマンド指定）
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

    # Knowledge Management（デフォルト設定: sources=qa, target_files=qa/*.md, force_refresh=false）
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
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional


def _configure_stdio_encoding() -> None:
    """stdout/stderr を UTF-8 に再設定する（パイプ経由起動時の cp932 対策）。

    `hve gui` などから ``subprocess.Popen(..., stdout=PIPE)`` で起動された場合、
    Python の標準出力ストリームはコンソール直結時の UTF-8 ではなく OS ロケール
    （Windows なら cp932）にフォールバックする。この状態で console.py が出力する
    ``▸`` (U+25B8) 等の Unicode 記号を ``print()`` すると ``UnicodeEncodeError``
    で落ちる。本関数で起動時に UTF-8 を強制し、全モードで一貫した出力にする。

    - ``errors="replace"`` により、万一エンコード不能文字が混入しても例外で
      落ちず置換文字に置き換える。
    - コンソール直結時（既に UTF-8 ベース）でも冪等に動作する。
    - ``reconfigure`` が無い環境（Python 3.6 以前等）では no-op。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - top-level guard
            pass


_configure_stdio_encoding()


def _reexec_in_venv_if_needed() -> None:
    """``python -m hve`` がリポジトリの ``.venv`` 外の Python で起動された場合に、
    同梱 ``.venv`` の Python へ自動的に再 exec する。

    セットアップ (``hve/setup-hve.*``) は全依存を ``<repo>/.venv`` に導入する。
    しかし activate 漏れや、システム Python から ``python -m hve gui`` を直接実行
    した場合は ``ModuleNotFoundError: No module named 'PySide6'`` 等で起動に失敗する。
    本関数はこれを吸収し、セットアップ直後でも ``python -m hve gui`` / ``cli`` が
    そのまま動作するようにする。

    挙動:
      - 既に ``.venv`` の Python で動作している場合は何もしない（冪等）。
      - ``.venv`` が存在しない場合は何もしない（現在の Python で続行）。
      - ``HVE_NO_VENV_REEXEC=1`` でオプトアウト（再帰防止にも使用）。
      - 検出・再 exec に失敗した場合は現在の Python で続行（フォールバック）。

    呼び出し箇所は 2 か所に限定する:
      - ``__name__ == "__main__"`` の module level（重い import より前）
      - ``_console_main()``（``hve`` console script 経路）
    ``import hve.__main__`` 等のライブラリ利用時には発火させない。
    """
    if os.environ.get("HVE_NO_VENV_REEXEC", "").strip().lower() in {"1", "true", "yes"}:
        return

    try:
        repo_root = Path(__file__).resolve().parent.parent
        venv_py = (
            repo_root / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else repo_root / ".venv" / "bin" / "python"
        )
        if not venv_py.exists():
            return
        # 既に .venv の Python で動作しているなら再 exec は不要。
        try:
            already_in_venv = os.path.samefile(sys.executable, str(venv_py))
        except OSError:
            already_in_venv = Path(sys.executable).resolve() == venv_py.resolve()
        if already_in_venv:
            return
        new_argv = [str(venv_py), "-m", "hve", *sys.argv[1:]]
        new_env = dict(os.environ)
        new_env["HVE_NO_VENV_REEXEC"] = "1"  # 再帰防止フラグ
    except Exception:  # pragma: no cover - 検出失敗時は従来挙動へフォールバック
        return

    print(
        # NOTE: この通知は環境正規化前（.venv 外の Python・cp932 等のコンソール）に
        # 出力される可能性があるため、文字化けを避けて ASCII のみで記述する。
        f"[hve] Detected non-.venv Python; re-executing with .venv: {venv_py}",
        file=sys.stderr,
    )

    if os.name == "nt":
        # Windows では os.execv の挙動が不安定なため subprocess + 終了コード継承を用いる。
        import subprocess

        try:
            completed = subprocess.run(new_argv, env=new_env)
        except Exception:  # pragma: no cover - 起動失敗時は現在の Python で続行
            return
        sys.exit(completed.returncode)
    else:
        try:
            os.execve(str(venv_py), new_argv, new_env)
        except Exception:  # pragma: no cover - exec 失敗時は現在の Python で続行
            return


if __name__ == "__main__":
    # 重い依存 (`.config` -> `cq`) を読み込む前に .venv へ再 exec する。
    # `python -m hve` では以下の module level import がファイル末尾の
    # `if __name__ == "__main__":` ブロックより先に評価されるため、
    # ガードをここに置かないと依存欠落で先に落ちる。
    _reexec_in_venv_if_needed()

try:
    from .config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_CHOICES, SDKConfig
    from .workflow_registry import canonicalize_workflow_id, get_workflow
except ImportError:
    # 平坦 import への退避は `cd hve && python __main__.py` のような
    # パッケージ文脈なし実行のときだけ。パッケージとして import されて
    # いる場合の失敗は依存欠落 (例: cq 未導入) なので真因を握り潰さず再送出する。
    if __package__:
        raise
    from config import DEFAULT_MODEL, MODEL_AUTO_VALUE, MODEL_CHOICES, SDKConfig  # type: ignore[no-redef]
    _workflow_registry_module = __import__("workflow_" + "registry")
    canonicalize_workflow_id = getattr(
        _workflow_registry_module,
        "canonicalize_workflow_id",
    )
    get_workflow = getattr(_workflow_registry_module, "get_workflow")


def _ts() -> str:
    """現在時刻のプレフィックス文字列を返す。"""
    return f"[{datetime.now().strftime('%H:%M:%S')}]"


# -----------------------------------------------------------------------
# Auto モデル定数
# -----------------------------------------------------------------------

MODEL_AUTO = MODEL_AUTO_VALUE

# AKM デフォルト値
# Work IQ を入力ソースとして任意追加できるよう、既定は qa + original-docs のマルチ値（カンマ区切り）。
_AKM_DEFAULT_SOURCES = "qa,original-docs"
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
# Work IQ を含むマルチ選択用のソース一覧（C-1 で使用）
_AKM_SOURCES_MULTI_OPTIONS = [
    "qa（質問票）",
    "original-docs（原資料）",
    "workiq（Microsoft 365 Copilot Work IQ）",
]
_AKM_SOURCES_MULTI_VALUES = ["qa", "original-docs", "workiq"]
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
    "adfd": "データデータフロー処理 / バッチの APP-ID を自動選択",
    "adfdv": "データデータフロー処理 / バッチの APP-ID を自動選択",
}

_PARAM_PROMPT_LABELS = {
    "app_ids": "対象 APP-ID",
    "app_id": "対象 APP-ID（単一）",
    "resource_group": "Azure リソースグループ名（任意）",
    "usecase_id": "対象ユースケースID（任意）",
    "app_id": "対象データフローアプリID（カンマ区切り・任意）",
    "target_scope": "対象スコープ",
    "focus_areas": "重点観点（任意）",
    "target_dirs": "ドキュメント生成対象ディレクトリ（カンマ区切り。省略 = 全体）",
    "exclude_patterns": "除外パターン（カンマ区切り）",
    "issue_title": "GitHub Issue タイトル（任意）",
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
    "app_id": "",
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
            return f"対象業務名 {s.DIM}既定値: Step 1で作成されたドキュメントの「戦略的提言」から、LLMで自動生成){s.RESET}"
        return "対象業務名既定値: Step 1で作成されたドキュメントの「戦略的提言」から、LLMで自動生成)"
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
        - selected_steps: ウィザードでユーザーが選択したグループ ID 一覧（"1" / "2" / "3" / "4"）。
          Enter 時の初期値は ["2", "3", "4"]。
          グループ ID は registry 侧の `_WORKFLOW_GROUP_MAPS["ard"]` で実 Step ID に展開される:
            "1" → ["1", "1.1", "1.2"]（企業の事業分析）
            "2" → ["2"]（要求定義書作成）
            "3" → ["2.1"]（KPI/OKR 定義・任意）
            "4" → ["3.1", "3.2", "3.3"]（ユースケース作成）
    """
    from datetime import date

    params: dict = {}
    # 4 グループ体系。各グループは内部で複数 Step を順次実行する。
    # Step 3（KPI/OKR）も既定で選択に含める（Step 2 / 4 と同時実行することで戦略的記述から
    # KPI/OKR・計測データ・データ収集設計まで一気通貫で生成する運用に合わせる）。
    _ard_step_ids = ["1", "2", "3", "4"]
    _ard_step_options = [
        "[1] 企業の事業分析（事業分野候補列挙 → 分野別深掘り → 統合）",
        "[2] 要求定義書作成（Step 1 の出力があれば参考にし、無くてもよい）",
        "[3] KPI/OKR 定義（任意・戦略的記述から KPI/OKR・計測データ・データ収集設計を生成）",
        "[4] ユースケース作成（骨格抽出 → 詳細生成 → カタログ統合）",
    ]
    selected_indices = con.prompt_multi_select(
        "ARD で実行するステップを選択",
        _ard_step_options,
        default_indices=[1, 2, 3],
    )
    selected_steps = [_ard_step_ids[i] for i in selected_indices if 0 <= i < len(_ard_step_ids)]
    if not selected_steps:
        selected_steps = ["2", "3", "4"]

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
        # quick-auto モードでも Step 3 (KPI/OKR 定義) を既定で有効化する（GUI/CLI 対話ウィザードと整合）。
        # orchestrator 側で selected_steps に "3" が含まれれば自動同期されるが、明示的に True を記録する。
        params["include_kpi_okr"] = True
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
        # Step 3 (KPI/OKR 定義・任意): Step 2 または Step 4 が選択時のみプロンプト。
        # 他の場合は自動的に False（DAG にも組み込まれない）。
        if ("2" in selected_steps or "4" in selected_steps):
            params["include_kpi_okr"] = con.prompt_yes_no(
                "KPI/OKR 定義 (Step 3・任意) を実行しますか？"
                "（戦略的記述から KPI/OKR・計測データ・データ収集設計を生成）",
                default=False,
            )
        else:
            params["include_kpi_okr"] = False

    # グループ ID ("1"/"2"/"3"/"4") は registry 侧の _WORKFLOW_GROUP_MAPS で実 Step ID に展開される。
    # （旧仕様の "1.1 選択時に Step '1' を自動前提" は撤廃。グループ "1" 自体が 1,1.1,1.2 を包含する。）

    return params, selected_steps


def _asdw_data_deploy_is_selected(selected_step_ids: list[str]) -> bool:
    """Return whether an ASDW selection can reach Step 1.3."""
    return not selected_step_ids or any(
        step_id in {"1", "1.3"} or step_id.startswith("1.3/")
        for step_id in selected_step_ids
    )


# ASDW-WEB Step 1.3 の必須パラメータの表示ラベル（FR-CLI-14）。
# キー集合の正本は workflow_registry の StepDef.required_params（FR-DAG-07）。
_ASDW_DATA_DEPLOY_PARAM_LABELS = {
    "resource_group": "Azure リソースグループ名",
    "data_location": "DataDeploy location",
    "data_resource_suffix": "DataDeploy resource suffix",
    "data_vnet_cidr": "DataDeploy VNet CIDR",
    "data_private_endpoint_subnet_cidr": "DataDeploy private endpoint subnet CIDR",
    "data_aci_subnet_cidr": "DataDeploy ACI subnet CIDR",
}


def _asdw_data_deploy_param_keys() -> frozenset:
    """ASDW-WEB Step 1.3 が宣言する必須パラメータ名を返す（FR-DAG-07）。"""
    wf = get_workflow("asdw-web")
    step = wf.get_step("1.3") if wf is not None else None
    return frozenset(step.required_params) if step is not None else frozenset()


def _prompt_asdw_data_deploy_params(con, collected: dict) -> dict:
    """ASDW-WEB Step 1.3 の必須パラメータを宣言（FR-DAG-07）から収集する。

    既定値があるキーは既定値を提示し、Enter のみで採用できる。
    先行の汎用ループで非空値を収集済みのキーは再質問しない。
    """
    wf = get_workflow("asdw-web")
    step = wf.get_step("1.3") if wf is not None else None
    if step is None:
        return {}
    values: dict = {}
    for key in step.required_params:
        existing = collected.get(key)
        if isinstance(existing, str) and existing.strip():
            continue
        values[key] = con.prompt_input(
            _ASDW_DATA_DEPLOY_PARAM_LABELS.get(key, key),
            default=step.default_params.get(key, ""),
            required=True,
        )
    return values


def _collect_generic_workflow_params(
    con,
    wf,
    *,
    is_quick_auto: bool,
    selected_step_ids: Optional[list[str]] = None,
) -> dict:
    """AKM/AQOD 以外のワークフロー固有パラメータを収集する。"""
    params: dict = {}
    # FR-CLI-14: Step 1.3 の required_params は DataDeploy ブロックが宣言由来の
    # ラベル・既定値で尋ねるため、汎用ループ側では尋ねない（二重質問防止）。
    asdw_data_param_keys: frozenset = frozenset()
    collect_asdw_data_params = (
        wf.id == "asdw-web"
        and not is_quick_auto
        and _asdw_data_deploy_is_selected(selected_step_ids or [])
    )
    if collect_asdw_data_params:
        asdw_data_param_keys = _asdw_data_deploy_param_keys()
    if "app_ids" in wf.params or "app_id" in wf.params:
        if not is_quick_auto:
            params.update(_prompt_app_ids(con, wf.id))
    for param_name in wf.params:
        if param_name in ("app_ids", "app_id"):
            continue
        if param_name in asdw_data_param_keys:
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
    if collect_asdw_data_params:
        params.update(_prompt_asdw_data_deploy_params(con, params))
    return params


def _default_akm_target_files(sources) -> str:
    """AKM の sources に応じた target_files 既定値を返す。

    ``sources`` は文字列（カンマ/空白区切り）または ``list[str]`` を受け付ける。
    Work IQ のみ、または非 Work IQ ソースが複数の場合は既定パターンなし（``""``）。

    後方互換: 旧 ``"original-docs"`` / ``"both"`` 等の単一文字列も受理する。
    """
    # orchestrator 側の正規化／既定算出を再利用し、本モジュール内の重複ロジックを避ける。
    try:
        from .orchestrator import _default_akm_target_files as _impl  # type: ignore
    except ImportError:
        from orchestrator import _default_akm_target_files as _impl  # type: ignore[no-redef]
    return _impl(sources)


def _normalize_akm_sources(value) -> list:
    """``orchestrator._normalize_akm_sources`` への薄いラッパー。"""
    try:
        from .orchestrator import _normalize_akm_sources as _impl  # type: ignore
    except ImportError:
        from orchestrator import _normalize_akm_sources as _impl  # type: ignore[no-redef]
    return _impl(value)


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

    _wf_id = canonicalize_workflow_id(wf_id)
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
        params["force_refresh"] = False
        params["custom_source_dir"] = ""
        params["enable_auto_merge"] = False
        # Work IQ 入力フェーズはクイック全自動モードでは既定 OFF（明示要求がない限り）。
        params["workiq_akm_ingest_dxx"] = []
        return params

    # 取り込みソースをマルチ選択（qa / original-docs / workiq）。
    # 既定は qa + original-docs。空選択は既定にフォールバックする。
    _default_indices = [0, 1]  # qa, original-docs
    selected_indices = con.prompt_multi_select(
        "取り込みソースを選択してください（複数選択可）",
        _AKM_SOURCES_MULTI_OPTIONS,
        default_indices=_default_indices,
    )
    if not selected_indices:
        selected_indices = list(_default_indices)
    selected_values = [_AKM_SOURCES_MULTI_VALUES[i] for i in selected_indices]
    # _normalize_akm_sources を経由して順序固定化（workiq, qa, original-docs）。
    normalized = _normalize_akm_sources(selected_values)
    params["sources"] = ",".join(normalized)

    default_target = _default_akm_target_files(normalized)
    target_input = con.prompt_input(
        "対象ファイルパス（スペース区切り、省略時: デフォルト）",
        default=default_target,
    )
    target_input_strip = (target_input or "").strip()
    params["target_files"] = target_input_strip if target_input_strip else default_target

    params["force_refresh"] = con.prompt_yes_no(
        "既存 knowledge/ 出力を完全に再生成する？",
        default=False,
    )
    params["custom_source_dir"] = con.prompt_input(
        "追加ソースディレクトリ（スペース区切り・任意）",
        default="",
    )
    params["enable_auto_merge"] = False

    # Work IQ が選択されている場合のみ、取り込み対象 Dxx の絞り込みを尋ねる（Sub-C-4）。
    if "workiq" in normalized:
        dxx_input = con.prompt_input(
            "Work IQ 取り込み対象 Dxx（カンマ区切り、例: D01,D04。省略=全件 D01〜D21）",
            default="",
        )
        # config 側のヘルパで正規化（無効パターンは除外、空 → []）。
        try:
            from .config import _parse_workiq_akm_ingest_dxx  # type: ignore
        except ImportError:
            from config import _parse_workiq_akm_ingest_dxx  # type: ignore[no-redef]
        params["workiq_akm_ingest_dxx"] = _parse_workiq_akm_ingest_dxx(dxx_input or "")
    else:
        params["workiq_akm_ingest_dxx"] = []

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

    # 必須（--autopilot-chain 指定時は省略可）
    orch.add_argument(
        "--workflow", "-w",
        required=False,
        default=None,
        metavar="WORKFLOW_ID",
        help=(
            "ワークフロー ID: "
            "aas(App Architecture Design) / "
            "aad(App Detail Design) / "
            "asdw(App Dev Microservice Azure) / "
            "adfd(Dataflow Design) / "
            "adfdv(Dataflow Dev) / "
            "akm(Knowledge Management) / "
            "aqod(Original Docs Review) / "
            "adoc(Source Codeからのドキュメント作成)"
            " — `--autopilot-chain` 指定時は省略可（排他）"
        ),
    )

    # Autopilot チェーン実行（GUI Autopilot と同等の挙動を CLI で再現）
    orch.add_argument(
        "--autopilot-chain",
        default=None,
        metavar="WORKFLOW_IDS",
        help=(
            "Autopilot チェーン実行で許可する Workflow ID をカンマ区切りで指定する "
            "(例: --autopilot-chain aad-web,asdw-web)。"
            "`docs/catalog/app-arch-catalog.md` から APP 一覧を取得し、APP 単位の"
            "並列レーン × チェーン内直列で `python -m hve orchestrate` を起動する。"
            "※ 実際の実行順序は APP アーキ種別ごとの固定チェーン（web-cloud=aad-web→asdw-web、"
            "batch=adfd→adfdv）で決まり、本引数はその中から実行する workflow をフィルタする。"
            "未対応 ID は警告のみで無視される。`--workflow` とは排他指定。"
        ),
    )
    orch.add_argument(
        "--autopilot-dry-run",
        action="store_true",
        default=False,
        help="--autopilot-chain の実行計画のみ表示して終了する（サブプロセスは起動しない）。",
    )
    orch.add_argument(
        "--autopilot-catalog",
        default=None,
        metavar="PATH",
        help="--autopilot-chain で参照するカタログファイル（既定: docs/catalog/app-arch-catalog.md）。",
    )
    orch.add_argument(
        "--autopilot-max-parallel",
        type=int,
        default=4,
        metavar="N",
        help="--autopilot-chain の APP 並列度（既定: 4、1〜16 にクリップ）。",
    )

    orch.add_argument(
        "--enable-agentic-retrieval",
        choices=["auto", "yes", "no"],
        default=None,
        help=(
            "Agentic Retrieval Step（AAD-WEB 2.6 / ASDW-WEB 2.5・2.6）の有効化。"
            "no を指定すると当該 Step を実行対象から外す。"
            "省略時はウィザード回答、それも無ければ auto。"
        ),
    )

    orch.add_argument(
        "--agentic-data-source-modes",
        nargs="+",
        choices=["indexer", "push"],
        default=None,
        metavar="MODE",
        help="Agentic Retrieval のデータソース投入方式（indexer / push、複数指定可。既定: indexer）。",
    )
    orch.add_argument(
        "--foundry-mcp-integration",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Microsoft Foundry 連携（Remote MCP Server）の有無（既定: 有効）。",
    )
    orch.add_argument(
        "--agentic-data-sources-hint",
        default=None,
        metavar="TEXT",
        help="想定データソースのヒント（自由記述）。Knowledge Source 選定の根拠に使う。",
    )
    orch.add_argument(
        "--agentic-existing-design-diff-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="既存の Agentic Retrieval 設計を上書きせず差分更新する（既定: 無効）。",
    )
    orch.add_argument(
        "--foundry-sku-fallback-policy",
        choices=["standard_allowed", "global_required"],
        default=None,
        help=(
            "Foundry モデル SKU のフォールバック方針。"
            "standard_allowed = Standard へのフォールバックを許容（既定）、"
            "global_required = Global Standard 必須。"
        ),
    )

    orch.add_argument(
        "--enable-tool-search",
        choices=["auto", "yes", "no"],
        default=None,
        help=(
            "Foundry Toolbox の tool search（Tool 定義の遅延公開）の使用方針。"
            "auto = Tool 総数が 15 を超えたら有効化（既定）、"
            "yes = 常に有効、no = 使わない。"
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

    # reasoning effort (SDK ModelInfo.supported_reasoning_efforts から選択)
    orch.add_argument(
        "--reasoning-effort",
        default=None,
        metavar="EFFORT",
        help=(
            "モデルの reasoning effort 値 (モデルが supportedReasoningEfforts を返す場合のみ有効。"
            "例: low/medium/high)。省略時は Auto モデルでは high をフォールバック、"
            "明示モデルでは SDK 既定動作。サポート外の値は SDK エラーとなる可能性がある。"
        ),
    )
    orch.add_argument(
        "--review-reasoning-effort",
        default=None,
        metavar="EFFORT",
        help="レビュー用モデルの reasoning effort（省略時は --reasoning-effort を継承）",
    )
    orch.add_argument(
        "--qa-reasoning-effort",
        default=None,
        metavar="EFFORT",
        help="QA 用モデルの reasoning effort（省略時は --reasoning-effort を継承）",
    )
    orch.add_argument(
        "--context-tier",
        default=None,
        choices=["default", "long_context"],
        help=(
            "SDK の create_session(context_tier=...) へ渡すコンテキスト階層。"
            "long_context は対応モデルでロングコンテキストを有効化する。"
            "省略時は SDK/サーバ既定。"
        ),
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
        "--qa-answer-mode",
        choices=["autopilot", "gui-file"],
        default=None,
        help=(
            "QA 回答モード（GUI からの利用想定）:"
            " 'autopilot' = 全問既定値自動採用、"
            " 'gui-file' = --qa-ipc-dir で指定したディレクトリ経由で GUI から回答を受け取る。"
            " 未指定時は既存挙動（非 TTY フォールバック or 対話）。"
        ),
    )
    orch.add_argument(
        "--qa-ipc-dir",
        default=None,
        metavar="PATH",
        help=(
            "--qa-answer-mode=gui-file 時の IPC ディレクトリパス。"
            " CLI は <step_id>.request.json を書き出し <step_id>.answers.md / <step_id>.cancel を待機する。"
        ),
    )
    orch.add_argument(
        "--steering-ipc-dir",
        default=None,
        metavar="PATH",
        help=(
            "実行中ワークフローへの割り込み送信（Steering）用 IPC ディレクトリパス（GUI からの利用想定）。"
            " CLI は steering-<step_id>-<epoch_ms>.request.json を polling し、検出時に"
            " session.send(mode=\"immediate\") でメインタスクへ割り込みメッセージを注入する。"
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
        "--auto-compaction",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="auto_compaction",
        help=(
            "サブステップ実行で SDK の自動コンテキスト圧縮（infinite_sessions）を有効化する "
            "(--auto-compaction: 有効, --no-auto-compaction: 無効, 省略時: HVEConfig.auto_compaction を継承)"
        ),
    )
    orch.add_argument(
        "--tool-search",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="tool_search",
        help=(
            "SDK のツール定義遅延ロード（tool_search）を有効化する "
            "(--tool-search: 有効, --no-tool-search: 無効, 省略時: HVEConfig.tool_search を継承)"
        ),
    )
    orch.add_argument(
        "--tool-search-ranking",
        choices=["sdk", "hve"],
        default=None,
        dest="tool_search_ranking",
        help=(
            "tool_search 有効時のランキング実装。"
            "sdk: SDK 組み込みのまま（既定）/ "
            "hve: `tool_search_tool` を HVE 実装へ差し替え、日本語対応 BM25・pin ポリシー・"
            "Skill のカタログ合流を使う。--tool-search とは直交する"
        ),
    )
    orch.add_argument(
        "--workiq-akm-ingest",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "AKM の入力ソースとして Work IQ を有効/無効化する"
            "（未指定時は --sources に 'workiq' が含まれるかで自動判定）"
        ),
    )
    orch.add_argument(
        "--workiq-dxx",
        default=None,
        metavar="DXX_LIST",
        help=(
            "AKM Work IQ 取り込み対象 Dxx をカンマ区切りで指定（例: D01,D04）。"
            "省略時は全 D01〜D21 を対象とする。"
        ),
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
    orch.add_argument(
        "--workiq-request-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Work IQ MCP サーバーへのツール呼び出し 1 回あたりのタイムアウト秒数（未指定時: 環境変数 WORKIQ_REQUEST_TIMEOUT / 設定（既定 300 秒 = 5 分））。Copilot SDK MCPServerConfigLocal.timeout にミリ秒として渡される。",
    )

    # Issue/PR 作成
    orch.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "local 実行モード既定の continue-on-precheck を無効化する。"
            " Pre-check（入力成果物・必須 Skill）失敗時に従来通り中断する。"
            " github 実行モード（Cloud）では本フラグは無視される。"
        ),
    )
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

    # Fleet mode
    orch.add_argument(
        "--fleet-mode",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="fleet_mode_enabled",
        help="複数 Step の DAG wave を Copilot SDK Fleet mode に委譲する（既定: 無効、未指定時は環境変数/設定を継承）",
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

    # Cloud Sessions (GitHub Copilot SDK 1.0.0+)
    orch.add_argument(
        "--cloud-session",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="cloud_session_enabled",
        help="Cloud Session を有効/無効化する（既定: 無効、未指定時は環境変数/設定を継承）",
    )
    orch.add_argument(
        "--cloud-session-owner",
        default=None,
        metavar="OWNER",
        help="Cloud Session の repository.owner 明示値（未指定時は --repo / REPO から補完）",
    )
    orch.add_argument(
        "--cloud-session-repository-name",
        default=None,
        metavar="NAME",
        help="Cloud Session の repository.name 明示値（未指定時は --repo / REPO から補完）",
    )
    orch.add_argument(
        "--cloud-session-branch",
        default=None,
        metavar="BRANCH",
        help="Cloud Session の repository.branch 明示値（未指定時は --branch / base_branch を使用）",
    )
    orch.add_argument(
        "--cloud-session-max-concurrency",
        type=int,
        default=None,
        metavar="N",
        help="Cloud Session の同時実行上限（未指定時: 5）",
    )
    orch.add_argument(
        "--cloud-session-integration-id",
        default=None,
        metavar="ID",
        help="GITHUB_COPILOT_INTEGRATION_ID に渡す Cloud Session integration ID",
    )
    orch.add_argument(
        "--cloud-session-mc-base-url",
        default=None,
        metavar="URL",
        help="COPILOT_MC_BASE_URL に渡す Mission Control base URL（GHES 用）",
    )
    orch.add_argument(
        "--cloud-session-step-overrides",
        default=None,
        metavar="JSON",
        help="Step 単位 Cloud Session 上書き JSON（例: '{\"1\": true, \"2\": false}'）",
    )
    orch.add_argument(
        "--cloud-session-subtask-overrides",
        default=None,
        metavar="JSON",
        help="サブタスク単位 Cloud Session 上書き JSON（例: '{\"pre_qa\": true}'）",
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
        help="アプリ ID (ASDW/ADFDV 等で使用)。後方互換のため残す。複数指定は --app-ids を使用",
    )
    orch.add_argument(
        "--app-ids",
        default=None,
        metavar="APP_IDS",
        help=(
            "対象アプリケーション (APP-ID) — カンマ区切りで複数指定可。\n"
            "AAD-WEB/ASDW-WEB は Webフロントエンド + クラウド、\n"
            "ADFD/ADFDV は データデータフロー処理/バッチ の APP-ID のみ採用します。\n"
            "未指定時は docs/catalog/app-arch-catalog.md から自動選択します。"
        ),
    )
    orch.add_argument(
        "--resource-group",
        default=None,
        metavar="RG",
        help="Azure リソースグループ名",
    )
    orch.add_argument("--data-location", default=None, metavar="LOCATION")
    orch.add_argument("--data-resource-suffix", default=None, metavar="SUFFIX")
    orch.add_argument("--data-vnet-cidr", default=None, metavar="CIDR")
    orch.add_argument(
        "--data-private-endpoint-subnet-cidr", default=None, metavar="CIDR"
    )
    orch.add_argument("--data-aci-subnet-cidr", default=None, metavar="CIDR")
    orch.add_argument(
        "--usecase-id",
        default=None,
        metavar="UC_ID",
        help="ユースケース ID (ASDW 等で使用)",
    )

    # AKM 固有パラメータ
    orch.add_argument(
        "--sources",
        default=None,
        help=(
            "AKM: 取り込みソース。qa / original-docs / workiq / both（後方互換）"
            " のカンマ区切り組合せ（例: 'qa,original-docs', 'qa,original-docs,workiq', 'workiq'）。"
            "省略時の既定は 'qa,original-docs'。"
        ),
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
        help="AKM: 既存 knowledge/ 出力を完全に再生成する (デフォルト: 無効。--force-refresh で有効化)",
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
        "--delete-local-merged-branch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "FR-CLI-34: enable_auto_merge による auto-approve-and-merge 完了（PR が merged）を"
            " 検知後、今回作成した作業ブランチをローカルのみ削除する"
            " (デフォルト: 有効、--no-delete-local-merged-branch で無効化)"
        ),
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
    orch.add_argument(
        "--include-kpi-okr",
        action="store_true",
        default=False,
        help=(
            "ARD: Step 3 (KPI/OKR 定義) を実行する（任意・既定 false）。"
            "true の場合、戦略的記述から KPI/OKR・計測データ定義・データ収集設計を生成し "
            "docs/recommended-kpi-okr.md を出力する。後続 UC・APP 設計が任意参照する。"
        ),
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
    orch.add_argument(
        "--self-improve-max-iterations",
        type=int,
        default=None,
        metavar="N",
        help="自己改善ループの最大繰り返し回数（既定: 3）。--self-improve 有効時のみ有効。",
    )
    orch.add_argument(
        "--self-improve-target-scope",
        default=None,
        metavar="SCOPE",
        help="自己改善ループの対象パス（例: 'src/' / 'hve/' / 空=リポジトリ全体）。--self-improve 有効時のみ有効。",
    )
    orch.add_argument(
        "--self-improve-goal",
        default=None,
        metavar="TEXT",
        help="自己改善ループのゴール説明（省略時はワークフロー種別から自動設定）。--self-improve 有効時のみ有効。",
    )

    # mdq リアルタイム索引更新（HVE CLI Orchestrator 限定機能）
    orch.add_argument(
        "--mdq-watch",
        dest="mdq_watch",
        action="store_true",
        default=None,
        help=(
            "Markdown ファイルの追加/更新/削除を OS イベントで検知し .mdq/index.sqlite を逐次更新する。"
            " 既定 ON。watchdog 未導入時は自動で無効化（警告ログのみ）。"
            " 環境変数 HVE_MDQ_WATCH=0 または --no-mdq-watch で無効化できる。"
            " 既存の `python -m mdq index` による手動索引更新は維持される。"
        ),
    )
    orch.add_argument(
        "--no-mdq-watch",
        dest="no_mdq_watch",
        action="store_true",
        default=False,
        help="mdq リアルタイム索引更新を無効化する（--mdq-watch および HVE_MDQ_WATCH=true より優先）。",
    )
    orch.add_argument(
        "--mdq-watch-debounce-ms",
        dest="mdq_watch_debounce_ms",
        type=int,
        default=None,
        metavar="MS",
        help="mdq watcher のデバウンス間隔（ms、既定 500）。環境変数 HVE_MDQ_WATCH_DEBOUNCE_MS でも指定可。",
    )

    # cq リアルタイム索引更新（HVE CLI Orchestrator 限定機能）
    orch.add_argument(
        "--cq-watch",
        dest="cq_watch",
        action="store_true",
        default=None,
        help=(
            "ソースファイルの追加/更新/削除を OS イベントで検知し .cq/index-<profile>.sqlite を逐次更新する。"
            " 監視対象は cq 設定ファイルで最初に宣言された profile 。"
            " 既定 ON。watchdog 未導入時や cq 設定不在時は自動で無効化（警告ログのみ）。"
            " 環境変数 HVE_CQ_WATCH=0 または --no-cq-watch で無効化できる。"
            " 既存の `python -m cq index` による手動索引更新は維持される。"
        ),
    )
    orch.add_argument(
        "--no-cq-watch",
        dest="no_cq_watch",
        action="store_true",
        default=False,
        help="cq リアルタイム索引更新を無効化する（--cq-watch および HVE_CQ_WATCH=true より優先）。",
    )
    orch.add_argument(
        "--cq-watch-debounce-ms",
        dest="cq_watch_debounce_ms",
        type=int,
        default=None,
        metavar="MS",
        help="cq watcher のデバウンス間隔（ms）。環境変数 HVE_CQ_WATCH_DEBOUNCE_MS でも指定可。省略時は cq の既定値。",
    )

    # --- Workbench UI（4 ペイン固定レイアウトのターミナル表示）---
    orch.add_argument(
        "--workbench",
        choices=("auto", "on", "off"),
        default="auto",
        help=(
            "Workbench UI（Header/Steps/Body 固定スクロール/Footer）を有効化する。"
            "auto: TTY かつ非 quiet/final_only/HVE_NO_WORKBENCH=1 時に有効。"
            "off: 常に既存の plain 出力。"
        ),
    )
    orch.add_argument(
        "--workbench-body-lines",
        type=int,
        default=10,
        metavar="N",
        help="Workbench Body のコンテンツ行数（10〜20 にクランプ。既定: 10。環境変数 HVE_WORKBENCH_BODY_LINES でも指定可）。",
    )
    orch.add_argument(
        "--workbench-history",
        type=int,
        default=10000,
        metavar="N",
        help="Workbench 履歴バッファ容量（既定: 10000 行）。",
    )
    orch.add_argument(
        "--workbench-flush-on-exit",
        dest="workbench_flush_on_exit",
        action="store_true",
        default=True,
        help="Workbench 終了時に履歴を通常 stdout にフラッシュする（CI ログ保存性、既定: 有効）。",
    )
    orch.add_argument(
        "--no-workbench-flush-on-exit",
        dest="workbench_flush_on_exit",
        action="store_false",
        help="Workbench 終了時のフラッシュを無効化する。",
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

    # --- gui サブコマンド ---
    gui_parser = sub.add_parser(
        "gui",
        help="PySide6 ベースの HVE GUI Orchestrator を起動する (pip install -e .[gui] が必要)",
    )
    # Autopilot モード関連フラグ
    gui_parser.add_argument(
        "--autopilot-child",
        action="store_true",
        help="（内部用）Autopilot 親 GUI から起動される子 GUI モード。"
             " Wizard をバイパスし、--app-id / --chain で指定されたチェーンを直接実行する。",
    )
    gui_parser.add_argument(
        "--app-id",
        default=None,
        help="（--autopilot-child 用）対象 APP-ID（例: APP-01）",
    )
    gui_parser.add_argument(
        "--chain",
        default=None,
        help="（--autopilot-child 用）実行する workflow_id のカンマ区切りリスト。"
             " 許可値: aad-web, asdw-web, adfd, adfdv",
    )
    gui_parser.add_argument(
        "--app-arch-catalog",
        default=None,
        help="Application Architecture Catalog ファイルのパス"
             " (既定: docs/catalog/app-arch-catalog.md)。"
             " Autopilot モードのカタログ指定にも使用する。",
    )

    # --- cli サブコマンド ---
    # `run` のエイリアス。引数なし起動が GUI 既定に変わったため、CLI 対話ウィザードを
    # 明示的に起動するエントリポイントとして追加。
    cli_parser = sub.add_parser(
        "cli",
        help="対話型 CLI ウィザードでワークフローを実行する (旧: 引数なし時の既定挙動)",
    )
    cli_parser.add_argument(
        "--banner",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="banner",
        help="起動時バナー表示を制御する (--banner: 表示, --no-banner: 抑止, 省略時: 表示)",
    )

    # --- login サブコマンド ---
    # GitHub Copilot へ OAuth Device Flow でログインし、利用可能モデル一覧を
    # キャッシュに保存する。認証付与は SDK 同梱 `copilot login` が担当。
    login_parser = sub.add_parser(
        "login",
        help="GitHub Copilot へログインし、利用可能モデル一覧をキャッシュする",
    )
    login_parser.add_argument(
        "--host",
        default="https://github.com",
        help="GitHub ホスト URL (GHEC データレジデンシー時のみ変更)",
    )
    login_parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="ログイン後のモデル一覧取得をスキップする",
    )
    login_parser.add_argument(
        "--status",
        action="store_true",
        help="ログインを起動せず、現在の認証状態とキャッシュされたモデル一覧を表示する",
    )

    # --- pricing サブコマンド ---
    # GitHub Copilot の AI Credit 料金表（モデル別 multiplier + プラン別追加料金）を
    # クロール & キャッシュし、`show` で人間可読に確認するためのユーティリティ。
    pricing_parser = sub.add_parser(
        "pricing",
        help="GitHub Copilot AI Credit 料金表を取得・表示する",
    )
    pricing_sub = pricing_parser.add_subparsers(dest="pricing_command")
    pricing_show = pricing_sub.add_parser(
        "show",
        help="現在キャッシュされている料金表を表示する（無ければ取得を試行）",
    )
    pricing_show.add_argument(
        "--json",
        action="store_true",
        help="JSON 形式で出力する",
    )
    pricing_refresh = pricing_sub.add_parser(
        "refresh",
        help="docs.github.com / github.com/pricing から料金表を強制再取得する",
    )
    pricing_refresh.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP タイムアウト秒（デフォルト: 10.0）",
    )

    # --- toolsearch サブコマンド ---
    # FR-TS-09 / FR-TS-10: 差し替えたランカーの実行時統計を集計して表示する。
    toolsearch_parser = sub.add_parser(
        "toolsearch",
        help="Tool Search ランキング（HVE 実装）の統計を表示する",
    )
    toolsearch_sub = toolsearch_parser.add_subparsers(dest="toolsearch_command")
    ts_dashboard = toolsearch_sub.add_parser(
        "dashboard",
        help="収集済みイベントからダッシュボードを描画する",
    )
    ts_dashboard.add_argument(
        "--events",
        default=None,
        help="イベントログのパス（既定: <repo-root>/.toolsearch/events.jsonl、HVE_TOOLSEARCH_EVENTS）",
    )
    ts_dashboard.add_argument(
        "--usage",
        default=None,
        help="利用履歴のパス（既定: <repo-root>/.toolsearch/usage.jsonl、HVE_TOOLSEARCH_USAGE）",
    )
    ts_dashboard.add_argument(
        "--since",
        default=None,
        help="この ISO8601 時刻（UTC）以降のイベントだけを集計する 例: 2026-08-01T00:00:00Z",
    )
    ts_dashboard.add_argument(
        "--top",
        type=int,
        default=10,
        help="上位一覧の表示件数（デフォルト: 10）",
    )
    ts_dashboard.add_argument("--json", action="store_true", help="JSON 形式で出力する")
    ts_dashboard.add_argument(
        "--html",
        default=None,
        help="自己完結 HTML をこのパスへ書き出す（外部ネットワークへ接続しない）",
    )
    ts_mode = ts_dashboard.add_mutually_exclusive_group()
    ts_mode.add_argument(
        "--follow",
        action="store_true",
        help="一定間隔で再集計して表示を更新する（Ctrl+C で終了）",
    )
    ts_mode.add_argument("--once", action="store_true", help="1 回だけ描画して終了する（既定）")
    ts_dashboard.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="--follow のときの更新間隔秒（デフォルト: 2.0）",
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
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"{_ts()} ❌ MCP 設定ファイルの形式が不正です: JSON object を指定してください。", file=sys.stderr)
            return None
        if "mcpServers" in data:
            servers = data.get("mcpServers")
            if not isinstance(servers, dict):
                print(f"{_ts()} ❌ MCP 設定ファイルの形式が不正です: mcpServers は JSON object である必要があります。", file=sys.stderr)
                return None
            return servers
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{_ts()} ❌ MCP 設定ファイルの読み込みに失敗しました: {exc}", file=sys.stderr)
        return None


# -----------------------------------------------------------------------
# SDKConfig 構築
# -----------------------------------------------------------------------

def _apply_agentic_retrieval_cli_overrides(config, args: argparse.Namespace) -> None:
    """Agentic Retrieval 関連の CLI フラグを config へ反映する。

    優先順位は CLI フラグ > ウィザード回答 > 既定値。
    CLI 未指定（None）のときは config を変更しないので、ウィザードで
    収集した値がそのまま残る。
    """
    for attr in (
        "enable_agentic_retrieval",
        "agentic_data_source_modes",
        "foundry_mcp_integration",
        "agentic_data_sources_hint",
        "agentic_existing_design_diff_only",
        "foundry_sku_fallback_policy",
        "enable_tool_search",
    ):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(config, attr, value)


def _build_config(args: argparse.Namespace):
    """argparse の Namespace から SDKConfig を構築する。"""
    # モジュールのインポート
    _sdk_dir = Path(__file__).resolve().parent
    if str(_sdk_dir) not in sys.path:
        sys.path.insert(0, str(_sdk_dir))

    try:
        from .config import DEFAULT_MODEL, SDKConfig, normalize_model, _parse_bool_mapping
    except ImportError:
        from config import DEFAULT_MODEL, SDKConfig, normalize_model, _parse_bool_mapping  # type: ignore[no-redef]

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
    # reasoning_effort (ユーザー明示指定を SDKConfig に転送)
    cfg.reasoning_effort = getattr(args, "reasoning_effort", None) or None
    cfg.review_reasoning_effort = getattr(args, "review_reasoning_effort", None) or None
    cfg.qa_reasoning_effort = getattr(args, "qa_reasoning_effort", None) or None
    # context_tier (ユーザー明示指定を SDKConfig に転送)
    cfg.context_tier = getattr(args, "context_tier", None) or None
    cfg.max_parallel = args.max_parallel
    cfg.auto_qa = args.auto_qa
    cfg.force_interactive = getattr(args, "force_interactive", False)
    cfg.qa_answer_mode = getattr(args, "qa_answer_mode", None)
    cfg.qa_ipc_dir = getattr(args, "qa_ipc_dir", None)
    cfg.steering_ipc_dir = getattr(args, "steering_ipc_dir", None)
    cfg.auto_contents_review = args.auto_contents_review
    cfg.auto_coding_agent_review = args.auto_coding_agent_review
    cfg.auto_coding_agent_review_auto_approval = args.auto_coding_agent_review_auto_approval
    cfg.create_issues = args.create_issues
    cfg.create_pr = args.create_pr
    cfg.enable_auto_merge = getattr(args, "enable_auto_merge", False)
    cfg.delete_local_merged_branch = getattr(args, "delete_local_merged_branch", True)
    cfg.verbose = args.verbose or not args.quiet  # verbose はデフォルト True; --quiet で抑制
    cfg.quiet = args.quiet
    cfg.show_stream = args.show_stream
    cfg.log_level = args.log_level
    cfg.no_color = True if getattr(args, "no_color", False) else None
    cfg.show_banner = getattr(args, "banner", None)
    cfg.screen_reader = getattr(args, "screen_reader", False)
    cfg.timestamp_style = getattr(args, "timestamp_style", "prefix")
    cfg.final_only = getattr(args, "final_only", False)

    # --- Workbench UI（Phase 5）---
    _wb_mode = getattr(args, "workbench", "auto")
    cfg.no_workbench = (_wb_mode == "off")
    # 優先順位: CLI 明示値 > 環境変数 HVE_WORKBENCH_BODY_LINES > 既定 10
    _wb_lines_raw = int(getattr(args, "workbench_body_lines", 10) or 10)
    import os as _os_wb
    _env_wb_lines = _os_wb.environ.get("HVE_WORKBENCH_BODY_LINES", "").strip()
    if _env_wb_lines and _wb_lines_raw == 10:
        try:
            _wb_lines_raw = int(_env_wb_lines)
        except ValueError:
            pass
    _wb_lines = max(10, min(20, _wb_lines_raw))
    if _wb_lines != _wb_lines_raw:
        import sys as _sys
        print(
            f"[hve] workbench body lines={_wb_lines_raw} を [10,20] にクランプ → {_wb_lines}",
            file=_sys.stderr,
        )
    cfg.workbench_body_lines = _wb_lines
    cfg.workbench_history = int(getattr(args, "workbench_history", 10000) or 10000)
    cfg.workbench_flush_on_exit = bool(getattr(args, "workbench_flush_on_exit", True))
    # --workbench {on,auto,off} のマッピング:
    #   off → cfg.no_workbench=True で起動を拑否
    #   auto → Console.workbench_enabled の自動判定（TTY/quiet/final_only/HVE_NO_WORKBENCH）
    #   on → auto と同じ起動判定を採りつつ、HVE_NO_WORKBENCH の拑否だけ解除する
    if _wb_mode == "on":
        import os as _os
        _os.environ.pop("HVE_NO_WORKBENCH", None)

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

    # Self-Improve 詳細オプション（auto_self_improve 有効時のみ反映）
    if cfg.auto_self_improve and not cfg.self_improve_skip:
        _si_iter = getattr(args, "self_improve_max_iterations", None)
        if _si_iter is not None:
            cfg.self_improve_max_iterations = int(_si_iter)
        _si_scope = getattr(args, "self_improve_target_scope", None)
        if _si_scope is not None:
            cfg.self_improve_target_scope = _si_scope
        _si_goal = getattr(args, "self_improve_goal", None)
        if _si_goal is not None:
            cfg.self_improve_goal = _si_goal

    # mdq リアルタイム索引更新: 優先順位 --no-mdq-watch > --mdq-watch > HVE_MDQ_WATCH > デフォルト True
    if getattr(args, "no_mdq_watch", False):
        cfg.mdq_watch = False
    elif getattr(args, "mdq_watch", None) is True:
        cfg.mdq_watch = True
    # debounce: CLI 引数 > 環境変数 > デフォルト
    _mdq_debounce = getattr(args, "mdq_watch_debounce_ms", None)
    if _mdq_debounce is not None:
        cfg.mdq_watch_debounce_ms = int(_mdq_debounce)

    # cq リアルタイム索引更新: 優先順位 --no-cq-watch > --cq-watch > HVE_CQ_WATCH > デフォルト True
    if getattr(args, "no_cq_watch", False):
        cfg.cq_watch = False
    elif getattr(args, "cq_watch", None) is True:
        cfg.cq_watch = True
    _cq_debounce = getattr(args, "cq_watch_debounce_ms", None)
    if _cq_debounce is not None:
        cfg.cq_watch_debounce_ms = int(_cq_debounce)

    if getattr(args, "fleet_mode_enabled", None) is not None:
        cfg.fleet_mode_enabled = bool(args.fleet_mode_enabled)

    if args.cli_path:
        cfg.cli_path = args.cli_path
    if args.cli_url:
        cfg.cli_url = args.cli_url

    # Cloud Sessions（CLI 明示値 > 環境変数 / SDKConfig.from_env）
    if getattr(args, "cloud_session_enabled", None) is not None:
        cfg.cloud_session_enabled = bool(args.cloud_session_enabled)
    if getattr(args, "cloud_session_owner", None):
        cfg.cloud_session_repository_owner = args.cloud_session_owner.strip() or None
    if getattr(args, "cloud_session_repository_name", None):
        cfg.cloud_session_repository_name = args.cloud_session_repository_name.strip() or None
    if getattr(args, "cloud_session_branch", None):
        cfg.cloud_session_repository_branch = args.cloud_session_branch.strip() or None
    if getattr(args, "cloud_session_max_concurrency", None) is not None:
        cfg.cloud_session_max_concurrency = max(1, int(args.cloud_session_max_concurrency))
    if getattr(args, "cloud_session_integration_id", None):
        cfg.cloud_session_integration_id = args.cloud_session_integration_id.strip() or None
        if cfg.cloud_session_integration_id:
            os.environ["GITHUB_COPILOT_INTEGRATION_ID"] = cfg.cloud_session_integration_id
    if getattr(args, "cloud_session_mc_base_url", None):
        cfg.cloud_session_mc_base_url = args.cloud_session_mc_base_url.strip() or None
        if cfg.cloud_session_mc_base_url:
            os.environ["COPILOT_MC_BASE_URL"] = cfg.cloud_session_mc_base_url
    if getattr(args, "cloud_session_step_overrides", None) is not None:
        cfg.cloud_session_step_overrides = _parse_bool_mapping(args.cloud_session_step_overrides)
    if getattr(args, "cloud_session_subtask_overrides", None) is not None:
        cfg.cloud_session_subtask_overrides = _parse_bool_mapping(args.cloud_session_subtask_overrides)

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
    if getattr(args, "auto_compaction", None) is not None:
        cfg.auto_compaction = bool(args.auto_compaction)
    if getattr(args, "tool_search", None) is not None:
        cfg.tool_search = bool(args.tool_search)
    if getattr(args, "tool_search_ranking", None):
        cfg.tool_search_ranking = str(args.tool_search_ranking)
    # AKM 入力ソースとしての Work IQ（独立フラグ）。
    # 明示指定（--workiq-akm-ingest / --no-workiq-akm-ingest）優先。
    # 未指定時は --sources に 'workiq' が含まれているかで自動判定する。
    _ingest_flag = getattr(args, "workiq_akm_ingest", None)
    _sources_raw = getattr(args, "sources", None) or ""
    _sources_has_workiq = "workiq" in [
        t.strip().lower() for t in _sources_raw.replace(" ", ",").split(",") if t.strip()
    ]
    if _ingest_flag is not None:
        cfg.workiq_akm_ingest_enabled = bool(_ingest_flag)
    elif _sources_has_workiq:
        cfg.workiq_akm_ingest_enabled = True
    # --workiq-dxx の解析（config 側のヘルパを再利用）。
    _dxx_raw = getattr(args, "workiq_dxx", None)
    if _dxx_raw is not None:
        try:
            from .config import _parse_workiq_akm_ingest_dxx as _parse_dxx  # type: ignore
        except ImportError:
            from config import _parse_workiq_akm_ingest_dxx as _parse_dxx  # type: ignore[no-redef]
        cfg.workiq_akm_ingest_dxx = _parse_dxx(_dxx_raw)
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
    _workiq_req_timeout = getattr(args, "workiq_request_timeout", None)
    if _workiq_req_timeout is not None and _workiq_req_timeout > 0:
        cfg.workiq_request_timeout = _workiq_req_timeout
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

def _validate_app_id_args(args: argparse.Namespace) -> Optional[str]:
    """Return a deterministic error for conflicting legacy and plural APP IDs."""
    raw_app_ids = getattr(args, "app_ids", None)
    legacy_app_id = getattr(args, "app_id", None)
    if not raw_app_ids or not legacy_app_id:
        return None
    selected = [item.strip() for item in raw_app_ids.split(",") if item.strip()]
    legacy = legacy_app_id.strip()
    if len(selected) != 1 or selected[0] != legacy:
        return "--app-id must match the one value specified by --app-ids."
    return None


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
        selected_app_ids = [
            s.strip() for s in args.app_ids.split(",") if s.strip()
        ]
        legacy_app_id = args.app_id.strip() if args.app_id else ""
        app_id_error = _validate_app_id_args(args)
        if app_id_error:
            raise ValueError(app_id_error)
        params["app_ids"] = selected_app_ids
        if len(params["app_ids"]) == 1:
            params["app_id"] = params["app_ids"][0]
    elif args.app_id:
        params["app_ids"] = [args.app_id.strip()]
        params["app_id"] = args.app_id  # 後方互換
    if args.resource_group:
        params["resource_group"] = args.resource_group
    for key in (
        "data_location",
        "data_resource_suffix",
        "data_vnet_cidr",
        "data_private_endpoint_subnet_cidr",
        "data_aci_subnet_cidr",
    ):
        value = getattr(args, key, None)
        if value is not None:
            params[key] = value
    if args.usecase_id:
        params["usecase_id"] = args.usecase_id

    # AKM 固有パラメータ
    if getattr(args, "workflow", None) == "akm":
        params["sources"] = getattr(args, "sources", None) or _AKM_DEFAULT_SOURCES
        target_files = getattr(args, "target_files", None)
        params["target_files"] = " ".join(target_files) if target_files else _default_akm_target_files(params["sources"])
        custom_source_dir = getattr(args, "custom_source_dir", None)
        params["custom_source_dir"] = " ".join(custom_source_dir) if custom_source_dir else ""
        # AKM では、フラグ未指定(None)の場合はデフォルトで False とする（差分マージ）
        force_refresh = getattr(args, "force_refresh", None)
        params["force_refresh"] = False if force_refresh is None else force_refresh
        params["enable_auto_merge"] = getattr(args, "enable_auto_merge", False)
        # Work IQ 取り込み対象 Dxx（--workiq-dxx）。
        # 文字列が渡された場合は orchestrator 側で正規化される。
        _dxx_raw = getattr(args, "workiq_dxx", None)
        if _dxx_raw:
            params["workiq_akm_ingest_dxx"] = _dxx_raw
    elif getattr(args, "workflow", None) == "aqod":
        params["target_scope"] = getattr(args, "target_scope", None) or _AQOD_DEFAULT_TARGET_SCOPE
        params["depth"] = getattr(args, "depth", None) or _AQOD_DEFAULT_DEPTH
        params["focus_areas"] = getattr(args, "focus_areas", None) or ""
    elif getattr(args, "workflow", None) == "ard":
        from datetime import date
        company_name = getattr(args, "company_name", None)
        target_business = getattr(args, "target_business", None) or ""
        requested_steps = list(params.get("steps") or [])
        # 4 グループ体系 ("1"/"2"/"3"/"4") を主とし、実 Step ID も許容する。
        # グループ ID は registry 侧の _WORKFLOW_GROUP_MAPS で実 Step ID に展開される:
        #   "1" → [1, 1.1, 1.2]、"2" → [2]、"3" → [2.1]、"4" → [3.1, 3.2, 3.3]
        _valid_step_ids = {"1", "2", "3", "4", "1.1", "1.2", "2.1", "3.1", "3.2", "3.3"}
        normalized_steps = requested_steps
        if requested_steps:
            invalid_steps = [sid for sid in requested_steps if sid not in _valid_step_ids]
            if invalid_steps:
                raise SystemExit(
                    f"ERROR: ARD の無効な --steps が指定されました: {', '.join(invalid_steps)} "
                    "(有効値: 1, 2, 3, 4 / 実 Step ID: 1.1, 1.2, 2.1, 3.1, 3.2, 3.3)"
                )
            normalized_steps = list(requested_steps)
            # 旧 実 Step ID '1.1' 指定時は Step '1' を自動前提として付与
            if "1.1" in normalized_steps and "1" not in normalized_steps:
                normalized_steps = ["1"] + normalized_steps
            params["steps"] = normalized_steps
        else:
            # 既定は Step 2/3/4（Step 1 は --steps で明示的に有効化する必要がある）。
            # help_content.py の説明（「既定で Step 2/3/4 が ON、Step 1 は明示的に有効化」）
            # および Autopilot 事前実行（素の `orchestrate --workflow ard`）の仕様に合わせる。
            normalized_steps = ["2", "3", "4"]
            params["steps"] = normalized_steps

        # グループ "1" または実 Step "1.1" / "1.2"（ARD グループ 1 系列）を含む場合は
        # company_name 必須。Step 1.2 は Step 1.1 (企業の事業分析) に依存するため。
        _requires_company = bool({"1", "1.1", "1.2"} & set(normalized_steps))
        if _requires_company and not company_name:
            raise SystemExit(
                "ERROR: ARD グループ 1（Step 1.1: 企業の事業分析 / Step 1.2 を含む）を実行する場合は --company-name が必須です"
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
        params["include_kpi_okr"] = bool(getattr(args, "include_kpi_okr", False))
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

    return params


# -----------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------

def _ensure_run_workdir_env() -> None:
    """orchestrate 限定で ``work/run/<run-id>/`` への env を注入する。

    既設定の ``HVE_WORK_ROOT`` は尊重する（GUI から子プロセスとして
    起動された場合や、テストでの override 用途）。``HVE_WORK_ROOT`` が
    既設定の場合、``HVE_RUN_ID`` の整合性は呼び出し側 (GUI / テスト) の責任。
    """
    if os.environ.get("HVE_WORK_ROOT"):
        return
    try:
        from .split_fork import resolve_run_id, resolve_work_root
    except ImportError:  # pragma: no cover - script execution path
        from split_fork import resolve_run_id, resolve_work_root  # type: ignore[no-redef]
    run_id = resolve_run_id()
    os.environ.setdefault("HVE_RUN_ID", run_id)
    work_root = resolve_work_root()
    os.environ["HVE_WORK_ROOT"] = str(work_root)
    work_root.mkdir(parents=True, exist_ok=True)


def main(argv: Optional[List[str]] = None) -> int:
    """エントリポイント。

    Returns:
        終了コード (0: 成功, 1: 失敗)
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "orchestrate":
        _ensure_run_workdir_env()
        return _cmd_orchestrate(args)

    if args.command == "qa-merge":
        return _cmd_qa_merge(args)

    if args.command == "workiq-doctor":
        return _cmd_workiq_doctor(args)

    if args.command == "emit-prompt":
        return _cmd_emit_prompt(args)

    if args.command == "gui":
        from .gui import run_gui
        return run_gui(args)

    if args.command == "cli":
        return _cmd_run_interactive(args)

    if args.command == "login":
        return _cmd_login(args)

    if args.command == "pricing":
        return _cmd_pricing(args)

    if args.command == "toolsearch":
        return _cmd_toolsearch(args)

    # 引数なし → GUI を既定として起動。PySide6 未導入時は CLI 対話ウィザードへ自動フォールバック。
    if args.command is None:
        try:
            from .gui import run_gui
        except ImportError as exc:
            print(
                f"{_ts()} ℹ️  PySide6 未導入のため CLI モードにフォールバックします。"
                f' GUI を使う場合は `pip install -e ".[gui]"` を実行してください。 ({exc})',
                file=sys.stderr,
            )
            return _cmd_run_interactive(args)
        return run_gui()

    # "run" サブコマンド → インタラクティブモード
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


def _run_copilot_auth_preflight(args: argparse.Namespace, config: "SDKConfig") -> bool:
    """orchestrate 実行前に GitHub Copilot 認証状態を確認する。

    ``--dry-run`` は SDK セッションを作らないため認証確認をスキップする。
    未認証かつ対話可能な場合だけ、ユーザー確認後に ``copilot login`` を実行する。
    """
    if getattr(config, "dry_run", False):
        return True

    try:
        from . import auth as _auth
    except ImportError:
        import auth as _auth  # type: ignore[no-redef]

    try:
        info = _auth.ensure_authenticated(interactive=False)
    except _auth.AuthError as exc:
        print(f"{_ts()} ❌ Copilot 認証状態を確認できません: {exc}", file=sys.stderr)
        return False

    if info.is_authenticated:
        return True

    if info.status_message:
        print(f"{_ts()} ⚠️  GitHub Copilot は未ログインです: {info.status_message}", file=sys.stderr)
    else:
        print(f"{_ts()} ⚠️  GitHub Copilot は未ログインです。", file=sys.stderr)

    interactive = bool(getattr(config, "force_interactive", False) or sys.stdin.isatty())
    if not interactive:
        print(f"{_ts()}    先に `hve login` を実行してから再試行してください。", file=sys.stderr)
        return False

    try:
        answer = input("今すぐ `copilot login` を実行しますか？ [Y/n]: ").strip().lower()
    except EOFError:
        print(f"{_ts()}    入力を取得できませんでした。先に `hve login` を実行してください。", file=sys.stderr)
        return False
    if answer not in ("", "y", "yes"):
        print(f"{_ts()}    ログインをキャンセルしました。", file=sys.stderr)
        return False

    try:
        info = _auth.ensure_authenticated(interactive=True)
    except _auth.AuthError as exc:
        print(f"{_ts()} ❌ Copilot ログインを開始できません: {exc}", file=sys.stderr)
        return False
    if info.is_authenticated:
        return True
    detail = f": {info.status_message}" if info.status_message else ""
    print(f"{_ts()} ❌ Copilot ログインが完了していません{detail}", file=sys.stderr)
    return False


def _is_workiq_requested(config: "SDKConfig") -> bool:
    """Work IQ を使う設定かを返す。"""
    return bool(
        getattr(config, "workiq_enabled", False)
        or getattr(config, "workiq_draft_mode", False)
        or config.is_workiq_qa_enabled()
        or config.is_workiq_akm_review_enabled()
        or config.is_workiq_akm_ingest_enabled()
    )


def _disable_workiq(config: "SDKConfig", params: Optional[dict] = None) -> None:
    """Work IQ 関連フラグを実行単位で無効化する。"""
    config.workiq_enabled = False
    config.workiq_qa_enabled = False
    config.workiq_akm_review_enabled = False
    config.workiq_akm_ingest_enabled = False
    config.workiq_draft_mode = False
    if params is not None:
        sources = str(params.get("sources") or "")
        if sources:
            kept = [part for part in sources.split(",") if part.strip().lower() != "workiq"]
            params["sources"] = ",".join(kept)
        params["workiq_akm_ingest_dxx"] = []
        params["ard_workiq_enabled"] = False


def _run_workiq_auth_preflight(
    args: argparse.Namespace,
    config: "SDKConfig",
    params: Optional[dict] = None,
) -> bool:
    """Work IQ 使用時に EULA / M365 認証を本処理前に確認する。"""
    if getattr(config, "dry_run", False) or not _is_workiq_requested(config):
        return True

    try:
        from .workiq import workiq_login
    except ImportError:
        from workiq import workiq_login  # type: ignore[no-redef]

    class _Console:
        @staticmethod
        def warning(message: str) -> None:
            print(f"{_ts()} ⚠️  {message}", file=sys.stderr)

    if workiq_login(_Console()):  # type: ignore[arg-type]
        return True

    interactive = bool(getattr(config, "force_interactive", False) or sys.stdin.isatty())
    if not interactive:
        print(f"{_ts()} ❌ Work IQ 認証確認に失敗しました。", file=sys.stderr)
        print(f"{_ts()}    先に `python -m hve workiq-doctor` で診断してください。", file=sys.stderr)
        return False

    try:
        answer = input("Work IQ を無効化して続行しますか？ [y/N]: ").strip().lower()
    except EOFError:
        return False
    if answer in ("y", "yes"):
        _disable_workiq(config, params)
        return True
    return False


def _is_azure_auth_requested(config: "SDKConfig", params: dict) -> bool:
    """Azure CLI 認証を必要とする可能性がある設定かを返す。"""
    if str(params.get("resource_group") or "").strip():
        return True
    return any("azure" in str(name).lower() for name in (config.mcp_servers or {}).keys())


def _azure_account_available() -> bool:
    """Azure CLI がログイン済みかを確認する。"""
    az = shutil.which("az")
    if not az:
        return False
    try:
        proc = subprocess.run(
            [az, "account", "show", "--output", "none"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _run_azure_auth_preflight(args: argparse.Namespace, config: "SDKConfig", params: dict) -> bool:
    """Azure 利用時に Azure CLI 認証を本処理前に確認する。"""
    if getattr(config, "dry_run", False) or not _is_azure_auth_requested(config, params):
        return True
    if _azure_account_available():
        return True

    az = shutil.which("az")
    if not az:
        print(f"{_ts()} ❌ `az` が見つかりません。Azure CLI をインストールしてください。", file=sys.stderr)
        return False

    print(f"{_ts()} ⚠️  Azure CLI が未ログインです。", file=sys.stderr)
    interactive = bool(getattr(config, "force_interactive", False) or sys.stdin.isatty())
    if not interactive:
        print(f"{_ts()}    先に `az login` を実行してから再試行してください。", file=sys.stderr)
        return False
    try:
        answer = input("今すぐ `az login` を実行しますか？ [Y/n]: ").strip().lower()
    except EOFError:
        return False
    if answer not in ("", "y", "yes"):
        return False
    try:
        rc = subprocess.run([az, "login"], check=False).returncode
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"{_ts()} ❌ `az login` の実行に失敗しました: {exc}", file=sys.stderr)
        return False
    if rc != 0:
        print(f"{_ts()} ❌ `az login` が異常終了しました (exit={rc})", file=sys.stderr)
        return False
    return _azure_account_available()


# -----------------------------------------------------------------------
# pricing
# -----------------------------------------------------------------------

def _cmd_pricing(args: argparse.Namespace) -> int:
    """`hve pricing {show|refresh}` ハンドラー。

    show:    キャッシュ済み料金表を表示。無い/破損時のみ取得を試行。
    refresh: 強制再取得し、成功時のみキャッシュを上書き保存する。
    """
    try:
        from .pricing import (
            PricingFetchError,
            default_cache_path,
            fetch_copilot_pricing,
            load_cached_pricing,
            save_cached_pricing,
        )
    except ImportError:
        from pricing import (  # type: ignore[no-redef]
            PricingFetchError,
            default_cache_path,
            fetch_copilot_pricing,
            load_cached_pricing,
            save_cached_pricing,
        )

    sub = getattr(args, "pricing_command", None) or "show"
    cache_path = default_cache_path()

    if sub == "refresh":
        timeout = float(getattr(args, "timeout", 10.0))
        try:
            pricing = fetch_copilot_pricing(timeout=timeout)
        except PricingFetchError as exc:
            print(f"❌ 料金表の取得に失敗しました: {exc}", file=sys.stderr)
            return 1
        ok = save_cached_pricing(pricing, cache_path)
        print(
            f"✅ 取得完了 (status={pricing.status}, models={len(pricing.models)}, "
            f"plans={len(pricing.plans)}) → {cache_path} (saved={ok})"
        )
        return 0

    # show
    pricing = load_cached_pricing(cache_path)
    if pricing is None:
        print(f"ℹ️  キャッシュが見つかりません ({cache_path})。取得を試行します...")
        try:
            pricing = fetch_copilot_pricing()
        except PricingFetchError as exc:
            print(f"❌ 取得に失敗しました: {exc}", file=sys.stderr)
            return 1
        save_cached_pricing(pricing, cache_path)

    if getattr(args, "json", False):
        print(json.dumps(pricing.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"# GitHub Copilot 料金表")
    print(f"- fetched_at : {pricing.fetched_at}")
    print(f"- status     : {pricing.status}")
    print(f"- source     :")
    for k, v in (pricing.source_urls or {}).items():
        print(f"    - {k}: {v}")
    print(f"\n## モデル別 multiplier ({len(pricing.models)})")
    for m in sorted(pricing.models.values(), key=lambda x: x.model_id):
        mult = "?" if m.multiplier is None else f"{m.multiplier}x"
        print(f"  - {m.model_id:<35} multiplier={mult}")
    print(f"\n## プラン ({len(pricing.plans)})")
    for p in sorted(pricing.plans.values(), key=lambda x: x.plan_id):
        addl = "?" if p.additional_request_usd is None else f"${p.additional_request_usd}"
        monthly = "?" if p.monthly_usd is None else f"${p.monthly_usd}"
        print(
            f"  - {p.plan_id:<22} monthly={monthly:<8} "
            f"included={p.included_premium_requests} additional={addl}"
        )
    return 0


def _cmd_toolsearch(args: argparse.Namespace) -> int:
    """`hve toolsearch dashboard` ハンドラー（FR-TS-10）。

    収集済みイベント（FR-TS-09）と利用履歴（FR-TS-07）だけから集計する。
    ネットワークへは接続しない。
    """
    try:
        from .toolsearch import dashboard as ts_dashboard
    except ImportError:
        from toolsearch import dashboard as ts_dashboard  # type: ignore[no-redef]

    sub = getattr(args, "toolsearch_command", None) or "dashboard"
    if sub != "dashboard":
        print(f"❌ 未知のサブコマンドです: {sub}", file=sys.stderr)
        return 2

    events_path = getattr(args, "events", None)
    usage_path = getattr(args, "usage", None)
    since = getattr(args, "since", None)

    if getattr(args, "follow", False):
        return ts_dashboard.run_live(
            events_path=events_path,
            usage_path=usage_path,
            since=since,
            interval=float(getattr(args, "interval", 2.0)),
            width=ts_dashboard.terminal_width(),
        )

    snapshot = ts_dashboard.build_dashboard(
        events_path=events_path,
        usage_path=usage_path,
        since=since,
        top=int(getattr(args, "top", 10)),
    )

    html_out = getattr(args, "html", None)
    if html_out:
        target = Path(html_out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ts_dashboard.render_html(snapshot), encoding="utf-8")
        except OSError as exc:
            print(f"❌ HTML を書き出せませんでした: {exc}", file=sys.stderr)
            return 1
        print(f"✅ {target}")

    if getattr(args, "json", False):
        print(ts_dashboard.render_json(snapshot))
    elif not html_out:
        print(ts_dashboard.render_text(snapshot, width=ts_dashboard.terminal_width()))

    if snapshot.queries == 0:
        print(
            "\nℹ️  イベントがまだありません。"
            " `--tool-search --tool-search-ranking hve` を付けて実行すると収集が始まります。",
            file=sys.stderr,
        )
    return 0


def _cmd_login(args: argparse.Namespace) -> int:
    """`hve login` ハンドラー: GitHub Copilot ログイン + モデル一覧キャッシュ更新。

    --status 指定時はログインを起動せず、現在の認証状態とキャッシュ状態のみ表示する。
    """
    try:
        from . import auth as _auth
        from . import models_api as _models_api
        from . import models_cache as _models_cache
    except ImportError:
        import auth as _auth  # type: ignore[no-redef]
        import models_api as _models_api  # type: ignore[no-redef]
        import models_cache as _models_cache  # type: ignore[no-redef]

    # --- --status: 認証状態とキャッシュ状態を表示して終了 ---
    if getattr(args, "status", False):
        print(f"{_ts()} 🔍 認証状態を確認中...")
        info = _auth.get_auth_status()
        if info.is_authenticated:
            print(f"  ✅ ログイン済み: {info.login or '(unknown)'}")
            if info.copilot_plan:
                print(f"     プラン: {info.copilot_plan}")
            if info.host:
                print(f"     ホスト: {info.host}")
        else:
            print(f"  ❌ 未ログイン")
            if info.status_message:
                print(f"     詳細: {info.status_message}")
            print(f"     ヒント: `hve login` でログインしてください。")

        cache_path = _models_cache.get_cache_path()
        cached = _models_cache.load(allow_stale=True)
        if cached:
            from datetime import datetime as _dt
            ts = _dt.fromtimestamp(cached.fetched_at).strftime("%Y-%m-%d %H:%M:%S")
            fresh = _models_cache.is_fresh(cached)
            print(
                f"\n  📦 モデルキャッシュ: {len(cached.models)} 件 "
                f"({'fresh' if fresh else 'stale'}, 取得: {ts})"
            )
            print(f"     {cache_path}")
        else:
            print(f"\n  📦 モデルキャッシュ: なし ({cache_path})")
        return 0 if info.is_authenticated else 1

    # --- 通常: copilot login 起動 ---
    print(f"{_ts()} 🔐 GitHub Copilot へログインします...")
    print(f"   ブラウザでデバイスフロー認証が開かれます。")

    try:
        rc = _auth.run_login(host=args.host)
    except _auth.AuthError as exc:
        print(f"{_ts()} ❌ ログイン失敗: {exc}", file=sys.stderr)
        return 2

    if rc != 0:
        print(f"{_ts()} ❌ copilot login が異常終了しました (exit={rc})", file=sys.stderr)
        return rc

    print(f"{_ts()} ✅ ログイン完了")

    # --- 認証状態の検証 ---
    info = _auth.get_auth_status()
    if info.is_authenticated and info.login:
        print(f"   ユーザー: {info.login}"
              + (f" (プラン: {info.copilot_plan})" if info.copilot_plan else ""))

    # --- モデル一覧取得 + キャッシュ書込 ---
    if getattr(args, "skip_fetch", False):
        print(f"{_ts()} ⏭️  --skip-fetch 指定のためモデル一覧取得をスキップしました。")
        return 0

    print(f"{_ts()} 📥 利用可能なモデル一覧を取得中...")
    try:
        entries = _models_api.fetch_model_entries()
    except _models_api.ModelsAPIError as exc:
        print(f"{_ts()} ⚠️  モデル一覧取得に失敗しました: {exc}", file=sys.stderr)
        print("     `hve` 実行時はフォールバック一覧が使用されます。")
        return 0  # ログイン自体は成功しているため非エラー終了

    models = [e.id for e in entries]
    if not models:
        print(f"{_ts()} ⚠️  モデル一覧が空でした。フォールバック一覧が使用されます。")
        return 0

    try:
        path = _models_cache.save_entries(entries)
        print(f"{_ts()} 💾 {len(models)} 件のモデルをキャッシュに保存しました。")
        print(f"     {path}")
    except OSError as exc:
        print(f"{_ts()} ⚠️  キャッシュ書込失敗 (処理は続行): {exc}", file=sys.stderr)

    return 0


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
    is_agent_self_improve_default = wf.id in {"aag", "aagd"}
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

    # ── 実行モード選択（Phase B: 早期分岐） ─────────────────
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

    # モデル選択 (Phase C) は分岐内でそれぞれ実行する:
    #   - クイック全自動: メインモデルのみ即座に選択 (QA/Review 別モデルは既定 OFF)
    #   - カスタム全自動 / 手動: Phase A' (機能要件詳細) の後にメイン/QA/Review をまとめて選択
    # モデル一覧はキャッシュ→SDK→フォールバックの順で動的取得 (Phase 3 で追加)
    # 取得失敗 / 戻り値が想定外型の場合は静的フォールバック ([MODEL_AUTO, *MODEL_CHOICES]) を使用する。
    model_options: list = [MODEL_AUTO, *MODEL_CHOICES]
    try:
        try:
            from .config import get_model_choices as _get_model_choices
        except ImportError:
            from config import get_model_choices as _get_model_choices  # type: ignore[no-redef]
        _dynamic = _get_model_choices(include_auto=True)
        # 受け取りは list[str] のみ採用 (test_main.py の mock_config_mod 経由で MagicMock が来る場合をガード)
        if isinstance(_dynamic, list) and _dynamic and all(isinstance(x, str) for x in _dynamic):
            model_options = _dynamic
    except Exception:
        # 動的取得が何らかの理由で失敗しても静的フォールバックで続行
        pass
    model = None
    model_display = None
    review_model = None
    review_model_display = None
    qa_model = None
    qa_model_display = None

    workiq_additional_prompt = ""
    ard_workiq_enabled = False

    # ── オプション設定 ────────────────────────────────────
    if is_quick_auto:
        # クイック全自動: ステップ5〜7aをデフォルト値で自動設定
        # ── Phase C (クイック全自動): メインモデルのみ選択 ────
        model_idx = con.menu_select("使用するモデルを選択", model_options, default_index=0)
        model, model_display = _resolve_model(model_options[model_idx])
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
        # クイック全自動モードでは AKM 入力としての Work IQ も既定 OFF（明示要求なし）。
        workiq_akm_ingest_enabled = False
        workiq_akm_ingest_dxx: list = []
        workiq_draft_mode = False
        workiq_per_question_timeout = 1200.0
        workiq_request_timeout = 300.0
        issue_title = ""
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
            params_extra.update(
                _collect_generic_workflow_params(
                    con,
                    wf,
                    is_quick_auto=True,
                    selected_step_ids=selected_step_ids,
                )
            )
        # Agentic Retrieval 設定（AAD-WEB / ASDW-WEB）
        _agentic_answers: dict = {}
        if wf.id in ("aad-web", "asdw-web"):
            _agentic_answers = _collect_agentic_retrieval_wizard_answers(con, wf.id, is_quick_auto=True)
        additional_prompt = None
        # AAG/AAGDはPost-DAG Self-Improve既定ON。他workflowは従来どおりOFF。
        auto_self_improve = is_agent_self_improve_default
        self_improve_explicit_opt_out = False
        self_improve_max_iterations = 3
        self_improve_target_scope = ""
        self_improve_goal = ""
        _disc_goal = None
        _disc_criteria = None
    else:
        # カスタム全自動 or 手動: 既存のインタラクティブ入力フロー
        # プロンプト順序は以下の Phase に再編済み:
        #   Phase A': 機能要件 詳細（ワークフロー固有 / Agentic / 追加プロンプト）
        #   Phase C : モデル群（メイン / QA 別モデル / Review 別モデル）
        #   Phase D : 出力・リソース（verbosity / timeout / branch / max_parallel）
        #   Phase E : 自動化補助（QA / Review / Work IQ / Code Review / 自己改善）
        #   Phase F : GitHub 連携（Issue / PR / repo / auto-merge）
        #   Phase G : dry_run

        # ── Phase A': 機能要件 詳細 ───────────────────────────
        # ── ワークフロー固有パラメータ ────────────────────────
        # PR 作成有無に依存する AKM の auto-merge プロンプトは Phase F で個別に扱う。
        params_extra: dict = {}
        if is_akm:
            params_extra.update(
                _prompt_akm_params(
                    con,
                    is_quick_auto=False,
                    will_create_pr=False,
                )
            )
        elif is_aqod:
            params_extra["target_scope"] = con.prompt_input(
                _PARAM_PROMPT_LABELS["target_scope"], default=_AQOD_DEFAULT_TARGET_SCOPE
            )
            params_extra["depth"] = _prompt_valid_aqod_depth(con)
            params_extra["focus_areas"] = con.prompt_input(_PARAM_PROMPT_LABELS["focus_areas"], default="")
        elif is_ard:
            _ard_wf_params, _ard_steps = _collect_ard_wizard_params(con, is_quick_auto=False)
            params_extra.update(_ard_wf_params)
            selected_step_ids = _ard_steps
        else:
            params_extra.update(
                _collect_generic_workflow_params(
                    con,
                    wf,
                    is_quick_auto=False,
                    selected_step_ids=selected_step_ids,
                )
            )
        # Agentic Retrieval 設定（AAD-WEB / ASDW-WEB）
        _agentic_answers: dict = {}
        if wf.id in ("aad-web", "asdw-web"):
            _agentic_answers = _collect_agentic_retrieval_wizard_answers(con, wf.id, is_quick_auto=False)

        # ── 追加プロンプト ────────────────────────────────────
        additional_prompt = con.prompt_input("全てのステップでの Prompt の末尾に追加するプロンプト（省略可）")

        # ── Phase C: メインモデル選択のみ ─────────────────────
        # QA 用 / Review 用の別モデル選択は Phase E に移動し、
        # 各機能（auto_qa / auto_review / auto_coding_agent_review）が ON のときだけ尋ねる。
        # OFF のときは Phase 冒頭の初期値（qa_model = None, review_model = None; 行 2357-2360）が維持される。
        model_idx = con.menu_select("使用するモデルを選択", model_options, default_index=0)
        model, model_display = _resolve_model(model_options[model_idx])

        # ── Phase D: 出力・リソース ────────────────────────────
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

        branch = con.prompt_input("ベースブランチ", default="main")
        if is_single_step_workflow:
            max_parallel = 1
        else:
            max_parallel = int(con.prompt_input("並列実行数", default="15") or "15")

        # ── Phase E: 自動化補助 ────────────────────────────────
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
                    # QA 有効時のみ QA 用モデルを尋ねる（Phase C から移設）。
                    use_different_qa_model = con.prompt_yes_no(
                        "QA にメインモデルとは別のモデルを使う？（n の場合、未指定なら環境変数 QA_MODEL を使用）",
                        default=False,
                    )
                    if use_different_qa_model:
                        qa_model_idx = con.menu_select("QA 用モデルを選択", model_options)
                        qa_model, qa_model_display = _resolve_model(model_options[qa_model_idx])
                        if qa_model == model:
                            qa_model = None
                            qa_model_display = None
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
                # QA 有効時のみ QA 用モデルを尋ねる（Phase C から移設）。
                use_different_qa_model = con.prompt_yes_no(
                    "QA にメインモデルとは別のモデルを使う？（n の場合、未指定なら環境変数 QA_MODEL を使用）",
                    default=False,
                )
                if use_different_qa_model:
                    qa_model_idx = con.menu_select("QA 用モデルを選択", model_options)
                    qa_model, qa_model_display = _resolve_model(model_options[qa_model_idx])
                    if qa_model == model:
                        qa_model = None
                        qa_model_display = None
            else:
                qa_answer_mode = None
                force_interactive = False
            # Review 自動投入 ON/OFF のみ Phase E で尋ねる。Review 用モデルは
            # Code Review Agent ブロックの直後で（いずれかが y のときだけ）まとめて尋ねる。
            auto_review = con.prompt_yes_no("Review 自動投入を有効にする？", default=False)

        # ── Work IQ 連携 ──────────────────────────────────────
        workiq_enabled = False
        workiq_qa_enabled = False
        workiq_akm_review_enabled = False
        # Sub-C-2: AKM 入力ソースとしての Work IQ。
        # params_extra["sources"] に "workiq" が含まれていれば自動 ON とする。
        # （独立フラグ。`workiq_akm_review_enabled`（DAG 後検証）とは別軸。）
        workiq_akm_ingest_enabled = bool(
            is_akm and "workiq" in (params_extra.get("sources", "") or "").split(",")
        )
        workiq_akm_ingest_dxx = list(params_extra.get("workiq_akm_ingest_dxx", []) or [])
        workiq_draft_mode = False
        _show_workiq_option = auto_qa or is_akm or is_ard
        workiq_per_question_timeout = 1200.0
        workiq_request_timeout = 300.0

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
            workiq_enabled = (
                workiq_qa_enabled or workiq_akm_review_enabled or workiq_akm_ingest_enabled
            )
            if workiq_enabled:
                con.spinner_start("Work IQ へのログイン中...")
                login_ok = workiq_login(con)
                con.spinner_stop()
                if not login_ok:
                    con.warning(
                        "Work IQ へのログインに失敗しました。Work IQ 連携を無効にします。"
                    )
                    workiq_enabled = False
                    # 入力フェーズも login 失敗時は OFF にする（独立フラグだが Work IQ 認証が必須のため）。
                    workiq_akm_ingest_enabled = False
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
                    _wiq_req_timeout_str = con.prompt_input(
                        "Work IQ Request Timeout（秒。MCP ツール呼び出し 1 回あたり。デフォルト: 300 = 5 分）",
                        default="300",
                    )
                    try:
                        workiq_request_timeout = float(_wiq_req_timeout_str or "300")
                    except ValueError:
                        con.warning("無効な値のため、デフォルトの 300 秒（5 分）を使用します。")
                        workiq_request_timeout = 300.0
                    if workiq_request_timeout <= 0:
                        con.warning("0 以下の値は無効なため、デフォルトの 300 秒（5 分）を使用します。")
                        workiq_request_timeout = 300.0

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

        # ── Review 用モデル選択（Phase C から移設）────────────
        # auto_review（敵対的レビュー）と auto_coding_agent_review は SDKConfig.review_model を共有する。
        # いずれか一方でも y のときだけ 1 回だけ尋ねる。両方 n なら初期値（None）を維持。
        if auto_review or auto_coding_agent_review:
            use_different_review_model = con.prompt_yes_no(
                "Review / Code Review Agent にメインモデルとは別のモデルを使う？（n の場合、未指定なら環境変数 REVIEW_MODEL を使用）",
                default=False,
            )
            if use_different_review_model:
                review_model_idx = con.menu_select("レビュー用モデルを選択", model_options)
                review_model, review_model_display = _resolve_model(model_options[review_model_idx])
                if review_model == model:
                    review_model = None
                    review_model_display = None

        # ── 自己改善ループ ────────────────────────────────────
        if is_agent_self_improve_default:
            self_improve_explicit_opt_out = con.prompt_yes_no(
                "AAG/AAGD 既定の自己改善ループを無効化する？（緊急opt-out）",
                default=False,
            )
            auto_self_improve = not self_improve_explicit_opt_out
        else:
            auto_self_improve = con.prompt_yes_no(
                "自己改善ループを有効にする？",
                default=False,
            )
            # 対話でNoを選んだ場合は環境変数より強い明示OFFとして扱う。
            self_improve_explicit_opt_out = not auto_self_improve
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

        # ── Phase F: GitHub 連携 ──────────────────────────────
        create_issues = con.prompt_yes_no("GitHub Issue を作成する？", default=False)
        create_pr = con.prompt_yes_no("GitHub PR を作成する？", default=False) if not create_issues else True
        issue_title = ""
        if create_issues:
            issue_title = con.prompt_input(
                _PARAM_PROMPT_LABELS["issue_title"],
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

        # Phase F の選択結果を params_extra に反映
        if is_akm:
            params_extra["enable_auto_merge"] = akm_enable_auto_merge
        if is_ard:
            params_extra["ard_workiq_enabled"] = ard_workiq_enabled
        if issue_title:
            params_extra["issue_title"] = issue_title

        # ── Phase G: 実行計画プレビュー ────────────────────────
        dry_run = con.prompt_yes_no("実行計画のプレビュー（実際の SDK 呼び出しをせず、DAG の実行計画のみ表示）？", default=False)

    # ── Phase H: ワークベンチ UI 起動有無（全モード共通）──────
    # ウィザード末尾で 4 ペイン固定レイアウト UI（Workbench）を起動するか確認する。
    # 既定 Yes。No の場合は cfg.no_workbench=True を設定し、`--workbench off` 相当の動作になる。
    # TTY / quiet / final_only / HVE_NO_WORKBENCH=1 等での自動降格条件は orchestrator/Console 側に従う。
    enable_workbench = con.prompt_yes_no(
        "ワークベンチ（4 ペイン UI）を起動しますか？",
        default=True,
    )

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
            summary_lines.append(f"Work IQ 取込 : {'ON' if workiq_akm_ingest_enabled else 'OFF'}")
            if workiq_akm_ingest_enabled and workiq_akm_ingest_dxx:
                summary_lines.append(
                    f"Work IQ 取込 Dxx: {','.join(workiq_akm_ingest_dxx)}"
                )
            elif workiq_akm_ingest_enabled:
                summary_lines.append("Work IQ 取込 Dxx: 全件（D01〜D21）")
        else:
            summary_lines.append(f"Work IQ     : {s.GREEN}ON{s.RESET}")
            summary_lines.append(f"Work IQ Draft: {'ON' if workiq_draft_mode else 'OFF'}")
        if workiq_additional_prompt:
            summary_lines.append(f"Work IQ Prompt: {workiq_additional_prompt[:50]}{'...' if len(workiq_additional_prompt) > 50 else ''}")
        summary_lines.append(f"Work IQ タイムアウト: {workiq_per_question_timeout:.0f} 秒")
        summary_lines.append(f"Work IQ Request Timeout: {workiq_request_timeout:.0f} 秒")
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
        f"ワークベンチ : {'ON' if enable_workbench else 'OFF'}",
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
    cfg.workiq_enabled = workiq_enabled
    cfg.workiq_qa_enabled = workiq_qa_enabled
    cfg.workiq_akm_review_enabled = workiq_akm_review_enabled
    cfg.workiq_akm_ingest_enabled = workiq_akm_ingest_enabled
    cfg.workiq_akm_ingest_dxx = list(workiq_akm_ingest_dxx or [])
    cfg.workiq_draft_mode = workiq_draft_mode
    cfg.workiq_draft_output_dir = "qa"
    cfg.workiq_per_question_timeout = workiq_per_question_timeout
    cfg.workiq_request_timeout = workiq_request_timeout
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
    # ウィザード末尾の「ワークベンチを起動しますか？」選択を反映
    # （Yes → cfg.no_workbench=False で既定挙動 / No → True で `--workbench off` 相当）
    cfg.no_workbench = not enable_workbench
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
    if self_improve_explicit_opt_out:
        cfg.auto_self_improve = False
        cfg.self_improve_skip = True
    elif auto_self_improve:
        cfg.auto_self_improve = True
        cfg.self_improve_skip = False
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

    # CLI フラグはウィザード回答より優先する（非対話実行での明示指定を成立させる）。
    _apply_agentic_retrieval_cli_overrides(cfg, args)

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

    if not _run_copilot_auth_preflight(args or argparse.Namespace(command="cli"), cfg):
        return 1

    if not _run_workiq_auth_preflight(args or argparse.Namespace(command="cli"), cfg, params):
        return 1

    if not _run_azure_auth_preflight(args or argparse.Namespace(command="cli"), cfg, params):
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
    # T-H1H2b: strict 停止 (status=blocked) を error より先に判定し、
    # failed と区別された「停止」として表示する。
    if result.get("blocked"):
        blocked_items = [str(item) for item in result.get("blocked", [])]
        blocked_label = (
            "Post-DAG Self-Improve が成功条件を満たさなかったため停止しました"
            if "self-improve" in blocked_items
            else "ワークフローは必須条件を満たさなかったため停止しました"
        )
        con._print(
            f"\n  {s.YELLOW}⏸ {blocked_label}"
            f"（status=blocked）。{s.RESET}",
            ts=False,
        )
        if result.get("error"):
            con._print(f"  {result['error']}", ts=False)
        return 1
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
        from .config import SDKConfig, normalize_model
        from .console import Console
    except ImportError:
        from config import SDKConfig, normalize_model  # type: ignore[no-redef]
        from console import Console  # type: ignore[no-redef]

    try:
        try:
            import copilot  # noqa: F401  # type: ignore[import]
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

        try:
            from .copilot_client_factory import create_copilot_client
        except ImportError:
            from copilot_client_factory import create_copilot_client  # type: ignore[no-redef]
        client = create_copilot_client(
            cli_path=cfg.cli_path,
            github_token=cfg.resolve_token() or None,
            log_level="error",
        )

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


def _cmd_orchestrate_autopilot_chain(args: argparse.Namespace) -> int:
    """orchestrate --autopilot-chain サブコマンドのハンドラー（Qt 非依存）。"""
    try:
        from .autopilot import (
            AutopilotSelection,
            build_plan,
            default_catalog_path,
        )
        from .autopilot.cli_runner import CliAutopilotRunner
    except ImportError:
        from autopilot import (  # type: ignore[no-redef]
            AutopilotSelection,
            build_plan,
            default_catalog_path,
        )
        from autopilot.cli_runner import CliAutopilotRunner  # type: ignore[no-redef]

    chain_raw: str = args.autopilot_chain
    chain_ids = [w.strip() for w in chain_raw.split(",") if w.strip()]
    if not chain_ids:
        print(
            f"{_ts()} ❌ --autopilot-chain に有効な workflow ID が含まれていません: {chain_raw!r}",
            file=sys.stderr,
        )
        return 1

    # selection は workflow ID リストから構築（未対応 ID は ignored_workflows へ）
    selection = AutopilotSelection.from_workflow_ids(chain_ids)
    if selection.ignored_workflows:
        print(
            f"{_ts()} ⚠️  --autopilot-chain の未対応 workflow ID を無視します: "
            f"{','.join(selection.ignored_workflows)}",
            file=sys.stderr,
        )

    # カタログパス解決
    repo_root = Path.cwd()
    if args.autopilot_catalog:
        catalog_path = Path(args.autopilot_catalog)
        if not catalog_path.is_absolute():
            catalog_path = repo_root / catalog_path
    else:
        catalog_path = default_catalog_path(repo_root)

    # ユーザー指定の --app-ids を Autopilot 計画にも反映する（未指定なら catalog 全件）。
    # --app-id（単数、後方互換）でも同様に動作させる。
    requested_app_ids: Optional[List[str]] = None
    raw_app_ids = getattr(args, "app_ids", None) or getattr(args, "app_id", None)
    if raw_app_ids:
        requested_app_ids = [s.strip() for s in raw_app_ids.split(",") if s.strip()] or None

    plan = build_plan(
        catalog_path,
        max_parallel=args.autopilot_max_parallel,
        selection=selection,
        requested_app_ids=requested_app_ids,
    )

    # 計画サマリ出力
    print(f"{_ts()} 🤖 Autopilot Chain Plan")
    print(f"  catalog: {plan.catalog_path}")
    print(f"  catalog_exists: {plan.catalog_exists}")
    print(f"  requires_aas: {plan.requires_aas}")
    print(f"  max_parallel: {plan.max_parallel}")
    print(f"  pre_phases: {plan.pre_phases}")
    print(f"  main_workflows: {plan.main_workflows}")
    print(f"  ignored_workflows: {plan.ignored_workflows}")
    print(f"  app_chains ({len(plan.app_chains)}):")
    for ch in plan.app_chains:
        print(f"    - {ch.app_id} [{ch.architecture}] → {','.join(ch.workflows)}")
    if plan.skipped:
        print(f"  skipped ({len(plan.skipped)}):")
        for sk in plan.skipped:
            print(f"    - {sk.app_id} [{sk.architecture}] reason={sk.reason}")

    if args.autopilot_dry_run:
        print(f"{_ts()} ✅ --autopilot-dry-run: 計画のみ表示しました。")
        return 0

    if plan.is_empty():
        if plan.requires_aas:
            print(
                f"{_ts()} ❌ Autopilot 実行には AAS（App Architecture Design）の出力カタログが必要です。"
                f"\n   先に `python -m hve orchestrate --workflow aas` を実行してください。",
                file=sys.stderr,
            )
            return 1
        print(
            f"{_ts()} ⚠️  実行対象の APP チェーンがありません。",
            file=sys.stderr,
        )
        return 0

    runner = CliAutopilotRunner(
        plan,
        progress_callback=lambda done, total: print(
            f"{_ts()} progress: {done}/{total}"
        ),
    )
    summary = runner.run()
    print(
        f"{_ts()} Autopilot result: completed={summary.completed_apps}/{summary.total_apps}"
        f" aborted={len(summary.aborted_apps)}"
    )
    print(f"{_ts()} {runner.runtime_summary()}")
    if summary.aborted_apps:
        for app_id in summary.aborted_apps:
            print(
                f"  - aborted: {app_id} (exit={summary.aborted_codes.get(app_id)})",
                file=sys.stderr,
            )
        return 1
    return 0


def _cmd_orchestrate(args: argparse.Namespace) -> int:
    """orchestrate サブコマンドのハンドラー。"""
    # HVE CLI Orchestrator 実行配下シグナルは OrchestratorContext を明示引数で
    # 伝播させる方式へ移行済み（copilot-instructions.md §0 Orchestrator 例外）。
    # 環境変数 `HVE_ORCHESTRATOR_ACTIVE` は使用しない。

    # --autopilot-chain と --workflow の排他チェック
    _autopilot_chain_raw = getattr(args, "autopilot_chain", None)
    if _autopilot_chain_raw and args.workflow:
        print(
            f"{_ts()} ❌ --autopilot-chain と --workflow は同時に指定できません。",
            file=sys.stderr,
        )
        return 1
    _app_id_error = _validate_app_id_args(args)
    if _app_id_error:
        print(f"{_ts()} ❌ {_app_id_error}", file=sys.stderr)
        return 1
    if _autopilot_chain_raw:
        return _cmd_orchestrate_autopilot_chain(args)
    if not args.workflow:
        print(
            f"{_ts()} ❌ --workflow または --autopilot-chain のいずれかを指定してください。",
            file=sys.stderr,
        )
        return 1

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

    try:
        from .orchestrator_context import OrchestratorContext
    except ImportError:
        from orchestrator_context import OrchestratorContext  # type: ignore[no-redef]

    config = _build_config(args)
    try:
        params = _build_params(args)
    except ValueError as exc:
        print(f"{_ts()} ❌ {exc}", file=sys.stderr)
        return 1

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

    if not _run_copilot_auth_preflight(args, config):
        return 1

    if not _run_workiq_auth_preflight(args, config, params):
        return 1

    if not _run_azure_auth_preflight(args, config, params):
        return 1

    # HVE CLI Orchestrator 配下シグナル: OrchestratorContext を生成して伝播。
    # `HVE_ORCHESTRATOR_ACTIVE` 環境変数は撤廃済み。
    # local 実行モード既定で continue_on_error=True、`--strict` でオプトアウト。
    # SPLIT_REQUIRED の subissues.md → Sub-Issue 作成は Cloud Agent Orchestrator
    # (Issue Template + GitHub Actions) の責務。CLI / GUI 標準経路では legacy
    # runtime split-fork を明示的に無効化し、DAG/fan-out 実行に集約する。
    _strict = bool(getattr(args, "strict", False))
    orchestrator_ctx = OrchestratorContext(
        run_id=config.run_id or "",
        split_fork_enabled=False,
        continue_on_error=not _strict,
    )

    result = asyncio.run(
        run_workflow(
            workflow_id=args.workflow,
            params=params,
            config=config,
            orchestrator_ctx=orchestrator_ctx,
        )
    )

    # 終了コード判定
    # T-H1H2b: blocked は failed と区別された「停止」として優先判定する。
    # stderr に明示ログを出して subprocess 経由の上位レイヤーが識別できるようにする。
    if result.get("blocked"):
        blocked_items = [str(item) for item in result.get("blocked", [])]
        blocked_label = (
            "Post-DAG Self-Improve が成功条件を満たさなかったため停止しました"
            if "self-improve" in blocked_items
            else "ワークフローは必須条件を満たさなかったため停止しました"
        )
        print(
            f"{_ts()} ⏸  {blocked_label}（status=blocked）。",
            file=sys.stderr,
        )
        if result.get("error"):
            print(f"{_ts()}    {result['error']}", file=sys.stderr)
        return 1
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


def _console_main() -> int:
    """``hve`` console script のエントリポイント。

    ``python -m hve`` と同じように .venv への再 exec を先に試みる。
    ``main()`` 自体はライブラリ用途 (テスト等) でも呼ばれるため、
    再 exec はここと ``__main__`` ブロックに限定する。
    """
    _reexec_in_venv_if_needed()
    return main()


if __name__ == "__main__":
    sys.exit(_console_main())
