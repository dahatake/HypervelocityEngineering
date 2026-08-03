"""FR-GUI-04: cq リアルタイム索引更新の GUI → CLI 伝播契約。

RED 先行。CLI フラグ・設定フィールド・OrchestrateArgs は Sub-008 で追加する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _args():
    from hve.gui.orchestrate_args import OrchestrateArgs

    return OrchestrateArgs(workflow="akm", repo_root=Path("."))


class TestOrchestrateArgs:
    def test_unset_watch_emits_no_flag(self) -> None:
        argv = _args().to_argv()

        assert "--cq-watch" not in argv
        assert "--no-cq-watch" not in argv
        assert "--cq-watch-debounce-ms" not in argv

    def test_explicit_on_and_off_are_emitted(self) -> None:
        on = _args()
        on.cq_watch = True
        off = _args()
        off.cq_watch = False

        assert "--cq-watch" in on.to_argv()
        assert "--no-cq-watch" in off.to_argv()

    def test_debounce_is_emitted_with_its_value(self) -> None:
        args = _args()
        args.cq_watch_debounce_ms = 900
        argv = args.to_argv()

        assert argv[argv.index("--cq-watch-debounce-ms") + 1] == "900"


class TestCliParser:
    def test_flags_are_declared(self) -> None:
        from hve.__main__ import _build_parser

        parsed = _build_parser().parse_args([
            "orchestrate", "--workflow", "akm", "--no-cq-watch",
            "--cq-watch-debounce-ms", "700",
        ])

        assert parsed.no_cq_watch is True
        assert parsed.cq_watch_debounce_ms == 700

    def test_watch_defaults_to_unset(self) -> None:
        from hve.__main__ import _build_parser

        parsed = _build_parser().parse_args(["orchestrate", "--workflow", "akm"])

        assert parsed.cq_watch is None
        assert parsed.no_cq_watch is False
        assert parsed.cq_watch_debounce_ms is None


class TestSdkConfig:
    def test_defaults_follow_cq(self) -> None:
        """debounce の既定値は cq 側の定数を単一の情報源とする。"""
        from cq.watcher import DEFAULT_DEBOUNCE_MS
        from hve.config import SDKConfig

        config = SDKConfig()

        assert config.cq_watch is True
        assert config.cq_watch_debounce_ms == DEFAULT_DEBOUNCE_MS

    def test_environment_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hve.config import SDKConfig

        monkeypatch.setenv("HVE_CQ_WATCH", "0")
        monkeypatch.setenv("HVE_CQ_WATCH_DEBOUNCE_MS", "1200")
        config = SDKConfig.from_env()

        assert config.cq_watch is False
        assert config.cq_watch_debounce_ms == 1200


class TestSettingsBridge:
    def test_gui_settings_are_bridged_into_orchestrate_args(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`[options]` の cq_watch 値が子プロセス引数へ渡ること。"""
        from hve.gui import settings_store

        monkeypatch.setattr(
            settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
        )
        stored = settings_store.defaults()
        stored["options"]["cq_watch"] = "off"
        stored["options"]["cq_watch_debounce_ms"] = 850
        settings_store.save(stored)

        from hve.gui.orchestrate_args import apply_watch_settings

        args = _args()
        apply_watch_settings(args, settings_store.load().get("options", {}))

        argv = args.to_argv()
        assert "--no-cq-watch" in argv
        assert argv[argv.index("--cq-watch-debounce-ms") + 1] == "850"

    def test_stored_text_tristate_is_normalised(self) -> None:
        """設定ストアは 3 状態を文字列で保持するため bool へ正規化すること。

        正規化なしでは `_append_tristate` が文字列を無視し、GUI の ON/OFF が
        子プロセスへ一切伝わらない（mdq 側で実在した不具合の回帰防止）。
        """
        from hve.gui.orchestrate_args import apply_watch_settings

        for prefix in ("mdq", "cq"):
            on = _args()
            apply_watch_settings(on, {f"{prefix}_watch": "on"})
            off = _args()
            apply_watch_settings(off, {f"{prefix}_watch": "off"})
            unset = _args()
            apply_watch_settings(unset, {f"{prefix}_watch": ""})

            assert f"--{prefix}-watch" in on.to_argv()
            assert f"--no-{prefix}-watch" in off.to_argv()
            assert f"--{prefix}-watch" not in unset.to_argv()
            assert f"--no-{prefix}-watch" not in unset.to_argv()

    def test_zero_debounce_means_unset(self) -> None:
        from hve.gui.orchestrate_args import apply_watch_settings

        args = _args()
        apply_watch_settings(args, {"cq_watch_debounce_ms": 0})

        assert "--cq-watch-debounce-ms" not in args.to_argv()


class TestHelpContent:
    def test_help_entries_exist(self) -> None:
        from hve.gui.help_content import option_help

        for key in ("cq_watch", "cq_watch_debounce_ms"):
            assert option_help(key).short, f"{key} の help が未登録"
