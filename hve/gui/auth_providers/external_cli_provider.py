"""hve.gui.auth_providers.external_cli_provider — Copilot SDK 外部 CLI サーバー疎通確認。

設定 ``cli_url`` (例: ``localhost:4321``) が指定されている場合のみ対象となる。
TCP レベルで疎通確認を行う (CopilotClient の ExternalServerConfig は実際に
セッションを張らないと検証できないため、ここでは軽量な TCP 接続でフォールバック)。

設計:
    - 認証は外部サーバー側に委譲されるため、本プロバイダは「接続可能性」のみを判定する。
    - 認証フロー固有の UI は提供しない (疎通確認のみ再実行)。
"""

from __future__ import annotations

import socket
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from . import AuthProvider, AuthResult, AuthState, AuthStatus, InteractivePlan, ProgressCallback

__all__ = ["ExternalCliProvider"]


def _parse_host_port(url: str) -> tuple[Optional[str], Optional[int]]:
    """``localhost:4321`` / ``http://localhost:4321`` 両形式からホスト・ポートを抽出。"""
    if not url:
        return None, None
    s = url.strip()
    if "://" not in s:
        s = "//" + s  # urlparse のための擬似スキーム
    parsed = urlparse(s, scheme="http")
    host = parsed.hostname
    port = parsed.port
    if port is None and parsed.scheme in ("http", "https"):
        port = 80 if parsed.scheme == "http" else 443
    return host, port


def _probe_tcp(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP connect ok ({host}:{port})"
    except OSError as exc:
        return False, f"TCP connect failed: {exc}"


class ExternalCliProvider:
    """``cli_url`` 用 ``AuthProvider`` 実装。"""

    id = "external_cli"
    display_name = "Copilot SDK 外部サーバー"
    required = False
    supports_interactive = True

    def __init__(self, url: str) -> None:
        self._url = url

    # ------------------------------------------------------------
    def is_applicable(self, settings: Dict[str, Any]) -> bool:
        return bool(settings.get("cli_url") or self._url)

    # ------------------------------------------------------------
    def is_required(self, settings: Dict[str, Any]) -> bool:
        """T9 (Wave 2): ``cli_url`` 設定があり利用中なら True。"""
        opts = settings.get("options", {}) if isinstance(settings, dict) else {}
        url = ""
        if isinstance(opts, dict):
            url = str(opts.get("cli_url") or "").strip()
        if not url:
            url = (settings.get("cli_url") if isinstance(settings, dict) else "") or ""
            url = str(url).strip()
        if not url:
            url = (self._url or "").strip()
        return bool(url)

    # ------------------------------------------------------------
    def build_interactive_plan(
        self, settings: Dict[str, Any]  # noqa: ARG002
    ) -> Optional[InteractivePlan]:
        """manifest が cli_url にマッチすれば InteractivePlan を返す。"""
        from ..pty_auth_controller import CommandSpec
        from .manifests import load_manifest_for

        manifest = load_manifest_for(provider_id=self.id, cli_url=self._url)
        if manifest is None or not manifest.pre_auth_commands:
            # 前提コマンドが無い manifest は PTY 起動の意味が薄いため None 扱い
            return None
        pre = [
            CommandSpec(
                argv=cmd.argv,
                success_regex=cmd.success_regex,
                failure_regex=cmd.failure_regex,
                timeout=cmd.timeout,
            )
            for cmd in manifest.pre_auth_commands
        ]
        return InteractivePlan(
            display_name=manifest.display_name or self.display_name,
            pre_commands=pre,
            notes_md=manifest.notes_md,
            timeout_total=manifest.timeout_total,
            source_manifest_id=manifest.id,
        )

    # ------------------------------------------------------------
    def check_status(self, *, timeout: float = 15.0) -> AuthStatus:
        host, port = _parse_host_port(self._url)
        if host is None or port is None:
            return AuthStatus(
                state=AuthState.NOT_AUTHENTICATED,
                detail=f"cli_url の解析に失敗: {self._url!r}",
            )
        ok, detail = _probe_tcp(host, port, timeout=min(timeout, 5.0))
        state = AuthState.AUTHENTICATED if ok else AuthState.NOT_AUTHENTICATED
        return AuthStatus(state=state, detail=detail)

    # ------------------------------------------------------------
    def authenticate(
        self,
        *,
        timeout: float = 60.0,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,  # noqa: ARG002
    ) -> AuthResult:
        if on_progress:
            on_progress(
                "外部 CLI サーバーの認証はサーバー側で行います。GUI からは疎通確認のみ実行します。"
            )
        status = self.check_status(timeout=timeout)
        return AuthResult(
            success=status.state.is_ok,
            state=status.state,
            message=status.detail,
        )
