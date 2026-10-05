"""FR-CQ-12: code-query Skill の配線と mdq からの隔離。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".github/skills/code-query/SKILL.md"
CLI_REFERENCE = SKILL.parent / "references/cli-reference.md"
INDEXING_INTERNALS = SKILL.parent / "references/indexing-internals.md"
HVE_INTEGRATION = SKILL.parent / "references/repo-specific/hve-integration.md"
MDQ_SKILL = REPO_ROOT / ".github/skills/markdown-query/SKILL.md"
ROUTING = REPO_ROOT / ".github/skills/_routing/README.md"
INSTRUCTIONS = REPO_ROOT / ".github/copilot-instructions.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_joined(*paths: Path) -> str:
    return "\n".join(_read(path) for path in paths)


def _imports_package(source: str, package: str) -> bool:
    """Does ``source`` import ``package`` in any form the interpreter accepts?

    Both `import X` and `from X import Y` must match; a substring check for
    ``"import X"`` alone silently misses the second form. The word boundary keeps
    a prose mention such as ``mdq.watcher`` in a docstring from counting.
    `importlib.import_module("X")` is out of scope: neither package uses it for
    the other today, and a dynamic form cannot be decided from the text alone.
    """
    pattern = rf"^[ \t]*(?:import|from)[ \t]+{re.escape(package)}\b"
    return re.search(pattern, source, re.MULTILINE) is not None


class TestSkillDefinition:
    def test_skill_file_exists(self) -> None:
        assert SKILL.is_file()

    @pytest.mark.parametrize("marker", ["USE FOR:", "PREFER OVER", "DO NOT USE FOR:", "WHEN:"])
    def test_frontmatter_declares_selection_markers(self, marker: str) -> None:
        head = _read(SKILL).split("---", 2)[1]
        assert marker in head

    def test_frontmatter_has_name_and_version(self) -> None:
        head = _read(SKILL).split("---", 2)[1]
        assert "name: code-query" in head
        assert "version:" in head

    def test_progressive_disclosure_references_exist(self) -> None:
        body = _read(SKILL)
        for reference in ("references/cli-reference.md", "references/indexing-internals.md", "references/repo-specific/hve-integration.md"):
            assert reference in body
            assert (SKILL.parent / reference).is_file()

    def test_shortest_invocation_examples_use_real_arguments(self) -> None:
        """`def` / `refs` は --q ではなく --symbol を取る。誤例を配ると Agent が失敗する。"""
        body = _read(SKILL)
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("python -m cq def") or stripped.startswith("python -m cq refs"):
                assert "--symbol" in stripped, stripped
                assert "--q " not in stripped, stripped

    def test_documented_symbols_actually_exist(self) -> None:
        """SKILL.md / cli-reference.md に載せる識別子は実在しなければならない（捏造禁止）。"""
        import re

        sources = _read(SKILL) + _read(SKILL.parent / "references/cli-reference.md")
        symbols = set(re.findall(r"--symbol \"([^\"]+)\"", sources))
        assert symbols, "検証対象の例が 1 つも無い"
        repo_sources = "\n".join(
            path.read_text(encoding="utf-8-sig", errors="ignore")
            for path in (REPO_ROOT / "hve").rglob("*.py")
        )
        for symbol in symbols:
            name = symbol.rpartition(".")[2]
            assert re.search(rf"\b(def|class)\s+{re.escape(name)}\b", repo_sources), symbol

    def test_root_selection_contract_keeps_source_markdown_boundary(self) -> None:
        """root の短縮後も、Code と Markdown の選択境界は frontmatter から読めること。"""
        head = _read(SKILL).split("---", 2)[1]
        prefer_clause = re.search(r"PREFER OVER(?P<clause>.*?)(?:DO NOT USE FOR:)", head, re.DOTALL)
        assert prefer_clause is not None
        assert all(token in prefer_clause.group("clause") for token in ("read_file", "grep_search", "source files"))
        assert "markdown lookup (use markdown-query)" in head
        assert "where something lives or what calls what" in head

    def test_reference_examples_for_def_and_refs_use_symbol_arguments(self) -> None:
        """root だけでなく、CLI / HVE-specific 例でも refs/def は --symbol を使う。"""
        examples: list[str] = []
        for path in (CLI_REFERENCE, HVE_INTEGRATION):
            for line in _read(path).splitlines():
                stripped = line.strip()
                if stripped.startswith("python -m cq def") or stripped.startswith("python -m cq refs"):
                    examples.append(stripped)
                    assert "--symbol" in stripped, stripped
                    assert "--q " not in stripped, stripped
        assert any("python -m cq def" in example for example in examples)
        assert any("python -m cq refs" in example for example in examples)

    def test_filter_match_profile_and_freshness_guidance_survives_reference_split(self) -> None:
        """root から詳細を逃がしても、Agent が必要な CLI 契約へ辿れること。"""
        docs = _read_joined(SKILL, CLI_REFERENCE, INDEXING_INTERNALS, HVE_INTEGRATION)
        for token in ("--profile", "--paths", "--max-tokens", "--return-unit"):
            assert token in docs
        for token in ("match", "or-fallback", "name-fallback", "stale", "--auto-reindex-limit"):
            assert token in docs
        for token in ("refs", "traces", "chunks_fts", "files"):
            assert token in _read(INDEXING_INTERNALS)


class TestRoutingRegistration:
    def test_routing_table_lists_the_skill(self) -> None:
        body = _read(ROUTING)
        assert "`code-query`" in body
        assert ".github/skills/code-query/SKILL.md" in body

    def test_instructions_declare_source_search_default(self) -> None:
        body = _read(INSTRUCTIONS)
        assert "code-query" in body
        assert "python -m cq search" in body


class TestMutualExclusionWithMarkdownQuery:
    def test_markdown_query_points_at_code_query(self) -> None:
        body = _read(MDQ_SKILL)
        assert "code-query" in body

    def test_code_query_points_at_markdown_query(self) -> None:
        body = _read(SKILL)
        assert "markdown-query" in body


class TestIsolationFromMarkdownQuery:
    """`cq` 導入で `mdq` の検索品質が変わらないことの構造的保証。"""

    def test_cq_does_not_index_markdown(self) -> None:
        from cq.languages import LANGUAGE_BY_SUFFIX

        assert ".md" not in LANGUAGE_BY_SUFFIX
        assert ".markdown" not in LANGUAGE_BY_SUFFIX

    def test_cq_database_path_is_separate_from_mdq(self) -> None:
        from cq.store import db_path_for

        path = db_path_for("hve")
        assert path.parts[0] == ".cq"
        assert ".mdq" not in str(path)

    def test_cq_package_does_not_import_mdq(self) -> None:
        offenders = [
            source.relative_to(REPO_ROOT).as_posix()
            for source in (REPO_ROOT / "cq").rglob("*.py")
            if _imports_package(source.read_text(encoding="utf-8"), "mdq")
        ]
        assert offenders == []

    @pytest.mark.parametrize(
        "source",
        ["import mdq", "import mdq.tokens", "from mdq import tokens", "from mdq.search import x"],
    )
    def test_import_guard_catches_every_import_form(self, source: str) -> None:
        """`from X import Y` を見逃すと、最も一般的な形式の結合が素通りする。"""
        assert _imports_package(source, "mdq")

    def test_mdq_package_is_unmodified_by_cq(self) -> None:
        offenders = [
            source.relative_to(REPO_ROOT).as_posix()
            for source in (REPO_ROOT / "mdq").rglob("*.py")
            if _imports_package(source.read_text(encoding="utf-8"), "cq")
        ]
        assert offenders == []
