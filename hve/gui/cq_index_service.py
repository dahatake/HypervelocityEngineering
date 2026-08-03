"""Compatibility exports for the shared Code Query GUI service."""

from cq.gui.index_service import (
    build,
    config_candidates,
    delete_index_db,
    get_index_stats,
    get_index_stats_all_profiles,
    list_profiles,
    search_preview,
)

__all__ = [
    "build",
    "config_candidates",
    "delete_index_db",
    "get_index_stats",
    "get_index_stats_all_profiles",
    "list_profiles",
    "search_preview",
]
