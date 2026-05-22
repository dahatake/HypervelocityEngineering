"""hve/tests/test_auth_manifests.py — manifest スキーマ / ローダのテスト。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hve.gui.auth_providers.manifests import (
    Manifest,
    ManifestError,
    _parse_manifest,
    builtin_manifests_dir,
    load_all_manifests,
    load_manifest_for,
)


# ---------------------------------------------------------------------------
# パーサ単体
# ---------------------------------------------------------------------------


def test_parse_minimal_valid_manifest() -> None:
    """最小有効 manifest (id + match のみ) がパース成功する。"""
    data = {"id": "x", "match": {"provider_id_regex": "^x$"}}
    m = _parse_manifest(data)
    assert m.id == "x"
    assert m.match.provider_id_regex == "^x$"
    assert m.pre_auth_commands == []
    assert m.main_command is None


def test_parse_rejects_missing_id() -> None:
    with pytest.raises(ManifestError, match="id"):
        _parse_manifest({"match": {"provider_id_regex": ".*"}})


def test_parse_rejects_empty_match() -> None:
    with pytest.raises(ManifestError, match="match"):
        _parse_manifest({"id": "x", "match": {}})


def test_parse_rejects_invalid_regex() -> None:
    with pytest.raises(ManifestError, match="regex"):
        _parse_manifest({"id": "x", "match": {"provider_id_regex": "(unclosed"}})


def test_parse_pre_auth_commands() -> None:
    data = {
        "id": "x",
        "match": {"provider_id_regex": ".*"},
        "pre_auth_commands": [
            {"argv": ["echo", "ok"], "success_regex": "ok", "timeout": 5},
            {"argv": ["true"]},
        ],
    }
    m = _parse_manifest(data)
    assert len(m.pre_auth_commands) == 2
    assert m.pre_auth_commands[0].argv == ["echo", "ok"]
    assert m.pre_auth_commands[0].success_regex == "ok"
    assert m.pre_auth_commands[0].timeout == 5
    assert m.pre_auth_commands[1].timeout == 600.0  # default


def test_parse_rejects_argv_not_list() -> None:
    with pytest.raises(ManifestError, match="argv"):
        _parse_manifest(
            {
                "id": "x",
                "match": {"provider_id_regex": ".*"},
                "pre_auth_commands": [{"argv": "echo ok"}],
            }
        )


# ---------------------------------------------------------------------------
# 同梱 manifest
# ---------------------------------------------------------------------------


def test_builtin_manifests_dir_exists() -> None:
    assert builtin_manifests_dir().is_dir()


def test_load_all_manifests_contains_builtin() -> None:
    manifests = load_all_manifests()
    ids = {m.id for m in manifests}
    assert "azure_mcp" in ids
    assert "github_mcp" in ids
    assert "_default" in ids


# ---------------------------------------------------------------------------
# マッチング
# ---------------------------------------------------------------------------


def test_match_azure_mcp_by_server_name() -> None:
    m = load_manifest_for(mcp_server_name="azure")
    assert m is not None
    assert m.id == "azure_mcp"


def test_match_github_mcp_variant_name() -> None:
    m = load_manifest_for(mcp_server_name="github-mcp")
    assert m is not None
    assert m.id == "github_mcp"


def test_unknown_server_falls_back_to_default() -> None:
    """個別 manifest が無い場合は _default が返る。"""
    m = load_manifest_for(provider_id="mcp:unknown_xyz", mcp_server_name="unknown_xyz")
    assert m is not None
    assert m.id == "_default"


def test_returns_none_when_no_query() -> None:
    """マッチ条件が一切無ければ None。_default の provider_id_regex=.* も
    provider_id が None なら発火しない (仕様: provider_id が指定された時のみマッチ)。"""
    assert load_manifest_for() is None


# ---------------------------------------------------------------------------
# ユーザー manifest 上書き
# ---------------------------------------------------------------------------


def test_user_manifest_overrides_builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_dir = tmp_path / "manifests"
    user_dir.mkdir()
    override = user_dir / "azure_mcp.yaml"
    override.write_text(
        """
id: azure_mcp
display_name: "Azure MCP (user override)"
match:
  mcp_server_name_regex: "^(azure|az)(-mcp)?$"
notes_md: "user override"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HVE_AUTH_MANIFESTS_DIR", str(user_dir))
    m = load_manifest_for(mcp_server_name="azure")
    assert m is not None
    assert m.id == "azure_mcp"
    assert m.display_name == "Azure MCP (user override)"
