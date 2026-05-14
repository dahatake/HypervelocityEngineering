"""BM25 + grep search over the indexed chunks.

Uses rank_bm25 when available; otherwise falls back to a tiny stdlib BM25.
Returns hits with minimal snippets (default ±2 body lines around the
strongest match) to keep context windows small.
"""
from __future__ import annotations

import fnmatch
import json
import math
import re
from dataclasses import dataclass
from typing import Iterable

try:
    from rank_bm25 import BM25Okapi  # type: ignore
    HAS_RANK_BM25 = True
except Exception:
    HAS_RANK_BM25 = False

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3040-\u30ff\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class Hit:
    chunk_id: str
    path: str
    heading_path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    expansion: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "heading_path": self.heading_path,
            "lines": [self.start_line, self.end_line],
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }
        if self.expansion is not None:
            d["expansion"] = self.expansion
        return d


class _MiniBM25:
    """Tiny BM25-Okapi fallback (no external deps)."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / self.N if self.N else 0
        self.doc_len = [len(d) for d in corpus]
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for doc in corpus:
            counts: dict[str, int] = {}
            for tok in doc:
                counts[tok] = counts.get(tok, 0) + 1
            self.tf.append(counts)
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            tok: math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            for tok, n in df.items()
        }

    def get_scores(self, query: list[str]) -> list[float]:
        scores = [0.0] * self.N
        for i in range(self.N):
            dl = self.doc_len[i]
            denom_norm = 1 - self.b + self.b * (dl / self.avgdl if self.avgdl else 1)
            for tok in query:
                if tok not in self.idf:
                    continue
                f = self.tf[i].get(tok, 0)
                if f == 0:
                    continue
                scores[i] += self.idf[tok] * (f * (self.k1 + 1)) / (
                    f + self.k1 * denom_norm
                )
        return scores


def _make_snippet(text: str, query_tokens: list[str], radius: int = 2,
                  max_chars: int = 400) -> str:
    """Return a compact snippet centered on the strongest matching line."""
    lines = text.splitlines()
    if not lines:
        return ""
    qset = set(query_tokens)
    best_idx = 0
    best_score = -1
    for i, line in enumerate(lines):
        toks = set(tokenize(line))
        score = len(toks & qset)
        if score > best_score:
            best_score = score
            best_idx = i
    lo = max(0, best_idx - radius)
    hi = min(len(lines), best_idx + radius + 1)
    snippet = "\n".join(lines[lo:hi])
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1] + "…"
    return snippet


def _path_matches(path: str, globs: list[str]) -> bool:
    if not globs:
        return True
    return any(fnmatch.fnmatch(path, g) for g in globs)


def _tag_matches(tags_json: str | None, wanted: list[str]) -> bool:
    if not wanted:
        return True
    if not tags_json:
        return False
    try:
        tags = json.loads(tags_json)
    except Exception:
        return False
    if not isinstance(tags, list):
        return False
    tagset = {str(t).lower() for t in tags}
    return all(w.lower() in tagset for w in wanted)


def search(conn, query: str, *, mode: str = "bm25",
           top_k: int = 5, max_tokens: int = 800,
           path_globs: list[str] | None = None,
           tags: list[str] | None = None,
           snippet_radius: int = 2,
           include_parent: bool = False,
           expand_neighbors: int = 0,
           merge_parts: bool = False,
           engine: str = "auto") -> list[Hit]:
    """Run a search against the indexed chunks.

    mode: 'bm25' | 'grep'
    engine: 'auto' | 'bm25' | 'fts5'. 'auto' picks 'fts5' when the env var
        HVE_MDQ_FTS5 is set to a truthy value and FTS5 is available on this
        DB; otherwise it uses the in-memory BM25 path.
    """
    import os
    from . import store as _store

    # Resolve engine selection. fts5 only applies for bm25-mode queries.
    use_fts5 = False
    if mode == "bm25":
        if engine == "fts5":
            use_fts5 = True
        elif engine == "auto" and os.environ.get("HVE_MDQ_FTS5", "").lower() in (
            "1", "true", "yes", "on"
        ):
            use_fts5 = True
        if use_fts5 and not _store.has_fts5(conn):
            use_fts5 = False  # silent fallback

    if use_fts5:
        return _search_fts5(
            conn, query,
            top_k=top_k, max_tokens=max_tokens,
            path_globs=path_globs, tags=tags,
            snippet_radius=snippet_radius,
            include_parent=include_parent,
            expand_neighbors=expand_neighbors,
            merge_parts=merge_parts,
        )

    rows = _store.all_chunks(conn)
    if path_globs:
        rows = [r for r in rows if _path_matches(r["path"], path_globs)]
    if tags:
        rows = [r for r in rows if _tag_matches(r["tags"], tags)]

    if not rows:
        return []

    q_tokens = tokenize(query)

    if mode == "grep" or not q_tokens:
        pat = re.compile(re.escape(query), re.IGNORECASE)
        scored = []
        for r in rows:
            n = len(pat.findall(r["text"]))
            if n > 0:
                scored.append((float(n), r))
        scored.sort(key=lambda x: -x[0])
    else:
        corpus = [tokenize(r["text"]) for r in rows]
        if HAS_RANK_BM25:
            bm25 = BM25Okapi(corpus)
            scores = bm25.get_scores(q_tokens)
        else:
            bm25 = _MiniBM25(corpus)
            scores = bm25.get_scores(q_tokens)
        scored = [(float(s), r) for s, r in zip(scores, rows) if s > 0]
        scored.sort(key=lambda x: -x[0])

    hits: list[Hit] = []
    spent = 0
    for score, r in scored[: max(top_k * 3, top_k)]:
        snippet = _make_snippet(r["text"], q_tokens, radius=snippet_radius)
        est = max(1, len(snippet) // 4)
        if spent + est > max_tokens and hits:
            break
        spent += est
        hits.append(Hit(
            chunk_id=r["chunk_id"],
            path=r["path"],
            heading_path=r["heading_path"],
            start_line=r["start_line"],
            end_line=r["end_line"],
            score=score,
            snippet=snippet,
        ))
        if len(hits) >= top_k:
            break

    # T04: expansion (parent / neighbors / parts)
    _apply_expansion(conn, hits, include_parent, expand_neighbors, merge_parts)
    return hits


def _apply_expansion(conn, hits: list[Hit], include_parent: bool,
                     expand_neighbors: int, merge_parts: bool) -> None:
    if not (include_parent or expand_neighbors > 0 or merge_parts):
        return
    for h in hits:
        exp: dict = {}
        if include_parent:
            p = _resolve_parent(conn, h)
            if p is not None:
                exp["parent"] = p
        if expand_neighbors > 0:
            neigh = _resolve_neighbors(conn, h, expand_neighbors)
            if neigh:
                exp["neighbors"] = neigh
        if merge_parts:
            parts = _resolve_parts(conn, h)
            if parts:
                exp["parts"] = parts
        if exp:
            h.expansion = exp


def _build_fts5_query(q_tokens: list[str]) -> str:
    """Quote each token and OR-join for FTS5 MATCH."""
    safe = []
    for t in q_tokens:
        # double-quote and escape internal double-quotes per FTS5 syntax.
        safe.append('"' + t.replace('"', '""') + '"')
    return " OR ".join(safe)


def _search_fts5(conn, query: str, *, top_k: int, max_tokens: int,
                 path_globs: list[str] | None,
                 tags: list[str] | None,
                 snippet_radius: int,
                 include_parent: bool,
                 expand_neighbors: int,
                 merge_parts: bool) -> list[Hit]:
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    fts_q = _build_fts5_query(q_tokens)
    try:
        rows = list(conn.execute(
            "SELECT c.chunk_id, c.path, c.heading_path, c.level, "
            "c.start_line, c.end_line, c.token_est, c.text, c.tags, "
            "c.part_index, c.part_total, bm25(chunks_fts) AS bm "
            "FROM chunks c JOIN chunks_fts f ON f.rowid = c.rowid "
            "WHERE chunks_fts MATCH ? "
            "ORDER BY bm ASC",
            (fts_q,),
        ))
    except _sql.OperationalError:
        return []

    if path_globs:
        rows = [r for r in rows if _path_matches(r["path"], path_globs)]
    if tags:
        rows = [r for r in rows if _tag_matches(r["tags"], tags)]

    hits: list[Hit] = []
    spent = 0
    for r in rows[: max(top_k * 3, top_k)]:
        snippet = _make_snippet(r["text"], q_tokens, radius=snippet_radius)
        est = max(1, len(snippet) // 4)
        if spent + est > max_tokens and hits:
            break
        spent += est
        # FTS5 bm25() returns negative values; smaller = better. Surface a
        # positive monotonic score for consumers (negate).
        hits.append(Hit(
            chunk_id=r["chunk_id"],
            path=r["path"],
            heading_path=r["heading_path"],
            start_line=r["start_line"],
            end_line=r["end_line"],
            score=-float(r["bm"]),
            snippet=snippet,
        ))
        if len(hits) >= top_k:
            break
    _apply_expansion(conn, hits, include_parent, expand_neighbors, merge_parts)
    return hits


def _row_to_brief(row) -> dict:
    return {
        "chunk_id": row["chunk_id"],
        "path": row["path"],
        "heading_path": row["heading_path"],
        "lines": [row["start_line"], row["end_line"]],
        "text": row["text"],
    }


def _resolve_parent(conn, hit: Hit) -> dict | None:
    hp = hit.heading_path or ""
    if " > " not in hp:
        return None
    parent_hp = hp.rsplit(" > ", 1)[0]
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    row = conn.execute(
        "SELECT chunk_id, path, heading_path, start_line, end_line, text "
        "FROM chunks WHERE path = ? AND heading_path = ? "
        "ORDER BY start_line LIMIT 1",
        (hit.path, parent_hp),
    ).fetchone()
    return _row_to_brief(row) if row else None


def _resolve_neighbors(conn, hit: Hit, n: int) -> list[dict]:
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    before = list(conn.execute(
        "SELECT chunk_id, path, heading_path, start_line, end_line, text "
        "FROM chunks WHERE path = ? AND start_line < ? "
        "ORDER BY start_line DESC LIMIT ?",
        (hit.path, hit.start_line, n),
    ))
    after = list(conn.execute(
        "SELECT chunk_id, path, heading_path, start_line, end_line, text "
        "FROM chunks WHERE path = ? AND start_line > ? "
        "ORDER BY start_line ASC LIMIT ?",
        (hit.path, hit.start_line, n),
    ))
    out = [_row_to_brief(r) for r in reversed(before)]
    out.extend(_row_to_brief(r) for r in after)
    return out


def _resolve_parts(conn, hit: Hit) -> list[dict]:
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    rows = list(conn.execute(
        "SELECT chunk_id, path, heading_path, start_line, end_line, text, "
        "part_index, part_total FROM chunks "
        "WHERE path = ? AND heading_path = ? AND chunk_id != ? "
        "ORDER BY part_index",
        (hit.path, hit.heading_path, hit.chunk_id),
    ))
    # only include if siblings exist (part_total > 1)
    rows = [r for r in rows if (r["part_total"] or 1) > 1]
    return [_row_to_brief(r) for r in rows]


def get_chunk(conn, chunk_id: str) -> dict | None:
    from . import store as _store  # noqa: F401
    conn.row_factory = __import__("sqlite3").Row
    row = conn.execute(
        "SELECT chunk_id, path, heading_path, level, start_line, end_line, "
        "token_est, text, tags FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "chunk_id": row["chunk_id"],
        "path": row["path"],
        "heading_path": row["heading_path"],
        "level": row["level"],
        "lines": [row["start_line"], row["end_line"]],
        "token_est": row["token_est"],
        "text": row["text"],
    }


def list_chunks(conn, path_globs: list[str] | None = None,
                heading_level: int | None = None,
                limit: int = 200) -> list[dict]:
    from . import store as _store  # noqa: F401
    conn.row_factory = __import__("sqlite3").Row
    rows = list(conn.execute(
        "SELECT path, heading_path, level, start_line, end_line FROM chunks "
        "ORDER BY path, start_line"
    ))
    out = []
    for r in rows:
        if path_globs and not _path_matches(r["path"], path_globs):
            continue
        if heading_level is not None and r["level"] != heading_level:
            continue
        out.append({
            "path": r["path"],
            "heading_path": r["heading_path"],
            "level": r["level"],
            "lines": [r["start_line"], r["end_line"]],
        })
        if len(out) >= limit:
            break
    return out
