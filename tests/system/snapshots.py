"""Build an expensive disposable repository once per pytest process and hand out copies.

`tools/install.py` plus the git setup costs several seconds; the tests only need a pristine
installed repository that they are free to mutate.  A copy of a finished snapshot is
isolated exactly like a fresh install and costs a fraction of it.
"""
from __future__ import annotations

import atexit
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable

_ROOT: Path | None = None
_BUILT: dict[str, Path] = {}


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=onerror)


def _base() -> Path:
    global _ROOT
    if _ROOT is None:
        _ROOT = Path(tempfile.mkdtemp(prefix="eabk-st-snap-"))
        atexit.register(lambda: _rmtree(_ROOT) if _ROOT and _ROOT.exists() else None)
    return _ROOT


def clone(key: str, build: Callable[[Path], object], dest: Path) -> Path:
    """Copy the snapshot `key` to `dest` (built once per process by `build(snapshot_dir)`)."""
    snap = _BUILT.get(key)
    if snap is None:
        snap = _base() / key
        build(snap)
        _BUILT[key] = snap
    shutil.copytree(snap, dest, symlinks=True, dirs_exist_ok=True)
    return dest
