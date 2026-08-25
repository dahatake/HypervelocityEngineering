#!/usr/bin/env python3
"""Thin CLI wrapper for the HVE AI Agent capability artifact validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[4]
if not (_REPO_ROOT / "hve" / "artifact_validation.py").is_file():
    raise RuntimeError("Unable to resolve repository root for capability validator")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hve.artifact_validation import validate_ai_agent_capability_artifacts  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate AAG/AAGD AG-CAP-01..10 artifacts.",
    )
    parser.add_argument("--workflow", choices=("aag", "aagd"), required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--agent-dir", type=Path)
    parser.add_argument("--test-spec", type=Path)
    parser.add_argument(
        "--tool-search-policy",
        choices=("auto", "yes", "no"),
        default="auto",
        help="Tool search policy for the generated Agent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit one structured JSON result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    errors = validate_ai_agent_capability_artifacts(
        args.workflow,
        args.design,
        agent_dir=args.agent_dir,
        test_spec_path=args.test_spec,
        tool_search_policy=args.tool_search_policy,
    )
    payload = {
        "workflow": args.workflow,
        "passed": not errors,
        "warnings": [],
        "errors": errors,
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(f"PASS: {args.workflow} AI Agent capability contract")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
