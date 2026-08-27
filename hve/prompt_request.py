"""hve.prompt_request — Prompt 版 request v1 の型・読込・検証（FR-PROMPT-02）。

Prompt 版は自然言語を repository Agent Skill が型付き request へ変換し、HVE Python
はその内容を **信用せず** に schema / registry / allowlist で再検証する。本モジュールは
その再検証だけを担い、自然言語の解釈を行わない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Tuple

from .workflow_registry import canonicalize_workflow_id, get_workflow

SCHEMA_VERSION = 1

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "goal", "workflows", "settings_overrides"})
_WORKFLOW_FIELDS = frozenset({"workflow_id", "steps", "params", "input_aliases"})
_ALIAS_FIELDS = frozenset({"canonical", "actual"})

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
        "cloud_session_branch",
        "strict",
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


@dataclass(frozen=True)
class PromptRequest:
    schema_version: int
    goal: str
    workflows: Tuple[WorkflowRequest, ...]
    settings_overrides: Mapping[str, Any] = field(default_factory=dict)


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

    return WorkflowRequest(
        workflow_id=canonical,
        requested_workflow_id=requested,
        steps=tuple(steps),
        params=params,
        input_aliases=aliases,
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

    return PromptRequest(
        schema_version=version,
        goal=goal,
        workflows=workflows,
        settings_overrides=dict(overrides_map),
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
