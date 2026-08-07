"""Toolbox Deploy artifact gate の validator テスト。

FR-WF-AAGD-02。
生成された deploy / verify スクリプトが設計 TB-CAP どおりに
Toolbox を作成・検証するかを静的に照合する。
Azure への書き込みや live 呼び出しは行わない。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_ai_agent_deploy_artifacts

from hve.tests.test_ai_agent_capability_validation import _design_text
from hve.tests.test_toolbox_implementation_validation import (
    _disabled_blocks,
    _tb_blocks,
)

_CREATE_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)

# Toolbox version を Agent 登録より先に作成する（冪等）。
if ! curl -sf -H "Foundry-Features: Toolboxes=V1Preview" \\
  "${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions/${TOOLBOX_VERSION}" >/dev/null; then
  curl -sf -X POST \\
    -H "Foundry-Features: Toolboxes=V1Preview" \\
    -H "Authorization: Bearer ${TOKEN}" \\
    --data @toolbox-version.json \\
    "${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions"
fi

# Agent 登録は toolbox version 作成後に行う。
az cognitiveservices account project show --name "${ACCOUNT}" --resource-group "${RG}" --project-name "${PROJECT}"
curl -sf -X POST --data '{"tools": [{"type": "toolbox_search"}]}' "${PROJECT_ENDPOINT}/assistants"
"""

_VERIFY_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $1" >&2; exit 1; }

TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)
LIST=$(curl -sf -H "Foundry-Features: Toolboxes=V1Preview" "${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions/${TOOLBOX_VERSION}/tools/list") || fail "tools/list"

echo "${LIST}" | grep -q 'tool_search' || fail "tool search is not enabled"
echo "${LIST}" | grep -q "${PINNED_TOOLS}" || fail "pinned tools do not match TB-CAP-03"
curl -sf -X POST --data '{"query": "order lookup"}' "${PROJECT_ENDPOINT}/tool_search" || fail "tool_search"
curl -sf -X POST --data '{"name": "order-read"}' "${PROJECT_ENDPOINT}/call_tool" || fail "call_tool"
[[ "$(echo "${SEARCH_RESULT}" | jq 'length')" -le "${TOOL_SEARCH_LIMIT}" ]] || fail "limit"
[[ -n "${TOOLBOX_VERSION}" ]] || fail "toolbox version is not pinned"
exit 0
"""


def _write(
    root: Path,
    *,
    tb_blocks: str,
    create_script: str | None,
    verify_script: str | None,
) -> tuple[Path, Path]:
    detail = root / "docs" / "agent" / "agent-detail-AG-01.md"
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text(_design_text() + "\n" + tb_blocks, encoding="utf-8")

    infra = root / "src" / "infra" / "azure"
    infra.mkdir(parents=True, exist_ok=True)
    if create_script is not None:
        (infra / "create-azure-agent-resources.sh").write_text(
            create_script, encoding="utf-8"
        )
    if verify_script is not None:
        (infra / "verify-agent-resources.sh").write_text(verify_script, encoding="utf-8")
    return detail, infra


def _validate(
    *,
    tb_blocks: str = "",
    create_script: str | None = _CREATE_SCRIPT,
    verify_script: str | None = _VERIFY_SCRIPT,
    policy: str = "yes",
) -> list:
    with TemporaryDirectory() as temp_dir:
        detail, infra = _write(
            Path(temp_dir),
            tb_blocks=tb_blocks or _tb_blocks(),
            create_script=create_script,
            verify_script=verify_script,
        )
        return validate_ai_agent_deploy_artifacts(detail, infra, policy)


def _tb_errors(errors: list) -> list:
    return [error for error in errors if "TB-CAP" in error]


class TestEnabledDeployArtifacts(unittest.TestCase):
    def test_matching_scripts_pass(self) -> None:
        self.assertEqual(_tb_errors(_validate()), [], _tb_errors(_validate()))

    def test_missing_create_script_fails(self) -> None:
        errors = _tb_errors(_validate(create_script=None))
        self.assertTrue(any("create" in e.lower() for e in errors), errors)

    def test_missing_verify_script_fails(self) -> None:
        errors = _tb_errors(_validate(verify_script=None))
        self.assertTrue(any("verify" in e.lower() for e in errors), errors)

    def test_toolbox_created_after_agent_registration_fails(self) -> None:
        """Agent が参照する前に version が無いと登録が壊れる。"""
        reordered = _CREATE_SCRIPT.replace(
            "# Toolbox version を Agent 登録より先に作成する（冪等）。", ""
        )
        reordered = (
            'curl -sf -X POST --data \'{"tools": [{"type": "toolbox_search"}]}\' '
            '"${PROJECT_ENDPOINT}/assistants"\n' + reordered
        )
        errors = _tb_errors(_validate(create_script=reordered))
        self.assertTrue(any("before" in e.lower() for e in errors), errors)

    def test_missing_toolbox_search_tool_fails(self) -> None:
        errors = _tb_errors(
            _validate(create_script=_CREATE_SCRIPT.replace("toolbox_search", "other"))
        )
        self.assertTrue(any("toolbox_search" in e for e in errors), errors)

    def test_missing_preview_header_fails(self) -> None:
        errors = _tb_errors(
            _validate(create_script=_CREATE_SCRIPT.replace("Foundry-Features", "X-Other"))
        )
        self.assertTrue(any("foundry-features" in e.lower() for e in errors), errors)

    def test_missing_token_scope_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                create_script=_CREATE_SCRIPT.replace(
                    "https://ai.azure.com/.default", "https://management.azure.com/.default"
                )
            )
        )
        self.assertTrue(any("scope" in e.lower() for e in errors), errors)

    def test_missing_version_specific_endpoint_fails(self) -> None:
        errors = _tb_errors(
            _validate(create_script=_CREATE_SCRIPT.replace("/versions", "/latest"))
        )
        self.assertTrue(any("version" in e.lower() for e in errors), errors)


class TestVerifyScriptContract(unittest.TestCase):
    def _without(self, marker: str) -> list:
        return _tb_errors(_validate(verify_script=_VERIFY_SCRIPT.replace(marker, "noop")))

    def test_requires_initial_tools_list(self) -> None:
        self.assertTrue(any("tools/list" in e for e in self._without("tools/list")))

    def test_requires_pin_set_check(self) -> None:
        self.assertTrue(any("pin" in e.lower() for e in self._without("PINNED_TOOLS")))

    def test_requires_tool_search_discovery(self) -> None:
        self.assertTrue(any("tool_search" in e for e in self._without("tool_search")))

    def test_requires_call_tool(self) -> None:
        self.assertTrue(any("call_tool" in e for e in self._without("call_tool")))

    def test_requires_limit_check(self) -> None:
        self.assertTrue(any("limit" in e.lower() for e in self._without("TOOL_SEARCH_LIMIT")))

    def test_requires_version_check(self) -> None:
        self.assertTrue(any("version" in e.lower() for e in self._without("TOOLBOX_VERSION")))

    def test_must_fail_closed(self) -> None:
        """検証が落ちても exit 0 で通ると誤 GREEN になる。"""
        errors = _tb_errors(
            _validate(verify_script=_VERIFY_SCRIPT.replace("set -euo pipefail", "set +e"))
        )
        self.assertTrue(any("fail-closed" in e.lower() for e in errors), errors)


class TestDisabledToolSearch(unittest.TestCase):
    def test_no_toolbox_artifacts_passes(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_disabled_blocks(),
                create_script="#!/usr/bin/env bash\nset -euo pipefail\naz account show\n",
                verify_script="#!/usr/bin/env bash\nset -euo pipefail\naz account show\n",
                policy="no",
            )
        )
        self.assertEqual(errors, [], errors)

    def test_toolbox_creation_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_disabled_blocks(),
                create_script=_CREATE_SCRIPT,
                verify_script="#!/usr/bin/env bash\nset -euo pipefail\naz account show\n",
                policy="no",
            )
        )
        self.assertTrue(any("must not" in e.lower() for e in errors), errors)


class TestNoToolboxDesign(unittest.TestCase):
    def test_auto_without_tb_cap_is_noop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            detail, infra = _write(
                Path(temp_dir),
                tb_blocks="",
                create_script="#!/usr/bin/env bash\nset -euo pipefail\naz account show\n",
                verify_script="#!/usr/bin/env bash\nset -euo pipefail\naz account show\n",
            )
            errors = validate_ai_agent_deploy_artifacts(detail, infra, "auto")
        self.assertEqual(_tb_errors(errors), [], errors)


if __name__ == "__main__":
    unittest.main()
