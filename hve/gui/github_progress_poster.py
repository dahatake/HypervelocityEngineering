"""hve.gui.github_progress_poster — rolling 進捗コメントの状態機械（FR-GUI-36）。

Post 先 1 件につき run ごとに 1 コメントだけを作成し、以降は同じ comment ID を
更新する。GitHub API は呼ばず、呼び出し側（`GitHubWorker`）へ渡す要求だけを返す
純粋な状態機械とし、PySide6 へは依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

__all__ = ["ProgressPostRequest", "GitHubProgressPoster"]

# Post 先の種別。要件が定める Issue / Pull Request の 2 種類だけを扱う。
_TARGET_KINDS = ("issue", "pr")


@dataclass(frozen=True)
class ProgressPostRequest:
    """呼び出し側が 1 回だけ実行すべき GitHub API 要求。"""

    kind: str
    target_number: int
    operation: str
    body: str
    comment_id: Optional[int] = None
    generation: int = 0


class _TargetState:
    """Post 先 1 件分の状態。"""

    def __init__(self, number: int, generation: int) -> None:
        self.number = number
        self.generation = generation
        self.comment_id: Optional[int] = None
        self.in_flight = False
        self.pending: Optional[str] = None

    def build_request(self, kind: str, body: str) -> ProgressPostRequest:
        operation = "update" if self.comment_id is not None else "create"
        return ProgressPostRequest(
            kind=kind,
            target_number=self.number,
            operation=operation,
            body=body,
            comment_id=self.comment_id,
            generation=self.generation,
        )


class GitHubProgressPoster:
    """Post 先ごとに 1 コメントを作成・更新する rolling state machine。

    - 同一 target への request が進行中の間は中間状態を queue へ積まず、
      最新 snapshot 1 件へ畳み込む。
    - create 失敗では comment ID を確定させず次回 create を再試行し、
      update 失敗では既存 comment ID を保持して次回 update を再試行する。
    - target 番号を変更した場合は旧 comment ID を再利用せず新規 create する。
      旧 target の in-flight 完了が遅延到着しても、世代不一致として無視する。
    - `close()` 後は新規 request を作らず、in-flight 完了通知でも pending を出さない。
    """

    def __init__(self) -> None:
        self._targets: Dict[str, _TargetState] = {}
        self._latest_body: Optional[str] = None
        self._closed = False
        self._generation = 0

    # -- 状態遷移 ---------------------------------------------------------

    def set_target(self, kind: str, number: int) -> Optional[ProgressPostRequest]:
        """Post 先を登録・変更する。

        既に最新 snapshot があり、かつ当該 target が idle なら即時 request を返す。
        """
        if self._closed or kind not in _TARGET_KINDS:
            return None

        existing = self._targets.get(kind)
        if existing is not None and existing.number == number:
            return None

        # 番号が変わった target では旧 comment ID を引き継がない。
        self._generation += 1
        self._targets[kind] = _TargetState(number, self._generation)
        return self._start_if_possible(kind)

    def submit(self, body: str) -> List[ProgressPostRequest]:
        """最新 snapshot を記録し、開始できる request を返す。"""
        if self._closed:
            return []
        self._latest_body = body

        requests: List[ProgressPostRequest] = []
        for kind in _TARGET_KINDS:
            request = self._start_if_possible(kind)
            if request is not None:
                requests.append(request)
        return requests

    def complete(
        self,
        kind: str,
        *,
        comment_id: Optional[int] = None,
        error: Optional[str] = None,
        generation: Optional[int] = None,
    ) -> Optional[ProgressPostRequest]:
        """in-flight request の完了を通知し、必要なら次の request を返す。

        `generation` を渡すと、target 差し替え後に到着した旧 request の完了を
        無視できる（旧 comment ID を新 target へ持ち込まない）。
        """
        state = self._targets.get(kind)
        if state is None:
            return None
        if generation is not None and generation != state.generation:
            # 差し替え前の target に属する完了通知。現行 target へ反映しない。
            return None

        state.in_flight = False
        if error is None and comment_id is not None:
            state.comment_id = comment_id

        if self._closed:
            state.pending = None
            return None

        pending = state.pending
        state.pending = None
        if pending is None:
            return None
        return self._start(kind, state, pending)

    def close(self) -> None:
        """新規 request の生成を停止する。既投稿コメントは削除しない。"""
        self._closed = True
        for state in self._targets.values():
            state.pending = None

    # -- 内部ヘルパ -------------------------------------------------------

    def _start_if_possible(self, kind: str) -> Optional[ProgressPostRequest]:
        # close 後は pending を含めて一切の新規生成を行わない（fail-closed）。
        if self._closed:
            return None
        state = self._targets.get(kind)
        if state is None or self._latest_body is None:
            return None
        if state.in_flight:
            # in-flight 中は最新 snapshot 1 件へ畳み込む（queue しない）。
            state.pending = self._latest_body
            return None
        return self._start(kind, state, self._latest_body)

    def _start(self, kind: str, state: _TargetState, body: str) -> ProgressPostRequest:
        state.in_flight = True
        return state.build_request(kind, body)
