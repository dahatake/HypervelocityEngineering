"""validate-io-contract.py

Validates every `.github/io-contracts/*.yaml` file against the schema defined
in `.github/io-contracts/SCHEMA.md`, and checks producer/consumer integrity
across the agent catalog.

Each YAML file is named `<AgentName>.yaml` and contains the io_contract directly
(i.e. top-level keys are `inputs:` and `outputs:`).

Also cross-checks the io-contracts against `hve/workflow_registry.py` StepDefs
to detect declaration drift between the two systems (registry_mismatch).

Exit codes:
  0: all valid
  1: schema, integrity, or registry-mismatch errors detected

Usage:
  python .github/scripts/validate-io-contract.py [--verbose] [--no-registry-check]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
IO_CONTRACTS_DIR = REPO_ROOT / ".github" / "io-contracts"
EXCEPTIONS_FILE = REPO_ROOT / ".github" / "io-contract-exceptions.yaml"

VALID_INPUT_KINDS = {"agent_artifact", "static", "runtime_param", "external"}
VALID_OUTPUT_MODES = {"create", "append", "overwrite", "upsert"}
VALID_BOOLS = {True, False}


def load_exceptions() -> dict:
    if not EXCEPTIONS_FILE.exists():
        return {"static_paths": [], "external_paths": [], "skip_agents": []}
    with EXCEPTIONS_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_io_contract(path: Path) -> tuple[dict | None, str]:
    """Load io_contract YAML. Returns (contract_dict, error_message)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"
    except OSError as e:
        return None, f"I/O error: {e}"
    if data is None:
        return None, "empty file"
    if not isinstance(data, dict):
        return None, "io_contract must be a mapping"
    return data, ""


def validate_io_contract(agent_name: str, contract: dict) -> list[str]:
    """Validate a single agent's io_contract structure. Returns list of errors."""
    errors: list[str] = []

    for role_key in ("inputs", "outputs"):
        items = contract.get(role_key)
        if items is None:
            errors.append(f"{agent_name}: missing io_contract.{role_key}")
            continue
        if not isinstance(items, list):
            errors.append(f"{agent_name}: io_contract.{role_key} must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{agent_name}: {role_key}[{i}] must be a mapping")
                continue
            if "path" not in item:
                errors.append(f"{agent_name}: {role_key}[{i}].path missing")
            if "required" not in item:
                errors.append(f"{agent_name}: {role_key}[{i}].required missing")
            elif item["required"] not in VALID_BOOLS:
                errors.append(f"{agent_name}: {role_key}[{i}].required must be bool")
            if role_key == "inputs":
                if "kind" not in item:
                    errors.append(f"{agent_name}: inputs[{i}].kind missing")
                elif item["kind"] not in VALID_INPUT_KINDS:
                    errors.append(f"{agent_name}: inputs[{i}].kind invalid: {item['kind']}")
                # producer requirement: required=true && kind=agent_artifact => producer must be non-empty string
                if (
                    item.get("required") is True
                    and item.get("kind") == "agent_artifact"
                ):
                    prod = item.get("producer")
                    if not isinstance(prod, str) or prod.strip() == "":
                        errors.append(
                            f"{agent_name}: inputs[{i}].producer must be non-empty "
                            f"when required=true and kind=agent_artifact (path={item.get('path')!r})"
                        )
            elif role_key == "outputs":
                if "mode" not in item:
                    errors.append(f"{agent_name}: outputs[{i}].mode missing")
                elif item["mode"] not in VALID_OUTPUT_MODES:
                    errors.append(f"{agent_name}: outputs[{i}].mode invalid: {item['mode']}")

    return errors


def collect_producers(agents: dict[str, dict]) -> dict[str, list[str]]:
    """Build map: output_path -> [agent names that produce it]."""
    producers: dict[str, list[str]] = defaultdict(list)
    for name, contract in agents.items():
        for out in contract.get("outputs") or []:
            if isinstance(out, dict) and out.get("path"):
                producers[out["path"]].append(name)
    return producers


def check_integrity(agents: dict[str, dict], producers: dict[str, list[str]], exc: dict) -> list[str]:
    """Verify required agent_artifact inputs have a matching producer.

    Matching strategy (in order):
      1. Exact path match
      2. Wildcard match: if input contains '*', glob-match against producer paths
      3. Basename match: if input has no '/', match producers by file basename
    """
    import fnmatch

    errors: list[str] = []
    skip = set(exc.get("skip_agents") or [])
    static_paths = set(exc.get("static_paths") or [])
    external_paths = set(exc.get("external_paths") or [])
    # Build basename index for fallback matching
    basename_to_paths: dict[str, list[str]] = defaultdict(list)
    for p in producers:
        bn = p.rsplit("/", 1)[-1] if "/" in p else p
        basename_to_paths[bn].append(p)

    def find_producers(path: str) -> list[str]:
        # 1. Exact
        if path in producers:
            return producers[path]
        # 2. Wildcard
        if "*" in path:
            matches = [p for p in producers if fnmatch.fnmatchcase(p, path)]
            if matches:
                return sum((producers[m] for m in matches), [])
        # 3. Basename fallback (only if path has no '/')
        if "/" not in path:
            if path in basename_to_paths:
                return sum((producers[p] for p in basename_to_paths[path]), [])
        return []

    for name, contract in agents.items():
        # per-Step filename: <Agent>--<workflow>--<stepId>. Skip-match against either basename or Agent name.
        agent_short = name.split("--", 1)[0]
        if name in skip or agent_short in skip:
            continue
        for inp in contract.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            path = inp.get("path")
            required = inp.get("required") is True
            kind = inp.get("kind")
            if not (required and kind == "agent_artifact"):
                continue
            if path in static_paths or path in external_paths:
                continue
            # Skip obviously non-path noise (extraction artifacts)
            if not path or path.startswith("<") or "summary>" in path.lower():
                continue
            declared_producer = inp.get("producer", "")
            actual_producers = find_producers(path)
            if not actual_producers:
                errors.append(f"{name}: input '{path}' (required agent_artifact) has no producer in inventory")
            elif declared_producer and declared_producer not in actual_producers:
                errors.append(
                    f"{name}: input '{path}' declares producer '{declared_producer}' "
                    f"but actual producers are {actual_producers}"
                )
    return errors


def main() -> int:
    verbose = "--verbose" in sys.argv
    skip_registry = "--no-registry-check" in sys.argv
    exceptions = load_exceptions()

    agents: dict[str, dict] = {}
    schema_errors: list[str] = []
    if not IO_CONTRACTS_DIR.is_dir():
        print(f"ERROR: io-contracts directory not found: {IO_CONTRACTS_DIR}", file=sys.stderr)
        return 1
    for fp in sorted(IO_CONTRACTS_DIR.glob("*.yaml")):
        if fp.name.startswith("_"):
            continue
        agent_name = fp.stem
        contract, err = load_io_contract(fp)
        if err:
            schema_errors.append(f"{agent_name}: {err}")
            continue
        if not isinstance(contract, dict):
            schema_errors.append(f"{agent_name}: io_contract not a mapping")
            continue
        agents[agent_name] = contract
        schema_errors.extend(validate_io_contract(agent_name, contract))

    producers = collect_producers(agents)
    integrity_errors = check_integrity(agents, producers, exceptions)
    registry_mismatch_errors = (
        [] if skip_registry else check_registry_mismatch(agents)
    )

    all_errors = schema_errors + integrity_errors + registry_mismatch_errors
    print(f"Agents checked: {len(agents)}")
    print(f"Schema errors: {len(schema_errors)}")
    print(f"Integrity errors: {len(integrity_errors)}")
    if not skip_registry:
        print(f"Registry mismatch errors: {len(registry_mismatch_errors)}")

    if verbose or all_errors:
        for e in all_errors:
            print(f"  ERROR: {e}")

    return 0 if not all_errors else 1


def check_registry_mismatch(agents: dict[str, dict]) -> list[str]:
    """Cross-check io-contracts against hve/workflow_registry.py StepDefs.

    For each StepDef with a custom_agent, compares:
      - StepDef.required_input_paths  vs  io-contract inputs (required=true)
      - StepDef.output_paths + output_paths_template  vs  io-contract outputs

    Returns a list of mismatch error messages. Pure path-string comparison;
    placeholder normalization is not performed.
    """
    errors: list[str] = []
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from hve.workflow_registry import list_workflows  # type: ignore
    except Exception as e:  # pragma: no cover
        errors.append(f"registry import failed: {e}")
        return errors

    for wf in list_workflows():
        wf_id = wf.id
        for step in wf.steps:
            if getattr(step, "is_container", False):
                continue
            agent = getattr(step, "custom_agent", None)
            if not agent:
                continue
            # Per-Step file naming (Q-A2.1=A): <Agent>--<workflow>--<stepId>.yaml
            basename = f"{agent}--{wf_id}--{step.id}"
            contract = agents.get(basename)
            if contract is None:
                errors.append(
                    f"{wf_id}/{step.id}: per-Step io-contract '{basename}.yaml' not found"
                )
                continue

            ri = [
                i for i in (contract.get("inputs") or [])
                if i.get("required") is True and i.get("kind") == "agent_artifact"
            ]
            ri_paths = {(i.get("path") or "").strip() for i in ri}
            ao_paths = {
                (o.get("path") or "").strip()
                for o in (contract.get("outputs") or [])
            }
            step_in = {p.strip() for p in (step.required_input_paths or [])}
            step_out = {p.strip() for p in (step.output_paths or [])} | {
                p.strip() for p in (step.output_paths_template or [])
            }

            only_step_out = sorted(step_out - ao_paths)
            only_contract_out = sorted(ao_paths - step_out)
            only_step_in = sorted(step_in - ri_paths)
            only_contract_in = sorted(ri_paths - step_in)

            for p in only_step_out:
                errors.append(
                    f"{wf_id}/{step.id}({basename}): output '{p}' declared in StepDef but not in io-contract"
                )
            for p in only_contract_out:
                errors.append(
                    f"{wf_id}/{step.id}({basename}): output '{p}' declared in io-contract but not in StepDef"
                )
            for p in only_step_in:
                errors.append(
                    f"{wf_id}/{step.id}({basename}): required input '{p}' declared in StepDef but not in io-contract"
                )
            for p in only_contract_in:
                errors.append(
                    f"{wf_id}/{step.id}({basename}): required input '{p}' declared in io-contract but not in StepDef"
                )
    return errors


if __name__ == "__main__":
    sys.exit(main())

