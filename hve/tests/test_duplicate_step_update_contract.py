"""N5-1: 同じ Agent・同じ出力の後段 Step は既存成果物への差分追記に絞る（FR-WF-ASDW-06 / FR-WF-AAGD-10）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.workflow_registry import get_workflow

_ROOT = Path(__file__).resolve().parents[2]

_PAIRS = (
    # (前段 Workflow, Step, 後段 Workflow, Step, 共通の出力)
    ("aad-web", "2.5", "asdw-web", "2.1", "docs/azure/azure-services-additional.md"),
    ("aag", "1", "aagd", "1", "docs/agent/agent-application-definition.md"),
)


def _step(workflow_id: str, step_id: str):
    workflow = get_workflow(workflow_id)
    assert workflow is not None
    return next(s for s in workflow.steps if s.id == step_id)


@pytest.mark.parametrize("pair", _PAIRS, ids=lambda p: f"{p[2]}-{p[3]}")
def test_pairs_still_share_agent_and_output(pair) -> None:
    upstream = _step(pair[0], pair[1])
    downstream = _step(pair[2], pair[3])
    assert upstream.custom_agent == downstream.custom_agent
    assert pair[4] in upstream.output_paths
    assert pair[4] in downstream.output_paths


@pytest.mark.parametrize("pair", _PAIRS, ids=lambda p: f"{p[2]}-{p[3]}")
def test_downstream_body_reads_existing_output_and_appends_only_the_difference(pair) -> None:
    body_path = _ROOT / _step(pair[2], pair[3]).body_template_path
    body = body_path.read_text(encoding="utf-8")
    assert f"既存の `{pair[4]}` がある場合は読み" in body
    assert "差分だけを追記" in body
    assert "既存の記述を削除・再生成しない" in body
