#!/usr/bin/env python3
"""summarize.py - shrink a long log / test output to a few lines for the LLM (plan §10, R-21).

Usage:
  python scripts/summarize.py work/runs/<run-id>/logs/build.log [--max-lines 15] [--tail 5]
  some-command 2>&1 | python scripts/summarize.py -

Prints: one header line, test-runner summary lines, the first distinct error lines, and the tail.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hvelib as h  # noqa: E402

ERROR_RX = re.compile(
    r"(?i)(\berror\b|\bfailed\b|\bfailure\b|\bexception\b|traceback|assert(ion)?error|\bFAIL\b|✗|✘|\bpanic\b|\bfatal\b|ERR!|"
    r"\bE\s{3}|^\s*>\s+\d+\s*\||not ok\b|CHK-\d+)"
)
NOISE_RX = re.compile(r"(?i)(0 errors?|0 failed|errors?=0|no errors|warning: LF will be replaced)")
SUMMARY_RX = re.compile(
    r"(?i)(=+ .*(passed|failed|error).* =+|^Tests?:\s|^Test Suites?:|^\s*\d+ (passed|failed|skipped)\b|Passed!|Failed!|"
    r"^(ok|FAIL)\s+\S+\s+[\d.]+s|^rdcheck: |^verify: |^ledger run: |Build (succeeded|FAILED)|\d+ Warning\(s\)|\d+ Error\(s\))"
)


def summarize(text: str, max_lines: int, tail: int) -> str:
    lines = [l.rstrip() for l in text.splitlines()]
    summary = [l.strip() for l in lines if SUMMARY_RX.search(l)]
    errors, seen = [], set()
    for l in lines:
        if ERROR_RX.search(l) and not NOISE_RX.search(l):
            key = re.sub(r"\d+", "#", l.strip())[:160]
            if key in seen:
                continue
            seen.add(key)
            errors.append(l.strip()[:300])
    out = [f"summary: {len(lines)} lines, error-like={len(errors)}"]
    out += summary[-5:]
    budget = max(max_lines - len(out) - tail, 3)
    out += errors[:budget]
    if len(errors) > budget:
        out.append(f"... (+{len(errors) - budget} more error-like lines)")
    if tail:
        out.append("--- tail ---")
        out += [l[:300] for l in lines[-tail:]]
    return "\n".join(out)


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--max-lines", type=int, default=15)
    ap.add_argument("--tail", type=int, default=5)
    args = ap.parse_args(argv)
    if args.path == "-":
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"summary: {args.path} がありません")
            return 1
        text = p.read_bytes().decode("utf-8", "replace")
    print(summarize(text, args.max_lines, args.tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
