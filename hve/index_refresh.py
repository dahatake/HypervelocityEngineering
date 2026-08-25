"""hve.index_refresh — 起動時に既存の mdq / cq 索引 DB を差分更新する（FR-CLI-77 / FR-GUI-22）。

CLI と GUI が共有する単一実装。対象は**実在する索引 DB だけ**とし、未構築の
strategy / profile を起動時に作らない。索引 DB のパス規則は `mdq` / `cq` 側の
実装を単一の情報源とする（FR-MAINT-07）。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FLAG = "HVE_STARTUP_INDEX_REFRESH"

# `hve/config.py` の `_env_bool` と同一規約。相対 / 絶対 import の双方で読み込ま
# れうるモジュールのため、当該ヘルパを import せず同じ判定を持つ。
_ENABLED_VALUES = frozenset({"true", "1", "yes"})

_lock = threading.Lock()
_thread: threading.Thread | None = None
_done = threading.Event()
_done.set()


@dataclass(frozen=True)
class Target:
    """差分更新の対象 1 件。

    ``label`` は mdq が ``"<lang>/<strategy>"``、cq が ``"<profile>"``。
    """

    engine: str
    label: str
    db_path: Path


def is_enabled() -> bool:
    raw = os.environ.get(ENV_FLAG)
    if raw is None:
        return True
    return raw.strip().lower() in _ENABLED_VALUES


def enumerate_targets(repo_root: Path | str) -> list[Target]:
    root = _resolved(repo_root)
    return _mdq_targets(root) + _cq_targets(root)


def _resolved(repo_root: Path | str) -> Path:
    """`mdq.indexer.build_index` は解決済み絶対パスとの `relative_to` で走査するため。"""
    return Path(repo_root).resolve()


def refresh_all(repo_root: Path | str) -> dict:
    """全対象を逐次で差分更新する。1 件の失敗が残りを止めてはならない。"""
    root = _resolved(repo_root)
    targets = enumerate_targets(root)
    refreshed = 0
    failed: list[str] = []
    for target in targets:
        try:
            if target.engine == "mdq":
                _refresh_mdq(root, target)
            else:
                _refresh_cq(root, target)
            refreshed += 1
        except Exception as exc:  # noqa: BLE001 -- 補助機構。本体実行を妨げない
            failed.append(f"{target.engine}:{target.label}: {exc}")
            logger.warning(
                "index refresh: %s %s の差分更新に失敗しました (%s)",
                target.engine, target.label, exc,
            )
    return {"targets": len(targets), "refreshed": refreshed, "failed": failed}


def start_background(repo_root: Path | str) -> bool:
    """差分更新をバックグラウンドで開始する。プロセス内 1 回だけ起動する。"""
    global _thread

    if not is_enabled():
        return False
    with _lock:
        if _thread is not None:
            return False
        _done.clear()
        _thread = threading.Thread(
            target=_worker, args=(Path(repo_root),),
            name="hve-index-refresh", daemon=True,
        )
        _thread.start()
    return True


def is_running() -> bool:
    return not _done.is_set()


def wait_until_idle(timeout: float | None = None) -> bool:
    """差分更新の完了を待つ。開始していなければ即座に ``True`` を返す。"""
    return _done.wait(timeout)


def _worker(repo_root: Path) -> None:
    try:
        summary = refresh_all(repo_root)
        logger.info("index refresh: %s", summary)
    except Exception as exc:  # noqa: BLE001 -- 起動を妨げない
        logger.warning("index refresh: 起動時の差分更新に失敗しました (%s)", exc)
    finally:
        _done.set()


def _mdq_targets(root: Path) -> list[Target]:
    from mdq import store as mdq_store

    try:
        found = mdq_store.existing_index_dbs(root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("index refresh: mdq 索引の列挙に失敗しました (%s)", exc)
        return []
    return [
        Target("mdq", f"{lang}/{strategy}", path) for lang, strategy, path in found
    ]


def _cq_targets(root: Path) -> list[Target]:
    from cq import config as cq_config
    from cq import store as cq_store

    try:
        profiles = cq_config.resolve_profiles(root)
    except Exception as exc:  # noqa: BLE001 -- 設定不在は FR-CQ-01 の fail-closed に従い対象 0 件
        logger.debug("index refresh: cq profile の解決をスキップしました (%s)", exc)
        return []
    targets: list[Target] = []
    for name in profiles:
        db_path = root / cq_store.db_path_for(name)
        if db_path.is_file():
            targets.append(Target("cq", name, db_path))
    return targets


def _refresh_mdq(root: Path, target: Target) -> None:
    from mdq import config as mdq_config
    from mdq import indexer as mdq_indexer
    from mdq import store as mdq_store

    lang, strategy = target.label.split("/", 1)
    conn = mdq_store.open_store(target.db_path, lang=lang)
    try:
        mdq_indexer.build_index(
            root,
            mdq_config.resolve_roots(root),
            conn,
            rebuild=False,
            prune=True,
            strategy=strategy,
            tabular_globs=mdq_config.resolve_tabular_globs(root),
        )
    finally:
        conn.close()


def _refresh_cq(root: Path, target: Target) -> None:
    from cq import config as cq_config
    from cq import indexer as cq_indexer

    cq_indexer.build_index(
        root,
        cq_config.resolve_profile(root, target.label),
        db_path=target.db_path,
        rebuild=False,
    )
