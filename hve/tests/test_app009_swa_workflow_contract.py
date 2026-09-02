"""FR-WF-ASDW-04: APP-009 SWA deployment stays manual and fail-closed."""

from __future__ import annotations

from pathlib import Path
import re

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "azure-static-web-apps-app009.yml"
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md"
_PROMPT_MIRROR = _REPO_ROOT / "users-guide" / "prompt-reference" / "copies" / "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md.txt"


def _load_workflow() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _on(data: dict) -> dict:
    return data.get("on") or data[True]


def test_trigger_is_manual_only_with_required_target_inputs() -> None:
    data = _load_workflow()
    triggers = _on(data)
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"resource_group", "static_web_app_name"}
    for definition in inputs.values():
        assert definition["required"] is True
        assert definition["type"] == "string"
        assert "default" not in definition


def test_workflow_uses_only_required_permissions_and_one_deploy_job() -> None:
    data = _load_workflow()
    assert data["permissions"] == {"id-token": "write", "contents": "read"}
    assert set(data["jobs"]) == {"build_and_deploy_job"}
    job = data["jobs"]["build_and_deploy_job"]
    assert job["environment"] == "copilot"
    assert job["env"] == {
        "RESOURCE_GROUP": "${{ inputs.resource_group }}",
        "STATIC_WEB_APP_NAME": "${{ inputs.static_web_app_name }}",
    }


def test_target_is_confirmed_before_token_retrieval_and_deploy() -> None:
    data = _load_workflow()
    steps = data["jobs"]["build_and_deploy_job"]["steps"]
    names = [step.get("name", "") for step in steps]
    validate_index = names.index("Validate deployment target inputs")
    login_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("azure/login@")
    )
    target_index = names.index("Confirm Azure Static Web App target")
    token_index = names.index("Get Azure Static Web Apps deployment token")
    deploy_index = names.index("Build and Deploy")
    assert validate_index < login_index < target_index < token_index < deploy_index
    assert "az staticwebapp show" in steps[target_index]["run"]
    assert "az staticwebapp secrets list" in steps[token_index]["run"]
    assert "::add-mask::${deployment_token}" in steps[token_index]["run"]
    assert str(steps[deploy_index]["uses"]).startswith("Azure/static-web-apps-deploy@")
    assert "repo_token" not in steps[deploy_index]["with"]


def test_hard_coded_target_and_pull_request_paths_are_absent() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "dahatake-membership" not in text
    assert "swa-app009-dahatake-membership" not in text
    assert "close_pull_request_job" not in text
    assert "action: close" not in text


def test_step_prompt_matches_the_manual_workflow_contract() -> None:
    prompt = _PROMPT.read_text(encoding="utf-8")
    assert _PROMPT_MIRROR.read_bytes() == _PROMPT.read_bytes()
    assert "trigger は `workflow_dispatch` だけ" in prompt
    assert "`push` / `pull_request` trigger と PR close job を追加しない" in prompt
    assert '-f resource_group="${RESOURCE_GROUP}"' in prompt
    assert '-f static_web_app_name="${SWA_NAME}"' in prompt
    assert "`az staticwebapp show` で対象確認" in prompt


def test_azure_deploy_actions_are_pinned_to_full_commit_shas() -> None:
    data = _load_workflow()
    steps = data["jobs"]["build_and_deploy_job"]["steps"]
    action_refs = {
        str(step["uses"])
        for step in steps
        if str(step.get("uses", "")).startswith(("azure/login@", "Azure/static-web-apps-deploy@"))
    }
    assert len(action_refs) == 2
    assert all(re.fullmatch(r"(?:azure/login|Azure/static-web-apps-deploy)@[0-9a-f]{40}", ref) for ref in action_refs)
