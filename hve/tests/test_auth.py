"""tests/test_auth.py — hve.auth のユニットテスト

SDK 通信とサブプロセス起動は unittest.mock で差し替え、ロジック部分を検証する。
"""

from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from hve.auth import (
    AuthError,
    AuthInfo,
    TOKEN_ENV_VARS,
    find_copilot_binary,
    get_auth_status,
    is_authenticated,
    resolve_token_env,
    run_login,
)


# =====================================================================
# resolve_token_env
# =====================================================================


class TestResolveTokenEnv:
    def test_returns_none_when_all_empty(self, monkeypatch):
        for name in TOKEN_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        assert resolve_token_env() is None

    def test_priority_copilot_first(self, monkeypatch):
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "tok-copilot")
        monkeypatch.setenv("GH_TOKEN", "tok-gh")
        monkeypatch.setenv("GITHUB_TOKEN", "tok-github")
        assert resolve_token_env() == "tok-copilot"

    def test_priority_gh_then_github(self, monkeypatch):
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", "tok-gh")
        monkeypatch.setenv("GITHUB_TOKEN", "tok-github")
        assert resolve_token_env() == "tok-gh"

    def test_fallback_to_github_token(self, monkeypatch):
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "tok-github")
        assert resolve_token_env() == "tok-github"

    def test_empty_string_is_skipped(self, monkeypatch):
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "")
        monkeypatch.setenv("GH_TOKEN", "tok-gh")
        assert resolve_token_env() == "tok-gh"


# =====================================================================
# get_auth_status / is_authenticated
# =====================================================================


def _make_fake_client(*, is_auth=True, login="alice", plan="pro", host="github.com",
                     status_message=None, start_raises=None, status_raises=None,
                     attr_style="camel"):
    """SDK CopilotClient を模倣する async モック生成ヘルパー。

    attr_style:
      - "camel": 実 SDK と同じ camelCase 属性 (isAuthenticated / statusMessage)
      - "snake": 旧名 snake_case 属性 (is_authenticated / status_message) のみ。
                fallback 経路の検証に使う。
      - "both" : 両方の属性を持つ（camelCase が優先されることの検証用）。
    """
    client = MagicMock()

    async def _start():
        if start_raises:
            raise start_raises

    async def _stop():
        return None

    async def _get_auth_status():
        if status_raises:
            raise status_raises
        # MagicMock は未指定属性を truthy 値で自動生成してしまうため SimpleNamespace を使う。
        attrs = {"login": login, "copilot_plan": plan, "host": host}
        if attr_style in ("camel", "both"):
            attrs["isAuthenticated"] = is_auth
            attrs["statusMessage"] = status_message
        if attr_style in ("snake", "both"):
            attrs["is_authenticated"] = is_auth
            attrs["status_message"] = status_message
        return SimpleNamespace(**attrs)

    client.start = _start
    client.stop = _stop
    client.get_auth_status = _get_auth_status
    return client


class TestGetAuthStatus:
    def test_authenticated_user(self):
        fake = _make_fake_client(is_auth=True, login="alice", plan="pro")
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is True
        assert info.login == "alice"
        assert info.copilot_plan == "pro"

    def test_unauthenticated_user(self):
        fake = _make_fake_client(is_auth=False, login=None, plan=None)
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is False
        assert info.login is None

    def test_sdk_runtime_error_is_swallowed(self):
        fake = _make_fake_client(start_raises=RuntimeError("boom"))
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is False
        assert info.status_message is not None
        assert "RuntimeError" in info.status_message

    def test_timeout_returns_unauthenticated(self):
        async def _hang():
            await asyncio.sleep(10)

        async def _noop():
            return None

        fake = MagicMock()
        fake.start = _hang
        fake.stop = _noop
        fake.get_auth_status = _noop

        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=0.1)
        assert info.is_authenticated is False
        assert info.status_message is not None
        assert "timeout" in info.status_message.lower()

    def test_import_error_raises_auth_error(self, monkeypatch):
        import sys

        # copilot モジュール import を失敗させる
        monkeypatch.setitem(sys.modules, "copilot", None)
        with pytest.raises(AuthError):
            get_auth_status(timeout=1.0)

    # ------------------------------------------------------------------
    # SDK 属性名互換テスト (camelCase / snake_case fallback)
    # 実 SDK GetAuthStatusResponse は camelCase (isAuthenticated / statusMessage)
    # を返す。HVE 側は camelCase を優先し、snake_case を fallback として参照する。
    # ------------------------------------------------------------------
    def test_camelcase_attrs_are_read(self):
        """実 SDK と同形式 (camelCase) のレスポンスから正しく読み取れる。"""
        fake = _make_fake_client(
            is_auth=True, login="alice", status_message="ok", attr_style="camel"
        )
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is True
        assert info.login == "alice"
        assert info.status_message == "ok"

    def test_camelcase_false_is_respected(self):
        """camelCase で isAuthenticated=False が False として伝わる (MagicMock 退行回帰)。"""
        fake = _make_fake_client(
            is_auth=False, login=None, status_message="not signed in",
            attr_style="camel",
        )
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is False
        assert info.status_message == "not signed in"

    def test_snake_case_fallback(self):
        """snake_case のみ持つレスポンス (旧 SDK 想定) でも fallback で読み取れる。"""
        fake = _make_fake_client(
            is_auth=True, login="bob", status_message="legacy",
            attr_style="snake",
        )
        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is True
        assert info.login == "bob"
        assert info.status_message == "legacy"

    def test_camelcase_takes_precedence_over_snake(self):
        """両方持つ場合 camelCase が優先される。"""
        # camelCase=True, snake_case=False という不整合状態を直接構築
        s = SimpleNamespace(
            isAuthenticated=True,
            is_authenticated=False,
            statusMessage="camel",
            status_message="snake",
            login="x",
            copilot_plan=None,
            host=None,
        )

        async def _start(): return None
        async def _stop(): return None
        async def _get(): return s

        fake = MagicMock()
        fake.start = _start
        fake.stop = _stop
        fake.get_auth_status = _get

        with patch("copilot.CopilotClient", return_value=fake):
            info = get_auth_status(timeout=5.0)
        assert info.is_authenticated is True
        assert info.status_message == "camel"


class TestIsAuthenticated:
    def test_true(self):
        fake = _make_fake_client(is_auth=True)
        with patch("copilot.CopilotClient", return_value=fake):
            assert is_authenticated(timeout=5.0) is True

    def test_false(self):
        fake = _make_fake_client(is_auth=False)
        with patch("copilot.CopilotClient", return_value=fake):
            assert is_authenticated(timeout=5.0) is False


# =====================================================================
# find_copilot_binary
# =====================================================================


class TestFindCopilotBinary:
    def test_returns_path_when_bundled_exists(self):
        # SDK が実際に同梱しているため非 None で返るはず
        path = find_copilot_binary()
        assert path is not None
        assert "copilot" in path.lower()

    def test_falls_back_to_which_when_bundle_missing(self, monkeypatch, tmp_path):
        # copilot.bin の __file__ を非存在パスに差し替えて同梱バイナリ未検出を再現
        import copilot.bin as real_bin

        fake_bin = MagicMock()
        fake_bin.__file__ = str(tmp_path / "nonexistent" / "__init__.py")
        monkeypatch.setattr("copilot.bin", fake_bin, raising=False)
        # parent module の属性も差し替え (import copilot.bin as _bin は親属性経由)
        import copilot as copilot_pkg

        monkeypatch.setattr(copilot_pkg, "bin", fake_bin)
        with patch("shutil.which", return_value="/usr/bin/copilot"):
            result = find_copilot_binary()
        assert result == "/usr/bin/copilot"


# =====================================================================
# run_login
# =====================================================================


class TestRunLogin:
    def test_invokes_copilot_login(self):
        with patch("hve.auth.find_copilot_binary", return_value="/tmp/copilot"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0
                )
                rc = run_login()
        assert rc == 0
        called_args = mock_run.call_args[0][0]
        assert called_args[0] == "/tmp/copilot"
        assert called_args[1] == "login"
        assert "--host" not in called_args  # default host は省略

    def test_passes_host_when_non_default(self):
        with patch("hve.auth.find_copilot_binary", return_value="/tmp/copilot"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0
                )
                run_login(host="https://example.ghe.com")
        called_args = mock_run.call_args[0][0]
        assert "--host" in called_args
        assert "https://example.ghe.com" in called_args

    def test_raises_when_binary_missing(self):
        with patch("hve.auth.find_copilot_binary", return_value=None):
            with pytest.raises(AuthError):
                run_login()

    def test_explicit_binary_overrides_lookup(self):
        with patch("hve.auth.find_copilot_binary", return_value=None):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0
                )
                rc = run_login(binary="/custom/copilot")
        assert rc == 0
        assert mock_run.call_args[0][0][0] == "/custom/copilot"

    def test_nonzero_return_code_propagated(self):
        with patch("hve.auth.find_copilot_binary", return_value="/tmp/copilot"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=2
                )
                rc = run_login()
        assert rc == 2


# =====================================================================
# AuthInfo
# =====================================================================


class TestAuthInfo:
    def test_is_frozen(self):
        info = AuthInfo(is_authenticated=True, login="alice")
        with pytest.raises(Exception):
            info.login = "bob"  # type: ignore[misc]

    def test_defaults(self):
        info = AuthInfo(is_authenticated=False)
        assert info.login is None
        assert info.copilot_plan is None
        assert info.host is None
        assert info.status_message is None
