"""FR-CLI-13/81/91: Work IQ startup policy の入口横断契約。"""

from __future__ import annotations

from argparse import Namespace
import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY

import pytest

from hve import __main__ as hve_main
from hve import workiq
from hve.config import SDKConfig


class _Config(SDKConfig):
    def __init__(self, *, requested: bool = True) -> None:
        super().__init__()
        self.dry_run = False
        self.workiq_enabled = requested
        self.knowledge_sources = ["workiq", "docs-mcp"] if requested else ["docs-mcp"]


def _capability(state: str) -> workiq.WorkIQCapability:
    return workiq.WorkIQCapability(
        state=state,
        reason_code=state,
        enabled_server_names=("workiq",) if state == "ready" else (),
    )


def _run_preflight(
    args: Namespace,
    config: Any,
    params: dict,
    *,
    workflow: str,
) -> bool:
    return hve_main._run_workiq_capability_preflight(
        args,
        config,
        params,
        workflow=workflow,
    )


def _orchestrate_option_strings() -> set[str]:
    parser = hve_main._build_parser()
    subparsers = parser._subparsers._group_actions[0]
    return {
        option
        for action in subparsers.choices["orchestrate"]._actions
        for option in action.option_strings
    }


def test_removed_workiq_cli_surface_is_absent() -> None:
    parser = hve_main._build_parser()
    subcommands = set(parser._subparsers._group_actions[0].choices)

    assert "workiq-doctor" not in subcommands
    assert not hasattr(hve_main, "_cmd_workiq_doctor")
    assert {
        "--workiq-tenant-id",
        "--workiq-request-timeout",
        "--workiq-prompt-review",
        "--workiq-akm-review",
        "--no-workiq-akm-review",
        "--workiq-akm-ingest",
        "--no-workiq-akm-ingest",
        "--workiq-dxx",
        "--workiq-draft",
        "--workiq-draft-output-dir",
        "--workiq-prompt-qa",
        "--workiq-prompt-km",
        "--workiq-per-question-timeout",
    }.isdisjoint(_orchestrate_option_strings())
    assert "--knowledge-source" in _orchestrate_option_strings()


@pytest.mark.parametrize(
    "argv",
    (
        ["workiq-doctor"],
        ["orchestrate", "--workflow", "aas", "--workiq-tenant-id", "tenant"],
        ["orchestrate", "--workflow", "aas", "--workiq-request-timeout", "30"],
        ["orchestrate", "--workflow", "aas", "--workiq-prompt-review", "review"],
    ),
)
def test_removed_workiq_cli_surface_is_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        hve_main._build_parser().parse_args(argv)


@pytest.mark.parametrize(
    ("state", "expected"),
    (("ready", True), ("not-configured", False), ("unverified", False)),
)
def test_wizard_availability_uses_one_sdk_discovery_snapshot(
    state: str,
    expected: bool,
) -> None:
    calls: list[dict[str, Any]] = []
    module = SimpleNamespace(
        probe_workiq_plugin_capability=lambda **kwargs: (
            calls.append(kwargs) or _capability(state)
        ),
        is_workiq_available=lambda: (_ for _ in ()).throw(
            AssertionError("legacy npx availability must not run")
        ),
    )

    assert hve_main._workiq_available_via_sdk_discovery(
        module,
        cli_path="copilot-custom",
        cli_url="tcp://127.0.0.1:4321",
    ) is expected
    assert calls == [
        {
            "cli_path": "copilot-custom",
            "cli_url": "tcp://127.0.0.1:4321",
            "working_directory": ANY,
        }
    ]


def test_akm_wizard_omits_workiq_when_not_configured() -> None:
    console = SimpleNamespace(
        options=[],
        prompts=[],
        prompt_multi_select=lambda prompt, options, **_kwargs: (
            console.prompts.append(prompt)
            or setattr(console, "options", list(options))
            or [0]
        ),
        prompt_input=lambda prompt, default="", **_kwargs: (
            console.prompts.append(prompt) or default
        ),
        prompt_yes_no=lambda prompt, default=False, **_kwargs: (
            console.prompts.append(prompt) or default
        ),
    )

    params = hve_main._prompt_akm_params(
        console,
        False,
        will_create_pr=False,
        workiq_available=False,
    )

    assert "workiq（Microsoft 365 Copilot Work IQ）" not in console.options
    assert "workiq" not in str(params.get("sources") or "")
    assert not any("Work IQ" in prompt for prompt in console.prompts)


def test_dry_run_and_non_workiq_run_skip_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **_kwargs: calls.append("discover"),
    )

    dry_run = _Config()
    dry_run.dry_run = True
    assert _run_preflight(
        Namespace(workflow="ard"), dry_run, {}, workflow="ard"
    ) is True

    not_requested = _Config(requested=False)
    assert _run_preflight(
        Namespace(workflow="ard"), not_requested, {}, workflow="ard"
    ) is True
    assert calls == []


def test_ready_capability_runs_single_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _Config()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **kwargs: calls.append(kwargs) or _capability("ready"),
    )
    assert _run_preflight(
        Namespace(workflow="ard"), config, {}, workflow="ard"
    ) is True
    assert len(calls) == 1
    assert config.workiq_enabled is True


def test_unavailable_disables_workiq_for_this_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _Config()
    params = {"sources": "workiq,qa", "ard_workiq_enabled": True}
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **_kwargs: _capability("not-configured"),
    )

    assert _run_preflight(
        Namespace(workflow="akm"), config, params, workflow="akm"
    ) is True
    assert config.workiq_enabled is False
    assert config.knowledge_sources == ["docs-mcp"]
    assert config.effective_knowledge_sources() == ["docs-mcp"]
    assert params["sources"] == "qa"
    assert params["ard_workiq_enabled"] is False


def test_workiq_only_akm_is_rejected_after_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _Config()
    params = {"sources": "workiq"}
    monkeypatch.setattr(
        workiq,
        "probe_workiq_plugin_capability",
        lambda **_kwargs: _capability("unverified"),
    )

    assert _run_preflight(
        Namespace(workflow="akm"), config, params, workflow="akm"
    ) is False


def test_capability_preflight_contains_no_hve_auth_path() -> None:
    source = inspect.getsource(hve_main._run_workiq_capability_preflight)

    assert "ensure_workiq_plugin_authenticated" not in source
    assert "workiq_login" not in source
    assert "tenant_id" not in source
    assert source.count("probe_workiq_plugin_capability(") == 1
    assert source.count("disable_workiq_for_run(") == 1
