"""Cloud/hve workflow parity helpers.

This module intentionally reports observed differences only. It does not try to
merge Cloud and hve DAG definitions or infer missing transitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Tuple


DEFAULT_WORKFLOW_ALIASES: Mapping[str, Tuple[str, ...]] = {
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
