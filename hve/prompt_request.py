"""hve.prompt_request — Prompt 版 request v1 の型・読込・検証（FR-PROMPT-02）。

Prompt 版は自然言語を repository Agent Skill が型付き request へ変換し、HVE Python
はその内容を **信用せず** に schema / registry / allowlist で再検証する。本モジュールは
その再検証だけを担い、自然言語の解釈を行わない。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .step_inputs import StepInputSpec, resolve_step_input_step_ids
from .workflow_registry import (
    canonicalize_workflow_id,
    get_workflow,
)

SCHEMA_VERSION = 1

_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "goal", "workflows", "settings_overrides", "execution_policy"}
)
_EXECUTION_POLICY_FIELDS = frozenset(
    {"unattended", "pre_approved_operations", "allow_public_exposure", "budget_note"}
)
# FR-PROMPT-13: 事前承認できる操作の固定 allowlist。
ALLOWED_PRE_APPROVED_OPERATIONS: frozenset[str] = frozenset({"azure_deploy"})
BUDGET_NOTE_MAX_CHARS = 200
# runner._RESOURCE_GROUP_RE と同一の規則（計画の承認範囲と実行時の範囲を一致させる）。
_RESOURCE_GROUP_RE = re.compile(r"^[-\w.()]{1,90}$")
_WORKFLOW_FIELDS = frozenset(
    {"workflow_id", "steps", "params", "input_aliases", "step_inputs"}
)
_ALIAS_FIELDS = frozenset({"canonical", "actual"})
_STEP_INPUT_FIELDS = frozenset({"step_id", "role", "canonical", "source"})

# `settings_overrides` で上書きしてよいキー。
#
# 除外方針:
#   - 資格情報・秘密（token / password / secret / credential / key）は名前ごと持ち込まない。
#   - 実行系（`cli_path` / `cli_url` / `mcp_config` / `repo_root` / 任意 env）は上書きさせない。
#   - Prompt CLI が所有する値（`dry_run` / `workbench` / `steps` / `workflow`）も対象外。
ALLOWED_SETTINGS_OVERRIDES: frozenset[str] = frozenset(
    {
        "model",
        "review_model",
        "qa_model",
        "akm_model",
        "reasoning_effort",
        "review_reasoning_effort",
        "qa_reasoning_effort",
        "akm_reasoning_effort",
        "context_tier",
        "akm_context_tier",
        "max_parallel",
        "timeout",
        "review_timeout",
        "auto_qa",
        "auto_contents_review",
        "verbosity",
        "branch",
        # FR-LOCAL-SURFACE-01 (a): ローカル 3 面で共有する shared setting。
        # いずれも GUI 設定画面に存在し、`OrchestrateArgs` へ同名の
        # フィールドがある（例外は `cloud_session_branch` で、保存 key は
        # `cloud_session_repository_branch`）。
        "enable_agentic_retrieval",
        "agentic_data_source_modes",
        "foundry_mcp_integration",
        "agentic_data_sources_hint",
        "agentic_existing_design_diff_only",
        "foundry_sku_fallback_policy",
        "enable_tool_search",
        # FR-MODEL-04: SDK Tool Search の defer_threshold。
        # 0 / 未指定は CLI へ渡さず SDK 既定へ委譲する。
        "tool_search_defer_threshold",
        "cloud_session_branch",
        "strict",
        # FR-KD-14: 知識源の run 単位指定（値は _validate_knowledge_overrides で検証する）。
        "workiq",
        "knowledge_sources",
    }
)


class PromptRequestError(ValueError):
    """request v1 の検証に失敗したことを表す。fail-closed で実行を止める。"""


@dataclass(frozen=True)
class InputAliasSpec:
    """request 上の入力別名宣言（安全性検証は `hve.input_aliases` が行う）。"""

    canonical: str
    actual: str


@dataclass(frozen=True)
class WorkflowRequest:
    workflow_id: str
    """registry の canonical ID。"""

    requested_workflow_id: str
    """request に書かれていた元の表記（計画へ明示するために保持）。"""

    steps: Tuple[str, ...] = ()
    params: Mapping[str, str] = field(default_factory=dict)
    input_aliases: Tuple[InputAliasSpec, ...] = ()
    step_inputs: Tuple[StepInputSpec, ...] = ()


@dataclass(frozen=True)
class ExecutionPolicy:
    """FR-PROMPT-13: 利用者が最初の依頼で宣言した事前承認の範囲。"""

    unattended: bool = False
    pre_approved_operations: Tuple[str, ...] = ()
    allow_public_exposure: bool = False
    budget_note: str = ""

    def to_dict(self) -> dict:
        return {
            "allow_public_exposure": self.allow_public_exposure,
            "budget_note": self.budget_note,
            "pre_approved_operations": list(self.pre_approved_operations),
            "unattended": self.unattended,
        }


@dataclass(frozen=True)
class PromptRequest:
    schema_version: int
    goal: str
    workflows: Tuple[WorkflowRequest, ...]
    settings_overrides: Mapping[str, Any] = field(default_factory=dict)
    execution_policy: "ExecutionPolicy | None" = None


def _require_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PromptRequestError(f"{where} は JSON object でなければなりません。")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: Iterable[str], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise PromptRequestError(
            f"{where} に未知のフィールドがあります: {', '.join(unknown)}"
        )


def _parse_alias(raw: Any, where: str) -> InputAliasSpec:
    data = _require_mapping(raw, where)
    _reject_unknown(data, _ALIAS_FIELDS, where)
    for key in ("canonical", "actual"):
        if key not in data:
            raise PromptRequestError(f"{where} に '{key}' がありません。")
        if not isinstance(data[key], str) or not data[key].strip():
            raise PromptRequestError(f"{where}.{key} は空でない文字列でなければなりません。")
    return InputAliasSpec(canonical=data["canonical"], actual=data["actual"])


def _parse_step_input(
    raw: Any,
    where: str,
    *,
    workflow: Any,
    selected_steps: Sequence[str],
) -> StepInputSpec:
    data = _require_mapping(raw, where)
    _reject_unknown(data, _STEP_INPUT_FIELDS, where)
    step_id = data.get("step_id")
    role = data.get("role")
    source = data.get("source")
    if not isinstance(step_id, str) or not step_id.strip():
        raise PromptRequestError(f"{where}.step_id は空でない文字列でなければなりません。")
    step = workflow.get_step(step_id)
    if step is None or step.is_container:
        raise PromptRequestError(f"{where}.step_id は実行Stepでなければなりません: {step_id!r}")
    if selected_steps:
        active = set(resolve_step_input_step_ids(workflow.id, selected_steps))
        if step_id not in active:
            raise PromptRequestError(
                f"{where}.step_id は選択されたstepsに含まれません: {step_id!r}"
            )
    if role not in {"additional", "substitute"}:
        raise PromptRequestError(
            f"{where}.role は additional / substitute のいずれかでなければなりません。"
        )
    if not isinstance(source, str) or not source.strip():
        raise PromptRequestError(f"{where}.source は空でない文字列でなければなりません。")
    canonical = data.get("canonical")
    if canonical is not None and (
        not isinstance(canonical, str) or not canonical.strip()
    ):
        raise PromptRequestError(f"{where}.canonical は空でない文字列でなければなりません。")
    if role == "substitute" and canonical is None:
        raise PromptRequestError(f"{where}.canonical は substitute で必須です。")
    return StepInputSpec(
        step_id=step_id,
        role=role,
        canonical=canonical,
        source=source,
    )


def _parse_workflow(raw: Any, index: int) -> WorkflowRequest:
    where = f"workflows[{index}]"
    data = _require_mapping(raw, where)
    _reject_unknown(data, _WORKFLOW_FIELDS, where)

    requested = data.get("workflow_id")
    if not isinstance(requested, str) or not requested.strip():
        raise PromptRequestError(f"{where}.workflow_id は空でない文字列でなければなりません。")

    canonical = canonicalize_workflow_id(requested)
    wf = get_workflow(canonical)
    if wf is None:
        raise PromptRequestError(
            f"{where}.workflow_id が registry に存在しません: {requested!r}"
        )

    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, (list, tuple)):
        raise PromptRequestError(f"{where}.steps は配列でなければなりません。")
    steps: list[str] = []
    known = {s.id for s in wf.steps}
    for step in raw_steps:
        if not isinstance(step, str):
            raise PromptRequestError(f"{where}.steps の要素は文字列でなければなりません。")
        if step not in known:
            raise PromptRequestError(
                f"{where}.steps に Workflow '{canonical}' へ存在しない Step があります: {step!r}"
            )
        steps.append(step)

    raw_params = data.get("params", {})
    params_map = _require_mapping(raw_params, f"{where}.params")
    allowed_params = set(wf.params)
    params: dict[str, str] = {}
    for key, value in params_map.items():
        if key not in allowed_params:
            raise PromptRequestError(
                f"{where}.params に Workflow '{canonical}' が宣言していないパラメータがあります: {key!r}"
            )
        if not isinstance(value, str):
            raise PromptRequestError(f"{where}.params.{key} は文字列でなければなりません。")
        params[key] = value

    raw_aliases = data.get("input_aliases", [])
    if not isinstance(raw_aliases, (list, tuple)):
        raise PromptRequestError(f"{where}.input_aliases は配列でなければなりません。")
    aliases = tuple(
        _parse_alias(item, f"{where}.input_aliases[{i}]")
        for i, item in enumerate(raw_aliases)
    )

    raw_step_inputs = data.get("step_inputs", [])
    if not isinstance(raw_step_inputs, (list, tuple)):
        raise PromptRequestError(f"{where}.step_inputs は配列でなければなりません。")
    step_inputs = tuple(
        _parse_step_input(
            item,
            f"{where}.step_inputs[{i}]",
            workflow=wf,
            selected_steps=steps,
        )
        for i, item in enumerate(raw_step_inputs)
    )

    return WorkflowRequest(
        workflow_id=canonical,
        requested_workflow_id=requested,
        steps=tuple(steps),
        params=params,
        input_aliases=aliases,
        step_inputs=step_inputs,
    )


def _validate_knowledge_overrides(overrides: Mapping[str, Any]) -> None:
    """FR-KD-14: `workiq` は真偽値、`knowledge_sources` は FR-KD-01 の名前規則に合う文字列。"""
    if "workiq" in overrides and not isinstance(overrides["workiq"], bool):
        raise PromptRequestError("settings_overrides.workiq は真偽値でなければなりません。")
    if "knowledge_sources" in overrides:
        value = overrides["knowledge_sources"]
        if not isinstance(value, str):
            raise PromptRequestError(
                "settings_overrides.knowledge_sources はカンマ区切りの文字列でなければなりません。"
            )
        from .knowledge_discovery import parse_source_names

        try:
            parse_source_names([value], strict=True)
        except ValueError as exc:
            raise PromptRequestError(
                f"settings_overrides.knowledge_sources に不正な知識源名があります: {exc}"
            ) from exc


def _parse_bool(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise PromptRequestError(f"execution_policy.{key} は真偽値でなければなりません。")
    return value


def _parse_execution_policy(
    raw: Any, workflows: Tuple[WorkflowRequest, ...]
) -> ExecutionPolicy:
    data = _require_mapping(raw, "execution_policy")
    _reject_unknown(data, _EXECUTION_POLICY_FIELDS, "execution_policy")

    raw_ops = data.get("pre_approved_operations", [])
    if not isinstance(raw_ops, (list, tuple)):
        raise PromptRequestError("execution_policy.pre_approved_operations は配列でなければなりません。")
    operations: list[str] = []
    for op in raw_ops:
        if not isinstance(op, str) or op not in ALLOWED_PRE_APPROVED_OPERATIONS:
            raise PromptRequestError(
                "execution_policy.pre_approved_operations に許可されていない操作があります: "
                f"{op!r}（許可: {', '.join(sorted(ALLOWED_PRE_APPROVED_OPERATIONS))}）"
            )
        if op not in operations:
            operations.append(op)

    budget_note = data.get("budget_note", "")
    if not isinstance(budget_note, str):
        raise PromptRequestError("execution_policy.budget_note は文字列でなければなりません。")
    if len(budget_note) > BUDGET_NOTE_MAX_CHARS or any(
        ord(ch) < 0x20 or ord(ch) == 0x7F for ch in budget_note
    ):
        raise PromptRequestError(
            f"execution_policy.budget_note は {BUDGET_NOTE_MAX_CHARS} 文字以内で、"
            "改行・制御文字を含まない文字列でなければなりません。"
        )

    if "azure_deploy" in operations:
        # デプロイの事前承認は、宣言した resource_group の範囲に限る。
        deploying = [
            wf
            for wf in workflows
            if "resource_group" in getattr(get_workflow(wf.workflow_id), "params", ())
        ]
        if not deploying:
            raise PromptRequestError(
                "execution_policy の azure_deploy には、resource_group を持つ Workflow の選択が必要です。"
            )
        for wf in deploying:
            if not str(wf.params.get("resource_group", "")).strip():
                raise PromptRequestError(
                    f"execution_policy の azure_deploy には workflows[{wf.workflow_id}].params.resource_group が必要です。"
                )

    for wf in workflows:
        rg = wf.params.get("resource_group")
        if rg is not None and str(rg).strip() and not _RESOURCE_GROUP_RE.fullmatch(str(rg).strip()):
            raise PromptRequestError(
                f"workflows[{wf.workflow_id}].params.resource_group は Azure のリソースグループ名の規則"
                "（英数字・`-`・`_`・`.`・`(`・`)`、90 文字以内）に従う必要があります。"
            )

    return ExecutionPolicy(
        unattended=_parse_bool(data, "unattended"),
        pre_approved_operations=tuple(operations),
        allow_public_exposure=_parse_bool(data, "allow_public_exposure"),
        budget_note=budget_note,
    )


def parse_request(data: Any) -> PromptRequest:
    """検証済みの `PromptRequest` を返す。不正なら `PromptRequestError`。"""
    root = _require_mapping(data, "request")
    _reject_unknown(root, _TOP_LEVEL_FIELDS, "request")

    version = root.get("schema_version")
    # `bool` は `int` の派生だが schema version としては受理しない。
    if isinstance(version, bool) or not isinstance(version, int):
        raise PromptRequestError("schema_version は整数でなければなりません。")
    if version != SCHEMA_VERSION:
        raise PromptRequestError(
            f"未知の schema_version です: {version}（対応は {SCHEMA_VERSION} のみ）"
        )

    goal = root.get("goal", "")
    if not isinstance(goal, str):
        raise PromptRequestError("goal は文字列でなければなりません。")

    raw_workflows = root.get("workflows")
    if not isinstance(raw_workflows, (list, tuple)) or not raw_workflows:
        raise PromptRequestError("workflows は 1 件以上の配列でなければなりません。")

    workflows = tuple(_parse_workflow(item, i) for i, item in enumerate(raw_workflows))
    seen: set[str] = set()
    for wf in workflows:
        if wf.workflow_id in seen:
            raise PromptRequestError(
                f"同じ Workflow が重複しています: {wf.workflow_id!r}"
                f"（別名解決後に一致するものを含む）"
            )
        seen.add(wf.workflow_id)

    overrides_map = _require_mapping(
        root.get("settings_overrides", {}), "settings_overrides"
    )
    rejected = sorted(set(overrides_map) - ALLOWED_SETTINGS_OVERRIDES)
    if rejected:
        raise PromptRequestError(
            "settings_overrides に許可されていないキーがあります: " + ", ".join(rejected)
        )
    _validate_knowledge_overrides(overrides_map)

    execution_policy = (
        _parse_execution_policy(root["execution_policy"], workflows)
        if "execution_policy" in root
        else None
    )

    return PromptRequest(
        schema_version=version,
        goal=goal,
        workflows=workflows,
        settings_overrides=dict(overrides_map),
        execution_policy=execution_policy,
    )


def _reject_duplicate_keys(pairs: Sequence[Tuple[str, Any]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise PromptRequestError(f"JSON に重複キーがあります: {key!r}")
        seen[key] = value
    return seen


def load_request(path: "str | Path") -> PromptRequest:
    """UTF-8 JSON の request ファイルを読み込んで検証する。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptRequestError(f"request ファイルを読み込めません: {p} ({exc})") from exc
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise PromptRequestError(f"request ファイルの JSON が不正です: {p} ({exc})") from exc
    return parse_request(data)
