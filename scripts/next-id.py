#!/usr/bin/env python3
"""next-id.py - the only way to allocate IDs (plan §7.4 G-3, CHK-01/02).

Usage:
  python scripts/next-id.py FR [--count 3] [--note "..."]      # -> FR-013 (FR-014 ...)
  python scripts/next-id.py NFR-SEC | AC | Q | PARAM | G | SRC | E2E | IT
  python scripts/next-id.py --sync [--adopt] [--finalize]     # reconcile docs/id-registry.md
  python scripts/next-id.py --peek FR                          # show next ID without allocating

The next number is max(requirements definition, ID registry, the same files on the base
branch, the system-test ledger, and the allocation log shared by all worktrees) + 1.
Allocated IDs are appended to docs/id-registry.md and to <git-common-dir>/ebak-id-alloc.json,
so parallel worktrees never hand out the same ID.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

KIND_RE = re.compile(r"^(G|FR|AC|Q|PARAM|SRC|E2E|IT|NFR-[A-Z0-9]+)$")
REGISTRY_TITLE = (
    "# ID 台帳\n\n"
    "要求・受入基準・質問票・パラメータ・テストケースの ID は `scripts/next-id.py` でだけ採番します。"
    "この表は採番の記録です。手で行を足したり、番号を振ったりしないでください。\n\n"
    "状態: 採番済み（未使用）／使用中／廃止（本文に残っている）／削除済み（本文から外した。再利用禁止）／欠番（使わなかった。再利用禁止）\n\n"
    "| ID | 種別 | 状態 | 採番日時 | 採番元 | メモ |\n|---|---|---|---|---|---|\n"
)


def common_dir(root: Path) -> Optional[Path]:
    rc, out = h.git(["rev-parse", "--git-common-dir"], root)
    if rc != 0 or not out.strip():
        return None
    p = Path(out.strip())
    return (root / p).resolve() if not p.is_absolute() else p


class Lock:
    def __init__(self, path: Optional[Path]):
        self.path = path

    def __enter__(self):
        if not self.path:
            return self
        deadline = time.time() + 30
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 120:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise SystemExit(f"ERROR next-id: ロックを取得できません: {self.path}")
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self.path:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def ids_in_text(text: str, kind: str) -> List[int]:
    rx = re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(kind) + r"-(\d{3,})(?![0-9])")
    return [int(m) for m in rx.findall(text or "")]


def max_for_kind(root: Path, cfg: dict, kind: str, alloc: Dict[str, int]) -> int:
    nums: List[int] = [alloc.get(kind, 0)]
    texts: List[str] = []
    for p in h.requirement_files(root, cfg):
        texts.append(h.strip_comments(h.read_text(p)))
    reg = root / h.mf(cfg, "id_registry")
    if reg.exists():
        texts.append(h.read_text(reg))
    led = root / h.mf(cfg, "ledger")
    if led.exists():
        texts.append(h.read_text(led))
    base = cfg.get("base_branch", "main")
    for ref in (base, f"origin/{base}"):
        if not h.ref_exists(root, ref):
            continue
        for rel in (h.mf(cfg, "requirements"), h.mf(cfg, "id_registry"), h.mf(cfg, "ledger")):
            t = h.git_show(root, ref, rel)
            if t:
                texts.append(h.strip_comments(t))
        rc, out = h.git(["ls-tree", "-r", "--name-only", ref, h.mf(cfg, "requirements_dir")], root)
        if rc == 0:
            for rel in out.splitlines():
                t = h.git_show(root, ref, rel)
                if t:
                    texts.append(h.strip_comments(t))
    for t in texts:
        nums += ids_in_text(t, kind)
    if kind in ("E2E", "IT") and led.exists():
        try:
            for c in json.loads(h.read_text(led)).get("cases", []):
                m = re.match(rf"^{kind}-(\d+)$", c.get("id", ""))
                if m:
                    nums.append(int(m.group(1)))
        except json.JSONDecodeError:
            pass
    return max(nums)


def fmt(kind: str, n: int) -> str:
    return f"{kind}-{n:03d}"


def ensure_registry(path: Path) -> str:
    if path.exists():
        text = h.read_text(path)
        if "| ID |" in text:
            return text
        return text.rstrip("\n") + "\n\n" + REGISTRY_TITLE.split("\n\n", 1)[1]
    return REGISTRY_TITLE


def append_rows(path: Path, rows: List[str]) -> None:
    text = ensure_registry(path)
    if not text.endswith("\n"):
        text += "\n"
    text += "".join(r + "\n" for r in rows)
    h.write_text_atomic(path, text)


def source_label(root: Path) -> str:
    br = h.current_branch(root) or "-"
    return f"{br}@{h.head_commit(root) or '-'}"


def allocate(root: Path, cfg: dict, kind: str, count: int, note: str, dry: bool) -> List[str]:
    cd = common_dir(root)
    alloc_path = cd / "ebak-id-alloc.json" if cd else None
    with Lock(cd / "ebak-id-alloc.lock" if cd else None):
        alloc = h.read_json(alloc_path, default={}) if alloc_path else {}
        start = max_for_kind(root, cfg, kind, alloc) + 1
        ids = [fmt(kind, n) for n in range(start, start + count)]
        if dry:
            return ids
        now = h.now_iso()
        src = source_label(root)
        note = note.replace("|", "／")
        append_rows(root / h.mf(cfg, "id_registry"), [f"| {i} | {kind} | 採番済み | {now} | {src} | {note} |" for i in ids])
        if alloc_path:
            alloc[kind] = start + count - 1
            h.write_json(alloc_path, alloc)
    return ids


REUSE_FORBIDDEN = ("削除済み", "欠番")


def plan_sync(root: Path, cfg: dict, adopt: bool, finalize: bool, revive: bool = True,
              dedupe: bool = False) -> dict:
    """Compute the reconciled registry without writing it.

    Returns {"text", "exists", "changes": [(id, old, new)], "added": [id], "missing": [id],
    "reused": [id], "dups_removed": [(id, line)], "dups_conflict": [(id, line)]}.
    revive=False keeps 削除済み／欠番 rows that are used again (CHK-02) instead of marking them 使用中.
    dedupe=True removes later rows that repeat an ID with the same 採番日時 and 採番元 (merge=union artifacts).
    """
    reg_path = root / h.mf(cfg, "id_registry")
    doc = h.parse_requirements(root, cfg)
    ledger = h.load_ledger(root, cfg)
    case_ids = {c.get("id") for c in ledger.get("cases", []) if isinstance(c, dict) and c.get("id")}
    text = ensure_registry(reg_path)
    lines = text.splitlines()
    reg = h.parse_registry_text(text)
    res: dict = {"exists": reg_path.exists(), "changes": [], "added": [], "missing": [], "reused": [],
                 "dups_removed": [], "dups_conflict": []}
    seen: Dict[str, List[str]] = {}
    drop: List[int] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^\|\s*([A-Z0-9-]+)\s*\|", line)
        if not m or m.group(1) == "ID":
            continue
        id_ = m.group(1)
        cells = h.split_row(line)
        if len(cells) < 3:
            continue
        if dedupe and id_ in seen:
            if cells[3:5] == seen[id_][3:5]:
                drop.append(idx)
                res["dups_removed"].append((id_, idx + 1))
                continue
            res["dups_conflict"].append((id_, idx + 1))
        seen.setdefault(id_, cells)
        state = cells[2]
        kind = h.id_kind(id_)
        if kind in ("E2E", "IT"):
            present = id_ in case_ids
            retired = False
        else:
            present = id_ in doc.defs
            req = doc.requirements.get(id_)
            retired = bool(req and req.state == "廃止")
        new = state
        if present:
            if not revive and state in REUSE_FORBIDDEN:
                res["reused"].append(id_)
                continue
            new = "廃止" if retired else "使用中"
        elif state in ("使用中", "廃止"):
            new = "削除済み"
        elif state == "採番済み" and finalize:
            new = "欠番"
        if new != state:
            cells[2] = new
            lines[idx] = "| " + " | ".join(cells) + " |"
            res["changes"].append((id_, state, new))
    for idx in reversed(drop):
        del lines[idx]
    out = "\n".join(lines) + "\n"
    missing = [i for i in sorted(doc.defs, key=lambda x: (h.id_kind(x), h.id_num(x)))
               if i not in reg and h.id_kind(i) not in ("", "G", "SRC")]
    missing += sorted(c for c in case_ids if c not in reg)
    res["missing"] = missing
    if adopt:
        src = source_label(root)
        now = h.now_iso()
        added = []
        for id_ in missing:
            req = doc.requirements.get(id_)
            st = "廃止" if req and req.state == "廃止" else "使用中"
            added.append(f"| {id_} | {h.id_kind(id_)} | {st} | {now} | {src} | 既存の ID を取り込み |")
        out += "".join(a + "\n" for a in added)
        res["added"] = list(missing)
    res["text"] = out
    res["ids"] = list(doc.defs) + list(case_ids)
    return res


def write_sync(root: Path, cfg: dict, plan: dict) -> None:
    reg_path = root / h.mf(cfg, "id_registry")
    if plan["changes"] or plan["added"] or plan["dups_removed"] or not plan["exists"]:
        h.write_text_atomic(reg_path, plan["text"])
    cd = common_dir(root)
    if cd:
        alloc_path = cd / "ebak-id-alloc.json"
        with Lock(cd / "ebak-id-alloc.lock"):
            alloc = h.read_json(alloc_path, default={}) or {}
            for id_ in plan["ids"]:
                if not id_:
                    continue
                k = h.id_kind(id_)
                if k:
                    alloc[k] = max(alloc.get(k, 0), h.id_num(id_))
            h.write_json(alloc_path, alloc)


def sync(root: Path, cfg: dict, adopt: bool, finalize: bool) -> int:
    plan = plan_sync(root, cfg, adopt, finalize)
    for id_, old, new in plan["changes"]:
        print(f"{id_}: {old} -> {new}")
    write_sync(root, cfg, plan)
    print(f"next-id sync: changed={len(plan['changes'])} adopted={len(plan['added'])}")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", nargs="?", help="FR, NFR-<区分>, AC, Q, PARAM, G, SRC, E2E, IT")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--note", default="")
    ap.add_argument("--peek", action="store_true", help="採番せずに次の ID を表示する")
    ap.add_argument("--sync", action="store_true", help="ID 台帳の状態を要求定義書・台帳に合わせる")
    ap.add_argument("--adopt", action="store_true", help="--sync と併用。台帳にない既存の ID を取り込む")
    ap.add_argument("--finalize", action="store_true", help="--sync と併用。使わなかった採番済みを欠番にする")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    if args.sync:
        return sync(root, cfg, args.adopt, args.finalize)
    if not args.kind or not KIND_RE.match(args.kind):
        ap.error("kind は FR, NFR-<区分>（例: NFR-SEC）, AC, Q, PARAM, G, SRC, E2E, IT のどれかです")
    if args.count < 1 or args.count > 200:
        ap.error("--count は 1〜200 です")
    ids = allocate(root, cfg, args.kind, args.count, args.note, args.peek)
    print("\n".join(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
