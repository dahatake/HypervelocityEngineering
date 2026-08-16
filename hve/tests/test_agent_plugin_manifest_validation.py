"""Agent Plugins Specification 1.0.0 準拠マニフェストの validator テスト。

FR-WF-AAGD-06。
仕様は <https://github.com/agentplugins/agent-plugins-spec>（2026-08-16 確認）。
`plugin.json` の必須フィールド・名前制約・closed schema を決定的に検証する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hve.artifact_validation import validate_agent_plugin_manifest

_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _manifest(**overrides: Any) -> dict:
    manifest = {
        "$schema": _SCHEMA,
        "name": "ag-01",
        "description": "Order resolution agent packaged as an Agent Plugin.",
        "version": "0.1.0",
    }
    manifest.update(overrides)
    return manifest


def _validate(
    manifest: "dict | str | None",
    *,
    agent_key: str = "AG-01",
) -> list:
    with TemporaryDirectory() as temp_dir:
        agent_dir = Path(temp_dir) / agent_key
        agent_dir.mkdir(parents=True, exist_ok=True)
        if manifest is not None:
            text = manifest if isinstance(manifest, str) else json.dumps(manifest)
            (agent_dir / "plugin.json").write_text(text, encoding="utf-8")
        return validate_agent_plugin_manifest(agent_dir, agent_key)


class TestManifestPresence(unittest.TestCase):
    def test_valid_manifest_passes(self) -> None:
        self.assertEqual(_validate(_manifest()), [])

    def test_missing_manifest_fails(self) -> None:
        errors = _validate(None)
        self.assertTrue(any("plugin.json" in error for error in errors), errors)

    def test_invalid_json_fails(self) -> None:
        errors = _validate("{not json")
        self.assertTrue(errors)

    def test_non_object_root_fails(self) -> None:
        errors = _validate("[]")
        self.assertTrue(errors)


class TestSchemaIdentifier(unittest.TestCase):
    def test_missing_schema_fails(self) -> None:
        manifest = _manifest()
        del manifest["$schema"]
        self.assertTrue(_validate(manifest))

    def test_other_schema_identifier_fails(self) -> None:
        errors = _validate(
            _manifest(**{"$schema": "https://agent-plugins.org/schemas/0.9.0/plugin.schema.json"})
        )
        self.assertTrue(any("$schema" in error for error in errors), errors)


class TestNameConstraints(unittest.TestCase):
    def test_name_must_equal_the_lowercased_fanout_key(self) -> None:
        errors = _validate(_manifest(name="other-agent"))
        self.assertTrue(any("ag-01" in error for error in errors), errors)

    def test_uppercase_key_is_not_accepted_verbatim(self) -> None:
        """`AG-01` は仕様 §5.5 の文字集合を満たさない。"""
        self.assertTrue(_validate(_manifest(name="AG-01")))

    def test_missing_name_fails(self) -> None:
        manifest = _manifest()
        del manifest["name"]
        self.assertTrue(_validate(manifest))

    def test_empty_name_fails(self) -> None:
        self.assertTrue(_validate(_manifest(name=""), agent_key=""))

    def test_leading_hyphen_fails(self) -> None:
        self.assertTrue(_validate(_manifest(name="-ag-01"), agent_key="-AG-01"))

    def test_trailing_period_fails(self) -> None:
        self.assertTrue(_validate(_manifest(name="ag-01."), agent_key="AG-01."))

    def test_consecutive_hyphens_fail(self) -> None:
        self.assertTrue(_validate(_manifest(name="ag--01"), agent_key="AG--01"))

    def test_consecutive_periods_fail(self) -> None:
        self.assertTrue(_validate(_manifest(name="ag..01"), agent_key="AG..01"))

    def test_name_longer_than_64_characters_fails(self) -> None:
        key = "a" * 65
        self.assertTrue(_validate(_manifest(name=key), agent_key=key))

    def test_name_of_exactly_64_characters_passes(self) -> None:
        key = "a" * 64
        self.assertEqual(_validate(_manifest(name=key), agent_key=key), [])

    def test_periods_are_allowed(self) -> None:
        self.assertEqual(
            _validate(_manifest(name="acme.tools"), agent_key="Acme.Tools"), []
        )


class TestClosedSchema(unittest.TestCase):
    def test_unknown_top_level_field_fails(self) -> None:
        errors = _validate(_manifest(max_iterations=3))
        self.assertTrue(any("max_iterations" in error for error in errors), errors)

    def test_specification_optional_fields_are_accepted(self) -> None:
        """仕様 §5.4 の任意フィールドを利用者が追記しても壊さない。"""
        self.assertEqual(
            _validate(_manifest(license="MIT", keywords=["agent"])),
            [],
        )


class TestGeneratedFields(unittest.TestCase):
    def test_description_is_required_by_hve(self) -> None:
        manifest = _manifest()
        del manifest["description"]
        self.assertTrue(_validate(manifest))

    def test_version_is_required_by_hve(self) -> None:
        manifest = _manifest()
        del manifest["version"]
        self.assertTrue(_validate(manifest))

    def test_blank_description_fails(self) -> None:
        self.assertTrue(_validate(_manifest(description="   ")))


class TestImplementationGateIntegration(unittest.TestCase):
    def test_missing_manifest_fails_the_implementation_gate(self) -> None:
        from hve.artifact_validation import validate_ai_agent_implementation_artifacts
        from hve.tests.test_ai_agent_capability_validation import (
            _write_design,
            _write_implementation,
        )

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            detail = _write_design(root)
            agent_dir, test_spec = _write_implementation(root)
            (agent_dir / "plugin.json").unlink(missing_ok=True)
            errors = validate_ai_agent_implementation_artifacts(
                detail, agent_dir, test_spec
            )
        self.assertTrue(any("plugin.json" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
