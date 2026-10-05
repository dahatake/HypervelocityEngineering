"""Parse the authoring forms used by the HVE requirement-test mapping."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cq.traces import FEATURE_ID_RE  # noqa: E402  canonical requirement grammar


GATE_ID_RE = r"G-[A-Z]+"
SECTION_ID_RE = r"§[0-9.]+"
MAX_RANGE_ITEMS = 100
HISTORY_SECTION_PREFIXES = ("11.", "12.", "14.")
ALLOWED_TEST_PREFIXES = (
    "hve/tests/",
    "hve/gui/tests/",
    "mdq/tests/",
    "cq/tests/",
    ".github/scripts/tests/",
    ".github/scripts/python/tests/",
    ".github/scripts/powershell/tests/",
    "mdq/gui/tests/",
    "tests/bats/",
)

_ID_RE = re.compile(
    rf"(?<![A-Za-z0-9-])(?P<id>(?:{FEATURE_ID_RE}|{GATE_ID_RE}|{SECTION_ID_RE}))"
    rf"(?![A-Za-z0-9_.-])"
)
_RANGE_END_RE = re.compile(r"\s*(?P<separator>[〜～~])\s*(?P<end>\d+)(?![A-Za-z0-9_.-])")
_SEPARATOR_RE = re.compile(r"\s*(?P<separator>/|・)\s*")
_SHORTHAND_NUMBER_RE = re.compile(r"(?P<number>\d+)(?![A-Za-z0-9_.-])")
_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
_JUDGMENT_RE = re.compile(r"^\s*-\s*判定:\s*(?P<judgment>.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
_DEFINITION_LIST_RE = re.compile(
    rf"^\s*(?:[-*+]|\d+\.)\s+(?:~~)?(?:\*\*)?"
    rf"(?P<id>(?:{FEATURE_ID_RE}|{GATE_ID_RE}))(?:（[^）]+）)?(?:\*\*)?\s*:"
)
_DEFINITION_TABLE_RE = re.compile(
    rf"^\s*\|\s*(?:~~)?(?:\*\*)?"
    rf"(?P<id>(?:{FEATURE_ID_RE}|{GATE_ID_RE}))(?:（[^）]+）)?(?:\*\*)?(?:~~)?\s*\|"
)


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _numeric_id_parts(identifier: str) -> tuple[str, int, int] | None:
    if "-§" in identifier or re.fullmatch(FEATURE_ID_RE, identifier) is None:
        return None
    match = re.fullmatch(r"(?P<prefix>.+-)(?P<number>\d+)", identifier)
    if match is None:
        return None
    number = match.group("number")
    return match.group("prefix"), int(number), len(number)


def _mapping_id_occurrences_from_text(text: str) -> list[str]:
    expression = text.partition("—")[0].lstrip()
    first = _ID_RE.match(expression)
    if first is None:
        return []

    identifiers: list[str] = []
    position = 0
    inherited_numeric: tuple[str, int] | None = None
    while True:
        identifier_match = _ID_RE.match(expression, position)
        if identifier_match is not None:
            identifier = identifier_match.group("id")
            numeric_parts = _numeric_id_parts(identifier)
            position = identifier_match.end()
            range_match = _RANGE_END_RE.match(expression, position)
            if range_match is not None:
                if numeric_parts is None:
                    return []
                prefix, start, width = numeric_parts
                end = int(range_match.group("end"))
                if end < start or end - start + 1 > MAX_RANGE_ITEMS:
                    return []
                identifiers.extend(
                    f"{prefix}{number:0{width}d}" for number in range(start, end + 1)
                )
                position = range_match.end()
            else:
                remainder = expression[position:].lstrip()
                if remainder.startswith(("〜", "～", "~")):
                    return []
                identifiers.append(identifier)
            if numeric_parts is not None:
                inherited_numeric = (numeric_parts[0], numeric_parts[2])
        else:
            if inherited_numeric is None:
                return []
            number_match = _SHORTHAND_NUMBER_RE.match(expression, position)
            if number_match is None:
                return []
            prefix, width = inherited_numeric
            identifiers.append(
                f"{prefix}{int(number_match.group('number')):0{width}d}"
            )
            position = number_match.end()

        separator = _SEPARATOR_RE.match(expression, position)
        if separator is None:
            return identifiers
        position = separator.end()
        if position >= len(expression):
            return []


def mapping_ids_from_text(text: str) -> list[str]:
    """Return unique mapping IDs before the first em dash, in source order."""
    return _unique_in_order(_mapping_id_occurrences_from_text(text))


def _compact(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _mapping_ids(value: str) -> list[str]:
    return [
        identifier
        for identifier in mapping_ids_from_text(value)
        if not identifier.startswith("§")
    ]


def _mapping_id_occurrences(value: str) -> list[str]:
    return [
        identifier
        for identifier in _mapping_id_occurrences_from_text(value)
        if not identifier.startswith("§")
    ]


def _heading_mapping_id_occurrences(title: str) -> list[str]:
    """Return IDs only when a heading starts with an actual mapping ID."""
    title_prefix = title.partition("—")[0].strip()
    first = _ID_RE.match(title_prefix)
    if first is None or first.group("id").startswith("§"):
        return []
    identifier = first.group("id")
    if not identifier.startswith("G-") and _numeric_id_parts(identifier) is None:
        return []
    return _mapping_id_occurrences(title)


def definition_ids_in_line(line: str) -> list[str]:
    """Return IDs only from a structural requirement definition line."""
    match = _DEFINITION_LIST_RE.match(line) or _DEFINITION_TABLE_RE.match(line)
    return [match.group("id")] if match is not None else []


def requirement_status_for_line(line: str) -> str:
    """Classify only structural removal markers, never prose vocabulary."""
    if re.match(r"^\s*(?:[-*+]|\d+\.)\s+~~", line):
        return "deprecated-or-removed"
    if re.match(r"^\s*\|\s*~~", line):
        return "deprecated-or-removed"
    if re.search(r"→\s*(?:\*\*)?廃止", line):
        return "deprecated-or-removed"
    return "active-or-described"


def iter_requirement_definitions(
    text: str,
) -> Iterable[tuple[int, str, str, str, str]]:
    """Yield visible non-history requirement definitions in source order."""
    current_section = ""
    top_level_section = ""
    for line_number, line in visible_markdown_lines(text):
        heading = _HEADING_RE.match(line)
        if heading is not None:
            current_section = heading.group("title")
            if len(heading.group("marks")) == 2:
                top_level_section = current_section
        if top_level_section.startswith(HISTORY_SECTION_PREFIXES):
            continue
        status = requirement_status_for_line(line)
        for identifier in definition_ids_in_line(line):
            yield line_number, current_section, identifier, status, line


def _ensure_entry(
    mapping: dict[str, dict[str, object]],
    identifier: str,
    line_number: int,
    title: str,
) -> dict[str, object]:
    if identifier not in mapping:
        mapping[identifier] = {
            "line": line_number,
            "lines": [],
            "title": _compact(title, 300),
            "judgment": "",
            "tests": [],
            "links": [],
        }
    return mapping[identifier]


def _record_occurrence(entry: dict[str, object], line_number: int) -> None:
    lines = entry["lines"]
    assert isinstance(lines, list)
    lines.append(line_number)


def _add_links(entry: dict[str, object], text: str) -> None:
    tests = entry["tests"]
    links = entry["links"]
    assert isinstance(tests, list)
    assert isinstance(links, list)
    for display, target in _LINK_RE.findall(text):
        pair = (display, target)
        if pair not in links:
            links.append(pair)
        test_path = target.strip()
        if test_path.startswith(ALLOWED_TEST_PREFIXES) and test_path not in tests:
            tests.append(test_path)


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _without_inline_code(line: str) -> str:
    return re.sub(r"(`+)[^`]*\1", "", line)


def visible_markdown_lines(text: str) -> Iterable[tuple[int, str]]:
    in_comment = False
    fence: tuple[str, int] | None = None
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        line = source_line
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            marker, length = fence
            if re.fullmatch(rf"\s{{0,3}}{re.escape(marker)}{{{length},}}\s*", line):
                fence = None
            continue
        if fence_match is not None and not in_comment:
            marker_text = fence_match.group(1)
            fence = (marker_text[0], len(marker_text))
            continue
        if not in_comment and (line.startswith("\t") or line.startswith("    ")):
            continue

        visible = ""
        cursor = 0
        while cursor < len(line):
            if in_comment:
                end = line.find("-->", cursor)
                if end < 0:
                    cursor = len(line)
                    break
                in_comment = False
                cursor = end + 3
                continue
            start = line.find("<!--", cursor)
            if start < 0:
                visible += line[cursor:]
                break
            visible += line[cursor:start]
            cursor = start + 4
            in_comment = True
        yield line_number, _without_inline_code(visible)


def parse_requirement_mapping(text: str) -> dict[str, dict[str, object]]:
    """Parse mapping headings and table rows into one entry per expanded ID."""
    mapping: dict[str, dict[str, object]] = {}
    current_ids: list[str] = []

    for line_number, line in visible_markdown_lines(text):
        heading = _HEADING_RE.match(line)
        if heading is not None:
            current_ids = []
            if 2 <= len(heading.group("marks")) <= 6:
                title = heading.group("title")
                occurrences = _heading_mapping_id_occurrences(title)
                current_ids = _unique_in_order(occurrences)
                for identifier in occurrences:
                    entry = _ensure_entry(mapping, identifier, line_number, title)
                    _record_occurrence(entry, line_number)
            continue

        cells = _table_cells(line)
        if cells is not None:
            if len(cells) >= 2:
                occurrences = _heading_mapping_id_occurrences(cells[0])
                for identifier in occurrences:
                    entry = _ensure_entry(mapping, identifier, line_number, cells[0])
                    _record_occurrence(entry, line_number)
                    entry["judgment"] = _compact(cells[1], 200)
                    _add_links(entry, " | ".join(cells[2:]))
            continue

        if not current_ids:
            continue
        judgment = _JUDGMENT_RE.match(line)
        for identifier in current_ids:
            entry = mapping[identifier]
            if judgment is not None:
                entry["judgment"] = _compact(judgment.group("judgment"), 200)
            _add_links(entry, line)

    return mapping


def resolve_allowed_test_path(root: Path, test_path: str) -> Path:
    """Resolve an allowlisted test file without crossing symlinks or its root."""
    prefix = next(
        (candidate for candidate in ALLOWED_TEST_PREFIXES if test_path.startswith(candidate)),
        None,
    )
    if prefix is None:
        raise ValueError(f"test path is outside the allowlist: {test_path}")
    pure_path = PurePosixPath(test_path)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise ValueError(f"invalid test path: {test_path}")

    current = root
    for part in pure_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"test path must not contain a symlink: {test_path}")
    try:
        root_resolved = root.resolve(strict=True)
        allowed_root = (root / prefix.rstrip("/")).resolve(strict=True)
        resolved = current.resolve(strict=True)
        resolved.relative_to(root_resolved)
        resolved.relative_to(allowed_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"test path is missing or escapes its allowed root: {test_path}") from exc
    if not resolved.is_file():
        raise ValueError(f"test path is not a file: {test_path}")
    return resolved
