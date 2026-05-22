"""hve.gui.auth_monitor — 認証状態のバックグラウンド監視。

設計 (Q6=C 多重化):
    - ``QTimer`` で一定間隔 (既定 5 分) ごとに全プロバイダの ``check_status()``
      をワーカースレッドで非同期実行する。
    - 状態変化を Signal で配信:
        ``provider_state_changed(provider_id: str, state: str)``
        ``snapshot_changed(snapshot: dict[str, AuthState])``
        ``any_expired()``
        ``all_required_ok()``
    - ``force_refresh()`` でワークフロー実行直前の同期再確認も可能。

ライフサイクル:
    1. ``set_providers(providers)`` で監視対象を設定 (動的入れ替え可)。
    2. ``start()`` でタイマー開始。
    3. ``stop()`` で停止。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .auth_providers import AuthProvider, AuthState, AuthStatus, provider_is_required

__all__ = ["AuthMonitor", "DEFAULT_HEARTBEAT_MS"]


# 既定の heartbeat 間隔 (5 分)。
DEFAULT_HEARTBEAT_MS: int = 5 * 60 * 1000


class _CheckWorker(QThread):
    """全プロバイダの check_status を順番に実行するワーカー。"""

    done = Signal(dict)  # {provider_id: AuthStatus}

    def __init__(
        self,
        providers: List[AuthProvider],
        timeout: float,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._providers = list(providers)
        self._timeout = timeout

    def run(self) -> None:  # type: ignore[override]
        result: Dict[str, AuthStatus] = {}
        for p in self._providers:
            try:
                result[p.id] = p.check_status(timeout=self._timeout)
            except Exception as exc:  # pragma: no cover - 安全網
                result[p.id] = AuthStatus(
                    state=AuthState.UNKNOWN,
                    detail=f"{type(exc).__name__}: {exc}",
                )
        self.done.emit(result)


class AuthMonitor(QObject):
    """全プロバイダの認証状態を監視するシングルトン候補オブジェクト。"""

    provider_state_changed = Signal(str, str)  # (provider_id, AuthState.value)
    snapshot_changed = Signal(dict)            # {provider_id: AuthState.value}
    any_expired = Signal()
    all_required_ok = Signal()

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        heartbeat_ms: int = DEFAULT_HEARTBEAT_MS,
        check_timeout: float = 10.0,
    ) -> None:
        super().__init__(parent)
        self._providers: List[AuthProvider] = []
        self._states: Dict[str, AuthState] = {}
        self._heartbeat_ms = max(int(heartbeat_ms), 5_000)
        self._check_timeout = float(check_timeout)
        self._worker: Optional[_CheckWorker] = None
        # T10 (Wave 3): settings スナップショット (provider.is_required(settings) 用)
        self._settings: Dict[str, Any] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(self._heartbeat_ms)
        self._timer.timeout.connect(self._on_heartbeat)

    # ------------------------------------------------------------
    # 構成
    # ------------------------------------------------------------
    def set_providers(
        self,
        providers: List[AuthProvider],
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """監視対象を入れ替える (UNKNOWN で初期化)。

        T10: 任意で settings を同時更新可能。``settings is None`` の場合は
        既存スナップショットを維持する。
        """
        self._providers = list(providers)
        if settings is not None:
            self._settings = dict(settings)
        new_states: Dict[str, AuthState] = {}
        for p in self._providers:
            new_states[p.id] = self._states.get(p.id, AuthState.UNKNOWN)
        self._states = new_states
        self.snapshot_changed.emit(self._snapshot_value())

    def set_settings(self, settings: Dict[str, Any]) -> None:
        """T10: settings スナップショットを差し替える (provider 構成は維持)。"""
        self._settings = dict(settings or {})

    def current_settings(self) -> Dict[str, Any]:
        return dict(self._settings)

    def required_provider_ids(self) -> set[str]:
        """T10: 現在の settings に基づき必須プロバイダ ID 集合を返す。"""
        return {p.id for p in self._providers if provider_is_required(p, self._settings)}

    def providers(self) -> List[AuthProvider]:
        return list(self._providers)

    def heartbeat_ms(self) -> int:
        return self._heartbeat_ms

    def set_heartbeat_ms(self, value: int) -> None:
        self._heartbeat_ms = max(int(value), 5_000)
        self._timer.setInterval(self._heartbeat_ms)

    # ------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        worker = self._worker
        if worker is not None:
            worker.quit()
            worker.wait(2_000)
            self._worker = None

    # ------------------------------------------------------------
    # 状態取得
    # ------------------------------------------------------------
    def latest_state(self, provider_id: str) -> AuthState:
        return self._states.get(provider_id, AuthState.UNKNOWN)

    def snapshot(self) -> Dict[str, AuthState]:
        return dict(self._states)

    def _snapshot_value(self) -> Dict[str, str]:
        return {pid: state.value for pid, state in self._states.items()}

    # ------------------------------------------------------------
    # 強制更新
    # ------------------------------------------------------------
    def force_refresh(self) -> None:
        """非同期で全プロバイダの状態を即時更新する (Signal は通常通り発火)。"""
        self._launch_worker()

    def invalidate_provider(self, provider_id: str) -> None:
        """指定プロバイダの状態を ``UNKNOWN`` に戻し、次回チェックまで未確定扱いにする (T07)。

        PTY インタラクティブ認証 (T06) の完了直後など、外部 CLI の OS 資格情報ストア
        への書き込みが完了している保証は無いため、UI 上のステータスをいったん
        ``UNKNOWN`` に戻してから ``force_refresh()`` を呼び、最新状態へ更新する。
        """
        if provider_id in self._states and self._states[provider_id] is not AuthState.UNKNOWN:
            self._states[provider_id] = AuthState.UNKNOWN
            self.provider_state_changed.emit(provider_id, AuthState.UNKNOWN.value)
            self.snapshot_changed.emit(self._snapshot_value())

    def refresh_provider(self, provider_id: str) -> None:
        """指定プロバイダを ``UNKNOWN`` に戻してから全体 refresh を実行する (T07)。

        個別プロバイダだけの非同期 check_status は ``_CheckWorker`` の現在実装上
        サポートしていないため、内部的には全体リフレッシュへ委譲する。
        """
        self.invalidate_provider(provider_id)
        self.force_refresh()

    def _on_heartbeat(self) -> None:
        self._launch_worker()

    def _launch_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # 直前 worker 実行中はスキップ
        if not self._providers:
            return
        worker = _CheckWorker(self._providers, self._check_timeout, self)
        worker.done.connect(self._on_worker_done)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    # ------------------------------------------------------------
    # 結果ハンドリング
    # ------------------------------------------------------------
    def _on_worker_done(self, result: dict) -> None:
        any_expired = False
        all_required_ok = True
        # T10: 動的判定 — provider.is_required(settings) を利用
        required_ids = self.required_provider_ids()
        for pid, status in result.items():
            new_state: AuthState = status.state if isinstance(status, AuthStatus) else AuthState.UNKNOWN
            old_state = self._states.get(pid, AuthState.UNKNOWN)
            self._states[pid] = new_state
            if old_state is AuthState.AUTHENTICATED and new_state in (
                AuthState.NOT_AUTHENTICATED,
                AuthState.EXPIRED,
            ):
                any_expired = True
            if old_state != new_state:
                self.provider_state_changed.emit(pid, new_state.value)

        for pid in required_ids:
            if self._states.get(pid) is not AuthState.AUTHENTICATED:
                all_required_ok = False
                break

        self.snapshot_changed.emit(self._snapshot_value())
        if any_expired:
            self.any_expired.emit()
        if all_required_ok and required_ids:
            self.all_required_ok.emit()

    def _on_worker_finished(self) -> None:
        # worker は parent=self なので GC は親オブジェクト破棄時。
        # 完了時は参照を外して次回起動可能にする。
        self._worker = None
