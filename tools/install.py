#!/usr/bin/env python3
"""install.py - install / update / uninstall the Assured Build Kit into another repository.

Usually started through tools/install.ps1 or tools/install.sh (one command, downloads this repository).
From a local clone:
  python tools/install.py --target <path-to-your-repo> [--dry-run] [--force] [--no-ci]
  python tools/install.py --target <repo> --check        # show what would change, exit 1 if outdated
  python tools/install.py --target <repo> --uninstall    # remove unmodified toolkit files (keeps docs and ledger)

What it does (idempotent):
  * copies the managed files (.github/agents, .github/skills, .github/hooks, .github/workflows/hve-verify.yml,
    scripts/*) and updates them on re-run unless you modified them locally;
  * removes files that older versions installed but this version no longer ships (OBSOLETE), unless modified;
  * creates the management-data templates only when missing (docs/*.md, tests/system/ledger.json);
  * merges scripts/hve.config.json (adds new keys, keeps your values);
  * adds /work/ to .gitignore, union-merge rules to .gitattributes, and a marked block to AGENTS.md
    and .github/copilot-instructions.md;
  * records versions and hashes in .github/hve-toolkit.json.
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
    ".github/skills/system-test-increment/SKILL.md",
    ".github/skills/rd-audit/SKILL.md",
    ".github/skills/build/SKILL.md",
    ".github/hooks/quality-gates.json",
    ".github/workflows/hve-verify.yml",
    "scripts/hvelib.py",
    "scripts/rdcheck.py",
    "scripts/verify.py",
    "scripts/verify.ps1",
    "scripts/verify.sh",
    "scripts/next-id.py",
    "scripts/ledger.py",
    "scripts/select-tests.py",
    "scripts/summarize.py",
    "scripts/clean-work.py",
    "scripts/run-state.py",
    "scripts/kpi.py",
    "scripts/import-speckit.py",
    "scripts/hooks/gate.py",
]
# Shipped by older versions. Removed on update when unmodified (prompt files are not loaded by the
# VS Code Agent Host / Copilot CLI; /build is now the skill .github/skills/build/SKILL.md).
OBSOLETE = [
    ".github/prompts/build.prompt.md",
]
TEMPLATES = [
    "docs/requirements-definition.md",
    "docs/catalog.md",
    "docs/id-registry.md",
    "docs/run-history.md",
    "tests/system/ledger.json",
]
CONFIG = "scripts/hve.config.json"
MANIFEST = ".github/hve-toolkit.json"
EXECUTABLE = {"scripts/verify.sh"}
BEGIN, END = "<!-- hve-abk:begin -->", "<!-- hve-abk:end -->"
LEGACY_MARKERS = (("<!-- hve-" + "conductor:begin -->", "<!-- hve-" + "conductor:end -->"),)


def block_markers(text: str):
    """Return the (begin, end) pair present in text (current first, then legacy), or None."""
    for b, e in ((BEGIN, END),) + LEGACY_MARKERS:
        if b in text and e in text:
            return b, e
    return None
INSTRUCTIONS_BLOCK = """## Assured Build Kit（要求定義書・カタログ・System Test の一貫性）

- 長時間の開発の依頼は、custom agent `conductor` に 1 回で渡します（VS Code・GitHub Copilot app では `/build`）。手順は `.github/agents/` と `.github/skills/` にあります。
- 検証は `python scripts/verify.py`（`scripts/verify.ps1` / `scripts/verify.sh`）。exit 0 が合格です。
- 要求の正本は `docs/requirements-definition.md` で、編集は rd-author だけが行います。ID は `python scripts/next-id.py <種別>` でだけ採番します。
- System Test の台帳 `tests/system/ledger.json` は `python scripts/ledger.py` でだけ更新します。
- 一時ファイル（ログ・証跡・実行結果・作業メモ）は `/work` に置きます（git の管理対象外。14 日で削除）。"""
GITIGNORE_LINES = ["/work/"]
GITATTR_LINES = ["docs/id-registry.md merge=union", "docs/run-history.md merge=union"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def toolkit_version(source: Path) -> str:
    for line in (source / "scripts" / "hvelib.py").read_text(encoding="utf-8").splitlines():
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
        files = [f for f in MANAGED if not (self.no_ci and f.endswith("hve-verify.yml"))]
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
                    shutil.copy2(dest, dest.with_name(dest.name + f".hve-backup-{self.stamp}"))
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
            "name": "hve-assured-build-kit",
            "version": version,
            "source": os.environ.get("HVE_SOURCE_LABEL", str(self.source)),
            "installed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "files": self.new_hashes,
        }
        self.note("MANIFEST", MANIFEST)
        self.write_bytes(MANIFEST, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def uninstall(self) -> None:
        files = self.manifest.get("files", {})
        if not files:
            raise SystemExit(f"ERROR install: {MANIFEST} がないため、導入済みのファイルを特定できません")
        for rel, h in files.items():
            p = self.target / rel
            if not p.exists():
                continue
            if sha(p) == h or self.force:
                self.note("REMOVE", rel)
                if not self.dry:
                    p.unlink()
            else:
                self.note("KEEP-LOCAL", rel)
        for rel in ("AGENTS.md", ".github/copilot-instructions.md"):
            p = self.target / rel
            if p.exists():
                text = p.read_text(encoding="utf-8")
                if BEGIN in text and END in text:
                    pre, rest = text.split(BEGIN, 1)
                    new = (pre.rstrip() + "\n" + rest.split(END, 1)[1].lstrip("\n")).strip() + "\n"
                    self.note("UNBLOCK", rel)
                    if not self.dry:
                        if new.strip() in ("", "# AGENTS.md", "# Copilot instructions"):
                            p.unlink()
                        else:
                            p.write_text(new, encoding="utf-8")
        if not self.dry:
            (self.target / MANIFEST).unlink(missing_ok=True)
        self.note("KEEP", "docs/*, tests/system/ledger.json, scripts/hve.config.json, .gitignore, .gitattributes（管理データと設定は残します）")


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
    ap.add_argument("--force", action="store_true", help="ローカルで変更した toolkit のファイルも上書きする（.hve-backup-* を残す）")
    ap.add_argument("--no-ci", action="store_true", help=".github/workflows/hve-verify.yml を入れない")
    ap.add_argument("--version", action="store_true", help="toolkit の版を表示して終了する")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--allow-non-git", action="store_true")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args(argv)

    if sys.version_info < (3, 9):
        raise SystemExit("ERROR install: Python 3.9 以上が必要です")
    source = Path(args.source).resolve()
    target = Path(args.target).resolve()
    if not (source / "scripts" / "hvelib.py").exists():
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
    ins = Installer(source, target, dry, args.force, args.no_ci)
    version = toolkit_version(source)
    if args.uninstall:
        ins.uninstall()
    else:
        ins.install_managed()
        ins.remove_obsolete()
        ins.install_templates()
        ins.install_config()
        ins.ensure_lines(".gitignore", GITIGNORE_LINES, "# Assured Build Kit: temporary run files (kept 14 days)")
        ins.ensure_lines(".gitattributes", GITATTR_LINES, "# Assured Build Kit: append-only records")
        ins.ensure_block("AGENTS.md", "# AGENTS.md\n\n")
        ins.ensure_block(".github/copilot-instructions.md", "# Copilot instructions\n\n")
        if ins.manifest.get("version") != version or any(k not in ("SAME", "EXISTS", "KEEP-LOCAL") for k, _ in ins.actions):
            ins.write_manifest(version)

    width = max((len(k) for k, _ in ins.actions), default=4)
    for kind, rel in ins.actions:
        print(f"{kind.ljust(width)}  {rel}")
    pending = [a for a in ins.actions if a[0] not in ("SAME", "EXISTS", "KEEP-LOCAL", "KEEP")]
    kept = [rel for k, rel in ins.actions if k == "KEEP-LOCAL"]
    mode = "uninstall" if args.uninstall else ("check" if args.check else ("dry-run" if args.dry_run else "install"))
    print(f"\nAssured Build Kit {version}: {mode} {target}  changes={len(pending)}")
    if kept:
        print(f"注意: ローカルで変更されたファイルは更新していません（{len(kept)} 件）。上書きするには --force（バックアップを残します）。")
    if args.check:
        return 1 if pending else 0
    if dry or args.uninstall:
        return 0
    if not args.skip_verify:
        print("\n--- verify --docs-only ---")
        run_verify(target)
    print("\n次の手順（README.md の「インストール」「Quickstart」）:")
    print("  1. 変更を確認して commit します: git add -A && git commit -m \"Add Assured Build Kit\"")
    print("  2. scripts/hve.config.json の verify.commands に、ビルド・静的検査・テストのコマンドを登録します（初回の実行で implementer が登録することもできます）")
    print("  3. VS Code の Agents ウィンドウで Session Target=Copilot、Agent=conductor、Autopilot、New Worktree を選び、")
    print("     チャット欄に「/build やりたいこと」と書いて送ります（入力欄は表示されません）")
    print("     （雛形は「/build template」で表示されます。Copilot CLI では `copilot --agent conductor --autopilot` などで同じ雛形を送ります）")
    print("     GitHub Copilot app では、プロジェクトにこのリポジトリを追加し、新しい worktree・Autopilot・Agent=conductor で「/build やりたいこと」を送ります")
    return 0


if __name__ == "__main__":
    sys.exit(main())
