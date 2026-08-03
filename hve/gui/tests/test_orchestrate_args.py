"""hve.gui.tests.test_orchestrate_args

FR-CLI-34: OrchestrateArgs.to_argv() の delete_local_merged_branch 変換テスト。
既定（有効）では何も出力せず、off（False）時のみ --no-delete-local-merged-branch を出力する。
"""

from __future__ import annotations

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


class TestAppIdToArgv:
    def test_app_id_is_not_duplicated(self) -> None:
        argv = OrchestrateArgs(workflow="asdw-web", app_id="APP-009").to_argv()

        assert argv.count("--app-id") == 1
        assert argv[argv.index("--app-id") + 1] == "APP-009"


class TestDataDeployBootstrapToArgv:
    def test_bootstrap_values_are_emitted_once(self) -> None:
        argv = OrchestrateArgs(
            workflow="asdw-web",
            data_location="japaneast",
            data_resource_suffix="app009",
            data_vnet_cidr="10.40.0.0/16",
            data_private_endpoint_subnet_cidr="10.40.1.0/24",
            data_aci_subnet_cidr="10.40.2.0/24",
        ).to_argv()

        for flag in (
            "--data-location",
            "--data-resource-suffix",
            "--data-vnet-cidr",
            "--data-private-endpoint-subnet-cidr",
            "--data-aci-subnet-cidr",
        ):
            assert argv.count(flag) == 1
        assert "--data-verify-aci-image" not in argv
