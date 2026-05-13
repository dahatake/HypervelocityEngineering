"""resume_cli.py — Phase 5 (Resume): セッション管理 CLI サブコマンド群。

`python -m hve resume {list,show,rename,delete,continue}` で再開可能セッションを
非対話的に管理する。各ハンドラーは `argparse.Namespace` を受け取り終了コードを返す。

== サブコマンド仕様 ==

list      — 一覧表示。未完了のみ表示。`--json` で JSON 出力。
show      — 1 セッションの詳細を表示。`--json` で JSON 出力。
rename    — `state.session_name` を更新。
delete    — `<session-state-dir>/runs/<run_id>/` を削除。`--hard` で SDK 側セッションも削除。
continue  — 非対話で resume 実行（`__main__._resume_selected_run` の対話部分を skip）。

== Git 管理ポリシー ==

`<session-state-dir>/runs/<run_id>/` 配下は `run_state.py` モジュール docstring と同様、
Git にコミットされるクロスデバイス共有メタデータである。`delete` サブコマンドは
ディレクトリツリーごと安全に削除する（hve が生成したものに限定）。

== 安全性ガード ==

- `delete --hard`: 削除対象 session_id は必ず `DEFAULT_SESSION_ID_PREFIX`（"hve"）
  で始まるものに限定する。誤って他用途のセッションを削除しないため。
- `delete`: ディレクトリ削除前に `state.json` の存在を確認し、想定外ディレクトリの
  削除を防ぐ。`--yes` で確認スキップ。
- 全コマンド: `run_id` は `_safe_run_id_component` でパス安全に正規化済み。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .run_state import (
        DEFAULT_RUNS_DIR,
        DEFAULT_SESSION_ID_PREFIX,
        RunState,
        StepState,
        _safe_run_id_component,
        list_resumable_runs,
        to_local_time_str,
    )
    from .run_lock import RunLock, RunLockError
    from .run_journal import (
        DEFAULT_ARCHIVE_DIRNAME,
        KIND_DELETE_HARD_DIR_REMOVED,
        RunJournal,
    )
except ImportError:  # flat-import (test) フォールバック
    from run_state import (  # type: ignore[no-redef]
        DEFAULT_RUNS_DIR,
        DEFAULT_SESSION_ID_PREFIX,
        RunState,
        StepState,
        _safe_run_id_component,
        list_resumable_runs,
        to_local_time_str,
    )
    from run_lock import RunLock, RunLockError  # type: ignore[no-redef]
    from run_journal import (  # type: ignore[no-redef]
        DEFAULT_ARCHIVE_DIRNAME,
        KIND_DELETE_HARD_DIR_REMOVED,
        RunJournal,
    )

# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _resolve_work_dir(args: argparse.Namespace) -> Path:
    """`--work-dir` 指定があればそれを優先、無ければ DEFAULT_RUNS_DIR。"""
    explicit = getattr(args, "work_dir", None)
    if explicit:
        return Path(explicit)
    return DEFAULT_RUNS_DIR


def _load_state_or_error(run_id: str, work_dir: Path) -> Optional[RunState]:
    """state.json を読み込む。失敗時は stderr に出力して None を返す。"""
    try:
        return RunState.load(run_id, work_dir=work_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: run_id='{run_id}' を読み込めません: {exc}", file=sys.stderr)
        return None
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"ERROR: state.json の読み込みに失敗しました (run_id='{run_id}'): {exc}",
            file=sys.stderr,
        )
        return None


def _state_summary_dict(state: RunState) -> Dict[str, Any]:
    """`list --json` / `show --json` 用の要約 dict を返す。"""
    return {
        "run_id": state.run_id,
        "session_name": state.session_name,
        "workflow_id": state.workflow_id,
        "status": state.status,
        "progress": {
            "completed": state.completed_count,
            "total": state.total_count or len(state.step_states),
        },
        "created_at": state.created_at,
        "last_updated_at": state.last_updated_at,
        "pause_reason": state.pause_reason,
    }


def _confirm(prompt: str, *, default: bool = False, assume_yes: bool = False) -> bool:
    """対話確認。`assume_yes` なら自動 True。EOF/中断は default を返す。"""
    if assume_yes:
        return True
    hint = "Y/n" if default else "y/N"
    try:
        ans = input(f"{prompt} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return default
    if not ans:
        return default
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# list サブコマンド
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    """`hve resume list` ハンドラー。

    未完了（status != completed）のみ表示し、`--json` で機械可読形式に切り替える。
    """
    work_dir = _resolve_work_dir(args)
    all_runs = list_resumable_runs(work_dir)
    runs = [r for r in all_runs if r.status != "completed"]

    as_json: bool = bool(getattr(args, "json", False))

    if as_json:
        payload = [_state_summary_dict(r) for r in runs]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not runs:
        if all_runs:
            print("未完了のセッションはありません（完了済みセッションは表示しません）。")
        else:
            print("保存されているセッションはありません。")
        return 0

    print(f"{'RUN_ID':<32} {'STATUS':<10} {'PROGRESS':<10} {'WORKFLOW':<12} {'UPDATED':<14} NAME")
    print("─" * 100)
    for r in runs:
        progress = f"{r.completed_count}/{r.total_count or len(r.step_states)}"
        updated = to_local_time_str(r.last_updated_at)
        name = (r.session_name or "(無名)")
        # name はターミナル幅を圧迫しないよう 40 文字までで切り詰める
        if len(name) > 40:
            name = name[:39] + "…"
        print(
            f"{r.run_id:<32} {r.status:<10} {progress:<10} "
            f"{r.workflow_id:<12} {updated:<14} {name}"
        )
    return 0


# ---------------------------------------------------------------------------
# show サブコマンド
# ---------------------------------------------------------------------------

def cmd_show(args: argparse.Namespace) -> int:
    """`hve resume show <run_id>` ハンドラー。

    1 セッションの詳細（メタ + ステップごとの状態）を表示する。
    """
    work_dir = _resolve_work_dir(args)
    run_id: str = args.run_id
    state = _load_state_or_error(run_id, work_dir)
    if state is None:
        return 1

    as_json: bool = bool(getattr(args, "json", False))
    if as_json:
        # ステップ状態を含む全体を出力（_work_dir は除外）
        full = state.to_dict()
        print(json.dumps(full, ensure_ascii=False, indent=2))
        return 0

    progress = f"{state.completed_count}/{state.total_count or len(state.step_states)}"
    print(f"Run ID         : {state.run_id}")
    print(f"セッション名    : {state.session_name or '(無名)'}")
    print(f"ワークフロー    : {state.workflow_id}")
    print(f"ステータス      : {state.status}")
    print(f"進捗            : {progress} ステップ完了")
    print(f"作成日時        : {to_local_time_str(state.created_at)}")
    print(f"最終更新        : {to_local_time_str(state.last_updated_at)}")
    print(f"中断理由        : {state.pause_reason or '(不明)'}")
    print(f"SDK バージョン  : {state.host.copilot_sdk_version or '(不明)'}")
    snap_model = state.config_snapshot.get("model") if state.config_snapshot else None
    print(f"モデル          : {snap_model or '(snapshot に無し)'}")

    if state.step_states:
        print()
        print(f"{'STEP_ID':<24} {'STATUS':<10} {'ELAPSED':<10} SESSION_ID")
        print("─" * 90)
        for sid in state.selected_step_ids or list(state.step_states.keys()):
            st = state.step_states.get(sid)
            if st is None:
                continue
            elapsed = f"{st.elapsed_seconds:.2f}s" if st.elapsed_seconds else "-"
            sess = st.session_id or "-"
            print(f"{sid:<24} {st.status:<10} {elapsed:<10} {sess}")
            if st.error_summary:
                print(f"  └─ error: {st.error_summary}")

    print()
    print("注: SDK 側セッション (~/.copilot/session-state/<sid>/) はデバイス毎に保持され、")
    print("    Git では同期されません。別デバイスで resume すると当該ステップは新規")
    print("    セッション (フォーク) として再実行されます。")
    return 0


# ---------------------------------------------------------------------------
# rename サブコマンド
# ---------------------------------------------------------------------------

def cmd_rename(args: argparse.Namespace) -> int:
    """`hve resume rename <run_id> <new_name>` ハンドラー。"""
    work_dir = _resolve_work_dir(args)
    run_id: str = args.run_id
    new_name: str = args.new_name.strip()
    if not new_name:
        print("ERROR: 新しいセッション名は空にできません。", file=sys.stderr)
        return 1

    state = _load_state_or_error(run_id, work_dir)
    if state is None:
        return 1

    old_name = state.session_name or "(無名)"
    state.session_name = new_name
    try:
        state.save()
    except OSError as exc:
        print(f"ERROR: state.json の保存に失敗しました: {exc}", file=sys.stderr)
        return 1

    print(f"OK: セッション名を変更しました")
    print(f"  Run ID  : {state.run_id}")
    print(f"  旧名    : {old_name}")
    print(f"  新名    : {new_name}")
    return 0


# ---------------------------------------------------------------------------
# delete サブコマンド
# ---------------------------------------------------------------------------

async def _hard_delete_sdk_sessions(
    state: RunState,
    *,
    journal: Optional["RunJournal"] = None,
    journal_seq: Optional[int] = None,
) -> List[str]:
    """state に含まれる SDK セッション ID を全て delete_session する。

    DEFAULT_SESSION_ID_PREFIX で始まる ID のみ削除対象とし、誤って他用途の
    セッションを消さない。Phase 4 では `get_session_metadata` で存在確認してから
    `delete_session` を呼ぶ idempotent パターンに変更。

    Args:
        state: 削除対象の RunState。
        journal: 進捗を記録する RunJournal（Phase 4）。None なら記録しない。
        journal_seq: journal の対象 seq。journal 非 None なら必須。

    Returns:
        削除に失敗した session_id（失敗理由付き）のリスト。
    """
    try:
        from copilot import CopilotClient, SubprocessConfig  # type: ignore[import]
    except ImportError:
        # SDK 未インストール環境では SDK 側削除はスキップする
        return [
            f"{st.session_id}: copilot SDK 未インストールのため削除できません"
            for st in state.step_states.values()
            if st.session_id and st.session_id.startswith(DEFAULT_SESSION_ID_PREFIX)
        ]

    try:
        from .config import SDKConfig
        from .run_journal import (
            KIND_DELETE_HARD_SDK_DELETED,
            KIND_DELETE_HARD_SDK_FAILED,
        )
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]
        from run_journal import (  # type: ignore[no-redef]
            KIND_DELETE_HARD_SDK_DELETED,
            KIND_DELETE_HARD_SDK_FAILED,
        )

    cfg = SDKConfig.from_env()
    sdk_config = SubprocessConfig(
        cli_path=cfg.cli_path,
        github_token=cfg.resolve_token() or None,
        log_level="error",
    )
    client = CopilotClient(config=sdk_config)
    failed: List[str] = []
    try:
        await client.start()
        for st in state.step_states.values():
            sid = st.session_id
            if not sid:
                continue
            # 安全性ガード: hve prefix の ID のみ削除
            if not sid.startswith(DEFAULT_SESSION_ID_PREFIX):
                failed.append(f"{sid}: prefix が '{DEFAULT_SESSION_ID_PREFIX}' で始まらないためスキップ")
                continue
            try:
                # Phase 4: idempotent パターン (Phase 0 調査結果に基づく)
                # `get_session_metadata(sid)` が None を返せばセッション不在 → 削除済み扱い
                meta = await client.get_session_metadata(sid)
                if meta is None:
                    if journal is not None and journal_seq is not None:
                        journal.step(journal_seq, kind=KIND_DELETE_HARD_SDK_DELETED,
                                     target=sid, payload={"note": "already-absent"})
                    continue
                await client.delete_session(sid)
                if journal is not None and journal_seq is not None:
                    journal.step(journal_seq, kind=KIND_DELETE_HARD_SDK_DELETED, target=sid)
            except Exception as exc:  # SDK が定義する例外型は変動するため広く捕捉
                failed.append(f"{sid}: {type(exc).__name__}: {exc}")
                if journal is not None and journal_seq is not None:
                    journal.step(journal_seq, kind=KIND_DELETE_HARD_SDK_FAILED, target=sid,
                                 payload={"error": f"{type(exc).__name__}: {exc}"})
    finally:
        try:
            await client.stop()
        except Exception:  # pragma: no cover - cleanup ベストエフォート
            pass
    return failed


def _safe_remove_run_dir(state: RunState, work_dir: Path) -> None:
    """`work_dir/<run_id>/` を安全に削除する。

    state.json の存在を確認し、想定外のディレクトリ（手作業で作られたフォルダ等）
    を誤削除しない。
    """
    safe_id = _safe_run_id_component(state.run_id)
    target = work_dir / safe_id
    if not target.exists():
        return
    state_file = target / "state.json"
    if not state_file.exists():
        # state.json が無いディレクトリは hve 管理外と判断し触らない
        raise RuntimeError(
            f"安全性ガード: '{target}' に state.json が存在しないため削除しません。"
            " 手作業で削除してください。"
        )
    shutil.rmtree(target)


def cmd_delete(args: argparse.Namespace) -> int:
    """`hve resume delete <run_id>` ハンドラー。

    Phase 4 (Resume 2-layer txn): `RunLock` で排他制御し、`RunJournal` に
    Write-Ahead Intent Log として `delete-hard.begin → step* → end` を記録する。
    途中クラッシュ時は次回起動時の `recover_pending_on_startup` で完遂される。

    `--hard` 指定時は SDK 側の `~/.copilot/session-state/<sid>/` も
    `client.delete_session()` 経由で削除する（idempotent: get_session_metadata で
    存在確認してから削除）。`--yes` で確認をスキップ。
    """
    work_dir = _resolve_work_dir(args)
    run_id: str = args.run_id
    is_hard: bool = bool(getattr(args, "hard", False))
    assume_yes: bool = bool(getattr(args, "yes", False))

    state = _load_state_or_error(run_id, work_dir)
    if state is None:
        return 1

    print(f"削除対象:")
    print(f"  Run ID       : {state.run_id}")
    print(f"  セッション名 : {state.session_name or '(無名)'}")
    print(f"  ワークフロー : {state.workflow_id}")
    print(f"  ステータス   : {state.status}")
    sdk_session_ids = [
        st.session_id for st in state.step_states.values()
        if st.session_id and st.session_id.startswith(DEFAULT_SESSION_ID_PREFIX)
    ]
    if is_hard:
        print(f"  --hard 指定により SDK 側セッション {len(sdk_session_ids)} 件も削除します")

    if not _confirm("本当に削除しますか？", default=False, assume_yes=assume_yes):
        print("キャンセルしました。")
        return 0

    # Phase 4: RunLock + RunJournal による crash-safe delete
    archive_dir = work_dir.parent / DEFAULT_ARCHIVE_DIRNAME
    try:
        lock = RunLock(state.run_id, work_dir)
        lock.acquire()
    except RunLockError as exc:
        print(f"ERROR: ロック取得失敗（他プロセス使用中の可能性）: {exc}", file=sys.stderr)
        if exc.held_by:
            print(f"  保持者: pid={exc.held_by.get('pid')} "
                  f"hostname={exc.held_by.get('hostname_hash')} "
                  f"heartbeat={exc.held_by.get('heartbeat_at')}", file=sys.stderr)
        return 1

    journal = RunJournal(work_dir / _safe_run_id_component(state.run_id))
    seq = journal.begin(
        kind="delete-hard",
        target=state.run_id,
        payload={"session_ids": sdk_session_ids, "is_hard": is_hard},
    )

    try:
        # SDK 側削除（--hard 時のみ）
        if is_hard:
            try:
                failed = asyncio.run(_hard_delete_sdk_sessions(
                    state, journal=journal, journal_seq=seq,
                ))
            except Exception as exc:  # pragma: no cover - asyncio 異常系
                print(f"WARN: SDK 側セッション削除中に例外: {exc}", file=sys.stderr)
                failed = []
            for line in failed:
                print(f"WARN: SDK 削除失敗: {line}", file=sys.stderr)

        # state.json 存在ガード（rmtree 前）
        run_dir_path = work_dir / _safe_run_id_component(state.run_id)
        if run_dir_path.exists() and not (run_dir_path / "state.json").exists():
            print(
                f"ERROR: 安全性ガード: '{run_dir_path}' に state.json が存在しないため削除しません。",
                file=sys.stderr,
            )
            return 1

        # Critical #1 (v1.0.2): journal を archive へ移動してから end を書く。
        # この順序により、end 書き込み後 / rmtree 前にクラッシュしても、
        # archive 内に begin + end が揃った journal が残るため recovery で no-op として扱える。
        # archive 移動 → end → rmtree の順なら、end 失敗時も archive 内に begin だけが
        # 残るため次回起動時の recovery で完遂可能。
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_path = journal.archive(archive_dir)
        if archived_path is not None:
            # archive 済みファイルに end を直接追記する
            _append_to_archive(archived_path, {
                "seq": seq,
                "ts": datetime_utc_now_iso(),
                "kind": "delete-hard.end",
                "target": state.run_id,
                "payload": {},
            })
    finally:
        # lock を release してから rmtree（Windows 互換）。
        # ロック解放後 rmtree までの間に他プロセスがロックを取れるが、
        # state.json 存在ガードによりすぐ撤退できるため実害なし。
        try:
            lock.release()
        except Exception:  # pragma: no cover
            pass

    # <session-state-dir>/runs/<run_id>/ 削除（.lock もここで消える。journal は既に archive 済み）
    try:
        if run_dir_path.exists():
            shutil.rmtree(run_dir_path)
    except OSError as exc:
        print(f"ERROR: ディレクトリ削除に失敗: {exc}", file=sys.stderr)
        return 1

    print(f"OK: 削除しました (run_id={state.run_id})")
    return 0


def _append_to_archive(archive_path: Path, record: Dict[str, Any]) -> None:
    """archive 済み journal ファイルへ末尾 1 行追加（O_APPEND で原子的書き込み）。"""
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(archive_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        try:
            os.fsync(fd)
        except OSError:  # pragma: no cover
            pass
    finally:
        os.close(fd)


def datetime_utc_now_iso() -> str:
    """ISO 8601 UTC 文字列を返す（cmd_delete 内のみで使用）。"""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# continue サブコマンド
# ---------------------------------------------------------------------------

def cmd_continue(args: argparse.Namespace) -> int:
    """`hve resume continue <run_id>` ハンドラー。

    非対話的に Resume を実行する。Wizard の `_resume_selected_run` から
    panel/確認プロンプトを除いた経路で `run_workflow(resume_state=...)` を呼ぶ。

    SDK バージョン差異を検出した場合は warning を表示するが処理は続行する。
    `--abort-on-sdk-mismatch` 指定時は終了コード 1 で中断する。
    """
    work_dir = _resolve_work_dir(args)
    run_id: str = args.run_id

    state = _load_state_or_error(run_id, work_dir)
    if state is None:
        return 1

    try:
        from .config import SDKConfig
        from .orchestrator import run_workflow
        from .run_state import get_current_sdk_version
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]
        from orchestrator import run_workflow  # type: ignore[no-redef]
        from run_state import get_current_sdk_version  # type: ignore[no-redef]

    # SDK バージョン差異警告
    current_sdk = get_current_sdk_version()
    saved_sdk = state.host.copilot_sdk_version or "(不明)"
    if current_sdk != saved_sdk and saved_sdk != "(不明)":
        msg = (
            f"WARN: SDK バージョン差異を検出: 保存時 {saved_sdk} → 現在 {current_sdk}\n"
            "  セッション形式の互換性が保証されない可能性があります。"
        )
        print(msg, file=sys.stderr)
        if bool(getattr(args, "abort_on_sdk_mismatch", False)):
            print("ERROR: --abort-on-sdk-mismatch により中断します。", file=sys.stderr)
            return 1

    # 環境変数チェック (PR/Issue 作成が有効だった場合)
    snap = state.config_snapshot or {}
    if snap.get("create_pr") or snap.get("create_issues"):
        if not os.environ.get("REPO"):
            print("ERROR: REPO 環境変数が設定されていません。Resume できません。", file=sys.stderr)
            return 1
        if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
            print(
                "ERROR: GH_TOKEN（または GITHUB_TOKEN）環境変数が設定されていません。",
                file=sys.stderr,
            )
            return 1

    cfg = SDKConfig.from_env()

    print(f"↻ Resume: Run ID {state.run_id} ({state.workflow_id}) を再開します...")
    try:
        result = asyncio.run(
            run_workflow(
                workflow_id=state.workflow_id,
                params=None,  # snapshot から復元
                config=cfg,
                resume_state=state,
            )
        )
    except KeyboardInterrupt:
        print(
            "\n中断されました（再度 hve resume continue を実行すると続きから再開できます）。",
            file=sys.stderr,
        )
        return 1

    # 結果判定
    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1
    if result.get("code_review_error"):
        print(f"ERROR: Code Review Agent: {result['code_review_error']}", file=sys.stderr)
        return 1
    if result.get("failed"):
        return 1
    print("OK: Resume 完了")
    return 0


# ---------------------------------------------------------------------------
# argparse パーサー定義 / dispatcher
# ---------------------------------------------------------------------------

def add_resume_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """`__main__._build_parser` から呼ばれる resume サブパーサー登録。

    Returns:
        登録された resume parser（呼び出し側で属性を追加する場合に使う）。
    """
    resume_parser = subparsers.add_parser(
        "resume",
        help="再開可能なセッションを管理する (list/show/rename/delete/continue)",
    )
    # 共通オプション
    resume_parser.add_argument(
        "--work-dir",
        default=None,
        metavar="PATH",
        help=f"runs ディレクトリのパス (デフォルト: {DEFAULT_RUNS_DIR})",
    )

    resume_sub = resume_parser.add_subparsers(dest="resume_command")

    # list
    p_list = resume_sub.add_parser("list", help="セッション一覧を表示する")
    p_list.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON 形式で出力する",
    )

    # show
    p_show = resume_sub.add_parser("show", help="1 セッションの詳細を表示する")
    p_show.add_argument("run_id", help="表示する Run ID")
    p_show.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON 形式で出力する",
    )

    # rename
    p_rename = resume_sub.add_parser("rename", help="セッション名を変更する")
    p_rename.add_argument("run_id", help="対象 Run ID")
    p_rename.add_argument("new_name", help="新しいセッション名")

    # delete
    p_delete = resume_sub.add_parser("delete", help="セッションを削除する")
    p_delete.add_argument("run_id", help="削除する Run ID")
    p_delete.add_argument(
        "--hard",
        action="store_true",
        default=False,
        help="SDK 側セッション (~/.copilot/session-state/) も削除する",
    )
    p_delete.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="確認プロンプトをスキップする",
    )

    # continue
    p_cont = resume_sub.add_parser("continue", help="非対話で Resume 実行する")
    p_cont.add_argument("run_id", help="再開する Run ID")
    p_cont.add_argument(
        "--abort-on-sdk-mismatch",
        action="store_true",
        default=False,
        help="SDK バージョン差異を検出したら中断する (デフォルトは警告のみで続行)",
    )

    # Phase 5: reconcile
    p_rec = resume_sub.add_parser(
        "reconcile",
        help="state.json と SDK セッション実体の整合性をチェックする (Phase 5)",
    )
    p_rec.add_argument(
        "run_id", nargs="?", default=None,
        help="対象 Run ID（省略 + --all なら全 Run）",
    )
    p_rec.add_argument(
        "--all", action="store_true", default=False,
        help="<session-state-dir>/runs/ 配下の全 Run を対象にする",
    )
    p_rec.add_argument(
        "--dry-run", action="store_true", default=True,
        help="既定。実際の state.json 修正は行わず候補のみ表示",
    )
    p_rec.add_argument(
        "--auto-fix", dest="dry_run", action="store_false",
        help="state_only 検出時に state を pending に戻す",
    )
    p_rec.add_argument(
        "--json", action="store_true", default=False,
        help="JSON 形式で出力する",
    )

    # Phase 5: gc-orphans
    p_gc = resume_sub.add_parser(
        "gc-orphans",
        help="hve-* prefix の orphan SDK セッションを削除する (Phase 5)",
    )
    p_gc.add_argument(
        "--dry-run", action="store_true", default=True,
        help="既定。削除候補のみ表示",
    )
    p_gc.add_argument(
        "--yes", "-y", dest="dry_run", action="store_false",
        help="実削除を行う（確認なし）",
    )
    p_gc.add_argument(
        "--json", action="store_true", default=False,
        help="JSON 形式で出力する",
    )

    return resume_parser


def dispatch(args: argparse.Namespace) -> int:
    """`hve resume <subcommand>` のディスパッチャ。

    `__main__.main` から `args.command == "resume"` の場合に呼ばれる。
    """
    sub = getattr(args, "resume_command", None)
    if sub == "list":
        return cmd_list(args)
    if sub == "show":
        return cmd_show(args)
    if sub == "rename":
        return cmd_rename(args)
    if sub == "delete":
        return cmd_delete(args)
    if sub == "continue":
        return cmd_continue(args)
    if sub == "reconcile":
        return cmd_reconcile(args)
    if sub == "gc-orphans":
        return cmd_gc_orphans(args)
    # サブコマンド未指定 → 簡易ヘルプ
    print(
        "使い方: python -m hve resume {list|show|rename|delete|continue|reconcile|gc-orphans} [...]\n"
        "  list        — セッション一覧 (--json)\n"
        "  show        — 1 セッションの詳細 (--json)\n"
        "  rename      — セッション名変更\n"
        "  delete      — セッション削除 (--hard で SDK 側も / --yes で確認スキップ)\n"
        "  continue    — 非対話 Resume 実行 (--abort-on-sdk-mismatch)\n"
        "  reconcile   — state.json と SDK セッション実体の整合性チェック\n"
        "  gc-orphans  — hve-* prefix の orphan SDK セッションを削除",
        file=sys.stderr,
    )
    return 1


# ---------------------------------------------------------------------------
# reconcile / gc-orphans サブコマンド (Phase 5)
# ---------------------------------------------------------------------------

async def _build_sdk_client_for_reconcile() -> Any:
    """SDK の CopilotClient を構築して start する。失敗時は None を返す。"""
    try:
        from copilot import CopilotClient, SubprocessConfig  # type: ignore[import]
    except ImportError:
        return None
    try:
        from .config import SDKConfig
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]
    cfg = SDKConfig.from_env()
    sdk_config = SubprocessConfig(
        cli_path=cfg.cli_path,
        github_token=cfg.resolve_token() or None,
        log_level="error",
    )
    client = CopilotClient(config=sdk_config)
    await client.start()
    return client


def cmd_reconcile(args: argparse.Namespace) -> int:
    """`hve resume reconcile [run_id] [--all] [--auto-fix]` ハンドラー。"""
    try:
        from .reconciler import reconcile_all, reconcile_run
        from .run_state import RunState
    except ImportError:
        from reconciler import reconcile_all, reconcile_run  # type: ignore[no-redef]
        from run_state import RunState  # type: ignore[no-redef]

    work_dir = _resolve_work_dir(args)
    run_id = getattr(args, "run_id", None)
    is_all = bool(getattr(args, "all", False))
    dry_run = bool(getattr(args, "dry_run", True))
    as_json = bool(getattr(args, "json", False))

    if not run_id and not is_all:
        print("ERROR: run_id または --all を指定してください", file=sys.stderr)
        return 1

    async def _main() -> Dict[str, Any]:
        client = await _build_sdk_client_for_reconcile()

        async def _list_sessions():
            return await client.list_sessions()

        try:
            if is_all:
                results = await reconcile_all(
                    work_dir, sdk_client=client, dry_run=dry_run
                )
            else:
                state = RunState.load(run_id, work_dir=work_dir)
                results = {state.run_id: await reconcile_run(
                    state, sdk_client=client, dry_run=dry_run,
                    sdk_list_sessions=_list_sessions if client else None,
                )}
        finally:
            if client is not None:
                try:
                    await client.stop()
                except Exception:  # pragma: no cover
                    pass

        out: Dict[str, Any] = {}
        for rid, r in results.items():
            out[rid] = {
                "sessions_state_only": r.sessions_state_only,
                "sessions_sdk_only": r.sessions_sdk_only,
                "sessions_both": r.sessions_both,
                "actions_taken": r.actions_taken,
                "actions_pending": r.actions_pending,
            }
        return out

    try:
        results = asyncio.run(_main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: reconcile 実行中に例外: {exc}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    for rid, r in results.items():
        print(f"Run ID: {rid}")
        print(f"  状態整合 (both)        : {len(r['sessions_both'])}")
        print(f"  state のみ (SDK 消失)  : {len(r['sessions_state_only'])}")
        print(f"  SDK のみ (orphan 候補) : {len(r['sessions_sdk_only'])}")
        for sid in r['sessions_state_only']:
            print(f"    [state-only] {sid}")
        for sid in r['sessions_sdk_only']:
            print(f"    [sdk-only]   {sid}")
        if r['actions_taken']:
            print(f"  実行アクション:")
            for a in r['actions_taken']:
                print(f"    - {a}")
        if r['actions_pending']:
            print(f"  保留アクション (--auto-fix で実行可):")
            for a in r['actions_pending']:
                print(f"    - {a}")
    return 0


def cmd_gc_orphans(args: argparse.Namespace) -> int:
    """`hve resume gc-orphans [--yes]` ハンドラー。"""
    try:
        from .reconciler import gc_orphans
    except ImportError:
        from reconciler import gc_orphans  # type: ignore[no-redef]

    work_dir = _resolve_work_dir(args)
    dry_run = bool(getattr(args, "dry_run", True))
    as_json = bool(getattr(args, "json", False))

    async def _main():
        client = await _build_sdk_client_for_reconcile()
        if client is None:
            return None
        try:
            return await gc_orphans(work_dir, sdk_client=client, dry_run=dry_run)
        finally:
            try:
                await client.stop()
            except Exception:  # pragma: no cover
                pass

    try:
        result = asyncio.run(_main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: gc-orphans 実行中に例外: {exc}", file=sys.stderr)
        return 1

    if result is None:
        print("ERROR: Copilot SDK が利用できません", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps({
            "candidates": result.candidates,
            "deleted": result.deleted,
            "failed": result.failed,
            "dry_run": result.dry_run,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"削除候補: {len(result.candidates)} 件")
    for sid in result.candidates:
        print(f"  - {sid}")
    if dry_run:
        print("（--yes を付けると実削除します）")
    else:
        print(f"削除成功: {len(result.deleted)} 件")
        if result.failed:
            print(f"削除失敗: {len(result.failed)} 件")
            for f in result.failed:
                print(f"  - {f}", file=sys.stderr)
    return 0
