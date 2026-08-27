"""hve.gui.github_branch_cleanup_monitor — GUI 起動中の targeted cleanup 監視（FR-GUI-37）。

当該 GUI セッション内で HVE が作成した作業 branch について、指定 PR 番号だけを
低頻度で確認し、merged を観測したときだけ FR-CLI-34 の共通 core へローカル cleanup を
委譲する。Issue / Pull Request の一覧 API と remote branch 削除は使わない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from hve.branch_cleanup import LocalBranchCleanupTarget, cleanup_local_branch

__all__ = [
    "PullRequestStatusRequest",
    "LocalCleanupRequest",
    "GitHubBranchCleanupMonitor",
    "build_status_task",
]


@dataclass(frozen=True)
class PullRequestStatusRequest:
    """`get_pull_request` を 1 回だけ実行するための要求。"""

    repo: str
    pr_number: int
    target: LocalBranchCleanupTarget
    generation: int


@dataclass(frozen=True)
class LocalCleanupRequest:
    """共通 core へ委譲するローカル cleanup 要求。"""

    target: LocalBranchCleanupTarget
    pull_request: Mapping[str, Any]

    def run(self, *, runner: Any = None):
        """FR-CLI-34 の共通 core へ委譲する（判定・削除を再実装しない）。"""
        return cleanup_local_branch(self.target, self.pull_request, runner=runner)


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def build_status_task(request: PullRequestStatusRequest):
    """`GitHubWorker` へ渡す status 取得 task を返す。

    対象 PR 番号を指定した `github_service.get_pull_request` だけを使い、
    Issue / Pull Request の一覧 API を呼ばない（FR-GUI-37 / FR-GUI-31）。
    実行は必ず `GitHubWorker` から行い、GUI thread で呼ばない。
    """
    from functools import partial

    from . import github_service

    return partial(github_service.get_pull_request, request.repo, request.pr_number)


class _TargetState:
    """監視対象 1 件分の状態。"""

    def __init__(self, target: LocalBranchCleanupTarget, generation: int, now: float) -> None:
        self.target = target
        self.generation = generation
        self.due_at = now
        self.in_flight = False
        self.stopped = False


class GitHubBranchCleanupMonitor:
    """PR 番号を指定した status 確認と、merged 時のローカル cleanup 委譲を管理する。

    GUI thread では GitHub API も git command も実行しない。本クラスは状態遷移だけを
    担い、実際の API 呼び出しは呼び出し側が `GitHubWorker` から行う。
    """

    def __init__(self, *, enabled: bool, poll_interval_seconds: float) -> None:
        interval = float(poll_interval_seconds)
        if interval <= 0:
            raise ValueError("poll_interval_seconds は正の値である必要があります。")
        self._enabled = bool(enabled)
        self._interval = interval
        self._closed = False
        self._generation = 0
        self._targets: Dict[int, _TargetState] = {}
        self._finished: set = set()
        # 進行中 worker の回収用（呼び出し側が `track_worker` で登録する）。
        self._workers: List[Any] = []

    def track_worker(self, worker: Any) -> None:
        """回収対象の worker を登録し、完了時に自動で外す。

        GUI セッションが長く続いても worker 一覧が無制限に伸びないようにする。
        """
        self._workers.append(worker)
        finished = getattr(worker, "finished", None)
        connect = getattr(finished, "connect", None)
        if connect is None:
            return

        def _forget() -> None:
            try:
                self._workers.remove(worker)
            except ValueError:
                pass

        try:
            connect(_forget)
        except Exception:
            pass

    # -- 登録 -------------------------------------------------------------

    def watch(self, target: LocalBranchCleanupTarget, *, now: float) -> bool:
        """監視対象を登録する。登録した場合だけ ``True`` を返す。"""
        if not self._enabled or self._closed:
            return False
        if not getattr(target, "created_by_hve", False):
            return False

        number = _positive_int(getattr(target, "pr_number", None))
        if number is None:
            return False
        if number in self._finished:
            # cleanup 要求を生成済みの target は同じセッションで再登録しない。
            return False

        existing = self._targets.get(number)
        if existing is not None and existing.target == target:
            # 重複登録は進行中 request の状態を初期化しない。
            return False

        self._generation += 1
        self._targets[number] = _TargetState(target, self._generation, now)
        return True

    # -- ポーリング -------------------------------------------------------

    def poll_due(self, *, now: float) -> List[PullRequestStatusRequest]:
        """確認期限に達した target の status request を返す。"""
        if self._closed:
            return []

        requests: List[PullRequestStatusRequest] = []
        # 反復中に `watch()` で target が追加されても壊れないよう snapshot を取る。
        for number, state in list(self._targets.items()):
            if state.stopped or state.in_flight or now < state.due_at:
                continue
            state.in_flight = True
            requests.append(
                PullRequestStatusRequest(
                    repo=state.target.repo,
                    pr_number=number,
                    target=state.target,
                    generation=state.generation,
                )
            )
        return requests

    def complete(
        self,
        request: PullRequestStatusRequest,
        *,
        pull_request: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        retryable: bool = False,
        now: float = 0.0,
    ) -> Optional[LocalCleanupRequest]:
        """status request の完了を通知し、merged なら cleanup 要求を返す。"""
        state = self._targets.get(request.pr_number)
        if state is None or state.generation != request.generation:
            # 差し替え後に到着した旧世代の完了。現行 target へ反映しない。
            return None
        if state.stopped:
            # 監視終了済み。cleanup 要求を二重生成しない。
            return None

        state.in_flight = False
        if self._closed:
            state.stopped = True
            return None

        if error is not None:
            if retryable:
                state.due_at = now + self._interval
            else:
                state.stopped = True
            return None

        if not isinstance(pull_request, Mapping):
            state.stopped = True
            return None
        if _positive_int(pull_request.get("number")) != request.pr_number:
            state.stopped = True
            return None

        if pull_request.get("merged") is True:
            state.stopped = True
            self._finished.add(request.pr_number)
            return LocalCleanupRequest(target=state.target, pull_request=pull_request)

        if str(pull_request.get("state") or "").lower() == "closed":
            # closed-unmerged は恒久的に対象外。
            state.stopped = True
            return None

        state.due_at = now + self._interval
        return None

    # -- 終了 -------------------------------------------------------------

    def close(self) -> None:
        """新規 target と新規 request の生成を停止する。"""
        self._closed = True

    def shutdown(self, *, timeout_ms: int) -> None:
        """状態を閉じ、進行中 worker を上限付きで回収する。"""
        self.close()
        for worker in list(self._workers):
            try:
                worker.wait(timeout_ms)
            except Exception:
                pass
        self._workers.clear()
