#!/usr/bin/env python3
"""他リポジトリへ配布パッケージをコピーする単一実装。

`tools/for-other-repo/<package>/package.toml` が「何をどこから集めるか」を宣言し、
本スクリプトが実際の収集・版判定・マニフェスト生成を行う。エンジン本体や
Skill 定義はここで再実装せず、既存の `tools/skills/*` キットと `hve/toolsearch/`
をそのまま集める。

使い方（上流リポジトリのルートから実行）::

    python tools/for-other-repo/copy_to_repo.py --list
    python tools/for-other-repo/copy_to_repo.py D:\\other-repo\\tools\\hve-kits
    python tools/for-other-repo/copy_to_repo.py D:\\other-repo\\tools -p tool-search
    python tools/for-other-repo/copy_to_repo.py D:\\other-repo\\tools --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PACKAGES_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGES_DIR.parent.parent
BOOTSTRAP_DIR = PACKAGES_DIR / "_bootstrap"

MANIFEST_NAME = "KIT-VERSION.json"
MANIFEST_SCHEMA_VERSION = 1

# 配布物に混ぜてはならないもの。package.toml の exclude を書き忘れても落とす。
ALWAYS_DROP_DIRS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "node_modules"}
)
ALWAYS_DROP_SUFFIXES = frozenset({".pyc", ".pyo", ".pyd"})

_VERSION_RE = re.compile(r"^\s*__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


class PackageError(RuntimeError):
    """package.toml の宣言が不正、または参照先が存在しない。"""


# ---------------------------------------------------------------------------
# パッケージ宣言の読み込み
# ---------------------------------------------------------------------------


def load_package(package_dir: Path) -> dict[str, Any]:
    manifest = package_dir / "package.toml"
    if not manifest.is_file():
        raise PackageError(f"package manifest not found: {manifest}")
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))["package"]
    for key in ("name", "version", "engine"):
        if not data.get(key):
            raise PackageError(f"{manifest} is missing package.{key}")
    data["_dir"] = package_dir
    return data


def discover_packages() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(PACKAGES_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not (path / "package.toml").is_file():
            continue
        package = load_package(path)
        found[package["name"]] = package
    return found


# ---------------------------------------------------------------------------
# コピー
# ---------------------------------------------------------------------------


def _matches(rel_posix: str, patterns: Sequence[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(rel_posix, pattern) for pattern in patterns)


def _is_always_dropped(rel: Path) -> bool:
    if any(part in ALWAYS_DROP_DIRS for part in rel.parts):
        return True
    if any(part.startswith(".venv") for part in rel.parts):
        return True
    return rel.suffix in ALWAYS_DROP_SUFFIXES


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(source: Path, target: Path, excludes: Sequence[str]) -> int:
    copied = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if _is_always_dropped(rel) or _matches(rel.as_posix(), excludes):
            continue
        _copy_file(path, target / rel)
        copied += 1
    return copied


def stage_package(package: dict[str, Any], staging: Path, *, include_docs: bool) -> None:
    """package.toml の宣言どおりに staging ツリーを組み立てる。"""
    for source in package.get("sources", []):
        origin = (REPO_ROOT / source["from"]).resolve()
        target = staging / source.get("to", ".")
        excludes = tuple(source.get("exclude", []))
        if origin.is_dir():
            _copy_tree(origin, target, excludes)
        elif origin.is_file():
            _copy_file(origin, target)
        else:
            raise PackageError(
                f"[{package['name']}] declared source does not exist: {origin}"
            )

    if include_docs:
        for doc in package.get("docs", []):
            origin = (REPO_ROOT / doc["from"]).resolve()
            target = staging / doc["to"]
            if origin.is_dir():
                _copy_tree(origin, target, tuple(doc.get("exclude", [])))
            elif origin.is_file():
                _copy_file(origin, target)
            else:
                raise PackageError(
                    f"[{package['name']}] declared doc does not exist: {origin}"
                )

    for name in ("install.py", "install.ps1", "install.sh"):
        _copy_file(BOOTSTRAP_DIR / name, staging / name)

    extras = package.get("extra_dependencies")
    if extras:
        payload = {
            "schema_version": 1,
            "note": package.get(
                "extra_dependencies_note", "install.py がキットの venv へ追加導入する。"
            ),
            "packages": list(extras),
        }
        (staging / "install-extras.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# 版管理
# ---------------------------------------------------------------------------


def parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value).split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts) or (0,)


def file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == MANIFEST_NAME or _is_always_dropped(rel):
            continue
        hashes[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def source_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def engine_version(staging: Path, engine: str, fallback: str) -> str:
    init = staging / "vendor" / engine / "__init__.py"
    if init.is_file():
        found = _VERSION_RE.search(init.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found.group(1)
    return fallback


def read_manifest(package_root: Path) -> dict[str, Any] | None:
    path = package_root / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_manifest(
    package: dict[str, Any], staging: Path, hashes: dict[str, str]
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "package": package["name"],
        "version": package["version"],
        "engine": package["engine"],
        "engine_version": engine_version(staging, package["engine"], package["version"]),
        "summary": package.get("summary", ""),
        "post_install_note": package.get("post_install_note", ""),
        "source_repo": package.get("source_repo", "dahatake/RoyalytyService2ndGen"),
        "source_commit": source_commit(),
        "copied_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": len(hashes),
        # 利用者が編集する前提のファイル。改変検出の対象から外す。
        "preserved": [],
        "files": hashes,
    }


def compare_versions(current: dict[str, Any] | None, new_version: str) -> str:
    """`new` / `upgrade` / `same` / `downgrade` を返す。"""
    if current is None:
        return "new"
    old = parse_version(str(current.get("version", "0")))
    new = parse_version(new_version)
    if new > old:
        return "upgrade"
    if new == old:
        return "same"
    return "downgrade"


def local_modifications(package_root: Path, manifest: dict[str, Any]) -> list[str]:
    """マニフェストに記録された配布ファイルのうち、コピー先で改変されたもの。

    `preserved`（利用者が編集する前提のファイル）は対象外。
    """
    preserved = set(manifest.get("preserved") or ())
    modified: list[str] = []
    for rel, digest in (manifest.get("files") or {}).items():
        if rel in preserved:
            continue
        path = package_root / rel
        if not path.is_file():
            modified.append(f"{rel} (欠落)")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            modified.append(f"{rel} (改変)")
    return modified


# ---------------------------------------------------------------------------
# 適用
# ---------------------------------------------------------------------------


def apply_package(
    package: dict[str, Any],
    staging: Path,
    package_root: Path,
    manifest: dict[str, Any],
    previous: dict[str, Any] | None,
    preserve: Sequence[str],
) -> tuple[int, int, list[str]]:
    """staging をコピー先へ反映する。戻り値は (書き込み数, 削除数, 温存したパス)。"""
    kept: list[str] = []
    written = 0
    for rel in sorted(manifest["files"]):
        target = package_root / rel
        if rel in preserve and target.is_file():
            # 温存したファイルの実体はコピー先のもの。マニフェストもそれに合わせる。
            manifest["files"][rel] = hashlib.sha256(target.read_bytes()).hexdigest()
            kept.append(rel)
            continue
        _copy_file(staging / rel, target)
        written += 1
    manifest["preserved"] = kept

    removed = 0
    if previous:
        obsolete = set(previous.get("files") or {}) - set(manifest["files"])
        for rel in sorted(obsolete):
            target = package_root / rel
            if target.is_file():
                target.unlink()
                removed += 1
        _prune_empty_dirs(package_root)

    (package_root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return written, removed, kept


def _prune_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_list(packages: dict[str, dict[str, Any]]) -> None:
    print("利用可能なパッケージ:")
    for name, package in packages.items():
        print(f"  {name:<16} v{package['version']:<8} engine={package['engine']}")
        summary = package.get("summary")
        if summary:
            print(f"  {'':<16} {summary}")


def _resolve_targets(
    packages: dict[str, dict[str, Any]], requested: Sequence[str]
) -> list[dict[str, Any]]:
    if not requested:
        return list(packages.values())
    selected: list[dict[str, Any]] = []
    for name in requested:
        if name not in packages:
            raise SystemExit(
                f"未知のパッケージです: {name}（--list で一覧を確認してください）"
            )
        selected.append(packages[name])
    return selected


def _check(package: dict[str, Any], package_root: Path) -> int:
    current = read_manifest(package_root)
    status = compare_versions(current, package["version"])
    label = f"[{package['name']}]"
    if current is None:
        print(f"{label} 未導入 → v{package['version']} を導入できます: {package_root}")
        return 0
    print(
        f"{label} コピー先 v{current.get('version')} "
        f"(copied_at={current.get('copied_at')}, commit={current.get('source_commit')})"
        f" / 上流 v{package['version']} → {status}"
    )
    modified = local_modifications(package_root, current)
    if modified:
        print(f"{label} コピー先で改変/欠落したファイル {len(modified)} 件:")
        for rel in modified[:20]:
            print(f"    - {rel}")
        if len(modified) > 20:
            print(f"    ... 他 {len(modified) - 20} 件")
    return 0


def _relax_output_encoding() -> None:
    """cp932 コンソールへ日本語ログを出しても落とさない。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    _relax_output_encoding()

    parser = argparse.ArgumentParser(
        description="markdown-query / code-query / tool-search を他リポジトリへコピーする",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "dest",
        nargs="?",
        type=Path,
        help="コピー先ディレクトリ。配下に <パッケージ名>/ が作られる。",
    )
    parser.add_argument(
        "-p", "--package", action="append", default=[],
        help="コピーするパッケージ名（複数指定可。既定: 全部）",
    )
    parser.add_argument("--list", action="store_true", help="一覧を表示して終了する")
    parser.add_argument(
        "--check", action="store_true",
        help="コピーせず、コピー先の版と改変状況だけ表示する",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="コピー対象を表示するだけで書き込まない"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="版が同じ／古い場合でもコピーする（既定はスキップ）",
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="コピー先直下へ展開する（単一パッケージのときのみ）",
    )
    parser.add_argument(
        "--no-docs", action="store_true", help="users-guide のドキュメント同梱を省略する"
    )
    args = parser.parse_args(argv)

    try:
        packages = discover_packages()
    except PackageError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    if args.list:
        _print_list(packages)
        return 0

    if args.dest is None:
        parser.error("コピー先パスを指定してください（--list / --help も参照）")

    targets = _resolve_targets(packages, args.package)
    if args.flat and len(targets) != 1:
        parser.error("--flat は単一パッケージ（-p で 1 つ指定）のときだけ使えます")

    dest_root = args.dest.expanduser().resolve()
    exit_code = 0

    for package in targets:
        package_root = dest_root if args.flat else dest_root / package["name"]
        label = f"[{package['name']}]"

        if args.check:
            _check(package, package_root)
            continue

        previous = read_manifest(package_root)
        status = compare_versions(previous, package["version"])
        if previous is not None and status in ("same", "downgrade") and not args.force:
            print(
                f"{label} スキップ: コピー先 v{previous.get('version')} / "
                f"上流 v{package['version']} ({status})。--force で上書きできます。"
            )
            continue

        with tempfile.TemporaryDirectory(prefix="for-other-repo-") as tmp:
            staging = Path(tmp) / package["name"]
            try:
                stage_package(package, staging, include_docs=not args.no_docs)
            except PackageError as exc:
                print(f"❌ {exc}", file=sys.stderr)
                exit_code = 1
                continue

            hashes = file_hashes(staging)
            manifest = build_manifest(package, staging, hashes)

            if args.dry_run:
                print(
                    f"{label} dry-run: {len(hashes)} ファイルを {package_root} へ "
                    f"({status}, v{package['version']})"
                )
                for rel in list(hashes)[:15]:
                    print(f"    {rel}")
                if len(hashes) > 15:
                    print(f"    ... 他 {len(hashes) - 15} ファイル")
                continue

            if previous:
                modified = local_modifications(package_root, previous)
                if modified:
                    print(f"{label} 警告: コピー先で改変/欠落していたファイル {len(modified)} 件を上書きします")
                    for rel in modified[:10]:
                        print(f"    - {rel}")

            package_root.mkdir(parents=True, exist_ok=True)
            written, removed, kept = apply_package(
                package,
                staging,
                package_root,
                manifest,
                previous,
                tuple(package.get("preserve", [])),
            )

        print(
            f"{label} {status}: v{manifest['version']} "
            f"(engine {manifest['engine']} {manifest['engine_version']}, "
            f"commit {manifest['source_commit'] or 'unknown'}) → {package_root}"
        )
        print(f"{label} 書き込み {written} / 削除 {removed} / 温存 {len(kept)}")
        for rel in kept:
            print(f"    温存: {rel}")
        entry = "install.ps1" if sys.platform == "win32" else "install.sh"
        print(f"{label} 次の手順: コピー先リポジトリのルートで {package_root / entry} を実行")

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
