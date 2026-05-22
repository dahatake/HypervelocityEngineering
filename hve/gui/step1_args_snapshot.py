"""hve.gui.step1_args_snapshot — Step 1 事前チェック完了時の args/パラメータ保存。

Issue: gui Step 1 のすべての事前チェック完了後に、タスク実行用の全 args/
パラメーターを ``work/gui-runs/<session_run_id>/step1-precheck/`` 配下に
JSON スナップショットとして保存する。

設計方針:
  - 失敗は GUI 主処理を止めない（全例外を握り潰し WARNING ログのみ）。
  - 機密情報は本モジュール内蔵のホワイトリストでマスクする
    （``*_token`` / ``*_secret`` / ``*_key`` / ``*-token`` / ``*-secret`` /
    ``*-key`` を含むキー名／argv フラグ名は ``***`` に置換）。
  - 反復ごとに ``<timestamp>__iter<n>/`` を新規作成（既存ディレクトリは
    削除→新規作成、`work-artifacts-layout` Skill §4.1 準拠）。
  - 最終承認時は ``latest-accepted/`` へコピー。
  - JSON のみ（YAML/TOML は出力しない）。

公開 API:
  - :func:`save_step1_snapshot`
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

logger = logging.getLogger(__name__)

__all__ = ["save_step1_snapshot"]


# --- マスキング ---------------------------------------------------------------

_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|bearer|credential)",
    re.IGNORECASE,
)
_MASK = "***"


def _is_secret_key(name: str) -> bool:
    if not name:
        return False
    return bool(_SECRET_KEY_RE.search(name))


def _mask_value(key: str, value: Any) -> Any:
    if _is_secret_key(key) and value not in (None, "", [], {}):
        return _MASK
    return value


def _mask_mapping(d: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, Mapping):
            out[k] = _mask_mapping(v)
        elif isinstance(v, list):
            out[k] = [_mask_mapping(x) if isinstance(x, Mapping) else x for x in v]
        else:
            out[k] = _mask_value(k, v)
    return out


def _mask_argv(argv: List[str]) -> List[str]:
    """argv 内の ``--*-token VALUE`` / ``--*-token=VALUE`` をマスク。"""
    masked: List[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and "=" in tok:
            name, _, val = tok.partition("=")
            flag = name.lstrip("-")
            if _is_secret_key(flag):
                masked.append(f"{name}={_MASK}")
            else:
                masked.append(tok)
            i += 1
            continue
        if tok.startswith("--"):
            flag = tok.lstrip("-")
            masked.append(tok)
            if _is_secret_key(flag) and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                masked.append(_MASK)
                i += 2
                continue
        else:
            masked.append(tok)
        i += 1
    return masked


# --- シリアライズ -------------------------------------------------------------


def _to_jsonable(obj: Any) -> Any:
    """``Path`` / dataclass / set 等を JSON 直列化可能な型へ変換。"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if dataclasses.is_dataclass(obj):
        return _to_jsonable(dataclasses.asdict(obj))
    # Enum / その他
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


# --- 公開 API -----------------------------------------------------------------


def save_step1_snapshot(
    *,
    work_root: Path,
    session_run_id: str,
    iteration: int,
    is_final_accepted: bool,
    wf_ids: Iterable[str],
    page_options: Any,
    repo_root: Path,
    autopilot_mode: bool = False,
    precheck_result: Any = None,
    plan_review: Any = None,
    additional_prompts: Optional[Mapping[str, str]] = None,
    extra_provided: Optional[Mapping[str, List[str]]] = None,
    attachment_paths: Optional[Iterable[str]] = None,
    auth_states: Any = None,
    env_overrides: Optional[Mapping[str, str]] = None,
) -> Optional[Path]:
    """Step 1 事前チェック完了時点のスナップショットを保存する。

    Args:
        work_root: ``GuiSessionWorkdir.work_root``。
        session_run_id: ``GuiSessionWorkdir.session_run_id``。
        iteration: precheck → plan review のループ回数（1 始まり）。
        is_final_accepted: ユーザーが「このプランで実行」を承認した最終時点なら True。
        wf_ids: 選択中の workflow ID 一覧。
        page_options: ``MainWindow._page_options``（``build_args_for_workflow`` を呼ぶ）。
        repo_root: リポジトリルート。
        autopilot_mode: Autopilot 経路かどうか。
        precheck_result: ``run_step1_precheck`` の戻り値（任意）。
        plan_review: ``build_step1_plan_review`` の戻り値（任意）。
        additional_prompts: workflow_id → 追加プロンプト。
        extra_provided: extra_provided_paths_by_workflow。
        attachment_paths: ARD 添付パス一覧。
        auth_states: provider → AuthState のマップ（任意、状態のみ記録）。
        env_overrides: 子プロセス注入 env（HVE_WORK_ROOT 等）。

    Returns:
        作成したスナップショットディレクトリの Path（失敗時 None）。
    """
    try:
        wf_ids_list = [str(w) for w in (wf_ids or [])]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_root = work_root / "step1-precheck" / f"{ts}__iter{iteration}"
        # 削除→新規作成（work-artifacts-layout §4.1）
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root, ignore_errors=True)
        snapshot_root.mkdir(parents=True, exist_ok=True)

        # 1) metadata.json
        _write_json(
            snapshot_root / "metadata.json",
            {
                "schema_version": 1,
                "session_run_id": session_run_id,
                "iteration": iteration,
                "is_final_accepted": bool(is_final_accepted),
                "autopilot_mode": bool(autopilot_mode),
                "timestamp_utc": ts,
                "work_root": str(work_root),
                "repo_root": str(repo_root),
                "workflow_ids": wf_ids_list,
            },
        )

        # 2) selection.json
        _write_json(
            snapshot_root / "selection.json",
            {
                "workflow_ids": wf_ids_list,
                "autopilot_mode": bool(autopilot_mode),
            },
        )

        # 3) orchestrate-args.json / orchestrate-argv.json (per workflow)
        args_map: Dict[str, Any] = {}
        argv_map: Dict[str, List[str]] = {}
        for wf in wf_ids_list:
            try:
                args = page_options.build_args_for_workflow(wf, repo_root=repo_root)
                args_dict = _to_jsonable(args)
                if isinstance(args_dict, Mapping):
                    args_dict = _mask_mapping(args_dict)
                args_map[wf] = args_dict
                try:
                    argv = list(args.to_argv())
                except Exception as exc_argv:
                    logger.warning(
                        "step1_args_snapshot: to_argv 失敗 wf=%s: %s", wf, exc_argv
                    )
                    argv = []
                argv_map[wf] = _mask_argv(argv)
            except Exception as exc_args:
                logger.warning(
                    "step1_args_snapshot: build_args_for_workflow 失敗 wf=%s: %s",
                    wf,
                    exc_args,
                )
                args_map[wf] = {"_error": str(exc_args)}
                argv_map[wf] = []
        _write_json(snapshot_root / "orchestrate-args.json", args_map)
        _write_json(snapshot_root / "orchestrate-argv.json", argv_map)

        # 4) precheck-result.json
        if precheck_result is not None:
            _write_json(
                snapshot_root / "precheck-result.json",
                _to_jsonable(precheck_result),
            )

        # 5) plan-review.json
        if plan_review is not None:
            _write_json(
                snapshot_root / "plan-review.json",
                _to_jsonable(plan_review),
            )

        # 6) attachments.json
        _write_json(
            snapshot_root / "attachments.json",
            {
                "additional_prompts": dict(additional_prompts or {}),
                "extra_provided": {
                    str(k): [str(p) for p in v]
                    for k, v in (extra_provided or {}).items()
                },
                "ard_attachment_paths": [str(p) for p in (attachment_paths or [])],
            },
        )

        # 7) auth-snapshot.json（状態名のみ、トークン等は含めない）
        if auth_states is not None:
            auth_dump: Dict[str, str] = {}
            try:
                for prov, state in dict(auth_states).items():
                    auth_dump[str(prov)] = getattr(state, "name", str(state))
            except Exception as exc_auth:
                auth_dump = {"_error": str(exc_auth)}
            _write_json(snapshot_root / "auth-snapshot.json", auth_dump)

        # 8) env-overrides.json
        _write_json(
            snapshot_root / "env-overrides.json",
            _mask_mapping(dict(env_overrides or {})),
        )

        # 9) latest-accepted/ コピー（最終承認時のみ）
        if is_final_accepted:
            try:
                latest = work_root / "step1-precheck" / "latest-accepted"
                if latest.exists():
                    shutil.rmtree(latest, ignore_errors=True)
                shutil.copytree(snapshot_root, latest)
            except Exception as exc_copy:
                logger.warning(
                    "step1_args_snapshot: latest-accepted コピー失敗: %s", exc_copy
                )

        logger.info(
            "step1_args_snapshot: 保存完了 path=%s iter=%d final=%s",
            snapshot_root,
            iteration,
            is_final_accepted,
        )
        return snapshot_root
    except Exception as exc:  # 防御的: GUI 主処理を止めない
        logger.warning("step1_args_snapshot: 保存失敗: %s", exc, exc_info=True)
        return None
