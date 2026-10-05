#!/usr/bin/env python3
"""HVE application filesを別フォルダーへ安全に置き換えコピーする。"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
SCOPE_MODULE = Path(".github/scripts/hve_scope.py")

# `hve_scope.py` は HVE と生成アプリの境界の機械正本。以下は版管理境界には
# 含まれないものの、抽出先の HVE checkout を利用・保守するために必要な資産。
SUPPORT_FILES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        # コピー済み hve/tests/test_systemtest_screenshot_prompt_contract.py が実在を assert する。
        "tests/[cli]SystemTest - Full.txt",
        "tests/[gui]SystemTest - Full.txt",
        # コピー済み `tools/*.py` の io-contract 移行スクリプト群の手順書。
        "tools/io-contracts-README.md",
    }
)
SUPPORT_PREFIXES = (
    ".vscode/",
    "tests/prompt-version/",
    "tools/for-other-repo/",
    "tools/skills/_kit/",
    "users-guide/",
)
NEVER_COPY_PREFIXES = ("tools/copy-hve-other-repo/",)
REQUIRED_FILES = frozenset(
    {
        ".github/copilot-instructions.md",
        ".github/scripts/hve_scope.py",
        "LICENSE",
        "cq/__init__.py",
        "hve.cmd",
        "hve.sh",
        "hve/__init__.py",
        "hve/setup-hve.ps1",
        "hve/setup-hve.sh",
        "mdq/__init__.py",
        "pyproject.toml",
    }
)
_REPARSE_POINT = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))


class CopyError(RuntimeError):
    """コピーを安全に完了できない。"""


@dataclass(frozen=True)
class CopyResult:
    source: Path
    destination: Path
    copied_files: int
    removed_entries: int
    dry_run: bool


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _contains_git_metadata_component(path: Path) -> bool:
    return any(part.casefold() == ".git" for part in path.parts)


def _is_preserved_git_entry(entry: Path, destination: Path) -> bool:
    if entry.name == ".git":
        return True
    if entry.name.casefold() != ".git":
        return False
    try:
        return os.path.samestat(entry.lstat(), (destination / ".git").lstat())
    except OSError:
        return False


def validate_paths(source_root: Path, destination: Path) -> tuple[Path, Path]:
    """破壊的削除より前に source / destination の境界を検証する。"""
    lexical_target = Path(os.path.abspath(Path(destination).expanduser()))
    if _contains_git_metadata_component(lexical_target):
        raise CopyError(
            f"destination must not be Git metadata or its child: {lexical_target}"
        )
    source = _resolved(Path(source_root))
    target = _resolved(Path(destination))

    if not source.is_dir():
        raise CopyError(f"HVE source directory does not exist: {source}")
    if not (source / SCOPE_MODULE).is_file():
        raise CopyError(f"HVE scope module does not exist: {source / SCOPE_MODULE}")
    if target.parent == target:
        raise CopyError(f"destination must not be a filesystem root: {target}")
    if target == _resolved(Path.home()):
        raise CopyError(f"destination must not be the current user's home directory: {target}")
    if _contains_git_metadata_component(target):
        raise CopyError(f"destination must not be Git metadata or its child: {target}")
    if _paths_overlap(source, target):
        raise CopyError(
            f"source and destination must not overlap: source={source}, destination={target}"
        )
    if target.exists() and not target.is_dir():
        raise CopyError(f"destination exists but is not a directory: {target}")
    return source, target


def _load_scope_module(source_root: Path) -> ModuleType:
    path = source_root / SCOPE_MODULE
    spec = importlib.util.spec_from_file_location("_copy_hve_scope", path)
    if spec is None or spec.loader is None:
        raise CopyError(f"cannot load HVE scope module: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise CopyError(f"cannot execute HVE scope module: {path}: {exc}") from exc
    if not callable(getattr(module, "is_in_scope", None)):
        raise CopyError(f"HVE scope module has no is_in_scope(): {path}")
    if not callable(getattr(module, "is_out_of_scope", None)):
        raise CopyError(f"HVE scope module has no is_out_of_scope(): {path}")
    return module


def _git_worktree_files(source_root: Path) -> tuple[Path, ...]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            check=False,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CopyError(f"cannot enumerate source files with git: {exc}") from exc
    if completed.returncode != 0:
        detail = os.fsdecode(completed.stderr).strip() or "unknown git error"
        raise CopyError(f"git ls-files failed: {detail}")

    paths: set[Path] = set()
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        value = os.fsdecode(raw)
        if "\\" in value:
            raise CopyError(f"git returned a non-POSIX repository path: {value!r}")
        pure = PurePosixPath(value)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise CopyError(f"git returned an unsafe repository path: {value!r}")
        paths.add(Path(*pure.parts))
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def _is_selected(relative: Path, scope: ModuleType) -> bool:
    value = relative.as_posix()
    if relative.parts and relative.parts[0].casefold() == ".git":
        return False
    if value.startswith(NEVER_COPY_PREFIXES):
        return False
    if value in SUPPORT_FILES:
        return True
    if value.startswith(SUPPORT_PREFIXES):
        return True
    if value.startswith(".github/"):
        # Repository-owned HVE metadata is included, except generated-app deploy
        # workflows explicitly excluded by the canonical scope implementation.
        return not bool(scope.is_out_of_scope(value))
    return bool(scope.is_in_scope(value))


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CopyError(f"cannot inspect source path: {path}: {exc}") from exc
    return stat.S_ISLNK(metadata.st_mode) or bool(
        int(getattr(metadata, "st_file_attributes", 0)) & _REPARSE_POINT
    )


def _validate_regular_source_file(
    source_root: Path,
    relative: Path,
    checked_directories: set[Path],
) -> bool:
    current = source_root
    for part in relative.parts[:-1]:
        current = current / part
        if current in checked_directories:
            continue
        if _is_link_or_reparse(current):
            raise CopyError(f"selected source directory is a link or reparse point: {current}")
        if not current.is_dir():
            return False
        checked_directories.add(current)

    source = source_root / relative
    if not source.exists():
        # A tracked file deleted in the working tree must remain absent in the copy.
        return False
    if _is_link_or_reparse(source):
        raise CopyError(f"selected source file is a link or reparse point: {source}")
    if not source.is_file():
        raise CopyError(f"selected source path is not a regular file: {source}")
    return True


def collect_source_files(source_root: Path) -> tuple[Path, ...]:
    """現在の worktree から HVE application の相対ファイル一覧を返す。"""
    source = _resolved(Path(source_root))
    scope = _load_scope_module(source)
    selected: list[Path] = []
    checked_directories: set[Path] = set()
    for relative in _git_worktree_files(source):
        if not _is_selected(relative, scope):
            continue
        if _validate_regular_source_file(source, relative, checked_directories):
            selected.append(relative)

    selected_values = {path.as_posix() for path in selected}
    missing = sorted(REQUIRED_FILES - selected_values)
    if missing:
        raise CopyError(
            "required HVE source files are missing: " + ", ".join(missing)
        )
    return tuple(selected)


def _destination_entries(destination: Path) -> tuple[Path, ...]:
    if not destination.exists():
        return ()
    if not destination.is_dir():
        raise CopyError(f"destination exists but is not a directory: {destination}")
    try:
        return tuple(
            sorted(
                (
                    entry
                    for entry in destination.iterdir()
                    if not _is_preserved_git_entry(entry, destination)
                ),
                key=lambda entry: entry.name,
            )
        )
    except OSError as exc:
        raise CopyError(f"cannot enumerate destination: {destination}: {exc}") from exc


def _git_identity(destination: Path) -> tuple[int, int, int, int, bytes | None] | None:
    git_entry = destination / ".git"
    try:
        metadata = git_entry.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CopyError(f"cannot inspect destination .git entry: {git_entry}: {exc}") from exc
    payload: bytes | None = None
    if stat.S_ISREG(metadata.st_mode):
        try:
            payload = git_entry.read_bytes()
        except OSError as exc:
            raise CopyError(f"cannot read destination .git file: {git_entry}: {exc}") from exc
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        int(metadata.st_size),
        payload,
    )


def _make_writable(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    is_reparse = bool(
        int(getattr(metadata, "st_file_attributes", 0)) & _REPARSE_POINT
    )
    if stat.S_ISLNK(metadata.st_mode) or is_reparse:
        return
    mode = stat.S_IMODE(metadata.st_mode) | stat.S_IWUSR | stat.S_IRUSR
    if stat.S_ISDIR(metadata.st_mode):
        mode |= stat.S_IXUSR
    path.chmod(mode)


def _raise_walk_error(error: OSError) -> None:
    raise error


def _make_tree_writable(root: Path) -> None:
    _make_writable(root)
    for current, directories, files in os.walk(
        root,
        topdown=True,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        current_path = Path(current)
        _make_writable(current_path)
        for name in directories:
            _make_writable(current_path / name)
        for name in files:
            _make_writable(current_path / name)


def _remove_path(path: Path) -> None:
    try:
        metadata = path.lstat()
        is_reparse = bool(
            int(getattr(metadata, "st_file_attributes", 0)) & _REPARSE_POINT
        )
        if stat.S_ISLNK(metadata.st_mode):
            path.unlink()
        elif is_reparse and path.is_dir():
            path.rmdir()
        elif stat.S_ISDIR(metadata.st_mode):
            _make_tree_writable(path)
            shutil.rmtree(path)
        else:
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
            path.unlink()
    except OSError as exc:
        raise CopyError(f"cannot delete destination entry: {path}: {exc}") from exc


def _clean_destination(destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    entries = _destination_entries(destination)
    for entry in entries:
        if _is_preserved_git_entry(entry, destination):  # Defense in depth.
            raise CopyError(f"internal error: refusing to delete .git: {entry}")
        _remove_path(entry)

    remaining = tuple(
        entry.name
        for entry in destination.iterdir()
        if not _is_preserved_git_entry(entry, destination)
    )
    if remaining:
        raise CopyError(
            "destination cleanup was incomplete; copy was not started: "
            + ", ".join(sorted(remaining))
        )
    return len(entries)


def _stage_files(source: Path, relative_files: Sequence[Path], staging: Path) -> None:
    for relative in relative_files:
        source_file = source / relative
        target_file = staging / relative
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
        except OSError as exc:
            raise CopyError(f"cannot stage source file: {source_file}: {exc}") from exc


def _copy_staged_files(
    staging: Path, destination: Path, relative_files: Sequence[Path]
) -> None:
    for relative in relative_files:
        source_file = staging / relative
        target_file = destination / relative
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
        except OSError as exc:
            raise CopyError(f"cannot copy staged file: {relative}: {exc}") from exc

    missing = [relative.as_posix() for relative in relative_files if not (destination / relative).is_file()]
    if missing:
        raise CopyError("destination verification failed for: " + ", ".join(missing))


def copy_hve_application(
    source_root: Path,
    destination: Path,
    *,
    dry_run: bool = False,
) -> CopyResult:
    """HVE source を staging 後、destination の `.git` 以外を置換する。"""
    source, target = validate_paths(source_root, destination)
    relative_files = collect_source_files(source)
    removable = _destination_entries(target)
    if dry_run:
        return CopyResult(source, target, len(relative_files), len(removable), True)

    git_before = _git_identity(target)
    with tempfile.TemporaryDirectory(prefix="copy-hve-") as temporary:
        staging = Path(temporary).resolve() / "payload"
        if _paths_overlap(staging, source) or _paths_overlap(staging, target):
            raise CopyError(
                f"temporary staging directory overlaps source or destination: {staging}"
            )
        staging.mkdir()
        _stage_files(source, relative_files, staging)

        removed = _clean_destination(target)
        if _git_identity(target) != git_before:
            raise CopyError("destination .git changed during cleanup; copy was not started")
        _copy_staged_files(staging, target, relative_files)

    if _git_identity(target) != git_before:
        raise CopyError("destination .git changed during copy")
    return CopyResult(source, target, len(relative_files), removed, False)


def _relax_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError):
            pass


def _confirm(destination: Path) -> bool:
    if not getattr(sys.stdin, "isatty", lambda: False)():
        return False
    print(f"警告: {destination} の直下にある .git 以外をすべて削除します。")
    try:
        answer = input("続行するには DELETE と入力してください: ")
    except (EOFError, OSError):
        return False
    return answer == "DELETE"


def main(
    argv: Sequence[str] | None = None,
    *,
    source_root: Path | None = None,
) -> int:
    _relax_output_encoding()
    parser = argparse.ArgumentParser(
        description=(
            "HVE application filesを指定フォルダーへコピーする。"
            "コピー先の .git は保持し、それ以外はコピー前にすべて削除する。"
        )
    )
    parser.add_argument("destination", type=Path, help="置き換え先フォルダー")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="削除・コピーを行わず対象件数だけ確認する",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="DELETE 確認を省略する（自動実行向け）",
    )
    args = parser.parse_args(argv)
    source = REPO_ROOT if source_root is None else Path(source_root)

    try:
        preview = copy_hve_application(source, args.destination, dry_run=True)
    except CopyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    git_state = "保持" if (preview.destination / ".git").exists() else "存在しない"
    print(f"source      : {preview.source}")
    print(f"destination : {preview.destination}")
    print(f"copy files  : {preview.copied_files}")
    print(f"delete items: {preview.removed_entries} (.git を除く直下エントリ)")
    print(f".git        : {git_state}")
    if args.dry_run:
        print("dry-run: ファイルシステムは変更していません。")
        return 0

    if not args.yes and not _confirm(preview.destination):
        print("ERROR: コピーを中止しました。自動実行では --yes が必要です。", file=sys.stderr)
        return 2

    try:
        result = copy_hve_application(source, preview.destination)
    except CopyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"完了: .git を保持し、{result.removed_entries} エントリを削除後、"
        f"HVE {result.copied_files} ファイルをコピーしました。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())