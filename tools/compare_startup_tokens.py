#!/usr/bin/env python3
"""before / after の起動時トークン比較レポート生成。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_current_token_metrics(payload: Dict[str, Any]) -> Dict[str, int]:
    metrics: Dict[str, int] = {}

    def _walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            if "current_tokens" in node and isinstance(node.get("current_tokens"), int):
                metrics[prefix] = int(node["current_tokens"])
            for key, value in node.items():
                child = f"{prefix}.{key}" if prefix else key
                _walk(child, value)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                child = f"{prefix}[{idx}]"
                _walk(child, value)

    _walk("", payload.get("measurements", {}))
    return metrics


def build_comparison(
    before: Dict[str, Any], after: Dict[str, Any]
) -> List[Tuple[str, Optional[int], Optional[int], Optional[int], Optional[float]]]:
    b = extract_current_token_metrics(before)
    a = extract_current_token_metrics(after)
    keys = sorted(set(b) | set(a))
    rows: List[Tuple[str, Optional[int], Optional[int], Optional[int], Optional[float]]] = []
    for key in keys:
        before_val = b.get(key)
        after_val = a.get(key)
        if before_val is None or after_val is None:
            delta = None
            ratio = None
        else:
            delta = after_val - before_val
            ratio = (delta / before_val * 100.0) if before_val else 0.0
        rows.append((key, before_val, after_val, delta, ratio))
    return rows


def _format_int_or_na(value: Optional[int]) -> str:
    return "N/A" if value is None else str(value)


def _format_delta_or_na(value: Optional[int]) -> str:
    return "N/A" if value is None else f"{value:+d}"


def _format_ratio_or_na(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def render_markdown(
    rows: List[Tuple[str, Optional[int], Optional[int], Optional[int], Optional[float]]],
    before_label: str,
    after_label: str,
) -> str:
    lines = [
        "# Startup Token Comparison",
        "",
        f"- before: {before_label}",
        f"- after: {after_label}",
        "",
        "| metric | before | after | delta | delta% |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric, before_val, after_val, delta, ratio in rows:
        lines.append(
            f"| `{metric}` | {_format_int_or_na(before_val)} | {_format_int_or_na(after_val)} | {_format_delta_or_na(delta)} | {_format_ratio_or_na(ratio)} |"
        )
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare startup token usage JSON files")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", default=None, help="optional markdown output path")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    before_path = Path(args.before)
    after_path = Path(args.after)

    before = _load(before_path)
    after = _load(after_path)
    rows = build_comparison(before, after)
    markdown = render_markdown(rows, before.get("label", before_path.name), after.get("label", after_path.name))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"saved: {out_path}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
