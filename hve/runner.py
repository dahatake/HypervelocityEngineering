"""runner.py — StepRunner: 1 ステップを CopilotSession で実行する"""

from __future__ import annotations

import asyncio
import copy
import json
import ntpath
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

try:
    from .prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level `import runner` compatibility
    from prompt_loader import load_prompt_file  # type: ignore[import-not-found,no-redef]

if __package__:
    from .artifact_validation import (
        _ASDW_AUDIT_MODE_ACL_DIRECT,
        _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
        _ASDW_DATA_DEPLOY_NETWORK_KEYS,
        find_missing_output_paths,
    )
    from .asdw_data_script_generator import (
        AsdwDataScriptGenerationError,
        ensure_asdw_data_producers,
    )
    from .asdw_data_script_launcher import (
        ScriptLauncherError,
        execute_pipeline,
        resolve_azure_cli_executable,
    )
    from .asdw_data_runtime_context import (
        AsdwDataDeployContextError,
        build_asdw_data_deploy_bootstrap_context,
    )
    from .fanout_expander import resolve_output_path_prefix_gates
    from .runtime_observability import extract_usage_credit_fields, is_plain_repo_path_token
    from .workflow_registry import (
        ASDW_DATA_DEPLOY_SUPPORTED_APP_ID as _ASDW_SUPPORTED_APP_ID,
    )
else:  # pragma: no cover - top-level runner compatibility
    from artifact_validation import (  # type: ignore[import-not-found,no-redef]
        _ASDW_AUDIT_MODE_ACL_DIRECT,
        _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
        _ASDW_DATA_DEPLOY_NETWORK_KEYS,
        find_missing_output_paths,
    )
    from asdw_data_script_generator import (  # type: ignore[import-not-found,no-redef]
        AsdwDataScriptGenerationError,
        ensure_asdw_data_producers,
    )
    from asdw_data_script_launcher import (  # type: ignore[import-not-found,no-redef]
        ScriptLauncherError,
        execute_pipeline,
        resolve_azure_cli_executable,
    )
    from asdw_data_runtime_context import (  # type: ignore[import-not-found,no-redef]
        AsdwDataDeployContextError,
        build_asdw_data_deploy_bootstrap_context,
    )
    from fanout_expander import (  # type: ignore[import-not-found,no-redef]
        resolve_output_path_prefix_gates,
    )
    from runtime_observability import (  # type: ignore[import-not-found,no-redef]
        extract_usage_credit_fields,
        is_plain_repo_path_token,
    )
    from workflow_registry import (  # type: ignore[import-not-found,no-redef]
        ASDW_DATA_DEPLOY_SUPPORTED_APP_ID as _ASDW_SUPPORTED_APP_ID,
    )

# 同時 stdin アクセスを防止し、全ステップで共有される sys.stdin を順番に利用させる。
# asyncio.Lock により同一イベントループ内の複数コルーチンからの同時入力を直列化する。
# Python 3.10+ の DeprecationWarning を回避するため、イベントループ起動後に遅延生成する。
_stdin_lock: Optional[asyncio.Lock] = None


def _get_stdin_lock() -> asyncio.Lock:
    """asyncio.Lock を遅延生成して返す（イベントループ起動後に初回生成）。"""
    global _stdin_lock
    if _stdin_lock is None:
        _stdin_lock = asyncio.Lock()
    return _stdin_lock


def _safe_run_id(run_id: str) -> str:
    """run_id を安全なパスコンポーネントに正規化する。

    - 空の場合は generate_run_id() で自動生成（StepRunner 単独使用への対応）
    - 許可文字: 英数字・ハイフン・アンダースコアのみ（`/` や `..` 等のパストラバーサル文字を除去）
    """
    rid = run_id or generate_run_id()
    # 安全でない文字を除去（英数字・ハイフン・アンダースコア以外）
    rid = re.sub(r"[^A-Za-z0-9\-_]", "", rid)
    # 除去の結果が空になった場合もフォールバック生成
    return rid or generate_run_id()


def _work_identifier_for_step(step_id: str, fanout_meta: Optional[Dict[str, Any]]) -> str:
    """Agent Prompt の WORK `Issue-<識別子>` に使う識別子を返す。

    非 fan-out Step は既存互換の `0` を維持する。fan-out 子だけ step_id 由来の
    パス安全な識別子にして、並列子が同じ `Issue-0` を共有しないようにする。
    """
    if not fanout_meta or not fanout_meta.get("fanout_key"):
        return "0"
    token = str(step_id or "").strip()
    if not token:
        return "0"
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", token).strip("-")
    return f"step-{safe}" if safe else "0"


def _safe_work_path_component(value: str, label: str) -> str:
    """Return one direct path component for a run-scoped work directory."""
    component = str(value or "").strip()
    if (
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        or "\x00" in component
        or Path(component).is_absolute()
    ):
        raise ValueError(f"unsafe {label} work path component: {value!r}")
    return component


def _step_work_dir(
    custom_agent: Optional[str],
    identifier: str,
) -> Path:
    """Return the run-scoped work directory for one Step without creating it."""
    try:
        from .split_fork import resolve_work_root
    except ImportError:  # pragma: no cover
        from split_fork import resolve_work_root  # type: ignore[no-redef]

    safe_identifier = _safe_work_path_component(identifier, "identifier")
    work_root = resolve_work_root().resolve()
    issue_dir = f"Issue-{safe_identifier}"
    target = (
        work_root
        / _safe_work_path_component(custom_agent, "custom_agent")
        / issue_dir
        if custom_agent
        else work_root / issue_dir
    )
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(work_root)
    except ValueError as exc:
        raise ValueError(
            f"step work directory escapes HVE_WORK_ROOT: {resolved_target}"
        ) from exc
    return resolved_target


def _ensure_step_work_dir(
    custom_agent: Optional[str],
    identifier: str,
) -> Path:
    """Create the exact run-scoped Step work directory before Agent startup."""
    work_dir = _step_work_dir(custom_agent, identifier)
    work_dir.mkdir(parents=True, exist_ok=True)
    if not work_dir.is_dir():
        raise OSError(f"step work directory was not created: {work_dir}")
    return work_dir


# FR-WF-AAG-01: 生成する AI Agent の Tool Search 方針を注入する Step。
_TOOL_SEARCH_POLICY_STEPS: Dict[str, Tuple[str, ...]] = {
    "aag": ("3",),
    "aagd": ("2.3", "3", "4"),
}


def _tool_search_policy_prefix(
    workflow_id: Optional[str],
    step_id: str,
    policy: str,
) -> str:
    """対象 Step の Prompt へ生成 AI Agent の Tool Search 方針を注入する。

    利用者が指定した値をそのまま渡し、Agent 側で既定へ丸めさせない。
    非対象 Step には何も足さない（Prompt を変えない）。
    """
    steps = _TOOL_SEARCH_POLICY_STEPS.get((workflow_id or "").strip().casefold())
    if not steps or str(step_id).split("/", 1)[0] not in steps:
        return ""
    return (
        "## 生成する AI Agent の Tool Search 方針\n"
        f"- 方針: `{policy}`\n"
        "- これは利用者指定であり、Agent の判断・追加コメントで上書きしない。\n"
        "- `auto` / `yes` / `no` 以外なら推測せず、blocked として停止する。"
    )


# FR-WF-AAG-03: 生成する AI Agent の Agentic Retrieval 方針を注入する Step。
# Step 4 は tool search 専用評価のため対象外。
_AGENTIC_RETRIEVAL_POLICY_STEPS: Dict[str, Tuple[str, ...]] = {
    "aag": ("3",),
    "aagd": ("2.3", "3"),
}


def _agentic_retrieval_policy_prefix(
    workflow_id: Optional[str],
    step_id: str,
    policy: str,
) -> str:
    """対象 Step の Prompt へ生成 AI Agent の Agentic Retrieval 方針を注入する。

    同じ Step へ Tool Search 方針も注入されるため、見出しを別にする。
    """
    steps = _AGENTIC_RETRIEVAL_POLICY_STEPS.get((workflow_id or "").strip().casefold())
    if not steps or str(step_id).split("/", 1)[0] not in steps:
        return ""
    return (
        "## 生成する AI Agent の Agentic Retrieval 方針\n"
        f"- 方針: `{policy}`\n"
        "- これは利用者指定であり、Agent の判断・追加コメントで上書きしない。\n"
        "- `auto` / `yes` / `no` 以外なら推測せず、blocked として停止する。"
    )


def _repository_skill_directories(
    skill_names: Optional[List[str]] = None,
) -> List[str]:
    """Return repository Skill discovery directories scoped to declared Skills.

    FR-CLI-73: 公開するのは `.github/skills` root と、当該 active Step が宣言した
    Skill（`required_skills` / インストール済み optional）のディレクトリだけ。
    root 直下の全ディレクトリを無条件に公開してはならない。

    CLI のスキル発見は深さ 1 (`<dir>/<name>/SKILL.md`) のみ走査するため、
    `azure-skills/azure-cli-deploy-scripts` のようなネスト配置 Skill は
    その親ディレクトリ (`<root>/azure-skills`) を公開して発見可能にする。
    """
    skills_dir = Path.cwd() / ".github" / "skills"
    if not skills_dir.is_dir():
        return []
    directories = [str(skills_dir)]
    if not skill_names:
        return directories

    try:
        from .skill_resolver import discover_available_skills, resolve_skill_alias
    except ImportError:  # pragma: no cover - top-level runner compatibility
        from skill_resolver import (  # type: ignore[import-not-found,no-redef]
            discover_available_skills,
            resolve_skill_alias,
        )

    available = discover_available_skills()
    seen: set[str] = {os.path.normcase(os.path.normpath(str(skills_dir)))}
    for raw_name in skill_names:
        subpath = available.get(resolve_skill_alias(str(raw_name)))
        if not subpath:
            # external Skill / 未知の Skill は本関数の対象外（別経路で公開される）
            continue
        parent = (skills_dir / subpath).parent
        normalized = os.path.normcase(os.path.normpath(str(parent)))
        if normalized in seen:
            continue
        seen.add(normalized)
        directories.append(str(parent))
    return directories


_ASDW_DATA_REGISTRATION_SCRIPT = "src/data/azure/data-registration-script.sh"
_ASDW_DATA_PREP_SCRIPT = "src/infra/azure/create-azure-data-resources-prep.sh"
_ASDW_DATA_CREATE_SCRIPT = "src/infra/azure/create-azure-data-resources.sh"
_ASDW_DATA_DEPLOY_SUPPORTED_APP_ID = _ASDW_SUPPORTED_APP_ID


def format_exception_for_log(exc: BaseException) -> str:
    """例外を `型名: メッセージ` 形式へ整形する（NFR-OBS-08）。

    `str(exc)` だけでは `KeyError('1.1')` が `'1.1'` としか出力されず、
    同じ表示のまま原因不明の失敗が反復する。少なくとも例外型名を残す。
    """
    message = str(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
_ASDW_DATA_DEPLOY_COMMON_ENVIRONMENT_KEYS = (
    "RESOURCE_GROUP",
    "LOCATION",
    "SUBSCRIPTION_ID",
    *_ASDW_DATA_DEPLOY_NETWORK_KEYS,
    "DATA_VERIFY_ACR_NAME",
    "DATA_VERIFY_IMAGE_NAME",
    "DATA_VERIFY_ACI_IMAGE",
    "SQL_SERVER",
    "SQL_HOST",
    "SQL_DATABASE",
    "SQL_DB_SVC01",
    "SQL_DB_SVC02",
    "SQL_DB_SVC03",
    "SQL_DB_SVC07",
    "SQL_DB_SVC09",
    "COSMOS_ACCOUNT",
    "COSMOS_ENDPOINT",
    "COSMOS_DATABASE",
    "COSMOS_CONTAINER_VOC",
    "CONFIDENTIAL_LEDGER_NAME",
    "CONFIDENTIAL_LEDGER_ENDPOINT",
)
_ASDW_DATA_DEPLOY_AUDIT_ENVIRONMENT_KEYS = {
    _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST: (
        "SQL_DB_SVC12",
        "SQL_AUDIT_TABLE",
    ),
    _ASDW_AUDIT_MODE_ACL_DIRECT: ("CONFIDENTIAL_LEDGER_COLLECTION",),
}
# `DATA_VERIFY_ACR_NAME` / `DATA_VERIFY_ACI_IMAGE` は bootstrap context が
# RESOURCE_GROUP と RESOURCE_SUFFIX から導出するため、ここでは写像しない。
# Azure がマネージド ID の clientId を prep stage で採番するため、run 開始時点の
# snapshot では解決できない唯一の宣言キーとして launcher が読み戻す。
_ASDW_DATA_DEPLOY_READ_BACK_KEY = "DATA_DEPLOY_IDENTITY_CLIENT_ID"
_ASDW_DATA_DEPLOY_BOOTSTRAP_PARAM_KEYS = {
    "LOCATION": "data_location",
    "RESOURCE_SUFFIX": "data_resource_suffix",
    "DATA_VNET_CIDR": "data_vnet_cidr",
    "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": "data_private_endpoint_subnet_cidr",
    "DATA_ACI_SUBNET_CIDR": "data_aci_subnet_cidr",
}
_ASDW_DATA_DEPLOY_HVE_OWNED_ENVIRONMENT_KEYS = frozenset(
    {
        *_ASDW_DATA_DEPLOY_COMMON_ENVIRONMENT_KEYS,
        *(
            key
            for keys in _ASDW_DATA_DEPLOY_AUDIT_ENVIRONMENT_KEYS.values()
            for key in keys
        ),
        "DATA_CREATE_RUN_ID",
        "DATA_REGISTER_RUN_ID",
        "DATA_VERIFY_RUN_ID",
        "AUDIT_RECORD_JSON",
        "HVE_ASDW_SAMPLE_DATA_JSON",
        "HVE_ASDW_SCRIPT_DIR",
        "HVE_ASDW_SCRIPT_STAGE",
        "DATA_DEPLOY_ENV",
        "SAMPLE_DATA",
        "WORK_DIR",
    }
)
_ASDW_DATA_DEPLOY_PIPELINE_SEQUENCE = (
    ("prep", 1),
    ("create", 1),
    ("registration", 1),
    ("verify", 1),
    ("create", 2),
    ("registration", 2),
    ("verify", 2),
)
_ASDW_DATA_DEPLOY_MICROSOFT_LEARN_SERVER = "microsoft-learn"
_ASDW_DATA_DEPLOY_MICROSOFT_LEARN_CONFIG = {
    "type": "http",
    "url": "https://learn.microsoft.com/api/mcp",
    "tools": ["*"],
}
_FOUNDRY_REQUIRED_AZURE_MCP_SERVER = "azure"
_FOUNDRY_REQUIRED_AZURE_MCP_CONFIG = {
    "tools": ["*"],
    "command": "npx",
    "args": ["-y", "@azure/mcp@latest", "server", "start"],
}
_FOUNDRY_REQUIRED_MCP_SERVERS = {
    _FOUNDRY_REQUIRED_AZURE_MCP_SERVER: _FOUNDRY_REQUIRED_AZURE_MCP_CONFIG,
    _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_SERVER: _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_CONFIG,
}
def _permission_path_has_reparse_point(path_stat: os.stat_result) -> bool:
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    return bool(int(getattr(path_stat, "st_file_attributes", 0)) & reparse_flag)


def _permission_path_has_windows_alias(raw_path: str) -> bool:
    """Reject ADS, reserved devices, and Win32 trailing-dot/space aliases."""
    drive, drive_tail = ntpath.splitdrive(raw_path)
    if drive and not drive_tail.startswith(("\\", "/")):
        return True
    candidate = Path(raw_path)
    reserved = re.compile(
        r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|"
        r"COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
        re.IGNORECASE,
    )
    for index, part in enumerate(candidate.parts):
        if index == 0 and part == candidate.anchor:
            continue
        if not part or part.endswith((".", " ")):
            return True
        if (
            ":" in part
            or reserved.fullmatch(part)
            or (
                hasattr(ntpath, "isreserved")
                and ntpath.isreserved(part)
            )
        ):
            return True
    return False


def _permission_repo_relative_path(
    path: Any,
    *,
    require_exists: bool = False,
    require_regular_file: bool = False,
) -> Optional[str]:
    """Return a direct repository-relative path, rejecting aliases and escapes."""
    raw_path = str(path or "")
    if (
        not raw_path
        or raw_path != raw_path.strip()
        or "\x00" in raw_path
        or _permission_path_has_windows_alias(raw_path)
        or any(
            part in {".", ".."}
            for part in raw_path.replace("\\", "/").split("/")
        )
    ):
        return None
    try:
        repo_root = Path.cwd().resolve()
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        lexical = Path(os.path.abspath(candidate))
        if require_exists and not lexical.exists():
            return None
        resolved = candidate.resolve(strict=False)
        lexical_relative = lexical.relative_to(repo_root)
        resolved_relative = resolved.relative_to(repo_root)
        if os.path.normcase(os.path.normpath(lexical)) != os.path.normcase(
            os.path.normpath(resolved)
        ):
            return None
        if os.path.normcase(os.path.normpath(lexical_relative)) != os.path.normcase(
            os.path.normpath(resolved_relative)
        ):
            return None

        current = repo_root
        for part in lexical_relative.parts:
            current = current / part
            if not current.exists():
                break
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode) or _permission_path_has_reparse_point(
                current_stat
            ):
                return None
        if lexical.exists():
            final_stat = os.lstat(lexical)
            if require_regular_file and not stat.S_ISREG(final_stat.st_mode):
                return None
            if stat.S_ISREG(final_stat.st_mode) and final_stat.st_nlink != 1:
                return None
        return resolved_relative.as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


def _read_repository_mcp_config(repo_root: Path) -> Dict[str, Any]:
    """Return the `mcpServers` map declared in the repository-pinned MCP config."""
    if repo_root.resolve() != Path.cwd().resolve():
        return {}
    config_relative = _permission_repo_relative_path(
        ".github/.mcp.json",
        require_exists=True,
        require_regular_file=True,
    )
    if config_relative is None:
        return {}
    try:
        payload = json.loads((repo_root / config_relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}
    servers = payload.get("mcpServers") if isinstance(payload, dict) else None
    return servers if isinstance(servers, dict) else {}


def _load_repository_pinned_mcp_servers(
    repo_root: Path,
    expected_servers: Dict[str, Any],
) -> Dict[str, Any]:
    """Load an exact named subset from the repository-pinned MCP config."""
    servers = _read_repository_mcp_config(repo_root)
    if not servers:
        return {}
    configured = {name: servers.get(name) for name in expected_servers}
    if configured != expected_servers:
        return {}
    return copy.deepcopy(expected_servers)


def _load_trusted_asdw_data_deploy_mcp_servers(
    repo_root: Path,
) -> Dict[str, Any]:
    """Load only the repository-pinned official Microsoft Learn MCP endpoint."""
    return _load_repository_pinned_mcp_servers(
        repo_root,
        {
            _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_SERVER: (
                _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_CONFIG
            )
        },
    )


def _load_trusted_foundry_mcp_servers(repo_root: Path) -> Dict[str, Any]:
    """Load the exact Azure and Microsoft Learn MCP servers for Foundry Steps."""
    return _load_repository_pinned_mcp_servers(
        repo_root,
        _FOUNDRY_REQUIRED_MCP_SERVERS,
    )


def _require_trusted_asdw_data_deploy_mcp_servers(
    repo_root: Path,
) -> Dict[str, Any]:
    """Return the one pinned server or fail before a DataDeploy session starts."""
    servers = _load_trusted_asdw_data_deploy_mcp_servers(repo_root)
    expected = {
        _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_SERVER: dict(
            _ASDW_DATA_DEPLOY_MICROSOFT_LEARN_CONFIG
        )
    }
    if servers != expected:
        raise RuntimeError(
            "ASDW Step 1.3 requires the repository-pinned Microsoft Learn "
            "MCP server before session creation."
        )
    return servers


def _require_trusted_foundry_mcp_servers(repo_root: Path) -> Dict[str, Any]:
    """Return the pinned Foundry MCP subset or fail before session creation."""
    servers = _load_trusted_foundry_mcp_servers(repo_root)
    if servers != _FOUNDRY_REQUIRED_MCP_SERVERS:
        raise RuntimeError(
            "Foundry-required Step requires repository-pinned Azure and "
            "Microsoft Learn MCP servers before session creation."
        )
    return servers


def _validate_asdw_data_deploy_runtime_context(
    validated_run_id: str,
    repo_root: Path,
) -> List[str]:
    """Validate the exact run root and pinned documentation server pre-session."""
    errors: List[str] = []
    resolved_repo_root = repo_root.resolve()
    expected_work_root = (
        resolved_repo_root / "work" / "run" / validated_run_id
    ).resolve()
    try:
        from .split_fork import resolve_run_id, resolve_work_root
    except ImportError:  # pragma: no cover
        from split_fork import resolve_run_id, resolve_work_root  # type: ignore[no-redef]

    if (
        not validated_run_id
        or _safe_run_id(validated_run_id) != validated_run_id
        or resolve_run_id() != validated_run_id
    ):
        errors.append(
            "ASDW Step 1.3 requires one canonical run ID shared by config and environment."
        )

    raw_work_root = os.environ.get("HVE_WORK_ROOT", "")
    if raw_work_root:
        if (
            raw_work_root != raw_work_root.strip()
            or "\x00" in raw_work_root
            or not Path(raw_work_root).is_absolute()
            or any(
                part in {".", ".."}
                for part in raw_work_root.replace("\\", "/").split("/")
            )
        ):
            errors.append(
                "ASDW Step 1.3 HVE_WORK_ROOT must be one canonical absolute path."
            )
        else:
            lexical_work_root = Path(os.path.abspath(raw_work_root))
            if os.path.normcase(os.path.normpath(lexical_work_root)) != os.path.normcase(
                os.path.normpath(expected_work_root)
            ):
                errors.append(
                    "ASDW Step 1.3 HVE_WORK_ROOT must match the validated current run."
                )
    if resolve_work_root().resolve() != expected_work_root:
        errors.append(
            "ASDW Step 1.3 resolved work root must match work/run/<validated-run-id>."
        )

    try:
        _require_trusted_asdw_data_deploy_mcp_servers(resolved_repo_root)
    except RuntimeError as exc:
        errors.append(str(exc))
    return errors


def _build_asdw_data_deploy_environment_snapshot(
    workflow_params: Mapping[str, Any],
    process_environment: Mapping[str, str],
    audit_mode: object,
    bootstrap_context: Optional[Mapping[str, str]] = None,
) -> Mapping[str, str]:
    """Freeze the complete non-secret Step 1.3 input contract.

    ``RESOURCE_GROUP`` has one authoritative source: the workflow parameter.
    The already-validated bootstrap context overrides matching process values;
    remaining declared values are explicit process inputs. HVE-owned payloads
    and stage run IDs are removed so the byte-pinned launcher can provision
    them from stable files for each stage. ``audit_mode`` is accepted as an
    untrusted object and validated here so an invalid generator result fails
    closed. The returned mapping is immutable and is passed to the locally
    spawned Copilot runtime before session start.
    """
    if not isinstance(audit_mode, str) or audit_mode not in (
        _ASDW_AUDIT_MODE_SQL_LEDGER_DIGEST,
        _ASDW_AUDIT_MODE_ACL_DIRECT,
    ):
        raise ValueError("ASDW Step 1.3 resolved an unsupported audit storage mode.")

    resource_group = workflow_params.get("resource_group")
    if type(resource_group) is not str:
        raise ValueError(
            "ASDW Step 1.3 requires the resource_group workflow parameter."
        )
    if (
        bootstrap_context is not None
        and bootstrap_context.get("RESOURCE_GROUP") != resource_group
    ):
        raise ValueError(
            "ASDW Step 1.3 bootstrap context does not match the resource_group workflow parameter."
        )
    required_keys = (
        *_ASDW_DATA_DEPLOY_COMMON_ENVIRONMENT_KEYS,
        *_ASDW_DATA_DEPLOY_AUDIT_ENVIRONMENT_KEYS[audit_mode],
    )
    declared_values: Dict[str, str] = {
        "RESOURCE_GROUP": (
            bootstrap_context["RESOURCE_GROUP"]
            if bootstrap_context is not None
            else resource_group
        )
    }
    for key in required_keys:
        if key == "RESOURCE_GROUP":
            continue
        if key == _ASDW_DATA_DEPLOY_READ_BACK_KEY:
            # Azure assigns this value when the prep stage creates the
            # identity, so the launcher reads it back between stages.
            continue
        value = (
            bootstrap_context.get(key)
            if bootstrap_context is not None and key in bootstrap_context
            else process_environment.get(key)
        )
        if type(value) is not str:
            raise ValueError(
                f"ASDW Step 1.3 requires explicit runtime input {key}."
            )
        declared_values[key] = value

    for key, value in declared_values.items():
        if (
            not value
            or value != value.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError(
                f"ASDW Step 1.3 runtime input {key} must be a non-empty single-line value."
            )
    if declared_values["DATA_NETWORK_MODE"] != "private":
        raise ValueError(
            "ASDW Step 1.3 DATA_NETWORK_MODE must be private; other routes are blocked."
        )

    managed_casefold = {
        key.casefold() for key in _ASDW_DATA_DEPLOY_HVE_OWNED_ENVIRONMENT_KEYS
    }
    frozen_environment = {
        key: value
        for key, value in process_environment.items()
        if key.casefold() not in managed_casefold
    }
    if bootstrap_context is not None:
        frozen_environment.update(bootstrap_context)
    frozen_environment.update(declared_values)
    return MappingProxyType(frozen_environment)


def _build_asdw_data_deploy_bootstrap_inputs(
    workflow_params: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Map only explicit workflow parameters into the Step 1.3 bootstrap API."""
    return {
        context_key: workflow_params.get(parameter_key)
        for context_key, parameter_key in _ASDW_DATA_DEPLOY_BOOTSTRAP_PARAM_KEYS.items()
    }


def _resolve_asdw_data_deploy_subscription_id() -> str:
    """Return the signed-in Azure subscription ID for Step 1.3.

    The subscription ID is the one value the resource names cannot be derived
    from, and asking the operator for it duplicates what `az login` already
    knows. Resolving it here keeps the workflow to a single required input.
    """
    try:
        completed = subprocess.run(
            [
                resolve_azure_cli_executable(),
                "account",
                "show",
                "--query",
                "id",
                "--output",
                "tsv",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, ScriptLauncherError) as exc:
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 could not run the Azure CLI to resolve SUBSCRIPTION_ID."
        ) from exc
    if completed.returncode != 0:
        raise AsdwDataDeployContextError(
            "ASDW Step 1.3 could not resolve SUBSCRIPTION_ID; run `az login` first."
        )
    return completed.stdout.strip()


def _asdw_data_deploy_evidence_paths(
    repo_root: Path,
    run_id: str,
) -> tuple[Path, Path, Path]:
    """Return the three HVE-owned evidence paths for native Step 1.3."""
    work_dir = (
        repo_root
        / "work"
        / "run"
        / run_id
        / "Dev-Microservice-Azure-DataDeploy"
        / "Issue-step-1-3"
    )
    tdd_report = (
        repo_root
        / "tests"
        / "run"
        / run_id
        / "asdw-web"
        / "step-1-3"
        / "APP-009"
        / "GREEN"
        / "tdd-test-report.md"
    )
    return (
        work_dir / "work-status.md",
        work_dir / "ac-verification.md",
        tdd_report,
    )


def _write_asdw_data_deploy_evidence(
    repo_root: Path,
    run_id: str,
    pipeline_results: object,
) -> list[str]:
    """Write bounded native-pipeline evidence without accepting Agent prose."""
    if not isinstance(pipeline_results, tuple):
        return ["ASDW native data pipeline evidence requires an immutable result tuple."]
    rows: list[tuple[str, int, int, bool]] = []
    for result in pipeline_results:
        stage = getattr(result, "stage", None)
        attempt = getattr(result, "attempt", None)
        exit_code = getattr(result, "exit_code", None)
        reached = getattr(result, "reached", None)
        if (
            type(stage) is not str
            or type(attempt) is not int
            or type(exit_code) is not int
            or type(reached) is not bool
        ):
            return ["ASDW native data pipeline evidence received an invalid StageResult."]
        rows.append((stage, attempt, exit_code, reached))

    is_complete_success = (
        tuple((stage, attempt) for stage, attempt, _exit, _reached in rows)
        == _ASDW_DATA_DEPLOY_PIPELINE_SEQUENCE
        and all(exit_code == 0 and reached for _stage, _attempt, exit_code, reached in rows)
    )
    status = "PASS" if is_complete_success else "BLOCKED"
    outcomes = {
        (stage, attempt): exit_code == 0 and reached
        for stage, attempt, exit_code, reached in rows
    }
    ac1_status = "✅" if is_complete_success else "❌"
    ac2_status = (
        "✅"
        if all(
            outcomes.get((stage, attempt)) is True
            for stage, attempt in (
                ("create", 1),
                ("registration", 1),
                ("create", 2),
                ("registration", 2),
            )
        )
        else "❌"
    )
    ac3_status = (
        "✅"
        if all(
            outcomes.get(("verify", attempt)) is True
            for attempt in (1, 2)
        )
        else "❌"
    )
    tdd_judgement = "PASS" if is_complete_success else "BLOCKED"
    stage_lines = "\n".join(
        f"| {stage} | {attempt} | {exit_code} | {'reached' if reached else 'not-reached'} |"
        for stage, attempt, exit_code, reached in rows
    ) or "| none | 0 | 1 | not-reached |"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    work_status_path, ac_report_path, tdd_report_path = _asdw_data_deploy_evidence_paths(
        repo_root,
        run_id,
    )
    contents = {
        work_status_path: (
            "# HVE-owned ASDW DataDeploy work status\n\n"
            f"- status: {status}\n"
            "- evidence_source: stage_results\n\n"
            "| Stage | Attempt | Exit code | Reached |\n"
            "| --- | ---: | ---: | --- |\n"
            f"{stage_lines}\n"
        ),
        ac_report_path: (
            "# HVE-owned ASDW DataDeploy AC verification\n\n"
            "| AC-ID | Description | Status | StageResult evidence |\n"
            "| --- | --- | --- | --- |\n"
            f"| AC-1 | native pipeline completed | {ac1_status} | stage_results sequence |\n"
            f"| AC-2 | create and registration second pass | {ac2_status} | create/registration attempts 1 and 2 |\n"
            f"| AC-3 | verify completed for both passes | {ac3_status} | verify attempts 1 and 2 |\n"
        ),
        tdd_report_path: (
            "# HVE-owned ASDW DataDeploy TDD report\n\n"
            "<!-- validation-confirmed -->\n\n"
            "- Schema-Version: 1.0\n"
            "- Workflow: asdw-web\n"
            "- Step: 1.3\n"
            "- Agent: Dev-Microservice-Azure-DataDeploy\n"
            "- Target-Key: APP-009\n"
            "- Phase: GREEN\n"
            "- Test-Code-Path: src/infra/azure\n"
            f"- Timestamp-UTC: {timestamp}\n"
            "- Evidence-Status: EXECUTED\n"
            f"- TDD-Judgement: {tdd_judgement}\n"
            "- Secret-Redaction: confirmed\n"
            "- Test-Files-Changed: none\n\n"
            "## Command\n\nHVE-owned native DataDeploy pipeline.\n\n"
            "## Expected Outcome\n\nFixed two-pass pipeline reaches verify.\n\n"
            f"## Actual Result\n\n{status}\n\n"
            "## Evidence\n\nStageResult sequence recorded by HVE.\n\n"
            "## Failure Analysis\n\nNo Agent-authored evidence is accepted.\n\n"
            "## Test Protection\n\nThe pipeline result is immutable evidence.\n"
        ),
    }
    originals: dict[Path, bytes | None] = {}
    staged: dict[Path, Path] = {}
    committed: list[Path] = []
    try:
        for path, content in contents.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = path.read_bytes() if path.exists() else None
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
            )
            temporary_path = Path(temporary_name)
            staged[path] = temporary_path
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for path in contents:
            os.replace(staged[path], path)
            committed.append(path)
    except OSError:
        for path in reversed(committed):
            original = originals.get(path)
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                    continue
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{path.name}.restore.",
                    suffix=".tmp",
                    dir=path.parent,
                )
                temporary_path = Path(temporary_name)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, path)
            except OSError:
                pass
        for temporary_path in staged.values():
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return ["ASDW native data pipeline evidence could not be written."]
    return []


def _is_asdw_data_deploy_step(
    step_id: Optional[str],
    custom_agent: Optional[str],
) -> bool:
    return bool(
        custom_agent == "Dev-Microservice-Azure-DataDeploy"
        and str(step_id or "").split("/", 1)[0] == "1.3"
    )


def _has_supported_asdw_data_deploy_app_scope(
    step_id: str,
    workflow_params: Mapping[str, Any],
) -> bool:
    """Require exactly the one APP coverage the fixed producer can render."""
    selected = workflow_params.get("app_ids")
    singular = workflow_params.get("app_id")
    if (
        type(selected) is not list
        or len(selected) != 1
        or type(selected[0]) is not str
        or selected[0] != _ASDW_DATA_DEPLOY_SUPPORTED_APP_ID
    ):
        return False
    if singular is not None and (
        type(singular) is not str
        or singular != _ASDW_DATA_DEPLOY_SUPPORTED_APP_ID
    ):
        return False
    parts = step_id.split("/")
    return len(parts) == 1 or (
        len(parts) == 2
        and parts[1] == _ASDW_DATA_DEPLOY_SUPPORTED_APP_ID
    )


try:
    from .config import (
        SDKConfig,
        generate_run_id,
        SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS,
        DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        to_wire_model,
    )
    from .console import Console, _ACTION_DISPLAY, timestamp_prefix
    from .prompts import (
        REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
        PRE_EXECUTION_QA_PROMPT_V2, MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
    )
    from .qa_merger import QADocument, QAMerger
    from .run_state import DEFAULT_SESSION_ID_PREFIX, make_session_id
    from .run_state_store import (
        DurableStateError,
        LeaseToken,
        RunStateStore,
        default_state_path,
    )
    from .self_improve import (
        scan_codebase, record_learning, get_learning_summary,
        _build_verification_result,
        ImprovementRecord, ScanResult, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from .workiq import (
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, query_workiq_detailed,
        get_workiq_prompt_template, save_workiq_result,
        WORKIQ_MCP_SERVER_NAME, WORKIQ_MCP_SERVER_NAMES, WORKIQ_MCP_TOOL_NAMES,
        extract_workiq_status,
        is_workiq_tool_name, extract_tool_name_from_event,
        extract_workiq_tool_name_from_event,
        format_workiq_tool_not_invoked_warning,
        is_workiq_result_mergeable,
    )
    from .orchestrator_context import OrchestratorContext
    from .phase1_request_plan import plan_phase1_request
    from .cloud_session import (
        acquire_cloud_session_slot,
        attach_cloud_session_event_logger,
        attach_cloud_session_limiter_release,
        build_cloud_session_options,
        is_policy_blocked_error,
        resolve_cloud_repository,
        should_use_cloud_session,
        wait_for_cloud_session_ready,
    )
except ImportError:
    from config import (  # type: ignore[no-redef]
        SDKConfig,
        generate_run_id,
        SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS,
        DEFAULT_CONTEXT_INJECTION_MAX_CHARS,
        to_wire_model,
    )
    from console import Console, _ACTION_DISPLAY, timestamp_prefix  # type: ignore[no-redef]
    from prompts import (  # type: ignore[no-redef]
        REVIEW_PROMPT, ADVERSARIAL_RECHECK_PROMPT,
        QA_PROMPT_V2,
        SELF_IMPROVE_SCAN_PROMPT, SELF_IMPROVE_PLAN_PROMPT, SELF_IMPROVE_VERIFY_PROMPT,
        PRE_EXECUTION_QA_PROMPT_V2, MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT,
    )
    from qa_merger import QADocument, QAMerger  # type: ignore[no-redef]
    from phase1_request_plan import plan_phase1_request  # type: ignore[no-redef]
    from run_state import DEFAULT_SESSION_ID_PREFIX, make_session_id  # type: ignore[no-redef]
    # Durable state types must keep one class identity even when ``runner`` is
    # imported through the legacy flat-module compatibility path.  The flat
    # orchestrator delegates durable planning/storage to the canonical package
    # modules, so importing a second top-level ``run_state_store`` here would
    # make valid fenced tokens fail ``isinstance`` checks.
    from hve.run_state_store import (  # type: ignore[no-redef]
        DurableStateError,
        LeaseToken,
        RunStateStore,
        default_state_path,
    )
    from self_improve import (  # type: ignore[no-redef]
        scan_codebase, record_learning, get_learning_summary,
        _build_verification_result,
        ImprovementRecord, ScanResult, VerificationResult,
        DEFAULT_QUALITY_THRESHOLD, LEARNING_SUMMARY_MAX_LENGTH,
    )
    from workiq import (  # type: ignore[no-redef]
        is_workiq_available, build_workiq_mcp_config,
        query_workiq, query_workiq_detailed,
        get_workiq_prompt_template, save_workiq_result,
        WORKIQ_MCP_SERVER_NAME, WORKIQ_MCP_SERVER_NAMES, WORKIQ_MCP_TOOL_NAMES,
        extract_workiq_status,
        is_workiq_tool_name, extract_tool_name_from_event,
        extract_workiq_tool_name_from_event,
        format_workiq_tool_not_invoked_warning,
        is_workiq_result_mergeable,
    )
    from orchestrator_context import OrchestratorContext  # type: ignore[no-redef]
    from cloud_session import (  # type: ignore[no-redef]
        acquire_cloud_session_slot,
        attach_cloud_session_event_logger,
        attach_cloud_session_limiter_release,
        build_cloud_session_options,
        is_policy_blocked_error,
        resolve_cloud_repository,
        should_use_cloud_session,
        wait_for_cloud_session_ready,
    )

# Phase 4 プロンプト長の上限（長い出力を切り詰めてトークン消費を制御する）
_MAX_SCAN_OUTPUT_LENGTH: int = 8000
_MAX_PLAN_SCAN_LENGTH: int = 4000
_MAX_LEARNING_SUMMARY_LENGTH: int = 2000
_ACTION_DETAIL_MAX_LENGTH: int = 120
_ACTION_RESULT_SINGLE_LINE_MAX_LENGTH: int = 100
_MODEL_CALL_FAILURE_THRESHOLD: int = 3

# Wave 2-6: Work IQ 優先度フィルタで優先扱いする重要度値
# priority_filter=True 時は "最重要"/"高" を先頭に寄せ、不足分は残りで補填して max 件に収める
_WORKIQ_HIGH_PRIORITY_VALUES: frozenset[str] = frozenset(["最重要", "高"])
_WORKIQ_MCP_SERVER_ALIASES: frozenset[str] = frozenset(
    name.lower() for name in WORKIQ_MCP_SERVER_NAMES
)


def _is_workiq_mcp_server_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _WORKIQ_MCP_SERVER_ALIASES


_AZURE_MCP_SERVER_NAME = "azure"

# FR-CLI-79: 全 Step の Custom Agent プロンプトが Azure に言及しない Workflow。
# 未登録の Workflow は従来どおり全サーバを受け取る（宣言漏れを機能破壊にしない）。
_AZURE_FREE_WORKFLOWS = frozenset({"ard", "akm", "adi", "adoc"})


def _filter_mcp_servers_for_session(
    mcp_servers: Optional[Dict[str, Any]],
    *,
    include_workiq: bool = False,
    workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return MCP servers for a session, excluding Work IQ aliases by default.

    HVE uses `_hve_workiq` internally, while user-level MCP config can expose a
    server named `workiq`. Main coding sessions should not connect either alias
    unless a dedicated Work IQ phase explicitly opts in.

    FR-CLI-79: Azure を使わない Workflow では `azure` サーバも外す。
    """
    if not mcp_servers:
        return {}
    _drop_azure = str(workflow_id or "").strip().lower() in _AZURE_FREE_WORKFLOWS
    return {
        _k: _v
        for _k, _v in mcp_servers.items()
        if (include_workiq or not _is_workiq_mcp_server_name(_k))
        and not (_drop_azure and str(_k).strip().lower() == _AZURE_MCP_SERVER_NAME)
    }


def _apply_repository_mcp_scope(
    opts: Dict[str, Any],
    *,
    include_workiq: bool = False,
    workflow_id: Optional[str] = None,
) -> None:
    """FR-CLI-76: リポジトリ宣言の MCP サーバだけを公開し、自動探索を止める。

    既に `opts["mcp_servers"]` がある場合はそれを優先して宣言分を併合する。
    宣言が存在しない / 読み取れない / 空の場合は何もしない（呼び出し側の
    `enable_config_discovery` を従来どおり `True` のまま残すため）。
    """
    declared = _filter_mcp_servers_for_session(
        copy.deepcopy(_read_repository_mcp_config(Path.cwd())),
        include_workiq=include_workiq,
        workflow_id=workflow_id,
    )
    if not declared:
        return
    merged = dict(opts.get("mcp_servers") or {})
    for _name, _server in declared.items():
        merged.setdefault(_name, _server)
    opts["mcp_servers"] = merged
    opts["enable_config_discovery"] = False


def _filter_workiq_questions(
    questions: "List[Any]",
    max_questions: int,
    priority_filter: bool,
) -> "List[Any]":
    """Work IQ クエリ対象の質問を絞り込む。

    priority_filter=True の場合、重要度が "最重要"/"高" の質問を優先して先頭に寄せ、
    不足分は残りの質問で補填した上で max_questions 件に収める。
    priority_filter=False の場合は元の順番のまま max_questions 件を返す。
    max_questions が負の値の場合は 0 として扱う。
    """
    normalized_max = max(0, max_questions)
    if not priority_filter:
        return list(questions)[:normalized_max]

    high = [q for q in questions if getattr(q, "priority", "") in _WORKIQ_HIGH_PRIORITY_VALUES]
    rest = [q for q in questions if getattr(q, "priority", "") not in _WORKIQ_HIGH_PRIORITY_VALUES]
    combined = high + rest
    return combined[:normalized_max]

# ---------------------------------------------------------------------------
# Self-Improve スコープ解決ヘルパー
# ---------------------------------------------------------------------------

# SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS は config.py からインポート済み
# （_SI_SCOPE_DEFAULTS として後方互換エイリアスを公開）
_SI_SCOPE_DEFAULTS = SELF_IMPROVE_WORKFLOW_SCOPE_DEFAULTS

_RUNNER_EXECUTION_MODE_CONSTRAINT_SUFFIX = load_prompt_file(
    "runtime/runner/execution-mode-constraint-suffix.prompt.md"
)
_RUNNER_REVIEW_OWNERSHIP_AUTO_CONTENTS_REVIEW_SUFFIX = load_prompt_file(
    "runtime/runner/review-ownership-auto-contents-review.prompt.md"
)
_RUNNER_REVIEW_OWNERSHIP_INLINE_SELF_CHECK_SUFFIX = load_prompt_file(
    "runtime/runner/review-ownership-inline-self-check.prompt.md"
)
_RUNNER_PHASE1_AGENT_PREFIX_TEMPLATE = load_prompt_file(
    "runtime/runner/phase1-agent-prefix.prompt.md"
)
_RUNNER_PHASE1_PRE_QA_HEADING = load_prompt_file(
    "runtime/runner/phase1-pre-qa-heading.prompt.md"
)
_RUNNER_PHASE1_MAIN_TASK_HEADING = load_prompt_file(
    "runtime/runner/phase1-main-task-heading.prompt.md"
)
_RUNNER_TDD_REPORT_INSTRUCTION_SUFFIX_TEMPLATE = load_prompt_file(
    "runtime/runner/tdd-report-instruction-suffix.prompt.md"
)
# Durable Main-session recovery is loaded at execution time so callers and tests
# always use the canonical prompt file rather than a copied module constant.
_RUNNER_RESUME_RECOVERY_PROMPT_PATH = (
    "runtime/runner/resume-recovery.prompt.md"
)
_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS = 5.0
_RUNNER_CLEANUP_TIMEOUT_SECONDS = 5.0
_RUNNER_FORCE_STOP_TIMEOUT_SECONDS = 2.0


def _remaining_deadline_seconds(deadline: float) -> float:
    """Return the positive time remaining for one event-loop deadline."""
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError("durable resume deadline expired")
    return remaining


async def _disconnect_session_bounded(session: Any) -> None:
    """Disconnect one SDK session without allowing cleanup to hang forever."""
    await asyncio.wait_for(
        session.disconnect(),
        timeout=_RUNNER_CLEANUP_TIMEOUT_SECONDS,
    )


async def _stop_client_bounded(client: Any, console: Any) -> None:
    """Stop an SDK client within fixed bounds, escalating to force_stop."""
    try:
        await asyncio.wait_for(
            client.stop(),
            timeout=_RUNNER_CLEANUP_TIMEOUT_SECONDS,
        )
        return
    except TimeoutError:
        console.warning("[cleanup] client.stop() timed out; forcing shutdown")
    except Exception as cleanup_exc:
        console.warning(f"[cleanup] client.stop() failed: {cleanup_exc}")

    force_stop = getattr(client, "force_stop", None)
    if not callable(force_stop):
        return
    try:
        await asyncio.wait_for(
            force_stop(),
            timeout=_RUNNER_FORCE_STOP_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        console.warning("[cleanup] client.force_stop() timed out")
    except Exception as cleanup_exc:
        console.warning(f"[cleanup] client.force_stop() failed: {cleanup_exc}")


def _resolve_step_output_paths(workflow: Any, step_id: str) -> List[str]:
    """ステップから成果物パスを取得する。

    workflow_registry.py の StepDef.output_paths を参照する。
    output_paths が未定義または空の場合は空リストを返し、
    呼び出し側で workflow_default にフォールバックする。
    """
    step = next(
        (s for s in getattr(workflow, "steps", []) if getattr(s, "id", None) == step_id),
        None,
    )
    if step is None:
        return []
    paths = getattr(step, "output_paths", None)
    return list(paths) if paths else []


def _build_execution_mode_constraint_suffix(ctx: Any) -> str:
    """CLI/GUI Orchestrator 配下 (fleet mode 以外) のとき prompt 末尾に付与する制約文を返す。

    `ctx` が `None`（単独実行モード）または `split_fork_enabled=True`（fleet mode）の
    場合は空文字を返す。詳細は copilot-instructions.md §0。
    """
    if ctx is None or getattr(ctx, "split_fork_enabled", False):
        return ""
    return _RUNNER_EXECUTION_MODE_CONSTRAINT_SUFFIX


def _build_review_ownership_suffix(auto_contents_review: bool) -> str:
    """メインタスクと敵対的レビューの所有権を明示する末尾指示を返す。"""
    if auto_contents_review:
        return _RUNNER_REVIEW_OWNERSHIP_AUTO_CONTENTS_REVIEW_SUFFIX
    return _RUNNER_REVIEW_OWNERSHIP_INLINE_SELF_CHECK_SUFFIX


def _compose_phase1_prompt(
    *,
    agent_prefix: str,
    step_prompt: str,
    pre_qa_context: str,
    execution_mode_suffix: str,
    tdd_suffix: str,
    review_suffix: str,
) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    """Phase 1 の送信本文と、合計が一致する成分列を返す。"""
    components: List[Tuple[str, str]] = []
    if agent_prefix:
        components.append(
            (
                "agent_prefix",
                _RUNNER_PHASE1_AGENT_PREFIX_TEMPLATE.format(
                    agent_prefix=agent_prefix
                ),
            )
        )
    if pre_qa_context:
        components.extend((
            ("pre_qa_heading", _RUNNER_PHASE1_PRE_QA_HEADING),
            ("pre_qa_context", pre_qa_context),
            ("main_task_heading", _RUNNER_PHASE1_MAIN_TASK_HEADING),
        ))
    components.append(("step_prompt", step_prompt))
    for name, suffix in (
        ("execution_mode_suffix", execution_mode_suffix),
        ("tdd_suffix", tdd_suffix),
        ("review_suffix", review_suffix),
    ):
        if suffix:
            components.append((name, suffix))
    return "".join(text for _name, text in components), tuple(components)


def _check_output_paths_gate(
    ctx: Any, workflow: Any, step_id: str, repo_root: Path
) -> List[str]:
    """CLI/GUI Orchestrator 配下で `output_paths` の欠落を検出する。

    FR-WF-OUT-01: 宣言された成果物が 1 件でも欠落した Step は `failed` とする。
    FR-WF-OUT-10: fail-closed drop されたエントリのうち fan-out キーを含むものは、
    キー出現位置までの接頭辞に前方一致する成果物の存在で検証する（欠落報告では
    接頭辞であることを示すため末尾に `*` を付す）。

    戻り値:
      - 空リスト: ゲート pass（条件不該当、宣言なし、または全て存在）
      - 非空リスト: 欠落した path 群（fail 用。存在する宣言 path は含めない）
    """
    if ctx is None or getattr(ctx, "split_fork_enabled", False):
        return []
    step = next(
        (s for s in getattr(workflow, "steps", []) if getattr(s, "id", None) == step_id),
        None,
    )
    declared = _resolve_step_output_paths(workflow, step_id)
    prefix_gates = (
        resolve_output_path_prefix_gates(step) if step is not None else []
    )
    return find_missing_output_paths(repo_root, declared, prefix_gates)

# Auto-QA マージファイルのサフィックス（HVE 実行補助 QA。ADI 原本質問票のmain成果物とは別物）
_EXECUTION_QA_MERGED_SUFFIX: str = "execution-qa-merged.md"
# 事前実行 QA ファイルのサフィックス（メインタスク実行前の質問票）
_PRE_EXECUTION_QA_SUFFIX: str = "pre-execution-qa.md"

# LLM が本文ではなく「成果物サマリー + artifacts: qa/foo.md」だけを返す場合の再パース用。
# セキュリティ上、相対 `qa/*.md` のみを許可し、絶対パスや `..` は読まない。
_QA_ARTIFACT_PATH_RE: re.Pattern[str] = re.compile(
    r"(?:^|[\s`\"'(\[])(qa[\\/][^\s`\"')\]]+?\.md)(?=[\s`\"')\],,。．、;；]|$)",
    re.IGNORECASE,
)


def _extract_safe_qa_artifact_paths(
    content: str,
    base_dir: "Path | str" = ".",
) -> List[Path]:
    """LLM 応答中の安全な `qa/*.md` artifacts パスを抽出する。

    絶対パス、`..` を含むパス、`qa/` 以外のパス、存在しないファイルは除外する。
    """
    base = Path(base_dir)
    base_resolved = base.resolve()
    paths: List[Path] = []
    seen: set[str] = set()
    for match in _QA_ARTIFACT_PATH_RE.finditer(content or ""):
        raw = match.group(1).strip().strip("`\"'").rstrip(".,、。;；")
        candidate = Path(raw.replace("\\", "/"))
        if candidate.is_absolute() or not candidate.parts:
            continue
        if candidate.parts[0].lower() != "qa":
            continue
        if any(part in ("..", "") for part in candidate.parts):
            continue

        full_path = base / candidate
        try:
            resolved = full_path.resolve()
            resolved.relative_to(base_resolved)
        except (OSError, ValueError):
            continue
        if not full_path.is_file():
            continue

        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(full_path)
    return paths


def _parse_qa_content_with_artifact_fallback(
    qa_content: str,
    base_dir: "Path | str" = ".",
) -> Tuple["QADocument", Optional[Path]]:
    """QA 応答本文をパースし、失敗時は artifacts 参照先の QA ファイルを再パースする。"""
    parsed = QAMerger.parse_qa_content(qa_content)
    if parsed.questions:
        return parsed, None

    for artifact_path in _extract_safe_qa_artifact_paths(qa_content, base_dir=base_dir):
        try:
            artifact_content = artifact_path.read_text(encoding="utf-8")
        except OSError:
            continue
        candidate = QAMerger.parse_qa_content(artifact_content)
        if candidate.questions:
            return candidate, artifact_path

    return parsed, None


async def _create_session_with_auto_reasoning_fallback(
    client: Any,
    session_opts: Dict[str, Any],
    *,
    config: Optional[SDKConfig] = None,
    step_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    subtask_kind: Optional[str] = None,
    console: Optional[Any] = None,
    requires_external_skill_directories: bool = False,
) -> Any:
    """create_session を呼び出し、SDK が reasoning_effort を未サポートの場合は除外して再試行する。

    SDK バージョン < 0.3.0 互換のための防御。reasoning_effort が opts に
    含まれない場合は単純な create_session 呼び出しと等価。

    検出条件は Python の組み込み TypeError 文言
    (`got an unexpected keyword argument`) と `reasoning_effort` の両方が
    含まれる場合に限定する。これにより、SDK 側の値検証エラー
    (例: `reasoning_effort must be one of ...`) や、別キーワードの
    エラーメッセージに `reasoning_effort` が偶然含まれるケースで
    誤って引数を剥がして再試行することを防ぐ。

    併せて、Skill レジストリへ `.github/skills` を登録する
    (`skill_directories` / `enable_config_discovery`) を呼び出し側で
    未指定の場合のみ自動注入する。CLI のスキル発見は深さ 1
    (`<root>/<name>/SKILL.md`) のみ走査するため、`skill_directories`
    には root に加えて各カテゴリ直下サブフォルダも列挙する。SDK が
    当該引数を未サポートの場合は TypeError を契機に剥がして再試行する。
    """
    _opts_with_skills = dict(session_opts)
    # context_tier: ユーザー設定 (SDKConfig.context_tier) を create_session へ伝播する。
    # truthy のときのみ注入し、呼び出し側が明示済みなら尊重する。
    if config is not None and getattr(config, "context_tier", None) and "context_tier" not in _opts_with_skills:
        _opts_with_skills["context_tier"] = config.context_tier
    _cloud_injected = False
    _had_streaming_before_cloud = "streaming" in _opts_with_skills
    _streaming_before_cloud = _opts_with_skills.get("streaming")
    if config is not None and "cloud" not in _opts_with_skills:
        _cloud_opts = build_cloud_session_options(
            config,
            step_id=step_id,
            subtask_kind=subtask_kind,
        )
        if _cloud_opts is not None:
            _opts_with_skills["cloud"] = _cloud_opts
            _cloud_injected = True
            _opts_with_skills["streaming"] = True
        elif should_use_cloud_session(config, step_id=step_id, subtask_kind=subtask_kind) and console is not None:
            owner, name, _branch = resolve_cloud_repository(config)
            try:
                if not owner or not name:
                    console.warning(
                        "Cloud Session repository owner/name が解決できないため、ローカルセッションにフォールバックします。"
                    )
                else:
                    console.warning(
                        "Cloud Session 型が現在の Copilot SDK で利用できないため、ローカルセッションにフォールバックします。"
                    )
            except Exception:
                pass
    if "skill_directories" not in _opts_with_skills:
        # CLI のスキル発見は深さ 1 (`<root>/<name>/SKILL.md`) のみ走査するため、
        # root に加えて各カテゴリ直下サブフォルダも列挙し、ネスト配置スキル
        # (`<root>/<category>/<name>/SKILL.md`) を発見可能にする。
        # SKILL.md 不在のサブフォルダを渡しても無害（CLI 側で無視される）。
        _repository_skill_dirs = _repository_skill_directories()
        if _repository_skill_dirs:
            _opts_with_skills["skill_directories"] = _repository_skill_dirs
    # FR-CLI-76: 呼び出し側が MCP を指定していないときは、リポジトリ宣言分だけを公開し
    # ワークスペース / ユーザースコープ / プラグイン由来の自動探索を止める。
    if (
        "mcp_servers" not in _opts_with_skills
        and "enable_config_discovery" not in _opts_with_skills
    ):
        # include_workiq=True: 本経路は従来 workiq を落としていないので挙動を変えない。
        _apply_repository_mcp_scope(
            _opts_with_skills, include_workiq=True, workflow_id=workflow_id
        )
    if "enable_config_discovery" not in _opts_with_skills:
        _opts_with_skills["enable_config_discovery"] = True

    async def _attempt(opts: Dict[str, Any]) -> Any:
        limiter = None
        try:
            if "cloud" in opts and config is not None:
                limiter = await acquire_cloud_session_slot(config)
            session = await client.create_session(**opts)
            if "cloud" in opts:
                attach_cloud_session_event_logger(
                    session,
                    step_id=step_id,
                    subtask_kind=subtask_kind,
                )
                await wait_for_cloud_session_ready(session)
                if limiter is not None:
                    attach_cloud_session_limiter_release(session, limiter)
                    limiter = None
            return session
        except TypeError as exc:
            if limiter is not None:
                limiter.release_slot()
            msg = str(exc)
            if "unexpected keyword argument" not in msg:
                raise
            for _kw in ("skill_directories", "enable_config_discovery", "disabled_skills", "custom_agent", "cloud", "context_tier", "tool_search"):
                if _kw in msg and _kw in opts:
                    if (
                        _kw == "skill_directories"
                        and requires_external_skill_directories
                    ):
                        raise RuntimeError(
                            "HVE required external Skill directories are not "
                            "supported by the active Copilot SDK."
                        ) from exc
                    if (
                        _kw == "enable_config_discovery"
                        and opts.get(_kw) is False
                    ):
                        # ASDW Step 1.3 のMCP隔離境界。古いSDKへfallbackして
                        # workspace/user MCP discoveryを再有効化してはならない。
                        raise
                    if _kw == "cloud" and console is not None:
                        try:
                            console.warning(
                                "Cloud Session は現在の Copilot SDK で未サポートのため、ローカルセッションにフォールバックします。"
                            )
                        except Exception:
                            pass
                    elif console is not None:
                        # 無言で引数を剥ぐと、当該機能が無効化されたことに気付けない。
                        try:
                            console.warning(
                                f"Copilot SDK が create_session({_kw}=...) を未サポートのため、"
                                f"当該引数を除外して再試行します（{_kw} の機能は無効になります）。"
                            )
                        except Exception:
                            pass
                    _stripped = {k: v for k, v in opts.items() if k != _kw}
                    if _kw == "cloud" and _cloud_injected:
                        if _had_streaming_before_cloud:
                            _stripped["streaming"] = _streaming_before_cloud
                        else:
                            _stripped.pop("streaming", None)
                    return await _attempt(_stripped)
            if "reasoning_effort" in msg and "reasoning_effort" in opts:
                _stripped = {k: v for k, v in opts.items() if k != "reasoning_effort"}
                return await _attempt(_stripped)
            raise
        except Exception as exc:
            if limiter is not None:
                limiter.release_slot()
            if is_policy_blocked_error(exc) and console is not None:
                try:
                    console.warning(
                        "Cloud Session が組織ポリシーでブロックされました（policy_blocked）。リトライせず停止します。"
                    )
                except Exception:
                    pass
                raise
            if "cloud" in opts and _cloud_injected:
                if console is not None:
                    try:
                        console.warning(
                            f"Cloud Session の準備に失敗したため、ローカルセッションにフォールバックします ({type(exc).__name__})。"
                        )
                    except Exception:
                        pass
                stripped = {k: v for k, v in opts.items() if k != "cloud"}
                if _had_streaming_before_cloud:
                    stripped["streaming"] = _streaming_before_cloud
                else:
                    stripped.pop("streaming", None)
                return await _attempt(stripped)
            raise

    return await _attempt(_opts_with_skills)


def _truncate_context(text: str, max_length: int) -> str:
    """コンテキストを先頭 + 末尾で切り詰める。"""
    if len(text) <= max_length:
        return text
    head_size = max_length * 3 // 4
    omit_msg = f"\n\n... (中略: 全体 {len(text):,} 文字) ...\n\n"
    tail_size = max_length - head_size - len(omit_msg)
    if tail_size <= 0:
        return text[:max_length]
    return text[:head_size] + omit_msg + text[-tail_size:]


def _truncate_context_with_warn(
    text: str,
    max_length: int,
    *,
    label: str,
    console: Any,
) -> str:
    """`_truncate_context` のラッパー。切詰めが発生した場合だけ console.warning を出す。

    G-4: 出力サイズの可観測化。処理は継続する（U-3=a の方針）。
    label にはフェーズ名（例: "Phase 3 review_context"）を渡す。
    console は `Console` インターフェース互換（warning メソッドを持つ）。
    """
    if len(text) > max_length:
        try:
            console.warning(
                f"  ⚠️ {label}: コンテキストが上限 {max_length:,} 文字を超過 "
                f"(実サイズ {len(text):,}) — 先頭/末尾切詰め適用"
            )
        except Exception:
            # console が None / warning 未実装でも切詰め自体は実施する
            pass
    return _truncate_context(text, max_length)


_CLIENT_START_MAX_ATTEMPTS: int = 3
_CLIENT_START_BACKOFF_SECONDS: tuple = (0.5, 1.0, 2.0)


# ---------------------------------------------------------------------------
# ADR-0002: Fan-out per-key プロンプト注入ヘルパー (T3B)
# ---------------------------------------------------------------------------

def _apply_fanout_prompt_template(
    *,
    prompt: str,
    fanout_meta: Dict[str, Any],
    console: Any = None,
) -> str:
    """fan-out 子ステップ用の追加プロンプトを base prompt 先頭に注入する。

    テンプレートパス内の ``{key}`` を fanout_key で置換してから読み込む。
    ファイルが存在しない場合は base prompt をそのまま返す（warning のみ）。
    """
    key = fanout_meta.get("fanout_key", "")
    template_path = fanout_meta.get("additional_prompt_template_path")
    if not template_path or not key:
        return prompt
    try:
        resolved_path = template_path.format(key=key)
    except (KeyError, IndexError, ValueError):
        resolved_path = template_path
    p = Path(resolved_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.is_file():
        if console is not None:
            try:
                console.warning(
                    f"  ⚠️ fan-out テンプレが存在しません: {p} (key={key}) — base prompt を使用"
                )
            except Exception:
                pass
        return prompt
    try:
        addendum = p.read_text(encoding="utf-8")
    except OSError as exc:
        if console is not None:
            try:
                console.warning(f"  ⚠️ fan-out テンプレ読込失敗 ({p}): {exc}")
            except Exception:
                pass
        return prompt
    addendum = addendum.replace("{{key}}", key)
    return (
        f"## Fan-out コンテキスト (key={key})\n\n"
        f"{addendum}\n\n"
        f"## メインタスク\n\n"
        f"{prompt}"
    )


async def _start_client_with_retry(client: Any, *, console: Any = None) -> None:
    """`client.start()` を最大 _CLIENT_START_MAX_ATTEMPTS 回リトライする。

    SDK プロセス起動の瞬断（ポート競合・cli プロセス未起動の race 等）に対する
    防御。最終試行も失敗した場合は元の例外をそのまま伝播する。
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, _CLIENT_START_MAX_ATTEMPTS + 1):
        try:
            await client.start()
            return
        except Exception as exc:
            last_exc = exc
            if attempt >= _CLIENT_START_MAX_ATTEMPTS:
                break
            backoff = _CLIENT_START_BACKOFF_SECONDS[
                min(attempt - 1, len(_CLIENT_START_BACKOFF_SECONDS) - 1)
            ]
            if console is not None:
                try:
                    console.warning(
                        f"client.start() 失敗 ({type(exc).__name__}: {exc}) — "
                        f"{backoff}s 後にリトライ ({attempt}/{_CLIENT_START_MAX_ATTEMPTS})"
                    )
                except Exception:
                    pass
            await asyncio.sleep(backoff)
    assert last_exc is not None
    raise last_exc


def _is_review_fail(content: str) -> bool:
    """合格判定行のトークンから FAIL 判定かどうかを判定する。

    - 「合格判定」を含む行のみを対象にすることで、
      本文中に "fail" が含まれる場合の誤検知を防ぐ。
    - 合否行は「✅ PASS」または「❌ FAIL」といった一意なトークンを前提とし、
      テンプレート由来の「PASS / FAIL」併記行は FAIL とみなさない。

    敵対的レビューではサマリー/合格判定が必須のため、
    合格判定行が 1 行も見つからない場合はフォーマット不備として
    FAIL 扱い（再レビュー実行側に倒す）とする。
    """
    has_judgement_line = False
    for line in content.splitlines():
        if "合格判定" not in line:
            continue
        has_judgement_line = True

        # 明示的な ✅ PASS トークンがあれば FAIL ではない
        if "✅" in line and "PASS" in line.upper():
            return False

        # 明示的な ❌ FAIL トークンがある場合は FAIL
        if "❌" in line and "FAIL" in line.upper():
            return True

        # フォールバック: 絵文字なしでも大文字小文字を問わず FAIL を検出
        if "FAIL" in line.upper():
            return True

    # 合格判定行が存在しない場合は安全側に倒して FAIL 扱いとする
    return not has_judgement_line


# Windows では監視側（GUI のファイル監視通知で宛先を開く読み取り）がハンドルを
# 握っている瞬間に os.replace が WinError 5 を返すため、短時間だけ再試行する。
_ATOMIC_REPLACE_ATTEMPTS: int = 10
_ATOMIC_REPLACE_RETRY_INTERVAL_SECONDS: float = 0.05


def _atomic_write_text(path: Path, content: str) -> None:
    """tmp + os.replace でアトミックに書き込む。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _ATOMIC_REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_ATOMIC_REPLACE_RETRY_INTERVAL_SECONDS)


async def _collect_qa_answers_via_ipc(
    console: "Console",
    doc: "QADocument",
    step_id: str,
    config: "SDKConfig",
) -> Tuple[str, bool]:
    """qa_answer_mode="gui-file" モード: GUI からの回答を IPC ファイル経由で受け取る。

    フロー:
        1. <ipc_dir>/<step_id>.questionnaire.md に質問票を書き出す
        2. <ipc_dir>/<step_id>.request.json を書き出して GUI に通知
        3. <ipc_dir>/<step_id>.answers.md または <ipc_dir>/<step_id>.cancel を polling
        4. タイムアウト時は既定値全採用にフォールバック

    Returns:
        (user_answers_raw, skip_input) — 既存 _collect_qa_answers と同形式

    Raises:
        RuntimeError: ユーザーが GUI 側でキャンセルした場合（cancel ファイル検出）
    """
    from datetime import datetime, timezone

    if not config.qa_ipc_dir:
        console.warning(
            "qa_answer_mode=gui-file が指定されましたが qa_ipc_dir が空のため"
            " 全問既定値候補を採用します。"
        )
        return "", True

    try:
        ipc_dir = Path(config.qa_ipc_dir)
        ipc_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        console.warning(
            f"IPC ディレクトリの作成に失敗しました ({config.qa_ipc_dir}): {exc}。"
            " 全問既定値候補を採用します。"
        )
        return "", True

    questionnaire_path = ipc_dir / f"{step_id}.questionnaire.md"
    request_path = ipc_dir / f"{step_id}.request.json"
    answers_path = ipc_dir / f"{step_id}.answers.md"
    cancel_path = ipc_dir / f"{step_id}.cancel"

    # 1. 質問票（rendered）を IPC dir に書き出す
    try:
        from .qa_merger import QAMerger
    except ImportError:  # pragma: no cover
        from qa_merger import QAMerger  # type: ignore[no-redef]
    try:
        questionnaire_md = QAMerger.render_merged(doc)
    except Exception:
        # render に失敗した場合は最低限のフォーマットで保存
        _lines = [f"# QA 質問票 (step {step_id})\n"]
        for q in doc.questions:
            _lines.append(f"\n## Q{q.no}: {q.question}\n")
            if q.choices:
                for c in q.choices:
                    _lines.append(f"- {c.label}) {c.text}")
            if q.default_answer:
                _lines.append(f"\n既定値候補: {q.default_answer}\n")
        questionnaire_md = "\n".join(_lines)
    _atomic_write_text(questionnaire_path, questionnaire_md)

    # 2. request JSON
    request_data = {
        "schema_version": 1,
        "step_id": step_id,
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "questionnaire_path": str(questionnaire_path.resolve()),
        "qa_input_timeout_seconds": config.qa_gui_input_timeout_seconds,
    }
    _atomic_write_text(request_path, json.dumps(request_data, ensure_ascii=False, indent=2))

    console.status(
        f"GUI からの QA 回答待ち... (IPC dir: {ipc_dir.as_posix()},"
        f" タイムアウト: {config.qa_gui_input_timeout_seconds:.0f}s)"
    )

    # 3. polling
    timeout = config.qa_gui_input_timeout_seconds
    poll_interval = 1.0
    start = time.monotonic()
    user_answers_raw = ""
    cancelled = False
    timed_out = False
    while True:
        if cancel_path.exists():
            cancelled = True
            break
        if answers_path.exists():
            try:
                user_answers_raw = answers_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.warning(
                    f"answers ファイル読み込みに失敗しました ({answers_path}): {exc}。"
                    " 既定値候補を採用します。"
                )
                user_answers_raw = ""
            break
        if time.monotonic() - start > timeout:
            timed_out = True
            break
        await asyncio.sleep(poll_interval)

    # 4. cleanup (best-effort)
    for _p in (request_path, answers_path, questionnaire_path, cancel_path):
        try:
            if _p.exists():
                _p.unlink()
        except OSError:
            pass

    if cancelled:
        raise RuntimeError(
            f"QA 回答が GUI 側でキャンセルされました (step={step_id})"
        )

    if timed_out:
        console.warning(
            f"GUI 回答待ちタイムアウト ({timeout:.0f}s) — 全問既定値候補を採用します。"
        )
        return "", True

    skip_input = (user_answers_raw.strip() == "")
    if skip_input:
        console.status("GUI: 全問既定値候補を採用しました。")
    else:
        try:
            _parsed_answers = QAMerger.parse_answers(user_answers_raw)
            console.answer_summary(doc.questions, _parsed_answers)
        except Exception as exc:  # pragma: no cover - 防御的
            console.warning(f"GUI 回答サマリー表示に失敗: {exc}")
    return user_answers_raw, skip_input


async def _collect_qa_answers(
    console: "Console",
    doc: "QADocument",
    step_id: str,
    config: "SDKConfig",
) -> Tuple[str, bool]:
    """Phase 2b: QA 質問票への回答を収集する。

    questions が空リストの場合は呼び出し元でフォールバック済みであること前提。

    TTY 時:
        questionnaire_table() → prompt_answer_mode() → "all"/"one" フロー → answer_summary()

    非 TTY 時:
        questionnaire_table() のみ表示し、既定値候補を全採用する。

    qa_auto_defaults 時:
        questionnaire_table() のみ表示し、全問既定値候補を自動採用する。
        ウィザードモードの auto_qa=y で設定される。

    qa_answer_mode="autopilot" 時 (GUI Autopilot):
        テーブル表示後、全問既定値を自動採用。

    qa_answer_mode="gui-file" 時 (GUI ユーザー回答):
        IPC ファイル経由で GUI からの回答を待つ。

    Args:
        console: Console インスタンス。
        doc: パース済み QADocument（questions > 0 が前提）。
        step_id: ステップ識別子（プロンプト表示用）。
        config: SDKConfig（タイムアウト設定等）。

    Returns:
        (user_answers_raw, skip_input)
        - user_answers_raw: "番号: ラベル" 形式のテキスト、またはデフォルト採用時は ""。
        - skip_input: True のとき全問デフォルト採用。
    """
    console.questionnaire_table(doc.questions)

    # GUI 由来モード分岐（非 TTY 判定より前に処理する）
    if config.qa_answer_mode == "gui-file":
        console.status(
            f"[QA-DIAG] qa_answer_mode=gui-file 検出 → IPC モードへ遷移"
            f" (step={step_id}, ipc_dir={config.qa_ipc_dir})"
        )
        return await _collect_qa_answers_via_ipc(console, doc, step_id, config)

    if config.qa_answer_mode == "autopilot":
        console.status(
            "Autopilot モード: 全問既定値候補を自動採用します。"
        )
        return "", True

    _is_interactive = (
        not config.unattended
        and (config.force_interactive or sys.stdin.isatty())
    )
    if not _is_interactive:
        # 非 TTY または全自動モード: テーブル表示のみ行いデフォルト採用
        if config.unattended:
            console.warning(
                "全自動モードのため、全問既定値候補を自動採用します。"
            )
        else:
            console.warning(
                "stdin が非対話モード（TTY ではない）のため、全問既定値候補を自動採用します。\n"
                "  インタラクティブ入力を強制する場合は --force-interactive オプション（orchestrate コマンド）"
                " または wizard モードの「強制インタラクティブ」設定を有効にしてください。"
            )
        console.status("全問既定値候補を採用しました。")
        return "", True

    # QA 全問デフォルト自動採用モード（wizard の auto_qa=y で設定）
    # Issue Template Workflow (auto-qa-default-answer.yml) と同等の動作:
    # 質問票テーブルを表示した後、全問既定値候補を自動採用してステップを先に進める。
    if config.qa_auto_defaults:
        console.status(
            "QA 自動投入モード: 全問既定値候補を自動採用します。"
        )
        return "", True

    # TTY: フルインタラクティブフロー
    if config.qa_answer_mode:
        mode = config.qa_answer_mode
    else:
        mode = console.prompt_answer_mode()

    if mode == "all":
        # 4A. 全問一括入力モード
        user_answers_raw = await _read_stdin_multiline(
            prompt_msg=(
                f"[Step.{step_id}] QA 回答を入力してください\n"
                "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                "  空行で入力終了 / skip または何も入力せず Enter で既定値候補を採用:"
            ),
            console=console,
            timeout=config.qa_input_timeout_seconds,
        )
        if user_answers_raw.strip().lower() in ("", "skip"):
            # 全問空入力 → 既定値採用確認
            adopt = console.prompt_yes_no(
                "全問既定値候補を採用しますか？",
                default=True,
            )
            if adopt:
                skip_input = True
            else:
                # 再入力（もう一度同じ一括入力を試みる）
                user_answers_raw = await _read_stdin_multiline(
                    prompt_msg=(
                        f"[Step.{step_id}] QA 回答を再入力してください\n"
                        "  形式: 「番号: 選択肢」を1行1問で入力（例: 1: A）\n"
                        "  空行で入力終了:"
                    ),
                    console=console,
                    timeout=config.qa_input_timeout_seconds,
                )
                skip_input = user_answers_raw.strip().lower() in ("", "skip")
        else:
            skip_input = False
    else:
        # 4B. 1問ずつ入力モード
        answers_dict: Dict[int, str] = {}
        for q in doc.questions:
            ans = console.prompt_question_answer(q)
            answers_dict[q.no] = ans

        # "番号: ラベル" 形式で user_answers_raw を構築
        user_answers_raw = "\n".join(
            f"{no}: {label}" for no, label in answers_dict.items()
        )
        skip_input = False

    # 回答サマリー表示（skip_input 時は全問デフォルト採用のステータスのみ）
    if skip_input:
        console.status("全問既定値候補を採用しました。")
    else:
        _parsed_answers = QAMerger.parse_answers(user_answers_raw)
        console.answer_summary(doc.questions, _parsed_answers)

    return user_answers_raw, skip_input


def _should_run_pre_execution_qa(
    *,
    auto_qa: bool,
    workflow_id: Optional[str],
    custom_agent: Optional[str],
    prompt: str,
) -> bool:
    """FR-QA-03: auto_qa 有効時はワークフロー共通の事前 QA を実行する。"""
    del workflow_id, custom_agent, prompt
    return bool(auto_qa)


def _persist_answered_qa_and_dispatch(
    *,
    doc: "QADocument",
    user_answers_raw: str,
    use_defaults: bool,
    output_path: Path,
    workflow_id: Optional[str],
    dispatcher: Optional[Callable[[Path], None]],
) -> str:
    """回答済み QA を保存・再検証し、AKM 登録キューへ非待機で渡す。"""
    if not doc.questions:
        return ""
    answers = {} if use_defaults else QAMerger.parse_answers(user_answers_raw)
    merged = QAMerger.merge_answers(doc, answers, use_defaults=use_defaults)
    content = QAMerger.render_merged(merged)
    if not QAMerger.save_merged(content, output_path):
        raise RuntimeError(f"回答済み QA を保存できませんでした: {output_path}")
    errors = QAMerger.validate_answered_file(
        output_path,
        expected_content=content,
        expected_questions=len(doc.questions),
    )
    if errors:
        raise RuntimeError(
            "回答済み QA の保存検証に失敗しました: " + " / ".join(errors)
        )
    if workflow_id != "akm" and dispatcher is not None:
        dispatcher(output_path)
    return content


# ------------------------------------------------------------------
# ファイル I/O 追跡 — ツール分類定数
# ------------------------------------------------------------------

# ツール引数からファイルパスを取得するキー（表示用の summary キーとは分離）
_FILE_PATH_KEYS: tuple = ("path", "filePath", "file_path")

# write 操作を行うツール名
_WRITE_TOOLS: frozenset = frozenset({
    "edit_file", "editFile",
    "write_file", "writeFile",
    "create_file", "createFile",
    "patch", "replace",
    "create",  # Copilot SDK 短縮別名（新規作成 = write）
})

# read + write の両方を行うツール名（既存ファイルを読んでから書く）
_READ_WRITE_TOOLS: frozenset = frozenset({
    "edit_file", "editFile",
    "patch",
    "edit",  # Copilot SDK 短縮別名（既存編集 = read + write）
})

# ファイル追跡をスキップするツール名
_SKIP_TOOLS: frozenset = frozenset({
    "glob", "search", "grep", "rg",
})

# Work IQ ツール名（workiq.py の WORKIQ_MCP_TOOL_NAMES と同一）
_WORKIQ_TOOL_NAMES: frozenset = frozenset(WORKIQ_MCP_TOOL_NAMES)

# QA Draft の Work IQ 質問間隔（workiq._WORKIQ_QUERY_INTERVAL_SECONDS と同値のローカル定数）
_WORKIQ_DRAFT_QUERY_INTERVAL_SECONDS: float = 2.0

# FR-GUI-12: GUI からのジョブ対話 IPC を監視する間隔。
_STEERING_POLL_INTERVAL_SECONDS: float = 1.0

# QA Draft の Work IQ 結果マーカー文字列
# _clean_results フィルタとの一貫性を保つために定数化する
_WORKIQ_RESULT_NO_DATA = "関連情報なし"
_WORKIQ_RESULT_UNINVESTIGATED_PREFIX = "未調査"

_INTENT_DIAG_MAX_VALUE_LENGTH = 180
_INTENT_DIAG_MAX_ATTRS = 20
_INTENT_DIAG_SENSITIVE_TOKENS: tuple = (
    "token", "api_key", "apikey", "secret", "password", "authorization",
    "auth", "bearer", "cookie", "session", "credential", "private",
    "access_token",
)
_INTENT_DIAG_ALLOWED_KEYS: frozenset = frozenset({
    "intent", "description", "text", "content", "message", "kind", "details",
})

class StepRunner:
    """1 ステップを CopilotSession で実行する。

    フロー (1ステップ内、メイン + 必要時サブセッション):
    ┌──────────────────────────────────────────────────┐
    │ CopilotSession (同一セッション = コンテキスト保持)   │
    │                                                    │
    │  [auto_qa=True の場合]                               │
    │  Phase 0: 事前 QA                                  │
    │    0a: session.send_and_wait(PRE_EXECUTION_QA_PROMPT_V2)│
    │       → Agent が実行前質問票を生成（成果物なし）    │
    │    0b: CLI stdin で複数行回答入力                   │
    │    0c: [Work IQ 有効時] query_workiq_detailed()    │
    │    0d: qa/{run_id}-{step_id}-pre-execution-qa.md 保存   │
    │       pre_qa_context 文字列を組み立てる             │
    │                                                    │
    │  Phase 1: session.send_and_wait(prompt)            │
    │    → [Phase 0 実行済みの場合] prompt 先頭に         │
    │       pre_qa_context を注入してから実行             │
    │    → Agent がメインタスク実行                        │
    │                                                    │
    │  注: Phase 2（事後 QA / post-QA モード）は廃止済み。 │
    │     旧 qa_phase="post"/"both" および                │
    │     旧post-QA制御は削除されました。                 │
    │                                                    │
    │  [auto_contents_review=True の場合]                 │
    │  Phase 3: session.send_and_wait(REVIEW_PROMPT)     │
    │    → 敵対的レビュー（6軸検証 + PASS/FAIL判定）       │
    │    → FAIL時: 再レビューサイクル（最大2回）            │
    │                                                    │
    │  [auto_self_improve=True の場合]                    │
    │  Phase 4: 自己改善ループ（最大 N イテレーション）     │
    │    → 4a: scan_codebase()  ruff+pytest+markdownlint │
    │    → 4b: LLM 統合評価 + 改善計画生成                 │
    │    → 4c: session 内で改善実行                        │
    │    → 4d: 検証（Verification Loop §10.1）            │
    │    → 4e: record_learning() 学習ログ記録              │
    │    → 4f: デグレード検知（スコア悪化 or FAIL で停止） │
    │                                                    │
    │  session.disconnect()                              │
    └──────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        config: SDKConfig,
        console: Console,
        *,
        orchestrator_ctx: Optional["OrchestratorContext"] = None,
        workflow_params: Optional[Mapping[str, Any]] = None,
        qa_akm_dispatcher: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self.config = config
        self.console = console
        # Orchestrator 実行コンテキスト（`HVE_ORCHESTRATOR_ACTIVE` 環境変数の置換）。
        # None == 単独実行モード（Split fork 無効、Agent は plan.md/subissues.md 生成で停止）。
        # 非 None == Orchestrator 配下（Split 検出時に subissues.md からサブタスクを並列 fork）。
        self._orchestrator_ctx = orchestrator_ctx
        # Prompt renderingとruntimeで同じeffective workflow parametersを使う。
        # 呼出側の後続mutationがAzure実行境界へ影響しないようshallow copyを固定する。
        self._workflow_params: Mapping[str, Any] = MappingProxyType(
            dict(workflow_params or {})
        )
        self._qa_akm_dispatcher = qa_akm_dispatcher
        self._workiq_tool_called = False
        self._workiq_called_tools: List[str] = []
        # FR-TS-07: 自動 pin の学習材料。Step 終了時に id へ解決して記録する。
        self._toolsearch_called_tools: List[str] = []
        self._toolsearch_context: Any = None
        # Phase 6: サブセッション作成回数カウンター（observability）。
        # run_step() 開始時にリセットされる。テストから参照可能。
        self._sub_sessions_created: int = 0
        # ADR-0002: fan-out 子ステップ実行中に session_opts ビルダーから参照されるメタ
        self._current_fanout_meta: Optional[Dict[str, Any]] = None
        # Fork-integration (T2.1): ステップ毎のフォーク回数。0=初回、1+=リトライ。
        # DAGExecutor が `set_fork_index(step_id, n)` で更新し、_make_step_session_id
        # から参照することで session_id に `-fork{n}` suffix を付与する。
        self._fork_indices: Dict[str, int] = {}
        # TTFT (Time-to-First-Token) 計測: step_id -> turn_start time.monotonic()。
        # assistant.turn_start で記録、最初の assistant.message_delta で差分を計測し
        # console.stats_event("assistant_ttft", ...) として GUI へ通知後、削除。
        # assistant.usage / turn_end でもリセットする（取りこぼし防止）。
        self._ttft_pending: Dict[str, float] = {}
        # permission.requested の累積回数（GUI 詳細ポップアップ用）。
        self._permission_count: int = 0
        # T4 (GUI 統計): Skill 名の重複発火抑制。step_id -> set[skill_name]。
        # SDK skill.invoked と SKILL.md パス検出フォールバックの両方から書き込まれる。
        self._skill_invoked_seen: Dict[str, set] = {}
        # tool.execution_complete の failure だけで最低限の診断情報を出すため、
        # ID欠落時の直近 tool.execution_start を step 単位で一時保持する。
        self._last_tool_start_by_step: Dict[
            str, Tuple[str, Dict[str, Any], int]
        ] = {}
        # 現行 SDK は start/complete の両方へ tool_call_id を付与するため、
        # 並列呼び出しを step + call ID で相関する。値は失敗時に既存の
        # 安全な path/range 要約へ渡すだけで、shell command/query は出力しない。
        self._tool_start_by_call: Dict[
            Tuple[str, str], Tuple[str, Dict[str, Any], int]
        ] = {}
        # SDK model.call_failure の連続発生検出。Phase 1 メインタスクだけを
        # fail-fast 対象にし、2h step-timeout まで待ち続ける事態を防ぐ。
        self._model_call_failure_counts: Dict[str, int] = {}
        self._model_call_failure_events: Dict[str, asyncio.Event] = {}
        # FR-GUI-12: `stop_and_send` で受け取った (request_id, 指示)。主タスク復帰後に
        # 新しいターンとして送信し、その応答を Step の主応答として扱う。
        self._pending_job_redirects: Dict[str, List[Tuple[str, str]]] = {}
        self._asdw_data_deploy_environment_snapshots: Dict[
            str, Mapping[str, str]
        ] = {}
        self._session_security_violation_events: Dict[str, asyncio.Event] = {}
        self._session_security_violations: Dict[str, str] = {}
        # One Workflow instance owns one fenced state_version chain even when
        # DAG steps overlap.  A process-local lock keeps synchronous SQLite
        # transitions and token replacement indivisible across callbacks.
        self._durable_token_lock = threading.RLock()
        self._durable_token_initialized = False
        self._durable_token: Optional[LeaseToken] = None
        selected_steps = self._workflow_params.get("selected_steps") or ()
        if isinstance(selected_steps, str):
            selected_steps = tuple(
                item
                for item in re.split(r"[\s,]+", selected_steps)
                if item
            )
        self._durable_reuse_target_step_id = (
            str(selected_steps[0])
            if isinstance(selected_steps, (list, tuple)) and selected_steps
            else None
        )

    def _session_id_prefix(self) -> str:
        """SDKConfig.session_id_prefix が空ならデフォルト ("hve") を返す。"""
        prefix = (self.config.session_id_prefix or "").strip()
        return prefix or DEFAULT_SESSION_ID_PREFIX

    def _get_context_injection_max_chars(self) -> int:
        """コンテキスト注入上限を返す。None/不正値は既定値 20,000 に正規化する。"""
        value = getattr(self.config, "context_injection_max_chars", DEFAULT_CONTEXT_INJECTION_MAX_CHARS)
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return DEFAULT_CONTEXT_INJECTION_MAX_CHARS
        return normalized if normalized > 0 else DEFAULT_CONTEXT_INJECTION_MAX_CHARS

    def _make_step_session_id(self, step_id: str, suffix: str = "") -> str:
        """このステップ用の決定論的 session_id を生成する。

        Phase 2 (Resume): 同 run_id × step_id × suffix の組み合わせは常に同じ
        session_id を返すため、Phase 3 で `client.resume_session(session_id)` を
        呼べる前提を作る。

        Fork-integration (T2.1): `_fork_indices[step_id] > 0` の場合、suffix に
        `-fork{N}` を自動付与する。これにより DAGExecutor がリトライ時に
        `set_fork_index()` を呼ぶだけでフォーク用の独立 session_id が得られる。

        Args:
            step_id: ステップ識別子（"1.1" 等）
            suffix: サブセッション種別（"qa" / "review" / "pre-qa" 等）。空ならメインセッション。
        """
        effective_suffix = suffix
        fork_index = self._fork_indices.get(step_id, 0)
        if fork_index > 0:
            fork_token = f"fork{fork_index}"
            effective_suffix = f"{suffix}-{fork_token}" if suffix else fork_token
        return make_session_id(
            run_id=self.config.run_id,
            step_id=step_id,
            suffix=effective_suffix,
            prefix=self._session_id_prefix(),
        )

    def _make_fork_session_id(self, step_id: str, fork_index: int, suffix: str = "") -> str:
        """フォーク用 session_id を、`_fork_indices` 状態に依存せず直接生成する。

        Fork-integration (T2.1): KPI ロガーや診断ツールが「次に発火するフォーク
        session_id」を予測したい場合に使う。`_fork_indices[step_id]` を更新せず
        参照のみで完結するため、副作用がない。

        Args:
            step_id: ステップ識別子
            fork_index: フォーク回数（1 以上）。0 以下は ValueError。
            suffix: 追加 suffix。空でも可。

        Returns:
            `{prefix}-{run_id}-step-{step_id}[-{suffix}]-fork{N}` 形式の session_id

        Raises:
            ValueError: fork_index が 1 未満の場合
        """
        if fork_index < 1:
            raise ValueError(f"fork_index は 1 以上である必要があります（指定値: {fork_index}）")
        fork_token = f"fork{fork_index}"
        effective_suffix = f"{suffix}-{fork_token}" if suffix else fork_token
        return make_session_id(
            run_id=self.config.run_id,
            step_id=step_id,
            suffix=effective_suffix,
            prefix=self._session_id_prefix(),
        )

    def set_fork_index(self, step_id: str, fork_index: int) -> None:
        """ステップのフォーク回数を更新する（DAGExecutor のリトライフックから呼ぶ）。

        Fork-integration (T2.1): 次回 `_make_step_session_id(step_id)` 呼び出しから
        `-fork{N}` suffix が自動付与される。`fork_index=0` でリセット可。

        Args:
            step_id: ステップ識別子
            fork_index: 0 以上。0=フォークなし（初回）
        """
        if fork_index < 0:
            raise ValueError(f"fork_index は 0 以上である必要があります（指定値: {fork_index}）")
        if fork_index == 0:
            self._fork_indices.pop(step_id, None)
        else:
            self._fork_indices[step_id] = fork_index

    def _build_sub_session_opts(
        self,
        model: str,
        *,
        include_workiq: bool = False,
        step_id: Optional[str] = None,
        suffix: str = "",
        custom_agent: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """レビュー/QA 用の別セッション構築オプションを生成する。

        メインセッションの custom_agent / custom_agents を除外した
        最小限のオプションセットを返す。Work IQ は QA フェーズ専用で、
        include_workiq=True の場合だけ追加する。

        Phase 2 (Resume): step_id + suffix が指定された場合は決定論的 session_id を
        付与する（make_session_id で生成）。後方互換のため step_id=None の場合は
        session_id を付与しない（SDK 側で自動生成）。

        SPLIT-fork 拡張 (custom_agent): SPLIT_REQUIRED 分割サブタスクの実行では
        親 Step と **同じ Custom Agent** を継承する必要があるため、`custom_agent`
        引数が指定された場合のみ ``opts["custom_agent"]`` に設定する。QA/Review
        の既存呼び出しは ``custom_agent=None`` (省略) で従来挙動を維持する。
        """
        opts: Dict[str, Any] = {
            "on_permission_request": self._build_step_permission_handler(
                step_id,
                custom_agent,
            ),
            "streaming": True,
        }
        # Q1=C / Q3=a: SDK へ `custom_agent` / `custom_agents` キーは渡さない。
        # SPLIT-fork 用の Agent 識別子継承は呼び出し側で Prompt 前置として実現する。
        # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
        _wire_model = to_wire_model(model)
        if _wire_model:
            opts["model"] = _wire_model
        _mcp = _filter_mcp_servers_for_session(
            self.config.mcp_servers,
            include_workiq=include_workiq,
        )

        # Work IQ MCP Server は QA フェーズ専用のサブセッションにだけ追加する。
        if (
            include_workiq
            and self.config.is_workiq_qa_enabled()
            and is_workiq_available()
        ):
            _workiq_mcp = build_workiq_mcp_config(
                tenant_id=self.config.workiq_tenant_id,
                request_timeout=self.config.workiq_request_timeout,
            )
            for _k, _v in _workiq_mcp.items():
                if _k not in _mcp:
                    _mcp[_k] = _v
            # FR-CLI-76 (v2.41): `mcp_servers` を明示すると共通経路の縮約が効かず自動探索が
            # 残るため、プラグイン由来の `workiq` が tools:["*"] で併存し `_hve_workiq` の
            # 最小権限 allowlist を迂回できてしまう。宣言分（Work IQ 別名を除く）を併合して
            # 自動探索を止める。宣言が無い場合は従来どおり自動探索を残す。
            opts["mcp_servers"] = _mcp
            _apply_repository_mcp_scope(opts, workflow_id=workflow_id)
            _mcp = opts["mcp_servers"]

        if _mcp:
            opts["mcp_servers"] = _mcp

        # G-1: SDK の available_tools / excluded_tools をサブセッションへ伝搬する
        # （メインセッションと同じ制限をサブにも適用）
        if self.config.available_tools:
            opts["available_tools"] = list(self.config.available_tools)
        if self.config.excluded_tools:
            opts["excluded_tools"] = list(self.config.excluded_tools)

        # FR-MODEL-04: ツール定義遅延ロードもメインと同一値をサブへ伝搬する。
        if self.config.tool_search:
            opts["tool_search"] = {"enabled": True}

        # Phase 2: 決定論的 session_id を付与（step_id + suffix が指定された場合のみ）
        if step_id:
            opts["session_id"] = self._make_step_session_id(step_id, suffix=suffix)

        return opts

    def _build_step_permission_handler(
        self,
        step_id: Optional[str],
        custom_agent: Optional[str],
    ) -> Callable[[Any, Dict[str, str]], Any]:
        """Return the default SDK permission handler for an Agent session."""
        from copilot.session import PermissionHandler

        return PermissionHandler.approve_all

    # ------------------------------------------------------------------
    # Phase 6: サブセッション要否の判定ヘルパー（テスト容易性のために分離）
    # ------------------------------------------------------------------

    def _should_use_pre_qa_sub_session(self, qa_model: str, workiq_available: bool) -> bool:
        """事前 QA にサブセッションが必要かを判定する。

        以下のいずれかが True の場合にサブセッションを作成する:
        - qa_model が main_model と異なる（同じ "Auto" 同士なら同一とみなす）
        - WorkIQ MCP が利用可能（QA 専用セッションに WorkIQ を含める必要があるため）
        """
        return (qa_model != self.config.model) or workiq_available

    def _should_use_qa_sub_session(self, qa_model: str, workiq_available: bool) -> bool:
        """事後 QA にサブセッションが必要かを判定する。

        事前 QA と同一条件:
        - qa_model が main_model と異なる
        - WorkIQ MCP が利用可能
        """
        return (qa_model != self.config.model) or workiq_available

    def _should_use_review_sub_session(self, review_model: str) -> bool:
        """敵対的レビューにサブセッションが必要かを判定する。

        review_model が main_model と異なる場合にのみサブセッションを作成する。
        Review フェーズでは WorkIQ は使用しないためモデル差異のみを判定する。
        """
        return review_model != self.config.model

    def _log_sub_session_reason(
        self,
        step_id: str,
        phase: str,
        qa_model: Optional[str] = None,
        workiq_available: bool = False,
    ) -> None:
        """サブセッション作成理由を console.event() で記録する（secrets 非出力）。

        呼び出し元は必ずサブセッション作成条件（モデル差異 or WorkIQ 有効）が
        True のときのみ呼び出すこと。条件が全て False の状態で呼ばれた場合は
        "(内部エラー: 理由不明)" と記録する（呼び出しバグの早期検知用）。

        Args:
            step_id: ステップ識別子（ログ識別用）
            phase: フェーズ名（"Pre-QA" / "Post-QA" / "Review"）
            qa_model: QA/Review 用モデル名（Noneの場合はモデル差異ログを省略）
            workiq_available: WorkIQ が有効かどうか
        """
        _reasons: List[str] = []
        if qa_model is not None and qa_model != self.config.model:
            _reasons.append(
                f"モデル差異 (sub={qa_model!r}, main={self.config.model!r})"
            )
        if workiq_available:
            _reasons.append("WorkIQ 有効")
        # 呼び出し元の責務: _reasons が空になるのは呼び出し側のバグ
        _reason_str = "、".join(_reasons) if _reasons else "(内部エラー: 理由不明)"
        self.console.event(
            f"  ▶ [{step_id}] {phase} サブセッション作成 — 理由: {_reason_str}"
        )

    def _log_main_session_reuse(self, step_id: str, phase: str) -> None:
        """メインセッション再利用を console.event() で記録する。"""
        self.console.event(
            f"  🔄 [{step_id}] {phase} メインセッションを再利用"
        )

    def _durable_lease_token_from_context(self) -> Optional[LeaseToken]:
        """Rebuild the fenced token from canonical durable context fields."""
        with self._durable_token_lock:
            if self._durable_token_initialized:
                return self._durable_token

            ctx = self._orchestrator_ctx
            if ctx is None:
                self._durable_token_initialized = True
                return None

            execution_id = getattr(ctx, "execution_id", None)
            instance_id = getattr(ctx, "instance_id", None)
            state_version = getattr(ctx, "expected_state_version", None)
            recovery_action = getattr(ctx, "recovery_action", None)
            lease_owner = getattr(ctx, "lease_owner", None)
            lease_generation = getattr(ctx, "lease_generation", None)
            values = (
                execution_id,
                instance_id,
                state_version,
                recovery_action,
                lease_owner,
                lease_generation,
            )
            if all(value is None for value in values):
                self._durable_token_initialized = True
                return None

            # A newly registered normal child legitimately carries identity
            # before T18 acquires and attaches its Workflow lease.
            if (
                type(execution_id) is str
                and execution_id
                and type(instance_id) is str
                and instance_id
                and all(
                    value is None
                    for value in (
                        state_version,
                        recovery_action,
                        lease_owner,
                        lease_generation,
                    )
                )
            ):
                self._durable_token_initialized = True
                return None

            if (
                type(execution_id) is not str
                or not execution_id
                or type(instance_id) is not str
                or not instance_id
                or type(state_version) is not int
                or state_version < 0
                or type(lease_owner) is not str
                or not lease_owner
                or type(lease_generation) is not int
                or lease_generation < 0
            ):
                raise DurableStateError("durable runner context is incomplete")
            self._durable_token = LeaseToken(
                execution_id=execution_id,
                instance_id=instance_id,
                owner=lease_owner,
                generation=lease_generation,
                state_version=state_version,
            )
            self._durable_token_initialized = True
            return self._durable_token

    def _set_durable_lease_token(self, token: LeaseToken) -> None:
        """Replace the shared fenced token after an orchestrator transition."""
        if not isinstance(token, LeaseToken):
            raise DurableStateError("invalid durable lease token")
        with self._durable_token_lock:
            self._durable_token = token
            self._durable_token_initialized = True

    def _commit_durable_checkpoint(
        self,
        *,
        step_id: str,
        phase: str,
        session_id: Any,
    ) -> None:
        """Commit one phase/session snapshot before its first SDK action."""
        if type(phase) is not str or not phase:
            raise DurableStateError("durable phase is invalid")
        if type(session_id) is not str or not session_id:
            raise DurableStateError("durable session ID is invalid")
        with self._durable_token_lock:
            token = self._durable_lease_token_from_context()
            if token is None:
                return
            with RunStateStore(default_state_path()) as store:
                next_token = store.transition_step(
                    token,
                    step_id,
                    "running",
                    phase=phase,
                    phase_state="running",
                    session_id=session_id,
                )
            self._durable_token = next_token
            self._durable_token_initialized = True

    def _load_durable_reuse_session_id(self, step_id: str) -> Optional[str]:
        """Return the persisted Main session selected for durable recovery.

        The row is read before any SDK session action.  Only the explicit
        ``reuse-session`` action enters this path; ``restart-step`` deliberately
        continues through the normal deterministic attempt-session path.
        """
        ctx = self._orchestrator_ctx
        if getattr(ctx, "recovery_action", None) != "reuse-session":
            return None
        target_step_id = self._durable_reuse_target_step_id
        if type(target_step_id) is not str or not target_step_id:
            raise RuntimeError(
                "durable reuse-session target Step is unavailable"
            )
        if step_id != target_step_id:
            return None

        token = self._durable_lease_token_from_context()
        if token is None:
            raise RuntimeError("durable reuse-session context is incomplete")

        with RunStateStore(default_state_path()) as store:
            rows = store.list_steps(token.execution_id, token.instance_id)

        def _field(record: Any, name: str) -> Any:
            if isinstance(record, Mapping):
                return record.get(name)
            try:
                return record[name]
            except (IndexError, KeyError, TypeError):
                return getattr(record, name, None)

        targets = [
            row
            for row in rows
            if _field(row, "record_kind") == "step"
            and _field(row, "step_id") == step_id
        ]
        if len(targets) != 1:
            raise RuntimeError(
                "durable reuse-session requires exactly one persisted target Step"
            )

        target = targets[0]
        if _field(target, "phase") != "main":
            raise RuntimeError(
                "durable reuse-session is supported only for the Main phase"
            )
        session_id = _field(target, "session_id")
        if type(session_id) is not str or not session_id.strip():
            raise RuntimeError(
                "durable reuse-session requires a saved Main session ID"
            )
        return session_id

    # ------------------------------------------------------------------
    # メインセッション生成
    # ------------------------------------------------------------------

    async def _create_main_session(
        self,
        *,
        client: Any,
        session_opts: Dict[str, Any],
        step_id: str,
        workflow_id: Optional[str] = None,
        requires_external_skill_directories: bool = False,
    ) -> Any:
        """メインセッションを create_session で構築する。"""
        return await _create_session_with_auto_reasoning_fallback(
            client,
            session_opts,
            config=self.config,
            step_id=step_id,
            workflow_id=workflow_id,
            subtask_kind="main",
            console=self.console,
            requires_external_skill_directories=requires_external_skill_directories,
        )

    @staticmethod
    def _get_required_skills_for_step(
        workflow_id: Optional[str],
        step_id: str,
        workflow: Optional[Any],
    ) -> List[str]:
        """Resolve one Step's required Skills without changing resolver policy."""
        if not workflow_id:
            return []
        try:
            from .workflow_registry import get_step
            from .skill_resolver import get_required_skills_for_step
        except ImportError:  # pragma: no cover
            from workflow_registry import get_step  # type: ignore[import-not-found,no-redef]
            from skill_resolver import get_required_skills_for_step  # type: ignore[import-not-found,no-redef]

        resolved_workflow_id = getattr(workflow, "id", None) or workflow_id
        base_step_id = str(step_id).split("/", 1)[0]
        step = get_step(resolved_workflow_id, base_step_id)
        if step is None:
            return []
        return get_required_skills_for_step(
            workflow_id=resolved_workflow_id,
            step_id=base_step_id,
            step_declared_required=list(
                getattr(step, "required_skills", []) or []
            ),
        )

    @staticmethod
    def _add_required_external_skill_directories(
        session_opts: Dict[str, Any],
        required_skills: List[str],
    ) -> bool:
        """Attach only declared external required Skills to one session."""
        if not required_skills:
            return False
        try:
            try:
                from .skill_resolver import (
                    get_external_skill_directory,
                    get_skill_directory,
                )
            except ImportError:  # pragma: no cover
                from skill_resolver import (  # type: ignore[import-not-found,no-redef]
                    get_external_skill_directory,
                    get_skill_directory,
                )
        except Exception as exc:
            raise RuntimeError(
                "HVE required Skill resolver is unavailable before session creation."
            ) from exc

        external_directories: List[str] = []
        missing: List[str] = []
        for skill in required_skills:
            resolved_directory = get_skill_directory(skill)
            if resolved_directory is None:
                missing.append(skill)
                continue
            external_directory = get_external_skill_directory(skill)
            if external_directory is not None and resolved_directory == external_directory:
                external_directories.append(str(external_directory))

        if missing:
            raise RuntimeError(
                "HVE required Skill directory is unavailable before session creation: "
                + ", ".join(sorted(set(missing)))
            )

        directories = list(session_opts.get("skill_directories") or [])
        if not directories:
            directories = _repository_skill_directories(required_skills)
        seen: set[str] = {
            os.path.normcase(os.path.normpath(directory))
            for directory in directories
        }
        for directory in external_directories:
            normalized = os.path.normcase(os.path.normpath(directory))
            if normalized not in seen:
                directories.append(directory)
                seen.add(normalized)
        if directories:
            # FR-CLI-73: repository Skill の公開範囲は required 宣言で決まるため、
            # external Skill が無い Step でも解決済みディレクトリを確定させる。
            session_opts["skill_directories"] = directories
        return bool(external_directories)

    @staticmethod
    def _get_optional_skills_for_step(
        workflow_id: Optional[str],
        step_id: str,
    ) -> List[str]:
        """Resolve optional candidates without making them a session precondition."""
        if not workflow_id:
            return []
        try:
            try:
                from .skill_resolver import get_optional_skills_for_step
            except ImportError:  # pragma: no cover
                from skill_resolver import get_optional_skills_for_step  # type: ignore[import-not-found,no-redef]
            return get_optional_skills_for_step(workflow_id, step_id)
        except Exception:
            return []

    @staticmethod
    def _add_available_optional_external_skill_directories(
        session_opts: Dict[str, Any],
        optional_skills: List[str],
    ) -> List[str]:
        """Attach installed optional external candidates without making them required."""
        if not optional_skills:
            return []
        try:
            try:
                from .skill_resolver import get_external_skill_directory
            except ImportError:  # pragma: no cover
                from skill_resolver import get_external_skill_directory  # type: ignore[import-not-found,no-redef]
        except Exception:
            return []

        resolved: List[Tuple[str, str]] = []
        for skill in optional_skills:
            external_skill_directory = get_external_skill_directory(skill)
            if external_skill_directory is not None:
                resolved.append((skill, str(external_skill_directory)))
        if not resolved:
            return []

        directories = list(session_opts.get("skill_directories") or [])
        if not directories:
            directories = _repository_skill_directories(optional_skills)
        seen: set[str] = {
            os.path.normcase(os.path.normpath(directory))
            for directory in directories
        }
        available_names: List[str] = []
        for skill, directory_text in resolved:
            normalized = os.path.normcase(os.path.normpath(directory_text))
            if normalized not in seen:
                directories.append(directory_text)
                seen.add(normalized)
            available_names.append(skill)
        session_opts["skill_directories"] = directories
        return available_names

    @staticmethod
    def _is_foundry_required_step(required_skills: List[str]) -> bool:
        """Return whether this Step requires the external Foundry meta Skill."""
        return "microsoft-foundry" in required_skills

    async def _verify_foundry_required_session_mcp_servers(
        self,
        session: Any,
    ) -> None:
        """Require Azure and Microsoft Learn MCP servers to be connected.

        Unlike ASDW Step 1.3, this is a subset check: normal config discovery
        can load additional non-Foundry MCP servers without weakening the two
        required Foundry capabilities.
        """
        try:
            mcp_list = await session.rpc.mcp.list()
        except Exception as exc:
            raise RuntimeError(
                "Foundry-required MCP server list is unavailable after session creation."
            ) from exc

        connected: set[str] = set()
        for server in getattr(mcp_list, "servers", []) or []:
            name = str(getattr(server, "name", "") or "")
            status = getattr(server, "status", None)
            status_value = getattr(status, "value", status)
            if str(status_value or "").casefold() == "connected":
                connected.add(name)

        missing = set(_FOUNDRY_REQUIRED_MCP_SERVERS) - connected
        if missing:
            raise RuntimeError(
                "Foundry-required MCP servers are unavailable or disconnected: "
                + ", ".join(sorted(missing))
            )

    # ------------------------------------------------------------------
    # メインタスク成果物改善ヘルパー（Phase 2c / Phase 3 / Phase 4 共通）
    # ------------------------------------------------------------------

    async def _apply_main_artifact_improvements(
        self,
        *,
        session: Any,
        step_id: str,
        title: str,
        workflow_id: Optional[str],
        custom_agent: Optional[str],
        original_prompt: str,
        main_output: str,
        source_phase: str,
        improvement_context: str,
        timeout: float,
    ) -> str:
        """改善材料に基づきメインタスク成果物を改善する共通ヘルパー。

        Args:
            session: メインセッション（Phase 1 と同じセッション）。
            step_id: ステップ識別子。
            title: ステップタイトル。
            workflow_id: ワークフロー識別子（成果物形式ルールの適用に使用）。
            custom_agent: Custom Agent 名。
            original_prompt: メインタスク実行時の元プロンプト。
            main_output: Phase 1 メインタスクの実行結果（参考）。Phase 2c/3/4 の改善適用後も
                再取得されないため、実際の最新成果物はセッションのコンテキストに蓄積されている。
            source_phase: 改善材料の出所フェーズ名。
            improvement_context: 改善材料のテキスト。
            timeout: セッションタイムアウト秒数。

        Returns:
            改善後の応答テキスト（失敗時は空文字）。
        """
        if not improvement_context or not improvement_context.strip():
            return ""

        try:
            _max_context_chars = self._get_context_injection_max_chars()
            _trunc_prompt = _truncate_context_with_warn(
                original_prompt, _max_context_chars,
                label=f"{source_phase} original_prompt", console=self.console,
            )
            _trunc_output = _truncate_context_with_warn(
                main_output, _max_context_chars,
                label=f"{source_phase} main_output", console=self.console,
            )
            _trunc_context = _truncate_context_with_warn(
                improvement_context, _max_context_chars,
                label=f"{source_phase} improvement_context", console=self.console,
            )

            _improve_prompt = MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT.format(
                source_phase=source_phase,
                workflow_id=workflow_id or "(未指定)",
                step_id=step_id,
                step_title=title,
                custom_agent=str(custom_agent) if custom_agent else "None",
                original_prompt=_trunc_prompt,
                main_output=_trunc_output,
                improvement_context=_trunc_context,
            )

            _response = await session.send_and_wait(_improve_prompt, timeout=timeout)
            _result = _extract_text(_response)

            if not _result or not _result.strip():
                self.console.warning(
                    f"[{step_id}] {source_phase}: メイン成果物改善の応答が空でした。"
                )

            return _result
        except Exception as exc:
            self.console.warning(
                f"[{step_id}] {source_phase}: メイン成果物改善に失敗しました（後続処理を継続）: {exc}"
            )
            return ""

    def _check_diff_after_improvement(self, step_id: str, source_phase: str) -> List[str]:
        """改善適用後に git diff を確認し、変更ファイルを返す。

        改善が必要と判定されたにもかかわらず差分がない場合は warning を出力する。

        Returns:
            変更されたファイルのリスト（差分なしの場合は空リスト）。
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            if result.returncode != 0:
                self.console.warning(
                    f"[{step_id}] {source_phase}: git diff の実行に失敗しました"
                    f" (exit={result.returncode}): {result.stderr.strip()}"
                )
                return []
            changed_files = [f for f in result.stdout.splitlines() if f.strip()]
            if changed_files:
                self.console.event(
                    f"  📝 [{step_id}] {source_phase}: 差分あり ({len(changed_files)} ファイル変更): "
                    + ", ".join(changed_files[:5])
                    + ("..." if len(changed_files) > 5 else "")
                )
            else:
                self.console.warning(
                    f"[{step_id}] {source_phase}: 改善が適用されましたが git diff に差分がありません。"
                    " 成果物がセッション内のみで更新された可能性があります。"
                )
            return changed_files
        except Exception as exc:
            self.console.warning(
                f"[{step_id}] {source_phase}: git diff 確認に失敗しました: {exc}"
            )
            return []

    # ------------------------------------------------------------------
    # ファイル I/O 追跡ヘルパー
    # ------------------------------------------------------------------

    def _resolve_run_id_safely(self) -> str:
        """run_id を取得する。解決できなくても呼び出し元を落とさない。"""
        try:
            from .split_fork import resolve_run_id
        except ImportError:  # pragma: no cover - script execution
            from split_fork import resolve_run_id  # type: ignore[no-redef]
        try:
            return str(resolve_run_id())
        except Exception:
            return ""

    def _record_toolsearch_usage(self, step_id: str) -> None:
        """FR-TS-07: Step で呼ばれたツールを利用履歴へ記録し、蓄積をクリアする。"""
        called = self._toolsearch_called_tools
        self._toolsearch_called_tools = []
        context = self._toolsearch_context
        self._toolsearch_context = None
        if not called or context is None:
            return
        try:
            from .toolsearch.session import record_session_usage, resolve_called_tool_ids
        except ImportError:  # pragma: no cover - script execution
            return
        try:
            record_session_usage(
                resolve_called_tool_ids(context, called),
                # run_id を混ぜる。`_make_step_session_id` は決定論なのでそのまま使うと
                # 同じ Step を何回実行しても session 数が 1 のままで、
                # 自動 pin のウォームアップ（FR-TS-07）に到達しない。
                session_id=f"{self._resolve_run_id_safely()}:{step_id}",
                workflow_id=getattr(context, "workflow_id", None),
                step_id=getattr(context, "step_id", None),
            )
        except Exception:
            # 履歴記録の失敗で Step を落とさない。
            pass

    def _track_tool_files(self, step_id: str, tool_name: str, args: dict) -> None:
        """ツール実行イベントからファイルパスを抽出し Console に記録・表示する。"""
        import os
        if tool_name in _SKIP_TOOLS:
            return

        if tool_name in ("apply_patch", "applyPatch"):
            self._track_apply_patch_files(step_id, args)
            return

        # シェル系ツール: command キーからファイル操作を簡易抽出
        if tool_name == "bash":
            command = args.get("command", "")
            if isinstance(command, str) and command:
                self._track_bash_files(step_id, command)
            return

        if tool_name == "powershell":
            command = args.get("command", "")
            if isinstance(command, str) and command:
                self._track_powershell_files(step_id, command)
            return

        # ファイル操作ツール: 引数キーからパスを抽出
        for key in _FILE_PATH_KEYS:
            val = args.get(key)
            if val and isinstance(val, str):
                normalized = os.path.normpath(val)
                if tool_name in _READ_WRITE_TOOLS:
                    self.console.track_file(step_id, normalized, "read")
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "read")
                    self.console.file_io(step_id, normalized, "write")
                elif tool_name in _WRITE_TOOLS:
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "write")
                else:
                    self.console.track_file(step_id, normalized, "read")
                    self.console.file_io(step_id, normalized, "read")
                break

    def _track_apply_patch_files(self, step_id: str, args: dict) -> None:
        """apply_patch の V4A patch header から更新対象ファイルだけを追跡する。"""
        import os
        import re

        patch_text = args.get("input") or args.get("patch") or args.get("content") or ""
        if not isinstance(patch_text, str) or not patch_text:
            return

        seen: set[str] = set()
        for line in patch_text.splitlines():
            match = re.match(r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s+(?P<path>.+?)\s*$", line)
            if not match:
                continue
            path = match.group("path").strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[0].strip()
            if not path or path in seen:
                continue
            seen.add(path)
            normalized = os.path.normpath(path)
            self.console.track_file(step_id, normalized, "write")
            self.console.file_io(step_id, normalized, "write")

    def _track_bash_files(self, step_id: str, command: str) -> None:
        """bash コマンド文字列からファイル操作を簡易抽出する。"""
        import os
        import re

        for m in re.finditer(r'tee(?:\s+-a)?\s+([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "write")
                self.console.file_io(step_id, os.path.normpath(path), "write")

        for m in re.finditer(r'(?:\d+>>?|>>?)\s*([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "write")
                self.console.file_io(step_id, os.path.normpath(path), "write")

        for m in re.finditer(
            r'\b(?:cp|mv)\s+(?:-\w+\s+)*([^\s;|&]+)\s+([^\s;|&]+)', command
        ):
            dest = m.group(2).strip("'\"")
            if dest and not dest.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(dest), "write")
                self.console.file_io(step_id, os.path.normpath(dest), "write")

        for m in re.finditer(
            r'\b(?:cat|head|tail|less|more)\s+(?:-\w+\s+)*([^\s;|&>]+)', command
        ):
            path = m.group(1).strip("'\"")
            if path and not path.startswith("-"):
                self.console.track_file(step_id, os.path.normpath(path), "read")
                self.console.file_io(step_id, os.path.normpath(path), "read")

    def _detect_skill_load_from_args(self, step_id: str, args: dict) -> None:
        """ツール引数中のパスから `.github/skills/<name>/` 配下の読込を検出し、
        skill_invoked stats イベントを発火する（SDK skill.invoked 未発火時の
        フォールバック）。重複発火は ``self._skill_invoked_seen`` で抑制。
        """
        import re as _re

        # `.github/skills/<name>/` 配下 (SKILL.md / references/*.md 等) を捕捉。
        # Windows パス区切り `\` と Unix `/` の両方に対応。
        pattern = _re.compile(
            r"[\\/]\.github[\\/]skills[\\/]([^\\/]+)[\\/]",
            _re.IGNORECASE,
        )
        seen = self._skill_invoked_seen.setdefault(step_id, set())

        def _scan(val: object) -> None:
            if isinstance(val, str):
                m = pattern.search(val)
                if m:
                    name = m.group(1).strip()
                    if name and name not in seen:
                        seen.add(name)
                        try:
                            self.console.stats_event(
                                "skill_invoked",
                                step_id=step_id,
                                name=name,
                                source="path_detect",
                            )
                        except Exception:
                            pass
            elif isinstance(val, dict):
                for v in val.values():
                    _scan(v)
            elif isinstance(val, list):
                for v in val:
                    _scan(v)

        _scan(args)

    def _track_powershell_files(self, step_id: str, command: str) -> None:
        """PowerShell コマンド文字列からファイル操作を簡易抽出する（best-effort）。

        設計方針:
        - -Path / -FilePath / -LiteralPath 明示パラメータからのキャプチャを最優先
        - パイプライン/複文ごとに cmdlet を判定して read/write を決める
        - PowerShell のパラメータ構文の完全な網羅は目的としない
        - 未検出ケースがあっても step_io_summary が空になるだけで動作に影響しない
        """
        import os
        import re

        path_write_cmdlets = {"set-content", "add-content", "new-item"}
        file_path_write_cmdlets = {"out-file"}

        # パイプラインや複文ごとに判定（例: Get-Content ... | Out-File ...）
        for segment in re.split(r"[|;]", command):
            seg = segment.strip()
            if not seg:
                continue

            cmdlet_match = re.search(r"\b([A-Za-z]+-[A-Za-z][A-Za-z0-9]*)\b", seg)
            cmdlet = cmdlet_match.group(1).lower() if cmdlet_match else ""

            # -Path / -LiteralPath
            for m in re.finditer(
                r'-(?:Path|LiteralPath)\s+([^\s;|&]+)', seg, re.IGNORECASE
            ):
                path = m.group(1).strip("'\"")
                if is_plain_repo_path_token(path) and not path.startswith("-"):
                    # 既知 write cmdlet 以外は read 扱い（best-effort）
                    mode = "write" if cmdlet in path_write_cmdlets else "read"
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, mode)
                    self.console.file_io(step_id, normalized, mode)

            # -FilePath
            for m in re.finditer(r'-FilePath\s+([^\s;|&]+)', seg, re.IGNORECASE):
                path = m.group(1).strip("'\"")
                if is_plain_repo_path_token(path) and not path.startswith("-"):
                    # 既知 write cmdlet 以外は read 扱い（best-effort）
                    mode = "write" if cmdlet in file_path_write_cmdlets else "read"
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, mode)
                    self.console.file_io(step_id, normalized, mode)

            # -Destination（copy/move の出力先）
            for m in re.finditer(r'-Destination\s+([^\s;|&]+)', seg, re.IGNORECASE):
                path = m.group(1).strip("'\"")
                if is_plain_repo_path_token(path) and not path.startswith("-"):
                    normalized = os.path.normpath(path)
                    self.console.track_file(step_id, normalized, "write")
                    self.console.file_io(step_id, normalized, "write")

        # PowerShell リダイレクト演算子 (>, >>)
        for m in re.finditer(r'(?:\d+)?>>?\s*([^\s;|&]+)', command):
            path = m.group(1).strip("'\"")
            if is_plain_repo_path_token(path) and not path.startswith("-"):
                normalized = os.path.normpath(path)
                self.console.track_file(step_id, normalized, "write")
                self.console.file_io(step_id, normalized, "write")

    @staticmethod
    def _build_action_display(tool_name: str, args: Any) -> Tuple[str, str]:
        """ツール名と引数から Copilot CLI 風の action_name/detail を生成する。"""
        action_name = _ACTION_DISPLAY.get(tool_name, tool_name)
        detail = ""
        if not isinstance(args, dict):
            return action_name, detail

        if tool_name in ("grep", "rg", "search"):
            pattern = args.get("pattern") or args.get("query") or ""
            scope = (
                args.get("scope")
                or args.get("path")
                or args.get("paths")
                or args.get("glob")
                or args.get("include")
                or ""
            )
            if pattern:
                detail = f"\"{pattern}\""
                if scope:
                    detail = f"{detail} ({scope})"
            elif scope:
                detail = str(scope)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("read_file", "readFile", "cat", "head", "tail"):
            path = args.get("path") or args.get("filePath") or args.get("file_path") or ""
            if path:
                action_name = f"Read {Path(str(path)).name}"
                detail = str(path)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("edit_file", "editFile", "write_file", "writeFile", "create_file", "createFile"):
            path = args.get("path") or args.get("filePath") or args.get("file_path") or ""
            if path:
                action_name = f"{_ACTION_DISPLAY.get(tool_name, tool_name)} {Path(str(path)).name}"
                detail = str(path)
            return action_name, StepRunner._truncate_action_detail(detail)

        if tool_name in ("bash", "powershell"):
            command = args.get("command") or ""
            if command:
                detail = str(command)
            return action_name, StepRunner._truncate_action_detail(detail)

        for key in ("command", "path", "filePath", "file_path", "query", "pattern", "url", "intent"):
            val = args.get(key)
            if val:
                val_str = str(val)
                detail = val_str
                break
        return action_name, StepRunner._truncate_action_detail(detail)

    @staticmethod
    def _truncate_action_detail(text: str) -> str:
        """アクション詳細文字列を表示上限で切り詰める。"""
        if len(text) > _ACTION_DETAIL_MAX_LENGTH:
            return text[:_ACTION_DETAIL_MAX_LENGTH] + "..."
        return text

    @staticmethod
    def _build_tool_result_text(data: Any) -> str:
        """tool.execution_complete の data から結果サマリー文字列を生成する。"""
        get = StepRunner._get
        result_summary = get(data, "result_summary", "resultSummary", default="")
        if result_summary:
            return str(result_summary)

        output = get(data, "output", default="")
        if isinstance(output, str):
            stripped = output.strip()
            if not stripped:
                return ""
            lines = stripped.splitlines()
            if len(lines) == 1:
                return lines[0][:_ACTION_RESULT_SINGLE_LINE_MAX_LENGTH]
            return f"{len(lines)} lines"
        return ""

    @staticmethod
    def _build_failed_tool_args_summary(tool_name: str, args: Any) -> str:
        """失敗 tool ログへ付ける安全な引数サマリーを生成する。

        調査不能だった view_range 系の失敗に限定して有用な情報を残す。
        shell command や任意 query は秘密情報・ログ肥大化リスクがあるため含めない。
        """
        if not isinstance(args, dict):
            return ""
        if tool_name not in ("view", "read_file", "readFile", "cat", "head", "tail"):
            return ""

        parts: List[str] = []
        for key in (
            "path",
            "filePath",
            "file_path",
            "view_range",
            "viewRange",
            "startLine",
            "endLine",
            "start_line",
            "end_line",
        ):
            if key not in args:
                continue
            value = args.get(key)
            if value is None or value == "":
                continue
            value_text = str(value)
            if len(value_text) > _ACTION_DETAIL_MAX_LENGTH:
                value_text = value_text[:_ACTION_DETAIL_MAX_LENGTH] + "..."
            parts.append(f"{key}={value_text}")
        return ", ".join(parts)

    @staticmethod
    def _safe_failed_tool_args(tool_name: str, args: Any) -> Dict[str, Any]:
        """相関中に保持してよい read/view 系の path/range 引数だけを返す。"""
        if not isinstance(args, dict):
            return {}
        if tool_name not in ("view", "read_file", "readFile", "cat", "head", "tail"):
            return {}
        safe_keys = (
            "path",
            "filePath",
            "file_path",
            "view_range",
            "viewRange",
            "startLine",
            "endLine",
            "start_line",
            "end_line",
        )
        return {key: args[key] for key in safe_keys if key in args}

    def _clear_tool_start_state(self, step_id: str) -> None:
        """1 Step の未完了 tool start 相関情報だけを破棄する。"""
        normalized_step_id = str(step_id)
        self._last_tool_start_by_step.pop(normalized_step_id, None)
        for key in [
            key for key in self._tool_start_by_call if key[0] == normalized_step_id
        ]:
            self._tool_start_by_call.pop(key, None)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    async def _run_pre_execution_qa(
        self,
        session: Any,
        client: Any,
        step_id: str,
        original_prompt: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
        current_phase: int,
        total_phases: int,
        main_session_id: Optional[str] = None,
    ) -> str:
        """Phase 0: 事前 QA 質問票生成・回答収集・Work IQ (optional)。

        PRE_EXECUTION_QA_PROMPT_V2 を使用し、メインタスク実行前に不明点を確認する。
        全 Workflow で実行する。AKM 自身では回答済み QA を保存するが、
        QA 起点 AKM は再登録しない。

        Returns:
            pre_qa_context: Phase 1 プロンプト先頭に注入する Markdown 文字列。
            空文字の場合は注入なし。
        """
        self.console.step_phase_start(step_id, current_phase, total_phases, "事前 QA")
        phase0_start = time.time()
        effective_main_session_id = (
            main_session_id or self._make_step_session_id(step_id)
        )

        _qa_model = self.config.get_qa_model()
        _qa_workiq_requested = (
            self.config.is_workiq_qa_enabled()
            and not _is_asdw_data_deploy_step(step_id, custom_agent)
        )
        _qa_workiq_configured = any(
            _is_workiq_mcp_server_name(_name)
            for _name in (self.config.mcp_servers or {})
        )
        _qa_workiq_available = (
            _qa_workiq_requested
            and (_qa_workiq_configured or is_workiq_available())
        )
        if _qa_workiq_requested and not _qa_workiq_available:
            self.console.warning(
                "Work IQ が検出できません。事前 QA フェーズの Work IQ 連携をスキップします。"
            )

        _use_pre_qa_sub_session = self._should_use_pre_qa_sub_session(_qa_model, _qa_workiq_available)
        _pre_qa_session = None
        pre_qa_context = ""
        try:
            _effective_pre_qa_session = session
            # Phase 0a: 事前質問票生成 — 原プロンプトをコンテキストとして注入
            _max_context_chars = self._get_context_injection_max_chars()
            _prompt_context = _truncate_context_with_warn(
                original_prompt, _max_context_chars,
                label="Phase 0 Pre-QA original_prompt", console=self.console,
            )
            _effective_pre_qa_prompt = (
                "以下はこれから実行するタスクのプロンプトです。"
                "成果物はまだ存在しません。このプロンプトを前提として事前質問票を作成してください。\n\n"
                f"=== タスクプロンプト（最大{_max_context_chars:,}文字） ===\n"
                f"{_prompt_context}\n"
                "=== タスクプロンプトここまで ===\n\n"
                f"{PRE_EXECUTION_QA_PROMPT_V2}"
            )

            if _use_pre_qa_sub_session:
                self._log_sub_session_reason(
                    step_id, "Pre-QA",
                    qa_model=_qa_model,
                    workiq_available=_qa_workiq_available,
                )
                _pre_qa_session_opts = self._build_sub_session_opts(
                    _qa_model,
                    include_workiq=_qa_workiq_available,
                    step_id=step_id,
                    suffix="pre-qa",
                    custom_agent=custom_agent,
                    workflow_id=workflow_id,
                )
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="pre-qa",
                    session_id=_pre_qa_session_opts["session_id"],
                )
                _pre_qa_required_skills = self._get_required_skills_for_step(
                    workflow_id,
                    step_id,
                    None,
                )
                _pre_qa_requires_external_skills = (
                    self._add_required_external_skill_directories(
                        _pre_qa_session_opts,
                        _pre_qa_required_skills,
                    )
                )
                _pre_qa_session = await _create_session_with_auto_reasoning_fallback(
                    client,
                    _pre_qa_session_opts,
                    config=self.config,
                    step_id=step_id,
                    subtask_kind="pre_qa",
                    console=self.console,
                    requires_external_skill_directories=
                    _pre_qa_requires_external_skills,
                )
                _pre_qa_session.on(
                    lambda event, sid=step_id:
                    self._handle_session_event_for_step(event, sid)
                )
                _effective_pre_qa_session = _pre_qa_session
                self._sub_sessions_created += 1
                _qa_workiq_mcp_enabled = False  # デフォルト False: loop で server が見つかれば True に更新
                if _qa_workiq_available:
                    try:
                        _mcp_list = await _pre_qa_session.rpc.mcp.list()
                        for _srv in _mcp_list.servers:
                            if getattr(_srv, "name", "") == WORKIQ_MCP_SERVER_NAME:
                                _qa_workiq_mcp_enabled = True
                                break
                    except Exception:
                        _qa_workiq_mcp_enabled = False
            else:
                _qa_workiq_mcp_enabled = False
                self._log_main_session_reuse(step_id, "Pre-QA")
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="pre-qa",
                    session_id=effective_main_session_id,
                )

            # Phase 0a: 質問票生成
            pre_qa_response = await _effective_pre_qa_session.send_and_wait(
                _effective_pre_qa_prompt, timeout=self.config.timeout_seconds
            )
            pre_qa_raw = _extract_text(pre_qa_response)

            # QAMerger でパース
            # 例外/0件のいずれも単一の skip_reason に集約し、後段で 1 度だけ通知する
            # （Phase 0b/0c で同じ条件を再評価するため、対称性も担保）。
            # 注: 型・属性不整合等のプログラミングエラーをサイレントに握りつぶさず、
            # 観測可能にするため except Exception で捕捉のうえ理由を保持する。
            _parse_succeeded = False
            parsed_pre_qa = QADocument(questions=[])
            _pre_qa_skip_reason: Optional[str] = None
            if not pre_qa_raw:
                _pre_qa_skip_reason = "LLM 応答が空のため事前 QA をスキップします。"
            else:
                try:
                    parsed_pre_qa, _ = _parse_qa_content_with_artifact_fallback(
                        pre_qa_raw,
                        base_dir=".",
                    )
                    _parse_succeeded = bool(parsed_pre_qa.questions)
                    if not _parse_succeeded:
                        _pre_qa_skip_reason = (
                            "事前 QA 質問票から質問を抽出できませんでした"
                            "（Phase 0b/0c をスキップしてメインタスクへ進みます）。"
                        )
                except Exception as _parse_exc:
                    _pre_qa_skip_reason = (
                        f"事前 QA 質問票のパースに失敗しました "
                        f"({type(_parse_exc).__name__}: {_parse_exc})。"
                        " Phase 0b/0c をスキップしてメインタスクへ進みます。"
                    )
            if _pre_qa_skip_reason is not None:
                self.console.warning(
                    f"事前 QA スキップ (step={step_id}): {_pre_qa_skip_reason}"
                )

            # Phase 0b: 回答収集
            user_answers_raw = ""
            skip_input = True
            if _parse_succeeded and parsed_pre_qa.questions:
                user_answers_raw, skip_input = await _collect_qa_answers(
                    self.console, parsed_pre_qa, step_id, self.config
                )

            # Phase 0c: Work IQ（有効かつ質問が存在する場合）
            _workiq_pre_qa_context = ""
            if (
                _qa_workiq_available
                and _qa_workiq_mcp_enabled
                and _parse_succeeded
                and parsed_pre_qa.questions
            ):
                self.console.status("🔍 Work IQ: 事前 QA の質問ごとに M365 調査を開始します...")
                self.console.spinner_start("Work IQ 問い合わせ中...")
                try:
                    _wiq_template = get_workiq_prompt_template(
                        "qa", self.config.workiq_prompt_qa
                    )
                    # Wave 2-6: 重要度フィルタ + 上限適用でクエリ数を削減
                    _filtered_questions = _filter_workiq_questions(
                        parsed_pre_qa.questions,
                        self.config.workiq_max_draft_questions,
                        getattr(self.config, "workiq_priority_filter", True),
                    )
                    _question_items = [(q.no, q.question) for q in _filtered_questions]

                    _per_question_results: Dict[int, str] = {}
                    _mergeable_results: Dict[int, str] = {}
                    _workiq_response_count = 0
                    for _q_no, _q_text in _question_items:
                        _before_count = len(self._workiq_called_tools)
                        _before_any_tools = len(self._toolsearch_called_tools)
                        try:
                            # F6: 検索精度向上のため構造化（QAQuestion の category/priority/default_answer を活用）
                            _q_obj = next((q for q in parsed_pre_qa.questions if q.no == _q_no), None)
                            _meta_lines = [f"- No: Q{_q_no}", f"- 質問: {_q_text}"]
                            if _q_obj and getattr(_q_obj, "category", ""):
                                _meta_lines.append(f"- 分類: {_q_obj.category}")
                            if _q_obj and getattr(_q_obj, "priority", ""):
                                _meta_lines.append(f"- 重要度: {_q_obj.priority}")
                            if _q_obj and getattr(_q_obj, "default_answer", ""):
                                _meta_lines.append(f"- 既定値候補: {_q_obj.default_answer}")
                            _target_content = "\n".join(_meta_lines)
                            _query = _wiq_template.format(target_content=_target_content)
                            self.console.workiq_prompt(_query, label=f"Work IQ プロンプト [Q{_q_no}]")
                            _detail_result = await query_workiq_detailed(
                                _effective_pre_qa_session,
                                _query,
                                timeout=self.config.workiq_per_question_timeout,
                            )
                            if not self.console.show_stream:
                                self.console.workiq_response(
                                    _detail_result.content or "",
                                    label=f"Work IQ 応答 [Q{_q_no}]",
                                )
                            _after_tools = self._workiq_called_tools[_before_count:]
                            if _detail_result.error:
                                _per_question_results[_q_no] = (
                                    f"Work IQ 失敗: {_detail_result.error}"
                                )
                            else:
                                _raw_content = _detail_result.content or ""
                                _workiq_response_count += 1
                                _status = extract_workiq_status(_raw_content)
                                if is_workiq_result_mergeable(
                                    tool_confirmed=bool(_after_tools),
                                    status=_status,
                                ):
                                    _per_question_results[_q_no] = _raw_content
                                    _mergeable_results[_q_no] = _raw_content
                                elif _after_tools:
                                    _status_label = _status or "不明"
                                    _per_question_results[_q_no] = (
                                        f"（QA未統合: status={_status_label}）\n{_raw_content}"
                                    )
                                else:
                                    _per_question_results[_q_no] = (
                                        "（Work IQ: ツール呼び出しなし）\n"
                                        "（QA未統合: tool実行未確認）\n"
                                        f"{_raw_content}"
                                    )
                                    if _status in ("FOUND", "PARTIAL"):
                                        # FR-QA-06: 一次情報ありと申告された応答が
                                        # 統合されないのは検出漏れの疑いがあるため警告する。
                                        self.console.warning(
                                            format_workiq_tool_not_invoked_warning(
                                                f"Q{_q_no}",
                                                observed_tools=self._toolsearch_called_tools[
                                                    _before_any_tools:
                                                ],
                                                status=_status,
                                            )
                                        )
                        except Exception as _wiq_exc:
                            _per_question_results[_q_no] = f"Work IQ エラー: {_wiq_exc}"

                    # 結果をマージ
                    parsed_pre_qa = QAMerger.merge_workiq_results(
                        parsed_pre_qa,
                        _mergeable_results,
                    )
                    _workiq_output_dir = self.config.workiq_draft_output_dir or "qa"
                    _raw_lines: List[str] = []
                    for q in parsed_pre_qa.questions[:self.config.workiq_max_draft_questions]:
                        _ctx = _per_question_results.get(
                            q.no,
                            "（Work IQ 未実行）",
                        )
                        _raw_lines.extend([f"### Q{q.no}: {q.question}", _ctx, ""])
                    save_workiq_result(
                        self.config.run_id, step_id, "pre-qa-draft",
                        "\n".join(_raw_lines).strip(),
                        base_dir=_workiq_output_dir,
                    )
                    _workiq_pre_qa_context = "\n".join(_raw_lines).strip()
                    _merged_count = sum(
                        1 for q in parsed_pre_qa.questions if q.workiq_answer
                    )
                    if _merged_count == 0 and _workiq_response_count > 0:
                        # FR-QA-06: 応答があるのに統合 0 件は異常の可能性が高い。
                        self.console.warning(
                            f"Work IQ: {_workiq_response_count} 件の応答を得ましたが、"
                            "0 件の質問にしか回答案を統合できませんでした。"
                            "検証済み一次情報として扱える結果がありません。"
                        )
                    else:
                        self.console.status(
                            f"✅ Work IQ: {_merged_count} 件の質問に回答案を統合しました"
                        )
                except Exception as draft_exc:
                    self.console.warning(f"Work IQ 事前 QA 連携に失敗しました: {draft_exc}")
                finally:
                    self.console.spinner_stop()

            # Phase 0d: QA 回答マージ + qa/ ファイル保存
            if _parse_succeeded and parsed_pre_qa.questions:
                _pre_qa_file_path = Path(
                    f"qa/{self.config.run_id}-{step_id}-{_PRE_EXECUTION_QA_SUFFIX}"
                )
                _pre_qa_old_content = ""
                if _pre_qa_file_path.exists():
                    try:
                        _pre_qa_old_content = _pre_qa_file_path.read_text(encoding="utf-8")
                    except OSError as _e:
                        self.console.warning(f"事前 QA ファイルの旧コンテンツ読み込みに失敗しました ({_pre_qa_file_path}): {_e}。diff は全行追加として表示されます。")
                merged_content = _persist_answered_qa_and_dispatch(
                    doc=parsed_pre_qa,
                    user_answers_raw=user_answers_raw,
                    use_defaults=skip_input,
                    output_path=_pre_qa_file_path,
                    workflow_id=workflow_id,
                    dispatcher=self._qa_akm_dispatcher,
                )
                self.console.status(
                    f"✅ 事前 QA 質問票を保存・検証しました ({_pre_qa_file_path.as_posix()})"
                )
                self.console.file_diff(
                    step_id,
                    _pre_qa_file_path.as_posix(),
                    _pre_qa_old_content,
                    merged_content,
                )

                # pre_qa_context を組み立てる
                _context_lines = [
                    "## 事前 QA 確認済み情報\n",
                    merged_content,
                ]
                if _workiq_pre_qa_context:
                    _context_lines.append("\n\n## Work IQ による補足情報\n")
                    _context_lines.append(_workiq_pre_qa_context)
                pre_qa_context = "\n".join(_context_lines)

        finally:
            if _pre_qa_session is not None:
                await _pre_qa_session.disconnect()

        self.console.step_phase_end(
            step_id, current_phase, total_phases, "事前 QA",
            elapsed=time.time() - phase0_start,
        )
        return pre_qa_context

    # ------------------------------------------------------------------
    # Phase 1.5: legacy SPLIT_REQUIRED runtime fork
    # ------------------------------------------------------------------

    async def _maybe_run_split_fork(
        self,
        *,
        session: Any,
        step_id: str,
        custom_agent: Optional[str],
    ) -> bool:
        """Legacy opt-in: SPLIT_REQUIRED の subissues.md を検出し、Fleet mode を起動する。

        CLI / GUI 標準経路では `OrchestratorContext.split_fork_enabled=False` のため
        動作しない。Cloud 版の正式な SPLIT_REQUIRED 処理は GitHub Actions の
        `create-subissues-from-pr.yml` / `advance-subissues.yml` による Sub-Issue
        作成・Copilot Cloud Agent アサインで行う。

        本メソッドは legacy / 実験用途として、明示的に
        `split_fork_enabled=True` を渡した場合のみ動作する。単独実行モードでは
        常に True を返して素通しする。

        サブタスクは `depends_on` と出力先を Fleet prompt に明記し、Copilot SDK
        の parent session 内 fleet mode へ委譲する。

        Args:
            session: 親 Step のメイン CopilotSession
            step_id: 親 Step ID
            custom_agent: 親 Step の Custom Agent 名

        Returns:
            True: 全サブタスク成功 / SPLIT 未発生 / Orchestrator 未配下 /
                legacy split-fork 無効のため標準経路へ継続可能
            False: 1 件以上のサブタスクが失敗、または再帰深度上限到達
        """
        ctx = self._orchestrator_ctx
        # 単独実行モード or 機能無効 → 素通し（従来挙動）
        # 観測性: なぜ fork が走らないかを必ず journal/console に残す（無音 return 禁止）
        if ctx is None:
            self.console.event(
                f"  ⏭ [{step_id}] split-fork: 単独実行モード (orchestrator_ctx=None) — fork スキップ"
            )
            return True
        if not ctx.split_fork_enabled:
            # CLI / GUI 標準経路では split_fork_enabled=False が正常値のため、WARN ではなく
            # event（低重大度・GUI「実行中の課題」非対象）で記録する。上の ctx is None 分岐と同じ扱い。
            self.console.event(
                f"  ⏭ [{step_id}] legacy split-fork は無効です "
                f"(split_fork_enabled=False)。subissues.md を GitHub Sub-Issue として"
                f"実行する場合は Cloud Agent Orchestrator の create-subissues 経路を使い、"
                f"CLI / GUI では workflow DAG / fan-out として分割してください。"
            )
            return True

        try:
            from .split_fork import (
                SubIssuesParseError,
                build_subtask_prompt,
                check_subtask_completion,
                compute_waves,
                discover_subissues_md_verbose,
                make_subtask_work_subdir,
                parse_subissues_md,
                resolve_work_root,
            )
        except ImportError:  # pragma: no cover - script execution path
            from split_fork import (  # type: ignore[no-redef]
                SubIssuesParseError,
                build_subtask_prompt,
                check_subtask_completion,
                compute_waves,
                discover_subissues_md_verbose,
                make_subtask_work_subdir,
                parse_subissues_md,
                resolve_work_root,
            )
        try:
            from .fleet_mode import FleetEventCollector, build_split_fleet_prompt, start_fleet
        except ImportError:  # pragma: no cover
            from fleet_mode import FleetEventCollector, build_split_fleet_prompt, start_fleet  # type: ignore[no-redef]

        # custom_agent 欠落は致命ではないが SPLIT_REQUIRED 検出精度を下げるため警告。
        if not custom_agent:
            self.console.event(
                f"  ⚠ [{step_id}] split-fork: custom_agent 未指定 — "
                f"agent-scoped 探索をスキップし fallback-glob に依存します"
            )

        work_root = resolve_work_root()
        # GUI セッション隔離 (Issue-gui-session-workdir-isolation T1):
        # run_id / step_id を伝播してスコープ外の subissues.md 誤検出を防ぐ。
        # self.config.run_id は generate_run_id() で必ず生成されているが、
        # 防御的に空文字を None に正規化する。
        _scope_run_id = self.config.run_id or None
        discover_result = discover_subissues_md_verbose(
            work_root=work_root,
            custom_agent=custom_agent,
            parent_step_id=step_id,
            run_id=_scope_run_id,
            step_id=step_id,
        )
        subissues_path = discover_result.path
        if subissues_path is None:
            # SPLIT 未発生 — ただし「実際に subissues.md が存在するのに発見できない」
            # ケースを後追いできるよう、探索条件を必ず journal/console に残す。
            try:
                _cwd = str(Path.cwd())
            except Exception:
                _cwd = "<unknown>"

            # F2-5: 整合性チェック — plan.md が SPLIT_REQUIRED を宣言しているのに
            # subissues.md が存在しないケースは Agent 仕様違反 (§0)。Step を失敗化する。
            # Issue-gui-session-workdir-isolation Critical#1:
            # 過去 run の plan.md が残存しているとここで誤検出されるため、
            # discover_subissues_md_verbose と同じ run_id スコープでフィルタする。
            # T-C1.2: 同 run 内の別 Agent の plan.md による誤検出を防ぐため、
            # custom_agent 指定時は当該 Agent ディレクトリ配下のみに限定する。
            # work_root 自体が run-id を含む場合、parent.name の run スコープ
            # フィルタは過剰（Issue-0 形式で常に弾かれる）なので skip する。
            try:
                from .split_fork import (
                    is_failed_dir,
                    matches_run_scope as _matches_run_scope,
                    matches_step_scope as _matches_step_scope,
                    work_root_contains_run_id as _work_root_contains_run_id,
                )
            except ImportError:  # pragma: no cover
                from split_fork import (  # type: ignore[no-redef]
                    is_failed_dir,
                    matches_run_scope as _matches_run_scope,
                    matches_step_scope as _matches_step_scope,
                    work_root_contains_run_id as _work_root_contains_run_id,
                )
            _skip_run_scope_filter = _work_root_contains_run_id(
                work_root, _scope_run_id
            )
            inconsistent_plans: List[Path] = []
            try:
                if work_root.is_dir():
                    if custom_agent:
                        plan_globs = [
                            (work_root / custom_agent).glob("Issue-*/plan.md"),
                        ]
                    else:
                        plan_globs = [
                            work_root.glob("Issue-*/plan.md"),
                            work_root.glob("*/Issue-*/plan.md"),
                        ]
                    seen_plans: set = set()
                    for g in plan_globs:
                        for plan_path in g:
                            if plan_path in seen_plans:
                                continue
                            seen_plans.add(plan_path)
                            # `.failed-*` 退避済みディレクトリ配下の plan.md は除外。
                            # discover_subissues_md_verbose と同じルールに揃える。
                            if is_failed_dir(plan_path.parent.name):
                                continue
                            # run_id スコープに合致しない過去 run の plan.md は除外
                            # （work_root が run_id を含む場合は work_root スコープで成立済み）
                            if not _skip_run_scope_filter:
                                if not _matches_run_scope(
                                    plan_path.parent.name, _scope_run_id
                                ):
                                    continue
                            # step_id スコープ: Issue-0 形式では常に True、
                            # Issue-<run_id>-step-<id> 形式では絞り込みが効く
                            if not _matches_step_scope(plan_path.parent.name, step_id):
                                continue
                            try:
                                head = plan_path.read_text(
                                    encoding="utf-8", errors="replace"
                                )[:2048]
                            except OSError:
                                continue
                            if "split_decision: SPLIT_REQUIRED" in head:
                                inconsistent_plans.append(plan_path)
            except Exception:  # pragma: no cover - 防御的: 整合性チェックで例外起こさない
                inconsistent_plans = []

            if inconsistent_plans:
                self.console.error(
                    f"  ✗ [{step_id}] split-fork 整合性違反: "
                    f"plan.md が SPLIT_REQUIRED を宣言しているが subissues.md が未検出 "
                    f"(plans={[str(p) for p in inconsistent_plans]}, "
                    f"work_root={work_root}, custom_agent={custom_agent!r})"
                )
                return False

            self.console.event(
                f"  ⏭ [{step_id}] split-fork: subissues.md 未検出 — fork スキップ "
                f"(work_root={work_root}, custom_agent={custom_agent!r}, "
                f"work_root_exists={work_root.is_dir()}, cwd={_cwd})"
            )
            return True

        # 観測性: どの glob パターンでヒットしたかを残す（fallback-glob 経由なら要注意）
        self.console.event(
            f"  🔍 [{step_id}] split-fork: subissues.md 検出 "
            f"(pattern={discover_result.matched_pattern}, "
            f"candidates={discover_result.candidates_examined}, path={subissues_path})"
        )

        depth = ctx.split_fork_depth
        max_depth = ctx.split_fork_max_depth
        if depth >= max_depth:
            self.console.error(
                f"  ✗ [{step_id}] SPLIT fork 深度上限到達 (depth={depth}, max={max_depth}) "
                f"— subissues.md 発見も実行をスキップして Step failed 化"
            )
            return False

        try:
            subissues = parse_subissues_md(subissues_path)
        except SubIssuesParseError as exc:
            self.console.error(
                f"  ✗ [{step_id}] subissues.md パース失敗: {exc}"
            )
            try:
                failed_dir = subissues_path.parent.with_name(
                    f"{subissues_path.parent.name}.failed-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
                )
                subissues_path.parent.rename(failed_dir)
                self.console.event(
                    f"  ↪ [{step_id}] 失敗した split-fork work dir を退避: {failed_dir}"
                )
            except Exception as rename_exc:
                self.console.warning(
                    f"split-fork parse failure work dir の退避に失敗しました: {rename_exc}"
                )
            return False

        try:
            waves = compute_waves(subissues)
        except SubIssuesParseError as exc:
            self.console.error(
                f"  ✗ [{step_id}] subissues.md depends_on 解決失敗: {exc}"
            )
            return False

        self.console.event(
            f"  🔀 [{step_id}] SPLIT_REQUIRED 検出 ({subissues_path}) "
            f"— {len(subissues)} サブタスクを {len(waves)} wave で並列 fork "
            f"(depth={depth}/{max_depth}, max_parallel={ctx.max_parallel_subtasks})"
        )

        # parent_work_identifier を subissues.md のパスから推定する
        # 例: work/Arch-UI-Detail/Issue-screen-detail/subissues.md
        #     → parent_work_identifier = "screen-detail"
        parent_dir_name = subissues_path.parent.name
        if parent_dir_name.startswith("Issue-"):
            parent_identifier = parent_dir_name[len("Issue-"):]
        else:
            parent_identifier = parent_dir_name

        if len(subissues) == 1:
            sub = subissues[0]
            self.console.event(
                f"  ▶ [{step_id}/sub-{sub.index:03d}] 単一サブタスクのため Fleet mode を使わず parent session で実行"
            )
            work_subdir = make_subtask_work_subdir(
                parent_custom_agent=custom_agent,
                parent_work_identifier=parent_identifier,
                subissue_index=sub.index,
            )
            sub_prompt = build_subtask_prompt(
                subissue=sub,
                parent_step_id=step_id,
                parent_custom_agent=custom_agent,
                work_subdir=work_subdir,
                repo_root=Path.cwd(),
                work_root=work_root,
            )
            try:
                sub_response = await session.send_and_wait(
                    sub_prompt,
                    timeout=self.config.timeout_seconds,
                )
                _ = _extract_text(sub_response)
            except Exception as exc:
                self.console.error(
                    f"  ✗ [{step_id}/sub-{sub.index:03d}] parent session 実行中にエラー: {exc}"
                )
                return False

            ok, reason = check_subtask_completion(work_root, work_subdir)
            if ok:
                self.console.event(f"  ✓ [{step_id}/sub-{sub.index:03d}] 成功")
                return True
            self.console.error(
                f"  ✗ [{step_id}/sub-{sub.index:03d}] 完了判定 FAIL: {reason}"
            )
            return False

        fleet_plan = build_split_fleet_prompt(
            subissues=subissues,
            parent_step_id=step_id,
            parent_custom_agent=custom_agent,
            parent_identifier=parent_identifier,
            repo_root=Path.cwd(),
            work_root=work_root,
        )
        collector = FleetEventCollector()
        unsubscribe = session.on(collector.handle_event)
        try:
            outcome = await start_fleet(session, fleet_plan.prompt)
        finally:
            if callable(unsubscribe):
                try:
                    unsubscribe()
                except Exception:
                    pass

        if not outcome.started:
            self.console.error(
                f"  ✗ [{step_id}] fleet mode 起動失敗: {outcome.reason}"
            )
            return False

        deadline = time.monotonic() + max(1.0, float(self.config.timeout_seconds or 1))
        poll_interval = 0.5
        completion_state: Dict[int, tuple[bool, str]] = {}
        while True:
            completion_state = {
                sub.index: check_subtask_completion(work_root, fleet_plan.work_subdirs[sub.index])
                for sub in subissues
            }
            if all(ok for ok, _reason in completion_state.values()):
                break
            if collector.has_failed:
                break
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(poll_interval)

        all_success = all(ok for ok, _reason in completion_state.values())
        for sub in subissues:
            ok, reason = completion_state[sub.index]
            if ok:
                self.console.event(f"  ✓ [{step_id}/sub-{sub.index:03d}] 成功")
            else:
                self.console.error(
                    f"  ✗ [{step_id}/sub-{sub.index:03d}] 完了判定 FAIL: {reason}"
                )

        if collector.has_failed:
            all_success = False
            self.console.error(f"  ✗ [{step_id}] fleet sub-agent 失敗: {collector.failed}")

        return all_success

    async def run_step(
        self,
        step_id: str,
        title: str,
        prompt: str,
        custom_agent: Optional[str] = None,
        workflow_id: Optional[str] = None,
        fanout_meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """ステップを実行する。

        Args:
            step_id: ステップ識別子（例: "1.1", "2.3", fan-out 子の場合 "1/D01"）
            title: ステップタイトル（表示用）
            prompt: メインタスクのプロンプト文字列
            custom_agent: 使用する Custom Agent 名（省略可）
            workflow_id: ワークフロー識別子（省略可）。成果物形式ルールの切り替えに使用。
            fanout_meta: ADR-0002 fan-out 子ステップのメタ情報。次のキーを含む:
                - fanout_key: fan-out キー（例 "D01"）
                - base_step_id: 親ステップ ID（例 "1"）
                - additional_prompt_template_path: per-key プロンプトテンプレ
                - per_key_mcp_servers: per-key MCP 上書き

        Returns:
            True: 成功, False: 失敗
        """
        start = time.time()
        self._clear_tool_start_state(step_id)
        _recovery_action = getattr(
            self._orchestrator_ctx,
            "recovery_action",
            None,
        )
        _is_reuse_target = (
            _recovery_action == "reuse-session"
            and step_id == self._durable_reuse_target_step_id
        )
        if not self.config.dry_run and not _is_reuse_target:
            # FR-CLI-84 判定 (1): 受領プロンプト単体が既に予算を超えている場合は、
            # Copilot SDK クライアント / セッションの生成と Phase 0 事前 QA より前に停止する。
            _received_plan = plan_phase1_request(
                prompt,
                components=(("step_prompt", prompt),),
            )
            if _received_plan.is_over_budget:
                self.console.error(
                    f"Step.{step_id}: 受領したプロンプトが HVE 内部予算を超えました。"
                    "入力を分割するかファイル化して再実行してください。\n"
                    + _received_plan.describe()
                )
                return False
        # markdown-query Skill 利用ログ (.mdq/usage.jsonl) と Step 紐付けのため
        # 環境変数を伝播する。子プロセス（Copilot SDK 経由含む）が継承し、
        # mdq CLI から mdq.usage_log が読み取る。
        # 注意: 並列 Step 実行時は同一 os.environ を共有するため step_id 属性は
        # ベストエフォート（A2 指標の精度に影響）。workflow_id 単位の集計
        # （Skill 利用統計のメイン用途）は run_workflow 側で設定済みのため不変。
        try:
            os.environ["HVE_STEP_ID"] = str(step_id)
            if custom_agent:
                os.environ["HVE_AGENT_ID"] = str(custom_agent)
            else:
                os.environ.pop("HVE_AGENT_ID", None)
        except Exception:
            pass

        # workflow オブジェクトを 1 回だけ resolve（Phase 4 自己改善ループ内および
        # run_step 終端の output_paths gate で共有する）。StepRunner.__init__ には
        # workflow が注入されていないため registry 経由で都度引く（O(1) dict lookup）。
        try:
            from .workflow_registry import get_workflow as _get_workflow
        except ImportError:
            from workflow_registry import get_workflow as _get_workflow  # type: ignore[no-redef]
        _resolved_workflow = _get_workflow(workflow_id) if workflow_id else None

        # ADR-0002: fan-out per-key プロンプト注入 (T3B) と per-key MCP 上書き (T3A)
        if fanout_meta:
            try:
                prompt = _apply_fanout_prompt_template(
                    prompt=prompt,
                    fanout_meta=fanout_meta,
                    console=self.console,
                )
            except Exception as exc:
                # テンプレ読み込み失敗時は warning のみ出して prompt は変更しない
                try:
                    self.console.warning(
                        f"  ⚠️ Step.{step_id} fan-out テンプレ展開失敗: {exc}"
                    )
                except Exception:
                    pass
            # per-key MCP は session_opts 構築箇所で参照するため self._current_fanout_meta に保持
            self._current_fanout_meta = fanout_meta
        else:
            self._current_fanout_meta = None
        self._workiq_tool_called = False
        self._workiq_called_tools = []
        # Phase 6: サブセッション作成回数カウンターをリセット
        self._sub_sessions_created = 0

        # run_id を1回だけ正規化して書き戻す（Phase 2/4 で別々に生成されるのを防ぐ）。
        # Azure writeを行うStep 1.3では黙示的な文字除去を許さず、envとconfigを
        # 同じ検証済みrun contextへ固定する。
        _is_data_deploy = _is_asdw_data_deploy_step(step_id, custom_agent)
        _raw_run_id = self.config.run_id
        _env_run_id = os.environ.get("HVE_RUN_ID", "")
        if _is_data_deploy and not _raw_run_id and _env_run_id:
            self.config.run_id = _env_run_id
        else:
            self.config.run_id = _safe_run_id(self.config.run_id)
        if _is_data_deploy:
            if not _has_supported_asdw_data_deploy_app_scope(
                str(step_id),
                self._workflow_params
            ):
                self.console.error(
                    f"  ❌ [{step_id}] ASDW Step 1.3 supports exactly one "
                    "selected APP-009 before producer generation"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            try:
                _bootstrap_context = build_asdw_data_deploy_bootstrap_context(
                    workflow_params=self._workflow_params,
                    bootstrap_inputs=_build_asdw_data_deploy_bootstrap_inputs(
                        self._workflow_params
                    ),
                    subscription_id=_resolve_asdw_data_deploy_subscription_id(),
                )
            except AsdwDataDeployContextError as _bootstrap_error:
                self.console.error(f"  ❌ [{step_id}] {_bootstrap_error}")
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if (
                self.config.run_id != _safe_run_id(self.config.run_id)
                or (_raw_run_id and _raw_run_id != self.config.run_id)
                or (_env_run_id and _env_run_id != _env_run_id.strip())
                or (
                    _env_run_id
                    and _env_run_id != self.config.run_id
                )
                or (
                    _env_run_id
                    and _safe_run_id(_env_run_id) != _env_run_id
                )
            ):
                self.console.error(
                    f"  ❌ [{step_id}] invalid or inconsistent HVE run ID; "
                    "Step 1.3 stopped before Azure execution"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if self.config.cli_url:
                self.console.error(
                    f"  ❌ [{step_id}] ASDW Step 1.3 requires a local Copilot "
                    "runtime so HVE can inject one frozen execution environment"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if not _env_run_id:
                os.environ["HVE_RUN_ID"] = self.config.run_id
            _runtime_context_errors = _validate_asdw_data_deploy_runtime_context(
                self.config.run_id,
                Path.cwd(),
            )
            if _runtime_context_errors:
                for _runtime_error in _runtime_context_errors:
                    self.console.error(f"  ❌ [{step_id}] {_runtime_error}")
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
        _work_identifier = _work_identifier_for_step(step_id, fanout_meta)

        # --- dry_run ---
        if self.config.dry_run:
            self.console.step_start(step_id, title, agent=custom_agent)
            self.console.event(f"[DRY-RUN] Step.{step_id} would execute: {title}")
            elapsed = time.time() - start
            self.console.step_end(step_id, "success", elapsed=elapsed)
            return True

        self.console.step_start(step_id, title, agent=custom_agent)
        self._current_step_id = step_id

        pre_verify_contract_errors = []
        # Step.1.2 (DataTestCoding) は verify-data-resources.sh の producer であり、
        # stale な既存ファイルを再生成・修復する責務を持つ。生成前に同ファイルを
        # fail-fast すると producer 自身が起動できないため、pre-run gate は
        # Step.1.3 (DataDeploy) の入力検査に限定する。Step.1.2 の生成結果は
        # セッション完了後の post-run gate で検査する。
        if (
            custom_agent == "Dev-Microservice-Azure-DataDeploy"
            and str(step_id).split("/", 1)[0] == "1.3"
        ):
            pre_verify_contract_errors = self._run_asdw_data_verify_contract_gate(
                step_id, custom_agent, include_registration=False
            )
        if pre_verify_contract_errors:
            for _msg in pre_verify_contract_errors:
                self.console.error(_msg)
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        # FR-APPREQ-03: 生成アプリケーション要求トレーサビリティの preflight。
        # allowlist 対象 Custom Agent だけ、SDK 起動前に対象 APP の要求定義書を
        # 検証し、fail-closed で停止する。対象外 Agent は no-op（既存呼び出し元を
        # 壊さない）。
        _app_requirement_context = ""
        if custom_agent in self._APP_REQUIREMENT_PREFLIGHT_AGENTS and workflow_id:
            try:
                from .application_requirements import (
                    ApplicationRequirementError,
                    build_application_requirement_context,
                )
            except ImportError:
                from application_requirements import (  # type: ignore[no-redef]
                    ApplicationRequirementError,
                    build_application_requirement_context,
                )
            try:
                _app_requirement_context = build_application_requirement_context(
                    workflow_id=workflow_id,
                    workflow_params=self._workflow_params or {},
                    fanout_meta=fanout_meta,
                    repo_root=Path.cwd(),
                )
            except ApplicationRequirementError as _app_requirement_error:
                self.console.error(
                    f"  ❌ [{step_id}] APP要求preflight failed: {_app_requirement_error}"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
        if _app_requirement_context:
            prompt = f"{prompt}\n\n{_app_requirement_context}"

        # Agent Prompt に注入する WORK path を、Agent/SDK 起動前に実在させる。
        # Prompt 任せの mkdir では、最初の read/search が Issue-* 不在で失敗するため、
        # Runner が同じ識別子を使って idempotent に作成する。
        try:
            _step_work_dir_path = _ensure_step_work_dir(
                custom_agent,
                _work_identifier,
            )
            self.console.event(
                f"  📁 [{step_id}] work directory ready: {_step_work_dir_path}"
            )
        except (OSError, ValueError) as _work_dir_exc:
            self.console.error(
                f"  ❌ [{step_id}] step work directory creation failed: "
                f"{_work_dir_exc}"
            )
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        if (
            workflow_id == "asdw-web"
            and _is_asdw_data_deploy_step(step_id, custom_agent)
        ):
            try:
                _generation_result = ensure_asdw_data_producers(Path.cwd())
            except AsdwDataScriptGenerationError:
                self.console.error(
                    f"  ❌ [{step_id}] ASDW data producer generation failed "
                    "before Agent startup"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            _generation_status = getattr(_generation_result, "status", None)
            if type(_generation_status) is not str:
                self.console.error(
                    f"  ❌ [{step_id}] ASDW data producer generation returned "
                    "an invalid status before Agent startup"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if _generation_status == "reused":
                _generation_status_literal = "reused"
            elif _generation_status == "regenerated":
                _generation_status_literal = "regenerated"
            else:
                self.console.error(
                    f"  ❌ [{step_id}] ASDW data producer generation returned "
                    "an invalid status before Agent startup"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            _generation_audit_mode = getattr(
                _generation_result,
                "audit_mode",
                None,
            )
            try:
                _environment_snapshot = (
                    _build_asdw_data_deploy_environment_snapshot(
                        self._workflow_params,
                        os.environ,
                        _generation_audit_mode,
                        _bootstrap_context,
                    )
                )
            except ValueError as _environment_error:
                self.console.error(
                    f"  ❌ [{step_id}] {_environment_error}"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            self._asdw_data_deploy_environment_snapshots[
                str(step_id)
            ] = _environment_snapshot
            self.console.event(
                f"  🧱 [{step_id}] ASDW data producers: "
                f"{_generation_status_literal}"
            )
            _pipeline_work_root = os.environ.get("HVE_WORK_ROOT")
            if type(_pipeline_work_root) is not str or not _pipeline_work_root:
                self.console.error(
                    f"  ❌ [{step_id}] ASDW native data pipeline is missing its HVE work root"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            _pipeline_environment = dict(_environment_snapshot)
            _pipeline_environment["HVE_RUN_ID"] = self.config.run_id
            _pipeline_environment["HVE_WORK_ROOT"] = _pipeline_work_root
            try:
                _pipeline_results = execute_pipeline(
                    repo_root=Path.cwd(),
                    environment=_pipeline_environment,
                )
            except Exception:
                _evidence_errors = _write_asdw_data_deploy_evidence(
                    Path.cwd(),
                    self.config.run_id,
                    (),
                )
                for _evidence_error in _evidence_errors:
                    self.console.error(f"  ❌ [{step_id}] {_evidence_error}")
                self.console.error(
                    f"  ❌ [{step_id}] ASDW native data pipeline failed before SDK startup"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            _evidence_errors = _write_asdw_data_deploy_evidence(
                Path.cwd(),
                self.config.run_id,
                _pipeline_results,
            )
            if _evidence_errors:
                for _evidence_error in _evidence_errors:
                    self.console.error(f"  ❌ [{step_id}] {_evidence_error}")
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if (
                not _pipeline_results
                or any(
                    type(getattr(_result, "exit_code", None)) is not int
                    or _result.exit_code != 0
                    for _result in _pipeline_results
                )
            ):
                self.console.error(
                    f"  ❌ [{step_id}] ASDW native data pipeline returned a failed stage"
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            _native_evidence_gate_errors = (
                self._run_tdd_report_gate(step_id, custom_agent, workflow_id)
                + self._run_deploy_ac_gate(
                    step_id,
                    custom_agent,
                    _resolved_workflow,
                )
            )
            if _native_evidence_gate_errors:
                for _gate_error in _native_evidence_gate_errors:
                    self.console.error(f"  ❌ [{step_id}] {_gate_error}")
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            self.console.event(
                f"  ✓ [{step_id}] ASDW native data pipeline completed"
            )
            elapsed = time.time() - start
            self.console.step_end(step_id, "success", elapsed=elapsed)
            return True

        # --- SDK インポート確認 ---
        try:
            from copilot.session import PermissionHandler  # type: ignore[import]
        except ImportError:
            self.console.error(
                "GitHub Copilot SDK がインストールされていません。\n"
                "  pip install github-copilot-sdk  # または適切なパッケージ名で再試行してください。"
            )
            return False

        session = None
        client = None
        _reuse_session_id: Optional[str] = None
        _recovery_prompt: Optional[str] = None
        _resume_flags = {
            "already_in_use": False,
            "session_was_active": False,
        }

        def _resumed_session_is_active(candidate: Any) -> bool:
            return bool(
                _resume_flags["already_in_use"]
                or _resume_flags["session_was_active"]
                or getattr(candidate, "already_in_use", None) is True
                or getattr(candidate, "session_was_active", None) is True
            )

        try:
            self._durable_lease_token_from_context()
            # FR-CLI-90: inspect the durable target before creating or resuming
            # any SDK session.  A non-Main row therefore fails without an SDK
            # session action, while restart-step never consumes the saved ID.
            _reuse_session_id = self._load_durable_reuse_session_id(step_id)
            # SDK 1.0.0: CopilotClient(connection=RuntimeConnection.*)
            # verbosity >= 3 (verbose) かつデフォルトの log_level ("error") の場合のみ debug に昇格。
            # ユーザーが明示的に log_level を指定している場合はそれを尊重する。
            _effective_log_level = (
                "debug"
                if self.config.verbosity >= 3 and self.config.log_level == "error"
                else self.config.log_level
            )
            try:
                from .copilot_client_factory import create_copilot_client
            except ImportError:  # pragma: no cover
                from copilot_client_factory import create_copilot_client  # type: ignore[no-redef]
            client = create_copilot_client(
                cli_path=self.config.cli_path,
                cli_url=self.config.cli_url,
                github_token=self.config.resolve_token() or None,
                log_level=_effective_log_level,
                cli_args=self.config.cli_args,
                env=(
                    self._asdw_data_deploy_environment_snapshots.get(str(step_id))
                    if _is_data_deploy
                    else None
                ),
            )
            await _start_client_with_retry(client, console=self.console)

            # セッション構築オプション
            session_opts: Dict[str, Any] = {
                "on_permission_request": self._build_step_permission_handler(
                    step_id,
                    custom_agent,
                ),
                "streaming": True,
            }
            _required_skills_for_step = self._get_required_skills_for_step(
                workflow_id,
                step_id,
                _resolved_workflow,
            )
            _is_foundry_required = self._is_foundry_required_step(
                _required_skills_for_step
            )
            _requires_external_skill_directories = (
                self._add_required_external_skill_directories(
                session_opts,
                _required_skills_for_step,
                )
            )
            _optional_skills_for_step = self._get_optional_skills_for_step(
                workflow_id,
                step_id,
            )
            self._add_available_optional_external_skill_directories(
                session_opts,
                _optional_skills_for_step,
            )
            if _is_data_deploy:
                session_opts["enable_config_discovery"] = False
                session_opts["on_event"] = (
                    lambda event, sid=str(step_id):
                    self._handle_session_event_for_step(event, sid)
                )
            # Auto 経路: model="auto" を SDK へ渡し、サーバ側 Auto Model Selection に委譲する。
            _wire_model = to_wire_model(self.config.model)
            if _wire_model:
                session_opts["model"] = _wire_model

            # Step 1.3 は repository-pinned Microsoft Learn MCP だけを使用し、
            # user-supplied server の同名偽装や Azure write tool を接続しない。
            if _is_asdw_data_deploy_step(step_id, custom_agent):
                _main_mcp_servers = _require_trusted_asdw_data_deploy_mcp_servers(
                    Path.cwd()
                )
                if _main_mcp_servers:
                    session_opts["mcp_servers"] = copy.deepcopy(
                        _main_mcp_servers
                    )
            elif _is_foundry_required:
                _foundry_mcp_servers = _require_trusted_foundry_mcp_servers(
                    Path.cwd()
                )
                _main_mcp_servers = {
                    _k: copy.deepcopy(_v)
                    for _k, _v in _filter_mcp_servers_for_session(
                        self.config.mcp_servers,
                        include_workiq=False,
                    ).items()
                }
                _main_mcp_servers.update(copy.deepcopy(_foundry_mcp_servers))
                session_opts["mcp_servers"] = _main_mcp_servers
            elif self.config.mcp_servers:
                _main_mcp_servers = {
                    _k: copy.deepcopy(_v)
                    for _k, _v in _filter_mcp_servers_for_session(
                        self.config.mcp_servers,
                        include_workiq=False,
                    ).items()
                }
                if _main_mcp_servers:
                    session_opts["mcp_servers"] = _main_mcp_servers

            # ADR-0002 (T3A/E-4): fan-out 子ステップでは per-key MCP を上書きマージ
            _fmeta = getattr(self, "_current_fanout_meta", None)
            if _fmeta and not _is_asdw_data_deploy_step(step_id, custom_agent):
                _per_key = _fmeta.get("per_key_mcp_servers") or {}
                _key_servers = _per_key.get(_fmeta.get("fanout_key", "")) or {}
                if _key_servers:
                    _merged = dict(session_opts.get("mcp_servers") or {})
                    for _k, _v in _key_servers.items():
                        _merged[_k] = copy.deepcopy(_v)
                    if _is_foundry_required:
                        _merged.update(
                            copy.deepcopy(
                                _require_trusted_foundry_mcp_servers(Path.cwd())
                            )
                        )
                    session_opts["mcp_servers"] = _merged
                    try:
                        self.console.event(
                            f"  🔌 [{step_id}] per-key MCP {sorted(_key_servers.keys())} を適用"
                        )
                    except Exception:
                        pass

            # G-1: SDK の available_tools / excluded_tools をメインセッションへ伝搬する
            # SDK 0.1.0: create_session(..., available_tools=None, excluded_tools=None, ...)
            if self.config.available_tools:
                session_opts["available_tools"] = list(self.config.available_tools)
            if self.config.excluded_tools:
                session_opts["excluded_tools"] = list(self.config.excluded_tools)

            # Auto Compaction: True 時に SDK 側の infinite_sessions（自動コンテキスト圧縮）を有効化。
            if self.config.auto_compaction:
                session_opts["infinite_sessions"] = {"enabled": True}

            # FR-MODEL-04: SDK のツール定義遅延ロードをメインセッションへ伝搬する。
            if self.config.tool_search:
                session_opts["tool_search"] = {"enabled": True}

                # FR-TS-01 / 06 / 07: tool_search_ranking="hve" のときだけ
                # `tool_search_tool` を HVE 実装へ差し替え、Skill もカタログへ合流させる。
                try:
                    from .toolsearch.session import build_session_toolset
                    from .toolsearch.stats import StatsCollector
                except ImportError:  # pragma: no cover - script execution
                    from toolsearch.session import (  # type: ignore[no-redef]
                        build_session_toolset,
                    )
                    from toolsearch.stats import StatsCollector  # type: ignore[no-redef]
                try:
                    _ts_tools, self._toolsearch_context = build_session_toolset(
                        self.config,
                        repo_root=Path.cwd(),
                        workflow_id=workflow_id,
                        step_id=step_id,
                        # FR-TS-09: 検索イベントを追記専用 JSONL へ流し、
                        # `hve toolsearch dashboard` から観測できるようにする。
                        on_event=StatsCollector(
                            run_id=self._resolve_run_id_safely(),
                            workflow_id=workflow_id,
                            step_id=step_id,
                        ),
                        # G4 未実測: Cloud Session でカスタム tools が有効か確認できていないため
                        # 当面 Cloud 経路では差し替えを行わない（SDK 既定のまま動かす）。
                        enabled=not should_use_cloud_session(self.config, step_id=step_id),
                    )
                except Exception as _ts_exc:  # 検索の組立失敗で Step を落とさない
                    _ts_tools = []
                    self._toolsearch_context = None
                    try:
                        self.console.warning(
                            f"  ⚠️ [{step_id}] Tool Search のランキング差し替えをスキップします: {_ts_exc}"
                        )
                    except Exception:
                        pass
                if _ts_tools:
                    session_opts["tools"] = list(session_opts.get("tools") or []) + _ts_tools
                    try:
                        self.console.event(
                            f"  🔎 [{step_id}] Tool Search ランキングを HVE 実装へ差し替え "
                            f"(tools={len(_ts_tools)})"
                        )
                    except Exception:
                        pass

            # Custom Agent 廃止後 (Q1=C / Q3=a):
            # `custom_agents` / `agent` キーは SDK に渡さない。
            # 代わりに `.github/prompts/<custom_agent>.prompt.md` を読み込み、
            # メインタスク Prompt の先頭に前置する。
            try:
                from .prompt_loader import load_prompt, substitute_work_placeholders
            except ImportError:  # pragma: no cover
                from prompt_loader import (  # type: ignore[no-redef]
                    load_prompt,
                    substitute_work_placeholders,
                )

            _agent_prompt_body = load_prompt(custom_agent) if custom_agent else ""
            # WORK プレースホルダ (<run-id> / <識別子>) を実値へ置換し、Agent が
            # work/run/<run-id>/ の外に作業ディレクトリを作るのを防ぐ。run_id は
            # resolve_work_root() の <run-id> と一致させるため resolve_run_id() を使う。
            if _agent_prompt_body:
                try:
                    from .split_fork import resolve_run_id
                except ImportError:  # pragma: no cover
                    from split_fork import resolve_run_id  # type: ignore[no-redef]
                _agent_prompt_body = substitute_work_placeholders(
                    _agent_prompt_body,
                    run_id=resolve_run_id(),
                    identifier=_work_identifier,
                )

            # Skill 利用ガード（Prompt 末尾に付加）
            _skill_guard_text = ""
            if custom_agent:
                _guard = [
                    "## Skill 利用ガード",
                    "- `skill(...)` ツールには Custom Agent 名ではなく、skill 名のみを指定すること。",
                ]
                if _required_skills_for_step:
                    _guard.append(
                        "- このステップで必須の skill 名: "
                        + ", ".join(f"`{s}`" for s in _required_skills_for_step)
                    )
                if _optional_skills_for_step:
                    _guard.append(
                        "- 条件付き候補 skill 名（対象Azureサービスまたは操作と一致する場合だけ使用し、一致しない候補は読まない）: "
                        + ", ".join(
                            f"`{s}`" for s in _optional_skills_for_step
                        )
                    )
                _skill_guard_text = "\n".join(_guard)

            _prompt_prefix_parts: List[str] = []
            if _agent_prompt_body:
                _prompt_prefix_parts.append(_agent_prompt_body.strip())
            if _skill_guard_text:
                _prompt_prefix_parts.append(_skill_guard_text)
            _tool_search_policy_text = _tool_search_policy_prefix(
                workflow_id,
                step_id,
                self.config.enable_tool_search,
            )
            if _tool_search_policy_text:
                _prompt_prefix_parts.append(_tool_search_policy_text)
            _agentic_retrieval_policy_text = _agentic_retrieval_policy_prefix(
                workflow_id,
                step_id,
                self.config.enable_agentic_retrieval,
            )
            if _agentic_retrieval_policy_text:
                _prompt_prefix_parts.append(_agentic_retrieval_policy_text)
            # FR-CLI-85: additional_prompt と markdown-query 強制ブロックは
            # orchestrator が Step プロンプト末尾へ連結済みのため再度前置しない。
            _agent_prefix = "\n\n".join(_prompt_prefix_parts).strip()
            _execution_mode_suffix = _build_execution_mode_constraint_suffix(
                self._orchestrator_ctx
            )
            _tdd_suffix = self._build_tdd_report_instruction_suffix(
                step_id=step_id,
                custom_agent=custom_agent,
                workflow_id=workflow_id,
            )
            _review_suffix = _build_review_ownership_suffix(
                self.config.auto_contents_review
            )
            if _reuse_session_id is not None:
                _recovery_prompt = load_prompt_file(
                    _RUNNER_RESUME_RECOVERY_PROMPT_PATH
                )
                if not _recovery_prompt.strip():
                    raise RuntimeError(
                        "durable Main recovery prompt is empty"
                    )
                _pre_qa_free_prompt = _recovery_prompt
                _pre_qa_free_components = (
                    ("recovery_prompt", _recovery_prompt),
                )
            else:
                _pre_qa_free_prompt, _pre_qa_free_components = _compose_phase1_prompt(
                    agent_prefix=_agent_prefix,
                    step_prompt=prompt,
                    pre_qa_context="",
                    execution_mode_suffix=_execution_mode_suffix,
                    tdd_suffix=_tdd_suffix,
                    review_suffix=_review_suffix,
                )
            _pre_qa_free_plan = plan_phase1_request(
                _pre_qa_free_prompt,
                components=_pre_qa_free_components,
            )
            if _pre_qa_free_plan.is_over_budget:
                self.console.error(
                    f"Step.{step_id}: Phase 0 前の確定プロンプトが HVE 内部予算を超えました。"
                    "入力を分割するかファイル化して再実行してください。\n"
                    + _pre_qa_free_plan.describe()
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False

            if _reuse_session_id is not None:
                _main_session_id = _reuse_session_id
                _resume_event_received = asyncio.Event()
                _resume_deadline = (
                    asyncio.get_running_loop().time()
                    + _RUNNER_RESUME_EVENT_TIMEOUT_SECONDS
                )

                def _handle_resume_event(event: Any) -> None:
                    event_type = getattr(
                        getattr(event, "type", None),
                        "value",
                        getattr(event, "type", None),
                    )
                    if event_type == "session.resume":
                        data = getattr(event, "data", None)
                        # SDK 1.0.8 SessionResumeData exposes snake_case fields.
                        if getattr(data, "already_in_use", None) is True:
                            _resume_flags["already_in_use"] = True
                        if getattr(data, "session_was_active", None) is True:
                            _resume_flags["session_was_active"] = True
                        _resume_event_received.set()
                    self._handle_session_event_for_step(event, step_id)

                # T22 shared seam: re-commit the persisted identity before the
                # resume RPC.  The callback is registered by resume_session
                # before that RPC, so a synchronous session.resume event is not
                # lost.  No create-session fallback exists in this branch.
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="main",
                    session_id=_main_session_id,
                )
                _resume_local_options = {
                    key: session_opts[key]
                    for key in ("tools",)
                    if session_opts.get(key)
                }
                try:
                    session = await asyncio.wait_for(
                        client.resume_session(
                            _main_session_id,
                            on_event=_handle_resume_event,
                            on_permission_request=session_opts[
                                "on_permission_request"
                            ],
                            continue_pending_work=False,
                            **_resume_local_options,
                        ),
                        timeout=_remaining_deadline_seconds(_resume_deadline),
                    )
                    await asyncio.wait_for(
                        _resume_event_received.wait(),
                        timeout=_remaining_deadline_seconds(_resume_deadline),
                    )
                except TimeoutError as exc:
                    resume_error = RuntimeError(
                        "durable SDK session resume did not complete within deadline"
                    )
                    if session is not None:
                        try:
                            await _disconnect_session_bounded(session)
                        except Exception as cleanup_exc:
                            resume_error.add_note(
                                "resume timeout cleanup also failed: "
                                f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                            )
                        finally:
                            session = None
                    raise resume_error from exc
                if _resumed_session_is_active(session):
                    resume_error = RuntimeError(
                        "durable SDK session is active or already in use"
                    )
                    try:
                        await _disconnect_session_bounded(session)
                    except Exception as cleanup_exc:
                        resume_error.add_note(
                            "active-session cleanup also failed: "
                            f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                        )
                    finally:
                        session = None
                    raise resume_error
            else:
                # restart-step intentionally follows this path: the saved
                # session ID is never copied, and the current attempt's run ID
                # produces a fresh deterministic session ID.
                if not session_opts.get("session_id"):
                    session_opts["session_id"] = self._make_step_session_id(step_id)
                _main_session_id = session_opts["session_id"]
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="main",
                    session_id=_main_session_id,
                )

                session = await self._create_main_session(
                    client=client,
                    session_opts=session_opts,
                    step_id=step_id,
                    workflow_id=workflow_id,
                    requires_external_skill_directories=
                    _requires_external_skill_directories,
                )

                if _is_foundry_required:
                    await self._verify_foundry_required_session_mcp_servers(session)
                session.on(
                    lambda event, sid=step_id:
                    self._handle_session_event_for_step(event, sid)
                )

            # ストリーム表示の開始マーカー
            if self.console.show_stream:
                self.console.stream_start(step_id)

            # フェーズ総数を動的算出
            _run_pre_qa = _should_run_pre_execution_qa(
                auto_qa=self.config.auto_qa,
                workflow_id=workflow_id,
                custom_agent=custom_agent,
                prompt=prompt,
            ) and _reuse_session_id is None

            # 事後 QA (post-QA モード) は廃止されました。
            # 旧 post-QA 制御は削除済み。
            total_phases = 1  # Phase 1: メインタスク
            if _run_pre_qa:
                total_phases += 1
            if self.config.auto_contents_review:
                total_phases += 1
            _si_scope = self.config.self_improve_scope
            _step_si_allowed = _si_scope in ("", "step")
            if self.config.auto_self_improve and not self.config.self_improve_skip and _step_si_allowed:
                total_phases += 1
            current_phase = 0

            # final_message に渡す最終応答テキスト（各 Phase 完了後に非空なら上書き）
            final_response_text: str = ""

            # Phase 0: 事前 QA（_run_pre_qa=True の場合）
            pre_qa_context = ""
            if _run_pre_qa:
                current_phase += 1
                pre_qa_context = await self._run_pre_execution_qa(
                    session=session,
                    client=client,
                    step_id=step_id,
                    main_session_id=_main_session_id,
                    original_prompt=prompt,
                    custom_agent=custom_agent,
                    workflow_id=workflow_id,
                    current_phase=current_phase,
                    total_phases=total_phases,
                )

            # Phase 1: メインタスク
            current_phase += 1
            phase1_start = time.time()
            self.console.step_phase_start(step_id, current_phase, total_phases, "メインタスク")

            if _reuse_session_id is not None:
                assert _recovery_prompt is not None
                _injected_prompt = _recovery_prompt
                _final_components = (("recovery_prompt", _recovery_prompt),)
            else:
                _injected_prompt, _final_components = _compose_phase1_prompt(
                    agent_prefix=_agent_prefix,
                    step_prompt=prompt,
                    pre_qa_context=pre_qa_context,
                    execution_mode_suffix=_execution_mode_suffix,
                    tdd_suffix=_tdd_suffix,
                    review_suffix=_review_suffix,
                )
            # FR-CLI-84 判定 (2): 連結後の最終プロンプトを送信直前に再度照合する。
            # 予算超過時は Phase 1 のモデル呼び出しを 1 回も行わずに失敗させる。
            _final_plan = plan_phase1_request(
                _injected_prompt,
                components=_final_components,
            )
            if _final_plan.is_over_budget:
                self.console.error(
                    f"Step.{step_id}: Phase 1 のプロンプトが HVE 内部予算を超えました。"
                    "入力を分割するかファイル化して再実行してください。\n"
                    + _final_plan.describe()
                )
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False
            if (
                _reuse_session_id is not None
                and _resumed_session_is_active(session)
            ):
                try:
                    await session.disconnect()
                finally:
                    session = None
                raise RuntimeError(
                    "durable SDK session is active or already in use"
                )
            self._commit_durable_checkpoint(
                step_id=step_id,
                phase="main",
                session_id=_main_session_id,
            )
            main_response = await self._send_and_wait_with_model_call_failure_guard(
                session,
                _injected_prompt,
                timeout=self.config.timeout_seconds,
                step_id=step_id,
            )
            main_output = _extract_text(main_response)
            if main_output and main_output.strip():
                final_response_text = main_output
            self.console.step_phase_end(
                step_id, current_phase, total_phases, "メインタスク",
                elapsed=time.time() - phase1_start,
            )

            preflight_failure_errors = (
                self._run_asdw_data_deploy_preflight_failure_gate(
                    step_id,
                    custom_agent,
                )
            )
            if preflight_failure_errors:
                for _msg in preflight_failure_errors:
                    self.console.error(_msg)
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False

            # Step.1.3 の registration script はこのメインタスク自身が producer
            # である。後続の split-fork / review が早期終了しても未検証の登録
            # スクリプトを通過させないよう、生成直後に registration 込みで検査する。
            # session_start を渡し、当 step で再生成された producer script のみ検査
            # する（stale な commit 済みスクリプトで真因をマスクしない。memo §20）。
            post_main_contract_errors = (
                self._run_asdw_data_producer_contract_gate(
                    step_id,
                    custom_agent,
                    session_start=start,
                )
                + self._run_asdw_data_verify_contract_gate(
                    step_id,
                    custom_agent,
                    include_registration=False,
                )
            )
            if post_main_contract_errors:
                for _msg in post_main_contract_errors:
                    self.console.error(_msg)
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False

            # Phase 1.5 (legacy SPLIT-fork): Agent が SPLIT_REQUIRED 判定で
            # subissues.md を出力した場合の runtime fork は CLI / GUI 標準経路では
            # 無効。Cloud 版は GitHub Actions 側で Sub-Issue を生成する。
            # 明示 opt-in (split_fork_enabled=True) 時のみ legacy 経路として動く。
            # T-C1.2: stats_event は always=True で stdout 確定出力されるため
            # verbosity=0 でも観測可能 (Console.event は verbosity=0 で抑制)。
            self.console.event(f"  🔀 [{step_id}] split-fork 判定開始")
            self.console.stats_event(
                "split_fork_phase", step_id=step_id, phase="enter"
            )
            if (
                self._orchestrator_ctx is not None
                and self._orchestrator_ctx.split_fork_enabled
            ):
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="split-fork",
                    session_id=_main_session_id,
                )
            _split_fork_ok = await self._maybe_run_split_fork(
                session=session,
                step_id=step_id,
                custom_agent=custom_agent,
            )
            self.console.event(
                f"  🔀 [{step_id}] split-fork 判定完了 (ok={_split_fork_ok})"
            )
            self.console.stats_event(
                "split_fork_phase", step_id=step_id, phase="exit",
                ok=_split_fork_ok,
            )
            if not _split_fork_ok:
                # サブタスクのいずれかが失敗 → Step failed として早期 return
                self.console.step_io_summary(step_id)
                elapsed = time.time() - start
                self.console.step_end(step_id, "failed", elapsed=elapsed)
                return False

            # Phase 2 (post-QA / 事後 QA) は廃止されました。
            # 旧 post-QA 制御とCLIオプションは削除済み。

            # Phase 3: 敵対的レビュー（auto_contents_review=True の場合）
            if self.config.auto_contents_review:
                current_phase += 1
                phase3_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "敵対的レビュー")
                _review_model = self.config.get_review_model()
                _use_review_sub_session = self._should_use_review_sub_session(_review_model)
                _review_session = None
                try:
                    _effective_review_session = session
                    _effective_review_prompt = REVIEW_PROMPT
                    if _use_review_sub_session:
                        self._log_sub_session_reason(
                            step_id, "Review",
                            qa_model=_review_model,
                        )
                        _review_session_opts = self._build_sub_session_opts(
                            _review_model,
                            step_id=step_id,
                            suffix="review",
                            custom_agent=custom_agent,
                        )
                        self._commit_durable_checkpoint(
                            step_id=step_id,
                            phase="review",
                            session_id=_review_session_opts["session_id"],
                        )
                        _review_required_skills = self._get_required_skills_for_step(
                            workflow_id,
                            step_id,
                            _resolved_workflow,
                        )
                        _review_requires_external_skills = (
                            self._add_required_external_skill_directories(
                                _review_session_opts,
                                _review_required_skills,
                            )
                        )
                        _review_session = await _create_session_with_auto_reasoning_fallback(
                            client,
                            _review_session_opts,
                            config=self.config,
                            step_id=step_id,
                            subtask_kind="review",
                            console=self.console,
                            requires_external_skill_directories=
                            _review_requires_external_skills,
                        )
                        _review_session.on(
                            lambda event, sid=step_id:
                            self._handle_session_event_for_step(event, sid)
                        )
                        self._sub_sessions_created += 1
                        _max_context_chars = self._get_context_injection_max_chars()
                        _review_context = _truncate_context_with_warn(
                            main_output or "", _max_context_chars,
                            label="Phase 3 Review main_output", console=self.console,
                        )
                        _effective_review_prompt = (
                            "以下は同一ステップのメインタスク出力です。"
                            "この内容を前提としてレビューしてください。\n\n"
                            f"=== メインタスク出力（最大{_max_context_chars:,}文字） ===\n"
                            f"{_review_context}\n"
                            "=== メインタスク出力ここまで ===\n\n"
                            f"{REVIEW_PROMPT}"
                        )
                        _effective_review_session = _review_session
                    else:
                        self._log_main_session_reuse(step_id, "Review")
                        self._commit_durable_checkpoint(
                            step_id=step_id,
                            phase="review",
                            session_id=_main_session_id,
                        )

                    # 1回目: 敵対的レビュー実行
                    review_response = await _effective_review_session.send_and_wait(
                        _effective_review_prompt, timeout=self.config.timeout_seconds
                    )
                    review_content = _extract_text(review_response)
                    self.console.review_result(review_content)

                    # 初回 PASS 判定
                    if not _is_review_fail(review_content):
                        self.console.status(
                            "✅ 敵対的レビュー PASS（初回） — 再レビュー不要"
                        )
                        self.console.step_phase_end(
                            step_id, current_phase, total_phases, "敵対的レビュー",
                            elapsed=time.time() - phase3_start, result="PASS",
                        )
                    else:
                        # 再レビューサイクル（最大2回）
                        review_passed = False
                        for cycle in range(1, 3):  # cycle 1, 2
                            self.console.status(
                                f"❌ 敵対的レビュー FAIL — 再レビューサイクル {cycle}/2 を実行"
                            )
                            # FAIL 時: メイン成果物改善（設定有効時）
                            if self.config.apply_review_improvements_to_main:
                                _phase3_result = await self._apply_main_artifact_improvements(
                                    session=session,
                                    step_id=step_id,
                                    title=title,
                                    workflow_id=workflow_id,
                                    custom_agent=custom_agent,
                                    original_prompt=(
                                        _recovery_prompt
                                        if _reuse_session_id is not None
                                        else prompt
                                    ),
                                    main_output=main_output or "",
                                    source_phase="Phase 3 Adversarial Review",
                                    improvement_context=review_content,
                                    timeout=self.config.timeout_seconds,
                                )
                                if _phase3_result and _phase3_result.strip():
                                    final_response_text = _phase3_result
                                self._check_diff_after_improvement(
                                    step_id, "Phase 3 Adversarial Review"
                                )
                            recheck_prompt = ADVERSARIAL_RECHECK_PROMPT.format(cycle=cycle)
                            recheck_response = await _effective_review_session.send_and_wait(
                                recheck_prompt, timeout=self.config.timeout_seconds
                            )
                            review_content = _extract_text(recheck_response)
                            self.console.review_result(review_content)

                            if not _is_review_fail(review_content):
                                self.console.status(
                                    f"✅ 敵対的レビュー PASS（再レビューサイクル {cycle}/2 後）"
                                )
                                self.console.step_phase_end(
                                    step_id, current_phase, total_phases, "敵対的レビュー",
                                    elapsed=time.time() - phase3_start, result="PASS",
                                )
                                review_passed = True
                                break

                        if not review_passed:
                            self.console.step_phase_end(
                                step_id, current_phase, total_phases, "敵対的レビュー",
                                elapsed=time.time() - phase3_start, result="FAIL",
                            )
                            self.console.status(
                                "⚠️ 最大再レビューサイクル到達 — Critical が残存しています"
                            )
                            # Critical が残存している場合はステップ失敗として扱う
                            raise RuntimeError(
                                "Critical issues remain after maximum adversarial review cycles."
                            )
                finally:
                    if _review_session is not None:
                        await _review_session.disconnect()

            # Phase 4: 自己改善ループ（auto_self_improve=True かつ skip でない場合）
            # scope が "" または "step" の場合のみ実行。"workflow" / "disabled" の場合はスキップ。
            _si_scope = self.config.self_improve_scope
            _step_si_allowed = _si_scope in ("", "step")
            if self.config.auto_self_improve and not self.config.self_improve_skip and not _step_si_allowed:
                self.console.event(
                    f"  ⏭️ [{step_id}] Phase 4 自己改善ループをスキップ "
                    f"(self_improve_scope={_si_scope!r} — step-level は実行しない)"
                )
            if self.config.auto_self_improve and not self.config.self_improve_skip and _step_si_allowed:
                current_phase += 1
                phase4_start = time.time()
                self.console.step_phase_start(step_id, current_phase, total_phases, "自己改善ループ")
                self._commit_durable_checkpoint(
                    step_id=step_id,
                    phase="self-improve",
                    session_id=_main_session_id,
                )

                # _work_dir は ステップ ID で分離されたパスを使用する（並列安全性）
                # `work/run/<run-id>/self-improve/step-<step_id>/`
                from .split_fork import resolve_work_root as _rwr
                _work_dir = _rwr() / "self-improve" / f"step-{step_id}"
                _max_iter = self.config.self_improve_max_iterations

                for _iteration in range(1, _max_iter + 1):
                    _iter_start = time.time()

                    # Phase 4a: コードベーススキャン（subprocess）
                    self.console.event(
                        f"  🔍 [{step_id}] 自己改善 {_iteration}/{_max_iter}: コードベーススキャン中..."
                    )
                    _step_outputs = _resolve_step_output_paths(_resolved_workflow, step_id)
                    _workflow_default = _SI_SCOPE_DEFAULTS.get(_resolved_workflow.id, "") if _resolved_workflow is not None else ""
                    _scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
                        step_output_paths=_step_outputs,
                        workflow_default=_workflow_default,
                    )
                    _before_score = _scan["quality_score"]
                    self.console.event(
                        f"  📊 [{step_id}] quality_score: {_before_score} "
                        f"(lint={_scan['summary']['lint_errors']}, "
                        f"test_fail={_scan['summary']['test_failures']}, "
                        f"coverage={_scan['summary']['coverage_pct']:.1f}%)"
                    )

                    # スコアが十分高く問題なし → 改善不要で終了
                    if _before_score >= DEFAULT_QUALITY_THRESHOLD and not _scan["summary"]["test_failures"]:
                        self.console.status(
                            f"✅ 自己改善ループ: quality_score={_before_score} ≥ {DEFAULT_QUALITY_THRESHOLD} — 改善不要"
                        )
                        break

                    # Phase 4b: LLM 統合評価 + 改善計画生成
                    _previous_learning = get_learning_summary(_work_dir, _iteration - 1)
                    _scan_prompt = SELF_IMPROVE_SCAN_PROMPT.format(
                        target_scope=self.config.self_improve_target_scope or "全体",
                        scan_output=_scan["raw_output"][:_MAX_SCAN_OUTPUT_LENGTH],
                    )
                    _scan_response = await session.send_and_wait(
                        _scan_prompt, timeout=self.config.timeout_seconds
                    )
                    _scan_content = _extract_text(_scan_response)

                    _plan_prompt = SELF_IMPROVE_PLAN_PROMPT.format(
                        iteration=_iteration,
                        scan_result_json=_scan_content[:_MAX_PLAN_SCAN_LENGTH],
                        previous_learning=_previous_learning[:_MAX_LEARNING_SUMMARY_LENGTH] if _previous_learning else "(初回)",
                    )
                    _plan_response = await session.send_and_wait(
                        _plan_prompt, timeout=self.config.timeout_seconds
                    )
                    _plan_content = _extract_text(_plan_response)

                    if "IMPROVEMENT_NOT_NEEDED" in _plan_content:
                        self.console.status(
                            "✅ 自己改善ループ: 改善不要と判定されました"
                        )
                        break

                    # Phase 4c: セッション内で改善実行
                    # 計画内容（_plan_content）を実行指示としてセッションに送信する
                    self.console.event(
                        f"  🔧 [{step_id}] 自己改善 {_iteration}/{_max_iter}: 改善実行中..."
                    )
                    if self.config.apply_self_improve_to_main:
                        _phase4_result = await self._apply_main_artifact_improvements(
                            session=session,
                            step_id=step_id,
                            title=title,
                            workflow_id=workflow_id,
                            custom_agent=custom_agent,
                            original_prompt=(
                                _recovery_prompt
                                if _reuse_session_id is not None
                                else prompt
                            ),
                            main_output=main_output or "",
                            source_phase=f"Phase 4 Self-Improve iteration {_iteration}",
                            improvement_context=_plan_content[:_MAX_PLAN_SCAN_LENGTH],
                            timeout=self.config.timeout_seconds,
                        )
                        if _phase4_result and _phase4_result.strip():
                            final_response_text = _phase4_result
                        self._check_diff_after_improvement(
                            step_id, f"Phase 4 Self-Improve iteration {_iteration}"
                        )
                    else:
                        _exec_prompt = (
                            f"以下の改善計画を実行してください。\n\n{_plan_content[:_MAX_PLAN_SCAN_LENGTH]}"
                        )
                        await session.send_and_wait(
                            _exec_prompt, timeout=self.config.timeout_seconds
                        )

                    # Phase 4d: 改善後検証（Verification Loop §10.1 準拠）
                    _after_scan = scan_codebase(
                        target_scope=self.config.self_improve_target_scope,
                        step_output_paths=_step_outputs,
                        workflow_default=_workflow_default,
                    )
                    _verify_prompt = SELF_IMPROVE_VERIFY_PROMPT.format(
                        before_score=_before_score,
                        after_scan_output=_after_scan["raw_output"][:_MAX_SCAN_OUTPUT_LENGTH],
                    )
                    _verify_response = await session.send_and_wait(
                        _verify_prompt, timeout=self.config.timeout_seconds
                    )
                    _verify_content = _extract_text(_verify_response)

                    # 検証結果は scan 実測値だけから決定的に導出する（FR-CLI-63）。
                    # LLM 応答は notes の説明としてのみ使用し、判定へ反映しない。
                    _json_parse_error: Optional[str] = None
                    _json_match = _extract_json_block(_verify_content)
                    if _json_match:
                        try:
                            json.loads(_json_match)
                        except (json.JSONDecodeError, ValueError, TypeError) as _exc:
                            # G-7: JSON パース失敗を可観測化（黙示フォールバックの抑止）
                            _json_parse_error = f"{type(_exc).__name__}: {_exc}"
                            self.console.warning(
                                f"  ⚠️ [{step_id}] Phase 4 verify: LLM JSON のパースに失敗しました "
                                f"({_json_parse_error}) — 判定は scan 実測値のみを使用します"
                            )
                    else:
                        _json_parse_error = "no_json_block_found"
                        self.console.warning(
                            f"  ⚠️ [{step_id}] Phase 4 verify: LLM 応答に JSON ブロックが見つかりません — "
                            "判定は scan 実測値のみを使用します"
                        )

                    _verification: VerificationResult = _build_phase4_verification(
                        _after_scan, _before_score, _verify_content, _json_parse_error,
                    )
                    _after_score = _verification["after_quality_score"]
                    _degraded = _verification["degraded"]

                    # Phase 4e: 学習ログ記録
                    _record: ImprovementRecord = {
                        "iteration": _iteration,
                        "before_score": _before_score,
                        "after_score": _after_score,
                        "degraded": _degraded,
                        "plan_summary": _plan_content[:_MAX_PLAN_SCAN_LENGTH],
                        "verification": _verification,
                        "elapsed_seconds": time.time() - _iter_start,
                    }
                    record_learning(_work_dir, _iteration, _record)

                    self.console.event(
                        f"  📈 [{step_id}] 自己改善 {_iteration}/{_max_iter}: "
                        f"score {_before_score} → {_after_score} "
                        f"({'⚠️ デグレード' if _degraded else '✅ 改善'})"
                    )

                    # Phase 4f: デグレード検知 → 即時停止
                    if _degraded:
                        self.console.status(
                            f"⚠️ 自己改善ループ: デグレード検知 — イテレーション {_iteration} で停止"
                        )
                        break

                self.console.step_phase_end(
                    step_id, current_phase, total_phases, "自己改善ループ",
                    elapsed=time.time() - phase4_start,
                )

        except DurableStateError:
            raise
        except Exception as exc:
            self.console.error(
                f"Step.{step_id} 実行中にエラーが発生しました: {format_exception_for_log(exc)}"
            )
            self.console.step_io_summary(step_id)
            elapsed = time.time() - start
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False
        finally:
            self._clear_tool_start_state(step_id)
            self._record_toolsearch_usage(step_id)
            try:
                try:
                    if session is not None:
                        await _disconnect_session_bounded(session)
                except Exception as cleanup_exc:
                    self.console.warning(f"[cleanup] session.disconnect() failed: {cleanup_exc}")
                finally:
                    if client is not None:
                        await _stop_client_bounded(client, self.console)
            finally:
                self._clear_tool_start_state(step_id)

        elapsed = time.time() - start
        self.console.step_io_summary(step_id)

        # FR-APPREQ-04: ARD Step 4.2 完了時の APP 要求 coverage 検証（catalog 全 APP
        # の文書実在・schema・orphan）。ARD Step 4.2 以外は no-op。
        _app_requirement_coverage_errors: List[str] = []
        if (
            workflow_id
            and str(workflow_id).strip().lower() == "ard"
            and str(step_id).split("/", 1)[0] == "4.2"
        ):
            try:
                from .application_requirements import validate_requirement_coverage
            except ImportError:
                from application_requirements import (  # type: ignore[no-redef]
                    validate_requirement_coverage,
                )
            try:
                _app_requirement_coverage = validate_requirement_coverage(Path.cwd())
            except Exception as _app_requirement_coverage_exc:
                _app_requirement_coverage_errors = [str(_app_requirement_coverage_exc)]
            else:
                _app_requirement_coverage_errors = list(_app_requirement_coverage.errors)
        if _app_requirement_coverage_errors:
            for _msg in _app_requirement_coverage_errors:
                self.console.error(f"  ❌ [{step_id}] APP要求coverage failed: {_msg}")
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        # FR-APPREQ-04: allowlist 対象 Custom Agent の完了報告に記録された
        # trace block（<!-- app-requirements:start/end -->）を検証する。
        # 完了報告が無い（未対応 Agent・単体テスト等）場合は no-op とする。
        _app_requirement_trace_errors: List[str] = []
        if custom_agent in self._APP_REQUIREMENT_PREFLIGHT_AGENTS and workflow_id:
            try:
                from .application_requirements import (
                    ApplicationRequirementError,
                    resolve_application_requirement_app_ids,
                    validate_application_requirement_trace_block,
                )
            except ImportError:
                from application_requirements import (  # type: ignore[no-redef]
                    ApplicationRequirementError,
                    resolve_application_requirement_app_ids,
                    validate_application_requirement_trace_block,
                )
            try:
                _app_requirement_report_path = (
                    _step_work_dir(custom_agent, _work_identifier) / "completion-report.md"
                )
                _app_requirement_report_text = _app_requirement_report_path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except (OSError, ValueError):
                _app_requirement_report_text = None
            if _app_requirement_report_text is not None:
                try:
                    _app_requirement_expected_ids = resolve_application_requirement_app_ids(
                        workflow_id=workflow_id,
                        workflow_params=self._workflow_params or {},
                        fanout_meta=fanout_meta,
                        repo_root=Path.cwd(),
                    )
                except ApplicationRequirementError as _app_requirement_resolve_error:
                    _app_requirement_trace_errors = [str(_app_requirement_resolve_error)]
                else:
                    try:
                        _app_requirement_trace_errors = validate_application_requirement_trace_block(
                            _app_requirement_report_text,
                            repo_root=Path.cwd(),
                            expected_app_ids=_app_requirement_expected_ids,
                        )
                    except Exception as _app_requirement_trace_exc:
                        _app_requirement_trace_errors = [str(_app_requirement_trace_exc)]
        if _app_requirement_trace_errors:
            for _msg in _app_requirement_trace_errors:
                self.console.error(f"  ❌ [{step_id}] APP要求trace block failed: {_msg}")
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        self.console.final_message(step_id, final_response_text or main_output or "")

        verify_contract_errors = (
            self._run_asdw_data_producer_contract_gate(
                step_id, custom_agent, session_start=start
            )
            + self._run_asdw_data_verify_contract_gate(
                step_id,
                custom_agent,
                include_registration=False,
            )
        )
        if verify_contract_errors:
            for _msg in verify_contract_errors:
                self.console.error(_msg)
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        capability_gate_errors = self._run_ai_agent_capability_gate(
            step_id,
            custom_agent,
            workflow_id,
        )
        if capability_gate_errors:
            for _msg in capability_gate_errors:
                self.console.error(_msg)
            try:
                import json as _json_capability_gate
                import sys as _sys_capability_gate
                _capability_payload = _json_capability_gate.dumps(
                    {
                        "kind": "ai_agent_capability_gate_failed",
                        "step_id": step_id,
                        "agent": custom_agent or "",
                        "errors": capability_gate_errors,
                    },
                    ensure_ascii=True,
                )
                print(
                    f"[hve:fatal] {_capability_payload}",
                    file=_sys_capability_gate.stdout,
                    flush=True,
                )
            except Exception:
                pass
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        tdd_report_errors = self._run_tdd_report_gate(step_id, custom_agent, workflow_id)
        if tdd_report_errors:
            for _msg in tdd_report_errors:
                self.console.error(_msg)
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        ui_red_contract_errors = self._run_asdw_ui_red_unresolved_contract_gate(step_id, custom_agent, workflow_id)
        if ui_red_contract_errors:
            for _msg in ui_red_contract_errors:
                self.console.error(_msg)
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        conformance_errors = self._run_requirements_conformance_gate(
            step_id, custom_agent, _resolved_workflow
        )
        if conformance_errors:
            for _msg in conformance_errors:
                self.console.error(_msg)
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        agent_report_errors = self._run_agent_capability_report_gate(
            step_id, custom_agent, _resolved_workflow
        )
        if agent_report_errors:
            for _msg in agent_report_errors:
                self.console.error(_msg)
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        # Deploy 系 Agent: ac-verification.md の実在系 AC が GREEN かを検証し、
        # 未達なら Step を fail に降格する (T5)。
        # 既存 stop_on_fatal 経路を再利用するため、未達時は [hve:fatal] マーカーも出力。
        # 並列実行中の同 wave Step は中断しない（既存挙動踏襲）。
        gate_errors = self._run_deploy_ac_gate(step_id, custom_agent, _resolved_workflow)
        if gate_errors:
            for _msg in gate_errors:
                self.console.error(_msg)
            try:
                import json as _json_gate
                import sys as _sys_gate
                _gate_payload = _json_gate.dumps(
                    {
                        "kind": "deploy_ac_gate_failed",
                        "step_id": step_id,
                        "agent": custom_agent or "",
                        "errors": gate_errors,
                    },
                    ensure_ascii=True,
                )
                print(f"[hve:fatal] {_gate_payload}", file=_sys_gate.stdout, flush=True)
            except Exception:
                pass
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        # CLI/GUI Orchestrator 配下 (fleet mode 以外) では、宣言された output_paths が
        # 1 件でも未生成の場合に Step を fail 化する (FR-WF-OUT-01)。Deploy 系では実在系
        # AC の失敗を先に報告し、service catalog 等の output 不足で根本原因を覆い隠さない。
        # NOTE: workflow オブジェクトは StepRunner.__init__ に注入されていないため、
        # workflow_id から workflow_registry.get_workflow() で都度解決する（O(1) lookup）。
        _missing_outputs = _check_output_paths_gate(
            self._orchestrator_ctx, _resolved_workflow, step_id, Path.cwd()
        )
        if _missing_outputs:
            self.console.error(
                f"  ❌ [{step_id}] output-missing: 宣言された主成果物が未生成です — "
                f"{', '.join(_missing_outputs)}"
            )
            self.console.step_end(step_id, "failed", elapsed=elapsed)
            return False

        self.console.step_end(step_id, "success", elapsed=elapsed)
        return True

    # 要件適合実測レポートの成果物ゲート（FR-WF-CONF-02 / 03 / 05）。
    _REQUIREMENTS_CONFORMANCE_GATE_TARGETS = {
        ("asdw-web", "5.3"): "docs/azure/requirements-conformance-report.md",
        ("adfdv", "4.3"): "docs/dataflow/requirements-conformance-report.md",
        ("aagd", "5"): "docs/agent/requirements-conformance-report.md",
        ("aar", "7"): "docs/azure/agentic-retrieval/requirements-conformance-report.md",
    }

    def _run_requirements_conformance_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> List[str]:
        if custom_agent != "QA-RequirementsConformanceEval" or not workflow_id:
            return []
        workflow = str(workflow_id).strip().casefold()
        base_step_id = str(step_id).split("/", 1)[0]
        report = self._REQUIREMENTS_CONFORMANCE_GATE_TARGETS.get(
            (workflow, base_step_id)
        )
        if report is None:
            return []

        try:
            from hve.artifact_validation import (
                validate_requirements_conformance_report,
            )
        except Exception as exc:
            return [
                f"[{custom_agent}] requirements conformance gate import failed: "
                f"{type(exc).__name__}: {exc}"
            ]

        try:
            validation_errors = validate_requirements_conformance_report(
                Path.cwd() / report,
                workflow_id=workflow,
                step_id=base_step_id,
            )
        except Exception as exc:
            return [
                f"[{custom_agent}] requirements conformance validator raised: "
                f"{type(exc).__name__}: {exc}"
            ]
        return [f"[{custom_agent}] {error}" for error in validation_errors]

    # AAGD Step 6 / 7 の成果物ゲート（AG-CAP-10 / AG-CAP-09）。
    # Agent 名で引くため、他 workflow へ同名 Agent を足しても誤発火しない。
    _AGENT_CAPABILITY_REPORT_GATE_TARGETS = {
        ("QA-AgentRouteRightsizingEval", "aagd", "6"): "docs/agent/route-rightsizing-report.md",
        ("Dev-Agent-M365Publish", "aagd", "7"): "docs/agent/m365-publish-report.md",
    }

    def _run_agent_capability_report_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> List[str]:
        if not custom_agent or not workflow_id:
            return []
        workflow = str(workflow_id).strip().casefold()
        base_step_id = str(step_id).split("/", 1)[0]
        report = self._AGENT_CAPABILITY_REPORT_GATE_TARGETS.get(
            (custom_agent, workflow, base_step_id)
        )
        if report is None:
            return []

        try:
            from hve.artifact_validation import (
                validate_m365_publish_report,
                validate_route_rightsizing_report,
            )
        except Exception as exc:
            return [
                f"[{custom_agent}] agent capability report gate import failed: "
                f"{type(exc).__name__}: {exc}"
            ]
        validator = (
            validate_route_rightsizing_report
            if custom_agent == "QA-AgentRouteRightsizingEval"
            else validate_m365_publish_report
        )

        try:
            validation_errors = validator(
                Path.cwd() / report,
                workflow_id=workflow,
                step_id=base_step_id,
            )
        except Exception as exc:
            return [
                f"[{custom_agent}] agent capability report validator raised: "
                f"{type(exc).__name__}: {exc}"
            ]
        return [f"[{custom_agent}] {error}" for error in validation_errors]

    def _run_asdw_data_verify_contract_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        *,
        include_registration: bool = True,
    ) -> List[str]:
        """ASDW-WEB data verify スクリプト契約を検査する。

        Step.1.2 (DataTestCoding) の生成直後だけでなく、Step.1.3
        (DataDeploy) が既存成果物を入力として再利用する場合も同じ契約を検査する。
        これにより stale な `verify-data-resources.sh` を Azure 操作前に fail-fast する。
        """
        base_step_id = str(step_id).split("/", 1)[0]
        is_data_testcoding = (
            custom_agent == "Dev-Microservice-Azure-DataTestCoding"
            and base_step_id == "1.2"
        )
        is_data_deploy = (
            custom_agent == "Dev-Microservice-Azure-DataDeploy"
            and base_step_id == "1.3"
        )
        if not (is_data_testcoding or is_data_deploy):
            return []
        try:
            from hve.artifact_validation import (
                validate_asdw_data_registration_script,
                validate_asdw_data_verify_script,
            )
        except Exception as _import_exc:
            return [
                f"[{custom_agent}] "
                f"verify-data-resources.sh contract gate import failed: {_import_exc}"
            ]

        worktree = Path.cwd()
        sample_data_path = worktree / "src" / "data" / "sample-data.json"
        design_doc_path = worktree / "docs" / "azure" / "azure-services-data.md"
        # Step.1.2 では sample-data は任意。Step.1.3 は期待件数の正本として
        # 必須なので、一般入力gateのwarning設定に依存せずRunner自身がfail-closedにする。
        if is_data_deploy and not sample_data_path.is_file():
            return [
                f"[{custom_agent}] required input src/data/sample-data.json not found: "
                f"{sample_data_path}"
            ]
        errors = validate_asdw_data_verify_script(
            worktree / "src" / "infra" / "azure" / "verify-data-resources.sh",
            design_doc_path=design_doc_path,
            private_capability_required=True,
            sample_data_path=(
                sample_data_path
                if is_data_deploy or sample_data_path.is_file()
                else None
            ),
        )
        noun = "generated" if is_data_testcoding else "input"
        gate_errors = [
            f"[{custom_agent}] {noun} verify-data-resources.sh contract failed: {err}"
            for err in errors
        ]
        if is_data_deploy and include_registration:
            registration_errors = validate_asdw_data_registration_script(
                worktree / "src" / "data" / "azure" / "data-registration-script.sh",
                design_doc_path=design_doc_path,
            )
            gate_errors.extend(
                f"[{custom_agent}] generated data-registration-script.sh contract failed: {err}"
                for err in registration_errors
            )
        return gate_errors

    def _run_asdw_data_deploy_preflight_failure_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
    ) -> List[str]:
        """Return a recorded Step 1.3 pre-flight failure before stale artifact gates."""
        if not _is_asdw_data_deploy_step(step_id, custom_agent):
            return []
        try:
            identifier = _work_identifier_for_step(
                step_id,
                self._current_fanout_meta,
            )
            report_path = (
                _step_work_dir(custom_agent, identifier) / "completion-report.md"
            )
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            return []
        match = re.search(
            r"<!--\s*fatal:\s*pre-flight-failed:?\s*(?P<reason>.*?)\s*-->",
            report_text,
        )
        if match is None:
            return []
        reason = match.group("reason").strip()
        if reason == "{理由}":
            return []
        return [
            f"[{custom_agent}] pre-flight failed: "
            f"{reason or '(理由未記載)'} (from completion-report.md)"
        ]

    def _run_asdw_data_create_contract_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
    ) -> List[str]:
        """Validate the Step 1.3 prep/create pair before launcher execution."""
        if not _is_asdw_data_deploy_step(step_id, custom_agent):
            return []
        try:
            from hve.artifact_validation import validate_asdw_data_create_scripts
        except Exception as exc:
            return [
                f"[{custom_agent}] prep/create contract gate import failed: "
                f"{type(exc).__name__}"
            ]
        root = Path.cwd()
        errors = validate_asdw_data_create_scripts(
            root / _ASDW_DATA_PREP_SCRIPT,
            root / _ASDW_DATA_CREATE_SCRIPT,
            design_doc_path=root / "docs" / "azure" / "azure-services-data.md",
            sample_data_path=root / "src" / "data" / "sample-data.json",
        )
        return [
            f"[{custom_agent}] generated prep/create contract failed: {error}"
            for error in errors
        ]

    def _asdw_producer_script_is_session_output(
        self,
        rel_path: str,
        session_start: Optional[float],
    ) -> bool:
        """Return True when a Step 1.3 producer script must be validated.

        ``session_start is None`` denotes the pre-execution security gate: the
        launcher is about to run against Azure, so the script is validated
        unconditionally. When a step start time is supplied (post-main / final
        quality gates), only scripts written during this step (mtime >= start)
        are validated. A stale committed script that the agent never
        regenerated this session is skipped so that its errors do not mask the
        true failure cause (memo §20).
        """
        if session_start is None:
            return True
        try:
            mtime = (Path.cwd() / rel_path).stat().st_mtime
        except OSError:
            return False
        return mtime >= session_start

    def _run_asdw_data_producer_contract_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        *,
        session_start: Optional[float] = None,
    ) -> List[str]:
        """Validate all three Step 1.3-owned producer scripts before Azure.

        At the pre-execution permission gate (``session_start is None``) every
        producer script is validated. At the post-main / final quality gates a
        ``session_start`` is supplied and only scripts regenerated during this
        step are validated. The prep/create validator requires both scripts,
        so it runs in freshness mode only when both are regenerated; a stale
        sibling must not mask the current session's output (memo §20).
        """
        if not _is_asdw_data_deploy_step(step_id, custom_agent):
            return []
        gate_errors: List[str] = []
        prep_is_session_output = self._asdw_producer_script_is_session_output(
            _ASDW_DATA_PREP_SCRIPT,
            session_start,
        )
        create_is_session_output = self._asdw_producer_script_is_session_output(
            _ASDW_DATA_CREATE_SCRIPT,
            session_start,
        )
        if prep_is_session_output and create_is_session_output:
            gate_errors = self._run_asdw_data_create_contract_gate(
                step_id,
                custom_agent,
            )
        if not self._asdw_producer_script_is_session_output(
            _ASDW_DATA_REGISTRATION_SCRIPT, session_start
        ):
            return gate_errors
        try:
            from hve.artifact_validation import validate_asdw_data_registration_script
        except Exception as exc:
            return gate_errors + [
                f"[{custom_agent}] registration contract gate import failed: "
                f"{type(exc).__name__}"
            ]
        root = Path.cwd()
        registration_errors = validate_asdw_data_registration_script(
            root / _ASDW_DATA_REGISTRATION_SCRIPT,
            design_doc_path=root / "docs" / "azure" / "azure-services-data.md",
        )
        return gate_errors + [
            f"[{custom_agent}] generated data-registration-script.sh contract failed: "
            f"{error}"
            for error in registration_errors
        ]

    # ------------------------------------------------------------------
    # AAG/AAGD AI Agent capability artifact gate
    # ------------------------------------------------------------------
    _AI_AGENT_CAPABILITY_GATE_TARGETS: Dict[Tuple[str, str, str], str] = {
        ("aag", "3", "Arch-AIAgentDesign-Step3"): "design",
        ("aagd", "2.3", "Dev-Microservice-Azure-AgentCoding"): "implementation",
        ("aagd", "3", "Dev-Microservice-Azure-AgentDeploy"): "deploy",
        ("aagd", "4", "QA-ToolSearchEval"): "eval",
    }

    def _run_ai_agent_capability_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> List[str]:
        """AAG Step 3/AAGD Step 2.3のfan-out成果物だけを検証する。"""
        if not custom_agent or not workflow_id:
            return []
        workflow = str(workflow_id).strip().casefold()
        step_parts = str(step_id).split("/", 1)
        base_step_id = step_parts[0]
        mode = self._AI_AGENT_CAPABILITY_GATE_TARGETS.get(
            (workflow, base_step_id, custom_agent)
        )
        if mode is None:
            return []

        target_key = step_parts[1].strip() if len(step_parts) > 1 else ""
        if not target_key:
            return [
                f"[{custom_agent}] AI Agent capability gate requires a fan-out target key"
            ]
        if len(target_key) > 128 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*",
            target_key,
        ):
            return [
                f"[{custom_agent}] unsafe AI Agent fan-out target key: {target_key!r}"
            ]

        try:
            from hve.artifact_validation import (
                validate_ai_agent_capability_artifacts,
                validate_ai_agent_deploy_artifacts,
                validate_tool_search_eval_report,
            )
        except Exception as exc:
            return [
                f"[{custom_agent}] AI Agent capability gate import failed: "
                f"{type(exc).__name__}: {exc}"
            ]

        repo_root = Path.cwd()
        design_path = (
            repo_root
            / "docs"
            / "agent"
            / f"agent-detail-{target_key}.md"
        )
        try:
            if mode == "design":
                validation_errors = validate_ai_agent_capability_artifacts(
                    workflow,
                    design_path,
                    tool_search_policy=self.config.enable_tool_search,
                    agentic_retrieval_policy=self.config.enable_agentic_retrieval,
                )
            elif mode == "deploy":
                validation_errors = validate_ai_agent_deploy_artifacts(
                    design_path,
                    repo_root / "src" / "infra" / "azure",
                    self.config.enable_tool_search,
                    self.config.enable_agentic_retrieval,
                )
            elif mode == "eval":
                validation_errors = validate_tool_search_eval_report(
                    design_path,
                    repo_root
                    / "docs"
                    / "agent"
                    / "tool-search-eval"
                    / f"{target_key}-eval-report.md",
                    self.config.enable_tool_search,
                )
            else:
                validation_errors = validate_ai_agent_capability_artifacts(
                    workflow,
                    design_path,
                    agent_dir=repo_root / "src" / "agent" / target_key,
                    test_spec_path=(
                        repo_root
                        / "docs"
                        / "test-specs"
                        / f"{target_key}-test-spec.md"
                    ),
                    tool_search_policy=self.config.enable_tool_search,
                    agentic_retrieval_policy=self.config.enable_agentic_retrieval,
                )
        except Exception as exc:
            return [
                f"[{custom_agent}] AI Agent capability validator raised: "
                f"{type(exc).__name__}: {exc}"
            ]
        return [
            f"[{custom_agent}] AI Agent capability contract failed: {error}"
            for error in validation_errors
        ]

    # ------------------------------------------------------------------
    # TDD RED/GREEN test report gate
    # ------------------------------------------------------------------
    _TDD_REPORT_PHASES: Dict[Tuple[str, str, str], str] = {
        ("asdw-web", "1.2", "Dev-Microservice-Azure-DataTestCoding"): "RED",
        ("asdw-web", "1.3", "Dev-Microservice-Azure-DataDeploy"): "GREEN",
        ("asdw-web", "2.3", "Dev-Microservice-Azure-AddServiceTestCoding"): "RED",
        ("asdw-web", "2.4", "Dev-Microservice-Azure-AddServiceTesting"): "GREEN",
        ("asdw-web", "3.2", "Dev-Microservice-Azure-ServiceTestCoding"): "RED",
        ("asdw-web", "3.3", "Dev-Microservice-Azure-ServiceCoding-AzureFunctions"): "GREEN",
        ("asdw-web", "4.1", "Dev-Microservice-Azure-UITestCoding"): "RED",
        ("asdw-web", "4.2", "Dev-Microservice-Azure-UICoding"): "GREEN",
        ("adfdv", "2.1", "Dev-Dataflow-TestCoding"): "RED",
        ("adfdv", "2.2", "Dev-Dataflow-ServiceCoding"): "GREEN",
        ("aagd", "2.2", "Dev-Microservice-Azure-AgentTestCoding"): "RED",
        ("aagd", "2.3", "Dev-Microservice-Azure-AgentCoding"): "GREEN",
    }

    # ------------------------------------------------------------------
    # FR-APPREQ-03: 生成アプリケーション要求トレーサビリティ preflight/completion gate
    # ------------------------------------------------------------------
    # Prompt が docs/architectural-requirements-app-NNN.md を必須参照へ更新済みの
    # Custom Agent だけを対象とする allowlist（_TDD_REPORT_PHASES と同じ、既存呼び
    # 出し元（47 箇所超）を壊さない段階的展開パターン）。対象外の custom_agent は
    # preflight/trace gate とも no-op のままとする。
    _APP_REQUIREMENT_PREFLIGHT_AGENTS = frozenset(
        {
            "Arch-ArchitectureCandidateAnalyzer",
        }
    )

    @staticmethod
    def _safe_tdd_step_dir(step_id: str) -> str:
        base_step_id = str(step_id).split("/", 1)[0]
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", base_step_id).strip("-")
        return f"step-{safe or 'default'}"

    @staticmethod
    def _read_asdw_stable_repo_file(
        path: Path,
        repo_root: Path,
        artifact_name: str,
    ) -> Tuple[Optional[str], List[str]]:
        """Read one stable regular UTF-8 file under the repository root."""
        resolved_repo_root = repo_root.resolve()
        try:
            path.relative_to(resolved_repo_root)
        except ValueError:
            return None, [f"{artifact_name} path must stay under the repository root."]

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            descriptor = os.open(path, flags)
        except (FileNotFoundError, NotADirectoryError):
            return None, [f"{artifact_name} not found: {path.as_posix()}"]
        except OSError as exc:
            return None, [f"{artifact_name} is unreadable: {exc}"]
        try:
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISREG(opened_stat.st_mode):
                return None, [
                    f"{artifact_name} is not a regular file: {path.as_posix()}"
                ]

            path_stat = os.lstat(path)
            reparse_flag = int(
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
            )
            path_attributes = int(
                getattr(path_stat, "st_file_attributes", 0)
            )
            if (
                stat.S_ISLNK(path_stat.st_mode)
                or path_attributes & reparse_flag
                or not stat.S_ISREG(path_stat.st_mode)
            ):
                return None, [
                    f"{artifact_name} must not be a symlink or reparse point."
                ]
            if not os.path.samestat(opened_stat, path_stat):
                return None, [f"{artifact_name} changed while it was opened."]

            resolved_path = path.resolve(strict=True)
            try:
                resolved_path.relative_to(resolved_repo_root)
            except ValueError:
                return None, [
                    f"{artifact_name} resolves outside the repository root."
                ]
            lexical_path = Path(os.path.abspath(path))
            if os.path.normcase(os.path.normpath(resolved_path)) != os.path.normcase(
                os.path.normpath(lexical_path)
            ):
                return None, [
                    f"{artifact_name} path must not contain a symlink, junction, "
                    "or reparse point."
                ]
            resolved_stat = os.stat(resolved_path, follow_symlinks=False)
            if not os.path.samestat(opened_stat, resolved_stat):
                return None, [f"{artifact_name} changed during path validation."]

            with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as stream:
                text = stream.read()
            final_stat = os.fstat(descriptor)
            if (
                not os.path.samestat(opened_stat, final_stat)
                or opened_stat.st_size != final_stat.st_size
                or opened_stat.st_mtime_ns != final_stat.st_mtime_ns
            ):
                return None, [f"{artifact_name} changed while it was read."]
            final_path_stat = os.lstat(path)
            if (
                stat.S_ISLNK(final_path_stat.st_mode)
                or int(getattr(final_path_stat, "st_file_attributes", 0))
                & reparse_flag
                or not os.path.samestat(opened_stat, final_path_stat)
            ):
                return None, [f"{artifact_name} path changed while it was read."]
            final_resolved_path = path.resolve(strict=True)
            try:
                final_resolved_path.relative_to(resolved_repo_root)
            except ValueError:
                return None, [
                    f"{artifact_name} resolves outside the repository root after "
                    "it was read."
                ]
            if os.path.normcase(
                os.path.normpath(final_resolved_path)
            ) != os.path.normcase(os.path.normpath(lexical_path)):
                return None, [
                    f"{artifact_name} path gained a symlink, junction, or reparse "
                    "point while it was read."
                ]
            final_resolved_stat = os.stat(
                final_resolved_path,
                follow_symlinks=False,
            )
            if not os.path.samestat(opened_stat, final_resolved_stat):
                return None, [
                    f"{artifact_name} changed during final path validation."
                ]
            return text, []
        except (OSError, UnicodeError) as exc:
            return None, [f"{artifact_name} is unreadable: {exc}"]
        finally:
            os.close(descriptor)

    @staticmethod
    def _validate_asdw_data_static_verification_log(
        report_path: Path,
        repo_root: Path,
        report_text: str,
    ) -> List[str]:
        """Require the Step 1.2 report's exact, local, non-empty raw log."""
        try:
            from hve.artifact_validation import _visible_asdw_design_lines
        except Exception as exc:
            return [f"ASDW data RED report visibility parser import failed: {exc}"]

        visible_lines, visibility_error = _visible_asdw_design_lines(report_text)
        if visibility_error:
            return [
                "ASDW data RED report visibility boundary is invalid: "
                f"{visibility_error}"
            ]
        container_prefix = re.compile(
            r"^(?: {0,3}>[ \t]*| {0,3}(?:[-+*]|\d{1,9}[.)])[ \t]+)"
        )
        container_hidden_opener = re.compile(
            r"^(?:(?:`{3,}|~{3,})|<(?:/?[A-Za-z][A-Za-z0-9-]*"
            r"(?=[\s/>]|$)|![A-Z]|!\[CDATA\[|!--|\?))",
            re.IGNORECASE,
        )
        for line in visible_lines:
            remainder = line
            has_container = False
            while prefix_match := container_prefix.match(remainder):
                has_container = True
                remainder = remainder[prefix_match.end() :]
            if has_container and container_hidden_opener.match(remainder):
                return [
                    "ASDW data RED report must not place fenced code or raw HTML "
                    "inside a list/blockquote container."
                ]
        raw_log_values = [
            match.group("value")
            for line in visible_lines
            if (
                match := re.fullmatch(
                    r" {0,3}-[ \t]+Raw-Log-Path[ \t]*:[ \t]*"
                    r"(?P<value>[^\r\n]*?)[ \t]*",
                    line,
                )
            )
        ]
        if len(raw_log_values) != 1:
            return [
                "ASDW data RED report requires exactly one visible, single-line "
                "Raw-Log-Path label."
            ]

        expected_path = report_path.with_name("static-verification.log")
        try:
            expected_label = expected_path.relative_to(repo_root).as_posix()
        except ValueError:
            return ["ASDW data RED report path must stay under the repository root."]
        raw_log_value = raw_log_values[0]
        if (
            len(raw_log_value) >= 2
            and raw_log_value.startswith("`")
            and raw_log_value.endswith("`")
            and not raw_log_value.startswith("``")
            and not raw_log_value.endswith("``")
        ):
            raw_log_value = raw_log_value[1:-1]
        expected_windows_label = expected_label.replace("/", "\\")
        if raw_log_value not in (expected_label, expected_windows_label):
            return [
                "ASDW data RED report Raw-Log-Path must exactly match either "
                f"`{expected_label}` or `{expected_windows_label}`."
            ]

        raw_log_text, raw_log_errors = StepRunner._read_asdw_stable_repo_file(
            expected_path,
            repo_root,
            "ASDW data static-verification.log",
        )
        if raw_log_errors:
            return raw_log_errors
        if raw_log_text is None or not raw_log_text.strip():
            return ["ASDW data static-verification.log must not be empty."]
        return []

    def _run_asdw_step12_evidence_check(
        self,
        report_path: Path,
        repo_root: Path,
        report_text: str,
    ) -> List[str]:
        """Validate the Step 1.2 report against an HVE-owned machine log.

        HVE runs the fixed local verifier to produce the authoritative
        three-state machine log, writes it beside the report for audit, and
        checks that the Agent-visible report labels match it. This keeps a
        static contract PASS from being presented as a live RED execution and a
        nonzero focused pytest from being folded into a single PASS.
        """
        try:
            from hve.asdw_step12_verification import (
                run_asdw_step12_local_verification,
            )
            from hve.artifact_validation import (
                validate_asdw_step12_evidence_report,
            )
        except Exception as exc:
            return [f"ASDW Step 1.2 evidence check import failed: {exc}"]

        try:
            machine_log = run_asdw_step12_local_verification(repo_root)
        except Exception as exc:
            return [
                "ASDW Step 1.2 local verification failed: "
                f"{type(exc).__name__}"
            ]

        machine_log_path = report_path.with_name("machine-verification.log")
        try:
            machine_log_path.write_text(
                machine_log, encoding="utf-8", newline="\n"
            )
        except OSError:
            pass

        return validate_asdw_step12_evidence_report(report_text, machine_log)

    def _build_tdd_report_instruction_suffix(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> str:
        """Return exact TDD report path instructions for fan-out TDD steps."""
        if not custom_agent or not workflow_id:
            return ""
        workflow_key = str(workflow_id).strip().lower()
        step_parts = str(step_id).split("/", 1)
        base_step_id = step_parts[0]
        target_key = step_parts[1].strip() if len(step_parts) > 1 else ""
        if not target_key:
            return ""
        phase = self._TDD_REPORT_PHASES.get((workflow_key, base_step_id, custom_agent))
        if not phase:
            return ""

        try:
            from hve.split_fork import resolve_run_id
        except ImportError:  # pragma: no cover - script execution path
            from split_fork import resolve_run_id  # type: ignore[no-redef]

        run_id = resolve_run_id()
        step_dir = self._safe_tdd_step_dir(base_step_id)
        report_path = (
            Path("tests")
            / "run"
            / run_id
            / workflow_key
            / step_dir
            / target_key
            / phase
            / "tdd-test-report.md"
        ).as_posix()
        return _RUNNER_TDD_REPORT_INSTRUCTION_SUFFIX_TEMPLATE.format(
            report_path=report_path,
            workflow_key=workflow_key,
            custom_agent=custom_agent,
            base_step_id=base_step_id,
            target_key=target_key,
            phase=phase,
        )

    def _run_tdd_report_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> List[str]:
        """Validate run-scoped TDD RED/GREEN report existence and schema.

        This gate is intentionally allowlist-based and checks only the minimal
        Markdown contract. ASDW data Step 1.2 additionally requires the exact
        non-empty static-verification.log promised by its generation contract;
        the gate does not parse runner-specific log contents.
        """
        if not custom_agent or not workflow_id:
            return []
        workflow_key = str(workflow_id).strip().lower()
        step_parts = str(step_id).split("/", 1)
        base_step_id = step_parts[0]
        target_key = step_parts[1].strip() if len(step_parts) > 1 else ""
        phase = self._TDD_REPORT_PHASES.get((workflow_key, base_step_id, custom_agent))
        if not phase:
            return []

        try:
            from hve.split_fork import resolve_run_id
            from hve.artifact_validation import (
                _extract_markdown_label,
                validate_tdd_test_report,
            )
        except Exception as exc:
            return [f"[{custom_agent}] TDD report gate import failed: {exc}"]

        run_id = resolve_run_id()
        step_dir = self._safe_tdd_step_dir(base_step_id)
        repo_root = Path.cwd().resolve()
        report_root = repo_root / "tests" / "run" / run_id / workflow_key / step_dir
        if target_key:
            candidates = [report_root / target_key / phase / "tdd-test-report.md"]
        else:
            candidates = sorted(report_root.glob(f"*/{phase}/tdd-test-report.md"))
        if not candidates:
            action_hint = (
                "Agent が必須成果物を生成しないままターンを終えた可能性が高い"
                "（ツール不安定による無出力・捏造・非対話での確認質問終了・"
                "推論ループへの脱線が無いか console-log を確認）。"
            )
            return [
                f"[{custom_agent}] tdd-test-report.md not found "
                f"(searched {report_root.as_posix()}/*/{phase}/tdd-test-report.md)"
                f"; {action_hint}"
            ]

        errors: List[str] = []
        require_asdw_data_raw_log = (
            workflow_key == "asdw-web"
            and base_step_id == "1.2"
            and custom_agent == "Dev-Microservice-Azure-DataTestCoding"
        )
        for report_path in candidates:
            stable_report_text: Optional[str] = None
            stable_report_errors: List[str] = []
            if require_asdw_data_raw_log:
                stable_report_text, stable_report_errors = (
                    self._read_asdw_stable_repo_file(
                        report_path,
                        repo_root,
                        "ASDW data RED report",
                    )
                )
            if stable_report_errors:
                report_errors = stable_report_errors
            else:
                report_errors = validate_tdd_test_report(
                    report_path,
                    expected_phase=phase,
                    expected_workflow=workflow_key,
                    expected_target_key=target_key or None,
                    report_text=stable_report_text,
                )
            if require_asdw_data_raw_log and stable_report_text is not None:
                report_errors.extend(
                    self._validate_asdw_data_static_verification_log(
                        report_path,
                        repo_root,
                        stable_report_text,
                    )
                )
                report_errors.extend(
                    self._run_asdw_step12_evidence_check(
                        report_path,
                        repo_root,
                        stable_report_text,
                    )
                )
            for err in report_errors:
                errors.append(f"[{custom_agent}] {report_path.as_posix()}: {err}")
            # GREEN の BLOCKED（テスト側/共有設定ブロッカーの正直な記録）は失敗にしないが、
            # 見落とし防止のため警告として可視化する。
            if phase == "GREEN" and not report_errors:
                try:
                    _text = report_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    _text = ""
                if _extract_markdown_label(_text, "TDD-Judgement").upper() == "BLOCKED":
                    self.console.warning(
                        f"[{custom_agent}] {report_path.as_posix()}: "
                        "TDD-Judgement=BLOCKED（テスト側/共有設定ブロッカーを記録）。"
                        "ステップは成功扱いだが要フォロー。"
                    )
        return errors

    def _run_asdw_ui_red_unresolved_contract_gate(
        self,
        step_id: str,
        custom_agent: Optional[str],
        workflow_id: Optional[str],
    ) -> List[str]:
        """Fail ASDW-WEB UI RED tests that embed unresolved TBD contracts."""
        workflow_key = str(workflow_id or "").strip().lower()
        step_parts = str(step_id).split("/", 1)
        base_step_id = step_parts[0]
        target_key = step_parts[1].strip() if len(step_parts) > 1 else ""
        if not (
            workflow_key == "asdw-web"
            and base_step_id == "4.1"
            and custom_agent == "Dev-Microservice-Azure-UITestCoding"
            and target_key
        ):
            return []

        try:
            from hve.artifact_validation import validate_asdw_ui_red_tests_no_unresolved_contracts
        except Exception as exc:
            return [f"[{custom_agent}] UI RED unresolved contract gate import failed: {exc}"]

        test_root = Path.cwd() / "src" / "test" / "ui" / target_key
        return [
            f"[{custom_agent}] generated UI RED test contract failed: {err}"
            for err in validate_asdw_ui_red_tests_no_unresolved_contracts(test_root)
        ]

    # ------------------------------------------------------------------
    # Deploy 系 Agent 向け AC 検証 gate (T5)
    # ------------------------------------------------------------------
    def _run_deploy_ac_gate(
        self, step_id: str, custom_agent: Optional[str], workflow: Optional[Any] = None
    ) -> List[str]:
        """Deploy 系 Agent の ac-verification.md を検査する。

        completion-report.md に pre-flight 失敗マーカー
        （`<!-- fatal: pre-flight-failed: {理由} -->`）があれば、ac-verification.md
        検査より先に明確な理由で fail させる。allowlist 外 Agent や report 不在
        パターンの判定は `validate_deploy_ac_verification` に委譲。

        実在系 AC は registry の `StepDef.reality_gate_acs`（宣言があれば優先）から
        解決し、無ければ後方互換で Agent 名ハードコード辞書
        `_DEPLOY_AGENT_REALITY_AC` にフォールバックする。どちらでも AC が
        解決できない場合は gate を発火しない（空 list 返却）。
        """
        if not custom_agent:
            return []
        try:
            from hve.artifact_validation import (
                is_deploy_step,
                validate_asdw_foundry_deploy_artifacts,
                validate_deploy_ac_verification,
            )
        except Exception as _import_exc:
            self.console.warning(
                f"  ⚠️ Deploy AC gate: artifact_validation import failed ({_import_exc}); skipping"
            )
            return []
        # registry 宣言の reality_gate_acs を解決（fan-out 子 step "1.2/D01" は基底 ID で照合）。
        registry_acs: List[str] = []
        if workflow is not None:
            try:
                base_step_id = str(step_id).split("/", 1)[0]
                _step_def = workflow.get_step(base_step_id)
                if _step_def is not None:
                    registry_acs = list(getattr(_step_def, "reality_gate_acs", []) or [])
            except Exception:
                registry_acs = []
        # allowlist 判定: registry 宣言があるか、後方互換 dict のメンバーなら発火。
        if not is_deploy_step(custom_agent, registry_acs):
            return []
        # 規約: <work-root>/{custom_agent}/Issue-step-{step_id をハイフン化}/ac-verification.md
        # <work-root> は resolve_work_root()（HVE_WORK_ROOT または work/run/<run-id>/）。
        # run スコープ外の legacy `work/` は探索しない。
        identifier = "step-" + str(step_id).replace(".", "-")
        try:
            from hve.split_fork import resolve_work_root
            work_root = resolve_work_root()
        except Exception as _rwr_exc:
            self.console.warning(
                f"  ⚠️ Deploy AC gate: resolve_work_root unavailable ({_rwr_exc}); "
                "skipping"
            )
            return []
        base = work_root / custom_agent
        report_path = base / f"Issue-{identifier}" / "ac-verification.md"
        # Pre-flight 失敗マーカー検出: deploy prompt は pre-flight 失敗時に
        # completion-report.md へ `<!-- fatal: pre-flight-failed: {理由} -->` を記載する。
        # ac-verification.md 不在判定より先に検出し、明確な理由で fail させる
        # （未検出時は従来どおり ac-verification.md を検査）。
        _preflight_reports = [base / f"Issue-{identifier}" / "completion-report.md"]
        if base.exists():
            _preflight_reports += sorted(base.glob("Issue-*/completion-report.md"))
        _seen_cr: set[str] = set()
        for _cr in _preflight_reports:
            if str(_cr) in _seen_cr or not _cr.is_file():
                continue
            _seen_cr.add(str(_cr))
            try:
                _cr_text = _cr.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            _m = re.search(
                r"<!--\s*fatal:\s*pre-flight-failed:?\s*(?P<reason>.*?)\s*-->", _cr_text
            )
            if _m:
                _reason = _m.group("reason").strip()
                # 未置換のプレースホルダ（雛形の引用）は実失敗ではないため無視する。
                if _reason == "{理由}":
                    continue
                return [
                    f"[{custom_agent}] pre-flight failed: "
                    f"{_reason or '(理由未記載)'} (from {_cr.name})"
                ]
        if not report_path.exists():
            # フォールバック: Issue-* を glob（識別子が step-<id> 以外の場合に対応）
            cands = sorted(base.glob("Issue-*/ac-verification.md")) if base.exists() else []
            if cands:
                report_path = cands[-1]
            else:
                # 規約パス・glob フォールバックの双方で未発見。
                # 「Agent が規約パス Issue-step-<id> に書いた」という誤解を避けるため、
                # 探索した両経路と既存の Issue-* ディレクトリ（あれば）を診断に含める。
                existing = (
                    sorted(p.name for p in base.glob("Issue-*") if p.is_dir())
                    if base.exists()
                    else []
                )
                if not base.exists():
                    hint = f"agent work root does not exist: {base}"
                elif existing:
                    hint = f"existing Issue-* dirs: {', '.join(existing[:5])}"
                else:
                    hint = "agent work root exists but no Issue-* dirs under it"
                # 成果物が丸ごと未生成のときは、Agent が必須成果物を作らずにターンを
                # 終えた可能性が高い（git/PR 操作や推論ループへの脱線を含む）。原因調査の
                # 起点を示すため、actionable な一文を診断に付す。
                action_hint = (
                    "Agent が ac-verification.md を生成しないままターンを終えた可能性。"
                    "GREEN 未達時も AC-1 を ❌ で記録した ac-verification.md を作成して終了する必要あり。"
                    "git/PR 操作、docs 整理、Word/docx/chart 作成、TODO/SQL query、推論ループへの脱線が無いか console-log を確認。"
                    "step_io_summary の write 先が $null の場合は実成果物未生成を疑う"
                    if not existing
                    else "Issue-* は存在するが ac-verification.md が無い。"
                    "GREEN 未達時も AC-1 を ❌ で記録した ac-verification.md を作成して終了する必要あり。"
                    "出力先パスのドリフトが無いか確認"
                )
                return [
                    f"[{custom_agent}] ac-verification.md not found "
                    f"(searched canonical path {report_path} and glob "
                    f"'Issue-*/ac-verification.md' under {base}); {hint}; {action_hint}"
                ]
        errors = validate_deploy_ac_verification(report_path, custom_agent, registry_acs)
        base_step_id = str(step_id).split("/", 1)[0]
        workflow_id = getattr(workflow, "id", "") if workflow is not None else ""
        if (
            workflow_id == "asdw-web"
            and base_step_id == "2.2"
            and custom_agent == "Dev-Microservice-Azure-AddServiceDeploy"
        ):
            repo_root = Path.cwd()
            artifact_errors = validate_asdw_foundry_deploy_artifacts(
                repo_root / "docs" / "azure" / "azure-services-additional.md",
                repo_root
                / "src"
                / "infra"
                / "azure"
                / "create-azure-additional-resources"
                / "services",
                repo_root
                / "src"
                / "infra"
                / "azure"
                / "create-azure-additional-resources"
                / "verify-additional-resources.sh",
            )
            errors.extend(
                f"[{custom_agent}] Foundry deploy artifact contract failed: {error}"
                for error in artifact_errors
            )
        return errors

    # ------------------------------------------------------------------
    # 内部ヘルパー — SDK data 属性の安全取得
    # ------------------------------------------------------------------

    @staticmethod
    def _get(data: Any, *names: str, default: Any = "") -> Any:
        """data オブジェクトから属性を安全に取得する。

        SDK v0.2.2 Python では snake_case 属性名を使用するが、
        将来の変更に備え camelCase もフォールバックで試す。
        """
        if data is None:
            return default
        for name in names:
            val = getattr(data, name, None)
            if val is not None:
                return val
        return default

    async def _poll_steering_ipc(self, session: Any, step_id: str) -> None:
        """GUI からのジョブ対話 IPC を監視する（FR-GUI-12）。

        `config.steering_ipc_dir` が未設定の場合は即座に終了する（機能無効）。
        検出した要求は作成順に原子的に claim してから処理するため、順序変更や
        取消と競合しても同じ要求を 2 度送信しない。

        呼び出し元（`_send_and_wait_with_model_call_failure_guard`）が
        `asyncio.create_task` でタスク化し、メインタスク完了時に `cancel()` する前提の
        無限ループ。`asyncio.CancelledError` はそのまま伝播させる。
        """
        ipc_dir_raw = getattr(self.config, "steering_ipc_dir", None)
        if not ipc_dir_raw:
            return
        try:
            from .job_interaction_ipc import (
                claim_request,
                list_request_paths,
                read_request,
                release_request,
            )
        except ImportError:  # pragma: no cover - script execution path
            from job_interaction_ipc import (  # type: ignore[no-redef]
                claim_request,
                list_request_paths,
                read_request,
                release_request,
            )

        ipc_dir = Path(ipc_dir_raw)

        while True:
            try:
                for path in list_request_paths(ipc_dir, step_id):
                    claimed = claim_request(path)
                    if claimed is None:
                        continue
                    request = read_request(claimed)
                    if request is None:
                        release_request(claimed)
                        continue
                    try:
                        await self._dispatch_job_interaction(
                            session, step_id, request, ipc_dir
                        )
                    finally:
                        release_request(claimed)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 対話送信はベストエフォート機能のため、想定外の例外で polling ループ
                # 自体が停止しないようにする。
                pass
            await asyncio.sleep(_STEERING_POLL_INTERVAL_SECONDS)

    async def _dispatch_job_interaction(
        self,
        session: Any,
        step_id: str,
        request: Any,
        ipc_dir: Path,
    ) -> None:
        """1 件の対話要求を SDK 呼び出しへ写像し、ACK を書き出す（FR-GUI-12）。

        ACK には要求 ID・action・状態だけを含め、要求本文を複写しない。
        `stop_and_send` は abort 成功だけでは受理とせず、実際に新しいターンとして
        送信できた時点で ACK する（送信前に Step が例外復帰しても accepted を残さない）。
        """
        try:
            from .job_interaction_ipc import ACTION_QUEUE, ACTION_STOP_AND_SEND
        except ImportError:  # pragma: no cover - script execution path
            from job_interaction_ipc import (  # type: ignore[no-redef]
                ACTION_QUEUE,
                ACTION_STOP_AND_SEND,
            )

        try:
            if request.action == ACTION_QUEUE:
                await session.send(request.text, mode="enqueue")
                self.console.event(
                    f"  ⏳ [{step_id}] 対話メッセージをキューへ追加しました"
                )
            elif request.action == ACTION_STOP_AND_SEND:
                await session.abort()
                self._pending_job_redirects.setdefault(step_id, []).append(
                    (request.request_id, request.text)
                )
                self.console.event(
                    f"  ⏹ [{step_id}] 実行中のターンを中断し、指示を新しいターンへ引き継ぎます"
                )
                return
            else:
                await session.send(request.text, mode="immediate")
                self.console.event(
                    f"  ⚡ [{step_id}] 割り込みメッセージを送信しました"
                )
        except Exception as exc:
            detail = type(exc).__name__
            self.console.warning(
                f"  ⚠️ [{step_id}] 対話メッセージの送信に失敗しました ({detail})"
            )
            self._write_job_interaction_ack(
                ipc_dir, request.request_id, request.action, "failed", detail=detail
            )
            return
        self._write_job_interaction_ack(
            ipc_dir, request.request_id, request.action, "accepted"
        )

    def _write_job_interaction_ack(
        self,
        ipc_dir: Optional[Path],
        request_id: str,
        action: str,
        status: str,
        *,
        detail: str = "",
    ) -> None:
        """ジョブ対話の ACK を書き出す。失敗しても Step を落とさない。"""
        if ipc_dir is None:
            ipc_dir_raw = getattr(self.config, "steering_ipc_dir", None)
            if not ipc_dir_raw:
                return
            ipc_dir = Path(ipc_dir_raw)
        try:
            from .job_interaction_ipc import write_ack
        except ImportError:  # pragma: no cover - script execution path
            from job_interaction_ipc import write_ack  # type: ignore[no-redef]
        try:
            write_ack(ipc_dir, request_id, action, status, detail=detail)
        except (OSError, ValueError):
            pass

    def _pop_pending_job_redirect(self, step_id: str) -> Optional[Tuple[str, str]]:
        """`stop_and_send` で受け取った未送信の (request_id, 指示) を 1 件取り出す。"""
        pending = self._pending_job_redirects.get(step_id)
        if not pending:
            return None
        entry = pending.pop(0)
        if not pending:
            self._pending_job_redirects.pop(step_id, None)
        return entry

    def _fail_pending_job_redirects(self, step_id: str, detail: str) -> None:
        """送信されないまま破棄される指示を failed として ACK する。"""
        try:
            from .job_interaction_ipc import ACTION_STOP_AND_SEND
        except ImportError:  # pragma: no cover - script execution path
            from job_interaction_ipc import ACTION_STOP_AND_SEND  # type: ignore[no-redef]
        for request_id, _text in self._pending_job_redirects.pop(step_id, []):
            self._write_job_interaction_ack(
                None, request_id, ACTION_STOP_AND_SEND, "failed", detail=detail
            )

    async def _drain_pending_job_redirects(
        self,
        session: Any,
        step_id: str,
        result: Any,
        *,
        timeout: float,
    ) -> Any:
        """`stop_and_send` の指示を新しいターンとして実行し、その応答を主応答とする。

        abort により主タスクの待機が復帰しても、送信内容が観測されないまま
        Step が後続ゲートへ進まないことを保証する。
        """
        try:
            from .job_interaction_ipc import ACTION_STOP_AND_SEND
        except ImportError:  # pragma: no cover - script execution path
            from job_interaction_ipc import ACTION_STOP_AND_SEND  # type: ignore[no-redef]

        while True:
            entry = self._pop_pending_job_redirect(step_id)
            if entry is None:
                return result
            request_id, text = entry
            try:
                result = await session.send_and_wait(text, timeout=timeout)
            except Exception as exc:
                self._write_job_interaction_ack(
                    None,
                    request_id,
                    ACTION_STOP_AND_SEND,
                    "failed",
                    detail=type(exc).__name__,
                )
                raise
            self._write_job_interaction_ack(
                None, request_id, ACTION_STOP_AND_SEND, "accepted"
            )
            # 主タスクの待機は既に解消済みのため、再待機したターンでも
            # セキュリティ違反と model.call_failure の閾値超過を取りこぼさない。
            security_event = self._session_security_violation_events.get(step_id)
            if security_event is not None and security_event.is_set():
                raise RuntimeError(
                    self._session_security_violations.get(
                        step_id,
                        f"session security violation for step {step_id}",
                    )
                )
            failure_event = self._model_call_failure_events.get(step_id)
            if failure_event is not None and failure_event.is_set():
                count = self._model_call_failure_counts.get(step_id, 0)
                raise RuntimeError(
                    f"model.call_failure repeated {count} times for step {step_id}"
                )

    async def _send_and_wait_with_model_call_failure_guard(
        self,
        session: Any,
        prompt: str,
        *,
        timeout: float,
        step_id: str,
    ) -> Any:
        """Phase 1 の send_and_wait を model.call_failure 連続発生で早期失敗させる。

        GUI からの Steering IPC（`_poll_steering_ipc`）も並行タスクとして起動し、
        メインタスク完了時に確実にキャンセルする。
        """
        self._model_call_failure_counts[step_id] = 0
        failure_event = asyncio.Event()
        self._model_call_failure_events[step_id] = failure_event
        security_event = self._session_security_violation_events.get(step_id)
        send_task = asyncio.create_task(session.send_and_wait(prompt, timeout=timeout))
        failure_task = asyncio.create_task(failure_event.wait())
        security_task = (
            asyncio.create_task(security_event.wait())
            if security_event is not None
            else None
        )
        steering_task = asyncio.create_task(self._poll_steering_ipc(session, step_id))
        try:
            wait_tasks = {send_task, failure_task}
            if security_task is not None:
                wait_tasks.add(security_task)
            done, _pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if (
                security_task is not None
                and security_task in done
            ):
                if not send_task.done():
                    send_task.cancel()
                    try:
                        await send_task
                    except asyncio.CancelledError:
                        pass
                raise RuntimeError(
                    self._session_security_violations.get(
                        step_id,
                        f"session security violation for step {step_id}",
                    )
                )
            if failure_task in done and not send_task.done():
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass
                count = self._model_call_failure_counts.get(step_id, 0)
                raise RuntimeError(
                    f"model.call_failure repeated {count} times for step {step_id}"
                )
            result = await send_task
            return await self._drain_pending_job_redirects(
                session, step_id, result, timeout=timeout
            )
        finally:
            if not failure_task.done():
                failure_task.cancel()
                try:
                    await failure_task
                except asyncio.CancelledError:
                    pass
            if security_task is not None and not security_task.done():
                security_task.cancel()
                try:
                    await security_task
                except asyncio.CancelledError:
                    pass
            if not steering_task.done():
                steering_task.cancel()
                try:
                    await steering_task
                except asyncio.CancelledError:
                    pass
            self._model_call_failure_events.pop(step_id, None)
            self._model_call_failure_counts.pop(step_id, None)
            self._fail_pending_job_redirects(step_id, "step_ended_before_send")

    # ------------------------------------------------------------------
    # 内部イベントハンドラー
    # ------------------------------------------------------------------

    def _handle_session_event_for_step(self, event: Any, step_id: str) -> None:
        """特定 Step に束縛して CopilotSession イベントを処理する。"""
        self._handle_session_event(event, step_id_override=step_id)

    def _handle_session_event(self, event: Any, *, step_id_override: Optional[str] = None) -> None:
        """CopilotSession のイベントを受け取り Console に出力する。

        SDK v0.2.2 のイベントタイプ一覧:
        https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
        """
        # SDK v0.2.2: event.type は SessionEventType enum、.value で文字列取得
        etype = getattr(getattr(event, "type", None), "value", "") or ""
        data = getattr(event, "data", None)
        step_id = step_id_override if step_id_override is not None else getattr(self, "_current_step_id", "")
        _get = self._get

        # ディスパッチテーブルを使わず if-elif で処理する。
        # etype の出現頻度が高いものを上に配置。

        if etype == "model.call_failure":
            count = self._model_call_failure_counts.get(step_id, 0) + 1
            self._model_call_failure_counts[step_id] = count
            detail = _get(data, "reason", "code", "error_code", "errorCode", "status", default="")
            detail_text = str(detail)[:120] if detail else ""
            suffix = f": {detail_text}" if detail_text else ""
            self.console.warning(
                f"⚠️ [{step_id}] model.call_failure ({count}/{_MODEL_CALL_FAILURE_THRESHOLD}){suffix}"
            )
            try:
                self.console.stats_event(
                    "model_call_failure",
                    step_id=step_id,
                    count=count,
                    threshold=_MODEL_CALL_FAILURE_THRESHOLD,
                    detail=detail_text or None,
                )
            except Exception:
                pass
            if count >= _MODEL_CALL_FAILURE_THRESHOLD:
                failure_event = self._model_call_failure_events.get(step_id)
                if failure_event is not None:
                    failure_event.set()
            return

        # --- ストリーム系 (高頻度、show_stream ガード) ---
        if etype == "assistant.message_delta":
            # SDK 仕様では deltaContent (camelCase) のみ。Python SDK の snake_case 変換に備え delta_content も受ける。
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                # TTFT 計測: turn_start 以降初めてのトークンならポップ
                ttft_start = self._ttft_pending.pop(step_id, None)
                if ttft_start is not None:
                    try:
                        elapsed_ms = (time.monotonic() - ttft_start) * 1000.0
                        self.console.stats_event(
                            "assistant_ttft",
                            step_id=step_id,
                            ttft_ms=round(elapsed_ms, 2),
                        )
                    except Exception:
                        pass
                self.console.stream_token(step_id, token)
                # ADR-0002 E-1: stderr JSON へトークン長を出力（verbosity 不問）
                try:
                    self.console.token_chunk(step_id, token, kind="message")
                except Exception:
                    pass
            return

        if etype == "assistant.streaming_delta":
            # バイト進捗 — 表示不要
            return

        # --- ツール実行 (高頻度) ---
        if etype == "tool.execution_start":
            tool_name = extract_tool_name_from_event(event) or _get(data, "tool_name", "toolName", "name", default="unknown")
            args = _get(data, "arguments", default=None)
            tool_call_id = str(
                _get(data, "tool_call_id", "toolCallId", default="") or ""
            )
            start_info = (
                str(tool_name or ""),
                self._safe_failed_tool_args(str(tool_name or ""), args),
            )
            if tool_call_id:
                correlation_key = (step_id or "", tool_call_id)
                existing = self._tool_start_by_call.get(correlation_key)
                if existing is not None:
                    self._tool_start_by_call[correlation_key] = (
                        "",
                        {},
                        existing[2] + 1,
                    )
                else:
                    self._tool_start_by_call[correlation_key] = (
                        start_info[0],
                        start_info[1],
                        1,
                    )
            else:
                legacy_key = step_id or ""
                existing = self._last_tool_start_by_step.get(legacy_key)
                if existing is not None:
                    self._last_tool_start_by_step[legacy_key] = (
                        "",
                        {},
                        existing[2] + 1,
                    )
                else:
                    self._last_tool_start_by_step[legacy_key] = (
                        start_info[0],
                        start_info[1],
                        1,
                    )

            # FR-MCPLOG-01: MCP 由来の tool は全件全文をログへ残す。
            # 後続の `report_intent` / `task` の早期 return より前で行うこと。
            mcp_server_name = _get(data, "mcp_server_name", "mcpServerName", default="")
            if mcp_server_name:
                self.console.mcp_tool_request(
                    str(mcp_server_name),
                    str(_get(data, "mcp_tool_name", "mcpToolName", default="") or tool_name or ""),
                    tool_call_id=tool_call_id,
                    step_id=step_id or "",
                    arguments=args,
                )

            # report_intent ツールは Thinking として表示する（通常のアクション表示をスキップ）
            if tool_name == "report_intent":
                if step_id:
                    self.console.increment_tool_count(step_id)
                intent_text = ""
                if isinstance(args, dict):
                    intent_text = (
                        args.get("intent")
                        or args.get("message")
                        or args.get("text")
                        or args.get("description")
                        or args.get("content")
                        or ""
                    )
                    if not intent_text:
                        # フォールバック: 最初の文字列値を使う
                        for v in args.values():
                            if v and isinstance(v, str):
                                intent_text = v
                                break
                elif isinstance(args, str):
                    intent_text = args
                if intent_text:
                    self.console.thinking(step_id, str(intent_text))
                return

            # task ツールは SDK 内部制御ツールのため表示を簡潔にする
            if tool_name == "task":
                if step_id:
                    self.console.increment_tool_count(step_id)
                # verbose 時のみ表示、それ以外はスキップ
                if self.console.verbose:
                    self.console.event(f"  🔧 [{step_id}] task (internal)")
                # GUI 用構造化イベント（verbose 依存せず常時発火）
                try:
                    self.console.stats_event(
                        "tool_invoked",
                        step_id=step_id,
                        tool_name="task",
                        action_name="task (internal)",
                    )
                except Exception:
                    pass
                return

            action_name, detail = self._build_action_display(tool_name, args)
            if args and isinstance(args, dict):
                # 既存のファイル I/O 追跡ロジックは維持
                self._track_tool_files(step_id, tool_name, args)
            if tool_name:
                # FR-TS-07: 自動 pin の学習材料。id への解決は Step 終了時に行う。
                self._toolsearch_called_tools.append(str(tool_name))
            workiq_tool_name = extract_workiq_tool_name_from_event(event)
            if workiq_tool_name:
                self._workiq_called_tools.append(workiq_tool_name)
                if not self._workiq_tool_called:
                    self._workiq_tool_called = True
                    self.console.status(
                        f"🔍 Work IQ ツール '{workiq_tool_name}' が呼び出されました"
                    )
            self.console.action_start(step_id, action_name, detail)
            # GUI 用構造化イベント：tool_name を集計キーとして送出。
            # action_name は表示用の整形済み文字列 (Run (PowerShell) 等)。
            try:
                self.console.stats_event(
                    "tool_invoked",
                    step_id=step_id,
                    tool_name=str(tool_name or ""),
                    action_name=str(action_name or ""),
                )
            except Exception:
                pass
            # T4 フォールバック: SDK が skill.invoked を発火しない経路で
            # Skill が SKILL.md / references の view として読まれた場合に検出。
            try:
                if args and isinstance(args, dict):
                    self._detect_skill_load_from_args(step_id or "", args)
            except Exception:
                pass
            return

        if etype == "tool.execution_complete":
            success = _get(data, "success", default=False)
            error = _get(data, "error", default=None)
            tool_call_id = str(
                _get(data, "tool_call_id", "toolCallId", default="") or ""
            )
            # FR-MCPLOG-01: 完了イベントは MCP サーバー名を持たないため、
            # ロガ側の `tool_call_id` 相関だけが帰属を決める。
            self.console.mcp_tool_response(
                tool_call_id=tool_call_id,
                success=bool(success),
                content=str(_get(_get(data, "result", default=None), "content", default="") or ""),
                error=str(_get(error, "message", default=error) or "") if error else "",
                step_id=step_id or "",
            )
            last_tool_name: str
            last_args: Dict[str, Any]
            if tool_call_id:
                correlation_key = (step_id or "", tool_call_id)
                correlated = self._tool_start_by_call.get(correlation_key)
                if correlated is None:
                    last_tool_name, last_args = "", {}
                else:
                    last_tool_name, last_args, pending_count = correlated
                    if pending_count <= 1:
                        self._tool_start_by_call.pop(correlation_key, None)
                    else:
                        self._tool_start_by_call[correlation_key] = (
                            last_tool_name,
                            last_args,
                            pending_count - 1,
                        )
            else:
                legacy_key = step_id or ""
                correlated = self._last_tool_start_by_step.get(legacy_key)
                if correlated is None:
                    last_tool_name, last_args = "", {}
                else:
                    last_tool_name, last_args, pending_count = correlated
                    if pending_count <= 1:
                        self._last_tool_start_by_step.pop(legacy_key, None)
                    else:
                        self._last_tool_start_by_step[legacy_key] = (
                            last_tool_name,
                            last_args,
                            pending_count - 1,
                        )
            if success:
                result_text = self._build_tool_result_text(data)
                # NFR-OBS-07: 回復済みツール失敗を GUI が降格できるよう、
                # 同じ (step, tool) での成功を構造化イベントとして発火する。
                if last_tool_name:
                    try:
                        self.console.stats_event(
                            "tool_result",
                            step_id=step_id or "",
                            tool_name=str(last_tool_name),
                            success=True,
                        )
                    except Exception:
                        pass
                # result_text が空でも action_result を呼ぶ。console 側で実行中アクション
                # 追跡（step_elapsed のハートビート表示）をクリアするため。空文字時は
                # 表示されずクリアのみ行われる（成功・結果テキスト無しのツールで追跡が
                # 残留し、誤った「実行中」表示が次のツール開始まで続くのを防ぐ）。
                self.console.action_result(step_id, result_text)
            else:
                error_msg = ""
                if error:
                    error_msg = _get(error, "message", default=str(error))
                # T-M5: ツール失敗ログにツール名を前置（特に timeout のような汎用エラーの真因特定支援）
                # extract_tool_name_from_event は tool.execution_start 専用のため、
                # tool.execution_complete.data から直接 tool_name を抽出する。
                # workiq.py:689 と同じく MCP 系を legacy より優先する。
                mcp_tool_name = _get(data, "mcp_tool_name", "mcpToolName", default="")
                legacy_tool_name = _get(data, "tool_name", "toolName", "name", default="")
                failed_tool_name = mcp_tool_name or legacy_tool_name
                if failed_tool_name:
                    error_msg = f"{failed_tool_name}: {error_msg}" if error_msg else str(failed_tool_name)
                effective_tool_name = str(failed_tool_name or last_tool_name or "")
                if not failed_tool_name and last_tool_name:
                    error_msg = (
                        f"{last_tool_name}: {error_msg}"
                        if error_msg
                        else str(last_tool_name)
                    )
                args_tool_name = effective_tool_name
                args_summary = self._build_failed_tool_args_summary(args_tool_name, last_args)
                if args_summary:
                    error_msg = f"{error_msg} ({args_summary})" if error_msg else args_summary
                # 失敗も観測対象とする。引数・エラー本文は送らない（FR-RTO-04）。
                try:
                    self.console.stats_event(
                        "tool_result",
                        step_id=step_id or "",
                        tool_name=str(effective_tool_name or ""),
                        success=False,
                    )
                except Exception:
                    pass
                self.console.tool_result(step_id, False, error_msg=error_msg)
            return

        if etype == "tool.execution_partial_result":
            output = _get(data, "partial_output", "partialOutput") or ""
            if output:
                self.console.tool_output(step_id, output)
            return

        if etype == "tool.execution_progress":
            msg = _get(data, "progress_message", "progressMessage") or ""
            if msg:
                self.console.event(f"  ⏳ [{step_id}] {msg}")
            return

        # --- アシスタント応答 ---
        if etype == "assistant.intent":
            def _normalize_intent_candidate(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, str):
                    return value
                return str(value)

            def _collect_detail_values(details: Any) -> List[str]:
                if details is None:
                    return []
                if isinstance(details, dict):
                    raw_values = details.values()
                elif isinstance(details, (list, tuple, set)):
                    raw_values = details
                else:
                    raw_values = [details]

                normalized_values: List[str] = []
                for raw_value in raw_values:
                    text_value = _normalize_intent_candidate(raw_value)
                    if text_value == "":
                        continue
                    normalized_values.append(text_value)
                return normalized_values

            def _sanitize_diag_value(key: str, value: Any) -> str:
                def _truncate_diag_text(text: str) -> str:
                    if len(text) > _INTENT_DIAG_MAX_VALUE_LENGTH:
                        return f"{text[:_INTENT_DIAG_MAX_VALUE_LENGTH]}...(truncated)"
                    return text

                key_l = str(key).lower()
                if any(t in key_l for t in _INTENT_DIAG_SENSITIVE_TOKENS):
                    return "<masked>"

                def _sanitize_nested(obj: Any) -> Any:
                    if isinstance(obj, dict):
                        sanitized = {}
                        for nested_k, nested_v in obj.items():
                            nested_k_str = str(nested_k)
                            nested_k_l = nested_k_str.lower()
                            if any(t in nested_k_l for t in _INTENT_DIAG_SENSITIVE_TOKENS):
                                sanitized[nested_k_str] = "<masked>"
                            else:
                                sanitized[nested_k_str] = _sanitize_nested(nested_v)
                        return sanitized
                    if isinstance(obj, (list, tuple, set)):
                        return [_sanitize_nested(v) for v in obj]
                    if obj is None:
                        return None
                    text_obj = str(obj)
                    return _truncate_diag_text(text_obj)

                try:
                    safe_value = _sanitize_nested(value) if key_l == "details" else value
                    text = repr(safe_value)
                except (TypeError, ValueError):
                    return "<error>"

                return _truncate_diag_text(text)

            # 診断ログ: intent イベントの data 構造を確認する（verbose 時のみ）
            is_verbose = self.config.verbosity >= 3
            if is_verbose and data is not None:
                _diag_attrs = {}
                _diag_reasons: List[str] = []
                _diag_items = None

                if isinstance(data, dict):
                    _diag_items = data.items()
                    _diag_reasons.append("source=dict")
                else:
                    try:
                        data_dict = vars(data)
                    except TypeError as exc:
                        data_dict = None
                        _diag_reasons.append(
                            f"vars_failed={type(exc).__name__}"
                        )
                    if isinstance(data_dict, dict):
                        _diag_items = data_dict.items()
                        _diag_reasons.append("source=vars")
                    else:
                        _fallback_attrs = {}
                        _fallback_errors = {}
                        for _a in dir(data):
                            if str(_a).startswith("_"):
                                continue
                            try:
                                _fallback_attrs[_a] = getattr(data, _a)
                            except Exception as exc:
                                _fallback_errors[_a] = f"{type(exc).__name__}"
                        _diag_items = _fallback_attrs.items()
                        _diag_reasons.append("source=dir/getattr")
                        if _fallback_errors:
                            _diag_reasons.append(
                                f"getattr_failed={len(_fallback_errors)}"
                            )

                if _diag_items is not None:
                    for _a, _v in _diag_items:
                        attr_name = str(_a)
                        if attr_name.startswith("_"):
                            continue
                        if len(_diag_attrs) >= _INTENT_DIAG_MAX_ATTRS:
                            _diag_attrs["__truncated__"] = "<max-attrs-reached>"
                            break
                        if attr_name in _INTENT_DIAG_ALLOWED_KEYS:
                            _diag_attrs[attr_name] = _sanitize_diag_value(attr_name, _v)
                        else:
                            _diag_attrs[attr_name] = "<omitted>"

                if not _diag_attrs:
                    _diag_reasons.append("no_public_attrs_extracted")
                self.console.event(
                    "🔍 [DIAG] assistant.intent data attrs: "
                    f"{_diag_attrs} "
                    f"(reasons: {', '.join(_diag_reasons) if _diag_reasons else 'none'})"
                )

            intent_text = ""
            for field_name in ("intent", "description", "text", "content", "message"):
                candidate_text = _normalize_intent_candidate(_get(data, field_name))
                if candidate_text:
                    intent_text = candidate_text
                    break

            if not intent_text:
                kind = _normalize_intent_candidate(_get(data, "kind"))
                if kind:
                    detail_values = _collect_detail_values(_get(data, "details"))
                    intent_text = (
                        f"{kind}: {', '.join(detail_values)}"
                        if detail_values
                        else kind
                    )

            if intent_text:
                self.console.thinking(step_id, str(intent_text))
            elif is_verbose:
                self.console.event(
                    f"⚠️ [DIAG] assistant.intent fired but no text extracted. "
                    f"data type={type(data).__name__}"
                )
            return

        if etype == "assistant.turn_start":
            turn_id = _get(data, "turn_id", "turnId") or ""
            self.console.turn_start(step_id, turn_id)
            # TTFT 計測開始
            self._ttft_pending[step_id] = time.monotonic()
            return

        if etype == "assistant.turn_end":
            self.console.stream_end(step_id)
            self.console.turn_end(step_id)
            # TTFT 未観測のまま turn が終わったケースはクリア
            self._ttft_pending.pop(step_id, None)
            return

        if etype == "assistant.message":
            content = _get(data, "content") or ""
            tool_reqs = _get(data, "tool_requests", "toolRequests", default=None) or []
            self.console.assistant_message(step_id, len(content), len(tool_reqs))
            return

        if etype == "assistant.reasoning":
            content = _get(data, "content") or ""
            self.console.reasoning_complete(step_id, content)
            return

        if etype == "assistant.reasoning_delta":
            token = _get(data, "delta_content", "deltaContent") or ""
            if token:
                self.console.reasoning_token(step_id, token)
                # ADR-0002 E-1: stderr JSON へ reasoning デルタ長を出力
                try:
                    self.console.token_chunk(step_id, token, kind="reasoning")
                except Exception:
                    pass
            return

        if etype == "assistant.usage":
            # T1.5: 初回 assistant.usage 受信時に 1 回だけ env を dump
            # (P1: env 伝播 / P2: 文字化け・空白混入 / P4: モジュールキャッシュ
            # の切り分け用)。ハンドラに到達した時点で「assistant.usage 経路
            # 自体は OK」と判明するため、後の env チェックの真偽を裏取りできる。
            if not getattr(self, "_debug_env_dumped", False):
                self._debug_env_dumped = True
                try:
                    raw_env = os.environ.get(
                        "HVE_DEBUG_ASSISTANT_USAGE", "<unset>"
                    )
                    # stats_event 経路 (構造化 / GUI state 反映用)。
                    self.console.stats_event(
                        "debug_env",
                        step_id=step_id,
                        HVE_DEBUG_ASSISTANT_USAGE_raw=raw_env,
                        HVE_DEBUG_ASSISTANT_USAGE_repr=repr(raw_env),
                        HVE_DEBUG_ASSISTANT_USAGE_len=(
                            len(raw_env) if isinstance(raw_env, str) else -1
                        ),
                        pid=os.getpid(),
                    )
                    # 通常ログ経路 (UI _log_pane へ確実に表示するため。
                    # `[hve:stats]` 行は is_stats_line で _log_pane から除外
                    # されるため、診断目的では通常行として別途出力する)。
                    # 通常運用時のログノイズを避けるため env gate を適用。
                    if isinstance(raw_env, str) and raw_env.strip() in (
                        "1", "true", "True"
                    ):
                        self.console.diag(
                            f"[debug_env step={step_id}] "
                            f"HVE_DEBUG_ASSISTANT_USAGE={raw_env!r} "
                            f"(len={len(raw_env)}) "
                            f"pid={os.getpid()}"
                        )
                except Exception:
                    pass
            model = _get(data, "model") or "?"
            inp = _get(data, "input_tokens", "inputTokens", default=0) or 0
            out = _get(data, "output_tokens", "outputTokens", default=0) or 0
            dur = _get(data, "duration", default=None)
            # SDK の AssistantUsageData.duration は timedelta | None。
            # int(timedelta) は TypeError になるためミリ秒へ変換する。
            dur_ms = int(dur.total_seconds() * 1000) if dur else None
            self.console.usage(step_id, model, int(inp), int(out),
                               duration_ms=dur_ms)
            # デバッグ採取: HVE_DEBUG_ASSISTANT_USAGE=1 で生 SDK ペイロードを
            # 1 行 JSON として stats_event 経由で出力する（フィールド名特定用、
            # 出力量が増えるため通常は無効）。
            if os.environ.get("HVE_DEBUG_ASSISTANT_USAGE", "").strip() in ("1", "true", "True"):
                try:
                    import json as _json
                    payload_json = _json.dumps(data, ensure_ascii=False, default=str)
                    self.console.stats_event(
                        "assistant_usage_raw",
                        step_id=step_id,
                        payload_json=payload_json,
                    )
                    # UI _log_pane へ確実に表示するため通常ログ経路でも出力。
                    # 長過ぎる場合は truncate（GUI 応答性 / ログメモリ保護）。
                    _MAX = 20000
                    shown = (
                        payload_json
                        if len(payload_json) <= _MAX
                        else payload_json[:_MAX] + "... [truncated]"
                    )
                    self.console.diag(
                        f"[assistant_usage_raw SENSITIVE_DEBUG step={step_id}] {shown}"
                    )
                except Exception as _raw_err:
                    # T1.5 (P3 切り分け): payload シリアライズ等で失敗した場合に
                    # 原因を表面化させる。silent fail だと「raw が出ない =
                    # env 伝播の問題」と誤判定されるため、err を構造化ログで出す。
                    try:
                        self.console.stats_event(
                            "assistant_usage_raw_err",
                            step_id=step_id,
                            err=str(_raw_err),
                            err_type=type(_raw_err).__name__,
                        )
                        self.console.diag(
                            f"[assistant_usage_raw_err step={step_id}] "
                            f"{type(_raw_err).__name__}: {_raw_err}"
                        )
                    except Exception:
                        pass
            # SDK 1.0.x で AssistantUsageData.copilot_usage / quota_snapshots は
            # Internal 属性 (_copilot_usage / _quota_snapshots) へ改名され、
            # getattr 経由 (_get) では取得できない。公開シリアライズ契約
            # data.to_dict() で camelCase キーの dict へ正規化してから読む
            # (copilotUsage.totalNanoAiu / tokenDetails / quotaSnapshots)。
            # cost / model / apiCallId 等は公開属性のままのため data から直接読む。
            usage_dict: dict = {}
            _to_dict = getattr(data, "to_dict", None)
            if callable(_to_dict):
                try:
                    _d = _to_dict()
                    if isinstance(_d, dict):
                        usage_dict = _d
                except Exception:
                    usage_dict = {}
            copilot_usage = usage_dict.get("copilotUsage")
            if not isinstance(copilot_usage, dict):
                copilot_usage = None
            # 詳細 (キャッシュ / reasoning / inter_token_latency / billing)を GUI へ
            try:
                cache_read = _get(data, "cache_read_tokens", "cacheReadTokens", default=None)
                cache_write = _get(data, "cache_write_tokens", "cacheWriteTokens", default=None)
                reasoning = _get(data, "reasoning_tokens", "reasoningTokens", default=None)
                itl = _get(data, "inter_token_latency_ms", "interTokenLatencyMs", default=None)
                token_details_raw = (
                    copilot_usage.get("tokenDetails")
                    if copilot_usage is not None
                    else None
                )
                token_details: list = []
                if token_details_raw:
                    for td in token_details_raw:
                        try:
                            td_d = td if isinstance(td, dict) else {}
                            token_details.append(
                                {
                                    "type": td_d.get("tokenType", "") or "",
                                    "count": int(td_d.get("tokenCount", 0) or 0),
                                    # cost_per_batch / batch_size は表示用補足情報。
                                    # 単位は AIU。単純加算しない（単価のため）。
                                    "cost_per_batch": td_d.get("costPerBatch"),
                                    "batch_size": td_d.get("batchSize"),
                                }
                            )
                        except Exception:
                            continue
                self.console.stats_event(
                    "assistant_usage",
                    step_id=step_id,
                    model=str(model),
                    input=int(inp),
                    output=int(out),
                    reasoning=int(reasoning) if reasoning is not None else None,
                    cache_read=int(cache_read) if cache_read is not None else None,
                    cache_write=int(cache_write) if cache_write is not None else None,
                    inter_token_latency_ms=(
                        float(itl) if itl is not None else None
                    ),
                    token_details=token_details or None,
                )
            except Exception:
                pass
            # --- AI Credit / 課金関連の抽出 (Phase A) ---
            # 抽出は `runtime_observability.extract_usage_credit_fields` へ単一化し
            # （FR-MAINT-07）、SDK Fleet mode 経路と同一実装を共有する。
            # session.disconnect が即時ハンドラクリアするため session.shutdown
            # 経由の totalPremiumRequests は届かない。assistant.usage 経由で
            # リアルタイムに料金/Reqs を把握する経路を新設する (捏造禁止)。
            try:
                credit_fields = extract_usage_credit_fields(data)
                if credit_fields is not None:
                    self.console.stats_event(
                        "usage_credit",
                        step_id=step_id,
                        **credit_fields,
                    )
            except Exception:
                pass
            try:
                quota_snapshots = usage_dict.get("quotaSnapshots")
                if isinstance(quota_snapshots, dict) and quota_snapshots:
                    for qid, snap in quota_snapshots.items():
                        if not isinstance(snap, dict):
                            continue
                        try:
                            reset_date = snap.get("resetDate")
                            reset_date_iso: Optional[str] = None
                            if reset_date is not None:
                                # to_dict() は ISO 文字列化済み。念のため
                                # datetime / date も許容する。
                                if hasattr(reset_date, "isoformat"):
                                    reset_date_iso = reset_date.isoformat()
                                else:
                                    reset_date_iso = str(reset_date)
                            self.console.stats_event(
                                "quota_snapshot",
                                step_id=step_id,
                                model=str(model),
                                quota_id=str(qid),
                                used_requests=float(
                                    snap.get("usedRequests", 0) or 0
                                ),
                                entitlement_requests=float(
                                    snap.get("entitlementRequests", 0) or 0
                                ),
                                remaining_percentage=float(
                                    snap.get("remainingPercentage", 0) or 0
                                ),
                                overage=float(snap.get("overage", 0) or 0),
                                is_unlimited_entitlement=bool(
                                    snap.get("isUnlimitedEntitlement", False)
                                ),
                                overage_allowed_with_exhausted_quota=bool(
                                    snap.get("overageAllowedWithExhaustedQuota", False)
                                ),
                                usage_allowed_with_exhausted_quota=bool(
                                    snap.get("usageAllowedWithExhaustedQuota", False)
                                ),
                                reset_date_iso=reset_date_iso,
                            )
                        except Exception:
                            continue
            except Exception:
                pass
            # TTFT 計測終了タイミング（turn 完了）フラグをリセット
            self._ttft_pending.pop(step_id, None)
            return

        # --- サブエージェント / スキル ---
        if etype == "subagent.started":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_started(step_id, name)
            return

        if etype == "subagent.completed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            self.console.subagent_completed(step_id, name)
            return

        if etype == "subagent.failed":
            name = _get(data, "agent_display_name", "agentDisplayName") or etype
            err = _get(data, "error") or ""
            self.console.subagent_failed(step_id, name, error=str(err))
            return

        if etype == "subagent.selected":
            name = _get(data, "agent_display_name", "agentDisplayName") or ""
            self.console.subagent_selected(step_id, name)
            return

        if etype == "subagent.deselected":
            self.console.event(f"🤖 [{step_id}] Agent 解除")
            return

        if etype == "skill.invoked":
            name = _get(data, "name") or ""
            # SDK 経由の skill.invoked は SKILL.md パス検出フォールバックと
            # 二重発火しないよう seen セットへ記録してから console へ。
            if name:
                seen = self._skill_invoked_seen.setdefault(step_id or "", set())
                if name in seen:
                    return
                seen.add(str(name))
            self.console.skill_invoked(step_id, name)
            return

        # --- セッション ---
        if etype == "session.error":
            err_type = _get(data, "error_type", "errorType") or ""
            message = _get(data, "message") or ""
            self.console.session_error(err_type, message)
            return

        if etype == "session.log":
            level = _get(data, "level") or "info"
            message = _get(data, "message") or ""
            if message:
                self.console.cli_log(step_id, f"[{level}] {message}")
            return

        if etype == "session.usage_info":
            limit = int(_get(data, "token_limit", "tokenLimit", default=0) or 0)
            current = int(_get(data, "current_tokens", "currentTokens", default=0) or 0)
            msgs = int(_get(data, "messages_length", "messagesLength", default=0) or 0)
            self.console.context_usage(step_id, current, limit, msgs)
            # 詳細内訳を構造化ログとして出力（GUI ポップアップ用）
            try:
                self.console.stats_event(
                    "session_usage_detail",
                    step_id=step_id,
                    current=current,
                    limit=limit,
                    msgs=msgs,
                    system=_get(data, "system_tokens", "systemTokens", default=None),
                    tool_definitions=_get(
                        data, "tool_definitions_tokens", "toolDefinitionsTokens", default=None
                    ),
                    conversation=_get(
                        data, "conversation_tokens", "conversationTokens", default=None
                    ),
                )
            except Exception:
                pass
            return

        if etype == "session.compaction_start":
            self.console.compaction(step_id, "start")
            return

        if etype == "session.compaction_complete":
            pre = int(_get(data, "pre_compaction_tokens", "preCompactionTokens", default=0) or 0)
            post = int(_get(data, "post_compaction_tokens", "postCompactionTokens", default=0) or 0)
            self.console.compaction(step_id, "complete", pre_tokens=pre, post_tokens=post)
            try:
                tokens_removed = int(
                    _get(data, "tokens_removed", "tokensRemoved", default=max(0, pre - post)) or 0
                )
                self.console.stats_event(
                    "compaction_complete",
                    step_id=step_id,
                    pre=pre,
                    post=post,
                    removed=tokens_removed,
                )
            except Exception:
                pass
            return

        if etype == "session.task_complete":
            summary = _get(data, "summary") or ""
            self.console.task_complete(step_id, summary=str(summary))
            return

        if etype == "session.shutdown":
            changes = _get(data, "code_changes", "codeChanges", default=None)
            reqs = int(_get(data, "total_premium_requests", "totalPremiumRequests", default=0) or 0)
            dur_ms = int(_get(data, "total_api_duration_ms", "totalApiDurationMs", default=0) or 0)
            lines_added = int(_get(changes, "lines_added", "linesAdded", default=0) or 0) if changes else 0
            lines_removed = int(_get(changes, "lines_removed", "linesRemoved", default=0) or 0) if changes else 0
            # SDK の ShutdownCodeChanges.files_modified は list[str]（件数ではない）。
            _files_mod = _get(changes, "files_modified", "filesModified", default=None) if changes else None
            files_mod = len(_files_mod) if isinstance(_files_mod, (list, tuple)) else int(_files_mod or 0)
            self.console.shutdown_stats(step_id, lines_added, lines_removed,
                                        files_mod, reqs, dur_ms)
            # GUI 連携: premium_requests を累積コスト計算に渡すための stats_event
            if reqs > 0:
                try:
                    self.console.stats_event(
                        "premium_requests",
                        step_id=step_id,
                        count=reqs,
                        model=getattr(self.config, "model", "") or "",
                    )
                except Exception:
                    pass
            return

        # --- パーミッション ---
        if etype == "permission.requested":
            req = _get(data, "permission_request", "permissionRequest", default=None)
            kind_obj = _get(req, "kind", default="") if req else ""
            kind_str = getattr(kind_obj, "value", str(kind_obj)) if kind_obj else ""
            self.console.permission(step_id, kind_str, resolved=False)
            # GUI 詳細ポップアップ用に累計数を通知
            self._permission_count += 1
            try:
                # `kind` は stats_event の位置引数名と衝突するため別キーで送る。
                self.console.stats_event(
                    "permission_count",
                    step_id=step_id,
                    count=self._permission_count,
                    permission_kind=kind_str,
                )
            except Exception:
                pass
            return

        if etype == "permission.completed":
            result_obj = _get(data, "result", default=None)
            kind_str = _get(result_obj, "kind", default="") if result_obj else ""
            kind_val = getattr(kind_str, "value", str(kind_str)) if kind_str else ""
            self.console.permission(step_id, "", resolved=True, result=kind_val)
            return

        if etype == "session.mcp_servers_loaded":
            servers = _get(data, "servers", default=[])
            for srv in servers:
                name = _get(srv, "name", default="?")
                status_obj = _get(srv, "status", default=None)
                status = getattr(status_obj, "value", str(status_obj)) if status_obj else "unknown"
                error = _get(srv, "error", default=None)
                transport_obj = _get(srv, "transport", default=None)
                source_obj = _get(srv, "source", default=None)
                self.console.mcp_server_status(
                    str(name),
                    status=str(status),
                    error=str(error) if error else "",
                    plugin_name=str(_get(srv, "plugin_name", "pluginName", default="") or ""),
                    transport=str(getattr(transport_obj, "value", transport_obj) or "") if transport_obj else "",
                    source=str(getattr(source_obj, "value", source_obj) or "") if source_obj else "",
                )
                if status == "connected":
                    self.console.status(f"✅ MCP サーバー '{name}' 接続成功")
                elif status in ("failed", "needs-auth"):
                    # Work IQ だけが best-effort（FR-QA-03 / FR-QA-06）。他サーバーは fail-closed ガード（FR-TS-03）を持つ。
                    _non_fatal = (
                        "。Work IQ は補助的な情報源のため実行は継続します"
                        if _is_workiq_mcp_server_name(name)
                        else ""
                    )
                    self.console.warning(
                        f"❌ MCP サーバー '{name}' 接続失敗 (status={status})"
                        + (f": {error}" if error else "")
                        + _non_fatal
                    )
                else:
                    self.console.event(f"ℹ️ MCP '{name}' status={status}")
            return

        if etype == "session.mcp_server_status_changed":
            server_name = _get(data, "server_name", "serverName", default="?")
            status_obj = _get(data, "status", default=None)
            status = getattr(status_obj, "value", str(status_obj)) if status_obj else "unknown"
            self.console.mcp_server_status(
                str(server_name),
                status=str(status),
                error=str(_get(data, "error", default="") or ""),
            )
            if status in ("failed", "needs-auth") and server_name == WORKIQ_MCP_SERVER_NAME:
                self.console.warning(
                    f"❌ Work IQ MCP サーバー接続状態変更: {status}"
                    "。Work IQ は補助的な情報源のため実行は継続します"
                )
            else:
                self.console.event(f"MCP '{server_name}' → {status}")
            return

        # --- その他 (既知だが詳細表示不要なイベント) ---
        if etype in (
            "session.idle",
            "session.title_changed",
            "session.context_changed",
            "user.message",
            "system.message",
            "tool.user_requested",
            "abort",
            "command.queued",
            "command.completed",
            "user_input.requested",
            "user_input.completed",
            "elicitation.requested",
            "elicitation.completed",
            "external_tool.requested",
            "external_tool.completed",
            "exit_plan_mode.requested",
            "exit_plan_mode.completed",
            # SDK 内部イベント: エンドユーザーへの付加価値がないため抑制
            "hook.start",
            "hook.end",
            "pending_messages.modified",
            "session.tools_updated",
        ):
            return

        # 未知のイベントタイプ: 将来の SDK 更新に備え verbose で表示
        self.console.event(f"[{step_id}] event: {etype}")


# ------------------------------------------------------------------
# 内部ヘルパー
# ------------------------------------------------------------------


def _blocking_stdin_read() -> str:
    """スレッドプール内で実行するブロッキング stdin 読み取り。"""
    try:
        return sys.stdin.readline().rstrip("\n")
    except (EOFError, OSError):
        return ""


async def _read_stdin_multiline(
    prompt_msg: str,
    console: Any,
    timeout: float = 300.0,
) -> str:
    """複数行の回答入力を受け付ける。

    入力形式: "番号: 選択肢ラベル" を1行1問で入力。
    空行で入力終了。stdin が非対話的な場合はデフォルト回答を自動適用。

    Args:
        prompt_msg: ユーザーへの入力促進メッセージ。
        console: Console インスタンス。
        timeout: タイムアウト秒数（デフォルト: 300 秒）。

    Returns:
        入力された複数行テキスト（空 = デフォルト回答採用）。
    """
    # stdin が非対話的（パイプ、リダイレクト等）の場合はスキップ
    if not sys.stdin.isatty():
        console.warning(
            f"{prompt_msg}\n"
            "  → stdin が非対話モードのため、デフォルト回答を自動適用します。"
        )
        return ""

    async with _get_stdin_lock():
        # 他のステップのストリーム出力と視覚的に分離
        print(flush=True)
        print(f"{timestamp_prefix()} {'─' * 50}", flush=True)
        console.warning(prompt_msg)
        print(f"{timestamp_prefix()} {'─' * 50}", flush=True)

        collected: List[str] = []
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, _blocking_stdin_read),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                console.warning(
                    f"入力タイムアウト ({timeout:.0f}s)。デフォルト回答を自動適用します。"
                )
                return ""

            # 空行で入力終了
            if not line.strip():
                break
            # "skip" で即座にデフォルト採用
            if line.strip().lower() == "skip":
                return ""
            collected.append(line)

        return "\n".join(collected)


def _extract_text(response: Any) -> str:
    """SDK レスポンスからテキスト部分を取り出す。

    SDK v0.2.2: send_and_wait() は SessionEvent | None を返す。
    テキストは event.data.content に格納される。
    """
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    # SDK v0.2.2: SessionEvent.data.content
    data = getattr(response, "data", None)
    if data is not None:
        for attr in ("content", "message"):
            val = getattr(data, attr, None)
            if val is not None:
                return str(val)
    # フォールバック: response 直接の属性
    for attr in ("content", "text", "message"):
        val = getattr(response, attr, None)
        if val is not None:
            return str(val)
    # 未知の型の場合はフォールバックで空文字を返す（repr 文字列の混入を防止）
    return ""


def _extract_json_block(text: str) -> Optional[str]:
    """テキストから最初の JSON オブジェクト（`{...}`）を抽出して返す。

    LLM の検証レスポンスに含まれる JSON を取り出すために使用する。
    ネストされたオブジェクトも正しく処理するために、文字の深さカウントを使用する。

    Returns:
        JSON 文字列（抽出できない場合は None）。
    """
    # ```json ... ``` フェンス内を先に探す（フェンスの開始 `{` から深さカウント）
    _fence_start = re.compile(r"```(?:json)?\s*\n?")
    m = _fence_start.search(text)
    search_text = text[m.end():] if m else text

    # `{` から始まる最初の JSON オブジェクトを深さカウントで抽出
    start = search_text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(search_text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return search_text[start : i + 1]
    return None


def _build_phase4_verification(
    after_scan: "ScanResult",
    before_score: int,
    verify_content: str,
    json_parse_error: Optional[str],
) -> "VerificationResult":
    """Phase 4d の検証結果を scan 実測値だけから決定的に構築する（FR-CLI-63）。

    判定は `self_improve._build_verification_result()` を単一の実装とし、
    LLM 応答は `notes` の説明としてのみ保持する。
    """
    verification = _build_verification_result(after_scan, before_score)
    notes = verify_content[:LEARNING_SUMMARY_MAX_LENGTH]
    if json_parse_error:
        notes = f"[json_parse_error={json_parse_error}] " + notes
    verification["notes"] = notes
    return verification
