"""FR-IDL-01: ID 台帳と相互参照の決定的検査（N6-1）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hve.catalog_parsers import parse_id_ledger
from hve.id_ledger import bootstrap_ledger_rows, check_id_ledger, render_ledger

_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / ".github" / "scripts" / "check-id-ledger.py"

_HEADER = "| ID | 種別 | 名前 | 親 ID | 状態 | 詳細文書 | 書込みパス接頭辞 |\n|---|---|---|---|---|---|---|\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path, *, ledger_rows: str | None = None, matrix_screen: str = "APP-009-S001",
          test_id: str = "TEST-APP-009-S001-UI-001") -> Path:
    _write(tmp_path, "docs/catalog/app-catalog.md", "| APP-ID | アーキタイプ名 |\n|---|---|\n| APP-009 | 会員サポート |\n")
    _write(tmp_path, "docs/catalog/screen-catalog-APP-009.md", "| 画面ID | 画面名 |\n|---|---|\n| S001 | 会員ポータル |\n")
    _write(tmp_path, "docs/catalog/service-catalog.md", "## A. サマリ（表）\n\n| サービスID | サービス名 | 利用APP |\n|---|---|---|\n| SVC-09 | 会員サポート | APP-009 |\n")
    _write(tmp_path, "docs/catalog/service-catalog-matrix.md",
           "| 画面ID | 画面名 | 所属APP |\n|---|---|---|\n" f"| {matrix_screen} | 会員ポータル | APP-009 |\n")
    _write(tmp_path, "docs/screen/APP-009-S001.md", "# S001\n")
    _write(tmp_path, "docs/services/SVC-09.md", "# SVC-09\n")
    _write(tmp_path, "docs/test-specs/APP-009-S001-test-spec.md", f"| テストID |\n|---|\n| {test_id} |\n")
    if ledger_rows is None:
        ledger_rows = (
            "| APP-009 | APP | 会員サポート | - | active | docs/catalog/app-catalog.md | - |\n"
            "| APP-009-S001 | SCR | 会員ポータル | APP-009 | active | docs/screen/APP-009-S001.md | src/app/APP-009-S001/; src/test/ui/APP-009-S001/ |\n"
            "| SVC-09 | SVC | 会員サポート | APP-009 | active | docs/services/SVC-09.md | src/api/SVC-09-; src/test/api/SVC-09.Tests/ |\n"
        )
    _write(tmp_path, "docs/catalog/id-ledger.md", "# ID 台帳\n\n" + _HEADER + ledger_rows)
    return tmp_path


def _rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


def test_parser_reads_all_columns(tmp_path: Path) -> None:
    entries = parse_id_ledger(_repo(tmp_path))
    by_id = {entry.id: entry for entry in entries}
    assert set(by_id) == {"APP-009", "APP-009-S001", "SVC-09"}
    screen = by_id["APP-009-S001"]
    assert (screen.kind, screen.parent_ids, screen.state) == ("SCR", ("APP-009",), "active")
    assert screen.write_prefixes == ("src/app/APP-009-S001/", "src/test/ui/APP-009-S001/")
    assert by_id["APP-009"].write_prefixes == ()


def test_consistent_repository_has_no_findings(tmp_path: Path) -> None:
    assert check_id_ledger(_repo(tmp_path)) == []


def test_missing_ledger_is_not_checked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/catalog/id-ledger.md").unlink()
    assert check_id_ledger(repo) == []


@pytest.mark.parametrize(
    ("extra_row", "rule"),
    [
        ("| SVC-09 | SVC | 重複 | APP-009 | planned | - | - |\n", "duplicate-id"),
        ("| SVC-10 | APP | 形式違い | - | planned | - | - |\n", "kind-format"),
        ("| APP-010-S001 | SCR | 親なし | APP-010 | planned | - | - |\n", "missing-parent"),
        ("| SVC-11 | SVC | 文書なし | APP-009 | active | docs/services/SVC-11.md | src/api/SVC-11- |\n", "missing-detail-doc"),
        ("| SVC-12 | SVC | 状態違い | APP-009 | done | - | - |\n", "state"),
        ("| SVC-13 | SVC | 接頭辞重複 | APP-009 | planned | - | src/api/SVC-09-extra/ |\n", None),
    ],
)
def test_ledger_rules(tmp_path: Path, extra_row: str, rule: str | None) -> None:
    base = (
        "| APP-009 | APP | 会員サポート | - | active | docs/catalog/app-catalog.md | - |\n"
        "| APP-009-S001 | SCR | 会員ポータル | APP-009 | active | docs/screen/APP-009-S001.md | src/app/APP-009-S001/ |\n"
        "| SVC-09 | SVC | 会員サポート | APP-009 | active | docs/services/SVC-09.md | src/api/SVC-09- |\n"
    )
    findings = check_id_ledger(_repo(tmp_path, ledger_rows=base + extra_row))
    if rule is None:
        # planned 行は所有範囲の重なり検査の対象外（active どうしだけを比べる）
        assert "prefix-overlap" not in _rules(findings)
    else:
        assert rule in _rules(findings)


def test_active_write_prefixes_must_not_overlap(tmp_path: Path) -> None:
    rows = (
        "| APP-009 | APP | 会員サポート | - | active | docs/catalog/app-catalog.md | - |\n"
        "| APP-009-S001 | SCR | 会員ポータル | APP-009 | active | docs/screen/APP-009-S001.md | src/app/ |\n"
        "| SVC-09 | SVC | 会員サポート | APP-009 | active | docs/services/SVC-09.md | src/api/SVC-09- |\n"
        "| APP-009-S002 | SCR | 別画面 | APP-009 | active | docs/screen/APP-009-S001.md | src/app/APP-009-S002/ |\n"
    )
    findings = check_id_ledger(_repo(tmp_path, ledger_rows=rows))
    assert "prefix-overlap" in _rules(findings)


def test_catalog_ids_must_be_in_ledger(tmp_path: Path) -> None:
    rows = "| APP-009 | APP | 会員サポート | - | active | docs/catalog/app-catalog.md | - |\n"
    findings = check_id_ledger(_repo(tmp_path, ledger_rows=rows))
    missing = {f.id for f in findings if f.rule == "catalog-id-missing"}
    assert missing == {"APP-009-S001", "SVC-09"}


def test_drift_unresolved_screen_reference_is_detected(tmp_path: Path) -> None:
    """既存ドリフト: service-catalog-matrix の画面 ID が TBD のまま（整合性レポート No.1）。"""
    findings = check_id_ledger(_repo(tmp_path, matrix_screen="TBD"))
    assert "unresolved-screen-ref" in _rules(findings)


def test_drift_test_id_naming_is_detected(tmp_path: Path) -> None:
    """既存ドリフト: テスト ID の命名が 5 通り（整合性レポート No.6）。"""
    findings = check_id_ledger(_repo(tmp_path, test_id="T-APP-009-S001-001"))
    assert "test-id-naming" in _rules(findings)


def test_bootstrap_builds_rows_from_catalogs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs/catalog/id-ledger.md").unlink()
    rows = bootstrap_ledger_rows(repo)
    by_id = {row.id: row for row in rows}
    assert by_id["APP-009-S001"].detail_doc == "docs/screen/APP-009-S001.md"
    assert by_id["APP-009-S001"].state == "active"
    assert by_id["SVC-09"].parent_ids == ("APP-009",)
    assert by_id["SVC-09"].write_prefixes == ("src/api/SVC-09-", "src/test/api/SVC-09.Tests/")
    (repo / "docs/catalog/id-ledger.md").write_text(render_ledger(rows), encoding="utf-8")
    assert check_id_ledger(repo) == []


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(_CLI), *args], capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, matrix_screen="TBD")
    assert _cli("--repo-root", str(repo)).returncode == 1
    warn = _cli("--repo-root", str(repo), "--warn-only")
    assert warn.returncode == 0
    assert "unresolved-screen-ref" in warn.stdout
    clean = _repo(tmp_path / "clean")
    assert _cli("--repo-root", str(clean)).returncode == 0
