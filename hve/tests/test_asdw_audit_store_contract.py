"""ASDW-WEB AuditRecord storage mode の設計追随契約テスト。"""
from __future__ import annotations

from pathlib import Path

import pytest

from hve import artifact_validation


_SQL_LEDGER_DIGEST = "sql-ledger-digest"
_ACL_DIRECT = "acl-direct"
_SQL_CANONICAL = (
    "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ "
    "Azure confidential ledger（信頼済み database digest 保管先、条件付き）"
)
_DIRECT_CANONICAL = "Azure confidential ledger（AuditRecord を直接格納）"


def _design_document(
    chosen: str,
    *,
    alternatives: str = "Azure Blob Storage immutable storage",
    duplicate_audit_row: bool = False,
    include_audit_row: bool = True,
    include_chosen_column: bool = True,
) -> str:
    headers = [
        "Entity",
        "Data characteristics（構造/更新頻度/サイズ）",
        "Access patterns（主要クエリ/ホットパス）",
        "Consistency（強/最終/要件根拠）",
        "Chosen Azure service（正式名称）",
        "Partition/Key/Index（要点）",
        "Rationale（3〜6行）",
        "Alternatives（最大2つ）",
        "Evidence（根拠リンク）",
    ]
    member = [
        "Member",
        "構造化",
        "ID検索",
        "強整合",
        "**Azure SQL Database**",
        "member_id",
        "関係制約",
        "Azure Cosmos DB",
        "official-link",
    ]
    audit = [
        "AuditRecord",
        "追記証拠",
        "相関ID検索",
        "強整合",
        chosen,
        "audit_event_id",
        "監査証拠",
        alternatives,
        "official-link",
    ]
    if not include_chosen_column:
        chosen_index = headers.index("Chosen Azure service（正式名称）")
        del headers[chosen_index]
        del member[chosen_index]
        del audit[chosen_index]

    def row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    rows = [row(headers), row(["---"] * len(headers)), row(member)]
    if include_audit_row:
        rows.append(row(audit))
        if duplicate_audit_row:
            rows.append(row(audit))
    return "\n".join(
        (
            "# Azure data design",
            "",
            "## 1. エンティティ別ストア選定",
            "",
            *rows,
            "",
            "## 2. ストア間の整合性/同期戦略",
            "",
            "| 方針 | 採否 | 理由・運用上の注意 |",
            "|---|---|---|",
            "| AuditRecord の整合性証明 | 条件付き採用 | "
            "AuditRecord は Azure SQL Database に保持し database digest を保管する |",
            "",
        )
    )


def _resolve(tmp_path: Path, text: str) -> tuple[str | None, list[str]]:
    design = tmp_path / "azure-services-data.md"
    design.write_text(text, encoding="utf-8")
    resolver = getattr(
        artifact_validation,
        "_resolve_asdw_audit_storage_mode",
        None,
    )
    assert callable(resolver), (
        "AuditRecord mode resolver is not implemented: "
        "_resolve_asdw_audit_storage_mode"
    )
    return resolver(design)


def _sql_audit_count_source(expected: int = 3) -> str:
    return f'''from contextlib import ExitStack
from mssql_python import connect
import os, re, sys

svc12_connection = ExitStack()
svc12_cursor = ExitStack()
try:
    svc12_connection = connect("Server=$SQL_HOST;Database=$SQL_DB_SVC12;UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no")
    svc12_cursor = svc12_connection.cursor()
    audit_table = os.environ["SQL_AUDIT_TABLE"]
    next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)]))
    svc12_cursor.execute(f"SELECT COUNT_BIG(*) FROM [dbo].[{{audit_table}}]")
    audit_count = svc12_cursor.fetchone()[0]
    print(int(audit_count))
    audit_count == {expected} or sys.exit(1)
finally:
    svc12_cursor.close()
    svc12_connection.close()
'''


def _validate_sql_audit_count(source: str, expected: int = 3) -> list[str]:
    validator = getattr(
        artifact_validation,
        "_validate_asdw_sql_audit_count",
        None,
    )
    assert callable(validator), (
        "SQL AuditRecord count validator is not implemented: "
        "_validate_asdw_sql_audit_count"
    )
    return validator(source, expected)


def _validate_sql_audit_metadata(source: str) -> list[str]:
    validator = getattr(
        artifact_validation,
        "_validate_asdw_sql_audit_metadata",
        None,
    )
    assert callable(validator), (
        "SQL AuditRecord metadata validator is not implemented: "
        "_validate_asdw_sql_audit_metadata"
    )
    return validator(source)


def _sql_audit_metadata_source() -> str:
    count_source = _sql_audit_count_source().replace(
        "from mssql_python import connect\n",
        "from mssql_python import connect\nfrom urllib.parse import urlparse\n",
        1,
    )
    guard = "    audit_count == 3 or sys.exit(1)\n"
    metadata = '''    svc12_cursor.execute("SELECT SCHEMA_NAME(schema_id), name, ledger_type_desc FROM sys.tables")
    audit_table_types = {(str(row[0]), str(row[1])): str(row[2]) for row in svc12_cursor.fetchall()}
    audit_ledger_type = audit_table_types.get(("dbo", audit_table), "")
    audit_ledger_ok = audit_ledger_type == "APPEND_ONLY_LEDGER_TABLE"
    next(filter(None, [audit_ledger_ok]))
    ledger_host = urlparse(os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"]).hostname
    next(filter(None, [ledger_host]))
    svc12_cursor.execute("SELECT path, last_digest_block_id FROM sys.database_ledger_digest_locations WHERE is_current = 1")
    digest_rows = svc12_cursor.fetchall()
    digest_ready = any((urlparse(str(row[0])).hostname == ledger_host, row[1] is not None) == (True, True) for row in digest_rows)
    next(filter(None, [digest_ready]))
'''
    return count_source.replace(guard, guard + metadata, 1)


def test_resolves_sql_ledger_with_confidential_ledger_digest(
    tmp_path: Path,
) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "**Azure SQL Database の append-only ledger table**（SVC-12 の監査証拠 SoT）"
            "+ **Azure confidential ledger**（信頼済み database digest 保管先、条件付き）",
            alternatives="Azure confidential ledger 直接格納",
        ),
    )

    assert mode == _SQL_LEDGER_DIGEST
    assert errors == []


def test_resolves_direct_confidential_ledger_storage(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "**Azure confidential ledger**（AuditRecord を直接格納）",
            alternatives="Azure SQL Database 検索投影",
        ),
    )

    assert mode == _ACL_DIRECT
    assert errors == []


def test_does_not_select_sql_digest_mode_from_alternatives_column(
    tmp_path: Path,
) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "**Azure confidential ledger**（AuditRecord を直接格納）",
            alternatives=(
                "Azure SQL Database の append-only ledger table + "
                "Azure confidential ledger database digest 保管先"
            ),
        ),
    )

    assert mode == _ACL_DIRECT
    assert errors == []


def test_rejects_unknown_audit_storage_mode(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "Azure Blob Storage immutable storage",
            alternatives="Azure confidential ledger 直接格納",
        ),
    )

    assert mode is None
    assert errors
    assert any("AuditRecord" in error for error in errors)


def test_rejects_missing_audit_record_row(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document("unused", include_audit_row=False),
    )

    assert mode is None
    assert errors
    assert any("AuditRecord" in error for error in errors)


def test_rejects_duplicate_audit_record_rows(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "Azure confidential ledger（AuditRecord を直接格納）",
            duplicate_audit_row=True,
        ),
    )

    assert mode is None
    assert errors
    assert any("AuditRecord" in error for error in errors)


def test_rejects_ambiguous_direct_and_digest_semantics(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "Azure SQL Database append-only ledger table + "
            "Azure confidential ledger database digest 保管先 + "
            "AuditRecord を直接格納"
        ),
    )

    assert mode is None
    assert errors
    assert any("AuditRecord" in error for error in errors)


def test_rejects_missing_chosen_service_column(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document("unused", include_chosen_column=False),
    )

    assert mode is None
    assert errors
    assert any("Chosen Azure service" in error for error in errors)


def test_rejects_missing_design_document(tmp_path: Path) -> None:
    missing = tmp_path / "missing-azure-services-data.md"
    resolver = getattr(
        artifact_validation,
        "_resolve_asdw_audit_storage_mode",
        None,
    )
    assert callable(resolver), (
        "AuditRecord mode resolver is not implemented: "
        "_resolve_asdw_audit_storage_mode"
    )

    mode, errors = resolver(missing)

    assert mode is None
    assert errors


def test_accepts_markdown_decorated_audit_record_entity(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| AuditRecord |", "| **AuditRecord** |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode == _ACL_DIRECT
    assert errors == []


def test_rejects_unpublished_english_direct_alias(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        _design_document(
            "Store AuditRecord directly in Azure confidential ledger"
        ),
    )

    assert mode is None
    assert errors == [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


@pytest.mark.parametrize(
    "chosen",
    (
        _SQL_CANONICAL.lower(),
        _DIRECT_CANONICAL.lower(),
        "Azure SQL Database の append-only ledger table + "
        "Azure confidential ledger（database digest 保管先）",
        "Azure SQL Database の append-only ledger table + "
        "Azure confidential ledger（信頼済み database digest 保管先）",
        "***Azure confidential ledger***（AuditRecord を直接格納）",
        "Azure confidential  ledger（AuditRecord を直接格納）",
    ),
)
def test_rejects_unpublished_case_alias_decoration_or_spacing(
    tmp_path: Path,
    chosen: str,
) -> None:
    mode, errors = _resolve(tmp_path, _design_document(chosen))

    assert mode is None
    assert errors == [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


@pytest.mark.parametrize(
    ("chosen", "expected_mode"),
    (
        (
            "**Azure confidential ledger**（AuditRecord を直接格納）。",
            _ACL_DIRECT,
        ),
        (
            "*Azure confidential ledger*（AuditRecord を直接格納）.",
            _ACL_DIRECT,
        ),
        (
            "**Azure SQL Database の append-only ledger table**（SVC-12 の監査証拠 SoT）"
            "+ **Azure confidential ledger**（信頼済み database digest 保管先、条件付き）。",
            _SQL_LEDGER_DIGEST,
        ),
    ),
)
def test_accepts_balanced_chosen_decoration_and_one_trailing_period(
    tmp_path: Path,
    chosen: str,
    expected_mode: str,
) -> None:
    mode, errors = _resolve(tmp_path, _design_document(chosen))

    assert mode == expected_mode
    assert errors == []


def test_resolves_current_azure_data_design_audit_mode() -> None:
    design = Path(__file__).resolve().parents[2] / "docs" / "azure" / "azure-services-data.md"
    resolver = getattr(
        artifact_validation,
        "_resolve_asdw_audit_storage_mode",
    )

    mode, errors = resolver(design)

    assert mode == _SQL_LEDGER_DIGEST
    assert errors == []


@pytest.mark.parametrize(
    "chosen",
    (
        "Azure confidential ledger（AuditRecord を直接格納）。。",
        "**Azure confidential ledger（AuditRecord を直接格納）",
        "*Azure confidential ledger（AuditRecord を直接格納）",
    ),
)
def test_does_not_over_normalize_chosen_value(
    tmp_path: Path,
    chosen: str,
) -> None:
    mode, errors = _resolve(tmp_path, _design_document(chosen))

    assert mode is None
    assert errors == [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


def test_data_design_prompt_and_shared_contract_publish_same_canonical_values() -> None:
    root = Path(__file__).resolve().parents[2]
    prompt = (
        root / ".github" / "prompts" / "Dev-Microservice-Azure-DataDesign.prompt.md"
    ).read_text(encoding="utf-8")
    contract = (
        root
        / ".github"
        / "skills"
        / "azure-skills"
        / "azure-cli-deploy-scripts"
        / "references"
        / "asdw-data-verifier-contract.md"
    ).read_text(encoding="utf-8")
    canonical_values = (
        "Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）"
        "+ Azure confidential ledger（信頼済み database digest 保管先、条件付き）",
        "Azure confidential ledger（AuditRecord を直接格納）",
    )
    for value in canonical_values:
        assert value in prompt
        assert value in contract
    for syntax in ("`**...**`", "`` `...` ``", "`*...*`"):
        assert syntax in prompt
    assert "`_..._` / `~~...~~`等は使用しない" in prompt


@pytest.mark.parametrize(
    "chosen",
    (
        "Azure confidential ledger へ AuditRecord を直接格納しない",
        "Azure SQL Database append-only ledger table は不採用、"
        "Azure confidential ledger に database digest を保管しない",
        "Do not store AuditRecord directly in Azure confidential ledger",
    ),
)
def test_rejects_negative_storage_decisions(
    tmp_path: Path,
    chosen: str,
) -> None:
    mode, errors = _resolve(tmp_path, _design_document(chosen))

    assert mode is None
    assert errors == [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


def test_rejects_lowercase_entity_name(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| AuditRecord |", "| auditrecord |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one `AuditRecord` entity row."
    ]


def test_rejects_noncanonical_chosen_header(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("Chosen Azure service（正式名称）", "Chosen Azure services", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode entity selection table header must match "
        "the fixed nine-column DataDesign schema, including exactly one "
        "`Entity` and `Chosen Azure service` column."
    ]


def test_rejects_table_not_immediately_after_heading(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace(
        "## 1. エンティティ別ストア選定\n\n|",
        "## 1. エンティティ別ストア選定\n\n説明文\n\n|",
        1,
    )

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires the entity selection table "
        "immediately after its section heading."
    ]


def test_rejects_second_table_in_entity_section(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace(
        "\n## 2. ストア間の整合性/同期戦略",
        "\n補足\n| Extra | Value |\n|---|---|\n| x | y |\n"
        "## 2. ストア間の整合性/同期戦略",
        1,
    )

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one Markdown table "
        "under the entity selection section."
    ]


@pytest.mark.parametrize("wrapper", ("fence", "comment", "indent"))
def test_ignores_hidden_spoofed_entity_tables(
    tmp_path: Path,
    wrapper: str,
) -> None:
    fake = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    if wrapper == "fence":
        hidden = f"```markdown\n{fake}\n```\n"
    elif wrapper == "comment":
        hidden = f"<!--\n{fake}\n-->\n"
    else:
        hidden = "\n".join(f"    {line}" for line in fake.splitlines()) + "\n"
    actual = _design_document(_SQL_CANONICAL)

    mode, errors = _resolve(tmp_path, hidden + actual)

    assert mode == _SQL_LEDGER_DIGEST
    assert errors == []


@pytest.mark.parametrize("placement", ("comment-only", "prefix", "suffix"))
def test_accepts_closed_single_line_html_comment(
    tmp_path: Path,
    placement: str,
) -> None:
    actual = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    if placement == "comment-only":
        text = "<!-- hidden note -->\n" + actual
    elif placement == "prefix":
        text = actual.replace(
            "## 1. エンティティ別ストア選定",
            "<!-- hidden -->## 1. エンティティ別ストア選定",
            1,
        )
    else:
        text = actual.replace(
            "## 1. エンティティ別ストア選定",
            "## 1. エンティティ別ストア選定<!-- hidden -->",
            1,
        )

    mode, errors = _resolve(tmp_path, text)

    assert mode == _ACL_DIRECT
    assert errors == []


@pytest.mark.parametrize(
    ("prefix", "expected_error"),
    (
        (
            "<!--\n",
            "AuditRecord storage mode design document has an unclosed HTML comment.",
        ),
        (
            "```markdown\n",
            "AuditRecord storage mode design document has an unclosed fenced block.",
        ),
    ),
)
def test_rejects_unclosed_hidden_blocks(
    tmp_path: Path,
    prefix: str,
    expected_error: str,
) -> None:
    mode, errors = _resolve(
        tmp_path,
        prefix
        + _design_document(
            "Azure confidential ledger（AuditRecord を直接格納）"
        ),
    )

    assert mode is None
    assert errors == [expected_error]


def test_does_not_treat_text_after_fence_marker_as_closing_fence(
    tmp_path: Path,
) -> None:
    hidden = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    text = f"```markdown\n{hidden}\n```not-a-close\n"

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode design document has an unclosed fenced block."
    ]


def test_indented_fence_does_not_change_fence_state(tmp_path: Path) -> None:
    indented_fence = "    ```markdown\n    hidden\n    ```\n"
    actual = _design_document(_SQL_CANONICAL)

    mode, errors = _resolve(tmp_path, indented_fence + actual)

    assert mode == _SQL_LEDGER_DIGEST
    assert errors == []


def test_mixed_space_tab_indented_spoof_is_ignored(tmp_path: Path) -> None:
    fake = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    hidden = "\n".join(f"   \t{line}" for line in fake.splitlines()) + "\n"
    actual = _design_document(_SQL_CANONICAL)

    mode, errors = _resolve(tmp_path, hidden + actual)

    assert mode == _SQL_LEDGER_DIGEST
    assert errors == []


@pytest.mark.parametrize("column_delta", (-1, 1))
def test_rejects_non_nine_column_data_rows(
    tmp_path: Path,
    column_delta: int,
) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    audit_line = next(
        line for line in text.splitlines() if line.startswith("| AuditRecord |")
    )
    cells = [cell.strip() for cell in audit_line.strip("|").split("|")]
    if column_delta < 0:
        cells.pop()
    else:
        cells.append("unexpected")
    replacement = "| " + " | ".join(cells) + " |"
    text = text.replace(audit_line, replacement, 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode entity selection table must use exactly nine columns."
    ]


def test_rejects_invalid_table_separator(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| --- | --- |", "| -- | --- |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode entity selection table separator is invalid."
    ]


def test_rejects_decorated_fixed_header(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| Entity |", "| **Entity** |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode entity selection table header must match "
        "the fixed nine-column DataDesign schema, including exactly one "
        "`Entity` and `Chosen Azure service` column."
    ]


def test_rejects_double_edge_pipe(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| Entity |", "|| Entity |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one Markdown table "
        "under the entity selection section."
    ]


def test_rejects_additional_table_without_edge_pipes(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace(
        "\n## 2. ストア間の整合性/同期戦略",
        "\n補足\nExtra | Value\n--- | ---\nx | y\n"
        "## 2. ストア間の整合性/同期戦略",
        1,
    )

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one Markdown table "
        "under the entity selection section."
    ]


def test_rejects_duplicate_entity_section_heading(tmp_path: Path) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    text += "\n## 1. エンティティ別ストア選定\n"

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one "
        "`## 1. エンティティ別ストア選定` section."
    ]


@pytest.mark.parametrize(
    "chosen",
    (
        "Azure SQL Database の append-only ledger table（not SoT）+ "
        "Azure confidential ledger（database digest の保管先ではない）。",
        "Azure SQL Database の append-only ledger table + "
        "Azure confidential ledger（database digest 保管先、AuditRecord を直接格納）",
        "Never store AuditRecord directly in Azure confidential ledger",
        "Azure confidential ledger（AuditRecord を直接格納する方式ではない）",
    ),
)
def test_rejects_noncanonical_or_ambiguous_mode_phrases(
    tmp_path: Path,
    chosen: str,
) -> None:
    mode, errors = _resolve(tmp_path, _design_document(chosen))

    assert mode is None
    assert errors == [
        "AuditRecord Chosen Azure service uses an unknown storage mode."
    ]


def test_rejects_pipe_delimited_competing_row_without_edge_pipes(
    tmp_path: Path,
) -> None:
    text = _design_document(_SQL_CANONICAL).replace(
        "\n## 2. ストア間の整合性/同期戦略",
        "\nAuditRecord | 追記証拠 | 相関ID検索 | 強整合 | "
        "Azure confidential ledger（AuditRecord を直接格納） | "
        "audit_event_id | 監査証拠 | SQL | link\n"
        "## 2. ストア間の整合性/同期戦略",
        1,
    )

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one Markdown table "
        "under the entity selection section."
    ]


@pytest.mark.parametrize(
    "tag",
    (
        "pre",
        "script",
        "style",
        "textarea",
        "div",
        "details",
        "table",
        "iframe",
        "custom-element",
    ),
)
def test_rejects_raw_html_spoofed_table(
    tmp_path: Path,
    tag: str,
) -> None:
    hidden = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    )
    actual = _design_document(_SQL_CANONICAL)

    mode, errors = _resolve(
        tmp_path,
        f"<{tag}>\n{hidden}\n</{tag}>\n{actual}",
    )

    assert mode is None
    assert errors == [
        "AuditRecord storage mode design document contains a raw HTML block, "
        "which is not permitted."
    ]


def test_rejects_unclosed_raw_html_block(tmp_path: Path) -> None:
    mode, errors = _resolve(
        tmp_path,
        "<pre>\n"
        + _design_document(
            "Azure confidential ledger（AuditRecord を直接格納）"
        ),
    )

    assert mode is None
    assert errors == [
        "AuditRecord storage mode design document contains a raw HTML block, "
        "which is not permitted."
    ]


@pytest.mark.parametrize(
    "entity",
    ("AuditRecord**", "**AuditRecord", "Au**ditRecord", "`AuditRecord"),
)
def test_rejects_unbalanced_or_inword_entity_decoration(
    tmp_path: Path,
    entity: str,
) -> None:
    text = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).replace("| AuditRecord |", f"| {entity} |", 1)

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    assert errors == [
        "AuditRecord storage mode requires exactly one `AuditRecord` entity row."
    ]


@pytest.mark.parametrize(
    "hidden_prefix",
    (
        "<pre>\nhidden\n</pre>",
        "<!--\nhidden\n-->",
    ),
)
def test_does_not_reuse_hidden_block_closing_line_suffix_as_heading(
    tmp_path: Path,
    hidden_prefix: str,
) -> None:
    table_only = _design_document(
        "Azure confidential ledger（AuditRecord を直接格納）"
    ).split("## 1. エンティティ別ストア選定\n", 1)[1]
    text = hidden_prefix + "## 1. エンティティ別ストア選定\n" + table_only

    mode, errors = _resolve(tmp_path, text)

    assert mode is None
    if hidden_prefix.startswith("<pre>"):
        assert errors == [
            "AuditRecord storage mode design document contains a raw HTML block, "
            "which is not permitted."
        ]
    else:
        assert errors == [
            "AuditRecord storage mode requires exactly one "
            "`## 1. エンティティ別ストア選定` section."
        ]


@pytest.mark.parametrize(
    "raw_html",
    (
        "<div\n hidden>\n",
        "<details\n open>\n",
        "<div hidden/>\n",
        "<custom-element/>\n",
        "<br>\n",
        "<!DOCTYPE html>\n",
        "<!ENTITY hidden SYSTEM 'value'>\n",
        "<![CDATA[hidden]]>\n",
        "<?xml version='1.0'?>\n",
    ),
)
def test_rejects_multiline_or_self_closing_raw_html(
    tmp_path: Path,
    raw_html: str,
) -> None:
    mode, errors = _resolve(tmp_path, raw_html + _design_document(_SQL_CANONICAL))

    assert mode is None
    assert errors == [
        "AuditRecord storage mode design document contains a raw HTML block, "
        "which is not permitted."
    ]


def test_sql_audit_count_accepts_svc12_dynamic_table_and_expected_count() -> None:
    assert _validate_sql_audit_count(_sql_audit_count_source()) == []


@pytest.mark.parametrize(
    ("old", "new", "error_fragment"),
    (
        (
            "Database=$SQL_DB_SVC12;",
            "Database=$SQL_DB_SVC09;",
            "SQL_DB_SVC12",
        ),
        (
            'audit_table = os.environ["SQL_AUDIT_TABLE"]',
            'audit_table = "audit_records"',
            "SQL_AUDIT_TABLE",
        ),
        (
            're.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)',
            're.fullmatch(r".*", audit_table)',
            "safe SQL identifier",
        ),
        (
            'f"SELECT COUNT_BIG(*) FROM [dbo].[{audit_table}]"',
            'f"SELECT COUNT_BIG(*) FROM [audit].[{audit_table}]"',
            "COUNT_BIG",
        ),
        (
            "audit_count = svc12_cursor.fetchone()[0]",
            "audit_count = 3",
            "fetchone",
        ),
        (
            "audit_count == 3 or sys.exit(1)",
            "audit_count == 2 or sys.exit(1)",
            "expected count 3",
        ),
        (
            "print(int(audit_count))",
            "print(3)",
            "emit",
        ),
    ),
)
def test_sql_audit_count_rejects_wrong_binding_or_stale_count(
    old: str,
    new: str,
    error_fragment: str,
) -> None:
    source = _sql_audit_count_source()
    assert old in source

    errors = _validate_sql_audit_count(source.replace(old, new, 1))

    assert any(error_fragment in error for error in errors), errors


@pytest.mark.parametrize(
    "close_call",
    ("svc12_cursor.close()", "svc12_connection.close()"),
)
def test_sql_audit_count_requires_cursor_and_connection_close_in_finally(
    close_call: str,
) -> None:
    source = _sql_audit_count_source()
    assert close_call in source

    errors = _validate_sql_audit_count(source.replace(f"    {close_call}\n", "", 1))

    assert any("same finally" in error for error in errors), errors


def test_sql_audit_count_rejects_query_filter() -> None:
    source = _sql_audit_count_source().replace(
        "FROM [dbo].[{audit_table}]",
        "FROM [dbo].[{audit_table}] WHERE active = 1",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("COUNT_BIG" in error for error in errors), errors


def test_sql_audit_count_rejects_dead_function_candidate() -> None:
    imports, body = _sql_audit_count_source().split("\n\n", 1)
    source = imports + "\n\ndef dead():\n" + "\n".join(
        f"    {line}" for line in body.splitlines()
    )

    errors = _validate_sql_audit_count(source)

    assert any("reachable top-level" in error for error in errors), errors


def test_sql_audit_count_rejects_dead_conditional_candidate() -> None:
    imports, body = _sql_audit_count_source().split("\n\n", 1)
    source = imports + "\n\nif False:\n" + "\n".join(
        f"    {line}" for line in body.splitlines()
    )

    errors = _validate_sql_audit_count(source)

    assert any("reachable top-level" in error for error in errors), errors


def test_sql_audit_count_rejects_decoy_and_live_candidates() -> None:
    source = _sql_audit_count_source()
    decoy = '''
def dead_decoy():
    connection = connect("Server=$SQL_HOST;Database=$SQL_DB_SVC12;UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no")
'''

    errors = _validate_sql_audit_count(decoy + source)

    assert any("exactly one reachable" in error for error in errors), errors


def test_sql_audit_count_rejects_missing_mssql_python_import() -> None:
    source = _sql_audit_count_source().replace(
        "from mssql_python import connect\n",
        "def connect(value):\n    return value\n",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("mssql_python" in error for error in errors), errors


@pytest.mark.parametrize(
    "rebind",
    (
        "connect = lambda value: value\n",
        "sys.exit = lambda value: None\n",
        "print = lambda value: None\n",
    ),
)
def test_sql_audit_count_rejects_protected_symbol_rebinding(
    rebind: str,
) -> None:
    source = _sql_audit_count_source().replace(
        "svc12_connection = ExitStack()\n",
        rebind + "svc12_connection = ExitStack()\n",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("protected runtime symbols" in error for error in errors), errors


def test_sql_audit_count_rejects_ignored_identifier_check() -> None:
    source = _sql_audit_count_source().replace(
        'next(filter(None, [re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)]))',
        're.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit_table)',
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("safe SQL identifier" in error for error in errors), errors


def test_sql_audit_count_rejects_second_query_before_fetch() -> None:
    source = _sql_audit_count_source().replace(
        "    audit_count = svc12_cursor.fetchone()[0]",
        '    svc12_cursor.execute("SELECT 1")\n'
        "    audit_count = svc12_cursor.fetchone()[0]",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("immediately" in error for error in errors), errors


@pytest.mark.parametrize(
    ("anchor", "reassignment", "error_fragment"),
    (
        (
            "    audit_table = os.environ",
            "    audit_table = 'replacement'\n",
            "audit_table",
        ),
        (
            "    svc12_cursor.execute",
            "    svc12_cursor = svc12_connection.cursor()\n",
            "reassign its SVC-12 cursor",
        ),
        (
            "    print(int(audit_count))",
            "    audit_count = 3\n",
            "reassign the executed COUNT_BIG result",
        ),
    ),
)
def test_sql_audit_count_rejects_reassignment(
    anchor: str,
    reassignment: str,
    error_fragment: str,
) -> None:
    source = _sql_audit_count_source().replace(anchor, reassignment + anchor, 1)

    errors = _validate_sql_audit_count(source)

    assert any(error_fragment in error for error in errors), errors


def test_sql_audit_count_rejects_guard_before_emit() -> None:
    source = _sql_audit_count_source()
    emit = "    print(int(audit_count))\n"
    guard = "    audit_count == 3 or sys.exit(1)\n"
    assert emit in source and guard in source
    source = source.replace(emit + guard, guard + emit, 1)

    errors = _validate_sql_audit_count(source)

    assert any("after emitting" in error for error in errors), errors


def test_sql_audit_count_rejects_early_exit_before_query() -> None:
    source = _sql_audit_count_source().replace(
        "    svc12_connection = connect",
        "    sys.exit(0)\n    svc12_connection = connect",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("unconditional sys.exit" in error for error in errors), errors


def test_sql_audit_count_rejects_dead_cleanup_calls() -> None:
    source = _sql_audit_count_source().replace(
        "    svc12_cursor.close()\n    svc12_connection.close()",
        "    if False:\n"
        "        svc12_cursor.close()\n"
        "        svc12_connection.close()",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("direct calls" in error for error in errors), errors


def test_sql_audit_count_requires_safe_preinitialization() -> None:
    source = _sql_audit_count_source().replace(
        "svc12_connection = ExitStack()",
        "svc12_connection = None",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("initialize its SVC-12 connection" in error for error in errors), errors


@pytest.mark.parametrize(
    "handler",
    (
        "except BaseException:\n    pass\n",
        "except SystemExit:\n    pass\n",
    ),
)
def test_sql_audit_count_rejects_exception_handlers(handler: str) -> None:
    source = _sql_audit_count_source().replace(
        "finally:\n",
        handler + "finally:\n",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("without except or else" in error for error in errors), errors


def test_sql_audit_count_rejects_success_exit_after_emit() -> None:
    source = _sql_audit_count_source().replace(
        "    audit_count == 3 or sys.exit(1)",
        "    sys.exit(0)\n    audit_count == 3 or sys.exit(1)",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("success or dynamic sys.exit" in error for error in errors), errors


def test_sql_audit_count_rejects_exit_in_finally() -> None:
    source = _sql_audit_count_source().replace(
        "    svc12_connection.close()",
        "    svc12_connection.close()\n    sys.exit(0)",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("success or dynamic sys.exit" in error for error in errors), errors
    assert any("direct close calls only" in error for error in errors), errors


@pytest.mark.parametrize(
    "definition",
    (
        "def connect(value):\n    return value\n\n",
        "class sys:\n    @staticmethod\n    def exit(value):\n        return None\n\n",
        "def ExitStack():\n    return None\n\n",
    ),
)
def test_sql_audit_count_rejects_protected_definitions(
    definition: str,
) -> None:
    source = _sql_audit_count_source().replace(
        "import os, re, sys\n\n",
        "import os, re, sys\n\n" + definition,
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("protected runtime symbols" in error for error in errors), errors


@pytest.mark.parametrize("position", ("before", "after"))
def test_sql_audit_count_rejects_unapproved_cursor_sql(position: str) -> None:
    anchor = '    svc12_cursor.execute(f"SELECT COUNT_BIG(*) FROM [dbo].[{audit_table}]")\n'
    extra = '    svc12_cursor.execute("DELETE FROM [dbo].[audit_records]")\n'
    source = _sql_audit_count_source()
    if position == "before":
        source = source.replace(anchor, extra + anchor, 1)
    else:
        guard = "    audit_count == 3 or sys.exit(1)\n"
        source = source.replace(guard, guard + extra, 1)

    errors = _validate_sql_audit_count(source)

    assert any("unapproved SQL" in error for error in errors), errors


def test_sql_audit_count_rejects_conflicting_database_property() -> None:
    source = _sql_audit_count_source().replace(
        "Database=$SQL_DB_SVC12;",
        "Database=$SQL_DB_SVC09;Database=$SQL_DB_SVC12;",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("exactly one reachable" in error for error in errors), errors


def test_sql_audit_count_rejects_finally_raise() -> None:
    source = _sql_audit_count_source().replace(
        "    svc12_connection.close()",
        "    svc12_connection.close()\n    raise RuntimeError('override')",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("separate raise path" in error for error in errors), errors
    assert any("direct close calls only" in error for error in errors), errors


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("Server=$SQL_HOST", "Server=public.example.invalid"),
        ("UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID", "UID=admin"),
        ("Authentication=ActiveDirectoryMSI", "Authentication=SqlPassword"),
        ("Encrypt=yes", "Encrypt=no"),
        ("TrustServerCertificate=no", "TrustServerCertificate=yes"),
        (
            "Database=$SQL_DB_SVC12;",
            "Database=$SQL_DB_SVC12;Database=$SQL_DB_SVC12;",
        ),
    ),
)
def test_sql_audit_count_rejects_insecure_or_duplicate_connection_properties(
    old: str,
    new: str,
) -> None:
    source = _sql_audit_count_source().replace(old, new, 1)

    errors = _validate_sql_audit_count(source)

    assert any("exactly one reachable" in error for error in errors), errors


def test_sql_audit_count_rejects_unconditional_failure_exit_after_emit() -> None:
    source = _sql_audit_count_source().replace(
        "    audit_count == 3 or sys.exit(1)",
        "    sys.exit(1)\n    audit_count == 3 or sys.exit(1)",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("unconditional sys.exit" in error for error in errors), errors


def test_sql_audit_count_accepts_known_metadata_reads() -> None:
    guard = "    audit_count == 3 or sys.exit(1)\n"
    metadata_reads = (
        '    svc12_cursor.execute("SELECT SCHEMA_NAME(schema_id), name, '
        'ledger_type_desc FROM sys.tables")\n'
        '    svc12_cursor.execute("SELECT path, last_digest_block_id FROM '
        'sys.database_ledger_digest_locations WHERE is_current = 1")\n'
    )
    source = _sql_audit_count_source().replace(guard, guard + metadata_reads, 1)

    assert _validate_sql_audit_count(source) == []


def test_sql_audit_count_rejects_try_else() -> None:
    source = _sql_audit_count_source().replace(
        "finally:\n",
        "except Exception:\n    raise\nelse:\n    pass\nfinally:\n",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("without except or else" in error for error in errors), errors


def test_sql_audit_count_rejects_dynamic_exit() -> None:
    source = _sql_audit_count_source().replace(
        "    audit_count == 3 or sys.exit(1)",
        "    code = 0\n    sys.exit(code)\n    audit_count == 3 or sys.exit(1)",
        1,
    )

    errors = _validate_sql_audit_count(source)

    assert any("success or dynamic sys.exit" in error for error in errors), errors


@pytest.mark.parametrize(
    ("old", "new", "error_fragment"),
    (
        (
            "from contextlib import ExitStack\n",
            "from contextlib import ExitStack\nfrom contextlib import ExitStack\n",
            "ExitStack",
        ),
        (
            "import os, re, sys\n",
            "import os, re, sys\nimport os\n",
            "protected runtime symbols",
        ),
        (
            "import os, re, sys\n",
            "import os as os_alias, re, sys\n",
            "protected runtime symbols",
        ),
    ),
)
def test_sql_audit_count_rejects_duplicate_or_aliased_runtime_imports(
    old: str,
    new: str,
    error_fragment: str,
) -> None:
    source = _sql_audit_count_source().replace(old, new, 1)

    errors = _validate_sql_audit_count(source)

    assert any(error_fragment in error for error in errors), errors


def test_sql_audit_metadata_accepts_append_only_table_and_current_acl_digest() -> None:
    assert _validate_sql_audit_metadata(_sql_audit_metadata_source()) == []


@pytest.mark.parametrize(
    ("old", "new", "error_fragment"),
    (
        (
            "SELECT SCHEMA_NAME(schema_id), name, ledger_type_desc FROM sys.tables",
            "SELECT name FROM sys.tables",
            "sys.tables",
        ),
        (
            '("dbo", audit_table)',
            '("audit", audit_table)',
            "dbo",
        ),
        (
            'audit_ledger_type == "APPEND_ONLY_LEDGER_TABLE"',
            'audit_ledger_type == "UPDATABLE_LEDGER_TABLE"',
            "APPEND_ONLY_LEDGER_TABLE",
        ),
        (
            "next(filter(None, [audit_ledger_ok]))",
            "print(audit_ledger_ok)",
            "fail closed",
        ),
        (
            'os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"]',
            'os.environ["OTHER_ENDPOINT"]',
            "CONFIDENTIAL_LEDGER_ENDPOINT",
        ),
        (
            "WHERE is_current = 1",
            "WHERE is_current = 0",
            "is_current = 1",
        ),
        (
            "urlparse(str(row[0])).hostname == ledger_host",
            "True",
            "same host",
        ),
        (
            "row[1] is not None",
            "True",
            "last_digest_block_id",
        ),
        (
            "next(filter(None, [digest_ready]))",
            "print(digest_ready)",
            "fail closed",
        ),
    ),
)
def test_sql_audit_metadata_rejects_wrong_or_non_enforced_metadata(
    old: str,
    new: str,
    error_fragment: str,
) -> None:
    source = _sql_audit_metadata_source()
    assert old in source

    errors = _validate_sql_audit_metadata(source.replace(old, new, 1))

    assert any(error_fragment in error for error in errors), errors


def test_sql_audit_metadata_rejects_missing_digest_rows_fetch() -> None:
    source = _sql_audit_metadata_source().replace(
        "    digest_rows = svc12_cursor.fetchall()\n",
        "    digest_rows = []\n",
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("fetchall" in error for error in errors), errors


def test_sql_audit_metadata_rejects_separate_cursor() -> None:
    source = _sql_audit_metadata_source().replace(
        '    svc12_cursor.execute("SELECT path, last_digest_block_id',
        '    other_cursor.execute("SELECT path, last_digest_block_id',
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("SVC-12 cursor" in error for error in errors), errors


@pytest.mark.parametrize(
    "binding",
    (
        "from builtins import bool as next\n",
        "from builtins import bool as any\n",
        "from urllib.parse import urlparse as str\n",
    ),
)
def test_sql_audit_metadata_rejects_protected_import_aliases(
    binding: str,
) -> None:
    source = _sql_audit_metadata_source().replace(
        "import os, re, sys\n",
        "import os, re, sys\n" + binding,
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("protected runtime symbols" in error for error in errors), errors


@pytest.mark.parametrize(
    "mutation",
    (
        "os.environ = {}\n",
        'os.environ["CONFIDENTIAL_LEDGER_ENDPOINT"] = "https://other.invalid"\n',
    ),
)
def test_sql_audit_metadata_rejects_os_environ_mutation(
    mutation: str,
) -> None:
    source = _sql_audit_metadata_source().replace(
        "svc12_connection = ExitStack()\n",
        mutation + "svc12_connection = ExitStack()\n",
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("protected runtime symbols" in error for error in errors), errors


def test_sql_audit_metadata_rejects_constant_false_assert() -> None:
    source = _sql_audit_metadata_source().replace(
        '    svc12_cursor.execute("SELECT SCHEMA_NAME',
        '    assert False\n    svc12_cursor.execute("SELECT SCHEMA_NAME',
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("assert False" in error for error in errors), errors


@pytest.mark.parametrize("wrapper", ("assignment", "nested"))
def test_sql_audit_metadata_rejects_non_direct_unapproved_execute(
    wrapper: str,
) -> None:
    source = _sql_audit_metadata_source()
    anchor = '    svc12_cursor.execute("SELECT SCHEMA_NAME'
    if wrapper == "assignment":
        extra = '    ignored = svc12_cursor.execute("DELETE FROM [dbo].[audit_records]")\n'
    else:
        extra = '    print(svc12_cursor.execute("DELETE FROM [dbo].[audit_records]"))\n'
    source = source.replace(anchor, extra + anchor, 1)

    errors = _validate_sql_audit_metadata(source)

    assert any("allows only direct" in error for error in errors), errors


@pytest.mark.parametrize("guard_name", ("audit_ledger_ok", "digest_ready"))
def test_sql_audit_metadata_rejects_unknown_sql_before_guard(
    guard_name: str,
) -> None:
    source = _sql_audit_metadata_source()
    guard = f"    next(filter(None, [{guard_name}]))\n"
    source = source.replace(
        guard,
        '    svc12_cursor.execute("UPDATE [dbo].[audit_records] SET x = 1")\n'
        + guard,
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("allows only direct" in error for error in errors), errors


def test_sql_audit_metadata_rejects_top_level_assert_false_before_try() -> None:
    source = _sql_audit_metadata_source().replace(
        "try:\n",
        "assert False\ntry:\n",
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("top-level try after `assert False`" in error for error in errors), errors


def test_sql_audit_metadata_rejects_reversed_ledger_and_digest_guards() -> None:
    source = _sql_audit_metadata_source()
    ledger_guard = "    next(filter(None, [audit_ledger_ok]))\n"
    digest_guard = "    next(filter(None, [digest_ready]))\n"
    assert ledger_guard in source and digest_guard in source
    source = source.replace(ledger_guard, "", 1).replace(
        digest_guard,
        digest_guard + ledger_guard,
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("append-only table guard" in error for error in errors), errors


def test_sql_audit_metadata_rejects_cursor_alias_with_extra_sql() -> None:
    source = _sql_audit_metadata_source().replace(
        '    svc12_cursor.execute("SELECT SCHEMA_NAME',
        "    other_cursor = svc12_cursor\n"
        '    other_cursor.execute("DELETE FROM [dbo].[audit_records]")\n'
        '    svc12_cursor.execute("SELECT SCHEMA_NAME',
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("must not alias its SVC-12 cursor" in error for error in errors), errors


@pytest.mark.parametrize(
    "mutation",
    (
        'os.environ.update({"CONFIDENTIAL_LEDGER_ENDPOINT": "https://other.invalid"})\n',
        'os.environ.setdefault("CONFIDENTIAL_LEDGER_ENDPOINT", "https://other.invalid")\n',
        'os.putenv("CONFIDENTIAL_LEDGER_ENDPOINT", "https://other.invalid")\n',
        'os.unsetenv("CONFIDENTIAL_LEDGER_ENDPOINT")\n',
    ),
)
def test_sql_audit_metadata_rejects_environment_mutator_calls(
    mutation: str,
) -> None:
    source = _sql_audit_metadata_source().replace(
        "svc12_connection = ExitStack()\n",
        mutation + "svc12_connection = ExitStack()\n",
        1,
    )

    errors = _validate_sql_audit_metadata(source)

    assert any("protected runtime symbols" in error for error in errors), errors
