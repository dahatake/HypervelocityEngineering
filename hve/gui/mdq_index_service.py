"""Compatibility exports for the shared Markdown Query GUI service."""

from mdq.gui.index_service import (
    delete_index_db,
    get_index_stats,
    get_index_stats_all_strategies,
    rebuild_index,
    resolve_effective_roots,
    search_preview,
)

__all__ = [
    "delete_index_db",
    "get_index_stats",
    "get_index_stats_all_strategies",
    "rebuild_index",
    "resolve_effective_roots",
    "search_preview",
]
