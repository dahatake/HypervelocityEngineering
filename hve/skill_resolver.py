from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_MANIFEST_FILE = "skill_manifest.json"
_SKILL_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SKILL_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _skills_root() -> Path:
    return _repo_root() / ".github" / "skills"


@lru_cache(maxsize=1)
def load_skill_manifest() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / _MANIFEST_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_skill_name(name: str) -> str:
    return name.strip().replace("_", "-").lower()


def resolve_skill_alias(name: str) -> str:
    manifest = load_skill_manifest()
    aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), dict) else {}
    if not name:
        return ""
    direct = aliases.get(name)
    if isinstance(direct, str) and direct.strip():
        return _normalize_skill_name(direct)

    lowered = {str(k).lower(): str(v) for k, v in aliases.items()}
    by_lower = lowered.get(name.lower())
    if by_lower:
        return _normalize_skill_name(by_lower)

    return _normalize_skill_name(name)


def parse_skill_name_from_file(skill_file: Path) -> str:
    try:
        text = skill_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    m = _SKILL_FRONTMATTER_RE.match(text)
    if not m:
        return ""
    fm = m.group(1)
    n = _SKILL_NAME_RE.search(fm)
    if not n:
        return ""
    return _normalize_skill_name(n.group(1).strip().strip("'\""))


@lru_cache(maxsize=1)
def discover_available_skills() -> Dict[str, str]:
    """Return normalized skill name -> subpath under .github/skills/."""
    base = _skills_root()
    result: Dict[str, str] = {}
    if not base.is_dir():
        return result

    for skill_md in sorted(base.glob("**/SKILL.md")):
        name = parse_skill_name_from_file(skill_md)
        if not name or name in result:
            continue
        rel = skill_md.relative_to(base).as_posix()
        result[name] = rel.removesuffix("/SKILL.md")
    return result


def get_workflow_default_skills(workflow_id: str) -> List[str]:
    manifest = load_skill_manifest()
    defaults = manifest.get("workflow_defaults")
    if not isinstance(defaults, dict):
        return []
    raw = defaults.get((workflow_id or "").lower(), [])
    if not isinstance(raw, list):
        return []
    return [resolve_skill_alias(str(s)) for s in raw if str(s).strip()]


def get_skill_subpaths_for_workflow(workflow_id: str) -> List[str]:
    available = discover_available_skills()
    subpaths: List[str] = []
    seen: Set[str] = set()
    for skill in get_workflow_default_skills(workflow_id):
        subpath = available.get(skill)
        if not subpath or subpath in seen:
            continue
        seen.add(subpath)
        subpaths.append(subpath)
    return subpaths


def get_required_skills_for_step(
    workflow_id: str,
    step_id: str,
    step_declared_required: Optional[List[str]] = None,
) -> List[str]:
    """Return workflow defaults + step-specific required skills (deduplicated)."""
    manifest = load_skill_manifest()
    req = manifest.get("required_skills")
    result: List[str] = []
    seen: Set[str] = set()

    # Workflow defaults are treated as the baseline skill set for every step.
    for name in get_workflow_default_skills(workflow_id):
        if name and name not in seen:
            seen.add(name)
            result.append(name)

    if isinstance(req, dict):
        wf_req = req.get((workflow_id or "").lower())
        if isinstance(wf_req, dict):
            m_list = wf_req.get(step_id, [])
            if isinstance(m_list, list):
                for name in m_list:
                    resolved = resolve_skill_alias(str(name))
                    if resolved and resolved not in seen:
                        seen.add(resolved)
                        result.append(resolved)

    for name in step_declared_required or []:
        resolved = resolve_skill_alias(str(name))
        if resolved and resolved not in seen:
            seen.add(resolved)
            result.append(resolved)

    return result


def validate_skill_names(skill_names: List[str]) -> Tuple[List[str], Dict[str, str], Dict[str, List[str]]]:
    """Return (missing, resolved_map, suggestions)."""
    available = discover_available_skills()
    available_names = set(available.keys())
    missing: List[str] = []
    resolved: Dict[str, str] = {}
    suggestions: Dict[str, List[str]] = {}

    for raw in skill_names:
        normalized = resolve_skill_alias(raw)
        resolved[raw] = normalized
        if normalized in available_names:
            continue
        missing.append(normalized)
        suggestions[normalized] = difflib.get_close_matches(
            normalized,
            sorted(available_names),
            n=3,
            cutoff=0.6,
        )
    return missing, resolved, suggestions
