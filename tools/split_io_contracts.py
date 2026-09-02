"""split_io_contracts.py — Per-Agent io-contract YAML を per-Step ファイルへ分割する。

入力: .github/io-contracts/<Agent>.yaml （N 件）
出力: .github/io-contracts/<Agent>--<workflow>--<stepId>.yaml （M 件、M >= N）

ルール:
  1. hve.workflow_registry の全 StepDef（is_container=False, custom_agent != None）を走査。
  2. 各 StepDef について、対応 Agent の既存 YAML を基底として読み込み、
     - outputs を StepDef.output_paths + StepDef.output_paths_template で **置換**
     - inputs はそのまま継承し、StepDef.required_input_paths に列挙されているパスは
       required=true に昇格、それ以外は元の required 値を保持
  3. producer 参照は分割完了後にすべて per-Step ファイル名形式に正規化する別ステップで行う
     （本スクリプトは Agent 名のまま出力する。正規化は後続タスクで）。
  4. 旧 <Agent>.yaml は本スクリプトでは削除しない（後続タスクで実施）。
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


def step_filename(agent: str, wf_id: str, step_id: str) -> str:
    # Q-A2.1=A: <Agent>--<workflow>--<stepId>.yaml
    return f"{agent}--{wf_id}--{step_id}.yaml"


def step_outputs(step) -> list[str]:
    out = list(step.output_paths or [])
    if step.output_paths_template:
        out += list(step.output_paths_template)
    return out


def build_per_step_contract(base: dict, step) -> dict:
    """既存 <Agent>.yaml の構造を保ったまま per-Step 用に上書き。"""
    new_inputs: list[dict] = []
    required_paths = set((step.required_input_paths or []))
    for inp in (base.get("inputs") or []):
        if not isinstance(inp, dict):
            continue
        new = dict(inp)
        p = (new.get("path") or "").strip()
        if p in required_paths and new.get("required") is not True:
            new["required"] = True
        new_inputs.append(new)

    new_outputs: list[dict] = []
    out_paths = step_outputs(step)
    if out_paths:
        # 既存 outputs から path → mode を辞書化（mode 情報を保持）
        base_modes: dict[str, str] = {}
        for o in (base.get("outputs") or []):
            if isinstance(o, dict):
                bp = (o.get("path") or "").strip()
                if bp:
                    base_modes[bp] = str(o.get("mode") or "create")
        for p in out_paths:
            mode = base_modes.get(p, "create")
            new_outputs.append({"path": p, "required": True, "mode": mode})
    else:
        # output_paths/template 未宣言 → 既存 outputs をそのまま継承
        new_outputs = list(base.get("outputs") or [])

    return {"inputs": new_inputs, "outputs": new_outputs}


def main() -> int:
    # 1. 既存 per-Agent YAML を読み込み（agent_name -> contract）
    agent_contracts: dict[str, dict] = {}
    for fp in sorted(IOC.glob("*.yaml")):
        if "--" in fp.stem:  # 既に per-Step 形式のファイルはスキップ
            continue
        agent_contracts[fp.stem] = load_yaml(fp)

    # 2. 全 StepDef を per-Step YAML として出力
    generated: list[str] = []
    missing_base: list[str] = []
    for wf in list_workflows():
        wf_id = wf.id
        for step in wf.steps:
            if getattr(step, "is_container", False):
                continue
            agent = getattr(step, "custom_agent", None)
            if not agent:
                continue
            base = agent_contracts.get(agent)
            if base is None:
                missing_base.append(f"{wf_id}/{step.id}: {agent}")
                continue
            new_contract = build_per_step_contract(base, step)
            out_fp = IOC / step_filename(agent, wf_id, step.id)
            emit_yaml(out_fp, new_contract)
            generated.append(out_fp.name)

    print(f"Generated: {len(generated)}")
    if missing_base:
        print(f"WARN missing base contracts ({len(missing_base)}):")
        for m in missing_base:
            print(f"  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
