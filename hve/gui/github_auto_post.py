"""hve.gui.github_auto_post — 自動進捗 Post の結線コントローラ（FR-GUI-36）。

観測イベント（`[hve:stats]`）から Post 対象と進捗 snapshot を組み立て、
`GitHubProgressPoster` の rolling 契約に従って GitHub API 要求を返す。
GitHub API は呼ばず、PySide6 へも依存しない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from hve.gui.github_progress_format import FINAL_STATUSES, format_progress_comment
from hve.gui.github_progress_poster import GitHubProgressPoster, ProgressPostRequest

__all__ = ["AUTO_POST_TARGETS", "MAX_COMMENT_CHARS", "GitHubAutoPostController"]

# FR-GUI-36: 設定値は 4 値のみ。
AUTO_POST_TARGETS = ("off", "issue", "pr", "both")

# GitHub の comment 本文上限（文字数）。超過すると API が必ず失敗するため、
# 最終更新の console 末尾を削って先頭の進捗表を守る。
MAX_COMMENT_CHARS = 65_536

_TRUNCATION_NOTICE = "\n\n> 文字数上限のため末尾を省略しました。"

# Step の terminal 状態（FR-GUI-36 が定める更新契機）。
_STEP_TERMINAL_STATUSES = frozenset({"done", "failed", "skipped", "blocked"})

_KIND_BY_TARGET = {
    "issue": ("issue",),
    "pr": ("pr",),
    "both": ("issue", "pr"),
    "off": (),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncate_body(body: str) -> str:
    """GitHub の comment 上限を超えないよう末尾を削る。

    上限超過は API が必ず失敗するため、先頭の進捗表を優先して残す。
    """
    if len(body) <= MAX_COMMENT_CHARS:
        return body
    keep = MAX_COMMENT_CHARS - len(_TRUNCATION_NOTICE)
    return body[:keep] + _TRUNCATION_NOTICE


class GitHubAutoPostController:
    """観測イベントを rolling 進捗コメントへ変換する。

    - `target_mode` が `off` の間は request を 1 件も生成しない。
    - 更新契機は run 開始、Step の terminal 状態、Workflow 終了だけとする。
    - 新規 PR は post-DAG でしか確定しないため、PR への Post は最終更新から始まる。
    """

    def __init__(
        self,
        *,
        target_mode: str = "off",
        poster: Optional[GitHubProgressPoster] = None,
        clock: Any = _utc_now_iso,
    ) -> None:
        self._target_mode = target_mode if target_mode in AUTO_POST_TARGETS else "off"
        self._poster = poster if poster is not None else GitHubProgressPoster()
        self._clock = clock
        self._closed = False

        self._run_id = ""
        self._workflow_id = ""
        self._overall_status = "running"
        self._steps: Dict[str, Dict[str, Any]] = {}
        self._numbers: Dict[str, int] = {}
        self._started = False

    # -- 設定 -------------------------------------------------------------

    @property
    def target_mode(self) -> str:
        return self._target_mode

    def set_target_mode(self, mode: str) -> List[ProgressPostRequest]:
        """Post 先を切り替える。OFF への切替では既存コメントを削除しない。

        切替そのものは更新契機ではないため、直ちに Post しない（FR-GUI-36）。
        次の Step terminal または最終更新から新しい Post 先へ反映される。
        """
        self._target_mode = mode if mode in AUTO_POST_TARGETS else "off"
        return []

    # -- イベント ---------------------------------------------------------

    def handle_event(self, payload: Mapping[str, Any]) -> List[ProgressPostRequest]:
        """観測イベント 1 件を取り込み、開始すべき request を返す。"""
        if self._closed or not isinstance(payload, Mapping):
            return []

        kind = payload.get("kind")
        if kind == "github_target":
            return self._on_github_target(payload)
        if kind == "step_status":
            return self._on_step_status(payload)
        return []

    def finalize(
        self,
        *,
        overall_status: str,
        console_text: Optional[str] = None,
    ) -> List[ProgressPostRequest]:
        """Workflow 終了時の最終更新を返す。"""
        if self._closed:
            return []
        self._overall_status = overall_status
        return self._submit(console_text=console_text)

    def complete(
        self,
        kind: str,
        *,
        comment_id: Optional[int] = None,
        error: Optional[str] = None,
        generation: Optional[int] = None,
    ) -> Optional[ProgressPostRequest]:
        """API 完了を通知し、必要なら次の request を返す。"""
        return self._poster.complete(
            kind, comment_id=comment_id, error=error, generation=generation
        )

    def close(self) -> None:
        """新規 request の生成を停止する。既投稿コメントは削除しない。"""
        self._closed = True
        self._poster.close()

    # -- 内部処理 ---------------------------------------------------------

    def _on_github_target(self, payload: Mapping[str, Any]) -> List[ProgressPostRequest]:
        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id:
            self._run_id = run_id
        workflow_id = payload.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id:
            self._workflow_id = workflow_id

        for key, kind in (("issue_number", "issue"), ("pr_number", "pr")):
            number = payload.get(key)
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                continue
            self._numbers[kind] = number

        # target 確定自体は更新契機ではない。新規 PR は post-DAG で確定するため、
        # 最終更新で最新 snapshot を 1 回だけ Post する（FR-GUI-36）。
        return []

    def _on_step_status(self, payload: Mapping[str, Any]) -> List[ProgressPostRequest]:
        step_id = payload.get("step")
        if not isinstance(step_id, str) or not step_id:
            return []

        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id:
            self._run_id = run_id
        workflow_id = payload.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id:
            self._workflow_id = workflow_id

        status = payload.get("status")
        entry = self._steps.setdefault(step_id, {"step_id": step_id})
        if isinstance(status, str) and status:
            entry["status"] = status
        elapsed = payload.get("elapsed")
        if not isinstance(elapsed, bool) and isinstance(elapsed, (int, float)):
            entry["elapsed"] = elapsed

        # 更新契機は run 開始と Step の terminal 状態だけ。
        is_start = not self._started
        is_terminal = isinstance(status, str) and status in _STEP_TERMINAL_STATUSES
        if not (is_start or is_terminal):
            return []
        self._started = True
        return self._submit()

    def _register_targets(self) -> List[ProgressPostRequest]:
        requests: List[ProgressPostRequest] = []
        for kind in _KIND_BY_TARGET.get(self._target_mode, ()):
            number = self._numbers.get(kind)
            if number is None:
                continue
            request = self._poster.set_target(kind, number)
            if request is not None:
                requests.append(request)
        return requests

    def _submit(self, *, console_text: Optional[str] = None) -> List[ProgressPostRequest]:
        if self._target_mode == "off":
            return []
        body = format_progress_comment(
            run_id=self._run_id,
            workflow_id=self._workflow_id,
            overall_status=self._overall_status,
            steps=[self._steps[key] for key in sorted(self._steps)],
            updated_at=self._clock(),
            console_text=console_text if self._overall_status in FINAL_STATUSES else None,
        )
        body = _truncate_body(body)
        # 先に最新 snapshot を登録してから target を登録する。逆順だと新規 target へ
        # 古い snapshot を先に Post してしまう。
        requests = self._poster.submit(body)
        requests.extend(self._register_targets())
        return requests
