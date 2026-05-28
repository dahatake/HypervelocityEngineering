"""remove_work_outputs.py — 全 per-Step io-contract YAML から {WORK}* で始まる outputs を除去する。

Stage 4.A3: work-artifacts-layout 由来の共通 work artifact（plan.md / subissues.md /
work-status.md 等）は StepDef.output_paths には宣言されない。
これらを outputs から削除して StepDef と整合させる。
inputs から {WORK}* は対象外（基本 outputs にしか登場しない）。
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
IOC = REPO / ".github" / "io-contracts"


def main() -> int:
    updated = 0
    removed_total = 0
    for fp in sorted(IOC.glob("*.yaml")):
        with fp.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        outs = data.get("outputs") or []
        new_outs = [o for o in outs if not (isinstance(o, dict) and (o.get("path") or "").startswith("{WORK}"))]
        removed = len(outs) - len(new_outs)
        if removed > 0:
            data["outputs"] = new_outs
            text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
            fp.write_text(text, encoding="utf-8")
            updated += 1
            removed_total += removed
    print(f"Files updated: {updated}, entries removed: {removed_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
