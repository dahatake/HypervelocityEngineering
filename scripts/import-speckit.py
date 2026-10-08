#!/usr/bin/env python3
"""import-speckit.py - turn GitHub Spec Kit artifacts into a /build request draft for the conductor.

Usage:
  python scripts/import-speckit.py                      # all features under specs/ of this repo
  python scripts/import-speckit.py --source ../app      # another Spec Kit project
  python scripts/import-speckit.py --feature 001-photo-albums --feature 002-sharing
  python scripts/import-speckit.py --implement          # also implement (omit `scope: なし`)
  python scripts/import-speckit.py --json               # mapping only, as JSON
  python scripts/import-speckit.py --stdout             # print the request instead of writing a file

Reads:  specs/<feature>/spec.md (required), plan.md / tasks.md (references only),
        .specify/memory/constitution.md (principles -> 既定制約 candidates).
Writes: work/import/speckit-<YYYYmmddHHMM>.md  (mapping table + the request to paste after /build)

This script never edits docs/requirements-definition.md (G-1: rd-author only) and never assigns
toolkit IDs (G-3: next-id.py only). Spec Kit IDs are kept as source references like
`speckit:001-photo-albums/FR-003`; rd-author re-numbers them when it writes the requirements.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

PRIORITY = {"P1": "MUST", "P2": "SHOULD"}
CLARIFY_RE = re.compile(r"\[NEEDS CLARIFICATION:\s*([^\]]+)\]", re.I)
STORY_RE = re.compile(r"^###\s+User Story\s+(\d+)\s*[-–—:]\s*(.*?)\s*(?:\(Priority:\s*(P\d+)\s*\))?\s*$", re.I)
SCENARIO_RE = re.compile(r"^\s*\d+\.\s+(.*\*\*Given\*\*.*)$", re.I)
ID_BULLET_RE = re.compile(r"^\s*[-*]\s+\*\*((?:FR|SC|NFR)-\d+)\*\*\s*[:：]\s*(.*)$")
NAMED_BULLET_RE = re.compile(r"^\s*[-*]\s+\*\*([^*]+)\*\*\s*[:：]\s*(.*)$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
CLAR_QA_RE = re.compile(r"^\s*[-*]\s+Q[:：]\s*(.*?)\s*(?:→|->)\s*A[:：]\s*(.*)$")
PRINCIPLE_RE = re.compile(r"^###\s+(.*)$")
PLACEHOLDER_RE = re.compile(r"\[(?:FEATURE NAME|Brief Title|DATE|initial state|action|expected outcome|"
                            r"Entity \d|PROJECT_NAME|PRINCIPLE_\d_NAME|[A-Z_]{4,})\]")
MODAL_RE = re.compile(r"\b(MUST NOT|MUST|SHALL|SHOULD|MAY|COULD)\b")


@dataclass
class Item:
    ref: str
    kind: str
    target: str
    text: str
    priority: str = ""
    note: str = ""
    clarifications: List[str] = field(default_factory=list)


@dataclass
class Feature:
    name: str
    title: str
    path: str
    status: str = ""
    items: List[Item] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    placeholders: List[str] = field(default_factory=list)
    raw: str = ""


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("|", "／")).strip()


def priority_from_text(text: str) -> str:
    m = MODAL_RE.search(text)
    if not m:
        return ""
    word = m.group(1)
    return {"MUST NOT": "MUST", "SHALL": "MUST", "COULD": "MAY"}.get(word, word)


def section_of(line: str, current: str) -> str:
    m = re.match(r"^(#{2,3})\s+(.*)$", line)
    if not m:
        return current
    title = m.group(2).lower()
    for key, name in (("user scenario", "stories"), ("edge case", "edge"), ("functional requirement", "fr"),
                      ("non-functional", "nfr"), ("key entit", "entities"), ("success criteria", "sc"),
                      ("measurable outcome", "sc"), ("assumption", "assumptions"), ("clarification", "clarify"),
                      ("requirements", "fr")):
        if key in title:
            return name
    if m.group(1) == "##":
        return "other"
    return current if current in ("stories", "clarify") else "other"


def parse_spec(path: Path, feature: str) -> Feature:
    raw = h.read_text(path)
    text = strip_comments(raw)
    lines = text.splitlines()
    title = feature
    status = ""
    for l in lines[:15]:
        m = re.match(r"^#\s+(?:Feature Specification:\s*)?(.*)$", l)
        if m and title == feature:
            title = m.group(1).strip() or feature
        m = re.match(r"^\*\*Status\*\*\s*:\s*(.*)$", l)
        if m:
            status = m.group(1).strip()
    f = Feature(name=feature, title=title, path=path.as_posix(), status=status, raw=raw)
    f.placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
    ref = lambda local: f"speckit:{feature}/{local}"  # noqa: E731
    section = "other"
    story: Optional[Item] = None
    story_no = ""
    scen_no = 0
    edge_no = assume_no = clar_no = 0
    in_why = False
    for line in lines:
        m = STORY_RE.match(line)
        if m:
            section = "stories"
            story_no = m.group(1)
            prio = (m.group(3) or "").upper()
            story = Item(ref(f"US{story_no}"), "ユーザーストーリー", "要求（FR）と利用シナリオ",
                         clean(m.group(2)), PRIORITY.get(prio, "MAY" if prio else ""), f"Spec Kit の優先度 {prio or '未指定'}")
            f.items.append(story)
            scen_no = 0
            in_why = False
            continue
        if line.startswith("#"):
            section = section_of(line, section)
            if section != "stories":
                story = None
            continue
        if section == "stories" and story is not None:
            m = SCENARIO_RE.match(line)
            if m:
                scen_no += 1
                body = clean(m.group(1).replace("**", ""))
                f.items.append(Item(ref(f"US{story_no}-AS{scen_no}"), "受入シナリオ", f"受入基準（AC）← {story.ref}",
                                    body, story.priority, "検証レベル候補: system"))
                continue
            m = re.match(r"^\*\*Why this priority\*\*\s*:\s*(.*)$", line.strip(), re.I)
            if m:
                story.note += f"。理由: {clean(m.group(1))}"
                in_why = True
                continue
            m = re.match(r"^\*\*Independent Test\*\*\s*:\s*(.*)$", line.strip(), re.I)
            if m:
                story.note += f"。独立テスト: {clean(m.group(1))}"
                continue
            if line.strip() and not line.strip().startswith(("**", "---")) and not in_why and scen_no == 0:
                story.text = clean(f"{story.text}: {line}") if ":" not in story.text else clean(f"{story.text} {line}")
            continue
        m = ID_BULLET_RE.match(line)
        if m and section in ("fr", "nfr", "sc", "other"):
            sid, body = m.group(1), clean(m.group(2))
            if sid.startswith("SC"):
                f.items.append(Item(ref(sid), "成功基準", "目的（G）の成功指標、または非機能要求（NFR）", body))
            elif sid.startswith("NFR") or section == "nfr":
                f.items.append(Item(ref(sid), "非機能要求", "非機能要求（NFR-<区分>）", body, priority_from_text(body)))
            else:
                f.items.append(Item(ref(sid), "機能要求", "要求（FR）", body, priority_from_text(body)))
            continue
        if section == "entities":
            m = NAMED_BULLET_RE.match(line)
            if m:
                f.items.append(Item(ref(f"ENT-{clean(m.group(1))}"), "主要エンティティ", "用語・対象エンティティ", clean(m.group(2))))
            continue
        if section == "edge":
            m = BULLET_RE.match(line)
            if m:
                edge_no += 1
                body = clean(m.group(1))
                question = body.endswith(("?", "？"))
                f.items.append(Item(ref(f"EC{edge_no}"), "エッジケース",
                                    "質問票（Q）。答えが本文にあれば受入基準（AC）" if question else "受入基準（AC）", body))
            continue
        if section == "assumptions":
            m = BULLET_RE.match(line)
            if m:
                assume_no += 1
                f.items.append(Item(ref(f"AS{assume_no}"), "前提", "前提・制約、または ASSUMPTION", clean(m.group(1))))
            continue
        if section == "clarify":
            m = CLAR_QA_RE.match(line)
            if m:
                clar_no += 1
                f.items.append(Item(ref(f"CL{clar_no}"), "確認済みの回答", "決定記録（出自: 利用者決定）",
                                    clean(f"Q: {m.group(1)} → A: {m.group(2)}")))
            continue
    open_no = 0
    for it in f.items:
        it.clarifications = [clean(c) for c in CLARIFY_RE.findall(it.text)]
    for idx, line in enumerate(lines, 1):
        for c in CLARIFY_RE.findall(line):
            if not any(clean(c) in it.clarifications for it in f.items):
                open_no += 1
                f.items.append(Item(ref(f"NC{open_no}"), "未確定事項", "質問票（Q）", clean(c), note=f"spec.md {idx} 行目"))
    for extra in ("plan.md", "tasks.md", "research.md", "data-model.md", "quickstart.md"):
        p = path.parent / extra
        if p.exists():
            f.references.append(p.as_posix())
    contracts = path.parent / "contracts"
    if contracts.is_dir():
        f.references.append(contracts.as_posix() + "/")
    return f


def parse_constitution(path: Path) -> List[Item]:
    text = strip_comments(h.read_text(path))
    items: List[Item] = []
    in_core = False
    cur: Optional[Item] = None
    for line in text.splitlines():
        if line.startswith("## "):
            in_core = "principle" in line.lower() or "原則" in line
            cur = None
            continue
        m = PRINCIPLE_RE.match(line)
        if in_core and m:
            name = clean(re.sub(r"^[IVXLC]+\.\s*", "", m.group(1)))
            cur = Item(f"speckit:constitution/{len(items) + 1}", "原則（Constitution）", "既定制約、または非機能要求（NFR）", name)
            items.append(cur)
            continue
        if cur is not None and line.strip():
            body = clean(line.lstrip("-* "))
            cur.text = f"{cur.text}: {body}" if ": " not in cur.text else f"{cur.text} {body}"
            if len(cur.text) > 400:
                cur.text = cur.text[:400] + "…"
    return items


def find_features(source: Path, only: List[str]) -> List[Path]:
    specs = source / "specs"
    if not specs.is_dir():
        return []
    out = sorted(p for p in specs.glob("*/spec.md"))
    if only:
        out = [p for p in out if p.parent.name in only or any(p.parent.name.startswith(o) for o in only)]
    return out


def mapping_table(features: List[Feature], principles: List[Item]) -> str:
    rows = ["| 取り込み元 | Spec Kit の種別 | 取り込み先の候補 | 優先度の候補 | 内容（要約） | 備考 |", "|---|---|---|---|---|---|"]
    for it in [*principles, *(i for f in features for i in f.items)]:
        note = it.note
        if it.clarifications:
            note = (note + "。" if note else "") + "未確定: " + " / ".join(it.clarifications) + " → Q と BLOCKED"
        body = it.text if len(it.text) <= 160 else it.text[:160] + "…"
        rows.append(f"| `{it.ref}` | {it.kind} | {it.target} | {it.priority or '-'} | {body} | {clean(note) or '-'} |")
    return "\n".join(rows)


def build_request(features: List[Feature], principles: List[Item], constitution: Optional[Path],
                  source: Path, implement: bool) -> str:
    def rel(p: str) -> str:
        try:
            return Path(p).resolve().relative_to(source.resolve()).as_posix()
        except ValueError:
            return p

    parts = ["<request>",
             "GitHub Spec Kit の成果物（下の pasted_content）を、この toolkit の要求定義書とカタログに取り込む。意味は変えない。",
             "- 取り込み元の ID（`speckit:<機能>/FR-001` など）は toolkit の ID として使わない。要求・AC・Q・G・PARAM は next-id.py で採番し直し、各要求の出典欄に取り込み元 ID を書く。",
             "- 取り込み元のファイルは出典台帳に SRC として登録する（区分: 本文）。",
             "- 対応表の「取り込み先の候補」に従う。ユーザーストーリーは利用シナリオと要求（FR）に、受入シナリオ（Given/When/Then）は受入基準（AC）にする。",
             "- Spec Kit の優先度 P1 は MUST、P2 は SHOULD、P3 以降は MAY を候補とする。本文の MUST/SHOULD/MAY と食い違う場合は、強い方を採り、理由を優先度の欄に書く。",
             "- `[NEEDS CLARIFICATION: …]` は質問票（Q）にし、関係する受入基準に BLOCKED を付ける。Clarifications の回答は決定記録にする（出自: 利用者決定）。",
             "- 閾値・期間・件数は PARAM にする。plan.md の技術選定は要求にしない（前提・制約に当たるものだけ書く）。",
             "- Constitution の原則は既定制約か非機能要求にする。テスト方針などの開発プロセスの原則は要求にせず、決定記録に残す。",
             "- 同じ意味の既存の要求があれば、新しく作らずに既存の要求 ID へ対応付け、違いがあれば競合として質問票に挙げる。",
             "",
             "対応表（import-speckit.py が機械的に作成。判断は rd-author が行う）:",
             "",
             mapping_table(features, principles),
             ""]
    if constitution is not None:
        parts += [f'<pasted_content id="speckit-constitution">',
                  strip_comments(h.read_text(constitution)).strip(),
                  f'</pasted_content id="speckit-constitution">', ""]
    for f in features:
        pid = f"speckit-{f.name}"
        parts += [f'<pasted_content id="{pid}">', strip_comments(f.raw).strip(), f'</pasted_content id="{pid}">', ""]
    if not implement:
        parts.append("今回は要求定義書とカタログへの取り込みだけを行い、実装はまだしない。")
    parts += ["</request>", "<answers>", "</answers>", "<references>"]
    for f in features:
        parts.append(rel(f.path))
        parts += [rel(r) for r in f.references]
    if constitution is not None:
        parts.append(rel(constitution.as_posix()))
    parts.append("</references>")
    if not implement:
        parts += ["<run_options>", "scope: なし", "approval_policy: 厳格", "</run_options>"]
    return "\n".join(parts) + "\n"


def summary_counts(features: List[Feature], principles: List[Item]) -> Dict[str, int]:
    c: Dict[str, int] = {}
    for it in [*principles, *(i for f in features for i in f.items)]:
        c[it.kind] = c.get(it.kind, 0) + 1
    return c


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=None, help="Spec Kit のプロジェクトのルート（既定: このリポジトリ）")
    ap.add_argument("--feature", action="append", default=[], help="specs/ 配下の機能ディレクトリ名（前方一致・複数可）")
    ap.add_argument("--no-constitution", action="store_true")
    ap.add_argument("--implement", action="store_true", help="取り込み後に実装まで進める依頼にする")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else h.repo_root()
    cfg = h.load_config(root)
    source = Path(args.source).resolve() if args.source else root
    spec_paths = find_features(source, args.feature)
    if not spec_paths:
        print(f"ERROR import-speckit: {source.as_posix()}/specs/*/spec.md が見つかりません")
        return 2
    features = [parse_spec(p, p.parent.name) for p in spec_paths]
    const_path = source / ".specify" / "memory" / "constitution.md"
    constitution = const_path if const_path.exists() and not args.no_constitution else None
    principles = parse_constitution(constitution) if constitution else []
    if constitution and not principles:
        constitution = None
    counts = summary_counts(features, principles)
    open_q = sum(1 for f in features for i in f.items if i.kind == "未確定事項" or i.clarifications)
    if args.json:
        print(json.dumps({"source": source.as_posix(), "features": [
            {"name": f.name, "title": f.title, "status": f.status, "path": f.path, "references": f.references,
             "placeholders": f.placeholders, "items": [asdict(i) for i in f.items]} for f in features],
            "constitution": [asdict(i) for i in principles], "counts": counts}, ensure_ascii=False, indent=2))
        return 0
    request = build_request(features, principles, constitution, source, args.implement)
    if args.stdout:
        sys.stdout.write(request)
        return 0
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    out = Path(args.out) if args.out else h.work_dir(root, cfg) / "import" / f"speckit-{stamp}.md"
    warn = [f"- `{f.name}`: テンプレートのままの箇所があります（{', '.join(f.placeholders[:5])}）。先に Spec Kit 側で埋めるか、rd-author に質問票へ挙げさせます"
            for f in features if f.placeholders]
    doc = [f"# Spec Kit からの取り込み（{dt.datetime.now().strftime('%Y-%m-%d %H:%M')}）", "",
           f"- 取り込み元: `{source.as_posix()}`",
           f"- 機能: {', '.join(f'`{f.name}`（{f.title}、{f.status or "状態不明"}）' for f in features)}",
           f"- Constitution: {'あり（原則 ' + str(len(principles)) + ' 件）' if constitution else 'なし'}",
           "- 件数: " + "、".join(f"{k} {v}" for k, v in counts.items()),
           f"- 未確定事項（`[NEEDS CLARIFICATION]`）: {open_q} 件", ""]
    if warn:
        doc += ["## 注意", "", *warn, ""]
    doc += ["## 使い方", "",
            "1. 下の「依頼文」を、conductor の `/build` の後に貼り付けて送信します（既定では要求定義だけを行い、実装しません）。",
            "2. run-report.md の質問票に回答し、次の `/build` で実装まで進めます（`--implement` で作った依頼文なら 1 回で実装まで進みます）。",
            "", "## 依頼文", "", "~~~~text", request.rstrip("\n"), "~~~~", ""]
    h.write_text_atomic(out, "\n".join(doc))
    try:
        shown = out.resolve().relative_to(root).as_posix()
    except ValueError:
        shown = out.as_posix()
    print(f"import-speckit: features={len(features)} items={sum(counts.values())} clarifications={open_q} -> {shown}")
    for w in warn:
        print("WARN " + w[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
