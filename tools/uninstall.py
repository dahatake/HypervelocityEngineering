#!/usr/bin/env python3
"""uninstall.py - remove the Enterprise App Build Kit (EABK), installed by any version, from a git repository.

Standard library only (Python 3.9+). Needs tools/uninstall-catalog.json next to it (or --catalog); the one-command
wrappers tools/uninstall.ps1 / tools/uninstall.sh download both files, so it works in any repository:

  python tools/uninstall.py --target <repo> [--dry-run]   # remove the toolkit files, blocks and manifests
  python tools/uninstall.py --target <repo> --purge        # also the management data, config, /work, appended lines,
                                                           # backups: nothing of EABK remains
  python tools/uninstall.py --target <repo> --runs         # also the worktrees and merged run/* branches of the old
                                                           # conductor (otherwise only reported)

What is removed, for every version (0.1 "hve" names included; see tools/build-uninstall-catalog.py):
  * a file at a path some version shipped, when its content equals a content that version shipped (or the hash a
    manifest recorded). A modified file is kept (KEEP-LOCAL) unless --force and the path is recorded in a manifest or
    shipped by this version. A file of yours at an old path (e.g. your own users-guide/README.md) is never removed;
  * the marked blocks in AGENTS.md / .github/copilot-instructions.md (every marker any version used); the file is
    deleted when nothing but the toolkit's title remains;
  * the manifests (.github/ebak-toolkit.json, .github/hve-toolkit.json);
  * with --purge: the management data (docs/*, the ledger, as configured), the config, /work (unless it holds tracked
    files), the toolkit's sections of .gitignore / .gitattributes (your lines and blank lines stay), *.ebak-backup-* /
    *.hve-backup-* files.
Symbolic links and junctions are never followed. Exit code: 0 = nothing of the toolkit remains in the chosen scope,
1 = something remains (listed as RESIDUE), 2 = error. --dry-run only lists and exits 0.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

CATALOG_NAME = "uninstall-catalog.json"


def norm_sha(data: bytes) -> str:
    """Same as tools/install.py sha(): CRLF and LF are the same content for text files."""
    if b"\0" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def is_link(p: Path) -> bool:
    """A symbolic link or (Windows) a junction / other reparse point: never followed, never deleted through."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def safe_rel(rel: str) -> bool:
    p = Path(rel)
    return bool(rel) and not p.is_absolute() and ".." not in p.parts and not rel.startswith(("/", "\\"))


def load_catalog(path: Optional[str]) -> dict:
    p = Path(path) if path else Path(__file__).resolve().parent / CATALOG_NAME
    if not p.is_file():
        raise SystemExit(f"ERROR uninstall: カタログがありません: {p}（tools/uninstall.ps1 / uninstall.sh で実行するか、--catalog で指定します）")
    cat = json.loads(p.read_text(encoding="utf-8"))
    if cat.get("schema") != 1:
        raise SystemExit(f"ERROR uninstall: 未知のカタログの形式です: {p}")
    # From a clone of the toolkit, files changed after the catalog was built are still recognised.
    src_root = p.resolve().parent.parent
    if (src_root / "scripts" / "ebaklib.py").is_file():
        for dest, src in (cat.get("current") or {}).items():
            f = src_root / src
            if f.is_file():
                cat["files"].setdefault(dest, [])
                h = norm_sha(f.read_bytes())
                if h not in cat["files"][dest]:
                    cat["files"][dest].append(h)
    return cat


class Text:
    """A text file read and written with its own line ending (CRLF files stay CRLF)."""

    def __init__(self, p: Path):
        raw = p.read_bytes()
        self.eol = "\r\n" if b"\r\n" in raw else "\n"
        self.text = raw.decode("utf-8", "surrogateescape").replace("\r\n", "\n")

    def encode(self, text: str) -> bytes:
        return text.replace("\n", self.eol).encode("utf-8", "surrogateescape")


class Uninstaller:
    def __init__(self, target: Path, cat: dict, dry: bool, force: bool, label: str = "REMOVE"):
        self.target, self.cat, self.dry, self.force, self.label = target, cat, dry, force, label
        self.actions: List[Tuple[str, str]] = []
        self.residue: List[str] = []
        self.root = target.resolve()
        self.recorded: Dict[str, str] = {}
        for m in cat.get("manifests", []):
            try:
                data = json.loads((target / m).read_text(encoding="utf-8"))
                self.recorded.update({k: v for k, v in (data.get("files") or {}).items() if isinstance(v, str)})
            except (OSError, ValueError, AttributeError):
                pass

    # ---- primitives ------------------------------------------------------------------------------

    def note(self, kind: str, rel: str) -> None:
        self.actions.append((kind, rel))

    def inside(self, rel: str) -> bool:
        if not safe_rel(rel):
            return False
        p = (self.target / rel).resolve()
        return p != self.root and self.root in p.parents

    def write(self, rel: str, data: bytes) -> None:
        if not self.dry:
            (self.target / rel).write_bytes(data)

    def remove(self, rel: str, kind: Optional[str] = None) -> None:
        p = self.target / rel
        if self.dry:
            self.note(kind or self.label, rel)
            return
        for attempt in range(5):
            try:
                self._remove(p)
                break
            except OSError as e:
                # Windows: a file briefly held by a scanner / an editor; report it instead of stopping half-way
                if attempt == 4:
                    self.note("ERROR", f"{rel}: {e}")
                    self.residue.append(rel)
                    return
                time.sleep(0.2 * (attempt + 1))
        self.note(kind or self.label, rel)
        if p.suffix == ".py":
            cache = p.parent / "__pycache__"
            for pyc in cache.glob(p.stem + ".*.pyc"):
                try:
                    pyc.unlink()
                except OSError:
                    pass
            self.prune(cache)
        self.prune(p.parent)

    @staticmethod
    def _remove(p: Path) -> None:
        def writable(func, path, _exc):  # read-only files (e.g. git objects in a worktree) on Windows
            os.chmod(path, stat.S_IWRITE)
            func(path)
        if p.is_dir() and not is_link(p):
            shutil.rmtree(p, onerror=writable)  # Python >= 3.8 removes a junction inside without emptying its target
        elif is_link(p) and p.is_dir():
            os.rmdir(p)
        elif os.path.lexists(p):
            p.unlink()

    def prune(self, d: Path) -> None:
        d = d.resolve() if d.exists() else d
        while d != self.root and self.root in d.parents:
            try:
                d.rmdir()
            except OSError:
                return
            d = d.parent

    # ---- steps -----------------------------------------------------------------------------------

    def files(self, force_paths: Set[str]) -> None:
        """Toolkit files of every version: removed when their content is one the toolkit shipped."""
        known: Dict[str, List[str]] = self.cat.get("files", {})
        for rel in sorted(set(known) | set(self.recorded)):
            if not self.inside(rel):
                continue
            p = self.target / rel
            if is_link(p):
                self.note("KEEP-LINK", rel)
                self.residue.append(rel)
                continue
            if not p.is_file():
                continue
            data = p.read_bytes()
            hashes = set(known.get(rel, []))
            if rel in self.recorded:
                hashes.add(self.recorded[rel])
            if norm_sha(data) in hashes or hashlib.sha256(data).hexdigest() in hashes:
                self.remove(rel)
            elif self.force and rel in force_paths:
                self.remove(rel, self.label if self.label != "REMOVE" else "REMOVE(force)")
            elif rel in force_paths:
                self.note("KEEP-LOCAL", rel)
                self.residue.append(rel)
            else:
                # only an older version used this path and no manifest says the toolkit put the file there:
                # it may be the user's own file (e.g. users-guide/README.md), so it is listed, never removed
                self.note("KEEP-UNKNOWN", rel)

    def backups(self) -> None:
        infixes = self.cat.get("backup_infixes", [])
        dirs: Set[str] = set()
        for rel in set(self.cat.get("files", {})) | set(self.recorded) | set(self.cat.get("configs", [])):
            if safe_rel(rel):
                dirs.add(str(Path(rel).parent.as_posix()))
        for d in sorted(dirs):
            base = self.target / d
            if not base.is_dir() or is_link(base) or not self.inside(d if d != "." else "x"):
                continue
            for f in sorted(base.iterdir()):
                if f.is_file() and not is_link(f) and any(i in f.name for i in infixes):
                    self.remove(f.relative_to(self.target).as_posix())

    def blocks(self) -> None:
        markers = [tuple(m) for m in self.cat.get("markers", [])]
        for rel, title in self.cat.get("blocks", []):
            p = self.target / rel
            if not p.is_file() or is_link(p):
                continue
            t = Text(p)
            text, changed = t.text, False
            for begin, end in markers:
                while begin in text and end in text.split(begin, 1)[1]:
                    pre, rest = text.split(begin, 1)
                    post = rest.split(end, 1)[1].lstrip("\n")
                    text = pre.rstrip() + ("\n\n" + post if post.strip() else "\n") if pre.strip() else post
                    changed = True
            if not changed:
                continue
            if text.strip() in ("", title.strip()):
                self.remove(rel, "UNBLOCK")
            else:
                self.note("UNBLOCK", rel)
                self.write(rel, t.encode(text))

    def ignore_lines(self) -> None:
        """Remove the sections the toolkit appended (a header any version wrote + the lines under it that are
        toolkit lines) and the blank line it inserted before them; everything else stays byte for byte."""
        for rel, spec in (self.cat.get("ignore") or {}).items():
            p = self.target / rel
            if not p.is_file() or is_link(p):
                continue
            t = Text(p)
            headers, toolkit = set(spec.get("headers", [])), set(spec.get("lines", []))
            lines = t.text.split("\n")
            out: List[str] = []
            i, changed = 0, False
            while i < len(lines):
                if lines[i].strip() in headers:
                    changed = True
                    if out and not out[-1].strip():
                        out.pop()
                    i += 1
                    while i < len(lines) and lines[i].strip() in toolkit:
                        i += 1
                    continue
                out.append(lines[i])
                i += 1
            if not changed:
                continue
            text = "\n".join(out)
            if not text.strip():
                self.remove(rel, "UNAPPEND")
                continue
            if t.text.endswith("\n") and not text.endswith("\n"):
                text += "\n"
            self.note("UNAPPEND", rel)
            self.write(rel, t.encode(text))

    def config_paths(self) -> Tuple[List[str], List[str]]:
        data_paths = list(self.cat.get("data", []))
        work = list(self.cat.get("work_dirs", ["work"]))
        for c in self.cat.get("configs", []):
            try:
                cfg = json.loads((self.target / c).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            files = cfg.get("files") or {}
            if isinstance(files, dict):
                data_paths += [v for v in files.values() if isinstance(v, str) and v]
            w = (cfg.get("work") or {}).get("dir") if isinstance(cfg.get("work"), dict) else None
            if isinstance(w, str) and w:
                work.append(w)
        return list(dict.fromkeys(data_paths)), list(dict.fromkeys(work))

    def tracked(self, rel: str) -> bool:
        if not (self.target / ".git").exists():
            return False
        proc = subprocess.run(["git", "ls-files", "-z", "--", rel], cwd=str(self.target), capture_output=True)
        return proc.returncode == 0 and bool(proc.stdout.strip(b"\0"))

    def data(self) -> None:
        data_paths, work = self.config_paths()
        for rel in data_paths:
            if not self.inside(rel):
                self.note("SKIP(outside repo)", rel)
            elif os.path.lexists(self.target / rel):
                self.remove(rel)
        for rel in work:
            if not self.inside(rel):
                self.note("SKIP(outside repo)", rel)
            elif os.path.lexists(self.target / rel):
                if self.tracked(rel):
                    self.note("KEEP(tracked files)", rel)
                    self.residue.append(rel)
                else:
                    self.remove(rel)
                    if not self.dry and (self.target / ".git").exists():
                        subprocess.run(["git", "worktree", "prune"], cwd=str(self.target), capture_output=True)

    def configs(self) -> None:
        for rel in self.cat.get("configs", []):
            if self.inside(rel) and (self.target / rel).is_file():
                self.remove(rel)

    def manifests(self) -> None:
        for rel in self.cat.get("manifests", []):
            if self.inside(rel) and (self.target / rel).is_file():
                self.remove(rel)

    # ---- runs of the old conductor (worktrees and branches) -------------------------------------

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=str(self.target), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def run_worktrees(self) -> List[Tuple[Path, str]]:
        spec = self.cat.get("runs") or {}
        prefix = "refs/heads/" + spec.get("branch_prefix", "run/")
        proc = self._git("worktree", "list", "--porcelain")
        if proc.returncode != 0:
            return []
        out, path, branch = [], None, ""
        _, work = self.config_paths()
        pools = [(self.root / w / spec.get("pool_dir", "worktrees")) for w in work if safe_rel(w)]
        for line in proc.stdout.splitlines() + [""]:
            if line.startswith("worktree "):
                path, branch = Path(line[9:].strip()), ""
            elif line.startswith("branch "):
                branch = line[7:].strip()
            elif not line.strip() and path is not None:
                rp = path.resolve() if path.exists() else path
                is_run = (branch.startswith(prefix)
                          or fnmatch.fnmatch(path.name, f"{self.root.name}{spec.get('worktree_infix', '-run-')}*")
                          or any(pool == rp.parent or pool in rp.parents for pool in pools))
                if is_run and rp != self.root:
                    out.append((path, branch[len("refs/heads/"):] if branch else ""))
                path = None
        return out

    def unlink_links(self, top: Path) -> None:
        """Remove the dependency links (node_modules ... shared by junction / symlink) without touching their targets."""
        for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
            for name in list(dirnames) + filenames:
                p = Path(dirpath) / name
                if name == ".git":
                    continue
                if is_link(p):
                    self.note("UNLINK", str(p))
                    if not self.dry:
                        if p.is_dir():
                            os.rmdir(p)
                        else:
                            p.unlink()
                    if name in dirnames:
                        dirnames.remove(name)

    def runs(self, remove: bool) -> None:
        if not (self.target / ".git").exists():
            return
        spec = self.cat.get("runs") or {}
        for path, branch in self.run_worktrees():
            if not remove:
                self.note("RUN-WORKTREE", f"{path}（--runs で削除できます）")
                continue
            if path.exists():
                self.unlink_links(path)
            self.note("REMOVE-WORKTREE", str(path))
            if not self.dry:
                proc = self._git("worktree", "remove", "--force", str(path))
                if proc.returncode != 0:
                    self.note("KEEP-WORKTREE", f"{path}: {proc.stderr.strip()[:200]}")
                    self.residue.append(str(path))
        if remove and not self.dry:
            self._git("worktree", "prune")
        refs = self._git("for-each-ref", "--format=%(refname:short)", "refs/heads/" + spec.get("branch_prefix", "run/"))
        for b in [x for x in refs.stdout.splitlines() if x.strip()]:
            if not remove:
                self.note("RUN-BRANCH", f"{b}（--runs で、取り込み済みなら削除できます）")
                continue
            merged = self._git("merge-base", "--is-ancestor", b, "HEAD").returncode == 0
            if not merged:
                self.note("KEEP-BRANCH(unmerged)", b)
                self.residue.append(b)
                continue
            self.note("DELETE-BRANCH", b)
            if not self.dry:
                proc = self._git("branch", "-D", b)
                if proc.returncode != 0:
                    self.note("KEEP-BRANCH", f"{b}: {proc.stderr.strip()[:200]}")
                    self.residue.append(b)

    # ---- modes -----------------------------------------------------------------------------------

    def force_paths(self) -> Set[str]:
        return set(self.recorded) | set((self.cat.get("current") or {}).keys())

    def uninstall(self, purge: bool, runs: bool) -> None:
        self.files(self.force_paths())
        self.blocks()
        if purge:
            self.backups()
            self.data()
            self.configs()
            self.ignore_lines()
        self.manifests()
        self.runs(remove=runs)

    def clean(self) -> None:
        """For `install.py --clean`: every toolkit file (modified ones too when this version ships them or a manifest
        recorded them), backups, config, blocks, appended sections and manifests; the management data stays."""
        self.files(self.force_paths())
        self.backups()
        self.configs()
        self.blocks()
        self.ignore_lines()
        self.manifests()


def is_git_root(target: Path) -> bool:
    # A folder inside another repository (or a broken .git) must not count: git would act on the outer repository.
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(target), capture_output=True, text=True)
    except OSError:
        return False
    if proc.returncode != 0 or not proc.stdout.strip():
        return False
    return os.path.normcase(str(Path(proc.stdout.strip()).resolve())) == os.path.normcase(str(target))


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.getcwd(), help="対象のリポジトリ（既定: カレントディレクトリ）")
    ap.add_argument("--catalog", help=f"カタログ（既定: このスクリプトの隣の {CATALOG_NAME}）")
    ap.add_argument("--dry-run", action="store_true", help="書き込まずに、行う操作だけを表示する")
    ap.add_argument("--force", action="store_true",
                    help="変更された toolkit のファイルも削除する（manifest に記録されたパスか、この版が配布するパスだけ）")
    ap.add_argument("--purge", action="store_true",
                    help="管理データ（docs・台帳）・設定・/work・.gitignore と .gitattributes の追記・バックアップも削除する")
    ap.add_argument("--runs", action="store_true",
                    help="旧版の conductor が作った worktree と、取り込み済みの run/* ブランチも削除する（既定は表示だけ）")
    ap.add_argument("--allow-non-git", action="store_true")
    args = ap.parse_args(argv)
    if sys.version_info < (3, 9):
        raise SystemExit("ERROR uninstall: Python 3.9 以上が必要です")
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise SystemExit(f"ERROR uninstall: 対象がありません: {target}")
    if (target / "tools" / "build-uninstall-catalog.py").is_file() and (target / "tools" / CATALOG_NAME).is_file():
        raise SystemExit("ERROR uninstall: 対象が toolkit のソースです。--target にアンインストールするリポジトリを指定します")
    if not args.allow_non_git and not is_git_root(target):
        raise SystemExit(f"ERROR uninstall: {target} は git リポジトリの最上位ではありません（削除を git から戻せるように。--allow-non-git で続行）")
    cat = load_catalog(args.catalog)
    u = Uninstaller(target, cat, args.dry_run, args.force)
    u.uninstall(purge=args.purge, runs=args.runs)

    width = max((len(k) for k, _ in u.actions), default=4)
    for kind, rel in u.actions:
        print(f"{kind.ljust(width)}  {rel}")
    info = ("KEEP-LOCAL", "KEEP-UNKNOWN", "KEEP-LINK", "RUN-WORKTREE", "RUN-BRANCH", "KEEP(tracked files)", "KEEP-BRANCH(unmerged)",
            "KEEP-WORKTREE", "KEEP-BRANCH", "SKIP(outside repo)", "ERROR")
    changes = [a for a in u.actions if a[0] not in info]
    mode = ("purge" if args.purge else "uninstall") + (" (dry-run)" if args.dry_run else "")
    print(f"\nEnterprise App Build Kit (catalog {cat.get('toolkit_version')}, {cat.get('installer_versions')} installer versions): "
          f"{mode} {target}  changes={len(changes)}")
    if not u.actions:
        print("EABK の痕跡はありません。")
    if not args.purge:
        print("残したもの: 管理データ（docs/*・台帳）・設定・/work・.gitignore と .gitattributes の追記・バックアップ（すべて消すには --purge）")
    if any(k in ("RUN-WORKTREE", "RUN-BRANCH") for k, _ in u.actions):
        print("注意: 旧版の conductor の worktree・run/* ブランチがあります。削除するには --runs（未取り込みのブランチは残します）")
    if any(k == "KEEP-UNKNOWN" for k, _ in u.actions):
        print("KEEP-UNKNOWN: 旧版だけが使ったパスにある、どの版の内容とも一致しないファイルです（利用者のファイルの可能性があるため残しました）")
    if args.dry_run:
        return 0
    if u.residue:
        print(f"\nRESIDUE: EABK の痕跡が {len(u.residue)} 件残っています（変更されたファイルなど。内容を確かめて手で削除するか、--force）:")
        for r in u.residue:
            print(f"  {r}")
        return 1
    print("\n次の手順: 変更を確認して commit します: git status && git add -A && git commit -m \"Remove Enterprise App Build Kit\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
