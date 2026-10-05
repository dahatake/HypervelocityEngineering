"""FR-CLOUD-06: the Bash registry heredocs are generated from hve/workflow_registry.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "hve-dev" / "generate_workflow_registry_sh.py"
BASH_REGISTRY = REPO_ROOT / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_workflow_registry_sh", GENERATOR)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bash_registry_matches_generated_output() -> None:
    with BASH_REGISTRY.open(encoding="utf-8", newline="") as f:
        current = f.read()
    assert _load_generator().render(current) == current, (
        "workflow-registry.sh の heredoc JSON が hve/workflow_registry.py と一致しない。"
        "直接編集せず `python hve-dev/generate_workflow_registry_sh.py` を実行する"
    )
