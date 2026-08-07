"""T6: `enable_tool_search` の 3 面（CLI / GUI / Cloud）パリティ検証。

`auto` は「Tool 総数が 15 を超えたら有効化」を意味し、hve 側の既定と同じ。
GUI が `auto` を選んだときに CLI へフラグを渡さないのは、
対話ウィザードや将来の Issue タグで設定した値を静かに上書きしないため。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_MATRIX_PATH = Path(__file__).resolve().parent / "fixtures" / "option_parity_matrix.yaml"
_CLI_FLAG = "--enable-tool-search"
_OPTION_KEY = "enable_tool_search"


def _matrix_entry(option_key: str) -> dict:
    data = yaml.safe_load(_MATRIX_PATH.read_text(encoding="utf-8"))
    rows = data["options"] if isinstance(data, dict) and "options" in data else data
    for row in rows:
        if row.get("option_key") == option_key:
            return row
    raise AssertionError(f"option_parity_matrix.yaml に {option_key} が存在しない")


def _parse(*extra: str):
    from hve.__main__ import _build_parser

    return _build_parser().parse_args(
        ["orchestrate", "--workflow", "aagd", *extra]
    )


class TestConfigDefault:
    def test_default_is_auto(self):
        """既定は auto。Tool 数に応じた自動判定に委ねる。"""
        from hve.config import SDKConfig

        assert SDKConfig().enable_tool_search == "auto"


class TestCliFlag:
    def test_default_is_none(self):
        """未指定は None。設定済みの値を上書きしない。"""
        assert _parse().enable_tool_search is None

    @pytest.mark.parametrize("value", ["auto", "yes", "no"])
    def test_accepts_documented_values(self, value: str):
        assert _parse(_CLI_FLAG, value).enable_tool_search == value

    def test_rejects_undocumented_value(self):
        """typo が既定へ化けないよう fail-closed にする。"""
        with pytest.raises(SystemExit):
            _parse(_CLI_FLAG, "true")

    def test_appears_in_help(self):
        """orchestrate サブコマンドの help に出ることを見る。

        トップレベルの help にはサブコマンドのフラグが含まれない。
        """
        from hve.__main__ import _build_parser

        parser = _build_parser()
        sub = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        )
        assert _CLI_FLAG in sub.choices["orchestrate"].format_help()


class TestCliOverrideReachesConfig:
    def test_value_reaches_config(self):
        import argparse

        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.config import SDKConfig

        cfg = SDKConfig()
        _apply_agentic_retrieval_cli_overrides(cfg, _parse(_CLI_FLAG, "no"))
        assert cfg.enable_tool_search == "no"

    def test_unspecified_preserves_existing(self):
        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.config import SDKConfig

        cfg = SDKConfig()
        cfg.enable_tool_search = "yes"
        _apply_agentic_retrieval_cli_overrides(cfg, _parse())
        assert cfg.enable_tool_search == "yes"


class TestGuiArgs:
    def test_default_is_none(self):
        from hve.gui.orchestrate_args import OrchestrateArgs

        assert OrchestrateArgs(workflow="aagd").enable_tool_search is None

    def test_default_emits_no_flag(self):
        from hve.gui.orchestrate_args import OrchestrateArgs

        assert _CLI_FLAG not in OrchestrateArgs(workflow="aagd").to_argv()

    @pytest.mark.parametrize("value", ["yes", "no"])
    def test_value_round_trips_through_cli(self, value: str):
        from hve.__main__ import _build_parser
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="aagd")
        args.enable_tool_search = value
        ns = _build_parser().parse_args(args.to_argv())
        assert ns.enable_tool_search == value


class TestGuiWidget:
    def test_widget_offers_three_states(self):
        pytest.importorskip("PySide6")
        source = (
            Path(__file__).resolve().parents[1] / "gui" / "page_options.py"
        ).read_text(encoding="utf-8")
        assert "self.enable_tool_search = QComboBox()" in source
        assert "args.enable_tool_search" in source

    def test_widget_explains_the_threshold(self):
        """利用者が「なぜ 15 なのか」を画面で判断できるようにする。"""
        pytest.importorskip("PySide6")
        source = (
            Path(__file__).resolve().parents[1] / "gui" / "page_options.py"
        ).read_text(encoding="utf-8")
        # ウィジェット定義から description 末尾までを見る
        start = source.index("self.enable_tool_search = QComboBox()")
        assert "15" in source[start:start + 2000]


class TestParityMatrix:
    def test_matrix_records_the_cli_flag(self):
        assert _matrix_entry(_OPTION_KEY)["hve_cli_flag"] == _CLI_FLAG

    def test_matrix_flag_is_parsable(self):
        from hve.__main__ import _build_parser

        entry = _matrix_entry(_OPTION_KEY)
        ns = _build_parser().parse_args(
            ["orchestrate", "--workflow", "aagd", entry["hve_cli_flag"], "no"]
        )
        assert getattr(ns, entry["hve_config_attr"]) == "no"

    def test_cloud_surface_exposes_the_same_option(self):
        """Cloud だけ選べないと、no の Agent で Step.4 を落とせない。"""
        entry = _matrix_entry(_OPTION_KEY)
        assert entry["issue_form_field_id"] == _OPTION_KEY
        assert "Cloud" in entry["notes"]

    def test_applies_to_matches_the_actual_surface_coverage(self):
        """Issue Form / SDKConfig の両方にあるので common。"""
        assert _matrix_entry(_OPTION_KEY)["applies_to"] == "common"

    def test_notes_distinguish_from_hve_own_tool_search(self):
        """SDKConfig には HVE 自身の SDK セッション用 `tool_search` も存在する。

        名前が似ているため、表の時点で別物と分かるようにしておく。
        """
        assert "別ドメイン" in _matrix_entry(_OPTION_KEY)["notes"]


class TestThresholdIsSingleSourced:
    """閾値 15 が config コメントと validator で一致している。"""

    def test_validator_uses_fifteen(self):
        from hve.artifact_validation import _TOOLBOX_TOOL_COUNT_THRESHOLD

        assert _TOOLBOX_TOOL_COUNT_THRESHOLD == 15

    def test_config_comment_documents_the_same_threshold(self):
        """フィールド定義を基点に見る。

        config.py には HVE 自身の `tool_search` 側から本フィールドを参照する
        コメントもあるため、単純な先頭一致だと別の箇所を読んでしまう。
        """
        source = (
            Path(__file__).resolve().parents[1] / "config.py"
        ).read_text(encoding="utf-8")
        start = source.index("enable_tool_search: str =")
        assert "15" in source[start:start + 600]
