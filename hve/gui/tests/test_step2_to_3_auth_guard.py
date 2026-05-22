"""hve.gui.tests.test_step2_to_3_auth_guard — T15/T16 (Wave 5).

Step 2 → Step 3 遷移時の認証ガードを構成する要素 (provider.is_required(settings) +
state チェック) の動作と、Microsoft Learn 用 manifest (`auth_required: false`) の
ロードを検証する。

設計判断: 完全な ``MainWindow`` インスタンス化は重い依存 (CopilotChatPanel, PTY 等)
を要するため、ガードを構成する以下 3 要素を分離して検証する:
    1. ``provider.is_required(settings)`` の動的判定
    2. ``AuthMonitor.required_provider_ids()`` の計算
    3. ``microsoft_learn.yml`` manifest の auth_required=false
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.auth_monitor import AuthMonitor  # noqa: E402
from hve.gui.auth_providers import AuthState, AuthStatus  # noqa: E402
from hve.gui.auth_providers.github_provider import GitHubProvider  # noqa: E402
from hve.gui.auth_providers.mcp_generic_provider import McpGenericProvider  # noqa: E402
from hve.gui.auth_providers.workiq_provider import WorkIQProvider  # noqa: E402
from hve.gui.auth_providers.manifests import load_manifest_for  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def _collect_missing(monitor: AuthMonitor) -> list[str]:
    """``_verify_required_auth_before_run`` 内のロジックを再現する。"""
    from hve.gui.auth_providers import provider_is_required

    settings = monitor.current_settings()
    missing = []
    for p in monitor.providers():
        if not provider_is_required(p, settings):
            continue
        if monitor.latest_state(p.id) is not AuthState.AUTHENTICATED:
            missing.append(p.display_name)
    return missing


# ---------------------------------------------------------------------------
# T16: ガードシナリオ
# ---------------------------------------------------------------------------
def test_workiq_on_and_unauthenticated_blocks() -> None:
    """Step 2 で workiq=True、Work IQ プロバイダ未認証 → ガードでブロック。"""
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    wq = WorkIQProvider()
    settings = {"options": {"workiq": True}}
    mon.set_providers([gh, wq], settings)
    # GitHub は認証済、Work IQ は未認証としてシミュレート
    mon._states = {
        "github": AuthState.AUTHENTICATED,
        "workiq": AuthState.NOT_AUTHENTICATED,
    }
    missing = _collect_missing(mon)
    assert "Microsoft Work IQ" in missing


def test_workiq_off_passes_even_when_workiq_unauthenticated() -> None:
    """Work IQ 設定 OFF なら、Work IQ 未認証でも素通り。"""
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    wq = WorkIQProvider()
    settings = {"options": {"workiq": False}}
    mon.set_providers([gh, wq], settings)
    mon._states = {
        "github": AuthState.AUTHENTICATED,
        "workiq": AuthState.NOT_AUTHENTICATED,
    }
    missing = _collect_missing(mon)
    assert missing == []


def test_azure_mcp_enabled_and_unauthenticated_blocks() -> None:
    """`mcp_enabled[azure]=True` かつ azure-mcp 未認証 → ガードでブロック。"""
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    azure = McpGenericProvider("azure", {})
    settings = {
        "options": {},
        "mcp_enabled": {"azure": True},
    }
    mon.set_providers([gh, azure], settings)
    mon._states = {
        "github": AuthState.AUTHENTICATED,
        "mcp:azure": AuthState.NOT_AUTHENTICATED,
    }
    missing = _collect_missing(mon)
    assert "MCP: azure" in missing


def test_microsoft_learn_enabled_passes_without_auth() -> None:
    """`mcp_enabled[microsoft-learn]=True` でも manifest.auth_required=false → 素通り。

    実 manifest ``microsoft_learn.yml`` を load_manifest_for 経由で利用する。
    """
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    ms_learn = McpGenericProvider("microsoft-learn", {})
    settings = {
        "options": {},
        "mcp_enabled": {"microsoft-learn": True},
    }
    mon.set_providers([gh, ms_learn], settings)
    mon._states = {
        "github": AuthState.AUTHENTICATED,
        "mcp:microsoft-learn": AuthState.NOT_AUTHENTICATED,
    }
    missing = _collect_missing(mon)
    assert missing == []


# ---------------------------------------------------------------------------
# T15: 起動時 GitHub Copilot 必須化 (ロジックレベル)
# ---------------------------------------------------------------------------
def test_github_always_required_at_startup() -> None:
    """GitHub Copilot は常に required (= 起動時モーダル発動条件) であること。"""
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    # 起動直後で settings は空、何も Step 2 で選択していない状態
    mon.set_providers([gh], {})
    # GitHub 未認証なら required_provider_ids に含まれる
    assert "github" in mon.required_provider_ids()


def test_github_authenticated_passes_startup_check() -> None:
    _ensure_app()
    mon = AuthMonitor()
    gh = GitHubProvider()
    mon.set_providers([gh], {})
    mon._states = {"github": AuthState.AUTHENTICATED}
    # ガードロジック: required かつ NOT AUTHENTICATED のものが無い
    assert _collect_missing(mon) == []


# ---------------------------------------------------------------------------
# Microsoft Learn manifest
# ---------------------------------------------------------------------------
def test_microsoft_learn_manifest_auth_required_false() -> None:
    """`microsoft_learn.yml` が ``auth_required: false`` で読み込まれること。"""
    manifest = load_manifest_for(
        provider_id="mcp:microsoft-learn",
        mcp_server_name="microsoft-learn",
    )
    assert manifest is not None
    assert manifest.auth_required is False


def test_default_manifest_auth_required_true() -> None:
    """`_default.yml` は ``auth_required: true`` で読み込まれること (安全側既定)。"""
    # 個別 manifest にマッチしないサーバ名を渡して _default にフォールバックさせる
    manifest = load_manifest_for(
        provider_id="mcp:some-unknown-server-xyz",
        mcp_server_name="some-unknown-server-xyz",
    )
    assert manifest is not None
    assert manifest.auth_required is True
