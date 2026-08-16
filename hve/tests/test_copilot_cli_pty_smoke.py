"""hve/tests/test_copilot_cli_pty_smoke.py — 対話 CLI 起動境界の実 PTY smoke（FR-GUI-10）。

認証・モデル呼び出し・プロンプト送信は行わない。解決済み `copilot` 実行ファイルが
実 PTY 上で起動して終了できること、および引数がシェル解釈されずリストのまま渡ることを
Windows / macOS / Linux で確認する。Windows では `copilot` の実体が `.CMD` / `.BAT` の
シムになり得るため、この 2 点がプラットフォーム依存の主なリスクとなる。

PySide6 に依存しない（`hve.gui.pty_backend` と `hve.gui.copilot_cli_bridge` は
いずれも stdlib のみに依存する）。CI の `gui-pty-tests` job は PTY backend と
`copilot` の解決を fail-closed で確認したうえで skip 0 件を要求する。
"""

from __future__ import annotations

import re
import sys
import time
from typing import List

import pytest

from hve.gui import pty_backend
from hve.gui.copilot_cli_bridge import CopilotCliBridge

_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

pty_required = pytest.mark.skipif(
    not pty_backend.is_pty_available(),
    reason="PTY backend (pywinpty/ptyprocess) not installed",
)

_COPILOT_BINARY = CopilotCliBridge.find_binary()

copilot_required = pytest.mark.skipif(
    not _COPILOT_BINARY,
    reason="GitHub Copilot CLI is not resolvable (setup-hve installs it)",
)


def _read_until_exit(session: pty_backend.PtySession, timeout: float = 60.0) -> bytes:
    """子プロセスが終了し、残バッファが空になるまで読み続ける。"""
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while time.monotonic() < deadline:
        chunk = session.read_nowait(4096)
        if chunk:
            buffer.extend(chunk)
            continue
        if not session.is_alive():
            tail = session.read_nowait(4096)
            if tail:
                buffer.extend(tail)
                continue
            break
        time.sleep(0.05)
    return bytes(buffer)


@pty_required
@copilot_required
def test_resolved_copilot_binary_reports_version_through_a_real_pty() -> None:
    """解決済み CLI が実 PTY 上で起動し、版を出力して終了する。

    `--no-auto-update` を付けるのは、オンライン更新チェックが「最新利用可能版」を
    返して pin 版との突合を壊すため（FR-MODEL-07 と同じ理由）。
    """
    argv: List[str] = [str(_COPILOT_BINARY), "--no-auto-update", "--version"]
    session = pty_backend.spawn(argv)
    try:
        output = _read_until_exit(session)
    finally:
        session.close(grace_seconds=1.0)

    assert not session.is_alive()
    text = output.decode("utf-8", errors="replace")
    # ブランド文字列は将来の文言変更で壊れるため、版を返したことだけを見る。
    assert _VERSION_RE.search(text), f"unexpected copilot --version output: {text!r}"


@pty_required
def test_arguments_are_passed_as_a_list_without_shell_interpretation() -> None:
    """引数はリストのまま渡り、シェルメタ文字が解釈されない。

    対話プロンプトは `-i <prompt>` として 1 引数で渡すため、Windows のシム経由でも
    `&` / `|` などが再解釈されないことが前提になる。
    """
    payload = "stop using Synapse & echo pwned"
    argv = [sys.executable, "-c", "import sys; print(sys.argv[1])", payload]
    session = pty_backend.spawn(argv)
    try:
        output = _read_until_exit(session, timeout=30.0)
    finally:
        session.close(grace_seconds=1.0)

    # 分割されればリテラルの payload は現れず、実行されれば分割されている。
    assert payload in output.decode("utf-8", errors="replace")
