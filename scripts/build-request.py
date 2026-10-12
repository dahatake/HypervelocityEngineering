#!/usr/bin/env python3
"""build-request.py - generate a /build request from an allowed time only (FR-1016).

Usage:
  python scripts/build-request.py <許容時間>      # e.g. 60分 / 24時間 / 90m / 1.5h

Prints a request in the /build template format (<request>, <answers>, <references>,
<run_options>).  `max_hours` is the given time; `scope` is the first N candidates of the
FR-1015 analysis (scripts/next-impl.py), where N = floor(minutes / PARAM-012), at least 1.
It only generates text: it starts no run, implements nothing and writes no file.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True  # read-only: leave no __pycache__ in the target repository
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

DEFAULT_MINUTES_PER_REQ = 60.0  # used only when PARAM-012 is missing in the target repository
UNITS = {
    "分": 1.0, "m": 1.0, "min": 1.0, "mins": 1.0, "minute": 1.0, "minutes": 1.0,
    "時間": 60.0, "h": 60.0, "hr": 60.0, "hrs": 60.0, "hour": 60.0, "hours": 60.0,
}
EXAMPLES = "60分、90m、24時間、1.5h"
RUN_OPTIONS = [
    ("approval_policy", "安全範囲は推奨どおり"), ("parallel_workers", "auto"),
    ("git_push", "しない"), ("deploy", "しない"), ("external_write", "しない"),
    ("paid_services", "使わない"), ("external_exposure", "公開しない"),
]


def parse_duration(text: str) -> float:
    """Return minutes.  Raises ValueError with the cause and examples."""
    s = (text or "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z分時間]*)", s)
    if not m:
        raise ValueError(f"許容時間 '{s}' を数と単位として読めません")
    num, unit = float(m.group(1)), m.group(2).lower()
    if not unit:
        raise ValueError(f"許容時間 '{s}' に単位がありません")
    if unit not in UNITS:
        raise ValueError(f"許容時間 '{s}' の単位 '{m.group(2)}' は未対応です（対応: 分・m・時間・h）")
    if num <= 0:
        raise ValueError(f"許容時間 '{s}' は 0 より大きくします")
    return num * UNITS[unit]


def minutes_per_requirement(root: Path, cfg: dict) -> float:
    doc = h.parse_requirements(root, cfg)
    p = doc.params.get("PARAM-012")
    if p:
        m = re.search(r"\d+(?:\.\d+)?", h.strip_md(p.get("value", "")))
        if m and float(m.group()) > 0:
            return float(m.group())
    return DEFAULT_MINUTES_PER_REQ


def fmt_hours(minutes: float) -> str:
    return f"{round(minutes / 60.0, 6):g}"


def build(root: Path, cfg: dict, minutes: float, label: str) -> Optional[str]:
    """Return the request text, or None when there is no candidate (message is printed)."""
    nxt = h.load_script("next-impl")
    res = nxt.analyze(root, cfg)
    per = minutes_per_requirement(root, cfg)
    n = max(1, int(math.floor(round(minutes / per, 9))))
    if not res["candidates"]:
        print("次に実装できる候補がありません。依頼は出力しません。")
        print("")
        print(nxt.excluded_md(res))
        return None
    scope = res["scope"][:n]
    chosen = {c["id"] for c in res["candidates"] if c["id"] in scope}
    table = nxt.rank_table_md({**res, "candidates": [c for c in res["candidates"] if c["id"] in chosen]})
    request = (
        f"次に実装すべき要求として、分析（scripts/next-impl.py）が選んだ {len(scope)} 件を実装する。"
        f"許容時間 {label}（1 要求あたり {per:g} 分で換算し、最大 {n} 件）。\n"
        f"選定の根拠（順位表）:\n\n{table}"
    )
    lines = [f"max_hours: {fmt_hours(minutes)}"]
    lines += [f"{k}: {v}" for k, v in RUN_OPTIONS[:2]]
    lines.append("scope: " + ", ".join(scope))
    lines += [f"{k}: {v}" for k, v in RUN_OPTIONS[2:]]
    return (f"<request>\n{request}\n</request>\n<answers>\n</answers>\n<references>\n</references>\n"
            "<run_options>\n" + "\n".join(lines) + "\n</run_options>")


def main(argv=None) -> int:
    h.setup_io()
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(f"使い方: python scripts/build-request.py <許容時間>  例: {EXAMPLES}", file=sys.stderr)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    try:
        minutes = parse_duration(argv[0])
    except ValueError as e:
        print(f"ERROR build-request: {e}。指定例: {EXAMPLES}", file=sys.stderr)
        return 2
    root = h.repo_root()
    cfg = h.load_config(root)
    text = build(root, cfg, minutes, argv[0].strip())
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
