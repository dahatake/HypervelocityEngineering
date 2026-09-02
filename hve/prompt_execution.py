"""hve.prompt_execution — Prompt 版の実行計画・plan hash・委譲実行（FR-PROMPT-01 / 03 / 04 / 05 / 11）。

本モジュールは Workflow 実行エンジンを持たない。検証済み request と保存済み GUI 設定から
既存 `orchestrate` サブコマンドの argv を組み立て、承認済みの計画だけを子プロセスとして
起動する薄い境界である。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from .input_aliases import ResolvedAlias, normalize_alias_pairs, validate_aliases
from .prompt_request import PromptRequest
from .resume_service import ResumeService, WorkflowDescriptor
from .run_state_store import DurableStateError, RunStateStore
from .runtime_observability import make_instance_id
from .workflow_order import sort_workflows_by_dependencies

PLAN_SCHEMA_VERSION = 1

Runner = Callable[..., "subprocess.CompletedProcess[Any]"]


@dataclass(frozen=True)
class WorkflowPlan:
    workflow_id: str
    requested_workflow_id: str
    steps: Tuple[str, ...]
    argv: Tuple[str, ...]
    input_aliases: Tuple[ResolvedAlias, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    schema_version: int
    goal: str
    head_commit: str
    workflows: Tuple[WorkflowPlan, ...]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_plan_json(self).encode("utf-8")).hexdigest()


def resolve_head_commit(repo_root: "str | Path") -> str:
    """リポジトリの HEAD commit を返す。取得できない場合は `"unknown"`。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=False,
        )
    except OSError:
        return "unknown"
    out = (proc.stdout or "").strip()
    return out if proc.returncode == 0 and out else "unknown"


def validate_resolved_head_commit(value: Any) -> str:
    """Return a resolved HEAD value or fail closed before durable execution."""
    checked = value.strip() if isinstance(value, str) else ""
    if not checked or checked.casefold() == "unknown":
        raise DurableStateError("repository HEAD commit could not be resolved")
    return checked


def build_execution_plan(
    request: PromptRequest,
    *,
    settings: Mapping[str, Mapping[str, Any]],
    repo_root: "str | Path",
    head_commit: str,
) -> ExecutionPlan:
    """検証済み request と保存済み設定から決定的な実行計画を組み立てる。"""
    from .gui.orchestrate_args import args_from_settings

    by_id = {w.workflow_id: w for w in request.workflows}
    ordered = sort_workflows_by_dependencies([w.workflow_id for w in request.workflows])

    plans: List[WorkflowPlan] = []
    for workflow_id in ordered:
        wf_request = by_id[workflow_id]
        aliases = validate_aliases(
            normalize_alias_pairs(
                [(a.canonical, a.actual) for a in wf_request.input_aliases]
            ),
            workflow_id=workflow_id,
            step_ids=list(wf_request.steps),
            repo_root=repo_root,
        )
        overrides = dict(request.settings_overrides)
        args = args_from_settings(
            settings,
            workflow=workflow_id,
            overrides=overrides,
            steps=list(wf_request.steps),
            goal=request.goal,
            input_aliases=[(a.canonical, a.actual) for a in aliases],
            repo_root=Path(repo_root),
        )
        _apply_workflow_params(args, wf_request.params)
        plans.append(
            WorkflowPlan(
                workflow_id=workflow_id,
                requested_workflow_id=wf_request.requested_workflow_id,
                steps=wf_request.steps,
                argv=tuple(args.to_argv()),
                input_aliases=aliases,
            )
        )

    return ExecutionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        goal=request.goal,
        head_commit=head_commit,
        workflows=tuple(plans),
    )


_TRUE_WORDS = frozenset({"true", "on", "yes", "1"})
_FALSE_WORDS = frozenset({"false", "off", "no", "0"})
# `TriState = Optional[bool]`。dataclass のアノテーションは文字列で保持される。
_TRISTATE_ANNOTATIONS = frozenset({"TriState", "Optional[bool]", "bool|None"})


def _apply_workflow_params(args: Any, params: Mapping[str, str]) -> None:
    """Workflow 固有パラメータを `OrchestrateArgs` の同名フィールドへ反映する。

    request の値は必ず文字列なので、宛先フィールドの型（list / 3 状態 bool / int）へ
    変換してから代入する。変換できない値と、`OrchestrateArgs` に対応フィールドが
    無いパラメータは fail-closed で拒否する（黙って捨てない）。
    """
    from dataclasses import fields as dataclass_fields

    known = {f.name: f for f in dataclass_fields(type(args))}
    for key, value in params.items():
        field_def = known.get(key)
        if field_def is None:
            raise ValueError(
                f"パラメータ '{key}' は Prompt 版の CLI 引数に対応していないため指定できません。"
            )
        setattr(args, key, _coerce_param(field_def, key, value))


def _coerce_param(field_def: Any, key: str, value: str) -> Any:
    """request の文字列パラメータを `OrchestrateArgs` のフィールド型へ変換する。"""
    annotation = str(field_def.type).replace(" ", "")
    text = value.strip()

    if annotation.startswith("List["):
        return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]

    if annotation in _TRISTATE_ANNOTATIONS or annotation == "bool":
        lowered = text.lower()
        if lowered in _TRUE_WORDS:
            return True
        if lowered in _FALSE_WORDS:
            return False
        raise ValueError(
            f"パラメータ '{key}' には true / false を指定してください（受け取った値: {value!r}）。"
        )

    if "int" in annotation:
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(
                f"パラメータ '{key}' には整数を指定してください（受け取った値: {value!r}）。"
            ) from exc

    return value


def canonical_plan_json(plan: ExecutionPlan) -> str:
    """plan hash の入力となる canonical JSON を返す。"""
    payload = {
        "goal": plan.goal,
        "head_commit": plan.head_commit,
        "schema_version": plan.schema_version,
        "workflows": [
            {
                "argv": list(wp.argv),
                "input_aliases": [
                    {"actual": a.actual, "canonical": a.canonical} for a in wp.input_aliases
                ],
                "steps": list(wp.steps),
                "workflow_id": wp.workflow_id,
            }
            for wp in plan.workflows
        ],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def format_plan(plan: ExecutionPlan) -> str:
    """利用者へ提示する計画テキストを返す。"""
    lines = [
        "# Prompt 版 実行計画",
        "",
        f"- HEAD: {plan.head_commit}",
        f"- 実行順: {' -> '.join(wp.workflow_id for wp in plan.workflows)}",
        "",
    ]
    for index, wp in enumerate(plan.workflows, start=1):
        lines.append(f"## {index}. {wp.workflow_id}")
        if wp.requested_workflow_id != wp.workflow_id:
            lines.append(f"- request の表記: `{wp.requested_workflow_id}`")
        lines.append(f"- Step: {', '.join(wp.steps) if wp.steps else '(既定の選択)'}")
        for alias in wp.input_aliases:
            lines.append(f"- 入力別名: `{alias.canonical}` → `{alias.actual}`")
        lines.append("- argv:")
        lines.append("  ```")
        lines.append("  " + " ".join(wp.argv))
        lines.append("  ```")
        lines.append("")
    lines.append(
        "（argv は確認用の表示です。実行は Agent が argv 配列で行うため、"
        "利用者が手で打つ必要はありません）"
    )
    lines.append("")
    lines.append(f"plan SHA-256: {plan.sha256}")
    lines.append("")
    lines.append(
        "承認方法: 利用者はこの計画を読み、「実行してください」と自然言語で伝えるだけでよい。\n"
        "Agent は承認を受けてから、上の plan SHA-256 を `--expected-sha256` に指定して実行すること。\n"
        "利用者へコマンドの入力を求めてはならない。"
    )
    return "\n".join(lines)


def _default_runner(argv: Sequence[str], **kwargs: Any) -> "subprocess.CompletedProcess[Any]":
    kwargs.pop("shell", None)
    return subprocess.run(list(argv), shell=False, check=False, **kwargs)


def _option_values(argv: Sequence[str], flag: str) -> Tuple[str, ...]:
    """Return explicit values for one long option without interpreting argv."""
    values: List[str] = []
    prefix = f"{flag}="
    for index, token in enumerate(argv):
        if token.startswith(prefix):
            values.append(token[len(prefix) :])
        elif token == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
    return tuple(values)


def _single_app_id(argv: Sequence[str]) -> Optional[str]:
    """Resolve only the unambiguous single APP-ID shape accepted by orchestrate."""
    app_ids_values = _option_values(argv, "--app-ids")
    legacy_values = _option_values(argv, "--app-id")
    if len(app_ids_values) > 1 or len(legacy_values) > 1:
        return None

    legacy = legacy_values[0].strip() if legacy_values else ""
    if app_ids_values:
        selected = [
            value.strip()
            for value in app_ids_values[0].split(",")
            if value.strip()
        ]
        if len(selected) != 1 or (legacy and legacy != selected[0]):
            return None
        return selected[0]
    return legacy or None


def _register_durable_execution(
    plan: ExecutionPlan,
    repo_root: "str | Path",
) -> Tuple[str, Tuple[str, ...]]:
    """Register every ordered Prompt Workflow before starting the first child."""
    with RunStateStore() as store:
        service = ResumeService(store, repo_root)
        descriptors: List[WorkflowDescriptor] = []
        for ordinal, workflow in enumerate(plan.workflows):
            safe_argv, missing_replay_keys = service.sanitize_argv(workflow.argv)
            descriptors.append(
                WorkflowDescriptor(
                    instance_id=make_instance_id(
                        workflow.workflow_id,
                        _single_app_id(safe_argv),
                    ),
                    workflow_id=workflow.workflow_id,
                    ordinal=ordinal,
                    mode="standard",
                    argv=safe_argv,
                    missing_replay_keys=missing_replay_keys,
                )
            )
        execution_id = service.register_execution(
            "prompt",
            tuple(descriptors),
            checkpoint_head=plan.head_commit,
        )
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise DurableStateError("durable registration returned an invalid execution ID")
    return execution_id, tuple(item.instance_id for item in descriptors)


def _verify_durable_child_completion(
    execution_id: str,
    instance_id: str,
) -> bool:
    """Verify that a zero-exit child committed a successful terminal state."""
    try:
        with RunStateStore() as store:
            instance = store.get_instance(execution_id, instance_id)
    except DurableStateError:
        return False
    if instance is None:
        return False
    try:
        status = str(instance["status"])
    except (IndexError, KeyError, TypeError):
        status = str(getattr(instance, "status", ""))
    return status in {"succeeded", "skipped"}


def _head_matches_approved_plan(
    plan: ExecutionPlan,
    cwd: "str | Path | None",
) -> bool:
    """Re-read HEAD so approval cannot outlive a pre-launch repository change."""
    if cwd is None:
        return True
    try:
        current_head = validate_resolved_head_commit(resolve_head_commit(cwd))
    except DurableStateError:
        return False
    return current_head == plan.head_commit


def run_plan(
    plan: ExecutionPlan,
    *,
    dry_run: bool,
    runner: Optional[Runner] = None,
    cwd: Optional["str | Path"] = None,
) -> int:
    """計画された Workflow を順番に実行する。最初の非 0 終了コードで打ち切る。"""
    try:
        validate_resolved_head_commit(plan.head_commit)
    except DurableStateError:
        print(
            "Prompt execution の HEAD commit を確認できません。子プロセスは起動していません。",
            file=sys.stderr,
        )
        return 1
    if not _head_matches_approved_plan(plan, cwd):
        print(
            "Prompt execution の HEAD が承認済み計画から変化しました。子プロセスは起動していません。",
            file=sys.stderr,
        )
        return 1
    execute = runner or _default_runner
    durable_identity: Optional[Tuple[str, Tuple[str, ...]]] = None
    if not dry_run:
        try:
            durable_identity = _register_durable_execution(
                plan,
                cwd if cwd is not None else Path.cwd(),
            )
        except DurableStateError:
            print(
                "Prompt durable execution の登録に失敗しました。子プロセスは起動していません。",
                file=sys.stderr,
            )
            return 1

    for ordinal, wp in enumerate(plan.workflows):
        if ordinal == 0 and not _head_matches_approved_plan(plan, cwd):
            print(
                "Prompt execution の HEAD が登録後に変化しました。子プロセスは起動していません。",
                file=sys.stderr,
            )
            return 1
        argv = [sys.executable, "-m", "hve", *wp.argv]
        if dry_run:
            argv.append("--dry-run")
        elif durable_identity is not None:
            execution_id, instance_ids = durable_identity
            argv.extend(
                (
                    "--execution-id",
                    execution_id,
                    "--instance-id",
                    instance_ids[ordinal],
                )
            )
        kwargs: dict = {"shell": False}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        try:
            result = execute(argv, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            print(
                f"Prompt child process を起動できませんでした ({type(exc).__name__})。",
                file=sys.stderr,
            )
            return 1
        raw_code = getattr(result, "returncode", None)
        if isinstance(raw_code, bool) or not isinstance(raw_code, int):
            print(
                "Prompt child process が有効な終了コードを返しませんでした。",
                file=sys.stderr,
            )
            return 1
        code = raw_code
        if code != 0:
            return code
        if not dry_run and durable_identity is not None:
            execution_id, instance_ids = durable_identity
            if not _verify_durable_child_completion(
                execution_id,
                instance_ids[ordinal],
            ):
                print(
                    "Prompt child process は成功終了しましたが、durable state が完了していません。",
                    file=sys.stderr,
                )
                return 1
    return 0
