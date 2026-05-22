#!/usr/bin/env python3
"""起動時トークン使用量の計測 harness。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MODEL_AUTO_VALUE = "Auto"
DEFAULT_MODEL = "claude-opus-4.7"
LIGHTWEIGHT_PROMPT = "このセッションは起動時計測です。'OK' のみ返答してください。"


@dataclass
class UsageSnapshot:
    current_tokens: int
    token_limit: int
    messages_length: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _event_type(event: Any) -> str:
    raw = getattr(event, "type", None)
    return getattr(raw, "value", "") or ""


def _event_data(event: Any) -> Any:
    return getattr(event, "data", None)


def _event_get(data: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(data, dict) and key in data:
            val = data[key]
            if val is not None:
                return val
        if hasattr(data, key):
            val = getattr(data, key)
            if val is not None:
                return val
    return default


def _sanitize_label(label: str) -> str:
    basename = Path(label.strip()).name
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", basename)
    cleaned = cleaned.strip("._-")
    return cleaned or "measurement"


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _load_mcp_servers(repo_root: Path, mcp_config_path: Optional[str]) -> Dict[str, Any]:
    if mcp_config_path:
        path = Path(mcp_config_path)
    else:
        path = repo_root / ".github" / ".mcp.json"

    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(data, dict):
        mcp = data.get("mcpServers")
        if isinstance(mcp, dict):
            return mcp
    return {}


def _import_sdk() -> Dict[str, Any]:
    try:
        from copilot import CopilotClient, ExternalServerConfig, SubprocessConfig  # type: ignore[import]
        from copilot.session import PermissionHandler  # type: ignore[import]

        return {
            "CopilotClient": CopilotClient,
            "SubprocessConfig": SubprocessConfig,
            "ExternalServerConfig": ExternalServerConfig,
            "PermissionHandler": PermissionHandler,
            "module": "copilot",
        }
    except ImportError:
        from github_copilot_sdk import CopilotClient, ExternalServerConfig, SubprocessConfig  # type: ignore[import]
        from github_copilot_sdk.session import PermissionHandler  # type: ignore[import]

        return {
            "CopilotClient": CopilotClient,
            "SubprocessConfig": SubprocessConfig,
            "ExternalServerConfig": ExternalServerConfig,
            "PermissionHandler": PermissionHandler,
            "module": "github_copilot_sdk",
        }


async def measure_single_session(session: Any, prompt: str, timeout: float) -> Dict[str, Any]:
    usage: Optional[UsageSnapshot] = None

    def _handle_event(event: Any) -> None:
        nonlocal usage
        if usage is not None:
            return
        if _event_type(event) != "session.usage_info":
            return

        data = _event_data(event)
        usage = UsageSnapshot(
            current_tokens=_safe_int(_event_get(data, "current_tokens", "currentTokens", default=0)),
            token_limit=_safe_int(_event_get(data, "token_limit", "tokenLimit", default=0)),
            messages_length=_safe_int(_event_get(data, "messages_length", "messagesLength", default=0)),
        )

    session.on(_handle_event)

    status = "ok"
    error_message = None
    try:
        await session.send_and_wait(prompt, timeout=timeout)
    except Exception as exc:
        status = "send_failed"
        error_message = str(exc)
    finally:
        await session.disconnect()

    result: Dict[str, Any] = {
        "status": status,
        "current_tokens": usage.current_tokens if usage else None,
        "token_limit": usage.token_limit if usage else None,
        "messages_length": usage.messages_length if usage else None,
    }
    if usage is None and status == "ok":
        result["status"] = "usage_info_not_observed"
    if error_message:
        result["error"] = error_message
    return result


async def _measure_phase(
    client: Any,
    phase_name: str,
    *,
    permission_handler: Any,
    model: str,
    mcp_servers: Optional[Dict[str, Any]],
    prompt: str,
    timeout: float,
) -> Dict[str, Any]:
    session_opts: Dict[str, Any] = {
        "on_permission_request": permission_handler.approve_all,
        "streaming": True,
    }
    if model and model != MODEL_AUTO_VALUE:
        session_opts["model"] = model
    if mcp_servers:
        session_opts["mcp_servers"] = mcp_servers

    session = await client.create_session(**session_opts)
    measured = await measure_single_session(session, prompt, timeout)
    measured["phase"] = phase_name
    return measured


async def _measure_cli_only(
    client: Any,
    *,
    permission_handler: Any,
    model: str,
    prompt: str,
    timeout: float,
) -> Dict[str, Any]:
    return await _measure_phase(
        client,
        "cli-only",
        permission_handler=permission_handler,
        model=model,
        mcp_servers=None,
        prompt=prompt,
        timeout=timeout,
    )


async def _measure_hve_config(
    client: Any,
    *,
    repo_root: Path,
    permission_handler: Any,
    model: str,
    mcp_servers: Dict[str, Any],
    prompt: str,
    timeout: float,
    auto_qa: bool,
    auto_contents_review: bool,
    workiq_enabled: bool,
    workiq_tenant_id: Optional[str],
) -> Dict[str, Any]:
    phases: Dict[str, Any] = {}
    non_fatal_warnings: List[str] = []

    main_mcp = dict(mcp_servers)
    if workiq_enabled:
        try:
            if str(repo_root) not in sys.path:
                sys.path.insert(0, str(repo_root))
            from hve.workiq import build_workiq_mcp_config  # type: ignore[import]

            workiq_mcp = build_workiq_mcp_config(tenant_id=workiq_tenant_id)
            for key, value in workiq_mcp.items():
                if key not in main_mcp:
                    main_mcp[key] = value
        except Exception as exc:
            # Work IQ 設定の読み込みに失敗しても、計測自体は継続する。
            non_fatal_warnings.append(f"workiq_mcp_setup_failed: {exc}")

    phases["main"] = await _measure_phase(
        client,
        "main",
        permission_handler=permission_handler,
        model=model,
        mcp_servers=main_mcp,
        prompt=prompt,
        timeout=timeout,
    )

    if auto_qa:
        phases["pre_qa"] = await _measure_phase(
            client,
            "pre_qa",
            permission_handler=permission_handler,
            model=model,
            mcp_servers=main_mcp,
            prompt=prompt,
            timeout=timeout,
        )
        phases["qa"] = await _measure_phase(
            client,
            "qa",
            permission_handler=permission_handler,
            model=model,
            mcp_servers=main_mcp,
            prompt=prompt,
            timeout=timeout,
        )
    else:
        phases["pre_qa"] = {"status": "skipped", "reason": "auto_qa=False"}
        phases["qa"] = {"status": "skipped", "reason": "auto_qa=False"}

    if auto_contents_review:
        phases["review"] = await _measure_phase(
            client,
            "review",
            permission_handler=permission_handler,
            model=model,
            mcp_servers=main_mcp,
            prompt=prompt,
            timeout=timeout,
        )
    else:
        phases["review"] = {"status": "skipped", "reason": "auto_contents_review=False"}

    result = {
        "options": {
            "auto_qa": auto_qa,
            "auto_contents_review": auto_contents_review,
            "auto_self_improve": False,
            "workiq_enabled": workiq_enabled,
            "dry_run": False,
        },
        "phases": phases,
    }
    if non_fatal_warnings:
        result["warnings"] = non_fatal_warnings
    return result


async def _run_measurement(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    sdk_details: Dict[str, Any]

    payload: Dict[str, Any] = {
        "timestamp": _utc_now_iso(),
        "label": args.label,
        "git_commit": _git_commit(repo_root),
        "repo_root": str(repo_root),
        "mode": args.mode,
        "measurements": {},
        "environment": {
            "python": sys.version,
        },
    }

    try:
        sdk_details = _import_sdk()
        payload["environment"]["sdk_module"] = sdk_details["module"]
    except Exception as exc:
        payload["status"] = "sdk_unavailable"
        payload["error"] = f"SDK import failed: {exc}"
        return payload

    mcp_servers = _load_mcp_servers(repo_root, args.mcp_config)
    payload["environment"]["mcp_servers"] = sorted(list(mcp_servers.keys()))

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    model = args.model or os.environ.get("MODEL") or DEFAULT_MODEL
    workiq_tenant_id = args.workiq_tenant_id or os.environ.get("WORKIQ_TENANT_ID")

    if args.cli_url:
        sdk_cfg = sdk_details["ExternalServerConfig"](url=args.cli_url)
    else:
        sdk_cfg = sdk_details["SubprocessConfig"](
            cli_path=args.cli_path,
            github_token=token,
            log_level="error",
            cli_args=[],
        )

    client = sdk_details["CopilotClient"](config=sdk_cfg)
    errors: List[str] = []
    try:
        await client.start()
    except Exception as exc:
        payload["status"] = "client_start_failed"
        payload["error"] = f"CopilotClient.start failed: {exc}"
        return payload
    try:
        if args.mode in ("cli", "both"):
            try:
                payload["measurements"]["cli_only"] = await _measure_cli_only(
                    client,
                    permission_handler=sdk_details["PermissionHandler"],
                    model=model,
                    prompt=args.prompt,
                    timeout=args.timeout,
                )
            except Exception as exc:
                payload["measurements"]["cli_only"] = {
                    "status": "measurement_failed",
                    "error": str(exc),
                }
                errors.append(f"cli_only failed: {exc}")

        if args.mode in ("hve", "both"):
            hve_configs: Dict[str, Any] = {}
            try:
                hve_configs["default"] = await _measure_hve_config(
                    client,
                    repo_root=repo_root,
                    permission_handler=sdk_details["PermissionHandler"],
                    model=model,
                    mcp_servers=mcp_servers,
                    prompt=args.prompt,
                    timeout=args.timeout,
                    auto_qa=False,
                    auto_contents_review=False,
                    workiq_enabled=False,
                    workiq_tenant_id=workiq_tenant_id,
                )
            except Exception as exc:
                hve_configs["default"] = {"status": "measurement_failed", "error": str(exc)}
                errors.append(f"hve.default failed: {exc}")

            try:
                hve_configs["all_features"] = await _measure_hve_config(
                    client,
                    repo_root=repo_root,
                    permission_handler=sdk_details["PermissionHandler"],
                    model=model,
                    mcp_servers=mcp_servers,
                    prompt=args.prompt,
                    timeout=args.timeout,
                    auto_qa=True,
                    auto_contents_review=True,
                    workiq_enabled=True,
                    workiq_tenant_id=workiq_tenant_id,
                )
            except Exception as exc:
                hve_configs["all_features"] = {"status": "measurement_failed", "error": str(exc)}
                errors.append(f"hve.all_features failed: {exc}")

            payload["measurements"]["hve"] = {"configurations": hve_configs}
    finally:
        try:
            await client.stop()
        except Exception as exc:
            errors.append(f"CopilotClient.stop failed: {exc}")

    if errors:
        payload["status"] = "partial_failure" if payload["measurements"] else "failed"
        payload["error"] = " | ".join(errors)
    else:
        payload["status"] = "ok"
    return payload


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure startup token usage")
    parser.add_argument("--mode", choices=["cli", "hve", "both"], default="both")
    parser.add_argument("--label", required=True)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--output-dir", default="measurements")
    parser.add_argument("--cli-path", default=None)
    parser.add_argument("--cli-url", default=None)
    parser.add_argument("--mcp-config", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--workiq-tenant-id", default=None)
    parser.add_argument("--prompt", default=LIGHTWEIGHT_PROMPT)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args(argv)


def _write_measurement(payload: Dict[str, Any], output_dir: Path, label: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = _sanitize_label(label)
    out_path = output_dir / f"{ts}-{safe_label}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    payload = asyncio.run(_run_measurement(args))
    out_path = _write_measurement(payload, Path(args.output_dir), args.label)
    print(f"saved: {out_path}")
    if payload.get("status") != "ok":
        print(f"status: {payload.get('status')}", file=sys.stderr)
        if payload.get("error"):
            print(payload["error"], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
