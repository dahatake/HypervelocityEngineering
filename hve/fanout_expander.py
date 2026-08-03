"""fanout_expander.py — Fan-out 対応 WorkflowDef 変換 (ADR-0002)

`WorkflowDef` 内で fan-out 指定された StepDef を、N 個の合成 StepDef に展開する。
DAGExecutor は展開後のフラットなステップ集合だけを見ればよく、既存の DAG 走査ロジックを
変更せずに 21 並列等の真の並列度を実現できる。

== 展開仕様 ==
- ベース StepDef ``id="1"`` に ``fanout_static_keys=["D01",...,"D21"]`` 指定時:
  - 21 個の合成 StepDef を生成。
  - 各 ``id = "1/D01"``, ``"1/D02"`` ... ``"1/D21"``。
  - 元の ``depends_on`` を継承（並列展開のため互いには依存しない）。
- 動的 fan-out (``fanout_parser`` 指定): catalog_parsers でキー解決。
- 下流 StepDef の ``depends_on`` 内に展開対象 ID が含まれている場合は、
  N 個の合成 ID 全てに置換（AND join → 全件完了で下流起動）。
- 空展開 (K-1): 展開キー 0 件 → そのベース ID をそのまま skip 候補として残し、
  呼び出し側が ``fanout-empty`` 理由で skip 化する。

== 公開 API ==
- ``expand_workflow_fanout(workflow, repo_root) -> ExpandedWorkflow``
- ``ExpandedWorkflow``: 展開後の steps と、ベース ID → 子 ID のマップを持つ。
- ``FanoutChildStep``: 合成 StepDef 互換オブジェクト。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

try:
    from .catalog_parsers import (
        parse_catalog,
        parse_service_app_mapping,
        CatalogParseError,
        KNOWN_PARSERS,
    )
    from .workflow_registry import StepDef, WorkflowDef
except ImportError:  # pragma: no cover - script execution
    from catalog_parsers import (  # type: ignore[no-redef]
        parse_catalog,
        parse_service_app_mapping,
        CatalogParseError,
        KNOWN_PARSERS,
    )
    from workflow_registry import StepDef, WorkflowDef  # type: ignore[no-redef]


# APP-ID フィルタ対象 parser 一覧（C'-1 採用範囲）。
# - app_catalog: キー自体が APP-NN → 完全一致で判定。
# - screen_catalog: キーが APP-NN-S### 形式 → 先頭 APP-NN をプレフィックス抽出して判定。
# - service_catalog: parse_service_app_mapping で SVC→[APP] を取得し、いずれかが
#   app_ids に含まれる SVC のみ残す。
# - dataflow_catalog: AAS の共通カタログ ``docs/catalog/app-catalog.md`` を
#   参照するため、キー形式は app_catalog と同じく APP-NN → 完全一致で判定。
#
# 未掲載 parser (agent_catalog / business_candidate / use_case_skeleton) は
# app_ids が指定されていても素通し（フィルタしない）。
# agent はカタログ実体およびスキーマ未確定のため対象外。
# business / use_case は ARD 系で APP-ID と無関係。
_APP_ID_FILTERABLE_PARSERS: FrozenSet[str] = frozenset({
    "app_catalog",
    "screen_catalog",
    "service_catalog",
    "dataflow_catalog",
})

# screen_catalog キーから APP-ID プレフィックスを抽出する正規表現。
# キー形式: ``APP-NN-S###`` または ``APP-NNN-S###``。
# ``startswith`` ベースだと "APP-10" が "APP-100" 配下を誤マッチするため、
# 必ず正規表現グループで厳密抽出する。
_SCREEN_KEY_PREFIX_RE = re.compile(r"^(APP-\d{2,3})-")

# ``output_paths_template`` で使える「fan-out キーの意味的別名」プレースホルダ。
# io-contract / prompt / template 側は ``{screenId}`` ``{serviceId}`` のような
# 意味名で成果物パスを表記するため、レジストリ側でも同じ表記を宣言できるようにする
# （FR-FANOUT-OUT-01）。
#
# 登録してよいのは「その parser が返す fan-out キーそのもの」を指す名前だけ。
# 名前は catalog_parsers の各 parser が抽出する ID 体系に一致させること:
#   app_catalog / dataflow_catalog → ``APP-NN``（dataflow_catalog も APP-ID を返す）
#   screen_catalog → ``APP-NN-S###`` / service_catalog → ``SVC-*``
#   agent_catalog → ``AGT-*`` / business_candidate → ``BIZ-NN``
#   use_case_skeleton → ``UC-*``
# ``{screenNameSlug}`` のような「キーから導出できない属性」は登録しない
# （catalog parser が名称スラッグを返さないため、置換すると実在しないパスを宣言してしまう）。
_KEY_ALIAS_PLACEHOLDERS_BY_PARSER: Dict[str, Tuple[str, ...]] = {
    "app_catalog": ("appId",),
    "screen_catalog": ("screenId",),
    "service_catalog": ("serviceId",),
    "dataflow_catalog": ("appId",),
    "agent_catalog": ("agentId",),
    "business_candidate": ("businessId",),
    "use_case_skeleton": ("useCaseId",),
}

# 置換後に残るプレースホルダ表記（``{...}`` / ``<...>``）の検出。
_UNRESOLVED_PLACEHOLDER_RE = re.compile(r"[{<][^{}<>]*[}>]")

# 確定ファイルパスではないと判定する glob メタ文字。
_GLOB_CHARS: Tuple[str, ...] = ("*", "?")


def _key_placeholder_names(step: Any) -> Tuple[str, ...]:
    """当該 StepDef で fan-out キーへ解決してよいプレースホルダ名を返す。

    ``{key}`` は常に有効（後方互換）。``fanout_parser`` 指定時のみ、その parser
    に対応する ID 別名を追加する。静的キー（``fanout_static_keys``）の Step は
    ID 体系が parser に紐付かないため ``{key}`` のみ。
    """
    names: List[str] = ["key"]
    parser = getattr(step, "fanout_parser", None)
    if parser:
        names.extend(_KEY_ALIAS_PLACEHOLDERS_BY_PARSER.get(parser, ()))
    return tuple(names)


def _substitute_key_placeholders(
    path: str,
    key: str,
    placeholder_names: Tuple[str, ...],
) -> str:
    """``{key}`` およびキー別名プレースホルダを fan-out キーへ置換する。"""
    resolved = path or ""
    for name in placeholder_names:
        resolved = resolved.replace("{" + name + "}", key)
    return resolved


def _resolve_output_path_template(
    path: str,
    key: str,
    placeholder_names: Tuple[str, ...],
    directory_prefixes: Tuple[str, ...] = (),
) -> Optional[str]:
    """``output_paths_template`` の 1 エントリを fan-out 子の具体 path へ解決する。

    確定ファイルパスへ解決できない場合は ``None`` を返し、呼び出し側は当該
    エントリを子ステップの ``output_paths`` に **載せない**。宣言しておいて
    実在しないパスを runner の output_paths ゲート（FR-WF-OUT-01）へ渡すと
    誤 fail になるため、fail-closed で落とす。

    載せない条件:
      - キー別名プレースホルダを 1 つも含まない（per-key 成果物ではなく、
        全 fan-out 子で同一 path になる）
      - 置換後もプレースホルダ（``{...}`` / ``<...>``）が残る
      - glob（``*`` / ``?``）を含む
      - ディレクトリ参照（末尾 ``/``）
      - 同一 template 内で宣言されたディレクトリ成果物の配下にある
        （ディレクトリ配下のファイル構成は Agent の裁量であり、個別ファイル単位で
        ゲートすると同一成果物でも構成差で誤 fail する）
    """
    if not path:
        return None
    tokens = tuple("{" + name + "}" for name in placeholder_names)
    if not any(token in path for token in tokens):
        return None
    resolved = _substitute_key_placeholders(path, key, placeholder_names)
    if _UNRESOLVED_PLACEHOLDER_RE.search(resolved):
        return None
    if any(ch in resolved for ch in _GLOB_CHARS):
        return None
    if resolved.endswith("/"):
        return None
    if any(resolved.startswith(prefix) for prefix in directory_prefixes):
        return None
    return resolved


def _declared_directory_prefixes(
    template: List[str],
    key: str,
    placeholder_names: Tuple[str, ...],
) -> Tuple[str, ...]:
    """template 内でディレクトリ成果物として宣言されたパス接頭辞を返す。"""
    prefixes: List[str] = []
    for path in template or []:
        resolved = _substitute_key_placeholders(str(path or ""), key, placeholder_names)
        if resolved.endswith("/") and resolved != "/":
            prefixes.append(resolved)
    return tuple(prefixes)


def resolve_output_path_prefix_gates(step: Any) -> List[str]:
    """FR-WF-OUT-10: drop されたエントリを prefix 存在ゲートへ降格する。

    ``_resolve_output_path_template`` が確定ファイルパスへ解決できず落とした
    エントリのうち、**fan-out キーを実際に含む** ものは「当該キーの成果物が
    存在するか」だけなら検証できる。キー出現位置の直後までを接頭辞として返し、
    呼び出し側は前方一致するファイル / ディレクトリの存在を検査する。

    完全パス一致や glob 一致ではなく接頭辞一致を採るのは、同一 run の生成物でも
    ``{id}-{slug}-description.md`` / ``{id}-description.md`` / ``{id}.md`` の
    ように命名が分岐する一方、**ID 接頭辞で始まる点だけは一貫している**という
    実地の証拠に基づく（FR-WF-OUT-08 / 10）。

    返さない条件:
      - fan-out していない（``fanout_key`` が空）
      - キー別名プレースホルダを 1 つも含まない（全 fan-out 子で同一パスになる）
      - 置換してもキーが現れない（parser が返さない ID 名を使っている。
        ADFDV の ``{jobId}`` 等、FR-WF-ADFDV-01）
      - 確定ファイルパスへ解決できる（通常の ``output_paths`` ゲートが担う）
    """
    key = str(getattr(step, "fanout_key", "") or "")
    if not key:
        return []
    template = list(getattr(step, "output_paths_template", None) or [])
    if not template:
        return []

    placeholder_names = _key_placeholder_names(step)
    tokens = tuple("{" + name + "}" for name in placeholder_names)
    gates: List[str] = []
    for path in template:
        raw = str(path or "")
        if not any(token in raw for token in tokens):
            continue
        if _resolve_output_path_template(raw, key, placeholder_names) is not None:
            continue
        resolved = _substitute_key_placeholders(raw, key, placeholder_names)
        index = resolved.find(key)
        if index < 0:
            continue
        prefix = resolved[: index + len(key)]
        if prefix and prefix not in gates:
            gates.append(prefix)
    return gates


@dataclass
class FanoutChildStep:
    """fan-out 展開後の合成 StepDef 互換オブジェクト。

    DAGExecutor / runner.py 側は ``step.id`` ``step.title`` ``step.custom_agent``
    ``step.depends_on`` ``step.body_template_path`` ``step.is_container``
    ``step.consumed_artifacts`` ``step.skip_fallback_deps`` ``step.block_unless``
    ``step.output_paths`` ``step.required_input_paths`` を参照する。
    fan-out 特有の追加属性 ``fanout_key`` ``base_step_id``
    ``additional_prompt_template_path`` ``per_key_mcp_servers``（基底の物そのまま）も持つ。
    """

    id: str
    title: str
    custom_agent: Optional[str]
    depends_on: List[str]
    body_template_path: Optional[str]
    is_container: bool
    skip_fallback_deps: List[str]
    block_unless: List[str]
    consumed_artifacts: Optional[List[str]]
    output_paths: List[str]
    required_input_paths: List[str]
    requires_remote_cicd: bool = False
    # fan-out 固有
    fanout_key: str = ""
    base_step_id: str = ""
    additional_prompt_template_path: Optional[str] = None
    per_key_mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None
    # ベース StepDef との互換性のため空属性
    fanout_static_keys: Optional[List[str]] = None
    fanout_parser: Optional[str] = None
    output_paths_template: Optional[List[str]] = None  # Sub-3: 親 StepDef の template を保持（参考用）
    # FR-DAG-07: ベース StepDef のパラメータ契約をそのまま継承する。
    # fan-out キーごとに必須パラメータが変わることはないため {key} 置換は行わない。
    required_params: List[str] = field(default_factory=list)
    default_params: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExpandedWorkflow:
    """fan-out 展開後のワークフロー snapshot。"""

    workflow_id: str
    steps: List[Any]
    """展開後の全ステップ（StepDef または FanoutChildStep）。"""

    fanout_map: Dict[str, List[str]] = field(default_factory=dict)
    """ベース step_id → 子 step_id リスト。0 件展開時はベース ID が key となり値が []。"""

    empty_fanout_ids: List[str] = field(default_factory=list)
    """0 件展開でスキップすべきベース step_id 一覧（K-1）。"""

    deferred_fanout_ids: List[str] = field(default_factory=list)
    """0 件展開のうち、同一実行内の upstream step が入力を生成する見込みの
    ベース step_id 一覧（T-C2）。orchestrator が empty_fanout_ids と差分集合を
    取って active から discard せず保持する判定に使う。
    本フィールド自体は ``expand_workflow_fanout`` では設定されず、
    orchestrator._expand_workflow_for_dag が後付けで設定する（呼び出し側責務）。"""

    max_parallel: Optional[int] = None
    """WorkflowDef.max_parallel をそのまま伝搬。"""


def _filter_keys_by_app_ids(
    parser: str,
    keys: List[str],
    app_ids: Optional[List[str]],
    repo_root: Path,
) -> List[str]:
    """fan-out 展開キーを app_ids で絞り込む。

    Args:
        parser: ``fanout_parser`` 名（``app_catalog`` 等）。
        keys: parser が返した展開キー全件。
        app_ids: GUI / CLI で指定された対象 APP-ID。``None`` または空リストの
            場合はフィルタを適用せず ``keys`` をそのまま返す（後方互換）。
        repo_root: 追加カタログ参照用ルート（``service_catalog`` の SVC→APP
            mapping 取得で使用）。

    Returns:
        絞り込み後のキーリスト。順序は ``keys`` の元順序を保持。
        ``parser`` がフィルタ対象外（``_APP_ID_FILTERABLE_PARSERS`` 外）の場合は
        ``keys`` をそのまま返す（明示パススルー）。
    """
    if not app_ids:
        return keys
    if parser not in _APP_ID_FILTERABLE_PARSERS:
        return keys
    app_ids_set = set(app_ids)
    if parser in ("app_catalog", "dataflow_catalog"):
        return [k for k in keys if k in app_ids_set]
    if parser == "screen_catalog":
        result: List[str] = []
        for k in keys:
            m = _SCREEN_KEY_PREFIX_RE.match(k)
            if m is not None and m.group(1) in app_ids_set:
                result.append(k)
        return result
    if parser == "service_catalog":
        try:
            svc_to_apps = parse_service_app_mapping(repo_root)
        except CatalogParseError:  # pragma: no cover - parser 例外時はフィルタ無効化
            return keys
        if not svc_to_apps:
            # mapping が取得できない場合はフィルタを適用しない（後方互換）。
            return keys
        result = []
        for k in keys:
            apps = svc_to_apps.get(k)
            if apps is None:
                continue
            if any(a in app_ids_set for a in apps):
                result.append(k)
        return result
    # 防御的（_APP_ID_FILTERABLE_PARSERS に追加され_filter_keys_by_app_ids 内で
    # 分岐未追加というケースを早期検出）
    return keys


def _resolve_keys(
    step: Any,
    repo_root: Path,
    *,
    app_ids: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """StepDef から fan-out キーを解決する。fan-out 非対象なら None。

    Args:
        step: 対象 StepDef。
        repo_root: catalog parser がカタログを探すルート。
        app_ids: GUI / CLI で指定された対象 APP-ID リスト。``None`` または空
            リストの場合はフィルタを適用せず全件返す。指定がある場合は
            ``_filter_keys_by_app_ids`` で絞り込む。
    """
    static_keys = getattr(step, "fanout_static_keys", None)
    if static_keys:
        return list(static_keys)
    parser = getattr(step, "fanout_parser", None)
    if not parser:
        return None
    if parser not in KNOWN_PARSERS:
        raise CatalogParseError(
            f"StepDef '{step.id}': 未登録の fanout_parser '{parser}'"
        )
    keys = parse_catalog(parser, repo_root)
    return _filter_keys_by_app_ids(parser, keys, app_ids, repo_root)


def _make_child(step: Any, key: str) -> FanoutChildStep:
    """ベース StepDef + key から合成 StepDef を生成する。"""
    child_id = f"{step.id}/{key}"
    # Sub-3 (Q3=b): output_paths_template のプレースホルダ置換で fan-out 子の
    # output_paths を構築する。FR-FANOUT-OUT-01 で ``{key}`` 以外の意味名
    # （``{screenId}`` 等）にも対応し、確定ファイルパスへ解決できないエントリは
    # 落とす（`_resolve_output_path_template` 参照）。
    # template が指定されていれば優先、それ以外は親の output_paths を継承する。
    template = getattr(step, "output_paths_template", None)
    if template:
        placeholder_names = _key_placeholder_names(step)
        directory_prefixes = _declared_directory_prefixes(
            template, key, placeholder_names
        )
        resolved_outputs = []
        for path in template:
            resolved = _resolve_output_path_template(
                path, key, placeholder_names, directory_prefixes
            )
            if resolved is not None and resolved not in resolved_outputs:
                resolved_outputs.append(resolved)
    else:
        resolved_outputs = list(getattr(step, "output_paths", []) or [])
    resolved_inputs = [
        p.replace("{key}", key)
        for p in (getattr(step, "required_input_paths", []) or [])
    ]
    return FanoutChildStep(
        id=child_id,
        title=f"{step.title} ({key})",
        custom_agent=getattr(step, "custom_agent", None),
        depends_on=list(getattr(step, "depends_on", []) or []),
        body_template_path=getattr(step, "body_template_path", None),
        is_container=False,
        skip_fallback_deps=list(getattr(step, "skip_fallback_deps", []) or []),
        block_unless=list(getattr(step, "block_unless", []) or []),
        consumed_artifacts=getattr(step, "consumed_artifacts", None),
        output_paths=resolved_outputs,
        required_input_paths=resolved_inputs,
        requires_remote_cicd=bool(getattr(step, "requires_remote_cicd", False)),
        fanout_key=key,
        base_step_id=step.id,
        additional_prompt_template_path=getattr(step, "additional_prompt_template_path", None),
        per_key_mcp_servers=getattr(step, "per_key_mcp_servers", None),
        required_params=list(getattr(step, "required_params", []) or []),
        default_params=dict(getattr(step, "default_params", {}) or {}),
    )


def expand_workflow_fanout(
    workflow: WorkflowDef,
    repo_root: Path,
    *,
    app_ids: Optional[List[str]] = None,
) -> ExpandedWorkflow:
    """WorkflowDef を fan-out 展開する。

    Args:
        workflow: 元の WorkflowDef。
        repo_root: 動的解決パーサが読み込むカタログのルート。
        app_ids: GUI / CLI で指定された対象 APP-ID リスト。``None`` または空
            リストの場合はフィルタを適用せず全件展開する（後方互換）。
            指定がある場合は ``_APP_ID_FILTERABLE_PARSERS`` 対象の fan-out
            キーを app_ids で絞り込む。フィルタ結果が 0 件になった base step
            は既存 K-1 (fanout-empty) 経路で skip される。

    Returns:
        展開後の steps と fanout_map を保持する ExpandedWorkflow。
    """
    fanout_map: Dict[str, List[str]] = {}
    empty_fanout_ids: List[str] = []
    children_by_base: Dict[str, List[FanoutChildStep]] = {}
    pass_through: List[Any] = []

    for step in workflow.steps:
        if getattr(step, "is_container", False):
            pass_through.append(step)
            continue
        keys = _resolve_keys(step, repo_root, app_ids=app_ids)
        if keys is None:
            pass_through.append(step)
            continue
        if not keys:
            # K-1: 0 件展開 → ベース ID をそのまま残し、呼び出し側で skip 化する
            empty_fanout_ids.append(step.id)
            pass_through.append(step)
            fanout_map[step.id] = []
            continue
        children = [_make_child(step, k) for k in keys]
        children_by_base[step.id] = children
        fanout_map[step.id] = [c.id for c in children]

    # 下流ステップの depends_on を子 ID リストへ置換（non-mutating: 必要時のみコピーを差し替え）
    def _remap_deps(step: Any) -> Any:
        deps = list(getattr(step, "depends_on", []) or [])
        if not deps:
            return step
        if not any(d in children_by_base for d in deps):
            return step
        new_deps: List[str] = []
        for d in deps:
            if d in children_by_base:
                new_deps.extend([c.id for c in children_by_base[d]])
            else:
                new_deps.append(d)
        # 元 StepDef を変異させない: dataclasses.replace で新インスタンス生成
        try:
            new_step = replace(step, depends_on=new_deps)
        except TypeError:
            # FanoutChildStep など replace 不可な型は属性差し替えで fallback
            new_step = step
            try:
                new_step.depends_on = new_deps  # type: ignore[attr-defined]
            except Exception:
                pass
        return new_step

    expanded_steps: List[Any] = [_remap_deps(s) for s in pass_through]

    # 子ステップを末尾に追加（並列展開）。fan-out 子自身の depends_on も
    # 親ベース ID（例: "A"）が children_by_base に含まれる場合は全子 ID リストへ
    # 張り替える（クロス積）。これを行わないと、`get_next_steps` のフォールバック
    # 「dep がレジストリに存在しない → 解決済み」が誤発火し、上流 fan-out 親の
    # 子が未完了でも下流 fan-out 親の子が起動してしまう（aad-web Step 2.3 等）。
    for base_id, children in children_by_base.items():
        for child in children:
            expanded_steps.append(_remap_deps(child))

    return ExpandedWorkflow(
        workflow_id=getattr(workflow, "id", "unknown"),
        steps=expanded_steps,
        fanout_map=fanout_map,
        empty_fanout_ids=empty_fanout_ids,
        max_parallel=getattr(workflow, "max_parallel", None),
    )


def expand_single_step_fanout(
    base_step: Any,
    repo_root: Path,
    *,
    app_ids: Optional[List[str]] = None,
) -> Optional[List[FanoutChildStep]]:
    """単一の fan-out base step を展開し、子 step リストを返す。

    DAGExecutor のランタイム再展開（deferred fan-out 経路）から呼び出される。
    `expand_workflow_fanout` 全体展開と異なり、下流 step の depends_on remap は
    行わない（呼び出し側が DAG mutate 時に自前で実施する）。

    Args:
        base_step: fan-out 対象のベース StepDef。
        repo_root: catalog parser がカタログファイルを探すルート。
        app_ids: GUI / CLI で指定された対象 APP-ID リスト。``None`` または空
            リストの場合はフィルタを適用せず全件展開する（後方互換）。
            指定がある場合は ``_APP_ID_FILTERABLE_PARSERS`` 対象の fan-out
            キーを app_ids で絞り込む。

    Returns:
        子 step (FanoutChildStep) のリスト。base_step が fan-out 非対象
        （``fanout_static_keys`` も ``fanout_parser`` も無い）の場合や、
        展開キーが 0 件だった場合は None。
    """
    keys = _resolve_keys(base_step, repo_root, app_ids=app_ids)
    if not keys:
        return None
    return [_make_child(base_step, k) for k in keys]
