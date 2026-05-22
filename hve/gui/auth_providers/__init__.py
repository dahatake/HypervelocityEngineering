"""hve.gui.auth_providers — Plugin / MCP Server 認証プロバイダ基盤。

設計:
    - 各 Plugin / MCP Server を 1 つの ``AuthProvider`` 実装として表現する。
    - ``check_status()`` は同期・短時間 (タイムアウト付き) で現在の認証状態を返す。
    - ``authenticate()`` は同期だがブロッキングする可能性があるためワーカースレッド前提。
    - GUI 側 (``PluginAuthDialog`` / ``AuthMonitor``) はこのプロトコルにのみ依存する。

依存:
    - 既存 ``hve.auth`` / ``hve.workiq`` / ``hve.__main__._load_mcp_config`` を内部で利用する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "AuthState",
    "AuthResult",
    "AuthStatus",
    "ProgressCallback",
    "AuthProvider",
    "InteractivePlan",
    "InteractiveAuthProvider",
    "provider_supports_interactive",
    "provider_is_required",
]


class AuthState(str, Enum):
    """プロバイダの認証状態。

    値:
        NOT_APPLICABLE: 設定されておらず本セッションでは対象外。
        UNKNOWN:        未確認 (初期状態 / エラー)。
        NOT_AUTHENTICATED: 未認証。
        AUTHENTICATED:  認証済み。
        EXPIRED:        トークン失効。再認証が必要。
        CHECKING:       状態確認処理が進行中。
    """

    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    NOT_AUTHENTICATED = "not_authenticated"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    CHECKING = "checking"

    @property
    def is_ok(self) -> bool:
        """認証が完了している (= ワークフロー実行可能) 状態か。"""
        return self is AuthState.AUTHENTICATED


@dataclass(frozen=True)
class AuthStatus:
    """``check_status()`` の戻り値。"""

    state: AuthState
    detail: Optional[str] = None
    expiry_hint: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthResult:
    """``authenticate()`` の戻り値。"""

    success: bool
    state: AuthState
    message: Optional[str] = None
    expiry_hint: Optional[datetime] = None


# 進捗通知コールバック。authenticate() 内から任意回数呼ばれてよい。
ProgressCallback = Callable[[str], None]


@runtime_checkable
class AuthProvider(Protocol):
    """Plugin / MCP Server 認証プロバイダの最小インターフェース。

    実装クラスは以下属性を提供する:
        id            プロバイダ識別子 (例: ``"github"``, ``"mcp:foo"``)。
        display_name  UI 表示名。
        required      ワークフロー実行に必須か (False ならスキップ可)。
    """

    id: str
    display_name: str
    required: bool

    def is_applicable(self, settings: Dict[str, Any]) -> bool:
        """設定上、本プロバイダが対象になるか。"""
        ...

    def check_status(self, *, timeout: float = 15.0) -> AuthStatus:
        """現在の認証状態を取得する (短時間で完了する想定)。"""
        ...

    def authenticate(
        self,
        *,
        timeout: float = 600.0,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> AuthResult:
        """認証フローを実行する (ブロッキング可)。

        Args:
            timeout: 全体タイムアウト秒。
            on_progress: 進捗ログ通知 (任意)。
            cancel_check: True を返したらキャンセル扱いで早期復帰する関数 (任意)。
        """
        ...


# ---------------------------------------------------------------------------
# インタラクティブ認証拡張 (T05)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InteractivePlan:
    """PTY + xterm.js ベースのインタラクティブ認証フロー実行計画。

    GUI 側 (T06 ``PtyAuthSessionWidget``) は本オブジェクトを上から順に処理する:
        1. ``pre_commands`` を 1 つずつ ``PtyAuthController`` で実行。
        2. 任意で ``main_command`` を実行。
        3. ``notes_md`` は実行前にユーザーへ表示する案内文 (Markdown)。

    Attributes:
        display_name: UI 上の表示名。
        pre_commands: 前提コマンド (例: ``az login`` / ``gh auth login``)。
        main_command: 主コマンド (任意)。設定なら最後に走らせる。
        notes_md: 実行前に表示する Markdown 注意書き (任意)。
        timeout_total: フロー全体のタイムアウト秒 (UI 側の安全網)。
        source_manifest_id: 由来 manifest の id (デバッグ用、任意)。
    """

    display_name: str
    pre_commands: List[Any] = field(default_factory=list)  # list[CommandSpec]
    main_command: Optional[Any] = None  # Optional[CommandSpec]
    notes_md: Optional[str] = None
    timeout_total: float = 900.0
    source_manifest_id: Optional[str] = None


@runtime_checkable
class InteractiveAuthProvider(Protocol):
    """``AuthProvider`` をインタラクティブ認証で拡張する任意プロトコル。

    実装は必須ではない。実装する場合は ``supports_interactive=True`` を返し、
    ``build_interactive_plan(settings)`` で ``InteractivePlan`` を返すこと。
    """

    supports_interactive: bool

    def build_interactive_plan(
        self, settings: Dict[str, Any]
    ) -> Optional[InteractivePlan]:
        ...


def provider_supports_interactive(provider: Any) -> bool:
    """``provider`` がインタラクティブ認証フローを提供できるかを判定する。

    新旧プロバイダの混在環境で安全に判定するためのヘルパ。属性存在チェックと
    値の真偽の両方を見る。
    """
    return bool(getattr(provider, "supports_interactive", False)) and callable(
        getattr(provider, "build_interactive_plan", None)
    )


def provider_is_required(provider: Any, settings: Dict[str, Any]) -> bool:
    """``provider`` が当該 ``settings`` のもとで認証必須かを判定する。

    Wave 1〜5 (T4/D1): プロバイダ実装は ``is_required(settings) -> bool`` を提供
    することが推奨されるが、後方互換のため未実装プロバイダは旧 ``required``
    属性 (固定 bool) にフォールバックする。
    """
    fn = getattr(provider, "is_required", None)
    if callable(fn):
        try:
            return bool(fn(settings))
        except Exception:  # pragma: no cover - 安全網
            return bool(getattr(provider, "required", False))
    return bool(getattr(provider, "required", False))
