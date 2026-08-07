"""validate_deploy_ac_verification の単体テスト (T6)。"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import time
from pathlib import Path
from typing import cast

import pytest

from hve.artifact_validation import (
    _DEPLOY_AGENT_REALITY_AC,
    build_provider_inventory_snapshot,
    is_deploy_step,
    validate_asdw_data_verify_script,
    validate_asdw_foundry_deploy_artifacts,
    validate_deploy_ac_verification,
    wave_has_deploy_step,
)
from hve.asdw_data_script_launcher import execute_stage
from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------
def _write_report(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ac-verification.md"
    p.write_text(content, encoding="utf-8")
    return p


def _write_agent_inventory_evidence(
    tmp_path: Path,
    route_rows: dict[str, list[str]],
) -> None:
    categories = (
        "project-connection",
        "rbac-consent",
        "key-vault-reference",
        "package",
        "config-flag",
    )
    before_raw: dict[str, dict[str, list[str]]] = {
        route: {category: [] for category in categories}
        for route in route_rows
    }
    after_raw: dict[str, dict[str, list[str]]] = {
        route: {category: [] for category in categories}
        for route in route_rows
    }
    evidence_routes = {}
    for route, cells in route_rows.items():
        selected = cells[0].upper().startswith("SELECTED")
        changed = []
        if selected:
            after_raw[route]["project-connection"] = [f"{route}-connection"]
            changed = ["project-connection"]
        evidence_routes[route] = {
            "selection": "selected" if selected else "n/a",
            "changed_categories": changed,
            "unexpected_categories": [],
        }

    def write_snapshot(name: str, snapshot: dict[str, object]) -> str:
        path = tmp_path / name
        text = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
        snapshot_bytes = text.encode("utf-8")
        path.write_bytes(snapshot_bytes)
        return hashlib.sha256(snapshot_bytes).hexdigest()

    before_hash = write_snapshot(
        "provider-inventory-before.json",
        build_provider_inventory_snapshot(before_raw),
    )
    after_hash = write_snapshot(
        "provider-inventory-after.json",
        build_provider_inventory_snapshot(after_raw),
    )
    (tmp_path / "provider-inventory-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "secret_values_included": False,
                "before_snapshot": "provider-inventory-before.json",
                "before_sha256": before_hash,
                "after_snapshot": "provider-inventory-after.json",
                "after_sha256": after_hash,
                "routes": evidence_routes,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def _agent_provider_table(
    tmp_path: Path,
    *,
    route_rows: dict[str, list[str]] | None = None,
) -> str:
    routes = (
        "azure-ai-search-foundry-iq",
        "work-iq",
        "fabric-iq",
        "web-iq",
        "foundry-web-search",
        "remote-mcp",
    )
    overrides = route_rows or {}
    lines = [
        "## Provider Pre-flight",
        "",
        "| Route | Status | Decision source | Permission | Data boundary | Smoke evidence | Inventory delta | Secret redaction | Evidence redaction |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows: dict[str, list[str]] = {}
    for route in routes:
        cells = list(overrides.get(
            route,
            [
                f"N/A: {route} is not selected by Section 7.0 / 7.3",
                "docs/agent/agent-detail-key.md#section-7",
                "N/A",
                "N/A",
                "N/A",
                "zero; evidence=provider-inventory-evidence.json",
                "confirmed",
                "confirmed",
            ],
        ))
        if cells[5] in {"zero", "expected-only"}:
            cells[5] += "; evidence=provider-inventory-evidence.json"
        rows[route] = cells
        lines.append(f"| {route} | " + " | ".join(cells) + " |")
    _write_agent_inventory_evidence(tmp_path, rows)
    return "\n".join(lines) + "\n"


def _write_foundry_design(tmp_path: Path, *, adopted: bool = True) -> Path:
    p = tmp_path / "azure-services-additional.md"
    service = "Microsoft Foundry (Foundry Agent Service)" if adopted else "Azure Key Vault"
    p.write_text(f"| AI/LLM | {service} |\n", encoding="utf-8")
    return p


def _write_foundry_artifacts(
    tmp_path: Path, service_script: str, verify_script: str
) -> tuple[Path, Path]:
    services = tmp_path / "services"
    services.mkdir()
    (services / "aiservices.sh").write_text(service_script, encoding="utf-8")
    verify = tmp_path / "verify-additional-resources.sh"
    verify.write_text(verify_script, encoding="utf-8")
    return services, verify


# ---------------------------------------------------------------------------
# ASDW Foundry Project artifact contract
# ---------------------------------------------------------------------------
def test_foundry_artifact_contract_is_noop_when_not_adopted(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path, adopted=False)
    assert validate_asdw_foundry_deploy_artifacts(
        design, tmp_path / "missing-services", tmp_path / "missing-verify.sh"
    ) == []


def test_foundry_artifact_contract_rejects_missing_scripts(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    errors = validate_asdw_foundry_deploy_artifacts(
        design, tmp_path / "missing-services", tmp_path / "missing-verify.sh"
    )
    assert any("service scripts not found" in error for error in errors)
    assert any("verify script not found" in error for error in errors)


def test_foundry_artifact_contract_rejects_comment_only_commands(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services, verify = _write_foundry_artifacts(
        tmp_path,
        "# az cognitiveservices account project show\n"
        "# az cognitiveservices account project create\n"
        "# az cognitiveservices account project show\n",
        "# az cognitiveservices account project show\n",
    )
    errors = validate_asdw_foundry_deploy_artifacts(design, services, verify)
    assert any("show before and after" in error for error in errors)
    assert any("project create" in error for error in errors)
    assert any("verify script must execute project show" in error for error in errors)


def test_foundry_artifact_contract_rejects_legacy_project_cli(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services, verify = _write_foundry_artifacts(
        tmp_path,
        "az ai project show --name old\n"
        "az cognitiveservices account project show --name account -g rg --project-name project\n"
        "az cognitiveservices account project create --name account -g rg --project-name project --location eastus\n"
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
    )
    errors = validate_asdw_foundry_deploy_artifacts(design, services, verify)
    assert any("legacy `az ai project`" in error for error in errors)


def test_foundry_artifact_contract_accepts_valid_multiline_commands(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services, verify = _write_foundry_artifacts(
        tmp_path,
        "az cognitiveservices account project show \\\n"
        "  --name account -g rg --project-name project\n"
        "az cognitiveservices account project create \\\n"
        "  --name account -g rg --project-name project --location eastus\n"
        "az cognitiveservices account project show \\\n"
        "  --name account -g rg --project-name project\n",
        "az cognitiveservices account project show \\\n"
        "  --name account -g rg --project-name project\n",
    )
    assert validate_asdw_foundry_deploy_artifacts(design, services, verify) == []


def test_foundry_artifact_contract_ignores_echo_and_inline_comment_text(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services, verify = _write_foundry_artifacts(
        tmp_path,
        "echo 'az cognitiveservices account project show'\n"
        "echo noop # az cognitiveservices account project create\n",
        "echo 'az cognitiveservices account project show'\n",
    )
    errors = validate_asdw_foundry_deploy_artifacts(design, services, verify)
    assert any("show before and after" in error for error in errors)
    assert any("project create" in error for error in errors)
    assert any("verify script must execute project show" in error for error in errors)


def test_foundry_artifact_contract_accepts_crlf_continuations(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services, verify = _write_foundry_artifacts(
        tmp_path,
        "az cognitiveservices account project show \\\r\n"
        "  --name account -g rg --project-name project\r\n"
        "az cognitiveservices account project create \\\r\n"
        "  --name account -g rg --project-name project --location eastus\r\n"
        "az cognitiveservices account project show \\\r\n"
        "  --name account -g rg --project-name project\r\n",
        "az cognitiveservices account project show \\\r\n"
        "  --name account -g rg --project-name project\r\n",
    )
    assert validate_asdw_foundry_deploy_artifacts(design, services, verify) == []


def test_foundry_artifact_contract_combines_multiple_service_scripts(tmp_path: Path) -> None:
    design = _write_foundry_design(tmp_path)
    services = tmp_path / "services"
    services.mkdir()
    (services / "foundry-account.sh").write_text(
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        encoding="utf-8",
    )
    (services / "foundry-project.sh").write_text(
        "az cognitiveservices account project create --name account -g rg --project-name project --location eastus\n"
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        encoding="utf-8",
    )
    verify = tmp_path / "verify-additional-resources.sh"
    verify.write_text(
        "az cognitiveservices account project show --name account -g rg --project-name project\n",
        encoding="utf-8",
    )
    assert validate_asdw_foundry_deploy_artifacts(design, services, verify) == []


# ---------------------------------------------------------------------------
# is_deploy_step（Deploy Step 判定ユーティリティ）
# ---------------------------------------------------------------------------
def test_is_deploy_step_true_for_known_deploy_agents() -> None:
    """allowlist 辞書のメンバーは Deploy 系と判定される。"""
    for agent in _DEPLOY_AGENT_REALITY_AC:
        assert is_deploy_step(agent) is True


def test_is_deploy_step_false_for_post_deploy_test() -> None:
    """Deploy 後テスト Agent（"Deploy" を含むが辞書外）は非 Deploy。"""
    assert is_deploy_step("Dev-Microservice-Azure-ComputePostDeployTest") is False


def test_is_deploy_step_false_for_non_deploy_agent() -> None:
    """非 Deploy Agent（コーディング/テスト）は False。"""
    assert is_deploy_step("Dev-Microservice-Azure-DataTestCoding") is False


def test_is_deploy_step_false_for_none() -> None:
    """コンテナ等 custom_agent=None は False。"""
    assert is_deploy_step(None) is False


def test_is_deploy_step_true_when_reality_gate_acs_declared() -> None:
    """reality_gate_acs 宣言があれば辞書外 Agent でも Deploy 系。"""
    assert is_deploy_step("Some-Custom-Deploy", ["AC-1"]) is True


def test_is_deploy_step_false_when_reality_gate_acs_empty_and_outside() -> None:
    """reality_gate_acs 空 + 辞書外は False。"""
    assert is_deploy_step("Some-Custom-Deploy", []) is False


# ---------------------------------------------------------------------------
# wave_has_deploy_step（Deploy 境界判定）
# ---------------------------------------------------------------------------
def _step_like(custom_agent, reality_gate_acs=None):
    from types import SimpleNamespace

    return SimpleNamespace(custom_agent=custom_agent, reality_gate_acs=reality_gate_acs)


def test_wave_has_deploy_step_true_when_deploy_present() -> None:
    """wave に Deploy Step が 1 つでもあれば True。"""
    steps = [
        _step_like("Dev-Microservice-Azure-DataTestCoding"),
        _step_like("Dev-Microservice-Azure-DataDeploy"),
    ]
    assert wave_has_deploy_step(steps) is True


def test_wave_has_deploy_step_false_when_no_deploy() -> None:
    """非 Deploy のみの wave は False。"""
    steps = [
        _step_like("Dev-Microservice-Azure-DataDesign"),
        _step_like("Dev-Microservice-Azure-DataTestCoding"),
    ]
    assert wave_has_deploy_step(steps) is False


def test_wave_has_deploy_step_empty() -> None:
    """空 wave は False。"""
    assert wave_has_deploy_step([]) is False


def test_wave_has_deploy_step_reality_gate_declared() -> None:
    """reality_gate_acs 宣言を持つ Step も Deploy 扱い。"""
    steps = [_step_like("Some-Custom-Agent", ["AC-1"])]
    assert wave_has_deploy_step(steps) is True


# ---------------------------------------------------------------------------
# 構造系
# ---------------------------------------------------------------------------
def test_allowlist_outside_agent_returns_empty(tmp_path: Path) -> None:
    """allowlist 外 Agent は report の中身に関係なく空 list（既存挙動不変）。"""
    p = _write_report(tmp_path, "| AC-1 | dummy | ❌ | none |\n")
    assert validate_deploy_ac_verification(p, "SomeOtherAgent") == []


def test_report_not_found_returns_error(tmp_path: Path) -> None:
    """report 不在は明示エラー 1 件を返す。"""
    missing = tmp_path / "missing.md"
    errs = validate_deploy_ac_verification(
        missing, "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
    )
    assert len(errs) == 1
    assert "not found" in errs[0]


def test_runner_deploy_ac_gate_does_not_read_legacy_work_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """run スコープ外の legacy work/ は Deploy AC gate の探索対象にしない。"""
    agent = "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
    run_root = tmp_path / "work" / "run" / "run-1"
    legacy_report = tmp_path / "work" / agent / "Issue-step-1" / "ac-verification.md"
    legacy_report.parent.mkdir(parents=True, exist_ok=True)
    legacy_report.write_text(
        "| AC-3 | リソース存在 | ✅ | ok |\n"
        "| AC-9 | smoke | ✅ | ok |\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_deploy_ac_gate("1", agent)

    assert len(errs) == 1
    assert "not found" in errs[0]
    assert str(run_root) in errs[0]


def test_runner_deploy_ac_gate_reads_run_scoped_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """run スコープ配下の ac-verification.md は Deploy AC gate で検証される。"""
    agent = "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
    report = tmp_path / "work" / "run" / "run-1" / agent / "Issue-step-1" / "ac-verification.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "| AC-3 | リソース存在 | ✅ | ok |\n"
        "| AC-9 | smoke | ✅ | ok |\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work" / "run" / "run-1"))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    assert runner._run_deploy_ac_gate("1", agent) == []


def test_runner_deploy_ac_gate_not_found_message_includes_search_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """ac-verification.md がどこにも無い場合、診断メッセージに探索経路と
    既存 Issue-* ディレクトリを含める（規約パス Issue-step-<id> だけを示して
    「Agent がそこに書いた」と誤解させない）。実 run の Issue-0 ドリフト再現。
    """
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    # Agent は Issue-0/ に plan.md を作ったが ac-verification.md は未作成、という実バグ状況
    issue0 = run_root / agent / "Issue-0"
    issue0.mkdir(parents=True, exist_ok=True)
    (issue0 / "plan.md").write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_deploy_ac_gate("1.3", agent)

    assert len(errs) == 1
    msg = errs[0]
    assert "not found" in msg
    # 規約パス（Issue-step-1-3）と glob フォールバックの双方を探索した事実を提示
    assert "Issue-step-1-3" in msg
    assert "Issue-*/ac-verification.md" in msg
    # 既存の Issue-0 を提示して「規約パスに書いた」という誤解を防ぐ
    assert "Issue-0" in msg
    # Issue-* 存在時は出力先ドリフトを疑う actionable hint を提示
    assert "出力先パスのドリフト" in msg
    assert "AC-1 を ❌" in msg


def test_runner_deploy_ac_gate_no_issue_dir_message_includes_drift_hint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Issue-* ディレクトリが皆無（成果物丸ごと未生成）の場合、診断メッセージに
    「Agent が成果物未生成のままターン終了／脱線」を疑う actionable hint を含める。
    実 run の AddServiceDeploy 停止（no Issue-* dirs）を再現。
    """
    agent = "Dev-Microservice-Azure-AddServiceDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    # agent work root だけ作り、Issue-* は一切作らない
    (run_root / agent).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_deploy_ac_gate("2.2", agent)

    assert len(errs) == 1
    msg = errs[0]
    assert "not found" in msg
    assert "agent work root exists but no Issue-* dirs under it" in msg
    # 成果物未生成のままターン終了／脱線を疑う actionable hint
    assert "ターンを終えた可能性" in msg
    assert "AC-1 を ❌" in msg
    assert "console-log を確認" in msg
    assert "Word/docx/chart" in msg
    assert "$null" in msg


def test_runner_deploy_ac_gate_missing_agent_root_message_is_explicit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """agent work root 自体が無い場合は Issue-* 不在と区別して診断する。"""
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    run_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_deploy_ac_gate("1.3", agent)

    assert len(errs) == 1
    assert "agent work root does not exist" in errs[0]


def test_runner_asdw_data_verify_contract_gate_rejects_stale_script(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """DataTestCoding Step.1.2 の post-run gate は stale verify-data-resources.sh を fail にする。"""
    script = tmp_path / "src" / "infra" / "azure" / "verify-data-resources.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query 'provisioningState' -o tsv
echo "provisioningState=Succeeded"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_asdw_data_verify_contract_gate(
        "1.2", "Dev-Microservice-Azure-DataTestCoding"
    )

    assert errs
    assert any("verify-data-resources.sh contract failed" in e for e in errs)


def test_runner_asdw_data_verify_contract_gate_rejects_stale_input_for_data_deploy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """DataDeploy Step.1.3 は再利用された stale verify-data-resources.sh を fail にする。"""
    script = tmp_path / "src" / "infra" / "azure" / "verify-data-resources.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
  --restart-policy Never \
  --command-line "sh -c 'PGPASSWORD=$PG_TOKEN psql -h $PG_HOST -U $PG_ADMIN_USER -d $PG_DB_NAME'"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )
    sample_data = tmp_path / "src" / "data" / "sample-data.json"
    sample_data.parent.mkdir(parents=True, exist_ok=True)
    sample_data.write_text('{"entities": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_asdw_data_verify_contract_gate(
        "1.3", "Dev-Microservice-Azure-DataDeploy"
    )

    assert errs
    assert any("input verify-data-resources.sh contract failed" in e for e in errs)
    assert any("--os-type Linux" in e for e in errs)


def test_runner_data_deploy_gate_passes_same_design_path_to_both_validators(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Step 1.3 post gate must use one canonical design path for both artifacts."""
    calls: list[tuple[str, Path, Path]] = []

    def fake_verify(path, *, design_doc_path, private_capability_required, sample_data_path):
        calls.append(("verify", Path(path), Path(design_doc_path)))
        assert private_capability_required is True
        assert sample_data_path == tmp_path / "src" / "data" / "sample-data.json"
        return []

    def fake_registration(path, *, design_doc_path):
        calls.append(("registration", Path(path), Path(design_doc_path)))
        return []

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_verify_script", fake_verify
    )
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration,
    )
    sample_data = tmp_path / "src" / "data" / "sample-data.json"
    sample_data.parent.mkdir(parents=True)
    sample_data.write_text('{"entities": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    assert runner._run_asdw_data_verify_contract_gate(
        "1.3",
        "Dev-Microservice-Azure-DataDeploy",
    ) == []

    design = tmp_path / "docs" / "azure" / "azure-services-data.md"
    assert calls == [
        (
            "verify",
            tmp_path / "src" / "infra" / "azure" / "verify-data-resources.sh",
            design,
        ),
        (
            "registration",
            tmp_path / "src" / "data" / "azure" / "data-registration-script.sh",
            design,
        ),
    ]

    calls.clear()
    assert runner._run_asdw_data_verify_contract_gate(
        "1.3",
        "Dev-Microservice-Azure-DataDeploy",
        include_registration=False,
    ) == []
    assert calls == [
        (
            "verify",
            tmp_path / "src" / "infra" / "azure" / "verify-data-resources.sh",
            design,
        )
    ]


def test_runner_data_deploy_producer_gate_validates_prep_create_and_registration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Step 1.3 must reject a stale registration producer before Azure launch."""
    calls: list[tuple[str, Path, Path]] = []

    def fake_create(prep, create, *, design_doc_path, sample_data_path):
        calls.append(("create", Path(prep), Path(design_doc_path)))
        assert Path(create) == tmp_path / "src/infra/azure/create-azure-data-resources.sh"
        assert sample_data_path == tmp_path / "src/data/sample-data.json"
        return []

    def fake_registration(path, *, design_doc_path):
        calls.append(("registration", Path(path), Path(design_doc_path)))
        return ["marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_create_scripts",
        fake_create,
    )
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration,
    )
    monkeypatch.chdir(tmp_path)
    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errors = runner._run_asdw_data_producer_contract_gate(
        "1.3",
        "Dev-Microservice-Azure-DataDeploy",
    )

    design = tmp_path / "docs/azure/azure-services-data.md"
    assert calls == [
        (
            "create",
            tmp_path / "src/infra/azure/create-azure-data-resources-prep.sh",
            design,
        ),
        (
            "registration",
            tmp_path / "src/data/azure/data-registration-script.sh",
            design,
        ),
    ]
    assert errors == [
        "[Dev-Microservice-Azure-DataDeploy] "
        "generated data-registration-script.sh contract failed: marker missing"
    ]


# ---------------------------------------------------------------------------
# T-β1: post-main producer gate は session 開始後に再生成された script のみ検査
#   （stale な commit 済みスクリプトで真因をマスクしない。memo §20）
# ---------------------------------------------------------------------------
_DATA_DEPLOY_AGENT = "Dev-Microservice-Azure-DataDeploy"


def _write_producer_script(tmp_path: Path, rel: str, mtime: float) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/usr/bin/env bash\necho stale\n", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_producer_script_freshness_helper(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    session_start = time.time()
    rel = "src/data/azure/data-registration-script.sh"

    # session_start=None → 常に検査対象（pre-execution security gate）
    assert runner._asdw_producer_script_is_session_output(rel, None) is True
    # 未存在 → session 出力ではない（skip）
    assert runner._asdw_producer_script_is_session_output(rel, session_start) is False
    # stale (mtime < start) → skip
    _write_producer_script(tmp_path, rel, session_start - 3600)
    assert runner._asdw_producer_script_is_session_output(rel, session_start) is False
    # fresh (mtime >= start) → 検査対象
    _write_producer_script(tmp_path, rel, session_start + 5)
    assert runner._asdw_producer_script_is_session_output(rel, session_start) is True


def test_producer_gate_skips_stale_scripts_not_regenerated_this_session(
    tmp_path: Path, monkeypatch
) -> None:
    """全 producer script が stale なら post-main gate は空を返し真因をマスクしない。"""
    validator_calls: list[str] = []

    def fake_create(*_a, **_k):
        validator_calls.append("create")
        return ["prep/create stale"]

    def fake_registration(*_a, **_k):
        validator_calls.append("registration")
        return ["marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_create_scripts", fake_create
    )
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration,
    )
    monkeypatch.chdir(tmp_path)
    session_start = time.time()
    for rel in (
        "src/infra/azure/create-azure-data-resources-prep.sh",
        "src/infra/azure/create-azure-data-resources.sh",
        "src/data/azure/data-registration-script.sh",
    ):
        _write_producer_script(tmp_path, rel, session_start - 3600)

    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    errors = runner._run_asdw_data_producer_contract_gate(
        "1.3", _DATA_DEPLOY_AGENT, session_start=session_start
    )

    assert errors == []
    assert validator_calls == []


@pytest.mark.parametrize(
    "fresh_rel",
    (
        "src/infra/azure/create-azure-data-resources-prep.sh",
        "src/infra/azure/create-azure-data-resources.sh",
    ),
)
def test_producer_gate_skips_stale_sibling_in_mixed_prep_create_pair(
    tmp_path: Path,
    monkeypatch,
    fresh_rel: str,
) -> None:
    """A fresh producer must not be masked by a stale prep/create sibling."""
    validator_calls: list[str] = []

    def fake_create(*_args, **_kwargs):
        validator_calls.append("create")
        return ["stale sibling marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_create_scripts",
        fake_create,
    )
    monkeypatch.chdir(tmp_path)
    session_start = time.time()
    prep_rel = "src/infra/azure/create-azure-data-resources-prep.sh"
    create_rel = "src/infra/azure/create-azure-data-resources.sh"
    _write_producer_script(tmp_path, prep_rel, session_start - 3600)
    _write_producer_script(tmp_path, create_rel, session_start - 3600)
    _write_producer_script(tmp_path, fresh_rel, session_start + 5)

    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    errors = runner._run_asdw_data_producer_contract_gate(
        "1.3",
        _DATA_DEPLOY_AGENT,
        session_start=session_start,
    )

    assert errors == []
    assert validator_calls == []


def test_producer_gate_validates_fresh_prep_create_pair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Both regenerated prep/create scripts remain subject to pair validation."""
    validator_calls: list[str] = []

    def fake_create(*_args, **_kwargs):
        validator_calls.append("create")
        return ["fresh pair marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_create_scripts",
        fake_create,
    )
    monkeypatch.chdir(tmp_path)
    session_start = time.time()
    _write_producer_script(
        tmp_path,
        "src/infra/azure/create-azure-data-resources-prep.sh",
        session_start + 5,
    )
    _write_producer_script(
        tmp_path,
        "src/infra/azure/create-azure-data-resources.sh",
        session_start + 5,
    )

    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    errors = runner._run_asdw_data_producer_contract_gate(
        "1.3",
        _DATA_DEPLOY_AGENT,
        session_start=session_start,
    )

    assert validator_calls == ["create"]
    assert errors == [
        "[Dev-Microservice-Azure-DataDeploy] "
        "generated prep/create contract failed: fresh pair marker missing"
    ]


def test_producer_gate_validates_scripts_regenerated_this_session(
    tmp_path: Path, monkeypatch
) -> None:
    """当 session で再生成された（fresh）registration は検証される。"""

    def fake_registration(*_a, **_k):
        return ["marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration,
    )
    monkeypatch.chdir(tmp_path)
    session_start = time.time() - 3600
    # registration のみ fresh。prep/create 未存在 → create gate は skip。
    _write_producer_script(
        tmp_path, "src/data/azure/data-registration-script.sh", time.time()
    )

    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    errors = runner._run_asdw_data_producer_contract_gate(
        "1.3", _DATA_DEPLOY_AGENT, session_start=session_start
    )

    assert any("data-registration-script.sh contract failed" in e for e in errors)


def test_producer_gate_validates_unconditionally_without_session_start(
    tmp_path: Path, monkeypatch
) -> None:
    """pre-execution gate (session_start=None) は stale でも検証し security を維持。"""

    def fake_registration(*_a, **_k):
        return ["marker missing"]

    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_registration_script",
        fake_registration,
    )
    monkeypatch.chdir(tmp_path)
    # stale mtime だが session_start=None → 無条件検証
    _write_producer_script(
        tmp_path, "src/data/azure/data-registration-script.sh", time.time() - 3600
    )

    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))
    errors = runner._run_asdw_data_producer_contract_gate("1.3", _DATA_DEPLOY_AGENT)

    assert any("data-registration-script.sh contract failed" in e for e in errors)


def test_producer_gate_post_main_and_final_pass_session_start() -> None:
    """post-main / final gate は session_start を渡し、pre-execution は無条件検証。"""
    source = inspect.getsource(StepRunner.run_step)
    # run_step の producer gate は post-main / final の 2 箇所のみで、
    # そのいずれもが session_start=start を渡す（freshness 判定付き品質 gate）。
    assert source.count("self._run_asdw_data_producer_contract_gate(") == 2
    assert source.count("session_start=start") >= 2

    # security 回帰防止: Azure を実行する pre-execution 境界は session_start を
    # 一切受け取らず、実行対象 script を無条件に検証する（memo §20 の stale skip は
    # post-main 品質 gate 限定で、Azure 実行前の security 境界は緩めない）。
    # Step 1.3 の native 化により旧 permission 配線は削除されたため、現行の
    # pre-execution 境界は launcher の stage 実行経路（bash 起動直前）である。
    stage_source = inspect.getsource(execute_stage)
    assert "_validate_stage(" in stage_source
    assert "session_start" not in stage_source
    assert stage_source.index("_validate_stage(") < stage_source.index(
        "process_runner("
    )


def test_runner_data_deploy_gate_fails_closed_when_sample_data_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    validator_called = False

    def unexpected_validator(*_args, **_kwargs):
        nonlocal validator_called
        validator_called = True
        return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "hve.artifact_validation.validate_asdw_data_verify_script",
        unexpected_validator,
    )
    runner = StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))

    errors = runner._run_asdw_data_verify_contract_gate(
        "1.3",
        "Dev-Microservice-Azure-DataDeploy",
        include_registration=False,
    )

    assert any(
        "required input src/data/sample-data.json not found" in error
        for error in errors
    ), errors
    assert validator_called is False


def test_asdw_data_verify_validator_rejects_missing_postgresql_aci_os_type(tmp_path: Path) -> None:
    """PostgreSQL ACI fallback は `--os-type Linux` 欠落時に契約違反となる。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
  --restart-policy Never \
  --secure-environment-variables PGPASSWORD="$PG_TOKEN" \
  --environment-variables PGSSLMODE="require" PGHOST="$PG_HOST" PGUSER="$PG_ADMIN_USER" PGDATABASE="$PG_DB_NAME" \
  --command-line 'sh -c '\''psql --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE"'\'''
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert any("--os-type Linux" in e for e in errors)


def test_asdw_data_verify_validator_rejects_missing_postgresql_aci_resource_requests(tmp_path: Path) -> None:
        """PostgreSQL ACI fallback は `--cpu` / `--memory` 欠落時に契約違反となる。"""
        script = tmp_path / "verify-data-resources.sh"
        script.write_text(
                """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
    --os-type Linux --restart-policy Never \
    --secure-environment-variables PGPASSWORD="$PG_TOKEN" \
    --environment-variables PGSSLMODE="require" PGHOST="$PG_HOST" PGUSER="$PG_ADMIN_USER" PGDATABASE="$PG_DB_NAME" \
    --command-line 'sh -c '\''psql --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE"'\'''
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
                encoding="utf-8",
        )

        errors = validate_asdw_data_verify_script(script)

        assert any("--cpu" in e for e in errors)
        assert any("--memory" in e for e in errors)


def test_asdw_data_verify_validator_rejects_resource_requests_only_in_comments(tmp_path: Path) -> None:
        """`--cpu` / `--memory` がコメントにあるだけでは ACI 契約を満たさない。"""
        script = tmp_path / "verify-data-resources.sh"
        script.write_text(
                """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
# az container create must use --cpu 1 --memory 1, but this stale command does not.
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
    --os-type Linux --restart-policy Never \
    --secure-environment-variables PGPASSWORD="$PG_TOKEN" \
    --environment-variables PGSSLMODE="require" PGHOST="$PG_HOST" PGUSER="$PG_ADMIN_USER" PGDATABASE="$PG_DB_NAME" \
    --command-line 'sh -c '\''psql --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE"'\'''
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
                encoding="utf-8",
        )

        errors = validate_asdw_data_verify_script(script)

        assert any("--cpu" in e for e in errors)
        assert any("--memory" in e for e in errors)


def test_asdw_data_verify_validator_rejects_postgresql_aci_command_line_token(tmp_path: Path) -> None:
    """PostgreSQL ACI fallback で token/UPN を command-line に直展開する実装を落とす。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
az container create -g "$RESOURCE_GROUP" -n verify-pg --image postgres:16-alpine \
    --os-type Linux --cpu 1 --memory 1 --restart-policy Never \
  --secure-environment-variables PGPASSWORD="$PG_TOKEN" \
  --environment-variables PGSSLMODE="require" PGHOST="$PG_HOST" PGUSER="$PG_ADMIN_USER" PGDATABASE="$PG_DB_NAME" \
  --command-line "sh -c 'PGPASSWORD=$PG_TOKEN psql -h $PG_HOST -U $PG_ADMIN_USER -d $PG_DB_NAME'"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert any("アクセストークン" in e for e in errors)
    assert any("UPN" in e for e in errors)


def test_asdw_data_verify_validator_rejects_postgresql_db_show_database_name_flag(tmp_path: Path) -> None:
    """PostgreSQL データベース存在確認は `--database-name` ではなく `--name` を使う契約。

    `az postgres flexible-server db show` に存在しない `--database-name` を使うと
    az CLI が `unrecognized arguments` で失敗する（正しい引数は `--name`/`-n`）。
    RED フェーズではこの失敗が `az_tsv` のエラー握り潰しにより `[FAIL] ... not found`
    と区別できず見逃されるため（2026-07-02 run 20260702T155130-4a3032 実証）、
    静的 gate で検出する。
    """
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
DB_NAME="$(az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$PG_SERVER_NAME" --database-name "$PG_DB_NAME" --query name -o tsv)"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert any("db show" in e and "--database-name" in e for e in errors)
    assert any("--name" in e for e in errors)


def test_asdw_data_verify_validator_accepts_postgresql_db_show_name_flag(tmp_path: Path) -> None:
    """PostgreSQL データベース存在確認が正しい `--name` を使う場合は誤検出しない。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
DB_NAME="$(az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$PG_SERVER_NAME" --name "$PG_DB_NAME" --query name -o tsv)"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert not any("db show" in e and "--database-name" in e for e in errors)


def test_asdw_data_verify_validator_accepts_postgresql_db_show_short_name_flag(tmp_path: Path) -> None:
    """PostgreSQL データベース存在確認が短縮形 `-n` を使う場合も誤検出しない。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
DB_NAME="$(az postgres flexible-server db show -g "$RESOURCE_GROUP" -s "$PG_SERVER_NAME" -n "$PG_DB_NAME" --query name -o tsv)"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert not any("db show" in e and "--database-name" in e for e in errors)


def test_asdw_data_verify_validator_does_not_flag_database_name_mentioned_only_in_comment(
    tmp_path: Path,
) -> None:
    """`--database-name` がコメント（`#` 以降）にのみ登場する場合は誤検知しない。

    2026-07-02 の敵対的レビューで実証された false positive の再発防止用回帰テスト。
    生成物が「`db show` は `--database-name` 不可、`--name` を使う」と正しく解説する
    コメントを書いた場合でも、実際のコマンドが `--name` を使っていれば gate は
    失敗させてはならない。
    """
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
PG_STATE="$(az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query state -o tsv)"
[ "$PG_STATE" = "Ready" ] && echo "state=Ready"
# NOTE: az postgres flexible-server db show does NOT support --database-name; use --name instead.
DB_NAME="$(az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$PG_SERVER_NAME" --name "$PG_DB_NAME" --query name -o tsv)"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert not any("db show" in e and "--database-name" in e for e in errors)


def test_runner_asdw_data_verify_contract_gate_ignores_non_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """ASDW DataTestCoding/DataDeploy 以外には ASDW verify 契約 gate を適用しない。"""
    monkeypatch.chdir(tmp_path)
    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    assert runner._run_asdw_data_verify_contract_gate("2.2", "Dev-Microservice-Azure-AddServiceDeploy") == []


def test_runner_deploy_ac_gate_finds_report_via_glob_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """canonical パス（Issue-step-<id>）が無くても、Agent が Issue-0/ に書いた
    ac-verification.md を glob フォールバックで発見して検証する（実 run の成功経路）。
    """
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    # canonical は Issue-step-1-3 だが、Agent は Issue-0/ に GREEN な AC-1 を書いた
    report = run_root / agent / "Issue-0" / "ac-verification.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "| AC-1 | データストア存在 + provisioningState=Succeeded | ✅ | verify GREEN |\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    # glob フォールバックで Issue-0 を拾い、AC-1=✅ なので gate は pass（空 list）
    assert runner._run_deploy_ac_gate("1.3", agent) == []


def test_runner_deploy_ac_gate_detects_preflight_failure_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """completion-report.md の pre-flight 失敗マーカーを ac-verification.md 不在
    より先に検出し、明確な理由で fail させる（6 deploy prompt が記載するマーカーの実機構化）。
    """
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    # pre-flight 失敗: completion-report.md にマーカーのみ（ac-verification.md は未作成）
    issue = run_root / agent / "Issue-step-1-3"
    issue.mkdir(parents=True, exist_ok=True)
    (issue / "completion-report.md").write_text(
        "# 完了報告\n\n<!-- fatal: pre-flight-failed: az account show 失敗 -->\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    errs = runner._run_deploy_ac_gate("1.3", agent)

    assert len(errs) == 1
    # 「not found」ではなく pre-flight 失敗理由が報告される
    assert "pre-flight failed" in errs[0]
    assert "az account show 失敗" in errs[0]


def test_runner_deploy_ac_gate_no_preflight_marker_falls_through_to_ac_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """completion-report.md があってもマーカーが無ければ従来どおり
    ac-verification.md を検査する（pre-flight 検出が正常系を阻害しないこと）。
    """
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    issue = run_root / agent / "Issue-step-1-3"
    issue.mkdir(parents=True, exist_ok=True)
    # マーカー無しの completion-report.md + GREEN な ac-verification.md
    (issue / "completion-report.md").write_text("# 完了報告\n\n正常完了\n", encoding="utf-8")
    (issue / "ac-verification.md").write_text(
        "| AC-1 | データストア存在 + provisioningState=Succeeded | ✅ | verify GREEN |\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    # マーカー無し → ac-verification.md を検査し AC-1=✅ なので pass
    assert runner._run_deploy_ac_gate("1.3", agent) == []


def test_runner_deploy_ac_gate_ignores_unfilled_preflight_placeholder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """completion-report.md が雛形の未置換プレースホルダ `{理由}` を引用しただけの
    場合は pre-flight 失敗と誤検出せず、ac-verification.md 検査へフォールスルーする。
    """
    agent = "Dev-Microservice-Azure-DataDeploy"
    run_root = tmp_path / "work" / "run" / "run-1"
    issue = run_root / agent / "Issue-step-1-3"
    issue.mkdir(parents=True, exist_ok=True)
    # 雛形をそのまま引用（未置換の {理由}）+ GREEN な ac-verification.md
    (issue / "completion-report.md").write_text(
        "手順引用: `<!-- fatal: pre-flight-failed: {理由} -->`\n正常完了\n",
        encoding="utf-8",
    )
    (issue / "ac-verification.md").write_text(
        "| AC-1 | データストア存在 + provisioningState=Succeeded | ✅ | verify GREEN |\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_WORK_ROOT", str(run_root))

    runner = StepRunner(
        config=SDKConfig(),
        console=Console(verbose=False, quiet=True),
    )

    # プレースホルダは無視 → ac-verification.md (AC-1=✅) を検査して pass
    assert runner._run_deploy_ac_gate("1.3", agent) == []


# ---------------------------------------------------------------------------
# Compute: AC-3 / AC-9
# ---------------------------------------------------------------------------
def test_compute_all_green_passes(tmp_path: Path) -> None:
    content = (
        "| AC | 内容 | 状態 | 根拠 |\n"
        "|----|------|------|------|\n"
        "| AC-3 | リソース存在 | ✅ | verify GREEN |\n"
        "| AC-9 | smoke | ✅ | smoke OK |\n"
    )
    p = _write_report(tmp_path, content)
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
        )
        == []
    )


def test_compute_ac3_failed_returns_error(tmp_path: Path) -> None:
    content = (
        "| AC-3 | リソース存在 | ❌ | not deployed |\n"
        "| AC-9 | smoke | ✅ | ok |\n"
    )
    p = _write_report(tmp_path, content)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
    )
    assert len(errs) == 1
    assert "AC-3" in errs[0]


def test_compute_ac9_needs_verification_returns_error(tmp_path: Path) -> None:
    content = (
        "| AC-3 | リソース存在 | ✅ | ok |\n"
        "| AC-9 | smoke | ⏳ NEEDS-VERIFICATION | pending |\n"
    )
    p = _write_report(tmp_path, content)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions"
    )
    assert len(errs) == 1
    assert "AC-9" in errs[0]


# ---------------------------------------------------------------------------
# SWA: AC-1 / AC-6 / AC-8
# ---------------------------------------------------------------------------
def test_swa_all_green_passes(tmp_path: Path) -> None:
    content = (
        "| AC-1 | SWA リソース存在 | ✅ | ok |\n"
        "| AC-6 | deploy 成功 | ✅ | ok |\n"
        "| AC-8 | HTTP200 + DOM | ✅ | ok |\n"
    )
    p = _write_report(tmp_path, content)
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps"
        )
        == []
    )


def test_swa_pending_status_returns_errors(tmp_path: Path) -> None:
    content = (
        "| AC-1 | SWA リソース存在 | ⏳ | not created |\n"
        "| AC-6 | deploy 成功 | ❌ | failed |\n"
        "| AC-8 | HTTP200 + DOM | ✅ | ok |\n"
    )
    p = _write_report(tmp_path, content)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps"
    )
    assert len(errs) == 2


def test_swa_missing_ac_row_returns_error(tmp_path: Path) -> None:
    """AC-8 行が存在しない場合、`not found as table row` エラー。"""
    content = (
        "| AC-1 | SWA リソース存在 | ✅ | ok |\n"
        "| AC-6 | deploy 成功 | ✅ | ok |\n"
    )
    p = _write_report(tmp_path, content)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps"
    )
    assert len(errs) == 1
    assert "AC-8" in errs[0]
    assert "not found" in errs[0]


# ---------------------------------------------------------------------------
# AddService: AC-1
# ---------------------------------------------------------------------------
def test_addservice_pass(tmp_path: Path) -> None:
    p = _write_report(tmp_path, "| AC-1 | リソース存在 | ✅ | ok |\n")
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-AddServiceDeploy"
        )
        == []
    )


def test_addservice_fail(tmp_path: Path) -> None:
    p = _write_report(tmp_path, "| AC-1 | リソース存在 | ❌ | nope |\n")
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AddServiceDeploy"
    )
    assert len(errs) == 1


# ---------------------------------------------------------------------------
# AgenticRetrieval: AC4B-1 / AC4B-14 / AC4B-15 / AC4B-18
# ---------------------------------------------------------------------------
_AGENTIC_RETRIEVAL_GREEN_ROWS = (
    "| AC4B-1 | リソース存在 | ✅ | ok |\n"
    "| AC4B-14 | reasoning effort 一致 | ✅ | live 設定と設計値が一致 |\n"
    "| AC4B-15 | Knowledge Source 一致 | ✅ | 2 件とも名前・alwaysQuery が一致 |\n"
    "| AC4B-18 | smoke retrieve | ✅ | 全 Knowledge Source が検索対象 |\n"
)


def test_agentic_retrieval_pass(tmp_path: Path) -> None:
    p = _write_report(tmp_path, _AGENTIC_RETRIEVAL_GREEN_ROWS)
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-AgenticRetrievalDeploy"
        )
        == []
    )


# ---------------------------------------------------------------------------
# registry 駆動 reality_gate_acs（G2: プラットフォーム非依存の汎用化）
# ---------------------------------------------------------------------------
def test_registry_acs_fire_for_non_allowlisted_agent(tmp_path: Path) -> None:
    """required_acs を渡せば、allowlist 辞書に無い Agent でも gate が発火する。

    非 Azure（AWS / GCP / Windows / iOS 等）の Deploy Agent でも、registry の
    reality_gate_acs を渡せば実在検証が効くことを固定する（汎用化の核心）。
    """
    p = _write_report(tmp_path, "| AC-1 | デプロイ済み | ❌ | nope |\n")
    errs = validate_deploy_ac_verification(
        p, "Dev-SomePlatform-Deploy", required_acs=["AC-1"]
    )
    assert len(errs) == 1
    assert "not GREEN" in errs[0]


def test_registry_acs_pass_for_non_allowlisted_agent(tmp_path: Path) -> None:
    """非 allowlist Agent でも required_acs が GREEN なら空 list。"""
    p = _write_report(tmp_path, "| AC-1 | デプロイ済み | ✅ | ok |\n")
    assert (
        validate_deploy_ac_verification(
            p, "Dev-SomePlatform-Deploy", required_acs=["AC-1"]
        )
        == []
    )


def test_registry_acs_override_allowlist_dict(tmp_path: Path) -> None:
    """required_acs を渡すと allowlist 辞書ではなく宣言側の AC を検証する。

    AddServiceDeploy の dict は ["AC-1"] のみだが、registry で ["AC-1","AC-13"] を
    渡せば AC-13 も強制される（G3 で塞ぐ穴の単体検証）。
    """
    p = _write_report(
        tmp_path,
        "| AC-1 | リソース存在 | ✅ | ok |\n"
        "| AC-13 | デプロイ済みモデル | ❌ | 0件 |\n",
    )
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AddServiceDeploy", required_acs=["AC-1", "AC-13"]
    )
    assert any("AC-13" in e and "not GREEN" in e for e in errs)


def test_na_status_is_treated_as_green(tmp_path: Path) -> None:
    """状態欄 N/A は GREEN 扱い（条件付き実在系 AC の非該当を許容）。"""
    p = _write_report(
        tmp_path,
        "| AC-1 | リソース存在 | ✅ | ok |\n"
        "| AC-13 | デプロイ済みモデル | N/A | AI/LLM 非該当 |\n",
    )
    assert validate_deploy_ac_verification(
        p,
        "Dev-Microservice-Azure-AddServiceDeploy",
        required_acs=["AC-1", "AC-13"],
    ) == []


def test_foundry_project_na_status_is_treated_as_green(tmp_path: Path) -> None:
    """AI/LLM 非採用時は AC-13/AC-14 の両 N/A 行を受理する。"""
    p = _write_report(
        tmp_path,
        "| AC-1 | リソース存在 | ✅ | ok |\n"
        "| AC-13 | デプロイ済みモデル | N/A | AI/LLM 非該当 |\n"
        "| AC-14 | Foundry Project | N/A | AI/LLM 非該当 |\n",
    )
    assert validate_deploy_ac_verification(
        p,
        "Dev-Microservice-Azure-AddServiceDeploy",
        required_acs=["AC-1", "AC-13", "AC-14"],
    ) == []
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-AddServiceDeploy", required_acs=["AC-1", "AC-13"]
        )
        == []
    )


def test_conditional_ac_missing_row_is_error(tmp_path: Path) -> None:
    """条件付き AC の行を丸ごと省くと not found エラー（N/A 行を残させるため）。"""
    p = _write_report(tmp_path, "| AC-1 | リソース存在 | ✅ | ok |\n")
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AddServiceDeploy", required_acs=["AC-1", "AC-13"]
    )
    assert any("AC-13" in e and "not found" in e for e in errs)


def test_empty_required_acs_falls_back_to_dict(tmp_path: Path) -> None:
    """required_acs が空/None なら後方互換で allowlist 辞書にフォールバックする。"""
    p = _write_report(tmp_path, "| AC-1 | リソース存在 | ✅ | ok |\n")
    # AddServiceDeploy の dict は ["AC-1"]。空リストで呼んでも dict が効く。
    assert (
        validate_deploy_ac_verification(
            p, "Dev-Microservice-Azure-AddServiceDeploy", required_acs=[]
        )
        == []
    )


def test_addservice_deploy_step_declares_reality_gate_acs() -> None:
    """AddServiceDeploy(2.2) が account/model/project の reality AC を宣言する。"""
    from hve.workflow_registry import get_step

    step = get_step("asdw-web", "2.2")
    assert step is not None
    assert step.custom_agent == "Dev-Microservice-Azure-AddServiceDeploy"
    assert step.reality_gate_acs == ["AC-1", "AC-13", "AC-14"]


def test_asdw_data_deploy_step_declares_runtime_registration_acs() -> None:
    """ASDW Step 1.3はGREEN・冪等性・全件数をruntime gateで強制する。"""
    from hve.workflow_registry import get_step

    step = get_step("asdw-web", "1.3")

    if step is None:
        raise AssertionError("asdw-web Step 1.3 must exist")
    assert step.custom_agent == "Dev-Microservice-Azure-DataDeploy"
    assert "src/data/sample-data.json" in step.required_input_paths
    assert step.reality_gate_acs == ["AC-1", "AC-2", "AC-3"]
    assert is_deploy_step(step.custom_agent, step.reality_gate_acs) is True


def test_asdw_data_deploy_runtime_gate_requires_idempotency_and_all_counts(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        "| AC-1 | verifier GREEN | ✅ | all resources healthy |\n",
    )

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("AC-2" in error and "not found" in error for error in errors)
    assert any("AC-3" in error and "not found" in error for error in errors)


def test_asdw_data_deploy_runtime_gate_accepts_all_required_acs(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        "| AC-1 | verifier GREEN | ✅ | all resources healthy |\n"
        "| AC-2 | create + registration idempotent | ✅ | rerun no duplicate |\n"
        "| AC-3 | all entity counts match | ✅ | sample-data exact |\n",
    )

    assert validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    ) == []


def test_asdw_data_deploy_runtime_gate_requires_exact_green_status(
    tmp_path: Path,
) -> None:
    for invalid_status in ("N/A", "該当なし", "PASS", ""):
        report = _write_report(
            tmp_path,
            "| AC-1 | verifier GREEN | ✅ | ok |\n"
            f"| AC-2 | idempotent | {invalid_status} | invalid |\n"
            "| AC-3 | all counts | ✅ | ok |\n",
        )

        errors = validate_deploy_ac_verification(
            report,
            "Dev-Microservice-Azure-DataDeploy",
            required_acs=["AC-1", "AC-2", "AC-3"],
        )

        assert any(
            "AC AC-2 must be exactly `✅`" in error for error in errors
        ), (invalid_status, errors)


def test_asdw_data_deploy_runtime_gate_rejects_duplicate_required_ac_rows(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        "| AC-1 | verifier GREEN | ✅ | ok |\n"
        "| AC-2 | idempotent | ❌ | failed first |\n"
        "| AC-2 | idempotent | ✅ | duplicate override |\n"
        "| AC-3 | all counts | ✅ | ok |\n",
    )

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("AC AC-2 must appear exactly once" in error for error in errors), errors


@pytest.mark.parametrize(
    "hidden_report",
    (
        "```markdown\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "```\n",
        "<!--\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "-->\n",
        "    | AC-1 | verifier GREEN | ✅ | hidden |\n"
        "    | AC-2 | idempotent | ✅ | hidden |\n"
        "    | AC-3 | all counts | ✅ | hidden |\n",
        "<pre>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</pre>\n",
        "<div hidden>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</div>\n",
        "<details>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</details>\n",
        "<table>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</table>\n",
        "<iframe hidden>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</iframe>\n",
        "<custom-element hidden>\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</custom-element>\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_ignores_hidden_green_rows(
    tmp_path: Path,
    hidden_report: str,
) -> None:
    report = _write_report(tmp_path, hidden_report)

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    if hidden_report.lstrip().startswith("<") and not hidden_report.lstrip().startswith("<!--"):
        assert any("visibility boundary is invalid" in error for error in errors), errors
        return
    assert all(
        any(ac in error and "not found" in error for error in errors)
        for ac in ("AC-1", "AC-2", "AC-3")
    ), errors


def test_asdw_data_deploy_hidden_green_cannot_override_visible_failure(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        "| AC-1 | verifier GREEN | ✅ | visible |\n"
        "| AC-2 | idempotent | ❌ | visible failure |\n"
        "| AC-3 | all counts | ✅ | visible |\n"
        "<!-- | AC-2 | idempotent | ✅ | hidden override | -->\n",
    )

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("AC AC-2 must be exactly `✅`" in error for error in errors), errors
    assert not any("AC AC-2 must appear exactly once" in error for error in errors), errors


@pytest.mark.parametrize(
    "unclosed",
    (
        "<!--\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "```markdown\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "<pre>\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "<div hidden>\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "<details>\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "<table>\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
        "<iframe>\n| AC-1 | verifier GREEN | ✅ | hidden |\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_fails_closed_on_unclosed_hidden_region(
    tmp_path: Path,
    unclosed: str,
) -> None:
    report = _write_report(tmp_path, unclosed)

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("visibility boundary is invalid" in error for error in errors), errors


@pytest.mark.parametrize(
    "hidden_report",
    (
        "<!-- first\n"
        "--> <!-- second\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "-->\n",
        "<script>first\n"
        "</script><script>second\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</script>\n",
        "<pre></pre><pre>second\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "</pre>\n",
        "```~markdown\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "```\n",
        "~~~`markdown\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "~~~\n",
        "~~~~~ info\n"
        "| AC-1 | verifier GREEN | ✅ | hidden |\n"
        "| AC-2 | idempotent | ✅ | hidden |\n"
        "| AC-3 | all counts | ✅ | hidden |\n"
        "~~~~~\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_ignores_chained_hidden_regions(
    tmp_path: Path,
    hidden_report: str,
) -> None:
    report = _write_report(tmp_path, hidden_report)

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    if hidden_report.lstrip().startswith("<") and not hidden_report.lstrip().startswith("<!--"):
        assert any("visibility boundary is invalid" in error for error in errors), errors
        return
    assert all(
        any(ac in error and "not found" in error for error in errors)
        for ac in ("AC-1", "AC-2", "AC-3")
    ), errors


@pytest.mark.parametrize(
    "raw_html",
    (
        "<div\n hidden>\n| AC-1 | x | ✅ | hidden |\n</div>\n",
        "<details\n open>\n| AC-1 | x | ✅ | hidden |\n</details>\n",
        "<div hidden/>\n| AC-1 | x | ✅ | hidden |\n",
        "<custom-element/>\n| AC-1 | x | ✅ | hidden |\n",
        "<br>\n| AC-1 | x | ✅ | hidden |\n",
        "<div></div><details\n>\n| AC-1 | x | ✅ | hidden |\n",
        "<!DOCTYPE html>\n| AC-1 | x | ✅ | hidden |\n",
        "<!ENTITY hidden SYSTEM 'value'>\n| AC-1 | x | ✅ | hidden |\n",
        "<![CDATA[hidden]]>\n| AC-1 | x | ✅ | hidden |\n",
        "<?xml version='1.0'?>\n| AC-1 | x | ✅ | hidden |\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_rejects_every_raw_html_block(
    tmp_path: Path,
    raw_html: str,
) -> None:
    report = _write_report(tmp_path, raw_html)

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("visibility boundary is invalid" in error for error in errors), errors


def test_asdw_data_deploy_runtime_gate_allows_inline_br_in_table_cells(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        "| AC-1 | verifier GREEN | ✅ | line1<br>line2 |\n"
        "| AC-2 | idempotent | ✅ | line1<br />line2 |\n"
        "| AC-3 | all counts | ✅ | line1<BR>line2 |\n",
    )

    assert validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    ) == []


@pytest.mark.parametrize(
    "hidden_html",
    (
        "<!-- <div hidden> -->\n",
        "```html\n<div hidden>\n```\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_ignores_raw_html_inside_hidden_markdown(
    tmp_path: Path,
    hidden_html: str,
) -> None:
    report = _write_report(
        tmp_path,
        hidden_html
        + "| AC-1 | verifier GREEN | ✅ | visible |\n"
        "| AC-2 | idempotent | ✅ | visible |\n"
        "| AC-3 | all counts | ✅ | visible |\n",
    )

    assert validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    ) == []


@pytest.mark.parametrize(
    "unclosed",
    (
        "<!-- first\n--> <!-- second\n| AC-1 | x | ✅ | hidden |\n",
        "<script>first\n</script><script>second\n| AC-1 | x | ✅ | hidden |\n",
        "<pre></pre><pre>second\n| AC-1 | x | ✅ | hidden |\n",
        "```~markdown\n| AC-1 | x | ✅ | hidden |\n",
        "~~~`markdown\n| AC-1 | x | ✅ | hidden |\n",
    ),
)
def test_asdw_data_deploy_runtime_gate_rejects_chained_unclosed_boundary(
    tmp_path: Path,
    unclosed: str,
) -> None:
    report = _write_report(tmp_path, unclosed)

    errors = validate_deploy_ac_verification(
        report,
        "Dev-Microservice-Azure-DataDeploy",
        required_acs=["AC-1", "AC-2", "AC-3"],
    )

    assert any("visibility boundary is invalid" in error for error in errors), errors


def test_adfdv_data_deploy_step_declares_reality_gate_acs() -> None:
    """ADFDV Step.1.2 の DataDeploy が実在系 AC-3 を registry で宣言する。"""
    from hve.workflow_registry import get_step

    step = get_step("adfdv", "1.2")

    assert step is not None
    assert step.custom_agent == "Dev-Dataflow-DataDeploy"
    assert step.reality_gate_acs == ["AC-3"]
    assert is_deploy_step(step.custom_agent, step.reality_gate_acs) is True


def test_adfdv_functions_deploy_step_declares_reality_gate_acs() -> None:
    """ADFDV Step.3 の FunctionsDeploy が実在系 AC-2/AC-3 を registry で宣言する。"""
    from hve.workflow_registry import get_step

    step = get_step("adfdv", "3")

    assert step is not None
    assert step.custom_agent == "Dev-Dataflow-FunctionsDeploy"
    assert step.reality_gate_acs == ["AC-2", "AC-3"]
    assert is_deploy_step(step.custom_agent, step.reality_gate_acs) is True


def test_adfdv_data_deploy_registry_ac3_validation(tmp_path: Path) -> None:
    """allowlist 外の ADFDV DataDeploy でも registry required_acs により AC-3 未達を検出する。"""
    p = _write_report(tmp_path, "| AC-3 | batch resources verified | ❌ | verify failed |\n")

    errs = validate_deploy_ac_verification(
        p, "Dev-Dataflow-DataDeploy", required_acs=["AC-3"]
    )

    assert len(errs) == 1
    assert "AC-3" in errs[0]


def test_adfdv_functions_deploy_registry_ac2_ac3_validation(tmp_path: Path) -> None:
    """allowlist 外の ADFDV FunctionsDeploy でも AC-2/AC-3 の GREEN を強制できる。"""
    p = _write_report(
        tmp_path,
        "| AC-2 | verify-batch-resources | ✅ | ok |\n"
        "| AC-3 | deployed resources exist | ⏳ NEEDS-VERIFICATION | pending |\n",
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Dataflow-FunctionsDeploy", required_acs=["AC-2", "AC-3"]
    )

    assert len(errs) == 1
    assert "AC-3" in errs[0]



def test_agentic_retrieval_fail(tmp_path: Path) -> None:
    rows = _AGENTIC_RETRIEVAL_GREEN_ROWS.replace(
        "| AC4B-1 | リソース存在 | ✅ | ok |",
        "| AC4B-1 | リソース存在 | ⏳ | pending |",
    )
    p = _write_report(tmp_path, rows)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgenticRetrievalDeploy"
    )
    assert len(errs) == 1
    assert "AC4B-1" in errs[0]


def test_agentic_retrieval_smoke_retrieve_must_be_green(tmp_path: Path) -> None:
    """AC4B-18（全 Knowledge Source を横断した smoke retrieve）は実在系。"""
    rows = _AGENTIC_RETRIEVAL_GREEN_ROWS.replace(
        "| AC4B-18 | smoke retrieve | ✅ | 全 Knowledge Source が検索対象 |",
        "| AC4B-18 | smoke retrieve | ❌ | 未実行 |",
    )
    p = _write_report(tmp_path, rows)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgenticRetrievalDeploy"
    )
    assert len(errs) == 1
    assert "AC4B-18" in errs[0]


def test_agentic_retrieval_missing_knowledge_source_row_is_rejected(tmp_path: Path) -> None:
    """AC4B-15 の行ごと削除した場合も gate が発火する。"""
    rows = "".join(
        line + "\n"
        for line in _AGENTIC_RETRIEVAL_GREEN_ROWS.splitlines()
        if "AC4B-15" not in line
    )
    p = _write_report(tmp_path, rows)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgenticRetrievalDeploy"
    )
    assert len(errs) == 1
    assert "AC4B-15" in errs[0]


# ---------------------------------------------------------------------------
# AgentDeploy: AC-1 / AC-2 / AC-3
# ---------------------------------------------------------------------------
def test_agent_deploy_pass(tmp_path: Path) -> None:
    content = (
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + _agent_provider_table(tmp_path)
    )
    p = _write_report(tmp_path, content)
    assert (
        validate_deploy_ac_verification(p, "Dev-Microservice-Azure-AgentDeploy")
        == []
    )


def test_agent_deploy_fail(tmp_path: Path) -> None:
    content = (
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ❌ | not registered |\n"
        "| AC-3 | HTTP 200 | ⏳ NEEDS-VERIFICATION | pending |\n"
        + _agent_provider_table(tmp_path)
    )
    p = _write_report(tmp_path, content)
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )
    assert len(errs) == 2


def test_agent_deploy_missing_provider_preflight_is_error(tmp_path: Path) -> None:
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n",
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("Provider Pre-flight" in error and "not found" in error for error in errs)


def test_agent_deploy_selected_provider_requires_green_evidence(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "work-iq": [
                "SELECTED-FAIL",
                "docs/agent/agent-detail-key.md#section-7",
                "delegated user",
                "tenant scoped",
                "N/A",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        }
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("work-iq" in error and "SELECTED-PASS" in error for error in errs)


def test_agent_deploy_selected_provider_accepts_redacted_smoke_evidence(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "azure-ai-search-foundry-iq": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "project identity with read role",
                "same approved tenant and region",
                "tool=knowledge_base_retrieve status=200 citations=2",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        }
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    assert validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    ) == []


def test_agent_deploy_na_provider_requires_reason_source_and_zero_delta(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "fabric-iq": [
                "N/A: <理由>",
                "TBD",
                "N/A",
                "N/A",
                "N/A",
                "unexpected",
                "confirmed",
                "confirmed",
            ]
        }
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("fabric-iq" in error and "Decision source" in error for error in errs)
    assert any("fabric-iq" in error and "concrete reason" in error for error in errs)
    assert any("fabric-iq" in error and "Inventory delta must be" in error for error in errs)


def test_agent_deploy_provider_smoke_rejects_raw_url_or_secret(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "web-iq": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "delegated user",
                "approved external web boundary",
                "https://internal.example/items/42 token=raw-value",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        }
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("web-iq" in error and "secret-like material" in error for error in errs)
    assert any("web-iq" in error and "must not contain raw URLs" in error for error in errs)


def test_agent_deploy_provider_table_inside_code_fence_is_rejected(tmp_path: Path) -> None:
    fenced_table = "```markdown\n" + _agent_provider_table(tmp_path) + "```\n"
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + fenced_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("Provider Pre-flight" in error and "not found" in error for error in errs)


def test_agent_deploy_provider_table_inside_longer_code_fence_is_rejected(tmp_path: Path) -> None:
    fenced_table = "````markdown\n```\n" + _agent_provider_table(tmp_path) + "````\n"
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + fenced_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("Provider Pre-flight" in error and "not found" in error for error in errs)


def test_agent_deploy_provider_table_requires_exact_header(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(tmp_path).replace(
        "| Route | Status |", "| Provider | Status |", 1
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("exact fixed 9-column header" in error for error in errs)


def test_agent_deploy_provider_table_rejects_secret_in_permission(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "work-iq": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "token=raw-value",
                "tenant scoped",
                "tool=fetch status=200 count=1",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        },
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("work-iq" in error and "secret-like material" in error for error in errs)


def test_agent_deploy_provider_table_rejects_raw_url_in_permission(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "remote-mcp": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "endpoint=https://mcp.internal.example/",
                "approved tenant boundary",
                "tool=read status=200 count=1",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        },
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("remote-mcp" in error and "must not contain raw URLs" in error for error in errs)


def test_agent_deploy_provider_table_rejects_query_title_and_item_evidence(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "fabric-iq": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "delegated user",
                "approved workspace region",
                "status=200 query=payroll document title=Payroll item ID=42",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        },
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("fabric-iq" in error and "query/title/item/body" in error for error in errs)


def test_agent_deploy_provider_table_rejects_sensitive_aliases(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "fabric-iq": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "credential=raw-value",
                "approved workspace region",
                "status=200 title=Payroll item_id=42 body=Confidential",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        },
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("fabric-iq" in error and "secret-like material" in error for error in errs)
    assert any("fabric-iq" in error and "query/title/item/body" in error for error in errs)


def test_agent_deploy_web_provider_rejects_raw_public_citation_url(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(
        tmp_path,
        route_rows={
            "foundry-web-search": [
                "SELECTED-PASS",
                "docs/agent/agent-detail-key.md#section-7",
                "project user",
                "approved external web boundary",
                "status=200 citations=1 https://www.microsoft.com/",
                "expected-only",
                "confirmed",
                "confirmed",
            ]
        },
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any(
        "foundry-web-search" in error and "must not contain raw URLs" in error
        for error in errs
    )


def test_provider_inventory_generator_rehashes_hex_shaped_raw_identifier() -> None:
    categories = {
        "project-connection": ["a" * 64],
        "rbac-consent": [],
        "key-vault-reference": [],
        "package": [],
        "config-flag": [],
    }
    raw_routes = {
        route: {category: list(values) for category, values in categories.items()}
        for route in (
            "azure-ai-search-foundry-iq",
            "work-iq",
            "fabric-iq",
            "web-iq",
            "foundry-web-search",
            "remote-mcp",
        )
    }

    snapshot = build_provider_inventory_snapshot(raw_routes)
    routes = cast(dict[str, dict[str, list[str]]], snapshot["routes"])
    stored = routes["work-iq"]["project-connection"]

    assert stored == [hashlib.sha256(("a" * 64).encode("utf-8")).hexdigest()]
    assert stored != ["a" * 64]
    assert snapshot["generator"] == (
        "hve.artifact_validation.build_provider_inventory_snapshot/v1"
    )


def test_agent_deploy_na_inventory_uses_snapshot_delta_not_self_report(tmp_path: Path) -> None:
    provider_table = _agent_provider_table(tmp_path)
    after_path = tmp_path / "provider-inventory-after.json"
    after_payload = json.loads(after_path.read_text(encoding="utf-8"))
    after_payload["routes"]["fabric-iq"]["project-connection"] = ["2" * 64]
    after_text = json.dumps(
        after_payload, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"
    after_bytes = after_text.encode("utf-8")
    after_path.write_bytes(after_bytes)
    evidence_path = tmp_path / "provider-inventory-evidence.json"
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence_payload["after_sha256"] = hashlib.sha256(
        after_bytes
    ).hexdigest()
    evidence_path.write_text(
        json.dumps(
            evidence_payload, ensure_ascii=False, sort_keys=True, indent=2
        ) + "\n",
        encoding="utf-8",
    )
    p = _write_report(
        tmp_path,
        "| AC-1 | Foundry プロジェクト存在 | ✅ | ok |\n"
        "| AC-2 | Agent 登録 | ✅ | ok |\n"
        "| AC-3 | HTTP 200 | ✅ | ok |\n"
        + provider_table,
    )

    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-AgentDeploy"
    )

    assert any("fabric-iq" in error and "changed_categories" in error for error in errs)
    assert any("fabric-iq" in error and "zero inventory delta" in error for error in errs)


# ---------------------------------------------------------------------------
# DataDeploy: AC-1
# ---------------------------------------------------------------------------
def test_data_deploy_pass(tmp_path: Path) -> None:
    p = _write_report(
        tmp_path,
        "| AC-1 | データストア存在 + provisioningState=Succeeded | ✅ | verify GREEN |\n",
    )
    assert (
        validate_deploy_ac_verification(p, "Dev-Microservice-Azure-DataDeploy")
        == []
    )


def test_data_deploy_fail(tmp_path: Path) -> None:
    p = _write_report(
        tmp_path,
        "| AC-1 | データストア存在 | ❌ | not created |\n",
    )
    errs = validate_deploy_ac_verification(
        p, "Dev-Microservice-Azure-DataDeploy"
    )
    assert len(errs) == 1


# ---------------------------------------------------------------------------
# allowlist 定数の sanity check
# ---------------------------------------------------------------------------
def test_allowlist_constant_has_expected_agents() -> None:
    assert set(_DEPLOY_AGENT_REALITY_AC.keys()) == {
        "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions",
        "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps",
        "Dev-Microservice-Azure-AddServiceDeploy",
        "Dev-Microservice-Azure-AgenticRetrievalDeploy",
        "Dev-Microservice-Azure-AgentDeploy",
        "Dev-Microservice-Azure-DataDeploy",
    }
