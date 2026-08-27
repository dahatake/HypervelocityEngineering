"""template_engine.py — テンプレート読み込み・プレースホルダ展開

旧 `.github/cli/orchestrate.py` のテンプレートエンジン関連関数を移植したもの。
Step body は `.github/prompts/steps/` にあり、path 解決は `prompt_loader` の単一実装へ委譲する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level `import template_engine` compatibility
    from prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]

try:
    from .workflow_registry import WorkflowDef, canonicalize_workflow_id
except ImportError:  # pragma: no cover - top-level `import template_engine` compatibility
    from workflow_registry import WorkflowDef, canonicalize_workflow_id  # type: ignore[import-not-found,no-redef]

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# target_files 系ワークフローのデフォルト対象ファイル。
# ここで指定するパターンは orchestrator 側の glob 展開で評価される。
# `qa/*.md` は単一階層、`docs-original/*` は直下エントリを既定とする。
_DEFAULT_TARGET_FILES: Dict[str, str] = {
    "akm": "qa/*.md",
}
# `{WORK}` は後段Agentが解決するrun-scoped作業パスのliteralであり、
# `render_template()` の置換対象ではない。外部fragment内でもそのまま保持する。
_EXISTING_ARTIFACT_POLICY_SECTION = load_prompt_file(
    "runtime/template/existing-artifact-policy.prompt.md"
).strip()
_AZURE_OFFICIAL_INFO_SECTION = load_prompt_file(
    "runtime/template/azure-official-info.prompt.md"
).strip()
_GENERATED_TEST_RUNTIME_SECTION = load_prompt_file(
    "runtime/template/generated-test-runtime.prompt.md"
).strip()
_QA_REVIEW_CONTEXT_SECTION = load_prompt_file(
    "runtime/template/qa-review-context.prompt.md"
)
_APP_ID_SECTION_TEMPLATE = load_prompt_file(
    "runtime/template/app-id-section.prompt.md"
)
_RESOURCE_GROUP_SECTION_TEMPLATE = load_prompt_file(
    "runtime/template/resource-group-section.prompt.md"
)
_JOB_SECTION_TEMPLATE = load_prompt_file(
    "runtime/template/job-section.prompt.md"
)
_TARGET_FILES_SECTION_TEMPLATE = load_prompt_file(
    "runtime/template/target-files-section.prompt.md"
)
_COMPLETION_GITHUB_TEMPLATE = load_prompt_file(
    "runtime/template/completion-github.prompt.md"
)
_COMPLETION_LOCAL_TEMPLATE = load_prompt_file(
    "runtime/template/completion-local.prompt.md"
)
_REMOTE_MCP_SERVER_SECTION = load_prompt_file(
    "runtime/template/remote-mcp-implementation.prompt.md"
)
_REMOTE_MCP_SERVER_DESIGN_SECTION = load_prompt_file(
    "runtime/template/remote-mcp-design.prompt.md"
)


def _get_default_akm_target_files(sources) -> str:
    """AKM の sources に応じた target_files 既定値を返す。

    ``sources`` は文字列（カンマ/空白区切り）または ``list[str]`` を受け付ける。
    Work IQ のみ、または非 Work IQ ソースが複数の場合は既定パターンなし。

    後方互換: 旧 ``"original-docs"`` / ``"both"`` 等の単一文字列も受理する。
    """
    # orchestrator 側の正規化ロジックを再利用する。
    try:
        from .orchestrator import _default_akm_target_files as _impl  # type: ignore
    except ImportError:
        import importlib
        _impl = getattr(importlib.import_module("orchestrator"), "_default_akm_target_files")
    return _impl(sources)

# ワークフロー名称マップ（タイトルプレフィックス用）
_WORKFLOW_DISPLAY_NAMES: Dict[str, str] = {
    "ard": "Auto Requirement Definition",
    "aas": "Architecture Design",
    "ada": "Agent Data Architecture",
    "aad-web": "Web App Design",
    "asdw-web": "Web App Dev & Deploy",
    "adfd": "Dataflow Design",
    "adfdv": "Dataflow Dev & Deploy",
    "aag": "AI Agent Design",
    "aagd": "AI Agent Dev & Deploy",
    "aar": "Agentic Retrieval Add-on",
    "akm": "Knowledge Management",
    "adi": "Auto Design-doc Ingestion",
    "adoc": "Source Codeからのドキュメント作成",
    # 後方互換エイリアス
    "aad": "Web App Design",
    "asdw": "Web App Dev & Deploy",
}

# ワークフロー略称（Issue タイトルプレフィックス: [AAS], [AAD] 等）
_WORKFLOW_PREFIX: Dict[str, str] = {
    "ard": "ARD",
    "aas": "AAS",
    "ada": "ADA",
    "aad-web": "AAD-WEB",
    "asdw-web": "ASDW-WEB",
    "adfd": "ADFD",
    "adfdv": "ADFDV",
    "aag": "AAG",
    "aagd": "AAGD",
    "akm": "AKM",
    "adi": "ADI",
    "adoc": "ADOC",
    # 後方互換エイリアス
    "aad": "AAD-WEB",
    "asdw": "ASDW-WEB",
}

# ---------------------------------------------------------------------------
# Agentic Retrieval 質問項目定義（Phase 2）
# ---------------------------------------------------------------------------
# 各エントリのキーは Issue Form YAML の `id` と一致させる（Phase 7 同期テスト前提）。
# applies_to: 質問が対象となるワークフロー ID のリスト（正規 ID のみ）。
# kind: dropdown / checkboxes / textarea / checkbox
# options: dropdown/checkboxes の選択肢リスト（kind=textarea/checkbox では省略）
# default: dropdown の場合は選択肢リストのインデックス（0-based）、
#          checkboxes の場合は list[str]（既定で選択済みの選択肢リスト）、
#          checkbox の場合は bool、textarea の場合は文字列。
_AGENTIC_RETRIEVAL_QUESTIONS: Dict[str, Any] = {
    "enable_agentic_retrieval": {
        "label": "Agentic Retrieval を使用する",
        "description": (
            "Chat-Bot / AI Agent を機能要件に含むアプリ向け。"
            "`Arch-AgenticRetrieval-Detail` Custom Agent の自動判定結果に従います。"
            "明示的な上書きも可能です。"
            "「しない」を選ぶと AAD-WEB / ASDW-WEB の Agentic Retrieval 関連ステップは生成されません。"
        ),
        "kind": "dropdown",
        "options": ["する", "しない", "自動判定に従う"],
        "default": 2,
        "applies_to": ["aad-web", "asdw-web"],
    },
    "agentic_data_source_modes": {
        "label": "データソース投入方式",
        "description": (
            "Indexer 対応データソースは保守性の観点から Indexer を優先します。"
            "Indexer 非対応のデータは Push API。両方の併用も可。"
            "対応一覧は実行時に Microsoft Learn MCP で確認します。"
        ),
        "kind": "checkboxes",
        "options": ["Indexer (Pull)", "Push API"],
        "default": ["Indexer (Pull)"],
        "applies_to": ["asdw-web"],
    },
    "foundry_mcp_integration": {
        "label": "Microsoft Foundry 連携（Remote MCP Server）",
        "description": (
            "「する」を選ぶと Foundry プロジェクトの新規作成・モデルの Global Deployment・"
            "MCP 接続設定までを IaC が自動構成します。"
        ),
        "kind": "dropdown",
        "options": ["する", "しない"],
        "default": 0,
        "applies_to": ["aad-web", "asdw-web"],
    },
    "agentic_data_sources_hint": {
        "label": "想定データソース（任意）",
        "description": (
            "起点となるデータソース想定を 1 行 1 件で記述。空でも可。"
            "例: `Blob: rg-xxx/sa-docs/raw`"
        ),
        "kind": "textarea",
        "default": "",
        "applies_to": ["asdw-web"],
    },
    "agentic_existing_design_diff_only": {
        "label": "既存設計の差分更新",
        "description": (
            "チェック時、`docs/azure/agentic-retrieval/` の既存設計を上書きせず差分更新します。"
        ),
        "kind": "checkbox",
        "default": False,
        "applies_to": ["asdw-web"],
    },
    "foundry_sku_fallback_policy": {
        "label": "Foundry モデル SKU フォールバック",
        "description": (
            "Global Standard クォータ枯渇時に Standard SKU へフォールバックを許容するか。"
            "`cli-evidence.md` に根拠記録されます。"
        ),
        "kind": "dropdown",
        "options": ["Global 必須（Standard 拒否）", "Standard 許容"],
        "default": 1,
        "applies_to": ["asdw-web"],
    },
}

# _AGENTIC_RETRIEVAL_QUESTIONS に存在するキーのうち applies_to に含めるワークフロー毎のリスト
_AGENTIC_RETRIEVAL_KEYS_FOR: Dict[str, List[str]] = {
    "aad-web": [
        k for k, v in _AGENTIC_RETRIEVAL_QUESTIONS.items()
        if "aad-web" in v["applies_to"]
    ],
    "asdw-web": [
        k for k, v in _AGENTIC_RETRIEVAL_QUESTIONS.items()
        if "asdw-web" in v["applies_to"]
    ],
}


def format_agentic_retrieval_block(workflow_id: str) -> str:
    """指定ワークフローに適用される Agentic Retrieval 質問一覧を Markdown で返す。

    Phase 7 の同期テストが将来追加可能な構造になっている。

    Args:
        workflow_id: "aad-web" または "asdw-web"（後方互換エイリアスも可）。

    Returns:
        Agentic Retrieval 質問ブロックの Markdown 文字列。
        対象ワークフローでない場合は空文字列。
    """
    wf_id = canonicalize_workflow_id(workflow_id)
    keys = _AGENTIC_RETRIEVAL_KEYS_FOR.get(wf_id)
    if not keys:
        return ""
    lines: List[str] = ["## Agentic Retrieval 設定\n"]
    for key in keys:
        q = _AGENTIC_RETRIEVAL_QUESTIONS[key]
        label = q["label"]
        desc = q["description"]
        kind = q["kind"]
        default = q["default"]
        lines.append(f"### {label}\n")
        lines.append(f"{desc}\n")
        if kind == "dropdown":
            opts = q["options"]
            for i, opt in enumerate(opts):
                marker = "**（既定）**" if i == default else ""
                lines.append(f"- {opt}{marker}")
        elif kind == "checkboxes":
            opts = q["options"]
            defaults_list = default if isinstance(default, list) else []
            for opt in opts:
                marker = "**（既定）**" if opt in defaults_list else ""
                lines.append(f"- {opt}{marker}")
        elif kind == "checkbox":
            default_str = "✓（既定）" if default else "✗（既定）"
            lines.append(f"デフォルト: {default_str}")
        elif kind == "textarea":
            lines.append(f"デフォルト: {default!r}")
        lines.append("")
    return "\n".join(lines)


def normalize_agentic_retrieval_answers(answers: dict) -> dict:
    """Agentic Retrieval 質問の回答を正規化する。

    Q1（enable_agentic_retrieval）が "no" または日本語 UI 値 "しない" のとき、
    Q3（foundry_mcp_integration）と Q6（foundry_sku_fallback_policy）を強制的に
    無効化する。内部値（"no"）と UI 表示値（"しない"）の両方を受け付ける。

    Args:
        answers: hve CLI ウィザードまたは Issue Form から収集したフィールド辞書。
                 すべてのキーが存在しなくてもよい。

    Returns:
        正規化後の辞書（元の辞書は変更しない）。
    """
    result = dict(answers)
    enable = result.get("enable_agentic_retrieval", "auto")
    # "no"（内部値）または "しない"（UI 表示値）のどちらでも無効化する
    if enable in ("no", "しない"):
        result["foundry_mcp_integration"] = False
        result["foundry_sku_fallback_policy"] = "standard_allowed"
    return result


# ---------------------------------------------------------------------------
# 対話入力ヘルパー
# ---------------------------------------------------------------------------


def _prompt(label: str, default: str = "", required: bool = False) -> str:
    """CLI プロンプトで入力を受け付ける。"""
    suffix = f" [{default}]" if default else ""
    req = " (必須)" if required else ""
    while True:
        answer = input(f"{label}{req}{suffix}: ").strip()
        if not answer:
            answer = default
        if required and not answer:
            print("  ⚠️ 入力が必要です。", flush=True)
            continue
        return answer


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    """Yes/No プロンプト。"""
    default_str = "Y/n" if default else "y/N"
    answer = input(f"{label} [{default_str}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_steps(wf: WorkflowDef) -> List[str]:
    """実行ステップ選択プロンプト。

    空入力 = 全ステップ実行。選択した場合はそのステップ ID のリストを返す。
    """
    non_container_steps = [s for s in wf.steps if not s.is_container]
    print("\n実行するステップを選択してください（カンマ区切りで番号を入力）:")
    print("  空入力（Enter）= 全ステップ実行")
    for i, step in enumerate(non_container_steps, 1):
        print(f"  {i}. Step.{step.id}: {step.title}")

    while True:
        answer = input("\n選択 (例: 1,3,5): ").strip()
        if not answer:
            return []  # 全ステップ

        selected_indices: List[int] = []
        for part in answer.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(non_container_steps):
                    selected_indices.append(idx)
                else:
                    print(f"  ⚠️ 範囲外: {idx}（スキップ）")
            else:
                print(f"  ⚠️ 無効な入力: {part!r}（スキップ）")

        if selected_indices:
            return [non_container_steps[i - 1].id for i in selected_indices]

        print("  ❌ 有効なステップが選択されませんでした。再入力してください。")


# ---------------------------------------------------------------------------
# パラメータ収集
# ---------------------------------------------------------------------------


def collect_params(wf: WorkflowDef, *, will_create_pr: bool = False) -> dict:
    """ワークフロー固有パラメータを対話的に収集する。

    Args:
        wf: 対象ワークフロー定義。
        will_create_pr: GitHub Issue または PR を作成する場合 True。
            False のときは `enable_auto_merge` プロンプトを表示せず False を採用する。

    Returns:
        dict with keys:
          branch, selected_steps, skip_review, skip_qa,
          + ワークフロー固有パラメータ (app_ids, app_id, resource_group, usecase_id, app_id)
    """
    print(f"\n{'='*60}")
    print(f" ワークフロー: {_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}")
    print(f"{'='*60}\n")

    params: dict = {}

    # 共通パラメータ
    params["branch"] = _prompt("対象ブランチ", default="main")

    # ワークフロー固有パラメータ
    if "app_ids" in wf.params or "app_id" in wf.params:
        _arch_hint = {
            "aad-web": "Webフロントエンド + クラウド",
            "asdw-web": "Webフロントエンド + クラウド",
            "adfd": "データデータフロー処理 / バッチ",
            "adfdv": "データデータフロー処理 / バッチ",
        }.get(wf.id, "")
        if _arch_hint:
            _prompt_label = (
                f"対象アプリケーション (APP-ID) — カンマ区切りで複数指定可"
                f"（未指定時は {_arch_hint} の APP-ID を自動選択）"
            )
        else:
            _prompt_label = "対象アプリケーション (APP-ID) — カンマ区切りで複数指定可"
        raw = _prompt(
            _prompt_label,
            default="",
            required=False,
        )
        if raw:
            params["app_ids"] = [s.strip() for s in raw.split(",") if s.strip()]
            if len(params["app_ids"]) == 1:
                params["app_id"] = params["app_ids"][0]
    if "resource_group" in wf.params:
        params["resource_group"] = _prompt("リソースグループ名", default="", required=False)
    if "usecase_id" in wf.params:
        params["usecase_id"] = _prompt("ユースケースID", default="", required=False)
    if "app_id" in wf.params:
        params["app_id"] = _prompt(
            "対象データフローアプリ ID（カンマ区切り）", default="", required=False
        )
    if "tdd_max_retries" in wf.params:
        import re as _re
        print("\n[TDD GREEN リトライ最大回数]")
        print("  TDD GREEN フェーズでテストが全 PASS にならない場合、")
        print("  実装を修正しながら最大この回数まで再試行します。")
        print("  上限を超えた場合は blocked ラベルを付与して停止します。")
        print("  選択肢: 3 / 5 / 7 / 10  （デフォルト: 5）")
        raw = _prompt("TDD GREEN リトライ最大回数", default="5", required=False)
        m = _re.search(r'\d+', raw or "5")
        if m:
            params["tdd_max_retries"] = int(m.group())
        else:
            import logging
            logging.warning(f"tdd_max_retries '{raw}' を整数変換できません。デフォルト 5 を使用します")
            params["tdd_max_retries"] = 5
    if "create_remote_mcp_server" in wf.params:
        params["create_remote_mcp_server"] = _prompt_yes_no(
            "API 作成時に Remote MCP Server 実装を追加する？", default=True
        )

    # AKM 固有パラメータ
    if "sources" in wf.params:
        print("\n取り込みソースを選択してください:")
        print("  1) qa")
        print("  2) original-docs")
        print("  3) both")
        while True:
            source_input = input("選択 [1]: ").strip() or "1"
            source_map = {"1": "qa", "2": "original-docs", "3": "both"}
            if source_input in source_map:
                params["sources"] = source_map[source_input]
                break
            print("  ⚠️ 1〜3 を入力してください。")

    if "target_files" in wf.params:
        if wf.id == "akm":
            default_target_files = _get_default_akm_target_files(params.get("sources", "qa"))
        else:
            default_target_files = _DEFAULT_TARGET_FILES.get(wf.id, "")
        target_files = _prompt(
            "対象ファイルパス（スペース区切り）", default=default_target_files, required=False
        )
        params["target_files"] = target_files.strip() if target_files.strip() else default_target_files

    if "force_refresh" in wf.params:
        params["force_refresh"] = _prompt_yes_no(
            "既存 knowledge/ 出力を完全に再生成する？", default=False
        )
    if "custom_source_dir" in wf.params:
        params["custom_source_dir"] = _prompt(
            "custom_source_dir（スペース区切り・任意）", default="", required=False
        )
    if "enable_auto_merge" in wf.params:
        if will_create_pr:
            params["enable_auto_merge"] = _prompt_yes_no(
                "PR の自動 Approve & Auto-merge を有効にする？", default=False
            )
        else:
            params["enable_auto_merge"] = False

    # ADI 固有パラメータ
    if wf.id == "adi":
        params["purpose"] = _prompt(
            "設計書選別の目的（任意）",
            default="",
            required=False,
        )
        params["target_scope"] = _prompt(
            "対象設計書スコープ（省略時: docs-original/）",
            default="docs-original/",
            required=False,
        )
        print("\n分析の深さを選択してください:")
        print("  1) standard")
        print("  2) lightweight")
        while True:
            depth_input = input("選択 [1]: ").strip() or "1"
            depth_map = {"1": "standard", "2": "lightweight"}
            if depth_input in depth_map:
                params["depth"] = depth_map[depth_input]
                break
            print("  ⚠️ 1〜2 を入力してください。")
        params["focus_areas"] = _prompt(
            "重点観点（任意）",
            default="",
            required=False,
        )

    # ADOC 固有パラメータ
    if "target_dirs" in wf.params:
        params["target_dirs"] = _prompt(
            "ドキュメント生成対象ディレクトリ（カンマ区切り。省略 = 全体）",
            default="",
            required=False,
        )
    if "exclude_patterns" in wf.params:
        params["exclude_patterns"] = _prompt(
            "除外パターン（カンマ区切り）",
            default="node_modules/,vendor/,dist/,*.lock,__pycache__/",
            required=False,
        )
    if "doc_purpose" in wf.params:
        print("\nドキュメントの主目的を選択してください:")
        print("  1) all")
        print("  2) onboarding")
        print("  3) refactoring")
        print("  4) migration")
        while True:
            purpose_input = input("選択 [1]: ").strip() or "1"
            purpose_map = {
                "1": "all",
                "2": "onboarding",
                "3": "refactoring",
                "4": "migration",
            }
            if purpose_input in purpose_map:
                params["doc_purpose"] = purpose_map[purpose_input]
                break
            print("  ⚠️ 1〜4 を入力してください。")
    if "max_file_lines" in wf.params:
        while True:
            val = _prompt("大規模ファイル分割閾値（行数）", default="500", required=False).strip()
            if not val:
                params["max_file_lines"] = 500
                break
            if val.isdigit():
                params["max_file_lines"] = int(val)
                break
            print("  ⚠️ 数値を入力してください。")

    # ステップ選択
    params["selected_steps"] = _prompt_steps(wf)

    # レビュー / 質問票設定
    params["skip_review"] = _prompt_yes_no(
        "HVE Phase 3 の敵対的レビューをスキップする？",
        default=False,
    )
    params["skip_qa"] = _prompt_yes_no("質問票の作成をスキップする？", default=False)

    return params


# ---------------------------------------------------------------------------
# テンプレート読み込みと展開
# ---------------------------------------------------------------------------


def _load_template(template_path: str) -> str:
    """Step body テンプレートを単一 loader 経由で読み込む。

    FR-PROMPT-SRC-02: 必須 prompt は欠損・空・不正 path で fail-closed とする。
    path の正規化と `.github/prompts/` prefix の取り扱いは loader 側の単一実装に任せる。
    """
    return load_prompt_file(template_path)


def _build_existing_artifact_policy_section() -> str:
    """既存成果物更新方針セクションを返す。"""
    return _EXISTING_ARTIFACT_POLICY_SECTION


def _inject_azure_official_info_section(body: str) -> str:
    """Azure 関連 Step に Microsoft Learn MCP 参照規律を補う。

    テンプレート側に既に明記済みの場合は重複させない。
    """
    if "Azure" not in body or "利用可能なら必ず参照" in body:
        return body
    return f"{body.rstrip()}\n\n{_AZURE_OFFICIAL_INFO_SECTION}\n"


def _inject_generated_test_runtime_section(body: str) -> str:
    """TDD 関連テンプレートに生成テストの実行環境契約を補う。

    既にテンプレート側へ `## 生成テストの実行環境` が明記されている場合は
    重複させない。対象は TDD 専用レポートを要求するテンプレートに限定し、
    通常の設計・ドキュメント生成テンプレートへは注入しない。
    """
    if "生成テストの実行環境" in body:
        return body
    if "tdd-test-report.md" not in body and "TDD テスト結果レポート" not in body:
        return body
    return f"{body.rstrip()}\n\n{_GENERATED_TEST_RUNTIME_SECTION}\n"


def _resolve_app_ids(params: dict) -> list:
    """params から app_ids リストを解決する。

    ``app_ids`` (list) を優先し、なければ ``app_id`` をリスト化して返す。
    どちらも存在しない場合は空リストを返す。
    """
    ids = params.get("app_ids")
    if ids:
        return ids
    single = params.get("app_id")
    return [single] if single else []


def _build_root_ref(root_issue_num: int, params: Optional[dict] = None) -> str:
    """テンプレートの ``{root_ref}`` を展開する。

    メタデータ HTML コメントを生成する。
    """
    if params is None:
        params = {}

    branch = params.get("branch", "main")
    auto_qa = str(not params.get("skip_qa", False)).lower()
    auto_merge = str(bool(params.get("enable_auto_merge", False))).lower()

    parts = [
        f"<!-- root-issue: #{root_issue_num} -->",
        f"<!-- branch: {branch} -->",
    ]

    resource_group = params.get("resource_group", "")
    if resource_group:
        parts.append(f"<!-- resource-group: {resource_group} -->")
    app_ids = _resolve_app_ids(params)
    if app_ids:
        parts.append(f"<!-- app-ids: {', '.join(app_ids)} -->")

    app_id = params.get("app_id", "")
    if app_id:
        parts.append(f"<!-- app-ids: {app_id} -->")

    parts.append(f"<!-- auto-qa: {auto_qa} -->")
    parts.append(f"<!-- auto-merge: {auto_merge} -->")

    tdd_max_retries = params.get("tdd_max_retries", 5)
    parts.append(f"<!-- tdd-max-retries: {tdd_max_retries} -->")

    create_remote_mcp_server = _get_bool_param_str(params, "create_remote_mcp_server", default=True)
    parts.append(f"<!-- create-remote-mcp-server: {create_remote_mcp_server} -->")

    return "\n".join(parts)


def _build_qa_review_context_section() -> str:
    """全 Step に共通の QA / Review / 前成果物 参照セクションを返す。

    Issue Template 経路でも QA 回答・Review 指摘が主タスク成果物へ確実に反映されるよう、
    全 Step template に自動注入する共通参照ルール（Phase 3 追加）。
    """
    return _QA_REVIEW_CONTEXT_SECTION


def _build_app_id_section(app_id) -> str:
    """ASDW テンプレートの ``{app_id_section}`` を展開する。

    Args:
        app_id: 単一の APP-ID 文字列またはリスト。リストの場合は複数 APP-ID に対応。
    """
    if isinstance(app_id, list):
        ids = [aid for aid in app_id if aid]
    else:
        ids = [app_id] if app_id else []
    if not ids:
        # APP-ID 未指定時: スコープセクションを挿入しない。
        # aad-web / asdw-web / adfd / adfdv では、orchestrator の app-arch filter が
        # 推薦アーキテクチャに合致する APP-ID を effective_params に設定するため、
        # 通常このパスには到達しない。
        return ""
    id_list = ", ".join(f"`{aid}`" for aid in ids)
    return _APP_ID_SECTION_TEMPLATE.replace("{id_list}", id_list)


def _build_rg_section(resource_group: str) -> str:
    """ADFDV テンプレートの ``{rg_section}`` を展開する。"""
    if not resource_group:
        return ""
    return _RESOURCE_GROUP_SECTION_TEMPLATE.replace("{resource_group}", resource_group)


def _build_job_section(app_id: str) -> str:
    """ADFDV テンプレートの ``{job_section}`` を展開する。"""
    if not app_id:
        return ""
    return _JOB_SECTION_TEMPLATE.replace("{job_id}", app_id)


def _build_target_files_section(target_files: str) -> str:
    """AKM テンプレートの対象ファイルセクションを展開する。"""
    if not target_files:
        return ""
    files = [f.strip() for f in target_files.split() if f.strip()]
    if not files:
        return ""
    lines = "\n".join(f"- `{f}`" for f in files)
    return _TARGET_FILES_SECTION_TEMPLATE.replace("{target_lines}", lines)


def _build_completion_instruction(label_prefix: str, execution_mode: str) -> str:
    """実行モードに応じた完了条件を返す。"""
    done_label = f"{label_prefix}:done"
    if execution_mode == "github":
        return _COMPLETION_GITHUB_TEMPLATE.replace("{done_label}", done_label)
    return _COMPLETION_LOCAL_TEMPLATE.replace("{done_label}", done_label)


def _normalize_bool(value, default: bool = True) -> bool:
    """様々な型・文字列表現の値を Python の bool に正規化する。

    対応する値:
        - ``True`` / ``False``
        - ``"true"`` / ``"false"``
        - ``"1"`` / ``"0"``
        - ``"yes"`` / ``"no"``
        - ``"y"`` / ``"n"``
        - ``"on"`` / ``"off"``
        - ``"作成する"`` / ``"作成しない"``

    未対応値・``None`` は ``default`` を返す。

    Args:
        value: 正規化する値。
        default: 不明値のデフォルト。

    Returns:
        正規化された bool 値。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "y", "on", "作成する"):
        return True
    if s in ("false", "0", "no", "n", "off", "作成しない"):
        return False
    return default


def _get_bool_param_str(params: dict, key: str, default: bool = True) -> str:
    """params から bool 値を取得し、小文字の ``"true"`` / ``"false"`` 文字列に変換する。

    Args:
        params: パラメータ辞書。
        key: 取得するキー名。
        default: キーが存在しない場合のデフォルト値。

    Returns:
        ``"true"`` または ``"false"`` のいずれかの文字列。
    """
    raw = params.get(key)
    if raw is None:
        return str(default).lower()
    return str(_normalize_bool(raw, default=default)).lower()


def _build_remote_mcp_server_section(create_remote_mcp_server: bool) -> str:
    """Step.2.5 テンプレートの ``{remote_mcp_server_section}`` を展開する。

    Args:
        create_remote_mcp_server: ``True`` のとき Remote MCP Server 実装指示セクションを返す。
            ``False`` のときは空文字を返す（プレースホルダを除去）。

    Returns:
        Remote MCP Server 実装指示セクションの Markdown 文字列。
        ``create_remote_mcp_server=False`` のときは空文字列。
    """
    if not create_remote_mcp_server:
        return ""
    return _REMOTE_MCP_SERVER_SECTION


def _build_remote_mcp_server_design_section(create_remote_mcp_server: bool) -> str:
    """Step.2.2 テンプレートの ``{remote_mcp_server_design_section}`` を展開する。

    設計フェーズ向けの Remote MCP Server 設計観点セクションを生成する。
    技術選定（SDK / Transport / Cloud Compute）は固定せず、設計観点のみを記述する。

    Args:
        create_remote_mcp_server: ``True`` のとき Remote MCP Server 設計観点セクションを返す。
            ``False`` のときは空文字を返す（プレースホルダを除去）。

    Returns:
        Remote MCP Server 設計観点セクションの Markdown 文字列。
        ``create_remote_mcp_server=False`` のときは空文字列。
    """
    if not create_remote_mcp_server:
        return ""
    return _REMOTE_MCP_SERVER_DESIGN_SECTION


def render_template(
    template_path: str,
    root_issue_num: int,
    params: dict,
    wf: WorkflowDef,
    execution_mode: str = "local",
) -> str:
    """テンプレートを読み込み、プレースホルダを展開する。"""
    body = _load_template(template_path)

    root_ref = _build_root_ref(root_issue_num, params)
    qa_review_section = _build_qa_review_context_section()

    body = body.replace("{root_ref}", root_ref)
    body = body.replace("{additional_section}", qa_review_section)
    if "{existing_artifact_policy}" in body:
        body = body.replace(
            "{existing_artifact_policy}",
            _build_existing_artifact_policy_section(),
        )
    body = body.replace(
        "{completion_instruction}",
        _build_completion_instruction(wf.label_prefix, execution_mode),
    )

    # ASDW 固有プレースホルダ
    app_ids = _resolve_app_ids(params)
    body = body.replace("{app_id_section}", _build_app_id_section(app_ids if app_ids else params.get("app_id", "")))
    body = body.replace("{resource_group}", params.get("resource_group", ""))
    body = body.replace("{usecase_id}", params.get("usecase_id", ""))
    body = body.replace("{tdd_max_retries}", str(params.get("tdd_max_retries", 5)))
    body = body.replace(
        "{remote_mcp_server_section}",
        _build_remote_mcp_server_section(
            _normalize_bool(params.get("create_remote_mcp_server"), default=True)
        ),
    )

    # AAD-WEB 固有プレースホルダ
    body = body.replace(
        "{remote_mcp_server_design_section}",
        _build_remote_mcp_server_design_section(
            _normalize_bool(params.get("create_remote_mcp_server"), default=True)
        ),
    )

    # 推薦アーキテクチャ スコープセクション（aad-web / asdw-web / adfd / adfdv 共通）
    body = body.replace(
        "{app_arch_scope_section}",
        params.get("app_arch_scope_section", ""),
    )

    # ADFDV 固有プレースホルダ
    body = body.replace("{rg_section}", _build_rg_section(params.get("resource_group", "")))
    body = body.replace("{job_section}", _build_job_section(params.get("app_id", "")))

    # AKM 固有プレースホルダ
    body = body.replace("{akm_sources}", params.get("sources", "qa,original-docs"))
    body = body.replace("{akm_target_files}", params.get("target_files", ""))
    body = body.replace(
        "{akm_target_files_section}",
        _build_target_files_section(params.get("target_files", "")),
    )
    body = body.replace(
        "{akm_force_refresh}",
        str(params.get("force_refresh", False)).lower(),
    )
    body = body.replace("{akm_custom_source_dir}", params.get("custom_source_dir", ""))

    # ADI 固有プレースホルダ
    body = body.replace("{adi_target_scope}", params.get("target_scope", "docs-original/"))
    body = body.replace("{adi_depth}", params.get("depth", "standard"))
    body = body.replace("{adi_focus_areas}", params.get("focus_areas", ""))
    # purpose が空のときは目的非依存モードで実行される。
    body = body.replace("{adi_purpose}", (params.get("purpose", "") or "").strip() or "未指定")

    # ARD 固有プレースホルダ（未入力時も placeholder が残らないようにする）
    _ard_company_name = (params.get("company_name", "") or "").strip() or "未指定"
    _ard_target_business = (params.get("target_business", "") or "").strip() or "未指定"
    body = body.replace("{company_name}", _ard_company_name)
    body = body.replace("{target_business}", _ard_target_business)

    # ARD: orchestrator/__main__ で既定値が必ず設定されるが、
    # 直接 render_template を呼ぶ単体テストや非ARDワークフローからの参照に備えて
    # ここで防御的に既定値を埋める（既定値は ARD ウィザード/CLI 既定と一致）。
    _ard_survey_period_years = str(
        params.get("survey_period_years", "") or "30"
    ).strip()
    body = body.replace("{survey_period_years}", _ard_survey_period_years)

    _ard_survey_base_date = (params.get("survey_base_date", "") or "").strip()
    if not _ard_survey_base_date:
        import datetime as _dt
        _ard_survey_base_date = _dt.date.today().strftime("%Y-%m-%d")
    body = body.replace("{survey_base_date}", _ard_survey_base_date)

    body = body.replace(
        "{target_region}",
        (params.get("target_region", "") or "").strip() or "グローバル全体",
    )
    body = body.replace(
        "{analysis_purpose}",
        (params.get("analysis_purpose", "") or "").strip() or "中長期成長戦略の立案",
    )

    _ard_attached = params.get("attached_docs", "")
    if isinstance(_ard_attached, list):
        _ard_attached = ", ".join(str(x) for x in _ard_attached)
    _ard_attached = (_ard_attached or "").strip() or "添付なし"
    body = body.replace("{attached_docs}", _ard_attached)

    # ADOC 固有プレースホルダ
    body = body.replace("{target_dirs}", params.get("target_dirs", ""))
    body = body.replace(
        "{exclude_patterns}",
        params.get("exclude_patterns", "node_modules/,vendor/,dist/,*.lock,__pycache__/"),
    )
    body = body.replace("{doc_purpose}", params.get("doc_purpose", "all"))
    body = body.replace("{max_file_lines}", str(params.get("max_file_lines", 500)))

    # コンテナ固有プレースホルダ (AAD step-7)
    body = body.replace("{s7_subtasks}", "Step.7.1, Step.7.2, Step.7.3")

    if execution_mode == "local":
        import re

        body = re.sub(
            r"- 完了時に自身に `[a-z-]+:done` ラベルを付与すること",
            "- 上記の出力ファイルが全て正常に生成されていることを確認して完了とすること\n"
            "- ※ ローカル実行のため done ラベルの付与は不要です",
            body,
        )
        body = re.sub(
            r"- 完了時に `[a-z-]+:done` を付与すること",
            "- 上記の出力ファイルが全て正常に生成されていることを確認して完了とすること\n"
            "- ※ ローカル実行のため done ラベルの付与は不要です",
            body,
        )

    body = _inject_azure_official_info_section(body)
    body = _inject_generated_test_runtime_section(body)

    return body


# ---------------------------------------------------------------------------
# ステップフィルタリング
# ---------------------------------------------------------------------------


def resolve_selected_steps(
    wf: WorkflowDef, selected_step_ids: List[str]
) -> Set[str]:
    """選択ステップ ID から、実際に作成するステップ ID セットを返す。

    空リスト = 全ステップ。
    選択ステップが指定された場合、そのステップと関連コンテナを含める。
    """
    all_steps = {s.id for s in wf.steps}

    if not selected_step_ids:
        return all_steps

    # バリデーション: 未知の Step ID を警告して除外
    valid_ids: List[str] = []
    for sid in selected_step_ids:
        if sid in all_steps:
            valid_ids.append(sid)
        else:
            print(f"  ⚠️ 未知の Step ID: {sid!r}（ワークフロー {wf.id} に存在しません。除外します）")

    if not valid_ids:
        print("  ⚠️ 有効な Step ID がないため、全ステップを実行します。")
        return all_steps

    selected = set(valid_ids)

    # コンテナを含める: 選択ステップの親コンテナ（コンテナ ID が子ステップ ID の prefix）
    for step in wf.steps:
        if step.is_container:
            has_selected_child = any(
                child_id.startswith(step.id + ".")
                for child_id in selected
            )
            if has_selected_child:
                selected.add(step.id)

    return selected


# ---------------------------------------------------------------------------
# Root Issue 作成
# ---------------------------------------------------------------------------


def build_root_issue_body(wf: WorkflowDef, params: dict) -> str:
    """Root Issue の本文を組み立てる。"""
    prefix = _WORKFLOW_PREFIX.get(wf.id, wf.id.upper())
    branch = params.get("branch", "main")
    auto_qa = str(not params.get("skip_qa", False)).lower()
    auto_merge = str(bool(params.get("enable_auto_merge", False))).lower()

    lines: List[str] = []
    lines.append(f"# [{prefix}] {_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}\n")

    # メタデータ HTML コメント
    lines.append(f"<!-- branch: {branch} -->")
    if params.get("resource_group"):
        lines.append(f"<!-- resource-group: {params['resource_group']} -->")
    app_ids = _resolve_app_ids(params)
    if app_ids:
        lines.append(f"<!-- app-ids: {', '.join(app_ids)} -->")
    if params.get("app_id"):
        lines.append(f"<!-- app-ids: {params['app_id']} -->")
    lines.append(f"<!-- auto-qa: {auto_qa} -->")
    lines.append(f"<!-- auto-merge: {auto_merge} -->")
    if "create_remote_mcp_server" in wf.params:
        create_remote_mcp_server = _get_bool_param_str(params, "create_remote_mcp_server", default=True)
        lines.append(f"<!-- create-remote-mcp-server: {create_remote_mcp_server} -->")
    lines.append("")
    lines.append(f"ワークフロー: **{_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}**")
    lines.append(f"ブランチ: `{branch}`")

    if params.get("app_ids"):
        id_list = ", ".join(f"`{aid}`" for aid in params["app_ids"])
        lines.append(f"APP-ID: {id_list}")
    elif params.get("app_id"):
        lines.append(f"APP-ID: `{params['app_id']}`")
    if params.get("resource_group"):
        lines.append(f"リソースグループ: `{params['resource_group']}`")
    if params.get("usecase_id"):
        lines.append(f"ユースケースID: `{params['usecase_id']}`")
    if params.get("app_id"):
        lines.append(f"データフローアプリ ID: `{params['app_id']}`")
    if params.get("sources"):
        lines.append(f"sources: `{params['sources']}`")
    if params.get("target_files"):
        lines.append(f"target_files: `{params['target_files']}`")
    if params.get("custom_source_dir"):
        lines.append(f"custom_source_dir: `{params['custom_source_dir']}`")
    if params.get("force_refresh"):
        lines.append(f"force_refresh: `{params['force_refresh']}`")
    if params.get("target_scope"):
        lines.append(f"target_scope: `{params['target_scope']}`")
    if params.get("depth"):
        lines.append(f"depth: `{params['depth']}`")
    if params.get("focus_areas"):
        lines.append(f"focus_areas: `{params['focus_areas']}`")
    if params.get("app_arch_scope_section"):
        lines.append(params["app_arch_scope_section"])

    return "\n".join(lines)
