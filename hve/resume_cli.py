"""resume_cli.py — Phase 5 (Resume): セッション管理 CLI サブコマンド群。

`python -m hve resume {list,show,rename,delete,continue}` で再開可能セッションを
非対話的に管理する。各ハンドラーは `argparse.Namespace` を受け取り終了コードを返す。

== サブコマンド仕様 ==

list      — 一覧表示。未完了のみ表示。`--json` で JSON 出力。
show      — 1 セッションの詳細を表示。`--json` で JSON 出力。
rename    — `state.session_name` を更新。
delete    — `work/runs/<run_id>/` を削除。`--hard` で SDK 側セッションも削除。
continue  — 非対話で resume 実行（`__main__._resume_selected_run` の対話部分を skip）。

== work-artifacts-layout §4.1 との関係 ==

`work/runs/<run_id>/` 配下は `run_state.py` モジュール docstring と同様、Git にコミット
されない実行時メタデータであり §4.1 の delete→create ルールの対象外。`delete` サブ
コマンドはディレクトリツリーごと安全に削除する（hve が生成したものに限定）。

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

async def _hard_delete_sdk_sessions(state: RunState) -> List[str]:
    """state に含まれる SDK セッション ID を全て delete_session する。

    DEFAULT_SESSION_ID_PREFIX で始まる ID のみ削除対象とし、誤って他用途の
    セッションを消さない。

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
    except ImportError:
        from config import SDKConfig  # type: ignore[no-redef]

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
                await client.delete_session(sid)
            except Exception as exc:  # SDK が定義する例外型は変動するため広く捕捉
                failed.append(f"{sid}: {type(exc).__name__}: {exc}")
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

    `--hard` 指定時は SDK 側の `~/.copilot/session-state/<sid>/` も
    `client.delete_session()` 経由で削除する。`--yes` で確認をスキップ。
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
    sdk_count = sum(
        1 for st in state.step_states.values()
        if st.session_id and st.session_id.startswith(DEFAULT_SESSION_ID_PREFIX)
    )
    if is_hard:
        print(f"  --hard 指定により SDK 側セッション {sdk_count} 件も削除します")

    if not _confirm("本当に削除しますか？", default=False, assume_yes=assume_yes):
        print("キャンセルしました。")
        return 0

    # SDK 側削除（--hard 時のみ）
    if is_hard:
        try:
            failed = asyncio.run(_hard_delete_sdk_sessions(state))
        except Exception as exc:  # pragma: no cover - asyncio 異常系
            print(f"WARN: SDK 側セッション削除中に例外: {exc}", file=sys.stderr)
            failed = []
        for line in failed:
            print(f"WARN: SDK 削除失敗: {line}", file=sys.stderr)

    # work/runs/<run_id>/ 削除
    try:
        _safe_remove_run_dir(state, work_dir)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: ディレクトリ削除に失敗: {exc}", file=sys.stderr)
        return 1

    print(f"OK: 削除しました (run_id={state.run_id})")
    return 0


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
    # サブコマンド未指定 → 簡易ヘルプ
    print(
        "使い方: python -m hve resume {list|show|rename|delete|continue} [...]\n"
        "  list      — セッション一覧 (--json)\n"
        "  show      — 1 セッションの詳細 (--json)\n"
        "  rename    — セッション名変更\n"
        "  delete    — セッション削除 (--hard で SDK 側も / --yes で確認スキップ)\n"
        "  continue  — 非対話 Resume 実行 (--abort-on-sdk-mismatch)",
        file=sys.stderr,
    )
    return 1
