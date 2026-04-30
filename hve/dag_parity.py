"""Cloud/hve workflow parity helpers.

This module intentionally reports observed differences only. It does not try to
merge Cloud and hve DAG definitions or infer missing transitions.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


DEFAULT_WORKFLOW_ALIASES: Mapping[str, Tuple[str, ...]] = {
    # Legacy aliases used only when comparing hve workflow ids with the older
    # bash registry, which once registered bare "aad" and "asdw"
    # (pre-Phase-1 cleanup). These entries let parity checks treat hve
    # canonical ids such as "aad-web" as the same workflow when bash still
    # contains the legacy id, avoiding spurious diffs during registry parity
    # comparison.
    "aad-web": ("aad",),
    "asdw-web": ("asdw",),
}


@dataclass(frozen=True)
class WorkflowParityItem:
    workflow_id: str
    classification: str
    hve_id: Optional[str] = None
    cloud_bash_id: Optional[str] = None
    reusable_workflow_id: Optional[str] = None
    alias_of: Optional[str] = None


@dataclass(frozen=True)
class WorkflowParityReport:
    items: Tuple[WorkflowParityItem, ...]

    @property
    def has_differences(self) -> bool:
        return any(item.classification != "same" for item in self.items)

    def by_classification(self, classification: str) -> Tuple[WorkflowParityItem, ...]:
        return tuple(item for item in self.items if item.classification == classification)


def extract_bash_workflow_ids(registry_path: str | Path) -> Tuple[str, ...]:
    """Extract workflow ids declared in .github/scripts/bash/lib/workflow-registry.sh."""
    text = Path(registry_path).read_text(encoding="utf-8")
    return tuple(sorted(set(re.findall(r"_WORKFLOW_REGISTRY\[([^\]]+)\]", text))))


def extract_reusable_workflow_ids(paths: Iterable[str | Path]) -> Tuple[str, ...]:
    """Extract hve workflow ids passed to `python -m hve --workflow ...` in YAML."""
    workflow_ids: set[str] = set()
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        workflow_ids.update(re.findall(r"--workflow\s+([A-Za-z0-9_-]+)", text))
    return tuple(sorted(workflow_ids))


def compare_workflow_id_sets(
    hve_ids: Sequence[str],
    cloud_bash_ids: Sequence[str],
    reusable_workflow_ids: Sequence[str],
    *,
    aliases: Mapping[str, Tuple[str, ...]] = DEFAULT_WORKFLOW_ALIASES,
) -> WorkflowParityReport:
    """Compare observed workflow IDs without changing either execution path."""
    hve = set(hve_ids)
    bash = set(cloud_bash_ids)
    reusable = set(reusable_workflow_ids)
    all_ids = sorted(hve | bash | reusable)
    items: list[WorkflowParityItem] = []
    consumed_aliases: set[str] = set()
    reverse_aliases = {
        alias: workflow_id
        for workflow_id, alias_values in aliases.items()
        for alias in alias_values
    }

    for workflow_id in all_ids:
        if workflow_id in consumed_aliases:
            continue
        if workflow_id in reverse_aliases and reverse_aliases[workflow_id] in hve and workflow_id in bash:
            continue
        if workflow_id in hve and workflow_id in bash and workflow_id in reusable:
            items.append(WorkflowParityItem(
                workflow_id=workflow_id,
                classification="same",
                hve_id=workflow_id,
                cloud_bash_id=workflow_id,
                reusable_workflow_id=workflow_id,
            ))
            continue

        alias_item = _alias_item(workflow_id, hve, bash, reusable, aliases)
        if alias_item is not None:
            items.append(alias_item)
            consumed_aliases.update(
                filter(None, (alias_item.hve_id, alias_item.cloud_bash_id))
            )
            continue

        sources = (
            workflow_id in hve,
            workflow_id in bash,
            workflow_id in reusable,
        )
        classification = _classify_sources(sources)
        items.append(WorkflowParityItem(
            workflow_id=workflow_id,
            classification=classification,
            hve_id=workflow_id if workflow_id in hve else None,
            cloud_bash_id=workflow_id if workflow_id in bash else None,
            reusable_workflow_id=workflow_id if workflow_id in reusable else None,
        ))

    return WorkflowParityReport(items=tuple(items))


def _alias_item(
    workflow_id: str,
    hve: set[str],
    bash: set[str],
    reusable: set[str],
    aliases: Mapping[str, Tuple[str, ...]],
) -> Optional[WorkflowParityItem]:
    if workflow_id not in aliases or workflow_id not in hve:
        return None
    for alias in aliases[workflow_id]:
        if alias in bash:
            return WorkflowParityItem(
                workflow_id=workflow_id,
                classification="legacy-alias",
                hve_id=workflow_id,
                cloud_bash_id=alias,
                reusable_workflow_id=workflow_id if workflow_id in reusable else None,
                alias_of=alias,
            )
    return None


def _classify_sources(sources: tuple[bool, bool, bool]) -> str:
    in_hve, in_bash, in_reusable = sources
    if in_hve and not in_bash and not in_reusable:
        return "hve-only"
    if not in_hve and in_bash and not in_reusable:
        return "cloud-bash-only"
    if not in_hve and not in_bash and in_reusable:
        return "cloud-reusable-only"
    if in_hve and not in_bash and in_reusable:
        return "missing-bash-registry"
    if not in_hve and in_bash and in_reusable:
        return "cloud-only"
    if in_hve and in_bash and not in_reusable:
        return "missing-reusable-workflow"
    return "unknown"


# ---------------------------------------------------------------------------
# Step-level parity helpers (P2-1)
# ---------------------------------------------------------------------------

def extract_bash_workflow_steps(
    registry_path: str | Path,
    workflow_id: str,
) -> Tuple[str, ...]:
    """Extract non-container step IDs for *workflow_id* from workflow-registry.sh.

    The bash registry embeds each workflow's definition as a JSON heredoc:

        _WORKFLOW_REGISTRY[<id>]=$(cat <<'JSONEOF'
        { "steps": [...] }
        JSONEOF
        )

    Returns an empty tuple when the workflow is not found or the JSON is invalid.
    """
    try:
        text = Path(registry_path).read_text(encoding="utf-8")
    except OSError as exc:
        warnings.warn(
            f"extract_bash_workflow_steps: failed to read registry file "
            f"{registry_path}: {exc}. Returning no steps for workflow '{workflow_id}'.",
            stacklevel=2,
        )
        return ()
    pattern = (
        r"_WORKFLOW_REGISTRY\[" + re.escape(workflow_id) + r"\]=\$\(cat <<'JSONEOF'\n"
        r"(.*?)\nJSONEOF"
    )
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return ()
    try:
        workflow_def: dict[str, Any] = json.loads(match.group(1))
        return tuple(
            step["id"]
            for step in workflow_def.get("steps", [])
            if not step.get("is_container", False)
        )
    except (json.JSONDecodeError, KeyError) as exc:
        warnings.warn(
            f"extract_bash_workflow_steps: failed to parse JSON for workflow "
            f"'{workflow_id}' in {registry_path}: {exc}. "
            f"Check that the workflow ID exists and the heredoc JSON is valid.",
            stacklevel=2,
        )
        return ()


def compare_step_definitions(
    bash_workflow_id: str,
    hve_workflow_id: str,
    bash_steps: Sequence[str],
    hve_steps: Sequence[str],
) -> dict[str, Any]:
    """Compare bash and hve workflow step ID lists and return a diff summary.

    Args:
        bash_workflow_id: Workflow ID as registered in workflow-registry.sh.
        hve_workflow_id:  Workflow ID as registered in hve workflow_registry.py.
        bash_steps:       Step ID list extracted from the bash registry.
        hve_steps:        Step ID list extracted from the hve registry.

    Returns:
        {
            "bash_workflow_id": str,
            "hve_workflow_id":  str,
            "bash_only": [...],   # step IDs present only in bash
            "hve_only":  [...],   # step IDs present only in hve
            "common":    [...],   # step IDs present in both
            "in_sync":   bool,    # True when both lists contain the same IDs
        }
    """
    bash_set = set(bash_steps)
    hve_set = set(hve_steps)
    return {
        "bash_workflow_id": bash_workflow_id,
        "hve_workflow_id": hve_workflow_id,
        "bash_only": sorted(bash_set - hve_set),
        "hve_only": sorted(hve_set - bash_set),
        "common": sorted(bash_set & hve_set),
        "in_sync": bash_set == hve_set,
    }


def compare_step_metadata(
    bash_workflow_id: str,
    hve_workflow_id: str,
    bash_step_data: Sequence[Mapping[str, Any]],
    hve_step_data: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare per-step agent names and depends_on between bash and hve.

    Only steps whose IDs appear in both registries are compared.
    Fields that cannot be retrieved from a side are omitted from the diff.

    Args:
        bash_workflow_id: Workflow ID as registered in workflow-registry.sh.
        hve_workflow_id:  Workflow ID as registered in hve workflow_registry.py.
        bash_step_data:   List of step dicts from the bash registry JSON
                          (keys: ``id``, ``custom_agent``, ``depends_on``).
        hve_step_data:    List of step dicts from the hve registry
                          (keys: ``id``, ``custom_agent``, ``depends_on``).

    Returns:
        {
            "bash_workflow_id": str,
            "hve_workflow_id":  str,
            "diffs": [           # one entry per differing step
                {
                    "step_id": str,
                    "field":   str,   # "custom_agent" | "depends_on"
                    "bash":    Any,
                    "hve":     Any,
                }
            ],
            "in_sync": bool,
        }

    .. note::
        ``depends_on`` values are compared as *sets* (order-insensitive).
    """
    def _index_by_id(
        step_data: Sequence[Mapping[str, Any]],
        source_name: str,
    ) -> dict[str, Mapping[str, Any]]:
        indexed: dict[str, Mapping[str, Any]] = {}
        for i, step in enumerate(step_data):
            step_id = step.get("id")
            if not isinstance(step_id, str):
                warnings.warn(
                    f"compare_step_metadata: skipping {source_name} step at index {i} "
                    f"without a valid 'id' field.",
                    stacklevel=3,
                )
                continue
            indexed[step_id] = step
        return indexed

    bash_by_id = _index_by_id(bash_step_data, "bash")
    hve_by_id = _index_by_id(hve_step_data, "hve")
    common_ids = sorted(set(bash_by_id) & set(hve_by_id))

    diffs: list[dict[str, Any]] = []
    for step_id in common_ids:
        b = bash_by_id[step_id]
        h = hve_by_id[step_id]

        # Compare custom_agent when both sides provide the field
        if "custom_agent" in b and "custom_agent" in h:
            if b["custom_agent"] != h["custom_agent"]:
                diffs.append({
                    "step_id": step_id,
                    "field": "custom_agent",
                    "bash": b["custom_agent"],
                    "hve": h["custom_agent"],
                })

        # Compare depends_on as sets (order-insensitive)
        if "depends_on" in b and "depends_on" in h:
            if set(b["depends_on"]) != set(h["depends_on"]):
                diffs.append({
                    "step_id": step_id,
                    "field": "depends_on",
                    "bash": sorted(b["depends_on"]),
                    "hve": sorted(h["depends_on"]),
                })

    return {
        "bash_workflow_id": bash_workflow_id,
        "hve_workflow_id": hve_workflow_id,
        "diffs": diffs,
        "in_sync": len(diffs) == 0,
    }
