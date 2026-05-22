"""hve.gui.auth_providers.mcp_generic_provider — 汎用 MCP サーバー疎通確認プロバイダ。

``mcp_config`` JSON で定義された個別 MCP サーバーごとに 1 インスタンス生成する。
MCP プロトコルには標準的な認証方式が定められていないため、本プロバイダは
**疎通確認 (Copilot SDK で 1 セッションを張れるか)** のみを行う。

設計:
    - mcp_config JSON のスキーマは Copilot SDK の ``mcp_servers`` 引数互換
      (``{"servers": {"<name>": {...}}}`` または ``{"<name>": {...}}``)。
    - 疎通成功 = AUTHENTICATED, 失敗 = NOT_AUTHENTICATED。
    - 認証フロー (authenticate) も check_status と同じく疎通テストを再実行する。
      サーバー固有の認証は GUI からは制御できないため、ユーザーに事前準備を案内する。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from . import AuthProvider, AuthResult, AuthState, AuthStatus, InteractivePlan, ProgressCallback

__all__ = ["McpGenericProvider"]


def _probe_session(server_name: str, server_def: Dict[str, Any], timeout: float) -> tuple[bool, str]:
    """Copilot SDK で create_session を試行する。

    Returns:
        (success, detail) のタプル。detail は失敗理由 / 成功確認メッセージ。
    """

    async def _run() -> tuple[bool, str]:
        try:
            from copilot import CopilotClient  # type: ignore[import-not-found]
            from copilot.session import PermissionHandler  # type: ignore[import-not-found]
        except ImportError as exc:
            return False, f"github-copilot-sdk import failed: {exc}"

        client = CopilotClient()
        try:
            await client.start()
            await client.create_session(
                mcp_servers={server_name: server_def},
                on_permission_request=PermissionHandler.approve_all,
            )
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            try:
                await client.stop()
            except Exception:  # pragma: no cover
                pass
        return True, "create_session ok"

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
    except asyncio.TimeoutError:
        return False, f"timeout after {timeout}s"
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"


class McpGenericProvider:
    """``mcp_config`` 内の 1 サーバー = 1 プロバイダ。"""

    required = False
    supports_interactive = True

    def __init__(self, server_name: str, server_def: Dict[str, Any]) -> None:
        self._name = server_name
        self._def = dict(server_def)
        self.id = f"mcp:{server_name}"
        self.display_name = f"MCP: {server_name}"
        # 敵対的レビュー #5: manifest を 1 度だけ読み込みキャッシュ。
        # is_required は heartbeat 毎に呼ばれるため YAML 再パースを避ける。
        # None = 未ロード、False = ロード試行済 (manifest 無し or 失敗)。
        self._manifest_cache: Any = None
        self._manifest_loaded: bool = False

    # ------------------------------------------------------------
    def is_applicable(self, settings: Dict[str, Any]) -> bool:  # noqa: ARG002
        return True

    # ------------------------------------------------------------
    def is_required(self, settings: Dict[str, Any]) -> bool:
        """T8 (Wave 2 / C2 + E2): MCP サーバ利用 ON かつ manifest が認証必要なら True。

        判定:
            1. ``settings["mcp_enabled"][self._name]`` が True (利用 ON)。
            2. manifest の ``auth_required`` が True (Microsoft Learn 等 False は除外)。
               manifest が見つからない場合は ``_default.yml`` の ``auth_required=True``
               にフォールバック (= 安全側に倒して必須扱い)。

        どちらかが False なら認証ガード対象外。
        """
        if not isinstance(settings, dict):
            return False
        mcp_enabled = settings.get("mcp_enabled") or {}
        if not isinstance(mcp_enabled, dict):
            return False
        enabled = mcp_enabled.get(self._name)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return False

        # manifest の auth_required を参照 (manifest が無い場合は True)
        manifest = self._get_manifest_cached()
        if manifest is None:
            return True
        return bool(getattr(manifest, "auth_required", True))

    def _get_manifest_cached(self) -> Any:
        """manifest を 1 度だけロードしてキャッシュする (敵対的レビュー #5)。"""
        if self._manifest_loaded:
            return self._manifest_cache
        try:
            from .manifests import load_manifest_for
            self._manifest_cache = load_manifest_for(
                provider_id=self.id, mcp_server_name=self._name
            )
        except Exception:
            # ロード失敗時は None を返し、上位で安全側 (auth_required=True 扱い)
            self._manifest_cache = None
        self._manifest_loaded = True
        return self._manifest_cache

    # ------------------------------------------------------------
    def build_interactive_plan(
        self, settings: Dict[str, Any]  # noqa: ARG002
    ) -> Optional[InteractivePlan]:
        """manifest があれば InteractivePlan を組み立てて返す。

        manifest 不在時は ``_default`` manifest がマッチする。それも見つからない
        場合は ``None`` を返し、呼び出し側で従来の疎通確認のみへフォールバック。
        """
        # 遅延 import (PySide6 / CommandSpec 依存を CLI モードで巻き込まない)
        from ..pty_auth_controller import CommandSpec
        from .manifests import load_manifest_for

        manifest = load_manifest_for(
            provider_id=self.id, mcp_server_name=self._name
        )
        if manifest is None:
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
        main = None
        if manifest.main_command is not None:
            main = CommandSpec(
                argv=manifest.main_command.argv,
                success_regex=manifest.main_command.success_regex,
                failure_regex=manifest.main_command.failure_regex,
                timeout=manifest.main_command.timeout,
            )
        return InteractivePlan(
            display_name=manifest.display_name or self.display_name,
            pre_commands=pre,
            main_command=main,
            notes_md=manifest.notes_md,
            timeout_total=manifest.timeout_total,
            source_manifest_id=manifest.id,
        )

    # ------------------------------------------------------------
    def check_status(self, *, timeout: float = 15.0) -> AuthStatus:
        ok, detail = _probe_session(self._name, self._def, timeout)
        state = AuthState.AUTHENTICATED if ok else AuthState.NOT_AUTHENTICATED
        return AuthStatus(state=state, detail=detail)

    # ------------------------------------------------------------
    def authenticate(
        self,
        *,
        timeout: float = 600.0,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,  # noqa: ARG002
    ) -> AuthResult:
        if on_progress:
            on_progress(
                f"MCP '{self._name}' は GUI 経由の認証フローを提供していません。"
                "サーバー固有の認証 (環境変数 / 個別ログイン等) を事前に完了してください。"
                "疎通確認のみを実施します。"
            )
            on_progress(f"create_session 疎通テスト中 (timeout={timeout}s)...")
        ok, detail = _probe_session(self._name, self._def, timeout)
        if on_progress:
            on_progress(detail)
        if ok:
            return AuthResult(success=True, state=AuthState.AUTHENTICATED, message=detail)
        return AuthResult(
            success=False,
            state=AuthState.NOT_AUTHENTICATED,
            message=detail,
        )
