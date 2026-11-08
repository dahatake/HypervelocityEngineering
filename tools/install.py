#!/usr/bin/env python3
"""install.py - install / update / uninstall the Enterprise App Build Kit into another repository.

Usually started through tools/install.ps1 or tools/install.sh (one command, downloads this repository).
From a local clone:
  python tools/install.py --target <path-to-your-repo> [--dry-run] [--force] [--no-ci]
  python tools/install.py --target <repo> --check        # show what would change, exit 1 if outdated
  python tools/install.py --target <repo> --clean        # clean install: delete every toolkit file, then install
  python tools/install.py --target <repo> --uninstall    # remove unmodified toolkit files (keeps docs and ledger)
  python tools/install.py --target <repo> --purge        # uninstall + remove docs, ledger, config, /work, appended lines
  (one command: tools/uninstall.ps1 / tools/uninstall.sh, same options as install.ps1 / install.sh)

What it does (idempotent) - EABK Lite: rules + data layer + deterministic checks, no orchestration:
  * copies the managed files (.github/agents/rd-auditor, .github/skills, .github/workflows/ebak-verify.yml (check only),
    scripts/*, EABK-Studio/ = the read-only data-layer viewer with its role guides
    and screenshots) and updates them on re-run unless you modified them locally;
  * keeps no migration code for older versions: `--clean` (clean install) deletes every file the toolkit installed
    (the manifest's records, this version's files, backups, the config, the marked blocks and appended lines) and
    then installs from scratch; the management data (docs/*, the ledger) and your code and tests are kept;
  * creates the management-data templates only when missing (docs/*.md, tests/system/ledger.json);
  * merges scripts/ebak.config.json (adds new keys, keeps your values);
  * adds /work/ to .gitignore, union-merge rules to .gitattributes, and a marked block to AGENTS.md
    and .github/copilot-instructions.md;
  * records versions and hashes in .github/ebak-toolkit.json;
  * after an install / update, calls the data-layer common entry point once: `scripts/rdfix.py --full --apply`
    (check -> repair -> re-check; the requirements definition and docs/integrations.md are never changed; repairs are
    not committed). `--no-repair` runs `rdfix.py --full` (check + plan only, writes nothing); `--skip-verify` neither
    checks nor repairs; --dry-run / --check / --uninstall / --purge never repair. The installer's exit code does
    not depend on the data-layer result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

MANAGED = [
    ".github/agents/rd-auditor.agent.md",
    ".github/skills/requirement-definition/SKILL.md",
    ".github/skills/requirement-definition/original.md",
    ".github/skills/requirement-definition/integration-checklist.md",
    ".github/skills/requirement-definition/integration-requirements.md",
    ".github/skills/rd-audit/SKILL.md",
    ".github/skills/adopt-existing/SKILL.md",
    ".github/workflows/ebak-verify.yml",
    "scripts/ebaklib.py",
    "scripts/rdcheck.py",
    "scripts/rdfix.py",
    "scripts/entities.py",
    "scripts/extpoints.py",
    "scripts/metadata.json",
    "scripts/verify.py",
    "scripts/verify.ps1",
    "scripts/verify.sh",
    "scripts/next-id.py",
    "scripts/ledger.py",
    "scripts/summarize.py",
    "scripts/adopt.py",
    "tools/install.py",
    "users-guide/README.md",
    "users-guide/01-writing-requests.md",
    "users-guide/02-daily-workflow.md",
    "users-guide/03-requirements-format.md",
    "users-guide/04-customization.md",
    "users-guide/05-scripts-reference.md",
    "users-guide/06-quality-gates.md",
    "users-guide/07-troubleshooting.md",
    "users-guide/08-roadmap.md",
    "users-guide/09-versioning.md",
    "users-guide/10-adopting-existing-apps.md",
    "users-guide/11-integration-catalog.md",
    "users-guide/README.en.md",
    "users-guide/01-writing-requests.en.md",
    "users-guide/02-daily-workflow.en.md",
    "users-guide/03-requirements-format.en.md",
    "users-guide/04-customization.en.md",
    "users-guide/05-scripts-reference.en.md",
    "users-guide/06-quality-gates.en.md",
    "users-guide/07-troubleshooting.en.md",
    "users-guide/08-roadmap.en.md",
    "users-guide/09-versioning.en.md",
    "users-guide/10-adopting-existing-apps.en.md",
    "users-guide/11-integration-catalog.en.md",
    "users-guide/images/architecture-diagram.png",
    "users-guide/images/dashboard.png",
    "EABK-Studio/eabk_model.py",
    "EABK-Studio/README.md",
    "EABK-Studio/start.ps1",
    "EABK-Studio/start.sh",
    "EABK-Studio/studio.py",
    "EABK-Studio/web/app.css",
    "EABK-Studio/web/sz.css",
    "EABK-Studio/web/index.html",
    "EABK-Studio/web/js/app.js",
    "EABK-Studio/web/js/dashboard.js",
    "EABK-Studio/web/js/diagrams.js",
    "EABK-Studio/web/js/drawer.js",
    "EABK-Studio/web/js/entities.js",
    "EABK-Studio/web/js/hier.js",
    "EABK-Studio/web/js/i18n.js",
    "EABK-Studio/web/js/implstatus.js",
    "EABK-Studio/web/js/insights.js",
    "EABK-Studio/web/js/map2d.js",
    "EABK-Studio/web/js/map3d.js",
    "EABK-Studio/web/js/placement.js",
    "EABK-Studio/web/js/semzoom.js",
    "EABK-Studio/web/js/source.js",
    "EABK-Studio/web/js/store.js",
    "EABK-Studio/web/js/sz2d.js",
    "EABK-Studio/web/js/sz3d.js",
    "EABK-Studio/web/js/tables.js",
    "EABK-Studio/web/js/ui.js",
    "EABK-Studio/web/vendor/three.LICENSE",
    "EABK-Studio/web/vendor/three.module.min.js",
    "users-guide/studio/README.md",
    "users-guide/studio/01-first-steps.md",
    "users-guide/studio/02-screens.md",
    "users-guide/studio/03-tasks.md",
    "users-guide/studio/04-troubleshooting.md",
    "users-guide/studio/05-product-manager.md",
    "users-guide/studio/06-architect.md",
    "users-guide/studio/07-software-engineer.md",
    "users-guide/studio/08-data-reference.md",
    "users-guide/studio/capture-screens.py",
    "users-guide/studio/screen-images.json",
    "users-guide/studio/images/cases.png",
    "users-guide/studio/images/consistency.png",
    "users-guide/studio/images/dashboard.png",
    "users-guide/studio/images/diagrams.png",
    "users-guide/studio/images/header.png",
    "users-guide/studio/images/maintenance.png",
    "users-guide/studio/images/map2d.png",
    "users-guide/studio/images/map3d.png",
    "users-guide/studio/images/placement.png",
    "users-guide/studio/images/runtime.png",
    "users-guide/studio/images/source.png",
    "users-guide/studio/images/states.png",
    "users-guide/studio/images/structure.png",
    "users-guide/studio/images/tables.png",
]
# The source's users-guide/ is installed as EABK-docs/ in the target (the target's own users-guide/ is never touched).
GUIDE_SRC, GUIDE_DEST = "users-guide/", "EABK-docs/"


def dest_of(rel: str) -> str:
    return GUIDE_DEST + rel[len(GUIDE_SRC):] if rel.startswith(GUIDE_SRC) else rel


TEMPLATES = [
    "docs/requirements-definition.md",
    "docs/catalog.md",
    "docs/integrations.md",
    "docs/id-registry.md",
    "tests/system/ledger.json",
]
CONFIG = "scripts/ebak.config.json"
MANIFEST = ".github/ebak-toolkit.json"
EXECUTABLE = {"scripts/verify.sh", "EABK-Studio/start.sh"}
BEGIN, END = "<!-- ebak-abk:begin -->", "<!-- ebak-abk:end -->"

INSTRUCTIONS_BLOCK = """## Enterprise App Build Kit Lite（要求定義書・カタログ・System Test の一貫性）

- 振る舞いを変える変更（機能の追加・変更・削除）では、同じ変更の中で `docs/requirements-definition.md` の要求と受入基準（AC）を更新します。誰が編集してもかまいません（手順は skill `requirement-definition`）。
- 新しい ID は `python scripts/next-id.py <種別>` でだけ採番します。手で番号を振りません（複数の人・PC で並行しても重複させないため）。
- テストの名前かコメントに、検証する要求 ID と AC ID を書きます（例: `FR-012 AC-031`）。System Test の台帳 `tests/system/ledger.json` は `python scripts/ledger.py` でだけ更新し、テストを消す・弱めるときは `--reason` で理由を残します。
- ファイルを足す・名前を変える・消すときは、`docs/catalog.md` の行も直します（`python scripts/rdfix.py --apply` で追従できます）。
- 完了の前に `python scripts/verify.py` を実行して exit 0 にします（CI の `ebak-verify` も同じ検査をします）。
- 一時ファイル（ログ・証跡・作業メモ）は `/work` に置きます（git の管理対象外）。"""
GITIGNORE_LINES = ["/work/"]
GITATTR_LINES = ["docs/id-registry.md merge=union",
                 "scripts/*.sh text eol=lf", "EABK-Studio/*.sh text eol=lf"]
GITIGNORE_HEADER = "# Enterprise App Build Kit: temporary files (logs, evidence, notes)"
GITATTR_HEADER = "# Enterprise App Build Kit: append-only records"
# Every header the toolkit has ever written starts with this; --clean / --purge remove such a header and its lines.
TOOLKIT_HEADER_PREFIX = "# Enterprise App Build Kit"
# Management data paths (defaults of scripts/ebaklib.py DEFAULT_CONFIG["files"]); --purge also honours the target's config.
DEFAULT_FILES = {
    "requirements": "docs/requirements-definition.md",
    "requirements_dir": "docs/requirements",
    "catalog": "docs/catalog.md",
    "id_registry": "docs/id-registry.md",
    "ledger": "tests/system/ledger.json",
    "manual_tests": "docs/manual-tests.md",
    "integrations": "docs/integrations.md",
}


def preflight() -> None:
    """Warn (never fail) about missing tools that the installed scripts, agents and hooks rely on."""
    if not shutil.which("git"):
        print("警告: git が PATH にありません。verify.py の変更範囲の判定と CI が動きません。")
    if not shutil.which("python"):
        print("警告: `python` コマンドが PATH にありません（`python3` / `py` のみ）。手順書・agent・verify.commands は `python scripts/...` と書かれています。"
              "Windows は python.org か `winget install Python.Python.3.12` で導入（PATH に追加）、macOS・Linux は `python` を `python3` の別名にします"
              "（例: python-is-python3、または venv を有効化）。")


def sha(path: Path) -> str:
    """Content hash that ignores CRLF vs LF in text files: a Windows checkout (core.autocrlf) turns the same toolkit
    file into CRLF, which must not look like a local modification (binary files, with NUL bytes, are hashed as is)."""
    data = path.read_bytes()
    if b"\0" not in data:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def sha_raw(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_recorded(path: Path, recorded) -> bool:
    """True when `path` still has the content the manifest recorded (older manifests hold raw byte hashes)."""
    return bool(recorded) and recorded in (sha(path), sha_raw(path))


IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+(.+?)|import\s+([\w.]+)(?:\s+as\s+(\w+))?)\s*(?:#.*)?$")


def _flatten_json(node, prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten_json(v, f"{prefix}/{k}"))
    elif isinstance(node, list):
        for v in node:
            out[f"{prefix}[{json.dumps(v, ensure_ascii=False, sort_keys=True)[:80]}]"] = ""
    else:
        out[prefix] = ""
    return out


def find_dropped_wiring(rel: str, old_text: str, new_text: str, target: Path,
                        registered: set, toolkit_modules: set) -> List[Tuple[int, str]]:
    """FR-1083: lines the user added to a toolkit file (in `old_text`, the backup) that wire a project-specific check in
    and would be lost by the overwrite, unless the module is already registered as an extension (FR-1082).
    Returns [(line number in the backup, line)].  Conservative on purpose: only imports of a module that exists in the
    target's scripts/ but is not a toolkit module, and calls through the names it binds, plus keys added to metadata.json."""
    out: List[Tuple[int, str]] = []
    if rel == "scripts/metadata.json":
        try:
            old_p, new_p = _flatten_json(json.loads(old_text)), _flatten_json(json.loads(new_text))
        except ValueError:
            return out
        lines = old_text.splitlines()
        for path in old_p:
            if path in new_p:
                continue
            key = path.rsplit("/", 1)[-1].split("[", 1)[0]
            n = next((i for i, l in enumerate(lines, 1) if key and f'"{key}"' in l), 0)
            out.append((n, f"metadata.json に追加された定義 {path}"))
        return out
    if not (rel.startswith("scripts/") and rel.endswith(".py")):
        return out
    new_lines = {l.strip() for l in new_text.splitlines()}
    added = [(i, l) for i, l in enumerate(old_text.splitlines(), 1)
             if l.strip() and not l.strip().startswith("#") and l.strip() not in new_lines]
    bound: Dict[str, int] = {}
    skip_names: set = set()
    for i, l in added:
        m = IMPORT_RE.match(l)
        if not m:
            continue
        mod = m.group(1) or m.group(3)
        top = mod.split(".")[0]
        if top in toolkit_modules or not ((target / "scripts" / f"{top}.py").is_file() or (target / "scripts" / top).is_dir()):
            continue
        names = [n.strip().split(" as ")[-1].strip("() ") for n in m.group(2).split(",")] if m.group(2) else [m.group(4) or top]
        keys = {mod.rsplit(".", 1)[-1]} | {n for n in names if n}
        if keys & registered:
            skip_names |= set(names)
            continue
        out.append((i, l.strip()))
        for n in names:
            if n and n != "*":
                bound[n] = i
    for i, l in added:
        if IMPORT_RE.match(l):
            continue
        for n in bound:
            if n not in skip_names and re.search(rf"\b{re.escape(n)}\s*[.(]", l):
                out.append((i, l.strip()))
                break
    return sorted(set(out))


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
        self.warnings: List[str] = []

    def check_wiring(self, rel: str, dest: Path, src: Path) -> None:
        """FR-1083: before `dest` is overwritten (and backed up), warn about wiring the user added that would be lost."""
        if not ((rel.startswith("scripts/") and rel.endswith(".py")) or rel == "scripts/metadata.json"):
            return
        try:
            old = dest.read_text(encoding="utf-8")
            new = src.read_text(encoding="utf-8")
            cfg = json.loads((self.target / CONFIG).read_text(encoding="utf-8")) if (self.target / CONFIG).is_file() else {}
        except (OSError, ValueError):
            return
        registered = {str(c.get("module")).rsplit(".", 1)[-1] for c in ((cfg.get("extensions") or {}).get("checks") or [])
                      if isinstance(c, dict) and c.get("module")}
        ext_dir = self.target / "scripts" / "ext"
        if ext_dir.is_dir():
            registered |= {p.stem for p in ext_dir.glob("*.py")}
        owned = {Path(r).stem for r in list(MANAGED) + list(self.manifest.get("files", {})) if r.startswith("scripts/")}
        hits = find_dropped_wiring(rel, old, new, self.target, registered, owned)
        if not hits:
            return
        backup = f"{rel}.ebak-backup-{self.stamp}"
        for n, text in hits:
            self.warnings.append(f"WARN-WIRING  {rel}:{n or '?'}  {text}  （{backup} の行。拡張点に未登録のため、この更新で脱落します）")

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
            rel = dest_of(rel)
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
            unmodified = is_recorded(dest, old)
            if unmodified or self.force:
                if not unmodified:
                    self.check_wiring(rel, dest, src)  # FR-1083: also in --dry-run / --check (display only)
                if not unmodified and not self.dry:
                    shutil.copy2(dest, dest.with_name(dest.name + f".ebak-backup-{self.stamp}"))
                self.note("UPDATE" if unmodified else "OVERWRITE", rel)
                self.write_bytes(rel, src.read_bytes())
            else:
                self.note("KEEP-LOCAL", rel)
                self.new_hashes[rel] = old or cur

    def keep_orphans(self) -> None:
        """Files an older version installed and this version does not ship stay on disk and in the manifest
        (so that `--clean` can still find them); they are only reported."""
        shipped = {dest_of(r) for r in MANAGED}
        self.orphans = sorted(rel for rel, h in self.manifest.get("files", {}).items()
                              if rel not in shipped and (self.target / rel).is_file())
        for rel in self.orphans:
            self.new_hashes[rel] = self.manifest["files"][rel]

    def install_templates(self) -> None:
        for rel in TEMPLATES:
            if (self.target / rel).exists():
                self.note("EXISTS", rel)
            else:
                self.note("CREATE", rel)
                self.write_bytes(rel, (self.source / "tools" / "templates" / rel).read_bytes())

    def install_config(self) -> None:
        src = json.loads((self.source / CONFIG).read_text(encoding="utf-8"))
        # the source's verify.commands are this repository's own (Studio tests); a target registers its own
        src.setdefault("verify", {})["commands"] = []
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
            candidates = {dest_of(rel): (sha(self.source / rel) if (self.source / rel).exists() else None) for rel in MANAGED}
            if any((self.target / rel).exists() for rel in candidates):
                self.note("WARN", f"{MANIFEST} がないため、この版の toolkit と同じ内容のファイルだけを削除します")
        for rel, h in candidates.items():
            p = self.target / rel
            if not p.is_file():
                continue
            if self.force or (h is not None and is_recorded(p, h)):
                self.remove_path(rel)
            else:
                self.note("KEEP-LOCAL", rel)

    def remove_backups(self) -> None:
        for rel in sorted({dest_of(r) for r in MANAGED} | set(self.manifest.get("files", {})) | {CONFIG}):
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
            while BEGIN in text and END in text.split(BEGIN, 1)[1]:
                pre, rest = text.split(BEGIN, 1)
                text = pre.rstrip() + "\n\n" + rest.split(END, 1)[1].lstrip("\n")
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
        kept: List[str] = []
        in_section = False
        for l in text.splitlines():
            if l.strip() == header or l.strip().startswith(TOOLKIT_HEADER_PREFIX):
                in_section = True
                continue
            if in_section and l.strip():
                continue  # every line the toolkit appended under its header, whatever version wrote it
            in_section = False
            if l.strip() not in drop:
                kept.append(l)
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

    def clean(self) -> None:
        """--clean: delete every file the toolkit installed, whatever version and whether modified, so that the
        install that follows starts from scratch. Kept: the management data (docs/*, the ledger), /work, your code."""
        for rel in sorted(set(self.manifest.get("files", {})) | {dest_of(r) for r in MANAGED}):
            if (self.target / rel).is_file():
                self.remove_path(rel, "CLEAN")
        self.remove_backups()
        if (self.target / CONFIG).is_file():
            self.remove_path(CONFIG, "CLEAN")
        self.remove_blocks()
        self.remove_lines(".gitignore", GITIGNORE_LINES, GITIGNORE_HEADER)
        self.remove_lines(".gitattributes", GITATTR_LINES, GITATTR_HEADER)
        if (self.target / MANIFEST).is_file():
            self.remove_path(MANIFEST, "CLEAN")
        self.manifest = {"files": {}}

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


def run_data_layer(target: Path, apply: bool) -> int:
    """FR-1044/FR-1045: the only data-layer step of the installer. It calls the common entry point once
    (`rdfix.py --full [--apply]`); the check, the repair and the pass/fail all come from it (no second verify)."""
    cmd = [sys.executable, str(target / "scripts" / "rdfix.py"), "--full"] + (["--apply"] if apply else [])
    try:
        proc = subprocess.run(cmd, cwd=str(target), capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"WARN データ層の確認・修復を実行できません: {exc}")
        return 2
    for part in (proc.stdout, proc.stderr):
        if (part or "").strip():
            print(part.strip())
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
    ap.add_argument("--clean", action="store_true",
                    help="クリーンインストール: toolkit が入れたファイル（旧版のものも、変更したものも）・設定・ブロック・追記をすべて削除してから導入する"
                         "（管理データ・/work・利用者のコードとテストは残す。未 commit の変更があると止まる）")
    ap.add_argument("--uninstall", action="store_true", help="変更していない toolkit のファイルと AGENTS.md などのブロックを削除する（管理データと設定は残す）")
    ap.add_argument("--purge", action="store_true", help="--uninstall に加えて、管理データ（docs・台帳）・設定・/work・.gitignore と .gitattributes の追記・バックアップも削除する")
    ap.add_argument("--allow-non-git", action="store_true")
    ap.add_argument("--skip-verify", action="store_true", help="導入後のデータ層の検査も修復も行わない")
    ap.add_argument("--no-repair", action="store_true",
                    help="導入後のデータ層の自動修復をせず、検査と修復の計画だけを表示する（書き込まない）")
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
    if args.clean:
        if uninstalling or args.check:
            raise SystemExit("ERROR install: --clean は --uninstall・--purge・--check と同時に指定できません")
        if not (target / ".git").exists():
            raise SystemExit("ERROR install: --clean は git リポジトリでだけ使えます（消したファイルを git から戻せるようにするため）")
        st = subprocess.run(["git", "status", "--porcelain"], cwd=str(target), capture_output=True, text=True)
        if st.returncode != 0 or st.stdout.strip():
            raise SystemExit("ERROR install: --clean の前に、未 commit の変更を commit するか退避します（git status）")
    ins = Installer(source, target, dry, args.force, args.no_ci)
    version = toolkit_version(source)
    if uninstalling:
        ins.uninstall(purge=args.purge)
    else:
        if args.clean:
            ins.clean()
        if args.clean and dry:
            ins.note("INSTALL", "（削除のあとに、新規の導入と同じようにすべてを入れ直します）")
        else:
            ins.install_managed()
            ins.keep_orphans()
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
        mode = ("clean " if args.clean else "") + ("check" if args.check else ("dry-run" if args.dry_run else "install"))
    print(f"\nEnterprise App Build Kit {version}: {mode} {target}  changes={len(pending)}")
    orphans = getattr(ins, "orphans", [])
    if orphans:
        print(f"\n注意: この版が配布しないファイルが {len(orphans)} 件残っています（旧版が入れたもの）: {', '.join(orphans[:5])}"
              + (" …" if len(orphans) > 5 else "") + "\n  旧版からの移行はしません。すべて消して入れ直すには --clean を使います（先に --dry-run で確認できます）")
    if args.clean and not dry:
        print("\n注意: --clean で scripts/ebak.config.json を既定に戻しました。以前の値は `git diff scripts/ebak.config.json` で確認できます")
    if ins.warnings:
        print(f"\n警告: 利用側が足した配線のうち、拡張点（extensions.checks / scripts/ext/*.py）に未登録のものが {len(ins.warnings)} 件あり、"
              "この更新で脱落します（上書き・バックアップ・終了コードは変わりません）:" if not dry else
              f"\n警告（判定だけ・書き込みなし）: 更新すると、拡張点に未登録の配線 {len(ins.warnings)} 件が脱落します:")
        for w in ins.warnings:
            print("  " + w)
        print("  移行: 検査を scripts/ 配下のモジュールの関数 f(root, cfg)（指摘の一覧を返す）にして、"
              "scripts/ebak.config.json の extensions.checks に {\"module\": \"…\", \"function\": \"…\", \"target\": \"rdcheck\"} を足すか、"
              "scripts/ext/ に置きます。toolkit のファイルは編集しません（users-guide/04-customization.md の「検査の拡張」）。")
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
            if not args.purge:
                print("  2. 管理データ・設定・/work も消すには --purge で再実行します（先に --dry-run で確認できます）")
        return 0
    if dry:
        return 0
    preflight()
    if not args.skip_verify:
        apply = not args.no_repair
        print("\n--- データ層の確認" + ("と自動修復" if apply else "（修復の計画のみ・書き込みません）")
              + ": python scripts/rdfix.py --full" + (" --apply" if apply else "") + " ---")
        rc = run_data_layer(target, apply)
        label = "再検査" if apply else "検査"
        verdict = "合格 (PASS)" if rc == 0 else ("不合格 (FAIL)" if rc == 1 else "判定できません（修復は取り消された、または実行されませんでした）")
        print(f"データ層の{label}の合否: {verdict}")
        if rc != 0 or not apply:
            print("データ層の確認: `python scripts/rdfix.py --full`、自動修復: `python scripts/rdfix.py --full --apply`"
                  "（導入した toolkit のファイルはそのまま残ります。修復は commit していません。要求定義書は変更しません）")
        if rc == 2:
            print("取り消しの理由は上の表示を確認します。インストーラの終了コードはデータ層の結果で変わりません")
    print("\n次の手順（README.md の「インストール」「Quickstart」）:")
    print("  1. 変更を確認して commit します: git add -A && git commit -m \"Add Enterprise App Build Kit\"")
    print("  2. scripts/ebak.config.json の verify.commands に、ビルド・静的検査・テストのコマンドを登録します")
    print("  3. いつもの Copilot（既定のエージェント）に、ふだんどおり依頼します。AGENTS.md の規則に従って、")
    print("     要求定義書・カタログ・テストが同じ変更の中で更新され、push すると CI の ebak-verify が同じ検査をします")
    print("     （節目には custom agent `rd-auditor` に意味の監査を頼めます。手順: EABK-docs/06-quality-gates.md）")
    print("  4. （任意）要求・カタログ・試験を図と表で見るには、EABK Studio を起動します（読み取り専用。役割は pm / architect / swe）:")
    print("     python EABK-Studio/studio.py --check            # データ層が読めるか確認")
    print("     python EABK-Studio/studio.py --role pm          # ブラウザーが開きます。ガイド: EABK-docs/studio/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
