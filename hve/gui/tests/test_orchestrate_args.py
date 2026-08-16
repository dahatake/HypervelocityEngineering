"""hve.gui.tests.test_orchestrate_args

FR-CLI-34: OrchestrateArgs.to_argv() の delete_local_merged_branch 変換テスト。
既定（有効）では何も出力せず、off（False）時のみ --no-delete-local-merged-branch を出力する。
"""

from __future__ import annotations

import dataclasses

from hve.gui.orchestrate_args import OrchestrateArgs


class TestDeleteLocalMergedBranchToArgv:
    def test_default_emits_no_flag(self) -> None:
        """既定（True）では --delete-local-merged-branch / --no-... を出力しない。"""
        argv = OrchestrateArgs(workflow="aas").to_argv()
        assert "--no-delete-local-merged-branch" not in argv
        assert "--delete-local-merged-branch" not in argv

    def test_off_emits_no_flag(self) -> None:
        """off（False）では --no-delete-local-merged-branch を出力する。"""
        argv = OrchestrateArgs(workflow="aas", delete_local_merged_branch=False).to_argv()
        assert "--no-delete-local-merged-branch" in argv


class TestContextTierToArgv:
    """context_tier → --context-tier 変換テスト。"""

    def test_default_is_long_context(self) -> None:
        """既定では --context-tier long_context を出力する。"""
        argv = OrchestrateArgs(workflow="aas").to_argv()
        assert "--context-tier" in argv
        assert argv[argv.index("--context-tier") + 1] == "long_context"

    def test_explicit_default_value(self) -> None:
        """context_tier='default' を指定すると --context-tier default を出力する。"""
        argv = OrchestrateArgs(workflow="aas", context_tier="default").to_argv()
        assert argv[argv.index("--context-tier") + 1] == "default"

    def test_none_emits_no_flag(self) -> None:
        """context_tier=None（未指定）では --context-tier を出力しない。"""
        argv = OrchestrateArgs(workflow="aas", context_tier=None).to_argv()
        assert "--context-tier" not in argv


class TestSteeringIpcDirToArgv:
    """steering_ipc_dir → --steering-ipc-dir 変換テスト。"""

    def test_default_emits_no_flag(self) -> None:
        """既定（None）では --steering-ipc-dir を出力しない。"""
        argv = OrchestrateArgs(workflow="aas").to_argv()
        assert "--steering-ipc-dir" not in argv

    def test_set_emits_flag_with_path(self) -> None:
        """steering_ipc_dir 設定時は --steering-ipc-dir <path> を出力する。"""
        argv = OrchestrateArgs(workflow="aas", steering_ipc_dir="/tmp/steering").to_argv()
        assert "--steering-ipc-dir" in argv
        assert argv[argv.index("--steering-ipc-dir") + 1] == "/tmp/steering"


class TestToolSearchToArgv:
    """FR-MODEL-04: tool_search → --tool-search / --no-tool-search 変換テスト。"""

    def test_default_emits_no_flag(self) -> None:
        """既定（None = CLI 既定を継承）ではどちらのフラグも出力しない。"""
        argv = OrchestrateArgs(workflow="aas").to_argv()
        assert "--tool-search" not in argv
        assert "--no-tool-search" not in argv

    def test_on_emits_flag(self) -> None:
        argv = OrchestrateArgs(workflow="aas", tool_search=True).to_argv()
        assert "--tool-search" in argv

    def test_off_emits_negative_flag(self) -> None:
        argv = OrchestrateArgs(workflow="aas", tool_search=False).to_argv()
        assert "--no-tool-search" in argv


class TestAppIdToArgv:
    def test_app_id_is_not_duplicated(self) -> None:
        argv = OrchestrateArgs(workflow="asdw-web", app_id="APP-009").to_argv()

        assert argv.count("--app-id") == 1
        assert argv[argv.index("--app-id") + 1] == "APP-009"


class TestDataDeployBootstrapToArgv:
    """FR-WF-ASDW-02: 既定値を持つ 5 件は GUI の入力項目ではない。"""

    _FLAGS = (
        "--data-location",
        "--data-resource-suffix",
        "--data-vnet-cidr",
        "--data-private-endpoint-subnet-cidr",
        "--data-aci-subnet-cidr",
        "--data-verify-aci-image",
    )
    _FIELDS = (
        "data_location",
        "data_resource_suffix",
        "data_vnet_cidr",
        "data_private_endpoint_subnet_cidr",
        "data_aci_subnet_cidr",
    )

    def test_gui_does_not_emit_bootstrap_flags(self) -> None:
        argv = OrchestrateArgs(
            workflow="asdw-web", resource_group="rg-app009"
        ).to_argv()

        assert argv[argv.index("--resource-group") + 1] == "rg-app009"
        for flag in self._FLAGS:
            assert flag not in argv

    def test_bootstrap_fields_are_not_declared(self) -> None:
        names = {f.name for f in dataclasses.fields(OrchestrateArgs)}
        for name in self._FIELDS:
            assert name not in names
