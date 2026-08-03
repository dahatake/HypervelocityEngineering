from __future__ import annotations

import sys
import types

import pytest

from hve import copilot_client_factory as factory
from hve.copilot_client_factory import create_copilot_client


class _FakeRuntimeConnection:
    @staticmethod
    def for_stdio(*, path=None, args=()):
        return {"kind": "stdio", "path": path, "args": tuple(args)}

    @staticmethod
    def for_uri(url, *, connection_token=None):
        return {"kind": "uri", "url": url, "connection_token": connection_token}


class _FakeCopilotClient:
    instances: list["_FakeCopilotClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)


def _install_fake_copilot(monkeypatch):
    _FakeCopilotClient.instances.clear()
    fake = types.ModuleType("copilot")
    fake.CopilotClient = _FakeCopilotClient
    fake.RuntimeConnection = _FakeRuntimeConnection
    monkeypatch.setitem(sys.modules, "copilot", fake)
    monkeypatch.setattr(factory, "_require_pwsh7_on_windows", lambda: "C:/pwsh.exe")
    return fake


def test_create_client_uses_stdio_connection(monkeypatch):
    _install_fake_copilot(monkeypatch)

    client = create_copilot_client(
        cli_path="C:/bin/copilot.exe",
        github_token="token",
        log_level="debug",
        cli_args=["--log-dir=tmp"],
        working_directory="C:/repo",
        env={"A": "B"},
    )

    assert client.kwargs == {
        "connection": {
            "kind": "stdio",
            "path": "C:/bin/copilot.exe",
            "args": ("--log-dir=tmp",),
        },
        "log_level": "debug",
        "github_token": "token",
        "working_directory": "C:/repo",
        "env": {"A": "B"},
    }


def test_create_client_uses_uri_connection_without_local_auth_options(monkeypatch):
    _install_fake_copilot(monkeypatch)

    client = create_copilot_client(
        cli_url="localhost:4321",
        github_token="token",
        cli_path="ignored",
        cli_args=["ignored"],
        working_directory="ignored",
        env={"IGNORED": "1"},
    )

    assert client.kwargs == {
        "connection": {
            "kind": "uri",
            "url": "localhost:4321",
            "connection_token": None,
        },
        "log_level": "info",
    }


def test_create_client_supports_legacy_config_shaped_test_double(monkeypatch):
    calls = {}

    class _LegacyClient:
        def __init__(self, config=None):
            self.config = config

    class _SubprocessConfig:
        def __init__(self, **kwargs):
            calls["subprocess"] = kwargs

    fake = types.ModuleType("copilot")
    fake.CopilotClient = _LegacyClient
    fake.SubprocessConfig = _SubprocessConfig
    monkeypatch.setitem(sys.modules, "copilot", fake)
    monkeypatch.setattr(factory, "_require_pwsh7_on_windows", lambda: "C:/pwsh.exe")

    client = create_copilot_client(
        cli_path="copilot",
        github_token="token",
        log_level="debug",
        cli_args=["--x"],
    )

    assert isinstance(client, _LegacyClient)
    assert calls["subprocess"] == {
        "cli_path": "copilot",
        "github_token": "token",
        "log_level": "debug",
        "cli_args": ("--x",),
    }


def test_legacy_client_rejects_required_runtime_environment(monkeypatch):
    class _LegacyClient:
        pass

    fake = types.ModuleType("copilot")
    fake.CopilotClient = _LegacyClient
    monkeypatch.setitem(sys.modules, "copilot", fake)
    monkeypatch.setattr(factory, "_require_pwsh7_on_windows", lambda: "C:/pwsh.exe")

    with pytest.raises(RuntimeError, match="cannot inject"):
        create_copilot_client(env={"RESOURCE_GROUP": "formal-value"})


def test_create_client_does_not_retry_legacy_import_when_sdk_is_missing(
    monkeypatch,
):
    """残存copilot.sessionがあってもparent SDK不在はImportErrorのまま返す。"""
    monkeypatch.setitem(sys.modules, "copilot", None)
    monkeypatch.setitem(sys.modules, "copilot.session", types.ModuleType("copilot.session"))

    try:
        create_copilot_client()
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("missing Copilot SDK must raise ModuleNotFoundError")


def test_windows_local_runtime_requires_pwsh7(monkeypatch) -> None:
    factory._require_pwsh7_on_windows.cache_clear()
    monkeypatch.setattr(factory.sys, "platform", "win32")
    monkeypatch.setattr(factory.shutil, "which", lambda name: "C:/bin/pwsh.exe")
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(factory.subprocess, "run", fake_run)

    assert factory._require_pwsh7_on_windows() == "C:/bin/pwsh.exe"
    assert calls == [[
        "C:/bin/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-Command",
        "if ($PSVersionTable.PSEdition -eq 'Core' -and $PSVersionTable.PSVersion.Major -ge 7) { exit 0 } else { exit 1 }",
    ]]

    factory._require_pwsh7_on_windows.cache_clear()


def test_windows_local_runtime_never_falls_back_to_powershell_51(monkeypatch) -> None:
    factory._require_pwsh7_on_windows.cache_clear()
    monkeypatch.setattr(factory.sys, "platform", "win32")
    monkeypatch.setattr(factory.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="Windows PowerShell 5.1 fallback is prohibited"):
        factory._require_pwsh7_on_windows()

    factory._require_pwsh7_on_windows.cache_clear()