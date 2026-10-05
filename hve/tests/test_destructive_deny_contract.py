"""NFR-SEC-04: Step セッションは CRITICAL なシェル操作だけを実行前に拒否し、記録する。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from copilot.generated.rpc import PermissionDecisionReject

from hve.config import SDKConfig
from hve.console import Console
from hve.permission_handler import build_step_permission_handler
from hve.runner import StepRunner

_CRITICAL_COMMANDS = [
    "rm -fr /",
    "rm -rf ~",
    "rm -rf .",
    "DROP TABLE users",
    "DROP DATABASE appdb",
    "TRUNCATE TABLE audit_log",
    "az resource delete --ids /subscriptions/000/resourceGroups/rg/providers/Microsoft.Web/sites/app",
    "az group delete --name rg-prod",
    "az deployment delete --name rollout --resource-group rg",
    "az keyvault delete --name kv-prod",
    "az storage account delete --name stprod --resource-group rg",
    "az cosmosdb delete --name cdb-prod --resource-group rg",
    "az sql server delete --name sql-prod --resource-group rg",
    "az functionapp delete --name func-prod --resource-group rg",
]

_NON_CRITICAL_COMMANDS = [
    "rm file.txt",
    "git push origin main",
    "git push origin main --force",
    "git reset --hard",
    "DELETE FROM users;",
    "pytest hve/tests/test_config.py -q",
]


def _shell_request(command: str) -> Any:
    # SDK の PermissionRequestShell はコマンド全文を full_command_text に持つ
    return SimpleNamespace(kind="shell", full_command_text=command)


def test_only_critical_patterns_are_denied() -> None:
    approved: list[str] = []
    warnings: list[str] = []

    def approve(request: Any, _invocation: Any) -> str:
        approved.append(getattr(request, "full_command_text", request.kind))
        return "approved"

    handler = build_step_permission_handler(approve, warn=warnings.append)

    for command in _CRITICAL_COMMANDS:
        assert isinstance(handler(_shell_request(command), {}), PermissionDecisionReject), command
    assert approved == []
    assert len(warnings) == len(_CRITICAL_COMMANDS)
    # 秘密値を含みうるコマンド本文は記録しない
    assert all("kv-prod" not in w and "rg-prod" not in w for w in warnings)

    for command in _NON_CRITICAL_COMMANDS:
        assert handler(_shell_request(command), {}) == "approved", command
    assert approved == _NON_CRITICAL_COMMANDS

    # シェル以外の権限要求は委譲する
    assert handler(SimpleNamespace(kind="write", file_name="docs/a.md"), {}) == "approved"


def test_step_sessions_use_critical_deny_handler() -> None:
    runner = StepRunner(
        config=SDKConfig(dry_run=True, model="claude-opus-4.7"),
        console=Console(verbose=False, quiet=True),
    )
    handler = runner._build_step_permission_handler("1.1", None)

    assert isinstance(handler(_shell_request("az group delete --name rg"), {}), PermissionDecisionReject)
    assert not isinstance(handler(_shell_request("pytest -q"), {}), PermissionDecisionReject)
