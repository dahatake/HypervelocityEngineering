"""tests/test_cli_login.py — `hve login` サブコマンドの統合テスト"""

from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from hve.__main__ import _build_parser, _cmd_login
from hve.auth import AuthError, AuthInfo
from hve.models_api import ModelsAPIError


def _parse(argv):
    return _build_parser().parse_args(argv)


# =====================================================================
# argparse
# =====================================================================


class TestLoginParser:
    def test_basic(self):
        ns = _parse(["login"])
        assert ns.command == "login"
        assert ns.host == "https://github.com"
        assert ns.skip_fetch is False
        assert ns.status is False

    def test_host_override(self):
        ns = _parse(["login", "--host", "https://example.ghe.com"])
        assert ns.host == "https://example.ghe.com"

    def test_skip_fetch_flag(self):
        ns = _parse(["login", "--skip-fetch"])
        assert ns.skip_fetch is True

    def test_status_flag(self):
        ns = _parse(["login", "--status"])
        assert ns.status is True


# =====================================================================
# _cmd_login: --status
# =====================================================================


class TestStatusMode:
    def test_status_authenticated(self, isolated_cache_env, capsys):
        info = AuthInfo(is_authenticated=True, login="alice", copilot_plan="pro")
        with patch("hve.auth.get_auth_status", return_value=info):
            rc = _cmd_login(_parse(["login", "--status"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "alice" in out
        assert "pro" in out

    def test_status_unauthenticated(self, isolated_cache_env, capsys):
        info = AuthInfo(is_authenticated=False, status_message="not logged in")
        with patch("hve.auth.get_auth_status", return_value=info):
            rc = _cmd_login(_parse(["login", "--status"]))
        out = capsys.readouterr().out
        assert rc == 1
        assert "未ログイン" in out
        assert "not logged in" in out

    def test_status_shows_cache_info(self, isolated_cache_env, capsys):
        from hve import models_cache

        models_cache.save(["m1", "m2"], now=1000.0)
        info = AuthInfo(is_authenticated=True, login="bob")
        with patch("hve.auth.get_auth_status", return_value=info):
            _cmd_login(_parse(["login", "--status"]))
        out = capsys.readouterr().out
        assert "2 件" in out


# =====================================================================
# _cmd_login: 通常ログイン
# =====================================================================


class TestNormalLogin:
    def test_success_fetches_and_caches(self, isolated_cache_env, capsys):
        from hve import models_cache

        info = AuthInfo(is_authenticated=True, login="alice")
        with patch("hve.auth.run_login", return_value=0), \
             patch("hve.auth.get_auth_status", return_value=info), \
             patch("hve.models_api.fetch_models", return_value=["a", "b", "c"]):
            rc = _cmd_login(_parse(["login"]))
        assert rc == 0
        cached = models_cache.load()
        assert cached is not None
        assert cached.models == ["a", "b", "c"]

    def test_skip_fetch_skips_cache_save(self, isolated_cache_env):
        from hve import models_cache

        info = AuthInfo(is_authenticated=True, login="alice")
        with patch("hve.auth.run_login", return_value=0), \
             patch("hve.auth.get_auth_status", return_value=info), \
             patch("hve.models_api.fetch_models") as mock_fetch:
            rc = _cmd_login(_parse(["login", "--skip-fetch"]))
        assert rc == 0
        mock_fetch.assert_not_called()
        assert models_cache.load() is None

    def test_run_login_failure_returns_nonzero(self, isolated_cache_env):
        with patch("hve.auth.run_login", return_value=2):
            rc = _cmd_login(_parse(["login"]))
        assert rc == 2

    def test_auth_error_returns_2(self, isolated_cache_env, capsys):
        with patch("hve.auth.run_login", side_effect=AuthError("no binary")):
            rc = _cmd_login(_parse(["login"]))
        assert rc == 2

    def test_fetch_failure_returns_0_with_warning(self, isolated_cache_env, capsys):
        info = AuthInfo(is_authenticated=True, login="alice")
        with patch("hve.auth.run_login", return_value=0), \
             patch("hve.auth.get_auth_status", return_value=info), \
             patch("hve.models_api.fetch_models", side_effect=ModelsAPIError("net error")):
            rc = _cmd_login(_parse(["login"]))
        # ログイン自体は成功しているため非エラー
        assert rc == 0

    def test_passes_host_to_run_login(self, isolated_cache_env):
        info = AuthInfo(is_authenticated=True, login="alice")
        with patch("hve.auth.run_login", return_value=0) as mock_login, \
             patch("hve.auth.get_auth_status", return_value=info), \
             patch("hve.models_api.fetch_models", return_value=["a"]):
            _cmd_login(_parse(["login", "--host", "https://example.ghe.com"]))
        mock_login.assert_called_once()
        assert mock_login.call_args.kwargs.get("host") == "https://example.ghe.com"

    def test_empty_models_does_not_save_cache(self, isolated_cache_env):
        from hve import models_cache

        info = AuthInfo(is_authenticated=True, login="alice")
        with patch("hve.auth.run_login", return_value=0), \
             patch("hve.auth.get_auth_status", return_value=info), \
             patch("hve.models_api.fetch_models", return_value=[]):
            rc = _cmd_login(_parse(["login"]))
        assert rc == 0
        assert models_cache.load() is None


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def isolated_cache_env(tmp_path, monkeypatch):
    """テスト間でキャッシュファイルを分離する。"""
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", str(tmp_path / "models.json"))
    yield tmp_path
