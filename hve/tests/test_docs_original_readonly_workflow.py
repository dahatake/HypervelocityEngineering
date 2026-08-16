"""docs-original/ 読み取り専用 CI の契約テスト。

対応要件:
- NFR-SEC-02: docs-original/ は読み取り専用
- FR-WF-ADI-02: ADI は docs-original/ へ書き込まない
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "protect-readonly-paths.yml"


def _docs_original_check_script() -> str:
    workflow = yaml.load(_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    job = jobs.get("check-docs-original")
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    script = next(
        (
            step.get("run")
            for step in steps
            if isinstance(step, dict)
            and step.get("name") == "docs-original/ 配下の変更を検出"
        ),
        None,
    )
    assert isinstance(script, str)
    return script


def test_docs_original_changes_remain_fail_closed() -> None:
    script = _docs_original_check_script()

    assert "set -euo pipefail" in script
    assert 'gh api "repos/${REPO}/pulls/${PR_NUMBER}/files" --paginate' in script
    assert "READONLY_VIOLATIONS" in script
    assert "exit 1" in script
    assert "docs-original/ 配下の許可されていない変更" in script


def test_only_same_path_legacy_rename_is_exempted() -> None:
    script = _docs_original_check_script()

    allowed_rename = re.compile(
        r'if \[ "\$\{status\}" = "renamed" \] \\\n+'
        r'\s+&& \[\[ "\$\{filename\}" == docs-original/\* \]\] \\\n+'
        r'\s+&& \[\[ "\$\{previous_filename\}" == original-docs/\* \]\] \\\n+'
        r'\s+&& \[ "\$\{source_relative\}" = "\$\{destination_relative\}" \]; then\n'
        r'\s+echo "ℹ️ 初回原本移行を許可: \$\{previous_filename\} -> \$\{filename\}"\n'
        r'\s+continue',
    )
    assert allowed_rename.search(script)