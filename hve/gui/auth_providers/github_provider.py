"""hve.gui.auth_providers.github_provider — GitHub Copilot 認証プロバイダ。

既存 ``hve.auth`` モジュールをラップし ``AuthProvider`` プロトコルに適合させる。
認証フローは ``copilot login`` サブプロセス (Device Flow) に委譲する。
"""

from __future__ import annotations

import subprocess
from typing import Any, Callable, Dict, Optional

from . import AuthProvider, AuthResult, AuthState, AuthStatus, ProgressCallback

__all__ = ["GitHubProvider"]


class GitHubProvider:
    """GitHub Copilot CLI / SDK 用 ``AuthProvider`` 実装。"""

    id = "github"
    display_name = "GitHub Copilot"
    required = True

    def __init__(self, host: str = "https://github.com") -> None:
        self._host = host

    # ------------------------------------------------------------
    def is_applicable(self, settings: Dict[str, Any]) -> bool:  # noqa: ARG002
        # GitHub Copilot は HVE 全体で必須なので常に対象。
        return True

    # ------------------------------------------------------------
    def is_required(self, settings: Dict[str, Any]) -> bool:  # noqa: ARG002
        # T6 (Wave 2): GitHub Copilot はアプリ起動時から実行直前まで常に必須。
        return True

    # ------------------------------------------------------------
    def check_status(self, *, timeout: float = 30.0) -> AuthStatus:
        try:
            from hve import auth as _auth
        except ImportError as exc:
            return AuthStatus(
                state=AuthState.UNKNOWN,
                detail=f"auth module unavailable: {exc}",
            )
        try:
            info = _auth.get_auth_status(timeout=timeout)
        except Exception as exc:  # pragma: no cover - get_auth_status は基本握りつぶし
            return AuthStatus(state=AuthState.UNKNOWN, detail=str(exc))

        if getattr(info, "is_authenticated", False):
            return AuthStatus(
                state=AuthState.AUTHENTICATED,
                detail=getattr(info, "login", None),
            )
        msg = getattr(info, "status_message", None) or ""
        # SDK が "timeout" を返した場合は UNKNOWN として扱う (失効と区別)
        if "timeout" in msg.lower():
            return AuthStatus(state=AuthState.UNKNOWN, detail=msg)
        return AuthStatus(state=AuthState.NOT_AUTHENTICATED, detail=msg or None)

    # ------------------------------------------------------------
    def authenticate(
        self,
        *,
        timeout: float = 600.0,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> AuthResult:
        try:
            from hve import auth as _auth
        except ImportError as exc:
            return AuthResult(
                success=False,
                state=AuthState.UNKNOWN,
                message=f"auth module unavailable: {exc}",
            )

        exe = _auth.find_copilot_binary()
        if not exe:
            return AuthResult(
                success=False,
                state=AuthState.NOT_AUTHENTICATED,
                message="copilot 実行ファイルが見つかりません。",
            )

        if on_progress:
            on_progress(f"$ {exe} login")

        def _forward(line: str) -> None:
            if on_progress and line:
                on_progress(line)

        try:
            rc = _auth.run_login(
                host=self._host,
                binary=exe,
                timeout=timeout,
                on_output=_forward if on_progress else None,
            )
        except subprocess.TimeoutExpired:
            return AuthResult(
                success=False,
                state=AuthState.NOT_AUTHENTICATED,
                message=f"timeout after {timeout}s",
            )
        except Exception as exc:
            return AuthResult(
                success=False,
                state=AuthState.UNKNOWN,
                message=f"{type(exc).__name__}: {exc}",
            )

        if cancel_check and cancel_check():
            return AuthResult(
                success=False,
                state=AuthState.NOT_AUTHENTICATED,
                message="cancelled",
            )

        if rc == 0:
            status = self.check_status(timeout=15.0)
            return AuthResult(
                success=status.state.is_ok,
                state=status.state,
                message=status.detail,
            )
        return AuthResult(
            success=False,
            state=AuthState.NOT_AUTHENTICATED,
            message=f"copilot login exited with code {rc}",
        )
