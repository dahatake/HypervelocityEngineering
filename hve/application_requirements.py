"""APP 別要求定義書の schema・scope・traceability 契約。

FR-APPREQ-01〜05 の決定的な判定をこのモジュールへ集約し、CLI / GUI の
Runner と Cloud 向け検証コードで同じ実装を再利用する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:  # pragma: no cover - script-style import compatibility
    from .app_arch_filter import resolve_app_arch_scope
    from .catalog_parsers import parse_catalog, parse_service_app_mapping
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover
    from hve.app_arch_filter import resolve_app_arch_scope
    from hve.catalog_parsers import parse_catalog, parse_service_app_mapping
    from hve.prompt_loader import load_prompt_file


_APP_ID_RE = re.compile(r"^APP-\d{3}$")
_REQUIREMENT_ID_RE = re.compile(r"^(APP-\d{3})-(FR|NFR|C)-(\d{3})$")
_REQUIREMENT_FILE_RE = re.compile(r"^architectural-requirements-app-(\d{3})\.md$")
_METADATA_KEYS = ("Schema-Version", "APP-ID", "APP名", "Document-Status")
_TABLE_HEADER = (
    "Requirement ID",
    "Status",
    "Requirement",
    "Source",
    "Acceptance Criteria",
    "Blocker",
)
_ALLOWED_STATUSES = frozenset({"confirmed", "source-backed", "TBD"})
_ALLOWED_BLOCKERS = frozenset({"yes", "no"})
_TRACE_KEYS = (
    "APP-IDs",
    "Requirement-IDs",
    "Requirement-Documents",
    "Unresolved-Blockers",
)
_TARGET_WORKFLOWS = frozenset(
    {"aas", "ada", "aad-web", "asdw-web", "adfd", "adfdv", "aag", "aagd", "aar"}
)
_ARCH_FILTER_WORKFLOWS = frozenset({"aad-web", "asdw-web", "adfd", "adfdv"})


class ApplicationRequirementError(ValueError):
    """APP 要求契約を決定的に満たせない場合の例外。"""


@dataclass(frozen=True)
class RequirementRow:
    """要求表の 1 行。"""

    requirement_id: str
    status: str
    requirement: str
    source: str
    acceptance_criteria: str
    blocker: str

    @property
    def app_id(self) -> str:
        match = _REQUIREMENT_ID_RE.fullmatch(self.requirement_id)
        return match.group(1) if match else ""

    @property
    def kind(self) -> str:
        match = _REQUIREMENT_ID_RE.fullmatch(self.requirement_id)
        return match.group(2) if match else ""

    @property
    def sequence(self) -> int:
        match = _REQUIREMENT_ID_RE.fullmatch(self.requirement_id)
        return int(match.group(3)) if match else 0


@dataclass(frozen=True)
class RequirementDocument:
    """検証済み APP 要求定義書。"""

    path: Path
    schema_version: int
    app_id: str
    app_name: str
    document_status: str
    rows: tuple[RequirementRow, ...]

    @property
    def blocking_requirement_ids(self) -> tuple[str, ...]:
        return tuple(row.requirement_id for row in self.rows if row.blocker == "yes")

    @property
    def unresolved_blocking_requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            row.requirement_id
            for row in self.rows
            if row.status == "TBD" and row.blocker == "yes"
        )


@dataclass(frozen=True)
class RequirementCoverage:
    """app-catalog と APP 要求定義書群の coverage 結果。"""

    app_ids: tuple[str, ...]
    errors: tuple[str, ...]
    orphan_paths: tuple[Path, ...]


@dataclass(frozen=True)
class RequirementMergeResult:
    """既存行を保護した決定的 upsert の結果。"""

    document: RequirementDocument
    conflicts: tuple[str, ...]


def canonical_requirement_path(app_id: str) -> Path:
    """APP-ID の canonical なリポジトリ相対パスを返す。"""
    if not isinstance(app_id, str) or not _APP_ID_RE.fullmatch(app_id):
        raise ApplicationRequirementError(
            f"APP-ID は APP-NNN 形式でなければなりません: {app_id!r}"
        )
    return Path("docs") / f"architectural-requirements-app-{app_id[4:]}.md"


def _split_markdown_row(line: str) -> list[str]:
    """エスケープ済み pipe を保持して Markdown table のセルを分割する。"""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped[1:-1]:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
            current.append(char)
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _parse_document(path: Path, expected_app_id: str | None) -> tuple[RequirementDocument | None, list[str]]:
    errors: list[str] = []
    if expected_app_id is not None and not _APP_ID_RE.fullmatch(expected_app_id):
        return None, [f"expected APP-ID が不正です: {expected_app_id!r}"]
    if not path.is_file():
        return None, [f"APP 要求定義書が存在しません: {path.as_posix()}"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [f"APP 要求定義書を UTF-8 で読めません: {path.as_posix()}: {exc}"]

    metadata: dict[str, str] = {}
    counts = {key: 0 for key in _METADATA_KEYS}
    metadata_pattern = re.compile(
        r"^\s*-\s*(Schema-Version|APP-ID|APP名|Document-Status)\s*:\s*(.*?)\s*$"
    )
    for line in text.splitlines():
        match = metadata_pattern.match(line)
        if not match:
            continue
        key, value = match.groups()
        counts[key] += 1
        metadata[key] = value
    for key in _METADATA_KEYS:
        if counts[key] != 1:
            errors.append(f"{key} は正確に1回必要です（検出={counts[key]}）")
        elif not metadata[key]:
            errors.append(f"{key} は空にできません")

    schema_version = 0
    if counts["Schema-Version"] == 1:
        try:
            schema_version = int(metadata["Schema-Version"])
        except ValueError:
            errors.append("Schema-Version は整数 1 でなければなりません")
        else:
            if schema_version != 1:
                errors.append(
                    f"未対応の Schema-Version です: {metadata['Schema-Version']}"
                )

    app_id = metadata.get("APP-ID", "")
    if counts["APP-ID"] == 1 and not _APP_ID_RE.fullmatch(app_id):
        errors.append(f"APP-ID は APP-NNN 形式でなければなりません: {app_id!r}")
    if expected_app_id and app_id and app_id != expected_app_id:
        errors.append(
            f"APP-ID が対象と一致しません: expected={expected_app_id}, actual={app_id}"
        )
    filename_match = _REQUIREMENT_FILE_RE.fullmatch(path.name)
    if filename_match and app_id and app_id != f"APP-{filename_match.group(1)}":
        errors.append(
            "APP-ID が canonical ファイル名と一致しません: "
            f"file={path.name}, APP-ID={app_id}"
        )

    lines = text.splitlines()
    requirements_heading = next(
        (index for index, line in enumerate(lines) if line.strip() == "## Requirements"),
        None,
    )
    rows: list[RequirementRow] = []
    if requirements_heading is None:
        errors.append("`## Requirements` セクションがありません")
    else:
        section_end = next(
            (
                index
                for index in range(requirements_heading + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        table_lines = [
            line
            for line in lines[requirements_heading + 1 : section_end]
            if line.strip().startswith("|")
        ]
        if len(table_lines) < 2:
            errors.append("Requirements の Markdown table がありません")
        else:
            header = tuple(_split_markdown_row(table_lines[0]))
            if header != _TABLE_HEADER:
                errors.append(
                    "Requirements table の固定列が不正です: "
                    + " | ".join(header)
                )
            separator = _split_markdown_row(table_lines[1])
            if len(separator) != len(_TABLE_HEADER) or not _is_separator_row(separator):
                errors.append("Requirements table の区切り行が不正です")
            for row_number, line in enumerate(table_lines[2:], start=1):
                cells = _split_markdown_row(line)
                if len(cells) != len(_TABLE_HEADER):
                    errors.append(
                        f"Requirements row {row_number} の列数が不正です: {len(cells)}"
                    )
                    continue
                if not all(cells):
                    errors.append(f"Requirements row {row_number} に空セルがあります")
                    continue
                row = RequirementRow(*cells)
                match = _REQUIREMENT_ID_RE.fullmatch(row.requirement_id)
                if not match:
                    errors.append(
                        f"Requirement ID が不正です: {row.requirement_id!r}"
                    )
                elif app_id and match.group(1) != app_id:
                    errors.append(
                        "Requirement ID の APP-ID が文書と一致しません: "
                        f"{row.requirement_id} / {app_id}"
                    )
                elif match.group(3) == "000":
                    errors.append(
                        f"Requirement ID の末尾番号は 001〜999 です: {row.requirement_id}"
                    )
                if row.status not in _ALLOWED_STATUSES:
                    errors.append(f"Status が不正です: {row.status!r}")
                if row.blocker not in _ALLOWED_BLOCKERS:
                    errors.append(f"Blocker が不正です: {row.blocker!r}")
                rows.append(row)

    ids = [row.requirement_id for row in rows]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    for requirement_id in duplicates:
        errors.append(f"duplicate Requirement ID: {requirement_id}")

    if errors:
        return None, errors
    return (
        RequirementDocument(
            path=path,
            schema_version=schema_version,
            app_id=app_id,
            app_name=metadata["APP名"],
            document_status=metadata["Document-Status"],
            rows=tuple(rows),
        ),
        [],
    )


def validate_requirement_document(
    path: str | Path, *, expected_app_id: str | None = None
) -> list[str]:
    """APP 要求定義書を検証し、決定的なエラー一覧を返す。"""
    _, errors = _parse_document(Path(path), expected_app_id)
    return errors


def parse_requirement_document(
    path: str | Path, *, expected_app_id: str | None = None
) -> RequirementDocument:
    """検証済み文書を返す。不正時は fail-closed で例外にする。"""
    document, errors = _parse_document(Path(path), expected_app_id)
    if document is None:
        raise ApplicationRequirementError("; ".join(errors))
    return document


def next_requirement_id(document: RequirementDocument, kind: str) -> str:
    """同じ APP・kind の最大番号の次を返す。999 超過は拒否する。"""
    normalized_kind = str(kind).upper()
    if normalized_kind not in {"FR", "NFR", "C"}:
        raise ApplicationRequirementError(f"Requirement kind が不正です: {kind!r}")
    maximum = max(
        (row.sequence for row in document.rows if row.kind == normalized_kind),
        default=0,
    )
    if maximum >= 999:
        raise ApplicationRequirementError(
            f"{document.app_id}-{normalized_kind} の ID 上限 999 に達しました"
        )
    return f"{document.app_id}-{normalized_kind}-{maximum + 1:03d}"


def merge_requirement_documents(
    existing: RequirementDocument,
    proposed: RequirementDocument,
) -> RequirementMergeResult:
    """既存行を削除・再番号付けせず、提案の新規 ID だけを追加する。"""
    if existing.app_id != proposed.app_id:
        raise ApplicationRequirementError(
            f"upsert 対象 APP-ID が一致しません: {existing.app_id} / {proposed.app_id}"
        )
    existing_by_id = {row.requirement_id: row for row in existing.rows}
    merged = list(existing.rows)
    conflicts: list[str] = []
    maxima = {
        kind: max(
            (row.sequence for row in existing.rows if row.kind == kind),
            default=0,
        )
        for kind in ("FR", "NFR", "C")
    }
    for row in proposed.rows:
        current = existing_by_id.get(row.requirement_id)
        if current is None:
            expected_sequence = maxima[row.kind] + 1
            if row.sequence != expected_sequence:
                conflicts.append(
                    f"{row.requirement_id}: 新規 ID は {existing.app_id}-{row.kind}-"
                    f"{expected_sequence:03d} でなければならないため追加しない"
                )
                continue
            merged.append(row)
            existing_by_id[row.requirement_id] = row
            maxima[row.kind] = row.sequence
        elif current != row:
            conflicts.append(
                f"{row.requirement_id}: 既存行と提案行が競合するため既存内容を保持"
            )
    return RequirementMergeResult(
        document=RequirementDocument(
            path=existing.path,
            schema_version=existing.schema_version,
            app_id=existing.app_id,
            app_name=existing.app_name,
            document_status=existing.document_status,
            rows=tuple(merged),
        ),
        conflicts=tuple(conflicts),
    )


def _catalog_app_ids(repo_root: Path) -> tuple[str, ...]:
    ids = parse_catalog("app_catalog", repo_root)
    invalid = [app_id for app_id in ids if not _APP_ID_RE.fullmatch(app_id)]
    if invalid:
        raise ApplicationRequirementError(
            f"app-catalog に不正な APP-ID があります: {', '.join(invalid)}"
        )
    if not ids:
        raise ApplicationRequirementError(
            "docs/catalog/app-catalog.md に APP-NNN がありません"
        )
    return tuple(ids)


def validate_requirement_coverage(repo_root: str | Path) -> RequirementCoverage:
    """app-catalog 全 APP の文書実在・schema と orphan を検証する。"""
    root = Path(repo_root)
    try:
        app_ids = _catalog_app_ids(root)
    except ApplicationRequirementError as exc:
        return RequirementCoverage((), (str(exc),), ())

    errors: list[str] = []
    expected_paths: set[Path] = set()
    for app_id in app_ids:
        relative_path = canonical_requirement_path(app_id)
        expected_paths.add(relative_path)
        for error in validate_requirement_document(
            root / relative_path, expected_app_id=app_id
        ):
            errors.append(f"{app_id}: {error}")

    docs_dir = root / "docs"
    actual_paths: set[Path] = set()
    if docs_dir.is_dir():
        for path in docs_dir.glob("architectural-requirements-app-*.md"):
            if _REQUIREMENT_FILE_RE.fullmatch(path.name):
                actual_paths.add(path.relative_to(root))
            else:
                errors.append(
                    f"canonical 形式でない APP 要求定義書です: {path.relative_to(root).as_posix()}"
                )
    orphan_paths = tuple(sorted(actual_paths - expected_paths, key=lambda item: item.as_posix()))
    return RequirementCoverage(app_ids, tuple(errors), orphan_paths)


def _normalize_app_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates: Iterable[object] = value.split(",")
    elif isinstance(value, Sequence):
        candidates = value
    else:
        candidates = (value,)
    result: list[str] = []
    for candidate in candidates:
        app_id = str(candidate).strip()
        if not app_id:
            continue
        if not _APP_ID_RE.fullmatch(app_id):
            raise ApplicationRequirementError(f"APP-ID が不正です: {app_id!r}")
        if app_id not in result:
            result.append(app_id)
    return tuple(result)


def extract_application_requirement_app_ids(issue_body: str) -> tuple[str, ...]:
    """Cloud Issue body の metadata または Issue Form 節から APP-ID を抽出する。"""
    body = str(issue_body or "")
    metadata_values = re.findall(
        r"<!--\s*app-ids?:\s*([^>]*)-->", body, re.IGNORECASE
    )
    if len(metadata_values) > 1:
        raise ApplicationRequirementError(
            "Cloud Issue body の app-id/app-ids metadata は最大1件です"
        )

    raw_value = metadata_values[0].strip() if metadata_values else ""
    if not metadata_values:
        sections = re.findall(
            r"^###\s*対象アプリケーション\s*\(APP-ID\)[^\n]*\n(.*?)(?=^###\s|\Z)",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if len(sections) > 1:
            raise ApplicationRequirementError(
                "Cloud Issue body の対象アプリケーション節は最大1件です"
            )
        raw_value = sections[0].strip() if sections else ""

    if not raw_value or raw_value == "_No response_":
        return ()
    tokens = [
        token.strip().strip("`")
        for token in re.split(r"[,\s]+", raw_value)
        if token.strip()
    ]
    return _normalize_app_ids(tokens)


def _apps_for_fanout_key(key: str, repo_root: Path) -> tuple[str, ...]:
    direct = re.match(r"^(APP-\d{3})(?:$|-)", key)
    if direct:
        return (direct.group(1),)
    if key.startswith("SVC-"):
        return tuple(parse_service_app_mapping(repo_root).get(key, ()))

    # 将来の entity / agent catalog も同じ規則で解決できるよう、キーを含む
    # catalog 行に明示された APP-ID だけを採用する。推測はしない。
    candidate_paths = [
        repo_root / "docs" / "catalog" / "data-catalog.md",
        repo_root / "docs" / "catalog" / "data-model.md",
        repo_root / "docs" / "agent" / "agent-architecture.md",
        repo_root / "docs" / "ai-agent-catalog.md",
    ]
    found: list[str] = []
    key_pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])")
    for path in candidate_paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            if not key_pattern.search(line):
                continue
            for app_id in re.findall(r"APP-\d{3}", line):
                if app_id not in found:
                    found.append(app_id)
    return tuple(found)


def _classified_app_ids(workflow_id: str, repo_root: Path) -> tuple[str, ...]:
    if workflow_id not in _ARCH_FILTER_WORKFLOWS:
        return _catalog_app_ids(repo_root)
    try:
        result = resolve_app_arch_scope(
            workflow_id=workflow_id,
            requested_app_ids=None,
            catalog_path=str(repo_root / "docs" / "catalog" / "app-arch-catalog.md"),
            dry_run=False,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ApplicationRequirementError(str(exc)) from exc
    return tuple(result.matched_app_ids)


def resolve_application_requirement_app_ids(
    *,
    workflow_id: str,
    workflow_params: Mapping[str, object],
    fanout_meta: Mapping[str, object] | None,
    repo_root: str | Path,
) -> tuple[str, ...]:
    """Workflow / fan-out context から参照対象 APP-ID を決定する。"""
    normalized_workflow = workflow_id.lower()
    if normalized_workflow not in _TARGET_WORKFLOWS:
        return ()
    root = Path(repo_root)
    catalog_ids = _catalog_app_ids(root)
    catalog_set = set(catalog_ids)

    fanout_key = str((fanout_meta or {}).get("fanout_key") or "").strip()
    if fanout_key:
        mapped = _apps_for_fanout_key(fanout_key, root)
        if mapped:
            unknown = [app_id for app_id in mapped if app_id not in catalog_set]
            if unknown:
                raise ApplicationRequirementError(
                    f"fan-out key {fanout_key} の APP-ID が app-catalog にありません: "
                    + ", ".join(unknown)
                )
            return mapped

    selected = _normalize_app_ids(
        workflow_params.get("app_ids") or workflow_params.get("app_id")
    )
    if selected:
        unknown = [app_id for app_id in selected if app_id not in catalog_set]
        if unknown:
            raise ApplicationRequirementError(
                "対象 APP-ID が app-catalog にありません: " + ", ".join(unknown)
            )
        return selected

    classified = _classified_app_ids(normalized_workflow, root)
    if not classified:
        raise ApplicationRequirementError(
            f"Workflow {workflow_id} の対象 APP-ID を解決できません"
        )
    return classified


def build_application_requirement_context(
    *,
    workflow_id: str,
    workflow_params: Mapping[str, object],
    fanout_meta: Mapping[str, object] | None,
    repo_root: str | Path,
) -> str:
    """対象 path と ID だけを含む、全文非注入の追加プロンプトを返す。"""
    root = Path(repo_root)
    app_ids = resolve_application_requirement_app_ids(
        workflow_id=workflow_id,
        workflow_params=workflow_params,
        fanout_meta=fanout_meta,
        repo_root=root,
    )
    if not app_ids:
        return ""

    paths: list[Path] = []
    unresolved: list[str] = []
    errors: list[str] = []
    for app_id in app_ids:
        relative_path = canonical_requirement_path(app_id)
        paths.append(relative_path)
        document, document_errors = _parse_document(root / relative_path, app_id)
        if document is None:
            errors.extend(f"{app_id}: {error}" for error in document_errors)
        else:
            unresolved.extend(document.unresolved_blocking_requirement_ids)
    if errors:
        raise ApplicationRequirementError("; ".join(errors))
    if unresolved:
        raise ApplicationRequirementError(
            "未解決の TBD Blocker があります: " + ", ".join(unresolved)
        )

    template_lines = load_prompt_file(
        "runtime/addenda/application-requirements.prompt.md"
    ).splitlines()
    if len(template_lines) < 5 or not template_lines[1].startswith("- 対象 APP-ID:") \
            or not template_lines[2].startswith("- 必須要求定義書:"):
        raise ApplicationRequirementError(
            "APP要求 addendum template が不正です: runtime/addenda/application-requirements.prompt.md"
        )

    return "\n".join(
        [
            template_lines[0],
            template_lines[1] + " " + ", ".join(app_ids),
            template_lines[2],
            *(f"  - `{path.as_posix()}`" for path in paths),
            *template_lines[3:],
        ]
    )


def _parse_csv_value(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if not stripped or stripped.casefold() in {"none", "なし", "n/a"}:
        return ()
    return tuple(item.strip().strip("`") for item in stripped.split(",") if item.strip())


def validate_application_requirement_trace_block(
    text: str,
    *,
    repo_root: str | Path,
    expected_app_ids: Sequence[str],
) -> list[str]:
    """完了報告の APP requirement trace block を構造・実在だけで検証する。"""
    errors: list[str] = []
    start_marker = "<!-- app-requirements:start -->"
    end_marker = "<!-- app-requirements:end -->"
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        return ["app-requirements trace block は開始・終了マーカーを各1回必要とします"]
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker)
    if end <= start:
        return ["app-requirements trace block のマーカー順序が不正です"]
    block = text[start:end]

    values: dict[str, str] = {}
    for key in _TRACE_KEYS:
        matches = re.findall(rf"^\s*-\s*{re.escape(key)}\s*:\s*(.*?)\s*$", block, re.MULTILINE)
        if len(matches) != 1:
            errors.append(f"{key} は trace block 内に正確に1回必要です")
        else:
            values[key] = matches[0]
    if errors:
        return errors

    try:
        actual_app_ids = _normalize_app_ids(_parse_csv_value(values["APP-IDs"]))
        expected = _normalize_app_ids(expected_app_ids)
    except ApplicationRequirementError as exc:
        return [str(exc)]
    if actual_app_ids != expected:
        errors.append(
            "APP-IDs が対象と一致しません: "
            f"expected={list(expected)}, actual={list(actual_app_ids)}"
        )

    root = Path(repo_root)
    requirement_ids = _parse_csv_value(values["Requirement-IDs"])
    document_paths = _parse_csv_value(values["Requirement-Documents"])
    unresolved_ids = _parse_csv_value(values["Unresolved-Blockers"])
    expected_paths = tuple(
        canonical_requirement_path(app_id).as_posix() for app_id in actual_app_ids
    )
    if document_paths != expected_paths:
        errors.append(
            "Requirement-Documents が canonical path と一致しません: "
            f"expected={list(expected_paths)}, actual={list(document_paths)}"
        )

    rows_by_id: dict[str, RequirementRow] = {}
    actual_unresolved_ids: list[str] = []
    for app_id, relative_path in zip(actual_app_ids, expected_paths):
        try:
            document = parse_requirement_document(
                root / relative_path, expected_app_id=app_id
            )
        except ApplicationRequirementError as exc:
            errors.append(str(exc))
            continue
        rows_by_id.update({row.requirement_id: row for row in document.rows})
        actual_unresolved_ids.extend(document.unresolved_blocking_requirement_ids)

    if actual_unresolved_ids:
        errors.append(
            "実行後の要求文書に未解決の TBD Blocker があります: "
            + ", ".join(actual_unresolved_ids)
        )

    for requirement_id in requirement_ids:
        row = rows_by_id.get(requirement_id)
        if row is None:
            errors.append(f"Requirement-ID が対象文書に存在しません: {requirement_id}")
        elif row.status not in {"confirmed", "source-backed"}:
            errors.append(
                f"Requirement-ID は confirmed/source-backed のみ引用できます: {requirement_id}"
            )
        elif row.app_id not in actual_app_ids:
            errors.append(f"Requirement-ID の APP-ID が対象外です: {requirement_id}")

    for requirement_id in unresolved_ids:
        row = rows_by_id.get(requirement_id)
        if row is None:
            errors.append(f"Unresolved-Blocker が対象文書に存在しません: {requirement_id}")
        elif not (row.status == "TBD" and row.blocker == "yes"):
            errors.append(
                f"Unresolved-Blocker は TBD かつ Blocker=yes でなければなりません: {requirement_id}"
            )
    return errors


__all__ = [
    "ApplicationRequirementError",
    "RequirementCoverage",
    "RequirementDocument",
    "RequirementMergeResult",
    "RequirementRow",
    "build_application_requirement_context",
    "canonical_requirement_path",
    "extract_application_requirement_app_ids",
    "merge_requirement_documents",
    "next_requirement_id",
    "parse_requirement_document",
    "resolve_application_requirement_app_ids",
    "validate_application_requirement_trace_block",
    "validate_requirement_coverage",
    "validate_requirement_document",
]
