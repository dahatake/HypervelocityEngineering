"""検証／登録 ACI イメージ資産（Dockerfile）の契約テスト。

検証項目:
  1. Dockerfile が規約パスに存在すること
  2. ベースイメージが `mssql-python` の要求（Python 3.10 以降）を満たすこと
  3. `mssql-python` が Linux で要求するシステムライブラリを導入していること
  4. 同梱する配布集合が、`hve/artifact_validation.py` の validator が ACI 実行時
     インストールとして許容する配布集合（SSOT）と一致すること
  5. `hve/artifact_validation.py` の生成プログラムに未知 import が増えていないこと
  6. LF 改行・BOM なしであること（ACR Tasks は Linux 上でビルドする）

AuditRecord 登録 ACI は `python -c` ペイロード 1 個のみを許容し実行時
インストールができないため、必要な配布はイメージへ同梱する必要がある。

根拠: work/analysis/2026-07-27-asdw-verify-image-facts.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / "src" / "infra" / "azure" / "data-verify" / "Dockerfile"
_ARTIFACT_VALIDATION = _REPO_ROOT / "hve" / "artifact_validation.py"

# `mssql-python` の Linux 実行に必要なシステムライブラリ（Debian 系）。
_REQUIRED_SYSTEM_LIBRARIES = ("libltdl7", "libkrb5-3", "libgssapi-krb5-2")

# ACI 内 Python が import するトップレベルモジュールとして既知のもの。
# `azure.core` は azure-cosmos / azure-identity の依存として解決される。
_KNOWN_GENERATED_MODULES = frozenset(
    {
        "mssql_python",
        "azure.core",
        "azure.cosmos",
        "azure.identity",
        "azure.confidentialledger",
    }
)

# 生成される ACI プログラムの import 文を拾うパターン。
_GENERATED_IMPORT_PATTERN = re.compile(
    r"^from ((?:azure|mssql_python)(?:\.[a-z_]+)*) import",
    re.MULTILINE,
)
# validator が ACI 実行時インストールとして許容する配布名リテラル（SSOT）。
_VALIDATOR_PACKAGES_PATTERN = re.compile(
    r'^\s+packages (?:=|\+=) "([a-z0-9 -]+)"$',
    re.MULTILINE,
)
# Dockerfile 内の `名前==バージョン` を拾うパターン。
_PIN_PATTERN = re.compile(
    r"^\s+([a-z0-9][a-z0-9-]*)==(\d[0-9A-Za-z.]*)\s*\\?$",
    re.MULTILINE,
)


def _dockerfile_bytes() -> bytes:
    return _DOCKERFILE.read_bytes()


def _dockerfile_text() -> str:
    return _dockerfile_bytes().decode("utf-8")


def _artifact_validation_text() -> str:
    return _ARTIFACT_VALIDATION.read_text(encoding="utf-8")


def _pinned_distributions() -> set:
    return {name for name, _version in _PIN_PATTERN.findall(_dockerfile_text())}


def _top_level_module(module: str) -> str:
    """`azure.cosmos.aio` -> `azure.cosmos` / `mssql_python` -> `mssql_python`。"""
    if not module.startswith("azure."):
        return module.split(".", 1)[0]
    parts = module.split(".")
    return ".".join(parts[:2])


def test_dockerfile_exists() -> None:
    assert _DOCKERFILE.is_file()


def test_base_image_satisfies_mssql_python_minimum_python_version() -> None:
    """`mssql-python` は Python 3.10 以降を要求する。"""
    match = re.search(
        r"^FROM python:(\d+)\.(\d+)-slim$",
        _dockerfile_text(),
        re.MULTILINE,
    )
    assert match is not None, "ベースイメージは python:<major>.<minor>-slim で固定する"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (3, 10)


@pytest.mark.parametrize("library", _REQUIRED_SYSTEM_LIBRARIES)
def test_required_system_libraries_are_installed(library: str) -> None:
    assert library in _dockerfile_text()


def test_every_generated_import_is_covered_by_a_known_module() -> None:
    """`hve/artifact_validation.py` の生成プログラムに未知 import が増えたら検知する。"""
    discovered = {
        _top_level_module(module)
        for module in _GENERATED_IMPORT_PATTERN.findall(_artifact_validation_text())
    }
    assert discovered, "hve/artifact_validation.py の import 文を 1 件も検出できていない"
    unknown = discovered - _KNOWN_GENERATED_MODULES
    assert not unknown, (
        f"hve/artifact_validation.py に未知モジュール {sorted(unknown)} が増えた。"
        "Dockerfile の同梱配布と本テストの既知モジュール集合を更新すること"
    )


def test_pinned_distributions_match_the_validator_allowed_package_set() -> None:
    """同梱配布は validator が許容する配布集合（SSOT）と一致させる。"""
    groups = _VALIDATOR_PACKAGES_PATTERN.findall(_artifact_validation_text())
    assert groups, "hve/artifact_validation.py の `packages` 定義を検出できていない"
    allowed = {name for group in groups for name in group.split()}
    assert _pinned_distributions() == allowed


def test_every_pinned_distribution_uses_an_exact_version() -> None:
    """再現性のため範囲指定ではなく完全一致で固定する。"""
    assert _pinned_distributions()
    assert ">=" not in _dockerfile_text()


def test_dockerfile_uses_lf_without_bom() -> None:
    raw = _dockerfile_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
