# vendor/ — Vendored `mdq` package

This directory contains a **vendored copy** of the `mdq` Python package
(the index/search/CLI engine for the `markdown-query` Skill). When this
`tools/skills/markdown_query/` directory is copied into another repository
that does not already have `mdq` installed, the launcher scripts
(`launch-gui.{cmd,ps1,sh}`) prepend `vendor/` to `sys.path` so that
`import mdq` resolves to this copy.

## Source of truth

- Upstream: `mdq/` at the root of the HVE source repository
  (https://github.com/dahatake/RoyalytyService2ndGen).

## Vendored modules (current snapshot)

| File | Purpose |
| --- | --- |
| `__init__.py` / `__main__.py` | Package entrypoints |
| `cli.py` | `python -m mdq` argparse entry. `--strategy auto` lives here. |
| `config.py` | Portable config loader (`mdq.toml` / `.mdq/config.toml` resolution, `GENERIC_DEFAULT_ROOTS`). |
| `contextualizer.py` | Contextualizer template used by `semantic_paragraph`. |
| `embeddings.py` | Embedding provider abstraction (fastembed / null). |
| `indexer.py` | File walker, chunk dataclass, `parent_chunk_id` assignment, `_subdivide` with `overlap_paragraphs`. |
| `sentence_splitter.py` | Sentence splitter (nltk / regex fallback) for `semantic_paragraph`. |
| `strategies.py` | Strategy registry + per-strategy scanners. |
| `strategies_semantic.py` | `semantic_paragraph` implementation (embedding-based subdivision). |
| `strategies_pageindex.py` | `pageindex` implementation (heading tree + per-node summary). |
| `search.py` | BM25 / grep / FTS5 search, parent chain (`with_parent_depth`), pageindex `tree_path`, dedup. |
| `store.py` | SQLite schema (v6) and migrations. |
| `query_router.py` | **Skill-side auto strategy router** invoked when `--strategy auto`. Pure rule-based, no LLM. |
| `tokenize.py` | FTS5 tokenizer resolver. |
| `usage_log.py` | JSONL append-only log. |
| `usage_stats.py` | 19-metric aggregation (H1/H2 cover routing). |
| `watcher.py` | watchdog-based realtime updater. |

> When adding a new module upstream, append it to this table during sync.

## Re-syncing (when upgrading from upstream)

Inside the HVE source repository:

```powershell
# Windows
Remove-Item -Recurse -Force tools/skills/markdown_query/vendor/mdq
Copy-Item   -Recurse -Force -Exclude __pycache__,tests mdq tools/skills/markdown_query/vendor/mdq
Remove-Item -Recurse -Force tools/skills/markdown_query/vendor/mdq/__pycache__ -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force tools/skills/markdown_query/vendor/mdq/tests       -ErrorAction SilentlyContinue
```

```bash
# Linux / macOS
rm -rf  tools/skills/markdown_query/vendor/mdq
cp -R   mdq tools/skills/markdown_query/vendor/mdq
rm -rf  tools/skills/markdown_query/vendor/mdq/__pycache__
rm -rf  tools/skills/markdown_query/vendor/mdq/tests
```

Then commit the changes with a message referencing the upstream commit SHA
that the vendored snapshot was taken from.

## Do **not** edit files under `vendor/mdq/` directly

Bug fixes and features must be made in the upstream `mdq/` source first,
then synced down via the procedure above. Direct edits will be lost.
