"""Read-only EABK management-data model.

FR-001 AC-001; FR-013 AC-013; NFR-SEC-002 AC-024; NFR-OPS-004 AC-029
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Union

DEFAULT_FILES = {
    "requirements": "docs/requirements-definition.md",
    "catalog": "docs/catalog.md",
    "id_registry": "docs/id-registry.md",
    "run_history": "docs/run-history.md",
    "ledger": "tests/system/ledger.json",
}


def _config(repo: Path) -> Dict[str, str]:
    config = repo / "scripts" / "ebak.config.json"
    if not config.is_file():
        return dict(DEFAULT_FILES)
    try:
        values = json.loads(config.read_text(encoding="utf-8")).get("management_files", {})
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid management data config: {exc}") from exc
    return {**DEFAULT_FILES, **{key: str(value) for key, value in values.items()}}


def management_paths(repo: Path) -> List[Path]:
    """Return configured management files without creating or modifying them."""
    return [repo / value for value in _config(repo).values()]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        raise ValueError(f"Cannot read management data {path}: {exc}") from exc


def _nodes(text: str, pattern: str, kind: str) -> List[dict]:
    found = []
    for match in re.finditer(pattern, text, re.MULTILINE):
        node_id, title = match.group(1), match.group(2).strip()
        found.append({"id": node_id, "title": title, "kind": kind})
    return found


def _catalog_rows(text: str) -> Iterable[List[str]]:
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:-]+\|", line):
            yield [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def build_model(repo_path: Union[str, Path]) -> dict:
    """Build a traversable snapshot using reads only."""
    repo = Path(repo_path).expanduser().resolve()
    files = _config(repo)
    requirements_path = repo / files["requirements"]
    catalog_path = repo / files["catalog"]
    if not requirements_path.is_file() or not catalog_path.is_file():
        raise ValueError("Required management data is missing (requirements and catalog)")

    requirements = _read(requirements_path)
    catalog = _read(catalog_path)
    reqs = _nodes(requirements, r"^####\s+((?:FR|NFR)-[\w-]+)\s+(.+)$", "requirement")
    acs = _nodes(requirements, r"^\s*-\s*受入基準\s+(AC-[\w-]+):\s*(.+)$", "acceptance-criterion")
    goals = _nodes(requirements, r"^\|\s*(G-\d+)\s*\|\s*([^|]+)", "goal")
    params = _nodes(requirements, r"^\|\s*(PARAM-\d+)\s*\|\s*([^|]+)", "parameter")
    questions = _nodes(requirements, r"^###?\s+(Q-\d+)\s+(.+)$", "question")
    sources = _nodes(requirements, r"^\|\s*(SRC-\d+)\s*\|\s*([^|]+)", "source")

    catalog_features: List[dict] = []
    api_nodes: List[dict] = []
    table_nodes: List[dict] = []
    component_nodes: List[dict] = []
    for cells in _catalog_rows(catalog):
        if cells and re.fullmatch(r"(?:FR|NFR)-[\w-]+", cells[0]) and len(cells) >= 6:
            catalog_features.append({
                "id": f"catalog:{cells[0]}", "requirement_id": cells[0],
                "title": cells[1], "files": cells[3], "tests": cells[4],
                "components": cells[5], "kind": "catalog-feature",
            })
        elif len(cells) == 3 and cells[0].startswith(("GET ", "POST ", "PUT ", "DELETE ")):
            api_nodes.append({"id": f"api:{cells[0]}", "title": cells[0], "file": cells[1], "kind": "api"})
        elif len(cells) == 4 and cells[0] not in {"テーブル名", "部品名"}:
            table_nodes.append({"id": f"table:{cells[0]}", "title": cells[0], "file": cells[1], "kind": "table"})
        elif len(cells) == 4 and cells[0] not in {"名前", "要求 ID"}:
            component_nodes.append({"id": f"component:{cells[0]}", "title": cells[0], "file": cells[1], "kind": "component"})

    ledger_path = repo / files["ledger"]
    cases = []
    if ledger_path.is_file():
        try:
            for case in json.loads(_read(ledger_path)).get("cases", []):
                cases.append({"id": case["id"], "title": case.get("title", ""), "kind": "test",
                              "requirement_ids": case.get("requirement_ids", [])})
        except (json.JSONDecodeError, KeyError):
            pass

    edges = []
    for feature in catalog_features:
        req = feature["requirement_id"]
        edges.append({"from": req, "to": feature["id"], "kind": "catalog"})
        for token in re.findall(r"(?:EABK-Studio|docs|tests|scripts)/[^,、\s]+", feature["files"] + " " + feature["tests"]):
            edges.append({"from": feature["id"], "to": f"file:{token}", "kind": "file"})
    for case in cases:
        for req in case["requirement_ids"]:
            edges.append({"from": req, "to": case["id"], "kind": "test"})

    referenced_files = sorted({edge["to"][5:] for edge in edges if edge["to"].startswith("file:")})
    return {
        "meta": {"repo": str(repo), "name": repo.name, "management_files": files},
        "goals": goals, "reqs": reqs, "acs": acs, "params": params,
        "questions": questions, "sources": sources, "catalog": catalog_features,
        "apis": api_nodes, "tables": table_nodes, "components": component_nodes,
        "tests": cases,
        "files": [{"id": f"file:{path}", "title": path, "kind": "file"} for path in referenced_files],
        "states": sorted(set(re.findall(r"決定状態:\s*([^\n　]+)", requirements))),
        "edges": edges,
    }
