"""Generate the heredoc JSON of .github/scripts/bash/lib/workflow-registry.sh (FR-CLOUD-06).

Each ``_WORKFLOW_REGISTRY[<id>]`` heredoc body is rebuilt from ``hve/workflow_registry.py``.
Only ``name`` keeps the value already in the Bash file, because Cloud and CLI / GUI
keep their own display names. The header comments and shell functions are maintained by hand.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hve.workflow_registry import get_workflow  # noqa: E402

BASH_REGISTRY = ROOT / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"

_HEREDOC = re.compile(
    r"(_WORKFLOW_REGISTRY\[([^\]]+)\]=\$\(cat <<'JSONEOF'(\r?\n))(.*?)(\r?\nJSONEOF)",
    re.DOTALL,
)
_STEP_KEYS = (
    "id",
    "title",
    "custom_agent",
    "depends_on",
    "is_container",
    "skip_fallback_deps",
    "block_unless",
    "body_template_path",
)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _body(workflow_id: str, name: str, newline: str) -> str:
    wf = get_workflow(workflow_id)
    if wf is None or wf.id != workflow_id:
        raise SystemExit(f"workflow '{workflow_id}' is not defined in hve/workflow_registry.py")
    labels = [f"    {_dump(k)}: {_dump(v)}" for k, v in wf.state_labels.items()]
    steps = [
        "    "
        + json.dumps(
            {k: getattr(step, k) for k in _STEP_KEYS},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for step in wf.steps
    ]
    lines = [
        "{",
        f'  "id": {_dump(wf.id)},',
        f'  "name": {_dump(name)},',
        f'  "label_prefix": {_dump(wf.label_prefix)},',
        '  "state_labels": {',
        ("," + newline).join(labels),
        "  },",
        f'  "params": {_dump(wf.params)},',
        '  "steps": [',
        ("," + newline).join(steps),
        "  ]",
        "}",
    ]
    return newline.join(lines)


def render(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        head, workflow_id, newline, body, tail = match.groups()
        name = json.loads(body)["name"]
        return head + _body(workflow_id, name, newline) + tail

    rendered, count = _HEREDOC.subn(replace, text)
    if count == 0:
        raise SystemExit("no _WORKFLOW_REGISTRY heredoc found")
    return rendered


def main() -> int:
    with BASH_REGISTRY.open(encoding="utf-8", newline="") as f:
        text = f.read()
    with BASH_REGISTRY.open("w", encoding="utf-8", newline="") as f:
        f.write(render(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
