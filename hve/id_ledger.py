"""hve/id_ledger.py — ID 台帳の決定的検査と生成（FR-IDL-01）。

生成されるアプリの ``docs/catalog`` の ID（APP・画面・サービス）の相互参照を、
モデルの QA Step ではなくコードで検査する。台帳の読込は
``hve.catalog_parsers.parse_id_ledger`` を単一実装とする。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

try:
    from .catalog_parsers import (
        ID_LEDGER_PATH,
        LedgerEntry,
        parse_app_catalog,
        parse_id_ledger,
        parse_screen_catalog,
        parse_service_app_mapping,
        parse_service_catalog,
    )
except ImportError:  # pragma: no cover - script execution path
    from catalog_parsers import (  # type: ignore[no-redef]
        ID_LEDGER_PATH,
        LedgerEntry,
        parse_app_catalog,
        parse_id_ledger,
        parse_screen_catalog,
        parse_service_app_mapping,
        parse_service_catalog,
    )

KIND_PATTERNS = {
    "APP": re.compile(r"^APP-\d{2,3}$"),
    "SCR": re.compile(r"^APP-\d{2,3}-S\d{3,}$"),
    "SVC": re.compile(r"^SVC-[A-Za-z0-9_\-]+$"),
}
STATES = ("active", "planned", "deprecated")
_MATRIX_PATH = "docs/catalog/service-catalog-matrix.md"
_TEST_SPEC_DIR = "docs/test-specs"
_TEST_ID_CELL = re.compile(r"\b(?:TEST|T|UT|IT|E2E|AT)-[A-Za-z0-9][A-Za-z0-9_\-]*")


@dataclass(frozen=True)
class Finding:
    """検査で見つかった 1 件の違反。"""

    rule: str
    id: str
    message: str

    def format(self) -> str:
        return f"[{self.rule}] {self.id}: {self.message}"


def _overlaps(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def _ledger_rules(entries: Sequence[LedgerEntry], repo_root: Path) -> List[Finding]:
    findings: List[Finding] = []
    ids = [e.id for e in entries]
    known = set(ids)
    for entry in entries:
        if ids.count(entry.id) > 1:
            findings.append(Finding("duplicate-id", entry.id, f"台帳で重複している（{ID_LEDGER_PATH}:{entry.line}）"))
        pattern = KIND_PATTERNS.get(entry.kind)
        if pattern is None or not pattern.match(entry.id):
            findings.append(Finding("kind-format", entry.id, f"種別 {entry.kind!r} と ID の形式が一致しない"))
        if entry.state not in STATES:
            findings.append(Finding("state", entry.id, f"状態 {entry.state!r} は {'/'.join(STATES)} のいずれでもない"))
        for parent in entry.parent_ids:
            if parent not in known:
                findings.append(Finding("missing-parent", entry.id, f"親 ID {parent} が台帳に無い"))
        if entry.kind == "SCR" and entry.parent_ids and not entry.id.startswith(entry.parent_ids[0] + "-"):
            findings.append(Finding("missing-parent", entry.id, f"画面の親 {entry.parent_ids[0]} が ID の接頭辞と一致しない"))
        if entry.state == "active":
            if not entry.detail_doc or not (repo_root / entry.detail_doc).is_file():
                findings.append(Finding("missing-detail-doc", entry.id, f"詳細文書 {entry.detail_doc or '(未記入)'} が存在しない"))
    active = [e for e in entries if e.state == "active"]
    for index, left in enumerate(active):
        for right in active[index + 1:]:
            if left.kind != right.kind:
                continue
            for a in left.write_prefixes:
                for b in right.write_prefixes:
                    if _overlaps(a, b):
                        findings.append(Finding(
                            "prefix-overlap", left.id,
                            f"書込みパス接頭辞 {a} が {right.id} の {b} と重なる",
                        ))
    return findings


def _catalog_rules(entries: Sequence[LedgerEntry], repo_root: Path) -> List[Finding]:
    known = {e.id for e in entries}
    catalog_ids = [*parse_app_catalog(repo_root), *parse_screen_catalog(repo_root), *parse_service_catalog(repo_root)]
    return [
        Finding("catalog-id-missing", catalog_id, "カタログにあるが台帳に無い")
        for catalog_id in dict.fromkeys(catalog_ids)
        if catalog_id not in known
    ]


def _table_column_values(text: str, header: str) -> Iterable[str]:
    column: Optional[int] = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            column = None
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if header in cols:
            column = cols.index(header)
            continue
        if column is None or re.match(r"^\|\s*[-:\s|]+\s*\|?$", s) or column >= len(cols):
            continue
        yield cols[column].strip("`")


def _reference_rules(entries: Sequence[LedgerEntry], repo_root: Path) -> List[Finding]:
    findings: List[Finding] = []
    screens = {e.id for e in entries if e.kind == "SCR"}
    matrix = repo_root / _MATRIX_PATH
    if matrix.is_file():
        for value in _table_column_values(matrix.read_text(encoding="utf-8"), "画面ID"):
            if value in {"", "—", "-"}:
                continue
            if value.upper().startswith("TBD") or value not in screens:
                findings.append(Finding("unresolved-screen-ref", value or "(空)", f"{_MATRIX_PATH} の画面 ID が台帳の画面を指していない"))
    spec_dir = repo_root / _TEST_SPEC_DIR
    for entry in entries:
        if entry.kind not in {"SCR", "SVC"}:
            continue
        spec = spec_dir / f"{entry.id}-test-spec.md"
        if not spec.is_file():
            continue
        prefix = f"TEST-{entry.id}-"
        bad = sorted({m.group(0) for m in _TEST_ID_CELL.finditer(spec.read_text(encoding="utf-8")) if not m.group(0).startswith(prefix)})
        if bad:
            findings.append(Finding(
                "test-id-naming", entry.id,
                f"{spec.relative_to(repo_root).as_posix()} のテスト ID が {prefix} で始まらない: {', '.join(bad[:5])}",
            ))
    return findings


def check_id_ledger(repo_root: Path) -> List[Finding]:
    """台帳を検査して違反を返す。台帳が無い場合は空リスト（FR-IDL-01）。"""
    repo_root = Path(repo_root)
    if not (repo_root / ID_LEDGER_PATH).is_file():
        return []
    entries = parse_id_ledger(repo_root)
    return [
        *_ledger_rules(entries, repo_root),
        *_catalog_rules(entries, repo_root),
        *_reference_rules(entries, repo_root),
    ]


def _find_detail_doc(repo_root: Path, directory: str, entry_id: str) -> str:
    base = repo_root / directory
    if not base.is_dir():
        return ""
    candidates = sorted(
        (p for p in base.glob(f"{entry_id}*.md") if p.stem == entry_id or p.name.startswith(f"{entry_id}-")),
        key=lambda p: (len(p.name), p.name),
    )
    return candidates[0].relative_to(repo_root).as_posix() if candidates else ""


def bootstrap_ledger_rows(repo_root: Path) -> List[LedgerEntry]:
    """既存のカタログと詳細文書から台帳の行を作る（詳細文書が無い行は planned）。"""
    repo_root = Path(repo_root)
    rows: List[LedgerEntry] = []
    for app_id in parse_app_catalog(repo_root):
        rows.append(LedgerEntry(app_id, "APP", app_id, (), "active", "docs/catalog/app-catalog.md", ()))
    for screen_id in parse_screen_catalog(repo_root):
        doc = _find_detail_doc(repo_root, "docs/screen", screen_id)
        rows.append(LedgerEntry(
            screen_id, "SCR", screen_id, (screen_id.rsplit("-", 1)[0],), "active" if doc else "planned", doc,
            (f"src/app/{screen_id}/", f"src/test/ui/{screen_id}/"),
        ))
    mapping = parse_service_app_mapping(repo_root)
    for service_id in parse_service_catalog(repo_root):
        doc = _find_detail_doc(repo_root, "docs/services", service_id)
        rows.append(LedgerEntry(
            service_id, "SVC", service_id, tuple(mapping.get(service_id, ())), "active" if doc else "planned", doc,
            (f"src/api/{service_id}-", f"src/test/api/{service_id}.Tests/"),
        ))
    return rows


def render_ledger(rows: Sequence[LedgerEntry]) -> str:
    """台帳の行を Markdown に書き出す。"""
    lines = [
        "# ID 台帳",
        "",
        "生成されるアプリの APP・画面・サービスの ID を管理する台帳（FR-IDL-01）。"
        "検査: `python .github/scripts/check-id-ledger.py`。",
        "",
        "| ID | 種別 | 名前 | 親 ID | 状態 | 詳細文書 | 書込みパス接頭辞 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.id} | {row.kind} | {row.name} | {', '.join(row.parent_ids) or '-'} | {row.state} | "
            f"{row.detail_doc or '-'} | {'; '.join(row.write_prefixes) or '-'} |"
        )
    return "\n".join(lines) + "\n"
