#!/usr/bin/env python3
"""rdcheck.py - parse and check the management data (plan §10, CHK-01..23).

Usage:
  python scripts/rdcheck.py check [--base REF] [--run RUN_ID] [--strict] [--strict-ledger] [--json]
  python scripts/rdcheck.py show ID [ID ...]        # print only the requirement / AC block (token saving)
  python scripts/rdcheck.py list [--state 承認済み] [--level system] [--priority MUST] [--kind FR]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402


@dataclass
class Finding:
    level: str
    chk: str
    loc: str
    msg: str

    def line(self) -> str:
        return f"{self.level} {self.chk} {self.loc} {self.msg}"


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
        self._files: Optional[List[str]] = None
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
                   self.chk18, self.chk19, self.chk20, self.chk21, self.chk23):
            fn()
        return self.findings

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
        for rid, row in self.cat_req.items():
            req = self.doc.requirements.get(rid)
            if req is None:
                self.err("CHK-07", self.loc(cat, row.line), f"カタログの {rid} が要求定義書にありません")
                continue
            cstate = h.normalize_state(h.catalog_cell(row, "決定状態"))
            if cstate != req.state:
                self.err("CHK-07", self.loc(cat, row.line), f"{rid} の決定状態が一致しません（カタログ={cstate or '空'}、要求定義書={req.state or '空'}）")
        files = set(self.files())
        for ln, p in self.cat_refs:
            rel = p.lstrip("./")
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
            missing = [k for k in ("要求", "決定状態", "優先度", "上位", "対象エンティティ", "関係する状態", "参照パラメータ") if k not in r.fields]
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
        rc, out = h.git(["ls-files"], self.root)
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
        print(f"{r.id}\t{r.state or '-'}\t{r.priority or '-'}\t{r.title}\tACs={','.join(r.acs) or '-'}")
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


def cmd_digest(args, root, cfg) -> int:
    doc = h.parse_requirements(root, cfg)
    ids = args.ids or sorted(doc.acs)
    for a in ids:
        ac = doc.acs.get(a)
        print(f"{a}\t{h.ac_digest(ac, doc.params) if ac else 'NOT_FOUND'}")
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
    sub.add_parser("stats")
    d = sub.add_parser("digest")
    d.add_argument("ids", nargs="*")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    return {"check": cmd_check, "show": cmd_show, "list": cmd_list, "stats": cmd_stats, "digest": cmd_digest}[args.cmd](args, root, cfg)


if __name__ == "__main__":
    sys.exit(main())
