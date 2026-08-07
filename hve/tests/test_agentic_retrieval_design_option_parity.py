"""C7: Agentic Retrieval の設計パラメータ 5 件の 3 面パリティ検証。

`enable_agentic_retrieval` は Step の実行可否を左右するため
`test_agentic_retrieval_surface_parity.py` で個別に固定している。
本モジュールはそれ以外の 5 件——生成される設計内容にのみ影響する
パラメータ——について、CLI / GUI / パリティ表の一致を固定する。

いずれも「未指定なら CLI へ渡さない」ことが重要である。
GUI が既定値を常に送ると、対話ウィザードで収集した値を
静かに上書きしてしまうため。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_MATRIX_PATH = Path(__file__).resolve().parent / "fixtures" / "option_parity_matrix.yaml"

# option_key -> (CLI フラグ, CLI 引数例, 期待される config 値)
_DESIGN_OPTIONS = {
    "agentic_data_source_modes": (
        "--agentic-data-source-modes",
        ["indexer", "push"],
        ["indexer", "push"],
    ),
    "foundry_mcp_integration": ("--foundry-mcp-integration", [], True),
    "agentic_data_sources_hint": (
        "--agentic-data-sources-hint",
        ["社内規程 PDF (Blob)"],
        "社内規程 PDF (Blob)",
    ),
    "agentic_existing_design_diff_only": (
        "--agentic-existing-design-diff-only",
        [],
        True,
    ),
    "foundry_sku_fallback_policy": (
        "--foundry-sku-fallback-policy",
        ["global_required"],
        "global_required",
    ),
}


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
        ["orchestrate", "--workflow", "asdw-web", *extra]
    )


@pytest.mark.parametrize("option_key", sorted(_DESIGN_OPTIONS))
class TestCliFlags:
    def test_default_is_none(self, option_key: str):
        """未指定は None。ウィザード回答を静かに上書きしないための前提。"""
        assert getattr(_parse(), option_key) is None

    def test_flag_sets_expected_value(self, option_key: str):
        flag, argv, expected = _DESIGN_OPTIONS[option_key]
        assert getattr(_parse(flag, *argv), option_key) == expected

    def test_matrix_matches_implementation(self, option_key: str):
        flag, _, _ = _DESIGN_OPTIONS[option_key]
        assert _matrix_entry(option_key)["hve_cli_flag"] == flag


class TestBooleanFlagsHaveNegativeForm:
    """bool 系は否定形を持ち、既定 True を明示的に無効化できる。"""

    @pytest.mark.parametrize(
        "flag,attr",
        [
            ("--no-foundry-mcp-integration", "foundry_mcp_integration"),
            (
                "--no-agentic-existing-design-diff-only",
                "agentic_existing_design_diff_only",
            ),
        ],
    )
    def test_negative_form_sets_false(self, flag: str, attr: str):
        assert getattr(_parse(flag), attr) is False


class TestCliOverridesReachConfig:
    """CLI 値が SDKConfig まで到達する（フラグが宙に浮かない）。"""

    def _apply(self, *extra: str):
        import argparse

        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.config import SDKConfig

        cfg = SDKConfig()
        _apply_agentic_retrieval_cli_overrides(cfg, _parse(*extra))
        return cfg

    @pytest.mark.parametrize("option_key", sorted(_DESIGN_OPTIONS))
    def test_value_reaches_config(self, option_key: str):
        flag, argv, expected = _DESIGN_OPTIONS[option_key]
        assert getattr(self._apply(flag, *argv), option_key) == expected

    def test_unspecified_flags_preserve_wizard_answers(self):
        """CLI 未指定のとき、ウィザードが入れた値が保持される。"""
        import argparse

        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.config import SDKConfig

        cfg = SDKConfig()
        cfg.agentic_data_sources_hint = "ウィザード由来"
        cfg.foundry_mcp_integration = False
        _apply_agentic_retrieval_cli_overrides(cfg, _parse())
        assert cfg.agentic_data_sources_hint == "ウィザード由来"
        assert cfg.foundry_mcp_integration is False


class TestGuiEmitsParsableArgv:
    """GUI が生成した argv を CLI が必ず解釈できる（面間の契約）。"""

    def test_all_options_round_trip(self):
        from hve.__main__ import _build_parser
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="asdw-web")
        args.agentic_data_source_modes = ["indexer", "push"]
        args.foundry_mcp_integration = False
        args.agentic_data_sources_hint = "Blob と Azure SQL"
        args.agentic_existing_design_diff_only = True
        args.foundry_sku_fallback_policy = "global_required"

        ns = _build_parser().parse_args(args.to_argv())
        assert ns.agentic_data_source_modes == ["indexer", "push"]
        assert ns.foundry_mcp_integration is False
        assert ns.agentic_data_sources_hint == "Blob と Azure SQL"
        assert ns.agentic_existing_design_diff_only is True
        assert ns.foundry_sku_fallback_policy == "global_required"

    def test_defaults_emit_no_agentic_flags(self):
        """既定の GUI 状態では余計なフラグを付けない。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(workflow="asdw-web").to_argv()
        for flag, _, _ in _DESIGN_OPTIONS.values():
            assert flag not in argv
        assert "--no-foundry-mcp-integration" not in argv


class TestGuiWidgetsExist:
    def test_page_options_defines_all_widgets(self):
        pytest.importorskip("PySide6")
        source = (
            Path(__file__).resolve().parents[1] / "gui" / "page_options.py"
        ).read_text(encoding="utf-8")
        for option_key in _DESIGN_OPTIONS:
            assert f"self.{option_key} = " in source, f"{option_key} のウィジェットが無い"
            assert f"args.{option_key} = " in source, f"{option_key} の書き戻しが無い"
