from __future__ import annotations

import difflib
import json
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .workflow_registry import canonicalize_workflow_id
except ImportError:  # pragma: no cover - script execution
    from workflow_registry import canonicalize_workflow_id  # type: ignore[import-not-found,no-redef]

_MANIFEST_FILE = "skill_manifest.json"
_SKILL_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SKILL_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_EXTERNAL_SKILL_DIRECTORY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _skills_root() -> Path:
    return _repo_root() / ".github" / "skills"


def _external_skills_root() -> Path:
    """Return the standard user-level Skill root without scanning it."""
    return Path.home() / ".agents" / "skills"


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
    raw_aliases = manifest.get("aliases")
    aliases: Dict[str, Any] = raw_aliases if isinstance(raw_aliases, dict) else {}
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


def _is_symlink_or_reparse_point(path: Path) -> bool:
    """Reject filesystem links so an exact external Skill path cannot escape."""
    try:
        path_stat = path.lstat()
    except OSError:
        return True
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    return bool(
        stat.S_ISLNK(path_stat.st_mode)
        or int(getattr(path_stat, "st_file_attributes", 0)) & reparse_flag
    )


def get_external_skill_directory(
    name: str,
    *,
    external_skills_root: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve one external Skill by its exact canonical directory name.

    This intentionally does not enumerate the user-level Skill root.  A caller
    must declare the Skill it needs, after which only
    ``~/.agents/skills/<canonical-name>/SKILL.md`` is inspected.
    """
    canonical_name = resolve_skill_alias(name)
    if not _EXTERNAL_SKILL_DIRECTORY_NAME_RE.fullmatch(canonical_name):
        return None
    root = (external_skills_root or _external_skills_root()).expanduser()
    if not root.is_dir():
        return None
    candidate = root / canonical_name
    skill_file = candidate / "SKILL.md"
    if not candidate.is_dir() or not skill_file.is_file():
        return None
    if _is_symlink_or_reparse_point(candidate) or _is_symlink_or_reparse_point(
        skill_file
    ):
        return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        resolved_skill_file = skill_file.resolve(strict=True)
    except OSError:
        return None
    if resolved_candidate.parent != resolved_root:
        return None
    if resolved_skill_file.parent != resolved_candidate:
        return None
    if parse_skill_name_from_file(skill_file) != canonical_name:
        return None
    return candidate


def get_skill_directory(
    name: str,
    *,
    external_skills_root: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a declared Skill directory, preferring repository-owned Skills."""
    canonical_name = resolve_skill_alias(name)
    if not canonical_name:
        return None
    repository_subpath = discover_available_skills().get(canonical_name)
    if repository_subpath:
        return _skills_root() / repository_subpath
    return get_external_skill_directory(
        canonical_name,
        external_skills_root=external_skills_root,
    )


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
    raw = defaults.get(canonicalize_workflow_id(workflow_id), [])
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
    canonical_workflow_id = canonicalize_workflow_id(workflow_id)
    result: List[str] = []
    seen: Set[str] = set()

    # Workflow defaults are treated as the baseline skill set for every step.
    for name in get_workflow_default_skills(workflow_id):
        if name and name not in seen:
            seen.add(name)
            result.append(name)

    if isinstance(req, dict):
        wf_req = req.get(canonical_workflow_id)
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


def get_optional_skills_for_step(workflow_id: str, step_id: str) -> List[str]:
    """Return only declared optional Skill candidates for one active Step.

    Optional candidates are not preflight requirements and are intentionally
    separate from ``get_required_skills_for_step``.  Callers must select a
    candidate only when the Step's selected Azure service or operation matches
    its documented trigger.
    """
    manifest = load_skill_manifest()
    optional = manifest.get("optional_skills")
    if not isinstance(optional, dict):
        return []
    workflow_candidates = optional.get(canonicalize_workflow_id(workflow_id))
    if not isinstance(workflow_candidates, dict):
        return []
    raw_candidates = workflow_candidates.get(str(step_id).split("/", 1)[0], [])
    if not isinstance(raw_candidates, list):
        return []

    result: List[str] = []
    seen: Set[str] = set()
    for raw_name in raw_candidates:
        normalized = resolve_skill_alias(str(raw_name))
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def validate_skill_names(
    skill_names: List[str],
    *,
    external_skills_root: Optional[Path] = None,
) -> Tuple[List[str], Dict[str, str], Dict[str, List[str]]]:
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
        if get_external_skill_directory(
            normalized,
            external_skills_root=external_skills_root,
        ) is not None:
            continue
        missing.append(normalized)
        suggestions[normalized] = difflib.get_close_matches(
            normalized,
            sorted(available_names),
            n=3,
            cutoff=0.6,
        )
    return missing, resolved, suggestions
