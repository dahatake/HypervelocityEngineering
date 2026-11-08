#!/usr/bin/env python3
"""Verification matrix for tools/uninstall.py (toolkit maintenance; FR-1087 AC-475 AC-476 AC-478; not shipped).

Each historical EABK version is installed with ITS OWN tools/install.py (from `git archive <commit>`) into a fresh git
repository that already has committed user files. Variants:
  manifest         the installed state as is
  no-manifest      the manifest deleted (as if lost, or never written)
  upgrade-to-HEAD  then this working tree's installer run on top
Then the CURRENT tools/uninstall.py --purge --runs removes it. Oracle: exit 0 and `git status --porcelain --ignored
--untracked-files=all` empty, i.e. the repository is byte for byte its pre-install commit, ignored files included.

  python tools/verify-uninstall-matrix.py            # representative versions x 3 variants
  python tools/verify-uninstall-matrix.py --all      # every committed installer version (merges included), no-manifest
Results: work/uninstall-matrix/result*.json, and log-<commit>-<variant>.txt for each failure. Exit 0 when all are OK.
Baselines use LF: installers before FR-1087 rewrote a CRLF AGENTS.md / .gitignore as LF, which cannot be undone
(CRLF round trip of the current installer is covered by tests/toolkit/test_uninstall.py).
"""
import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work" / "uninstall-matrix"
REPRESENTATIVE = ["a62da1fa", "acc23fc5", "a0414f8b", "d3976f78", "71768a0c", "39a88a31", "c61ee5b4", "9f28f205",
                  "5160adcc", "f55bed82", "2c0e4e9f", "d87628cb", "e0060f36", "30610559", "205ddddb"]


def sh(cmd, cwd, timeout=900):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def extract(commit):
    dest = OUT / f"src-{commit}"
    if dest.exists():
        return dest
    data = subprocess.run(["git", "archive", commit], cwd=str(ROOT), capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:
            tf.extractall(dest)  # noqa: S202 - our own git archive
    return dest


def rmtree(p):
    shutil.rmtree(p, onerror=lambda f, x, e: (Path(x).chmod(0o700), f(x)))


def baseline(name):
    t = OUT / name
    if t.exists():
        rmtree(t)
    t.mkdir(parents=True)
    sh(["git", "init", "-q"], t)
    if not (t / ".git" / "HEAD").is_file():
        raise SystemExit(f"git init failed in {t}")
    sh(["git", "config", "core.autocrlf", "false"], t)
    (t / "AGENTS.md").write_bytes(b"# My project agents\n\nBe careful with the payments module.\n")
    (t / ".gitignore").write_bytes(b"node_modules/\n*.log\n")
    (t / "users-guide").mkdir()
    (t / "users-guide" / "README.md").write_bytes(b"# Our own user guide (not EABK)\n")
    (t / "docs").mkdir()
    (t / "docs" / "architecture.md").write_bytes(b"# Architecture\n")
    (t / "app.py").write_bytes(b"print('hello')\n")
    sh(["git", "add", "-A"], t)
    sh(["git", "-c", "user.email=m@x", "-c", "user.name=m", "commit", "-qm", "baseline"], t)
    return t


def install(src, t):
    py = (src / "tools" / "install.py").read_text(encoding="utf-8")
    cmd = [sys.executable, str(src / "tools" / "install.py"), "--target", str(t)]
    if "--source" in py:
        cmd += ["--source", str(src)]
    if "--skip-verify" in py:
        cmd.append("--skip-verify")
    return sh(cmd, t).returncode


def uninstall(t):
    p = sh([sys.executable, str(ROOT / "tools" / "uninstall.py"), "--target", str(t), "--purge", "--runs"], t)
    st = sh(["git", "status", "--porcelain", "--ignored", "--untracked-files=all"], t).stdout.strip()
    return p.returncode, st, p.stdout + p.stderr


def plan(all_versions, commits):
    if all_versions:
        allc = sh(["git", "log", "--reverse", "--full-history", "--format=%h", "--", "tools/install.py"], ROOT).stdout.split()
        return [(c, ("no-manifest",)) for c in allc]
    return [(c, ("manifest", "no-manifest", "upgrade-to-HEAD")) for c in (commits or REPRESENTATIVE)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="every committed installer version (no-manifest variant)")
    ap.add_argument("--commit", action="append", help="only these commits (repeatable)")
    ap.add_argument("--keep", action="store_true", help="keep the extracted sources and the test repositories")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for c, variants in plan(args.all, args.commit):
        try:
            src = extract(c)
        except subprocess.CalledProcessError:
            print(f"SKIP {c} (not in this clone)", flush=True)
            continue
        for variant in variants:
            t = baseline(f"t-{c}-{variant}")
            irc = install(src, t)
            paths = len(sh(["git", "status", "--porcelain", "--untracked-files=all"], t).stdout.splitlines())
            if variant == "no-manifest":
                for m in (".github/ebak-toolkit.json", ".github/hve-toolkit.json"):
                    if (t / m).exists():
                        (t / m).unlink()
            if variant == "upgrade-to-HEAD":
                install(ROOT, t)
            urc, st, out = uninstall(t)
            ok = urc == 0 and st == ""
            rows.append({"commit": c, "variant": variant, "install_rc": irc, "installed_paths": paths,
                         "uninstall_rc": urc, "residue": st.splitlines(), "ok": ok})
            print(f"{'OK  ' if ok else 'FAIL'} {c} {variant:16} install_rc={irc} paths={paths} uninstall_rc={urc}"
                  + ("" if ok else "\n      " + "\n      ".join(st.splitlines()[:15])), flush=True)
            if not ok:
                (OUT / f"log-{c}-{variant}.txt").write_text(out, encoding="utf-8")
            elif not args.keep:
                rmtree(t)
        if not args.keep:
            rmtree(src)
    (OUT / ("result-all.json" if args.all else "result.json")).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    bad = [r for r in rows if not r["ok"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
