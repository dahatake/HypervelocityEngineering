"""hve.gui.auth_providers.workiq_provider — Work IQ 認証プロバイダ。

``npx -y @microsoft/workiq accept-eula`` と ``ask -q ping`` のシーケンスを実行し
認証状態を確定する。詳細は ``hve.workiq.workiq_login`` を参照。

設計:
    - **GUI 設定の ``workiq_tenant_id`` は廃止済**。Copilot CLI の
      ``copilot plugin list`` に ``workiq`` プラグインがあるときのみ registry が
      本プロバイダをインスタンス化する。
    - check_status は ``hve.workiq.is_workiq_available`` (キャッシュ付き) を再利用。
    - authenticate は ``workiq_login`` (同期) を直接呼ぶ。GUI 上のキャンセルは
      実行中サブプロセスを kill する手段が無いため timeout で打ち切る方針。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from . import AuthProvider, AuthResult, AuthState, AuthStatus, ProgressCallback

__all__ = ["WorkIQProvider"]


class _ProgressConsole:
    """``hve.workiq.workiq_login`` が要求する Console プロトコルの最小実装。"""

    def __init__(self, on_progress: Optional[ProgressCallback]) -> None:
        self._on_progress = on_progress

    def _emit(self, prefix: str, msg: str) -> None:
        if self._on_progress:
            try:
                self._on_progress(f"[{prefix}] {msg}")
            except Exception:  # pragma: no cover
                pass

    def info(self, msg: str) -> None:  # pragma: no cover - 呼ばれない可能性あり
        self._emit("info", msg)

    def warning(self, msg: str) -> None:
        self._emit("warn", msg)

    def error(self, msg: str) -> None:  # pragma: no cover
        self._emit("error", msg)


class WorkIQProvider:
    """Microsoft Work IQ MCP 用 ``AuthProvider`` 実装。"""

    id = "workiq"
    display_name = "Microsoft Work IQ"
    required = False  # Work IQ はオプショナル

    def __init__(self) -> None:
        # tenant_id は Copilot CLI plugin 側で管理されるため GUI では保持しない。
        pass

    # ------------------------------------------------------------
    def is_applicable(self, settings: Dict[str, Any]) -> bool:  # noqa: ARG002
        # registry が ``copilot plugin list`` に ``workiq`` があるときのみ
        # 本プロバイダを生成するため、生成された時点で常に True 。
        return True

    # ------------------------------------------------------------
    def is_required(self, settings: Dict[str, Any]) -> bool:
        """T7 (Wave 2 / B1): Work IQ 関連オプションのいずれかが ON/値ありなら必須。

        判定対象キー (``settings["options"]`` 配下):
            - workiq                          (bool)
            - workiq_akm_review               (tristate str: "true"/"false"/"")
            - workiq_akm_ingest               (tristate str)
            - workiq_draft                    (bool)
            - workiq_dxx                      (str: 非空なら使用扱い)
            - workiq_draft_output_dir         (str: 非空なら使用扱い)
            - workiq_prompt_qa / _km / _review (str: 非空なら使用扱い)
            - workiq_per_question_timeout     (float: > 0 なら使用扱い)

        Step 2 で 1 つでも ON/値あり → True。
        """
        opts = settings.get("options", {}) if isinstance(settings, dict) else {}
        if not isinstance(opts, dict):
            return False

        # bool 直接判定
        for key in ("workiq", "workiq_draft"):
            v = opts.get(key)
            if isinstance(v, bool) and v:
                return True
            if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "on"):
                return True

        # tristate: "true" のみ ON 扱い (空 / "false" は未指定/明示 OFF)
        for key in ("workiq_akm_review", "workiq_akm_ingest"):
            v = opts.get(key)
            if isinstance(v, str) and v.strip().lower() == "true":
                return True
            if v is True:
                return True

        # 文字列キー: 非空なら使用扱い
        for key in (
            "workiq_dxx",
            "workiq_draft_output_dir",
            "workiq_prompt_qa",
            "workiq_prompt_km",
            "workiq_prompt_review",
        ):
            v = opts.get(key)
            if isinstance(v, str) and v.strip():
                return True

        # タイムアウト: > 0 なら使用扱い
        v = opts.get("workiq_per_question_timeout")
        try:
            if v is not None and float(v) > 0.0:
                return True
        except (TypeError, ValueError):
            pass

        return False

    # ------------------------------------------------------------
    def check_status(self, *, timeout: float = 15.0) -> AuthStatus:  # noqa: ARG002
        try:
            from hve.workiq import is_workiq_available
        except ImportError as exc:
            return AuthStatus(
                state=AuthState.UNKNOWN,
                detail=f"workiq module unavailable: {exc}",
            )
        # is_workiq_available は npx 経由で 'version' が成功するかを確認する。
        # 認証済みかを正確に検知する API は存在しないため、利用可能性を以て
        # AUTHENTICATED とみなす方針 (ask -q ping は重いので check_status では避ける)。
        try:
            ok = is_workiq_available()
        except Exception as exc:  # pragma: no cover
            return AuthStatus(state=AuthState.UNKNOWN, detail=str(exc))
        if ok:
            return AuthStatus(state=AuthState.AUTHENTICATED)
        return AuthStatus(state=AuthState.NOT_AUTHENTICATED)

    # ------------------------------------------------------------
    def authenticate(
        self,
        *,
        timeout: float = 600.0,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,  # noqa: ARG002 - 内部 sync 不可
    ) -> AuthResult:
        try:
            from hve.workiq import workiq_login
        except ImportError as exc:
            return AuthResult(
                success=False,
                state=AuthState.UNKNOWN,
                message=f"workiq module unavailable: {exc}",
            )
        console = _ProgressConsole(on_progress)
        if on_progress:
            on_progress(f"workiq_login starting (timeout={timeout}s)")
        try:
            ok = workiq_login(console, timeout=timeout)
        except Exception as exc:
            return AuthResult(
                success=False,
                state=AuthState.UNKNOWN,
                message=f"{type(exc).__name__}: {exc}",
            )
        if ok:
            return AuthResult(success=True, state=AuthState.AUTHENTICATED)
        return AuthResult(
            success=False,
            state=AuthState.NOT_AUTHENTICATED,
            message="workiq_login returned False",
        )
