"""FR-TS-13: SDK resource classification policy の RED 契約テスト。"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from hve.toolsearch import policy as policy_module
from hve.toolsearch.policy import PolicyError, ToolSearchPolicy
from hve.workflow_registry import list_workflows


_CLASSIFICATIONS = {"knowledge", "software-engineering", "both", "unclassified"}
_SOFTWARE_ENGINEERING_WORKFLOWS = {
    "aas",
    "ada",
    "aad-web",
    "asdw-web",
    "adfd",
    "adfdv",
    "aag",
    "aagd",
    "aar",
    "adoc",
}


def _raw_policy() -> dict:
    return {
        "version": 1,
        "limit": 5,
        "max_limit": 10,
        "tau": 0.4,
        "field_weights": {
            "name": 3.0,
            "additional_search_text": 2.5,
            "description": 2.0,
            "arg_terms": 1.0,
        },
        "pins": {},
        "additional_search_text": {},
        "step_overrides": {},
        "resource_classifications": {
            "plugins": {
                "docs-plugin": "knowledge",
                "engineering-plugin": "software-engineering",
                "shared-plugin": "both",
                "uncategorized-plugin": "unclassified",
            },
            "mcp_servers": {
                "docs": "knowledge",
                "build": "software-engineering",
                "shared": "both",
                "explicit-unknown": "unclassified",
            },
            "skills": {
                "answer-docs": "knowledge",
                "write-code": "software-engineering",
                "review": "both",
                "explicit-unknown": "unclassified",
            },
        },
        "knowledge_tool_allowlists": {
            "docs": ["search", "read_document"],
            "shared": ["lookup"],
        },
        "software_engineering_tool_allowlists": {
            "build": ["compile", "test"],
            "shared": ["inspect_code"],
        },
        "required_mcp_servers_by_skill": {
            "answer-docs": ["docs"],
        },
    }


def _policy(**overrides) -> ToolSearchPolicy:
    raw = _raw_policy()
    raw.update(overrides)
    return ToolSearchPolicy.from_dict(raw)


def _workflow_ids() -> set[str]:
    values = list_workflows()
    return {
        str(getattr(item, "id", getattr(item, "workflow_id", item)))
        for item in values
    }


def test_policy_accepts_exactly_the_four_resource_classifications() -> None:
    policy = _policy()

    expected = {
        "docs-plugin": "knowledge",
        "engineering-plugin": "software-engineering",
        "shared-plugin": "both",
        "uncategorized-plugin": "unclassified",
    }
    assert set(expected.values()) == _CLASSIFICATIONS
    for name, classification in expected.items():
        assert policy.classification_for("plugins", name) == classification


@pytest.mark.parametrize("invalid", ["", "engineering", "read-only", "BOTH", None, 1])
def test_policy_rejects_unknown_or_non_string_classification_values(invalid: object) -> None:
    raw = _raw_policy()
    raw["resource_classifications"]["mcp_servers"]["docs"] = invalid

    with pytest.raises(PolicyError, match="classification"):
        ToolSearchPolicy.from_dict(raw)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("resource_classifications", []),
        ("resource_classifications", {"plugins": {}, "mcp_servers": {}}),
        ("resource_classifications", {"plugins": {}, "mcp_servers": {}, "skills": {}, "tools": {}}),
        ("knowledge_tool_allowlists", []),
        ("software_engineering_tool_allowlists", "compile"),
    ],
)
def test_policy_rejects_malformed_resource_tables(field: str, invalid: object) -> None:
    raw = _raw_policy()
    raw[field] = invalid

    with pytest.raises(PolicyError):
        ToolSearchPolicy.from_dict(raw)


@pytest.mark.parametrize("kind", ["plugins", "mcp_servers", "skills"])
@pytest.mark.parametrize("invalid_name", ["", "   ", "*", 1])
def test_policy_rejects_invalid_exact_resource_names(
    kind: str,
    invalid_name: object,
) -> None:
    raw = _raw_policy()
    raw["resource_classifications"][kind] = {invalid_name: "knowledge"}

    with pytest.raises(PolicyError, match="name"):
        ToolSearchPolicy.from_dict(raw)


@pytest.mark.parametrize(
    "missing",
    [
        "resource_classifications",
        "knowledge_tool_allowlists",
        "software_engineering_tool_allowlists",
    ],
)
def test_policy_requires_every_resource_routing_table(missing: str) -> None:
    raw = _raw_policy()
    del raw[missing]

    with pytest.raises(PolicyError, match=missing):
        ToolSearchPolicy.from_dict(raw)


def test_exact_resource_classification_beats_owner_plugin_then_defaults_unclassified() -> None:
    policy = _policy(
        resource_classifications={
            "plugins": {"docs-plugin": "knowledge"},
            "mcp_servers": {"shared": "software-engineering"},
            "skills": {},
        }
    )

    assert policy.classification_for(
        "mcp_servers", "shared", owner_plugin="docs-plugin"
    ) == "software-engineering"
    assert policy.classification_for(
        "mcp_servers", "plugin-owned", owner_plugin="docs-plugin"
    ) == "knowledge"
    assert policy.classification_for(
        "skills", "plugin-skill", owner_plugin="docs-plugin"
    ) == "knowledge"
    assert policy.classification_for(
        "skills", "owner-not-confirmed", owner_plugin=None
    ) == "unclassified"
    assert policy.classification_for(
        "mcp_servers", "unknown", owner_plugin="unknown-plugin"
    ) == "unclassified"


def test_classification_lookup_rejects_unknown_kind_instead_of_guessing() -> None:
    policy = _policy()

    with pytest.raises(PolicyError, match="resource kind"):
        policy.classification_for("tools", "search")


def test_knowledge_and_software_engineering_allowlists_are_separate_exact_bare_names() -> None:
    policy = _policy()

    assert set(policy.tool_allowlist_for("knowledge", "docs")) == {
        "search",
        "read_document",
    }
    assert set(policy.tool_allowlist_for("knowledge", "shared")) == {"lookup"}
    assert set(policy.tool_allowlist_for("software-engineering", "shared")) == {
        "inspect_code"
    }
    assert set(policy.tool_allowlist_for("software-engineering", "docs")) == set()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("knowledge_tool_allowlists", {"docs": "search"}),
        ("knowledge_tool_allowlists", {"docs": [""]}),
        ("knowledge_tool_allowlists", {"docs": ["*"]}),
        ("knowledge_tool_allowlists", {"docs": ["mcp:docs-search"]}),
        ("knowledge_tool_allowlists", {"docs": ["search", "search"]}),
        ("software_engineering_tool_allowlists", {"build": [1]}),
        ("software_engineering_tool_allowlists", {"": ["compile"]}),
    ],
)
def test_invalid_tool_allowlist_schema_fails_closed(field: str, value: object) -> None:
    raw = _raw_policy()
    raw[field] = value

    with pytest.raises(PolicyError, match="allowlist"):
        ToolSearchPolicy.from_dict(raw)


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"": ["docs"]},
        {"answer-docs": "docs"},
        {"answer-docs": []},
        {"answer-docs": ["docs", "docs"]},
        {"answer-docs": ["*"]},
        {"answer-docs": [1]},
    ],
)
def test_required_mcp_servers_by_skill_rejects_non_exact_or_empty_values(
    value: object,
) -> None:
    raw = _raw_policy()
    raw["required_mcp_servers_by_skill"] = value

    with pytest.raises(PolicyError, match="required_mcp_servers_by_skill"):
        ToolSearchPolicy.from_dict(raw)


def test_required_mcp_servers_by_skill_resolves_exact_names_in_declaration_order() -> None:
    policy = _policy(
        required_mcp_servers_by_skill={
            "answer-docs": ["tenant-docs", "shared"],
            "review": ["shared", "tenant-review"],
        }
    )

    assert policy.required_mcp_servers_for_skills(
        ["answer-docs", "review", "answer-docs"]
    ) == ("tenant-docs", "shared", "tenant-review")


def test_mcp_dependent_required_skill_without_mapping_fails_closed() -> None:
    policy = _policy(required_mcp_servers_by_skill={})

    with pytest.raises(PolicyError, match="microsoft-foundry"):
        policy.required_mcp_servers_for_skills(["microsoft-foundry"])


def test_workflow_sets_match_registry_and_required_categories() -> None:
    registry = _workflow_ids()

    assert len(registry) == 13
    assert set(policy_module.KNOWLEDGE_WORKFLOW_IDS) == registry
    assert set(policy_module.SOFTWARE_ENGINEERING_WORKFLOW_IDS) == _SOFTWARE_ENGINEERING_WORKFLOWS
    assert set(policy_module.SOFTWARE_ENGINEERING_WORKFLOW_IDS) <= registry


@pytest.mark.parametrize("workflow_id", sorted(_SOFTWARE_ENGINEERING_WORKFLOWS))
def test_software_engineering_classification_is_allowed_only_for_declared_workflows(
    workflow_id: str,
) -> None:
    policy = _policy()

    assert policy.classification_allowed(workflow_id, "software-engineering") is True
    assert policy.classification_allowed(workflow_id, "both") is True


def test_knowledge_is_allowed_for_every_registered_workflow_and_unclassified_is_not() -> None:
    policy = _policy()

    for workflow_id in _workflow_ids():
        assert policy.classification_allowed(workflow_id, "knowledge") is True
        assert policy.classification_allowed(workflow_id, "both") is True
        assert policy.classification_allowed(workflow_id, "unclassified") is False


def test_non_software_workflow_does_not_receive_software_engineering_resources() -> None:
    policy = _policy()
    knowledge_only = _workflow_ids() - _SOFTWARE_ENGINEERING_WORKFLOWS
    assert knowledge_only

    for workflow_id in knowledge_only:
        assert policy.classification_allowed(workflow_id, "software-engineering") is False


def test_unknown_workflow_fails_closed() -> None:
    policy = _policy()

    with pytest.raises(PolicyError, match="workflow"):
        policy.classification_allowed("not-in-registry", "knowledge")


def test_resource_routing_metadata_round_trips_without_loss() -> None:
    raw = _raw_policy()
    raw["future_top_level"] = {
        "mode": "preserve-verbatim",
        "nested": {"enabled": True},
    }
    policy = ToolSearchPolicy.from_dict(deepcopy(raw))

    serialized = policy.to_dict()
    assert serialized["resource_classifications"] == raw["resource_classifications"]
    assert serialized["knowledge_tool_allowlists"] == raw["knowledge_tool_allowlists"]
    assert (
        serialized["software_engineering_tool_allowlists"]
        == raw["software_engineering_tool_allowlists"]
    )
    assert (
        serialized["required_mcp_servers_by_skill"]
        == raw["required_mcp_servers_by_skill"]
    )
    assert serialized["future_top_level"] == raw["future_top_level"]
    assert ToolSearchPolicy.from_dict(serialized) == policy


def test_bundled_policy_routes_workiq_with_read_only_allowlist() -> None:
    """FR-KD-02: 既定の workiq 許可リストは読み取り系 6 件だけで、変更系を含まない。"""
    policy = ToolSearchPolicy.load()

    assert policy.classification_for("mcp_servers", "workiq") == "knowledge"
    allowlist = policy.tool_allowlist_for("knowledge", "workiq")
    assert set(allowlist) == {"retrieve", "ask", "fetch", "search_paths", "get_schema", "list_agents"}
    assert len(allowlist) == 6
    for forbidden in ("create_entity", "update_entity", "delete_entity", "do_action", "call_function", "fetch_blob"):
        assert forbidden not in allowlist


def _bundled_raw() -> dict:
    return json.loads(ToolSearchPolicy.default_path().read_text(encoding="utf-8"))


def test_bundled_policy_routes_required_skill_mcp_dependencies() -> None:
    """FR-TS-13: bundled policy自身がrequired Skillのexact MCP依存を宣言する。"""
    from hve.toolsearch.resource_routing import resolve_resource_route

    policy = ToolSearchPolicy.load()
    required = policy.required_mcp_servers_for_skills(["microsoft-foundry"])
    assert required == ("azure", "microsoft-learn")

    snapshot = _snapshot_with(mcp_servers=list(required), skills=["microsoft-foundry"])
    for workflow_id in sorted(_SOFTWARE_ENGINEERING_WORKFLOWS):
        route = resolve_resource_route(
            snapshot=snapshot,
            policy=policy,
            workflow_id=workflow_id,
            required_skills=["microsoft-foundry"],
        )
        for name in required:
            assert name in route.enabled_mcp_servers, (workflow_id, name)
            assert route.mcp_tool_allowlists[name], (workflow_id, name)


def test_repository_policy_can_replace_required_skill_mcp_server_names(
    tmp_path,
) -> None:
    from hve.toolsearch.resource_routing import resolve_resource_route

    raw = _raw_policy()
    raw["resource_classifications"]["mcp_servers"]["tenant-foundry"] = (
        "software-engineering"
    )
    raw["software_engineering_tool_allowlists"]["tenant-foundry"] = ["inspect"]
    raw["resource_classifications"]["skills"]["microsoft-foundry"] = (
        "software-engineering"
    )
    raw["required_mcp_servers_by_skill"] = {
        "microsoft-foundry": ["tenant-foundry"]
    }
    policy_dir = tmp_path / ".toolsearch"
    policy_dir.mkdir()
    (policy_dir / "policy.json").write_text(
        json.dumps(raw),
        encoding="utf-8",
    )

    policy = ToolSearchPolicy.load(repo_root=tmp_path)
    route = resolve_resource_route(
        snapshot=_snapshot_with(
            mcp_servers=["tenant-foundry"],
            skills=["microsoft-foundry"],
        ),
        policy=policy,
        workflow_id="aagd",
        required_skills=["microsoft-foundry"],
    )

    assert route.required_mcp_servers == ("tenant-foundry",)
    assert route.mcp_tool_allowlists == {"tenant-foundry": ("inspect",)}


def test_bundled_policy_classifies_every_resource_it_pins() -> None:
    """FR-TS-13: `pins` で常時公開を宣言した resource を分類未設定で除外してはならない。"""
    raw = _bundled_raw()
    policy = ToolSearchPolicy.load()

    for key, mode in raw["pins"].items():
        if mode == "never":
            continue
        kind, server, name = key.split(":", 2)
        if kind == "mcp":
            assert policy.classification_for("mcp_servers", server) != "unclassified", key
        elif kind == "skill" and name != "*":
            skill_name = name[len("skill_"):] if name.startswith("skill_") else name
            assert policy.classification_for("skills", skill_name) != "unclassified", key


def _snapshot_with(*, mcp_servers: list[str], skills: list[str] | None = None):
    from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot

    return ResourceSnapshot(
        plugin_state="ready",
        mcp_state="ready",
        skill_state="ready",
        skill_ownership_state="ready",
        plugins=(),
        mcp_servers=tuple(
            ResourceItem(
                kind="mcp_server", name=name, enabled=True, source_kind="user"
            )
            for name in mcp_servers
        ),
        skills=tuple(
            ResourceItem(
                kind="skill", name=name, enabled=True, source_kind="user"
            )
            for name in (skills or [])
        ),
    )
