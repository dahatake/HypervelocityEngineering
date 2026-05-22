"""validate-io-contract.py

Validates the `io_contract:` frontmatter block of every `.github/agents/*.agent.md`
file against the schema defined in `.github/agents/CONTRIBUTING.md`, and checks
producer/consumer integrity across the agent catalog.

Exit codes:
  0: all valid
  1: schema or integrity errors detected

Usage:
  python .github/scripts/validate-io-contract.py [--verbose]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".github" / "agents"
EXCEPTIONS_FILE = REPO_ROOT / ".github" / "io-contract-exceptions.yaml"

VALID_INPUT_KINDS = {"agent_artifact", "static", "runtime_param", "external"}
VALID_OUTPUT_MODES = {"create", "append", "overwrite", "upsert"}
VALID_BOOLS = {True, False}


def load_exceptions() -> dict:
    if not EXCEPTIONS_FILE.exists():
        return {"static_paths": [], "external_paths": [], "skip_agents": []}
    with EXCEPTIONS_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def extract_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, "no frontmatter"
    end = text.find("\n---\n", 4)
    if end == -1:
        end = text.find("\n---", 4)
        if end == -1:
            return None, "unterminated frontmatter"
    fm_text = text[4:end]
    try:
        return yaml.safe_load(fm_text), ""
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"


def validate_io_contract(agent_name: str, fm: dict) -> list[str]:
    """Validate a single agent's io_contract structure. Returns list of errors."""
    errors: list[str] = []
    contract = fm.get("io_contract")
    if contract is None:
        return [f"{agent_name}: missing io_contract"]
    if not isinstance(contract, dict):
        return [f"{agent_name}: io_contract must be a mapping"]

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
            elif role_key == "outputs":
                if "mode" not in item:
                    errors.append(f"{agent_name}: outputs[{i}].mode missing")
                elif item["mode"] not in VALID_OUTPUT_MODES:
                    errors.append(f"{agent_name}: outputs[{i}].mode invalid: {item['mode']}")

    return errors


def collect_producers(agents: dict[str, dict]) -> dict[str, list[str]]:
    """Build map: output_path -> [agent names that produce it]."""
    producers: dict[str, list[str]] = defaultdict(list)
    for name, fm in agents.items():
        for out in (fm.get("io_contract") or {}).get("outputs") or []:
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

    for name, fm in agents.items():
        if name in skip:
            continue
        for inp in (fm.get("io_contract") or {}).get("inputs") or []:
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
    exceptions = load_exceptions()

    agents: dict[str, dict] = {}
    schema_errors: list[str] = []
    for fp in sorted(AGENTS_DIR.glob("*.agent.md")):
        if fp.name.startswith("_"):
            continue
        agent_name = fp.stem.replace(".agent", "")
        text = fp.read_text(encoding="utf-8")
        fm, err = extract_frontmatter(text)
        if err:
            schema_errors.append(f"{agent_name}: {err}")
            continue
        if not isinstance(fm, dict):
            schema_errors.append(f"{agent_name}: frontmatter not a mapping")
            continue
        agents[agent_name] = fm
        schema_errors.extend(validate_io_contract(agent_name, fm))

    producers = collect_producers(agents)
    integrity_errors = check_integrity(agents, producers, exceptions)

    all_errors = schema_errors + integrity_errors
    print(f"Agents checked: {len(agents)}")
    print(f"Schema errors: {len(schema_errors)}")
    print(f"Integrity errors: {len(integrity_errors)}")

    if verbose or all_errors:
        for e in all_errors:
            print(f"  ERROR: {e}")

    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
