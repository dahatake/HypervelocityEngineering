"""FR-APPREQ-01/02: APP別要求定義書の決定的schemaとcoverage契約。"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _api():
    return importlib.import_module("hve.application_requirements")


_VALID_DOC = """# APP-001 要求定義書

- Schema-Version: 1
- APP-ID: APP-001
- APP名: 会員管理
- Document-Status: active

## Requirements

| Requirement ID | Status | Requirement | Source | Acceptance Criteria | Blocker |
|---|---|---|---|---|---|
| APP-001-FR-001 | confirmed | 会員を登録できる | docs/catalog/use-case-catalog.md#UC-001 | 登録結果を確認できる | no |
| APP-001-NFR-001 | source-backed | 操作を監査できる | knowledge/D09.md | 監査記録を検索できる | no |
| APP-001-C-001 | TBD | 保持期間を確定する | TBD | 保持期間が承認される | yes |
"""


def _write_requirement(root: Path, app_id: str = "APP-001", text: str = _VALID_DOC) -> Path:
    path = root / "docs" / f"architectural-requirements-app-{app_id.removeprefix('APP-')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_catalog(root: Path, *app_ids: str) -> Path:
    path = root / "docs" / "catalog" / "app-catalog.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {app_id} | app-{app_id} |" for app_id in app_ids)
    path.write_text(
        "# App Catalog\n\n| APP-ID | APP名 |\n|---|---|\n" + rows + "\n",
        encoding="utf-8",
    )
    return path


def test_canonical_requirement_path_is_stable_and_safe() -> None:
    api = _api()
    assert api.canonical_requirement_path("APP-001") == Path(
        "docs/architectural-requirements-app-001.md"
    )
    for invalid in ("APP-01", "APP-0001", "app-001", "../APP-001", "APP-001/x"):
        with pytest.raises(api.ApplicationRequirementError):
            api.canonical_requirement_path(invalid)


@pytest.mark.parametrize(
    "body,expected",
    [
        ("<!-- app-ids: APP-002, APP-001 -->", ("APP-002", "APP-001")),
        ("<!-- app-id: APP-004 -->", ("APP-004",)),
        (
            "### 対象アプリケーション (APP-ID) — 複数指定可（任意）\n"
            "APP-003, APP-001\n\n### 次の項目\nvalue",
            ("APP-003", "APP-001"),
        ),
        ("### 対象アプリケーション (APP-ID)\n_No response_", ()),
        ("no app selection", ()),
    ],
)
def test_cloud_issue_body_app_ids_are_extracted_deterministically(
    body: str, expected: tuple[str, ...]
) -> None:
    assert _api().extract_application_requirement_app_ids(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "<!-- app-ids: APP-01 -->",
        "<!-- app-ids: APP-001 --><!-- app-ids: APP-002 -->",
        "### 対象アプリケーション (APP-ID)\nAPP-001\n\n"
        "### 対象アプリケーション (APP-ID)\nAPP-002",
    ],
)
def test_cloud_issue_body_app_ids_fail_closed_on_ambiguous_or_invalid_input(
    body: str,
) -> None:
    api = _api()
    with pytest.raises(api.ApplicationRequirementError):
        api.extract_application_requirement_app_ids(body)


def test_valid_document_round_trips_fixed_schema(tmp_path: Path) -> None:
    api = _api()
    path = _write_requirement(tmp_path)
    document = api.parse_requirement_document(path, expected_app_id="APP-001")

    assert document.schema_version == 1
    assert document.app_id == "APP-001"
    assert document.app_name == "会員管理"
    assert document.document_status == "active"
    assert [row.requirement_id for row in document.rows] == [
        "APP-001-FR-001",
        "APP-001-NFR-001",
        "APP-001-C-001",
    ]
    assert document.blocking_requirement_ids == ("APP-001-C-001",)
    assert api.validate_requirement_document(path, expected_app_id="APP-001") == []


@pytest.mark.parametrize(
    "old,new,error_token",
    [
        ("APP-001-FR-001", "APP-002-FR-001", "APP-ID"),
        ("APP-001-NFR-001", "APP-001-NFR-01", "Requirement ID"),
        ("APP-001-NFR-001", "APP-001-NFR-000", "001〜999"),
        ("source-backed", "guessed", "Status"),
        ("| no |", "| maybe |", "Blocker"),
        ("- Schema-Version: 1", "- Schema-Version: 2", "Schema-Version"),
    ],
)
def test_invalid_document_values_fail_closed(
    tmp_path: Path, old: str, new: str, error_token: str
) -> None:
    api = _api()
    path = _write_requirement(tmp_path, text=_VALID_DOC.replace(old, new, 1))
    errors = api.validate_requirement_document(path, expected_app_id="APP-001")
    assert errors
    assert any(error_token in error for error in errors)


def test_duplicate_requirement_ids_are_rejected(tmp_path: Path) -> None:
    api = _api()
    duplicate = _VALID_DOC.replace(
        "APP-001-NFR-001", "APP-001-FR-001", 1
    )
    path = _write_requirement(tmp_path, text=duplicate)
    errors = api.validate_requirement_document(path, expected_app_id="APP-001")
    assert any("duplicate" in error.casefold() for error in errors)


def test_escaped_pipe_is_a_cell_value_and_later_tables_are_out_of_scope(
    tmp_path: Path,
) -> None:
    api = _api()
    text = _VALID_DOC.replace("会員を登録できる", r"会員を登録 \| 更新できる")
    text += """

## Verification

| Check | Result |
|---|---|
| schema | PASS |
"""
    document = api.parse_requirement_document(_write_requirement(tmp_path, text=text))
    assert document.rows[0].requirement == r"会員を登録 \| 更新できる"


def test_document_app_id_must_match_canonical_filename(tmp_path: Path) -> None:
    api = _api()
    path = _write_requirement(
        tmp_path,
        text=_VALID_DOC.replace("APP-001", "APP-002"),
    )
    errors = api.validate_requirement_document(path)
    assert any("canonical ファイル名" in error for error in errors)


def test_next_requirement_id_preserves_existing_ids_and_fails_at_999(tmp_path: Path) -> None:
    api = _api()
    with_gap = _VALID_DOC.replace(
        "| APP-001-NFR-001",
        "| APP-001-FR-003 | source-backed | 既存追記 | QA | 追記を保持できる | no |\n"
        "| APP-001-NFR-001",
    )
    path = _write_requirement(tmp_path, text=with_gap)
    document = api.parse_requirement_document(path)
    assert api.next_requirement_id(document, "FR") == "APP-001-FR-004"

    exhausted = _VALID_DOC.replace("APP-001-FR-001", "APP-001-FR-999")
    exhausted_doc = api.parse_requirement_document(
        _write_requirement(tmp_path, text=exhausted)
    )
    with pytest.raises(api.ApplicationRequirementError):
        api.next_requirement_id(exhausted_doc, "FR")


def test_upsert_preserves_confirmed_content_source_backed_ids_and_human_rows(
    tmp_path: Path,
) -> None:
    api = _api()
    existing = api.parse_requirement_document(_write_requirement(tmp_path))
    proposed = api.parse_requirement_document(
        _write_requirement(
            tmp_path,
            text=_VALID_DOC.replace(
                "会員を登録できる", "推論で変更した内容"
            ).replace("APP-001-NFR-001", "APP-001-NFR-009"),
        )
    )

    result = api.merge_requirement_documents(existing, proposed)
    rows = {row.requirement_id: row for row in result.document.rows}
    assert rows["APP-001-FR-001"].requirement == "会員を登録できる"
    assert "APP-001-NFR-001" in rows
    assert "APP-001-C-001" in rows
    assert "APP-001-NFR-009" not in rows
    assert any("APP-001-FR-001" in conflict for conflict in result.conflicts)


def test_upsert_accepts_only_the_next_id_per_kind(tmp_path: Path) -> None:
    api = _api()
    existing = api.parse_requirement_document(_write_requirement(tmp_path))
    proposed_text = _VALID_DOC.replace(
        "| APP-001-NFR-001",
        "| APP-001-NFR-001",
    ).replace(
        "| APP-001-C-001",
        "| APP-001-NFR-002 | source-backed | 新規追記 | QA | 追記を確認できる | no |\n"
        "| APP-001-C-001",
    )
    proposed = api.parse_requirement_document(
        _write_requirement(tmp_path, text=proposed_text)
    )
    result = api.merge_requirement_documents(existing, proposed)
    assert "APP-001-NFR-002" in {
        row.requirement_id for row in result.document.rows
    }


def test_coverage_reports_missing_and_preserves_orphans(tmp_path: Path) -> None:
    api = _api()
    _write_catalog(tmp_path, "APP-001", "APP-002")
    _write_requirement(tmp_path, "APP-001")
    _write_requirement(
        tmp_path,
        "APP-003",
        _VALID_DOC.replace("APP-001", "APP-003"),
    )

    coverage = api.validate_requirement_coverage(tmp_path)
    assert any("APP-002" in error for error in coverage.errors)
    assert coverage.orphan_paths == (
        Path("docs/architectural-requirements-app-003.md"),
    )
    assert (tmp_path / coverage.orphan_paths[0]).is_file()
