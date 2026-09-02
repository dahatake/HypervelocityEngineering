"""Shared durable execution registration and resume planning.

The service owns the FR-STATE-05 / FR-CLI-90 decisions that must remain
identical across the CLI, GUI Plan, and Prompt surfaces.  It persists only a
fixed replay allowlist; free-form values are supplied again for one resume
attempt and are hashed, not stored.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import time
from typing import Any, Mapping, Sequence
import uuid

from .artifact_validation import find_missing_output_paths
from .fanout_expander import resolve_output_path_prefix_gates
from .run_state_store import (
    canonical_repo_root,
    DurableStateError,
    LeaseToken,
    RunStateStore,
    compute_repo_key,
    reject_sensitive_persisted_text,
)
from .startup_preflight import is_github_repository_slug


_ALLOWED_ACTIONS = frozenset({"reuse-session", "restart-step"})
_ALLOWED_MODES = frozenset({"standard"})
_RISK_ORDER = (
    "unsupported_mode",
    "active_owner",
    "failed",
    "non_terminal",
    "head_drift",
    "missing_output",
    "missing_replay_value",
    "sdk_missing",
    "sdk_in_use",
)

# Values in this allowlist are identifiers, numeric settings, or fixed enums.
# Free-form text, arbitrary paths, endpoints, credentials, and tool/MCP payloads
# are deliberately absent and become key-only replay gaps.
_REPLAY_VALUE_FLAGS = frozenset(
    {
        "--workflow",
        "--enable-agentic-retrieval",
        "--foundry-sku-fallback-policy",
        "--enable-tool-search",
        "--model",
        "--review-model",
        "--qa-model",
        "--akm-model",
        "--reasoning-effort",
        "--review-reasoning-effort",
        "--qa-reasoning-effort",
        "--akm-reasoning-effort",
        "--context-tier",
        "--akm-context-tier",
        "--max-parallel",
        "--qa-answer-mode",
        "--tool-search-ranking",
        "--workiq-dxx",
        "--workiq-per-question-timeout",
        "--workiq-request-timeout",
        "--issue-number",
        "--log-level",
        "--timestamp-style",
        "--timeout",
        "--review-timeout",
        "--steps",
        "--app-id",
        "--app-ids",
        "--resource-group",
        "--branch",
        "--cloud-session-owner",
        "--cloud-session-repository-name",
        "--cloud-session-branch",
        "--cloud-session-max-concurrency",
        "--repo",
        "--verbosity",
        "--workbench",
        "--workbench-body-lines",
        "--workbench-history",
        "--sources",
        "--data-location",
        "--data-resource-suffix",
        "--data-vnet-cidr",
        "--data-private-endpoint-subnet-cidr",
        "--data-aci-subnet-cidr",
        "--usecase-id",
        "--depth",
        "--max-file-lines",
        "--survey-base-date",
        "--survey-period-years",
        "--target-recommendation-id",
        "--tdd-max-retries",
        "--context-max-chars",
        "--self-improve-max-iterations",
        "--mdq-watch-debounce-ms",
        "--cq-watch-debounce-ms",
    }
)
_REPLAY_MULTI_VALUE_FLAGS = frozenset({"--agentic-data-source-modes"})
_REPLAY_BOOLEAN_FLAGS = frozenset(
    {
        "--strict",
        "--auto-qa",
        "--qa-akm-background-merge",
        "--force-interactive",
        "--auto-contents-review",
        "--auto-coding-agent-review",
        "--auto-coding-agent-review-auto-approval",
        "--workiq",
        "--workiq-akm-review",
        "--no-workiq-akm-review",
        "--no-self-improve",
        "--auto-compaction",
        "--no-auto-compaction",
        "--tool-search",
        "--no-tool-search",
        "--foundry-mcp-integration",
        "--no-foundry-mcp-integration",
        "--agentic-existing-design-diff-only",
        "--no-agentic-existing-design-diff-only",
        "--workiq-akm-ingest",
        "--no-workiq-akm-ingest",
        "--workiq-draft",
        "--create-issues",
        "--assign-copilot-agent",
        "--create-pr",
        "--create-working-branch",
        "--no-create-working-branch",
        "--approval-gates",
        "--no-color",
        "--screen-reader",
        "--quiet",
        "--verbose",
        "--show-stream",
        "--banner",
        "--no-banner",
        "--final-only",
        "--fleet-mode",
        "--no-fleet-mode",
        "--cloud-session",
        "--no-cloud-session",
        "--force-refresh",
        "--no-force-refresh",
        "--enable-auto-merge",
        "--delete-local-merged-branch",
        "--no-delete-local-merged-branch",
        "--include-kpi-okr",
        "--create-remote-mcp-server",
        "--no-create-remote-mcp-server",
        "--self-improve",
        "--mdq-watch",
        "--no-mdq-watch",
        "--cq-watch",
        "--no-cq-watch",
        "--workbench-flush-on-exit",
        "--no-workbench-flush-on-exit",
        "--unattended",
    }
)
_MISSING_VALUE_FLAGS = frozenset(
    {
        "--agentic-data-sources-hint",
        "--qa-ipc-dir",
        "--steering-ipc-dir",
        "--workiq-draft-output-dir",
        "--workiq-tenant-id",
        "--workiq-prompt-qa",
        "--workiq-prompt-km",
        "--workiq-prompt-review",
        "--mcp-config",
        "--cli-path",
        "--cli-url",
        "--cloud-session-integration-id",
        "--cloud-session-mc-base-url",
        "--cloud-session-step-overrides",
        "--cloud-session-subtask-overrides",
        "--focus-areas",
        "--purpose",
        "--target-dirs",
        "--exclude-patterns",
        "--doc-purpose",
        "--company-name",
        "--target-business",
        "--target-region",
        "--analysis-purpose",
        "--attached-docs",
        "--additional-prompt",
        "--issue-title",
        "--self-improve-goal",
        "--target-scope",
        "--self-improve-target-scope",
    }
)
_MISSING_MULTI_VALUE_FLAGS = frozenset(
    {"--ignore-paths", "--target-files", "--custom-source-dir"}
)
_MISSING_PAIR_FLAGS = frozenset({"--input-alias"})
_REJECTED_FLAGS = frozenset(
    {
        "--help",
        "--autopilot-chain",
        "--autopilot-dry-run",
        "--autopilot-catalog",
        "--autopilot-max-parallel",
        "--resume-run",
        "--execution-id",
        "--instance-id",
        "--expected-state-version",
        "--recovery-action",
        "--lease-owner",
        "--lease-generation",
        "--dry-run",
    }
)
_SHORT_FLAGS = {
    "-h": "--help",
    "-w": "--workflow",
    "-m": "--model",
    "-v": "--verbose",
    "-q": "--quiet",
}
_REPLAY_FLAG_BY_KEY = {
    "agentic_data_sources_hint": "--agentic-data-sources-hint",
    "qa_ipc_dir": "--qa-ipc-dir",
    "steering_ipc_dir": "--steering-ipc-dir",
    "workiq_draft_output_dir": "--workiq-draft-output-dir",
    "workiq_tenant_id": "--workiq-tenant-id",
    "additional_prompt": "--additional-prompt",
    "issue_title": "--issue-title",
    "workiq_prompt_qa": "--workiq-prompt-qa",
    "workiq_prompt_km": "--workiq-prompt-km",
    "workiq_prompt_review": "--workiq-prompt-review",
    "mcp_config": "--mcp-config",
    "cli_path": "--cli-path",
    "cli_url": "--cli-url",
    "cloud_session_integration_id": "--cloud-session-integration-id",
    "cloud_session_mc_base_url": "--cloud-session-mc-base-url",
    "cloud_session_step_overrides": "--cloud-session-step-overrides",
    "cloud_session_subtask_overrides": "--cloud-session-subtask-overrides",
    "focus_areas": "--focus-areas",
    "purpose": "--purpose",
    "target_dirs": "--target-dirs",
    "exclude_patterns": "--exclude-patterns",
    "doc_purpose": "--doc-purpose",
    "company_name": "--company-name",
    "target_business": "--target-business",
    "target_region": "--target-region",
    "analysis_purpose": "--analysis-purpose",
    "attached_docs": "--attached-docs",
    "self_improve_goal": "--self-improve-goal",
    "target_scope": "--target-scope",
    "self_improve_target_scope": "--self-improve-target-scope",
    "ignore_paths": "--ignore-paths",
    "target_files": "--target-files",
    "custom_source_dir": "--custom-source-dir",
    "input_alias": "--input-alias",
}
_KEY_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


@dataclass(frozen=True, slots=True)
class WorkflowDescriptor:
    instance_id: str
    workflow_id: str
    ordinal: int
    mode: str = "standard"
    argv: tuple[str, ...] = ()
    missing_replay_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResumeCandidate:
    execution_id: str
    repo_key: str
    instance_id: str
    workflow_id: str
    status: str
    mode: str
    state_version: int
    heartbeat_at: float | None
    heartbeat_age_seconds: float | None
    updated_at: str
    surface: str


@dataclass(frozen=True, slots=True)
class ResumePlan:
    execution_id: str
    instance_id: str
    workflow_id: str
    action: str | None
    expected_state_version: int
    risk_reasons: tuple[str, ...]
    missing_replay_keys: tuple[str, ...]
    argv: tuple[str, ...]
    resume_plan_hash: str


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return deterministic compact UTF-8 JSON for hashes and storage."""

    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _descriptor_payload(descriptor: WorkflowDescriptor) -> dict[str, Any]:
    return {
        "instance_id": descriptor.instance_id,
        "workflow_id": descriptor.workflow_id,
        "ordinal": descriptor.ordinal,
        "mode": descriptor.mode,
        "argv": list(descriptor.argv),
        "missing_replay_keys": list(descriptor.missing_replay_keys),
    }


def compute_launch_plan_hash(descriptors: Sequence[WorkflowDescriptor]) -> str:
    """Hash an ordered sanitized plan without an execution identity."""

    payload = [_descriptor_payload(descriptor) for descriptor in descriptors]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_resume_plan_hash(payload: Mapping[str, Any]) -> str:
    """Hash the transient state/action/input snapshot used for approval."""

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record[name]
    try:
        return record[name]
    except (IndexError, KeyError, TypeError):
        return getattr(record, name)


def _option_key(flag: str) -> str:
    name = flag.lstrip("-")
    if name.startswith("no-"):
        name = name[3:]
    return name.replace("-", "_")


def _split_option_token(raw: str) -> tuple[str, str | None]:
    head, separator, inline_value = raw.partition("=")
    return _SHORT_FLAGS.get(head, head), inline_value if separator else None


_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _validate_persisted_replay_value(flag: str, value: str) -> None:
    """Reject values that cannot be safely persisted as control metadata."""
    reject_sensitive_persisted_text(value, f"replay option {flag}")
    if any(character in value for character in ("\r", "\n")):
        raise DurableStateError(f"replay option contains control text: {flag}")
    if flag == "--repo" and not is_github_repository_slug(value):
        raise DurableStateError("replay repository must use owner/repo form")
    if _URI_SCHEME_RE.match(value):
        raise DurableStateError(f"replay option cannot persist a URL: {flag}")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise DurableStateError(f"replay option cannot persist an absolute path: {flag}")


def _validate_descriptor(descriptor: WorkflowDescriptor) -> None:
    for name, value in (
        ("instance_id", descriptor.instance_id),
        ("workflow_id", descriptor.workflow_id),
        ("mode", descriptor.mode),
    ):
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise DurableStateError(f"workflow descriptor {name} is invalid")
    if (
        isinstance(descriptor.ordinal, bool)
        or not isinstance(descriptor.ordinal, int)
        or descriptor.ordinal < 0
    ):
        raise DurableStateError("workflow descriptor ordinal is invalid")
    if any(not isinstance(value, str) or "\x00" in value for value in descriptor.argv):
        raise DurableStateError("workflow descriptor argv is invalid")
    if any(_KEY_RE.fullmatch(value) is None for value in descriptor.missing_replay_keys):
        raise DurableStateError("workflow descriptor replay key is invalid")
    if set(descriptor.missing_replay_keys).difference(_REPLAY_FLAG_BY_KEY):
        raise DurableStateError("workflow descriptor replay key is unsupported")


def _parse_selected_steps(argv: Sequence[str]) -> list[str]:
    values = list(argv)
    if "--steps" not in values:
        return []
    index = values.index("--steps") + 1
    if index >= len(values) or values[index].startswith("-"):
        raise DurableStateError("stored --steps option is malformed")
    return [item for item in re.split(r"[\s,]+", values[index]) if item]


def _workflow_from_argv(argv: Sequence[str]) -> str:
    positions = [index for index, value in enumerate(argv) if value == "--workflow"]
    if len(positions) != 1:
        raise DurableStateError("replay argv must contain exactly one workflow")
    index = positions[0] + 1
    if index >= len(argv) or not argv[index] or argv[index].startswith("-"):
        raise DurableStateError("stored workflow option is malformed")
    return argv[index]


def _decode_replay_groups(key: str, value: str) -> tuple[tuple[str, ...], ...]:
    if key == "input_alias":
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise DurableStateError("input_alias replay value is malformed") from exc
            if not isinstance(parsed, list):
                raise DurableStateError("input_alias replay value is malformed")
            if len(parsed) == 2 and all(isinstance(item, str) for item in parsed):
                groups = (tuple(parsed),)
            elif parsed and all(
                isinstance(pair, list)
                and len(pair) == 2
                and all(isinstance(item, str) for item in pair)
                for pair in parsed
            ):
                groups = tuple(tuple(pair) for pair in parsed)
            else:
                raise DurableStateError("input_alias replay value is malformed")
        else:
            groups = (tuple(value.split("=", 1)),)
        if any(len(group) != 2 for group in groups):
            raise DurableStateError("input_alias replay value requires alias and path")
    elif _REPLAY_FLAG_BY_KEY[key] in _MISSING_MULTI_VALUE_FLAGS:
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise DurableStateError("multi-value replay input is malformed") from exc
            if not isinstance(parsed, list):
                raise DurableStateError("multi-value replay input is malformed")
            values = tuple(parsed)
        else:
            values = (value,)
        groups = (values,)
    else:
        groups = ((value,),)
    if any(
        not isinstance(item, str)
        or not item
        or "\x00" in item
        or "\r" in item
        or "\n" in item
        for group in groups
        for item in group
    ):
        raise DurableStateError(f"resume replay value is invalid: {key}")
    if (
        key == "input_alias"
        or _REPLAY_FLAG_BY_KEY[key] in _MISSING_MULTI_VALUE_FLAGS
    ) and any(item.startswith("-") for group in groups for item in group):
        raise DurableStateError(
            f"resume replay value cannot be interpreted as an option: {key}"
        )
    return groups


def _append_replay_value(argv: list[str], key: str, value: str) -> None:
    flag = _REPLAY_FLAG_BY_KEY[key]
    for values in _decode_replay_groups(key, value):
        if flag in _MISSING_VALUE_FLAGS:
            argv.append(f"{flag}={values[0]}")
        else:
            argv.append(flag)
            argv.extend(values)


def _replace_selected_steps(argv: Sequence[str], step_ids: Sequence[str]) -> tuple[str, ...]:
    values = list(argv)
    if "--steps" in values:
        index = values.index("--steps")
        if index + 1 >= len(values) or values[index + 1].startswith("-"):
            raise DurableStateError("stored --steps option is malformed")
        del values[index : index + 2]
    if step_ids:
        values.extend(("--steps", ",".join(step_ids)))
    return tuple(values)


def reconcile_succeeded_steps(
    repo_root: "str | Path",
    workflow: Any,
    active_step_ids: Sequence[str] | set[str],
    succeeded_step_ids: Sequence[str] | set[str],
) -> tuple[set[str], bool]:
    """Reactivate succeeded steps whose outputs, or upstream outputs, are missing."""
    active = set(active_step_ids)
    succeeded = set(succeeded_step_ids)
    invalidated: set[str] = set()
    for step in getattr(workflow, "steps", ()) or ():
        if step.id not in active or step.id not in succeeded:
            continue
        missing = find_missing_output_paths(
            repo_root,
            list(getattr(step, "output_paths", ()) or ()),
            resolve_output_path_prefix_gates(step),
        )
        if missing:
            invalidated.add(step.id)

    changed = True
    while changed:
        changed = False
        for step in getattr(workflow, "steps", ()) or ():
            if step.id not in active or step.id in invalidated:
                continue
            dependencies = set(getattr(step, "depends_on", ()) or ())
            dependencies.update(getattr(step, "skip_fallback_deps", ()) or ())
            dependencies.update(getattr(step, "block_unless", ()) or ())
            if dependencies.intersection(invalidated):
                invalidated.add(step.id)
                changed = True

    execute = {
        step.id
        for step in getattr(workflow, "steps", ()) or ()
        if step.id in active
        and not getattr(step, "is_container", False)
        and (step.id not in succeeded or step.id in invalidated)
    }
    return execute, bool(invalidated)


def _append_resolved_replay_value(
    argv: list[str], flag: str, value: Any
) -> None:
    """Append one non-empty resolved scalar or sequence."""
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        values = [str(item) for item in value if str(item)]
    else:
        text = str(value)
        values = [text] if text else []
    if values:
        argv.append(flag)
        argv.extend(values)


def _append_resolved_replay_switch(
    argv: list[str],
    enabled: Any,
    enable_flag: str,
    disable_flag: str | None = None,
) -> None:
    """Append one resolved boolean switch."""
    if enabled is True:
        argv.append(enable_flag)
    elif enabled is False and disable_flag:
        argv.append(disable_flag)


def build_resolved_replay_argv(
    workflow_id: str,
    config: Any,
    params: Mapping[str, Any],
    *,
    args: Any = None,
    continue_on_error: bool | None = None,
) -> tuple[str, ...]:
    """Build the canonical replay shape from resolved config and parameters."""
    argv: list[str] = ["orchestrate", "--workflow", workflow_id]

    for flag, value in (
        ("--model", getattr(config, "model", None)),
        ("--review-model", getattr(config, "review_model", None)),
        ("--qa-model", getattr(config, "qa_model", None)),
        ("--akm-model", getattr(config, "akm_model", None)),
        ("--reasoning-effort", getattr(config, "reasoning_effort", None)),
        ("--review-reasoning-effort", getattr(config, "review_reasoning_effort", None)),
        ("--qa-reasoning-effort", getattr(config, "qa_reasoning_effort", None)),
        ("--akm-reasoning-effort", getattr(config, "akm_reasoning_effort", None)),
        ("--context-tier", getattr(config, "context_tier", None)),
        ("--akm-context-tier", getattr(config, "akm_context_tier", None)),
        ("--enable-agentic-retrieval", getattr(config, "enable_agentic_retrieval", None)),
        ("--foundry-sku-fallback-policy", getattr(config, "foundry_sku_fallback_policy", None)),
        ("--enable-tool-search", getattr(config, "enable_tool_search", None)),
        ("--max-parallel", getattr(config, "max_parallel", None)),
        ("--tool-search-ranking", getattr(config, "tool_search_ranking", None)),
        ("--workiq-dxx", ",".join(getattr(config, "workiq_akm_ingest_dxx", ()) or ())),
        ("--workiq-per-question-timeout", getattr(config, "workiq_per_question_timeout", None)),
        ("--workiq-request-timeout", getattr(config, "workiq_request_timeout", None)),
        ("--issue-number", getattr(config, "issue_number", None)),
        ("--log-level", getattr(config, "log_level", None)),
        ("--timestamp-style", getattr(config, "timestamp_style", None)),
        ("--timeout", getattr(config, "timeout_seconds", None)),
        ("--review-timeout", getattr(config, "review_timeout_seconds", None)),
        ("--branch", getattr(config, "base_branch", None)),
        ("--repo", getattr(config, "repo", None)),
        ("--context-max-chars", getattr(config, "context_injection_max_chars", None)),
        ("--self-improve-max-iterations", getattr(config, "self_improve_max_iterations", None)),
        ("--self-improve-target-scope", getattr(config, "self_improve_target_scope", None)),
        ("--mdq-watch-debounce-ms", getattr(config, "mdq_watch_debounce_ms", None)),
        ("--cq-watch-debounce-ms", getattr(config, "cq_watch_debounce_ms", None)),
        ("--agentic-data-sources-hint", getattr(config, "agentic_data_sources_hint", None)),
        ("--qa-ipc-dir", getattr(config, "qa_ipc_dir", None)),
        ("--steering-ipc-dir", getattr(config, "steering_ipc_dir", None)),
        ("--workiq-draft-output-dir", getattr(config, "workiq_draft_output_dir", None)),
        ("--workiq-tenant-id", getattr(config, "workiq_tenant_id", None)),
        ("--workiq-prompt-qa", getattr(config, "workiq_prompt_qa", None)),
        ("--workiq-prompt-km", getattr(config, "workiq_prompt_km", None)),
        ("--workiq-prompt-review", getattr(config, "workiq_prompt_review", None)),
        ("--cli-path", getattr(config, "cli_path", None)),
        ("--cli-url", getattr(config, "cli_url", None)),
        ("--additional-prompt", getattr(config, "additional_prompt", None)),
        ("--self-improve-goal", getattr(config, "self_improve_goal", None)),
    ):
        _append_resolved_replay_value(argv, flag, value)

    mcp_config = getattr(args, "mcp_config", None) if args is not None else None
    if mcp_config:
        _append_resolved_replay_value(argv, "--mcp-config", mcp_config)
    elif getattr(config, "mcp_servers", None):
        # The configured payload may contain endpoints or credentials.  A fixed
        # ephemeral sentinel causes sanitize_argv() to retain only the gap key.
        _append_resolved_replay_value(
            argv, "--mcp-config", "replay-value-required"
        )

    _append_resolved_replay_value(
        argv,
        "--agentic-data-source-modes",
        getattr(config, "agentic_data_source_modes", None),
    )
    qa_answer_mode = getattr(config, "qa_answer_mode", None)
    if qa_answer_mode == "all":
        qa_answer_mode = "autopilot"
    _append_resolved_replay_value(argv, "--qa-answer-mode", qa_answer_mode)
    verbosity = getattr(config, "verbosity", None)
    if verbosity in range(4):
        _append_resolved_replay_value(
            argv,
            "--verbosity",
            ("quiet", "compact", "normal", "verbose")[verbosity],
        )

    strict = getattr(args, "strict", None) if args is not None else None
    if continue_on_error is not None:
        strict = not continue_on_error
    for enabled, enable_flag, disable_flag in (
        (strict, "--strict", None),
        (getattr(config, "auto_qa", None), "--auto-qa", None),
        (getattr(config, "qa_akm_background_merge", None), "--qa-akm-background-merge", None),
        (getattr(config, "force_interactive", None), "--force-interactive", None),
        (getattr(config, "auto_contents_review", None), "--auto-contents-review", None),
        (getattr(config, "auto_coding_agent_review", None), "--auto-coding-agent-review", None),
        (getattr(config, "auto_coding_agent_review_auto_approval", None), "--auto-coding-agent-review-auto-approval", None),
        (getattr(config, "auto_compaction", None), "--auto-compaction", "--no-auto-compaction"),
        (getattr(config, "tool_search", None), "--tool-search", "--no-tool-search"),
        (getattr(config, "foundry_mcp_integration", None), "--foundry-mcp-integration", "--no-foundry-mcp-integration"),
        (getattr(config, "agentic_existing_design_diff_only", None), "--agentic-existing-design-diff-only", "--no-agentic-existing-design-diff-only"),
        (getattr(config, "create_issues", None), "--create-issues", None),
        (getattr(config, "create_pr", None), "--create-pr", None),
        (getattr(config, "create_working_branch", None), "--create-working-branch", "--no-create-working-branch"),
        (getattr(config, "no_color", None), "--no-color", None),
        (getattr(config, "screen_reader", None), "--screen-reader", None),
        (getattr(config, "show_stream", None), "--show-stream", None),
        (getattr(config, "show_banner", None), "--banner", "--no-banner"),
        (getattr(config, "final_only", None), "--final-only", None),
        (getattr(config, "fleet_mode_enabled", None), "--fleet-mode", "--no-fleet-mode"),
        (getattr(config, "cloud_session_enabled", None), "--cloud-session", "--no-cloud-session"),
        (getattr(config, "enable_auto_merge", None), "--enable-auto-merge", None),
        (getattr(config, "delete_local_merged_branch", None), "--delete-local-merged-branch", "--no-delete-local-merged-branch"),
        (getattr(config, "workiq_akm_review_enabled", None), "--workiq-akm-review", "--no-workiq-akm-review"),
        (getattr(config, "workiq_akm_ingest_enabled", None), "--workiq-akm-ingest", "--no-workiq-akm-ingest"),
        (getattr(config, "workiq_draft_mode", None), "--workiq-draft", None),
        (getattr(config, "mdq_watch", None), "--mdq-watch", "--no-mdq-watch"),
        (getattr(config, "cq_watch", None), "--cq-watch", "--no-cq-watch"),
        (getattr(config, "workbench_flush_on_exit", None), "--workbench-flush-on-exit", "--no-workbench-flush-on-exit"),
    ):
        _append_resolved_replay_switch(
            argv, enabled, enable_flag, disable_flag
        )

    if getattr(config, "workiq_qa_enabled", False):
        argv.append("--workiq")
    if getattr(config, "unattended", False):
        argv.append("--unattended")
    if getattr(config, "self_improve_skip", False):
        argv.append("--no-self-improve")
    elif getattr(config, "auto_self_improve", False):
        argv.append("--self-improve")
    if getattr(config, "no_workbench", False):
        _append_resolved_replay_value(argv, "--workbench", "off")
    _append_resolved_replay_value(
        argv, "--ignore-paths", getattr(config, "ignore_paths", None)
    )

    steps = params.get("steps") or params.get("selected_steps")
    if isinstance(steps, (list, tuple)):
        steps = ",".join(str(step) for step in steps if str(step))
    _append_resolved_replay_value(argv, "--steps", steps)
    app_ids = params.get("app_ids")
    if isinstance(app_ids, (list, tuple)):
        app_ids = ",".join(str(app_id) for app_id in app_ids if str(app_id))
    if not app_ids:
        app_ids = params.get("app_id")
    _append_resolved_replay_value(argv, "--app-ids", app_ids)

    for key, flag in (
        ("resource_group", "--resource-group"),
        ("sources", "--sources"),
        ("data_location", "--data-location"),
        ("data_resource_suffix", "--data-resource-suffix"),
        ("data_vnet_cidr", "--data-vnet-cidr"),
        ("data_private_endpoint_subnet_cidr", "--data-private-endpoint-subnet-cidr"),
        ("data_aci_subnet_cidr", "--data-aci-subnet-cidr"),
        ("usecase_id", "--usecase-id"),
        ("target_scope", "--target-scope"),
        ("depth", "--depth"),
        ("max_file_lines", "--max-file-lines"),
        ("survey_base_date", "--survey-base-date"),
        ("survey_period_years", "--survey-period-years"),
        ("target_recommendation_id", "--target-recommendation-id"),
        ("tdd_max_retries", "--tdd-max-retries"),
        ("focus_areas", "--focus-areas"),
        ("purpose", "--purpose"),
        ("target_dirs", "--target-dirs"),
        ("exclude_patterns", "--exclude-patterns"),
        ("doc_purpose", "--doc-purpose"),
        ("company_name", "--company-name"),
        ("target_business", "--target-business"),
        ("target_region", "--target-region"),
        ("analysis_purpose", "--analysis-purpose"),
        ("attached_docs", "--attached-docs"),
        ("issue_title", "--issue-title"),
        ("target_files", "--target-files"),
        ("custom_source_dir", "--custom-source-dir"),
    ):
        value = params.get(key)
        if key == "attached_docs" and isinstance(value, (list, tuple)):
            value = ",".join(str(item) for item in value if str(item))
        _append_resolved_replay_value(argv, flag, value)

    for key, enable_flag, disable_flag in (
        ("force_refresh", "--force-refresh", "--no-force-refresh"),
        ("approval_gates", "--approval-gates", None),
        ("include_kpi_okr", "--include-kpi-okr", None),
        ("create_remote_mcp_server", "--create-remote-mcp-server", "--no-create-remote-mcp-server"),
    ):
        if key in params:
            _append_resolved_replay_switch(
                argv, params[key], enable_flag, disable_flag
            )
    for alias in params.get("input_aliases") or ():
        if isinstance(alias, (list, tuple)) and len(alias) == 2:
            argv.extend(("--input-alias", str(alias[0]), str(alias[1])))
    return tuple(argv)


def standard_execution_is_registerable(
    config: Any,
    params: Mapping[str, Any],
    *,
    existing_execution_id: Any = None,
) -> bool:
    """Return whether a resolved standard local run may be registered."""
    try:
        from .runtime_observability import is_child_process
    except ImportError:  # pragma: no cover - flat-load compatibility
        from runtime_observability import is_child_process  # type: ignore[no-redef]
    return not any(
        (
            is_child_process(),
            bool(getattr(config, "dry_run", False)),
            bool(getattr(config, "fleet_mode_enabled", False)),
            bool(getattr(config, "cloud_session_enabled", False)),
            bool(
                getattr(config, "create_issues", False)
                and getattr(config, "assign_copilot_agent", False)
            ),
            bool(params.get("resume_run")),
            bool(existing_execution_id),
        )
    )


class ResumeService:
    """Register executions and build repository-scoped resume plans."""

    def __init__(self, store: RunStateStore, repo_root: str | Path) -> None:
        self.store = store
        self.repo_root = canonical_repo_root(repo_root)
        self.repo_key = compute_repo_key(self.repo_root)

    @staticmethod
    def new_execution_id() -> str:
        return f"exec-{uuid.uuid4().hex}"

    def sanitize_argv(
        self, argv: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Keep fixed replay metadata and return key names for omitted values."""

        if isinstance(argv, (str, bytes, bytearray)) or not isinstance(argv, Sequence):
            raise DurableStateError("replay argv must be an ordered string sequence")
        values = tuple(argv)
        if not values or values[0] != "orchestrate":
            raise DurableStateError("replay argv must start with orchestrate")
        if any(not isinstance(value, str) or "\x00" in value for value in values):
            raise DurableStateError("replay argv contains an invalid value")

        safe: list[str] = ["orchestrate"]
        missing: list[str] = []
        index = 1
        while index < len(values):
            raw_flag = values[index]
            flag, inline_value = _split_option_token(raw_flag)
            if not flag.startswith("--"):
                raise DurableStateError("unexpected replay positional value")
            if flag in _REJECTED_FLAGS:
                raise DurableStateError(f"replay option is outside durable scope: {flag}")

            if flag in _REPLAY_BOOLEAN_FLAGS:
                if inline_value is not None:
                    raise DurableStateError(
                        f"boolean replay option does not accept a value: {flag}"
                    )
                safe.append(flag)
                index += 1
                continue

            if flag in _REPLAY_VALUE_FLAGS:
                if inline_value is None:
                    if index + 1 >= len(values) or values[index + 1].startswith("-"):
                        raise DurableStateError(f"replay option requires a value: {flag}")
                    value = values[index + 1]
                    index += 2
                else:
                    value = inline_value
                    index += 1
                if not value:
                    raise DurableStateError(f"replay option requires a value: {flag}")
                _validate_persisted_replay_value(flag, value)
                safe.extend((flag, value))
                continue

            if flag in _REPLAY_MULTI_VALUE_FLAGS:
                collected = [] if inline_value is None else [inline_value]
                end = index + 1
                while end < len(values) and not values[end].startswith("-"):
                    collected.append(values[end])
                    end += 1
                if not collected or any(not value for value in collected):
                    raise DurableStateError(f"replay option requires values: {flag}")
                for value in collected:
                    _validate_persisted_replay_value(flag, value)
                safe.append(flag)
                safe.extend(collected)
                index = end
                continue

            if flag in _MISSING_VALUE_FLAGS:
                if inline_value is None:
                    if index + 1 >= len(values) or values[index + 1].startswith("-"):
                        raise DurableStateError(f"replay option requires a value: {flag}")
                    index += 2
                else:
                    if not inline_value:
                        raise DurableStateError(f"replay option requires a value: {flag}")
                    index += 1
            elif flag in _MISSING_MULTI_VALUE_FLAGS:
                value_count = 1 if inline_value else 0
                index += 1
                while index < len(values) and not values[index].startswith("-"):
                    value_count += 1
                    index += 1
                if value_count == 0:
                    raise DurableStateError(f"replay option requires values: {flag}")
            elif flag in _MISSING_PAIR_FLAGS:
                value_count = 1 if inline_value else 0
                index += 1
                while (
                    value_count < 2
                    and index < len(values)
                    and not values[index].startswith("-")
                ):
                    value_count += 1
                    index += 1
                if value_count != 2:
                    raise DurableStateError(f"replay option requires two values: {flag}")
            else:
                raise DurableStateError(f"unsupported replay option: {flag}")

            key = _option_key(flag)
            if key not in missing:
                missing.append(key)

        return tuple(safe), tuple(missing)

    def register_execution(
        self,
        surface: str,
        descriptors: Sequence[WorkflowDescriptor],
        *,
        execution_id: str | None = None,
        checkpoint_head: str | None = None,
    ) -> str:
        """Sanitize and atomically register one ordered execution plan."""

        if isinstance(descriptors, (str, bytes, bytearray)) or not isinstance(
            descriptors, Sequence
        ):
            raise DurableStateError("workflow descriptors must be an ordered sequence")
        if not isinstance(surface, str) or not surface.strip():
            raise DurableStateError("execution surface is required")

        sanitized: list[WorkflowDescriptor] = []
        for descriptor in descriptors:
            if not isinstance(descriptor, WorkflowDescriptor):
                raise DurableStateError("invalid workflow descriptor")
            _validate_descriptor(descriptor)
            safe_argv, omitted = self.sanitize_argv(descriptor.argv)
            if _workflow_from_argv(safe_argv) != descriptor.workflow_id:
                raise DurableStateError(
                    "workflow descriptor does not match replay argv"
                )
            missing = tuple(
                dict.fromkeys((*descriptor.missing_replay_keys, *omitted))
            )
            sanitized.append(
                replace(
                    descriptor,
                    argv=safe_argv,
                    missing_replay_keys=missing,
                )
            )

        if not sanitized:
            raise DurableStateError("at least one workflow descriptor is required")
        ordinals = [item.ordinal for item in sanitized]
        if ordinals != list(range(len(sanitized))):
            raise DurableStateError("workflow ordinals must be contiguous from zero")
        instance_ids = [item.instance_id for item in sanitized]
        if len(set(instance_ids)) != len(instance_ids):
            raise DurableStateError("workflow instance IDs must be unique")

        resolved_execution_id = execution_id or self.new_execution_id()
        plan_payload = {
            "instances": [_descriptor_payload(item) for item in sanitized],
            "checkpoint_head": checkpoint_head,
        }
        plan_json = canonical_json(plan_payload)
        self.store.register_execution(
            resolved_execution_id,
            self.repo_key,
            surface,
            compute_launch_plan_hash(tuple(sanitized)),
            plan_json,
            tuple(sanitized),
        )
        return resolved_execution_id

    def list_candidates(self) -> tuple[ResumeCandidate, ...]:
        """Return current-repository candidates in store-defined newest order."""

        now = time.time()
        candidates: list[ResumeCandidate] = []
        for execution in self.store.list_candidates(self.repo_key):
            execution_id = str(_field(execution, "execution_id"))
            instances = self.store.list_instances(execution_id)
            instance = next(
                (
                    item
                    for item in instances
                    if str(_field(item, "status")) != "succeeded"
                ),
                None,
            )
            if instance is None:
                continue
            heartbeat = _field(instance, "heartbeat_at")
            heartbeat_value = float(heartbeat) if heartbeat is not None else None
            candidates.append(
                ResumeCandidate(
                    execution_id=execution_id,
                    repo_key=self.repo_key,
                    instance_id=str(_field(instance, "instance_id")),
                    workflow_id=str(_field(instance, "workflow_id")),
                    status=str(_field(instance, "status")),
                    mode=str(_field(instance, "mode")),
                    state_version=int(_field(instance, "state_version")),
                    heartbeat_at=heartbeat_value,
                    heartbeat_age_seconds=(
                        None
                        if heartbeat_value is None
                        else max(0.0, now - heartbeat_value)
                    ),
                    updated_at=str(_field(execution, "updated_at")),
                    surface=str(_field(execution, "surface")),
                )
            )
        return tuple(candidates)

    def build_plan(
        self,
        execution_id: str,
        *,
        action: str | None = None,
        replay_values: Mapping[str, str] | None = None,
        current_head: str | None = None,
    ) -> ResumePlan:
        """Build one transient plan for the earliest non-succeeded instance."""

        if action is not None and action not in _ALLOWED_ACTIONS:
            raise DurableStateError("unsupported recovery action")
        if current_head is not None and (
            not isinstance(current_head, str)
            or not current_head
            or "\x00" in current_head
        ):
            raise DurableStateError("current repository HEAD is invalid")
        if replay_values is not None and not isinstance(replay_values, Mapping):
            raise DurableStateError("resume replay values must be a mapping")
        execution = self.store.get_execution(execution_id)
        if execution is None:
            raise DurableStateError("durable execution was not found")
        if str(_field(execution, "repo_key")) != self.repo_key:
            raise DurableStateError("durable execution belongs to another repository")

        instances = self.store.list_instances(execution_id)
        if not instances:
            raise DurableStateError("durable execution has no workflow instances")
        ordinals = [int(_field(item, "ordinal")) for item in instances]
        if ordinals != list(range(len(instances))):
            raise DurableStateError("durable workflow instance order is invalid")
        instance = next(
            (
                item
                for item in instances
                if str(_field(item, "status")) != "succeeded"
            ),
            None,
        )
        if instance is None:
            raise DurableStateError("durable execution has no incomplete workflow")
        instance_id = str(_field(instance, "instance_id"))
        workflow_id = str(_field(instance, "workflow_id"))
        mode = str(_field(instance, "mode"))
        state_version = int(_field(instance, "state_version"))

        descriptor = self._load_descriptor(execution, instance_id)
        if (
            descriptor.workflow_id != workflow_id
            or descriptor.ordinal != int(_field(instance, "ordinal"))
            or descriptor.mode != mode
            or _workflow_from_argv(descriptor.argv) != workflow_id
        ):
            raise DurableStateError("stored workflow descriptor does not match state")
        replay = dict(replay_values or {})
        if any(
            not isinstance(key, str) or _KEY_RE.fullmatch(key) is None
            for key in replay
        ):
            raise DurableStateError("resume replay contains an invalid key")
        unknown_replay = set(replay).difference(descriptor.missing_replay_keys)
        if unknown_replay:
            raise DurableStateError(
                "resume replay contains unknown keys: " + ", ".join(sorted(unknown_replay))
            )
        for key, value in replay.items():
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise DurableStateError(f"resume replay value is invalid: {key}")
            _decode_replay_groups(key, value)

        missing_replay = tuple(
            key for key in descriptor.missing_replay_keys if key not in replay
        )
        safe_argv, output_missing = self._reconcile_outputs(
            execution_id,
            instance_id,
            workflow_id,
            descriptor.argv,
        )
        argv = list(safe_argv)
        if argv:
            for key in descriptor.missing_replay_keys:
                if key in replay:
                    _append_replay_value(argv, key, replay[key])

        risk: set[str] = set()
        if mode not in _ALLOWED_MODES:
            risk.add("unsupported_mode")
        status = str(_field(instance, "status"))
        if status == "failed":
            risk.add("failed")
        elif status in {"running", "suspended", "blocked"}:
            risk.add("non_terminal")
        checkpoint_head = _field(instance, "checkpoint_head")
        if (
            checkpoint_head is not None
            and current_head is not None
            and str(checkpoint_head) != current_head
        ):
            risk.add("head_drift")
        if missing_replay:
            risk.add("missing_replay_value")

        lease_owner = _field(instance, "lease_owner")
        lease_expires_at = _field(instance, "lease_expires_at")
        if lease_owner is not None:
            if (
                lease_expires_at is not None
                and float(lease_expires_at) > time.time()
            ):
                risk.add("active_owner")
            else:
                risk.add("non_terminal")

        if output_missing:
            risk.add("missing_output")

        if action == "reuse-session":
            steps = self.store.list_steps(execution_id, instance_id)
            selected = _parse_selected_steps(safe_argv) if safe_argv else []
            target_step_id = selected[0] if selected else None
            latest = next(
                (
                    row
                    for row in reversed(steps)
                    if str(_field(row, "record_kind")) == "step"
                    and str(_field(row, "step_id")) == target_step_id
                ),
                None,
            )
            if (
                latest is None
                or str(_field(latest, "phase") or "") != "main"
                or not _field(latest, "session_id")
            ):
                risk.add("sdk_missing")

        ordered_risks = tuple(item for item in _RISK_ORDER if item in risk)
        replay_hashes = {
            key: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for key, value in sorted(replay.items())
        }
        instance_snapshots = [
            {
                "instance_id": str(_field(item, "instance_id")),
                "ordinal": int(_field(item, "ordinal")),
                "status": str(_field(item, "status")),
                "state_version": int(_field(item, "state_version")),
            }
            for item in instances
        ]
        hash_payload = {
            "execution_id": execution_id,
            "instance_id": instance_id,
            "workflow_id": workflow_id,
            "instances": instance_snapshots,
            "action": action,
            "current_head": current_head,
            "risk_reasons": ordered_risks,
            "missing_replay_keys": missing_replay,
            "replay_value_hashes": replay_hashes,
            "safe_argv": safe_argv,
        }
        return ResumePlan(
            execution_id=execution_id,
            instance_id=instance_id,
            workflow_id=workflow_id,
            action=action,
            expected_state_version=state_version,
            risk_reasons=ordered_risks,
            missing_replay_keys=missing_replay,
            argv=tuple(argv),
            resume_plan_hash=compute_resume_plan_hash(hash_payload),
        )

    def acquire(self, plan: ResumePlan, owner: str) -> LeaseToken:
        """Acquire the plan snapshot with expected-state-version CAS."""

        if not isinstance(plan, ResumePlan):
            raise DurableStateError("invalid resume plan")
        if plan.missing_replay_keys:
            raise DurableStateError("resume replay values are incomplete")
        if plan.risk_reasons and plan.action is None:
            raise DurableStateError("risky resume requires an explicit recovery action")
        if plan.action is not None and plan.action not in _ALLOWED_ACTIONS:
            raise DurableStateError("unsupported recovery action")
        if tuple(reason for reason in _RISK_ORDER if reason in plan.risk_reasons) != (
            plan.risk_reasons
        ) or any(reason not in _RISK_ORDER for reason in plan.risk_reasons):
            raise DurableStateError("resume plan contains invalid risk reasons")
        if "unsupported_mode" in plan.risk_reasons:
            raise DurableStateError("durable resume mode is unsupported")
        if plan.action == "reuse-session" and any(
            reason in plan.risk_reasons for reason in ("sdk_missing", "sdk_in_use")
        ):
            raise DurableStateError("stored SDK session cannot be reused")
        if re.fullmatch(r"[0-9a-f]{64}", plan.resume_plan_hash) is None:
            raise DurableStateError("resume plan hash is invalid")

        execution = self.store.get_execution(plan.execution_id)
        if execution is None or str(_field(execution, "repo_key")) != self.repo_key:
            raise DurableStateError("resume plan belongs to another repository")
        instances = self.store.list_instances(plan.execution_id)
        instance = next(
            (
                item
                for item in instances
                if str(_field(item, "status")) != "succeeded"
            ),
            None,
        )
        if (
            instance is None
            or str(_field(instance, "instance_id")) != plan.instance_id
            or str(_field(instance, "workflow_id")) != plan.workflow_id
            or int(_field(instance, "state_version"))
            != plan.expected_state_version
        ):
            raise DurableStateError("resume plan state is stale")
        if str(_field(instance, "mode")) not in _ALLOWED_MODES:
            raise DurableStateError("durable resume mode is unsupported")
        if plan.argv and _workflow_from_argv(plan.argv) != plan.workflow_id:
            raise DurableStateError("resume plan workflow is invalid")
        return self.store.acquire_lease(
            plan.execution_id,
            plan.instance_id,
            plan.expected_state_version,
            owner,
            allow_takeover=plan.action is not None,
        )

    def complete_reconciled(
        self,
        plan: ResumePlan,
        token: LeaseToken,
    ) -> LeaseToken:
        """Fence an output-complete instance to ``succeeded`` without a child.

        ``build_plan()`` returns an empty argv only when every selected Step is
        already successful and its required outputs still exist.  Recheck that
        condition after lease acquisition so a subcommand-less child is never
        used as a workflow-finalization mechanism.
        """
        if not isinstance(plan, ResumePlan) or not isinstance(token, LeaseToken):
            raise DurableStateError("invalid reconciled completion context")
        if plan.argv:
            raise DurableStateError(
                "reconciled completion requires an empty child argv"
            )
        if plan.missing_replay_keys:
            raise DurableStateError("resume replay values are incomplete")
        if (
            token.execution_id != plan.execution_id
            or token.instance_id != plan.instance_id
            or token.state_version != plan.expected_state_version
        ):
            raise DurableStateError("reconciled completion token is stale")

        execution = self.store.get_execution(plan.execution_id)
        instance = self.store.get_instance(plan.execution_id, plan.instance_id)
        if execution is None or str(_field(execution, "repo_key")) != self.repo_key:
            raise DurableStateError("resume plan belongs to another repository")
        if (
            instance is None
            or str(_field(instance, "workflow_id")) != plan.workflow_id
            or str(_field(instance, "status")) == "succeeded"
            or int(_field(instance, "state_version")) != token.state_version
            or str(_field(instance, "lease_owner") or "") != token.owner
            or int(_field(instance, "lease_generation")) != token.generation
        ):
            raise DurableStateError("reconciled completion state is stale")

        descriptor = self._load_descriptor(execution, plan.instance_id)
        current_argv, output_missing = self._reconcile_outputs(
            plan.execution_id,
            plan.instance_id,
            plan.workflow_id,
            descriptor.argv,
        )
        if current_argv or output_missing:
            raise DurableStateError(
                "reconciled outputs changed before workflow completion"
            )
        return self.store.transition_workflow(token, "succeeded")

    @staticmethod
    def _load_descriptor(execution: Any, instance_id: str) -> WorkflowDescriptor:
        try:
            payload = json.loads(str(_field(execution, "plan_json")))
            raw_instances = payload["instances"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DurableStateError("stored durable plan is invalid") from exc
        if not isinstance(raw_instances, list):
            raise DurableStateError("stored durable plan instances are invalid")
        descriptors: list[WorkflowDescriptor] = []
        try:
            for raw in raw_instances:
                if not isinstance(raw, dict):
                    raise TypeError("descriptor must be an object")
                descriptor = WorkflowDescriptor(
                    instance_id=raw["instance_id"],
                    workflow_id=raw["workflow_id"],
                    ordinal=raw["ordinal"],
                    mode=raw["mode"],
                    argv=tuple(raw["argv"]),
                    missing_replay_keys=tuple(raw["missing_replay_keys"]),
                )
                _validate_descriptor(descriptor)
                if _workflow_from_argv(descriptor.argv) != descriptor.workflow_id:
                    raise DurableStateError(
                        "stored workflow descriptor has a mismatched workflow"
                    )
                descriptors.append(descriptor)
        except (KeyError, TypeError) as exc:
            raise DurableStateError("stored workflow descriptor is malformed") from exc
        if [item.ordinal for item in descriptors] != list(range(len(descriptors))):
            raise DurableStateError("stored workflow descriptor order is invalid")
        if len({item.instance_id for item in descriptors}) != len(descriptors):
            raise DurableStateError("stored workflow instance IDs are not unique")
        if compute_launch_plan_hash(descriptors) != str(
            _field(execution, "launch_plan_hash")
        ):
            raise DurableStateError("stored durable launch plan hash is invalid")
        descriptor = next(
            (item for item in descriptors if item.instance_id == instance_id),
            None,
        )
        if descriptor is None:
            raise DurableStateError("stored workflow descriptor was not found")
        return descriptor

    def _reconcile_outputs(
        self,
        execution_id: str,
        instance_id: str,
        workflow_id: str,
        argv: tuple[str, ...],
    ) -> tuple[tuple[str, ...], bool]:
        try:
            from .template_engine import resolve_selected_steps
            from .workflow_registry import get_workflow
        except ImportError:  # pragma: no cover - top-level compatibility
            from template_engine import resolve_selected_steps  # type: ignore[no-redef]
            from workflow_registry import get_workflow  # type: ignore[no-redef]

        workflow = get_workflow(workflow_id)
        if workflow is None:
            raise DurableStateError("stored workflow is no longer available")
        requested = _parse_selected_steps(argv)
        known_step_ids = {step.id for step in workflow.steps}
        if set(requested).difference(known_step_ids):
            raise DurableStateError("stored durable plan contains an unknown step")
        active = resolve_selected_steps(workflow, requested)
        ordered_active = [
            step.id
            for step in workflow.steps
            if step.id in active and not getattr(step, "is_container", False)
        ]

        succeeded = {
            str(_field(row, "step_id"))
            for row in self.store.list_steps(execution_id, instance_id)
            if str(_field(row, "record_kind")) == "step"
            and str(_field(row, "status")) == "succeeded"
        }
        execute_set, output_missing = reconcile_succeeded_steps(
            self.repo_root,
            workflow,
            active,
            succeeded,
        )
        execute = [
            step_id
            for step_id in ordered_active
            if step_id in execute_set
        ]
        if not execute:
            return (), output_missing
        return _replace_selected_steps(argv, execute), output_missing


__all__ = [
    "ResumeCandidate",
    "ResumePlan",
    "ResumeService",
    "WorkflowDescriptor",
    "build_resolved_replay_argv",
    "canonical_json",
    "compute_launch_plan_hash",
    "compute_resume_plan_hash",
    "reconcile_succeeded_steps",
    "standard_execution_is_registerable",
]
