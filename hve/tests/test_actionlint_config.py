"""Local actionlint configuration must stay narrow and repository-specific."""
from __future__ import annotations

from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _REPO_ROOT / ".github" / "actionlint.yaml"
_QUEUE_WORKFLOWS = {
    ".github/workflows/auto-ai-agent-design-reusable.yml",
    ".github/workflows/auto-ai-agent-dev-reusable.yml",
}
_QUEUE_DIAGNOSTIC = 'unexpected key "queue" for "concurrency" section'


def _config() -> dict:
    return yaml.load(_CONFIG.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_self_hosted_runner_label_is_declared() -> None:
    assert _config()["self-hosted-runner"]["labels"] == ["aca"]


def test_queue_compatibility_ignores_are_scoped_to_two_workflows() -> None:
    paths = _config()["paths"]
    assert set(paths) == _QUEUE_WORKFLOWS
    for rule in paths.values():
        assert rule == {"ignore": [_QUEUE_DIAGNOSTIC]}


def test_queue_compatibility_ignores_match_actual_usage() -> None:
    actual = {
        path.relative_to(_REPO_ROOT).as_posix()
        for path in (_REPO_ROOT / ".github" / "workflows").glob("*.y*ml")
        if "queue: max" in path.read_text(encoding="utf-8")
    }
    assert actual == _QUEUE_WORKFLOWS
    for relative in actual:
        text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
        assert text.count("queue: max") == 2
        assert text.count("cancel-in-progress: false") == 2
