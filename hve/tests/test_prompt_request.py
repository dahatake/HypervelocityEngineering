"""FR-PROMPT-02 — Prompt 版 request v1 の schema と fail-closed 検証の契約テスト。

本テストは実装前の RED として追加する。HVE Python は自然言語生成物（LLM が
組み立てた request）を信用せず、schema・registry・allowlist で再検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hve import prompt_request
from hve.prompt_request import PromptRequestError, load_request, parse_request


def _minimal(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "goal": "要求定義を作りたい",
        "workflows": [{"workflow_id": "ard"}],
    }
    data.update(overrides)
    return data


class TestSchemaVersion:
    def test_accepts_version_1(self):
        req = parse_request(_minimal())
        assert req.schema_version == 1

    @pytest.mark.parametrize("value", [0, 2, "1", 1.0, None, True])
    def test_rejects_non_integer_or_unknown_major(self, value):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(schema_version=value))

    def test_rejects_missing_schema_version(self):
        data = _minimal()
        del data["schema_version"]
        with pytest.raises(PromptRequestError):
            parse_request(data)


class TestUnknownFields:
    def test_rejects_unknown_top_level_field(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(shell_command="rm -rf /"))

    def test_rejects_unknown_workflow_field(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(workflows=[{"workflow_id": "ard", "env": {"TOKEN": "x"}}]))

    def test_rejects_unknown_alias_field(self):
        data = _minimal(
            workflows=[
                {
                    "workflow_id": "ard",
                    "input_aliases": [
                        {"canonical": "a.md", "actual": "b.md", "copy": True}
                    ],
                }
            ]
        )
        with pytest.raises(PromptRequestError):
            parse_request(data)


class TestWorkflowsField:
    def test_rejects_empty_workflows(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(workflows=[]))

    def test_rejects_duplicate_workflow(self):
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(workflows=[{"workflow_id": "ard"}, {"workflow_id": "ard"}])
            )

    def test_rejects_duplicate_after_alias_resolution(self):
        """`aad` は registry の alias で `aad-web` へ解決されるため重複になる。"""
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(workflows=[{"workflow_id": "aad"}, {"workflow_id": "aad-web"}])
            )

    def test_rejects_unknown_workflow_id(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(workflows=[{"workflow_id": "no-such-workflow"}]))

    def test_canonicalizes_workflow_id_and_keeps_requested(self):
        req = parse_request(_minimal(workflows=[{"workflow_id": "AAD"}]))
        assert req.workflows[0].workflow_id == "aad-web"
        assert req.workflows[0].requested_workflow_id == "AAD"


class TestSteps:
    def test_accepts_existing_step_ids(self):
        req = parse_request(_minimal(workflows=[{"workflow_id": "ard", "steps": ["1"]}]))
        assert req.workflows[0].steps == ("1",)

    def test_rejects_unknown_step_id(self):
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(workflows=[{"workflow_id": "ard", "steps": ["999.999"]}])
            )

    def test_rejects_non_string_step(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(workflows=[{"workflow_id": "ard", "steps": [1]}]))

    def test_unspecified_steps_is_empty(self):
        req = parse_request(_minimal())
        assert req.workflows[0].steps == ()


class TestParamsAllowlist:
    def test_accepts_declared_workflow_param(self):
        req = parse_request(
            _minimal(workflows=[{"workflow_id": "ard", "params": {"company_name": "例"}}])
        )
        assert req.workflows[0].params["company_name"] == "例"

    def test_rejects_param_not_declared_by_workflow(self):
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(
                    workflows=[{"workflow_id": "ard", "params": {"target_dirs": "src"}}]
                )
            )

    def test_rejects_non_string_param_value(self):
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(workflows=[{"workflow_id": "ard", "params": {"company_name": 1}}])
            )


class TestSettingsOverridesAllowlist:
    def test_accepts_allowlisted_override(self):
        req = parse_request(_minimal(settings_overrides={"reasoning_effort": "high"}))
        assert req.settings_overrides["reasoning_effort"] == "high"

    @pytest.mark.parametrize(
        "key",
        [
            "token",
            "password",
            "github_token",
            "cli_path",
            "env",
            "mcp_config",
            "repo_root",
        ],
    )
    def test_rejects_credential_and_execution_surface_keys(self, key):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(settings_overrides={key: "x"}))

    @pytest.mark.parametrize("key", ["dry_run", "workbench", "steps", "workflow"])
    def test_rejects_prompt_cli_owned_keys(self, key):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(settings_overrides={key: "x"}))

    def test_allowlist_excludes_all_credential_like_names(self):
        lowered = {k.lower() for k in prompt_request.ALLOWED_SETTINGS_OVERRIDES}
        for needle in ("token", "password", "secret", "credential", "key"):
            assert not any(needle in k for k in lowered), needle


class TestGoal:
    def test_goal_is_kept_verbatim(self):
        req = parse_request(_minimal(goal="  複数行\nの目的  "))
        assert req.goal == "  複数行\nの目的  "

    def test_rejects_non_string_goal(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(goal=["a"]))

    def test_goal_is_optional(self):
        data = _minimal()
        del data["goal"]
        assert parse_request(data).goal == ""


class TestLoadRequest:
    def test_loads_utf8_json_file(self, tmp_path: Path):
        p = tmp_path / "request.json"
        p.write_text(json.dumps(_minimal(), ensure_ascii=False), encoding="utf-8")
        assert load_request(p).workflows[0].workflow_id == "ard"

    def test_rejects_duplicate_keys(self, tmp_path: Path):
        p = tmp_path / "request.json"
        p.write_text(
            '{"schema_version": 1, "schema_version": 1, "workflows": [{"workflow_id": "ard"}]}',
            encoding="utf-8",
        )
        with pytest.raises(PromptRequestError):
            load_request(p)

    def test_rejects_non_object_root(self, tmp_path: Path):
        p = tmp_path / "request.json"
        p.write_text("[]", encoding="utf-8")
        with pytest.raises(PromptRequestError):
            load_request(p)

    def test_rejects_missing_file(self, tmp_path: Path):
        with pytest.raises(PromptRequestError):
            load_request(tmp_path / "absent.json")

    def test_rejects_invalid_json(self, tmp_path: Path):
        p = tmp_path / "request.json"
        p.write_text("{", encoding="utf-8")
        with pytest.raises(PromptRequestError):
            load_request(p)


class TestRequirementIsDeclared:
    def test_fr_prompt_02_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-02**" in text
