"""RED contracts for the local Repository Query tools (FR-RQ-02/NFR-RQ-01)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import pytest
from mdq import tokens as mdq_tokens

from hve.repository_query_tools import (
    EvidenceLedger,
    RepositoryQueryInputError,
    RepositoryQueryLimitError,
    RepositoryQuerySourceError,
    RepositoryQueryTools,
)

Hit = dict[str, Any]


class Search(Protocol):
    def __call__(
        self,
        query: str,
        *,
        paths: tuple[str, ...],
        top_k: int,
        max_tokens: int,
    ) -> list[Hit]: ...


class Getter(Protocol):
    def __call__(self, chunk_id: str) -> Hit | None: ...


class References(Protocol):
    def __call__(self, symbol: str, *, top_k: int) -> list[Hit]: ...


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\ncontract\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    return 1\n\ndef helper():\n    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "other.py").write_text("def other():\n    return 2\n", encoding="utf-8")
    return tmp_path


def _markdown_hit() -> Hit:
    return {
        "chunk_id": "md-1",
        "path": "docs/spec.md",
        "lines": [1, 2],
        "snippet": "# Spec\ncontract",
        "heading_path": "Spec",
    }


def _code_hit() -> Hit:
    return {
        "chunk_id": "cq-1",
        "path": "pkg/service.py",
        "lines": [1, 2],
        "snippet": "def run():\n    return 1",
        "parser": "ast",
    }


def _tools(
    repo_root: Path,
    *,
    markdown_search: Search | None = None,
    markdown_get: Getter | None = None,
    code_search: Search | None = None,
    code_get: Getter | None = None,
    code_references: References | None = None,
) -> RepositoryQueryTools:
    return RepositoryQueryTools(
        repo_root=repo_root,
        markdown_search=markdown_search or (lambda *args, **kwargs: [_markdown_hit()]),
        markdown_get=markdown_get or (
            lambda chunk_id: {
                **_markdown_hit(),
                "text": "# Spec\ncontract\nfull markdown",
            }
        ),
        code_search=code_search or (lambda *args, **kwargs: [_code_hit()]),
        code_get=code_get or (
            lambda chunk_id: {
                **_code_hit(),
                "text": "def run():\n    return 1\n# full code",
            }
        ),
        code_references=code_references or (
            lambda symbol, *, top_k: [
                {"path": "pkg/service.py", "line": 1, "name": symbol}
            ]
        ),
    )


class TestEvidenceLedger:
    def test_assigns_stable_refs_and_deduplicates(self, repo_root: Path) -> None:
        ledger = EvidenceLedger(repo_root)
        # FR-RQ-02 fixes the key as (source, chunk_id); mutable excerpts do not
        # replace the first locally-grounded observation.
        first = ledger.register("markdown", _markdown_hit())
        duplicate = ledger.register("markdown", {**_markdown_hit(), "snippet": "new"})
        second = ledger.register("code", _code_hit())

        assert first == duplicate == "E1"
        assert second == "E2"
        assert [item["ref_id"] for item in ledger.evidence()] == ["E1", "E2"]
        assert ledger.get("E1")["snippet"] == "# Spec\ncontract"

    def test_source_is_part_of_the_deduplication_key(self, repo_root: Path) -> None:
        ledger = EvidenceLedger(repo_root)
        hit = _markdown_hit()

        assert ledger.register("markdown", hit) == "E1"
        assert ledger.register("code", hit) == "E2"

    def test_rejects_sources_outside_the_two_local_indexes(self, repo_root: Path) -> None:
        ledger = EvidenceLedger(repo_root)

        with pytest.raises(RepositoryQueryInputError):
            ledger.register("web", _markdown_hit())

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "../secret.py",
            "pkg/../secret.py",
            "C:/secret.py",
            "C:\\secret.py",
            "bad\x00.py",
        ],
    )
    def test_rejects_unsafe_evidence_paths(self, repo_root: Path, path: str) -> None:
        ledger = EvidenceLedger(repo_root)

        with pytest.raises(RepositoryQueryInputError):
            ledger.register("code", {**_code_hit(), "path": path})

    def test_rejects_a_symlink_that_resolves_outside_the_repository(
        self, repo_root: Path
    ) -> None:
        outside = repo_root.parent / f"{repo_root.name}-outside.py"
        outside.write_text("outside = True\n", encoding="utf-8")
        link = repo_root / "outside-link.py"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

        with pytest.raises(RepositoryQueryInputError):
            EvidenceLedger(repo_root).register(
                "code", {**_code_hit(), "path": "outside-link.py"}
            )


class TestSearchTools:
    def test_markdown_search_forwards_fixed_caps_and_registers_refs(
        self, repo_root: Path
    ) -> None:
        calls: list[tuple[str, tuple[str, ...], int, int]] = []

        def searcher(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            calls.append((query, paths, top_k, max_tokens))
            return [_markdown_hit()]

        tools = _tools(repo_root, markdown_search=searcher)

        hits = tools.search_markdown(["first", "second"], paths=["docs/**"])

        assert calls == [
            ("first", ("docs/**",), 3, 800),
            ("second", ("docs/**",), 3, 800),
        ]
        assert [hit["ref_id"] for hit in hits] == ["E1", "E1"]
        assert all(hit["source"] == "markdown" for hit in hits)
        # One outer custom-tool invocation can contain multiple local searches.
        assert tools.activity() == {"tool_calls": 1, "internal_searches": 2}

    def test_code_search_uses_the_same_limits(self, repo_root: Path) -> None:
        calls: list[tuple[str, tuple[str, ...], int, int]] = []

        def searcher(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            calls.append((query, paths, top_k, max_tokens))
            return [_code_hit()]

        tools = _tools(repo_root, code_search=searcher)

        hits = tools.search_code(["run"], paths=["pkg/**"])

        assert calls == [("run", ("pkg/**",), 3, 800)]
        assert hits[0]["ref_id"] == "E1"
        assert hits[0]["source"] == "code"

    @pytest.mark.parametrize("queries", [[], [""], [" "]])
    def test_rejects_invalid_query_batches_before_backend_call(
        self, repo_root: Path, queries: list[str]
    ) -> None:
        backend_calls: list[str] = []

        def searcher(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            backend_calls.append(query)
            return [_code_hit()]

        tools = _tools(repo_root, code_search=searcher)

        with pytest.raises(RepositoryQueryInputError):
            tools.search_code(queries)

        assert backend_calls == []

    def test_accepts_exactly_three_queries(self, repo_root: Path) -> None:
        tools = _tools(repo_root)

        hits = tools.search_code(["one", "two", "three"])

        assert len(hits) == 3
        assert tools.activity() == {"tool_calls": 1, "internal_searches": 3}

    def test_internal_searches_count_queries_even_when_there_are_no_hits(
        self, repo_root: Path
    ) -> None:
        tools = _tools(repo_root, code_search=lambda *args, **kwargs: [])

        assert tools.search_code(["one", "two", "three"]) == []
        assert tools.activity() == {"tool_calls": 1, "internal_searches": 3}

    @pytest.mark.parametrize(
        "path",
        [
            "/absolute/**",
            "../private/**",
            "pkg/../private/**",
            "C:/private/**",
            "C:\\private\\**",
            "bad\x00/**",
        ],
    )
    def test_rejects_unsafe_path_filters(self, repo_root: Path, path: str) -> None:
        backend_calls: list[str] = []

        def searcher(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            backend_calls.append(query)
            return [_markdown_hit()]

        tools = _tools(repo_root, markdown_search=searcher)

        with pytest.raises(RepositoryQueryInputError):
            tools.search_markdown(["query"], paths=[path])

        assert backend_calls == []

    def test_does_not_hide_backend_errors(self, repo_root: Path) -> None:
        def failing(*args: object, **kwargs: object) -> list[Hit]:
            raise RuntimeError("backend exploded")

        tools = _tools(repo_root, code_search=failing)

        with pytest.raises(RepositoryQuerySourceError, match="backend exploded"):
            tools.search_code(["query"])

    def test_rejects_a_backend_hit_outside_the_repository(self, repo_root: Path) -> None:
        outside = repo_root.parent / f"{repo_root.name}-outside.py"
        outside.write_text("outside = True\n", encoding="utf-8")
        tools = _tools(
            repo_root,
            code_search=lambda *args, **kwargs: [
                {**_code_hit(), "path": f"../{outside.name}"}
            ],
        )

        with pytest.raises(RepositoryQuerySourceError):
            tools.search_code(["query"])

    def test_caps_backend_results_even_if_a_backend_ignores_top_k(
        self, repo_root: Path
    ) -> None:
        def overflowing_search(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            return [
                {**_code_hit(), "chunk_id": f"{query}-{index}"}
                for index in range(4)
            ]

        tools = _tools(
            repo_root,
            code_search=overflowing_search,
        )

        hits = tools.search_code(["first", "second"])

        assert len(hits) == 6
        assert [hit["chunk_id"] for hit in hits] == [
            "first-0",
            "first-1",
            "first-2",
            "second-0",
            "second-1",
            "second-2",
        ]
        assert [item["chunk_id"] for item in tools.ledger.evidence()] == [
            "first-0",
            "first-1",
            "first-2",
            "second-0",
            "second-1",
            "second-2",
        ]

    def test_rejects_a_backend_response_over_the_token_budget(
        self, repo_root: Path
    ) -> None:
        oversized = "oversized " * 2_000
        assert mdq_tokens.count_tokens(oversized) > 800
        tools = _tools(
            repo_root,
            code_search=lambda *args, **kwargs: [
                {**_code_hit(), "snippet": oversized}
            ],
        )

        with pytest.raises(RepositoryQueryLimitError):
            tools.search_code(["query"])

        assert tools.ledger.evidence() == []

    def test_token_budget_is_the_sum_of_all_hits_for_one_query(
        self, repo_root: Path
    ) -> None:
        snippets = ["alpha " * 350, "beta " * 350, "gamma " * 350]
        counts = [mdq_tokens.count_tokens(snippet) for snippet in snippets]
        assert all(count < 800 for count in counts)
        assert sum(counts) > 800
        tools = _tools(
            repo_root,
            code_search=lambda *args, **kwargs: [
                {**_code_hit(), "chunk_id": f"cq-{index}", "snippet": snippet}
                for index, snippet in enumerate(snippets)
            ],
        )

        with pytest.raises(RepositoryQueryLimitError):
            tools.search_code(["query"])

        assert tools.ledger.evidence() == []

    def test_invalid_query_batch_is_rejected_before_backend_call(
        self, repo_root: Path
    ) -> None:
        backend_calls: list[str] = []

        def searcher(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            backend_calls.append(query)
            return [_code_hit()]

        tools = _tools(repo_root, code_search=searcher)

        with pytest.raises(RepositoryQueryInputError):
            tools.search_code(["one", "two", "three", "four"])

        assert backend_calls == []
        assert tools.ledger.evidence() == []


class TestOpenEvidence:
    def test_opens_only_registered_refs_with_the_correct_backend(
        self, repo_root: Path
    ) -> None:
        opened: list[tuple[str, str]] = []

        def markdown_get(chunk_id: str) -> Hit:
            opened.append(("markdown", chunk_id))
            return {**_markdown_hit(), "text": "full markdown"}

        def code_get(chunk_id: str) -> Hit:
            opened.append(("code", chunk_id))
            return {**_code_hit(), "text": "full code"}

        tools = _tools(repo_root, markdown_get=markdown_get, code_get=code_get)
        md_ref = tools.search_markdown(["spec"])[0]["ref_id"]
        code_ref = tools.search_code(["run"])[0]["ref_id"]

        evidence = tools.open_evidence([md_ref, code_ref])

        assert opened == [("markdown", "md-1"), ("code", "cq-1")]
        assert [item["ref_id"] for item in evidence] == ["E1", "E2"]
        assert [item["text"] for item in evidence] == ["full markdown", "full code"]
        assert tools.activity() == {"tool_calls": 3, "internal_searches": 2}

    def test_unknown_ref_is_rejected_before_any_backend_call(
        self, repo_root: Path
    ) -> None:
        calls: list[tuple[str, str]] = []
        tools = _tools(
            repo_root,
            markdown_get=lambda chunk_id: calls.append(  # type: ignore[arg-type]
                ("markdown", chunk_id)
            ),
            code_get=lambda chunk_id: calls.append(  # type: ignore[arg-type]
                ("code", chunk_id)
            ),
        )

        with pytest.raises(RepositoryQueryInputError, match="E99"):
            tools.open_evidence(["E99"])

        assert calls == []

    def test_rejects_more_than_three_refs(self, repo_root: Path) -> None:
        opened: list[str] = []
        tools = _tools(
            repo_root,
            code_search=lambda query, **kwargs: [
                {**_code_hit(), "chunk_id": f"{query}-{index}"}
                for index in range(4)
            ],
            code_get=lambda chunk_id: opened.append(chunk_id),  # type: ignore[arg-type]
        )
        refs = [
            str(hit["ref_id"])
            for hit in tools.search_code(["one", "two"])
        ][:4]
        assert len(refs) == 4
        assert len(set(refs)) == 4

        with pytest.raises(RepositoryQueryInputError):
            tools.open_evidence(refs)

        assert opened == []

    def test_rejects_mismatched_content_from_the_backend(self, repo_root: Path) -> None:
        tools = _tools(
            repo_root,
            code_get=lambda chunk_id: {
                **_code_hit(),
                "chunk_id": "different",
                "text": "wrong",
            },
        )
        ref = tools.search_code(["run"])[0]["ref_id"]

        with pytest.raises(RepositoryQuerySourceError):
            tools.open_evidence([ref])

    def test_rejects_content_for_a_different_path(self, repo_root: Path) -> None:
        tools = _tools(
            repo_root,
            code_get=lambda chunk_id: {
                **_code_hit(),
                "path": "pkg/other.py",
                "text": "wrong path",
            },
        )
        ref = tools.search_code(["run"])[0]["ref_id"]

        with pytest.raises(RepositoryQuerySourceError):
            tools.open_evidence([ref])

    def test_missing_registered_content_is_a_source_error(self, repo_root: Path) -> None:
        tools = _tools(repo_root, code_get=lambda chunk_id: None)
        ref = tools.search_code(["run"])[0]["ref_id"]

        with pytest.raises(RepositoryQuerySourceError):
            tools.open_evidence([ref])


class TestReferencesAndLimits:
    def test_reference_lookup_forwards_the_fixed_limit(self, repo_root: Path) -> None:
        calls: list[tuple[str, int]] = []

        def references(symbol: str, *, top_k: int) -> list[Hit]:
            calls.append((symbol, top_k))
            return [{"path": "pkg/service.py", "line": 1, "name": symbol}]

        tools = _tools(repo_root, code_references=references)

        rows = tools.find_code_references("run")

        assert calls == [("run", 3)]
        # Reference rows intentionally remain locations; only search hits enter
        # the Evidence Ledger and can be passed to open_evidence.
        assert rows == [{"path": "pkg/service.py", "line": 1, "name": "run"}]

    def test_reference_rows_are_capped_and_do_not_enter_the_ledger(
        self, repo_root: Path
    ) -> None:
        tools = _tools(
            repo_root,
            code_references=lambda symbol, *, top_k: [
                {"path": "pkg/service.py", "line": index, "name": symbol}
                for index in range(1, 5)
            ],
        )

        rows = tools.find_code_references("run")

        assert len(rows) == 3
        assert tools.ledger.evidence() == []
        assert tools.search_code(["run"])[0]["ref_id"] == "E1"

    def test_reference_line_must_exist_in_the_source_file(
        self, repo_root: Path
    ) -> None:
        tools = _tools(
            repo_root,
            code_references=lambda symbol, *, top_k: [
                {"path": "pkg/service.py", "line": 999, "name": symbol}
            ],
        )

        with pytest.raises(RepositoryQuerySourceError):
            tools.find_code_references("run")

    @pytest.mark.parametrize("symbol", ["", " ", "bad\x00symbol"])
    def test_rejects_invalid_symbols(self, repo_root: Path, symbol: str) -> None:
        tools = _tools(repo_root)

        with pytest.raises(RepositoryQueryInputError):
            tools.find_code_references(symbol)

    def test_seventh_tool_call_is_rejected_without_calling_a_backend(
        self, repo_root: Path
    ) -> None:
        calls: list[str] = []

        def references(symbol: str, *, top_k: int) -> list[Hit]:
            calls.append(symbol)
            return []

        tools = _tools(repo_root, code_references=references)
        for _ in range(6):
            assert tools.find_code_references("run") == []

        with pytest.raises(RepositoryQueryLimitError):
            tools.find_code_references("run")

        assert calls == ["run"] * 6
        assert tools.activity() == {"tool_calls": 6, "internal_searches": 0}
        assert tools.ledger.evidence() == []

    def test_tool_call_limit_is_global_across_all_four_methods(
        self, repo_root: Path
    ) -> None:
        reference_calls: list[str] = []
        search_calls: list[str] = []

        def references(symbol: str, *, top_k: int) -> list[Hit]:
            reference_calls.append(symbol)
            return []

        def code_search(
            query: str, *, paths: tuple[str, ...], top_k: int, max_tokens: int
        ) -> list[Hit]:
            search_calls.append(query)
            return [_code_hit()]

        tools = _tools(
            repo_root, code_references=references, code_search=code_search
        )
        ref = tools.search_code(["run"])[0]["ref_id"]  # call 1
        assert tools.search_markdown(["spec"])  # call 2
        assert tools.open_evidence([ref])  # call 3
        assert tools.find_code_references("run") == []  # call 4
        assert tools.find_code_references("run") == []  # call 5
        assert tools.find_code_references("run") == []  # call 6

        with pytest.raises(RepositoryQueryLimitError):
            tools.search_code(["must-not-run"])

        assert reference_calls == ["run"] * 3
        assert search_calls == ["run"]
        assert tools.activity() == {"tool_calls": 6, "internal_searches": 2}
