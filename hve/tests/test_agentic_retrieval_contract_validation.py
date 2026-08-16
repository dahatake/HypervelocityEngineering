"""Agentic Retrieval 契約（AR-CAP-01〜05）validator テスト。

`agentic-retrieval-contract` Skill の整合ルール R1〜R12 を
`hve.artifact_validation` が決定的に検証することを確認する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import (
    _validate_agentic_retrieval_implementation,
    validate_ai_agent_design_artifact,
)


_ROUTING_WITH_FOUNDRY_IQ = """#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）
| Request class | Data source | Required for Done | Preferred route | Design status | Checked at | Runtime probe | Fallback route | Blocked condition | Permission boundary | Citation requirement | Decision source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enterprise-unstructured | Internal policy corpus | yes | Foundry IQ knowledge base | preview | 2026-08-04 | Verify knowledge base reachability and index read role | none: block rather than substitute another corpus | Stop and Handoff when no citation can be produced | project managed identity with index read role | source references with retrieval timestamp | docs/agent/agent-architecture.md#Knowledge-Boundary |
"""

_ROUTING_WITHOUT_FOUNDRY_IQ = """#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）
| Request class | Data source | Required for Done | Preferred route | Design status | Checked at | Runtime probe | Fallback route | Blocked condition | Permission boundary | Citation requirement | Decision source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| operational-api-read | Order service | yes | orders-search | supported | 2026-08-04 | Verify service health and delegated scope | none: block rather than substitute another source | Stop and Handoff when the API is unavailable | delegated order-reader scope | correlation ID and observed timestamp | docs/catalog/service-catalog-matrix.md#Orders |
"""

_CRUD_NA = """#### 7.1 REST CRUD Matrix（AG-CAP-04）
- Status: N/A
- Reason: Mutation Intent is none and the use case has no operational API read or persistent state change.
- Decision source: docs/agent/agent-application-definition.md#Goal-Contract
- Recheck condition: Re-evaluate when Create, Read, Update, or Delete of business state is requested.
"""

_MCP_NA = """#### 7.3 MCP Integration Plan（AG-CAP-05）
- Status: N/A
- Reason: No retrieval or external Tool server is required beyond the knowledge base connection.
- Decision source: docs/agent/agent-architecture.md#Agent-Boundary
- Recheck condition: Re-evaluate when a remote schema Tool becomes required.
"""

_SKILL_NOT_REQUIRED = """#### 7.4 Skill Packaging Decision（AG-CAP-06）
- Decision: not-required
- Repeated procedure count: 1
- Reuse evidence: The procedure is a single Agent-specific call and has no cross-state reuse.
- Decision source: docs/agent/agent-architecture.md#Reusable-Procedures
"""

_HEAD = """# AI Agent design detail

#### 2.1 Goal Contract（AG-CAP-01）
- Mission: Answer internal policy questions with cited evidence.
- Mutation Intent: none
- Failure conditions: Required input, permission, policy, or criterion failure stops completion.
- Partial success: Optional evidence may be omitted only when all required criteria pass and the omission is shown.
- Handoff: Transfer criterion status, attempted actions, and redacted evidence when human judgement is required.

| Criterion ID | Description | Required for Done | Evaluator type | Evaluation procedure | Evidence required | Failure action | Contract source |
|---|---|---|---|---|---|---|---|
| POLICY-CITED | The answer cites a required policy source | yes | rule | Compare normalized result and policy outcome | redacted rule result and correlation ID | blocked or Handoff | docs/agent/agent-application-definition.md#Goal-Contract |

#### 6.1 Runtime Goal Loop（AG-CAP-02）
- States: PLAN, ACT, OBSERVE, EVALUATE, REPLAN
- Max iterations: 3
- Operation deadline: 30 seconds for the complete request
- Tool budget: 4 calls per request
- Cost budget: 8000 input and output tokens per request
- Action fingerprint: canonical Tool operation target and SHA-256 arguments; repeated actions require new Evidence.
- Evidence: Each iteration records criterion status, Tool result ID, timestamp, and redacted summary.
- Stop conditions: DONE, PARTIAL, BLOCKED, HANDOFF, MAX_ITERATIONS, DEADLINE, POLICY_STOP, USER_CANCELLED, DEGRADATION
"""


def _ar_cap_01(
    *,
    effort: str = "low",
    output_mode: str = "answerSynthesis",
    ks_count: str = "2",
    region_line: str = "",
    checked_at: str = "2026-08-04",
    index_config: "str | None" = "policy-semantic-config on the policy-docs index",
) -> str:
    region = f"- Region availability: {region_line}\n" if region_line else ""
    index = (
        f"- Index semantic configuration: {index_config}\n"
        if index_config is not None
        else ""
    )
    return f"""#### 7.0.1 Knowledge Base Contract（AR-CAP-01）
- Status: selected
- Knowledge base name: policy-kb
- Knowledge domain: Internal HR and compliance policy documents.
- Query planning LLM: model-router
- Retrieval reasoning effort: {effort}
- Effort rationale: Balances latency against multi-source planning for policy questions.
- Output mode: {output_mode}
- Retrieval instructions: Prefer internal policy sources and skip web unless a publication date is requested.
- Knowledge source count: {ks_count}
{index}{region}- Design status: preview
- Checked at: {checked_at}
- Decision source: docs/agent/agent-architecture.md#Knowledge-Boundary
"""


_KS_HEADER = (
    "| KS name | Kind | Locality | Always query | Selection description | Ingestion "
    "| Freshness SLO | Permission boundary | Required for Done | Design status | Checked at | Decision source |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)

_KS_ROW_BLOB = (
    "| policy-docs | Azure blob | indexed | true: policy answers always need the internal corpus "
    "| Internal HR and compliance policy documents | indexer: scheduled crawl satisfies the freshness target "
    "| 24 hours | project managed identity with index read role | yes | supported | 2026-08-04 "
    "| docs/azure/azure-services-data.md#Policy |\n"
)

_KS_ROW_WEB = (
    "| public-news | Web | remote | false: only used when a publication date is requested "
    "| Public web news for publication dates | remote-live: no ingestion required "
    "| real time | public web with no tenant data sent | no | preview | 2026-08-04 "
    "| docs/agent/agent-architecture.md#Web |\n"
)


def _ar_cap_02(rows: str = _KS_ROW_BLOB + _KS_ROW_WEB) -> str:
    return "#### 7.0.2 Knowledge Source Matrix（AR-CAP-02）\n" + _KS_HEADER + rows


def _ar_cap_03(*, extra: str = "", llm_budget: str = "6000 tokens per request") -> str:
    return f"""#### 7.0.3 Retrieval Budget（AR-CAP-03）
- Expected subqueries per request: 2 to 4
- Retrieval token budget: 12000 tokens per request
- LLM token budget: {llm_budget}
- Latency target p50: 1200 ms
- Latency target p95: 3000 ms
- Max runtime: 30 seconds
- Max output size: 6000 characters
- Degradation policy: Drop the optional web source and return partial success with the missing source listed.
- Measurement method: Activity log subquery count and retrieve latency percentiles.
{extra}"""


def _ar_cap_04(*, references: str = "enabled: citations are required by the answer contract") -> str:
    return f"""#### 7.0.4 Evidence & Observability（AR-CAP-04）
- Source references: {references}
- Activity log: enabled: needed to measure subquery count
- Citation fields: source class, source identifier, path or URL, retrieval timestamp
- Blocked condition: Stop and Handoff when no citation can be produced for a required source.
- Secret handling: Store provider, tool name, status, counts, and hashed identifiers only.
- Decision source: docs/agent/agent-architecture.md#Evidence
"""


def _ar_cap_05(
    *,
    consumer: str = "Foundry Agent Service",
    allowlist: str = "knowledge_base_retrieve",
    per_user: str = "not-required: the corpus is tenant wide and no document level ACL is applied",
) -> str:
    return f"""#### 7.0.5 MCP Exposure（AR-CAP-05）
- Status: selected
- Consumer: {consumer}
- Project connection: policy-kb-mcp-connection created with reuse-or-create
- Connection category: RemoteTool
- Auth type: ProjectManagedIdentity
- Tool allowlist: {allowlist}
- Approval mode: never
- Per-user authorization: {per_user}
- Design status: preview
- Checked at: 2026-08-04
- Decision source: docs/agent/agent-architecture.md#Tool-Boundary
"""


def _design(
    *,
    routing: str = _ROUTING_WITH_FOUNDRY_IQ,
    ar_blocks: "str | None" = None,
) -> str:
    if ar_blocks is None:
        ar_blocks = (
            _ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
    return _HEAD + "\n" + routing + "\n" + ar_blocks + "\n" + _CRUD_NA + "\n" + _MCP_NA + "\n" + _SKILL_NOT_REQUIRED


def _validate(text: str, *, agentic_retrieval_policy: str = "auto") -> list:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "agent-detail-AG-01.md"
        path.write_text(text, encoding="utf-8")
        return validate_ai_agent_design_artifact(
            path, agentic_retrieval_policy=agentic_retrieval_policy
        )


def _ar_errors(errors: list) -> list:
    return [e for e in errors if "AR-CAP" in e]


class TestAgenticRetrievalContractGating(unittest.TestCase):
    """AR-CAP 契約の発動条件を検証する。"""

    def test_foundry_iq_route_with_full_contract_passes(self) -> None:
        self.assertEqual(_ar_errors(_validate(_design())), [])

    def test_foundry_iq_route_without_contract_fails(self) -> None:
        errors = _ar_errors(_validate(_design(ar_blocks="")))
        self.assertTrue(errors)
        for contract_id in ("AR-CAP-01", "AR-CAP-02", "AR-CAP-03", "AR-CAP-04", "AR-CAP-05"):
            self.assertTrue(
                any(contract_id in e for e in errors),
                msg=f"{contract_id} の欠落が検出されていない: {errors}",
            )

    def test_non_foundry_route_does_not_require_contract(self) -> None:
        errors = _validate(_design(routing=_ROUTING_WITHOUT_FOUNDRY_IQ, ar_blocks=""))
        self.assertEqual(_ar_errors(errors), [])

    def test_fallback_route_also_triggers_contract(self) -> None:
        routing = _ROUTING_WITHOUT_FOUNDRY_IQ.replace(
            "none: block rather than substitute another source",
            "Azure AI Search Agentic Retrieval knowledge base",
        )
        errors = _ar_errors(_validate(_design(routing=routing, ar_blocks="")))
        self.assertTrue(errors)


class TestAgenticRetrievalConsistencyRules(unittest.TestCase):
    """整合ルール R1〜R12 を検証する。"""

    def test_r1_invalid_reasoning_effort_is_rejected(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(effort="aggressive") + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("Retrieval reasoning effort" in e for e in _ar_errors(_validate(text))))

    def test_r2_minimal_requires_extractive_data(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(effort="minimal", output_mode="answerSynthesis", ks_count="1")
            + "\n" + _ar_cap_02(rows=_KS_ROW_BLOB) + "\n" + _ar_cap_03(llm_budget="0 tokens per request")
            + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("extractiveData" in e for e in _ar_errors(_validate(text))))

    def test_r3_minimal_rejects_web_knowledge_source(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(effort="minimal", output_mode="extractiveData")
            + "\n" + _ar_cap_02() + "\n" + _ar_cap_03(llm_budget="0 tokens per request")
            + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("web" in e.casefold() for e in _ar_errors(_validate(text))))

    def test_r5_more_than_ten_knowledge_sources_is_rejected(self) -> None:
        rows = "".join(
            _KS_ROW_BLOB.replace("policy-docs", f"policy-docs-{index:02d}")
            for index in range(11)
        )
        text = _design(
            ar_blocks=_ar_cap_01(ks_count="11") + "\n" + _ar_cap_02(rows=rows)
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("10" in e for e in _ar_errors(_validate(text))))

    def test_knowledge_source_count_must_match_matrix_rows(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(ks_count="5") + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(
            any("Knowledge source count" in e for e in _ar_errors(_validate(text)))
        )

    def test_r6_low_effort_requires_selection_description(self) -> None:
        row = _KS_ROW_BLOB.replace("| Internal HR and compliance policy documents |", "|  |")
        text = _design(
            ar_blocks=_ar_cap_01(ks_count="1") + "\n" + _ar_cap_02(rows=row)
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(
            any("Selection description" in e for e in _ar_errors(_validate(text)))
        )

    def test_always_query_requires_boolean_with_reason(self) -> None:
        row = _KS_ROW_BLOB.replace(
            "| true: policy answers always need the internal corpus |", "| yes |"
        )
        text = _design(
            ar_blocks=_ar_cap_01(ks_count="1") + "\n" + _ar_cap_02(rows=row)
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("Always query" in e for e in _ar_errors(_validate(text))))

    def test_r7_medium_effort_requires_region_availability(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(effort="medium") + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(
            any("Region availability" in e for e in _ar_errors(_validate(text)))
        )

    def test_r7_medium_effort_with_region_availability_passes(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(
                effort="medium",
                region_line="Japan East is listed as a supported region, confirmed 2026-08-04",
            )
            + "\n" + _ar_cap_02() + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertEqual(_ar_errors(_validate(text)), [])

    def test_r8_unlimited_budget_is_rejected(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03(llm_budget="unlimited") + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("LLM token budget" in e for e in _ar_errors(_validate(text))))

    def test_r9_duplicated_reasoning_effort_is_rejected(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01() + "\n"
            + _ar_cap_02() + "\n"
            + _ar_cap_03(extra="- Retrieval reasoning effort: medium\n")
            + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(
            any("AR-CAP-03" in e and "reasoning effort" in e.casefold() for e in _ar_errors(_validate(text)))
        )

    def test_r10_extra_tool_in_allowlist_is_rejected(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n"
            + _ar_cap_05(allowlist="knowledge_base_retrieve, knowledge_base_admin")
        )
        self.assertTrue(any("allowlist" in e.casefold() for e in _ar_errors(_validate(text))))

    def test_r11_per_user_required_with_foundry_agent_service_is_blocked(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n"
            + _ar_cap_05(
                per_user="required: per user document level ACL must be enforced at query time"
            )
        )
        self.assertTrue(
            any("Per-user authorization" in e for e in _ar_errors(_validate(text)))
        )

    def test_r11_per_user_required_with_other_consumer_is_allowed(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n"
            + _ar_cap_05(
                consumer="Azure OpenAI Responses API",
                per_user="required: per user document level ACL is enforced with a per request header",
            )
        )
        self.assertEqual(_ar_errors(_validate(text)), [])

    def test_r12_invalid_checked_at_is_rejected(self) -> None:
        text = _design(
            ar_blocks=_ar_cap_01(checked_at="2026/08/04") + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(any("Checked at" in e for e in _ar_errors(_validate(text))))

    def test_missing_required_label_is_rejected(self) -> None:
        block = _ar_cap_01().replace(
            "- Retrieval instructions: Prefer internal policy sources and skip web unless a publication date is requested.\n",
            "",
        )
        text = _design(
            ar_blocks=block + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        self.assertTrue(
            any("Retrieval instructions" in e for e in _ar_errors(_validate(text)))
        )

    def test_reasoned_na_for_mcp_exposure_is_accepted(self) -> None:
        na_block = """#### 7.0.5 MCP Exposure（AR-CAP-05）
- Status: N/A
- Reason: The knowledge base is consumed only by this Agent process and is not exposed to other hosts.
- Decision source: docs/agent/agent-architecture.md#Tool-Boundary
- Recheck condition: Re-evaluate when another MCP host must reuse this knowledge base.
"""
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n" + na_block
        )
        self.assertEqual(_ar_errors(_validate(text)), [])

    def test_bare_na_for_mcp_exposure_is_rejected(self) -> None:
        na_block = """#### 7.0.5 MCP Exposure（AR-CAP-05）
- Status: N/A
"""
        text = _design(
            ar_blocks=_ar_cap_01() + "\n" + _ar_cap_02() + "\n" + _ar_cap_03()
            + "\n" + _ar_cap_04() + "\n" + na_block
        )
        self.assertTrue(_ar_errors(_validate(text)))


class TestAgenticRetrievalImplementationGate(unittest.TestCase):
    """AR-CAP-01 / 02 / 05 の設計値が実装へ反映されているかを検証する。"""

    _CONTRACT = {
        "selected": True,
        "knowledge_base_name": "policy-kb",
        "reasoning_effort": "low",
        "knowledge_sources": ["policy-docs", "public-news"],
        "mcp_exposure": {"foundry_agent_service": True, "tools": ["knowledge_base_retrieve"]},
    }
    _CONFIG = {
        "knowledge_base": {
            "name": "policy-kb",
            "retrieval_reasoning_effort": "low",
            "knowledge_sources": ["policy-docs", "public-news"],
        },
        "mcp_servers": [
            {"server_label": "knowledge-base", "tool_allowlist": ["knowledge_base_retrieve"]}
        ],
    }
    _SOURCE = "def retrieve(query):\n    return call_tool('knowledge_base_retrieve', query)\n"

    def test_aligned_implementation_passes(self) -> None:
        self.assertEqual(
            _validate_agentic_retrieval_implementation(
                dict(self._CONTRACT), json.loads(json.dumps(self._CONFIG)), self._SOURCE
            ),
            [],
        )

    def test_missing_knowledge_base_name_in_configuration_fails(self) -> None:
        config = json.loads(json.dumps(self._CONFIG))
        config["knowledge_base"]["name"] = "other-kb"
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), config, self._SOURCE
        )
        self.assertTrue(any("knowledge base name missing" in e for e in errors))

    def test_extra_mcp_tool_in_configuration_fails(self) -> None:
        """Foundry Agent Service は knowledge_base_retrieve 以外を解決できない。

        設計時（R10）は許可外ツールを拒否していたが実装時は素通りしていたため、
        設計/実装の対称性をここで固定する。
        """
        config = json.loads(json.dumps(self._CONFIG))
        config["mcp_servers"][0]["tool_allowlist"] = [
            "knowledge_base_retrieve",
            "list_indexes",
        ]
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), config, self._SOURCE
        )
        self.assertTrue(
            any("supports only knowledge_base_retrieve" in e for e in errors),
            f"許可外ツールが拒否されない: {errors}",
        )
        self.assertTrue(any("list_indexes" in e for e in errors))

    def test_allowlist_with_only_the_supported_tool_passes(self) -> None:
        """陰性対照: 許可ツールのみなら追加エラーを出さない。"""
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), json.loads(json.dumps(self._CONFIG)), self._SOURCE
        )
        self.assertEqual([e for e in errors if "supports only" in e], [])

    def test_reasoning_effort_mismatch_fails(self) -> None:
        config = json.loads(json.dumps(self._CONFIG))
        config["knowledge_base"]["retrieval_reasoning_effort"] = "medium"
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), config, self._SOURCE
        )
        self.assertTrue(any("retrieval_reasoning_effort" in e for e in errors))

    def test_missing_knowledge_source_in_configuration_fails(self) -> None:
        config = json.loads(json.dumps(self._CONFIG))
        config["knowledge_base"]["knowledge_sources"] = ["policy-docs"]
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), config, self._SOURCE
        )
        self.assertTrue(any("public-news" in e for e in errors))

    def test_missing_knowledge_base_retrieve_tool_fails(self) -> None:
        config = json.loads(json.dumps(self._CONFIG))
        config["mcp_servers"][0]["tool_allowlist"] = ["get_schema"]
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT), config, self._SOURCE
        )
        self.assertTrue(any("knowledge_base_retrieve" in e for e in errors))

    def test_source_without_knowledge_base_retrieve_fails(self) -> None:
        errors = _validate_agentic_retrieval_implementation(
            dict(self._CONTRACT),
            json.loads(json.dumps(self._CONFIG)),
            "def retrieve(query):\n    return None\n",
        )
        self.assertTrue(any("source does not reference" in e for e in errors))

    def test_non_foundry_consumer_skips_tool_allowlist_check(self) -> None:
        contract = dict(self._CONTRACT)
        contract["mcp_exposure"] = {"foundry_agent_service": False, "tools": []}
        errors = _validate_agentic_retrieval_implementation(
            contract,
            json.loads(json.dumps(self._CONFIG)),
            "def retrieve(query):\n    return None\n",
        )
        self.assertEqual(errors, [])

    def test_design_metadata_marks_agentic_retrieval_selected(self) -> None:
        from hve.artifact_validation import _parse_ai_agent_design

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent-detail-AG-01.md"
            path.write_text(_design(), encoding="utf-8")
            _, metadata = _parse_ai_agent_design(path)
        contract = metadata.get("agentic_retrieval") or {}
        self.assertTrue(contract.get("selected"))
        self.assertEqual(contract.get("knowledge_base_name"), "policy-kb")
        self.assertEqual(contract.get("reasoning_effort"), "low")
        self.assertEqual(contract.get("knowledge_sources"), ["policy-docs", "public-news"])

    def test_design_metadata_absent_without_agentic_route(self) -> None:
        from hve.artifact_validation import _parse_ai_agent_design

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent-detail-AG-01.md"
            path.write_text(
                _design(routing=_ROUTING_WITHOUT_FOUNDRY_IQ, ar_blocks=""),
                encoding="utf-8",
            )
            _, metadata = _parse_ai_agent_design(path)
        self.assertIsNone(metadata.get("agentic_retrieval"))


class TestKnowledgeSourceLowerBound(unittest.TestCase):
    """FR-WF-AAG-04: 1 行の Knowledge Base は横断検索の前提を満たさない。"""

    def test_two_knowledge_sources_pass(self) -> None:
        self.assertEqual(_ar_errors(_validate(_design())), [])

    def test_single_knowledge_source_is_rejected(self) -> None:
        blocks = (
            _ar_cap_01(ks_count="1") + "\n" + _ar_cap_02(rows=_KS_ROW_BLOB)
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        errors = _ar_errors(_validate(_design(ar_blocks=blocks)))
        self.assertTrue(
            any("AR-CAP-02" in error and "at least" in error.lower() for error in errors),
            errors,
        )


class TestIndexSemanticConfiguration(unittest.TestCase):
    """FR-WF-AAG-04: 索引側の semantic configuration が検索品質の上限を決める。"""

    def test_missing_index_configuration_is_rejected(self) -> None:
        blocks = (
            _ar_cap_01(index_config=None) + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        errors = _ar_errors(_validate(_design(ar_blocks=blocks)))
        self.assertTrue(
            any("Index semantic configuration" in error for error in errors), errors
        )

    def test_bare_tbd_index_configuration_is_rejected(self) -> None:
        blocks = (
            _ar_cap_01(index_config="TBD") + "\n" + _ar_cap_02()
            + "\n" + _ar_cap_03() + "\n" + _ar_cap_04() + "\n" + _ar_cap_05()
        )
        errors = _ar_errors(_validate(_design(ar_blocks=blocks)))
        self.assertTrue(
            any("Index semantic configuration" in error for error in errors), errors
        )


class TestAgenticRetrievalPolicyGating(unittest.TestCase):
    """FR-WF-AAG-04: 方針 `yes` / `no` を設計成果物側で検証する。"""

    def test_auto_does_not_force_a_route(self) -> None:
        design = _design(routing=_ROUTING_WITHOUT_FOUNDRY_IQ, ar_blocks="")
        self.assertEqual(
            _ar_errors(_validate(design, agentic_retrieval_policy="auto")), []
        )

    def test_yes_requires_foundry_iq_for_enterprise_unstructured(self) -> None:
        routing = _ROUTING_WITH_FOUNDRY_IQ.replace(
            "Foundry IQ knowledge base", "internal-policy-search"
        )
        errors = _validate(
            _design(routing=routing, ar_blocks=""), agentic_retrieval_policy="yes"
        )
        self.assertTrue(
            any("AR-CAP" in error and "yes" in error for error in errors), errors
        )

    def test_yes_without_enterprise_unstructured_is_not_forced(self) -> None:
        design = _design(routing=_ROUTING_WITHOUT_FOUNDRY_IQ, ar_blocks="")
        self.assertEqual(
            _ar_errors(_validate(design, agentic_retrieval_policy="yes")), []
        )

    def test_yes_with_the_selected_route_passes(self) -> None:
        self.assertEqual(
            _ar_errors(_validate(_design(), agentic_retrieval_policy="yes")), []
        )

    def test_no_forbids_the_foundry_iq_route(self) -> None:
        errors = _validate(_design(), agentic_retrieval_policy="no")
        self.assertTrue(
            any("AR-CAP" in error and "no" in error for error in errors), errors
        )

    def test_unknown_policy_is_fail_closed(self) -> None:
        errors = _validate(_design(), agentic_retrieval_policy="ON")
        self.assertTrue(
            any("agentic retrieval policy" in error.lower() for error in errors), errors
        )


if __name__ == "__main__":
    unittest.main()
