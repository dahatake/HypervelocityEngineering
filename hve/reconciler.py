"""hve/reconciler.py — Phase 5 (Resume 2-layer txn): 整合性チェック / Orphan GC。

Layer 1 (`state.json`) と Layer 2 (Copilot SDK の `~/.copilot/session-state/`) の
不整合を検出し、自動修復または列挙する。

== 検出パターン ==

| パターン | state.json | SDK 側 | 対応 |
|---|---|---|---|
| `both` | あり | あり | 整合（何もしない）|
| `state_only` | あり | なし | Resume 開始時に該当 step を `pending` + `session_id=None` に戻す |
| `sdk_only` | なし | あり | `hve-*` prefix なら orphan として GC 対象 |

== 公開 API ==

- `reconcile_run(state, *, sdk_client=None, dry_run=True)` → `ReconcileResult`
- `reconcile_all(work_dir, *, sdk_client=None, dry_run=True)`
- `gc_orphans(work_dir, *, sdk_client=None, dry_run=True)` → 削除対象 sid 一覧と実行結果

SDK の存在確認は `CopilotClient.get_session_metadata(sid)` を使う（Phase 0 調査で
公式 API 採用を確定済）。`sdk_client=None` の場合、SDK 操作はスキップして
列挙のみ実行する。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

try:
    from .run_state import (
        DEFAULT_RUNS_DIR,
        DEFAULT_SESSION_ID_PREFIX,
        RunState,
        list_resumable_runs,
    )
except ImportError:
    from run_state import (  # type: ignore[no-redef]
        DEFAULT_RUNS_DIR,
        DEFAULT_SESSION_ID_PREFIX,
        RunState,
        list_resumable_runs,
    )


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

@dataclass
class ReconcileResult:
    """1 Run 分の reconcile 結果。"""

    run_id: str
    sessions_state_only: List[str] = field(default_factory=list)
    """state.json にあるが SDK に存在しない session_id。"""
    sessions_sdk_only: List[str] = field(default_factory=list)
    """SDK にあるが state.json で参照されない session_id（orphan 候補）。"""
    sessions_both: List[str] = field(default_factory=list)
    """両方に存在し整合している session_id。"""
    sessions_unknown: List[str] = field(default_factory=list)
    """SDK 確認中に例外が起き、状態を判定できなかった session_id。dry_run の可否に関わらず状態を変更しない。"""
    actions_taken: List[str] = field(default_factory=list)
    """実際に行った修正（dry_run=False 時のみ）。"""
    actions_pending: List[str] = field(default_factory=list)
    """dry_run=True で「修正可能だが実行していない」アクションの説明。"""


# ---------------------------------------------------------------------------
# SDK 抽象化
# ---------------------------------------------------------------------------

# `sdk_client` の duck-typed インターフェース:
#   - `await client.get_session_metadata(sid) -> Optional[Any]`
#   - `await client.list_sessions() -> List[Any]`（オプション、orphan GC で使用）
#   - `await client.delete_session(sid) -> None`（オプション、GC 実行時のみ）
#
# Phase 0 調査で Copilot SDK の `CopilotClient` がこれらを提供することを確認済み。


# ---------------------------------------------------------------------------
# reconcile_run
# ---------------------------------------------------------------------------

async def reconcile_run(
    state: RunState,
    *,
    sdk_client: Any = None,
    dry_run: bool = True,
    sdk_list_sessions: Optional[Callable[[], Awaitable[List[Any]]]] = None,
) -> ReconcileResult:
    """1 Run の reconcile を実行する。

    Args:
        state: 対象 RunState。
        sdk_client: `get_session_metadata` を提供するオブジェクト。None なら sdk 側
            は確認せず、state.json 内の sid を全て `sessions_both` 扱いとする
            （SDK 未接続時の degraded mode）。
        dry_run: True なら実際の state.json 修正は行わず、`actions_pending` にのみ記録。
        sdk_list_sessions: orphan 検出用の SDK セッション一覧取得関数。None なら
            sdk_only の検出はスキップ（reconcile_all / gc_orphans で別途使う）。

    Returns:
        ReconcileResult。
    """
    result = ReconcileResult(run_id=state.run_id)

    # state.json 内の sid を収集
    state_sids: Dict[str, str] = {}  # sid -> step_id
    for step_id, st in state.step_states.items():
        if st.session_id:
            state_sids[st.session_id] = step_id

    # SDK 側で各 sid の存在確認
    if sdk_client is not None:
        for sid, step_id in state_sids.items():
            try:
                meta = await sdk_client.get_session_metadata(sid)
            except Exception as exc:  # pragma: no cover - SDK 例外型不定
                # Critical #2: 例外時は sessions_unknown に分類（both と区別）
                result.actions_pending.append(
                    f"step={step_id} sid={sid}: SDK 確認失敗 ({type(exc).__name__})"
                )
                result.sessions_unknown.append(sid)
                continue
            if meta is None:
                result.sessions_state_only.append(sid)
                action = (f"step={step_id}: sid={sid} を pending に戻す "
                          f"(SDK 側で消失)")
                if dry_run:
                    result.actions_pending.append(action)
                else:
                    # state を pending + session_id=None に戻す。
                    # update_step は内部で state.save() を呼ぶが、save 失敗時に
                    # OSError が伝播するとメモリ上は変更済み・ディスクは未変更
                    # という不整合になるため、変更前の値をスナップショットして
                    # OSError 時にロールバックする。
                    st = state.step_states.get(step_id)
                    original: Optional[tuple] = None
                    if st is not None:
                        original = (st.status, st.session_id, st.sdk_session_exists)
                    try:
                        state.update_step(step_id, status="pending", session_id=None,
                                          sdk_session_exists=False)
                        result.actions_taken.append(action)
                    except OSError as exc:
                        if original is not None and st is not None:
                            st.status, st.session_id, st.sdk_session_exists = original
                        result.actions_pending.append(
                            f"step={step_id}: state.json save 失敗 "
                            f"(変更をロールバック: {exc})"
                        )
            else:
                result.sessions_both.append(sid)
                # Major #6: dry_run=True 時は state 変更に一切手をつけない
                if not dry_run:
                    st = state.step_states.get(step_id)
                    original_sse = st.sdk_session_exists if st is not None else None
                    try:
                        state.update_step(step_id, sdk_session_exists=True)
                    except OSError as exc:
                        if st is not None:
                            st.sdk_session_exists = original_sse
                        result.actions_pending.append(
                            f"step={step_id}: sdk_session_exists 更新の save 失敗 "
                            f"(変更をロールバック: {exc})"
                        )
    else:
        # SDK 未接続: state 内 sid は確認できないので unknown 扱いにする
        # （「整合」と誘誘するより「不明」として明示するのが安全）
        result.sessions_unknown.extend(state_sids.keys())
        if state_sids:
            result.actions_pending.append(
                "SDK 未接続のため完全な整合性チェックをスキップしました"
            )

    # sdk_only 検出（list_sessions が提供されている場合のみ）
    if sdk_list_sessions is not None:
        try:
            all_sessions = await sdk_list_sessions()
        except Exception:
            all_sessions = []
        all_sids = {getattr(s, "sessionId", None) or getattr(s, "session_id", None)
                    for s in all_sessions}
        all_sids.discard(None)
        for sid in all_sids:
            if sid in state_sids:
                continue
            # この run_id に属するべき sid のみ orphan として記録する
            # 形式: hve-<run_id>-step-<...>
            prefix = f"{DEFAULT_SESSION_ID_PREFIX}-{state.run_id}-step-"
            if sid.startswith(prefix):
                result.sessions_sdk_only.append(sid)

    # sdk_session_index に最終確認時刻を記録する。Major #6: dry_run=True のときは
    # state をメモリ上も一切変更しない。
    # save 失敗時は in-memory の sdk_session_index 変更もロールバックして
    # ディスクとメモリの整合を維持する。
    if not dry_run:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        index_originals: Dict[str, Optional[str]] = {}
        for sid in result.sessions_both:
            index_originals[sid] = state.sdk_session_index.get(sid)
            state.sdk_session_index[sid] = now
        if index_originals or result.actions_taken:
            # state.json を save（sdk_session_index 変更 or actions_taken があった場合）
            try:
                state.save()
            except OSError as exc:  # pragma: no cover
                # Rollback: ディスクは未更新なので in-memory も元に戻す
                for sid, orig in index_originals.items():
                    if orig is None:
                        state.sdk_session_index.pop(sid, None)
                    else:
                        state.sdk_session_index[sid] = orig
                result.actions_pending.append(
                    f"state.json save 失敗 (sdk_session_index 変更をロールバック: {exc})"
                )

    return result


# ---------------------------------------------------------------------------
# reconcile_all
# ---------------------------------------------------------------------------

async def reconcile_all(
    work_dir: Optional[Path] = None,
    *,
    sdk_client: Any = None,
    dry_run: bool = True,
) -> Dict[str, ReconcileResult]:
    """`<session-state-dir>/runs/` 配下の全 Run に対して reconcile を実行する。

    Critical #3 (v1.0.2): `sdk_client` が `list_sessions` を提供する場合、
    `sdk_list_sessions` を組み立てて `reconcile_run` に渡し、`sessions_sdk_only`
    の検出も行う。
    """
    wd = Path(work_dir) if work_dir else DEFAULT_RUNS_DIR
    runs = list_resumable_runs(wd)
    results: Dict[str, ReconcileResult] = {}

    # sdk_client から list_sessions を一度だけ呼んで結果を全 run で共有する
    cached_sessions: Optional[List[Any]] = None
    if sdk_client is not None and hasattr(sdk_client, "list_sessions"):
        try:
            cached_sessions = await sdk_client.list_sessions()
        except Exception:  # pragma: no cover
            cached_sessions = []

    async def _list_sessions_cached() -> List[Any]:
        return cached_sessions or []

    list_fn = _list_sessions_cached if cached_sessions is not None else None
    for state in runs:
        results[state.run_id] = await reconcile_run(
            state, sdk_client=sdk_client, dry_run=dry_run,
            sdk_list_sessions=list_fn,
        )
    return results


# ---------------------------------------------------------------------------
# gc_orphans
# ---------------------------------------------------------------------------

@dataclass
class GcResult:
    """orphan GC の実行結果。"""

    candidates: List[str] = field(default_factory=list)
    """削除候補と判定された hve-* prefix の session_id。"""
    deleted: List[str] = field(default_factory=list)
    """実際に削除に成功した session_id。"""
    failed: List[str] = field(default_factory=list)
    """削除失敗（reason 付き）。"""
    dry_run: bool = True


async def gc_orphans(
    work_dir: Optional[Path] = None,
    *,
    sdk_client: Any = None,
    dry_run: bool = True,
) -> GcResult:
    """SDK 側に残っているが state.json から参照されていない `hve-*` session を削除する。

    安全ガード:
    - `DEFAULT_SESSION_ID_PREFIX`（"hve"）で始まる session_id のみ対象。
    - state.json で参照中の sid は絶対に削除しない（reconcile_run の sessions_both と
      sessions_state_only を全 Run 分集約して exclusion set とする）。

    Args:
        work_dir: `<session-state-dir>/runs/` ルート。
        sdk_client: `list_sessions()` / `delete_session()` を提供。None なら何もしない。
        dry_run: True なら候補列挙のみ。False なら実削除。
    """
    result = GcResult(dry_run=dry_run)
    if sdk_client is None:
        return result

    wd = Path(work_dir) if work_dir else DEFAULT_RUNS_DIR
    runs = list_resumable_runs(wd)

    # 保護対象 sid（state.json で参照中）
    protected: Set[str] = set()
    for state in runs:
        for st in state.step_states.values():
            if st.session_id:
                protected.add(st.session_id)

    # SDK 側の全 hve-* セッション
    try:
        all_sessions = await sdk_client.list_sessions()
    except Exception as exc:
        result.failed.append(f"list_sessions 失敗: {type(exc).__name__}: {exc}")
        return result

    for s in all_sessions:
        sid = getattr(s, "sessionId", None) or getattr(s, "session_id", None)
        if not sid or not sid.startswith(DEFAULT_SESSION_ID_PREFIX + "-"):
            continue
        if sid in protected:
            continue
        result.candidates.append(sid)

    if dry_run:
        return result

    for sid in result.candidates:
        try:
            await sdk_client.delete_session(sid)
            result.deleted.append(sid)
        except Exception as exc:
            result.failed.append(f"{sid}: {type(exc).__name__}: {exc}")

    return result


__all__ = [
    "ReconcileResult",
    "GcResult",
    "reconcile_run",
    "reconcile_all",
    "gc_orphans",
]
