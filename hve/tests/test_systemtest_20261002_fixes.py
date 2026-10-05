"""CLI / Prompt システムテスト（2026-10-01 22:35）の検出事項 N-01〜N-08 の回帰テスト。

N-01（resume 親の heartbeat）は test_resume_cli.py、N-02（reuse-session の deadline）は
test_runner_resume.py、N-07（料金表）は tests/pricing/test_pricing_crawler.py に置く。
"""

from __future__ import annotations

import builtins
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hve.__main__ as hve_main
from hve.console import Console

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# N-03 / N-06: CTRL_BREAK_EVENT を SIGINT と同じ中断経路へ変換する
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="CTRL_BREAK_EVENT is Windows only")
def test_ctrl_break_runs_finally_blocks_and_exits_with_one(tmp_path: Path) -> None:
    import signal

    marker = tmp_path / "marker.txt"
    script = tmp_path / "child.py"
    script.write_text(
        textwrap.dedent(
            """
            import asyncio, pathlib, sys
            from hve.__main__ import _install_windows_break_as_interrupt

            marker = pathlib.Path(sys.argv[1])

            async def main():
                try:
                    marker.write_text("started")
                    await asyncio.sleep(60)
                finally:
                    marker.write_text("finally")

            _install_windows_break_as_interrupt()
            try:
                asyncio.run(main())
            except KeyboardInterrupt:
                sys.exit(1)
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [sys.executable, str(script), str(marker)],
        cwd=_REPO_ROOT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if marker.exists() and marker.read_text() == "started":
                break
            time.sleep(0.1)
        else:
            pytest.fail("child did not start")
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        assert proc.wait(timeout=30) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
    assert marker.read_text() == "finally"


def test_break_handler_installation_is_a_noop_without_sigbreak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    fake_signal = SimpleNamespace(signal=lambda *a: calls.append(a), SIGINT=2)
    monkeypatch.setattr(hve_main, "signal", fake_signal)

    hve_main._install_windows_break_as_interrupt()

    assert calls == []


# ---------------------------------------------------------------------------
# N-04: stdin が EOF のときの wizard
# ---------------------------------------------------------------------------

def _raise_eof(*_args: Any, **_kwargs: Any) -> str:
    raise EOFError


@pytest.mark.parametrize(
    "prompt",
    [
        lambda con: con.menu_select("選択", ["a", "b"], default_index=1),
        lambda con: con.prompt_input("対象業務名", required=True),
        lambda con: con.prompt_yes_no("実行しますか？", default=True),
        lambda con: con.prompt_multi_select("複数選択", ["a", "b"]),
    ],
)
def test_console_records_stdin_eof(
    monkeypatch: pytest.MonkeyPatch, prompt: Any
) -> None:
    con = Console(verbose=False, quiet=True)
    assert con.input_eof is False
    monkeypatch.setattr(builtins, "input", _raise_eof)

    prompt(con)

    assert con.input_eof is True


def test_console_keyboard_interrupt_is_not_recorded_as_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    con = Console(verbose=False, quiet=True)

    def interrupt(*_args: Any, **_kwargs: Any) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", interrupt)
    con.prompt_input("x")

    assert con.input_eof is False


# ---------------------------------------------------------------------------
# N-05: qa-merge の統合ドキュメント生成
# ---------------------------------------------------------------------------

_QA_CONTENT = """\
# テスト質問票

**状態**: 回答待ち
**推論許可**: なし

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | 通信方式はどれか | A) REST / B) gRPC | A) REST | 習熟度 |
"""


class _FakeSession:
    def __init__(self, reply: Any, error: Exception | None) -> None:
        self.reply = reply
        self.error = error
        self.disconnected = False

    async def send_and_wait(self, prompt: str, **_kwargs: Any) -> Any:
        if self.error is not None:
            raise self.error
        return self.reply

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeClient:
    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        self.session = _FakeSession(reply, error)
        self.create_kwargs: dict[str, Any] = {}
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def create_session(self, **kwargs: Any) -> _FakeSession:
        self.create_kwargs = kwargs
        return self.session

    async def stop(self) -> None:
        self.stopped = True


def _run_qa_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, client: _FakeClient
) -> tuple[int, Path]:
    import hve.copilot_client_factory as factory
    from hve.qa_merger import QAMerger

    qa_file = tmp_path / "qa-sample.md"
    qa_file.write_text(_QA_CONTENT, encoding="utf-8")
    monkeypatch.setattr(factory, "create_copilot_client", lambda **_kwargs: client)
    code = hve_main.main(
        ["qa-merge", "--qa-file", str(qa_file), "--use-defaults", "--model", "Auto"]
    )
    return code, QAMerger.generate_consolidated_path(qa_file)


def _reply(text: str) -> Any:
    return SimpleNamespace(data=SimpleNamespace(content=text))


def test_qa_merge_consolidation_saves_document_and_closes_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _FakeClient(reply=_reply("# 統合ドキュメント\n本文"))

    code, consolidated = _run_qa_merge(monkeypatch, tmp_path, client)

    assert code == 0
    assert "統合ドキュメント" in consolidated.read_text(encoding="utf-8")
    assert client.started and client.stopped and client.session.disconnected
    assert callable(client.create_kwargs["on_permission_request"])
    assert "model" not in client.create_kwargs

def test_qa_merge_consolidation_failure_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _FakeClient(error=RuntimeError("model unavailable"))

    code, consolidated = _run_qa_merge(monkeypatch, tmp_path, client)

    assert code == 1
    assert not consolidated.exists()
    assert client.stopped and client.session.disconnected
    assert "統合ドキュメント生成に失敗" in capsys.readouterr().err


def test_qa_merge_empty_consolidation_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _FakeClient(reply=_reply("   "))

    code, consolidated = _run_qa_merge(monkeypatch, tmp_path, client)

    assert code == 1
    assert not consolidated.exists()


def test_qa_merge_skip_consistency_does_not_start_a_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hve.copilot_client_factory as factory

    qa_file = tmp_path / "qa-sample.md"
    qa_file.write_text(_QA_CONTENT, encoding="utf-8")

    def forbidden(**_kwargs: Any) -> Any:
        raise AssertionError("client must not be created")

    monkeypatch.setattr(factory, "create_copilot_client", forbidden)

    assert hve_main.main(
        ["qa-merge", "--qa-file", str(qa_file), "--use-defaults", "--skip-consistency"]
    ) == 0


# ---------------------------------------------------------------------------
# N-08: Skill は registry 定数を APP-ID として採用しない
# ---------------------------------------------------------------------------

def test_prompt_edition_skill_forbids_adopting_registry_constant_as_app_id() -> None:
    text = (_REPO_ROOT / ".github" / "skills" / "hve-prompt-edition" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "適当な APP-ID" in text
    assert "ASDW_DATA_DEPLOY_SUPPORTED_APP_ID" in text
    assert "確認なしに採用・使用可能な値として提示してはならない" in text
