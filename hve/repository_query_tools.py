"""Read-only local tools for the Repository Query measurement PoC.

The module is deliberately a thin host-side boundary over the existing mdq/cq
APIs. It owns validation, evidence IDs, and safety caps; it does not implement a
new search engine, provider abstraction, plugin system, or network fallback.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from mdq import tokens as mdq_tokens
from pydantic import BaseModel, Field

MAX_TOOL_CALLS = 6
MAX_QUERIES_PER_SEARCH = 3
MAX_HITS_PER_QUERY = 3
MAX_TOKENS_PER_QUERY = 800
MAX_REFS_PER_OPEN = 3
MAX_REFERENCES = 3
_SOURCES = frozenset({"markdown", "code"})

Hit = dict[str, Any]


class RepositoryQueryError(RuntimeError):
    """Base error for the local Repository Query boundary."""


class RepositoryQueryInputError(RepositoryQueryError, ValueError):
    """Raised before a backend call when tool input is unsafe or malformed."""


class RepositoryQuerySourceError(RepositoryQueryError):
    """Raised when a local backend fails or returns untrusted data."""


class RepositoryQueryLimitError(RepositoryQueryError):
    """Raised before work that would exceed a fixed safety cap."""

    def __init__(self, cap_name: str, limit: int, actual: int) -> None:
        super().__init__(f"{cap_name} limit exceeded: {actual} > {limit}")
        self.cap_name = cap_name
        self.limit = limit
        self.actual = actual
        self.usage: dict[str, int] | None = None


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


class SearchToolParams(BaseModel):
    queries: list[str]
    paths: list[str] = Field(default_factory=list)


class OpenEvidenceToolParams(BaseModel):
    ref_ids: list[str]


class CodeReferencesToolParams(BaseModel):
    symbol: str


def _safe_relative_path(repo_root: Path, raw: object) -> str:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise RepositoryQueryInputError("path must be a non-empty POSIX relative path")
    path = PurePosixPath(raw)
    first = path.parts[0] if path.parts else ""
    if (
        path.is_absolute()
        or ".." in path.parts
        or ":" in first
        or raw != path.as_posix()
    ):
        raise RepositoryQueryInputError(f"unsafe repository path: {raw!r}")
    target = (repo_root / path).resolve()
    if not target.is_relative_to(repo_root):
        raise RepositoryQueryInputError(f"path escapes repository: {raw!r}")
    return raw


def _safe_existing_file(repo_root: Path, raw: object) -> str:
    relative = _safe_relative_path(repo_root, raw)
    if not (repo_root / relative).is_file():
        raise RepositoryQueryInputError(f"repository file does not exist: {relative}")
    return relative


def _safe_filters(repo_root: Path, paths: object) -> tuple[str, ...]:
    if paths is None:
        return ()
    if not isinstance(paths, (list, tuple)):
        raise RepositoryQueryInputError("paths must be a list of repository-relative globs")
    checked: list[str] = []
    for raw in paths:
        checked.append(_safe_relative_path(repo_root, raw))
    return tuple(checked)


def _valid_lines(raw: object) -> list[int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise RepositoryQueryInputError("evidence lines must contain start and end")
    start, end = raw
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or end < start
    ):
        raise RepositoryQueryInputError("evidence line range is invalid")
    return [start, end]


class EvidenceLedger:
    """Query-scoped stable evidence IDs backed only by repository files."""

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._by_key: dict[tuple[str, str], str] = {}
        self._by_ref: dict[str, Hit] = {}
        self._ordered: list[str] = []

    def register(self, source: str, hit: Hit) -> str:
        if source not in _SOURCES:
            raise RepositoryQueryInputError(f"unsupported evidence source: {source!r}")
        if not isinstance(hit, dict):
            raise RepositoryQueryInputError("evidence hit must be an object")
        chunk_id = hit.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or "\x00" in chunk_id:
            raise RepositoryQueryInputError("evidence chunk_id must be non-empty")
        path = _safe_existing_file(self.repo_root, hit.get("path"))
        lines = _valid_lines(hit.get("lines"))
        snippet = hit.get("snippet")
        if not isinstance(snippet, str):
            raise RepositoryQueryInputError("evidence snippet must be a string")

        key = (source, chunk_id)
        existing = self._by_key.get(key)
        if existing is not None:
            return existing

        ref_id = f"E{len(self._ordered) + 1}"
        row = dict(hit)
        row.update(
            ref_id=ref_id,
            source=source,
            chunk_id=chunk_id,
            path=path,
            lines=lines,
            snippet=snippet,
        )
        self._by_key[key] = ref_id
        self._by_ref[ref_id] = row
        self._ordered.append(ref_id)
        return ref_id

    def get(self, ref_id: object) -> Hit:
        if not isinstance(ref_id, str) or ref_id not in self._by_ref:
            raise RepositoryQueryInputError(f"unknown evidence ref: {ref_id}")
        return dict(self._by_ref[ref_id])

    def evidence(self) -> list[Hit]:
        return [dict(self._by_ref[ref_id]) for ref_id in self._ordered]


class RepositoryQueryTools:
    """Four bounded, read-only tools sharing one query-scoped ledger."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        markdown_search: Search,
        markdown_get: Getter,
        code_search: Search,
        code_get: Getter,
        code_references: References,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ledger = EvidenceLedger(self.repo_root)
        self._markdown_search = markdown_search
        self._markdown_get = markdown_get
        self._code_search = code_search
        self._code_get = code_get
        self._code_references = code_references
        self._tool_calls = 0
        self._internal_searches = 0
        self._sdk_tools: list[object] | None = None

    def activity(self) -> dict[str, int]:
        return {
            "tool_calls": self._tool_calls,
            "internal_searches": self._internal_searches,
        }

    def _start_tool_call(self) -> None:
        actual = self._tool_calls + 1
        if actual > MAX_TOOL_CALLS:
            raise RepositoryQueryLimitError("tool_calls", MAX_TOOL_CALLS, actual)
        self._tool_calls = actual

    @staticmethod
    def _queries(raw: object) -> tuple[str, ...]:
        if not isinstance(raw, (list, tuple)):
            raise RepositoryQueryInputError("queries must be a list")
        if not 1 <= len(raw) <= MAX_QUERIES_PER_SEARCH:
            raise RepositoryQueryInputError(
                f"queries must contain 1..{MAX_QUERIES_PER_SEARCH} items"
            )
        values: list[str] = []
        for query in raw:
            if not isinstance(query, str) or not query.strip() or "\x00" in query:
                raise RepositoryQueryInputError("queries must be non-empty strings")
            values.append(query.strip())
        return tuple(values)

    def search_markdown(
        self, queries: list[str], *, paths: list[str] | None = None
    ) -> list[Hit]:
        return self._search("markdown", queries, paths)

    def search_code(
        self, queries: list[str], *, paths: list[str] | None = None
    ) -> list[Hit]:
        return self._search("code", queries, paths)

    def _search(
        self, source: str, queries: object, paths: object
    ) -> list[Hit]:
        checked_queries = self._queries(queries)
        checked_paths = _safe_filters(self.repo_root, paths)
        self._start_tool_call()
        backend = self._markdown_search if source == "markdown" else self._code_search
        output: list[Hit] = []
        for query in checked_queries:
            self._internal_searches += 1
            try:
                raw_hits = backend(
                    query,
                    paths=checked_paths,
                    top_k=MAX_HITS_PER_QUERY,
                    max_tokens=MAX_TOKENS_PER_QUERY,
                )
            except RepositoryQueryError:
                raise
            except Exception as exc:
                raise RepositoryQuerySourceError(
                    f"{source} backend failed: {exc}"
                ) from exc
            if not isinstance(raw_hits, list):
                raise RepositoryQuerySourceError(f"{source} backend returned non-list hits")
            bounded_hits = raw_hits[:MAX_HITS_PER_QUERY]
            token_counts: list[int] = []
            for raw_hit in bounded_hits:
                if not isinstance(raw_hit, dict):
                    raise RepositoryQuerySourceError(f"{source} backend returned invalid hit")
                encoded = json.dumps(raw_hit, ensure_ascii=False, sort_keys=True)
                token_counts.append(mdq_tokens.count_tokens(encoded))
            query_tokens = sum(token_counts)
            if query_tokens > MAX_TOKENS_PER_QUERY:
                raise RepositoryQueryLimitError(
                    "tokens_per_subquery", MAX_TOKENS_PER_QUERY, query_tokens
                )
            for raw_hit in bounded_hits:
                try:
                    ref_id = self.ledger.register(source, raw_hit)
                except RepositoryQueryInputError as exc:
                    raise RepositoryQuerySourceError(
                        f"{source} backend returned unsafe evidence: {exc}"
                    ) from exc
                payload = dict(raw_hit)
                payload.update(source=source, ref_id=ref_id)
                output.append(payload)
        return output

    def open_evidence(self, ref_ids: list[str]) -> list[Hit]:
        if not isinstance(ref_ids, (list, tuple)) or not 1 <= len(ref_ids) <= MAX_REFS_PER_OPEN:
            raise RepositoryQueryInputError(
                f"ref_ids must contain 1..{MAX_REFS_PER_OPEN} items"
            )
        if len(set(ref_ids)) != len(ref_ids):
            raise RepositoryQueryInputError("ref_ids must not contain duplicates")
        rows = [self.ledger.get(ref_id) for ref_id in ref_ids]
        self._start_tool_call()
        opened: list[Hit] = []
        for row in rows:
            getter = self._markdown_get if row["source"] == "markdown" else self._code_get
            try:
                content = getter(str(row["chunk_id"]))
            except RepositoryQueryError:
                raise
            except Exception as exc:
                raise RepositoryQuerySourceError(f"evidence backend failed: {exc}") from exc
            if not isinstance(content, dict):
                raise RepositoryQuerySourceError("registered evidence content is unavailable")
            try:
                content_path = _safe_existing_file(self.repo_root, content.get("path"))
                content_lines = _valid_lines(content.get("lines"))
            except RepositoryQueryInputError as exc:
                raise RepositoryQuerySourceError(
                    f"evidence backend returned unsafe content: {exc}"
                ) from exc
            if (
                content.get("chunk_id") != row["chunk_id"]
                or content_path != row["path"]
                or content_lines != row["lines"]
            ):
                raise RepositoryQuerySourceError("evidence backend content mismatches ledger")
            text = content.get("text")
            if not isinstance(text, str):
                raise RepositoryQuerySourceError("evidence backend omitted text")
            payload = dict(content)
            payload.update(ref_id=row["ref_id"], source=row["source"])
            opened.append(payload)
        return opened

    def find_code_references(self, symbol: str) -> list[Hit]:
        if not isinstance(symbol, str) or not symbol.strip() or "\x00" in symbol:
            raise RepositoryQueryInputError("symbol must be a non-empty string")
        self._start_tool_call()
        try:
            rows = self._code_references(symbol.strip(), top_k=MAX_REFERENCES)
        except RepositoryQueryError:
            raise
        except Exception as exc:
            raise RepositoryQuerySourceError(f"reference backend failed: {exc}") from exc
        if not isinstance(rows, list):
            raise RepositoryQuerySourceError("reference backend returned non-list rows")
        output: list[Hit] = []
        for raw in rows[:MAX_REFERENCES]:
            if not isinstance(raw, dict):
                raise RepositoryQuerySourceError("reference backend returned invalid row")
            try:
                path = _safe_existing_file(self.repo_root, raw.get("path"))
            except RepositoryQueryInputError as exc:
                raise RepositoryQuerySourceError(
                    f"reference backend returned unsafe path: {exc}"
                ) from exc
            line = raw.get("line")
            if isinstance(line, bool) or not isinstance(line, int) or line < 1:
                raise RepositoryQuerySourceError("reference backend returned invalid line")
            line_count = len(
                (self.repo_root / path).read_text(
                    encoding="utf-8-sig", errors="replace"
                ).splitlines()
            )
            if line > line_count:
                raise RepositoryQuerySourceError(
                    "reference backend returned a line outside the source file"
                )
            payload = dict(raw)
            payload["path"] = path
            output.append(payload)
        return output

    def sdk_tools(self) -> list[object]:
        """Build the exact four read-only SDK tools lazily."""
        if self._sdk_tools is not None:
            return list(self._sdk_tools)

        from copilot import define_tool

        async def search_markdown_handler(
            params: SearchToolParams, _invocation: object
        ) -> list[Hit]:
            return self.search_markdown(params.queries, paths=params.paths)

        async def search_code_handler(
            params: SearchToolParams, _invocation: object
        ) -> list[Hit]:
            return self.search_code(params.queries, paths=params.paths)

        async def open_evidence_handler(
            params: OpenEvidenceToolParams, _invocation: object
        ) -> list[Hit]:
            return self.open_evidence(params.ref_ids)

        async def references_handler(
            params: CodeReferencesToolParams, _invocation: object
        ) -> list[Hit]:
            return self.find_code_references(params.symbol)

        self._sdk_tools = [
            define_tool(
                name="search_markdown",
                description="Search local repository Markdown with fixed caps.",
                handler=search_markdown_handler,
                params_type=SearchToolParams,
                skip_permission=True,
            ),
            define_tool(
                name="search_code",
                description="Search local repository source code with fixed caps.",
                handler=search_code_handler,
                params_type=SearchToolParams,
                skip_permission=True,
            ),
            define_tool(
                name="open_evidence",
                description="Open only evidence refs registered by this query.",
                handler=open_evidence_handler,
                params_type=OpenEvidenceToolParams,
                skip_permission=True,
            ),
            define_tool(
                name="find_code_references",
                description="Find local code references for one symbol.",
                handler=references_handler,
                params_type=CodeReferencesToolParams,
                skip_permission=True,
            ),
        ]
        return list(self._sdk_tools)


def build_repository_query_tools(
    *,
    repo_root: Path | str,
    mdq_db_path: Path | str,
    cq_db_path: Path | str,
    cq_profile: str = "hve",
    mdq_lang: str = "ja-jp",
) -> RepositoryQueryTools:
    """Bind the safe tool boundary to the existing mdq/cq implementations."""
    root = Path(repo_root).resolve()
    mdq_db = Path(mdq_db_path)
    cq_db = Path(cq_db_path)
    if not mdq_db.is_file():
        raise RepositoryQuerySourceError(f"mdq index not found: {mdq_db}")
    if not cq_db.is_file():
        raise RepositoryQuerySourceError(f"cq index not found: {cq_db}")

    from cq import search as cq_search
    from cq import traces as cq_traces
    from mdq import search as mdq_search
    from mdq import store as mdq_store

    def markdown_search(
        query: str,
        *,
        paths: tuple[str, ...],
        top_k: int,
        max_tokens: int,
    ) -> list[Hit]:
        with closing(mdq_store.open_store(mdq_db, lang=mdq_lang)) as conn:
            return [
                hit.to_dict()
                for hit in mdq_search.search(
                    conn,
                    query,
                    top_k=top_k,
                    max_tokens=max_tokens,
                    path_globs=list(paths),
                )
            ]

    def markdown_get(chunk_id: str) -> Hit | None:
        with closing(mdq_store.open_store(mdq_db, lang=mdq_lang)) as conn:
            return mdq_search.get_chunk(conn, chunk_id)

    def code_search(
        query: str,
        *,
        paths: tuple[str, ...],
        top_k: int,
        max_tokens: int,
    ) -> list[Hit]:
        scopes = paths or (None,)
        merged: list[Hit] = []
        seen: set[str] = set()
        for scope in scopes:
            for hit in cq_search.search(
                root,
                cq_profile,
                query=query,
                top_k=top_k,
                max_tokens=max_tokens,
                paths=scope,
                db_path=cq_db,
            ):
                payload = hit.to_dict()
                key = payload.get("chunk_id")
                if not isinstance(key, str) or not key:
                    raise RepositoryQuerySourceError(
                        "cq backend returned a hit without chunk_id"
                    )
                if key not in seen:
                    seen.add(key)
                    merged.append(payload)
        merged.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("path") or "")))
        return merged[:top_k]

    def code_get(chunk_id: str) -> Hit | None:
        payload = cq_search.get_chunk(cq_db, chunk_id)
        return dict(payload) if payload is not None else None

    def code_references(symbol: str, *, top_k: int) -> list[Hit]:
        return cq_traces.references(cq_db, symbol, top_k=top_k)

    return RepositoryQueryTools(
        repo_root=root,
        markdown_search=markdown_search,
        markdown_get=markdown_get,
        code_search=code_search,
        code_get=code_get,
        code_references=code_references,
    )
