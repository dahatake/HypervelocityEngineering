"""run_id path sanitizing keeps one rule implementation (hve/run_state.py).

The structural test only detects the same regex literal. A rule rewritten with
a different expression would not be detected.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hve import fork_kpi_logger, knowledge_files, run_state, runner

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RULE_LITERAL = r"[^A-Za-z0-9\-_]"
_NORMAL = "20260512T031415-abc123"
_TRAVERSAL = "../../etc/passwd-abc"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(_NORMAL, _NORMAL), (_TRAVERSAL, "etcpasswd-abc")],
)
def test_every_caller_keeps_the_same_allowed_characters(raw: str, expected: str, tmp_path: Path) -> None:
    assert run_state._safe_run_id_component(raw) == expected
    assert runner._safe_run_id(raw) == expected
    assert fork_kpi_logger._sanitize_run_id(raw) == expected
    rel, _ = knowledge_files.create_qa_document(tmp_path, run_id=raw, label="akm", text="# QA\n")
    assert rel == f"qa/{expected}-akm-knowledge-discovery-qa.md"


@pytest.mark.parametrize("raw", ["", "!!!"])
def test_empty_results_keep_each_caller_fallback(raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        run_state._safe_run_id_component(raw)
    monkeypatch.setattr(runner, "generate_run_id", lambda: "generated-id")
    assert runner._safe_run_id(raw) == "generated-id"
    assert fork_kpi_logger._sanitize_run_id(raw) == "unknown"
    rel, _ = knowledge_files.create_qa_document(tmp_path, run_id=raw, label="akm", text="# QA\n")
    assert rel == "qa/unknown-akm-knowledge-discovery-qa.md"


def test_rule_literal_has_a_single_implementation() -> None:
    out = subprocess.run(
        ["git", "grep", "-l", "-F", _RULE_LITERAL, "--", "hve/*.py", ":!hve/tests/*", ":!hve/gui/tests/*"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    assert out == ["hve/run_state.py"]
