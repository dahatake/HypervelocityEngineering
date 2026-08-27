"""ASDW-WEB Step 単位 remote CI/CD の prompt/template 契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "prompts" / "steps" / "asdw-web"
_CICD_SKILL = _REPO_ROOT / ".github" / "skills" / "cicd" / "github-actions-cicd"
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_IO_CONTRACTS_DIR = _REPO_ROOT / ".github" / "io-contracts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_asdw_compute_deploy_template_uses_orchestrator_branch() -> None:
    text = _read(_TEMPLATES_DIR / "step-3.4.prompt.md")
    assert "デプロイブランチ: `{branch}`" in text
    assert "Step.3.4 用に作成・push" in text
    assert "gh workflow run ... --ref {branch}" in text
    assert "新規 branch 作成や `gh pr create` は行わない" in text


def test_asdw_ui_deploy_template_uses_orchestrator_branch_not_main() -> None:
    text = _read(_TEMPLATES_DIR / "step-4.3.prompt.md")
    assert "デプロイブランチ: `{branch}`" in text
    assert "デプロイブランチ: `main`" not in text
    assert "Step.4.3 用に作成・push" in text
    assert "gh workflow run ... --ref {branch}" in text
    assert "新規 branch 作成や `gh pr create` は行わない" in text


def test_asdw_remote_cicd_deploy_prompts_define_branch_pr_boundary() -> None:
    for prompt_name, step_id in [
        ("Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md", "Step.3.4"),
        ("Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md", "Step.4.3"),
    ]:
        text = _read(_PROMPTS_DIR / prompt_name)
        assert f"ASDW-WEB {step_id}" in text
        assert "Orchestrator が Step 専用ブランチを作成" in text
        assert "PR 作成・merge・base branch 復帰を担当" in text
        assert "新規 branch 作成・checkout・`gh pr create` を行わず" in text
        assert "`gh workflow run" in text and "--ref <branch>" in text


def test_asdw_remote_cicd_deploy_prompts_restrict_agent_push_target() -> None:
    for prompt_name in [
        "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.prompt.md",
        "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md",
    ]:
        text = _read(_PROMPTS_DIR / prompt_name)
        assert "`git push origin HEAD` を実行しない" in text
        assert "`main` または base branch へ push しない" in text
        assert "`git push origin HEAD:<branch>`" in text


def test_asdw_data_and_addservice_deploy_prompts_are_not_step_scoped_remote_cicd() -> None:
    data_text = _read(_PROMPTS_DIR / "Dev-Microservice-Azure-DataDeploy.prompt.md")
    add_text = _read(_PROMPTS_DIR / "Dev-Microservice-Azure-AddServiceDeploy.prompt.md")
    assert "本 Step.1.3 は Step 単位ブランチ / PR / merge の対象外" in data_text
    assert "本 Step.1.3 では `gh workflow run` を発火しない" in data_text
    assert "本 Step.2.2 は Step 単位ブランチ / PR / merge の対象外" in add_text
    assert "本 Step.2.2 では `gh workflow run` を発火しない" in add_text


def test_github_actions_cicd_skill_documents_hve_step_scoped_boundary() -> None:
    skill_text = _read(_CICD_SKILL / "SKILL.md")
    detail_text = _read(_CICD_SKILL / "references" / "cicd-common-spec.md")
    for text in (skill_text, detail_text):
        assert "HVE" in text and "Step 単位 CI/CD" in text
        assert "Orchestrator" in text
        assert "gh workflow run" in text and "--ref <branch>" in text
        assert "`gh pr create`" in text and "行わない" in text
        assert "merge" in text
        assert "`git push origin HEAD` を実行しない" in text
        assert "`main` または base branch へ push しない" in text
        assert "`git push origin HEAD:<branch>`" in text


def test_asdw_ui_deploy_prompt_uses_existing_default_branch_workflow() -> None:
    text = _read(_PROMPTS_DIR / "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.prompt.md")
    assert "Step.4.3 では SWA workflow を新規作成・更新しない" in text
    assert "default branch に存在する `.github/workflows/azure-static-web-apps-app009.yml`" in text
    assert "workflow が default branch に存在しない場合は deploy へ進まない" in text


def test_asdw_ui_deploy_template_uses_existing_workflow_not_runtime_output() -> None:
    text = _read(_TEMPLATES_DIR / "step-4.3.prompt.md")
    assert "既存 workflow: `.github/workflows/azure-static-web-apps-app009.yml`" in text
    assert "SWA デプロイワークフローを新規作成しない" in text
    assert "Secret `AZURE_STATIC_WEB_APPS_API_TOKEN` 参照" not in text
    assert "`api_location`: `src/app/lib/api/`" not in text


def test_github_actions_cicd_skill_documents_default_branch_workflow_precondition() -> None:
    skill_text = _read(_CICD_SKILL / "SKILL.md")
    detail_text = _read(_CICD_SKILL / "references" / "cicd-common-spec.md")
    for text in (skill_text, detail_text):
        assert "default branch に存在する workflow" in text
        assert "同一 Step 内で新規作成した workflow を dispatch しない" in text


def test_app009_swa_workflow_exists_and_uses_oidc_dynamic_token() -> None:
    text = _read(_WORKFLOWS_DIR / "azure-static-web-apps-app009.yml")
    assert "workflow_dispatch:" in text
    assert "environment: copilot" in text
    assert "azure/login@v2" in text
    assert "az staticwebapp secrets list" in text
    assert "Azure/static-web-apps-deploy@v1" in text
    assert "api_location: ''" in text
    assert "AZURE_STATIC_WEB_APPS_API_TOKEN" not in text


def test_asdw_ui_deploy_io_contract_treats_swa_workflow_as_input() -> None:
    text = _read(
        _IO_CONTRACTS_DIR
        / "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps--asdw-web--4.3.yaml"
    )
    assert "- path: .github/workflows/azure-static-web-apps-app009.yml" in text
    assert "producer: repository" in text
    outputs = text.split("outputs:", 1)[1]
    assert ".github/workflows/azure-static-web-apps-" not in outputs
    assert "- path: work/run/<run-id>/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps/Issue-<識別子>/screen-azure-deploy-work-status.md" in outputs
    assert "- path: work/run/<run-id>/Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps/Issue-<識別子>/ac-verification.md" in outputs