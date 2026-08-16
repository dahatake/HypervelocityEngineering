"""AI Agent capability artifact validator tests (Sub-22)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from hve.artifact_validation import (
    validate_ai_agent_capability_artifacts,
    validate_ai_agent_design_artifact,
    validate_ai_agent_implementation_artifacts,
)


_CONTRACT_HEADINGS = (
    "Goal Contract（AG-CAP-01）",
    "Runtime Goal Loop（AG-CAP-02）",
    "Knowledge & Structured Data Routing（AG-CAP-03）",
    "REST CRUD Matrix（AG-CAP-04）",
    "MCP Integration Plan（AG-CAP-05）",
    "Skill Packaging Decision（AG-CAP-06）",
)


def _design_text(*, reasoned_na: bool = False, skill_required: bool = False) -> str:
    mutation_intent = "none" if reasoned_na else "required"
    if reasoned_na:
        routing = """#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）
- Status: N/A
- Reason: This Agent transforms only caller-provided local input and retrieves no external data.
- Decision source: docs/agent/agent-application-definition.md#Scope
- Recheck condition: Re-evaluate when an external or operational data source becomes required for Done.
"""
        crud = """##### REST CRUD Matrix（AG-CAP-04）
- Status: N/A
- Reason: Mutation Intent is none and the use case has no operational API read or persistent state change.
- Decision source: docs/agent/agent-application-definition.md#Goal-Contract
- Recheck condition: Re-evaluate when Create, Read, Update, or Delete of business state is requested.
"""
        mcp = """#### 7.3 MCP Integration Plan（AG-CAP-05）
- Status: N/A
- Reason: No retrieval or external Tool server is required by this local transformation Agent.
- Decision source: docs/agent/agent-architecture.md#Agent-Boundary
- Recheck condition: Re-evaluate when a remote retrieval or schema Tool becomes required.
"""
    else:
        routing = """#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）
| Request class | Data source | Required for Done | Preferred route | Design status | Checked at | Runtime probe | Fallback route | Blocked condition | Permission boundary | Citation requirement | Decision source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| operational-api-read | Order service | yes | orders-search | supported | 2026-07-10 | Verify service health and delegated scope | none: block rather than substitute another source | Stop and Handoff when the API or delegated scope is unavailable | delegated order-reader scope | correlation ID and observed timestamp | docs/catalog/service-catalog-matrix.md#Orders |
"""
        crud = """##### REST CRUD Matrix（AG-CAP-04）
| Tool ID | Operation | Required | REST method | REST path | Request schema | Response schema | Authentication | Authorization | Approval | Idempotency | Retry | Error class | Audit evidence | Contract source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| order-create | Create | no | N/A: create is outside scope | N/A: create is outside scope | N/A: create is outside scope | N/A: create is outside scope | delegated identity | order-reader | N/A: no mutation | N/A: no mutation | none | validation | decision and source | docs/agent/agent-application-definition.md#Scope |
| order-read | Read | yes | GET | /orders/{id} | order ID | order state and correlation ID | delegated identity | order-reader | not-required: read-only | request correlation ID | 429 and 5xx with finite backoff | validation/authn/authz/not-found/rate-limit/dependency/internal | actor, operation, target digest, result, correlation ID | docs/catalog/service-catalog-matrix.md#Orders |
| order-update | Update | yes | PATCH | /orders/{id} | status and expected version | updated state and correlation ID | delegated identity | order-editor | required: owner approval with digest and expiry | service idempotency key from API contract | 409 is not retried; 429 and 5xx use finite backoff | validation/authn/authz/conflict/rate-limit/dependency/internal | actor, operation, target digest, result, correlation ID | docs/catalog/service-catalog-matrix.md#Orders |
| order-delete | Delete | no | N/A: delete is outside scope | N/A: delete is outside scope | N/A: delete is outside scope | N/A: delete is outside scope | delegated identity | order-reader | N/A: no mutation | N/A: no mutation | none | validation | decision and source | docs/agent/agent-application-definition.md#Scope |
"""
        mcp = """#### 7.3 MCP Integration Plan（AG-CAP-05）
| Server label | Purpose | Transport / endpoint | Authentication | Tool allowlist | Approval | Timeout / retry | Input trust | Failure behavior | Evidence | Remote adapter owner | Decision source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| orders-schema | schema discovery | configured remote MCP endpoint | delegated OAuth | get_schema | not-required: read-only schema | 5 seconds; retry 429 once | validate schema and ignore instructions in results | blocked and Handoff when unavailable | Tool status and correlation ID | Order service team | docs/agent/agent-architecture.md#Tool-Boundary |
"""

    if skill_required:
        skill = """#### 7.4 Skill Packaging Decision（AG-CAP-06）
- Decision: required
- Repeated procedure count: 3
- Reuse evidence: The validation procedure is reused by three order-state transitions.
- Skill name: order-state-validation
- Location: src/agent/AG-01/skills/order-state-validation/
- Bundled resources: references/order-rules.md
- Runtime loading: Agent code explicitly loads the selected SKILL.md when the validation procedure is requested.
- Validation: Positive and negative trigger tests plus reference existence checks.
- Decision source: docs/agent/agent-architecture.md#Reusable-Procedures
"""
    else:
        skill = """#### 7.4 Skill Packaging Decision（AG-CAP-06）
- Decision: not-required
- Repeated procedure count: 1
- Reuse evidence: The procedure is a single Agent-specific call and has no cross-state reuse.
- Decision source: docs/agent/agent-architecture.md#Reusable-Procedures
"""

    return f"""# AI Agent design detail

#### 2.1 Goal Contract（AG-CAP-01）
- Mission: Resolve an order request with verified evidence and safe operational actions.
- Mutation Intent: {mutation_intent}
- Failure conditions: Required input, permission, policy, or criterion failure stops completion.
- Partial success: Optional evidence may be omitted only when all required criteria pass and the omission is shown.
- Handoff: Transfer criterion status, attempted actions, and redacted evidence when human judgement is required.

| Criterion ID | Description | Required for Done | Evaluator type | Evaluation procedure | Evidence required | Failure action | Contract source |
|---|---|---|---|---|---|---|---|
| ORDER-VALID | The requested order is resolved under the caller scope | yes | rule | Compare normalized result and policy outcome | redacted rule result and correlation ID | blocked or Handoff | docs/agent/agent-application-definition.md#Goal-Contract |

#### 6.1 Runtime Goal Loop（AG-CAP-02）
- States: PLAN, ACT, OBSERVE, EVALUATE, REPLAN
- Max iterations: 3
- Operation deadline: 30 seconds for the complete request
- Tool budget: 4 calls per request
- Cost budget: 8000 input and output tokens per request
- Action fingerprint: canonical Tool operation target and SHA-256 arguments; repeated actions require new Evidence.
- Evidence: Each iteration records criterion status, Tool result ID, timestamp, and redacted summary.
- Stop conditions: DONE, PARTIAL, BLOCKED, HANDOFF, MAX_ITERATIONS, DEADLINE, POLICY_STOP, USER_CANCELLED, DEGRADATION

{routing}
{crud}
{mcp}
{skill}
"""


def _system_prompt() -> str:
    return """# Role
Order resolution Agent.
## Goals
Resolve the required criterion.
## Non-Goals
Do not invent order state.
## Inputs
Validated order request.
## Tools
Only allowlisted REST and MCP Tools.
## Runtime Goal Loop
PLAN, ACT, OBSERVE, EVALUATE, and REPLAN with finite limits.
## Routing
Use only the selected route and approved fallback.
## Procedure
Evaluate evidence after each action.
## Output format
Return status, evidence summary, and next action.
## Safeguards
Require approval for mutation and redact secrets.
"""


def _python_source() -> str:
    return '''"""AG-CAP-01 AG-CAP-02 AG-CAP-03 AG-CAP-04 implementation."""
from enum import Enum

SELECTED_ROUTE = "orders-search"
REST_READ_TOOL_ID = "order-read"
REST_READ_METHOD = "GET"
REST_TOOL_ID = "order-update"
REST_METHOD = "PATCH"
REST_PATH = "/orders/{id}"

class GoalLoopState(Enum):
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    HANDOFF = "HANDOFF"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    DEADLINE = "DEADLINE"
    POLICY_STOP = "POLICY_STOP"
    USER_CANCELLED = "USER_CANCELLED"
    DEGRADATION = "DEGRADATION"

def plan(criterion_results, evidence):
    return (criterion_results, evidence)

def act(action, approval_digest, idempotency_key):
    # HTTP client adapter classifies validation/authn/authz/conflict/rate-limit/dependency/internal.
    audit_evidence = {"actor": "redacted", "operation": REST_TOOL_ID, "result": "pending"}
    return action, approval_digest, idempotency_key, audit_evidence

def send_rest_request(http_client, payload):
    # Finite retry policy applies only to classified rate-limit/dependency errors.
    return http_client.request(REST_METHOD, REST_PATH, json=payload)

def route_request(request_class, request):
    if request_class != "operational-api-read":
        raise ValueError("Request class outside selected route")
    return SELECTED_ROUTE, request

def observe(tool_result, correlation_id):
    return {"status": tool_result, "correlation_id": correlation_id}

def evaluate(observation, criterion_results, evidence):
    return observation, criterion_results, evidence

def run_goal_loop(config, actions):
    attempted_action_fingerprints = set()
    for iteration in range(config["max_iterations"]):
        planned = plan([], [])
        result = act(planned, "approval-digest", "idempotency-key")
        observation = observe(result, "correlation-id")
        evaluation = evaluate(observation, [], [])
        if evaluation:
            return GoalLoopState.DONE
        attempted_action_fingerprints.add(str(iteration))
    return GoalLoopState.MAX_ITERATIONS
'''


def _mcp_source() -> str:
    return '''"""AG-CAP-05 MCP client contract."""
SERVER_LABEL = "orders-schema"
TOOL_ALLOWLIST = {"get_schema"}
AUTHENTICATION = "delegated OAuth"
TIMEOUT_SECONDS = 5
FAILURE_BEHAVIOR = "blocked and Handoff"

def call_mcp(tool_name, untrusted_result):
    if tool_name not in TOOL_ALLOWLIST:
        raise PermissionError("Tool outside allowlist")
    return {"status": "validated", "result": str(untrusted_result)}
'''


def _csharp_source() -> str:
    return '''// AG-CAP-01 AG-CAP-02 AG-CAP-03 AG-CAP-04 AG-CAP-05
public enum GoalLoopState { DONE, PARTIAL, BLOCKED, HANDOFF, MAX_ITERATIONS, DEADLINE, POLICY_STOP, USER_CANCELLED, DEGRADATION }
public sealed class GoalLoop {
  private const string Route = "orders-search";
    private const string ReadToolId = "order-read";
    private const string ReadMethod = "GET";
  private const string ToolId = "order-update";
  private const string Method = "PATCH";
  private const string Path = "/orders/{id}";
  private const string McpServer = "orders-schema";
  private const string McpToolAllowlist = "get_schema";
    private const string McpAuthentication = "delegated OAuth";
    private const int McpTimeoutSeconds = 5;
    private const string McpFailureBehavior = "blocked and Handoff";
    private const string ErrorClassification = "validation authn authz conflict rate-limit dependency internal";
    private const string RetryPolicy = "finite retry for rate-limit and dependency errors";
  public object Plan(object criteria, object evidence) => evidence;
  public object Act(object action, object approval, object idempotency, object audit) => action;
  public object Observe(object toolResult, object correlationId) => toolResult;
  public object Evaluate(object observation, object criterionResult, object evidence) => observation;
    public object SendRestRequest(HttpClient httpClient, object payload, object approval, object idempotency, object audit) => httpClient.Send(new HttpRequestMessage(new HttpMethod(Method), Path));
    public object RouteRequest(string requestClass, object request) => requestClass == "operational-api-read" ? request : throw new InvalidOperationException();
  public GoalLoopState RunGoalLoop(int maxIterations) {
        var attemptedActionFingerprints = new HashSet<string>();
    for (var iteration = 0; iteration < maxIterations; iteration++) {
      var evidence = Evaluate(Observe(Act("action", "approval", "idempotency", "audit"), "correlation"), "criterion", "evidence");
      if (evidence != null) return GoalLoopState.DONE;
    }
    return GoalLoopState.MAX_ITERATIONS;
  }
}
'''


def _test_spec() -> str:
    rows = "\n".join(
        f"| TEST-AG-CAP-0{index} | AG-CAP-0{index} | deterministic mock result and redacted Evidence |"
        for index in range(1, 7)
    )
    return f"""# Agent capability test specification
| Test Case ID | Contract ID | Evidence |
|---|---|---|
{rows}
"""


def _write_design(
    root: Path,
    *,
    reasoned_na: bool = False,
    skill_required: bool = False,
) -> Path:
    path = root / "docs" / "agent" / "agent-detail-AG-01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _design_text(
            reasoned_na=reasoned_na,
            skill_required=skill_required,
        ),
        encoding="utf-8",
    )
    return path


def _write_implementation(
    root: Path,
    *,
    language: str = "python",
    skill_required: bool = False,
) -> tuple[Path, Path]:
    agent_dir = root / "src" / "agent" / "AG-01"
    prompt_path = agent_dir / "prompts" / "system-prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(_system_prompt(), encoding="utf-8")

    config = {
        "max_iterations": 3,
        "selected_routes": [
            {
                "request_class": "operational-api-read",
                "preferred_route": "orders-search",
                "fallback_route": "none",
            }
        ],
        "rest_tools": [
            {"tool_id": "order-read", "method": "GET", "path": "/orders/{id}"},
            {"tool_id": "order-update", "method": "PATCH", "path": "/orders/{id}"}
        ],
        "mcp_servers": [
            {"server_label": "orders-schema", "tool_allowlist": ["get_schema"]}
        ],
    }
    config_name = "appsettings.json" if language == "csharp" else "agent-config.json"
    (agent_dir / config_name).write_text(json.dumps(config), encoding="utf-8")
    (agent_dir / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "ag-01",
                "description": "Order resolution agent packaged as an Agent Plugin.",
                "version": "0.1.0",
            }
        ),
        encoding="utf-8",
    )
    if language == "csharp":
        (agent_dir / "GoalLoop.cs").write_text(_csharp_source(), encoding="utf-8")
    else:
        (agent_dir / "agent.py").write_text(_python_source(), encoding="utf-8")
        (agent_dir / "mcp_client.py").write_text(_mcp_source(), encoding="utf-8")

    if skill_required:
        skill_dir = agent_dir / "skills" / "order-state-validation"
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: order-state-validation
description: Validate order transitions when an order mutation is requested.
---
# Procedure
Validate the transition.
## Input
Normalized order and target state.
## Output
A deterministic validation result.
## Errors
Return a classified validation error.
## Completion
Complete only after all rules pass.
""",
            encoding="utf-8",
        )
        (skill_dir / "references" / "order-rules.md").write_text(
            "# Order rules\nValidated transition rules.\n",
            encoding="utf-8",
        )
        source_path = agent_dir / ("GoalLoop.cs" if language == "csharp" else "agent.py")
        if language == "csharp":
            loading_source = """
// AG-CAP-06 explicit runtime loading for skills/order-state-validation/SKILL.md
public static class SkillLoader {
  public static string LoadSkill(string path) => File.ReadAllText(path);
}
"""
        else:
            loading_source = """
# AG-CAP-06 explicit runtime loading for skills/order-state-validation/SKILL.md
def load_skill(skill_path):
    with open(skill_path, encoding="utf-8") as handle:
        return handle.read()
"""
        source_path.write_text(
            source_path.read_text(encoding="utf-8") + loading_source,
            encoding="utf-8",
        )

    test_spec = root / "docs" / "test-specs" / "AG-01-test-spec.md"
    test_spec.parent.mkdir(parents=True, exist_ok=True)
    test_spec.write_text(_test_spec(), encoding="utf-8")
    return agent_dir, test_spec


def test_valid_minimal_design_passes(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    assert validate_ai_agent_design_artifact(detail) == []


def test_design_rejects_each_missing_contract(tmp_path: Path) -> None:
    for index, heading in enumerate(_CONTRACT_HEADINGS):
        detail = _write_design(tmp_path / str(index))
        detail.write_text(
            detail.read_text(encoding="utf-8").replace(heading, f"Missing {heading}"),
            encoding="utf-8",
        )
        errors = validate_ai_agent_design_artifact(detail)
        assert any(heading.split("（", 1)[0] in error for error in errors)


def test_design_requires_structured_routing_not_provider_name_only(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    text = detail.read_text(encoding="utf-8")
    start = text.index("#### 7.0 Knowledge")
    end = text.index("##### REST CRUD Matrix")
    detail.write_text(
        text[:start]
        + "#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）\nWork IQ\n\n"
        + text[end:],
        encoding="utf-8",
    )
    errors = validate_ai_agent_design_artifact(detail)
    assert any("AG-CAP-03" in error and "table" in error.lower() for error in errors)


def test_design_ignores_fenced_and_indented_code_block_tables(tmp_path: Path) -> None:
    for index, wrapper in enumerate(("fenced", "indented")):
        detail = _write_design(tmp_path / wrapper)
        text = detail.read_text(encoding="utf-8")
        start = text.index("#### 7.0 Knowledge")
        end = text.index("##### REST CRUD Matrix")
        section = text[start:end].rstrip()
        heading, table = section.split("\n", 1)
        if wrapper == "fenced":
            replacement = f"{heading}\n```markdown\n{table}\n```\n\n"
        else:
            replacement = heading + "\n" + "\n".join(
                f"    {line}" for line in table.splitlines()
            ) + "\n\n"
        detail.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
        errors = validate_ai_agent_design_artifact(detail)
        assert any("AG-CAP-03" in error and "table" in error.lower() for error in errors), index


def test_design_rejects_missing_contract_fields_and_invalid_decisions(tmp_path: Path) -> None:
    replacements = (
        ("- Mission: Resolve an order request with verified evidence and safe operational actions.\n", "", "AG-CAP-01"),
        ("- Max iterations: 3", "- Max iterations: TBD", "AG-CAP-02"),
        ("| orders-schema | schema discovery | configured remote MCP endpoint | delegated OAuth | get_schema |", "| orders-schema | schema discovery | configured remote MCP endpoint | delegated OAuth | * |", "AG-CAP-05"),
        ("- Decision: not-required", "- Decision: TBD", "AG-CAP-06"),
    )
    for index, (old, new, contract_id) in enumerate(replacements):
        detail = _write_design(tmp_path / str(index))
        detail.write_text(
            detail.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        errors = validate_ai_agent_design_artifact(detail)
        assert any(contract_id in error for error in errors)


def test_design_rejects_tbd_duplicate_criterion_and_unapproved_mutation(
    tmp_path: Path,
) -> None:
    cases = (
        ("- Mutation Intent: required", "- Mutation Intent: TBD", "Mutation Intent"),
        (
            "| ORDER-VALID | The requested order is resolved under the caller scope | yes | rule | Compare normalized result and policy outcome | redacted rule result and correlation ID | blocked or Handoff | docs/agent/agent-application-definition.md#Goal-Contract |",
            "| ORDER-VALID | The requested order is resolved under the caller scope | yes | rule | Compare normalized result and policy outcome | redacted rule result and correlation ID | blocked or Handoff | docs/agent/agent-application-definition.md#Goal-Contract |\n"
            "| ORDER-VALID | Duplicate criterion | yes | rule | Compare duplicate | duplicate evidence | blocked | docs/agent/agent-application-definition.md#Goal-Contract |",
            "duplicate Criterion ID",
        ),
        (
            "required: owner approval with digest and expiry",
            "auto-approved without human review",
            "HITL approval",
        ),
    )
    for index, (old, new, expected) in enumerate(cases):
        detail = _write_design(tmp_path / str(index))
        detail.write_text(
            detail.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        errors = validate_ai_agent_design_artifact(detail)
        assert any(expected in error for error in errors)


def test_reasoned_na_is_allowed_and_bare_na_is_rejected(tmp_path: Path) -> None:
    detail = _write_design(tmp_path, reasoned_na=True)
    assert validate_ai_agent_design_artifact(detail) == []

    text = detail.read_text(encoding="utf-8")
    text = text.replace(
        "- Reason: This Agent transforms only caller-provided local input and retrieves no external data.\n"
        "- Decision source: docs/agent/agent-application-definition.md#Scope\n"
        "- Recheck condition: Re-evaluate when an external or operational data source becomes required for Done.\n",
        "- Reason: N/A\n",
    )
    detail.write_text(text, encoding="utf-8")
    errors = validate_ai_agent_design_artifact(detail)
    assert any("AG-CAP-03" in error and "N/A" in error for error in errors)


def test_missing_design_path_fails(tmp_path: Path) -> None:
    errors = validate_ai_agent_design_artifact(tmp_path / "missing.md")
    assert errors and "not found" in errors[0].lower()


def test_valid_python_and_csharp_implementations_pass(tmp_path: Path) -> None:
    for language in ("python", "csharp"):
        root = tmp_path / language
        detail = _write_design(root)
        agent_dir, test_spec = _write_implementation(root, language=language)
        assert validate_ai_agent_implementation_artifacts(
            detail,
            agent_dir,
            test_spec,
        ) == []


def test_implementation_rejects_missing_core_artifacts(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    (agent_dir / "prompts" / "system-prompt.md").unlink()
    (agent_dir / "agent-config.json").unlink()
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("System Prompt" in error for error in errors)
    assert any("configuration" in error.lower() for error in errors)


def test_implementation_rejects_route_rest_mcp_and_runtime_gaps(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    (agent_dir / "agent.py").write_text(
        '# AG-CAP-01\nSELECTED_ROUTE = "orders-search"\n',
        encoding="utf-8",
    )
    (agent_dir / "mcp_client.py").unlink()
    config_path = agent_dir / "agent-config.json"
    config_path.write_text(json.dumps({"max_iterations": 3}), encoding="utf-8")
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("AG-CAP-02" in error for error in errors)
    assert any("AG-CAP-03" in error for error in errors)
    assert any("route adapter" in error for error in errors)
    assert any("AG-CAP-04" in error for error in errors)
    assert any("AG-CAP-05" in error for error in errors)


def test_comment_only_runtime_callables_do_not_pass(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    source_path = agent_dir / "agent.py"
    source = source_path.read_text(encoding="utf-8")
    for name in ("plan", "act", "observe", "evaluate"):
        source = source.replace(f"def {name}(", f"# def {name}(")
    source_path.write_text(source, encoding="utf-8")
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    for name in ("plan", "act", "observe", "evaluate"):
        assert any(f"callable {name}" in error for error in errors)


def test_structured_route_names_as_config_keys_are_supported(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    config_path = agent_dir / "agent-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["selected_routes"] = {
        "operational-api-read": {
            "orders-search": {"enabled": True},
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec) == []


def test_required_skill_resources_and_explicit_loading_are_enforced(tmp_path: Path) -> None:
    detail = _write_design(tmp_path, skill_required=True)
    agent_dir, test_spec = _write_implementation(tmp_path)
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("AG-CAP-06" in error and "SKILL.md" in error for error in errors)

    agent_dir, test_spec = _write_implementation(tmp_path, skill_required=True)
    assert validate_ai_agent_implementation_artifacts(
        detail,
        agent_dir,
        test_spec,
    ) == []


# ---------------------------------------------------------------------------
# FR-WF-AAGD-07: Agent Skills 仕様の frontmatter 長さ制約
# ---------------------------------------------------------------------------

_SKILL_BODY = """# Procedure
Validate the transition.
## Input
Normalized order and target state.
## Output
A deterministic validation result.
## Errors
Return a classified validation error.
## Completion
Complete only after all rules pass.
"""


def _write_skill_case(
    root: Path,
    *,
    skill_name: str = "order-state-validation",
    description: str = "Validate order transitions when an order mutation is requested.",
) -> tuple[Path, Path, Path]:
    detail = _write_design(root, skill_required=True)
    agent_dir, test_spec = _write_implementation(root, skill_required=True)

    if skill_name != "order-state-validation":
        for path in (detail, agent_dir / "agent.py"):
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "order-state-validation", skill_name
                ),
                encoding="utf-8",
            )
        (agent_dir / "skills" / "order-state-validation").rename(
            agent_dir / "skills" / skill_name
        )

    (agent_dir / "skills" / skill_name / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n---\n{_SKILL_BODY}",
        encoding="utf-8",
    )
    return detail, agent_dir, test_spec


def _skill_errors(errors: list) -> list:
    return [error for error in errors if "AG-CAP-06" in error]


def test_skill_name_at_the_length_limit_passes(tmp_path: Path) -> None:
    detail, agent_dir, test_spec = _write_skill_case(tmp_path, skill_name="a" * 64)
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert _skill_errors(errors) == [], errors


def test_skill_name_longer_than_64_characters_fails(tmp_path: Path) -> None:
    detail, agent_dir, test_spec = _write_skill_case(tmp_path, skill_name="a" * 65)
    errors = _skill_errors(
        validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    )
    assert any("64" in error for error in errors), errors


def test_skill_description_at_the_length_limit_passes(tmp_path: Path) -> None:
    detail, agent_dir, test_spec = _write_skill_case(tmp_path, description="d" * 1024)
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert _skill_errors(errors) == [], errors


def test_skill_description_longer_than_1024_characters_fails(tmp_path: Path) -> None:
    detail, agent_dir, test_spec = _write_skill_case(tmp_path, description="d" * 1025)
    errors = _skill_errors(
        validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    )
    assert any("1024" in error for error in errors), errors



def test_not_required_skill_rejects_unapproved_skill_artifact(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    skill_dir = agent_dir / "skills" / "unused"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("unused", encoding="utf-8")
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("AG-CAP-06" in error and "not-required" in error for error in errors)


def test_secret_values_are_rejected_but_redacted_placeholders_are_allowed(
    tmp_path: Path,
) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    config_path = agent_dir / "agent-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["client_secret"] = "super-secret-production-value"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("secret-like" in error.lower() for error in errors)
    assert all("super-secret-production-value" not in error for error in errors)

    config["client_secret"] = "${ORDER_CLIENT_SECRET}"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    source_path = agent_dir / "agent.py"
    source_path.write_text(
        source_path.read_text(encoding="utf-8")
        + '\ntoken = credential.get_token(scope)\nheaders = {"Authorization": f"Bearer {token}"}\n',
        encoding="utf-8",
    )
    assert validate_ai_agent_implementation_artifacts(
        detail,
        agent_dir,
        test_spec,
    ) == []


def test_reasoned_na_implementation_has_no_unselected_artifacts(tmp_path: Path) -> None:
    detail = _write_design(tmp_path, reasoned_na=True)
    agent_dir = tmp_path / "src" / "agent" / "AG-01"
    prompt_path = agent_dir / "prompts" / "system-prompt.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text(_system_prompt(), encoding="utf-8")
    (agent_dir / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "ag-01",
                "description": "Local transformation agent packaged as an Agent Plugin.",
                "version": "0.1.0",
            }
        ),
        encoding="utf-8",
    )
    (agent_dir / "agent-config.json").write_text(
        json.dumps(
            {
                "max_iterations": 3,
                "selected_routes": [],
                "rest_tools": [],
                "mcp_servers": [],
            }
        ),
        encoding="utf-8",
    )
    (agent_dir / "agent.py").write_text(
        '''"""AG-CAP-01 and AG-CAP-02 local runtime implementation."""
from enum import Enum
class GoalLoopState(Enum):
    DONE = "DONE"; PARTIAL = "PARTIAL"; BLOCKED = "BLOCKED"; HANDOFF = "HANDOFF"
    MAX_ITERATIONS = "MAX_ITERATIONS"; DEADLINE = "DEADLINE"; POLICY_STOP = "POLICY_STOP"
    USER_CANCELLED = "USER_CANCELLED"; DEGRADATION = "DEGRADATION"
def plan(criteria, evidence): return criteria, evidence
def act(action): return action
def observe(result): return result
def evaluate(observation, criterion_results, evidence): return observation, criterion_results, evidence
def run_goal_loop(config):
    attempted_action_fingerprints = set()
    for iteration in range(config["max_iterations"]):
        evidence = evaluate(observe(act(plan([], [])[0])), [], [])
        attempted_action_fingerprints.add(str(iteration))
        if evidence: return GoalLoopState.DONE
    return GoalLoopState.MAX_ITERATIONS
''',
        encoding="utf-8",
    )
    test_spec = tmp_path / "docs" / "test-specs" / "AG-01-test-spec.md"
    test_spec.parent.mkdir(parents=True)
    test_spec.write_text(_test_spec(), encoding="utf-8")
    assert validate_ai_agent_implementation_artifacts(
        detail,
        agent_dir,
        test_spec,
    ) == []


def test_reasoned_na_rejects_route_rest_and_mcp_artifacts(tmp_path: Path) -> None:
    detail = _write_design(tmp_path, reasoned_na=True)
    agent_dir, test_spec = _write_implementation(tmp_path)
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("AG-CAP-03" in error and "conflicts" in error for error in errors)
    assert any("AG-CAP-04" in error and "conflicts" in error for error in errors)
    assert any("AG-CAP-05" in error and "conflicts" in error for error in errors)


def test_nested_symlink_is_rejected_when_supported(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "fixture.py").write_text(
        "VALUE = 'outside-symlink-fixture'",
        encoding="utf-8",
    )
    link = agent_dir / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        raise unittest.SkipTest(f"symlink unavailable: {exc}") from exc
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("symlink" in error.lower() for error in errors)


def test_empty_system_prompt_body_and_string_only_test_trace_fail(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    prompt_path = agent_dir / "prompts" / "system-prompt.md"
    prompt_path.write_text(
        prompt_path.read_text(encoding="utf-8").replace(
            "## Goals\nResolve the required criterion.",
            "## Goals",
        ),
        encoding="utf-8",
    )
    test_spec.write_text("AG-CAP-01 AG-CAP-02 AG-CAP-03 AG-CAP-04 AG-CAP-05 AG-CAP-06", encoding="utf-8")
    errors = validate_ai_agent_implementation_artifacts(detail, agent_dir, test_spec)
    assert any("Goals" in error and "body" in error for error in errors)
    assert any("trace table" in error for error in errors)


def test_missing_agent_directory_and_test_trace_fail(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    errors = validate_ai_agent_implementation_artifacts(
        detail,
        tmp_path / "src" / "agent" / "AG-01",
        tmp_path / "docs" / "test-specs" / "AG-01-test-spec.md",
    )
    assert any("agent directory" in error.lower() for error in errors)
    assert any("test specification" in error.lower() for error in errors)


def test_workflow_dispatcher_is_noop_outside_aag_and_aagd(tmp_path: Path) -> None:
    assert validate_ai_agent_capability_artifacts(
        "aad-web",
        tmp_path / "missing.md",
    ) == []


def test_workflow_dispatcher_routes_aag_and_aagd(tmp_path: Path) -> None:
    detail = _write_design(tmp_path)
    agent_dir, test_spec = _write_implementation(tmp_path)
    assert validate_ai_agent_capability_artifacts("aag", detail) == []
    assert validate_ai_agent_capability_artifacts(
        "aagd",
        detail,
        agent_dir=agent_dir,
        test_spec_path=test_spec,
    ) == []
