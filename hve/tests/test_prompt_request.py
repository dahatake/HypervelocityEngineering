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


class TestStepInputs:
    """FR-INPUT-06: workflows[].step_inputs は後方互換な任意field。"""

    def test_accepts_ordered_step_inputs(self):
        req = parse_request(
            _minimal(
                workflows=[
                    {
                        "workflow_id": "aas",
                        "steps": ["1"],
                        "step_inputs": [
                            {
                                "step_id": "1",
                                "role": "additional",
                                "source": "incoming/a.md",
                            },
                            {
                                "step_id": "1",
                                "role": "substitute",
                                "canonical": "docs/catalog/app-catalog.md",
                                "source": "incoming/b.docx",
                            },
                        ],
                    }
                ]
            )
        )
        assert [item.source for item in req.workflows[0].step_inputs] == [
            "incoming/a.md",
            "incoming/b.docx",
        ]
        assert req.workflows[0].step_inputs[1].canonical == "docs/catalog/app-catalog.md"

    def test_omitted_step_inputs_keeps_legacy_request(self):
        assert parse_request(_minimal()).workflows[0].step_inputs == ()

    def test_container_selection_allows_input_for_executable_child(self):
        req = parse_request(
            _minimal(
                workflows=[{
                    "workflow_id": "asdw-web",
                    "steps": ["1"],
                    "step_inputs": [{
                        "step_id": "1.1",
                        "role": "additional",
                        "source": "incoming/a.md",
                    }],
                }]
            )
        )
        assert req.workflows[0].step_inputs[0].step_id == "1.1"

    @pytest.mark.parametrize(
        "entry",
        [
            {"step_id": "1", "role": "unknown", "source": "a.md"},
            {"step_id": "1", "role": "substitute", "source": "a.md"},
            {"step_id": "999", "role": "additional", "source": "a.md"},
            {"step_id": "1", "role": "additional", "source": "a.md", "extra": True},
        ],
    )
    def test_rejects_invalid_step_input(self, entry):
        with pytest.raises(PromptRequestError):
            parse_request(
                _minimal(
                    workflows=[
                        {"workflow_id": "aas", "steps": ["1"], "step_inputs": [entry]}
                    ]
                )
            )


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

    def test_rejects_null_goal(self):
        with pytest.raises(PromptRequestError):
            parse_request(_minimal(goal=None))


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


class TestExecutionPolicy:
    """FR-PROMPT-13 — 事前承認の宣言（execution_policy）。"""

    @staticmethod
    def _deploy_request(policy: dict, resource_group: str | None = "rg-hve-dev") -> dict:
        workflow: dict = {"workflow_id": "asdw-web"}
        if resource_group is not None:
            workflow["params"] = {"resource_group": resource_group}
        return _minimal(workflows=[workflow], execution_policy=policy)

    def test_omitted_policy_keeps_legacy_request(self):
        req = parse_request(_minimal())
        assert req.execution_policy is None

    @pytest.mark.parametrize(
        "resource_group", ["rg;az group delete", "rg name", "rg$(id)", "a" * 91]
    )
    def test_rejects_resource_group_outside_azure_naming_rule(self, resource_group):
        # N-13: 計画の承認範囲と runner の宣言範囲を一致させるため、request 段階で拒否する。
        request = self._deploy_request(
            {"pre_approved_operations": ["azure_deploy"]}, resource_group
        )
        with pytest.raises(PromptRequestError, match="resource_group"):
            parse_request(request)
        with pytest.raises(PromptRequestError, match="resource_group"):
            parse_request(self._deploy_request({}, resource_group))

    def test_accepts_full_policy(self):
        req = parse_request(
            self._deploy_request(
                {
                    "unattended": True,
                    "pre_approved_operations": ["azure_deploy"],
                    "allow_public_exposure": False,
                    "budget_note": "月 5,000 円以内を目安",
                }
            )
        )
        policy = req.execution_policy
        assert policy is not None
        assert policy.unattended is True
        assert policy.pre_approved_operations == ("azure_deploy",)
        assert policy.allow_public_exposure is False
        assert policy.budget_note == "月 5,000 円以内を目安"

    def test_rejects_unknown_policy_field(self):
        with pytest.raises(PromptRequestError, match="execution_policy"):
            parse_request(_minimal(execution_policy={"unattended": True, "shell": "rm"}))

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_rejects_non_bool_unattended(self, value):
        with pytest.raises(PromptRequestError, match="unattended"):
            parse_request(_minimal(execution_policy={"unattended": value}))

    def test_rejects_operation_outside_allowlist(self):
        with pytest.raises(PromptRequestError, match="pre_approved_operations"):
            parse_request(
                self._deploy_request({"pre_approved_operations": ["delete_resource_group"]})
            )

    @pytest.mark.parametrize("resource_group", [None, "", "   "])
    def test_azure_deploy_requires_resource_group(self, resource_group):
        with pytest.raises(PromptRequestError, match="resource_group"):
            parse_request(
                self._deploy_request(
                    {"pre_approved_operations": ["azure_deploy"]},
                    resource_group=resource_group,
                )
            )

    def test_azure_deploy_requires_a_deploying_workflow(self):
        with pytest.raises(PromptRequestError, match="resource_group"):
            parse_request(
                _minimal(execution_policy={"pre_approved_operations": ["azure_deploy"]})
            )

    @pytest.mark.parametrize("note", ["x" * 201, "改行\nを含む", "制御\x07文字"])
    def test_rejects_unsafe_budget_note(self, note):
        with pytest.raises(PromptRequestError, match="budget_note"):
            parse_request(_minimal(execution_policy={"budget_note": note}))
