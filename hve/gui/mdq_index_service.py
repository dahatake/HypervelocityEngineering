"""GUI 向け Markdown Query インデックス操作サービス。"""

from __future__ import annotations

from datetime import datetime
from time import perf_counter
from pathlib import Path
from typing import Iterable

from mdq import cli as mdq_cli
from mdq import indexer as mdq_indexer
from mdq import store as mdq_store
from mdq.strategies import ALL_STRATEGIES


def _resolve_db_path(
    repo_root: Path,
    db_path: Path | None = None,
    *,
    lang: str = "ja-jp",
    strategy: str = "heading",
) -> Path:
    if db_path is not None:
        return db_path
    return (repo_root / mdq_store.db_path_for(lang, strategy)).resolve()


def _file_mtime_iso(path: Path) -> str:
    if not path.exists():
        return "未作成"
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.isoformat(timespec="seconds")


def resolve_effective_roots(roots: Iterable[str] | None = None) -> list[str]:
    """有効な索引ルートを解決する。

    優先順位:
      1. 明示的に渡された ``roots`` 引数（非 None かつ非空）
      2. GUI 設定 ``[mdq] target_folders``（非空時）
      3. ``mdq_cli.DEFAULT_ROOTS``

    要件: ``target_folders`` 非空時は索引対象を上書きし、検索範囲と一致させる。
    """
    if roots is not None:
        explicit = [r for r in roots if r]
        if explicit:
            return list(explicit)
    try:
        from . import settings_store  # 遅延 import: 循環回避
        configured = settings_store.get_mdq_target_folders()
    except Exception:  # pragma: no cover - 設定ファイル破損時はフォールバック
        configured = []
    if configured:
        return configured
    return list(mdq_cli.DEFAULT_ROOTS)


def get_index_stats(
    repo_root: Path,
    *,
    db_path: Path | None = None,
    lang: str = "ja-jp",
    strategy: str = "heading",
) -> dict:
    """インデックス統計情報を返す。"""
    resolved_db = _resolve_db_path(repo_root, db_path, lang=lang, strategy=strategy)
    conn = mdq_store.open_store(resolved_db, lang=lang)
    try:
        base = mdq_store.stats(conn)
        root_stats = []
        for root in resolve_effective_roots():
            files = conn.execute(
                "SELECT COUNT(*) FROM files WHERE path = ? OR path LIKE ?",
                (root, f"{root}/%"),
            ).fetchone()[0]
            chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE path = ? OR path LIKE ?",
                (root, f"{root}/%"),
            ).fetchone()[0]
            root_stats.append(
                {
                    "root": root,
                    "files": int(files),
                    "chunks": int(chunks),
                }
            )
        return {
            "db_path": str(resolved_db),
            "db_exists": resolved_db.exists(),
            "db_mtime": _file_mtime_iso(resolved_db),
            "schema_version": mdq_store.SCHEMA_VERSION,
            "fts5_enabled": mdq_store.has_fts5(conn),
            "lang": lang,
            "strategy": strategy,
            "files": int(base.get("files", 0)),
            "chunks": int(base.get("chunks", 0)),
            "root_stats": root_stats,
        }
    finally:
        conn.close()


def rebuild_index(
    repo_root: Path,
    *,
    roots: Iterable[str] | None = None,
    db_path: Path | None = None,
    lang: str = "ja-jp",
    strategy: str = "heading",
    overlap_paragraphs: int | None = None,
    force: bool = False,
    semantic_options: dict | None = None,
    progress_callback=None,
) -> dict:
    """インデックスを手動更新し、更新サマリを返す。

    standalone GUI (``tools/skills/markdown_query/gui/mdq_index_service.py``)
    の同名関数と挙動を一致させること（SoT 二重管理）。詳細は当該 docstring
    を参照。
    """
    resolved_db = _resolve_db_path(repo_root, db_path, lang=lang, strategy=strategy)
    if strategy == "semantic_paragraph":
        try:
            from mdq import strategies_semantic as _sem
            _sem.clear_runtime_config()
            if semantic_options:
                _sem.set_runtime_config(**semantic_options)
        except Exception:  # noqa: BLE001 -- semantic extra not installed
            pass
    conn = mdq_store.open_store(resolved_db, lang=lang)
    try:
        t0 = perf_counter()
        selected_roots = resolve_effective_roots(roots)
        summary = mdq_indexer.build_index(
            repo_root,
            selected_roots,
            conn,
            rebuild=bool(force),
            prune=True,
            strategy=strategy,
            overlap_paragraphs=overlap_paragraphs,
            progress_callback=progress_callback,
        )
        elapsed_ms = int((perf_counter() - t0) * 1000)
        summary["roots"] = selected_roots
        summary["db_path"] = str(resolved_db)
        summary["lang"] = lang
        summary["strategy"] = strategy
        summary["elapsed_ms"] = elapsed_ms
        summary["force_rebuild"] = bool(force)
        if overlap_paragraphs is not None:
            summary["overlap_paragraphs"] = int(overlap_paragraphs)
        return summary
    finally:
        conn.close()


def delete_index_db(
    repo_root: Path,
    *,
    lang: str = "ja-jp",
    strategy: str = "heading",
    db_path: Path | None = None,
) -> dict:
    """``.mdq/index-<lang>-<strategy>.sqlite`` を削除する (Q12=B 削除のみ)。

    standalone GUI 側 ``mdq_index_service.delete_index_db`` の挙動と一致。
    """
    resolved_db = _resolve_db_path(
        repo_root, db_path, lang=lang, strategy=strategy
    )
    if not resolved_db.exists():
        return {"deleted": False, "db_path": str(resolved_db)}
    resolved_db.unlink()
    return {"deleted": True, "db_path": str(resolved_db)}


def search_preview(
    repo_root: Path,
    query: str,
    *,
    lang: str = "ja-jp",
    strategy: str = "heading",
    top_k: int = 3,
    db_path: Path | None = None,
    fusion_alpha: float | None = None,
) -> list[dict]:
    """GUI「試し検索」用 (Q4=B)。standalone GUI 側と同等のシグネチャ。"""
    from mdq import search as mdq_search

    resolved_db = _resolve_db_path(
        repo_root, db_path, lang=lang, strategy=strategy
    )
    if not resolved_db.exists():
        return []
    conn = mdq_store.open_store(resolved_db, lang=lang)
    try:
        hits = mdq_search.search(
            conn, query,
            top_k=int(top_k),
            max_tokens=600,
            fusion_alpha=fusion_alpha,
        )
        return [
            {
                "path": h.path,
                "heading_path": h.heading_path or "(top)",
                "score": float(h.score),
                "snippet": h.snippet,
            }
            for h in hits
        ]
    finally:
        conn.close()


def get_index_stats_all_strategies(
    repo_root: Path,
    *,
    lang: str = "ja-jp",
) -> dict[str, dict]:
    """全 Chunking Strategy について統計情報を取得する。

    DB が **未生成** の Strategy では ``mdq_store.open_store`` を呼ばずに
    スタブ値 (``db_exists=False`` / ``files=0`` / ``chunks=0`` /
    ``db_mtime="未作成"``) を返す。これは ``open_store`` が
    ``sqlite3.connect`` + SCHEMA 実行で **空 DB ファイルを物理生成** する
    副作用を回避するため (敵対的レビュー No.1)。

    GUI の「Strategy 別統計表」表示に使用する (T14)。
    """
    out: dict[str, dict] = {}
    for strategy in ALL_STRATEGIES:
        resolved_db = _resolve_db_path(
            repo_root, None, lang=lang, strategy=strategy
        )
        if not resolved_db.exists():
            # DB 未生成: ファイルを作らずスタブ値を返す
            out[strategy] = {
                "db_path": str(resolved_db),
                "db_exists": False,
                "db_mtime": "未作成",
                "schema_version": mdq_store.SCHEMA_VERSION,
                "fts5_enabled": False,
                "lang": lang,
                "strategy": strategy,
                "files": 0,
                "chunks": 0,
                "root_stats": [],
            }
            continue
        try:
            out[strategy] = get_index_stats(
                repo_root, lang=lang, strategy=strategy
            )
        except Exception as exc:  # pragma: no cover - 防御的
            out[strategy] = {
                "db_path": str(resolved_db),
                "db_exists": True,  # ファイルは存在するが読めない
                "db_mtime": _file_mtime_iso(resolved_db),
                "schema_version": "-",
                "fts5_enabled": False,
                "lang": lang,
                "strategy": strategy,
                "files": 0,
                "chunks": 0,
                "root_stats": [],
                "error": str(exc),
            }
    return out
