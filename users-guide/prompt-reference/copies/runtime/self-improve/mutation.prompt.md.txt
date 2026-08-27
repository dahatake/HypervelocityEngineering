You are executing HVE Post-DAG Self-Improve MUTATE.
Perform actual minimal file edits. Do not merely describe changes.
Only edit the resolved repository-relative target paths listed below. Never edit work/,
tests to weaken/skip them, criterion definitions, permissions, RBAC, HITL, approvals,
or guardrails. Do not commit, revert, reset, clean, or discard pre-existing changes.

## Goal
{goal_description}

## Resolved target paths
{scope_paths_json}

## Criterion definitions (source/evaluator/evidence are binding)
{criterion_definitions_json}

## Before criterion results
{before_criterion_results_json}

## Scan summary
{scan_summary_json}

## Plan
{plan_json}

## Previous learning summary
{learning_summary}

After editing, return exactly one JSON object and no Markdown/code fence:
{{
  "status": "MUTATED|PARTIAL_FAILURE|IMPROVEMENT_NOT_NEEDED",
  "changed_files": ["repo/relative/path"],
  "failed_changes": [{{"path": "repo/relative/path", "error": "short error"}}],
  "no_change_reason": "non-empty only for IMPROVEMENT_NOT_NEEDED",
  "response_summary": "short non-sensitive summary"
}}
