"""mdq configuration loader.

Loads optional per-repository configuration so that ``DEFAULT_ROOTS`` and other
defaults can be overridden without forking ``mdq.cli``.

Resolution order for the config file (first hit wins):

1. Explicit path passed via ``--config PATH`` (handled by the caller).
2. ``<repo_root>/mdq.toml``
3. ``<repo_root>/.mdq/config.toml``

Schema (TOML)::

    [index]
    # Directories scanned by ``python -m mdq index`` / ``watch`` when no
    # ``--root`` argument is given. Missing directories are silently skipped
    # by the indexer.
    roots = ["docs", "users-guide", "knowledge"]

If no config file is found, ``GENERIC_DEFAULT_ROOTS`` is used. This keeps the
generic Skill portable across repositories: a fresh clone of any project only
needs to drop a ``mdq.toml`` to declare its documentation layout.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Optional

# Minimal, generic defaults. Repositories with richer doc layouts should
# declare their roots in ``mdq.toml`` (see module docstring).
GENERIC_DEFAULT_ROOTS: list[str] = ["docs", "users-guide"]

CONFIG_FILENAMES: tuple[Path, ...] = (
    Path("mdq.toml"),
    Path(".mdq") / "config.toml",
)


def find_config(repo_root: Path) -> Optional[Path]:
    """Return the first existing config file under ``repo_root``, or ``None``."""
    for rel in CONFIG_FILENAMES:
        candidate = repo_root / rel
        if candidate.is_file():
            return candidate
    return None


def load_config(repo_root: Path,
                explicit: Optional[Path] = None) -> dict[str, Any]:
    """Load and return the parsed config dict (empty dict if no file)."""
    path = explicit if explicit is not None else find_config(repo_root)
    if path is None or not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def resolve_roots(repo_root: Path,
                  cli_roots: Optional[list[str]] = None,
                  config_path: Optional[Path] = None) -> list[str]:
    """Resolve the effective index roots.

    Priority: ``--root`` CLI flags > ``[index].roots`` in config file >
    ``GENERIC_DEFAULT_ROOTS``.
    """
    if cli_roots:
        return list(cli_roots)
    cfg = load_config(repo_root, explicit=config_path)
    raw = cfg.get("index", {}).get("roots")
    if isinstance(raw, list) and raw:
        return [str(r) for r in raw]
    return list(GENERIC_DEFAULT_ROOTS)
