"""enrich_upstream_inputs.py — per-Step io-contract に上流 Step の output を input として追加する。

各 per-Step YAML について:
  1. 対応する StepDef を _REGISTRY から取得
  2. step.depends_on の各上流 Step の output_paths + output_paths_template を取得
  3. それらが当該 per-Step YAML の inputs に存在しない場合は追加（required: true, kind: agent_artifact）
  4. producer は <上流 Agent>--<workflow>--<上流 stepId> に設定

これにより、Step 間の依存チェーン（StepDef.depends_on）が io-contract の input/output 関係としても表現される。
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from hve.workflow_registry import list_workflows  # type: ignore

IOC = REPO / ".github" / "io-contracts"


def load_yaml(fp: Path) -> dict:
    with fp.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def emit_yaml(fp: Path, data: dict) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    fp.write_text(text, encoding="utf-8")


def step_outputs(step) -> list[str]:
    out = list(step.output_paths or [])
    if step.output_paths_template:
        out += list(step.output_paths_template)
    return out


def main() -> int:
    # Build (wf_id, step_id) -> step, agent, basename
    step_index: dict[tuple[str, str], tuple[object, str, str]] = {}
    for wf in list_workflows():
        wf_id = wf.id
        for step in wf.steps:
            if getattr(step, "is_container", False):
                continue
            agent = getattr(step, "custom_agent", None)
            if not agent:
                continue
            basename = f"{agent}--{wf_id}--{step.id}"
            step_index[(wf_id, step.id)] = (step, agent, basename)

    updated = 0
    added_total = 0
    for (wf_id, step_id), (step, agent, basename) in step_index.items():
        fp = IOC / f"{basename}.yaml"
        if not fp.exists():
            continue
        c = load_yaml(fp)
        existing_input_paths = {(i.get("path") or "").strip() for i in (c.get("inputs") or []) if isinstance(i, dict)}

        new_inputs: list[dict] = []
        for dep_step_id in (step.depends_on or []):
            up = step_index.get((wf_id, dep_step_id))
            if up is None:
                continue
            up_step, up_agent, up_basename = up
            for p in step_outputs(up_step):
                if p in existing_input_paths:
                    continue
                new_inputs.append({
                    "path": p,
                    "required": True,
                    "kind": "agent_artifact",
                    "producer": up_basename,
                })
                existing_input_paths.add(p)

        if new_inputs:
            c.setdefault("inputs", []).extend(new_inputs)
            emit_yaml(fp, c)
            updated += 1
            added_total += len(new_inputs)
    print(f"Updated: {updated}, inputs added: {added_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
