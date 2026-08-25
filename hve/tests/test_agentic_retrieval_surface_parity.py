"""P6: Agentic Retrieval オプションの 3 面（CLI / GUI / Cloud）パリティ検証。

背景:
    `SDKConfig.enable_agentic_retrieval` は P5 で `StepDef.disabled_when_config`
    と接続され、実際に Step の実行可否を左右するようになった。しかし設定手段は
    対話ウィザードのみで、CLI フラグ・GUI ウィジェットが存在せず、非対話実行
    （CI / GUI 起動）から制御できなかった。

    本テストは 3 面それぞれから同じ値が届くこと、およびパリティ表がその実装と
    一致していることを固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_PATH = Path(__file__).resolve().parent / "fixtures" / "option_parity_matrix.yaml"

_CLI_FLAG = "--enable-agentic-retrieval"
_OPTION_KEY = "enable_agentic_retrieval"


def _matrix_entry(option_key: str) -> dict:
    data = yaml.safe_load(_MATRIX_PATH.read_text(encoding="utf-8"))
    rows = data["options"] if isinstance(data, dict) and "options" in data else data
    for row in rows:
        if row.get("option_key") == option_key:
            return row
    raise AssertionError(f"option_parity_matrix.yaml に {option_key} が存在しない")


class TestCliFlag:
    """CLI 面: --enable-agentic-retrieval が argparse に存在し値を通す。"""

    def _parse(self, *extra: str):
        from hve.__main__ import _build_parser as build_parser

        parser = build_parser()
        return parser.parse_args(["orchestrate", "--workflow", "asdw-web", *extra])

    def test_flag_exists_and_defaults_to_none(self):
        """未指定時は None（= ウィザード回答/既定に委ねる）。"""
        ns = self._parse()
        assert hasattr(ns, "enable_agentic_retrieval"), (
            "CLI に --enable-agentic-retrieval が存在しない"
        )
        assert ns.enable_agentic_retrieval is None

    @pytest.mark.parametrize("value", ["auto", "yes", "no"])
    def test_accepts_documented_values(self, value: str):
        ns = self._parse(_CLI_FLAG, value)
        assert ns.enable_agentic_retrieval == value

    def test_rejects_undocumented_value(self):
        """choices 外の値は fail-closed で拒否する（typo が既定 auto に化けない）。"""
        with pytest.raises(SystemExit):
            self._parse(_CLI_FLAG, "true")


class TestGuiArgs:
    """GUI 面: OrchestrateArgs が CLI フラグへ変換する。"""

    def test_field_exists_and_defaults_to_none(self):
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="asdw-web")
        assert args.enable_agentic_retrieval is None

    def test_none_is_not_emitted(self):
        """既定（auto 相当）では CLI 引数を増やさない。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        argv = OrchestrateArgs(workflow="asdw-web").to_argv()
        assert _CLI_FLAG not in argv

    @pytest.mark.parametrize("value", ["yes", "no"])
    def test_value_is_emitted_as_cli_flag(self, value: str):
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="asdw-web")
        args.enable_agentic_retrieval = value
        argv = args.to_argv()
        assert _CLI_FLAG in argv
        assert argv[argv.index(_CLI_FLAG) + 1] == value

    def test_emitted_argv_is_accepted_by_cli_parser(self):
        """GUI が生成した argv が CLI 側で必ず解釈できる（面間の契約）。"""
        from hve.__main__ import _build_parser as build_parser
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="asdw-web")
        args.enable_agentic_retrieval = "no"
        # to_argv() はサブコマンド名を含むため、そのままパーサへ渡す。
        ns = build_parser().parse_args(args.to_argv())
        assert ns.enable_agentic_retrieval == "no"


class TestGuiWidget:
    """GUI 面: 設定画面のウィジェットが 3 状態を持ち OrchestrateArgs へ書き戻す。"""

    def test_widget_offers_all_three_states(self):
        """import 可能な環境でのみ実行（PySide6 未導入環境は skip）。"""
        pytest.importorskip("PySide6")
        source = (_REPO_ROOT / "hve" / "gui" / "page_options.py").read_text(encoding="utf-8")
        assert "self.enable_agentic_retrieval = QComboBox()" in source
        for value in ("auto", "yes", "no"):
            assert f'userData="{value}"' in source, f"{value} 選択肢が無い"
        assert "args.enable_agentic_retrieval" in source, "OrchestrateArgs へ書き戻していない"


class TestCloudTags:
    """Cloud 面: 再利用ワークフローが AR Step を条件付きで生成する。

    Cloud は `python -m hve orchestrate` を起動せず、GitHub Issue を作成して
    Copilot Cloud Agent に処理させる方式である。したがって Python 側の
    `StepDef.disabled_when_config` は効かず、無効化は
    「Issue を作らない」というワークフロー内の条件分岐で実現する。

    AAD-WEB Cloud は `Step.7.5`、ASDW-WEB Cloud は registry と同じ
    `Step.2.5` / `Step.2.6` を使用する。
    """

    _WORKFLOWS = (
        "auto-app-detail-design-web-reusable.yml",
        "auto-app-dev-microservice-web-reusable.yml",
    )

    def _text(self, workflow_file: str) -> str:
        path = _REPO_ROOT / ".github" / "workflows" / workflow_file
        assert path.exists(), f"{workflow_file} が存在しない"
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("workflow_file", _WORKFLOWS)
    def test_reusable_workflow_embeds_tag(self, workflow_file: str):
        assert "enable-agentic-retrieval:" in self._text(workflow_file)

    def test_design_workflow_creates_step_7_5(self):
        text = self._text("auto-app-detail-design-web-reusable.yml")
        assert "[AAD-WEB] Step.7.5: Agentic Retrieval 機能要件詳細" in text
        assert "Arch-AgenticRetrieval-Detail" in text

    def test_dev_workflow_creates_step_2_5_and_2_6(self):
        text = self._text("auto-app-dev-microservice-web-reusable.yml")
        assert "[ASDW-WEB] Step.2.5: Agentic Retrieval Azure 実装設計" in text
        assert "[ASDW-WEB] Step.2.6: Agentic Retrieval Deploy" in text
        assert "Dev-Microservice-Azure-AgenticRetrievalDesign" in text
        assert "Dev-Microservice-Azure-AgenticRetrievalDeploy" in text

    @pytest.mark.parametrize("workflow_file", _WORKFLOWS)
    def test_ar_steps_are_gated_by_the_tag(self, workflow_file: str):
        """タグだけ埋めて無視する状態（設問が効かない状態）を防ぐ。"""
        assert '"${ENABLE_AGENTIC_RETRIEVAL}" != "no"' in self._text(workflow_file), (
            f"{workflow_file} で AR Step が enable_agentic_retrieval により無効化されていない"
        )

    def test_design_transition_includes_step_7_5(self):
        """7.5 が Step.7 コンテナの完了判定に含まれる（取り残されない）。"""
        text = self._text("auto-app-detail-design-web-reusable.yml")
        assert r"\] Step\.7\.5:" in text
        assert '"7.3"|"7.4"|"7.5")' in text
        assert "s75_ok" in text

    def test_dev_transition_declares_current_agentic_dependencies(self):
        """2.1 → 2.5、2.2 + 2.5 → 2.6 の依存を固定する。"""
        text = self._text("auto-app-dev-microservice-web-reusable.yml")
        assert '"2.5": ["2.1"]' in text
        assert '"2.6": ["2.2", "2.5"]' in text

    def test_dev_falls_back_when_ar_steps_absent(self):
        """AR 無効時は 2.5 / 2.6 Issue を作らず、欠落依存を完了扱いにする。"""
        text = self._text("auto-app-dev-microservice-web-reusable.yml")
        assert 'if [[ "${ENABLE_AGENTIC_RETRIEVAL}" != "no" ]]; then' in text
        assert "return sid not in steps or" in text


class TestCliOverridePrecedence:
    """CLI フラグ > ウィザード回答 > 既定値 の優先順位を固定する。"""

    def _config(self, wizard_value: str):
        from hve.config import SDKConfig

        cfg = SDKConfig()
        cfg.enable_agentic_retrieval = wizard_value
        return cfg

    def _args(self, cli_value):
        import argparse

        return argparse.Namespace(enable_agentic_retrieval=cli_value)

    def test_cli_overrides_wizard_answer(self):
        from hve.__main__ import _apply_agentic_retrieval_cli_overrides

        cfg = self._config("yes")
        _apply_agentic_retrieval_cli_overrides(cfg, self._args("no"))
        assert cfg.enable_agentic_retrieval == "no"

    def test_missing_cli_flag_preserves_wizard_answer(self):
        """CLI 未指定でウィザード回答が既定値に上書きされない（P5 の設定が死なない）。"""
        from hve.__main__ import _apply_agentic_retrieval_cli_overrides

        cfg = self._config("no")
        _apply_agentic_retrieval_cli_overrides(cfg, self._args(None))
        assert cfg.enable_agentic_retrieval == "no"

    def test_cli_no_actually_disables_steps(self):
        """CLI 指定が Step 無効化まで到達する（設定と実行の接続を端から端まで確認）。"""
        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.workflow_registry import resolve_disabled_step_ids

        cfg = self._config("yes")
        _apply_agentic_retrieval_cli_overrides(cfg, self._args("no"))
        disabled = resolve_disabled_step_ids(
            "asdw-web", {"enable_agentic_retrieval": cfg.enable_agentic_retrieval}
        )
        assert {"2.5", "2.6"} <= disabled

    def test_cli_yes_keeps_steps_enabled(self):
        from hve.__main__ import _apply_agentic_retrieval_cli_overrides
        from hve.workflow_registry import resolve_disabled_step_ids

        cfg = self._config("no")
        _apply_agentic_retrieval_cli_overrides(cfg, self._args("yes"))
        disabled = resolve_disabled_step_ids(
            "asdw-web", {"enable_agentic_retrieval": cfg.enable_agentic_retrieval}
        )
        assert not ({"2.5", "2.6"} & disabled)


class TestParityMatrix:
    """パリティ表が実装と一致している（表だけ先行して嘘にならない）。"""

    def test_matrix_records_the_cli_flag(self):
        entry = _matrix_entry(_OPTION_KEY)
        assert entry["hve_cli_flag"] == _CLI_FLAG, (
            "パリティ表の hve_cli_flag が実装と不一致"
        )

    def test_matrix_flag_is_actually_parsable(self):
        """表に書かれたフラグ名が実在することを CLI パーサで確認する。"""
        from hve.__main__ import _build_parser as build_parser

        entry = _matrix_entry(_OPTION_KEY)
        ns = build_parser().parse_args(
            ["orchestrate", "--workflow", "asdw-web", entry["hve_cli_flag"], "no"]
        )
        assert getattr(ns, entry["hve_config_attr"]) == "no"
