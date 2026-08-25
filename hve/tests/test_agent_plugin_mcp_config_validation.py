"""test_agent_plugin_mcp_config_validation.py — AG-CAP-09 の `mcp.json` 契約テスト。

Agent Plugins Specification 1.0.0 §7.2 の closed schema・transport・URL 制約・
資格情報の埋め込み禁止を決定的に検証する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_agent_plugin_mcp_config


_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _validate(config: object | None, *, required: bool = True) -> list[str]:
    with TemporaryDirectory() as tmp:
        agent_dir = Path(tmp) / "AG-01"
        agent_dir.mkdir(parents=True)
        if config is not None:
            text = config if isinstance(config, str) else json.dumps(config)
            (agent_dir / "mcp.json").write_text(text, encoding="utf-8")
        return validate_agent_plugin_mcp_config(agent_dir, required)


def _remote(**overrides: object) -> dict:
    server: dict = {"type": "streamable-http", "url": "https://example.invalid/mcp"}
    server.update(overrides)
    return {"$schema": _SCHEMA, "mcpServers": {"order-agent": server}}


class TestPresenceContract(unittest.TestCase):
    def test_absent_and_not_required_is_ok(self) -> None:
        self.assertEqual(_validate(None, required=False), [])

    def test_absent_but_required_is_rejected(self) -> None:
        errors = _validate(None, required=True)
        self.assertTrue(any("mcp.json not found" in e for e in errors), errors)

    def test_present_but_not_selected_is_rejected(self) -> None:
        """設計が採用していない公開設定を黙って同梱させない。"""
        errors = _validate(_remote(), required=False)
        self.assertTrue(any("does not select it" in e for e in errors), errors)


class TestSchemaContract(unittest.TestCase):
    def test_valid_remote_config_passes(self) -> None:
        self.assertEqual(_validate(_remote()), [])

    def test_valid_stdio_config_passes(self) -> None:
        config = {
            "$schema": _SCHEMA,
            "mcpServers": {
                "order-agent": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "order_agent"],
                    "env": {"ORDER_AGENT_MODE": "mcp"},
                }
            },
        }
        self.assertEqual(_validate(config), [])

    def test_invalid_json_is_reported(self) -> None:
        errors = _validate("{not json", required=True)
        self.assertTrue(any("not valid JSON" in e for e in errors), errors)

    def test_wrong_schema_version_is_rejected(self) -> None:
        config = _remote()
        config["$schema"] = "https://agent-plugins.org/schemas/0.9.0/mcp.schema.json"
        errors = _validate(config)
        self.assertTrue(any("$schema must be" in e for e in errors), errors)

    def test_extra_top_level_field_is_rejected(self) -> None:
        config = _remote()
        config["maxIterations"] = 3
        errors = _validate(config)
        self.assertTrue(any("outside the Agent Plugins" in e for e in errors), errors)

    def test_empty_servers_is_rejected(self) -> None:
        errors = _validate({"$schema": _SCHEMA, "mcpServers": {}})
        self.assertTrue(any("non-empty object" in e for e in errors), errors)

    def test_unknown_transport_is_rejected(self) -> None:
        errors = _validate(_remote(type="websocket"))
        self.assertTrue(any(".type must be one of" in e for e in errors), errors)

    def test_extra_server_field_is_rejected(self) -> None:
        errors = _validate(_remote(timeout=5))
        self.assertTrue(any("outside the MCP server schema" in e for e in errors), errors)


class TestTransportBoundary(unittest.TestCase):
    def test_stdio_must_not_declare_url(self) -> None:
        config = {
            "$schema": _SCHEMA,
            "mcpServers": {
                "s": {"type": "stdio", "command": "python", "url": "https://a.invalid"}
            },
        }
        errors = _validate(config)
        self.assertTrue(any("must not declare url" in e for e in errors), errors)

    def test_remote_must_not_declare_command(self) -> None:
        errors = _validate(_remote(command="python"))
        self.assertTrue(any("must not declare command" in e for e in errors), errors)

    def test_remote_must_not_declare_env(self) -> None:
        """仕様上リモートは url / headers だけを持つ。Prompt の記述と揃える。"""
        errors = _validate(_remote(env={"MODE": "mcp"}))
        self.assertTrue(any("command, args, or env" in e for e in errors), errors)

    def test_stdio_requires_command(self) -> None:
        config = {"$schema": _SCHEMA, "mcpServers": {"s": {"type": "stdio"}}}
        errors = _validate(config)
        self.assertTrue(any(".command must be" in e for e in errors), errors)


class TestUrlContract(unittest.TestCase):
    def test_non_loopback_http_is_rejected(self) -> None:
        errors = _validate(_remote(url="http://example.invalid/mcp"))
        self.assertTrue(any("must use HTTPS" in e for e in errors), errors)

    def test_loopback_http_is_allowed(self) -> None:
        self.assertEqual(_validate(_remote(url="http://localhost:3000/mcp")), [])

    def test_user_info_is_rejected(self) -> None:
        errors = _validate(_remote(url="https://user:pw@example.invalid/mcp"))
        self.assertTrue(any("must not contain user info" in e for e in errors), errors)

    def test_fragment_is_rejected(self) -> None:
        errors = _validate(_remote(url="https://example.invalid/mcp#tools"))
        self.assertTrue(any("must not contain a fragment" in e for e in errors), errors)

    def test_relative_url_is_rejected(self) -> None:
        errors = _validate(_remote(url="/mcp"))
        self.assertTrue(any("absolute http(s) URL" in e for e in errors), errors)

    def test_empty_host_is_rejected(self) -> None:
        errors = _validate(_remote(url="https:///mcp"))
        self.assertTrue(any("must declare a host" in e for e in errors), errors)

    def test_unparsable_ipv6_url_is_reported_not_raised(self) -> None:
        """`urlparse` の ValueError をゲート外へ伝播させない。"""
        errors = _validate(_remote(url="https://[::1/mcp"))
        self.assertTrue(any("not a parsable URL" in e for e in errors), errors)


class TestCredentialContract(unittest.TestCase):
    def test_literal_header_credential_is_rejected(self) -> None:
        errors = _validate(_remote(headers={"Authorization": "Bearer abc123"}))
        self.assertTrue(any("must not embed a credential" in e for e in errors), errors)

    def test_variable_reference_header_is_allowed(self) -> None:
        self.assertEqual(
            _validate(_remote(headers={"Authorization": "Bearer ${ORDER_TOKEN}"})), []
        )

    def test_literal_env_api_key_is_rejected(self) -> None:
        config = {
            "$schema": _SCHEMA,
            "mcpServers": {
                "s": {"type": "stdio", "command": "python", "env": {"API_KEY": "k-123"}}
            },
        }
        errors = _validate(config)
        self.assertTrue(any("must not embed a credential" in e for e in errors), errors)

    def test_reserved_variable_redefinition_is_rejected(self) -> None:
        config = {
            "$schema": _SCHEMA,
            "mcpServers": {
                "s": {"type": "stdio", "command": "python", "env": {"PLUGIN_ROOT": "/x"}}
            },
        }
        errors = _validate(config)
        self.assertTrue(any("reserved variable" in e for e in errors), errors)

    def test_literal_secret_in_a_non_credential_key_is_rejected(self) -> None:
        """キー名が無害でも値が secret らしければ拒否する。"""
        errors = _validate(_remote(headers={"X-Custom": "Bearer eyJhbGciOiJIUzI1.abcdefghij.klmnopqrst"}))
        self.assertTrue(any("secret-like" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
