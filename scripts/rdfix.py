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
                                    file references (CHK-08), implementation files of retired requirements (CHK-17)
  ledger    tests/system/ledger.json  missing fields, requirement_ids, missing / orphan ac_digests
                                    -> through ledger.py with history (G-2)
  gitignore .gitignore              /work/ (CHK-23)
  history   docs/run-history.md     rows duplicated by merge=union (CHK-23)
What needs a judgment (changed AC text, reused or hand-numbered IDs, ...) is listed as MANUAL with the role
that fixes it. Output: "FIX <CHK> <loc> <msg>" / "MANUAL <CHK> <loc> <msg>（担当: role）" and one summary line.
Exit code: 0 = nothing left to fix automatically, 1 = fixes pending (dry run) or not converged, 2 = refused.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402

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
    def __init__(self, root: Path, cfg: dict, adopt: bool, only: Set[str]):
        self.root, self.cfg, self.adopt, self.only = root, cfg, adopt, only
        self.doc = h.parse_requirements(root, cfg)
        self.actions: List[Action] = []
        self.writers: List = []
        self._files: Optional[List[str]] = None
        self._file_set: Set[str] = set()
        self._id_index: Optional[Dict[str, Tuple[Set[str], Set[str]]]] = None
        self._renames: Optional[Dict[str, str]] = None

    # ------------------------------------------------------------------ helpers
    def act(self, kind: str, chk: str, loc: str, msg: str, owner: str, target: str) -> None:
        self.actions.append(Action(kind, chk, loc, msg, owner, target))

    def files(self) -> List[str]:
        if self._files is None:
            self._files = h.tracked_files(self.root)
            self._file_set = set(self._files)
        return self._files

    def exists(self, p: str) -> bool:
        rel = p.lstrip("./")
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
        cur, seen = p.lstrip("./"), set()
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
        for tb in tables:
            is_func = any(tb is f for f in func)
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
        rc, out = h.git(["ls-files"], self.root)
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


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="修正を書き込む（既定は確認だけ）")
    ap.add_argument("--only", default="", help=f"対象を絞る（カンマ区切り）: {', '.join(TARGETS)}")
    ap.add_argument("--adopt", action="store_true", help="ID 台帳にない ID を取り込む（手で振った ID でないと確認したとき）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    only = {x.strip() for x in args.only.split(",") if x.strip()} or set(TARGETS)
    bad = only - set(TARGETS)
    if bad:
        ap.error(f"--only は {', '.join(TARGETS)} から選びます（不明: {', '.join(sorted(bad))}）")
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
