"""ASDW-WEB Step.1.2 private-aware verifier 生成契約テスト。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re

import pytest

from hve.prompt_loader import substitute_work_placeholders
from hve.template_engine import render_template
from hve.tests.asdw_data_verify_fixtures import PRIVATE_VERIFIER
from hve.workflow_registry import ASDW_WEB


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "Dev-Microservice-Azure-DataTestCoding.prompt.md"
)
_TEMPLATE = (
    _REPO_ROOT
    / ".github"
    / "prompts"
    / "steps"
    / "asdw-web"
    / "step-1.2.prompt.md"
)
_AZURE_CLI_SKILL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "azure-skills"
    / "azure-cli-deploy-scripts"
    / "SKILL.md"
)
_VERIFIER_CONTRACT = (
    _AZURE_CLI_SKILL.parent
    / "references"
    / "asdw-data-verifier-contract.md"
)
_VERIFIER_CONTRACT_LINK = "references/asdw-data-verifier-contract.md"
_VERIFIER_CONTRACT_REPO_PATH = (
    ".github/skills/azure-skills/azure-cli-deploy-scripts/"
    "references/asdw-data-verifier-contract.md"
)
_VSCODE_TASKS = _REPO_ROOT / ".vscode" / "tasks.json"
_DELEGATION_SENTENCE = (
    "Skill `azure-cli-deploy-scripts` の `"
    f"{_VERIFIER_CONTRACT_REPO_PATH}` を適用する。"
)
_FAIL_CLOSED_SENTENCE = (
    "固定 evidence schema が未定義のため、最初の Azure CLI / SDK / "
    "data-plane 呼び出しより前に `[ERROR]` を出力して非ゼロ終了する。"
)
_NO_ROUTE_ATTEMPT_SENTENCE = (
    "直接接続、一時 ACI、retry、fallback を開始しない。"
)
_STEP_1_2_RUNTIME_HEADING = "## Step 1.2 実行時必須契約"
_PROMPT_SSOT_REFERENCE = (
    "Agent 仕様 `.github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md`"
    " の同名セクション"
)
_STEP_1_2_RUNTIME_LINES = (
    "- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。",
    "- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。",
    "- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。",
)
_POSITIVE_ROUTE_ATTEMPT_RE = re.compile(
    r"(?:直接接続|一時\s*ACI|retry|再試行|fallback|フォールバック)"
    r"[^。\n]*?(?:実行する|開始する|許可する|優先する|切り?替える|切替する|"
    r"経由(?:で)?取得する)"
)
_ACI_LIFECYCLE_DETAILS = (
    "az container create",
    "az container delete",
    "aci_created",
    "aci_wait_failed",
    "aci_name",
    "aci_name_count",
    "cleanup_aci",
    "timeout 600 az container logs",
    "trap cleanup_aci EXIT INT TERM",
    "private) 直下",
    "ACI 作成",
)

_EXPECTED_NETWORK_KEYS = {
    "DATA_NETWORK_MODE",
    "DATA_VNET_NAME",
    "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
    "DATA_ACI_SUBNET_ID",
    "DATA_NAT_GATEWAY_NAME",
    "DATA_DEPLOY_IDENTITY_ID",
    "DATA_DEPLOY_IDENTITY_CLIENT_ID",
    "SQL_PRIVATE_ENDPOINT_NAME",
    "COSMOS_PRIVATE_ENDPOINT_NAME",
    "SQL_PRIVATE_DNS_ZONE",
    "COSMOS_PRIVATE_DNS_ZONE",
}
_EXPECTED_MODES = {"public", "private", "nsp", "blocked"}
_SELECTED_SQL_COVERAGE = (
    ("Member", "SQL_DB_SVC01", "members", "member_count", 1),
    ("ConsentRecord", "SQL_DB_SVC01", "consent_records", "consent_count", 2),
    ("DataRightsRequest", "SQL_DB_SVC01", "data_rights_requests", "rights_count", 3),
    ("LoyaltyAccount", "SQL_DB_SVC02", "loyalty_accounts", "loyalty_count", 4),
    ("PointTransaction", "SQL_DB_SVC02", "point_transactions", "point_count", 5),
    ("Reward", "SQL_DB_SVC03", "rewards", "reward_count", 6),
    ("RewardExchange", "SQL_DB_SVC03", "reward_exchanges", "exchange_count", 7),
    (
        "PaidMembershipContract",
        "SQL_DB_SVC07",
        "paid_membership_contracts",
        "contract_count",
        8,
    ),
    ("SupportCase", "SQL_DB_SVC09", "support_cases", "support_count", 9),
    ("CaseResolution", "SQL_DB_SVC09", "case_resolutions", "resolution_count", 10),
)
_VOC_EXPECTED_COUNT = 11
_AUDIT_EXPECTED_COUNT = 12


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _shared_contract_text() -> str:
    assert _VERIFIER_CONTRACT.is_file(), (
        "ASDW verifier network contract must have one Skill-owned SSOT: "
        f"{_VERIFIER_CONTRACT}"
    )
    return _text(_VERIFIER_CONTRACT)


def _selected_data_verifier_fixture() -> str:
    """実生成物に依存しない、選定 entity coverage 用の完全な verifier。"""
    database_keys = tuple(dict.fromkeys(row[1] for row in _SELECTED_SQL_COVERAGE))
    database_variables = {
        database: (
            ("connection", "cursor")
            if index == 0
            else (
                f"{database.removeprefix('SQL_DB_').lower()}_connection",
                f"{database.removeprefix('SQL_DB_').lower()}_cursor",
            )
        )
        for index, database in enumerate(database_keys)
    }
    lines = [
        "from mssql_python import connect",
        "from azure.identity import DefaultAzureCredential",
        "from azure.cosmos import CosmosClient",
        "import os, sys",
        'client_id = "$DATA_DEPLOY_IDENTITY_CLIENT_ID"',
    ]
    for database in database_keys:
        connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f'{connection_name} = connect("Server=$SQL_HOST;Database=${database};'
                "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;"
                'Encrypt=yes;TrustServerCertificate=no")',
                f"{cursor_name} = {connection_name}.cursor()",
            )
        )
    lines.extend(
        (
            "credential = DefaultAzureCredential(managed_identity_client_id=client_id)",
            'cosmos = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=credential)',
            'container = cosmos.get_database_client(os.environ["COSMOS_DATABASE"]).get_container_client(os.environ["COSMOS_CONTAINER_VOC"])',
            "try:",
        )
    )
    for _entity, database, table, count_name, expected in _SELECTED_SQL_COVERAGE:
        _connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f'    {cursor_name}.execute("SELECT COUNT_BIG(*) FROM [dbo].[{table}]")',
                f"    {count_name} = {cursor_name}.fetchone()[0]",
                f"    {count_name} == {expected} or sys.exit(1)",
                f"    print(int({count_name}))",
            )
        )
    lines.extend(
        (
            '    cosmos_count = list(container.query_items(query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))[0]',
            f"    cosmos_count == {_VOC_EXPECTED_COUNT} or sys.exit(1)",
            "    print(int(cosmos_count))",
            "finally:",
        )
    )
    for database in database_keys:
        connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f"    {cursor_name}.close()",
                f"    {connection_name}.close()",
            )
        )
    lines.extend(("    cosmos.close()", "    credential.close()"))
    python_source = "\n".join(lines).replace('"', r'\"')
    aci_command = (
        '                aci_command="python -m pip install mssql-python '
        "azure-identity azure-cosmos && python -c '"
        + python_source
        + "'\""
    )
    verifier = re.sub(
        r"(?m)^\s*aci_command=.*$",
        lambda _match: aci_command,
        PRIVATE_VERIFIER,
        count=1,
    )
    audit_contract = f'''\ncheck_count() {{
    local entity=$1
    local actual=$2
    local expected=$3
    if ((actual != expected)); then
        return 1
    fi
}}
audit_count="$(python -c 'from azure.confidentialledger import ConfidentialLedgerClient; from azure.identity import DefaultAzureCredential; import os; credential=DefaultAzureCredential(); client=ConfidentialLedgerClient(endpoint=os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"], credential=credential); entries=client.list_ledger_entries(collection_id=os.environ["CONFIDENTIAL_LEDGER_COLLECTION"]); print(sum(1 for _ in entries)); client.close(); credential.close()')"
check_count AuditRecord "$audit_count" {_AUDIT_EXPECTED_COUNT}
'''
    return verifier + audit_contract


def _mode_selected_data_verifier_fixture(audit_mode: str) -> str:
    """設計選定modeをACI内で実行する完全なprivate verifier fixture。"""
    assert audit_mode in {"sql-ledger-digest", "acl-direct"}
    database_keys = tuple(dict.fromkeys(row[1] for row in _SELECTED_SQL_COVERAGE))
    if audit_mode == "sql-ledger-digest":
        database_keys += ("SQL_DB_SVC12",)
    database_variables = {
        database: (
            ("connection", "cursor")
            if index == 0
            else (
                f"{database.removeprefix('SQL_DB_').lower()}_connection",
                f"{database.removeprefix('SQL_DB_').lower()}_cursor",
            )
        )
        for index, database in enumerate(database_keys)
    }
    lines = [
        "# Runtime packages: mssql-python azure-identity azure-cosmos azure-confidentialledger",
        "from contextlib import ExitStack",
        "from mssql_python import connect",
        "from azure.identity import DefaultAzureCredential",
        "from azure.cosmos import CosmosClient",
        "import os, re, sys",
    ]
    if audit_mode == "sql-ledger-digest":
        lines.append("from urllib.parse import urlparse")
    else:
        lines.extend(
            (
                "from azure.confidentialledger import ConfidentialLedgerClient",
                "from tempfile import TemporaryDirectory",
            )
        )
    lines.append('client_id = "$DATA_DEPLOY_IDENTITY_CLIENT_ID"')
    for database in database_keys:
        connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f"{connection_name} = ExitStack()",
                f"{cursor_name} = ExitStack()",
            )
        )
    lines.extend(("credential = ExitStack()", "cosmos = ExitStack()"))
    if audit_mode == "acl-direct":
        lines.extend(
            (
                "ledger_certificate_directory = ExitStack()",
                "ledger_client = ExitStack()",
            )
        )
    lines.append("try:")
    for database in database_keys:
        connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f'    {connection_name} = connect("Server=$SQL_HOST;Database=${database};'
                "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;"
                'Encrypt=yes;TrustServerCertificate=no")',
                f"    {cursor_name} = {connection_name}.cursor()",
            )
        )
    lines.extend(
        (
            "    credential = DefaultAzureCredential(managed_identity_client_id=client_id)",
            '    cosmos = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=credential)',
            '    container = cosmos.get_database_client(os.environ["COSMOS_DATABASE"]).get_container_client(os.environ["COSMOS_CONTAINER_VOC"])',
        )
    )
    if audit_mode == "acl-direct":
        lines.extend(
            (
                "    ledger_certificate_directory = TemporaryDirectory()",
                '    ledger_certificate_path = ledger_certificate_directory.name + "/ledger_certificate.pem"',
                '    ledger_client = ConfidentialLedgerClient(endpoint=os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"], credential=credential, ledger_certificate_path=ledger_certificate_path)',
            )
        )
    for _entity, database, table, count_name, expected in _SELECTED_SQL_COVERAGE:
        _connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f'    {cursor_name}.execute("SELECT COUNT_BIG(*) FROM [dbo].[{table}]")',
                f"    {count_name} = {cursor_name}.fetchone()[0]",
                f"    {count_name} == {expected} or sys.exit(1)",
                f"    print(int({count_name}))",
            )
        )
    lines.extend(
        (
            '    cosmos_count = list(container.query_items(query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))[0]',
            f"    cosmos_count == {_VOC_EXPECTED_COUNT} or sys.exit(1)",
            "    print(int(cosmos_count))",
        )
    )
    if audit_mode == "sql-ledger-digest":
        _connection_name, cursor_name = database_variables["SQL_DB_SVC12"]
        lines.extend(
            (
                '    audit_table = os.environ["SQL_AUDIT_TABLE"]',
                '    next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)]))',
                f'    {cursor_name}.execute(f"SELECT COUNT_BIG(*) FROM [dbo].[{{audit_table}}]")',
                f"    audit_count = {cursor_name}.fetchone()[0]",
                "    print(int(audit_count))",
                f"    audit_count == {_AUDIT_EXPECTED_COUNT} or sys.exit(1)",
                f'    {cursor_name}.execute("SELECT SCHEMA_NAME(schema_id), name, ledger_type_desc FROM sys.tables")',
                f"    audit_table_types = {{(str(row[0]), str(row[1])): str(row[2]) for row in {cursor_name}.fetchall()}}",
                '    audit_ledger_type = audit_table_types.get(("dbo", audit_table), "")',
                '    audit_ledger_ok = audit_ledger_type == "APPEND_ONLY_LEDGER_TABLE"',
                '    ledger_host = urlparse(os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"]).hostname',
                "    next(filter(None, [ledger_host]))",
                f'    {cursor_name}.execute("SELECT path, last_digest_block_id FROM sys.database_ledger_digest_locations WHERE is_current = 1")',
                f"    digest_rows = {cursor_name}.fetchall()",
                '    digest_ready = any((urlparse(str(row[0])).hostname == ledger_host, row[1] is not None) == (True, True) for row in digest_rows)',
                "    next(filter(None, [audit_ledger_ok]))",
                "    next(filter(None, [digest_ready]))",
            )
        )
    else:
        lines.extend(
            (
                '    audit_entries = ledger_client.list_ledger_entries(collection_id=os.environ["CONFIDENTIAL_LEDGER_COLLECTION"])',
                "    audit_count = sum(1 for _ in audit_entries)",
                "    print(int(audit_count))",
                f"    audit_count == {_AUDIT_EXPECTED_COUNT} or sys.exit(1)",
            )
        )
    lines.append("finally:")
    for database in database_keys:
        connection_name, cursor_name = database_variables[database]
        lines.extend(
            (
                f"    {cursor_name}.close()",
                f"    {connection_name}.close()",
            )
        )
    lines.extend(("    cosmos.close()",))
    if audit_mode == "acl-direct":
        lines.append("    ledger_client.close()")
    lines.append("    credential.close()")
    if audit_mode == "acl-direct":
        lines.append("    ledger_certificate_directory.cleanup()")
    python_source = "\n".join(lines).replace('"', r'\"')
    packages = "mssql-python azure-identity azure-cosmos"
    if audit_mode == "acl-direct":
        packages += " azure-confidentialledger"
    aci_command = f'                aci_command="python -m pip install {packages} && python -c \'{python_source}\'"'
    verifier = re.sub(
        r"(?m)^\s*aci_command=.*$",
        lambda _match: aci_command,
        PRIVATE_VERIFIER,
        count=1,
    )
    required_keys = [
        "SQL_HOST",
        "SQL_DB_SVC01",
        "SQL_DB_SVC02",
        "SQL_DB_SVC03",
        "SQL_DB_SVC07",
        "SQL_DB_SVC09",
        "COSMOS_ENDPOINT",
        "COSMOS_DATABASE",
        "COSMOS_CONTAINER_VOC",
        "CONFIDENTIAL_LEDGER_ENDPOINT",
    ]
    environment_keys = [
        "COSMOS_ENDPOINT",
        "COSMOS_DATABASE",
        "COSMOS_CONTAINER_VOC",
        "CONFIDENTIAL_LEDGER_ENDPOINT",
    ]
    if audit_mode == "sql-ledger-digest":
        required_keys.extend(("SQL_DB_SVC12", "SQL_AUDIT_TABLE"))
        environment_keys.append("SQL_AUDIT_TABLE")
    environment_values = (
        "".join(f'{key}="${key}" ' for key in environment_keys)
    )
    if audit_mode == "acl-direct":
        required_keys.append("CONFIDENTIAL_LEDGER_COLLECTION")
        environment_values += (
            'CONFIDENTIAL_LEDGER_COLLECTION="$CONFIDENTIAL_LEDGER_COLLECTION" '
        )
    required_lines = "".join(
        f'        : "${{{key}:?}}"\n' for key in required_keys
    )
    verifier = verifier.replace(
        '        : "${DATA_VERIFY_RUN_ID:?}"\n',
        '        : "${DATA_VERIFY_RUN_ID:?}"\n' + required_lines,
        1,
    )
    verifier = verifier.replace(
        'AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" --command-line',
        'AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" '
        + environment_values
        + "--command-line",
        1,
    )
    return verifier


def _sql_mode_verifier_with_dns_fixture() -> str:
    """SQL mode fixtureに正規SQL/Cosmos DNS preflightを追加する。"""
    verifier = _mode_selected_data_verifier_fixture("sql-ledger-digest")
    verifier = verifier.replace(
        "import os, re, sys\n",
        "import os, re, socket, sys\n",
        1,
    )
    dns_source = (
        '    sql_private_ips = set(os.environ[\\"SQL_PRIVATE_ENDPOINT_IPS\\"].split(\\",\\"))\n'
        '    sql_resolved_ips = {address[4][0] for address in socket.getaddrinfo(os.environ[\\"SQL_HOST\\"], 1433, 0, socket.SOCK_STREAM)}\n'
        "    next(iter(sql_resolved_ips))\n"
        "    next(filter(None, [sql_resolved_ips.issubset(sql_private_ips)]))\n"
        '    cosmos_host = urlparse(os.environ[\\"COSMOS_ENDPOINT\\"]).hostname\n'
        '    cosmos_private_ips = set(os.environ[\\"COSMOS_PRIVATE_ENDPOINT_IPS\\"].split(\\",\\"))\n'
        '    cosmos_resolved_ips = {address[4][0] for address in socket.getaddrinfo(cosmos_host, 443, 0, socket.SOCK_STREAM)}\n'
        "    next(iter(cosmos_resolved_ips))\n"
        "    next(filter(None, [cosmos_resolved_ips.issubset(cosmos_private_ips)]))\n"
    )
    return verifier.replace("try:\n", "try:\n" + dns_source, 1)


def _audit_design_document(audit_mode: str) -> str:
    if audit_mode == "sql-ledger-digest":
        chosen = (
            "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ "
            "Azure confidential ledger（信頼済み database digest 保管先、条件付き）"
        )
    elif audit_mode == "acl-direct":
        chosen = "Azure confidential ledger（AuditRecord を直接格納）"
    else:
        chosen = "Azure Blob Storage immutable storage"
    return "\n".join(
        (
            "# Azure data design",
            "",
            "## 1. エンティティ別ストア選定",
            "",
            "| Entity | Data characteristics（構造/更新頻度/サイズ） | Access patterns（主要クエリ/ホットパス） | Consistency（強/最終/要件根拠） | Chosen Azure service（正式名称） | Partition/Key/Index（要点） | Rationale（3〜6行） | Alternatives（最大2つ） | Evidence（根拠リンク） |",
            "|---|---|---|---|---|---|---|---|---|",
            f"| AuditRecord | 追記 | 監査 | 強整合 | {chosen} | id | 根拠 | 代替 | link |",
            "",
        )
    )


def _write_mode_selected_fixture(
    tmp_path: Path,
    verifier_mode: str,
    design_mode: str,
) -> tuple[Path, Path, Path]:
    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    verifier.write_text(
        _mode_selected_data_verifier_fixture(verifier_mode),
        encoding="utf-8",
    )
    design = tmp_path / "azure-services-data.md"
    design.write_text(_audit_design_document(design_mode), encoding="utf-8")
    return verifier, sample_data, design


def _write_selected_data_fixture(tmp_path: Path) -> tuple[Path, Path]:
    verifier = tmp_path / "verify-data-resources.sh"
    verifier.write_text(_selected_data_verifier_fixture(), encoding="utf-8")
    sample_data = tmp_path / "sample-data.json"
    entities = {
        entity: [
            {"id": f"fixture-{entity}-{index}"}
            for index in range(expected)
        ]
        for entity, *_rest, expected in _SELECTED_SQL_COVERAGE
    }
    entities.update(
        {
            "VocRecord": [
                {"id": f"fixture-voc-{index}"}
                for index in range(_VOC_EXPECTED_COUNT)
            ],
            "AuditRecord": [
                {"id": f"fixture-audit-{index}"}
                for index in range(_AUDIT_EXPECTED_COUNT)
            ],
        }
    )
    sample_data.write_text(
        json.dumps({"entities": entities}, ensure_ascii=False),
        encoding="utf-8",
    )
    return verifier, sample_data


def _without_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?(?:-->|$)", "", text, flags=re.DOTALL)


def _without_preformatted_html(text: str) -> str:
    return re.sub(r"(?is)<pre(?:\s[^>]*)?>.*?(?:</pre\s*>|$)", "", text)


def _without_markdown_fences(text: str) -> str:
    visible: list[str] = []
    fence_char = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        if fence_char:
            closing = re.fullmatch(
                rf" {{0,3}}({re.escape(fence_char)}{{{fence_length},}})[ \t]*(?:\r?\n)?",
                line,
            )
            if closing:
                fence_char = ""
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opening:
            marker = opening.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            continue
        visible.append(line)
    return "".join(visible)


def _assert_data_testcoding_raw_log_and_view_contract(
    text: str,
    source: object,
) -> None:
    visible_text = _without_markdown_fences(
        _without_preformatted_html(_without_html_comments(text))
    )
    assert not re.search(
        r"(?:規範|契約|以下の3行)[^。\n]{0,60}(?:適用しない|無効|従わない|例示のみ|無視する)",
        visible_text,
    ), source
    visible_lines = visible_text.splitlines()
    heading_indexes = [
        index
        for index, line in enumerate(visible_lines)
        if line == _STEP_1_2_RUNTIME_HEADING
    ]
    assert len(heading_indexes) == 1, source
    section_start = heading_indexes[0] + 1
    assert visible_lines[section_start : section_start + 4] == [
        "",
        *_STEP_1_2_RUNTIME_LINES,
    ], source


def _mode_contract(text: str, mode: str, next_mode: str) -> str:
    section = _network_contract(text)
    return section.split(f"### `{mode}` mode", 1)[1].split(
        f"### `{next_mode}` mode", 1
    )[0]


def _network_contract(text: str) -> str:
    text = _without_html_comments(text)
    start = "## HVE launcher environment contract"
    assert start in text, f"missing network contract heading: {start}"
    section = text.split(start, 1)[1]
    next_heading = re.search(r"^## (?!#)", section, re.MULTILINE)
    return section if next_heading is None else section[: next_heading.start()]


def _private_contract(text: str) -> str:
    return _network_contract(text).split(
        "### `private` mode", 1
    )[1].split("### `nsp` mode", 1)[0]


def _private_steps(text: str) -> dict[int, str]:
    private = _private_contract(text)
    headings = list(re.finditer(r"^([1-4])\. \*\*.+?\*\*:", private, re.MULTILINE))
    assert [int(match.group(1)) for match in headings] == [1, 2, 3, 4]
    return {
        int(match.group(1)): private[
            match.start() : headings[index + 1].start()
            if index + 1 < len(headings)
            else len(private)
        ]
        for index, match in enumerate(headings)
    }


def test_prompt_and_template_declare_the_exact_network_key_contract() -> None:
    skill = _without_html_comments(_text(_AZURE_CLI_SKILL))
    assert skill.count(f"]({_VERIFIER_CONTRACT_LINK})") == 1
    assert "## HVE launcher environment contract" not in skill
    assert not (_EXPECTED_NETWORK_KEYS & set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", skill)))
    text = _shared_contract_text()
    section = _network_contract(text)
    private = _private_contract(text)
    declared = re.findall(
        r"^- `([A-Z][A-Z0-9_]+)`$", section, re.MULTILINE
    )
    assert set(declared) == _EXPECTED_NETWORK_KEYS
    assert len(declared) == len(_EXPECTED_NETWORK_KEYS)
    assert "全キーを実際に参照" in section
    assert "未使用キー" in section
    assert "HVE Runnerがsession開始前に構築したimmutableなsanitized environment snapshot" in section
    assert "effective workflow parameter" in section
    assert "HVEが決定論的に導出した値" in section
    assert "verifier 自身は `source` / `.`" in section
    assert "launcher環境入力の受領" in section
    assert "中間 environment file を読み込まず" in section
    assert "`aci_created=0` を `trap` 前に初期化" in section
    assert "az container list" in private
    assert "aci_name_count" in private
    assert "厳密に `0`" in private
    assert "`az container show` の非ゼロ" in private
    assert "実行した**直後**に `aci_created=1`" in section
    assert '--name "$aci_name" --yes || true' in section
    consumption_phrases = {
        "DATA_NETWORK_MODE": "`DATA_NETWORK_MODE=private`",
        "DATA_VNET_NAME": "`DATA_VNET_NAME` の実在",
        "DATA_PRIVATE_ENDPOINT_SUBNET_ID": (
            "各 Private Endpoint の subnet ID が "
            "`DATA_PRIVATE_ENDPOINT_SUBNET_ID` と一致"
        ),
        "DATA_ACI_SUBNET_ID": '--subnet "$DATA_ACI_SUBNET_ID"',
        "DATA_NAT_GATEWAY_NAME": (
            "関連付く NAT Gateway 名が `DATA_NAT_GATEWAY_NAME` と一致"
        ),
        "DATA_DEPLOY_IDENTITY_ID": '--assign-identity "$DATA_DEPLOY_IDENTITY_ID"',
        "DATA_DEPLOY_IDENTITY_CLIENT_ID": (
            "その client ID が `DATA_DEPLOY_IDENTITY_CLIENT_ID` と一致"
        ),
        "SQL_PRIVATE_ENDPOINT_NAME": (
            "`SQL_PRIVATE_ENDPOINT_NAME` / `COSMOS_PRIVATE_ENDPOINT_NAME` "
            "の Private Endpoint connection state"
        ),
        "COSMOS_PRIVATE_ENDPOINT_NAME": (
            "`SQL_PRIVATE_ENDPOINT_NAME` / `COSMOS_PRIVATE_ENDPOINT_NAME` "
            "の Private Endpoint connection state"
        ),
        "SQL_PRIVATE_DNS_ZONE": (
            "`SQL_PRIVATE_DNS_ZONE` / `COSMOS_PRIVATE_DNS_ZONE` の "
            "Private DNS zone"
        ),
        "COSMOS_PRIVATE_DNS_ZONE": (
            "`SQL_PRIVATE_DNS_ZONE` / `COSMOS_PRIVATE_DNS_ZONE` の "
            "Private DNS zone"
        ),
    }
    for key, phrase in consumption_phrases.items():
        assert phrase in section, key


def test_prompt_and_template_reference_skill_contract_without_copying_it() -> None:
    """F-06: Skill contract への委譲文は Prompt を単一正本とし template へ複製しない。"""
    prompt_raw = _text(_PROMPT)
    assert _without_html_comments(prompt_raw).count(_DELEGATION_SENTENCE) == 1
    assert prompt_raw.count(_DELEGATION_SENTENCE) == 1

    template_raw = _text(_TEMPLATE)
    assert _DELEGATION_SENTENCE not in template_raw
    assert "ASDW data network contract" in template_raw
    assert _PROMPT_SSOT_REFERENCE in template_raw

    for path in (_PROMPT, _TEMPLATE):
        raw_text = _text(path)
        assert "## HVE launcher environment contract" not in raw_text, path
        assert not (
            _EXPECTED_NETWORK_KEYS
            & set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", raw_text))
        ), path
        for detail in _ACI_LIFECYCLE_DETAILS:
            assert detail not in raw_text, (path, detail)


def test_html_comment_only_network_contract_is_not_accepted() -> None:
    commented_contract = """<!--
## HVE launcher environment contract
- `DATA_NETWORK_MODE`
### `private` mode
-->
"""

    with pytest.raises(AssertionError, match="missing network contract heading"):
        _network_contract(commented_contract)


def test_prompt_and_template_require_all_four_modes_without_implicit_fallback() -> None:
    text = _shared_contract_text()
    section = _network_contract(text)
    modes = re.findall(r"^### `([a-z]+)` mode$", section, re.MULTILINE)
    assert modes == ["public", "private", "nsp", "blocked"]
    assert set(modes) == _EXPECTED_MODES
    assert all(modes.count(mode) == 1 for mode in _EXPECTED_MODES)
    assert "別 mode への黙示 fallback" in section
    assert "public endpoint へ fallback" in section
    assert 'case "${DATA_NETWORK_MODE:?}" in' in section
    assert "`${DATA_NETWORK_MODE:-}`" in section
    assert "`public)`、`private)`、`nsp)`、`blocked)`" in section
    assert "4 mode間の相対順序は規定しない" in section
    assert "最後の`*)`" in section
    assert "未知値・空値をcase後へfall-throughさせない" in section
    public = _mode_contract(text, "public", "private")
    nsp = _mode_contract(text, "nsp", "blocked")
    for mode_contract in (public, nsp):
        assert _FAIL_CLOSED_SENTENCE in mode_contract
        assert _NO_ROUTE_ATTEMPT_SENTENCE in mode_contract
        assert _POSITIVE_ROUTE_ATTEMPT_RE.search(mode_contract) is None


def test_private_mode_verifies_topology_read_only_before_data_plane_checks() -> None:
    text = _shared_contract_text()
    private = _private_contract(text)
    steps = _private_steps(text)
    required = (
        "DATA_VNET_NAME",
        "DATA_PRIVATE_ENDPOINT_SUBNET_ID",
        "DATA_ACI_SUBNET_ID",
        "DATA_NAT_GATEWAY_NAME",
        "DATA_DEPLOY_IDENTITY_ID",
        "DATA_DEPLOY_IDENTITY_CLIENT_ID",
        "SQL_PRIVATE_ENDPOINT_NAME",
        "COSMOS_PRIVATE_ENDPOINT_NAME",
        "SQL_PRIVATE_DNS_ZONE",
        "COSMOS_PRIVATE_DNS_ZONE",
        "read-only",
        "Private Endpoint connection state",
        "Private DNS",
        "VNet link",
        "NAT Gateway",
        "`private)` 直下の直列文",
        "許容する関数定義は `cleanup_aci` だけ",
        "未呼出helper",
        "動的command名",
    )
    for phrase in required:
        assert phrase in private, phrase
    assert "`set -euo pipefail`" in private
    assert "host側の実行文は" in private
    assert "`;` / `&&` / `||` / `&`" in private
    assert "true branch を直接の `exit 1`" in private
    assert "データプレーン検証より前" in private
    assert all("az container create" not in steps[number] for number in (1, 2, 3))
    assert "show` / `list" in steps[3]
    for key in _EXPECTED_NETWORK_KEYS | {"DATA_VERIFY_ACI_IMAGE"}:
        assert key in steps[2], key


def test_private_mode_uses_vnet_aci_and_user_assigned_identity() -> None:
    text = _shared_contract_text()
    private = _private_contract(text)
    aci_step = _private_steps(text)[4]
    expected_create = (
        'az container create --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --image "$DATA_VERIFY_ACI_IMAGE" '
        '--subnet "$DATA_ACI_SUBNET_ID" '
        '--acr-identity "$DATA_DEPLOY_IDENTITY_ID" '
        '--assign-identity "$DATA_DEPLOY_IDENTITY_ID" '
        '--restart-policy Never --os-type Linux --cpu 1 --memory 1 '
        '--command-line "$aci_command"'
    )
    expected_delete = (
        'az container delete --resource-group "$RESOURCE_GROUP" '
        '--name "$aci_name" --yes'
    )
    assert private.count("az container delete") == 1
    assert expected_create in aci_step
    assert expected_delete in aci_step
    assert '`aci_name="verify-data-$DATA_VERIFY_RUN_ID"' in aci_step
    assert "`--tags hveVerifyRunId=\"$DATA_VERIFY_RUN_ID\"`" in aci_step
    assert "ACI 作成前に同名のACIが存在したら非ゼロ終了" in aci_step
    assert "create失敗または応答不明時にはフラグを立てず、既存ACIを削除してはならない" in aci_step
    assert "`aci_wait_failed=0`" in private
    assert "aci_wait_failed=1" in private
    assert "`actual == expected or sys.exit(1)`" in aci_step
    assert "`assert`、`PYTHONOPTIMIZE`、`python -O` / `-OO` を用いてはならない" in aci_step
    assert "秘密を含まない `aci_command`" in aci_step
    assert "VNet内の検証workload" not in aci_step
    assert "検証 ACI の作成と cleanup は verifier が所有" in aci_step
    assert "DefaultAzureCredential" in private
    assert (
        "ローカル端末から SQL / Cosmos / Azure confidential ledger の "
        "data-plane へ直接接続しない"
    ) in private
    assert (
        "public endpoint / firewall rule / 共有キー / SAS / "
        "秘密を含む接続文字列 / 長期 token への fallback を禁止する"
        in private
    )
    assert "DATA_VERIFY_ACI_IMAGE" in private
    assert "mssql-python" in private
    expected_sql_auth = (
        "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;"
        "Authentication=ActiveDirectoryMSI;Encrypt=yes;"
        "TrustServerCertificate=no"
    )
    assert expected_sql_auth in private
    assert not re.search(
        r"\b(?:uid|user id)=(?!\$DATA_DEPLOY_IDENTITY_CLIENT_ID(?:;|\b))",
        private,
        re.IGNORECASE,
    )
    assert not re.search(r"\b(?:pwd|password)=", private, re.IGNORECASE)
    assert "azure-cosmos" in private
    expected_cosmos_auth = (
        "credential = DefaultAzureCredential(managed_identity_client_id="
        "DATA_DEPLOY_IDENTITY_CLIENT_ID); client = CosmosClient(endpoint, "
        "credential=credential)"
    )
    assert expected_cosmos_auth in private
    assert not re.search(r"CosmosClient\([^\n)]*credential=(?!credential\))", private)
    assert "ODBC版 `sqlcmd -G`" in private
    assert "禁止" in private
    assert "`cleanup_aci` は `aci_created` が `1` の場合だけ" in aci_step
    assert "`trap cleanup_aci EXIT INT TERM`" in aci_step
    assert "ACI 作成**前**に `trap cleanup_aci EXIT INT TERM`" in aci_step
    assert "`aci_created=0` を `trap` 前に初期化" in aci_step
    assert "実行した**直後**に `aci_created=1`" in aci_step
    assert "--yes || true" in aci_step
    assert "timeout 600 az container logs" in private
    assert "無制限の`--follow`" in private
    assert "Start-Sleep" in private
    assert "GNU coreutils の `timeout`" in text
    assert "`command -v timeout`" in text
    assert "`^[0-9a-f]{32}$`" in private
    assert "最初の Azure CLI 呼び出しより前" in private
    assert "全 SQL cursor / connection" in aci_step
    assert "CosmosClient / DefaultAzureCredential" in aci_step
    assert "`close()`" in aci_step
    assert "ACI 作成、`aci_created=1`、`aci_wait_failed=0`、終了待機、終了コード取得、結果判定" in private


def test_shared_contract_declares_two_design_selected_audit_storage_modes() -> None:
    private = _private_contract(_shared_contract_text())
    audit = private.split("#### AuditRecord storage mode contract", 1)[1]

    assert "`Entity`列と`Chosen Azure service`列だけを読む単一resolver" in audit
    for exact_one in (
        "`## 1. エンティティ別ストア選定`見出しとその直下の表",
        "表内の`Entity`列",
        "`Chosen Azure service`列",
        "`Entity`値が`AuditRecord`と完全一致する行",
    ):
        assert exact_one in audit
    assert "それぞれ厳密に1件" in audit
    assert "0件または複数件は`blocked`" in audit
    for ignored_column in ("`Alternatives`", "`Rationale`", "`Evidence`"):
        assert ignored_column in audit
    assert "別表の`AuditRecord の整合性証明`はmode判定に使用しない" in audit
    accepted_modes = audit.split("受理するmodeは次の2つだけ", 1)[1]
    modes = re.findall(r"^- `([^`]+)`:", accepted_modes, re.MULTILINE)
    assert modes == ["sql-ledger-digest", "acl-direct"]
    assert "Step 1.2とStep 1.3は同じresolverを使用" in audit
    assert "Step 1.3は最初のAzure writeより前" in audit
    assert "入力verifierが現在のmodeに適合" in audit
    assert "不一致またはstaleなら最初のwrite前に`blocked`" in audit
    assert "別ファイルまたは環境変数へmodeを複製しない" in audit
    assert "direct modeへの既定fallbackは禁止" in audit
    assert "未知方式" in audit
    assert "両方式に一致する曖昧な記述" in audit


def test_shared_contract_separates_sql_payload_from_digest_storage() -> None:
    private = _private_contract(_shared_contract_text())
    audit = private.split("#### AuditRecord storage mode contract", 1)[1]
    sql_mode = audit.split("- `sql-ledger-digest`:", 1)[1].split(
        "- `acl-direct`:", 1
    )[0]
    direct_mode = audit.split("- `acl-direct`:", 1)[1]

    for requirement in (
        "`SQL_DB_SVC12`",
        "`dbo.${SQL_AUDIT_TABLE}`",
        "`APPEND_ONLY_LEDGER_TABLE`",
        "`sys.database_ledger_digest_locations`",
        "`CONFIDENTIAL_LEDGER_ENDPOINT`",
        "`last_digest_block_id`",
        "最初のAzure create / update / data-plane writeより前",
        "read-onlyでpreflight",
        "一切writeせず`blocked`",
        "存在しない場合だけpreflight成功後",
        "`AuditRecord`業務ペイロードはSQL tableだけへ登録",
    ):
        assert requirement in sql_mode
    assert "直接登録・同期してはならない" in sql_mode
    assert "`CONFIDENTIAL_LEDGER_COLLECTION`" in direct_mode
    assert "専用collection IDの正本キー" in direct_mode
    assert "両Stepは呼出し側からexportされた同じ非空値をconsume" in direct_mode
    assert "暗黙の既定値" in direct_mode
    assert "別collectionへのfallback" in direct_mode
    assert "verifier-owned private ACI内" in direct_mode
    assert "同じUser-assigned Managed Identity" in direct_mode
    assert "対象専用collection" in direct_mode
    assert "application entriesを実際に列挙・集計" in direct_mode
    assert "同じ`finally`で`close()`" in direct_mode
    assert "`SQL_DB_SVC12`または`SQL_AUDIT_TABLE`を必須にしない" in direct_mode


def test_shared_contract_defines_mode_selected_registration_aci() -> None:
    text = _shared_contract_text()
    section = text.split("#### Step 1.3 AuditRecord registration contract", 1)[1]
    for requirement in (
        "`DATA_REGISTER_ACI_IMAGE`等の同義キーを追加せず",
        "`DATA_VERIFY_ACI_IMAGE`を登録ACIの`--image`にも使用",
        "`DATA_REGISTER_RUN_ID`",
        "`AUDIT_RECORD_JSON`",
        "`--secure-environment-variables`",
        '空白なしの`NAME="$SOURCE"`',
        "`isinstance(audit, dict)`",
        '`isinstance(audit["auditEventId"], str)`',
        '`audit_id = audit["auditEventId"].strip()`',
        "parameterized実行",
        "`begin_create_ledger_entry(...).result()`を厳密に1回",
    ):
        assert requirement in section
    assert "DATA_REGISTER_ACI_IMAGE" not in section.split("`DATA_REGISTER_ACI_IMAGE`等", 1)[1]


def test_private_mode_forbids_local_confidential_ledger_data_plane_access() -> None:
    private = _private_contract(_shared_contract_text())

    assert (
        "ローカル端末から SQL / Cosmos / Azure confidential ledger の "
        "data-plane へ直接接続しない"
    ) in private


def test_prompt_and_template_require_complete_selected_entity_coverage_and_raw_log() -> None:
    required_entities = (
        "Member",
        "ConsentRecord",
        "DataRightsRequest",
        "LoyaltyAccount",
        "PointTransaction",
        "Reward",
        "RewardExchange",
        "PaidMembershipContract",
        "SupportCase",
        "CaseResolution",
        "VocRecord",
        "AuditRecord",
    )
    prompt_text = _text(_PROMPT)
    for entity in required_entities:
        assert entity in prompt_text, entity
    assert "対象エンティティ集合を過不足なく" in prompt_text

    # F-06: entity 列挙は Prompt を単一正本とし、template は委譲だけを持つ。
    template_text = _text(_TEMPLATE)
    assert "AuditRecord" not in template_text
    assert "対象エンティティ集合" in template_text
    assert _PROMPT_SSOT_REFERENCE in template_text

    for path in (_PROMPT, _TEMPLATE):
        text = _text(path)
        assert "static-verification.log" in text, path
        assert "Raw-Log-Path" in text, path
        assert "Azure CLI / REST / live commandを実行していない" in text, path


@pytest.mark.parametrize(
    "path",
    (_PROMPT, _TEMPLATE),
    ids=("prompt", "template"),
)
def test_prompt_and_template_require_canonical_raw_log_focused_gate_and_view_hygiene(
    path: Path,
) -> None:
    _assert_data_testcoding_raw_log_and_view_contract(_text(path), path)
    if path == _TEMPLATE:
        text = _text(path)
        start = next(
            line
            for line in text.splitlines()
            if "static-verification.log" in line
            and "Raw-Log-Path" in line
            and "`N/A`を記録しない" in line
        )
        required_block = (
            f"{start}\n\n"
            f"{_STEP_1_2_RUNTIME_HEADING}\n\n"
            + "\n".join(_STEP_1_2_RUNTIME_LINES)
            + "\n\n"
            "{completion_instruction}"
        )
        assert required_block in text, path


def test_data_testcoding_prompt_checks_optional_knowledge_before_reading() -> None:
    """Optional knowledge must not be read in the same speculative tool batch."""
    text = _text(_PROMPT)

    assert "任意の`knowledge/`ファイルは存在確認の成功結果を受け取った後" in text
    assert "次のツール呼び出しでのみreadする" in text
    assert "未検出ならreadを発行せずskipする" in text


def test_data_testcoding_prompt_resolves_wildcards_before_ripgrep() -> None:
    """Wildcard expressions are glob inputs, never literal ripgrep search paths."""
    text = _text(_PROMPT)

    assert "wildcardを`rg`のpaths引数へそのまま渡さない" in text
    assert "glob結果の実在する完全パスだけを`rg`へ渡す" in text


def test_prompt_forbids_ending_turn_without_red_artifacts() -> None:
    """Step 1.2 プロンプトは必須成果物未生成での終了・非対話での確認質問終了を禁止する。

    deploy 系プロンプトの `ac-verification.md` 未生成終了禁止と対称の契約。
    """
    text = _text(_PROMPT)
    # 必須成果物未生成での終了禁止（BLOCKED/FAIL 記録で必ず生成）
    assert "必須成果物未生成での終了禁止" in text
    assert "Evidence-Status: BLOCKED" in text
    assert "TDD-Judgement: FAIL" in text
    # 非対話での確認質問による停止禁止。ただし §4 依存停止は正当な hard-stop で対象外
    assert "非対話オーケストレーションでの確認質問による停止禁止" in text
    assert "§4 の依存確認による停止" in text
    assert "本項の対象外" in text
    # 既存 verifier 安定読取不能時は際限のない適合監査を続けず再生成する
    assert "既存 verifier の適合監査でのターン浪費禁止" in text


def test_template_completion_and_output_section_cover_red_report_and_log() -> None:
    """テンプレートの完了条件と `## 出力` が RED レポート/ログを実効カバーする。

    ローカル実行の `{completion_instruction}`（「上記の出力ファイルが全て正常に
    生成されていることを確認」）は `## 出力` 列挙を自己完了チェック対象にするため、
    RED レポートとログが `## 出力` に列挙されていることを固定する。
    """
    text = _text(_TEMPLATE)
    # 完了条件のミラー行（未生成での終了禁止）
    assert "作成しないままターンを終えない" in text
    # `## 出力` セクションに RED レポート/ログが列挙されていること
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "## 出力")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    output_section = "\n".join(lines[start:end])
    assert "tdd-test-report.md" in output_section
    assert "static-verification.log" in output_section


def test_prompt_and_template_front_load_mandatory_outputs_before_manual_audit() -> None:
    """RED 成果物を手読み監査より前に確定させる「出力前倒し」規則を固定する。

    既存 verifier を逐次手読みで精査するのに複数ターンを費やすと、その間の
    モデル/SDK 側ターン終了（リテラルツール呼び出し等）で 0-written となり gate が
    失敗する。機械検証（bash -n / artifact validator / LF・BOM）→ static-verification.log →
    tdd-test-report.md の順で必須成果物を早期確定する契約を prompt/template で固定する。
    """
    prompt_text = _text(_PROMPT)
    assert "出力の前倒し" in prompt_text
    assert "逐次手読みでの網羅精査に複数ターンを費やさず" in prompt_text
    assert "追加の手読みレビュー・網羅監査は必須成果物の作成後にのみ行う" in prompt_text

    template_text = _text(_TEMPLATE)
    assert "出力前倒し" in template_text
    assert "逐次手読み" in template_text
    assert "追加の手読みレビューより前に" in template_text


def test_step_1_2_render_and_agent_prompt_deliver_runtime_contract_context() -> None:
    run_id = "20260720T000000-contract"
    rendered = render_template(
        ".github/prompts/steps/asdw-web/step-1.2.prompt.md",
        0,
        {"app_ids": ["APP-009"]},
        ASDW_WEB,
        execution_mode="local",
    )
    agent_prompt = substitute_work_placeholders(
        _text(_PROMPT),
        run_id=run_id,
        identifier="0",
    )
    injected = f"{agent_prompt}\n\n{rendered}"

    assert injected.count(_STEP_1_2_RUNTIME_HEADING) == 2
    assert "APP-ID: `APP-009`" in injected
    assert (
        f"tests/run/{run_id}/asdw-web/step-1-2/<target-app-id>/RED/"
        "static-verification.log"
    ) in agent_prompt
    assert "<run-id>" not in agent_prompt
    assert "{app_id_section}" not in injected


def test_prompt_declares_the_three_state_evidence_contract() -> None:
    """Sub-016 / F-06: 3 状態証跡ラベルの判定規則は Prompt を単一正本とする。"""
    text = _text(_PROMPT)
    for token in (
        "Artifact-Contract-Status",
        "Live-RED-Status",
        "Focused-Regression-Status",
        "EXPECTED_FAIL",
        "Live-RED-Status: NOT_RUN",
        "Focused-Regression-Status: FAIL",
        "machine-verification.log",
        "live Azure verifier を実行していない",
        "単一 PASS へ畳み込ま",
    ):
        assert token in text, token


def test_template_keeps_step_scoped_three_state_values_and_delegates_rules() -> None:
    """F-06: template は Step 固有値だけを持ち、判定規則と固定スキーマを Prompt へ委譲する。

    live Azure verifier を実行しないという Step 1.2 固有の帰結（`NOT_RUN`）は
    template に残し、3 状態ラベルの取り得る値・machine log 整合・畳み込み禁止等の
    Agent 振る舞い規定と固定レポートスキーマは Prompt を正本として逐語重複させない。
    """
    text = _text(_TEMPLATE)
    assert "- Live-RED-Status: NOT_RUN" in text
    assert _PROMPT_SSOT_REFERENCE in text

    # 汎用ラベル定義・固定スキーマは Prompt 側が正本として保持する。
    prompt_text = _text(_PROMPT)
    for label in (
        "Artifact-Contract-Status",
        "Live-RED-Status",
        "Focused-Regression-Status",
        "EXPECTED_FAIL",
        "- Schema-Version: 1",
        "## Test Protection",
    ):
        assert label in prompt_text, label
        if label != "Live-RED-Status":
            assert label not in text, label

    for duplicated in (
        "machine-verification.log",
        "単一 PASS へ畳み込ま",
        "static contract の PASS を live RED 実行として偽ら",
    ):
        assert duplicated not in text, duplicated


@pytest.mark.parametrize(
    "invalid_text",
    (
        """
- `Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを使用しなくてよい。`\\`区切りを書いてもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を含めない。
- `read_file` / view の大きい範囲を指定し、`view_range out of bounds`時も再取得せず同じ範囲を繰り返す。
""",
        """
    以下の規範は適用しない（禁止例）。

    ## Step 1.2 実行時必須契約

    - 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
    - focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
    - `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
    """,
        """
    前置き: ## Step 1.2 実行時必須契約

    - 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
    - focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
    - `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
    """,
        """
        ## Step 1.2 実行時必須契約

        - 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
        - focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
        - `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
    """,
        "## Step 1.2 実行時必須契約\n\n"
        "- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。\n\n"
        "- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。\n"
        "- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。\n",
        (
            "## Step 1.2 実行時必須契約\n\n"
            "- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。<TRAILING_SPACE>\n"
            "- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。\n"
            "- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。\n"
        ).replace("<TRAILING_SPACE>", " "),
        """<!--
    ## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
-->
""",
        """<!--
    ## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
""",
    """
以下の3行は例示であり、実行時には従わない。

## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
""",
    """```markdown
## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
```
""",
    """```markdown
## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
````
""",
    """~~~markdown
## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
~~~~
""",
    """```markdown
## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
""",
    """<pre>
## Step 1.2 実行時必須契約

- 生成する`Raw-Log-Path`は、Windows環境でもrepository-relativeの`/`区切りを必ず使用し、`\\`区切りを書かないこと。値は単一のバッククォート1組で囲んでもよい。
- focused pytestには`hve/tests/test_runner_tdd_report_gate.py`を必ず含める。
- `read_file` / view の行範囲は実在行数が不明なまま大きく指定しないこと。`view_range out of bounds`時は見出し検索または小範囲で再取得し、同じ範囲を繰り返さないこと。
</pre>
""",
    ),
    ids=(
        "negated-lines",
        "negating-wrapper",
        "example-wrapper",
        "inline-heading",
        "indented-code",
        "blank-between-lines",
        "trailing-space",
        "closed-comment",
        "unclosed-comment",
        "fenced-code",
        "longer-backtick-closing-fence",
        "longer-tilde-closing-fence",
        "unclosed-fence",
        "preformatted-html",
    ),
)
def test_data_testcoding_contract_rejects_negated_or_commented_requirements(
    invalid_text: str,
) -> None:
    with pytest.raises(AssertionError):
        _assert_data_testcoding_raw_log_and_view_contract(
            invalid_text,
            "adversarial fixture",
        )


def test_vscode_artifact_validator_task_uses_runner_equivalent_inputs() -> None:
    tasks = json.loads(_text(_VSCODE_TASKS))
    matching = [
        task
        for task in tasks.get("tasks", [])
        if task.get("label") == "T09 Verify artifact contract"
    ]
    assert len(matching) == 1
    arguments = matching[0].get("args", [])
    assert len(arguments) == 2
    assert arguments[0] == "-c"
    command = arguments[1]
    program = ast.parse(command)
    calls = [
        node
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_asdw_data_verify_script"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 1
    assert isinstance(call.args[0], ast.Constant)
    assert call.args[0].value == "src/infra/azure/verify-data-resources.sh"
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    assert set(keywords) == {
        "design_doc_path",
        "private_capability_required",
        "sample_data_path",
    }
    assert isinstance(keywords["design_doc_path"], ast.Constant)
    assert keywords["design_doc_path"].value == "docs/azure/azure-services-data.md"
    assert isinstance(keywords["private_capability_required"], ast.Constant)
    assert keywords["private_capability_required"].value is True
    assert isinstance(keywords["sample_data_path"], ast.Constant)
    assert keywords["sample_data_path"].value == "src/data/sample-data.json"


def test_selected_data_validator_accepts_self_contained_fixture(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)

    assert validate_asdw_data_verify_script(
        verifier,
        private_capability_required=True,
        sample_data_path=sample_data,
    ) == []


@pytest.mark.parametrize(
    "mode",
    ("sql-ledger-digest", "acl-direct"),
)
def test_public_validator_accepts_verifier_matching_selected_audit_mode(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )

    assert validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    ) == []


@pytest.mark.parametrize(
    ("verifier_mode", "design_mode", "expected_fragment"),
    (
        ("acl-direct", "sql-ledger-digest", "$SQL_DB_SVC12"),
        (
            "sql-ledger-digest",
            "acl-direct",
            "$CONFIDENTIAL_LEDGER_COLLECTION",
        ),
    ),
)
def test_public_validator_rejects_verifier_for_other_audit_mode(
    tmp_path: Path,
    verifier_mode: str,
    design_mode: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=verifier_mode,
        design_mode=design_mode,
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


def test_public_validator_resolves_mode_even_without_optional_sample_data(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, _sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="unknown",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=None,
    )

    assert any(
        "AuditRecord Chosen Azure service uses an unknown storage mode" in error
        for error in errors
    ), errors


def test_public_validator_rejects_host_side_acl_count_for_direct_mode(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    design = tmp_path / "azure-services-data.md"
    design.write_text(_audit_design_document("acl-direct"), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("CONFIDENTIAL_LEDGER_COLLECTION" in error for error in errors), errors


@pytest.mark.parametrize(
    ("old", "new", "expected_fragment"),
    (
        (
            "try:\n",
            "sys.exit(0)\ntry:\n",
            "only imports and direct initializations",
        ),
        (
            "    ledger_certificate_directory.cleanup()'\"",
            "    ledger_certificate_directory.cleanup()\n    sys.exit(0)'\"",
            "same direct finally block",
        ),
        (
            "    print(int(audit_count))",
            "    audit_count = 12\n    print(int(audit_count))",
            "reassign the executed entry count",
        ),
        (
            "    audit_entries = ledger_client.list_ledger_entries",
            "    ledger_client = ledger_client\n"
            "    audit_entries = ledger_client.list_ledger_entries",
            "reassign its ledger client",
        ),
        (
            "    ledger_client = ConfidentialLedgerClient",
            "    credential = credential\n"
            "    ledger_client = ConfidentialLedgerClient",
            "protected runtime",
        ),
    ),
)
def test_public_validator_rejects_acl_direct_bypass_mutations(
    tmp_path: Path,
    old: str,
    new: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    assert old in text
    verifier.write_text(text.replace(old, new, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


@pytest.mark.parametrize(
    "replacement",
    (
        "    ledger_certificate_directory.cleanup()\n"
        "    ledger_client.close()\n"
        "    credential.close()",
        "    ledger_client.close()\n"
        "    ledger_certificate_directory.cleanup()\n"
        "    credential.close()",
    ),
)
def test_public_validator_rejects_early_acl_tls_certificate_cleanup(
    tmp_path: Path,
    replacement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    canonical = (
        "    ledger_client.close()\n"
        "    credential.close()\n"
        "    ledger_certificate_directory.cleanup()"
    )
    assert canonical in text
    verifier.write_text(text.replace(canonical, replacement, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("ledger TLS certificate" in error for error in errors), errors


def test_public_validator_rejects_duplicate_acl_client_in_dead_function(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    text = text.replace(
        "try:\n",
        "def dead_client():\n"
        "    return ConfidentialLedgerClient(endpoint=os.environ[\"CONFIDENTIAL_LEDGER_ENDPOINT\"], credential=credential)\n"
        "try:\n",
        1,
    )
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("dead scope" in error for error in errors), errors


def test_public_validator_rejects_nested_pre_try_success_exit(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    text = text.replace(
        "try:\n",
        "try:\n    sys.exit(0)\nfinally:\n    pass\ntry:\n",
        1,
    )
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("exactly one reachable top-level try/finally" in error for error in errors), errors


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    (
        ("count-rebind", "must not reassign SupportCase count"),
        ("dead-count", "dead scope"),
        ("dead-finally", "dead scope"),
        ("pre-try-connection", "design-selected SQL databases"),
    ),
)
def test_public_validator_rejects_selected_data_dead_or_rebound_paths(
    tmp_path: Path,
    mutation: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    text = verifier.read_text(encoding="utf-8")
    if mutation == "count-rebind":
        old = "    support_count == 9 or sys.exit(1)"
        new = "    support_count = 9\n" + old
        assert old in text
        text = text.replace(old, new, 1)
    elif mutation == "dead-count":
        old = (
            '    svc09_cursor.execute(\\"SELECT COUNT_BIG(*) FROM [dbo].[support_cases]\\")\n'
            "    support_count = svc09_cursor.fetchone()[0]\n"
            "    support_count == 9 or sys.exit(1)\n"
            "    print(int(support_count))\n"
        )
        dead = (
            "def dead_support_count():\n"
            '    svc09_cursor.execute(\\"SELECT COUNT_BIG(*) FROM [dbo].[support_cases]\\")\n'
            "    support_count = svc09_cursor.fetchone()[0]\n"
            "    support_count == 9 or sys.exit(1)\n"
            "    print(int(support_count))\n"
        )
        assert old in text
        text = text.replace(old, "", 1)
        text = text.replace("try:\n", dead + "try:\n", 1)
    elif mutation == "dead-finally":
        old = "    svc09_cursor.close()\n"
        dead = "def dead_close():\n    svc09_cursor.close()\n"
        assert old in text
        text = text.replace(old, "", 1)
        text = text.replace("try:\n", dead + "try:\n", 1)
    else:
        old = (
            '    svc09_connection = connect(\\"Server=$SQL_HOST;Database=$SQL_DB_SVC09;'
            "UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;"
            'Encrypt=yes;TrustServerCertificate=no\\")\n'
        )
        assert old in text
        text = text.replace("try:\n", old.removeprefix("    ") + "try:\n", 1)
        text = text.replace(old, "", 1)
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


@pytest.mark.parametrize(
    ("entity", "count_name", "expected"),
    tuple(
        (entity, count_name, expected)
        for entity, _database, _table, count_name, expected in _SELECTED_SQL_COVERAGE
    ) + (("VocRecord", "cosmos_count", _VOC_EXPECTED_COUNT),),
)
def test_public_validator_rejects_every_selected_count_reassignment(
    tmp_path: Path,
    entity: str,
    count_name: str,
    expected: int,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    guard = f"    {count_name} == {expected} or sys.exit(1)"
    assert guard in text
    verifier.write_text(
        text.replace(guard, f"    {count_name} = {expected}\n{guard}", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    if entity == "VocRecord":
        assert any("canonical VocRecord count" in error for error in errors), errors
    else:
        assert any(f"must not reassign {entity} count" in error for error in errors), errors


def test_public_validator_rejects_decoy_cosmos_shared_credential(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    text = text.replace(
        "credential = ExitStack()\ncosmos = ExitStack()\n",
        "credential = ExitStack()\nother_credential = ExitStack()\n"
        "cosmos = ExitStack()\ndecoy_cosmos = ExitStack()\n",
        1,
    )
    old = (
        "    credential = DefaultAzureCredential(managed_identity_client_id=client_id)\n"
        '    cosmos = CosmosClient(os.environ[\\"COSMOS_ENDPOINT\\"], credential=credential)\n'
    )
    new = (
        "    credential = DefaultAzureCredential(managed_identity_client_id=client_id)\n"
        "    other_credential = DefaultAzureCredential(managed_identity_client_id=client_id)\n"
        '    cosmos = CosmosClient(os.environ[\\"COSMOS_ENDPOINT\\"], credential=other_credential)\n'
        '    decoy_cosmos = CosmosClient(os.environ[\\"COSMOS_ENDPOINT\\"], credential=credential)\n'
    )
    assert old in text
    text = text.replace(old, new, 1).replace(
        "    cosmos.close()\n",
        "    cosmos.close()\n    decoy_cosmos.close()\n"
        "    other_credential.close()\n",
        1,
    )
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("without decoys" in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "extra_statement"),
    (
        (
            "sql-ledger-digest",
            '    cursor.execute(\\"DELETE FROM [dbo].[members]\\")\n',
        ),
        (
            "acl-direct",
            '    container.upsert_item(body={\\"id\\": \\"extra\\"})\n',
        ),
        (
            "acl-direct",
            '    ledger_client.create_ledger_entry(contents=\\"extra\\")\n',
        ),
    ),
)
def test_public_validator_rejects_additional_data_plane_operations(
    tmp_path: Path,
    mode: str,
    extra_statement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", extra_statement + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("canonical read/count" in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "extra_statements"),
    (
        (
            "sql-ledger-digest",
            "    resources = [cursor]\n"
            '    resources[0].execute(\\"DELETE FROM [dbo].[members]\\")\n',
        ),
        (
            "acl-direct",
            '    resources = {\\"voc\\": container}\n'
            '    resources[\\"voc\\"].upsert_item(body={\\"id\\": \\"extra\\"})\n',
        ),
        (
            "acl-direct",
            "    resources = (ledger_client,)\n"
            '    resources[0].create_ledger_entry(contents=\\"extra\\")\n',
        ),
    ),
)
def test_public_validator_rejects_aliased_data_plane_operations(
    tmp_path: Path,
    mode: str,
    extra_statements: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", extra_statements + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(
        "must not alias or mutate protected" in error
        or "canonical direct receivers" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    ("mode", "extra_statements"),
    (
        (
            "sql-ledger-digest",
            "    runtime = sys\n    runtime.exit = print\n",
        ),
        (
            "acl-direct",
            '    environment = os.environ\n'
            '    environment[\\"CONFIDENTIAL_LEDGER_COLLECTION\\"] = \\"other\\"\n',
        ),
    ),
)
def test_public_validator_rejects_runtime_or_environment_alias_mutation(
    tmp_path: Path,
    mode: str,
    extra_statements: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("try:\n", "try:\n" + extra_statements, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("must not alias or mutate protected" in error for error in errors), errors


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
@pytest.mark.parametrize(
    "extra_statements",
    (
        "    runtime = sys or None\n"
        "    replacement = print or None\n"
        "    runtime.exit = replacement\n",
        "    environment = [value for value in [os.environ]][0]\n"
        '    environment[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"] = \\"other\\"\n',
    ),
)
def test_public_validator_rejects_wrapped_protected_alias_mutation(
    tmp_path: Path,
    mode: str,
    extra_statements: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("try:\n", "try:\n" + extra_statements, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("must not alias or mutate protected" in error for error in errors), errors


@pytest.mark.parametrize(
    "extra_statement",
    (
        "    runtime = (wrapped := sys)\n",
        "    runtime = {value for value in [sys]}\n",
        "    runtime = {index: value for index, value in [(0, sys)]}\n",
        "    runtime = (value for value in [sys])\n",
        '    del os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]\n',
    ),
)
def test_public_validator_rejects_all_supported_protected_alias_forms(
    tmp_path: Path,
    extra_statement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("try:\n", "try:\n" + extra_statement, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(
        "must not alias or mutate protected" in error
        or "direct straight-line statements" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    "extra_statement",
    (
        '    socket.getaddrinfo(\\"example.com\\", 443, 0, socket.SOCK_STREAM)\n',
        '    audit_table_types.get(\\"other\\")\n',
        "    sql_resolved_ips.issubset(cosmos_private_ips)\n",
        '    print(\\"fake evidence\\")\n',
    ),
)
def test_public_validator_rejects_noncanonical_read_or_output_call_shapes(
    tmp_path: Path,
    extra_statement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", extra_statement + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("fixed canonical" in error for error in errors), errors


@pytest.mark.parametrize(
    "extra_statement",
    (
        '    print(f\\"{os.environ}\\")\n',
        "    secret_value = 1\n    print(int(secret_value))\n",
        '    print(str(os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]))\n',
        '    urlparse(\\"https://example.com\\")\n',
    ),
)
def test_public_validator_rejects_noncanonical_output_or_conversion_calls(
    tmp_path: Path,
    extra_statement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", extra_statement + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("fixed canonical" in error for error in errors), errors


@pytest.mark.parametrize(
    "extra_statements",
    (
        '    audit_ledger_status = os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]\n'
        '    print(f\\"{audit_ledger_status}\\")\n',
        '    audit_ledger_type = os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]\n'
        '    print(f\\"{audit_ledger_type}\\")\n',
        '    digest_status = os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]\n'
        '    print(f\\"{digest_status}\\")\n',
        '    status_by_result = {(True, False): os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]}\n'
        '    print(f\\"{status_by_result[(member_count == 0, member_count == 1)]}\\")\n',
    ),
)
def test_public_validator_rejects_tainted_canonical_output_names(
    tmp_path: Path,
    extra_statements: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", extra_statements + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("fixed canonical" in error for error in errors), errors


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_rejects_tainted_legacy_audit_count_name(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    text = text.replace("audit_count", "actual_audit_count")
    taint = (
        '    audit_count = os.environ[\\"CONFIDENTIAL_LEDGER_ENDPOINT\\"]\n'
        '    print(f\\"{audit_count}\\")\n'
    )
    verifier.write_text(
        text.replace("finally:\n", taint + "finally:\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("fixed canonical" in error for error in errors), errors


def test_public_validator_accepts_canonical_dns_preflight_fixture(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    verifier.write_text(_sql_mode_verifier_with_dns_fixture(), encoding="utf-8")

    assert validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    ) == []


@pytest.mark.parametrize("mutation", ("missing-import", "rebound-module"))
def test_public_validator_rejects_invalid_socket_binding_for_dns_preflight(
    tmp_path: Path,
    mutation: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="sql-ledger-digest",
        design_mode="sql-ledger-digest",
    )
    text = _sql_mode_verifier_with_dns_fixture()
    if mutation == "missing-import":
        text = text.replace("import os, re, socket, sys\n", "import os, re, sys\n", 1)
    else:
        text = text.replace("try:\n", "socket = None\ntry:\n", 1)
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("canonical SDK/runtime import" in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "injected_import"),
    (
        ("acl-direct", "import fake_runtime as sys\n"),
        (
            "acl-direct",
            "from fake_ledger import ConfidentialLedgerClient\n",
        ),
        ("sql-ledger-digest", "from fake_cosmos import CosmosClient\n"),
    ),
)
def test_public_validator_rejects_protected_import_overwrite(
    tmp_path: Path,
    mode: str,
    injected_import: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    anchor = 'client_id = \\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\\"\n'
    assert anchor in text
    verifier.write_text(
        text.replace(anchor, injected_import + anchor, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("canonical SDK/runtime import" in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "anchor", "injected"),
    (
        (
            "acl-direct",
            'client_id = \\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\\"\n',
            'import sys as runtime\nclient_id = \\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\\"\n',
        ),
        (
            "acl-direct",
            "try:\n",
            "try:\n    sys.exit.__call__(0)\n",
        ),
        (
            "sql-ledger-digest",
            "try:\n",
            'try:\n    cursor.execute.__call__(\\"DELETE FROM [dbo].[members]\\")\n',
        ),
        (
            "acl-direct",
            "try:\n",
            'try:\n    os.environ.update({\\"CONFIDENTIAL_LEDGER_COLLECTION\\": \\"other\\"})\n',
        ),
    ),
)
def test_public_validator_rejects_indirect_runtime_or_data_plane_calls(
    tmp_path: Path,
    mode: str,
    anchor: str,
    injected: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    assert anchor in text
    verifier.write_text(text.replace(anchor, injected, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(
        "canonical SDK/runtime import" in error
        or "fixed canonical" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    ("mode", "statement"),
    (
        (
            "sql-ledger-digest",
            "    next(filter(os._exit, [0]))\n",
        ),
        (
            "acl-direct",
            '    list(filter(os.environ.update, [{\\"CONFIDENTIAL_LEDGER_COLLECTION\\": \\"other\\"}]))\n',
        ),
        (
            "acl-direct",
            '    list(filter(container.upsert_item, [{\\"id\\": \\"extra\\"}]))\n',
        ),
    ),
)
def test_public_validator_rejects_higher_order_runtime_or_data_plane_calls(
    tmp_path: Path,
    mode: str,
    statement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("try:\n", "try:\n" + statement, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("fixed canonical" in error for error in errors), errors


@pytest.mark.parametrize(
    ("anchor", "injected"),
    (
        (
            "try:\n",
            "early = exit(0)\ntry:\n",
        ),
        (
            "try:\n",
            "try:\n    early = quit(0)\n",
        ),
        (
            "try:\n",
            "try:\n    os._exit(0)\n",
        ),
    ),
)
def test_public_validator_rejects_alternative_success_termination(
    tmp_path: Path,
    anchor: str,
    injected: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    assert anchor in text
    verifier.write_text(text.replace(anchor, injected, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(
        "success-termination paths" in error
        or "only imports and direct initializations" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    "mutation",
    ("prefix-success-exit", "suffix-status-mask"),
)
def test_public_validator_rejects_noncanonical_aci_command_envelope(
    tmp_path: Path,
    mutation: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    if mutation == "prefix-success-exit":
        old = 'aci_command="python -m pip install'
        new = 'aci_command="printf ok; exit 0; python -m pip install'
    else:
        old = "    ledger_certificate_directory.cleanup()'\""
        new = "    ledger_certificate_directory.cleanup()' || true\""
    assert old in text
    verifier.write_text(text.replace(old, new, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("without prefix, suffix" in error for error in errors), errors


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_rejects_os_exec_process_replacement(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    injected = (
        'try:\n    os.execl(sys.executable, sys.executable, '
        '\\"-c\\", \\"print(1)\\")\n'
    )
    assert "try:\n" in text
    verifier.write_text(
        text.replace("try:\n", injected, 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("os.exec*" in error for error in errors), errors


@pytest.mark.parametrize(
    ("old", "new", "expected_fragment"),
    (
        (
            'client_id = \\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\\"',
            'client_id = \\"fixed-client-id\\"',
            "DATA_DEPLOY_IDENTITY_CLIENT_ID",
        ),
        (
            "credential=credential)",
            "credential=other_credential)",
            "same managed-identity credential",
        ),
    ),
)
def test_public_validator_rejects_acl_direct_identity_drift(
    tmp_path: Path,
    old: str,
    new: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    assert old in text
    verifier.write_text(text.replace(old, new, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "key", "remove_kind"),
    (
        ("sql-ledger-digest", "CONFIDENTIAL_LEDGER_ENDPOINT", "guard"),
        ("sql-ledger-digest", "CONFIDENTIAL_LEDGER_ENDPOINT", "transfer"),
        ("acl-direct", "CONFIDENTIAL_LEDGER_COLLECTION", "guard"),
        ("acl-direct", "CONFIDENTIAL_LEDGER_COLLECTION", "transfer"),
    ),
)
def test_public_validator_rejects_missing_audit_mode_env_wiring(
    tmp_path: Path,
    mode: str,
    key: str,
    remove_kind: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    target = (
        f'        : "${{{key}:?}}"\n'
        if remove_kind == "guard"
        else f'{key}="${key}" '
    )
    assert target in text
    verifier.write_text(text.replace(target, "", 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(key in error for error in errors), errors


@pytest.mark.parametrize(
    ("mode", "key", "remove_kind"),
    (
        ("sql-ledger-digest", "COSMOS_ENDPOINT", "guard"),
        ("sql-ledger-digest", "COSMOS_DATABASE", "transfer"),
        ("sql-ledger-digest", "SQL_AUDIT_TABLE", "transfer"),
        ("acl-direct", "COSMOS_CONTAINER_VOC", "guard"),
        ("acl-direct", "COSMOS_CONTAINER_VOC", "transfer"),
    ),
)
def test_public_validator_rejects_missing_common_payload_env_wiring(
    tmp_path: Path,
    mode: str,
    key: str,
    remove_kind: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    target = (
        f'        : "${{{key}:?}}"\n'
        if remove_kind == "guard"
        else f'{key}="${key}" '
    )
    assert target in text
    verifier.write_text(text.replace(target, "", 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(key in error for error in errors), errors


@pytest.mark.parametrize(
    ("option", "value", "replacement"),
    (
        ("--restart-policy", "Never", "Always"),
        ("--os-type", "Linux", "Windows"),
        ("--cpu", "1", "2"),
        ("--memory", "1", "2"),
        ("--cpu", "1", "1 --cpu 1"),
    ),
)
def test_public_validator_rejects_noncanonical_private_aci_options(
    tmp_path: Path,
    option: str,
    value: str,
    replacement: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    target = f"{option} {value}"
    assert target in text
    verifier.write_text(
        text.replace(target, f"{option} {replacement}", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(option in error for error in errors), errors


def test_public_validator_requires_all_mode_guards_before_first_azure_cli(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    first_guard = '        : "${SQL_HOST:?}"\n'
    assert first_guard in text
    verifier.write_text(
        text.replace(
            first_guard,
            '        az identity show --ids "$DATA_DEPLOY_IDENTITY_ID"\n'
            + first_guard,
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("SQL_HOST" in error and "before Azure CLI" in error for error in errors), errors


@pytest.mark.parametrize(
    "mutation",
    ("late-guard", "suffix-value", "duplicate-value"),
)
def test_public_validator_rejects_noncanonical_audit_env_wiring(
    tmp_path: Path,
    mutation: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    key = "CONFIDENTIAL_LEDGER_COLLECTION"
    if mutation == "late-guard":
        guard = f'        : "${{{key}:?}}"\n'
        first_az = (
            '                vnet_id="$(az network vnet show --name '
            '"$DATA_VNET_NAME" --query id --output tsv)"\n'
        )
        assert guard in text and first_az in text
        text = text.replace(guard, "", 1).replace(
            first_az,
            first_az + guard,
            1,
        )
    elif mutation == "suffix-value":
        old = f'{key}="${key}" '
        assert old in text
        text = text.replace(old, f'{key}="${key}-shadow" ', 1)
    else:
        old = f'{key}="${key}" '
        assert old in text
        text = text.replace(old, old + old, 1)
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(key in error for error in errors), errors


@pytest.mark.parametrize("selected_mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_rejects_mixed_audit_mode_payload(
    tmp_path: Path,
    selected_mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=selected_mode,
        design_mode=selected_mode,
    )
    text = verifier.read_text(encoding="utf-8")
    if selected_mode == "sql-ledger-digest":
        mixed = (
            "    # opposite-mode executable markers\n"
            "    ledger_client = ConfidentialLedgerClient\n"
            "    list_ledger_entries = ledger_client.list_ledger_entries\n"
            "    collection = os.environ[\"CONFIDENTIAL_LEDGER_COLLECTION\"]\n"
        )
    else:
        mixed = (
            "    # opposite-mode executable markers\n"
            '    sql_database = "$SQL_DB_SVC12"\n'
            "    sql_table = os.environ[\"SQL_AUDIT_TABLE\"]\n"
            '    ledger_type = "APPEND_ONLY_LEDGER_TABLE"\n'
            '    digest_source = "sys.database_ledger_digest_locations"\n'
        )
    text = text.replace("finally:\n", mixed + "finally:\n", 1)
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("must not include" in error for error in errors), errors


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_ignores_opposite_mode_markers_in_python_comments(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    marker_comment = (
        "    # ConfidentialLedgerClient list_ledger_entries "
        "CONFIDENTIAL_LEDGER_COLLECTION\n"
        if mode == "sql-ledger-digest"
        else "    # SQL_DB_SVC12 SQL_AUDIT_TABLE APPEND_ONLY_LEDGER_TABLE "
        "sys.database_ledger_digest_locations\n"
    )
    text = verifier.read_text(encoding="utf-8")
    verifier.write_text(
        text.replace("finally:\n", marker_comment + "finally:\n", 1),
        encoding="utf-8",
    )

    assert validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    ) == []


def test_public_validator_rejects_correct_acl_aci_plus_host_side_acl_execution(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    with verifier.open("a", encoding="utf-8") as stream:
        stream.write(
            "\n# host-side forbidden execution\n"
            "python -c 'from azure.confidentialledger import ConfidentialLedgerClient; "
            "client=ConfidentialLedgerClient(); client.list_ledger_entries()'\n"
        )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("inside the private ACI payload only" in error for error in errors), errors


def test_public_validator_rejects_post_case_external_data_plane_script(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    with verifier.open("a", encoding="utf-8") as stream:
        stream.write("\n./run-ledger-data-plane-check.sh\n")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("inside the private ACI payload only" in error for error in errors), errors


@pytest.mark.parametrize(
    "command",
    (
        "command bash route-check.sh",
        "env ./route-check.sh",
        "run-ledger-route-check",
        "route_check.py",
    ),
)
def test_public_validator_rejects_wrapped_or_path_post_case_script(
    tmp_path: Path,
    command: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    with verifier.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{command}\n")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("inside the private ACI payload only" in error for error in errors), errors


@pytest.mark.parametrize(
    ("suffix", "expected_fragment"),
    (
        (
            '\naz group delete --name "$RESOURCE_GROUP" --yes\n',
            "must not execute Azure create/update/delete",
        ),
        (
            '\naz rest --method POST --url "https://management.azure.com/example"\n',
            "permits only explicit Azure REST GET/HEAD",
        ),
        (
            '\naz rest --method "POST" --url "https://management.azure.com/example"\n',
            "permits only explicit Azure REST GET/HEAD",
        ),
        (
            "\naz rest --method='PATCH' --url \"https://management.azure.com/example\"\n",
            "permits only explicit Azure REST GET/HEAD",
        ),
        (
            '\naz rest --method GET --url "https://management.azure.com/read"; '
            'az rest --method "POST" --url "https://management.azure.com/write"\n',
            "permits only explicit Azure REST GET/HEAD",
        ),
        (
            '\naz rest --method GET --method "POST" '
            '--url "https://management.azure.com/example"\n',
            "permits only explicit Azure REST GET/HEAD",
        ),
        (
            '\nmode="$DATA_NETWORK_MODE"\ncase "$mode" in\n  private) exit 0 ;;\nesac\n',
            "must not dispatch a second shell case",
        ),
    ),
)
def test_public_validator_rejects_post_case_azure_mutation_or_dispatch(
    tmp_path: Path,
    suffix: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    with verifier.open("a", encoding="utf-8") as stream:
        stream.write(suffix)

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


def test_public_validator_allows_explicit_post_case_rest_get(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    with verifier.open("a", encoding="utf-8") as stream:
        stream.write(
            '\naz rest --method "GET" --url "https://management.azure.com/example"\n'
        )

    assert validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    ) == []


@pytest.mark.parametrize("mode", ("public", "nsp", "blocked"))
@pytest.mark.parametrize(
    "command",
    ("python3 route.py", "bash route.sh", "source route.sh", "./route.sh"),
)
def test_public_validator_rejects_route_attempt_in_fail_closed_mode(
    tmp_path: Path,
    mode: str,
    command: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    branch = f"    {mode})\n"
    assert branch in text
    verifier.write_text(
        text.replace(branch, branch + f"        {command}\n", 1),
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(error.startswith(f"{mode} mode must contain only") for error in errors), errors


@pytest.mark.parametrize("mode", ("public", "nsp", "blocked"))
@pytest.mark.parametrize(
    "mutation",
    ("same-line-suffix", "process-substitution"),
)
def test_public_validator_rejects_inline_route_attempt_in_fail_closed_mode(
    tmp_path: Path,
    mode: str,
    mutation: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    line_pattern = re.compile(
        rf"(?m)^\s*printf '\[ERROR\] {mode}[^']*\\n' >&2$"
    )
    match = line_pattern.search(text)
    assert match is not None
    if mutation == "same-line-suffix":
        replacement = match.group(0).replace(
            " >&2",
            "; bash route.sh >&2",
        )
    else:
        replacement = (
            f"        printf '[ERROR] {mode} route failed %s\\n' "
            "<(bash route.sh) >&2"
        )
    verifier.write_text(
        text[: match.start()] + replacement + text[match.end() :],
        encoding="utf-8",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(error.startswith(f"{mode} mode must contain only") for error in errors), errors


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    (
        (
            "default-selector",
            "case selector must be one direct DATA_NETWORK_MODE expansion",
        ),
        (
            "selector-execution",
            "case selector must be one direct DATA_NETWORK_MODE expansion",
        ),
        (
            "leading-wildcard",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "duplicate-public",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "compound-clause",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "question-glob",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "bracket-glob",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "quoted-wildcard",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "escaped-wildcard",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
        (
            "missing-wildcard",
            "network-mode case requires private/public/nsp/blocked exactly once",
        ),
    ),
)
def test_public_validator_rejects_noncanonical_network_case_inventory(
    tmp_path: Path,
    mutation: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    text = verifier.read_text(encoding="utf-8")
    case_line = 'case "${DATA_NETWORK_MODE:?}" in'
    assert case_line in text
    if mutation == "default-selector":
        text = text.replace(case_line, 'case "${DATA_NETWORK_MODE:-}" in', 1)
    elif mutation == "selector-execution":
        text = text.replace(
            case_line,
            'case "$(bash route.sh; printf %s "$DATA_NETWORK_MODE")" in',
            1,
        )
    elif mutation == "leading-wildcard":
        text = text.replace(
            case_line,
            case_line + "\n  *) exit 0 ;;",
            1,
        )
    elif mutation == "duplicate-public":
        text = text.replace(
            "    public)\n",
            "    public)\n        exit 1\n        ;;\n    public)\n",
            1,
        )
    elif mutation == "compound-clause":
        text = text.replace("    public)\n", "    public|other)\n", 1)
    elif mutation == "question-glob":
        text = text.replace(case_line, case_line + "\n  ?*) exit 0 ;;", 1)
    elif mutation == "bracket-glob":
        text = text.replace(case_line, case_line + "\n  [a-z]*) exit 0 ;;", 1)
    elif mutation == "quoted-wildcard":
        text = text.replace("    *)\n", '    "*")\n', 1)
    elif mutation == "escaped-wildcard":
        text = text.replace("    *)\n", "    \\*)\n", 1)
    else:
        wildcard = (
            "    *)\n"
            "        printf '[ERROR] DATA_NETWORK_MODE is invalid\\n' >&2\n"
            "        exit 1\n"
            "        ;;\n"
        )
        assert wildcard in text
        text = text.replace(wildcard, "", 1)
    verifier.write_text(text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_accepts_known_mode_without_optional_sample_data(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, _sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )

    assert validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=None,
    ) == []


@pytest.mark.parametrize("mode", ("sql-ledger-digest", "acl-direct"))
def test_public_validator_rejects_missing_known_mode_audit_guard_without_sample_data(
    tmp_path: Path,
    mode: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, _sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode=mode,
        design_mode=mode,
    )
    text = verifier.read_text(encoding="utf-8")
    guard = f"    audit_count == {_AUDIT_EXPECTED_COUNT} or sys.exit(1)\n"
    assert guard in text
    verifier.write_text(text.replace(guard, "", 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=None,
    )

    assert any("AuditRecord count" in error for error in errors), errors


@pytest.mark.parametrize(
    ("sample_text", "expected_fragment"),
    (
        ("{not-json", "sample-data JSON error"),
        ("[]", "sample-data root must be an object"),
        ('{"entities": []}', "`entities` must be an object"),
    ),
)
def test_public_validator_reports_precise_sample_data_error(
    tmp_path: Path,
    sample_text: str,
    expected_fragment: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    sample_data.write_text(sample_text, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any(expected_fragment in error for error in errors), errors


def test_public_validator_reports_sample_data_utf8_decode_error(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="acl-direct",
    )
    sample_data.write_bytes(b"\xff\xfe\x00")

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("sample-data UTF-8 decode error" in error for error in errors), errors


def test_public_validator_unknown_mode_does_not_run_legacy_audit_fallback(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data, design = _write_mode_selected_fixture(
        tmp_path,
        verifier_mode="acl-direct",
        design_mode="unknown",
    )

    errors = validate_asdw_data_verify_script(
        verifier,
        design_doc_path=design,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("unknown storage mode" in error for error in errors), errors
    assert not any("defined check_count function" in error for error in errors), errors


@pytest.mark.parametrize(
    "source,replacement",
    (
        ("SELECT COUNT_BIG(*) FROM [dbo].[support_cases]", "SELECT COUNT_BIG(*) FROM [dbo].[missing_support_cases]"),
        ("support_count == 9 or sys.exit(1)", "support_count == 2 or sys.exit(1)"),
    ),
)
def test_selected_data_validator_rejects_incomplete_or_stale_fixture_contract(
    tmp_path: Path, source: str, replacement: str
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    original = verifier.read_text(encoding="utf-8")
    assert source in original
    verifier.write_text(original.replace(source, replacement, 1), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("selected APP data coverage" in error for error in errors)


def test_selected_data_validator_rejects_incomplete_sample_data(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    data = json.loads(sample_data.read_text(encoding="utf-8"))
    del data["entities"]["AuditRecord"]
    sample_data.write_text(json.dumps(data), encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("sample-data" in error and "AuditRecord" in error for error in errors)


@pytest.mark.parametrize(
    "mutation",
    (
        'audit_count="12"',
        "check_count_missing() {",
    ),
)
def test_selected_data_validator_rejects_non_executable_audit_contract(
    tmp_path: Path,
    mutation: str,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    original = verifier.read_text(encoding="utf-8")
    source = (
        'audit_count="$(python -c \'from azure.confidentialledger'
        if mutation.startswith("audit_count")
        else "check_count() {"
    )
    assert source in original
    if mutation.startswith("audit_count"):
        start = original.index(source)
        end = original.index("\ncheck_count AuditRecord", start)
        mutated = original[:start] + mutation + original[end:]
    else:
        mutated = original.replace(source, mutation, 1)
    verifier.write_text(mutated, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("AuditRecord" in error for error in errors)


def test_selected_data_validator_requires_all_closes_in_same_finally(
    tmp_path: Path,
) -> None:
    from hve.artifact_validation import validate_asdw_data_verify_script

    verifier, sample_data = _write_selected_data_fixture(tmp_path)
    original = verifier.read_text(encoding="utf-8")
    mutated = original.replace("finally:\n", "finally:\n    pass\n", 1)
    close_calls = re.findall(
        r"(?m)^    ([A-Za-z_][A-Za-z0-9_]*\.close\(\))(?=['\"]*$)",
        mutated,
    )
    assert close_calls
    for close_call in close_calls:
        mutated = mutated.replace(f"    {close_call}", close_call, 1)
    verifier.write_text(mutated, encoding="utf-8")

    errors = validate_asdw_data_verify_script(
        verifier,
        private_capability_required=True,
        sample_data_path=sample_data,
    )

    assert any("same finally block" in error for error in errors), errors


def test_direct_first_is_public_only_and_inputs_fail_closed() -> None:
    public = _mode_contract(_shared_contract_text(), "public", "private")
    assert _FAIL_CLOSED_SENTENCE in public
    assert _NO_ROUTE_ATTEMPT_SENTENCE in public
    assert _POSITIVE_ROUTE_ATTEMPT_RE.search(public) is None
    for path in (_PROMPT, _TEMPLATE):
        text = _text(path)
        assert "public mode に限り" not in text
        assert "直接接続を優先" not in text
        assert "直接到達を優先" not in text

        catalog_lines = [
            line for line in text.splitlines() if "app-catalog.md" in line
        ]
        assert catalog_lines, path
        assert any(
            "空" in line
            and ("存在しない" in line or "未生成" in line)
            and ("停止" in line or "実行不可" in line)
            for line in catalog_lines
        ), path
        assert "対象 APP-ID 解決不能" in text, path
        assert "交差結果 0 件" in text, path
        assert "verifier 生成前に停止" in text, path


def test_nsp_mode_does_not_infer_approval_from_arbitrary_json() -> None:
    nsp = _network_contract(_shared_contract_text()).split("### `nsp` mode", 1)[1].split("### `blocked` mode", 1)[0]
    assert "任意 JSON" in nsp
    assert "推測" in nsp
    assert "固定 schema" in nsp
    assert "現時点では固定 schema 未定義" in nsp
    assert "JSON parser" in nsp
    assert "生成しない" in nsp
    assert "blocked" in nsp


def test_blocked_mode_stops_before_any_azure_mutation_or_data_check() -> None:
    blocked = _network_contract(_shared_contract_text()).split("### `blocked` mode", 1)[1]
    assert "非ゼロ終了" in blocked
    assert "Azure create / update" in blocked
    assert "一時 ACI" in blocked
    assert "データプレーン検証" in blocked
    assert "開始しない" in blocked


def test_tdd_report_uses_canonical_asdw_workflow_path() -> None:
    for path in (_PROMPT, _TEMPLATE):
        text = _text(path)
        assert (
            "tests/run/<run-id>/asdw-web/step-1-2/<target-app-id>/RED/"
            "tdd-test-report.md"
        ) in text, path
        assert "- Workflow: asdw-web" in text, path
        assert "Custom Agent 名を Workflow に使用しない" in text, path


def test_prompt_owns_truthful_evidence_recording_rules() -> None:
    """F-06: 証跡ラベルの記録可否規則は Prompt を単一正本とする。"""
    text = _text(_PROMPT)
    assert "`bash -n` が成功していない場合" in text
    assert "Evidence-Status: EXECUTED" in text
    assert "TDD-Judgement: PASS" in text
    assert "記録してはならない" in text
    assert "verifier を作成または更新した場合" in text
    assert "- Test-Files-Changed: yes" in text


def test_template_delegates_evidence_recording_rules_to_prompt() -> None:
    """F-06: template は証跡記録規則を逐語重複せず Prompt へ委譲する。"""
    text = _text(_TEMPLATE)
    assert _PROMPT_SSOT_REFERENCE in text
    for duplicated in (
        "`bash -n` が成功していない場合",
        "verifier を作成または更新した場合",
        "- Test-Files-Changed: yes",
        "見出し名は",
    ):
        assert duplicated not in text, duplicated


def test_template_delegates_runtime_environment_rules_to_prompt() -> None:
    """F-06: 実行ホスト / launcher 環境契約の本文を template から削除する。

    `## 生成テストの実行環境` 見出し自体は残し、template_engine の
    重複注入（`_inject_generated_test_runtime_section`）を抜けないことも固定する。
    """
    prompt_text = _text(_PROMPT)
    template_text = _text(_TEMPLATE)
    assert "GNU coreutils の `timeout`" in prompt_text
    assert "HVE launcher environment contract" in prompt_text
    assert "GNU coreutils" not in template_text
    assert "HVE launcher environment contract" not in template_text
    assert "## 生成テストの実行環境" in template_text
    assert "ローカル端末 / CI" in template_text
    assert "環境変数" in template_text
    assert "秘密情報" in template_text
    assert template_text.count(_PROMPT_SSOT_REFERENCE) == 2
