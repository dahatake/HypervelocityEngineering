"""hve.gui.workflow_step_requirements — ワークフロー要件テーブル定義（Task A-1 改訂版）。

設計プラン「ワークフロー必須要件サマリーバナー」§7 Task A-1 に対応する純データ層。
各ワークフローの「最小ステップ ID」と、そのステップが実行に最低限必要とする
入力情報（必須情報キー）/ 入力ファイル種別を定義する。

【一次ソース】（捏造禁止。すべて以下からのみ抽出）
  - ワークフロー & ステップ定義: ``hve/workflow_registry.py`` の ``WorkflowDef``
  - Step 2 オプション分類: ``hve/gui/page_options.py`` の
    ``_STEP2_FIELDS_BY_WORKFLOW`` / ``_WORKFLOW_TO_PRIMARY_CATEGORY``
  - ARD グループ ID: ``hve/gui/page_workflow_select.py`` の
    ``_WorkflowStepsGroup._ARD_GROUPS``
  - Custom Agent 概要: ``.github/agents/*.agent.md`` の description

【中間レビュー反映事項】（2026-05-23 ユーザー承認済み）
  - Q-A: ard.2 は ``target_business`` 必須（Agent 名 ``Targeted`` から）。
         ard.1 と ard.2 の OR ロジックは解消し、別ステップで別々の必須情報。
  - Q-B: aag.1 / aagd.1 から ``usecase_id`` を削除（任意）。
  - Q-C: akm.1 は ``original_docs_or_qa``（いずれか存在で OK）。
  - ``app_id`` は全ワークフローの必須情報キーから削除。代わりに対象カタログ
    ファイル（``app-catalog.md`` 等）の存在を ``required_file_kind`` として扱う。
    根拠: ユーザー指定の挙動「app_id 未指定時はカタログ内の全 APP が対象」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------
# 型定義
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StepRequirement:
    """1 つの (workflow_id, step_id) ペアに対応する必須要件定義。"""

    workflow_id: str
    step_id: str
    required_info_keys: Tuple[str, ...] = ()
    required_info_logic: str = "none"  # "all" / "any" / "none"
    required_file_kind: Optional[str] = None
    guidance_text: str = ""


@dataclass(frozen=True)
class FileKindSpec:
    """必須ファイル種別 → 解決対象パスのマッピング定義。"""

    paths: Tuple[str, ...]
    logic: str  # "any" / "all"
    display_name: str  # ガイダンス文に埋め込む名称


# --------------------------------------------------------------------------
# ワークフロー登録順（Task A-2 の pick_target_step が参照する明示順）
# 根拠: hve/gui/page_options.py の _WORKFLOW_CANONICAL_ORDER を踏襲。
# --------------------------------------------------------------------------

WORKFLOW_PRIORITY: Tuple[str, ...] = (
    "ard", "aas", "aad-web", "asdw-web",
    "adfd", "adfdv", "aag", "aagd",
    "akm", "aqod", "adoc",
)


# --------------------------------------------------------------------------
# ワークフロー → 配置先セクション名（QGroupBox 識別子）
# 根拠: hve/gui/page_options.py の _WORKFLOW_TO_PRIMARY_CATEGORY。
# 対応セクションを持たないワークフロー（aas / aag / aagd）は "OPTIONS_TOP" を
# フォールバックとして採用する。
# --------------------------------------------------------------------------

WORKFLOW_TO_SECTION: Dict[str, str] = {
    "ard": "C14",
    "aad-web": "C10",
    "asdw-web": "C10",
    "adfd": "C10",
    "adfdv": "C10",
    "akm": "C11",
    "aqod": "C12",
    "adoc": "C13",
    "aas": "OPTIONS_TOP",
    "aag": "OPTIONS_TOP",
    "aagd": "OPTIONS_TOP",
    "autopilot": "OPTIONS_TOP",
}


# 仮想ワークフロー ID。Autopilot ON 時に `pick_target_step` / `summarize_requirements`
# から参照される。`workflow_registry.py` の WorkflowDef とは独立した GUI 内部 ID。
AUTOPILOT_PSEUDO_WORKFLOW_ID: str = "autopilot"
AUTOPILOT_PSEUDO_STEP_ID: str = "0"

# Autopilot ON 時に `docs/catalog/app-arch-catalog.md` を必須とするワークフロー集合。
# 根拠: ``hve/autopilot/plan_review_gap.py`` の ``_AUTOPILOT_IMPLICIT_REQUIRED_PATHS``
# と同じ集合。ARD/AAS のみ選択時は catalog が pre_phase 出力として生成される側
# （``hve/autopilot/planner.py`` の pre_phase_only モード）であり必須ではない。
_AUTOPILOT_CATALOG_REQUIRING_WORKFLOWS: Tuple[str, ...] = (
    "aad-web", "asdw-web", "adfd", "adfdv",
)


# --------------------------------------------------------------------------
# 入力フィールドキー（正準名）。
# 改訂により ``app_id`` / ``usecase_id`` は必須情報から除外。
# --------------------------------------------------------------------------

INPUT_FIELD_KEYS: Tuple[str, ...] = (
    "company_name",     # ARD Step 1 (Untargeted) 必須
    "target_business",  # ARD Step 2 (Targeted) 必須
    "resource_group",   # asdw-web / adfdv / aagd 必須
    "target_dirs",      # adoc 必須
)


# --------------------------------------------------------------------------
# 必須ファイル種別 → 解決対象パス
# 注: "ard_origin" は AttachmentPane の状態で判定するため本テーブルでは扱わない。
# --------------------------------------------------------------------------

FILE_KIND_TO_SPEC: Dict[str, FileKindSpec] = {
    "business_requirement_md": FileKindSpec(
        paths=("docs/business-requirement.md",),
        logic="all",
        display_name="docs/business-requirement.md",
    ),
    "use_case_catalog": FileKindSpec(
        paths=("docs/catalog/use-case-catalog.md",),
        logic="all",
        display_name="docs/catalog/use-case-catalog.md",
    ),
    "app_catalog": FileKindSpec(
        paths=("docs/catalog/app-catalog.md",),
        logic="all",
        display_name="docs/catalog/app-catalog.md",
    ),
    "dataflow_app_catalog": FileKindSpec(
        paths=("docs/dataflow/dataflow-app-catalog.md",),
        logic="all",
        display_name="docs/dataflow/dataflow-app-catalog.md",
    ),
    "original_docs": FileKindSpec(
        paths=("original-docs/",),
        logic="all",
        display_name="original-docs/ 配下",
    ),
    "original_docs_or_qa": FileKindSpec(
        paths=("original-docs/", "qa/"),
        logic="any",
        display_name="original-docs/ または qa/ 配下",
    ),
}


# --------------------------------------------------------------------------
# 要件テーブル本体
# --------------------------------------------------------------------------

REQUIREMENT_TABLE: Dict[Tuple[str, str], StepRequirement] = {}


def _add(req: StepRequirement) -> None:
    REQUIREMENT_TABLE[(req.workflow_id, req.step_id)] = req


# ---- ARD（グループ ID 単位） ----
_add(StepRequirement(
    workflow_id="ard", step_id="1",
    required_info_keys=("company_name",),
    required_info_logic="all",
    required_file_kind=None,
    guidance_text=(
        "事業分野候補列挙（Untargeted）には対象企業名の指定が必須です。"
    ),
))
_add(StepRequirement(
    workflow_id="ard", step_id="2",
    required_info_keys=("target_business",),
    required_info_logic="all",
    required_file_kind=None,
    guidance_text=(
        "対象業務深掘り分析（Targeted）には業務エリア（target_business）の指定が必須です。"
        "添付資料を投入する場合は「★ 起点」を 1 つ選択してください。"
    ),
))
_add(StepRequirement(
    workflow_id="ard", step_id="3",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="business_requirement_md",
    guidance_text=(
        "KPI/OKR 定義（任意）は事業要件文書 docs/business-requirement.md を根拠とします。"
        "同セッション内で ARD Step 2 を ON にするか、既に当該ファイルが存在する状態で実行してください。"
    ),
))
_add(StepRequirement(
    workflow_id="ard", step_id="4",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="business_requirement_md",
    guidance_text=(
        "ユースケース作成は docs/business-requirement.md を入力とします。"
        "同セッション内で ARD Step 2 を ON にするか、既に当該ファイルが存在する状態で実行してください。"
    ),
))

# ---- AAS ----
_add(StepRequirement(
    workflow_id="aas", step_id="1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="use_case_catalog",
    guidance_text=(
        "アーキテクチャ設計は docs/catalog/use-case-catalog.md を入力とします。"
        "ARD ワークフローを先に実行するか、当該ファイルを配置してください。"
    ),
))

# ---- AAD-WEB ----
_add(StepRequirement(
    workflow_id="aad-web", step_id="1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="app_catalog",
    guidance_text=(
        "Web App 設計は docs/catalog/app-catalog.md を入力とします。"
        "AAS を先に実行するか、当該ファイルを配置してください。"
        "対象 APP-ID は任意指定（省略時はカタログ内全 APP が対象）。"
    ),
))

# ---- ASDW-WEB ----
_add(StepRequirement(
    workflow_id="asdw-web", step_id="1.1",
    required_info_keys=("resource_group",),
    required_info_logic="all",
    required_file_kind="app_catalog",
    guidance_text=(
        "Web App 実装・デプロイには Azure リソースグループ名と "
        "docs/catalog/app-catalog.md が必須です。"
        "対象 APP-ID は任意指定（省略時はカタログ内全 APP が対象）。"
    ),
))

# ---- ADFD ----
_add(StepRequirement(
    workflow_id="adfd", step_id="1.1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="use_case_catalog",
    guidance_text=(
        "データフロー設計は docs/catalog/use-case-catalog.md を入力とします。"
        "対象 APP-ID は任意指定（省略時はカタログ内全 APP が対象）。"
    ),
))

# ---- ADFDV ----
_add(StepRequirement(
    workflow_id="adfdv", step_id="1.1",
    required_info_keys=("resource_group",),
    required_info_logic="all",
    required_file_kind="dataflow_app_catalog",
    guidance_text=(
        "データフロー実装・デプロイには Azure リソースグループ名と "
        "docs/dataflow/dataflow-app-catalog.md が必須です。"
        "対象 APP-ID は任意指定（省略時はカタログ内全 APP が対象）。"
    ),
))

# ---- AAG ----
_add(StepRequirement(
    workflow_id="aag", step_id="1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="app_catalog",
    guidance_text=(
        "AI Agent 設計は docs/catalog/app-catalog.md を入力とします。"
        "対象 APP-ID / ユースケース ID は任意指定（省略時はカタログ全体が対象）。"
    ),
))

# ---- AAGD ----
_add(StepRequirement(
    workflow_id="aagd", step_id="1",
    required_info_keys=("resource_group",),
    required_info_logic="all",
    required_file_kind="app_catalog",
    guidance_text=(
        "AI Agent 実装・デプロイには Azure リソースグループ名と "
        "docs/catalog/app-catalog.md が必須です。"
        "対象 APP-ID / ユースケース ID は任意指定。"
    ),
))

# ---- AKM ----
_add(StepRequirement(
    workflow_id="akm", step_id="1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="original_docs_or_qa",
    guidance_text=(
        "knowledge/ ドキュメント生成には original-docs/ または qa/ 配下のいずれかに "
        "ソースファイルが配置されている必要があります。"
    ),
))

# ---- AQOD ----
_add(StepRequirement(
    workflow_id="aqod", step_id="1",
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind="original_docs",
    guidance_text=(
        "original-docs レビューには original-docs/ 配下に対象ファイルが "
        "配置されている必要があります。"
    ),
))

# ---- ADOC ----
_add(StepRequirement(
    workflow_id="adoc", step_id="1",
    required_info_keys=("target_dirs",),
    required_info_logic="all",
    required_file_kind=None,
    guidance_text=(
        "ソースコードからのドキュメント生成には、ドキュメント生成対象ディレクトリ "
        "（target_dirs）の指定が必須です。"
    ),
))


# ---- Autopilot（仮想ワークフロー） ----
# Autopilot ON 時はカタログから実行ワークフローが自動判定され、UI 上は個別
# ワークフロー選択がグレーアウトされる。バナー / Precheck の両方で本エントリ
# 1 件のみを評価し、カタログファイル本体の存在のみを確認する。
# 実際のカタログパスは可変（GUI の page_workflow.autopilot_catalog_path()）のため、
# required_file_kind は使わず summarize_requirements 側で動的にパスを差し込む。
_add(StepRequirement(
    workflow_id=AUTOPILOT_PSEUDO_WORKFLOW_ID,
    step_id=AUTOPILOT_PSEUDO_STEP_ID,
    required_info_keys=(),
    required_info_logic="none",
    required_file_kind=None,
    guidance_text=(
        "Autopilot モードでは Application Architecture Catalog "
        "（既定: docs/catalog/app-arch-catalog.md）から実行ワークフローを自動判定します。"
        "カタログファイルが存在することが必須です。"
    ),
))


# --------------------------------------------------------------------------
# 公開ユーティリティ
# --------------------------------------------------------------------------


def get_requirement(workflow_id: str, step_id: str) -> Optional[StepRequirement]:
    """指定 (workflow_id, step_id) の要件定義を返す。未定義なら None。"""
    return REQUIREMENT_TABLE.get((workflow_id, step_id))


def all_defined_keys() -> List[Tuple[str, str]]:
    """REQUIREMENT_TABLE に登録されたすべての (workflow_id, step_id) を返す。"""
    return sorted(REQUIREMENT_TABLE.keys())


def get_file_kind_spec(kind: str) -> Optional[FileKindSpec]:
    """必須ファイル種別から FileKindSpec を取得。未定義なら None。"""
    return FILE_KIND_TO_SPEC.get(kind)


# --------------------------------------------------------------------------
# Task A-2: 純関数 — ターゲットステップ選択 / 要件サマリー生成
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RequirementItem:
    """サマリー内の 1 項目（情報フィールド or ファイル）。

    status:
      - "ok":   充足
      - "warn": 未充足（警告表示）
      - "info": 中立情報（任意項目で未入力 等）
    """

    label: str
    status: str  # "ok" / "warn" / "info"
    detail: str = ""


@dataclass(frozen=True)
class RequirementsSummary:
    """バナーに表示する要件サマリーの最終形。Widget 非依存。"""

    workflow_id: str
    step_id: str
    section: str  # 配置先セクション識別子（"C14" / "C10" / "OPTIONS_TOP" 等）
    overall_status: str  # "ok" / "warn" / "none"
    guidance_text: str
    items: Tuple[RequirementItem, ...] = field(default_factory=tuple)


def _natural_step_key(step_id: str) -> Tuple[int, ...]:
    """ステップ ID を自然順比較用タプルに変換する。

    例: "1" → (1,), "1.1" → (1, 1), "2.3T" → (2, 3, 9999)
    数値変換できない要素は 9999 として末尾扱い（決定論的）。
    """
    parts = step_id.split(".")
    result: List[int] = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(9999)
    return tuple(result)


def pick_target_step(
    selected: Sequence[Tuple[str, Sequence[str]]],
    priority: Sequence[str] = WORKFLOW_PRIORITY,
) -> Optional[Tuple[str, str]]:
    """選択中の (workflow_id, step_ids) 群から、表示対象 1 件を決定する。

    決定ロジック（プラン §1 #5 = A, §1 #2 = A）:
      1. ``priority`` 登録順で先に出てくるワークフローを選ぶ。
      2. そのワークフローの選択ステップから、自然順最小のステップ ID を選ぶ。
      3. ``REQUIREMENT_TABLE`` に該当エントリが無い場合は次優先ワークフローへ。

    Args:
        selected: [(workflow_id, [step_id, ...]), ...]
        priority: ワークフロー優先順位（既定: WORKFLOW_PRIORITY）。

    Returns:
        (workflow_id, step_id) または None（対象なし）。
    """
    by_wf: Dict[str, List[str]] = {wf: list(steps) for wf, steps in selected if steps}
    for wf in priority:
        steps = by_wf.get(wf)
        if not steps:
            continue
        # REQUIREMENT_TABLE に存在するエントリの中で最小を選ぶ
        candidates = [s for s in steps if (wf, s) in REQUIREMENT_TABLE]
        if not candidates:
            continue
        chosen = min(candidates, key=_natural_step_key)
        return (wf, chosen)
    return None


def _eval_info_status(
    keys: Sequence[str],
    logic: str,
    input_values: Dict[str, str],
) -> Tuple[str, List[RequirementItem]]:
    """必須情報キー群の充足状態を評価し、(overall, items) を返す。"""
    items: List[RequirementItem] = []
    if not keys:
        return ("ok", items)

    filled: List[bool] = []
    for k in keys:
        v = (input_values.get(k) or "").strip()
        if v:
            items.append(RequirementItem(label=k, status="ok", detail="入力済み"))
            filled.append(True)
        else:
            items.append(RequirementItem(label=k, status="warn", detail="未入力"))
            filled.append(False)

    if logic == "all":
        overall = "ok" if all(filled) else "warn"
    elif logic == "any":
        overall = "ok" if any(filled) else "warn"
    else:  # "none"
        overall = "ok"
    return (overall, items)


def _eval_file_status(
    kind: Optional[str],
    file_exists: Callable[[str], bool],
) -> Tuple[str, List[RequirementItem]]:
    """必須ファイル種別の充足状態を評価し、(overall, items) を返す。"""
    items: List[RequirementItem] = []
    if not kind:
        return ("ok", items)

    spec = FILE_KIND_TO_SPEC.get(kind)
    if spec is None:
        # 定義なしの kind は無視（警告にしない）
        return ("ok", items)

    results = [file_exists(p) for p in spec.paths]
    for p, ok in zip(spec.paths, results):
        items.append(RequirementItem(
            label=p,
            status="ok" if ok else "warn",
            detail="存在" if ok else "未配置",
        ))

    if spec.logic == "any":
        overall = "ok" if any(results) else "warn"
    else:  # "all"
        overall = "ok" if all(results) else "warn"
    return (overall, items)


def _eval_ard_origin_status(
    workflow_id: str,
    step_id: str,
    attached_count: int,
    origin_chosen: bool,
) -> Tuple[str, List[RequirementItem]]:
    """ARD Step 2 専用: 添付資料の★起点選択状態を評価する。

    プラン §5 受け入れ条件 6:
      - 添付 0 件 → 警告対象外（status=ok）
      - 添付 >=1 件 + 起点未選択 → warn
      - 添付 >=1 件 + 起点選択済み → ok
    """
    if not (workflow_id == "ard" and step_id == "2"):
        return ("ok", [])
    if attached_count <= 0:
        return ("ok", [])
    if origin_chosen:
        return ("ok", [RequirementItem(
            label="★ 起点ファイル",
            status="ok",
            detail="選択済み",
        )])
    return ("warn", [RequirementItem(
        label="★ 起点ファイル",
        status="warn",
        detail=f"添付 {attached_count} 件: 起点を 1 つ選択してください",
    )])


def summarize_requirements(
    workflow_id: str,
    step_id: str,
    *,
    input_values: Optional[Dict[str, str]] = None,
    file_exists: Optional[Callable[[str], bool]] = None,
    attached_count: int = 0,
    origin_chosen: bool = False,
    autopilot_catalog_path: Optional[str] = None,
) -> Optional[RequirementsSummary]:
    """指定された (workflow_id, step_id) の要件サマリーを生成する。

    Args:
        workflow_id: ワークフロー ID。``AUTOPILOT_PSEUDO_WORKFLOW_ID`` を指定すると
            Autopilot モード用のサマリーを生成する。
        step_id: ステップ ID。
        input_values: 必須情報キー → 入力値の辞書（None は空辞書扱い）。
        file_exists: ファイル/ディレクトリ存在判定関数（None なら常に False）。
        attached_count: ARD 添付資料の件数。
        origin_chosen: ARD 添付資料の起点が選択済みかどうか。
        autopilot_catalog_path: Autopilot モード時のカタログファイルパス（既定:
            ``docs/catalog/app-arch-catalog.md``）。``workflow_id`` が
            ``AUTOPILOT_PSEUDO_WORKFLOW_ID`` のときのみ使用される。

    Returns:
        RequirementsSummary、または該当要件未定義時は None。
    """
    req = REQUIREMENT_TABLE.get((workflow_id, step_id))
    if req is None:
        return None
    iv = input_values or {}
    fe = file_exists or (lambda _p: False)

    info_overall, info_items = _eval_info_status(
        req.required_info_keys, req.required_info_logic, iv,
    )
    file_overall, file_items = _eval_file_status(req.required_file_kind, fe)
    origin_overall, origin_items = _eval_ard_origin_status(
        workflow_id, step_id, attached_count, origin_chosen,
    )

    # Autopilot 専用: カタログファイル存在チェックを動的注入。
    autopilot_overall = "ok"
    autopilot_items: List[RequirementItem] = []
    if workflow_id == AUTOPILOT_PSEUDO_WORKFLOW_ID and step_id == AUTOPILOT_PSEUDO_STEP_ID:
        cat_path = autopilot_catalog_path or "docs/catalog/app-arch-catalog.md"
        cat_ok = fe(cat_path)
        autopilot_items.append(RequirementItem(
            label=cat_path,
            status="ok" if cat_ok else "warn",
            detail="存在" if cat_ok else "未配置",
        ))
        autopilot_overall = "ok" if cat_ok else "warn"

    # overall 集約: いずれかが warn なら warn、すべて ok なら ok。
    if "warn" in (info_overall, file_overall, origin_overall, autopilot_overall):
        overall = "warn"
    else:
        overall = "ok"

    all_items = (
        tuple(info_items)
        + tuple(file_items)
        + tuple(origin_items)
        + tuple(autopilot_items)
    )
    section = WORKFLOW_TO_SECTION.get(workflow_id, "OPTIONS_TOP")

    return RequirementsSummary(
        workflow_id=workflow_id,
        step_id=step_id,
        section=section,
        overall_status=overall,
        guidance_text=req.guidance_text,
        items=all_items,
    )


# --------------------------------------------------------------------------
# Task A-3: バナー / Precheck 共通入口
# --------------------------------------------------------------------------


def summarize_requirements_for_selection(
    selected: Sequence[Tuple[str, Sequence[str]]],
    *,
    input_values: Optional[Dict[str, str]] = None,
    file_exists: Optional[Callable[[str], bool]] = None,
    attached_count: int = 0,
    origin_chosen: bool = False,
    autopilot_mode: bool = False,
    autopilot_catalog_path: Optional[str] = None,
) -> List[RequirementsSummary]:
    """選択中の (workflow_id, step_ids) 群から、評価対象サマリーを生成する。

    バナー（リアルタイム表示）と Step 1 Precheck（[次へ] 押下時検査）の
    両方から呼ばれる **唯一の共通入口**。両者で同じ結果を返すために、本関数は
    **常に 0 件または 1 件のサマリー** を返す（バナー表示と完全一致）。

    決定ロジック:
      - ``autopilot_mode=True`` のとき:
        - ``selected`` 内に ``_AUTOPILOT_CATALOG_REQUIRING_WORKFLOWS``
          （aad-web / asdw-web / adfd / adfdv）のいずれかが **ステップ 1 件以上
          選択された状態で** 含まれる場合のみ、Autopilot 仮想ワークフローの
          単独サマリー 1 件を返す（``app-arch-catalog.md`` 存在チェックを実施）。
        - 上記に該当しない場合（例: ARD/AAS のみ選択）は、Autopilot OFF と
          同じく ``pick_target_step`` で最優先個別ワークフローの要件を返す。
          これにより Autopilot ON/OFF で同じ選択 → 同じ入力チェック結果に
          なる（``hve/autopilot/planner.py`` の pre_phase_only モードと整合）。
      - ``autopilot_mode=False`` のとき: ``pick_target_step`` と同じ優先度で
        最優先ワークフローの最小エントリステップを 1 件選び、そのサマリーのみを
        返す。下流ワークフロー（例: ARD+AAS 同時選択時の AAS）の入力は、
        上流ワークフロー（ARD）が同一セッション内で生成すると想定し検査しない。

    Args:
        selected: [(workflow_id, [step_id, ...]), ...]
        input_values: 共通の入力値辞書。
        file_exists: 共通のファイル存在判定関数。
        attached_count: ARD 添付件数。
        origin_chosen: ARD 起点選択状態。
        autopilot_mode: Autopilot ON フラグ。
        autopilot_catalog_path: Autopilot カタログパス（autopilot_mode のみ有効）。

    Returns:
        ``RequirementsSummary`` を 0〜1 件含むリスト。
    """
    if autopilot_mode:
        # Autopilot ON でも catalog を必要とする SE 系 WF が
        # 「ステップ 1 件以上選択」で含まれる場合のみ Autopilot 仮想サマリーを返す。
        se_requires_catalog = any(
            wf in _AUTOPILOT_CATALOG_REQUIRING_WORKFLOWS and len(list(steps)) > 0
            for wf, steps in selected
        )
        if se_requires_catalog:
            s = summarize_requirements(
                AUTOPILOT_PSEUDO_WORKFLOW_ID,
                AUTOPILOT_PSEUDO_STEP_ID,
                input_values=input_values,
                file_exists=file_exists,
                autopilot_catalog_path=autopilot_catalog_path,
            )
            return [s] if s is not None else []
        # SE 系未選択 → 通常モードと同じフォールバック（catalog 要件を出さない）

    target = pick_target_step(selected)
    if target is None:
        return []
    workflow_id, step_id = target
    s = summarize_requirements(
        workflow_id, step_id,
        input_values=input_values,
        file_exists=file_exists,
        attached_count=attached_count,
        origin_chosen=origin_chosen,
    )
    return [s] if s is not None else []

