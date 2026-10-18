#!/usr/bin/env python3
"""rdcheck.py - parse and check the management data (plan §10, CHK-01..27).

Usage:
  python scripts/rdcheck.py check [--base REF] [--run RUN_ID] [--strict] [--strict-ledger] [--json]
  python scripts/rdcheck.py show ID [ID ...]        # print only the requirement / AC block (token saving)
  python scripts/rdcheck.py trace ID|名前 [...] [--json]  # links up and down (G / SRC / 用語・状態 / PARAM / AC / 台帳 / カタログ / コード)
  python scripts/rdcheck.py list [--state 承認済み] [--level system] [--priority MUST] [--kind FR] [--area 名 | --by-area]
  python scripts/rdcheck.py index [ID ...] [--kind 上位|出典|参照|実装|検証|使用] [--json]  # 種類つきの関係（都度生成）
  python scripts/rdcheck.py stats                   # metrics for rd-audit
  python scripts/rdcheck.py digest [AC ...]         # current AC digests (PARAM expanded)

Exit code of `check`: 0 = no error, 1 = at least one error.
One finding per line: "<ERROR|WARN> <CHK-ID> <location> <message>".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.dont_write_bytecode = True  # FR-1062 AC-343: 導出は読み取り専用。利用者のリポジトリに __pycache__ を残さない
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402
import entities as ent  # noqa: E402

# requirements that must have a row in the function table of the catalog (same as rdfix.CATALOG_STATES)
CATALOG_STATES = ("承認済み", "承認待ち", "保留")
HISTORY_SECTION_RE = re.compile(r"変更履歴|決定記録|監査指摘")
ASSET_RE = re.compile(r"(共通部品|API|イベント|テーブル)\s*[「『]([^」』]+)[」』]")


@dataclass
class Finding:
    level: str
    chk: str
    loc: str
    msg: str

    def line(self) -> str:
        return f"{self.level} {self.chk} {self.loc} {self.msg}"


@dataclass
class Ref:
    """One mention of an ID in the requirements definition (outside its own definition line)."""
    file: str
    line: int
    section: str
    owner: str  # requirement whose block contains the mention ('' if none)


class Checker:
    def __init__(self, root: Path, cfg: dict, base: Optional[str], run_id: Optional[str],
                 strict: bool, strict_ledger: Optional[bool]):
        self.root, self.cfg, self.base, self.run_id = root, cfg, base, run_id
        self.strict = strict
        self.findings: List[Finding] = []
        self.doc = h.parse_requirements(root, cfg)
        self.ledger = h.load_ledger(root, cfg)
        self.cat_exists, self.cat_rows, self.cat_refs = h.parse_catalog(root, cfg)
        self.cat_req = h.catalog_req_rows(self.cat_rows)
        self.cat_tables = h.parse_catalog_tables(root, cfg)
        self.integ = h.parse_integrations(root, cfg)
        self._files: Optional[List[str]] = None
        self._refs: Optional[Dict[str, List[Ref]]] = None
        self.croot = h.conductor_root(root, cfg)
        if strict_ledger is None:
            strict_ledger = strict
            rid = run_id or h.current_run(self.croot, cfg)
            if rid and h.load_meta(self.croot, cfg, rid).get("ledger_strict"):
                strict_ledger = True
        self.strict_ledger = strict_ledger

    # ------------------------------------------------------------------ helpers
    def add(self, level: str, chk: str, loc: str, msg: str) -> None:
        self.findings.append(Finding(level, chk, loc, msg))

    def err(self, chk: str, loc: str, msg: str) -> None:
        self.add("ERROR", chk, loc, msg)

    def warn(self, chk: str, loc: str, msg: str) -> None:
        self.add("ERROR" if self.strict and chk in ("CHK-09",) else "WARN", chk, loc, msg)

    @staticmethod
    def loc(file: str, line) -> str:
        return f"{file}:{line}"

    def git_ls_files(self):
        # NFR-PERF-003 AC-089: 同一引数の git ls-files は 1 回だけ起動する
        if getattr(self, "_ls_cache", None) is None:
            self._ls_cache = h.git(["ls-files"], self.root)
        return self._ls_cache

    def files(self) -> List[str]:
        if self._files is None:
            self._files = h.tracked_files(self.root)
        return self._files

    def read(self, rel: str) -> str:
        p = self.root / rel
        try:
            if p.stat().st_size > 2_000_000:
                return ""
            data = p.read_bytes()
        except OSError:
            return ""
        if b"\0" in data[:4096]:
            return ""
        return data.decode("utf-8", "replace")

    def scan_files(self) -> List[str]:
        ex = self.cfg["checks"]["id_scan_exclude"] + [h.mf(self.cfg, "ledger")]
        return [f for f in self.files() if not h.glob_match(f, ex)]

    def test_files(self) -> List[str]:
        rx = re.compile(self.cfg["checks"]["test_path_pattern"])
        return [f for f in self.scan_files() if rx.search(f)]

    # ------------------------------------------------------------------ run all
    def run_all(self) -> List[Finding]:
        req_path = h.mf(self.cfg, "requirements")
        if not self.doc.exists:
            self.add("ERROR" if self.strict else "WARN", "CHK-00", req_path,
                     "要求定義書がありません（未初期化）。conductor の工程 1 で rd-author が作成します")
            self.chk23()
            return self.findings
        for fn in (self.chk01_02, self.chk03, self.chk04, self.chk05, self.chk06_22, self.chk07_08,
                   self.chk09, self.chk10_11, self.chk12, self.chk13_14_15, self.chk16, self.chk17,
                   self.chk18, self.chk19, self.chk20, self.chk21, self.chk23, self.chk25, self.chk26,
                   self.chk27, self.chk24, self.chk28, self.chk29, self.chk30, self.chk31, self.chk32):
            fn()
        return self.findings

    # ------------------------------------------------------------------ reference index
    def refs(self) -> Dict[str, List[Ref]]:
        """ID -> mentions in the requirements definition, excluding definition lines, code blocks and `code`."""
        if self._refs is None:
            def_lines = {(d.file, d.line) for ds in self.doc.defs.values() for d in ds}
            out: Dict[str, List[Ref]] = {}
            for rel, text in self.doc.text.items():
                section, owner, owner_lvl, in_code = "", "", 0, False
                for ln, line in enumerate(text.splitlines(), start=1):
                    if line.lstrip().startswith("```"):
                        in_code = not in_code
                        continue
                    if in_code:
                        continue
                    hm = h.HEADING_RE.match(line)
                    if hm:
                        section = hm.group(2)
                        lvl = len(hm.group(1))
                        rm = h.REQ_HEADING_RE.match(line)
                        if rm:
                            owner, owner_lvl = rm.group(2), lvl
                        elif owner and lvl <= owner_lvl:
                            owner = ""
                    body = re.sub(r"`[^`]*`", "", line)
                    own = (rel, ln) in def_lines
                    for m in h.ID_RE.finditer(body):
                        id_ = m.group(0)
                        if own and body.find(id_) == m.start() and self._defined_here(id_, rel, ln):
                            continue
                        out.setdefault(id_, []).append(Ref(rel, ln, section, owner))
            self._refs = out
        return self._refs

    def _defined_here(self, id_: str, rel: str, ln: int) -> bool:
        return any(d.file == rel and d.line == ln for d in self.doc.defs.get(id_, []))

    # ------------------------------------------------------------------ CHK-01/02
    def chk01_02(self) -> None:
        for id_, defs in self.doc.defs.items():
            if len(defs) > 1:
                where = ", ".join(self.loc(d.file, d.line) for d in defs)
                self.err("CHK-01", self.loc(defs[0].file, defs[0].line), f"{id_} が重複して定義されています（{where}）")
        reg_path = self.root / h.mf(self.cfg, "id_registry")
        if not reg_path.exists():
            self.warn("CHK-01", h.mf(self.cfg, "id_registry"), "ID 台帳がありません。scripts/next-id.py --sync --adopt で作成してください")
            return
        reg = h.parse_registry_text(h.read_text(reg_path))
        for id_, defs in self.doc.defs.items():
            kind = h.id_kind(id_)
            if kind in ("", "SRC", "G"):
                continue
            ent = reg.get(id_)
            if ent is None:
                self.err("CHK-01", self.loc(defs[0].file, defs[0].line),
                         f"{id_} が ID 台帳にありません。ID は scripts/next-id.py でだけ採番します（G-3）")
            elif re.search(r"削除済み|欠番", ent["state"]):
                self.err("CHK-02", self.loc(defs[0].file, defs[0].line),
                         f"{id_} は ID 台帳で「{ent['state']}」です。廃止・削除した ID は再利用しません")

    # ------------------------------------------------------------------ CHK-03
    def chk03(self) -> None:
        for ac in self.doc.acs.values():
            if not ac.requirement:
                self.err("CHK-03", self.loc(ac.file, ac.line), f"{ac.id} の対応する要求がありません（要求の見出しの下に書くか「対応する要求:」を付けます）")
            elif ac.requirement not in self.doc.requirements:
                self.err("CHK-03", self.loc(ac.file, ac.line), f"{ac.id} が存在しない要求 {ac.requirement} を参照しています")

    # ------------------------------------------------------------------ CHK-04
    def chk04(self) -> None:
        goals = set(self.doc.kind_ids("G"))
        used: Dict[str, int] = {g: 0 for g in goals}
        for r in self.doc.requirements.values():
            if not r.active:
                continue
            upper = r.fields.get("上位", "")
            gids = re.findall(r"G-\d{3,}", upper)
            if not gids and not re.search(r"既定制約|制約", upper):
                self.err("CHK-04", self.loc(r.file, r.line), f"{r.id} の「上位」に G-ID または既定制約がありません")
            for g in gids:
                if g not in goals:
                    self.err("CHK-04", self.loc(r.file, r.line), f"{r.id} が存在しない目的 {g} を参照しています")
                elif r.state == "承認済み":
                    used[g] += 1
        for g, n in used.items():
            if n == 0:
                d = self.doc.defs[g][0]
                self.warn("CHK-04", self.loc(d.file, d.line), f"{g} に承認済みの要求がありません")

    # ------------------------------------------------------------------ CHK-05
    def chk05(self) -> None:
        for r in self.doc.requirements.values():
            if not r.active or r.priority != "MUST":
                continue
            if r.acs:
                continue
            qs = re.findall(r"Q-\d{3,}", " ".join(r.body))
            open_q = [q for q in qs if q in self.doc.questions and not self.doc.questions[q]["answered"]]
            if not open_q:
                self.err("CHK-05", self.loc(r.file, r.line), f"MUST 要求 {r.id} に受入基準も未回答の質問票もありません")

    # ------------------------------------------------------------------ CHK-06 / CHK-22
    def chk06_22(self) -> None:
        for r in self.doc.requirements.values():
            if not r.state_raw:
                continue
            if r.state not in h.STATES:
                self.err("CHK-20", self.loc(r.file, r.line), f"{r.id} の決定状態「{r.state_raw}」は 承認済み／承認待ち／保留／却下／廃止 のどれでもありません")
                continue
            if r.state != "承認済み":
                continue
            basis = r.basis
            if not basis:
                self.err("CHK-06", self.loc(r.file, r.line), f"承認済みの {r.id} に決定記録（承認の根拠と日付）がありません")
                continue
            ok = False
            if re.search(r"(依頼|承認依頼|包括承認)\s*\d{4}-\d{2}-\d{2}", basis):
                ok = True
            m = re.search(r"(Q-\d{3,})\s*\d{4}-\d{2}-\d{2}", basis)
            if m:
                if m.group(1) in self.doc.defs:
                    ok = True
                else:
                    self.err("CHK-22", self.loc(r.file, r.line), f"{r.id} の決定記録が存在しない {m.group(1)} を指しています")
                    continue
            if re.search(r"既存", basis):
                ok = True
            if not ok:
                self.err("CHK-22", self.loc(r.file, r.line), f"{r.id} の決定記録「{basis}」が 依頼・Q・承認依頼・包括承認 のどれも指していません")

    # ------------------------------------------------------------------ CHK-07 / CHK-08
    def chk07_08(self) -> None:
        cat = h.mf(self.cfg, "catalog")
        if not self.cat_exists:
            self.warn("CHK-07", cat, "カタログがありません")
            return
        if not any(k == "feature" for k, _ in self.cat_tables):
            self.err("CHK-07", cat, "カタログに機能の表（要求 ID・題名・決定状態の列）がありません")
        seen: Dict[str, int] = {}
        for row in self.cat_rows:
            m = h.REQ_ID_RE.search(h.catalog_cell(row, "要求ID"))
            if not m:
                continue
            rid = m.group(1)
            if rid in seen and seen[rid] != row.line:
                self.err("CHK-07", self.loc(cat, row.line), f"{rid} の行が機能の表に重複しています（{seen[rid]} 行目）。1 要求 1 行にします")
            seen.setdefault(rid, row.line)
        for rid, row in self.cat_req.items():
            req = self.doc.requirements.get(rid)
            if req is None:
                self.err("CHK-07", self.loc(cat, row.line), f"カタログの {rid} が要求定義書にありません")
                continue
            cstate = h.normalize_state(h.catalog_cell(row, "決定状態"))
            if cstate != req.state:
                self.err("CHK-07", self.loc(cat, row.line), f"{rid} の決定状態が一致しません（カタログ={cstate or '空'}、要求定義書={req.state or '空'}）")
            if any("題名" in k for k in row.cells):
                ctitle = h.strip_md(h.catalog_cell(row, "題名"))
                if req.title and ctitle != req.title:
                    self.err("CHK-07", self.loc(cat, row.line), f"{rid} の題名が一致しません（カタログ=「{ctitle}」、要求定義書=「{req.title}」）")
        for rid, req in self.doc.requirements.items():
            if req.state in CATALOG_STATES and rid not in self.cat_req:
                self.err("CHK-07", self.loc(req.file, req.line),
                         f"{rid}（{req.state}）がカタログの機能の表にありません（rdfix.py --only catalog --apply で行を追加できます）")
        files = set(self.files())
        for ln, p in self.cat_refs:
            rel = p[2:] if p.startswith("./") else p
            if rel in files or (self.root / rel).exists():
                continue
            self.err("CHK-08", self.loc(cat, ln), f"カタログのファイル {p} が存在しません")

    # ------------------------------------------------------------------ CHK-09
    def implementable_must(self) -> List[h.Requirement]:
        out = []
        for r in self.doc.requirements.values():
            if r.state != "承認済み" or r.priority != "MUST":
                continue
            acs = [self.doc.acs[a] for a in r.acs if a in self.doc.acs]
            if acs and all(a.blocked for a in acs):
                continue
            out.append(r)
        return out

    def chk09(self) -> None:
        ids_in_tests: Set[str] = set()
        for f in self.test_files():
            ids_in_tests.update(h.CODE_ID_RE.findall(self.read(f)))
        manual = self.root / h.mf(self.cfg, "manual_tests")
        if manual.exists():
            ids_in_tests.update(h.CODE_ID_RE.findall(h.read_text(manual)))
        for r in self.implementable_must():
            row = self.cat_req.get(r.id)
            impl = h.catalog_cell(row, "実装ファイル") if row else ""
            implemented = bool(row) and bool(h.split_paths(impl))
            if r.id in ids_in_tests:
                if not row:
                    self.err("CHK-09", self.loc(r.file, r.line), f"MUST 要求 {r.id} がカタログの機能の表にありません")
                continue
            if implemented:
                self.err("CHK-09", self.loc(r.file, r.line), f"実装済みの MUST 要求 {r.id} の ID がテストコードにも {h.mf(self.cfg, 'manual_tests')} にもありません")
            else:
                self.warn("CHK-09", self.loc(r.file, r.line), f"MUST 要求 {r.id} は未実装です（カタログ・テストに未反映）")

    # ------------------------------------------------------------------ CHK-10 / CHK-11
    def chk10_11(self) -> None:
        led = h.mf(self.cfg, "ledger")
        cases = self.ledger.get("cases", [])
        sys_acs = {a.id: a for a in h.system_acs(self.doc)}
        covered: Set[str] = set()
        level_missing = "ERROR" if (self.strict_ledger or self.strict) else "WARN"
        for c in cases:
            cid = c.get("id", "?")
            for a in c.get("ac_ids", []):
                covered.add(a)
                if a not in self.doc.acs:
                    self.err("CHK-10", led, f"{cid} が存在しない受入基準 {a} を参照しています")
                elif a not in sys_acs and c.get("status") != "blocked":
                    ac = self.doc.acs[a]
                    req = self.doc.requirements.get(ac.requirement or "")
                    why = "BLOCKED" if ac.blocked else (f"検証レベル={ac.level or '未記入'}" if ac.level != "system" else f"要求の決定状態={req.state if req else '不明'}")
                    self.err("CHK-10", led, f"{cid} の {a} は System Test の対象外です（{why}）。ケースを理由つきで blocked にするか更新します")
            for r in c.get("requirement_ids", []):
                if r not in self.doc.requirements:
                    self.err("CHK-10", led, f"{cid} が存在しない要求 {r} を参照しています")
        for a, ac in sys_acs.items():
            if a not in covered:
                self.add(level_missing, "CHK-10", self.loc(ac.file, ac.line), f"system の受入基準 {a} に対応する台帳のケースがありません")
        digests = self.ledger.get("ac_digests", {})
        for a in sorted(covered):
            ac = self.doc.acs.get(a)
            if not ac:
                continue
            cur = h.ac_digest(ac, self.doc.params)
            old = digests.get(a)
            if old is None:
                self.add(level_missing, "CHK-11", led, f"{a} の ac_digests がありません（ledger.py digests --update）")
            elif old != cur:
                self.add(level_missing, "CHK-11", self.loc(ac.file, ac.line), f"{a} の本文が台帳の作成時から変わっています（{old} → {cur}）。test-designer がケースを見直します")

    # ------------------------------------------------------------------ CHK-12
    def chk12(self) -> None:
        led = h.mf(self.cfg, "ledger")
        branch = h.current_branch(self.root)
        wm = re.match(r"^work/([^/]+)/[^/]+$", branch)
        if wm:
            integ = h.load_meta(self.croot, self.cfg, wm.group(1)).get("integration_branch")
            fork = None
            for ref in ([integ] if integ else []) + [self.cfg.get("base_branch", "main")]:
                if ref and h.ref_exists(self.root, ref):
                    rc, out = h.git(["merge-base", "HEAD", ref], self.root)
                    if rc == 0 and out.strip():
                        fork = out.strip()
                        break
            if fork:
                rc, out = h.git(["diff", "--name-only", f"{fork}...HEAD", "--", "tests/system"], self.root)
                changed = [x for x in out.splitlines() if x.strip()] if rc == 0 else []
                if changed:
                    self.err("CHK-12", branch, f"作業役のブランチが System Test を変更しています: {', '.join(changed[:5])}（G-2）")
            return
        if not self.base:
            return
        old_text = h.git_show(self.root, self.base, led)
        if not old_text:
            return
        try:
            old = json.loads(old_text)
        except json.JSONDecodeError:
            return
        now = {c.get("id"): c for c in self.ledger.get("cases", [])}
        grew_any = False
        for oc in old.get("cases", []):
            cid = oc.get("id")
            nc = now.get(cid)
            if nc is None:
                self.err("CHK-12", led, f"台帳のケース {cid} が削除されています（削除はせず blocked と理由を history に残します）")
                continue
            grew = len(nc.get("history", [])) > len(oc.get("history", []))
            grew_any = grew_any or grew
            if nc.get("command") != oc.get("command") and not grew:
                self.err("CHK-12", led, f"{cid} の command が理由（history）なしに変更されています")
            if sorted(nc.get("ac_ids", [])) != sorted(oc.get("ac_ids", [])) and not grew:
                self.err("CHK-12", led, f"{cid} の ac_ids が理由（history）なしに変更されています")
        rx = re.compile(r"\bassert|\bexpect\s*\(|\bshould\b|\bAssert\.|\bverify\s*\(")
        rc, out = h.git(["diff", "--name-only", f"{self.base}", "--", "tests/system"], self.root)
        for rel in (out.splitlines() if rc == 0 else []):
            if rel.endswith(".json"):
                continue
            before = h.git_show(self.root, self.base, rel) or ""
            after = self.read(rel)
            nb, na = len(rx.findall(before)), len(rx.findall(after))
            if na < nb and not grew_any:
                self.err("CHK-12", rel, f"System Test の検証（assert 等）が {nb} → {na} に減っていて、台帳の history に理由がありません")

    # ------------------------------------------------------------------ CHK-13/14/15
    def changed_ids(self) -> Optional[Set[str]]:
        if not self.base:
            return None
        texts = {}
        for rel in self.doc.files:
            t = h.git_show(self.root, self.base, rel)
            if t is not None:
                texts[rel] = t
        old = h.parse_requirements_texts(texts)
        changed: Set[str] = set()
        for rid, r in self.doc.requirements.items():
            o = old.requirements.get(rid)
            if o is None or o.statement != r.statement:
                changed.add(rid)
        for aid, a in self.doc.acs.items():
            o = old.acs.get(aid)
            if o is None or o.full_text() != a.full_text():
                changed.add(aid)
        return changed

    def chk13_14_15(self) -> None:
        changed = self.changed_ids()
        words = self.cfg["checks"]["ambiguous_words"]
        unit_rx = re.compile(self.cfg["checks"]["unit_pattern"])
        items = []
        for r in self.doc.requirements.values():
            if r.active:
                items.append((r.id, r.file, r.line, r.statement, r.priority))
        for a in self.doc.acs.values():
            req = self.doc.requirements.get(a.requirement or "")
            if req is None or req.active:
                items.append((a.id, a.file, a.line, a.full_text(), req.priority if req else ""))
        for id_, f, ln, text, prio in items:
            if not text:
                continue
            if changed is None or id_ in changed:
                hits = [w for w in words if w in text]
                if hits:
                    lvl = "ERROR" if (self.strict and prio == "MUST") else "WARN"
                    self.add(lvl, "CHK-13", self.loc(f, ln), f"{id_} に曖昧な語があります: {'、'.join(hits)}")
            plain = h.PARAM_REF_RE.sub("", text)
            plain = re.sub(r"WCAG\s*[\d.]+|\d{4}-\d{2}-\d{2}|(?:[A-Z]+-)+\d{3,}", "", plain)
            nums = unit_rx.findall(plain)
            if nums:
                self.warn("CHK-14", self.loc(f, ln), f"{id_} に数値と単位の直書きがあります（PARAM を参照します）: {'、'.join(nums[:3])}")
            for term, forb in self.doc.terms:
                bad = [w for w in forb if w and w in text]
                if bad:
                    self.warn("CHK-15", self.loc(f, ln), f"{id_} が用語「{term}」の禁止同義語を使っています: {'、'.join(bad)}")

    # ------------------------------------------------------------------ CHK-16
    def chk16(self) -> None:
        for rel, text in self.doc.text.items():
            for ln, line in enumerate(text.splitlines(), start=1):
                line = re.sub(r"`[^`]*`", "", line)
                for m in h.PARAM_REF_RE.finditer(line):
                    if m.group(1) not in self.doc.params:
                        self.err("CHK-16", self.loc(rel, ln), f"未定義のパラメータ {m.group(1)} を参照しています")
        for r in self.doc.requirements.values():
            for p in re.findall(r"PARAM-\d{3,}", r.fields.get("参照パラメータ", "")):
                if p not in self.doc.params:
                    self.err("CHK-16", self.loc(r.file, r.line), f"{r.id} の参照パラメータ {p} が定義されていません")
        for pid, defs in self.doc.defs.items():
            if pid.startswith("PARAM-") and pid not in self.doc.params:
                self.err("CHK-16", self.loc(defs[0].file, defs[0].line), f"{pid} がパラメータの表（ID・値・単位）にありません")

    # ------------------------------------------------------------------ CHK-17
    def chk17(self) -> None:
        retired = [r for r in self.doc.requirements.values() if r.state == "廃止"]
        if not retired:
            return
        code_ids: Set[str] = set()
        for f in self.scan_files():
            code_ids.update(h.CODE_ID_RE.findall(self.read(f)))
        for r in retired:
            in_code = r.id in code_ids or any(a in code_ids for a in r.acs)
            row = self.cat_req.get(r.id)
            if not in_code and not row:
                self.warn("CHK-17", self.loc(r.file, r.line), f"廃止の {r.id} はコード・テスト・カタログから取り除かれています。本文から外し、変更履歴に残せます")
            if not in_code and row and h.split_paths(h.catalog_cell(row, "実装ファイル")):
                self.err("CHK-17", self.loc(h.mf(self.cfg, "catalog"), row.line), f"廃止の {r.id} のコードがないのに、カタログに実装ファイルが残っています")

    # ------------------------------------------------------------------ CHK-18
    def chk18(self) -> None:
        for ac in self.doc.acs.values():
            if not ac.blocked:
                continue
            ref = ac.blocked_ref
            qs = re.findall(r"Q-\d{3,}", ref)
            ok = bool(re.search(r"TBD|競合", ref))
            for q in qs:
                if q not in self.doc.defs:
                    self.err("CHK-18", self.loc(ac.file, ac.line), f"BLOCKED の {ac.id} が存在しない {q} を参照しています")
                elif self.doc.questions.get(q, {}).get("answered"):
                    self.err("CHK-18", self.loc(ac.file, ac.line), f"BLOCKED の {ac.id} が回答済みの {q} を参照しています。回答を反映して BLOCKED を外します")
                else:
                    ok = True
            if not ok:
                self.err("CHK-18", self.loc(ac.file, ac.line), f"BLOCKED の {ac.id} が未回答の Q・TBD・競合のどれも参照していません")

    # ------------------------------------------------------------------ CHK-19
    def chk19(self) -> None:
        known = set(self.doc.defs)
        reported: Set[str] = set()
        for f in self.scan_files():
            text = self.read(f)
            if not text:
                continue
            for ln, line in enumerate(text.splitlines(), start=1):
                for id_ in h.CODE_ID_RE.findall(line):
                    if id_ not in known and (f, id_) not in reported:
                        reported.add((f, id_))
                        self.err("CHK-19", self.loc(f, ln), f"{id_} が要求定義書にありません")

    # ------------------------------------------------------------------ CHK-20
    def chk20(self) -> None:
        req = h.mf(self.cfg, "requirements")
        if not self.doc.no_ui:
            if not self.doc.has_ui_policy:
                self.err("CHK-20", req, "既定制約（ui_policy）の節がありません（画面を持たないアプリは、その事実と根拠を前提・制約に書きます）")
            need = ["ペルソナ", "業務", "判断", "データ", "役割"]
            ok = any(all(any(n in c for c in hdr) for n in need) for hdr in self.doc.persona_headers)
            if not ok:
                self.err("CHK-20", req, "ペルソナ表に必須の列（ペルソナ・業務・主要な判断・使うデータ・役割）がありません")
        for r in self.doc.requirements.values():
            if not r.active:
                continue
            missing = [k for k in h.required_requirement_fields() if k not in r.fields]
            if missing:
                self.err("CHK-20", self.loc(r.file, r.line), f"{r.id} に構造化欄がありません: {'、'.join(missing)}（値がなければ「なし」と書きます）")
            if r.state == "承認済み":
                for a in r.acs:
                    ac = self.doc.acs.get(a)
                    if ac and ac.level not in h.VERIFICATION_LEVELS:
                        self.err("CHK-20", self.loc(ac.file, ac.line), f"{a} に検証レベル（system／integration／unit／manual）がありません")

    # ------------------------------------------------------------------ CHK-21
    def chk21(self) -> None:
        if not self.run_id:
            return
        rdir = h.run_dir(self.croot, self.cfg, self.run_id)
        if not (rdir / "queue.json").exists():
            return
        q = h.load_queue(self.croot, self.cfg, self.run_id)
        status = {}
        for c in self.ledger.get("cases", []):
            for a in c.get("ac_ids", []):
                status.setdefault(a, []).append(c.get("status"))
        sys_ids = {a.id for a in h.system_acs(self.doc)}
        for it in q.get("items", []):
            if it.get("status") != "done":
                continue
            for rid in it.get("requirement_ids", []):
                row = self.cat_req.get(rid)
                if not row or not h.split_paths(h.catalog_cell(row, "実装ファイル")):
                    self.err("CHK-21", f"queue:{it.get('id')}", f"done の {rid} がカタログに実装ファイルとして載っていません")
            for a in it.get("ac_ids", []):
                if a in sys_ids and not any(s == "pass" for s in status.get(a, [])):
                    self.err("CHK-21", f"queue:{it.get('id')}", f"done の {a} の台帳のケースが pass になっていません")

    # ------------------------------------------------------------------ CHK-23
    def chk23(self) -> None:
        wd = self.cfg["work"]["dir"]
        gi = self.root / ".gitignore"
        lines = h.read_text(gi).splitlines() if gi.exists() else []
        if not any(re.fullmatch(rf"/?{re.escape(wd)}/?\*{{0,2}}", l.strip()) for l in lines):
            self.err("CHK-23", ".gitignore", f"/{wd}/ が .gitignore にありません（一時ファイルを git の管理対象外にします）")
        rx = re.compile(self.cfg["checks"]["temp_file_pattern"])
        rc, out = self.git_ls_files()
        for f in (out.splitlines() if rc == 0 else []):
            if (f.startswith("docs/") or f.startswith("tests/")) and rx.search(f):
                self.err("CHK-23", f, "一時ファイル（ログ・証跡・実行結果）が commit されています。/work に置きます")
        hist = self.root / h.mf(self.cfg, "run_history")
        if hist.exists():
            seen: Dict[str, int] = {}
            for t in h.parse_tables(h.read_text(hist).splitlines()):
                c = t.col("run-id", "run_id")
                if c is None:
                    continue
                for ln, cells in t.rows:
                    rid = h.strip_md(cells[c]) if c < len(cells) else ""
                    if not rid:
                        continue
                    if rid in seen:
                        self.err("CHK-23", self.loc(h.mf(self.cfg, "run_history"), ln), f"run-id {rid} が重複しています（{seen[rid]} 行目）")
                    seen[rid] = ln

    # ------------------------------------------------------------------ CHK-24
    def chk24(self) -> None:
        """Every ID mentioned in the requirements definition and the catalog must point to a definition."""
        already: Set[str] = set()
        for f in self.findings:
            if f.level == "ERROR" and re.search(r"存在しない|未定義|定義されていません|ありません", f.msg):
                already.update(m.group(0) for m in h.ID_RE.finditer(f.msg))
        retired: Set[str] = set()
        reg_path = self.root / h.mf(self.cfg, "id_registry")
        if reg_path.exists():
            for id_, ent in h.parse_registry_text(h.read_text(reg_path)).items():
                if re.search(r"削除済み|欠番|廃止", ent["state"]):
                    retired.add(id_)
        for id_, refs in sorted(self.refs().items()):
            if id_ in self.doc.defs or id_ in already:
                continue
            for r in refs:
                if id_ in retired and HISTORY_SECTION_RE.search(r.section):
                    continue
                self.err("CHK-24", self.loc(r.file, r.line), f"{id_} を参照していますが、要求定義書に定義がありません（参照先がない）")
        cat = h.mf(self.cfg, "catalog")
        for kind, t in self.cat_tables:
            if kind == "feature":
                continue  # CHK-07
            for ln, cells in t.rows:
                for m in h.ID_RE.finditer(" ".join(cells)):
                    id_ = m.group(0)
                    if id_ not in self.doc.defs:
                        self.err("CHK-24", self.loc(cat, ln), f"カタログの「{t.heading or kind}」の行が、要求定義書にない {id_} を参照しています")
                        continue
                    req = self.doc.requirements.get(id_)
                    if req is not None and not req.active:
                        self.warn("CHK-24", self.loc(cat, ln), f"カタログの「{t.heading or kind}」の行が {req.state} の {id_} を参照しています。参照を外すか、資産ごと取り除きます")

    # ------------------------------------------------------------------ CHK-25
    def chk25(self) -> None:
        """Structured fields must point to definitions: 対象エンティティ → 用語・状態の表, 関係する状態 → 状態の表,
        参照パラメータ ⇔ {PARAM-xxx} used in the requirement and its ACs."""
        known = set(self.doc.glossary) | set(self.doc.entities)
        for r in self.doc.requirements.values():
            if not r.active:
                continue
            loc = self.loc(r.file, r.line)
            ents = h.split_values(r.fields.get("対象エンティティ", ""))
            for e in ents:
                if e not in known:
                    self.err("CHK-25", loc, f"{r.id} の対象エンティティ「{e}」が用語の表にも状態の表にもありません（用語の表か状態の表に定義します）")
            states = h.split_values(r.fields.get("関係する状態", ""), states=True)
            if states:
                with_states = [e for e in ents if e in self.doc.entities]
                if not with_states:
                    self.err("CHK-25", loc, f"{r.id} の関係する状態（{'、'.join(states)}）を持つ対象エンティティ（{'、'.join(ents) or 'なし'}）が状態の表にありません")
                else:
                    defined: Set[str] = set()
                    for e in with_states:
                        defined |= self.doc.entities[e]["states"]  # type: ignore[operator]
                    for s in states:
                        if s not in defined:
                            self.err("CHK-25", loc, f"{r.id} の関係する状態「{s}」が状態の表（{'、'.join(with_states)}）にありません")
            # FR-1020 AC-152: optional fields (usage of entities / scenarios) (absent = valid)
            for problem in ent.optional_field_problems(self.doc, r):
                self.err("CHK-25", loc, f"{r.id} の{problem}")
            listed = set(re.findall(r"PARAM-\d{3,}", r.fields.get("参照パラメータ", "")))
            text = " ".join(r.body) + " " + " ".join(self.doc.acs[a].full_text() for a in r.acs if a in self.doc.acs)
            used = set(h.PARAM_REF_RE.findall(text))
            for p in sorted(used - listed):
                self.err("CHK-25", loc, f"{r.id} の本文・受入基準が {{{p}}} を使っていますが、参照パラメータの欄にありません")
            for p in sorted(listed - used):
                self.warn("CHK-25", loc, f"{r.id} の参照パラメータ {p} が本文・受入基準で {{{p}}} として使われていません")
        # FR-1025 AC-170: the optional column definitions of the catalog (absent = valid)
        for f, ln, msg in ent.column_problems(self.doc, self.root, self.cfg):
            self.err("CHK-25", self.loc(f, ln), msg)

    # ------------------------------------------------------------------ CHK-26
    def chk26(self) -> None:
        """Definitions that nothing refers to (orphans): PARAM, SRC, entities of the state table."""
        refs = self.refs()
        for pid, p in self.doc.params.items():
            if not refs.get(pid):
                self.warn("CHK-26", self.loc(p["file"], p["line"]), f"{pid} はどの要求・受入基準からも参照されていません（不要なら廃止します）")
        for sid in self.doc.kind_ids("SRC"):
            if not refs.get(sid):
                d = self.doc.defs[sid][0]
                self.warn("CHK-26", self.loc(d.file, d.line), f"{sid} はどの要求・ペルソナからも出典として参照されていません")
        used_ents: Set[str] = set()
        for r in self.doc.requirements.values():
            if r.active:
                used_ents.update(h.split_values(r.fields.get("対象エンティティ", "")))
        for e, info in self.doc.entities.items():
            if e not in used_ents:
                self.warn("CHK-26", self.loc(str(info["file"]), info["line"]), f"状態の表の「{e}」を対象エンティティにする要求がありません")

    # ------------------------------------------------------------------ CHK-27
    def catalog_names(self) -> Dict[str, Dict[str, int]]:
        col = {"part": "部品名", "api": "名前", "table": "テーブル名"}
        out: Dict[str, Dict[str, int]] = {"part": {}, "api": {}, "table": {}}
        for kind, t in self.cat_tables:
            c = t.col(col[kind]) if kind in col else None
            if c is None:
                continue
            for ln, cells in t.rows:
                n = h.strip_md(cells[c]) if c < len(cells) else ""
                if n and n not in h.NONE_VALUES:
                    out[kind].setdefault(n, ln)
        return out

    def chk27(self) -> None:
        """Catalog tables are linked both ways: 機能の表「使っている共通部品」⇔ 共通部品の表「使っている要求 ID」,
        and 関連する既存資産 of a requirement must exist in the catalog."""
        if not self.cat_exists:
            return
        cat = h.mf(self.cfg, "catalog")
        col = {"part": "部品名", "api": "名前", "table": "テーブル名"}
        label = {"part": "共通部品", "api": "API・イベント", "table": "テーブル"}
        for kind, t in self.cat_tables:
            c = t.col(col[kind]) if kind in col else None
            if c is None:
                continue
            seen: Dict[str, int] = {}
            for ln, cells in t.rows:
                n = h.strip_md(cells[c]) if c < len(cells) else ""
                if not n or n in h.NONE_VALUES:
                    continue
                if n in seen:
                    self.err("CHK-27", self.loc(cat, ln), f"{label[kind]}の表に「{n}」が重複しています（{seen[n]} 行目）")
                seen.setdefault(n, ln)
        names = self.catalog_names()
        used_by: Dict[str, Set[str]] = {}
        for rid, row in self.cat_req.items():
            for p in h.split_values(h.catalog_cell(row, "共通部品")):
                used_by.setdefault(p, set()).add(rid)
                if p not in names["part"]:
                    self.err("CHK-27", self.loc(cat, row.line), f"{rid} が使っている共通部品「{p}」が共通部品の表にありません")
        for kind, t in self.cat_tables:
            if kind != "part":
                continue
            nc, uc = t.col("部品名"), t.col("要求ID", "要求 ID")
            if nc is None or uc is None:
                continue
            for ln, cells in t.rows:
                n = h.strip_md(cells[nc]) if nc < len(cells) else ""
                if not n or n in h.NONE_VALUES:
                    continue
                declared = set(h.REQ_ID_RE.findall(cells[uc] if uc < len(cells) else ""))
                actual = used_by.get(n, set())
                if declared != actual:
                    self.err("CHK-27", self.loc(cat, ln),
                             f"共通部品「{n}」の使っている要求 ID（{'、'.join(sorted(declared)) or 'なし'}）が機能の表"
                             f"（{'、'.join(sorted(actual)) or 'なし'}）と一致しません（rdfix.py --only catalog --apply で機能の表に合わせます）")
        kind_of = {"共通部品": "part", "API": "api", "イベント": "api", "テーブル": "table"}
        for r in self.doc.requirements.values():
            if not r.active:
                continue
            for m in ASSET_RE.finditer(r.fields.get("関連する既存資産", "")):
                k = kind_of[m.group(1)]
                if m.group(2).strip() not in names[k]:
                    self.err("CHK-27", self.loc(r.file, r.line),
                             f"{r.id} の関連する既存資産 {m.group(1)}「{m.group(2)}」がカタログの{label[k]}の表にありません")


    # ------------------------------------------------------------------ CHK-28 (FR-1035 / FR-1036)
    def chk28(self) -> None:
        """外部連携カタログ（任意）の形式・ID・観点の欄・秘密値・要求との対応。カタログがなければ何も報告しない。"""
        cat = self.integ
        # 要求定義書から INT-xxx への参照（カタログの有無にかかわらず、存在しなければ未定義参照）
        ids = cat.by_id() if cat.exists else {}
        for rel, text in self.doc.text.items():
            in_code = False
            for ln, line in enumerate(text.splitlines(), start=1):
                if line.lstrip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                for m in h.INT_ID_RE.finditer(re.sub(r"`[^`]*`", "", line)):
                    if m.group(1) not in ids:
                        self.err("CHK-28", self.loc(rel, ln), f"{m.group(1)} を参照していますが、外部連携カタログ（{cat.file}）に定義がありません（未定義参照）")
        if not cat.exists:
            return
        seen: Dict[str, int] = {}
        reg_path = self.root / h.mf(self.cfg, "id_registry")
        reg = h.parse_registry_text(h.read_text(reg_path)) if reg_path.exists() else None
        for it in cat.items:
            where = self.loc(cat.file, it.line)
            if it.bad_id:
                self.err("CHK-28", where, f"{it.id} は ID の形式（INT-001 のように INT-<3 桁以上の番号>）に合いません。ID は next-id.py INT で採番します")
                continue
            if it.id in seen:
                self.err("CHK-28", where, f"{it.id} が重複して定義されています（{seen[it.id]} 行目）")
                continue
            seen[it.id] = it.line
            if reg is not None:
                ent = reg.get(it.id)
                if ent is None:
                    self.warn("CHK-28", where, f"{it.id} が ID 台帳にありません。ID は scripts/next-id.py INT でだけ採番します（G-3）")
                elif re.search(r"削除済み|欠番", ent["state"]):
                    self.err("CHK-28", where, f"{it.id} は ID 台帳で「{ent['state']}」です。廃止・削除した ID は再利用しません")
            if not it.name:
                self.err("CHK-28", where, f"{it.id} の名前（見出しの ID の後ろ）がありません（AC-208）")
            for key, ln in it.dup_fields:
                self.err("CHK-28", self.loc(cat.file, ln), f"{it.id} の欄「{key}」が重複しています")
            for key in it.fields:
                if key not in h.INT_REQUIRED + h.INT_PERSPECTIVES + h.INT_OPTIONAL and h.INT_SECRET_FIELD_RE.search(key):
                    self.err("CHK-28", self.loc(cat.file, it.field_lines[key]),
                             f"{it.id} に認証情報の値を書く欄「{key}」があります。方式の名前と秘密の保管場所の名前だけを書きます（AC-209）")
            for key in h.INT_REQUIRED:
                if key not in it.fields or not it.get(key):
                    self.err("CHK-28", where, f"{it.id} の必須欄「{key}」がありません（AC-208）")
            for key in h.INT_PERSPECTIVES:
                if key not in it.fields:
                    self.err("CHK-28", where, f"{it.id} の観点の欄「{key}」がありません（値・なし・TBD（Q-xxx）のどれかで埋めます。FR-1038）")
            for key, raw in it.fields.items():
                ln = self.loc(cat.file, it.field_lines[key])
                val = h.strip_md(raw)
                if not val:
                    if key in h.INT_PERSPECTIVES:
                        self.err("CHK-28", ln, f"{it.id} の「{key}」が空です（値・なし・TBD（Q-xxx）のどれかで埋めます）")
                    continue
                if key in h.INT_PERSPECTIVES + h.INT_REQUIRED and (val in h.INT_BAD_PLACEHOLDERS or val.upper().startswith("TBD")):
                    m = h.INT_TBD_RE.match(val)
                    if not m:
                        self.err("CHK-28", ln, f"{it.id} の「{key}」の値「{val}」は 値／なし／TBD（Q-xxx）の形式ではありません")
                    elif m.group(1) not in self.doc.defs:
                        self.err("CHK-28", ln, f"{it.id} の「{key}」の TBD が指す {m.group(1)} が質問票にありません")
                    elif key == "状態":
                        self.err("CHK-28", ln, f"{it.id} の状態に TBD は書けません（{'／'.join(h.INT_STATES)}）")
                for rx in h.INT_SECRET_VALUE_RES:
                    sm = rx.search(re.sub(r"`", "", val))
                    if sm:
                        self.err("CHK-28", ln, f"{it.id} の「{key}」に認証情報の値らしい文字列があります。値は書かず、方式の名前と秘密の保管場所の名前だけを書きます（AC-209）")
                        break
            direction = it.get("方向")
            if direction and direction not in h.INT_DIRECTIONS and not h.INT_TBD_RE.match(direction) \
                    and direction not in h.INT_BAD_PLACEHOLDERS and not direction.upper().startswith("TBD"):
                self.err("CHK-28", self.loc(cat.file, it.field_lines["方向"]), f"{it.id} の方向「{direction}」は {'／'.join(h.INT_DIRECTIONS)} のどれでもありません")
            state = it.get("状態")
            if state and state not in h.INT_STATES and not state.upper().startswith("TBD") and state not in h.INT_BAD_PLACEHOLDERS:
                self.err("CHK-28", self.loc(cat.file, it.field_lines["状態"]), f"{it.id} の状態「{state}」は {'／'.join(h.INT_STATES)} のどれでもありません")
            rel_cell = it.get("関連する要求")
            if rel_cell and "関連する要求" in it.fields:
                rids = h.REQ_ID_RE.findall(rel_cell)
                tbd = h.INT_TBD_RE.match(rel_cell)
                if not rids and not tbd:
                    self.err("CHK-28", self.loc(cat.file, it.field_lines["関連する要求"]),
                             f"{it.id} の関連する要求に要求 ID（FR-xxx／NFR-xxx-xxx）がありません（AC-208）")
                for rid in rids:
                    if rid not in self.doc.requirements:
                        self.err("CHK-28", self.loc(cat.file, it.field_lines["関連する要求"]), f"{it.id} の関連する要求 {rid} が要求定義書にありません")
                if state == "運用中" and rids:
                    bad = [r for r in rids if r in self.doc.requirements and self.doc.requirements[r].state != "承認済み"]
                    if bad:
                        self.warn("CHK-28", where, f"{it.id} は運用中ですが、関連する要求 {'、'.join(bad)} が承認済みではありません")
        listed = {h.strip_md(c) for _, header, cells in cat.index_rows for c in cells[:1] if h.INT_ID_RE.fullmatch(h.strip_md(c))}
        for ln, header, cells in cat.index_rows:
            iid = h.strip_md(cells[0]) if cells else ""
            if iid and h.INT_ID_RE.fullmatch(iid) and iid not in ids:
                self.warn("CHK-28", self.loc(cat.file, ln), f"索引表の {iid} に対応する項目（#### {iid} …）がありません")
        for iid, it in ids.items():
            if cat.index_rows and iid not in listed:
                self.warn("CHK-28", self.loc(cat.file, it.line), f"{it.id} が索引表にありません")

    # ------------------------------------------------------------------ FR-1057/1058: areas and metadata
    def rd_tables(self):
        if getattr(self, "_rd_tables", None) is None:
            out = []
            for rel, text in self.doc.text.items():
                for t in h.parse_tables(text.splitlines()):
                    out.append((rel, t))
            self._rd_tables = out
        return self._rd_tables

    def area_table(self) -> Dict[str, tuple]:
        """領域の一覧表（領域名・上位 G-ID・含む要求数）-> {領域名: (file, line, G-ID cell, count cell)}"""
        out: Dict[str, tuple] = {}
        for rel, t in self.rd_tables():
            c_name, c_g, c_n = t.col("領域名"), t.col("上位"), t.col("要求数")
            if c_name is None or c_g is None:
                continue
            for ln, cells in t.rows:
                if c_name < len(cells) and h.strip_md(cells[c_name]):
                    out.setdefault(h.strip_md(cells[c_name]), (rel, ln, cells[c_g] if c_g < len(cells) else "",
                                                               cells[c_n] if c_n is not None and c_n < len(cells) else ""))
        return out

    def area_assignment(self) -> Optional[Dict[str, tuple]]:
        """決定記録の領域の割り当て表（要求 ID・領域）-> {要求 ID: (file, line, 領域)}。表がなければ None（FR-1060 の承認前）。"""
        found: Optional[Dict[str, tuple]] = None
        for rel, t in self.rd_tables():
            if t.col("領域名") is not None:
                continue
            c_id, c_a = t.col("要求 ID", "要求ID"), t.col("領域")
            if c_id is None or c_a is None:
                continue
            found = found if found is not None else {}
            for ln, cells in t.rows:
                m = h.REQ_ID_RE.search(cells[c_id]) if c_id < len(cells) else None
                if m and c_a < len(cells):
                    found.setdefault(m.group(1), (rel, ln, h.strip_md(cells[c_a])))
        return found

    # CHK-29 (FR-1058 AC-318/320): metadata definition (scripts/metadata.json)
    def chk29(self) -> None:
        defs = h.requirement_field_defs()
        if not defs:
            return
        for r in self.doc.requirements.values():
            for k, v in r.fields.items():
                loc = self.loc(r.file, r.field_lines.get(k, r.line))
                d = defs.get(k)
                if d is None:
                    self.err("CHK-29", loc, f"{r.id} の欄「{k}」がメタデータ定義（scripts/metadata.json）にありません")
                    continue
                pat = d.get("pattern")
                val = v.strip()
                if pat and val and not re.search(pat, val):
                    self.err("CHK-29", loc, f"{r.id} の欄「{k}」の値「{val[:30]}」が許容値（{d.get('type', pat)}）の形式に合いません")

    # CHK-30 (FR-1057 AC-315..317, FR-1060 AC-326): areas
    def chk30(self) -> None:
        areas = self.area_table()
        assign = self.area_assignment()
        reqs = [r for r in self.doc.requirements.values() if r.state != "廃止"]
        for r in reqs:
            a = r.area
            if a and areas and a not in areas:
                self.err("CHK-30", self.loc(r.file, r.field_lines.get("領域", r.line)),
                         f"{r.id} の領域「{a}」が領域の一覧表にありません")
        for name, (rel, ln, g, n) in areas.items():
            gids = re.findall(r"G-\d{3,}", g)
            if not gids or any(x not in self.doc.defs for x in gids):
                self.err("CHK-30", self.loc(rel, ln), f"領域「{name}」の上位 G-ID（{g or '空'}）が目的にありません")
            cnt = sum(1 for r in reqs if r.area == name)
            nm = re.search(r"\d+", n or "")
            if nm and int(nm.group(0)) != cnt:
                self.warn("CHK-30", self.loc(rel, ln), f"領域「{name}」の含む要求数 {nm.group(0)} が実際の {cnt} 件（廃止を除く）と違います")
        unassigned = [r for r in reqs if not r.area]
        self.area_info = len(unassigned)
        if assign is not None:
            for r in unassigned:
                self.err("CHK-30", self.loc(r.file, r.line), f"{r.id} に領域の欄がありません（領域の割り当て表の承認後は必須）")
            for rid, (rel, ln, a) in assign.items():
                r = self.doc.requirements.get(rid)
                if r is None:
                    self.err("CHK-30", self.loc(rel, ln), f"割り当て表の {rid} が要求定義書にありません")
                elif r.state != "廃止" and r.area and r.area != a:
                    self.err("CHK-30", self.loc(rel, ln), f"{rid} の領域が割り当て表（{a}）と欄の値（{r.area}）で一致しません")
            for r in reqs:
                if r.id not in assign:
                    self.err("CHK-30", self.loc(r.file, r.line), f"{r.id} が領域の割り当て表にありません")
        # catalog sections: 領域: <名> (AC-317)
        for kind, t in self.cat_tables:
            if kind != "feature":
                continue
            m = re.match(r"^領域\s*[:：]\s*(.+)$", t.heading.strip())
            if not m:
                continue
            section = h.strip_md(m.group(1))
            c = t.col("要求 ID", "要求ID")
            for ln, cells in t.rows:
                rm = h.REQ_ID_RE.search(cells[c]) if c is not None and c < len(cells) else None
                r = self.doc.requirements.get(rm.group(1)) if rm else None
                if r is not None and r.area and r.area != section:
                    self.err("CHK-30", self.loc(h.mf(self.cfg, "catalog"), ln),
                             f"{r.id} の領域がカタログの区切り（{section}）と要求定義書（{r.area}）で一致しません")

    # CHK-31 (NFR-UX-014 AC-324): same kind of table, same column names and order
    def chk31(self) -> None:
        first: Dict[str, List[str]] = {}
        for kind, t in self.cat_tables:
            if not kind:
                continue
            norm = [re.sub(r"\s+", "", c) for c in t.header]
            ref = first.setdefault(kind, norm)
            if norm != ref:
                self.warn("CHK-31", self.loc(h.mf(self.cfg, "catalog"), t.header_line),
                          f"表「{t.heading}」の列名・列の順序が、同じ種類の先頭の表（{'|'.join(ref)}）と違います")

    # CHK-32 (NFR-UX-014 AC-323): items directly under one section (PARAM-043)
    def chk32(self) -> None:
        if self.area_assignment() is None:
            return  # 領域化の前の節には警告しない（段階導入）
        meta = h.load_metadata().get("parameters", {})
        limit = int(meta.get("section_item_limit_default", 20))
        p = self.doc.params.get(meta.get("section_item_limit_param", "PARAM-043"))
        if p:
            m = re.search(r"\d+", h.strip_md(p.get("value", "")))
            if m:
                limit = int(m.group(0))
        files = [(rel, text) for rel, text in self.doc.text.items()]
        cat = h.mf(self.cfg, "catalog")
        if self.cat_exists:
            files.append((cat, h.strip_comments(h.read_text(self.root / cat))))
        for rel, text in files:
            lines = text.splitlines()
            stack: List[list] = []  # [level, title, line, count]
            done: List[list] = []
            in_code, i = False, 0
            while i < len(lines):
                line = lines[i]
                if line.lstrip().startswith("```"):
                    in_code = not in_code
                    i += 1
                    continue
                if in_code:
                    i += 1
                    continue
                hm = h.HEADING_RE.match(line)
                if hm:
                    lvl = len(hm.group(1))
                    while stack and stack[-1][0] >= lvl:
                        done.append(stack.pop())
                    if stack:
                        stack[-1][3] += 1
                    stack.append([lvl, hm.group(2), i + 1, 0])
                elif line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
                    j = i + 2
                    while j < len(lines) and lines[j].lstrip().startswith("|"):
                        j += 1
                    if stack:
                        stack[-1][3] += j - (i + 2)
                    i = j
                    continue
                i += 1
            done.extend(stack)
            for lvl, title, ln, n in done:
                if n > limit and re.match(r"^領域\s*[:：]", title.strip()):
                    self.warn("CHK-32", self.loc(rel, ln), f"節「{title}」の直下の項目が {n} 件で、上限 {limit} 件（PARAM-043）を超えています")

# ---------------------------------------------------------------------- commands

def cmd_check(args, root, cfg) -> int:
    base = args.base
    if base is None:
        base = h.default_base(root, cfg)
    elif base == "none":
        base = None
    run_id = args.run
    if run_id == "current":
        run_id = h.current_run(h.conductor_root(root, cfg), cfg)
    ck = Checker(root, cfg, base, run_id, args.strict, True if args.strict_ledger else (False if args.no_strict_ledger else None))
    findings = ck.run_all()
    findings.sort(key=lambda f: (f.level != "ERROR", f.chk, f.loc))
    errors = sum(1 for f in findings if f.level == "ERROR")
    warns = len(findings) - errors
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warns, "findings": [f.__dict__ for f in findings]}, ensure_ascii=False, indent=2))
    else:
        shown = [f for f in findings if f.level == "ERROR" or not args.errors_only]
        for f in shown:
            print(f.line())
        if getattr(ck, "area_info", None) is not None and ck.doc.exists and not args.errors_only:
            if ck.area_assignment() is None:
                print(f"INFO 領域未所属の要求: {ck.area_info} 件（領域の割り当て表の承認まで任意）")
        print(f"rdcheck: errors={errors} warnings={warns} base={base or '-'} run={run_id or '-'}")
    return 1 if errors else 0


def cmd_show(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    rc = 0
    for id_ in args.ids:
        defs = doc.defs.get(id_)
        if not defs:
            print(f"{id_}: 見つかりません")
            rc = 1
            continue
        d = defs[0]
        lines = doc.text[d.file].splitlines()
        start = d.line - 1
        first = lines[start]
        if first.lstrip().startswith("#"):
            lvl = len(first) - len(first.lstrip("#"))
            end = start + 1
            while end < len(lines):
                m = h.HEADING_RE.match(lines[end])
                if m and len(m.group(1)) <= lvl:
                    break
                end += 1
        elif first.lstrip().startswith("|"):
            end = start + 1
            hdr = start
            while hdr > 0 and lines[hdr - 1].lstrip().startswith("|"):
                hdr -= 1
            print(f"# {d.file}:{d.line}")
            print("\n".join(lines[hdr:hdr + 2]))
        else:
            end = start + 1
            indent = len(first) - len(first.lstrip())
            while end < len(lines) and lines[end].strip() and (len(lines[end]) - len(lines[end].lstrip())) > indent:
                end += 1
        if not first.lstrip().startswith("|"):
            print(f"# {d.file}:{d.line}")
        print("\n".join(lines[start:end]).rstrip())
        print()
    return rc


def cmd_list(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    reqs: list = []
    if args.kind == "AC" or args.level:
        for ac in doc.acs.values():
            req = doc.requirements.get(ac.requirement or "")
            if args.level and ac.level != args.level:
                continue
            if args.state and (not req or req.state != args.state):
                continue
            flag = " BLOCKED" if ac.blocked else ""
            print(f"{ac.id}\t{ac.requirement or '-'}\t{ac.level or '-'}{flag}\t{ac.text[:60]}")
        return 0
    for r in doc.requirements.values():
        if args.state and r.state != args.state:
            continue
        if args.priority and r.priority != args.priority.upper():
            continue
        if args.kind and not r.id.startswith(args.kind):
            continue
        reqs.append(r)
    if args.area is not None or args.by_area:
        return _list_by_area(doc, reqs, args.area)
    for r in reqs:
        print(f"{r.id}\t{r.state or '-'}\t{r.priority or '-'}\t{r.title}\tACs={','.join(r.acs) or '-'}")
    return 0


def _list_by_area(doc, reqs, area) -> int:
    """領域別の一覧（FR-1057 AC-316）。廃止の要求は領域の件数に含めず、件数だけ別に示す。"""
    live = [r for r in reqs if r.state != "廃止"]
    abolished = sum(1 for r in reqs if r.state == "廃止")
    if area is not None:
        for r in live:
            if r.area == area:
                print(f"{r.id}\t{r.state or '-'}\t{r.title}")
        if abolished:
            print(f"(廃止は件数に含めません: {sum(1 for r in reqs if r.state == '廃止' and r.area == area)} 件)")
        return 0
    groups: Dict[str, list] = {}
    for r in live:
        groups.setdefault(r.area or "（未所属）", []).append(r)
    for name in sorted(groups, key=lambda n: (n == "（未所属）", n)):
        print(f"## {name}（{len(groups[name])} 件）")
        for r in groups[name]:
            print(f"{r.id}\t{r.state or '-'}\t{r.title}")
    print(f"合計 {len(live)} 件（廃止 {abolished} 件は別）")
    return 0


# ---------------------------------------------------------------------- relation index (FR-1059)

def build_index(ck: "Checker") -> List[tuple]:
    """種類つきの関係の索引（始点 ID・種類・終点 ID）。保存せず、要求定義書・カタログ・台帳の既存の記述から都度生成する。
    上位・出典・参照 = 要求定義書、実装・使用 = カタログ、検証 = 台帳。"""
    out: Set[tuple] = set()
    doc = ck.doc
    for r in doc.requirements.values():
        for g in re.findall(r"G-\d{3,}", r.fields.get("上位", "")):
            out.add((r.id, "上位", g))
        for s in h.split_values(r.fields.get("出典", "")):
            out.add((r.id, "出典", s))
        for p in re.findall(r"PARAM-\d{3,}", r.fields.get("参照パラメータ", "")):
            out.add((r.id, "参照", p))
        for e in h.split_values(r.fields.get("対象エンティティ", "")):
            out.add((r.id, "参照", e))
    for a in doc.acs.values():
        for p in h.PARAM_REF_RE.findall(a.full_text()):
            out.add((a.id, "参照", p))
    for rid, row in ck.cat_req.items():
        for path in h.split_paths(h.catalog_cell(row, "実装ファイル")):
            out.add((rid, "実装", path))
        for part in h.split_values(h.catalog_cell(row, "使っている共通部品")):
            out.add((rid, "使用", part))
    for c in ck.ledger.get("cases", []):
        cid = c.get("id")
        if not cid:
            continue
        for a in c.get("ac_ids", []):
            out.add((cid, "検証", a))
        for rid in c.get("requirement_ids", []):
            out.add((cid, "検証", rid))
    return sorted(out)


def cmd_index(args, root, cfg) -> int:
    ck = Checker(root, cfg, None, None, False, False)
    pairs = build_index(ck)
    if args.ids:
        ids = set(args.ids)
        pairs = [p for p in pairs if p[0] in ids or p[2] in ids]
    if args.kind:
        pairs = [p for p in pairs if p[1] == args.kind]
    if args.json:
        print(json.dumps([{"from": a, "kind": k, "to": b} for a, k, b in pairs], ensure_ascii=False, indent=2))
    else:
        for a, k, b in pairs:
            print(f"{a}\t{k}\t{b}")
    return 0


def cmd_stats(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    ledger = h.load_ledger(root, cfg)
    reqs = list(doc.requirements.values())
    per_goal: Dict[str, int] = {}
    for r in reqs:
        for g in re.findall(r"G-\d{3,}", r.fields.get("上位", "")):
            per_goal[g] = per_goal.get(g, 0) + 1
    must = [r for r in reqs if r.priority == "MUST" and r.active]
    must_cov = sum(1 for r in must if r.acs)
    sys_acs = h.system_acs(doc)
    covered = {a for c in ledger.get("cases", []) for a in c.get("ac_ids", [])}
    sys_cov = sum(1 for a in sys_acs if a.id in covered)
    alltext = "\n".join(doc.text.values())
    stats = {
        "requirements": len(reqs),
        "by_state": {s: sum(1 for r in reqs if r.state == s) for s in h.STATES},
        "per_goal": per_goal,
        "must_ac_coverage": f"{must_cov}/{len(must)}",
        "system_ac_ledger_coverage": f"{sys_cov}/{len(sys_acs)}",
        "acs": len(doc.acs),
        "blocked_acs": sum(1 for a in doc.acs.values() if a.blocked),
        "TBD": len(re.findall(r"\bTBD\b", alltext)),
        "ASSUMPTION": len(re.findall(r"\[ASSUMPTION\]", alltext)),
        "競合": len(re.findall(r"競合", alltext)),
        "open_questions": sum(1 for q in doc.questions.values() if not q["answered"]),
        "ledger": {s: sum(1 for c in ledger.get("cases", []) if c.get("status") == s) for s in ("pass", "fail", "blocked", "not_run")},
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def _code_index(ck: "Checker") -> Dict[str, Set[str]]:
    idx: Dict[str, Set[str]] = {}
    for f in ck.scan_files():
        for id_ in set(h.CODE_ID_RE.findall(ck.read(f))):
            idx.setdefault(id_, set()).add(f)
    return idx


def trace_one(ck: "Checker", key: str, code: Dict[str, Set[str]]) -> dict:
    doc = ck.doc
    refs = ck.refs()
    cases = ck.ledger.get("cases", [])

    def where(id_: str) -> str:
        d = doc.defs.get(id_)
        return f"{d[0].file}:{d[0].line}" if d else "-"

    def referrers(id_: str) -> List[str]:
        return sorted({r.owner or f"{r.file}:{r.line}（{r.section}）" for r in refs.get(id_, [])})

    def cat_assets(rid: str) -> List[str]:
        out = []
        for kind, t in ck.cat_tables:
            if kind in ("api", "table", "part"):
                c = t.col("部品名", "テーブル名", "名前")
                for ln, cells in t.rows:
                    if rid in h.REQ_ID_RE.findall(" ".join(cells)) and c is not None and c < len(cells):
                        out.append(f"{t.heading or kind}「{h.strip_md(cells[c])}」")
        return out

    if key in doc.requirements:
        r = doc.requirements[key]
        row = ck.cat_req.get(key)
        acs = []
        for a in r.acs:
            ac = doc.acs.get(a)
            if not ac:
                continue
            acs.append({
                "id": a, "level": ac.level or "-", "blocked": ac.blocked_ref if ac.blocked else "",
                "cases": [f"{c.get('id')}({c.get('status')})" for c in cases if a in c.get("ac_ids", [])],
                "code": sorted(code.get(a, set())),
            })
        ents = h.split_values(r.fields.get("対象エンティティ", ""))
        return {
            "id": key, "kind": "requirement", "title": r.title, "state": r.state, "priority": r.priority, "at": where(key),
            "upper": [{"id": g, "at": where(g)} for g in re.findall(r"G-\d{3,}", r.fields.get("上位", ""))] or [r.fields.get("上位", "")],
            "source": r.fields.get("出典", "") or r.fields.get("出自", ""),
            "entities": {e: sorted(doc.entities.get(e, {}).get("states", set())) for e in ents},  # type: ignore[arg-type]
            "states": h.split_values(r.fields.get("関係する状態", ""), states=True),
            "params": {p: f"{h.strip_md(doc.params[p]['value'])}{h.strip_md(doc.params[p]['unit'])}" if p in doc.params else "未定義"
                       for p in re.findall(r"PARAM-\d{3,}", r.fields.get("参照パラメータ", ""))},
            "acs": acs,
            "catalog": {k: h.strip_md(v) for k, v in row.cells.items()} if row else None,
            "catalog_assets": cat_assets(key),
            "code": sorted(code.get(key, set())),
            "referenced_by": [x for x in referrers(key) if x != key],
        }
    if key in doc.acs:
        ac = doc.acs[key]
        return {"id": key, "kind": "AC", "at": where(key), "requirement": ac.requirement, "level": ac.level or "-",
                "blocked": ac.blocked_ref if ac.blocked else "",
                "cases": [f"{c.get('id')}({c.get('status')})" for c in cases if key in c.get("ac_ids", [])],
                "code": sorted(code.get(key, set())), "referenced_by": referrers(key)}
    if key.startswith("G-") and key in doc.defs:
        reqs = [r.id for r in doc.requirements.values() if key in re.findall(r"G-\d{3,}", r.fields.get("上位", ""))]
        return {"id": key, "kind": "goal", "at": where(key), "requirements": reqs, "referenced_by": referrers(key)}
    if h.INT_ID_RE.fullmatch(key):
        it = ck.integ.by_id().get(key) if ck.integ.exists else None
        if it is None:
            return {"id": key, "kind": "not_found"}
        mention_owners: Set[str] = set()
        for rel, text in doc.text.items():
            owner, owner_lvl, in_code = "", 0, False
            for line in text.splitlines():
                if line.lstrip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
                hm = h.HEADING_RE.match(line)
                if hm:
                    rm = h.REQ_HEADING_RE.match(line)
                    if rm:
                        owner, owner_lvl = rm.group(2), len(hm.group(1))
                    elif owner and len(hm.group(1)) <= owner_lvl:
                        owner = ""
                if owner and key in h.INT_ID_RE.findall(re.sub(r"`[^`]*`", "", line)):
                    mention_owners.add(owner)
        related = set(h.REQ_ID_RE.findall(it.get("関連する要求"))) | mention_owners
        reqs = sorted(r for r in related if r in doc.requirements)
        acs = sorted({a for r in reqs for a in doc.requirements[r].acs})
        return {"id": key, "kind": "外部連携", "title": it.name, "at": f"{it.file}:{it.line}",
                "direction": it.get("方向"), "integration_state": it.get("状態"), "counterparty": it.get("連携先"),
                "requirements": [f"{r}（{doc.requirements[r].state}）" for r in reqs],
                "acs": acs and [{"id": a, "level": doc.acs[a].level or "-", "cases": [], "code": [], "blocked": ""} for a in acs if a in doc.acs]}
    if key in doc.defs:
        return {"id": key, "kind": h.id_kind(key) or "id", "at": where(key), "referenced_by": referrers(key)}
    if key in doc.entities or key in doc.glossary:
        reqs = [r.id for r in doc.requirements.values() if key in h.split_values(r.fields.get("対象エンティティ", ""))]
        info = doc.entities.get(key)
        return {"id": key, "kind": "entity", "states": sorted(info["states"]) if info else [],  # type: ignore[arg-type]
                "at": f"{info['file']}:{info['line']}" if info else "{}:{}".format(*doc.glossary[key]), "requirements": reqs}
    names = ck.catalog_names()
    for kind, label in (("part", "共通部品"), ("api", "API・イベント"), ("table", "テーブル")):
        if key in names[kind]:
            reqs = sorted(rid for rid, row in ck.cat_req.items() if key in h.split_values(h.catalog_cell(row, "共通部品"))) if kind == "part" else []
            for k2, t in ck.cat_tables:
                if k2 == kind:
                    for ln, cells in t.rows:
                        if ln == names[kind][key]:
                            reqs = sorted(set(reqs) | set(h.REQ_ID_RE.findall(" ".join(cells))))
            return {"id": key, "kind": label, "at": f"{h.mf(ck.cfg, 'catalog')}:{names[kind][key]}", "requirements": reqs}
    return {"id": key, "kind": "not_found"}


def _print_trace(t: dict) -> None:
    if t["kind"] == "not_found":
        print(f"{t['id']}: 見つかりません")
        return
    head = f"{t['id']} [{t['kind']}]"
    if t["kind"] == "requirement":
        head += f" {t['title']}（{t['state'] or '-'}・{t['priority'] or '-'}）"
    print(f"{head}  {t.get('at', '-')}")
    for k, v in t.items():
        if k in ("id", "kind", "title", "state", "priority", "at") or v in (None, "", [], {}):
            continue
        if k == "acs":
            print("  acs:")
            for a in v:
                extra = f" BLOCKED: {a['blocked']}" if a["blocked"] else ""
                print(f"    {a['id']} [{a['level']}]{extra} cases={','.join(a['cases']) or '-'} code={','.join(a['code']) or '-'}")
        elif isinstance(v, dict):
            print(f"  {k}: " + "　".join(f"{a}={'/'.join(b) if isinstance(b, list) else b}" for a, b in v.items()))
        elif isinstance(v, list):
            print(f"  {k}: " + ", ".join(x if isinstance(x, str) else f"{x['id']}({x['at']})" for x in v))
        else:
            print(f"  {k}: {v}")
    print()


def cmd_trace(args, root, cfg) -> int:
    ck = Checker(root, cfg, None, None, False, False)
    code = _code_index(ck)
    out = [trace_one(ck, k, code) for k in args.ids]
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for t in out:
            _print_trace(t)
    return 1 if any(t["kind"] == "not_found" for t in out) else 0


def cmd_digest(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    ids = args.ids or sorted(doc.acs)
    for a in ids:
        ac = doc.acs.get(a)
        print(f"{a}\t{h.ac_digest(ac, doc.params) if ac else 'NOT_FOUND'}")
    return 0


def cmd_hierarchy(args, root, cfg) -> int:
    """FR-1062: 種類→区分→領域→項目の階層。導出の実体は EABK-Studio/eabk_model.py（1 か所）。都度生成し、保存しない。"""
    studio = Path(__file__).resolve().parent.parent / "EABK-Studio"
    if not (studio / "eabk_model.py").is_file():
        studio = root / "EABK-Studio"
    sys.path.insert(0, str(studio))
    sd = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import eabk_model
        hier = eabk_model.build_model(root)["hierarchy"]
    finally:
        sys.dont_write_bytecode = sd
    if args.json:
        print(json.dumps(hier, ensure_ascii=False, indent=2))
    else:
        for t in hier["tiers"]:
            print(f"{' > '.join(t['path'])}\t{t['count']}")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--base", default=None, help="比較の基準（既定: main との merge-base。'none' で比較しない）")
    c.add_argument("--run", default=None, help="CHK-21 を行う run-id（'current' 可）")
    c.add_argument("--strict", action="store_true", help="warn の一部を error にする（最終・統合時）")
    c.add_argument("--strict-ledger", action="store_true", help="CHK-10/11 の不足を error にする（工程 4 以降）")
    c.add_argument("--no-strict-ledger", action="store_true")
    c.add_argument("--errors-only", action="store_true")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("ids", nargs="+")
    l = sub.add_parser("list")
    l.add_argument("--state")
    l.add_argument("--level")
    l.add_argument("--priority")
    l.add_argument("--kind")
    l.add_argument("--area", default=None, help="領域で絞り込む（廃止は含めない）")
    l.add_argument("--by-area", action="store_true", help="領域ごとにまとめて表示する")
    ix = sub.add_parser("index", help="種類つきの関係の索引（要求定義書・カタログ・台帳から都度生成。保存しない）")
    ix.add_argument("ids", nargs="*", help="指定した ID が始点か終点の組だけ表示（逆引き）")
    ix.add_argument("--kind", choices=["上位", "出典", "参照", "実装", "検証", "使用"])
    ix.add_argument("--json", action="store_true")
    sub.add_parser("stats")
    d = sub.add_parser("digest")
    d.add_argument("ids", nargs="*")
    tr = sub.add_parser("trace")
    tr.add_argument("ids", nargs="+")
    tr.add_argument("--json", action="store_true")
    hi = sub.add_parser("hierarchy", help="種類→区分→領域→項目の階層（FR-1062。都度生成。保存しない）")
    hi.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    return {"check": cmd_check, "show": cmd_show, "list": cmd_list, "stats": cmd_stats, "digest": cmd_digest,
            "trace": cmd_trace, "index": cmd_index, "hierarchy": cmd_hierarchy}[args.cmd](args, root, cfg)


if __name__ == "__main__":
    sys.exit(main())
