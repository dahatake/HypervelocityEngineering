"""FR-PROMPT-12: Prompt plan の Work IQ capability 縮退契約。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from hve import prompt_execution, workiq
from hve.gui import settings_store
from hve.prompt_request import parse_request


def _settings(**options) -> dict:
    value = settings_store.defaults()
    value["options"].update(options)
    return value


def _request(workflows=None):
    return parse_request(
        {
            "schema_version": 1,
            "goal": "設計を進める",
            "workflows": workflows or [{"workflow_id": "ard"}],
        }
    )


def _capability(state: str):
    return workiq.WorkIQCapability(
        state=state,
        reason_code=state,
        enabled_server_names=("workiq",) if state == "ready" else (),
    )


def _plan(tmp_path, *, request=None, settings=None, capability=None):
    return prompt_execution.build_execution_plan(
        request or _request(),
        settings=settings or _settings(),
        repo_root=tmp_path,
        head_commit="a" * 40,
        workiq_capability=capability or _capability("ready"),
    )


def test_unavailable_saved_workiq_is_removed_from_effective_argv(tmp_path) -> None:
    plan = _plan(
        tmp_path,
        settings=_settings(workiq=True, workiq_prompt_qa="custom"),
        capability=_capability("not-configured"),
    )

    argv = plan.workflows[0].argv
    assert not any(token.startswith("--workiq") for token in argv)
    assert plan.notices == (
        "<!-- workiq-disabled: workflows=ard; reason=not-configured -->",
    )


def test_non_workiq_plan_performs_no_discovery(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **_kwargs: calls.append("static") or _capability("not-configured"),
        raising=False,
    )
    plan = prompt_execution.build_execution_plan(
        _request(),
        settings=_settings(workiq=False),
        repo_root=tmp_path,
        head_commit="a" * 40,
    )

    assert calls == []
    assert plan.notices == ()


def test_requested_plan_performs_one_discovery(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static = _capability("ready")
    calls: list[str] = []

    def fake_probe(**_kwargs):
        calls.append("static")
        return static

    monkeypatch.setattr(workiq, "probe_workiq_plugin_capability", fake_probe, raising=False)
    plan = prompt_execution.build_execution_plan(
        _request(),
        settings=_settings(workiq=True),
        repo_root=tmp_path,
        head_commit="a" * 40,
    )

    assert calls == ["static"]
    assert "--workiq" in plan.workflows[0].argv
    assert plan.notices == ()


def test_prompt_plan_inventory_never_initializes_or_queries_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """FR-PROMPT-03 / 12: inventory は許可し、runtime 接続は dry-run へ持ち込まない。"""
    from hve import __main__ as hve_main
    from hve import copilot_client_factory
    from hve.toolsearch import resource_inventory, resource_routing

    forbidden = Mock(side_effect=AssertionError("Prompt plan must not enter runtime"))
    runtime_mcp = SimpleNamespace(list=forbidden, list_tools=forbidden)
    session = SimpleNamespace(
        rpc=SimpleNamespace(
            plugins=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(plugins=[]))),
            skills=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(skills=[]))),
            mcp=runtime_mcp,
            tools=SimpleNamespace(initialize_and_validate=forbidden),
            options=SimpleNamespace(update=forbidden),
        ),
        disconnect=AsyncMock(),
        send=forbidden,
        send_and_wait=forbidden,
    )
    client = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        create_session=AsyncMock(return_value=session),
        rpc=SimpleNamespace(
            mcp=SimpleNamespace(
                discover=AsyncMock(return_value=SimpleNamespace(servers=[
                    SimpleNamespace(name=name, enabled=True, source="user")
                    for name in ("workiq", "other-mcp")
                ])),
                list=forbidden,
                list_tools=forbidden,
            ),
            plugins=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(plugins=[]))),
            skills=SimpleNamespace(discover=AsyncMock(
                return_value=SimpleNamespace(skills=[], errors=[]),
            )),
        ),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(copilot_client_factory, "create_copilot_client", factory)
    monkeypatch.setattr(resource_inventory, "_CACHE", {})
    monkeypatch.setattr(resource_routing, "apply_resource_route", forbidden)
    from hve import knowledge_discovery
    monkeypatch.setattr(knowledge_discovery, "run_knowledge_discovery", forbidden)
    monkeypatch.setattr(knowledge_discovery, "inspect_runtime_sources", forbidden)
    monkeypatch.setattr(prompt_execution, "_register_durable_execution", forbidden)
    monkeypatch.setattr(prompt_execution, "resolve_head_commit", lambda _root: "a" * 40)
    settings = _settings(workiq=True, sources_workiq=True, sources_qa=True)
    original_settings = deepcopy(settings)
    monkeypatch.setattr(settings_store, "load", lambda: settings)
    monkeypatch.setattr(settings_store, "save", forbidden)
    monkeypatch.chdir(tmp_path)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1,
        "goal": "設計を進める",
        "workflows": [{"workflow_id": "ard"}, {"workflow_id": "akm"}],
    }, ensure_ascii=False), encoding="utf-8")
    request_bytes = request.read_bytes()
    child = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(prompt_execution, "_default_runner", child)

    code = hve_main.main(["prompt", "plan", "--request", str(request)])

    assert code == 0
    assert "plan SHA-256:" in capsys.readouterr().out
    factory.assert_called_once()
    client.start.assert_awaited_once()
    client.rpc.mcp.discover.assert_awaited_once()
    assert client.rpc.mcp.discover.await_args.args[0].working_directory == str(tmp_path)
    client.rpc.plugins.list.assert_awaited_once()
    client.rpc.skills.discover.assert_awaited_once()
    # FR-TS-12 の metadata session は全 MCP を事前に無効化した場合だけ許可する。
    client.create_session.assert_awaited_once_with(
        working_directory=str(tmp_path),
        enable_config_discovery=True,
        request_extensions=False,
        enable_skills=True,
        disabled_mcp_servers=["other-mcp", "workiq"],
    )
    session.rpc.plugins.list.assert_awaited_once()
    session.rpc.skills.list.assert_awaited_once()
    session.disconnect.assert_awaited_once()
    client.stop.assert_awaited_once()
    assert child.call_count == 2
    for call in child.call_args_list:
        assert "--dry-run" in call.args[0]
        assert call.kwargs == {"shell": False, "cwd": str(tmp_path)}
    forbidden.assert_not_called()
    assert settings == original_settings
    assert request.read_bytes() == request_bytes


def test_removed_tenant_environment_does_not_change_discovery_plan(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("WORKIQ_TENANT_ID", "tenant")
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **_kwargs: calls.append("static") or _capability("not-configured"),
    )
    plan = prompt_execution.build_execution_plan(
        _request(),
        settings=_settings(workiq=True),
        repo_root=tmp_path,
        head_commit="a" * 40,
    )

    assert calls == ["static"]
    assert "--workiq" not in plan.workflows[0].argv
    assert plan.notices == (
        "<!-- workiq-disabled: workflows=ard; reason=not-configured -->",
    )


def test_multiple_requested_workflows_share_one_discovery_snapshot(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **kwargs: calls.append(kwargs) or _capability("ready"),
    )

    plan = prompt_execution.build_execution_plan(
        _request([{"workflow_id": "ard"}, {"workflow_id": "akm"}]),
        settings=_settings(
            workiq=True,
            sources_workiq=True,
            sources_qa=True,
            sources_original_docs=False,
        ),
        repo_root=tmp_path,
        head_commit="a" * 40,
    )

    assert len(calls) == 1
    assert all("--workiq" in workflow.argv or "--sources" in workflow.argv for workflow in plan.workflows)


def test_mixed_akm_sources_keep_non_workiq_sources(tmp_path) -> None:
    plan = _plan(
        tmp_path,
        request=_request([{"workflow_id": "akm"}]),
        settings=_settings(
            sources_workiq=True,
            sources_qa=True,
            sources_original_docs=False,
        ),
        capability=_capability("not-configured"),
    )

    argv = list(plan.workflows[0].argv)
    start = argv.index("--sources")
    assert argv[start + 1] == "qa"
    assert plan.notices == (
        "<!-- workiq-disabled: workflows=akm; reason=not-configured -->",
    )


def test_same_reason_workflows_are_aggregated_in_sorted_order(tmp_path) -> None:
    plan = _plan(
        tmp_path,
        request=_request([{"workflow_id": "ard"}, {"workflow_id": "akm"}]),
        settings=_settings(
            workiq=True,
            sources_workiq=True,
            sources_qa=True,
            sources_original_docs=False,
        ),
        capability=_capability("unverified"),
    )

    assert plan.notices == (
        "<!-- workiq-disabled: workflows=akm,ard; reason=unverified -->",
    )


def test_workiq_only_akm_is_rejected_before_a_child_plan(tmp_path) -> None:
    with pytest.raises(prompt_execution.WorkIQSourceUnavailable):
        _plan(
            tmp_path,
            request=_request([{"workflow_id": "akm"}]),
            settings=_settings(
                sources_workiq=True,
                sources_qa=False,
                sources_original_docs=False,
            ),
            capability=_capability("unverified"),
        )


def test_ready_capability_preserves_workiq_argv_and_has_no_notice(tmp_path) -> None:
    plan = _plan(
        tmp_path,
        settings=_settings(workiq=True),
        capability=_capability("ready"),
    )

    assert "--workiq" in plan.workflows[0].argv
    assert plan.notices == ()


def test_comment_is_rendered_once_and_is_not_part_of_canonical_hash(tmp_path) -> None:
    plan = _plan(
        tmp_path,
        settings=_settings(workiq=True),
        capability=_capability("unverified"),
    )

    rendered = prompt_execution.format_plan(plan)
    assert rendered.count("<!-- workiq-disabled:") == 1
    assert "⚠" not in rendered
    canonical = prompt_execution.canonical_plan_json(plan)
    assert "workiq-disabled" not in canonical
    assert "notices" not in json.loads(canonical)


def test_notice_never_contains_capability_config_or_auth_material(tmp_path) -> None:
    capability = workiq.WorkIQCapability(
        state="unverified",
        reason_code="unverified",
        enabled_server_names=("secret-server-name",),
    )
    plan = _plan(tmp_path, settings=_settings(workiq=True), capability=capability)

    rendered = prompt_execution.format_plan(plan)
    assert "secret-server-name" not in rendered


def test_unknown_capability_reason_is_normalized_to_unverified(tmp_path) -> None:
    capability = workiq.WorkIQCapability(
        state="unverified",
        reason_code="internal-secret-reason",
    )

    plan = _plan(tmp_path, settings=_settings(workiq=True), capability=capability)

    assert plan.notices == (
        "<!-- workiq-disabled: workflows=ard; reason=unverified -->",
    )


def test_capability_changes_effective_hash_in_both_directions(tmp_path) -> None:
    ready = _plan(tmp_path, settings=_settings(workiq=True), capability=_capability("ready"))
    unavailable = _plan(
        tmp_path,
        settings=_settings(workiq=True),
        capability=_capability("not-configured"),
    )

    assert ready.sha256 != unavailable.sha256


def test_requirement_declares_one_authoritative_reason_per_plan() -> None:
    requirement = (
        Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
    )
    block = requirement.split("- **FR-PROMPT-12**:", 1)[1].split("### 5.21", 1)[0]

    assert "1計画につき1つのauthoritative discovery snapshot" in block
    assert "複数 reason code" not in block
