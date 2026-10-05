"""Check the ID ledger (docs/catalog/id-ledger.md) deterministically (FR-IDL-01).

`hve/id_ledger.py` owns the rules; this entrypoint only adapts them to a shell caller.
Exit code 0 when there is no violation (or with --warn-only), 1 when violations exist.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from hve.id_ledger import bootstrap_ledger_rows, check_id_ledger, render_ledger  # noqa: E402
from hve.catalog_parsers import ID_LEDGER_PATH  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--warn-only", action="store_true", help="violations are printed but exit 0")
    parser.add_argument("--bootstrap", action="store_true", help="write the ledger from existing catalogs")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if args.bootstrap:
        target = repo_root / ID_LEDGER_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_ledger(bootstrap_ledger_rows(repo_root)), encoding="utf-8", newline="\n")
        print(f"wrote {ID_LEDGER_PATH}")

    findings = check_id_ledger(repo_root)
    for finding in findings:
        print(finding.format())
    print(f"id-ledger: {len(findings)} violation(s)")
    return 0 if not findings or args.warn_only else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
