#!/usr/bin/env python3
"""rdfix.py - repair inconsistencies between the data-layer files (the requirements definition is the source of truth).

Usage:
  python scripts/rdfix.py                         # show the plan only (dry run)
  python scripts/rdfix.py --apply                 # write the fixes, then re-check with rdcheck
  python scripts/rdfix.py --only catalog,ledger   # registry | catalog | ledger | gitignore | history
  python scripts/rdfix.py --adopt --apply         # also register IDs missing from the ID registry (CHK-01)
  python scripts/rdfix.py --json

What is fixed (derived data follows the requirements definition, which is never edited - G-1):
  registry  docs/id-registry.md     states (使用中／廃止／削除済み), duplicated rows (merge=union), missing file
                                    -> through next-id.py (G-3)
  catalog   docs/catalog.md         決定状態・題名 of the function table (CHK-07), rows for requirements that are
                                    missing, rows for unknown requirements without files, renamed / deleted
                                    file references (CHK-08), implementation files of retired requirements (CHK-17),
                                    使っている要求 ID of the common-parts table from the function table (CHK-27)
  ledger    tests/system/ledger.json  missing fields, requirement_ids, missing / orphan ac_digests
                                    -> through ledger.py with history (G-2)
  gitignore .gitignore              /work/ (CHK-23)
  history   docs/run-history.md     rows duplicated by merge=union (CHK-23)
What needs a judgment (changed AC text, reused or hand-numbered IDs, ...) is listed as MANUAL with the role
that fixes it. Output: "FIX <CHK> <loc> <msg>" / "MANUAL <CHK> <loc> <msg>（担当: role）" and one summary line.
Exit code: 0 = nothing left to fix automatically, 1 = fixes pending (dry run) or not converged, 2 = refused.

Full check / repair (FR-1046, NFR-REL-002, NFR-REL-003) - the data-layer check (rdcheck) and the repair plan in one run:
  python scripts/rdfix.py --full                  # check only: never writes, never waits for the lock
  python scripts/rdfix.py --full --apply          # check -> repair -> re-check (until converged, PARAM-026 rounds)
  python scripts/rdfix.py --full [--apply] --json # the same result as JSON (one object, fields per item)
  Exit code: 0 = pass / repaired, 1 = manual items left / repairs planned / not converged,
             2 = not run or cancelled (worker branch, lock wait timeout, everything undone, internal error).
  Safety of --full --apply: one repair at a time per repository (lock file work/.ebak/rdfix.lock with the PID;
  waits up to PARAM-027 seconds, a lock left by a dead process is taken over); every write is a temp file + os.replace;
  the requirements definition and docs/integrations.md are compared byte-for-byte before / after; a write failure,
  a new check error or an internal error undoes every change (the files are byte-identical to before the repair).
  Remaining MANUAL lines carry the CHK-ID, file:line, the role in charge and the next action.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import socket
import stat
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402


def _strip_dot_slash(p: str) -> str:
    """先頭の './' の繰り返しだけを除く（lstrip("./") は '.github/...' の先頭の '.' も落とす）。"""
    while p.startswith("./"):
        p = p[2:]
    return p

TARGETS = ("registry", "catalog", "ledger", "gitignore", "history")
CATALOG_TEMPLATE = (
    "# カタログ\n\n"
    "既存の機能・API・テーブル・共通部品の対応表です。1 行 1 項目の短い表にし、詳細はリンク先のファイルに任せます。\n"
    "機能の表は rd-author（要求 ID・題名・決定状態）と implementer（実装ファイル・テスト・共通部品）が更新します。\n"
    "未実装の要求は、実装ファイルとテストの欄を「未実装」とします。\n\n"
    "## 機能\n\n"
    "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n"
    "|---|---|---|---|---|---|\n"
)
CATALOG_STATES = ("承認済み", "承認待ち", "保留")
GITIGNORE_HEADER = "# Enterprise App Build Kit: temporary run files (kept 14 days)"


@dataclass
class Action:
    kind: str  # FIX | MANUAL
    chk: str
    loc: str
    msg: str
    owner: str = ""
    target: str = ""

    def line(self) -> str:
        tail = f"（担当: {self.owner}）" if self.kind == "MANUAL" and self.owner else ""
        return f"{self.kind} {self.chk} {self.loc} {self.msg}{tail}"


class LineEdits:
    """Line-based edits that keep the rest of a file byte-for-byte."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.trailing_nl = text.endswith("\n") or not text
        self.replace: Dict[int, Optional[str]] = {}
        self.insert: Dict[int, List[str]] = {}

    def set(self, idx: int, line: Optional[str]) -> None:
        self.replace[idx] = line

    def add_after(self, idx: int, line: str) -> None:
        self.insert.setdefault(idx, []).append(line)

    @property
    def dirty(self) -> bool:
        return bool(self.replace or self.insert)

    def text(self) -> str:
        out: List[str] = []
        for i, line in enumerate(self.lines):
            new = self.replace.get(i, line)
            if new is not None:
                out.append(new)
            out.extend(self.insert.get(i, []))
        if -1 in self.insert:
            out = self.insert[-1] + out
        return "\n".join(out) + ("\n" if self.trailing_nl else "")


def row_line(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


class Fixer:
    def __init__(self, root: Path, cfg: dict, adopt: bool, only: Set[str], doc=None):
        self.root, self.cfg, self.adopt, self.only = root, cfg, adopt, only
        self.doc = doc if doc is not None else h.parse_requirements(root, cfg)
        self.actions: List[Action] = []
        self.writers: List = []
        self._files: Optional[List[str]] = None
        self._file_set: Set[str] = set()
        self._id_index: Optional[Dict[str, Tuple[Set[str], Set[str]]]] = None
        self._renames: Optional[Dict[str, str]] = None

    # ------------------------------------------------------------------ helpers
    def act(self, kind: str, chk: str, loc: str, msg: str, owner: str, target: str) -> None:
        self.actions.append(Action(kind, chk, loc, msg, owner, target))

    def git_ls_files(self):
        # NFR-PERF-003 AC-089: 同一引数の git ls-files は 1 回だけ起動する
        if getattr(self, "_ls_cache", None) is None:
            self._ls_cache = h.git(["ls-files"], self.root)
        return self._ls_cache

    def files(self) -> List[str]:
        if self._files is None:
            self._files = h.tracked_files(self.root)
            self._file_set = set(self._files)
        return self._files

    def exists(self, p: str) -> bool:
        rel = _strip_dot_slash(p)
        self.files()
        return rel in self._file_set or (self.root / rel).exists()

    def id_index(self) -> Dict[str, Tuple[Set[str], Set[str]]]:
        """ID -> (implementation files, test files) that mention it (same scope as rdcheck CHK-09/17/19)."""
        if self._id_index is None:
            ex = self.cfg["checks"]["id_scan_exclude"] + [h.mf(self.cfg, "ledger")]
            trx = re.compile(self.cfg["checks"]["test_path_pattern"])
            idx: Dict[str, Tuple[Set[str], Set[str]]] = {}
            for f in self.files():
                if h.glob_match(f, ex):
                    continue
                p = self.root / f
                try:
                    if p.stat().st_size > 2_000_000:
                        continue
                    data = p.read_bytes()
                except OSError:
                    continue
                if b"\0" in data[:4096]:
                    continue
                for id_ in set(h.CODE_ID_RE.findall(data.decode("utf-8", "replace"))):
                    impl, tests = idx.setdefault(id_, (set(), set()))
                    (tests if trx.search(f) else impl).add(f)
            self._id_index = idx
        return self._id_index

    def files_for(self, rid: str) -> Tuple[List[str], List[str]]:
        req = self.doc.requirements.get(rid)
        impl: Set[str] = set()
        tests: Set[str] = set()
        for id_ in [rid] + (req.acs if req else []):
            i, t = self.id_index().get(id_, (set(), set()))
            impl |= i
            tests |= t
        return sorted(impl), sorted(tests)

    def renames(self) -> Dict[str, str]:
        if self._renames is None:
            self._renames = {}
            rc, out = h.git(["log", "--diff-filter=R", "-M", "--name-status", "--format="], self.root)
            if rc == 0:
                # git log is newest first; keep the most recent rename of each path
                for line in out.splitlines():
                    parts = line.split("\t")
                    if len(parts) == 3 and parts[0].startswith("R"):
                        self._renames.setdefault(parts[1], parts[2])
        return self._renames

    def follow(self, p: str) -> Optional[str]:
        cur, seen = _strip_dot_slash(p), set()
        while cur in self.renames() and cur not in seen:
            seen.add(cur)
            cur = self.renames()[cur]
            if self.exists(cur):
                return cur
        return None

    # ------------------------------------------------------------------ run
    def plan(self) -> List[Action]:
        for name in TARGETS:
            if name in self.only:
                getattr(self, f"fix_{name}")()
        return self.actions

    def apply(self) -> None:
        for w in self.writers:
            w()

    # ------------------------------------------------------------------ registry
    def fix_registry(self) -> None:
        if not self.doc.exists:
            return
        reg = h.mf(self.cfg, "id_registry")
        nid = h.load_script("next-id")
        exists = (self.root / reg).exists()
        plan = nid.plan_sync(self.root, self.cfg, adopt=self.adopt or not exists, finalize=False,
                             revive=False, dedupe=True)
        t = "registry"
        if not exists:
            self.act("FIX", "CHK-01", reg, f"ID 台帳がありません。既存の ID {len(plan['added'])} 件を取り込んで作成します", "", t)
        else:
            for id_ in plan["added"]:
                self.act("FIX", "CHK-01", reg, f"{id_} を ID 台帳に取り込みます（--adopt）", "", t)
            if not self.adopt:
                for id_ in plan["missing"]:
                    self.act("MANUAL", "CHK-01", reg,
                             f"{id_} が ID 台帳にありません。手で振った ID なら next-id.py で採番し直します。"
                             "正しい ID と確認できたら `rdfix.py --adopt --apply` で取り込みます", "rd-author", t)
        for id_, old, new in plan["changes"]:
            self.act("FIX", "CHK-01", reg, f"{id_} の状態を {old} → {new} に直します", "", t)
        for id_, ln in plan["dups_removed"]:
            self.act("FIX", "CHK-01", f"{reg}:{ln}", f"{id_} の重複した行（merge=union の名残り）を取り除きます", "", t)
        for id_, ln in plan["dups_conflict"]:
            self.act("MANUAL", "CHK-01", f"{reg}:{ln}",
                     f"{id_} が二重に採番されています（採番日時・採番元が違う）。後から使った側を next-id.py で採番し直します", "rd-author", t)
        for id_ in plan["reused"]:
            d = self.doc.defs.get(id_, [None])[0]
            loc = f"{d.file}:{d.line}" if d else reg
            self.act("MANUAL", "CHK-02", loc,
                     f"{id_} は ID 台帳で削除済み／欠番です。廃止・削除した ID は再利用せず、next-id.py で採番し直します", "rd-author", t)
        if plan["changes"] or plan["added"] or plan["dups_removed"] or not exists:
            self.writers.append(lambda: nid.write_sync(self.root, self.cfg, plan))

    # ------------------------------------------------------------------ catalog
    def fix_catalog(self) -> None:
        if not self.doc.exists:
            return
        cat = h.mf(self.cfg, "catalog")
        path = self.root / cat
        t = "catalog"
        created = not path.exists()
        text = CATALOG_TEMPLATE if created else h.read_text(path)
        if created:
            self.act("FIX", "CHK-07", cat, "カタログがありません。雛形から作成します", "", t)
        ed = LineEdits(text)
        tables = h.parse_tables(h.strip_comments(text).splitlines())
        func = [tb for tb in tables if tb.col("要求 ID", "要求ID") is not None and tb.col("決定状態") is not None]
        if not func:
            self.act("MANUAL", "CHK-07", cat, "カタログに機能の表（要求 ID・決定状態の列）がありません", "rd-author", t)
        seen: Dict[str, List[str]] = {}
        used_by: Dict[str, Set[str]] = {}
        part_names: Set[str] = set()
        for tb in tables:
            kind = h.catalog_table_kind(tb)
            pc, nc = tb.col("共通部品"), tb.col("部品名")
            idc0 = tb.col("要求 ID", "要求ID")
            for _, cells in tb.rows:
                if kind == "feature" and pc is not None and idc0 is not None and pc < len(cells):
                    m = h.REQ_ID_RE.search(cells[idc0])
                    if m and m.group(1) in self.doc.requirements:
                        for p in h.split_values(cells[pc]):
                            used_by.setdefault(p, set()).add(m.group(1))
                elif kind == "part" and nc is not None and nc < len(cells):
                    part_names.add(h.strip_md(cells[nc]))
        for p in sorted(set(used_by) - part_names):
            self.act("MANUAL", "CHK-27", cat, f"機能の表が使っている共通部品「{p}」が共通部品の表にありません。行を追加します（{'、'.join(sorted(used_by[p]))}）", "implementer", t)
        for tb in tables:
            is_func = any(tb is f for f in func)
            is_part = h.catalog_table_kind(tb) == "part"
            pnc, puc = tb.col("部品名"), tb.col("要求 ID", "要求ID")
            file_cols = [i for i, hd in enumerate(tb.header) if re.search(r"ファイル|テスト", hd)]
            idc, tc, sc = tb.col("要求 ID", "要求ID"), tb.col("題名"), tb.col("決定状態")
            ic = tb.col("実装ファイル")
            for ln, cells in tb.rows:
                cells = cells + [""] * (len(tb.header) - len(cells))
                orig = list(cells)
                loc = f"{cat}:{ln}"
                if is_func and idc is not None:
                    m = h.REQ_ID_RE.search(cells[idc])
                    if m:
                        rid = m.group(1)
                        req = self.doc.requirements.get(rid)
                        has_files = any(h.split_paths(cells[c]) for c in file_cols)
                        if rid in seen:
                            if [h.strip_md(c) for c in cells] == seen[rid]:
                                ed.set(ln - 1, None)
                                self.act("FIX", "CHK-07", loc, f"{rid} の重複した行を取り除きます", "", t)
                            else:
                                self.act("MANUAL", "CHK-07", loc, f"{rid} の行が複数あり、内容が違います。1 行にまとめます", "rd-author", t)
                            continue
                        seen[rid] = [h.strip_md(c) for c in cells]
                        if req is None:
                            if has_files:
                                self.act("MANUAL", "CHK-07", loc,
                                         f"要求定義書にない {rid} の行に実装ファイル・テストがあります。要求を戻すか、実装を取り除いて行を消します",
                                         "rd-author", t)
                            else:
                                ed.set(ln - 1, None)
                                self.act("FIX", "CHK-07", loc, f"要求定義書にない {rid} の行を取り除きます（実装ファイル・テストの記載なし）", "", t)
                            continue
                        if sc is not None and req.state and h.normalize_state(cells[sc]) != req.state:
                            self.act("FIX", "CHK-07", loc,
                                     f"{rid} の決定状態を {h.strip_md(cells[sc]) or '空'} → {req.state} に直します（要求定義書に合わせる）", "", t)
                            cells[sc] = req.state
                        if tc is not None and req.title and h.strip_md(cells[tc]) != req.title:
                            self.act("FIX", "CHK-07", loc, f"{rid} の題名を「{h.strip_md(cells[tc])}」→「{req.title}」に直します", "", t)
                            cells[tc] = req.title
                        if ic is not None and req.state == "廃止" and h.split_paths(cells[ic]):
                            impl, tests = self.files_for(rid)
                            if not impl and not tests:
                                self.act("FIX", "CHK-17", loc, f"廃止の {rid} のコードはもうないので、実装ファイルの欄を「なし」にします", "", t)
                                cells[ic] = "なし"
                for c in file_cols:
                    cells[c] = self._fix_paths(cells[c], loc, "未実装" if is_func else "-", t)
                if is_part and pnc is not None and puc is not None:
                    name = h.strip_md(cells[pnc])
                    if name and name not in h.NONE_VALUES:
                        want = sorted(used_by.get(name, set()))
                        if sorted(set(h.REQ_ID_RE.findall(cells[puc]))) != want:
                            new = "、".join(want) or "なし"
                            self.act("FIX", "CHK-27", loc, f"共通部品「{name}」の使っている要求 ID を「{h.strip_md(cells[puc]) or '空'}」→「{new}」に直します（機能の表に合わせる）", "", t)
                            cells[puc] = new
                if cells != orig:
                    ed.set(ln - 1, row_line(cells))
        if func:
            tb = func[0]
            after = (tb.rows[-1][0] - 1) if tb.rows else tb.header_line  # 0-based index of the last table line
            for rid, req in self.doc.requirements.items():
                if rid in seen or req.state not in CATALOG_STATES:
                    continue
                impl, tests = self.files_for(rid)
                vals = {"要求ID": rid, "題名": req.title or "-", "決定状態": req.state,
                        "実装ファイル": ", ".join(impl) or "未実装", "テスト": ", ".join(tests) or "未実装"}
                cells = []
                for hd in tb.header:
                    hn = hd.replace(" ", "")
                    cells.append(next((v for k, v in vals.items() if k in hn), "-"))
                ed.add_after(after, row_line(cells))
                self.act("FIX", "CHK-07", cat, f"{rid}（{req.state}）の行がないので追加します"
                         + (f"（コード・テストの参照から: {', '.join(impl + tests)}）" if impl or tests else ""), "", t)
        if ed.dirty or created:
            self.writers.append(lambda: h.write_text_atomic(path, ed.text()))

    def _fix_paths(self, cell: str, loc: str, empty: str, t: str) -> str:
        paths = h.split_paths(cell)
        missing = [p for p in paths if not self.exists(p)]
        if not missing:
            return cell
        moved = {p: self.follow(p) for p in missing}
        for p, dst in moved.items():
            if dst:
                self.act("FIX", "CHK-08", loc, f"カタログのファイル {p} は {dst} に名前が変わっています。参照を直します", "", t)
            else:
                self.act("FIX", "CHK-08", loc, f"カタログのファイル {p} が存在しないので、参照を取り除きます", "", t)
        if all(moved.values()):
            for p, dst in moved.items():
                cell = re.sub(r"(?<![\w./-])" + re.escape(p) + r"(?![\w-])", dst, cell)
            return cell
        keep: List[str] = []
        for p in paths:
            q = moved[p] if p in moved else p
            if q and q not in keep:
                keep.append(q)
        return ", ".join(keep) or empty

    # ------------------------------------------------------------------ ledger
    def fix_ledger(self) -> None:
        ledger = h.load_script("ledger")
        for a in ledger.repair(self.root, self.cfg, self.doc, apply=False):
            self.act(a["kind"], a["chk"], a["loc"], a["msg"], a["owner"], "ledger")
        if any(a.kind == "FIX" and a.target == "ledger" for a in self.actions):
            self.writers.append(lambda: ledger.repair(self.root, self.cfg, h.parse_requirements(self.root, self.cfg), apply=True))

    # ------------------------------------------------------------------ .gitignore
    def fix_gitignore(self) -> None:
        wd = self.cfg["work"]["dir"]
        rx = re.compile(self.cfg["checks"]["temp_file_pattern"])
        rc, out = self.git_ls_files()
        for f in (out.splitlines() if rc == 0 else []):
            if (f.startswith("docs/") or f.startswith("tests/")) and rx.search(f):
                self.act("MANUAL", "CHK-23", f, f"一時ファイルが commit されています。/{wd}/runs/<run-id>/ へ移し `git rm --cached` します",
                         "conductor", "gitignore")
        gi = self.root / ".gitignore"
        lines = h.read_text(gi).splitlines() if gi.exists() else []
        if any(re.fullmatch(rf"/?{re.escape(wd)}/?\*{{0,2}}", l.strip()) for l in lines):
            return
        self.act("FIX", "CHK-23", ".gitignore", f"/{wd}/ を追加します（一時ファイルを git の管理対象外にする）", "", "gitignore")

        def write() -> None:
            text = h.read_text(gi) if gi.exists() else ""
            if text and not text.endswith("\n"):
                text += "\n"
            h.write_text_atomic(gi, text + ("\n" if text else "") + f"{GITIGNORE_HEADER}\n/{wd}/\n")
        self.writers.append(write)

    # ------------------------------------------------------------------ run history
    def fix_history(self) -> None:
        rel = h.mf(self.cfg, "run_history")
        path = self.root / rel
        if not path.exists():
            return
        text = h.read_text(path)
        ed = LineEdits(text)
        lines = ed.lines
        for tb in h.parse_tables(h.strip_comments(text).splitlines()):
            c = tb.col("run-id", "run_id")
            if c is None:
                continue
            seen: Dict[str, int] = {}
            for ln, cells in tb.rows:
                rid = h.strip_md(cells[c]) if c < len(cells) else ""
                if not rid:
                    continue
                if rid in seen:
                    if lines[ln - 1].strip() == lines[seen[rid] - 1].strip():
                        ed.set(ln - 1, None)
                        self.act("FIX", "CHK-23", f"{rel}:{ln}", f"run-id {rid} の重複した行（merge=union の名残り）を取り除きます", "", "history")
                    else:
                        self.act("MANUAL", "CHK-23", f"{rel}:{ln}", f"run-id {rid} の行が {seen[rid]} 行目と内容が違います。正しい 1 行を残します", "conductor", "history")
                    continue
                seen[rid] = ln
        if ed.dirty:
            self.writers.append(lambda: h.write_text_atomic(path, ed.text()))


# ---------------------------------------------------------------------- entry points

def count_fixable(root: Path, cfg: dict) -> int:
    """Number of automatic fixes available (used by verify.py for a hint). Never writes."""
    return sum(1 for a in Fixer(root, cfg, False, set(TARGETS)).plan() if a.kind == "FIX")


def is_work_branch(root: Path) -> bool:
    return bool(re.match(r"^work/[^/]+/[^/]+$", h.current_branch(root)))


def rdcheck_summary(root: Path) -> Tuple[int, List[str]]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = h.load_script("rdcheck").main(["--root", str(root), "check", "--errors-only"])
    return rc, buf.getvalue().strip().splitlines()


# ---------------------------------------------------------------------- full check / repair (FR-1046)
# FR-1046 AC-240〜243, NFR-REL-002 AC-244〜247, NFR-REL-003 AC-248〜250

MAX_ROUNDS = 3        # PARAM-026: 検査→修復の繰り返しの上限（scripts/ebak.config.json の repair.max_rounds で変更）
LOCK_WAIT_SEC = 30.0  # PARAM-027: 同時に起動された修復の排他の待ち時間の上限（repair.lock_wait_sec / --lock-wait）
TMP_PREFIX = ".rdfix-tmp-"
LOCK_REGION = 1 << 30  # Windows でロックするバイトの位置（PID の記録より後ろ。記録は他のプロセスから読める）
LOC_LINE_RE = re.compile(r"^(.+?):(\d+)$")
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9\-])((?:[A-Z][A-Z0-9]*-)+\d{3,})(?![0-9])")
NAME_RE = re.compile(r"[「『]([^」』]+)[」』]")
ROLES = ("rd-author", "test-designer", "implementer", "conductor")
ROLE_ACTION = {
    "rd-author": "conductor が rd-author に依頼して要求定義書・カタログ・ID 台帳を直し、`python scripts/rdfix.py --full` で確かめます",
    "test-designer": "conductor が test-designer に依頼して System Test の台帳を直し（`ledger.py update`・`block`・`digests --update`）、"
                     "`python scripts/rdfix.py --full` で確かめます",
    "implementer": "conductor が implementer に依頼してカタログの実装ファイル・テスト・共通部品を直し、`python scripts/rdfix.py --full` で確かめます",
    "conductor": "conductor が統合ブランチで直し、`python scripts/rdfix.py --full` で確かめます",
}
CHK_OWNER = {"CHK-08": "implementer", "CHK-09": "implementer", "CHK-17": "implementer", "CHK-19": "implementer",
             "CHK-27": "implementer", "CHK-10": "test-designer", "CHK-11": "test-designer", "CHK-12": "test-designer",
             "CHK-21": "conductor", "CHK-23": "conductor"}
CHK_HINT = {
    "CHK-00": "要求定義書を作成します",
    "CHK-01": "`next-id.py` で採番し直します（正しい ID と確認できたら `rdfix.py --full --apply --adopt` で取り込みます）",
    "CHK-02": "削除済み・欠番の ID は再利用せず、`next-id.py` で新しい ID を採番します",
    "CHK-03": "AC を要求の見出しの下に書くか、`対応する要求:` を付けます",
    "CHK-04": "上位の欄を存在する G-ID に直します",
    "CHK-05": "AC を追加するか、Q を挙げます",
    "CHK-06": "決定状態を `承認済み（依頼 YYYY-MM-DD）` の形にします",
    "CHK-07": "カタログの機能の表を要求定義書に合わせます",
    "CHK-08": "カタログのパスを直すか「未実装」にします",
    "CHK-09": "テスト名かコメントに要求 ID と AC ID を書きます",
    "CHK-10": "台帳にケースを追加するか、対象外になった AC のケースを `ledger.py block` します",
    "CHK-11": "ケースを見直してから `ledger.py digests --update` を実行します",
    "CHK-12": "台帳・tests/system の変更を元に戻し、変更は `ledger.py update --reason` で行います",
    "CHK-16": "PARAM の表に追加します",
    "CHK-17": "廃止した要求のコード・テスト・カタログの行を取り除きます",
    "CHK-18": "ブロックの原因を書くか、回答を反映して BLOCKED を外します",
    "CHK-19": "コード・テストの ID を直します（廃止した ID の残骸は削除します）",
    "CHK-20": "要求定義書の形式（構造化欄・検証レベル・決定状態）に合わせます",
    "CHK-21": "統合をやり直します",
    "CHK-22": "決定記録の根拠（依頼・Q・承認依頼・包括承認）を直します",
    "CHK-23": "`.gitignore` に `/work/` を足し、一時ファイルを /work に移します。重複した run-id は正しい 1 行を残します",
    "CHK-24": "ID を直すか、参照先を定義します",
    "CHK-25": "用語・状態の表に定義するか、構造化欄を直します",
    "CHK-27": "カタログの表に行を足すか、表どうしを一致させます",
    "CHK-28": "外部連携カタログの項目を直します",
}


def _cfg_number(cfg: dict, key: str, default: float, minimum: float) -> float:
    try:
        v = float((cfg.get("repair") or {}).get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default
    return v if v >= minimum else default


def _file_of(loc: str) -> str:
    m = LOC_LINE_RE.match(loc)
    return m.group(1) if m else loc


def _err_key(e) -> Tuple[str, str, str]:
    """Identity of a check error that survives line shifts caused by the repair itself."""
    return e.chk, _file_of(e.loc), re.sub(r"\d+\s*行目", "#行目", e.msg)


@dataclass
class Item:
    """One reported item of --full (FIX / MANUAL / ERROR) with the fields of AC-242."""
    kind: str
    chk: str
    loc: str
    msg: str
    owner: str = ""
    target: str = ""
    file: str = ""
    line: int = 0
    action: str = ""
    source: str = "rdfix"

    def text(self) -> str:
        if self.kind == "MANUAL":
            return f"MANUAL {self.chk} {self.loc} {self.msg}（担当: {self.owner}）次の行動: {self.action}"
        return f"{self.kind} {self.chk} {self.loc} {self.msg}"


class Locator:
    """file:line for items whose location names only a file (AC-242)."""

    def __init__(self, root: Path, doc):
        self.root, self.doc = root, doc
        self._lines: Dict[str, List[str]] = {}

    def lines(self, rel: str) -> List[str]:
        if rel not in self._lines:
            try:
                self._lines[rel] = (self.root / rel).read_bytes().decode("utf-8", "replace").splitlines()
            except OSError:
                self._lines[rel] = []
        return self._lines[rel]

    def __call__(self, loc: str, msg: str) -> Tuple[str, int]:
        m = LOC_LINE_RE.match(loc)
        if m:
            return m.group(1), int(m.group(2))
        rel = loc.strip() or "."
        tokens = TOKEN_RE.findall(msg)
        for needle in tokens + NAME_RE.findall(msg):
            rx = re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(needle) + r"(?![A-Za-z0-9])")
            for i, text in enumerate(self.lines(rel), 1):
                if rx.search(text):
                    return rel, i
        for tok in tokens:  # an ID that is missing from the file: point at its definition
            d = (self.doc.defs.get(tok) or [None])[0] if self.doc is not None else None
            if d is not None:
                return d.file, d.line
        return rel, 1


def manual_item(src, loc_of: Locator, source: str) -> Item:
    file, line = loc_of(src.loc, src.msg)
    if source == "rdfix":
        owner = src.owner if src.owner in ROLES else "conductor"
        action = ROLE_ACTION[owner]
        target = src.target
    else:
        owner = CHK_OWNER.get(src.chk, "rd-author")
        action = CHK_HINT.get(src.chk, "検査の指摘に従って直します") + "。" + ROLE_ACTION[owner]
        target = ""
    return Item("MANUAL", src.chk, f"{file}:{line}", src.msg, owner, target, file, line, action, source)


@dataclass
class Inspection:
    fixer: "Fixer"
    actions: List[Action]
    errors: list  # rdcheck Finding (ERROR level only)

    @property
    def fixes(self) -> List[Action]:
        return [a for a in self.actions if a.kind == "FIX"]

    @property
    def manual(self) -> List[Action]:
        return [a for a in self.actions if a.kind == "MANUAL"]

    def uncovered(self) -> list:
        """Check errors that no FIX / MANUAL action already reports (same CHK at the same place)."""
        out = []
        for e in self.errors:
            if not any(a.chk == e.chk and (a.loc == e.loc or (_file_of(a.loc) == _file_of(e.loc) and not LOC_LINE_RE.match(a.loc)))
                       for a in self.actions):
                out.append(e)
        return out


def inspect(root: Path, cfg: dict, adopt: bool, only: Set[str]) -> Inspection:
    """One data-layer inspection: rdcheck (same as `verify.py --docs-only`) and the repair plan, sharing one parse."""
    rdc = h.load_script("rdcheck")
    ck = rdc.Checker(root, cfg, h.default_base(root, cfg), None, False, None)
    errors = [f for f in ck.run_all() if f.level == "ERROR"]
    fx = Fixer(root, cfg, adopt, only, doc=ck.doc)
    if getattr(ck, "_files", None) is not None:
        fx._files, fx._file_set = ck._files, set(ck._files)
    if getattr(ck, "_ls_cache", None) is not None:
        fx._ls_cache = ck._ls_cache
    return Inspection(fx, fx.plan(), errors)


# -------------------------------------------------------------- atomic writes and undo (NFR-REL-002)

def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Temp file in the same directory + fsync + os.replace: the target is either the old or the new complete content.
    The temp file never outlives a failure; the target keeps its permission bits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        mode = None
    fd, tmp = tempfile.mkstemp(prefix=f"{TMP_PREFIX}{os.getpid()}-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None and os.name != "nt":
            os.chmod(tmp, mode)
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                # Windows: a reader (indexer, antivirus, editor) can hold the target for a moment
                if os.name != "nt" or attempt == 3 or (mode is not None and not mode & stat.S_IWRITE):
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Cancel(Exception):
    """A reason to undo every change of this apply (exit 2)."""

    def __init__(self, reason: str, new_errors: Optional[list] = None):
        super().__init__(reason)
        self.reason = reason
        self.new_errors = new_errors or []


def protected_paths(root: Path, cfg: dict) -> List[Path]:
    """The requirements definition (index + split files) and the integration catalog: never changed by a repair."""
    out = [root / h.mf(cfg, "requirements")]
    split_dir = root / h.mf(cfg, "requirements_dir")
    if split_dir.is_dir():
        out += sorted(p for p in split_dir.rglob("*") if p.is_file())
    out.append(root / (cfg["management_files"].get("integrations") or "docs/integrations.md"))
    return out


def data_layer_paths(root: Path, cfg: dict) -> List[Path]:
    rels = [v for k, v in cfg["management_files"].items() if k != "requirements_dir" and isinstance(v, str) and v]
    out: List[Path] = []
    for p in [root / r for r in rels] + [root / ".gitignore"] + protected_paths(root, cfg):
        if p not in out:
            out.append(p)
    return out


def _read(p: Path) -> Optional[bytes]:
    try:
        return p.read_bytes()
    except FileNotFoundError:
        return None


class Transaction:
    """Undo log of one apply: the bytes (and times) of every data-layer file before the first write,
    plus every file written through ebaklib.write_text_atomic while capturing."""

    def __init__(self, root: Path, cfg: dict):
        self.root, self.cfg = root, cfg
        self.root_abs = os.path.abspath(str(root))
        self.orig: Dict[str, Optional[Tuple[bytes, int, int]]] = {}
        self.written: List[str] = []
        self._orig_write = h.write_text_atomic
        for p in data_layer_paths(root, cfg):
            self.remember(p)
        self.protected_before = self.protected_state()

    def key(self, p) -> str:
        return os.path.abspath(str(p))

    def remember(self, p) -> None:
        k = self.key(p)
        if k in self.orig:
            return
        try:
            st = os.stat(k)
            with open(k, "rb") as fh:
                self.orig[k] = (fh.read(), st.st_atime_ns, st.st_mtime_ns)
        except FileNotFoundError:
            self.orig[k] = None

    def inside(self, p) -> bool:
        try:
            rel = os.path.relpath(self.key(p), self.root_abs)
        except ValueError:  # another drive (Windows)
            return False
        parts = Path(rel).parts
        return bool(parts) and parts[0] not in ("..", ".git")

    def write(self, path, text: str) -> None:
        """Replacement of ebaklib.write_text_atomic while capturing."""
        if not self.inside(path):
            return self._orig_write(path, text)
        self.remember(path)
        k = self.key(path)
        if k not in self.written:
            self.written.append(k)
        atomic_write_bytes(Path(k), text.encode("utf-8"))

    @contextlib.contextmanager
    def capture(self):
        h.write_text_atomic = self.write
        try:
            yield self
        finally:
            h.write_text_atomic = self._orig_write

    def protected_state(self) -> Dict[str, Optional[bytes]]:
        return {self.key(p): _read(p) for p in protected_paths(self.root, self.cfg)}

    def protected_changed(self) -> List[str]:
        now = self.protected_state()
        keys = set(now) | set(self.protected_before)
        return sorted(self.rel(k) for k in keys if now.get(k) != self.protected_before.get(k))

    def rel(self, k: str) -> str:
        try:
            return Path(os.path.relpath(k, self.root_abs)).as_posix()
        except ValueError:
            return k

    def changed(self) -> List[str]:
        return sorted(self.rel(k) for k, o in self.orig.items() if _read(Path(k)) != (o[0] if o else None))

    def rollback(self) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Restore every file to its bytes (and times) before the repair. Returns (restored, failed)."""
        for k in self.protected_state():  # files that appeared under the protected paths during the repair
            self.orig.setdefault(k, None)
        restored: List[str] = []
        failed: List[Tuple[str, str]] = []
        for k, o in self.orig.items():
            p = Path(k)
            cur = _read(p)
            want = o[0] if o else None
            try:
                if cur != want:
                    if want is None:
                        p.unlink()
                    else:
                        atomic_write_bytes(p, want)
                    restored.append(self.rel(k))
                if o and o[2]:
                    st = p.stat()
                    if st.st_mtime_ns != o[2]:
                        os.utime(k, ns=(o[1], o[2]))
            except OSError as exc:
                failed.append((self.rel(k), f"{type(exc).__name__}: {exc}"))
        if failed:
            self.backup([k for k, _ in failed])
        return restored, failed

    def backup(self, rels: List[str]) -> Optional[Path]:
        """Keep the pre-repair bytes of files that could not be restored under work/.ebak/ (never lose them)."""
        try:
            d = h.work_dir(self.root, self.cfg) / ".ebak" / f"rdfix-undo-{time.strftime('%Y%m%d-%H%M%S')}"
            for rel in rels:
                o = self.orig.get(self.key(self.root / rel))
                if o:
                    dst = d / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(o[0])
            self.backup_dir = d
            return d
        except OSError:
            return None


def sweep_temp(root: Path, cfg: dict) -> int:
    """Temp files left by a repair that was killed while writing (only the lock holder calls this)."""
    n = 0
    for d in sorted({p.parent for p in data_layer_paths(root, cfg)}):
        if not d.is_dir():
            continue
        for p in d.glob(TMP_PREFIX + "*"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


# -------------------------------------------------------------- one repair at a time (NFR-REL-003 AC-250)

def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        hp = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(hp, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(hp)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def lock_path(root: Path, cfg: dict) -> Path:
    return h.work_dir(root, cfg) / ".ebak" / "rdfix.lock"


class RepairLock:
    """Exclusive lock of the repository's data-layer repair.

    The operating system's file lock (fcntl.flock / msvcrt.locking) decides who holds it, so a holder that died
    can never block the next repair; the lock file records the holder's PID, host and start time. A record that is
    still there when the lock is free was left by a repair that ended abnormally; it is taken over after checking
    that the process no longer exists (the record is cleared on a normal release, the file itself is kept so that
    two waiters can never hold two different files)."""

    def __init__(self, path: Path):
        self.path = path
        self.fd: Optional[int] = None
        self.held = False

    def _try(self) -> bool:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, LOCK_REGION, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def record(self) -> dict:
        try:
            raw = self.path.read_bytes()
            data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def acquire(self, wait: float, notify: Callable[[str], None]) -> Tuple[bool, dict]:
        """(True, previous record) when acquired; (False, holder record) after `wait` seconds."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
        deadline = time.monotonic() + max(0.0, wait)
        announced = False
        while not self._try():
            holder = self.record()
            if not announced:
                notify(f"INFO rdfix: 別の修復（PID {holder.get('pid', '?')}、{holder.get('started', '?')} 開始）が実行中です。"
                       f"最大 {wait:g} 秒待ちます（PARAM-027）")
                announced = True
            left = deadline - time.monotonic()
            if left <= 0:
                os.close(self.fd)
                self.fd = None
                return False, holder
            time.sleep(min(0.1, left))
        prev = self.record()
        self.held = True
        info = {"pid": os.getpid(), "host": socket.gethostname(), "started": h.now_iso(),
                "command": "rdfix.py --full --apply"}
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.ftruncate(self.fd, 0)
        os.write(self.fd, json.dumps(info, ensure_ascii=False).encode("utf-8"))
        return True, prev

    def release(self) -> None:
        if self.fd is None:
            return
        if not getattr(self, "held", False):  # interrupted while waiting: the record belongs to the holder
            os.close(self.fd)
            self.fd = None
            return
        self.held = False
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            os.ftruncate(self.fd, 0)
        except OSError:
            pass
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, LOCK_REGION, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None


# -------------------------------------------------------------- report

class FullReport:
    def __init__(self, as_json: bool, apply: bool):
        self.as_json, self.apply = as_json, apply
        self.infos: List[str] = []

    def info(self, line: str) -> None:
        self.infos.append(line)
        print(line, file=sys.stderr if self.as_json else sys.stdout, flush=True)

    def finish(self, rc: int, result: str, reason: str = "", fixes: Optional[List[Item]] = None,
               manual: Optional[List[Item]] = None, errors: Optional[List[Item]] = None,
               new_errors: Optional[List[Item]] = None, unconverged: Optional[List[Item]] = None,
               undone: Optional[List[Item]] = None, restored: Optional[List[str]] = None,
               not_restored: Optional[List[Tuple[str, str]]] = None, rounds: int = 0) -> int:
        fixes, manual, errors = fixes or [], manual or [], errors or []
        new_errors, unconverged, undone = new_errors or [], unconverged or [], undone or []
        restored, not_restored = restored or [], not_restored or []
        mode = "apply" if self.apply else "check"
        if self.as_json:
            print(json.dumps({
                "mode": mode, "result": result, "exit": rc, "reason": reason, "rounds": rounds,
                "applied": bool(self.apply and fixes and rc != 2),
                "fix": [asdict(i) for i in fixes], "manual": [asdict(i) for i in manual],
                "errors": [asdict(i) for i in errors], "new_errors": [asdict(i) for i in new_errors],
                "unconverged": [asdict(i) for i in unconverged], "undone": [asdict(i) for i in undone],
                "restored": restored, "not_restored": [{"file": f, "error": e} for f, e in not_restored],
                "info": self.infos,
            }, ensure_ascii=False, indent=2))
            return rc
        for i in fixes + manual:
            print(i.text())
        for i in errors:
            print(f"{i.text()}（修復の後の再検査で確かめます）")
        for i in unconverged:
            print("UNCONVERGED " + i.text().split(" ", 1)[1])
        for i in undone:
            print("UNDONE " + i.text().split(" ", 1)[1])
        for i in new_errors:
            print("NEW-ERROR " + i.text().split(" ", 1)[1])
        if reason:
            print(f"ERROR rdfix: {reason}")
        if restored:
            print(f"  修復前の内容に戻したファイル: {', '.join(restored)}")
        for f, e in not_restored:
            print(f"ERROR rdfix: {f} を元に戻せませんでした（{e}）。修復前の内容は work/.ebak/rdfix-undo-*/ に保存しました")
        hint = ""
        if not self.apply and fixes:
            hint = " → `python scripts/rdfix.py --full --apply` で自動修復します"
        elif manual and rc == 1:
            hint = " → 手動対応は各行の担当の役割が直します"
        print(f"rdfix: fix={len(fixes)} manual={len(manual)} mode={mode} rounds={rounds} result={result}{hint}")
        return rc


def _items(actions, kind: str) -> List[Item]:
    out = []
    for a in actions:
        m = LOC_LINE_RE.match(a.loc)
        out.append(Item(kind, a.chk, a.loc, a.msg, a.owner, a.target, _file_of(a.loc), int(m.group(2)) if m else 0))
    return out


def _err_items(errors) -> List[Item]:
    return [Item("ERROR", e.chk, e.loc, e.msg, CHK_OWNER.get(e.chk, "rd-author"), "", _file_of(e.loc),
                 int(LOC_LINE_RE.match(e.loc).group(2)) if LOC_LINE_RE.match(e.loc) else 0,
                 CHK_HINT.get(e.chk, ""), "rdcheck") for e in errors]


def _manual_items(root: Path, insp: Inspection) -> List[Item]:
    loc_of = Locator(root, insp.fixer.doc)
    out = [manual_item(a, loc_of, "rdfix") for a in insp.manual]
    out += [manual_item(e, loc_of, "rdcheck") for e in insp.uncovered()]
    return out


def _dedupe(items: List[Item]) -> List[Item]:
    seen: Set[str] = set()
    out = []
    for i in items:
        t = i.text()
        if t not in seen:
            seen.add(t)
            out.append(i)
    return out


def _summary(exc: BaseException) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    where = f"（{Path(tb[-1].filename).name}:{tb[-1].lineno} {tb[-1].name}）" if tb else ""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}{': ' + text if text else ''}{where}"


def _log_error(root: Path, cfg: dict, exc: BaseException) -> str:
    try:
        p = h.work_dir(root, cfg) / ".ebak" / "rdfix-error.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"--- {h.now_iso()} pid={os.getpid()}\n")
            fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return Path(os.path.relpath(p, root)).as_posix()
    except (OSError, ValueError):
        return ""


def run_full(root: Path, cfg: dict, args, only: Set[str]) -> int:
    """`--full` (check only) and `--full --apply` (check -> repair -> re-check). See the module docstring."""
    rep = FullReport(args.json, args.apply)
    state: Dict[str, object] = {"tx": None, "attempted": []}
    lock: Optional[RepairLock] = None
    try:
        if args.apply and is_work_branch(root):
            return rep.finish(2, "refused", "作業役のブランチ（work/<run-id>/<item>）では --apply しません。"
                                            "conductor が統合ブランチで実行します（G-2）")
        if args.apply:
            wait = args.lock_wait if args.lock_wait is not None else _cfg_number(cfg, "lock_wait_sec", LOCK_WAIT_SEC, 0)
            lock = RepairLock(lock_path(root, cfg))
            ok, rec = lock.acquire(max(0.0, wait), rep.info)
            if not ok:
                lock = None
                return rep.finish(2, "lock-timeout",
                                  f"同じリポジトリの別の修復（PID {rec.get('pid', '?')}）が {wait:g} 秒以内に終わらなかったため、"
                                  "書き込まずに終了しました。先の修復が終わってから `python scripts/rdfix.py --full --apply` を実行し直します")
            pid = rec.get("pid")
            if isinstance(pid, int) and pid != os.getpid():
                gone = rec.get("host") not in (None, socket.gethostname()) or not pid_alive(pid)
                rep.info(f"INFO rdfix: 異常終了した修復（PID {pid}）が残した排他を引き継ぎました"
                         + ("（PID {} のプロセスは存在しません）".format(pid) if gone else
                            "（OS のロックは解放済みで、PID {} は別のプロセスです）".format(pid)))
            n = sweep_temp(root, cfg)
            if n:
                rep.info(f"INFO rdfix: 中断した修復が残した一時ファイル {n} 件を取り除きました")
        insp = inspect(root, cfg, args.adopt, only)
        if not args.apply:
            fixes = _items(insp.fixes, "FIX")
            if fixes:
                manual = _manual_items(root, Inspection(insp.fixer, insp.manual, []))
                errors = _err_items(insp.uncovered())
            else:
                manual, errors = _manual_items(root, insp), []
            rc = 1 if fixes or manual or errors else 0
            result = "plan" if fixes else ("manual" if manual else "pass")
            return rep.finish(rc, result, fixes=fixes, manual=manual, errors=errors)
        return _apply_full(root, cfg, args, only, rep, insp, state)
    except BaseException as exc:  # NFR-REL-002 AC-247: summary + undo instead of a traceback
        tx = state.get("tx")
        restored: List[str] = []
        failed: List[Tuple[str, str]] = []
        if isinstance(tx, Transaction):
            try:
                restored, failed = tx.rollback()
            except BaseException as exc2:  # noqa: BLE001 - report, never raise from here
                failed = [("*", _summary(exc2))]
        log = _log_error(root, cfg, exc)
        what = "中断されたため" if isinstance(exc, KeyboardInterrupt) else "想定外の内部エラーのため"
        undo = "すべての変更を取り消し、修復前の内容に戻しました" if isinstance(tx, Transaction) and not failed else \
            ("一部の変更を取り消せませんでした" if failed else "何も書き込んでいません")
        return rep.finish(2, "error", f"{what}{'修復' if args.apply else '確認'}を中止しました: {_summary(exc)}。{undo}"
                          + (f"（詳細: {log}）" if log else ""),
                          undone=_items(state.get("attempted") or [], "FIX"), restored=restored, not_restored=failed)
    finally:
        if lock is not None:
            lock.release()


def _apply_full(root: Path, cfg: dict, args, only: Set[str], rep: FullReport, insp: Inspection, state: dict) -> int:
    max_rounds = int(_cfg_number(cfg, "max_rounds", MAX_ROUNDS, 1))
    before_errors = {_err_key(e) for e in insp.errors}
    applied: List[Action] = []
    rounds = 0
    while insp.fixes and rounds < max_rounds:
        tx = state.get("tx")
        if tx is None:
            tx = Transaction(root, cfg)
            state["tx"] = tx
        rounds += 1
        state["attempted"] = applied + insp.fixes
        try:
            with tx.capture():
                insp.fixer.apply()
        except OSError as exc:
            return _cancel(rep, tx, f"書き込みに失敗しました（{_summary(exc)}）", state, rounds)
        protected = tx.protected_changed()
        if protected:
            return _cancel(rep, tx, "修復が要求定義書または外部連携カタログを書き換えました: " + ", ".join(protected)
                           + "（要求定義書と外部連携カタログは修復の対象外です）", state, rounds)
        applied += insp.fixes
        insp = inspect(root, cfg, args.adopt, only)  # the re-check of this round
    new = [e for e in insp.errors if _err_key(e) not in before_errors]
    if new and state.get("tx") is not None:
        return _cancel(rep, state["tx"], f"修復の後の再検査で、修復前になかったエラーが {len(new)} 件現れました", state, rounds,
                       new_errors=_err_items(new))
    fixes = _dedupe(_items(applied, "FIX"))
    if insp.fixes:  # AC-249: not converged within PARAM-026 rounds; the repairs made so far are kept
        return rep.finish(1, "not-converged",
                          f"{max_rounds} 回の検査と修復の繰り返しで収束しませんでした（PARAM-026）。"
                          "残った項目は `python scripts/rdfix.py --full` で確かめ、conductor が原因を調べます",
                          fixes=fixes, manual=_manual_items(root, Inspection(insp.fixer, insp.manual, [])),
                          errors=_err_items(insp.uncovered()), unconverged=_items(insp.fixes, "FIX"), rounds=rounds)
    manual = _manual_items(root, insp)
    if manual:
        return rep.finish(1, "manual", fixes=fixes, manual=manual, rounds=rounds)
    return rep.finish(0, "repaired" if applied else "pass", fixes=fixes, rounds=rounds)


def _cancel(rep: FullReport, tx: Transaction, reason: str, state: dict, rounds: int,
            new_errors: Optional[List[Item]] = None) -> int:
    restored, failed = tx.rollback()
    state["tx"] = None
    tail = "すべての変更を取り消し、修復前の内容に戻しました" if not failed else "一部の変更を取り消せませんでした"
    return rep.finish(2, "cancelled", f"{reason}。{tail}", undone=_dedupe(_items(state.get("attempted") or [], "FIX")),
                      new_errors=new_errors, restored=restored, not_restored=failed, rounds=rounds)


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="修正を書き込む（既定は確認だけ）")
    ap.add_argument("--only", default="", help=f"対象を絞る（カンマ区切り）: {', '.join(TARGETS)}")
    ap.add_argument("--adopt", action="store_true", help="ID 台帳にない ID を取り込む（手で振った ID でないと確認したとき）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--full", action="store_true",
                    help="データ層の検査（rdcheck）と修復の計画をまとめて行う。--apply で検査→修復→再検査（FR-1046）")
    ap.add_argument("--lock-wait", type=float, default=None, metavar="SEC",
                    help=f"--full --apply の排他の待ち秒（既定 {LOCK_WAIT_SEC:g} 秒 = PARAM-027）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    only = {x.strip() for x in args.only.split(",") if x.strip()} or set(TARGETS)
    bad = only - set(TARGETS)
    if bad:
        ap.error(f"--only は {', '.join(TARGETS)} から選びます（不明: {', '.join(sorted(bad))}）")
    if args.full:
        return run_full(root, cfg, args, only)
    if args.apply and is_work_branch(root):
        print("ERROR rdfix: 作業役のブランチ（work/<run-id>/<item>）では --apply しません。"
              "conductor が統合ブランチで実行します（G-2）")
        return 2
    fx = Fixer(root, cfg, args.adopt, only)
    actions = fx.plan()
    fixes = [a for a in actions if a.kind == "FIX"]
    manual = [a for a in actions if a.kind == "MANUAL"]
    rc = 1 if fixes and not args.apply else 0
    after: List[str] = []
    if args.apply and fixes:
        fx.apply()
        left = [a for a in Fixer(root, cfg, args.adopt, only).plan() if a.kind == "FIX"]
        if left:
            rc = 1
            after += [f"ERROR rdfix: 修正後も {len(left)} 件が残っています（収束しません）: " + left[0].line()]
    if args.apply:
        crc, lines = rdcheck_summary(root)
        after += [l for l in lines if l.startswith("ERROR")][:15] + lines[-1:]
    if args.json:
        print(json.dumps({"applied": bool(args.apply and fixes), "fix": [asdict(a) for a in fixes],
                          "manual": [asdict(a) for a in manual], "after": after}, ensure_ascii=False, indent=2))
        return rc
    for a in fixes + manual:
        print(a.line())
    for l in after:
        print("  " + l if not l.startswith("ERROR rdfix") else l)
    mode = "applied" if args.apply else "dry-run"
    hint = " → `python scripts/rdfix.py --apply` で修正します" if fixes and not args.apply else ""
    print(f"rdfix: fix={len(fixes)} manual={len(manual)} mode={mode}{hint}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
