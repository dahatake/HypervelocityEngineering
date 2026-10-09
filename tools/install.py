#!/usr/bin/env python3
"""install.py - install / update / uninstall the Enterprise App Build Kit into another repository.

Usually started through tools/install.ps1 or tools/install.sh (one command, downloads this repository).
From a local clone:
  python tools/install.py --target <path-to-your-repo> [--dry-run] [--force] [--no-ci]
  python tools/install.py --target <repo> --check        # show what would change, exit 1 if outdated
  python tools/install.py --target <repo> --uninstall    # remove unmodified toolkit files (keeps docs and ledger)
  python tools/install.py --target <repo> --purge        # uninstall + remove docs, ledger, config, /work, appended lines
  (one command: tools/uninstall.ps1 / tools/uninstall.sh, same options as install.ps1 / install.sh)

What it does (idempotent):
  * copies the managed files (.github/agents, .github/skills, .github/hooks, .github/workflows/ebak-verify.yml,
    scripts/*) and updates them on re-run unless you modified them locally;
  * removes files that older versions installed but this version no longer ships (OBSOLETE), unless modified;
  * creates the management-data templates only when missing (docs/*.md, tests/system/ledger.json);
  * merges scripts/ebak.config.json (adds new keys, keeps your values);
  * adds /work/ to .gitignore, union-merge rules to .gitattributes, and a marked block to AGENTS.md
    and .github/copilot-instructions.md;
  * records versions and hashes in .github/ebak-toolkit.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

MANAGED = [
    ".github/agents/conductor.agent.md",
    ".github/agents/rd-author.agent.md",
    ".github/agents/rd-auditor.agent.md",
    ".github/agents/test-designer.agent.md",
    ".github/agents/implementer.agent.md",
    ".github/agents/reviewer.agent.md",
    ".github/skills/requirement-definition/SKILL.md",
    ".github/skills/implement-fr/SKILL.md",
    ".github/skills/implement-fr/ui-design.md",
    ".github/skills/implement-fr/original-rd.md",
    ".github/skills/system-test-increment/SKILL.md",
    ".github/skills/rd-audit/SKILL.md",
    ".github/skills/build/SKILL.md",
    ".github/skills/build-template/SKILL.md",
    ".github/hooks/quality-gates.json",
    ".github/workflows/ebak-verify.yml",
    "scripts/ebaklib.py",
    "scripts/rdcheck.py",
    "scripts/rdfix.py",
    "scripts/verify.py",
    "scripts/verify.ps1",
    "scripts/verify.sh",
    "scripts/next-id.py",
    "scripts/ledger.py",
    "scripts/select-tests.py",
    "scripts/summarize.py",
    "scripts/clean-work.py",
    "scripts/run-state.py",
    "scripts/integrate.py",
    "scripts/kpi.py",
    "scripts/import-speckit.py",
    "scripts/hooks/gate.py",
    "EABK-Studio/eabk_model.py",
    "EABK-Studio/README.md",
    "EABK-Studio/start.ps1",
    "EABK-Studio/start.sh",
    "EABK-Studio/studio.py",
    "EABK-Studio/web/app.css",
    "EABK-Studio/web/index.html",
    "EABK-Studio/web/js/app.js",
    "EABK-Studio/web/js/dashboard.js",
    "EABK-Studio/web/js/diagrams.js",
    "EABK-Studio/web/js/drawer.js",
    "EABK-Studio/web/js/i18n.js",
    "EABK-Studio/web/js/map2d.js",
    "EABK-Studio/web/js/map3d.js",
    "EABK-Studio/web/js/placement.js",
    "EABK-Studio/web/js/source.js",
    "EABK-Studio/web/js/store.js",
    "EABK-Studio/web/js/tables.js",
    "EABK-Studio/web/js/ui.js",
    "EABK-Studio/web/vendor/three.LICENSE",
    "EABK-Studio/web/vendor/three.module.min.js",
    "EABK-Studio/users-guide/README.md",
    "EABK-Studio/users-guide/01-first-steps.md",
    "EABK-Studio/users-guide/02-screens.md",
    "EABK-Studio/users-guide/03-tasks.md",
    "EABK-Studio/users-guide/04-troubleshooting.md",
]
# Files no longer shipped. Removed on update when unmodified.
OBSOLETE: list[str] = []
TEMPLATES = [
    "docs/requirements-definition.md",
    "docs/catalog.md",
    "docs/id-registry.md",
    "docs/run-history.md",
    "tests/system/ledger.json",
]
CONFIG = "scripts/ebak.config.json"
MANIFEST = ".github/ebak-toolkit.json"
EXECUTABLE = {"scripts/verify.sh", "EABK-Studio/start.sh"}
BEGIN, END = "<!-- ebak-abk:begin -->", "<!-- ebak-abk:end -->"
LEGACY_MARKERS = (("<!-- ebak-" + "conductor:begin -->", "<!-- ebak-" + "conductor:end -->"),)


def block_markers(text: str):
    """Return the (begin, end) pair present in text (current first, then legacy), or None."""
    for b, e in ((BEGIN, END),) + LEGACY_MARKERS:
        if b in text and e in text:
            return b, e
    return None
INSTRUCTIONS_BLOCK = """## Enterprise App Build Kit（要求定義書・カタログ・System Test の一貫性）

- 長時間の開発の依頼は、custom agent `conductor` に 1 回で渡します（VS Code・GitHub Copilot app では `/build`）。手順は `.github/agents/` と `.github/skills/` にあります。
- 検証は `python scripts/verify.py`（`scripts/verify.ps1` / `scripts/verify.sh`）。exit 0 が合格です。
- 要求の正本は `docs/requirements-definition.md` で、編集は rd-author だけが行います。ID は `python scripts/next-id.py <種別>` でだけ採番します。
- System Test の台帳 `tests/system/ledger.json` は `python scripts/ledger.py` でだけ更新します。
- 一時ファイル（ログ・証跡・実行結果・作業メモ）は `/work` に置きます（git の管理対象外。14 日で削除）。"""
GITIGNORE_LINES = ["/work/"]
GITATTR_LINES = ["docs/id-registry.md merge=union", "docs/run-history.md merge=union"]
GITIGNORE_HEADER = "# Enterprise App Build Kit: temporary run files (kept 14 days)"
GITATTR_HEADER = "# Enterprise App Build Kit: append-only records"
# Management data paths (defaults of scripts/ebaklib.py DEFAULT_CONFIG["files"]); --purge also honours the target's config.
DEFAULT_FILES = {
    "requirements": "docs/requirements-definition.md",
    "requirements_dir": "docs/requirements",
    "catalog": "docs/catalog.md",
    "id_registry": "docs/id-registry.md",
    "run_history": "docs/run-history.md",
    "ledger": "tests/system/ledger.json",
    "manual_tests": "docs/manual-tests.md",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def toolkit_version(source: Path) -> str:
    for line in (source / "scripts" / "ebaklib.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("TOOLKIT_VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


class Installer:
    def __init__(self, source: Path, target: Path, dry: bool, force: bool, no_ci: bool):
        self.source, self.target, self.dry, self.force, self.no_ci = source, target, dry, force, no_ci
        self.actions: List[Tuple[str, str]] = []
        self.manifest = self.load_manifest()
        self.new_hashes: Dict[str, str] = {}
        self.stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")

    def load_manifest(self) -> dict:
        p = self.target / MANIFEST
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"files": {}}

    def note(self, kind: str, rel: str) -> None:
        self.actions.append((kind, rel))

    def write_bytes(self, rel: str, data: bytes) -> None:
        if self.dry:
            return
        dest = self.target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if rel in EXECUTABLE and os.name != "nt":
            dest.chmod(dest.stat().st_mode | 0o111)

    def managed_files(self) -> List[str]:
        files = [f for f in MANAGED if not (self.no_ci and f.endswith("ebak-verify.yml"))]
        return files

    def install_managed(self) -> None:
        for rel in self.managed_files():
            src = self.source / rel
            if not src.exists():
                raise SystemExit(f"ERROR install: ソースに {rel} がありません（{self.source}）")
            new = sha(src)
            self.new_hashes[rel] = new
            dest = self.target / rel
            if not dest.exists():
                self.note("ADD", rel)
                self.write_bytes(rel, src.read_bytes())
                continue
            cur = sha(dest)
            if cur == new:
                self.note("SAME", rel)
                continue
            old = self.manifest.get("files", {}).get(rel)
            if old == cur or self.force:
                if old != cur and not self.dry:
                    shutil.copy2(dest, dest.with_name(dest.name + f".ebak-backup-{self.stamp}"))
                self.note("UPDATE" if old == cur else "OVERWRITE", rel)
                self.write_bytes(rel, src.read_bytes())
            else:
                self.note("KEEP-LOCAL", rel)
                self.new_hashes[rel] = old or cur

    def remove_obsolete(self) -> None:
        for rel in OBSOLETE:
            p = self.target / rel
            old = self.manifest.get("files", {}).get(rel)
            if not p.exists() or old is None:
                continue
            if sha(p) == old:
                self.note("REMOVE", rel)
                if not self.dry:
                    p.unlink()
                    try:
                        p.parent.rmdir()
                    except OSError:
                        pass
            else:
                self.note("KEEP-LOCAL", rel)
                self.new_hashes[rel] = old

    def install_templates(self) -> None:
        for rel in TEMPLATES:
            if (self.target / rel).exists():
                self.note("EXISTS", rel)
            else:
                self.note("CREATE", rel)
                self.write_bytes(rel, (self.source / rel).read_bytes())

    def install_config(self) -> None:
        src = json.loads((self.source / CONFIG).read_text(encoding="utf-8"))
        dest_p = self.target / CONFIG
        if not dest_p.exists():
            self.note("CREATE", CONFIG)
            self.write_bytes(CONFIG, (json.dumps(src, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            return
        try:
            cur = json.loads(dest_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.note("KEEP-LOCAL(invalid json)", CONFIG)
            return

        def merge(a: dict, b: dict) -> bool:
            changed = False
            for k, v in b.items():
                if k not in a:
                    a[k] = v
                    changed = True
                elif isinstance(v, dict) and isinstance(a[k], dict):
                    changed = merge(a[k], v) or changed
            return changed
        if merge(cur, src):
            self.note("MERGE", CONFIG)
            self.write_bytes(CONFIG, (json.dumps(cur, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        else:
            self.note("SAME", CONFIG)

    def ensure_lines(self, rel: str, lines: List[str], header: str) -> None:
        p = self.target / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        existing = {l.strip() for l in text.splitlines()}
        missing = [l for l in lines if l not in existing and not (l == "/work/" and existing & {"work/", "/work", "work"})]
        if not missing:
            self.note("SAME", rel)
            return
        self.note("APPEND", rel)
        if text and not text.endswith("\n"):
            text += "\n"
        text += ("\n" if text else "") + header + "\n" + "\n".join(missing) + "\n"
        self.write_bytes(rel, text.encode("utf-8"))

    def ensure_block(self, rel: str, title: str) -> None:
        p = self.target / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        block = f"{BEGIN}\n{INSTRUCTIONS_BLOCK}\n{END}"
        if BEGIN in text and END in text:
            pre, rest = text.split(BEGIN, 1)
            post = rest.split(END, 1)[1]
            new = pre + block + post
        else:
            new = (text.rstrip() + "\n\n" if text.strip() else title) + block + "\n"
        if new == text:
            self.note("SAME", rel)
            return
        self.note("BLOCK", rel)
        self.write_bytes(rel, new.encode("utf-8"))

    def write_manifest(self, version: str) -> None:
        data = {
            "name": "ebak-enterprise-app-build-kit",
            "version": version,
            "source": os.environ.get("EBAK_SOURCE_LABEL", str(self.source)),
            "installed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "files": self.new_hashes,
        }
        self.note("MANIFEST", MANIFEST)
        self.write_bytes(MANIFEST, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # ---- uninstall / cleanup -------------------------------------------------------------------

    def remove_path(self, rel: str, kind: str = "REMOVE") -> None:
        """Delete a file or directory under the target and prune the directories it leaves empty."""
        p = self.target / rel
        self.note(kind, rel)
        if self.dry:
            return
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
        if p.suffix == ".py":
            cache = p.parent / "__pycache__"
            for pyc in cache.glob(p.stem + ".*.pyc"):
                pyc.unlink(missing_ok=True)
            self.prune_dirs(cache)
        self.prune_dirs(p.parent)

    def prune_dirs(self, d: Path) -> None:
        root = self.target.resolve()
        d = d.resolve()
        while d != root and root in d.parents:
            try:
                d.rmdir()
            except OSError:
                return
            d = d.parent

    def uninstall_files(self) -> None:
        recorded = self.manifest.get("files", {})
        if recorded:
            candidates = dict(recorded)
        else:
            # No manifest (deleted or never written): treat a file as unmodified when it equals this toolkit's copy.
            candidates = {rel: (sha(self.source / rel) if (self.source / rel).exists() else None) for rel in MANAGED + OBSOLETE}
            if any((self.target / rel).exists() for rel in candidates):
                self.note("WARN", f"{MANIFEST} がないため、この版の toolkit と同じ内容のファイルだけを削除します")
        for rel, h in candidates.items():
            p = self.target / rel
            if not p.is_file():
                continue
            if self.force or (h is not None and sha(p) == h):
                self.remove_path(rel)
            else:
                self.note("KEEP-LOCAL", rel)

    def remove_backups(self) -> None:
        for rel in sorted(set(MANAGED + OBSOLETE + [CONFIG])):
            d = (self.target / rel).parent
            if d.is_dir():
                for b in sorted(d.glob(Path(rel).name + ".ebak-backup-*")):
                    self.remove_path(b.relative_to(self.target).as_posix())

    def remove_blocks(self) -> None:
        for rel, title in (("AGENTS.md", "# AGENTS.md"), (".github/copilot-instructions.md", "# Copilot instructions")):
            p = self.target / rel
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            changed = False
            while True:
                m = block_markers(text)
                if not m:
                    break
                b, e = m
                pre, rest = text.split(b, 1)
                if e not in rest:
                    break
                text = pre.rstrip() + "\n\n" + rest.split(e, 1)[1].lstrip("\n")
                changed = True
            if not changed:
                continue
            text = text.strip() + "\n"
            if text.strip() in ("", title):
                self.remove_path(rel, "UNBLOCK")
            else:
                self.note("UNBLOCK", rel)
                self.write_bytes(rel, text.encode("utf-8"))

    def remove_lines(self, rel: str, lines: List[str], header: str) -> None:
        p = self.target / rel
        if not p.is_file():
            return
        text = p.read_text(encoding="utf-8")
        drop = set(lines) | {header}
        kept = [l for l in text.splitlines() if l.strip() not in drop]
        if len(kept) == len(text.splitlines()):
            return
        out: List[str] = []
        for l in kept:
            if not l.strip() and (not out or not out[-1].strip()):
                continue
            out.append(l)
        while out and not out[-1].strip():
            out.pop()
        if not out:
            self.remove_path(rel, "UNAPPEND")
            return
        self.note("UNAPPEND", rel)
        self.write_bytes(rel, ("\n".join(out) + "\n").encode("utf-8"))

    def purge_data(self) -> None:
        """Remove the management data, config and run files that the toolkit created (--purge)."""
        cfg = dict(DEFAULT_FILES)
        work_dir = "work"
        try:
            data = json.loads((self.target / CONFIG).read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in (data.get("files") or {}).items() if isinstance(v, str) and v})
            work_dir = (data.get("work") or {}).get("dir") or work_dir
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
        rels = list(dict.fromkeys(TEMPLATES + [v for v in cfg.values()] + [work_dir, CONFIG]))
        root = self.target.resolve()
        for rel in rels:
            p = (self.target / rel).resolve()
            if p == root or root not in p.parents:
                self.note("SKIP(outside repo)", rel)
                continue
            if p.exists():
                self.remove_path(rel)

    def uninstall(self, purge: bool = False) -> None:
        self.uninstall_files()
        self.remove_blocks()
        if purge:
            self.remove_backups()
            self.purge_data()
            self.remove_lines(".gitignore", GITIGNORE_LINES, GITIGNORE_HEADER)
            self.remove_lines(".gitattributes", GITATTR_LINES, GITATTR_HEADER)
        if (self.target / MANIFEST).exists():
            self.remove_path(MANIFEST)
        if not purge:
            self.note("KEEP", "docs/*, tests/system/ledger.json, scripts/ebak.config.json, /work, .gitignore, .gitattributes"
                              "（管理データと設定は残します。すべて削除するには --purge）")


def run_verify(target: Path) -> int:
    try:
        proc = subprocess.run([sys.executable, str(target / "scripts" / "verify.py"), "--docs-only"],
                              cwd=str(target), capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"WARN verify を実行できません: {exc}")
        return 1
    print((proc.stdout or "").strip())
    return proc.returncode


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.getcwd(), help="導入先のリポジトリ（既定: カレントディレクトリ）")
    ap.add_argument("--source", default=str(Path(__file__).resolve().parent.parent), help="toolkit のソース（既定: このスクリプトのリポジトリ）")
    ap.add_argument("--dry-run", action="store_true", help="書き込まずに、行う操作だけを表示する")
    ap.add_argument("--check", action="store_true", help="更新が必要かを確かめる（必要なら exit 1）")
    ap.add_argument("--force", action="store_true", help="ローカルで変更した toolkit のファイルも上書きする（.ebak-backup-* を残す）")
    ap.add_argument("--no-ci", action="store_true", help=".github/workflows/ebak-verify.yml を入れない")
    ap.add_argument("--version", action="store_true", help="toolkit の版を表示して終了する")
    ap.add_argument("--uninstall", action="store_true", help="変更していない toolkit のファイルと AGENTS.md などのブロックを削除する（管理データと設定は残す）")
    ap.add_argument("--purge", action="store_true", help="--uninstall に加えて、管理データ（docs・台帳）・設定・/work・.gitignore と .gitattributes の追記・バックアップも削除する")
    ap.add_argument("--allow-non-git", action="store_true")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args(argv)

    if sys.version_info < (3, 9):
        raise SystemExit("ERROR install: Python 3.9 以上が必要です")
    source = Path(args.source).resolve()
    target = Path(args.target).resolve()
    if not (source / "scripts" / "ebaklib.py").exists():
        raise SystemExit(f"ERROR install: toolkit のソースが見つかりません: {source}")
    if args.version:
        print(toolkit_version(source))
        return 0
    if source == target:
        raise SystemExit("ERROR install: 導入先が toolkit のソースと同じです。--target に導入先のリポジトリを指定します")
    if not target.is_dir():
        raise SystemExit(f"ERROR install: 導入先がありません: {target}")
    if not (target / ".git").exists() and not args.allow_non_git:
        raise SystemExit(f"ERROR install: {target} は git リポジトリではありません（`git init` するか --allow-non-git）")

    dry = args.dry_run or args.check
    uninstalling = args.uninstall or args.purge
    ins = Installer(source, target, dry, args.force, args.no_ci)
    version = toolkit_version(source)
    if uninstalling:
        ins.uninstall(purge=args.purge)
    else:
        ins.install_managed()
        ins.remove_obsolete()
        ins.install_templates()
        ins.install_config()
        ins.ensure_lines(".gitignore", GITIGNORE_LINES, GITIGNORE_HEADER)
        ins.ensure_lines(".gitattributes", GITATTR_LINES, GITATTR_HEADER)
        ins.ensure_block("AGENTS.md", "# AGENTS.md\n\n")
        ins.ensure_block(".github/copilot-instructions.md", "# Copilot instructions\n\n")
        if ins.manifest.get("version") != version or any(k not in ("SAME", "EXISTS", "KEEP-LOCAL") for k, _ in ins.actions):
            ins.write_manifest(version)

    width = max((len(k) for k, _ in ins.actions), default=4)
    for kind, rel in ins.actions:
        print(f"{kind.ljust(width)}  {rel}")
    pending = [a for a in ins.actions if a[0] not in ("SAME", "EXISTS", "KEEP-LOCAL", "KEEP", "WARN")]
    kept = [rel for k, rel in ins.actions if k == "KEEP-LOCAL"]
    if uninstalling:
        mode = ("purge" if args.purge else "uninstall") + (" (dry-run)" if dry else "")
    else:
        mode = "check" if args.check else ("dry-run" if args.dry_run else "install")
    print(f"\nEnterprise App Build Kit {version}: {mode} {target}  changes={len(pending)}")
    if kept:
        if uninstalling:
            print(f"注意: ローカルで変更されたファイルは削除していません（{len(kept)} 件）。削除するには --force。")
        else:
            print(f"注意: ローカルで変更されたファイルは更新していません（{len(kept)} 件）。上書きするには --force（バックアップを残します）。")
    if args.check:
        return 1 if pending else 0
    if uninstalling:
        if not dry:
            print("\n次の手順:")
            print("  1. 変更を確認して commit します: git status && git add -A && git commit -m \"Remove Enterprise App Build Kit\"")
            if args.purge:
                print("  2. run が作った worktree と work/* ブランチが残っていれば削除します: git worktree list / git branch --list \"work/*\"")
            else:
                print("  2. 管理データ・設定・/work も消すには --purge で再実行します（先に --dry-run で確認できます）")
        return 0
    if dry:
        return 0
    if not args.skip_verify:
        print("\n--- verify --docs-only ---")
        run_verify(target)
    print("\n次の手順（README.md の「インストール」「Quickstart」）:")
    print("  1. 変更を確認して commit します: git add -A && git commit -m \"Add Enterprise App Build Kit\"")
    print("  2. scripts/ebak.config.json の verify.commands に、ビルド・静的検査・テストのコマンドを登録します（初回の実行で implementer が登録することもできます）")
    print("  3. VS Code の Agents ウィンドウで Session Target=Copilot、Agent=conductor、Autopilot、New Worktree を選び、")
    print("     チャット欄に「/build やりたいこと」と書いて送ります（入力欄は表示されません）")
    print("     （雛形は「/build-template」（または「/build template」）で表示されます。Copilot CLI では `copilot --agent conductor --autopilot` などで同じ雛形を送ります）")
    print("     GitHub Copilot app では、プロジェクトにこのリポジトリを追加し、新しい worktree・Autopilot・Agent=conductor で「/build やりたいこと」を送ります")
    return 0


if __name__ == "__main__":
    sys.exit(main())
