#!/usr/bin/env python3
"""entities.py - entity ledger derived from the management data, and reconciliation with an enterprise data catalog
(FR-1020, FR-1023, FR-1024, NFR-COMPAT-003, NFR-SEC-023).

Usage:
  python scripts/entities.py list  [--repo DIR] [--json]   # entity ledger (FR-1020)
  python scripts/entities.py check [--repo DIR] [--json] [--strict]   # reconcile with the enterprise data catalog (FR-1023)
  python scripts/entities.py todo  [--repo DIR] [--json]   # entities not covered, as question-sheet rows (FR-1024)

The ledger is derived from what the management data already has; no entity file or table is created:
  * names        = union of 用語表 (3.3), 状態表 (3.4) and every active requirement's 対象エンティティ
  * description  = the 定義 cell of the 用語表
  * tables       = rows of the catalog's テーブル表 (a table is linked to an entity only when that entity is a
                   target of every requirement the table relates to, or when the table name / definition file
                   contains the entity name; nothing is guessed otherwise)
  * use cases    = requirement IDs that target the entity, with the optional fields
                   `エンティティの使い方: 注文（作成）、顧客（参照/更新）` (作成・参照・更新・削除) and
                   `利用シナリオ: 1、2` (numbers of the numbered list in section 5)
Optional setting in scripts/ebak.config.json (the enterprise data catalog; absent or "利用しない" = not used: no check, no ToDo):
  "enterprise_data_catalog": {"source": "<file path or http(s) URL>", "name_column": "<column / key of the entity name>"}
The source is read only (never written, never cached; the body is not copied: only names and positions are shown).
URLs: http / https only, no credentials in the URL, at most PARAM-016 seconds (default 10).

Exit code: 0 (also for differences and 照合不能); with `check --strict`, 1 when there are differences or the source is
unusable; 2 for a usage error.  The commands never write to the target repository.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.dont_write_bytecode = True  # read-only: leave no __pycache__ in the target repository
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

USAGE_WORDS = ("作成", "参照", "更新", "削除")
USAGE_FIELD = "エンティティの使い方"
SCENARIO_FIELD = "利用シナリオ"
RELATION_FIELD = "エンティティの関係"
RELATION_KINDS = ("参照", "外部キー")
KEY_WORDS = ("主キー", "外部キー", "なし")
COLUMN_HEAD_RE = re.compile(r"^#{2,6}\s+列\s*[:：]\s*(.+?)\s*#*\s*$")
DEFAULT_THRESHOLD = 0.8
DEFAULT_TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024
NAME_KEYS = ("エンティティ名", "entity_name", "entityname", "エンティティ", "entity", "名称", "テーブル名", "table_name",
             "table", "用語", "名前", "name")

R_UNCHECKED = "企業カタログ未確認"
OPT_OUT = "利用しない"  # explicit opt-out value of enterprise_data_catalog (FR-1023)
R_MISSING = "企業カタログになし"
R_CONFIRM = "名称の確認"


# --------------------------------------------------------------------------- optional fields (shared with rdcheck)

def split_top(value: str) -> List[str]:
    """Split on 、,，;； outside parentheses."""
    out, cur, depth = [], "", 0
    for ch in value:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if depth == 0 and ch in "、,，;；":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [p.strip() for p in out if p.strip()]


def parse_usage_field(value: str) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """`注文（作成）、顧客（参照/更新）` -> ([(entity, [usage...])], [problem...]).  Words other than 作成・参照・更新・削除
    are returned as they are so that the caller can report them."""
    items: List[Tuple[str, List[str]]] = []
    problems: List[str] = []
    for tok in split_top(h.strip_md(value)):
        if tok in h.NONE_VALUES:
            continue
        m = re.fullmatch(r"(.+?)\s*[（(](.*)[）)]", tok)
        if not m:
            problems.append(f"「{tok}」は 名前（使い方） の書式ではありません")
            continue
        usages = [u.strip() for u in re.split(r"[/／・,，]", m.group(2)) if u.strip()]
        if not usages:
            problems.append(f"「{tok}」に使い方がありません")
            continue
        items.append((m.group(1).strip().strip("「」"), usages))
    return items, problems


def parse_scenario_field(value: str) -> Tuple[List[int], List[str]]:
    nums: List[int] = []
    bad: List[str] = []
    for tok in split_top(h.strip_md(value)):
        if tok in h.NONE_VALUES:
            continue
        if re.fullmatch(r"\d+", tok):
            nums.append(int(tok))
        else:
            bad.append(tok)
    return nums, bad


def scenario_items(doc: "h.RequirementsDoc") -> Dict[int, str]:
    """Numbered items under the heading 「利用シナリオ」 (section 5): number -> text."""
    out: Dict[int, str] = {}
    for text in doc.text.values():
        in_sec, level, in_code = False, 0, False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            hm = h.HEADING_RE.match(line)
            if hm:
                lv = len(hm.group(1))
                if "利用シナリオ" in hm.group(2):
                    in_sec, level = True, lv
                elif in_sec and lv <= level:
                    in_sec = False
                continue
            if in_sec:
                m = re.match(r"^\s*(\d+)[.．)）]\s*(.*)$", line)
                if m:
                    out.setdefault(int(m.group(1)), m.group(2).strip())
    return out


def defined_entity_names(doc: "h.RequirementsDoc") -> set:
    return set(doc.glossary) | set(doc.entities)


def optional_field_problems(doc: "h.RequirementsDoc", req: "h.Requirement") -> List[str]:
    """Reasons why the optional fields of a requirement are invalid (AC-152).  Empty when absent or valid."""
    out: List[str] = []
    known = defined_entity_names(doc)
    if USAGE_FIELD in req.fields:
        items, problems = parse_usage_field(req.fields[USAGE_FIELD])
        out += [f"{USAGE_FIELD}: {p}" for p in problems]
        for name, usages in items:
            if name not in known:
                out.append(f"{USAGE_FIELD}: エンティティ「{name}」が用語の表にも状態の表にもありません")
            for u in usages:
                if u not in USAGE_WORDS:
                    out.append(f"{USAGE_FIELD}: 使い方「{u}」は {'・'.join(USAGE_WORDS)} のいずれかにします（{name}）")
    if SCENARIO_FIELD in req.fields:
        nums, bad = scenario_items_check(doc, req.fields[SCENARIO_FIELD])
        out += [f"{SCENARIO_FIELD}: {p}" for p in bad]
    if RELATION_FIELD in req.fields:  # FR-1026 AC-172
        rels, problems = parse_relation_field(req.fields[RELATION_FIELD])
        out += [f"{RELATION_FIELD}: {p}" for p in problems]
        for a, b, k in rels:
            for n in (a, b):
                if n not in known:
                    out.append(f"{RELATION_FIELD}: エンティティ「{n}」が用語の表にも状態の表にもありません")
            if k not in RELATION_KINDS:
                out.append(f"{RELATION_FIELD}: 種別「{k}」は {'・'.join(RELATION_KINDS)} のいずれかにします（{a}→{b}）")
    return out


# --------------------------------------------------------------------------- relations and columns (FR-1025, FR-1026, FR-1030)

def parse_relation_field(value: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """`注文→商品（参照）、注文→顧客（外部キー）` -> ([(from, to, kind)], [problem...])."""
    items: List[Tuple[str, str, str]] = []
    problems: List[str] = []
    for tok in split_top(h.strip_md(value)):
        if tok in h.NONE_VALUES:
            continue
        m = re.fullmatch(r"(.+?)\s*(?:→|⇒|->)\s*(.+?)\s*[（(](.*)[）)]", tok)
        if m:
            items.append((m.group(1).strip().strip("「」"), m.group(2).strip().strip("「」"), m.group(3).strip()))
        elif re.fullmatch(r".+?\s*(?:→|⇒|->)\s*.+", tok):
            problems.append(f"「{tok}」に種別がありません（{'・'.join(RELATION_KINDS)}）")
        else:
            problems.append(f"「{tok}」は 注文→商品（参照） の書式ではありません")
    return items, problems


def parse_ref(ref: str) -> Optional[Tuple[str, str]]:
    m = re.fullmatch(r"(.+)\.([^.]+)", (ref or "").strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def catalog_columns(root: Path, cfg: dict) -> List[dict]:
    """`### 列: <table>` sections of the catalog (optional): [{table, entity, file, line, rows, problems}]."""
    rel = h.mf(cfg, "catalog")
    path = root / rel
    out: List[dict] = []
    if not path.is_file():
        return out
    lines = h.strip_comments(h.read_text(path)).splitlines()
    cur: Optional[dict] = None
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if h.HEADING_RE.match(line):
            m = COLUMN_HEAD_RE.match(line)
            cur = {"table": h.strip_md(m.group(1)), "entity": "", "file": rel, "line": i, "body": [], "rows": [], "problems": []} if m else None
            if cur:
                out.append(cur)
            continue
        if cur is None:
            continue
        em = re.match(r"^\s*\**対象エンティティ\**\s*[:：]\s*(.*)$", line)
        if em:
            cur["entity"] = h.strip_md(em.group(1))
            continue
        cur["body"].append((i, line))
    for sec in out:
        tabs = [t for t in h.parse_tables([l for _, l in sec["body"]]) if t.col("列名") is not None]
        if not tabs:
            sec["problems"].append((sec["line"], f"列「{sec['table']}」の節に 列名・型・キー・参照先・説明 の表がありません"))
            continue
        t = tabs[0]
        ix = [t.col(n) for n in ("列名", "型", "キー", "参照先", "説明")]
        for rel_ln, cells in t.rows:
            ln = sec["body"][rel_ln - 1][0]
            get = lambda k: h.strip_md(cells[ix[k]]) if ix[k] is not None and ix[k] < len(cells) else ""  # noqa: E731
            if not get(0):
                continue
            sec["rows"].append({"name": get(0), "type": get(1), "key": get(2), "ref": get(3), "description": get(4), "line": ln})
    return out


def _by_req(doc: "h.RequirementsDoc") -> Dict[str, List[str]]:
    return {r.id: h.split_values(r.fields.get("対象エンティティ", "")) for r in doc.requirements.values() if r.active}


def _linked_tables(name: str, tables: List[dict], by_req: Dict[str, List[str]]) -> List[dict]:
    linked = []
    for t in tables:
        rel = [x for x in t["reqs"] if x in by_req]
        common = None
        for x in rel:
            s = set(by_req[x])
            common = s if common is None else common & s
        by_name = name in t["name"] or name in t["file"]
        if (common is not None and name in common) or by_name:
            linked.append({"name": t["name"], "file": t["file"]})
    return linked


# --- DDL / JSON Schema supplement (FR-1030): read-only, no network, nothing is guessed
SKIP_DIRS = {"node_modules", "work", "vendor", "__pycache__", "venv", "dist", "build", "bin", "obj", "site-packages"}
MAX_SCHEMA_FILES = 300
MAX_SCHEMA_BYTES = 1024 * 1024
CREATE_RE = re.compile(r"create\s+(?:or\s+replace\s+)?(?:(?:global\s+|local\s+)?temp(?:orary)?\s+)?table\s+(?:if\s+not\s+exists\s+)?([`\"\[]?[\w.\"`\[\]]+)\s*\(", re.I)


def _unq(s: str) -> str:
    return s.strip().strip('`"[]').strip()


def _tail(s: str) -> str:
    return _unq(s.split(".")[-1]) if s else s


def _split_top_commas(s: str) -> List[Tuple[str, int]]:
    out, cur, depth, start = [], "", 0, 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append((cur, start))
            cur, start = "", i + 1
        else:
            cur += ch
    out.append((cur, start))
    return out


def parse_ddl(text: str, rel: str) -> Tuple[List[dict], List[dict]]:
    """CREATE TABLE statements -> ([{table, columns:[{name,type,key,ref,line}]}], [{file,line,reason}])."""
    tables: List[dict] = []
    diags: List[dict] = []
    clean = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), text)
    clean = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), clean, flags=re.S)
    for m in CREATE_RE.finditer(clean):
        start = m.end()
        depth, i = 1, start
        while i < len(clean) and depth:
            depth += {"(": 1, ")": -1}.get(clean[i], 0)
            i += 1
        base_line = clean.count("\n", 0, m.start()) + 1
        if depth:
            diags.append({"file": rel, "line": base_line, "reason": f"CREATE TABLE {_tail(m.group(1))} の括弧が閉じていないため解析できません"})
            continue
        body = clean[start:i - 1]
        cols: Dict[str, dict] = {}
        order: List[str] = []
        pending: List[Tuple[str, str, str, int]] = []  # (kind, col, ref, line)
        for item, off in _split_top_commas(body):
            s = item.strip()
            if not s:
                continue
            ln = clean.count("\n", 0, start + off + (len(item) - len(item.lstrip()))) + 1
            low = re.sub(r"^constraint\s+\S+\s+", "", s, flags=re.I)
            pk = re.match(r"primary\s+key\s*\(([^)]*)\)", low, re.I)
            fk = re.match(r"foreign\s+key\s*\(([^)]*)\)\s*references\s+([`\"\[\w.\]]+)\s*\(([^)]*)\)", low, re.I)
            if pk:
                for c in pk.group(1).split(","):
                    pending.append(("pk", _unq(c), "", ln))
                continue
            if fk:
                a, b = [_unq(x) for x in fk.group(1).split(",")], [_unq(x) for x in fk.group(3).split(",")]
                if len(a) == len(b):
                    for x, y in zip(a, b):
                        pending.append(("fk", x, f"{_tail(fk.group(2))}.{y}", ln))
                else:
                    diags.append({"file": rel, "line": ln, "reason": "FOREIGN KEY の列数が参照先の列数と合いません"})
                continue
            if re.match(r"(unique|check|key|index|exclude|foreign\s+key|primary\s+key|fulltext)\b", low, re.I):
                continue
            cm = re.match(r"([`\"\[]?[\w]+[`\"\]]?)\s+([A-Za-z_][\w ]*?(?:\s*\([^)]*\))?)(?=\s|$|,)(.*)$", s, re.S)
            if not cm:
                diags.append({"file": rel, "line": ln, "reason": f"列の定義「{s[:40]}」を解析できません"})
                continue
            name, typ, rest = _unq(cm.group(1)), cm.group(2).strip(), cm.group(3)
            typ = re.split(r"\s+(?:not|null|default|primary|references|unique|check|constraint|auto_increment|identity|generated)\b", typ, flags=re.I)[0].strip()
            key, ref = "なし", ""
            if re.search(r"\bprimary\s+key\b", rest, re.I):
                key = "主キー"
            rm = re.search(r"\breferences\s+([`\"\[\w.\]]+)\s*(?:\(([^)]*)\))?", rest, re.I)
            if rm:
                if rm.group(2):
                    key, ref = "外部キー", f"{_tail(rm.group(1))}.{_unq(rm.group(2).split(',')[0])}"
                else:
                    diags.append({"file": rel, "line": ln, "reason": f"列 {name} の REFERENCES に参照先の列がありません"})
            cols[name] = {"name": name, "type": typ, "key": key, "ref": ref, "line": ln}
            order.append(name)
        for kind, cname, ref, ln in pending:
            if cname in cols:
                if kind == "pk":
                    cols[cname]["key"] = "主キー"
                else:
                    cols[cname]["key"], cols[cname]["ref"] = "外部キー", ref
        tables.append({"table": _tail(m.group(1)), "columns": [cols[n] for n in order], "file": rel, "line": base_line})
    return tables, diags


def parse_json_schema(text: str, rel: str) -> Tuple[Optional[dict], List[dict]]:
    try:
        data = json.loads(text)
    except ValueError as e:
        return None, [{"file": rel, "line": 1, "reason": f"JSON として解析できません: {e}"}]
    if not isinstance(data, dict) or not isinstance(data.get("properties"), dict):
        return None, []
    lines = text.splitlines()
    cols = []
    for name, spec in data["properties"].items():
        typ = spec.get("type") if isinstance(spec, dict) else None
        typ = "|".join(typ) if isinstance(typ, list) else (typ or "")
        ln = next((i for i, l in enumerate(lines, 1) if f'"{name}"' in l), 1)
        cols.append({"name": name, "type": typ, "key": "", "ref": "", "line": ln})
    title = data.get("title") if isinstance(data.get("title"), str) else ""
    stem = re.sub(r"\.schema$", "", Path(rel).stem)
    return {"table": stem, "title": title, "columns": cols, "file": rel, "line": 1}, []


def scan_schema_files(root: Path) -> Tuple[List[dict], List[dict], List[str]]:
    """Read-only scan of *.sql and *.schema.json (and schema(s)/ directory JSON) files.  Returns (tables, diagnostics, files)."""
    import os
    tables: List[dict] = []
    diags: List[dict] = []
    files: List[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for n in sorted(names):
            p = Path(dirpath) / n
            low = n.lower()
            in_schema_dir = p.parent.name.lower() in ("schema", "schemas")
            if not (low.endswith(".sql") or low.endswith(".schema.json") or (low.endswith(".json") and in_schema_dir)):
                continue
            if len(files) >= MAX_SCHEMA_FILES:
                diags.append({"file": "", "line": 0, "reason": f"読み取るファイルが {MAX_SCHEMA_FILES} 件を超えたため、残りは読んでいません"})
                return tables, diags, files
            rel = p.relative_to(root).as_posix()
            try:
                if p.stat().st_size > MAX_SCHEMA_BYTES:
                    diags.append({"file": rel, "line": 0, "reason": "ファイルが大きすぎるため読んでいません"})
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                diags.append({"file": rel, "line": 0, "reason": f"読めません: {e.__class__.__name__}"})
                continue
            files.append(rel)
            if low.endswith(".sql"):
                ts, ds = parse_ddl(text, rel)
                tables += ts
                diags += ds
            else:
                t, ds = parse_json_schema(text, rel)
                if t:
                    tables.append(t)
                diags += ds
    return tables, diags, files


def column_model(root: Path, cfg: dict, doc: "h.RequirementsDoc") -> dict:
    """Columns (FR-1025) and the supplement from DDL / schema files (FR-1030), per entity, with the problems of the written
    definitions: {"columns": {entity: [column]}, "problems": [(file, line, message)], "supplement": {...}}."""
    tables = _catalog_tables(root, cfg)
    by_req = _by_req(doc)
    known = set(doc.glossary) | set(doc.entities) | {e for v in by_req.values() for e in v}
    tabnames = {t["name"] for t in tables}
    tab_ents: Dict[str, List[str]] = {}  # table name -> entities linked to it (computed once: O(entities x tables))
    for n in sorted(known):
        for l in _linked_tables(n, tables, by_req):
            tab_ents.setdefault(l["name"], []).append(n)
    problems: List[Tuple[str, int, str]] = []
    cols: Dict[str, List[dict]] = {}
    table_entity: Dict[str, str] = {}
    for sec in catalog_columns(root, cfg):
        for ln, msg in sec["problems"]:
            problems.append((sec["file"], ln, msg))
        if sec["table"] not in tabnames:
            problems.append((sec["file"], sec["line"], f"列の定義「{sec['table']}」はカタログのテーブルの表にないテーブルです"))
        ent_name = sec["entity"]
        if ent_name in h.NONE_VALUES:
            ent_name = ""
        if not ent_name:
            cands = tab_ents.get(sec["table"], [])
            ent_name = cands[0] if len(cands) == 1 else ""
        if not ent_name:
            problems.append((sec["file"], sec["line"], f"列の定義「{sec['table']}」の対象エンティティを特定できません（節の先頭に 対象エンティティ: 名前 を書きます）"))
            continue
        if ent_name not in known:
            problems.append((sec["file"], sec["line"], f"列の定義「{sec['table']}」の対象エンティティ「{ent_name}」が用語の表にも状態の表にもありません"))
            continue
        table_entity[sec["table"].casefold()] = ent_name
        for r in sec["rows"]:
            if r["key"] and r["key"] not in KEY_WORDS:
                problems.append((sec["file"], r["line"], f"列 {r['name']} のキー「{r['key']}」は {'・'.join(KEY_WORDS)} のいずれかにします"))
            cols.setdefault(ent_name, []).append({**{k: r[k] for k in ("name", "type", "key", "ref", "description")}, "table": sec["table"],
                                                  "origin": "管理データ", "source": {"file": sec["file"], "line": r["line"]}, "mismatch": []})
    # supplement (FR-1030)
    sup_tables, diags, sup_files = scan_schema_files(root)
    for t in tables:
        ents = tab_ents.get(t["name"], [])
        if len(ents) == 1:
            table_entity.setdefault(t["name"].casefold(), ents[0])
    for n in known:
        table_entity.setdefault(n.casefold(), n)
    for st in sup_tables:
        ent_name = table_entity.get(st["table"].casefold()) or (st.get("title") if st.get("title") in known else "")
        if not ent_name:
            diags.append({"file": st["file"], "line": st["line"], "reason": f"テーブル {st['table']} に対応するエンティティを特定できないため補完していません"})
            continue
        have = {c["name"].casefold(): c for c in cols.get(ent_name, [])}
        for sc in st["columns"]:
            ref = sc["ref"]
            if ref:
                p = parse_ref(ref)
                tgt = table_entity.get(p[0].casefold()) if p else None
                if tgt:
                    ref = f"{tgt}.{p[1]}"
                else:
                    diags.append({"file": st["file"], "line": sc["line"], "reason": f"列 {sc['name']} の参照先テーブルに対応するエンティティを特定できないため参照先を補完していません"})
                    ref = ""
            sup = {"type": sc["type"], "key": sc["key"], "ref": ref}
            src = {"file": st["file"], "line": sc["line"]}
            cur = have.get(sc["name"].casefold())
            if cur:
                for f in ("type", "key", "ref"):
                    a, b = cur[f], sup[f]
                    if b and a.casefold() != b.casefold() and not (f == "ref" and sc["ref"] and not ref):
                        cur["mismatch"].append({"field": f, "managed": a, "supplement": b, "source": src})
            else:
                col = {"name": sc["name"], "type": sup["type"], "key": sup["key"], "ref": ref, "description": "",
                       "table": st["table"], "origin": "補完", "source": src, "mismatch": []}
                cols.setdefault(ent_name, []).append(col)
                have[sc["name"].casefold()] = col
    # references of the written columns must resolve (AC-170)
    for e, lst in cols.items():
        for c in lst:
            if c["origin"] != "管理データ" or not c["ref"]:
                continue
            p = parse_ref(c["ref"])
            file, line = c["source"]["file"], c["source"]["line"]
            if not p:
                problems.append((file, line, f"列 {c['name']} の参照先「{c['ref']}」は エンティティ.列 の書式ではありません"))
            elif p[0] not in known:
                problems.append((file, line, f"列 {c['name']} の参照先のエンティティ「{p[0]}」が用語の表にも状態の表にもありません"))
            elif p[1] not in {x["name"] for x in cols.get(p[0], [])}:
                problems.append((file, line, f"列 {c['name']} の参照先の列「{p[1]}」がエンティティ「{p[0]}」の列にありません"))
    return {"columns": cols, "problems": problems, "supplement": {"files": sup_files, "diagnostics": diags}, "known": known}


def column_problems(doc: "h.RequirementsDoc", root: Path, cfg: dict) -> List[Tuple[str, int, str]]:
    """Errors of the written column definitions (AC-170).  Empty when there are none."""
    return column_model(root, cfg, doc)["problems"]


def derive_relations(doc: "h.RequirementsDoc", reqs: list, entities: List[dict], columns: Dict[str, List[dict]], known: set) -> List[dict]:
    rels: Dict[tuple, dict] = {}

    def add(key: tuple, base: dict, source: dict) -> dict:
        r = rels.setdefault(key, {**base, "sources": []})
        if source not in r["sources"]:
            r["sources"].append(source)
        return r

    for r in reqs:  # entity <-> entity by the requirement's optional field (AC-171)
        if RELATION_FIELD in r.fields:
            items, _ = parse_relation_field(r.fields[RELATION_FIELD])
            for a, b, k in items:
                if a in known and b in known and k in RELATION_KINDS:
                    rel = add(("entity", a, b), {"kind": k, "scope": "entity", "from": a, "to": b}, {"file": r.file, "line": r.line, "origin": f"要求 {r.id}"})
                    if k == "外部キー":
                        rel["kind"] = "外部キー"
    for e, lst in columns.items():  # column <-> column, and the FK's entity <-> entity (AC-173)
        for c in lst:
            p = parse_ref(c["ref"]) if c["ref"] else None
            if not p or p[0] not in known:
                continue
            src = {**c["source"], "origin": "列の定義" if c["origin"] == "管理データ" else "DDL・スキーマ（補完）"}
            add(("column", e, p[0], c["name"], p[1]), {"kind": "参照", "scope": "column", "from": e, "to": p[0],
                                                       "fromColumn": c["name"], "toColumn": p[1]}, src)
            if c["key"] == "外部キー" and p[0] != e:
                rel = add(("entity", e, p[0]), {"kind": "外部キー", "scope": "entity", "from": e, "to": p[0]}, src)
                rel["kind"] = "外部キー"
    for e in entities:  # entity -> table / requirement (FR-1022, already derived)
        for tb in e["tables"]:
            add(("usage", e["name"], "table:" + tb["name"]), {"kind": "使用", "scope": "usage", "from": e["name"], "to": tb["name"], "toType": "table"},
                {"file": tb["file"], "line": 0, "origin": "カタログのテーブル表"})
        for u in e["usecases"]:
            r = doc.requirements.get(u["requirement"])
            add(("usage", e["name"], "req:" + u["requirement"]), {"kind": "使用", "scope": "usage", "from": e["name"], "to": u["requirement"], "toType": "requirement"},
                {"file": r.file if r else "", "line": r.line if r else 0, "origin": "要求の対象エンティティ"})
    return sorted(rels.values(), key=lambda r: (r["scope"], r["from"], r["to"], r.get("fromColumn", ""), r.get("toColumn", "")))


def derive_clusters(names: List[str], relations: List[dict]) -> List[dict]:
    parent = {n: n for n in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in relations:
        if r["scope"] == "entity" and r["from"] in parent and r["to"] in parent:
            parent[find(r["from"])] = find(r["to"])
    groups: Dict[str, List[str]] = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    ordered = sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))
    return [{"id": f"C{i + 1}", "count": len(g), "entities": g} for i, g in enumerate(ordered)]


def scenario_items_check(doc: "h.RequirementsDoc", value: str) -> Tuple[List[int], List[str]]:
    nums, bad = parse_scenario_field(value)
    problems = [f"「{b}」は項番（数字）ではありません" for b in bad]
    items = scenario_items(doc)
    for n in nums:
        if n not in items:
            problems.append(f"利用シナリオ {n} が第 5 節にありません")
    return nums, problems


# --------------------------------------------------------------------------- derivation (FR-1020)

def _glossary_definitions(doc: "h.RequirementsDoc") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for text in doc.text.values():
        for t in h.parse_tables(text.splitlines()):
            tcol, dcol = t.col("用語"), t.col("定義")
            if tcol is None or dcol is None:
                continue
            for _, cells in t.rows:
                if tcol < len(cells) and dcol < len(cells):
                    for term in h.split_values(cells[tcol]):
                        out.setdefault(term, h.strip_md(cells[dcol]))
    return out


def derive(root: Path, cfg: dict) -> dict:
    doc = h.parse_requirements(root, cfg)
    defs = _glossary_definitions(doc)
    reqs = [r for r in doc.requirements.values() if r.active]
    names: Dict[str, Tuple[str, int]] = {}
    for n, pos in doc.glossary.items():
        names.setdefault(n, pos)
    for n, info in doc.entities.items():
        names.setdefault(n, (str(info["file"]), int(info["line"])))  # type: ignore[arg-type]
    by_req: Dict[str, List[str]] = {}
    for r in reqs:
        ents = h.split_values(r.fields.get("対象エンティティ", ""))
        by_req[r.id] = ents
        for e in ents:
            names.setdefault(e, (r.file, r.line))
    scen_items = scenario_items(doc)
    tables = _catalog_tables(root, cfg)
    entities = []
    for name in sorted(names):
        use = []
        usages: set = set()
        for r in reqs:
            if name not in by_req[r.id]:
                continue
            u_items, _ = parse_usage_field(r.fields.get(USAGE_FIELD, ""))
            u = sorted({w for n, ws in u_items if n == name for w in ws if w in USAGE_WORDS}, key=USAGE_WORDS.index)
            nums, _ = parse_scenario_field(r.fields.get(SCENARIO_FIELD, ""))
            nums = sorted(n for n in set(nums) if n in scen_items)
            usages.update(u)
            use.append({"requirement": r.id, "title": r.title, "scenarios": nums, "usages": u})
        linked = _linked_tables(name, tables, by_req)
        desc = defs.get(name, "")
        entities.append({
            "name": name,
            "description": desc,
            "tables": linked,
            "usecases": use,
            "usages": sorted(usages, key=USAGE_WORDS.index),
            "missing": [m for m, ok in (("説明未記載", bool(desc)), ("テーブル未記載", bool(linked)),
                                         ("使い方未記載", bool(usages))) if not ok],
            "position": {"file": names[name][0], "line": names[name][1]},
        })
    cm = column_model(root, cfg, doc)
    for e in entities:  # FR-1025 / FR-1030
        e["columns"] = cm["columns"].get(e["name"], [])
        e["columnsMissing"] = not e["columns"]  # 「列未記載」: nothing is guessed
    relations = derive_relations(doc, reqs, entities, cm["columns"], set(names))
    return {"entities": entities, "scenarios": {str(k): v for k, v in sorted(scen_items.items())},
            "relations": relations, "clusters": derive_clusters([e["name"] for e in entities], relations),
            "supplement": cm["supplement"]}


def _catalog_tables(root: Path, cfg: dict) -> List[dict]:
    out = []
    try:
        tabs = h.parse_catalog_tables(root, cfg)
    except Exception:  # noqa: BLE001 - a broken catalog must not stop the ledger
        return out
    for kind, t in tabs:
        if kind != "table":
            continue
        nc, fc, rc = t.col("テーブル名"), t.col("定義ファイル"), t.col("要求ID", "要求 ID")
        for _, cells in t.rows:
            name = h.strip_md(cells[nc]) if nc is not None and nc < len(cells) else ""
            if not name or name in h.NONE_VALUES:
                continue
            out.append({
                "name": name,
                "file": h.strip_md(cells[fc]) if fc is not None and fc < len(cells) else "",
                "reqs": h.REQ_ID_RE.findall(cells[rc]) if rc is not None and rc < len(cells) else [],
            })
    return out


def render_list(model: dict) -> str:
    ents = model["entities"]
    if not ents:
        return "エンティティなし（用語表・状態表・各要求の対象エンティティ欄に名前がありません）\n"
    lines = [f"エンティティ: {len(ents)} 件"]
    for e in ents:
        tab = "、".join(f"{t['name']}（{t['file']}）" if t["file"] else t["name"] for t in e["tables"]) or "テーブル未記載"
        uc = "、".join(
            u["requirement"] + ("（シナリオ " + "・".join(map(str, u["scenarios"])) + "）" if u["scenarios"] else "")
            for u in e["usecases"]) or "ユースケースなし"
        lines.append(f"- {e['name']} | 説明: {e['description'] or '説明未記載'} | 管理テーブル: {tab} | "
                     f"ユースケース: {uc} | 使い方: {'、'.join(e['usages']) or '使い方未記載'}"
                     f" | 列: {str(len(e['columns'])) + ' 件' if e.get('columns') else '列未記載'}")
    rels = [r for r in model.get("relations", []) if r["scope"] != "usage"]
    if rels:
        lines.append(f"関係: {len(rels)} 件")
        for r in rels:
            a = r["from"] + (f".{r['fromColumn']}" if r.get("fromColumn") else "")
            b = r["to"] + (f".{r['toColumn']}" if r.get("toColumn") else "")
            src = "、".join(f"{s['file']}:{s['line']}" for s in r["sources"])
            lines.append(f"- {a}→{b}（{r['kind']}） | 出典: {src}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- enterprise data catalog (FR-1023, NFR-SEC-023)

class SourceError(Exception):
    pass


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    return re.sub(r"\s+", "", s).casefold()


def safe_display(source: str) -> str:
    """A form of the source that is safe to print: no credentials, no query string or fragment."""
    if re.match(r"^https?://", source, re.I):
        try:
            p = urllib.parse.urlsplit(source)
            host = p.hostname or ""
            if p.port:
                host += f":{p.port}"
            return f"{p.scheme}://{host}{p.path}"
        except ValueError:
            return "(URL)"
    return source


def classify_source(source: str) -> Tuple[str, str]:
    """-> ("url"|"file", value).  Raises SourceError with a reason that never contains credentials."""
    s = source.strip()
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", s)
    if m and not re.match(r"^[A-Za-z]:[\\/]", s):
        scheme = m.group(1).lower()
        if scheme not in ("http", "https"):
            raise SourceError(f"許可していない方式（{scheme}）です。http・https だけを取得します")
        try:
            p = urllib.parse.urlsplit(s)
            _ = p.port
        except ValueError:
            raise SourceError("URL を解釈できません")
        if p.username is not None or p.password is not None or "@" in p.netloc:
            raise SourceError("URL に認証情報（利用者名・パスワード）が埋め込まれているため取得しません")
        if not p.hostname:
            raise SourceError("URL にホスト名がありません")
        return "url", s
    return "file", s


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        p = urllib.parse.urlsplit(newurl)
        if p.scheme not in ("http", "https") or p.username is not None or p.password is not None or "@" in p.netloc:
            raise SourceError("転送先が許可していない URL です")
        if req.get_method() != "GET":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _decode(data: bytes, charset: Optional[str]) -> str:
    for enc in ([charset] if charset else []) + ["utf-8-sig", "cp932"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def fetch_url(url: str, timeout: float) -> Tuple[str, str]:
    """GET only.  -> (text, content_type).  Never cached or written anywhere."""
    deadline = time.monotonic() + timeout
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "eabk-entities/1", "Accept": "*/*"})
    opener = urllib.request.build_opener(_SafeRedirect())
    try:
        resp = opener.open(req, timeout=timeout)
    except SourceError:
        raise
    except urllib.error.HTTPError as exc:
        raise SourceError(f"取得できません（HTTP {exc.code}）")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SourceError(f"取得できません（{type(exc).__name__}）")
    try:
        buf = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise SourceError(f"{timeout:g} 秒以内に取得できません")
            try:
                chunk = resp.read(65536)
            except (OSError, ValueError):
                raise SourceError(f"{timeout:g} 秒以内に取得できません")
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_BYTES:
                raise SourceError("大きすぎるため取得を打ち切りました")
        ctype = resp.headers.get("Content-Type", "") or ""
        cm = re.search(r"charset=([\w\-]+)", ctype, re.I)
        return _decode(bytes(buf), cm.group(1) if cm else None), ctype
    finally:
        resp.close()


def _pick_column(header: List[str], name_column: str) -> int:
    norm = [_norm(x) for x in header]
    if name_column:
        for i, x in enumerate(header):
            if x.strip() == name_column.strip() or norm[i] == _norm(name_column):
                return i
        raise SourceError(f"指定した名前の列「{name_column}」がありません")
    for key in NAME_KEYS:
        for i, x in enumerate(norm):
            if x == _norm(key) or _norm(key) in x:
                return i
    return 0


def parse_csv(text: str, name_column: str) -> List[Tuple[str, int]]:
    rows = list(csv.reader(io.StringIO(text)))
    rows = [(i + 1, r) for i, r in enumerate(rows) if any(c.strip() for c in r)]
    if not rows:
        return []
    col = _pick_column(rows[0][1], name_column)
    return [(r[col].strip(), ln) for ln, r in rows[1:] if col < len(r) and r[col].strip()]


def parse_markdown(text: str, name_column: str) -> List[Tuple[str, int]]:
    lines = text.splitlines()
    out: List[Tuple[str, int]] = []
    in_table_lines = set()
    for t in h.parse_tables(lines):
        col = _pick_column(t.header, name_column)
        for ln, cells in t.rows:
            in_table_lines.add(ln)
            v = h.strip_md(cells[col]) if col < len(cells) else ""
            if v:
                out.append((v, ln))
    if out:
        return out
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", line)
        if m:
            v = re.split(r"\s*[:：]\s*|\s+[-–—]\s+", h.strip_md(m.group(1)), maxsplit=1)[0].strip()
            if v:
                out.append((v, i))
    return out


def parse_json(text: str, name_column: str) -> List[Tuple[str, int]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"JSON を解析できません（{exc.lineno} 行目）")
    keys = [name_column] if name_column else []
    names: List[str] = []

    def pick(d: dict) -> Optional[str]:
        low = {str(k).strip().casefold(): k for k in d}
        for k in keys + list(NAME_KEYS):
            if k.strip().casefold() in low and isinstance(d[low[k.strip().casefold()]], str):
                return d[low[k.strip().casefold()]]
        return None

    def walk(o, depth=0) -> None:  # noqa: ANN001
        if depth > 6:
            return
        if isinstance(o, list):
            for it in o:
                if isinstance(it, str):
                    names.append(it)
                elif isinstance(it, dict):
                    v = pick(it)
                    if v is not None:
                        names.append(v)
                    else:
                        walk(it, depth + 1)
        elif isinstance(o, dict):
            lists = [v for v in o.values() if isinstance(v, (list, dict))]
            v = pick(o)
            if v is not None and not lists:
                names.append(v)
            elif any(isinstance(x, list) for x in o.values()):
                for x in o.values():
                    if isinstance(x, list):
                        walk(x, depth + 1)
            elif o and all(isinstance(x, dict) for x in o.values()):
                names.extend(str(k) for k in o)

    walk(data)
    lines = text.splitlines()
    out: List[Tuple[str, int]] = []
    start = 0
    for n in names:
        n = n.strip()
        if not n:
            continue
        needle = json.dumps(n, ensure_ascii=False)
        needle_a = json.dumps(n)
        ln = next((i for i in range(start, len(lines)) if needle in lines[i] or needle_a in lines[i]), None)
        if ln is None:
            ln = next((i for i in range(len(lines)) if needle in lines[i] or needle_a in lines[i]), 0)
        start = ln
        out.append((n, ln + 1))
    return out


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: List[List[Tuple[int, List[str]]]] = []
        self.items: List[Tuple[str, int]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None
        self._li: Optional[List[str]] = None
        self._li_line = 0
        self._row_line = 0

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row, self._row_line = [], self.getpos()[0]
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "li":
            self._li, self._li_line = [], self.getpos()[0]

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append((self._row_line, self._row))
            self._row = None
        elif tag == "li" and self._li is not None:
            v = "".join(self._li).strip()
            if v:
                self.items.append((v, self._li_line))
            self._li = None

    def handle_data(self, data):  # noqa: ANN001
        if self._cell is not None:
            self._cell.append(data)
        if self._li is not None:
            self._li.append(data)


def parse_html(text: str, name_column: str) -> List[Tuple[str, int]]:
    p = _Html()
    p.feed(text)
    out: List[Tuple[str, int]] = []
    for tab in p.tables:
        if len(tab) < 2:
            continue
        col = _pick_column(tab[0][1], name_column)
        out += [(r[col].strip(), ln) for ln, r in tab[1:] if col < len(r) and r[col].strip()]
    if out:
        return out
    return [(re.split(r"\s*[:：]\s*", v, maxsplit=1)[0].strip(), ln) for v, ln in p.items]


def parse_names(text: str, fmt: str, name_column: str) -> List[Tuple[str, int]]:
    s = text.lstrip("\ufeff")
    if fmt == "auto":
        t = s.lstrip()
        if t.startswith(("{", "[")):
            fmt = "json"
        elif re.match(r"<(!doctype|html|\?xml|body|table|ul|ol)", t, re.I):
            fmt = "html"
        elif re.search(r"^\s*\|.*\|\s*$", s, re.M) or re.search(r"^\s*(?:[-*+]|\d+[.)])\s+\S", s, re.M) or t.startswith("#"):
            fmt = "markdown"
        else:
            fmt = "csv"
    try:
        if fmt == "json":
            return parse_json(s, name_column)
        if fmt == "markdown":
            return parse_markdown(s, name_column)
        if fmt == "html":
            return parse_html(s, name_column)
        return parse_csv(s, name_column)
    except SourceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SourceError(f"解析できません（{type(exc).__name__}）")


def _format_from(name: str, ctype: str = "") -> str:
    n = name.lower().split("?")[0]
    c = ctype.lower()
    if n.endswith(".csv") or "text/csv" in c:
        return "csv"
    if n.endswith(".json") or "json" in c:
        return "json"
    if n.endswith((".md", ".markdown")) or "markdown" in c:
        return "markdown"
    if n.endswith((".htm", ".html")) or "html" in c:
        return "html"
    return "auto"


def params(root: Path, cfg: dict) -> Tuple[float, float]:
    """(PARAM-015 similarity threshold, PARAM-016 timeout seconds) from the requirements; defaults when absent."""
    thr, tmo = DEFAULT_THRESHOLD, DEFAULT_TIMEOUT
    try:
        doc = h.parse_requirements(root, cfg)
        for pid, cur in (("PARAM-015", "t"), ("PARAM-016", "o")):
            v = re.search(r"\d+(?:\.\d+)?", doc.params.get(pid, {}).get("value", ""))
            if v:
                if cur == "t" and 0 < float(v.group(0)) <= 1:
                    thr = float(v.group(0))
                elif cur == "o" and float(v.group(0)) > 0:
                    tmo = float(v.group(0))
    except Exception:  # noqa: BLE001
        pass
    return thr, tmo


def load_enterprise(root: Path, cfg: dict, timeout: float) -> dict:
    """-> {"state": "unset"|"declined"|"ok"|"unusable", "display", "reason", "names": [(name, "出典:行")]}"""
    conf = cfg.get("enterprise_data_catalog")
    source = (conf.get("source") if isinstance(conf, dict) else conf) if conf else None
    if not source or not str(source).strip():
        return {"state": "unset", "display": "", "reason": "", "names": []}
    source = str(source)
    if source.strip() == OPT_OUT:  # explicit "利用しない" (FR-1023 AC-232)
        return {"state": "declined", "display": "", "reason": "", "names": []}
    name_column = str(conf.get("name_column", "")) if isinstance(conf, dict) else ""
    fmt_conf = str(conf.get("format", "auto")).lower() if isinstance(conf, dict) else "auto"
    display = safe_display(source)
    try:
        kind, value = classify_source(source)
        if kind == "url":
            text, ctype = fetch_url(value, timeout)
            fmt = fmt_conf if fmt_conf != "auto" else _format_from(urllib.parse.urlsplit(value).path, ctype)
        else:
            path = Path(value)
            path = path if path.is_absolute() else root / path
            try:
                text = _decode(path.read_bytes(), None)
            except OSError:
                raise SourceError("ファイルを読めません")
            fmt = fmt_conf if fmt_conf != "auto" else _format_from(path.name)
        names = parse_names(text, fmt, name_column)
        if not names:
            raise SourceError("解析できません（エンティティ名を取り出せません）")
        return {"state": "ok", "display": display, "reason": "",
                "names": [(n, f"{display}:{ln}") for n, ln in names]}
    except SourceError as exc:
        return {"state": "unusable", "display": display, "reason": str(exc), "names": []}


def reconcile(eabk: List[Tuple[str, str]], ent: List[Tuple[str, str]], threshold: float) -> dict:
    """eabk / ent: [(name, position)].  -> matched, eabk_only, ent_only, fuzzy (lists of tuples)."""
    matched, fuzzy = [], []
    e_left = sorted(eabk)
    c_left = list(ent)
    for e in list(e_left):
        hit = next((c for c in c_left if c[0] == e[0]), None)
        if hit:
            matched.append((e, hit))
            e_left.remove(e)
            c_left.remove(hit)
    cands = []
    for e in e_left:
        ne = _norm(e[0])
        for c in c_left:
            nc = _norm(c[0])
            if ne and ne == nc:
                score = 1.0
            else:
                sm = difflib.SequenceMatcher(None, ne, nc)
                if not ne or not nc or sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                    continue
                score = sm.ratio()
                if score < threshold:
                    continue
            cands.append((-score, e[0], c[0], e, c))
    cands.sort(key=lambda x: (x[0], x[1], x[2]))
    used_e, used_c = set(), set()
    for _, _, _, e, c in cands:
        if e in used_e or c in used_c:
            continue
        used_e.add(e)
        used_c.add(c)
        fuzzy.append((e, c))
    return {
        "matched": matched,
        "fuzzy": sorted(fuzzy, key=lambda p: p[0][0]),
        "eabk_only": [e for e in e_left if e not in used_e],
        "ent_only": [c for c in c_left if c not in used_c],
    }


def run_check(root: Path, cfg: dict) -> dict:
    model = derive(root, cfg)
    thr, tmo = params(root, cfg)
    src = load_enterprise(root, cfg, tmo)
    eabk = [(e["name"], f"{e['position']['file']}:{e['position']['line']}") for e in model["entities"]]
    res = reconcile(eabk, src["names"], thr) if src["state"] == "ok" else None
    return {"model": model, "source": src, "result": res, "eabk_count": len(eabk)}


def render_check(rep: dict) -> str:
    src, res = rep["source"], rep["result"]
    if src["state"] == "unset":
        return "企業データカタログ: 利用しない（未設定）\n"
    if src["state"] == "declined":
        return "企業データカタログ: 利用しない\n"
    if src["state"] == "unusable":
        return f"企業データカタログ: 照合不能（{src['display']}）\n理由: {src['reason']}\n"
    out = [f"企業データカタログ: {src['display']}（{len(src['names'])} 件）／エンティティ: {rep['eabk_count']} 件"]

    def sec(title: str, rows: List[str]) -> None:
        out.append(f"{title}: {len(rows)} 件")
        out.extend(f"  - {r}" for r in rows)

    sec("一致", [f"{e[0]} ⇔ {c[0]}（EABK: {e[1]}／企業カタログ: {c[1]}）" for e, c in res["matched"]])
    sec("EABK のみ（企業カタログにない）", [f"{e[0]}（EABK: {e[1]}）" for e in res["eabk_only"]])
    sec("企業カタログのみ（EABK にない）", [f"{c[0]}（企業カタログ: {c[1]}）" for c in res["ent_only"]])
    sec("名称の揺れ候補（確定した一致ではない）", [f"{e[0]} ≈ {c[0]}（EABK: {e[1]}／企業カタログ: {c[1]}）" for e, c in res["fuzzy"]])
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- ToDo (FR-1024)

def _existing_open_questions(root: Path, cfg: dict) -> List[str]:
    doc = h.parse_requirements(root, cfg)
    rows = []
    for text in doc.text.values():
        for t in h.parse_tables(text.splitlines()):
            for _, cells in t.rows:
                if cells and re.fullmatch(r"Q-\d{3,}", h.strip_md(cells[0])):
                    q = doc.questions.get(h.strip_md(cells[0]), {})
                    if not q.get("answered"):
                        rows.append(" ".join(cells))
    return rows


def build_todos(root: Path, cfg: dict, rep: dict) -> List[dict]:
    ents = [e["name"] for e in rep["model"]["entities"]]
    res = rep["result"]
    todos: List[Tuple[str, str, str]] = []
    if rep["source"]["state"] in ("unset", "declined"):
        return []
    if rep["source"]["state"] != "ok":
        todos = [(n, R_UNCHECKED, "") for n in ents]
    else:
        eo = {e[0] for e in res["eabk_only"]}
        fz = {e[0]: c[0] for e, c in res["fuzzy"]}
        for n in ents:
            if n in fz:
                todos.append((n, R_CONFIRM, fz[n]))
            elif n in eo:
                todos.append((n, R_MISSING, ""))
    open_q = _existing_open_questions(root, cfg)
    out, seen = [], set()
    for n, reason, cand in sorted(todos):
        if (n, reason) in seen or any(f"「{n}」" in q and reason in q for q in open_q):
            continue
        seen.add((n, reason))
        out.append({"entity": n, "reason": reason, "candidate": cand, **_todo_text(n, reason, cand)})
    return out


def _todo_text(name: str, reason: str, cand: str) -> dict:
    if reason == R_UNCHECKED:
        q = f"エンティティ「{name}」が企業データカタログに載っているかを確認できていません（理由: {reason}）。参照元を設定して検査するか、担当者に確認する"
        opts = "A: scripts/ebak.config.json に参照元を設定して再検査する／B: 企業データカタログの担当者に確認して回答する／C: 対象外とする（理由を回答）"
    elif reason == R_MISSING:
        q = f"エンティティ「{name}」は企業データカタログに名前も揺れ候補もありません（理由: {reason}）。どう扱うか"
        opts = "A: 企業データカタログへの登録を依頼する／B: 企業データカタログの別名に合わせて用語表を直す／C: 対象外とする（理由を回答）"
    else:
        q = f"エンティティ「{name}」は企業データカタログの「{cand}」と名称が揺れている可能性があります（理由: {reason}）。同じものか"
        opts = "A: EABK の名前を企業データカタログに合わせる／B: 企業データカタログ側の名前を直す依頼をする／C: 別のものとして扱う（理由を回答）"
    return {"question": q, "options": opts, "importance": "中", "recommended": "A"}


def render_todo(rep: dict, todos: List[dict]) -> str:
    out = []
    if rep["source"]["state"] in ("unset", "declined"):
        out.append("企業データカタログ: 利用しない" + ("（未設定）" if rep["source"]["state"] == "unset" else ""))
        out.append("ToDo: 0 件（企業データカタログを利用しないため、照合も ToDo も行いません）")
        return "\n".join(out) + "\n"
    elif rep["source"]["state"] == "unusable":
        out.append(f"企業データカタログ: 照合不能（{rep['source']['display']}）。理由: {rep['source']['reason']}")
    if not rep["model"]["entities"]:
        out.append("ToDo: 0 件（エンティティなし）")
        return "\n".join(out) + "\n"
    if not todos:
        out.append("ToDo: 0 件（全てのエンティティが企業データカタログと一致、または質問票に同じ ToDo があります）")
        return "\n".join(out) + "\n"
    esc = lambda s: s.replace("|", "\\|")  # noqa: E731
    out.append(f"ToDo: {len(todos)} 件（質問票の行の形式。ID は採番前。rd-author が next-id.py で採番して質問票へ転記します。このコマンドは管理データを書き換えません）")
    out.append("| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |")
    out.append("|---|---|---|---|---|---|---|")
    for t in todos:
        out.append(f"| （採番前） | {t['importance']} | {esc(t['question'])} | {esc(t['options'])} | {t['recommended']} | 未回答 | — |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- cli

def _root(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg).resolve()
    cwd = Path.cwd()
    return cwd if (cwd / "scripts" / "ebak.config.json").exists() else h.repo_root()


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description="エンティティ台帳と企業データカタログとの整合（読み取り専用）")
    ap.add_argument("command", choices=["list", "check", "todo"])
    ap.add_argument("--repo", help="対象リポジトリのルート（省略時は現在のディレクトリ）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="check: 差分または照合不能のとき exit 1")
    args = ap.parse_args(argv)
    root = _root(args.repo)
    cfg = h.load_config(root)
    if args.command == "list":
        model = derive(root, cfg)
        print(json.dumps(model, ensure_ascii=False, indent=2) if args.json else render_list(model), end="" if not args.json else "\n")
        return 0
    rep = run_check(root, cfg)
    if args.command == "check":
        if args.json:
            print(json.dumps({"source": {k: v for k, v in rep["source"].items() if k != "names"},
                              "result": rep["result"]}, ensure_ascii=False, indent=2))
        else:
            print(render_check(rep), end="")
        res = rep["result"]
        bad = rep["source"]["state"] == "unusable" or bool(res and (res["eabk_only"] or res["ent_only"] or res["fuzzy"]))
        return 1 if args.strict and bad else 0
    todos = build_todos(root, cfg, rep)
    print(json.dumps(todos, ensure_ascii=False, indent=2) if args.json else render_todo(rep, todos), end="" if not args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
