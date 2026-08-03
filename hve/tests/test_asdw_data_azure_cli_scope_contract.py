"""生成スクリプトの Azure CLI スコープ引数が ARM 形式であることを固定する。

live canary（3 回目の再開実行）が Step 1.3 の prep stage で Azure CLI の内部例外に
より停止した。

    azure/cli/command_modules/resource/policy.py, in ResolveScopeForList
    IndexError: list index out of range

`az policy assignment list --scope` / `az policy exemption list --scope` は ARM の
スコープパスを期待しており、裸のサブスクリプション GUID を渡すと azure-cli 内部で
パス分解に失敗して IndexError になる。実測:

    az policy assignment list --scope "<GUID>"                 -> rc=1 IndexError
    az policy assignment list --scope "/subscriptions/<GUID>"  -> rc=0

同じ生成スクリプト内の `az role assignment create` や
`az network private-endpoint create --private-connection-resource-id` は既に
`/subscriptions/$SUBSCRIPTION_ID/...` を組み立てており、policy preflight の 2 行だけが
裸の GUID を渡していた。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve import asdw_data_runtime_context as runtime_context  # noqa: E402
from hve import asdw_data_script_launcher as launcher  # noqa: E402
from hve.asdw_data_script_generator import (  # noqa: E402
    _read_generation_inputs,
    render_asdw_data_producers,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_PREFLIGHT_SCRIPTS = (launcher._PREP, launcher._CREATE)
_BARE_SUBSCRIPTION_SCOPE = re.compile(r'--scope\s+"\$SUBSCRIPTION_ID"')
_SUBSCRIPTION_ARM_SCOPE = '--scope "/subscriptions/$SUBSCRIPTION_ID"'


def _generated_scripts() -> dict[str, str]:
    design_text, sample_data_text = _read_generation_inputs(_REPO_ROOT)
    rendered = render_asdw_data_producers(
        design_text=design_text,
        sample_data_text=sample_data_text,
    )
    return {
        relative: payload.decode("utf-8") if isinstance(payload, bytes) else payload
        for relative, payload in rendered.items()
    }


@pytest.mark.parametrize("relative", _POLICY_PREFLIGHT_SCRIPTS)
def test_tracked_script_never_passes_a_bare_subscription_id_as_scope(
    relative: str,
) -> None:
    """裸の GUID は azure-cli がスコープパスとして分解できず IndexError になる。"""
    text = (_REPO_ROOT / relative).read_text(encoding="utf-8")

    assert not _BARE_SUBSCRIPTION_SCOPE.search(text), (
        f"{relative} が `--scope \"$SUBSCRIPTION_ID\"` を渡している。"
        "ARM スコープパス `/subscriptions/$SUBSCRIPTION_ID` を使うこと"
    )


@pytest.mark.parametrize("relative", _POLICY_PREFLIGHT_SCRIPTS)
def test_tracked_script_uses_the_subscription_arm_scope(relative: str) -> None:
    """policy preflight は subscription の ARM スコープパスを使う。"""
    text = (_REPO_ROOT / relative).read_text(encoding="utf-8")

    assert _SUBSCRIPTION_ARM_SCOPE in text, (
        f"{relative} の policy preflight が subscription ARM スコープを使っていない"
    )


@pytest.mark.parametrize("relative", _POLICY_PREFLIGHT_SCRIPTS)
def test_generated_script_never_passes_a_bare_subscription_id_as_scope(
    relative: str,
) -> None:
    """tracked ファイルだけでなく生成器出力そのものを固定する。"""
    generated = _generated_scripts()

    assert not _BARE_SUBSCRIPTION_SCOPE.search(generated[relative]), (
        f"生成器が {relative} へ裸の `$SUBSCRIPTION_ID` スコープを出力している"
    )


def test_resource_scoped_commands_keep_building_full_arm_paths() -> None:
    """既に正しい `/subscriptions/.../resourceGroups/...` 形式を退行させない。"""
    prep = (_REPO_ROOT / launcher._PREP).read_text(encoding="utf-8")
    create = (_REPO_ROOT / launcher._CREATE).read_text(encoding="utf-8")

    assert (
        "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
        "/providers/Microsoft.ContainerRegistry/registries/$DATA_VERIFY_ACR_NAME"
    ) in prep
    assert (
        "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
        "/providers/Microsoft.Sql/servers/$SQL_SERVER"
    ) in create


# --- az acr build のソース指定形式 -------------------------------------------
#
# `az acr build` は Windows でソースディレクトリの指定形式を強く選ぶ。実測:
#
#     --file Dockerfile "C:\...\azure/data-verify"   -> Unable to find 'Dockerfile'.
#     --file Dockerfile "C:\...\azure\data-verify"   -> Unable to find 'Dockerfile'.
#     --file Dockerfile src/infra/azure/data-verify  -> Unable to find 'Dockerfile'.
#     cd <dir> && --file Dockerfile .                -> rc=0（ビルド成功）
#
# ドライブレター付き絶対パスもリポジトリ相対パスも受理されず、カレント
# ディレクトリを移動して `.` を渡す形式だけが成立する。


def test_acr_build_uses_the_current_directory_as_source() -> None:
    """絶対パス／多階層相対パスを渡すと Dockerfile を発見できない。"""
    prep = (_REPO_ROOT / launcher._PREP).read_text(encoding="utf-8")
    lines = [line.strip() for line in prep.splitlines() if "az acr build" in line]

    assert lines, "prep が検証イメージをビルドしていない"
    for line in lines:
        assert line.endswith(" ."), (
            f"az acr build のソースは `.` でなければならない: {line}"
        )
        assert "$SCRIPT_DIR/data-verify" not in line, (
            f"ソースにディレクトリパスを渡している: {line}"
        )


def test_acr_build_is_preceded_by_a_directory_change() -> None:
    """`.` を渡す前に検証イメージのディレクトリへ移動している。"""
    prep = (_REPO_ROOT / launcher._PREP).read_text(encoding="utf-8")
    statements = [line.strip() for line in prep.splitlines() if line.strip()]
    build_index = next(
        index for index, line in enumerate(statements) if line.startswith("az acr build")
    )

    assert statements[build_index - 1] == 'cd "$SCRIPT_DIR/data-verify"', (
        "az acr build の直前で検証イメージのディレクトリへ移動すること: "
        f"{statements[build_index - 1]}"
    )
    assert statements[build_index + 1] == 'cd "$SCRIPT_DIR"', (
        "ビルド後にカレントディレクトリを戻すこと: "
        f"{statements[build_index + 1]}"
    )


# --- AAD 専用認証と外部管理者 -------------------------------------------------
#
# `az sql server create --enable-ad-only-auth` は外部管理者の指定を必須とする。
# 欠けると Azure 側が拒否する:
#
#     Code: MissingExternalAdministratorWithAadOnlyAuth
#     Message: In order to use Azure AD Only Authentication, please provide
#              details of an external administrator.


def test_sql_server_ad_only_auth_declares_an_external_administrator() -> None:
    """AAD 専用認証を使うなら外部管理者 3 引数を必ず渡す。"""
    create = (_REPO_ROOT / launcher._CREATE).read_text(encoding="utf-8")
    lines = [line.strip() for line in create.splitlines() if "az sql server create" in line]

    assert lines, "create が SQL Server を作成していない"
    for line in lines:
        if "--enable-ad-only-auth" not in line:
            continue
        for flag in (
            "--external-admin-principal-type",
            "--external-admin-name",
            "--external-admin-sid",
        ):
            assert flag in line, f"{flag} が欠落している: {line}"


def test_sql_server_admin_is_the_deploy_managed_identity() -> None:
    """検証 ACI が MSI 接続する同じ identity を AAD 管理者にする。

    Application の `--external-admin-sid` は Client ID（Object ID ではない）。
    検証 ACI は `AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID"` と
    `Authentication=ActiveDirectoryMSI` で接続するため、同じ値を用いる。
    """
    create = (_REPO_ROOT / launcher._CREATE).read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in create.splitlines()
        if "az sql server create" in line and "--enable-ad-only-auth" in line
    ]

    assert lines, "AAD 専用認証の SQL Server 作成行が無い"
    for line in lines:
        assert "--external-admin-principal-type Application" in line, line
        assert (
            f"--external-admin-name {runtime_context._DEPLOY_IDENTITY_NAME}" in line
        ), line
        assert '--external-admin-sid "$DATA_DEPLOY_IDENTITY_CLIENT_ID"' in line, line
