"""hve/recovery.py — Phase 4 (Resume 2-layer txn): 起動時 recovery。

`<session-state-dir>/journal-archive/` 配下の未完了 `begin` レコードに対する補償処理を行う。
主な対象: `delete-hard.begin` で開始されたものの、SDK 削除やディレクトリ削除の
途中でクラッシュしたケース。

== Recovery 原則 ==

- 全操作は idempotent。再実行しても副作用が増えない。
- SDK 側削除は `get_session_metadata(sid)` で存在確認してから `delete_session(sid)`。
- ディレクトリ削除は `Path.exists()` で確認してから `shutil.rmtree()`。
- recovery 完了後に journal ファイルの末尾へ `end` レコードを append する
  （archive 内のファイルへの追記）。
"""

from __future__ import annotations

import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    from .run_journal import (
        DEFAULT_ARCHIVE_DIRNAME,
        KIND_DELETE_HARD_DIR_REMOVED,
        KIND_DELETE_HARD_END,
        KIND_DELETE_HARD_SDK_DELETED,
        KIND_DELETE_HARD_SDK_FAILED,
        scan_archive_for_pending,
    )
    from .run_state import DEFAULT_RUNS_DIR, DEFAULT_SESSION_ID_PREFIX, _safe_run_id_component
except ImportError:
    from run_journal import (  # type: ignore[no-redef]
        DEFAULT_ARCHIVE_DIRNAME,
        KIND_DELETE_HARD_DIR_REMOVED,
        KIND_DELETE_HARD_END,
        KIND_DELETE_HARD_SDK_DELETED,
        KIND_DELETE_HARD_SDK_FAILED,
        scan_archive_for_pending,
    )
    from run_state import DEFAULT_RUNS_DIR, DEFAULT_SESSION_ID_PREFIX, _safe_run_id_component  # type: ignore[no-redef]


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append_to_archived_journal(archive_path: Path, record: Dict[str, Any]) -> None:
    """archive 済み journal ファイルへ末尾 append。"""
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with archive_path.open("a", encoding="utf-8") as f:
        f.write(line)


def _read_records(path: Path) -> List[Dict[str, Any]]:
    """journal ファイルから全レコードを読む。"""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ---------------------------------------------------------------------------
# delete-hard recovery
# ---------------------------------------------------------------------------

async def _recover_one_delete_hard(
    archive_path: Path,
    *,
    work_dir: Path,
    sdk_delete_session: Optional[Callable[[str], Awaitable[None]]] = None,
    sdk_session_exists: Optional[Callable[[str], Awaitable[bool]]] = None,
    print_fn: Callable[[str], None] = lambda s: print(s, file=sys.stderr),
) -> Dict[str, Any]:
    """1 つの archive ファイル内の未完了 delete-hard を完遂させる。

    Args:
        archive_path: pending な archive ファイル。
        work_dir: `<session-state-dir>/runs/` のルート（実 run_id ディレクトリ削除用）。
        sdk_delete_session: SDK `delete_session(sid)` 相当の関数。
            None なら SDK 操作はスキップ（dir 削除のみ）。
        sdk_session_exists: SDK `get_session_metadata(sid) is not None` 相当。
            None なら毎回 delete を試みる（失敗を握り潰す）。
        print_fn: 進捗ログ出力先。

    Returns:
        recovery 結果のサマリ dict。
    """
    records = _read_records(archive_path)
    if not records:
        return {"archive": str(archive_path), "skipped": True, "reason": "empty"}

    # begin / step / end の seq マップを構築
    pending_begins: Dict[int, Dict[str, Any]] = {}
    completed_seqs: set = set()
    sdk_deleted_per_seq: Dict[int, set] = {}
    dir_removed_per_seq: set = set()

    for rec in records:
        try:
            seq = int(rec.get("seq", -1))
        except (TypeError, ValueError):
            continue
        k = rec.get("kind", "")
        if k.endswith(".begin"):
            pending_begins[seq] = rec
        elif k.endswith(".end"):
            completed_seqs.add(seq)
        elif k == KIND_DELETE_HARD_SDK_DELETED:
            sdk_deleted_per_seq.setdefault(seq, set()).add(rec.get("target", ""))
        elif k == KIND_DELETE_HARD_DIR_REMOVED:
            dir_removed_per_seq.add(seq)

    summary = {
        "archive": str(archive_path),
        "recovered_seqs": [],
        "errors": [],
    }

    for seq, begin_rec in pending_begins.items():
        if seq in completed_seqs:
            continue
        kind = begin_rec.get("kind", "")
        if not kind.startswith("delete-hard."):
            # delete-hard 以外の意図は本モジュールでは扱わない
            continue

        payload = begin_rec.get("payload") or {}
        run_id_target = begin_rec.get("target", "")
        session_ids: List[str] = list(payload.get("session_ids") or [])

        print_fn(f"[recovery] delete-hard seq={seq} target={run_id_target} を再開します")

        # 1. 未削除の SDK セッションを処理
        already_deleted = sdk_deleted_per_seq.get(seq, set())
        for sid in session_ids:
            if sid in already_deleted:
                continue
            if not sid.startswith(DEFAULT_SESSION_ID_PREFIX):
                # 安全ガード: hve prefix のみ
                summary["errors"].append(
                    f"seq={seq} sid={sid}: prefix '{DEFAULT_SESSION_ID_PREFIX}' \u3067\u59cb\u307e\u3089\u305a\u30b9\u30ad\u30c3\u30d7"
                )
                continue
            if sdk_delete_session is None:
                summary["errors"].append(
                    f"seq={seq} sid={sid}: SDK \u672a\u63a5\u7d9a\u306e\u305f\u3081 SDK \u524a\u9664\u30b9\u30ad\u30c3\u30d7"
                )
                continue
            try:
                if sdk_session_exists is not None:
                    exists = await sdk_session_exists(sid)
                    if not exists:
                        # \u65e2\u306b\u524a\u9664\u6e08 \u2192 \u8a18\u9332\u3060\u3051\u8ffd\u52a0
                        _append_to_archived_journal(archive_path, {
                            "seq": seq, "ts": _utc_now_iso(),
                            "kind": KIND_DELETE_HARD_SDK_DELETED,
                            "target": sid,
                            "payload": {"recovered": True, "note": "already-absent"},
                        })
                        continue
                await sdk_delete_session(sid)
                _append_to_archived_journal(archive_path, {
                    "seq": seq, "ts": _utc_now_iso(),
                    "kind": KIND_DELETE_HARD_SDK_DELETED,
                    "target": sid,
                    "payload": {"recovered": True},
                })
            except Exception as exc:
                summary["errors"].append(
                    f"seq={seq} sid={sid}: SDK \u524a\u9664\u5931\u6557 ({type(exc).__name__}: {exc})"
                )
                _append_to_archived_journal(archive_path, {
                    "seq": seq, "ts": _utc_now_iso(),
                    "kind": KIND_DELETE_HARD_SDK_FAILED,
                    "target": sid,
                    "payload": {"recovered": True, "error": f"{type(exc).__name__}: {exc}"},
                })

        # 2. run_dir 削除
        if seq not in dir_removed_per_seq and run_id_target:
            # Critical: パス安全性チェックは削除処理の try ブロック外で行う。
            # ValueError（不正な run_id）の場合はディレクトリ削除を一切試行せず
            # 即座に次の seq へスキップする（ディレクトリトラバーサル防止）。
            try:
                safe = _safe_run_id_component(run_id_target)
            except ValueError as exc:
                summary["errors"].append(
                    f"seq={seq} run_dir={run_id_target}: \u4e0d\u6b63\u306arun_id ({exc})"
                )
                continue
            try:
                target_dir = work_dir / safe
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                _append_to_archived_journal(archive_path, {
                    "seq": seq, "ts": _utc_now_iso(),
                    "kind": KIND_DELETE_HARD_DIR_REMOVED,
                    "target": run_id_target,
                    "payload": {"recovered": True},
                })
            except OSError as exc:
                summary["errors"].append(
                    f"seq={seq} run_dir={run_id_target}: \u524a\u9664\u5931\u6557 ({exc})"
                )

        # 3. end \u3092\u8ffd\u8a18
        _append_to_archived_journal(archive_path, {
            "seq": seq, "ts": _utc_now_iso(),
            "kind": KIND_DELETE_HARD_END,
            "target": run_id_target,
            "payload": {"recovered": True},
        })
        summary["recovered_seqs"].append(seq)

    return summary


async def recover_pending_on_startup(
    *,
    work_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None,
    sdk_delete_session: Optional[Callable[[str], Awaitable[None]]] = None,
    sdk_session_exists: Optional[Callable[[str], Awaitable[bool]]] = None,
    print_fn: Callable[[str], None] = lambda s: print(s, file=sys.stderr),
) -> List[Dict[str, Any]]:
    """`<session-state-dir>/journal-archive/` 配下の未完了 begin を全て recovery する。

    Args:
        work_dir: `<session-state-dir>/runs/` ルート（既定 `DEFAULT_RUNS_DIR`）。
        archive_dir: archive ディレクトリ（既定 `<work_dir のひとつ上>/journal-archive`）。
        sdk_delete_session / sdk_session_exists: SDK 関数。None なら SDK 操作スキップ。

    Returns:
        各 archive ファイルの recovery サマリのリスト。
    """
    wd = Path(work_dir) if work_dir else DEFAULT_RUNS_DIR
    ad = Path(archive_dir) if archive_dir else (wd.parent / DEFAULT_ARCHIVE_DIRNAME)
    pending = scan_archive_for_pending(ad)
    if not pending:
        return []
    results: List[Dict[str, Any]] = []
    for archive_path in pending:
        try:
            res = await _recover_one_delete_hard(
                archive_path,
                work_dir=wd,
                sdk_delete_session=sdk_delete_session,
                sdk_session_exists=sdk_session_exists,
                print_fn=print_fn,
            )
            results.append(res)
        except Exception as exc:  # pragma: no cover - top-level guard
            print_fn(f"[recovery] {archive_path.name}: 例外 ({type(exc).__name__}: {exc})")
            results.append({"archive": str(archive_path), "error": str(exc)})
    return results


__all__ = [
    "recover_pending_on_startup",
]
