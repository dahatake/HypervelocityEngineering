"""Copilot SDK client construction helpers.

GitHub Copilot SDK 1.0.0 removed the older ``SubprocessConfig`` /
``ExternalServerConfig`` construction path used by this project.  Keep the
translation from HVE's existing ``cli_path`` / ``cli_url`` settings to the SDK
1.0.0 ``RuntimeConnection`` API in one small place.
"""

from __future__ import annotations

from functools import lru_cache
import shutil
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence


@lru_cache(maxsize=1)
def _require_pwsh7_on_windows() -> Optional[str]:
    """Return the installed ``pwsh`` path or fail before local SDK startup.

    GitHub Copilot CLI uses ``pwsh`` for its Windows PowerShell tool. HVE must
    never let a missing modern shell fall back to Windows PowerShell 5.1.
    """
    if not sys.platform.startswith("win"):
        return None

    pwsh = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if not pwsh:
        raise RuntimeError(
            "HVE on Windows requires PowerShell 7+ (pwsh.exe); "
            "Windows PowerShell 5.1 fallback is prohibited."
        )

    probe = subprocess.run(
        [
            pwsh,
            "-NoLogo",
            "-NoProfile",
            "-Command",
            "if ($PSVersionTable.PSEdition -eq 'Core' -and "
            "$PSVersionTable.PSVersion.Major -ge 7) { exit 0 } else { exit 1 }",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            "HVE resolved a non-Core or pre-7 PowerShell executable; "
            "install/update PowerShell 7 and ensure pwsh.exe is on PATH."
        )
    return pwsh


def create_copilot_client(
    *,
    cli_path: Optional[str] = None,
    cli_url: Optional[str] = None,
    github_token: Optional[str] = None,
    log_level: str = "info",
    cli_args: Optional[Sequence[str]] = None,
    working_directory: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Any:
    """Create a ``CopilotClient`` using the SDK 1.0.0 connection API.

    Args:
        cli_path: Local Copilot CLI binary path. ``None`` lets the SDK/runtime
            choose its default binary.
        cli_url: Existing headless Copilot CLI server URL. When set, the SDK
            connects to that server and does not spawn a local process.
        github_token: Token for local stdio runtime authentication. Not passed
            for ``cli_url`` connections because SDK URI connections are for an
            already-running runtime.
        log_level: SDK runtime log level.
        cli_args: Additional CLI args for local stdio runtime.
        working_directory: Optional runtime working directory.
        env: Optional environment for spawned local runtime.
    """
    try:
        from copilot import CopilotClient  # type: ignore[import]
    except ImportError:
        # SDK自体が存在しない場合はlegacy importを再試行せず、呼出側の
        # graceful degradationへ同じImportErrorを返す。
        raise

    if not cli_url:
        _require_pwsh7_on_windows()

    try:
        from copilot import RuntimeConnection  # type: ignore[import]
    except ImportError:
        # moduleとCopilotClientは存在するがRuntimeConnectionだけがない場合は、
        # pre-1.0 SDKまたはlegacy-shaped test doubleとして扱う。
        if env is not None:
            raise RuntimeError(
                "The installed Copilot SDK cannot inject the required runtime "
                "environment; RuntimeConnection support is required."
            )
        return _create_legacy_config_client(
            cli_path=cli_path,
            cli_url=cli_url,
            github_token=github_token,
            log_level=log_level,
            cli_args=cli_args,
        )

    connection: Any
    if cli_url:
        connection = RuntimeConnection.for_uri(cli_url)
        kwargs: dict[str, Any] = {
            "connection": connection,
            "log_level": log_level,
        }
    else:
        connection = RuntimeConnection.for_stdio(
            path=cli_path,
            args=tuple(cli_args or ()),
        )
        kwargs = {
            "connection": connection,
            "log_level": log_level,
        }
        if github_token:
            kwargs["github_token"] = github_token
        if working_directory:
            kwargs["working_directory"] = working_directory
        if env:
            kwargs["env"] = dict(env)

    return CopilotClient(**kwargs)


def _create_legacy_config_client(
    *,
    cli_path: Optional[str],
    cli_url: Optional[str],
    github_token: Optional[str],
    log_level: str,
    cli_args: Optional[Sequence[str]],
) -> Any:
    """Fallback for older SDK-shaped test doubles and pre-1.0 SDKs."""
    from copilot import CopilotClient  # type: ignore[import]

    if cli_url:
        from copilot import ExternalServerConfig  # type: ignore[attr-defined]

        return CopilotClient(config=ExternalServerConfig(url=cli_url))  # type: ignore[call-arg]

    from copilot import SubprocessConfig  # type: ignore[attr-defined]

    return CopilotClient(  # type: ignore[call-arg]
        config=SubprocessConfig(
            cli_path=cli_path,
            github_token=github_token,
            log_level=log_level,
            cli_args=tuple(cli_args or ()),
        )
    )