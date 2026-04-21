"""template_engine.py — テンプレート読み込み・プレースホルダ展開

旧 `.github/cli/orchestrate.py` のテンプレートエンジン関連関数を移植したもの。
テンプレートファイルは `.github/scripts/templates/` に格納されている。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

from .workflow_registry import WorkflowDef

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# テンプレートディレクトリのベースパス（リポジトリルート相対）
_TEMPLATES_BASE = Path(__file__).resolve().parent.parent / ".github" / "scripts"

# target_files 系ワークフローのデフォルト対象ファイル。
# ここで指定するパターンは orchestrator 側の glob 展開で評価される。
# `qa/*.md` は単一階層、`original-docs/*` は直下エントリを既定とする。
_DEFAULT_TARGET_FILES: Dict[str, str] = {
    "akm": "qa/*.md",
}


def _get_default_akm_target_files(sources: str) -> str:
    """AKM の sources に応じた target_files 既定値を返す。"""
    if sources == "original-docs":
        return "original-docs/*"
    if sources == "both":
        return ""
    return _DEFAULT_TARGET_FILES.get("akm", "")

# ワークフロー名称マップ（タイトルプレフィックス用）
_WORKFLOW_DISPLAY_NAMES: Dict[str, str] = {
    "aas": "App Architecture Design",
    "aad": "App Detail Design",
    "asdw": "App Dev Microservice Azure",
    "abd": "Batch Design",
    "abdv": "Batch Dev",
    "akm": "Knowledge Management",
    "aqod": "Original Docs Review",
    "adoc": "Source Codeからのドキュメント作成",
}

# ワークフロー略称（Issue タイトルプレフィックス: [AAS], [AAD] 等）
_WORKFLOW_PREFIX: Dict[str, str] = {
    "aas": "AAS",
    "aad": "AAD",
    "asdw": "ASDW",
    "abd": "ABD",
    "abdv": "ABDV",
    "akm": "AKM",
    "aqod": "AQOD",
    "adoc": "ADOC",
}


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
          branch, selected_steps, skip_review, skip_qa, additional_comment,
          + ワークフロー固有パラメータ (app_id, resource_group, usecase_id, batch_job_id)
    """
    print(f"\n{'='*60}")
    print(f" ワークフロー: {_WORKFLOW_DISPLAY_NAMES.get(wf.id, wf.id)}")
    print(f"{'='*60}\n")

    params: dict = {}

    # 共通パラメータ
    params["branch"] = _prompt("対象ブランチ", default="main")

    # ワークフロー固有パラメータ
    if "app_ids" in wf.params or "app_id" in wf.params:
        raw = _prompt("対象アプリケーション (APP-ID) — カンマ区切りで複数指定可", default="", required=False)
        if raw:
            params["app_ids"] = [s.strip() for s in raw.split(",") if s.strip()]
            if len(params["app_ids"]) == 1:
                params["app_id"] = params["app_ids"][0]
    if "resource_group" in wf.params:
        params["resource_group"] = _prompt("リソースグループ名", default="", required=False)
    if "usecase_id" in wf.params:
        params["usecase_id"] = _prompt("ユースケースID", default="", required=False)
    if "batch_job_id" in wf.params:
        params["batch_job_id"] = _prompt(
            "対象バッチジョブ ID（カンマ区切り）", default="", required=False
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
            "既存の status.md を完全に再生成する？", default=True
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

    # AQOD 固有パラメータ
    if wf.id == "aqod":
        params["target_scope"] = _prompt(
            "対象スコープ（省略時: original-docs/）",
            default="original-docs/",
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
    params["skip_review"] = _prompt_yes_no("セルフレビューをスキップする？", default=False)
    params["skip_qa"] = _prompt_yes_no("質問票の作成をスキップする？", default=False)

    # 追加コメント
    params["additional_comment"] = _prompt("追加コメント（任意）", default="")

    return params


# ---------------------------------------------------------------------------
# テンプレート読み込みと展開
# ---------------------------------------------------------------------------


def _load_template(template_path: str) -> str:
    """テンプレートファイルを読み込む。"""
    full_path = _TEMPLATES_BASE / template_path
    if not full_path.exists():
        print(f"  ⚠️ テンプレートが見つかりません: {template_path}", flush=True)
        return ""
    return full_path.read_text(encoding="utf-8")


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
    auto_review = str(not params.get("skip_review", False)).lower()
    auto_context_review = "true"
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

    batch_job_id = params.get("batch_job_id", "")
    if batch_job_id:
        parts.append(f"<!-- batch-job-ids: {batch_job_id} -->")

    parts.append(f"<!-- auto-review: {auto_review} -->")
    parts.append(f"<!-- auto-context-review: {auto_context_review} -->")
    parts.append(f"<!-- auto-qa: {auto_qa} -->")
    parts.append(f"<!-- auto-merge: {auto_merge} -->")

    return "\n".join(parts)


def _build_additional_section(params: dict) -> str:
    """テンプレートの ``{additional_section}`` を展開する。"""
    additional = params.get("additional_comment", "")
    if additional:
        return f"\n\n## 追加コメント\n{additional}"
    return ""


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
        return ""
    id_list = ", ".join(f"`{aid}`" for aid in ids)
    return (
        f"\n\n## 対象アプリケーション\n"
        f"- APP-ID: {id_list}\n"
        f"- この Step では上記 APP-ID に関連するサービス/エンティティ/画面のみを対象とする\n"
        f"- `docs/catalog/app-catalog.md` を参照し、対象 APP-ID に紐づく項目を特定する\n"
        f"- 共有サービス/エンティティ（複数 APP で利用されるもの）も対象に含む"
    )


def _build_rg_section(resource_group: str) -> str:
    """ABDV テンプレートの ``{rg_section}`` を展開する。"""
    if not resource_group:
        return ""
    return f"\n\n## リソースグループ\n`{resource_group}`"


def _build_job_section(batch_job_id: str) -> str:
    """ABDV テンプレートの ``{job_section}`` を展開する。"""
    if not batch_job_id:
        return ""
    return f"\n\n## 対象バッチジョブ ID\n`{batch_job_id}`"


def _build_target_files_section(target_files: str) -> str:
    """AKM テンプレートの対象ファイルセクションを展開する。"""
    if not target_files:
        return ""
    files = [f.strip() for f in target_files.split() if f.strip()]
    if not files:
        return ""
    lines = "\n".join(f"- `{f}`" for f in files)
    return f"\n\n## 対象ファイル\n{lines}"


def render_template(
    template_path: str,
    root_issue_num: int,
    params: dict,
    wf: WorkflowDef,
) -> str:
    """テンプレートを読み込み、プレースホルダを展開する。"""
    body = _load_template(template_path)
    if not body:
        return ""

    root_ref = _build_root_ref(root_issue_num, params)
    additional_section = _build_additional_section(params)

    body = body.replace("{root_ref}", root_ref)
    body = body.replace("{additional_section}", additional_section)

    # ASDW 固有プレースホルダ
    app_ids = _resolve_app_ids(params)
    body = body.replace("{app_id_section}", _build_app_id_section(app_ids if app_ids else params.get("app_id", "")))
    body = body.replace("{resource_group}", params.get("resource_group", ""))
    body = body.replace("{usecase_id}", params.get("usecase_id", ""))

    # ABDV 固有プレースホルダ
    body = body.replace("{rg_section}", _build_rg_section(params.get("resource_group", "")))
    body = body.replace("{job_section}", _build_job_section(params.get("batch_job_id", "")))

    # AKM 固有プレースホルダ
    body = body.replace("{akm_sources}", params.get("sources", "qa"))
    body = body.replace("{akm_target_files}", params.get("target_files", ""))
    body = body.replace(
        "{akm_target_files_section}",
        _build_target_files_section(params.get("target_files", "")),
    )
    body = body.replace(
        "{akm_force_refresh}",
        str(params.get("force_refresh", True)).lower(),
    )
    body = body.replace("{akm_custom_source_dir}", params.get("custom_source_dir", ""))

    # AQOD 固有プレースホルダ
    body = body.replace("{aqod_target_scope}", params.get("target_scope", "original-docs/"))
    body = body.replace("{aqod_depth}", params.get("depth", "standard"))
    body = body.replace("{aqod_focus_areas}", params.get("focus_areas", ""))

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
    auto_review = str(not params.get("skip_review", False)).lower()
    auto_context_review = "true"
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
    if params.get("batch_job_id"):
        lines.append(f"<!-- batch-job-ids: {params['batch_job_id']} -->")
    lines.append(f"<!-- auto-review: {auto_review} -->")
    lines.append(f"<!-- auto-context-review: {auto_context_review} -->")
    lines.append(f"<!-- auto-qa: {auto_qa} -->")
    lines.append(f"<!-- auto-merge: {auto_merge} -->")
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
    if params.get("batch_job_id"):
        lines.append(f"バッチジョブ ID: `{params['batch_job_id']}`")
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
    additional = params.get("additional_comment", "")
    if additional:
        lines.append(f"\n## 追加コメント\n{additional}")

    return "\n".join(lines)
