"""FR-CLI-88: GitHub MCP を宣言する場合の参照系 allowlist ガード。

PR / Issue（障害記録）は `mdq` / `cq` の索引対象外（FR-CQ-01 / FR-MDQ-02）であり、
参照するには `.github/.mcp.json` への宣言が必要になる。FR-CLI-76 は宣言外の
MCP サーバを自動探索で取り込まないため、プラグイン由来のサーバは届かない。

本テストは、宣言した場合に書き込み系ツールが混入しないことだけを固定する。
サーバー定義そのもの（command / url / tool 名）は利用者環境に依存するため、
本リポジトリでは確定させない。
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MCP_JSON = _REPO_ROOT / ".github" / ".mcp.json"
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"

#: 書き込み・状態変更を示す語。GitHub MCP の tool 名に現れたら参照系ではない。
WRITE_TOKENS = (
    "create",
    "update",
    "delete",
    "merge",
    "close",
    "push",
    "add",
    "remove",
    "assign",
    "dispatch",
    "write",
)


def _servers() -> dict:
    payload = json.loads(_MCP_JSON.read_text(encoding="utf-8-sig"))
    servers = payload.get("mcpServers")
    assert isinstance(servers, dict), "mcpServers が dict ではない"
    return servers


def _github_servers() -> dict:
    """GitHub を指すサーバを抽出する。

    サーバ名は利用者が自由に付けられるため、名前だけで判定すると
    `gh` / `pr-reader` のような命名でガードを回避できてしまう。
    接続先（command / args / url）に `github` が現れる場合も対象に含める。
    """
    matched = {}
    for name, spec in _servers().items():
        haystack = f"{name} {json.dumps(spec, ensure_ascii=False)}".lower()
        if "github" in haystack:
            matched[name] = spec
    return matched


def _requirement_block(requirement_id: str) -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"- **{requirement_id}**")]
    assert len(starts) == 1, f"{requirement_id} の定義行が {len(starts)} 件見つかった"
    block = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line)
    return "\n".join(block)


class TestDeclarationFile:
    def test_every_server_declares_its_tools(self) -> None:
        missing = [name for name, spec in _servers().items() if "tools" not in (spec or {})]
        assert not missing, f"tools 宣言の無い MCP サーバ: {missing}"


class TestGithubServerIsReadOnly:
    def test_no_wildcard_tools(self) -> None:
        offenders = [
            name for name, spec in _github_servers().items() if "*" in (spec.get("tools") or [])
        ]
        assert not offenders, (
            f"GitHub MCP へ tools: ['*'] を宣言している: {offenders}。"
            " 参照系だけを列挙すること（FR-CLI-88）"
        )

    def test_no_write_tools(self) -> None:
        offenders = []
        for name, spec in _github_servers().items():
            for tool in spec.get("tools") or []:
                lowered = str(tool).lower()
                if any(token in lowered for token in WRITE_TOKENS):
                    offenders.append(f"{name}:{tool}")
        assert not offenders, f"GitHub MCP に書き込み系ツールが含まれる: {offenders}"


class TestRequirementIsDeclared:
    def test_requirement_keeps_the_index_contracts_unchanged(self) -> None:
        block = _requirement_block("FR-CLI-88")
        assert "FR-CQ-01" in block
        assert "FR-MDQ-02" in block

    def test_requirement_requires_a_read_only_allowlist(self) -> None:
        block = _requirement_block("FR-CLI-88")
        assert "参照系" in block
        assert "FR-CLI-76" in block
