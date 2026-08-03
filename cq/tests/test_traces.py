"""Contracts for the reference graph and doc traceability (FR-CQ-07)."""

from __future__ import annotations

import ast
import json
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import config, indexer, search, store, traces

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "hve-dev" / "generate_tdd_inventory.py"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text(
        "import os\n"
        "from pkg import helper\n"
        "\n"
        "\n"
        "def run():\n"
        "    # FR-MAINT-07 の判定をここで行う\n"
        "    return helper.assist(os.sep)\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "tests.cs").write_text(
        "public sealed class Probe\n"
        "{\n"
        "    // 出典: docs/test-specs/SVC-02-test-spec.md#TEST-SVC-02-001\n"
        "    public void Case1() { }\n"
        "}\n",
        encoding="utf-8",
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite")
    return tmp_path


def _rows(repo: Path, sql: str, *params) -> list[tuple]:
    with closing(store.open_store(repo / ".cq" / "index-test.sqlite", create=False)) as conn:
        return [tuple(r) for r in conn.execute(sql, params)]


class TestPatternsAreSingleSourced:
    def test_generator_does_not_redeclare_the_feature_id_pattern(self) -> None:
        """規範 ID の抽出パターンを二重定義しない（FR-CQ-07 / FR-MAINT-06）。"""
        tree = ast.parse(GENERATOR.read_text(encoding="utf-8-sig"))
        assigned = {
            node.targets[0].id
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        }
        assert "FEATURE_ID_RE" not in assigned

    def test_generator_imports_the_shared_pattern(self) -> None:
        tree = ast.parse(GENERATOR.read_text(encoding="utf-8-sig"))
        imported = {
            (node.module, alias.name)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert ("cq.traces", "FEATURE_ID_RE") in imported

    def test_generator_still_resolves_the_pattern_at_runtime(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_tdd_inventory", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.FEATURE_ID_RE == traces.FEATURE_ID_RE


class TestExtraction:
    @pytest.mark.parametrize(("line", "expected"), [
        ("# 出典: docs/test-specs/SVC-02-test-spec.md#TEST-SVC-02-001",
         ("TEST-SVC-02-001", "docs/test-specs/SVC-02-test-spec.md", "#TEST-SVC-02-001")),
        ("// 出典: docs/a.md#UT-SVC03-004", ("UT-SVC03-004", "docs/a.md", "#UT-SVC03-004")),
    ])
    def test_source_references_yield_id_path_and_anchor(self, line, expected) -> None:
        found = traces.extract(line)
        assert (found[0].trace_id, found[0].doc_path, found[0].anchor) == expected

    @pytest.mark.parametrize("text", ["FR-MAINT-07", "NFR-CTX-01", "APP-009", "SVC-02", "UC-12"])
    def test_bare_identifiers_are_extracted(self, text: str) -> None:
        assert [t.trace_id for t in traces.extract(f"see {text} for details")] == [text]

    def test_line_numbers_are_recorded(self) -> None:
        found = traces.extract("x\ny\n# 出典: docs/a.md#TEST-A-001\n")
        assert found[0].line == 3

    def test_unrelated_text_yields_nothing(self) -> None:
        assert traces.extract("just a normal comment") == ()

    def test_extraction_is_deterministic(self) -> None:
        text = "# FR-MAINT-07\n# 出典: docs/a.md#TEST-A-001\n"
        assert traces.extract(text) == traces.extract(text)


class TestIndexedGraph:
    def test_imports_are_recorded(self, repo: Path) -> None:
        modules = {r[0] for r in _rows(repo, "SELECT module FROM imports WHERE path='pkg/core.py'")}
        assert {"os", "pkg"} <= modules

    def test_references_are_recorded(self, repo: Path) -> None:
        names = {r[0] for r in _rows(repo, "SELECT name FROM refs WHERE path='pkg/core.py'")}
        assert "assist" in names

    def test_traces_are_recorded_with_doc_targets(self, repo: Path) -> None:
        rows = _rows(
            repo,
            "SELECT trace_id, doc_path, anchor FROM traces WHERE path='pkg/tests.cs'",
        )
        assert ("TEST-SVC-02-001", "docs/test-specs/SVC-02-test-spec.md", "#TEST-SVC-02-001") in rows

    def test_bare_requirement_ids_are_recorded(self, repo: Path) -> None:
        rows = {r[0] for r in _rows(repo, "SELECT trace_id FROM traces WHERE path='pkg/core.py'")}
        assert "FR-MAINT-07" in rows

    def test_graph_rows_are_pruned_with_their_file(self, repo: Path) -> None:
        (repo / "pkg" / "core.py").unlink()
        profile = config.resolve_profile(repo, "test")
        indexer.build_index(repo, profile, db_path=repo / ".cq" / "index-test.sqlite")
        assert _rows(repo, "SELECT count(*) FROM refs WHERE path='pkg/core.py'") == [(0,)]
        assert _rows(repo, "SELECT count(*) FROM imports WHERE path='pkg/core.py'") == [(0,)]
        assert _rows(repo, "SELECT count(*) FROM traces WHERE path='pkg/core.py'") == [(0,)]


class TestTraceLookup:
    def test_trace_id_resolves_to_a_code_location(self, repo: Path) -> None:
        hits = search.search(
            repo, "test", query="TEST-SVC-02-001",
            db_path=repo / ".cq" / "index-test.sqlite",
        )
        assert hits[0].route == "trace"
        assert hits[0].path == "pkg/tests.cs"
        assert hits[0].lines == [3, 3]

    def test_trace_hit_points_at_the_design_document(self, repo: Path) -> None:
        hit = search.search(
            repo, "test", query="TEST-SVC-02-001",
            db_path=repo / ".cq" / "index-test.sqlite",
        )[0]
        payload = hit.to_dict()
        assert payload["doc_path"] == "docs/test-specs/SVC-02-test-spec.md"
        assert payload["anchor"] == "#TEST-SVC-02-001"

    def test_reverse_lookup_from_a_path(self, repo: Path) -> None:
        found = traces.for_path(
            repo / ".cq" / "index-test.sqlite", "pkg/tests.cs"
        )
        assert [(t["trace_id"], t["doc_path"]) for t in found] == [
            ("TEST-SVC-02-001", "docs/test-specs/SVC-02-test-spec.md")
        ]

    def test_design_document_body_is_not_returned(self, repo: Path) -> None:
        """設計文書の本文取得は mdq の担当（FR-CQ-01）。"""
        found = traces.for_path(repo / ".cq" / "index-test.sqlite", "pkg/tests.cs")
        assert set(found[0]) == {"path", "line", "trace_id", "doc_path", "anchor"}


class TestRefsCommand:
    def test_refs_lists_call_sites(self, repo: Path) -> None:
        found = traces.references(
            repo / ".cq" / "index-test.sqlite", "assist", top_k=10
        )
        assert [(r["path"], r["line"]) for r in found] == [("pkg/core.py", 7)]


class TestCli:
    def _args(self, repo: Path) -> list[str]:
        return ["--profile", "test", "--repo-root", str(repo),
                "--db", str(repo / ".cq" / "index-test.sqlite")]

    def test_refs_command(self, repo: Path, capsys) -> None:
        from cq import cli

        assert cli.main(["refs", "--symbol", "assist", *self._args(repo)]) == 0
        row = json.loads(capsys.readouterr().out.splitlines()[0])
        assert (row["path"], row["line"]) == ("pkg/core.py", 7)

    def test_trace_by_id_command(self, repo: Path, capsys) -> None:
        from cq import cli

        assert cli.main(["trace", "--id", "TEST-SVC-02-001", *self._args(repo)]) == 0
        row = json.loads(capsys.readouterr().out.splitlines()[0])
        assert row["path"] == "pkg/tests.cs"
        assert row["doc_path"] == "docs/test-specs/SVC-02-test-spec.md"

    def test_trace_by_path_command(self, repo: Path, capsys) -> None:
        from cq import cli

        assert cli.main(["trace", "--by-path", "pkg/tests.cs", *self._args(repo)]) == 0
        row = json.loads(capsys.readouterr().out.splitlines()[0])
        assert row["anchor"] == "#TEST-SVC-02-001"
