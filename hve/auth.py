"""auth.py — GitHub Copilot 認証ユーティリティ

`github-copilot-sdk` パッケージ同梱の `copilot.exe` が OAuth Device Flow + OS
資格情報ストア保存を実装済みのため、本モジュールは以下の薄いラッパーを提供する:

  1. 認証状態の確認 (`get_auth_status` / `is_authenticated`)
  2. ログイン起動 (`run_login` — `copilot login` サブコマンドを起動)
  3. 環境変数優先順の解決 (`resolve_token_env`)

トークン参照優先順 (Copilot CLI 仕様):
    COPILOT_GITHUB_TOKEN > GH_TOKEN > GITHUB_TOKEN

外部依存:
    - github-copilot-sdk (CopilotClient, SessionAuthStatus)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

__all__ = [
    "AuthInfo",
    "AuthError",
    "TOKEN_ENV_VARS",
    "resolve_token_env",
    "get_auth_status",
    "is_authenticated",
    "ensure_authenticated",
    "run_login",
    "find_copilot_binary",
]


# Copilot CLI が参照する環境変数の優先順 (高 → 低)
TOKEN_ENV_VARS: tuple[str, ...] = (
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


# ---------------------------------------------------------------------------
# データクラス・例外
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthInfo:
    """SDK の SessionAuthStatus から必要項目を抽出した不変データ。"""

    is_authenticated: bool
    login: Optional[str] = None
    copilot_plan: Optional[str] = None
    host: Optional[str] = None
    status_message: Optional[str] = None


class AuthError(Exception):
    """認証関連エラー。"""


# ---------------------------------------------------------------------------
# トークン解決
# ---------------------------------------------------------------------------


def resolve_token_env() -> Optional[str]:
    """環境変数から Copilot CLI 互換のトークンを優先順で解決する。

    Returns:
        最初に見つかった非空トークン文字列。何もなければ None。
    """
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# 認証状態取得
# ---------------------------------------------------------------------------


async def _get_auth_status_async(
    *,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> AuthInfo:
    """SDK CopilotClient を起動して認証状態を取得する (内部 async 実装)。"""
    if cli_path or cli_url:
        try:
            from .copilot_client_factory import create_copilot_client
        except ImportError:
            try:
                from copilot_client_factory import create_copilot_client  # type: ignore[import-not-found,no-redef]
            except ImportError as e:  # pragma: no cover - SDK 必須
                raise AuthError(f"github-copilot-sdk が import できません: {e}") from e
        client = create_copilot_client(
            cli_path=cli_path,
            cli_url=cli_url,
            log_level="error",
        )
    else:
        try:
            from copilot import CopilotClient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - SDK 必須
            raise AuthError(f"github-copilot-sdk が import できません: {e}") from e
        client = CopilotClient()
    try:
        await client.start()
        status = await client.get_auth_status()
        # SDK の GetAuthStatusResponse は camelCase 属性 (isAuthenticated /
        # statusMessage) を持つ。互換のため snake_case も fallback で参照する。
        return AuthInfo(
            is_authenticated=bool(
                getattr(
                    status,
                    "isAuthenticated",
                    getattr(status, "is_authenticated", False),
                )
            ),
            login=getattr(status, "login", None),
            copilot_plan=getattr(status, "copilot_plan", None),
            host=getattr(status, "host", None),
            status_message=getattr(
                status,
                "statusMessage",
                getattr(status, "status_message", None),
            ),
        )
    finally:
        try:
            await client.stop()
        except Exception:
            # stop 失敗は致命的でないため握りつぶす
            pass


def get_auth_status(
    timeout: float = 30.0,
    *,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> AuthInfo:
    """認証状態を同期的に取得する。

    Args:
        timeout: SDK 起動 + ステータス取得のタイムアウト秒。
        cli_path: 状態確認に使うlocal Copilot CLI runtimeの明示path。
        cli_url: 状態確認に使う既存Copilot CLI server URL。

    Returns:
        AuthInfo。SDK 起動失敗時は is_authenticated=False の AuthInfo を返し、
        status_message にエラー要約を格納する (例外を投げない方針)。
    """
    try:
        return asyncio.run(
            asyncio.wait_for(
                _get_auth_status_async(cli_path=cli_path, cli_url=cli_url),
                timeout=timeout,
            )
        )
    except asyncio.TimeoutError:
        return AuthInfo(
            is_authenticated=False,
            status_message=f"timeout after {timeout}s",
        )
    except AuthError:
        raise
    except Exception as e:  # SDK ランタイムエラーは握りつぶし未認証扱い
        return AuthInfo(
            is_authenticated=False,
            status_message=f"{type(e).__name__}: {e}",
        )


def is_authenticated(
    timeout: float = 30.0,
    *,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> bool:
    """認証済みかどうかの便利関数。"""
    return get_auth_status(
        timeout=timeout,
        cli_path=cli_path,
        cli_url=cli_url,
    ).is_authenticated


def ensure_authenticated(
    *,
    interactive: bool = False,
    host: str = "https://github.com",
    status_timeout: float = 30.0,
    login_timeout: Optional[float] = None,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> AuthInfo:
    """GitHub Copilot 認証状態を確認し、必要ならログインを実行する。

    Args:
        interactive: True のとき、未認証なら ``copilot login`` を実行する。
            False のときは状態確認のみ行う。
        host: ``copilot login`` に渡す GitHub ホスト URL。
        status_timeout: 認証状態確認のタイムアウト秒。
        login_timeout: ``copilot login`` のタイムアウト秒。None で無制限。
        cli_path: 状態確認と対話loginに使うlocal runtimeの明示path。
        cli_url: 状態確認に使う外部runtime。未認証時のlocal login代替は行わない。

    Returns:
        最終的な AuthInfo。ログインコマンドが非 0 で終了した場合は
        ``is_authenticated=False`` とし、``status_message`` に終了コードを入れる。
    """
    info = get_auth_status(
        timeout=status_timeout,
        cli_path=cli_path,
        cli_url=cli_url,
    )
    if info.is_authenticated or not interactive:
        return info

    if cli_url:
        return AuthInfo(
            is_authenticated=False,
            status_message="external Copilot CLI server requires server-side authentication",
        )
    rc = run_login(host=host, binary=cli_path, timeout=login_timeout)
    if rc != 0:
        return AuthInfo(
            is_authenticated=False,
            status_message=f"copilot login exited with {rc}",
        )
    return get_auth_status(
        timeout=status_timeout,
        cli_path=cli_path,
        cli_url=cli_url,
    )


# ---------------------------------------------------------------------------
# ログイン起動
# ---------------------------------------------------------------------------


def find_copilot_binary() -> Optional[str]:
    """SDK実セッションと同じ解決順でCopilot CLI runtimeを返す。"""
    configured = os.environ.get("COPILOT_CLI_PATH")
    if configured:
        return configured

    try:
        from copilot._cli_download import get_cached_cli_path
    except ImportError:
        return None
    try:
        return get_cached_cli_path()
    except Exception:
        return None


def run_login(
    host: str = "https://github.com",
    *,
    binary: Optional[str] = None,
    timeout: Optional[float] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> int:
    """`copilot login` を起動して OAuth Device Flow を実行する。

    対話的にユーザー確認が必要なため、本関数は同期 (foreground) 実行する。
    GUI から呼ぶ場合はワーカースレッドに退避すること。

    Args:
        host: GitHub ホスト URL。GHEC データレジデンシーのみ変更する。
        binary: copilot 実行ファイル絶対パス (テスト差し替え用)。
        timeout: サブプロセスタイムアウト秒。None で無制限。
        on_output: 指定時、サブプロセス出力を 1 行ずつコールバックへ転送する
            (改行は除去済み)。同時に親プロセス stdout にもエコーする。
            None の場合は従来通り親プロセスに出力を継承する。

    Returns:
        サブプロセスの終了コード (0 = 成功)。

    Raises:
        AuthError: copilot 実行ファイルが見つからない場合。
        subprocess.TimeoutExpired: タイムアウト超過。
    """
    exe = binary or find_copilot_binary()
    if not exe:
        raise AuthError(
            "copilot 実行ファイルが見つかりません。github-copilot-sdk が"
            "正しくインストールされているか確認してください。"
        )

    cmd = [exe, "login"]
    if host and host != "https://github.com":
        cmd.extend(["--host", host])

    if on_output is None:
        completed = subprocess.run(cmd, timeout=timeout)
        return completed.returncode

    # on_output 指定時: Popen で stdout/stderr をパイプし行単位で転送する。
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    deadline = None if timeout is None else time.monotonic() + timeout
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            stripped = line.rstrip("\r\n")
            try:
                on_output(stripped)
            except Exception:
                pass
            # 親プロセス stdout にもエコー (既存ターミナル動作維持)
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                pass
            if deadline is not None and time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                _t: float = float(timeout) if timeout is not None else 0.0
                raise subprocess.TimeoutExpired(cmd, _t)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    remaining = None
    if deadline is not None:
        remaining = max(0.0, deadline - time.monotonic())
    rc = proc.wait(timeout=remaining)
    return rc
