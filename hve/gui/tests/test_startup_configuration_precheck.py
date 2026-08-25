"""FR-CLI-82 / FR-GUI-01 の GUI startup preflight 契約テスト。"""

from __future__ import annotations

import importlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest

from hve.autopilot import precheck_runner
from hve.autopilot.precheck_model import PrecheckCategory
from hve.gui.orchestrate_args import OrchestrateArgs

_PROMPT_FIELDS = {
    "additional_prompt",
    "workiq_prompt_qa",
    "workiq_prompt_km",
    "workiq_prompt_review",
}


@dataclass(frozen=True)
class _StartupIssue:
    category: str
    field_name: str
    message: str
    remediation_hint: str


@dataclass(frozen=True)
class _StartupResult:
    issues: tuple[_StartupIssue, ...] = ()

    def is_ok(self) -> bool:
        return not self.issues


def _patch_shared_validator(
    monkeypatch: pytest.MonkeyPatch,
    validator: Mock,
) -> None:
    """module-level / call-time import のどちらでも共有 validator を遮断する。"""
    try:
        startup_preflight = importlib.import_module("hve.startup_preflight")
    except ModuleNotFoundError:
        startup_preflight = None
    if startup_preflight is not None:
        monkeypatch.setattr(
            startup_preflight,
            "validate_startup_configuration",
            validator,
        )
    monkeypatch.setattr(
        precheck_runner,
        "validate_startup_configuration",
        validator,
        raising=False,
    )


def _forbid_subprocess(*_args, **_kwargs):
    raise AssertionError("GUI startup preflight must not invoke subprocess/network")


def test_uses_shared_local_preflight_and_maps_setting_and_auth_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    validator = Mock(
        return_value=_StartupResult(
            (
                _StartupIssue("setting", "repo", "repo invalid", "set owner/repo"),
                _StartupIssue(
                    "setting",
                    "base_branch",
                    "branch invalid",
                    "set a valid branch",
                ),
                _StartupIssue(
                    "setting",
                    "origin",
                    "origin missing",
                    "configure origin",
                ),
                _StartupIssue("auth", "token", "token missing", "sign in"),
            )
        )
    )
    _patch_shared_validator(monkeypatch, validator)

    result = precheck_runner.run_step1_precheck(
        ["asdw-web"],
        tmp_path,
        steps_by_workflow={"asdw-web": ["3.4"]},
        startup_args_by_workflow={
            "asdw-web": OrchestrateArgs(
                workflow="asdw-web",
                create_pr=True,
                repo="owner/repo",
                branch="release/2026.08",
                repo_root=tmp_path,
            )
        },
    )

    validator.assert_called_once()
    kwargs = validator.call_args.kwargs
    assert kwargs["workflow"].id == "asdw-web"
    assert kwargs["active_steps"] == {"3.4"}
    assert kwargs["create_issues"] is False
    assert kwargs["create_pr"] is True
    assert kwargs["enable_auto_merge"] is False
    assert kwargs["repo"] == "owner/repo"
    assert kwargs["token"] == ""
    assert kwargs["base_branch"] == "release/2026.08"
    assert kwargs["check_remote"] is False
    assert Path(kwargs["repo_root"]) == tmp_path
    assert _PROMPT_FIELDS.isdisjoint(kwargs)

    by_field = {item.field_name: item for item in result.items}
    assert {
        field for field in ("repo", "base_branch", "origin")
        if by_field[field].category is PrecheckCategory.SETTING
    } == {"repo", "base_branch", "origin"}
    assert by_field["token"].category is PrecheckCategory.AUTH
    assert by_field["base_branch"].description == "branch invalid"
    assert by_field["base_branch"].remediation_hint == "set a valid branch"


def test_prompt_free_text_does_not_change_precheck_result_or_validator_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "gui-startup-token")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)

    validator = Mock(return_value=_StartupResult())
    _patch_shared_validator(monkeypatch, validator)

    common = {
        "workflow": "aas",
        "create_pr": True,
        "repo": "owner/repo",
        "branch": "main",
        "repo_root": tmp_path,
    }
    prompt_values = {
        "additional_prompt": "repo=broken branch=invalid",
        "workiq_prompt_qa": "token missing",
        "workiq_prompt_km": "origin must not be inspected here",
        "workiq_prompt_review": "feature..broken",
    }

    baseline = precheck_runner.run_step1_precheck(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["1"]},
        startup_args_by_workflow={"aas": OrchestrateArgs(**common)},
    )
    changed = precheck_runner.run_step1_precheck(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["1"]},
        startup_args_by_workflow={
            "aas": OrchestrateArgs(**common, **prompt_values)
        },
    )

    assert baseline.items == changed.items
    assert validator.call_count == 2
    for call in validator.call_args_list:
        assert _PROMPT_FIELDS.isdisjoint(call.kwargs)
        rendered_call = repr(call)
        for prompt in prompt_values.values():
            assert prompt not in rendered_call
