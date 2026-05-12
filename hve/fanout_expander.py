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

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .catalog_parsers import parse_catalog, CatalogParseError, KNOWN_PARSERS
    from .workflow_registry import StepDef, WorkflowDef
except ImportError:  # pragma: no cover - script execution
    from catalog_parsers import parse_catalog, CatalogParseError, KNOWN_PARSERS  # type: ignore[no-redef]
    from workflow_registry import StepDef, WorkflowDef  # type: ignore[no-redef]


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
    # fan-out 固有
    fanout_key: str = ""
    base_step_id: str = ""
    additional_prompt_template_path: Optional[str] = None
    per_key_mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None
    # ベース StepDef との互換性のため空属性
    fanout_static_keys: Optional[List[str]] = None
    fanout_parser: Optional[str] = None
    output_paths_template: Optional[List[str]] = None  # Sub-3: 親 StepDef の template を保持（参考用）


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

    max_parallel: Optional[int] = None
    """WorkflowDef.max_parallel をそのまま伝搬。"""


def _resolve_keys(step: Any, repo_root: Path) -> Optional[List[str]]:
    """StepDef から fan-out キーを解決する。fan-out 非対象なら None。"""
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
    return parse_catalog(parser, repo_root)


def _make_child(step: Any, key: str) -> FanoutChildStep:
    """ベース StepDef + key から合成 StepDef を生成する。"""
    child_id = f"{step.id}/{key}"
    # Sub-3 (Q3=b): output_paths_template の {key} 置換で fan-out 子の output_paths を構築する。
    # template が指定されていれば優先、それ以外は親の output_paths を継承する。
    template = getattr(step, "output_paths_template", None)
    if template:
        resolved_outputs = [p.replace("{key}", key) for p in template]
    else:
        resolved_outputs = list(getattr(step, "output_paths", []) or [])
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
        required_input_paths=list(getattr(step, "required_input_paths", []) or []),
        fanout_key=key,
        base_step_id=step.id,
        additional_prompt_template_path=getattr(step, "additional_prompt_template_path", None),
        per_key_mcp_servers=getattr(step, "per_key_mcp_servers", None),
    )


def expand_workflow_fanout(
    workflow: WorkflowDef,
    repo_root: Path,
) -> ExpandedWorkflow:
    """WorkflowDef を fan-out 展開する。

    Args:
        workflow: 元の WorkflowDef。
        repo_root: 動的解決パーサが読み込むカタログのルート。

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
        keys = _resolve_keys(step, repo_root)
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
    expanded_steps: List[Any] = []
    for step in pass_through:
        deps = list(getattr(step, "depends_on", []) or [])
        if not deps:
            expanded_steps.append(step)
            continue
        if not any(d in children_by_base for d in deps):
            expanded_steps.append(step)
            continue
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
        expanded_steps.append(new_step)

    # 子ステップを末尾に追加（並列展開）
    for base_id, children in children_by_base.items():
        expanded_steps.extend(children)

    return ExpandedWorkflow(
        workflow_id=getattr(workflow, "id", "unknown"),
        steps=expanded_steps,
        fanout_map=fanout_map,
        empty_fanout_ids=empty_fanout_ids,
        max_parallel=getattr(workflow, "max_parallel", None),
    )
