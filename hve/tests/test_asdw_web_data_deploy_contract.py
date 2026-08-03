"""ASDW-WEB Step.1.3 (Dev-Microservice-Azure-DataDeploy) の prompt/template 契約テスト。

Step.1.3 が `deploy_ac_gate_failed` で繰り返し停止した事象への再発抑止として
追加した以下の契約が消えないことを検証する:
  - DataDeploy prompt の禁止事項に「出力契約外成果物の作成」「同期完了済みコマンドの
    出力再取得」が含まれること
  - Step.1.3 テンプレートの `## 出力` に必須 work 成果物
    (`work-status.md` / `ac-verification.md`) が列挙されていること
    （`{completion_instruction}` の「上記の出力ファイルが全て生成されたか」確認が
    これらを対象に含めるため）
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from hve.artifact_validation import validate_asdw_data_verify_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-DataDeploy.prompt.md"
)
_STEP_1_3 = (
    _REPO_ROOT
    / ".github"
    / "scripts"
    / "templates"
    / "asdw-web"
    / "step-1.3.md"
)
_COPILOT_INSTRUCTIONS = _REPO_ROOT / ".github" / "copilot-instructions.md"
_STEP_1_2 = (
    _REPO_ROOT
    / ".github"
    / "scripts"
    / "templates"
    / "asdw-web"
    / "step-1.2.md"
)
_STEP_1_1 = (
    _REPO_ROOT
    / ".github"
    / "scripts"
    / "templates"
    / "asdw-web"
    / "step-1.1.md"
)
_GENERIC_IO_CONTRACT = (
    _REPO_ROOT
    / ".github"
    / "io-contracts"
    / "Dev-Microservice-Azure-DataDeploy.yaml"
)
_STEP_IO_CONTRACT = (
    _REPO_ROOT
    / ".github"
    / "io-contracts"
    / "Dev-Microservice-Azure-DataDeploy--asdw-web--1.3.yaml"
)

# Step.1.2 (TDD RED) verify スクリプト生成元 prompt。
_TESTCODING_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-DataTestCoding.prompt.md"
)
_SHARED_NETWORK_CONTRACT = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "azure-skills"
    / "azure-cli-deploy-scripts"
    / "references"
    / "asdw-data-verifier-contract.md"
)
_DATA_DESIGN_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-DataDesign.prompt.md"
)
_GITATTRIBUTES = _REPO_ROOT / ".gitattributes"

_ASDW_DATA_AZURE_DOC_FILES = (
    _DATA_DESIGN_PROMPT,
    _TESTCODING_PROMPT,
    _PROMPT,
    _STEP_1_1,
    _STEP_1_2,
    _STEP_1_3,
)

_GUI_POWERSHELL_TRANSPORT = (
    'pwsh.exe -NoLogo -NoProfile -Command "<canonical command>"'
)
_HVE_PRODUCER_HEADING = "## HVE-owned producer contract (Agent read-only)"
_PRODUCER_SCRIPT_OUTPUTS = (
    "create-azure-data-resources-prep.sh",
    "create-azure-data-resources.sh",
    "data-registration-script.sh",
)
_AGENT_DELEGATION_DOCS = (
    _PROMPT,
    _STEP_1_3,
)
_PRODUCER_IO_CONTRACTS = (_GENERIC_IO_CONTRACT, _STEP_IO_CONTRACT)


def _markdown_section(text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE)
    assert match is not None, f"missing section {heading!r}"
    following = text[match.end() :]
    next_heading = re.search(r"^## (?!#)", following, re.MULTILINE)
    return following if next_heading is None else following[: next_heading.start()]


def test_data_deploy_prompt_prohibits_out_of_contract_artifact() -> None:
    """出力契約外成果物（課題管理表等）の作成禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "出力先パスに無い成果物" in text


def test_data_deploy_prompt_prohibits_resync_completed_command() -> None:
    """同期完了済みコマンドへの出力取得ツール再呼び出し禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "同期実行で既に完了したコマンド" in text


def test_data_deploy_prompt_delegates_evidence_finalization_to_hve() -> None:
    """P11: 証跡の確定は HVE evidence が行い、Agent は介入しない。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "HVE evidence が StageResult だけを根拠に生成し" in text
    assert "Agent はこれらを新規作成・上書き・訂正しない" in text
    assert "未到達 stage や未実行 verify を `✅` / `PASS` にしない" in text
    assert "HVE が記録した事実を書き換えない" in text


def test_data_deploy_docs_define_execution_ownership_exactly_once() -> None:
    """P11: generator / launcher / pipeline / evidence / Agent の責務を 1 回だけ定義する。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert text.count("## 実行責務（本 Step で 1 回だけ定義する）") == 1
    for subject in (
        "| HVE generator |",
        "| HVE launcher |",
        "| HVE pipeline |",
        "| HVE evidence |",
        "| Agent |",
    ):
        assert text.count(subject) == 1, subject
    assert "prep → create → registration → verify → create → registration → verify" in text


def test_data_deploy_docs_remove_agent_launcher_stage_requests() -> None:
    """P11: Agent は launcher stage を要求せず、HVE pipeline が実行する。"""
    for path in _AGENT_DELEGATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "Agent は launcher stage を要求しない" in text, path
        assert "HVE-owned fixed pipeline" in text, path
        assert "python -m hve.asdw_data_script_launcher create" not in text, path
        assert "python -m hve.asdw_data_script_launcher registration" not in text, path
        assert "python -m hve.asdw_data_script_launcher verify" not in text, path


def test_data_deploy_prompt_requires_green_tdd_report_as_hve_owned_artifact() -> None:
    """P11: GREEN tdd-test-report.md は HVE evidence が生成する必須成果物である。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "TDD テスト結果レポート `tdd-test-report.md`" in text
    assert "本レポートは HVE evidence が StageResult だけを根拠に生成する" in text
    assert "Agent は新規作成・上書き・訂正を行わない" in text


def test_step_1_3_template_requires_green_tdd_report_artifact() -> None:
    """GREEN tdd-test-report.md が template の必須スタブ・完了条件に列挙されている。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "TDD テスト結果レポート `tdd-test-report.md`" in text
    assert "`TDD-Judgement` を `PASS`（GREEN）/`BLOCKED`" in text
    assert "`TDD-Judgement: BLOCKED`" in text


def test_data_deploy_prompt_requires_direct_launcher_invocation_without_probe() -> None:
    """launcher の存在 probe 禁止・直接呼び出し・失敗時フォールバック禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "ファイル存在を shell で確認しない" in text
    assert "Get-ChildItem" in text
    assert "手動 `az` 代替検証" in text
    assert "フォールバックしない" in text


def test_step_1_3_template_requires_direct_launcher_invocation_without_probe() -> None:
    """launcher の存在 probe 禁止・失敗時フォールバック禁止が template に明記されている。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "ファイル存在を shell で probe しない" in text
    assert "フォールバックせず" in text


def test_data_deploy_prompt_prohibits_fabricated_green() -> None:
    """未実行操作を実行済みのように記録する捏造の禁止が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "実行・成功したかのように" in text
    assert "幻覚の自己検知・コンテキスト逼迫を検知した後も" in text
    assert "AC-1 の状態は**直近の実 verify 出力**のみを根拠" in text
    assert "verify 未実行 / 結果確認不能" in text


def test_data_deploy_prompt_limits_long_running_command_output() -> None:
    """長時間 Azure 操作の出力で context を肥大化させない規律が prompt に明記されている。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "長時間コマンドの出力は会話へ全量貼らず" in text
    assert "`create` /" in text
    assert "data-registration-script.sh" in text
    assert "verify-data-resources.sh" in text
    assert "exit code と末尾" in text
    assert "必要最小限に限定" in text


def test_data_deploy_prompt_does_not_delegate_producer_internals_to_agent() -> None:
    """Remove exact legacy implementation instructions, not generic terms."""
    prompt = _PROMPT.read_text(encoding="utf-8")
    template = _STEP_1_3.read_text(encoding="utf-8")
    for phrase in (
        "- **データサービス作成の並列実行方針（必須）**:",
        "- **ジョブ起動と終了コード集約**:",
        "{WORK}artifacts/logs/data-create-<service>.log",
        "data-deploy.env.d/<service>.env",
        "Azure SDK が必要な Cosmos/Blob/ADX 登録だけは隔離 venv",
        "pip/venv のログを stdout に混ぜて",
        "Kusto SDK（`azure-kusto-ingest` / `azure-kusto-data`）",
    ):
        assert phrase not in prompt, phrase
    for phrase in (
        "データサービス作成の並列実行方針」に従う",
        "その非Audit登録用 Python は WSL/Linux native `python3`",
        "Azure SDKが必要な登録処理のみ隔離 venvを使う",
    ):
        assert phrase not in template, phrase


def test_data_deploy_preflight_contract_is_cross_platform_and_shared() -> None:
    """Prompt/template/skill must use only PowerShell-and-Bash-compatible probes."""
    expected = (
        "az --version",
        "az account show -o tsv",
        "gh --version",
        "gh auth status",
    )
    for path in (_PROMPT, _STEP_1_3, _SHARED_NETWORK_CONTRACT):
        text = path.read_text(encoding="utf-8")
        for command in expected:
            assert command in text, f"{path.name} must declare {command!r}"
        assert "command -v az" not in text
        assert "command -v gh" not in text


def test_data_deploy_skill_limits_gui_powershell_to_the_canonical_transport() -> None:
    """The GUI transport exception must not authorize agent-created wrappers."""
    text = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")

    assert _GUI_POWERSHELL_TRANSPORT in text
    assert "追加option・改行・入れ子引用符を拒否したうえで" in text
    assert "内側を固定preflight、固定inspection、または上記launcherとの完全一致で再判定" in text
    assert "commands[].identifier`も外側の完全なtransport文字列と厳密一致" in text
    assert "生成主体を示す改ざん不能なprovenanceを持たない" in text
    assert "Agentにこのwrapperの要求・組み立てを許可するものではない" in text
    assert "PowerShell / cmd / make / npm等の不透明なwrapperを既定承認しない" in text
    for path in (_PROMPT, _STEP_1_3):
        delegated = path.read_text(encoding="utf-8")
        assert _GUI_POWERSHELL_TRANSPORT not in delegated, path
        assert "pwsh.exe" not in delegated, path
        assert "asdw-data-verifier-contract.md" in delegated, path


def test_data_deploy_shell_restriction_exempts_mdq_cli_requirement() -> None:
    """A shell-constrained Step must not be ordered to invoke disallowed mdq CLI."""
    text = _COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")

    assert "fail-closed shell allowlist" in text
    assert "markdown-query CLI" in text
    assert "read/search tool" in text


def test_data_deploy_prompt_and_template_delegate_strict_details_to_shared_contract() -> None:
    """Prompt/template state responsibility and delegate grammar to one SSOT."""
    for path in _AGENT_DELEGATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "asdw-data-verifier-contract.md" in text
        assert _HVE_PRODUCER_HEADING in text
    shared = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")
    assert "Step 1.3 DataDeploy network contract" in shared
    assert "Step 1.3 AuditRecord registration contract" in shared


def test_shell_scripts_are_lf_pinned_in_gitattributes() -> None:
    """生成/実行される shell scripts は Git checkout 時点で LF に固定される。"""
    text = _GITATTRIBUTES.read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in text


def test_data_prompts_and_templates_require_lf_shell_scripts() -> None:
    """DataTestCoding/DataDeploy の prompt/template は CRLF 混入を禁止する。"""
    for path in (_PROMPT, _TESTCODING_PROMPT, _STEP_1_2, _STEP_1_3):
        text = path.read_text(encoding="utf-8")
        assert "LF 改行" in text
        assert "CRLF 禁止" in text
        assert "UTF-8 BOM なし" in text


def test_asdw_data_prompts_and_templates_require_microsoft_learn_mcp_evidence() -> None:
    """ASDW-WEB Step.1 系は Azure 情報を Microsoft Learn MCP で確認し根拠を残す。"""
    for path in _ASDW_DATA_AZURE_DOC_FILES:
        text = path.read_text(encoding="utf-8")
        assert "Microsoft Learn MCP" in text, f"{path.name} に Microsoft Learn MCP 参照規律が無い"
        assert "利用可能なら必ず参照" in text, f"{path.name} に利用可能時の必須参照規律が無い"
        assert "title / URL / 確認事項" in text, f"{path.name} に根拠記録形式が無い"
        assert "要確認（Microsoft Learn MCP 未取得）" in text, f"{path.name} に未取得時の留保表現が無い"
        assert "推測で確定しない" in text, f"{path.name} に推測確定禁止が無い"


def test_step_1_3_template_lists_work_artifacts_as_output() -> None:
    """Step.1.3 テンプレートの出力に必須 work 成果物が run スコープパスで列挙されている。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "Issue-<識別子>/ac-verification.md" in text
    assert "Issue-<識別子>/work-status.md" in text


def test_step_1_2_template_uses_postgresql_state_ready_contract() -> None:
    """Step.1.2 テンプレートは PostgreSQL Flexible Server に state=Ready を使う。"""
    text = _STEP_1_2.read_text(encoding="utf-8")
    assert "PostgreSQL Flexible Server" in text
    assert "state=Ready" in text
    assert "PostgreSQL Flexible Server に `provisioningState=Succeeded` を一律適用せず" in text


def test_data_testcoding_prompt_uses_postgresql_state_ready_contract() -> None:
    """DataTestCoding prompt は PostgreSQL Flexible Server を provisioningState で一律判定しない。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "PostgreSQL Flexible Server は `az postgres flexible-server show --query state -o tsv` が `Ready`" in text
    assert "PostgreSQL Flexible Server に `provisioningState=Succeeded` を一律適用してはならない" in text


def test_data_testcoding_delegates_safe_passwordless_private_aci_contract() -> None:
    """Step.1.2 は secret 型の旧 fallback でなく共有UAMI契約へ委譲する。"""
    prompt = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    contract = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")
    assert "asdw-data-verifier-contract.md` を適用する" in prompt
    for option in (
        "--assign-identity",
        "--restart-policy Never",
        "--os-type Linux",
        "--cpu 1",
        "--memory 1",
    ):
        assert option in contract
    assert "Authentication=ActiveDirectoryMSI" in contract
    assert "DefaultAzureCredential(managed_identity_client_id=" in contract
    assert "PGPASSWORD" not in contract
    assert "秘密を含む接続文字列 / 長期 token への fallback を禁止" in contract


def test_shared_private_aci_contract_requires_bounded_log_and_exit_checks() -> None:
    """共有契約はhost側の脆弱な最終行抽出でなくACI終了状態を判定する。"""
    contract = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")
    assert "timeout 600 az container logs" in contract
    assert "aci_wait_failed=1" in contract
    assert "instanceView.currentState.exitCode" in contract
    assert "wait失敗、非ゼロexit、空ログで非ゼロ終了" in contract
    assert "待機なし、無制限の`--follow`、timeout値変更" in contract
    assert "tail -n 1" not in contract


def test_asdw_data_verify_validator_rejects_postgresql_provisioning_state(tmp_path: Path) -> None:
    """ASDW data verify validator は stale な PostgreSQL provisioningState 判定を落とす。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query 'provisioningState' -o tsv
echo "provisioningState=Succeeded"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(script)

    assert any("--query state" in e for e in errors)
    assert any("provisioningState" in e for e in errors)


def test_asdw_data_verify_validator_accepts_postgresql_state_ready(tmp_path: Path) -> None:
    """ASDW data verify validator は PostgreSQL state=Ready と安全な ACI fallback を受け入れる。"""
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
  --command-line 'sh -c '\''psql --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE"'\'''
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(script) == []


# PostgreSQL を含まない verify スクリプト（Azure SQL / Cosmos / Storage のみ）。
_NON_POSTGRES_VERIFY_SCRIPT = """#!/usr/bin/env bash
az_tsv() {
    az "$@" -o tsv 2>/dev/null
}

verify_sql() {
    az_tsv sql db show --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" --name "$SQL_DATABASE" --query status
}

verify_cosmos() {
    az_tsv cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --query provisioningState
}

verify_storage() {
    az_tsv storage account show --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" --query provisioningState
}
"""

# Chosen 列に PostgreSQL を含まない設計（Alternatives 列には含む）。
_DESIGN_WITHOUT_POSTGRES = """# Azure データストア設計

## 1. エンティティ別ストア選定

| Entity | Data characteristics | Access patterns | Consistency | Chosen Azure service | Partition/Key/Index | Rationale | Alternatives | Evidence |
|---|---|---|---|---|---|---|---|---|
| SupportCase | 構造化 | member_id | 強整合 | Azure SQL Database | PK: id | OLTP | Azure Database for PostgreSQL Flexible Server | link |
| ChatbotSession | 半構造化 | session_id | 最終 | Azure Cosmos DB | pk: session_id | NoSQL | Azure SQL Database | link |
| PrivacyAuditEntry | append-only | range | 最終 | Azure Blob Storage + Azure Data Explorer | path | WORM | Azure Cosmos DB | link |
"""

# Chosen 列に PostgreSQL を含む設計。
_DESIGN_WITH_POSTGRES = """# Azure データストア設計

## 1. エンティティ別ストア選定

| Entity | Data characteristics | Access patterns | Consistency | Chosen Azure service | Partition/Key/Index | Rationale | Alternatives | Evidence |
|---|---|---|---|---|---|---|---|---|
| SupportCase | 構造化 | member_id | 強整合 | Azure Database for PostgreSQL Flexible Server | PK: id | OLTP | Azure SQL Database | link |
"""


def test_asdw_data_verify_validator_accepts_non_postgresql_design(tmp_path: Path) -> None:
    """設計が PostgreSQL 非選定なら、PostgreSQL 検証を含まない verify スクリプトを受け入れる。

    2026-07-02 の実行で DataDesign が Azure SQL / Cosmos / Blob+ADX を選定
    （PostgreSQL は Alternatives のみ）した際、正しく生成された PostgreSQL 非依存の
    verify スクリプトを gate が 4 件の偽陽性で fail させた事象の再発防止。
    """
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_NON_POSTGRES_VERIFY_SCRIPT, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_DESIGN_WITHOUT_POSTGRES, encoding="utf-8")

    assert validate_asdw_data_verify_script(script, design_doc_path=design) == []


def test_asdw_data_verify_validator_requires_postgresql_when_design_selects_it(tmp_path: Path) -> None:
    """設計が PostgreSQL を選定しているのに verify スクリプトが欠く場合は契約違反。

    PostgreSQL 検証要求の条件化後も、実際に選定された PostgreSQL の欠落
    （stale / 未カバレッジ）は検出し続けることを保証する。
    """
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(_NON_POSTGRES_VERIFY_SCRIPT, encoding="utf-8")
    design = tmp_path / "azure-services-data.md"
    design.write_text(_DESIGN_WITH_POSTGRES, encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, design_doc_path=design)

    assert any("az postgres flexible-server show" in e for e in errors)


def test_asdw_data_verify_validator_validates_present_postgresql_block_regardless_of_design(
    tmp_path: Path,
) -> None:
    """設計が PostgreSQL 非選定でも、スクリプトに PostgreSQL ブロックが実在すれば正当性を検査する。"""
    script = tmp_path / "verify-data-resources.sh"
    script.write_text(
        """#!/usr/bin/env bash
section "PostgreSQL Flexible Server: ${PG_SERVER_NAME}"
az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_SERVER_NAME" --query 'provisioningState' -o tsv
echo "provisioningState=Succeeded"
section "Cosmos DB: ${COSMOS_ACCOUNT_NAME}"
""",
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_DESIGN_WITHOUT_POSTGRES, encoding="utf-8")

    errors = validate_asdw_data_verify_script(script, design_doc_path=design)

    # 実在する PostgreSQL ブロックの provisioningState 誤用は設計に関わらず検出する。
    assert any("--query state" in e for e in errors)


def test_design_requires_postgresql_distinguishes_chosen_from_alternatives(tmp_path: Path) -> None:
    """_design_requires_postgresql は Chosen 列のみを見て Alternatives 列の PostgreSQL を無視する。"""
    from hve.artifact_validation import _design_requires_postgresql

    without_pg = tmp_path / "no-pg.md"
    without_pg.write_text(_DESIGN_WITHOUT_POSTGRES, encoding="utf-8")
    with_pg = tmp_path / "with-pg.md"
    with_pg.write_text(_DESIGN_WITH_POSTGRES, encoding="utf-8")

    assert _design_requires_postgresql(without_pg) is False
    assert _design_requires_postgresql(with_pg) is True
    assert _design_requires_postgresql(None) is False
    assert _design_requires_postgresql(tmp_path / "missing.md") is False


def test_asdw_data_verify_validator_accepts_az_tsv_postgresql_state_ready(tmp_path: Path) -> None:
        """ASDW data verify validator は az_tsv wrapper 経由の PostgreSQL state=Ready を受け入れる。"""
        script = tmp_path / "verify-data-resources.sh"
        script.write_text(
                """#!/usr/bin/env bash
az_tsv() {
    az "$@" -o tsv 2>/dev/null
}

verify_postgres() {
    local state=""
    state="$(az_tsv postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$POSTGRES_SERVER" --query state)"
    if [[ "$state" == "Ready" ]]; then
        echo "state=Ready"
    fi
    postgres_count_via_aci
}

postgres_count_via_aci() {
    az container create \
        --resource-group "$RESOURCE_GROUP" \
        --name verify-pg \
        --image postgres:16-alpine \
        --os-type Linux \
        --cpu 1 \
        --memory 1 \
        --restart-policy Never \
        --environment-variables \
            "PGHOST=${POSTGRES_HOST}" \
            "PGUSER=${PG_USER}" \
            "PGDATABASE=${POSTGRES_DATABASE}" \
            "PGSSLMODE=require" \
        --secure-environment-variables "PGPASSWORD=${PG_TOKEN}" \
        --command-line "sh -c 'psql -tAc \"select 1\"'"
}

verify_cosmos() {
    az_tsv cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --query provisioningState
}

verify_storage() {
    az_tsv storage account show --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" --query provisioningState
}

verify_synapse() {
    az_tsv synapse workspace show --resource-group "$RESOURCE_GROUP" --name "$SYNAPSE_WORKSPACE" --query provisioningState
}
""",
                encoding="utf-8",
        )

        assert validate_asdw_data_verify_script(script) == []


def test_asdw_data_verify_validator_rejects_az_tsv_postgresql_provisioning_state(tmp_path: Path) -> None:
        """ASDW data verify validator は az_tsv wrapper 経由でも PostgreSQL provisioningState 判定を落とす。"""
        script = tmp_path / "verify-data-resources.sh"
        script.write_text(
                """#!/usr/bin/env bash
az_tsv() {
    az "$@" -o tsv 2>/dev/null
}

verify_postgres() {
    local state=""
    state="$(az_tsv postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$POSTGRES_SERVER" --query provisioningState)"
    if [[ "$state" == "Succeeded" ]]; then
        echo "provisioningState=Succeeded"
    fi
    az container create \
        --resource-group "$RESOURCE_GROUP" \
        --name verify-pg \
        --image postgres:16-alpine \
        --os-type Linux \
        --cpu 1 \
        --memory 1 \
        --restart-policy Never \
        --environment-variables \
            "PGHOST=${POSTGRES_HOST}" \
            "PGUSER=${PG_USER}" \
            "PGDATABASE=${POSTGRES_DATABASE}" \
            "PGSSLMODE=require" \
        --secure-environment-variables "PGPASSWORD=${PG_TOKEN}" \
        --command-line "sh -c 'psql -tAc \"select 1\"'"
}

verify_cosmos() {
    az_tsv cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --query provisioningState
}
""",
                encoding="utf-8",
        )

        errors = validate_asdw_data_verify_script(script)

        assert any("--query state" in e for e in errors)
        assert any("provisioningState" in e for e in errors)


def test_data_deploy_prompt_keeps_run_specific_evidence_in_work() -> None:
    """DataDeploy prompt はラン固有証跡を docs/src ではなく work に閉じる。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "ラン固有の再実行ログ・検証失敗理由・AC 証跡" in text
    assert "`docs/` / `src/` へ追記しない" in text
    assert "実質変更がある場合のみ更新" in text


def test_step_1_3_template_keeps_run_specific_evidence_in_work() -> None:
    """Step.1.3 テンプレートもラン固有証跡を docs/src へ追記しない。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "ラン固有の再実行ログ・verify 失敗理由・AC 証跡" in text
    assert "`docs/` / `src/` へ追記しない" in text
    assert "実質変更がある場合のみ更新" in text


def test_prompt_and_template_agree_on_work_artifact_paths() -> None:
    """DataDeploy prompt の出力契約と Step.1.3 テンプレの出力が work 成果物パスで一致する。

    片方だけ変更されると Agent が認識する出力契約が乖離するため、両者に同じ
    run スコープパスが含まれることを検証する。
    """
    prompt = _PROMPT.read_text(encoding="utf-8")
    template = _STEP_1_3.read_text(encoding="utf-8")
    for rel in (
        "work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/work-status.md",
        "work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/ac-verification.md",
    ):
        assert rel in prompt
        assert rel in template


def test_data_deploy_prompt_caps_green_retries_and_records_failure() -> None:
    """GREEN 未達時は最大5回（異なるアプローチ）で打ち切り、AC-1 ❌ を記録する契約がある。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "初回を含め最大5回" in text
    assert "tdd-green-retry-strategy" in text
    assert "前回と**異なるアプローチ**" in text
    assert "Microsoft Learn MCP" in text
    assert "実際に対象stage processを開始した後" in text
    assert "process開始前の拒否、恒久エラー" in text
    assert "追加修正・追加実行を続けず" in text
    assert "AC-1 を `❌`" in text


def test_data_deploy_prompt_stops_after_ac1_failure() -> None:
    """AC-1 ❌ 確定後は追加調査や docs/src 更新へ進まず終了する契約がある。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "AC-1 ❌ 確定後は即終了" in text
    assert "`docs/` / `src/` 更新" in text
    assert "service catalog 追記" in text
    assert "追加の `git diff` / grep / secret scan" in text
    assert "firewall 調査" in text
    assert "verify 再試行へ進まない" in text
    assert "証跡付き fail として終了" in text


def test_shared_contract_defines_hve_owned_producer_lifecycle() -> None:
    """The shared contract is the detailed producer lifecycle SSOT."""
    ownership = _markdown_section(
        _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8"),
        _HVE_PRODUCER_HEADING,
    )
    for script in _PRODUCER_SCRIPT_OUTPUTS:
        assert script in ownership, script
    for phrase in (
        "Agent session 開始前",
        "HVE",
        "3本一組",
        "current validator",
        "`reused` / `regenerated`",
        "private builder",
        "test fixture",
        "canonical base64",
        "decoded AST",
        "逆解析しない",
        "launcher は producer を生成・修復しない",
        "同一bytes",
        "validate / execute only",
        "prep → create → registration → verify",
    ):
        assert phrase in ownership, phrase


def test_shared_contract_separates_pre_session_failure_from_session_rejection() -> None:
    """Only HVE can report a failure that occurs before an Agent exists."""
    ownership = _markdown_section(
        _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8"),
        _HVE_PRODUCER_HEADING,
    )
    for phrase in (
        "pre-session generation failure",
        "Agent session を開始しない",
        "HVE が sanitized failure",
        "Step を fail",
        "Agent evidence / launcher request は存在しない",
        "launcher current-validation rejection",
    ):
        assert phrase in ownership, phrase


@pytest.mark.parametrize("path", _AGENT_DELEGATION_DOCS, ids=lambda path: path.name)
def test_prompt_and_template_delegate_hve_owned_producer_lifecycle(path: Path) -> None:
    """Agent-facing docs contain only the post-session responsibility summary."""
    ownership = _markdown_section(
        path.read_text(encoding="utf-8"),
        _HVE_PRODUCER_HEADING,
    )
    assert "asdw-data-verifier-contract.md" in ownership
    assert "producer は read-only" in ownership
    assert "read-only inspection" in ownership
    assert "証跡" in ownership
    assert "HVE-owned fixed pipeline" in ownership
    assert "launcher current-validation rejection" in ownership
    assert "producer を編集" in ownership
    assert "pre-session generation failure" not in ownership
    for phrase in ("private builder", "canonical base64", "decoded AST"):
        assert phrase not in ownership, (path, phrase)


@pytest.mark.parametrize("path", _AGENT_DELEGATION_DOCS, ids=lambda path: path.name)
def test_prompt_and_template_forbid_private_payload_reconstruction(path: Path) -> None:
    """One abstract sentence prohibits implementation and fixture reconstruction."""
    ownership = _markdown_section(
        path.read_text(encoding="utf-8"),
        _HVE_PRODUCER_HEADING,
    )
    for phrase in (
        "private implementation",
        "test fixture",
        "canonical payload",
        "参照・復元しない",
    ):
        assert phrase in ownership, (path, phrase)


def test_data_deploy_contracts_remove_agent_owned_repair_model() -> None:
    """No delegated document may retain the superseded Agent repair loop."""
    forbidden = (
        "## Producer static contract 修復（launcher 前）",
        "本 Step の producer として再生成する",
        "初回生成後に1回だけ修復して `prep` から再評価する",
        "再評価後に 2回目の static contract 不適合",
        "`data-registration-script.sh`はStep 1.3自身の生成物なので",
    )
    for path in (*_AGENT_DELEGATION_DOCS, _SHARED_NETWORK_CONTRACT):
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (path, phrase)
    assert "- ステップ1: スクリプト作成" not in _PROMPT.read_text(encoding="utf-8")
    assert "1. デプロイスクリプトの作成（" not in _STEP_1_3.read_text(encoding="utf-8")


def test_data_deploy_prompt_has_no_agent_authored_evidence_stub() -> None:
    """P11: Agent が証跡スタブを作る旧契約を prompt から除去する。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "必須証跡スタブ作成" not in text
    assert "HVE-owned evidence（Agent は作成しない）" in text


def test_step_1_3_template_has_no_agent_authored_evidence_stub() -> None:
    """P11: Agent が証跡スタブを作る旧契約を template から除去する。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "初期スタブ" not in text
    assert "HVE evidence が StageResult だけを根拠に生成する" in text
    assert "Agent はこれらを新規作成・上書き・訂正しない" in text


def test_data_deploy_docs_share_one_agent_evidence_prohibition_wording() -> None:
    """P11: Prompt / template の Agent 証跡禁止文言を一致させる。"""
    for path in _AGENT_DELEGATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "Agent はこれらを新規作成・上書き・訂正しない" in text, path


def test_step_1_3_template_allows_recorded_fail_instead_of_timeout() -> None:
    """Step.1.3 は GREEN 未達時も AC-1 ❌ 記録済み fail で終了できる。"""
    text = _STEP_1_3.read_text(encoding="utf-8")
    assert "最大5回" in text
    assert "AC-1 を `❌`" in text
    assert "証跡付き fail" in text


def test_data_deploy_agent_docs_delegate_direct_launcher_environment_contract() -> None:
    """Agent docs do not duplicate or repair an intermediate env-file schema."""
    for path in _AGENT_DELEGATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "asdw-data-verifier-contract.md" in text
        assert "sanitized launcher environment" in text
        assert "data-deploy.env" not in text, path
    shared = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")
    assert "## HVE launcher environment contract" in shared
    assert "中間 environment file" in shared


def test_step_1_2_docs_use_only_the_hve_owned_environment_snapshot() -> None:
    """Verifier producer must not preserve the removed intermediate file route.

    F-06: launcher environment 契約の本文は Prompt を単一正本とし、template は
    同名セクションへの委譲だけを持つ（逐語重複させない）。
    """
    prompt_text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "HVE Runner がsession開始前" in prompt_text
    assert "同じsanitized snapshot" in prompt_text
    assert "Agentも値のexport・補完を行わない" in prompt_text

    template_text = _STEP_1_2.read_text(encoding="utf-8")
    assert "環境変数の受領方法" in template_text
    assert (
        "Agent 仕様 `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md`"
        " の同名セクション"
    ) in template_text
    for text in (prompt_text, template_text):
        assert "data-deploy.env" not in text


def test_shared_environment_contract_declares_formal_sources_and_complete_schema() -> None:
    """Runtime reachability is explicit rather than depending on ambient guesswork."""
    text = _SHARED_NETWORK_CONTRACT.read_text(encoding="utf-8")
    for phrase in (
        "immutableなsanitized environment snapshot",
        "effective workflow parameter",
        "HVEが決定論的に導出した値",
        "外部`cli_url` runtimeではAgent sessionを開始しない",
        "`RESOURCE_GROUP`, `LOCATION`, `SUBSCRIPTION_ID`",
        "`DATA_VERIFY_ACI_IMAGE`",
        "`SQL_DB_SVC12`, `SQL_AUDIT_TABLE`",
        "`CONFIDENTIAL_LEDGER_COLLECTION`",
        "stable `src/data/sample-data.json` snapshot",
    ):
        assert phrase in text, phrase


def test_prompt_and_template_share_one_started_transient_retry_contract() -> None:
    """Retry is bounded and never repairs a pre-process contract rejection."""
    for path in (_PROMPT, _STEP_1_3):
        text = path.read_text(encoding="utf-8")
        assert "初回を含め最大5回" in text, path
        assert "実際に対象stage processを開始した後" in text, path
        assert "current-validation / launcher environment / module / run-context / predecessor marker" in text, path
        assert "process開始前の拒否" in text, path
        assert "最大3回" not in text, path


def test_data_deploy_docs_classify_hve_owned_outputs() -> None:
    """Producer lifecycle outputs と evidence outputs の両方を HVE が所有する。"""
    for path in _AGENT_DELEGATION_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "HVE-owned lifecycle outputs" in text, path
        assert "HVE-owned evidence outputs" in text, path
        assert "producer 3本はAgentの修正対象ではない" in text, path
    for contract in _PRODUCER_IO_CONTRACTS:
        text = contract.read_text(encoding="utf-8")
        assert text.count("# HVE-owned lifecycle output; Agent read-only") == 3


def test_data_deploy_prompt_requires_foreground_launcher_stages() -> None:
    """No launcher stage may be delegated to an Agent-managed background job."""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "各launcher stageは前景で完了まで待つ" in text
    assert "背景実行" not in text
    assert "バックグラウンド" not in text


def test_data_deploy_prompt_blocks_nonremediable_launcher_contract_errors() -> None:
    """Agent retries only a started transient stage, never contract/config defects."""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "current-validation / launcher environment / module / run-context" in text
    assert "即BLOCKED" in text
    assert "data-deploy.env` の変数契約補正" not in text
    assert "fixed launcher stage" in text


def test_data_deploy_final_review_never_edits_hve_owned_producers() -> None:
    """F-09: Step.1.3 は HVE-native。Agent は証跡も producer も訂正しない。"""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "HVE-owned evidenceはAgentが訂正せず" in text
    assert "producer問題も修正せずBLOCKED証跡化" in text
    assert "Agent-owned evidence" not in text
    assert "Agent-owned evidence" not in _STEP_1_3.read_text(encoding="utf-8")


def test_data_testcoding_prompt_requires_mcp_lookup_for_selected_service_counts() -> None:
    """選定store固有の件数取得手段は名称を固定せず公式情報で確認する。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "対象サービスごとのCLI / SDK / query構文はMicrosoft Learn MCPで確認" in text
    assert "存在しないサブコマンドを類推しない" in text
    assert "具体的なnetwork route、実行host、認証、temporary workload、cleanup" in text


def test_data_testcoding_prompt_requires_mcp_lookup_for_command_syntax() -> None:
    """Step.1.2 prompt は個別データストアの az CLI コマンド構文（引数名等）を
    ハードコードせず、Microsoft Learn MCP でサービスごとに個別確認するよう要求する
    （類推による引数取り違えの再発抑止）。

    2026-07-02 run 20260702T155130-4a3032 で、`az postgres flexible-server db show` の
    引数名を隣接する ADX/Kusto の `--database-name` ガイダンスへの類推混同により
    誤生成し deploy_ac_gate_failed が発生した。個別コマンドの正しい引数を prompt に
    ハードコードする方式は対象データストアの変更・CLI バージョンアップの都度追記が必要になり
    保守不能なため、HVE アプリケーション開発の順守事項として MCP でのその都度確認に
    統一する（2026-07-02 ユーザー指示）。
    """
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "類推で流用してはならない" in text
    assert "Microsoft Learn MCP で個別に確認" in text


def test_data_testcoding_prompt_prohibits_inferred_sample_counts() -> None:
    """sample-data.json に無い派生 Entity を期待件数として事実化しない契約がある。"""
    text = _TESTCODING_PROMPT.read_text(encoding="utf-8")
    assert "sample-data.json` に存在しない Entity" in text
    assert "推測で `EXPECT_*=1`" in text
    assert "ConversationTurn(派生)" in text
    assert "過去 run の生成済み `src/` 成果物" in text
    assert "GREEN 条件から外す" in text


def test_data_deploy_io_contracts_list_work_artifacts_as_top_level_outputs() -> None:
    """DataDeploy io-contract が gate 必須 work 成果物を top-level outputs として宣言する。"""
    for path in (_GENERIC_IO_CONTRACT, _STEP_IO_CONTRACT):
        text = path.read_text(encoding="utf-8")
        assert "\n- path: work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/work-status.md" in text
        assert "\n- path: work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/ac-verification.md" in text
        assert "\n  - path: work/run/<run-id>/Dev-Microservice-Azure-DataDeploy" not in text


def test_data_deploy_contracts_treat_absent_knowledge_d08_as_optional() -> None:
    """Prompt, workflow, and I/O contracts must agree that D08 is optional."""
    for path in (_GENERIC_IO_CONTRACT, _STEP_IO_CONTRACT):
        text = path.read_text(encoding="utf-8")
        expected = (
            "- path: knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md\n"
            "  required: false"
        )
        assert expected in text


def test_data_deploy_io_contracts_declare_hve_owned_scripts_as_upsert() -> None:
    """The existing/missing/regenerated lifecycle uses the existing upsert mode."""
    for contract in _PRODUCER_IO_CONTRACTS:
        text = contract.read_text(encoding="utf-8")
        for path in (
            "src/infra/azure/create-azure-data-resources-prep.sh",
            "src/infra/azure/create-azure-data-resources.sh",
            "src/data/azure/data-registration-script.sh",
        ):
            assert f"- path: {path}\n  required: true\n  mode: upsert" in text, (
                contract,
                path,
            )


def test_data_deploy_registry_declares_all_script_outputs() -> None:
    """Precheck must see the same generated scripts as the Step contract."""
    from hve.workflow_registry import get_workflow

    workflow = get_workflow("asdw-web")
    assert workflow is not None
    step = workflow.get_step("1.3")
    assert step is not None
    expected_outputs = {
        "src/infra/azure/create-azure-data-resources-prep.sh",
        "src/infra/azure/create-azure-data-resources.sh",
        "src/data/azure/data-registration-script.sh",
        "docs/azure/service-catalog.md",
    }
    assert set(step.output_paths) == expected_outputs
    assert len(step.output_paths) == len(expected_outputs)


def test_data_deploy_prompt_does_not_duplicate_non_audit_payload_implementation() -> None:
    """Remove the exact legacy payload-authoring instructions from the Agent."""
    text = _PROMPT.read_text(encoding="utf-8")
    assert "Kusto SDK（`azure-kusto-ingest` / `azure-kusto-data`）" not in text
    assert "Azure SDK 依存の wrapper と分離した plain Python helper" not in text
    assert "pip/venv のログを stdout に混ぜて" not in text
    assert "asdw-data-verifier-contract.md" in text


def test_data_deploy_prompt_and_template_keep_registration_audit_only() -> None:
    """Audit専用scriptへ非Audit Cosmos/ADX処理を戻さない。"""
    prompt = _PROMPT.read_text(encoding="utf-8")
    template = _STEP_1_3.read_text(encoding="utf-8")

    for text in (prompt, template):
        assert "AuditRecord専用" in text or "Audit専用" in text
        assert "他11エンティティ" in text
        assert "create-azure-data-resources.sh" in text
    assert "成果物 `data-registration-script.sh` の ADX 投入" not in prompt
    assert "ADX (Kusto) への投入（成果物 `data-registration-script.sh`）" not in prompt
    assert "END marker後" in prompt and "任意shell" in prompt
    assert "END marker後" in template and "任意shell" in template
