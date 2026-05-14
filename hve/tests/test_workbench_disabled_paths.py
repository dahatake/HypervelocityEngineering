"""test_workbench_disabled_paths.py — Console.workbench_enabled 判定のテスト。"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from hve.console import Console


def _make_console(**kwargs):
    return Console(**kwargs)


def test_enabled_when_tty_and_no_flags() -> None:
    c = _make_console(verbosity=2)
    with patch.object(c, "_is_tty", True), patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HVE_NO_WORKBENCH", None)
        assert c.workbench_enabled is True


def test_disabled_when_not_tty() -> None:
    c = _make_console(verbosity=2)
    with patch.object(c, "_is_tty", False):
        assert c.workbench_enabled is False


def test_disabled_when_quiet() -> None:
    c = _make_console(verbosity=0)
    with patch.object(c, "_is_tty", True):
        assert c.workbench_enabled is False


def test_disabled_when_final_only() -> None:
    c = _make_console(final_only=True)
    with patch.object(c, "_is_tty", True):
        assert c.workbench_enabled is False


def test_disabled_when_env_set() -> None:
    c = _make_console(verbosity=2)
    with patch.object(c, "_is_tty", True), patch.dict(
        os.environ, {"HVE_NO_WORKBENCH": "1"}
    ):
        assert c.workbench_enabled is False


def test_attach_and_detach_workbench() -> None:
    c = _make_console(verbosity=2)

    class _Stub:
        pass

    wb = _Stub()
    original_style = c.s
    c.attach_workbench(wb)
    assert c._workbench is wb
    # _Style が差し替えられている
    assert c.s is not original_style

    c.detach_workbench()
    assert c._workbench is None
    # _Style が復元されている
    assert c.s is original_style


def test_attach_idempotent_detach() -> None:
    c = _make_console(verbosity=2)
    # attach せずに detach しても例外にならない
    c.detach_workbench()
    assert c._workbench is None
