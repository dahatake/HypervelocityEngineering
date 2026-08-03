"""生成スクリプトが宣言済みネットワークパラメータを実際に適用することを固定する。

live canary（5 回目の再開実行）で Step 1.3 が初めて Azure リソース作成に到達し、
リソースグループと VNet が実際に作成された。そこで 2 つの欠陥が判明した。

1. `az network vnet subnet create --ids "$DATA_..._SUBNET_ID"` は成立しない。
   `--ids` は既存リソース参照用（show / update / delete）であり、`create` では
   `--name` / `--resource-group` / `--vnet-name` が `[Required]`。実行結果:

       ERROR: the following arguments are required:
       --resource-group/-g, -n/--name, --vnet-name

2. `az network vnet create` に `--address-prefixes` が無く、宣言した CIDR が
   沈黙のうちに無視されていた。実際に作成された VNet のアドレス空間は
   `10.0.0.0/16`（Azure CLI の既定値）で、宣言値 `10.40.0.0/16` ではなかった。
   `DATA_VNET_CIDR` / `DATA_PRIVATE_ENDPOINT_SUBNET_CIDR` / `DATA_ACI_SUBNET_CIDR`
   はいずれも `FR-WF-ASDW-01` が既定値の根拠まで定義した宣言入力である。

2 の一般形として「宣言済みワークフローパラメータは生成スクリプトへ到達する」
という不変条件を固定し、宣言入力が黙って捨てられる欠陥の再発を防ぐ。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve import asdw_data_runtime_context as runtime_context  # noqa: E402
from hve import asdw_data_script_launcher as launcher  # noqa: E402
from hve import runner as runner_module  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALL_SCRIPTS = (
    launcher._PREP,
    launcher._CREATE,
    launcher._REGISTRATION,
    launcher._VERIFY,
)

# RESOURCE_SUFFIX は Python 側で全リソース名へ決定論的に展開され、生成スクリプトは
# 展開後の名前（DATA_VNET_NAME / SQL_SERVER 等）を消費する。したがってスクリプト
# 本文に現れないことが正しい。
_DERIVATION_ONLY_CONTEXT_KEYS = frozenset({"RESOURCE_SUFFIX"})


def _script_text(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def _combined_scripts() -> str:
    return "\n".join(_script_text(relative) for relative in _ALL_SCRIPTS)


def _shell_reference(name: str) -> re.Pattern[str]:
    return re.compile(rf"\$\{{?{re.escape(name)}\b")


def _logical_lines(relative: str, needle: str) -> list[str]:
    return [
        line.strip()
        for line in _script_text(relative).splitlines()
        if needle in line
    ]


def test_declared_workflow_parameters_reach_the_generated_scripts() -> None:
    """宣言済み入力が生成スクリプトに到達せず黙って無視されるのを防ぐ。"""
    combined = _combined_scripts()
    declared = set(runner_module._ASDW_DATA_DEPLOY_BOOTSTRAP_PARAM_KEYS)

    unconsumed = sorted(
        key
        for key in declared - _DERIVATION_ONLY_CONTEXT_KEYS
        if not _shell_reference(key).search(combined)
    )

    assert not unconsumed, (
        "宣言済みワークフローパラメータが生成スクリプトへ到達していない: "
        f"{unconsumed}"
    )


def test_vnet_creation_applies_the_declared_address_space() -> None:
    """VNet を Azure CLI の既定アドレス空間で作らせない。"""
    lines = _logical_lines(launcher._PREP, "az network vnet create")

    assert lines, "prep が VNet を作成していない"
    for line in lines:
        assert "--address-prefixes" in line, (
            f"--address-prefixes が無く既定値 10.0.0.0/16 で作成される: {line}"
        )
        assert '"$DATA_VNET_CIDR"' in line, (
            f"宣言済み DATA_VNET_CIDR を適用していない: {line}"
        )


def test_subnet_creation_uses_creatable_arguments() -> None:
    """`az network vnet subnet create` は --ids を受け付けない。"""
    lines = _logical_lines(launcher._PREP, "az network vnet subnet create")

    assert lines, "prep がサブネットを作成していない"
    for line in lines:
        assert "--ids" not in line, (
            f"subnet create は --ids を受け付けない: {line}"
        )
        for flag in ("--resource-group", "--vnet-name", "--name", "--address-prefixes"):
            assert flag in line, f"{flag} が欠落している: {line}"


@pytest.mark.parametrize(
    ("subnet_name", "cidr_key"),
    (
        ("snet-private-endpoint", "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR"),
        ("snet-aci", "DATA_ACI_SUBNET_CIDR"),
    ),
)
def test_each_subnet_applies_its_declared_cidr(subnet_name: str, cidr_key: str) -> None:
    """各サブネットが対応する宣言済み CIDR で作成される。"""
    lines = [
        line
        for line in _logical_lines(launcher._PREP, "az network vnet subnet create")
        if subnet_name in line
    ]

    assert lines, f"{subnet_name} を作成する行が無い"
    assert any(f'"${cidr_key}"' in line for line in lines), (
        f"{subnet_name} が {cidr_key} を適用していない"
    )


def test_subnet_update_may_still_use_resource_ids() -> None:
    """update / show / delete は --ids を使ってよい（退行させない）。"""
    lines = _logical_lines(launcher._PREP, "az network vnet subnet update")

    assert lines, "prep がサブネット更新をしていない"
    assert all("--ids" in line for line in lines)


def test_subnet_literals_match_the_runtime_context_constants() -> None:
    """スクリプト内のサブネット名リテラルとリソース ID 導出元を一致させる。

    生成テンプレートは shell の `${VAR}` と衝突するため素の文字列リテラルで
    サブネット名を書いている。`DATA_*_SUBNET_ID` を組み立てる定数と乖離すると、
    作成したサブネットと後段が参照するサブネットが別物になる。
    """
    prep = _script_text(launcher._PREP)

    for constant in (
        runtime_context._PRIVATE_ENDPOINT_SUBNET_NAME,
        runtime_context._ACI_SUBNET_NAME,
        runtime_context._DEPLOY_IDENTITY_NAME,
    ):
        assert f"--name {constant} " in prep or f"--name {constant}\n" in prep, (
            f"prep が {constant} を作成していない（ID 導出元の定数と不一致）"
        )


# --- Confidential Ledger のリージョン fallback -------------------------------
#
# Azure Confidential Ledger は `japaneast` で利用できない。実行結果:
#
#     Code: LocationNotAvailableForResourceType
#     Message: The provided location 'japaneast' is not available for resource
#              type 'Microsoft.ConfidentialLedger/Ledgers'.
#
# `az provider show --namespace Microsoft.ConfidentialLedger` で対応 location を
# 確認したところ、リポジトリ標準優先順位（japaneast -> japanwest ->
# southeastasia）のうち `southeastasia` だけが対応していた。Skill
# `azure-region-policy` §2 の fallback ルールに従う。


def test_confidential_ledger_creation_pins_a_supported_location() -> None:
    """既定 location が非対応のため、台帳だけ明示 location で作成する。"""
    create = _script_text(launcher._CREATE)
    lines = [
        line.strip()
        for line in create.splitlines()
        if "az confidentialledger create" in line
    ]

    assert lines, "create が Confidential Ledger を作成していない"
    for line in lines:
        assert '--location "$CONFIDENTIAL_LEDGER_LOCATION"' in line, (
            f"台帳の location を明示していない（既定 location は非対応）: {line}"
        )


def test_confidential_ledger_location_follows_the_repository_region_policy() -> None:
    """fallback 先はリポジトリ標準優先順位の中から選ぶ。"""
    assert runtime_context._CONFIDENTIAL_LEDGER_LOCATION in (
        "japaneast",
        "japanwest",
        "southeastasia",
    ), "azure-region-policy §1 の標準優先順位外の location を使っている"


def test_confidential_ledger_location_reaches_the_child_environment() -> None:
    """明示 location が子 stage へ届かなければ台帳作成が失敗する。"""
    assert (
        "CONFIDENTIAL_LEDGER_LOCATION"
        in launcher._ASDW_DATA_DEPLOY_CHILD_CONTEXT_KEYS
    )
