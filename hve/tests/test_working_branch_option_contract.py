"""FR-CLI-83: PR用作業branchを新規作成するか選ぶ全入口RED契約。"""

from __future__ import annotations

import dataclasses
import importlib
import inspect

from hve.config import SDKConfig
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.startup_preflight import validate_startup_configuration


def _main_module():
    return importlib.import_module("hve.__main__")


def _parse(*extra: str):
    parser = _main_module()._build_parser()
    return parser.parse_args(["orchestrate", "--workflow", "aas", *extra])


class TestSdkConfigContract:
    def test_config_declares_create_working_branch(self) -> None:
        names = {field.name for field in dataclasses.fields(SDKConfig)}
        assert "create_working_branch" in names

    def test_config_default_creates_a_branch(self) -> None:
        assert getattr(SDKConfig(), "create_working_branch", None) is True


class TestCliContract:
    def test_parser_default_creates_a_branch(self) -> None:
        assert getattr(_parse(), "create_working_branch", None) is True

    def test_parser_accepts_negative_flag(self) -> None:
        assert getattr(
            _parse("--no-create-working-branch"), "create_working_branch", None
        ) is False

    def test_build_config_propagates_false(self) -> None:
        config = _main_module()._build_config(_parse("--no-create-working-branch"))
        assert getattr(config, "create_working_branch", None) is False


class TestGuiArgvContract:
    def test_gui_args_declares_default_true(self) -> None:
        fields = {field.name: field for field in dataclasses.fields(OrchestrateArgs)}
        assert fields["create_working_branch"].default is True

    def test_default_emits_no_flag(self) -> None:
        argv = OrchestrateArgs(workflow="aas").to_argv()
        assert "--create-working-branch" not in argv
        assert "--no-create-working-branch" not in argv

    def test_false_emits_negative_flag(self) -> None:
        args = OrchestrateArgs(workflow="aas")
        args.create_working_branch = False  # type: ignore[attr-defined]
        assert "--no-create-working-branch" in args.to_argv()


class TestStartupPreflightContract:
    def test_preflight_accepts_branch_mode(self) -> None:
        parameters = inspect.signature(validate_startup_configuration).parameters
        assert "create_working_branch" in parameters
