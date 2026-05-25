"""mdq CLI - minimal interface intended for Skill/Agent invocation.

Usage:
    python -m mdq index   [--root PATH ...] [--rebuild]
    python -m mdq watch   [--root PATH ...] [--debounce-ms 500]
                              [--burst-threshold 100] [--burst-window-s 1.0]
                              [--initial-index]
    python -m mdq search  --q "..." [--paths GLOB ...] [--tags t1 t2]
                              [--top-k 5] [--max-tokens 800]
                              [--mode bm25|grep]
                              [--format jsonl|compact]
    python -m mdq get     --chunk-id ID
    python -m mdq list    [--paths GLOB ...] [--heading-level N]
    python -m mdq stats

Root resolution (when ``--root`` is omitted):
    1. ``<repo_root>/mdq.toml`` ``[index].roots``
    2. ``<repo_root>/.mdq/config.toml`` ``[index].roots``
    3. ``mdq.config.GENERIC_DEFAULT_ROOTS`` (``docs``, ``users-guide``)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Optional

from . import config as _config
from . import indexer, search as searcher, store
from . import usage_log as _usage_log

# Generic minimal defaults. Repositories with richer documentation layouts
# (e.g. ``knowledge/``, ``qa/``, ``original-docs/``) should declare their
# roots via ``mdq.toml`` or ``.mdq/config.toml``; see ``mdq.config``.
# Missing directories are silently skipped by the indexer, so listing
# non-existent folders is safe.
DEFAULT_ROOTS = list(_config.GENERIC_DEFAULT_ROOTS)


def _effective_roots(cli_roots):
    """Resolve roots from CLI args / config file / built-in defaults."""
    return _config.resolve_roots(Path.cwd(), cli_roots=cli_roots)


def _add_db_arg(p: argparse.ArgumentParser, *, allow_auto: bool = False) -> None:
    p.add_argument("--db", default=None,
                   help="SQLite store path. If omitted, resolves to "
                        ".mdq/index-<lang>-<strategy>.sqlite via --lang/--strategy.")
    p.add_argument("--lang", choices=["ja-jp", "en-us"], default="ja-jp",
                   help="Tokenize language (default: ja-jp). Selects FTS5 "
                        "tokenizer and the per-language DB instance.")
    strategy_choices = ["heading", "heading_recursive", "fixed_window",
                        "semantic_paragraph", "pageindex"]
    if allow_auto:
        strategy_choices = ["auto"] + strategy_choices
        p.add_argument(
            "--strategy",
            choices=strategy_choices,
            default="auto",
            help="Markdown chunking strategy (default for search: auto). "
                 "'auto' lets mdq.query_router pick the best strategy from "
                 "the query text; on miss it falls back to existing DBs.",
        )
    else:
        p.add_argument(
            "--strategy",
            choices=strategy_choices,
            default="heading",
            help="Markdown chunking strategy (default: heading).",
        )


def _resolve_db(args: argparse.Namespace) -> str:
    """Return the effective DB path string.

    If ``--db`` is given explicitly use it; otherwise compute
    ``.mdq/index-<lang>-<strategy>.sqlite``.
    """
    if args.db:
        return args.db
    strat = getattr(args, "strategy", "heading")
    # 'auto' is only valid for search; for other subcommands we never pass
    # allow_auto=True. Defensive guard in case _resolve_db is called early.
    if strat == "auto":
        strat = "heading"
    return str(store.db_path_for(args.lang, strat))


def cmd_index(args: argparse.Namespace) -> int:
    roots = _effective_roots(args.root)
    repo_root = Path.cwd()
    db_path = _resolve_db(args)
    conn = store.open_store(db_path, lang=args.lang)
    # Install semantic_paragraph runtime overrides (Q8=A: all CLI-overridable).
    if args.strategy == "semantic_paragraph":
        from . import strategies_semantic as _sem
        _sem.clear_runtime_config()
        _sem.set_runtime_config(
            percentile_lo=getattr(args, "breakpoint_percentile_lo", None),
            percentile_hi=getattr(args, "breakpoint_percentile_hi", None),
            min_chars=getattr(args, "min_chars", None),
            max_chars=(args.max_chunk_chars or None),
            contextualize=(False
                           if getattr(args, "no_semantic_contextualize", False)
                           else None),
            embed_provider=getattr(args, "embed_provider", None),
            embed_model=getattr(args, "embed_model", None),
            late_chunking=(True
                           if getattr(args, "late_chunking", False)
                           else None),
        )
    # Install pageindex runtime overrides.
    if args.strategy == "pageindex":
        from . import strategies_pageindex as _pi
        _pi.clear_runtime_config()
        _pi.set_runtime_config(
            summary_chars=(getattr(args, "pageindex_summary_chars", None) or None),
            summary_mode=getattr(args, "pageindex_summary_mode", None),
        )
    t0 = perf_counter()
    summary = indexer.build_index(
        repo_root, roots, conn,
        rebuild=args.rebuild,
        prune=not args.no_prune,
        max_chunk_chars=args.max_chunk_chars,
        strategy=args.strategy,
        overlap_paragraphs=getattr(args, "overlap_paragraphs", None),
    )
    elapsed_ms = int((perf_counter() - t0) * 1000)
    summary["roots"] = roots
    _usage_log.append_record(
        command="index",
        args={
            "roots": roots,
            "rebuild": bool(args.rebuild),
            "no_prune": bool(args.no_prune),
            "max_chunk_chars": int(args.max_chunk_chars),
            "overlap_paragraphs": getattr(args, "overlap_paragraphs", None),
            "strategy": args.strategy,
        },
        elapsed_ms=elapsed_ms,
        result={
            "files_indexed": int(summary.get("files_indexed", 0)),
            "files_skipped": int(summary.get("files_skipped", 0)),
            "chunks_written": int(summary.get("chunks_written", 0)),
            "pruned_files": int(summary.get("pruned_files", 0)),
            "pruned_chunks": int(summary.get("pruned_chunks", 0)),
        },
        exit_code=0,
        repo_root=repo_root,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()

    # Resolve strategy via the router when --strategy auto is requested.
    # The query interface stays unified: callers do not pre-select strategies.
    router_decision = None
    effective_strategy = args.strategy
    if args.strategy == "auto":
        from . import query_router as _router
        available = _router.discover_available_strategies(repo_root)
        router_decision = _router.classify_query(
            args.q,
            available_strategies=available if available else None,
            mode=args.mode,
        )
        effective_strategy = router_decision.strategy

    # Reuse _resolve_db's logic but with the resolved strategy.
    if args.db:
        db_path = args.db
    else:
        db_path = str(store.db_path_for(args.lang, effective_strategy))
    conn = store.open_store(db_path, lang=args.lang)

    # --include-parent is shorthand for --with-parent-depth 1.
    with_parent_depth = int(getattr(args, "with_parent_depth", 0) or 0)
    if args.include_parent and with_parent_depth <= 0:
        with_parent_depth = 1

    t0 = perf_counter()
    hits = searcher.search(
        conn, args.q,
        mode=args.mode,
        top_k=args.top_k,
        max_tokens=args.max_tokens,
        path_globs=args.paths or None,
        tags=args.tags or None,
        snippet_radius=args.snippet_radius,
        include_parent=bool(with_parent_depth >= 1),
        parent_depth=with_parent_depth,
        expand_neighbors=args.expand_neighbors,
        merge_parts=args.merge_parts,
        engine=args.engine,
        fusion_alpha=getattr(args, "fusion_alpha", None),
        pageindex_tree_depth=int(
            getattr(args, "pageindex_tree_depth", 0) or 0
        ),
    )
    elapsed_ms = int((perf_counter() - t0) * 1000)
    # 集計: snippet 文字数合計と、参照元ファイルの全文字数推定
    # （Context 削減率の算出に使用する。捏造防止のため取得不能時は 0。）
    snippet_chars = 0
    source_file_chars = 0
    seen_files: set[str] = set()
    score_top: Optional[float] = None
    score_2nd: Optional[float] = None  # C2 上位 2 件 score 差用
    sorted_scores: list[float] = sorted(
        (float(h.score) for h in hits), reverse=True
    )
    if sorted_scores:
        score_top = sorted_scores[0]
        if len(sorted_scores) >= 2:
            score_2nd = sorted_scores[1]
    for h in hits:
        snippet_chars += len((h.snippet or ""))
        if h.path and h.path not in seen_files:
            seen_files.add(h.path)
            try:
                p = (repo_root / h.path)
                if p.exists() and p.is_file():
                    source_file_chars += len(p.read_text(encoding="utf-8",
                                                          errors="ignore"))
            except Exception:
                pass
    if args.format == "compact":
        for h in hits:
            print(f"{h.path}:{h.start_line}-{h.end_line}  "
                  f"[{h.heading_path}]  score={h.score:.2f}")
            for ln in h.snippet.splitlines():
                print(f"  | {ln}")
    else:
        for h in hits:
            print(json.dumps(h.to_dict(), ensure_ascii=False))
    result: dict = {
        "hit_count": len(hits),
        "snippet_chars": snippet_chars,
        "source_file_chars": source_file_chars,
    }
    if score_top is not None:
        result["score_top"] = score_top
    if score_2nd is not None:
        result["score_2nd"] = score_2nd
    # Count how many hits actually expanded a parent (for H2 metric).
    parent_expanded = sum(
        1 for h in hits
        if h.expansion is not None and h.expansion.get("parent")
    )
    if parent_expanded:
        result["parent_expanded"] = parent_expanded
    log_args = {
        "q": args.q,
        "mode": args.mode,
        "top_k": int(args.top_k),
        "max_tokens": int(args.max_tokens),
        "paths": list(args.paths or []),
        "tags": list(args.tags or []),
        "snippet_radius": int(args.snippet_radius),
        "include_parent": bool(args.include_parent),
        "with_parent_depth": int(with_parent_depth),
        "expand_neighbors": int(args.expand_neighbors),
        "merge_parts": bool(args.merge_parts),
        "engine": args.engine,
        "strategy": args.strategy,
        "effective_strategy": effective_strategy,
    }
    if router_decision is not None:
        log_args["router_reason"] = router_decision.reason
        log_args["router_rule_id"] = router_decision.rule_id
        log_args["router_fallback_used"] = router_decision.fallback_used
    _usage_log.append_record(
        command="search",
        args=log_args,
        elapsed_ms=elapsed_ms,
        result=result,
        exit_code=0,
        repo_root=repo_root,
    )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    conn = store.open_store(_resolve_db(args), lang=args.lang)
    t0 = perf_counter()
    chunk = searcher.get_chunk(conn, args.chunk_id)
    elapsed_ms = int((perf_counter() - t0) * 1000)
    if not chunk:
        _usage_log.append_record(
            command="get",
            args={"chunk_id": args.chunk_id},
            elapsed_ms=elapsed_ms,
            result={"found": False, "body_chars": 0},
            exit_code=1,
            repo_root=repo_root,
        )
        print(json.dumps({"error": "not_found"}), file=sys.stderr)
        return 1
    body = chunk.get("body", "") if isinstance(chunk, dict) else ""
    _usage_log.append_record(
        command="get",
        args={"chunk_id": args.chunk_id},
        elapsed_ms=elapsed_ms,
        result={"found": True, "body_chars": len(body or "")},
        exit_code=0,
        repo_root=repo_root,
    )
    print(json.dumps(chunk, ensure_ascii=False))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    conn = store.open_store(_resolve_db(args), lang=args.lang)
    t0 = perf_counter()
    items = searcher.list_chunks(
        conn,
        path_globs=args.paths or None,
        heading_level=args.heading_level,
        limit=args.limit,
    )
    elapsed_ms = int((perf_counter() - t0) * 1000)
    for it in items:
        print(json.dumps(it, ensure_ascii=False))
    _usage_log.append_record(
        command="list",
        args={
            "paths": list(args.paths or []),
            "heading_level": args.heading_level,
            "limit": int(args.limit),
        },
        elapsed_ms=elapsed_ms,
        result={"count": len(items)},
        exit_code=0,
        repo_root=repo_root,
    )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    conn = store.open_store(_resolve_db(args), lang=args.lang)
    t0 = perf_counter()
    s = store.stats(conn)
    elapsed_ms = int((perf_counter() - t0) * 1000)
    print(json.dumps(s, ensure_ascii=False))
    _usage_log.append_record(
        command="stats",
        args={},
        elapsed_ms=elapsed_ms,
        result={"files": int(s.get("files", 0)),
                "chunks": int(s.get("chunks", 0))},
        exit_code=0,
        repo_root=repo_root,
    )
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """`python -m mdq watch` - フォアグラウンドでリアルタイム索引更新。

    既存の ``index`` サブコマンドはそのまま残しており、ユーザーが手動で索引を
    更新する選択肢は維持されている。本コマンドは開発時のスタンドアロン
    動作確認用、または上位 Orchestrator とは別プロセスで watcher だけを動かしたい
    場合のためのもの。Ctrl+C で停止する。
    """
    import logging
    import signal
    import time as _time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        from . import watcher as _watcher_mod
    except ImportError as exc:  # pragma: no cover - defensive
        print(json.dumps({"error": f"watcher import failed: {exc}"}),
              file=sys.stderr)
        return 1

    roots = _effective_roots(args.root)
    repo_root = Path.cwd()
    db_path = Path(_resolve_db(args))

    # 初回索引は明示的に要求された場合のみ実行する（ユーザーが既存 `index`
    # を直前に流していれば二重実行を避けたい）。
    if args.initial_index:
        conn = store.open_store(db_path, lang=args.lang)
        summary = indexer.build_index(repo_root, roots, conn,
                                      rebuild=False, prune=True,
                                      strategy=args.strategy)
        summary["roots"] = roots
        print(json.dumps({"initial_index": summary}, ensure_ascii=False))
        try:
            conn.close()
        except Exception:
            pass

    w = _watcher_mod.MdqWatcher(
        repo_root=repo_root,
        roots=roots,
        db_path=db_path,
        debounce_ms=args.debounce_ms,
        burst_threshold=args.burst_threshold,
        burst_window_s=args.burst_window_s,
        lang=args.lang,
        strategy=args.strategy,
    )
    ok = w.start()
    if not ok:
        print(json.dumps({"error": "watcher start failed (watchdog 未導入か)"}),
              file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "watching",
        "roots": roots,
        "db": str(db_path),
        "debounce_ms": args.debounce_ms,
    }, ensure_ascii=False))

    stop = threading_event_or_none()

    def _handle_sigint(signum, frame):  # type: ignore[no-untyped-def]
        if stop is not None:
            stop.set()

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:
        pass

    try:
        if stop is not None:
            stop.wait()
        else:  # pragma: no cover - fallback
            while True:
                _time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        w.stop()
    return 0


def threading_event_or_none():
    """threading.Event を返す（テスト容易性のため関数化）。"""
    try:
        import threading
        return threading.Event()
    except Exception:  # pragma: no cover
        return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mdq",
                                description="Local-only Markdown query toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    p_idx = sub.add_parser("index", help="Build or update the index")
    _add_db_arg(p_idx)
    p_idx.add_argument("--root", action="append",
                       help="Index root (repeatable). When omitted, roots are "
                            "resolved from mdq.toml / .mdq/config.toml "
                            "([index].roots) or fall back to the built-in "
                            "generic defaults. See mdq.config.")
    p_idx.add_argument("--rebuild", action="store_true",
                       help="Rebuild even if file hashes match")
    p_idx.add_argument("--no-prune", action="store_true",
                       help="Do not remove store entries for files that no "
                            "longer exist on disk (default: prune enabled)")
    p_idx.add_argument("--max-chunk-chars", type=int, default=0,
                       help="If >0, sub-split chunks larger than this many "
                            "chars at paragraph/line boundaries (code fences "
                            "stay intact). 0 disables (default).")
    p_idx.add_argument(
        "--overlap-paragraphs", type=int, default=None,
        help="heading_recursive strategy only: prepend trailing N paragraphs "
             "of each text sub-chunk to the next (overlap window). "
             "Defaults to mdq.strategies.HEADING_RECURSIVE_OVERLAP_PARAGRAPHS (=1).",
    )
    # --- semantic_paragraph strategy options (Q1/Q2/Q4/Q8/Q11) -----------
    p_idx.add_argument(
        "--breakpoint-percentile-lo", type=float, default=None,
        help="semantic_paragraph: lower bound of percentile binary search "
             "(default: 50).",
    )
    p_idx.add_argument(
        "--breakpoint-percentile-hi", type=float, default=None,
        help="semantic_paragraph: upper bound of percentile binary search "
             "(default: 99).",
    )
    p_idx.add_argument(
        "--min-chars", type=int, default=None,
        help="semantic_paragraph: minimum chunk size in chars "
             "(default: 200). Shorter sub-chunks are merged into predecessor.",
    )
    p_idx.add_argument(
        "--embed-provider", default=None,
        help="semantic_paragraph: embedding provider name. Falls back to "
             "MDQ_EMBED_PROVIDER env or 'fastembed' (default).",
    )
    p_idx.add_argument(
        "--embed-model", default=None,
        help="semantic_paragraph: embedding model name. Falls back to "
             "MDQ_EMBED_MODEL env or 'intfloat/multilingual-e5-large' (default; MIT, ~2.2GB first DL).",
    )
    p_idx.add_argument(
        "--no-semantic-contextualize", action="store_true",
        help="semantic_paragraph: disable the default-on contextualizer "
             "template (Q11=B). When set, chunk text is raw body only.",
    )
    p_idx.add_argument(
        "--late-chunking", action="store_true",
        help="semantic_paragraph: enable late-chunking pass (Q9=B). "
             "Embeds each final chunk and persists vectors into the "
             "chunk_embedding column for linear-weighted retrieval fusion.",
    )
    # --- pageindex strategy options --------------------------------------
    p_idx.add_argument(
        "--pageindex-summary-chars", type=int, default=0,
        help="pageindex: per-chunk summary length in characters "
             "(0 uses code default PAGEINDEX_SUMMARY_CHARS=200).",
    )
    p_idx.add_argument(
        "--pageindex-summary-mode",
        choices=["head", "first_paragraph"], default=None,
        help="pageindex: summary extraction mode "
             "(default: 'head' — first N chars of the body). "
             "'first_paragraph' picks the first paragraph, clipped to N chars.",
    )
    p_idx.set_defaults(func=cmd_index)

    p_s = sub.add_parser("search", help="Search the index")
    _add_db_arg(p_s, allow_auto=True)
    p_s.add_argument("--q", required=True, help="Query string")
    p_s.add_argument("--mode", choices=["bm25", "grep"], default="bm25")
    p_s.add_argument("--top-k", type=int, default=5)
    p_s.add_argument("--max-tokens", type=int, default=800,
                     help="Approximate snippet-token budget across all hits")
    p_s.add_argument("--paths", nargs="*", help="Path glob filters (fnmatch)")
    p_s.add_argument("--tags", nargs="*", help="Frontmatter tag filters (AND)")
    p_s.add_argument("--snippet-radius", type=int, default=2)
    p_s.add_argument("--include-parent", action="store_true",
                     help="Include the nearest ancestor heading chunk in "
                          "expansion. Equivalent to --with-parent-depth 1.")
    p_s.add_argument(
        "--with-parent-depth", type=int, default=0, metavar="N",
        help="Include up to N ancestor heading chunks in expansion "
             "(0 disables, 1 = direct parent, >=2 walks the chain).",
    )
    p_s.add_argument("--expand-neighbors", type=int, default=0, metavar="N",
                     help="Include N adjacent chunks (before/after) per hit.")
    p_s.add_argument("--merge-parts", action="store_true",
                     help="Include sibling parts (part_total>1) of the hit.")
    p_s.add_argument("--engine", choices=["auto", "bm25", "fts5"],
                     default="auto",
                     help="Search engine. 'auto' uses FTS5 when MDQ_FTS5 "
                          "(or legacy HVE_MDQ_FTS5) env is set and supported, "
                          "otherwise in-memory BM25 (default).")
    p_s.add_argument(
        "--fusion-alpha", type=float, default=None,
        help="When the index has chunk_embedding values (late-chunking), "
             "blend final_score = alpha*bm25_norm + (1-alpha)*cosine_sim. "
             "Default: 0.5. Set to 1.0 to disable vector blending; 0.0 to "
             "score by cosine only.",
    )
    p_s.add_argument(
        "--pageindex-tree-depth", type=int, default=0, metavar="N",
        help="pageindex DB 限定: each hit's expansion gets a "
             "table-of-contents 'tree_path' walking up to N ancestor "
             "heading chunks. Each node = {chunk_id, heading_path, summary}. "
             "Ordered root-first, hit last. 0 disables (default). "
             "他 strategy DB では summary 列が NULL のため黙って無視される。",
    )
    p_s.add_argument("--format", choices=["jsonl", "compact"], default="jsonl")
    p_s.set_defaults(func=cmd_search)

    p_g = sub.add_parser("get", help="Fetch a single chunk by chunk_id")
    _add_db_arg(p_g)
    p_g.add_argument("--chunk-id", required=True)
    p_g.set_defaults(func=cmd_get)

    p_l = sub.add_parser("list", help="List indexed chunks (headings)")
    _add_db_arg(p_l)
    p_l.add_argument("--paths", nargs="*")
    p_l.add_argument("--heading-level", type=int, default=None)
    p_l.add_argument("--limit", type=int, default=200)
    p_l.set_defaults(func=cmd_list)

    p_st = sub.add_parser("stats", help="Show index statistics")
    _add_db_arg(p_st)
    p_st.set_defaults(func=cmd_stats)

    p_w = sub.add_parser(
        "watch",
        help="Realtime index updates via watchdog (standalone watcher process)",
    )
    _add_db_arg(p_w)
    p_w.add_argument("--root", action="append",
                     help="Watch root (repeatable). Resolved like --root for "
                          "`index` (mdq.toml / .mdq/config.toml / defaults).")
    p_w.add_argument("--debounce-ms", type=int, default=500,
                     help="同一ファイルへの連続イベントを抑制するデバウンス時間 (ms, 既定 500)")
    p_w.add_argument("--burst-threshold", type=int, default=100,
                     help="バースト検出閾値（イベント件数 / burst-window-s）。"
                          "超過時は build_index で全 root を再走査する (既定 100)")
    p_w.add_argument("--burst-window-s", type=float, default=1.0,
                     help="バースト検出ウィンドウ秒数 (既定 1.0)")
    p_w.add_argument("--initial-index", action="store_true",
                     help="watch 開始前に build_index を 1 回実行する")
    p_w.set_defaults(func=cmd_watch)

    return p


def _ensure_utf8_stdio() -> None:
    """Force stdout/stderr to UTF-8 to avoid UnicodeEncodeError on Windows cp932.

    JSON 出力には ensure_ascii=False で非 ASCII（絵文字・日本語）が含まれるため、
    Windows のレガシー cp932 標準出力では `\\U0001f4c4` 等が encode 失敗で exit 1
    となる。Agent からのツール呼び出しを安定させるため、起動時に UTF-8 を強制する。
    `reconfigure` 不在環境（リダイレクト時の TextIOWrapper 以外）は黙ってスキップ。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
