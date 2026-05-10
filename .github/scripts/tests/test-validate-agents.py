#!/usr/bin/env python3
"""Unit tests for .github/scripts/validate-agents.py

Tests cover:
- extract_frontmatter
- get_description
- parse_tools_list
- main() behavior via subprocess (good and bad fixture files)

Run:
  pytest .github/scripts/tests/test-validate-agents.py -v
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "validate-agents.py"


# ---------------------------------------------------------------------------
# Import helpers from the script under test
# ---------------------------------------------------------------------------


def _import_script():
    """Import validate-agents module without executing main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_agents", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def va():
    return _import_script()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(extra_args: list[str], tmp_agents_dir: Path) -> tuple[int, str]:
    """Run validate-agents.py against a custom agents dir via subprocess."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)] + extra_args,
        capture_output=True,
        text=True,
        cwd=str(tmp_agents_dir),
    )
    return result.returncode, result.stdout + result.stderr


def _make_agent(tmp_path: Path, filename: str, content: str) -> Path:
    agents_dir = tmp_path / ".github" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    f = agents_dir / filename
    f.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# extract_frontmatter tests
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_valid(self, va):
        content = "---\nname: Test\n---\nbody"
        result = va.extract_frontmatter(content)
        assert result is not None
        assert "name: Test" in result

    def test_missing_open(self, va):
        assert va.extract_frontmatter("name: Test\n---\nbody") is None

    def test_missing_close(self, va):
        assert va.extract_frontmatter("---\nname: Test\nbody") is None

    def test_empty_frontmatter(self, va):
        # "---\n\n---\nbody" has a blank line between delimiters
        content = "---\n\n---\nbody"
        result = va.extract_frontmatter(content)
        assert result is not None
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# get_description tests
# ---------------------------------------------------------------------------


class TestGetDescription:
    def test_single_line(self, va):
        fm = 'name: X\ndescription: Short description here\n'
        assert va.get_description(fm) == "Short description here"

    def test_quoted(self, va):
        fm = 'description: "quoted desc"\n'
        assert va.get_description(fm) == "quoted desc"

    def test_missing(self, va):
        assert va.get_description("name: X\n") == ""

    def test_multiline_block(self, va):
        fm = "description: >\n  line one\n  line two\n"
        result = va.get_description(fm)
        assert "line one" in result
        assert "line two" in result


# ---------------------------------------------------------------------------
# parse_tools_list tests
# ---------------------------------------------------------------------------


class TestParseToolsList:
    def test_wildcard(self, va):
        fm = 'tools: ["*"]\n'
        assert va.parse_tools_list(fm) == ["*"]

    def test_list(self, va):
        fm = "tools: ['read', 'edit', 'search']\n"
        result = va.parse_tools_list(fm)
        assert result == ["read", "edit", "search"]

    def test_missing(self, va):
        assert va.parse_tools_list("name: X\n") is None

    def test_empty_list(self, va):
        fm = "tools: []\n"
        result = va.parse_tools_list(fm)
        assert result == []

    def test_block_list_format(self, va):
        """YAML block list format (- item) is correctly parsed."""
        fm = "name: X\ntools:\n  - read\n  - edit\n  - search\n"
        result = va.parse_tools_list(fm)
        assert result == ["read", "edit", "search"]

    def test_unquoted_inline(self, va):
        """Unquoted inline list [read, search] is correctly parsed."""
        fm = "tools: [read, search]\n"
        result = va.parse_tools_list(fm)
        assert result == ["read", "search"]


# ---------------------------------------------------------------------------
# Integration tests via subprocess
# ---------------------------------------------------------------------------


class TestGoodAgent:
    """A fully compliant agent produces no errors and exit code 0."""

    CONTENT = textwrap.dedent("""\
        ---
        name: TestGoodAgent
        description: Use this agent when you need to generate a comprehensive test report for the repository.
        model: claude-sonnet-4-5
        tools: ["read", "search"]
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    def test_no_error(self, tmp_path):
        base = _make_agent(tmp_path, "TestGoodAgent.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 0, out
        assert "Errors        : 0" in out

    def test_no_warnings_for_good_agent(self, tmp_path):
        base = _make_agent(tmp_path, "TestGoodAgent.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert "⚠️" not in out


class TestMissingName:
    CONTENT = textwrap.dedent("""\
        ---
        description: Use this agent when you need something done quickly and efficiently.
        tools: ["read"]
        ---
        # Body
    """)

    def test_error_on_missing_name(self, tmp_path):
        base = _make_agent(tmp_path, "NoName.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 1, out
        assert "Missing required field: 'name'" in out

    def test_strict_still_error(self, tmp_path):
        base = _make_agent(tmp_path, "NoName.agent.md", self.CONTENT)
        rc, out = _run(["--strict"], base)
        assert rc == 1, out


class TestMissingDescription:
    CONTENT = textwrap.dedent("""\
        ---
        name: NoDesc
        tools: ["read"]
        ---
        # Body
    """)

    def test_error_on_missing_description(self, tmp_path):
        base = _make_agent(tmp_path, "NoDesc.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 1, out
        assert "Missing required field: 'description'" in out


class TestMissingFrontmatter:
    CONTENT = "# No frontmatter at all\nJust body content."

    def test_error_on_missing_frontmatter(self, tmp_path):
        base = _make_agent(tmp_path, "NoFM.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 1, out
        assert "Missing or malformed frontmatter" in out


class TestDuplicateName:
    CONTENT_A = textwrap.dedent("""\
        ---
        name: DuplicateAgent
        description: Use this agent when you need to deduplicate entries in the system.
        tools: ["read"]
        metadata:
          version: "1.0.0"
        ---
        # A
    """)
    CONTENT_B = textwrap.dedent("""\
        ---
        name: DuplicateAgent
        description: Use this agent when you need to merge duplicate data sources.
        tools: ["read"]
        metadata:
          version: "1.0.0"
        ---
        # B
    """)

    def test_duplicate_name_is_error(self, tmp_path):
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "A.agent.md").write_text(self.CONTENT_A, encoding="utf-8")
        (agents_dir / "B.agent.md").write_text(self.CONTENT_B, encoding="utf-8")
        rc, out = _run([], tmp_path)
        assert rc == 1, out
        assert "Duplicate name" in out


class TestRecommendedFieldsAreWarnings:
    """Missing model/tools produce warnings (not errors) by default."""

    CONTENT = textwrap.dedent("""\
        ---
        name: NoModelNoTools
        description: Use this agent when you need to process data without any external tools.
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    def test_default_mode_no_error(self, tmp_path):
        base = _make_agent(tmp_path, "NoModelNoTools.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 0, out

    def test_default_mode_has_warnings(self, tmp_path):
        base = _make_agent(tmp_path, "NoModelNoTools.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert "Missing recommended field: 'model'" in out
        assert "Missing recommended field: 'tools'" in out

    def test_strict_mode_error(self, tmp_path):
        base = _make_agent(tmp_path, "NoModelNoTools.agent.md", self.CONTENT)
        rc, out = _run(["--strict"], base)
        assert rc == 1, out
        assert "Errors" in out


class TestToolsWildcard:
    """tools: ["*"] produces a warning but not an error."""

    CONTENT = textwrap.dedent("""\
        ---
        name: WildcardTools
        description: Use this agent when you need full access to all available tools.
        model: claude-sonnet-4-5
        tools: ["*"]
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    def test_wildcard_is_warning_not_error(self, tmp_path):
        base = _make_agent(tmp_path, "WildcardTools.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert rc == 0, out
        assert "wildcard" in out.lower() or "*" in out

    def test_wildcard_warning_in_strict(self, tmp_path):
        base = _make_agent(tmp_path, "WildcardTools.agent.md", self.CONTENT)
        rc, out = _run(["--strict"], base)
        # wildcard is always warning, never error even in strict
        assert rc == 0, out


class TestDescriptionQuality:
    """Short description and missing when-to-invoke are warnings."""

    SHORT_DESC = textwrap.dedent("""\
        ---
        name: ShortDesc
        description: Short
        model: claude-sonnet-4-5
        tools: ["read"]
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    NO_WHEN = textwrap.dedent("""\
        ---
        name: NoWhenDesc
        description: This agent processes documents and generates comprehensive analysis reports.
        model: claude-sonnet-4-5
        tools: ["read"]
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    def test_short_description_is_warning(self, tmp_path):
        base = _make_agent(tmp_path, "ShortDesc.agent.md", self.SHORT_DESC)
        rc, out = _run([], base)
        assert rc == 0, out
        assert "too short" in out.lower()

    def test_no_when_to_invoke_is_warning(self, tmp_path):
        base = _make_agent(tmp_path, "NoWhenDesc.agent.md", self.NO_WHEN)
        rc, out = _run([], base)
        assert rc == 0, out
        assert "when to invoke" in out.lower()


class TestSummaryOutput:
    """Summary block is always printed."""

    CONTENT = textwrap.dedent("""\
        ---
        name: SummaryTest
        description: Use this agent when you need to verify summary output in tests.
        model: claude-sonnet-4-5
        tools: ["read"]
        metadata:
          version: "1.0.0"
        ---
        # Body
    """)

    def test_summary_present(self, tmp_path):
        base = _make_agent(tmp_path, "SummaryTest.agent.md", self.CONTENT)
        rc, out = _run([], base)
        assert "Files checked" in out
        assert "Errors" in out
        assert "Warnings" in out


class TestMetadataVersion:
    """metadata.version is a required field."""

    MISSING_VERSION = textwrap.dedent("""\
        ---
        name: NoVersion
        description: Use this agent when you need to process data without version metadata.
        model: claude-sonnet-4-5
        tools: ["read"]
        ---
        # Body
    """)

    INVALID_VERSION = textwrap.dedent("""\
        ---
        name: BadVersion
        description: Use this agent when you need to process data with invalid version metadata.
        model: claude-sonnet-4-5
        tools: ["read"]
        metadata:
          version: "not-semver"
        ---
        # Body
    """)

    def test_missing_version_is_error(self, tmp_path):
        base = _make_agent(tmp_path, "NoVersion.agent.md", self.MISSING_VERSION)
        rc, out = _run([], base)
        assert rc == 1, out
        assert "metadata.version" in out

    def test_invalid_version_is_error(self, tmp_path):
        base = _make_agent(tmp_path, "BadVersion.agent.md", self.INVALID_VERSION)
        rc, out = _run([], base)
        assert rc == 1, out
        assert "metadata.version" in out
