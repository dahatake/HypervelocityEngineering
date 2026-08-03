"""FR-MAINT-06: 規範リテラルごとの判定実装が単一であること。

`.github/copilot-instructions.md` §0 が定める検証マーカー書式について、
判定ロジックが 1 実装へ集約され、他の実行面がそれを呼び出すことを固定する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hve.split_fork import has_validation_marker

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_VALIDATION = _REPO_ROOT / "hve" / "artifact_validation.py"
_MARKER_CLI = _REPO_ROOT / ".github" / "scripts" / "check_validation_marker.py"
_CLOUD_WORKFLOWS = (
    _REPO_ROOT / ".github" / "workflows" / "auto-approve-and-merge.yml",
    _REPO_ROOT / ".github" / "workflows" / "auto-qa-to-review-transition.yml",
)
_LOCAL_REGEX_NAMES = ("HEADING_REGEX", "BULLET_REGEX", "LEGACY_REGEX")

_HTML_MARKER = "<!-- validation-confirmed -->"
_HEADING_FORMS = ("## 検証", "### 検証結果", "# Validation")
_BULLET_FORMS = ("- 検証: pytest 12 passed", "* Validation: ran pytest", "- **検証**: pytest 12 passed")


class TestValidationMarkerDecision:
    """copilot-instructions.md §0 の 3 形式を単一実装が判定する。"""

    def test_html_comment_form_is_accepted(self) -> None:
        assert has_validation_marker(f"body\n{_HTML_MARKER}\n") is True

    @pytest.mark.parametrize("form", _HEADING_FORMS)
    def test_heading_form_is_accepted(self, form: str) -> None:
        assert has_validation_marker(f"body\n{form}\n- ran pytest\n") is True

    @pytest.mark.parametrize("form", _BULLET_FORMS)
    def test_bullet_form_is_accepted(self, form: str) -> None:
        assert has_validation_marker(f"body\n{form}\n") is True

    def test_missing_marker_is_rejected(self) -> None:
        assert has_validation_marker("no marker in this report\n") is False

    def test_html_comment_only_mode_rejects_prose_forms(self) -> None:
        assert has_validation_marker("## 検証\n- ran pytest\n", html_comment_only=True) is False
        assert has_validation_marker(f"x\n{_HTML_MARKER}\n", html_comment_only=True) is True


class TestSingleDecisionImplementation:
    def test_artifact_validation_delegates_instead_of_reimplementing(self) -> None:
        source = _ARTIFACT_VALIDATION.read_text(encoding="utf-8")
        assert f'"{_HTML_MARKER}" not in text' not in source, (
            "TDD report validation must reuse hve.split_fork.has_validation_marker"
        )
        assert "has_validation_marker" in source


class TestCloudSurfaceDelegatesMarkerDecision:
    """cloud 面が独自の判定を持たず、単一実装を呼び出すこと。"""

    def test_shared_entrypoint_exists(self) -> None:
        assert _MARKER_CLI.is_file()

    @pytest.mark.parametrize("workflow", _CLOUD_WORKFLOWS, ids=lambda path: path.name)
    def test_workflow_does_not_reimplement_marker_patterns(self, workflow: Path) -> None:
        source = workflow.read_text(encoding="utf-8")
        present = [name for name in _LOCAL_REGEX_NAMES if name in source]
        assert not present, f"{workflow.name} must delegate the decision instead of declaring {present}"

    @pytest.mark.parametrize("workflow", _CLOUD_WORKFLOWS, ids=lambda path: path.name)
    def test_workflow_calls_shared_entrypoint(self, workflow: Path) -> None:
        assert "check_validation_marker.py" in workflow.read_text(encoding="utf-8")

    def test_entrypoint_reports_presence_by_exit_code(self, tmp_path: Path) -> None:
        subject = tmp_path / "subject.md"
        subject.write_text("## 検証\n- ran pytest\n", encoding="utf-8")
        found = subprocess.run([sys.executable, str(_MARKER_CLI), "--text-file", str(subject)], check=False)
        assert found.returncode == 0

        subject.write_text("nothing relevant here\n", encoding="utf-8")
        missing = subprocess.run([sys.executable, str(_MARKER_CLI), "--text-file", str(subject)], check=False)
        assert missing.returncode == 1

    def test_entrypoint_supports_html_comment_only_mode(self, tmp_path: Path) -> None:
        subject = tmp_path / "subject.md"
        subject.write_text("## 検証\n- ran pytest\n", encoding="utf-8")
        strict = subprocess.run(
            [sys.executable, str(_MARKER_CLI), "--text-file", str(subject), "--html-comment-only"],
            check=False,
        )
        assert strict.returncode == 1
